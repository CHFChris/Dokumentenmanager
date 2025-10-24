# app/schemas/auth.py
from __future__ import annotations
from typing import Optional, Annotated
from pydantic import BaseModel, EmailStr, Field
from pydantic import StringConstraints  # v2: String-Constraints über Annotated

# ---------- Gemeinsame Typen ----------
UsernameStr = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=3,
        max_length=30,
        pattern=r"^[a-zA-Z0-9_.-]+$"
    )
]

PasswordStr = Annotated[
    str,
    StringConstraints(
        min_length=8,
        max_length=64  # Policy ≙ Hashing
    )
]

# ---------- Register ----------
class RegisterIn(BaseModel):
    username: UsernameStr = Field(
        description="Erlaubt sind Buchstaben, Ziffern, Unterstrich, Punkt und Bindestrich."
    )
    email: EmailStr
    password: PasswordStr

# ---------- Login ----------
class LoginIn(BaseModel):
    identifier: str = Field(..., description="E-Mail oder Benutzername")
    password: PasswordStr

# ---------- Password-Reset ----------
class PasswordResetStartIn(BaseModel):
    email: EmailStr

class PasswordResetCompleteIn(BaseModel):
    token: str = Field(min_length=16, max_length=512)
    new_password: PasswordStr

# ---------- User-DTOs ----------
class UserOut(BaseModel):
    id: int
    username: str
    email: EmailStr
    display_name: Optional[str] = None
    role_id: int

    model_config = {"from_attributes": True}  # ORM-kompatibel

class UserLiteOut(BaseModel):
    id: int
    username: str
    email: EmailStr

    model_config = {"from_attributes": True}

# ---------- Tokens ----------
class TokenOut(BaseModel):
    token: str
    user: UserLiteOut

# ---------- Hilfs-Endpunkte ----------
class UsernameAvailabilityOut(BaseModel):
    username: str
    available: bool
