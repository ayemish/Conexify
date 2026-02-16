"""
Security CI Checks — pre-deploy compliance verification + SLSA provenance.

Run as part of CI/CD pipeline to:
1. Generate ISO 27001 + OWASP ASVS compliance report
2. Block deploy if compliance rate is below threshold
3. Track SLSA provenance for agent artifacts

Usage:
    python -m loweconex_platform.security.ci_checks --min-compliance 0.80
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

try:
    from loweconex_platform.security.security_controls import (
        SecurityControlsRegistry, SLSAProvenance,
    )
    SECURITY_AVAILABLE = True
except ImportError:
    SECURITY_AVAILABLE = False


class PreDeployComplianceCheck:
    """
    Runs compliance checks before deployment.

    Returns exit code 0 on pass, 1 on failure.
    """

    def __init__(
        self,
        registry: Optional[Any] = None,
        min_compliance_rate: float = 0.80,
        require_slsa: bool = True,
    ):
        if registry is not None:
            self._registry = registry
        elif SECURITY_AVAILABLE:
            self._registry = SecurityControlsRegistry()
            self._registry.add_baseline_iso27001()
            self._registry.add_baseline_owasp()
        else:
            self._registry = None

        self.min_compliance_rate = min_compliance_rate
        self.require_slsa = require_slsa

    def run(self, artifact_paths: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Execute all pre-deploy checks.

        Returns:
            {"passed": bool, "compliance_report": {...}, "slsa": {...}, "issues": [...]}
        """
        result: Dict[str, Any] = {
            "passed": True,
            "timestamp": datetime.utcnow().isoformat(),
            "issues": [],
        }

        if not self._registry:
            result["issues"].append("Security controls registry not available")
            result["passed"] = False
            return result

        # 1. Generate compliance report
        try:
            report = self._registry.generate_compliance_report()
            result["compliance_report"] = report

            rate = report.get("compliance_rate", 0)
            if rate < self.min_compliance_rate:
                result["passed"] = False
                result["issues"].append(
                    f"Compliance rate {rate:.0%} below minimum {self.min_compliance_rate:.0%}"
                )
                logger.error(f"COMPLIANCE CHECK FAILED: {rate:.0%} < {self.min_compliance_rate:.0%}")
            else:
                logger.info(f"Compliance check passed: {rate:.0%}")

            # Flag any not-implemented controls
            not_impl = report.get("not_implemented", 0)
            if not_impl > 0:
                result["issues"].append(f"{not_impl} controls not yet implemented")

        except Exception as e:
            result["passed"] = False
            result["issues"].append(f"Compliance report generation failed: {e}")

        # 2. SLSA provenance tracking
        if self.require_slsa and artifact_paths:
            try:
                slsa_records = []
                for path in artifact_paths:
                    prov = self._create_slsa_provenance(path)
                    slsa_records.append(prov)
                    if self._registry and SECURITY_AVAILABLE:
                        self._registry.register_provenance(
                            SLSAProvenance(
                                artifact_name=path,
                                artifact_hash=prov["artifact_hash"],
                                builder_id="ci_pipeline",
                                build_type="automated",
                                source_repo=prov.get("source_repo", ""),
                                slsa_level=1,
                            )
                        )
                result["slsa_provenance"] = slsa_records
                logger.info(f"SLSA provenance tracked for {len(slsa_records)} artifacts")
            except Exception as e:
                result["issues"].append(f"SLSA provenance tracking failed: {e}")

        return result

    def _create_slsa_provenance(self, artifact_path: str) -> Dict[str, Any]:
        """Create SLSA v1.0 provenance record for an artifact."""
        try:
            with open(artifact_path, "rb") as f:
                content = f.read()
            artifact_hash = hashlib.sha256(content).hexdigest()
        except (FileNotFoundError, IOError):
            artifact_hash = hashlib.sha256(artifact_path.encode()).hexdigest()

        return {
            "artifact_path": artifact_path,
            "artifact_hash": f"sha256:{artifact_hash}",
            "builder_id": "loweconex_ci",
            "build_type": "automated",
            "build_ts": datetime.utcnow().isoformat(),
            "slsa_level": 1,
        }


def main():
    """CLI entry point for CI/CD integration."""
    parser = argparse.ArgumentParser(description="Pre-deploy compliance check")
    parser.add_argument(
        "--min-compliance", type=float, default=0.80,
        help="Minimum compliance rate (0-1) to pass (default: 0.80)"
    )
    parser.add_argument(
        "--artifacts", nargs="*", default=[],
        help="Artifact paths to track SLSA provenance for"
    )
    parser.add_argument(
        "--output", type=str, default=None,
        help="Output file for compliance report JSON"
    )
    parser.add_argument(
        "--no-slsa", action="store_true",
        help="Skip SLSA provenance tracking"
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    checker = PreDeployComplianceCheck(
        min_compliance_rate=args.min_compliance,
        require_slsa=not args.no_slsa,
    )
    result = checker.run(artifact_paths=args.artifacts or None)

    if args.output:
        with open(args.output, "w") as f:
            json.dump(result, f, indent=2, default=str)
        logger.info(f"Report written to {args.output}")

    if result["passed"]:
        print(f"✓ Pre-deploy compliance check PASSED")
        sys.exit(0)
    else:
        print(f"✗ Pre-deploy compliance check FAILED")
        for issue in result["issues"]:
            print(f"  - {issue}")
        sys.exit(1)


if __name__ == "__main__":
    main()
