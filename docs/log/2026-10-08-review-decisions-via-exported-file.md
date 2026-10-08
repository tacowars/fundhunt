# Review marks return through an exported JSON file, not a local server

- Date: 2026-10-08
- Links: ADR `2026-10-08-local-first-agent-as-judge`; `src/fundhunt/report.py`

## Decision

- **The report is one static, self-contained HTML file.** Its data is
  embedded and it makes no network requests.
- **Marking.** The user marks each candidate *pursue*, *maybe* or
  *dismiss*, with an optional note. The marks live in the browser's
  localStorage, keyed by profile.
- **Export.** **Export decisions** downloads
  `fundhunt-decisions-<profile>-<date>.json`.
- **Import.** `fundhunt decisions import --profile <name>` reads those
  files from `~/Downloads` and `data/inbox/`, or from explicit paths.
  The import is idempotent: for each (profile, record), the latest
  `decided_at` wins. The agent runs it at the start of every run.
- **Use.** Dismissed records drop out of the agent's candidate list. All
  marks are evidence when tuning the profile, and the agent proposes any
  change before making it.

## Why

- **Labels were the predecessor's scarcest resource.** Its calibration
  stalled when the pilot user was no longer available to label. Marks
  made during normal use are the cheapest label source there is.
- **A static file needs nothing running.** It opens in any browser,
  survives being emailed or archived, and leaves no port open. A
  `fundhunt serve` process would be one more thing for a non-programmer
  to start, stop and debug.

## Punted / alternatives

- *A local HTTP server writing straight to SQLite.* Deferred. Revisit if
  the export/import round trip proves to be friction in practice.
- *Using marks to change scoring automatically.* Rejected. Feedback is
  evidence, not a silent mutation, as in the predecessor. Profile changes
  stay explicit and user-approved.
