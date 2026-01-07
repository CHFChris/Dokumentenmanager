# app/schemas/auth.py
from __future__ import annotations
from typing import Optional, Annotated
from pydantic import BaseModel, EmailStr, Field, field_validator
from pydantic import StringConstraints
import re

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
        max_length=64
    )
]

# ---------- Register ----------
class RegisterIn(BaseModel):
    username: UsernameStr = Field(
        description="Erlaubt sind Buchstaben, Ziffern, Unterstrich, Punkt und Bindestrich."
    )
    email: EmailStr
    password: PasswordStr

    @field_validator("password")
    @classmethod
    def password_policy(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters.")
        if not re.search(r"[A-Za-z]", v):
            raise ValueError("Password must contain at least one letter.")
        if not re.search(r"\d", v):
            raise ValueError("Password must contain at least one digit.")
        return v

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

    @field_validator("new_password")
    @classmethod
    def password_policy(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters.")
        if not re.search(r"[A-Za-z]", v):
            raise ValueError("Password must contain at least one letter.")
        if not re.search(r"\d", v):
            raise ValueError("Password must contain at least one digit.")
        return v

# ---------- User-DTOs ----------
class UserOut(BaseModel):
    id: int
    username: str
    email: EmailStr
    display_name: Optional[str] = None
    role_id: int

    model_config = {"from_attributes": True}

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
