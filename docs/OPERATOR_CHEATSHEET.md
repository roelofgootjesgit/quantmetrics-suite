# QuantBuild Operator Cheat Sheet

Korte operationele sheet voor dagelijkse run op VPS.

**Secrets:** staan in de **OS-omgeving**; op de VPS in `/etc/quantbuild/quantbuild.env` (systemd `EnvironmentFile=`) **of** in **QuantOS** **`quantmetrics_os/orchestrator/.env`** als je via de orchestrator start. Lijst met alle variabelenamen: **`docs/CREDENTIALS_AND_ENVIRONMENT.md`**.

**Huidige cTrader-demo VPS:** `WorkingDirectory` = `/opt/quantbuild/quantbuild_e1_v1` (niet de repo-standaard `quantbuildv1`). **Runtime file log:** `/opt/quantbuild/quantbuild_e1_v1/logs/runtime_ctrader_demo.log` — einde week / review: `tail -n 200` of `tail -f` op dit pad. Twijfel → `systemctl show quantbuild-ctrader-demo.service -p WorkingDirectory`.

---

## 0) Week start — suite aan, incl. QuantLog + logs

**Doel:** de bot draait de hele week door; **QuantLog** append’t **JSONL** onder `data/quantlog_events/<UTC-datum>/` (als `quantlog.enabled` in je YAML aan staat); je hebt **file logs** + optioneel **nightly** validate/summary.

### 0.1 Code en venv (eenmalig per week of na wijzigingen)

Pas `/opt/quantbuild/…` aan naar jouw pad (bijv. `/root/dev/quant/quantbuildv1`):

```bash
export QB=/root/dev/quant/quantbuildv1
cd "$QB" && git pull --ff-only
cd /root/dev/quant/quantbridgev1 && git pull --ff-only
cd /root/dev/quant/quantlogv1 && git pull --ff-only
cd /root/dev/quant/quantmetrics_os && git pull --ff-only

cd "$QB" && source .venv/bin/activate
pip install -r requirements.txt   # alleen als requirements gewijzigd
pip install -e /root/dev/quant/quantlogv1   # nodig voor quantlog_post_run / CLI
```

### 0.2 Secrets

Zorg dat **alle** keys gezet zijn (systemd-`EnvironmentFile` **of** `orchestrator/.env` vóór `quantmetrics.py`). Zie **`docs/CREDENTIALS_AND_ENVIRONMENT.md`**.

### 0.3 Runtime starten (kies één)

**A — systemd** (units moeten naar jouw `WorkingDirectory` / `ExecStart`-pad wijzen; standaard in repo = `/opt/quantbuild/quantbuildv1`):

```bash
sudo systemctl daemon-reload
sudo systemctl enable quantbuild-ctrader-demo.service
sudo systemctl restart quantbuild-ctrader-demo.service
sudo systemctl status quantbuild-ctrader-demo.service --no-pager
```

Snelle week-kick via script (zelfde service-naam, zie §0.4 voor env-vars):

```bash
cd /root/dev/quant/quantbuildv1
chmod +x scripts/vps/start_weekrun.sh
QUANTBUILD_ROOT=/root/dev/quant/quantbuildv1 ./scripts/vps/start_weekrun.sh
```

**B — tmux + orchestrator** (geen systemd, wél `orchestrator/.env`):

```bash
tmux new -s qb
cd /root/dev/quant/quantmetrics_os/orchestrator
/root/dev/quant/quantbuildv1/.venv/bin/python quantmetrics.py build -c configs/demo_strict_ctrader.yaml
# Ctrl+B dan D om los te laten
```

**cTrader demo-account — echte API-orders (geen cash op live broker-account):** zet **`CTRADER_*`** + **`QUANTBRIDGE_SRC_PATH`**, cTrader desktop ingelogd, QuantBridge-deps geïnstalleerd. Start met **`quantmetrics.py build --real -c configs/demo_strict_ctrader.yaml`** (of `strict_prod_v2_ctrader_icmarkets.yaml`). Zonder **`--real`** blijft het dry-run.

**Demo losser (funnel / minder `regime_block`):** **`configs/demo_loose_ctrader.yaml`** — `filters.regime` uit, lossere entry-regels; QuantLog-pad `data/quantlog_events_demo_loose`. Gebruik expliciet `-c configs/demo_loose_ctrader.yaml` (niet alleen strict hernoemen).

**cTrader connect faalt:** `set -a; source …/orchestrator/.env; set +a` en daarna **`python scripts/diagnose_ctrader_connect.py -c configs/demo_loose_ctrader.yaml`** — JSON met TCP-check, SDK-import en `failure_detail` (token wordt niet volledig gelogd).

**Handmatig vanuit `quantbuildv1` met secrets in `orchestrator/.env`:** `quantmetrics.py` laadt die `.env`; een kale `python -m src.quantbuild.app …` **niet**. Gebruik:  
`chmod +x scripts/vps/run_live.sh` (eenmalig)  
`./scripts/vps/run_live.sh --config configs/demo_strict_ctrader.yaml live --dry-run`  
(of zet `QUANTBUILD_ORCHESTRATOR_ENV=/pad/naar/orchestrator/.env`). Anders: `source …/orchestrator/.env` vóór `python -m …`.

**Zonder cTrader** (alleen Oanda practice + andere datafeeds): `demo_strict_prod_v2.yaml` / `demo_loose_prod_v2.yaml` + `OANDA_*` — zie `docs/CREDENTIALS_AND_ENVIRONMENT.md`.

*(Zie ook `quantmetrics.py build --help`.)*

**Telegram bij suite start/stop (versie + instellingen):** zet in je YAML `monitoring.telegram.enabled: true` + bot/chat (of env-vars). Daarna:

- **Start vóór live:**  
  `quantmetrics.py build --notify-start -c configs/demo_strict_ctrader.yaml`  
  (stuurt `suite-notify start` met **QuantBuild-versie**, **git short SHA** — of `QUANTBUILD_GIT_REVISION` — en **samenvatting**: config-pad, dry_run/real, symbol, broker, data source, QuantLog, strategy, guards, filters).  
  Optioneel: `--notify-components "build bridge quantlog"` (default).

- **Handmatig zelfde bericht:**  
  `python -m src.quantbuild.app --config configs/demo_strict_ctrader.yaml suite-notify start build bridge quantlog --dry-run`  
  of `--real` i.p.v. `--dry-run`.

- **Stop** (bijv. bij `systemctl stop`, of handmatig):  
  `python -m src.quantbuild.app --config configs/demo_strict_ctrader.yaml suite-notify stop build bridge quantlog --reason "systemd stop"`  
  Zelfde versie/instellingenblok als bij start. In systemd: `ExecStopPost=.../python -m src.quantbuild.app --config ... suite-notify stop ...` (paden aanpassen).

### 0.4 QuantLog “live” controleren

Gebruikt de **echte** `WorkingDirectory` van de draaiende unit (geen hardcoded `cd`). Unit-naam aanpassen als je service anders heet.

```bash
DAY=$(date -u +%F)
WORKDIR=$(systemctl show quantbuild-ctrader-demo.service -p WorkingDirectory --value)
LOG="$WORKDIR/data/quantlog_events/$DAY/quantbuild.jsonl"

echo "=== $DAY Event Log ==="
echo "File: $LOG"
echo
echo "=== Last 5 entries ==="
tail -n 5 "$LOG" | jq . 2>/dev/null || tail -n 5 "$LOG"
```

Zie je geen map/bestand: check YAML `quantlog:` (`enabled`, `base_path`) en of de bot echt draait. (`jq` is optioneel; zonder `jq` vallen de laatste regels terug op ruwe JSONL.)

### 0.5 Nightly rapport (validate + summarize vorige UTC-dag)

**Timer** (eenmalig): standaard unit-bestanden gebruiken `/opt/quantbuild/quantbuildv1` — pas **`deploy/systemd/quantbuild-quantlog-report.service`** naar jouw pad aan **of** kopieer handmatig naar `/etc/systemd/system/` met juiste paden, daarna `install_quantlog_nightly_timer.sh` (of handmatig `systemctl enable --now` op timer). Zie §9.

**Handmatig nu** (zonder systemd, jouw pad):

```bash
export QUANTBUILD_ROOT=/root/dev/quant/quantbuildv1
export QUANTBUILD_POST_RUN_CONFIG=configs/strict_prod_v2.yaml
export QUANTLOG_REPO_PATH=/root/dev/quant/quantlogv1
cd "$QUANTBUILD_ROOT" && source .venv/bin/activate
mkdir -p logs
bash scripts/vps/quantlog_nightly.sh 2>&1 | tee -a logs/quantlog_nightly_manual.log
```

`QUANTBUILD_POST_RUN_CONFIG` moet dezelfde logische setup zijn als je runtime-config: **`quantlog.enabled: true`** en hetzelfde **`quantlog.base_path`** als waar JSONL naartoe schrijft. Staat `enabled` niet in jouw YAML, dan blijft na merge **`default.yaml` → false** en stopt `quantlog_post_run.py` met exit 2 — ook al bestaat er wél JSONL. Oplossing: `git pull` (demo/prod YAML’s in repo zetten `enabled: true`) of handmatig `enabled: true` toevoegen.

**QuantLog-repo-pad:** zet **`QUANTLOG_REPO_PATH`** (of alias **`QUANTLOG_ROOT`**) naar je clone, bv. `/root/dev/quant/quantlogv1`. Zonder geldige clone faalt post-run vóór validate.

**Quality score / exit 1:** `quantlog_post_run.py` eindigt met exit **1** als `score-run` onder de drempel zit (default **95**). In **dry-run** met weinig `trade_executed`-events is een lagere score normaal. Voor alleen pipeline-checks: `--pass-threshold 0` of een lagere waarde meegeven.

*(Alleen nodig als je geen timer hebt; de timer schrijft naar `logs/quantlog_nightly.log` via systemd.)*

### 0.6b Edge Unlock — backtest 2025 + discovery dry-run + daily review

**Backtest heel 2025** (zelfde stack als `configs/edge_unlock_discovery.yaml`; cache: `data/README_MARKET_CACHE.md`):

```bash
python -m src.quantbuild.app --config configs/backtest_2025_edge_unlock.yaml backtest
```

Dukascopy-cache pad: `configs/backtest_2025_edge_unlock_dukascopy.yaml` (zelfde commando, ander `--config`).

**OHLC cache vullen / verlengen (XAUUSD 15m + 1h, lang venster):**

```bash
python scripts/fetch_dukascopy_xauusd.py --days 550 --tf 15m 1h
```

**Discovery live/paper (standaard dry-run):**

```bash
python -m src.quantbuild.app --config configs/edge_unlock_discovery.yaml live --dry-run
```

**Compacte metrics uit QuantLog JSONL:**

```bash
python scripts/edge_unlock_daily_review.py data/quantlog_events/runs/bt_2025_edge_unlock.jsonl
```

### 0.6 Logs volgen

- **File log** (cTrader-demo unit, huidige VPS): `tail -f /opt/quantbuild/quantbuild_e1_v1/logs/runtime_ctrader_demo.log` — elders vaak `…/quantbuildv1/logs/runtime_ctrader_demo.log`
- **Journald:** `journalctl -u quantbuild-ctrader-demo.service -f`
- **Orchestrator / stdout:** output in je tmux-paneel

---

## 1) Daily Check (copy/paste)

```bash
sudo systemctl is-active quantbuild-ctrader-demo.service
# Huidige VPS (e1):
tail -n 80 /opt/quantbuild/quantbuild_e1_v1/logs/runtime_ctrader_demo.log
# Andere install (repo-standaard):
# cd /opt/quantbuild/quantbuildv1 && tail -n 80 logs/runtime_ctrader_demo.log
```

Snelle signalen:
- Goed: `Connected to cTrader OpenAPI`, `ProtoOAReconcileRes`, `decision_cycle`
- Fout: `market_data_bootstrap_failed`, `QuantBridge cTrader connect failed`

---

## 2) Daily Update + Restart

```bash
cd /opt/quantbuild/quantbridgev1
git fetch origin
git checkout main
git pull --ff-only

cd /opt/quantbuild/quantlogv1
git fetch origin
git checkout main
git pull --ff-only

cd /opt/quantbuild/quantbuildv1
git fetch origin
git checkout v2-development
git pull --ff-only

sudo systemctl restart quantbuild-ctrader-demo.service
sudo systemctl is-active quantbuild-ctrader-demo.service
```

Zie `docs/VPS_MULTI_MODULE_DEPLOYMENT.md`: na pull eventueel `pip install -r requirements.txt` en/of `pip install -e /opt/quantbuild/quantlogv1` in **QuantBuild** `.venv` vóór restart.

**Eerste keer op deze VPS:** als `ls /opt/quantbuild/quantlogv1` faalt → in `/opt/quantbuild` uitvoeren: `git clone <jouw-QuantLog-repo-URL> quantlogv1`, daarna `pip install -e /opt/quantbuild/quantlogv1` in de QuantBuild-venv. Zonder deze clone werkt `python -m quantlog.cli` / `scripts/quantlog_post_run.py` niet op de server (events staan wél in `data/quantlog_events/`).

---

## 2.6) Nieuwe Telegram-bot (schone start)

Gebruik dit als je **opnieuw** begint (nieuwe bot, nieuwe chat, of oude token gelekt).

1. Open Telegram → **@BotFather** → `/newbot` → kies weergavenaam en username → kopieer de **HTTP API token** (alleen in je **env** of secret store; **nooit** in git of YAML committen).
2. Zoek je bot op in Telegram en stuur **`/start`** (of een willekeurig bericht) zodat er een conversatie bestaat.
3. **Chat-ID bepalen** (voorbeelden):
   - Eén-op-eén: na stap 2:  
     `curl -s "https://api.telegram.org/bot<JE_TOKEN>/getUpdates"` — in de JSON zoek je `chat":{"id": …}`.
   - **Groep:** voeg de bot toe, stuur een bericht in de groep, zelfde `getUpdates`; groep-`id` is vaak **negatief**.
4. Zet op de VPS in **`orchestrator/.env`** of **`/etc/quantbuild/quantbuild.env`** (of export vóór start):
   - `TELEGRAM_BOT_TOKEN=…`
   - `TELEGRAM_CHAT_ID=…` (string; mag negatief voor groepen)
   - `TELEGRAM_ENABLED=true`
   - Aanrader: **`TELEGRAM_INSTANCE_LABEL=…`** (bijv. `VPS-CTRADER-2026-04`) zodat meldingen van deze run herkenbaar zijn.
5. **YAML:** in veel demo-configs staat `monitoring.telegram.enabled: false`. Dat is oké: **`TELEGRAM_ENABLED=true` in de omgeving overschrijft** dit via `config.py` zolang token/chat_id gezet zijn. Wil je liever alles in YAML, zet daar `enabled: true` en placeholders — secrets blijven uit git via env-overrides.
6. **Oude bot niet meer gebruiken?** Bij BotFather: `/mybots` → bot → **API Token** → **Revoke** — daarna is alleen de **nieuwe** token geldig.
7. Verificatie: hieronder **§3 Quick Test**.

---

## 3) Telegram Quick Test

```bash
set -a; source /etc/quantbuild/quantbuild.env; set +a
# of: set -a; source /root/dev/quant/quantmetrics_os/orchestrator/.env; set +a
curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
  -d "chat_id=${TELEGRAM_CHAT_ID}" \
  -d "text=VPS operator test ✅"
```

---

## 4) Strict cTrader Data Gate (preflight)

Gebruik dit alleen als je strict broker-native candles wil afdwingen.

```bash
cd /opt/quantbuild/quantbuildv1
source .venv/bin/activate
set -a; source /etc/quantbuild/quantbuild.env; set +a
python -m src.quantbuild.app --config configs/preflight_live_ctrader.yaml live --dry-run
```

NO-GO signalen:
- `live_data_refresh_fail_fast requested=ctrader`
- `market_data_bootstrap_failed`
- `received=0`

---

## 5) Service Control

```bash
sudo systemctl start quantbuild-ctrader-demo.service
sudo systemctl stop quantbuild-ctrader-demo.service
sudo systemctl restart quantbuild-ctrader-demo.service
sudo systemctl status quantbuild-ctrader-demo.service --no-pager
```

---

## 6) Logs

```bash
tail -f /opt/quantbuild/quantbuild_e1_v1/logs/runtime_ctrader_demo.log
# repo-standaard: tail -f /opt/quantbuild/quantbuildv1/logs/runtime_ctrader_demo.log
journalctl -u quantbuild-ctrader-demo.service -n 120 --no-pager
```

---

## 7) Incident Playbook

### A) Service is not active

```bash
sudo systemctl restart quantbuild-ctrader-demo.service
sudo systemctl status quantbuild-ctrader-demo.service --no-pager
tail -n 120 /opt/quantbuild/quantbuild_e1_v1/logs/runtime_ctrader_demo.log
```

### B) cTrader connect fails

```bash
cd /opt/quantbuild/quantbuildv1
set -a; source /etc/quantbuild/quantbuild.env; set +a
python scripts/ctrader_smoke.py --config configs/ctrader_quantbridge_openapi.yaml
```

### C) Telegram stil

```bash
set -a; source /etc/quantbuild/quantbuild.env; set +a
echo "ENABLED=$TELEGRAM_ENABLED CHAT_ID=$TELEGRAM_CHAT_ID LABEL=$TELEGRAM_INSTANCE_LABEL"
curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
  -d "chat_id=${TELEGRAM_CHAT_ID}" \
  -d "text=Telegram recovery ping"
```

---

## 8) Environment Labels (aanrader)

Gebruik verschillende labels zodat Telegram duidelijk is:

- VPS: `TELEGRAM_INSTANCE_LABEL=VPS-LIVE`
- Local: `TELEGRAM_INSTANCE_LABEL=LOCAL-DEV`

---

## 9) QuantLog nightly (optioneel)

Vereist: `quantlogv1` gecloned + `pip install -e /opt/quantbuild/quantlogv1` in QuantBuild `.venv`.

Eenmalig installeren (timer = elke dag ~00:20 **serverlocal time**; zet VPS op UTC met `timedatectl set-timezone UTC` zodat dit gelijk is aan UTC):

```bash
cd /opt/quantbuild/quantbuildv1
chmod +x scripts/vps/install_quantlog_nightly_timer.sh scripts/vps/quantlog_nightly.sh
./scripts/vps/install_quantlog_nightly_timer.sh
sudo systemctl list-timers | grep quantlog
```

Handmatig één run (gisteren UTC):

```bash
sudo systemctl start quantbuild-quantlog-report.service
tail -n 80 /opt/quantbuild/quantbuildv1/logs/quantlog_nightly.log
```

Optioneel in `/etc/quantbuild/quantbuild.env`: `QUANTBUILD_POST_RUN_CONFIG=configs/jouw.yaml`, `QUANTLOG_REPO_PATH=...`.

---

## 10) P1.4 — validate-events op productiedata

Na een deploy met correlatie-fix: op de VPS (met QuantLog CLI werkend):

```bash
cd /opt/quantbuild/quantbuildv1 && source .venv/bin/activate
python -m quantlog.cli validate-events --path data/quantlog_events/2026-04-02
```

Geen structurele `invalid_run_id` / `invalid_session_id` verwacht.

---

## 11) QuantBuild ↔ QuantLog koppelcheck

Controleert: QuantLog-repo vindbaar, `validate-events` op de **test-fixture**, en gelijkheid van **NO_ACTION**-reason sets (Build vs QuantLog schema).

```bash
cd /opt/quantbuild/quantbuildv1
source .venv/bin/activate
python scripts/check_quantlog_linkage.py
```

- **Geen clone:** script eindigt met **exit 0** maar print **`WARNING`** op stderr → zelfde als GitHub Actions zonder QuantLog.
- **Strikte modus** (bijv. vóór release): `QUANTLOG_LINKAGE_STRICT=1 python scripts/check_quantlog_linkage.py` of `python scripts/check_quantlog_linkage.py --strict` → **exit 1** als repo ontbreekt of validatie/schema mismatch.

Zie ook runtime: bij `quantlog.enabled` zonder vindbare repo logt `live_runner` een **warning** bij start.

