# QuantBuild Operator Cheat Sheet

Korte operationele sheet voor dagelijkse run op VPS.

---

## 1) Daily Check (copy/paste)

```bash
cd /opt/quantbuild/quantbuild_e1_v1
sudo systemctl is-active quantbuild-ctrader-demo.service
tail -n 80 logs/runtime_ctrader_demo.log
```

Snelle signalen:
- Goed: `Connected to cTrader OpenAPI`, `ProtoOAReconcileRes`, `decision_cycle`
- Fout: `market_data_bootstrap_failed`, `QuantBridge cTrader connect failed`

---

## 2) Daily Update + Restart

```bash
cd /opt/quantbuild/quantBridge-v.1
git fetch origin
git checkout main
git pull --ff-only

cd /opt/quantbuild/quantlog-v.1
git fetch origin
git checkout main
git pull --ff-only

cd /opt/quantbuild/quantbuild_e1_v1
git fetch origin
git checkout v2-development
git pull --ff-only

sudo systemctl restart quantbuild-ctrader-demo.service
sudo systemctl is-active quantbuild-ctrader-demo.service
```

Zie `docs/VPS_MULTI_MODULE_DEPLOYMENT.md`: na pull eventueel `pip install -r requirements.txt` en/of `pip install -e /opt/quantbuild/quantlog-v.1` in **QuantBuild** `.venv` vóór restart.

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
cd /opt/quantbuild/quantbuild_e1_v1
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
cd /opt/quantbuild/quantbuild_e1_v1
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

