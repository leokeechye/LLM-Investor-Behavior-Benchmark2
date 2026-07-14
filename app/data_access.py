"""Data loading for the Streamlit dashboard.

Reads LIBB run directories (equity curves + metric JSONs) and computes the two
benchmarks (SPY and equal-weight of the universe), all normalized to the same
starting cash so every series shares one y-axis.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

import libb.execution.get_market_data as market_data
from libb.other.types_file import DiskLayout


def _layout(run_dir: str | Path) -> DiskLayout:
    return DiskLayout.from_root(Path(run_dir))


def available_models(run_root: str | Path) -> list[str]:
    """Model run-dir names under ``run_root`` that have an equity history."""
    root = Path(run_root)
    if not root.exists():
        return []
    return sorted(
        p.name
        for p in root.iterdir()
        if p.is_dir() and (p / "portfolio" / "portfolio_history.csv").exists()
    )


def load_config(run_dir: str | Path) -> dict:
    path = _layout(run_dir).config_path
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def load_equity_curve(run_dir: str | Path) -> pd.DataFrame:
    """Return date/equity/cash/positions_value/overall_return_pct, sorted by date."""
    path = _layout(run_dir).portfolio_history_path
    if not path.exists():
        return pd.DataFrame(columns=["date", "equity"])
    df = pd.read_csv(path)
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["date"])
    keep = [c for c in ["date", "equity", "cash", "positions_value", "overall_return_pct"] if c in df.columns]
    return df[keep].sort_values("date").reset_index(drop=True)


def load_metric(run_dir: str | Path, name: str) -> pd.DataFrame:
    layout = _layout(run_dir)
    path = {
        "behavior": layout.behavior_path,
        "performance": layout.performance_path,
        "sentiment": layout.sentiment_path,
    }[name]
    if not path.exists():
        return pd.DataFrame()
    data = json.loads(path.read_text(encoding="utf-8") or "[]")
    return pd.DataFrame(data)


def metrics_comparison(run_dirs_by_model: dict[str, str], name: str) -> pd.DataFrame:
    """Latest row of ``name`` metric per model, models as rows."""
    rows = {}
    for model, run_dir in run_dirs_by_model.items():
        df = load_metric(run_dir, name)
        rows[model] = df.iloc[-1].to_dict() if not df.empty else {}
    table = pd.DataFrame(rows).T
    return table


# ----------------------------------
# Benchmarks (require price data)
# ----------------------------------

def _close_series(ticker: str, start, end) -> pd.Series:
    hist = market_data.download_data_on_given_range(ticker, start, end)
    s = hist["Close"].copy()
    s.index = pd.to_datetime(s.index)
    return s.sort_index()


def benchmark_spy(start, end, starting_cash: float) -> pd.DataFrame:
    """SPY buy-and-hold, normalized to ``starting_cash`` at ``start``."""
    s = _close_series("SPY", start, end)
    value = s / s.iloc[0] * starting_cash
    return pd.DataFrame({"date": value.index, "equity": value.to_numpy()})


def benchmark_equal_weight(universe, start, end, starting_cash: float) -> pd.DataFrame:
    """Equal-weight buy-and-hold of the universe, normalized to ``starting_cash``."""
    normalized = []
    for ticker in sorted(universe):
        try:
            s = _close_series(ticker, start, end)
            normalized.append(s / s.iloc[0])
        except Exception:
            continue  # skip a ticker with no data rather than fail the whole benchmark
    if not normalized:
        return pd.DataFrame(columns=["date", "equity"])
    matrix = pd.concat(normalized, axis=1)
    equal_weight = matrix.mean(axis=1) * starting_cash
    return pd.DataFrame({"date": equal_weight.index, "equity": equal_weight.to_numpy()})
