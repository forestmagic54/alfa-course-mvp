from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import CITEXT
from sqlalchemy.dialects.postgresql import UUID as UUIDType
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class Courses(Base):
    __tablename__ = 'Courses'
    __table_args__ = (
        {'schema': 'public'},
    )
    Id: Mapped[UUID] = mapped_column('Id', UUIDType, primary_key=True, nullable=False)
    Title: Mapped[str] = mapped_column('Title', CITEXT, nullable=False)
    Description: Mapped[str] = mapped_column('Description', CITEXT, nullable=False)
    Target: Mapped[str | None] = mapped_column('Target', CITEXT, nullable=True)
    Duration: Mapped[str | None] = mapped_column('Duration', String(255), nullable=True)
    LessonQuantity: Mapped[int] = mapped_column('LessonQuantity', Integer, nullable=False)
    StatusId: Mapped[UUID] = mapped_column('StatusId', UUIDType, ForeignKey('public.Statuses.Id', ondelete="RESTRICT"), nullable=False)
    TypeId: Mapped[UUID | None] = mapped_column('TypeId', UUIDType, ForeignKey('public.CourseTypes.Id', ondelete="RESTRICT"), nullable=True)
    IsDeleted: Mapped[bool] = mapped_column('IsDeleted', Boolean, nullable=False)
    IsClosed: Mapped[bool] = mapped_column('IsClosed', Boolean, nullable=False)
    Cost: Mapped[int | None] = mapped_column('Cost', Integer, nullable=True)
    Url: Mapped[str] = mapped_column('Url', CITEXT, nullable=False)


class Statuses(Base):
    __tablename__ = 'Statuses'
    __table_args__ = (
        {'schema': 'public'},
    )
    Id: Mapped[UUID] = mapped_column('Id', UUIDType, primary_key=True, nullable=False)
    Title: Mapped[str] = mapped_column('Title', CITEXT, nullable=False)


class Lessons(Base):
    __tablename__ = 'Lessons'
    __table_args__ = (
        {'schema': 'public'},
    )
    Id: Mapped[UUID] = mapped_column('Id', UUIDType, primary_key=True, nullable=False)
    Title: Mapped[str] = mapped_column('Title', CITEXT, nullable=False)
    Description: Mapped[str | None] = mapped_column('Description', CITEXT, nullable=True)
    Duration: Mapped[str | None] = mapped_column('Duration', String(32), nullable=True)
    IsDeleted: Mapped[bool] = mapped_column('IsDeleted', Boolean, nullable=False)


class CourseLessonBindings(Base):
    __tablename__ = 'CourseLessonBindings'
    __table_args__ = (
        {'schema': 'public'},
    )
    CourseId: Mapped[UUID] = mapped_column('CourseId', UUIDType, ForeignKey('public.Courses.Id', ondelete="RESTRICT"), primary_key=True, nullable=False)
    LessonId: Mapped[UUID] = mapped_column('LessonId', UUIDType, ForeignKey('public.Lessons.Id', ondelete="RESTRICT"), primary_key=True, nullable=False)
    Order: Mapped[int | None] = mapped_column('Order', Integer, nullable=True)
    IsTrial: Mapped[bool] = mapped_column('IsTrial', Boolean, nullable=False)
    IsDeleted: Mapped[bool] = mapped_column('IsDeleted', Boolean, nullable=False)


class CourseInfoTypes(Base):
    __tablename__ = 'CourseInfoTypes'
    __table_args__ = (
        {'schema': 'public'},
    )
    Id: Mapped[UUID] = mapped_column('Id', UUIDType, primary_key=True, nullable=False)
    Title: Mapped[str] = mapped_column('Title', CITEXT, nullable=False)


class CourseTariffBindings(Base):
    __tablename__ = 'CourseTariffBindings'
    __table_args__ = (
        {'schema': 'public'},
    )
    Id: Mapped[UUID] = mapped_column('Id', UUIDType, primary_key=True, nullable=False)
    CourseId: Mapped[UUID] = mapped_column('CourseId', UUIDType, ForeignKey('public.Courses.Id', ondelete="RESTRICT"), nullable=False)
    Title: Mapped[str] = mapped_column('Title', CITEXT, nullable=False)
    Cost: Mapped[int] = mapped_column('Cost', Integer, nullable=False)
    Description: Mapped[str | None] = mapped_column('Description', CITEXT, nullable=True)


class CourseInfoBindings(Base):
    __tablename__ = 'CourseInfoBindings'
    __table_args__ = (
        {'schema': 'public'},
    )
    Id: Mapped[UUID] = mapped_column('Id', UUIDType, primary_key=True, nullable=False)
    CourseId: Mapped[UUID] = mapped_column('CourseId', UUIDType, ForeignKey('public.Courses.Id', ondelete="RESTRICT"), nullable=False)
    CourseInfoTypeId: Mapped[UUID] = mapped_column('CourseInfoTypeId', UUIDType, ForeignKey('public.CourseInfoTypes.Id', ondelete="RESTRICT"), nullable=False)
    CourseTariffId: Mapped[UUID | None] = mapped_column('CourseTariffId', UUIDType, ForeignKey('public.CourseTariffBindings.Id', ondelete="RESTRICT"), nullable=True)
    Title: Mapped[str] = mapped_column('Title', CITEXT, nullable=False)
    Description: Mapped[str | None] = mapped_column('Description', CITEXT, nullable=True)
    Order: Mapped[int | None] = mapped_column('Order', Integer, nullable=True)


class ContentSettings(Base):
    __tablename__ = 'ContentSettings'
    __table_args__ = (
        {'schema': 'public'},
    )
    Id: Mapped[UUID] = mapped_column('Id', UUIDType, primary_key=True, nullable=False)
    EntityId: Mapped[UUID] = mapped_column('EntityId', UUIDType, nullable=False)
    EntityTypeId: Mapped[UUID] = mapped_column('EntityTypeId', UUIDType, nullable=False)
    StatusId: Mapped[UUID] = mapped_column('StatusId', UUIDType, nullable=False)
    IsDeleted: Mapped[bool] = mapped_column('IsDeleted', Boolean, nullable=False)


class Topics(Base):
    __tablename__ = 'Topics'
    __table_args__ = (
        {'schema': 'public'},
    )
    Id: Mapped[UUID] = mapped_column('Id', UUIDType, primary_key=True, nullable=False)
    Title: Mapped[str] = mapped_column('Title', CITEXT, nullable=False)


class Tags(Base):
    __tablename__ = 'Tags'
    __table_args__ = (
        {'schema': 'public'},
    )
    Id: Mapped[UUID] = mapped_column('Id', UUIDType, primary_key=True, nullable=False)
    Title: Mapped[str] = mapped_column('Title', CITEXT, nullable=False)


class Industries(Base):
    __tablename__ = 'Industries'
    __table_args__ = (
        {'schema': 'public'},
    )
    Id: Mapped[UUID] = mapped_column('Id', UUIDType, primary_key=True, nullable=False)
    Title: Mapped[str] = mapped_column('Title', CITEXT, nullable=False)


class ContentSettingsTopics(Base):
    __tablename__ = 'ContentSettingsTopics'
    __table_args__ = (
        {'schema': 'public'},
    )
    ContentSettingsId: Mapped[UUID] = mapped_column('ContentSettingsId', UUIDType, ForeignKey('public.ContentSettings.Id', ondelete="RESTRICT"), primary_key=True, nullable=False)
    TopicId: Mapped[UUID] = mapped_column('TopicId', UUIDType, ForeignKey('public.Topics.Id', ondelete="RESTRICT"), primary_key=True, nullable=False)
    Order: Mapped[int] = mapped_column('Order', Integer, nullable=False)


class ContentSettingsTags(Base):
    __tablename__ = 'ContentSettingsTags'
    __table_args__ = (
        {'schema': 'public'},
    )
    ContentSettingsId: Mapped[UUID] = mapped_column('ContentSettingsId', UUIDType, ForeignKey('public.ContentSettings.Id', ondelete="RESTRICT"), primary_key=True, nullable=False)
    TagId: Mapped[UUID] = mapped_column('TagId', UUIDType, ForeignKey('public.Tags.Id', ondelete="RESTRICT"), primary_key=True, nullable=False)
    Order: Mapped[int] = mapped_column('Order', Integer, nullable=False)


class ContentSettingsIndustries(Base):
    __tablename__ = 'ContentSettingsIndustries'
    __table_args__ = (
        {'schema': 'public'},
    )
    ContentSettingsId: Mapped[UUID] = mapped_column('ContentSettingsId', UUIDType, ForeignKey('public.ContentSettings.Id', ondelete="RESTRICT"), primary_key=True, nullable=False)
    IndustryId: Mapped[UUID] = mapped_column('IndustryId', UUIDType, ForeignKey('public.Industries.Id', ondelete="RESTRICT"), primary_key=True, nullable=False)
    Order: Mapped[int] = mapped_column('Order', Integer, nullable=False)


class CourseUserBindings(Base):
    __tablename__ = 'CourseUserBindings'
    __table_args__ = (
        {'schema': 'public'},
    )
    Id: Mapped[UUID] = mapped_column('Id', UUIDType, primary_key=True, nullable=False)
    CourseId: Mapped[UUID] = mapped_column('CourseId', UUIDType, ForeignKey('public.Courses.Id', ondelete="RESTRICT"), nullable=False)
    UserId: Mapped[UUID] = mapped_column('UserId', UUIDType, nullable=False)
    IsCompleted: Mapped[bool] = mapped_column('IsCompleted', Boolean, nullable=False)
    Completed: Mapped[datetime | None] = mapped_column('Completed', DateTime(timezone=True), nullable=True)
    StudyingStartDate: Mapped[datetime | None] = mapped_column('StudyingStartDate', DateTime(timezone=True), nullable=True)
    LessonsCompleted: Mapped[int] = mapped_column('LessonsCompleted', Integer, nullable=False)
    IsPaid: Mapped[bool] = mapped_column('IsPaid', Boolean, nullable=False)
    SubscriptionId: Mapped[UUID | None] = mapped_column('SubscriptionId', UUIDType, nullable=True)
    IsDeleted: Mapped[bool] = mapped_column('IsDeleted', Boolean, nullable=False)


class CourseUserLessonBindings(Base):
    __tablename__ = 'CourseUserLessonBindings'
    __table_args__ = (
        {'schema': 'public'},
    )
    Id: Mapped[UUID] = mapped_column('Id', UUIDType, primary_key=True, nullable=False)
    CourseUserId: Mapped[UUID] = mapped_column('CourseUserId', UUIDType, ForeignKey('public.CourseUserBindings.Id', ondelete="RESTRICT"), nullable=False)
    LessonId: Mapped[UUID] = mapped_column('LessonId', UUIDType, ForeignKey('public.Lessons.Id', ondelete="RESTRICT"), nullable=False)
    StudyingStartDate: Mapped[datetime | None] = mapped_column('StudyingStartDate', DateTime(timezone=True), nullable=True)
    Completed: Mapped[datetime | None] = mapped_column('Completed', DateTime(timezone=True), nullable=True)


class UserRatings(Base):
    __tablename__ = 'UserRatings'
    __table_args__ = (
        {'schema': 'public'},
    )
    Id: Mapped[UUID] = mapped_column('Id', UUIDType, primary_key=True, nullable=False)
    UserId: Mapped[UUID | None] = mapped_column('UserId', UUIDType, nullable=True)
    EntityId: Mapped[UUID] = mapped_column('EntityId', UUIDType, nullable=False)
    EntityTypeId: Mapped[UUID] = mapped_column('EntityTypeId', UUIDType, nullable=False)
    Value: Mapped[int] = mapped_column('Value', SmallInteger, nullable=False)
    Created: Mapped[datetime] = mapped_column('Created', DateTime(timezone=True), nullable=False)
    IsDeleted: Mapped[bool] = mapped_column('IsDeleted', Boolean, nullable=False)


class RatingTags(Base):
    __tablename__ = 'RatingTags'
    __table_args__ = (
        {'schema': 'public'},
    )
    Id: Mapped[UUID] = mapped_column('Id', UUIDType, primary_key=True, nullable=False)
    Title: Mapped[str] = mapped_column('Title', CITEXT, nullable=False)


class UserRatingTagsBindings(Base):
    __tablename__ = 'UserRatingTagsBindings'
    __table_args__ = (
        {'schema': 'public'},
    )
    UserRatingId: Mapped[UUID] = mapped_column('UserRatingId', UUIDType, ForeignKey('public.UserRatings.Id', ondelete="RESTRICT"), primary_key=True, nullable=False)
    TagId: Mapped[UUID] = mapped_column('TagId', UUIDType, ForeignKey('public.RatingTags.Id', ondelete="RESTRICT"), primary_key=True, nullable=False)
    Text: Mapped[str | None] = mapped_column('Text', String(500), nullable=True)


class Subscription(Base):
    __tablename__ = 'Subscription'
    __table_args__ = (
        {'schema': 'public'},
    )
    Id: Mapped[UUID] = mapped_column('Id', UUIDType, primary_key=True, nullable=False)
    Title: Mapped[str] = mapped_column('Title', CITEXT, nullable=False)
    Description: Mapped[str | None] = mapped_column('Description', CITEXT, nullable=True)
    IsDeleted: Mapped[bool] = mapped_column('IsDeleted', Boolean, nullable=False)


class SubscriptionTariffs(Base):
    __tablename__ = 'SubscriptionTariffs'
    __table_args__ = (
        {'schema': 'public'},
    )
    Id: Mapped[UUID] = mapped_column('Id', UUIDType, primary_key=True, nullable=False)
    SubscriptionId: Mapped[UUID] = mapped_column('SubscriptionId', UUIDType, ForeignKey('public.Subscription.Id', ondelete="RESTRICT"), nullable=False)
    Title: Mapped[str] = mapped_column('Title', CITEXT, nullable=False)
    Cost: Mapped[int] = mapped_column('Cost', Integer, nullable=False)
    DiscountCost: Mapped[int | None] = mapped_column('DiscountCost', Integer, nullable=True)
    Recurrence: Mapped[int] = mapped_column('Recurrence', Integer, nullable=False)
    RecurrenceValue: Mapped[int] = mapped_column('RecurrenceValue', Integer, nullable=False)


class CourseSubscriptions(Base):
    __tablename__ = 'CourseSubscriptions'
    __table_args__ = (
        {'schema': 'public'},
    )
    CourseId: Mapped[UUID] = mapped_column('CourseId', UUIDType, ForeignKey('public.Courses.Id', ondelete="RESTRICT"), primary_key=True, nullable=False)
    SubscriptionId: Mapped[UUID] = mapped_column('SubscriptionId', UUIDType, ForeignKey('public.Subscription.Id', ondelete="RESTRICT"), primary_key=True, nullable=False)


class RecommendedItems(Base):
    __tablename__ = 'RecommendedItems'
    __table_args__ = (
        {'schema': 'public'},
    )
    Id: Mapped[UUID] = mapped_column('Id', UUIDType, primary_key=True, nullable=False)
    ItemId: Mapped[UUID] = mapped_column('ItemId', UUIDType, primary_key=True, nullable=False)
    ItemTypeId: Mapped[UUID] = mapped_column('ItemTypeId', UUIDType, primary_key=True, nullable=False)
    CourseId: Mapped[UUID | None] = mapped_column('CourseId', UUIDType, nullable=True)
    Order: Mapped[int | None] = mapped_column('Order', Integer, nullable=True)


class Articles(Base):
    __tablename__ = 'Articles'
    __table_args__ = (
        {'schema': 'public'},
    )
    Id: Mapped[UUID] = mapped_column('Id', UUIDType, primary_key=True, nullable=False)
    Title: Mapped[str] = mapped_column('Title', CITEXT, nullable=False)
    Description: Mapped[str | None] = mapped_column('Description', CITEXT, nullable=True)
    Content: Mapped[str | None] = mapped_column('Content', CITEXT, nullable=True)
    Duration: Mapped[str | None] = mapped_column('Duration', CITEXT, nullable=True)
    Url: Mapped[str] = mapped_column('Url', CITEXT, nullable=False)
    StatusId: Mapped[UUID] = mapped_column('StatusId', UUIDType, ForeignKey('public.Statuses.Id', ondelete="RESTRICT"), nullable=False)
    SubjectId: Mapped[UUID | None] = mapped_column('SubjectId', UUIDType, ForeignKey('public.ArticleSubjects.Id', ondelete="RESTRICT"), nullable=True)
    IsLesson: Mapped[bool] = mapped_column('IsLesson', Boolean, nullable=False)
    IsPublic: Mapped[bool] = mapped_column('IsPublic', Boolean, nullable=False)
    IsClosed: Mapped[bool] = mapped_column('IsClosed', Boolean, nullable=False)
    IsDeleted: Mapped[bool] = mapped_column('IsDeleted', Boolean, nullable=False)
    Published: Mapped[datetime | None] = mapped_column('Published', DateTime(timezone=True), nullable=True)


class DocumentTypes(Base):
    __tablename__ = 'DocumentTypes'
    __table_args__ = (
        {'schema': 'public'},
    )
    Id: Mapped[UUID] = mapped_column('Id', UUIDType, primary_key=True, nullable=False)
    Title: Mapped[str] = mapped_column('Title', CITEXT, nullable=False)
    Description: Mapped[str | None] = mapped_column('Description', CITEXT, nullable=True)
    IsDeleted: Mapped[bool] = mapped_column('IsDeleted', Boolean, nullable=False)


class Files(Base):
    __tablename__ = 'Files'
    __table_args__ = (
        {'schema': 'public'},
    )
    Id: Mapped[UUID] = mapped_column('Id', UUIDType, primary_key=True, nullable=False)
    Title: Mapped[str] = mapped_column('Title', CITEXT, nullable=False)
    Url: Mapped[str] = mapped_column('Url', Text, nullable=False)
    Size: Mapped[int] = mapped_column('Size', BigInteger, nullable=False)
    Extension: Mapped[str] = mapped_column('Extension', Text, nullable=False)
    IsDeleted: Mapped[bool] = mapped_column('IsDeleted', Boolean, nullable=False)


class Documents(Base):
    __tablename__ = 'Documents'
    __table_args__ = (
        {'schema': 'public'},
    )
    Id: Mapped[UUID] = mapped_column('Id', UUIDType, primary_key=True, nullable=False)
    Title: Mapped[str] = mapped_column('Title', CITEXT, nullable=False)
    Description: Mapped[str | None] = mapped_column('Description', CITEXT, nullable=True)
    Url: Mapped[str] = mapped_column('Url', CITEXT, nullable=False)
    TypeId: Mapped[UUID] = mapped_column('TypeId', UUIDType, ForeignKey('public.DocumentTypes.Id', ondelete="RESTRICT"), nullable=False)
    FileId: Mapped[UUID | None] = mapped_column('FileId', UUIDType, ForeignKey('public.Files.Id', ondelete="RESTRICT"), nullable=True)
    FileIdNew: Mapped[UUID | None] = mapped_column('FileIdNew', UUIDType, nullable=True)
    Extension: Mapped[str | None] = mapped_column('Extension', String(7), nullable=True)
    Size: Mapped[int | None] = mapped_column('Size', Integer, nullable=True)
    StatusId: Mapped[UUID] = mapped_column('StatusId', UUIDType, ForeignKey('public.Statuses.Id', ondelete="RESTRICT"), nullable=False)
    IsDeleted: Mapped[bool] = mapped_column('IsDeleted', Boolean, nullable=False)
    Published: Mapped[datetime | None] = mapped_column('Published', DateTime(timezone=True), nullable=True)


class CourseTypes(Base):
    __tablename__ = 'CourseTypes'
    __table_args__ = (
        {'schema': 'public'},
    )
    Id: Mapped[UUID] = mapped_column('Id', UUIDType, primary_key=True, nullable=False)
    Title: Mapped[str] = mapped_column('Title', CITEXT, nullable=False)
    IsDeleted: Mapped[bool] = mapped_column('IsDeleted', Boolean, nullable=False)


class ArticleSubjects(Base):
    __tablename__ = 'ArticleSubjects'
    __table_args__ = (
        {'schema': 'public'},
    )
    Id: Mapped[UUID] = mapped_column('Id', UUIDType, primary_key=True, nullable=False)
    Title: Mapped[str] = mapped_column('Title', CITEXT, nullable=False)
    Description: Mapped[str | None] = mapped_column('Description', CITEXT, nullable=True)
    IsPublic: Mapped[bool] = mapped_column('IsPublic', Boolean, nullable=False)
    IsDeleted: Mapped[bool] = mapped_column('IsDeleted', Boolean, nullable=False)
    Url: Mapped[str | None] = mapped_column('Url', CITEXT, nullable=True)


class DocumentBindings(Base):
    __tablename__ = 'DocumentBindings'
    __table_args__ = (
        {'schema': 'public'},
    )
    DocumentId: Mapped[UUID] = mapped_column('DocumentId', UUIDType, ForeignKey('public.Documents.Id', ondelete="RESTRICT"), primary_key=True, nullable=False)
    LinkedDocumentId: Mapped[UUID] = mapped_column('LinkedDocumentId', UUIDType, ForeignKey('public.Documents.Id', ondelete="RESTRICT"), primary_key=True, nullable=False)
    Order: Mapped[int | None] = mapped_column('Order', Integer, nullable=True)


