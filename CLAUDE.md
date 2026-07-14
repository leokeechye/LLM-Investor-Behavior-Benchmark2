# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# Project: Multi-LLM Investor Comparison on LIBB

Fork of LuckyOne7777/LLM-Investor-Behavior-Benchmark. Goal: multiple LLMs
(OpenAI, Anthropic, DeepSeek, Gemini — native SDKs, keys in .env) paper-trade
a constrained stock universe, compared in a Streamlit UI, deployed on Railway.
The session-by-session execution plan is in PLAN.md.

## Standing constraints (ask before changing)

These are locked decisions that apply to all work, built or not:

- **Keep `libb/` core unmodified where possible**; build in `user_side/` and
  `app/` so the fork stays mergeable with upstream.
- **Run state root is `LIBB_DATA_DIR`** (`user_side/paths.py`): defaults to
  `user_side/runs` locally, set to the Railway volume `/data` in the Dockerfile.
  Never commit `.env` or `/data`. Generated replay runs (`user_side/runs/replay/`)
  are gitignored; the committed `run_v1/*` dirs are empty scaffolding.
- **Benchmarks are SPY *and* equal-weight of the chosen universe** — the fair
  comparator for a hand-picked stock list.
- **Deployment is a single Railway service**: a volume mounts to one service,
  so the Streamlit dashboard and the scheduler must live in one process.

## To build (target architecture — mostly not yet implemented)

The pieces below are the *work*, not existing code. Follow these shapes when
building them; each notes current status. Full per-session breakdown in PLAN.md.

- **Provider adapters + model registry.** ✅ *Built.* One adapter per provider
  behind a common `generate(prompt)->str` interface in `user_side/providers/`
  (`base.py`, `openai_adapter.py`, `deepseek_adapter.py`, `anthropic_adapter.py`,
  `gemini_adapter.py`, `registry.py`). Registry in `config/models.yaml`
  (`{name, provider, model_id, training_cutoff}`); `prompt_models.py` dispatches
  by run-dir name (`libb._root.name`). `.env` loaded via python-dotenv.
- **Universe enforcement at order validation.** ✅ *Built.* `user_side/universe.py`
  `enforce_universe()` rejects+logs (status `REJECTED`) any out-of-universe order
  to the trade_log — never silently dropped. Universe in `config/universe.yaml`;
  injected into both live prompts. Called before `save_orders` in both workflows.
- **Replay engine (historical mode).** ✅ *Built.* `user_side/replay.py`
  `run_replay()` drives day-by-day, point-in-time, fills at next-session open
  (reuses LIBB's fill logic; order dates forced to `next_trading_day`). Prompt in
  `user_side/prompts/replay_prompt.py` is **price-history-only** (no news).
  Overlap with a model's `training_cutoff` is flagged. CLI: `python -m user_side.replay`.
- **Streamlit dashboard (`app/`).** ✅ *Built.* `app/streamlit_app.py` +
  `app/data_access.py`: live/replay mode, model picker, equity curves per model
  vs SPY & equal-weight, behavior/performance/sentiment tables, amber
  lookahead-bias banner + shaded in-training region. Run:
  `streamlit run app/streamlit_app.py`.
- **Live daily loop scheduler.** ✅ *Built.* `user_side/scheduler.py`
  `start_scheduler()` runs the live flow weekdays 22:00 UTC (APScheduler), with an
  idempotent job (`run_live_once` skips closed/already-finalized days). Started by
  `run.py`, gated by `ENABLE_SCHEDULER`.
- **Railway deployment.** ✅ *Built.* `Dockerfile` (python:3.12-slim; libb uses
  3.12-only f-strings) →
  `run.py`, which runs the scheduler + Streamlit on `$PORT` in one service. Run
  state under `LIBB_DATA_DIR` (=`/data` on Railway; see `user_side/paths.py`).
  Steps in `DEPLOY.md`. (Image not built locally — Docker unavailable here; Railway
  builds it.)

## Commands

```bash
# Setup (Python >= 3.10)
python3 -m venv .venv && source .venv/bin/activate
pip install --upgrade pip && pip install -r requirements.txt && pip install -e .

# Verify the package imports from source
python -c "import libb; print(libb.__file__)"

# Run the live example workflow (uses today's date)
python -m user_side.workflow

# Run the historical backtest loop (iterates a fixed date range)
python -m user_side.backtesting_workflow

# Run a historical replay for one model (point-in-time, price-only)
python -m user_side.replay --model gpt-4.1 --start 2024-02-01 --end 2024-02-16

# Launch the dashboard
streamlit run app/streamlit_app.py

# Tests (pytest configured in pyproject; network-free)
python -m pytest -q
```

Requires provider API keys in the environment or `.env` (`OPENAI_API_KEY`,
`DEEPSEEK_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`) for anything that calls
a model. The test suite (`tests/`) is fully network-free (stubbed prices, canned
model outputs). No linter/formatter is configured.

## Architecture: how LIBB works

**`libb/` is the reusable core; `user_side/` is the app built on top of it.**
Keep provider/orchestration/universe/replay work in `user_side/` and `app/` so
`libb/` stays mergeable with upstream.

### The `LIBBmodel` facade (`libb/model.py`)
One `LIBBmodel(model_path, run_date, config)` instance == one model's run for one
date. It is the single entry point and delegates to the subpackages:
- `core/` — `Processing` (order execution orchestration), `DiskReader`/`DiskWriter`
- `execution/` — buy/sell/stop-loss logic, order processing, market data (yfinance)
- `metrics/` — `performance` (Sharpe/Sortino/drawdown/CAPM), `behavior`
  (HHI/turnover/loss-aversion/order-quality), `sentiment` (Loughran-McDonald lexicon)
- `graphs/` — equity and sentiment plots
- `other/types_file.py` — `DiskLayout` (all on-disk paths), `Order`, `Log`, snapshots

### State is entirely on disk; the run directory is the data model
Every run persists to a fixed tree under `model_path` (defined by
`DiskLayout.from_root`): `portfolio/` (cash.json, portfolio.csv, *_history.csv,
trade_log.csv, pending_trades.json), `metrics/{behavior,performance,sentiment}.json`,
`research/{daily_reports,deep_research,prompts}/`, `logging/`, and `config.json`.
`ensure_file_system()` creates all of it on construction. Existing example runs
live in `user_side/runs/run_v1/{deepseek,gpt-4.1}/`.

### The daily execution loop
Per model, per date, a workflow does:
1. `libb.process_portfolio()` — fills the **previous** run's pending orders, updates
   history, writes a logging record.
2. Build a prompt and call the model → free text containing an `<ORDERS_JSON>{...}</ORDERS_JSON>` block.
3. `parse_json(report, "ORDERS_JSON")` extracts the orders (`libb/other/parse.py`).
4. `libb.save_orders(...)` writes them to `pending_trades.json` — they fill on the
   **next** run (next-day-open semantics). `libb.analyze_sentiment(report, ...)` and
   `save_daily_update`/`save_deep_research` persist the rest.

Orders (`Order` TypedDict) use `action` `"b"`/`"s"`/`"u"` (update stop-loss);
`process_order` routes on that. `user_side/workflow.py` runs a single **live** day;
`user_side/backtesting_workflow.py` loops a date range. Both branch on weekday:
Fri = weekly deep-research flow, Mon–Thu = daily flow, weekends skipped.

### Safety invariants (do not weaken)
- **Atomic with rollback:** `process_portfolio()` snapshots disk on construction
  (`STARTUP_DISK_SNAPSHOT`); on any exception it restores the snapshot and marks the
  instance invalid. A failed instance **cannot be reused** — construct a new one.
- **Forward-only ledger:** it refuses to run a `run_date` that is in the future,
  already recorded, or on/before the last recorded date (no back-jumping, no overwriting history).
- **NYSE calendar:** non-trading days are skipped (logged as SKIPPED), not executed.

### Config
`config` dict keys and defaults live in `libb/other/config_setup.py`:
`risk_free_rate` (0.045), `trading_days_per_year` (252), `starting_cash` (10000),
`slippage_pct_per_trade` (0.0), `locked` (True). Config is validated
(`verifiy_config`) and set into a process-global via `set_config`. If disk
`config.json` has `locked: True`, a mismatched passed-in config is **ignored** in
favor of disk — unlock or edit `config.json` to change a run's parameters.

## Further docs
`docs/` covers LIBB's philosophy and internals — start at `docs/README.md`;
`docs/important-constraints.md` and `docs/workflow.md` are the most load-bearing.
