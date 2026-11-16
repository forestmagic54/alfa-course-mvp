from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.config import load_demo_config
from src.db.crud.commerce import CommerceCRUD
from src.db.crud.onboarding import OnboardingCRUD
from src.db.crud.users import UsersCRUD
from src.db.models.users import OnboardingResponses, UserProfiles
from src.services.types import OnboardingInputData

CURRENT_QUESTIONNAIRE_CONFIGS = {'simple': '2'}


class QuestionnaireUnavailable(Exception):
    pass


class QuestionnaireVersionMismatch(Exception):
    pass


class InvalidAnswers(Exception):
    def __init__(self, fields):
        self.fields = fields


def current_config(form_type):
    version = CURRENT_QUESTIONNAIRE_CONFIGS.get(form_type)
    if version is None:
        raise QuestionnaireUnavailable
    config = load_demo_config(version)
    if config['questionnaire']['form_type'] != form_type:
        raise ValueError('Questionnaire configuration type mismatch')
    return config


def validate_answers(form_type, version, status, answers, config=None):
    config = config or current_config(form_type)
    questionnaire = config['questionnaire']
    if questionnaire['form_type'] != form_type:
        raise QuestionnaireUnavailable
    if questionnaire['questionnaire_version'] != version:
        raise QuestionnaireVersionMismatch
    questions = {q['key']: q for q in questionnaire['questions']}
    invalid = []
    if status == 'skipped' and answers:
        invalid.append('answers')
    for key, value in answers.items():
        question = questions.get(key)
        if question is None:
            invalid.append(f'answers.{key}')
            continue
        if value is None:
            continue
        kind = question['type']
        if kind == 'text':
            valid = isinstance(value, str) and bool(value) and len(value) <= question['max_length']
        else:
            options = {option['value'] for option in question['options']}
            if kind == 'single_select':
                valid = isinstance(value, str) and value in options
            else:
                valid = (isinstance(value, list) and bool(value)
                         and all(isinstance(item, str) and item in options for item in value)
                         and len(set(value)) == len(value))
        if not valid:
            invalid.append(f'answers.{key}')
    if status == 'completed':
        invalid.extend(f'answers.{key}' for key, q in questions.items()
                       if q['required'] and (key not in answers or answers[key] is None))
    if invalid:
        raise InvalidAnswers(list(dict.fromkeys(invalid)))
    return config


def profile_values(profile, answers, config):
    projection = config['answer_projection']
    values = {target: answers[key] for key, target in projection.items() if key in answers}
    if profile and profile.profile_config_version != config['profile_config_version']:
        old = load_demo_config(profile.profile_config_version)
        old_projection = old['answer_projection']
        old_questions = {q['key']: q for q in old['questionnaire']['questions']}
        new_questions = {q['key']: q for q in config['questionnaire']['questions']}
        for key, target in old_projection.items():
            value = getattr(profile, target)
            if target in values or value is None:
                continue
            if (projection.get(key) != target or key not in new_questions
                    or old_questions[key]['type'] != 'single_select'
                    or new_questions[key]['type'] != 'single_select'
                    or value not in {o['value'] for o in new_questions[key]['options']}):
                raise ValueError('Profile configuration migration required')
            values[target] = value
        if profile.industry_code is not None and profile.industry_code not in {x['code'] for x in config['industries']}:
            raise ValueError('Profile configuration migration required')
    return values


@dataclass(frozen=True)
class EffectivePreferences:
    config: Any
    goal: dict
    industry: str | None
    learning_mode: str | None
    profile_version: str | None
    goal_code: str | None = None
    stage_code: str | None = None
    industry_code: str | None = None

    @property
    def personalized(self) -> bool:
        return bool(self.goal_code or self.industry)


def effective_preferences(profile: UserProfiles | None, onboarding: OnboardingInputData | None) -> EffectivePreferences:
    config = load_demo_config(profile.profile_config_version) if profile else load_demo_config()
    values = {key: getattr(profile, key, None) for key in ('goal_code', 'industry_code', 'stage_code')} if profile else {}
    learning_mode = getattr(profile, 'learning_mode', None)
    if onboarding is not None:
        config = validate_answers(onboarding['form_type'], onboarding['questionnaire_version'],
                                  onboarding['status'], onboarding['answers'])
        if onboarding['status'] != 'skipped':
            updated = profile_values(profile, onboarding['answers'], config)
            values.update(updated)
            learning_mode = updated.get('learning_mode', learning_mode)
    goal = config['goals'].get(values.get('goal_code'), {})
    industry = next((x['industry_id'] for x in config['industries'] if x['code'] == values.get('industry_code')), None)
    return EffectivePreferences(config, goal, industry, learning_mode,
                                config['profile_config_version'] if values else None, values.get('goal_code'),
                                values.get('stage_code'), values.get('industry_code'))


class OnboardingService:
    def __init__(self, session: AsyncSession, users: UsersCRUD, onboarding: OnboardingCRUD, commerce: CommerceCRUD):
        self.session = session
        self.users = users
        self.onboarding = onboarding
        self.commerce = commerce

    async def save(self, user_id: UUID, form_type: str, version: str, status: str,
                   answers: dict[str, object]) -> OnboardingResponses:
        config = validate_answers(form_type, version, status, answers)
        users, onboarding, commerce = self.users, self.onboarding, self.commerce
        try:
            await users.lock(user_id)
            latest = await onboarding.latest(user_id)
            if latest and (latest.form_type, latest.questionnaire_version, latest.status, latest.answers) == (form_type, version, status, answers):
                await self.session.commit()
                return latest
            previous_completed = await users.onboarding_completed(user_id) if status == 'completed' else False
            profile = await onboarding.profile(user_id) if status != 'skipped' else None
            values = profile_values(profile, answers, config) if status != 'skipped' else {}
            now = datetime.now(UTC)
            response = await onboarding.create_response(user_id=user_id, form_type=form_type,
                questionnaire_version=version, status=status, answers=answers, created_at=now,
                submitted_at=now, completed_at=now if status == 'completed' else None)
            if values:
                if profile is None:
                    profile = await onboarding.create_profile(user_id=user_id)
                for key, value in values.items():
                    setattr(profile, key, value)
                profile.profile_config_version = config['profile_config_version']
                profile.source_onboarding_response_id = response.id
                profile.updated_at = now
            if (status == 'completed' and not previous_completed
                    and not await commerce.has_onboarding_grant(user_id)
                    and not await commerce.has_course_purchase(user_id)):
                discount = config['welcome_discount']
                await commerce.create_onboarding_grant(user_id, now, discount['percent'], discount['duration_days'])
            await self.session.commit()
            return response
        except BaseException:
            await self.session.rollback()
            raise
