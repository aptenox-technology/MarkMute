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
