"""Integration tests for notification API endpoints and WebSocket.

Requires: PostgreSQL running at INTEGRATION_DATABASE_URL.
Run with: pytest tests/integration/test_notifications_api.py -v

Tests:
- User GET /notifications returns only own events
- User cannot see system events
- Admin GET /admin/notifications returns all
- Admin can see details
- Non-admin gets 403 on admin endpoints
- Mark as read works
- Mark all as read works
- WS rejects invalid token
- WS accepts valid token
"""

import pytest
from uuid import uuid4

from app.database import ErrorEvent, ErrorOrigin, ErrorSeverity
from app.services.error_capture import log_user_error, log_system_error

pytestmark = pytest.mark.integration


# ── Helper Fixtures ────────────────────────────────────────────────────────


@pytest.fixture
async def regular_user(db_session):
    """Create a regular (non-admin) user with unique email."""
    from passlib.context import CryptContext
    from app.database import User

    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    unique_email = f"regular_{uuid4().hex[:8]}@example.com"
    user = User(
        id=uuid4(),
        email=unique_email,
        hashed_password=pwd_context.hash("password123"),
        is_active=True,
        is_superuser=False,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
def regular_user_token(regular_user):
    from app.api.auth import create_access_token
    return create_access_token(data={"sub": str(regular_user.id)})


@pytest.fixture
async def second_user(db_session):
    """Create a second regular user for isolation tests."""
    from passlib.context import CryptContext
    from app.database import User

    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    unique_email = f"second_{uuid4().hex[:8]}@example.com"
    user = User(
        id=uuid4(),
        email=unique_email,
        hashed_password=pwd_context.hash("password123"),
        is_active=True,
        is_superuser=False,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
def second_user_token(second_user):
    from app.api.auth import create_access_token
    return create_access_token(data={"sub": str(second_user.id)})


@pytest.fixture
async def admin_user(db_session):
    """Create an admin user with unique email."""
    from passlib.context import CryptContext
    from app.database import User

    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    unique_email = f"admin_{uuid4().hex[:8]}@example.com"
    user = User(
        id=uuid4(),
        email=unique_email,
        hashed_password=pwd_context.hash("admin123"),
        is_active=True,
        is_superuser=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
def admin_token(admin_user):
    from app.api.auth import create_access_token
    return create_access_token(data={"sub": str(admin_user.id)})


@pytest.fixture
async def user_event(db_session, regular_user):
    """Create an error event for the regular user."""
    event = await log_user_error(
        db_session,
        user_id=regular_user.id,
        severity=ErrorSeverity.ERROR,
        origin=ErrorOrigin.MEDIA_GENERATION,
        message="User test error",
        details={"provider": "test"},
    )
    return event


@pytest.fixture
async def system_event(db_session):
    """Create a system error event (user_id=None)."""
    event = await log_system_error(
        db_session,
        severity=ErrorSeverity.CRITICAL,
        origin=ErrorOrigin.SYSTEM,
        message="System test error",
        details={"component": "test"},
    )
    return event


@pytest.fixture
async def authenticated_client(integration_client, regular_user_token):
    """Client authenticated as regular user."""
    integration_client.headers["Authorization"] = f"Bearer {regular_user_token}"
    return integration_client


@pytest.fixture
async def admin_client(integration_client, admin_token):
    """Client authenticated as admin user."""
    integration_client.headers["Authorization"] = f"Bearer {admin_token}"
    return integration_client


@pytest.fixture
async def client(db_session):
    """Unauthenticated client."""
    from httpx import ASGITransport, AsyncClient
    from app.main import app
    from app.database import get_db

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac
    app.dependency_overrides.clear()


# ── User Endpoint Tests ────────────────────────────────────────────────────


class TestUserNotifications:
    """Tests for GET /api/notifications (user-facing)."""

    @pytest.mark.asyncio
    async def test_user_sees_own_events(self, authenticated_client, regular_user, user_event):
        """User can see their own error events."""
        response = await authenticated_client.get("/api/notifications")
        assert response.status_code == 200
        data = response.json()
        
        assert data["total"] >= 1
        assert len(data["items"]) >= 1
        
        # Verify the event is present
        event_ids = [item["id"] for item in data["items"]]
        assert str(user_event.id) in event_ids

    @pytest.mark.asyncio
    async def test_user_cannot_see_other_users_events(
        self, authenticated_client, db_session, second_user
    ):
        """User cannot see events belonging to other users."""
        # Create an event for the second user
        await log_user_error(
            db_session,
            user_id=second_user.id,
            severity=ErrorSeverity.ERROR,
            origin=ErrorOrigin.LLM,
            message="Other user's error",
        )

        response = await authenticated_client.get("/api/notifications")
        assert response.status_code == 200
        data = response.json()
        
        # Should not contain the other user's event
        for item in data["items"]:
            assert item["userId"] != str(second_user.id)

    @pytest.mark.asyncio
    async def test_user_cannot_see_system_events(
        self, authenticated_client, system_event
    ):
        """Regular users cannot see system events (user_id=None)."""
        response = await authenticated_client.get("/api/notifications")
        assert response.status_code == 200
        data = response.json()
        
        # System events should not be in the response
        for item in data["items"]:
            assert item["userId"] is not None

    @pytest.mark.asyncio
    async def test_user_response_excludes_details(
        self, authenticated_client, user_event
    ):
        """User-facing response does not include the details field."""
        response = await authenticated_client.get("/api/notifications")
        assert response.status_code == 200
        data = response.json()
        
        # Find our event
        event_data = next(
            (item for item in data["items"] if item["id"] == str(user_event.id)),
            None
        )
        assert event_data is not None
        
        # Details should not be present in user response
        assert "details" not in event_data

    @pytest.mark.asyncio
    async def test_unread_count(self, authenticated_client, user_event):
        """Unread count reflects unread events."""
        response = await authenticated_client.get("/api/notifications/unread-count")
        assert response.status_code == 200
        data = response.json()
        
        assert "unreadCount" in data
        assert data["unreadCount"] >= 1

    @pytest.mark.asyncio
    async def test_filter_by_severity(self, authenticated_client, db_session, regular_user):
        """Filtering by severity works correctly."""
        # Create events with different severities
        await log_user_error(
            db_session,
            user_id=regular_user.id,
            severity=ErrorSeverity.WARNING,
            origin=ErrorOrigin.SYSTEM,
            message="Warning event",
        )
        await log_user_error(
            db_session,
            user_id=regular_user.id,
            severity=ErrorSeverity.ERROR,
            origin=ErrorOrigin.SYSTEM,
            message="Error event",
        )

        response = await authenticated_client.get(
            "/api/notifications", params={"severity": ["warning"]}
        )
        assert response.status_code == 200
        data = response.json()
        
        for item in data["items"]:
            assert item["severity"] == "warning"

    @pytest.mark.asyncio
    async def test_filter_unread_only(self, authenticated_client, db_session, regular_user):
        """Filtering unread_only works correctly."""
        # Create an unread event
        unread_event = await log_user_error(
            db_session,
            user_id=regular_user.id,
            severity=ErrorSeverity.INFO,
            origin=ErrorOrigin.SYSTEM,
            message="Unread event",
        )

        # Query with unreadOnly filter
        response = await authenticated_client.get(
            "/api/notifications", params={"unreadOnly": True}
        )
        assert response.status_code == 200
        data = response.json()
        
        # The unread event should be in the results
        event_ids = [item["id"] for item in data["items"]]
        assert str(unread_event.id) in event_ids
        
        # All returned items should be unread
        for item in data["items"]:
            assert item["readAt"] is None

    @pytest.mark.asyncio
    async def test_pagination(self, authenticated_client, db_session, regular_user):
        """Pagination works correctly."""
        # Create multiple events
        for i in range(5):
            await log_user_error(
                db_session,
                user_id=regular_user.id,
                severity=ErrorSeverity.INFO,
                origin=ErrorOrigin.SYSTEM,
                message=f"Event {i}",
            )

        response = await authenticated_client.get(
            "/api/notifications", params={"limit": 2, "offset": 0}
        )
        assert response.status_code == 200
        data = response.json()
        
        assert len(data["items"]) == 2
        assert data["total"] >= 5


# ── Mark as Read Tests ─────────────────────────────────────────────────────


class TestMarkAsRead:
    """Tests for POST /api/notifications/{id}/read and /mark-all-read."""

    @pytest.mark.asyncio
    async def test_mark_single_as_read(self, authenticated_client, user_event):
        """Marking a single notification as read works."""
        response = await authenticated_client.post(
            f"/api/notifications/{user_event.id}/read"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

        # Verify it's marked as read
        response = await authenticated_client.get("/api/notifications")
        event_data = next(
            (item for item in response.json()["items"] if item["id"] == str(user_event.id)),
            None
        )
        assert event_data is not None
        assert event_data["readAt"] is not None

    @pytest.mark.asyncio
    async def test_mark_all_as_read(self, authenticated_client, db_session, regular_user):
        """Marking all notifications as read works."""
        # Create multiple unread events
        for i in range(3):
            await log_user_error(
                db_session,
                user_id=regular_user.id,
                severity=ErrorSeverity.INFO,
                origin=ErrorOrigin.SYSTEM,
                message=f"Unread {i}",
            )

        response = await authenticated_client.post("/api/notifications/mark-all-read")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

        # Verify all are marked as read
        response = await authenticated_client.get("/api/notifications/unread-count")
        assert response.json()["unreadCount"] == 0

    @pytest.mark.asyncio
    async def test_cannot_mark_other_users_event(
        self, authenticated_client, db_session, second_user
    ):
        """User cannot mark another user's event as read."""
        # Create an event for the second user
        other_event = await log_user_error(
            db_session,
            user_id=second_user.id,
            severity=ErrorSeverity.ERROR,
            origin=ErrorOrigin.SYSTEM,
            message="Other user's event",
        )

        # Try to mark it as read (should fail with 404)
        response = await authenticated_client.post(
            f"/api/notifications/{other_event.id}/read"
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_mark_nonexistent_event(self, authenticated_client):
        """Marking a non-existent event returns 404."""
        fake_id = uuid4()
        response = await authenticated_client.post(
            f"/api/notifications/{fake_id}/read"
        )
        assert response.status_code == 404


# ── Admin Endpoint Tests ───────────────────────────────────────────────────


class TestAdminNotifications:
    """Tests for GET /api/admin/notifications (admin-facing)."""

    @pytest.mark.asyncio
    async def test_admin_sees_all_events(
        self, admin_client, regular_user, second_user, db_session
    ):
        """Admin can see events from all users."""
        # Create events for different users
        user1_event = await log_user_error(
            db_session,
            user_id=regular_user.id,
            severity=ErrorSeverity.ERROR,
            origin=ErrorOrigin.MEDIA_GENERATION,
            message="User 1 error",
        )
        user2_event = await log_user_error(
            db_session,
            user_id=second_user.id,
            severity=ErrorSeverity.WARNING,
            origin=ErrorOrigin.LLM,
            message="User 2 error",
        )
        system_evt = await log_system_error(
            db_session,
            severity=ErrorSeverity.CRITICAL,
            origin=ErrorOrigin.SYSTEM,
            message="System error",
        )

        response = await admin_client.get("/api/admin/notifications")
        assert response.status_code == 200
        data = response.json()
        
        event_ids = [item["id"] for item in data["items"]]
        assert str(user1_event.id) in event_ids
        assert str(user2_event.id) in event_ids
        assert str(system_evt.id) in event_ids

    @pytest.mark.asyncio
    async def test_admin_sees_system_events(self, admin_client, system_event):
        """Admin can see system events (user_id=None)."""
        response = await admin_client.get("/api/admin/notifications")
        assert response.status_code == 200
        data = response.json()
        
        # Find the system event
        system_events = [item for item in data["items"] if item["userId"] is None]
        assert len(system_events) >= 1

    @pytest.mark.asyncio
    async def test_admin_sees_details(self, admin_client, user_event):
        """Admin endpoint includes the details field."""
        response = await admin_client.get(f"/api/admin/notifications/{user_event.id}")
        assert response.status_code == 200
        data = response.json()
        
        assert "details" in data
        assert data["details"] == {"provider": "test"}

    @pytest.mark.asyncio
    async def test_admin_filter_by_user(self, admin_client, db_session, regular_user):
        """Admin can filter events by user_id."""
        # Create an event for the regular user
        user_event = await log_user_error(
            db_session,
            user_id=regular_user.id,
            severity=ErrorSeverity.ERROR,
            origin=ErrorOrigin.SYSTEM,
            message="User event for filter test",
        )

        response = await admin_client.get(
            "/api/admin/notifications", params={"userId": str(regular_user.id)}
        )
        assert response.status_code == 200
        data = response.json()
        
        # The user's event should be in the results
        event_ids = [item["id"] for item in data["items"]]
        assert str(user_event.id) in event_ids
        
        # Verify the event has the correct userId
        user_event_data = next(
            (item for item in data["items"] if item["id"] == str(user_event.id)),
            None
        )
        assert user_event_data is not None
        assert user_event_data["userId"] == str(regular_user.id)

    @pytest.mark.asyncio
    async def test_admin_delete_event(self, admin_client, db_session, regular_user):
        """Admin can delete an error event."""
        event = await log_user_error(
            db_session,
            user_id=regular_user.id,
            severity=ErrorSeverity.INFO,
            origin=ErrorOrigin.SYSTEM,
            message="To be deleted",
        )

        response = await admin_client.delete(f"/api/admin/notifications/{event.id}")
        assert response.status_code == 200
        assert response.json()["success"] is True

        # Verify it's deleted
        response = await admin_client.get(f"/api/admin/notifications/{event.id}")
        assert response.status_code == 404


# ── Admin Access Control Tests ─────────────────────────────────────────────


class TestAdminAccessControl:
    """Tests for admin endpoint access control."""

    @pytest.mark.asyncio
    async def test_non_admin_gets_403(self, authenticated_client, user_event):
        """Non-admin users get 403 on admin endpoints."""
        response = await authenticated_client.get("/api/admin/notifications")
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_non_admin_cannot_see_details(self, authenticated_client, user_event):
        """Non-admin users cannot access admin detail endpoint."""
        response = await authenticated_client.get(
            f"/api/admin/notifications/{user_event.id}"
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_non_admin_cannot_delete(self, authenticated_client, user_event):
        """Non-admin users cannot delete events via admin endpoint."""
        response = await authenticated_client.delete(
            f"/api/admin/notifications/{user_event.id}"
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_unauthenticated_gets_401(self, client, user_event):
        """Unauthenticated requests get 401."""
        response = await client.get("/api/notifications")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_unauthenticated_admin_gets_401(self, client):
        """Unauthenticated requests to admin endpoint get 401."""
        response = await client.get("/api/admin/notifications")
        assert response.status_code == 401



@pytest.fixture
def ws_server_available():
    """Check if WebSocket server is running on localhost:8000."""
    import socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(1)
    try:
        sock.connect(("localhost", 8000))
        return True
    except (socket.timeout, ConnectionRefusedError, OSError):
        return False
    finally:
        sock.close()


# ── WebSocket Authentication Tests ─────────────────────────────────────────


class TestWebSocketAuth:
    """Tests for WebSocket authentication at /ws/notifications."""

    @pytest.mark.asyncio
    async def test_ws_rejects_no_token(self, ws_server_available):
        """WebSocket rejects connections without a token."""
        if not ws_server_available:
            pytest.skip("WebSocket server not running on localhost:8000")
        from websockets.asyncio.client import connect
        from websockets.exceptions import InvalidStatus
        
        with pytest.raises(InvalidStatus) as exc_info:
            async with connect("ws://localhost:8000/ws/notifications"):
                pass
        
        # InvalidStatus raised - connection was rejected (status code varies by websockets version)

    @pytest.mark.asyncio
    async def test_ws_rejects_invalid_token(self, ws_server_available):
        """WebSocket rejects connections with invalid token."""
        if not ws_server_available:
            pytest.skip("WebSocket server not running on localhost:8000")
        from websockets.asyncio.client import connect
        from websockets.exceptions import InvalidStatus
        
        with pytest.raises(InvalidStatus) as exc_info:
            async with connect(
                "ws://localhost:8000/ws/notifications?token=invalid_token"
            ):
                pass
        
        # InvalidStatus raised - connection was rejected (status code varies by websockets version)

    @pytest.mark.asyncio
    async def test_ws_accepts_valid_token(self, ws_server_available):
        """WebSocket accepts connections with valid token."""
        if not ws_server_available:
            pytest.skip("WebSocket server not running on localhost:8000")
        from websockets.asyncio.client import connect
        from app.api.auth import create_access_token
        from app.database import async_session, User
        from sqlalchemy import select
        
        async with async_session() as db:
            result = await db.execute(select(User).limit(1))
            user = result.scalar_one_or_none()
        
        if user is None:
            pytest.skip("No users in main database — skipping WS auth test")
        
        token = create_access_token(data={"sub": str(user.id)})
        
        # Should connect successfully
        async with connect(
            f"ws://localhost:8000/ws/notifications?token={token}"
        ) as ws:
            # Connection established - send a ping to verify
            await ws.ping()
            # If we get here, auth succeeded

    @pytest.mark.asyncio
    async def test_ws_rejects_expired_token(self, ws_server_available):
        """WebSocket rejects connections with expired token."""
        if not ws_server_available:
            pytest.skip("WebSocket server not running on localhost:8000")
        from websockets.asyncio.client import connect
        from websockets.exceptions import InvalidStatus
        from datetime import datetime, timedelta
        from jose import jwt
        from app.config import get_settings
        
        settings = get_settings()
        # Create an expired token
        expired_payload = {
            "sub": str(uuid4()),
            "exp": datetime.utcnow() - timedelta(hours=1),
        }
        expired_token = jwt.encode(
            expired_payload, settings.secret_key, algorithm=settings.algorithm
        )
        
        with pytest.raises(InvalidStatus) as exc_info:
            async with connect(
                f"ws://localhost:8000/ws/notifications?token={expired_token}"
            ):
                pass
        
        # InvalidStatus raised - connection was rejected (status code varies by websockets version)
