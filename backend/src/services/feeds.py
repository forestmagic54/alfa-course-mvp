import json
from typing import Literal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.config import load_demo_config
from src.db.crud.materials import MaterialsCRUD
from src.db.crud.onboarding import OnboardingCRUD
from src.db.crud.recommendations import RecommendationsCRUD
from src.db.crud.users import UsersCRUD
from src.db.models.recommendations import RecommendationLists
from src.db.models.users import UserProfiles
from src.services.onboarding import effective_preferences
from src.services.recommendations import RecommendationService
from src.services.types import (
    MaterialCardData,
    OnboardingInputData,
    ProfileSnapshot,
    RecommendationItemData,
    RecommendationListData,
)


def snapshot(profile: UserProfiles | None) -> ProfileSnapshot | None:
    if profile is None:
        return None
    return {
        'goal_code': profile.goal_code,
        'industry_code': profile.industry_code,
        'stage_code': profile.stage_code,
        'learning_mode': profile.learning_mode,
        'profile_config_version': profile.profile_config_version,
        'source_onboarding_response_id': str(profile.source_onboarding_response_id) if profile.source_onboarding_response_id is not None else None,
        'updated_at': str(profile.updated_at) if profile.updated_at is not None else None,
    }


class FeedService:
    def __init__(self, session: AsyncSession, recommendations: RecommendationsCRUD, onboarding: OnboardingCRUD,
                 users: UsersCRUD, catalog: MaterialsCRUD, ranker: RecommendationService, card_builder):
        self.session = session
        self.recommendations = recommendations
        self.onboarding = onboarding
        self.users = users
        self.catalog = catalog
        self.ranker = ranker
        self.build_cards = card_builder

    async def render(self, user_id: UUID, lists: list[RecommendationLists]) -> list[RecommendationListData]:
        rows = await self.recommendations.items([item.id for item in lists])
        config = load_demo_config()
        visible = await self.catalog.visible_subset([material.id for _, material in rows])
        materials = {m.id: m for _, m in rows if m.id in visible}
        cards: dict[UUID, MaterialCardData] = {c['id']: c for c in await self.build_cards(list(materials.values()), user_id, config)}
        grouped: dict[UUID, list[RecommendationItemData]] = {item.id: [] for item in lists}
        by_id = {item.id: item for item in lists}
        for item, material in rows:
            card = cards.get(material.id)
            if card is None:
                card = {'id': material.id, 'kind': material.kind, 'title': material.title,
                        'duration_minutes': None, 'topics': [], 'industries': [], 'skills': [],
                        'access_type': 'unknown', 'access': 'unknown', 'offers': [],
                        'primary_action': None, 'is_favorite': False}
                if material.kind == 'course':
                    card['course_id'] = material.verified_course_id
            stale = by_id[item.list_id].context_snapshot.get('material_versions', {}).get(str(material.id)) != material.source_version
            explanation = ('Материал можно изучить для знакомства с темой.' if stale or material.id not in visible
                           else item.explanation)
            grouped[item.list_id].append({'position': item.position, 'material': card, 'explanation': explanation,
                                          'offer_text': None if stale or material.id not in visible else item.offer_text})
        return [{'id': row.id, 'mode': 'personalized', 'format': row.recommendation_format,
                 'saved_at': row.saved_at, 'items': grouped[row.id]} for row in lists]

    async def feed(self, user_id: UUID | None, *, mode: Literal['popular', 'personalized'] | None = None,
                   format: Literal['quick', 'medium'] | None = None, onboarding: OnboardingInputData | None = None,
                   regenerate: bool = False, limit: int = 5) -> RecommendationListData:
        while True:
            profile = await self.onboarding.fresh_profile(user_id) if user_id is not None else None
            profile_data = snapshot(profile)
            preferences = effective_preferences(profile, onboarding)
            chosen_format = format or ('medium' if preferences.learning_mode == 'practical' else 'quick')
            if mode == 'popular' or not preferences.personalized:
                result = await self.ranker.recommend('popular', user_id=user_id, limit=limit)
                return {'id': None, 'mode': 'popular', 'format': None, 'saved_at': None, 'items': result.items}
            if user_id is not None and onboarding is None and not regenerate:
                existing = await self.recommendations.current(user_id, chosen_format, profile_data)
                if existing:
                    return (await self.render(user_id, [existing]))[0]
            result = await self.ranker.recommend(chosen_format, user_id=user_id, preferences=preferences, limit=limit)
            if user_id is None or onboarding is not None:
                return {'id': None, 'mode': 'personalized', 'format': chosen_format, 'saved_at': None, 'items': result.items}
            json.dumps({'profile': profile_data, 'material_versions': result.material_versions,
                        'ranking_config': result.ranking_config}, allow_nan=False)
            try:
                await self.session.rollback()
                await self.users.lock(user_id)
                current = snapshot(await self.onboarding.fresh_profile(user_id))
                if current != profile_data:
                    await self.session.rollback()
                    continue
                crud = self.recommendations
                existing = await crud.current(user_id, chosen_format, current) if not regenerate else None
                row = existing or await crud.create(user_id, current, chosen_format, result)
                await self.session.commit()
                return (await self.render(user_id, [row]))[0]
            except BaseException:
                await self.session.rollback()
                raise

    async def save_feed(self, user_id: UUID, list_id: UUID) -> RecommendationListData | None:
        try:
            row = await self.recommendations.save(user_id, list_id)
            await self.session.commit()
        except BaseException:
            await self.session.rollback()
            raise
        return (await self.render(user_id, [row]))[0] if row else None

    async def saved(self, user_id: UUID) -> list[RecommendationListData]:
        return await self.render(user_id, await self.recommendations.saved(user_id))
