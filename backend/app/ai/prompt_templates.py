"""Prompt templates for the Explainable AI engine (Part 3)."""

import json
from typing import Any

PHISHING_SYSTEM_PROMPT = (
    "You are CYBERGUARD, an AI cybersecurity analyst. Analyze the provided "
    "email and heuristic indicators. Return a strict JSON object with keys: "
    "'explanation' (string, detailed human-readable paragraph starting with "
    "the exact severity band, e.g., '<Band> Risk: ...'), "
    "'mitre_techniques' (array of objects with 'id' and 'name', e.g., "
    "T1566.001), 'recommended_actions' (array of strings)."
)

URL_SYSTEM_PROMPT = (
    "You are CYBERGUARD, an AI cybersecurity analyst. Analyze the provided "
    "URL, its lexical characteristics, and any redirect indicators. Return a "
    "strict JSON object with keys: 'explanation' (string, detailed "
    "human-readable paragraph starting with the exact severity band, e.g., '<Band> "
    "Risk: ...'), 'mitre_techniques' (array of objects "
    "with 'id' and 'name', e.g., T1566.002), 'recommended_actions' (array "
    "of strings)."
)

IMPERSONATION_SYSTEM_PROMPT = (
    "You are CYBERGUARD, an AI cybersecurity analyst. Analyze the provided "
    "message and heuristic indicators for digital impersonation and social "
    "engineering. Return a strict JSON object with keys: 'explanation' "
    "(string, detailed human-readable paragraph starting with '<Band> Risk:'), 'mitre_techniques' "
    "(array of objects with 'id' and 'name', e.g., T1656), "
    "'recommended_actions' (array of strings)."
)

ACCOUNT_TAKEOVER_SYSTEM_PROMPT = (
    "You are CYBERGUARD, an AI cybersecurity analyst. Analyze the provided "
    "authentication events and heuristic indicators for account takeover, "
    "impossible travel, and credential stuffing. Return a strict JSON "
    "object with keys: 'explanation' (string, detailed human-readable "
    "paragraph starting with '<Band> Risk:'), 'mitre_techniques' (array of objects with 'id' and "
    "'name', e.g., T1110.003), 'recommended_actions' (array of strings)."
)

NETWORK_THREAT_SYSTEM_PROMPT = (
    "You are CYBERGUARD, an AI cybersecurity analyst. Analyze the provided "
    "network flows, API logs, and heuristic indicators for network "
    "anomalies, data exfiltration, and API abuse. Return a strict JSON "
    "object with keys: 'explanation' (string, detailed human-readable "
    "paragraph starting with '<Band> Risk:'), 'mitre_techniques' (array of objects with 'id' and "
    "'name', e.g., T1041), 'recommended_actions' (array of strings)."
)

DEEPFAKE_SYSTEM_PROMPT = (
    "You are CYBERGUARD, an AI cybersecurity analyst specialising in media "
    "forensics. Given forensic indicators, the analysis method, and whether "
    "any component is simulated, return strict JSON with keys: "
    "'explanation' (human-readable paragraph starting with '<Band> Risk:' stating the authenticity "
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
    "provided alert context to give specific, actionable answers. "
    "The first sentence of your response must begin with exactly '<Band> Risk:' "
    "matching the assessed context severity, and your narrative must not contradict it. "
    "Always be precise and cite alert IDs when relevant."
)


def format_risk_instruction(risk_score: int | None = None, severity: str | None = None) -> str:
    """Format assessment injection and leading band instruction."""
    if not severity:
        return ""
    band = severity.capitalize()
    score_part = f" (risk score: {risk_score}/100)" if risk_score is not None else ""
    return (
        f"\n\nASSESSED RISK SEVERITY: {band} Risk{score_part}.\n"
        f"CRITICAL INSTRUCTION: The very first sentence of your explanation MUST begin with exactly "
        f"'{band} Risk:' using the injected band, and the narrative must not contradict it."
    )


def format_phishing_user_prompt(
    payload: dict[str, Any],
    indicators: list[dict],
    risk_score: int | None = None,
    severity: str | None = None,
) -> str:
    """Build the user prompt for phishing email analysis."""
    risk_inst = format_risk_instruction(risk_score, severity)
    # Surface the script-detection result so the narrative references the
    # language (phishing_detector emits a type='language' indicator).
    detected_lang = next(
        (str(i.get("value")) for i in indicators if i.get("type") == "language" and i.get("value")),
        "en",
    )
    lang_names = {"hi": "Hindi", "te": "Telugu", "or": "Odia", "roman": "Romanised Indic"}
    lang_name = lang_names.get(detected_lang, "English")
    lang_inst = (
        f"\n\nDetected language: {lang_name} ({detected_lang}). The explanation "
        f"must reference this language and quote any Indic-language indicator "
        f"phrases verbatim alongside their meaning."
        if detected_lang != "en"
        else ""
    )
    return (
        "Analyze the following email for phishing and social engineering "
        "indicators.\n\n"
        f"Email data:\n{json.dumps(payload, indent=2, default=str)}\n\n"
        f"Heuristic indicators detected:\n{json.dumps(indicators, indent=2)}\n\n"
        "Respond with the strict JSON object described in the system prompt."
        f"{lang_inst}{risk_inst}"
    )


def format_url_user_prompt(
    url: str,
    indicators: list[dict],
    risk_score: int | None = None,
    severity: str | None = None,
) -> str:
    """Build the user prompt for URL analysis."""
    risk_inst = format_risk_instruction(risk_score, severity)
    return (
        "Analyze the following URL for malicious, deceptive, or spoofed "
        "website indicators.\n\n"
        f"URL: {json.dumps(url)}\n\n"
        f"Heuristic indicators detected:\n{json.dumps(indicators, indent=2)}\n\n"
        "Respond with the strict JSON object described in the system prompt."
        f"{risk_inst}"
    )


def format_impersonation_user_prompt(
    payload: dict[str, Any],
    indicators: list[dict],
    risk_score: int | None = None,
    severity: str | None = None,
) -> str:
    """Build the user prompt for digital impersonation analysis."""
    risk_inst = format_risk_instruction(risk_score, severity)
    return (
        "Analyze the following message for digital impersonation and "
        "social engineering indicators.\n\n"
        f"Message data:\n{json.dumps(payload, indent=2, default=str)}\n\n"
        f"Heuristic indicators detected:\n{json.dumps(indicators, indent=2)}\n\n"
        "Respond with the strict JSON object described in the system prompt."
        f"{risk_inst}"
    )


def format_account_takeover_user_prompt(
    auth_events: list[dict],
    indicators: list[dict],
    risk_score: int | None = None,
    severity: str | None = None,
) -> str:
    """Build the user prompt for account takeover analysis."""
    risk_inst = format_risk_instruction(risk_score, severity)
    return (
        "Analyze the following authentication events for account takeover, "
        "impossible travel, and credential stuffing indicators.\n\n"
        f"Authentication events:\n{json.dumps(auth_events, indent=2, default=str)}\n\n"
        f"Heuristic indicators detected:\n{json.dumps(indicators, indent=2)}\n\n"
        "Respond with the strict JSON object described in the system prompt."
        f"{risk_inst}"
    )


def format_network_user_prompt(
    flows: list[dict],
    api_logs: list[dict],
    indicators: list[dict],
    risk_score: int | None = None,
    severity: str | None = None,
) -> str:
    """Build the user prompt for network and API abuse analysis."""
    risk_inst = format_risk_instruction(risk_score, severity)
    return (
        "Analyze the following network flows and API logs for network "
        "anomalies, data exfiltration, and API abuse indicators.\n\n"
        f"Network flows:\n{json.dumps(flows, indent=2, default=str)}\n\n"
        f"API logs:\n{json.dumps(api_logs, indent=2, default=str)}\n\n"
        f"Heuristic indicators detected:\n{json.dumps(indicators, indent=2)}\n\n"
        "Respond with the strict JSON object described in the system prompt."
        f"{risk_inst}"
    )


def format_deepfake_user_prompt(
    result: dict[str, Any],
    risk_score: int | None = None,
    severity: str | None = None,
) -> str:
    """Build the user prompt for media forensics analysis.

    Injects the analysis method, the simulated flag, both scores and the
    forensic indicators into the prompt.
    """
    final_score = risk_score if risk_score is not None else result.get("risk_score")
    final_sev = severity if severity is not None else result.get("severity")
    summary = {
        "analysis_method": result.get("method"),
        "simulated": result.get("simulated"),
        "media_type": result.get("media_type"),
        "authenticity_score": result.get("authenticity_score"),
        "manipulation_probability": result.get("manipulation_probability"),
        "risk_score": final_score,
        "severity": final_sev,
        "indicators": result.get("indicators", []),
    }
    risk_inst = format_risk_instruction(final_score, final_sev)
    return (
        "Analyze the following media forensics result and write the "
        "explainability output for the alert.\n\n"
        f"Forensic result:\n{json.dumps(summary, indent=2, default=str)}\n\n"
        "Respond with the strict JSON object described in the system prompt. "
        "Remember to include 'Flag multimedia for manual verification' in "
        "'recommended_actions' if manipulation_probability is above 0.5."
        f"{risk_inst}"
    )
