"""Shared optional import helpers for predictable fallback behavior."""

from __future__ import annotations

import importlib
import logging
from typing import Any, Optional


def optional_import(
    module_name: str,
    *,
    feature_name: Optional[str] = None,
    logger: Optional[logging.Logger] = None,
) -> Any:
    """Import module_name and return module or None with standardized logging."""
    log = logger or logging.getLogger(__name__)
    feature = feature_name or module_name
    try:
        return importlib.import_module(module_name)
    except Exception as exc:
        log.info("Optional dependency unavailable for %s: module=%s error=%s", feature, module_name, exc)
        return None
