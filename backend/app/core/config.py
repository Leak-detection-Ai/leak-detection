from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "LeakGuard"
    app_env: str = "development"

    api_host: str = "0.0.0.0"
    api_port: int = 8000

    frontend_origin: str = "http://localhost:5173"

    database_url: str

    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 15
    refresh_token_days: int = 30

    token_encryption_key: str
    csrf_secret: str

    cookie_secure: bool = False
    cookie_samesite: str = "lax"

    rate_limit_per_minute: int = 120
    max_upload_mb: int = 5
    social_sync_interval_seconds: int = 60

    mastodon_instance: str = "https://mastodon.social"
    mastodon_client_name: str = "LeakGuard"
    mastodon_client_website: str = "http://localhost:5173"

    mastodon_client_id: str | None = None
    mastodon_client_secret: str | None = None

    mastodon_redirect_uri: str = (
        "http://localhost:8000/api/oauth/mastodon/callback"
    )

    mastodon_scopes: str = "read:accounts read:statuses"

    seed_demo: bool = False
    demo_email: str = "demo@example.com"
    demo_password: str = "ChangeThisDemoPassword123!"

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore",
    )


settings = Settings()