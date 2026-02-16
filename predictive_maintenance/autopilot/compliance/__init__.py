"""
Compliance Autopilot Module

Implements regulatory compliance tracking for:
- EU F-gas Regulation (517/2014) - refrigerant leak detection and record-keeping
- Refrigerant metadata per asset
- Leak case generation and tracking
- Compliance logbook generation
"""

from .fgas import (
    FGasComplianceService,
    RefrigerantAsset,
    LeakCheckRecord,
    RefrigerantTransaction,
    ComplianceLogbook,
    FGasThresholds,
)

__all__ = [
    "FGasComplianceService",
    "RefrigerantAsset",
    "LeakCheckRecord",
    "RefrigerantTransaction",
    "ComplianceLogbook",
    "FGasThresholds",
]
