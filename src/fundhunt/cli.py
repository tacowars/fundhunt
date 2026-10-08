"""fundhunt command line. Every command prints JSON on stdout (progress goes
to stderr), so an agent can drive it without parsing prose.

    fundhunt status                         database, sources, profiles
    fundhunt sources                        what each source covers
    fundhunt profile list | check <name>    validate profiles
    fundhunt sync [--source S ...] [--force]
    fundhunt rank --profile P
    fundhunt candidates --profile P [--top N] [--all]
    fundhunt show <ref>                     one full record
    fundhunt doc <ref> [--max-chars N]      official documents as text (deep read)
    fundhunt verdict --profile P < verdicts.json
    fundhunt decisions import --profile P [FILE ...]
    fundhunt report --profile P [--open]
    fundhunt run --profile P                sync + rank + candidates, in one go
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__, documents, pipeline, rank, report
from . import profile as profile_mod
from .settings import db_path
from .sources import DESCRIPTIONS, SOURCES
from .store import Store


def emit(obj) -> None:
    json.dump(obj, sys.stdout, ensure_ascii=False, indent=2, default=str)
    sys.stdout.write("\n")


def fail(msg: str, code: int = 1) -> int:
    emit({"error": msg})
    return code


def _profile(name: str):
    try:
        return profile_mod.load(name)
    except FileNotFoundError as exc:
        raise SystemExit(fail(str(exc)))
    except Exception as exc:
        raise SystemExit(fail(f"profile {name!r} is invalid: {exc}"))


def cmd_status(a) -> int:
    st = Store()
    profiles = []
    for p in profile_mod.list_profiles():
        try:
            prof = profile_mod.load(str(p))
            profiles.append({"name": prof.name, "file": str(p), "valid": True})
        except Exception as exc:
            profiles.append({"file": str(p), "valid": False, "error": str(exc)[:300]})
    last = {}
    for s in SOURCES:
        ok = st.last_success(s)
        last[s] = ok.isoformat() if ok else None
    emit({"version": __version__, "database": str(db_path()), "corpus": st.stats(),
          "last_complete_sync": last, "recent_runs": st.runs(10), "profiles": profiles})
    return 0


def cmd_sources(a) -> int:
    emit([{"source": s, "covers": DESCRIPTIONS[s]} for s in SOURCES])
    return 0


def cmd_profile(a) -> int:
    if a.action == "list":
        emit([str(p) for p in profile_mod.list_profiles()])
        return 0
    prof = _profile(a.name)
    groups = {k: len(g.terms) for k, g in prof.keywords.items()}
    warnings = []
    if not prof.keywords.get("core") or not prof.keywords["core"].terms:
        warnings.append("no core keywords: nothing can reach tier A")
    if prof.name.startswith("example-"):
        warnings.append("this is a shipped example; copy it to profiles/<your-name>.yaml")
    emit({"valid": True, "name": prof.name, "hash": prof.hash(), "brief": prof.brief(),
          "keyword_terms": groups, "warnings": warnings})
    return 0


def cmd_sync(a) -> int:
    bad = [s for s in a.source or [] if s not in SOURCES]
    if bad:
        return fail(f"unknown source(s) {bad}; choose from {SOURCES}")
    res = pipeline.sync(Store(), a.source, force=a.force)
    emit(res)
    return 0 if all(r.get("ok") for r in res.values()) else 3


def cmd_rank(a) -> int:
    prof = _profile(a.profile)
    emit({"profile": prof.name, **rank.run(Store(), prof)})
    return 0


def cmd_candidates(a) -> int:
    prof = _profile(a.profile)
    emit(pipeline.candidates(Store(), prof, a.top, include_judged=a.all))
    return 0


def cmd_show(a) -> int:
    opp = Store().get(a.ref)
    if not opp:
        return fail(f"no record {a.ref}")
    emit(opp.model_dump(mode="json"))
    return 0


def cmd_doc(a) -> int:
    opp = Store().get(a.ref)
    if not opp:
        return fail(f"no record {a.ref}")
    emit(documents.read(opp, max_chars=a.max_chars, max_docs=a.max_docs))
    return 0


def cmd_verdict(a) -> int:
    prof = _profile(a.profile)
    text = Path(a.file).read_text(encoding="utf-8") if a.file else sys.stdin.read()
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        return fail(f"verdict input is not JSON: {exc}")
    res = pipeline.save_verdicts(Store(), prof, payload)
    emit(res)
    return 0 if not res["errors"] else 4


def cmd_decisions(a) -> int:
    prof = _profile(a.profile)
    files = pipeline.decision_files(prof, [Path(f) for f in a.files])
    emit(pipeline.import_decisions(Store(), prof, files))
    return 0


def cmd_report(a) -> int:
    prof = _profile(a.profile)
    emit(report.write(Store(), prof, open_browser=a.open))
    return 0


def cmd_run(a) -> int:
    prof = _profile(a.profile)
    st = Store()
    synced = {} if a.no_sync else pipeline.sync(st, None)
    ranked = rank.run(st, prof)
    cands = pipeline.candidates(st, prof, a.top)
    emit({"sync": synced, "rank": ranked, **cands})
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="fundhunt", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--version", action="version", version=__version__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status").set_defaults(fn=cmd_status)
    sub.add_parser("sources").set_defaults(fn=cmd_sources)

    p = sub.add_parser("profile")
    p.add_argument("action", choices=["list", "check"])
    p.add_argument("name", nargs="?")
    p.set_defaults(fn=cmd_profile)

    p = sub.add_parser("sync")
    p.add_argument("--source", action="append", help="limit to a source (repeatable)")
    p.add_argument("--force", action="store_true", help="poll weekly sources anyway")
    p.set_defaults(fn=cmd_sync)

    for name, fn in (("rank", cmd_rank), ("report", cmd_report)):
        p = sub.add_parser(name)
        p.add_argument("--profile", required=True)
        if name == "report":
            p.add_argument("--open", action="store_true", help="open in the default browser")
        p.set_defaults(fn=fn)

    p = sub.add_parser("candidates")
    p.add_argument("--profile", required=True)
    p.add_argument("--top", type=int)
    p.add_argument("--all", action="store_true", help="include records with a current verdict")
    p.set_defaults(fn=cmd_candidates)

    p = sub.add_parser("run")
    p.add_argument("--profile", required=True)
    p.add_argument("--top", type=int)
    p.add_argument("--no-sync", action="store_true")
    p.set_defaults(fn=cmd_run)

    p = sub.add_parser("show")
    p.add_argument("ref")
    p.set_defaults(fn=cmd_show)

    p = sub.add_parser("doc")
    p.add_argument("ref")
    p.add_argument("--max-chars", type=int, default=60_000)
    p.add_argument("--max-docs", type=int, default=3)
    p.set_defaults(fn=cmd_doc)

    p = sub.add_parser("verdict")
    p.add_argument("--profile", required=True)
    p.add_argument("--file", help="read verdict JSON from a file instead of stdin")
    p.set_defaults(fn=cmd_verdict)

    p = sub.add_parser("decisions")
    p.add_argument("action", choices=["import"])
    p.add_argument("--profile", required=True)
    p.add_argument("files", nargs="*")
    p.set_defaults(fn=cmd_decisions)

    a = ap.parse_args(argv)
    if a.cmd == "profile" and a.action == "check" and not a.name:
        return fail("profile check needs a profile name")
    return a.fn(a)


if __name__ == "__main__":
    raise SystemExit(main())
