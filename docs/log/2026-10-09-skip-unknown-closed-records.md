# Closed records we never held are skipped, except in BDNS

- Date: 2026-10-09
- Links: refines the pruning in ADR `nightly-corpus-snapshot`;
  `docs/sources.md` (common rules)

## Decision

- **At sync.** A record that arrives already closed is skipped, unless
  its id is stored already (`models.lifecycle`: a past deadline, or a
  closed status). Sync reports it as `skipped_closed`. A record we
  already hold still takes the update, so verdicts on it go stale as
  they should.
- **BDNS is exempt** (`sources.KEEPS_UNKNOWN_CLOSED`). It picks which
  details to fetch by the ids it holds, so a skipped closed call would
  be fetched again every night.
- **In the snapshot.** Closed records from every other source are pruned
  as soon as `lifecycle()` calls them closed, by deadline or by status
  (TED `can-*`, PLACSP `resuelta`), since nothing would fetch them
  again. A deadline-only check missed the undated award notices. BDNS keeps the 60-day rule: closed for 60 days, and held for 60
  days.

## Why

The third snapshot run (2026-10-08) added 5,005 PLACSP records in one
incremental window. Almost all were award, resolution or evaluation
notices for tenders the corpus never held. They took the snapshot from
4.4 to 9.8 MB in a day, and would have grown every user's local database
the same way. Ranking excludes closed records anyway, so they were dead
weight.

Rebuilding that same snapshot under these rules gives 6.4 MB instead of
9.8 MB:
- PLACSP drops from 10,856 records to 5,835;
- TED drops from 2,529 to 2,129, losing its award notices;
- SEDIA's stale "open" topics past their deadline go as well.

## Punted / alternatives

- *Filtering in each adapter.* Rejected: the rule is the same for every
  source, and in `sync` it sits next to the store it consults.
- *Pruning users' local databases.* Still open. Local databases no
  longer grow from unknown closed notices, but they keep what they
  already have.
