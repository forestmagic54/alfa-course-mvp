from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select, update

from src.db.models.materials import Materials
from src.db.models.recommendations import RecommendationItems, RecommendationLists


class RecommendationsCRUD:
    def __init__(self, session):
        self.session = session

    def owned(self, user_id):
        return (RecommendationLists.user_id == user_id, RecommendationLists.list_type == 'feed',
                RecommendationLists.mode == 'personalized')

    async def current(self, user_id, format, profile):
        query = (select(RecommendationLists).where(*self.owned(user_id),
                 RecommendationLists.recommendation_format == format,
                 RecommendationLists.context_snapshot.contains({'profile': profile}))
                 .order_by(RecommendationLists.created_at.desc(), RecommendationLists.id.desc()).limit(1))
        return await self.session.scalar(query)

    async def saved(self, user_id):
        query = (select(RecommendationLists).where(*self.owned(user_id), RecommendationLists.saved_at.is_not(None))
                 .order_by(RecommendationLists.saved_at.desc(), RecommendationLists.id.desc()))
        return list((await self.session.scalars(query)).all())

    async def save(self, user_id, list_id):
        query = (update(RecommendationLists).where(*self.owned(user_id), RecommendationLists.id == list_id,
                 RecommendationLists.saved_at.is_(None)).values(saved_at=datetime.now(UTC)))
        await self.session.execute(query)
        return await self.session.scalar(select(RecommendationLists).where(*self.owned(user_id),
                                         RecommendationLists.id == list_id).execution_options(populate_existing=True))

    async def create(self, user_id, profile, format, result):
        row = RecommendationLists(user_id=user_id, onboarding_response_id=UUID(profile['source_onboarding_response_id']) if profile['source_onboarding_response_id'] else None,
            list_type='feed', mode='personalized', recommendation_format=format,
            context_snapshot={'profile': profile, 'material_versions': result.material_versions},
            ranking_version=result.ranking_version, ranking_config=result.ranking_config)
        self.session.add(row)
        await self.session.flush()
        for item, ranked in zip(result.items, result.ranked_items, strict=True):
            self.session.add(RecommendationItems(list_id=row.id, material_id=ranked.material_id,
                position=item['position'], explanation=item['explanation'], offer_text=item['offer_text'],
                selection_kind=ranked.selection_kind, score=ranked.score))
        await self.session.flush()
        return row

    def owned_roadmap(self, user_id):
        return (RecommendationLists.user_id == user_id, RecommendationLists.list_type == 'trajectory',
                RecommendationLists.mode == 'personalized', RecommendationLists.recommendation_format == 'deep')

    async def roadmap(self, user_id, list_id):
        return await self.session.scalar(select(RecommendationLists).where(*self.owned_roadmap(user_id),
                                         RecommendationLists.id == list_id).execution_options(populate_existing=True))

    async def saved_roadmaps(self, user_id):
        query = (select(RecommendationLists).where(*self.owned_roadmap(user_id), RecommendationLists.saved_at.is_not(None))
                 .order_by(RecommendationLists.saved_at.desc(), RecommendationLists.id.desc()))
        return list((await self.session.scalars(query)).all())

    async def save_roadmap(self, user_id, list_id):
        query = (update(RecommendationLists).where(*self.owned_roadmap(user_id), RecommendationLists.id == list_id,
                 RecommendationLists.saved_at.is_(None)).values(saved_at=datetime.now(UTC)))
        await self.session.execute(query)
        return await self.roadmap(user_id, list_id)

    async def create_roadmap(self, user_id, profile, result):
        row = RecommendationLists(user_id=user_id, onboarding_response_id=UUID(profile['source_onboarding_response_id']) if profile['source_onboarding_response_id'] else None,
            list_type='trajectory', mode='personalized', recommendation_format='deep', title=result.title, summary=result.summary,
            context_snapshot={'profile': profile, 'material_versions': result.material_versions},
            ranking_version=result.ranking_version, ranking_config=result.ranking_config)
        self.session.add(row)
        await self.session.flush()
        for item, ranked in zip(result.items, result.ranked_items, strict=True):
            self.session.add(RecommendationItems(list_id=row.id, material_id=ranked.material_id,
                position=item['position'], explanation=item['explanation'], offer_text=item['offer_text'],
                selection_kind=ranked.selection_kind, score=ranked.score, step_role=item['step_role'],
                transition_text=item['transition_text']))
        await self.session.flush()
        return row

    async def items(self, list_ids):
        if not list_ids:
            return []
        query = (select(RecommendationItems, Materials).join(Materials, Materials.id == RecommendationItems.material_id)
                 .where(RecommendationItems.list_id.in_(list_ids)).order_by(RecommendationItems.position))
        return (await self.session.execute(query)).all()
