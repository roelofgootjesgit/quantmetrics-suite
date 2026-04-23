# Chain validate-events, summarize-day, check-ingest-health, score-run for a day folder.
# From repo root (venv optional if PYTHONPATH=src works):
#   $env:PYTHONPATH = "$PWD\src"
#   powershell -File scripts/nightly_quantlog_report.ps1 -Path "data\imported\2026-04-01"
#
# Exit codes: validate 1 on errors; ingest-health 3 if gaps; score-run 4 if below threshold.
param(
    [Parameter(Mandatory = $true)]
    [string] $Path,
    [double] $MaxGapSeconds = 300,
    [int] $PassThreshold = 95
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $repoRoot
if (-not $env:PYTHONPATH) {
    $env:PYTHONPATH = Join-Path $repoRoot "src"
}

Write-Host "=== validate-events ==="
python -m quantlog.cli validate-events --path $Path
$v = $LASTEXITCODE

Write-Host "=== summarize-day ==="
python -m quantlog.cli summarize-day --path $Path
$null = $LASTEXITCODE

Write-Host "=== check-ingest-health ==="
python -m quantlog.cli check-ingest-health --path $Path --max-gap-seconds $MaxGapSeconds
$h = $LASTEXITCODE

Write-Host "=== score-run ==="
python -m quantlog.cli score-run --path $Path --max-gap-seconds $MaxGapSeconds --pass-threshold $PassThreshold
$s = $LASTEXITCODE

$worst = [Math]::Max([Math]::Max($v, $h), $s)
Write-Host "=== done (exit $worst): validate=$v ingest_health=$h score_run=$s ==="
exit $worst
