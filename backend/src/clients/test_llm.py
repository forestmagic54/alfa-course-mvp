"""Автономные проверки контрактов LLM без сети и базы данных."""

import asyncio
import json
from types import SimpleNamespace
from uuid import UUID

import httpx
import pytest

from src.config.settings import MISTRAL, LLMSettings

from .llm import LLMClient


def settings():
    """Создаёт изолированные настройки без чтения рабочего .env."""
    return LLMSettings(
        _env_file=None, cloudflare_api_token='test_token',
        cloudflare_account_id='a' * 32, llm_model=MISTRAL,
        llm_temperature=0.2, llm_max_tokens=512,
    )


def material(kind='course', description='Исходная аннотация'):
    """Имитирует загруженный ORM-объект с лишними приватными полями."""
    return SimpleNamespace(
        id=UUID(int=1), kind=kind, title='Учёт', public_description=description,
        access_type='unknown', duration_minutes=None, difficulty_level=None,
        source_version='1', private_lesson='DO_NOT_SEND', metadata_={'secret': 'DO_NOT_SEND'},
    )


def completion(reason=None):
    """Формирует ответ Mistral в формате Workers AI."""
    result = {
        'response': 'Краткое описание.',
        'usage': {'prompt_tokens': 10, 'completion_tokens': 20, 'neurons': 0.8},
    }
    if reason is not None:
        result['finish_reason'] = reason
    return {'success': True, 'result': result}


@pytest.mark.parametrize('kind', ['article', 'course'])
def test_request_contract_and_privacy(kind):
    """Проверяет запрос к Mistral, разрешённые поля и закрытие клиента."""
    def handler(request):
        """Проверяет фактический HTTP-запрос на границе клиента."""
        payload = json.loads(request.content)
        assert request.url.path.endswith(MISTRAL)
        assert request.headers['Authorization'] == 'Bearer test_token'
        assert payload['temperature'] == 0.2
        assert payload['max_tokens'] == 512
        assert isinstance(payload['messages'], list)
        assert 'DO_NOT_SEND' not in request.content.decode()
        facts = json.loads(payload['messages'][1]['content'])
        assert facts['material']['access_type'] == 'unknown'
        assert facts['is_studied'] is True
        return httpx.Response(200, json=completion())

    async def run():
        """Выполняет вызов и проверяет нормализованный результат и расход."""
        async with LLMClient(settings(), transport=httpx.MockTransport(handler)) as client:
            generate = getattr(client, f'generate_{kind}_description')
            result = await generate(material(kind), is_studied=True)
            assert result.status == 'succeeded'
            assert result.text == 'Краткое описание.'
            assert client.get_usage()['usage']['neurons']['known_total'] == 0.8
            assert client.get_usage()['remaining_tokens'] is None
        assert client._http.is_closed
    asyncio.run(run())


@pytest.mark.parametrize('failure', ['http', 'json', 'length', 'empty', 'timeout', 'provider', 'result', 'content', 'html', 'oversize'])
def test_failure_and_fallback(failure):
    """Не выдаёт обрыв или ошибку за успешную генерацию и сохраняет аннотацию."""
    def handler(request):
        """Возвращает выбранный сбой без обращения к внешнему сервису."""
        if failure == 'timeout':
            raise httpx.ReadTimeout('secret provider detail')
        if failure == 'http':
            return httpx.Response(429, text='secret provider detail')
        if failure == 'json':
            return httpx.Response(200, text='not JSON')
        data = completion(reason='length' if failure == 'length' else None)
        if failure == 'provider':
            data['errors'] = [{'message': 'secret provider detail'}]
        elif failure == 'result':
            data['result'] = 'secret provider detail'
        elif failure in ('empty', 'content', 'html', 'oversize'):
            data['result']['response'] = {
                'empty': '', 'content': {'secret': 'provider detail'},
                'html': '<p>Описание</p>', 'oversize': 'я' * 4001,
            }[failure]
        return httpx.Response(200, json=data)

    async def run():
        """Проверяет fallback и отсутствие утечки сырых ошибок."""
        async with LLMClient(settings(), transport=httpx.MockTransport(handler)) as client:
            result = await client.generate_course_description(material())
            assert result.status == 'fallback'
            assert result.text == 'Исходная аннотация'
            assert 'secret' not in result.model_dump_json()
            assert client.get_usage()['generation_requests_attempted'] == 1
    asyncio.run(run())


@pytest.mark.parametrize('description', [None, '', '   '])
def test_missing_description_does_not_generate(description):
    """Не тратит квоту и не генерирует программу по одному названию."""
    def handler(request):
        pytest.fail('Unexpected request')

    async def run():
        async with LLMClient(settings(), transport=httpx.MockTransport(handler)) as client:
            for kind in ('article', 'course'):
                result = json.loads(await client.generate_description_json(
                    material(kind, description), studied_materials=[material()],
                ))
                assert result['status'] == 'failed'
                assert result['text'] is None
                assert result['error'] == 'missing_public_description'
                assert result['usage']['input_tokens'] is None
            assert client.get_usage()['generation_requests_attempted'] == 0
    asyncio.run(run())


def test_status_does_not_count_as_generation():
    """Проверка каталога не расходует счётчик генераций Mistral."""
    paths = []

    def handler(request):
        """Фиксирует операции каталога и генерации."""
        paths.append(request.url.path)
        if request.method == 'GET':
            return httpx.Response(200, json={'success': True, 'result': []})
        return httpx.Response(200, json=completion())

    async def run():
        """Проверяет модель и счётчик запросов после чтения каталога."""
        async with LLMClient(settings(), transport=httpx.MockTransport(handler)) as client:
            assert (await client.check_status())['generation_checked'] is False
            assert client.get_usage()['generation_requests_attempted'] == 0
            result = await client.generate_course_description(material())
            assert result.model == MISTRAL
            assert paths[1].endswith(MISTRAL)
            assert client.get_usage()['generation_requests_attempted'] == 1
    asyncio.run(run())


def test_wrong_material_does_not_call_api():
    """Отклоняет несовместимый тип материала до сетевого запроса."""
    def handler(request):
        """Запрещает неожиданный сетевой вызов."""
        pytest.fail('Unexpected request')

    async def run():
        """Проверяет тип материала и тип текущей отметки изучения."""
        async with LLMClient(settings(), transport=httpx.MockTransport(handler)) as client:
            with pytest.raises(ValueError):
                await client.generate_course_description(material('article'))
            with pytest.raises(ValueError):
                await client.generate_course_description(material(), is_studied='false')
    asyncio.run(run())


def test_mistral_profile_scenarios(monkeypatch, capsys):
    """Проверяет передачу профилей и трёх состояний изучения через JSON-функцию."""
    from . import check_mistral

    received = []

    def handler(request):
        """Сохраняет фактические входы запросов без внешней сети."""
        assert request.url.path.endswith(MISTRAL)
        received.append(json.loads(json.loads(request.content)['messages'][1]['content']))
        return httpx.Response(200, json=completion())

    client = LLMClient(settings(), transport=httpx.MockTransport(handler))
    monkeypatch.setattr(check_mistral, 'LLMClient', lambda: client)
    assert asyncio.run(check_mistral.main(profiles=True)) == 0
    assert len(received) == 8
    assert all(item['material'] == received[0]['material'] for item in received)
    assert received[0]['profile'] is None
    assert received[1]['profile']['learning_mode'] == 'quick'
    assert received[1]['profile']['stage_label'] == 'Запускаю бизнес'
    assert received[1]['profile']['goal_label'] == 'Разобраться с финансами и учётом'
    assert received[1]['material']['learning_role'] == 'intro'
    assert received[1]['material']['annotation_source'] == 'manual'
    assert received[2]['profile'] == received[3]['profile']
    assert received[2]['is_studied'] is False
    assert received[3]['is_studied'] is True
    assert received[4]['profile']['learning_mode'] == 'trajectory'
    assert received[4]['is_studied'] is None
    assert received[5]['profile']['learning_mode'] is None
    assert received[6]['profile'] == received[7]['profile'] == received[2]['profile']
    assert received[2]['studied_materials'] == []
    assert 'ячейки' in received[6]['studied_materials'][0]['public_description']
    assert 'фотографирования' in received[7]['studied_materials'][0]['public_description']
    assert 'id' not in received[6]['studied_materials'][0]
    assert capsys.readouterr().out.count('Краткое описание.') == 8
    assert client._http.is_closed


def test_studied_materials_privacy_and_limit():
    """Не передаёт приватные поля истории и отклоняет избыточный контекст до API."""
    requests = []

    def handler(request):
        """Проверяет фактическую историю на границе провайдера."""
        requests.append(request)
        assert 'DO_NOT_SEND' not in request.content.decode()
        facts = json.loads(json.loads(request.content)['messages'][1]['content'])
        assert len(facts['studied_materials']) == 1
        assert facts['studied_materials'][0]['public_description'] == 'Предыдущий курс'
        assert 'id' not in facts['studied_materials'][0]
        return httpx.Response(200, json=completion())

    async def run():
        """Проверяет JSON-вызов с ORM-подобной историей и ограничение её размера."""
        previous = material(description='Предыдущий курс')
        previous.id = UUID(int=2)
        async with LLMClient(settings(), transport=httpx.MockTransport(handler)) as client:
            result = json.loads(await client.generate_description_json(
                material(), studied_materials=[material(), previous],
            ))
            assert result['status'] == 'succeeded'
            with pytest.raises(ValueError):
                await client.generate_course_description(material(), studied_materials=[previous] * 11)
            assert len(requests) == 1
    asyncio.run(run())


def test_unknown_profile_version_keeps_codes_without_labels():
    """Не расшифровывает старые или неизвестные коды по чужой версии словаря."""
    from .llm_schemas import ProfileInput

    profile = ProfileInput(stage_code='starting', profile_config_version='999999')
    payload = profile.to_prompt()
    assert payload['stage_code'] == 'starting'
    assert 'stage_label' not in payload


@pytest.mark.parametrize('provider_ok', [True, False])
def test_mistral_mixed_scenarios(monkeypatch, capsys, provider_ok):
    """Отличает ожидаемый отказ без аннотации от сбоя провайдера на смешанных входах."""
    from . import check_mistral

    received = []

    def handler(request):
        """Фиксирует входы реального клиента с подменённым HTTP-транспортом."""
        received.append(json.loads(json.loads(request.content)['messages'][1]['content']))
        return httpx.Response(200, json=completion()) if provider_ok else httpx.Response(503)

    client = LLMClient(settings(), transport=httpx.MockTransport(handler))
    monkeypatch.setattr(check_mistral, 'LLMClient', lambda: client)
    assert asyncio.run(check_mistral.main(mixed=True)) == int(not provider_ok)
    assert len(received) == 4
    assert {item['material']['kind'] for item in received} == {'article', 'course'}
    assert received[1]['profile']['industry_label'] == 'Тестовая отрасль'
    assert received[1]['studied_materials']
    assert received[2]['is_studied'] is True
    assert all('metadata' not in item['material'] for item in received)
    output = capsys.readouterr().out
    assert output.count('Краткое описание.') == (4 if provider_ok else 0)
    assert 'missing_public_description' in output
    assert 'Описание не сформировано:' in output
    if not provider_ok:
        assert 'http_503' in output
