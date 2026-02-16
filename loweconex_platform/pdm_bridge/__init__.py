"""
PdM Integration Bridge — connects predictive_maintenance model outputs
to the Loweconex digital twin platform and KPI crews.

Feeds: failure risk, RUL, fault classifications, health scores, sensor trust,
and decision artifacts from HVACRPdMAdvancedSystem into AssetTwin health fields
and KPI crew inputs.
"""

from loweconex_platform.pdm_bridge.bridge import (
    PdMBridge,
    PdMAssetSnapshot,
    PdMBridgeConfig,
)

__all__ = [
    "PdMBridge",
    "PdMAssetSnapshot",
    "PdMBridgeConfig",
]
