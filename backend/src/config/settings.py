from dataclasses import dataclass, field
from typing import ClassVar, Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL

MISTRAL = '@cf/mistralai/mistral-small-3.1-24b-instruct'


class BaseConfig(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')


class LLMSettings(BaseConfig):
    cloudflare_api_token: SecretStr = SecretStr('')
    cloudflare_account_id: str = ''
    llm_model: Literal['@cf/mistralai/mistral-small-3.1-24b-instruct'] = MISTRAL
    llm_timeout_seconds: float = Field(default=30, gt=0, le=120)
    llm_max_tokens: int = Field(default=1024, ge=64, le=4096)
    llm_temperature: float = Field(default=0.4, ge=0, le=2)


class ApplicationConfig(BaseConfig):
    llm_enabled: bool = True
    generation_timeout_seconds: float = Field(default=3, gt=0, allow_inf_nan=False)
    host: str = Field(default='127.0.0.1')
    port: int = Field(default=8000, ge=1, le=65535)
    api_prefix: str = Field(default='/api/v1', pattern=r'^(?:/[a-zA-Z0-9._~-]+)*$')


class DatabaseConfig(BaseConfig):
    model_config = SettingsConfigDict(env_prefix='DATABASE_', populate_by_name=True)

    username: str = Field(min_length=1, validation_alias='POSTGRES_USER')
    password: SecretStr = Field(validation_alias='POSTGRES_PASSWORD')
    name: str = Field(min_length=1, validation_alias='POSTGRES_DB')
    host: str = Field(min_length=1)
    port: int = Field(default=5432, ge=1, le=65535)

    @field_validator('password')
    @classmethod
    def validate_password(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value():
            raise ValueError('POSTGRES_PASSWORD must not be empty')
        return value

    @property
    def url(self) -> URL:
        return URL.create(
            'postgresql+asyncpg', username=self.username,
            password=self.password.get_secret_value(), host=self.host,
            port=self.port, database=self.name,
        )


class JWTConfig(BaseConfig):
    algorithm: ClassVar[str] = 'HS256'
    jwt_secret: SecretStr
    jwt_expire_minutes: int = Field(gt=0)

    @field_validator('jwt_secret')
    @classmethod
    def validate_jwt_secret(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().strip():
            raise ValueError('JWT_SECRET must not be empty')
        return value


@dataclass
class Settings:
    app: ApplicationConfig = field(default_factory=ApplicationConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    jwt: JWTConfig = field(default_factory=JWTConfig)
