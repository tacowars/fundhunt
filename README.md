<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/assets/logo-dark.svg">
    <img src="docs/assets/logo-light.svg" alt="fundhunt logo: an engraved hunting dog" width="160">
  </picture>
</p>

# fundhunt

**Encuentra subvenciones, ayudas y licitaciones públicas, españolas y
europeas, que encajan contigo.** Para autónomos, pymes, ayuntamientos,
asociaciones y quienes les asesoran. No hace falta saber informática:
tu asistente de IA lo instala y lo maneja por ti.

*Find Spanish and EU grants, aid and public tenders that fit you. Your AI
assistant installs and runs it for you. [English below](#get-started).*

## Empieza aquí

Necesitas un ordenador (Windows o Mac) y un asistente de IA que pueda
trabajar con archivos y programas en tu ordenador. Por ejemplo, la app de
escritorio de **Claude** con *Cowork* o *Claude Code*, o **ChatGPT** con
*Codex*. Abre una conversación y escribe:

> **Instala fundhunt desde https://github.com/tacowars/fundhunt y
> configúralo para mí.**

El asistente lo descarga, te pide permiso antes de instalar nada y luego
te hace unas pocas preguntas sobre ti o tu organización. También puede
leer tu web o un folleto. Con eso prepara tu perfil.

Después, cuando quieras resultados nuevos, dile:

> **Busca subvenciones y licitaciones para mí.**

Revisa las convocatorias, lee los documentos oficiales de las mejores y
te abre una página con los resultados. En esa página marcas cada una
como *me interesa*, *quizás* o *descartar*, y puedes añadir notas. Una
visita guiada te enseña cómo la primera vez. Luego envías tus marcas al
asistente con uno de los dos botones de la página. Así la próxima vez
acierta más.

Para tener la última versión, dile: **Actualiza fundhunt.**

## Get started

You need a computer (Windows or Mac) and an AI assistant that can work
with files and programs on it. For example, the **Claude** desktop app
with *Cowork* or *Claude Code*, or **ChatGPT** with *Codex*. Start a
conversation and say:

> **Install fundhunt from https://github.com/tacowars/fundhunt and set
> it up for me.**

The assistant downloads it, asks before installing anything, and then
asks you a few questions about you or your organisation. It can also
read your website or a brochure. From that it writes your profile.

After that, whenever you want fresh results, say:

> **Find grants and tenders for me.**

It goes through the calls, reads the official documents of the best
ones, and opens a results page. On the page you mark each call
*pursue*, *maybe* or *dismiss*, and add notes. A guided tour shows how
on first open. Then you send your marks back with one of the page's two
buttons, so the next run is sharper.

To get the latest version, say: **Update fundhunt.**

You can keep several profiles, for example your firm plus each client
you advise.

## For the assistant doing the install

Talk to the user in their language and in plain words: they may never
have used a terminal. Ask before installing anything.

1. **Choose the folder.** Default to a `fundhunt` folder in the user's
   Documents. In Cowork, use the folder the user shared with you.
2. **Get the code.** If `git` is available, clone
   `https://github.com/tacowars/fundhunt.git` into that folder.
   Otherwise download
   `https://github.com/tacowars/fundhunt/archive/refs/heads/main.zip`
   and extract the contents of its `fundhunt-main/` folder into it.
3. **Get uv** (it brings its own Python and needs no administrator
   rights). Check with `uv --version`. If it's missing, ask, then run:
   - Windows (PowerShell):
     `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`
   - macOS / Linux: `curl -LsSf https://astral.sh/uv/install.sh | sh`

   A shell started before the install may not find `uv` yet. Open a new
   one, or call it by its full path: `%USERPROFILE%\.local\bin\uv.exe` on
   Windows, `~/.local/bin/uv` elsewhere.
4. **Check it works.** From the folder, run `uv run fundhunt status`;
   the first run sets up the environment. Then run
   `uv run fundhunt sync`, which downloads the nightly data snapshot in
   seconds.
5. **Hand over to the skill.** Read `AGENTS.md`, then
   `skills/fundhunt/SKILL.md` in full, and start its workflow A
   (profile).

## How it works

```
 public sources ──nightly──▶ snapshot ──sync──▶ local SQLite ──rank──▶ shortlist ──agent judges──▶ results page
 (TED, BDNS, PLACSP,         (GitHub            data/fundhunt.db       (keywords,    (reads the calls,     you mark pursue /
  EU portal, Interreg…)       release)                                  codes, rules)  writes verdicts)     maybe / dismiss
```

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
  examples), your marks, the database and the reports never leave your
  computer. fundhunt only downloads: from the public sources above, and
  the nightly snapshot from GitHub.

## For technical users

Clone and run it yourself with [uv](https://docs.astral.sh/uv/):

```bash
git clone https://github.com/tacowars/fundhunt.git && cd fundhunt
uv run fundhunt status
```

Open the folder in any coding agent and say *"set up fundhunt for me"*.
It reads `AGENTS.md` and the skill in `skills/fundhunt/`. You can also
write `profiles/<you>.yaml` by hand: copy one of the
`profiles/example-*.yaml` files. Every field is explained in
[`profiles/README.md`](profiles/README.md).

### Without an agent

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

### Scheduling

Since `sync` pulls the nightly snapshot, a schedule is rarely needed. To
keep the database fresh between sessions anyway, schedule the sync with
cron, launchd or the Task Scheduler:

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
