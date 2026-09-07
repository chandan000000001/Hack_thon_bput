"""Account takeover heuristic detector (Part 4).

Rule-based analysis of authentication log events. Each event is expected
to carry: user, ip, location, device, status, timestamp. No ML or LLM
logic lives here.
"""

from collections import defaultdict
from datetime import datetime, timezone

FAILED_STATUSES = {"failed", "failure", "failure ", "denied", "denied "}
SUCCESS_STATUSES = {"success", "successful", "passed"}

IMPOSSIBLE_TRAVEL_WINDOW_MINUTES = 60
CONSECUTIVE_FAILURES_BEFORE_SUCCESS = 2
FAILED_BURST_THRESHOLD = 3  # flag when a user has 3 OR MORE failed attempts

SUSPICIOUS_DEVICE_TOKENS = ("linux", "unknown")


def _parse_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _is_successful(event: dict) -> bool:
    return str(event.get("status", "")).strip().lower() in SUCCESS_STATUSES


def _is_failed(event: dict) -> bool:
    return str(event.get("status", "")).strip().lower() in FAILED_STATUSES


def _group_by_user(events: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for event in events:
        user = str(event.get("user", "")).strip()
        if user:
            grouped[user].append(event)
    for user_events in grouped.values():
        user_events.sort(
            key=lambda event: _parse_timestamp(event.get("timestamp"))
            or datetime.min.replace(tzinfo=timezone.utc)
        )
    return grouped


def _check_failed_burst(user: str, user_events: list[dict]) -> list[dict]:
    failed_count = sum(1 for event in user_events if _is_failed(event))
    if failed_count >= FAILED_BURST_THRESHOLD:
        return [
            {
                "type": "failed_login_burst",
                "value": f"{user}: {failed_count} failed logins",
                "severity": "high",
                "description": (
                    f"User '{user}' has {failed_count} failed login attempts "
                    f"(threshold {FAILED_BURST_THRESHOLD}), consistent with a "
                    "password spray or brute force attempt."
                ),
            }
        ]
    return []


def _check_impossible_travel(user: str, user_events: list[dict]) -> list[dict]:
    successful = [
        (event, _parse_timestamp(event.get("timestamp")))
        for event in user_events
        if _is_successful(event)
    ]
    for event, parsed_time in successful:
        if parsed_time is None:
            continue
        for previous_event, previous_time in successful:
            if previous_event is event or previous_time is None:
                continue
            delta_minutes = abs((parsed_time - previous_time).total_seconds()) / 60
            location_a = str(event.get("location", "")).strip().lower()
            location_b = str(previous_event.get("location", "")).strip().lower()
            if location_a and location_b and location_a != location_b and 0 < delta_minutes < IMPOSSIBLE_TRAVEL_WINDOW_MINUTES:
                return [
                    {
                        "type": "impossible_travel",
                        "value": f"{user}: {location_b} -> {location_a}",
                        "severity": "critical",
                        "description": (
                            f"User '{user}' has successful logins from "
                            f"'{previous_event.get('location')}' and "
                            f"'{event.get('location')}' only "
                            f"{delta_minutes:.0f} minutes apart."
                        ),
                    }
                ]
    return []


def _check_new_device(user: str, user_events: list[dict]) -> list[dict]:
    indicators: list[dict] = []
    seen_devices: set[str] = set()
    for event in user_events:
        device = str(event.get("device", "")).strip()
        if not device or not _is_successful(event):
            continue
        device_key = device.lower()
        if device_key not in seen_devices and seen_devices:
            indicators.append(
                {
                    "type": "new_device",
                    "value": f"{user}: {device}",
                    "severity": "medium",
                    "description": (
                        f"New or unknown device: successful login for user "
                        f"'{user}' from a device not seen before: '{device}'."
                    ),
                }
            )
        seen_devices.add(device_key)
        lowered = device_key
        if any(token in lowered for token in SUSPICIOUS_DEVICE_TOKENS) and not any(
            indicator["value"] == f"{user}: {device}" for indicator in indicators
        ):
            indicators.append(
                {
                    "type": "suspicious_device",
                    "value": f"{user}: {device}",
                    "severity": "medium",
                    "description": (
                        f"Successful login for user '{user}' from an "
                        f"unrecognized agent type: '{device}'."
                    ),
                }
            )
    return indicators


def _check_success_after_failures(user: str, user_events: list[dict]) -> list[dict]:
    consecutive_failures = 0
    for event in user_events:
        if _is_failed(event):
            consecutive_failures += 1
            continue
        if _is_successful(event) and consecutive_failures >= CONSECUTIVE_FAILURES_BEFORE_SUCCESS:
            return [
                {
                    "type": "success_after_failures",
                    "value": f"{user}: {consecutive_failures} failures then success",
                    "severity": "high",
                    "description": (
                        f"Successful login for user '{user}' occurred after "
                        f"{consecutive_failures} consecutive failed attempts, a "
                        "pattern consistent with a credential stuffing or "
                        "brute force success."
                    ),
                }
            ]
        consecutive_failures = 0
    return []


def analyze_auth_log_heuristics(events: list[dict]) -> list[dict]:
    """Run all account takeover heuristics and return the indicator list."""
    indicators: list[dict] = []
    for user, user_events in _group_by_user(events).items():
        indicators.extend(_check_failed_burst(user, user_events))
        indicators.extend(_check_impossible_travel(user, user_events))
        indicators.extend(_check_new_device(user, user_events))
        indicators.extend(_check_success_after_failures(user, user_events))
    return indicators
