from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    bot_token: str = ""
    owner_telegram_id: int = 0
    timezone: str = "Europe/Moscow"
    data_dir: str = "/data"
    database_path: str = "/data/ubot.db"
    log_level: str = "INFO"

    host_agent_url: str = ""
    host_agent_token: str = ""
    healthchecks_url: str = ""

    @property
    def db_path(self) -> Path:
        return Path(self.database_path)

    @property
    def is_configured(self) -> bool:
        return bool(self.bot_token) and self.owner_telegram_id > 0


settings = Settings()
