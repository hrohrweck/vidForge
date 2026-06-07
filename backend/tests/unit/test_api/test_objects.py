from datetime import datetime
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.database import Job, ObjectRef, ObjectRefImage


class TestObjectsAPI:
    """CRUD API tests for object library endpoints."""

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

    @pytest.fixture
    async def object_for_superuser(self, db_session, superuser):
        obj = ObjectRef(
            id=uuid4(),
            name="Superuser Object",
            user_id=superuser.id,
        )
        db_session.add(obj)
        await db_session.commit()
        await db_session.refresh(obj)
        return obj

    @pytest.mark.asyncio
    async def test_list_objects_returns_user_objects(
        self,
        client: AsyncClient,
        regular_user_token: str,
        object_for_user,
        object_for_superuser,
    ):
        response = await client.get(
            "/api/objects",
            headers={"Authorization": f"Bearer {regular_user_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "objects" in data
        assert "total" in data
        assert data["total"] == 1
        obj_ids = [o["id"] for o in data["objects"]]
        assert str(object_for_user.id) in obj_ids
        assert str(object_for_superuser.id) not in obj_ids

    @pytest.mark.asyncio
    async def test_list_objects_includes_images(
        self,
        client: AsyncClient,
        regular_user_token: str,
        object_with_images,
    ):
        response = await client.get(
            "/api/objects",
            headers={"Authorization": f"Bearer {regular_user_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        obj = data["objects"][0]
        assert obj["name"] == "Blue Vase"
        assert len(obj["images"]) == 2
        primary = [img for img in obj["images"] if img["is_primary"]]
        assert len(primary) == 1
        assert primary[0]["storage_path"] == "/objects/vase/front.png"

    @pytest.mark.asyncio
    async def test_list_objects_excludes_deleted(
        self,
        client: AsyncClient,
        regular_user_token: str,
        object_for_user,
        db_session,
    ):
        object_for_user.deleted_at = datetime.utcnow()
        await db_session.commit()

        response = await client.get(
            "/api/objects",
            headers={"Authorization": f"Bearer {regular_user_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["objects"] == []

    @pytest.mark.asyncio
    async def test_list_objects_unauthenticated_returns_401(self, client: AsyncClient):
        response = await client.get("/api/objects")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_get_object_returns_single_object_with_images(
        self,
        client: AsyncClient,
        regular_user_token: str,
        object_with_images,
    ):
        response = await client.get(
            f"/api/objects/{object_with_images.id}",
            headers={"Authorization": f"Bearer {regular_user_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(object_with_images.id)
        assert data["name"] == "Blue Vase"
        assert len(data["images"]) == 2
        assert data["job_count"] == 0

    @pytest.mark.asyncio
    async def test_get_object_not_found_returns_404(
        self,
        client: AsyncClient,
        regular_user_token: str,
    ):
        response = await client.get(
            f"/api/objects/{uuid4()}",
            headers={"Authorization": f"Bearer {regular_user_token}"},
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_object_other_users_object_returns_404(
        self,
        client: AsyncClient,
        regular_user_token: str,
        object_for_superuser,
    ):
        response = await client.get(
            f"/api/objects/{object_for_superuser.id}",
            headers={"Authorization": f"Bearer {regular_user_token}"},
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_object_deleted_returns_404(
        self,
        client: AsyncClient,
        regular_user_token: str,
        object_for_user,
        db_session,
    ):
        object_for_user.deleted_at = datetime.utcnow()
        await db_session.commit()

        response = await client.get(
            f"/api/objects/{object_for_user.id}",
            headers={"Authorization": f"Bearer {regular_user_token}"},
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_object_unauthenticated_returns_401(self, client: AsyncClient, object_for_user):
        response = await client.get(f"/api/objects/{object_for_user.id}")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_delete_object_soft_deletes(
        self,
        client: AsyncClient,
        regular_user_token: str,
        object_for_user,
        db_session,
    ):
        response = await client.delete(
            f"/api/objects/{object_for_user.id}",
            headers={"Authorization": f"Bearer {regular_user_token}"},
        )
        assert response.status_code == 204

        # Verify soft delete in DB
        await db_session.refresh(object_for_user)
        assert object_for_user.deleted_at is not None

    @pytest.mark.asyncio
    async def test_deleted_object_not_in_list(
        self,
        client: AsyncClient,
        regular_user_token: str,
        object_for_user,
        db_session,
    ):
        await client.delete(
            f"/api/objects/{object_for_user.id}",
            headers={"Authorization": f"Bearer {regular_user_token}"},
        )

        # Verify it no longer appears in list
        response = await client.get(
            "/api/objects",
            headers={"Authorization": f"Bearer {regular_user_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["objects"] == []

    @pytest.mark.asyncio
    async def test_delete_other_users_object_returns_404(
        self,
        client: AsyncClient,
        regular_user_token: str,
        object_for_superuser,
    ):
        response = await client.delete(
            f"/api/objects/{object_for_superuser.id}",
            headers={"Authorization": f"Bearer {regular_user_token}"},
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_object_unauthenticated_returns_401(self, client: AsyncClient, object_for_user):
        response = await client.delete(f"/api/objects/{object_for_user.id}")
        assert response.status_code == 401


class TestJobObjectsEndpoint:
    """Tests for GET /api/jobs/{job_id}/objects endpoint."""

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
        db_session.add(img1)
        await db_session.commit()
        return obj

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
    async def job_with_objects(
        self, db_session, job_for_user, object_with_images, object_for_user
    ):
        from app.database import JobObjectRef

        ja1 = JobObjectRef(
            job_id=job_for_user.id,
            object_ref_id=object_with_images.id,
            role="main",
            importance_score=0.95,
        )
        ja2 = JobObjectRef(
            job_id=job_for_user.id,
            object_ref_id=object_for_user.id,
            role="background",
            importance_score=0.3,
        )
        db_session.add_all([ja1, ja2])
        await db_session.commit()
        return job_for_user

    @pytest.mark.asyncio
    async def test_get_job_objects_returns_assigned_objects(
        self,
        client: AsyncClient,
        regular_user_token: str,
        job_with_objects,
    ):
        response = await client.get(
            f"/api/jobs/{job_with_objects.id}/objects",
            headers={"Authorization": f"Bearer {regular_user_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 2

        objects_by_name = {o["object_name"]: o for o in data}
        assert "Blue Vase" in objects_by_name
        assert "Sports Car" in objects_by_name

        vase = objects_by_name["Blue Vase"]
        assert vase["role"] == "main"
        assert vase["importance_score"] == 0.95
        assert vase["category"] == "decor"
        assert vase["primary_image_path"] == "/objects/vase/front.png"

        car = objects_by_name["Sports Car"]
        assert car["role"] == "background"
        assert car["importance_score"] == 0.3

    @pytest.mark.asyncio
    async def test_get_job_objects_empty_when_no_objects_assigned(
        self,
        client: AsyncClient,
        regular_user_token: str,
        job_for_user,
    ):
        response = await client.get(
            f"/api/jobs/{job_for_user.id}/objects",
            headers={"Authorization": f"Bearer {regular_user_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 0

    @pytest.mark.asyncio
    async def test_get_job_objects_excludes_deleted_objects(
        self,
        client: AsyncClient,
        regular_user_token: str,
        job_with_objects,
        object_with_images,
        db_session,
    ):
        # Soft-delete one of the assigned objects
        object_with_images.deleted_at = datetime.utcnow()
        await db_session.commit()

        response = await client.get(
            f"/api/jobs/{job_with_objects.id}/objects",
            headers={"Authorization": f"Bearer {regular_user_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        # Only the non-deleted object should appear
        assert len(data) == 1
        assert data[0]["object_name"] == "Sports Car"

    @pytest.mark.asyncio
    async def test_get_job_objects_other_users_job_returns_empty(
        self,
        client: AsyncClient,
        regular_user_token: str,
        db_session,
        superuser,
        template,
    ):
        # Create a job owned by superuser
        other_job = Job(
            id=uuid4(),
            user_id=superuser.id,
            template_id=template.id,
            status="pending",
            input_data={"prompt": "test"},
        )
        db_session.add(other_job)
        await db_session.commit()

        response = await client.get(
            f"/api/jobs/{other_job.id}/objects",
            headers={"Authorization": f"Bearer {regular_user_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 0

    @pytest.mark.asyncio
    async def test_get_job_objects_unauthenticated_returns_401(
        self, client: AsyncClient, job_for_user
    ):
        response = await client.get(f"/api/jobs/{job_for_user.id}/objects")
        assert response.status_code == 401
