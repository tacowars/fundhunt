"""Path resolution. Everything lives under the clone unless overridden.

- FUNDHUNT_HOME      base directory (default: the repository root)
- FUNDHUNT_DB        SQLite database (default: <home>/data/fundhunt.db)
- FUNDHUNT_PROFILES  profile directory (default: <home>/profiles)
"""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _path(env: str, default: Path) -> Path:
    v = os.environ.get(env)
    return Path(v).expanduser() if v else default


def home() -> Path:
    return _path("FUNDHUNT_HOME", ROOT)


def data_dir() -> Path:
    return home() / "data"


def db_path() -> Path:
    return _path("FUNDHUNT_DB", data_dir() / "fundhunt.db")


def reports_dir() -> Path:
    return data_dir() / "reports"


def docs_cache_dir() -> Path:
    return data_dir() / "documents"


def inbox_dir() -> Path:
    """Where exported review decisions can be dropped for `fundhunt decisions import`."""
    return data_dir() / "inbox"


def profiles_dir() -> Path:
    return _path("FUNDHUNT_PROFILES", home() / "profiles")
