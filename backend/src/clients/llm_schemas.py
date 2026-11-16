"""Снимки разрешённых полей ORM и результаты генерации."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

Label = Annotated[str, Field(min_length=1, max_length=200)]


class StudiedMaterialInput(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    title: str = Field(min_length=1, max_length=1000)
    kind: Literal['article', 'course', 'document']


class MaterialInput(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    kind: Literal['article', 'course', 'document']
    title: str = Field(min_length=1, max_length=1000)
    public_description: str | None = Field(default=None, max_length=16000)
    default_offer_text: str | None = None
    access_type: Literal['free', 'paid', 'unknown']
    duration_minutes: int | None = Field(default=None, gt=0)
    difficulty_level: Literal['beginner', 'intermediate', 'advanced'] | None = None
    learning_role: Literal['intro', 'practice', 'advanced'] | None = None
    annotation_source: Literal['import', 'manual', 'model'] | None = None
    annotation_version: str | None = Field(default=None, max_length=100)
    source_version: str
    topics: list[Label] = Field(default_factory=list, max_length=30)
    tags: list[Label] = Field(default_factory=list, max_length=30)
    industries: list[Label] = Field(default_factory=list, max_length=30)
    selection_kind: Literal['relevance', 'exploration', 'fallback'] | None = None
    mode: Literal['quick', 'medium', 'deep'] | None = None
    matched_topics: list[Label] = Field(default_factory=list, max_length=30)
    matched_tags: list[Label] = Field(default_factory=list, max_length=30)


class ProfileInput(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    stage_code: str | None = Field(default=None, max_length=100)
    industry_code: str | None = Field(default=None, max_length=100)
    goal_code: str | None = Field(default=None, max_length=100)
    learning_mode: Literal['quick', 'practical', 'trajectory'] | None = None
    profile_config_version: str

    def to_prompt(self) -> dict:
        """Дополняет коды профиля подписями из соответствующей версии конфигурации."""
        from src.config.demo import load_demo_config

        data = self.model_dump()
        try:
            config = load_demo_config(self.profile_config_version)
        except ValueError:
            return data
        for question in config['questionnaire']['questions']:
            field = config['answer_projection'][question['key']]
            label = next((item['label'] for item in question['options'] if item['value'] == data.get(field)), None)
            if label is not None:
                data[field.removesuffix('_code') + '_label'] = label
        industry = next((item['label'] for item in config['industries'] if item['code'] == self.industry_code), None)
        if industry is not None:
            data['industry_label'] = industry
        return data


class Usage(BaseModel):
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    neurons: float | None = Field(default=None, ge=0, allow_inf_nan=False)


class DescriptionResult(BaseModel):
    material_id: UUID
    source_version: str
    model: str
    status: Literal['succeeded', 'fallback', 'failed']
    text: str | None
    latency_ms: int
    usage: Usage = Field(default_factory=Usage)
    error: str | None = None

