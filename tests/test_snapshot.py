import json
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from fundhunt import pipeline, snapshot
from fundhunt.models import Kind, Opportunity
from fundhunt.sources import SOURCES
from fundhunt.store import Store


def opp(source="bdns", sid="1", title="t", deadline=None):
    return Opportunity(source=source, source_id=sid, kind=Kind.GRANT, title=title,
                       deadline=deadline)


def iso(delta: timedelta) -> str:
    return (datetime.now(timezone.utc) + delta).isoformat(timespec="seconds")


def nightly(tmp_path, records, fresh=True) -> Store:
    """A corpus as the nightly job would have it: records plus a recent
    successful run for every source."""
    st = Store(tmp_path / "nightly.db")
    for o in records:
        st.upsert(o)
    for s in SOURCES:
        run = st.start_run(s)
        st.finish_run(run, ok=True, counts={})
    if not fresh:
        st.conn.execute("UPDATE source_runs SET started_at = ?", (iso(-timedelta(days=10)),))
    st.conn.execute("INSERT OR REPLACE INTO meta VALUES ('ted_countries', '[\"ES\"]')")
    st.commit()
    return st


def test_build_is_lean(tmp_path):
    old = datetime.now() - timedelta(days=200)
    st = nightly(tmp_path, [opp(sid="open"), opp(sid="long-closed", deadline=old)])
    st.conn.execute("UPDATE opportunities SET first_seen = ?", (iso(-timedelta(days=90)),))
    st.upsert(opp(sid="just-arrived", deadline=old))  # kept: BDNS skips known ids
    st.upsert(opp(sid="open", title="changed"))  # leaves a revision behind
    st.save_verdict("someone", {"ref": "bdns:open", "verdict": "strong"}, "h", "p")
    st.commit()
    res = snapshot.build(st, tmp_path / "dist")
    assert res["records"] == {"bdns": 2}
    assert set(res["runs"]) == set(SOURCES)

    db = tmp_path / "check.db"
    import gzip
    db.write_bytes(gzip.decompress((tmp_path / "dist" / snapshot.DB_ASSET).read_bytes()))
    c = sqlite3.connect(db)
    for table in ("revisions", "verdicts", "decisions", "matches"):
        assert c.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0


def test_pull_merges_and_keeps_personal_tables(tmp_path):
    published = tmp_path / "dist"
    snapshot.build(nightly(tmp_path, [opp(sid="a", title="new title"), opp(sid="b")]), published)

    st = Store()
    st.upsert(opp(sid="a", title="old title"))
    st.conn.execute("UPDATE opportunities SET last_changed = ?", (iso(-timedelta(days=3)),))
    st.upsert(opp(sid="mine"))  # only we have it: absence never closes it
    st.save_verdict("me", {"ref": "bdns:mine", "verdict": "strong"}, "h", "p")
    st.commit()

    res = snapshot.pull(st, str(published))
    assert (res["status"], res["new"], res["updated"]) == ("applied", 1, 1)
    assert st.get("bdns:a").title == "new title"
    assert st.get("bdns:mine") is not None
    assert st.conn.execute("SELECT COUNT(*) FROM revisions").fetchone()[0] == 1
    assert st.conn.execute("SELECT COUNT(*) FROM verdicts").fetchone()[0] == 1
    assert st.last_success("ted") is not None
    assert snapshot.pull(st, str(published))["status"] == "up to date"


def test_newer_local_record_wins(tmp_path):
    published = tmp_path / "dist"
    snapshot.build(nightly(tmp_path, [opp(sid="a", title="nightly")]), published)
    st = Store()
    st.upsert(opp(sid="a", title="mine, fetched later"))
    st.conn.execute("UPDATE opportunities SET last_changed = ?", (iso(timedelta(hours=1)),))
    st.commit()
    snapshot.pull(st, str(published))
    assert st.get("bdns:a").title == "mine, fetched later"


def test_checksum_mismatch_is_refused(tmp_path):
    published = tmp_path / "dist"
    snapshot.build(nightly(tmp_path, [opp()]), published)
    manifest = json.loads((published / snapshot.MANIFEST_ASSET).read_text())
    manifest["sha256"] = "0" * 64
    (published / snapshot.MANIFEST_ASSET).write_text(json.dumps(manifest))
    with pytest.raises(snapshot.SnapshotError):
        snapshot.pull(Store(), str(published))


def test_sync_skips_sources_a_fresh_snapshot_covers(tmp_path, monkeypatch):
    published = tmp_path / "dist"
    snapshot.build(nightly(tmp_path, [opp()]), published)
    monkeypatch.setenv("FUNDHUNT_SNAPSHOT", str(published))
    # no_network makes any direct fetch fail, so every source must be skipped
    res = pipeline.sync(Store(), log=lambda m: None)
    assert res["snapshot"]["status"] == "applied"
    assert all("covered by the nightly snapshot" in res[s]["skipped"] for s in SOURCES)


def test_stale_snapshot_falls_back_to_direct_sync(tmp_path, monkeypatch):
    published = tmp_path / "dist"
    snapshot.build(nightly(tmp_path, [opp()], fresh=False), published)
    monkeypatch.setenv("FUNDHUNT_SNAPSHOT", str(published))
    res = pipeline.sync(Store(), only=None, log=lambda m: None)
    assert res["snapshot"]["status"] == "applied"
    assert "skipped" not in res["bdns"]  # fetched directly (and refused by no_network)


def test_unreachable_snapshot_is_not_fatal(tmp_path, monkeypatch):
    monkeypatch.setenv("FUNDHUNT_SNAPSHOT", str(tmp_path / "nowhere"))
    res = pipeline.sync(Store(), only=None, log=lambda m: None)
    assert res["snapshot"]["status"] == "unavailable" and res["snapshot"]["ok"]


def test_sync_skips_closed_records_it_never_held(monkeypatch):
    past = datetime.now() - timedelta(days=3)
    future = datetime.now() + timedelta(days=30)
    st = Store()
    st.upsert(opp(source="placsp", sid="tracked", deadline=future))
    st.commit()
    feeds = {
        "placsp": [opp(source="placsp", sid="award-only", deadline=past),   # skipped
                   opp(source="placsp", sid="tracked", title="now closed", deadline=past),
                   opp(source="placsp", sid="fresh", deadline=future)],
        "bdns": [opp(source="bdns", sid="closed-call", deadline=past)],     # kept
    }
    monkeypatch.setattr(pipeline, "registry", lambda: {s: (lambda ctx, s=s: iter(feeds[s]))
                                                        for s in feeds})
    res = pipeline.sync(st, only=["placsp", "bdns"], log=lambda m: None)
    assert (res["placsp"]["skipped_closed"], res["placsp"]["new"], res["placsp"]["updated"]) == (1, 1, 1)
    assert st.get("placsp:award-only") is None
    assert st.get("placsp:tracked").title == "now closed"  # a held record still learns it closed
    assert st.get("bdns:closed-call") is not None


def test_build_drops_closed_records_except_bdns(tmp_path):
    past = datetime.now() - timedelta(days=3)
    resolved = opp(source="placsp", sid="resolved")
    resolved.status = "resuelta"  # closed by status, with no deadline
    st = nightly(tmp_path, [opp(source="placsp", sid="closed", deadline=past), resolved,
                            opp(source="placsp", sid="open"),
                            opp(source="bdns", sid="closed", deadline=past)])
    assert snapshot.build(st, tmp_path / "dist")["records"] == {"bdns": 1, "placsp": 1}
