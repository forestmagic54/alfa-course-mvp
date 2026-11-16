from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator, model_validator
from pydantic.json_schema import SkipJsonSchema

from src.api.onboarding.schemas import OnboardingInput


class MaterialFilters(BaseModel):
    q: str | None = None
    kind: Literal['course', 'article', 'document'] | None = None
    topic_id: UUID | None = None
    industry_id: UUID | None = None
    skill_id: UUID | None = None
    access_type: Literal['free', 'paid', 'subscription'] | None = None
    min_price_minor: int | None = None
    max_price_minor: int | None = None
    max_duration_minutes: int | None = None
    limit: int = 20
    offset: int = 0


class NamedItem(BaseModel):
    id: UUID
    title: str


class Price(BaseModel):
    amount_minor: int
    currency: Literal['RUB']
    source: Literal['demo_config', 'historical_dump']


class CourseOffer(BaseModel):
    kind: Literal['course']
    price: Price
    discounted_amount_minor: int | None


class SubscriptionOffer(BaseModel):
    kind: Literal['subscription']
    subscription_id: UUID
    subscription_tariff_id: UUID
    title: str
    price: Price
    discounted_amount_minor: int | None
    duration_months: int


class MaterialAction(BaseModel):
    type: Literal['open_course', 'read_article', 'open_document', 'download_document', 'buy_course', 'subscribe']
    url: str | None = None
    subscription_tariff_id: UUID | None = None


# shortcut: shared card schema; split course/article/document models at the next card schema refactor.
class MaterialCard(BaseModel):
    id: UUID
    kind: Literal['course', 'article', 'document']
    title: str
    duration_minutes: int | None
    topics: list[NamedItem]
    industries: list[NamedItem]
    skills: list[NamedItem]
    access_type: Literal['free', 'paid', 'unknown']
    access: Literal['free', 'course_purchase', 'subscription', 'none', 'unknown']
    course_id: UUID | None = None
    offers: list[CourseOffer | SubscriptionOffer]
    primary_action: MaterialAction | None
    is_favorite: bool

    @model_validator(mode='after')
    def validate_course_id(self):
        if self.kind == 'course' and self.course_id is None:
            raise ValueError('course_id is required for courses')
        if self.kind != 'course' and 'course_id' in self.model_fields_set:
            raise ValueError('course_id is only allowed for courses')
        return self


class MaterialDetail(MaterialCard):
    description: str | None
    explanation: str | None
    related_materials: list[MaterialCard]


class MaterialExplanationInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    onboarding: OnboardingInput | SkipJsonSchema[None] = None

    @field_validator('onboarding')
    @classmethod
    def reject_null(cls, value):
        if value is None:
            raise ValueError('Omit the field instead of passing null')
        return value


class MaterialExplanation(BaseModel):
    material_id: UUID
    kind: Literal['course', 'article', 'document']
    explanation: str
    offer_text: str | None


class MaterialPage(BaseModel):
    items: list[MaterialCard]
    total: int


class FilterOptions(BaseModel):
    topics: list[NamedItem]
    industries: list[NamedItem]
    skills: list[NamedItem]
