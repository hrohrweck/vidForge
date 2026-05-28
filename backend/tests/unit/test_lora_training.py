"""Unit tests for LoRA registry and avatar training orchestration.

Tests cover the lora_registry module (CRUD operations) and the
_train_avatar_lora task's orchestration logic without requiring
an actual ComfyUI / GPU environment.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ═══════════════════════════════════════════════════════════════════
# Registry tests
# ═══════════════════════════════════════════════════════════════════


class TestLoraRegistry:
    """Tests for app.services.lora_registry — pure in-memory dict operations."""

    @pytest.fixture(autouse=True)
    def _clear_registry(self):
        """Reset the module-level registry dict between tests."""
        from app.services import lora_registry

        lora_registry._registry.clear()

    # ── register ─────────────────────────────────────────────────-

    def test_lora_registry_register(self):
        """register_lora stores an entry keyed by avatar_id."""
        from app.services.lora_registry import _registry, register_lora

        register_lora("ava-1", "/path/to/lora.safetensors")

        assert "ava-1" in _registry
        assert _registry["ava-1"]["path"] == "/path/to/lora.safetensors"
        assert _registry["ava-1"]["base_model"] == "flux1-schnell"

    def test_lora_registry_register_custom_base(self):
        """register_lora accepts a custom base_model."""
        from app.services.lora_registry import _registry, register_lora

        register_lora("ava-2", "/lora/thing.safetensors", base_model="sdxl")

        assert _registry["ava-2"]["base_model"] == "sdxl"

    # ── get ──────────────────────────────────────────────────────

    def test_lora_registry_get(self):
        """get_lora returns the stored dict for a registered avatar."""
        from app.services.lora_registry import get_lora, register_lora

        register_lora("ava-3", "/loras/ava3.safetensors", base_model="wan")

        info = get_lora("ava-3")
        assert info is not None
        assert info["path"] == "/loras/ava3.safetensors"
        assert info["base_model"] == "wan"

    def test_lora_registry_missing(self):
        """get_lora returns None for an unknown avatar_id."""
        from app.services.lora_registry import get_lora

        assert get_lora("non-existent") is None

    # ── unregister ───────────────────────────────────────────────

    def test_lora_registry_unregister(self):
        """unregister removes an entry from the registry."""
        from app.services.lora_registry import _registry, register_lora, unregister_lora

        register_lora("ava-4", "/loras/ava4.safetensors")
        unregister_lora("ava-4")

        assert "ava-4" not in _registry

    def test_lora_registry_unregister_missing_noop(self):
        """unregister on a missing key does not raise."""
        from app.services.lora_registry import unregister_lora

        # Should not raise
        unregister_lora("never-registered")

    # ── has_lora ─────────────────────────────────────────────────

    def test_lora_registry_has_lora_true(self):
        """has_lora returns True for a registered avatar."""
        from app.services.lora_registry import has_lora, register_lora

        register_lora("ava-5", "/path.safetensors")
        assert has_lora("ava-5") is True

    def test_lora_registry_has_lora_false(self):
        """has_lora returns False for an unknown avatar."""
        from app.services.lora_registry import has_lora

        assert has_lora("no-such-avatar") is False

    # ── overwrite ────────────────────────────────────────────────

    def test_lora_registry_overwrite(self):
        """register_lora overwrites an existing entry for the same avatar_id."""
        from app.services.lora_registry import register_lora, get_lora

        register_lora("ava-6", "/old.safetensors")
        register_lora("ava-6", "/new.safetensors", base_model="sdxl")

        info = get_lora("ava-6")
        assert info["path"] == "/new.safetensors"
        assert info["base_model"] == "sdxl"


# ═══════════════════════════════════════════════════════════════════
# Training task tests
# ═══════════════════════════════════════════════════════════════════


def _build_mock_ctx():
    """Return a ctx MagicMock wired to an AsyncMock session."""
    mock_session = AsyncMock()
    ctx_manager = MagicMock()
    ctx_manager.__aenter__ = AsyncMock(return_value=mock_session)
    ctx_manager.__aexit__ = AsyncMock(return_value=None)
    factory = MagicMock(return_value=ctx_manager)

    ctx_mock = MagicMock()
    ctx_mock.session_factory = factory
    return ctx_mock, mock_session


def _build_mock_avatar():
    """Return (plain_avatar, eager_avatar, images).

    plain_avatar — returned by ``db.get()``
    eager_avatar — returned by the selectinload query
    images       — list of 3 MagicMocks with ``storage_path`` set
    """
    avatar = MagicMock()
    avatar.id = "11111111-1111-1111-1111-111111111111"
    avatar.name = "Test Avatar"
    avatar.gender = "Female"
    avatar.bio = "A test bio"
    avatar.lora_training_status = "not_trained"
    avatar.lora_model_path = None

    images = []
    for idx in range(3):
        img = MagicMock()
        img.storage_path = f"images/img{idx}.png"
        images.append(img)

    eager = MagicMock()
    eager.images = images
    return avatar, eager, images


def _run_training_patches(ctx_mock, session_mock, tmp_path, patches):
    """Apply shared patches and return the patch-manager stack.

    ``patches`` is a list of extra ``(target, kwargs)`` tuples.
    """
    from unittest.mock import patch as _patch

    base = [
        _patch("app.workers.tasks.ctx", ctx_mock),
        _patch("app.workers.tasks.settings"),
        _patch("asyncio.sleep", new_callable=AsyncMock),
        _patch("shutil.copy2"),
    ]
    for target, kwargs in patches:
        base.append(_patch(target, **kwargs))

    entered = []
    for p in base:
        entered.append(p.__enter__())

    # Wire up settings.storage_path
    from app.workers import tasks as tmod

    tmod.settings.storage_path = str(tmp_path)

    return entered


def _stop_patches(entered):
    from unittest.mock import _patch

    for p in reversed(entered):
        if isinstance(p, _patch):
            p.__exit__(None, None, None)


class TestLoraTrainingTask:

    @pytest.fixture
    def tmp_storage(self):
        with tempfile.TemporaryDirectory() as tmp:
            yield Path(tmp)

    # ── helpers ──────────────────────────────────────────────────

    @staticmethod
    def _setup_execute(session_mock, eager_avatar):
        result_mock = MagicMock()
        result_mock.scalar_one.return_value = eager_avatar
        session_mock.execute = AsyncMock(return_value=result_mock)

    # ── tests ───────────────────────────────────────────────────

    def test_training_creates_directory(self, tmp_storage):
        ctx_mock, session_mock = _build_mock_ctx()
        avatar, eager, _ = _build_mock_avatar()
        session_mock.get.return_value = avatar
        self._setup_execute(session_mock, eager)

        patches = _run_training_patches(ctx_mock, session_mock, tmp_storage, [])

        try:
            import asyncio
            from app.workers.tasks import _train_avatar_lora

            asyncio.run(_train_avatar_lora(str(avatar.id)))
        finally:
            _stop_patches(patches)

        expected_dir = tmp_storage / "loras" / str(avatar.id)
        assert expected_dir.exists()
        assert expected_dir.is_dir()

    def test_training_sets_status_trained(self, tmp_storage):
        ctx_mock, session_mock = _build_mock_ctx()
        avatar, eager, _ = _build_mock_avatar()
        session_mock.get.return_value = avatar
        self._setup_execute(session_mock, eager)

        patches = _run_training_patches(ctx_mock, session_mock, tmp_storage, [])

        try:
            import asyncio
            from app.workers.tasks import _train_avatar_lora

            asyncio.run(_train_avatar_lora(str(avatar.id)))
        finally:
            _stop_patches(patches)

        assert avatar.lora_training_status == "trained"
        assert avatar.lora_model_path is not None
        assert "avatar_lora.safetensors" in str(avatar.lora_model_path)

    def test_training_sets_status_failed_on_error(self, tmp_storage):
        ctx_mock, session_mock = _build_mock_ctx()
        avatar, _, _ = _build_mock_avatar()
        session_mock.get.return_value = avatar
        session_mock.execute = AsyncMock(side_effect=RuntimeError("DB error"))

        patches = _run_training_patches(ctx_mock, session_mock, tmp_storage, [])

        try:
            import asyncio
            from app.workers.tasks import _train_avatar_lora

            with pytest.raises(RuntimeError, match="DB error"):
                asyncio.run(_train_avatar_lora(str(avatar.id)))
        finally:
            _stop_patches(patches)

        assert avatar.lora_training_status == "failed"

    def test_insufficient_images_raises_value_error(self, tmp_storage):
        ctx_mock, session_mock = _build_mock_ctx()
        avatar, _, _ = _build_mock_avatar()
        session_mock.get.return_value = avatar

        img1 = MagicMock(storage_path="a.png")
        img2 = MagicMock(storage_path="b.png")
        eager_few = MagicMock()
        eager_few.images = [img1, img2]
        self._setup_execute(session_mock, eager_few)

        patches = _run_training_patches(ctx_mock, session_mock, tmp_storage, [])

        try:
            import asyncio
            from app.workers.tasks import _train_avatar_lora

            with pytest.raises(ValueError, match="Need at least 3 images"):
                asyncio.run(_train_avatar_lora(str(avatar.id)))
        finally:
            _stop_patches(patches)

        assert avatar.lora_training_status == "failed"

    def test_avatar_not_found_returns_failed(self, tmp_storage):
        ctx_mock, session_mock = _build_mock_ctx()
        session_mock.get.return_value = None

        patches = _run_training_patches(ctx_mock, session_mock, tmp_storage, [])

        try:
            import asyncio
            from app.workers.tasks import _train_avatar_lora

            result = asyncio.run(_train_avatar_lora("00000000-0000-0000-0000-000000000000"))
        finally:
            _stop_patches(patches)

        assert result["status"] == "failed"
        assert "Avatar not found" in result["error"]

    def test_celery_task_shim_delegates(self):
        with patch("app.workers.tasks.ctx") as mock_ctx:
            mock_ctx.run.return_value = {"status": "completed"}
            from app.workers.tasks import train_avatar_lora

            result = train_avatar_lora("00000000-0000-0000-0000-000000000000")

            mock_ctx.run.assert_called_once()
            assert result["status"] == "completed"
