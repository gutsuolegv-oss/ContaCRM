from pydantic import BaseModel, ConfigDict, Field

from app.models import UserRole


class LoginIn(BaseModel):
    email: str = Field(max_length=255)
    password: str = Field(max_length=1024)


class AccessTokenOut(BaseModel):
    """Refresh token-ul NU e aici: vine într-un cookie httpOnly (vezi app/api/auth.py)."""

    access_token: str
    token_type: str = "bearer"  # noqa: S105
    expires_in: int  # secunde


class MeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    full_name: str
    role: UserRole
    must_change_password: bool
