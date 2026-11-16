import asyncio
from types import SimpleNamespace
from uuid import UUID

import pytest
from pydantic import ValidationError

from src.api.email_preferences.schemas import EmailPreferencesInput
from src.services.email import EmailError, EmailService


def run(coro):
    return asyncio.run(coro)


class Session:
    def __init__(self):
        self.events = []

    async def commit(self):
        self.events.append('commit')

    async def rollback(self):
        self.events.append('rollback')


class Users:
    def __init__(self, session):
        self.session = session

    async def lock(self, user_id):
        self.session.events.append('lock')
        return user_id


class Email:
    def __init__(self):
        self.rows = {}
        self.messages = {}

    async def preferences(self, user_id):
        return self.rows.get(user_id)

    async def message(self, message_id):
        return self.messages.get(message_id)

    async def add(self, row):
        if hasattr(row, 'marketing_consent'):
            self.rows[row.user_id] = row
        else:
            self.messages[row.id] = row


def setup():
    session, email = Session(), Email()
    return EmailService(session, Users(session), email, 'demo-1'), session, email


def test_consent_transitions_and_validation():
    user = UUID(int=1)
    service, session, email = setup()
    assert run(service.get(user))['marketing_consent'] is False
    run(service.update(user, False, None))
    assert not email.rows
    with pytest.raises(EmailError):
        run(service.update(user, True, 'old'))
    row = run(service.update(user, True, 'demo-1'))
    initial = row.consent_updated_at
    run(service.update(user, True, 'demo-1'))
    assert row.consent_updated_at == initial
    run(service.update(user, False, None))
    assert row.unsubscribed_at == row.consent_updated_at and row.consent_version == 'demo-1'
    revoked = row.unsubscribed_at
    run(service.update(user, False, None))
    assert row.unsubscribed_at == revoked
    run(service.update(user, True, 'demo-1'))
    assert row.unsubscribed_at is None and row.marketing_consent
    assert session.events[0:2] == ['lock', 'commit']
    for data in ({'marketing_consent': True}, {'marketing_consent': False, 'consent_version': None},
                 {'marketing_consent': False, 'user_id': str(user)}):
        with pytest.raises(ValidationError):
            EmailPreferencesInput(**data)


def test_preparation_requires_consent_and_rejects_foreign_id(tmp_path):
    user, other, message = (UUID(int=i) for i in range(1, 4))
    service, _, email = setup()
    with pytest.raises(EmailError):
        run(service.prepare(user, message, tmp_path))
    run(service.update(user, True, 'demo-1'))
    path = run(service.prepare(user, message, tmp_path))
    assert path.is_file() and 'Заглушка' in path.read_text()
    assert len(email.messages) == 1
    assert run(service.prepare(user, message, tmp_path)) == path
    email.rows[other] = SimpleNamespace(marketing_consent=True, consent_version='demo-1')
    with pytest.raises(EmailError):
        run(service.prepare(other, message, tmp_path))
    run(service.update(user, False, None))
    with pytest.raises(EmailError):
        run(service.prepare(user, message, tmp_path))
    assert path.is_file()


def test_preparation_rejects_orphan_without_overwriting(tmp_path):
    user, message = UUID(int=1), UUID(int=2)
    service, _, _ = setup()
    run(service.update(user, True, 'demo-1'))
    path = tmp_path / f'{message}.txt'
    path.write_text('existing')
    with pytest.raises(FileExistsError):
        run(service.prepare(user, message, tmp_path))
    assert path.read_text() == 'existing'
    assert list(tmp_path.iterdir()) == [path]


def test_commit_failure_checks_database_before_removing_file(tmp_path):
    user, message = UUID(int=1), UUID(int=2)
    service, session, email = setup()
    run(service.update(user, True, 'demo-1'))

    async def failed_commit():
        raise RuntimeError('commit failed')

    async def rolled_back():
        email.messages.clear()

    session.commit = failed_commit
    session.rollback = rolled_back
    with pytest.raises(RuntimeError, match='commit failed'):
        run(service.prepare(user, message, tmp_path))
    assert not list(tmp_path.iterdir())

    async def uncertain():
        raise RuntimeError('database unavailable')

    async def rollback_uncertain():
        email.message = uncertain_message

    async def uncertain_message(message_id):
        return await uncertain()

    session.rollback = rollback_uncertain
    with pytest.raises(RuntimeError, match='commit failed'):
        run(service.prepare(user, message, tmp_path))
    assert (tmp_path / f'{message}.txt').is_file()
