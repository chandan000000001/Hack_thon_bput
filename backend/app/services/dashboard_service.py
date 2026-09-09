"""Dashboard summary service (Part 6).

Supabase's REST API does not support SQL GROUP BY, so this service fetch
the relevant rows and performs all grouping/counting in Python. This is
acceptable for a prototype with moderate data volume.
"""

from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import HTTPException, status

from app.core.supabase_client import get_supabase

SEVERITY_ORDER = ["safe", "low", "medium", "high", "critical"]
SEVERITY_COLORS = {
    "safe": "#10b981",
    "low": "#eab308",
    "medium": "#f59e0b",
    "high": "#f97316",
    "critical": "#ef4444",
}
SEVERITY_RANK = {name: rank for rank, name in enumerate(SEVERITY_ORDER)}
MODULE_ORDER = [
    "phishing",
    "url",
    "impersonation",
    "deepfake",
    "account_takeover",
    "network",
    "api_abuse",
]
INCIDENT_STATUSES = ["open", "investigating", "contained", "closed"]
TIMELINE_HOURS = 24


def _parse_ts(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _build_attack_timeline(
    alerts: list[dict], events: list[dict], now: datetime
) -> list[dict[str, Any]]:
    """Bucket alerts and events into the last 24 hourly slots."""
    buckets: dict[str, dict[str, Any]] = {}
    for hours_ago in range(TIMELINE_HOURS - 1, -1, -1):
        slot_start = (now - timedelta(hours=hours_ago)).replace(
            minute=0, second=0, microsecond=0
        )
        key = slot_start.strftime("%Y-%m-%d %H")
        buckets[key] = {
            "hour": slot_start.strftime("%H:00"),
            "threats": 0,
            "events": 0,
        }

    for alert in alerts:
        parsed = _parse_ts(alert.get("created_at"))
        if parsed is None:
            continue
        key = parsed.replace(minute=0, second=0, microsecond=0).strftime("%Y-%m-%d %H")
        if key in buckets:
            buckets[key]["threats"] += 1

    for event in events:
        parsed = _parse_ts(event.get("created_at"))
        if parsed is None:
            continue
        key = parsed.replace(minute=0, second=0, microsecond=0).strftime("%Y-%m-%d %H")
        if key in buckets:
            buckets[key]["events"] += 1

    return list(buckets.values())


def _top_targeted_users(alerts: list[dict]) -> list[dict[str, Any]]:
    """Group alerts by target_user; input is ordered newest first."""
    stats: dict[str, dict[str, Any]] = {}
    for alert in alerts:
        target_user = alert.get("target_user")
        if not target_user:
            continue
        entry = stats.setdefault(
            target_user, {"attacks": 0, "last_attack": alert.get("created_at")}
        )
        entry["attacks"] += 1
    ranked = sorted(stats.items(), key=lambda item: item[1]["attacks"], reverse=True)
    return [
        {"user": user, "attacks": entry["attacks"], "last_attack": entry["last_attack"]}
        for user, entry in ranked[:5]
    ]


def _top_targeted_services(alerts: list[dict]) -> list[dict[str, Any]]:
    """Group alerts by target_service with the highest severity seen."""
    stats: dict[str, dict[str, Any]] = {}
    for alert in alerts:
        target_service = alert.get("target_service")
        if not target_service:
            continue
        entry = stats.setdefault(
            target_service, {"attacks": 0, "risk_rank": -1, "risk_level": None}
        )
        entry["attacks"] += 1
        rank = SEVERITY_RANK.get(alert.get("severity"), -1)
        if rank > entry["risk_rank"]:
            entry["risk_rank"] = rank
            entry["risk_level"] = alert.get("severity")
    ranked = sorted(stats.items(), key=lambda item: item[1]["attacks"], reverse=True)
    return [
        {
            "service": service,
            "attacks": entry["attacks"],
            "risk_level": entry["risk_level"],
        }
        for service, entry in ranked[:5]
    ]


async def get_dashboard_summary(org_id: str) -> dict[str, Any]:
    """Build the complete dashboard summary for one organization.

    Every query is filtered by org_id — the service-role client bypasses RLS,
    so this filter is the tenant isolation for dashboard counts, group-bys
    and the recent-alerts feed.
    """
    client = get_supabase()
    try:
        alerts = (
            client.table("alerts")
            .select("id, module, severity, target_user, target_service, created_at")
            .eq("org_id", org_id)
            .order("created_at", desc=True)
            .execute()
            .data
            or []
        )
        events = (
            client.table("events")
            .select("id, created_at")
            .eq("org_id", org_id)
            .execute()
            .data
            or []
        )
        incidents = (
            client.table("incidents")
            .select("id, status")
            .eq("org_id", org_id)
            .execute()
            .data
            or []
        )
        recent_alerts = (
            client.table("alerts")
            .select("*")
            .eq("org_id", org_id)
            .order("created_at", desc=True)
            .limit(10)
            .execute()
            .data
            or []
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to load dashboard data",
        ) from exc

    module_counts = Counter(alert.get("module") for alert in alerts)
    severity_counts = Counter(alert.get("severity") for alert in alerts)

    risk_distribution = [
        {
            "name": severity,
            "value": severity_counts.get(severity, 0),
            "color": SEVERITY_COLORS[severity],
        }
        for severity in SEVERITY_ORDER
    ]
    threat_categories = [
        {"name": module, "count": module_counts.get(module, 0)}
        for module in MODULE_ORDER
    ]

    incident_summary = {status_name: 0 for status_name in INCIDENT_STATUSES}
    for incident in incidents:
        incident_status = incident.get("status")
        if incident_status in incident_summary:
            incident_summary[incident_status] += 1

    return {
        "total_events_analyzed": len(events),
        "threats_detected": len(alerts),
        "phishing_attempts": module_counts.get("phishing", 0),
        "impersonation_attempts": module_counts.get("impersonation", 0),
        "suspected_deepfakes": module_counts.get("deepfake", 0),
        "account_takeover_attempts": module_counts.get("account_takeover", 0),
        "network_threats": module_counts.get("network", 0),
        "api_abuse_attempts": module_counts.get("api_abuse", 0),
        "risk_distribution": risk_distribution,
        "threat_categories": threat_categories,
        "attack_timeline": _build_attack_timeline(alerts, events, datetime.now(timezone.utc)),
        "top_targeted_users": _top_targeted_users(alerts),
        "top_targeted_services": _top_targeted_services(alerts),
        "recent_alerts": recent_alerts,
        "incident_summary": incident_summary,
    }
