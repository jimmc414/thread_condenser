from pydantic_settings import BaseSettings
from pydantic import AnyUrl, Field, field_validator


class Settings(BaseSettings):
    APP_ENV: str = "dev"
    APP_SECRET: str
    POSTGRES_DSN: AnyUrl
    REDIS_URL: str

    SLACK_BOT_TOKEN: str
    SLACK_SIGNING_SECRET: str
    PUBLIC_BASE_URL: str = "http://localhost:8080"

    M365_TENANT_ID: str | None = None
    M365_CLIENT_ID: str | None = None
    M365_CLIENT_SECRET: str | None = None
    TEAMS_BOT_APP_ID: str | None = None
    TEAMS_BOT_APP_PASSWORD: str | None = None
    GRAPH_NOTIFICATION_SECRET: str | None = None
    OUTLOOK_SHARED_MAILBOXES: list[str] = Field(default_factory=list)

    LLM_PROVIDER: str = "openai"
    OPENAI_API_KEY: str | None = None
    OPENAI_MODEL: str = "gpt-4o-mini"
    LLM_MAX_INPUT_TOKENS: int = 40000
    LLM_MAX_OUTPUT_TOKENS: int = 6000

    WATCH_WINDOW_SECONDS: int = 21600
    PROMOTION_THRESHOLD: float = 0.65

    @field_validator("OUTLOOK_SHARED_MAILBOXES", mode="before")
    @classmethod
    def _split_mailboxes(cls, value: str | list[str] | None) -> list[str] | None:
        if isinstance(value, str):
            return [part.strip() for part in value.split(",") if part.strip()]
        return value

    class Config:
        env_file = ".env"


default_settings: Settings | None = None


def get_settings() -> Settings:
    global default_settings
    if default_settings is None:
        default_settings = Settings()
    return default_settings


settings = get_settings()
