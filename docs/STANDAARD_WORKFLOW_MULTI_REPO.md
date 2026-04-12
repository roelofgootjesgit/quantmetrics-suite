# Standaard workflow — losse repos (QuantBuild ecosysteem)

Dit document beschrijft **hoe we samenwerken over meerdere repositories** zonder monorepo of submodules. Het is de **proces-laag** bovenop de technische VPS-afspraken in `docs/VPS_MULTI_MODULE_DEPLOYMENT.md` en de **copy/paste** commando’s in `docs/OPERATOR_CHEATSHEET.md`.

**Principe:** elke repo heeft een eigen `git`-historie; **QuantBuild** is de **integratiehub** (runtime, systemd, config, linkage-scripts, release-notities).

**Credentials:** overal geldt **`docs/CREDENTIALS_AND_ENVIRONMENT.md`** — secrets leven in **`os.environ`** (VPS: systemd `EnvironmentFile`; lokaal: export of gitignored `.env` die dotenv inlaadt). Geen tokens in git of in voorbeeld-config buiten placeholders.

---

## 1) Repos en rollen

| Repo (voorbeeldmap) | Rol |
|---------------------|-----|
| **quantbuildv1** | Bot, orchestratie, productie-config, eventpad `data/quantlog_events/`, CI, VPS-systemd. **Hier documenteer je welke combinatie van andere repos je hebt getest.** |
| **quantbridgev1** | Broker/OpenAPI-laag; wordt op de VPS als **bronpad** geladen (`QUANTBRIDGE_SRC_PATH`). Geen tweede productie-venv tenzij bewust anders afgesproken. |
| **quantlogv1** | Event-spine: schema, validate/replay/CLI; contract met wat QuantBuild emitteert. |
| **quantmetrics_os** | Typisch **analyse/metrics** naast de runtime-stack. Heeft meestal **geen** gedeelde VPS-venv met de bot; eigen branch/pull en eigen venv als die repo dat nodig heeft. Koppel aan QuantBuild via **exports** (JSON/summary) of gedeelde data-mappen op jouw machine — niet impliciet mengen met `quantbuildv1/.venv` tenzij je dat expliciet ontwerpt. |

Paden op de VPS zijn vastgelegd in `VPS_MULTI_MODULE_DEPLOYMENT.md` (onder `/opt/quantbuild/…`). Lokaal op Windows mag je dezelfde mapnamen naast elkaar zetten, bijv. `C:\Users\…\quantbuildv1` naast siblings `quantbridgev1`, `quantlogv1`, `quantmetrics_os`.

---

## 2) Lokale ontwikkeling (Cursor / VS Code)

1. **Multi-root workspace:** voeg alle relevante mappen toe (*File → Add Folder to Workspace*) en sla een `.code-workspace`-bestand op. Zo edit je overal, maar blijft **git per map** (geen verwarring over welke repo een commit bevat).
2. **Per wijziging:** altijd in de **juiste** root `git status` / `commit` / `push` — niet alles in één commit proppen over repo-grenzen heen.
3. **Python:** op de VPS geldt **één** bot-venv in QuantBuild (`docs/VPS_MULTI_MODULE_DEPLOYMENT.md`). Lokaal mag je per repo een venv hebben; houd dat in je hoofd als je imports tussen repos test.

### 2.1) Alles tegelijk pushen (optioneel)

Het script **commit niet**; het voert alleen `git push` uit per repo die bestaat en een geldige branch heeft. Handig na commits in meerdere mappen in één sessie.

| Script | Wanneer |
|--------|---------|
| `scripts/dev/push_all_repos.ps1` | Windows / PowerShell |
| `scripts/dev/push_all_repos.sh` | WSL, Linux, macOS |

**Standaardpaden:** beide scripts nemen de **oudermap van `quantbuildv1`** als root en zoeken daar siblings: `quantbuildv1`, `quantbridgev1`, `quantlogv1`, `quantmetrics_os`. Ontbrekende mappen of geen `.git` → **waarschuwing en verder** (andere repos worden wél gepusht).

**Windows (vanuit quantbuildv1):**

```powershell
.\scripts\dev\push_all_repos.ps1
```

Alleen commando’s tonen:

```powershell
.\scripts\dev\push_all_repos.ps1 -DryRun
```

Andere remote of andere bovenliggende map (als je repos niet direct naast `quantbuildv1` staan):

```powershell
.\scripts\dev\push_all_repos.ps1 -Remote origin
$env:QUANT_ECOSYSTEM_ROOT = "C:\Users\Gebruiker"
.\scripts\dev\push_all_repos.ps1
```

**Bash:**

```bash
chmod +x scripts/dev/push_all_repos.sh   # eenmalig op Unix
./scripts/dev/push_all_repos.sh
DRY_RUN=1 ./scripts/dev/push_all_repos.sh
QUANT_ECOSYSTEM_ROOT=/pad/naar/parent ./scripts/dev/push_all_repos.sh
REMOTE=upstream ./scripts/dev/push_all_repos.sh
```

**Let op:** bij de eerste keer een branch naar de remote brengen moet je vaak upstream zetten (`git push -u origin <branch>`) **in die repo**; daarna werkt het massa-push-script. Repos met **detached HEAD** worden overgeslagen. Volg nog steeds de **PR-volgorde** (§3): massa-push is alleen gemak, geen vervanging van contract-first merges.

---

## 3) Wie gaat eerst: PR- en merge-volgorde

Werk **contract-first**: wie het **externe contract** wijzigt (QuantLog-schema, bridge-API, gedeelde types), merge dat **eerst** in die repo. Daarna pas QuantBuild aan (emitter, mapping, config, tests).

**Vuistregel bij twijfel:**

1. **QuantBridge** — als de transportlaag of signatures veranderen waar QuantBuild op leunt.  
2. **QuantLog** — als JSONL/schema/validator/replay veranderen.  
3. **QuantBuild** — integratie, `check_quantlog_linkage`, configs, documentatie.  
4. **quantmetrics_os** — wanneer je alleen analyse of downstream rapportage wijzigt; vaak **parallel** of na een QuantBuild-export, niet in de kritieke pad van `systemctl restart`.

Als **alleen** QuantBuild feature-werk doet zonder contractwijziging: normale feature branch in quantbuildv1 volstaat.

---

## 4) Release-set (traceerbaarheid)

Voor elke release naar productie (of belangrijke milestone) noteer je **één regel** (in PR-beschrijving, tag, of `CHANGELOG`), bijvoorbeeld:

```text
Release 2026-04-12: quantbuild @abc1234 | quantbridge @def5678 | quantlog @ghi9012 | quantmetrics (optioneel) @…
```

Zo kun je na een incident exact de **combinatie** reconstrueren. Je hoeft geen gezamenlijke git-tag over alle repos te forceren; wel **bewuste alignment**.

---

## 5) VPS: pull en restart (samenvatting)

Volgorde staat uitgewerkt in `docs/VPS_MULTI_MODULE_DEPLOYMENT.md` §5.4 en in `docs/OPERATOR_CHEATSHEET.md` §2. In het kort:

1. `git pull --ff-only` in **quantbridgev1** (juiste branch).  
2. Idem **quantlogv1**.  
3. Idem **quantbuildv1**.  
4. Alleen in **QuantBuild** `.venv`: `pip install -r requirements.txt` indien nodig; optioneel `pip install -e …/quantlogv1` als je die workflow gebruikt.  
5. **`systemctl restart` één keer** aan het eind.

**quantmetrics_os** hoort hier alleen als je die **op dezelfde server** bewust deployt; standaard draait de bot **zonder** metrics-repo op de VPS.

---

## 6) Kwaliteitspoort vóór merge (QuantBuild)

- Draai tests en waar van toepassing:  
  `python scripts/check_quantlog_linkage.py`  
  Strikte modus: `QUANTLOG_LINKAGE_STRICT=1` of `--strict` (zie `docs/OPERATOR_CHEATSHEET.md` §11).  
- CI in QuantBuild volgt dezelfde linkage-check; zorg dat **contract-wijzigingen** in log/bridge **eerst** beschikbaar zijn of dat je fixture/versie-afspraken tijdelijk aligned houdt.

---

## 7) Checklist — voor merge / voor deploy

**Ontwikkeling (multi-repo wijziging):**

- [ ] Contract gewijzigd? → Eerst bridge en/of log gemerged, daarna QuantBuild-PR.  
- [ ] QuantBuild-PR vermeldt **release-set** (commits of tags van siblings).  
- [ ] `check_quantlog_linkage` (lokaal of CI) groen waar verwacht.

**Deploy VPS (na pull):**

- [ ] Zelfde items als `docs/VPS_MULTI_MODULE_DEPLOYMENT.md` §9 (branches, pip in QuantBuild-venv, `QUANTBRIDGE_SRC_PATH`, één restart, logs gecontroleerd).

---

## 8) Gerelateerde documenten

| Document | Inhoud |
|----------|--------|
| `docs/VPS_MULTI_MODULE_DEPLOYMENT.md` | Python 3.10, paden, venv, pull-volgorde, systemd |
| `docs/OPERATOR_CHEATSHEET.md` | Dagelijkse commando’s, quantlog nightly, linkage |
| `docs/VPS_DEPLOYMENT_RUNBOOK.md` | Eerste install, clone-URL’s, units |
| `docs/VPS_JSON_DAGELIJKSE_ANALYSE_WORKFLOW.md` | Data/export richting analyse |
| `scripts/dev/push_all_repos.ps1` / `.sh` | Optioneel: push alle repos in één run |

---

*Aanmaak: 2026-04-12 — losse repos, QuantBuild als hub, optioneel quantmetrics_os naast de runtime-stack. Massa-push scripts: 2026-04-12.*
