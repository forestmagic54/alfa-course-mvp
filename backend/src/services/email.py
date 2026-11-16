import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.db.crud.email import EmailCRUD
from src.db.crud.users import UsersCRUD
from src.db.models.email import EmailMessages, EmailPreferences


class EmailError(ValueError):
    pass


class EmailService:
    def __init__(self, session: AsyncSession, users: UsersCRUD, email: EmailCRUD, version: str):
        self.session, self.users, self.email, self.version = session, users, email, version

    async def get(self, user_id: UUID):
        row = await self.email.preferences(user_id)
        return row or {'marketing_consent': False, 'consent_version': None,
                       'consent_updated_at': None, 'unsubscribed_at': None}

    async def update(self, user_id: UUID, consent: bool, version: str | None):
        if consent and version != self.version:
            raise EmailError('Unsupported consent version')
        try:
            if await self.users.lock(user_id) is None:
                raise EmailError('Account not found')
            row = await self.email.preferences(user_id)
            if row is None and not consent:
                await self.session.commit()
                return {'marketing_consent': False, 'consent_version': None,
                        'consent_updated_at': None, 'unsubscribed_at': None}
            now = datetime.now(UTC)
            if row is None:
                row = EmailPreferences(user_id=user_id, marketing_consent=True,
                                       consent_version=version, consent_updated_at=now)
                await self.email.add(row)
            elif row.marketing_consent != consent or (consent and row.consent_version != version):
                row.marketing_consent = consent
                row.consent_updated_at = now
                if consent:
                    row.consent_version = version
                    row.unsubscribed_at = None
                else:
                    row.unsubscribed_at = now
            await self.session.commit()
            return row
        except BaseException:
            await self.session.rollback()
            raise

    async def prepare(self, user_id: UUID, message_id: UUID, directory: Path) -> Path:
        path = directory / f'{message_id}.txt'
        created = False
        commit_started = False
        try:
            if await self.users.lock(user_id) is None:
                raise EmailError('Account not found')
            preferences = await self.email.preferences(user_id)
            if not preferences or not preferences.marketing_consent or preferences.consent_version != self.version:
                raise EmailError('Current marketing consent required')
            message = await self.email.message(message_id)
            if message:
                if (message.user_id != user_id or message.kind != 'placeholder'
                        or message.list_id is not None or message.status != 'prepared'):
                    raise EmailError('Preparation ID already in use')
                if not path.is_file() or path.is_symlink():
                    raise EmailError('Prepared file is missing or invalid')
                await self.session.rollback()
                return path
            await self.email.add(EmailMessages(id=message_id, user_id=user_id, kind='placeholder',
                                               status='prepared', list_id=None))
            directory.mkdir(mode=0o700, parents=True, exist_ok=True)
            fd, temp_name = tempfile.mkstemp(dir=directory, prefix='.email-')
            try:
                with os.fdopen(fd, 'w', encoding='utf-8') as file:
                    file.write('Тема: Тестовое письмо\n\nЗаглушка содержимого письма.\n\n'
                               'Чтобы изменить согласие на рассылку, войдите в аккаунт '
                               'и откройте настройки рассылки.\n')
                os.link(temp_name, path)
                created = True
            finally:
                os.unlink(temp_name)
            commit_started = True
            await self.session.commit()
            return path
        except BaseException:
            await self.session.rollback()
            if created:
                # shortcut: an orphan may remain after a crash; add recovery before real delivery.
                if not commit_started:
                    path.unlink(missing_ok=True)
                else:
                    try:
                        committed = await self.email.message(message_id)
                    except Exception:
                        committed = True
                    if not committed:
                        path.unlink(missing_ok=True)
            raise
