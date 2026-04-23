# Schema Change Checklist

Gebruik deze checklist bij elke schemawijziging.

- [ ] Impact op `event_version` beoordeeld (breaking vs non-breaking)
- [ ] `EVENT_VERSIONING_POLICY.md` toegepast
- [ ] Replay backward compatibility getest op oude fixtures
- [ ] Contract fixtures bijgewerkt (indien nodig)
- [ ] Validator tests bijgewerkt
- [ ] Smoke runner nog groen
- [ ] Sample day validate/summarize groen
- [ ] `score-run` boven threshold op clean dataset
- [ ] Anomaly quality gate faalt zoals verwacht
- [ ] Documentatie bijgewerkt (`docs/EVENT_SCHEMA.md`, root `README.md`, `docs/REPLAY_RUNBOOK.md`)

Geen merge zonder complete checklist.

