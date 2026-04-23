# QuantLog Ops Console — Build Handbook v0.1

## Purpose

The QuantLog Ops Console is the **operator layer** on top of QuantLog.

Its purpose is simple:

> Understand what the trading system did in under 60 seconds — without SSH, CLI, or manual log retrieval.

This is not a dashboard for aesthetics.
This is a **decision visibility system**.

---

# 1. System Role

## Position in Architecture

```
Market Data / News
        ↓
Signal Engine (QuantBuild)
        ↓
Risk Engine
        ↓
Execution Engine (QuantBridge)
        ↓
Event Logging (QuantLog)
        ↓
🔥 QuantLog Ops Console (THIS SYSTEM)
        ↓
Research / Strategy Improvement
```

This completes the **closed feedback loop**:

```
log → analyze → improve → deploy → repeat
```

Without this layer:

* Data exists ✅
* Insight does NOT ❌

---

# 2. Design Principles

## 2.1 Question-first

The system must answer:

* Why were there no trades?
* What blocked trades?
* Was the system active?
* Which runs are abnormal?

NOT:

* “Here are logs”

---

## 2.2 Speed > Perfection

* Fast load times
* No heavy queries
* Lazy loading
* Cached summaries

---

## 2.3 Zero Friction

* One URL
* One click → data
* No SSH required

---

## 2.4 Read-only Safety

STRICT RULE:

* No trading actions
* No system control
* No config edits

---

# 3. Scope Definition

## This IS:

* Read-only observability layer
* Log access interface
* Decision breakdown tool
* Debugging environment

## This is NOT:

* Trading system
* QuantLog replacement
* Analytics warehouse
* Monitoring cluster

---

# 4. Tech Stack (MVP)

* Python 3.10+
* Streamlit
* JSONL file-based logs
* No database

---

# 5. Directory Structure

```
quantlog_ops/

├── app.py
├── config.py
│
├── services/
│   ├── file_indexer.py
│   ├── event_loader.py
│   ├── summarizer.py
│   ├── exporter.py
│
├── pages/
│   ├── 1_Daily_Control.py
│   ├── 2_Decision_Breakdown.py
│   ├── 3_Event_Explorer.py
│   ├── 4_Downloads.py
│
└── utils/
    ├── parser.py
    ├── filters.py
```

---

# 6. Data Contract (REQUIRED)

Each event must be mappable to:

```json
{
  "timestamp_utc": "",
  "run_id": "",
  "event_type": "",
  "symbol": "",
  "session": "",
  "regime": "",
  "decision": "",
  "reason_code": "",
  "confidence": 0,
  "source_system": "",
  "order_ref": ""
}
```

If your logs do not expose this clearly → FIX QuantLog mapping first.

---

# 7. Core Services

---

## 7.1 File Indexer

**Goal:** Discover available log days and runs

### Input:

```
/logs/quantlog_events/YYYY-MM-DD/
```

### Output:

```python
[
  {
    "date": "2026-04-19",
    "runs": [
      {
        "run_id": "abc123",
        "path": "...",
        "files": [...]
      }
    ]
  }
]
```

---

## 7.2 Event Loader

**Goal:** Load JSONL safely

### Requirements:

* Lazy loading
* Chunk support
* Fault tolerant

---

## 7.3 Summarizer (CRITICAL)

**Goal:** Turn raw logs into insights

### Output:

```python
{
  "total_events": 1245,
  "signals": 300,
  "entries": 5,
  "no_action": 295,
  "errors": 2,
  "by_reason": {
    "cooldown_active": 120,
    "no_setup": 80
  },
  "by_regime": {
    "compression": 200,
    "expansion": 100
  }
}
```

---

## 7.4 Exporter

**Goal:** Remove need for SSH

### Features:

* Download JSONL
* Zip full run
* Export CSV

---

# 8. UI Pages

---

## 8.1 Daily Control (CORE PAGE)

### Goal:

Understand system state instantly

### UI:

| Run ID | Events | Signals | Entries | No Action | Errors | Download |
| ------ | ------ | ------- | ------- | --------- | ------ | -------- |

### KPIs:

* total runs
* total events
* total trades
* dominant reason

---

## 8.2 Decision Breakdown

### Goal:

Why no trades?

### Must show:

```
cooldown_active → 60%
compression → 25%
no_setup → 10%
```

### Components:

* reason_code histogram
* regime distribution
* top blockers

---

## 8.3 Event Explorer

### Goal:

Deep debug

### Features:

* filters:

  * event_type
  * decision
  * symbol
  * regime

* table view

Click row → show raw JSON

---

## 8.4 Downloads

### Goal:

Replace manual log retrieval

### Buttons:

* Download day
* Download run
* Export summary CSV

---

# 9. Performance Rules

* Max 10k events per load
* Cache summaries
* Lazy load tables
* No full reload on filter

---

# 10. MVP Scope (STRICT)

## Must have:

* Daily Control page
* Decision Breakdown
* Event Explorer
* Downloads

## Must NOT have:

* PnL charts
* Trading controls
* AI insights
* Styling polish

---

# 11. Edge Integration

This system answers:

## Where is the edge?

→ Which signals fail

## How is edge measured?

→ signal → entry ratio

## What blocks trades?

→ reason_code distribution

## What changes next?

→ Signal Engine / Risk Engine

---

# 12. Build Order

## Step 1

File indexer

## Step 2

Daily Control page

## Step 3

Summarizer

## Step 4

Decision Breakdown

## Step 5

Event Explorer

## Step 6

Downloads

---

# 13. Acceptance Criteria

System is DONE when:

* No SSH needed
* Logs accessible in browser
* Can explain no-trade day in <60 seconds
* Can download logs in 1 click

---

# 14. Future (v0.2)

ONLY AFTER MVP:

* Telegram integration
* Auto reports
* Run comparison
* Anomaly detection

---

# 15. Final Rule

This is not a dashboard.

This is:

> The control panel of your trading desk.

If it does not speed up decision-making → it is wrong.
