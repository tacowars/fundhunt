"""Profiles, ranking, verdicts, decisions and the report, end to end on a
synthetic corpus."""

import json
from datetime import date, datetime, timedelta

import pytest

from fundhunt import pipeline, profile, rank, report
from fundhunt.models import Classification, Kind, Opportunity, lifecycle
from fundhunt.store import Store

SOON = datetime.combine(date.today() + timedelta(days=40), datetime.min.time())


def opp(source="bdns", sid="1", kind=Kind.GRANT, title="t", **kw):
    return Opportunity(source=source, source_id=sid, kind=kind, title=title,
                       country="ES", deadline=kw.pop("deadline", SOON), **kw)


@pytest.fixture
def sme():
    return profile.load("example-sme")


@pytest.fixture
def store(isolated_home):
    st = Store()
    st.upsert(opp(sid="100", title="Ayudas para proyectos de visión artificial en la industria"))
    st.upsert(opp(sid="101", title="Subvención para obras de urbanización"))
    st.upsert(opp(source="placsp", sid="P-1", kind=Kind.TENDER,
                  title="Servicio de desarrollo de software de analítica de datos",
                  budget_value=120000,
                  classifications=[Classification(scheme="cpv", code="72200000")]))
    st.upsert(opp(sid="102", title="Visión artificial cerrada",
                  deadline=datetime(2020, 1, 1)))
    st.upsert(opp(sid="103", title="Convocatoria nominativa de inteligencia artificial",
                  raw={"tipoConvocatoria": "Concesión directa - instrumental"}))
    st.commit()
    return st


def test_examples_are_valid():
    for p in profile.list_profiles():
        assert profile.load(str(p)).name == p.stem


def test_profile_rejects_unknown_fields(tmp_path):
    bad = tmp_path / "x.yaml"
    bad.write_text("name: x\nwho: {role: company, summary: 'twenty characters at least'}\nnope: 1\n")
    with pytest.raises(Exception):
        profile.load(str(bad))


def test_lifecycle_never_assumes_open():
    assert lifecycle(opp(deadline=None)) == "uncertain"
    assert lifecycle(opp(deadline=None, status="cerrado")) == "closed"
    assert lifecycle(opp(deadline=datetime(2020, 1, 1))) == "closed"
    assert lifecycle(opp(open_date=date.today() + timedelta(days=3))) == "forthcoming"


def test_rank_tiers_and_exclusions(store, sme):
    counts = rank.run(store, sme)
    rows = {r["source_id"]: r for r in store.ranked(sme.name)}
    assert rows["100"]["tier"] == rank.TIER_A
    assert "102" not in rows and "103" not in rows  # closed, instrumental
    assert counts["excluded"] >= 1  # instrumental; closed is pre-filtered by deadline
    assert rows["P-1"]["tier"] == rank.TIER_B  # strong hit + CPV match
    if "101" in rows:  # negative term pushes works grants down
        assert rows["101"]["score"] < rows["100"]["score"]


def test_negative_terms_ignore_classification_labels(sme):
    r = rank.Ranker(sme)
    o = opp(title="Ayudas de inteligencia artificial",
            classifications=[Classification(scheme="cnae", code="81", label="Limpieza")])
    assert not any("negative" in x for x in r.score(o).reasons)


def test_verdicts_pin_hashes_and_go_stale(store, sme):
    rank.run(store, sme)
    first = pipeline.candidates(store, sme)
    refs = [c["ref"] for c in first["candidates"]]
    assert "bdns:100" in refs
    res = pipeline.save_verdicts(store, sme, [
        {"ref": "bdns:100", "verdict": "strong", "route": "apply",
         "summary": "Ayudas a proyectos de visión artificial.", "rationale": "Encaja con el núcleo."},
        {"ref": "bdns:101", "verdict": "reject", "summary": "Obras de urbanización.",
         "rationale": "No es su mercado."},  # missing constraint -> error
    ])
    assert res["saved"] == 1 and len(res["errors"]) == 1
    second = pipeline.candidates(store, sme)
    assert "bdns:100" not in [c["ref"] for c in second["candidates"]]
    # the record changes: its verdict becomes stale and it is offered again
    store.upsert(opp(sid="100", title="Ayudas para proyectos de visión artificial en la industria (corrección)"))
    store.commit()
    rank.run(store, sme)
    third = {c["ref"]: c for c in pipeline.candidates(store, sme)["candidates"]}
    assert third["bdns:100"]["verdict_state"] == "stale-record"


def test_decisions_import_and_dismissed_drop_out(store, sme, tmp_path):
    rank.run(store, sme)
    f = tmp_path / "fundhunt-decisions-example-sme-2026-10-08.json"
    f.write_text(json.dumps({"profile": "example-sme", "decisions": [
        {"ref": "bdns:100", "decision": "dismiss", "note": "ya presentado",
         "decided_at": "2026-10-08T10:00:00Z"}]}))
    payloads = pipeline.parse_decisions(f.read_text())
    res = pipeline.import_decisions(store, sme, payloads)
    assert res["applied"] == 1 and res["totals"] == {"dismiss": 1}
    assert pipeline.import_decisions(store, sme, payloads)["applied"] == 0  # idempotent
    assert "bdns:100" not in [c["ref"] for c in pipeline.candidates(store, sme)["candidates"]]


def test_report_renders_sections(store, sme):
    rank.run(store, sme)
    pipeline.save_verdicts(store, sme, [{
        "ref": "placsp:P-1", "verdict": "plausible", "route": "bid",
        "summary": "Desarrollo de software de analítica </script> para un ayuntamiento.",
        "rationale": "Encaja, pero falta la solvencia exigida."}])
    out = report.write(store, sme)
    page = open(out["latest"], encoding="utf-8").read()
    assert out["counts"]["plausible"] == 1
    assert "<\\/script>" in page  # embedded JSON cannot close the script tag
    assert page.count("</script>") == 1


def test_near_duplicates_collapse(isolated_home, sme):
    st = Store()
    for i in range(3):
        st.upsert(opp(sid=f"20{i}", title="Ayudas LEADER visión artificial comarca", funder="GDR"))
    st.commit()
    rank.run(st, sme)
    groups = pipeline.grouped(st, sme)
    assert len(groups) == 1 and len(groups[0]["variants"]) == 2


def test_report_sizing_does_not_stale_verdicts(sme):
    wider = sme.model_copy(update={"report": sme.report.model_copy(update={"top": 99})})
    assert wider.hash() == sme.hash()
    other = sme.model_copy(update={"not_interested_in": "otra cosa"})
    assert other.hash() != sme.hash()


def test_pasted_block_survives_chat_wrapping(store, sme):
    rank.run(store, sme)
    pasted = (
        "here are my marks!\n```\nFUNDHUNT-DECISIONS example-sme 2 marks\n"
        '{"profile":"example-sme","decisions":['
        '{"ref":"placsp:P-1","decision":"pursue","note":"llamar","decided_at":"2026-10-08T11:00:00Z"},'
        '{"ref":"bdns:100","decision":null,"note":"revisar bases","decided_at":"2026-10-08T11:01:00Z"}]}'
        "\n```\nthanks"
    )
    res = pipeline.import_decisions(store, sme, pipeline.parse_decisions(pasted))
    assert res["applied"] == 2 and res["totals"] == {"pursue": 1, "note": 1}
    with pytest.raises(ValueError):
        pipeline.parse_decisions("no block here")
