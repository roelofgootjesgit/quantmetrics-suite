# QuantOS — suite starten (handout)

Korte gids om **QuantBuild** (signal engine), **QuantBridge** (execution engine) en **QuantLog** (observability layer) vanuit **QuantOS** te draaien — checkout-map **`quantmetrics_os/`**. De orchestrator staat in `orchestrator/` en start subprocessen met de juiste repo-root en `PYTHONPATH`.

---

## 1. Eenmalige setup: `.env`

Kopieer het voorbeeld naar een lokale env-file:

```text
orchestrator/config.example.env  →  orchestrator/.env
```

Pas de paden aan als je repos ergens anders staan:

| Variabele | Betekenis |
|-----------|-----------|
| `QUANTBUILD_ROOT` | Pad naar `quantbuildv1` |
| `QUANTBRIDGE_ROOT` | Pad naar `quantbridgev1` |
| `QUANTLOG_ROOT` | Pad naar `quantlogv1` |
| `QUANTLOG_EVENTS_ROOT` | Optioneel. JSONL-dagmappen; default: `<QUANTBUILD_ROOT>/data/quantlog_events` |
| `PYTHON` | Python-executable (default: `python`) |
| `QUANTBUILD_CONFIG` | Default YAML t.o.v. QuantBuild-root |
| `QUANTBRIDGE_CONFIG` | Default YAML t.o.v. QuantBridge-root |

Controleren of alles klopt:

```powershell
cd C:\Users\Gebruiker\quantmetrics_os\orchestrator   # QuantOS — Orchestrator
python quantmetrics.py check
```

Of via het wrapper-script:

```powershell
.\qm.ps1 check
```

---

## 2. Veelgebruikte commando’s

Alle voorbeelden: werkdirectory = `quantmetrics_os/orchestrator` (QuantOS).

| Doel | Commando |
|------|----------|
| Paden tonen | `python quantmetrics.py check` |
| QuantBuild live (paper / dry-run, geen `--real`) | `python quantmetrics.py build -c configs/strict_prod_v2.yaml` |
| QuantBuild met echte orders | `python quantmetrics.py build -c <config.yaml> --real` |
| Extra args door naar QuantBuild | `python quantmetrics.py build -c ... -- --dry-run` (na `--`) |
| QuantBridge: cTrader smoke (mock) | `python quantmetrics.py bridge smoke --mode mock` |
| QuantBridge: cTrader smoke (OpenAPI) | `python quantmetrics.py bridge smoke --mode openapi` |
| QuantBridge: regressiesuite | `python quantmetrics.py bridge regression` |
| QuantLog CLI | `python quantmetrics.py log validate-events -- --path <pad-naar-dagmap>` |
| Post-run keten (validate + summarize + score) | `python quantmetrics.py post-run 2026-03-29` |
| QuantBuild backtest (na afloop automatisch `research/runs_digest.md` uit `runs/`) | `python quantmetrics.py backtest -c configs/<naam>.yaml` · uitschakelen: `--no-research-digest` |
| Telegram suite start/stop (als in QuantBuild-YAML geconfigureerd) | `python quantmetrics.py notify start build bridge log` |

Zie `orchestrator/quantmetrics.py` voor de volledige argparse-hulp (`--help` per subcommando waar van toepassing).

---

## 3. VS Code: alle repos tegelijk

Open het multi-root workspace-bestand:

```text
vscode/quant-suite.code-workspace
```

Daarmee staan **quantmetrics_os** (QuantOS), **quantbuildv1** (QuantBuild), **quantbridgev1** (QuantBridge) en **quantlogv1** (QuantLog) naast elkaar (broer-mappen onder dezelfde parent).

---

## 4. QuantBuild + echte cTrader (QuantBridge OpenAPI)

QuantBuild laadt de bridge-module dynamisch. Zet het pad naar de **src**-map van QuantBridge in de omgeving, bijvoorbeeld:

```text
QUANTBRIDGE_SRC_PATH=C:/Users/<jij>/quantbridgev1/src
```

Dit is **los** van `quantmetrics.py`; het hoort bij runs die **vanuit QuantBuild** met `mock_mode: false` en OpenAPI willen verbinden. Credentials staan typisch in env of bridge-`local.env` / `.env` (zie QuantBridge-docs).

---

## 5. Repo-layout (aanbevolen)

```text
<parent>/
  quantmetrics_os/    ← QuantOS — orchestrator + deze docs
  quantbuildv1/
  quantbridgev1/
  quantlogv1/
```

Clonen/updaten in één keer kan met `scripts/clone_quant_suite.sh` (Linux/macOS/WSL); die kan ook een gegenereerde `orchestrator/.env` schrijven.

---

## 6. Snelle rooktest

Na een geldige `.env`:

```powershell
cd orchestrator
python quantmetrics.py check
python quantmetrics.py bridge smoke --mode mock
```

Als beide slagen, zijn roots en QuantBridge-smoke lokaal in orde.
