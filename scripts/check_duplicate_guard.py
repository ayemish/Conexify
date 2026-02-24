#!/usr/bin/env python3
"""Guardrails against critical duplicate-source drift."""

from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]


def _fail(msg: str) -> None:
    print(f"[duplicate-guard] {msg}")
    raise SystemExit(1)


def _check_wrapper(path: Path, expected_import_hint: str, max_lines: int = 80) -> None:
    if not path.exists():
        _fail(f"Missing wrapper file: {path}")
    text = path.read_text(encoding="utf-8")
    line_count = len(text.splitlines())
    if line_count > max_lines:
        _fail(f"Wrapper too large (expected thin compatibility module): {path} ({line_count} lines)")
    if expected_import_hint not in text:
        _fail(f"Wrapper does not reference canonical module '{expected_import_hint}': {path}")


def _check_archived_example(path: Path) -> None:
    if not path.exists():
        return
    marker = path / "ARCHIVED_EXAMPLE.md"
    if not marker.exists():
        _fail(f"Archived example directory missing archive marker: {path}")


def main() -> int:
    _check_wrapper(
        ROOT / "oil_gas/agents/pdm_agent_protocols.py",
        "predictive_maintenance.agents",
    )
    _check_archived_example(ROOT / "CapEx Generator copy")
    print("[duplicate-guard] OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
