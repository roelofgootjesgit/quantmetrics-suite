# QuantLog op de VPS — aansluiting op de QuantBuild-workflow

**Dit bestand is geen tweede waarheid.** De volledige afspraken voor venv, Python-versie, paden en push/pull staan in **QuantBuild**:

| Bron (QuantBuild repo) | Inhoud |
|------------------------|--------|
| `docs/VPS_MULTI_MODULE_DEPLOYMENT.md` | **Contract:** Python **3.10.x**, één `.venv` alleen in `quantbuildv1`, geen tweede bot-venv voor Bridge, `QUANTBRIDGE_SRC_PATH`, pull-volgorde, systemd-pad, checklist |
| `docs/OPERATOR_CHEATSHEET.md` | Dagelijkse **copy/paste**: bridge pull → build pull → `systemctl restart` |
| `docs/VPS_DEPLOYMENT_RUNBOOK.md` | Install, systemd, health |

QuantLog voegt alleen toe: **waar de derde repo staat**, **hoe die in dezelfde ritme past**, en **hoe je de CLI draait zonder een aparte QuantLog-venv** op productie.

---

## 1) Zelfde principes als QuantBridge (geen eigen productie-venv)

Zoals in `VPS_MULTI_MODULE_DEPLOYMENT.md` §4: **QuantBridge** heeft op productie **geen** eigen `.venv` — code staat op schijf en de bot draait met **QuantBuild’s** interpreter.

**QuantLog idem:**

- Clone onder `/opt/quantbuild/quantlogv1` (of de naam van jouw GitHub-repo).
- **Maak geen** `python3 -m venv` in QuantLog voor de standaard VPS-setup.
- Gebruik voor handmatige commands: **QuantBuild’s venv** activeren, daarna QuantLog via **`pip install -e`** of **`PYTHONPATH`** (zie §5).

Zo blijft er **één** Python-wereld: `quantbuildv1/.venv`, versie **3.10.x**, zoals het contract voorschrijft.

---

## 2) Directory layout (uitbreiding op QuantBuild §3)

```text
/opt/quantbuild/quantbuildv1     ← enige bot-venv: .venv hier
/opt/quantbuild/quantbridgev1      ← bron, geen productie-venv
/opt/quantbuild/quantlogv1         ← bron, geen productie-venv
/etc/quantbuild/quantbuild.env       ← o.a. QUANTBRIDGE_SRC_PATH
```

Event-JSONL staat **niet** in de QuantLog-repo, maar volgt QuantBuild-config (`quantlog.base_path`, typisch `data/quantlog_events/<datum>/` onder `quantbuildv1`).

---

## 3) Eerste keer: QuantLog clonen (geen venv in deze map)

```bash
cd /opt/quantbuild
git clone <JOUW_QUANTLOG_REPO_URL> quantlogv1
```

**Optioneel** — QuantLog als editable package in **QuantBuild’s** venv (één interpreter):

```bash
cd /opt/quantbuild/quantbuildv1
source .venv/bin/activate
python --version   # moet 3.10.x zijn
pip install -e /opt/quantbuild/quantlogv1
deactivate
```

Als je **geen** `pip install -e` wilt: voor CLI-scripts kun je hetzelfde doen als `scripts/quantlog_post_run.py` in QuantBuild — `PYTHONPATH=/opt/quantbuild/quantlogv1/src` zetten bij aanroep met `quantbuildv1/.venv/bin/python`.

---

## 4) Lokaal: push (ontwikkelmachine)

Niet anders dan normale Git-gewoonte:

```bash
git status
git add … && git commit -m "…"
git push origin <jouw-branch>
```

Op de VPS gebeurt **geen** push naar productie; alleen **`git pull --ff-only`** (zie hieronder).

---

## 5) VPS: dagelijkse update — zelfde blok als Operator Cheat Sheet + QuantLog

**Exact de volgorde uit** `OPERATOR_CHEATSHEET.md` §2, met **QuantLog** tussen Bridge en Build (beide zijn bron-repos vóór je de app herstart).

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
```

**Daarna** (alleen als `requirements.txt` van QuantBuild wijzigde — zie `VPS_MULTI_MODULE_DEPLOYMENT.md` §5.1):

```bash
cd /opt/quantbuild/quantbuildv1
source .venv/bin/activate
python --version
pip install -r requirements.txt
pip install -e /opt/quantbuild/quantlogv1
deactivate
```

**Herstart** (zelfde als cheatsheet):

```bash
sudo systemctl restart quantbuild-ctrader-demo.service
sudo systemctl is-active quantbuild-ctrader-demo.service
```

*Unit-naam kan afwijken; pas aan jouw systemd-unit aan.*

---

## 6) QuantLog CLI / validatie op de VPS

Altijd vanuit **QuantBuild**-map met **geactiveerde `.venv`** (of volledige pad naar `.venv/bin/python`):

```bash
cd /opt/quantbuild/quantbuildv1
source .venv/bin/activate
python -m quantlog.cli validate-events --path data/quantlog_events/2026-04-01
deactivate
```

Werkt `python -m quantlog.cli` niet: `pip install -e /opt/quantbuild/quantlogv1` opnieuw uitvoeren in deze venv, of tijdelijk:

```bash
PYTHONPATH=/opt/quantbuild/quantlogv1/src python -m quantlog.cli validate-events --path …
```

---

## 7) QuantBuild `quantlog_post_run.py`

Blijft zoals in QuantBuild gedocumenteerd; op de VPS hoort `--quantlog-repo-path` naar de clone:

```bash
cd /opt/quantbuild/quantbuildv1
source .venv/bin/activate
python scripts/quantlog_post_run.py \
  --config configs/ctrader_quantbridge_openapi.yaml \
  --quantlog-repo-path /opt/quantbuild/quantlogv1 \
  --date 2026-04-01
```

---

## 8) Checklist-uitbreiding (naast QuantBuild §9)

Na elke deploy ook:

- [ ] **QuantLog:** juiste branch, `git pull --ff-only` zonder conflicts  
- [ ] QuantLog-code gewijzigd en je gebruikt `pip install -e`? → opnieuw `pip install -e /opt/quantbuild/quantlogv1` in **QuantBuild** `.venv`  
- [ ] Geen `python`/`pip` voor de stack **buiten** `quantbuildv1/.venv` (zie `VPS_MULTI_MODULE_DEPLOYMENT.md` §6)

---

## 9) Dit bestand synchron houden

Bij wijzigingen aan **branches** (`main` / `v2-development`) of **unit-namen**: pas eerst **QuantBuild** `OPERATOR_CHEATSHEET.md` / `VPS_MULTI_MODULE_DEPLOYMENT.md` aan, daarna dit bestand dezelfde waarden geven.

*QuantLog — afgestemd op QuantBuild `docs/VPS_MULTI_MODULE_DEPLOYMENT.md` (Python 3.10, single venv, drie-repo pull).*
