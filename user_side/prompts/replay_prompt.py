"""Price-history-only prompt for historical replay.

Replay is a point-in-time teaching demo: on simulated day ``t`` the model may
see ONLY price history up to and including ``t`` — no news feeds (those are
current-day only and would leak the future). See CLAUDE.md architecture
decisions. The output format matches the live prompts so ``parse_json`` +
``enforce_universe`` + ``save_orders`` work unchanged.
"""
from libb.model import LIBBmodel


SYSTEM_HEADER = """System Message

You are a portfolio manager in HISTORICAL REPLAY mode. Today is {today}. You may
reason ONLY about the price history and portfolio state provided below — you have
no news, and you must not use any knowledge of events after {today}. Do not
reference or assume anything that happened after {today}.
"""


CAPITAL_RULE = """
---------------------------------------------------------------------------
CAPITAL RULE (HARD)
---------------------------------------------------------------------------
Use the live portfolio state provided (cash, positions, cost basis, stops, pnl)
as the sole source of truth. Do NOT reset or assume any starting capital.
Full shares only. Long-only: no options, shorting, leverage, or margin.
"""


UNIVERSE_SECTION = """
---------------------------------------------------------------------------
ALLOWED UNIVERSE (HARD)
---------------------------------------------------------------------------
You may ONLY place orders for these tickers. An order for any ticker not in this
list will be REJECTED and logged — it will NOT execute:

[{tickers}]
"""


PORTFOLIO_SECTION = """
---------------------------------------------------------------------------
CURRENT PORTFOLIO (as of {today})
---------------------------------------------------------------------------
[{portfolio_text}]
"""


PRICE_HISTORY_SECTION = """
---------------------------------------------------------------------------
PRICE HISTORY (point-in-time, through {today}; most recent last)
---------------------------------------------------------------------------
{price_history_text}
"""


LOGS_SECTION = """
---------------------------------------------------------------------------
RECENT EXECUTION LOG
---------------------------------------------------------------------------
{logs_text}
"""


OBJECTIVES = """
---------------------------------------------------------------------------
OBJECTIVES
---------------------------------------------------------------------------
- Evaluate price action and your current exposure, concentration, and liquidity.
- Decide whether to hold, trim, add, exit, or initiate.
- Every long position must have a stop-loss.
- Limit prices must be within ±10% of the last close unless justified.
- All orders are LIMIT DAY orders, full shares only.
- Execution date is the next trading session: {next_trading_day}.
- If no trade is justified, return an empty orders array.
"""


OUTPUT_TEMPLATE = """
---------------------------------------------------------------------------
OUTPUT FORMAT (STRICT)
---------------------------------------------------------------------------
Output exactly three blocks:

<ANALYSIS>
...your point-in-time reasoning...
</ANALYSIS>

<ORDERS_JSON>
{{
  "orders": [
    {{
      "action": "b" | "s" | "u",
      "ticker": "XYZ",
      "shares": 1,
      "order_type": "LIMIT",
      "limit_price": 10.25,
      "time_in_force": "DAY",
      "date": "{next_trading_day}",
      "stop_loss": 8.90,
      "rationale": "short justification",
      "confidence": 0.80
    }}
  ]
}}
</ORDERS_JSON>

<CONFIDENCE_LVL>
0.65
</CONFIDENCE_LVL>

The JSON must be pure and contain no comments. Use an empty "orders" list if not trading.
"""


def create_replay_prompt(
    libb: LIBBmodel,
    *,
    price_history_text: str,
    universe_str: str,
    next_trading_day: str,
) -> str:
    """Assemble the point-in-time replay prompt for the model's run_date."""
    today = str(libb.run_date)

    portfolio = libb.portfolio
    portfolio_text = (
        portfolio.to_string(index=False)
        if not portfolio.empty
        else (
            "You have 0 active positions and must make at least one trade to "
            f"build a portfolio. Starting cash: {libb.STARTING_CASH}"
        )
    )

    logs = libb.recent_execution_logs()
    logs_text = (
        logs.to_string(index=False)
        if not isinstance(logs, str) and not logs.empty
        else "No recent trade logs."
    )

    return (
        SYSTEM_HEADER.format(today=today)
        + CAPITAL_RULE
        + UNIVERSE_SECTION.format(tickers=universe_str)
        + PORTFOLIO_SECTION.format(today=today, portfolio_text=portfolio_text)
        + PRICE_HISTORY_SECTION.format(today=today, price_history_text=price_history_text)
        + LOGS_SECTION.format(logs_text=logs_text)
        + OBJECTIVES.format(next_trading_day=next_trading_day)
        + OUTPUT_TEMPLATE.format(next_trading_day=next_trading_day)
    )
