# Getting started is one sentence to the user's assistant

- Date: 2026-10-08
- Links: ADR `local-first-agent-as-judge` (its consequence "users need
  `uv`, a terminal-capable agent…" now falls on the agent, not the user);
  `skill-pointers-not-symlinks`; `README.md`; `skills/fundhunt/SKILL.md`

## Decision

- **The README opens with a sentence to say, not steps to follow.** It
  opens in Spanish, then repeats in English: *"Instala fundhunt desde
  https://github.com/tacowars/fundhunt y configúralo para mí."* No `uv`,
  git or terminal instructions appear before it.
- **The assistant installs.** A README section addressed to the
  assistant covers the rest:
  - choose a folder;
  - clone if git exists, otherwise download the `main` zip, so git is
    not required;
  - install uv with its official one-liner after asking (PowerShell on
    Windows), and work around a stale `PATH`;
  - run `status` and `sync`, then hand over to the skill.
- **Updates are a sentence too** ("Update fundhunt", skill workflow E):
  `git pull` for a clone. For a zip, the assistant extracts a fresh copy,
  moves the user's profiles and `data/` into it, and swaps the folders,
  keeping the old one until the user agrees to delete it. Extracting
  over the old folder fails where a path changed type (the old skill
  symlinks were text files in a Windows extraction) and leaves deleted
  files behind.
- **Technical setup moves to a "For technical users" section** near the
  end of the README.
- **Windows-safe agent I/O.**
  - The skill no longer pipes JSON through shell heredocs, which
    PowerShell lacks. Agents write the JSON to `data/tmp/` and pass the
    path: `verdict --file`, `decisions import <file>`.
  - The CLI forces UTF-8 on stdin, stdout and stderr, so accented
    titles print correctly under a legacy Windows code page.
- **Tone.** The skill tells the agent that most users aren't technical:
  plain words in the user's language, and no commands or JSON unless
  asked.

## Why

The owner's expected users are about 99% Windows laptop users in Spain:
autónomos, small businesses, small municipalities and their advisors.
They have no terminal experience, but they do have a Claude or ChatGPT
subscription whose app can run code. "Install uv, then git clone" would
stop them at step one, and git is rarely present on Windows. Their
assistant can do every one of those steps if it is told how.

## Punted / alternatives

- *A Windows installer or a standalone executable.* Deferred: the
  assistant is needed for judging anyway, and it can install uv in one
  command.
- *A Claude desktop extension or an uploadable skill zip.* Worth
  revisiting after the cross-platform test round shows where the
  agent-led install struggles.
- *A Spanish-only README.* Rejected: the technical sections and
  contributors stay English, and the opening serves both languages.
