from unittest.mock import AsyncMock, patch

import pytest

from app.chatbot.api_tools import call_user_api
from app.chatbot.tools import (
    ToolContext,
    _handle_create_folder,
    _handle_delete_asset,
    _handle_delete_folder,
    _handle_delete_tag,
    _handle_folder_tree,
    _handle_get_asset,
    _handle_list_assets,
    _handle_list_folders,
    _handle_list_tags,
    _handle_search_media_library,
    _handle_tag_asset,
    _handle_untag_asset,
    _handle_update_asset,
    _handle_update_folder,
    _handle_update_tag,
    create_builtin_registry,
)


@pytest.fixture
def ctx():
    return ToolContext(user_id="test-user-id")


class TestToolRegistration:
    def test_all_media_tools_registered(self):
        registry = create_builtin_registry()
        names = set(registry.list_all().keys())
        expected = {
            "list_folders",
            "create_folder",
            "update_folder",
            "delete_folder",
            "folder_tree",
            "list_assets",
            "get_asset",
            "update_asset",
            "delete_asset",
            "list_tags",
            "create_tag",
            "update_tag",
            "delete_tag",
            "tag_asset",
            "untag_asset",
            "search_media_library",
        }
        assert expected.issubset(names)


class TestSearchMediaLibrary:
    @pytest.mark.asyncio
    async def test_routes_through_call_user_api(self, ctx):
        with patch("app.chatbot.api_tools.call_user_api", new_callable=AsyncMock) as mock:
            mock.return_value = {"assets": [{"id": "a1", "name": "cat.png"}], "next_cursor": None}
            result = await _handle_search_media_library(ctx, {"query": "cat"})
            assert result["assets"][0]["name"] == "cat.png"
            mock.assert_awaited_once_with(ctx, "GET", "/media/assets", params={"search": "cat", "limit": 20})

    @pytest.mark.asyncio
    async def test_missing_query(self, ctx):
        result = await _handle_search_media_library(ctx, {})
        assert result["error"] == "missing_argument"

    @pytest.mark.asyncio
    async def test_with_file_type_filter(self, ctx):
        with patch("app.chatbot.api_tools.call_user_api", new_callable=AsyncMock) as mock:
            mock.return_value = {"assets": [], "next_cursor": None}
            result = await _handle_search_media_library(ctx, {"query": "dog", "file_type": "image"})
            assert result == {"assets": [], "next_cursor": None}
            mock.assert_awaited_once_with(
                ctx, "GET", "/media/assets", params={"search": "dog", "limit": 20, "file_type": "image"}
            )


class TestListAssetsPagination:
    @pytest.mark.asyncio
    async def test_pagination_defaults(self, ctx):
        with patch("app.chatbot.api_tools.call_user_api", new_callable=AsyncMock) as mock:
            mock.return_value = {"assets": [{"id": f"a{i}"} for i in range(20)], "next_cursor": "c1"}
            result = await _handle_list_assets(ctx, {})
            assert len(result["assets"]) == 20
            mock.assert_awaited_once_with(ctx, "GET", "/media/assets", params={"limit": 20, "offset": 0})

    @pytest.mark.asyncio
    async def test_pagination_second_page(self, ctx):
        with patch("app.chatbot.api_tools.call_user_api", new_callable=AsyncMock) as mock:
            mock.return_value = {"assets": [{"id": f"a{i}"} for i in range(5)], "next_cursor": None}
            result = await _handle_list_assets(ctx, {"limit": 20, "offset": 20})
            assert len(result["assets"]) == 5
            mock.assert_awaited_once_with(
                ctx, "GET", "/media/assets", params={"limit": 20, "offset": 20}
            )


class TestFolderCreateDeleteCycle:
    @pytest.mark.asyncio
    async def test_create_folder(self, ctx):
        with patch("app.chatbot.api_tools.call_user_api", new_callable=AsyncMock) as mock:
            mock.return_value = {"id": "folder-123", "name": "from-bot"}
            result = await _handle_create_folder(ctx, {"name": "from-bot"})
            assert result["id"] == "folder-123"
            mock.assert_awaited_once_with(ctx, "POST", "/media/folders", json_data={"name": "from-bot"})

    @pytest.mark.asyncio
    async def test_delete_folder(self, ctx):
        with patch("app.chatbot.api_tools.call_user_api", new_callable=AsyncMock) as mock:
            mock.return_value = {}
            result = await _handle_delete_folder(ctx, {"id": "folder-123"})
            assert "error" not in result
            mock.assert_awaited_once_with(ctx, "DELETE", "/media/folders/folder-123")

    @pytest.mark.asyncio
    async def test_create_then_list_no_longer_present(self, ctx):
        with patch("app.chatbot.api_tools.call_user_api", new_callable=AsyncMock) as mock:
            mock.side_effect = [
                {"id": "folder-123", "name": "from-bot"},
                {},
                [],
            ]
            create_result = await _handle_create_folder(ctx, {"name": "from-bot"})
            assert create_result["id"] == "folder-123"

            delete_result = await _handle_delete_folder(ctx, {"id": "folder-123"})
            assert "error" not in delete_result

            list_result = await _handle_list_folders(ctx, {})
            assert list_result == []


class TestListFolders:
    @pytest.mark.asyncio
    async def test_happy_path(self, ctx):
        with patch("app.chatbot.api_tools.call_user_api", new_callable=AsyncMock) as mock:
            mock.return_value = [{"id": "f1", "name": "Photos"}]
            result = await _handle_list_folders(ctx, {})
            assert result[0]["name"] == "Photos"
            mock.assert_awaited_once_with(ctx, "GET", "/media/folders", params={})

    @pytest.mark.asyncio
    async def test_with_parent_id(self, ctx):
        with patch("app.chatbot.api_tools.call_user_api", new_callable=AsyncMock) as mock:
            mock.return_value = []
            result = await _handle_list_folders(ctx, {"parent_id": "f1"})
            assert result == []
            mock.assert_awaited_once_with(ctx, "GET", "/media/folders", params={"parent_id": "f1"})


class TestUpdateFolder:
    @pytest.mark.asyncio
    async def test_rename(self, ctx):
        with patch("app.chatbot.api_tools.call_user_api", new_callable=AsyncMock) as mock:
            mock.return_value = {"id": "f1", "name": "New Name"}
            result = await _handle_update_folder(ctx, {"id": "f1", "name": "New Name"})
            assert result["name"] == "New Name"
            mock.assert_awaited_once_with(
                ctx, "PATCH", "/media/folders/f1", json_data={"name": "New Name"}
            )

    @pytest.mark.asyncio
    async def test_missing_id(self, ctx):
        result = await _handle_update_folder(ctx, {"name": "New Name"})
        assert result["error"] == "missing_argument"

    @pytest.mark.asyncio
    async def test_no_fields(self, ctx):
        result = await _handle_update_folder(ctx, {"id": "f1"})
        assert result["error"] == "missing_argument"


class TestFolderTree:
    @pytest.mark.asyncio
    async def test_happy_path(self, ctx):
        with patch("app.chatbot.api_tools.call_user_api", new_callable=AsyncMock) as mock:
            mock.return_value = [{"id": "f1", "name": "Root", "children": []}]
            result = await _handle_folder_tree(ctx, {})
            assert result[0]["name"] == "Root"
            mock.assert_awaited_once_with(ctx, "GET", "/media/folders/tree")


class TestGetAsset:
    @pytest.mark.asyncio
    async def test_happy_path(self, ctx):
        with patch("app.chatbot.api_tools.call_user_api", new_callable=AsyncMock) as mock:
            mock.return_value = {"id": "a1", "name": "video.mp4"}
            result = await _handle_get_asset(ctx, {"id": "a1"})
            assert result["name"] == "video.mp4"
            mock.assert_awaited_once_with(ctx, "GET", "/media/assets/a1")

    @pytest.mark.asyncio
    async def test_missing_id(self, ctx):
        result = await _handle_get_asset(ctx, {})
        assert result["error"] == "missing_argument"


class TestUpdateAsset:
    @pytest.mark.asyncio
    async def test_rename(self, ctx):
        with patch("app.chatbot.api_tools.call_user_api", new_callable=AsyncMock) as mock:
            mock.return_value = {"id": "a1", "name": "renamed.mp4"}
            result = await _handle_update_asset(ctx, {"id": "a1", "name": "renamed.mp4"})
            assert result["name"] == "renamed.mp4"
            mock.assert_awaited_once_with(
                ctx, "PATCH", "/media/assets/a1", json_data={"name": "renamed.mp4"}
            )

    @pytest.mark.asyncio
    async def test_missing_id(self, ctx):
        result = await _handle_update_asset(ctx, {"name": "x"})
        assert result["error"] == "missing_argument"


class TestDeleteAsset:
    @pytest.mark.asyncio
    async def test_happy_path(self, ctx):
        with patch("app.chatbot.api_tools.call_user_api", new_callable=AsyncMock) as mock:
            mock.return_value = {}
            result = await _handle_delete_asset(ctx, {"id": "a1"})
            assert "error" not in result
            mock.assert_awaited_once_with(ctx, "DELETE", "/media/assets/a1")

    @pytest.mark.asyncio
    async def test_missing_id(self, ctx):
        result = await _handle_delete_asset(ctx, {})
        assert result["error"] == "missing_argument"


class TestListTags:
    @pytest.mark.asyncio
    async def test_happy_path(self, ctx):
        with patch("app.chatbot.api_tools.call_user_api", new_callable=AsyncMock) as mock:
            mock.return_value = [{"id": "t1", "name": "favorite"}]
            result = await _handle_list_tags(ctx, {})
            assert result[0]["name"] == "favorite"
            mock.assert_awaited_once_with(ctx, "GET", "/media/tags")


class TestCreateTag:
    @pytest.mark.asyncio
    async def test_happy_path(self, ctx):
        with patch("app.chatbot.api_tools.call_user_api", new_callable=AsyncMock) as mock:
            mock.return_value = {"id": "t1", "name": "important", "color": "ff0000"}
            result = await _handle_create_folder(ctx, {"name": "important", "color": "ff0000"})
            assert result["name"] == "important"


class TestUpdateTag:
    @pytest.mark.asyncio
    async def test_rename(self, ctx):
        with patch("app.chatbot.api_tools.call_user_api", new_callable=AsyncMock) as mock:
            mock.return_value = {"id": "t1", "name": "urgent"}
            result = await _handle_update_tag(ctx, {"id": "t1", "name": "urgent"})
            assert result["name"] == "urgent"
            mock.assert_awaited_once_with(
                ctx, "PATCH", "/media/tags/t1", json_data={"name": "urgent"}
            )

    @pytest.mark.asyncio
    async def test_missing_id(self, ctx):
        result = await _handle_update_tag(ctx, {"name": "x"})
        assert result["error"] == "missing_argument"


class TestDeleteTag:
    @pytest.mark.asyncio
    async def test_happy_path(self, ctx):
        with patch("app.chatbot.api_tools.call_user_api", new_callable=AsyncMock) as mock:
            mock.return_value = {}
            result = await _handle_delete_tag(ctx, {"id": "t1"})
            assert "error" not in result
            mock.assert_awaited_once_with(ctx, "DELETE", "/media/tags/t1")


class TestTagAsset:
    @pytest.mark.asyncio
    async def test_happy_path(self, ctx):
        with patch("app.chatbot.api_tools.call_user_api", new_callable=AsyncMock) as mock:
            mock.return_value = {"tagged": 1}
            result = await _handle_tag_asset(ctx, {"asset_id": "a1", "tag_id": "t1"})
            assert result["tagged"] == 1
            mock.assert_awaited_once_with(
                ctx,
                "POST",
                "/media/assets/bulk/tag",
                json_data={"asset_ids": ["a1"], "tag_ids": ["t1"]},
            )

    @pytest.mark.asyncio
    async def test_missing_args(self, ctx):
        result = await _handle_tag_asset(ctx, {"asset_id": "a1"})
        assert result["error"] == "missing_argument"


class TestUntagAsset:
    @pytest.mark.asyncio
    async def test_happy_path(self, ctx):
        with patch("app.chatbot.api_tools.call_user_api", new_callable=AsyncMock) as mock:
            mock.return_value = {"tagged": 1}
            result = await _handle_untag_asset(ctx, {"asset_id": "a1", "tag_id": "t1"})
            assert result["tagged"] == 1
            mock.assert_awaited_once_with(
                ctx,
                "POST",
                "/media/assets/bulk/tag",
                json_data={"asset_ids": ["a1"], "tag_ids": []},
            )
