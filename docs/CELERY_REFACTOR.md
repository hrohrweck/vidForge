# Celery Worker Architecture

> **Status**: Implemented. This document reflects the current state.

## Architecture

Celery workers run in a prefork pool. Each worker child process maintains a
**singleton `WorkerContext`** that holds shared async resources for the
lifetime of that process — eliminating the per-task overhead of creating new
event loops, database engines, and Redis connections.

```
Worker process startup
    │
    ├─ worker_process_init signal
    │     ├─ discover_plugins()           — load all plugins from backend/plugins/
    │     └─ ctx.start()                  — create shared resources
    │           ├─ Background thread with persistent asyncio event loop
    │           ├─ One AsyncEngine (pooled connections to PostgreSQL)
    │           ├─ One redis.asyncio.Redis (pooled)
    │           └─ One async_sessionmaker
    │
    ├─ Task: process_scene_video_job(job_id, stage)
    │     └─ ctx.run(_process_scene_video_job(...))
    │           ├─ Opens a session from ctx.session_factory
    │           ├─ Delegates to dispatch_stage() or dispatch_scene_rerender()
    │           └─ Properly scopes sessions per operation
    │
    └─ worker_process_shutdown signal
          ├─ Dispose AsyncEngine
          ├─ Close Redis
          └─ Stop event loop
```

## Key Files

| File | Purpose |
|---|---|
| `app/workers/celery_app.py` | Celery app factory + worker signals |
| `app/workers/context.py` | `WorkerContext` singleton with `ctx.run()` |
| `app/workers/dispatcher.py` | Plugin-aware stage dispatcher |
| `app/workers/tasks.py` | Thin sync shims that call `ctx.run()` |

## Task Reference

| Task | Stage | Description |
|---|---|---|
| `process_video_job` | — | Legacy single-clip generation (non-scene jobs) |
| `process_scene_video_job` | `generating_images` / `generating_videos` | Runs a pipeline stage via the plugin dispatcher |
| `generate_scene_media` | — | Re-render a single scene's image or video |
| `export_scene_video` | `rendering` | Exports final video via `dispatch_stage('rendering')` |
| `send_heartbeat` | — | Registers worker in DB |
| `cleanup_stale_workers` | — | Removes stale worker heartbeats |
| `reset_daily_budgets` | — | Resets daily spend counters |
| `generate_preview` | — | Creates low-res preview of a video |
| `merge_videos` | — | Concatenates video segments |
| `sync_provider_models` | — | Syncs available models for all active providers of a given type via `registry.create()` + `instance.sync_models()` |
| `sync_all_provider_models` | — | Queries all active provider types from DB and dispatches `sync_provider_models` for each |

## Plugin Dispatcher

The scene-based pipeline is routed through `dispatch_stage()` in
`app/workers/dispatcher.py`:

```
dispatch_stage(job_id, stage)
    ├─ Load job → resolve plugin (from template config)
    ├─ stage == "planning"         → plugin.enrich_inputs() + plugin.plan_scenes()
    ├─ stage == "generating_images" → plugin.generate_images()
    ├─ stage == "generating_videos" → plugin.generate_videos()
    └─ stage == "rendering"        → plugin.render()
```

## Adding a New Celery Task

1. Define the async function that does the real work.
2. Create a thin sync wrapper:

```python
@celery_app.task(bind=True, time_limit=TASK_TIME_LIMIT)
def my_new_task(self, job_id: str, ...):
    return ctx.run(_my_new_task(job_id, ...))

async def _my_new_task(job_id: str, ...):
    async with ctx.session_factory() as db:
        ...
```

3. Never use `asyncio.run()` inside tasks — always use `ctx.run()`.
