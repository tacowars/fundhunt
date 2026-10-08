# Review marks return by download or by pasting into chat, taught by a guided tour

- Date: 2026-10-08
- Links: refines `2026-10-08-review-decisions-via-exported-file`; `src/fundhunt/report.py`

## Decision

The report stays one static, self-contained HTML file. Getting marks back
to the agent changes in four ways:

1. **Two return channels.**
   - **Download file** writes `fundhunt-decisions-<profile>-<date>.json`.
     An agent on the same machine finds it in `~/Downloads`; elsewhere it
     can be attached to the chat.
   - **Copy for agent** puts a text block on the clipboard. It starts with
     a `FUNDHUNT-DECISIONS` marker line, then a one-line hint for the
     agent, then the JSON. The user pastes it into the chat, and the agent
     pipes it to `fundhunt decisions import --stdin`.
   - The parser ignores code fences and surrounding prose. When the
     browser blocks clipboard access, a dialog shows the text pre-selected
     for manual copying.
2. **A guided tour** runs on first open and can be replayed from the "?"
   button. Its help bubbles cover the mark buttons, the notes, and the
   two send-back buttons, with when to use which.
3. **Visible unsent state.**
   - A badge counts marks changed since the last send ("3 sin enviar").
   - Leaving the page with unsent marks triggers the browser's
     leave-page warning.
4. **Notes are kept when a mark is cleared.** They are stored as decision
   `note`, and `fundhunt decisions list` shows the agent every mark and
   note, so it can propose profile changes.

## Why

The earlier record assumed the agent and the browser share a filesystem.
That holds for desktop and terminal agents, but not for cloud sandboxes:
Claude Code on the web, Codex cloud, and mobile-app sessions. In those,
the user may not be able to attach files at all, while pasting text into
the chat works everywhere.

A local review server, writing straight to SQLite, has the same
shared-machine assumption. It also depends on each sandbox allowing a
port to be opened and reached. Those environments are untested, so the
static file with a paste route keeps every option open.

The tour addresses the main failure of a static page, which is
forgetting to send the marks back: the predecessor lost its feedback
loop when labelling stopped.

## Punted / alternatives

- *`fundhunt review`, a localhost server that saves marks as they are
  made.* Deferred, not rejected. Revisit once the target sandboxes are
  tested. It would complement the static page in local sessions, not
  replace it.
- *The File System Access API, writing straight into `data/inbox`.*
  Rejected: Chromium only, it needs a folder-picker step, and it does
  nothing for cloud sessions.
- *A tour library.* Rejected: the page loads nothing from the network,
  and about 60 lines of inline script are enough.
