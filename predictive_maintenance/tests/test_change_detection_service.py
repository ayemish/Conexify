"""
Tests for Change Detection Service
"""

import pytest
from datetime import datetime, timedelta
import numpy as np

import sys
import pathlib
ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from predictive_maintenance.services.change_detection_service import (
    SequentialChangeDetectionService,
    ChangeDetectorConfig,
)
from predictive_maintenance.core.schemas import (
    OperatingRegime,
    SensorType,
    ResidualObservation,
)


class TestSequentialChangeDetectionService:
    """Tests for SequentialChangeDetectionService"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.config = ChangeDetectorConfig(
            cusum_threshold=3.0,
            cusum_slack=0.5,
            glr_threshold=5.0,
            min_persistence_minutes=30.0,
            min_steady_state_regimes=1,
            stability_window=20,
        )
        self.service = SequentialChangeDetectionService("test_asset", self.config)
    
    def _make_residual(
        self,
        residual: float,
        sensor_type: SensorType = SensorType.SUCTION_PRESSURE,
        regime: OperatingRegime = OperatingRegime.STEADY_COOL,
        timestamp: datetime = None,
    ) -> ResidualObservation:
        """Create a test residual observation"""
        return ResidualObservation(
            timestamp=timestamp or datetime.utcnow(),
            sensor_id=f"test_{sensor_type.value}",
            sensor_type=sensor_type,
            regime=regime,
            observed=70.0 + residual,
            predicted=70.0,
            residual=residual,
            z_score=residual / 2.0,  # Assuming sigma=2
        )
    
    def test_no_change_on_normal_residuals(self):
        """Test that no change is detected on normal residuals"""
        ts = datetime.utcnow()
        
        for i in range(50):
            residual = self._make_residual(
                residual=np.random.normal(0, 1),
                timestamp=ts + timedelta(minutes=i),
            )
            result = self.service.process_observation(
                residual,
                OperatingRegime.STEADY_COOL,
                trust_score=1.0,
            )
        
        assert not result.change_detected
    
    def test_change_detected_on_shift(self):
        """Test that change is detected on mean shift"""
        ts = datetime.utcnow()
        
        # Normal period
        for i in range(30):
            residual = self._make_residual(
                residual=np.random.normal(0, 1),
                timestamp=ts + timedelta(minutes=i),
            )
            self.service.process_observation(
                residual,
                OperatingRegime.STEADY_COOL,
                trust_score=1.0,
            )
        
        # Shifted period (mean = 3)
        for i in range(30, 80):
            residual = self._make_residual(
                residual=np.random.normal(3, 1),
                timestamp=ts + timedelta(minutes=i),
            )
            result = self.service.process_observation(
                residual,
                OperatingRegime.STEADY_COOL,
                trust_score=1.0,
            )
        
        # Should detect change
        assert result.change_detected or result.change_score > 0.5
    
    def test_cusum_accumulates(self):
        """Test that CUSUM statistics accumulate correctly"""
        ts = datetime.utcnow()
        
        # Feed positive residuals
        for i in range(20):
            residual = self._make_residual(
                residual=2.0,  # Consistent positive shift
                timestamp=ts + timedelta(minutes=i),
            )
            result = self.service.process_observation(
                residual,
                OperatingRegime.STEADY_COOL,
                trust_score=1.0,
            )
        
        # CUSUM positive should have grown
        assert result.cusum_pos > 0
    
    def test_low_trust_suppresses_change(self):
        """Test that low sensor trust suppresses change detection"""
        ts = datetime.utcnow()
        
        # Large residuals but low trust
        for i in range(50):
            residual = self._make_residual(
                residual=5.0,  # Large shift
                timestamp=ts + timedelta(minutes=i),
            )
            result = self.service.process_observation(
                residual,
                OperatingRegime.STEADY_COOL,
                trust_score=0.3,  # Low trust
            )
        
        # Change detection should be dampened
        assert result.change_score < 0.8


class TestChangeDetectorConfig:
    """Test configuration options"""
    
    def test_config_defaults(self):
        """Test default configuration values"""
        config = ChangeDetectorConfig()
        
        assert config.cusum_threshold > 0
        assert config.glr_threshold > 0
        assert config.min_persistence_minutes > 0
    
    def test_custom_config(self):
        """Test custom configuration"""
        config = ChangeDetectorConfig(
            cusum_threshold=10.0,
            glr_threshold=20.0,
        )
        
        assert config.cusum_threshold == 10.0
        assert config.glr_threshold == 20.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
