from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from httpx import AsyncClient

from app.database import Job, User


class TestScenesPathContainment:
    @pytest.mark.asyncio
    async def test_audio_metadata_rejects_traversal(
        self,
        client: AsyncClient,
        regular_user_token: str,
        db_session,
        regular_user: User,
        template,
        tmp_path,
    ):
        job = Job(
            id=uuid4(),
            user_id=regular_user.id,
            template_id=template.id,
            status="pending",
            input_data={"audio_file": "../../../etc/passwd"},
        )
        db_session.add(job)
        await db_session.commit()

        with patch("app.api.scenes.get_settings") as mock_settings:
            mock_settings.return_value.storage_path = str(tmp_path)
            response = await client.get(
                f"/api/jobs/{job.id}/audio-metadata",
                headers={"Authorization": f"Bearer {regular_user_token}"},
            )
            assert response.status_code == 400
            assert "traversal" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_extract_lyrics_rejects_traversal(
        self,
        client: AsyncClient,
        regular_user_token: str,
        db_session,
        regular_user: User,
        template,
        tmp_path,
    ):
        job = Job(
            id=uuid4(),
            user_id=regular_user.id,
            template_id=template.id,
            status="pending",
            input_data={},
        )
        db_session.add(job)
        await db_session.commit()

        with patch("app.api.scenes.get_settings") as mock_settings:
            mock_settings.return_value.storage_path = str(tmp_path)
            response = await client.post(
                f"/api/jobs/{job.id}/lyrics/extract",
                json={"audio_file_path": "../../../etc/passwd"},
                headers={"Authorization": f"Bearer {regular_user_token}"},
            )
            assert response.status_code == 400
            assert "traversal" in response.json()["detail"].lower()


class TestUploadsOwnership:
    @pytest.fixture
    async def other_user(self, db_session):
        from passlib.context import CryptContext

        pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
        user = User(
            id=uuid4(),
            email="other@example.com",
            hashed_password=pwd_context.hash("password123"),
            is_active=True,
            is_superuser=False,
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)
        return user

    @pytest.fixture
    def other_user_token(self, other_user):
        from app.api.auth import create_access_token

        return create_access_token(data={"sub": str(other_user.id)})

    @pytest.mark.asyncio
    async def test_download_other_user_file_forbidden(
        self,
        client: AsyncClient,
        regular_user_token: str,
        other_user: User,
    ):
        mock_storage = AsyncMock()
        mock_storage.download = AsyncMock(return_value=b"secret")

        with patch("app.api.uploads.get_storage_backend", return_value=mock_storage):
            response = await client.get(
                f"/api/uploads/download/uploads/audio/{other_user.id}/2024/01/01/test.mp3",
                headers={"Authorization": f"Bearer {regular_user_token}"},
            )
            assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_stream_other_user_file_forbidden(
        self,
        client: AsyncClient,
        regular_user_token: str,
        other_user: User,
    ):
        mock_storage = AsyncMock()
        mock_storage.download = AsyncMock(return_value=b"secret")

        with patch("app.api.uploads.get_storage_backend", return_value=mock_storage):
            response = await client.get(
                f"/api/uploads/stream/uploads/audio/{other_user.id}/2024/01/01/test.mp3",
                headers={"Authorization": f"Bearer {regular_user_token}"},
            )
            assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_thumbnail_anonymous_rejected(
        self,
        client: AsyncClient,
        regular_user: User,
    ):
        mock_storage = AsyncMock()
        mock_storage.download = AsyncMock(return_value=b"video")

        with patch("app.api.uploads.get_storage_backend", return_value=mock_storage):
            response = await client.get(
                f"/api/uploads/thumbnail/uploads/video/{regular_user.id}/2024/01/01/test.mp4",
            )
            assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_thumbnails_anonymous_rejected(
        self,
        client: AsyncClient,
        regular_user: User,
    ):
        mock_storage = AsyncMock()
        mock_storage.download = AsyncMock(return_value=b"video")

        with patch("app.api.uploads.get_storage_backend", return_value=mock_storage):
            response = await client.get(
                f"/api/uploads/thumbnails/uploads/video/{regular_user.id}/2024/01/01/test.mp4",
            )
            assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_download_own_file_allowed(
        self,
        client: AsyncClient,
        regular_user_token: str,
        regular_user: User,
    ):
        mock_storage = AsyncMock()
        mock_storage.download = AsyncMock(return_value=b"myfile")

        with patch("app.api.uploads.get_storage_backend", return_value=mock_storage):
            response = await client.get(
                f"/api/uploads/download/uploads/audio/{regular_user.id}/2024/01/01/test.mp3",
                headers={"Authorization": f"Bearer {regular_user_token}"},
            )
            assert response.status_code == 200
            assert response.content == b"myfile"

    @pytest.mark.asyncio
    async def test_stream_own_file_allowed(
        self,
        client: AsyncClient,
        regular_user_token: str,
        regular_user: User,
    ):
        mock_storage = AsyncMock()
        mock_storage.download = AsyncMock(return_value=b"myfile")

        with patch("app.api.uploads.get_storage_backend", return_value=mock_storage):
            response = await client.get(
                f"/api/uploads/stream/uploads/audio/{regular_user.id}/2024/01/01/test.mp3",
                headers={"Authorization": f"Bearer {regular_user_token}"},
            )
            assert response.status_code == 200
            assert response.content == b"myfile"
