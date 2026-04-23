# Live VPS-koppeling en lokale backtest — checklist

Praktische stappen om **QuantMetrics Analytics** (`quantmetrics_analytics`) te voeden met echte QuantLog-data, én om **QuantBuild-backtests** lokaal te draaien. Dit document is een **operator-checklist**, geen tweede waarheid naast QuantBuild: paden volgen je YAML en VPS-layout.

---

## Rollen (kort)

| Component | Waar het draait | Wat analytics nodig heeft |
|-----------|-----------------|----------------------------|
| QuantBuild live | VPS | JSONL onder `quantlog.base_path` (zie config) |
| QuantBuild backtest | Lokaal (of VPS) | Zelfde schema JSONL als `quantlog.enabled` aan staat (o.a. `runs/<run_id>.jsonl`) |
| Analytics CLI | Meestal **lokaal** tegen een **gekopieerde** `.jsonl` | Alleen **lezen** — geen mutatie van logs |

---

## Deel A — Live VPS → analytics op je PC

### A.1 Waar staan de events op de VPS?

Typisch schrijft QuantBuild append-only logs naar een **datum-map** onder je QuantBuild-root:

```text
<QUANTBUILD_ROOT>/data/quantlog_events/<YYYY-MM-DD>/quantbuild.jsonl
```

Exact pad volgt **`quantlog.base_path`** in je YAML (zie `configs/*.yaml`). Op een dev-VPS staat `QUANTBUILD_ROOT` vaak zoals in `quantmetrics_os/orchestrator/config.vps.example.env` — aanpassen naar jouw machine.

**Check op de VPS** (pad invullen):

```bash
ls -la "$QUANTBUILD_ROOT/data/quantlog_events/$(date -u +%F)/"
```

Je wilt minimaal het bestand van **de dag die je analyseert** (UTC-datum in de mapnaam).

### A.2 Data naar je laptop halen (kies één)

Doel: een map op Windows met één of meer `.jsonl`-bestanden die `quantmetrics_analytics` kan lezen.

1. **SCP / SFTP (eenvoudig)**  
   Vanaf je PC (Git Bash, WSL of WinSCP): kopieer een dag-map of alleen `quantbuild.jsonl` naar bijvoorbeeld `C:\data\quantlog_sync\2026-04-19\`.

2. **rsync (efficiënt, deltas)**  
   Op WSL of Linux-client: sync alleen `quantlog_events` voor een datumbereik naar een lokale map.

3. **VS Code Remote SSH**  
   Open de VPS-map, download het relevante `.jsonl` via de editor naar je werkmap.

**Geen secrets in JSONL verwachten** — keys horen in de omgeving (`docs/CREDENTIALS_AND_ENVIRONMENT.md` in QuantBuild). Controleer exports voordat je iets deelt.

### A.3 Analytics lokaal installeren en draaien

```powershell
cd C:\Users\Gebruiker\quantanalyticsv1
pip install -e .
python -m quantmetrics_analytics.cli.run_analysis --jsonl "C:\pad\naar\quantbuild.jsonl" --reports all
```

**Leesbaar rapportbestand:** standaard schrijft de CLI een UTF-8 **`.txt`** naar **`output_rapport/`** onder je quantanalytics-clone (map wordt zo nodig aangemaakt; bestandsnaam = invoerbestandsnaam + UTC-timestamp). Op stderr zie je `Report written to: ...`. Gebruik **`--stdout`** als je alleen terminal-output wilt (geen bestand).

```powershell
cd C:\Users\Gebruiker\quantanalyticsv1
python -m quantmetrics_analytics.cli.run_analysis `
  --jsonl "C:\pad\naar\quantbuild.jsonl" `
  --reports all
```

Eigen pad (overschrijft de standaardmap):

```powershell
python -m quantmetrics_analytics.cli.run_analysis `
  --jsonl "C:\pad\naar\quantbuild.jsonl" `
  --reports all `
  --output "D:\data\my_analysis.txt"
```

Meerdere dagen / bestanden:

```powershell
python -m quantmetrics_analytics.cli.run_analysis --dir "C:\pad\naar\quantlog_sync" --reports summary,no-trade,funnel
```

Of één glob (PowerShell: quotes om het patroon):

```powershell
python -m quantmetrics_analytics.cli.run_analysis --glob "C:\data\quantlog_sync\**\*.jsonl" --reports all
```

### A.4 Optioneel: analytics op de VPS draaien

Kan als `pandas` al in **QuantBuild’s `.venv`** zit en je wilt geen sync:

```bash
cd /pad/naar/quantanalyticsv1
/path/naar/quantbuildv1/.venv/bin/pip install -e .
/path/naar/quantbuildv1/.venv/bin/python -m quantmetrics_analytics.cli.run_analysis \
  --jsonl "$QUANTBUILD_ROOT/data/quantlog_events/$(date -u +%F)/quantbuild.jsonl" \
  --reports all
```

Voordeel: geen copy. Nadeel: afhankelijk van één productie-venv en Pythonversie op de VPS — lokaal analyseren blijft meestal het schoonst.

### A.5 Referenties (suite)

| Onderwerp | Doc |
|-----------|-----|
| VPS directory layout, één venv | `quantbuildv1/docs/VPS_MULTI_MODULE_DEPLOYMENT.md` |
| QuantLog op VPS (geen tweede venv) | `quantlogv1/docs/VPS_SYNC.md` |
| Orchestrator env + paden | `quantmetrics_os/orchestrator/config.vps.example.env` |
| Dagelijkse JSON / mentor-workflow | `quantbuildv1/docs/VPS_JSON_DAGELIJKSE_ANALYSE_WORKFLOW.md` |

---

## Deel B — Backtest lokaal draaien (QuantBuild)

Analytics op **live JSONL** en backtest zijn hetzelfde **event-schema**, zolang QuantLog in de backtest-config **aan** staat: de engine kan naar o.a. `data/quantlog_events/runs/<run_id>.jsonl` schrijven (zie implementatie in `quantbuildv1/src/quantbuild/backtest/engine.py` en je YAML-sectie `quantlog`).

### B.1 Voorbereiding (eenmalig)

```powershell
cd C:\Users\Gebruiker\quantbuildv1
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

Zorg dat je **config** naar de juiste **datafeed / cache** wijst (bijv. Dukascopy-cache voor edge-unlock configs — zie je eigen YAML-commentaar).

### B.2 Backtest starten

Algemeen patroon (exacte config = jouw onderzoeks-setup):

```powershell
cd C:\Users\Gebruiker\quantbuildv1
.\.venv\Scripts\activate
python -m src.quantbuild.app backtest --config configs\strict_prod_v2.yaml
```

Andere voorbeelden uit de operator-docs:

```text
python -m src.quantbuild.app backtest --config configs/backtest_2025_edge_unlock.yaml
```

(Zie `quantbuildv1/docs/OPERATOR_CHEATSHEET.md` §0.6b voor edge-unlock varianten.)

### B.3 Output

- **Rapporten / metrics**: typisch onder `reports/` (QuantBuild README).
- **QuantLog JSONL** (als ingeschakeld): onder je `quantlog.base_path`, o.a. consolidated run-bestand — dat kun je met **dezelfde** `run_analysis.py` analyseren als live-VPS logs.

### B.4 Daarna analytics op backtest-events

```powershell
cd C:\Users\Gebruiker\quantanalyticsv1
pip install -e .
python -m quantmetrics_analytics.cli.run_analysis --jsonl "C:\Users\Gebruiker\quantbuildv1\data\quantlog_events\runs\<run_id>.jsonl" --reports all
```

Het rapport staat daarna onder **`quantanalyticsv1\output_rapport\`** (zie stderr voor het exacte pad). Alleen naar de console: voeg **`--stdout`** toe.

Het exacte pad naar het run-`.jsonl` staat in je backtest-log of volgt uit `run_id` in config.

---

## Samenvatting

| Doel | Actie |
|------|--------|
| Live inzicht | VPS: JSONL vinden → sync naar PC → `run_analysis.py --jsonl` of `--dir` |
| Backtest | `quantbuildv1`: `python -m src.quantbuild.app backtest --config …` |
| Zelfde analytics op backtest | QuantLog in YAML aan → `run_analysis.py` op het gegenereerde `.jsonl` |

Als een stap faalt: eerst controleren of `event_type` en `payload_*` kolommen in het bestand zitten (`--reports summary`).
