# QuantOS — centrale aansturing (idee, later bouwen)

**Status:** ontwerpnotitie — nog geen implementatieplafond vastgelegd.  
**Doel:** vastleggen *of* en *hoe* we de suite primair vanuit **QuantOS** (`quantmetrics_os/`) aansturen, zonder nu code te hoeven wijzigen.

Gerelateerd: [`Roadmap_os.md`](Roadmap_os.md) (platformvisie), [`SUITE_START_HANDOUT.md`](SUITE_START_HANDOUT.md) (praktisch starten; kan voorlopen op code).

---

## 1. Waarom dit

- Eén **ingang** op de VPS en lokaal: juiste `*_ROOT`, secrets via `orchestrator/.env`, consistente `cwd` en `PYTHONPATH`.
- Geen tweede risk- of execution-logica in QuantOS — alleen **orchestratie** (subprocessen, vaste workflows, optioneel planning).
- Ondersteunt de gesloten loop: Build → Bridge → Log → Analytics → verbeteringen in Build.

---

## 2. Principe: dunne control plane

| QuantOS doet wel | QuantOS doet niet |
|------------------|-------------------|
| Env laden, paden resolveren | Strategie-, risk- of brokerregels dupliceren |
| Standaardketens starten (live, regressie, smoke, post-run, …) | Eigen event-store of mutatie van historische events |
| Documenteren welke repo-CLI leidend is | Businesslogica van sibling-repos vervangen |

Bron van waarheid voor gedrag blijft per domein-repo (QuantBuild / QuantBridge / QuantLog / QuantAnalytics).

---

## 3. Richting voor later: subcommando’s en ketens

Alles hieronder is **backlog** — volgorde en scope bepalen we bij implementatie.

1. **Verificatie** — `check`: alle verplichte env-variabelen en repo-mappen; optioneel Python/venv hints.
2. **QuantBuild** — al grotendeels richting: `build` (live / dry-run / notify-start); eventueel expliciet doorgeven van extra args naar `quantbuild.app`.
3. **QuantBridge** — naast regressie: wrappers voor `smoke`, `runtime_control`, VPS-paper-cycle, enz., zolang die als stabiele scripts in `quantbridgev1` bestaan.
4. **QuantLog** — wrappers naar bestaande validate/summarize-CLI’s met paden uit env (`QUANTLOG_ROOT`, `QUANTLOG_EVENTS_ROOT`).
5. **QuantAnalytics** — optioneel één entry “dagelijkse run” als die repo een vaste CLI krijgt.
6. **Post-run** — één commando dat een logische keten aanroept (valideren → samenvatten → score), afhankelijk van wat we in de repos standaardiseren.
7. **Notify** — gestandaardiseerde suite start/stop via QuantBuild-config (Telegram), zonder secrets in QuantOS-repo.

---

## 4. Operationeel model (later)

- VPS: systemd units of cron die **`python orchestrator/quantmetrics.py …`** aanroepen vanuit `quantmetrics_os/orchestrator`.
- Geen harde afhankelijkheid van een GUI; alles scriptbaar en reproduceerbaar.

---

## 5. Alignement docs ↔ code

[`SUITE_START_HANDOUT.md`](SUITE_START_HANDOUT.md) noemt commando’s die **al bedoeld** zijn als ergonomie; niet alles hoeft al in `orchestrator/quantmetrics.py` te zitten. Bij implementatie: handout bijwerken of ontbrekende subcommands toevoegen — één bron van waarheid (`--help` + handout synchroon houden).

---

## 6. Open punten (bij start implementatie)

- Welke workflows zijn “must-have” op de VPS dag 1?
- Waar ligt de grens tussen “één subprocess” versus “compose script in `scripts/`”?
- Moet QuantOS ooit state bijhouden (lange processen), of alleen fire-and-forget + logging naar bestaande QuantLog-streams?

---

*Laatste update: concept vastgelegd als startpunt voor latere uitwerking.*
