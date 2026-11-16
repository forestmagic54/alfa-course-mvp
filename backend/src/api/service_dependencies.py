from typing import Annotated

from fastapi import Depends

from src.api.dependencies import ContextDep, SessionDep
from src.config import load_demo_config
from src.db.crud.commerce import CommerceCRUD
from src.db.crud.email import EmailCRUD
from src.db.crud.favorites import FavoritesCRUD
from src.db.crud.material_explanations import MaterialExplanationsCRUD
from src.db.crud.material_studies import MaterialStudiesCRUD
from src.db.crud.materials import MaterialsCRUD
from src.db.crud.onboarding import OnboardingCRUD
from src.db.crud.recommendations import RecommendationsCRUD
from src.db.crud.users import UsersCRUD
from src.services.auth import AuthService
from src.services.commerce import CommerceService
from src.services.email import EmailService
from src.services.favorites import FavoriteService
from src.services.feeds import FeedService
from src.services.material_explanations import (
    ExplanationReader,
    MaterialExplanationService,
)
from src.services.material_studies import MaterialStudyService
from src.services.materials import MaterialService
from src.services.onboarding import OnboardingService
from src.services.recommendations import RecommendationService
from src.services.roadmaps import RoadmapService


def get_auth_service(session: SessionDep) -> AuthService:
    return AuthService(session, UsersCRUD(session), FavoritesCRUD(session),
                       load_demo_config()['favorites']['default_folder_name'])


def get_material_service(session: SessionDep) -> MaterialService:
    return MaterialService(lambda config: MaterialsCRUD(session, config), CommerceCRUD(session), FavoritesCRUD(session),
                           ExplanationReader(MaterialExplanationsCRUD(session), OnboardingCRUD(session)))


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]
MaterialServiceDep = Annotated[MaterialService, Depends(get_material_service)]


def get_explanation_service(session: SessionDep, context: ContextDep) -> MaterialExplanationService:
    return MaterialExplanationService(session, MaterialsCRUD(session, load_demo_config()), OnboardingCRUD(session),
                                      UsersCRUD(session), MaterialExplanationsCRUD(session),
                                      getattr(context.generator, 'client', None), context.settings.app.generation_timeout_seconds)


ExplanationServiceDep = Annotated[MaterialExplanationService, Depends(get_explanation_service)]


def get_onboarding_service(session: SessionDep) -> OnboardingService:
    return OnboardingService(session, UsersCRUD(session), OnboardingCRUD(session), CommerceCRUD(session))


def get_feed_service(session: SessionDep, context: ContextDep, materials: MaterialServiceDep) -> FeedService:
    ranker = RecommendationService(session, context.ranker, context.generator, context.fallback_generator,
                                   context.settings.app.generation_timeout_seconds,
                                   materials.materials_factory, materials.build_cards)
    return FeedService(session, RecommendationsCRUD(session), OnboardingCRUD(session), UsersCRUD(session),
                       materials.materials_factory(load_demo_config()), ranker, materials.build_cards)


OnboardingServiceDep = Annotated[OnboardingService, Depends(get_onboarding_service)]
FeedServiceDep = Annotated[FeedService, Depends(get_feed_service)]


def get_roadmap_service(session: SessionDep, context: ContextDep, materials: MaterialServiceDep) -> RoadmapService:
    feed = get_feed_service(session, context, materials)
    return RoadmapService(session, feed.recommendations, feed.onboarding, feed.users, feed.catalog,
                          feed.ranker, materials.build_cards, MaterialStudiesCRUD(session))


def get_material_study_service(session: SessionDep) -> MaterialStudyService:
    return MaterialStudyService(session, MaterialsCRUD(session, load_demo_config()), MaterialStudiesCRUD(session))


RoadmapServiceDep = Annotated[RoadmapService, Depends(get_roadmap_service)]
MaterialStudyServiceDep = Annotated[MaterialStudyService, Depends(get_material_study_service)]


def get_favorite_service(session: SessionDep, materials: MaterialServiceDep) -> FavoriteService:
    config = load_demo_config()
    return FavoriteService(session, FavoritesCRUD(session), MaterialsCRUD(session, config), materials, config)


FavoriteServiceDep = Annotated[FavoriteService, Depends(get_favorite_service)]


def get_commerce_service(session: SessionDep):
    config = load_demo_config()
    return CommerceService(session, UsersCRUD(session), CommerceCRUD(session), MaterialsCRUD(session, config), config)


CommerceServiceDep = Annotated[CommerceService, Depends(get_commerce_service)]


def get_email_service(session: SessionDep) -> EmailService:
    return EmailService(session, UsersCRUD(session), EmailCRUD(session),
                        load_demo_config()['email']['consent_version'])


EmailServiceDep = Annotated[EmailService, Depends(get_email_service)]
