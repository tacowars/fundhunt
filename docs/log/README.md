# Decision log: one file per decision

This convention is inherited from fundhunt's predecessor project (see
`2026-10-08-lineage-from-the-web-prototype`). Dated files mean parallel
contributors and agents never collide on a sequence number.

## Convention

- **One decision per file**, named `YYYY-MM-DD-<slug>.md` (kebab-case
  slug).
  - Scaffold one with `bash scripts/log.sh new <slug> [title]`.
  - The date is the day the decision was made, so `ls` sorts
    chronologically.
  - List the records with `bash scripts/log.sh list`.
- **Cite a decision by its slug**, e.g. "per `agent-is-the-judge`".
- **Record decisions and their rationale, not progress.** Progress
  belongs in issues and PRs. Durable reference material such as endpoint
  quirks goes to `docs/sources.md` or `AGENTS.md`. A log entry may point
  at that material, but it is not its home.
- **Architecture-level decisions get an ADR** in `docs/adr/` instead. A
  log entry may point at an ADR but must not duplicate it.
- **Files are append-only history.** Fixing a typo is fine. A superseded
  decision gets a new file that names the old one; it is never rewritten.
- **A decision made during PR work lands in the same PR.** The PR body
  names the record, or says why none was needed.
- **Public repository.** The owner is `tacowars`; no real names, personal
  emails or client names appear in any record.

## Template

```markdown
# <Short declarative summary of the decision>

- Date: YYYY-MM-DD
- Links: issue #n · PR #n · ADR <slug> — whichever apply

## Decision

What was decided, concretely.

## Why

The reasoning, constraints, and evidence.

## Punted / alternatives

What was considered and rejected, or deferred and why.
```
