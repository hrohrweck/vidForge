import pytest
from httpx import AsyncClient

from app.services.app_settings import clear_settings_cache


@pytest.fixture(autouse=True)
def clear_cache_between_tests():
    clear_settings_cache()
    yield
    clear_settings_cache()


async def create_folder(
    client: AsyncClient,
    token: str,
    name: str,
    parent_id: str | None = None,
):
    payload = {"name": name, "parent_id": parent_id}
    return await client.post(
        "/api/media/folders",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )


@pytest.mark.asyncio
async def test_folder_creation_rejects_depth_greater_than_setting(
    client: AsyncClient,
    regular_user_token: str,
):
    root = await create_folder(client, regular_user_token, "root")
    assert root.status_code == 201
    child = await create_folder(client, regular_user_token, "child", root.json()["id"])
    assert child.status_code == 201
    grandchild = await create_folder(client, regular_user_token, "grandchild", child.json()["id"])
    assert grandchild.status_code == 201

    too_deep = await create_folder(
        client,
        regular_user_token,
        "too-deep",
        grandchild.json()["id"],
    )

    assert too_deep.status_code == 400
    assert "maximum allowed depth" in too_deep.json()["detail"]


@pytest.mark.asyncio
async def test_folder_update_rejects_move_that_exceeds_depth(
    client: AsyncClient,
    regular_user_token: str,
):
    root = await create_folder(client, regular_user_token, "root")
    child = await create_folder(client, regular_user_token, "child", root.json()["id"])
    grandchild = await create_folder(client, regular_user_token, "grandchild", child.json()["id"])
    folder_to_move = await create_folder(client, regular_user_token, "move-me")
    assert folder_to_move.status_code == 201

    response = await client.patch(
        f"/api/media/folders/{folder_to_move.json()['id']}",
        json={"parent_id": grandchild.json()["id"]},
        headers={"Authorization": f"Bearer {regular_user_token}"},
    )

    assert response.status_code == 400
    assert "maximum allowed depth" in response.json()["detail"]


@pytest.mark.asyncio
async def test_folder_update_rejects_self_or_descendant_parent(
    client: AsyncClient,
    regular_user_token: str,
):
    root = await create_folder(client, regular_user_token, "root")
    child = await create_folder(client, regular_user_token, "child", root.json()["id"])

    self_move = await client.patch(
        f"/api/media/folders/{root.json()['id']}",
        json={"parent_id": root.json()["id"]},
        headers={"Authorization": f"Bearer {regular_user_token}"},
    )
    descendant_move = await client.patch(
        f"/api/media/folders/{root.json()['id']}",
        json={"parent_id": child.json()["id"]},
        headers={"Authorization": f"Bearer {regular_user_token}"},
    )

    assert self_move.status_code == 400
    assert descendant_move.status_code == 400


@pytest.mark.asyncio
async def test_admin_can_update_depth_setting_and_non_admin_cannot(
    client: AsyncClient,
    db_session,
    superuser_token: str,
    regular_user_token: str,
):
    get_response = await client.get(
        "/api/admin/settings/media",
        headers={"Authorization": f"Bearer {superuser_token}"},
    )
    assert get_response.status_code == 200
    assert get_response.json() == {"max_folder_depth": 3}

    denied = await client.patch(
        "/api/admin/settings/media",
        json={"max_folder_depth": 4},
        headers={"Authorization": f"Bearer {regular_user_token}"},
    )
    assert denied.status_code == 403

    updated = await client.patch(
        "/api/admin/settings/media",
        json={"max_folder_depth": 4},
        headers={"Authorization": f"Bearer {superuser_token}"},
    )
    assert updated.status_code == 200
    assert updated.json() == {"max_folder_depth": 4}

    root = await create_folder(client, regular_user_token, "root")
    child = await create_folder(client, regular_user_token, "child", root.json()["id"])
    grandchild = await create_folder(client, regular_user_token, "grandchild", child.json()["id"])
    great_grandchild = await create_folder(
        client,
        regular_user_token,
        "great-grandchild",
        grandchild.json()["id"],
    )

    assert great_grandchild.status_code == 201
