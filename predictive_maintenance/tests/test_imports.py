"""
Test that all PDM project imports work correctly.

This verifies the project separation is complete.
"""

import pytest


def test_core_schemas_import():
    """Test core schemas import"""
    from predictive_maintenance.core.schemas import (
        OperatingRegime,
        SensorType,
        FaultType,
        AlertSeverity,
        AlertType,
        FalsePositiveBudget,
        TelemetrySnapshot,
        SensorReading,
        RegimeState,
        SensorTrust,
        ResidualObservation,
        ChangeDetectionResult,
        FaultHypothesis,
        MaintenanceAlert,
    )
    
    assert OperatingRegime.STEADY_COOL == "steady_cool"
    assert SensorType.SUCTION_PRESSURE == "suction_pressure"


def test_services_import():
    """Test services import"""
    from predictive_maintenance.services import (
        RegimeSegmentationService,
        SensorTrustService,
        SequentialChangeDetectionService,
        FaultHypothesisService,
        DecisionPolicyService,
        EquipmentFingerprintService,
    )
    
    # Basic instantiation check
    assert RegimeSegmentationService is not None


def test_agents_import():
    """Test agents import"""
    from predictive_maintenance.agents import (
        PDMModelAgent,
        PDMModelAgentRole,
        PDMModelOrchestrator,
        OrchestratorConfig,
        TelemetryInput,
        CollaborativeDecisionWorkflow,
        DecisionType,
    )
    
    assert PDMModelAgentRole.REGIME_DETECTOR == "regime_detector"


def test_integration_import():
    """Test integration import"""
    from predictive_maintenance.integration import (
        HVACRPdMAdvancedSystem,
        PDMEventBus,
        PDMEvent,
    )
    
    assert HVACRPdMAdvancedSystem is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
