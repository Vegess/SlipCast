# SlipCast analysis notebooks

Two notebooks that explore SlipCast's demo data and reproduce its model evaluation. They
load data **through the backend services** (`backend/app/services`), exactly as the API
does, so their numbers match the app's Model evaluation page for the same day.

| Notebook | What it shows |
|---|---|
| [`01_exploratory_analysis.ipynb`](01_exploratory_analysis.ipynb) | Cycle-time distributions, throughput, cumulative flow, and slip rate by type, theme and owner; plans and ticket quality versus slipping. |
| [`02_model_evaluation.ipynb`](02_model_evaluation.ipynb) | The type classifier, slip-risk model, reference-class coverage and Monte Carlo backtest, with the time-based split and baselines explained. |

Both are saved **with outputs**, so they render on GitHub without running anything.

## Run them yourself

From the repository root (Python 3.12):

```bash
python -m venv notebooks/.venv
```

```bash
source notebooks/.venv/bin/activate   # Windows: notebooks\.venv\Scripts\activate
```

```bash
python -m pip install -r notebooks/requirements.txt
```

```bash
cd notebooks && python -m jupyter lab
```

To re-run a notebook end to end and save its outputs (what was done before committing):

```bash
python -m jupyter nbconvert --to notebook --execute --inplace 01_exploratory_analysis.ipynb
```

## Notes

- `slipcast_data.py` generates the seeded demo project and wraps it in the backend's
  `Analysis` class. It fixes "today" to 2026-11-05 so results are reproducible; the live
  app uses the real date, so its demo numbers can differ slightly.
- The notebook dependencies (Jupyter, matplotlib, seaborn) are listed in
  `notebooks/requirements.txt` and are **not** installed in the API image: the API image is
  built from `backend/` only, and the root `.dockerignore` excludes `notebooks/` from any
  build that uses the repository root as its context.
- The data is synthetic. The notebooks show the methods work and how they are evaluated;
  on real data, SlipCast's forecast ledger measures accuracy per team.
