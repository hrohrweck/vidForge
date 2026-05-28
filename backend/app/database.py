from datetime import datetime
from decimal import Decimal
from typing import AsyncGenerator
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    select,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.config import get_settings


class Base(DeclarativeBase):
    pass


class UserGroup(Base):
    __tablename__ = "user_groups"
    __table_args__ = (UniqueConstraint("user_id", "group_id", name="uq_user_group"),)

    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    group_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("groups.id", ondelete="CASCADE"), primary_key=True
    )


class GroupPermission(Base):
    __tablename__ = "group_permissions"
    __table_args__ = (UniqueConstraint("group_id", "permission_id", name="uq_group_permission"),)

    group_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("groups.id", ondelete="CASCADE"), primary_key=True
    )
    permission_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True
    )


class Permission(Base):
    __tablename__ = "permissions"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(String(255))
    category: Mapped[str] = mapped_column(String(50), nullable=False, index=True)

    groups: Mapped[list["Group"]] = relationship(
        secondary="group_permissions", back_populates="permissions", lazy="selectin"
    )


class Group(Base):
    __tablename__ = "groups"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    users: Mapped[list["User"]] = relationship(
        secondary="user_groups", back_populates="groups", lazy="selectin"
    )
    permissions: Mapped[list["Permission"]] = relationship(
        secondary="group_permissions", back_populates="groups", lazy="selectin"
    )


class Conversation(Base):
    __tablename__ = "conversation"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    model_id: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    user: Mapped["User"] = relationship(back_populates="conversations")
    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan"
    )
    token_usages: Mapped[list["ChatTokenUsage"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan"
    )


class Message(Base):
    __tablename__ = "message"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    conversation_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("conversation.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    tool_calls: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    tool_call_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    attachments: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    tokens_in: Mapped[int] = mapped_column(Integer, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    conversation: Mapped["Conversation"] = relationship(back_populates="messages")


class MCPServer(Base):
    __tablename__ = "mcp_server"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    auth_type: Mapped[str] = mapped_column(String(20), default="none", nullable=False)
    encrypted_credentials: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class ChatTokenUsage(Base):
    __tablename__ = "chat_token_usage"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    model_id: Mapped[str] = mapped_column(String(100), nullable=False)
    conversation_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("conversation.id", ondelete="CASCADE"), nullable=True
    )
    tokens_in: Mapped[int] = mapped_column(Integer, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, default=0)
    recorded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped["User"] = relationship(back_populates="chat_token_usages")
    conversation: Mapped["Conversation | None"] = relationship(back_populates="token_usages")


engine = create_async_engine(
    get_settings().database_url,
    echo=get_settings().debug,
)

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def create_tables() -> None:
    # Import media models so their tables are included in Base.metadata
    import app.models.app_settings  # noqa: F401
    import app.models.media  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session() as session:
        yield session


class User(Base):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    jobs: Mapped[list["Job"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    templates: Mapped[list["Template"]] = relationship(
        back_populates="creator", cascade="all, delete-orphan"
    )
    settings: Mapped["UserSettings"] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    groups: Mapped[list["Group"]] = relationship(
        secondary="user_groups", back_populates="users", lazy="selectin"
    )
    media_folders: Mapped[list["MediaFolder"]] = relationship(  # noqa: F821
        back_populates="user", cascade="all, delete-orphan"
    )
    media_assets: Mapped[list["MediaAsset"]] = relationship(  # noqa: F821
        back_populates="user", cascade="all, delete-orphan"
    )
    media_tags: Mapped[list["MediaTag"]] = relationship(  # noqa: F821
        back_populates="user", cascade="all, delete-orphan"
    )
    projects: Mapped[list["Project"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    conversations: Mapped[list["Conversation"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    chat_token_usages: Mapped[list["ChatTokenUsage"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    avatars: Mapped[list["Avatar"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class UserSettings(Base):
    __tablename__ = "user_settings"

    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id"), primary_key=True
    )
    default_style_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("styles.id"), nullable=True
    )
    storage_backend: Mapped[str] = mapped_column(String(50), default="local")
    storage_config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    preferences: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    user: Mapped["User"] = relationship(back_populates="settings")
    default_style: Mapped["Style | None"] = relationship(back_populates="users_using_default")


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    user: Mapped["User"] = relationship(back_populates="projects")
    jobs: Mapped[list["Job"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    media_assets: Mapped[list["MediaAsset"]] = relationship(back_populates="project")  # noqa: F821


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    title: Mapped[str] = mapped_column(String(255), nullable=False, default="Untitled Video")
    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    project_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=True
    )
    template_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("templates.id"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(50), default="pending", index=True)
    stage: Mapped[str] = mapped_column(String(50), default="planning", index=True)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    input_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    output_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    preview_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    thumbnail_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("providers.id"), nullable=True
    )
    worker_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("workers.id"), nullable=True
    )
    provider_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    provider_preference: Mapped[str] = mapped_column(String(50), default="auto")
    model_preference: Mapped[str | None] = mapped_column(String(50), nullable=True)
    estimated_cost: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    actual_cost: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    image_provider_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("providers.id"), nullable=True
    )
    video_provider_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("providers.id"), nullable=True
    )
    export_options: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    workflow_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    user: Mapped["User"] = relationship(back_populates="jobs")
    project: Mapped["Project | None"] = relationship(back_populates="jobs")
    template: Mapped["Template | None"] = relationship(back_populates="jobs")
    provider: Mapped["Provider | None"] = relationship(
        back_populates="jobs", foreign_keys=[provider_id]
    )
    image_provider: Mapped["Provider | None"] = relationship(
        foreign_keys=[image_provider_id]
    )
    video_provider: Mapped["Provider | None"] = relationship(
        foreign_keys=[video_provider_id]
    )
    worker: Mapped["Worker | None"] = relationship(back_populates="jobs")
    scenes: Mapped[list["VideoScene"]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )
    avatar_assignments: Mapped[list["JobAvatar"]] = relationship(
        back_populates="job", lazy="selectin"
    )


class Template(Base):
    __tablename__ = "templates"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    config: Mapped[dict] = mapped_column(JSONB, nullable=False)
    is_builtin: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    creator: Mapped["User | None"] = relationship(back_populates="templates")
    jobs: Mapped[list["Job"]] = relationship(back_populates="template")


class Style(Base):
    __tablename__ = "styles"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    params: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    users_using_default: Mapped[list["UserSettings"]] = relationship(back_populates="default_style")


class Provider(Base):
    __tablename__ = "providers"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    provider_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    daily_budget_limit: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    current_daily_spend: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0"))
    spend_reset_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    priority: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    workers: Mapped[list["Worker"]] = relationship(
        back_populates="provider", cascade="all, delete-orphan"
    )
    jobs: Mapped[list["Job"]] = relationship(
        back_populates="provider", foreign_keys="Job.provider_id"
    )
    poe_models: Mapped[list["PoeModel"]] = relationship(
        back_populates="provider", cascade="all, delete-orphan"
    )
    atlascloud_models: Mapped[list["AtlasCloudModel"]] = relationship(
        back_populates="provider", cascade="all, delete-orphan"
    )


class AtlasCloudModel(Base):
    __tablename__ = "atlascloud_models"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    provider_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("providers.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    model_id: Mapped[str] = mapped_column(String(255), nullable=False)
    modality: Mapped[str] = mapped_column(String(20), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    provider: Mapped["Provider"] = relationship(back_populates="atlascloud_models")


class PoeModel(Base):
    __tablename__ = "poe_models"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    provider_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("providers.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    model_id: Mapped[str] = mapped_column(String(255), nullable=False)
    modality: Mapped[str] = mapped_column(String(20), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    provider: Mapped["Provider"] = relationship(back_populates="poe_models")


class Worker(Base):
    __tablename__ = "workers"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    provider_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("providers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    worker_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="offline", index=True)
    capabilities: Mapped[dict] = mapped_column(JSONB, default=dict)
    last_heartbeat: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    current_job_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    provider: Mapped["Provider"] = relationship(back_populates="workers")
    jobs: Mapped[list["Job"]] = relationship(back_populates="worker")


class CostLog(Base):
    __tablename__ = "cost_log"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    provider_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("providers.id"), nullable=False
    )
    job_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("jobs.id"), nullable=True
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    gpu_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class VideoScene(Base):
    __tablename__ = "video_scenes"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    job_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    scene_number: Mapped[int] = mapped_column(Integer, nullable=False)
    start_time: Mapped[float] = mapped_column(nullable=False)
    end_time: Mapped[float] = mapped_column(nullable=False)
    lyrics_segment: Mapped[str | None] = mapped_column(Text, nullable=True)
    visual_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    mood: Mapped[str] = mapped_column(String(50), default="neutral")
    camera_movement: Mapped[str] = mapped_column(String(50), default="static")
    reference_image_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    thumbnail_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    generated_video_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="pending")
    image_provider_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("providers.id", ondelete="SET NULL"), nullable=True
    )
    video_provider_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("providers.id", ondelete="SET NULL"), nullable=True
    )
    image_prompt_enhanced: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration: Mapped[float | None] = mapped_column(nullable=True)
    model_used: Mapped[str | None] = mapped_column(String(100), nullable=True)
    seed: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    job: Mapped["Job"] = relationship(back_populates="scenes")


async def seed_builtin_data() -> None:
    """Load built-in templates and styles into the database.

    Templates come from two sources:
    1. Plugin ``template.yaml`` files (preferred)
    2. Legacy ``templates/*.yaml`` files (kept for backward compat)
    """
    from app.config import get_settings
    from app.plugins.registry import get_all_plugins
    from app.services.template_loader import StyleLoader, TemplateLoader

    settings = get_settings()

    async with async_session() as db:
        # --- Load templates from plugins first ---
        for plugin in get_all_plugins().values():
            try:
                tdef = plugin.get_template_definition()
                result = await db.execute(
                    select(Template).where(Template.name == tdef["name"])
                )
                existing = result.scalar_one_or_none()
                if existing:
                    # Update config so existing jobs still work
                    existing.config = {
                        "plugin_id": plugin.plugin_id,
                        "workflow_type": "scene_based",
                        "inputs": tdef.get("inputs", []),
                    }
                    if "config" in tdef:
                        existing.config.update(tdef["config"])
                    if "stages" in tdef:
                        existing.config["stages"] = tdef["stages"]
                    continue

                config: dict = {
                    "plugin_id": plugin.plugin_id,
                    "workflow_type": "scene_based",
                    "inputs": tdef.get("inputs", []),
                    "pipeline": tdef.get("pipeline", []),
                }
                if "config" in tdef:
                    config.update(tdef["config"])
                if "stages" in tdef:
                    config["stages"] = tdef["stages"]

                template = Template(
                    name=tdef["name"],
                    description=tdef.get("description"),
                    config=config,
                    is_builtin=True,
                    created_by=None,
                )
                db.add(template)
            except Exception as e:
                print(f"Warning: Could not seed template from plugin {plugin.plugin_id}: {e}")

        # --- Load legacy templates (those without a plugin) ---
        template_loader = TemplateLoader(settings.templates_path)
        try:
            for template_data in template_loader.load_all_templates():
                result = await db.execute(
                    select(Template).where(Template.name == template_data["name"])
                )
                if result.scalar_one_or_none():
                    continue  # already loaded via plugin
        except Exception as e:
            print(f"Warning: Could not scan legacy templates: {e}")

        await db.commit()

        # Load styles
        style_loader = StyleLoader(settings.styles_path)
        try:
            styles = style_loader.load_all_styles()
            for style_data in styles:
                # Check if style already exists by name
                result = await db.execute(select(Style).where(Style.name == style_data["name"]))
                existing = result.scalar_one_or_none()

                if not existing:
                    style = Style(
                        name=style_data["name"],
                        category=style_data.get("category", "video"),
                        params=style_data.get("params", {}),
                    )
                    db.add(style)
            await db.commit()
        except Exception as e:
            await db.rollback()
            print(f"Warning: Could not seed styles: {e}")


DEFAULT_PERMISSIONS = [
    ("jobs:create", "Create new video generation jobs", "jobs"),
    ("jobs:view", "View own jobs", "jobs"),
    ("jobs:view:all", "View all users' jobs", "jobs"),
    ("templates:create", "Create custom templates", "templates"),
    ("templates:view", "View templates", "templates"),
    ("styles:create", "Create custom styles", "styles"),
    ("admin:dashboard", "View admin dashboard", "admin"),
    ("admin:users:read", "View user list and details", "admin"),
    ("admin:users:write", "Modify users (roles, status, groups)", "admin"),
    ("admin:users:delete", "Delete users", "admin"),
    ("admin:jobs:manage", "Cancel/retry any job", "admin"),
    ("admin:groups:manage", "Create and manage groups", "admin"),
]

DEFAULT_GROUPS = {
    "users": {
        "description": "Default group for regular users",
        "permissions": ["jobs:create", "jobs:view", "templates:view", "styles:create"],
    },
    "editors": {
        "description": "Users with elevated content creation privileges",
        "permissions": [
            "jobs:create",
            "jobs:view",
            "jobs:view:all",
            "templates:create",
            "templates:view",
            "styles:create",
        ],
    },
    "admins": {
        "description": "Administrators with full access",
        "permissions": [p[0] for p in DEFAULT_PERMISSIONS],
    },
}


async def seed_rbac_data() -> None:
    """Seed permissions, groups, and group-permission assignments."""
    async with async_session() as db:
        try:
            for name, description, category in DEFAULT_PERMISSIONS:
                result = await db.execute(select(Permission).where(Permission.name == name))
                if not result.scalar_one_or_none():
                    permission = Permission(
                        name=name,
                        description=description,
                        category=category,
                    )
                    db.add(permission)
            await db.commit()
        except Exception as e:
            await db.rollback()
            print(f"Warning: Could not seed permissions: {e}")

        permission_cache: dict[str, Permission] = {}
        for name, _, _ in DEFAULT_PERMISSIONS:
            result = await db.execute(select(Permission).where(Permission.name == name))
            perm = result.scalar_one_or_none()
            if perm:
                permission_cache[name] = perm

        try:
            for group_name, group_config in DEFAULT_GROUPS.items():
                result = await db.execute(select(Group).where(Group.name == group_name))
                group = result.scalar_one_or_none()

                if not group:
                    group = Group(
                        name=group_name,
                        description=group_config["description"],
                    )
                    db.add(group)
                    await db.flush()

                for perm_name in group_config["permissions"]:
                    if perm_name in permission_cache:
                        existing = await db.execute(
                            select(GroupPermission).where(
                                GroupPermission.group_id == group.id,
                                GroupPermission.permission_id == permission_cache[perm_name].id,
                            )
                        )
                        if not existing.scalar_one_or_none():
                            gp = GroupPermission(
                                group_id=group.id,
                                permission_id=permission_cache[perm_name].id,
                            )
                            db.add(gp)
            await db.commit()
        except Exception as e:
            await db.rollback()
            print(f"Warning: Could not seed groups: {e}")


class Avatar(Base):
    __tablename__ = "avatars"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    gender: Mapped[str] = mapped_column(String(20), nullable=False)
    bio: Mapped[str | None] = mapped_column(Text, nullable=True)
    consistency_strategy: Mapped[str] = mapped_column(String(20), default="ip_adapter")
    primary_image_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("avatar_images.id", use_alter=True, name="fk_avatar_primary_image"),
        nullable=True,
    )
    lora_model_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    lora_training_status: Mapped[str] = mapped_column(
        String(20), server_default="not_trained", nullable=False
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    user: Mapped["User"] = relationship(back_populates="avatars")
    images: Mapped[list["AvatarImage"]] = relationship(
        back_populates="avatar",
        primaryjoin="AvatarImage.avatar_id == Avatar.id",
        cascade="all, delete-orphan",
    )
    primary_image: Mapped["AvatarImage | None"] = relationship(
        primaryjoin="Avatar.primary_image_id == AvatarImage.id",
        post_update=True,
    )
    job_assignments: Mapped[list["JobAvatar"]] = relationship(back_populates="avatar")


class AvatarImage(Base):
    __tablename__ = "avatar_images"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    avatar_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("avatars.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    storage_path: Mapped[str] = mapped_column(String(500), nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    file_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    content_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    avatar: Mapped["Avatar"] = relationship(
        back_populates="images", foreign_keys=[avatar_id]
    )


class JobAvatar(Base):
    __tablename__ = "job_avatars"
    __table_args__ = ()

    job_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("jobs.id", ondelete="CASCADE"),
        primary_key=True,
    )
    avatar_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("avatars.id", ondelete="CASCADE"),
        primary_key=True,
    )
    role: Mapped[str | None] = mapped_column(Text, nullable=True)
    consistency_strategy_override: Mapped[str | None] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    job: Mapped["Job"] = relationship(back_populates="avatar_assignments")
    avatar: Mapped["Avatar"] = relationship(back_populates="job_assignments")
