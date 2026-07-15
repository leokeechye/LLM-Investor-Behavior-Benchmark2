"""Dashboard smoke test.

Generates a deterministic (stubbed-price, no-network) replay so the dashboard
has data, then runs the Streamlit script via AppTest and asserts it renders
without an exception — exercising the equity chart, the in-training band, and
the metric tables. Uses Streamlit's headless AppTest harness (no browser).
"""
import shutil
from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from user_side.replay import run_replay

DEMO_MODEL = "gpt-4.1"  # in the registry, so the cutoff chip + overlap band render
REPLAY_ROOT = Path("user_side/runs/replay")

CANNED_REPORT = """<ANALYSIS>demo</ANALYSIS>
<ORDERS_JSON>
{"orders": [{"action": "b", "ticker": "AAPL", "shares": 1, "order_type": "LIMIT",
"limit_price": 999.0, "time_in_force": "DAY", "date": "2000-01-01",
"stop_loss": 1.0, "rationale": "t", "confidence": 0.5}]}
</ORDERS_JSON>
<CONFIDENCE_LVL>0.5</CONFIDENCE_LVL>"""


def _fake_range(ticker, start, end):
    """Deterministic gentle uptrend per ticker (varies so the curve isn't flat)."""
    idx = pd.bdate_range(start=start, end=end)
    if len(idx) == 0:
        idx = pd.DatetimeIndex([pd.Timestamp(end)])
    base = 10 + (sum(ord(c) for c in ticker) % 5)
    closes = [round(base + 0.1 * i, 2) for i in range(len(idx))]
    ser = lambda vals: pd.Series(vals, index=idx)
    close = ser(closes)
    return {
        "Low": ser([c - 0.5 for c in closes]), "High": ser([c + 0.5 for c in closes]),
        "Close": close, "Open": close.copy(), "Volume": ser([1000] * len(idx)),
        "Ticker": ticker, "start_date": str(start), "end_date": str(end),
    }


@pytest.fixture
def demo_replay(monkeypatch):
    monkeypatch.setattr("libb.execution.get_market_data.download_data_on_given_range", _fake_range)
    demo_dir = REPLAY_ROOT / DEMO_MODEL
    if demo_dir.exists():
        shutil.rmtree(demo_dir)
    run_replay(
        DEMO_MODEL, "2024-02-05", "2024-02-16",
        generate_fn=lambda m, p: CANNED_REPORT, lookback=5, analyze_sentiment=False,
    )
    yield
    if demo_dir.exists():
        shutil.rmtree(demo_dir)


def test_dashboard_runs_without_error(demo_replay):
    at = AppTest.from_file("app/streamlit_app.py", default_timeout=60).run()
    assert not at.exception  # Live mode (no data) stops cleanly

    at.radio[0].set_value("Replay").run()  # switch to the run we just generated
    assert not at.exception
    # the in-training warning banner should appear (2024-02 is before gpt-4.1's cutoff)
    assert any("In-training period" in w.value for w in at.warning)
