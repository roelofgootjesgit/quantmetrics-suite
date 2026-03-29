# Quant stack integration acceptance — first truth-loop

Dit document legt de **eerste formele acceptance run** vast: QuantBuild + QuantBridge + QuantLog als één keten (`run → log → validate → replay → summarize → quality`).

Vul na elke acceptance run de secties **Resultaten** bij; houd repo-SHAs actueel.

---

## Referentie-integratie (commits na stack-wiring)

| Repo | Branch | Commit | Onderwerp |
|------|--------|--------|-----------|
| quantbuildE1 | `v2-development` | `3cf42b8` | Integrate QuantLog emitter into live runner and add post-run pipeline |
| quantBridge-v.1 | `main` | `ccdea09` | Make observability sink QuantLog-compatible with canonical envelope |
| quantLog v.1 | `main` | *(vul SHA na doc-commit)* | *(governance / CLI — vul in)* |

---

## Run config (invullen)

- **Datum (UTC)**: …
- **QuantBuild config**: bijv. `configs/strict_prod_v2.yaml` of `configs/ctrader_quantbridge_openapi.yaml`
- **`quantlog.enabled`**: `true`
- **`quantlog.base_path`**: …
- **`environment`**: `dry_run` / `live` / …
- **QuantBridge**: ja/nee, welke sink/path
- **Opmerkingen**: …

---

## Stappen (checklist)

1. Eén QuantBuild run met `quantlog.enabled: true` (liefst dry-run).
2. QuantBridge events laten meeschrijven naar dezelfde of afgesproken log-structuur.
3. `python scripts/quantlog_post_run.py` (uit QuantBuild-repo; `PYTHONPATH` naar QuantLog `src` indien nodig).
4. Output bewaren: validate, summarize, score-run, replay (eerste trace).

---

## Resultaten (invullen)

### Event counts

| Bron | Bestand / dagmap | Regels / events | Opmerking |
|------|------------------|-----------------|-----------|
| QuantBuild | `…/YYYY-MM-DD/quantbuild.jsonl` | … | … |
| QuantBridge | … | … | … |

### `validate-events`

- **Status**: pass / fail
- **Samenvatting** (plak relevante CLI-output of pad naar log): …

### `summarize-day`

- **Pad / excerpt**: …

### `score-run`

- **Score / status**: …

### `replay-trace` (eerste trace)

- **trace_id**: …
- **Status**: coherent / issues
- **Excerpt**: …

---

## Bekende afwijkingen

- Trace-discipline: controleer `trace_id`, `order_ref`, `position_id` end-to-end (Build → Bridge).
- Volume/duplicatie: dubbele emits, `source_seq` na restart — hier documenteren wat je ziet.

---

## Go / no-go

- [ ] Validator zonder errors op de acceptance-dag.
- [ ] Minstens één trace succesvol gereplayed als sanity check.
- [ ] Score-run gedraaid; uitslag genoteerd.
- [ ] Afwijkingen expliciet genoteerd (of “geen”).
