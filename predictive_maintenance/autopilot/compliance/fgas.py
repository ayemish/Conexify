"""
F-Gas Compliance Service

Implements EU F-gas Regulation (517/2014) compliance for refrigerant systems:
- Asset refrigerant metadata tracking
- Leak detection thresholds based on CO2 equivalent
- Leak check scheduling
- Refrigerant transaction logging
- Compliance logbook generation (Article 6)
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional
import uuid

logger = logging.getLogger(__name__)


class RefrigerantType(str, Enum):
    """Common refrigerant types with GWP values"""
    R410A = "R-410A"
    R404A = "R-404A"
    R134A = "R-134a"
    R407C = "R-407C"
    R22 = "R-22"
    R32 = "R-32"
    R290 = "R-290"  # Propane
    R744 = "R-744"  # CO2
    R1234YF = "R-1234yf"
    R1234ZE = "R-1234ze"


# Global Warming Potential (GWP) values per refrigerant
GWP_VALUES = {
    RefrigerantType.R410A: 2088,
    RefrigerantType.R404A: 3922,
    RefrigerantType.R134A: 1430,
    RefrigerantType.R407C: 1774,
    RefrigerantType.R22: 1810,
    RefrigerantType.R32: 675,
    RefrigerantType.R290: 3,
    RefrigerantType.R744: 1,
    RefrigerantType.R1234YF: 4,
    RefrigerantType.R1234ZE: 7,
}


class TransactionType(str, Enum):
    """Refrigerant transaction types"""
    INITIAL_CHARGE = "initial_charge"
    TOP_UP = "top_up"
    RECOVERY = "recovery"
    LEAK_DETECTED = "leak_detected"
    DECOMMISSION = "decommission"


class LeakCheckFrequency(str, Enum):
    """Required leak check frequencies based on CO2e threshold"""
    ANNUAL = "annual"          # 5-50 tCO2e
    SEMI_ANNUAL = "semi_annual"  # 50-500 tCO2e
    QUARTERLY = "quarterly"    # >500 tCO2e (with leak detection system: semi-annual)


@dataclass
class FGasThresholds:
    """EU F-gas regulation thresholds"""
    # CO2 equivalent thresholds (tonnes)
    LEAK_CHECK_THRESHOLD_LOW = 5.0      # Annual checks required above this
    LEAK_CHECK_THRESHOLD_MED = 50.0     # Semi-annual checks required above this
    LEAK_CHECK_THRESHOLD_HIGH = 500.0   # Quarterly checks required above this
    
    # Leak detection system thresholds
    LEAK_DETECTION_REQUIRED = 500.0     # Automatic leak detection required above this
    
    # Record keeping thresholds
    RECORD_KEEPING_THRESHOLD = 5.0      # Record keeping required above this
    
    # Maximum leak rate before mandatory repair (%)
    MAX_LEAK_RATE = 10.0


@dataclass
class RefrigerantAsset:
    """
    Refrigerant system asset with F-gas compliance metadata.
    
    Per EU F-gas Regulation Article 4, operators must:
    - Maintain records of refrigerant quantities
    - Track leak checks and repairs
    - Ensure proper leak detection for large systems
    """
    asset_id: str
    tenant_id: str
    site_id: str
    
    # Refrigerant info
    refrigerant_type: RefrigerantType
    charge_kg: float  # Current charge in kg
    original_charge_kg: float  # Factory charge
    
    # Calculated values
    co2_equivalent_tonnes: float = 0.0
    
    # Leak detection
    has_leak_detection: bool = False
    leak_detection_type: str = ""  # pressure, ultrasonic, etc.
    
    # Compliance status
    last_leak_check: Optional[datetime] = None
    next_leak_check_due: Optional[datetime] = None
    leak_check_frequency: LeakCheckFrequency = LeakCheckFrequency.ANNUAL
    
    # Metadata
    manufacturer: str = ""
    model: str = ""
    serial_number: str = ""
    installation_date: Optional[datetime] = None
    
    # Lifecycle
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    decommissioned_at: Optional[datetime] = None
    
    def __post_init__(self):
        self._calculate_co2e()
        self._determine_leak_check_frequency()
    
    def _calculate_co2e(self):
        """Calculate CO2 equivalent in tonnes"""
        gwp = GWP_VALUES.get(self.refrigerant_type, 0)
        self.co2_equivalent_tonnes = (self.charge_kg * gwp) / 1000
    
    def _determine_leak_check_frequency(self):
        """Determine required leak check frequency based on CO2e"""
        thresholds = FGasThresholds()
        
        if self.co2_equivalent_tonnes >= thresholds.LEAK_CHECK_THRESHOLD_HIGH:
            if self.has_leak_detection:
                self.leak_check_frequency = LeakCheckFrequency.SEMI_ANNUAL
            else:
                self.leak_check_frequency = LeakCheckFrequency.QUARTERLY
        elif self.co2_equivalent_tonnes >= thresholds.LEAK_CHECK_THRESHOLD_MED:
            self.leak_check_frequency = LeakCheckFrequency.SEMI_ANNUAL
        elif self.co2_equivalent_tonnes >= thresholds.LEAK_CHECK_THRESHOLD_LOW:
            self.leak_check_frequency = LeakCheckFrequency.ANNUAL
    
    def requires_leak_detection(self) -> bool:
        """Check if automatic leak detection is required"""
        return self.co2_equivalent_tonnes >= FGasThresholds.LEAK_DETECTION_REQUIRED
    
    def requires_record_keeping(self) -> bool:
        """Check if F-gas record keeping is required"""
        return self.co2_equivalent_tonnes >= FGasThresholds.RECORD_KEEPING_THRESHOLD
    
    def calculate_next_leak_check(self) -> datetime:
        """Calculate when next leak check is due"""
        if not self.last_leak_check:
            return datetime.utcnow()
        
        intervals = {
            LeakCheckFrequency.ANNUAL: timedelta(days=365),
            LeakCheckFrequency.SEMI_ANNUAL: timedelta(days=182),
            LeakCheckFrequency.QUARTERLY: timedelta(days=91),
        }
        
        interval = intervals.get(self.leak_check_frequency, timedelta(days=365))
        return self.last_leak_check + interval
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "asset_id": self.asset_id,
            "tenant_id": self.tenant_id,
            "site_id": self.site_id,
            "refrigerant_type": self.refrigerant_type.value,
            "charge_kg": self.charge_kg,
            "original_charge_kg": self.original_charge_kg,
            "co2_equivalent_tonnes": self.co2_equivalent_tonnes,
            "has_leak_detection": self.has_leak_detection,
            "leak_check_frequency": self.leak_check_frequency.value,
            "last_leak_check": self.last_leak_check.isoformat() if self.last_leak_check else None,
            "next_leak_check_due": self.next_leak_check_due.isoformat() if self.next_leak_check_due else None,
            "requires_leak_detection": self.requires_leak_detection(),
            "requires_record_keeping": self.requires_record_keeping(),
        }


@dataclass
class LeakCheckRecord:
    """Record of a leak check inspection"""
    record_id: str = field(default_factory=lambda: f"LCR-{uuid.uuid4().hex[:8].upper()}")
    asset_id: str = ""
    tenant_id: str = ""
    
    # Check details
    check_date: datetime = field(default_factory=datetime.utcnow)
    technician_id: str = ""
    technician_name: str = ""
    technician_certification: str = ""  # F-gas certification number
    
    # Results
    leak_detected: bool = False
    leak_location: str = ""
    estimated_leak_rate_kg_year: float = 0.0
    
    # Measurements
    system_pressure_bar: Optional[float] = None
    superheat_k: Optional[float] = None
    subcool_k: Optional[float] = None
    
    # Repair info (if leak detected)
    repair_completed: bool = False
    repair_date: Optional[datetime] = None
    repair_description: str = ""
    
    # Follow-up
    follow_up_check_required: bool = False
    follow_up_check_date: Optional[datetime] = None
    
    # Notes
    notes: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "record_id": self.record_id,
            "asset_id": self.asset_id,
            "check_date": self.check_date.isoformat(),
            "technician_name": self.technician_name,
            "technician_certification": self.technician_certification,
            "leak_detected": self.leak_detected,
            "leak_location": self.leak_location,
            "estimated_leak_rate_kg_year": self.estimated_leak_rate_kg_year,
            "repair_completed": self.repair_completed,
            "repair_date": self.repair_date.isoformat() if self.repair_date else None,
            "notes": self.notes,
        }


@dataclass
class RefrigerantTransaction:
    """Record of refrigerant addition or recovery"""
    transaction_id: str = field(default_factory=lambda: f"RTX-{uuid.uuid4().hex[:8].upper()}")
    asset_id: str = ""
    tenant_id: str = ""
    
    # Transaction details
    transaction_type: TransactionType = TransactionType.TOP_UP
    transaction_date: datetime = field(default_factory=datetime.utcnow)
    
    # Refrigerant info
    refrigerant_type: RefrigerantType = RefrigerantType.R410A
    quantity_kg: float = 0.0
    
    # For recovery
    recovered_to: str = ""  # Cylinder ID, reclamation facility, etc.
    
    # Technician
    technician_id: str = ""
    technician_name: str = ""
    technician_certification: str = ""
    
    # Related records
    leak_check_record_id: Optional[str] = None
    incident_id: Optional[str] = None
    
    # Notes
    notes: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "transaction_id": self.transaction_id,
            "asset_id": self.asset_id,
            "transaction_type": self.transaction_type.value,
            "transaction_date": self.transaction_date.isoformat(),
            "refrigerant_type": self.refrigerant_type.value,
            "quantity_kg": self.quantity_kg,
            "technician_name": self.technician_name,
            "technician_certification": self.technician_certification,
            "incident_id": self.incident_id,
            "notes": self.notes,
        }


@dataclass
class ComplianceLogbook:
    """
    F-gas compliance logbook for an asset.
    
    Per EU F-gas Regulation Article 6, operators must maintain records of:
    - Quantity and type of refrigerant
    - Quantity added/recovered
    - Results of leak checks
    - Technician details and certifications
    """
    asset_id: str
    tenant_id: str
    site_id: str
    
    # Asset info
    asset: Optional[RefrigerantAsset] = None
    
    # Records
    leak_checks: List[LeakCheckRecord] = field(default_factory=list)
    transactions: List[RefrigerantTransaction] = field(default_factory=list)
    
    # Summary
    total_refrigerant_added_kg: float = 0.0
    total_refrigerant_recovered_kg: float = 0.0
    estimated_annual_leak_rate_percent: float = 0.0
    
    # Compliance status
    is_compliant: bool = True
    compliance_issues: List[str] = field(default_factory=list)
    
    # Generated
    generated_at: datetime = field(default_factory=datetime.utcnow)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "asset_id": self.asset_id,
            "tenant_id": self.tenant_id,
            "site_id": self.site_id,
            "asset": self.asset.to_dict() if self.asset else None,
            "leak_checks": [lc.to_dict() for lc in self.leak_checks],
            "transactions": [t.to_dict() for t in self.transactions],
            "total_refrigerant_added_kg": self.total_refrigerant_added_kg,
            "total_refrigerant_recovered_kg": self.total_refrigerant_recovered_kg,
            "estimated_annual_leak_rate_percent": self.estimated_annual_leak_rate_percent,
            "is_compliant": self.is_compliant,
            "compliance_issues": self.compliance_issues,
            "generated_at": self.generated_at.isoformat(),
        }
    
    def to_text(self) -> str:
        """Generate text format logbook for export"""
        lines = [
            "=" * 80,
            "F-GAS COMPLIANCE LOGBOOK",
            "EU Regulation 517/2014",
            "=" * 80,
            "",
            f"Asset ID: {self.asset_id}",
            f"Site ID: {self.site_id}",
            f"Generated: {self.generated_at.isoformat()}",
            "",
        ]
        
        if self.asset:
            lines.extend([
                "-" * 40,
                "EQUIPMENT DETAILS",
                "-" * 40,
                f"Refrigerant Type: {self.asset.refrigerant_type.value}",
                f"Current Charge: {self.asset.charge_kg:.2f} kg",
                f"Original Charge: {self.asset.original_charge_kg:.2f} kg",
                f"CO2 Equivalent: {self.asset.co2_equivalent_tonnes:.2f} tonnes",
                f"Leak Detection System: {'Yes' if self.asset.has_leak_detection else 'No'}",
                f"Required Check Frequency: {self.asset.leak_check_frequency.value}",
                "",
            ])
        
        lines.extend([
            "-" * 40,
            "LEAK CHECK RECORDS",
            "-" * 40,
        ])
        
        for lc in self.leak_checks:
            lines.extend([
                f"Date: {lc.check_date.isoformat()}",
                f"Technician: {lc.technician_name} (Cert: {lc.technician_certification})",
                f"Leak Detected: {'Yes' if lc.leak_detected else 'No'}",
            ])
            if lc.leak_detected:
                lines.append(f"Location: {lc.leak_location}")
                lines.append(f"Est. Leak Rate: {lc.estimated_leak_rate_kg_year:.2f} kg/year")
            if lc.repair_completed:
                lines.append(f"Repair Completed: {lc.repair_date.isoformat()}")
            lines.append("")
        
        lines.extend([
            "-" * 40,
            "REFRIGERANT TRANSACTIONS",
            "-" * 40,
        ])
        
        for tx in self.transactions:
            lines.extend([
                f"Date: {tx.transaction_date.isoformat()}",
                f"Type: {tx.transaction_type.value}",
                f"Quantity: {tx.quantity_kg:.2f} kg {tx.refrigerant_type.value}",
                f"Technician: {tx.technician_name} (Cert: {tx.technician_certification})",
                "",
            ])
        
        lines.extend([
            "-" * 40,
            "SUMMARY",
            "-" * 40,
            f"Total Added: {self.total_refrigerant_added_kg:.2f} kg",
            f"Total Recovered: {self.total_refrigerant_recovered_kg:.2f} kg",
            f"Est. Annual Leak Rate: {self.estimated_annual_leak_rate_percent:.1f}%",
            "",
            f"Compliance Status: {'COMPLIANT' if self.is_compliant else 'NON-COMPLIANT'}",
        ])
        
        if self.compliance_issues:
            lines.append("Issues:")
            for issue in self.compliance_issues:
                lines.append(f"  - {issue}")
        
        lines.extend([
            "",
            "=" * 80,
        ])
        
        return "\n".join(lines)


class FGasComplianceService:
    """
    F-Gas compliance management service.
    
    Provides:
    - Asset refrigerant metadata management
    - Leak check scheduling and tracking
    - Transaction logging
    - Compliance logbook generation
    - Integration with autopilot incidents
    """
    
    def __init__(self, session_factory: Callable = None):
        self.session_factory = session_factory
        
        # In-memory storage (would be database in production)
        self._assets: Dict[str, RefrigerantAsset] = {}
        self._leak_checks: Dict[str, List[LeakCheckRecord]] = {}
        self._transactions: Dict[str, List[RefrigerantTransaction]] = {}
    
    def register_asset(self, asset: RefrigerantAsset) -> str:
        """Register a refrigerant asset"""
        asset.next_leak_check_due = asset.calculate_next_leak_check()
        self._assets[asset.asset_id] = asset
        self._leak_checks[asset.asset_id] = []
        self._transactions[asset.asset_id] = []
        
        logger.info(
            f"Registered refrigerant asset {asset.asset_id}: "
            f"{asset.refrigerant_type.value} {asset.charge_kg}kg "
            f"({asset.co2_equivalent_tonnes:.1f} tCO2e)"
        )
        
        return asset.asset_id
    
    def get_asset(self, asset_id: str) -> Optional[RefrigerantAsset]:
        """Get a refrigerant asset"""
        return self._assets.get(asset_id)
    
    def record_leak_check(self, record: LeakCheckRecord) -> str:
        """Record a leak check inspection"""
        if record.asset_id not in self._leak_checks:
            self._leak_checks[record.asset_id] = []
        
        self._leak_checks[record.asset_id].append(record)
        
        # Update asset last check date
        asset = self._assets.get(record.asset_id)
        if asset:
            asset.last_leak_check = record.check_date
            asset.next_leak_check_due = asset.calculate_next_leak_check()
            asset.updated_at = datetime.utcnow()
        
        logger.info(
            f"Recorded leak check for {record.asset_id}: "
            f"leak_detected={record.leak_detected}"
        )
        
        return record.record_id
    
    def record_transaction(self, transaction: RefrigerantTransaction) -> str:
        """Record a refrigerant transaction"""
        if transaction.asset_id not in self._transactions:
            self._transactions[transaction.asset_id] = []
        
        self._transactions[transaction.asset_id].append(transaction)
        
        # Update asset charge
        asset = self._assets.get(transaction.asset_id)
        if asset:
            if transaction.transaction_type in [TransactionType.INITIAL_CHARGE, TransactionType.TOP_UP]:
                asset.charge_kg += transaction.quantity_kg
            elif transaction.transaction_type == TransactionType.RECOVERY:
                asset.charge_kg -= transaction.quantity_kg
            
            asset._calculate_co2e()
            asset._determine_leak_check_frequency()
            asset.updated_at = datetime.utcnow()
        
        logger.info(
            f"Recorded {transaction.transaction_type.value} for {transaction.asset_id}: "
            f"{transaction.quantity_kg}kg {transaction.refrigerant_type.value}"
        )
        
        return transaction.transaction_id
    
    def generate_logbook(self, asset_id: str) -> ComplianceLogbook:
        """Generate compliance logbook for an asset"""
        asset = self._assets.get(asset_id)
        leak_checks = self._leak_checks.get(asset_id, [])
        transactions = self._transactions.get(asset_id, [])
        
        logbook = ComplianceLogbook(
            asset_id=asset_id,
            tenant_id=asset.tenant_id if asset else "",
            site_id=asset.site_id if asset else "",
            asset=asset,
            leak_checks=sorted(leak_checks, key=lambda x: x.check_date, reverse=True),
            transactions=sorted(transactions, key=lambda x: x.transaction_date, reverse=True),
        )
        
        # Calculate totals
        for tx in transactions:
            if tx.transaction_type in [TransactionType.INITIAL_CHARGE, TransactionType.TOP_UP]:
                logbook.total_refrigerant_added_kg += tx.quantity_kg
            elif tx.transaction_type == TransactionType.RECOVERY:
                logbook.total_refrigerant_recovered_kg += tx.quantity_kg
        
        # Calculate annual leak rate
        if asset and asset.original_charge_kg > 0:
            net_loss = logbook.total_refrigerant_added_kg - logbook.total_refrigerant_recovered_kg
            # Rough annual estimate
            logbook.estimated_annual_leak_rate_percent = (net_loss / asset.original_charge_kg) * 100
        
        # Check compliance
        logbook.compliance_issues = self._check_compliance(asset, leak_checks)
        logbook.is_compliant = len(logbook.compliance_issues) == 0
        
        return logbook
    
    def _check_compliance(
        self,
        asset: Optional[RefrigerantAsset],
        leak_checks: List[LeakCheckRecord],
    ) -> List[str]:
        """Check for compliance issues"""
        issues = []
        
        if not asset:
            return issues
        
        # Check if leak detection is required but not present
        if asset.requires_leak_detection() and not asset.has_leak_detection:
            issues.append(
                f"Automatic leak detection system required (CO2e > 500t) but not installed"
            )
        
        # Check if leak check is overdue
        if asset.next_leak_check_due and datetime.utcnow() > asset.next_leak_check_due:
            days_overdue = (datetime.utcnow() - asset.next_leak_check_due).days
            issues.append(
                f"Leak check overdue by {days_overdue} days"
            )
        
        # Check for unrepaired leaks
        for lc in leak_checks:
            if lc.leak_detected and not lc.repair_completed:
                days_since = (datetime.utcnow() - lc.check_date).days
                if days_since > 14:  # Must repair within 14 days per F-gas regulation
                    issues.append(
                        f"Leak detected on {lc.check_date.date()} not repaired within 14 days"
                    )
        
        # Check annual leak rate
        if asset.original_charge_kg > 0:
            added = sum(
                tx.quantity_kg for tx in self._transactions.get(asset.asset_id, [])
                if tx.transaction_type == TransactionType.TOP_UP
            )
            leak_rate = (added / asset.original_charge_kg) * 100
            if leak_rate > FGasThresholds.MAX_LEAK_RATE:
                issues.append(
                    f"Annual leak rate ({leak_rate:.1f}%) exceeds maximum ({FGasThresholds.MAX_LEAK_RATE}%)"
                )
        
        return issues
    
    def get_assets_needing_check(
        self,
        tenant_id: str = None,
        days_lookahead: int = 30,
    ) -> List[RefrigerantAsset]:
        """Get assets with leak checks due soon"""
        cutoff = datetime.utcnow() + timedelta(days=days_lookahead)
        
        due = []
        for asset in self._assets.values():
            if tenant_id and asset.tenant_id != tenant_id:
                continue
            if asset.next_leak_check_due and asset.next_leak_check_due <= cutoff:
                due.append(asset)
        
        return sorted(due, key=lambda a: a.next_leak_check_due or datetime.max)
    
    def create_leak_incident(
        self,
        asset_id: str,
        estimated_leak_kg: float,
        detection_source: str = "autopilot",
    ) -> Dict[str, Any]:
        """
        Create a compliance case for a detected leak.
        
        Returns incident data for autopilot processing.
        """
        asset = self._assets.get(asset_id)
        if not asset:
            raise ValueError(f"Asset {asset_id} not found")
        
        incident_id = f"LEAK-{uuid.uuid4().hex[:8].upper()}"
        
        # Record leak detection transaction
        transaction = RefrigerantTransaction(
            asset_id=asset_id,
            tenant_id=asset.tenant_id,
            transaction_type=TransactionType.LEAK_DETECTED,
            refrigerant_type=asset.refrigerant_type,
            quantity_kg=estimated_leak_kg,
            incident_id=incident_id,
            notes=f"Leak detected by {detection_source}",
        )
        self.record_transaction(transaction)
        
        # Create incident data
        incident_data = {
            "incident_id": incident_id,
            "tenant_id": asset.tenant_id,
            "site_id": asset.site_id,
            "asset_id": asset_id,
            "fault_type": "refrigerant_leak",
            "severity": self._calculate_leak_severity(asset, estimated_leak_kg),
            "source": detection_source,
            "trigger_evidence": {
                "estimated_leak_kg": estimated_leak_kg,
                "refrigerant_type": asset.refrigerant_type.value,
                "co2_equivalent_kg": estimated_leak_kg * GWP_VALUES.get(asset.refrigerant_type, 0),
                "asset_charge_kg": asset.charge_kg,
                "leak_percentage": (estimated_leak_kg / asset.charge_kg) * 100 if asset.charge_kg > 0 else 0,
            },
            "compliance_required": True,
            "compliance_type": "fgas",
        }
        
        logger.info(
            f"Created leak incident {incident_id} for asset {asset_id}: "
            f"~{estimated_leak_kg}kg {asset.refrigerant_type.value}"
        )
        
        return incident_data
    
    def _calculate_leak_severity(
        self,
        asset: RefrigerantAsset,
        estimated_leak_kg: float,
    ) -> str:
        """Calculate severity based on leak size"""
        if asset.charge_kg <= 0:
            return "high"
        
        leak_percentage = (estimated_leak_kg / asset.charge_kg) * 100
        
        if leak_percentage > 20:
            return "critical"
        elif leak_percentage > 10:
            return "high"
        elif leak_percentage > 5:
            return "medium"
        else:
            return "low"
