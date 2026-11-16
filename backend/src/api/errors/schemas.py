from pydantic import BaseModel


class ErrorField(BaseModel):
    field: str
    message: str


class Error(BaseModel):
    code: str
    message: str
    fields: list[ErrorField] | None = None
