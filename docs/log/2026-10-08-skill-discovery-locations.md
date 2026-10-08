# AGENTS.md is canonical; the skill is symlinked where agents discover skills

- Date: 2026-10-08
- Links: ADR `2026-10-08-local-first-agent-as-judge`

## Decision

- **One source.** The skill lives once, at `skills/fundhunt/`, and
  follows the Agent Skills layout: a `SKILL.md` with name and description
  frontmatter, plus `references/`.
- **Symlinks.** It is linked as `.claude/skills/fundhunt` and
  `.agents/skills/fundhunt`, for agents that auto-discover skills there.
- **Entry point.** `AGENTS.md` tells every agent to load
  `skills/fundhunt/SKILL.md` explicitly, and `CLAUDE.md` imports
  `AGENTS.md`.

## Why

- **Discovery paths differ.** The agents users are likely to bring
  (Claude Code, Codex, Cowork) find skills in different places, and the
  conventions are still moving.
- **One file every agent reads.** `AGENTS.md` plus an explicit path
  works with any agent that reads repository instructions. The symlinks
  are a convenience on top of it, not a dependency.

## Punted / alternatives

- *Copies instead of symlinks.* Rejected: copies drift. If a Windows
  checkout does not materialise symlinks, the `AGENTS.md` pointer still
  works.
- *Packaging the skill separately* (a plugin or marketplace). Deferred
  until the skill is stable.
