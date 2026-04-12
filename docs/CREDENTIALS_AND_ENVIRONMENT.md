# Credentials en omgeving (single source of truth)

**Afspraak:** alle **secrets en gevoelige tokens** komen **uitsluitend** in de **proces-omgeving** terecht — wat Python ziet als `os.environ`. Niets daarvan hoort in git (geen YAML met echte keys, geen commits van `.env`).

Dit document is de **canonieke lijst** van variabelenamen en **waar** je ze zet. Andere runbooks (`VPS_DEPLOYMENT_RUNBOOK.md`, `VPS_MULTI_MODULE_DEPLOYMENT.md`, `OPERATOR_CHEATSHEET.md`) verwijzen hiernaar.

---

## 1) Hoe “OS” in de praktijk werkt

| Situatie | Hoe variabelen in `os.environ` komen |
|----------|----------------------------------------|
| **Linux VPS + systemd** | `EnvironmentFile=/etc/quantbuild/quantbuild.env` in de unit (aanbevolen). Zie `deploy/systemd/quantbuild.env.example`. |
| **Handmatig op de server** | `export KEY=value` in je shell, of `set -a; source /etc/quantbuild/quantbuild.env; set +a`. |
| **Windows / lokaal** | Systeem-omgeving, PowerShell `$env:KEY="value"`, of een **lokale** `.env` naast de repo. |
| **Repo-root `.env` (lokaal)** | Bestand staat in `.gitignore`. Bij import laadt `src/quantbuild/config.py` `python-dotenv` (`load_dotenv(override=True)`), zodat dezelfde keys in **`os.environ`** belanden. Dat is **geen** tweede bron van waarheid — alleen een handige manier om de OS-env te vullen tijdens dev. |
| **Orchestrator (bijv. quantmetrics_os)** | Als een parent-proces subprocessen start: zet dezelfde `KEY=value` in de **omgeving van dat parent** (bijv. orchestrator-`.env` die vóór `subprocess` in `os.environ` wordt geladen). Het kind erft `os.environ`; er hoeft geen tweede “verborgen” plek te zijn. |
| **CI / cloud** | Secret manager of pipeline-variabelen → geïnjecteerd als environment op de job-runner. |

**Prioriteit in code:** overrides uit de omgeving gaan vóór platte waarden in YAML waar `config.py` dat expliciet merge’t (broker, news, AI, Telegram). Houd YAML dus vrij van echte secrets.

---

## 2) Variabelen die QuantBuild herkent (namen)

**Broker — Oanda**

- `OANDA_ACCOUNT_ID`
- `OANDA_TOKEN`

**Broker — cTrader (via QuantBridge)**

- `CTRADER_ACCOUNT_ID`
- `CTRADER_ACCESS_TOKEN`
- `CTRADER_CLIENT_ID`
- `CTRADER_CLIENT_SECRET`

**QuantBridge-pad (geen secret, wel verplicht op VPS voor cTrader-pad)**

- `QUANTBRIDGE_SRC_PATH` — bijv. `/opt/quantbuild/quantbridgev1/src`

**News / AI**

- `NEWSAPI_KEY`, `NEWSAPI_ENABLED`, `NEWSAPI_CATEGORIES`
- `FINNHUB_API_KEY`, `FINNHUB_ENABLED`, `FINNHUB_CATEGORY`
- `OPENAI_API_KEY`, `OPENAI_MODEL`

**Telegram**

- `TELEGRAM_ENABLED`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `TELEGRAM_SYSTEM_LABEL`, `TELEGRAM_INSTANCE_LABEL`
- `TELEGRAM_REPORT_INTERVAL_SECONDS`

**Data / config**

- `CONFIG_PATH` — alternatief YAML-pad
- `DATA_PATH`, `CACHE_TTL_HOURS`

**Sessie / tooling**

- `QUANTBUILD_SESSION_ID` (optioneel; o.a. live runner)
- `QUANTLOG_REPO_PATH` — pad naar quantlog-repo (scripts / post-run)

**Launch / nightly (optioneel)**

- `QUANTBUILD_POST_RUN_CONFIG` — YAML voor post-run scripts (zie operator-cheatsheet)

Zie `src/quantbuild/config.py` voor de exacte merge-logica.

---

## 3) `scripts/launch_live_safe.py` en QuantBridge-`.env`

Preflight/lancering leest cTrader-credentials in deze volgorde: **`os.environ` → waarden uit geladen config (YAML) → optioneel** `quantbridgev1/local.env` en **`.env`** (alleen als die bestaan op de bridge-checkout). **Productie:** zet alles in **`os.environ`** (systemd `EnvironmentFile`); dan zijn bridge-`.env`-bestanden overbodig en hoef je geen secrets naast de bridge-repo te bewaren.

---

## 4) Waar je niets zet

- Geen echte tokens in **README**, **Markdown-voorbeelden**, **issue/PR-tekst**, of **gecommit YAML**.
- Geen `quantbuild.env` met echte waarden in de repo — alleen `deploy/systemd/quantbuild.env.example` met lege of placeholder-waarden.
- De root **`.env`** is lokaal en **gitignored**; commit die nooit.

---

## 5) Snelle copy-paste (alleen namen)

Template zonder waarden: **`.env.example`** in de repo-root en **`deploy/systemd/quantbuild.env.example`** voor VPS/systemd.

Als je twijfelt of een nieuwe secret een eigen env-naam nodig heeft: voeg die toe in `config.py` (of de betreffende broker-module) **en** actualiseer dit document en `.env.example`.
