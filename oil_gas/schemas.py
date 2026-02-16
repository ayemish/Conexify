"""
Oil & Gas Telemetry Monitoring - Data Contracts

Defines data structures for oil & gas telemetry monitoring.
Based on industry standards: OPC-UA, WITSML, PRODML.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from enum import Enum
import json


class SensorType(str, Enum):
    """Types of oilfield sensors"""
    PRESSURE = "pressure"
    TEMPERATURE = "temperature"
    FLOW_RATE = "flow_rate"
    VIBRATION = "vibration"
    LEVEL = "level"
    GAS_DETECTOR = "gas_detector"
    VALVE_POSITION = "valve_position"
    PUMP_STATUS = "pump_status"
    MOTOR_CURRENT = "motor_current"
    CASING_PRESSURE = "casing_pressure"
    TUBING_PRESSURE = "tubing_pressure"
    BOTTOMHOLE_PRESSURE = "bottomhole_pressure"
    CHOKE_POSITION = "choke_position"
    H2S_DETECTOR = "h2s_detector"


class AlertSeverity(str, Enum):
    """Alert severity levels"""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"
    EMERGENCY = "emergency"


class WellType(str, Enum):
    """Types of wells"""
    PRODUCTION = "production"
    INJECTION = "injection"
    DISPOSAL = "disposal"
    OBSERVATION = "observation"


class MaintenanceType(str, Enum):
    """Types of maintenance"""
    PREVENTIVE = "preventive"
    CORRECTIVE = "corrective"
    PREDICTIVE = "predictive"
    EMERGENCY = "emergency"


@dataclass
class SensorConfig:
    """Configuration for a sensor"""
    sensor_id: str
    sensor_type: SensorType
    name: str
    unit: str
    
    # Thresholds
    min_value: float = 0.0
    max_value: float = float('inf')
    warning_low: Optional[float] = None
    warning_high: Optional[float] = None
    critical_low: Optional[float] = None
    critical_high: Optional[float] = None
    
    # Sampling
    sample_rate_seconds: int = 60
    
    # Location
    well_id: Optional[str] = None
    equipment_id: Optional[str] = None


@dataclass
class WellConfig:
    """Configuration for a well"""
    well_id: str
    well_name: str
    well_type: WellType
    
    # Location
    latitude: float = 0.0
    longitude: float = 0.0
    field_name: str = ""
    
    # Characteristics
    depth_ft: float = 0.0
    target_production_bpd: float = 0.0
    
    # Sensors
    sensors: List[SensorConfig] = field(default_factory=list)
    
    # Status
    is_active: bool = True
    last_maintenance: Optional[datetime] = None


@dataclass
class OilGasConfig:
    """Configuration for Oil & Gas monitoring"""
    site_id: str
    site_name: str
    operator: str
    
    # Wells
    wells: List[WellConfig] = field(default_factory=list)
    
    # Monitoring settings
    anomaly_sensitivity: float = 2.0  # Z-score threshold
    prediction_horizon_hours: int = 24
    
    # Alert settings
    alert_cooldown_minutes: int = 15
    auto_acknowledge_info: bool = True
    
    # Compliance
    regulatory_body: str = "API"
    h2s_threshold_ppm: float = 10.0
    flare_limit_mscfd: float = 1000.0


@dataclass
class TelemetryReading:
    """A single telemetry reading"""
    sensor_id: str
    timestamp: datetime
    value: float
    unit: str
    
    # Quality
    quality: float = 1.0  # 0-1 quality score
    is_valid: bool = True
    
    # Context
    well_id: Optional[str] = None
    equipment_id: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "sensor_id": self.sensor_id,
            "timestamp": self.timestamp.isoformat(),
            "value": self.value,
            "unit": self.unit,
            "quality": self.quality,
        }


@dataclass
class AnomalyAlert:
    """An anomaly detection alert"""
    alert_id: str
    sensor_id: str
    well_id: str
    severity: AlertSeverity
    
    # Anomaly details
    anomaly_type: str  # spike, drift, flatline, out_of_range
    current_value: float
    expected_value: float
    deviation: float
    z_score: float
    
    # Timing
    detected_at: datetime
    acknowledged: bool = False
    acknowledged_by: Optional[str] = None
    
    # Resolution
    resolved: bool = False
    resolution_notes: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "alert_id": self.alert_id,
            "sensor_id": self.sensor_id,
            "well_id": self.well_id,
            "severity": self.severity.value,
            "anomaly_type": self.anomaly_type,
            "current_value": self.current_value,
            "z_score": self.z_score,
            "detected_at": self.detected_at.isoformat(),
        }


@dataclass
class MaintenancePrediction:
    """Predictive maintenance prediction"""
    equipment_id: str
    well_id: str
    
    # Prediction
    failure_probability: float
    predicted_failure_date: Optional[datetime]
    remaining_useful_life_hours: float
    confidence: float
    
    # Recommendation
    maintenance_type: MaintenanceType
    recommended_action: str
    priority: int  # 1-5
    estimated_downtime_hours: float
    estimated_cost: float
    
    # Model info
    model_version: str = "v1"
    predicted_at: datetime = field(default_factory=datetime.utcnow)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "equipment_id": self.equipment_id,
            "well_id": self.well_id,
            "failure_probability": self.failure_probability,
            "remaining_useful_life_hours": self.remaining_useful_life_hours,
            "recommended_action": self.recommended_action,
            "priority": self.priority,
        }


@dataclass
class ProductionMetrics:
    """Production metrics for a well"""
    well_id: str
    timestamp: datetime
    
    # Production
    oil_rate_bpd: float = 0.0
    gas_rate_mscfd: float = 0.0
    water_rate_bpd: float = 0.0
    
    # Derived
    gor_scf_bbl: float = 0.0  # Gas-Oil Ratio
    water_cut_pct: float = 0.0
    
    # Pressures
    tubing_pressure_psi: float = 0.0
    casing_pressure_psi: float = 0.0
    
    # Efficiency
    uptime_pct: float = 100.0
    efficiency_pct: float = 100.0
    
    def compute_derived(self):
        """Compute derived metrics"""
        if self.oil_rate_bpd > 0:
            self.gor_scf_bbl = self.gas_rate_mscfd * 1000 / self.oil_rate_bpd
        
        total_liquid = self.oil_rate_bpd + self.water_rate_bpd
        if total_liquid > 0:
            self.water_cut_pct = (self.water_rate_bpd / total_liquid) * 100
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "well_id": self.well_id,
            "timestamp": self.timestamp.isoformat(),
            "oil_rate_bpd": self.oil_rate_bpd,
            "gas_rate_mscfd": self.gas_rate_mscfd,
            "water_cut_pct": self.water_cut_pct,
            "efficiency_pct": self.efficiency_pct,
        }


@dataclass
class SafetyStatus:
    """Safety status for a site/well"""
    site_id: str
    timestamp: datetime
    
    # Overall status
    is_safe: bool = True
    active_alerts: int = 0
    critical_alerts: int = 0
    
    # Gas detection
    h2s_detected: bool = False
    h2s_level_ppm: float = 0.0
    lel_detected: bool = False
    lel_level_pct: float = 0.0
    
    # Pressure safety
    overpressure_risk: bool = False
    max_pressure_pct: float = 0.0
    
    # Personnel
    personnel_on_site: int = 0
    emergency_muster_required: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "site_id": self.site_id,
            "is_safe": self.is_safe,
            "active_alerts": self.active_alerts,
            "critical_alerts": self.critical_alerts,
            "h2s_level_ppm": self.h2s_level_ppm,
        }


@dataclass
class ComplianceReport:
    """Regulatory compliance report"""
    report_id: str
    site_id: str
    period_start: datetime
    period_end: datetime
    
    # Status
    is_compliant: bool = True
    violations: List[str] = field(default_factory=list)
    
    # Metrics
    flare_volume_mscf: float = 0.0
    vented_volume_mscf: float = 0.0
    spill_incidents: int = 0
    safety_incidents: int = 0
    
    # Environmental
    emissions_co2_tons: float = 0.0
    emissions_ch4_tons: float = 0.0
    water_usage_bbl: float = 0.0
    
    # Generated
    generated_at: datetime = field(default_factory=datetime.utcnow)
    regulatory_body: str = "API"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "report_id": self.report_id,
            "site_id": self.site_id,
            "is_compliant": self.is_compliant,
            "violations": self.violations,
            "period_start": self.period_start.isoformat(),
            "period_end": self.period_end.isoformat(),
        }


@dataclass
class OilGasDecisionPack:
    """Complete Oil & Gas monitoring decision package"""
    pack_id: str
    site_id: str
    created_at: datetime
    
    # Status
    production_metrics: Dict[str, ProductionMetrics]
    safety_status: SafetyStatus
    
    # Alerts & Predictions
    active_alerts: List[AnomalyAlert]
    maintenance_predictions: List[MaintenancePrediction]
    
    # Compliance
    compliance_report: Optional[ComplianceReport]
    
    # Recommendations
    recommendations: List[Dict[str, Any]]
    executive_summary: str
    
    # Overall
    overall_health_score: float = 1.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "pack_id": self.pack_id,
            "site_id": self.site_id,
            "created_at": self.created_at.isoformat(),
            "overall_health_score": self.overall_health_score,
            "n_alerts": len(self.active_alerts),
            "n_maintenance_items": len(self.maintenance_predictions),
            "is_compliant": self.compliance_report.is_compliant if self.compliance_report else True,
        }
    
    def save(self, path: str):
        """Save decision pack to JSON"""
        from pathlib import Path as PathLib
        PathLib(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2, default=str)
