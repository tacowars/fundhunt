"""Deep-read support: find a record's official documents and extract text.

Per-source recipes (each verified against the live portals):
- bdns: the documentos API (detail JSON → documentos[].id → documento
  endpoint); convocatoria text first, then bases reguladoras, then the rest.
- placsp: the feed's captured document references (pliegos first);
  otherwise the detail page, which sits behind an intermittent WAF.
- ted: the /pdf rendering of the notice (the detail page is a JS shell).
- sedia: topicDetails/<id lowercased>.json — its description/conditions
  text, plus the call-fiche PDF linked from it when there is one.
- sedia_cascade: no portal document; the stored summary is the source.
- interreg / epah: plain GET of the stored URL, tolerating link rot.

Every failure degrades to a status on that document, never an exception:
the agent then judges on stored fields and says so.
"""

from __future__ import annotations

import hashlib
import html
import io
import json
import re
import time
import unicodedata
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urlsplit

import httpx

from . import http
from .models import Opportunity
from .settings import docs_cache_dir

BDNS_API = "https://www.infosubvenciones.es/bdnstrans/api"
SEDIA_TOPIC = "https://ec.europa.eu/info/funding-tenders/opportunities/data/topicDetails"
BROWSER_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/140.0 Safari/537.36")
MAX_BYTES = 25_000_000
MIN_CHARS = 300
SPACING_S = 0.5

_TED_DETAIL = re.compile(r"ted\.europa\.eu/.*/detail/(\d+-\d+)")
_PLACSP_ANCHOR = re.compile(
    r"<a[^>]*href=\"([^\"]*GetDocumentByIdServlet[^\"]*)\"[^>]*>(.*?)</a>", re.I | re.S)
_EMBEDDED_URL = re.compile(r"https?://[^\s\"'<>]+")
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_SKIP = {"script", "style", "nav", "header", "footer", "noscript"}


@dataclass
class Doc:
    role: str
    url: str
    priority: int = 5
    status: str = "pending"   # ok | unreadable | failed | pending
    text: str = ""
    note: str | None = None


def _fold(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s.lower())
                   if not unicodedata.combining(c))


class _Text(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.skip, self.parts = 0, []

    def handle_starttag(self, tag, attrs):
        self.skip += tag in _SKIP

    def handle_endtag(self, tag):
        if tag in _SKIP and self.skip:
            self.skip -= 1

    def handle_data(self, data):
        if not self.skip and data.strip():
            self.parts.append(data)


def html_to_text(s: str) -> str:
    p = _Text()
    p.feed(s)
    p.close()
    return clean("\n".join(p.parts))


def clean(text: str) -> str:
    text = _CONTROL.sub("", text)
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n\s*\n+", "\n\n", text).strip()


def extract(content: bytes, media_type: str | None) -> tuple[str, str]:
    """(status, text) for fetched bytes: PDF via pypdf, HTML via the parser."""
    if not content or len(content) > MAX_BYTES:
        return "unreadable", ""
    head = content[:2000].lower()
    try:
        if content[:5] == b"%PDF-" or "pdf" in (media_type or ""):
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(content))
            text = clean("\n".join((pg.extract_text() or "") for pg in reader.pages))
        elif "html" in (media_type or "") or b"<html" in head or b"<!doctype html" in head:
            text = html_to_text(content.decode("utf-8", errors="replace"))
        else:
            text = clean(content.decode("utf-8", errors="replace"))
    except Exception:
        return "unreadable", ""
    if len(text) < MIN_CHARS:
        return "unreadable", text
    return "ok", text


def _looks_like_waf(content: bytes) -> bool:
    head = content[:4000].lower()
    return b"<html" in head and (b"tspd" in head or b"bobcmn" in head
                                 or b"please enable javascript" in head)


class Fetcher:
    """Polite GETs with a small on-disk cache keyed by URL."""

    def __init__(self, client: httpx.Client | None = None, use_cache: bool = True):
        self.c = client or http.client(timeout=60)
        self.use_cache = use_cache
        self._last = 0.0

    def get(self, url: str, browser: bool = False) -> tuple[bytes, str | None]:
        key = hashlib.sha256(url.encode()).hexdigest()
        cache = docs_cache_dir() / key
        if self.use_cache and cache.exists():
            meta = cache.with_suffix(".type")
            return cache.read_bytes(), meta.read_text() if meta.exists() else None
        wait = SPACING_S - (time.monotonic() - self._last)
        if wait > 0:
            time.sleep(wait)
        headers = {"User-Agent": BROWSER_UA} if browser else {}
        resp = http.request(self.c, "GET", url, headers=headers, retries=1)
        self._last = time.monotonic()
        content = resp.content
        if _looks_like_waf(content):
            raise RuntimeError("bot-protection interstitial instead of the document")
        mtype = resp.headers.get("content-type")
        if self.use_cache:
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_bytes(content)
            if mtype:
                cache.with_suffix(".type").write_text(mtype)
        return content, mtype


def _harvest_links(node) -> list[str]:
    out: list[str] = []

    def add(u: str):
        if u not in out:
            out.append(u)

    def walk(n):
        if isinstance(n, str):
            if n.startswith(("http://", "https://")):
                add(n)
            if "http" in n:
                for m in _EMBEDDED_URL.findall(html.unescape(n)):
                    add(m)
        elif isinstance(n, dict):
            for v in n.values():
                walk(v)
        elif isinstance(n, list):
            for v in n:
                walk(v)

    walk(node)
    return out


def _is_pdf(link: str) -> bool:
    low = link.lower()
    return urlsplit(low).path.endswith(".pdf") or low.endswith(".pdf")


def discover(opp: Opportunity, f: Fetcher) -> tuple[list[Doc], list[str]]:
    """Candidate documents in priority order, plus notes about the discovery."""
    notes: list[str] = []
    docs: list[Doc] = []
    if opp.source == "bdns":
        content, _ = f.get(f"{BDNS_API}/convocatorias?numConv={opp.source_id}")
        for e in (json.loads(content).get("documentos") or []):
            if e.get("id") is None:
                continue
            label = _fold(str(e.get("descripcion") or e.get("nombreFic") or ""))
            prio = (0 if "convocatoria" in label and "extracto" not in label
                    else 1 if "bases regulador" in label
                    else 3 if "extracto" in label else 2)
            docs.append(Doc(role=label[:60] or "documento", priority=prio,
                            url=f"{BDNS_API}/convocatorias/documentos?idDocumento={e['id']}"))
        if not docs:
            notes.append("BDNS record lists no documentos")
    elif opp.source == "placsp":
        for d in opp.documents:
            label = _fold(f"{d.role} {d.name or ''}")
            prio = 0 if d.role in {"legal", "technical"} or "pliego" in label else 2
            docs.append(Doc(role=f"{d.role}:{d.name or ''}", url=d.uri, priority=prio))
        if not docs and opp.url:
            try:
                page, _ = f.get(opp.url, browser=True)
                for href, label in _PLACSP_ANCHOR.findall(page.decode("utf-8", "replace")):
                    lab = _fold(re.sub(r"<[^>]+>", "", label))
                    prio = 0 if "pliego" in lab else 2 if "anuncio" in lab else 3
                    docs.append(Doc(role=lab[:60] or "documento",
                                    url=html.unescape(href), priority=prio))
            except Exception as exc:
                notes.append(f"PLACSP detail page unavailable ({exc})")
    elif opp.source == "ted":
        m = _TED_DETAIL.search(opp.url or "")
        if m:
            docs.append(Doc(role="notice", url=f"https://ted.europa.eu/es/notice/{m.group(1)}/pdf",
                            priority=0))
        else:
            notes.append("TED url is not a notice detail link")
    elif opp.source == "sedia":
        if "europeaid" in _fold(opp.source_id):
            notes.append("EuropeAid topic: documents sit behind an EU login")
        else:
            url = f"{SEDIA_TOPIC}/{opp.source_id.lower()}.json"
            try:
                content, _ = f.get(url)
                payload = json.loads(content)
                topic = payload.get("TopicDetails") or payload
                blobs = [topic.get(k) for k in ("description", "conditions",
                                                "supportInfo", "budgetOverviewJSONItem")]
                text = html_to_text("\n".join(str(b) for b in blobs if b))
                docs.append(Doc(role="topic description", url=url, priority=0,
                                status="ok" if len(text) >= MIN_CHARS else "unreadable",
                                text=text))
                pdfs = [u for u in _harvest_links(payload) if _is_pdf(u)]
                fiche = next((u for u in pdfs if "call-fiche" in u.lower()), None)
                if fiche:
                    docs.append(Doc(role="call fiche", url=fiche, priority=1))
            except Exception as exc:
                notes.append(f"SEDIA topicDetails unavailable ({exc})")
    elif opp.source == "sedia_cascade":
        notes.append("cascade calls have no portal document; the stored summary is the source"
                     " — the call's own page (url) may have more")
        if opp.url:
            docs.append(Doc(role="call page", url=opp.url, priority=0))
    elif opp.url:
        docs.append(Doc(role="page", url=opp.url, priority=0))
    docs.sort(key=lambda d: d.priority)
    return docs, notes


def read(opp: Opportunity, max_chars: int = 60_000, max_docs: int = 3,
         fetcher: Fetcher | None = None) -> dict:
    f = fetcher or Fetcher()
    try:
        docs, notes = discover(opp, f)
    except Exception as exc:
        docs, notes = [], [f"document discovery failed ({exc})"]
    budget = max_chars
    out = []
    for d in docs[:max_docs]:
        if d.status == "pending":
            try:
                content, mtype = f.get(d.url, browser=opp.source == "placsp")
                d.status, d.text = extract(content, mtype)
            except Exception as exc:
                d.status, d.note = "failed", str(exc)[:200]
        text = d.text[:budget] if d.status == "ok" else ""
        budget -= len(text)
        out.append({"role": d.role, "url": d.url, "status": d.status, "note": d.note,
                    "chars": len(d.text), "truncated": len(text) < len(d.text),
                    "text": text})
        if budget <= 0:
            break
    return {"ref": opp.ref, "notes": notes,
            "documents_found": len(docs), "documents": out,
            "readable": any(d["status"] == "ok" for d in out)}
