$ErrorActionPreference = "Stop"

Write-Host "[CI] Starting QuantLog smoke gates"

python -m pip install -e .

Write-Host "[CI] Running unit tests"
python -m unittest discover -s tests -p "test_*.py" -v

Write-Host "[CI] Running contract fixture checks"
python scripts/contract_check.py --contracts-path tests/fixtures/contracts --max-warnings 0

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

Write-Host "[CI] Replay integrity check on generated day"
$firstTrace = (Get-Content (Join-Path $dayPath "quantbuild.jsonl") -TotalCount 1 | ConvertFrom-Json).trace_id
if (-not $firstTrace) {
  throw "[CI][FAIL] could not extract trace_id for replay integrity check"
}
$replayRaw = python -m quantlog.cli replay-trace --path $dayPath --trace-id $firstTrace
$replay = $replayRaw | ConvertFrom-Json
if ($replay.events_found -le 0) {
  throw "[CI][FAIL] replay integrity check found zero events"
}

Write-Host "[CI] Checking ingest health"
$healthRaw = python -m quantlog.cli check-ingest-health --path $dayPath --max-gap-seconds 300
$health = $healthRaw | ConvertFrom-Json
if ($health.gaps_found -ne 0) {
  throw "[CI][FAIL] expected no ingest gaps in generated day"
}

Write-Host "[CI] Scoring run quality"
$scoreRaw = python -m quantlog.cli score-run --path $dayPath --max-gap-seconds 300 --pass-threshold 95
$score = $scoreRaw | ConvertFrom-Json
if (-not $score.passed) {
  throw "[CI][FAIL] run quality score did not pass threshold"
}

Write-Host "[CI] Generating anomaly day for negative quality check"
$anomalyRoot = Join-Path ".tmp" ("ci_events_anomaly_" + $runSuffix)
python scripts/generate_sample_day.py --output-path $anomalyRoot --date $date --traces 20 --seed 42 --inject-anomalies
$anomalyDayPath = Join-Path $anomalyRoot $date
$anomalyScoreRaw = python -m quantlog.cli score-run --path $anomalyDayPath --max-gap-seconds 300 --pass-threshold 95
$anomalyScore = $anomalyScoreRaw | ConvertFrom-Json
if ($anomalyScore.passed) {
  throw "[CI][FAIL] anomaly quality score unexpectedly passed"
}

Write-Host "[CI][PASS] All QuantLog smoke gates passed"
