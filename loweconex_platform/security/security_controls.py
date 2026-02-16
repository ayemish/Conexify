"""
Security Controls, OWASP ASVS, SLSA Provenance.

Implements:
- ISO/IEC 27001-aligned ISMS controls baseline with audit tracking
- OWASP ASVS verification requirements for ingestion/reporting APIs and UI
- SLSA-style provenance controls for agent/tooling artifacts
- Compliance report generation

References:
- ISO/IEC 27001:2022 Information Security Management
- OWASP Application Security Verification Standard (ASVS) 4.0
- SLSA (Supply-chain Levels for Software Artifacts) v1.0
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# =============================================================================
# ISO 27001 control domains
# =============================================================================

class ISO27001Domain(str, Enum):
    """ISO/IEC 27001:2022 Annex A control domains."""
    ORG_CONTROLS = "A.5"          # Organizational controls
    PEOPLE_CONTROLS = "A.6"       # People controls
    PHYSICAL_CONTROLS = "A.7"     # Physical controls
    TECH_CONTROLS = "A.8"         # Technological controls


class ControlStatus(str, Enum):
    NOT_IMPLEMENTED = "not_implemented"
    PARTIALLY_IMPLEMENTED = "partially_implemented"
    IMPLEMENTED = "implemented"
    VERIFIED = "verified"
    NOT_APPLICABLE = "not_applicable"


class OWASPLevel(str, Enum):
    """OWASP ASVS verification levels."""
    L1 = "L1"  # Opportunistic
    L2 = "L2"  # Standard
    L3 = "L3"  # Advanced


class SLSALevel(str, Enum):
    """SLSA build levels."""
    L0 = "L0"  # No guarantees
    L1 = "L1"  # Provenance exists
    L2 = "L2"  # Hosted build platform
    L3 = "L3"  # Hardened builds


# =============================================================================
# Security control model
# =============================================================================

@dataclass
class SecurityControl:
    """An ISO 27001-aligned security control."""
    control_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    iso_ref: str = ""            # e.g., "A.8.24" (Web filtering)
    title: str = ""
    description: str = ""
    domain: str = ISO27001Domain.TECH_CONTROLS.value
    status: str = ControlStatus.NOT_IMPLEMENTED.value

    # Implementation details
    implementation_notes: str = ""
    implementation_date: Optional[str] = None
    evidence_location: str = ""

    # Testing
    last_audit_date: Optional[str] = None
    last_audit_result: Optional[str] = None
    audit_frequency: str = "annual"
    next_audit_date: Optional[str] = None

    # Risk mapping
    mitigates_risks: List[str] = field(default_factory=list)

    # Ownership
    owner: str = ""
    reviewer: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "control_id": self.control_id,
            "iso_ref": self.iso_ref,
            "title": self.title,
            "description": self.description,
            "domain": self.domain,
            "status": self.status,
            "implementation_notes": self.implementation_notes,
            "implementation_date": self.implementation_date,
            "evidence_location": self.evidence_location,
            "last_audit_date": self.last_audit_date,
            "last_audit_result": self.last_audit_result,
            "audit_frequency": self.audit_frequency,
            "next_audit_date": self.next_audit_date,
            "mitigates_risks": self.mitigates_risks,
            "owner": self.owner,
            "reviewer": self.reviewer,
        }


# =============================================================================
# OWASP ASVS checks
# =============================================================================

@dataclass
class OWASPCheck:
    """An OWASP ASVS verification requirement."""
    check_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    asvs_ref: str = ""          # e.g., "V2.1.1"
    category: str = ""          # e.g., "Authentication", "Session Management"
    requirement: str = ""
    level: str = OWASPLevel.L1.value
    status: str = ControlStatus.NOT_IMPLEMENTED.value

    # Applicable endpoints
    applies_to: List[str] = field(default_factory=list)  # API paths, UI pages

    # Verification
    test_method: str = ""        # automated, manual, code_review
    last_tested: Optional[str] = None
    test_result: Optional[str] = None
    findings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "check_id": self.check_id,
            "asvs_ref": self.asvs_ref,
            "category": self.category,
            "requirement": self.requirement,
            "level": self.level,
            "status": self.status,
            "applies_to": self.applies_to,
            "test_method": self.test_method,
            "last_tested": self.last_tested,
            "test_result": self.test_result,
            "findings": self.findings,
        }


# =============================================================================
# SLSA provenance
# =============================================================================

@dataclass
class SLSAProvenance:
    """
    SLSA-style provenance record for an artifact.

    Tracks build provenance for agent code, tool definitions,
    prompt templates, and model artifacts.
    """
    provenance_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    artifact_name: str = ""
    artifact_type: str = ""      # agent, tool, prompt, model, config
    artifact_hash: str = ""      # SHA-256 of artifact content
    slsa_level: str = SLSALevel.L1.value

    # Build info
    builder: str = ""            # CI/CD system
    build_type: str = ""         # e.g., "github_actions", "manual"
    source_repo: str = ""
    source_ref: str = ""         # git commit SHA
    source_branch: str = ""

    # Invocation
    entry_point: str = ""
    parameters: Dict[str, Any] = field(default_factory=dict)
    environment: Dict[str, str] = field(default_factory=dict)

    # Materials (inputs)
    materials: List[Dict[str, str]] = field(default_factory=list)
    # e.g., [{"uri": "pkg:pypi/crewai@0.80", "digest": {"sha256": "abc..."}}]

    # Verification
    verified: bool = False
    verified_ts: Optional[str] = None
    verified_by: Optional[str] = None

    # Metadata
    created_ts: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "provenance_id": self.provenance_id,
            "artifact_name": self.artifact_name,
            "artifact_type": self.artifact_type,
            "artifact_hash": self.artifact_hash,
            "slsa_level": self.slsa_level,
            "builder": self.builder,
            "build_type": self.build_type,
            "source_repo": self.source_repo,
            "source_ref": self.source_ref,
            "source_branch": self.source_branch,
            "entry_point": self.entry_point,
            "parameters": self.parameters,
            "environment": self.environment,
            "materials": self.materials,
            "verified": self.verified,
            "verified_ts": self.verified_ts,
            "verified_by": self.verified_by,
            "created_ts": self.created_ts,
        }

    @staticmethod
    def compute_hash(content: str) -> str:
        return hashlib.sha256(content.encode()).hexdigest()


# =============================================================================
# Compliance report
# =============================================================================

@dataclass
class ComplianceReport:
    """Aggregated compliance report across all security frameworks."""
    report_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    generated_ts: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    # ISO 27001
    iso_controls_total: int = 0
    iso_controls_implemented: int = 0
    iso_controls_verified: int = 0
    iso_coverage_pct: float = 0.0

    # OWASP ASVS
    owasp_checks_total: int = 0
    owasp_checks_passed: int = 0
    owasp_target_level: str = OWASPLevel.L2.value
    owasp_coverage_pct: float = 0.0

    # SLSA
    slsa_artifacts_total: int = 0
    slsa_artifacts_verified: int = 0
    slsa_target_level: str = SLSALevel.L2.value

    # Overdue items
    overdue_audits: int = 0
    open_findings: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "report_id": self.report_id,
            "generated_ts": self.generated_ts,
            "iso_controls_total": self.iso_controls_total,
            "iso_controls_implemented": self.iso_controls_implemented,
            "iso_controls_verified": self.iso_controls_verified,
            "iso_coverage_pct": self.iso_coverage_pct,
            "owasp_checks_total": self.owasp_checks_total,
            "owasp_checks_passed": self.owasp_checks_passed,
            "owasp_target_level": self.owasp_target_level,
            "owasp_coverage_pct": self.owasp_coverage_pct,
            "slsa_artifacts_total": self.slsa_artifacts_total,
            "slsa_artifacts_verified": self.slsa_artifacts_verified,
            "slsa_target_level": self.slsa_target_level,
            "overdue_audits": self.overdue_audits,
            "open_findings": self.open_findings,
        }


# =============================================================================
# Security Controls Registry
# =============================================================================

class SecurityControlsRegistry:
    """
    Central registry managing all security controls, OWASP checks,
    and SLSA provenance records.

    Supports:
    - Registration and status tracking
    - Audit scheduling and overdue detection
    - Compliance report generation
    - Procurement-ready evidence export
    """

    def __init__(self):
        self._iso_controls: Dict[str, SecurityControl] = {}
        self._owasp_checks: Dict[str, OWASPCheck] = {}
        self._provenance: Dict[str, SLSAProvenance] = {}

    # --- ISO 27001 Controls ---

    def register_iso_control(self, control: SecurityControl):
        self._iso_controls[control.control_id] = control

    def add_baseline_controls(self):
        """Add standard ISO 27001 baseline controls for the platform."""
        baseline = [
            ("A.5.1", "Information security policies", ISO27001Domain.ORG_CONTROLS.value),
            ("A.5.2", "Information security roles and responsibilities", ISO27001Domain.ORG_CONTROLS.value),
            ("A.5.10", "Acceptable use of information", ISO27001Domain.ORG_CONTROLS.value),
            ("A.5.15", "Access control", ISO27001Domain.ORG_CONTROLS.value),
            ("A.5.23", "Information security for cloud services", ISO27001Domain.ORG_CONTROLS.value),
            ("A.5.29", "Information security during disruption", ISO27001Domain.ORG_CONTROLS.value),
            ("A.5.34", "Privacy and PII protection", ISO27001Domain.ORG_CONTROLS.value),
            ("A.6.1", "Screening", ISO27001Domain.PEOPLE_CONTROLS.value),
            ("A.6.3", "Information security awareness and training", ISO27001Domain.PEOPLE_CONTROLS.value),
            ("A.7.1", "Physical security perimeters", ISO27001Domain.PHYSICAL_CONTROLS.value),
            ("A.8.1", "User endpoint devices", ISO27001Domain.TECH_CONTROLS.value),
            ("A.8.2", "Privileged access rights", ISO27001Domain.TECH_CONTROLS.value),
            ("A.8.3", "Information access restriction", ISO27001Domain.TECH_CONTROLS.value),
            ("A.8.5", "Secure authentication", ISO27001Domain.TECH_CONTROLS.value),
            ("A.8.7", "Protection against malware", ISO27001Domain.TECH_CONTROLS.value),
            ("A.8.9", "Configuration management", ISO27001Domain.TECH_CONTROLS.value),
            ("A.8.10", "Information deletion", ISO27001Domain.TECH_CONTROLS.value),
            ("A.8.11", "Data masking", ISO27001Domain.TECH_CONTROLS.value),
            ("A.8.12", "Data leakage prevention", ISO27001Domain.TECH_CONTROLS.value),
            ("A.8.15", "Logging", ISO27001Domain.TECH_CONTROLS.value),
            ("A.8.16", "Monitoring activities", ISO27001Domain.TECH_CONTROLS.value),
            ("A.8.20", "Network security", ISO27001Domain.TECH_CONTROLS.value),
            ("A.8.24", "Use of cryptography", ISO27001Domain.TECH_CONTROLS.value),
            ("A.8.25", "Secure development lifecycle", ISO27001Domain.TECH_CONTROLS.value),
            ("A.8.26", "Application security requirements", ISO27001Domain.TECH_CONTROLS.value),
            ("A.8.28", "Secure coding", ISO27001Domain.TECH_CONTROLS.value),
        ]
        for iso_ref, title, domain in baseline:
            ctrl = SecurityControl(
                iso_ref=iso_ref,
                title=title,
                domain=domain,
            )
            self.register_iso_control(ctrl)
        logger.info(f"Added {len(baseline)} baseline ISO 27001 controls")

    def get_overdue_audits(self) -> List[SecurityControl]:
        """Get controls with overdue audits."""
        overdue = []
        now = datetime.utcnow()
        for ctrl in self._iso_controls.values():
            if ctrl.next_audit_date:
                try:
                    due = datetime.fromisoformat(ctrl.next_audit_date)
                    if now > due:
                        overdue.append(ctrl)
                except ValueError:
                    pass
            elif ctrl.status == ControlStatus.IMPLEMENTED.value and not ctrl.last_audit_date:
                overdue.append(ctrl)
        return overdue

    # --- OWASP ASVS ---

    def register_owasp_check(self, check: OWASPCheck):
        self._owasp_checks[check.check_id] = check

    def add_baseline_owasp_checks(self):
        """Add standard OWASP ASVS checks for the platform APIs."""
        checks = [
            ("V2.1.1", "Authentication", "Verify password length requirements", OWASPLevel.L1.value),
            ("V2.2.1", "Authentication", "Verify anti-automation controls", OWASPLevel.L1.value),
            ("V3.1.1", "Session Management", "Verify session token security", OWASPLevel.L1.value),
            ("V3.5.1", "Session Management", "Verify token-based session management", OWASPLevel.L2.value),
            ("V4.1.1", "Access Control", "Verify access controls on every API endpoint", OWASPLevel.L1.value),
            ("V4.2.1", "Access Control", "Verify sensitive data access requires authorization", OWASPLevel.L1.value),
            ("V5.1.1", "Validation", "Verify input validation on all inputs", OWASPLevel.L1.value),
            ("V5.2.1", "Validation", "Verify HTML output encoding", OWASPLevel.L1.value),
            ("V5.3.1", "Validation", "Verify SQL injection prevention", OWASPLevel.L1.value),
            ("V8.1.1", "Data Protection", "Verify sensitive data identified and classified", OWASPLevel.L1.value),
            ("V8.3.1", "Data Protection", "Verify sensitive data sent in HTTP body", OWASPLevel.L1.value),
            ("V9.1.1", "Communications", "Verify TLS for all connections", OWASPLevel.L1.value),
            ("V10.1.1", "Malicious Code", "Verify code integrity controls", OWASPLevel.L2.value),
            ("V13.1.1", "API Security", "Verify generic API security controls", OWASPLevel.L1.value),
            ("V13.2.1", "API Security", "Verify REST API uses security headers", OWASPLevel.L1.value),
            ("V14.2.1", "Configuration", "Verify dependency security", OWASPLevel.L1.value),
        ]
        for asvs_ref, category, requirement, level in checks:
            check = OWASPCheck(
                asvs_ref=asvs_ref,
                category=category,
                requirement=requirement,
                level=level,
            )
            self.register_owasp_check(check)
        logger.info(f"Added {len(checks)} baseline OWASP ASVS checks")

    # --- SLSA Provenance ---

    def register_provenance(self, prov: SLSAProvenance):
        self._provenance[prov.provenance_id] = prov

    def verify_provenance(self, provenance_id: str, verified_by: str) -> bool:
        prov = self._provenance.get(provenance_id)
        if not prov:
            return False
        prov.verified = True
        prov.verified_ts = datetime.utcnow().isoformat()
        prov.verified_by = verified_by
        return True

    def get_unverified_artifacts(self) -> List[SLSAProvenance]:
        return [p for p in self._provenance.values() if not p.verified]

    # --- Compliance Reporting ---

    def generate_compliance_report(self) -> ComplianceReport:
        """Generate an aggregated compliance report."""
        iso_total = len(self._iso_controls)
        iso_implemented = sum(
            1 for c in self._iso_controls.values()
            if c.status in (ControlStatus.IMPLEMENTED.value, ControlStatus.VERIFIED.value)
        )
        iso_verified = sum(
            1 for c in self._iso_controls.values()
            if c.status == ControlStatus.VERIFIED.value
        )

        owasp_total = len(self._owasp_checks)
        owasp_passed = sum(
            1 for c in self._owasp_checks.values()
            if c.test_result == "pass"
        )

        slsa_total = len(self._provenance)
        slsa_verified = sum(1 for p in self._provenance.values() if p.verified)

        open_findings = sum(
            len(c.findings) for c in self._owasp_checks.values()
            if c.findings
        )

        report = ComplianceReport(
            iso_controls_total=iso_total,
            iso_controls_implemented=iso_implemented,
            iso_controls_verified=iso_verified,
            iso_coverage_pct=iso_implemented / iso_total if iso_total else 0,
            owasp_checks_total=owasp_total,
            owasp_checks_passed=owasp_passed,
            owasp_coverage_pct=owasp_passed / owasp_total if owasp_total else 0,
            slsa_artifacts_total=slsa_total,
            slsa_artifacts_verified=slsa_verified,
            overdue_audits=len(self.get_overdue_audits()),
            open_findings=open_findings,
        )

        logger.info(
            f"Compliance report: ISO={iso_implemented}/{iso_total}, "
            f"OWASP={owasp_passed}/{owasp_total}, "
            f"SLSA={slsa_verified}/{slsa_total}"
        )
        return report

    def stats(self) -> Dict[str, Any]:
        return {
            "iso_controls": len(self._iso_controls),
            "owasp_checks": len(self._owasp_checks),
            "slsa_provenance": len(self._provenance),
        }
