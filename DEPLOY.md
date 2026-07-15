# Deploying to Railway

Single service, single volume, one container running **the Streamlit dashboard +
the in-process live-loop scheduler** (see `run.py`). A Railway volume mounts to one
service, so both live together — do **not** split them into separate services.

## What the container does

`Dockerfile` (python:3.12-slim) → `CMD ["python", "run.py"]`:
- starts the APScheduler live loop (weekdays 22:00 UTC — after US close in EST & EDT),
- launches Streamlit on `$PORT` (Railway injects `PORT`).

Run state is written under `LIBB_DATA_DIR` (baked to `/data` in the image) — the
Railway volume — so `run_v1/` (live) and `replay/` runs persist across deploys.

## Prerequisites

- Railway account on the **Hobby plan** (volumes require it)
- `railway` CLI authenticated (`railway login`)
- API keys: `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `DEEPSEEK_API_KEY`, `GEMINI_API_KEY`

## Steps

```bash
# 1. Create / link the project (from the repo root; Railway builds the Dockerfile)
railway init

# 2. Attach a volume mounted at /data  (Railway dashboard → Volumes, or:)
railway volume add --mount-path /data

# 3. Set the provider API keys (dashboard → Variables, or:)
railway variables set \
  OPENAI_API_KEY=... ANTHROPIC_API_KEY=... DEEPSEEK_API_KEY=... GEMINI_API_KEY=...
# LIBB_DATA_DIR=/data and ENABLE_SCHEDULER=1 are set in the Dockerfile;
# override in Variables if needed (e.g. ENABLE_SCHEDULER=0 to serve UI only).

# 4. Build + deploy
railway up
```

## Notes

- **All four keys are required by default** — the live job iterates every model in
  `MODELS` (`user_side/workflow.py`). To run fewer, trim that list (and the models
  in `config/models.yaml` if desired).
- **Idempotent job:** if today's session is already finalized for every model, the
  scheduler skips it — safe across restarts/redeploys and misfires.
- **First load shows "no runs found"** until the scheduler's first run (or a replay)
  populates `/data`.
- **Cost:** ~4 models × ~22 trading days ≈ a few dollars/month for the live loop;
  replay is heavier (cap large replay ranges).

## Local Docker smoke test (optional, needs Docker)

```bash
docker build -t libb-app .
# UI only (no scheduler), local ./data volume:
docker run --rm -p 8501:8501 -e PORT=8501 -e ENABLE_SCHEDULER=0 \
  -v "$PWD/data:/data" --env-file .env libb-app
# open http://localhost:8501
```
