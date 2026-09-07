"""Multi-source event ingestion endpoints (Part 2).

Every endpoint is protected by the Supabase Auth bearer-token dependency.
All inserts use the service role client. This part only ingests and stores
raw data; no detection or scoring happens here.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from pydantic import BaseModel

from app.core.security import get_current_user
from app.core.storage import (
    SIGNED_URL_EXPIRY_SECONDS,
    create_media_signed_url,
    upload_media_to_supabase,
)
from app.core.supabase_client import get_supabase
from app.schemas.events import (
    ApiLogEvent,
    AuthLogEvent,
    EmailEvent,
    MessageEvent,
    NetworkFlowEvent,
    UrlEvent,
)

router = APIRouter(prefix="/events", tags=["Events"])

MEDIA_CONTENT_TYPE_PREFIXES = ("image/", "audio/", "video/")
MEDIA_SOURCE = "media_upload"


def _insert_event(event_type: str, source: str, raw_data: dict) -> str:
    """Insert a new event row with status 'received' and return its id."""
    event_id = str(uuid.uuid4())
    try:
        get_supabase().table("events").insert(
            {
                "id": event_id,
                "event_type": event_type,
                "source": source,
                "raw_data": raw_data,
                "status": "received",
            }
        ).execute()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to store event",
        ) from exc
    return event_id


def _ingest_payload(payload: BaseModel) -> dict:
    """Persist a validated payload as a raw event and return the response."""
    event_id = _insert_event(
        event_type=payload.event_type,
        source=payload.source,
        raw_data=payload.model_dump(mode="json"),
    )
    return {"event_id": event_id, "event_type": payload.event_type, "status": "received"}


@router.post("/email")
def ingest_email_event(
    payload: EmailEvent, _user: dict = Depends(get_current_user)
) -> dict:
    return _ingest_payload(payload)


@router.post("/url")
def ingest_url_event(
    payload: UrlEvent, _user: dict = Depends(get_current_user)
) -> dict:
    return _ingest_payload(payload)


@router.post("/message")
def ingest_message_event(
    payload: MessageEvent, _user: dict = Depends(get_current_user)
) -> dict:
    return _ingest_payload(payload)


@router.post("/auth-log")
def ingest_auth_log_event(
    payload: AuthLogEvent, _user: dict = Depends(get_current_user)
) -> dict:
    return _ingest_payload(payload)


@router.post("/network")
def ingest_network_flow_event(
    payload: NetworkFlowEvent, _user: dict = Depends(get_current_user)
) -> dict:
    return _ingest_payload(payload)


@router.post("/api-log")
def ingest_api_log_event(
    payload: ApiLogEvent, _user: dict = Depends(get_current_user)
) -> dict:
    return _ingest_payload(payload)


@router.post("/media")
def ingest_media_event(
    file: UploadFile, _user: dict = Depends(get_current_user)
) -> dict:
    """Upload image/audio/video media and register it as a deepfake_media event."""
    content_type = file.content_type or ""
    if not content_type.startswith(MEDIA_CONTENT_TYPE_PREFIXES):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must be an image, audio, or video upload",
        )

    event_id = str(uuid.uuid4())
    _insert_event(
        event_type="deepfake_media",
        source=MEDIA_SOURCE,
        raw_data={
            "event_id": event_id,
            "file_name": file.filename,
            "content_type": content_type,
        },
    )

    try:
        media_record = upload_media_to_supabase(file, event_id)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to upload media file to storage",
        ) from exc

    try:
        get_supabase().table("media_files").insert(
            {
                "event_id": event_id,
                "file_name": media_record["file_name"],
                "storage_path": media_record["storage_path"],
                "file_type": media_record["file_type"],
                "size_bytes": media_record["size_bytes"],
            }
        ).execute()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to store media file metadata",
        ) from exc

    return {
        "event_id": event_id,
        "event_type": "deepfake_media",
        "status": "received",
        "file_name": media_record["file_name"],
        "storage_path": media_record["storage_path"],
    }


@router.get("/{event_id}")
def get_event(event_id: str, _user: dict = Depends(get_current_user)) -> dict:
    """Return a single stored event row by id."""
    try:
        response = (
            get_supabase()
            .table("events")
            .select("*")
            .eq("id", event_id)
            .limit(1)
            .execute()
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to query event",
        ) from exc

    rows = response.data or []
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found",
        )
    return rows[0]


@router.get("/{event_id}/media-url")
def get_event_media_url(event_id: str, _user: dict = Depends(get_current_user)) -> dict:
    """Return a 1-hour signed URL for the media file linked to the event."""
    try:
        response = (
            get_supabase()
            .table("media_files")
            .select("storage_path, file_name")
            .eq("event_id", event_id)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to query media file metadata",
        ) from exc

    rows = response.data or []
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No media file exists for this event",
        )

    media = rows[0]
    signed_url = create_media_signed_url(media["storage_path"])
    return {
        "event_id": event_id,
        "file_name": media["file_name"],
        "signed_url": signed_url,
        "expires_in_seconds": SIGNED_URL_EXPIRY_SECONDS,
    }
