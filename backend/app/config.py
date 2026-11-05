from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_SECRET = "change-me-in-production"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "SlipCast"
    environment: str = "development"
    database_url: str = "sqlite:///./slipcast.db"
    auto_create_tables: bool = True

    jwt_secret: str = DEFAULT_SECRET
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 60 * 24

    cors_origins: str = "http://localhost:4200"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    def validate_for_production(self) -> None:
        if self.environment == "production" and self.jwt_secret == DEFAULT_SECRET:
            raise RuntimeError("JWT_SECRET must be set in production")


@lru_cache
def get_settings() -> Settings:
    return Settings()
