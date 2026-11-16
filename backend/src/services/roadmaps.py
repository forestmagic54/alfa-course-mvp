import json
from uuid import UUID

from src.config import load_demo_config
from src.services.feeds import snapshot
from src.services.onboarding import effective_preferences


class MissingGoal(Exception):
    pass


class RoadmapService:
    def __init__(self, session, recommendations, onboarding, users, catalog, ranker, card_builder, studies):
        self.session, self.recommendations, self.onboarding, self.users = session, recommendations, onboarding, users
        self.catalog, self.ranker, self.build_cards, self.studies = catalog, ranker, card_builder, studies

    async def render(self, user_id: UUID, lists):
        rows = await self.recommendations.items([row.id for row in lists])
        ids = list({material.id for _, material in rows})
        visible = await self.catalog.visible_subset(ids) if ids else set()
        materials = {m.id: m for _, m in rows if m.id in visible}
        cards = {c['id']: c for c in await self.build_cards(list(materials.values()), user_id, load_demo_config())}
        studied = await self.studies.studied_ids(user_id, ids)
        grouped = {row.id: [] for row in lists}
        by_id = {row.id: row for row in lists}
        previous_stale = {row.id: False for row in lists}
        for item, material in rows:
            card = cards.get(material.id)
            if card is None:
                card = {'id': material.id, 'kind': material.kind, 'title': material.title,
                        'duration_minutes': None, 'topics': [], 'industries': [], 'skills': [],
                        'access_type': 'unknown', 'access': 'unknown', 'offers': [],
                        'primary_action': None, 'is_favorite': False}
                if material.kind == 'course':
                    card['course_id'] = material.verified_course_id
            stale = (material.id not in visible or
                     by_id[item.list_id].context_snapshot.get('material_versions', {}).get(str(material.id)) != material.source_version)
            grouped[item.list_id].append({'position': item.position, 'material': card,
                'explanation': 'Материал можно изучить для знакомства с темой.' if stale else item.explanation,
                'offer_text': None if stale else item.offer_text, 'step_role': item.step_role,
                'transition_text': None if item.position == 1 else
                    'Продолжите изучение темы с этим материалом.' if stale or previous_stale[item.list_id] else item.transition_text,
                'is_studied': material.id in studied})
            previous_stale[item.list_id] = stale
        return [{'id': row.id, 'title': row.title, 'summary': row.summary, 'saved_at': row.saved_at,
                 'steps': grouped[row.id]} for row in lists]

    async def generate(self, user_id: UUID | None, onboarding=None):
        while True:
            profile = await self.onboarding.fresh_profile(user_id) if user_id is not None else None
            profile_data = snapshot(profile)
            preferences = effective_preferences(profile, onboarding)
            if not preferences.goal_code:
                raise MissingGoal
            result = await self.ranker.recommend('deep', user_id=user_id, preferences=preferences)
            if user_id is None or onboarding is not None:
                ids = [item['material']['id'] for item in result.items]
                studied = await self.studies.studied_ids(user_id, ids) if user_id is not None else set()
                return {'id': None, 'title': result.title, 'summary': result.summary, 'saved_at': None,
                        'steps': [{**item, 'is_studied': item['material']['id'] in studied} for item in result.items]}
            json.dumps({'profile': profile_data, 'material_versions': result.material_versions,
                        'ranking_config': result.ranking_config}, allow_nan=False)
            try:
                await self.session.rollback()
                await self.users.lock(user_id)
                current = snapshot(await self.onboarding.fresh_profile(user_id))
                if current != profile_data:
                    await self.session.rollback()
                    continue
                row = await self.recommendations.create_roadmap(user_id, current, result)
                await self.session.commit()
                return (await self.render(user_id, [row]))[0]
            except BaseException:
                await self.session.rollback()
                raise

    async def get(self, user_id: UUID, list_id: UUID):
        row = await self.recommendations.roadmap(user_id, list_id)
        return (await self.render(user_id, [row]))[0] if row else None

    async def saved(self, user_id: UUID):
        return await self.render(user_id, await self.recommendations.saved_roadmaps(user_id))

    async def save(self, user_id: UUID, list_id: UUID):
        try:
            row = await self.recommendations.save_roadmap(user_id, list_id)
            await self.session.commit()
        except BaseException:
            await self.session.rollback()
            raise
        return (await self.render(user_id, [row]))[0] if row else None
