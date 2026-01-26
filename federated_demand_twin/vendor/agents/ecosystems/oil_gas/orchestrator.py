"""
Oil & Gas Telemetry Monitoring - Orchestrator

Coordinates the complete oil & gas monitoring workflow.
"""

import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
import hashlib

from ...crewai_base import AgentRegistry, AgentMessageBus

from .schemas import (
    OilGasConfig,
    WellConfig,
    SensorConfig,
    SensorType,
    WellType,
    TelemetryReading,
    OilGasDecisionPack,
)

from .agents import (
    TelemetryIngestionAgent,
    AnomalyDetectionAgent,
    PredictiveMaintenanceAgent,
    ProductionOptimizationAgent,
    SafetyMonitoringAgent,
    ComplianceAgent,
    AlertAgent,
    ReportingAgent,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class OilGasOrchestrator:
    """
    Orchestrates the Oil & Gas monitoring workflow.
    
    Pipeline: Ingest → Detect → Predict → Optimize → Safety → Compliance → Alert → Report
    """
    
    def __init__(self, config: OilGasConfig):
        self.config = config
        self.registry = AgentRegistry.get_instance()
        self.message_bus = self.registry.message_bus
        
        self._initialize_agents()
        
        self.run_history: List[OilGasDecisionPack] = []
        logger.info(f"OilGasOrchestrator initialized for {config.site_name}")
    
    def _initialize_agents(self):
        """Initialize all Oil & Gas agents"""
        site_id = self.config.site_id
        
        # Collect all sensors from all wells
        all_sensors = []
        for well in self.config.wells:
            all_sensors.extend(well.sensors)
        
        self.ingestion_agent = TelemetryIngestionAgent(site_id, all_sensors, self.message_bus)
        self.anomaly_agent = AnomalyDetectionAgent(site_id, self.config.anomaly_sensitivity, self.message_bus)
        self.maintenance_agent = PredictiveMaintenanceAgent(site_id, self.config.prediction_horizon_hours, self.message_bus)
        self.production_agent = ProductionOptimizationAgent(site_id, self.message_bus)
        self.safety_agent = SafetyMonitoringAgent(site_id, self.config, self.message_bus)
        self.compliance_agent = ComplianceAgent(site_id, self.config, self.message_bus)
        self.alert_agent = AlertAgent(site_id, self.config.alert_cooldown_minutes, self.message_bus)
        self.reporting_agent = ReportingAgent(site_id, self.message_bus)
        
        # Register agents
        for agent in [
            self.ingestion_agent, self.anomaly_agent, self.maintenance_agent,
            self.production_agent, self.safety_agent, self.compliance_agent,
            self.alert_agent, self.reporting_agent
        ]:
            self.registry.register(agent)
        
        logger.info(f"Initialized 8 Oil & Gas agents")
    
    def run(
        self,
        telemetry_readings: List[TelemetryReading],
        include_compliance: bool = True,
    ) -> OilGasDecisionPack:
        """
        Run the complete Oil & Gas monitoring workflow.
        
        Args:
            telemetry_readings: Current telemetry readings from sensors
            include_compliance: Whether to generate compliance report
        
        Returns:
            OilGasDecisionPack with status and recommendations
        """
        run_id = hashlib.md5(
            f"{datetime.utcnow().isoformat()}_{self.config.site_id}".encode()
        ).hexdigest()[:12]
        
        logger.info(f"Starting Oil & Gas monitoring run {run_id}")
        
        # 1. Ingest and validate telemetry
        logger.info("Step 1: Telemetry ingestion")
        ingestion_result = self.ingestion_agent.ingest_readings(telemetry_readings)
        
        # 2. Update baselines and detect anomalies
        logger.info("Step 2: Anomaly detection")
        all_alerts = []
        for well in self.config.wells:
            well_readings = [r for r in telemetry_readings if r.well_id == well.well_id]
            
            # Update baselines
            for sensor in well.sensors:
                sensor_readings = self.ingestion_agent.get_sensor_history(sensor.sensor_id)
                if len(sensor_readings) >= 50:
                    self.anomaly_agent.update_baseline(sensor.sensor_id, sensor_readings)
            
            # Detect anomalies
            alerts = self.anomaly_agent.detect_anomalies(well_readings, well.well_id)
            all_alerts.extend(alerts)
        
        # 3. Predictive maintenance
        logger.info("Step 3: Predictive maintenance")
        maintenance_predictions = []
        for well in self.config.wells:
            sensor_history = {
                s.sensor_id: self.ingestion_agent.get_sensor_history(s.sensor_id)
                for s in well.sensors
            }
            well_alerts = [a for a in all_alerts if a.well_id == well.well_id]
            
            prediction = self.maintenance_agent.predict_maintenance(
                equipment_id=f"{well.well_id}_pump",
                well_id=well.well_id,
                sensor_history=sensor_history,
                anomaly_alerts=well_alerts
            )
            if prediction:
                maintenance_predictions.append(prediction)
        
        # 4. Production metrics and optimization
        logger.info("Step 4: Production optimization")
        production_metrics = {}
        for well in self.config.wells:
            well_readings = {
                r.sensor_id: [r] for r in telemetry_readings if r.well_id == well.well_id
            }
            metrics = self.production_agent.compute_metrics(well.well_id, well_readings)
            production_metrics[well.well_id] = metrics
        
        # 5. Safety assessment
        logger.info("Step 5: Safety monitoring")
        safety_status = self.safety_agent.assess_safety(telemetry_readings, all_alerts)
        
        # 6. Compliance (optional)
        logger.info("Step 6: Compliance check")
        compliance_report = None
        if include_compliance:
            compliance_report = self.compliance_agent.generate_compliance_report(
                period_start=datetime.utcnow() - timedelta(days=1),
                period_end=datetime.utcnow(),
                production_metrics=production_metrics,
                safety_incidents=all_alerts
            )
        
        # 7. Process and route alerts
        logger.info("Step 7: Alert processing")
        processed_alerts = self.alert_agent.process_alerts(all_alerts)
        active_alerts = self.alert_agent.get_active_alerts()
        
        # 8. Generate report
        logger.info("Step 8: Reporting")
        executive_summary = self.reporting_agent.generate_executive_summary(
            production_metrics, safety_status, active_alerts, maintenance_predictions
        )
        
        # Build recommendations
        recommendations = []
        for pred in maintenance_predictions:
            recommendations.append({
                "type": "maintenance",
                "equipment_id": pred.equipment_id,
                "action": pred.recommended_action,
                "priority": pred.priority,
            })
        
        # Calculate health score
        health_score = 1.0
        if safety_status.critical_alerts > 0:
            health_score -= 0.3
        if not safety_status.is_safe:
            health_score -= 0.2
        health_score -= len(maintenance_predictions) * 0.05
        health_score = max(0.1, health_score)
        
        # Build decision pack
        decision_pack = OilGasDecisionPack(
            pack_id=run_id,
            site_id=self.config.site_id,
            created_at=datetime.utcnow(),
            production_metrics=production_metrics,
            safety_status=safety_status,
            active_alerts=active_alerts,
            maintenance_predictions=maintenance_predictions,
            compliance_report=compliance_report,
            recommendations=recommendations,
            executive_summary=executive_summary,
            overall_health_score=health_score,
        )
        
        self.run_history.append(decision_pack)
        logger.info(f"Oil & Gas monitoring complete. Health score: {health_score:.2f}")
        
        return decision_pack
    
    def get_agent_summary(self) -> Dict[str, Any]:
        """Get summary of Oil & Gas agents"""
        return {
            "ecosystem": "Oil & Gas Telemetry",
            "site_id": self.config.site_id,
            "n_wells": len(self.config.wells),
            "n_sensors": sum(len(w.sensors) for w in self.config.wells),
            "agents": [
                "TelemetryIngestion", "AnomalyDetection", "PredictiveMaintenance",
                "ProductionOptimization", "SafetyMonitoring", "Compliance",
                "AlertManager", "Reporting"
            ],
        }


def create_oil_gas_orchestrator(
    site_id: str,
    site_name: str,
    operator: str = "Demo Operator",
    wells: Optional[List[Dict[str, Any]]] = None,
    **kwargs
) -> OilGasOrchestrator:
    """Factory function for Oil & Gas orchestrator"""
    
    # Default wells if not provided
    if wells is None:
        wells = [
            {
                "well_id": "well_001",
                "well_name": "Production Well 1",
                "well_type": WellType.PRODUCTION,
                "target_production_bpd": 500,
                "sensors": [
                    {"sensor_id": "well_001_tubing_pressure", "sensor_type": SensorType.TUBING_PRESSURE, "name": "Tubing Pressure", "unit": "psi", "max_value": 5000},
                    {"sensor_id": "well_001_casing_pressure", "sensor_type": SensorType.CASING_PRESSURE, "name": "Casing Pressure", "unit": "psi", "max_value": 3000},
                    {"sensor_id": "well_001_oil_flow", "sensor_type": SensorType.FLOW_RATE, "name": "Oil Flow Rate", "unit": "bpd", "max_value": 1000},
                    {"sensor_id": "well_001_gas_flow", "sensor_type": SensorType.FLOW_RATE, "name": "Gas Flow Rate", "unit": "mscfd", "max_value": 5000},
                    {"sensor_id": "well_001_temperature", "sensor_type": SensorType.TEMPERATURE, "name": "Wellhead Temp", "unit": "F", "max_value": 300},
                    {"sensor_id": "well_001_h2s", "sensor_type": SensorType.H2S_DETECTOR, "name": "H2S Detector", "unit": "ppm", "max_value": 100, "critical_high": 10},
                ],
            },
            {
                "well_id": "well_002",
                "well_name": "Production Well 2",
                "well_type": WellType.PRODUCTION,
                "target_production_bpd": 350,
                "sensors": [
                    {"sensor_id": "well_002_tubing_pressure", "sensor_type": SensorType.TUBING_PRESSURE, "name": "Tubing Pressure", "unit": "psi", "max_value": 5000},
                    {"sensor_id": "well_002_casing_pressure", "sensor_type": SensorType.CASING_PRESSURE, "name": "Casing Pressure", "unit": "psi", "max_value": 3000},
                    {"sensor_id": "well_002_oil_flow", "sensor_type": SensorType.FLOW_RATE, "name": "Oil Flow Rate", "unit": "bpd", "max_value": 800},
                    {"sensor_id": "well_002_vibration", "sensor_type": SensorType.VIBRATION, "name": "Pump Vibration", "unit": "mm/s", "max_value": 20, "warning_high": 10},
                ],
            },
        ]
    
    # Build well configs
    well_configs = []
    for w in wells:
        sensors = [
            SensorConfig(
                sensor_id=s.get("sensor_id", f"sensor_{i}"),
                sensor_type=s.get("sensor_type", SensorType.PRESSURE),
                name=s.get("name", f"Sensor {i}"),
                unit=s.get("unit", ""),
                min_value=s.get("min_value", 0),
                max_value=s.get("max_value", float('inf')),
                warning_high=s.get("warning_high"),
                critical_high=s.get("critical_high"),
                well_id=w.get("well_id"),
            )
            for i, s in enumerate(w.get("sensors", []))
        ]
        
        well_configs.append(WellConfig(
            well_id=w.get("well_id", f"well_{len(well_configs)}"),
            well_name=w.get("well_name", f"Well {len(well_configs)}"),
            well_type=w.get("well_type", WellType.PRODUCTION),
            target_production_bpd=w.get("target_production_bpd", 0),
            sensors=sensors,
        ))
    
    config = OilGasConfig(
        site_id=site_id,
        site_name=site_name,
        operator=operator,
        wells=well_configs,
        **kwargs
    )
    
    return OilGasOrchestrator(config)
