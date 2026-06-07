from datetime import datetime
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import Job, JobObjectRef, ObjectRef, ObjectRefImage


class TestObjectRefModel:

    @pytest.mark.asyncio
    async def test_create_object_ref(self, db_session: AsyncSession, regular_user):
        obj = ObjectRef(
            name="Sports Car",
            description="Red Ferrari",
            user_id=regular_user.id,
            category="vehicle",
        )
        db_session.add(obj)
        await db_session.commit()
        await db_session.refresh(obj)

        assert obj.id is not None
        assert obj.name == "Sports Car"
        assert obj.description == "Red Ferrari"
        assert obj.user_id == regular_user.id
        assert obj.category == "vehicle"

    @pytest.mark.asyncio
    async def test_object_ref_visual_properties(self, db_session: AsyncSession, regular_user):
        obj = ObjectRef(
            name="Blue Vase",
            user_id=regular_user.id,
            visual_properties={"color": "blue", "material": "ceramic", "height_cm": 30},
        )
        db_session.add(obj)
        await db_session.commit()
        await db_session.refresh(obj)

        assert obj.visual_properties is not None
        assert obj.visual_properties["color"] == "blue"
        assert obj.visual_properties["material"] == "ceramic"

    @pytest.mark.asyncio
    async def test_object_ref_nullable_fields(self, db_session: AsyncSession, regular_user):
        obj = ObjectRef(
            name="Minimal Object",
            user_id=regular_user.id,
        )
        db_session.add(obj)
        await db_session.commit()
        await db_session.refresh(obj)

        assert obj.description is None
        assert obj.visual_properties is None
        assert obj.category is None
        assert obj.deleted_at is None

    @pytest.mark.asyncio
    async def test_object_ref_soft_delete(self, db_session: AsyncSession, regular_user):
        obj = ObjectRef(name="To Delete", user_id=regular_user.id)
        db_session.add(obj)
        await db_session.commit()

        obj.deleted_at = datetime.utcnow()
        await db_session.commit()
        await db_session.refresh(obj)

        assert obj.deleted_at is not None
        assert isinstance(obj.deleted_at, datetime)

    @pytest.mark.asyncio
    async def test_object_ref_belongs_to_user(self, db_session: AsyncSession, regular_user):
        obj = ObjectRef(name="User's Object", user_id=regular_user.id)
        db_session.add(obj)
        await db_session.commit()
        await db_session.refresh(obj)

        assert obj.user.id == regular_user.id
        assert obj.user.email == regular_user.email

    @pytest.mark.asyncio
    async def test_object_ref_timestamps(self, db_session: AsyncSession, regular_user):
        obj = ObjectRef(name="Timestamped", user_id=regular_user.id)
        db_session.add(obj)
        await db_session.commit()
        await db_session.refresh(obj)

        assert obj.created_at is not None
        assert obj.updated_at is not None
        assert isinstance(obj.created_at, datetime)
        assert isinstance(obj.updated_at, datetime)


class TestObjectRefImageModel:

    @pytest.mark.asyncio
    async def test_create_object_ref_image(self, db_session: AsyncSession, regular_user):
        obj = ObjectRef(name="Car", user_id=regular_user.id)
        db_session.add(obj)
        await db_session.commit()

        image = ObjectRefImage(
            object_ref_id=obj.id,
            storage_path="/objects/car/front.png",
            is_primary=True,
            sort_order=0,
            width=1024,
            height=768,
        )
        db_session.add(image)
        await db_session.commit()
        await db_session.refresh(image)

        assert image.id is not None
        assert image.object_ref_id == obj.id
        assert image.storage_path == "/objects/car/front.png"
        assert image.is_primary is True
        assert image.sort_order == 0
        assert image.width == 1024
        assert image.height == 768

    @pytest.mark.asyncio
    async def test_object_ref_image_defaults(self, db_session: AsyncSession, regular_user):
        obj = ObjectRef(name="Vase", user_id=regular_user.id)
        db_session.add(obj)
        await db_session.commit()

        image = ObjectRefImage(
            object_ref_id=obj.id,
            storage_path="/objects/vase/img.png",
        )
        db_session.add(image)
        await db_session.commit()
        await db_session.refresh(image)

        assert image.is_primary is False
        assert image.sort_order == 0
        assert image.width is None
        assert image.height is None

    @pytest.mark.asyncio
    async def test_object_ref_images_relationship(self, db_session: AsyncSession, regular_user):
        obj = ObjectRef(name="House", user_id=regular_user.id)
        db_session.add(obj)
        await db_session.commit()

        img_a = ObjectRefImage(object_ref_id=obj.id, storage_path="/objects/house/a.png")
        img_b = ObjectRefImage(object_ref_id=obj.id, storage_path="/objects/house/b.png")
        db_session.add_all([img_a, img_b])
        await db_session.commit()

        result = await db_session.execute(
            select(ObjectRef).where(ObjectRef.id == obj.id).options(selectinload(ObjectRef.images))
        )
        obj = result.scalar_one()

        assert len(obj.images) == 2
        paths = {img.storage_path for img in obj.images}
        assert paths == {"/objects/house/a.png", "/objects/house/b.png"}

    @pytest.mark.asyncio
    async def test_cascade_delete_object_ref_deletes_images(
        self, db_session: AsyncSession, regular_user
    ):
        obj = ObjectRef(name="To Delete", user_id=regular_user.id)
        db_session.add(obj)
        await db_session.commit()

        image = ObjectRefImage(object_ref_id=obj.id, storage_path="/objects/delete/img.png")
        db_session.add(image)
        await db_session.commit()
        image_id = image.id

        await db_session.delete(obj)
        await db_session.commit()

        result = await db_session.execute(
            select(ObjectRefImage).where(ObjectRefImage.id == image_id)
        )
        assert result.scalar_one_or_none() is None


class TestJobObjectRefModel:

    @pytest.mark.asyncio
    async def test_create_job_object_ref(self, db_session: AsyncSession, regular_user):
        obj = ObjectRef(name="Car", user_id=regular_user.id)
        db_session.add(obj)
        await db_session.commit()

        job = Job(user_id=regular_user.id)
        db_session.add(job)
        await db_session.commit()

        link = JobObjectRef(
            job_id=job.id,
            object_ref_id=obj.id,
            role="primary_subject",
            importance_score=0.95,
        )
        db_session.add(link)
        await db_session.commit()
        await db_session.refresh(link)

        assert link.job_id == job.id
        assert link.object_ref_id == obj.id
        assert link.role == "primary_subject"
        assert link.importance_score == 0.95

    @pytest.mark.asyncio
    async def test_job_object_ref_bidirectional(
        self, db_session: AsyncSession, regular_user
    ):
        obj = ObjectRef(name="Boat", user_id=regular_user.id)
        db_session.add(obj)
        await db_session.commit()

        job = Job(user_id=regular_user.id)
        db_session.add(job)
        await db_session.commit()

        link = JobObjectRef(job_id=job.id, object_ref_id=obj.id)
        db_session.add(link)
        await db_session.commit()

        # Access from job side
        result = await db_session.execute(
            select(Job).where(Job.id == job.id).options(selectinload(Job.object_ref_assignments))
        )
        job_loaded = result.scalar_one()
        assert len(job_loaded.object_ref_assignments) == 1
        assert job_loaded.object_ref_assignments[0].object_ref_id == obj.id

        # Access from object_ref side
        result = await db_session.execute(
            select(ObjectRef).where(ObjectRef.id == obj.id).options(selectinload(ObjectRef.job_assignments))
        )
        obj_loaded = result.scalar_one()
        assert len(obj_loaded.job_assignments) == 1
        assert obj_loaded.job_assignments[0].job_id == job.id

    @pytest.mark.asyncio
    async def test_job_object_ref_nullable_role_and_score(
        self, db_session: AsyncSession, regular_user
    ):
        obj = ObjectRef(name="Tree", user_id=regular_user.id)
        db_session.add(obj)
        await db_session.commit()

        job = Job(user_id=regular_user.id)
        db_session.add(job)
        await db_session.commit()

        link = JobObjectRef(job_id=job.id, object_ref_id=obj.id)
        db_session.add(link)
        await db_session.commit()
        await db_session.refresh(link)

        assert link.role is None
        assert link.importance_score is None

    @pytest.mark.asyncio
    async def test_cascade_delete_job_removes_assignment(
        self, db_session: AsyncSession, regular_user
    ):
        obj = ObjectRef(name="Rock", user_id=regular_user.id)
        db_session.add(obj)
        await db_session.commit()

        job = Job(user_id=regular_user.id)
        db_session.add(job)
        await db_session.commit()

        link = JobObjectRef(job_id=job.id, object_ref_id=obj.id)
        db_session.add(link)
        await db_session.commit()

        await db_session.delete(link)
        await db_session.delete(job)
        await db_session.commit()

        result = await db_session.execute(
            select(JobObjectRef).where(JobObjectRef.object_ref_id == obj.id)
        )
        assert result.scalar_one_or_none() is None
