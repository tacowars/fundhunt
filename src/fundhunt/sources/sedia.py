"""EU Funding & Tenders portal (SEDIA search API): grant topics and
cascade / FSTP calls.

Fragile undocumented endpoint: fixed shared `apiKey=SEDIA`, multipart-form
requests, every metadata value is a list of strings. Both feeds are
full-state polls (open + forthcoming) every run.

Why a date cursor and not pageNumber: the API re-executes the query per
page and its replicas disagree on ordering, so a paged walk re-serves and
loses documents under every sort field. The `es_SortDate` range cursor is
order-independent: each request asks for everything strictly after the
watermark; only complete date tie-blocks advance it, and the boundary
block is re-fetched whole by the next request. pageSize is capped at 100.

Dedup keys: topic identifier (grants); the competitive-call portal id for
cascade calls (one topic can host many). The index holds duplicate
documents per record, so pick a deterministic winner.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import date, datetime, timezone

from .. import http
from ..models import DocumentRef, Kind, Opportunity
from . import SyncContext

SEARCH_URL = "https://api.tech.ec.europa.eu/search-api/prod/rest/search"
TOPIC_URL = "https://ec.europa.eu/info/funding-tenders/opportunities/portal/screen/opportunities/topic-details/{}"
PAGE_SIZE = 100
MAX_REQUESTS = 200
SORT = {"field": "es_SortDate", "order": "ASC"}

STATUS_LABELS = {"31094501": "forthcoming", "31094502": "open", "31094503": "closed"}


def _one(meta: dict, key: str) -> str | None:
    vals = meta.get(key)
    return vals[0] if isinstance(vals, list) and vals else None


def _parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("+0000", "+00:00"))
    except ValueError:
        return None


def search(must: list[dict], ctx: SyncContext | None = None) -> Iterator[dict]:
    """Every result for the query, via the es_SortDate cursor."""
    after: str | None = None
    with http.client(timeout=60) as c:
        for _ in range(MAX_REQUESTS):
            clauses = list(must)
            if after:
                clauses.append({"range": {"es_SortDate": {"gt": after}}})
            resp = http.request(
                c, "POST", SEARCH_URL,
                params={"apiKey": "SEDIA", "text": "***",
                        "pageSize": str(PAGE_SIZE), "pageNumber": "1"},
                files={
                    "query": (None, json.dumps({"bool": {"must": clauses}}), "application/json"),
                    "languages": (None, json.dumps(["en"]), "application/json"),
                    "sort": (None, json.dumps(SORT), "application/json"),
                })
            results = resp.json().get("results") or []
            if len(results) < PAGE_SIZE:
                yield from results
                return
            boundary = _one(results[-1].get("metadata", {}), "es_SortDate")
            complete = [r for r in results
                        if _one(r.get("metadata", {}), "es_SortDate") != boundary]
            if not complete:
                # a tie-block >= page size cannot advance the cursor
                yield from results
                if ctx:
                    ctx.partial("SEDIA cursor stuck on a tie-block >= page size")
                return
            yield from complete
            after = _one(complete[-1].get("metadata", {}), "es_SortDate")
    if ctx:
        ctx.partial(f"SEDIA request cap ({MAX_REQUESTS}) reached")


def topic_from_result(r: dict) -> Opportunity | None:
    m = r.get("metadata", {})
    identifier = _one(m, "identifier")
    if not identifier:
        return None
    deadlines = m.get("deadlineDate") or []
    parsed = [d for d in (_parse_dt(x) for x in deadlines) if d]
    future = [d for d in parsed if d.date() >= date.today()]
    start = _parse_dt(_one(m, "startDate"))
    status_code = _one(m, "status")
    url = r.get("url") or TOPIC_URL.format(identifier.lower())
    return Opportunity(
        source="sedia",
        source_id=identifier,
        kind=Kind.GRANT,
        title=_one(m, "title") or identifier,
        summary=r.get("summary") or None,
        funder=" · ".join(filter(None, [_one(m, "frameworkProgramme"),
                                        _one(m, "callIdentifier")])) or None,
        status=STATUS_LABELS.get(status_code or "", status_code),
        open_date=start.date() if start else None,
        deadline=min(future) if future else (max(parsed) if parsed else None),
        deadlines_raw=deadlines,
        url=url,
        language="eng",
        documents=[DocumentRef(role="call", name="topic page", uri=url)],
        raw={"metadata_subset": {k: m.get(k) for k in (
            "identifier", "callIdentifier", "status", "deadlineModel",
            "frameworkProgramme", "programmePeriod", "typesOfAction")}},
    )


def fetch_topics(ctx: SyncContext) -> Iterator[Opportunity]:
    must = [{"terms": {"type": ["1", "2"]}},
            {"terms": {"status": ["31094501", "31094502"]}}]
    best: dict[str, Opportunity] = {}
    for r in search(must, ctx):
        opp = topic_from_result(r)
        if opp and (opp.source_id not in best or (r.get("reference") or "") < best[opp.source_id].raw.get("_ref", "~")):
            opp.raw["_ref"] = r.get("reference") or ""
            best[opp.source_id] = opp
    for k in sorted(best):
        best[k].raw.pop("_ref", None)
        yield best[k]


def cascade_key(r: dict) -> tuple[str, tuple[int, str]]:
    m = r.get("metadata", {})
    url = r.get("url") or ""
    call_id = url.rstrip("/").rsplit("/", 1)[-1] if "competitive-calls" in url else None
    title = _one(m, "callTitle") or _one(m, "title") or "FSTP call"
    key = call_id or f"{_one(m, 'projectAcronym')}:{title[:80]}"
    return key, (0 if call_id else 1, r.get("reference") or "")


def cascade_from_result(key: str, r: dict) -> Opportunity | None:
    m = r.get("metadata", {})
    deadlines = m.get("deadlineDate") or []
    parsed = [d for d in (_parse_dt(x) for x in deadlines) if d]
    future = [d for d in parsed if d >= datetime.now(timezone.utc)]
    if not future:
        return None  # every cutoff already passed
    project = _one(m, "projectAcronym")
    title = _one(m, "callTitle") or _one(m, "title") or "FSTP call"
    budget = _one(m, "budget")
    try:
        budget_value = float(budget) if budget else None
    except ValueError:
        budget_value = None
    return Opportunity(
        source="sedia_cascade",
        source_id=key,
        kind=Kind.GRANT,
        title=f"[{project}] {title}" if project else title,
        summary=_one(m, "description"),
        funder=_one(m, "projectName") or project,
        budget_value=budget_value,
        budget_currency="EUR" if budget_value is not None else None,
        status="open",
        deadline=min(future),
        deadlines_raw=deadlines,
        url=r.get("url"),
        language="eng",
        raw={"metadata_subset": {k: m.get(k) for k in (
            "identifier", "projectAcronym", "projectName", "budget", "startDate")}},
    )


def fetch_cascade(ctx: SyncContext) -> Iterator[Opportunity]:
    # `status` is stale on type-8 records: filter by future deadline instead
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT00:00:00.000+0000")
    must = [{"terms": {"type": ["8"]}},
            {"range": {"deadlineDate": {"gte": now_iso}}}]
    candidates: dict[str, tuple[tuple[int, str], dict]] = {}
    for r in search(must, ctx):
        key, rank = cascade_key(r)
        if key not in candidates or rank < candidates[key][0]:
            candidates[key] = (rank, r)
    for key, (_, r) in sorted(candidates.items()):
        opp = cascade_from_result(key, r)
        if opp:
            yield opp
