import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
REPO = Path(__file__).resolve().parents[1]


def fixture_json(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    """Every test gets its own data dir; profiles come from the shipped examples."""
    monkeypatch.setenv("FUNDHUNT_HOME", str(tmp_path))
    monkeypatch.setenv("FUNDHUNT_PROFILES", str(REPO / "profiles"))
    return tmp_path


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    import httpx

    def refuse(*a, **k):
        raise AssertionError("tests must not touch the network")

    monkeypatch.setattr(httpx.Client, "request", refuse)
