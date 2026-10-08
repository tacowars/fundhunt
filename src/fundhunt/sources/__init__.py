"""Source adapters. Each exposes `fetch(ctx) -> Iterator[Opportunity]`.

Registry order is also sync order (robust first, fragile last). Endpoint
quirks, dedup keys and failure modes for every source: docs/sources.md.

A missing record never closes an opportunity (conservative absence): only
a deadline or an explicit source status does, in models.lifecycle.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass, field

from ..models import Opportunity


@dataclass
class SyncContext:
    since_days: int              # incremental window for windowed sources
    first_run: bool              # no successful run yet: take the open stock
    known_ids: set[str] = field(default_factory=set)
    countries_iso2: list[str] = field(default_factory=lambda: ["ES"])
    partial_reason: str | None = None  # set by an adapter that hit a cap

    def partial(self, reason: str) -> None:
        self.partial_reason = reason


Fetch = Callable[[SyncContext], Iterator[Opportunity]]


def registry() -> dict[str, Fetch]:
    from . import bdns, epah, interreg, placsp, sedia, ted
    return {
        "ted": ted.fetch,
        "bdns": bdns.fetch,
        "placsp": placsp.fetch,
        "sedia": sedia.fetch_topics,
        "sedia_cascade": sedia.fetch_cascade,
        "interreg": interreg.fetch,
        "epah": epah.fetch,
    }


SOURCES = ["ted", "bdns", "placsp", "sedia", "sedia_cascade", "interreg", "epah"]

DESCRIPTIONS = {
    "ted": "TED — EU tenders published by buyers in your countries",
    "bdns": "BDNS / SNPSAP — Spanish public grants and aid (incl. CDTI)",
    "placsp": "PLACSP — Spanish public procurement (national + aggregated platforms)",
    "sedia": "EU Funding & Tenders portal — Horizon Europe, LIFE, Digital Europe… topics",
    "sedia_cascade": "EU Funding & Tenders — cascade / FSTP calls run by EU projects",
    "interreg": "Interreg — calls of all Interreg programmes (via interreg.eu)",
    "epah": "EPAH — Energy Poverty Advisory Hub calls for local authorities",
}
