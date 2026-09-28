"""Central configuration for zero-cost and optional paid providers."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


class ConfigError(RuntimeError):
    """Raised when required configuration is missing or invalid."""


def _require(key: str) -> str:
    value = os.getenv(key, "").strip()
    if not value:
        raise ConfigError(f"Missing required environment variable '{key}'. Copy .env.example to .env.")
    return value


def _int(key: str, default: int) -> int:
    try:
        return int(os.getenv(key, "").strip() or default)
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    # Free/default provider configuration
    gemini_api_key: str
    gemini_model: str
    image_provider: str
    pollinations_api_key: str
    pollinations_model: str
    image_width: int
    image_height: int

    # Optional Vertex configuration, only required for animation mode.
    credentials_path: str
    gcp_project_id: str
    gcp_location: str
    gcs_staging_bucket: str
    imagen_generate_model: str
    imagen_capability_model: str
    veo_model: str

    # Tuning
    scene_count: int
    video_seconds: int
    retry_max_attempts: int
    retry_base_delay: int
    log_level: str

    @staticmethod
    def load() -> "Settings":
        creds = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
        if creds:
            if not Path(creds).is_file():
                raise ConfigError(f"GOOGLE_APPLICATION_CREDENTIALS points to a missing file: {creds}")
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = creds

        return Settings(
            gemini_api_key=os.getenv("GEMINI_API_KEY", "").strip(),
            gemini_model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip(),
            image_provider=os.getenv("IMAGE_PROVIDER", "pollinations").strip().lower(),
            pollinations_api_key=os.getenv("POLLINATIONS_API_KEY", "").strip(),
            pollinations_model=os.getenv("POLLINATIONS_MODEL", "flux").strip(),
            image_width=_int("IMAGE_WIDTH", 1280),
            image_height=_int("IMAGE_HEIGHT", 720),
            credentials_path=creds,
            gcp_project_id=os.getenv("GCP_PROJECT_ID", "").strip(),
            gcp_location=os.getenv("GCP_LOCATION", "us-central1").strip(),
            gcs_staging_bucket=os.getenv("GCS_STAGING_BUCKET", "").strip(),
            imagen_generate_model=os.getenv("IMAGEN_GENERATE_MODEL", "imagen-3.0-generate-002").strip(),
            imagen_capability_model=os.getenv("IMAGEN_CAPABILITY_MODEL", "imagen-3.0-capability-001").strip(),
            veo_model=os.getenv("VEO_MODEL", "veo-2.0-generate-001").strip(),
            scene_count=_int("SCENE_COUNT", 5),
            video_seconds=_int("VIDEO_SECONDS", 5),
            retry_max_attempts=_int("RETRY_MAX_ATTEMPTS", 4),
            retry_base_delay=_int("RETRY_BASE_DELAY", 3),
            log_level=os.getenv("LOG_LEVEL", "INFO").strip().upper(),
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings.load()


settings = get_settings()


@lru_cache(maxsize=1)
def init_vertex() -> None:
    """Initialize Vertex only when the optional paid animation path is used."""
    if not settings.gcp_project_id:
        raise ConfigError(
            "Vertex AI is not configured. Use --video-mode slideshow for zero-cost mode, "
            "or configure GCP_PROJECT_ID and credentials for animation mode."
        )
    import vertexai
    vertexai.init(project=settings.gcp_project_id, location=settings.gcp_location)
