# QuantBuild v2 — strategy host (greenfield)

Deze map is een **aparte Python-package** voor de multi-strategy engine. De bestaande bot blijft in `src/quantbuild/` staan; hier bouw je de host-laag, orchestrator en strategie-plugins zonder de huidige live-runner te breken.

## Relatie met v1

| Locatie | Rol |
|---------|-----|
| `src/quantbuild/` | Huidige productie-/referentiecode (broker, SQE, live runner) |
| `quantbuild_v2/` | Nieuwe architectuur: strategy interface, loader, portfolio-laag |
| `docs/QUANTBUILD_V2_MULTI_STRATEGY.md` | Architectuur en rollout-plan |

Later kun je v1-stukken **selectief importeren of porten** (broker factory, config, models) vanuit `quantbuild_v2`, in plaats van alles te dupliceren.

## Ontwikkeling

Vanaf de **repo-root** (`quantbuildv1`):

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
pip install -e quantbuild_v2
```

Test of de package laadt:

```bash
python -c "import quantbuild_v2; print(quantbuild_v2.__version__)"
```

## Structuur

```text
quantbuild_v2/
  src/quantbuild_v2/
    strategies/     # plugins (interface + voorbeelden)
    orchestrator/     # laden uit config, later signal queue + portfolio gate
  configs/accounts/ # per-account YAML (voorbeeld)
```

## Volgende stap

Implementeer Fase 1 uit het architectuurdoc: loader hardenen, eerste echte strategie die intern v1-modules aanroept, en een dunne runner die alleen `quantbuild_v2` gebruikt.
