"""Allow ``python -m quantresearch`` → ledger CLI."""

from quantresearch.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
