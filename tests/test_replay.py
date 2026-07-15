"""Tests for the historical replay engine (user_side/replay.py).

Market data is stubbed to constant prices so the tests are network-free and
deterministic. Patching ``download_data_on_given_range`` at its source covers
both LIBB's fill path (``download_data_on_given_date`` resolves the range fn via
module globals) and the replay engine's own price fetch.
"""
from datetime import date

import pandas as pd
import pytest

from user_side import replay


# Canned model output: always buy 1 share of AAPL (an in-universe ticker).
# The order's own date is overwritten by the engine to the next session.
CANNED_REPORT = """<ANALYSIS>deterministic test</ANALYSIS>
<ORDERS_JSON>
{"orders": [{"action": "b", "ticker": "AAPL", "shares": 1, "order_type": "LIMIT",
"limit_price": 10.5, "time_in_force": "DAY", "date": "2000-01-01",
"stop_loss": 8.0, "rationale": "t", "confidence": 0.5}]}
</ORDERS_JSON>
<CONFIDENCE_LVL>0.5</CONFIDENCE_LVL>"""


def _canned_generate(model, prompt):
    return CANNED_REPORT


def _fake_range(ticker, start, end):
    """Constant OHLCV over business days in [start, end]."""
    idx = pd.bdate_range(start=start, end=end)
    if len(idx) == 0:
        idx = pd.DatetimeIndex([pd.Timestamp(end)])
    n = len(idx)
    s = lambda v: pd.Series([v] * n, index=idx)
    return {
        "Low": s(9.0), "High": s(11.0), "Close": s(10.0), "Open": s(10.0),
        "Volume": s(1000), "Ticker": ticker, "start_date": str(start), "end_date": str(end),
    }


@pytest.fixture
def stub_market(monkeypatch):
    monkeypatch.setattr(
        "libb.execution.get_market_data.download_data_on_given_range", _fake_range
    )


# --- calendar helpers -------------------------------------------------------

def test_trading_sessions_excludes_weekend():
    # 2024-02-05 (Mon) .. 2024-02-11 (Sun) -> Mon..Fri only
    sessions = replay.trading_sessions("2024-02-05", "2024-02-11")
    assert sessions == [date(2024, 2, d) for d in (5, 6, 7, 8, 9)]


def test_next_trading_day_skips_weekend():
    assert replay.next_trading_day("2024-02-09") == date(2024, 2, 12)  # Fri -> Mon


# --- point-in-time price history -------------------------------------------

def test_price_history_never_reads_the_future(stub_market, monkeypatch):
    seen_ends = []
    orig = replay.market_data.download_data_on_given_range

    def spy(ticker, start, end):
        seen_ends.append(pd.Timestamp(end).date())
        return orig(ticker, start, end)

    monkeypatch.setattr("libb.execution.get_market_data.download_data_on_given_range", spy)

    t = date(2024, 2, 9)
    text = replay.build_price_history_text(["AAPL", "MSFT"], t, lookback=10)
    assert "AAPL" in text and "MSFT" in text
    assert seen_ends and all(e <= t for e in seen_ends)  # no lookahead


# --- determinism ------------------------------------------------------------

def test_replay_is_deterministic(stub_market, tmp_path):
    kwargs = dict(
        start="2024-02-05", end="2024-02-09",
        generate_fn=_canned_generate, lookback=10, analyze_sentiment=False,
    )
    s1 = replay.run_replay("gpt-4.1", run_root=str(tmp_path / "a"), **kwargs)
    s2 = replay.run_replay("gpt-4.1", run_root=str(tmp_path / "b"), **kwargs)

    assert s1["sessions"] == 5
    assert s1["orders_filled"] > 0  # the loop actually traded

    for fname in ("portfolio/trade_log.csv", "portfolio/portfolio_history.csv"):
        a = (tmp_path / "a" / "gpt-4.1" / fname).read_text()
        b = (tmp_path / "b" / "gpt-4.1" / fname).read_text()
        assert a == b, f"{fname} differs between identical replays"
        assert "FILLED" in (tmp_path / "a" / "gpt-4.1" / "portfolio/trade_log.csv").read_text()


def test_replay_reset_allows_rerun(stub_market, tmp_path):
    kw = dict(
        generate_fn=_canned_generate, lookback=5, analyze_sentiment=False,
        run_root=str(tmp_path / "r"),
    )
    replay.run_replay("gpt-4.1", "2024-02-05", "2024-02-09", **kw)

    # Re-running an overlapping period without reset hits LIBB's forward-only guard.
    with pytest.raises(RuntimeError):
        replay.run_replay("gpt-4.1", "2024-02-05", "2024-02-07", **kw)

    # reset=True wipes the run dir first, so the re-run starts fresh and succeeds.
    summary = replay.run_replay("gpt-4.1", "2024-02-05", "2024-02-07", reset=True, **kw)
    assert summary["sessions"] == 3
