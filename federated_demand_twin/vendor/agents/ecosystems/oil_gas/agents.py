"""
Oil & Gas Telemetry Monitoring - Agents

CrewAI-compliant agents for oil & gas operations monitoring and optimization.
"""

import numpy as np
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
import logging
import hashlib

from ...crewai_base import (
    DemandTwinAgent,
    CrewAIAgentConfig,
    AgentCategory,
    AgentRole,
    AgentMessageBus,
    MessageType,
    AgentMessage,
)

from .schemas import (
    OilGasConfig,
    WellConfig,
    SensorConfig,
    SensorType,
    TelemetryReading,
    AnomalyAlert,
    AlertSeverity,
    MaintenancePrediction,
    MaintenanceType,
    ProductionMetrics,
    SafetyStatus,
    ComplianceReport,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TelemetryIngestionAgent(DemandTwinAgent):
    """
    Ingests and validates sensor telemetry data.
    """
    
    def __init__(
        self,
        site_id: str,
        sensors: List[SensorConfig],
        message_bus: Optional[AgentMessageBus] = None,
    ):
        config = CrewAIAgentConfig(
            agent_id=f"oilgas-{site_id}-telemetry",
            role=AgentRole.DATA_STEWARD,
            category=AgentCategory.DATA,
            name="Telemetry Data Steward",
            goal="Ingest and validate sensor telemetry data streams",
            backstory="""You are responsible for ensuring telemetry data quality 
            in oil & gas operations. You validate sensor readings, detect 
            communication failures, and maintain data integrity.""",
            retailer_id=site_id,
        )
        super().__init__(config, message_bus)
        
        self.sensors = {s.sensor_id: s for s in sensors}
        self.reading_history: Dict[str, List[TelemetryReading]] = {}
        self.quality_scores: Dict[str, float] = {}
    
    def ingest_readings(
        self,
        readings: List[TelemetryReading]
    ) -> Dict[str, Any]:
        """Ingest and validate telemetry readings"""
        valid_count = 0
        invalid_count = 0
        issues = []
        
        for reading in readings:
            sensor = self.sensors.get(reading.sensor_id)
            if not sensor:
                issues.append(f"Unknown sensor: {reading.sensor_id}")
                reading.is_valid = False
                invalid_count += 1
                continue
            
            # Validate range
            if reading.value < sensor.min_value or reading.value > sensor.max_value:
                reading.is_valid = False
                reading.quality = 0.5
                issues.append(f"{reading.sensor_id}: Value {reading.value} out of range")
                invalid_count += 1
            else:
                valid_count += 1
            
            # Store in history
            if reading.sensor_id not in self.reading_history:
                self.reading_history[reading.sensor_id] = []
            self.reading_history[reading.sensor_id].append(reading)
            
            # Keep last 1000 readings per sensor
            if len(self.reading_history[reading.sensor_id]) > 1000:
                self.reading_history[reading.sensor_id] = self.reading_history[reading.sensor_id][-1000:]
        
        # Compute quality scores
        for sensor_id, history in self.reading_history.items():
            valid = sum(1 for r in history[-100:] if r.is_valid)
            self.quality_scores[sensor_id] = valid / max(len(history[-100:]), 1)
        
        result = {
            "total_readings": len(readings),
            "valid": valid_count,
            "invalid": invalid_count,
            "issues": issues[:10],  # Top 10 issues
            "quality_scores": self.quality_scores,
            "ingested_at": datetime.utcnow().isoformat(),
        }
        
        self.log_action("ingest_readings", {"n_readings": len(readings)}, result)
        return result
    
    def get_sensor_history(
        self,
        sensor_id: str,
        n_readings: int = 100
    ) -> List[TelemetryReading]:
        """Get recent readings for a sensor"""
        return self.reading_history.get(sensor_id, [])[-n_readings:]


class AnomalyDetectionAgent(DemandTwinAgent):
    """
    Detects anomalies in sensor data using statistical methods.
    """
    
    def __init__(
        self,
        site_id: str,
        sensitivity: float = 2.0,
        message_bus: Optional[AgentMessageBus] = None,
    ):
        config = CrewAIAgentConfig(
            agent_id=f"oilgas-{site_id}-anomaly",
            role=AgentRole.ANOMALY_DETECTOR,
            category=AgentCategory.ANALYTICS,
            name="Anomaly Detector",
            goal="Detect anomalies in sensor telemetry streams",
            backstory="""You specialize in anomaly detection for industrial 
            equipment. You use statistical methods to identify spikes, drifts, 
            and unusual patterns in sensor data.""",
            retailer_id=site_id,
        )
        super().__init__(config, message_bus)
        
        self.sensitivity = sensitivity
        self.baselines: Dict[str, Dict[str, float]] = {}  # sensor_id -> {mean, std}
        self.active_alerts: List[AnomalyAlert] = []
    
    def update_baseline(
        self,
        sensor_id: str,
        readings: List[TelemetryReading]
    ):
        """Update baseline statistics for a sensor"""
        values = [r.value for r in readings if r.is_valid]
        if len(values) >= 10:
            self.baselines[sensor_id] = {
                "mean": float(np.mean(values)),
                "std": float(np.std(values)),
                "min": float(np.min(values)),
                "max": float(np.max(values)),
            }
    
    def detect_anomalies(
        self,
        readings: List[TelemetryReading],
        well_id: str
    ) -> List[AnomalyAlert]:
        """Detect anomalies in readings"""
        alerts = []
        
        for reading in readings:
            if not reading.is_valid:
                continue
            
            baseline = self.baselines.get(reading.sensor_id)
            if not baseline or baseline["std"] < 1e-6:
                continue
            
            # Z-score
            z_score = abs(reading.value - baseline["mean"]) / baseline["std"]
            
            if z_score > self.sensitivity:
                # Determine severity
                if z_score > self.sensitivity * 2:
                    severity = AlertSeverity.CRITICAL
                elif z_score > self.sensitivity * 1.5:
                    severity = AlertSeverity.WARNING
                else:
                    severity = AlertSeverity.INFO
                
                # Determine anomaly type
                if reading.value > baseline["mean"]:
                    anomaly_type = "high_spike"
                else:
                    anomaly_type = "low_spike"
                
                alert = AnomalyAlert(
                    alert_id=hashlib.md5(f"{reading.sensor_id}_{reading.timestamp}".encode()).hexdigest()[:12],
                    sensor_id=reading.sensor_id,
                    well_id=well_id,
                    severity=severity,
                    anomaly_type=anomaly_type,
                    current_value=reading.value,
                    expected_value=baseline["mean"],
                    deviation=reading.value - baseline["mean"],
                    z_score=z_score,
                    detected_at=datetime.utcnow(),
                )
                
                alerts.append(alert)
                self.active_alerts.append(alert)
        
        self.log_action("detect_anomalies", {"n_readings": len(readings)}, {"n_alerts": len(alerts)})
        return alerts


class PredictiveMaintenanceAgent(DemandTwinAgent):
    """
    Predicts equipment failures and maintenance needs.
    """
    
    def __init__(
        self,
        site_id: str,
        prediction_horizon_hours: int = 24,
        message_bus: Optional[AgentMessageBus] = None,
    ):
        config = CrewAIAgentConfig(
            agent_id=f"oilgas-{site_id}-maintenance",
            role=AgentRole.FORECASTER,
            category=AgentCategory.ANALYTICS,
            name="Predictive Maintenance Analyst",
            goal="Predict equipment failures before they occur",
            backstory="""You are an expert in predictive maintenance for oil & gas 
            equipment. You analyze sensor trends to predict failures and recommend 
            proactive maintenance actions.""",
            retailer_id=site_id,
        )
        super().__init__(config, message_bus)
        
        self.horizon_hours = prediction_horizon_hours
        self.predictions: List[MaintenancePrediction] = []
    
    def predict_maintenance(
        self,
        equipment_id: str,
        well_id: str,
        sensor_history: Dict[str, List[TelemetryReading]],
        anomaly_alerts: List[AnomalyAlert]
    ) -> Optional[MaintenancePrediction]:
        """Predict maintenance needs for equipment"""
        # Simple heuristic-based prediction
        # In production, this would use ML models
        
        # Count recent anomalies for this equipment
        recent_alerts = [
            a for a in anomaly_alerts
            if a.well_id == well_id and 
            (datetime.utcnow() - a.detected_at).total_seconds() < 86400
        ]
        
        critical_count = sum(1 for a in recent_alerts if a.severity == AlertSeverity.CRITICAL)
        warning_count = sum(1 for a in recent_alerts if a.severity == AlertSeverity.WARNING)
        
        # Calculate failure probability
        base_probability = 0.01
        failure_probability = base_probability + critical_count * 0.2 + warning_count * 0.05
        failure_probability = min(failure_probability, 0.95)
        
        if failure_probability < 0.1:
            return None  # Low risk, no prediction needed
        
        # Estimate remaining useful life
        if failure_probability > 0.5:
            rul_hours = 12
            priority = 1
            maintenance_type = MaintenanceType.EMERGENCY
            action = "Immediate inspection required"
        elif failure_probability > 0.3:
            rul_hours = 48
            priority = 2
            maintenance_type = MaintenanceType.PREDICTIVE
            action = "Schedule maintenance within 48 hours"
        else:
            rul_hours = 168
            priority = 3
            maintenance_type = MaintenanceType.PREVENTIVE
            action = "Monitor closely, schedule preventive maintenance"
        
        prediction = MaintenancePrediction(
            equipment_id=equipment_id,
            well_id=well_id,
            failure_probability=failure_probability,
            predicted_failure_date=datetime.utcnow() + timedelta(hours=rul_hours),
            remaining_useful_life_hours=rul_hours,
            confidence=0.7,
            maintenance_type=maintenance_type,
            recommended_action=action,
            priority=priority,
            estimated_downtime_hours=4 if priority <= 2 else 8,
            estimated_cost=5000 if priority <= 2 else 15000,
        )
        
        self.predictions.append(prediction)
        self.log_action("predict_maintenance", {"equipment_id": equipment_id}, prediction.to_dict())
        
        return prediction


class ProductionOptimizationAgent(DemandTwinAgent):
    """
    Optimizes well production parameters.
    """
    
    def __init__(
        self,
        site_id: str,
        message_bus: Optional[AgentMessageBus] = None,
    ):
        config = CrewAIAgentConfig(
            agent_id=f"oilgas-{site_id}-production",
            role=AgentRole.BUDGET_OPTIMIZER,
            category=AgentCategory.OPTIMIZATION,
            name="Production Optimizer",
            goal="Optimize well production while maintaining safety",
            backstory="""You optimize oil & gas production parameters. You balance 
            maximizing production with equipment longevity, safety constraints, 
            and regulatory requirements.""",
            retailer_id=site_id,
        )
        super().__init__(config, message_bus)
    
    def compute_metrics(
        self,
        well_id: str,
        readings: Dict[str, List[TelemetryReading]]
    ) -> ProductionMetrics:
        """Compute production metrics from telemetry"""
        metrics = ProductionMetrics(
            well_id=well_id,
            timestamp=datetime.utcnow(),
        )
        
        # Extract values from readings
        for sensor_id, sensor_readings in readings.items():
            if not sensor_readings:
                continue
            
            latest = sensor_readings[-1]
            
            if "flow" in sensor_id.lower() or "rate" in sensor_id.lower():
                if "oil" in sensor_id.lower():
                    metrics.oil_rate_bpd = latest.value
                elif "gas" in sensor_id.lower():
                    metrics.gas_rate_mscfd = latest.value
                elif "water" in sensor_id.lower():
                    metrics.water_rate_bpd = latest.value
            elif "tubing" in sensor_id.lower() and "pressure" in sensor_id.lower():
                metrics.tubing_pressure_psi = latest.value
            elif "casing" in sensor_id.lower() and "pressure" in sensor_id.lower():
                metrics.casing_pressure_psi = latest.value
        
        metrics.compute_derived()
        return metrics
    
    def optimize_production(
        self,
        well_config: WellConfig,
        current_metrics: ProductionMetrics,
        safety_status: SafetyStatus
    ) -> Dict[str, Any]:
        """Generate production optimization recommendations"""
        recommendations = []
        
        # Check if under target
        if current_metrics.oil_rate_bpd < well_config.target_production_bpd * 0.8:
            gap_pct = (well_config.target_production_bpd - current_metrics.oil_rate_bpd) / well_config.target_production_bpd
            recommendations.append({
                "type": "increase_production",
                "message": f"Production {gap_pct:.1%} below target",
                "suggested_action": "Consider adjusting choke position or pump rate",
                "priority": 2,
            })
        
        # Check water cut
        if current_metrics.water_cut_pct > 50:
            recommendations.append({
                "type": "high_water_cut",
                "message": f"Water cut at {current_metrics.water_cut_pct:.1f}%",
                "suggested_action": "Evaluate water shutoff options",
                "priority": 2,
            })
        
        # Check pressure differential
        if current_metrics.tubing_pressure_psi > 0 and current_metrics.casing_pressure_psi > 0:
            diff = abs(current_metrics.tubing_pressure_psi - current_metrics.casing_pressure_psi)
            if diff > 500:
                recommendations.append({
                    "type": "pressure_differential",
                    "message": f"Large pressure differential: {diff:.0f} psi",
                    "suggested_action": "Check for casing leak or tubing issue",
                    "priority": 1,
                })
        
        return {
            "well_id": well_config.well_id,
            "current_efficiency": current_metrics.efficiency_pct,
            "recommendations": recommendations,
            "analyzed_at": datetime.utcnow().isoformat(),
        }


class SafetyMonitoringAgent(DemandTwinAgent):
    """
    Monitors safety thresholds and conditions.
    """
    
    def __init__(
        self,
        site_id: str,
        config: OilGasConfig,
        message_bus: Optional[AgentMessageBus] = None,
    ):
        agent_config = CrewAIAgentConfig(
            agent_id=f"oilgas-{site_id}-safety",
            role=AgentRole.POLICY_VALIDATOR,
            category=AgentCategory.GOVERNANCE,
            name="Safety Monitor",
            goal="Ensure all operations meet safety requirements",
            backstory="""You are the safety watchdog for oil & gas operations. 
            You monitor H2S levels, pressure limits, and other safety-critical 
            parameters. Safety is always your top priority.""",
            retailer_id=site_id,
        )
        super().__init__(agent_config, message_bus)
        
        self.og_config = config
    
    def assess_safety(
        self,
        readings: List[TelemetryReading],
        alerts: List[AnomalyAlert]
    ) -> SafetyStatus:
        """Assess overall safety status"""
        status = SafetyStatus(
            site_id=self.og_config.site_id,
            timestamp=datetime.utcnow(),
        )
        
        # Count alerts
        status.active_alerts = len([a for a in alerts if not a.resolved])
        status.critical_alerts = len([a for a in alerts if a.severity == AlertSeverity.CRITICAL and not a.resolved])
        
        # Check H2S
        for reading in readings:
            if "h2s" in reading.sensor_id.lower():
                status.h2s_level_ppm = max(status.h2s_level_ppm, reading.value)
                if reading.value > self.og_config.h2s_threshold_ppm:
                    status.h2s_detected = True
        
        # Check LEL (Lower Explosive Limit)
        for reading in readings:
            if "lel" in reading.sensor_id.lower() or "gas_detector" in reading.sensor_id.lower():
                status.lel_level_pct = max(status.lel_level_pct, reading.value)
                if reading.value > 10:  # 10% LEL is concerning
                    status.lel_detected = True
        
        # Determine overall safety
        status.is_safe = (
            not status.h2s_detected and
            not status.lel_detected and
            status.critical_alerts == 0
        )
        
        if status.h2s_detected or status.lel_detected:
            status.emergency_muster_required = True
        
        return status


class ComplianceAgent(DemandTwinAgent):
    """
    Ensures regulatory compliance.
    """
    
    def __init__(
        self,
        site_id: str,
        config: OilGasConfig,
        message_bus: Optional[AgentMessageBus] = None,
    ):
        agent_config = CrewAIAgentConfig(
            agent_id=f"oilgas-{site_id}-compliance",
            role=AgentRole.COMPLIANCE_CHECKER,
            category=AgentCategory.GOVERNANCE,
            name="Compliance Officer",
            goal="Ensure all operations meet regulatory requirements",
            backstory="""You ensure compliance with API, EPA, and state 
            regulations for oil & gas operations. You track emissions, 
            spills, and safety incidents for reporting.""",
            retailer_id=site_id,
        )
        super().__init__(agent_config, message_bus)
        
        self.og_config = config
    
    def generate_compliance_report(
        self,
        period_start: datetime,
        period_end: datetime,
        production_metrics: Dict[str, ProductionMetrics],
        safety_incidents: List[AnomalyAlert]
    ) -> ComplianceReport:
        """Generate compliance report for a period"""
        violations = []
        
        # Check flaring
        total_flare = sum(
            m.gas_rate_mscfd * 0.05  # Assume 5% flared
            for m in production_metrics.values()
        ) * (period_end - period_start).days
        
        if total_flare > self.og_config.flare_limit_mscfd * (period_end - period_start).days:
            violations.append("Flare volume exceeded daily limit")
        
        # Count safety incidents
        critical_incidents = len([a for a in safety_incidents if a.severity == AlertSeverity.CRITICAL])
        
        report = ComplianceReport(
            report_id=hashlib.md5(f"{self.og_config.site_id}_{period_start}".encode()).hexdigest()[:12],
            site_id=self.og_config.site_id,
            period_start=period_start,
            period_end=period_end,
            is_compliant=len(violations) == 0,
            violations=violations,
            flare_volume_mscf=total_flare,
            safety_incidents=critical_incidents,
            regulatory_body=self.og_config.regulatory_body,
        )
        
        return report


class AlertAgent(DemandTwinAgent):
    """
    Manages and routes alerts.
    """
    
    def __init__(
        self,
        site_id: str,
        cooldown_minutes: int = 15,
        message_bus: Optional[AgentMessageBus] = None,
    ):
        config = CrewAIAgentConfig(
            agent_id=f"oilgas-{site_id}-alerts",
            role=AgentRole.RATIONALE_GENERATOR,
            category=AgentCategory.COMMUNICATION,
            name="Alert Manager",
            goal="Manage, prioritize, and route operational alerts",
            backstory="""You manage the alert system for oil & gas operations. 
            You consolidate, prioritize, and route alerts to ensure critical 
            issues get immediate attention.""",
            retailer_id=site_id,
        )
        super().__init__(config, message_bus)
        
        self.cooldown_minutes = cooldown_minutes
        self.alert_history: List[AnomalyAlert] = []
        self.last_alert_time: Dict[str, datetime] = {}
    
    def process_alerts(
        self,
        new_alerts: List[AnomalyAlert]
    ) -> List[AnomalyAlert]:
        """Process and filter alerts"""
        processed = []
        
        for alert in new_alerts:
            # Check cooldown
            key = f"{alert.sensor_id}_{alert.anomaly_type}"
            last_time = self.last_alert_time.get(key)
            
            if last_time:
                minutes_since = (datetime.utcnow() - last_time).total_seconds() / 60
                if minutes_since < self.cooldown_minutes and alert.severity != AlertSeverity.EMERGENCY:
                    continue  # Skip due to cooldown
            
            self.last_alert_time[key] = datetime.utcnow()
            self.alert_history.append(alert)
            processed.append(alert)
        
        return processed
    
    def get_active_alerts(
        self,
        severity: Optional[AlertSeverity] = None
    ) -> List[AnomalyAlert]:
        """Get active (unresolved) alerts"""
        active = [a for a in self.alert_history if not a.resolved]
        if severity:
            active = [a for a in active if a.severity == severity]
        return active


class ReportingAgent(DemandTwinAgent):
    """
    Generates operational reports.
    """
    
    def __init__(
        self,
        site_id: str,
        message_bus: Optional[AgentMessageBus] = None,
    ):
        config = CrewAIAgentConfig(
            agent_id=f"oilgas-{site_id}-reporting",
            role=AgentRole.REPORT_WRITER,
            category=AgentCategory.COMMUNICATION,
            name="Operations Reporter",
            goal="Generate comprehensive operational reports",
            backstory="""You compile operational data into clear, actionable 
            reports for operations managers and executives.""",
            retailer_id=site_id,
        )
        super().__init__(config, message_bus)
    
    def generate_executive_summary(
        self,
        production_metrics: Dict[str, ProductionMetrics],
        safety_status: SafetyStatus,
        active_alerts: List[AnomalyAlert],
        maintenance_predictions: List[MaintenancePrediction]
    ) -> str:
        """Generate executive summary"""
        total_oil = sum(m.oil_rate_bpd for m in production_metrics.values())
        total_gas = sum(m.gas_rate_mscfd for m in production_metrics.values())
        
        summary = f"""## Oil & Gas Operations Summary

**Report Generated:** {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}

### Production Overview
- **Total Oil Production:** {total_oil:,.0f} BPD
- **Total Gas Production:** {total_gas:,.0f} MSCFD
- **Active Wells:** {len(production_metrics)}

### Safety Status
- **Status:** {'✅ SAFE' if safety_status.is_safe else '🚨 ALERT'}
- **Active Alerts:** {len(active_alerts)}
- **Critical Alerts:** {safety_status.critical_alerts}
- **H2S Level:** {safety_status.h2s_level_ppm:.1f} ppm

### Maintenance
- **Pending Predictions:** {len(maintenance_predictions)}
- **High Priority Items:** {len([p for p in maintenance_predictions if p.priority <= 2])}

### Recommendations
"""
        
        for pred in sorted(maintenance_predictions, key=lambda x: x.priority)[:3]:
            summary += f"- **{pred.equipment_id}**: {pred.recommended_action} (Priority {pred.priority})\n"
        
        return summary
