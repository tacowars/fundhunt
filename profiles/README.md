# Profiles

A profile is one YAML file, `profiles/<name>.yaml`, describing an
applicant and what to look for. You can keep several: your organisation,
each client you advise, or one per business line. Your profiles are
**git-ignored**; only the `example-*.yaml` files are tracked.

Start by copying the closest example:

| Example | For |
|---|---|
| [`example-sme.yaml`](example-sme.yaml) | a company that applies for grants and bids for tenders |
| [`example-consultancy.yaml`](example-consultancy.yaml) | a consultancy that also advises clients and joins consortia |
| [`example-ayuntamiento.yaml`](example-ayuntamiento.yaml) | a public body that applies for grants (no tenders) |

Or ask your agent: *"set up fundhunt for me"*.

Check a profile with `uv run fundhunt profile check <name>`.

## How a profile is used

There are two stages:

1. **Ranking (mechanical).** The keyword, code, funder, budget and source
   fields score every open call. The top `report.top` calls become
   candidates. This stage only has to get the right calls into the top
   few dozen.
2. **Judging (your agent).** The agent reads the candidates against the
   **prose**: `who.summary`, `looking_for.notes` and `not_interested_in`.
   Be specific and honest there: size, location, legal form, track
   record, what you can deliver. The prose decides what you see first.

Changing a profile marks its existing verdicts stale, so the next run
judges the top candidates again.

## Fields

### Top level

| Field | Meaning |
|---|---|
| `name` | Lowercase, hyphens, e.g. `acme-energia`. Should match the file name. |
| `language` | `es` or `en`: the language of the report and the agent's summaries. |

### `who`: the applicant

| Field | Meaning |
|---|---|
| `role` | `company`, `consultancy`, `public_body`, `ngo`, `research` or `individual`. A `public_body` is treated as a direct applicant for calls aimed at local authorities (e.g. EPAH). |
| `summary` | What you do, your size and capacity, and your track record. **The judge reads this.** |
| `country` | ISO code, default `ES`. |
| `regions` | NUTS prefixes you are based in or prefer, e.g. `[ES52]`. Regional calls elsewhere lose a point; they are never hidden. |
| `size` | `micro`, `small`, `medium`, `large` or `n/a`. |
| `legal_form` | Free text: SL, SA, asociación, fundación, entidad local… |

### `looking_for`

| Field | Meaning |
|---|---|
| `kinds` | `grant` (subvenciones, ayudas) and/or `tender` (licitaciones). |
| `routes` | Which ways in you accept (list below). |
| `notes` | Prose: what is worth pursuing. **The judge reads this.** |
| `min_days_to_deadline` | Calls closing sooner than this are skipped. Default 5. |

The routes:
- `apply`: apply for a grant;
- `bid`: bid for a tender;
- `partner`: join a consortium, or subcontract to the applicant or
  bidder;
- `advise_clients`: calls that fund your clients, i.e. leads;
- `monitor`: watch only.

When the routes include `partner` or `advise_clients`, calls you can't
apply to yourself stay in play.

### `not_interested_in`

Prose: what looks relevant but never is. **The judge reads this.**

### `eligibility`: hard filters

| Field | Meaning |
|---|---|
| `countries` | Records from other countries are dropped; EU-wide records pass. It also tells TED which buyers' countries to sync. |
| `interreg_country` | Interreg calls must list this country as eligible. Default `Spain`. |
| `beneficiary_tokens` | BDNS: if none of these appears in the call's beneficiary types, the call is flagged *indirect* (not dropped). Leave the list empty to never flag. |

Always dropped, for every profile: closed calls, and BDNS *concesión
directa – instrumental* records, which are nominative grants with nothing
to apply to.

### `keywords`: the lexical funnel

There are four groups, each with `weight`, `cap` (0 = no cap) and
`terms`:

| Group | Role |
|---|---|
| `core` | Your thesis. One hit puts the call in **tier A**. |
| `strong` | Adjacent niches. Two hits, or one hit plus a CPV/CNAE/funder match, gives **tier B**. |
| `context` | Broad words with a low weight and a cap. |
| `negative` | Never-a-fit markers. The weight must be negative. Matched against the title, summary and funder only, never against classification labels. |

How terms match:
- A term matches as a case-insensitive, accent-free substring:
  `"pobreza energetica"` matches *Pobreza Energética*.
- A term can be a prefix: `"sostenib"` matches *sostenible* and
  *sostenibilidad*.
- A hit in the title earns +1 extra.
- Write terms in every language the calls use: Spanish for BDNS and
  PLACSP, English for the EU sources.

Calls are sorted by tier, then score. The tier is a sort key only, never
a filter.

### Codes, funders, budget

| Field | Meaning |
|---|---|
| `cpv.include` / `cpv.exclude` | Tender CPV prefixes, e.g. `"722"` for software services. With `include_weight` / `exclude_weight` (±2). |
| `cnae.include` / `cnae.exclude` | BDNS sector (CNAE) prefixes. |
| `funders.terms` / `funders.weight` | Substrings of funder or programme names worth a bonus, e.g. `cdti`, `life`, `horizon`. |
| `budget.tender_sweet_min` / `tender_sweet_max` / `tender_sweet_weight` | Bonus for tenders in your value range. |
| `budget.tender_max` / `tender_over_max_weight` | Penalty for tenders above your capacity. Grant budgets are never scored: they are call totals. |

### `sources`

| Field | Meaning |
|---|---|
| `disabled` | Sources to ignore, e.g. `[ted, placsp]` for a public body. A source no profile uses is not synced at all. |
| `boost` | Per-source points, e.g. `{sedia_cascade: 2}`. |

Run `uv run fundhunt sources` for the list.

### `report`

| Field | Meaning |
|---|---|
| `top` | How many top-ranked calls the agent judges per run. Default 40. Already-judged, unchanged calls are skipped. |
| `deep_read` | How many of those get their official documents read. Default 10. |
