"""
Auth Validation API Routes

Provides a simple API key validation endpoint for the frontend LoginPage.
In production, this validates against configured API keys.
In development, any non-empty key is accepted.
"""

import logging
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

    In development mode (no keys configured), any non-empty key is accepted.
    """
    if not body.api_key or not body.api_key.strip():
        raise HTTPException(status_code=401, detail="API key required")

    try:
        from ...config import settings
        configured_keys = getattr(getattr(settings, "api", None), "api_keys", [])
        if configured_keys:
            if body.api_key.strip() not in configured_keys:
                raise HTTPException(status_code=401, detail="Invalid API key")
            return ValidateKeyResponse(
                valid=True,
                user={"name": "Operator", "role": "operator"},
                role="operator",
            )
    except ImportError:
        pass
    except HTTPException:
        raise
    except Exception as e:
        logger.debug("Auth config check failed, allowing dev bypass: %s", e)

    # Development fallback: accept any key
    return ValidateKeyResponse(
        valid=True,
        user={"name": "Dev User", "role": "admin"},
        role="admin",
    )
