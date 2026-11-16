from datetime import datetime
from typing import Literal, NotRequired, TypedDict
from uuid import UUID


class NamedItemData(TypedDict):
    id: UUID
    title: str


class PriceData(TypedDict):
    amount_minor: int
    currency: str
    source: str


class CourseOfferData(TypedDict):
    kind: Literal['course']
    price: PriceData
    discounted_amount_minor: int | None


class SubscriptionOfferData(TypedDict):
    kind: Literal['subscription']
    subscription_id: UUID
    subscription_tariff_id: UUID
    title: str
    price: PriceData
    discounted_amount_minor: int | None
    duration_months: int


class MaterialActionData(TypedDict):
    type: str
    url: NotRequired[str | None]
    subscription_tariff_id: NotRequired[UUID | None]


class MaterialCardData(TypedDict):
    id: UUID
    kind: str
    title: str
    duration_minutes: int | None
    topics: list[NamedItemData]
    industries: list[NamedItemData]
    skills: list[NamedItemData]
    access_type: str
    access: str
    course_id: NotRequired[UUID | None]
    offers: list[CourseOfferData | SubscriptionOfferData]
    primary_action: MaterialActionData | None
    is_favorite: bool


class ClassificationData(TypedDict):
    topics: dict[UUID, str]
    industries: dict[UUID, str]
    tags: set[UUID]


class MaterialFiltersData(TypedDict):
    topics: list[NamedItemData]
    industries: list[NamedItemData]
    skills: list[NamedItemData]


class MaterialPageData(TypedDict):
    items: list[MaterialCardData]
    total: int


class MaterialDetailData(MaterialCardData):
    description: str | None
    explanation: str | None
    related_materials: list[MaterialCardData]


class OnboardingInputData(TypedDict):
    form_type: str
    questionnaire_version: str
    status: str
    answers: dict[str, object]


class ProfileSnapshot(TypedDict):
    goal_code: str | None
    industry_code: str | None
    stage_code: str | None
    learning_mode: str | None
    profile_config_version: str
    source_onboarding_response_id: str | None
    updated_at: str | None


class RecommendationItemData(TypedDict):
    position: int
    material: MaterialCardData
    explanation: str | None
    offer_text: str | None
    step_role: NotRequired[str | None]
    transition_text: NotRequired[str | None]
    is_studied: NotRequired[bool]


class RecommendationListData(TypedDict):
    id: UUID | None
    mode: str
    format: str | None
    saved_at: datetime | None
    items: list[RecommendationItemData]


class RoadmapStepData(RecommendationItemData):
    step_role: str
    transition_text: str | None
    is_studied: bool


class RoadmapData(TypedDict):
    id: UUID | None
    title: str
    summary: str
    saved_at: datetime | None
    steps: list[RoadmapStepData]


class FavoriteMaterialData(TypedDict):
    material_id: UUID
    created_at: datetime
    material: MaterialCardData | None
