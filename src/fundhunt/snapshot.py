"""The shared corpus snapshot: one nightly job syncs every source and
publishes the result, so users download a few megabytes instead of
re-crawling the same public registries (decision `nightly-corpus-snapshot`).

- `build` writes a lean, gzipped copy of the corpus plus a JSON manifest:
  no revision history, no per-profile tables, and records whose deadline
  passed long ago are pruned.
- `pull` fetches the manifest, downloads the snapshot when it is newer than
  the one already applied, checks its sha256 and merges it into the local
  database. Verdicts, decisions and matches are never touched.

A snapshot also carries each source's recent `source_runs`, so after a pull
a direct sync only fetches what changed since the nightly job ran.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import shutil
import sqlite3
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import http
from .settings import data_dir, snapshot_url
from .sources import KEEPS_UNKNOWN_CLOSED
from .store import SCHEMA_VERSION, Store, now

FORMAT = 1
DB_ASSET = "fundhunt-snapshot.db.gz"
MANIFEST_ASSET = "fundhunt-snapshot.json"
PRUNE_CLOSED_DAYS = 60     # closed this long ago and held this long: BDNS skips known ids,
                           # so a record pruned the day it arrived would be fetched again
PRUNE_UNDATED_DAYS = 365   # undated records (award notices) not seen for a year
RUNS_KEPT = 10             # recent source_runs per source

# A source counts as covered by the snapshot while its last nightly run is
# younger than this; weekly sources are polled less often by design.
FRESH = timedelta(hours=36)
FRESH_WEEKLY = timedelta(days=8)


# ---------------------------------------------------------------- build -- #

def build(store: Store, out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    built_at = now()
    # closed records of these sources are never fetched again unless held,
    # so the snapshot can drop them as soon as their deadline passes
    keeps = ", ".join(f"'{s}'" for s in sorted(KEEPS_UNKNOWN_CLOSED))
    with tempfile.TemporaryDirectory() as tmp:
        lean = Path(tmp) / "snapshot.db"
        store.commit()
        store.conn.execute("VACUUM INTO ?", (str(lean),))
        db = sqlite3.connect(lean)
        db.executescript(f"""
            DELETE FROM revisions; DELETE FROM matches;
            DELETE FROM verdicts; DELETE FROM decisions;
            DELETE FROM meta WHERE key = 'snapshot';
            DELETE FROM opportunities
             WHERE (source NOT IN ({keeps}) AND deadline < datetime('now'))
                OR (deadline < datetime('now', '-{PRUNE_CLOSED_DAYS} days')
                    AND first_seen < datetime('now', '-{PRUNE_CLOSED_DAYS} days'))
                OR (deadline IS NULL AND last_seen < datetime('now', '-{PRUNE_UNDATED_DAYS} days'));
            DELETE FROM source_runs WHERE id NOT IN (
                SELECT id FROM (SELECT id, row_number() OVER (
                    PARTITION BY source ORDER BY started_at DESC) AS n FROM source_runs)
                WHERE n <= {RUNS_KEPT});
        """)
        db.execute("INSERT OR REPLACE INTO meta VALUES ('snapshot_built_at', ?)", (built_at,))
        db.commit()
        countries = json.loads(_meta(db, "ted_countries") or '["ES"]')
        records = dict(db.execute(
            "SELECT source, COUNT(*) FROM opportunities GROUP BY source ORDER BY source"))
        runs = _latest_runs(db)
        db.execute("VACUUM")
        db.close()

        dest = out_dir / DB_ASSET
        with open(lean, "rb") as src, gzip.open(dest, "wb", compresslevel=9) as gz:
            shutil.copyfileobj(src, gz)
    manifest = {
        "format": FORMAT, "schema_version": SCHEMA_VERSION, "built_at": built_at,
        "file": DB_ASSET, "bytes": dest.stat().st_size, "sha256": _sha256(dest),
        "ted_countries": countries, "records": records, "runs": runs,
    }
    (out_dir / MANIFEST_ASSET).write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return {"snapshot": str(dest), "manifest": str(out_dir / MANIFEST_ASSET), **manifest}


# ----------------------------------------------------------------- pull -- #

def pull(store: Store, base: str | None = None, force: bool = False) -> dict:
    """Download and merge the published snapshot if it is newer than ours."""
    base = base or snapshot_url()
    if not base:
        raise SnapshotError("the snapshot is disabled (FUNDHUNT_SNAPSHOT=off)")
    base = base.rstrip("/")
    manifest = json.loads(_fetch(f"{base}/{MANIFEST_ASSET}"))
    if manifest.get("format") != FORMAT or manifest.get("schema_version") != SCHEMA_VERSION:
        raise SnapshotError(
            f"published snapshot is format {manifest.get('format')} / schema "
            f"{manifest.get('schema_version')}; this fundhunt reads {FORMAT} / "
            f"{SCHEMA_VERSION}. Update fundhunt.")
    current = applied(store)
    age = _age(manifest["built_at"])
    if current and not force and current["built_at"] >= manifest["built_at"]:
        return {"ok": True, "status": "up to date", "built_at": manifest["built_at"],
                "age_hours": round(age.total_seconds() / 3600, 1)}
    tmp_dir = data_dir() / "tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=tmp_dir) as tmp:
        gz = Path(tmp) / DB_ASSET
        gz.write_bytes(_fetch(f"{base}/{manifest['file']}"))
        if _sha256(gz) != manifest["sha256"]:
            raise SnapshotError("snapshot checksum mismatch (it may be mid-upload); try again later")
        db = Path(tmp) / "snapshot.db"
        with gzip.open(gz, "rb") as src, open(db, "wb") as out:
            shutil.copyfileobj(src, out)
        counts = merge(store, db)
    info = {k: manifest[k] for k in ("built_at", "ted_countries", "runs")}
    store.conn.execute("INSERT OR REPLACE INTO meta VALUES ('snapshot', ?)", (json.dumps(info),))
    store.commit()
    return {"ok": True, "status": "applied", "built_at": manifest["built_at"],
            "age_hours": round(age.total_seconds() / 3600, 1), **counts}


def merge(store: Store, snapshot_db: Path) -> dict:
    """Merge a snapshot's corpus into the local database. A record the
    snapshot changed more recently replaces ours (the old state goes to
    revisions, as in a direct sync); records only we have are kept, since
    absence never closes an opportunity."""
    c = store.conn
    store.commit()
    c.execute("ATTACH DATABASE ? AS snap", (str(snapshot_db),))
    try:
        with c:
            before = c.execute("SELECT COUNT(*) FROM opportunities").fetchone()[0]
            newer = """FROM snap.opportunities s WHERE s.source = o.source
                         AND s.source_id = o.source_id AND s.content_hash != o.content_hash
                         AND s.last_changed > o.last_changed"""
            c.execute(f"""INSERT INTO revisions (source, source_id, content_hash, normalized,
                            superseded_at)
                          SELECT o.source, o.source_id, o.content_hash, o.normalized, ?
                          FROM opportunities o WHERE EXISTS (SELECT 1 {newer})""", (now(),))
            updated = c.execute("""
                UPDATE opportunities AS o SET kind=s.kind, indirect=s.indirect, title=s.title,
                    funder=s.funder, country=s.country, status=s.status, open_date=s.open_date,
                    deadline=s.deadline, url=s.url, budget_value=s.budget_value,
                    content_hash=s.content_hash, normalized=s.normalized,
                    last_changed=s.last_changed
                FROM snap.opportunities s WHERE s.source = o.source AND s.source_id = o.source_id
                    AND s.content_hash != o.content_hash AND s.last_changed > o.last_changed
                """).rowcount
            c.execute("""UPDATE opportunities AS o SET last_seen = s.last_seen
                         FROM snap.opportunities s WHERE s.source = o.source
                           AND s.source_id = o.source_id AND s.last_seen > o.last_seen""")
            c.execute("INSERT OR IGNORE INTO opportunities SELECT * FROM snap.opportunities")
            new = c.execute("SELECT COUNT(*) FROM opportunities").fetchone()[0] - before
            c.execute("""INSERT INTO source_runs (source, started_at, finished_at, ok, coverage,
                           counts, error)
                         SELECT s.source, s.started_at, s.finished_at, s.ok, s.coverage,
                                json_set(coalesce(s.counts, '{}'), '$.via', 'snapshot'), s.error
                         FROM snap.source_runs s WHERE NOT EXISTS (
                           SELECT 1 FROM source_runs r WHERE r.source = s.source
                             AND r.started_at = s.started_at)""")
    finally:
        c.execute("DETACH DATABASE snap")
    return {"new": new, "updated": updated}


# --------------------------------------------------------------- status -- #

def applied(store: Store) -> dict | None:
    raw = _meta(store.conn, "snapshot")
    return json.loads(raw) if raw else None


def covered(store: Store, countries: list[str], weekly: set[str]) -> dict[str, str]:
    """Sources the applied snapshot keeps fresh enough to skip a direct sync,
    mapped to the time of the nightly run that covered them."""
    snap = applied(store)
    if not snap:
        return {}
    out = {}
    for source, run in snap.get("runs", {}).items():
        if not run.get("last_ok"):
            continue
        if source == "ted" and not set(countries) <= set(snap.get("ted_countries") or []):
            continue  # TED is fetched per country; the snapshot only has some
        if _age(run["last_ok"]) < (FRESH_WEEKLY if source in weekly else FRESH):
            out[source] = run["last_ok"]
    return out


# -------------------------------------------------------------- helpers -- #

class SnapshotError(RuntimeError):
    pass


def _fetch(url: str) -> bytes:
    if "://" not in url:  # a local directory (tests, or a mirror on disk)
        return Path(url).read_bytes()
    with http.client(timeout=120) as c:
        return http.request(c, "GET", url).content


def _latest_runs(db) -> dict:
    """Per source: when its last successful run started and how complete it was."""
    out = {}
    for source, started, coverage in db.execute(
            """SELECT source, started_at, coverage FROM source_runs WHERE ok = 1
               AND started_at = (SELECT max(started_at) FROM source_runs r
                                 WHERE r.source = source_runs.source AND r.ok = 1)"""):
        out[source] = {"last_ok": started, "coverage": coverage}
    return out


def _meta(conn, key: str) -> str | None:
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row[0] if row else None


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _age(iso: str) -> timedelta:
    return datetime.now(timezone.utc) - datetime.fromisoformat(iso)
