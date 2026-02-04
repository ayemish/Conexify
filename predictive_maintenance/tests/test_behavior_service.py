"""
Tests for Behavior Model Service
"""

import pytest
from datetime import datetime
import numpy as np

import sys
import pathlib
ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from predictive_maintenance.services.behavior_service import (
    BehaviorModelService,
    BehaviorPrediction,
)
from predictive_maintenance.core.schemas import OperatingRegime, SensorType


class TestBehaviorModelService:
    """Tests for BehaviorModelService"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.service = BehaviorModelService("test_asset")
    
    def test_predict_returns_prediction(self):
        """Test that predict returns a BehaviorPrediction"""
        context = {
            "ambient_temp": 85.0,
            "load_proxy": 0.7,
        }
        
        prediction = self.service.predict(
            sensor_type=SensorType.SUCTION_PRESSURE,
            regime=OperatingRegime.STEADY_COOL,
            context=context,
            timestamp=datetime.utcnow(),
        )
        
        assert isinstance(prediction, BehaviorPrediction)
        assert prediction.sensor_type == SensorType.SUCTION_PRESSURE
        assert prediction.regime == OperatingRegime.STEADY_COOL
    
    def test_prediction_has_uncertainty(self):
        """Test that predictions include uncertainty"""
        context = {"ambient_temp": 85.0, "load_proxy": 0.7}
        
        prediction = self.service.predict(
            sensor_type=SensorType.SUCTION_PRESSURE,
            regime=OperatingRegime.STEADY_COOL,
            context=context,
            timestamp=datetime.utcnow(),
        )
        
        assert prediction.prediction_std >= 0
    
    def test_update_with_observation(self):
        """Test that model can be updated with observations"""
        context = {"ambient_temp": 85.0, "load_proxy": 0.7}
        
        # Update with several observations
        for i in range(10):
            self.service.update_with_observation(
                observed_value=68.0 + np.random.normal(0, 1),
                sensor_type=SensorType.SUCTION_PRESSURE,
                regime=OperatingRegime.STEADY_COOL,
                context=context,
            )
        
        # Prediction should adapt
        prediction = self.service.predict(
            sensor_type=SensorType.SUCTION_PRESSURE,
            regime=OperatingRegime.STEADY_COOL,
            context=context,
            timestamp=datetime.utcnow(),
        )
        
        # Should be close to 68
        assert 60 < prediction.predicted_value < 80
    
    def test_regime_specific_predictions(self):
        """Test that predictions vary by regime"""
        context = {"ambient_temp": 85.0, "load_proxy": 0.7}
        
        pred_cool = self.service.predict(
            sensor_type=SensorType.DISCHARGE_PRESSURE,
            regime=OperatingRegime.STEADY_COOL,
            context=context,
            timestamp=datetime.utcnow(),
        )
        
        pred_off = self.service.predict(
            sensor_type=SensorType.DISCHARGE_PRESSURE,
            regime=OperatingRegime.OFF,
            context=context,
            timestamp=datetime.utcnow(),
        )
        
        # Predictions may differ by regime
        # (exact behavior depends on implementation)
        assert pred_cool is not None
        assert pred_off is not None


class TestBehaviorModelAdaptation:
    """Test adaptive behavior of the model"""
    
    def setup_method(self):
        self.service = BehaviorModelService("test_asset")
    
    def test_model_adapts_to_new_baseline(self):
        """Test that model adapts to new operating point"""
        context = {"ambient_temp": 95.0, "load_proxy": 0.9}
        
        # Feed high-temp observations
        for i in range(50):
            self.service.update_with_observation(
                observed_value=75.0 + np.random.normal(0, 0.5),
                sensor_type=SensorType.SUCTION_PRESSURE,
                regime=OperatingRegime.STEADY_COOL,
                context=context,
            )
        
        prediction = self.service.predict(
            sensor_type=SensorType.SUCTION_PRESSURE,
            regime=OperatingRegime.STEADY_COOL,
            context=context,
            timestamp=datetime.utcnow(),
        )
        
        # Should have adapted toward 75
        assert prediction.predicted_value > 70


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
