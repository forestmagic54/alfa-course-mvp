import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from fastapi.routing import serialize_response
from pydantic import ValidationError

from src.api.materials.routes import router as materials_router
from src.api.materials.schemas import MaterialCard, MaterialFilters
from src.api.recommendations.routes import router as feeds_router
from src.api.roadmaps.routes import router as roadmaps_router
from src.config import load_demo_config
from src.db.models.materials import Materials
from src.services.feeds import FeedService
from src.services.materials import MaterialService
from src.services.roadmaps import RoadmapService


@pytest.fixture
def material_responses():
    config = load_demo_config('1')
    user_id, list_id = UUID(int=100), UUID(int=101)
    course_id = UUID(next(iter(config['access']['course_prices'])))
    materials = [Materials(id=UUID(int=i), kind=kind, source_id=course_id if i == 1 else UUID(int=200 + i),
                          verified_course_id=course_id if i == 1 else UUID(int=204) if i == 4 else None,
                          title=kind, duration_minutes=None, access_type='paid' if kind == 'course' else 'free',
                          url='https://example.test/material', public_description='Description', source_version='1')
                 for i, kind in enumerate(('course', 'article', 'document', 'course'), 1)]
    catalog = SimpleNamespace(
        classification=AsyncMock(side_effect=lambda ids: {i: {'topics': {}, 'industries': {}, 'tags': set()} for i in ids}),
        visible_subset=AsyncMock(return_value={m.id for m in materials[:3]}),
        search=AsyncMock(return_value=(materials[:3], 3)), get=AsyncMock(return_value=materials[0]),
        related=AsyncMock(return_value=materials[1:3]))
    commerce = SimpleNamespace(tariffs=AsyncMock(return_value=[]), subscription_links=AsyncMock(return_value=[]),
                               user_state=AsyncMock(return_value=([], [], [])))
    service = MaterialService(lambda config: catalog, commerce, SimpleNamespace(material_ids=AsyncMock(return_value=set())))
    listing = SimpleNamespace(id=list_id, recommendation_format='quick', saved_at=None, title='Plan', summary='Summary',
        context_snapshot={'material_versions': {str(m.id): '1' for m in materials}})
    items = [(SimpleNamespace(list_id=list_id, position=i, explanation='Explanation', offer_text=None,
                              step_role='intro' if i == 1 else 'practice',
                              transition_text=None if i == 1 else 'Transition'), material)
             for i, material in enumerate(materials, 1)]
    recommendations = SimpleNamespace(items=AsyncMock(return_value=items))
    feeds = FeedService(None, recommendations, None, None, catalog, None, service.build_cards)
    roadmaps = RoadmapService(None, recommendations, None, None, catalog, None, service.build_cards,
                             SimpleNamespace(studied_ids=AsyncMock(return_value=set())))

    async def render():
        feed = await feeds.render(user_id, [listing])
        roadmap = await roadmaps.render(user_id, [listing])
        return {
            'listMaterials': await service.search(MaterialFilters(), user_id, config),
            'getMaterial': await service.detail(materials[0].id, user_id, config),
            'getRecommendations': feed[0], 'generateRecommendations': feed[0],
            'listSavedRecommendations': feed, 'saveRecommendations': feed[0],
            'generateRoadmap': roadmap[0], 'listSavedRoadmaps': roadmap,
            'getRoadmap': roadmap[0], 'saveRoadmap': roadmap[0],
        }
    return asyncio.run(render()), {str(m.id): str(m.verified_course_id) for m in materials if m.kind == 'course'}


def test_built_cards_keep_conditional_fields_in_all_response_routes(material_responses):
    payloads, course_ids = material_responses

    async def check():
        routes = [*materials_router.routes, *feeds_router.routes, *roadmaps_router.routes]
        for route in routes:
            if route.operation_id not in payloads:
                continue
            output = await serialize_response(field=route.response_field, response_content=payloads[route.operation_id],
                exclude_unset=route.response_model_exclude_unset, exclude_none=route.response_model_exclude_none)
            if route.operation_id == 'listMaterials':
                cards = output['items']
            elif route.operation_id == 'getMaterial':
                cards = [output, *output['related_materials']]
            else:
                lists = output if isinstance(output, list) else [output]
                assert all('id' in listing and listing['saved_at'] is None for listing in lists)
                cards = [item['material'] for listing in lists for item in listing.get('items', listing.get('steps', []))]
            for card in cards:
                assert 'duration_minutes' in card and 'primary_action' in card, route.operation_id
                if card['kind'] == 'course':
                    assert card['course_id'] == course_ids[card['id']], route.operation_id
                else:
                    assert 'course_id' not in card, route.operation_id
    asyncio.run(check())


@pytest.mark.parametrize(('index', 'include_id', 'course_id'), [
    (0, False, None), (0, True, None), (1, True, None), (2, True, UUID(int=999)),
])
def test_card_rejects_course_id_inconsistent_with_kind(material_responses, index, include_id, course_id):
    payloads, _ = material_responses
    card = dict(payloads['getRecommendations']['items'][index]['material'])
    card.pop('course_id', None)
    if include_id:
        card['course_id'] = course_id
    with pytest.raises(ValidationError):
        MaterialCard.model_validate(card)
