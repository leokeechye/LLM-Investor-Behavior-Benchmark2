"""Historical replay engine.

For each NYSE trading session ``t`` in a date range, this drives one model
through LIBB's normal daily loop but with a **point-in-time, price-history-only**
prompt (no news — see CLAUDE.md). Orders are dated the next trading session, so
they fill at that session's open on the following iteration, reusing LIBB's
existing fill logic and run-dir layout unchanged.

Replay is a teaching demo: any period is allowed, but a period overlapping a
model's training cutoff is flagged (results there reflect memorization, not
forecasting skill). Model calls go through ``generate_fn`` (injectable — the
default hits the provider registry; tests pass canned outputs for determinism).
"""
from __future__ import annotations

import shutil
from datetime import date
from pathlib import Path

import pandas as pd

import libb.execution.get_market_data as market_data
from libb import LIBBmodel
from libb.execution.utils import nyse
from libb.other.parse import parse_json

from .universe import enforce_universe, load_universe
from .providers.registry import generate as registry_generate, get_spec
from .prompts.replay_prompt import create_replay_prompt
from .paths import REPLAY_ROOT

DEFAULT_RUN_ROOT = REPLAY_ROOT


# ----------------------------------
# Trading-calendar helpers
# ----------------------------------

def trading_sessions(start: str | date, end: str | date) -> list[date]:
    """NYSE session dates in [start, end], inclusive."""
    schedule = nyse.schedule(start_date=start, end_date=end)
    return [ts.date() for ts in schedule.index]


def next_trading_day(day: str | date) -> date:
    """The first NYSE session strictly after ``day``."""
    day = pd.Timestamp(day)
    schedule = nyse.schedule(
        start_date=(day + pd.Timedelta(days=1)).date(),
        end_date=(day + pd.Timedelta(days=10)).date(),
    )
    if schedule.empty:
        raise RuntimeError(f"No NYSE session found within 10 days after {day.date()}")
    return schedule.index[0].date()


# ----------------------------------
# Point-in-time price history
# ----------------------------------

def build_price_history_text(tickers, end_date: str | date, lookback: int = 30) -> str:
    """Compact OHLC/close history per ticker, up to and including ``end_date``.

    Only data on or before ``end_date`` is fetched, so the prompt cannot leak
    the future. A ticker whose data is unavailable is noted, not dropped.
    """
    window_start = (pd.Timestamp(end_date) - pd.Timedelta(days=lookback * 2 + 10)).date()
    lines: list[str] = []
    for ticker in sorted(tickers):
        try:
            hist = market_data.download_data_on_given_range(ticker, window_start, end_date)
        except Exception as e:  # one bad ticker shouldn't abort the day
            lines.append(f"{ticker}: (price data unavailable: {e})")
            continue

        closes = hist["Close"].tail(lookback)
        if closes.empty:
            lines.append(f"{ticker}: (no price data through {end_date})")
            continue

        last = closes.index[-1]
        o = hist["Open"].loc[last]
        h = hist["High"].loc[last]
        low = hist["Low"].loc[last]
        c = hist["Close"].loc[last]
        close_list = ", ".join(f"{v:.2f}" for v in closes.to_list())
        lines.append(
            f"{ticker}: latest {pd.Timestamp(last).date()} "
            f"O={o:.2f} H={h:.2f} L={low:.2f} C={c:.2f}\n"
            f"  closes[{len(closes)}]: {close_list}"
        )
    return "\n".join(lines)


# ----------------------------------
# Lookahead-bias flag
# ----------------------------------

def overlaps_training_cutoff(model: str, start: date, end: date) -> bool:
    """True if the replay period overlaps the model's training cutoff.

    (Any session on or before the cutoff reflects memorization, not forecasting.)
    """
    try:
        spec = get_spec(model)
    except KeyError:
        return False
    return spec.training_cutoff is not None and start <= spec.training_cutoff


# ----------------------------------
# Driver
# ----------------------------------

def run_replay(
    model: str,
    start: str | date,
    end: str | date,
    *,
    run_root: str = DEFAULT_RUN_ROOT,
    lookback: int = 30,
    generate_fn=None,
    config: dict | None = None,
    analyze_sentiment: bool = True,
    progress_cb=None,
    reset: bool = False,
) -> dict:
    """Replay ``model`` day-by-day over [start, end]. Returns a run summary.

    ``generate_fn(model, prompt) -> str`` defaults to the provider registry;
    inject a deterministic stub for testing. Writes to ``run_root/<model>/``.
    LIBB refuses to overwrite an existing forward ledger, so pass ``reset=True``
    to wipe that model's replay dir first (each replay is a fresh experiment) —
    otherwise a re-run or overlapping period raises a backjump error.
    ``progress_cb(done, total, day)`` is called after each session (for UIs).
    """
    generate_fn = generate_fn or registry_generate

    universe = load_universe()
    universe_str = ", ".join(sorted(universe))

    sessions = trading_sessions(start, end)
    if not sessions:
        raise ValueError(f"No NYSE trading sessions between {start} and {end}.")

    cutoff_overlap = overlaps_training_cutoff(model, sessions[0], sessions[-1])
    if cutoff_overlap:
        print(
            f"[replay][WARNING] period {sessions[0]}..{sessions[-1]} overlaps "
            f"{model}'s training cutoff — results in that region reflect "
            "memorization, not forecasting skill."
        )

    root = str(Path(run_root) / model)
    if reset and Path(root).exists():
        shutil.rmtree(root)  # fresh experiment: LIBB won't overwrite an existing ledger

    orders_filled = orders_failed = 0
    n = len(sessions)

    for i, t in enumerate(sessions):
        libb = LIBBmodel(root, run_date=t, config=config)
        libb.process_portfolio()  # fills orders dated t (from the previous session)
        orders_filled += libb.filled_orders
        orders_failed += libb.failed_orders

        nxt = next_trading_day(t)
        price_text = build_price_history_text(universe, t, lookback)
        prompt = create_replay_prompt(
            libb,
            price_history_text=price_text,
            universe_str=universe_str,
            next_trading_day=str(nxt),
        )
        libb.save_prompt(prompt)

        report = generate_fn(model, prompt)
        if analyze_sentiment:
            libb.analyze_sentiment(report, report_type="Replay")
        libb.save_daily_update(report)

        try:
            orders = parse_json(report, "ORDERS_JSON")
        except ValueError as e:
            libb.save_additional_log("replay_parse_errors", f"{t}: {e}\n", append=True)
            orders = {"orders": []}

        orders = enforce_universe(libb, orders)
        # Guarantee next-session-open fills regardless of the model's date math.
        for order in orders["orders"]:
            order["date"] = str(nxt)
        libb.save_orders(orders)

        if progress_cb is not None:
            progress_cb(i + 1, n, t)

    return {
        "model": model,
        "sessions": len(sessions),
        "start": str(sessions[0]),
        "end": str(sessions[-1]),
        "orders_filled": orders_filled,
        "orders_failed": orders_failed,
        "training_cutoff_overlap": cutoff_overlap,
        "run_dir": root,
    }


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Run a historical replay for one model.")
    parser.add_argument("--model", required=True, help="registry model name (config/models.yaml)")
    parser.add_argument("--start", required=True, help="YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="YYYY-MM-DD")
    parser.add_argument("--lookback", type=int, default=30, help="price-history sessions to show")
    parser.add_argument("--run-root", default=DEFAULT_RUN_ROOT)
    args = parser.parse_args()

    summary = run_replay(
        args.model, args.start, args.end, run_root=args.run_root, lookback=args.lookback
    )
    print(summary)


if __name__ == "__main__":
    main()
