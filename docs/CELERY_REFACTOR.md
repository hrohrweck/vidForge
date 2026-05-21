# Celery Worker Refactoring Plan

## Problem Statement

Every Celery task in `backend/app/workers/tasks.py` wraps its async logic in
`asyncio.run()`.  This creates a **brand-new event loop** per task invocation,
which in turn creates:

1. **A new SQLAlchemy `AsyncEngine`** per call to `get_db_session_factory()`
   — no connection pooling across tasks; sockets are opened/closed for every
   DB access.
2. **A new `redis.Redis` connection** per call to `get_redis()` / `broadcast_update()`
   — same problem; TCP connect/disconnect overhead on every status broadcast.
3. **No cleanup** — engines are never `.dispose()`d, so PostgreSQL connections
   accumulate until the process hits the connection limit.
4. **`ComfyUISemaphore`** opens its own Redis connection per acquire/release cycle.

With 9 `asyncio.run()` calls, 10 `get_db_session_factory()` calls, and 4 raw
Redis connections, a single `process_video_job` execution can open **dozens of
database and Redis connections** that are never reused.

### Concrete Impact

| Symptom | Cause |
|---|---|
| PostgreSQL `too many connections` under load | Engine per `get_db_session_factory()` |
| Slow task startup (50-100ms) | New event loop + engine + pool init |
| Redis connection exhaustion | `get_redis()` creates untracked clients |
| Stale DB pool after broker reconnect | Engine created inside `asyncio.run()` is destroyed with the loop |

---

## Proposed Architecture

### Core Idea

Replace `asyncio.run()` with a **long-lived event loop** managed by a Celery
**worker signal**.  The event loop, database engine, and Redis connection pool
are created once when the worker process starts and reused across all tasks.

```
Worker process startup
    │
    ├─ Celery worker_init signal
    │     ├─ Create a single asyncio event loop (background thread)
    │     ├─ Create one AsyncEngine (pooled)
    │     ├─ Create one redis.asyncio.Redis (pooled)
    │     └─ Create one async_sessionmaker
    │
    ├─ Task: process_video_job(job_id)
    │     └─ _loop.run_until_complete(_process_video_job(job_id))
    │           ├─ Uses shared async_session_maker
    │           ├─ Uses shared redis client
    │           └─ Properly scopes sessions per operation
    │
    └─ Celery worker_process_shutdown signal
          ├─ Dispose AsyncEngine
          ├─ Close Redis
          └─ Stop event loop
```

### Why a Background Thread?

Celery workers are synchronous — `celery_app.task` decorators produce sync
functions.  We have three options:

| Approach | Pros | Cons |
|---|---|---|
| **A. Background thread + `run_coroutine_threadsafe`** | Minimal Celery changes; engine lives across tasks | Thread-safety requires care |
| **B. Switch to a native async task queue** (e.g. `arq`, `dramatiq[async]`) | Clean async throughout | Major rewrite; new infra |
| **C. Single `asyncio.run()` per worker with `celery -P eventlet/gevent`** | Standard pattern | Greenlet + asyncpg don't mix well |

**Option A is the pragmatic choice** — it keeps Celery, keeps the task
signatures identical, and only changes the internals.  The asyncpg driver is
thread-safe for separate connections, and we'll use thread-safe session
scoping.

---

## Implementation Steps

### Phase 1: Worker Context (shared resources)

**New file: `backend/app/workers/context.py`**

Holds the long-lived resources for the worker process:

```python
"""
WorkerContext — singleton holding long-lived async resources for a Celery
worker process.  Initialized once via Celery worker_init signal.
"""

import asyncio
import logging
from threading import Thread
from typing import Optional

import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import get_settings

logger = logging.getLogger(__name__)

_settings = get_settings()


class WorkerContext:
    """Manages the lifecycle of shared async resources."""

    def __init__(self) -> None:
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[Thread] = None
        self._engine: Optional[AsyncEngine] = None
        self._session_factory: Optional[async_sessionmaker[AsyncSession]] = None
        self._redis: Optional[aioredis.Redis] = None

    # ---- Lifecycle --------------------------------------------------------

    def start(self) -> None:
        """Start the background event loop (called from worker_init signal)."""
        self._loop = asyncio.new_event_loop()
        self._thread = Thread(target=self._loop.run_forever, daemon=True)
        self._thread.start()

        # Create resources on the loop
        fut = asyncio.run_coroutine_threadsafe(self._create_resources(), self._loop)
        fut.result(timeout=10)  # block until ready
        logger.info("[WorkerContext] Started — engine and redis ready")

    async def _create_resources(self) -> None:
        self._engine = create_async_engine(
            _settings.database_url,
            echo=_settings.debug,
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,
        )
        self._session_factory = async_sessionmaker(
            self._engine, class_=AsyncSession, expire_on_commit=False,
        )
        self._redis = aioredis.from_url(
            _settings.redis_url, decode_responses=True,
        )

    def stop(self) -> None:
        """Teardown (called from worker_process_shutdown signal)."""
        if self._loop is None:
            return
        fut = asyncio.run_coroutine_threadsafe(self._dispose_resources(), self._loop)
        try:
            fut.result(timeout=10)
        except Exception:
            pass
        self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("[WorkerContext] Stopped")

    async def _dispose_resources(self) -> None:
        if self._redis:
            await self._redis.close()
        if self._engine:
            await self._engine.dispose()

    # ---- Accessors --------------------------------------------------------

    @property
    def loop(self) -> asyncio.AbstractEventLoop:
        assert self._loop is not None, "WorkerContext not started"
        return self._loop

    @property
    def session_factory(self) -> async_sessionmaker[AsyncSession]:
        assert self._session_factory is not None
        return self._session_factory

    @property
    def redis(self) -> aioredis.Redis:
        assert self._redis is not None
        return self._redis

    # ---- Run coroutine on the shared loop ---------------------------------

    def run(self, coro):
        """Submit a coroutine and block until it returns (thread-safe)."""
        fut = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return fut.result()


# Module-level singleton — initialized by worker signals
ctx = WorkerContext()
```

**Changes to `backend/app/workers/celery_app.py`**:

```python
from celery.signals import worker_init, worker_process_shutdown

@worker_init.connect
def on_worker_init(**kwargs):
    from app.workers.context import ctx
    ctx.start()

@worker_process_shutdown.connect
def on_worker_shutdown(**kwargs):
    from app.workers.context import ctx
    ctx.stop()
```

---

### Phase 2: Rewrite `tasks.py` to use WorkerContext

Every task changes from this pattern:

```python
# BEFORE
@celery_app.task
def some_task(job_id: str) -> dict:
    async def run() -> dict:
        factory = get_db_session_factory()  # NEW ENGINE every time
        async with factory() as db:
            ...
    return asyncio.run(run())  # NEW LOOP every time
```

To this pattern:

```python
# AFTER
@celery_app.task
def some_task(job_id: str) -> dict:
    from app.workers.context import ctx
    return ctx.run(_some_task(job_id))

async def _some_task(job_id: str) -> dict:
    async with ctx.session_factory() as db:
        ...
```

**Key rule:** Every async function (`_some_task`, `_stage_planning`, etc.)
receives its `db` session as a parameter or opens one from the shared factory.
No function ever creates its own engine.

### Phase 3: Shared Redis client

Replace all `get_redis()` and `redis.from_url()` calls with the shared
`ctx.redis`:

```python
# BEFORE
def broadcast_update(job_id: str, message: dict) -> None:
    r = get_redis()  # new TCP connection
    r.publish(...)

# AFTER
async def broadcast_update(job_id: str, message: dict) -> None:
    await ctx.redis.publish(f"job:{job_id}", json.dumps(message))
```

`ComfyUISemaphore` similarly switches from `redis.Redis` to `redis.asyncio.Redis`
and receives the shared client:

```python
class ComfyUISemaphore:
    def __init__(self, redis_client: aioredis.Redis, key: str, max_concurrent: int):
        self._redis = redis_client
        ...
```

### Phase 4: Remove dead code

After the refactor, these become unused and can be deleted:

| Function / Variable | Reason |
|---|---|
| `get_db_session_factory()` | Replaced by `ctx.session_factory` |
| `get_redis()` | Replaced by `ctx.redis` |
| `progress_callback_wrapper()` (sync) | Merged into async `broadcast_update` |
| `async_progress_callback()` | Simplified — `broadcast_update` is now async-native |
| `settings` module-level variable (line 27) | Can stay, used for non-DB config |

### Phase 5: Fix dead code paths

`process_video_job` has unreachable code after `return` statements inside the
provider-type branches (the `actual_cost` / `BudgetTracker` block at ~line 461).
This block needs to be moved **before** the returns or into a finally/cleanup.

The correct fix is to move cost recording into the `finally` block alongside
semaphore release and router shutdown.

---

## Task-by-Task Rewrite Map

| Task function | Async helper | Sessions needed | Redis usage |
|---|---|---|---|
| `process_video_job` | `_process_video_job` | 1 main + per-update | broadcast, semaphore |
| `send_heartbeat` | `_send_heartbeat` | 1 | none |
| `cleanup_stale_workers` | `_cleanup_stale_workers` | 1 | none |
| `reset_daily_budgets` | `_reset_daily_budgets` | 1 | none |
| `generate_preview` | `_generate_preview` | 0 (filesystem only) | none |
| `merge_videos` | `_merge_videos` | 0 (filesystem only) | none |
| `process_scene_video_job` | `_process_scene_video_job` | 1 main | broadcast |
| `generate_scene_media` | `_generate_scene_media` | 1 | broadcast |
| `export_scene_video` | `_export_scene_video` | 1 main | broadcast |

Shared helpers also need updating:

| Helper | Change |
|---|---|
| `update_job_status()` | Use `ctx.session_factory()` instead of `get_db_session_factory()` |
| `broadcast_update()` | Use `await ctx.redis.publish()` instead of sync `get_redis()` |
| `get_template_name()` | Take `db` parameter instead of creating its own session |
| `_resolve_provider_for_job()` | Already takes `db` — no change needed |
| `_run_local_job()` | No DB — no change needed |
| `_run_runpod_job()` | No DB — no change needed |
| `_run_poe_job()` | Already takes `db` — no change needed |
| `_stage_planning()` | Already takes `db` — update broadcast calls |
| `_stage_generating_images()` | Already takes `db` — update broadcast calls |
| `_stage_generating_videos()` | Already takes `db` — update broadcast calls |
| `_stage_rendering()` | Already takes `db` — update broadcast calls |

---

## File Changes Summary

| File | Action |
|---|---|
| `app/workers/context.py` | **NEW** — WorkerContext singleton |
| `app/workers/celery_app.py` | **MODIFY** — Add worker_init / worker_process_shutdown signals |
| `app/workers/tasks.py` | **MAJOR REWRITE** — All 9 tasks + all helpers |
| `app/workers/__init__.py` | **NO CHANGE** |

No changes to API layer, services, models, or frontend.

---

## Testing Strategy

### Unit Tests (no infrastructure needed)

1. **`test_context_lifecycle`** — verify `start()` creates loop/engine/redis,
   `stop()` disposes them.
2. **`test_broadcast_update_uses_shared_redis`** — mock `ctx.redis`, verify
   `publish` called with correct channel/payload.
3. **`test_semaphore_uses_shared_redis`** — mock async redis, verify
   acquire/release calls `incr`/`decr`.
4. **`test_update_job_status_scoped_session`** — verify it opens and closes
   a session from the shared factory.

### Integration Tests (need PostgreSQL + Redis)

5. **`test_heartbeat_registers_worker`** — run `send_heartbeat` via
   `ctx.run()`, verify worker row in DB.
6. **`test_process_video_job_end_to_end`** — mock ComfyUI, verify job goes
   from `pending` → `completed` with correct status broadcasts.

### Performance Verification

7. **Connection count test** — run 5 tasks sequentially, count PostgreSQL
   connections before/after. Should remain stable (not grow by 5×).

---

## Risk Assessment

| Risk | Mitigation |
|---|---|
| Thread safety of asyncpg across `run_coroutine_threadsafe` | asyncpg connections are not shared across threads — each `session_factory()` call creates its own session on the shared engine. SQLAlchemy's pool is thread-safe. |
| Event loop crashes taking down the worker | Wrap `ctx.run()` with try/except; if the loop is dead, fall back to `asyncio.run()` and log a critical error. |
| Tasks that outlive the event loop | `fut.result(timeout=...)` prevents indefinite hang; Celery's `time_limit` kills the process if needed. |
| Regressions in task behavior | The async helper functions (`_stage_planning`, etc.) remain **identical** — only the calling convention changes. |

---

## Rollout Plan

1. **Branch:** `refactor/celery-worker-context`
2. **Phase 1+2+3** as a single PR (they're tightly coupled)
3. **Phase 4+5** cleanup in same PR
4. Deploy to staging, monitor:
   - PostgreSQL connection count (`SELECT count(*) FROM pg_stat_activity`)
   - Redis connection count (`INFO clients`)
   - Task throughput / latency
5. Rollout to production

---

## Estimated Effort

| Phase | Time |
|---|---|
| Phase 1: WorkerContext + signals | 2 hours |
| Phase 2: Rewrite 9 task functions | 3 hours |
| Phase 3: Shared Redis + ComfyUISemaphore | 1 hour |
| Phase 4: Dead code removal | 30 min |
| Phase 5: Fix unreachable code | 30 min |
| Tests | 2 hours |
| **Total** | **~9 hours** |
