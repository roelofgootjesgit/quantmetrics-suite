# QuantMetrics System Canonical Structure

This file is the single source of truth for naming and repository roles.

## Canonical root

- `quantmetrics-suite/`

## Canonical repositories and roles

```text
quantmetrics-suite/

├── quantbuild/          # Decision Engine (no broker execution)
│   ├── signal pipeline
│   ├── strategy modules
│   ├── regime detection
│   ├── risk & guards
│   └── decision output (trade_action events)
│
├── quantbridge/         # Execution Engine
│   ├── broker adapters (cTrader, etc.)
│   ├── order lifecycle
│   ├── account routing
│   └── execution validation
│
├── quantlog/            # Event Backbone (append-only truth)
│   ├── event schema
│   ├── validation
│   ├── replay engine
│   └── JSONL storage
│
├── quantanalytics/      # Analysis Engine (read-only)
│   ├── funnel analysis
│   ├── guard attribution
│   ├── expectancy / PF / DD
│   └── research reports
│
├── quantmetrics_os/     # Orchestration Layer ("QuantOS")
│   ├── run management
│   ├── experiment config routing
│   ├── artifact bundling
│   └── environment control
│
└── quantresearch/       # Optional research workspace
    ├── hypothesis logs
    ├── experiment notes
    └── decision tracking
```

## Hard rules

1. Do not use versioned module names in runtime naming (for example `*v1`, `*v2` suffixes).
2. Versioning belongs in git tags, schema versions, and release notes.
3. Runtime/log identity must use canonical system names (`quantbuild`, `quantbridge`, `quantlog`, `quantanalytics`, `quantmetrics_os`).
4. New docs must reference this file when describing system structure.
