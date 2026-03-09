from fastapi import APIRouter

from app.api.routes.content import router as content_router
from app.api.routes.dispatch import router as dispatch_router
from app.api.routes.health import router as health_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(dispatch_router)
api_router.include_router(content_router)
