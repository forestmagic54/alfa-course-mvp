from pydantic import BaseModel, ConfigDict, StrictBool


class MaterialStudyStateInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    is_studied: StrictBool
