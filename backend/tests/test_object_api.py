from io import BytesIO
from uuid import uuid4

import pytest
from httpx import AsyncClient
from PIL import Image

from app.database import ObjectRef


def _make_png_bytes(width: int = 64, height: int = 64) -> bytes:
    img = Image.new("RGB", (width, height), color="red")
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class TestObjectApiCamelCase:
    @pytest.fixture
    async def object_for_user(self, db_session, regular_user):
        obj = ObjectRef(
            id=uuid4(),
            name="Sports Car",
            description="Red Ferrari",
            user_id=regular_user.id,
            category="vehicle",
        )
        db_session.add(obj)
        await db_session.commit()
        await db_session.refresh(obj)
        return obj

    @pytest.fixture
    async def object_with_images(self, db_session, regular_user):
        from app.database import ObjectRefImage

        obj = ObjectRef(
            id=uuid4(),
            name="Blue Vase",
            description="Ceramic vase",
            user_id=regular_user.id,
            category="decor",
        )
        db_session.add(obj)
        await db_session.commit()
        await db_session.refresh(obj)

        img1 = ObjectRefImage(
            id=uuid4(),
            object_ref_id=obj.id,
            storage_path="/objects/vase/front.png",
            is_primary=True,
            sort_order=0,
            width=1024,
            height=768,
        )
        img2 = ObjectRefImage(
            id=uuid4(),
            object_ref_id=obj.id,
            storage_path="/objects/vase/side.png",
            is_primary=False,
            sort_order=1,
            width=512,
            height=512,
        )
        db_session.add_all([img1, img2])
        await db_session.commit()
        return obj

    @pytest.mark.asyncio
    async def test_create_object_returns_camel_case(self, client: AsyncClient, regular_user_token: str):
        payload = {
            "name": "Golden Lamp",
            "description": "An antique lamp",
            "category": "decor",
            "visualProperties": {"color": "gold", "material": "brass"},
        }
        response = await client.post(
            "/api/objects",
            json=payload,
            headers={"Authorization": f"Bearer {regular_user_token}"},
        )
        assert response.status_code == 201
        data = response.json()

        assert "id" in data
        assert data["name"] == "Golden Lamp"
        assert data["description"] == "An antique lamp"
        assert data["category"] == "decor"
        assert data["visualProperties"] == {"color": "gold", "material": "brass"}
        assert data["jobCount"] == 0
        assert "createdAt" in data
        assert "updatedAt" in data
        assert "images" in data
        assert data["images"] == []

    @pytest.mark.asyncio
    async def test_create_object_unauthenticated_returns_401(self, client: AsyncClient):
        response = await client.post(
            "/api/objects",
            json={"name": "Golden Lamp"},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_upload_image_marks_first_as_primary(self, client: AsyncClient, regular_user_token: str, object_for_user):
        png_bytes = _make_png_bytes(64, 64)
        response = await client.post(
            f"/api/objects/{object_for_user.id}/images",
            files={"file": ("test.png", png_bytes, "image/png")},
            headers={"Authorization": f"Bearer {regular_user_token}"},
        )
        assert response.status_code == 201
        data = response.json()

        assert "id" in data
        assert "storagePath" in data
        assert data["isPrimary"] is True
        assert data["sortOrder"] == 1
        assert data["width"] == 64
        assert data["height"] == 64

    @pytest.mark.asyncio
    async def test_upload_image_unauthenticated_returns_401(self, client: AsyncClient, object_for_user):
        png_bytes = _make_png_bytes(64, 64)
        response = await client.post(
            f"/api/objects/{object_for_user.id}/images",
            files={"file": ("test.png", png_bytes, "image/png")},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_list_objects_returns_camel_case(self, client: AsyncClient, regular_user_token: str, object_with_images):
        response = await client.get(
            "/api/objects",
            headers={"Authorization": f"Bearer {regular_user_token}"},
        )
        assert response.status_code == 200
        data = response.json()

        assert "objects" in data
        assert "total" in data
        assert data["total"] == 1

        obj = data["objects"][0]
        assert obj["name"] == "Blue Vase"
        assert obj["description"] == "Ceramic vase"
        assert obj["category"] == "decor"
        assert "visualProperties" in obj
        assert "jobCount" in obj
        assert "createdAt" in obj
        assert "updatedAt" in obj

        assert len(obj["images"]) == 2
        primary = [img for img in obj["images"] if img["isPrimary"]]
        assert len(primary) == 1
        assert primary[0]["storagePath"] == "/objects/vase/front.png"

        secondary = [img for img in obj["images"] if not img["isPrimary"]]
        assert len(secondary) == 1
        assert secondary[0]["storagePath"] == "/objects/vase/side.png"
        assert secondary[0]["sortOrder"] == 1
        assert secondary[0]["width"] == 512
        assert secondary[0]["height"] == 512

    @pytest.mark.asyncio
    async def test_get_object_returns_camel_case(self, client: AsyncClient, regular_user_token: str, object_with_images):
        response = await client.get(
            f"/api/objects/{object_with_images.id}",
            headers={"Authorization": f"Bearer {regular_user_token}"},
        )
        assert response.status_code == 200
        data = response.json()

        assert data["id"] == str(object_with_images.id)
        assert data["name"] == "Blue Vase"
        assert data["description"] == "Ceramic vase"
        assert data["category"] == "decor"
        assert "visualProperties" in data
        assert data["jobCount"] == 0
        assert "createdAt" in data
        assert "updatedAt" in data

        assert len(data["images"]) == 2
        primary = [img for img in data["images"] if img["isPrimary"]]
        assert len(primary) == 1
        assert primary[0]["storagePath"] == "/objects/vase/front.png"
        assert primary[0]["sortOrder"] == 0
        assert primary[0]["width"] == 1024
        assert primary[0]["height"] == 768
