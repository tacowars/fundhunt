# A nightly shared corpus snapshot is the default way to get the data

- Status: Accepted
- Date: 2026-10-08
- Decision owners: tacowars
- Depends on: `local-first-agent-as-judge` (amends its points 1 and 2 and
  its "no shared corpus" consequence; this is the re-entry it anticipated)
- Evidence: measurements below; `src/fundhunt/snapshot.py`

## Context

`local-first-agent-as-judge` gave every clone its own crawl of the public
sources. In practice that has three costs:

- **Time to first result.** A first sync takes about 30 minutes, most of
  it BDNS fetching details one by one, and BDNS needs two or three more
  syncs to drain its backlog. That is a poor first experience for the
  intended users, who are not technical and will meet fundhunt through a
  chat with their agent.
- **Load on the sources.** Every clone fetches the same public records,
  so the traffic on the registries grows with the number of users, all
  for identical data.
- **Sandboxed agents.** Cloud and app sandboxes (Cowork, ChatGPT,
  Claude Code on the web) may start without the previous session's
  database, and may not be allowed to reach Spanish government hosts.
  GitHub is reachable almost everywhere.

The test round across agents and platforms would hit all three costs
again and again.

## Decision

1. **One public nightly job builds the corpus.** The GitHub Actions
   workflow `.github/workflows/snapshot.yml` runs early every morning,
   Spanish time, on GitHub-hosted runners. It is only ever triggered by
   its schedule or by hand, never by pull requests.
   - It continues from the previous snapshot (`fundhunt snapshot pull`),
     then runs `fundhunt sync --direct`, so the sources see one
     incremental visit a day.
   - With no profiles present, every source is synced and TED is fetched
     for Spain.
2. **The snapshot is lean** (`fundhunt snapshot build`).
   - It contains the corpus and each source's recent `source_runs`.
   - It leaves out the revision history and every per-profile table, so
     no verdict, decision or match is ever published.
   - Records whose deadline passed more than 60 days ago are pruned.
     Recently closed ones stay, because BDNS uses known ids to drain its
     backlog. Undated records unseen for a year are pruned too, so the
     nightly corpus doesn't grow without bound.
   - It is gzipped, and published with a JSON manifest (build time,
     schema version, sha256, record counts, the last good run per source
     and the TED countries).
3. **It is published as release assets, never committed.** The assets of
   the `snapshot` release are replaced every night. Git history doesn't
   grow, and GitHub's file-size limits for repositories don't apply.
4. **`fundhunt sync` pulls the snapshot first.**
   - It downloads the manifest. If the snapshot is newer than the one
     already applied, it downloads the snapshot, checks the sha256 and
     merges it into the local database.
   - The merge takes a snapshot record only when it changed more recently
     than the local copy. The old state goes to `revisions`, as in a
     direct sync. Records only the user has are kept, because absence
     never closes an opportunity. Per-profile tables are never touched.
   - Sources whose last nightly run is fresh are skipped: under 36 hours,
     or 8 days for weekly sources. For TED, the profile's countries must
     also be covered.
   - Every other source is synced directly, as before.
   - An unreachable or broken snapshot is never fatal: every source is
     synced directly instead.
   - `sync --direct` or `sync --source …` skips the snapshot.
     `FUNDHUNT_SNAPSHOT` points at a mirror, or `off` disables it.
5. **The local-first parts stand.** Profiles, verdicts, decisions,
   documents and reports stay on the user's machine. The snapshot only
   carries public data, and pulling it is keyless.

## Consequences

- Measured on the current corpus: the database is 87 MB on disk and
  31 MB after `VACUUM`. The lean snapshot is 4.7 MB gzipped (10.8k
  records), and merging it into an empty database takes under a second.
  A typical first sync drops from about 30 minutes to seconds.
- fundhunt now has one hosted component: a scheduled workflow. It costs
  nothing on a public repository. If the job fails, users' syncs fall
  back to direct fetching, so a failure in the job means more load and
  slower syncs, never lost data.
- GitHub disables scheduled workflows in public repositories after 60
  days without activity. Clients see that only as a stale snapshot,
  which they handle. The owner gets GitHub's failure and disable emails.
- The assets are replaced one by one, so a reader can briefly see a new
  manifest next to an old database. The checksum catches this, and the
  pull fails cleanly: the snapshot is reported as `unavailable` and
  every source is synced directly instead.
- Snapshot users get TED records for the snapshot's countries (Spain).
  Profiles that need other countries still fetch TED directly.
- Republishing public-sector data needs the sources' reuse terms to
  allow it with attribution. Spanish (RISP) and EU (Commission decision
  2011/833/EU) open-data rules generally do. Confirming each source's
  terms, and adding attribution to the release notes, is a follow-up.

## Re-entry

- **GitHub's runners blocked by a source.** If a Spanish source refuses
  them, move that source's nightly sync to a scheduled job on a machine
  in the EU. It would publish the release assets with a token scoped to
  this repository. A self-hosted Actions runner attached to this public
  repository is ruled out: fork pull requests could run code on it, and
  its host details would appear in the public logs.
- **A snapshot outgrowing GitHub releases**, or users needing more than
  one country of TED by default.
