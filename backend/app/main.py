import asyncio
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from app.api import admin, auth, jobs, models, styles, storage, templates, uploads, users, providers
from app.api.websocket import manager as ws_manager
from app.config import get_settings
from app.database import create_tables, seed_builtin_data


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    settings = get_settings()
    if settings.debug:
        await create_tables()
    await seed_builtin_data()
    yield


app = FastAPI(
    title="VidForge API",
    description="API for automated social media video generation",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
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


@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "healthy"}


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
