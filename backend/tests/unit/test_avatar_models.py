from datetime import datetime
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import Avatar, AvatarImage, JobAvatar


class TestAvatarModel:

    @pytest.mark.asyncio
    async def test_create_avatar_with_valid_fields(self, db_session: AsyncSession, regular_user):
        avatar = Avatar(
            name="Alice",
            gender="Female",
            user_id=regular_user.id,
            bio="A test avatar",
        )
        db_session.add(avatar)
        await db_session.commit()
        await db_session.refresh(avatar)

        assert avatar.id is not None
        assert avatar.name == "Alice"
        assert avatar.gender == "Female"
        assert avatar.user_id == regular_user.id
        assert avatar.bio == "A test avatar"

    @pytest.mark.asyncio
    async def test_avatar_consistency_strategy_default(self, db_session: AsyncSession, regular_user):
        avatar = Avatar(name="Bob", gender="Male", user_id=regular_user.id)
        db_session.add(avatar)
        await db_session.commit()
        await db_session.refresh(avatar)

        assert avatar.consistency_strategy == "ip_adapter"

    @pytest.mark.asyncio
    async def test_avatar_explicit_consistency_strategy(
        self, db_session: AsyncSession, regular_user
    ):
        avatar = Avatar(
            name="Charlie",
            gender="Non-binary",
            user_id=regular_user.id,
            consistency_strategy="face_swap",
        )
        db_session.add(avatar)
        await db_session.commit()
        await db_session.refresh(avatar)

        assert avatar.consistency_strategy == "face_swap"

    @pytest.mark.asyncio
    async def test_avatar_nullable_bio_field(self, db_session: AsyncSession, regular_user):
        avatar = Avatar(name="Diana", gender="Female", user_id=regular_user.id)
        db_session.add(avatar)
        await db_session.commit()
        await db_session.refresh(avatar)

        assert avatar.bio is None

    @pytest.mark.asyncio
    async def test_avatar_timestamps_set_on_create(self, db_session: AsyncSession, regular_user):
        avatar = Avatar(name="Eve", gender="Female", user_id=regular_user.id)
        db_session.add(avatar)
        await db_session.commit()
        await db_session.refresh(avatar)

        assert avatar.created_at is not None
        assert avatar.updated_at is not None
        assert isinstance(avatar.created_at, datetime)
        assert isinstance(avatar.updated_at, datetime)

    @pytest.mark.asyncio
    async def test_avatar_soft_delete(self, db_session: AsyncSession, regular_user):
        avatar = Avatar(name="Frank", gender="Male", user_id=regular_user.id)
        db_session.add(avatar)
        await db_session.commit()

        avatar.deleted_at = datetime.utcnow()
        await db_session.commit()
        await db_session.refresh(avatar)

        assert avatar.deleted_at is not None
        assert isinstance(avatar.deleted_at, datetime)

    @pytest.mark.asyncio
    async def test_avatar_belongs_to_user(self, db_session: AsyncSession, regular_user):
        avatar = Avatar(name="Grace", gender="Female", user_id=regular_user.id)
        db_session.add(avatar)
        await db_session.commit()
        await db_session.refresh(avatar)

        assert avatar.user.id == regular_user.id
        assert avatar.user.email == regular_user.email


class TestAvatarImageModel:

    @pytest.mark.asyncio
    async def test_create_avatar_image(self, db_session: AsyncSession, regular_user):
        avatar = Avatar(name="Hank", gender="Male", user_id=regular_user.id)
        db_session.add(avatar)
        await db_session.commit()

        image = AvatarImage(
            avatar_id=avatar.id,
            storage_path="/avatars/hank/img_001.png",
            is_primary=True,
            sort_order=0,
            width=512,
            height=512,
        )
        db_session.add(image)
        await db_session.commit()
        await db_session.refresh(image)

        assert image.id is not None
        assert image.avatar_id == avatar.id
        assert image.storage_path == "/avatars/hank/img_001.png"
        assert image.is_primary is True
        assert image.sort_order == 0
        assert image.width == 512
        assert image.height == 512

    @pytest.mark.asyncio
    async def test_avatar_image_defaults(self, db_session: AsyncSession, regular_user):
        avatar = Avatar(name="Ivy", gender="Female", user_id=regular_user.id)
        db_session.add(avatar)
        await db_session.commit()

        image = AvatarImage(
            avatar_id=avatar.id,
            storage_path="/avatars/ivy/img_001.png",
        )
        db_session.add(image)
        await db_session.commit()
        await db_session.refresh(image)

        assert image.is_primary is False
        assert image.sort_order == 0

    @pytest.mark.asyncio
    async def test_avatar_images_relationship(self, db_session: AsyncSession, regular_user):
        from sqlalchemy.orm import selectinload

        avatar = Avatar(name="Jack", gender="Male", user_id=regular_user.id)
        db_session.add(avatar)
        await db_session.commit()

        image_a = AvatarImage(avatar_id=avatar.id, storage_path="/avatars/jack/a.png")
        image_b = AvatarImage(avatar_id=avatar.id, storage_path="/avatars/jack/b.png")
        db_session.add_all([image_a, image_b])
        await db_session.commit()

        result = await db_session.execute(
            select(Avatar).where(Avatar.id == avatar.id).options(selectinload(Avatar.images))
        )
        avatar = result.scalar_one()

        assert len(avatar.images) == 2
        paths = {img.storage_path for img in avatar.images}
        assert paths == {"/avatars/jack/a.png", "/avatars/jack/b.png"}

    @pytest.mark.asyncio
    async def test_avatar_primary_image_relationship(
        self, db_session: AsyncSession, regular_user
    ):
        avatar = Avatar(name="Kate", gender="Female", user_id=regular_user.id)
        db_session.add(avatar)
        await db_session.commit()

        image = AvatarImage(avatar_id=avatar.id, storage_path="/avatars/kate/primary.png")
        db_session.add(image)
        await db_session.commit()
        await db_session.refresh(image)

        avatar.primary_image_id = image.id
        await db_session.commit()
        await db_session.refresh(avatar)

        assert avatar.primary_image is not None
        assert avatar.primary_image.id == image.id
        assert avatar.primary_image.storage_path == "/avatars/kate/primary.png"

    @pytest.mark.asyncio
    async def test_cascade_delete_avatar_deletes_images(
        self, db_session: AsyncSession, regular_user
    ):
        avatar = Avatar(name="Leo", gender="Male", user_id=regular_user.id)
        db_session.add(avatar)
        await db_session.commit()

        image = AvatarImage(avatar_id=avatar.id, storage_path="/avatars/leo/img.png")
        db_session.add(image)
        await db_session.commit()
        image_id = image.id

        await db_session.delete(avatar)
        await db_session.commit()

        result = await db_session.execute(select(AvatarImage).where(AvatarImage.id == image_id))
        assert result.scalar_one_or_none() is None

    @pytest.mark.asyncio
    async def test_multiple_images_per_avatar(self, db_session: AsyncSession, regular_user):
        avatar = Avatar(name="Mia", gender="Female", user_id=regular_user.id)
        db_session.add(avatar)
        await db_session.commit()

        images = [
            AvatarImage(avatar_id=avatar.id, storage_path=f"/avatars/mia/img_{i}.png", sort_order=i)
            for i in range(3)
        ]
        db_session.add_all(images)
        await db_session.commit()

        result = await db_session.execute(
            select(AvatarImage).where(AvatarImage.avatar_id == avatar.id).order_by(AvatarImage.sort_order)
        )
        fetched = result.scalars().all()
        assert len(fetched) == 3
        assert [img.sort_order for img in fetched] == [0, 1, 2]


class TestJobAvatarModel:

    @pytest.mark.asyncio
    async def test_create_job_avatar_assignment(
        self, db_session: AsyncSession, regular_user, template, job_for_user
    ):
        avatar = Avatar(name="Nick", gender="Male", user_id=regular_user.id)
        db_session.add(avatar)
        await db_session.commit()

        assignment = JobAvatar(
            job_id=job_for_user.id,
            avatar_id=avatar.id,
            role="protagonist",
            consistency_strategy_override="face_swap",
        )
        db_session.add(assignment)
        await db_session.commit()
        await db_session.refresh(assignment)

        assert assignment.job_id == job_for_user.id
        assert assignment.avatar_id == avatar.id
        assert assignment.role == "protagonist"
        assert assignment.consistency_strategy_override == "face_swap"

    @pytest.mark.asyncio
    async def test_job_avatar_composite_pk(
        self, db_session: AsyncSession, regular_user, template, job_for_user
    ):
        avatar = Avatar(name="Oscar", gender="Male", user_id=regular_user.id)
        db_session.add(avatar)
        await db_session.commit()

        from app.database import Job

        job_b = Job(
            id=uuid4(),
            user_id=regular_user.id,
            template_id=template.id,
            status="pending",
            input_data={},
        )
        db_session.add(job_b)
        await db_session.commit()

        assignment_a = JobAvatar(job_id=job_for_user.id, avatar_id=avatar.id)
        assignment_b = JobAvatar(job_id=job_b.id, avatar_id=avatar.id)
        db_session.add_all([assignment_a, assignment_b])
        await db_session.commit()

        result = await db_session.execute(
            select(JobAvatar).where(JobAvatar.avatar_id == avatar.id)
        )
        assignments = result.scalars().all()
        assert len(assignments) == 2
        job_ids = {a.job_id for a in assignments}
        assert job_ids == {job_for_user.id, job_b.id}

    @pytest.mark.asyncio
    async def test_job_avatar_uniqueness_violation(
        self, db_session: AsyncSession, regular_user, template, job_for_user
    ):
        avatar = Avatar(name="Paul", gender="Male", user_id=regular_user.id)
        db_session.add(avatar)
        await db_session.commit()

        assignment = JobAvatar(job_id=job_for_user.id, avatar_id=avatar.id)
        db_session.add(assignment)
        await db_session.commit()

        duplicate = JobAvatar(job_id=job_for_user.id, avatar_id=avatar.id)
        db_session.add(duplicate)
        with pytest.raises(Exception):
            await db_session.commit()
        await db_session.rollback()

    @pytest.mark.asyncio
    async def test_avatar_job_assignments_relationship(
        self, db_session: AsyncSession, regular_user, template, job_for_user
    ):
        from sqlalchemy.orm import selectinload

        avatar = Avatar(name="Quinn", gender="Female", user_id=regular_user.id)
        db_session.add(avatar)
        await db_session.commit()

        assignment = JobAvatar(job_id=job_for_user.id, avatar_id=avatar.id)
        db_session.add(assignment)
        await db_session.commit()

        result = await db_session.execute(
            select(Avatar).where(Avatar.id == avatar.id).options(selectinload(Avatar.job_assignments))
        )
        avatar = result.scalar_one()

        assert len(avatar.job_assignments) == 1
        assert avatar.job_assignments[0].job_id == job_for_user.id

    @pytest.mark.asyncio
    async def test_job_avatar_assignments_relationship(
        self, db_session: AsyncSession, regular_user, template, job_for_user
    ):
        avatar = Avatar(name="Rachel", gender="Female", user_id=regular_user.id)
        db_session.add(avatar)
        await db_session.commit()

        assignment = JobAvatar(job_id=job_for_user.id, avatar_id=avatar.id)
        db_session.add(assignment)
        await db_session.commit()
        await db_session.refresh(job_for_user)

        assert len(job_for_user.avatar_assignments) == 1
        assert job_for_user.avatar_assignments[0].avatar_id == avatar.id

    @pytest.mark.asyncio
    async def test_job_avatar_nullable_role_and_override(
        self, db_session: AsyncSession, regular_user, template, job_for_user
    ):
        avatar = Avatar(name="Sam", gender="Male", user_id=regular_user.id)
        db_session.add(avatar)
        await db_session.commit()

        assignment = JobAvatar(job_id=job_for_user.id, avatar_id=avatar.id)
        db_session.add(assignment)
        await db_session.commit()
        await db_session.refresh(assignment)

        assert assignment.role is None
        assert assignment.consistency_strategy_override is None
