"""Application settings loaded from environment / .env file."""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # App
    APP_NAME: str = "MarkMute"
    APP_TAGLINE: str = "Best-effort watermark, metadata & invisible-trace remover"
    DEBUG: bool = False
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # Limits
    MAX_FILE_SIZE: int = 256 * 1024 * 1024  # 256 MiB uploads
    MAX_INPUT_SIZE: int = 256 * 1024 * 1024  # 256 MiB text payloads

    # Storage
    UPLOAD_DIR: Path = BASE_DIR / "uploads"

    # Redis / Celery (optional — required only for pixel removal / rewrite jobs)
    REDIS_URL: str = "redis://localhost:6379/0"

    # Optional external tools
    EXIFTOOL_PATH: str = "/usr/bin/exiftool"
    C2PATOOL_PATH: str = "/usr/local/bin/c2patool"

    # Optional: SynthID scoring checkout
    REVERSE_SYNTHID_DIR: Path | None = None

    # Optional: CtrlRegen pixel removal checkout
    NOAI_WATERMARK_DIR: Path | None = None

    # Optional: rewrite backends (passed through to the original script's env)
    OPENAI_API_KEY: str | None = None
    ANTHROPIC_API_KEY: str | None = None
    OLLAMA_HOST: str = "http://127.0.0.1:11434"
    WATERMARKS_REWRITE_ALLOW_REMOTE: int = 0
    WATERMARKS_REWRITE_API_KEY: str | None = None
    WATERMARKS_REWRITE_MODEL: str | None = None
    WATERMARKS_REWRITE_BASE_URL: str | None = None

    # Security
    CORS_ORIGINS: str = "http://localhost:8000"

    # Path to the original watermarks-remover scripts
    SCRIPTS_DIR: Path = (
        BASE_DIR
        / "upstream"
        / "watermarks-remover"
        / "skills"
        / "remove-ai-marks"
        / "scripts"
    )

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


settings = Settings()
