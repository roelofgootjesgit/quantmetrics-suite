# Academische research-laag — protocol-gap t.o.v. governance (QuantResearch)

Dit document vangt de diagnose **research engine vs. academische quant research** en wat we **stap voor stap** toevoegen. De bestaande ledger (`experiments/`, `registry/`) blijft de **audittrail**; dit protocol beschrijft wanneer een studie **inferentieel** aanspraak mag maken op “bevestigde edge”.

---

## Wat er al goed is (governance)

- Experiment-ID, run-IDs, configs, vensters, verdict (`PROMOTE` / registry).
- Reproduceerbare **pipeline** (`hyp002-pipeline`) en **metrics_bundle** (aggregaten).

Dat is **noodzakelijk**, maar **niet voldoende** voor academische claims.

---

## HARKing en retrospectieve “pre-registratie”

Als `pre_registration_status` = **`retrospective_reconstruction`**, dan is het document **geen** wetenschappelijke pre-registratie: het legt criteria vast **nadat** uitkomsten bekend zijn (Hypothesizing After Results are Known). Zulke bestanden zijn **template / administratie** — nuttig om het *formaat* van een echte pre-reg te oefenen, misleidend als je ze als pre-reg verkoopt.

`validate_preregistration_v1` vereist daarom:

- expliciete velden `pre_registration_status`, `pre_registration_valid`, `note`;
- bij `pre_registration_valid: true` een `locked_at_utc` **strikt vóór** `run_start_utc` van de primaire run (temporele integriteit);
- bij retrospectief + `valid: false` mag `locked_at` *na* de run (bewijs dat er geen valse temporal claim is); als `locked_at` toch vóór de run ligt, is dat **inconsistent** met “retrospectief” en wordt geflagd.

---

## Vier pijlers (vereist voor sterke claims)

### 1. Pre-registratie

Vóór (of gelijk bij start van) de primaire data-run vastleggen in machine-leesbaar formaat:

- **H0** en **H1** (formeel, toetsbaar op R of op gedefinieerde parameter).
- **alpha**, **minimum_n**, **minimum_effect_size_r** (economische vloer).
- Optioneel: **target_power**, datavenster, instrument.
- **pre_registration_timestamp_utc** (immutable referentie; idealiter git-commit vóór run).

**Implementatie v1:** `pipelines/hyp002_preregistration.json` + schema `schemas/hypothesis_preregistration_v1.schema.json`. De pipeline kopieert naar `experiments/EXP-002/preregistration.json` en rendert een sectie in `hypothesis.md`.

### 2. Statistische toetsing (niet alleen `mean_r`)

Aggregaat `expectancy_r` en `n` zijn **beschrijvend**. Toevoegen (wanneer per-trade R beschikbaar is):

- p-waarde (bijv. éénzijdige toets `E[R] > 0` of `> minimum_effect_size_r`),
- 95% CI (parametric of **bootstrap** op trade-R),
- Cohen’s *d* (effectgrootte op trade-R),
- robuuste toets (Wilcoxon) bij scheve verdeling.

**Status:** velden in `results_summary.md` gemarkeerd als *pending* tot QuantBuild/QuantLog een **R-lijst** exporteert.

### 3. Gecontroleerde isolatie (factorial / factor-gating)

Combinaties zoals “C=2 + expansion-block” leveren een **bundel**-effect; causale attributie vereist:

- baseline → + één factor → + interactie (factorial of sequentiële ladder),
- vastgelegd in `matrix_definition.variants` met expliciete factorlabels.

**Status:** HYP-002 manifest bevat meerdere runs; een strikte **factorial** matrix is roadmap (QuantBuild configs + manifest).

### 4. Reproducibiliteit voor derden

Minimaal: exacte **config + data-provenance + code-revision** (git SHA in bundle). Idealiter: **per-trade R** + datahash + seed (indien stochastisch).

**Status:** `metrics_bundle.json` uitbreiden met `git_commit` / `data_fingerprint` (roadmap); R-lijst uit JSONL/export.

---

## Twee statusstromen (nu in `experiment.json` voor EXP-002)

| Veld | Betekenis |
|------|-----------|
| `governance_status` | Descriptieve / interne criteria (aggregaten, drempels). |
| `academic_status` | Inferentie + echte pre-reg; `PENDING` tot geïmplementeerd. |
| `effective_status` | `GOVERNANCE_ONLY — not academically validated` tot beide trajecten PASS. |

`promotion_decision` in het ledger blijft bestaan voor compatibiliteit; **beslis nooit op “volgende fase” alleen op `governance_status`** als academische eisen van toepassing zijn.

---

## Verdict-laag (doeltoestand)

Een experiment krijgt pas een **academische** `PROMOTE` als (conceptueel):

| Gate | Betekenis |
|------|-----------|
| `pre_registration_verified` | preregistratie bestond vóór primaire run (git/policy) |
| `statistical_significance` | p &lt; alpha op pre-geregistreerde toets |
| `economic_significance` | punt-/intervalschatting &gt; `minimum_effect_size_r` |
| `reproducibility_check` | her-run / derde partij binnen tolerantie |

Tot die tijd blijft het ledger-veld `promotion_decision: PROMOTE` een **governance**-besluit op **descriptieve** drempels; zie `decision.md` en `preregistration.json` → `notes`.

---

## Research loop (doel)

1. Pre-registratie vastleggen (JSON + commit).  
2. Experimentdesign (factorial of single-factor).  
3. Uitvoering met logging van **per-trade R**.  
4. Inferentie (p, CI, d, robuust).  
5. Verdict (vier gates).  
6. Kennis (`confirmed_edges`) alleen met inferentie- + reproducibility-metadata.

---

## Gerelateerde bestanden

| Pad | Rol |
|-----|-----|
| `schemas/hypothesis_preregistration_v1.schema.json` | JSON Schema v1 |
| `pipelines/hyp002_preregistration.json` | HYP-002 voorbeeld-pre-reg |
| `quantresearch/preregistration.py` | `validate_preregistration_v1` |
| `experiments/EXP-002/preregistration.json` | Kopie na pipeline (audit) |

QuantBuild / QuantAnalytics uitbreidingen (JSONL `pnl_r` per trade, analytics-slice) volgen in aparte changes.
