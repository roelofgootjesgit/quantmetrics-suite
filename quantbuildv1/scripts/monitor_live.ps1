# ============================================================
# QuantBuild Live Monitor — PowerShell
# ============================================================
# Usage:  .\scripts\monitor_live.ps1
#         .\scripts\monitor_live.ps1 -RefreshSeconds 10
# ============================================================

param(
    [int]$RefreshSeconds = 15
)

$ROOT = Split-Path -Parent (Split-Path -Parent $PSCommandPath)
$LogDir = Join-Path $ROOT "logs"

function Get-LatestLog {
    $logs = Get-ChildItem -Path $LogDir -Filter "safe_live_launch_*.log" -ErrorAction SilentlyContinue |
            Sort-Object LastWriteTime -Descending
    if ($logs.Count -gt 0) { return $logs[0].FullName }

    $logs = Get-ChildItem -Path $LogDir -Filter "quantbuild_*.log" -ErrorAction SilentlyContinue |
            Sort-Object LastWriteTime -Descending
    if ($logs.Count -gt 0) { return $logs[0].FullName }
    return $null
}

function Get-Stats($Content) {
    $lines = $Content -split "`n"
    $total = $lines.Count

    $signals     = ($lines | Select-String "SIGNAL:" | Measure-Object).Count
    $trades      = ($lines | Select-String "Trade registered" | Measure-Object).Count
    $dryTrades   = ($lines | Select-String "\[DRY RUN\]" | Measure-Object).Count
    $regimeUpd   = ($lines | Select-String "Regime updated" | Measure-Object).Count
    $warmupOk    = ($lines | Select-String "BOOTSTRAP OK" | Measure-Object).Count
    $warmupFail  = ($lines | Select-String "BOOTSTRAP FAILED" | Measure-Object).Count
    $noSignal    = ($lines | Select-String "No entry signals" | Measure-Object).Count
    $dataWarn    = ($lines | Select-String "signal_warmup_check" | Measure-Object).Count
    $errors      = ($lines | Select-String "ERROR" | Measure-Object).Count
    $heartbeats  = ($lines | Select-String "Heartbeat" | Measure-Object).Count
    $newsBlocks  = ($lines | Select-String "NewsGate blocks" | Measure-Object).Count
    $spreadBlock = ($lines | Select-String "Spread guard" | Measure-Object).Count
    $posLimit    = ($lines | Select-String "Position limit" | Measure-Object).Count
    $bridgeExec  = ($lines | Select-String "quantbridge.execution" | Measure-Object).Count

    # Last few meaningful lines
    $tail = ($lines | Where-Object {
        $_ -match "SIGNAL:|Trade registered|Regime updated|BOOTSTRAP|ERROR|Heartbeat|quantbridge"
    } | Select-Object -Last 5) -join "`n"

    return @{
        TotalLines   = $total
        Signals      = $signals
        Trades       = $trades
        DryTrades    = $dryTrades
        RegimeUpdates = $regimeUpd
        BootstrapOk  = $warmupOk
        BootstrapFail = $warmupFail
        NoSignalChecks = $noSignal
        DataWarnings = $dataWarn
        Errors       = $errors
        Heartbeats   = $heartbeats
        NewsBlocks   = $newsBlocks
        SpreadBlocks = $spreadBlock
        PosLimitHits = $posLimit
        BridgeExecs  = $bridgeExec
        LastEvents   = $tail
    }
}

Clear-Host
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  QUANTBUILD LIVE MONITOR" -ForegroundColor Cyan
Write-Host "  Refresh: ${RefreshSeconds}s | Ctrl+C to stop" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

while ($true) {
    $logFile = Get-LatestLog
    if (-not $logFile) {
        Write-Host "[$(Get-Date -Format 'HH:mm:ss')] No log file found in $LogDir" -ForegroundColor Yellow
        Start-Sleep -Seconds $RefreshSeconds
        continue
    }

    $content = Get-Content $logFile -Raw -ErrorAction SilentlyContinue
    if (-not $content) {
        Write-Host "[$(Get-Date -Format 'HH:mm:ss')] Log file empty: $logFile" -ForegroundColor Yellow
        Start-Sleep -Seconds $RefreshSeconds
        continue
    }

    $s = Get-Stats $content
    $fname = Split-Path $logFile -Leaf

    Clear-Host
    Write-Host "============================================" -ForegroundColor Cyan
    Write-Host "  QUANTBUILD LIVE MONITOR" -ForegroundColor Cyan
    Write-Host "  $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" -ForegroundColor Gray
    Write-Host "  Log: $fname" -ForegroundColor Gray
    Write-Host "============================================" -ForegroundColor Cyan
    Write-Host ""

    # Bootstrap status
    if ($s.BootstrapOk -gt 0) {
        Write-Host "  BOOTSTRAP:     OK" -ForegroundColor Green
    } elseif ($s.BootstrapFail -gt 0) {
        Write-Host "  BOOTSTRAP:     FAILED" -ForegroundColor Red
    } else {
        Write-Host "  BOOTSTRAP:     pending..." -ForegroundColor Yellow
    }

    Write-Host ""
    Write-Host "  --- Activity ---" -ForegroundColor White

    # Signals + trades
    if ($s.Signals -gt 0) {
        Write-Host "  Signals:       $($s.Signals)" -ForegroundColor Green
    } else {
        Write-Host "  Signals:       $($s.Signals)" -ForegroundColor Gray
    }

    if ($s.Trades -gt 0) {
        Write-Host "  Trades:        $($s.Trades)" -ForegroundColor Green
    } elseif ($s.DryTrades -gt 0) {
        Write-Host "  Dry trades:    $($s.DryTrades)" -ForegroundColor Cyan
    } else {
        Write-Host "  Trades:        0" -ForegroundColor Gray
    }

    Write-Host "  Bridge execs:  $($s.BridgeExecs)" -ForegroundColor $(if ($s.BridgeExecs -gt 0) { "Green" } else { "Gray" })
    Write-Host "  Regime updates:$($s.RegimeUpdates)" -ForegroundColor Gray
    Write-Host "  Signal checks: $($s.NoSignalChecks) (no entry)" -ForegroundColor Gray
    Write-Host "  Heartbeats:    $($s.Heartbeats)" -ForegroundColor Gray

    Write-Host ""
    Write-Host "  --- Guards ---" -ForegroundColor White
    Write-Host "  News blocks:   $($s.NewsBlocks)" -ForegroundColor $(if ($s.NewsBlocks -gt 0) { "Yellow" } else { "Gray" })
    Write-Host "  Spread blocks: $($s.SpreadBlocks)" -ForegroundColor $(if ($s.SpreadBlocks -gt 0) { "Yellow" } else { "Gray" })
    Write-Host "  Pos limit:     $($s.PosLimitHits)" -ForegroundColor $(if ($s.PosLimitHits -gt 0) { "Yellow" } else { "Gray" })
    Write-Host "  Data warnings: $($s.DataWarnings)" -ForegroundColor $(if ($s.DataWarnings -gt 0) { "Red" } else { "Gray" })

    Write-Host ""
    Write-Host "  --- Health ---" -ForegroundColor White
    Write-Host "  Log lines:     $($s.TotalLines)" -ForegroundColor Gray
    if ($s.Errors -gt 0) {
        Write-Host "  ERRORS:        $($s.Errors)" -ForegroundColor Red
    } else {
        Write-Host "  Errors:        0" -ForegroundColor Green
    }

    Write-Host ""
    Write-Host "  --- Last Events ---" -ForegroundColor White
    if ($s.LastEvents) {
        $s.LastEvents -split "`n" | ForEach-Object {
            $line = $_.Trim()
            if ($line.Length -gt 100) { $line = $line.Substring(0, 100) + "..." }
            if ($line -match "ERROR") {
                Write-Host "  $line" -ForegroundColor Red
            } elseif ($line -match "SIGNAL:") {
                Write-Host "  $line" -ForegroundColor Green
            } elseif ($line -match "Trade") {
                Write-Host "  $line" -ForegroundColor Cyan
            } else {
                Write-Host "  $line" -ForegroundColor Gray
            }
        }
    } else {
        Write-Host "  (none yet)" -ForegroundColor Gray
    }

    Write-Host ""
    Write-Host "  Next refresh in ${RefreshSeconds}s..." -ForegroundColor DarkGray

    Start-Sleep -Seconds $RefreshSeconds
}
