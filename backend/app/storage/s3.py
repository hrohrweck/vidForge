from __future__ import annotations

from typing import Any

from . import StorageBackend


class S3Storage(StorageBackend):
    """Compatibility wrapper for the S3 storage backend."""

    def __init__(
        self,
        endpoint: str,
        access_key: str,
        secret_key: str,
        bucket: str,
        region: str = "us-east-1",
    ) -> None:
        import boto3

        self._bucket = bucket
        self._client = boto3.client(
            "s3",
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            endpoint_url=endpoint,
            region_name=region,
        )

    async def upload(self, path: str, data: bytes) -> None:
        self._client.put_object(Bucket=self._bucket, Key=path, Body=data)

    async def download(self, path: str) -> bytes:
        response = self._client.get_object(Bucket=self._bucket, Key=path)
        body = response["Body"]
        return body.read()

    async def delete(self, path: str) -> None:
        self._client.delete_object(Bucket=self._bucket, Key=path)

    async def list_files(self, prefix: str = "") -> list[dict[str, Any]]:
        result = self._client.list_objects_v2(
            Bucket=self._bucket,
            Prefix=prefix,
        )

        files: list[dict[str, Any]] = []
        for item in result.get("Contents", []):
            files.append(
                {
                    "path": item["Key"],
                    "size": item.get("Size", 0),
                    "modified": item.get("LastModified").timestamp(),
                }
            )
        return files

    async def get_url(self, path: str) -> str:
        return f"/storage/{path}"
