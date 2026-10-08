"""PLACSP (Spanish public procurement) — Atom feeds carrying CODICE XML.

PLACSP re-emits the whole licitación on every field change, so a tender
appears many times across feed pages; dedup key is ContractFolderID and
revision tracking captures each re-emission that changed content. Feeds
are newest-first, so the first occurrence per folder in a walk is the
newest emission.

contrataciondelestado.es sits behind an INTERMITTENT F5/Shape bot
challenge (an HTML body even on HTTP 200); the official mirror
contrataciondelsectorpublico.gob.es serves the same /sindicacion/ tree.
Prefer the mirror and fail over per page. Feed-internal rel=next links
are absolute on the primary host, so rewrite them before following.
Parsed with lxml: feedparser flattens CODICE lossily.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timedelta

import httpx
from lxml import etree

from .. import http
from ..models import Classification, DocumentRef, Kind, Opportunity, lifecycle
from . import SyncContext

_PRIMARY_HOST = "contrataciondelestado.es"
_MIRROR_HOST = "contrataciondelsectorpublico.gob.es"

FEEDS = [
    f"https://{_MIRROR_HOST}/sindicacion/sindicacion_643/licitacionesPerfilesContratanteCompleto3.atom",
    f"https://{_MIRROR_HOST}/sindicacion/sindicacion_1044/PlataformasAgregadasSinMenores.atom",
]
MAX_PAGES = 80               # per feed, incremental runs
# The archive is dominated by award/resolution re-emissions (~80% of a
# 30-day walk was already closed, and the walk took 15+ minutes), so the
# first run looks back two weeks and skips closed entries; above-threshold
# tenders with older publication still arrive through TED's open stock.
FIRST_RUN_DAYS = 14
FIRST_RUN_MAX_PAGES = 250    # per feed

NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "cbc": "urn:dgpe:names:draft:codice:schema:xsd:CommonBasicComponents-2",
    "cac": "urn:dgpe:names:draft:codice:schema:xsd:CommonAggregateComponents-2",
    "cbc-place-ext": "urn:dgpe:names:draft:codice-place-ext:schema:xsd:CommonBasicComponents-2",
    "cac-place-ext": "urn:dgpe:names:draft:codice-place-ext:schema:xsd:CommonAggregateComponents-2",
}

# ContractFolderStatusCode → label (CODICE code list)
STATUS = {"PRE": "anuncio previo", "PUB": "en plazo", "EV": "evaluación",
          "ADJ": "adjudicada", "RES": "resuelta", "ANUL": "anulada"}

_DOC_REFS = [
    ("cac:LegalDocumentReference", "legal"),
    ("cac:TechnicalDocumentReference", "technical"),
    ("cac:AdditionalDocumentReference", "additional"),
]


def _to_mirror(url: str) -> str:
    return url.replace(f"//{_PRIMARY_HOST}/", f"//{_MIRROR_HOST}/", 1)


def _swap_host(url: str) -> str:
    if f"//{_MIRROR_HOST}/" in url:
        return url.replace(f"//{_MIRROR_HOST}/", f"//{_PRIMARY_HOST}/", 1)
    return _to_mirror(url)


def _get_feed(c: httpx.Client, url: str):
    """Fetch and parse one page; on failure retry once on the other host."""
    try:
        return etree.fromstring(http.request(c, "GET", url, retries=0).content)
    except (etree.XMLSyntaxError, httpx.HTTPError):
        return etree.fromstring(http.request(c, "GET", _swap_host(url)).content)


def _t(node, path: str) -> str | None:
    r = node.xpath(f"string({path})", namespaces=NS)
    return r.strip() if r and r.strip() else None


def _document_refs(status_node) -> list[DocumentRef]:
    docs, seen = [], set()
    for element, role in _DOC_REFS:
        for ref in status_node.findall(element, NS):
            uri = _t(ref, "cac:Attachment/cac:ExternalReference/cbc:URI")
            if not uri or (role, uri) in seen:
                continue
            seen.add((role, uri))
            docs.append(DocumentRef(role=role, name=_t(ref, "cbc:ID"), uri=uri))
    return docs


def entry_to_opportunity(entry) -> Opportunity | None:
    status_node = entry.find(".//cac-place-ext:ContractFolderStatus", NS)
    if status_node is None:
        return None
    folder_id = _t(status_node, "cbc:ContractFolderID")
    if not folder_id:
        return None
    link = entry.find("atom:link", NS)
    status_code = _t(status_node, "cbc-place-ext:ContractFolderStatusCode")
    buyer = (_t(status_node, ".//cac-place-ext:LocatedContractingParty//cac:PartyName/cbc:Name")
             or _t(status_node, ".//cac:Party//cac:PartyName/cbc:Name"))

    project = status_node.find(".//cac:ProcurementProject", NS)
    cpvs, amount, nuts, summary = [], None, [], None
    if project is not None:
        cpvs = [c.text.strip() for c in project.findall(
            ".//cac:RequiredCommodityClassification/cbc:ItemClassificationCode", NS) if c.text]
        amount_s = (_t(project, ".//cac:BudgetAmount/cbc:EstimatedOverallContractAmount")
                    or _t(project, ".//cac:BudgetAmount/cbc:TotalAmount"))
        try:
            amount = float(amount_s) if amount_s else None
        except ValueError:
            amount = None
        nuts = [n.text.strip() for n in project.findall(
            ".//cac:RealizedLocation/cbc:CountrySubentityCode", NS) if n.text]
        summary = _t(project, "cbc:Name")

    deadline_s = _t(status_node, ".//cac:TenderingProcess/cac:TenderSubmissionDeadlinePeriod/cbc:EndDate")
    deadline_t = _t(status_node, ".//cac:TenderingProcess/cac:TenderSubmissionDeadlinePeriod/cbc:EndTime")
    deadline = None
    if deadline_s:
        try:
            deadline = datetime.fromisoformat(deadline_s[:10] + "T" + (deadline_t or "23:59:59")[:8])
        except ValueError:
            pass

    title = _t(entry, "atom:title") or f"Licitación {folder_id}"
    return Opportunity(
        source="placsp",
        source_id=folder_id,
        kind=Kind.TENDER,
        title=title[:500],
        summary=summary if summary and summary != title else None,
        funder=buyer,
        country="ES",
        regions=nuts,
        classifications=[Classification(scheme="cpv", code=c) for c in cpvs],
        budget_value=amount,
        budget_currency="EUR" if amount is not None else None,
        status=STATUS.get(status_code or "", status_code),
        deadline=deadline,
        deadlines_raw=[s for s in (deadline_s, deadline_t) if s],
        url=link.get("href") if link is not None else None,
        language="spa",
        documents=_document_refs(status_node),
        raw={"type_code": _t(status_node, ".//cac:ProcurementProject/cbc:TypeCode")},
    )


def parse_page(root, cutoff: datetime) -> tuple[list[Opportunity], bool, str | None]:
    """(opportunities, oldest_reached, next_url) for one parsed feed page."""
    out, oldest = [], False
    entries = root.findall("atom:entry", NS)
    for entry in entries:
        updated_s = _t(entry, "atom:updated")
        try:
            updated = datetime.fromisoformat(updated_s) if updated_s else None
        except ValueError:
            updated = None
        if updated and updated < cutoff:
            oldest = True
            continue
        opp = entry_to_opportunity(entry)
        if opp:
            out.append(opp)
    nxt = root.xpath("atom:link[@rel='next']/@href", namespaces=NS)
    return out, oldest or not entries, (_to_mirror(nxt[0]) if nxt else None)


def fetch(ctx: SyncContext) -> Iterator[Opportunity]:
    days = FIRST_RUN_DAYS if ctx.first_run else ctx.since_days
    max_pages = FIRST_RUN_MAX_PAGES if ctx.first_run else MAX_PAGES
    cutoff = datetime.now().astimezone() - timedelta(days=days)
    seen: set[str] = set()
    with http.client(timeout=60) as c:
        for feed_url in FEEDS:
            url: str | None = feed_url
            pages = 0
            while url:
                if pages >= max_pages:
                    ctx.partial(f"PLACSP page cap ({max_pages}) reached before the "
                                f"{days}-day cutoff")
                    break
                opps, done, url = parse_page(_get_feed(c, url), cutoff)
                pages += 1
                for opp in opps:
                    if ctx.first_run and lifecycle(opp) == "closed":
                        seen.add(opp.source_id)  # newest emission says closed
                        continue
                    if opp.source_id not in seen:
                        seen.add(opp.source_id)
                        yield opp
                if done:
                    break
