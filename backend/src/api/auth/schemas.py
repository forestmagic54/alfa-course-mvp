from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from src.api.account.schemas import Account


class Credentials(BaseModel):
    model_config = ConfigDict(extra='forbid')

    email: Annotated[EmailStr, Field(max_length=254)]
    password: Annotated[str, Field(min_length=1, max_length=128, json_schema_extra={'writeOnly': True, 'format': 'password'})]


class Registration(Credentials):
    password: Annotated[str, Field(min_length=8, max_length=128, json_schema_extra={'writeOnly': True, 'format': 'password'})]


class AuthSession(BaseModel):
    access_token: str
    token_type: Literal['Bearer'] = 'Bearer'
    expires_in: int = Field(gt=0)
    user: Account
