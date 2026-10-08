# The owner appears only as `tacowars`, enforced by a pre-commit guard

- Date: 2026-10-08
- Links: `scripts/privacy-check.sh`, `scripts/hooks/pre-commit`

## Decision

- **Git identity.** Commits and tags use
  `tacowars <575338+tacowars@users.noreply.github.com>`, the GitHub
  ID-based noreply address. It is set in the repository's local git
  config, not only globally.
- **Public text.** Code, docs, commit messages, PRs and issues name the
  owner only as `tacowars`: no real name, no email, no pronouns. Client
  and organisation names from the owner's work never appear, and
  example profiles are fictional.
- **Enforcement.** `scripts/privacy-check.sh`, installed as the
  pre-commit hook by `scripts/setup-dev.sh`, refuses a commit when:
  - the author or committer identity is not a noreply address;
  - an added line contains a non-noreply email address;
  - an added line contains a word from `.privacy-words`. This file is
    git-ignored and holds the words that must never appear, so the
    words themselves never enter the repository.

  `bash scripts/privacy-check.sh tree` scans every tracked file, and is
  run before each push.
- **Upstream contact.** The HTTP User-Agent identifies the project by its
  repository URL, with no personal contact address. That is enough for
  source operators to identify the traffic.

## Why

Identity leaks are cheap to prevent and impossible to fully remove from
git history afterwards. Contributors and agents repeat whatever text they
see, so the rule is enforced mechanically, not left to memory.

## Punted / alternatives

- *Rely on discipline alone.* Rejected for the reason above.
- *Put the word list in the repository.* Rejected: the list itself
  would leak the words.
