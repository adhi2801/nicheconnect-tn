from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "local"
    database_url: str
    redis_url: str
    secret_key: str
    access_token_expire_minutes: int = 60


settings = Settings()
