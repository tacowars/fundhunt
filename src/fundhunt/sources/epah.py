"""EPAH — Energy Poverty Advisory Hub newsroom (HTML scrape).

EPAH technical-assistance calls fund local authorities, so every record is
flagged `indirect`: for a company the play is advising or partnering with
a municipality; for a public body it is a direct application. Only news
items whose title suggests a call are kept. Annual cycle: weekly at most.
"""

from __future__ import annotations

import re
from collections.abc import Iterator

from .. import http
from ..models import Kind, Opportunity
from . import SyncContext

NEWS_URL = "https://energy-poverty.ec.europa.eu/newsroom/news"
BASE = "https://energy-poverty.ec.europa.eu"

CALL_HINT = re.compile(r"\bcall\b|technical assistance|applications?\s+open", re.I)


def parse(html: str) -> Iterator[Opportunity]:
    text = re.sub(r"<script.*?</script>", "", html, flags=re.S)
    items = re.findall(r'href="(/newsroom/news/[^"]+)"[^>]*>\s*([^<]{10,200})', text)
    seen: set[str] = set()
    for href, title in items:
        title = title.strip()
        if href in seen or href.endswith("/submission-form"):
            continue
        seen.add(href)
        if not CALL_HINT.search(title):
            continue
        yield Opportunity(
            source="epah",
            source_id=href.rstrip("/").rsplit("/", 1)[-1],
            kind=Kind.GRANT,
            indirect=True,
            title=title[:500],
            funder="EPAH / European Commission",
            url=BASE + href,
            language="eng",
        )


def fetch(ctx: SyncContext) -> Iterator[Opportunity]:
    with http.client() as c:
        resp = http.request(c, "GET", NEWS_URL)
    yield from parse(resp.text)
