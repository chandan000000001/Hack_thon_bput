"""Analysis pipeline endpoints (Parts 3, 4 & 5).

POST /analysis/email, /analysis/url, /analysis/impersonation,
/analysis/account-takeover, /analysis/network and /analysis/media run the
heuristic detectors, risk scoring, OpenRouter explanation, and alert
persistence. GET endpoints expose stored alerts.
"""

import uuid
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from pydantic import BaseModel, Field

from app.ai.openrouter_client import call_openrouter
from app.ai.prompt_templates import (
    ACCOUNT_TAKEOVER_SYSTEM_PROMPT,
    DEEPFAKE_SYSTEM_PROMPT,
    IMPERSONATION_SYSTEM_PROMPT,
    NETWORK_THREAT_SYSTEM_PROMPT,
    PHISHING_SYSTEM_PROMPT,
    URL_SYSTEM_PROMPT,
    format_account_takeover_user_prompt,
    format_deepfake_user_prompt,
    format_impersonation_user_prompt,
    format_network_user_prompt,
    format_phishing_user_prompt,
    format_url_user_prompt,
)
from app.core.security import CurrentUser, get_current_user, require_role
from app.core.storage import (
    MAX_MEDIA_SIZE_BYTES,
    download_media,
    upload_media_to_supabase,
)
from app.core.supabase_client import get_supabase
from app.services.account_takeover_detector import analyze_auth_log_heuristics
from app.services.alert_service import create_alert_in_db
from app.services.deepfake_detector import analyze_media
from app.services.impersonation_detector import analyze_impersonation_heuristics
from app.services.ml_inference import score_with_ml
from app.services.network_threat_detector import analyze_network_heuristics
from app.services.phishing_detector import analyze_email_heuristics
from app.services.scoring_service import get_severity
from app.services.url_detector import analyze_url_heuristics

router = APIRouter(prefix="/analysis", tags=["Analysis"])

ANALYSIS_MEDIA_CONTENT_TYPE_PREFIXES = ("image/", "video/", "audio/")
ANALYSIS_MEDIA_SOURCE = "media_upload"


class EmailAnalysisRequest(BaseModel):
    source: str = Field(default="api", min_length=1)
    sender: str = Field(min_length=1)
    subject: str
    body: str
    target_user: Optional[str] = None


class UrlAnalysisRequest(BaseModel):
    source: str = Field(default="api", min_length=1)
    url: str = Field(min_length=1)
    target_user: Optional[str] = None


class ImpersonationAnalysisRequest(BaseModel):
    source: str = Field(default="api", min_length=1)
    message: str
    claimed_identity: str = Field(min_length=1)


class AccountTakeoverAnalysisRequest(BaseModel):
    source: str = Field(default="api", min_length=1)
    events: list[dict[str, Any]]


class NetworkAnalysisRequest(BaseModel):
    source: str = Field(default="api", min_length=1)
    flows: list[dict[str, Any]] = []
    api_logs: list[dict[str, Any]] = []


def _create_analysis_event(event_type: str, source: str, raw_data: dict[str, Any]) -> str:
    """Insert a new event with status 'analyzing' and return its id."""
    try:
        response = (
            get_supabase()
            .table("events")
            .insert(
                {
                    "event_type": event_type,
                    "source": source,
                    "raw_data": raw_data,
                    "status": "analyzing",
                }
            )
            .execute()
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create event",
        ) from exc

    rows = response.data or []
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Event creation returned no data",
        )
    return rows[0]["id"]


def _fetch_alert_with_actions(alert_id: str) -> dict[str, Any]:
    """Return the alert row with its recommended_actions attached."""
    client = get_supabase()
    try:
        alert_response = (
            client.table("alerts").select("*").eq("id", alert_id).limit(1).execute()
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to query alert",
        ) from exc

    alert_rows = alert_response.data or []
    if not alert_rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alert not found",
        )

    # Fail-safe: a recommended_actions query failure must not 500 the alert
    # response — the alert is returned with an empty actions list instead.
    # NOTE: recommended_actions has no created_at column (Postgres 42703),
    # so this query must not order by it.
    actions_response = None
    try:
        actions_response = (
            client.table("recommended_actions")
            .select("*")
            .eq("alert_id", alert_id)
            .execute()
        )
    except Exception as e:
        print(f"❌ Supabase recommended_actions query error: {e}")

    return {**alert_rows[0], "recommended_actions": (actions_response.data if actions_response else None) or []}


async def _run_analysis_pipeline(
    *,
    event_type: str,
    module: str,
    source: str,
    raw_data: dict[str, Any],
    indicators: list[dict],
    system_prompt: str,
    user_prompt: str,
) -> dict[str, Any]:
    """Shared detection pipeline: persist event, score, explain, alert."""
    event_id = _create_analysis_event(
        event_type=event_type,
        source=source,
        raw_data=raw_data,
    )
    # Hybrid engine (ML Step 3): heuristic indicators + trained-model
    # probability are blended; the ml_model indicator is persisted but does
    # not add heuristic weight on top of the blend.
    _heuristic_score, hybrid_score, _ml_probability = score_with_ml(indicators)
    severity = get_severity(hybrid_score)

    llm_output = await call_openrouter(system_prompt, user_prompt)

    alert_id = create_alert_in_db(
        event_id=event_id,
        module=module,
        raw_data=raw_data,
        indicators=indicators,
        score=hybrid_score,
        severity=severity,
        llm_output=llm_output,
    )
    return _fetch_alert_with_actions(alert_id)


@router.post("/email")
async def analyze_email(
    payload: EmailAnalysisRequest, _analyst: CurrentUser = Depends(require_role("analyst"))
) -> dict:
    """Full phishing analysis pipeline for an email."""
    raw_data = payload.model_dump(mode="json")
    indicators = analyze_email_heuristics(
        sender=payload.sender, subject=payload.subject, body=payload.body
    )
    return await _run_analysis_pipeline(
        event_type="phishing_email",
        module="phishing",
        source=payload.source,
        raw_data=raw_data,
        indicators=indicators,
        system_prompt=PHISHING_SYSTEM_PROMPT,
        user_prompt=format_phishing_user_prompt(raw_data, indicators),
    )


@router.post("/url")
async def analyze_url(
    payload: UrlAnalysisRequest, _analyst: CurrentUser = Depends(require_role("analyst"))
) -> dict:
    """Full malicious URL analysis pipeline for a single URL."""
    raw_data = payload.model_dump(mode="json")
    indicators = analyze_url_heuristics(payload.url)
    return await _run_analysis_pipeline(
        event_type="malicious_url",
        module="url",
        source=payload.source,
        raw_data=raw_data,
        indicators=indicators,
        system_prompt=URL_SYSTEM_PROMPT,
        user_prompt=format_url_user_prompt(payload.url, indicators),
    )


@router.post("/impersonation")
async def analyze_impersonation(
    payload: ImpersonationAnalysisRequest, _analyst: CurrentUser = Depends(require_role("analyst"))
) -> dict:
    """Full digital impersonation analysis pipeline for a message."""
    raw_data = payload.model_dump(mode="json")
    indicators = analyze_impersonation_heuristics(
        message=payload.message, claimed_identity=payload.claimed_identity
    )
    return await _run_analysis_pipeline(
        event_type="impersonation_message",
        module="impersonation",
        source=payload.source,
        raw_data=raw_data,
        indicators=indicators,
        system_prompt=IMPERSONATION_SYSTEM_PROMPT,
        user_prompt=format_impersonation_user_prompt(raw_data, indicators),
    )


@router.post("/account-takeover")
async def analyze_account_takeover(
    payload: AccountTakeoverAnalysisRequest, _analyst: CurrentUser = Depends(require_role("analyst"))
) -> dict:
    """Full account takeover analysis pipeline for authentication logs."""
    raw_data = payload.model_dump(mode="json")
    indicators = analyze_auth_log_heuristics(payload.events)
    return await _run_analysis_pipeline(
        event_type="account_takeover",
        module="account_takeover",
        source=payload.source,
        raw_data=raw_data,
        indicators=indicators,
        system_prompt=ACCOUNT_TAKEOVER_SYSTEM_PROMPT,
        user_prompt=format_account_takeover_user_prompt(payload.events, indicators),
    )


@router.post("/network")
async def analyze_network(
    payload: NetworkAnalysisRequest, _analyst: CurrentUser = Depends(require_role("analyst"))
) -> dict:
    """Full network/API abuse analysis pipeline for flows and API logs."""
    raw_data = payload.model_dump(mode="json")
    indicators = analyze_network_heuristics(
        flows=payload.flows, api_logs=payload.api_logs
    )
    module = "network" if payload.flows else "api_abuse"
    return await _run_analysis_pipeline(
        event_type=module,
        module=module,
        source=payload.source,
        raw_data=raw_data,
        indicators=indicators,
        system_prompt=NETWORK_THREAT_SYSTEM_PROMPT,
        user_prompt=format_network_user_prompt(
            payload.flows, payload.api_logs, indicators
        ),
    )


def _finalize_deepfake_response(
    *,
    event_id: str,
    result: dict[str, Any],
    storage_path: str,
    file_name: str,
    content_type: str,
    llm_output: dict[str, Any],
) -> dict[str, Any]:
    """Persist the deepfake alert and build the unified API response."""
    raw_data = {
        "file_name": file_name,
        "content_type": content_type,
        "storage_path": storage_path,
        "media_type": result["media_type"],
        "method": result["method"],
        "simulated": result["simulated"],
    }
    alert_id = create_alert_in_db(
        event_id=event_id,
        module="deepfake",
        raw_data=raw_data,
        indicators=result["indicators"],
        score=result["risk_score"],
        severity=result["severity"],
        llm_output=llm_output,
    )
    alert = _fetch_alert_with_actions(alert_id)
    return {
        **result,
        "event_id": event_id,
        "alert_id": alert_id,
        "storage_path": storage_path,
        "explanation": alert.get("explanation"),
        "mitre_techniques": alert.get("mitre"),
        "recommended_actions": [
            {
                "action": action["action"],
                "automation_level": action["automation_level"],
                "requires_approval": action["requires_approval"],
            }
            for action in alert.get("recommended_actions", [])
        ],
    }


async def _run_deepfake_pipeline(
    *,
    event_id: str,
    file_bytes: bytes,
    file_name: str,
    content_type: str,
    storage_path: str,
) -> dict[str, Any]:
    """Shared deepfake pipeline: forensics, LLM explanation, alert, response."""
    try:
        result = analyze_media(file_bytes, file_name, content_type)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    llm_output = await call_openrouter(
        DEEPFAKE_SYSTEM_PROMPT,
        format_deepfake_user_prompt(result),
    )
    return _finalize_deepfake_response(
        event_id=event_id,
        result=result,
        storage_path=storage_path,
        file_name=file_name,
        content_type=content_type,
        llm_output=llm_output,
    )


@router.post("/media")
async def analyze_media_upload(
    file: UploadFile, _analyst: CurrentUser = Depends(require_role("analyst"))
) -> dict:
    """Full deepfake/media-forensics pipeline for an uploaded media file."""
    content_type = file.content_type or ""
    if not content_type.startswith(ANALYSIS_MEDIA_CONTENT_TYPE_PREFIXES):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must be an image, video, or audio upload",
        )

    file.file.seek(0, 2)
    size_bytes = file.file.tell()
    file.file.seek(0)
    if size_bytes > MAX_MEDIA_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File exceeds the maximum allowed size of 25 MB",
        )
    file_bytes = file.file.read()
    file_name = file.filename or "upload.bin"
    file.file.seek(0)  # the storage helper re-reads the spooled file

    event_id = _create_analysis_event(
        event_type="deepfake_media",
        source=ANALYSIS_MEDIA_SOURCE,
        raw_data={
            "file_name": file_name,
            "content_type": content_type,
            "size_bytes": size_bytes,
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

    return await _run_deepfake_pipeline(
        event_id=event_id,
        file_bytes=file_bytes,
        file_name=file_name,
        content_type=content_type,
        storage_path=media_record["storage_path"],
    )


@router.post("/media/event/{event_id}")
async def analyze_media_event(
    event_id: str, _analyst: CurrentUser = Depends(require_role("analyst"))
) -> dict:
    """Re-run the deepfake pipeline for an already-ingested media event."""
    try:
        response = (
            get_supabase()
            .table("media_files")
            .select("*")
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

    try:
        file_bytes = download_media(media["storage_path"])
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to download media file from storage",
        ) from exc

    return await _run_deepfake_pipeline(
        event_id=event_id,
        file_bytes=file_bytes,
        file_name=media.get("file_name") or "media",
        content_type=media.get("file_type") or "",
        storage_path=media["storage_path"],
    )


@router.get("/alerts")
def list_alerts(_user: dict = Depends(get_current_user)) -> dict:
    """Return all alerts, newest first."""
    try:
        response = (
            get_supabase()
            .table("alerts")
            .select("*")
            .order("created_at", desc=True)
            .execute()
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to query alerts",
        ) from exc

    rows = response.data or []
    return {"count": len(rows), "alerts": rows}


@router.get("/alerts/{alert_id}")
def get_alert(alert_id: str, _user: dict = Depends(get_current_user)) -> dict:
    """Return a single alert with its recommended actions."""
    return _fetch_alert_with_actions(alert_id)
