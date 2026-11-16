"""Пять ручных проверок Mistral на синтетических данных без обращения к БД."""

import argparse
import asyncio
import json
from uuid import UUID

from src.config.settings import MISTRAL

from .llm import LLMClient
from .llm_schemas import MaterialInput, ProfileInput

CASES = [
    {
        'kind': 'article',
        'title': 'Доходы и расходы: первые шаги',
        'public_description': 'Статья объясняет, как различать доходы и расходы малого бизнеса и вести их учёт.',
        'access_type': 'unknown',
    },
    {
        'kind': 'course',
        'title': 'Таблицы для предпринимателя',
        'public_description': (
            'Вводный курс по Microsoft Excel. Участник учится вводить данные, '
            'использовать функцию СУММ и фильтровать строки. В курсе 3 урока с упражнениями.'
        ),
        'access_type': 'free',
        'duration_minutes': 45,
        'difficulty_level': 'beginner',
        'learning_role': 'intro',
        'annotation_source': 'manual',
        'annotation_version': 'synthetic-v1',
    },
    {
        'kind': 'course',
        'title': 'Переговоры с поставщиками',
        'public_description': (
            'Курс учит готовить вопросы поставщику, сравнивать предложения по цене и срокам '
            'поставки, фиксировать договорённости. Включает 4 разбора переговоров и 2 упражнения.'
        ),
        'access_type': 'paid',
        'duration_minutes': 120,
        'difficulty_level': 'intermediate',
    },
    {
        'kind': 'article',
        'title': 'UTM-метки без путаницы',
        'public_description': (
            'Статья объясняет назначение параметров utm_source, utm_medium и utm_campaign. '
            'На примере Яндекс Метрики показано, как различать переходы из двух рекламных каналов.'
        ),
        'access_type': 'free',
    },
    {
        'kind': 'course',
        'title': 'Обратная связь в команде',
        'public_description': None,
        'access_type': 'unknown',
    },
]

PROFILE_CASES = [
    ('Без профиля', None, False, []),
    ('Запуск бизнеса, финансы, краткая подача', {
        'stage_code': 'starting', 'goal_code': 'finance', 'learning_mode': 'quick',
    }, False, []),
    ('Работающий бизнес, финансы, практика', {
        'stage_code': 'operating', 'goal_code': 'finance', 'learning_mode': 'practical',
    }, False, []),
    ('Тот же профиль, материал отмечен изученным', {
        'stage_code': 'operating', 'goal_code': 'finance', 'learning_mode': 'practical',
    }, True, []),
    ('Управление, последовательное обучение, отметка не проверялась', {
        'stage_code': 'operating', 'goal_code': 'management', 'learning_mode': 'trajectory',
    }, None, []),
    ('Неполный профиль, предпочтения не указаны', {}, None, []),
    ('Изучен связанный курс: скрытый контекст', {
        'stage_code': 'operating', 'goal_code': 'finance', 'learning_mode': 'practical',
    }, False, [{
        'id': UUID(int=101), 'kind': 'course', 'title': 'Знакомство с электронными таблицами',
        'public_description': 'Курс объясняет устройство электронной таблицы: строки, столбцы и ячейки.',
        'access_type': 'free', 'source_version': 'mistral-test-v1',
    }]),
    ('Изучена другая тема: не выдумывать связь', {
        'stage_code': 'operating', 'goal_code': 'finance', 'learning_mode': 'practical',
    }, False, [{
        'id': UUID(int=102), 'kind': 'article', 'title': 'Фотография товара',
        'public_description': 'Статья объясняет выбор фона и освещения для фотографирования товара.',
        'access_type': 'free', 'source_version': 'mistral-test-v1',
    }]),
]


async def main(profiles: bool = False, mixed: bool = False) -> int:
    """Проверяет материалы, профили на одном курсе либо смешанные сочетания входов."""
    cases = (
        [(label, CASES[1], profile, studied, history) for label, profile, studied, history in PROFILE_CASES]
        if profiles else [(case['title'], case, None, False, []) for case in CASES]
    )
    if mixed:
        cases = [
            ('Статья: запуск бизнеса, финансы, кратко', CASES[0], PROFILE_CASES[1][1], False, []),
            ('Excel: практика, тестовая отрасль, связанный материал', CASES[1], {
                **PROFILE_CASES[2][1], 'industry_code': 'demo',
            }, False, PROFILE_CASES[6][3]),
            ('Платный курс: повторение, управление', {
                **CASES[2], 'learning_role': 'practice', 'annotation_source': 'manual',
                'annotation_version': 'synthetic-v1',
            }, {'stage_code': 'operating', 'goal_code': 'management', 'learning_mode': 'practical'}, True, []),
            ('UTM: маркетинг, последовательное обучение, несвязанная история', CASES[3], {
                'stage_code': 'starting', 'goal_code': 'marketing', 'learning_mode': 'trajectory',
            }, None, PROFILE_CASES[6][3]),
            ('Нет аннотации: неполный профиль, неизвестная отрасль', CASES[4], {
                'industry_code': 'unknown_test', 'goal_code': 'management',
            }, None, PROFILE_CASES[7][3]),
        ]
    failed = False
    async with LLMClient() as client:
        print(f'Модель: {MISTRAL}. Примеров: {len(cases)}. Данные синтетические.', flush=True)
        if profiles:
            print('Проверяются профиль, отметка и содержание изученных материалов; владение навыками не утверждается.', flush=True)
            print('Подписи кодов берутся из версии конфигурации профиля.', flush=True)
        for index, (label, case, profile_data, studied, history_data) in enumerate(cases, start=1):
            material = MaterialInput(id=UUID(int=2 if profiles and not mixed else index), source_version='mistral-test-v1', **case)
            profile = ProfileInput(profile_config_version='1', **profile_data) if profile_data is not None else None
            history = [MaterialInput.model_validate(item) for item in history_data]
            inputs = {
                'material': material.model_dump(mode='json', exclude={'id', 'source_version'}),
                'profile': profile.to_prompt() if profile else None,
                'is_studied': studied,
                'studied_materials': [item.model_dump(mode='json', exclude={'id', 'source_version'}) for item in history],
            }
            print(f'\n--- Пример {index}/{len(cases)}: {label} ---', flush=True)
            print('Входные данные:', json.dumps(inputs, ensure_ascii=False, indent=2), flush=True)
            result = json.loads(await client.generate_description_json(
                material, profile, is_studied=studied, studied_materials=history,
            ))
            print(f"Статус: {result['status']}; время: {result['latency_ms'] / 1000:.2f} с", flush=True)
            headings = {'succeeded': 'Ответ модели:', 'fallback': 'Резервная аннотация:', 'failed': 'Описание не сформировано:'}
            print(headings[result['status']], flush=True)
            print(result['text'] or '(нет текста)', flush=True)
            print('Расход:', json.dumps(result['usage'], ensure_ascii=False), flush=True)
            print('Ошибка:', result['error'], flush=True)
            missing_description = not (material.public_description or '').strip()
            expected_rejection = (
                missing_description and result['status'] == 'failed'
                and result['error'] == 'missing_public_description' and result['text'] is None
            )
            failed |= not expected_rejection if missing_description else result['status'] != 'succeeded'
        print('\nИтоговый расход:', json.dumps(client.get_usage(), ensure_ascii=False, indent=2), flush=True)
    return int(failed)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--profiles', action='store_true', help='Сравнить восемь вариантов профиля и истории на одном курсе')
    mode.add_argument('--mixed', action='store_true', help='Пять сочетаний разных материалов, профилей и истории')
    args = parser.parse_args()
    raise SystemExit(asyncio.run(main(profiles=args.profiles, mixed=args.mixed)))
