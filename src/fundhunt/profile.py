"""Profile: who the applicant is and what to look for (profiles/<name>.yaml).

The schema is documented field by field in profiles/README.md; the
example-*.yaml files are runnable starting points. `fundhunt profile check`
validates a file and prints what it understood.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .settings import profiles_dir

Role = Literal["company", "consultancy", "public_body", "ngo", "research", "individual"]
Route = Literal["apply", "bid", "partner", "advise_clients", "monitor"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Who(_Strict):
    role: Role
    summary: str = Field(min_length=20, description="Plain-language description used for judging")
    country: str = "ES"
    regions: list[str] = Field(default_factory=list)  # NUTS prefixes, e.g. ES51
    size: Literal["micro", "small", "medium", "large", "n/a"] = "n/a"
    legal_form: str | None = None


class LookingFor(_Strict):
    kinds: list[Literal["grant", "tender"]] = Field(default_factory=lambda: ["grant", "tender"])
    routes: list[Route] = Field(default_factory=lambda: ["apply", "bid"])
    notes: str | None = None
    min_days_to_deadline: int = 5


class Eligibility(_Strict):
    countries: list[str] = Field(default_factory=lambda: ["ES"])
    interreg_country: str | None = "Spain"
    beneficiary_tokens: list[str] = Field(default_factory=list)


class KeywordGroup(_Strict):
    weight: float
    cap: float = 0
    terms: list[str] = Field(default_factory=list)


class Codes(_Strict):
    include: list[str] = Field(default_factory=list)
    exclude: list[str] = Field(default_factory=list)
    include_weight: float = 2
    exclude_weight: float = -2


class Funders(_Strict):
    weight: float = 2
    terms: list[str] = Field(default_factory=list)


class Budget(_Strict):
    tender_sweet_min: float | None = None
    tender_sweet_max: float | None = None
    tender_sweet_weight: float = 1
    tender_max: float | None = None
    tender_over_max_weight: float = -2


class Sources(_Strict):
    disabled: list[str] = Field(default_factory=list)
    boost: dict[str, float] = Field(default_factory=dict)


class Report(_Strict):
    top: int = 40           # lexical candidates handed to the agent for judging
    deep_read: int = 10     # of those, how many the agent reads documents for


class Profile(_Strict):
    name: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$")
    language: Literal["es", "en"] = "es"
    who: Who
    looking_for: LookingFor = Field(default_factory=LookingFor)
    not_interested_in: str | None = None
    eligibility: Eligibility = Field(default_factory=Eligibility)
    keywords: dict[str, KeywordGroup] = Field(default_factory=dict)
    cpv: Codes = Field(default_factory=Codes)
    cnae: Codes = Field(default_factory=Codes)
    funders: Funders = Field(default_factory=Funders)
    budget: Budget = Field(default_factory=Budget)
    sources: Sources = Field(default_factory=Sources)
    report: Report = Field(default_factory=Report)
    bdns_history_terms: list[str] = Field(default_factory=list)

    @field_validator("keywords")
    @classmethod
    def _known_groups(cls, v: dict[str, KeywordGroup]) -> dict[str, KeywordGroup]:
        unknown = set(v) - {"core", "strong", "context", "negative"}
        if unknown:
            raise ValueError(f"unknown keyword groups {sorted(unknown)}; "
                             "use core / strong / context / negative")
        if "negative" in v and v["negative"].weight > 0:
            raise ValueError("keywords.negative.weight must be negative")
        return v

    def hash(self) -> str:
        """Identity of what verdicts depend on; report sizing is excluded so
        widening `top` does not make existing verdicts stale."""
        canonical = json.dumps(self.model_dump(mode="json", exclude={"report"}),
                               sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(canonical.encode()).hexdigest()[:16]

    def brief(self) -> dict:
        """What the agent judges against: the prose plus the hard facts."""
        return {
            "name": self.name,
            "role": self.who.role,
            "who": self.who.summary.strip(),
            "country": self.who.country,
            "regions": self.who.regions,
            "size": self.who.size,
            "legal_form": self.who.legal_form,
            "kinds": self.looking_for.kinds,
            "routes": self.looking_for.routes,
            "looking_for": (self.looking_for.notes or "").strip() or None,
            "not_interested_in": (self.not_interested_in or "").strip() or None,
            "language": self.language,
        }


def resolve(name_or_path: str) -> Path:
    p = Path(name_or_path)
    if p.suffix in {".yaml", ".yml"} and p.exists():
        return p
    for ext in (".yaml", ".yml"):
        cand = profiles_dir() / f"{name_or_path}{ext}"
        if cand.exists():
            return cand
    raise FileNotFoundError(
        f"no profile {name_or_path!r} (looked in {profiles_dir()}); "
        "copy one of profiles/example-*.yaml to start")


def load(name_or_path: str) -> Profile:
    path = resolve(name_or_path)
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return Profile.model_validate(data)


def list_profiles() -> list[Path]:
    d = profiles_dir()
    return sorted(p for p in [*d.glob("*.yaml"), *d.glob("*.yml")])
