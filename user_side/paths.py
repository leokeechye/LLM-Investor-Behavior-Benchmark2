"""Run-state locations.

All run state lives under ``LIBB_DATA_DIR`` (default ``user_side/runs`` locally;
set to the Railway volume mount ``/data`` in production). Centralizing this here
lets the workflows, replay engine, and dashboard all agree on where runs live.
"""
import os
from pathlib import Path

DATA_DIR = Path(os.environ.get("LIBB_DATA_DIR", "user_side/runs"))

LIVE_ROOT = str(DATA_DIR / "run_v1")   # forward-only live daily/weekly runs
REPLAY_ROOT = str(DATA_DIR / "replay")  # historical replay runs
