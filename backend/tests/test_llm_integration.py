import asyncio
import json
from types import SimpleNamespace
from uuid import UUID

import httpx

from src.clients.llm import LLMClient
from src.config.settings import LLMSettings
from src.services.llm_generator import LLMGenerator
from src.services.onboarding import effective_preferences
from src.services.recommendation_stubs import StubGenerator, StubRanker
from src.services.recommendations import RecommendationService


def test_recommendation_passes_effective_context_to_http():
    material = SimpleNamespace(id=UUID(int=1), kind='article', title='Статья', source_table='Articles',
        is_recommendable=True, learning_role='intro', difficulty_level='beginner', annotation_source='manual',
        annotation_version='1', duration_minutes=None, source_version='1', public_description='О продажах',
        access_type='free', email='private@example.test')
    topic = UUID('6541a087-3b32-5f66-87a5-c9b3b386ec53')
    tag = UUID('9adc5662-855a-54db-bd20-766b15174ab9')
    class CRUD:
        async def recommendation_candidates(self): return [material]
        async def classification(self, ids):
            return {material.id: {'topics': {topic: 'Продажи'}, 'tags': {tag: 'Тег'}, 'industries': {}}}
    async def cards(*args):
        return [{'id': material.id, 'primary_action': {'type': 'open'}, 'access': 'free'}]
    seen = []
    def handler(request):
        seen.append(json.loads(json.loads(request.content)['messages'][1]['content']))
        return httpx.Response(200, json={'success': True, 'result': {'response': 'Текст о продажах.'}})
    async def run():
        settings = LLMSettings(_env_file=None, cloudflare_api_token='test', cloudflare_account_id='a' * 32)
        async with LLMClient(settings, transport=httpx.MockTransport(handler)) as client:
            service = RecommendationService(None, StubRanker(), LLMGenerator(client, 1), StubGenerator(), 1,
                                            lambda config: CRUD(), cards)
            onboarding = {'form_type': 'simple', 'questionnaire_version': '1', 'status': 'completed',
                          'answers': {'business_stage': 'operating', 'current_task': 'sales', 'learning_mode': None}}
            result = await service.recommend('quick', preferences=effective_preferences(None, onboarding))
            assert result.items[0]['explanation'] == 'Текст о продажах.'
            assert result.ranking_version == 'stub-v1'
            await service.recommend('popular')
    asyncio.run(run())
    assert len(seen) == 1
    assert seen[0]['material']['matched_topics'] == ['Продажи']
    assert seen[0]['material']['matched_tags'] == ['Тег']
    assert seen[0]['profile']['stage_label'] == 'Бизнес уже работает'
    assert seen[0]['profile']['learning_mode'] is None
    assert 'private@example.test' not in json.dumps(seen)


def test_timeout_preserves_completed_text_and_cancels_other_calls():
    from src.clients.llm_schemas import MaterialInput
    from src.services.recommendation_stubs import GenerationInput, RankedItem

    ids = [UUID(int=1), UUID(int=2)]
    cancelled = []
    class Client:
        async def generate_article_description(self, material, profile):
            if material.id == ids[0]:
                return SimpleNamespace(status='succeeded', material_id=material.id, source_version='1', text='Готово')
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.append(True)
    facts = {i: MaterialInput(id=i, kind='article', title='Название', public_description='Описание',
                              access_type='unknown', source_version='1') for i in ids}
    ranking = tuple(RankedItem(i, 'article', (), 'fallback') for i in ids)
    result = asyncio.run(LLMGenerator(Client(), 0.01).generate(GenerationInput('quick', None, (), ranking, facts=facts)))
    assert result.items[ids[0]].explanation == 'Готово'
    assert result.items[ids[1]].explanation != 'Готово'
    assert cancelled == [True]
