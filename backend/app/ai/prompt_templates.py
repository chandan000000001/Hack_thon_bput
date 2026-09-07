"""Prompt templates for the Explainable AI engine (Part 3)."""

import json
from typing import Any

PHISHING_SYSTEM_PROMPT = (
    "You are CYBERGUARD, an AI cybersecurity analyst. Analyze the provided "
    "email and heuristic indicators. Return a strict JSON object with keys: "
    "'explanation' (string, detailed human-readable paragraph starting with "
    "the risk level, e.g., 'High Risk: The sender domain...'), "
    "'mitre_techniques' (array of objects with 'id' and 'name', e.g., "
    "T1566.001), 'recommended_actions' (array of strings)."
)

URL_SYSTEM_PROMPT = (
    "You are CYBERGUARD, an AI cybersecurity analyst. Analyze the provided "
    "URL, its lexical characteristics, and any redirect indicators. Return a "
    "strict JSON object with keys: 'explanation' (string, detailed "
    "human-readable paragraph starting with the risk level, e.g., 'High "
    "Risk: The URL resolves to...'), 'mitre_techniques' (array of objects "
    "with 'id' and 'name', e.g., T1566.002), 'recommended_actions' (array "
    "of strings)."
)

IMPERSONATION_SYSTEM_PROMPT = (
    "You are CYBERGUARD, an AI cybersecurity analyst. Analyze the provided "
    "message and heuristic indicators for digital impersonation and social "
    "engineering. Return a strict JSON object with keys: 'explanation' "
    "(string, detailed human-readable paragraph), 'mitre_techniques' "
    "(array of objects with 'id' and 'name', e.g., T1656), "
    "'recommended_actions' (array of strings)."
)

ACCOUNT_TAKEOVER_SYSTEM_PROMPT = (
    "You are CYBERGUARD, an AI cybersecurity analyst. Analyze the provided "
    "authentication events and heuristic indicators for account takeover, "
    "impossible travel, and credential stuffing. Return a strict JSON "
    "object with keys: 'explanation' (string, detailed human-readable "
    "paragraph), 'mitre_techniques' (array of objects with 'id' and "
    "'name', e.g., T1110.003), 'recommended_actions' (array of strings)."
)

NETWORK_THREAT_SYSTEM_PROMPT = (
    "You are CYBERGUARD, an AI cybersecurity analyst. Analyze the provided "
    "network flows, API logs, and heuristic indicators for network "
    "anomalies, data exfiltration, and API abuse. Return a strict JSON "
    "object with keys: 'explanation' (string, detailed human-readable "
    "paragraph), 'mitre_techniques' (array of objects with 'id' and "
    "'name', e.g., T1041), 'recommended_actions' (array of strings)."
)

DEEPFAKE_SYSTEM_PROMPT = (
    "You are CYBERGUARD, an AI cybersecurity analyst specialising in media "
    "forensics. Given forensic indicators, the analysis method, and whether "
    "any component is simulated, return strict JSON with keys: "
    "'explanation' (human-readable paragraph stating the authenticity "
    "assessment and which indicators influenced it), 'mitre_techniques' "
    "(array of objects with id and name), 'recommended_actions' (array of "
    "strings; must include 'Flag multimedia for manual verification' "
    "whenever manipulation_probability is above 0.5)."
)

SOC_ASSISTANT_SYSTEM_PROMPT = (
    "You are the CYBERGUARD SOC Assistant, an AI-powered cybersecurity "
    "operations assistant. You help security analysts by answering "
    "questions about current threats, explaining alerts, suggesting "
    "investigation steps, and providing MITRE ATT&CK context. Use the "
    "provided alert context to give specific, actionable answers. Always "
    "be precise and cite alert IDs when relevant."
)


def format_phishing_user_prompt(payload: dict[str, Any], indicators: list[dict]) -> str:
    """Build the user prompt for phishing email analysis."""
    return (
        "Analyze the following email for phishing and social engineering "
        "indicators.\n\n"
        f"Email data:\n{json.dumps(payload, indent=2, default=str)}\n\n"
        f"Heuristic indicators detected:\n{json.dumps(indicators, indent=2)}\n\n"
        "Respond with the strict JSON object described in the system prompt."
    )


def format_url_user_prompt(url: str, indicators: list[dict]) -> str:
    """Build the user prompt for URL analysis."""
    return (
        "Analyze the following URL for malicious, deceptive, or spoofed "
        "website indicators.\n\n"
        f"URL: {json.dumps(url)}\n\n"
        f"Heuristic indicators detected:\n{json.dumps(indicators, indent=2)}\n\n"
        "Respond with the strict JSON object described in the system prompt."
    )


def format_impersonation_user_prompt(payload: dict[str, Any], indicators: list[dict]) -> str:
    """Build the user prompt for digital impersonation analysis."""
    return (
        "Analyze the following message for digital impersonation and "
        "social engineering indicators.\n\n"
        f"Message data:\n{json.dumps(payload, indent=2, default=str)}\n\n"
        f"Heuristic indicators detected:\n{json.dumps(indicators, indent=2)}\n\n"
        "Respond with the strict JSON object described in the system prompt."
    )


def format_account_takeover_user_prompt(auth_events: list[dict], indicators: list[dict]) -> str:
    """Build the user prompt for account takeover analysis."""
    return (
        "Analyze the following authentication events for account takeover, "
        "impossible travel, and credential stuffing indicators.\n\n"
        f"Authentication events:\n{json.dumps(auth_events, indent=2, default=str)}\n\n"
        f"Heuristic indicators detected:\n{json.dumps(indicators, indent=2)}\n\n"
        "Respond with the strict JSON object described in the system prompt."
    )


def format_network_user_prompt(
    flows: list[dict], api_logs: list[dict], indicators: list[dict]
) -> str:
    """Build the user prompt for network and API abuse analysis."""
    return (
        "Analyze the following network flows and API logs for network "
        "anomalies, data exfiltration, and API abuse indicators.\n\n"
        f"Network flows:\n{json.dumps(flows, indent=2, default=str)}\n\n"
        f"API logs:\n{json.dumps(api_logs, indent=2, default=str)}\n\n"
        f"Heuristic indicators detected:\n{json.dumps(indicators, indent=2)}\n\n"
        "Respond with the strict JSON object described in the system prompt."
    )


def format_deepfake_user_prompt(result: dict[str, Any]) -> str:
    """Build the user prompt for media forensics analysis.

    Injects the analysis method, the simulated flag, both scores and the
    forensic indicators into the prompt.
    """
    summary = {
        "analysis_method": result.get("method"),
        "simulated": result.get("simulated"),
        "media_type": result.get("media_type"),
        "authenticity_score": result.get("authenticity_score"),
        "manipulation_probability": result.get("manipulation_probability"),
        "indicators": result.get("indicators", []),
    }
    return (
        "Analyze the following media forensics result and write the "
        "explainability output for the alert.\n\n"
        f"Forensic result:\n{json.dumps(summary, indent=2, default=str)}\n\n"
        "Respond with the strict JSON object described in the system prompt. "
        "Remember to include 'Flag multimedia for manual verification' in "
        "'recommended_actions' if manipulation_probability is above 0.5."
    )
