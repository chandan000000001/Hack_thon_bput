"""Arq job implementations for Phase C-1 background analysis.

Two heavy pipelines run off the request thread:

    job_analyze_media(ctx, event_id)      — deepfake/media forensics
    job_analyze_bulk_logs(ctx, event_id)  — bulk auth-log / network ingestion

Each job is a thin wrapper around a `run_*` coroutine that contains the real
pipeline. The API layer calls the same `run_*` coroutine directly as the
synchronous fallback when Redis is unavailable, so queued and fallback paths
share one implementation and cannot drift.

Jobs are idempotent: if the event row is already 'completed' the job exits
immediately, so a redelivered or re-enqueued job never duplicates alerts.
Any exception marks the event 'failed' and is logged — never re-raised, so a
poison job cannot crash the worker loop.
"""

import logging
from typing import Any, Optional

from app.ai.llm_gateway import explain, make_cache_key, make_cache_key_from_bytes
from app.ai.prompt_templates import (
    ACCOUNT_TAKEOVER_SYSTEM_PROMPT,
    DEEPFAKE_SYSTEM_PROMPT,
    NETWORK_THREAT_SYSTEM_PROMPT,
    format_account_takeover_user_prompt,
    format_deepfake_user_prompt,
    format_network_user_prompt,
)
from app.core.storage import download_media
from app.core.supabase_client import get_supabase
from app.services.account_takeover_detector import analyze_auth_log_heuristics
from app.services.alert_service import create_alert_in_db
from app.services.deepfake_detector import analyze_media
from app.services.ml_inference import score_with_ml
from app.services.network_threat_detector import analyze_network_heuristics
from app.services.scoring_service import get_severity

logger = logging.getLogger("cyberguard.jobs")


async def _load_event(client: Any, event_id: str) -> Optional[dict[str, Any]]:
    """Fetch the event row, or None when it does not exist."""
    response = (
        client.table("events")
        .select("*")
        .eq("id", event_id)
        .limit(1)
        .execute()
    )
    rows = response.data or []
    return rows[0] if rows else None


def _mark_event(client: Any, event_id: str, status: str) -> None:
    """Best-effort event status update ('completed' or 'failed')."""
    try:
        client.table("events").update({"status": status}).eq("id", event_id).execute()
    except Exception:
        logger.exception("Failed to mark event %s as %s", event_id, status)


async def run_media_analysis(event_id: str) -> str:
    """Deepfake/media pipeline for an already-ingested media event.

    Returns the final event status ('completed' or 'failed'); idempotent for
    events already in the 'completed' state.
    """
    client = get_supabase()
    try:
        event = await _load_event(client, event_id)
    except Exception:
        logger.exception("Failed to load event %s for media analysis", event_id)
        return "failed"

    if event is None:
        logger.error("Event %s not found; media analysis aborted", event_id)
        return "failed"
    if event.get("status") == "completed":
        logger.info("Event %s already analyzed; job skipped (idempotent)", event_id)
        return "completed"

    try:
        media_response = (
            client.table("media_files")
            .select("*")
            .eq("event_id", event_id)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        media_rows = media_response.data or []
        if not media_rows:
            raise ValueError(f"No media_files row exists for event {event_id}")
        media = media_rows[0]

        file_bytes = download_media(media["storage_path"])
        result = analyze_media(
            file_bytes,
            media.get("file_name") or "media",
            media.get("file_type") or "",
        )

        explained = await explain(
            "deepfake",
            DEEPFAKE_SYSTEM_PROMPT,
            format_deepfake_user_prompt(result),
            make_cache_key_from_bytes("deepfake", file_bytes),
        )

        raw_data = {
            "file_name": media.get("file_name"),
            "content_type": media.get("file_type"),
            "storage_path": media.get("storage_path"),
            "media_type": result["media_type"],
            "method": result["method"],
            "simulated": result["simulated"],
        }
        create_alert_in_db(
            event_id=event_id,
            module="deepfake",
            raw_data=raw_data,
            indicators=result["indicators"],
            score=result["risk_score"],
            severity=result["severity"],
            llm_output=explained["explanation"],
            org_id=event["org_id"],
        )
        _mark_event(client, event_id, "completed")
        return "completed"
    except Exception:
        logger.exception("Background media analysis failed for event %s", event_id)
        _mark_event(client, event_id, "failed")
        return "failed"


async def run_bulk_log_analysis(event_id: str) -> str:
    """Bulk auth-log / network pipeline for an already-ingested batch event.

    Returns the final event status ('completed' or 'failed'); idempotent for
    events already in the 'completed' state.
    """
    client = get_supabase()
    try:
        event = await _load_event(client, event_id)
    except Exception:
        logger.exception("Failed to load event %s for bulk analysis", event_id)
        return "failed"

    if event is None:
        logger.error("Event %s not found; bulk analysis aborted", event_id)
        return "failed"
    if event.get("status") == "completed":
        logger.info("Event %s already analyzed; job skipped (idempotent)", event_id)
        return "completed"

    try:
        raw_data = event.get("raw_data") or {}
        kind = raw_data.get("kind")
        rows = raw_data.get("rows") or []

        if kind == "auth-log":
            module = "account_takeover"
            indicators = analyze_auth_log_heuristics(rows)
            system_prompt = ACCOUNT_TAKEOVER_SYSTEM_PROMPT
            user_prompt = format_account_takeover_user_prompt(rows, indicators)
        elif kind == "network":
            module = "network"
            indicators = analyze_network_heuristics(flows=rows, api_logs=[])
            system_prompt = NETWORK_THREAT_SYSTEM_PROMPT
            user_prompt = format_network_user_prompt(rows, [], indicators)
        else:
            raise ValueError(f"Unsupported bulk event kind: {kind!r}")

        _heuristic_score, hybrid_score, _ml_probability = score_with_ml(indicators)
        severity = get_severity(hybrid_score)

        explained = await explain(
            module, system_prompt, user_prompt, make_cache_key(module, raw_data)
        )

        create_alert_in_db(
            event_id=event_id,
            module=module,
            raw_data=raw_data,
            indicators=indicators,
            score=hybrid_score,
            severity=severity,
            llm_output=explained["explanation"],
            org_id=event["org_id"],
        )
        _mark_event(client, event_id, "completed")
        return "completed"
    except Exception:
        logger.exception("Background bulk log analysis failed for event %s", event_id)
        _mark_event(client, event_id, "failed")
        return "failed"


async def job_analyze_media(ctx: dict, event_id: str) -> str:
    """Arq entry point: deepfake/media forensics for one event."""
    logger.info("job_analyze_media started for event %s", event_id)
    return await run_media_analysis(event_id)


async def job_analyze_bulk_logs(ctx: dict, event_id: str) -> str:
    """Arq entry point: bulk auth-log / network analysis for one event."""
    logger.info("job_analyze_bulk_logs started for event %s", event_id)
    return await run_bulk_log_analysis(event_id)
