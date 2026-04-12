#!/usr/bin/env python3
"""Lokaal QuantLog testen tegen je JSONL (geen YAML-config nodig).

Voorbeelden (vanuit quantbuildv1-root, of overal met juiste paden):

  # Vandaag (UTC) onder data/quantlog_events/YYYY-MM-DD
  python scripts/test_quantlog_local.py

  # Expliciete map of .jsonl
  python scripts/test_quantlog_local.py --path data/quantlog_events/2026-04-12

  # CI-fixture
  python scripts/test_quantlog_local.py --fixture

  # Alleen controleren of QuantLog-CLI werkt
  python scripts/test_quantlog_local.py --list-types

Vereist: QuantLog-repo naast quantbuildv1 of QUANTLOG_REPO_PATH.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from src.quantbuild.quantlog_repo import (  # noqa: E402
    quantbuild_project_root,
    quantlog_pythonpath_prefix,
    resolve_quantlog_repo_path,
)

_DATE_DIR = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _default_events_base() -> Path:
    return quantbuild_project_root() / "data" / "quantlog_events"


def _resolve_quantlog_repo(cli_path: str | None) -> Path:
    if cli_path:
        p = Path(cli_path).expanduser().resolve()
        if (p / "src" / "quantlog").is_dir():
            return p
        sys.stderr.write(f"Invalid --quantlog-repo (no src/quantlog): {p}\n")
        sys.exit(2)
    found = resolve_quantlog_repo_path()
    if found is not None:
        return found
    sys.stderr.write(
        "QuantLog repo not found. Clone quantlogv1 naast quantbuildv1 of zet QUANTLOG_REPO_PATH.\n"
    )
    sys.exit(2)


def _latest_day_under(base: Path) -> Path | None:
    if not base.is_dir():
        return None
    candidates: list[Path] = []
    for child in base.iterdir():
        if child.is_dir() and _DATE_DIR.match(child.name):
            candidates.append(child)
    if not candidates:
        return None
    return sorted(candidates, key=lambda p: p.name)[-1]


def _resolve_events_path(
    *,
    path: str | None,
    base: Path,
    date: str | None,
    use_latest: bool,
) -> Path:
    if path:
        p = Path(path).expanduser().resolve()
        if not p.exists():
            sys.stderr.write(f"Path does not exist: {p}\n")
            sys.exit(2)
        return p

    if date:
        day = base / date
        if day.exists():
            return day
        sys.stderr.write(f"No folder for --date {date!r} under {base}\n")
        sys.exit(2)

    if use_latest:
        latest = _latest_day_under(base)
        if latest is not None:
            return latest

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    day = base / today
    if day.exists():
        return day

    latest = _latest_day_under(base)
    if latest is not None:
        sys.stderr.write(f"Using latest day under {base}: {latest.name}\n")
        return latest

    sys.stderr.write(
        f"No event data found under {base}.\n"
        f"  Pass --path naar een map of .jsonl, of --fixture voor de test-fixture.\n"
    )
    sys.exit(2)


def _env_with_quantlog(quantlog_repo: Path) -> dict[str, str]:
    env = os.environ.copy()
    prefix = quantlog_pythonpath_prefix(quantlog_repo)
    env["PYTHONPATH"] = prefix if not env.get("PYTHONPATH") else f"{prefix}{os.pathsep}{env['PYTHONPATH']}"
    return env


def _run_cli(
    quantlog_repo: Path,
    args: list[str],
    *,
    capture_json: bool,
) -> tuple[int, dict | None, str]:
    env = _env_with_quantlog(quantlog_repo)
    cmd = [sys.executable, "-m", "quantlog.cli", *args]
    proc = subprocess.run(cmd, capture_output=True, text=True, env=env, check=False)
    out = proc.stdout.strip()
    data = None
    if capture_json and out:
        try:
            data = json.loads(out)
        except json.JSONDecodeError:
            data = None
    return proc.returncode, data, out + (proc.stderr or "")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--path",
        help="Map of .jsonl (QuantLog doorzoekt recursief .jsonl in mappen).",
    )
    parser.add_argument(
        "--base",
        default=str(_default_events_base()),
        help="Basismap voor automatische dagkeuze (default: quantbuild data/quantlog_events)",
    )
    parser.add_argument(
        "--date",
        help="Dagmap YYYY-MM-DD onder --base (UTC).",
    )
    parser.add_argument(
        "--latest",
        action="store_true",
        help="Gebruik de nieuwste YYYY-MM-DD map onder --base i.p.v. vandaag.",
    )
    parser.add_argument(
        "--fixture",
        action="store_true",
        help=f"Kort voor --path tests/fixtures/quantlog/minimal_day (relatief t.o.v. quantbuild root).",
    )
    parser.add_argument("--quantlog-repo", help="Override QuantLog repository root.")
    parser.add_argument(
        "--list-types",
        action="store_true",
        help="Alleen 'list-event-types' draaien en exit.",
    )
    parser.add_argument("--no-summarize", action="store_true", help="Sla summarize-day over.")
    parser.add_argument("--no-score", action="store_true", help="Sla score-run over.")
    parser.add_argument("--no-pipeline", action="store_true", help="Sla QuantBuild pipeline-samenvatting over.")
    parser.add_argument("--pass-threshold", type=int, default=95, help="Voor score-run.")
    parser.add_argument("-q", "--quiet", action="store_true", help="Minder JSON naar stdout.")
    ns = parser.parse_args()

    quantlog_repo = _resolve_quantlog_repo(ns.quantlog_repo)

    if ns.list_types:
        rc, data, combined = _run_cli(quantlog_repo, ["list-event-types"], capture_json=True)
        if data is not None:
            print(json.dumps(data, indent=2, ensure_ascii=True))
        else:
            print(combined)
        return 0 if rc == 0 else 1

    if ns.fixture:
        events_path = quantbuild_project_root() / "tests" / "fixtures" / "quantlog" / "minimal_day"
    else:
        events_path = _resolve_events_path(
            path=ns.path,
            base=Path(ns.base).expanduser().resolve(),
            date=ns.date,
            use_latest=ns.latest,
        )

    print(f"QuantLog repo: {quantlog_repo}", flush=True)
    print(f"Events path:   {events_path}", flush=True)
    print(flush=True)

    rc_val, val_data, val_raw = _run_cli(
        quantlog_repo,
        ["validate-events", "--path", str(events_path)],
        capture_json=True,
    )
    if val_data and not ns.quiet:
        print(json.dumps(val_data, indent=2, ensure_ascii=True))
    elif not val_data:
        print(val_raw)
    print()
    if rc_val != 0:
        sys.stderr.write("validate-events failed (non-zero exit).\n")
        return 1
    err_n = int(val_data.get("errors_total", 0)) if isinstance(val_data, dict) else 0
    if err_n > 0:
        return 1

    if not ns.no_pipeline:
        pipe_script = _REPO_ROOT / "scripts" / "summarize_quantlog_pipeline.py"
        if pipe_script.is_file():
            print("--- pipeline funnel (summarize_quantlog_pipeline.py) ---", flush=True)
            proc = subprocess.run(
                [sys.executable, str(pipe_script), str(events_path)],
                check=False,
            )
            if proc.returncode != 0:
                sys.stderr.write("summarize_quantlog_pipeline.py exited with error.\n")
                return 1
            print(flush=True)

    if not ns.no_summarize:
        rc_sum, sum_data, sum_raw = _run_cli(
            quantlog_repo,
            ["summarize-day", "--path", str(events_path)],
            capture_json=True,
        )
        if sum_data and not ns.quiet:
            print(json.dumps(sum_data, indent=2, ensure_ascii=True))
        elif not sum_data:
            print(sum_raw)
        print()
        if rc_sum != 0:
            sys.stderr.write("summarize-day failed.\n")
            return 1

    if not ns.no_score:
        rc_sc, sc_data, sc_raw = _run_cli(
            quantlog_repo,
            [
                "score-run",
                "--path",
                str(events_path),
                "--pass-threshold",
                str(ns.pass_threshold),
            ],
            capture_json=True,
        )
        if sc_data:
            print(
                f"score-run: score={sc_data.get('score')} grade={sc_data.get('grade')} "
                f"passed={sc_data.get('passed')} errors={sc_data.get('errors_total')}"
            )
            if not ns.quiet:
                print(json.dumps(sc_data, indent=2, ensure_ascii=True))
        else:
            print(sc_raw)
        print()
        if rc_sc != 0:
            return 1

    print("OK — local QuantLog test completed.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
