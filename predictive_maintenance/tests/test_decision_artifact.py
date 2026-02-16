import sys
import pathlib
from datetime import datetime

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from predictive_maintenance.integration.advanced_system import HVACRPdMAdvancedSystem


def test_process_telemetry_with_artifact_returns_kernel_artifact():
    system = HVACRPdMAdvancedSystem("asset_1")
    telemetry = {
        "timestamp": datetime.utcnow(),
        "compressor_on": True,
        "compressor_current": 12.0,
        "compressor_power": 5.0,
        "evap_fan_on": True,
        "condenser_fan_on": True,
        "supply_fan_speed": 50.0,
        "suction_line_temp": 55.0,
        "discharge_temp": 110.0,
        "supply_air_temp": 55.0,
        "return_air_temp": 75.0,
        "ambient_temp": 85.0,
        "suction_pressure": 70.0,
        "discharge_pressure": 280.0,
    }

    alert, artifact = system.process_telemetry_with_artifact(telemetry)

    assert artifact.asset_id == "asset_1"
    assert artifact.base_alert_type == alert.alert_type
    assert len(artifact.gates) == 6
    assert artifact.context.get("telemetry_timestamp")
    assert system.export_decision_artifact() is not None
