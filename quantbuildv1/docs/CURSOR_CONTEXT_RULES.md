# Cursor Context Rules — Efficient Working Mode

Doel: **zo min mogelijk onnodige context laden**, zodat we sneller werken, goedkoper itereren en de aandacht op de juiste module houden.

---

## 1. Hoofdregel

**Lees nooit de hele codebase of alle documenten tegelijk.**
Lees alleen wat nodig is voor de taak van dit moment.

---

## 2. Context budget per taak

Bij elke taak geldt:

- pak alleen de **relevante map, file of functie**
- lees maximaal **1–3 bestanden tegelijk**
- laad eerst **samenvattingen**, daarna pas detailcode
- vermijd brede scans zoals: “analyseer hele project”

Gebruik dus altijd:

- eerst: probleemdefinitie
- dan: betrokken module
- dan: exact bestand of functie

---

## 3. Werk altijd module-first

Werk vanuit modules, niet vanuit het hele systeem.

Volg deze volgorde:

1. bepaal **welke module verandert**
2. lees alleen de files van die module
3. lees alleen upstream/downstream context als het echt nodig is
4. raak de rest van het systeem niet aan

Voorbeelden:

- signaalwijziging → alleen signal engine + config
- risk wijziging → alleen risk engine + sizing rules
- execution bug → alleen execution adapter + order flow
- logging issue → alleen logger/replay files

---

## 4. Eerst samenvatten, dan pas lezen

Voordat Cursor grote bestanden leest:

- vraag eerst om een **korte samenvatting van relevante files**
- vraag daarna welke file de **source of truth** is
- open pas daarna de echte implementatie

Voorkom dat Cursor direct 20 bestanden opent terwijl 2 bestanden genoeg zijn.

---

## 5. Gebruik een vaste vraagstructuur

Elke taak moet starten met deze 5 vragen:

1. Wat is het exacte probleem?
2. Welke module hoort hierbij?
3. Welke file is de source of truth?
4. Welke dependencies zijn echt nodig?
5. Wat hoeft expliciet **niet** gelezen te worden?

---

## 6. No full-repo mode

Cursor mag **niet standaard**:

- de hele repository indexeren voor één kleine wijziging
- alle markdown docs meelezen
- oude experimenten of archive-mappen openen
- testbestanden lezen als de wijziging puur conceptueel is
- notebooks, logs en exports in context trekken zonder reden

Alleen toestaan als de taak expliciet is:

- architectuur-audit
- refactor over meerdere modules
- dependency conflict
- root-cause analyse waarbij lokale inspectie onvoldoende is

---

## 7. Docs apart houden van build-context

Gebruik documentatie slim:

- **README / SUMMARY / architecture docs** = alleen voor oriëntatie
- **implementatiebestanden** = alleen lezen als we echt bouwen
- **oude hoofdstukken / brainstormteksten** = niet standaard meesturen

Regel:

**Conceptdocs zijn richtinggevend, maar code is leidend.**

---

## 8. Eén doel per prompt

Geef Cursor nooit een prompt met meerdere grote doelen tegelijk.

Slecht:

- fix strategy
- improve backtest
- optimize risk
- clean architecture
- update docs

Goed:

- “Analyseer alleen waarom `risk_per_trade` niet correct wordt toegepast in live execution.”
- “Bekijk alleen de regime filter in de signal engine en stel 1 concrete fix voor.”

---

## 9. Eerst diagnose, dan patch

Laat Cursor niet meteen coderen.

Stappen:

1. diagnose
2. oorzaak aanwijzen
3. relevante files benoemen
4. kleinste mogelijke patch voorstellen
5. pas daarna code aanpassen

Zo voorkom je dat te veel context wordt geladen voor een te grote rewrite.

---

## 10. Forceer minimale patchgrootte

Elke wijziging moet beginnen als:

- kleinste wijziging
- laagste risico
- minst aantal files
- zonder onnodige refactor

Regel:

**Niet herschrijven wat nog niet bewezen stuk is.**

---

## 11. Vraag altijd om een context boundary

Laat Cursor aan het begin expliciet aangeven:

- welke files wél gelezen worden
- welke files niet nodig zijn
- welke aannames worden gemaakt
- waar onzekerheid zit

Voorbeeld:

> Context boundary: ik lees alleen `signal_engine.py`, `regime_filter.py` en `strict_prod_v1.yaml`. Ik lees geen execution-, dashboard- of replay-files tenzij nodig.

---

## 12. Houd configs leidend

Bij trading systems zit veel gedrag in configs.
Dus:

- check eerst YAML/JSON/config files
- check daarna pas code
- wijzig liever parameters dan logica als het probleem configuratief is

Vaak is de fout geen codefout maar een verkeerde instelling.

---

## 13. Oude experimenten uitsluiten

Sluit standaard uit:

- `archive/`
- `old/`
- `experiments/`
- losse test dumps
- debug output
- tijdelijke notebooks
- backtest exports

Tenzij de vraag expliciet over historische vergelijking gaat.

---

## 14. Gebruik vaste werkmodi

### Mode A — Concept mode
Alleen denken. Geen code lezen behalve architectuur-samenvattingen.

### Mode B — Inspect mode
Lees alleen relevante files. Geen wijzigingen.

### Mode C — Patch mode
Lees minimale context en maak alleen de afgesproken patch.

### Mode D — Verify mode
Lees alleen wat nodig is om de wijziging te controleren.

Cursor moet altijd expliciet zeggen in welke mode het werkt.

---

## 15. Geen context op basis van nieuwsgierigheid

Cursor mag geen extra files openen “voor de zekerheid”.
Alle extra context moet functioneel nodig zijn.

Goede regel:

**Elke geopende file moet een reden hebben.**

---

## 16. Eerst interfaces, dan internals

Als een module onbekend is:

1. lees eerst public interface / function signatures
2. lees daarna call sites
3. lees pas daarna interne implementatie

Zo krijg je snel begrip zonder tokenverbranding.

---

## 17. Output altijd compact structureren

Laat Cursor antwoorden in dit formaat:

### Probleem

### Relevante module

### Files die ik lees

### Files die ik bewust niet lees

### Waarschijnlijke oorzaak

### Kleinste patch

### Risico van wijziging

Dit houdt de analyse kort en scherp.

---

## 18. Escalatieregel

Pas méér context laden als:

- de lokale file geen duidelijke oorzaak geeft
- meerdere modules hetzelfde gedrag beïnvloeden
- er een config/code mismatch is
- tests de diagnose tegenspreken

Dus:

**eerst smal, alleen breder als bewijs daarom vraagt.**

---

## 19. Specifiek voor QuantBuild / trading bots

Voor dit project gelden extra regels:

- signal, risk, execution en replay zijn **gescheiden modules**
- wijzig nooit tegelijk signal én risk én execution zonder noodzaak
- bij strategievragen eerst expectancy/regime/config bekijken
- bij live issues eerst adapter/config/logging bekijken
- bij performancevragen eerst dataset + assumptions checken, niet meteen model complexer maken

---

## 20. Standaard instructie voor Cursor

Gebruik deze instructie voortaan aan het begin van taken:

```md
Werk met minimale context.
Lees niet de hele repository.
Bepaal eerst welke module verandert.
Noem daarna exact welke 1–3 files je nodig hebt.
Noem ook welke files je bewust niet leest.
Doe eerst diagnose, daarna pas patch.
Kies altijd de kleinste wijziging met het laagste risico.
```

---

## 21. Korte teamregel

**Breed denken, smal lezen, klein bouwen.**

Dat is de standaard.

