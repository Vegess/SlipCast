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

    # Sign in with Google / GitHub. A provider's button only appears when both its values are set.
    google_client_id: str = ""
    google_client_secret: str = ""
    github_client_id: str = ""
    github_client_secret: str = ""
    # Where the web app lives (sign-in and invite links point here) and, optionally, the API's
    # own public URL. Without PUBLIC_API_URL it is worked out from the request (proxy-aware).
    public_web_url: str = "http://localhost:4200"
    public_api_url: str = ""
    invite_days: int = 7

    # Optional LLM advice layer. Without a key, rule-based advice is used everywhere.
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"
    groq_url: str = "https://api.groq.com/openai/v1/chat/completions"
    advice_per_minute: int = 6
    advice_per_day: int = 100

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    def validate_for_production(self) -> None:
        if self.environment == "production" and self.jwt_secret == DEFAULT_SECRET:
            raise RuntimeError("JWT_SECRET must be set in production")


@lru_cache
def get_settings() -> Settings:
    return Settings()
