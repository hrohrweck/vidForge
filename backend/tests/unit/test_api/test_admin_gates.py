"""Admin gate tests for global templates and styles write endpoints."""
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import create_access_token
from app.database import Style, Template, User


@pytest.fixture
async def non_builtin_template(db_session: AsyncSession, regular_user: User):
    template = Template(
        name="User Template",
        description="A user-created template",
        config={"inputs": []},
        is_builtin=False,
        created_by=regular_user.id,
    )
    db_session.add(template)
    await db_session.commit()
    await db_session.refresh(template)
    return template


@pytest.fixture
async def existing_style(db_session: AsyncSession):
    style = Style(
        name="Existing Style",
        category="test",
        params={},
    )
    db_session.add(style)
    await db_session.commit()
    await db_session.refresh(style)
    return style


class TestTemplateAdminGates:
    async def test_non_admin_cannot_create_template(self, client: AsyncClient, regular_user_token: str):
        response = await client.post(
            "/api/templates",
            json={"name": "New Template", "description": "", "config": {"inputs": []}},
            headers={"Authorization": f"Bearer {regular_user_token}"},
        )
        assert response.status_code == 403

    async def test_admin_can_create_template(self, client: AsyncClient, superuser_token: str):
        response = await client.post(
            "/api/templates",
            json={"name": "Admin Template", "description": "", "config": {"inputs": []}},
            headers={"Authorization": f"Bearer {superuser_token}"},
        )
        assert response.status_code == 200

    async def test_non_admin_cannot_update_template(
        self, client: AsyncClient, regular_user_token: str, non_builtin_template: Template
    ):
        response = await client.put(
            f"/api/templates/{non_builtin_template.id}",
            json={"name": "Updated", "description": "", "config": {"inputs": []}},
            headers={"Authorization": f"Bearer {regular_user_token}"},
        )
        assert response.status_code == 403

    async def test_admin_can_update_template(
        self, client: AsyncClient, superuser_token: str, non_builtin_template: Template
    ):
        response = await client.put(
            f"/api/templates/{non_builtin_template.id}",
            json={"name": "Updated", "description": "", "config": {"inputs": []}},
            headers={"Authorization": f"Bearer {superuser_token}"},
        )
        assert response.status_code == 200

    async def test_non_admin_cannot_delete_template(
        self, client: AsyncClient, regular_user_token: str, non_builtin_template: Template
    ):
        response = await client.delete(
            f"/api/templates/{non_builtin_template.id}",
            headers={"Authorization": f"Bearer {regular_user_token}"},
        )
        assert response.status_code == 403

    async def test_admin_can_delete_template(
        self, client: AsyncClient, superuser_token: str, non_builtin_template: Template
    ):
        response = await client.delete(
            f"/api/templates/{non_builtin_template.id}",
            headers={"Authorization": f"Bearer {superuser_token}"},
        )
        assert response.status_code == 200

    async def test_any_authenticated_user_can_list_templates(
        self, client: AsyncClient, regular_user_token: str
    ):
        response = await client.get(
            "/api/templates",
            headers={"Authorization": f"Bearer {regular_user_token}"},
        )
        assert response.status_code == 200

    async def test_any_authenticated_user_can_get_template(
        self, client: AsyncClient, regular_user_token: str, non_builtin_template: Template
    ):
        response = await client.get(
            f"/api/templates/{non_builtin_template.id}",
            headers={"Authorization": f"Bearer {regular_user_token}"},
        )
        assert response.status_code == 200


class TestStyleAdminGates:
    async def test_non_admin_cannot_create_style(self, client: AsyncClient, regular_user_token: str):
        response = await client.post(
            "/api/styles",
            json={"name": "New Style", "category": "test", "params": {}},
            headers={"Authorization": f"Bearer {regular_user_token}"},
        )
        assert response.status_code == 403

    async def test_admin_can_create_style(self, client: AsyncClient, superuser_token: str):
        response = await client.post(
            "/api/styles",
            json={"name": "Admin Style", "category": "test", "params": {}},
            headers={"Authorization": f"Bearer {superuser_token}"},
        )
        assert response.status_code == 200

    async def test_non_admin_cannot_update_style(
        self, client: AsyncClient, regular_user_token: str, existing_style: Style
    ):
        response = await client.put(
            f"/api/styles/{existing_style.id}",
            json={"name": "Updated", "category": "test", "params": {}},
            headers={"Authorization": f"Bearer {regular_user_token}"},
        )
        assert response.status_code == 403

    async def test_admin_can_update_style(
        self, client: AsyncClient, superuser_token: str, existing_style: Style
    ):
        response = await client.put(
            f"/api/styles/{existing_style.id}",
            json={"name": "Updated", "category": "test", "params": {}},
            headers={"Authorization": f"Bearer {superuser_token}"},
        )
        assert response.status_code == 200

    async def test_non_admin_cannot_delete_style(
        self, client: AsyncClient, regular_user_token: str, existing_style: Style
    ):
        response = await client.delete(
            f"/api/styles/{existing_style.id}",
            headers={"Authorization": f"Bearer {regular_user_token}"},
        )
        assert response.status_code == 403

    async def test_admin_can_delete_style(
        self, client: AsyncClient, superuser_token: str, existing_style: Style
    ):
        response = await client.delete(
            f"/api/styles/{existing_style.id}",
            headers={"Authorization": f"Bearer {superuser_token}"},
        )
        assert response.status_code == 200

    async def test_any_authenticated_user_can_list_styles(
        self, client: AsyncClient, regular_user_token: str
    ):
        response = await client.get(
            "/api/styles",
            headers={"Authorization": f"Bearer {regular_user_token}"},
        )
        assert response.status_code == 200

    async def test_any_authenticated_user_can_get_style(
        self, client: AsyncClient, regular_user_token: str, existing_style: Style
    ):
        response = await client.get(
            f"/api/styles/{existing_style.id}",
            headers={"Authorization": f"Bearer {regular_user_token}"},
        )
        assert response.status_code == 200
