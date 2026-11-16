import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = '0001_public'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.execute('SET LOCAL search_path TO public, pg_catalog')
    op.execute('CREATE SCHEMA IF NOT EXISTS public')
    op.execute('CREATE EXTENSION IF NOT EXISTS citext')
    op.create_table(
        'ArticleSubjects',
        sa.Column('Id', sa.UUID(), nullable=False),
        sa.Column('Title', postgresql.CITEXT(), nullable=False),
        sa.Column('Description', postgresql.CITEXT(), nullable=True),
        sa.Column('IsPublic', sa.Boolean(), nullable=False),
        sa.Column('IsDeleted', sa.Boolean(), nullable=False),
        sa.Column('Url', postgresql.CITEXT(), nullable=True),
        sa.PrimaryKeyConstraint('Id'),
        schema='public',
    )
    op.create_table(
        'ContentSettings',
        sa.Column('Id', sa.UUID(), nullable=False),
        sa.Column('EntityId', sa.UUID(), nullable=False),
        sa.Column('EntityTypeId', sa.UUID(), nullable=False),
        sa.Column('StatusId', sa.UUID(), nullable=False),
        sa.Column('IsDeleted', sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint('Id'),
        schema='public',
    )
    op.create_table(
        'CourseInfoTypes',
        sa.Column('Id', sa.UUID(), nullable=False),
        sa.Column('Title', postgresql.CITEXT(), nullable=False),
        sa.PrimaryKeyConstraint('Id'),
        schema='public',
    )
    op.create_table(
        'CourseTypes',
        sa.Column('Id', sa.UUID(), nullable=False),
        sa.Column('Title', postgresql.CITEXT(), nullable=False),
        sa.Column('IsDeleted', sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint('Id'),
        schema='public',
    )
    op.create_table(
        'DocumentTypes',
        sa.Column('Id', sa.UUID(), nullable=False),
        sa.Column('Title', postgresql.CITEXT(), nullable=False),
        sa.Column('Description', postgresql.CITEXT(), nullable=True),
        sa.Column('IsDeleted', sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint('Id'),
        schema='public',
    )
    op.create_table(
        'Files',
        sa.Column('Id', sa.UUID(), nullable=False),
        sa.Column('Title', postgresql.CITEXT(), nullable=False),
        sa.Column('Url', sa.Text(), nullable=False),
        sa.Column('Size', sa.BigInteger(), nullable=False),
        sa.Column('Extension', sa.Text(), nullable=False),
        sa.Column('IsDeleted', sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint('Id'),
        schema='public',
    )
    op.create_table(
        'Industries',
        sa.Column('Id', sa.UUID(), nullable=False),
        sa.Column('Title', postgresql.CITEXT(), nullable=False),
        sa.PrimaryKeyConstraint('Id'),
        schema='public',
    )
    op.create_table(
        'Lessons',
        sa.Column('Id', sa.UUID(), nullable=False),
        sa.Column('Title', postgresql.CITEXT(), nullable=False),
        sa.Column('Description', postgresql.CITEXT(), nullable=True),
        sa.Column('Duration', sa.String(length=32), nullable=True),
        sa.Column('IsDeleted', sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint('Id'),
        schema='public',
    )
    op.create_table(
        'RatingTags',
        sa.Column('Id', sa.UUID(), nullable=False),
        sa.Column('Title', postgresql.CITEXT(), nullable=False),
        sa.PrimaryKeyConstraint('Id'),
        schema='public',
    )
    op.create_table(
        'RecommendedItems',
        sa.Column('Id', sa.UUID(), nullable=False),
        sa.Column('ItemId', sa.UUID(), nullable=False),
        sa.Column('ItemTypeId', sa.UUID(), nullable=False),
        sa.Column('CourseId', sa.UUID(), nullable=True),
        sa.Column('Order', sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint('Id', 'ItemId', 'ItemTypeId'),
        schema='public',
    )
    op.create_table(
        'Statuses',
        sa.Column('Id', sa.UUID(), nullable=False),
        sa.Column('Title', postgresql.CITEXT(), nullable=False),
        sa.PrimaryKeyConstraint('Id'),
        schema='public',
    )
    op.create_table(
        'Subscription',
        sa.Column('Id', sa.UUID(), nullable=False),
        sa.Column('Title', postgresql.CITEXT(), nullable=False),
        sa.Column('Description', postgresql.CITEXT(), nullable=True),
        sa.Column('IsDeleted', sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint('Id'),
        schema='public',
    )
    op.create_table(
        'Tags',
        sa.Column('Id', sa.UUID(), nullable=False),
        sa.Column('Title', postgresql.CITEXT(), nullable=False),
        sa.PrimaryKeyConstraint('Id'),
        schema='public',
    )
    op.create_table(
        'Topics',
        sa.Column('Id', sa.UUID(), nullable=False),
        sa.Column('Title', postgresql.CITEXT(), nullable=False),
        sa.PrimaryKeyConstraint('Id'),
        schema='public',
    )
    op.create_table(
        'UserRatings',
        sa.Column('Id', sa.UUID(), nullable=False),
        sa.Column('UserId', sa.UUID(), nullable=True),
        sa.Column('EntityId', sa.UUID(), nullable=False),
        sa.Column('EntityTypeId', sa.UUID(), nullable=False),
        sa.Column('Value', sa.SmallInteger(), nullable=False),
        sa.Column('Created', sa.DateTime(timezone=True), nullable=False),
        sa.Column('IsDeleted', sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint('Id'),
        schema='public',
    )
    op.create_table(
        'Articles',
        sa.Column('Id', sa.UUID(), nullable=False),
        sa.Column('Title', postgresql.CITEXT(), nullable=False),
        sa.Column('Description', postgresql.CITEXT(), nullable=True),
        sa.Column('Content', postgresql.CITEXT(), nullable=True),
        sa.Column('Duration', postgresql.CITEXT(), nullable=True),
        sa.Column('Url', postgresql.CITEXT(), nullable=False),
        sa.Column('StatusId', sa.UUID(), nullable=False),
        sa.Column('SubjectId', sa.UUID(), nullable=True),
        sa.Column('IsLesson', sa.Boolean(), nullable=False),
        sa.Column('IsPublic', sa.Boolean(), nullable=False),
        sa.Column('IsClosed', sa.Boolean(), nullable=False),
        sa.Column('IsDeleted', sa.Boolean(), nullable=False),
        sa.Column('Published', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['StatusId'], ['public.Statuses.Id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['SubjectId'], ['public.ArticleSubjects.Id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('Id'),
        schema='public',
    )
    op.create_table(
        'ContentSettingsIndustries',
        sa.Column('ContentSettingsId', sa.UUID(), nullable=False),
        sa.Column('IndustryId', sa.UUID(), nullable=False),
        sa.Column('Order', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['ContentSettingsId'], ['public.ContentSettings.Id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['IndustryId'], ['public.Industries.Id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('ContentSettingsId', 'IndustryId'),
        schema='public',
    )
    op.create_table(
        'ContentSettingsTags',
        sa.Column('ContentSettingsId', sa.UUID(), nullable=False),
        sa.Column('TagId', sa.UUID(), nullable=False),
        sa.Column('Order', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['ContentSettingsId'], ['public.ContentSettings.Id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['TagId'], ['public.Tags.Id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('ContentSettingsId', 'TagId'),
        schema='public',
    )
    op.create_table(
        'ContentSettingsTopics',
        sa.Column('ContentSettingsId', sa.UUID(), nullable=False),
        sa.Column('TopicId', sa.UUID(), nullable=False),
        sa.Column('Order', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['ContentSettingsId'], ['public.ContentSettings.Id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['TopicId'], ['public.Topics.Id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('ContentSettingsId', 'TopicId'),
        schema='public',
    )
    op.create_table(
        'Courses',
        sa.Column('Id', sa.UUID(), nullable=False),
        sa.Column('Title', postgresql.CITEXT(), nullable=False),
        sa.Column('Description', postgresql.CITEXT(), nullable=False),
        sa.Column('Target', postgresql.CITEXT(), nullable=True),
        sa.Column('Duration', sa.String(length=255), nullable=True),
        sa.Column('LessonQuantity', sa.Integer(), nullable=False),
        sa.Column('StatusId', sa.UUID(), nullable=False),
        sa.Column('TypeId', sa.UUID(), nullable=True),
        sa.Column('IsDeleted', sa.Boolean(), nullable=False),
        sa.Column('IsClosed', sa.Boolean(), nullable=False),
        sa.Column('Cost', sa.Integer(), nullable=True),
        sa.Column('Url', postgresql.CITEXT(), nullable=False),
        sa.ForeignKeyConstraint(['StatusId'], ['public.Statuses.Id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['TypeId'], ['public.CourseTypes.Id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('Id'),
        schema='public',
    )
    op.create_table(
        'Documents',
        sa.Column('Id', sa.UUID(), nullable=False),
        sa.Column('Title', postgresql.CITEXT(), nullable=False),
        sa.Column('Description', postgresql.CITEXT(), nullable=True),
        sa.Column('Url', postgresql.CITEXT(), nullable=False),
        sa.Column('TypeId', sa.UUID(), nullable=False),
        sa.Column('FileId', sa.UUID(), nullable=True),
        sa.Column('FileIdNew', sa.UUID(), nullable=True),
        sa.Column('Extension', sa.String(length=7), nullable=True),
        sa.Column('Size', sa.Integer(), nullable=True),
        sa.Column('StatusId', sa.UUID(), nullable=False),
        sa.Column('IsDeleted', sa.Boolean(), nullable=False),
        sa.Column('Published', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['FileId'], ['public.Files.Id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['StatusId'], ['public.Statuses.Id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['TypeId'], ['public.DocumentTypes.Id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('Id'),
        schema='public',
    )
    op.create_table(
        'SubscriptionTariffs',
        sa.Column('Id', sa.UUID(), nullable=False),
        sa.Column('SubscriptionId', sa.UUID(), nullable=False),
        sa.Column('Title', postgresql.CITEXT(), nullable=False),
        sa.Column('Cost', sa.Integer(), nullable=False),
        sa.Column('DiscountCost', sa.Integer(), nullable=True),
        sa.Column('Recurrence', sa.Integer(), nullable=False),
        sa.Column('RecurrenceValue', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['SubscriptionId'], ['public.Subscription.Id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('Id'),
        schema='public',
    )
    op.create_table(
        'UserRatingTagsBindings',
        sa.Column('UserRatingId', sa.UUID(), nullable=False),
        sa.Column('TagId', sa.UUID(), nullable=False),
        sa.Column('Text', sa.String(length=500), nullable=True),
        sa.ForeignKeyConstraint(['TagId'], ['public.RatingTags.Id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['UserRatingId'], ['public.UserRatings.Id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('UserRatingId', 'TagId'),
        schema='public',
    )
    op.create_table(
        'CourseLessonBindings',
        sa.Column('CourseId', sa.UUID(), nullable=False),
        sa.Column('LessonId', sa.UUID(), nullable=False),
        sa.Column('Order', sa.Integer(), nullable=True),
        sa.Column('IsTrial', sa.Boolean(), nullable=False),
        sa.Column('IsDeleted', sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(['CourseId'], ['public.Courses.Id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['LessonId'], ['public.Lessons.Id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('CourseId', 'LessonId'),
        schema='public',
    )
    op.create_table(
        'CourseSubscriptions',
        sa.Column('CourseId', sa.UUID(), nullable=False),
        sa.Column('SubscriptionId', sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(['CourseId'], ['public.Courses.Id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['SubscriptionId'], ['public.Subscription.Id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('CourseId', 'SubscriptionId'),
        schema='public',
    )
    op.create_table(
        'CourseTariffBindings',
        sa.Column('Id', sa.UUID(), nullable=False),
        sa.Column('CourseId', sa.UUID(), nullable=False),
        sa.Column('Title', postgresql.CITEXT(), nullable=False),
        sa.Column('Cost', sa.Integer(), nullable=False),
        sa.Column('Description', postgresql.CITEXT(), nullable=True),
        sa.ForeignKeyConstraint(['CourseId'], ['public.Courses.Id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('Id'),
        schema='public',
    )
    op.create_table(
        'CourseUserBindings',
        sa.Column('Id', sa.UUID(), nullable=False),
        sa.Column('CourseId', sa.UUID(), nullable=False),
        sa.Column('UserId', sa.UUID(), nullable=False),
        sa.Column('IsCompleted', sa.Boolean(), nullable=False),
        sa.Column('Completed', sa.DateTime(timezone=True), nullable=True),
        sa.Column('StudyingStartDate', sa.DateTime(timezone=True), nullable=True),
        sa.Column('LessonsCompleted', sa.Integer(), nullable=False),
        sa.Column('IsPaid', sa.Boolean(), nullable=False),
        sa.Column('SubscriptionId', sa.UUID(), nullable=True),
        sa.Column('IsDeleted', sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(['CourseId'], ['public.Courses.Id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('Id'),
        schema='public',
    )
    op.create_table(
        'DocumentBindings',
        sa.Column('DocumentId', sa.UUID(), nullable=False),
        sa.Column('LinkedDocumentId', sa.UUID(), nullable=False),
        sa.Column('Order', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['DocumentId'], ['public.Documents.Id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['LinkedDocumentId'], ['public.Documents.Id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('DocumentId', 'LinkedDocumentId'),
        schema='public',
    )
    op.create_table(
        'CourseInfoBindings',
        sa.Column('Id', sa.UUID(), nullable=False),
        sa.Column('CourseId', sa.UUID(), nullable=False),
        sa.Column('CourseInfoTypeId', sa.UUID(), nullable=False),
        sa.Column('CourseTariffId', sa.UUID(), nullable=True),
        sa.Column('Title', postgresql.CITEXT(), nullable=False),
        sa.Column('Description', postgresql.CITEXT(), nullable=True),
        sa.Column('Order', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['CourseId'], ['public.Courses.Id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['CourseInfoTypeId'], ['public.CourseInfoTypes.Id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['CourseTariffId'], ['public.CourseTariffBindings.Id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('Id'),
        schema='public',
    )
    op.create_table(
        'CourseUserLessonBindings',
        sa.Column('Id', sa.UUID(), nullable=False),
        sa.Column('CourseUserId', sa.UUID(), nullable=False),
        sa.Column('LessonId', sa.UUID(), nullable=False),
        sa.Column('StudyingStartDate', sa.DateTime(timezone=True), nullable=True),
        sa.Column('Completed', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['CourseUserId'], ['public.CourseUserBindings.Id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['LessonId'], ['public.Lessons.Id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('Id'),
        schema='public',
    )


def downgrade():
    op.drop_table('CourseUserLessonBindings', schema='public')
    op.drop_table('CourseInfoBindings', schema='public')
    op.drop_table('DocumentBindings', schema='public')
    op.drop_table('CourseUserBindings', schema='public')
    op.drop_table('CourseTariffBindings', schema='public')
    op.drop_table('CourseSubscriptions', schema='public')
    op.drop_table('CourseLessonBindings', schema='public')
    op.drop_table('UserRatingTagsBindings', schema='public')
    op.drop_table('SubscriptionTariffs', schema='public')
    op.drop_table('Documents', schema='public')
    op.drop_table('Courses', schema='public')
    op.drop_table('ContentSettingsTopics', schema='public')
    op.drop_table('ContentSettingsTags', schema='public')
    op.drop_table('ContentSettingsIndustries', schema='public')
    op.drop_table('Articles', schema='public')
    op.drop_table('UserRatings', schema='public')
    op.drop_table('Topics', schema='public')
    op.drop_table('Tags', schema='public')
    op.drop_table('Subscription', schema='public')
    op.drop_table('Statuses', schema='public')
    op.drop_table('RecommendedItems', schema='public')
    op.drop_table('RatingTags', schema='public')
    op.drop_table('Lessons', schema='public')
    op.drop_table('Industries', schema='public')
    op.drop_table('Files', schema='public')
    op.drop_table('DocumentTypes', schema='public')
    op.drop_table('CourseTypes', schema='public')
    op.drop_table('CourseInfoTypes', schema='public')
    op.drop_table('ContentSettings', schema='public')
    op.drop_table('ArticleSubjects', schema='public')
