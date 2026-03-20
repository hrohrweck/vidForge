from datetime import datetime
from typing import AsyncGenerator
from uuid import UUID, uuid4

from sqlalchemy import DateTime, String, Text, Boolean, Integer, ForeignKey, select
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.config import get_settings


class Base(DeclarativeBase):
    pass


engine = create_async_engine(
    get_settings().database_url,
    echo=get_settings().debug,
)

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def create_tables() -> None:
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


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    template_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("templates.id"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(50), default="pending", index=True)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    input_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    output_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    preview_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    thumbnail_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    user: Mapped["User"] = relationship(back_populates="jobs")
    template: Mapped["Template | None"] = relationship(back_populates="jobs")


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


async def seed_builtin_data() -> None:
    """Load built-in templates and styles from YAML files into the database."""
    from app.services.template_loader import TemplateLoader, StyleLoader
    from app.config import get_settings
    
    settings = get_settings()
    
    async with async_session() as db:
        # Load templates
        template_loader = TemplateLoader(settings.templates_path)
        try:
            templates = template_loader.load_all_templates()
            for template_data in templates:
                # Check if template already exists by name
                result = await db.execute(
                    select(Template).where(Template.name == template_data["name"])
                )
                existing = result.scalar_one_or_none()
                
                if not existing:
                    template = Template(
                        name=template_data["name"],
                        description=template_data.get("description"),
                        config={
                            "template_file": template_data.get("_source_file", ""),
                            "inputs": template_data.get("inputs", []),
                            "pipeline": template_data.get("pipeline", []),
                        },
                        is_builtin=True,
                        created_by=None,
                    )
                    db.add(template)
            await db.commit()
        except Exception as e:
            await db.rollback()
            print(f"Warning: Could not seed templates: {e}")
        
        # Load styles
        style_loader = StyleLoader(settings.styles_path)
        try:
            styles = style_loader.load_all_styles()
            for style_data in styles:
                # Check if style already exists by name
                result = await db.execute(
                    select(Style).where(Style.name == style_data["name"])
                )
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
