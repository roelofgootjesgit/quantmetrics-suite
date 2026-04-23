# Quant Metrics Suite

Unified monorepo for the full Quant suite.

## Repository Structure

- `quantbuildv1/` - backtesting and build workflows
- `quantbridgev1/` - bridge and integration services
- `quantlogv1/` - event logging and audit layer
- `quantmetrics_os/` - metrics, experiment runs, and reporting
- `quantanalyticsv1/` - analytics and strategy analysis

Each module keeps its own `README.md` as module-level source of truth.

## Getting Started

1. Open this repository root in Cursor.
2. Navigate to the module you want to work on.
3. Follow that module's `README.md` for setup, test, and run commands.

## Monorepo Notes

- History from each original repository is preserved via `git subtree`.
- Cross-module changes can now be developed and reviewed in one pull request.
