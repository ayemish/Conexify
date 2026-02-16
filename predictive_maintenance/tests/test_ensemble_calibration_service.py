import sys
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from predictive_maintenance.services.ensemble_calibration_service import EnsembleCalibrationService


def test_update_populates_ensemble_interval_bounds():
    service = EnsembleCalibrationService(model_ids=["m1", "m2"], coverage_level=0.9)

    service.update(
        model_predictions={"m1": 0.4, "m2": 0.6},
        actual_value=0.55,
        model_intervals={"m1": (0.2, 0.5), "m2": (0.5, 0.8)},
    )

    point = service.calibration_points[-1]
    assert point.ensemble_lower < point.ensemble_upper
    assert point.conformity_score is not None
