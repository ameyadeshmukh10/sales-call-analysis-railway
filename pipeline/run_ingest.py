"""End-to-end deterministic pipeline runner.

  1. ingest_calls   — pull the recorded_calls view + associations into SQLite
  2. transcribe     — local STT of each recording into a normalized transcript
                      (HubSpot doesn't serve these meeting-bot transcripts via API)

Both steps are idempotent and incremental, so this is safe to schedule/re-run.
The analysis layer reads from the SQLite store this populates.

Usage:
  python -m pipeline.run_ingest                  # ingest + transcribe the window
  python -m pipeline.run_ingest --no-transcribe  # just ingest (fast)
  python -m pipeline.run_ingest --incremental    # only records changed since last run
"""
from __future__ import annotations

import argparse
import json
import logging

from . import ingest_calls, transcribe


def main() -> None:
    logging.basicConfig(level=logging.INFO,
                        format="%(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--start"); ap.add_argument("--end")
    ap.add_argument("--incremental", action="store_true")
    ap.add_argument("--no-transcribe", action="store_true")
    ap.add_argument("--keep-recordings", action="store_true")
    ap.add_argument("--backend", default=transcribe.DEFAULT_BACKEND,
                    choices=["mlx", "openai", "groq"])
    ap.add_argument("--model", default=None)
    a = ap.parse_args()

    log = logging.getLogger("run_ingest")
    log.info("STEP 1/2 — ingesting calls + associations")
    ing = ingest_calls.ingest(a.start, a.end, incremental=a.incremental)
    log.info("ingest summary: %s", json.dumps(ing, default=str))

    if a.no_transcribe:
        log.info("skipping transcription (--no-transcribe)")
        print(json.dumps({"ingest": ing}, indent=2, default=str))
        return

    log.info("STEP 2/2 — transcribing recordings (backend=%s)", a.backend)
    tr = transcribe.run(backend=a.backend, model=a.model,
                        keep_recordings=a.keep_recordings)
    tr.pop("details", None)
    log.info("transcribe summary: %s", json.dumps(tr, default=str))
    print(json.dumps({"ingest": ing, "transcribe": tr}, indent=2, default=str))


if __name__ == "__main__":
    main()
