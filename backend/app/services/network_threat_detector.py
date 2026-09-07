"""Network and API abuse heuristic detector (Part 4, hybrid in ML Step 3).

Rule-based analysis of network flows and API logs. Flow keys:
source_ip, dest_ip, port, bytes_out, protocol. API log keys: endpoint,
method, source_ip, status_code.

ML Step 3: each flow is mapped to the 4 KDD99-SF training features
(ml/data/train_network.csv header f0..f3) and scored by the trained
network_xgb.pkl model; the resulting probability is attached as an
ml_model indicator and blended by callers via
ml_inference.score_with_ml.
"""

import math
from collections import Counter
from typing import Any

from app.services.ml_inference import ml_indicator, predict_network

EXFIL_BYTES_THRESHOLD = 10_000_000
SUSPICIOUS_PORTS = {4444, 8888, 1337, 31337, 6667}
API_RATE_ABUSE_THRESHOLD = 50  # flag when a source IP exceeds this many requests
API_AUTH_FAILURE_THRESHOLD = 5  # flag when 401 count from one IP exceeds this


def _to_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _check_flows(flows: list[dict]) -> list[dict]:
    indicators: list[dict] = []
    for flow in flows:
        source_ip = str(flow.get("source_ip", "unknown"))
        dest_ip = str(flow.get("dest_ip", "unknown"))

        bytes_out = _to_int(flow.get("bytes_out"))
        if bytes_out > EXFIL_BYTES_THRESHOLD:
            indicators.append(
                {
                    "type": "potential_exfiltration",
                    "value": f"{source_ip} -> {dest_ip}: {bytes_out} bytes out",
                    "severity": "high",
                    "description": (
                        f"Flow from {source_ip} to {dest_ip} transferred "
                        f"{bytes_out} bytes outbound (threshold "
                        f"{EXFIL_BYTES_THRESHOLD}), a potential data exfiltration."
                    ),
                }
            )

        port = _to_int(flow.get("port"))
        if port in SUSPICIOUS_PORTS:
            indicators.append(
                {
                    "type": "suspicious_port",
                    "value": f"{source_ip} -> {dest_ip}:{port}",
                    "severity": "critical",
                    "description": (
                        f"Flow from {source_ip} to {dest_ip} uses port {port}, "
                        "commonly associated with C2 channels or backdoors."
                    ),
                }
            )
    return indicators


def _check_api_rate_abuse(api_logs: list[dict]) -> list[dict]:
    request_counts = Counter(
        str(log.get("source_ip")).strip()
        for log in api_logs
        if log.get("source_ip")
    )
    indicators: list[dict] = []
    for source_ip, count in request_counts.items():
        if count > API_RATE_ABUSE_THRESHOLD:
            indicators.append(
                {
                    "type": "api_rate_abuse",
                    "value": f"{source_ip}: {count} requests",
                    "severity": "high",
                    "description": (
                        f"Source IP {source_ip} issued {count} API requests "
                        f"(threshold {API_RATE_ABUSE_THRESHOLD}), indicating "
                        "rate abuse or automated scanning."
                    ),
                }
            )
    return indicators


def _check_api_auth_failures(api_logs: list[dict]) -> list[dict]:
    failure_counts = Counter(
        str(log.get("source_ip")).strip()
        for log in api_logs
        if _to_int(log.get("status_code")) == 401 and log.get("source_ip")
    )
    indicators: list[dict] = []
    for source_ip, count in failure_counts.items():
        if count > API_AUTH_FAILURE_THRESHOLD:
            indicators.append(
                {
                    "type": "repeated_api_auth_failures",
                    "value": f"{source_ip}: {count} x 401",
                    "severity": "high",
                    "description": (
                        f"Source IP {source_ip} produced {count} HTTP 401 "
                        f"responses (threshold {API_AUTH_FAILURE_THRESHOLD}), "
                        "indicating repeated API authentication failures."
                    ),
                }
            )
    return indicators


# ---------------------------------------------------------------------------
# ML feature mapping (ML Step 3)
# ---------------------------------------------------------------------------
# The trained network model expects the 4 features of the KDD99 "SF" subset,
# in the exact column order of ml/data/train_network.csv (header f0..f3):
#   f0 = log(duration + 0.1)   duration of the connection
#   f1 = service               KDD service name (label-encoded at training)
#   f2 = log(src_bytes + 0.1)  bytes from source to destination
#   f3 = log(dst_bytes + 0.1)  bytes from destination to source
#
# Mapping from our flow dicts (source_ip, dest_ip, port, bytes_out, protocol):
#   f0 -> flows are instantaneous records with no duration field -> 0.0,
#         i.e. log(0 + 0.1) = ln(0.1) (documented constant)
#   f1 -> derived from the destination port via PORT_TO_SERVICE below;
#         unknown ports map to KDD's generic 'other' service
#   f2 -> flow bytes_out (same semantics: bytes sent by the source)
#   f3 -> flow dicts carry no response bytes -> 0.0 -> log(0 + 0.1)
# If bytes_out is missing, src_bytes cannot be derived and ML is skipped
# for that event (heuristic indicators are kept).

PORT_TO_SERVICE = {
    80: "http", 443: "http", 8080: "http", 8000: "http", 8008: "http",
    25: "smtp", 587: "smtp", 465: "smtp",
    21: "ftp", 20: "ftp_data",
    23: "telnet", 22: "ssh", 194: "IRC", 6000: "X11", 53: "domain",
    13: "discard", 110: "pop_3", 109: "pop_3", 143: "imap4",
    513: "login", 514: "login", 70: "gopher",
}
DEFAULT_SERVICE = "other"
LOG_ZERO = math.log(0.1)  # ln(0.1) — the log transform's floor for a 0 value


def flow_to_training_features(flow: dict) -> list | None:
    """Map a flow dict to the 4 KDD99-SF training features, or None when the
    required bytes_out value is missing/invalid (ML skipped for the event)."""
    bytes_out = flow.get("bytes_out")
    try:
        bytes_out = float(bytes_out)
    except (TypeError, ValueError):
        return None

    port = flow.get("port")
    try:
        service = PORT_TO_SERVICE.get(int(port), DEFAULT_SERVICE)
    except (TypeError, ValueError):
        service = DEFAULT_SERVICE

    return [LOG_ZERO, service, math.log(bytes_out + 0.1), LOG_ZERO]


def analyze_network_heuristics(flows: list[dict], api_logs: list[dict]) -> list[dict]:
    """Run all network/API heuristics and return the indicator list.

    Hybrid mode (ML Step 3): flows are mapped to the KDD99-SF training
    features and scored by the trained network model; when a probability is
    available the ml_model indicator is appended and callers obtain the
    blended score via ml_inference.score_with_ml. When the flows cannot be
    featurised, ML is skipped and a warning indicator is appended instead.
    """
    indicators: list[dict] = []
    indicators.extend(_check_flows(flows))
    indicators.extend(_check_api_rate_abuse(api_logs))
    indicators.extend(_check_api_auth_failures(api_logs))

    if flows:
        probabilities = []
        unfeaturised = 0
        for flow in flows:
            row = flow_to_training_features(flow)
            if row is None:
                unfeaturised += 1
                continue
            probability = predict_network(row)
            if probability is not None:
                probabilities.append(probability)
        if probabilities:
            # Most malicious flow in the batch drives the ML contribution.
            indicators.append(ml_indicator("network_xgb.pkl", max(probabilities)))
        elif unfeaturised:
            indicators.append(
                {
                    "type": "ml_warning",
                    "value": f"{unfeaturised}/{len(flows)} flows could not be featurised",
                    "severity": "low",
                    "description": (
                        "Trained network model skipped: flows lack the bytes_out "
                        "value required for the KDD99 feature mapping."
                    ),
                }
            )
    return indicators
