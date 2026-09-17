"""Runtime configuration loaded from environment variables."""

from dataclasses import dataclass
import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Settings:
    """Settings required by the integration demo."""

    db_path: Path
    lims_result_url: str
    capture_backend: str = "mock"

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            db_path=Path(os.getenv("LIMS_DB_PATH", str(BASE_DIR / "lims_demo.db"))),
            lims_result_url=os.getenv(
                "LIMS_RESULT_URL",
                "http://127.0.0.1:8000/mock/lims/results",
            ),
            capture_backend=os.getenv("CAPTURE_BACKEND", "mock").strip().lower(),
        )
