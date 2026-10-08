"""Adapter normalization against recorded public payloads (no network)."""

from datetime import datetime

from lxml import etree

from conftest import FIXTURES, fixture_json
from fundhunt.models import Kind
from fundhunt.sources import bdns, epah, interreg, placsp, sedia, ted


def test_ted_normalizes_notices():
    notices = fixture_json("ted_search.json")["notices"]
    opps = [ted.normalize(n) for n in notices]
    assert opps and all(o.kind is Kind.TENDER and o.source == "ted" for o in opps)
    assert all(o.title for o in opps)
    assert any(o.classifications for o in opps)
    assert all(o.country in (None, "ES") for o in opps)


def test_ted_publication_key_orders_by_year_then_sequence():
    assert ted._pub_key("1-2026") > ted._pub_key("99999-2025")


def test_bdns_detail():
    o = bdns.normalize(fixture_json("bdns_detail.json"))
    assert o.kind is Kind.GRANT and o.country == "ES"
    assert o.source_id.isdigit()
    assert o.url
    assert "tiposBeneficiarios" in o.raw


def test_placsp_entries_and_documents():
    root = etree.fromstring((FIXTURES / "placsp.atom").read_bytes())
    opps, done, _next = placsp.parse_page(root, datetime(2000, 1, 1).astimezone())
    assert len(opps) == 3 and not done
    assert all(o.kind is Kind.TENDER and o.source_id for o in opps)
    assert all(d.role in {"legal", "technical", "additional"} for o in opps for d in o.documents)


def test_placsp_cutoff_stops_walk():
    root = etree.fromstring((FIXTURES / "placsp.atom").read_bytes())
    opps, done, _ = placsp.parse_page(root, datetime(2100, 1, 1).astimezone())
    assert opps == [] and done


def test_placsp_host_swap():
    url = "https://contrataciondelestado.es/sindicacion/x.atom"
    assert placsp._swap_host(placsp._swap_host(url)) == url
    assert "sectorpublico" in placsp._to_mirror(url)


def test_sedia_topics():
    results = fixture_json("sedia_search.json")["results"]
    opps = [o for o in (sedia.topic_from_result(r) for r in results) if o]
    assert opps and all(o.source == "sedia" and o.kind is Kind.GRANT for o in opps)
    assert all(o.documents for o in opps)


def test_sedia_cascade_keys_are_stable():
    results = fixture_json("sedia_cascade.json")["results"]
    keys = [sedia.cascade_key(r)[0] for r in results]
    assert keys == [sedia.cascade_key(r)[0] for r in results]
    assert all(keys)


def test_interreg_hits():
    hits = fixture_json("interreg.json")["results"][0]["hits"]
    opps = [interreg.normalize(h) for h in hits]
    assert len(opps) == 3 and all(o.source == "interreg" for o in opps)
    assert all("eligible_countries" in o.raw for o in opps)


def test_epah_keeps_only_calls_and_flags_indirect():
    opps = list(epah.parse((FIXTURES / "epah.html").read_text(encoding="utf-8")))
    assert all(o.indirect for o in opps)
    assert all(epah.CALL_HINT.search(o.title) for o in opps)
