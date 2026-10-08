"""SQLite storage: the corpus (shared by all profiles) plus per-profile
matches, agent verdicts and the user's review decisions.

Tables
- opportunities  current state, keyed (source, source_id), content-hashed
- revisions      append-only previous states when the content hash moves
- source_runs    one row per sync attempt per source (incremental windows)
- matches        lexical ranking per profile (rebuilt by `rank`)
- verdicts       the agent's judgment per profile, pinned to the record's
                 content hash and the profile hash it judged — a changed
                 record or profile makes the verdict stale, not wrong
- decisions      the user's pursue / maybe / dismiss marks from the report
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .models import Opportunity
from .settings import db_path as settings_db_path

SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS opportunities (
    source        TEXT NOT NULL,
    source_id     TEXT NOT NULL,
    kind          TEXT NOT NULL,
    indirect      INTEGER NOT NULL DEFAULT 0,
    title         TEXT NOT NULL,
    funder        TEXT,
    country       TEXT,
    status        TEXT,
    open_date     TEXT,
    deadline      TEXT,
    url           TEXT,
    budget_value  REAL,
    content_hash  TEXT NOT NULL,
    normalized    TEXT NOT NULL,
    first_seen    TEXT NOT NULL,
    last_seen     TEXT NOT NULL,
    last_changed  TEXT NOT NULL,
    PRIMARY KEY (source, source_id)
);
CREATE INDEX IF NOT EXISTS idx_opp_deadline ON opportunities(deadline);

CREATE TABLE IF NOT EXISTS revisions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    source        TEXT NOT NULL,
    source_id     TEXT NOT NULL,
    content_hash  TEXT NOT NULL,
    normalized    TEXT NOT NULL,
    superseded_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS source_runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    source      TEXT NOT NULL,
    started_at  TEXT NOT NULL,
    finished_at TEXT,
    ok          INTEGER NOT NULL DEFAULT 0,
    coverage    TEXT,            -- complete | partial (capped) | n/a
    counts      TEXT,            -- JSON {new, updated, unchanged}
    error       TEXT
);

CREATE TABLE IF NOT EXISTS matches (
    profile     TEXT NOT NULL,
    source      TEXT NOT NULL,
    source_id   TEXT NOT NULL,
    score       REAL NOT NULL,
    tier        INTEGER NOT NULL,
    indirect    INTEGER NOT NULL DEFAULT 0,
    reasons     TEXT NOT NULL,
    computed_at TEXT NOT NULL,
    PRIMARY KEY (profile, source, source_id)
);
CREATE INDEX IF NOT EXISTS idx_match_rank ON matches(profile, tier, score);

CREATE TABLE IF NOT EXISTS verdicts (
    profile       TEXT NOT NULL,
    source        TEXT NOT NULL,
    source_id     TEXT NOT NULL,
    content_hash  TEXT NOT NULL,
    profile_hash  TEXT NOT NULL,
    verdict       TEXT NOT NULL,   -- strong | plausible | reject
    route         TEXT,            -- apply | bid | partner | advise_clients | monitor
    fit           INTEGER,         -- 1-5, after a deep read
    summary       TEXT,
    rationale     TEXT,
    constraint_applied TEXT,
    key_constraints TEXT,          -- JSON list
    next_step     TEXT,
    deep_read     INTEGER NOT NULL DEFAULT 0,
    judged_by     TEXT,            -- free text: the agent/model that judged
    judged_at     TEXT NOT NULL,
    PRIMARY KEY (profile, source, source_id)
);

CREATE TABLE IF NOT EXISTS decisions (
    profile     TEXT NOT NULL,
    source      TEXT NOT NULL,
    source_id   TEXT NOT NULL,
    decision    TEXT NOT NULL,     -- pursue | maybe | dismiss
    note        TEXT,
    decided_at  TEXT NOT NULL,
    PRIMARY KEY (profile, source, source_id)
);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def split_ref(ref: str) -> tuple[str, str]:
    source, _, source_id = ref.partition(":")
    if not source or not source_id:
        raise ValueError(f"bad reference {ref!r}: expected '<source>:<id>'")
    return source, source_id


class Store:
    def __init__(self, path: Path | str | None = None):
        path = Path(path) if path else settings_db_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        # a scheduled sync and an agent session may overlap: WAL lets readers
        # run alongside the writer, and the timeout waits out short write locks
        self.conn = sqlite3.connect(path, timeout=60)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        if not self.conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='meta'").fetchone():
            self.conn.executescript(SCHEMA)
            self.conn.execute("INSERT OR IGNORE INTO meta VALUES ('schema_version', ?)",
                              (str(SCHEMA_VERSION),))
            self.conn.commit()

    def commit(self) -> None:
        self.conn.commit()

    # ---- corpus ------------------------------------------------------ #

    def upsert(self, opp: Opportunity) -> str:
        """Insert or update one opportunity: 'new' | 'updated' | 'unchanged'."""
        ts = now()
        new_hash = opp.content_hash()
        row = self.conn.execute(
            "SELECT content_hash, normalized FROM opportunities WHERE source=? AND source_id=?",
            (opp.source, opp.source_id)).fetchone()
        cols = (opp.kind.value, int(opp.indirect), opp.title, opp.funder,
                opp.country, opp.status,
                opp.open_date.isoformat() if opp.open_date else None,
                opp.deadline.isoformat() if opp.deadline else None,
                opp.url, opp.budget_value, new_hash, opp.model_dump_json())
        if row is None:
            self.conn.execute(
                """INSERT INTO opportunities (kind, indirect, title, funder, country,
                     status, open_date, deadline, url, budget_value, content_hash,
                     normalized, source, source_id, first_seen, last_seen, last_changed)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (*cols, opp.source, opp.source_id, ts, ts, ts))
            return "new"
        if row["content_hash"] == new_hash:
            self.conn.execute(
                "UPDATE opportunities SET last_seen=? WHERE source=? AND source_id=?",
                (ts, opp.source, opp.source_id))
            return "unchanged"
        self.conn.execute(
            """INSERT INTO revisions (source, source_id, content_hash, normalized, superseded_at)
               VALUES (?,?,?,?,?)""",
            (opp.source, opp.source_id, row["content_hash"], row["normalized"], ts))
        self.conn.execute(
            """UPDATE opportunities SET kind=?, indirect=?, title=?, funder=?, country=?,
                 status=?, open_date=?, deadline=?, url=?, budget_value=?, content_hash=?,
                 normalized=?, last_seen=?, last_changed=?
               WHERE source=? AND source_id=?""",
            (*cols, ts, ts, opp.source, opp.source_id))
        return "updated"

    def get(self, ref: str) -> Opportunity | None:
        source, source_id = split_ref(ref)
        row = self.conn.execute(
            "SELECT normalized FROM opportunities WHERE source=? AND source_id=?",
            (source, source_id)).fetchone()
        return Opportunity.model_validate_json(row["normalized"]) if row else None

    def content_hash(self, source: str, source_id: str) -> str | None:
        row = self.conn.execute(
            "SELECT content_hash FROM opportunities WHERE source=? AND source_id=?",
            (source, source_id)).fetchone()
        return row["content_hash"] if row else None

    def iter_opportunities(self, not_closed_before: str | None = None):
        """All records, optionally skipping ones whose deadline is before the
        given ISO date (cheap pre-filter; the lifecycle check is in rank)."""
        q = "SELECT normalized FROM opportunities"
        args: tuple = ()
        if not_closed_before:
            q += " WHERE deadline IS NULL OR deadline >= ?"
            args = (not_closed_before,)
        for row in self.conn.execute(q, args):
            yield Opportunity.model_validate_json(row["normalized"])

    def existing_ids(self, source: str) -> set[str]:
        return {r[0] for r in self.conn.execute(
            "SELECT source_id FROM opportunities WHERE source=?", (source,))}

    def stats(self) -> list[dict]:
        rows = self.conn.execute(
            """SELECT source, kind, COUNT(*) AS total,
                      SUM(CASE WHEN deadline >= datetime('now') THEN 1 ELSE 0 END) AS future_deadline
               FROM opportunities GROUP BY source, kind ORDER BY source""").fetchall()
        return [dict(r) for r in rows]

    # ---- sync bookkeeping -------------------------------------------- #

    def start_run(self, source: str) -> int:
        cur = self.conn.execute(
            "INSERT INTO source_runs (source, started_at) VALUES (?, ?)", (source, now()))
        self.commit()
        return cur.lastrowid

    def finish_run(self, run_id: int, *, ok: bool, counts: dict,
                   coverage: str | None = None, error: str | None = None) -> None:
        self.conn.execute(
            "UPDATE source_runs SET finished_at=?, ok=?, counts=?, coverage=?, error=? WHERE id=?",
            (now(), int(ok), json.dumps(counts), coverage, error, run_id))
        self.commit()

    def last_success(self, source: str) -> datetime | None:
        """Start time of the last complete, successful run of a source."""
        row = self.conn.execute(
            """SELECT started_at FROM source_runs WHERE source=? AND ok=1
                 AND coalesce(coverage, 'complete') != 'partial'
               ORDER BY started_at DESC LIMIT 1""", (source,)).fetchone()
        return datetime.fromisoformat(row["started_at"]) if row else None

    def runs(self, limit: int = 20) -> list[dict]:
        return [dict(r) for r in self.conn.execute(
            "SELECT * FROM source_runs ORDER BY id DESC LIMIT ?", (limit,))]

    # ---- per-profile ------------------------------------------------- #

    def replace_matches(self, profile: str, rows: list[tuple]) -> None:
        """rows: (source, source_id, score, tier, indirect, reasons_json)."""
        ts = now()
        self.conn.execute("DELETE FROM matches WHERE profile=?", (profile,))
        self.conn.executemany(
            """INSERT INTO matches (profile, source, source_id, score, tier, indirect,
                 reasons, computed_at) VALUES (?,?,?,?,?,?,?,?)""",
            [(profile, *r, ts) for r in rows])
        self.commit()

    def ranked(self, profile: str) -> list[sqlite3.Row]:
        """Lexical ranking joined with any verdict and decision."""
        return self.conn.execute(
            """SELECT m.score, m.tier, m.indirect AS match_indirect, m.reasons,
                      o.source, o.source_id, o.content_hash, o.normalized,
                      v.verdict, v.route, v.fit, v.summary, v.rationale,
                      v.constraint_applied, v.key_constraints, v.next_step,
                      v.deep_read, v.judged_by, v.judged_at,
                      v.content_hash AS v_content_hash, v.profile_hash AS v_profile_hash,
                      d.decision, d.note
               FROM matches m
               JOIN opportunities o ON o.source=m.source AND o.source_id=m.source_id
               LEFT JOIN verdicts v ON v.profile=m.profile AND v.source=m.source
                                   AND v.source_id=m.source_id
               LEFT JOIN decisions d ON d.profile=m.profile AND d.source=m.source
                                    AND d.source_id=m.source_id
               WHERE m.profile=?
               ORDER BY m.tier, m.score DESC, o.deadline IS NULL, o.deadline""",
            (profile,)).fetchall()

    def save_verdict(self, profile: str, v: dict, content_hash: str,
                     profile_hash: str) -> None:
        source, source_id = split_ref(v["ref"])
        self.conn.execute(
            """INSERT OR REPLACE INTO verdicts (profile, source, source_id, content_hash,
                 profile_hash, verdict, route, fit, summary, rationale, constraint_applied,
                 key_constraints, next_step, deep_read, judged_by, judged_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (profile, source, source_id, content_hash, profile_hash, v["verdict"],
             v.get("route"), v.get("fit"), v.get("summary"), v.get("rationale"),
             v.get("constraint_applied"),
             json.dumps(v.get("key_constraints") or [], ensure_ascii=False),
             v.get("next_step"), int(bool(v.get("deep_read"))), v.get("judged_by"), now()))

    def save_decision(self, profile: str, ref: str, decision: str,
                      note: str | None, decided_at: str | None = None) -> None:
        source, source_id = split_ref(ref)
        self.conn.execute(
            """INSERT OR REPLACE INTO decisions (profile, source, source_id, decision,
                 note, decided_at) VALUES (?,?,?,?,?,?)""",
            (profile, source, source_id, decision, note, decided_at or now()))
