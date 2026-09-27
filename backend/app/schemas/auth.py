from pydantic import BaseModel, ConfigDict, Field

from app.models import UserRole


class LoginIn(BaseModel):
    email: str = Field(max_length=255)
    password: str = Field(max_length=1024)


class RefreshIn(BaseModel):
    refresh_token: str = Field(max_length=255)


class TokenPairOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"  # noqa: S105
    expires_in: int  # secunde, pentru access token


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    full_name: str
    role: UserRole
