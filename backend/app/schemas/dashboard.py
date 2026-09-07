"""Pydantic schema for the dashboard summary endpoint (Part 6)."""

from pydantic import BaseModel


class DashboardSummary(BaseModel):
    """Aggregated metrics for the cybersecurity command dashboard."""

    total_events_analyzed: int
    threats_detected: int
    phishing_attempts: int
    impersonation_attempts: int
    suspected_deepfakes: int
    account_takeover_attempts: int
    network_threats: int
    api_abuse_attempts: int
    risk_distribution: list[dict]
    threat_categories: list[dict]
    attack_timeline: list[dict]
    top_targeted_users: list[dict]
    top_targeted_services: list[dict]
    recent_alerts: list
    incident_summary: dict
