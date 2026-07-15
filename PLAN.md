# Multi-LLM Investor Comparison — Deployment Plan

Fork of [LuckyOne7777/LLM-Investor-Behavior-Benchmark](https://github.com/LuckyOne7777/LLM-Investor-Behavior-Benchmark) (LIBB).
Goal: let multiple LLMs paper-trade a constrained stock universe, compare them in a
Streamlit UI, and host it on Railway. Executed as a series of Claude Code sessions;
architecture constraints live in `CLAUDE.md` (repo root) so every session inherits them.

## Locked decisions

- **Providers:** native SDKs — OpenAI, Anthropic, DeepSeek, Gemini. One adapter per provider, registry in `config/models.yaml` with `{name, provider, model_id, training_cutoff}`.
- **Historical replay:** any period allowed, framed as a **teaching demo**. UI must warn about lookahead bias whenever the period overlaps a model's training cutoff, and shade the in-training region on charts.
- **Live mode:** forward-only daily paper-trading loop — the methodologically clean experiment.
- **Deployment:** Railway (Hobby plan), single service, persistent volume at `/data`.
- **Benchmarks:** SPY **and** equal-weight of the chosen universe (the fair comparator for a hand-picked stock list).
- **Upstream hygiene:** keep `libb/` core unmodified where possible; build in `user_side/` and `app/`. Pin the upstream commit — the repo is young, with no tagged releases.

## Phase 0 — Prerequisites

- [ ] `gh` CLI authenticated to your GitHub account
- [ ] Claude Code installed and signed in
- [ ] Railway account on Hobby plan (volumes require it)
- [ ] API keys in hand: `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `DEEPSEEK_API_KEY`, `GEMINI_API_KEY` (Google AI Studio)
- [ ] Optional fallback data key (Tiingo or Alpha Vantage) in case Yahoo throttles Railway's datacenter IPs

```bash
gh repo fork LuckyOne7777/LLM-Investor-Behavior-Benchmark --clone
cd LLM-Investor-Behavior-Benchmark
# drop CLAUDE.md (from this package) into the repo root, then:
claude
```

## Session 1 — Environment + smoke test

- [x] Complete

Paste into Claude Code:

> Set up a venv, install requirements and the package editable, create a
> gitignored .env from my keys, and run user_side.workflow with one model on a
> 3-stock universe. Walk me through the generated run directory and the three
> metrics JSONs (behavior, performance, sentiment) so I understand LIBB's data
> model before we extend it.

**Exit criteria:** one clean end-to-end run; you can explain what lives in
`portfolio/`, `metrics/`, and `research/`.

## Session 2 — Provider adapters, universe constraint, replay engine

- [x] Complete

> Read libb/ and user_side/prompt_orchestration/, then:
> 1. Build four provider adapters (OpenAI, Anthropic, DeepSeek, Gemini) behind a
>    common `generate()` interface, with the model registry from CLAUDE.md.
>    Pin SDK versions in requirements.
> 2. Add universe enforcement in the order pipeline: orders for tickers outside
>    the configured universe are rejected and logged — never silently dropped.
> 3. Build the replay engine: for each trading day t in the range, construct the
>    prompt from yfinance data up to t only, tell the model "today is {t}", fill
>    orders at t+1 open, and reuse LIBB's run-dir layout so its metrics work
>    unchanged.
> 4. Write tests: universe rejection, adapter parity, and replay determinism
>    given canned model outputs.

**Design note:** replay prompts are price-history-only. Point-in-time news is
hard to source cleanly, and a leaky feed would quietly undermine even the demo
framing.

## Session 3 — Streamlit dashboard

- [x] Complete

> Build a Streamlit app in app/: sidebar for mode (live / replay), model picker,
> ticker universe, date range, starting cash. Charts: equity curve per model vs
> SPY and vs equal-weight of the universe. Tables comparing behavior.json,
> performance.json, sentiment.json across models. Replay runs as a background
> job with a progress bar. Each model chip shows its training_cutoff; if the
> replay period overlaps it, show a prominent amber banner — "in-training
> period: results reflect memorization, not forecasting skill" — and shade the
> pre-cutoff region of the chart.

The shaded region is the teaching money-shot: a model looking brilliant inside
its training window and ordinary after it is the lookahead-bias lesson in one
picture.

## Session 4 — Railway deployment

- [x] Complete

> Create a Dockerfile on python:3.11-slim running Streamlit on $PORT, with an
> in-process APScheduler job weekdays at 22:00 UTC for the live daily loop
> (safely after US close in both DST regimes). Make the daily job idempotent:
> skip if today's run is already finalized. All LIBB run paths under /data.

Then, outside Claude Code (or let it drive the CLI):

1. `railway init`
2. Attach a volume mounted at `/data` (Railway dashboard or CLI)
3. Set the four API keys as environment variables in the Railway dashboard
4. `railway up`

**Constraint:** a Railway volume mounts to a single service — keep the dashboard
and the scheduler in one process. Do not split them into separate services.

## Session 5 — Commit cadence and handoff

- [x] Complete

- Commit per session with clear messages; push to the fork.
- Verify `.env` and `/data` are gitignored before the first push.
- Pinned upstream base commit: `a4a4d70` ("Improve type handling of pending
  orders") — the fork's HEAD this work branches from (origin =
  `leokeechye/LLM-Investor-Behavior-Benchmark2`; no separate upstream remote).
- Deployed on Railway (project `handsome-love`, service `llm-app`) at
  https://llm-app-production-f181.up.railway.app

## Costs and risks

- **Live loop:** ~4 models × ~22 trading days ≈ 90–110 calls/month — a few dollars.
- **Replay demo:** one year × 4 models ≈ 1,000+ calls — order of US$10–40 depending on models. Cap or queue replay jobs so a big one doesn't starve the daily loop.
- **Data risk:** Yahoo occasionally throttles datacenter IPs; if yfinance flakes on Railway, swap in Tiingo/Alpha Vantage behind the same data interface.
- **Methodology:** everything here is paper trading. If realistic fills ever matter, Alpaca's paper API is the clean extension.
