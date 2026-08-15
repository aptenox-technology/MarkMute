# MarkMute

A production-ready web application that wraps the
[`watermarks-remover`](https://github.com/guillaumemeyer/watermarks-remover)
Python toolkit into an accessible drag-and-drop interface.

**MarkMute performs best-effort, verifiable removal — it never claims 100%
watermark-free output.**

> This tool is for privacy and hygiene on your own content. Users must adhere
> to local regulations and use responsibly.

## What it does

| Layer | Capability | Original script |
|---|---|---|
| **Text Layer A** | Detect & strip invisible Unicode: ZWSP, bidi controls, tag chars, exotic spaces, confusables | `inspect_text.py`, `clean_text.py` |
| **Text Layer B** | Statistical (token-sampling) watermark rewrite via LLM | `rewrite_text.py` |
| **File metadata** | C2PA / EXIF / XMP / doc-props from PNG, JPEG, WebP, SVG, PDF, DOCX, ODT, HTML, MD | `inspect_file.py`, `clean_file.py` |
| **Image metadata** | Same for images + optional SynthID pixel scoring | `inspect_image.py`, `clean_image.py`, `score_synthid.py` |
| **Pixel removal** | Optional CtrlRegen pixel-watermark removal (GPU, async) | `clean_image.py --remove-pixel ctrlregen` |

The upstream scripts are **reused as-is** via subprocess — the core logic is
never reimplemented. All wrappers parse the scripts' native `--json` output.

## Architecture

```
MarkMute/
├── docker-compose.yml          # app + celery worker + redis
├── Dockerfile
├── requirements.txt
├── .env.example
├── upstream/watermarks-remover # ⬅️ original repo (git submodule)
├── app/
│   ├── main.py                 # FastAPI entry
│   ├── config.py               # Pydantic settings
│   ├── routers/                # text · files · images · tasks
│   ├── services/               # wrappers around the original scripts
│   ├── models/                 # Pydantic schemas + enums
│   ├── core/                   # runner, security, utils, celery
│   └── static/                 # vanilla HTML + Tailwind CDN + JS SPA
├── uploads/                    # runtime dir (gitignored): raw/ cleaned/ backups/
└── tests/                      # API tests + fixtures
```

## Quick start (local)

```bash
git clone --recurse-submodules https://github.com/you/markmute.git
cd markmute

python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env

.venv/bin/uvicorn app.main:app --reload
# → http://localhost:8000  (API docs at /docs)
```

## Quick start (Docker)

```bash
docker compose up --build
# → http://localhost:8000
```

The `worker` service (Celery + Redis) is optional for basic use; it is only
required for async pixel removal (CtrlRegen) and remote LLM rewrites.

## API

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/v1/text/inspect` | Detect invisible Unicode / homoglyphs |
| `POST` | `/api/v1/text/clean` | Strip invisible Unicode |
| `POST` | `/api/v1/text/rewrite` | Layer-B rewrite via LLM (`print-prompt`, `ollama`, `openai-compatible`) |
| `POST` | `/api/v1/files/upload` | Upload a file (PNG/JPEG/WebP/SVG/PDF/DOCX/ODT/HTML/MD/TXT) |
| `POST` | `/api/v1/files/inspect/{id}` | Inspect metadata / C2PA / AI traces |
| `POST` | `/api/v1/files/clean/{id}` | Clean metadata, return download URL |
| `GET`  | `/api/v1/files/download/{id}` | Download cleaned file |
| `POST` | `/api/v1/images/upload` | Upload an image |
| `POST` | `/api/v1/images/inspect/{id}` | Inspect image |
| `POST` | `/api/v1/images/clean/{id}` | Clean image metadata |
| `POST` | `/api/v1/images/score/{id}` | SynthID pixel score (if configured) |
| `POST` | `/api/v1/images/remove-pixel/{id}` | Start async CtrlRegen removal → task_id |
| `GET`  | `/api/v1/tasks/{id}` | Poll async task status |
| `GET`  | `/api/v1/health` | Status incl. optional backend availability |

Interactive docs: `http://localhost:8000/docs`.

## Configuration (`.env`)

See [`.env.example`](.env.example). Notable knobs:

- `UPLOAD_DIR` — where uploads/cleaned files are stored
- `MAX_FILE_SIZE` / `MAX_INPUT_SIZE` — size limits
- `REVERSE_SYNTHID_DIR` — path to the reverse-SynthID checkout (optional)
- `NOAI_WATERMARK_DIR` — path to the CtrlRegen checkout (optional, GPU)
- `REDIS_URL` — broker for Celery async jobs (optional)
- `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` / `OLLAMA_HOST` — Layer-B rewrite backends

## Optional backends

| Backend | Install | Env var |
|---|---|---|
| SynthID scorer | `setup_synthid.sh` (upstream) + clone at pinned commit | `REVERSE_SYNTHID_DIR` |
| CtrlRegen pixel removal | `setup_ctrlregen.sh` (upstream) + clone at pinned commit | `NOAI_WATERMARK_DIR` |
| Ollama rewrite | run `ollama serve` | `OLLAMA_HOST` |
| OpenAI-compatible rewrite | any API key | `WATERMARKS_REWRITE_API_KEY`, `WATERMARKS_REWRITE_MODEL`, `WATERMARKS_REWRITE_BASE_URL` |

Note: rewrite calls an external LLM only when a real backend (not
`print-prompt`) is chosen — the UI confirms before sending text to a remote
service, and `WATERMARKS_REWRITE_ALLOW_REMOTE=0` denies non-loopback endpoints
unless explicitly allowed.

## Design notes

- **Subprocess over import** — the original scripts are CLI-first and
  security-hardened; subprocess preserves their stdin/stdout, arg parsing,
  exit codes and binary-refusal behavior.
- **`--json` everywhere** — the scripts emit structured JSON, so wrappers
  parse output instead of scraping human text.
- **Resource limits** — every subprocess gets `RLIMIT_AS`/`RLIMIT_FSIZE`
  (POSIX; macOS skips `RLIMIT_AS` where lowering is unsupported).
- **Binary defense in depth** — uploads are size-limited, extension-checked
  and magic-byte sniffed; the original scripts add their own refusal guards.
- **Celery for pixel removal** — CtrlRegen takes minutes per image; async
  tasks prevent HTTP timeouts.
- **Exit-code semantics** — inspect scripts exit `1` on suspicious content
  (a valid result, not an error); `clean_file.py` exits `1` when residual
  C2PA/AI signals remain (best-effort — file is still written).

## Deployment

### Vercel (current production)

Live at <https://markmute.vercel.app>. Vercel runs the FastAPI app natively
(Python service) via `vercel.json` + `pyproject.toml`:

```bash
npx vercel login
npx vercel --prod --yes
```

Env vars (set in the Vercel dashboard or `vercel env add`):
`MAX_FILE_SIZE` (Vercel caps function bodies at ~4.5 MB → 4194304),
`CORS_ORIGINS`, `OPENAI_API_KEY` / `OLLAMA_HOST` (optional rewrite).

Vercel caveats: uploads go to `/tmp` (ephemeral), SynthID/CtrlRegen and the
Celery worker are unavailable — the health pills report this honestly.

### Render (PaaS, easiest)

1. Push this repo to GitHub/GitLab
2. Render dashboard → **New → Web Service** → connect repo → runtime **Docker**
3. Set env vars (see `.env.example`; at minimum `UPLOAD_DIR` on a persistent disk)
4. Add a persistent **Disk** mounted at your `UPLOAD_DIR` (uploads must survive restarts)
5. Optional: create a Redis instance → set `REDIS_URL` (needed only for async pixel removal)
6. For Blueprint deploys, copy [`render.yaml`](render.yaml) to the repo root

`render.yaml` is included as reference — Render auto-detects it.

### Railway

1. **New Project** → **Deploy from GitHub** → select repo
2. Railway detects the Dockerfile automatically
3. Add volumes to `UPLOAD_DIR` via the service's **Volumes** tab
4. Add a Redis plugin and set `REDIS_URL`

### VPS / Docker (full control)

```bash
# GPU-less host (everything except pixel removal):
docker compose up -d --build

# GPU host (Linux + nvidia-container-toolkit): full backend incl. CtrlRegen
# pixel removal + SynthID scoring. One command provisions the upstream
# checkouts at their pinned commits, builds the GPU image and brings up the
# stack (run as root):
sudo bash scripts/deploy-gpu-vps.sh

# ...or manually:
mkdir -p data && git clone --quiet https://github.com/.../noai-watermark data/noai-watermark
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d --build
```

Behind a reverse proxy (Caddy/nginx) point at `127.0.0.1:8000`. Make sure
`CORS_ORIGINS` includes your domain.

### GPU backend notes

- The GPU image (`Dockerfile.gpu` → `aptenox/markmute-gpu`) bakes in the pip
  deps only (torch==2.4.1 CUDA 12.4 wheels typed at build time; the pinned
  `requirements-ctrlregen.txt` / `requirements-synthid-scorer.txt`). The
  upstream repos themselves are **not** bundled — they are cloned at pinned,
  immutable SHA-1 commits into `data/` and bind-mounted to
  `/opt/noai-watermark` and `/opt/reverse-SynthID`, where the scripts import
  them (`sys.path` at runtime). Pinning SHA-1s (rather than branch names)
  makes every provision reproducible.
- The worker runs the pixel jobs (`--ctrlregen-device cuda`, 20 steps,
  strength 0.7); the app image doesn't need the GPU.
- Validate the stack at `/api/v1/health` — both `ctrlregen_available` and
  `synthid_available` must read `true`; only then do the UI pills show
  sparse-block removal and SynthID scoring as available.

### Notes

- Uploads live in `UPLOAD_DIR` — always attach persistent storage; cleaned
  files are only useful if they survive restarts.
- The Celery worker (`worker` service) is optional unless you use async
  pixel removal (CtrlRegen). The `app` service works standalone.
- SynthID scoring and CtrlRegen removal require the backend checkouts to be
  installed into the mounted directories (see Optional backends above) —
  `/api/v1/health` reports honestly when they're missing.

## Tests

```bash
.venv/bin/pip install pytest httpx
.venv/bin/python -m pytest tests/ -q
```

## License & ethics

- **Code:** MIT (same as upstream). The submodule at
  `upstream/watermarks-remover` remains under its own MIT license.
- **Usage:** for content you own or are authorized to process only.
- **Claims:** MarkMute reports *verifiable removal* and *best-effort*
  results — it never certifies "100% watermark-free".
