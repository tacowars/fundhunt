"""Lexical ranking: score the corpus against a profile, with reasons.

Transparent weighted keyword + structural scorer: every point decomposes
into a human-readable reason, so a shortlist can be defended. Matching is
accent-folded substring search — profile terms are written unaccented
("pobreza energetica") and match accented text; a term may end mid-word to
act as a prefix ("energy communit").

Tiers are a sort key, never a filter:
  A (0)  at least one core hit
  B (1)  two distinct strong hits, or one strong hit plus a structural
         CPV / CNAE / funder match
  C (2)  everything else

The agent's judgment, not this score, decides what the user sees first;
this stage only has to get the right records into the agent's top-N.
"""

from __future__ import annotations

import functools
import json
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from .models import Opportunity, lifecycle
from .profile import Profile

TIER_A, TIER_B, TIER_C = 0, 1, 2
TIER_LABELS = {TIER_A: "A", TIER_B: "B", TIER_C: "C"}

INDIRECT_ROUTES = {"partner", "advise_clients"}


def fold(s: str) -> str:
    """Lowercase and strip accents: 'Pobreza Energética' -> 'pobreza energetica'."""
    nfkd = unicodedata.normalize("NFKD", s.lower())
    return "".join(ch for ch in nfkd if not unicodedata.combining(ch))


@functools.cache
def _cpv_labels() -> dict[str, str]:
    """Official CPV 2008 Spanish labels, keyed by 8-digit code without the
    check digit. Resolved at rank time, never written into stored records."""
    with open(Path(__file__).resolve().parent / "data" / "cpv_es.json", "rb") as f:
        return json.load(f)


def cpv_label(code: str) -> str | None:
    return _cpv_labels().get(code.split("-")[0])


@dataclass
class MatchResult:
    score: float = 0.0
    reasons: list[str] = field(default_factory=list)
    indirect: bool = False
    excluded: str | None = None
    hits: dict[str, set[str]] = field(default_factory=dict)
    structural: bool = False
    tier: int = TIER_C

    def add(self, pts: float, reason: str) -> None:
        self.score += pts
        self.reasons.append(f"{reason} {pts:+g}")

    def compute_tier(self) -> None:
        strong = len(self.hits.get("strong", ()))
        if self.hits.get("core"):
            self.tier = TIER_A
        elif strong >= 2 or (strong == 1 and self.structural):
            self.tier = TIER_B
        else:
            self.tier = TIER_C


class Ranker:
    def __init__(self, profile: Profile, today: date | None = None):
        self.p = profile
        self.today = today or datetime.now(timezone.utc).date()
        self.groups = {name: (g.weight, g.cap, [fold(t) for t in g.terms])
                       for name, g in profile.keywords.items()}
        self.funder_terms = [fold(t) for t in profile.funders.terms]
        self.wants_indirect = bool(INDIRECT_ROUTES & set(profile.looking_for.routes))

    # ------------------------------------------------------------------ #

    def _eligibility(self, opp: Opportunity, res: MatchResult) -> None:
        p = self.p
        if opp.source in p.sources.disabled:
            res.excluded = f"source {opp.source} disabled in profile"
            return
        if opp.kind.value not in p.looking_for.kinds:
            res.excluded = f"kind {opp.kind.value} not wanted"
            return
        state = lifecycle(opp, self.today)
        if state == "closed":
            res.excluded = "closed"
            return
        if (opp.deadline is not None and
                opp.deadline.date() < self.today + timedelta(days=p.looking_for.min_days_to_deadline)):
            res.excluded = f"deadline within {p.looking_for.min_days_to_deadline} days"
            return
        if state == "uncertain":
            res.reasons.append("lifecycle uncertain: no deadline or status — check the source")

        countries = p.eligibility.countries
        if countries and opp.country and opp.country not in countries:
            res.excluded = f"country {opp.country} not in {countries}"
            return

        want = p.eligibility.interreg_country
        if want and opp.source == "interreg":
            eligible = opp.raw.get("eligible_countries") or []
            if eligible and want not in eligible:
                res.excluded = f"{want} not eligible ({', '.join(eligible[:4])}…)"
                return

        # BDNS instrumental convocatorias are nominative grants to a named
        # beneficiary: there is no call and nothing to apply to, for anyone.
        if opp.source == "bdns" and \
                opp.raw.get("tipoConvocatoria") == "Concesión directa - instrumental":
            res.excluded = "BDNS instrumental (nominative grant, no call)"
            return

        tokens = p.eligibility.beneficiary_tokens
        if tokens and opp.source == "bdns":
            tipos = [fold(t.get("descripcion", ""))
                     for t in opp.raw.get("tiposBeneficiarios") or []]
            if tipos and not any(fold(tok) in t for tok in tokens for t in tipos):
                res.indirect = True
                res.reasons.append(f"indirect: beneficiaries are {tipos[0][:60]}")
        # EPAH and similar funds are for local authorities: indirect for a
        # company, the direct route for a public body
        if opp.indirect and p.who.role != "public_body":
            res.indirect = True
        if res.indirect and not self.wants_indirect:
            res.add(-2, "indirect and the profile takes no partner/advise routes")

    def _keywords(self, opp: Opportunity, res: MatchResult) -> None:
        title = fold(opp.title or "")
        # Negative terms never fire on classification catalog labels: broad
        # multi-sector calls list CNAE/CPV labels without being about them.
        body_neg = fold(" ".join(filter(None, [opp.summary, opp.funder])))
        labels = " ".join((c.label or (cpv_label(c.code) if c.scheme == "cpv" else None)
                           or c.code) for c in opp.classifications)
        body_pos = f"{body_neg} {fold(labels)}"
        for gname, (weight, cap, terms) in self.groups.items():
            body = body_neg if weight < 0 else body_pos
            pts = 0.0
            for term in terms:
                in_title = term in title
                if not in_title and term not in body:
                    continue
                bonus = 1 if (in_title and weight > 0) else 0
                pts += weight + bonus
                res.hits.setdefault(gname, set()).add(term)
                res.reasons.append(f"kw/{gname}: '{term}' ({'title' if in_title else 'body'}) "
                                   f"{weight + bonus:+g}")
            if cap and pts > cap:
                res.reasons.append(f"kw/{gname}: capped {pts:g} -> {cap:g}")
                pts = cap
            res.score += pts

    def _structural(self, opp: Opportunity, res: MatchResult) -> None:
        p = self.p
        cpvs = [c.code for c in opp.classifications if c.scheme == "cpv"]
        cnaes = [c.code for c in opp.classifications if c.scheme == "cnae"]
        if cpvs:
            if any(c.startswith(x) for x in p.cpv.include for c in cpvs):
                res.add(p.cpv.include_weight, f"cpv match {cpvs[:3]}")
                res.structural = True
            elif any(c.startswith(x) for x in p.cpv.exclude for c in cpvs):
                res.add(p.cpv.exclude_weight, f"cpv off-market {cpvs[:3]}")
        if cnaes:
            if any(c.startswith(x) for x in p.cnae.include for c in cnaes):
                res.add(p.cnae.include_weight, f"cnae match {cnaes[:3]}")
                res.structural = True
            elif any(c.startswith(x) for x in p.cnae.exclude for c in cnaes):
                res.add(p.cnae.exclude_weight, f"cnae off-market {cnaes[:3]}")
        if self.funder_terms and opp.funder:
            funder = fold(opp.funder)
            term = next((t for t in self.funder_terms if t in funder), None)
            if term:
                res.add(p.funders.weight, f"funder: '{term}'")
                res.structural = True

        b = p.budget
        if opp.kind.value == "tender" and opp.budget_value:
            if (b.tender_sweet_min is not None and b.tender_sweet_max is not None
                    and b.tender_sweet_min <= opp.budget_value <= b.tender_sweet_max):
                res.add(b.tender_sweet_weight, f"budget sweet spot €{opp.budget_value:,.0f}")
            elif b.tender_max is not None and opp.budget_value > b.tender_max:
                res.add(b.tender_over_max_weight, f"budget €{opp.budget_value:,.0f} over capacity")
        # grant budgets are call totals across beneficiaries: never scored

        # soft territory preference: regional records outside the profile's
        # regions lose a little, never get excluded (national calls carry none)
        if self.p.who.regions and opp.regions:
            codes = [r.split(" ")[0].upper() for r in opp.regions]
            if not any(c.startswith(w.upper()) or w.upper().startswith(c)
                       for c in codes for w in self.p.who.regions):
                res.add(-1, f"outside profile regions ({', '.join(codes[:3])})")

        boost = p.sources.boost.get(opp.source)
        if boost:
            res.add(boost, f"source {opp.source}")

    # ------------------------------------------------------------------ #

    def score(self, opp: Opportunity) -> MatchResult:
        res = MatchResult()
        self._eligibility(opp, res)
        if res.excluded:
            return res
        self._keywords(opp, res)
        self._structural(opp, res)
        res.compute_tier()
        return res


def run(store, profile: Profile, today: date | None = None) -> dict:
    """Score every not-yet-closed record and replace the profile's matches.

    Only records with a positive score or a keyword hit are kept: the rest
    is noise for this profile and would only bloat the matches table.
    """
    ranker = Ranker(profile, today)
    cutoff = ranker.today.isoformat()
    counts = {"considered": 0, "excluded": 0, "kept": 0, "tier_a": 0, "tier_b": 0}
    rows = []
    for opp in store.iter_opportunities(not_closed_before=cutoff):
        counts["considered"] += 1
        res = ranker.score(opp)
        if res.excluded:
            counts["excluded"] += 1
            continue
        if res.score <= 0 and not res.hits.get("core") and not res.hits.get("strong"):
            continue
        counts["kept"] += 1
        counts["tier_a"] += res.tier == TIER_A
        counts["tier_b"] += res.tier == TIER_B
        rows.append((opp.source, opp.source_id, res.score, res.tier, int(res.indirect),
                     json.dumps(res.reasons, ensure_ascii=False)))
    store.replace_matches(profile.name, rows)
    return counts


# ---- near-duplicate grouping (display + candidate lists) ------------- #

def dupkey(title: str | None, funder: str | None) -> tuple[str, str]:
    """Variant calls (one LEADER convocatoria per comarca, ordinals, typos)
    differ only in the title tail, so key on a normalized prefix."""
    t = re.sub(r"[^a-z0-9]+", " ", fold(title or "")).strip()[:100]
    return t, fold(funder or "")


def crossref(a: Opportunity, b: Opportunity) -> bool:
    """Same tender through two registries (TED reuses the PLACSP platform
    UUID): one record's id appears inside the other's URL. The length guard
    keeps short expediente numbers from accidental substring hits."""
    if a.source == b.source:
        return False
    return any(len(x.source_id) >= 12 and x.source_id in (y.url or "")
               for x, y in ((a, b), (b, a)))
