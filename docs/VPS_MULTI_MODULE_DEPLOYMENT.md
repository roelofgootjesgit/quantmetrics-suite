# VPS deployment alignment — meerdere modules (QuantBuild, QuantBridge, QuantLog)

Dit document is bedoeld om **hetzelfde te kopiëren of te linken in elke repo** (QuantBuild, QuantBridge, QuantLog, scripts). Zo blijft push/pull op de VPS voorspelbaar: één Python-versie, vaste paden, geen gemixte venv’s.

Gerelateerd: `docs/VPS_DEPLOYMENT_RUNBOOK.md` (stappen + systemd), `docs/OPERATOR_CHEATSHEET.md` (dagelijkse commands). QuantLog-repo: `docs/VPS_SYNC.md` (uitbreiding alleen voor de derde clone — **dit** bestand blijft de bron voor venv + volgorde).

---

## 1) Doel

- Na `git pull` op de VPS **niet** opnieuw in de war raken met Python-versies, verkeerde `python`, of een venv die per ongeluk opnieuw wordt aangemaakt met een andere minor.
- Duidelijk welke repo **welke venv** gebruikt, hoe QuantBuild naar QuantBridge wijst, en waar **QuantLog** op schijf staat (geen tweede bot-venv; zie §4).

---

## 2) Contract (afspraken — niet onderhandelbaar op productie-VPS)

| Afspraak | Waarde |
|----------|--------|
| Python op VPS | **3.10.x** (bijv. 3.10.13 via pyenv) |
| Runtime voor de bot | **Altijd** de interpreter uit `quantbuild_e1_v1/.venv/bin/python` |
| System `python3` | Alleen voor tooling; **niet** voor `pip install` van de bot |
| Nieuwe venv aanmaken | Alleen bewust, na doc lezen — geen `python3 -m venv` “ter fix” zonder reden |

**Gouden regel:** het `systemd`-unit (of handmatig starten) roept **nooit** `python3` of `python` zonder pad aan — alleen het volledige pad naar `.venv/bin/python` van QuantBuild.

---

## 3) Standaard directory-layout

Pas paden alleen aan als je weet waarom; anders houd je dit vast:

```text
/opt/quantbuild/quantbuild_e1_v1     ← hoofd-app, hier staat de .venv van de bot
/opt/quantbuild/quantBridge-v.1      ← library / OpenAPI-laag (geen tweede bot-venv nodig tenzij je bewust dev-test doet)
/opt/quantbuild/quantlog-v.1         ← event spine (validate / replay / CLI); geen eigen productie-venv
/etc/quantbuild/quantbuild.env       ← secrets + QUANTBRIDGE_SRC_PATH (niet in git)
```

JSONL-eventdagen staan **niet** in de QuantLog-repo: typisch onder QuantBuild, bv. `quantbuild_e1_v1/data/quantlog_events/<YYYY-MM-DD>/` (via config `quantlog.base_path`).

QuantBuild vindt QuantBridge via omgeving:

```bash
QUANTBRIDGE_SRC_PATH=/opt/quantbuild/quantBridge-v.1/src
```

(Zet dit in `/etc/quantbuild/quantbuild.env` en laad het via `EnvironmentFile=` in systemd.)

---

## 4) Welke repo heeft welke venv?

| Module | Repo op schijf | Virtualenv | `pip install` |
|--------|----------------|------------|----------------|
| **QuantBuild** (bot, systemd) | `quantbuild_e1_v1` | **Ja** — `.venv` | `requirements.txt` van **deze** repo |
| **QuantBridge** | `quantBridge-v.1` | **Nee** voor productie-run | QuantBuild’s venv bevat runtime-deps; bridge wordt als **bronpad** ingeladen |
| **QuantLog** | `quantlog-v.1` | **Nee** voor productie-run | Zelfde **QuantBuild** `.venv`; optioneel `pip install -e /opt/quantbuild/quantlog-v.1` voor `python -m quantlog.cli`. `scripts/quantlog_post_run.py` zet ook `PYTHONPATH` naar `quantlog-v.1/src` — dan is editable install niet verplicht voor post-run alleen |

**Waarom geen tweede venv voor alleen bridge op productie?**  
De live service start vanuit QuantBuild; die laadt `quantbridge` via `sys.path` + `QUANTBRIDGE_SRC_PATH`. Wijzigingen in bridge-code zijn dus: **pull in `quantBridge-v.1` → restart systemd** — geen aparte bridge-venv nodig, zolang je geen extra Python-packages in bridge toevoegt die niet in QuantBuild’s `requirements.txt` staan.

**Waarom geen QuantLog-eigen `.venv` op productie?**  
Hetzelfde principe: één interpreter (3.10.x) in QuantBuild’s venv. Na pull in `quantlog-v.1`: **herstart systemd** (als je runtime QuantLog-code pad gebruikt) en/of opnieuw `pip install -e …/quantlog-v.1` in QuantBuild’s venv als je de CLI zo aanroept.

Als je **wél** nieuwe pip-packages in QuantBridge introduceert: voeg ze toe aan QuantBuild `requirements.txt` (of documenteer een expliciete tweede venv — dat is een uitzondering, niet de standaard). QuantLog heeft normaal **geen** extra runtime-deps buiten de stdlib; blijft dat zo, dan volstaat `PYTHONPATH` of één `pip install -e`.

---

## 5) Push/pull workflow per module

### 5.1 QuantBuild

```bash
cd /opt/quantbuild/quantbuild_e1_v1
git fetch origin
git checkout v2-development    # of jouw vaste productie-branch
git pull --ff-only
```

**Na pull:**

```bash
source .venv/bin/activate
python --version    # moet 3.10.x tonen
pip install -r requirements.txt   # alleen als requirements.txt gewijzigd is
pip install -e /opt/quantbuild/quantlog-v.1   # optioneel: als je quantlog als package in deze venv wilt (CLI); anders alleen PYTHONPATH zoals post_run
deactivate
sudo systemctl restart quantbuild-ctrader-demo.service   # of jouw unit-naam
```

### 5.2 QuantBridge

```bash
cd /opt/quantbuild/quantBridge-v.1
git fetch origin
git checkout main                  # of jouw vaste branch
git pull --ff-only
```

**Na pull:** geen aparte bridge-venv. **Alleen bridge geüpdatet?** Herstart de service. **Volledige drie-repo update?** Gebruik §5.4 — **één** `systemctl restart` helemaal onderaan.

```bash
sudo systemctl restart quantbuild-ctrader-demo.service
```

### 5.3 QuantLog

```bash
cd /opt/quantbuild/quantlog-v.1
git fetch origin
git checkout main                  # of jouw vaste branch
git pull --ff-only
```

**Na pull:** geen eigen QuantLog-venv. Gebruik je `pip install -e` voor QuantLog in QuantBuild’s venv, voer die **opnieuw** uit na wijzigingen (of werk met alleen `PYTHONPATH` via `scripts/quantlog_post_run.py`). **Alleen QuantLog geüpdatet?** Herstart de service. **Volledige drie-repo update?** §5.4 — **één** restart onderaan.

```bash
sudo systemctl restart quantbuild-ctrader-demo.service
```

### 5.4 Volgorde bij twijfel

1. Pull **QuantBridge** eerst (als QuantBuild daar van afhangt).  
2. Pull **QuantLog** (validator / post_run / contracten).  
3. Pull **QuantBuild**.  
4. `pip install -r requirements.txt` alleen in **QuantBuild** `.venv` als nodig; optioneel `pip install -e /opt/quantbuild/quantlog-v.1`.  
5. Restart service **één keer** onderaan.

---

## 6) Python 3.10 consistent houden

### Check vóór je iets installeert

```bash
cd /opt/quantbuild/quantbuild_e1_v1
source .venv/bin/activate
which python
python --version
```

Verwacht: pad eindigt op `quantbuild_e1_v1/.venv/bin/python` en versie **3.10.x**.

### Veelvoorkomende fout

- `pip install` of `python` draaien **buiten** `.venv` → packages komen in user/system Python en systemd ziet ze niet.
- **Oplossing:** altijd `source .venv/bin/activate` vóór pip, of expliciet:

```bash
/opt/quantbuild/quantbuild_e1_v1/.venv/bin/pip install -r requirements.txt
```

### pyenv (als je VPS zo is ingericht)

Als de venv ooit met `pyenv`’s 3.10.13 is gemaakt, maak geen nieuwe venv met `/usr/bin/python3` zonder na te denken — dan krijg je twee werelden. Documenteer op de machine (of in dit bestand) welke command je ooit gebruikte, bijv.:

```bash
# voorbeeld — alleen ter referentie, niet blind kopiëren
pyenv shell 3.10.13
cd /opt/quantbuild/quantbuild_e1_v1
python -m venv .venv
```

---

## 7) systemd en Python-pad

`ExecStart` moet naar **deze** binary wijzen:

```text
/opt/quantbuild/quantbuild_e1_v1/.venv/bin/python -m src.quantbuild.app ...
```

Zo draait de service altijd tegen de juiste venv, ongeacht wat `PATH` of `python3` op het systeem is.

---

## 8) Snelle health-check na deploy

```bash
sudo systemctl is-active quantbuild-ctrader-demo.service
journalctl -u quantbuild-ctrader-demo.service -n 40 --no-pager
tail -n 80 /opt/quantbuild/quantbuild_e1_v1/logs/runtime_ctrader_demo.log
```

In logs: geen `No module named ...` na een pull — zo ja, vrijwel altijd verkeerde interpreter of `pip install` vergeten in **QuantBuild** `.venv`.

---

## 9) Checklist (plak in PR / na elke release)

- [ ] QuantBuild: juiste branch, `git pull --ff-only` zonder conflicts  
- [ ] QuantBridge: juiste branch, pull uitgevoerd als bridge gewijzigd is  
- [ ] QuantLog: juiste branch, pull uitgevoerd als log/contract gewijzigd is  
- [ ] `requirements.txt` gewijzigd? → `pip install -r requirements.txt` in **QuantBuild** `.venv`  
- [ ] QuantLog gewijzigd en je gebruikt `pip install -e`? → opnieuw `pip install -e /opt/quantbuild/quantlog-v.1` in **QuantBuild** `.venv`  
- [ ] `python --version` in `.venv` = 3.10.x  
- [ ] `QUANTBRIDGE_SRC_PATH` wijst naar `.../quantBridge-v.1/src`  
- [ ] `systemctl restart` uitgevoerd  
- [ ] Log + Telegram (indien aan) gecontroleerd  

---

## 10) Dit bestand in andere modules plaatsen

- **Optie A:** één “bron” in QuantBuild (`docs/VPS_MULTI_MODULE_DEPLOYMENT.md`) en op andere machines alleen dezelfde tekst handhaven.  
- **Optie B:** identieke kopie in elke repo onder `docs/` zodat clone’s overal dezelfde instructie hebben — update dan bewust alle kopieën bij grote wijzigingen.

Versie-regel onderaan helpt: `Last aligned: YYYY-MM-DD — Python 3.10, paths /opt/quantbuild/...`

---

*Last aligned: 2026-04-01 — Python 3.10 contract, QuantBridge + QuantLog + QuantBuild pull order, single QuantBuild venv.*
