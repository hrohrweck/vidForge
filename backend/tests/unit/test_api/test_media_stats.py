from uuid import uuid4

import pytest
from httpx import AsyncClient

from app.database import User
from app.models.media import MediaAsset


class TestMediaStats:
    @pytest.mark.asyncio
    async def test_empty_stats_returns_zeros(
        self,
        client: AsyncClient,
        regular_user_token: str,
    ):
        response = await client.get(
            "/api/media/stats",
            headers={"Authorization": f"Bearer {regular_user_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 0
        assert data["total_bytes"] == 0
        assert data["by_type"] == {}

    @pytest.mark.asyncio
    async def test_stats_aggregates_by_file_type(
        self,
        client: AsyncClient,
        regular_user_token: str,
        db_session,
        regular_user: User,
    ):
        assets = [
            MediaAsset(
                id=uuid4(),
                user_id=regular_user.id,
                name="image1.png",
                file_path="/tmp/image1.png",
                file_type="image",
                size_bytes=1000,
                source_type="uploaded",
            ),
            MediaAsset(
                id=uuid4(),
                user_id=regular_user.id,
                name="image2.png",
                file_path="/tmp/image2.png",
                file_type="image",
                size_bytes=2000,
                source_type="uploaded",
            ),
            MediaAsset(
                id=uuid4(),
                user_id=regular_user.id,
                name="video1.mp4",
                file_path="/tmp/video1.mp4",
                file_type="video",
                size_bytes=5000,
                source_type="generated",
            ),
        ]
        for asset in assets:
            db_session.add(asset)
        await db_session.commit()

        response = await client.get(
            "/api/media/stats",
            headers={"Authorization": f"Bearer {regular_user_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 3
        assert data["total_bytes"] == 8000
        assert "image" in data["by_type"]
        assert "video" in data["by_type"]
        assert data["by_type"]["image"]["count"] == 2
        assert data["by_type"]["image"]["bytes"] == 3000
        assert data["by_type"]["video"]["count"] == 1
        assert data["by_type"]["video"]["bytes"] == 5000

    @pytest.mark.asyncio
    async def test_stats_only_includes_current_user_assets(
        self,
        client: AsyncClient,
        regular_user_token: str,
        db_session,
        regular_user: User,
        superuser: User,
    ):
        my_asset = MediaAsset(
            id=uuid4(),
            user_id=regular_user.id,
            name="my_image.png",
            file_path="/tmp/my_image.png",
            file_type="image",
            size_bytes=1000,
            source_type="uploaded",
        )
        other_asset = MediaAsset(
            id=uuid4(),
            user_id=superuser.id,
            name="other_image.png",
            file_path="/tmp/other_image.png",
            file_type="image",
            size_bytes=2000,
            source_type="uploaded",
        )
        db_session.add(my_asset)
        db_session.add(other_asset)
        await db_session.commit()

        response = await client.get(
            "/api/media/stats",
            headers={"Authorization": f"Bearer {regular_user_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 1
        assert data["total_bytes"] == 1000

    @pytest.mark.asyncio
    async def test_stats_handles_null_size_bytes(
        self,
        client: AsyncClient,
        regular_user_token: str,
        db_session,
        regular_user: User,
    ):
        asset = MediaAsset(
            id=uuid4(),
            user_id=regular_user.id,
            name="unknown_size.png",
            file_path="/tmp/unknown_size.png",
            file_type="image",
            size_bytes=None,
            source_type="uploaded",
        )
        db_session.add(asset)
        await db_session.commit()

        response = await client.get(
            "/api/media/stats",
            headers={"Authorization": f"Bearer {regular_user_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 1
        assert data["total_bytes"] == 0
        assert data["by_type"]["image"]["bytes"] == 0

    @pytest.mark.asyncio
    async def test_stats_requires_auth(self, client: AsyncClient):
        response = await client.get("/api/media/stats")
        assert response.status_code == 401