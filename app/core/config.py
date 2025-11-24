# app/core/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, EmailStr


class Settings(BaseSettings):
    files_fernet_key: str
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,  # .env keys dürfen groß/klein geschrieben sein
        extra="forbid",        # nur bekannte Variablen erlaubt
    )

    # ------------------------------------------------------------
    # 🧭 Allgemeine App-Einstellungen
    # ------------------------------------------------------------
    APP_NAME: str = "Dokumentenmanager"
    APP_ENV: str = "development"
    SECRET_KEY: str = Field(..., min_length=16)

    # Basis-URL für Links (z. B. Verifizierungs-E-Mail)
    PUBLIC_BASE_URL: str = "http://127.0.0.1:8000"

    # Token-Laufzeiten
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # ------------------------------------------------------------
    # 🗄️ Datenbank
    # ------------------------------------------------------------
    DB_URL: str

    # ------------------------------------------------------------
    # 📂 Dateien / Upload
    # ------------------------------------------------------------
    FILES_DIR: str = "./data/files"
    MAX_UPLOAD_MB: int = 50

    # Fernet-Key für Datei-Verschlüsselung
    # kommt aus der Umgebungsvariable FILES_FERNET_KEY
    files_fernet_key: str = Field(..., env="FILES_FERNET_KEY")

    # ------------------------------------------------------------
    # 📩 SMTP / Mail
    # ------------------------------------------------------------
    MAIL_FROM: EmailStr
    MAIL_FROM_NAME: str = "Dokumentenmanager"
    MAIL_SERVER: str
    MAIL_PORT: int = 587
    MAIL_USERNAME: str | None = None
    MAIL_PASSWORD: str | None = None
    MAIL_USE_TLS: bool = True

    # ------------------------------------------------------------
    # 🔐 Passwort Reset
    # ------------------------------------------------------------
    RESET_RATE_LIMIT_MINUTES: int = 10
    RESET_TOKEN_EXPIRE_MINUTES: int = 60


# ------------------------------------------------------------
# Globale Settings-Instanz
# ------------------------------------------------------------
settings = Settings()
