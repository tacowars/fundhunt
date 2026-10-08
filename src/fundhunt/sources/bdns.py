"""BDNS / SNPSAP (Spanish public grants and aid, incl. CDTI calls).

Two-step: page the shallow `busqueda` list newest-first by fechaRecepcion
until records fall outside the window, then fetch the rich detail per
convocatoria. Dedup key: numeroConvocatoria.

No documented rate limits — be conservative: a delay between detail
fetches and a cap per run. Records not yet stored are fetched first, so a
backlog drains across successive runs; when the cap bites the run is marked
partial and the next sync continues (truncation is never silent).
There is no server-side "open" filter: openness comes from the detail.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from datetime import date, datetime, timedelta

from .. import http
from ..models import Classification, Kind, Opportunity
from . import SyncContext

API_BASE = "https://www.infosubvenciones.es/bdnstrans/api"
PAGE_SIZE = 200
DETAIL_DELAY_S = 0.25
MAX_DETAILS_PER_RUN = 600
FIRST_RUN_DAYS = 45          # registrations window taken on the first sync
FIRST_RUN_MAX_DETAILS = 2500  # ~15 min; the rest drains on later syncs


def _parse_date(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        return None


def normalize(detail: dict) -> Opportunity:
    organo = detail.get("organo") or {}
    funder = " / ".join(filter(None, [organo.get("nivel1"), organo.get("nivel2"),
                                      organo.get("nivel3")]))
    fin = _parse_date(detail.get("fechaFinSolicitud"))
    deadline = datetime.combine(fin, datetime.max.time().replace(microsecond=0)) if fin else None
    classifications = [
        Classification(scheme="cnae", code=s.get("codigo", ""), label=s.get("descripcion"))
        for s in detail.get("sectores") or [] if s.get("codigo")
    ] + [
        Classification(scheme="nuts", code=(r.get("descripcion") or "").split(" - ")[0],
                       label=r.get("descripcion"))
        for r in detail.get("regiones") or []
    ]
    num = str(detail.get("codigoBDNS") or detail.get("numeroConvocatoria"))
    budget = detail.get("presupuestoTotal")
    return Opportunity(
        source="bdns",
        source_id=num,
        kind=Kind.GRANT,
        title=(detail.get("descripcion") or f"Convocatoria {num}")[:500],
        summary=detail.get("descripcionFinalidad"),
        funder=funder or None,
        country="ES",
        regions=[c.code for c in classifications if c.scheme == "nuts"],
        classifications=classifications,
        budget_value=budget,
        budget_currency="EUR" if budget is not None else None,
        status="abierto" if detail.get("abierto") else "cerrado",
        open_date=_parse_date(detail.get("fechaInicioSolicitud")),
        deadline=deadline,
        deadlines_raw=[s for s in (detail.get("fechaFinSolicitud"), detail.get("textFin")) if s],
        url=(detail.get("urlBasesReguladoras") or detail.get("sedeElectronica")
             or f"https://www.infosubvenciones.es/bdnstrans/GE/es/convocatorias/{num}"),
        language="spa",
        raw={k: detail.get(k) for k in ("tipoConvocatoria", "tiposBeneficiarios",
                                        "instrumentos", "finalidad", "abierto",
                                        "textInicio", "textFin", "fechaRecepcion")},
    )


def fetch(ctx: SyncContext) -> Iterator[Opportunity]:
    days = FIRST_RUN_DAYS if ctx.first_run else ctx.since_days
    cap = FIRST_RUN_MAX_DETAILS if ctx.first_run else MAX_DETAILS_PER_RUN
    cutoff = date.today() - timedelta(days=days)
    with http.client() as c:
        page, pending = 0, []
        while True:
            resp = http.request(c, "GET", f"{API_BASE}/convocatorias/busqueda",
                                params={"page": str(page), "pageSize": str(PAGE_SIZE),
                                        "order": "fechaRecepcion", "direccion": "desc"})
            data = resp.json()
            stop = False
            for item in data.get("content", []):
                received = _parse_date(item.get("fechaRecepcion"))
                if received and received < cutoff:
                    stop = True
                    break
                if item.get("numeroConvocatoria"):
                    pending.append(str(item["numeroConvocatoria"]))
            if stop or data.get("last") or not data.get("content"):
                break
            page += 1

        pending = list(dict.fromkeys(pending))
        fresh = [n for n in pending if n not in ctx.known_ids]
        todo = fresh + [n for n in pending if n in ctx.known_ids]
        if len(fresh) > cap:
            ctx.partial(f"{len(fresh) - cap} new BDNS records deferred by the "
                        f"{cap}-detail cap; the next sync continues")
        todo = todo[:cap]

        failures = 0
        for num in todo:
            try:
                resp = http.request(c, "GET", f"{API_BASE}/convocatorias",
                                    params={"numConv": num})
                yield normalize(resp.json())
            except Exception:
                failures += 1
                if failures > 50:
                    raise
            time.sleep(DETAIL_DELAY_S)
        if failures:
            ctx.partial(f"{failures} BDNS detail fetches failed; the next sync retries them")
