import sys
import pathlib
from datetime import datetime, timedelta

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from predictive_maintenance.services.sensor_trust_service import SensorTrustService, SensorReading
from predictive_maintenance.core.schemas import SensorType


def test_out_of_range_penalty():
    service = SensorTrustService("asset_1")
    reading = SensorReading(
        timestamp=datetime.utcnow(),
        sensor_id="suction_pressure",
        sensor_type=SensorType.SUCTION_PRESSURE,
        value=-5.0,  # Below min_valid (0.0)
    )

    trust = service.process_reading(reading)
    assert trust.out_of_range_probability == 1.0
    assert trust.trust_score <= 0.5


def test_stuck_sensor_detection():
    service = SensorTrustService("asset_1")
    base_time = datetime.utcnow()

    for i in range(40):
        reading = SensorReading(
            timestamp=base_time + timedelta(minutes=i),
            sensor_id="supply_air_temp",
            sensor_type=SensorType.SUPPLY_AIR_TEMP,
            value=55.0,  # constant value
        )
        trust = service.process_reading(reading)

    assert trust.stuck_likelihood > 0.4
    assert trust.trust_score < 1.0


def test_drift_detection():
    service = SensorTrustService("asset_1")
    base_time = datetime.utcnow()

    # Baseline readings
    for i in range(50):
        reading = SensorReading(
            timestamp=base_time + timedelta(minutes=i),
            sensor_id="return_air_temp",
            sensor_type=SensorType.RETURN_AIR_TEMP,
            value=70.0,
        )
        service.process_reading(reading)

    # Drifted readings
    for i in range(50, 100):
        reading = SensorReading(
            timestamp=base_time + timedelta(minutes=i),
            sensor_id="return_air_temp",
            sensor_type=SensorType.RETURN_AIR_TEMP,
            value=85.0,
        )
        trust = service.process_reading(reading)

    assert trust.drift_likelihood > 0.5
    assert trust.trust_score < 1.0


def test_comms_quality_penalty():
    service = SensorTrustService("asset_1")
    base_time = datetime.utcnow()

    for i in range(20):
        reading = SensorReading(
            timestamp=base_time + timedelta(minutes=i),
            sensor_id="ambient_temp",
            sensor_type=SensorType.AMBIENT_TEMP,
            value=80.0 + i * 0.1,
            quality_code=1,  # mark as quality issue
        )
        trust = service.process_reading(reading)

    assert trust.comms_integrity < 1.0
    assert trust.trust_score < 1.0
