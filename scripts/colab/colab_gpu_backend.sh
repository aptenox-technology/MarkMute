#!/usr/bin/env bash
# =============================================================================
# MarkMute — free GPU backend for Google Colab (T4 for free, zero cost)
#
# Runs the full app+worker+redis stack natively (no Docker on Colab) with the
# pinned upstream backends, then exposes it through a free Cloudflare Quick
# Tunnel and SELF-REGISTERS with the public app — no manual env updates or
# redeploys when the tunnel URL rotates. The public app stores the
# registration for ~12 h (PIXEL_REGISTRY_TTL) in its Redis registry
# (Upstash free tier); when the Colab session expires, /api/v1/health just
# reports pixel_remote: null until the next session registers.
#
# Optional hardening: set a shared token on the public app
# (PIXEL_REGISTER_TOKEN):
#   !PIXEL_REGISTER_TOKEN=mysharedtoken bash scripts/colab/colab_gpu_backend.sh
#
# Usage in a Colab notebook (Runtime -> Change runtime type -> T4 GPU):
#   !git clone --recurse-submodules https://github.com/aptenox-technology/MarkMute.git
#   %cd MarkMute
#   !bash scripts/colab/colab_gpu_backend.sh
# (Already cloned without --recurse-submodules? Just re-run the script — it
#  fetches the submodule itself.)
#
# Sessions last up to ~12 h on the free tier — restart the cell anytime.
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
apt-get install -y -qq redis-server exiftool libmagic1 curl >/dev/null

# --- 2a. Python: the pinned research deps (transformers 4.37.2, safetensors
# 0.4.3, numpy 2.5/opencv 5) only have wheels through Python 3.12. Modern hosts
# ship 3.13/3.14, so provision a 3.12 runtime: use a system python3.12 when
# present (Colab), otherwise bootstrap an isolated .venv via uv. ---
PY_BIN="$(command -v python3.12 || true)"
if [ -z "$PY_BIN" ]; then
  if [ -x .venv/bin/python ]; then
    PY_BIN="$PWD/.venv/bin/python"
  else
    say "no python3.12 on PATH — bootstrapping an isolated 3.12 venv via uv"
    if ! command -v uv >/dev/null 2>&1; then
      curl -LsSf https://astral.sh/uv/install.sh | INSTALLER_NO_MODIFY_PATH=1 sh >/dev/null 2>&1 \
        || { echo "uv install failed — install python3.12 manually and re-run" >&2; exit 1; }
      export PATH="$HOME/.local/bin:$PATH"
    fi
    uv venv .venv --python 3.12 -q
    PY_BIN="$PWD/.venv/bin/python"
  fi
else
  # python3.12 is on PATH natively (Colab, etc.) — pip expected, no uv needed
  :
fi
# A .venv built by modern uv has NO pip — uv pip handles installs in that case;
# make sure uv exists whenever .venv is in play (a fresh shell PATH may lack it).
if [ -d .venv ] && ! command -v uv >/dev/null 2>&1; then
  say "installing uv (needed to install packages into the pip-less .venv)..."
  curl -LsSf https://astral.sh/uv/install.sh | INSTALLER_NO_MODIFY_PATH=1 sh >/dev/null 2>&1 \
    || { echo "uv install failed" >&2; exit 1; }
  export PATH="$HOME/.local/bin:$PATH"
fi
if [ -d .venv ]; then
  # uv venv does not seed pip anymore — use uv's own installer for the venv.
  PIP() { uv pip install --python .venv/bin/python -q "$@"; }
else
  PIP() { "$PY_BIN" -m pip install -q "$@"; }
fi
say "using python: $PY_BIN ($("$PY_BIN" -c 'import sys; print(sys.version.split()[0])'))"

# --- 2b. Upstream toolkit submodule (missing after a plain `git clone`) ----------
REQ_DIR="upstream/watermarks-remover/skills/remove-ai-marks/scripts"
if [ ! -f "$REQ_DIR/requirements-ctrlregen.txt" ]; then
  say "fetching upstream toolkit submodule..."
  git submodule update --init --recursive
fi

# --- 3. Python deps (Colab already ships CUDA torch — keep it) ------------------
PIP install -r requirements.txt \
    -r upstream/watermarks-remover/skills/remove-ai-marks/scripts/requirements-ctrlregen.txt \
    -r upstream/watermarks-remover/skills/remove-ai-marks/scripts/requirements-synthid-scorer.txt
# torch is never pinned in the requirements (kept out to avoid CUDA wheels on
# Colab); install it from the CPU index so CPU-only boxes work too.
"$PY_BIN" -c 'import torch' >/dev/null 2>&1 || \
  PIP --index-url https://download.pytorch.org/whl/cpu "torch==2.4.1" "torchvision==0.19.1"

# --- 4. Provision upstream backends at pinned commits ---------------------------
mkdir -p data downloads
# GitHub clones over HTTP/2 can drop mid-stream on Colab — fall back to
# HTTP/1.1 and retry until a checkpoint passes.
if ! git config --global http.version >/dev/null 2>&1; then
  git config --global http.version HTTP/1.1
fi
git config --global http.postBuffer 524288000 || true

provision() { # $1=dir $2=repo $3=ref
  local dir="$1" repo="$2" ref="$3"
  if { [ -f "$dir/.mm-pinned" ] || git -C "$dir" cat-file -e "$ref^{commit}" 2>/dev/null; } && [ -n "$(ls -A "$dir" 2>/dev/null)" ]; then
    say "checkout ok at pinned ref: $dir"
    return
  fi
  rm -rf "$dir"
  for attempt in 1 2 3; do
    say "cloning $repo (attempt $attempt/3)..."
    if git clone --quiet "$repo" "$dir" && git -C "$dir" checkout --quiet "$ref"; then
      say "cloned at $ref"
      return
    fi
    rm -rf "$dir"
    sleep 5
  done
  say "full clone kept failing — falling back to a shallow fetch of the exact pinned commit..."
  git init --quiet "$dir"
  git -C "$dir" remote add origin "$repo"
  if git -C "$dir" fetch --quiet --depth 1 --no-tags origin "$ref" \
      && git -C "$dir" checkout --quiet FETCH_HEAD; then
    say "shallow checkout at $ref"
    return
  fi
  rm -rf "$dir"
  say "git protocol blocked — falling back to a tarball download of the exact pinned commit..."
  # codeload.github.com uses a different edge than the git protocol, so tarball
  # downloads usually survive the flaky Colab→GitHub connections.
  local owner repo_name
  owner="${repo#https://github.com/}"; owner="${owner%%/*}"
  repo_name="${repo#https://github.com/}"; repo_name="${repo_name#*/}"; repo_name="${repo_name%%.git}"
  mkdir -p "$dir"
  tmp_tar="$(mktemp)"
  if [ ! -f "$dir/.mm-pinned" ] && curl -fsSL --connect-timeout 20 --retry 5 \
        -o "$tmp_tar" "https://codeload.github.com/$owner/$repo_name/tar.gz/$ref" \
      && tar -xzf "$tmp_tar" -C "$dir" --strip-components=1; then
    touch "$dir/.mm-pinned"
    rm -f "$tmp_tar"
    say "tarball checkout at $ref"
    return
  fi
  rm -f "$tmp_tar"
  rm -rf "$dir"
  echo "failed to provision $repo at $ref — check connectivity and re-run" >&2
  exit 1
}
provision "data/noai-watermark"  "$NOAI_REPO"   "$NOAI_REF"
provision "data/reverse-SynthID" "$SYNTHID_REPO" "$SYNTHID_REF"

# --- 5. Env ---------------------------------------------------------------------
PIXEL_KEY="$(openssl rand -hex 12 2>/dev/null || "$PY_BIN" -c 'import secrets; print(secrets.token_hex(12))')"
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
# Preemptively drop leftovers from prior runs — a stuck uvicorn holding :8000
# makes the fresh one bind-fail and shut right back down (the pattern we saw).
pkill -9 -f "uvicorn app.main:app" 2>/dev/null || true
pkill -9 -f "celery -A app.core.celery" 2>/dev/null || true
sleep 1
# Robust redis start (idempotent; safe to re-run the script).
redis-cli -h 127.0.0.1 ping >/dev/null 2>&1 || redis-server --daemonize yes
sleep 1
nohup "$PY_BIN" -m uvicorn app.main:app --host 0.0.0.0 --port 8000 > /tmp/uvicorn.log 2>&1 &
nohup "$PY_BIN" -m celery -A app.core.celery worker --loglevel=info -Q pixel_removal,default > /tmp/celery.log 2>&1 &

# --- 7. Warm up (first request after a Colab kernel boot can be slow) ------------
sleep 2
curl -fsS -H "x-pixel-key: $PIXEL_KEY" http://127.0.0.1:8000/api/v1/health > /dev/null \
  && echo "GPU backend warmed up" || echo "warmup ping failed (uvicorn may still be starting)"

# --- 8. Health -------------------------------------------------------------------
for i in $(seq 1 30); do
  curl -fsS -H "x-pixel-key: $PIXEL_KEY" http://127.0.0.1:8000/api/v1/health > /tmp/mmhealth.json && break
  sleep 2
done
"$PY_BIN" -c "
import json
h = json.load(open('/tmp/mmhealth.json'))
print('synthid_available: ', h.get('synthid_available'))
print('ctrlregen_available:', h.get('ctrlregen_available'))
"

say "GPU backend is up on :8000 — starting Cloudflare tunnel..."
if ! command -v cloudflared >/dev/null 2>&1; then
  say "installing cloudflared..."
  # Try pip (PyPI wheel bundles the binary) first, then the GitHub binary.
  if ! PIP install cloudflared 2>/dev/null || ! command -v cloudflared >/dev/null 2>&1; then
    ARCH="$(uname -m | sed 's/x86_64/amd64/; s/aarch64/arm64/')"
    curl -fsSL --connect-timeout 20 --retry 5 \
      -o /usr/local/bin/cloudflared "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-$ARCH"
    chmod +x /usr/local/bin/cloudflared
  fi
fi
command -v cloudflared >/dev/null 2>&1 || { echo "cloudflared install failed" >&2; exit 1; }
nohup cloudflared tunnel --url http://127.0.0.1:8000 > /tmp/tunnel.log 2>&1 &
echo "waiting for tunnel URL..."

# --- 9. Grab the tunnel URL and self-register with the public app ----------------
TUNNEL_URL=""
for i in $(seq 1 60); do
  TUNNEL_URL="$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' /tmp/tunnel.log | head -1 || true)"
  [ -n "$TUNNEL_URL" ] && break
  sleep 2
done
[ -n "$TUNNEL_URL" ] || { echo "tunnel URL not found in /tmp/tunnel.log"; exit 1; }
say "tunnel: $TUNNEL_URL"

REGISTER_URL="${PIXEL_REGISTER_URL:-https://markmute.vercel.app}"
TOKEN_JSON=""
[ -n "${PIXEL_REGISTER_TOKEN:-}" ] && TOKEN_JSON=",\"token\":\"$PIXEL_REGISTER_TOKEN\""
REG_RESULT="$(curl -fsS -X POST "$REGISTER_URL/api/v1/pixel/register" \
  -H 'content-type: application/json' \
  -d "{\"url\":\"$TUNNEL_URL\",\"key\":\"$PIXEL_KEY\"$TOKEN_JSON}" || echo 'REGISTER FAILED')"
say "registration: $REG_RESULT"
echo "Your quick Tunnel is live at: $TUNNEL_URL  (registered with $REGISTER_URL)"

# --- 10. Watchdog: hold the cell and restart any service that dies ----------------
# Individual crashes (uvicorn/celery/redis/tunnel) are healed in <25s yourself-free.
# Liveness = the service actually answers, not just "a process with that command
# exists" — stuck/dying processes (zombies, half-shutdown) fool pgrep and made
# uvicorn/celery stay dead while the watchdog "saw" them alive.
_http_code() { curl -s -o /dev/null -m 3 -w '%{http_code}' "$1"; }
# A tunnel is only healthy when the ORIGIN answered (guard replies 200/403).
# Edge-level errors (530/521/522/502/...) mean cloudflared can't reach us.
_tunnel_ok() {
  local c
  c="$(_http_code "$1/api/v1/health")"
  [ "$c" = "200" ] || [ "$c" = "403" ]
}

watchdog() {
  # --- uvicorn: once twice-unhealthy with a live process, it's stuck: kill -9 ---
  local code pcount
  code="$(_http_code http://127.0.0.1:8000/api/v1/health)"
  pcount="$(pgrep -f "uvicorn app.main:app" | wc -l | tr -d ' ')"
  echo "$(date -u +%T) uvicorn check: code=$code pgrep=$pcount" >> /tmp/watchdog.log
  if [ "$code" != "000" ]; then
    rm -f /tmp/.uvicorn-unhealthy
  elif pgrep -f "uvicorn app.main:app" >/dev/null 2>&1; then
    if [ -f /tmp/.uvicorn-unhealthy ]; then
      echo "$(date -u +%T) uvicorn stuck (no listener) — killing and restarting" >> /tmp/watchdog.log
      pkill -9 -f "uvicorn app.main:app" 2>/dev/null || true
      sleep 1
      nohup "$PY_BIN" -m uvicorn app.main:app --host 0.0.0.0 --port 8000 >> /tmp/uvicorn.log 2>&1 &
      rm -f /tmp/.uvicorn-unhealthy
    else
      touch /tmp/.uvicorn-unhealthy   # first miss may just be a slow startup
    fi
  else
    echo "$(date -u +%T) uvicorn restarted (missing)" >> /tmp/watchdog.log
    nohup "$PY_BIN" -m uvicorn app.main:app --host 0.0.0.0 --port 8000 >> /tmp/uvicorn.log 2>&1 &
  fi

  # --- celery: pgrep zombies could match forever; drop them first ---
  local cpid
  cpid="$(pgrep -f "celery -A app.core.celery" | head -1 || true)"
  if [ -n "$cpid" ] && [ "$(ps -o stat= -p "$cpid" 2>/dev/null | tr -d ' ')" = "Z" ]; then
    kill -9 "$cpid" 2>/dev/null || true
    cpid=""
  fi
  if [ -z "$cpid" ]; then
    nohup "$PY_BIN" -m celery -A app.core.celery worker --loglevel=info -Q pixel_removal,default >> /tmp/celery.log 2>&1 &
    echo "$(date -u +%T) celery restarted (missing/zombie)" >> /tmp/watchdog.log
  fi

  # --- redis ---
  redis-cli -h 127.0.0.1 ping >/dev/null 2>&1 || {
    pkill -9 -f redis-server 2>/dev/null || true
    sleep 1
    redis-server --daemonize yes
  }

  # Tunnel dies independent of the app (cloudflared quits, edge flakes) — the
  # registered URL goes stale and the public app gets 530. Detect it and bring
  # up a fresh tunnel, then re-register so the app still routes to us.
  TUNNEL_URL="$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' /tmp/tunnel.log | head -1 || true)"
  if [ -n "$TUNNEL_URL" ] && _tunnel_ok "$TUNNEL_URL"; then
    : # tunnel healthy (403/200 both fine — the guard answers with 403 on bad keys)
  else
    echo "$(date -u +%T) tunnel unhealthy ($TUNNEL_URL) — relaunching..." >> /tmp/watchdog.log
    pkill -f cloudflared 2>/dev/null || true
    sleep 2
    nohup cloudflared tunnel --url http://127.0.0.1:8000 > /tmp/tunnel.log 2>&1 &
    NEW_URL=""
    for i in $(seq 1 60); do
      NEW_URL="$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' /tmp/tunnel.log | head -1 || true)"
      [ -n "$NEW_URL" ] && break
      sleep 2
    done
    if [ -n "$NEW_URL" ] && _tunnel_ok "$NEW_URL"; then
      REGISTER_URL="${PIXEL_REGISTER_URL:-https://markmute.vercel.app}"
      TOKEN_JSON=""
      [ -n "${PIXEL_REGISTER_TOKEN:-}" ] && TOKEN_JSON=",\"token\":\"$PIXEL_REGISTER_TOKEN\""
      if curl -fsS -m 10 -X POST "$REGISTER_URL/api/v1/pixel/register" \
          -H 'content-type: application/json' \
          -d "{\"url\":\"$NEW_URL\",\"key\":\"$PIXEL_KEY\"$TOKEN_JSON}" >/dev/null 2>&1; then
        echo "$(date -u +%T) re-registered: $NEW_URL" >> /tmp/watchdog.log
      else
        echo "$(date -u +%T) re-registration failed" >> /tmp/watchdog.log
      fi
    else
      echo "$(date -u +%T) new tunnel unhealthy — retrying next cycle" >> /tmp/watchdog.log
    fi
  fi
}
echo "watchdog active — services auto-restart (app, worker, redis, tunnel) on crash; keep this tab open."
while true; do
  watchdog
  sleep 15
done