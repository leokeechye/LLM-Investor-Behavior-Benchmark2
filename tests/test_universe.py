"""Tests for stock-universe enforcement (user_side/universe.py)."""
import pandas as pd
import pytest

from libb import LIBBmodel
from user_side.universe import enforce_universe, load_universe


def _order(ticker, action="b"):
    """A fully-populated order matching the Order schema."""
    return {
        "action": action,
        "ticker": ticker,
        "shares": 1,
        "order_type": "LIMIT",
        "limit_price": 10.0,
        "time_in_force": "DAY",
        "date": "2026-01-05",
        "stop_loss": 9.0,
        "rationale": "test",
        "confidence": 0.5,
    }


def test_load_universe_uppercases(tmp_path):
    p = tmp_path / "u.yaml"
    p.write_text("universe:\n  - aapl\n  - Msft\n")
    assert load_universe(p) == frozenset({"AAPL", "MSFT"})


def test_load_universe_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_universe(tmp_path / "does_not_exist.yaml")


def test_load_universe_empty(tmp_path):
    p = tmp_path / "empty.yaml"
    p.write_text("universe: []\n")
    with pytest.raises(ValueError):
        load_universe(p)


def test_enforce_keeps_in_universe_rejects_others(tmp_path):
    libb = LIBBmodel(tmp_path / "run")
    universe = frozenset({"AAPL", "MSFT"})
    payload = {
        "orders": [
            _order("aapl"),   # in-universe (lowercase) -> accepted + normalized
            _order("TSLA"),   # out-of-universe        -> rejected + logged
            _order(""),       # missing ticker         -> rejected + logged
        ]
    }

    result = enforce_universe(libb, payload, universe=universe)

    # Only the in-universe order survives, normalized to uppercase.
    assert [o["ticker"] for o in result["orders"]] == ["AAPL"]

    # Rejected orders are LOGGED (never silently dropped) with status REJECTED.
    log = pd.read_csv(libb.layout.trade_log_path)
    rejected = log[log["status"] == "REJECTED"]
    assert len(rejected) == 2
    assert set(rejected["reason"]) == {
        "TICKER OUTSIDE UNIVERSE: TSLA",
        "TICKER OUTSIDE UNIVERSE: (missing)",
    }


def test_enforce_empty_payload(tmp_path):
    libb = LIBBmodel(tmp_path / "run")
    result = enforce_universe(libb, {"orders": []}, universe=frozenset({"AAPL"}))
    assert result == {"orders": []}
    # nothing logged
    assert pd.read_csv(libb.layout.trade_log_path).empty


def test_enforce_uses_default_config_universe(tmp_path):
    """With no explicit set, enforcement loads the shipped config/universe.yaml."""
    libb = LIBBmodel(tmp_path / "run")
    payload = {"orders": [_order("AAPL"), _order("ZZZZ")]}
    result = enforce_universe(libb, payload)  # loads config/universe.yaml
    assert [o["ticker"] for o in result["orders"]] == ["AAPL"]
