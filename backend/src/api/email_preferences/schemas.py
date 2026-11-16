from datetime import datetime
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, StrictBool, model_validator
from pydantic.json_schema import SkipJsonSchema


class EmailPreferencesInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    marketing_consent: StrictBool
    consent_version: Annotated[str, Field(min_length=1)] | SkipJsonSchema[None] = None

    @model_validator(mode='after')
    def validate_version(self) -> Self:
        if ('consent_version' in self.model_fields_set and not self.consent_version
                or self.marketing_consent and not self.consent_version):
            raise ValueError('Invalid consent version')
        return self


class EmailPreferences(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    marketing_consent: bool
    consent_version: str | None
    consent_updated_at: datetime | None
    unsubscribed_at: datetime | None
