import json
from datetime import datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest

from src.api.account.schemas import Account
from src.api.auth.schemas import Credentials

ROOT = Path(__file__).resolve().parents[1]


def no_duplicates(pairs):
    result = {}
    for key, value in pairs:
        assert key not in result, key
        result[key] = value
    return result


def load(path):
    return json.loads((ROOT / path).read_text(), object_pairs_hook=no_duplicates)


def date(value):
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    assert result.tzinfo is not None
    return result


@pytest.fixture(params=['1', '2'])
def data(request):
    version = request.param
    path = 'tests/fixtures/demo.json' if version == '1' else 'src/config/demo/fixture-v2.json'
    return load(path), load(f'src/config/demo/v{version}.json')


def test_demo_accounts_are_accepted_by_auth_and_account_schemas(data):
    fixture, _ = data
    for user in fixture['mvp']['users']:
        assert Credentials(email=user['email'], password='demo-password').email == user['email']
        assert Account(**user, onboarding_completed=False).email == user['email']


def test_ids_dates_and_references(data):
    fixture, config = data
    source, mvp = fixture['source'], fixture['mvp']
    all_ids = []
    for tables in (source, mvp):
        for rows in tables.values():
            ids = [row.get('Id', row.get('id')) for row in rows]
            ids = [x for x in ids if x is not None]
            assert len(ids) == len(set(ids))
            all_ids.extend(ids)
            for row in rows:
                for key, value in row.items():
                    if value is None:
                        continue
                    if key == 'id' or key == 'Id' or key.endswith('_id') or key.endswith('Id'):
                        UUID(value)
                    if key.endswith('_at') or key in ('Published', 'valid_from', 'valid_until', 'granted_at', 'expires_at', 'redeemed_at'):
                        date(value)
    assert len(all_ids) == len(set(all_ids))
    date(fixture['checked_at'])
    def ids(rows, key):
        return {r[key] for r in rows}
    users = ids(mvp['users'], 'id')
    materials = ids(mvp['materials'], 'id')
    folders = {r['id']: r for r in mvp['favorite_folders']}
    responses = {r['id']: r for r in mvp['onboarding_responses']}
    lists = {r['id']: r for r in mvp['recommendation_lists']}
    for table in ('onboarding_responses', 'user_profiles', 'favorite_folders', 'recommendation_lists', 'purchases', 'subscription_access', 'discount_grants', 'email_preferences'):
        assert all(r['user_id'] in users for r in mvp[table])
    for profile in mvp['user_profiles']:
        response = responses[profile['source_onboarding_response_id']]
        assert response['user_id'] == profile['user_id']
        assert response['status'] == 'completed' and response['completed_at']
        assert profile['profile_config_version'] == config['profile_config_version']
        assert all(profile[target] == response['answers'][key] for key, target in config['answer_projection'].items())
    for entry in mvp['recommendation_lists']:
        if entry['onboarding_response_id']:
            assert responses[entry['onboarding_response_id']]['user_id'] == entry['user_id']
    assert all(r['folder_id'] in folders and r['material_id'] in materials for r in mvp['favorites'])
    assert len({(r['folder_id'], r['material_id']) for r in mvp['favorites']}) == len(mvp['favorites'])
    assert all(sum(f['user_id'] == u and f['is_default'] for f in folders.values()) == 1 for u in users)
    assert any(sum(f['material_id'] == material for f in mvp['favorites']) > 1 for material in materials)
    studies = mvp['user_material_studies']
    pairs = {(r['user_id'], r['material_id']) for r in studies}
    assert len(pairs) == len(studies) and pairs
    assert all(user in users and material in materials for user, material in pairs)
    user, material = next(iter(pairs))
    assert any((other, material) not in pairs for other in users if other != user)
    assert len({r['list_id'] for r in mvp['recommendation_items'] if r['material_id'] == material and lists[r['list_id']]['user_id'] == user and lists[r['list_id']]['list_type'] == 'trajectory'}) >= 2
    for row in mvp['recommendation_items']:
        assert 'is_studied' not in row
        assert row['list_id'] in lists and row['material_id'] in materials and row['position'] > 0
    for key in ('position', 'material_id'):
        assert len({(r['list_id'], r[key]) for r in mvp['recommendation_items']}) == len(mvp['recommendation_items'])
    assert all(r['course_id'] in ids(source['Courses'], 'Id') and r['subscription_tariff_id'] is None for r in mvp['purchases'])
    assert all(r['subscription_id'] in ids(source['Subscription'], 'Id') for r in mvp['subscription_access'])


def test_catalog_and_configuration(data):
    fixture, config = data
    source, mvp = fixture['source'], fixture['mvp']
    by_table = {table: {r['Id']: r for r in rows if 'Id' in r} for table, rows in source.items()}
    kinds = {'course': 'Courses', 'article': 'Articles', 'document': 'Documents'}
    by_source = {}
    for material in mvp['materials']:
        kind, table, sid = material['kind'], material['source_table'], material['source_id']
        assert kinds[kind] == table and sid in by_table[table]
        assert material['id'] != sid and (table, sid) not in by_source
        by_source[table, sid] = material
        assert material['verified_course_id'] == (sid if kind == 'course' else None)
        assert material['learning_role'] in (None, 'intro', 'practice', 'advanced')
        assert material['difficulty_level'] in (None, 'beginner', 'intermediate', 'advanced')
        if material['source_version'] == 'demo-ml-pending':
            assert material['annotation_source'] is None and material['annotation_version'] is None
            assert material['learning_role'] is None and not material['is_recommendable']
        else:
            assert material['annotation_source'] == 'manual' and material['annotation_version']
        assert material.get('metadata') is None or material['metadata_schema_version']
        row = by_table[table][sid]
        if kind == 'course' and row.get('TypeId') is not None:
            assert row['TypeId'] in by_table['CourseTypes']
        if material['is_recommendable']:
            assert row['StatusId'] in config['catalog']['published_status_ids'] and not row['IsDeleted']
            if kind in ('course', 'article'):
                assert not row['IsClosed']
            if kind == 'article':
                assert row['IsPublic'] and row['Published'] and not row['IsLesson']
            if kind == 'document':
                assert row['TypeId'] in by_table['DocumentTypes'] and row['FileId'] in by_table['Files']
                assert not by_table['Files'][row['FileId']]['IsDeleted'] and row['Published']
    settings = by_table['ContentSettings']
    for setting in settings.values():
        matches = [kind for kind, entity in config['catalog']['entity_type_ids'].items() if entity == setting['EntityTypeId']]
        assert len(matches) == 1 and (kinds[matches[0]], setting['EntityId']) in by_source
        assert setting['StatusId'] in by_table['Statuses']
    for table, ref, target in [('ContentSettingsTopics','TopicId','Topics'), ('ContentSettingsTags','TagId','Tags'), ('ContentSettingsIndustries','IndustryId','Industries')]:
        pairs = [(r['ContentSettingsId'], r[ref]) for r in source[table]]
        assert len(pairs) == len(set(pairs))
        assert all(a in settings and b in by_table[target] for a, b in pairs)
    for goal in config['goals']:
        topics = config['goals'][goal]['topic_ids']
        tags = config['goals'][goal]['tag_ids']
        assert set(topics) <= by_table['Topics'].keys() and set(tags) <= by_table['Tags'].keys()
        candidate_settings = {r['ContentSettingsId'] for r in source['ContentSettingsTopics'] if r['TopicId'] in topics}
        candidates = [by_source[kinds[next(k for k, v in config['catalog']['entity_type_ids'].items() if v == settings[s]['EntityTypeId'])], settings[s]['EntityId']] for s in candidate_settings]
        assert {(r['kind'], r['learning_role'], r['difficulty_level']) for r in candidates} >= {('article','intro','beginner'), ('document','practice','intermediate'), ('course','advanced','advanced')}
    assert set(config['catalog']['popularity']) == {r['id'] for r in mvp['materials']}
    assert config['catalog']['popularity_tiebreak'] == ['title', 'id']
    assert all(set(s['tag_ids']) <= by_table['Tags'].keys() for s in config['skills'])
    assert any(not r['is_recommendable'] for r in mvp['materials'])
    if config['version'] == '1':
        assert any(r['learning_role'] is None and r['difficulty_level'] is None for r in mvp['materials'])


def test_access_and_account_states(data):
    fixture, config = data
    source, mvp = fixture['source'], fixture['mvp']
    now = date(fixture['checked_at'])
    free = set(config['access']['free_material_ids'])
    prices = config['access']['course_prices']
    assert free and prices and config['access']['offer_order'] == ['course', 'subscription']
    for material in mvp['materials']:
        if material['access_type'] == 'free':
            assert material['id'] in free and material['url']
        elif material['access_type'] == 'paid':
            assert material['source_id'] in prices
        else:
            assert material['access_type'] == 'unknown' and material['id'] not in free and material['source_id'] not in prices
    for price in list(prices.values()) + [t['price'] for t in config['subscriptions']['tariffs'].values()]:
        assert price['amount_minor'] > 0 and price['currency'] == 'RUB' and price['source'] == 'demo_config'
    assert all(t['duration_months'] > 0 for t in config['subscriptions']['tariffs'].values())
    assert set(prices) <= {r['CourseId'] for r in source['CourseTariffBindings']}
    assert source['CourseSubscriptions'] and any(r['CourseId'] in prices for r in source['CourseSubscriptions'])
    assert all(r['SubscriptionId'] in {s['Id'] for s in source['Subscription']} and r['CourseId'] in {c['Id'] for c in source['Courses']} for r in source['CourseSubscriptions'])
    for tid, tariff in config['subscriptions']['tariffs'].items():
        assert any(r['Id'] == tid and r['SubscriptionId'] == tariff['subscription_id'] for r in source['SubscriptionTariffs'])
    assert config['welcome_discount'] == {'percent': 10, 'duration_days': 7, 'first_paid_course_only': True, 'subscription_eligible': False}
    discount_states = set()
    for grant in mvp['discount_grants']:
        start, end = date(grant['granted_at']), date(grant['expires_at'])
        assert end - start == timedelta(days=7) and grant['discount_percent'] == 10 and grant['discount_amount_minor'] is None
        redeemed = grant['redeemed_at']
        if redeemed:
            assert start <= date(redeemed) < end
        discount_states.add('redeemed' if redeemed else 'expired' if now >= end else 'available')
    assert discount_states == {'available', 'redeemed', 'expired'}
    states = set()
    for access in mvp['subscription_access']:
        start, end = date(access['valid_from']), date(access['valid_until'])
        assert start < end
        revoked = access['revoked_at']
        if revoked:
            assert start <= date(revoked) <= now
        states.add('revoked' if revoked and date(revoked) <= now else 'active' if start <= now < end else 'expired')
    assert states == {'active', 'expired', 'revoked'}
    assert {r['marketing_consent'] for r in mvp['email_preferences']} == {True, False}
    assert any(r['unsubscribed_at'] and not r['marketing_consent'] and r['consent_version'] for r in mvp['email_preferences'])
    assert all(not r['marketing_consent'] or r['consent_version'] == config['email']['consent_version'] for r in mvp['email_preferences'])
    cold = next(r['id'] for r in mvp['users'] if r['email'] == 'cold@example.com')
    assert all(r['user_id'] != cold for table in ('onboarding_responses', 'purchases', 'subscription_access') for r in mvp[table])
    assert all(r['email'].endswith('@example.com') for r in mvp['users'])
    assert len({r['email'] for r in mvp['users']}) == len(mvp['users'])
    assert 'events' not in mvp and 'generation_runs' not in mvp
    forbidden = {'password', 'password_hash', 'token', 'jwt', 'secret', 'UserId', 'source_user_id', 'progress', 'is_completed', 'completed'}
    def check(value):
        if isinstance(value, dict):
            assert not forbidden.intersection(value)
            for item in value.values():
                check(item)
        elif isinstance(value, list):
            for item in value:
                check(item)
    check(fixture)


def test_questionnaire_and_returned_account(data):
    fixture, config = data
    mvp = fixture['mvp']
    questions = {q['key']: q for q in config['questionnaire']['questions']}
    assert set(questions) == {'business_stage', 'current_task', 'learning_mode'}
    assert [questions[k]['required'] for k in questions] == [True, True, False]
    assert {o['value'] for o in questions['business_stage']['options']} == {'starting', 'operating'}
    assert {o['value'] for o in questions['current_task']['options']} == {'sales', 'marketing', 'finance', 'management', 'other'}
    assert {o['value'] for o in questions['learning_mode']['options']} == {'quick', 'practical', 'trajectory'}
    assert {r['goal_code'] for r in mvp['user_profiles']} == {'sales', 'finance'}
    user = next(r['id'] for r in mvp['users'] if r['email'] == 'returned@example.com')
    roadmap = next(r for r in mvp['recommendation_lists'] if r['user_id'] == user)
    assert roadmap['list_type'] == 'trajectory' and roadmap['mode'] == 'personalized'
    assert roadmap['recommendation_format'] == 'deep' and roadmap['saved_at'] and roadmap['title'] and roadmap['summary']
    steps = sorted((r for r in mvp['recommendation_items'] if r['list_id'] == roadmap['id']), key=lambda r: r['position'])
    assert [r['position'] for r in steps] == [1, 2, 3]
    assert [r['step_role'] for r in steps] == ['intro', 'practice', 'advanced']
    assert all(r['explanation'] for r in steps) and steps[0]['transition_text'] is None
    assert all(r['transition_text'] for r in steps[1:])
    now = date(fixture['checked_at'])
    assert any(r['user_id'] == user and date(r['valid_from']) <= now < date(r['valid_until']) and r['revoked_at'] is None for r in mvp['subscription_access'])
    assert config['email']['delivery'] == 'local_only'
    assert config['migration_constraints']['excluded_tables'] == ['mvp.events']
    assert 'agreement' in config['migration_constraints']['generation_runs']
