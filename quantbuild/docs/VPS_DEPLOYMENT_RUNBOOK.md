# QuantBuild VPS Deployment Runbook

Praktische handleiding om QuantBuild + QuantBridge op een Linux VPS te deployen en 1 week stabiel te laten draaien met echte orders op een cTrader demo-account.

**Secrets en env-variabelen:** de **bron van waarheid** is altijd de **OS-omgeving** (`os.environ`) — op de VPS typisch via systemd `EnvironmentFile`. Volledige lijst en afspraken: **`docs/CREDENTIALS_AND_ENVIRONMENT.md`**.

**Editor / SSH-key / VS Code Remote:** zie `docs/VPS_SSH_VSCODE_SETUP.md` (start-checklist voor nieuwe VPS of nieuwe machine).

---

## 1) Scope en Doel

- Doel: operationele stabiliteit valideren (niet PnL-optimalisatie).
- Mode: live op demo-account (`--real`) met `data.source=ctrader` (strict).
- Verwachting: broker-native candles, fail-fast bij ontbrekende cTrader data, volledige decision audit trail.

---

## 2) Vereisten

- Ubuntu 22.04+ (of vergelijkbare Linux distro)
- Python 3.11+
- `git`, `venv`, `pip`
- Toegang tot cTrader credentials
- QuantBridge repository beschikbaar op de VPS

---

## 3) Directory Layout (aanbevolen)

```text
/opt/quantbuild/quantbuild
/opt/quantbuild/quantbridge
/opt/quantbuild/quantlog    # optioneel; event spine + post_run — zie docs/VPS_MULTI_MODULE_DEPLOYMENT.md
```

---

## 4) Installatie op VPS

Snelle route (scripts in deze repo):

```bash
cd /opt/quantbuild/quantbuild
chmod +x scripts/vps/bootstrap_vps.sh scripts/vps/install_systemd_service.sh
./scripts/vps/bootstrap_vps.sh <JOUW_QUANTBUILD_REPO_URL> <JOUW_QUANTBRIDGE_REPO_URL>
```

Handmatig:

```bash
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip

sudo mkdir -p /opt/quantbuild
sudo chown -R $USER:$USER /opt/quantbuild
cd /opt/quantbuild

git clone <JOUW_QUANTBUILD_REPO_URL> quantbuild
git clone <JOUW_QUANTBRIDGE_REPO_URL> quantbridge

cd /opt/quantbuild/quantbuild
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

---

## 5) Secrets en Environment

Gebruik **alleen** environment-variabelen voor credentials; commit **geen** secrets in YAML of git. Zie **`docs/CREDENTIALS_AND_ENVIRONMENT.md`** voor alle ondersteunde namen en voor orchestrator/subprocess.

```bash
export CTRADER_ACCOUNT_ID="..."
export CTRADER_ACCESS_TOKEN="..."
export CTRADER_CLIENT_ID="..."
export CTRADER_CLIENT_SECRET="..."
export QUANTBRIDGE_SRC_PATH="/opt/quantbuild/quantbridge/src"

# News + LLM
export FINNHUB_API_KEY="..."
export OPENAI_API_KEY="..."
# optioneel backup news source
export NEWSAPI_KEY="..."

# Telegram
export TELEGRAM_ENABLED="true"
export TELEGRAM_BOT_TOKEN="..."
export TELEGRAM_CHAT_ID="..."
export TELEGRAM_INSTANCE_LABEL="VPS"
```

Tip: zet deze in een service env-file (`/etc/quantbuild/quantbuild.env`).

---

## 6) Nieuwe SSH Sessie (altijd eerst)

Nieuwe PuTTY/SSH sessie start zonder actieve venv. Gebruik steeds:

```bash
cd /opt/quantbuild/quantbuild
source .venv/bin/activate
which python
```

Verwacht pad:

```text
/opt/quantbuild/quantbuild/.venv/bin/python
```

---

## 7) Config voor Runtime Testfase

Gebruik:

- `configs/ctrader_quantbridge_openapi.yaml`
- `data.source: ctrader`
- `broker.mock_mode: false`
- run command (demo-account, echte demo-orders):

```bash
cd /opt/quantbuild/quantbuild
source .venv/bin/activate
python -m src.quantbuild.app --config configs/ctrader_quantbridge_openapi.yaml live --real
```

---

## 8) News Intelligence Validatie (strict_prod_v2)

Voor news-gate + sentiment + LLM advisor + Telegram news-impact alerts:

```bash
cd /opt/quantbuild/quantbuild
source .venv/bin/activate

# 1) News ingest smoke test
python -m src.quantbuild.app --config configs/strict_prod_v2.yaml news-test

# 2) Telegram news-impact testbericht
python -c "from src.quantbuild.config import load_config; from src.quantbuild.alerts.telegram import TelegramAlerter; c=load_config('configs/strict_prod_v2.yaml'); t=TelegramAlerter(c); print('sent=', t.alert_news_event('VPS test news impact', 'VPS', 'bullish', 0.77, 'system/test'))"

# 3) Dry-run met volledige decision kernel
python -m src.quantbuild.app --config configs/strict_prod_v2.yaml live --dry-run
```

Belangrijke logregels tijdens dry-run:

- `Relevance filter: X/Y events passed`
- `News budget: dropped ... stale events`
- `News budget: processing ... dropped ... by poll cap`
- `LLM advisor ...` (block/suppress/boost)

---

## 9) Preflight Checks (verplicht)

### A. Truth-mode check (ctrader only, verwacht fail-fast als candles niet beschikbaar zijn)

```bash
python -m src.quantbuild.app --config configs/preflight_live_ctrader.yaml live --dry-run
```

Verwacht:
- `bootstrap_truth_mode ... cache_bypass=true`
- bij ontbrekende broker candles: `live_data_refresh_fail_fast`

### B. Auto check (verwacht bootstrap success)

Voor strict cTrader-run is deze stap optioneel en niet onderdeel van productiebeleid.

---

## 10) Systemd Service (aanbevolen)

Maak env-file (voorbeeld staat in `deploy/systemd/quantbuild.env.example`):

```bash
sudo mkdir -p /etc/quantbuild
sudo tee /etc/quantbuild/quantbuild.env >/dev/null <<'EOF'
CTRADER_ACCOUNT_ID=...
CTRADER_ACCESS_TOKEN=...
CTRADER_CLIENT_ID=...
CTRADER_CLIENT_SECRET=...
QUANTBRIDGE_SRC_PATH=/opt/quantbuild/quantbridge/src
EOF
```

Maak service:

```bash
sudo tee /etc/systemd/system/quantbuild-ctrader-demo.service >/dev/null <<'EOF'
[Unit]
Description=QuantBuild cTrader Demo Runtime
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/quantbuild/quantbuild
EnvironmentFile=/etc/quantbuild/quantbuild.env
ExecStart=/opt/quantbuild/quantbuild/.venv/bin/python scripts/launch_live_safe.py --config configs/ctrader_quantbridge_openapi.yaml --max-runtime-seconds 604800 --heartbeat-seconds 30 --skip-recovery
Restart=always
RestartSec=10
StandardOutput=append:/opt/quantbuild/quantbuild/logs/runtime_ctrader_demo.log
StandardError=append:/opt/quantbuild/quantbuild/logs/runtime_ctrader_demo.log

[Install]
WantedBy=multi-user.target
EOF
```

Start service:

```bash
sudo systemctl daemon-reload
sudo systemctl enable quantbuild-ctrader-demo.service
sudo systemctl start quantbuild-ctrader-demo.service
sudo systemctl status quantbuild-ctrader-demo.service --no-pager
```

Of via repo script:

```bash
cd /opt/quantbuild/quantbuild
chmod +x scripts/vps/start_weekrun.sh
./scripts/vps/start_weekrun.sh
```

Logs volgen:

```bash
tail -f /opt/quantbuild/quantbuild/logs/runtime_ctrader_demo.log
```

### QuantLog nightly timer (optioneel)

Valideert/summariseert de **vorige UTC-dag** (`scripts/vps/quantlog_nightly.sh`). Zet de server op **UTC** (`timedatectl set-timezone UTC`) of pas `deploy/systemd/quantbuild-quantlog-report.timer` aan.

```bash
cd /opt/quantbuild/quantbuild
chmod +x scripts/vps/install_quantlog_nightly_timer.sh scripts/vps/quantlog_nightly.sh
./scripts/vps/install_quantlog_nightly_timer.sh
```

Zie ook `docs/OPERATOR_CHEATSHEET.md` §9.

---

## 11) Week-Run Acceptatiecriteria

### Must pass

- Geen `market_data_bootstrap_failed`
- Geen terugkerende `received=0` in signal path
- `bootstrap_source_coherence_ok` bij startup
- `decision_cycle` aanwezig met `action` en `reason`
- Proces blijft draaien (of herstart gecontroleerd via systemd)

### Investigate

- Veel `bars_missing`
- Veel `same_bar_already_processed` zonder nieuwe bars over langere periode
- Veel guard blocks zonder marktcontextverklaring

### Fail

- Herhaalde crash loops
- Onverklaarbare exits zonder service restart
- Structureel ontbrekende decision logs

---

## 12) Dagelijkse Controle (snelle routine)

```bash
sudo systemctl status quantbuild-ctrader-demo.service --no-pager
rg "BOOTSTRAP|decision_cycle|market_data_bootstrap_failed|live_data_refresh_fail_fast|Relevance filter|News budget|LLM advisor|ERROR" /opt/quantbuild/quantbuild/logs/runtime_ctrader_demo.log
```

Of via script:

```bash
cd /opt/quantbuild/quantbuild
chmod +x scripts/vps/daily_health_check.sh
./scripts/vps/daily_health_check.sh
```

---

## 13) Na 1 Week: Go/No-Go

- **GO naar langere paper-run** als stabiliteit + decision trace consistent zijn.
- **NO-GO** als data-integriteit of decision observability gaten toont.
- Pas naar real execution wanneer cTrader candle path volledig bewezen is, of wanneer je live-data policy formeel is goedgekeurd.

