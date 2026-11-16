from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, Float, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as UUIDType

from src.db.models import Base
from src.services.commerce import add_months

SOURCE_TABLES = ('Statuses', 'Topics', 'Tags', 'Industries', 'DocumentTypes', 'Files',
                 'Courses', 'Articles', 'Documents', 'ContentSettings', 'ContentSettingsTopics',
                 'ContentSettingsTags', 'ContentSettingsIndustries', 'CourseTariffBindings',
                 'Subscription', 'SubscriptionTariffs', 'CourseSubscriptions')
MVP_TABLES = ('users', 'onboarding_responses', 'user_profiles', 'materials', 'favorite_folders',
              'favorites', 'recommendation_lists', 'recommendation_items', 'purchases',
              'subscription_access', 'discount_grants', 'email_preferences', 'user_material_studies')


def prepare_fixture(fixture: dict, config, now: datetime, password_hash: str) -> dict:
    if set(fixture) != {'checked_at', 'source', 'mvp'} or not password_hash or now.utcoffset() is None:
        raise ValueError('Invalid demo fixture')
    checked = datetime.fromisoformat(fixture['checked_at'].replace('Z', '+00:00'))
    if checked.utcoffset() is None:
        raise ValueError('Invalid fixture time')
    if set(fixture['source']) not in (set(SOURCE_TABLES), set(SOURCE_TABLES) | {'CourseTypes'}) or set(fixture['mvp']) != set(MVP_TABLES):
        raise ValueError('Unexpected demo tables')
    rows = {}
    for schema, section in (('public', fixture['source']), ('mvp', fixture['mvp'])):
        for name, values in section.items():
            table = Base.metadata.tables[f'{schema}.{name}']
            if not isinstance(values, list):
                raise ValueError('Invalid demo rows')
            rows[table.fullname] = []
            for source in values:
                if not isinstance(source, dict) or set(source) - set(table.c.keys()):
                    raise ValueError('Invalid demo columns')
                row = {}
                for key, value in source.items():
                    column = table.c[key]
                    if value is None:
                        if not column.nullable:
                            raise ValueError('Unexpected null')
                    elif isinstance(column.type, UUIDType):
                        value = UUID(value)
                    elif isinstance(column.type, DateTime):
                        value = datetime.fromisoformat(value.replace('Z', '+00:00'))
                        if value.utcoffset() is None:
                            raise ValueError('Date must include timezone')
                        if schema == 'mvp':
                            value += now - checked
                    elif isinstance(column.type, Boolean):
                        if type(value) is not bool:
                            raise ValueError('Invalid boolean')
                    elif isinstance(column.type, Integer):
                        if type(value) is not int:
                            raise ValueError('Invalid integer')
                    elif isinstance(column.type, Float):
                        if type(value) not in (int, float):
                            raise ValueError('Invalid number')
                    elif isinstance(column.type, Text):
                        if not isinstance(value, str):
                            raise ValueError('Invalid text')
                    elif isinstance(column.type, JSONB):
                        if not isinstance(value, (dict, list)):
                            raise ValueError('Invalid JSON')
                    row[key] = value
                if name == 'users' and schema == 'mvp':
                    row['password_hash'] = password_hash
                for column in table.c:
                    if column.name not in row and not column.nullable and column.default is None and column.server_default is None:
                        raise ValueError('Missing required demo column')
                rows[table.fullname].append(row)
    for name, values in rows.items():
        table = Base.metadata.tables[name]
        keys = [tuple(row.get(col.name) for col in table.primary_key) for row in values]
        if len(keys) != len(set(keys)):
            raise ValueError('Duplicate demo key')
        for row in values:
            for fk in table.foreign_keys:
                value = row.get(fk.parent.name)
                if value is not None and not any(other.get(fk.column.name) == value
                                                  for other in rows.get(fk.column.table.fullname, [])):
                    raise ValueError('Invalid demo reference')
    materials = rows['mvp.materials']
    for material in materials:
        table = {'course': 'Courses', 'article': 'Articles', 'document': 'Documents'}.get(material['kind'])
        if (material['source_table'] != table or not any(r['Id'] == material['source_id'] for r in rows.get(f'public.{table}', []))
                or material['verified_course_id'] != (material['source_id'] if table == 'Courses' else None)):
            raise ValueError('Invalid material source')
    if (any(row['profile_config_version'] != config['profile_config_version'] for row in rows['mvp.user_profiles'])
            or any(row['questionnaire_version'] != config['questionnaire']['questionnaire_version'] for row in rows['mvp.onboarding_responses'])
            or not set(config['catalog']['popularity']) <= {str(row['id']) for row in materials}
            or not set(config['access']['free_material_ids']) <= {str(row['id']) for row in materials}):
        raise ValueError('Incompatible demo configuration')
    # Preserve the fixture's calendar-month subscription periods when the current month differs.
    for original, access in zip(fixture['mvp']['subscription_access'], rows['mvp.subscription_access'], strict=True):
        start = datetime.fromisoformat(original['valid_from'].replace('Z', '+00:00'))
        end = datetime.fromisoformat(original['valid_until'].replace('Z', '+00:00'))
        months = (end.year - start.year) * 12 + end.month - start.month
        if months > 0 and add_months(start, months) == end:
            access['valid_until'] = add_months(access['valid_from'], months)
    return rows


class DemoService:
    def __init__(self, session, crud):
        self.session = session
        self.crud = crud

    async def load(self, fixture, config, password_hash):
        rows = prepare_fixture(fixture, config, datetime.now(UTC), password_hash)
        try:
            state = await self.crud.state(rows)
            if state == 'incompatible':
                raise ValueError('Database is not empty and does not contain the demo dataset')
            if state == 'empty':
                await self.crud.insert(rows)
            await self.session.commit()
            return state
        except Exception:
            await self.session.rollback()
            raise
