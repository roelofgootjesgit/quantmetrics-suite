# QuantLog Ops Console — Sprint B Handbook

## Operator Usability Layer

## Doel van Sprint B

Sprint B is bedoeld om de QuantLog Ops Console van een werkende observability-tool naar een **snelle operator console** te brengen.

Sprint A heeft de basis gehard:

* caching
* health KPI’s
* no-trade explainer
* separate caps
* parser discipline

Sprint B richt zich op de volgende vraag:

> Hoe maak je dagelijkse review en debugging sneller, met minder frictie?

Dit is geen analytics sprint.
Dit is geen visual polish sprint.
Dit is een **usability sprint**.

---

# 1. Sprint B Doelstelling

De operator moet:

* minder filters opnieuw hoeven zetten
* sneller kunnen wisselen tussen runs
* sneller uitzonderingen kunnen vinden
* sneller unknown / error / no_action kunnen isoleren
* sneller context meenemen tussen pagina’s

Succescriterium:

> De operator kan in enkele klikken van dagselectie naar oorzaak-analyse gaan, zonder steeds opnieuw dezelfde filters te zetten.

---

# 2. Scope van Sprint B

## In scope

* Session state voor vaste filters
* Quick filter buttons / toggles
* Run pinning / snelle run selectie
* Copyable metadata / context info
* Kleine UX-verbeteringen voor operator flow

## Niet in scope

* Auth
* Multi-user
* Database
* PnL
* Charts uitbreiden
* Trading controls
* Telegram integratie
* Styling overhaul

---

# 3. Principes

## 3.1 Operator speed first

Alles in deze sprint moet het aantal klikken verlagen.

## 3.2 State must survive navigation

Als een operator filters zet op pagina A, moeten die logisch blijven bestaan op pagina B.

## 3.3 Quick debug over full flexibility

Belangrijker dan “alle mogelijke filters” is:

* ENTER snel zien
* NO_ACTION snel zien
* ERRORS snel zien
* UNKNOWN snel zien

## 3.4 No hidden magic

Actieve filters moeten altijd zichtbaar zijn.

---

# 4. Sprint B Features

## 4.1 Session State Persistence

### Doel

Geselecteerde context behouden tussen pagina’s.

### Op te slaan in `st.session_state`

* selected_day
* selected_run_id
* selected_event_type
* selected_decision
* selected_symbol
* selected_regime
* quick_filter_mode
* pinned_run_id

### Gewenst gedrag

Als de gebruiker:

* een dag kiest op Daily Control
* daarna naar Event Explorer gaat

dan moet die dag automatisch geselecteerd blijven.

Als de gebruiker:

* een run selecteert
* daarna naar Decision Breakdown gaat

dan moet die run automatisch gebruikt worden waar logisch.

### Guardrails

* Als gekozen run niet meer bestaat voor de dag: reset naar `__all__`
* Als filterwaarde niet meer geldig is: reset alleen dat filter
* Geen hard crashes door stale session state

---

## 4.2 Quick Filter Bar

### Doel

Veelgebruikte debug-slices met 1 klik beschikbaar maken.

### Plaats

Boven Event Explorer en Decision Breakdown.

### Quick filters

* All
* ENTER only
* NO_ACTION only
* Errors only
* Unknown only

### UX-regel

De actieve quick filter moet duidelijk zichtbaar zijn.

---

## 4.3 Pinned Run

### Doel

Sneller werken op één run zonder steeds opnieuw te selecteren.

### Opslag

`st.session_state["ops_pinned_run_id"]`

### Regels

* Pinned run geldt alleen binnen de gekozen dag
* Als dag verandert en run niet bestaat: automatisch unpinnen of fallback naar `__all__`

---

## 4.4 Copyable Metadata Panel

Compact info-paneel + plain-text copy block voor notities / issues.

---

## 4.5 Sticky Filter Components

Elke filterwidget gebruikt stabiele keys (``ops_*``).

---

# 5. Technische Implementatie (repo)

| Pad | Rol |
|-----|-----|
| `quantlog_ops/utils/session_state.py` | Keys (`ops_*`), `sanitize_run_selection`, `scope_from_run_pick`, `reset_filters`, `format_copy_block` |
| `quantlog_ops/utils/quick_filters.py` | `apply_quick_filter`, `is_*_row` predicates |
| `quantlog_ops/page_fragments.py` | Gedeelde UI: `ensure_day_option`, `render_quick_filter_bar`, `render_context_copy_block`, `reset_filters_sidebar_button` |
| `quantlog_ops/pages/1_Daily_Control.py` | Dag + run (session), pin/unpin, context info, copy block |
| `quantlog_ops/pages/2_Decision_Breakdown.py` | Zelfde dag/run, quick filter vóór summarize, copy block |
| `quantlog_ops/pages/3_Event_Explorer.py` | Quick filter → detail substring filters, copy block |
| `quantlog_ops/pages/4_Downloads.py` | Toont sessie-dag/run + quick-modus in info |

**Session keys:** `ops_selected_day`, `ops_selected_run_id`, `ops_selected_event_type`, `ops_selected_decision`, `ops_selected_symbol`, `ops_selected_regime`, `ops_quick_filter_mode`, `ops_pinned_run_id`, plus `ops_events_root` voor events-pad.

---

# 6. UX-regels (samenvatting)

* Altijd tonen: dag, effectieve run, quick filter, cap waar relevant (`st.info` / `st.caption`).
* **Reset filters:** sidebar-knop zet quick → All en leegt detailvelden; run → pinned als geldig, anders `(all runs)`.
* Unknown-quick filter = expliciete debugging-modus (caption).

---

# 7. Acceptance Criteria

* [x] Dag en run blijven tussen pagina’s (zelfde `st.session_state` keys).
* [x] Quick filter blijft behouden (radio met `ops_quick_filter_mode`).
* [x] ENTER / NO_ACTION / Errors / Unknown quick modes met centrale helper.
* [x] Pin op Daily: `ops_pinned_run_id`; invalid pin wordt gesaneerd bij dag/run-wissel.
* [x] Metadata + plain-text copy block op Daily, Explorer, Breakdown.

---

# 8. Tests

| Bestand | Inhoud |
|---------|--------|
| `tests/test_ops_quick_filters.py` | Quick-modus slices |
| `tests/test_ops_session_state_logic.py` | Sanitize, reset, scope |
| `tests/test_ops_parser.py` | Bestaande parser/cap-tests (Sprint A) |

---

# 9. Definition of Done

Operator-flow: dag kiezen → run pinnnen → Decision Breakdown → NO_ACTION quick → Event Explorer → zelfde context zichtbaar → copy block plakken — **zonder opnieuw alles in te stellen**.

---

# 10. Mentor note

Sprint B voegt geen “meer power” toe; het **verlaagt frictie**. Context overleeft navigatie; veelgebruikte slices zijn één klik.
