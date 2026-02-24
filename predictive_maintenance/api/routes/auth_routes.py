"""
Auth Validation API Routes

Provides a simple API key validation endpoint for the frontend LoginPage.
Validates only against configured API keys.
"""

import logging
import os
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

auth_router = APIRouter()


class ValidateKeyRequest(BaseModel):
    api_key: str = Field(..., description="API key to validate")


class ValidateKeyResponse(BaseModel):
    valid: bool
    user: Optional[dict] = None
    role: str = "operator"


@auth_router.post("/validate", response_model=ValidateKeyResponse)
async def validate_api_key(body: ValidateKeyRequest):
    """Validate an API key and return user info.
    """
    if not body.api_key or not body.api_key.strip():
        raise HTTPException(status_code=401, detail="API key required")

    try:
        configured_keys = [
            key.strip()
            for key in os.getenv("PDM_API_KEYS", "").split(",")
            if key.strip()
        ]
        if not configured_keys:
            from ...config import get_settings
            configured_keys = getattr(getattr(get_settings(), "api", None), "api_keys", [])
    except ImportError as e:
        logger.error("Auth config import failed: %s", e)
        raise HTTPException(status_code=503, detail="Auth configuration unavailable")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Auth config check failed: %s", e)
        raise HTTPException(status_code=503, detail="Auth configuration unavailable")

    if not configured_keys:
        raise HTTPException(
            status_code=503,
            detail="Auth validation unavailable: no API keys configured",
        )

    if body.api_key.strip() not in configured_keys:
        raise HTTPException(status_code=401, detail="Invalid API key")

    return ValidateKeyResponse(
        valid=True,
        user={"name": "Operator", "role": "operator"},
        role="operator",
    )
