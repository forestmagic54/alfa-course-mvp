from fastapi import APIRouter

from src.api.account.routes import router as account_router
from src.api.auth.routes import router as auth_router
from src.api.discounts.routes import router as discounts_router
from src.api.email_preferences.routes import router as email_preferences_router
from src.api.favorites.routes import router as favorites_router
from src.api.material_studies.routes import router as material_studies_router
from src.api.materials.routes import router as materials_router
from src.api.onboarding.routes import router as onboarding_router
from src.api.preferences.routes import router as preferences_router
from src.api.purchases.routes import router as purchases_router
from src.api.recommendations.routes import router as recommendations_router
from src.api.roadmaps.routes import router as roadmaps_router
from src.api.subscriptions.routes import router as subscriptions_router

api_router = APIRouter()
api_router.include_router(materials_router)
api_router.include_router(auth_router)
api_router.include_router(account_router)
api_router.include_router(email_preferences_router)
api_router.include_router(favorites_router)

api_router.include_router(onboarding_router)
api_router.include_router(preferences_router)

api_router.include_router(recommendations_router)

api_router.include_router(roadmaps_router)
api_router.include_router(material_studies_router)


api_router.include_router(discounts_router)
api_router.include_router(purchases_router)
api_router.include_router(subscriptions_router)
