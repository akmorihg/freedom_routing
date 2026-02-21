from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    DATABASE_URL: str

    REDIS_URL: str

    S3_URL: str
    S3_ACCESS_KEY: str
    S3_SECRET_KEY: str
    S3_REGION_NAME: str
    S3_BUCKET: str


settings = Settings()
