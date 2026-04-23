# Push all ecosystem repos in one go (separate git remotes).
# Default: sibling folders under the parent directory of quantbuildv1.
# Folders: QuantBuild (quantbuildv1), QuantBridge (quantbridgev1), QuantLog (quantlogv1), QuantOS (quantmetrics_os).
#
# Usage:
#   .\scripts\dev\push_all_repos.ps1
#   .\scripts\dev\push_all_repos.ps1 -Remote origin -DryRun
#   $env:QUANT_ECOSYSTEM_ROOT = "C:\Users\You\src"; .\scripts\dev\push_all_repos.ps1

param(
    [string]$Remote = "origin",
    [switch]$DryRun,
    [string]$EcosystemRoot = $env:QUANT_ECOSYSTEM_ROOT
)

$ErrorActionPreference = "Stop"

$quantbuildRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
if (-not $EcosystemRoot) {
    $EcosystemRoot = Split-Path $quantbuildRoot -Parent
}

$repoNames = @(
    "quantbuildv1",
    "quantbridgev1",
    "quantlogv1",
    "quantmetrics_os"
)

$failed = New-Object System.Collections.Generic.List[string]

Write-Host "Ecosystem root: $EcosystemRoot" -ForegroundColor DarkGray
Write-Host "Remote: $Remote" -ForegroundColor DarkGray
Write-Host ""

foreach ($name in $repoNames) {
    $full = Join-Path $EcosystemRoot $name
    if (-not (Test-Path -LiteralPath $full)) {
        Write-Warning "Skipped (folder missing): $name -> $full"
        continue
    }
    $gitDir = Join-Path $full ".git"
    if (-not (Test-Path -LiteralPath $gitDir)) {
        Write-Warning "Skipped (not a git repo): $name"
        continue
    }

    $branch = (& git -C $full rev-parse --abbrev-ref HEAD 2>$null)
    if ($null -eq $branch) { $branch = "?" } else { $branch = $branch.Trim() }
    if ($branch -eq "HEAD") {
        Write-Warning "Skipped (detached HEAD): $name"
        continue
    }

    Write-Host "=== $name ($branch) ===" -ForegroundColor Cyan
    if ($DryRun) {
        Write-Host "  git -C `"$full`" push $Remote"
        continue
    }

    & git -C $full push $Remote
    if ($LASTEXITCODE -ne 0) {
        [void]$failed.Add($name)
    }
    Write-Host ""
}

if ($failed.Count -gt 0) {
    Write-Host "Failed for: $($failed -join ', ')" -ForegroundColor Red
    exit 1
}

Write-Host "Done: all pushes that ran completed successfully." -ForegroundColor Green
exit 0
