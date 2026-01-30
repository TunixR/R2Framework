import uuid

import aioboto3

from settings import AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, S3_BUCKET, S3_URL


class S3Client:
    @staticmethod
    def _client():
        session = aioboto3.Session()
        return session.client(
            "s3",
            endpoint_url=S3_URL,
            aws_access_key_id=AWS_ACCESS_KEY_ID,
            aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
            region_name="us-east-1",
        )

    @staticmethod
    async def upload_bytes(
        file_bytes: bytes, content_type: str, bucket: str = S3_BUCKET
    ) -> str:
        """
        Uploads bytes to the specified S3 bucket and returns the S3 URI.

        Args:
            file_bytes (bytes): The bytes to upload.
            content_type (str): The content type of the file.
            bucket (str): The S3 bucket to upload to. Defaults to S3_BUCKET.
        Returns:
            str: The S3 key of the uploaded file.
        """
        key = str(uuid.uuid4())
        async with S3Client._client() as s3_client:  # pyright: ignore[reportGeneralTypeIssues]
            await s3_client.put_object(
                Bucket=bucket, Key=key, Body=file_bytes, ContentType=content_type
            )
        return key

    @staticmethod
    async def download_bytes(key: str, bucket: str = S3_BUCKET) -> bytes:
        """
        Downloads bytes from the specified S3 bucket using the given key.

        Args:
            key (str): The S3 key of the file to download.
            bucket (str): The S3 bucket to download from. Defaults to S3_BUCKET.
        Returns:
            bytes: The downloaded file bytes.
        """
        async with S3Client._client() as s3_client:  # pyright: ignore[reportGeneralTypeIssues]
            obj = await s3_client.get_object(Bucket=bucket, Key=key)
            file_bytes = await obj["Body"].read()
        return file_bytes

    @staticmethod
    async def bulk_download_bytes(
        keys: list[str], bucket: str = S3_BUCKET
    ) -> dict[str, bytes]:
        """
        Downloads multiple files from the specified S3 bucket using the given keys.

        Args:
            keys (list[str]): The S3 keys of the files to download.
            bucket (str): The S3 bucket to download from. Defaults to S3_BUCKET.
        Returns:
            dict[str, bytes]: A dictionary mapping S3 keys to their downloaded file bytes.
        """
        result = {}
        async with S3Client._client() as s3_client:  # pyright: ignore[reportGeneralTypeIssues]
            for key in keys:
                obj = await s3_client.get_object(Bucket=bucket, Key=key)
                file_bytes = await obj["Body"].read()
                result[key] = file_bytes
        return result

    @staticmethod
    async def delete_object(key: str, bucket: str = S3_BUCKET) -> None:
        """
        Deletes an object from the specified S3 bucket using the given key.

        Args:
            key (str): The S3 key of the file to delete.
            bucket (str): The S3 bucket to delete from. Defaults to S3_BUCKET.
        """
        async with S3Client._client() as s3_client:  # pyright: ignore[reportGeneralTypeIssues]
            await s3_client.delete_object(Bucket=bucket, Key=key)

    @staticmethod
    async def bulk_delete_objects(keys: list[str], bucket: str = S3_BUCKET) -> None:
        """
        Deletes multiple objects from the specified S3 bucket using the given keys.

        Args:
            keys (list[str]): The S3 keys of the files to delete.
            bucket (str): The S3 bucket to delete from. Defaults to S3_BUCKET.
        """
        objects = [{"Key": key} for key in keys]
        async with S3Client._client() as s3_client:  # pyright: ignore[reportGeneralTypeIssues]
            await s3_client.delete_objects(Bucket=bucket, Delete={"Objects": objects})
