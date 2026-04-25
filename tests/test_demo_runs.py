from __future__ import annotations

from pathlib import Path
import subprocess
import sys


def test_run_demo_script_outputs_verdict() -> None:
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, str(root / "run_demo.py")],
        cwd=str(root),
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    output = result.stdout
    assert "Total events:" in output
    assert "Funnel: detected -> evaluated -> action -> filled -> closed" in output
    assert "Conversion rates:" in output
    assert "Guard attribution:" in output
    assert "Top blocking guard:" in output
    assert "Trade performance:" in output
    assert "winrate:" in output
    assert "profit_factor:" in output
    assert "expectancy:" in output
    assert "sample_size:" in output
    assert any(token in output for token in ("Verdict: PASS", "Verdict: VALIDATION_REQUIRED", "Verdict: REJECT"))
