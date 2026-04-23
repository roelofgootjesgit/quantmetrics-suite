# Market cache (OHLC parquet)

QuantBuild leest prijsdata uit:

`data/market_cache/<SYMBOL>/<timeframe>.parquet`  
(bijv. `data/market_cache/XAUUSD/15m.parquet`)

## Waarom je dit niet in git ziet

`.gitignore` sluit `data/market_cache/` en `*.parquet` uit: de cache blijft **lokaal** (of op je VPS), maar wordt **niet** meegecommit. Daardoor verdwijnt hij niet bij een normale `git pull`; wél kun je hem kwijtraken bij een **schone clone**, een **andere machine**, of agressief opschonen (`git clean -fdx` wist ook genegeerde bestanden).

## Eénmalig / verversen (aanbevolen voor lange historie)

De Dukascopy-download in `app fetch` beperkt soms tot een korte batch. Voor **meerdere jaren** in één keer goed gevuld:

```bash
python scripts/fetch_dukascopy_xauusd.py --days 550 --tf 15m 1h
```

Pas `--days` aan zodat je venster je backtest-dekking heeft (voor heel kalenderjaar 2025 vanaf 1 jan: ruim genoeg vanaf ~okt 2024 → ±550 dagen vanaf “vandaag”).

## Alternatief (CLI fetch)

```bash
python -m src.quantbuild.app --config configs/default.yaml fetch --days 400 --source dukascopy
```

Korter venster of andere symbolen: zie `scripts/fetch_dukascopy_xauusd.py` en `docs/CREDENTIALS_AND_ENVIRONMENT.md`.

## Vast pad houden

- Laat `data.base_path` in je YAML op `data/market_cache` staan (default), **of** zet één vaste map en overal dezelfde waarde gebruiken.
- Optioneel: omgevingsvariabele `DATA_PATH` wijst `config.py` naar een andere cache-root (zelfde structuur `SYMBOL/tf.parquet`).
