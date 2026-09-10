"""Supabase Storage integration for media uploads (Part 2).

All uploads use the service role client. The 'cyberguard-media' bucket is
private; read access is granted through short-lived signed URLs.
"""

import mimetypes
from pathlib import PurePosixPath

from fastapi import HTTPException, status
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


def upload_media_to_supabase(file_bytes: bytes, file_name: str | None, event_id: str) -> dict:
    """Upload already-read media bytes to the private 'cyberguard-media' bucket.

    Phase D-1: the caller reads the SpooledUploadFile exactly once and passes
    the bytes here, so the upload never re-reads the request stream.

    Returns a dict with file_name, storage_path, file_type and size_bytes.
    Raises HTTPException 413 if the bytes exceed the 25 MB limit.
    """
    if len(file_bytes) > MAX_MEDIA_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File exceeds the maximum allowed size of 25 MB",
        )

    safe_name = _sanitize_file_name(file_name)
    storage_path = f"media/{event_id}/{safe_name}"
    content_type = mimetypes.guess_type(safe_name)[0] or "application/octet-stream"
    client: Client = get_supabase()

    client.storage.from_(MEDIA_BUCKET).upload(
        path=storage_path,
        file=file_bytes,
        file_options={
            "content-type": content_type,
            "upsert": "true",
        },
    )

    return {
        "file_name": safe_name,
        "storage_path": storage_path,
        "file_type": content_type,
        "size_bytes": len(file_bytes),
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
