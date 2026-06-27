# Deploying to Railway

This is the operator guide for running the Sales Call Analysis system on
[Railway](https://railway.app) as a hosted dashboard with persistent storage.

## What gets deployed

One Railway **service** (built from the `Dockerfile`) running:

- the **Streamlit dashboard** (web, on Railway's `$PORT`),
- the **deterministic pipeline** (HubSpot ingest + OpenAI Whisper transcription),
  triggered from the dashboard and/or on a nightly schedule,
- the **Claude analysis engine** (`claude -p`, bundled in the image),

with all call data on a single mounted **volume** at `/data`.

```
                 ┌──────────────────────── Railway service ───────────────────────┐
   HubSpot  ──►  │  pipeline (ingest + transcribe)   Claude CLI (Stage A–D)        │
   OpenAI   ──►  │             │                          │                        │
   Anthropic──►  │             ▼                          ▼                        │
                 │        ┌─────────────── /data (volume) ───────────────┐         │
                 │        │  calls.db · transcripts/ · results/ · outputs/ │         │
                 │        └───────────────────┬───────────────────────────┘         │
                 │   Streamlit dashboard ◄────┘  (reads store + outputs)            │
                 └──────────────────────────────────────────────────────────────────┘
```

### Why one service, not a separate cron service

Railway volumes attach to **exactly one service** — they can't be shared. So the
nightly ingest can't live in its own cron service alongside a separate web
service: they couldn't both see the data. Instead the schedule runs **inside the
web service container** (`pipeline/scheduler.py`, launched by `start.sh`),
writing to the same volume. Same outcome, one source of truth.

---

## Prerequisites

- A Railway account and the new **code-only** GitHub repo connected to it.
- API keys:
  - `HUBSPOT_PRIVATE_APP_TOKEN` — read-only HubSpot private-app token.
  - `OPENAI_API_KEY` — for Whisper transcription (`whisper-1`).
  - `ANTHROPIC_API_KEY` — for the Claude analysis engine.

---

## Step 1 — Create the service

1. Railway → **New Project** → **Deploy from GitHub repo** → pick the new repo.
2. Railway detects the `Dockerfile` and `railway.json` and builds the image.
   (First build is slow — it installs ffmpeg, Node, and the Claude CLI.)
3. Don't worry about the first deploy crashing/looping yet — it has no volume or
   secrets. We add those next, then redeploy.

## Step 2 — Add the volume

1. In the service → **Settings** → **Volumes** → **New Volume**.
2. **Mount path:** `/data`
3. Size: start small (1 GB is plenty — recordings are deleted post-transcription;
   only the DB, transcripts, and deliverables persist).

The image already defaults `DATA_DIR=/data` and `OUTPUTS_DIR=/data/outputs`, so
mounting at `/data` is all that's strictly required for storage.

## Step 3 — Set environment variables

Service → **Variables** → add these (Raw editor makes it quick):

```
# Required — HubSpot ingest
HUBSPOT_PRIVATE_APP_TOKEN=pat-eu1-...
HUBSPOT_BASE_URL=https://api.hubapi.com
HUBSPOT_HUB_ID=144358290

# Required — transcription (OpenAI Whisper)
STT_BACKEND=openai
OPENAI_API_KEY=sk-...
OPENAI_WHISPER_MODEL=whisper-1

# Required — analysis engine (Claude)
ANTHROPIC_API_KEY=sk-ant-...

# Storage (defaults already baked into the image; set explicitly for clarity)
DATA_DIR=/data
OUTPUTS_DIR=/data/outputs

# Ingestion window (adjust as your corpus grows)
INGEST_WINDOW_START=2026-05-01
INGEST_WINDOW_END=2026-06-01

# Nightly scheduled ingest (optional — see Step 6)
SCHEDULE_INGEST=0
SCHEDULE_HOUR_UTC=6
SCHEDULE_MINUTE_UTC=0
```

> `FIREWORKS_API_KEY` is intentionally omitted — nothing in the code uses it yet.
> Add it only when/if an alternative-LLM path is wired in.

## Step 4 — Deploy & get a URL

1. Trigger a redeploy (Railway usually does this automatically after variable
   changes).
2. Service → **Settings** → **Networking** → **Generate Domain**.
3. Open the URL. The dashboard boots on the empty volume (it creates the SQLite
   schema on first load), so every page renders — just with no data yet.

## Step 5 — Seed the data (first run)

A fresh volume starts empty. Populate it from the dashboard's **Run pipeline**
page, in order:

1. **Ingest + transcribe** — pulls the configured window from HubSpot and
   transcribes each recording via OpenAI Whisper. Idempotent + resumable.
2. **Analyze calls (AI)** — runs the Stage A–D Claude analysis, then rebuilds
   scores and the deliverables. (Requires `ANTHROPIC_API_KEY`; the page will tell
   you if the CLI can't authenticate.)
3. **Rebuild scores & insights** — fast, no AI; recomputes rankings + action
   items from existing analysis.

Your existing local `data/` and `outputs/` stay on your Mac as a backup. Because
this repo is code-only and Railway has no direct volume-upload, the clean way to
populate the volume is to re-run the pipeline above (transcription is cheap;
analysis reproduces the deliverables). Everything is idempotent, so re-runs only
do new work.

## Step 6 — Turn on the nightly schedule (optional)

To have new calls flow in automatically, set `SCHEDULE_INGEST=1` (and adjust
`SCHEDULE_HOUR_UTC` / `SCHEDULE_MINUTE_UTC`, both UTC). The in-container scheduler
runs an **incremental** ingest+transcribe nightly and logs to
`/data/ui_runs/scheduler-*.log`. Analysis stays operator-triggered; run it from
the dashboard after new calls land (or extend `pipeline/scheduler.py`).

---

## Verifying & troubleshooting

- **Health:** Railway healthchecks `\/_stcore\/health` (Streamlit). A green deploy
  means the web server is up.
- **Page hangs on "Connecting…":** already mitigated — `start.sh` runs Streamlit
  with CORS/XSRF relaxed for Railway's proxy.
- **"Claude CLI couldn't authenticate":** confirm `ANTHROPIC_API_KEY` is set on
  the service and the deploy picked it up (redeploy after adding variables).
- **Transcription errors:** check `OPENAI_API_KEY` and that `STT_BACKEND=openai`.
  Per-call failures are flagged (`transcript_status=failed`), never fatal.
- **Data persistence:** data lives on the `/data` volume and survives redeploys.
  Deleting the volume deletes the data — there's no copy in git (by design).
- **Logs:** Railway **Deploy Logs** for the app; pipeline/scheduler run logs live
  under `/data/ui_runs/` and are tailed in the dashboard's run panels.

## Security notes

- The repo is **code-only** — no call content or PII in git.
- All customer data lives on the Railway volume; keep the project private and
  limit who can open a shell on the service.
- HubSpot access is **read-only**; the system never modifies CRM records.
