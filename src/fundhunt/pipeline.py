"""The steps between the corpus and the report: sync, candidates, verdicts,
decisions. The CLI is a thin JSON wrapper around these functions."""

from __future__ import annotations

import json
import math
import re
import sys
import traceback
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from . import profile as profile_mod
from .models import Opportunity, lifecycle
from .profile import Profile
from .rank import TIER_LABELS, crossref, dupkey
from .sources import SOURCES, SyncContext, registry
from .store import Store, split_ref

# Sources whose content changes slowly enough that a weekly poll is plenty.
WEEKLY = {"epah"}
MAX_WINDOW_DAYS = 30


# ---------------------------------------------------------------- sync -- #

def _countries(profiles: list[Profile]) -> list[str]:
    out: list[str] = []
    for p in profiles:
        for c in p.eligibility.countries or [p.who.country]:
            if c not in out:
                out.append(c)
    return out or ["ES"]


SOURCE_KIND = {"ted": "tender", "placsp": "tender"}  # everything else is a grant source


def _wanted_sources(profiles: list[Profile]) -> set[str]:
    """Sources at least one profile can use (all of them when there are none yet)."""
    if not profiles:
        return set(SOURCES)
    return {s for s in SOURCES for p in profiles
            if s not in p.sources.disabled
            and SOURCE_KIND.get(s, "grant") in p.looking_for.kinds}


def sync(store: Store, only: list[str] | None = None, force: bool = False,
         log=lambda msg: print(msg, file=sys.stderr, flush=True)) -> dict:
    profiles = []
    for path in profile_mod.list_profiles():
        try:
            profiles.append(profile_mod.load(str(path)))
        except Exception:
            pass  # a broken profile must not stop acquisition; `profile check` reports it
    # the shipped examples only steer acquisition until the user has a profile
    profiles = [p for p in profiles if not p.name.startswith("example-")] or profiles
    countries = _countries(profiles)
    fetchers = registry()
    wanted = _wanted_sources(profiles)
    now = datetime.now(timezone.utc)
    results = {}
    for name in only or SOURCES:
        if name not in fetchers:
            results[name] = {"ok": False, "error": f"unknown source {name!r}"}
            continue
        if not only and name not in wanted:
            results[name] = {"ok": True, "skipped": "no profile uses this source"}
            continue
        last = store.last_success(name)
        if last and name in WEEKLY and not force and now - last < timedelta(days=6):
            results[name] = {"ok": True, "skipped": "polled within the last 6 days"}
            continue
        days = MAX_WINDOW_DAYS if last is None else min(
            MAX_WINDOW_DAYS, max(2, math.ceil((now - last).total_seconds() / 86400) + 1))
        ctx = SyncContext(since_days=days, first_run=last is None,
                          known_ids=store.existing_ids(name), countries_iso2=countries)
        log(f"[{name}] syncing ({'first run: open stock' if ctx.first_run else f'last {days} days'})")
        run_id = store.start_run(name)
        counts = {"new": 0, "updated": 0, "unchanged": 0}
        try:
            for i, opp in enumerate(fetchers[name](ctx), 1):
                counts[store.upsert(opp)] += 1
                # commit per record: the adapter fetches between yields, and an
                # open write transaction would lock out a concurrent rank/verdict
                store.commit()
                if i % 250 == 0:
                    log(f"[{name}] {i} records…")
            coverage = "partial" if ctx.partial_reason else "complete"
            store.finish_run(run_id, ok=True, counts=counts, coverage=coverage,
                             error=ctx.partial_reason)
            results[name] = {"ok": True, **counts, "coverage": coverage,
                             **({"note": ctx.partial_reason} if ctx.partial_reason else {})}
        except Exception as exc:
            store.commit()  # keep whatever arrived before the failure
            err = f"{type(exc).__name__}: {exc}"
            store.finish_run(run_id, ok=False, counts=counts, error=err)
            results[name] = {"ok": False, **counts, "error": err[:500]}
            log(f"[{name}] FAILED: {err}\n{traceback.format_exc(limit=3)}")
        log(f"[{name}] {results[name]}")
    return results


# ---------------------------------------------------------- candidates -- #

def _days_left(opp: Opportunity) -> int | None:
    if opp.deadline is None:
        return None
    return (opp.deadline.date() - datetime.now(timezone.utc).date()).days


def _classifications(opp: Opportunity) -> list[str]:
    from .rank import cpv_label
    out = []
    for c in opp.classifications[:8]:
        label = c.label or (cpv_label(c.code) if c.scheme == "cpv" else None)
        out.append(f"{c.scheme}:{c.code}" + (f" {label[:70]}" if label else ""))
    return out


def card(row, opp: Opportunity) -> dict:
    """Compact, self-explanatory record for the agent and the report."""
    return {
        "ref": opp.ref,
        "kind": opp.kind.value,
        "source": opp.source,
        "title": opp.title,
        "funder": opp.funder,
        "country": opp.country,
        "regions": opp.regions[:6],
        "lifecycle": lifecycle(opp),
        "open_date": opp.open_date.isoformat() if opp.open_date else None,
        "deadline": opp.deadline.isoformat() if opp.deadline else None,
        "days_left": _days_left(opp),
        "budget": (f"{opp.budget_value:,.0f} {opp.budget_currency or ''}".strip()
                   if opp.budget_value else None),
        "budget_note": ("call total across all beneficiaries, not a ticket size"
                        if opp.kind.value == "grant" and opp.budget_value else None),
        "classifications": _classifications(opp),
        "summary": (opp.summary or "")[:1500] or None,
        "beneficiaries": [t.get("descripcion") for t in opp.raw.get("tiposBeneficiarios") or []][:6] or None,
        "eligible_countries": opp.raw.get("eligible_countries"),
        "indirect": bool(row["match_indirect"]) or opp.indirect,
        "url": opp.url,
        "documents_available": len(opp.documents) or None,
        "lexical": {"tier": TIER_LABELS[row["tier"]], "score": row["score"],
                    "reasons": json.loads(row["reasons"])[:12]},
    }


_ID_TOKEN = re.compile(r"[0-9a-fA-F-]{12,}|[A-Za-z0-9_/.-]{12,}")


def _xref_tokens(opp: Opportunity) -> set[str]:
    """Identifiers that let one registry's record find its twin in another
    (TED reuses the PLACSP platform UUID): the id itself plus long id-like
    tokens in the URL. Short ids (expediente numbers) are ignored."""
    toks = {opp.source_id} if len(opp.source_id) >= 12 else set()
    if opp.url:
        toks |= {t for t in _ID_TOKEN.findall(opp.url.split("?", 1)[-1]) if any(ch.isdigit() for ch in t)}
    return toks


def grouped(store: Store, prof: Profile) -> list[dict]:
    """Ranked rows collapsed into near-duplicate groups (best row first):
    same normalized title+funder, or the same tender seen in two registries."""
    groups: list[dict] = []
    by_key: dict[tuple[str, str], dict] = {}
    by_token: dict[str, dict] = {}
    for row in store.ranked(prof.name):
        opp = Opportunity.model_validate_json(row["normalized"])
        key = dupkey(opp.title, opp.funder)
        toks = _xref_tokens(opp) if opp.kind.value == "tender" else set()
        g = by_key.get(key)
        if g is None:
            g = next((by_token[t] for t in toks if t in by_token
                      and crossref(by_token[t]["opp"], opp)), None)
        if g is None:
            g = {"row": row, "opp": opp, "variants": []}
            groups.append(g)
            by_key[key] = g
        else:
            g["variants"].append(opp.ref)
        for t in toks:
            by_token.setdefault(t, g)
    return groups


def _verdict_state(row, content_hash: str, profile_hash: str) -> str:
    if row["verdict"] is None:
        return "missing"
    if row["v_content_hash"] != content_hash:
        return "stale-record"
    if row["v_profile_hash"] != profile_hash:
        return "stale-profile"
    return "current"


def candidates(store: Store, prof: Profile, top: int | None = None,
               include_judged: bool = False) -> dict:
    top = top or prof.report.top
    phash = prof.hash()
    out, judged = [], 0
    for g in grouped(store, prof)[: top]:
        row, opp = g["row"], g["opp"]
        if row["decision"] == "dismiss":
            continue
        state = _verdict_state(row, row["content_hash"], phash)
        if state == "current" and not include_judged:
            judged += 1
            continue
        c = card(row, opp)
        c["verdict_state"] = state
        if g["variants"]:
            c["near_duplicates"] = g["variants"][:10]
        out.append(c)
    return {
        "profile": prof.brief(),
        "profile_hash": phash,
        "deep_read_budget": prof.report.deep_read,
        "already_judged_and_current": judged,
        "to_judge": len(out),
        "candidates": out,
        "verdict_format": VERDICT_HELP,
    }


# ------------------------------------------------------------ verdicts -- #

VERDICT_HELP = (
    "Pipe a JSON list to `fundhunt verdict --profile <name>`; one object per ref: "
    "{ref, verdict: strong|plausible|reject, route: apply|bid|partner|advise_clients|monitor, "
    "summary (one sentence, profile language), rationale, constraint_applied (required for "
    "reject: the rule that rules it out), fit (1-5, only after a deep read), key_constraints "
    "[...], next_step, deep_read (bool), judged_by (agent/model name)}"
)


class VerdictIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ref: str
    verdict: Literal["strong", "plausible", "reject"]
    route: Literal["apply", "bid", "partner", "advise_clients", "monitor"] | None = None
    summary: str = Field(min_length=10)
    rationale: str = Field(min_length=10)
    constraint_applied: str | None = None
    fit: int | None = Field(default=None, ge=1, le=5)
    key_constraints: list[str] = Field(default_factory=list)
    next_step: str | None = None
    deep_read: bool = False
    judged_by: str | None = None

    @model_validator(mode="after")
    def _reject_needs_constraint(self):
        if self.verdict == "reject" and not self.constraint_applied:
            raise ValueError("a reject verdict must name constraint_applied")
        if self.verdict != "reject" and not self.route:
            raise ValueError("strong/plausible verdicts must name a route")
        return self


def save_verdicts(store: Store, prof: Profile, payload) -> dict:
    items = payload.get("verdicts", payload) if isinstance(payload, dict) else payload
    if isinstance(items, dict):
        items = [items]
    phash = prof.hash()
    saved, errors = 0, []
    for i, raw in enumerate(items):
        try:
            v = VerdictIn.model_validate(raw)
            source, source_id = split_ref(v.ref)
            chash = store.content_hash(source, source_id)
            if chash is None:
                raise ValueError(f"unknown ref {v.ref}")
            store.save_verdict(prof.name, v.model_dump(), chash, phash)
            saved += 1
        except (ValidationError, ValueError) as exc:
            errors.append({"index": i, "ref": raw.get("ref") if isinstance(raw, dict) else None,
                           "error": str(exc).splitlines()[0:3]})
    store.commit()
    return {"saved": saved, "errors": errors}


# ----------------------------------------------------------- decisions -- #

DECISIONS_MARKER = "FUNDHUNT-DECISIONS"


def decision_files(prof: Profile, extra: list[Path]) -> list[Path]:
    """Explicit paths plus exported files found in data/inbox and ~/Downloads."""
    from .settings import inbox_dir
    pattern = f"fundhunt-decisions-{prof.name}*.json"
    found = list(extra)
    for d in (inbox_dir(), Path.home() / "Downloads"):
        if d.is_dir():
            found += sorted(d.glob(pattern))
    return found


def parse_decisions(text: str) -> list[dict]:
    """Decision payloads from an exported file or a block pasted into chat.

    Accepts plain JSON, or text holding one or more blocks that start with
    the FUNDHUNT-DECISIONS marker line (the report's "copy for agent"
    button); chat apps may wrap the block in code fences or extra prose.
    """
    text = text.strip()
    if text.startswith("{"):
        return [json.loads(text)]
    payloads, dec = [], json.JSONDecoder()
    for chunk in text.split(DECISIONS_MARKER)[1:]:
        brace = chunk.find("{")
        if brace >= 0:
            payloads.append(dec.raw_decode(chunk[brace:])[0])
    if not payloads:
        raise ValueError(f"no {DECISIONS_MARKER} block or JSON object found")
    return payloads


def import_decisions(store: Store, prof: Profile, payloads: list[dict],
                     sources: list[str] | None = None) -> dict:
    """Idempotent: a mark is (profile, ref) → latest decided_at wins.

    A cleared mark that still carries a note is kept as decision 'note'."""
    imported, skipped = 0, 0
    for data in payloads:
        if data.get("profile") != prof.name:
            skipped += 1
            continue
        for d in data.get("decisions", []):
            decision = d.get("decision")
            if decision not in {"pursue", "maybe", "dismiss", None}:
                continue
            source, source_id = split_ref(d["ref"])
            cur = store.conn.execute(
                "SELECT decided_at FROM decisions WHERE profile=? AND source=? AND source_id=?",
                (prof.name, source, source_id)).fetchone()
            if cur and cur["decided_at"] >= (d.get("decided_at") or ""):
                continue
            if decision is None and not d.get("note"):
                store.conn.execute(
                    "DELETE FROM decisions WHERE profile=? AND source=? AND source_id=?",
                    (prof.name, source, source_id))
            else:
                store.save_decision(prof.name, d["ref"], decision or "note", d.get("note"),
                                    d.get("decided_at"))
            imported += 1
    store.commit()
    counts = {r["decision"]: r["n"] for r in store.conn.execute(
        "SELECT decision, COUNT(*) n FROM decisions WHERE profile=? GROUP BY decision",
        (prof.name,))}
    return {"sources": sources or [], "applied": imported,
            "skipped_other_profiles": skipped, "totals": counts}


def today() -> date:
    return datetime.now(timezone.utc).date()
