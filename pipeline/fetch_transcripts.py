"""Deterministic transcript + recording retrieval for ingested calls.

Strategy (flag, never fail):
  1. If the call has a transcription_id, try the HubSpot calling-extensions
     transcript API. On success, store clean speaker-attributed text -> status
     'present', source 'api'.
  2. On 4xx (404 not served / 403 missing scope), the API path is unavailable.
     If --download-recordings is set, stream the .mp4 recording to disk so a
     later STT pass can transcribe it; mark status 'missing' (no text yet) but
     record the recording path.
  3. Calls with neither transcript nor recording -> 'missing'.

The transcript API requires the private app scope
`crm.extensions_calling_transcripts.read`. If every call 404s, that scope is
almost certainly absent (or these HUBSPOT_MEETINGS bot transcripts aren't served
by that API), and the recording -> STT fallback is the path forward.

Recordings can be large (45-min meeting videos), so download is opt-in.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from dotenv import load_dotenv

from .hubspot_client import HubSpotClient, HubSpotError
from . import store

load_dotenv()
log = logging.getLogger("transcripts")

DATA_DIR = Path(os.environ.get("DATA_DIR", "./data")).resolve()
TRANSCRIPT_DIR = DATA_DIR / "transcripts"
RECORDING_DIR = DATA_DIR / "recordings"


def _normalize_transcript(payload: dict) -> dict:
    """Flatten the calling-extensions transcript payload into a clean,
    speaker-attributed turn list. Shape is defensive — HubSpot has returned a
    few variants. Raw payload is preserved alongside."""
    turns = []
    # Common shapes: {"results":[{"speakerId","text","startTime"}...]} or
    # {"transcript":{"sentences":[...]}}.
    candidates = (payload.get("results") or payload.get("sentences")
                  or (payload.get("transcript") or {}).get("sentences") or [])
    for seg in candidates:
        if not isinstance(seg, dict):
            continue
        turns.append({
            "speaker": seg.get("speakerId") or seg.get("speaker") or seg.get("actor"),
            "text": seg.get("text") or seg.get("transcript") or seg.get("content"),
            "start_ms": seg.get("startTime") or seg.get("start") or seg.get("timeOffset"),
            "end_ms": seg.get("endTime") or seg.get("end"),
        })
    return {"turns": turns, "n_turns": len(turns), "raw": payload}


def fetch(download_recordings: bool = False, only_pending: bool = True) -> dict:
    client = HubSpotClient()
    summary = {"checked": 0, "api_present": 0, "api_failed": 0,
               "recordings_downloaded": 0, "missing": 0, "errors": []}

    with store.connect() as conn:
        where = "WHERE transcript_status='pending'" if only_pending else ""
        rows = conn.execute(
            f"SELECT call_id, transcription_id, recording_url FROM calls {where}"
        ).fetchall()

    for row in rows:
        call_id = row["call_id"]
        tid = row["transcription_id"]
        rec_url = row["recording_url"]
        summary["checked"] += 1
        got_text = False

        if tid:
            try:
                payload = client.get_transcript(tid)
                norm = _normalize_transcript(payload)
                TRANSCRIPT_DIR.mkdir(parents=True, exist_ok=True)
                tpath = TRANSCRIPT_DIR / f"{call_id}.json"
                tpath.write_text(json.dumps(norm, default=str, indent=2))
                with store.connect() as conn:
                    store.set_call_transcript_state(
                        conn, call_id, status="present", source="api",
                        transcript_path=str(tpath))
                summary["api_present"] += 1
                got_text = True
            except HubSpotError as e:
                summary["api_failed"] += 1
                summary["errors"].append(f"{call_id}: {str(e)[:80]}")

        rec_path = None
        if not got_text and download_recordings and rec_url:
            try:
                dest = RECORDING_DIR / f"{call_id}.mp4"
                n = client.download(rec_url, dest)
                rec_path = str(dest)
                summary["recordings_downloaded"] += 1
                log.info("downloaded %s (%d bytes)", call_id, n)
            except HubSpotError as e:
                summary["errors"].append(f"{call_id} recording: {str(e)[:80]}")

        if not got_text:
            summary["missing"] += 1
            with store.connect() as conn:
                store.set_call_transcript_state(
                    conn, call_id,
                    status="missing",
                    source="none" if not rec_path else "stt_pending",
                    recording_path=rec_path)

    return summary


if __name__ == "__main__":
    import argparse
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--download-recordings", action="store_true",
                    help="stream .mp4 recordings to disk for STT fallback")
    ap.add_argument("--all", action="store_true",
                    help="re-check all calls, not just pending")
    a = ap.parse_args()
    s = fetch(download_recordings=a.download_recordings, only_pending=not a.all)
    print(json.dumps(s, indent=2, default=str))
