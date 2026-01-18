from __future__ import annotations

from pydantic import BaseModel, Field


# Neue Namensvariante (wie in deinem auth.py Import)
class MFAChallengeResponse(BaseModel):
    mfa_required: bool = True
    method: str = "email"
    challenge_id: str


class MFAVerifyRequest(BaseModel):
    challenge_id: str
    code: str = Field(..., min_length=6, max_length=6, pattern=r"^\d{6}$")


# Alte Namensvariante (Kompatibilitaet)
class MfaChallengeOut(MFAChallengeResponse):
    pass


class MfaVerifyIn(MFAVerifyRequest):
    pass
