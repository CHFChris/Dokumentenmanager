# app/core/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, EmailStr


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,  # .env keys können groß oder klein geschrieben sein
        extra="forbid",        # nur erlaubte Variablen akzeptieren
    )

    # === 🧭 App ===
    APP_NAME: str = "Dokumentenmanager"
    APP_ENV: str = "development"
    SECRET_KEY: str = Field(..., min_length=16)
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # === 🗄️ Datenbank ===
    DB_URL: str

    # === 📂 Dateien / Upload ===
    FILES_DIR: str = "./data/files"
    MAX_UPLOAD_MB: int = 50

    # === 📩 SMTP / Mail ===
    MAIL_FROM: EmailStr
    MAIL_FROM_NAME: str = "Dokumentenmanager"
    MAIL_SERVER: str
    MAIL_PORT: int = 587
    MAIL_USERNAME: str | None = None
    MAIL_PASSWORD: str | None = None
    MAIL_USE_TLS: bool = True

    # === 🔐 Passwort Reset ===
    RESET_RATE_LIMIT_MINUTES: int = 10
    RESET_TOKEN_EXPIRE_MINUTES: int = 60


# globale Instanz
settings = Settings()
