#!/usr/bin/env bash
# =============================================================================
# MarkMute — GPU VPS deploy script (CtrlRegen pixel removal + SynthID scoring)
#
# Brings up the full stack (app + worker + redis) on a GPU server, provisioning
# the upstream backends at their pinned commits and building the GPU image
# (aptenox/markmute-gpu) locally on the host.
#
# Requires: Ubuntu/Debian (or similar) with root/sudo, a NVIDIA GPU, and
# internet access. Idempotent — safe to re-run.
#
# Usage:  sudo bash scripts/deploy-gpu-vps.sh
# =============================================================================
set -euo pipefail

NOAI_REF="b642ae45d20eded52c96d570985eb4e3e427aac8"     # mertizci/noai-watermark
SYNTHID_REF="b11083676fd3ee3ff97ce9d03c0e409e46905902"    # aloshdenny/reverse-SynthID
NOAI_REPO="https://github.com/mertizci/noai-watermark.git"
SYNTHID_REPO="https://github.com/aloshdenny/reverse-SynthID.git"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATA_DIR="$ROOT/data"
UID_APP=1000

say()  { printf '\n\033[1;34m==>\033[0m %s\n' "$*"; }
fail() { printf '\n\033[1;31mERROR:\033[0m %s\n' "$*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || fail "run as root (sudo bash scripts/deploy-gpu-vps.sh)"

# --- 1. GPU present? ----------------------------------------------------------
command -v nvidia-smi >/dev/null 2>&1 || fail "nvidia-smi not found — install the NVIDIA driver"
say "GPU detected:"
nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader | head -1

# --- 2. Docker + nvidia-container-toolkit -------------------------------------
if ! command -v docker >/dev/null 2>&1; then
  say "Installing Docker Engine..."
  curl -fsSL https://get.docker.com | sh
fi
if ! docker info --format '{{.Name}}' >/dev/null 2>&1; then
  fail "docker daemon not reachable — start it and retry"
fi

if ! docker info 2>/dev/null | grep -qi "Runtimes:.*nvidia"; then
  say "Installing nvidia-container-toolkit..."
  curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey \
    | gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
  curl -fsSL https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list \
    | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' \
    > /etc/apt/sources.list.d/nvidia-container-toolkit.list
  apt-get update -qq && apt-get install -y -qq nvidia-container-toolkit
  nvidia-ctk runtime configure --runtime=docker
  systemctl restart docker
  say "nvidia-container-toolkit installed; docker restarted"
fi

# --- 3. Provision upstream backends at pinned commits -------------------------
mkdir -p "$DATA_DIR"
git config --global http.version HTTP/1.1 2>/dev/null || true
git config --global http.postBuffer 524288000 || true

provision() { # $1=dir  $2=repo  $3=ref
  local dir="$1" repo="$2" ref="$3"
  if [ -d "$dir/.git" ] && git -C "$dir" cat-file -e "$ref^{commit}" 2>/dev/null; then
    say "checkout ok at pinned ref: $dir"
    chown -R "$UID_APP":"$UID_APP" "$dir" || true
    return
  fi
  rm -rf "$dir"
  for attempt in 1 2 3; do
    say "cloning $repo (attempt $attempt/3)..."
    if git clone --quiet "$repo" "$dir" && git -C "$dir" checkout --quiet "$ref"; then
      chown -R "$UID_APP":"$UID_APP" "$dir" || true
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
      && git -C "$dir" checkout --quiet FETCH_HEAD \
      && git -C "$dir" cat-file -e "$ref^{commit}" >/dev/null 2>&1; then
    chown -R "$UID_APP":"$UID_APP" "$dir" || true
    say "shallow checkout at $ref"
    return
  fi
  rm -rf "$dir"
  fail "could not provision $repo at $ref"
}

provision "$DATA_DIR/noai-watermark"  "$NOAI_REPO"   "$NOAI_REF"
provision "$DATA_DIR/reverse-SynthID" "$SYNTHID_REPO" "$SYNTHID_REF"
say "Backends provisioned in $DATA_DIR"

# --- 4. Env --------------------------------------------------------------------
if [ ! -f "$ROOT/.env" ]; then
  cp "$ROOT/.env.example" "$ROOT/.env"
  say "Created $ROOT/.env from example — review it (LLM rewrite keys etc.)"
fi

# --- 5. Build GPU image + bring up the stack ------------------------------------
cd "$ROOT"
COMPOSE="docker compose -f docker-compose.yml -f docker-compose.gpu.yml"

say "Building aptenox/markmute-gpu (torch+CUDA — several minutes)..."
$COMPOSE build worker

say "Starting stack: $COMPOSE up -d --build"
$COMPOSE up -d --build

# --- 6. Health check ------------------------------------------------------------
for i in $(seq 1 30); do
  if curl -fsS http://localhost:8000/api/v1/health >/tmp/mmhealth.json 2>/dev/null; then
    break
  fi
  [ "$i" -eq 30 ] && fail "app did not become healthy: docker compose logs app"
  sleep 2
done

say "Health:"
python3 - <<'EOF'
import json
h = json.load(open("/tmp/mmhealth.json"))
for k in ("synthid_available", "ctrlregen_available"):
    print(("  {:<22} {}").format(k, h.get(k, "?")))
EOF

grep -q '"ctrlregen_available": *true' /tmp/mmhealth.json \
  && grep -q '"synthid_available": *true' /tmp/mmhealth.json \
  && say "GPU backends ONLINE — open http://localhost:8000 and run a Files/Images job." \
  || fail "backends not online — check: docker compose -f docker-compose.yml -f docker-compose.gpu.yml logs worker"