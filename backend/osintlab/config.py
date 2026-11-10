"""Runtime configuration.

All settings can be overridden with ``OSINTLAB_*`` environment variables or a
``.env`` file in the working directory.
"""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="OSINTLAB_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    data_dir: Path = Path.home() / ".local/share/osint-lab"
    database_url: str = ""
    ui_dir: Path | None = None
    user_agent: str = (
        "osint-lab/0.1 (educational OSINT workbench; "
        "+https://github.com/salihsavuran/osint-lab)"
    )
    request_timeout: float = 20.0
    max_retries: int = 2
    offline: bool = False

    @property
    def resolved_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        return f"sqlite:///{self.data_dir / 'osintlab.db'}"

    @property
    def evidence_dir(self) -> Path:
        path = self.data_dir / "evidence"
        path.mkdir(parents=True, exist_ok=True)
        return path


settings = Settings()
settings.data_dir.mkdir(parents=True, exist_ok=True)
