import asyncio
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from app.api import (
    admin,
    audio,
    auth,
    jobs,
    media,
    models,
    projects,
    providers,
    scenes,
    storage,
    styles,
    templates,
    uploads,
    users,
)
from app.api.websocket import manager as ws_manager
from app.config import get_settings
from app.database import User, async_session, create_tables, seed_builtin_data, seed_rbac_data
from app.services.model_manager import ModelManager, ModelManagerError


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    settings = get_settings()
    if settings.debug:
        await create_tables()

    # Discover and register template plugins
    from app.plugins.registry import discover_plugins, get_all_plugins
    discover_plugins()
    for pid, plugin in get_all_plugins().items():
        print(f"[Plugin] {pid}: {plugin.display_name}")

    await seed_builtin_data()
    await seed_rbac_data()

    # Create initial superuser if none exists
    from passlib.context import CryptContext
    from sqlalchemy import select as sa_select

    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    async with async_session() as db:
        result = await db.execute(sa_select(User).where(User.is_superuser))
        if not result.scalars().first():
            admin_user = User(
                email=settings.admin_email,
                hashed_password=pwd_context.hash(settings.admin_password),
                is_active=True,
                is_superuser=True,
            )
            db.add(admin_user)
            await db.commit()
            print(f"[Init] Created admin user: {settings.admin_email}")
        else:
            print("[Init] Admin user already exists")

    model_manager = ModelManager()
    try:
        required = ModelManager.get_required_models()
        results = await model_manager.ensure_models(required)
        for model, status in results.items():
            if status == "available":
                print(f"[ModelManager] {model} already available")
            elif status == "pulled":
                print(f"[ModelManager] Pulled {model}")
            else:
                print(f"[ModelManager] WARNING: {model} is not available and could not be pulled")
    except ModelManagerError as e:
        print(f"[ModelManager] Warning: {e}")
    finally:
        await model_manager.close()

    yield


app = FastAPI(
    title="VidForge API",
    description="API for automated social media video generation",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173", "http://10.80.2.253"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(users.router, prefix="/api/users", tags=["users"])
app.include_router(jobs.router, prefix="/api/jobs", tags=["jobs"])
app.include_router(templates.router, prefix="/api/templates", tags=["templates"])
app.include_router(styles.router, prefix="/api/styles", tags=["styles"])
app.include_router(storage.router, prefix="/api/storage", tags=["storage"])
app.include_router(uploads.router, prefix="/api/uploads", tags=["uploads"])
app.include_router(admin.router, prefix="/api/admin", tags=["admin"])
app.include_router(providers.router, prefix="/api/providers", tags=["providers"])
app.include_router(models.router, prefix="/api/models", tags=["models"])
app.include_router(scenes.router, prefix="/api/jobs", tags=["scenes"])
app.include_router(media.router, prefix="/api/media", tags=["media"])
app.include_router(audio.router, prefix="/api/audio", tags=["audio"])
app.include_router(projects.router, prefix="/api", tags=["projects"])


@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "healthy"}


@app.get("/health/models")
async def health_models() -> dict[str, Any]:
    from app.services.model_manager import ModelManager, ModelManagerError

    model_manager = ModelManager()
    try:
        required = ModelManager.get_required_models()
        available = await model_manager.list_available_models()
        results: dict[str, str] = {}
        for model in required:
            results[model] = "available" if model in available else "missing"
        return {"models": results}
    except ModelManagerError as e:
        return {"models": {}, "error": str(e)}
    finally:
        await model_manager.close()


@app.websocket("/ws/jobs/{job_id}")
async def websocket_job_updates(websocket: WebSocket, job_id: str) -> None:
    await ws_manager.connect(websocket, job_id)
    try:
        subscribe_task = asyncio.create_task(ws_manager.subscribe_to_job(job_id, websocket))
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            pass
        finally:
            subscribe_task.cancel()
    finally:
        ws_manager.disconnect(websocket, job_id)
