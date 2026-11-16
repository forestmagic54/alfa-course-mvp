import json
import re
from importlib.resources import files
from types import MappingProxyType
from uuid import UUID


def _freeze(value):
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


def load_demo_config(version: str = '2'):
    if not isinstance(version, str) or not re.fullmatch(r'[1-9][0-9]*', version):
        raise ValueError('Invalid configuration version')
    path = files('src.config').joinpath('demo', f'v{version}.json')
    if not path.is_file():
        raise ValueError(f'Unknown configuration version: {version}')
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        if data['version'] != version or not data['profile_config_version']:
            raise ValueError('Configuration version mismatch')
        questionnaire = data['questionnaire']
        if questionnaire['form_type'] not in ('simple', 'advanced') or not questionnaire['questionnaire_version']:
            raise ValueError('Invalid questionnaire version or type')
        questions = {q['key']: q for q in questionnaire['questions']}
        if len(questions) != len(questionnaire['questions']) or not set(data['answer_projection']) <= set(questions):
            raise ValueError('Invalid questionnaire projection')
        for question in questions.values():
            if (not isinstance(question['required'], bool) or not question['label']
                    or not re.fullmatch(r'[a-z][a-z0-9_]*', question['key'])):
                raise ValueError('Invalid question')
            kind = question['type']
            if kind == 'text':
                if 'options' in question or type(question['max_length']) is not int or question['max_length'] < 1:
                    raise ValueError('Invalid text question')
            elif kind in ('single_select', 'multi_select'):
                if 'max_length' in question:
                    raise ValueError('Invalid select question')
                options = [option['value'] for option in question['options'] if option['label'] and option['value']]
                if not options or len(options) != len(question['options']) or len(options) != len(set(options)):
                    raise ValueError('Invalid question options')
            else:
                raise ValueError('Invalid question type')
        goal_codes = {option['value'] for option in questions['current_task']['options']}
        if not set(data['goals']) <= goal_codes:
            raise ValueError('Unknown goal code')
        for goal in data['goals'].values():
            for key in ('topic_ids', 'tag_ids'):
                for value in goal[key]:
                    UUID(value)
        for industry in data['industries']:
            if not industry['code'] or not industry['label']:
                raise ValueError('Invalid industry')
            UUID(industry['industry_id'])
        for skill in data['skills']:
            UUID(skill['id'])
            if not skill['title']:
                raise ValueError('Invalid skill')
            for tag in skill['tag_ids']:
                UUID(tag)
        catalog = data['catalog']
        for material_id, minutes in catalog.get('duration_minutes', {}).items():
            UUID(material_id)
            if type(minutes) is not int or minutes <= 0:
                raise ValueError('Invalid material duration')
        for value in catalog['published_status_ids'] + list(catalog['entity_type_ids'].values()) + list(catalog['popularity']):
            UUID(value)
        if set(catalog['entity_type_ids']) != {'course', 'article', 'document'} or not catalog['popularity_tiebreak']:
            raise ValueError('Invalid catalog')
        access = data['access']
        for value in access['free_material_ids'] + list(access['course_prices']):
            UUID(value)
        for tariff_id, tariff in data['subscriptions']['tariffs'].items():
            UUID(tariff_id)
            UUID(tariff['subscription_id'])
            if tariff['duration_months'] <= 0:
                raise ValueError('Invalid tariff duration')
        prices = list(access['course_prices'].values()) + [tariff['price'] for tariff in data['subscriptions']['tariffs'].values()]
        if any(price['amount_minor'] < 0 or not price['currency'] or not price['source'] for price in prices):
            raise ValueError('Invalid price')
        discount = data['welcome_discount']
        if not (0 < discount['percent'] <= 100 and discount['duration_days'] > 0 and isinstance(discount['first_paid_course_only'], bool) and isinstance(discount['subscription_eligible'], bool)):
            raise ValueError('Invalid discount')
        if not access['offer_order'] or not data['favorites']['default_folder_name'] or not all(data['email'][key] for key in ('delivery', 'consent_version', 'consent_text')):
            raise ValueError('Invalid application configuration')
        data['migration_constraints']['excluded_tables']
    except (KeyError, TypeError, AttributeError, json.JSONDecodeError) as exc:
        raise ValueError('Invalid demo configuration') from exc
    return _freeze(data)
