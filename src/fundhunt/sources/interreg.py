"""Interreg — interreg.eu's public Algolia index (fed by keep.eu).

Fragile: these are the site's public frontend search credentials, which
can rotate without notice. When a sync fails with HTTP 403, open
https://interreg.eu/calls-for-projects/ in a browser, read the new
application id / search key from the Algolia request in the network tab,
and update them here (docs/sources.md, Interreg).

Full-state poll of open + forthcoming calls across all programmes; the
eligible-country list travels in `raw` so ranking can filter per profile.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime

from .. import http
from ..models import Classification, Kind, Opportunity
from . import SyncContext

ALGOLIA_URL = "https://2e032drcns-dsn.algolia.net/1/indexes/*/queries"
ALGOLIA_PARAMS = {
    "x-algolia-api-key": "afcd3bc5094a8f54ceb9cb221c74dbc7",
    "x-algolia-application-id": "2E032DRCNS",
}
INDEX = "prod_en-us_content"
HITS = 500


def _parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def normalize(h: dict) -> Opportunity:
    programmes = h.get("associatedProgrammes") or []
    deadline = _parse_dt(h.get("callDeadlineDate"))
    opened = _parse_dt(h.get("callOpenDate"))
    return Opportunity(
        source="interreg",
        source_id=str(h.get("objectID") or h.get("pageId")),
        kind=Kind.GRANT,
        title=h.get("title") or "Interreg call",
        summary=h.get("description") or h.get("teaser") or None,
        funder=", ".join(programmes) or "Interreg",
        regions=h.get("callEligibleCountryNuts") or [],
        classifications=[Classification(scheme="theme", code=t)
                         for t in h.get("callThemes") or h.get("themes") or []],
        status=(h.get("callStatus") or "").lower() or None,
        open_date=opened.date() if opened else None,
        deadline=deadline,
        deadlines_raw=[s for s in (h.get("callDeadlineDate"),) if s],
        url=h.get("callExternalUrl") or h.get("contentUrl"),
        language="eng",
        raw={"eligible_countries": h.get("callEligibleCountryNames"),
             "target_audience": h.get("targetAudience")},
    )


def fetch(ctx: SyncContext) -> Iterator[Opportunity]:
    body = {"requests": [{
        "indexName": INDEX,
        "filters": "contentType:callForProjectsPage AND "
                   "(callStatus:Open OR callStatus:Forthcoming)",
        "hitsPerPage": HITS,
        "query": "",
    }]}
    with http.client() as c:
        resp = http.request(c, "POST", ALGOLIA_URL, params=ALGOLIA_PARAMS, json=body)
        result = resp.json()["results"][0]
    hits = result.get("hits", [])
    if result.get("nbHits", 0) > len(hits):
        ctx.partial(f"Interreg returned {len(hits)} of {result['nbHits']} hits")
    for h in hits:
        yield normalize(h)
