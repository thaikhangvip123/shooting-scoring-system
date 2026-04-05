"""
backend/config.py
All application settings loaded from environment variables.
Copy .env.example → .env and fill in your values.
"""

from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # ── Server ────────────────────────────────────────────────────────────────
    app_name:    str  = "Shooting Scoring System"
    app_version: str  = "1.0.0"
    debug:       bool = False
    host:        str  = "0.0.0.0"
    port:        int  = 8000

    # ── Firebase ──────────────────────────────────────────────────────────────
    firebase_creds_path: str  = "serviceAccountKey.json"
    firebase_db_url:     str  = ""          # e.g. https://your-project.firebaseio.com
    use_firebase:        bool = True        # set False to use in-memory store

    # ── Target geometry ───────────────────────────────────────────────────────
    target_radius_mm: float = 225.0        # outermost ring radius
    rings_mm: list[float] = [              # ring boundary radii (inner → outer)
        11.25, 22.5, 45.0, 67.5, 90.0,
        112.5, 135.0, 157.5, 180.0, 202.5, 225.0
    ]

    # ── Duplicate detection ───────────────────────────────────────────────────
    duplicate_min_mm:  float = 2.0         # min mm distance between two shots
    duplicate_max_ms:  int   = 500         # time window for duplicate check

    # ── CORS ──────────────────────────────────────────────────────────────────
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:5173"]

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache
def get_settings() -> Settings:
    return Settings()