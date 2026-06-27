"""Deterministic auto-transcription of call recordings.

HubSpot does not serve the meeting-bot transcript text via its public API (the
calling-extensions transcript endpoint 404s for these HUBSPOT_MEETINGS calls),
but the .mp4 recording IS downloadable. This module closes that gap: it
downloads each recording, extracts audio with ffmpeg, and transcribes it with
Whisper (large-v3 class). Three interchangeable backends:

  * mlx    — local, Apple-Silicon GPU via MLX. No API key, audio never leaves
             the machine. ~14x real-time on an M4. Best for laptop runs.
  * openai — hosted Whisper (`whisper-1`) over the OpenAI platform API. Audio is
             sent (in chunks) to OpenAI. Best for hosted/Linux deploys (Railway)
             where there's no GPU. Requires OPENAI_API_KEY.
  * groq   — hosted whisper-large-v3 over the Groq API. ~190x real-time, trivial
             cost. Same OpenAI-compatible request shape as the openai backend.
             Requires GROQ_API_KEY.

The hosted backends share one code path: both Groq and OpenAI expose the same
`/audio/transcriptions` multipart endpoint (verbose_json + segment timestamps),
so the only difference is the URL, the api-key env var, and the model name.

It is plain ETL, not an agent: same input -> same transcript. Output matches the
normalized shape the rest of the system expects
(data/transcripts/{call_id}.json with a `turns` list), so downstream agents
don't care whether text came from the HubSpot API, MLX, OpenAI, or Groq.

Speaker labels: Whisper yields accurate, timestamped segments but not speaker
identity. We store segments with speaker=null; the Stage-A speaker-attribution
agent assigns rep-vs-customer using the known participants (call owner + the
associated contacts), which is more reliable than blind diarization.

Idempotent + resumable: calls already 'present' are skipped unless --force, so a
long batch can be stopped and restarted freely.
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import os
import subprocess
import tempfile
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

from .hubspot_client import HubSpotClient, HubSpotError
from . import store

load_dotenv()
log = logging.getLogger("transcribe")

DATA_DIR = Path(os.environ.get("DATA_DIR", "./data")).resolve()
TRANSCRIPT_DIR = DATA_DIR / "transcripts"
RECORDING_DIR = DATA_DIR / "recordings"

DEFAULT_BACKEND = os.environ.get("STT_BACKEND", "mlx")
MLX_MODEL = os.environ.get("WHISPER_MODEL", "mlx-community/whisper-large-v3-turbo")
GROQ_MODEL = os.environ.get("GROQ_WHISPER_MODEL", "whisper-large-v3")
# OpenAI's transcription model. `whisper-1` is the only OpenAI model that returns
# segment-level timestamps (verbose_json) — which the pipeline relies on. The
# newer gpt-4o-transcribe models do NOT return segments, so don't swap them in
# here without adapting _normalize.
OPENAI_MODEL = os.environ.get("OPENAI_WHISPER_MODEL", "whisper-1")

GROQ_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
OPENAI_URL = (os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
              + "/audio/transcriptions")

# Per-backend transport: backend -> (endpoint url, api-key env var, default model).
# Groq and OpenAI are both OpenAI-compatible /audio/transcriptions endpoints.
_HOSTED = {
    "groq":   (GROQ_URL,   "GROQ_API_KEY",   GROQ_MODEL),
    "openai": (OPENAI_URL, "OPENAI_API_KEY", OPENAI_MODEL),
}

# Chunk length for the hosted backends. A 16 kHz mono FLAC chunk this long stays
# well under the 25 MB upload cap (both Groq and OpenAI) regardless of how dense
# the speech is. (GROQ_CHUNK_SECONDS kept for backwards compatibility.)
CHUNK_SECONDS = int(os.environ.get("STT_CHUNK_SECONDS",
                                   os.environ.get("GROQ_CHUNK_SECONDS", "480")))
# Hard cap on any single ffmpeg/ffprobe call so a malformed recording can't hang
# the whole (unattended) batch — a timeout flags that one call 'failed' and moves on.
FFMPEG_TIMEOUT = int(os.environ.get("FFMPEG_TIMEOUT", "1800"))


def _default_model(backend: str) -> str:
    if backend in _HOSTED:
        return _HOSTED[backend][2]
    return MLX_MODEL


# ---------------- audio extraction ---------------- #

def extract_audio(src_mp4: Path, dest_wav: Path) -> None:
    """Downmix to 16 kHz mono PCM wav (what Whisper expects)."""
    dest_wav.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["ffmpeg", "-y", "-i", str(src_mp4), "-ac", "1", "-ar", "16000",
           "-vn", str(dest_wav), "-loglevel", "error"]
    subprocess.run(cmd, check=True, timeout=FFMPEG_TIMEOUT)


def _wav_seconds(wav_path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(wav_path)],
        capture_output=True, text=True, check=True, timeout=FFMPEG_TIMEOUT)
    return float(out.stdout.strip())


# ---------------- transcription backends ---------------- #

def transcribe_audio(wav_path: Path, *, backend: str = DEFAULT_BACKEND,
                     model: str | None = None) -> dict:
    """Return a Whisper-style result dict {text, segments, language}."""
    model = model or _default_model(backend)
    if backend == "mlx":
        return _transcribe_mlx(wav_path, model)
    if backend in _HOSTED:
        url, key_env, _ = _HOSTED[backend]
        api_key = os.environ.get(key_env, "")
        if not api_key:
            raise RuntimeError(f"{key_env} env var is not set")
        return _transcribe_hosted(wav_path, model, url=url, api_key=api_key,
                                  label=backend)
    raise ValueError(f"unknown STT backend: {backend!r}")


def _transcribe_mlx(wav_path: Path, model: str) -> dict:
    import mlx_whisper  # lazy import: only needed for the local backend
    return mlx_whisper.transcribe(str(wav_path), path_or_hf_repo=model)


def _transcribe_hosted(wav_path: Path, model: str, *, url: str, api_key: str,
                       label: str) -> dict:
    """Chunk the audio and transcribe each piece via a hosted OpenAI-compatible
    Whisper endpoint (OpenAI or Groq), stitching the segment timestamps back into
    a single timeline. Stays under the 25 MB upload cap for calls of any length."""
    total = _wav_seconds(wav_path)
    n_chunks = max(1, math.ceil(total / CHUNK_SECONDS))
    all_segments: list[dict] = []
    texts: list[str] = []
    language = None
    for i in range(n_chunks):
        offset = i * CHUNK_SECONDS
        with tempfile.NamedTemporaryFile(suffix=".flac", delete=False) as tf:
            chunk = Path(tf.name)
        try:
            subprocess.run(
                ["ffmpeg", "-y", "-ss", str(offset), "-t", str(CHUNK_SECONDS),
                 "-i", str(wav_path), "-ac", "1", "-ar", "16000", "-c:a", "flac",
                 str(chunk), "-loglevel", "error"], check=True, timeout=FFMPEG_TIMEOUT)
            resp = _hosted_request(chunk, model, url=url, api_key=api_key, label=label)
            language = language or resp.get("language")
            texts.append((resp.get("text") or "").strip())
            for s in resp.get("segments", []):
                all_segments.append({
                    "start": (s.get("start", 0) or 0) + offset,
                    "end": (s.get("end", 0) or 0) + offset,
                    "text": s.get("text", ""),
                })
        finally:
            chunk.unlink(missing_ok=True)
    return {"text": " ".join(t for t in texts if t),
            "segments": all_segments, "language": language}


def _hosted_request(audio_path: Path, model: str, *, url: str, api_key: str,
                    label: str, max_retries: int = 5) -> dict:
    attempt = 0
    while True:
        attempt += 1
        with open(audio_path, "rb") as fh:
            files = {"file": (audio_path.name, fh)}
            data = {"model": model, "response_format": "verbose_json",
                    "timestamp_granularities[]": "segment"}
            try:
                r = requests.post(url, headers={"Authorization": f"Bearer {api_key}"},
                                  files=files, data=data, timeout=180)
            except requests.RequestException as e:
                if attempt >= max_retries:
                    raise RuntimeError(f"{label} network error: {e}")
                time.sleep(min(2 ** attempt, 30))
                continue
        if r.status_code == 429 and attempt < max_retries:
            ra = r.headers.get("retry-after", "10")
            try:
                wait = float(ra)
            except (TypeError, ValueError):
                wait = 10.0  # header may be an HTTP-date; just back off a bit
            time.sleep(max(1.0, wait))
            continue
        if r.status_code >= 400:
            # never echo the key; body may include rate/limit detail
            raise RuntimeError(f"{label} {r.status_code}: {r.text[:200]}")
        return r.json()


def _normalize(result: dict, *, backend: str, model: str,
               audio_seconds: float | None) -> dict:  # noqa: C901
    turns = []
    for s in result.get("segments", []):
        text = (s.get("text") or "").strip()
        if not text:
            continue
        turns.append({
            "speaker": None,  # assigned by the Stage-A attribution agent
            "text": text,
            "start_ms": int(round((s.get("start", 0) or 0) * 1000)),
            "end_ms": int(round((s.get("end", 0) or 0) * 1000)),
        })
    return {
        "turns": turns,
        "n_turns": len(turns),
        "full_text": (result.get("text") or "").strip(),
        "language": result.get("language"),
        "backend": backend,
        "model": model,
        "audio_seconds": audio_seconds,
        "diarized": False,
    }


# ---------------- per-call driver ---------------- #

def transcribe_call(conn, client: HubSpotClient, call_id: str, recording_url: str,
                    *, backend: str, model: str, keep_recording: bool) -> tuple[str, str]:
    """Returns (status, detail). Never raises for expected failures."""
    if not recording_url:
        store.set_call_transcript_state(conn, call_id, status="missing",
                                        source="none")
        return "missing", "no recording url"

    mp4 = RECORDING_DIR / f"{call_id}.mp4"
    wav = None
    try:
        if not mp4.exists() or mp4.stat().st_size == 0:
            client.download(recording_url, mp4)
        # probe duration (best-effort)
        audio_seconds = _probe_seconds(mp4)
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tf:
            wav = Path(tf.name)
        extract_audio(mp4, wav)
        result = transcribe_audio(wav, backend=backend, model=model)
        norm = _normalize(result, backend=backend, model=model,
                          audio_seconds=audio_seconds)
        if not norm["turns"]:
            # No speech/segments returned — don't mark 'present' (the selectors
            # treat that as done); flag missing so it stays re-attemptable.
            store.set_call_transcript_state(conn, call_id, status="missing",
                                            source="none")
            return "missing", "empty transcript"
        TRANSCRIPT_DIR.mkdir(parents=True, exist_ok=True)
        tpath = TRANSCRIPT_DIR / f"{call_id}.json"
        tpath.write_text(json.dumps(norm, default=str, indent=2))
        store.set_call_transcript_state(
            conn, call_id, status="present", source="stt",
            transcript_path=str(tpath),
            recording_path=str(mp4) if keep_recording else None)
        return "present", f"{norm['n_turns']} turns"
    except HubSpotError as e:
        store.set_call_transcript_state(conn, call_id, status="missing",
                                        source="none")
        return "failed", f"download: {e}"
    except subprocess.CalledProcessError as e:
        store.set_call_transcript_state(conn, call_id, status="failed",
                                        source="none")
        return "failed", f"ffmpeg: {e}"
    except Exception as e:  # transcription error — flag, don't crash batch
        store.set_call_transcript_state(conn, call_id, status="failed",
                                        source="none")
        return "failed", f"{type(e).__name__}: {e}"
    finally:
        if wav and wav.exists():
            wav.unlink(missing_ok=True)
        if not keep_recording and mp4.exists():
            mp4.unlink(missing_ok=True)  # re-downloadable via the auth-retriever URL


def _probe_seconds(mp4: Path) -> float | None:
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", str(mp4)],
            capture_output=True, text=True, check=True, timeout=FFMPEG_TIMEOUT)
        return float(out.stdout.strip())
    except Exception:
        return None


def check_backend(backend: str) -> str | None:
    """Return a human error if the backend can't run, else None. Lets the caller
    fail fast with one clear message instead of erroring on every call."""
    if backend in _HOSTED:
        _, key_env, _ = _HOSTED[backend]
        if not os.environ.get(key_env):
            return (f"{key_env} is not set. Add it to .env (e.g. "
                    f"{key_env}=sk-... ) or switch the transcription backend to "
                    "'mlx' (local, no key).")
    elif backend == "mlx":
        try:
            import mlx_whisper  # noqa: F401
        except Exception:
            return ("The 'mlx' backend needs mlx-whisper (Apple Silicon). "
                    "Run `pip install -r requirements-local-stt.txt`, or use the "
                    "'groq' backend with a GROQ_API_KEY in .env.")
    return None


def run(backend: str = DEFAULT_BACKEND, model: str | None = None,
        force: bool = False, keep_recordings: bool = False,
        limit: int | None = None) -> dict:
    model = model or _default_model(backend)
    problem = check_backend(backend)
    if problem:
        log.error(problem)
        return {"to_process": 0, "present": 0, "failed": 0, "missing": 0,
                "backend": backend, "model": model, "error": problem, "details": []}
    client = HubSpotClient()
    with store.connect() as conn:
        if force:
            rows = conn.execute(
                "SELECT call_id, recording_url FROM calls WHERE recording_url IS NOT NULL"
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT call_id, recording_url FROM calls "
                "WHERE recording_url IS NOT NULL AND transcript_status != 'present'"
            ).fetchall()
    if limit:
        rows = rows[:limit]

    summary = {"to_process": len(rows), "present": 0, "failed": 0, "missing": 0,
               "backend": backend, "model": model, "details": []}
    t0 = time.time()
    for i, row in enumerate(rows, 1):
        call_id = row["call_id"]
        with store.connect() as conn:
            status, detail = transcribe_call(
                conn, client, call_id, row["recording_url"],
                backend=backend, model=model, keep_recording=keep_recordings)
        summary[status] = summary.get(status, 0) + 1
        elapsed = time.time() - t0
        log.info("[%d/%d] %s -> %s (%s) | %.0fs elapsed",
                 i, len(rows), call_id, status, detail, elapsed)
        summary["details"].append({"call_id": call_id, "status": status, "detail": detail})
    summary["elapsed_s"] = round(time.time() - t0, 1)
    return summary


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", default=DEFAULT_BACKEND,
                    choices=["mlx", "openai", "groq"],
                    help="mlx = local Apple Silicon; openai/groq = hosted API")
    ap.add_argument("--model", default=None, help="override the backend's default model")
    ap.add_argument("--force", action="store_true", help="re-transcribe all")
    ap.add_argument("--keep-recordings", action="store_true",
                    help="retain .mp4 files (default deletes them post-transcription)")
    ap.add_argument("--limit", type=int, default=None)
    a = ap.parse_args()
    s = run(backend=a.backend, model=a.model, force=a.force,
            keep_recordings=a.keep_recordings, limit=a.limit)
    s["details"] = s["details"][-5:]
    print(json.dumps(s, indent=2, default=str))
