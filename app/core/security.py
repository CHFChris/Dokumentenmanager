# app/core/security.py

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional
import hashlib
import jwt

# Passwörter: bevorzugt Argon2, Alt-Hashes (bcrypt_sha256) bleiben gültig
from passlib.hash import bcrypt_sha256, argon2

from app.core.config import settings

# =============================
# 🔐 Passwort-Hashing
# =============================

# bcrypt hat ein 72-Byte-Limit; wir kappen sicherheitshalber auf 64 Zeichen für bcrypt.
# Argon2 ist nicht auf 72 Bytes limitiert, aber wir vereinheitlichen Policies.
MAX_PWD_LEN_BCRYPT_SAFE = 64

# Optional: aus .env konfigurierbar, Standard = "argon2"
PASSWORD_SCHEME = getattr(settings, "PASSWORD_SCHEME", "argon2").lower().strip()  # "argon2" | "bcrypt"


# --- Hash-Schema-Erkennung ohne passlib.identify (über Präfixe) ---
def _scheme_of(hash_str: str) -> str:
    if not hash_str:
        return "unknown"
    h = hash_str.lower()
    if h.startswith("$argon2"):                  # z. B. $argon2id$...
        return "argon2"
    if h.startswith("$bcrypt-sha256$"):         # passlib's bcrypt_sha256
        return "bcrypt"
    if h.startswith("$2a$") or h.startswith("$2b$") or h.startswith("$2y$"):
        return "bcrypt"                         # klassische bcrypt-Hashes
    return "unknown"


def hash_password(password: str) -> str:
    """
    Erzeugt einen sicheren Passwort-Hash.
    - Neu: Argon2id (zeitgemäß, speicherhart)
    - Alt (optional): bcrypt_sha256 (falls PASSWORD_SCHEME="bcrypt")
    """
    if PASSWORD_SCHEME == "argon2":
        # Solide Default-Parameter (OWASP-orientiert; lokal noch performant)
        return argon2.using(
            type="ID",            # Argon2id
            time_cost=2,          # Rechendurchläufe
            memory_cost=102_400,  # ~100 MiB
            parallelism=8,
        ).hash(password)
    else:
        # bcrypt_sha256 umgeht 72-Byte-Limit via Hash-vor-Bcrypt.
        # Wir kappen dennoch auf 64 Zeichen (Policy & UI-Konsistenz).
        return bcrypt_sha256.hash(password[:MAX_PWD_LEN_BCRYPT_SAFE])


def get_password_hash(password: str) -> str:
    """
    Kompatible Wrapper-Funktion für Passwort-Hashing.
    Signatur: str -> str (für FastAPI/OAuth2-Utilities etc.).
    """
    return hash_password(password)


def verify_password(password: str, password_hash: str) -> bool:
    """
    Verifiziert ein Passwort gegen einen gespeicherten Hash.
    Unterstützt nahtlos:
    - Argon2 (neu erzeugte Hashes)
    - bcrypt_sha256 (historische Hashes)
    """
    scheme = _scheme_of(password_hash)
    try:
        if scheme == "argon2":
            return argon2.verify(password, password_hash)

        if scheme == "bcrypt":
            # defensive: bei bcrypt auf 64 kappen (Policy & UI deckungsgleich)
            return bcrypt_sha256.verify(password[:MAX_PWD_LEN_BCRYPT_SAFE], password_hash)

        # Fallback (sollte selten passieren): beide probieren
        return (
            argon2.verify(password, password_hash)
            or bcrypt_sha256.verify(password[:MAX_PWD_LEN_BCRYPT_SAFE], password_hash)
        )
    except Exception:
        # Keine sensiblen Details leaken; False zurückgeben
        return False


# =============================
# 🔑 Token-Hashing (z. B. für Passwort-Reset)
# =============================

def hash_token(token: str) -> str:
    """Einmal-Tokens nur gehasht in DB speichern (kein Klartext)."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# =============================
# 🪙 JWT Service (Auth Tokens)
# =============================

ALGORITHM = "HS256"


class JWTService:
    def __init__(self, secret: str, algorithm: str = ALGORITHM):
        self.secret = secret
        self.algorithm = algorithm

    def create_token(
        self,
        subject: str | int,
        expires_delta: timedelta,
        claims: Optional[dict[str, Any]] = None,
    ) -> str:
        """JWT erstellen (mit Ablaufzeit, Subject und optionalen Claims)."""
        now = datetime.now(timezone.utc)
        payload: dict[str, Any] = {
            "sub": str(subject),
            "iat": int(now.timestamp()),
            "exp": int((now + expires_delta).timestamp()),
        }
        if claims:
            payload.update(claims)
        return jwt.encode(payload, self.secret, algorithm=self.algorithm)

    def decode_token(self, token: str) -> dict[str, Any]:
        """JWT entschlüsseln und validieren."""
        return jwt.decode(token, self.secret, algorithms=[self.algorithm])


# Globale Instanz für die gesamte App
jwt_service = JWTService(settings.SECRET_KEY)
