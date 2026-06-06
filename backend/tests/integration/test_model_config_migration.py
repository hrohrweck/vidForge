"""Integration tests for ModelConfig migration (unified Poe/AtlasCloud models).

Verifies:
- extra_config column exists on model_configs table
- PoeModel and AtlasCloudModel classes are removed
- poe_models / atlascloud_models tables are absent
- ModelConfig CRUD works with extra_config
- Data written through ModelConfig is persisted correctly
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import inspect, text

from app.database import ModelConfig, Provider


@pytest.fixture
async def test_provider(db_session):
    provider = Provider(
        id=uuid4(),
        name="migration-test-provider",
        provider_type="poe",
        config={"api_key": "test"},
    )
    db_session.add(provider)
    await db_session.flush()
    return provider


class TestModelConfigMigration:
    """Verify unified model_configs schema after migration."""

    async def test_extra_config_column_exists(self, db_session):
        """extra_config JSONB column is present on model_configs table."""
        inspector = inspect(db_session.get_bind())
        columns = {
            col["name"]: col
            for col in await db_session.run_sync(
                lambda sync_conn: inspector.get_columns("model_configs")
            )
        }
        assert "extra_config" in columns
        assert columns["extra_config"]["nullable"] is True

    async def test_poe_models_table_absent(self, db_session):
        """poe_models table is not present after migration."""
        inspector = inspect(db_session.get_bind())
        tables = await db_session.run_sync(
            lambda sync_conn: inspector.get_table_names()
        )
        assert "poe_models" not in tables

    async def test_atlascloud_models_table_absent(self, db_session):
        """atlascloud_models table is not present after migration."""
        inspector = inspect(db_session.get_bind())
        tables = await db_session.run_sync(
            lambda sync_conn: inspector.get_table_names()
        )
        assert "atlascloud_models" not in tables

    async def test_poemodel_class_removed(self):
        """PoeModel class is not importable from database."""
        from app import database

        assert not hasattr(database, "PoeModel")

    async def test_atlascloudmodel_class_removed(self):
        """AtlasCloudModel class is not importable from database."""
        from app import database

        assert not hasattr(database, "AtlasCloudModel")

    async def test_create_model_config_with_extra_config(self, db_session, test_provider):
        """ModelConfig can be created with extra_config JSON data."""
        model = ModelConfig(
            id=uuid4(),
            provider_id=test_provider.id,
            model_id="test-video-model",
            provider_model_id="poe-raw-id-123",
            display_name="Test Video Model",
            modality="video",
            endpoint_type="generateVideo",
            extra_config={
                "migrated_from": "poe_models",
                "original_id": str(uuid4()),
                "custom_field": "custom_value",
            },
        )
        db_session.add(model)
        await db_session.flush()

        refreshed = await db_session.get(ModelConfig, model.id)
        assert refreshed is not None
        assert refreshed.extra_config is not None
        assert refreshed.extra_config["migrated_from"] == "poe_models"
        assert refreshed.extra_config["custom_field"] == "custom_value"

    async def test_update_extra_config(self, db_session, test_provider):
        """extra_config can be updated independently."""
        model = ModelConfig(
            id=uuid4(),
            provider_id=test_provider.id,
            model_id="update-test-model",
            provider_model_id="atlas-raw-id",
            display_name="Update Test",
            modality="text",
            endpoint_type="chat_completions",
            extra_config={"source": "atlascloud_models"},
        )
        db_session.add(model)
        await db_session.flush()

        model.extra_config = {"source": "atlascloud_models", "updated": True}
        await db_session.flush()

        refreshed = await db_session.get(ModelConfig, model.id)
        assert refreshed.extra_config == {"source": "atlascloud_models", "updated": True}

    async def test_extra_config_nullable(self, db_session, test_provider):
        """extra_config can be None (omitted)."""
        model = ModelConfig(
            id=uuid4(),
            provider_id=test_provider.id,
            model_id="null-config-model",
            provider_model_id="null-raw-id",
            display_name="Null Config Test",
            modality="text",
            endpoint_type="chat_completions",
            extra_config=None,
        )
        db_session.add(model)
        await db_session.flush()

        refreshed = await db_session.get(ModelConfig, model.id)
        assert refreshed.extra_config is None

    async def test_extra_config_persists_across_other_field_updates(
        self, db_session, test_provider
    ):
        """extra_config survives updates to other ModelConfig fields."""
        model = ModelConfig(
            id=uuid4(),
            provider_id=test_provider.id,
            model_id="persist-test-model",
            provider_model_id="persist-raw",
            display_name="Persist Test",
            modality="image",
            endpoint_type="generateImage",
            extra_config={"original_owner": "legacy_system"},
        )
        db_session.add(model)
        await db_session.flush()

        model.display_name = "Updated Display Name"
        model.is_active = False
        await db_session.flush()

        refreshed = await db_session.get(ModelConfig, model.id)
        assert refreshed.display_name == "Updated Display Name"
        assert refreshed.is_active is False
        assert refreshed.extra_config["original_owner"] == "legacy_system"

    async def test_bulk_insert_with_extra_config(self, db_session, test_provider):
        """Multiple models can be inserted with different extra_config values."""
        models = []
        for i in range(5):
            models.append(
                ModelConfig(
                    id=uuid4(),
                    provider_id=test_provider.id,
                    model_id=f"bulk-model-{i}",
                    provider_model_id=f"bulk-raw-{i}",
                    display_name=f"Bulk Model {i}",
                    modality="text",
                    endpoint_type="chat_completions",
                    extra_config={"index": i, "source": "bulk_insert_test"},
                )
            )
        db_session.add_all(models)
        await db_session.flush()

        for i, model in enumerate(models):
            refreshed = await db_session.get(ModelConfig, model.id)
            assert refreshed.extra_config["index"] == i
            assert refreshed.extra_config["source"] == "bulk_insert_test"


class TestProviderRelationshipCleanup:
    """Verify Provider no longer references PoeModel/AtlasCloudModel."""

    async def test_provider_has_no_poe_models_attr(self, db_session, test_provider):
        """Provider does not expose a poe_models relationship."""
        assert not hasattr(test_provider, "poe_models")

    async def test_provider_has_no_atlascloud_models_attr(self, db_session, test_provider):
        """Provider does not expose an atlascloud_models relationship."""
        assert not hasattr(test_provider, "atlascloud_models")

    async def test_provider_model_configs_works(self, db_session, test_provider):
        """Provider model_configs relationship still works post-migration."""
        model = ModelConfig(
            id=uuid4(),
            provider_id=test_provider.id,
            model_id="rel-test-model",
            provider_model_id="rel-raw-id",
            display_name="Relationship Test",
            modality="text",
            endpoint_type="chat_completions",
        )
        db_session.add(model)
        await db_session.flush()

        # Refresh provider to load relationship
        await db_session.refresh(test_provider)
        configs = test_provider.model_configs
        assert len(configs) == 1
        assert configs[0].model_id == "rel-test-model"
