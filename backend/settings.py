from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # tells pydantic to load from ".env"
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Postgres ---
    DATABASE_URL: str


settings = Settings()
