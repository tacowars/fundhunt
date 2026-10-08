# Architecture decision records

ADRs record decisions that shape the whole system. **Accepted ADRs are
binding.** The `Status:` line in each file, not its file name, says
whether an ADR is accepted. Smaller decisions go to `docs/log/`.

## Naming

Name each ADR `YYYY-MM-DD-<slug>.md` and cite it by slug.

## Header block

```markdown
# <Title>

- Status: Proposed | Accepted | Superseded by <slug>
- Date: YYYY-MM-DD
- Decision owners: tacowars
- Depends on: <slugs, or none>
- Evidence: <optional: benchmarks, records>
```

The sections are: **Context**, **Decision** and **Consequences**, plus a
**Re-entry** section where a later revisit is expected.
