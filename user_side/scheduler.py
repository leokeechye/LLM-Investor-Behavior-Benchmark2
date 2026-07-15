"""In-process live-trading scheduler.

Runs the live daily/weekly flow on a cron schedule (weekdays 22:00 UTC — safely
after the US market close in both EST and EDT). The job is idempotent: if today's
session is already finalized for every model, it is skipped, so a process restart
or a misfire re-fire won't double-run.
"""
from pathlib import Path

import pandas as pd

from libb.execution.utils import is_nyse_open
from libb.other.types_file import DiskLayout

from .paths import LIVE_ROOT
from .workflow import MODELS, daily_flow, weekly_flow


def _is_finalized(model: str, day) -> bool:
    """True if ``day`` already appears in this model's portfolio history."""
    path = DiskLayout.from_root(Path(f"{LIVE_ROOT}/{model}")).portfolio_history_path
    if not path.exists():
        return False
    df = pd.read_csv(path)
    return not df.empty and str(day) in set(df["date"].astype(str))


def run_live_once(day=None) -> None:
    """Run one live session for ``day`` (default: today), idempotently.

    Friday runs the weekly deep-research flow; Mon–Thu run the daily flow; the
    NYSE calendar and per-model finalization guard skip closed/already-done days.
    """
    day = pd.Timestamp(day).date() if day is not None else pd.Timestamp.now().date()

    if not is_nyse_open(day):
        print(f"[scheduler] {day}: NYSE closed — skipping.")
        return
    if all(_is_finalized(m, day) for m in MODELS):
        print(f"[scheduler] {day}: already finalized — skipping.")
        return

    if day.weekday() == 4:  # Friday
        print(f"[scheduler] {day}: running weekly flow…")
        weekly_flow(day)
    else:
        print(f"[scheduler] {day}: running daily flow…")
        daily_flow(day)
    print(f"[scheduler] {day}: done.")


def start_scheduler():
    """Start (and return) a background scheduler running the live loop.

    Weekdays at 22:00 UTC. ``misfire_grace_time`` + ``coalesce`` mean a missed
    fire (e.g. during a deploy) runs once when the process comes back, rather
    than piling up.
    """
    from apscheduler.schedulers.background import BackgroundScheduler

    scheduler = BackgroundScheduler(timezone="UTC")
    scheduler.add_job(
        run_live_once,
        trigger="cron",
        day_of_week="mon-fri",
        hour=22,
        minute=0,
        id="live_daily",
        misfire_grace_time=3600,
        coalesce=True,
        max_instances=1,
    )
    scheduler.start()
    print("[scheduler] started: live loop weekdays 22:00 UTC")
    return scheduler
