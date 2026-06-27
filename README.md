# Sales Call Analysis — SDR AI Worker

Ingests recorded HubSpot sales calls into a queryable store and runs narrow
analysis agents over them to sharpen how we price, package, discover, and run
the sales motion. Two cleanly separated parts: a **deterministic ingestion
pipeline** and an **agentic analysis layer**. See [AGENTS.md](AGENTS.md) for the
full architecture.

> **Deploying?** See [DEPLOY.md](DEPLOY.md) for the Railway setup (hosted
> dashboard, persistent volume, OpenAI transcription, nightly schedule).

## Quickstart

### 1. Install

```bash
pip install -r requirements.txt
# Local transcription needs ffmpeg (and Apple Silicon for the MLX backend):
brew install ffmpeg
```

### 2. Configure

```bash
cp .env.example .env
# edit .env and set HUBSPOT_PRIVATE_APP_TOKEN=pat-eu1-...
```

The token is read from the environment only and is never logged. `data/` (the
DB, transcripts, recordings) is gitignored — no call content or PII in git.

### 3. Ingest + transcribe

```bash
# Pull the recorded-calls view, traverse associations, then transcribe each
# recording. Pick a backend with --backend:
#   openai  hosted Whisper (whisper-1)         — needs OPENAI_API_KEY  (hosted/CI)
#   mlx     local Whisper large-v3-turbo (MLX) — Apple Silicon, no key (laptop)
#   groq    hosted Whisper large-v3            — needs GROQ_API_KEY
python -m pipeline.run_ingest --backend openai

# Faster: just ingest the CRM data, skip transcription
python -m pipeline.run_ingest --no-transcribe

# Only re-pull records changed since the last run
python -m pipeline.run_ingest --incremental
```

The default backend is read from `STT_BACKEND` (set to `openai` for the hosted
deploy; `mlx` for local laptop runs).

Run individual steps:

```bash
python -m pipeline.ingest_calls               # CRM ingest only
python -m pipeline.transcribe                  # transcribe pending recordings
python -m pipeline.transcribe --limit 2        # try a couple first
python -m pipeline.transcribe --keep-recordings  # retain .mp4 files
```

Transcription is idempotent and resumable: already-transcribed calls are
skipped, so a multi-hour batch can be stopped and restarted freely.

### 4. Inspect the store

```bash
sqlite3 data/calls.db
```

```sql
-- every call by rep, persona, company, and deal outcome
SELECT ca.call_id, o.full_name AS rep, ct.job_title AS persona,
       co.name AS company, d.stage_label, d.status
FROM calls ca
LEFT JOIN owners o        ON o.owner_id = ca.owner_id
LEFT JOIN call_contacts cc ON cc.call_id = ca.call_id
LEFT JOIN contacts ct      ON ct.contact_id = cc.contact_id
LEFT JOIN call_companies x ON x.call_id = ca.call_id
LEFT JOIN companies co     ON co.company_id = x.company_id
LEFT JOIN call_deals cd    ON cd.call_id = ca.call_id
LEFT JOIN deals d          ON d.deal_id = cd.deal_id
WHERE d.status = 'won';

-- transcript coverage
SELECT transcript_status, transcript_source, COUNT(*) FROM calls GROUP BY 1,2;
```

### 5. Run analysis (agentic layer)

The analysis agents in `/agents` read transcripts + deal outcomes from the
store, write versioned results back to `analysis_results`, and land the
deliverables + the derived rubric in `/outputs`. See [AGENTS.md](AGENTS.md).

### 6. The dashboard (UI)

```bash
pip install -r requirements-ui.txt     # streamlit + plotly
streamlit run ui/app.py                 # opens the EverWorker-branded dashboard
```

Five sections:
- **Overview & Run** — KPIs, live per-agent coverage, and run controls (ingest,
  transcribe, **Run analysis** = headless Claude over the pending worklist,
  re-score & aggregate). Each shows a live log + a copy-paste command fallback.
- **Calls** — filterable explorer (rep / persona / outcome / ICP / score).
- **Call detail** — transcript with rep/customer roles, discovery, objections,
  pricing reaction, next step, ICP, competitors, and a phase timeline.
- **Insights** — corpus charts + the 4 versioned deliverables (with diffs).
- **Action items** — ranked, data-driven punch list compiled from the deliverables.

The UI only reads the local store + `outputs/`; it triggers work through the same
CLIs and the `claude` CLI. Nothing new is computed behind your back.

## What's where

| Path | What |
|---|---|
| `pipeline/` | deterministic ETL — HubSpot client, store, ingest, transcribe |
| `skills/` | analysis agents (Stage A–D) |
| `data/` | SQLite db, transcripts, recordings, raw payloads (gitignored) |
| `outputs/` | versioned deliverables + rubric |
| `AGENTS.md` | architecture, schema, compounding model |

## Notes

- **Transcripts are auto-generated.** HubSpot doesn't serve these meeting-bot
  transcripts via API, so the pipeline downloads the recording and transcribes it
  with Whisper — hosted via OpenAI (`whisper-1`) for server/CI runs, or on-device
  via Apple MLX (~14× real-time on an M4) for local laptop runs.
- **Read-only** against HubSpot — the system never modifies CRM records.
- Missing transcripts/associations are flagged (`transcript_status`), never fatal.
