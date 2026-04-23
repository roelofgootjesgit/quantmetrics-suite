# Expansion dominance strategy

## Doel

Dit document beschrijft de volgende strategy-fase na:

- data integrity fixes
- edge discovery
- edge density curve
- eerste betrouwbare guard diagnostics

Doel:

- de strategie verschuiven van een brede, gemengde tradeverdeling  
  naar  
- een **expansion-dominante allocatie** waarin kapitaal en trade-frequentie naar de sterkste edge-context gaat.

---

## Kernobservaties

### 1. De strategie is positief, maar allocatie is inefficiënt

In de recente run (voorbeeld: 2025 full strict prod–achtig profiel):

- 36 trades
- mean R ≈ +0.33
- 148 signalen
- 36 ENTERs
- 112 NO_ACTIONs

Dat betekent:

- de machine werkt
- de strategy heeft edge
- maar de edge wordt nog niet optimaal verdeeld

### 2. Expansion is de sterkste edge

Per regime op gesloten trades (voorbeeldcijfers uit dezelfde run):

- **expansion:** mean R ≈ +2.00 (n=4)
- **trend:** mean R ≈ +0.125 (n=32)

Interpretatie:

- expansion is extreem waardevol per trade
- trend is nog positief, maar veel zwakker
- compression blijft inferieur / ongewenst

### 3. Trade-distributie is scheef

Zelfde run:

- trend trades: 32
- expansion trades: 4

Dit betekent:

```text
de sterkste edge krijgt de minste allocatie
de zwakkere edge krijgt de meeste allocatie
```

Dat is suboptimaal.

### 4. Session-gedrag verschilt sterk

Per session op gesloten trades (voorbeeldcijfers):

- **New York:** mean R ≈ +0.696
- **Overlap:** mean R ≈ -0.10
- **London:** mean R ≈ -1.0

Interpretatie:

- New York is de duidelijke hoofd-session
- London is in deze run negatief
- Overlap is zwak / twijfelachtig
- Asia blijft grotendeels onbekend omdat session gating daar veel blokkeert

### 5. Guards blokkeren vooral sessions, niet blind de hele strategy

Belangrijkste guard blocks (voorbeeld):

- `regime_allowed_sessions`: 76 blocks (68%)
- `daily_loss_cap`: 19 blocks (17%)
- `regime_profile`: 10 blocks (9%)

En:

- `regime_allowed_sessions` blokkeert in deze run vooral Asia
- `regime_profile` blokkeert vooral compression
- `daily_loss_cap` grijpt later in als risk-veto

Interpretatie:

- niet alle guards zijn “slecht”
- de vraag is niet: “guards uit?”
- de vraag is: **welke guard beperkt expansion-throughput onnodig?**

---

## Strategisch principe

De volgende strategy-fase is:

```text
meer expansion trades
minder trend trades
meer exposure naar New York
minder exposure naar zwakke sessions
```

Niet door alles losser te zetten, maar door **allocatie en selectie per context** aan te passen.

---

## Gewenst eindbeeld

**Van**

- trend-dominante tradeverdeling
- expansion als zeldzame high-quality uitzondering

**Naar**

- expansion als primaire alpha-bucket
- trend als secundaire, selectieve alpha-bucket
- compression uit
- slechte sessions zwaar beperkt of uit

---

## Strategy model

### Bucket 1 — Primary alpha

**Expansion + New York**

- hoogste expectancy per trade
- geschikt voor hogere risk en prioriteit
- kandidaat voor meer trade-throughput (onder bewijs)

### Bucket 2 — Secondary alpha

**Trend + New York**

- lichte edge
- alleen nemen onder strengere voorwaarden
- lagere sizing dan expansion

### Bucket 3 — Avoid / suppress

**London, Overlap, Compression**

- in huidige data zwak of negatief
- alleen herzien als later sterke tegenbewijzen komen (niveau B)

---

## Concrete strategie-aanpassingen

### Fase 1 — Expansion priority

**Doel:** expansion vaker toelaten en zwaarder laten wegen (relatief, niet “alles open”).

**Acties**

1. **Expansion risk uplift** — verhoog risk in expansion-context t.o.v. trend (voorbeeldidee: `expansion * 1.5`, `trend * 0.5` op `base_risk`; exact in SQE/policy implementeren).

2. **Expansion filter relaxation** — alleen in expansion-context gecontroleerd versoepelen (H1 gate, cooldown, session precisie, position limits regime-aware). **Één knop per experiment**, baseline vs variant.

### Fase 2 — Trend downgrade

**Doel:** trend niet langer dominante alpha-bucket.

**Acties**

1. **Strengere trend-entry** (confidence, displacement, combo/confluence).

2. **Lagere trend-sizing** versus expansion.

### Fase 3 — Session selection hard maken

**Op basis van huidige run (hypothese, geen eeuwige waarheid)**

| Session   | Richting |
|-----------|----------|
| New York  | Behouden, prioriteit |
| London    | Tijdelijk uit of alleen onder expansion-review |
| Overlap   | Suppress / review |
| Asia      | Niet blind openen; eerst guard attribution + dedicated rerun |

---

## Prioriteitsmatrix

| Prioriteit | Focus | Actie |
|------------|-------|--------|
| 1 | Expansion + New York | Hoogste prioriteit; sizing + experimenten |
| 2 | Trend + New York | Kleinere sizing; strengere filters |
| 3 | Expansion + Asia | Alleen na onderzoek & compare |
| 4 | London / Overlap | Geen focus tot tegenbewijs |

---

## Guard-aanpak

- **`regime_allowed_sessions`** — niet zomaar verwijderen; baseline vs variant (expansion + Asia-unlock alleen gericht).
- **`regime_profile`** — compression blokkeren mag; expansion niet onnodig afknijpen.
- **`daily_loss_cap`** — risk governance; laatste om te tunen voor “alpha-unlock”.

---

## Experimentenplan (codes)

| ID | Hypothese | Variant-idee |
|----|-----------|----------------|
| EXP-D1 | Expansion risk uplift | Expansion risk multiplier ↑ |
| EXP-D2 | Trend downgrade | Hogere confidence / lagere trend-risk |
| EXP-D3 | New York preference | London/Overlap uit, NY aan |
| EXP-D4 | Expansion + Asia unlock | Session guard gericht relaxen voor expansion Asia |

Allen: **één verschil tegelijk**, zelfde venster, niveau-B compare waar mogelijk (`quantmetrics-guard-attribution-compare`).

---

## Beslisregels

- **Promote:** expectancy omhoog, DD beheersbaar, expansion-dominantie sterker.
- **Reject:** veel meer trades maar mean R zwaar omlaag of DD disproportioneel.
- **Keep for research:** veelbelovend maar sample klein / effect onduidelijk.

---

## Wat niet doen

- geen combo van meerdere guards/config-wijzigingen tegelijk
- geen trend + session + risk gelijktijdig maximal tunen
- London/Asia niet promoten zonder dedicated test
- niet pure sum-R najagen zonder DD-context

---

## Doel van deze fase

Niet:

```text
meer trades maken
```

Wel:

```text
de sterkste edge vaker en groter traden
de zwakkere edge kleiner en selectiever traden
```

---

## Samenvatting

- Systeem en pipeline kunnen betrouwbaar zijn; **allocatie** is het optimalisatieprobleem.
- Expansion kwalificeert zich als primaire kwaliteit-edge in de voorbeeldrun; trend blijft zwakker op mean R bij veel trades.
- Session-keuze is groot; guards moeten **per hypothesis** getest worden.

Volgende strategy-fase in één zin:

```text
Expansion dominance · Trend downgrade · New York priority · guards alleen waar data het draagt
```

---

## Eindprincipe

```text
Niet de meeste trades winnen.
De beste context het meeste gewicht geven.
```
