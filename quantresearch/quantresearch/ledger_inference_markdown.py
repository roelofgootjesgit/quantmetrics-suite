"""Human-readable markdown snippets from ``inference_report.json`` (inference_v1)."""

from __future__ import annotations

import math
from typing import Any


def _fmt_float(x: Any, *, nd: int = 6) -> str:
    if x is None:
        return "—"
    try:
        v = float(x)
    except (TypeError, ValueError):
        return "—"
    if not math.isfinite(v):
        return "—"
    if abs(v) >= 1e4 or (abs(v) > 0 and abs(v) < 1e-4):
        return f"{v:.{nd}g}"
    return f"{v:.{nd}f}"


def render_inference_results_table(inference: dict[str, Any] | None) -> str:
    """Markdown table body for the inferentie section (no surrounding headings)."""
    if not inference:
        return (
            "| Statistiek | Status |\n"
            "|------------|--------|\n"
            "| Per-trade R inferentie | **pending** — plaats `inference_report.json` in `experiments/<id>/` en zet "
            "`inference_consumer: true` in het manifest. |\n"
        )

    sample = inference.get("sample") if isinstance(inference.get("sample"), dict) else {}
    ht = inference.get("hypothesis_test") if isinstance(inference.get("hypothesis_test"), dict) else {}
    ci = inference.get("confidence_interval") if isinstance(inference.get("confidence_interval"), dict) else {}
    fx = inference.get("effect_size") if isinstance(inference.get("effect_size"), dict) else {}
    verdict = inference.get("verdict") if isinstance(inference.get("verdict"), dict) else {}

    lo = ci.get("lower")
    if lo is None:
        lo = ci.get("ci_95_lower")
    hi = ci.get("upper")
    if hi is None:
        hi = ci.get("ci_95_upper")

    p_raw = ht.get("p_value")
    sig = ht.get("significant_at_alpha")
    sig_s = "PASS" if sig is True else ("FAIL" if sig is False else "—")

    def _n_disp(v: Any) -> str:
        try:
            return str(int(v))
        except (TypeError, ValueError):
            return "—"

    rows = [
        ("Bron", "QuantAnalytics `inference_report.json` (schema `inference_v1`)"),
        ("n (trade_closed)", _n_disp(sample.get("n"))),
        ("mean_r (descriptief)", _fmt_float(sample.get("mean_r"))),
        ("std_r / median_r", f"{_fmt_float(sample.get('std_r'))} / {_fmt_float(sample.get('median_r'))}"),
        ("Test gebruikt", str(ht.get("test_used") or "—")),
        ("p-waarde (two-sided vs H0 median R=0)", f"{_fmt_float(p_raw)} ({sig_s} bij α={ht.get('alpha', '—')})"),
        ("95% CI mean R (bootstrap)", f"[{_fmt_float(lo)}, {_fmt_float(hi)}] — method: {ci.get('method', '—')}"),
        (
            "Economische gate",
            f"ci_95_lower {_fmt_float(lo)} vs floor {verdict.get('minimum_effect_size_used', '—')} → "
            f"**{verdict.get('economic_significance', '—')}** (`{verdict.get('economic_rule', 'ci rule')}`)",
        ),
        ("Cohen's d (trade-R)", f"{_fmt_float(fx.get('cohens_d'))} ({fx.get('interpretation', '—')})"),
        ("Statistisch verdict", f"**{verdict.get('statistical_significance', '—')}**"),
        ("Economisch verdict", f"**{verdict.get('economic_significance', '—')}**"),
    ]
    lines = ["| Statistiek | Waarde |", "|------------|--------|"]
    for k, v in rows:
        vk = str(v).replace("|", "\\|")
        lines.append(f"| {k} | {vk} |")
    lines.append("")
    lines.append("Zie `docs/ACADEMIC_RESEARCH_PROTOCOL.md` en `experiment.json` voor governance vs academische status.")
    return "\n".join(lines)


def render_gate_b_section(
    *,
    academic_status: str,
    effective_status: str,
    inference_reason: str | None,
    pre_registration_valid: bool | None,
    pre_registration_status: str | None,
    inference: dict[str, Any] | None,
) -> str:
    """Markdown for ### Gate B — Academisch (inferentie)."""
    inv = inference or {}
    ht = inv.get("hypothesis_test") if isinstance(inv.get("hypothesis_test"), dict) else {}
    ci = inv.get("confidence_interval") if isinstance(inv.get("confidence_interval"), dict) else {}
    verdict = inv.get("verdict") if isinstance(inv.get("verdict"), dict) else {}

    lo = ci.get("lower")
    if lo is None:
        lo = ci.get("ci_95_lower")

    if inference:
        prv = pre_registration_valid if pre_registration_valid is not None else "n/a"
        prs = pre_registration_status if pre_registration_status else "n/a"
        pre_blk = (
            f"`preregistration.json`: **retrospectief** (`pre_registration_valid`: "
            f"**{prv}**, status `{prs}`).\n\n"
        )
        numbers = (
            f"- **Test:** `{ht.get('test_used', '—')}`  \n"
            f"- **p-waarde:** {_fmt_float(ht.get('p_value'))} → statistisch "
            f"**{verdict.get('statistical_significance', '—')}** (α = {ht.get('alpha', '—')})  \n"
            f"- **ci_95_lower (mean R):** {_fmt_float(lo)} → economisch "
            f"**{verdict.get('economic_significance', '—')}** (vloer = {verdict.get('minimum_effect_size_used', '—')} R)  \n"
        )
        if inference_reason:
            numbers += f"- **Reden (consumer):** {inference_reason}\n"
        body = (
            f"{pre_blk}"
            f"**`academic_status`:** **{academic_status}**  \n"
            f"**`effective_status`:** `{effective_status}`  \n\n"
            f"{numbers}\n"
            "Geen `PROMOTE_FULL` zonder PASS op **beide** gates (statistisch én economisch volgens CI-ondergrens).\n\n"
        )
    else:
        prv = pre_registration_valid if pre_registration_valid is not None else "n/a"
        body = (
            "**`academic_status`: PENDING** — geen `inference_report.json` in deze experiment-map, "
            "of inferentie nog niet geconsumeerd. "
            f"`preregistration.json` is **retrospectief** (`pre_registration_valid`: **{prv}**). "
            "Geen `PROMOTE_FULL` zolang Gate B niet vastligt.\n\n"
        )

    return body


def render_effective_status_paragraph(effective_status: str, academic_status: str) -> str:
    return (
        "### Effectieve status\n\n"
        f"**`effective_status`:** `{effective_status}`  \n"
        f"**`academic_status`:** **{academic_status}**\n\n"
        "Architectuurregel: promoveer niet naar fases die academische eisen stellen zonder expliciete PASS op beide gates.\n\n"
        "Dit is geen live-tradingbewijs; volgende fase: OOS-data, slippage-model, sizing, paper trading.\n"
    )
