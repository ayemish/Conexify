import sys
import pathlib
from datetime import datetime

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from predictive_maintenance.agents.orchestrator import PDMModelOrchestrator, TelemetryInput


def test_orchestrator_processes_telemetry():
    orchestrator = PDMModelOrchestrator(site_id="site_1")

    telemetry = TelemetryInput(
        timestamp=datetime.utcnow(),
        asset_id="asset_1",
        site_id="site_1",
        compressor_on=True,
        compressor_current=12.0,
        compressor_power=5.0,
        evap_fan_on=True,
        condenser_fan_on=True,
        supply_fan_speed=50.0,
        suction_line_temp=55.0,
        discharge_temp=110.0,
        supply_air_temp=55.0,
        return_air_temp=75.0,
        ambient_temp=85.0,
        suction_pressure=70.0,
        discharge_pressure=280.0,
    )

    result = orchestrator.process_telemetry(telemetry)

    assert result.layer_results
    assert "layer_0_context" in result.layer_results
    assert result.decision is not None
    assert len(result.decision.votes) > 0
