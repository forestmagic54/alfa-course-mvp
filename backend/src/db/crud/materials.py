from uuid import UUID

from sqlalchemy import and_, case, exists, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models.material_studies import UserMaterialStudies
from src.db.models.materials import Materials
from src.db.models.public import (
    Articles,
    ArticleSubjects,
    ContentSettings,
    ContentSettingsIndustries,
    ContentSettingsTags,
    ContentSettingsTopics,
    Courses,
    CourseSubscriptions,
    Documents,
    Industries,
    Subscription,
    SubscriptionTariffs,
    Tags,
    Topics,
)


class MaterialsCRUD:
    def __init__(self, session: AsyncSession, config):
        self.session = session
        self.config = config
        self.statuses = [UUID(value) for value in config['catalog']['published_status_ids']]
        self.types = {kind: UUID(value) for kind, value in config['catalog']['entity_type_ids'].items()}

    def visible(self):
        statuses = self.statuses
        course = exists(select(Courses.Id).where(
            Materials.kind == 'course', Materials.source_table == 'Courses',
            Courses.Id == Materials.source_id, Materials.verified_course_id == Courses.Id,
            Courses.StatusId.in_(statuses), Courses.IsDeleted.is_(False), Courses.IsClosed.is_(False)))
        subject_visible = or_(Articles.SubjectId.is_(None), exists(select(ArticleSubjects.Id).where(
            ArticleSubjects.Id == Articles.SubjectId, ArticleSubjects.IsPublic.is_(True),
            ArticleSubjects.IsDeleted.is_(False))))
        article = exists(select(Articles.Id).where(
            Materials.kind == 'article', Materials.source_table == 'Articles',
            Materials.verified_course_id.is_(None), Articles.Id == Materials.source_id,
            Articles.StatusId.in_(statuses), Articles.IsDeleted.is_(False), Articles.IsClosed.is_(False),
            Articles.IsPublic.is_(True), Articles.IsLesson.is_(False), subject_visible))
        document = exists(select(Documents.Id).where(
            Materials.kind == 'document', Materials.source_table == 'Documents',
            Materials.verified_course_id.is_(None), Documents.Id == Materials.source_id,
            Documents.StatusId.in_(statuses), Documents.IsDeleted.is_(False)))
        return or_(course, article, document)

    def setting_match(self):
        return and_(ContentSettings.EntityId == Materials.source_id,
                    ContentSettings.EntityTypeId == case(self.types, value=Materials.kind),
                    ContentSettings.StatusId.in_(self.statuses), ContentSettings.IsDeleted.is_(False))

    def classification_filter(self, binding, column, ids):
        return exists(select(ContentSettings.Id).join(binding, binding.ContentSettingsId == ContentSettings.Id)
                      .where(self.setting_match(), column.in_(ids)))

    def subscriptions_filter(self):
        available = [and_(SubscriptionTariffs.Id == UUID(tariff_id),
                          Subscription.Id == UUID(data['subscription_id']))
                     for tariff_id, data in self.config['subscriptions']['tariffs'].items()
                     if data['price']['amount_minor'] > 0]
        return exists(select(CourseSubscriptions.CourseId)
                      .join(Subscription, Subscription.Id == CourseSubscriptions.SubscriptionId)
                      .join(SubscriptionTariffs, SubscriptionTariffs.SubscriptionId == Subscription.Id)
                      .where(Materials.kind == 'course', CourseSubscriptions.CourseId == Materials.source_id,
                             Subscription.IsDeleted.is_(False), or_(False, *available)))

    def price(self):
        prices = {UUID(key): value['amount_minor'] for key, value in self.config['access']['course_prices'].items()
                  if value['amount_minor'] > 0}
        return case((Materials.access_type == 'free', 0),
                    (Materials.kind == 'course', case(prices, value=Materials.source_id)), else_=None)

    async def search(self, filters):
        conditions = [self.visible()]
        if filters.kind:
            conditions.append(Materials.kind == filters.kind)
        if filters.topic_id:
            conditions.append(self.classification_filter(ContentSettingsTopics, ContentSettingsTopics.TopicId, [filters.topic_id]))
        if filters.industry_id:
            conditions.append(self.classification_filter(ContentSettingsIndustries, ContentSettingsIndustries.IndustryId, [filters.industry_id]))
        if filters.skill_id:
            tags = [UUID(tag) for skill in self.config['skills'] if UUID(skill['id']) == filters.skill_id for tag in skill['tag_ids']]
            conditions.append(self.classification_filter(ContentSettingsTags, ContentSettingsTags.TagId, tags))
        if filters.access_type == 'free':
            conditions.append(Materials.access_type == 'free')
        elif filters.access_type == 'paid':
            conditions.append(and_(Materials.kind == 'course', Materials.source_id.in_(
                [UUID(key) for key, price in self.config['access']['course_prices'].items() if price['amount_minor'] > 0])))
        elif filters.access_type == 'subscription':
            conditions.append(self.subscriptions_filter())
        if filters.min_price_minor is not None:
            conditions.append(self.price() >= filters.min_price_minor)
        if filters.max_price_minor is not None:
            conditions.append(self.price() <= filters.max_price_minor)
        if filters.max_duration_minutes is not None:
            conditions.append(Materials.duration_minutes <= filters.max_duration_minutes)
        order = [func.lower(Materials.title), Materials.id]
        if filters.q:
            query = filters.q.lower()
            # escape LIKE metacharacters so they retain their literal meaning.
            escaped = query.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
            title = func.lower(Materials.title)
            conditions.append(title.like('%' + escaped + '%', escape='\\'))
            order.insert(0, case((title == query, 0), (title.like(escaped + '%', escape='\\'), 1), else_=2))
        elif self.config['catalog']['popularity']:
            popularity = {UUID(key): value for key, value in self.config['catalog']['popularity'].items()}
            order.insert(0, case(popularity, value=Materials.id, else_=None).desc().nulls_last())
        total = await self.session.scalar(select(func.count()).select_from(Materials).where(*conditions))
        items = (await self.session.scalars(select(Materials).where(*conditions).order_by(*order)
                                            .offset(filters.offset).limit(filters.limit))).all()
        return items, total

    async def recommendation_candidates(self):
        query = select(Materials).where(self.visible(), Materials.is_recommendable.is_(True))
        return list((await self.session.scalars(query)).all())

    async def get_any(self, material_id: UUID):
        return await self.session.get(Materials, material_id)

    async def get(self, material_id):
        return await self.session.scalar(select(Materials).where(Materials.id == material_id, self.visible()))

    async def lock_visible(self, material_id):
        query = (select(Materials).where(Materials.id == material_id, self.visible())
                 .with_for_update().execution_options(populate_existing=True))
        return await self.session.scalar(query)

    async def recent_studied(self, user_id: UUID) -> list[tuple[str, str]]:
        query = (select(Materials.title, Materials.kind)
                 .join(UserMaterialStudies, UserMaterialStudies.material_id == Materials.id)
                 .where(UserMaterialStudies.user_id == user_id, self.visible())
                 .order_by(UserMaterialStudies.marked_at.desc(), Materials.id.desc()).limit(10))
        return list((await self.session.execute(query)).tuples().all())

    async def get_course(self, course_id):
        return await self.session.scalar(select(Materials).where(
            Materials.verified_course_id == course_id, self.visible()))

    async def classification(self, material_ids):
        result = {material_id: {'topics': {}, 'industries': {}, 'tags': {}} for material_id in material_ids}
        if not result:
            return result
        for key, binding, entity, fk in (
            ('topics', ContentSettingsTopics, Topics, ContentSettingsTopics.TopicId),
            ('industries', ContentSettingsIndustries, Industries, ContentSettingsIndustries.IndustryId),
            ('tags', ContentSettingsTags, Tags, ContentSettingsTags.TagId),
        ):
            query = (select(Materials.id, entity.Id, entity.Title).join(ContentSettings, self.setting_match())
                     .join(binding, binding.ContentSettingsId == ContentSettings.Id).join(entity, entity.Id == fk)
                     .where(Materials.id.in_(material_ids), self.visible()))
            for material_id, entity_id, title in (await self.session.execute(query)).all():
                result[material_id][key][entity_id] = title
        return result

    async def related(self, material_id, topic_ids):
        if not topic_ids:
            return []
        query = (select(Materials, func.count(func.distinct(ContentSettingsTopics.TopicId)).label('common'))
                 .join(ContentSettings, self.setting_match())
                 .join(ContentSettingsTopics, ContentSettingsTopics.ContentSettingsId == ContentSettings.Id)
                 .where(self.visible(), Materials.id != material_id, ContentSettingsTopics.TopicId.in_(topic_ids))
                 .group_by(Materials.id).order_by(text('common DESC'), func.lower(Materials.title), Materials.id).limit(3))
        return list((await self.session.execute(query)).scalars().all())

    async def visible_ids(self):
        return list((await self.session.scalars(select(Materials.id).where(self.visible()))).all())

    async def sources(self):
        courses = list((await self.session.scalars(select(Courses))).all())
        articles = (await self.session.execute(select(Articles, ArticleSubjects).outerjoin(
            ArticleSubjects, ArticleSubjects.Id == Articles.SubjectId))).all()
        documents = list((await self.session.scalars(select(Documents))).all())
        return courses, articles, documents

    async def lock_and_projections(self):
        await self.session.execute(text("SELECT pg_advisory_xact_lock(hashtext('mvp.materials.sync'))"))
        values = (await self.session.scalars(select(Materials))).all()
        return {(item.source_table, item.source_id): item for item in values}

    def add(self, material):
        self.session.add(material)

    async def visible_subset(self, material_ids):
        if not material_ids:
            return set()
        query = select(Materials.id).where(Materials.id.in_(material_ids), self.visible())
        return set((await self.session.scalars(query)).all())
