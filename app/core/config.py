from pydantic_settings import BaseSettings
from pydantic import Field

class Settings(BaseSettings):
    APP_NAME: str = "Dokumentenmanager"
    APP_ENV: str = "development"
    SECRET_KEY: str = Field(..., min_length=16)
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    DB_URL: str
    FILES_DIR: str = "./data/files"
    MAX_UPLOAD_MB: int = 50

    class Config:
        env_file = ".env"

settings = Settings()
