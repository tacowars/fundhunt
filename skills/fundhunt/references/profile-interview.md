# Profile interview

Ask only what you can't infer from material the user gave you, such as a
website, brochure, CV or past applications. Ask one or two questions at a
time, in the user's language. Each question names the profile field it
fills.

1. **Who are you?** This fills `who.role` and `who.summary`.
   - Are you a company, a consultancy that also advises clients, a
     public body (ayuntamiento, diputación…), an NGO or association, a
     research group, or an individual?
   - What do you do, in two or three sentences?
2. **Size and form.** This fills `who.size`, `who.legal_form` and the
   capacity facts in `who.summary`.
   - Staff, and turnover if they want to share it.
   - Legal form: SL, SA, cooperativa, asociación, fundación, entidad
     local…
   - The largest project or contract you could take on.
3. **Where?** This fills `who.country`, `who.regions` and
   `eligibility.countries`.
   - Where are you based, and where do you work: province, region,
     national, EU?
   - Turn the answer into NUTS prefixes, e.g. Comunidad Valenciana =
     ES52, Andalucía = ES61, País Vasco = ES21, Madrid = ES30,
     Cataluña = ES51.
4. **What are you looking for?** This fills `looking_for.kinds` and
   `looking_for.routes`.
   - Grants and aid (subvenciones, ayudas), tenders (licitaciones), or
     both?
   - Would you join a consortium or subcontract (`partner`)?
   - Do you want leads for your clients (`advise_clients`)?
5. **Themes.** This fills `keywords.core`, `keywords.strong` and
   `looking_for.notes`.
   - What would a perfect call be about? Ask for 3–5 phrases.
   - Which adjacent topics would also interest you?
6. **What is never a fit?** This fills `not_interested_in` and
   `keywords.negative`. Ask for the kinds of call that look relevant but
   aren't, e.g. works contracts, equipment supply, or calls only for
   individuals.
7. **Track record.** This goes into `who.summary`. Have you won public
   funding or contracts before (CDTI, Horizon, LIFE, regional calls,
   public contracts)? It tells the judge how ambitious to be.
8. **Tenders only.** This fills `budget.*` and `cpv.include`.
   - What contract-value range suits you?
   - Which CPV codes do you usually bid under? Offer to infer them from
     the services they describe.
9. **Funders you know.** This fills `funders.terms`. Are there any
   programmes or agencies you already work with or want to favour?
10. **Language** (`language`). Should the results be in Spanish or
    English?

Before writing the file, read it back to the user as a short summary:
"You are… looking for… not interested in…". Then write it and run
`uv run fundhunt profile check <name>`.
