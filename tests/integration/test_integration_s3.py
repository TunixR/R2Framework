import uuid

import botocore.exceptions as bex
import pytest
import pytest_asyncio

from s3.utils import S3Client
from settings import S3_BUCKET, S3_URL


async def _ensure_bucket_exists() -> None:
    """
    Ensure the S3 bucket exists, creating it if necessary.
    """
    async with S3Client._client() as s3c:  # pyright: ignore[reportGeneralTypeIssues,reportPrivateUsage]
        try:
            await s3c.head_bucket(Bucket=S3_BUCKET)
        except bex.ClientError as e:
            # Try to create the bucket if it doesn't exist.
            # For us-east-1, CreateBucketConfiguration should be omitted.
            error_code = e.response.get("Error", {}).get("Code", "")
            if error_code in {"404", "NoSuchBucket", "NotFound"}:
                await s3c.create_bucket(Bucket=S3_BUCKET)
            else:
                raise


@pytest_asyncio.fixture(scope="module", autouse=True)
async def s3_ready():
    """
    Module-scoped fixture:
      - Attempts to connect to the configured S3 endpoint.
      - Ensures the test bucket exists (creates it if missing).
      - Skips tests if S3 is not reachable.
    """
    try:
        async with S3Client._client() as s3c:  # pyright: ignore[reportGeneralTypeIssues,reportPrivateUsage]
            # Basic connectivity check
            await s3c.list_buckets()
    except Exception as e:
        pytest.skip(f"S3 integration tests skipped (cannot connect to {S3_URL}): {e}")

    # If connectivity works, ensure the bucket is present
    try:
        await _ensure_bucket_exists()
    except Exception as e:
        pytest.skip(
            f"S3 integration tests skipped (cannot ensure bucket {S3_BUCKET}): {e}"
        )

    yield
    # No teardown: leave bucket/objects management to tests and environment


@pytest.mark.asyncio
async def test_upload_and_download_roundtrip():
    """
    Upload bytes and download them back; assert roundtrip integrity.
    """
    payload = b"hello s3 integration!"
    key = await S3Client.upload_bytes(
        payload, content_type="text/plain", bucket=S3_BUCKET
    )

    try:
        downloaded = await S3Client.download_bytes(key, bucket=S3_BUCKET)
        assert downloaded == payload
    finally:
        # Cleanup regardless of assertion outcome
        await S3Client.delete_object(key, bucket=S3_BUCKET)


@pytest.mark.asyncio
async def test_delete_object_removes_key():
    """
    Upload an object, delete it, then verify subsequent download fails.
    """
    payload = b"to be deleted"
    key = await S3Client.upload_bytes(
        payload, content_type="application/octet-stream", bucket=S3_BUCKET
    )

    # Delete the object
    await S3Client.delete_object(key, bucket=S3_BUCKET)

    # Verify download now fails
    with pytest.raises(bex.ClientError) as excinfo:
        _ = await S3Client.download_bytes(key, bucket=S3_BUCKET)

    # Be flexible across providers (AWS S3, MinIO, LocalStack, etc.)
    err_code = excinfo.value.response.get("Error", {}).get("Code", "")
    assert err_code in {"NoSuchKey", "404", "NotFound"}


@pytest.mark.asyncio
async def test_download_nonexistent_raises():
    """
    Attempt to download a random, non-existent key should raise an error.
    """
    random_key = str(uuid.uuid4())

    with pytest.raises(bex.ClientError) as excinfo:
        _ = await S3Client.download_bytes(random_key, bucket=S3_BUCKET)

    err_code = excinfo.value.response.get("Error", {}).get("Code", "")
    assert err_code in {"NoSuchKey", "404", "NotFound"}


@pytest.mark.asyncio
async def test_bulk_download_bytes_roundtrip_multiple_keys():
    """
    Upload multiple objects and bulk download them; assert mapping and contents.
    """
    payloads = {
        "text1": b"bulk 1",
        "text2": b"bulk 2",
        "text3": b"bulk 3",
    }

    keys: list[str] = []
    try:
        # Upload three objects
        for _, data in payloads.items():
            key = await S3Client.upload_bytes(
                data, content_type="application/octet-stream", bucket=S3_BUCKET
            )
            keys.append(key)

        # Bulk download
        downloaded_map = await S3Client.bulk_download_bytes(keys, bucket=S3_BUCKET)

        # Verify we got all keys and contents match
        assert set(downloaded_map.keys()) == set(keys)
        for i, key in enumerate(keys, start=1):
            assert downloaded_map[key] == payloads[f"text{i}"]
    finally:
        # Cleanup all uploaded objects
        for key in keys:
            await S3Client.delete_object(key, bucket=S3_BUCKET)


@pytest.mark.asyncio
async def test_bulk_delete_objects_removes_multiple_keys():
    """
    Upload multiple objects, bulk delete them, then verify each is gone.
    """
    payloads = [b"del 1", b"del 2", b"del 3"]
    keys: list[str] = []

    # Upload three objects
    for data in payloads:
        key = await S3Client.upload_bytes(
            data, content_type="application/octet-stream", bucket=S3_BUCKET
        )
        keys.append(key)

    # Bulk delete
    await S3Client.bulk_delete_objects(keys, bucket=S3_BUCKET)

    # Verify each download now fails
    for key in keys:
        with pytest.raises(bex.ClientError) as excinfo:
            _ = await S3Client.download_bytes(key, bucket=S3_BUCKET)
        err_code = excinfo.value.response.get("Error", {}).get("Code", "")
        assert err_code in {"NoSuchKey", "404", "NotFound"}
