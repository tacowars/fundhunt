"""Normalized opportunity model and lifecycle.

- Grants (subvenciones, ayudas) and tenders (licitaciones) are distinct
  kinds that share one envelope, so ranking runs over both.
- `indirect` marks opportunities the applicant cannot pursue directly
  (e.g. EPAH funds municipalities) but can reach as partner or adviser.
- Classifications stay source-native (CPV vs CNAE vs themes): CPV and CNAE
  are not interchangeable.
- `deadline` is the single "next actionable" datetime; every raw deadline
  string survives in `deadlines_raw`, the source payload subset in `raw`.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


class Kind(str, Enum):
    GRANT = "grant"
    TENDER = "tender"


class Classification(BaseModel):
    scheme: str  # cpv | cnae | nuts | theme | programme
    code: str
    label: str | None = None


class DocumentRef(BaseModel):
    """A source-declared document attachment (PLACSP pliegos, SEDIA call fiches)."""

    role: str  # legal | technical | additional | call
    name: str | None = None
    uri: str


class Opportunity(BaseModel):
    source: str  # ted | bdns | placsp | sedia | sedia_cascade | interreg | epah
    source_id: str  # dedup key within the source (docs/sources.md)
    kind: Kind
    indirect: bool = False

    title: str
    summary: str | None = None
    funder: str | None = None  # buyer / órgano convocante / programme
    country: str | None = None  # ISO-3166 alpha-2; None = EU-wide
    regions: list[str] = Field(default_factory=list)  # NUTS codes
    classifications: list[Classification] = Field(default_factory=list)

    budget_value: float | None = None
    budget_currency: str | None = None

    status: str | None = None  # source-native status, verbatim
    open_date: date | None = None
    deadline: datetime | None = None
    deadlines_raw: list[str] = Field(default_factory=list)

    url: str | None = None
    language: str | None = None
    documents: list[DocumentRef] = Field(default_factory=list)
    raw: dict = Field(default_factory=dict)

    @property
    def ref(self) -> str:
        """Stable cross-command identifier: '<source>:<source_id>'."""
        return f"{self.source}:{self.source_id}"

    def content_hash(self) -> str:
        """Hash of the normalized fields; `raw` is excluded (noisy re-orderings)."""
        payload = self.model_dump(mode="json", exclude={"raw"})
        canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(canonical.encode()).hexdigest()


# Source statuses that mean "no longer open" when no deadline is known.
CLOSED_STATUSES = {"cerrado", "closed", "evaluación", "adjudicada", "resuelta",
                   "anulada", "veat"}
FORTHCOMING_STATUSES = {"forthcoming", "anuncio previo"}


def lifecycle(opp: Opportunity, today: date | None = None) -> str:
    """lifecycle-v1: open | forthcoming | closed | uncertain.

    A missing deadline never means open: without one, only an explicit
    source status decides, otherwise the record is `uncertain`.
    """
    today = today or datetime.now(timezone.utc).date()
    status = (opp.status or "").lower()
    if opp.deadline is not None and opp.deadline.date() < today:
        return "closed"
    if opp.open_date is not None and opp.open_date > today:
        return "forthcoming"
    if opp.deadline is not None:
        return "open"
    if status in CLOSED_STATUSES or status.startswith("can-"):
        return "closed"
    if status in FORTHCOMING_STATUSES:
        return "forthcoming"
    if status in {"open", "abierto", "en plazo"}:
        return "open"
    return "uncertain"
