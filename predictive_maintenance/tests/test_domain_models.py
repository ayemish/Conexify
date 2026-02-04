"""
Tests for Domain Models (Refrigerant, Equipment, Physics)
"""

import pytest
import math

import sys
import pathlib
ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from predictive_maintenance.domain.refrigerant import (
    RefrigerantProperties,
    R410A,
    R22,
    R134A,
    get_refrigerant,
    calculate_superheat,
    calculate_subcool,
    saturation_temperature,
    saturation_pressure,
)
from predictive_maintenance.domain.equipment import (
    EquipmentSpecs,
    RTUSpecs,
    EquipmentType,
    DegradationModel,
    efficiency_degradation_curve,
)
from predictive_maintenance.domain.physics import (
    calculate_cop,
    calculate_eer,
    calculate_capacity,
    estimate_airflow,
    estimate_refrigerant_charge,
    diagnose_refrigerant_system,
)


class TestRefrigerantProperties:
    """Tests for refrigerant thermodynamic calculations"""
    
    def test_r410a_saturation_pressure(self):
        """Test R-410A saturation pressure calculation"""
        # At approximately 40°F, R-410A should be around 118 PSIG
        pressure = R410A.saturation_pressure(40)
        assert 100 < pressure < 140
    
    def test_r410a_saturation_temperature(self):
        """Test R-410A saturation temperature calculation"""
        # At 118 PSIG, should be around 40°F
        temp = R410A.saturation_temperature(118)
        assert 35 < temp < 50
    
    def test_superheat_calculation(self):
        """Test superheat calculation"""
        # Suction at 118 PSIG (sat temp ~40°F), measured 52°F
        superheat = R410A.superheat(118, 52)
        assert 10 < superheat < 14  # Should be ~12°F
    
    def test_subcool_calculation(self):
        """Test subcool calculation"""
        # Discharge at 400 PSIG (sat temp ~120°F), liquid at 110°F
        subcool = R410A.subcool(400, 110)
        assert 8 < subcool < 14  # Should be ~10°F
    
    def test_get_refrigerant_lookup(self):
        """Test refrigerant lookup"""
        ref = get_refrigerant("R410A")
        assert ref is not None
        assert ref.name == "R-410A"
        
        ref = get_refrigerant("R-22")
        assert ref is not None
        
        ref = get_refrigerant("unknown")
        assert ref is None
    
    def test_superheat_diagnosis(self):
        """Test superheat diagnosis"""
        # Normal superheat
        ok, diag = R410A.is_superheat_normal(12)
        assert ok
        assert diag == "optimal"
        
        # High superheat
        ok, diag = R410A.is_superheat_normal(25)
        assert not ok
        assert "high" in diag
        
        # Low superheat
        ok, diag = R410A.is_superheat_normal(3)
        assert not ok
        assert "low" in diag
    
    def test_subcool_diagnosis(self):
        """Test subcool diagnosis"""
        ok, diag = R410A.is_subcool_normal(10)
        assert ok
        
        ok, diag = R410A.is_subcool_normal(1)
        assert not ok


class TestEquipmentSpecs:
    """Tests for equipment specifications"""
    
    def test_rtu_specs_creation(self):
        """Test RTU specs creation"""
        from datetime import datetime
        
        specs = RTUSpecs(
            manufacturer="Carrier",
            model_number="48A",
            nominal_capacity_tons=5.0,
            refrigerant_type="R410A",
            install_date=datetime(2020, 1, 1),
        )
        
        assert specs.nominal_capacity_btuh == 60000  # 5 tons * 12000
        assert specs.nominal_cfm == 2000  # 5 tons * 400 CFM/ton
        assert specs.equipment_type == EquipmentType.RTU
    
    def test_equipment_age(self):
        """Test age calculation"""
        from datetime import datetime
        
        specs = RTUSpecs(
            manufacturer="Test",
            model_number="Test",
            nominal_capacity_tons=5.0,
            install_date=datetime(2020, 1, 1),
        )
        
        age = specs.age_years(reference_date=datetime(2025, 1, 1))
        assert 4.9 < age < 5.1
    
    def test_efficiency_degradation(self):
        """Test efficiency degradation estimation"""
        from datetime import datetime
        
        specs = RTUSpecs(
            manufacturer="Test",
            model_number="Test",
            nominal_capacity_tons=5.0,
            install_date=datetime(2015, 1, 1),  # 10 years old
        )
        
        degradation = specs.expected_efficiency_degradation(age_years=10)
        assert 0.6 < degradation < 0.9  # Should be degraded but not extreme


class TestDegradationModel:
    """Tests for degradation model"""
    
    def test_degradation_curve(self):
        """Test efficiency degradation curve"""
        # New equipment
        eff_new = efficiency_degradation_curve(0)
        assert eff_new > 0.99
        
        # 5 year old
        eff_5 = efficiency_degradation_curve(5)
        assert 0.8 < eff_5 < 1.0
        
        # 15 year old
        eff_15 = efficiency_degradation_curve(15)
        assert 0.6 < eff_15 < 0.85
        
        # Maintenance helps
        eff_maintained = efficiency_degradation_curve(10, maintenance_factor=1.0)
        eff_neglected = efficiency_degradation_curve(10, maintenance_factor=0.0)
        assert eff_maintained > eff_neglected
    
    def test_overall_health_score(self):
        """Test overall health score calculation"""
        from datetime import datetime
        
        specs = RTUSpecs(
            manufacturer="Test",
            model_number="Test",
            nominal_capacity_tons=5.0,
        )
        
        model = DegradationModel(
            asset_id="test",
            equipment_specs=specs,
            compressor_health=0.9,
            condenser_health=0.85,
            evaporator_health=0.8,
            fan_health=0.95,
            controls_health=1.0,
        )
        
        score = model.overall_health_score()
        assert 0.8 < score < 0.95


class TestPhysicsCalculations:
    """Tests for physics calculations"""
    
    def test_calculate_cop(self):
        """Test COP calculation"""
        # 60,000 BTU/hr capacity, 5000 watts input
        cop = calculate_cop(60000, 5000)
        
        # COP = 60000 / (5000 * 3.412) = ~3.52
        assert 3.4 < cop < 3.6
    
    def test_calculate_eer(self):
        """Test EER calculation"""
        # 60,000 BTU/hr, 5000 watts
        eer = calculate_eer(60000, 5000)
        
        # EER = 60000 / 5000 = 12
        assert eer == 12.0
    
    def test_calculate_capacity(self):
        """Test capacity calculation"""
        # 2000 CFM, 20°F delta T
        capacity = calculate_capacity(2000, 20)
        
        # Q = 1.08 * CFM * deltaT = 1.08 * 2000 * 20 = 43,200 BTU/hr
        assert 42000 < capacity < 44000
    
    def test_estimate_airflow(self):
        """Test airflow estimation"""
        # 55°F supply, 75°F return, 43,200 BTU/hr
        cfm = estimate_airflow(55, 75, 43200)
        
        # Should be ~2000 CFM
        assert 1900 < cfm < 2100
    
    def test_refrigerant_charge_estimation(self):
        """Test refrigerant charge estimation"""
        # Normal readings
        status, conf = estimate_refrigerant_charge(12, 10, 85, "txv")
        assert status == "normal"
        
        # Low subcool = undercharged
        status, conf = estimate_refrigerant_charge(15, 3, 85, "txv")
        assert status == "undercharged"
        
        # High subcool = overcharged
        status, conf = estimate_refrigerant_charge(10, 25, 85, "txv")
        assert status == "overcharged"
    
    def test_refrigerant_diagnosis(self):
        """Test comprehensive diagnosis"""
        diagnosis = diagnose_refrigerant_system(
            suction_pressure=118,
            discharge_pressure=400,
            suction_temp=52,
            liquid_temp=110,
            ambient_temp=95,
            refrigerant="R410A",
        )
        
        assert "superheat" in diagnosis
        assert "subcool" in diagnosis
        assert "status" in diagnosis
        assert diagnosis["superheat"] > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
