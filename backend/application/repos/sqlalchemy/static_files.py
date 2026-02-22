import inspect
import logging
from typing import Dict, Any, Optional

import aioboto3
from botocore.config import Config
from botocore.exceptions import ClientError

from backend.application.repos.abstract.static_files import AbstractStaticFileRepository
from backend.settings import Settings

logger = logging.getLogger(__name__)


class MiniIORepository(AbstractStaticFileRepository):
    """
    Async S3 repository for MinIO using aioboto3.
    """

    def __init__(self, settings: Settings):
        self._settings = settings
        self._session = aioboto3.Session()

        self._botocore_config = Config(
            s3={"addressing_style": "path"},
            retries={"max_attempts": 5, "mode": "standard"},
        )

    def _client_kwargs(self) -> Dict[str, Any]:
        return {
            "service_name": "s3",
            "endpoint_url": self._settings.S3_URL,
            "aws_access_key_id": self._settings.S3_ACCESS_KEY,
            "aws_secret_access_key": self._settings.S3_SECRET_KEY,
            "region_name": self._settings.S3_REGION_NAME,
            "verify": False,
            "config": self._botocore_config,
        }

    async def ensure_bucket(self, bucket: str) -> None:
        async with self._session.client(**self._client_kwargs()) as s3:
            try:
                await s3.head_bucket(Bucket=bucket)
                return
            except ClientError as e:
                error_code = e.response.get("Error", {}).get("Code")
                if error_code in ("404", "NoSuchBucket"):
                    try:
                        await s3.create_bucket(Bucket=bucket)
                        return
                    except ClientError as create_error:
                        create_code = create_error.response.get("Error", {}).get("Code")
                        if create_code in ("BucketAlreadyOwnedByYou", "BucketAlreadyExists"):
                            return
                        raise
                raise

    async def get_presigned_url(
        self,
        *,
        bucket: str,
        key: str,
        expires_in: int = 3600,
        method: str = "get_object",
        response_content_type: Optional[str] = None,
        response_content_disposition: Optional[str] = None,
    ) -> str:
        """
        Returns a presigned URL that is valid for `expires_in` seconds.
        method: "get_object" | "put_object" | etc.
        """
        await self.ensure_bucket(bucket)

        params: Dict[str, Any] = {"Bucket": bucket, "Key": key}

        # Optional: hint browser how to handle the file
        if response_content_type:
            params["ResponseContentType"] = response_content_type
        if response_content_disposition:
            params["ResponseContentDisposition"] = response_content_disposition

        async with self._session.client(**self._client_kwargs()) as s3:
            maybe_url = s3.generate_presigned_url(
                ClientMethod=method,
                Params=params,
                ExpiresIn=expires_in,
            )
            url = await maybe_url if inspect.isawaitable(maybe_url) else maybe_url

            url = url.replace("minio:9000", "localhost:9000")

            return str(url)

    async def get(
        self,
        *,
        bucket: str,
        key: str,
        range_header: Optional[str] = None,
        include_url: bool = True,
        url_expires_in: int = 3600,
    ) -> Dict[str, Any]:
        """
        If include_url=True, returns {"data": bytes, "url": str}
        else returns {"data": bytes}
        """
        await self.ensure_bucket(bucket)

        extra = {}
        if range_header:
            extra["Range"] = range_header

        async with self._session.client(**self._client_kwargs()) as s3:
            resp = await s3.get_object(Bucket=bucket, Key=key, **extra)
            body = resp["Body"]
            data = await body.read()
            body.close()

        result: Dict[str, Any] = {"data": data}

        if include_url:
            result["url"] = await self.get_presigned_url(
                bucket=bucket,
                key=key,
                expires_in=url_expires_in,
                method="get_object",
            )

        return result["url"]

    async def create(
        self,
        *,
        bucket: str,
        key: str,
        data: bytes,
        content_type: Optional[str] = None,
        metadata: Optional[Dict[str, str]] = None,
        include_url: bool = True,
        url_expires_in: int = 3600,
    ) -> Dict[str, Any]:
        await self.ensure_bucket(bucket)

        put_kwargs: Dict[str, Any] = {
            "Bucket": bucket,
            "Key": key,
            "Body": data,
        }

        if content_type:
            put_kwargs["ContentType"] = content_type
        if metadata:
            put_kwargs["Metadata"] = metadata

        async with self._session.client(**self._client_kwargs()) as s3:
            resp = await s3.put_object(**put_kwargs)

        result: Dict[str, Any] = {
            "bucket": bucket,
            "key": key,
            "etag": resp.get("ETag"),
            "version_id": resp.get("VersionId"),
        }

        if include_url:
            result["url"] = await self.get_presigned_url(
                bucket=bucket,
                key=key,
                expires_in=url_expires_in,
                method="get_object",
                response_content_type=content_type,
            )

        return result

    async def update(
        self,
        *,
        bucket: str,
        key: str,
        data: bytes,
        content_type: Optional[str] = None,
        metadata: Optional[Dict[str, str]] = None,
        include_url: bool = True,
        url_expires_in: int = 3600,
    ) -> Dict[str, Any]:
        return await self.create(
            bucket=bucket,
            key=key,
            data=data,
            content_type=content_type,
            metadata=metadata,
            include_url=include_url,
            url_expires_in=url_expires_in,
        )

    async def delete(self, *, bucket: str, key: str) -> bool:
        await self.ensure_bucket(bucket)
        async with self._session.client(**self._client_kwargs()) as s3:
            await s3.delete_object(Bucket=bucket, Key=key)
            return True
