import pytest
from unittest.mock import MagicMock, patch

from app.storage.s3 import S3Storage
from app.storage.ssh import SSHStorage


class TestS3DownloadErrors:
    @pytest.fixture
    def s3_storage(self):
        with patch("boto3.client") as mock_client:
            storage = S3Storage(
                endpoint="http://localhost:9000",
                access_key="test",
                secret_key="test",
                bucket="test-bucket",
            )
            storage._client = mock_client.return_value
            yield storage

    @pytest.mark.asyncio
    async def test_download_missing_key_raises_file_not_found(self, s3_storage):
        from botocore.exceptions import ClientError

        error_response = {"Error": {"Code": "NoSuchKey", "Message": "The specified key does not exist."}}
        s3_storage._client.get_object.side_effect = ClientError(error_response, "GetObject")

        with pytest.raises(FileNotFoundError):
            await s3_storage.download("missing/file.txt")

    @pytest.mark.asyncio
    async def test_download_other_s3_error_raises_storage_error(self, s3_storage):
        from botocore.exceptions import ClientError

        error_response = {"Error": {"Code": "InternalError", "Message": "Something went wrong"}}
        s3_storage._client.get_object.side_effect = ClientError(error_response, "GetObject")

        with pytest.raises(Exception) as exc_info:
            await s3_storage.download("some/file.txt")

        assert not isinstance(exc_info.value, FileNotFoundError)

    @pytest.mark.asyncio
    async def test_download_success_returns_bytes(self, s3_storage):
        s3_storage._client.get_object.return_value = {"Body": MagicMock(read=lambda: b"data")}
        result = await s3_storage.download("exists.txt")
        assert result == b"data"


class TestSSHHostKeyVerification:
    @pytest.mark.asyncio
    async def test_ssh_uses_reject_policy_for_unknown_host(self):
        with patch("paramiko.SSHClient") as mock_ssh_client, \
             patch("paramiko.RejectPolicy") as mock_reject, \
             patch("paramiko.AutoAddPolicy") as mock_autoadd:
            mock_client = MagicMock()
            mock_ssh_client.return_value = mock_client
            mock_reject.return_value = MagicMock()
            mock_autoadd.return_value = MagicMock()

            storage = SSHStorage(
                host="unknown.host.example",
                user="test",
                key_path="/tmp/fake_key",
                remote_path="/tmp/remote",
            )

            mock_client.load_host_keys.return_value = None
            mock_client.connect.side_effect = Exception("Host key verification failed")

            with pytest.raises(Exception):
                await storage.download("test.txt")

            set_policy_call = mock_client.set_missing_host_key_policy.call_args
            assert set_policy_call is not None
            policy = set_policy_call[0][0]
            assert isinstance(policy, type(mock_reject.return_value))
