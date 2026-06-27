"""In-container nightly scheduler for ingest + transcribe.

Railway volumes attach to exactly one service, so a separate cron *service* can't
share the web app's volume. Instead we run the schedule inside the same container
(launched in the background by `start.sh`), writing to the same mounted volume the
dashboard reads from. Single source of truth, no volume sharing required.

It runs the deterministic ETL only — `python -m pipeline.run_ingest --incremental`
(HubSpot pull + Whisper transcription). The agentic analysis (Claude) stays
operator-triggered from the dashboard; extend `_job()` if you later want it on a
schedule too.

Controlled by env vars:
  SCHEDULE_INGEST=1            enable the loop (default: off)
  SCHEDULE_HOUR_UTC=6         hour-of-day to run, UTC (default: 6)
  SCHEDULE_MINUTE_UTC=0       minute-of-hour to run, UTC (default: 0)
  SCHEDULE_RUN_ON_BOOT=0      also run once at startup (default: off)
  STT_BACKEND=openai          transcription backend the job uses (default: openai)

Idempotent + resumable like the underlying pipeline, so a missed or repeated run
only does new work.
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

log = logging.getLogger("scheduler")

REPO_ROOT = Path(__file__).resolve().parents[1]
RUN_DIR = Path(os.environ.get("DATA_DIR", str(REPO_ROOT / "data"))) / "ui_runs"


def _enabled() -> bool:
    return os.environ.get("SCHEDULE_INGEST", "").lower() in ("1", "true", "yes", "on")


def _seconds_until_next(now: datetime) -> tuple[float, datetime]:
    hour = int(os.environ.get("SCHEDULE_HOUR_UTC", "6"))
    minute = int(os.environ.get("SCHEDULE_MINUTE_UTC", "0"))
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds(), target


def _job() -> None:
    """Run one incremental ingest + transcribe, logging to the same place the
    dashboard's run panels tail from."""
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    log_path = RUN_DIR / f"scheduler-{stamp}.log"
    backend = os.environ.get("STT_BACKEND", "openai")
    cmd = [sys.executable, "-m", "pipeline.run_ingest", "--incremental",
           "--backend", backend]
    log.info("running scheduled ingest: %s", " ".join(cmd))
    with open(log_path, "w") as logf:
        logf.write(f"$ {' '.join(cmd)}\n\n")
        logf.flush()
        rc = subprocess.run(cmd, cwd=str(REPO_ROOT), stdout=logf,
                            stderr=subprocess.STDOUT).returncode
    log.info("scheduled ingest finished rc=%s (log: %s)", rc, log_path)


def main() -> None:
    logging.basicConfig(level=logging.INFO,
                        format="%(levelname)s %(name)s: %(message)s")
    if not _enabled():
        log.info("SCHEDULE_INGEST not set — scheduler idle (manual runs only).")
        return

    if os.environ.get("SCHEDULE_RUN_ON_BOOT", "").lower() in ("1", "true", "yes", "on"):
        try:
            _job()
        except Exception as e:  # never let a bad run kill the loop
            log.exception("run-on-boot ingest failed: %s", e)

    while True:
        now = datetime.now(timezone.utc)
        wait_s, target = _seconds_until_next(now)
        log.info("next scheduled ingest at %s UTC (in %.0f min)",
                 target.isoformat(), wait_s / 60)
        # sleep in bounded slices so SIGTERM is handled promptly on redeploy
        while wait_s > 0:
            time.sleep(min(wait_s, 300))
            wait_s = _seconds_until_next(datetime.now(timezone.utc))[0] \
                if (datetime.now(timezone.utc) < target) else 0
        try:
            _job()
        except Exception as e:
            log.exception("scheduled ingest failed: %s", e)
        # guard against a fast loop if the job returns instantly
        time.sleep(60)


if __name__ == "__main__":
    main()
