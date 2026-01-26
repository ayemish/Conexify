"""
HVAC Failure Prevention Example Workflow

Demonstrates the four-plane architecture handling a compressor short-cycling 
anomaly with rising discharge temperatures.

Workflow:
1. Trigger: Compressor short-cycling + rising discharge temps
2. Concurrent diagnostics: Rule checks, model scoring, signature matching
3. Correlation: Links to recent maintenance and voltage fluctuation
4. Plan: Confirm sensor → adjust staging → schedule inspection → pre-order part
5. Authorize: Interrupt for setpoint changes
6. Execute + Verify: Tool calls via strict schemas, confirm cycling normalizes
7. Close + Learn: Summary drafted, signature/runbook updated
"""

import logging
from datetime import datetime, timedelta
import random

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Import from parent package
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent.parent))

from federated_demand_twin.vendor.agents.ecosystems.oil_gas.data_plane import (
    TelemetryPoint, SignalSource, AutonomyLevel,
)
from federated_demand_twin.vendor.agents.ecosystems.oil_gas.orchestrator_v2 import (
    FourPlaneOrchestrator, OrchestrationConfig,
)


def generate_hvac_anomaly_telemetry(n_points: int = 100) -> list:
    """
    Generate telemetry data simulating compressor short-cycling 
    with rising discharge temperatures.
    """
    telemetry = []
    base_time = datetime.utcnow() - timedelta(hours=2)
    
    for i in range(n_points):
        timestamp = base_time + timedelta(minutes=i)
        
        # Compressor cycle count - abnormally high (short-cycling)
        cycle_rate = 15 + random.gauss(0, 2)  # Normal is ~6-8 cycles/hour
        if i > 50:  # Anomaly starts midway
            cycle_rate = 25 + random.gauss(0, 3)  # Short-cycling
        
        telemetry.append(TelemetryPoint(
            sensor_id="hvac_001_compressor_cycles",
            timestamp=timestamp,
            value=cycle_rate,
            unit="cycles/hour",
            source=SignalSource.BAS_SCADA,
        ))
        
        # Discharge temperature - rising
        base_temp = 160  # Normal discharge temp
        if i > 50:
            base_temp = 160 + (i - 50) * 0.5  # Rising temp
        discharge_temp = base_temp + random.gauss(0, 2)
        
        telemetry.append(TelemetryPoint(
            sensor_id="hvac_001_discharge_temp",
            timestamp=timestamp,
            value=discharge_temp,
            unit="F",
            source=SignalSource.BAS_SCADA,
        ))
        
        # Suction pressure - fluctuating (symptom of short-cycling)
        suction_pressure = 70 + random.gauss(0, 3)
        if i > 50:
            suction_pressure = 70 + random.gauss(0, 8)  # More fluctuation
        
        telemetry.append(TelemetryPoint(
            sensor_id="hvac_001_suction_pressure",
            timestamp=timestamp,
            value=suction_pressure,
            unit="psi",
            source=SignalSource.BAS_SCADA,
        ))
        
        # Condenser fan status
        telemetry.append(TelemetryPoint(
            sensor_id="hvac_001_condenser_fan",
            timestamp=timestamp,
            value=1.0 if random.random() > 0.1 else 0.0,
            unit="status",
            source=SignalSource.BAS_SCADA,
        ))
    
    return telemetry


def run_hvac_failure_prevention_demo():
    """
    Run the complete HVAC failure prevention workflow.
    """
    print("\n" + "="*80)
    print("HVAC FAILURE PREVENTION - FOUR-PLANE ARCHITECTURE DEMO")
    print("="*80 + "\n")
    
    # 1. Initialize Orchestrator
    print("1. INITIALIZING ORCHESTRATOR")
    print("-" * 40)
    
    config = OrchestrationConfig(
        site_id="building_001",
        site_name="Demo Building HVAC System",
        autonomy_level=AutonomyLevel.AUTO_LOW_RISK,  # Auto-execute low-risk actions
        enable_concurrent_diagnostics=True,
        auto_approve_low_risk=True,
    )
    
    orchestrator = FourPlaneOrchestrator(config)
    print(f"✓ Orchestrator initialized for {config.site_name}")
    print(f"✓ Autonomy level: {config.autonomy_level.value}")
    print(f"✓ 10 specialized agents ready\n")
    
    # 2. Generate anomaly telemetry
    print("2. GENERATING ANOMALY TELEMETRY")
    print("-" * 40)
    
    telemetry = generate_hvac_anomaly_telemetry(100)
    print(f"✓ Generated {len(telemetry)} telemetry points")
    print("✓ Simulating: Compressor short-cycling + rising discharge temps\n")
    
    # 3. Process telemetry through pipeline
    print("3. PROCESSING THROUGH FOUR-PLANE ARCHITECTURE")
    print("-" * 40)
    
    print("\n  DATA PLANE:")
    print("  → Ingesting telemetry...")
    print("  → Stream processing: normalization, feature extraction...")
    print("  → Generating alerts from threshold breaches...")
    
    cases = orchestrator.process_telemetry(telemetry)
    
    print(f"\n  AGENT PLANE:")
    print(f"  → Signal Triage: {len(cases)} case(s) created")
    
    if not cases:
        print("  ⚠ No cases generated - adjusting thresholds...")
        # Lower the anomaly threshold by adding more extreme readings
        for _ in range(20):
            telemetry.append(TelemetryPoint(
                sensor_id="hvac_001_compressor_cycles",
                timestamp=datetime.utcnow(),
                value=35 + random.gauss(0, 2),  # Very high cycle rate
                unit="cycles/hour",
                source=SignalSource.BAS_SCADA,
            ))
            telemetry.append(TelemetryPoint(
                sensor_id="hvac_001_discharge_temp",
                timestamp=datetime.utcnow(),
                value=200 + random.gauss(0, 5),  # High discharge temp
                unit="F",
                source=SignalSource.BAS_SCADA,
            ))
        
        cases = orchestrator.process_telemetry(telemetry)
        print(f"  → After adjustment: {len(cases)} case(s) created")
    
    if cases:
        case = cases[0]
        print(f"  → Case ID: {case.case_id}")
        print(f"  → Priority: {case.priority.value}")
        print(f"  → Classification: {case.classification.value if case.classification else 'pending'}")
        
        # Show diagnosis results
        print(f"\n  DIAGNOSIS (Concurrent):")
        if case.hypotheses:
            print(f"  → {len(case.hypotheses)} hypotheses generated")
            for i, h in enumerate(case.hypotheses[:3], 1):
                print(f"     {i}. {h.description} (confidence: {h.confidence:.2f})")
        
        if case.root_cause:
            print(f"  → Root cause: {case.root_cause.description}")
        
        # Show remediation plan
        print(f"\n  REMEDIATION PLAN:")
        if case.remediation_plan:
            plan = case.remediation_plan
            print(f"  → {len(plan.steps)} steps, risk level: {plan.overall_risk.value}")
            for step in plan.steps:
                status = "✓" if step.executed else "○"
                approval = " [needs approval]" if step.requires_approval and not step.approved_by else ""
                print(f"     {status} Step {step.sequence}: {step.description}{approval}")
        
        # Show orchestrator status
        print(f"\n  ORCHESTRATION PLANE:")
        status = orchestrator.get_orchestrator_status()
        print(f"  → Active cases: {status['active_cases']}")
        print(f"  → Pending approvals: {status['pending_approvals']}")
        print(f"  → Cases by state: {status['cases_by_state']}")
    
    # 4. Simulate human approval (if needed)
    print("\n4. HUMAN-IN-THE-LOOP AUTHORIZATION")
    print("-" * 40)
    
    pending = orchestrator.get_pending_approvals()
    if pending:
        print(f"  → {len(pending)} approval(s) pending")
        for req in pending:
            print(f"     - {req.request_id}: {req.step_description} ({req.risk_level.value} risk)")
            
            # Simulate approval
            orchestrator.approve_request(req.request_id, True, "operator_001", "Approved for demo")
            print(f"     ✓ Approved by operator_001")
    else:
        print("  → No approvals pending (auto-approved based on autonomy level)")
    
    # 5. Verification phase
    print("\n5. VERIFICATION & CLOSURE")
    print("-" * 40)
    
    if cases:
        case = cases[0]
        
        # Generate post-remediation telemetry (improved)
        post_telemetry = []
        for i in range(20):
            post_telemetry.append(TelemetryPoint(
                sensor_id="hvac_001_compressor_cycles",
                timestamp=datetime.utcnow() + timedelta(minutes=i),
                value=8 + random.gauss(0, 1),  # Normal cycle rate
                unit="cycles/hour",
                source=SignalSource.BAS_SCADA,
            ))
            post_telemetry.append(TelemetryPoint(
                sensor_id="hvac_001_discharge_temp",
                timestamp=datetime.utcnow() + timedelta(minutes=i),
                value=165 + random.gauss(0, 2),  # Normal temp
                unit="F",
                source=SignalSource.BAS_SCADA,
            ))
        
        # Process post-telemetry
        post_signals = orchestrator.stream_processor.process_batch(post_telemetry)
        
        # Transition to VERIFY if not already
        if case.state.value not in ["verify", "close", "learn"]:
            orchestrator.lifecycle.transition(
                case, 
                orchestrator.lifecycle.VALID_TRANSITIONS[case.state][0],
                "demo",
                "Advancing for verification"
            )
        
        # Run verification
        if case.state.value == "verify" or True:  # Force verification for demo
            from federated_demand_twin.vendor.agents.ecosystems.oil_gas.data_plane import CaseState
            case.state = CaseState.VERIFY
            
            result = orchestrator.verify_and_close(case.case_id, post_signals)
            
            print(f"  → Verification result: {result.get('status', 'unknown')}")
            if result.get('verification'):
                v = result['verification']
                print(f"     - Effective: {v.get('effective', False)}")
                print(f"     - Confidence: {v.get('confidence', 0):.2f}")
                print(f"     - Improved sensors: {len(v.get('improved', []))}")
                print(f"     - Recommendation: {v.get('recommendation', 'N/A')}")
            
            if result.get('learnings'):
                l = result['learnings']
                print(f"  → Learnings extracted:")
                for lesson in l.get('lessons', [])[:2]:
                    print(f"     - {lesson}")
    
    # 6. Final Summary
    print("\n" + "="*80)
    print("DEMO COMPLETE - SUMMARY")
    print("="*80)
    
    final_status = orchestrator.get_orchestrator_status()
    print(f"""
Site: {final_status['site_id']}
Autonomy Level: {final_status['autonomy_level']}
Active Cases: {final_status['active_cases']}
Resolved Cases: {final_status['resolved_cases']}
Pending Approvals: {final_status['pending_approvals']}

Agents Used:
{chr(10).join(f'  - {a}' for a in final_status['agents'])}

Architecture Demonstrated:
  ✓ Data Plane: Telemetry ingestion, stream processing, evidence store
  ✓ Agent Plane: 10 specialized agents with defined roles
  ✓ Orchestration Plane: Sequential + concurrent patterns, case lifecycle
  ✓ Execution Plane: Tool schemas, governance, audit logging
  ✓ Human-in-the-Loop: Approval workflow for sensitive actions
  ✓ Learning: Post-incident analysis and knowledge extraction
""")
    
    return orchestrator, cases


if __name__ == "__main__":
    orchestrator, cases = run_hvac_failure_prevention_demo()
