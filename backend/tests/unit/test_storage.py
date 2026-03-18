import pytest
import tempfile
import os
from pathlib import Path
from app.storage.local import LocalStorage


class TestLocalStorageSecurity:
    """Critical security tests for local storage backend."""

    @pytest.mark.asyncio
    async def test_path_traversal_attack_with_dotdot(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = LocalStorage(tmpdir)

            with pytest.raises(ValueError, match="Path traversal detected"):
                await storage.upload("../../../etc/passwd", b"malicious")

    @pytest.mark.asyncio
    async def test_path_traversal_attack_with_absolute_path(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = LocalStorage(tmpdir)

            with pytest.raises(ValueError, match="Path traversal detected"):
                await storage.upload("/etc/passwd", b"malicious")

    @pytest.mark.asyncio
    async def test_path_traversal_attack_with_symlink(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir)
            storage = LocalStorage(str(base_dir))

            outside_dir = base_dir.parent / "outside_test"
            outside_dir.mkdir(exist_ok=True)
            target_file = outside_dir / "secret.txt"
            target_file.write_text("secret data")

            symlink_path = base_dir / "malicious_link"
            try:
                symlink_path.symlink_to(outside_dir)

                with pytest.raises(ValueError):
                    await storage.download("malicious_link/secret.txt")
            finally:
                if symlink_path.exists():
                    symlink_path.unlink()
                if target_file.exists():
                    target_file.unlink()
                outside_dir.rmdir()

    @pytest.mark.asyncio
    async def test_upload_creates_file_in_correct_location(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = LocalStorage(tmpdir)
            content = b"test content"
            result = await storage.upload("test.txt", content)

            assert result == "test.txt"
            downloaded = await storage.download("test.txt")
            assert downloaded == content

    @pytest.mark.asyncio
    async def test_download_restricted_to_base_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = LocalStorage(tmpdir)

            with pytest.raises(FileNotFoundError):
                await storage.download("../outside_file.txt")

    @pytest.mark.asyncio
    async def test_upload_to_nested_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = LocalStorage(tmpdir)
            content = b"nested content"
            result = await storage.upload("subdir/nested/test.txt", content)

            assert result == "subdir/nested/test.txt"
            downloaded = await storage.download("subdir/nested/test.txt")
            assert downloaded == content


class TestLocalStorageOperations:
    """Functional tests for local storage."""

    @pytest.mark.asyncio
    async def test_upload_creates_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = LocalStorage(tmpdir)
            content = b"Hello, World!"
            result = await storage.upload("test.txt", content)

            assert result == "test.txt"
            downloaded = await storage.download("test.txt")
            assert downloaded == content

    @pytest.mark.asyncio
    async def test_download_retrieves_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = LocalStorage(tmpdir)
            content = b"Test content"
            await storage.upload("file.txt", content)

            downloaded = await storage.download("file.txt")
            assert downloaded == content

    @pytest.mark.asyncio
    async def test_download_nonexistent_file_raises_error(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = LocalStorage(tmpdir)
            with pytest.raises(FileNotFoundError, match="File not found"):
                await storage.download("nonexistent.txt")

    @pytest.mark.asyncio
    async def test_delete_removes_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = LocalStorage(tmpdir)
            content = b"To be deleted"
            await storage.upload("delete_me.txt", content)

            await storage.delete("delete_me.txt")

            with pytest.raises(FileNotFoundError):
                await storage.download("delete_me.txt")

    @pytest.mark.asyncio
    async def test_delete_nonexistent_file_does_not_raise(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = LocalStorage(tmpdir)
            await storage.delete("nonexistent.txt")

    @pytest.mark.asyncio
    async def test_list_files_returns_correct_metadata(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = LocalStorage(tmpdir)
            await storage.upload("file1.txt", b"content1")
            await storage.upload("file2.txt", b"content2")
            await storage.upload("subdir/file3.txt", b"content3")

            files = await storage.list_files("")

            assert len(files) == 3
            file_paths = [f["path"] for f in files]
            assert "file1.txt" in file_paths
            assert "file2.txt" in file_paths
            assert "subdir/file3.txt" in file_paths

            for file_info in files:
                assert "size" in file_info
                assert "modified" in file_info
                assert file_info["size"] > 0

    @pytest.mark.asyncio
    async def test_list_files_with_prefix(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = LocalStorage(tmpdir)
            await storage.upload("videos/video1.mp4", b"v1")
            await storage.upload("videos/video2.mp4", b"v2")
            await storage.upload("images/image1.jpg", b"i1")

            files = await storage.list_files("videos")

            assert len(files) == 2
            for f in files:
                assert f["path"].startswith("videos/")

    @pytest.mark.asyncio
    async def test_list_files_empty_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = LocalStorage(tmpdir)
            files = await storage.list_files("")
            assert files == []

    @pytest.mark.asyncio
    async def test_get_url(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = LocalStorage(tmpdir)
            url = await storage.get_url("test.txt")
            assert url == "/storage/test.txt"


class TestS3StorageMocked:
    """S3 storage tests with mocked boto3."""

    @pytest.mark.asyncio
    async def test_upload_calls_s3_api(self, mocker):
        mock_s3_client = mocker.MagicMock()
        mocker.patch("boto3.client", return_value=mock_s3_client)

        from app.storage.s3 import S3Storage

        storage = S3Storage(
            endpoint="https://s3.amazonaws.com",
            access_key="test",
            secret_key="test",
            bucket="test-bucket",
            region="us-east-1",
        )

        await storage.upload("test.txt", b"content")

        mock_s3_client.put_object.assert_called_once_with(
            Bucket="test-bucket", Key="test.txt", Body=b"content"
        )

    @pytest.mark.asyncio
    async def test_download_from_s3(self, mocker):
        mock_s3_client = mocker.MagicMock()
        mock_s3_client.get_object.return_value = {
            "Body": mocker.MagicMock(read=lambda: b"downloaded content")
        }
        mocker.patch("boto3.client", return_value=mock_s3_client)

        from app.storage.s3 import S3Storage

        storage = S3Storage(
            endpoint="https://s3.amazonaws.com",
            access_key="test",
            secret_key="test",
            bucket="test-bucket",
            region="us-east-1",
        )

        content = await storage.download("test.txt")

        assert content == b"downloaded content"
        mock_s3_client.get_object.assert_called_once_with(Bucket="test-bucket", Key="test.txt")

    @pytest.mark.asyncio
    async def test_delete_from_s3(self, mocker):
        mock_s3_client = mocker.MagicMock()
        mocker.patch("boto3.client", return_value=mock_s3_client)

        from app.storage.s3 import S3Storage

        storage = S3Storage(
            endpoint="https://s3.amazonaws.com",
            access_key="test",
            secret_key="test",
            bucket="test-bucket",
            region="us-east-1",
        )

        await storage.delete("test.txt")

        mock_s3_client.delete_object.assert_called_once_with(Bucket="test-bucket", Key="test.txt")


class TestSSHStorageMocked:
    """SSH storage tests with mocked paramiko."""

    @pytest.mark.asyncio
    async def test_upload_uses_sftp(self, mocker):
        mock_ssh_client = mocker.MagicMock()
        mock_sftp = mocker.MagicMock()
        mock_ssh_client.open_sftp.return_value.__enter__.return_value = mock_sftp

        mocker.patch("paramiko.SSHClient", return_value=mock_ssh_client)

        from app.storage.ssh import SSHStorage

        storage = SSHStorage(
            host="test.com",
            user="testuser",
            key_path="/tmp/test_key",
            remote_path="/remote/storage",
        )

        await storage.upload("test.txt", b"content")

        assert mock_sftp.putfo.called

    @pytest.mark.asyncio
    async def test_download_from_ssh(self, mocker):
        mock_ssh_client = mocker.MagicMock()
        mock_sftp = mocker.MagicMock()

        mock_file = mocker.MagicMock()
        mock_file.read.return_value = b"content"
        mock_file.__enter__ = mocker.MagicMock(return_value=mock_file)
        mock_file.__exit__ = mocker.MagicMock(return_value=None)

        mock_sftp.file.return_value = mock_file
        mock_ssh_client.open_sftp.return_value.__enter__.return_value = mock_sftp

        mocker.patch("paramiko.SSHClient", return_value=mock_ssh_client)

        from app.storage.ssh import SSHStorage

        storage = SSHStorage(
            host="test.com",
            user="testuser",
            key_path="/tmp/test_key",
            remote_path="/remote/storage",
        )

        content = await storage.download("test.txt")

        assert content == b"content"

    @pytest.mark.asyncio
    async def test_handles_ssh_connection_error(self, mocker):
        mock_ssh_client = mocker.MagicMock()
        mock_ssh_client.connect.side_effect = Exception("Connection failed")

        mocker.patch("paramiko.SSHClient", return_value=mock_ssh_client)

        from app.storage.ssh import SSHStorage

        storage = SSHStorage(
            host="test.com",
            user="testuser",
            key_path="/tmp/test_key",
            remote_path="/remote/storage",
        )

        with pytest.raises(Exception, match="Connection failed"):
            await storage.upload("test.txt", b"content")

