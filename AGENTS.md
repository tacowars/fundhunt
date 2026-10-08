# fundhunt — agent instructions

This file is read by Codex, Claude Code (via `CLAUDE.md`) and any agent
that follows the AGENTS.md convention.

## If you are here to USE fundhunt (the common case)

The user wants funding or tender opportunities, not code. Load and follow
the skill **`skills/fundhunt/SKILL.md`**; read it in full before doing
anything else. Pointer files at `.claude/skills/fundhunt` and
`.agents/skills/fundhunt` lead agents that discover skills there to it.

- **Never change code for normal use.** The CLI (`uv run fundhunt …`)
  covers setup, sync, ranking, document reading, verdicts and reports.
- The user's profiles (`profiles/*.yaml` except `example-*`), `data/`
  and the reports are personal and git-ignored. Never commit them,
  never paste their contents into issues or PRs, and never send them
  anywhere.

## If you are here to DEVELOP fundhunt

- Layout:
  - `src/fundhunt/`: the CLI (`cli.py`) and its modules (sync, snapshot, store,
    rank, documents, report).
  - `src/fundhunt/sources/`: one adapter per source.
  - `skills/fundhunt/`: the agent workflow.
  - `profiles/`: the schema docs and examples.
  - `docs/`: `sources.md`, the decision log and the ADRs.
- Verify with `uv run pytest`. Tests never touch the network: fixtures
  live in `tests/fixtures/`.
- Run `bash scripts/setup-dev.sh` once. It installs the pre-commit
  privacy guard (`scripts/privacy-check.sh`).
- **Public identity.** The owner appears only as `tacowars`. Never add a
  real name, a personal email, or a client or organisation name from
  the owner's work to code, docs, commits, PRs or issues. Commits use
  `tacowars <575338+tacowars@users.noreply.github.com>`. Example
  profiles are fictional.
- **Decisions.** One file per decision in `docs/log/YYYY-MM-DD-<slug>.md`
  (`bash scripts/log.sh new <slug>`; convention in `docs/log/README.md`).
  Architecture-level decisions get an ADR in `docs/adr/`. Accepted ADRs
  are binding.
- **Sources.** Endpoint quirks belong in `docs/sources.md`, next to the
  adapter change that needed them. Every source is keyless and public;
  don't add one that needs an account or scraping behind a login.
- **No LLM calls in code.** Judgment belongs to the user's agent, so
  fundhunt never needs an API key (ADR
  `2026-10-08-local-first-agent-as-judge`).
- Commit style: sentence-case imperative subject; the body explains why.
