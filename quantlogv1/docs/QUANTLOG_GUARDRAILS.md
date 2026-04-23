# QuantLog Guardrails

## 1. Doel

QuantLog moet stabiel blijven als waarheidlaag van de stack.

Dit document bewaakt scope en voorkomt dat QuantLog verandert in een monoliet.

---

## 2. QuantLog doet wel

- immutable event opslag (append-only)
- schema/contract validatie
- deterministic replay
- operationele samenvattingen
- ingest health checks
- run quality gating

---

## 3. QuantLog doet niet

- strategy decisions berekenen
- risk decisions nemen
- orders routen of brokeracties uitvoeren
- backtesting uitvoeren
- dashboards hosten als productlaag
- ML feature store / training pipeline zijn
- analytics warehouse vervangen

Als een feature een runtime tradingbeslissing neemt, hoort die niet in QuantLog.

---

## 4. Scope-creep signalen

Waarschuwingssignalen dat QuantLog te breed wordt:

- business logic in validator/replay modules
- stateful trading workflows in QuantLog code
- toenemende afhankelijkheden voor visualisatie/BI/ML
- QuantLog outputs die niet meer herleidbaar zijn naar ruwe events

---

## 5. Beslisregel: hoort dit in QuantLog?

Een feature hoort in QuantLog alleen als de kernvraag is:

> "Maakt dit eventkwaliteit, replaybaarheid, auditbaarheid of runkwaliteit beter?"

Als de kernvraag is:

> "Maakt dit tradingbeslissingen slimmer?"

dan hoort het in QuantBuild/QuantBridge of een researchlaag, niet in QuantLog.

---

## 6. Niet-onderhandelbare regels

1. `trace_id` en correlatievelden blijven kerncontract.
2. Schemawijzigingen volgen `EVENT_VERSIONING_POLICY.md`.
3. Replay van historische data blijft verplicht.
4. CI quality gates mogen niet worden omzeild.
5. QuantLog blijft het stabielste component van de stack.

