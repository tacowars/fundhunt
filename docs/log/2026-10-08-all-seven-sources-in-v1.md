# v1 ships all seven sources, including the three fragile ones

- Date: 2026-10-08
- Links: `docs/sources.md`

## Decision

The first release ships every source the predecessor ingested:

| Group | Sources |
|---|---|
| stable | `ted`, `bdns`, `placsp`, `sedia` |
| fragile | `sedia_cascade`, `interreg`, `epah` |

Fragility is handled in the design, not by leaving sources out:
- **Isolation.** Each source syncs in its own try/except, and a failing
  source never blocks the others. `sync` exits 3 and names the failure.
- **Partial coverage.** A capped run is recorded as `coverage: partial`,
  and the next sync resumes from the last *complete* run.
- **Conservative absence.** A record that disappears from a source never
  closes the opportunity; only its deadline or explicit status does.
- **Repair notes.** `docs/sources.md` carries a repair note per fragile
  source, such as rotating the Interreg key or the PLACSP host failover.
  The agent follows it when it hits that source's failure.

## Why

The fragile sources hold some of the most actionable calls:
- cascade/FSTP calls are small, fast and suited to SMEs;
- Interreg calls are a consortium route for partners;
- EPAH is the main route for municipalities, and a lead source for
  their advisers.

The predecessor ran all seven daily for weeks. The failures it saw were
intermittent and recoverable, not structural.

## Punted / alternatives

- *Ship the four stable sources first.* Rejected by the owner.
- *Official fallback APIs.* The keep.eu API, for example, needs
  registration. Deferred: fundhunt sources stay keyless.
