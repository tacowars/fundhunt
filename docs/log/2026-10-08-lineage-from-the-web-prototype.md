# fundhunt restarts as a clone-and-run tool, carrying forward the prototype's proven parts

- Date: 2026-10-08
- Links: ADR `2026-10-08-local-first-agent-as-judge`

## Decision

fundhunt is a new public repository, `tacowars/fundhunt`. It succeeds a
private project, `tacowars/granthunter`, which went from a local CLI
prototype to a hosted web application at fundhunt.eu. That project is on
hold, its cluster is decommissioned, and it stays private.

**Carried forward**, as fresh code without history:
- The seven source adapters and their hard-won quirks. They are
  re-recorded in `docs/sources.md`.
- The SQLite store with content-hash revisions.
- The lexical matcher with tiers and readable reasons, plus the
  lexical-v2 refinements that fit a single-user tool:
  - tier B can also be reached with one strong hit plus a structural
    match;
  - a soft territory penalty;
  - an indirect penalty only when the profile takes no partner/advise
    routes.
- `lifecycle-v1`, under which a missing deadline never means open.
- The per-source deep-read document recipes.
- The judge and deep-read contract: verdict, route ("play"),
  `constraint_applied`, fit, key constraints.
- The near-duplicate collapse.
- The decision-log convention: dated, one file per decision,
  append-only.

**Left behind**:
- multi-tenancy, auth, email, the REST API, the Angular SPA,
  Kubernetes/Terraform and PostgreSQL/pgvector;
- embeddings and vector retrieval;
- the metered LLM client and its spend guard;
- the predecessor's decision records (85 log entries, D1–D80, ADRs).
  They describe a different system and live with it. This repository
  cites its evidence only through this record.

No client data, personal profile, label set or database from the
predecessor enters this repository.

## Why

These are the predecessor's own measured outcomes:
- **The judge plus deep read is worth keeping.** On a blind replay, the
  AI-curated shortlist was 75% customer-useful in the top 12, against
  58% for lexical ranking alone.
- **Vectors didn't earn their cost.** Recovery of useful records in the
  top 12, on a blind set of 45 labels:

  | Method | Useful records recovered |
  |---|---|
  | lexical | 7 of 19 |
  | best enriched-vector variant | 3 of 19 |
  | hybrid | 6 of 19 |

  The predecessor's decision was "lexical stands". So no embeddings and
  no vector database: the install stays light and needs no API key.
- **The binding constraint was adoption, not matching quality.** One
  pilot user and 45 labels could not justify a hosted multi-tenant
  stack. A tool that each user runs inside an agent they already have
  removes that cost entirely.

## Punted / alternatives

- *Fork the private repository and strip it down.* Rejected. Its
  history holds client-specific material that must not become public,
  and most of the code is the tenancy and infrastructure being dropped.
- *Copy the old decision records.* Rejected for the reason above. The
  convention is reused instead.
