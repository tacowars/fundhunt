<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/assets/logo-dark.svg">
    <img src="docs/assets/logo-light.svg" alt="fundhunt logo: an engraved hunting dog" width="160">
  </picture>
</p>

# fundhunt

Find EU and Spanish **grants and aid (subvenciones, ayudas)** and **public
tenders (licitaciones)** that fit *you*: a company, a consultancy, a public
body, an NGO or a research group. It runs on your own machine. You don't
write any code: you fill in a profile, and your coding agent (Claude Code,
OpenAI Codex, Cowork or similar) does the rest.

```
 public sources ──sync──▶ local SQLite ──rank──▶ shortlist ──agent judges──▶ HTML results page
 (TED, BDNS, PLACSP,      data/fundhunt.db       (keywords,    (reads the calls,     you mark pursue /
  EU portal, Interreg…)                           codes, rules)  writes verdicts)     maybe / dismiss
```

## Quick start

1. Install [uv](https://docs.astral.sh/uv/getting-started/installation/)
   (it brings its own Python), then clone:
   ```bash
   git clone https://github.com/tacowars/fundhunt.git && cd fundhunt
   ```
2. Open the folder in your agent and say:
   > **Set up fundhunt for me.**

   The agent interviews you, or reads your website or brochure, and writes
   `profiles/<you>.yaml`. You can also copy one of the
   `profiles/example-*.yaml` files and edit it by hand. Every field is
   explained in [`profiles/README.md`](profiles/README.md).
3. Then, whenever you want fresh results:
   > **Run fundhunt for &lt;profile&gt;.**

   The agent syncs the sources and ranks the corpus. It judges the top
   candidates against your profile, reads the official documents of the
   best ones, and opens a results page in your browser.
4. On the page, mark each call *pursue / maybe / dismiss* and add notes.
   A short guided tour shows how on first open. Then send your marks
   back to the agent:
   - **Download file** if your agent runs on this computer. It finds the
     file in Downloads by itself; just say *"import my decisions"*.
   - **Copy for agent** if it runs in the cloud, in a web or mobile app,
     or can't see your files. Paste the copied text into the chat.

   Dismissed calls stay out of the way next time, and your notes guide
   the agent when it suggests changes to your profile.

You can keep as many profiles as you like, e.g. your firm plus each
client you advise. They share one database.

**Syncing takes seconds.** A public job rebuilds the data from every
source each night and publishes it as a
[snapshot](https://github.com/tacowars/fundhunt/releases/tag/snapshot)
of a few megabytes. Your copy downloads that instead of crawling the
registries itself, which also keeps the load on the public sources to
one visit a day. If the snapshot is missing or out of date, fundhunt
fetches from the sources directly. A first direct sync takes about 30
minutes, and later ones a few minutes.

## What it covers

| Source | What | Access |
|---|---|---|
| `ted` | EU tenders from buyers in your profile countries | official TED v3 API |
| `bdns` | Spanish public grants and aid (BDNS / SNPSAP, incl. CDTI) | official API |
| `placsp` | Spanish public procurement (national + aggregated regional platforms) | official Atom/CODICE feeds |
| `sedia` | EU Funding & Tenders portal topics (Horizon Europe, LIFE, Digital Europe…) | the portal's own search API (undocumented) |
| `sedia_cascade` | Cascade / FSTP calls run by EU-funded projects | same API |
| `interreg` | Calls of every Interreg programme | interreg.eu's public search index |
| `epah` | Energy Poverty Advisory Hub calls for local authorities | newsroom page |

Every source is public and needs no key. The last three depend on
unofficial interfaces that can change without notice; when one breaks,
the sync reports it and the others carry on. See
[`docs/sources.md`](docs/sources.md).

## Costs and privacy

- **No API keys and no LLM bill.** The judging is done by the agent you
  already use, under your own subscription. Verdicts are cached against
  each record's content, so only new or changed calls are judged again.
- **Everything stays local.** Your profiles (`profiles/*.yaml`, except the
  examples), the database and the reports are git-ignored. fundhunt only
  talks to the public sources above.

## Without an agent

Every step is a plain command that prints JSON:

```bash
uv run fundhunt status
uv run fundhunt sync
uv run fundhunt rank --profile acme
uv run fundhunt candidates --profile acme
uv run fundhunt report --profile acme --open
```

Without verdicts the page still shows the lexical ranking, under *Not yet
reviewed*.

## Scheduling

To keep the database fresh between sessions, schedule the sync with cron,
launchd or the Task Scheduler. Your agent can set this up ("schedule a
daily fundhunt sync"):

```cron
30 6 * * *  cd /path/to/fundhunt && uv run fundhunt sync >> data/sync.log 2>&1
```

Judging always happens in an agent session, never unattended.

## Licence

[AGPL-3.0-or-later](LICENSE). You may use, study, modify and share
fundhunt. If you distribute it, or offer a modified version as a network
service, you must publish your source under the same licence.

## Contributing

See [`AGENTS.md`](AGENTS.md) (it applies to humans too). Decisions are
logged in [`docs/log/`](docs/log/) and [`docs/adr/`](docs/adr/).
Run `bash scripts/setup-dev.sh` once before committing.
