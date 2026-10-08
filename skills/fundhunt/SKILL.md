---
name: fundhunt
description: Find EU and Spanish grants, aid (subvenciones, ayudas) and public tenders (licitaciones) that fit a user's profile, judge them, and open an HTML results page. Use when the user asks to set up fundhunt, create or edit a funding profile, run or refresh fundhunt, review funding/tender candidates, import their review decisions, or schedule source syncs.
---

# fundhunt

You run the whole fundhunt loop for the user. **No code changes are ever
needed for normal use.** If a step seems to need one, stop and tell the
user what broke. Don't patch the source.

You drive a CLI. Every command prints JSON on stdout and progress on
stderr. Run everything from the repository root:

```bash
uv run fundhunt <command>
```

If `uv` is missing, ask the user to install it
(https://docs.astral.sh/uv/getting-started/installation/), or install it
yourself if they agree. Nothing else needs installing: `uv run` builds the
environment on first use.

The division of labour: the CLI handles acquisition, storage, lexical
ranking, document text extraction and the report. **You** handle the
judgment: whether a call fits this applicant, by which route, and why.

## Which workflow?

| The user says… | Do |
|---|---|
| "set up fundhunt", "create my profile", no profile exists yet | **A. Profile** |
| "run fundhunt", "what's new", "find me grants/tenders" | **B. Run** |
| "import my decisions", they mention or attach the exported file, or paste a block starting `FUNDHUNT-DECISIONS` | **B**, step 1 only, then offer a run |
| "the results are off", "too much X" | **C. Tune** |
| "keep it updated", "schedule it" | **D. Schedule** |

Start every session with `uv run fundhunt status`. It shows the profiles,
the last complete sync per source and recent failures.

## A. Profile

1. Read `profiles/README.md` (the field reference) and the closest
   `profiles/example-*.yaml`:
   - `example-sme`: a company that applies and bids;
   - `example-consultancy`: also advises clients;
   - `example-ayuntamiento`: a public body that only applies.
2. Gather the facts. If the user gives a website, brochure or CV, read it
   first and only ask about the gaps. Otherwise interview them, using
   `references/profile-interview.md`. Keep it short: 6–10 questions, one
   or two at a time.
3. Write `profiles/<name>.yaml`. The name is lowercase with hyphens, e.g.
   `acme-energia`. Write `who.summary`, `looking_for.notes` and
   `not_interested_in` as honest prose in the user's language. You judge
   against these later, so the hard facts (size, location, legal form,
   track record) must be in them.
4. Keywords:
   - `core`: 4–8 phrases that *are* the user's thesis.
   - `strong`: adjacent niches.
   - `context`: broad words.
   - `negative`: never-a-fit markers.

   Write every term both unaccented and in each language the calls use:
   Spanish for BDNS and PLACSP, English for the EU sources. A term may be
   a prefix (`"sostenib"`).
5. Run `uv run fundhunt profile check <name>` and fix any errors.
6. If the database has data, calibrate. Run
   `uv run fundhunt rank --profile <name>`, then
   `uv run fundhunt candidates --profile <name> --top 15`. Show the user
   the 15 titles and ask "are these the right kind of thing?" Adjust the
   keywords once or twice. Don't chase perfection: your judgment step
   fixes ordering mistakes.
7. Tell the user the profile file is theirs to edit, and that it is never
   committed (git ignores it).

The user can have several profiles, e.g. their firm plus each client they
advise. All of them share one database.

## B. Run

1. **Import decisions.** The user's marks on the last report reach you in
   one of three ways. Handle whichever applies, then mention what was
   applied, e.g. "3 dismissed, 2 marked pursue, 1 note".
   - **A pasted block** starting with `FUNDHUNT-DECISIONS`, from the
     page's **Copy for agent** button. This is the normal route in cloud,
     web and mobile sessions. Pipe it verbatim:
     ```bash
     uv run fundhunt decisions import --profile <name> --stdin <<'EOF'
     <the pasted block, exactly as given>
     EOF
     ```
   - **An attached file** (`fundhunt-decisions-<profile>-<date>.json`):
     pass its path, `uv run fundhunt decisions import --profile <name> <path>`.
   - **Nothing given:** run `uv run fundhunt decisions import --profile <name>`.
     It searches `~/Downloads` and `data/inbox/`, which works when you run
     on the user's own machine. If it finds nothing and there is an
     earlier report, ask once whether they marked anything. If they did,
     explain both ways of sending marks back (step 9).
2. **Sync.** Run `uv run fundhunt sync`.
   - The first sync takes about 30 minutes. Tell the user before it
     starts and let it run. BDNS reports `coverage: partial` for its
     first 2–3 syncs while its backlog drains; that is expected.
   - Later syncs only fetch what changed: a few minutes.
   - Exit code 3 means at least one source failed. Report which one and
     carry on: the others are fine, and a failed source simply retries on
     the next sync.
   - `coverage: partial` means a cap was hit. The next sync continues
     where this one stopped.
3. **Rank.** Run `uv run fundhunt rank --profile <name>`.
4. **Get candidates.** Run `uv run fundhunt candidates --profile <name>`.
   It returns:
   - the profile `brief`;
   - the `candidates` that have no current verdict (new or changed
     records, or records judged against an older profile);
   - `deep_read_budget`.

   Already-judged records are skipped automatically, so later runs are
   cheap.
5. **Judge** each candidate against the brief, following
   `references/judging.md`. Read that file before your first verdict of
   the session.
6. **Deep read** the best calls, up to `deep_read_budget`: strong
   candidates first, then plausible ones with a decisive open question.
   For each, run `uv run fundhunt doc <ref>`. It returns the official
   documents as text, or explains why it couldn't. Then update the
   verdict with `fit`, `key_constraints`, `next_step` and
   `deep_read: true`.
7. **Save** your verdicts, in batches of about 10 as you go so that
   nothing is lost if the session ends:
   ```bash
   uv run fundhunt verdict --profile <name> <<'EOF'
   [ {"ref": "bdns:812345", "verdict": "strong", "route": "apply", ...}, ... ]
   EOF
   ```
   Fix every entry the result lists under `errors`, then save again.
8. **Report.** Run `uv run fundhunt report --profile <name> --open`. It
   writes `data/reports/<name>-latest.html`, one self-contained file.
   - **Running on the user's machine** (desktop app or terminal): the page
     opens in their browser. If it doesn't, give them the path.
   - **Running in a cloud or remote sandbox** (Claude Code on the web,
     Codex cloud, a mobile app session): the user can't open your files.
     Hand them the HTML file through whatever file-sharing your
     environment offers (an attachment, a download link, an artifact).
     If there is none, say so plainly and summarise the results in chat
     instead.
9. **Summarise in chat** in a few lines:
   - how many strong and plausible calls there are, and the 3–5 best,
     each with its deadline;
   - anything urgent, i.e. a deadline within 15 days;
   - any source that failed.

   Then tell them how to send their marks back. The page has a guided
   tour, but say it once anyway:
   - **Local session:** "press *Download file* and tell me *import my
     decisions*";
   - **Cloud, web or mobile session:** "press *Copy for agent* and paste
     the text here".

Don't judge the whole corpus. The lexical top-N is the funnel; raise
`--top` only if the user asks for a wider net.

## C. Tune

Use the user's decisions as evidence:
- To read the user's marks and notes, run
  `uv run fundhunt decisions list --profile <name>`. Notes are the
  richest signal: they say *why*.
- To read past verdicts, run
  `uv run fundhunt candidates --profile <name> --all`. Every candidate
  carries `verdict_state`.
- If several dismissed calls share a theme, propose a `negative` term or
  a `not_interested_in` sentence.
- If good calls come in from a source the profile boosts too little, or
  the user says something is missing, propose `strong` or `core` terms.

Always show the change and get a yes before editing the profile. Any
profile change makes the existing verdicts stale, so the next run
re-judges the top candidates. Say so.

## D. Schedule

Only `sync` may run unattended. Judging needs you. Offer the user's
platform scheduler, running from the repo root:
- macOS / Linux: cron
  `30 6 * * * cd <repo> && uv run fundhunt sync >> data/sync.log 2>&1`,
  or a launchd agent.
- Windows: Task Scheduler.

Ask before installing anything.

## Rules

- Never invent facts about a call. If the stored fields and documents
  don't say it, it's unknown. Write "unknown" and lower the verdict, or
  ask in `next_step`.
- Never edit `src/`, the database or the reports by hand. The CLI is the
  interface.
- Never send the user's profile or documents anywhere except the public
  sources the CLI already talks to.
- Write in the profile's `language` (es/en) for `summary`, `rationale`
  and `next_step`.
- If a source keeps failing, follow its entry in `docs/sources.md` and
  tell the user. The Interreg search key in particular rotates.
