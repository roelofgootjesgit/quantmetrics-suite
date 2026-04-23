# ANALYTICS_OUTPUT_GAPS.md

## Status t.o.v. implementatie (2026-04)

Dit bestand blijft het **backlog-/gap-document** (wat we nog willen voor research-grade diagnostics). Het overlapt **deels** met andere docs (`QUANTANALYTICS_CONSUMER_PLAN.md`, `quantanalyticsv1/docs/LIVE_VPS_AND_LOCAL_BACKTEST.md`, `quantanalyticsv1/README.md`), maar beschrijft **meer detail** dan het huidige MVP.

| Thema (zie secties hieronder) | In de MDs / MVP al gedekt? | In code nu |
|-------------------------------|----------------------------|------------|
| Event counts, NO_ACTION-breakdown, **event-gebaseerde** funnel, regime/session **volume** | Ja — basisreports + `run_summary.json` | `quantmetrics_analytics.cli.run_analysis`, `analysis/run_summary.py`, `signal_funnel`, `no_trade_analysis` |
| JSONL → tabellen (decisions / guards / executions / closed_trades) | Ja — CLI export flags | `--export-*-tsv`, `datasets/*` |
| **`run_summary.json`** met funnel + NO_ACTION + expectancy-stub op `trade_closed` | Ja — blueprint/TODO | `--run-summary-json`, `--run-summary-md` |
| **§1 Data quality report** (anomalies, incomplete chains, orphans, duplicates) | **Nee** — nog te bouwen | Geen dedicated module; gebruik liever **`quantlog validate-events`** op dezelfde JSONL als harde kwaliteitspoort |
| **§2 Decision-grain funnel** (1 rij per `decision_cycle_id`) | **Nee** — MVP-funnel is **event counts** | Vereist join/groupby op `decision_cycle_id` |
| **§3 Guard-level diagnostics** (`guard_name`-histogram, slice per regime/session) | **Deels** — export `guard_decisions` TSV; geen apart rapportblok | Alleen ruwe tabellen / handmatige analyse |
| **§4 Expectancy slices** (per regime/session/setup/combo) | **Deels** — stub in `run_summary`; geen echte slices op closed trades overal | Join `trade_closed` ↔ contextevents nodig |
| **§5–7** Exit efficiency, lifecycle open vs closed, context completeness | **Nee** — nog te bouwen | — |

**Conclusie:** wat we “net hebben uitgewerkt” in code/docs dekt het **MVP-pad** (exports + samenvattende metrics). **Dit document beschrijft nog steeds wat daarboven komt** — dat moeten we **nog maken** als we de roadmap hier volgen (prioriteit P0/P1 onderaan).

---

## Doel

Dit document definieert welke analytics outputs nog ontbreken om QuantAnalytics te laten evolueren van een basis-summary tool naar een echte research en diagnostics engine.

De huidige analyzer-output is bruikbaar als MVP, maar nog niet volledig genoeg om:

- edge leaks exact te lokaliseren
- datakwaliteit actief te bewaken
- guard gedrag scherp te beoordelen
- exits correct te evalueren
- strategy iteration veilig en gericht uit te voeren

---

# Huidige status

De analyzer levert nu al waardevolle basis-output:

- total events
- event type counts
- NO_ACTION breakdown
- signal funnel
- basis performance stats
- regime / session context

Dit is goed voor een eerste MVP.

Maar de output is nu nog vooral beschrijvend:

→ wat gebeurde er

Terwijl QuantAnalytics uiteindelijk ook moet kunnen verklaren:

→ of de data betrouwbaar is  
→ waar de pipeline structureel faalt  
→ waar edge verloren gaat  
→ welke module verantwoordelijk is  

---

# Kritieke ontbrekende outputblokken

## 1. DATA QUALITY REPORT

### Probleem
De huidige output toont wel event counts, maar niet expliciet of de dataset betrouwbaar genoeg is voor analyse.

Voorbeeld:
- `signal_evaluated > signal_detected` is een anomaly
- `order_filled > trade_closed` kan legitiem zijn, maar moet expliciet verklaard worden
- `<missing>` in session context wijst op ontbrekende producer context

Deze signalen moeten zichtbaar worden in een apart quality report.

### Toe te voegen metrics

- total decision cycles
- total trade lifecycles
- missing required fields per eventtype
- missing `decision_cycle_id`
- missing `trade_id`
- missing `session`
- missing `regime`
- missing `setup_type`
- duplicate `decision_cycle_id`
- duplicate `trade_id`
- orphan guard events
- orphan fill events
- orphan trade_closed events
- incomplete decision chains
- incomplete trade lifecycles
- sequence anomalies
- context completeness percentages

### Gewenste output

```text
DATA QUALITY
- decision cycles: 296
- missing signal_detected: 4
- duplicate decision_cycle_id: 0
- orphan fills: 0
- incomplete trade lifecycles: 36
- missing session on signal_evaluated: 50.7%
- sequence anomalies: 1
Waarom dit nodig is

Zonder quality output zijn alle performance conclusies mogelijk verdacht.

2. DECISION-GRAIN FUNNEL
Probleem

De huidige funnel gebruikt event counts.
Dat is nuttig, maar niet voldoende.

Event-based funnels kunnen misleidend zijn als:

één cycle meerdere events emit
sommige events missen
events dubbel voorkomen

De analyzer moet daarom ook funnel metrics tonen op basis van:

→ 1 row per decision_cycle_id

Toe te voegen metrics
total decision cycles
cycles with signal_detected
cycles with signal_evaluated
cycles with guard_decision
cycles ending in NO_ACTION
cycles ending in ENTER
cycles reaching order_filled
cycles reaching trade_closed
Gewenste output
DECISION FUNNEL
- total cycles: 296
- evaluated: 296
- blocked: 224
- entered: 72
- filled: 72
- closed: 36
Waarom dit nodig is

Dit is de echte funnel voor strategy diagnostics.
Niet event volume, maar cycle outcome telt.

3. GUARD-LEVEL DIAGNOSTICS
Probleem

De huidige output toont risk_blocked, maar niet welk guard exact de blokkade veroorzaakte.

Voor strategy improvement is risk_blocked te grof.

Je wilt weten:

welke guard blokkeert
hoe vaak
in welke context
of dat logisch lijkt
Toe te voegen metrics
blocks per guard_name
block rate per guard
blocks per guard per session
blocks per guard per regime
blocks per guard per setup_type
Gewenste output
GUARD DIAGNOSTICS
- spread_guard: 22 blocks
- max_positions_guard: 14 blocks
- cooldown_guard: 11 blocks
- news_guard: 5 blocks
Later / advanced

Niet MVP:

missed winner rate
avoided loser rate
Net Block Value
Waarom dit nodig is

Anders kun je nooit goed bepalen of guard logic edge beschermt of throughput vernietigt.

4. EXPECTANCY SLICES
Probleem

De huidige output geeft basis performance stats, maar nog geen echte sliced expectancy.

Er is nu volume context:

regime counts
session counts

Maar nog niet:

performance per regime
performance per session
performance per setup_type
Toe te voegen metrics
expectancy per regime
expectancy per session
expectancy per setup_type
expectancy per combo_count
expectancy per side
expectancy per symbol

Daarnaast:

winrate per slice
avg R per slice
trade count per slice
profit factor per slice
Gewenste output
EXPECTANCY SLICES
By regime:
- trend: +0.41R (n=32)
- expansion: -0.12R (n=4)

By session:
- Asia: -0.08R (n=14)
- New York: +0.56R (n=18)
Waarom dit nodig is

Pas hier kun je strategie-instellingen gericht aanpassen.

5. EXIT EFFICIENCY REPORT
Probleem

De huidige output toont:

average PnL
average MAE
average MFE

Maar nog niet:

hoeveel van MFE je echt hebt vastgelegd
welke exit reasons domineren
of exits edge laten liggen
Toe te voegen metrics
avg realized R
avg MFE R
avg MAE R
MFE capture ratio
median MFE capture ratio
exit reason distribution
holding time vs outcome
time-to-profit
time-to-loss
Gewenste output
EXIT EFFICIENCY
- avg realized R: 0.33
- avg MFE R: 1.44
- avg capture ratio: 23%
- top exit reason: tp_hit
- avg holding time winning trades: 1840s
Waarom dit nodig is

Dit is direct linked aan edge retention.
Hier zie je of exits goed zijn of geld laten liggen.

6. OPEN VS CLOSED LIFECYCLE STATUS
Probleem

Wanneer fills groter zijn dan closes, is niet direct duidelijk:

zijn trades nog open
zijn closes missing
is de run geëindigd vóór closure
is de lifecycle incompleet

Dat moet expliciet zichtbaar zijn.

Toe te voegen metrics
total ENTER cycles
total filled trades
total closed trades
open trades remaining at end of run
fill-to-close completion rate
average age of open trades
Gewenste output
LIFECYCLE STATUS
- entered: 72
- filled: 72
- closed: 36
- open at end of run: 36
- fill-to-close completion rate: 50%
Waarom dit nodig is

Anders lijken performance metrics mogelijk onvolledig of misleidend.

7. CONTEXT COMPLETENESS REPORT
Probleem

Wanneer contextvelden deels ontbreken, worden slices minder betrouwbaar.

Voorbeelden:

missing session
missing regime
missing setup_type
missing confidence

Dit moet een expliciet diagnostisch blok zijn.

Toe te voegen metrics
completeness % for:
session
regime
setup_type
side
confidence
spread
combo_count
Gewenste output
CONTEXT COMPLETENESS
- session: 49.3% complete
- regime: 100.0% complete
- setup_type: 100.0% complete
- confidence: 100.0% complete
- spread: 100.0% complete
Waarom dit nodig is

Analytics kan alleen zo goed zijn als de producer context.

Prioritering
P0 — eerst toevoegen
Data Quality Report
Decision-Grain Funnel
Open vs Closed Lifecycle Status
Context Completeness Report

Dit zijn betrouwbaarheid-blokken.

P1 — daarna toevoegen
Guard-Level Diagnostics
Expectancy Slices
Exit Efficiency Report

Dit zijn edge-diagnostiek blokken.

Aanbevolen outputstructuur

De analyzer-output zou idealiter deze volgorde krijgen:

DATA QUALITY
EVENT COUNTS
DECISION FUNNEL
NO_ACTION BREAKDOWN
GUARD DIAGNOSTICS
LIFECYCLE STATUS
PERFORMANCE SUMMARY
EXPECTANCY SLICES
EXIT EFFICIENCY
CONTEXT COMPLETENESS
WARNINGS / ANOMALIES
Hard rules
Geen performance conclusie zonder data quality check
Geen sliced expectancy zonder closed trade basis
Geen guard waardeclaims zonder guard_name breakdown
Geen funnel percentages alleen op raw event counts
Missing context altijd expliciet rapporteren
Open trades altijd apart rapporteren van closed trades
MVP+ Definition of Done

QuantAnalytics-output is pas echt bruikbaar voor strategy improvement als het:

datakwaliteit expliciet toont
decision cycles correct samenvat
trade lifecycles correct samenvat
expectancy per relevante slice toont
exit efficiency zichtbaar maakt
missing context expliciet rapporteert
Samenvatting

De huidige analyzer-output is een goede eerste MVP.

De volgende stap is dat de output niet alleen vertelt:

→ wat er gebeurde

maar ook:

→ of de data betrouwbaar is
→ waar edge wordt weggefilterd
→ waar execution of exits waarde vernietigen
→ waar strategie-aanpassingen echt zin hebben