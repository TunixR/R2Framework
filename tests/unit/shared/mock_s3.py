from typing import Any, override

from s3.utils import S3Client

_STORE: dict[str, Any] = {}


class MockS3Client(S3Client):
    @staticmethod
    @override
    async def upload_bytes(
        file_bytes: bytes, content_type: str, bucket: str = "mock-bucket"
    ) -> str:
        key = str(len(_STORE) + 1)
        _STORE[key] = {
            "bytes": file_bytes,
            "content_type": content_type,
            "bucket": bucket,
        }
        return key

    @staticmethod
    @override
    async def download_bytes(key: str, bucket: str = "mock-bucket") -> bytes:
        if key in _STORE and _STORE[key]["bucket"] == bucket:
            return _STORE[key]["bytes"]
        raise KeyError(f"Key {key} not found in bucket {bucket}.")

    @staticmethod
    @override
    async def delete_object(key: str, bucket: str = "mock-bucket") -> None:
        if key in _STORE and _STORE[key]["bucket"] == bucket:
            del _STORE[key]
        else:
            raise KeyError(f"Key {key} not found in bucket {bucket}.")
