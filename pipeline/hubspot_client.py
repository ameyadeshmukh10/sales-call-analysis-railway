"""HubSpot REST client. Auth, pagination, search, associations, retry/backoff.

Read-only usage only — this system never writes to HubSpot.

The token is read from HUBSPOT_PRIVATE_APP_TOKEN and is NEVER logged. Error
messages from this module deliberately omit the Authorization header.

EU data residency note: the CRM API uses the global host (api.hubapi.com) even
for app-eu1 portals. Only recording/transcript *media* is served from region
hosts (api-eu1 / hubspotusercontent-eu1.net); those URLs come back fully formed
in the call record and are fetched as-is.
"""
from __future__ import annotations

import logging
import os
import time
from typing import Any, Iterator

import requests
from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger("hubspot")

BASE_URL = os.environ.get("HUBSPOT_BASE_URL", "https://api.hubapi.com").rstrip("/")
TOKEN = os.environ.get("HUBSPOT_PRIVATE_APP_TOKEN", "")

CALLS_OBJECT = "0-48"  # Calls engagement object type


class HubSpotError(RuntimeError):
    pass


def _retry_after_seconds(val, default: float = 10.0) -> float:
    """Parse a Retry-After header (delta-seconds OR an HTTP-date) into a float,
    falling back to `default` on anything unparseable — so a 429 never crashes
    the retry loop with a ValueError."""
    if not val:
        return default
    try:
        return max(0.0, float(val))
    except (TypeError, ValueError):
        pass
    try:
        from datetime import datetime, timezone
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(val)
        if dt is not None:
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return max(0.0, (dt - datetime.now(timezone.utc)).total_seconds())
    except Exception:
        pass
    return default


class HubSpotClient:
    def __init__(self, token: str | None = None, base_url: str | None = None,
                 timeout: int = 30):
        self.token = token or TOKEN
        if not self.token:
            raise HubSpotError("HUBSPOT_PRIVATE_APP_TOKEN env var is not set")
        self.base = (base_url or BASE_URL).rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        })

    # ---------- core request with retry / rate-limit handling ---------- #
    def request(self, method: str, path: str, *, params: dict | None = None,
                json_body: dict | None = None, max_retries: int = 6,
                raw: bool = False) -> Any:
        url = f"{self.base}{path}" if path.startswith("/") else f"{self.base}/{path}"
        attempt = 0
        while True:
            attempt += 1
            try:
                r = self.session.request(method, url, params=params,
                                         json=json_body, timeout=self.timeout)
            except requests.RequestException as e:
                if attempt >= max_retries:
                    raise HubSpotError(
                        f"Network error after {attempt} attempts on {method} {path}: {e}")
                time.sleep(min(2 ** attempt, 30))
                continue

            if r.status_code == 429:
                wait = _retry_after_seconds(r.headers.get("Retry-After"))
                log.warning("rate-limited on %s; sleeping %ss", path, wait)
                time.sleep(wait)
                continue
            if 500 <= r.status_code < 600 and attempt < max_retries:
                time.sleep(min(2 ** attempt, 30))
                continue
            if r.status_code >= 400:
                # Never include the token; only path + status + body snippet.
                raise HubSpotError(f"{method} {path} -> {r.status_code}: {r.text[:300]}")
            if raw:
                return r
            if not r.content:
                return {}
            try:
                return r.json()
            except ValueError as e:
                # 2xx with a non-JSON body (e.g. an edge/interstitial HTML page).
                # Funnel into the HubSpotError path callers already handle.
                raise HubSpotError(
                    f"{method} {path} -> {r.status_code} non-JSON body: "
                    f"{r.text[:200]}") from e

    # ---------- list / search pagination ---------- #
    def search(self, object_type: str, *, properties: list[str],
               filter_groups: list[dict] | None = None,
               sorts: list[dict] | None = None, page_size: int = 100,
               limit: int | str = "all") -> Iterator[dict]:
        """POST /search with cursor pagination. Search API caps at 10k results."""
        path = f"/crm/v3/objects/{object_type}/search"
        body: dict[str, Any] = {
            "properties": properties,
            "limit": min(page_size, 200),
            "filterGroups": filter_groups or [],
            "sorts": sorts or [],
        }
        fetched = 0
        after: str | None = None
        while True:
            if after:
                body["after"] = after
            else:
                body.pop("after", None)
            data = self.request("POST", path, json_body=body)
            for item in data.get("results", []):
                yield item
                fetched += 1
                if limit != "all" and fetched >= int(limit):
                    return
            paging = (data.get("paging") or {}).get("next") or {}
            after = paging.get("after")
            if not after:
                return
            if fetched >= 10000:  # search API hard cap
                log.warning("search hit 10k cap for %s; narrow the window", object_type)
                return

    def get_object(self, object_type: str, obj_id: str, *,
                   properties: list[str] | None = None,
                   associations: list[str] | None = None) -> dict:
        params: dict[str, Any] = {}
        if properties:
            params["properties"] = ",".join(properties)
        if associations:
            params["associations"] = ",".join(associations)
        return self.request("GET", f"/crm/v3/objects/{object_type}/{obj_id}",
                            params=params)

    # ---------- batch reads ---------- #
    def batch_read(self, object_type: str, ids: list[str],
                   properties: list[str]) -> list[dict]:
        path = f"/crm/v3/objects/{object_type}/batch/read"
        out: list[dict] = []
        for chunk in _chunks(ids, 100):
            body = {"properties": properties, "inputs": [{"id": x} for x in chunk]}
            try:
                data = self.request("POST", path, json_body=body)
            except HubSpotError as e:
                # Skip a bad chunk rather than aborting the whole ingest.
                log.warning("batch_read %s: skipping chunk of %d (%s)",
                            object_type, len(chunk), e)
                continue
            out.extend(data.get("results", []))
        return out

    def associations_batch_read(self, from_type: str, to_type: str,
                                ids: list[str]) -> dict[str, list[str]]:
        """Batch resolve associations. Returns {from_id: [to_id, ...]}."""
        out: dict[str, list[str]] = {}
        path = f"/crm/v4/associations/{from_type}/{to_type}/batch/read"
        for chunk in _chunks(ids, 1000):
            body = {"inputs": [{"id": x} for x in chunk]}
            try:
                data = self.request("POST", path, json_body=body)
            except HubSpotError as e:
                # A failed chunk -> those ids get no associations; don't abort.
                log.warning("associations %s->%s: skipping chunk of %d (%s)",
                            from_type, to_type, len(chunk), e)
                continue
            for rec in data.get("results", []):
                src = rec["from"]["id"]
                out[src] = [t["toObjectId"] for t in rec.get("to", [])]
        return out

    # ---------- owners ---------- #
    def get_owner(self, owner_id: str) -> dict:
        return self.request("GET", f"/crm/v3/owners/{owner_id}")

    # ---------- transcript (calling extensions) ---------- #
    def get_transcript(self, transcript_id: str) -> dict:
        """GET /crm/v3/extensions/calling/transcripts/{id}.

        Raises HubSpotError (404 if the transcript isn't served for this call,
        403 if the token lacks crm.extensions_calling_transcripts.read).
        Callers must catch and flag-missing rather than crash the run.
        """
        return self.request(
            "GET", f"/crm/v3/extensions/calling/transcripts/{transcript_id}")

    # ---------- media download (recordings) ---------- #
    def download(self, url: str, dest, chunk: int = 1 << 16) -> int:
        """Stream a (possibly region-host, signed) media URL to a file.

        Returns bytes written. Recording URLs are pre-signed CDN links returned
        in the call record; we pass the bearer token too in case the first hop
        is the auth retriever.
        """
        from pathlib import Path
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        # Media endpoints reject the session's JSON Accept header (406) and
        # serve a signed CDN redirect; request any content type and follow it.
        headers = {"Accept": "*/*", "Content-Type": None}
        attempt = 0
        while True:
            attempt += 1
            try:
                with self.session.get(url, stream=True, timeout=self.timeout,
                                      headers=headers, allow_redirects=True) as r:
                    if r.status_code == 429 and attempt < 5:
                        time.sleep(_retry_after_seconds(r.headers.get("Retry-After")))
                        continue
                    if r.status_code >= 400:
                        raise HubSpotError(f"download -> {r.status_code}")
                    expected = int(r.headers.get("Content-Length") or 0)
                    n = 0
                    with open(dest, "wb") as f:
                        for block in r.iter_content(chunk_size=chunk):
                            f.write(block)
                            n += len(block)
                    if expected and n < expected and attempt < 5:
                        # short read vs Content-Length -> transient truncation
                        # (the "partial file" ffmpeg later complains about). Retry
                        # the whole download.
                        log.warning("download truncated (%d/%d bytes) on %s; retrying",
                                    n, expected, dest.name)
                        time.sleep(min(2 ** attempt, 20))
                        continue
                    # Return whatever we have: a full file, or a best-effort
                    # partial after retries (ffmpeg can still extract its audio).
                    return n
            except requests.RequestException as e:
                if attempt >= 5:
                    raise HubSpotError(f"download network error: {e}")
                time.sleep(min(2 ** attempt, 20))


def _chunks(seq: list, n: int):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def date_to_ms(iso_date: str) -> int:
    """'2026-05-01' -> epoch milliseconds (UTC midnight)."""
    from datetime import datetime, timezone
    dt = datetime.strptime(iso_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)
