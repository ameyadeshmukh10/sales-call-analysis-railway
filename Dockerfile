# Sales Call Analysis — container image for Railway.
#
# Bundles everything the running system needs:
#   - Python 3.11 + the pipeline / UI deps
#   - ffmpeg            (audio extraction + chunking for transcription)
#   - Node 20 + the Claude Code CLI  (the analysis engine shells out to `claude -p`)
#
# Data (SQLite DB, transcripts, deliverables) lives on a mounted Railway volume at
# /data — see DEPLOY.md. Nothing here writes call content into the image.
FROM python:3.11-slim

# System deps. Node 20 for the Claude CLI (needs Node >= 18); ffmpeg for STT.
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg ca-certificates curl git \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# Claude Code CLI — the agentic Stage A–D analysis runs through `claude -p`.
RUN npm install -g @anthropic-ai/claude-code

WORKDIR /app

# Python deps first so the layer caches across code changes.
COPY requirements.txt requirements-ui.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements-ui.txt

# App code (data/ and outputs/ are excluded via .dockerignore — they live on the volume).
COPY . .
RUN chmod +x start.sh

# Defaults; override any of these from the Railway service variables.
ENV PYTHONUNBUFFERED=1 \
    DATA_DIR=/data \
    OUTPUTS_DIR=/data/outputs \
    STT_BACKEND=openai

EXPOSE 8501
CMD ["./start.sh"]
