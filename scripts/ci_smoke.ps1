$ErrorActionPreference = "Stop"

Write-Host "[CI] Starting QuantLog smoke gates"

python -m pip install -e .

Write-Host "[CI] Running unit tests"
python -m unittest discover -s tests -p "test_*.py" -v

Write-Host "[CI] Running end-to-end smoke runner"
python scripts/smoke_end_to_end.py

Write-Host "[CI] Validating bundled sample events"
python -m quantlog.cli validate-events --path data/events/sample
python -m quantlog.cli replay-trace --path data/events/sample --trace-id trace_demo_1

$date = Get-Date -Format "yyyy-MM-dd"
$runSuffix = Get-Date -Format "yyyyMMdd_HHmmss"
$ciRoot = Join-Path ".tmp" ("ci_events_" + $runSuffix)

Write-Host "[CI] Generating synthetic day at $ciRoot ($date)"
python scripts/generate_sample_day.py --output-path $ciRoot --date $date --traces 40 --seed 42

$dayPath = Join-Path $ciRoot $date

Write-Host "[CI] Validating generated day"
python -m quantlog.cli validate-events --path $dayPath

Write-Host "[CI] Summarizing generated day"
$summaryRaw = python -m quantlog.cli summarize-day --path $dayPath
$summary = $summaryRaw | ConvertFrom-Json

if ($summary.events_total -le 0) {
  throw "[CI][FAIL] summary.events_total must be > 0"
}
if ($summary.trades_filled -le 0) {
  throw "[CI][FAIL] summary.trades_filled must be > 0"
}
if ($summary.blocks_total -le 0) {
  throw "[CI][FAIL] summary.blocks_total must be > 0"
}
if ($summary.broker_rejects -le 0) {
  throw "[CI][FAIL] summary.broker_rejects must be > 0"
}

Write-Host "[CI] Checking ingest health"
$healthRaw = python -m quantlog.cli check-ingest-health --path $dayPath --max-gap-seconds 300
$health = $healthRaw | ConvertFrom-Json
if ($health.gaps_found -ne 0) {
  throw "[CI][FAIL] expected no ingest gaps in generated day"
}

Write-Host "[CI][PASS] All QuantLog smoke gates passed"
