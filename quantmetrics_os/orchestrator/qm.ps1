# Usage: .\qm.ps1 check
#        .\qm.ps1 build -c configs/strict_prod_v2.yaml
# Requires orchestrator\.env (copy from config.example.env) or QUANT*_ROOT in the environment.
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
& python (Join-Path $here "quantmetrics.py") @args
exit $LASTEXITCODE
