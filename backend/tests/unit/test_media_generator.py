from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from app.database import ErrorOrigin, ErrorSeverity, Job, ModelConfig, Provider
from app.services.media_generator import (
    _map_media_error_to_friendly_message,
    _resolve_image_provider,
    _resolve_video_provider,
    generate_image,
    generate_video,
    get_provider_instance,
    get_provider_for_job,
)
from app.services.providers.base import (
    ImageProvider,
    ProviderCapabilities,
    ProviderConnectionError,
    ProviderError,
    ProviderOverloadedError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    VideoProvider,
)


# ── Helpers ──────────────────────────────────────────────────────────────


def _provider_row(**overrides: Any) -> Provider:
    """Build a minimal Provider ORM row for tests."""
    defaults = {
        "id": uuid4(),
        "name": "test-provider",
        "provider_type": "comfyui_direct",
        "config": {"comfyui_url": "http://localhost:8188"},
        "is_active": True,
    }
    defaults.update(overrides)
    return Provider(**defaults)


def _model_config_row(provider: Provider, model_id: str = "wan2.2") -> ModelConfig:
    """Build a ModelConfig row that references the given provider."""
    return ModelConfig(
        id=1,
        model_id=model_id,
        display_name=model_id,
        provider_id=provider.id,
        provider=provider,
        is_active=True,
    )


def _mock_image_provider(
    image_data: bytes = b"png_data", asset_id: str = "img_001"
) -> MagicMock:
    instance = MagicMock(spec=ImageProvider)
    instance.generate_image = AsyncMock(return_value=(asset_id, image_data))
    instance.classify_error = MagicMock(return_value=ProviderError("mock error"))
    instance.get_capabilities.return_value = ProviderCapabilities(
        supports_image=True,
    )
    instance.provider_id = uuid4()
    return instance


def _mock_video_provider(
    video_data: bytes = b"mp4_data", asset_id: str = "vid_001"
) -> MagicMock:
    instance = MagicMock(spec=VideoProvider)
    instance.generate_video = AsyncMock(return_value=(asset_id, video_data))
    instance.classify_error = MagicMock(return_value=ProviderError("mock error"))
    instance.get_capabilities.return_value = ProviderCapabilities(
        supports_video=True,
    )
    instance.provider_id = uuid4()
    return instance


def _mock_job(**overrides: Any) -> Job:
    """Build a minimal Job for tests."""
    defaults = {
        "id": uuid4(),
        "user_id": uuid4(),
        "template_id": "test_template",
        "status": "pending",
        "input_data": {},
        "image_provider_id": None,
        "video_provider_id": None,
    }
    defaults.update(overrides)
    return Job(**defaults)


# ── Error Mapping Tests ──────────────────────────────────────────────────


class TestMapMediaError:
    def test_invalid_video_output_error(self):
        from app.services.video_processor import (
            InvalidVideoOutputError,
            ValidationResult,
        )

        result = ValidationResult(
            valid=False,
            actual_frames=10,
            expected_frames=30,
            actual_duration=2.0,
        )
        exc = InvalidVideoOutputError("/tmp/test.mp4", result)
        msg = _map_media_error_to_friendly_message(exc, "video")
        assert "10 frames" in msg
        assert "30" in msg

    def test_overloaded_error(self):
        exc = ProviderOverloadedError("Service overloaded")
        msg = _map_media_error_to_friendly_message(exc, "image")
        assert "busy" in msg

    def test_rate_limit_error(self):
        exc = ProviderRateLimitError("Rate limited")
        msg = _map_media_error_to_friendly_message(exc, "video")
        assert "Too many requests" in msg

    def test_connection_error(self):
        exc = ProviderConnectionError("Connection refused")
        msg = _map_media_error_to_friendly_message(exc, "image")
        assert "Connection failed" in msg

    def test_timeout_error(self):
        exc = ProviderTimeoutError("Timed out")
        msg = _map_media_error_to_friendly_message(exc, "video")
        assert "timed out" in msg

    def test_generic_provider_error(self):
        exc = ProviderError("Something went wrong")
        msg = _map_media_error_to_friendly_message(exc, "image")
        assert "service error" in msg

    def test_fallback_string_matching_overloaded(self):
        exc = RuntimeError("Engine overloaded")
        msg = _map_media_error_to_friendly_message(exc, "image")
        assert "busy" in msg

    def test_fallback_string_matching_no_data(self):
        exc = RuntimeError("generation returned no output data")
        msg = _map_media_error_to_friendly_message(exc, "video")
        assert "no data" in msg

    def test_generic_fallback(self):
        exc = RuntimeError("Unknown error")
        msg = _map_media_error_to_friendly_message(exc, "image")
        assert msg == "An error occurred, please try again"


# ── get_provider_instance Tests ──────────────────────────────────────────


class TestGetProviderInstance:
    @pytest.mark.asyncio
    async def test_delegates_to_registry(self, db_session):
        provider = _provider_row()
        mock_instance = MagicMock()
        with patch(
            "app.services.model_resolution.JobRouter.get_provider_instance",
            new_callable=AsyncMock,
            return_value=mock_instance,
        ) as mock_create:
            result = await get_provider_instance(db_session, provider)
            mock_create.assert_called_once_with(provider.id)
            assert result is mock_instance


# ── get_provider_for_job Tests ───────────────────────────────────────────


class TestGetProviderForJob:
    @pytest.mark.asyncio
    async def test_uses_explicit_provider_id(self, db_session):
        provider = _provider_row()
        job = _mock_job(image_provider_id=provider.id)
        mock_instance = MagicMock()
        mock_instance.get_capabilities.return_value = ProviderCapabilities(
            supports_image=True
        )

        with patch(
            "app.services.model_resolution.JobRouter.get_provider_instance",
            new_callable=AsyncMock,
            return_value=mock_instance,
        ):
            # Seed the provider into the DB
            db_session.add(provider)
            await db_session.commit()

            result_prov, result_inst = await get_provider_for_job(
                db_session, job, "image"
            )
            assert result_prov is not None
            assert result_inst is mock_instance

    @pytest.mark.asyncio
    async def test_fallback_uses_capability_lookup(self, db_session):
        provider = _provider_row(provider_type="comfyui_direct")
        job = _mock_job()  # No explicit provider_id

        mock_instance = MagicMock()
        mock_instance.get_capabilities.return_value = ProviderCapabilities(
            supports_image=True,
            supports_video=True,
        )

        # Seed provider + mock router iteration
        db_session.add(provider)
        await db_session.commit()

        with patch(
            "app.services.model_resolution.JobRouter.get_provider_instance",
            new_callable=AsyncMock,
            return_value=mock_instance,
        ):
            result_prov, result_inst = await get_provider_for_job(
                db_session, job, "image"
            )
            assert result_inst is not None

    @pytest.mark.asyncio
    async def test_fallback_skips_incapable_providers(self, db_session):
        """Providers that don't support the modality should be skipped."""
        provider = _provider_row(provider_type="ollama")
        job = _mock_job()

        mock_instance = MagicMock()
        mock_instance.get_capabilities.return_value = ProviderCapabilities(
            supports_llm=True,
            supports_image=False,
            supports_video=False,
        )

        db_session.add(provider)
        await db_session.commit()

        with patch(
            "app.services.model_resolution.JobRouter.get_provider_instance",
            new_callable=AsyncMock,
            return_value=mock_instance,
        ):
            result_prov, result_inst = await get_provider_for_job(
                db_session, job, "image"
            )
            # Should return None — no capable image provider found
            assert result_prov is None
            assert result_inst is None


# ── _resolve_image_provider Tests ───────────────────────────────────────


class TestResolveImageProvider:
    @pytest.mark.asyncio
    async def test_returns_instance_from_model_config(self, db_session):
        provider = _provider_row()
        model_config = _model_config_row(provider, model_id="flux1-schnell")
        job = _mock_job()

        mock_instance = _mock_image_provider()

        with (
            patch(
                "app.services.model_config_service.ModelConfigService.resolve_model_config",
                new_callable=AsyncMock,
                return_value=model_config,
            ),
            patch(
                "app.services.model_resolution.JobRouter.get_provider_instance",
                new_callable=AsyncMock,
                return_value=mock_instance,
            ),
        ):
            model_id, pid, instance = await _resolve_image_provider(
                db_session, job, None, "flux1-schnell", has_reference_image=False
            )
            assert model_id == "flux1-schnell"
            assert isinstance(instance, MagicMock)
            assert instance.generate_image is not None

    @pytest.mark.asyncio
    async def test_returns_three_tuple_not_four(self, db_session):
        """Verify the new return signature — (model_id, provider_id, instance)."""
        provider = _provider_row()
        model_config = _model_config_row(provider)
        job = _mock_job()

        mock_instance = _mock_image_provider()

        with (
            patch(
                "app.services.model_config_service.ModelConfigService.resolve_model_config",
                new_callable=AsyncMock,
                return_value=model_config,
            ),
            patch(
                "app.services.model_resolution.JobRouter.get_provider_instance",
                new_callable=AsyncMock,
                return_value=mock_instance,
            ),
        ):
            result = await _resolve_image_provider(
                db_session, job, None, "wan2.2"
            )
            # Must be a 3-tuple: model_id, provider_id, instance
            assert len(result) == 3
            model_id, pid, instance = result
            assert isinstance(model_id, str)
            assert pid is not None or isinstance(pid, UUID)
            assert instance is not None


# ── _resolve_video_provider Tests ───────────────────────────────────────


class TestResolveVideoProvider:
    @pytest.mark.asyncio
    async def test_returns_instance_from_model_config(self, db_session):
        provider = _provider_row()
        model_config = _model_config_row(provider, model_id="wan2.2")
        job = _mock_job()

        mock_instance = _mock_video_provider()

        with (
            patch(
                "app.services.model_config_service.ModelConfigService.resolve_model_config",
                new_callable=AsyncMock,
                return_value=model_config,
            ),
            patch(
                "app.services.model_resolution.JobRouter.get_provider_instance",
                new_callable=AsyncMock,
                return_value=mock_instance,
            ),
        ):
            model_id, pid, instance = await _resolve_video_provider(
                db_session, job, None, "wan2.2", has_seed_image=False
            )
            assert model_id == "wan2.2"
            assert instance is not None


# ── generate_image Tests ─────────────────────────────────────────────────


class TestGenerateImage:
    @pytest.mark.asyncio
    async def test_calls_instance_generate_image(self, db_session):
        provider = _provider_row()
        model_config = _model_config_row(provider, model_id="flux1-schnell")
        job = _mock_job()
        mock_instance = _mock_image_provider()

        with (
            patch(
                "app.services.model_config_service.ModelConfigService.resolve_model_config",
                new_callable=AsyncMock,
                return_value=model_config,
            ),
            patch(
                "app.services.model_resolution.JobRouter.get_provider_instance",
                new_callable=AsyncMock,
                return_value=mock_instance,
            ),
        ):
            rel_path, model_desc, pid = await generate_image(
                db=db_session,
                job=job,
                prompt="A cat",
                scene_number=1,
                aspect_ratio="16:9",
            )

            # Assert instance.generate_image was called
            mock_instance.generate_image.assert_called_once()
            call_kwargs = mock_instance.generate_image.call_args.kwargs
            assert call_kwargs["prompt"] == "A cat"
            assert call_kwargs["model"] == "flux1-schnell"
            assert call_kwargs["aspect_ratio"] == "16:9"

            # Assert output
            assert rel_path.endswith(".png")
            assert "generated_with_flux1-schnell" in model_desc

    @pytest.mark.asyncio
    async def test_raises_if_not_image_provider(self, db_session):
        provider = _provider_row()
        model_config = _model_config_row(provider)
        job = _mock_job()

        # Create a mock that does NOT implement ImageProvider
        mock_instance = _mock_video_provider()
        mock_instance.generate_image = None

        with (
            patch(
                "app.services.model_config_service.ModelConfigService.resolve_model_config",
                new_callable=AsyncMock,
                return_value=model_config,
            ),
            patch(
                "app.services.model_resolution.JobRouter.get_provider_instance",
                new_callable=AsyncMock,
                return_value=mock_instance,
            ),
        ):
            with pytest.raises(ValueError, match="does not support image generation"):
                await generate_image(
                    db=db_session,
                    job=job,
                    prompt="A cat",
                    scene_number=1,
                )

    @pytest.mark.asyncio
    async def test_classifies_error_on_failure(self, db_session):
        provider = _provider_row()
        model_config = _model_config_row(provider)
        job = _mock_job()
        mock_instance = _mock_image_provider()
        mock_instance.generate_image.side_effect = RuntimeError("Service overloaded")

        with (
            patch(
                "app.services.model_config_service.ModelConfigService.resolve_model_config",
                new_callable=AsyncMock,
                return_value=model_config,
            ),
            patch(
                "app.services.model_resolution.JobRouter.get_provider_instance",
                new_callable=AsyncMock,
                return_value=mock_instance,
            ),
        ):
            with pytest.raises(RuntimeError):
                await generate_image(
                    db=db_session,
                    job=job,
                    prompt="A cat",
                    scene_number=1,
                )
            # classify_error should have been called
            mock_instance.classify_error.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_provider_type_branching(self, db_session):
        provider = _provider_row(provider_type="atlascloud")
        model_config = _model_config_row(provider, model_id="custom-model")
        job = _mock_job()
        mock_instance = _mock_image_provider()

        with (
            patch(
                "app.services.model_config_service.ModelConfigService.resolve_model_config",
                new_callable=AsyncMock,
                return_value=model_config,
            ),
            patch(
                "app.services.model_resolution.JobRouter.get_provider_instance",
                new_callable=AsyncMock,
                return_value=mock_instance,
            ),
        ):
            rel_path, model_desc, pid = await generate_image(
                db=db_session,
                job=job,
                prompt="A cat",
                scene_number=1,
            )
            # Same code path regardless of provider_type
            mock_instance.generate_image.assert_called_once()
            assert "generated_with_custom-model" in model_desc


# ── generate_video Tests ─────────────────────────────────────────────────


class TestGenerateVideo:
    @pytest.mark.asyncio
    async def test_calls_instance_generate_video(self, db_session):
        provider = _provider_row()
        model_config = _model_config_row(provider, model_id="wan2.2")
        job = _mock_job()
        mock_instance = _mock_video_provider()

        with (
            patch(
                "app.services.model_config_service.ModelConfigService.resolve_model_config",
                new_callable=AsyncMock,
                return_value=model_config,
            ),
            patch(
                "app.services.model_resolution.JobRouter.get_provider_instance",
                new_callable=AsyncMock,
                return_value=mock_instance,
            ),
            patch(
                "app.services.media_generator.VideoProcessor.validate_video_output",
                new_callable=AsyncMock,
                return_value=MagicMock(valid=True),
            ),
        ):
            rel_path, model_desc, pid, dur, warning = await generate_video(
                db=db_session,
                job=job,
                prompt="A sunset",
                scene_number=1,
                duration=5,
                aspect_ratio="16:9",
            )

            # Assert instance.generate_video was called
            mock_instance.generate_video.assert_called_once()
            call_kwargs = mock_instance.generate_video.call_args.kwargs
            assert call_kwargs["prompt"] == "A sunset"
            assert call_kwargs["duration"] == 5
            assert call_kwargs["aspect_ratio"] == "16:9"

            # Assert output
            assert rel_path.endswith(".mp4")
            assert "generated_with_wan2.2" in model_desc
            assert dur == 5.0

    @pytest.mark.asyncio
    async def test_raises_if_not_video_provider(self, db_session):
        provider = _provider_row()
        model_config = _model_config_row(provider)
        job = _mock_job()

        mock_instance = _mock_image_provider()  # ImageProvider only
        mock_instance.generate_video = None

        with (
            patch(
                "app.services.model_config_service.ModelConfigService.resolve_model_config",
                new_callable=AsyncMock,
                return_value=model_config,
            ),
            patch(
                "app.services.model_resolution.JobRouter.get_provider_instance",
                new_callable=AsyncMock,
                return_value=mock_instance,
            ),
        ):
            with pytest.raises(ValueError, match="does not support video generation"):
                await generate_video(
                    db=db_session,
                    job=job,
                    prompt="A sunset",
                    scene_number=1,
                )

    @pytest.mark.asyncio
    async def test_classifies_error_on_failure(self, db_session):
        provider = _provider_row()
        model_config = _model_config_row(provider)
        job = _mock_job()
        mock_instance = _mock_video_provider()
        mock_instance.generate_video.side_effect = RuntimeError("Connection refused")

        with (
            patch(
                "app.services.model_config_service.ModelConfigService.resolve_model_config",
                new_callable=AsyncMock,
                return_value=model_config,
            ),
            patch(
                "app.services.model_resolution.JobRouter.get_provider_instance",
                new_callable=AsyncMock,
                return_value=mock_instance,
            ),
        ):
            with pytest.raises(RuntimeError):
                await generate_video(
                    db=db_session,
                    job=job,
                    prompt="A sunset",
                    scene_number=1,
                )
            mock_instance.classify_error.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_provider_type_branching(self, db_session):
        provider = _provider_row(provider_type="poe")
        model_config = _model_config_row(provider, model_id="veo-3")
        job = _mock_job()
        mock_instance = _mock_video_provider()

        with (
            patch(
                "app.services.model_config_service.ModelConfigService.resolve_model_config",
                new_callable=AsyncMock,
                return_value=model_config,
            ),
            patch(
                "app.services.model_resolution.JobRouter.get_provider_instance",
                new_callable=AsyncMock,
                return_value=mock_instance,
            ),
            patch(
                "app.services.media_generator.VideoProcessor.validate_video_output",
                new_callable=AsyncMock,
                return_value=MagicMock(valid=True),
            ),
        ):
            rel_path, model_desc, pid, dur, warning = await generate_video(
                db=db_session,
                job=job,
                prompt="A sunset",
                scene_number=1,
            )
            # Same code path regardless of provider_type
            mock_instance.generate_video.assert_called_once()
            assert "generated_with_veo-3" in model_desc

    @pytest.mark.asyncio
    async def test_returns_aspect_ratio_warning(self, db_session):
        provider = _provider_row()
        model_config = _model_config_row(provider, model_id="wan2.2")
        model_config.constraints = {"supported_aspect_ratios": ["16:9"]}
        model_config.display_name = "TestModel"
        job = _mock_job()
        mock_instance = _mock_video_provider()

        with (
            patch(
                "app.services.model_config_service.ModelConfigService.resolve_model_config",
                new_callable=AsyncMock,
                return_value=model_config,
            ),
            patch(
                "app.services.model_resolution.JobRouter.get_provider_instance",
                new_callable=AsyncMock,
                return_value=mock_instance,
            ),
            patch(
                "app.services.media_generator.VideoProcessor.validate_video_output",
                new_callable=AsyncMock,
                return_value=MagicMock(valid=True),
            ),
            patch(
                "app.services.media_generator.check_aspect_ratio_support",
                new_callable=AsyncMock,
                return_value=(False, "Model 'TestModel' only supports 16:9"),
            ),
            patch(
                "sqlalchemy.ext.asyncio.AsyncSession.execute",
                new_callable=AsyncMock,
            ) as mock_execute,
        ):
            mock_scalars = MagicMock()
            mock_scalars.first.return_value = model_config
            mock_result = MagicMock()
            mock_result.scalars.return_value = mock_scalars
            mock_execute.return_value = mock_result

            _rel_path, _desc, _pid, _dur, warning = await generate_video(
                db=db_session,
                job=job,
                prompt="A sunset",
                scene_number=1,
                aspect_ratio="1:1",
                model_preference="wan2.2",
            )
            assert warning is not None
            assert "only supports" in warning


# ── No provider-specific imports ────────────────────────────────────────


class TestNoProviderSpecificImports:
    def test_no_specific_provider_classes_in_top_level(self):
        """Verify generate_image / generate_video use no provider classes."""
        import inspect
        import ast
        from pathlib import Path

        src = Path(__file__).parent.parent.parent / "app" / "services" / "media_generator.py"
        tree = ast.parse(src.read_text())

        imports = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                imports.append(node)

        provider_imports = []
        for imp in imports:
            if isinstance(imp, ast.ImportFrom) and imp.module:
                module = imp.module
                for alias in imp.names:
                    if "Provider" in alias.name and alias.name not in (
                        "ImageProvider", "VideoProvider", "ProviderBase",
                        "ProviderConnectionError", "ProviderError",
                        "ProviderOverloadedError", "ProviderRateLimitError",
                        "ProviderTimeoutError", "Provider",
                    ):
                        provider_imports.append(
                            f"{module}.{alias.name}"
                        )

        assert not provider_imports, (
            f"Specific provider classes still imported: {provider_imports}"
        )
