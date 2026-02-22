# Agent Teams & Individual Agent Capabilities

**Prepared for:** Data Science Team Review  
**Date:** February 20, 2026  
**Version:** 1.0  

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Agent Infrastructure](#2-agent-infrastructure)
3. [Team 1 — Context Agents (Layer 0)](#3-team-1--context-agents-layer-0)
4. [Team 2 — Data Quality Agents (Layer 1)](#4-team-2--data-quality-agents-layer-1)
5. [Team 3 — Behavioral Analysis Agents (Layer 2)](#5-team-3--behavioral-analysis-agents-layer-2)
6. [Team 4 — Diagnostic Agents (Layer 3)](#6-team-4--diagnostic-agents-layer-3)
7. [Team 5 — Decision Agents (Layer 4)](#7-team-5--decision-agents-layer-4)
8. [Team 6 — Workflow Agents (Downstream)](#8-team-6--workflow-agents-downstream)
9. [Team 7 — Scenario Planning Agents](#9-team-7--scenario-planning-agents)
10. [Orchestration Layer](#10-orchestration-layer)
11. [Communication Protocols](#11-communication-protocols)
12. [Collaborative Decision Workflow](#12-collaborative-decision-workflow)
13. [Guardian Merge (Safety Layer)](#13-guardian-merge-safety-layer)
14. [Agent Dependency Map](#14-agent-dependency-map)
15. [Decision Rule Engine](#15-decision-rule-engine)

---

## 1. Architecture Overview

The system uses a **layered multi-agent architecture**. Agents are organized into 7 teams across 5 execution layers, communicating through structured protocols and making collaborative decisions via weighted voting.

```
┌─────────────────────────────────────────────────────────────────┐
│                    PDMModelOrchestrator                          │
│              (Coordinates all model agents)                      │
└──────────────────────────┬──────────────────────────────────────┘
                           │
     ┌─────────────────────┼─────────────────────┐
     │                     │                     │
     ▼                     ▼                     ▼
┌──────────┐         ┌──────────┐         ┌──────────┐
│ Layer 0  │         │ Layer 1  │         │ Layer 2  │
│ Context  │────────▶│  Trust   │────────▶│ Behavior │
└──────────┘         └──────────┘         └──────────┘
     │                     │                     │
     │ RegimeDetection     │ SensorTrust         │ BehaviorModel
     │   Agent             │   Agent             │ ChangeDetection
     │                     │                     │   Agent
     └─────────────────────┼─────────────────────┘
                           │
     ┌─────────────────────┼─────────────────────┐
     │                     │                     │
     ▼                     ▼                     ▼
┌──────────┐         ┌──────────┐         ┌──────────┐
│ Layer 3  │         │ Layer 4  │         │ Workflow │
│ Diagnosis│────────▶│ Decision │────────▶│  Agents  │
└──────────┘         └──────────┘         └──────────┘
     │                     │                     │
     │ FaultHypothesis     │ DecisionPolicy      │ CaseTriage
     │   Agent             │   Agent             │ EvidenceToAction
     │                     │                     │ WorkOrderComposer
     └─────────────────────┴─────────────────────┘
                           │
                           ▼
                  ┌─────────────────┐
                  │ GuardianMerge   │
                  │ (Safety Layer)  │
                  └─────────────────┘
```

**Execution model:** Each layer completes before the next begins. Results propagate downstream. All agents participate in a collaborative vote before final decisions are made.

---

## 2. Agent Infrastructure

### 2.1 Base Classes

All agents inherit from a shared infrastructure defined in `shared/agents/base.py`:

| Class | Purpose |
|-------|---------|
| `BaseAgent` | Agent-compliant base with LLM reasoning, belief state, tools, and action logging |
| `PDMModelAgent` | Extends `BaseCrewAgent` + `EventHandler` — adds analysis history, voting, upstream/downstream wiring, result broadcasting |
| `PdMAgent` | Lightweight event-driven base for workflow agents |
| `ScenarioAgent` | Base for scenario planning agents |

### 2.2 Agent Categories

| Category | Description | Example Roles |
|----------|-------------|---------------|
| `DATA` | Data quality, validation | Data Steward, Data Validator |
| `ANALYTICS` | Anomaly detection, diagnostics, forecasting | Forecaster, Anomaly Detector, Digital Twin |
| `SIMULATION` | Digital Twin, scenario generation | Scenario Generator, Monte Carlo |
| `OPTIMIZATION` | Resource allocation, scheduling | Budget Optimizer, Resource Allocator |
| `GOVERNANCE` | Policy validation, approval workflows | Policy Validator, Compliance Checker |
| `COMMUNICATION` | Rationale generation, reporting | Report Writer, Executive Summarizer |

### 2.3 Agent Configuration

Every agent is configured with:

| Field | Description |
|-------|-------------|
| `agent_id` | Unique identifier (format: `{role}_{site_id}`) |
| `role` | `AgentRole` enum value |
| `category` | `AgentCategory` enum value |
| `name` | Human-readable name |
| `goal` | Agent's objective (used for LLM reasoning) |
| `backstory` | Domain expertise narrative (used for LLM reasoning) |
| `llm_model` | LLM model (default: `gpt-4`) |
| `temperature` | LLM temperature (default: 0.7) |
| `confidence_threshold` | Minimum confidence to act (default: 0.7) |
| `allow_delegation` | Can delegate to other agents (default: true) |

### 2.4 Common Agent Capabilities

Every `PDMModelAgent` can:

| Capability | Method | Description |
|------------|--------|-------------|
| **Analyze** | `analyze(inputs)` | Perform primary analysis, return `AgentAnalysisResult` |
| **Vote** | `vote_on_decision(question, context)` | Cast weighted vote on collaborative decisions |
| **Broadcast** | `broadcast_result(result)` | Send results to downstream agents via message bus |
| **Receive** | `receive_upstream_result(result)` | Receive results from upstream agents |
| **Handle Events** | `handle(event)` | Process Redis/in-memory event bus events |
| **Track History** | `analysis_history` | Maintains up to 1,000 historical results |

### 2.5 Standard Output: `AgentAnalysisResult`

Every agent produces a standardized result:

```python
@dataclass
class AgentAnalysisResult:
    agent_id: str
    agent_role: PDMModelAgentRole
    timestamp: datetime
    result_type: str          # e.g., "regime_state", "sensor_trust", "fault_hypothesis"
    result_data: Dict         # Agent-specific payload
    confidence: float         # [0, 1]
    uncertainty: Dict         # Per-metric uncertainty
    depends_on: List[str]     # Upstream agent IDs
    recommendations: List[str]
    concerns: List[str]
```

### 2.6 Standard Vote: `AgentVote`

Every agent casts votes with:

```python
@dataclass
class AgentVote:
    agent_id: str
    agent_role: PDMModelAgentRole
    opinion: AgentOpinion      # STRONGLY_AGREE / AGREE / NEUTRAL / DISAGREE / STRONGLY_DISAGREE / ABSTAIN
    confidence: float          # [0, 1]
    rationale: str             # Natural language explanation
    evidence: List[Dict]       # Supporting evidence
    weight: float              # Voting weight (role-based + Thompson Sampling)
```

---

## 3. Team 1 — Context Agents (Layer 0)

### 3.1 RegimeDetectionAgent

| Property | Value |
|----------|-------|
| **ID** | `regime_detection_{site_id}` |
| **Role** | `DATA_STEWARD` |
| **Category** | `DATA` |
| **Name** | Regime Detection Specialist |
| **Backstory** | Expert in HVAC/R system dynamics who understands that equipment behaves fundamentally differently during startup, steady-state, defrost, and shutdown. Classifies regimes to prevent false alarms from comparing different operating modes. |
| **Service** | `RegimeSegmentationService` |
| **Handles Events** | `TELEMETRY_RECEIVED` |
| **Upstream** | None (first in pipeline) |
| **Downstream** | SensorTrustAgent, BehaviorModelAgent |

**Analysis capability:**
- Receives raw telemetry (compressor state, temperatures, pressures, fan status, valve positions)
- Classifies into one of 11 operating regimes via deterministic rules + optional HMM refinement
- Reports `regime`, `confidence`, `duration_seconds`, `is_steady_state`, `previous_regime`
- Raises concern `"System in transient regime - defer behavioral analysis"` when not in steady state

**Voting behavior (`should_alert` questions):**

| Condition | Opinion | Weight | Rationale |
|-----------|---------|--------|-----------|
| System NOT in steady state | **DISAGREE** | 1.5 | "System is in {regime} (transient). Defer alerting until steady-state." |
| System in steady state | **NEUTRAL** | 1.0 | "Regime analysis supports proceeding." |
| Out-of-domain question | **ABSTAIN** | 0.0 | — |

**Key design principle:** This agent has elevated voting weight (1.5) on alert questions during transient regimes because false positives from transient comparison are the single largest FP source.

---

## 4. Team 2 — Data Quality Agents (Layer 1)

### 4.1 SensorTrustAgent

| Property | Value |
|----------|-------|
| **ID** | `sensor_trust_{site_id}` |
| **Role** | `DATA_VALIDATOR` |
| **Category** | `DATA` |
| **Name** | Sensor Trust Evaluator |
| **Backstory** | Sensor calibration expert who has seen thousands of false alarms caused by drifting sensors, stuck readings, and communication glitches. Knows that the first question is not "What's wrong with the equipment?" but "Can I trust this data?" Saves countless unnecessary truck rolls by catching sensor issues first. |
| **Service** | `SensorTrustService` |
| **Handles Events** | `TELEMETRY_RECEIVED` |
| **Upstream** | RegimeDetectionAgent |
| **Downstream** | BehaviorModelAgent, DecisionPolicyAgent |

**Analysis capability:**
- Processes each sensor reading through 5-check trust evaluation (drift, stuck, comms, range, rate-of-change)
- Produces per-sensor trust scores and identifies untrusted sensors
- Reports `trust_scores`, `min_trust`, `untrusted_sensors`, `all_trusted`
- Generates specific concerns: "suction_pressure appears stuck (likelihood: 85%)", "ambient_temp may be drifting (likelihood: 40%)"

**Voting behavior (`should_alert` / `should_dispatch` questions):**

| Condition | Opinion | Weight | Rationale |
|-----------|---------|--------|-----------|
| `min_trust < 0.5` | **STRONGLY_DISAGREE** | **2.0** | "Sensor trust too low. Likely sensor issue, not equipment fault." |
| `min_trust < 0.8` | **DISAGREE** | 1.5 | "Sensor trust marginal. Recommend sensor verification before dispatch." |
| `min_trust ≥ 0.8` | **NEUTRAL** | 1.0 | "All sensors trusted. Sensor data supports analysis." |

**Key design principle:** This agent has the **highest voting weight in the system (2.0)** when sensor trust is low. It functions as a hard veto — if sensors can't be trusted, no equipment fault alarm should fire regardless of what other agents think.

---

## 5. Team 3 — Behavioral Analysis Agents (Layer 2)

### 5.1 BehaviorModelAgent

| Property | Value |
|----------|-------|
| **ID** | `behavior_model_{site_id}` |
| **Role** | `FORECASTER` |
| **Category** | `ANALYTICS` |
| **Name** | Behavioral Prediction Specialist |
| **Backstory** | HVAC/R performance modeling expert who understands the physics of refrigeration cycles and air handling. Knows that expected behavior varies with ambient temperature, load, and operating regime. Builds accurate predictions that serve as the baseline for detecting true deviations. |
| **Services** | `BehaviorModelService`, `EquipmentFingerprintService` |
| **Handles Events** | `TELEMETRY_RECEIVED` |
| **Upstream** | RegimeDetectionAgent, SensorTrustAgent |
| **Downstream** | ChangeDetectionAgent |

**Analysis capability:**
- Uses hierarchical model (global fleet + per-unit fingerprint) to predict expected sensor values
- Computes residuals and z-scores per sensor under current regime and load
- Reports `predictions`, `residuals`, `significant_deviations` (z > 2.0), `fingerprint_confidence`
- Continuously updates behavior model and fingerprint with each observation

**Voting behavior (`should_alert` questions):**

| Condition | Opinion | Weight | Rationale |
|-----------|---------|--------|-----------|
| ≥2 significant deviations | **AGREE** | 1.2 | "Multiple behavioral deviations detected. Equipment not behaving as expected." |
| 1 significant deviation | **NEUTRAL** | 0.8 | "Single deviation. May need more evidence." |
| No deviations | **DISAGREE** | 1.0 | "Behavior within expected range. No significant deviations." |

---

### 5.2 ChangeDetectionAgent

| Property | Value |
|----------|-------|
| **ID** | `change_detection_{site_id}` |
| **Role** | `ANOMALY_DETECTOR` |
| **Category** | `ANALYTICS` |
| **Name** | Sequential Change Detection Specialist |
| **Backstory** | Signal processing expert trained in radar detection theory. Knows that a single spike is not an alarm — what matters is persistent deviation. Uses CUSUM and GLR to detect when a system is "no longer behaving like itself" rather than flagging every unusual reading. |
| **Service** | `SequentialChangeDetectionService` |
| **Handles Events** | `ANALYSIS_COMPLETE` |
| **Upstream** | BehaviorModelAgent |
| **Downstream** | FaultHypothesisAgent, DecisionPolicyAgent |

**Analysis capability:**
- Runs three parallel detectors (CUSUM, GLR, Bayesian OCPD) on each sensor's residual stream
- Enforces persistence (≥30 min), multi-regime observation (≥2 steady-state segments), and stability (≥0.7)
- Reports `change_results` per sensor (score, duration, regimes, stability), `changes_detected`, `max_persistence_hours`
- Joint cross-sensor detection for correlated changes

**Voting behavior (`should_alert` questions):**

| Condition | Opinion | Weight | Rationale |
|-----------|---------|--------|-----------|
| Changes detected AND persistence ≥6h | **STRONGLY_AGREE** | 1.5 | "Persistent change detected for X hours. This is not transient noise." |
| Changes detected, low persistence | **NEUTRAL** | 1.0 | "Change detected but persistence only X hours. Need more observation." |
| No changes detected | **DISAGREE** | 1.3 | "No persistent changes detected. Point anomalies do not warrant alerting." |

**Key design principle:** This agent has elevated disagree weight (1.3) because the absence of persistent change is strong evidence against alerting — point anomalies should not trigger maintenance actions.

---

## 6. Team 4 — Diagnostic Agents (Layer 3)

### 6.1 FaultHypothesisAgent

| Property | Value |
|----------|-------|
| **ID** | `fault_hypothesis_{site_id}` |
| **Role** | `DIGITAL_TWIN` |
| **Category** | `ANALYTICS` |
| **Name** | Bayesian Fault Diagnosis Specialist |
| **Backstory** | Diagnostic reasoning expert who understands that forcing a single fault label is often wrong. Instead, maintains probability distributions over fault hypotheses, gathering evidence until confidence is high enough for action. Knows that "I don't know yet" is a valid answer that prevents false diagnoses. |
| **Service** | `FaultHypothesisService` |
| **Handles Events** | `ANALYSIS_COMPLETE` |
| **Upstream** | ChangeDetectionAgent |
| **Downstream** | DecisionPolicyAgent |

**Analysis capability:**
- Extracts symptoms from residuals, change detections, and raw telemetry
- Performs Bayesian evidence fusion with fault-specific likelihood ratios
- Maintains full posterior over 12 fault types
- Reports `belief_distribution`, `top_fault`, `top_probability`, `is_concentrated`, `is_confident`, `recommended_action`, `n_evidence`

**Voting behavior (`should_alert` questions):**

| Condition | Opinion | Weight | Rationale |
|-----------|---------|--------|-----------|
| Confident + concentrated + top prob >60% | **AGREE** | 1.3 | "Diagnosis confident: {fault} ({prob}%). Evidence supports actionable alert." |
| Top fault >40% but not confident | **NEUTRAL** | 1.0 | "Leading hypothesis: {fault} ({prob}%). Need more evidence." |
| No confident diagnosis | **DISAGREE** | 1.2 | "No confident diagnosis. Probability mass spread across multiple hypotheses." |

**Key design principle:** Disagree weight (1.2) is elevated because unconfident diagnoses should block actionable alerts. The agent explicitly endorses "I don't know yet" as a valid signal.

---

## 7. Team 5 — Decision Agents (Layer 4)

### 7.1 DecisionPolicyAgent

| Property | Value |
|----------|-------|
| **ID** | `decision_policy_{site_id}` |
| **Role** | `POLICY_VALIDATOR` |
| **Category** | `GOVERNANCE` |
| **Name** | Decision Policy Enforcer |
| **Backstory** | Final arbiter of maintenance decisions, responsible for balancing detection sensitivity against alarm fatigue. Aggregates opinions from specialist agents, applies operational constraints (max alarms per month), and makes decisions that optimize technician efficiency and customer satisfaction. |
| **Service** | `DecisionPolicyService` |
| **Handles Events** | `ANALYSIS_COMPLETE` |
| **Upstream** | SensorTrustAgent, ChangeDetectionAgent, FaultHypothesisAgent |
| **Downstream** | None (terminal model agent) |

**Analysis capability:**
- Does not perform independent analysis — orchestrates collaborative decisions
- Applies false-positive budget constraints (max 0.3 actionable alarms/unit/month, max 5% NIF rate)
- Runs six sequential hard gates (sensor trust, steady state, change present, persistence, diagnosis confidence, budget)

**Unique capability — `make_collaborative_decision()`:**

This is the **key multi-agent collaboration method**. It:

1. Collects votes from all model agents on the question "Should we alert?"
2. Computes weighted consensus score using opinion × weight × confidence
3. Maps opinions to numeric scores: STRONGLY_AGREE=+2, AGREE=+1, NEUTRAL=0, DISAGREE=−1, STRONGLY_DISAGREE=−2
4. Determines final decision:
   - `weighted_score ≥ threshold` → **"proceed"** (consensus to alert)
   - `weighted_score ≤ -threshold` → **"defer"** (consensus to not alert)
   - Otherwise → **"uncertain"** (no consensus)
5. Identifies dissenting agents
6. Returns `CollaborativeDecision` with all votes, consensus status, aggregate confidence

**Voting behavior (`should_alert` questions):**

| Condition | Opinion | Weight | Rationale |
|-----------|---------|--------|-----------|
| FA probability exceeds budget | **DISAGREE** | 1.5 | "FA probability ({x}%) exceeds budget ({y}%)." |
| Confidence below actionable threshold | **DISAGREE** | 1.2 | "Confidence ({x}%) below threshold ({y}%)." |
| Budget constraints satisfied | **NEUTRAL** | 0.8 | "Budget constraints satisfied. Deferring to specialist agents." |

**Key design principle:** This agent deliberately uses weight 0.8 (below 1.0) when budget constraints are satisfied, deferring to specialist agents for the actual diagnostic judgment. It only asserts itself strongly to enforce budget violations.

---

## 8. Team 6 — Workflow Agents (Downstream)

These agents operate downstream of the decision layer, handling case processing after an alert decision is made. They communicate via the Redis/in-memory event bus.

### 8.1 CaseTriageAgent

| Property | Value |
|----------|-------|
| **ID** | Custom |
| **Base Class** | `PdMAgent` (EventHandler) |
| **Handles Events** | `CASE_CREATED` |

**Capability:**
- Receives newly created cases from the alert pipeline
- Triages into `dispatch` (severity = high) or `triage` (all other severities) buckets
- Emits `CASE_TRIAGED` event with `triage_decision`, `rationale`, and `priority_score`
- Priority scores: dispatch = 0.8, triage = 0.5

---

### 8.2 EvidenceToActionAgent

| Property | Value |
|----------|-------|
| **ID** | Custom |
| **Base Class** | `PdMAgent` (EventHandler) |
| **Handles Events** | `CASE_TRIAGED` |

**Capability:**
- Receives triaged cases
- Builds a maintenance evidence packet containing:
  - Problem statement
  - Evidence items (sensor data, change detection results, fault hypothesis)
  - Likely root causes
  - Recommended actions
  - Safety notes
- Emits `MAINTENANCE_PACKET_CREATED` event

---

### 8.3 WorkOrderComposerAgent

| Property | Value |
|----------|-------|
| **ID** | Custom |
| **Base Class** | `PdMAgent` (EventHandler) |
| **Handles Events** | `CASE_TRIAGED` |

**Capability:**
- Receives triaged cases, acts only on `dispatch` decisions
- Drafts a work order with title, description, priority, estimated parts, and estimated duration
- Emits `WORK_ORDER_DRAFTED` event
- Default estimated duration: 2 hours

---

## 9. Team 7 — Scenario Planning Agents

These agents evaluate maintenance scenarios from different stakeholder perspectives, enabling multi-lens analysis for planning decisions.

### 9.1 BudgetScenarioAgent

| Property | Value |
|----------|-------|
| **Base Class** | `ScenarioAgent` |
| **Perspective** | CapEx/OpEx cost analysis |

**Capability:**
- Analyzes scenarios from a financial lens
- Inputs: scope (asset/site/fleet), risk level, maintenance budget, health score, RUL
- Provides budget impact assessment and cost-benefit framing

### 9.2 RiskScenarioAgent

| Property | Value |
|----------|-------|
| **Base Class** | `ScenarioAgent` |
| **Perspective** | Failure probability and safety risk |

**Capability:**
- Analyzes scenarios from a risk and safety lens
- Inputs: scope, risk level, persona, fault probability, degradation index
- Provides risk-based prioritization and safety impact assessment

### 9.3 PaybackScenarioAgent

| Property | Value |
|----------|-------|
| **Base Class** | `ScenarioAgent` |
| **Perspective** | ROI and payback period analysis |

**Capability:**
- Analyzes scenarios from an investment return lens
- Inputs: scope, payback timeline, persona, energy penalty, estimated downtime cost
- Provides ROI projections and payback period estimates

**All scenario agents receive a `ScenarioContext`** containing persona ID, user message, scope, risk level, payback timeline, maintenance budget, and digital twin state.

---

## 10. Orchestration Layer

### 10.1 PDMModelOrchestrator

**File:** `agents/orchestrator.py`

The orchestrator is the **central coordinator** for the entire multi-agent system. It manages agent lifecycle, layered execution, result propagation, collaborative decisions, and constraint enforcement.

**Configuration (`OrchestratorConfig`):**

| Parameter | Default | Description |
|-----------|---------|-------------|
| `consensus_threshold` | 0.6 | Weighted score needed for consensus |
| `min_votes_for_decision` | 3 | Minimum votes required |
| `layer_timeout_seconds` | 30.0 | Per-layer execution timeout |
| `total_timeout_seconds` | 120.0 | Total pipeline timeout |
| `alert_confidence_threshold` | 0.7 | Min confidence for action alert |
| `dispatch_confidence_threshold` | 0.85 | Min confidence for dispatch |
| `max_alerts_per_day` | 10 | Daily alert cap |
| `max_dispatches_per_week` | 3 | Weekly dispatch cap |

**Role-based weight multipliers:**

| Agent Role | Weight | Rationale |
|------------|--------|-----------|
| Sensor Trust | **2.0** | Critical for preventing false alarms |
| Change Detection | 1.5 | Persistence is key evidence |
| Decision Policy | 1.5 | Budget enforcement authority |
| Fault Hypothesis | 1.3 | Diagnosis expertise |
| Regime Detection | 1.2 | Context is foundational |
| Behavior Model | 1.0 | Standard baseline weight |

**`process_telemetry()` execution flow:**

1. **Deterministic kernel first** — `HVACRPdMAdvancedSystem.process_telemetry_with_artifact()` runs the full detection/diagnosis pipeline deterministically. This is the source of truth.
2. **Layer 0** — RegimeDetectionAgent classifies regime, injects into inputs
3. **Layer 1** — SensorTrustAgent evaluates trust, injects min_trust and untrusted sensor list
4. **Layer 2** — BehaviorModelAgent predicts + computes residuals → ChangeDetectionAgent runs CUSUM/GLR
5. **Layer 3** — FaultHypothesisAgent updates Bayesian belief with evidence from changes
6. **Layer 4** — DecisionPolicyAgent orchestrates collaborative vote among all 6 agents
7. **Alert determination** — Maps consensus to alert type (dispatch/action/watch/none)
8. **Operational constraints** — Enforces daily alert and weekly dispatch caps
9. **Advisory construction** — Converts agent votes into `AgentAdvisory` objects
10. **Guardian merge** — `GuardianMergeService` merges kernel artifact with advisories under monotonic safety

**Advisory construction logic:**
- If collaborative decision ≠ "proceed" → generates `DOWNGRADE_TO_WATCH` advisory
- If no consensus → generates `ESCALATE_TO_HUMAN` advisory
- If SensorTrustAgent voted DISAGREE/STRONGLY_DISAGREE → generates `SUPPRESS_FOR_DATA_QUALITY` advisory
- If any agent voted STRONGLY_DISAGREE with ≥80% confidence → generates `ESCALATE_TO_HUMAN` advisory
- If alert type is "dispatch" → always generates `ESCALATE_TO_HUMAN` advisory (dispatch guard)

### 10.2 PDMDecisionCrew )

**File:** `agents/orchestrator.py`

Wraps the `PDMModelOrchestrator` in a `Crew` for advanced multi-agent collaboration. Uses `Process.hierarchical` mode, falls back to basic orchestrator otherwise.

---

## 11. Communication Protocols

**File:** `agents/protocols.py`

### 11.1 Protocol Message Types

| Type | Description |
|------|-------------|
| `ANALYSIS_RESULT` / `RESULT_ACK` | Agent broadcasts analysis results; recipients acknowledge |
| `QUERY` / `RESPONSE` / `QUERY_TIMEOUT` | Agent requests specific information from another agent |
| `VOTE_REQUEST` / `VOTE` / `VOTE_RESULT` | Structured voting for collaborative decisions |
| `ESCALATION` / `ESCALATION_ACK` | Agent escalates concern to higher-level agent |
| `FEEDBACK` / `FEEDBACK_ACK` | Decision outcome feedback for model improvement |
| `HEARTBEAT` | Agent liveness check |
| `SYNC_REQUEST` / `SYNC_RESPONSE` | State synchronization between agents |

### 11.2 Message Priority

| Priority | Order | Usage |
|----------|-------|-------|
| `CRITICAL` | 0 (highest) | Safety-critical escalations |
| `HIGH` | 1 | Vote requests, critical escalations |
| `NORMAL` | 2 | Analysis results, standard communication |
| `LOW` | 3 | Acknowledgments, heartbeats |

### 11.3 ProtocolMessageBus

Central message bus with:
- **Priority-based queuing** — messages sorted by priority
- **Directed and broadcast routing** — messages can target specific agents or broadcast to all
- **Handler registration** — agents register protocol handlers per message type
- **Dead letter handling** — undeliverable and expired messages tracked
- **Subscriber callbacks** — additional notification mechanism beyond handlers

### 11.4 VotingProtocol

Structured voting protocol flow:

1. **Initiator** broadcasts `VOTE_REQUEST` to all voting agents (with deadline)
2. Each agent responds with `VOTE` message (choice, confidence, weight, rationale, evidence)
3. Initiator tallies votes: `weighted_score = Σ(choice × weight × confidence)`
4. Consensus reached if `winning_weight / total_weight > 0.6`
5. Initiator broadcasts `VOTE_RESULT` to all participants

### 11.5 EscalationProtocol

Agents escalate concerns with:
- `concern_type` — what kind of issue
- `severity` — critical/high/medium/low (critical gets HIGH message priority)
- `description` — natural language explanation
- `evidence` — supporting data
- `recommended_action` — what should be done

**Use cases:** Sensor trust agent flags unreliable data, change detection flags persistent anomaly, fault hypothesis flags confident diagnosis.

### 11.6 ConsensusProtocol (Multi-Round)

For critical decisions requiring higher agreement:

1. Proposer submits initial proposal
2. Agents vote with rationale (agree/disagree + explanation)
3. If consensus threshold (default 0.8) not met → refine proposal based on rationales
4. Repeat until consensus or max rounds (default 3)
5. Reports agreement rate per round

### 11.7 ProtocolEnabledAgent (Mixin)

Adds full protocol capabilities to any PDM agent:
- `broadcast_analysis_result()` — broadcast results to downstream
- `participate_in_vote()` — cast votes in voting rounds
- `escalate_concern()` — raise issues to other agents
- Auto-registers `ResultBroadcastHandler` for receiving upstream results

---

## 12. Collaborative Decision Workflow

**File:** `agents/workflow.py`

### 12.1 Workflow States

```
INITIALIZED → CONTEXT_BUILDING → LAYER_0_REGIME → LAYER_1_TRUST
    → LAYER_2_BEHAVIOR → LAYER_3_DIAGNOSIS → LAYER_4_VOTING
    → CONSENSUS_BUILDING → DECISION_FINALIZED → ACTION_TAKEN → COMPLETED
                                                              (or FAILED)
```

### 12.2 Decision Types

| Type | Description |
|------|-------------|
| `NO_ACTION` | System operating normally |
| `CONTINUE_MONITORING` | Change detected but not yet confident |
| `WATCH_ALERT` | Emerging issue, generate watch alert |
| `ACTION_ALERT` | Likely fault, generate actionable alert |
| `DISPATCH_REQUIRED` | Confirmed fault, dispatch technician |
| `EMERGENCY_DISPATCH` | Critical confirmed fault, immediate dispatch |

### 12.3 `CollaborativeDecisionWorkflow`

Main entry point for the multi-agent system. The `process(telemetry)` method runs:

1. **Context building** — Logs telemetry metadata
2. **Layered analysis** — Executes Layer 0 → 1 → 2 → 3 sequentially, injecting each layer's results into the next
3. **Collaborative voting** — All 6 agents vote on "Should we generate a maintenance alert for this asset?"
4. **Decision finalization** — Rule engine evaluates context against prioritized decision rules
5. **Action** — Triggers appropriate callbacks for alerts/dispatches
6. **Audit** — Complete event trail logged, agent summary indexed into RAG store

### 12.4 Feedback Loop

`record_feedback(workflow_id, actual_outcome, was_correct)`:
- Records technician feedback on decision correctness
- Feeds into `RetrainingTriggerService` which may fire a model retraining request
- Updates Thompson Sampling agent weights via `AdaptiveAgentWeightService`
- Logged in workflow audit trail

---

## 13. Guardian Merge (Safety Layer)

**File:** `services/guardian_merge_service.py`

The Guardian enforces **monotonic safety** between the deterministic kernel and the agent advisory layer.

**Rule:** Agents can **tighten** decisions (downgrade, suppress, escalate) but **cannot relax** hard gates from the kernel.

| Advisory Action | Confidence Threshold | Effect |
|----------------|---------------------|--------|
| `SUPPRESS_FOR_DATA_QUALITY` | ≥ 0.70 | Downgrade to SENSOR_INTEGRITY or WATCH |
| `DOWNGRADE_TO_WATCH` | ≥ 0.70 | Reduce alert severity |
| `ESCALATE_TO_HUMAN` | ≥ 0.75 | Route to human review |
| `ENRICH` | ≥ 0.60 | Add context/evidence without changing decision |

**Failed gates always win:** If any kernel hard gate failed → force `AUTO_MONITOR` regardless of agent recommendations.

---

## 14. Agent Dependency Map

```
RegimeDetectionAgent ──────────────┐
  (Layer 0)                        │
  ├──▶ SensorTrustAgent            │
  │      (Layer 1)                 │
  │      ├──▶ BehaviorModelAgent   │
  │      │      (Layer 2)          │
  │      │      └──▶ ChangeDetectionAgent
  │      │             (Layer 2)   │
  │      │             ├──▶ FaultHypothesisAgent
  │      │             │     (Layer 3)
  │      │             │     └──▶ DecisionPolicyAgent
  │      │             │           (Layer 4)
  │      │             └──▶ DecisionPolicyAgent
  │      └──▶ DecisionPolicyAgent
  └──▶ BehaviorModelAgent
```

**Data flow summary:**
- Regime → injects `regime`, `is_steady_state` into all downstream inputs
- Sensor Trust → injects `sensor_trust`, `untrusted_sensors`
- Behavior Model → injects `residuals` per sensor
- Change Detection → injects `change_results`, `changes_detected`
- Fault Hypothesis → injects `belief_distribution`, `top_fault`, `is_confident`
- Decision Policy → produces final alert decision from collaborative vote

---

## 15. Decision Rule Engine

**File:** `agents/workflow.py`

Priority-ordered rules evaluated against workflow context. First matching rule determines the decision.

| Priority | Rule | Requirements | Decision |
|----------|------|-------------|----------|
| 1 | **Emergency Dispatch** | Trust ≥0.8, steady state, change detected, fault prob ≥0.9, consensus ≥0.85, ChangeDetection + FaultHypothesis agree | `EMERGENCY_DISPATCH` |
| 2 | **Dispatch Required** | Trust ≥0.7, steady state, change detected, fault prob ≥0.7, consensus ≥0.7 | `DISPATCH_REQUIRED` |
| 3 | **Action Alert** | Trust ≥0.6, steady state, change detected, fault prob ≥0.5, consensus ≥0.6 | `ACTION_ALERT` |
| 4 | **Watch Alert** | Trust ≥0.5, change detected, consensus ≥0.5 | `WATCH_ALERT` |
| 5 | **Continue Monitoring** | Trust ≥0.4, change detected | `CONTINUE_MONITORING` |
| 100 | **No Action** | (default fallback) | `NO_ACTION` |

**Key observations:**
- Emergency dispatch is the only rule requiring **explicit agreement from specific agent roles** (ChangeDetection + FaultHypothesis must both agree)
- All rules above "No Action" require change detection — point anomalies alone never trigger any alert
- Steady state is required for dispatch/action alerts but NOT for watch alerts
- Higher-priority rules require progressively stricter thresholds across all dimensions
