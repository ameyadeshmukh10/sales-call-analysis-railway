#!/usr/bin/env bash
# Container entrypoint: start the background ingest scheduler, then the dashboard.
set -euo pipefail

DATA_DIR="${DATA_DIR:-/data}"
OUTPUTS_DIR="${OUTPUTS_DIR:-${DATA_DIR}/outputs}"
export DATA_DIR OUTPUTS_DIR

# Make sure the volume dirs exist (first boot on a fresh volume).
mkdir -p "${DATA_DIR}" "${DATA_DIR}/transcripts" "${DATA_DIR}/results" \
         "${DATA_DIR}/ui_runs" "${OUTPUTS_DIR}"

# Surface where data lands and whether it actually persists. If DATA_DIR is not a
# real mountpoint, anything written there is EPHEMERAL and lost on the next
# redeploy — catch that here instead of discovering it after a long run.
echo "[start] DATA_DIR=${DATA_DIR}  OUTPUTS_DIR=${OUTPUTS_DIR}"
if grep -q " ${DATA_DIR} " /proc/mounts 2>/dev/null; then
    echo "[start] OK: ${DATA_DIR} is a mounted volume — data persists across redeploys."
else
    echo "[start] WARNING: ${DATA_DIR} is NOT a mountpoint — data written here is EPHEMERAL"
    echo "[start]          and will be lost on redeploy. Check that the Railway volume's"
    echo "[start]          mount path matches DATA_DIR exactly."
fi

# Background: nightly ingest + transcribe. No-op unless SCHEDULE_INGEST=1.
python -m pipeline.scheduler &

# Foreground: the Streamlit dashboard on the port Railway assigns.
# CORS/XSRF are relaxed so the websocket connects cleanly behind Railway's proxy.
exec streamlit run ui/app.py \
    --server.port "${PORT:-8501}" \
    --server.address 0.0.0.0 \
    --server.headless true \
    --server.enableCORS false \
    --server.enableXsrfProtection false \
    --browser.gatherUsageStats false
