# Contributing

Thanks for your interest in improving QuantMetrics Suite.

## Scope

This repository focuses on evidence-based strategy evaluation infrastructure. Contributions should improve reliability, auditability, reproducibility, or analysis quality.

## Development workflow

1. Fork the repository and create a feature branch.
2. Keep changes small and reviewable.
3. Add or update tests for behavior changes.
4. Run local checks before opening a PR:

```bash
pip install -r requirements.txt
pytest tests -q
python run_demo.py
```

## Pull request guidelines

- Explain the problem, change, and expected impact.
- Avoid unrelated refactors in the same PR.
- Do not add secrets, credentials, or large raw datasets.
- Preserve module boundaries (`quantbuild`, `quantbridge`, `quantlog`, `quantanalytics`, `quantmetrics_os`, `quantresearch`).

## Documentation expectations

If behavior or interfaces change, update the relevant docs and README sections in the same PR.
