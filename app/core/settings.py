from pydantic import BaseSettings


class Settings(BaseSettings):
    SMTP_HOST: str
    SMTP_PORT: int = 587
    SMTP_USERNAME: str | None = None
    SMTP_PASSWORD: str | None = None
    SMTP_FROM: str
    SMTP_USE_TLS: bool = True

    APP_NAME: str = "Dokumentenmanager"
    MFA_CODE_TTL_MINUTES: int = 10

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
