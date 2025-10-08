from datetime import datetime, timedelta, timezone
import jwt
from typing import Any, Optional
from app.core.config import settings

ALGORITHM = "HS256"

class JWTService:
    def __init__(self, secret: str, algorithm: str = ALGORITHM):
        self.secret = secret
        self.algorithm = algorithm

    def create_token(self, subject: str | int, expires_delta: timedelta, claims: Optional[dict[str, Any]] = None) -> str:
        now = datetime.now(timezone.utc)
        payload: dict[str, Any] = {"sub": str(subject), "iat": int(now.timestamp())}
        if claims:
            payload.update(claims)
        payload["exp"] = int((now + expires_delta).timestamp())
        return jwt.encode(payload, self.secret, algorithm=self.algorithm)

    def decode_token(self, token: str) -> dict[str, Any]:
        return jwt.decode(token, self.secret, algorithms=[self.algorithm])

jwt_service = JWTService(settings.SECRET_KEY)
