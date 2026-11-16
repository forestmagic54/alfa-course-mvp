import csv
import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from src.config.default_offers import load_default_offers
from src.db.crud.commerce import CommerceCRUD
from src.db.crud.favorites import FavoritesCRUD
from src.db.crud.materials import MaterialsCRUD
from src.db.models.materials import Materials
from src.db.models.public import Subscription, SubscriptionTariffs
from src.services.access import card_access, public_url
from src.services.types import (
    ClassificationData,
    MaterialCardData,
    MaterialDetailData,
    MaterialFiltersData,
    MaterialPageData,
    NamedItemData,
)


def source_visible(kind: str, source: Any, subject: Any, statuses: list[UUID]) -> bool:
    if source.StatusId not in statuses or source.IsDeleted:
        return False
    if kind == 'course':
        return not source.IsClosed
    if kind == 'article':
        return (not source.IsClosed and source.IsPublic and not source.IsLesson
                and (source.SubjectId is None or (subject is not None and subject.IsPublic and not subject.IsDeleted)))
    return True


def update_projection(material: Materials, kind: str, source: Any, visible: bool, config: Any, now: datetime) -> None:
    free = str(material.id) in config['access']['free_material_ids']
    price = config['access']['course_prices'].get(str(source.Id)) if kind == 'course' else None
    access_type = 'free' if free else 'paid' if price and price['amount_minor'] > 0 else 'unknown'
    # shortcut: source durations and real document file priority need verification before use.
    url = (config['catalog'].get('demo_document_urls', {}).get(str(material.id))
           if kind == 'document' else source.Url)
    facts = {'title': source.Title, 'public_description': source.Description if visible else None,
             'url': public_url(url) if visible else None,
             'duration_minutes': config['catalog'].get('duration_minutes', {}).get(str(material.id)),
             'access_type': access_type}
    for field, value in facts.items():
        setattr(material, field, value)
    material.is_recommendable = bool(visible and material.learning_role and material.difficulty_level
                                      and material.annotation_source and material.annotation_version)
    version = {**facts, 'visible': visible, 'config_version': config['version'],
               'annotation_source': material.annotation_source, 'annotation_version': material.annotation_version,
               'metadata_schema_version': material.metadata_schema_version, 'metadata': material.metadata_,
               'learning_role': material.learning_role, 'difficulty_level': material.difficulty_level}
    material.source_version = hashlib.sha256(json.dumps(version, sort_keys=True, ensure_ascii=False,
                                                        separators=(',', ':')).encode()).hexdigest()
    material.synced_at = now


def named_items(items: dict[UUID, str]) -> list[NamedItemData]:
    return [{'id': item_id, 'title': title} for item_id, title in
            sorted(items.items(), key=lambda item: (item[1].lower(), str(item[0])))]


def classifications(data: ClassificationData, config: Any) -> MaterialFiltersData:
    skills = {UUID(skill['id']): skill['title'] for skill in config['skills']
              if any(UUID(tag) in data['tags'] for tag in skill['tag_ids'])}
    return {'topics': named_items(data['topics']), 'industries': named_items(data['industries']),
            'skills': named_items(skills)}


class MaterialService:
    def __init__(self, materials_factory: Callable[[Any], MaterialsCRUD], commerce: CommerceCRUD, favorites: FavoritesCRUD,
                 explanations=None):
        self.materials_factory = materials_factory
        self.commerce = commerce
        self.favorites = favorites
        self.explanations = explanations

    async def build_cards(self, materials: list[Materials], user_id: UUID | None, config: Any, *,
                          now: datetime | None = None) -> list[MaterialCardData]:
        if not materials:
            return []
        now = now or datetime.now(UTC)
        ids = [material.id for material in materials]
        course_ids = [material.source_id for material in materials if material.kind == 'course']
        catalog = self.materials_factory(config)
        commerce = self.commerce
        classification = await catalog.classification(ids)
        rows = await commerce.tariffs(course_ids, [UUID(value) for value in config['subscriptions']['tariffs']])
        links: dict[UUID, set[UUID]] = {}
        for course_id, subscription_id in await commerce.subscription_links(course_ids):
            links.setdefault(course_id, set()).add(subscription_id)
        tariffs: dict[UUID, list[tuple[Subscription, SubscriptionTariffs]]] = {}
        for course_id, subscription, tariff in rows:
            data = config['subscriptions']['tariffs'][str(tariff.Id)]
            if str(subscription.Id) == data['subscription_id'] and data['price']['amount_minor'] > 0:
                tariffs.setdefault(course_id, []).append((subscription, tariff))
        purchases, subscriptions, discounts, favorites = [], [], [], set()
        if user_id is not None:
            purchases, subscriptions, discounts = await commerce.user_state(user_id)
            favorites = await self.favorites.material_ids(user_id, ids)
        cards: list[MaterialCardData] = []
        for material in materials:
            access, offers, action = card_access(material, tariffs.get(material.source_id, []), links.get(material.source_id, set()), purchases,
                                                  subscriptions, discounts, config, now)
            groups = classifications(classification[material.id], config)
            card: MaterialCardData = {'id': material.id, 'kind': material.kind, 'title': material.title,
                    'duration_minutes': material.duration_minutes, 'topics': groups['topics'],
                    'industries': groups['industries'], 'skills': groups['skills'],
                    'access_type': material.access_type, 'access': access, 'offers': offers,
                    'primary_action': action, 'is_favorite': material.id in favorites}
            if material.kind == 'course':
                card['course_id'] = material.verified_course_id
            cards.append(card)
        return cards

    async def get_filters(self, config: Any) -> MaterialFiltersData:
        crud = self.materials_factory(config)
        rows = await crud.classification(await crud.visible_ids())
        merged: ClassificationData = {'topics': {}, 'industries': {}, 'tags': set()}
        for value in rows.values():
            merged['topics'].update(value['topics'])
            merged['industries'].update(value['industries'])
            merged['tags'].update(value['tags'])
        return classifications(merged, config)

    async def search(self, filters, user_id: UUID | None, config: Any) -> MaterialPageData:
        materials, total = await self.materials_factory(config).search(filters)
        return {'items': await self.build_cards(materials, user_id, config), 'total': total}

    async def detail(self, material_id: UUID, user_id: UUID | None, config: Any) -> MaterialDetailData | None:
        catalog = self.materials_factory(config)
        material = await catalog.get(material_id)
        if material is None:
            return None
        classification = await catalog.classification([material.id])
        related = await catalog.related(material.id, list(classification[material.id]['topics']))
        cards = await self.build_cards([material, *related], user_id, config)
        explanation = (await self.explanations.read(material, user_id) if self.explanations is not None
                       else getattr(material, 'default_offer_text', None))
        return cast(MaterialDetailData, {**cards[0], 'description': material.public_description,
                                        'explanation': explanation, 'related_materials': cards[1:]})


class MaterialSyncService:
    def __init__(self, session: AsyncSession, catalog: MaterialsCRUD, config: Any):
        self.session = session
        self.catalog = catalog
        self.config = config

    async def synchronize(self) -> None:
        crud, config = self.catalog, self.config
        default_offers = load_default_offers()
        async with self.session.begin():
            existing = await crud.lock_and_projections()
            courses, articles, documents = await crud.sources()
            sources = ([('Courses', 'course', item, None) for item in courses]
                       + [('Articles', 'article', item, subject) for item, subject in articles]
                       + [('Documents', 'document', item, None) for item in documents])
            seen = set()
            now = datetime.now(UTC)
            for table, kind, source, subject in sources:
                key = (table, source.Id)
                seen.add(key)
                material = existing.get(key)
                if material is None:
                    material = Materials(id=uuid4(), source_table=table, source_id=source.Id, kind=kind,
                                         verified_course_id=source.Id if kind == 'course' else None)
                    crud.add(material)
                elif material.kind != kind or material.verified_course_id != (source.Id if kind == 'course' else None):
                    raise ValueError(f'Invalid material source mapping: {table} {source.Id}')
                if kind == 'course' and not (material.default_offer_text or '').strip():
                    material.default_offer_text = default_offers.get(source.Id)
                visible = source_visible(kind, source, subject, crud.statuses)
                update_projection(material, kind, source, visible, config, now)
            for key, material in existing.items():
                if key not in seen:
                    material.is_recommendable = False


class MaterialAnnotationService:
    def __init__(self, session: AsyncSession, catalog: MaterialsCRUD):
        self.session = session
        self.catalog = catalog

    async def import_csv(self, source: Any) -> int:
        reader = csv.DictReader(source)
        fields = ('source_table', 'source_id', 'learning_role', 'difficulty_level',
                  'annotation_source', 'annotation_version')
        if reader.fieldnames is None or len(reader.fieldnames) != len(fields) or set(reader.fieldnames) != set(fields):
            raise ValueError('Invalid annotation columns')
        rows = {}
        for row in reader:
            if (None in row or any(not isinstance(row[field], str) or not row[field].strip() for field in fields)
                    or row['source_table'] not in ('Articles', 'Courses', 'Documents')
                    or row['learning_role'] not in ('intro', 'practice', 'advanced')
                    or row['difficulty_level'] not in ('beginner', 'intermediate', 'advanced')
                    or row['annotation_source'] not in ('import', 'manual', 'model')):
                raise ValueError('Invalid annotation row')
            key = (row['source_table'], UUID(row['source_id']))
            if key in rows:
                raise ValueError(f'Duplicate annotation: {key[0]} {key[1]}')
            rows[key] = row
        if not rows:
            raise ValueError('Empty annotations')
        async with self.session.begin():
            existing = await self.catalog.lock_and_projections()
            missing = sorted(set(rows) - set(existing))
            if missing:
                keys = ', '.join(f'{table} {source_id}' for table, source_id in missing)
                raise ValueError(f'Matched {len(rows) - len(missing)}/{len(rows)}; missing: {keys}')
            for key, row in rows.items():
                for field in fields[2:]:
                    setattr(existing[key], field, row[field])
        return len(rows)

