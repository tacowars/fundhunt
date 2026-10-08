# Judging candidates

You screen one call at a time for **this applicant**, using only:
- the profile `brief`, and
- the candidate's fields or, after a deep read, its documents.

You are judging eligibility and how viable the call is for them, not how
good the call is in general.

## The verdict object

```json
{
  "ref": "placsp:2026/0412",
  "verdict": "strong",
  "route": "bid",
  "summary": "One sentence: what the CALL funds or buys, and for whom.",
  "rationale": "One or two sentences: why this verdict for this applicant.",
  "constraint_applied": null,
  "fit": 4,
  "key_constraints": ["Solvencia técnica: 3 contratos similares en 5 años",
                      "Lugar de ejecución: Bizkaia"],
  "next_step": "Pedir aclaración sobre el lote 2 antes del 14/11.",
  "deep_read": true,
  "judged_by": "<your agent / model name>"
}
```

Field rules:
- **`ref`**: copy it from the candidate exactly.
- **`verdict`**: one of three values.
  - **strong**: clearly eligible, a good thematic and capacity fit, and
    realistic before the deadline.
  - **plausible**: possibly worth it, but eligibility or fit can't be
    settled from what you have. Say what is missing in `rationale` or
    `next_step`.
  - **reject**: a hard constraint rules it out. `constraint_applied` is
    then **required**: the specific rule or fact, e.g. "Beneficiarios:
    solo personas físicas", "Lugar de ejecución fuera de las regiones del
    perfil", "Obra civil (CPV 45) — fuera de mercado".
- **`route`**: required for strong and plausible. It is the most
  realistic way in.
  - `apply`: apply for a grant directly.
  - `bid`: bid for a tender.
  - `partner`: join a consortium, or subcontract to the eligible
    applicant or bidder.
  - `advise_clients`: the call funds third parties the user can advise.
    These are leads, typical for consultancies.
  - `monitor`: nothing to do yet (forthcoming, or waiting for the
    documents).

  Only use a route that appears in `brief.routes`. If the only way in is
  a route the profile excludes, reject the call and say so.
- **`summary`**: describe the call itself, in the profile's language,
  even for English-language calls. Never describe the applicant here.
- **`fit`** (1–5): only after a deep read. 5 = made for them, 1 = barely
  relevant.
- **`key_constraints`**: hard facts from the documents that shape the
  play. For example: applicant type, territory, minimum turnover or
  solvency, consortium size, co-financing rate, maximum grant, eligible
  costs, and submission deadline and time.
- **`next_step`**: the user's concrete best move, in one sentence.

## Checks, in order

1. **Is it live?** Check `lifecycle` and `days_left`.
   - A deadline under about 10 days is only `strong` if the effort fits
     that time. Otherwise rate it `plausible` and say why.
   - `uncertain` means no deadline or status was found. Never assume the
     call is open; say so.
2. **Who can apply or bid?** Check `beneficiaries`, `eligible_countries`,
   the summary and, for tenders, the buyer. If the applicant's type
   (`brief.role`, `legal_form`, `size`) is excluded, reject the call.
   There is one exception: `partner` or `advise_clients` in
   `brief.routes` keeps it alive with that route.
3. **Where?** Check the territory restrictions against `brief.country`
   and `brief.regions`. Calls with national or EU scope pass.
4. **What?** Check the theme against `brief.who` and `brief.looking_for`.
   Anything in `brief.not_interested_in` is a reject.
5. **Can they deliver?**
   - Tender value against the capacity described in `brief.who`.
   - Grant ticket size, co-financing and consortium needs against their
     track record.
   - `budget` on a grant is the **call total** across all beneficiaries,
     not their ticket. Never reject a grant for being "too big" on that
     number alone.
6. **Near-duplicates.** `near_duplicates` lists sibling records, e.g. the
   same LEADER call per comarca, or the same tender on TED and PLACSP.
   Judge the representative record; you don't need to judge the siblings.

## Honesty rules

- **Use only what the fields and documents say.** If something decisive
  is unknown, say "unknown" and make the call `plausible` rather than
  `strong`. Name the question to resolve in `next_step`.
- **The lexical reasons are hints, not evidence.** A keyword hit doesn't
  make a call fit. A call with no hits can still fit, if you can see why.
- **Documents beat the stored summary.** After a deep read, ground
  `key_constraints` in what the documents say.
  - If `doc` returns `readable: false`, judge on the stored fields, set
    `deep_read: false` and mention it in `rationale`.
  - A `stale-record` candidate changed since your last verdict, so check
    what changed (`show <ref>`).
- **Be consistent across a run.** Similar calls get similar verdicts.
  When in doubt between two verdicts, pick the lower one and explain.

## Deep reads

`uv run fundhunt doc <ref>` returns up to 3 documents and about 60,000
characters of text. Read in this order:
1. who can apply;
2. what is funded or bought;
3. the amounts and co-financing;
4. territory;
5. evaluation criteria;
6. the deadline and how to submit.

For big documents, skim the first two documents' sections on
beneficiaries, eligible actions and requirements. You don't need to read
every page. Update the verdict, possibly up or down, then save it with
`deep_read: true`.
