"""Container entrypoint: the live scheduler + the Streamlit dashboard, one service.

Railway runs this as the container command. It starts the APScheduler live loop in
this process, then launches Streamlit as a child bound to ``$PORT``.

Why not embed the scheduler inside the Streamlit script? Streamlit only executes
its script when a browser session connects, so an embedded scheduler would never
fire unattended. Running it in this parent process makes the daily job independent
of web traffic. This is still a single Railway service (one container, one mounted
volume) — it just contains two processes.

Env:
  PORT               port Streamlit binds (Railway sets this; default 8501)
  ENABLE_SCHEDULER   "1" (default) to run the live loop; "0" to serve UI only
  LIBB_DATA_DIR      run-state root (set to the volume mount, e.g. /data)
"""
import os
import subprocess
import sys


def main() -> None:
    scheduler = None
    if os.environ.get("ENABLE_SCHEDULER", "1") == "1":
        from user_side.scheduler import start_scheduler

        scheduler = start_scheduler()

    port = os.environ.get("PORT", "8501")
    cmd = [
        sys.executable, "-m", "streamlit", "run", "app/streamlit_app.py",
        "--server.port", port,
        "--server.address", "0.0.0.0",
        "--server.headless", "true",
        "--browser.gatherUsageStats", "false",
    ]
    proc = subprocess.Popen(cmd)
    try:
        raise SystemExit(proc.wait())
    finally:
        if scheduler is not None:
            scheduler.shutdown(wait=False)
        if proc.poll() is None:
            proc.terminate()


if __name__ == "__main__":
    main()
