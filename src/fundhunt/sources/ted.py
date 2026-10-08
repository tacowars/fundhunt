"""TED v3 notice search (EU tenders).

Dedup key: procedure-identifier when present, else publication-number
(pre-2023 notices lack the procedure id). Corrigenda republish under new
publication numbers with the same procedure id, so they land as revisions.

The sort MUST be a unique total order: with the day-granular
publication-date sort, ITERATION pagination returned a slightly different
subset on every pass (~1% dropped/shifted). publication-number is unique.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from datetime import date, datetime, timedelta

from .. import http
from ..models import Classification, Kind, Opportunity
from . import SyncContext

SEARCH_URL = "https://api.ted.europa.eu/v3/notices/search"
FAILOVER_URL = "https://tedweb.api.ted.europa.eu/v3/notices/search"

FIELDS = [
    "publication-number", "publication-date", "notice-title", "buyer-name",
    "buyer-country", "classification-cpv", "notice-type", "contract-nature",
    "procedure-identifier", "deadline-receipt-tender-date-lot",
]
# Only probe-verified field names: TED rejects the whole query (HTTP 400)
# on an unknown field, so add new ones after checking docs/sources.md.

PAGE_SIZE = 250     # TED's max page size
PAGE_DELAY_S = 0.5  # burst runs have drawn nginx 429s

ISO2_TO_3 = {
    "AT": "AUT", "BE": "BEL", "BG": "BGR", "CY": "CYP", "CZ": "CZE", "DE": "DEU",
    "DK": "DNK", "EE": "EST", "ES": "ESP", "FI": "FIN", "FR": "FRA", "GR": "GRC",
    "HR": "HRV", "HU": "HUN", "IE": "IRL", "IT": "ITA", "LT": "LTU", "LU": "LUX",
    "LV": "LVA", "MT": "MLT", "NL": "NLD", "PL": "POL", "PT": "PRT", "RO": "ROU",
    "SE": "SWE", "SI": "SVN", "SK": "SVK", "NO": "NOR", "IS": "ISL", "LI": "LIE",
    "CH": "CHE",
}
ISO3_TO_2 = {v: k for k, v in ISO2_TO_3.items()}


def _pick_lang(multilingual: dict | None) -> tuple[str | None, str | None]:
    """(text, lang) preferring Spanish, then English, then anything."""
    if not multilingual:
        return None, None
    for lang in ("spa", "eng", *multilingual):
        val = multilingual.get(lang)
        if val:
            if isinstance(val, list):
                val = val[0]
            return val, lang
    return None, None


def _listify(v) -> list:
    if v is None:
        return []
    return v if isinstance(v, list) else [v]


def _next_deadline(notice: dict) -> tuple[datetime | None, list[str]]:
    raws = _listify(notice.get("deadline-receipt-tender-date-lot"))
    parsed = []
    for r in raws:
        try:
            parsed.append(datetime.fromisoformat(r))
        except ValueError:
            pass
    future = [d for d in parsed if d.date() >= date.today()]
    nxt = min(future) if future else (max(parsed) if parsed else None)
    return nxt, raws


def normalize(notice: dict) -> Opportunity:
    title, lang = _pick_lang(notice.get("notice-title"))
    buyer, _ = _pick_lang(notice.get("buyer-name"))
    deadline, deadlines_raw = _next_deadline(notice)
    pub_no = notice["publication-number"]
    html_links = (notice.get("links") or {}).get("html") or {}
    url = html_links.get("SPA") or html_links.get("ENG") or next(iter(html_links.values()), None)
    countries = _listify(notice.get("buyer-country"))
    return Opportunity(
        source="ted",
        source_id=notice.get("procedure-identifier") or pub_no,
        kind=Kind.TENDER,
        title=title or f"TED notice {pub_no}",
        funder=buyer,
        country=ISO3_TO_2.get(countries[0]) if countries else None,
        classifications=[Classification(scheme="cpv", code=c)
                         for c in _listify(notice.get("classification-cpv"))],
        status=notice.get("notice-type"),
        deadline=deadline,
        deadlines_raw=deadlines_raw,
        url=url,
        language=lang,
        raw={k: notice.get(k) for k in ("publication-number", "publication-date",
                                        "notice-type", "contract-nature", "buyer-country")},
    )


def _pub_key(pub_no: str) -> tuple[int, int]:
    """Publication numbers are '<seq>-<year>' (seq resets yearly)."""
    try:
        seq, year = pub_no.split("-", 1)
        return int(year), int(seq)
    except ValueError:
        return (0, 0)


def _iter_search(query: str) -> Iterator[Opportunity]:
    payload = {"query": query, "fields": FIELDS, "limit": PAGE_SIZE,
               "paginationMode": "ITERATION"}
    # A procedure can appear as several notices (original + corrigenda):
    # buffer and keep the highest publication number per procedure.
    best: dict[str, Opportunity] = {}
    with http.client() as c:
        token: str | None = None
        while True:
            body = dict(payload, **({"iterationNextToken": token} if token else {}))
            try:
                resp = http.request(c, "POST", SEARCH_URL, json=body)
            except Exception:
                resp = http.request(c, "POST", FAILOVER_URL, json=body)
            data = resp.json()
            notices = data.get("notices", [])
            for n in notices:
                opp = normalize(n)
                cur = best.get(opp.source_id)
                if cur is None or _pub_key(n["publication-number"]) > _pub_key(
                        cur.raw["publication-number"]):
                    best[opp.source_id] = opp
            token = data.get("iterationNextToken")
            if not token or not notices:
                break
            time.sleep(PAGE_DELAY_S)
    yield from (best[k] for k in sorted(best))


def fetch(ctx: SyncContext) -> Iterator[Opportunity]:
    iso3 = " ".join(ISO2_TO_3[c] for c in ctx.countries_iso2 if c in ISO2_TO_3) or "ESP"
    if ctx.first_run:
        # open stock: every notice whose submission deadline (any lot) is ahead
        today = date.today().strftime("%Y%m%d")
        query = (f"(buyer-country IN ({iso3})) AND (deadline-receipt-tender-date-lot >= {today}) "
                 "SORT BY publication-number DESC")
    else:
        since = (date.today() - timedelta(days=ctx.since_days)).strftime("%Y%m%d")
        query = (f"(buyer-country IN ({iso3})) AND (publication-date >= {since}) "
                 "SORT BY publication-number DESC")
    yield from _iter_search(query)
