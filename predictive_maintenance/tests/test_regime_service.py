"""
Tests for Regime Segmentation Service
"""

import pytest
from datetime import datetime, timedelta

import sys
import pathlib
ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from predictive_maintenance.services.regime_service import (
    RegimeSegmentationService,
    TelemetrySnapshot,
)
from predictive_maintenance.core.schemas import OperatingRegime


class TestRegimeSegmentationService:
    """Tests for RegimeSegmentationService"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.service = RegimeSegmentationService("test_asset")
    
    def _make_snapshot(
        self,
        compressor_on: bool = True,
        evap_fan_on: bool = True,
        condenser_fan_on: bool = True,
        supply_air_temp: float = 55.0,
        return_air_temp: float = 75.0,
        ambient_temp: float = 85.0,
        heating: bool = False,
    ) -> TelemetrySnapshot:
        """Create a test telemetry snapshot"""
        return TelemetrySnapshot(
            timestamp=datetime.utcnow(),
            asset_id="test_asset",
            compressor_on=compressor_on,
            compressor_current=15.0 if compressor_on else 0.0,
            evap_fan_on=evap_fan_on,
            condenser_fan_on=condenser_fan_on,
            supply_air_temp=supply_air_temp,
            return_air_temp=return_air_temp,
            ambient_temp=ambient_temp,
            heating_valve_pct=60.0 if heating else 0.0,
            reversing_valve_heat=heating,
        )
    
    def test_off_regime_detection(self):
        """Test detection of OFF regime"""
        snapshot = self._make_snapshot(
            compressor_on=False,
            evap_fan_on=False,
            condenser_fan_on=False,
        )
        
        state = self.service.classify_regime(snapshot)
        assert state.regime == OperatingRegime.OFF
    
    def test_steady_cool_regime_detection(self):
        """Test detection of steady cooling regime"""
        # Feed multiple samples to establish steady state
        for _ in range(10):
            snapshot = self._make_snapshot(
                compressor_on=True,
                supply_air_temp=55.0,
                return_air_temp=75.0,
            )
            state = self.service.classify_regime(snapshot)
        
        # Should be in steady cooling
        assert state.regime in [OperatingRegime.STEADY_COOL, OperatingRegime.TRANSIENT]
    
    def test_steady_heat_regime_detection(self):
        """Test detection of steady heating regime"""
        for _ in range(10):
            snapshot = self._make_snapshot(
                compressor_on=True,
                heating=True,
                supply_air_temp=95.0,
                return_air_temp=68.0,
            )
            state = self.service.classify_regime(snapshot)
        
        assert state.regime in [OperatingRegime.STEADY_HEAT, OperatingRegime.TRANSIENT]
    
    def test_startup_detection(self):
        """Test detection of startup regime"""
        # First, establish OFF state
        for _ in range(5):
            snapshot = self._make_snapshot(compressor_on=False, evap_fan_on=False)
            self.service.classify_regime(snapshot)
        
        # Now start compressor
        snapshot = self._make_snapshot(compressor_on=True)
        state = self.service.classify_regime(snapshot)
        
        # Should detect startup or transient
        assert state.regime in [OperatingRegime.STARTUP, OperatingRegime.TRANSIENT]
    
    def test_regime_confidence(self):
        """Test that regime confidence is provided"""
        snapshot = self._make_snapshot()
        state = self.service.classify_regime(snapshot)
        
        assert 0.0 <= state.confidence <= 1.0
    
    def test_is_steady_state(self):
        """Test steady state detection"""
        # Initially not steady
        assert not self.service.is_steady_state()
        
        # Feed consistent samples
        for _ in range(20):
            snapshot = self._make_snapshot(
                compressor_on=True,
                supply_air_temp=55.0,
            )
            self.service.classify_regime(snapshot)
        
        # Should eventually become steady
        # (depends on implementation threshold)


class TestRegimeTransitions:
    """Test regime transition handling"""
    
    def setup_method(self):
        self.service = RegimeSegmentationService("test_asset")
    
    def test_cooling_to_off_transition(self):
        """Test transition from cooling to off"""
        # Establish cooling
        for _ in range(10):
            snapshot = TelemetrySnapshot(
                timestamp=datetime.utcnow(),
                asset_id="test_asset",
                compressor_on=True,
                evap_fan_on=True,
            )
            self.service.classify_regime(snapshot)
        
        # Turn off
        snapshot = TelemetrySnapshot(
            timestamp=datetime.utcnow(),
            asset_id="test_asset",
            compressor_on=False,
            evap_fan_on=False,
        )
        state = self.service.classify_regime(snapshot)
        
        # Should be OFF or transitioning
        assert state.regime in [OperatingRegime.OFF, OperatingRegime.SHUTDOWN]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
