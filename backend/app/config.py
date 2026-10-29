"""Application settings, read from environment variables (or backend/.env)."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

GMAIL_READONLY_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Gemini
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    gemini_timeout_seconds: int = 60
    gemini_max_retries: int = 2

    # Google OAuth
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8000/api/auth/google/callback"

    # App
    database_url: str = "sqlite:///./smart_email.db"
    frontend_origin: str = "http://localhost:5173"
    session_secret: str = ""
    token_encryption_key: str = ""
    session_https_only: bool = False

    # When true, the agent creates suggested tasks automatically (still de-duplicated).
    # When false (default), a task is only created when the user clicks "Create Task".
    auto_create_tasks: bool = False

    # Timezone used to interpret deadlines such as "5 November 2026 at 5 PM" (IANA name).
    user_timezone: str = "UTC"

    # Limits
    max_body_chars_for_ai: int = 20000

    @property
    def google_oauth_configured(self) -> bool:
        return bool(self.google_client_id and self.google_client_secret)


@lru_cache
def get_settings() -> Settings:
    return Settings()
