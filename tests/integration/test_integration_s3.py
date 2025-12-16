import os
import uuid

import pytest
import pytest_asyncio
import botocore.exceptions as bex

from settings import S3_URL, S3_BUCKET
from s3.utils import upload_bytes, download_bytes, delete_object, _client


def _want_run() -> bool:
    """
    Environment-aware toggle to run integration tests.

    If RUN_S3_TESTS is set to "1" or "true" (case-insensitive), we try to run tests.
    Otherwise, we still attempt a connectivity check and will skip if S3 isn't reachable.
    """
    val = os.getenv("INTEGRATION_TESTS", "").strip().lower()
    return val in {"1", "true", "yes", "y", "on"}


async def _ensure_bucket_exists() -> None:
    """
    Ensure the S3 bucket exists, creating it if necessary.
    """
    async with _client() as s3c: # pyright: ignore
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
        async with _client() as s3c: # pyright: ignore
            # Basic connectivity check
            await s3c.list_buckets()
    except Exception as e:
        if _want_run():
            # If the user asked to run, but we still can't connect, skip with details.
            pytest.skip(f"S3 integration tests skipped (cannot connect to {S3_URL}): {e}")
        else:
            pytest.skip(
                "S3 integration tests skipped (S3 not available). "
                "Set RUN_S3_TESTS=1 to attempt running these tests."
            )

    # If connectivity works, ensure the bucket is present
    try:
        await _ensure_bucket_exists()
    except Exception as e:
        pytest.skip(f"S3 integration tests skipped (cannot ensure bucket {S3_BUCKET}): {e}")

    yield
    # No teardown: leave bucket/objects management to tests and environment


@pytest.mark.asyncio
async def test_upload_and_download_roundtrip():
    """
    Upload bytes and download them back; assert roundtrip integrity.
    """
    payload = b"hello s3 integration!"
    key = await upload_bytes(payload, content_type="text/plain", bucket=S3_BUCKET)

    try:
        downloaded = await download_bytes(key, bucket=S3_BUCKET)
        assert downloaded == payload
    finally:
        # Cleanup regardless of assertion outcome
        await delete_object(key, bucket=S3_BUCKET)


@pytest.mark.asyncio
async def test_delete_object_removes_key():
    """
    Upload an object, delete it, then verify subsequent download fails.
    """
    payload = b"to be deleted"
    key = await upload_bytes(payload, content_type="application/octet-stream", bucket=S3_BUCKET)

    # Delete the object
    await delete_object(key, bucket=S3_BUCKET)

    # Verify download now fails
    with pytest.raises(bex.ClientError) as excinfo:
        await download_bytes(key, bucket=S3_BUCKET)

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
        await download_bytes(random_key, bucket=S3_BUCKET)

    err_code = excinfo.value.response.get("Error", {}).get("Code", "")
    assert err_code in {"NoSuchKey", "404", "NotFound"}
