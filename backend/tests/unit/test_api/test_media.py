from datetime import datetime, timezone
from uuid import uuid4

import pytest
from httpx import AsyncClient

from app.database import MediaEvent, User
from app.models.media import MediaAsset


class TestServeAssetFile:
    @pytest.mark.asyncio
    async def test_serve_asset_file_inline_disposition(
        self,
        client: AsyncClient,
        regular_user_token: str,
        db_session,
        regular_user: User,
        tmp_path,
    ):
        test_content = b"Hello, inline world!"
        test_file = tmp_path / "test_asset.png"
        test_file.write_bytes(test_content)

        asset = MediaAsset(
            id=uuid4(),
            user_id=regular_user.id,
            name="test_asset.png",
            file_path=str(test_file),
            file_type="image",
            mime_type="image/png",
            source_type="uploaded",
        )
        db_session.add(asset)
        await db_session.commit()

        response = await client.get(
            f"/api/media/assets/{asset.id}/file",
            headers={"Authorization": f"Bearer {regular_user_token}"},
        )
        assert response.status_code == 200
        assert "inline" in response.headers["content-disposition"]
        assert asset.name in response.headers["content-disposition"]

    @pytest.mark.asyncio
    async def test_serve_asset_file_download_disposition(
        self,
        client: AsyncClient,
        regular_user_token: str,
        db_session,
        regular_user: User,
        tmp_path,
    ):
        test_content = b"Hello, download world!"
        test_file = tmp_path / "download_asset.png"
        test_file.write_bytes(test_content)

        asset = MediaAsset(
            id=uuid4(),
            user_id=regular_user.id,
            name="download_asset.png",
            file_path=str(test_file),
            file_type="image",
            mime_type="image/png",
            source_type="uploaded",
        )
        db_session.add(asset)
        await db_session.commit()

        response = await client.get(
            f"/api/media/assets/{asset.id}/file?download=1",
            headers={"Authorization": f"Bearer {regular_user_token}"},
        )
        assert response.status_code == 200
        assert "attachment" in response.headers["content-disposition"]
        assert "download_asset.png" in response.headers["content-disposition"]

    @pytest.mark.asyncio
    async def test_serve_asset_file_not_found(
        self,
        client: AsyncClient,
        regular_user_token: str,
        db_session,
        regular_user: User,
    ):
        fake_id = str(uuid4())
        response = await client.get(
            f"/api/media/assets/{fake_id}/file",
            headers={"Authorization": f"Bearer {regular_user_token}"},
        )
        assert response.status_code == 404


class TestMediaEventsSince:
    @pytest.mark.asyncio
    async def test_events_since_returns_recent_events(
        self,
        client: AsyncClient,
        regular_user_token: str,
        db_session,
        regular_user: User,
    ):
        events = [
            MediaEvent(
                id=uuid4(),
                user_id=regular_user.id,
                event_type="asset_created",
                seq=1,
                created_at=datetime.now(timezone.utc),
            ),
            MediaEvent(
                id=uuid4(),
                user_id=regular_user.id,
                event_type="asset_updated",
                seq=2,
                created_at=datetime.now(timezone.utc),
            ),
        ]
        for event in events:
            db_session.add(event)
        await db_session.commit()

        response = await client.get(
            "/api/media/events/since?seq=0",
            headers={"Authorization": f"Bearer {regular_user_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["seq"] == 1
        assert data[1]["seq"] == 2

    @pytest.mark.asyncio
    async def test_events_since_filters_by_seq(
        self,
        client: AsyncClient,
        regular_user_token: str,
        db_session,
        regular_user: User,
    ):
        events = [
            MediaEvent(
                id=uuid4(),
                user_id=regular_user.id,
                event_type="asset_created",
                seq=1,
                created_at=datetime.now(timezone.utc),
            ),
            MediaEvent(
                id=uuid4(),
                user_id=regular_user.id,
                event_type="asset_updated",
                seq=2,
                created_at=datetime.now(timezone.utc),
            ),
            MediaEvent(
                id=uuid4(),
                user_id=regular_user.id,
                event_type="asset_deleted",
                seq=3,
                created_at=datetime.now(timezone.utc),
            ),
        ]
        for event in events:
            db_session.add(event)
        await db_session.commit()

        response = await client.get(
            "/api/media/events/since?seq=1",
            headers={"Authorization": f"Bearer {regular_user_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["seq"] == 2
        assert data[1]["seq"] == 3

    @pytest.mark.asyncio
    async def test_events_since_only_includes_current_user_events(
        self,
        client: AsyncClient,
        regular_user_token: str,
        db_session,
        regular_user: User,
        superuser: User,
    ):
        my_event = MediaEvent(
            id=uuid4(),
            user_id=regular_user.id,
            event_type="asset_created",
            seq=1,
            created_at=datetime.now(timezone.utc),
        )
        other_event = MediaEvent(
            id=uuid4(),
            user_id=superuser.id,
            event_type="asset_created",
            seq=2,
            created_at=datetime.now(timezone.utc),
        )
        db_session.add(my_event)
        db_session.add(other_event)
        await db_session.commit()

        response = await client.get(
            "/api/media/events/since?seq=0",
            headers={"Authorization": f"Bearer {regular_user_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["seq"] == 1

    @pytest.mark.asyncio
    async def test_events_since_respects_limit(
        self,
        client: AsyncClient,
        regular_user_token: str,
        db_session,
        regular_user: User,
    ):
        for i in range(5):
            event = MediaEvent(
                id=uuid4(),
                user_id=regular_user.id,
                event_type="asset_created",
                seq=i + 1,
                created_at=datetime.now(timezone.utc),
            )
            db_session.add(event)
        await db_session.commit()

        response = await client.get(
            "/api/media/events/since?seq=0&limit=3",
            headers={"Authorization": f"Bearer {regular_user_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 3
