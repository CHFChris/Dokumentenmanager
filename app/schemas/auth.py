from pydantic import BaseModel, EmailStr, Field

class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=256)

class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=256)

class UserOut(BaseModel):
    id: int
    email: EmailStr

class TokenOut(BaseModel):
    token: str
    user: UserOut
