"""QuantResearch experiment ledger v1 — validate, link, summarize (no metrics, no QuantLog)."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from quantresearch.paths import experiments_dir, repo_root


def _utc_equivalent(a: str, b: str) -> bool:
    """Compare ISO-8601 timestamps (Z vs +00:00)."""
    try:
        sa = str(a).strip().replace("Z", "+00:00")
        sb = str(b).strip().replace("Z", "+00:00")
        return datetime.fromisoformat(sa) == datetime.fromisoformat(sb)
    except ValueError:
        return str(a).strip() == str(b).strip()


def _positive_int_rerun_index(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and value >= 1:
        return value
    if isinstance(value, float) and value == int(value) and int(value) >= 1:
        return int(value)
    if isinstance(value, str) and value.strip().isdigit():
        n = int(value.strip())
        return n if n >= 1 else None
    return None


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _suite_root_from_experiment(exp: dict[str, Any]) -> Path | None:
    suite = exp.get("suite") if isinstance(exp.get("suite"), dict) else {}
    root = suite.get("suite_root")
    if not root or not str(root).strip():
        return None
    return Path(str(root)).resolve()


def experiment_path(experiment_id: str) -> Path:
    d = experiments_dir() / experiment_id
    if not d.is_dir():
        raise FileNotFoundError(f"No experiment folder: {d}")
    return d


def load_experiment(experiment_id: str) -> dict[str, Any]:
    p = experiment_path(experiment_id) / "experiment.json"
    if not p.is_file():
        raise FileNotFoundError(f"Missing experiment.json: {p}")
    return _read_json(p)


def load_links(experiment_id: str) -> dict[str, Any] | None:
    p = experiment_path(experiment_id) / "links.json"
    if not p.is_file():
        return None
    return _read_json(p)


def _resolve_under_suite(suite_root: Path, rel: str, *, absolute_ok: bool) -> Path:
    p = Path(rel)
    if absolute_ok and p.is_absolute():
        return p.resolve()
    return (suite_root / rel).resolve()


def _terminal_ledger_status(status: str) -> bool:
    return status.lower() in ("completed", "archived", "rejected")


def _validate_rerun_lineage(
    experiment_id: str,
    exp: dict[str, Any],
    *,
    parent_id: str,
) -> list[str]:
    """parent_experiment_id set → require rerun fields and a completed parent with matching completed_at."""
    errors: list[str] = []
    if parent_id == experiment_id:
        errors.append(
            "rerun governance: parent_experiment_id must name a different experiment folder "
            "(prefer a new experiment_id such as ...-v2); self-reference is not allowed."
        )
        return errors

    reason = str(exp.get("rerun_reason", "") or "").strip()
    if not reason:
        errors.append("rerun governance: rerun_reason is required and must be non-empty when parent_experiment_id is set")

    ridx = _positive_int_rerun_index(exp.get("rerun_index"))
    if ridx is None:
        errors.append(
            "rerun governance: rerun_index is required and must be an integer >= 1 when parent_experiment_id is set"
        )

    prev = str(exp.get("previous_completed_at_utc", "") or "").strip()
    if not prev:
        errors.append(
            "rerun governance: previous_completed_at_utc is required (copy parent's completed_at_utc) "
            "when parent_experiment_id is set"
        )

    if errors:
        return errors

    pdir = experiments_dir() / parent_id
    if not pdir.is_dir():
        errors.append(f"rerun governance: parent experiment folder not found: {parent_id!r}")
        return errors

    pj = pdir / "experiment.json"
    if not pj.is_file():
        errors.append(f"rerun governance: parent experiment.json missing: {parent_id!r}")
        return errors

    try:
        parent = _read_json(pj)
    except (OSError, json.JSONDecodeError) as e:
        errors.append(f"rerun governance: cannot read parent experiment.json: {e}")
        return errors

    pst = str(parent.get("status", "")).strip().lower()
    if pst != "completed":
        errors.append(
            f"rerun governance: parent_experiment_id {parent_id!r} must have status 'completed' "
            f"(found {parent.get('status')!r})"
        )

    p_completed = str(parent.get("completed_at_utc") or "").strip()
    if not p_completed:
        errors.append(f"rerun governance: parent {parent_id!r} has no completed_at_utc")
    elif not _utc_equivalent(p_completed, prev):
        errors.append(
            "rerun governance: previous_completed_at_utc must exactly match the parent's completed_at_utc "
            f"(parent has {p_completed!r}, got {prev!r})"
        )

    return errors


def _ghost_reuse_and_lineage_errors(experiment_id: str, exp: dict[str, Any], exp_dir: Path) -> list[str]:
    """
    Prevent silent reuse of completed protocols: stale completed_at, links.json on a fresh matrix,
    or parent_experiment_id without a valid lineage.
    """
    errors: list[str] = []
    st = str(exp.get("status", "")).strip().lower()
    if st not in ("planned", "running"):
        return errors

    cat = str(exp.get("completed_at_utc") or "").strip()
    if cat:
        errors.append(
            "rerun governance: status is planned/running but completed_at_utc is still set. "
            "Clear completed_at_utc for a brand-new protocol, or use a new experiment folder (e.g. ...-v2) "
            "with parent_experiment_id + rerun_reason + rerun_index + previous_completed_at_utc."
        )

    if (exp_dir / "links.json").is_file():
        errors.append(
            "rerun governance: links.json already exists for this experiment folder. "
            "Do not delete it to bypass governance. Create a new experiment_id (e.g. ...-v2), keep the parent's "
            "links.json intact, and set parent_experiment_id + rerun_reason + rerun_index + "
            "previous_completed_at_utc on the child ledger."
        )

    parent_id = str(exp.get("parent_experiment_id", "") or "").strip()
    if parent_id:
        errors.extend(_validate_rerun_lineage(experiment_id, exp, parent_id=parent_id))

    return errors


def validate_experiment(experiment_id: str, *, mode: str = "full") -> list[str]:
    """Validate ledger. ``mode=pre_run`` = QuantOS matrix gate (hypothesis + plan + planned/running only)."""
    m = (mode or "full").strip().lower()
    if m == "pre_run":
        return _validate_pre_run(experiment_id)
    if m == "full":
        return _validate_full(experiment_id)
    return [f"unknown validate mode: {mode!r} (use full or pre_run)"]


def _validate_pre_run(experiment_id: str) -> list[str]:
    """QuantOS preflight: ledger entry exists and is ready to orchestrate (no outcomes required)."""
    errors: list[str] = []
    try:
        exp_dir = experiment_path(experiment_id)
    except FileNotFoundError as e:
        return [str(e)]

    if not (exp_dir / "experiment.json").is_file():
        errors.append("experiment.json missing")
        return errors

    try:
        exp = load_experiment(experiment_id)
    except (OSError, json.JSONDecodeError) as e:
        errors.append(f"experiment.json invalid: {e}")
        return errors

    if not (exp_dir / "hypothesis.md").is_file():
        errors.append("hypothesis.md missing")
    if not (exp_dir / "experiment_plan.md").is_file():
        errors.append("experiment_plan.md missing")

    st = str(exp.get("status", "")).strip().lower()
    if st not in ("planned", "running"):
        errors.append(
            f"preflight: status must be 'planned' or 'running' (found {exp.get('status')!r}). "
            "Set status to 'planned' (or 'running') in experiment.json before QuantOS matrix; "
            "completed experiments must be reset for a new orchestrated run."
        )

    eid = str(exp.get("experiment_id", "")).strip()
    if eid and eid != experiment_id:
        errors.append(f"experiment_id mismatch: folder {experiment_id!r} vs json {eid!r}")

    errors.extend(_ghost_reuse_and_lineage_errors(experiment_id, exp, exp_dir))

    return errors


def _validate_full(experiment_id: str) -> list[str]:
    """Full ledger validation (post-hoc / audit)."""
    errors: list[str] = []
    try:
        exp_dir = experiment_path(experiment_id)
    except FileNotFoundError as e:
        return [str(e)]

    ej = exp_dir / "experiment.json"
    if not ej.is_file():
        errors.append("experiment.json missing")
        return errors

    try:
        exp = _read_json(ej)
    except (OSError, json.JSONDecodeError) as e:
        errors.append(f"experiment.json invalid: {e}")
        return errors

    if not (exp_dir / "hypothesis.md").is_file():
        errors.append("hypothesis.md missing")
    if not (exp_dir / "experiment_plan.md").is_file():
        errors.append("experiment_plan.md missing")

    dec = exp_dir / "decision.md"
    if not dec.is_file():
        errors.append("decision.md missing")
    else:
        status = str(exp.get("status", "")).strip().lower()
        if _terminal_ledger_status(status):
            text = dec.read_text(encoding="utf-8")
            if not re.search(r"(?m)^##\s+Final\s+Decision\b", text):
                errors.append("decision.md must include a '## Final Decision' section for completed/archived/rejected")

    status = str(exp.get("status", ""))
    if status == "completed":
        if not exp.get("completed_at_utc"):
            errors.append("completed experiment must set completed_at_utc")
        links = load_links(experiment_id)
        if not links or not str(links.get("quantos_run_dir", "")).strip():
            errors.append("completed experiment must have links.json with quantos_run_dir")
        else:
            suite_root = _suite_root_from_experiment(exp)
            if suite_root and suite_root.is_dir():
                abs_ok = bool(links.get("paths_are_absolute"))
                run_dir = _resolve_under_suite(suite_root, str(links["quantos_run_dir"]), absolute_ok=abs_ok)
                if not run_dir.is_dir():
                    errors.append(f"QuantOS run dir does not exist: {run_dir}")
                cap = exp.get("canonical_artifact_path")
                if cap and str(cap).strip():
                    cpath = (suite_root / str(cap)).resolve()
                    if not cpath.is_dir():
                        errors.append(f"canonical_artifact_path is not a directory: {cpath}")
            else:
                errors.append("suite.suite_root missing or invalid — cannot verify QuantOS artifacts")

    prom = str(exp.get("promotion_decision", "UNKNOWN")).upper()
    disc = str(exp.get("discovery_tier", "")).lower()
    if prom == "PROMOTE" and disc in ("watchlist", "none"):
        errors.append(
            "promotion_decision PROMOTE is inconsistent with discovery_tier watchlist/none "
            "(watchlist is not promotion)"
        )

    suite_root = _suite_root_from_experiment(exp)
    links = load_links(experiment_id)
    if suite_root and links and str(links.get("quantos_run_dir", "")).strip():
        abs_ok = bool(links.get("paths_are_absolute"))
        run_dir = _resolve_under_suite(suite_root, str(links["quantos_run_dir"]), absolute_ok=abs_ok)
        baseline_folder = "a0_baseline"
        tc_path = links.get("throughput_compare_json")
        if tc_path and (suite_root / str(tc_path)).is_file():
            tc = _read_json(suite_root / str(tc_path))
            baseline_folder = str(tc.get("baseline_variant_folder") or baseline_folder)
        elif (run_dir / "THROUGHPUT_COMPARE.json").is_file():
            tc = _read_json(run_dir / "THROUGHPUT_COMPARE.json")
            baseline_folder = str(tc.get("baseline_variant_folder") or baseline_folder)

        prom_json = run_dir / baseline_folder / "analytics" / "promotion_decision.json"
        ev_json = run_dir / baseline_folder / "analytics" / "edge_verdict.json"
        if prom == "PROMOTE" and prom_json.is_file() and ev_json.is_file():
            ev = _read_json(ev_json)
            if str(ev.get("confidence", "")).upper() == "LOW":
                errors.append("promotion_decision PROMOTE inconsistent with baseline LOW confidence in evidence")

    st_lower = str(exp.get("status", "")).strip().lower()
    if st_lower in ("planned", "running"):
        errors.extend(_ghost_reuse_and_lineage_errors(experiment_id, exp, exp_dir))
    elif str(exp.get("parent_experiment_id", "") or "").strip():
        errors.extend(
            _validate_rerun_lineage(
                experiment_id,
                exp,
                parent_id=str(exp.get("parent_experiment_id", "") or "").strip(),
            )
        )

    return errors


def link_artifacts(
    experiment_id: str,
    *,
    quantos_run_dir: Path,
    suite_root: Path | None = None,
) -> Path:
    """Write links.json under the experiment folder. Paths stored relative to suite_root when possible."""
    exp_dir = experiment_path(experiment_id)
    exp = load_experiment(experiment_id)
    suite = suite_root or _suite_root_from_experiment(exp)
    if not suite or not suite.is_dir():
        raise RuntimeError("suite.suite_root must be set in experiment.json to resolve artifact paths")

    run_resolved = quantos_run_dir.expanduser().resolve()
    try:
        rel_run = str(run_resolved.relative_to(suite))
    except ValueError:
        rel_run = str(run_resolved)
        paths_absolute = True
    else:
        paths_absolute = False

    rel = rel_run.replace("\\", "/")
    if paths_absolute:
        base = str(run_resolved).replace("\\", "/")
        payload = {
            "quantos_run_dir": base,
            "paths_are_absolute": True,
            "throughput_compare_json": f"{base}/THROUGHPUT_COMPARE.json",
            "throughput_compare_md": f"{base}/THROUGHPUT_COMPARE.md",
            "throughput_discovery_registry": f"{base}/throughput_discovery_registry.json",
            "throughput_discovery_summary": f"{base}/THROUGHPUT_DISCOVERY_SUMMARY.md",
        }
    else:
        payload = {
            "quantos_run_dir": rel,
            "paths_are_absolute": False,
            "throughput_compare_json": f"{rel}/THROUGHPUT_COMPARE.json".replace("//", "/"),
            "throughput_compare_md": f"{rel}/THROUGHPUT_COMPARE.md".replace("//", "/"),
            "throughput_discovery_registry": f"{rel}/throughput_discovery_registry.json".replace("//", "/"),
            "throughput_discovery_summary": f"{rel}/THROUGHPUT_DISCOVERY_SUMMARY.md".replace("//", "/"),
        }
    out = exp_dir / "links.json"
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return out


def mark_experiment_completed(
    experiment_id: str,
    *,
    completed_at_utc: str | None = None,
) -> None:
    """Set experiment.json status to completed and timestamp (human fields unchanged)."""
    exp_dir = experiment_path(experiment_id)
    exp = load_experiment(experiment_id)
    exp["status"] = "completed"
    exp["completed_at_utc"] = completed_at_utc or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    (exp_dir / "experiment.json").write_text(json.dumps(exp, indent=2), encoding="utf-8")


def summarize_ledger_table() -> str:
    """Markdown table of all experiments with experiment.json."""
    lines = [
        "# Research ledger (auto-generated)",
        "",
        "QuantResearch records **hypothesis, interpretation, decision, and links** only. "
        "It does not run backtests, mutate QuantLog, or compute trading metrics.",
        "",
        "| Experiment | Status | Matrix | Decision | Discovery tier | Next action |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    ed = experiments_dir()
    if not ed.is_dir():
        lines.append("| *(no experiments dir)* | | | | | |")
        return "\n".join(lines) + "\n"

    for child in sorted(ed.iterdir()):
        if not child.is_dir() or child.name.startswith("."):
            continue
        ej = child / "experiment.json"
        if not ej.is_file():
            continue
        try:
            exp = _read_json(ej)
        except (OSError, json.JSONDecodeError):
            continue
        eid = exp.get("experiment_id", child.name)
        st = exp.get("status", "")
        mt = exp.get("matrix_type", exp.get("quantmetrics_os", {}).get("matrix_preset", "custom"))
        if not isinstance(mt, str):
            mt = "custom"
        dec = exp.get("promotion_decision", "UNKNOWN")
        dtier = exp.get("discovery_tier", "")
        na = exp.get("next_action", "")
        lines.append(f"| `{eid}` | {st} | {mt} | {dec} | {dtier} | {na} |")

    lines.append("")
    lines.append(f"*Generated from `{ed}` experiment folders.*")
    lines.append("")
    return "\n".join(lines)


def write_research_ledger_md() -> Path:
    """Write quantresearch/RESEARCH_LEDGER.md."""
    out = repo_root() / "RESEARCH_LEDGER.md"
    out.write_text(summarize_ledger_table(), encoding="utf-8")
    return out
