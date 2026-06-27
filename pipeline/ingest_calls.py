"""Deterministic ingestion of the HubSpot 'recorded_calls' view.

Pulls May-2026 recorded calls (those carrying a recording URL or a transcript),
traverses each call's associated contacts / companies / deals, resolves the
owning rep, and stores everything together in the SQLite store so the analysis
layer can join across all of it.

Idempotent: re-running upserts in place and never duplicates. Incremental:
pass incremental=True to only re-pull calls modified since the last watermark.

This is plain ETL — no agents. Transcript/recording *content* fetching lives in
fetch_transcripts.py and runs as a second deterministic step.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from dotenv import load_dotenv

from .hubspot_client import HubSpotClient, HubSpotError, date_to_ms, CALLS_OBJECT
from . import store

load_dotenv()
log = logging.getLogger("ingest")

DATA_DIR = Path(os.environ.get("DATA_DIR", "./data")).resolve()
RAW_DIR = DATA_DIR / "raw"

CALL_PROPS = [
    "hs_timestamp", "hs_createdate", "hs_lastmodifieddate", "hs_call_duration",
    "hs_call_recording_duration", "hs_call_direction", "hs_call_disposition",
    "hs_call_title", "hs_call_body", "hs_call_source", "hs_call_status",
    "hs_call_recording_url", "hs_call_video_recording_url",
    "hs_call_transcription_id", "hs_call_has_transcript",
    "hs_call_has_voicemail", "hubspot_owner_id",
]
CONTACT_PROPS = ["firstname", "lastname", "jobtitle", "email", "associatedcompanyid"]
COMPANY_PROPS = ["name", "domain", "industry", "numberofemployees",
                 "annualrevenue", "country"]
DEAL_PROPS = ["dealname", "dealstage", "pipeline", "amount", "closedate",
              "hs_is_closed", "hs_is_closed_won"]


def _save_raw(object_type: str, obj_id: str, payload: dict) -> str:
    d = RAW_DIR / object_type
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{obj_id}.json"
    p.write_text(json.dumps(payload, default=str, indent=2))
    return str(p.relative_to(DATA_DIR.parent)) if DATA_DIR.parent in p.parents else str(p)


def _resolve_stage_maps(client: HubSpotClient) -> tuple[dict, dict, dict]:
    """Return (stage_label, stage_closed, stage_won) keyed by stage id, plus
    pipeline_label keyed by pipeline id."""
    stage_label, stage_closed, stage_won, pipeline_label = {}, {}, {}, {}
    data = client.request("GET", "/crm/v3/pipelines/deals")
    for p in data.get("results", []):
        pipeline_label[p["id"]] = p.get("label")
        for s in p.get("stages", []):
            meta = s.get("metadata", {}) or {}
            stage_label[s["id"]] = s.get("label")
            closed = str(meta.get("isClosed", "false")).lower() == "true"
            stage_closed[s["id"]] = closed
            stage_won[s["id"]] = closed and float(meta.get("probability", 0) or 0) >= 1.0
    return stage_label, stage_closed, stage_won, pipeline_label


def _disposition_labels(client: HubSpotClient) -> dict:
    """Map hs_call_disposition GUIDs -> human labels."""
    try:
        data = client.request(
            "GET", f"/crm/v3/properties/{CALLS_OBJECT}/hs_call_disposition")
        return {o["value"]: o["label"] for o in data.get("options", [])}
    except HubSpotError:
        return {}


def _to_int(v):
    try:
        return int(float(v)) if v not in (None, "") else None
    except (ValueError, TypeError):
        return None


def _to_float(v):
    try:
        return float(v) if v not in (None, "") else None
    except (ValueError, TypeError):
        return None


def ingest(window_start: str | None = None, window_end: str | None = None,
           incremental: bool = False, limit: int | str = "all") -> dict:
    window_start = window_start or os.environ.get("INGEST_WINDOW_START", "2026-05-01")
    # window_end is optional. Incremental/scheduled runs IGNORE it and use an
    # open-ended upper bound (below) so calls after it still flow in.
    window_end = window_end or os.environ.get("INGEST_WINDOW_END")
    lo = str(date_to_ms(window_start))

    store.init_db()
    client = HubSpotClient()
    try:
        stage_label, stage_closed, stage_won, pipeline_label = _resolve_stage_maps(client)
    except HubSpotError as e:
        log.warning("pipeline stage maps unresolved, using raw stage ids: %s", e)
        stage_label, stage_closed, stage_won, pipeline_label = {}, {}, {}, {}
    disp_labels = _disposition_labels(client)

    # recorded_calls view = timestamp in window AND (has transcript OR has recording).
    # Two filterGroups -> OR between them, AND within each.
    if incremental or not window_end:
        # Open-ended upper bound; the hs_lastmodifieddate watermark filter (added
        # below) is what actually bounds an incremental re-pull. A fixed past
        # window_end would silently stop ingesting any newer calls.
        base_ts = {"propertyName": "hs_timestamp", "operator": "GTE", "value": lo}
    else:
        base_ts = {"propertyName": "hs_timestamp", "operator": "BETWEEN",
                   "value": lo, "highValue": str(date_to_ms(window_end))}
    filter_groups = [
        {"filters": [base_ts, {"propertyName": "hs_call_has_transcript",
                               "operator": "EQ", "value": "true"}]},
        {"filters": [base_ts, {"propertyName": "hs_call_recording_url",
                               "operator": "HAS_PROPERTY"}]},
    ]
    if incremental:
        with store.connect() as conn:
            wm = store.get_watermark(conn, "calls")
        if wm:
            for g in filter_groups:
                g["filters"].append({"propertyName": "hs_lastmodifieddate",
                                     "operator": "GT", "value": wm})

    calls = list(client.search(CALLS_OBJECT, properties=CALL_PROPS,
                               filter_groups=filter_groups,
                               sorts=[{"propertyName": "hs_timestamp",
                                       "direction": "ASCENDING"}],
                               limit=limit))
    # de-dup (a call can match both filter groups)
    seen, unique = set(), []
    for c in calls:
        if c["id"] not in seen:
            seen.add(c["id"])
            unique.append(c)
    calls = unique
    call_ids = [c["id"] for c in calls]
    log.info("recorded calls in window: %d", len(calls))

    # Resolve associations in batch.
    assoc_contacts = client.associations_batch_read(CALLS_OBJECT, "contacts", call_ids) if call_ids else {}
    assoc_companies = client.associations_batch_read(CALLS_OBJECT, "companies", call_ids) if call_ids else {}
    assoc_deals = client.associations_batch_read(CALLS_OBJECT, "deals", call_ids) if call_ids else {}

    contact_ids = sorted({x for v in assoc_contacts.values() for x in v})
    company_ids = sorted({x for v in assoc_companies.values() for x in v})
    deal_ids = sorted({x for v in assoc_deals.values() for x in v})

    contacts = client.batch_read("contacts", contact_ids, CONTACT_PROPS) if contact_ids else []
    companies = client.batch_read("companies", company_ids, COMPANY_PROPS) if company_ids else []
    deals = client.batch_read("deals", deal_ids, DEAL_PROPS) if deal_ids else []

    owner_ids = sorted({(c["properties"].get("hubspot_owner_id") or "")
                        for c in calls if c["properties"].get("hubspot_owner_id")})

    watermark = None
    summary = {"n_calls": len(calls), "n_contacts": len(contacts),
               "n_companies": len(companies), "n_deals": len(deals),
               "n_owners": len(owner_ids), "with_transcript_flag": 0,
               "with_recording_url": 0, "deal_outcomes": {}}

    # Resolve owners (network I/O) BEFORE opening the write transaction, so the
    # SQLite write lock isn't held across HubSpot round-trips (keeps the lock
    # short for the concurrent scheduler / UI / analysis writers).
    owner_rows = []
    for oid in owner_ids:
        try:
            o = client.get_owner(oid)
            fn, ln = o.get("firstName"), o.get("lastName")
            owner_rows.append({
                "owner_id": oid, "first_name": fn, "last_name": ln,
                "full_name": " ".join(x for x in [fn, ln] if x) or o.get("email"),
                "email": o.get("email"),
                "raw_json_path": _save_raw("owners", oid, o)})
        except HubSpotError as e:
            log.warning("owner %s unresolved: %s", oid, e)
            owner_rows.append({"owner_id": oid, "full_name": None})

    with store.connect() as conn:
        # owners
        for row in owner_rows:
            store.upsert_owner(conn, row)

        # contacts
        for c in contacts:
            p = c["properties"]
            fn, ln = p.get("firstname"), p.get("lastname")
            store.upsert_contact(conn, {
                "contact_id": c["id"], "first_name": fn, "last_name": ln,
                "full_name": " ".join(x for x in [fn, ln] if x) or None,
                "job_title": p.get("jobtitle"), "email": p.get("email"),
                "company_id": p.get("associatedcompanyid"),
                "raw_json_path": _save_raw("contacts", c["id"], c)})

        # companies
        for c in companies:
            p = c["properties"]
            store.upsert_company(conn, {
                "company_id": c["id"], "name": p.get("name"),
                "domain": p.get("domain"), "industry": p.get("industry"),
                "num_employees": p.get("numberofemployees"),
                "annual_revenue": p.get("annualrevenue"),
                "country": p.get("country"),
                "raw_json_path": _save_raw("companies", c["id"], c)})

        # deals
        for d in deals:
            p = d["properties"]
            stage = p.get("dealstage")
            is_closed = str(p.get("hs_is_closed", "")).lower() == "true" or stage_closed.get(stage, False)
            is_won = str(p.get("hs_is_closed_won", "")).lower() == "true" or stage_won.get(stage, False)
            status = "won" if is_won else ("lost" if is_closed else "open")
            summary["deal_outcomes"][status] = summary["deal_outcomes"].get(status, 0) + 1
            store.upsert_deal(conn, {
                "deal_id": d["id"], "name": p.get("dealname"),
                "stage": stage, "stage_label": stage_label.get(stage, stage),
                "pipeline": p.get("pipeline"),
                "pipeline_label": pipeline_label.get(p.get("pipeline"), p.get("pipeline")),
                "amount": _to_float(p.get("amount")), "status": status,
                "is_closed": int(is_closed), "is_won": int(is_won),
                "close_date": p.get("closedate"),
                "raw_json_path": _save_raw("deals", d["id"], d)})

        # calls + junctions + transcript state
        for c in calls:
            p = c["properties"]
            has_tr = str(p.get("hs_call_has_transcript", "")).lower() == "true"
            rec_url = p.get("hs_call_recording_url")
            if has_tr:
                summary["with_transcript_flag"] += 1
            if rec_url:
                summary["with_recording_url"] += 1
            lm = p.get("hs_lastmodifieddate")
            if lm and (watermark is None or lm > watermark):
                watermark = lm
            # transcript_status starts 'pending' if there's any content to fetch
            t_status = "pending" if (has_tr or p.get("hs_call_transcription_id") or rec_url) else "missing"
            store.upsert_call(conn, {
                "call_id": c["id"], "hs_timestamp": p.get("hs_timestamp"),
                "created_at": p.get("hs_createdate"), "last_modified": lm,
                "duration_ms": _to_int(p.get("hs_call_duration")),
                "recording_duration_ms": _to_int(p.get("hs_call_recording_duration")),
                "direction": p.get("hs_call_direction"),
                "disposition": p.get("hs_call_disposition"),
                "disposition_label": disp_labels.get(p.get("hs_call_disposition")),
                "title": p.get("hs_call_title"), "body": p.get("hs_call_body"),
                "source": p.get("hs_call_source"), "status": p.get("hs_call_status"),
                "recording_url": rec_url,
                "video_recording_url": p.get("hs_call_video_recording_url"),
                "transcription_id": p.get("hs_call_transcription_id"),
                "has_transcript": int(has_tr),
                "has_voicemail": int(str(p.get("hs_call_has_voicemail", "")).lower() == "true"),
                # Normalize "" -> None so the FK (-> owners) stays satisfiable;
                # empty owner ids are filtered out of the owners table above.
                "owner_id": (p.get("hubspot_owner_id") or None),
                "transcript_status": t_status,
                "raw_json_path": _save_raw("calls", c["id"], c),
                "ingested_at": store.now_iso()})
            for cid in assoc_contacts.get(c["id"], []):
                store.link(conn, "call_contacts", "call_id", c["id"], "contact_id", cid)
            for coid in assoc_companies.get(c["id"], []):
                store.link(conn, "call_companies", "call_id", c["id"], "company_id", coid)
            for did in assoc_deals.get(c["id"], []):
                store.link(conn, "call_deals", "call_id", c["id"], "deal_id", did)

        store.set_watermark(conn, "calls", watermark, len(calls),
                            notes=f"window {window_start}..{window_end or 'open'}")

    summary["watermark"] = watermark
    summary["window"] = f"{window_start}..{window_end or 'open'}"
    return summary


if __name__ == "__main__":
    import argparse
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--start"); ap.add_argument("--end")
    ap.add_argument("--incremental", action="store_true")
    ap.add_argument("--limit", default="all")
    a = ap.parse_args()
    limit = a.limit if a.limit == "all" else int(a.limit)
    s = ingest(a.start, a.end, incremental=a.incremental, limit=limit)
    print(json.dumps(s, indent=2, default=str))
