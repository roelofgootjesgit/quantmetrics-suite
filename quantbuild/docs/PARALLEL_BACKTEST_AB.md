# Parallel A/B backtests (werkdocument)

Hoe je **twee (of meer) backtests tegelijk** draait met **hetzelfde venster** en **gescheiden QuantLog `run_id`**, zodat QuantAnalytics-post-run per run klopt.

---

## Waarom dit bestand

- Parallel bespaart tijd.
- Zonder unieke `run_id` kregen twee processen die in **dezelfde UTC-seconde** starten **dezelfde** auto-`run_id` → post-run `--run-id` filter mengde events.
- **Fix (ingebouwd):** `resolve_quantlog_run_id()` in `src/quantbuild/execution/quantlog_ids.py` hangt `_<8 hex>` achter de tijdstempel-auto-id.

---

## Vaste A/B-set (STRATEGY_FIX_PLAN Sprint 1)

| Rol | Config |
|-----|--------|
| Baseline | `configs/backtest_2026_jan_mar.yaml` |
| Variant (trend `skip`) | `configs/backtest_2026_jan_mar_expansion_only.yaml` |
| Variant + NY session (expansion) | `configs/backtest_2026_jan_mar_expansion_ny.yaml` |

Zelfde data, symbol, dates, filters — varianten wijzigen alleen `regime_profiles` (trend uit; expansion-session subset). Live/paper stack zonder vast venster: `configs/expansion_ny_strategy.yaml`.

---

## PowerShell: twee jobs parallel

Vanuit **repo root** (`quantbuild`):

```powershell
$qb = "C:\Users\Gebruiker\quantbuild"   # pas aan indien nodig

$j1 = Start-Job -ScriptBlock {
    param($root)
    Set-Location $root
    python -m src.quantbuild.app --config configs/backtest_2026_jan_mar.yaml backtest
} -ArgumentList $qb

$j2 = Start-Job -ScriptBlock {
    param($root)
    Set-Location $root
    python -m src.quantbuild.app --config configs/backtest_2026_jan_mar_expansion_only.yaml backtest
} -ArgumentList $qb

Wait-Job $j1, $j2 | Out-Null

Write-Host "=== BASELINE ===" -ForegroundColor Cyan
Receive-Job $j1

Write-Host "=== VARIANT ===" -ForegroundColor Cyan
Receive-Job $j2

$s1, $s2 = $j1.State, $j2.State
Remove-Job $j1, $j2 -Force
Write-Host "Job states: $s1 , $s2"
if ($s1 -ne "Completed" -or $s2 -ne "Completed") { exit 1 }
```

In de job-output staat per run o.a. **`run_id=qb_run_...`** — die twee moeten **verschillen** zijn.

---

## Na de run

1. **QuantAnalytics** (post-run): rapport + `*_KEY_FINDINGS.md` onder `quantanalytics/output_rapport/` — per run al gefilterd op `run_id` als post-run aan stond.
2. **Handmatig zelfde filter:**  
   `python -m quantmetrics_analytics.cli.run_analysis --dir <quantlog_base> --run-id <run_id> --reports all`

---

## Expliciete `run_id` (optioneel)

Wil je vaste namen i.p.v. auto-id: in de yaml onder `quantlog`:

```yaml
quantlog:
  run_id: "ab_baseline_q1_2026"
```

respectievelijk een andere string voor de variant. Dan geen suffix-nodig voor uniekheid.

Omgeving (voor scripts): `QUANTBUILD_RUN_ID` wint ook als config `run_id` leeg is — zie `quantlog_ids.py`.

---

## Caveats

1. **`logs/backtest_quantbuild_*.log`** — bestandsnaam is tijd-gebaseerd; twee jobs in dezelfde seconde kunnen **dezelfde logfile** raken en regels door elkaar schrijven. Voor forensische logs: **sequentieel** draaien, of per job een eigen `cwd`/log policy (toekomstige verbetering).
2. **`data/quantlog_events`** — events zijn per `run_id` in JSONL gescheiden; parallel is OK zolang `run_id` uniek is.
3. **Oude corrupte JSONL-regels** — analytics kan `skip line ...` loggen; los data op of negeer voor A/B-interpretatie.

---

## CLI-vorm (sequentieel, simpel)

Geen parallel nodig:

```text
python -m src.quantbuild.app --config configs/backtest_2026_jan_mar.yaml backtest
python -m src.quantbuild.app --config configs/backtest_2026_jan_mar_expansion_only.yaml backtest
```

---

## Zie ook

- `quantmetrics_os/docs/STRATEGY_FIX_PLAN.md` — Sprint 1 hypothese en meetlijst.
- `configs/backtest_2026_jan_mar_expansion_only.yaml` — variant-config.
