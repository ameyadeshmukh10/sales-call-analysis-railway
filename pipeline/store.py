"""SQLite store for the Sales Call Analysis system.

Relational core (calls + entities + junctions) serves the analysis layer's
query pattern: "every call owned by rep X against persona Y where the deal
advanced past stage Z". Large blobs (transcript text, full HubSpot JSON,
recordings) live as files under data/ and are referenced by path, keeping the
DB lean.

All writes are idempotent upserts keyed on the HubSpot object id, so the
ingestion pipeline is safe to re-run: a second run updates in place and never
duplicates. Agent outputs land in `analysis_results`, versioned per
(call_id, agent, version), so re-running an agent keeps history instead of
overwriting it.
"""
from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from dotenv import load_dotenv

load_dotenv()

DATA_DIR = Path(os.environ.get("DATA_DIR", "./data")).resolve()
DB_PATH = DATA_DIR / "calls.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS owners (
    owner_id    TEXT PRIMARY KEY,
    first_name  TEXT,
    last_name   TEXT,
    full_name   TEXT,
    email       TEXT,
    raw_json_path TEXT
);

CREATE TABLE IF NOT EXISTS contacts (
    contact_id   TEXT PRIMARY KEY,
    first_name   TEXT,
    last_name    TEXT,
    full_name    TEXT,
    job_title    TEXT,
    email        TEXT,
    company_name TEXT,
    company_id   TEXT,
    raw_json_path TEXT
);

CREATE TABLE IF NOT EXISTS companies (
    company_id      TEXT PRIMARY KEY,
    name            TEXT,
    domain          TEXT,
    industry        TEXT,
    num_employees   TEXT,
    annual_revenue  TEXT,
    country         TEXT,
    raw_json_path   TEXT
);

CREATE TABLE IF NOT EXISTS deals (
    deal_id      TEXT PRIMARY KEY,
    name         TEXT,
    stage        TEXT,
    stage_label  TEXT,
    pipeline     TEXT,
    pipeline_label TEXT,
    amount       REAL,
    status       TEXT,          -- open | won | lost
    is_closed    INTEGER,
    is_won       INTEGER,
    close_date   TEXT,
    raw_json_path TEXT
);

CREATE TABLE IF NOT EXISTS calls (
    call_id            TEXT PRIMARY KEY,
    hs_timestamp       TEXT,
    created_at         TEXT,
    last_modified      TEXT,
    duration_ms        INTEGER,
    recording_duration_ms INTEGER,
    direction          TEXT,
    disposition        TEXT,
    disposition_label  TEXT,
    title              TEXT,
    body               TEXT,
    source             TEXT,
    status             TEXT,
    recording_url      TEXT,
    video_recording_url TEXT,
    transcription_id   TEXT,
    has_transcript     INTEGER,   -- HubSpot's flag (hs_call_has_transcript)
    has_voicemail      INTEGER,
    owner_id           TEXT,
    -- pipeline-managed transcript/recording state
    transcript_status  TEXT,      -- pending | present | missing | failed
    transcript_source  TEXT,      -- api | stt | none
    transcript_path    TEXT,
    recording_path     TEXT,
    raw_json_path      TEXT,
    ingested_at        TEXT,
    FOREIGN KEY (owner_id) REFERENCES owners(owner_id)
);

CREATE TABLE IF NOT EXISTS call_contacts (
    call_id    TEXT,
    contact_id TEXT,
    PRIMARY KEY (call_id, contact_id)
);

CREATE TABLE IF NOT EXISTS call_companies (
    call_id    TEXT,
    company_id TEXT,
    PRIMARY KEY (call_id, company_id)
);

CREATE TABLE IF NOT EXISTS call_deals (
    call_id TEXT,
    deal_id TEXT,
    PRIMARY KEY (call_id, deal_id)
);

-- Agent outputs, versioned. One row per (call_id, agent, version).
CREATE TABLE IF NOT EXISTS analysis_results (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    call_id     TEXT NOT NULL,
    agent       TEXT NOT NULL,
    version     INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT NOT NULL,
    result_json TEXT NOT NULL,
    UNIQUE (call_id, agent, version)
);

-- Incremental-ingest watermarks, one row per HubSpot object type.
CREATE TABLE IF NOT EXISTS ingest_state (
    object_type         TEXT PRIMARY KEY,
    last_run_at         TEXT,
    last_modified_watermark TEXT,
    n_seen              INTEGER DEFAULT 0,
    notes               TEXT
);

CREATE INDEX IF NOT EXISTS idx_calls_owner   ON calls(owner_id);
CREATE INDEX IF NOT EXISTS idx_calls_ts      ON calls(hs_timestamp);
CREATE INDEX IF NOT EXISTS idx_calls_tstatus ON calls(transcript_status);
CREATE INDEX IF NOT EXISTS idx_ar_call_agent ON analysis_results(call_id, agent);
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def connect(db_path: Path | str = DB_PATH):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db(db_path: Path | str = DB_PATH) -> None:
    with connect(db_path) as conn:
        conn.executescript(SCHEMA)


# ---------------- generic idempotent upsert ---------------- #

def _upsert(conn: sqlite3.Connection, table: str, pk: str, row: dict[str, Any]) -> None:
    """INSERT ... ON CONFLICT(pk) DO UPDATE. Only writes provided columns."""
    cols = [k for k in row.keys() if row[k] is not None or k == pk]
    if pk not in cols:
        cols.insert(0, pk)
    placeholders = ", ".join("?" for _ in cols)
    col_list = ", ".join(cols)
    updates = ", ".join(f"{c}=excluded.{c}" for c in cols if c != pk)
    sql = (
        f"INSERT INTO {table} ({col_list}) VALUES ({placeholders}) "
        f"ON CONFLICT({pk}) DO UPDATE SET {updates}"
    )
    conn.execute(sql, [row.get(c) for c in cols])


def upsert_owner(conn, row: dict) -> None:
    _upsert(conn, "owners", "owner_id", row)


def upsert_contact(conn, row: dict) -> None:
    _upsert(conn, "contacts", "contact_id", row)


def upsert_company(conn, row: dict) -> None:
    _upsert(conn, "companies", "company_id", row)


def upsert_deal(conn, row: dict) -> None:
    _upsert(conn, "deals", "deal_id", row)


def upsert_call(conn, row: dict) -> None:
    _upsert(conn, "calls", "call_id", row)


def link(conn, table: str, a_col: str, a_val: str, b_col: str, b_val: str) -> None:
    conn.execute(
        f"INSERT OR IGNORE INTO {table} ({a_col}, {b_col}) VALUES (?, ?)",
        (a_val, b_val),
    )


def set_call_transcript_state(conn, call_id: str, *, status: str,
                              source: str | None = None,
                              transcript_path: str | None = None,
                              recording_path: str | None = None) -> None:
    conn.execute(
        "UPDATE calls SET transcript_status=?, transcript_source=COALESCE(?, transcript_source), "
        "transcript_path=COALESCE(?, transcript_path), recording_path=COALESCE(?, recording_path) "
        "WHERE call_id=?",
        (status, source, transcript_path, recording_path, call_id),
    )


# ---------------- analysis results (versioned) ---------------- #

def next_version(conn, call_id: str, agent: str) -> int:
    cur = conn.execute(
        "SELECT COALESCE(MAX(version), 0) FROM analysis_results WHERE call_id=? AND agent=?",
        (call_id, agent),
    )
    return int(cur.fetchone()[0]) + 1


def write_analysis(conn, call_id: str, agent: str, result: Any,
                   version: int | None = None) -> int:
    """Store an agent result tagged to a call. Returns the version written.

    If version is None, appends a new version (keeps history). Pass an explicit
    version to overwrite a specific one.
    """
    v = version if version is not None else next_version(conn, call_id, agent)
    conn.execute(
        "INSERT INTO analysis_results (call_id, agent, version, created_at, result_json) "
        "VALUES (?, ?, ?, ?, ?) "
        "ON CONFLICT(call_id, agent, version) DO UPDATE SET "
        "created_at=excluded.created_at, result_json=excluded.result_json",
        (call_id, agent, v, now_iso(), json.dumps(result, default=str)),
    )
    return v


def latest_analysis(conn, call_id: str, agent: str) -> dict | None:
    cur = conn.execute(
        "SELECT result_json FROM analysis_results WHERE call_id=? AND agent=? "
        "ORDER BY version DESC LIMIT 1",
        (call_id, agent),
    )
    row = cur.fetchone()
    return json.loads(row[0]) if row else None


# ---------------- ingest watermark ---------------- #

def get_watermark(conn, object_type: str) -> str | None:
    cur = conn.execute(
        "SELECT last_modified_watermark FROM ingest_state WHERE object_type=?",
        (object_type,),
    )
    row = cur.fetchone()
    return row[0] if row else None


def set_watermark(conn, object_type: str, watermark: str | None, n_seen: int,
                  notes: str = "") -> None:
    conn.execute(
        "INSERT INTO ingest_state (object_type, last_run_at, last_modified_watermark, n_seen, notes) "
        "VALUES (?, ?, ?, ?, ?) "
        "ON CONFLICT(object_type) DO UPDATE SET "
        "last_run_at=excluded.last_run_at, "
        "last_modified_watermark=excluded.last_modified_watermark, "
        "n_seen=excluded.n_seen, notes=excluded.notes",
        (object_type, now_iso(), watermark, n_seen, notes),
    )


if __name__ == "__main__":
    init_db()
    print(f"Initialized SQLite store at {DB_PATH}")
