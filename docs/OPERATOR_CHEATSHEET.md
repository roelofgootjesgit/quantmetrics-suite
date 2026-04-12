# QuantBuild Operator Cheat Sheet

Korte operationele sheet voor dagelijkse run op VPS.

**Secrets:** staan in de **OS-omgeving**; op de VPS in `/etc/quantbuild/quantbuild.env` (systemd `EnvironmentFile=`) **of** in **`quantmetrics_os/orchestrator/.env`** als je via de orchestrator start. Lijst met alle variabelenamen: **`docs/CREDENTIALS_AND_ENVIRONMENT.md`**.

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
/root/dev/quant/quantbuildv1/.venv/bin/python quantmetrics.py build -c configs/strict_prod_v2.yaml
# Ctrl+B dan D om los te laten
```

*(Voeg `--dry-run` of `--real` toe zoals je policy is; zie `quantmetrics.py --help`.)*

### 0.4 QuantLog “live” controleren

```bash
cd /root/dev/quant/quantbuildv1
DAY=$(date -u +%Y-%m-%d)
ls -la "data/quantlog_events/$DAY"
tail -n 5 "data/quantlog_events/$DAY/quantbuild.jsonl"
```

Zie je geen map/bestand: check YAML `quantlog:` (`enabled`, `base_path`) en of de bot echt draait.

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

### 0.6 Logs volgen

- **File log** (cTrader-demo unit): `tail -f …/logs/runtime_ctrader_demo.log`
- **Journald:** `journalctl -u quantbuild-ctrader-demo.service -f`
- **Orchestrator / stdout:** output in je tmux-paneel

---

## 1) Daily Check (copy/paste)

```bash
cd /opt/quantbuild/quantbuildv1
sudo systemctl is-active quantbuild-ctrader-demo.service
tail -n 80 logs/runtime_ctrader_demo.log
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

## 3) Telegram Quick Test

```bash
set -a; source /etc/quantbuild/quantbuild.env; set +a
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
tail -f /opt/quantbuild/quantbuildv1/logs/runtime_ctrader_demo.log
journalctl -u quantbuild-ctrader-demo.service -n 120 --no-pager
```

---

## 7) Incident Playbook

### A) Service is not active

```bash
sudo systemctl restart quantbuild-ctrader-demo.service
sudo systemctl status quantbuild-ctrader-demo.service --no-pager
tail -n 120 /opt/quantbuild/quantbuildv1/logs/runtime_ctrader_demo.log
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

