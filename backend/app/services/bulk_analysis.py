"""Bulk auth-log / network analysis pipeline for already-ingested batch events.

Formerly the synchronous fallback for the (now removed) Arq background
worker; it is now the only execution path — POST /events/bulk runs it
directly on the request thread. Idempotent for events already in the
'completed' state; any exception marks the event 'failed' and is logged.
"""

import logging
from typing import Any, Optional

from app.ai.llm_gateway import explain, make_cache_key
from app.ai.prompt_templates import (
    ACCOUNT_TAKEOVER_SYSTEM_PROMPT,
    NETWORK_THREAT_SYSTEM_PROMPT,
    format_account_takeover_user_prompt,
    format_network_user_prompt,
    format_risk_instruction,
)
from app.core.asyncbridge import to_thread
from app.core.supabase_client import get_supabase
from app.services.account_takeover_detector import analyze_auth_log_heuristics
from app.services.alert_service import create_alert_in_db
from app.services.ml_inference import score_with_ml
from app.services.network_threat_detector import analyze_network_heuristics
from app.services.scoring_service import get_severity

logger = logging.getLogger("cyberguard.bulk_analysis")


async def _load_event(client: Any, event_id: str) -> Optional[dict[str, Any]]:
    """Fetch the event row, or None when it does not exist."""
    response = await to_thread(
        lambda: client.table("events").select("*").eq("id", event_id).limit(1).execute()
    )
    rows = response.data or []
    return rows[0] if rows else None


async def _mark_event(client: Any, event_id: str, status: str) -> None:
    """Best-effort event status update ('completed' or 'failed')."""
    try:
        await to_thread(
            lambda: client.table("events").update({"status": status}).eq("id", event_id).execute()
        )
    except Exception:
        logger.exception("Failed to mark event %s as %s", event_id, status)


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
        logger.info("Event %s already analyzed; skipped (idempotent)", event_id)
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

        risk_inst = format_risk_instruction(hybrid_score, severity)
        if risk_inst and risk_inst not in user_prompt:
            user_prompt = f"{user_prompt}{risk_inst}"

        explained = await explain(
            module=module,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            cache_key=make_cache_key(module, raw_data),
            json_mode=True,
            expected_band=severity,
            risk_score=hybrid_score,
        )

        await create_alert_in_db(
            event_id=event_id,
            module=module,
            raw_data=raw_data,
            indicators=indicators,
            score=hybrid_score,
            severity=severity,
            llm_output=explained["explanation"],
            org_id=event["org_id"],
        )
        await _mark_event(client, event_id, "completed")
        return "completed"
    except Exception:
        logger.exception("Bulk log analysis failed for event %s", event_id)
        await _mark_event(client, event_id, "failed")
        return "failed"
