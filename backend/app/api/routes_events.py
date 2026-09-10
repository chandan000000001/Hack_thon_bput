"""Multi-source event ingestion endpoints (Part 2 + Phase B/C-1).

Every endpoint is protected by the Supabase Auth bearer-token dependency and
scoped to the caller's organization: event INSERTs carry org_id and event
SELECTs filter by it, so the service-role client still enforces tenant
isolation at the application layer. POST /events/bulk (Phase C-1) ingests a
whole auth-log/network batch as one event and hands the heavy analysis to the
Arq worker, falling back to synchronous processing when Redis is unavailable.
"""

import uuid
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.core.asyncbridge import to_thread
from app.core.config import get_settings
from app.core.security import CurrentUser, get_current_user, require_permission
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
from app.services.job_queue import enqueue_job
from app.workers.jobs import run_bulk_log_analysis

router = APIRouter(prefix="/events", tags=["Events"])

MEDIA_CONTENT_TYPE_PREFIXES = ("image/", "audio/", "video/")
MEDIA_SOURCE = "media_upload"
BULK_SOURCE = "bulk_upload"


class BulkIngestRequest(BaseModel):
    """Body for POST /events/bulk — one batch of rows per request."""

    kind: Literal["auth-log", "network"]
    rows: list[dict[str, Any]] = Field(min_length=1)


def _insert_event(event_type: str, source: str, raw_data: dict, org_id: str) -> str:
    """Insert a new org-scoped event row with status 'received' and return its id."""
    event_id = str(uuid.uuid4())
    try:
        get_supabase().table("events").insert(
            {
                "id": event_id,
                "org_id": org_id,
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


def _ingest_payload(payload: BaseModel, org_id: str) -> dict:
    """Persist a validated payload as an org-scoped raw event."""
    event_id = _insert_event(
        event_type=payload.event_type,
        source=payload.source,
        raw_data=payload.model_dump(mode="json"),
        org_id=org_id,
    )
    return {"event_id": event_id, "event_type": payload.event_type, "status": "received"}


@router.post("/email")
def ingest_email_event(
    payload: EmailEvent, analyst: CurrentUser = Depends(require_permission("analysis.run"))
) -> dict:
    return _ingest_payload(payload, analyst.org_id)


@router.post("/url")
def ingest_url_event(
    payload: UrlEvent, analyst: CurrentUser = Depends(require_permission("analysis.run"))
) -> dict:
    return _ingest_payload(payload, analyst.org_id)


@router.post("/message")
def ingest_message_event(
    payload: MessageEvent, analyst: CurrentUser = Depends(require_permission("analysis.run"))
) -> dict:
    return _ingest_payload(payload, analyst.org_id)


@router.post("/auth-log")
def ingest_auth_log_event(
    payload: AuthLogEvent, analyst: CurrentUser = Depends(require_permission("analysis.run"))
) -> dict:
    return _ingest_payload(payload, analyst.org_id)


@router.post("/network")
def ingest_network_flow_event(
    payload: NetworkFlowEvent, analyst: CurrentUser = Depends(require_permission("analysis.run"))
) -> dict:
    return _ingest_payload(payload, analyst.org_id)


@router.post("/api-log")
def ingest_api_log_event(
    payload: ApiLogEvent, analyst: CurrentUser = Depends(require_permission("analysis.run"))
) -> dict:
    return _ingest_payload(payload, analyst.org_id)


@router.post("/media")
def ingest_media_event(
    file: UploadFile,
    analyst: CurrentUser = Depends(require_permission("analysis.run")),
    _media: CurrentUser = Depends(require_permission("media.upload")),
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
        org_id=analyst.org_id,
    )

    try:
        # FIX 7: read the upload exactly once; the uploader takes bytes.
        media_record = upload_media_to_supabase(file.file.read(), file.filename, event_id)
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


@router.post("/bulk")
async def ingest_bulk_events(
    payload: BulkIngestRequest, analyst: CurrentUser = Depends(require_permission("analysis.run"))
) -> dict:
    """Ingest a bulk auth-log or network batch as one event (Phase C-1).

    The batch is stored as a single org-scoped event with status 'analyzing';
    heavy analysis then runs on the Arq worker (202) or, when Redis is
    unavailable, synchronously on this request (200).
    """
    if len(payload.rows) > 1000:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Bulk batch exceeds 1000 rows",
        )

    event_type = "account_takeover" if payload.kind == "auth-log" else "network"
    event_id = str(uuid.uuid4())
    try:
        await to_thread(
            lambda: get_supabase()
            .table("events")
            .insert(
                {
                    "id": event_id,
                    "org_id": analyst.org_id,
                    "event_type": event_type,
                    "source": BULK_SOURCE,
                    "raw_data": {"kind": payload.kind, "rows": payload.rows},
                    "status": "analyzing",
                }
            )
            .execute()
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to store bulk event",
        ) from exc

    settings = get_settings()
    if settings.BACKGROUND_WORKERS_ENABLED and await enqueue_job(
        "job_analyze_bulk_logs", event_id=event_id
    ):
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content={
                "event_id": event_id,
                "event_type": event_type,
                "status": "analyzing",
                "message": "Queued for background analysis",
            },
        )

    final_status = await run_bulk_log_analysis(event_id)
    return {
        "event_id": event_id,
        "event_type": event_type,
        "status": final_status,
        "message": "Analyzed synchronously",
    }


@router.get("/{event_id}")
def get_event(event_id: str, user: CurrentUser = Depends(get_current_user)) -> dict:
    """Return a single org-scoped event row by id."""
    try:
        response = (
            get_supabase()
            .table("events")
            .select("*")
            .eq("id", event_id)
            .eq("org_id", user.org_id)
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
def get_event_media_url(event_id: str, user: CurrentUser = Depends(get_current_user)) -> dict:
    """Return a 1-hour signed URL for the media file linked to an org-scoped event."""
    try:
        owned = (
            get_supabase()
            .table("events")
            .select("id")
            .eq("id", event_id)
            .eq("org_id", user.org_id)
            .limit(1)
            .execute()
            .data
            or []
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to query event",
        ) from exc
    if not owned:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found",
        )

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
