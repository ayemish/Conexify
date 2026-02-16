"""
Tests for F-Gas Compliance Service
"""

import pytest
from datetime import datetime, timedelta
from predictive_maintenance.autopilot.compliance.fgas import (
    FGasComplianceService,
    RefrigerantAsset,
    LeakCheckRecord,
    RefrigerantTransaction,
    RefrigerantType,
    TransactionType,
    LeakCheckFrequency,
    GWP_VALUES,
    FGasThresholds,
)


@pytest.fixture
def service():
    return FGasComplianceService()


@pytest.fixture
def sample_asset():
    return RefrigerantAsset(
        asset_id="RTU-001",
        tenant_id="tenant-001",
        site_id="site-001",
        refrigerant_type=RefrigerantType.R410A,
        charge_kg=50.0,
        original_charge_kg=50.0,
        has_leak_detection=False,
    )


@pytest.fixture
def large_asset():
    """Asset with CO2e > 500 tonnes (requires leak detection)"""
    return RefrigerantAsset(
        asset_id="CHILLER-001",
        tenant_id="tenant-001",
        site_id="site-001",
        refrigerant_type=RefrigerantType.R404A,
        charge_kg=200.0,
        original_charge_kg=200.0,
        has_leak_detection=True,
    )


class TestRefrigerantAsset:
    """Test RefrigerantAsset calculations"""
    
    def test_co2e_calculation(self, sample_asset):
        # R-410A GWP = 2088
        # 50 kg * 2088 / 1000 = 104.4 tonnes
        expected = 50.0 * GWP_VALUES[RefrigerantType.R410A] / 1000
        assert abs(sample_asset.co2_equivalent_tonnes - expected) < 0.1
    
    def test_leak_check_frequency_medium(self, sample_asset):
        # 104.4 tCO2e -> semi-annual checks
        assert sample_asset.leak_check_frequency == LeakCheckFrequency.SEMI_ANNUAL
    
    def test_leak_check_frequency_high(self, large_asset):
        # R-404A GWP = 3922, 200 kg = 784.4 tCO2e
        # With leak detection -> semi-annual
        assert large_asset.co2_equivalent_tonnes > 500
        assert large_asset.leak_check_frequency == LeakCheckFrequency.SEMI_ANNUAL
    
    def test_leak_check_frequency_high_no_detection(self):
        asset = RefrigerantAsset(
            asset_id="TEST-001",
            tenant_id="t1",
            site_id="s1",
            refrigerant_type=RefrigerantType.R404A,
            charge_kg=200.0,
            original_charge_kg=200.0,
            has_leak_detection=False,
        )
        # Without leak detection -> quarterly
        assert asset.leak_check_frequency == LeakCheckFrequency.QUARTERLY
    
    def test_requires_leak_detection(self, large_asset):
        assert large_asset.requires_leak_detection() == True
    
    def test_requires_record_keeping(self, sample_asset):
        # > 5 tCO2e requires record keeping
        assert sample_asset.requires_record_keeping() == True
    
    def test_low_gwp_no_record_keeping(self):
        # R-290 (propane) GWP = 3
        # 10 kg * 3 / 1000 = 0.03 tCO2e < 5
        asset = RefrigerantAsset(
            asset_id="SMALL-001",
            tenant_id="t1",
            site_id="s1",
            refrigerant_type=RefrigerantType.R290,
            charge_kg=10.0,
            original_charge_kg=10.0,
        )
        assert asset.requires_record_keeping() == False
    
    def test_calculate_next_leak_check(self, sample_asset):
        sample_asset.last_leak_check = datetime.utcnow()
        next_check = sample_asset.calculate_next_leak_check()
        
        # Semi-annual = ~182 days
        expected = sample_asset.last_leak_check + timedelta(days=182)
        assert abs((next_check - expected).days) < 1


class TestFGasComplianceService:
    """Test FGasComplianceService operations"""
    
    def test_register_asset(self, service, sample_asset):
        asset_id = service.register_asset(sample_asset)
        
        assert asset_id == "RTU-001"
        
        retrieved = service.get_asset("RTU-001")
        assert retrieved is not None
        assert retrieved.refrigerant_type == RefrigerantType.R410A
    
    def test_record_leak_check(self, service, sample_asset):
        service.register_asset(sample_asset)
        
        record = LeakCheckRecord(
            asset_id="RTU-001",
            tenant_id="tenant-001",
            technician_name="John Smith",
            technician_certification="FGAS-12345",
            leak_detected=False,
        )
        
        record_id = service.record_leak_check(record)
        
        assert record_id is not None
        
        # Check asset updated
        asset = service.get_asset("RTU-001")
        assert asset.last_leak_check is not None
    
    def test_record_leak_check_with_leak(self, service, sample_asset):
        service.register_asset(sample_asset)
        
        record = LeakCheckRecord(
            asset_id="RTU-001",
            tenant_id="tenant-001",
            technician_name="Jane Doe",
            technician_certification="FGAS-67890",
            leak_detected=True,
            leak_location="Suction line fitting",
            estimated_leak_rate_kg_year=5.0,
        )
        
        service.record_leak_check(record)
        
        # Generate logbook
        logbook = service.generate_logbook("RTU-001")
        assert len(logbook.leak_checks) == 1
        assert logbook.leak_checks[0].leak_detected == True
    
    def test_record_transaction_topup(self, service, sample_asset):
        service.register_asset(sample_asset)
        
        transaction = RefrigerantTransaction(
            asset_id="RTU-001",
            tenant_id="tenant-001",
            transaction_type=TransactionType.TOP_UP,
            refrigerant_type=RefrigerantType.R410A,
            quantity_kg=5.0,
            technician_name="Tech One",
            technician_certification="FGAS-11111",
        )
        
        tx_id = service.record_transaction(transaction)
        
        assert tx_id is not None
        
        # Check charge updated
        asset = service.get_asset("RTU-001")
        assert asset.charge_kg == 55.0  # 50 + 5
    
    def test_record_transaction_recovery(self, service, sample_asset):
        service.register_asset(sample_asset)
        
        transaction = RefrigerantTransaction(
            asset_id="RTU-001",
            tenant_id="tenant-001",
            transaction_type=TransactionType.RECOVERY,
            refrigerant_type=RefrigerantType.R410A,
            quantity_kg=10.0,
            technician_name="Tech Two",
            technician_certification="FGAS-22222",
        )
        
        service.record_transaction(transaction)
        
        # Check charge updated
        asset = service.get_asset("RTU-001")
        assert asset.charge_kg == 40.0  # 50 - 10
    
    def test_generate_logbook(self, service, sample_asset):
        service.register_asset(sample_asset)
        
        # Add leak check
        service.record_leak_check(LeakCheckRecord(
            asset_id="RTU-001",
            tenant_id="tenant-001",
            technician_name="Tech",
            technician_certification="CERT-001",
        ))
        
        # Add transactions
        service.record_transaction(RefrigerantTransaction(
            asset_id="RTU-001",
            tenant_id="tenant-001",
            transaction_type=TransactionType.TOP_UP,
            refrigerant_type=RefrigerantType.R410A,
            quantity_kg=3.0,
            technician_name="Tech",
            technician_certification="CERT-001",
        ))
        
        logbook = service.generate_logbook("RTU-001")
        
        assert logbook.asset_id == "RTU-001"
        assert logbook.asset is not None
        assert len(logbook.leak_checks) == 1
        assert len(logbook.transactions) == 1
        assert logbook.total_refrigerant_added_kg == 3.0
    
    def test_compliance_check_overdue_leak_check(self, service, sample_asset):
        # Set last check to long ago
        sample_asset.last_leak_check = datetime.utcnow() - timedelta(days=200)
        sample_asset.next_leak_check_due = sample_asset.calculate_next_leak_check()
        
        service.register_asset(sample_asset)
        
        logbook = service.generate_logbook("RTU-001")
        
        assert logbook.is_compliant == False
        assert any("overdue" in issue.lower() for issue in logbook.compliance_issues)
    
    def test_compliance_check_unrepaired_leak(self, service, sample_asset):
        service.register_asset(sample_asset)
        
        # Record leak without repair
        record = LeakCheckRecord(
            asset_id="RTU-001",
            tenant_id="tenant-001",
            check_date=datetime.utcnow() - timedelta(days=20),  # >14 days ago
            technician_name="Tech",
            technician_certification="CERT",
            leak_detected=True,
            repair_completed=False,
        )
        service.record_leak_check(record)
        
        logbook = service.generate_logbook("RTU-001")
        
        assert logbook.is_compliant == False
        assert any("14 days" in issue for issue in logbook.compliance_issues)
    
    def test_compliance_check_missing_leak_detection(self, service):
        # Large asset without required leak detection
        asset = RefrigerantAsset(
            asset_id="BIG-001",
            tenant_id="t1",
            site_id="s1",
            refrigerant_type=RefrigerantType.R404A,
            charge_kg=200.0,
            original_charge_kg=200.0,
            has_leak_detection=False,
        )
        
        service.register_asset(asset)
        
        logbook = service.generate_logbook("BIG-001")
        
        assert logbook.is_compliant == False
        assert any("leak detection" in issue.lower() for issue in logbook.compliance_issues)
    
    def test_get_assets_needing_check(self, service):
        # Asset with check due soon
        asset1 = RefrigerantAsset(
            asset_id="DUE-001",
            tenant_id="t1",
            site_id="s1",
            refrigerant_type=RefrigerantType.R410A,
            charge_kg=50.0,
            original_charge_kg=50.0,
        )
        asset1.last_leak_check = datetime.utcnow() - timedelta(days=170)
        asset1.next_leak_check_due = asset1.calculate_next_leak_check()
        
        # Asset with check not due
        asset2 = RefrigerantAsset(
            asset_id="NOTDUE-001",
            tenant_id="t1",
            site_id="s1",
            refrigerant_type=RefrigerantType.R410A,
            charge_kg=50.0,
            original_charge_kg=50.0,
        )
        asset2.last_leak_check = datetime.utcnow()
        asset2.next_leak_check_due = asset2.calculate_next_leak_check()
        
        service.register_asset(asset1)
        service.register_asset(asset2)
        
        due_soon = service.get_assets_needing_check(days_lookahead=30)
        
        assert len(due_soon) == 1
        assert due_soon[0].asset_id == "DUE-001"
    
    def test_create_leak_incident(self, service, sample_asset):
        service.register_asset(sample_asset)
        
        incident = service.create_leak_incident(
            asset_id="RTU-001",
            estimated_leak_kg=5.0,
            detection_source="autopilot",
        )
        
        assert "incident_id" in incident
        assert incident["fault_type"] == "refrigerant_leak"
        assert incident["compliance_type"] == "fgas"
        assert incident["trigger_evidence"]["estimated_leak_kg"] == 5.0
    
    def test_logbook_text_export(self, service, sample_asset):
        service.register_asset(sample_asset)
        
        logbook = service.generate_logbook("RTU-001")
        text = logbook.to_text()
        
        assert "F-GAS COMPLIANCE LOGBOOK" in text
        assert "RTU-001" in text
        assert "R-410A" in text


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
