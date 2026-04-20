# QuantMetrics Analytics

**Deterministic analytics engine for event-driven trading systems**

---

## Overview

**QuantMetrics Analytics** is a downstream analysis module within the QuantMetrics suite.

It transforms raw event data from **QuantLog** into:

- structured datasets  
- actionable insights  
- system-level feedback  

This module is **not a dashboard**.

It is a **research and diagnostics engine** designed to:

- understand system behavior  
- validate trading edge  
- drive continuous improvement  

---

## Position in the Quant Stack
Market Data / News
↓
QuantBuild (Signal Engine)
↓
Risk Engine
↓
QuantBridge (Execution Engine)
↓
Broker / Trades
↓
QuantLog (Event Logging — Source of Truth)
↓
QuantMetrics Analytics ← YOU ARE HERE
↓
Insights / Reports / Feedback
↓
Strategy Improvements


---

## Core Purpose

This system answers:

- **Why are trades not executed?**
- **Where does the pipeline break down?**
- **Which filters destroy edge?**
- **What is the real expectancy of a strategy?**
- **How does performance vary across regimes and sessions?**
- **How does the system behave under real conditions?**

---

## Design Principles

### 1. **QuantLog is the Source of Truth**

- Raw data is **never modified**
- All analysis is **reproducible**
- Event replay remains **deterministic**

---

### 2. **Downstream Intelligence Only**

No analytics logic lives in:

- QuantBuild  
- QuantBridge  
- QuantLog  

All interpretation happens here.

---

### 3. **Reproducibility**

Every result must be:

- deterministic  
- version-controlled  
- traceable to raw events  

---

### 4. **Separation of Layers**


Raw Events → Structured Data → Entities → Metrics → Insights


Each layer has **one responsibility**.

---

## Data Pipeline


QuantLog JSONL (raw events)
↓
Ingestion
↓
Normalization
↓
Bronze (structured events - parquet)
↓
Silver (lifecycles & entities)
↓
Gold (metrics & aggregates)
↓
Reports / Feedback artifacts


---

## Storage Model


analytics_data/

bronze/
events/

silver/
signal_cycles/
trade_lifecycles/

gold/
metrics/

reports/
daily/
runs/


---

## Core Concepts

### **Signal Cycle**

A single decision loop:


signal_detected
→ signal_evaluated
→ risk_guard_decision
→ trade_action


Used to explain:

- why trades happen  
- why trades are blocked  

---

### **Trade Lifecycle**

Full execution path:


order_submitted
→ order_filled
→ position_open
→ position_closed


Used to measure:

- execution quality  
- trade performance  
- MAE / MFE  

---

### **Position Lifecycle**

Lifecycle of an open position:

- entry  
- drawdown (MAE)  
- expansion (MFE)  
- exit  

---

## Analysis Modules

### **1. No-Trade Analysis**

Breakdown of why trades are not executed:

- cooldown_active  
- regime_blocked  
- session_blocked  
- risk_blocked  
- no_setup  

---

### **2. Signal Funnel**

Pipeline throughput:


Detected → Evaluated → Risk Passed → Executed


Used to identify bottlenecks.

---

### **3. Performance Metrics**

- PnL  
- PnL (R-multiple)  
- Expectancy  
- Winrate  
- Drawdown  
- MAE / MFE  

---

### **4. Contextual Performance**

Performance segmented by:

- regime (trend / compression / expansion)  
- session (Asia / London / New York)  
- strategy  

---

### **5. System Behaviour Analysis**

- cooldown effects  
- filter impact  
- risk throttling  
- event latency  

---

## Output Types

### **Diagnostic Reports (Human)**


Trades: 0

Top reasons:

cooldown_active: 64%
compression_regime: 22%

Insight:
System is over-filtered during NY session.


---

### **Feedback Artifacts (Machine)**

```json
{
  "issue": "low_trade_frequency",
  "root_causes": ["cooldown_active", "compression_regime"],
  "suggestions": [
    "reduce cooldown duration",
    "disable compression trades"
  ]
}
What This Is Not
Not a trading bot
Not a signal generator
Not a dashboard tool
Not a BI platform
What This Is

A research and diagnostics engine for:

validating edge
understanding system behavior
improving trading strategies
enabling a closed feedback loop
Development Approach

Built in iterative sprints:

Raw ingestion (JSONL → DataFrame)
No-trade analysis (decision breakdown)
Signal funnel (pipeline diagnostics)
Trade lifecycle (performance)
Context intelligence (edge detection)

Each step is:

directly runnable on real data
incrementally extending the system
Future Direction
automated feedback loops into QuantBuild
strategy optimization suggestions
anomaly detection
multi-strategy portfolio analysis
real-time analytics
Philosophy

A trading bot executes trades.
A trading system understands itself.

QuantMetrics Analytics is built to ensure the latter.
