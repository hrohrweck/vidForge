import io
import zipfile
from uuid import uuid4

import pytest
from httpx import AsyncClient

from app.database import User
from app.models.media import MediaAsset


class TestBulkDownload:
    @pytest.mark.asyncio
    async def test_empty_asset_ids_returns_validation_error(
        self, client: AsyncClient, regular_user_token: str
    ):
        response = await client.post(
            "/api/media/assets/bulk/download",
            json={"asset_ids": []},
            headers={"Authorization": f"Bearer {regular_user_token}"},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_nonexistent_assets_returns_404(
        self, client: AsyncClient, regular_user_token: str
    ):
        fake_id = str(uuid4())
        response = await client.post(
            "/api/media/assets/bulk/download",
            json={"asset_ids": [fake_id]},
            headers={"Authorization": f"Bearer {regular_user_token}"},
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_download_only_includes_user_assets(
        self,
        client: AsyncClient,
        regular_user_token: str,
        db_session,
        regular_user: User,
        superuser: User,
    ):
        asset = MediaAsset(
            id=uuid4(),
            user_id=superuser.id,
            name="other_user_asset.txt",
            file_path="/tmp/other_user.txt",
            file_type="markdown",
            source_type="uploaded",
        )
        db_session.add(asset)
        await db_session.commit()

        response = await client.post(
            "/api/media/assets/bulk/download",
            json={"asset_ids": [str(asset.id)]},
            headers={"Authorization": f"Bearer {regular_user_token}"},
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_successful_download_returns_zip(
        self,
        client: AsyncClient,
        regular_user_token: str,
        db_session,
        regular_user: User,
        tmp_path,
    ):
        test_content = b"Hello, World!"
        test_file = tmp_path / "test_asset.txt"
        test_file.write_bytes(test_content)

        asset = MediaAsset(
            id=uuid4(),
            user_id=regular_user.id,
            name="test_asset.txt",
            file_path=str(test_file),
            file_type="markdown",
            source_type="uploaded",
        )
        db_session.add(asset)
        await db_session.commit()

        response = await client.post(
            "/api/media/assets/bulk/download",
            json={"asset_ids": [str(asset.id)]},
            headers={"Authorization": f"Bearer {regular_user_token}"},
        )
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/zip"
        assert "attachment" in response.headers["content-disposition"]

        zip_data = io.BytesIO(response.content)
        with zipfile.ZipFile(zip_data, "r") as zf:
            names = zf.namelist()
            assert len(names) == 1
            assert names[0].startswith(asset.id.hex[:8])

    @pytest.mark.asyncio
    async def test_missing_file_skipped_gracefully(
        self,
        client: AsyncClient,
        regular_user_token: str,
        db_session,
        regular_user: User,
    ):
        asset = MediaAsset(
            id=uuid4(),
            user_id=regular_user.id,
            name="missing_file.txt",
            file_path="/nonexistent/path/file.txt",
            file_type="markdown",
            source_type="uploaded",
        )
        db_session.add(asset)
        await db_session.commit()

        response = await client.post(
            "/api/media/assets/bulk/download",
            json={"asset_ids": [str(asset.id)]},
            headers={"Authorization": f"Bearer {regular_user_token}"},
        )
        assert response.status_code == 200
        zip_data = io.BytesIO(response.content)
        with zipfile.ZipFile(zip_data, "r") as zf:
            assert len(zf.namelist()) == 0

    @pytest.mark.asyncio
    async def test_multiple_assets_in_zip(
        self,
        client: AsyncClient,
        regular_user_token: str,
        db_session,
        regular_user: User,
        tmp_path,
    ):
        files = []
        for i in range(3):
            f = tmp_path / f"asset_{i}.txt"
            f.write_bytes(f"Content {i}".encode())
            files.append((uuid4(), f"asset_{i}.txt", str(f)))

        for aid, name, path in files:
            asset = MediaAsset(
                id=aid,
                user_id=regular_user.id,
                name=name,
                file_path=path,
                file_type="markdown",
                source_type="uploaded",
            )
            db_session.add(asset)
        await db_session.commit()

        response = await client.post(
            "/api/media/assets/bulk/download",
            json={"asset_ids": [str(aid) for aid, _, _ in files]},
            headers={"Authorization": f"Bearer {regular_user_token}"},
        )
        assert response.status_code == 200
        zip_data = io.BytesIO(response.content)
        with zipfile.ZipFile(zip_data, "r") as zf:
            names = zf.namelist()
            assert len(names) == 3