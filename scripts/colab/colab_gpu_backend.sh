#!/usr/bin/env bash
# =============================================================================
# MarkMute — free GPU backend for Google Colab (T4 for free, zero cost)
#
# Runs the full app+worker+redis stack natively (no Docker on Colab) with the
# pinned upstream backends, then exposes it through a free Cloudflare Quick
# Tunnel. Point the main app at it via:
#
#     PIXEL_REMOTE_URL=<tunnel-url>   (Vercel env)
#     PIXEL_REMOTE_KEY=<key>          (Vercel env; set PIXEL_REMOTE_ENFORCE=1 here)
#
# Usage in a Colab notebook (Runtime -> Change runtime type -> T4 GPU):
#   !git clone https://github.com/aptenox-technology/MarkMute.git
#   %cd MarkMute
#   !bash scripts/colab/colab_gpu_backend.sh
#
# Sessions last up to ~12 h on the free tier; restart the cell anytime and set
# the new tunnel URL on Vercel.
# =============================================================================
set -euo pipefail

NOAI_REF="b642ae45d20eded52c96d570985eb4e3e427aac8"
SYNTHID_REF="b11083676fd3ee3ff97ce9d03c0e409e46905902"
NOAI_REPO="https://github.com/mertizci/noai-watermark.git"
SYNTHID_REPO="https://github.com/aloshdenny/reverse-SynthID.git"

say()  { printf '\n\033[1;34m==>\033[0m %s\n' "$*"; }

[ "$(whoami)" = "root" ] || { echo "Colab runs as root — this must run inside a Colab cell"; exit 1; }

# --- 1. GPU present? -----------------------------------------------------------
nvidia-smi >/dev/null 2>&1 || {
  echo "No GPU — did you enable Runtime > Change runtime type > T4 GPU?"
  echo "Continuing on CPU is possible but CtrlRegen will be very slow."
}

# --- 2. System deps -------------------------------------------------------------
apt-get update -qq >/dev/null
apt-get install -y -qq redis-server exiftool libmagic1 >/dev/null
PIP="$(command -v pip3 || command -v pip)"

# --- 3. Python deps (Colab already ships CUDA torch — keep it) ------------------
$PIP install -q -r requirements.txt \
    -r upstream/watermarks-remover/skills/remove-ai-marks/scripts/requirements-ctrlregen.txt \
    -r upstream/watermarks-remover/skills/remove-ai-marks/scripts/requirements-synthid-scorer.txt

# --- 4. Provision upstream backends at pinned commits ---------------------------
mkdir -p data downloads
[ -d data/noai-watermark ] || {
  git clone --quiet "$NOAI_REPO" data/noai-watermark
  git -C data/noai-watermark checkout --quiet "$NOAI_REF"
}
[ -d data/reverse-SynthID ] || {
  git clone --quiet "$SYNTHID_REPO" data/reverse-SynthID
  git -C data/reverse-SynthID checkout --quiet "$SYNTHID_REF"
}

# --- 5. Env ---------------------------------------------------------------------
PIXEL_KEY="$(cat /dev/urandom | tr -dc 'a-f0-9' | head -c 24)"
cat > .env <<EOF
REDIS_URL=redis://127.0.0.1:6379/0
UPLOAD_DIR=$PWD/uploads
NOAI_WATERMARK_DIR=$PWD/data/noai-watermark
REVERSE_SYNTHID_DIR=$PWD/data/reverse-SynthID
EXIFTOOL_PATH=/usr/bin/exiftool
PIXEL_REMOTE_KEY=$PIXEL_KEY
PIXEL_REMOTE_ENFORCE=1
EOF
say "local key: $PIXEL_KEY"

# --- 6. Start redis + app + worker ----------------------------------------------
redis-server --daemonize yes 2>/dev/null || service redis-server start
sleep 1
nohup uvicorn app.main:app --host 0.0.0.0 --port 8000 > /tmp/uvicorn.log 2>&1 &
nohup celery -A app.core.celery worker --loglevel=info -Q pixel_removal,default > /tmp/celery.log 2>&1 &

# --- 7. Health -------------------------------------------------------------------
for i in $(seq 1 30); do
  curl -fsS -H "x-pixel-key: $PIXEL_KEY" http://127.0.0.1:8000/api/v1/health > /tmp/mmhealth.json && break
  sleep 2
done
python3 -c "
import json
h = json.load(open('/tmp/mmhealth.json'))
print('synthid_available: ', h.get('synthid_available'))
print('ctrlregen_available:', h.get('ctrlregen_available'))
"

say "GPU backend is up on :8000 — starting Cloudflare tunnel..."
ARCH="$(uname -m | sed 's/x86_64/amd64/; s/aarch64/arm64/')"
if ! command -v cloudflared >/dev/null 2>&1; then
  curl -fsSL -o /usr/local/bin/cloudflared "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-$ARCH"
  chmod +x /usr/local/bin/cloudflared
fi
cloudflared tunnel --url http://127.0.0.1:8000 2>&1 | tee /tmp/tunnel.log | sed 's|https://[a-z0-9-]*\.trycloudflare\.com|&  <-- COPY THIS URL|'