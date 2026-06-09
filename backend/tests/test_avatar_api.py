"""Integration tests for the Avatar API.

Test the full HTTP request/response cycle using SQLite in-memory
(via the main conftest.py dependency overrides). No PostgreSQL required.

    pytest tests/test_avatar_api.py -v
"""

import io
import uuid as uuid_mod

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app

# ── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture
async def authenticated_client(regular_user_token):
    """Return an httpx AsyncClient authenticated as regular_user."""
    async with (
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac,
    ):
        ac.headers["Authorization"] = f"Bearer {regular_user_token}"
        yield ac


@pytest.fixture
async def other_client(superuser_token):
    """Return an httpx AsyncClient authenticated as superuser (different user)."""
    async with (
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac,
    ):
        ac.headers["Authorization"] = f"Bearer {superuser_token}"
        yield ac


def _make_png(width: int = 1, height: int = 1) -> bytes:
    """Create a minimal valid PNG in memory."""
    from PIL import Image as PILImage

    buf = io.BytesIO()
    img = PILImage.new("RGB", (width, height), color="red")
    img.save(buf, format="PNG")
    return buf.getvalue()


def _make_invalid_image_bytes() -> bytes:
    """Return bytes that are NOT a valid image."""
    return b"this is not an image file"


# ---------------------------------------------------------------------------
# POST /api/avatars — Create
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_avatar_success(authenticated_client):
    """POST /api/avatars with valid data returns 201 + avatar."""
    payload = {
        "name": "Test Avatar",
        "gender": "Female",
        "bio": "A test bio",
        "consistencyStrategy": "face_swap",
    }
    response = await authenticated_client.post("/api/avatars", json=payload)
    assert response.status_code == 201

    data = response.json()
    assert data["name"] == "Test Avatar"
    assert data["gender"] == "Female"
    assert data["bio"] == "A test bio"
    assert data["consistencyStrategy"] == "face_swap"
    assert "id" in data
    assert "userId" in data
    assert "images" in data
    assert data["images"] == []
    assert "createdAt" in data
    assert "updatedAt" in data


@pytest.mark.asyncio
async def test_create_avatar_default_strategy(authenticated_client):
    """POST /api/avatars without consistency_strategy defaults to ip_adapter."""
    payload = {"name": "Default Avatar", "gender": "Male"}
    response = await authenticated_client.post("/api/avatars", json=payload)
    assert response.status_code == 201
    assert response.json()["consistencyStrategy"] == "ip_adapter"


@pytest.mark.asyncio
async def test_create_avatar_invalid_gender(authenticated_client):
    """POST /api/avatars with invalid gender returns 422."""
    payload = {"name": "Bad", "gender": "InvalidGender"}
    response = await authenticated_client.post("/api/avatars", json=payload)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_avatar_invalid_consistency_strategy(authenticated_client):
    """POST /api/avatars with invalid consistency_strategy returns 422."""
    payload = {
        "name": "Bad Strategy",
        "gender": "Male",
        "consistencyStrategy": "invalid_strategy",
    }
    response = await authenticated_client.post("/api/avatars", json=payload)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_avatar_empty_name(authenticated_client):
    """POST /api/avatars with empty name returns 422."""
    payload = {"name": "", "gender": "Male"}
    response = await authenticated_client.post("/api/avatars", json=payload)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_avatar_no_auth(client):
    """POST /api/avatars without auth returns 401."""
    response = await client.post(
        "/api/avatars",
        json={"name": "Unauth", "gender": "Male"},
    )
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/avatars — List
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_avatars_empty(authenticated_client):
    """GET /api/avatars with no avatars returns empty list."""
    response = await authenticated_client.get("/api/avatars")
    assert response.status_code == 200
    data = response.json()
    assert data["avatars"] == []
    assert data["total"] == 0


@pytest.mark.asyncio
async def test_list_avatars_with_data(authenticated_client):
    """GET /api/avatars returns created avatars."""
    # Create two avatars
    await authenticated_client.post(
        "/api/avatars", json={"name": "Avatar 1", "gender": "Male"}
    )
    await authenticated_client.post(
        "/api/avatars", json={"name": "Avatar 2", "gender": "Female"}
    )

    response = await authenticated_client.get("/api/avatars")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    assert len(data["avatars"]) == 2
    names = {a["name"] for a in data["avatars"]}
    assert names == {"Avatar 1", "Avatar 2"}


@pytest.mark.asyncio
async def test_list_avatars_user_isolation(authenticated_client, other_client):
    """GET /api/avatars only returns the current user's avatars."""
    # Create avatar as regular_user
    await authenticated_client.post(
        "/api/avatars", json={"name": "Mine", "gender": "Male"}
    )

    # Other user sees empty list
    response = await other_client.get("/api/avatars")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0
    assert data["avatars"] == []

    # Original user sees their avatar
    response = await authenticated_client.get("/api/avatars")
    assert response.status_code == 200
    assert response.json()["total"] == 1


@pytest.mark.asyncio
async def test_list_avatars_no_auth(client):
    """GET /api/avatars without auth returns 401."""
    response = await client.get("/api/avatars")
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/avatars/{id} — Get single
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_avatar_success(authenticated_client):
    """GET /api/avatars/{id} returns the full avatar."""
    create_resp = await authenticated_client.post(
        "/api/avatars",
        json={"name": "My Avatar", "gender": "Non-binary", "bio": "bio text"},
    )
    avatar_id = create_resp.json()["id"]

    response = await authenticated_client.get(f"/api/avatars/{avatar_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == avatar_id
    assert data["name"] == "My Avatar"
    assert data["gender"] == "Non-binary"
    assert data["bio"] == "bio text"
    assert data["images"] == []


@pytest.mark.asyncio
async def test_get_avatar_not_found(authenticated_client):
    """GET /api/avatars/{id} with non-existent id returns 404."""
    fake_id = str(uuid_mod.uuid4())
    response = await authenticated_client.get(f"/api/avatars/{fake_id}")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_avatar_other_user(authenticated_client, other_client):
    """GET /api/avatars/{id} for another user's avatar returns 404."""
    create_resp = await authenticated_client.post(
        "/api/avatars", json={"name": "Mine", "gender": "Male"}
    )
    avatar_id = create_resp.json()["id"]

    # Other user cannot access
    response = await other_client.get(f"/api/avatars/{avatar_id}")
    assert response.status_code == 404

    # Owner still can
    response = await authenticated_client.get(f"/api/avatars/{avatar_id}")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_get_avatar_no_auth(client):
    """GET /api/avatars/{id} without auth returns 401."""
    fake_id = str(uuid_mod.uuid4())
    response = await client.get(f"/api/avatars/{fake_id}")
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# PUT /api/avatars/{id} — Update
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_avatar_success(authenticated_client):
    """PUT /api/avatars/{id} updates specified fields."""
    create_resp = await authenticated_client.post(
        "/api/avatars", json={"name": "Original", "gender": "Male"}
    )
    avatar_id = create_resp.json()["id"]

    response = await authenticated_client.put(
        f"/api/avatars/{avatar_id}",
        json={"name": "Updated", "bio": "New bio"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Updated"
    assert data["bio"] == "New bio"
    assert data["gender"] == "Male"  # unchanged


@pytest.mark.asyncio
async def test_update_avatar_other_user(authenticated_client, other_client):
    """PUT /api/avatars/{id} for another user's avatar returns 404."""
    create_resp = await authenticated_client.post(
        "/api/avatars", json={"name": "Mine", "gender": "Male"}
    )
    avatar_id = create_resp.json()["id"]

    response = await other_client.put(
        f"/api/avatars/{avatar_id}",
        json={"name": "Hijacked"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_avatar_no_auth(client):
    """PUT /api/avatars/{id} without auth returns 401."""
    fake_id = str(uuid_mod.uuid4())
    response = await client.put(
        f"/api/avatars/{fake_id}", json={"name": "X"}
    )
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# DELETE /api/avatars/{id} — Soft delete
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_avatar_success(authenticated_client):
    """DELETE /api/avatars/{id} returns 204 and soft-deletes."""
    create_resp = await authenticated_client.post(
        "/api/avatars", json={"name": "To Delete", "gender": "Male"}
    )
    avatar_id = create_resp.json()["id"]

    response = await authenticated_client.delete(f"/api/avatars/{avatar_id}")
    assert response.status_code == 204
    assert response.content == b""  # 204 has no body


@pytest.mark.asyncio
async def test_delete_avatar_hidden_from_list(authenticated_client):
    """Deleted avatar is not returned by GET /api/avatars."""
    create_resp = await authenticated_client.post(
        "/api/avatars", json={"name": "Gone", "gender": "Male"}
    )
    avatar_id = create_resp.json()["id"]

    # Delete it
    await authenticated_client.delete(f"/api/avatars/{avatar_id}")

    # List should be empty
    response = await authenticated_client.get("/api/avatars")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0
    assert data["avatars"] == []


@pytest.mark.asyncio
async def test_delete_avatar_other_user(authenticated_client, other_client):
    """DELETE /api/avatars/{id} for another user's avatar returns 404."""
    create_resp = await authenticated_client.post(
        "/api/avatars", json={"name": "Mine", "gender": "Male"}
    )
    avatar_id = create_resp.json()["id"]

    response = await other_client.delete(f"/api/avatars/{avatar_id}")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_avatar_not_found(authenticated_client):
    """DELETE /api/avatars/{id} with non-existent id returns 404."""
    fake_id = str(uuid_mod.uuid4())
    response = await authenticated_client.delete(f"/api/avatars/{fake_id}")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_avatar_no_auth(client):
    """DELETE /api/avatars/{id} without auth returns 401."""
    fake_id = str(uuid_mod.uuid4())
    response = await client.delete(f"/api/avatars/{fake_id}")
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# POST /api/avatars/{id}/images — Upload image
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upload_image_success(authenticated_client):
    """POST /api/avatars/{id}/images with valid PNG returns 201."""
    create_resp = await authenticated_client.post(
        "/api/avatars", json={"name": "With Image", "gender": "Male"}
    )
    avatar_id = create_resp.json()["id"]

    png_bytes = _make_png(64, 64)
    response = await authenticated_client.post(
        f"/api/avatars/{avatar_id}/images",
        files={"file": ("test.png", png_bytes, "image/png")},
    )
    assert response.status_code == 201
    data = response.json()
    assert "id" in data
    assert data["storagePath"].startswith("avatars/")
    assert data["isPrimary"] is True  # first image is primary
    assert data["sortOrder"] >= 1


@pytest.mark.asyncio
async def test_upload_image_non_image_content_type(authenticated_client):
    """POST /api/avatars/{id}/images with text/plain returns 422."""
    create_resp = await authenticated_client.post(
        "/api/avatars", json={"name": "Image Test", "gender": "Male"}
    )
    avatar_id = create_resp.json()["id"]

    response = await authenticated_client.post(
        f"/api/avatars/{avatar_id}/images",
        files={"file": ("test.txt", b"not-an-image", "text/plain")},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_upload_image_invalid_file_data(authenticated_client):
    """POST /api/avatars/{id}/images with invalid image bytes returns 422."""
    create_resp = await authenticated_client.post(
        "/api/avatars", json={"name": "Bad Image", "gender": "Male"}
    )
    avatar_id = create_resp.json()["id"]

    response = await authenticated_client.post(
        f"/api/avatars/{avatar_id}/images",
        files={"file": ("fake.png", _make_invalid_image_bytes(), "image/png")},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_upload_image_no_auth(client):
    """POST /api/avatars/{id}/images without auth returns 401."""
    fake_id = str(uuid_mod.uuid4())
    response = await client.post(
        f"/api/avatars/{fake_id}/images",
        files={"file": ("test.png", _make_png(), "image/png")},
    )
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# PUT /api/avatars/{id}/images/{image_id}/primary — Set primary image
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_set_primary_image_success(authenticated_client):
    """PUT .../primary marks the specified image as primary."""
    create_resp = await authenticated_client.post(
        "/api/avatars", json={"name": "Primary Test", "gender": "Male"}
    )
    avatar_id = create_resp.json()["id"]

    # Upload two images
    img1 = await authenticated_client.post(
        f"/api/avatars/{avatar_id}/images",
        files={"file": ("img1.png", _make_png(), "image/png")},
    )
    img1_id = img1.json()["id"]
    assert img1.json()["isPrimary"] is True  # first is auto-primary

    img2 = await authenticated_client.post(
        f"/api/avatars/{avatar_id}/images",
        files={"file": ("img2.png", _make_png(2, 2), "image/png")},
    )
    img2_id = img2.json()["id"]
    assert img2.json()["isPrimary"] is False  # second is not

    # Set img2 as primary
    response = await authenticated_client.put(
        f"/api/avatars/{avatar_id}/images/{img2_id}/primary",
    )
    assert response.status_code == 200
    data = response.json()

    # Verify img2 is now primary in the response
    imgs = {img["id"]: img for img in data["images"]}
    assert imgs[img2_id]["isPrimary"] is True
    assert imgs[img1_id]["isPrimary"] is False
    assert data["primaryImageId"] == img2_id


@pytest.mark.asyncio
async def test_set_primary_image_not_found(authenticated_client):
    """PUT .../primary with non-existent image returns 404."""
    create_resp = await authenticated_client.post(
        "/api/avatars", json={"name": "Primary 404", "gender": "Male"}
    )
    avatar_id = create_resp.json()["id"]

    fake_image_id = str(uuid_mod.uuid4())
    response = await authenticated_client.put(
        f"/api/avatars/{avatar_id}/images/{fake_image_id}/primary",
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_set_primary_image_no_auth(client):
    """PUT .../primary without auth returns 401."""
    fake_avatar = str(uuid_mod.uuid4())
    fake_image = str(uuid_mod.uuid4())
    response = await client.put(
        f"/api/avatars/{fake_avatar}/images/{fake_image}/primary",
    )
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# DELETE /api/avatars/{id}/images/{image_id} — Delete image
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_image_success(authenticated_client):
    """DELETE .../images/{id} returns 204 and removes the image."""
    create_resp = await authenticated_client.post(
        "/api/avatars", json={"name": "Delete Image", "gender": "Male"}
    )
    avatar_id = create_resp.json()["id"]

    upload_resp = await authenticated_client.post(
        f"/api/avatars/{avatar_id}/images",
        files={"file": ("img.png", _make_png(), "image/png")},
    )
    image_id = upload_resp.json()["id"]

    response = await authenticated_client.delete(
        f"/api/avatars/{avatar_id}/images/{image_id}",
    )
    assert response.status_code == 204

    # Verify image is gone from the avatar
    get_resp = await authenticated_client.get(f"/api/avatars/{avatar_id}")
    assert get_resp.json()["images"] == []


@pytest.mark.asyncio
async def test_delete_image_not_found(authenticated_client):
    """DELETE .../images/{id} with non-existent image returns 404."""
    create_resp = await authenticated_client.post(
        "/api/avatars", json={"name": "Img 404", "gender": "Male"}
    )
    avatar_id = create_resp.json()["id"]

    fake_image_id = str(uuid_mod.uuid4())
    response = await authenticated_client.delete(
        f"/api/avatars/{avatar_id}/images/{fake_image_id}",
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_image_other_user(authenticated_client, other_client):
    """DELETE .../images/{id} for another user's avatar returns 404."""
    create_resp = await authenticated_client.post(
        "/api/avatars", json={"name": "My Avatar", "gender": "Male"}
    )
    avatar_id = create_resp.json()["id"]

    upload_resp = await authenticated_client.post(
        f"/api/avatars/{avatar_id}/images",
        files={"file": ("img.png", _make_png(), "image/png")},
    )
    image_id = upload_resp.json()["id"]

    response = await other_client.delete(
        f"/api/avatars/{avatar_id}/images/{image_id}",
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_image_no_auth(client):
    """DELETE .../images/{id} without auth returns 401."""
    fake_avatar = str(uuid_mod.uuid4())
    fake_image = str(uuid_mod.uuid4())
    response = await client.delete(
        f"/api/avatars/{fake_avatar}/images/{fake_image}",
    )
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# Edge cases: boundary values
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_avatar_long_name(authenticated_client):
    """POST /api/avatars with a long but valid name succeeds."""
    long_name = "A" * 255
    response = await authenticated_client.post(
        "/api/avatars", json={"name": long_name, "gender": "Other"}
    )
    assert response.status_code == 201
    assert response.json()["name"] == long_name


@pytest.mark.asyncio
async def test_create_avatar_minimal_fields(authenticated_client):
    """POST /api/avatars with only required fields creates avatar."""
    response = await authenticated_client.post(
        "/api/avatars", json={"name": "Min", "gender": "Male"}
    )
    assert response.status_code == 201
    data = response.json()
    assert data["bio"] is None
    assert data["consistencyStrategy"] == "ip_adapter"


@pytest.mark.asyncio
async def test_update_avatar_noop(authenticated_client):
    """PUT /api/avatars/{id} with empty body is a no-op."""
    create_resp = await authenticated_client.post(
        "/api/avatars", json={"name": "Noop", "gender": "Male"}
    )
    avatar_id = create_resp.json()["id"]

    response = await authenticated_client.put(
        f"/api/avatars/{avatar_id}", json={}
    )
    assert response.status_code == 200
    assert response.json()["name"] == "Noop"


@pytest.mark.asyncio
async def test_update_avatar_validation(authenticated_client):
    """PUT /api/avatars/{id} with empty name returns 422."""
    create_resp = await authenticated_client.post(
        "/api/avatars", json={"name": "Valid", "gender": "Male"}
    )
    avatar_id = create_resp.json()["id"]

    response = await authenticated_client.put(
        f"/api/avatars/{avatar_id}", json={"name": ""}
    )
    assert response.status_code == 422
