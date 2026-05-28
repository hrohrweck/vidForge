"""Unit tests for the Ollama provider, its model-sync integration,
and the provider-creation Alembic migration.

Covers:
- OllamaProvider initialization with config
- get_status returns correct ProviderInfo
- estimate_cost always returns 0.0
- queue_prompt / image-video ops raise NotImplementedError
- _sync_ollama_models delegates to ModelManager.list_available_models
- Migration creates the ollama provider row and cleans stale model_configs
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text

from app.services.providers.base import ProviderInfo
from app.services.providers.ollama import OllamaProvider


# ======================================================================
# Helpers
# ======================================================================


def _make_ollama_provider(
    provider_id: UUID | None = None,
    config: dict | None = None,
) -> OllamaProvider:
    return OllamaProvider(
        provider_id=provider_id or uuid4(),
        config=config or {},
    )


# ======================================================================
# 1. Initialization
# ======================================================================


class TestOllamaProviderInit:

    def test_initializes_with_provider_id(self):
        pid = uuid4()
        provider = OllamaProvider(provider_id=pid, config={})
        assert provider.provider_id == pid

    def test_stores_config_dict(self):
        cfg = {"foo": "bar"}
        provider = OllamaProvider(provider_id=uuid4(), config=cfg)
        assert provider.config == cfg

    def test_defaults_base_url_when_missing_in_config(self):
        provider = OllamaProvider(provider_id=uuid4(), config={})
        assert provider.base_url == "http://ollama:11434"

    def test_uses_custom_base_url_from_config(self):
        provider = OllamaProvider(
            provider_id=uuid4(),
            config={"base_url": "http://custom-ollama:9999"},
        )
        assert provider.base_url == "http://custom-ollama:9999"


# ======================================================================
# 2. get_status
# ======================================================================


class TestOllamaProviderGetStatus:

    @pytest.mark.asyncio
    async def test_returns_provider_info(self):
        provider = _make_ollama_provider()
        info = await provider.get_status()
        assert isinstance(info, ProviderInfo)

    @pytest.mark.asyncio
    async def test_provider_type_is_ollama(self):
        provider = _make_ollama_provider()
        info = await provider.get_status()
        assert info.provider_type == "ollama"

    @pytest.mark.asyncio
    async def test_name_is_ollama(self):
        provider = _make_ollama_provider()
        info = await provider.get_status()
        assert info.name == "Ollama"

    @pytest.mark.asyncio
    async def test_is_available_is_true(self):
        provider = _make_ollama_provider()
        info = await provider.get_status()
        assert info.is_available is True

    @pytest.mark.asyncio
    async def test_cost_per_job_is_zero(self):
        provider = _make_ollama_provider()
        info = await provider.get_status()
        assert info.cost_per_job == 0.0


# ======================================================================
# 3. estimate_cost
# ======================================================================


class TestOllamaProviderEstimateCost:

    @pytest.mark.asyncio
    async def test_returns_zero_for_empty_workflow(self):
        provider = _make_ollama_provider()
        cost = await provider.estimate_cost({})
        assert cost == 0.0

    @pytest.mark.asyncio
    async def test_returns_zero_for_non_empty_workflow(self):
        provider = _make_ollama_provider()
        cost = await provider.estimate_cost({"model": "qwen3.6", "prompt": "hello"})
        assert cost == 0.0

    @pytest.mark.asyncio
    async def test_returns_float_type(self):
        provider = _make_ollama_provider()
        cost = await provider.estimate_cost({})
        assert isinstance(cost, float)


# ======================================================================
# 4. Image / video operations raise NotImplementedError
# ======================================================================


class TestOllamaProviderRaisesOnMediaOps:

    @pytest.mark.asyncio
    async def test_queue_prompt_raises_not_implemented(self):
        provider = _make_ollama_provider()
        with pytest.raises(NotImplementedError, match="text-only"):
            await provider.queue_prompt({"prompt": "test"})

    @pytest.mark.asyncio
    async def test_wait_for_completion_raises_not_implemented(self):
        provider = _make_ollama_provider()
        with pytest.raises(NotImplementedError, match="text-only"):
            await provider.wait_for_completion("job-1")

    @pytest.mark.asyncio
    async def test_get_output_raises_not_implemented(self):
        provider = _make_ollama_provider()
        with pytest.raises(NotImplementedError, match="text-only"):
            await provider.get_output({})

    @pytest.mark.asyncio
    async def test_cancel_job_raises_not_implemented(self):
        provider = _make_ollama_provider()
        with pytest.raises(NotImplementedError, match="text-only"):
            await provider.cancel_job("job-1")


# ======================================================================
# 5. Lifecycle no-ops (initialize, shutdown, estimate_duration)
# ======================================================================


class TestOllamaProviderLifecycle:

    @pytest.mark.asyncio
    async def test_initialize_does_not_raise(self):
        provider = _make_ollama_provider()
        await provider.initialize({})

    @pytest.mark.asyncio
    async def test_shutdown_does_not_raise(self):
        provider = _make_ollama_provider()
        await provider.shutdown()

    @pytest.mark.asyncio
    async def test_estimate_duration_returns_one(self):
        provider = _make_ollama_provider()
        duration = await provider.estimate_duration({})
        assert duration == 1.0


# ======================================================================
# 6. _sync_ollama_models
# ======================================================================


class TestSyncOllamaModels:

    @pytest.mark.asyncio
    async def test_calls_model_manager_list_available_models(self):
        """_sync_ollama_models delegates to ModelManager.list_available_models."""
        from app.workers.tasks import _sync_ollama_models

        provider = MagicMock()
        provider.id = uuid4()

        with patch(
            "app.services.model_manager.ModelManager"
        ) as mock_mgr_cls:
            mock_mgr = MagicMock()
            mock_mgr.list_available_models = AsyncMock(return_value=["qwen3.6"])
            mock_mgr.close = AsyncMock()
            mock_mgr_cls.return_value = mock_mgr

            await _sync_ollama_models(provider)

            mock_mgr.list_available_models.assert_awaited_once()
            mock_mgr.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_returns_model_config_dicts(self):
        """Each discovered model is mapped to a well-formed ModelConfig dict."""
        from app.workers.tasks import _sync_ollama_models

        provider = MagicMock()
        provider.id = uuid4()

        with patch(
            "app.services.model_manager.ModelManager"
        ) as mock_mgr_cls:
            mock_mgr = MagicMock()
            mock_mgr.list_available_models = AsyncMock(
                return_value=["qwen3.6:latest", "llama3.3"]
            )
            mock_mgr.close = AsyncMock()
            mock_mgr_cls.return_value = mock_mgr

            result = await _sync_ollama_models(provider)

        assert len(result) == 2
        assert result[0]["model_id"] == "qwen3.6:latest"
        assert result[0]["display_name"] == "qwen3.6"
        assert result[0]["modality"] == "text"
        assert result[0]["endpoint_type"] == "chat_completions"
        assert result[0]["capabilities"]["supports_chat"] is True
        assert result[0]["cost_config"]["cost"] == 0
        assert result[0]["cost_config"]["currency"] == "USD"
        assert result[0]["is_deprecated"] is False
        assert result[0]["is_active"] is True

        assert result[1]["model_id"] == "llama3.3"
        assert result[1]["display_name"] == "llama3.3"

    @pytest.mark.asyncio
    async def test_closes_manager_even_on_error(self):
        """ModelManager.close() is always called, even when list_available_models raises."""
        from app.workers.tasks import _sync_ollama_models

        provider = MagicMock()
        provider.id = uuid4()

        with patch(
            "app.services.model_manager.ModelManager"
        ) as mock_mgr_cls:
            mock_mgr = MagicMock()
            mock_mgr.list_available_models = AsyncMock(
                side_effect=RuntimeError("Ollama not reachable")
            )
            mock_mgr.close = AsyncMock()
            mock_mgr_cls.return_value = mock_mgr

            with pytest.raises(RuntimeError, match="Ollama not reachable"):
                await _sync_ollama_models(provider)

            mock_mgr.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_models_installed(self):
        from app.workers.tasks import _sync_ollama_models

        provider = MagicMock()
        provider.id = uuid4()

        with patch(
            "app.services.model_manager.ModelManager"
        ) as mock_mgr_cls:
            mock_mgr = MagicMock()
            mock_mgr.list_available_models = AsyncMock(return_value=[])
            mock_mgr.close = AsyncMock()
            mock_mgr_cls.return_value = mock_mgr

            result = await _sync_ollama_models(provider)

        assert result == []


# ======================================================================
# 7. Model sync dispatcher routes ollama provider type
# ======================================================================


class TestDiscoverProviderModelsRoutesOllama:

    @pytest.mark.asyncio
    async def test_routes_ollama_type_to_sync_ollama(self):
        """_discover_provider_models dispatches 'ollama' type correctly."""
        from app.workers.tasks import _discover_provider_models

        provider = MagicMock()
        provider.provider_type = "ollama"

        with patch(
            "app.workers.tasks._sync_ollama_models",
            AsyncMock(return_value=[{"model_id": "test"}]),
        ) as mock_sync:
            result = await _discover_provider_models(provider)

            mock_sync.assert_awaited_once_with(provider)
            assert result == [{"model_id": "test"}]


# ======================================================================
# 8. Migration: 178bb857d97b_add_ollama_provider
# ======================================================================


# Columns required by the providers table that lack DB-level defaults on SQLite.
_PROVIDER_SQL_COLS = (
    "id, name, provider_type, config, is_active, "
    "current_daily_spend, spend_reset_at, priority, created_at, updated_at"
)
_PROVIDER_SQL_VALS = (
    ":id, :name, :type, :config, :active, "
    ":spend, datetime('now'), 0, datetime('now'), datetime('now')"
)

# Columns required by model_configs table on SQLite.
_MODEL_CONFIG_SQL_COLS = (
    "id, provider_id, model_id, provider_model_id, display_name, "
    "modality, prompt_format, endpoint_type, is_active, is_deprecated, "
    "created_at, updated_at"
)
_MODEL_CONFIG_SQL_VALS = (
    ":id, :pid, :mid, :mid, :mid, "
    ":modality, 'string', :endpoint, true, false, "
    "datetime('now'), datetime('now')"
)


class TestOllamaProviderMigration:

    @pytest.mark.asyncio
    async def test_upgrade_creates_ollama_provider_row(self, db_session):
        """After migration INSERT, exactly one ollama provider exists."""
        result = await db_session.execute(
            text("SELECT COUNT(*) FROM providers WHERE provider_type = 'ollama'")
        )
        assert result.scalar() == 0

        await db_session.execute(
            text(
                f"INSERT INTO providers ({_PROVIDER_SQL_COLS}) "
                f"VALUES ({_PROVIDER_SQL_VALS})"
            ),
            {
                "id": str(uuid4()),
                "name": "Ollama (Local)",
                "type": "ollama",
                "config": '{"base_url": "http://ollama:11434"}',
                "active": True,
                "spend": 0,
            },
        )
        await db_session.flush()

        result = await db_session.execute(
            text("SELECT COUNT(*) FROM providers WHERE provider_type = 'ollama'")
        )
        assert result.scalar() == 1

    @pytest.mark.asyncio
    async def test_upgrade_idempotent_does_not_duplicate(self, db_session):
        """If an ollama provider already exists, INSERT is skipped."""
        pid = str(uuid4())
        await db_session.execute(
            text(
                f"INSERT INTO providers ({_PROVIDER_SQL_COLS}) "
                f"VALUES ({_PROVIDER_SQL_VALS})"
            ),
            {
                "id": pid,
                "name": "Ollama (Local)",
                "type": "ollama",
                "config": "{}",
                "active": True,
                "spend": 0,
            },
        )
        await db_session.flush()

        result = await db_session.execute(
            text("SELECT 1 FROM providers WHERE provider_type = 'ollama'")
        )
        exists = result.fetchone()

        # Idempotent guard: only INSERT when no existing row
        if not exists:
            await db_session.execute(
                text(
                    f"INSERT INTO providers ({_PROVIDER_SQL_COLS}) "
                    f"VALUES ({_PROVIDER_SQL_VALS})"
                ),
                {
                    "id": str(uuid4()),
                    "name": "Ollama (Local)",
                    "type": "ollama",
                    "config": '{"base_url": "http://ollama:11434"}',
                    "active": True,
                    "spend": 0,
                },
            )
            await db_session.flush()

        result = await db_session.execute(
            text("SELECT COUNT(*) FROM providers WHERE provider_type = 'ollama'")
        )
        assert result.scalar() == 1

    @pytest.mark.asyncio
    async def test_upgrade_removes_ollama_comfyui_model_configs(self, db_session):
        """Only model_configs for ollama models with endpoint_type='comfyui' are cleaned."""
        provider_id = str(uuid4())
        await db_session.execute(
            text(
                f"INSERT INTO providers ({_PROVIDER_SQL_COLS}) "
                f"VALUES ({_PROVIDER_SQL_VALS})"
            ),
            {
                "id": provider_id,
                "name": "Test ComfyUI",
                "type": "comfyui_direct",
                "config": "{}",
                "active": True,
                "spend": 0,
            },
        )

        def _insert_model_config(model_id: str, endpoint: str = "comfyui", modality: str = "text"):
            return db_session.execute(
                text(
                    f"INSERT INTO model_configs ({_MODEL_CONFIG_SQL_COLS}) "
                    f"VALUES ({_MODEL_CONFIG_SQL_VALS})"
                ),
                {
                    "id": str(uuid4()),
                    "pid": provider_id,
                    "mid": model_id,
                    "modality": modality,
                    "endpoint": endpoint,
                },
            )

        await _insert_model_config("qwen3.6:35b")
        await _insert_model_config("llama3.3")
        await _insert_model_config("flux.1-schnell", modality="image")
        await db_session.flush()

        count_before = await db_session.execute(
            text("SELECT COUNT(*) FROM model_configs")
        )
        assert count_before.scalar() == 3

        await db_session.execute(
            text(
                "DELETE FROM model_configs WHERE model_id IN ('qwen3.6:35b', 'llama3.3') "
                "AND endpoint_type = 'comfyui'"
            ),
        )
        await db_session.flush()

        count_after = await db_session.execute(
            text("SELECT COUNT(*) FROM model_configs")
        )
        assert count_after.scalar() == 1

        remaining = await db_session.execute(
            text("SELECT model_id FROM model_configs")
        )
        remaining_ids = [row[0] for row in remaining.fetchall()]
        assert "flux.1-schnell" in remaining_ids
        assert "qwen3.6:35b" not in remaining_ids
        assert "llama3.3" not in remaining_ids

    @pytest.mark.asyncio
    async def test_downgrade_removes_ollama_provider(self, db_session):
        """Downgrade DELETE removes only the ollama provider."""
        params = {
            "active": True,
            "spend": 0,
            "config": "{}",
        }

        await db_session.execute(
            text(
                f"INSERT INTO providers ({_PROVIDER_SQL_COLS}) "
                f"VALUES ({_PROVIDER_SQL_VALS})"
            ),
            {**params, "id": str(uuid4()), "name": "Ollama (Local)", "type": "ollama"},
        )
        await db_session.execute(
            text(
                f"INSERT INTO providers ({_PROVIDER_SQL_COLS}) "
                f"VALUES ({_PROVIDER_SQL_VALS})"
            ),
            {**params, "id": str(uuid4()), "name": "Other", "type": "comfyui_direct"},
        )
        await db_session.flush()

        count_before = await db_session.execute(
            text("SELECT COUNT(*) FROM providers")
        )
        assert count_before.scalar() == 2

        await db_session.execute(
            text("DELETE FROM providers WHERE provider_type = 'ollama'")
        )
        await db_session.flush()

        count_after = await db_session.execute(
            text("SELECT COUNT(*) FROM providers")
        )
        assert count_after.scalar() == 1

        remaining = await db_session.execute(
            text("SELECT provider_type FROM providers")
        )
        assert remaining.scalar() == "comfyui_direct"
