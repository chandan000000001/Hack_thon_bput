"""Supabase Storage integration for media uploads (Part 2).

All uploads use the service role client. The 'cyberguard-media' bucket is
private; read access is granted through short-lived signed URLs.
"""

from pathlib import PurePosixPath

from fastapi import HTTPException, UploadFile, status
from supabase import Client

from app.core.supabase_client import get_supabase

MEDIA_BUCKET = "cyberguard-media"
MAX_MEDIA_SIZE_BYTES = 25 * 1024 * 1024  # 25 MB
SIGNED_URL_EXPIRY_SECONDS = 3600  # 1 hour


def _sanitize_file_name(file_name: str | None) -> str:
    """Strip any path components from the client-supplied file name."""
    if not file_name:
        return "upload.bin"
    return PurePosixPath(file_name.replace("\\", "/")).name or "upload.bin"


def upload_media_to_supabase(file: UploadFile, event_id: str) -> dict:
    """Upload a media file to the private 'cyberguard-media' bucket.

    Returns a dict with file_name, storage_path, file_type and size_bytes.
    Raises HTTPException 413 if the file exceeds the 25 MB limit.
    """
    content = file.file.read()
    if len(content) > MAX_MEDIA_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File exceeds the maximum allowed size of 25 MB",
        )

    file_name = _sanitize_file_name(file.filename)
    storage_path = f"media/{event_id}/{file_name}"
    client: Client = get_supabase()

    client.storage.from_(MEDIA_BUCKET).upload(
        path=storage_path,
        file=content,
        file_options={
            "content-type": file.content_type or "application/octet-stream",
            "upsert": "true",
        },
    )

    return {
        "file_name": file_name,
        "storage_path": storage_path,
        "file_type": file.content_type,
        "size_bytes": len(content),
    }


def create_media_signed_url(storage_path: str) -> str:
    """Return a temporary signed URL (valid 1 hour) for a stored media file."""
    client: Client = get_supabase()
    result = client.storage.from_(MEDIA_BUCKET).create_signed_url(
        storage_path, SIGNED_URL_EXPIRY_SECONDS
    )
    signed_url = result.get("signedURL") or result.get("signedUrl") if isinstance(result, dict) else result
    if not signed_url:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create signed URL for media file",
        )
    return signed_url


def download_media(storage_path: str) -> bytes:
    """Download a stored media file's bytes using the service role client."""
    client: Client = get_supabase()
    return client.storage.from_(MEDIA_BUCKET).download(storage_path)
