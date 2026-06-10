from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any, cast
from uuid import uuid4

import pytest
from starlette.websockets import WebSocketDisconnect

import app.main as main_module
from app.api.auth import TOKEN_COOKIE_NAME, create_access_token
from app.api.ws_auth import authenticate_websocket
from app.database import Conversation, Job, User


class FakeResult:
    def __init__(self, value: Any):
        self._value = value

    def scalar_one_or_none(self) -> Any:
        return self._value


class FakeDB:
    def __init__(self, value: Any):
        self.value = value
        self.executed = False

    async def execute(self, query: Any) -> FakeResult:
        self.executed = True
        return FakeResult(self.value)


class FakeWebSocket:
    def __init__(self, token: str | None = None, cookie_token: str | None = None):
        self.query_params: dict[str, str] = {} if token is None else {"token": token}
        self.cookies: dict[str, str] = {}
        if cookie_token is not None:
            self.cookies[TOKEN_COOKIE_NAME] = cookie_token
        self.accept_called = False
        self.close_calls: list[int | None] = []
        self.receive_calls = 0

    async def accept(self) -> None:
        self.accept_called = True

    async def close(self, code: int | None = None) -> None:
        self.close_calls.append(code)

    async def receive_text(self) -> str:
        self.receive_calls += 1
        raise WebSocketDisconnect(code=1000)


def _session_factory(db: FakeDB):
    @asynccontextmanager
    async def _session():
        yield db

    return _session


@pytest.fixture
def regular_user() -> User:
    return User(id=uuid4(), email="regular@example.com", hashed_password="x", is_active=True, is_superuser=False)


@pytest.fixture
def other_user() -> User:
    return User(id=uuid4(), email="other@example.com", hashed_password="x", is_active=True, is_superuser=False)


@pytest.fixture
def admin_user() -> User:
    return User(id=uuid4(), email="admin@example.com", hashed_password="x", is_active=True, is_superuser=True)


@pytest.fixture
def regular_user_token(regular_user: User) -> str:
    return create_access_token(data={"sub": str(regular_user.id)})


@pytest.fixture
def other_user_token(other_user: User) -> str:
    return create_access_token(data={"sub": str(other_user.id)})


@pytest.fixture
def conversation_for_user(regular_user: User) -> Conversation:
    return Conversation(id=uuid4(), user_id=regular_user.id, title="Test Chat", model_id="gpt-4")


@pytest.fixture
def job_for_user(regular_user: User) -> Job:
    return Job(id=uuid4(), user_id=regular_user.id, title="Test Job")


class TestAuthenticateWebSocket:
    @pytest.mark.asyncio
    async def test_no_credentials_returns_none(self):
        websocket: Any = SimpleNamespace(query_params={}, cookies={})
        assert await authenticate_websocket(websocket) is None

    @pytest.mark.asyncio
    async def test_query_token_authenticates_user(self, regular_user: User, regular_user_token: str):
        websocket: Any = SimpleNamespace(query_params={"token": regular_user_token}, cookies={})
        user = await authenticate_websocket(websocket, db=cast(Any, FakeDB(regular_user)))
        assert user is not None
        assert user.id == regular_user.id

    @pytest.mark.asyncio
    async def test_cookie_token_authenticates_user(self, regular_user: User, regular_user_token: str):
        websocket: Any = SimpleNamespace(query_params={}, cookies={TOKEN_COOKIE_NAME: regular_user_token})
        user = await authenticate_websocket(websocket, db=cast(Any, FakeDB(regular_user)))
        assert user is not None
        assert user.id == regular_user.id


class TestWSJobsAuth:
    @pytest.mark.asyncio
    async def test_no_credentials_rejected(self, job_for_user: Job, monkeypatch):
        websocket = FakeWebSocket()
        async def _auth(*args: Any, **kwargs: Any) -> None:
            return None

        monkeypatch.setattr(main_module, "authenticate_websocket", _auth)
        await main_module.websocket_job_updates(cast(Any, websocket), str(job_for_user.id))
        assert websocket.close_calls == [1008]
        assert websocket.accept_called is False

    @pytest.mark.asyncio
    async def test_valid_auth_accepted(self, regular_user: User, job_for_user: Job, monkeypatch):
        websocket = FakeWebSocket(token="ignored")
        db = FakeDB(job_for_user)
        async def _auth(*args: Any, **kwargs: Any) -> User:
            return regular_user

        async def _subscribe(*args: Any, **kwargs: Any) -> None:
            return None

        monkeypatch.setattr(main_module, "authenticate_websocket", _auth)
        monkeypatch.setattr(main_module, "async_session", _session_factory(db))
        monkeypatch.setattr(main_module.ws_manager, "subscribe_to_job", _subscribe)
        await main_module.websocket_job_updates(cast(Any, websocket), str(job_for_user.id))
        assert websocket.accept_called is True
        assert websocket.close_calls == []
        assert db.executed is True

    @pytest.mark.asyncio
    async def test_wrong_user_rejected(self, other_user: User, job_for_user: Job, monkeypatch):
        websocket = FakeWebSocket(token="ignored")
        db = FakeDB(None)
        async def _auth(*args: Any, **kwargs: Any) -> User:
            return other_user

        monkeypatch.setattr(main_module, "authenticate_websocket", _auth)
        monkeypatch.setattr(main_module, "async_session", _session_factory(db))
        await main_module.websocket_job_updates(cast(Any, websocket), str(job_for_user.id))
        assert websocket.close_calls == [1008]
        assert websocket.accept_called is False
        assert db.executed is True

    @pytest.mark.asyncio
    async def test_admin_bypass_allowed(self, admin_user: User, job_for_user: Job, monkeypatch):
        websocket = FakeWebSocket(token="ignored")
        db = FakeDB(None)
        async def _auth(*args: Any, **kwargs: Any) -> User:
            return admin_user

        async def _subscribe(*args: Any, **kwargs: Any) -> None:
            return None

        monkeypatch.setattr(main_module, "authenticate_websocket", _auth)
        monkeypatch.setattr(main_module, "async_session", _session_factory(db))
        monkeypatch.setattr(main_module.ws_manager, "subscribe_to_job", _subscribe)
        await main_module.websocket_job_updates(cast(Any, websocket), str(job_for_user.id))
        assert websocket.accept_called is True
        assert websocket.close_calls == []
        assert db.executed is False


class TestWSChatAuth:
    @pytest.mark.asyncio
    async def test_no_credentials_rejected(self, conversation_for_user: Conversation, monkeypatch):
        websocket = FakeWebSocket()
        async def _auth(*args: Any, **kwargs: Any) -> None:
            return None

        monkeypatch.setattr(main_module, "authenticate_websocket", _auth)
        await main_module.websocket_chat_updates(cast(Any, websocket), str(conversation_for_user.id))
        assert websocket.close_calls == [1008]
        assert websocket.accept_called is False

    @pytest.mark.asyncio
    async def test_valid_auth_accepted(self, regular_user: User, conversation_for_user: Conversation, monkeypatch):
        websocket = FakeWebSocket(token="ignored")
        db = FakeDB(conversation_for_user)
        async def _auth(*args: Any, **kwargs: Any) -> User:
            return regular_user

        async def _subscribe(*args: Any, **kwargs: Any) -> None:
            return None

        monkeypatch.setattr(main_module, "authenticate_websocket", _auth)
        monkeypatch.setattr(main_module, "async_session", _session_factory(db))
        monkeypatch.setattr(main_module.ws_manager, "subscribe_to_chat", _subscribe)
        await main_module.websocket_chat_updates(cast(Any, websocket), str(conversation_for_user.id))
        assert websocket.accept_called is True
        assert websocket.close_calls == [None]
        assert db.executed is True

    @pytest.mark.asyncio
    async def test_wrong_user_rejected(self, other_user: User, conversation_for_user: Conversation, monkeypatch):
        websocket = FakeWebSocket(token="ignored")
        db = FakeDB(None)
        async def _auth(*args: Any, **kwargs: Any) -> User:
            return other_user

        monkeypatch.setattr(main_module, "authenticate_websocket", _auth)
        monkeypatch.setattr(main_module, "async_session", _session_factory(db))
        await main_module.websocket_chat_updates(cast(Any, websocket), str(conversation_for_user.id))
        assert websocket.close_calls == [1008]
        assert websocket.accept_called is False
        assert db.executed is True

    @pytest.mark.asyncio
    async def test_admin_bypass_allowed(self, admin_user: User, conversation_for_user: Conversation, monkeypatch):
        websocket = FakeWebSocket(token="ignored")
        db = FakeDB(None)
        async def _auth(*args: Any, **kwargs: Any) -> User:
            return admin_user

        async def _subscribe(*args: Any, **kwargs: Any) -> None:
            return None

        monkeypatch.setattr(main_module, "authenticate_websocket", _auth)
        monkeypatch.setattr(main_module, "async_session", _session_factory(db))
        monkeypatch.setattr(main_module.ws_manager, "subscribe_to_chat", _subscribe)
        await main_module.websocket_chat_updates(cast(Any, websocket), str(conversation_for_user.id))
        assert websocket.accept_called is True
        assert websocket.close_calls == [None]
        assert db.executed is False
