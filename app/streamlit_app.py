"""Multi-LLM investor comparison dashboard.

Run with:  streamlit run app/streamlit_app.py
"""
import datetime as dt
import sys
from pathlib import Path

# Put the repo root on sys.path so `import user_side` / `import libb` work when
# Streamlit runs this file directly (it only adds the script's own dir).
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import altair as alt
import pandas as pd
import streamlit as st

from app.data_access import (
    available_models,
    benchmark_equal_weight,
    benchmark_spy,
    load_config,
    load_equity_curve,
    metrics_comparison,
)
from user_side.paths import LIVE_ROOT, REPLAY_ROOT
from user_side.providers.registry import load_registry
from user_side.replay import run_replay
from user_side.universe import load_universe

# Okabe-Ito — a published colorblind-safe categorical palette. Assigned to models
# in fixed order (never cycled); benchmarks use recessive dashed grays.
MODEL_PALETTE = ["#0072B2", "#E69F00", "#009E73", "#CC79A7", "#56B4E9", "#D55E00", "#F0E442"]
BENCH_COLOR = {"SPY": "#6E6E6E", "Equal-weight": "#111111"}
AMBER = "#E69F00"

st.set_page_config(page_title="Multi-LLM Investor Benchmark", layout="wide")
st.title("Multi-LLM Investor Comparison")

registry = load_registry()
universe = sorted(load_universe())

# ----------------------------------------------------------------------------
# Sidebar
# ----------------------------------------------------------------------------
mode = st.sidebar.radio("Mode", ["Live", "Replay"], help="Live = forward daily loop; Replay = historical teaching demo.")
run_root = LIVE_ROOT if mode == "Live" else REPLAY_ROOT

with st.sidebar.expander(f"Universe ({len(universe)} tickers)", expanded=False):
    st.write(", ".join(universe))

# Replay controls (real LLM + price calls — cost money and time).
if mode == "Replay":
    st.sidebar.subheader("Run a replay")
    replay_models = st.sidebar.multiselect("Models", list(registry.keys()))
    col_a, col_b = st.sidebar.columns(2)
    start_in = col_a.date_input("Start", dt.date(2024, 1, 2), key="rp_start")
    end_in = col_b.date_input("End", dt.date(2024, 2, 1), key="rp_end")
    lookback = st.sidebar.number_input("Lookback sessions", 5, 120, 30)
    st.sidebar.caption(
        "⚠️ Runs real model + price calls — this costs API credits. Each run is a "
        "fresh experiment: it **replaces** any previous replay for the chosen models."
    )
    if st.sidebar.button("Run replay", type="primary", disabled=not replay_models):
        bar = st.progress(0.0, text="Starting replay…")
        for m_idx, model_name in enumerate(replay_models):
            def _cb(done, total, day, _m=model_name, _i=m_idx):
                frac = (_i + done / total) / len(replay_models)
                bar.progress(frac, text=f"{_m}: {day} ({done}/{total})")
            run_replay(model_name, str(start_in), str(end_in),
                       lookback=int(lookback), reset=True, progress_cb=_cb)
        bar.progress(1.0, text="Replay complete")
        st.rerun()

# ----------------------------------------------------------------------------
# Model selection
# ----------------------------------------------------------------------------
models = available_models(run_root)
if not models:
    hint = "Run a replay from the sidebar." if mode == "Replay" else "Run the live workflow first."
    st.info(f"No runs found under `{run_root}`. {hint}")
    st.stop()

selected = st.multiselect("Models to compare", models, default=models)
if not selected:
    st.stop()

run_dirs = {m: f"{run_root}/{m}" for m in selected}
curves = {m: load_equity_curve(rd) for m, rd in run_dirs.items()}
curves = {m: c for m, c in curves.items() if not c.empty}
if not curves:
    st.warning("Selected models have no equity history yet.")
    st.stop()

starting_cash = float(load_config(next(iter(run_dirs.values()))).get("starting_cash", 10000))
all_dates = pd.concat([c["date"] for c in curves.values()])
start_d, end_d = all_dates.min(), all_dates.max()

# Model training-cutoff chips + lookahead-bias detection.
st.caption("Model training cutoffs — a replay period overlapping a cutoff is not a fair forecast test.")
chip_cols = st.columns(len(curves))
overlaps: dict[str, dt.date] = {}
for (m, _), col in zip(curves.items(), chip_cols):
    spec = registry.get(m)
    cutoff = spec.training_cutoff if spec else None
    col.metric(m, str(cutoff) if cutoff else "—", help="training_cutoff from config/models.yaml")
    if cutoff and start_d.date() <= cutoff:
        overlaps[m] = cutoff

if overlaps:
    detail = "; ".join(f"**{m}** (cutoff {c})" for m, c in overlaps.items())
    st.warning(
        f"⚠️ **In-training period.** For {detail}, results on/before the cutoff reflect "
        "**memorization, not forecasting skill.** The shaded region below marks it."
    )

# ----------------------------------------------------------------------------
# Equity chart
# ----------------------------------------------------------------------------
show_bench = st.checkbox("Show benchmarks (SPY & equal-weight) — fetches prices", value=False)

frames = []
domain, color_range, dash_kinds = [], [], []
for i, (m, c) in enumerate(curves.items()):
    frames.append(pd.DataFrame({"date": c["date"], "value": c["equity"], "series": m, "kind": "model"}))
    domain.append(m)
    color_range.append(MODEL_PALETTE[i % len(MODEL_PALETTE)])

if show_bench:
    try:
        with st.spinner("Fetching benchmark prices…"):
            spy = benchmark_spy(start_d, end_d, starting_cash)
            ew = benchmark_equal_weight(universe, start_d, end_d, starting_cash)
        for name, bdf in (("SPY", spy), ("Equal-weight", ew)):
            if not bdf.empty:
                frames.append(pd.DataFrame({"date": bdf["date"], "value": bdf["equity"], "series": name, "kind": "benchmark"}))
                domain.append(name)
                color_range.append(BENCH_COLOR[name])
    except Exception as e:
        st.info(f"Could not load benchmarks: {e}")

chart_df = pd.concat(frames, ignore_index=True)

color = alt.Color(
    "series:N",
    scale=alt.Scale(domain=domain, range=color_range),
    legend=alt.Legend(title=None, orient="top"),
)
x = alt.X("date:T", title=None)
y = alt.Y("value:Q", title="Portfolio value ($)", scale=alt.Scale(zero=False))

layers = []

# Shaded in-training band (drawn first, sits behind the lines).
if overlaps:
    band_df = pd.DataFrame({"start": [start_d], "end": [pd.Timestamp(max(overlaps.values()))]})
    layers.append(
        alt.Chart(band_df).mark_rect(color=AMBER, opacity=0.12).encode(x="start:T", x2="end:T")
    )
    rules_df = pd.DataFrame({"cutoff": [pd.Timestamp(c) for c in sorted(set(overlaps.values()))]})
    layers.append(
        alt.Chart(rules_df).mark_rule(color=AMBER, strokeDash=[4, 3]).encode(x="cutoff:T")
    )

model_df = chart_df[chart_df["kind"] == "model"]
layers.append(alt.Chart(model_df).mark_line(strokeWidth=2).encode(x=x, y=y, color=color))
if show_bench:
    bench_df = chart_df[chart_df["kind"] == "benchmark"]
    if not bench_df.empty:
        layers.append(alt.Chart(bench_df).mark_line(strokeWidth=2, strokeDash=[5, 4]).encode(x=x, y=y, color=color))

# Invisible points carry the hover tooltip.
layers.append(
    alt.Chart(chart_df).mark_circle(opacity=0).encode(
        x=x, y=y, color=color,
        tooltip=[alt.Tooltip("series:N", title="Series"),
                 alt.Tooltip("date:T", title="Date"),
                 alt.Tooltip("value:Q", title="Value", format="$,.0f")],
    )
)

st.altair_chart(
    alt.layer(*layers).interactive().properties(height=420).configure_axis(grid=True, gridOpacity=0.15),
    use_container_width=True,
)

# ----------------------------------------------------------------------------
# Metric comparison tables
# ----------------------------------------------------------------------------
st.subheader("Metric comparison (latest run per model)")
tab_perf, tab_behav, tab_sent = st.tabs(["Performance", "Behavior", "Sentiment"])
with tab_perf:
    st.dataframe(metrics_comparison(run_dirs, "performance"), use_container_width=True)
with tab_behav:
    st.dataframe(metrics_comparison(run_dirs, "behavior"), use_container_width=True)
with tab_sent:
    st.dataframe(metrics_comparison(run_dirs, "sentiment"), use_container_width=True)
