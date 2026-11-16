import asyncio
import hashlib
import json
import re
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from src.clients.llm_schemas import MaterialInput, ProfileInput
from src.db.crud.material_explanations import MaterialExplanationsCRUD
from src.db.models.material_explanations import MaterialExplanations
from src.services.onboarding import effective_preferences


def preferences_hash(preferences) -> str:
    values = [preferences.goal_code, preferences.industry_code, preferences.stage_code,
              preferences.learning_mode, preferences.profile_version or preferences.config['profile_config_version']]
    return hashlib.sha256(json.dumps(values, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def usable(row: MaterialExplanations | None, profile_hash: str, context_hash: str, source_version: str) -> bool:
    return bool(row and row.explanation and row.profile_hash == profile_hash
                and row.context_hash == context_hash and row.source_version == source_version)


def may_generate(row: MaterialExplanations, profile_hash: str, now: datetime) -> bool:
    if row.lease_until is not None and now < row.lease_until:
        return False
    if row.attempted_at is not None and now < row.attempted_at + timedelta(minutes=5):
        return False
    return (row.generated_at is None or row.profile_hash != profile_hash
            or now >= row.generated_at + timedelta(days=7))


class ExplanationReader:
    def __init__(self, explanations, onboarding):
        self.explanations = explanations
        self.onboarding = onboarding

    async def read(self, material, user_id: UUID | None) -> str | None:
        default = (getattr(material, 'default_offer_text', None) or '').strip() or None
        if user_id is None:
            return default
        profile = await self.onboarding.fresh_profile(user_id)
        profile_hash = preferences_hash(effective_preferences(profile, None))
        row = await self.explanations.get(user_id, material.id)
        return row.explanation if usable(row, profile_hash, profile_hash, material.source_version) else default


class ExplanationLeaseService:
    def __init__(self, session: AsyncSession, explanations: MaterialExplanationsCRUD):
        self.session = session
        self.explanations = explanations

    async def acquire(self, user_id: UUID, material_id: UUID, profile_hash: str,
                      now: datetime, duration: timedelta) -> UUID | None:
        try:
            row = await self.explanations.lock(user_id, material_id)
            if not may_generate(row, profile_hash, now):
                await self.session.rollback()
                return None
            lease_id = uuid4()
            row.lease_id = lease_id
            row.lease_until = now + duration
            row.attempted_at = now
            await self.session.commit()
            return lease_id
        except BaseException:
            await self.session.rollback()
            raise

    async def finish(self, user_id: UUID, material_id: UUID, lease_id: UUID, now: datetime, *,
                     explanation: str | None, offer_text: str | None = None,
                     profile_hash: str, context_hash: str, source_version: str) -> bool:
        try:
            row = await self.explanations.lock(user_id, material_id)
            if row.lease_id != lease_id or row.lease_until is None or now >= row.lease_until:
                await self.session.rollback()
                return False
            row.lease_id = None
            row.lease_until = None
            if explanation is not None and explanation.strip():
                row.explanation = explanation.strip()
                row.offer_text = offer_text
                row.profile_hash = profile_hash
                row.context_hash = context_hash
                row.source_version = source_version
                row.generated_at = now
                row.attempted_at = None
            await self.session.commit()
            return True
        except BaseException:
            await self.session.rollback()
            raise


class MaterialExplanationService:
    def __init__(self, session, catalog, onboarding, users, explanations, client, timeout):
        self.session, self.catalog, self.onboarding, self.users = session, catalog, onboarding, users
        self.explanations, self.client, self.timeout = explanations, client, timeout
        self.leases = ExplanationLeaseService(session, explanations)

    async def generate(self, user_id: UUID, material_id: UUID, onboarding: dict | None):
        material = await self.catalog.get(material_id)
        if material is None:
            return None
        profile = await self.onboarding.fresh_profile(user_id)
        saved = effective_preferences(profile, None)
        effective = effective_preferences(profile, onboarding)
        saved_hash, context_hash = preferences_hash(saved), preferences_hash(effective)
        source_version, kind = material.source_version, material.kind
        default = (getattr(material, 'default_offer_text', None) or '').strip() or None
        row = await self.explanations.get(user_id, material_id)
        previous = row.explanation if usable(row, saved_hash, context_hash, source_version) else None
        fallback = previous or default or 'Материал можно изучить для знакомства с темой.'
        history = [{'title': title, 'kind': item_kind} for title, item_kind in await self.catalog.recent_studied(user_id)]
        try:
            source = MaterialInput.model_validate(material)
            reader = ProfileInput(stage_code=effective.stage_code, industry_code=effective.industry_code,
                                  goal_code=effective.goal_code, learning_mode=effective.learning_mode,
                                  profile_config_version=effective.profile_version or '1')
        except ValueError:
            source, reader = None, None
        try:
            lease = await self.leases.acquire(user_id, material_id, saved_hash, datetime.now(UTC),
                                              timedelta(seconds=self.timeout + 10))
        except Exception:
            return {'material_id': material_id, 'kind': kind, 'explanation': fallback, 'offer_text': None}
        if lease is None:
            return {'material_id': material_id, 'kind': kind, 'explanation': fallback, 'offer_text': None}
        text = None
        try:
            if self.client is not None and source is not None:
                method = getattr(self.client, f'generate_{kind}_description')
                async with asyncio.timeout(self.timeout):
                    result = await method(source, reader, studied_materials=history)
                if (result.status == 'succeeded' and result.material_id == material_id
                        and result.source_version == source_version and isinstance(result.text, str)
                        and result.text.strip() and len(result.text) <= 4000
                        and not re.search(r'<[^>]+>', result.text)
                        and len(re.findall(r'[^.!?]+(?:[.!?]+|$)', result.text.strip())) <= 2):
                    text = result.text.strip()
        except Exception:
            text = None
        await self.users.lock(user_id)
        current = await self.catalog.lock_visible(material_id)
        current_profile = await self.onboarding.fresh_profile(user_id)
        valid = (current is not None and current.kind == kind and current.source_version == source_version
                 and preferences_hash(effective_preferences(current_profile, None)) == saved_hash)
        current_default = ((getattr(current, 'default_offer_text', None) or '').strip() or None) if current is not None else None
        current_kind = current.kind if current is not None else kind
        try:
            finished = await self.leases.finish(user_id, material_id, lease, datetime.now(UTC), explanation=text if valid else None,
                                                profile_hash=saved_hash, context_hash=context_hash, source_version=source_version)
        except Exception:
            finished = False
        if current is None:
            return None
        if not valid:
            fallback = current_default or 'Материал можно изучить для знакомства с темой.'
        return {'material_id': material_id, 'kind': current_kind, 'explanation': text if text and valid and finished else fallback,
                'offer_text': None}

