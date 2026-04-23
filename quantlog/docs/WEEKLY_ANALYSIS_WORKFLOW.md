# Wekelijkse analyse — standaardworkflow (lokaal)

Herhaalbare stappen om productie-events van de VPS (of andere host) op je laptop te analyseren met **deze** repo (`quantlog`). De CLI hoeft niet op de server te draaien; je kopieert alleen de JSONL-data.

**Gerelateerd:** [PLATFORM_ROADMAP.md](PLATFORM_ROADMAP.md) (volledige platform-roadmap: correlatie → reasons → events → nightly checks), [VPS_SYNC.md](VPS_SYNC.md) (waar events op de VPS staan), [DATA_TRANSFER_ROADMAP.md](DATA_TRANSFER_ROADMAP.md) (huidige copy-flow vs. latere sync-opties), [REPLAY_RUNBOOK.md](REPLAY_RUNBOOK.md) (diepgaander: replay, incidenten).

---

## 1) Eenmalig: omgeving

Zie root-[README.md](../README.md) — kort:

```powershell
cd "c:\Users\Gebruiker\quantlog"
python -m venv .venv
.venv\Scripts\activate
python -m pip install -e .
```

Daarna in elke nieuwe shell: alleen `.venv\Scripts\activate`.

---

## 2) Waar staan de events op de VPS?

Conform QuantBuild-config: meestal onder de **QuantBuild**-appmap, per dag een map:

```text
/opt/quantbuild/quantbuild/data/quantlog_events/YYYY-MM-DD/
```

*(Als jouw `quantlog.base_path` anders is, pas het bronpad in de kopieercommando’s aan.)*

---

## 2b) Één commando per stap (zodat je output kunt plakken)

**Zo gebruik je dit:** voer **stap 1** uit in je terminal, plak de output waar je wilt (of bewaar ’m). Ga pas naar **stap 2** als stap 1 klaar is. Geen haast — zo raak je de draad niet kwijt.

**Eerst invullen (op een kladje):**

- `jouwuser` = SSH-gebruiker op de VPS  
- `jouw.vps.example` = hostnaam of IP  
- Zeven datums van jouw week, bijv. `2026-03-31` t/m `2026-04-06` — zet die overal waar `DAG1` … `DAG7` staan (of vervang ze direct in de commando’s)

Standaardpad events (pas aan als nodig):

`/opt/quantbuild/quantbuild/data/quantlog_events`

---

### Deel A — VPS (bash): inloggen en kijken

| Stap | Wat je doet | Commando (exact één regel, copy/paste) |
|------|-------------|----------------------------------------|
| **1** | Inloggen op de VPS | `ssh jouwuser@jouw.vps.example` |
| **2** | Naar de event-map | `cd /opt/quantbuild/quantbuild/data/quantlog_events` |
| **3** | Controleren waar je bent | `pwd` |
| **4** | Alle dagmappen tonen | `ls -la` |
| **5** | Eerste dag van je week bekijken (pas datum aan) | `ls -la 2026-03-31` |
| **6** | Tweede dag | `ls -la 2026-04-01` |
| **7** | Derde dag | `ls -la 2026-04-02` |
| **8** | Vierde dag | `ls -la 2026-04-03` |
| **9** | Vijfde dag | `ls -la 2026-04-04` |
| **10** | Zesde dag | `ls -la 2026-04-05` |
| **11** | Zevende dag | `ls -la 2026-04-06` |

Als een map ontbreekt: je krijgt iets als `No such file or directory` — dat is oké voor dagen zonder events.

**Optioneel — grootte per dag (ook één regel per stap):**

| Stap | Commando |
|------|----------|
| **12** | `du -sh 2026-03-31` |
| **13** | `du -sh 2026-04-01` |
| **14** | `du -sh 2026-04-02` |
| **15** | `du -sh 2026-04-03` |
| **16** | `du -sh 2026-04-04` |
| **17** | `du -sh 2026-04-05` |
| **18** | `du -sh 2026-04-06` |

*(Vervang de datums door jouw week; als de map ontbreekt, meldt `du` een fout — sla die stap over.)*

---

### Deel B — VPS (bash): één `.tar.gz` maken voor download

Gebruik dit alleen als je **één bestand** naar je laptop wilt trekken. Nog steeds: **één commando per stap**.

| Stap | Commando |
|------|----------|
| **19** | `EVENTS="/opt/quantbuild/quantbuild/data/quantlog_events"` |
| **20** | `WEEK_LABEL="2026-W14"` |
| **21** | `TMP="/tmp/quantlog-export-${WEEK_LABEL}"` |
| **22** | `mkdir -p "$TMP"` |
| **23** | `cp -a "$EVENTS/2026-03-31" "$TMP/"` |
| **24** | `cp -a "$EVENTS/2026-04-01" "$TMP/"` |
| **25** | `cp -a "$EVENTS/2026-04-02" "$TMP/"` |
| **26** | `cp -a "$EVENTS/2026-04-03" "$TMP/"` |
| **27** | `cp -a "$EVENTS/2026-04-04" "$TMP/"` |
| **28** | `cp -a "$EVENTS/2026-04-05" "$TMP/"` |
| **29** | `cp -a "$EVENTS/2026-04-06" "$TMP/"` |

*(Als een `cp` faalt: die dag bestond niet — ga door met de volgende stap.)*

| Stap | Commando |
|------|----------|
| **30** | `tar -czvf "/tmp/quantlog-${WEEK_LABEL}.tar.gz" -C /tmp "$(basename "$TMP")"` |
| **31** | `ls -lh "/tmp/quantlog-${WEEK_LABEL}.tar.gz"` |

Klaar op de VPS: het bestand staat als `/tmp/quantlog-2026-W14.tar.gz` (als `WEEK_LABEL` zo heette).

**Opruimen op de VPS (optioneel, elk op zich):** alleen **nadat** je stap **36** op je laptop hebt gedaan (bestand veilig binnen). Als je shell nieuw is, eerst weer: `WEEK_LABEL="2026-W14"` en `TMP="/tmp/quantlog-export-${WEEK_LABEL}"`.

| Stap | Commando |
|------|----------|
| **32** | `rm -f "/tmp/quantlog-${WEEK_LABEL}.tar.gz"` |
| **33** | `rm -rf "$TMP"` |

---

### Deel C — Laptop (bash of WSL): archief ophalen en uitpakken

| Stap | Waar | Commando |
|------|------|----------|
| **34** | Laptop | `cd "/pad/naar/jouw/quantlog"` |
| **35** | Laptop | `mkdir -p data/imported/week-2026-W14` |
| **36** | Laptop | `scp jouwuser@jouw.vps.example:/tmp/quantlog-2026-W14.tar.gz .` |
| **37** | Laptop | `tar -xzvf quantlog-2026-W14.tar.gz -C data/imported/week-2026-W14 --strip-components=1` |

*(Paden en `WEEK_LABEL` gelijk houden met deel B. Zit `2026-04-01` niet in `data/imported/week-2026-W14/` maar dieper genest, dan `--strip-components` aanpassen of mappen handmatig verplaatsen.)*

---

### Deel D — VPS (optioneel): CLI-check op de server

| Stap | Commando |
|------|----------|
| **38** | `cd /opt/quantbuild/quantbuild` |
| **39** | `source .venv/bin/activate` |
| **40** | `python -m quantlog.cli validate-events --path data/quantlog_events/2026-04-01` |
| **41** | `deactivate` |

Zie [VPS_SYNC.md](VPS_SYNC.md) als `python -m quantlog.cli` niet werkt.

---

### Deel E — Laptop (PowerShell): zonder tar, dag per dag met `scp`

Als je **geen** tar gebruikt, kun je op je **Windows**-machine stap voor stap dit doen (pas user, host, datums en lokale map aan):

| Stap | Commando |
|------|----------|
| **42** | `cd "c:\Users\Gebruiker\quantlog"` |
| **43** | `New-Item -ItemType Directory -Force -Path "data\imported\week-2026-W14"` |
| **44** | `scp -r "jouwuser@jouw.vps.example:/opt/quantbuild/quantbuild/data/quantlog_events/2026-03-31" "data\imported\week-2026-W14"` |
| **45** | `scp -r "jouwuser@jouw.vps.example:/opt/quantbuild/quantbuild/data/quantlog_events/2026-04-01" "data\imported\week-2026-W14"` |
| **46** | `scp -r "jouwuser@jouw.vps.example:/opt/quantbuild/quantbuild/data/quantlog_events/2026-04-02" "data\imported\week-2026-W14"` |
| **47** | `scp -r "jouwuser@jouw.vps.example:/opt/quantbuild/quantbuild/data/quantlog_events/2026-04-03" "data\imported\week-2026-W14"` |
| **48** | `scp -r "jouwuser@jouw.vps.example:/opt/quantbuild/quantbuild/data/quantlog_events/2026-04-04" "data\imported\week-2026-W14"` |
| **49** | `scp -r "jouwuser@jouw.vps.example:/opt/quantbuild/quantbuild/data/quantlog_events/2026-04-05" "data\imported\week-2026-W14"` |
| **50** | `scp -r "jouwuser@jouw.vps.example:/opt/quantbuild/quantbuild/data/quantlog_events/2026-04-06" "data\imported\week-2026-W14"` |

---

### Deel F — Laptop (PowerShell): analyse CLI, één commando per stap

Ga naar je repo, activeer venv, daarna elk CLI-commando apart:

| Stap | Commando |
|------|----------|
| **51** | `cd "c:\Users\Gebruiker\quantlog"` |
| **52** | `.venv\Scripts\activate` |
| **53** | `python -m quantlog.cli validate-events --path data\imported\week-2026-W14` |
| **54** | `python -m quantlog.cli summarize-day --path data\imported\week-2026-W14` |
| **55** | `python -m quantlog.cli check-ingest-health --path data\imported\week-2026-W14 --max-gap-seconds 120` |
| **56** | `python -m quantlog.cli score-run --path data\imported\week-2026-W14 --max-gap-seconds 300 --pass-threshold 95` |

*(Pad `data\imported\week-2026-W14` aanpassen als jouw map anders heet.)*

---

## 3) Data naar je laptop brengen (compact)

Wil je **één commando per keer** met nummers: gebruik **§2b** (Deel B–F). Hieronder de kortere varianten (loops / meerdere regels in één blok).

Kies **alle dagen van de week** die je wilt meenemen (ISO-datum in de mapnaam).

### Optie A — hele week in één lokale map (aanbevolen)

Lokaal eerst een doelmap, bijvoorbeeld:

```text
data/imported/week-2026-W14/
```

Daarin komen submappen `2026-03-31`, `2026-04-01`, … (zelfde structuur als op de server).

**Hele week in één keer (PowerShell + `scp`):** zet `USER`, `HOST`, de **eerste dag van de week** (`$weekStart`, meestal maandag) en de mapnaam `week-…`.

```powershell
$User = "jouwuser"
$VpsHost = "jouw.vps.example"   # niet $HOST — dat is gereserveerd in PowerShell
$remoteBase = "${User}@${VpsHost}:/opt/quantbuild/quantbuild/data/quantlog_events"
$local = "c:\Users\Gebruiker\quantlog\data\imported\week-2026-W14"
$weekStart = Get-Date "2026-03-31"   # eerste dag die je wilt (lokaal / UTC-kalender zoals op de VPS)

New-Item -ItemType Directory -Force -Path $local | Out-Null
foreach ($i in 0..6) {
    $d = $weekStart.AddDays($i).ToString("yyyy-MM-dd")
    scp -r "${remoteBase}/$d" $local
}
```

Elke bestaande dagmap op de server wordt zo naar `$local\$d\` gezet. Ontbrekende dagen (geen map op de VPS) geven een `scp`-fout; dat is normaal als er die dag geen events zijn — sla die regel over of maak de map later alsnog leeg.

**Handmatig (zelfde idee, zonder loop):** pas `USER`, `HOST` en datums aan.

```powershell
$remote = "USER@HOST:/opt/quantbuild/quantbuild/data/quantlog_events"
$local  = "c:\Users\Gebruiker\quantlog\data\imported\week-2026-W14"
New-Item -ItemType Directory -Force -Path $local | Out-Null
scp -r "${remote}/2026-03-31" $local
scp -r "${remote}/2026-04-01" $local
# … één regel per kalenderdag
```

**Voorbeeld met `rsync` (als je dat gebruikt):**

```bash
rsync -avz -e ssh USER@HOST:/opt/quantbuild/quantbuild/data/quantlog_events/2026-04-0{1,2,3}/ \
  "./data/imported/week-2026-W14/"
```

*(Shell-syntax voor datumbereiken verschilt; het gaat om: meerdere dagmappen in één lokale parent.)*

### Optie B — alleen één dag

Kopieer één map `YYYY-MM-DD` en gebruik die direct als `--path` (zie §4).

---

## 4) Standaard analysevolgorde (copy/paste)

Zet `DATA` naar je **lokale** pad: of de **weekmap** (alle `*.jsonl` onderliggend worden meegenomen), of één **dagmap**.

**PowerShell:**

```powershell
cd "c:\Users\Gebruiker\quantlog"
.venv\Scripts\activate

$DATA = "data\imported\week-2026-W14"   # of: data\imported\2026-04-01

python -m quantlog.cli validate-events --path $DATA
python -m quantlog.cli summarize-day --path $DATA
python -m quantlog.cli check-ingest-health --path $DATA --max-gap-seconds 120
python -m quantlog.cli score-run --path $DATA --max-gap-seconds 300 --pass-threshold 95
```

**Interpretatie (kort):**

| Commando | Eerst kijken naar |
|----------|-------------------|
| `validate-events` | `errors_total` moet **0** zijn voordat je verder trekt. |
| `summarize-day` | Tellingen per event type, trades/blocks/slippage (over **alle** bestanden onder `$DATA`). |
| `check-ingest-health` | Gaten in `ingested_at_utc`; exitcode **3** = gap(s) gevonden. |
| `score-run` | Scorecard; exitcode **4** = onder drempel (`passed: false`). |

**Optioneel — audit-gap events wegschrijven** (mutatie in de event store op schijf; alleen doen als je dat bewust wilt):

```powershell
python -m quantlog.cli check-ingest-health --path $DATA --max-gap-seconds 120 --emit-audit-gap
```

**Diepgaand per trace:** `replay-trace` met een concrete `trace_id` uit je logs — zie [REPLAY_RUNBOOK.md](REPLAY_RUNBOOK.md).

---

## 5) Per dag vs hele week

- **`--path` = weekmap (parent):** alle `.jsonl` in alle submappen worden samen gescand — handig voor één weekoverzicht.
- **`--path` = één dagmap:** zelfde commando’s, smallere scope (sneller, duidelijker per kalenderdag).

---

## 6) Mini-checklist (elke keer)

1. [ ] Nieuwe data gekopieerd naar `data/imported/…`
2. [ ] `.venv` actief + `pip install -e .` nog geldig na repo-updates
3. [ ] `validate-events` → geen errors
4. [ ] `summarize-day` + `check-ingest-health` + `score-run`
5. [ ] Bij afwijkingen: eerst logging/gaten oplossen ([REPLAY_RUNBOOK.md](REPLAY_RUNBOOK.md) §3)

---

*QuantLog v1 — lokale analyse; events blijven bron van waarheid op schijf (append-only gedrag in productie niet vergeten bij `--emit-audit-gap`).*
