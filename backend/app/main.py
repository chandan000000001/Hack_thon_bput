"""CYBERGUARD API entrypoint.

Part 1: backend foundation (health, auth, db introspection).
Part 2: multi-source ingestion and Supabase Storage integration.
Part 3: AI detection (phishing & URL), risk scoring, OpenRouter XAI, alerts.
Part 4: impersonation, account takeover, and network/API threat detection.
Part 5: deepfake & manipulated media forensics.
Part 6: incidents, response execution, alert management, dashboard,
        audit logging, and the SOC assistant.
"""

import logging

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import (
    routes_admin,
    routes_alerts,
    routes_analysis,
    routes_assistant,
    routes_audit,
    routes_auth,
    routes_dashboard,
    routes_db,
    routes_events,
    routes_health,
    routes_incidents,
    routes_response,
)
from app.core.config import get_settings

logger = logging.getLogger("cyberguard")
logging.basicConfig(level=logging.INFO)

from app.core.calibration import load_calibration

settings = get_settings()
load_calibration()

# Phase D-2 (item 5): refuse to boot with a wildcard origin while cookies and
# Authorization headers are allowed — that combination defeats browser CORS
# enforcement entirely.
if "*" in settings.cors_origins_list:
    raise RuntimeError("CORS_ORIGINS must not contain '*' while allow_credentials is True")

app = FastAPI(
    title=settings.APP_TITLE,
    version=settings.APP_VERSION,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(routes_health.router, prefix=settings.API_V1_PREFIX)
app.include_router(routes_auth.router, prefix=settings.API_V1_PREFIX)
app.include_router(routes_db.router, prefix=settings.API_V1_PREFIX)
app.include_router(routes_events.router, prefix=settings.API_V1_PREFIX)
app.include_router(routes_analysis.router, prefix=settings.API_V1_PREFIX)
app.include_router(routes_alerts.router, prefix=settings.API_V1_PREFIX)
app.include_router(routes_incidents.router, prefix=settings.API_V1_PREFIX)
app.include_router(routes_response.router, prefix=settings.API_V1_PREFIX)
app.include_router(routes_dashboard.router, prefix=settings.API_V1_PREFIX)
app.include_router(routes_audit.router, prefix=settings.API_V1_PREFIX)
app.include_router(routes_assistant.router, prefix=settings.API_V1_PREFIX)
app.include_router(routes_admin.router, prefix=settings.API_V1_PREFIX)


@app.on_event("startup")
def log_model_deployment() -> None:
    """One-line visibility of the active deepfake model at startup."""
    from app.services.ml_inference import deepfake_deployment_status

    status = deepfake_deployment_status(light=True)["deepfake"]
    if status["heuristics_only"]:
        logger.warning(
            "deepfake model active: %s (128px, artifact %s) — artifact MISSING, "
            "heuristics-only degraded mode",
            status["version"],
            status["artifact"],
        )
    else:
        logger.info(
            "deepfake model active: %s (128px, artifact %s)",
            status["version"],
            status["artifact"],
        )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Return 400 (not FastAPI's default 422) for invalid request payloads."""
    return JSONResponse(
        status_code=400,
        content={
            "error": "invalid_payload",
            "message": "Request payload failed validation.",
            "details": jsonable_encoder(exc.errors()),
        },
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Convert unhandled errors into a JSON 500 response without leaking internals."""
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"error": "internal_server_error", "message": "An unexpected error occurred."},
    )
