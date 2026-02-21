import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, UploadFile, File, Query
from fastapi.responses import StreamingResponse

from backend.core.dependency_injection.app_container import AppContainer
from backend.core.dependency_injection.repository_container import RepositoryContainer

app_container = AppContainer()

static_router = APIRouter(prefix="/static", tags=["Static Files"])


@static_router.post("/files")
@app_container.inject(params=["session", "external_session", "global_external_session"])
async def create_static_file(
    repository_container: RepositoryContainer,
    file: UploadFile = File(...),
    bucket: str = Query("static", description="MinIO bucket name"),
    key: Optional[str] = Query(None, description="Object key. If not provided, uses filename."),
):
    """
    Upload a file to MinIO (create/overwrite).
    """
    try:
        repo = repository_container.static_file_repo_  # you should provide it in container
        object_key = key or file.filename
        if not object_key:
            raise HTTPException(status_code=400, detail="key or filename must be provided")

        data = await file.read()

        # Optional: ensure bucket exists (if your repo supports it)
        if hasattr(repo, "ensure_bucket"):
            await repo.ensure_bucket(bucket)

        result = await repo.create(
            bucket=bucket,
            key=object_key,
            data=data,
            content_type=file.content_type,
        )
        return {"bucket": bucket, "key": object_key, "etag": result.get("etag")}
    except HTTPException:
        raise
    except Exception as e:
        logging.exception("Error uploading static file: %s", str(e))
        raise HTTPException(status_code=500, detail="Failed to upload file") from e


@static_router.get("/files")
@app_container.inject(params=["session", "external_session", "global_external_session"])
async def get_static_file(
    repository_container: RepositoryContainer,
    bucket: str = Query("static"),
    key: str = Query(..., description="Object key in MinIO"),
    download_name: Optional[str] = Query(None, description="Filename for download"),
):
    """
    Download a file from MinIO as a stream.
    """
    try:
        repo = repository_container.static_file_repo_

        # We fetch bytes via repo.get() and stream them.
        # If you want true streaming for huge files, we can add repo.get_stream().
        data: bytes = await repo.get(bucket=bucket, key=key)

        filename = download_name or key.split("/")[-1] or "file"
        headers = {"Content-Disposition": f'attachment; filename="{filename}"'}

        return StreamingResponse(
            iter([data]),
            media_type="application/octet-stream",
            headers=headers,
        )
    except HTTPException:
        raise
    except Exception as e:
        logging.exception("Error downloading static file: %s", str(e))
        raise HTTPException(status_code=500, detail="Failed to download file") from e


@static_router.put("/files")
@app_container.inject(params=["session", "external_session", "global_external_session"])
async def update_static_file(
    repository_container: RepositoryContainer,
    file: UploadFile = File(...),
    bucket: str = Query("static"),
    key: str = Query(..., description="Object key to overwrite"),
):
    """
    Overwrite an existing object (S3/MinIO 'update' = put to same key).
    """
    try:
        repo = repository_container.static_file_repo_
        data = await file.read()

        result = await repo.update(
            bucket=bucket,
            key=key,
            data=data,
            content_type=file.content_type,
        )
        return {"bucket": bucket, "key": key, "etag": result.get("etag")}
    except HTTPException:
        raise
    except Exception as e:
        logging.exception("Error updating static file: %s", str(e))
        raise HTTPException(status_code=500, detail="Failed to update file") from e


@static_router.delete("/files")
@app_container.inject(params=["session", "external_session", "global_external_session"])
async def delete_static_file(
    repository_container: RepositoryContainer,
    bucket: str = Query("static"),
    key: str = Query(...),
):
    """
    Delete an object from MinIO.
    """
    try:
        repo = repository_container.static_file_repo_
        ok = await repo.delete(bucket=bucket, key=key)
        return {"bucket": bucket, "key": key, "deleted": bool(ok)}
    except HTTPException:
        raise
    except Exception as e:
        logging.exception("Error deleting static file: %s", str(e))
        raise HTTPException(status_code=500, detail="Failed to delete file") from e
