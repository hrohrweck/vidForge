from app.api.auth import router as auth_router
from app.api.jobs import router as jobs_router
from app.api.styles import router as styles_router
from app.api.storage import router as storage_router
from app.api.templates import router as templates_router
from app.api.users import router as users_router

__all__ = [
    "auth_router",
    "jobs_router",
    "styles_router",
    "storage_router",
    "templates_router",
    "users_router",
]
