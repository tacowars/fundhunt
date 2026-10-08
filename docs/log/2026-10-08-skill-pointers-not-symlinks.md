# Skill discovery uses pointer files instead of symlinks

- Date: 2026-10-08
- Links: supersedes the symlink part of `skill-discovery-locations`;
  `agent-led-install`

## Decision

`.claude/skills/fundhunt/SKILL.md` and `.agents/skills/fundhunt/SKILL.md`
are small pointer files, not symlinks. Each carries the same frontmatter
as `skills/fundhunt/SKILL.md`, so it triggers on the same requests, and
its body tells the agent to read the real skill. A test fails if either
pointer's frontmatter drifts from the skill's, or if a pointer turns back
into a symlink. The skill itself still lives once, in `skills/fundhunt/`.

## Why

Most users will now get fundhunt as GitHub's zip download on Windows,
where extraction turns a symlink into a short text file. Discovery would
then silently fall back to the `AGENTS.md` pointer. Pointer files work
everywhere. The earlier objection to copies, that they drift, doesn't
apply: only the frontmatter is duplicated, and a test guards it.

## Punted / alternatives

- *Full copies of the skill.* Rejected: they drift.
- *Relying on the `AGENTS.md` pointer alone.* Kept as the fallback, but
  skills that auto-trigger on "find me grants" need the files in place.
