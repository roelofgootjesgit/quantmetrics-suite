# Guard Attribution Engine

## Doel

Begrijpen **wat filters en guards met edge doen**: wie blokkeert hoe vaak, in welke context, en of dat waarschijnlijk winners kost (niveau A) of dat je het **causaal** kunt meten door reruns (niveau B).

QuantLog is de bron; analytics leest alleen.

---

## Input

- Consolidated QuantLog JSONL (backtest/paper), minimaal:
  - `signal_evaluated`
  - `risk_guard_decision`
  - `trade_closed`
- Optioneel: `trade_action` (funnel / NO_ACTION-analyse elders).
- Per analyse exact één **`run_id`** (niveau A) of twee **`run_id`s** (niveau B).

---

## Niveau A — slice-counterfactual (snelle triage)

Werking: voor elke **BLOCK** op een beslisronde wordt context uit `signal_evaluated` gecombineerd met het **gemiddelde gerealiseerde `pnl_r`** van trades in dezelfde slice (regime × session × setup × signal × richting). Onder een minimum sample in die slice → fallback (o.a. globaal gemiddelde); dat staat per rij vastgelegd.

**Limiet:** geen echte contra-factuele trade; alleen een **benadering** voor prioritering van onderzoek.

CLI: `quantmetrics-guard-attribution` (`quantmetrics_analytics.cli.guard_attribution`).

---

## Niveau B — rerun compare (hoofdwaarheid voor beslissingen)

Werking: twee engine-runs (**baseline** vs **variant**) op **dezelfde historische window** en data; verschil wordt gemeten op **gerealiseerde** `trade_closed` plus **BLOCK-tellingen per guard**.

Dat is de sterkste vorm in deze stack: de engine voert uit wat hij zou doen als de guard anders staat.

CLI: `quantmetrics-guard-attribution-compare` (`quantmetrics_analytics.cli.guard_attribution_compare`).

**Advies:** niveau A mag zeggen `likely_overblocking`; **strategy-wijzigingen baseer je op niveau B** (rerun compare bevestigt of verworpen).

---

## Output artifacts

| Artefact | Niveau |
|----------|--------|
| `output_rapport/guard_attribution_<run_id>.json` | A |
| `output_rapport/guard_attribution_<run_id>.md` | A |
| `output_rapport/guard_attribution_compare_<baseline>_vs_<variant>.json` | B |
| `output_rapport/guard_attribution_compare_<baseline>_vs_<variant>.md` | B |

In de JSON staan o.a. scorecards (A), Δ-trade-metrics en guard-block-tabellen (B).

---

## Hoe beslissingen te interpreteren

- **Labels (A)** zoals `likely_overblocking` / `likely_protective` zijn **heuristieken**, afhankelijk van slice-steekproef en drempels. Geen productie-switch op label alleen.
- **Δ mean R / sum R / max DD / PF (B)** vertellen wat de variant **daadwerkelijk** deed versus baseline op hetzelfde venster.
- **Δ blocks per guard:** verwacht bij een gerichte guard-experiment dat voor die guard de BLOCK-count zakt (of het gedrag zichtbaar verschuift); meerdere guards tegelijk verschuiven maakt dit onleesbaar.

---

## Experimentdiscipline (verplicht voor causaliteit)

Voor een geldige **guard attribution compare**:

1. **Exact één** guard- of filterconfig-verschil tussen baseline en variant (geen combo’s).
2. **Zelfde data window** (datums, symbol, timeframe) en waar mogelijk dezelfde cache/build.
3. **Baseline en variant expliciet benoemen** in config-naam, commit-bericht of run-label; in het B-rapport: `--baseline-label` / `--variant-label`.
4. **`run_id`s vastleggen** in je research log (notities, changelog, experiment-tabel) zodat resultaten reproduceerbaar blijven.

Als je dit niet afdwingt, **vervuilt** de vergelijking: je meet dan meerdere effecten tegelijk en kunt geen guard toeschrijven.
