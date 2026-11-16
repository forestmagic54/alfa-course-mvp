import asyncio
from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest

from src.config import load_demo_config
from src.services import onboarding as service

CONFIG = load_demo_config('1')


def validate(answers, status='completed', version='1', config=CONFIG):
    return service.validate_answers(config['questionnaire']['form_type'], version, status, answers, config)


def test_answers_and_versions():
    validate({'business_stage': 'starting', 'current_task': 'sales'})
    validate({'learning_mode': None}, 'partial')
    validate({}, 'skipped')
    for answers, status, field in [
        ({'x': 'x'}, 'partial', 'answers.x'),
        ({'current_task': True}, 'partial', 'answers.current_task'),
        ({'current_task': 'missing'}, 'partial', 'answers.current_task'),
        ({'business_stage': None}, 'completed', 'answers.business_stage'),
        ({'learning_mode': None}, 'skipped', 'answers'),
    ]:
        with pytest.raises(service.InvalidAnswers) as exc:
            validate(answers, status)
        assert field in exc.value.fields
    with pytest.raises(service.QuestionnaireVersionMismatch):
        validate({}, 'partial', 'old')


def test_other_question_types():
    config = {'questionnaire': {'form_type': 'advanced', 'questionnaire_version': '2', 'questions': [
        {'key': 'many', 'type': 'multi_select', 'required': True, 'options': [{'value': 'a'}, {'value': 'b'}]},
        {'key': 'text', 'type': 'text', 'required': False, 'max_length': 3},
    ]}}
    validate({'many': ['a', 'b'], 'text': 'yes'}, version='2', config=config)
    for answers in ({'many': ['a', 'a']}, {'many': []}, {'many': [True]}, {'many': ['a'], 'text': 'long'}):
        with pytest.raises(service.InvalidAnswers):
            validate(answers, version='2', config=config)


class Session:
    def __init__(self):
        self.commits = self.rollbacks = 0

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1


class State:
    def __init__(self):
        self.events = []
        self.history = []
        self.profiles = {}
        self.grants = []
        self.purchase = set()
        self.fail = None


def setup(monkeypatch):
    state = State()

    class Users:
        def __init__(self, session): pass
        async def lock(self, user_id): state.events.append('lock')
        async def onboarding_completed(self, user_id):
            return any(r.user_id == user_id and r.status == 'completed' for r in state.history)

    class Onboarding:
        def __init__(self, session): pass
        async def latest(self, user_id):
            state.events.append('latest')
            return next((r for r in reversed(state.history) if r.user_id == user_id), None)
        async def profile(self, user_id): return state.profiles.get(user_id)
        async def create_response(self, **values):
            response = SimpleNamespace(id=uuid4(), **values)
            state.history.append(response)
            return response
        async def create_profile(self, **values):
            if state.fail == 'profile':
                raise RuntimeError('profile')
            profile = SimpleNamespace(stage_code=None, industry_code=None, goal_code=None, learning_mode=None, **values)
            state.profiles[values['user_id']] = profile
            return profile

    class Commerce:
        def __init__(self, session): pass
        async def has_onboarding_grant(self, user_id): return any(g[0] == user_id for g in state.grants)
        async def has_course_purchase(self, user_id): return user_id in state.purchase
        async def create_onboarding_grant(self, user_id, now, percent, duration):
            if state.fail == 'grant':
                raise RuntimeError('grant')
            state.grants.append((user_id, now, percent, now + timedelta(days=duration)))

    state.users_class, state.onboarding_class, state.commerce_class = Users, Onboarding, Commerce
    return state


def save(state, session, user, answers, status='completed'):
    instance = service.OnboardingService(session, state.users_class(session), state.onboarding_class(session), state.commerce_class(session))
    return asyncio.run(instance.save(user, 'simple', '1', status, answers))


def test_save_merge_repeat_and_isolation(monkeypatch):
    state = setup(monkeypatch)
    session, user, other = Session(), uuid4(), uuid4()
    answers = {'business_stage': 'starting', 'current_task': 'sales'}
    first = save(state, session, user, answers)
    assert save(state, session, user, dict(reversed(list(answers.items())))) is first
    assert len(state.history) == 1 and len(state.grants) == 1
    grant = state.grants[0]
    assert grant[2] == 10 and grant[3] - grant[1] == timedelta(days=7)
    save(state, session, user, {'business_stage': None}, 'partial')
    profile = state.profiles[user]
    assert profile.stage_code is None and profile.goal_code == 'sales'
    source = profile.source_onboarding_response_id
    save(state, session, user, {}, 'skipped')
    assert profile.source_onboarding_response_id == source and len(state.grants) == 1
    save(state, session, other, {}, 'skipped')
    assert other not in state.profiles
    assert state.events[:2] == ['lock', 'latest']
    assert session.rollbacks == 0 and session.commits == 5


@pytest.mark.parametrize('condition', ['purchase', 'grant', 'completed'])
def test_no_second_grant(monkeypatch, condition):
    state = setup(monkeypatch)
    user = uuid4()
    if condition == 'purchase':
        state.purchase.add(user)
    if condition == 'grant':
        state.grants.append((user, None, 10, None))
    if condition == 'completed':
        state.history.append(SimpleNamespace(user_id=user, status='completed', form_type='simple', questionnaire_version='1', answers={}))
    save(state, Session(), user, {'business_stage': 'starting', 'current_task': 'sales'})
    assert len(state.grants) == (condition == 'grant')


@pytest.mark.parametrize('failure', ['profile', 'grant'])
def test_write_error_rolls_back(monkeypatch, failure):
    state = setup(monkeypatch)
    state.fail = failure
    session = Session()
    with pytest.raises(RuntimeError):
        save(state, session, uuid4(), {'business_stage': 'starting', 'current_task': 'sales'})
    assert session.rollbacks == 1 and session.commits == 0


def test_routes_read_only_current_user_and_unavailable(monkeypatch):
    from fastapi import HTTPException

    from src.api.onboarding.routes import (
        get_onboarding,
        get_questionnaire,
        put_onboarding,
    )
    from src.api.onboarding.schemas import OnboardingInput, Questionnaire
    from src.api.preferences.routes import get_preferences

    state = setup(monkeypatch)
    monkeypatch.setattr('src.api.onboarding.routes.OnboardingCRUD', state.onboarding_class)
    monkeypatch.setattr('src.api.preferences.routes.OnboardingCRUD', state.onboarding_class)
    user, other = uuid4(), uuid4()
    session = Session()
    assert asyncio.run(get_onboarding(SimpleNamespace(id=other), session)) is None
    assert asyncio.run(get_preferences(SimpleNamespace(id=other), session)) is None
    saved = save(state, session, user, {'business_stage': 'operating', 'current_task': 'sales'})
    assert asyncio.run(get_onboarding(SimpleNamespace(id=user), session)) is saved
    assert asyncio.run(get_onboarding(SimpleNamespace(id=other), session)) is None
    assert asyncio.run(get_preferences(SimpleNamespace(id=other), session)) is None
    assert Questionnaire.model_validate(asyncio.run(get_questionnaire())).form_type == 'simple'
    with pytest.raises(HTTPException) as exc:
        asyncio.run(get_questionnaire('advanced'))
    assert exc.value.status_code == 404 and exc.value.detail['code'] == 'questionnaire_not_available'
    body = OnboardingInput(form_type='advanced', questionnaire_version='1', answers={})
    with pytest.raises(HTTPException) as exc:
        asyncio.run(put_onboarding(body, SimpleNamespace(id=user), service.OnboardingService(
            session, state.users_class(session), state.onboarding_class(session), state.commerce_class(session))))
    assert exc.value.status_code == 404 and exc.value.detail['code'] == 'questionnaire_not_available'
