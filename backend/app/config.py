from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

CACHE_DIR = Path(__file__).resolve().parent.parent / ".cache"
CACHE_DIR.mkdir(exist_ok=True)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    google_maps_api_key: str | None = None

    sac_username: str | None = None
    sac_password: str | None = None

    gipfelbuch_username: str | None = None
    gipfelbuch_password: str | None = None

    cache_ttl_seconds: int = 86400

    @property
    def sac_configured(self) -> bool:
        return bool(self.sac_username and self.sac_password)

    @property
    def gipfelbuch_configured(self) -> bool:
        return bool(self.gipfelbuch_username and self.gipfelbuch_password)


settings = Settings()
