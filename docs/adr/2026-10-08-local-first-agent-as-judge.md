# Local-first CLI plus agent skill, with the user's agent as the judge

- Status: Accepted
- Date: 2026-10-08
- Decision owners: tacowars
- Depends on: none (founding ADR)
- Evidence: `docs/log/2026-10-08-lineage-from-the-web-prototype.md`

## Context

fundhunt's predecessor ran as a hosted, multi-tenant web application:
- FastAPI, Angular and PostgreSQL/pgvector on Kubernetes;
- an LLM judge paid for through a metered API.

It proved the matching concept: lexical ranking, then an LLM eligibility
judge, then a document-grounded deep read. It was shut down because too
few people used it. The infrastructure cost and operational weight were
out of all proportion to an audience of one pilot user.

The people who need this, such as consultancies, SMEs, municipalities,
NGOs and research groups, increasingly have a coding agent already:
Claude Code, OpenAI Codex, Cowork. That agent can read a call and judge
it as well as the hosted judge did, at no extra cost to them.

## Decision

1. **Distribution.** fundhunt is a public repository that each user
   clones and runs on their own machine. There is no server, account or
   hosted component.
2. **A deterministic CLI does the mechanics.** `uv run fundhunt …` covers:
   - acquisition from public keyless sources (`sync`);
   - storage in one local SQLite file (`data/fundhunt.db`);
   - lexical ranking per profile (`rank`);
   - document discovery and text extraction (`doc`);
   - verdict storage (`verdict`);
   - a self-contained HTML report (`report`).

   Every command prints JSON, so any agent can drive it.
3. **The user's agent is the judge.** fundhunt contains no LLM client
   and needs no API key. The agent skill (`skills/fundhunt/SKILL.md`,
   with `references/judging.md`) defines the workflow and the verdict
   contract:
   - `strong | plausible | reject`;
   - one route: `apply | bid | partner | advise_clients | monitor`;
   - `constraint_applied` is required for a reject;
   - `fit`, `key_constraints` and `next_step` are added after a deep read.

   The CLI validates verdicts and pins each one to the record's content
   hash and the profile hash. A changed record or profile makes the
   verdict stale, so it is judged again. An unchanged one is never
   re-judged, which keeps the agent's token use proportional to what is
   new.
4. **Profiles are YAML files** (`profiles/<name>.yaml`), and a user may
   keep several. The prose fields (`who.summary`, `looking_for.notes`,
   `not_interested_in`) are what the agent judges against. The
   structured fields only feed the lexical funnel.
5. **Portability.** `AGENTS.md` is the canonical entry point and
   `CLAUDE.md` imports it. The skill lives in `skills/fundhunt/` and is
   symlinked into `.claude/skills/` and `.agents/skills/`, where agents
   that auto-discover skills look. Everything else is plain files and
   commands, so any agent that can run a shell can use fundhunt.
6. **Feedback stays local.** Review marks made on the HTML page travel
   back as an exported JSON file (`fundhunt decisions import`). There is
   no local server (log: `2026-10-08-review-decisions-via-exported-file`).

## Consequences

- Users need `uv`, a terminal-capable agent, and about 30 minutes for the
  first sync. Later syncs are incremental.
- The quality of judgments depends on the user's agent and model. The
  rubric and the strict verdict schema keep the output comparable
  between agents, but they cannot make it identical. The agent and model
  are recorded in `judged_by`.
- There is no telemetry or shared corpus. Each clone acquires its own
  copy of the public data, which is acceptable at this scale: a few
  thousand requests per day across all sources.
- The predecessor's tenancy, auth, email, API, i18n framework and
  infrastructure layers are dropped.

## Re-entry

Revisit if users ask for:
- **unattended judging**, e.g. a scheduled run with a headless agent.
  That would need an explicit per-run cost guard;
- **a shared corpus**, to avoid every clone re-downloading the same
  public data.
