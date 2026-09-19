"""Central configuration. Loaded once, cached."""
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

# .../quantpulse/backend/app/core/config.py -> quantpulse/
ROOT_DIR = Path(__file__).resolve().parents[3]
load_dotenv(ROOT_DIR / ".env")


@dataclass(frozen=True)
class Settings:
    app_name: str
    app_env: str
    log_level: str
    backend_host: str
    backend_port: int
    frontend_origin: str
    data_dir: Path
    db_path: Path


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings(
        app_name=os.getenv("APP_NAME", "Quantpulse"),
        app_env=os.getenv("APP_ENV", "development"),
        log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        backend_host=os.getenv("BACKEND_HOST", "127.0.0.1"),
        backend_port=int(os.getenv("BACKEND_PORT", "8000")),
        frontend_origin=os.getenv("FRONTEND_ORIGIN", "http://localhost:5173"),
        data_dir=ROOT_DIR / "data",
        db_path=ROOT_DIR / "data" / "quantpulse.db",
    )
