"""Stock-universe enforcement.

Orders for tickers outside the configured universe (``config/universe.yaml``)
are rejected at order-validation time and logged to the run's trade_log with
status ``REJECTED`` — never silently dropped (see CLAUDE.md architecture
decisions). The same universe is the basis for the equal-weight benchmark.

Enforcement lives here (``user_side``) rather than in ``libb`` core so the fork
stays mergeable. The workflow calls ``enforce_universe`` on parsed orders just
before ``libb.save_orders``; only in-universe orders are persisted as pending.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

from libb.other.types_file import Order, OrderPaylaod
from libb.execution.utils import append_log, order_to_trade_schema

# repo_root/config/universe.yaml  (this file: repo_root/user_side/universe.py)
DEFAULT_UNIVERSE_PATH = Path(__file__).resolve().parents[1] / "config" / "universe.yaml"


@lru_cache(maxsize=None)
def load_universe(path: str | Path | None = None) -> frozenset[str]:
    """Load the allowed-ticker set from YAML (uppercased). Cached per path."""
    universe_path = Path(path) if path else DEFAULT_UNIVERSE_PATH
    if not universe_path.exists():
        raise FileNotFoundError(f"Universe config not found at {universe_path}")

    raw = yaml.safe_load(universe_path.read_text(encoding="utf-8")) or {}
    tickers = raw.get("universe", [])
    if not tickers:
        raise ValueError(f"Universe config at {universe_path} has no 'universe' entries.")
    return frozenset(str(t).strip().upper() for t in tickers)


def _ticker_of(order: Order) -> str:
    return str(order.get("ticker") or "").strip().upper()


def enforce_universe(
    libb,
    payload: OrderPaylaod,
    *,
    universe: frozenset[str] | None = None,
    universe_path: str | Path | None = None,
) -> OrderPaylaod:
    """Return a payload containing only in-universe orders.

    Each out-of-universe order is logged to ``libb.layout.trade_log_path`` with
    status ``REJECTED`` and dropped from the returned payload. In-universe order
    tickers are normalized to uppercase. Accepts an explicit ``universe`` set
    (mainly for tests); otherwise loads from ``universe_path`` / the default.
    """
    if universe is None:
        universe = load_universe(universe_path)

    orders = payload.get("orders", []) if payload else []
    accepted: list[Order] = []
    for order in orders:
        ticker = _ticker_of(order)
        if ticker in universe:
            order["ticker"] = ticker  # normalize
            accepted.append(order)
        else:
            reason = f"TICKER OUTSIDE UNIVERSE: {ticker or '(missing)'}"
            trade_dict = order_to_trade_schema(
                order, executed_price=None, PnL=None, status="REJECTED", reason=reason
            )
            append_log(libb.layout.trade_log_path, trade_dict)
    return OrderPaylaod(orders=accepted)
