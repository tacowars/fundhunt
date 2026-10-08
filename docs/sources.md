# Sources: endpoints, quirks and repair notes

Every source is public and keyless. The obligation is fair use: an
identifying User-Agent (`src/fundhunt/http.py`), paced requests and
incremental windows. The table gives the adapter file and dedup key for
each source.

| Source | Adapter | Dedup key | Poll style |
|---|---|---|---|
| `ted` | `sources/ted.py` | `procedure-identifier`, else publication number | window by publication date; open stock on first run |
| `bdns` | `sources/bdns.py` | `numeroConvocatoria` | list window + per-record detail, capped and draining |
| `placsp` | `sources/placsp.py` | `ContractFolderID` | Atom chain walked back to the window cutoff |
| `sedia` | `sources/sedia.py` | topic `identifier` | full state (open + forthcoming) every run |
| `sedia_cascade` | `sources/sedia.py` | competitive-call portal id | full state (future deadlines) every run |
| `interreg` | `sources/interreg.py` | Algolia `objectID` | full state every run |
| `epah` | `sources/epah.py` | newsroom slug | full state, at most weekly |

Common rules:
- **Incremental windows.** A run covers the days since the last
  *complete* successful run, plus one day of overlap, capped at 30.
- **Conservative absence.** A record vanishing from a feed never closes
  it; only its deadline or explicit status does (`models.lifecycle`).
- **Partial runs.** When a cap bites, the run is recorded as `partial`
  and the next run starts from the same point.

## TED: EU tenders (stable)

- **Endpoint.** `POST https://api.ted.europa.eu/v3/notices/search`, JSON
  in and out. The failover host is `tedweb.api.ted.europa.eu`.
- **Query syntax.** Expert query with eForms field names, e.g.
  `(buyer-country IN (ESP)) AND (publication-date >= 20261001) SORT BY publication-number DESC`.
  The sort goes inside the query string; `sortField` in the body is
  rejected with a 400.
- **Field names.** An unknown field name in `fields` rejects the *whole*
  request with a 400. The error lists every supported field, so check
  there before adding one.
- **Sort order.** The sort must be a unique total order. The day-granular
  `publication-date` sort made ITERATION pages unstable, with about 1%
  of notices dropped or shifted per pass. `publication-number` is
  unique.
- **Pagination.** `paginationMode: ITERATION` with `iterationNextToken`,
  250 per page, 0.5 s between pages. Bursts drew nginx 429s.
- **Shape.**
  - `notice-title` and `buyer-name` are dicts keyed by three-letter
    language code, and `buyer-name` values are lists.
  - `deadline-receipt-tender-date-lot` is per lot, so it is a list.
- **Dedup.** `procedure-identifier` is absent on pre-2023 notices, which
  fall back to the publication number. Corrigenda share the procedure id,
  so the highest publication number wins.
- **Same tender in two registries.** TED reuses the PLACSP platform UUID
  as the procedure id. The report collapses those twins (`rank.crossref`).
- **First run.** Every notice whose deadline (any lot) is in the future
  for the profile countries. Spain alone is about 2,000–3,000 notices.

## BDNS / SNPSAP: Spanish grants and aid (stable)

- **List.** `GET https://www.infosubvenciones.es/bdnstrans/api/convocatorias/busqueda`
  takes Spring-style params (`page`, `pageSize`, `order=fechaRecepcion`,
  `direccion=desc`) and returns a Spring `Page` envelope.
  - `totalElements` counts the whole database (650k+), so don't reconcile
    against it.
  - List records are shallow: id, `numeroConvocatoria`, descripción,
    `fechaRecepcion`, órgano levels.
- **Detail.** `GET …/api/convocatorias?numConv=<n>` returns the full
  record, with these fields:
  - `fechaInicioSolicitud` / `fechaFinSolicitud`, sometimes only as
    free text in `textInicio` / `textFin`;
  - `abierto`, `presupuestoTotal`, `tipoConvocatoria`;
  - `tiposBeneficiarios`;
  - `sectores`: **CNAE codes, not CPV**;
  - `regiones` (NUTS);
  - `documentos`.
- **No "open" filter on the server.** Openness is only knowable from the
  detail record.
- **Instrumental records.** `tipoConvocatoria = "Concesión directa -
  instrumental"` records are nominative grants with nothing to apply to.
  They are always excluded at rank time and were most of the corpus.
- **Pacing.** No rate limits are documented: 0.25 s between details and
  600 details per run (2,500 on the first run). Unstored records are
  fetched first, so a backlog drains over runs.
- **Documents.** For a deep read, take `documentos[].id` from the detail
  and fetch `…/convocatorias/documentos?idDocumento=<id>`. That returns
  octet-stream content; sniff for `%PDF`.
- **Fair use.** Every response carries an `advertencia` about reuse
  conditions. Keep the identifying User-Agent.

## PLACSP: Spanish public procurement (stable, behind a moody WAF)

- **Feeds.** Atom feeds with CODICE XML embedded per entry:
  - `/sindicacion/sindicacion_643/licitacionesPerfilesContratanteCompleto3.atom`
    (national profiles);
  - `/sindicacion/sindicacion_1044/PlataformasAgregadasSinMenores.atom`
    (aggregated regional and local platforms).
- **Hosts.** `contrataciondelestado.es` sits behind an **intermittent
  F5/Shape bot challenge** that returns HTML even on HTTP 200. The
  official mirror `contrataciondelsectorpublico.gob.es` serves the same
  `/sindicacion/` tree, so the adapter prefers the mirror and fails over
  per page.
  - Feed-internal `rel=next` links are absolute URLs on the primary host
    and are rewritten.
  - Entry deeplinks (`detalle_licitacion`) stay on the primary host: the
    mirror redirects `/wps/*` back.
- **Parsing.** Use lxml with a namespace map. feedparser flattens
  repeated CODICE elements lossily.
- **Re-emission.** The whole licitación is re-emitted on every field
  change. Feeds are newest-first, so the first occurrence per
  `ContractFolderID` in a walk is the newest.
- **Documents.** The feed carries attachment URLs inline
  (`Legal/Technical/AdditionalDocumentReference`). Those are captured as
  `documents` and used for the deep read, which avoids the WAF-guarded
  detail page. For some regional aggregators the feed URI is the only
  usable fetch path.
- **Status codes.** `PRE` anuncio previo, `PUB` en plazo, `EV`
  evaluación, `ADJ` adjudicada, `RES` resuelta, `ANUL` anulada.
- **Repair.** If both hosts fail for several days, check whether the
  `/sindicacion/` paths moved. The current feed index is linked from the
  platform's "Datos abiertos" page.

## SEDIA: EU Funding & Tenders portal (works, undocumented)

- **Endpoint.** `POST https://api.tech.ec.europa.eu/search-api/prod/rest/search?apiKey=SEDIA&text=***`
  with a **multipart form** body: `query` (Elasticsearch-style bool
  JSON), `languages` and `sort`. Every metadata value is a **list of
  strings**.
- **Filter codes** (undocumented, mapped empirically):
  - `status`: 31094501 forthcoming, 31094502 open, 31094503 closed.
  - `type`: 1 and 2 are grant topics (2 is EuropeAid), **8 is cascade
    calls**, 0 is EU-institution tenders, 3 is portal pages, 6 is topic
    updates.
- **Paging.** Use the cursor, not page numbers. The API re-executes the
  query per page and its replicas disagree on order, so a `pageNumber`
  walk re-serves and loses documents under every sort field. fundhunt
  pages with an `es_SortDate` range cursor:
  - each request asks for documents strictly after the watermark;
  - only complete date tie-blocks advance the watermark;
  - `pageSize` is capped at 100;
  - sorting by a field silently drops documents that lack it.
- **Duplicates.** The index holds duplicate documents per topic, so the
  adapter dedups by identifier with a deterministic winner.
- **Cascade (type 8).** `status` is stale on these records, so filter by
  `deadlineDate >= now` and re-check client-side: multi-cutoff calls
  carry several deadlines. Not every cascade call is published on the
  portal; portal coverage is the 90% solution.
- **Documents.** For a deep read, fetch
  `https://ec.europa.eu/info/funding-tenders/opportunities/data/topicDetails/<id lowercased>.json`.
  - Uppercase ids now 404.
  - Its HTML blobs (`description`, `conditions`) hold the call text, and
    the `call-fiche` PDF is linked from inside them.
  - EuropeAid topics sit behind an EU login and degrade to stored fields.
- **Repair.** If the endpoint starts rejecting requests, compare against
  the portal's own network traffic on the search page. The
  `apiKey=SEDIA` and `text=***` parameters are what the portal sends.

## Interreg: all Interreg programmes (fragile: rotating key)

- **Endpoint.** interreg.eu's call search is an Algolia widget fed by
  keep.eu, queried with the public frontend credentials:
  - app `2E032DRCNS`;
  - index `prod_en-us_content`;
  - filter `contentType:callForProjectsPage AND (callStatus:Open OR callStatus:Forthcoming)`.
- **Hits.** Structured: open and deadline dates, status, eligible
  countries and NUTS, themes, target audience, and the programme's own
  call page (`callExternalUrl`).
- **Repair (HTTP 403 or 404).** The search key rotated.
  1. Open https://interreg.eu/calls-for-projects/ in a browser.
  2. Find the request to `*.algolia.net` in the developer tools' network
     tab.
  3. Copy `x-algolia-api-key` (and the application id if it changed)
     into `ALGOLIA_PARAMS` in `sources/interreg.py`.

  This is the one documented case where a user's agent may edit code.
  Tell the user, and suggest opening an issue upstream.
- **Fallbacks, not implemented.** Programme sites mostly run WordPress
  with open `wp-json/wp/v2/posts`. keep.eu has an official API that
  needs registration.

## EPAH: Energy Poverty Advisory Hub (fragile: HTML scrape)

- **Endpoint.** `https://energy-poverty.ec.europa.eu/newsroom/news`, a
  server-rendered EC Drupal page with no RSS. The adapter keeps items
  whose title mentions a call, technical assistance or open applications.
- **Cadence.** The call cycle is annual, so the adapter polls weekly.
- **Indirect funding.** These calls fund *local authorities*. Records are
  flagged `indirect`, which is a lead for companies and consultancies,
  except for `role: public_body` profiles, which apply directly.
- **Repair.** If no items appear for months, check whether the newsroom
  URL or its link markup (`/newsroom/news/<slug>`) changed.
