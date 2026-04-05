# QuantBuild Operator Cheat Sheet

Korte operationele sheet voor dagelijkse run op VPS.

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

