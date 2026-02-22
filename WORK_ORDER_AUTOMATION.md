# Work Order Automation Process

**Prepared for:** Data Science Team Review  
**Date:** February 20, 2026  
**Version:** 1.0  

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Work Order Lifecycle](#2-work-order-lifecycle)
3. [Trigger Pathways](#3-trigger-pathways)
4. [LLM-Powered AI Service (7 Integration Points)](#4-llm-powered-ai-service-7-integration-points)
5. [Autonomous WO Creation from PdM Signals](#5-autonomous-wo-creation-from-pdm-signals)
6. [Natural Language Work Order Interpretation](#6-natural-language-work-order-interpretation)
7. [AI Prioritization & Impact Assessment](#7-ai-prioritization--impact-assessment)
8. [Intelligent Provider Matching & Dispatch](#8-intelligent-provider-matching--dispatch)
9. [Cost & Approval Recommendation](#9-cost--approval-recommendation)
10. [Post-Service Verification](#10-post-service-verification)
11. [Predictive Forecast & Narrative](#11-predictive-forecast--narrative)
12. [Workflow Agents (Case Triage Pipeline)](#12-workflow-agents-case-triage-pipeline)
13. [Execution Engine (Closed-Loop CMMS)](#13-execution-engine-closed-loop-cmms)
14. [Autopilot Orchestration Runtime](#14-autopilot-orchestration-runtime)
15. [Playbook System](#15-playbook-system)
16. [Approval Workflow (Human-in-the-Loop)](#16-approval-workflow-human-in-the-loop)
17. [CMMS Connectors](#17-cmms-connectors)
18. [Recommendation Tracking & Outcome M&V](#18-recommendation-tracking--outcome-mv)
19. [A/B Testing Framework](#19-ab-testing-framework)
20. [API Endpoints](#20-api-endpoints)
21. [End-to-End Flow Diagrams](#21-end-to-end-flow-diagrams)

---

## 1. System Overview

The work order automation system transforms predictive maintenance insights into actionable maintenance operations through a multi-layered AI pipeline. The system spans three major subsystems:

- **AI Work Order Service** (`predictive_maintenance/services/workorder/`) — LLM-powered generative AI across 7 integration points: NL interpretation, autonomous creation, prioritization, provider matching, cost recommendation, post-service verification, and forecasting
- **Workflow Agents** (`predictive_maintenance/agents/workflow_agents.py`) — Event-driven case triage, evidence packaging, and work order composition agents
- **Execution Engine** (`loweconex_platform/execution/execution_engine.py`) — Closed-loop CMMS writeback, control actions with safety policies, and recommendation tracking
- **Autopilot Runtime** (`predictive_maintenance/autopilot/`) — Playbook-driven orchestration with durable checkpointing, approval gates, and BMS/CMMS connector integration

Every AI decision includes **deterministic fallback heuristics** that activate when the LLM is unavailable, ensuring the system always produces reasonable outputs.

```
┌─────────────────────────────────────────────────────────────────────┐
│                      TRIGGER SOURCES                                 │
│  PdM Sensor Signals │ Natural Language │ Orchestrator Alerts         │
│  Autopilot Playbook │ Manual Request   │ Scheduled Inspection        │
└──────┬──────────────┴──────┬───────────┴──────┬─────────────────────┘
       │                     │                  │
       ▼                     ▼                  ▼
┌──────────────────────────────────────────────────────────────────────┐
│              WorkOrderLLMService (7 Integration Points)              │
│  interpret │ auto_create │ prioritize │ match │ cost │ verify │ fcst │
│                    ↕ LLM ↔ Fallback Heuristics                      │
└──────────────────────────┬───────────────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────────────┐
│               Workflow Agents (Event-Driven Pipeline)                │
│  CaseTriageAgent → EvidenceToActionAgent → WorkOrderComposerAgent   │
└──────────────────────────┬───────────────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────────────┐
│                    Execution Engine                                   │
│  RecommendationTracker → Approval Gate → CMMSConnector → Close-out  │
│  ControlActionLog (audit) │ Safety Policies │ Rollback support       │
└──────────────────────────┬───────────────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────────────┐
│                   External CMMS/ITSM                                 │
│  Maximo │ ServiceNow │ eMaint │ Fiix │ (pluggable via connector)    │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 2. Work Order Lifecycle

### 2.1 Status Flow (AI Service Model)

```
DRAFT → OPEN → ASSIGNED → IN_PROGRESS → PENDING_APPROVAL → COMPLETED → VERIFIED
                                                                    ↓
                                                                 REOPENED
```

| Status | Description |
|--------|-------------|
| `draft` | AI-generated, awaiting human review |
| `open` | Confirmed, ready for assignment |
| `assigned` | Provider selected and assigned |
| `in_progress` | Technician actively working |
| `pending_approval` | Awaiting cost/scope approval |
| `completed` | Service performed |
| `verified` | Post-service metrics confirm fix effectiveness |
| `reopened` | Verification failed, requires follow-up |

### 2.2 Status Flow (Execution Engine Model)

```
DRAFT → SUBMITTED → APPROVED → IN_PROGRESS → COMPLETED → VERIFIED
                                                    ↓
                                                CANCELLED
```

### 2.3 Priority Levels

| Priority | SLA (hours) | Criteria |
|----------|------------|----------|
| `emergency` | Immediate | Life safety, active fire, gas leak |
| `critical` | 4 | Complete system failure, food safety risk, active refrigerant leak |
| `high` | 24 | Significant performance degradation, SLA at risk, persistent anomaly >4h |
| `medium` | 72 | Moderate drift, scheduled maintenance overdue, intermittent issues |
| `low` | 168 | Cosmetic, informational, planned inspection |
| `planned` | Scheduled | Preventive maintenance, periodic inspection |

### 2.4 Work Order Sources

| Source | Description |
|--------|-------------|
| `manual` | Human-created via UI or voice |
| `ai_nlp` | Created from natural-language interpretation |
| `ai_sensor` | Autonomously created from PdM sensor signals |
| `pdm_alert` | Created from PdM alert escalation |

---

## 3. Trigger Pathways

Work orders enter the system through four distinct pathways:

### Pathway 1: Autonomous PdM Signal → WO
```
Streaming telemetry → PdM Kernel → Agent Analysis → Orchestrator Alert
→ WorkOrderLLMService.auto_create() → ExecutionEngine.cmms.submit_work_order()
```

### Pathway 2: Natural Language → WO
```
User text/voice input → WorkOrderLLMService.interpret()
→ Structured WO draft → Human review → Submit to CMMS
```

### Pathway 3: Orchestrator → Workflow Agents → WO
```
Telemetry → PDMModelOrchestrator.process_telemetry() → should_alert=True
→ IntegratedPDMOrchestrator.process_with_workflow()
→ CaseTriageAgent → EvidenceToActionAgent → WorkOrderComposerAgent
→ Work order drafted event
```

### Pathway 4: Autopilot Playbook → WO
```
Incident detected → PlaybookRegistry selects playbook
→ OrchestrationRuntime.execute_run() → StepExecutor._execute_create_ticket()
→ CMMS connector creates ticket
```

---

## 4. LLM-Powered AI Service (7 Integration Points)

**File:** `predictive_maintenance/services/workorder/llm_service.py`

### 4.1 WorkOrderLLMService

Singleton service (`get_wo_llm_service()`) providing generative AI capabilities. Uses OpenAI GPT-4 via the platform's `OpenAIClient` with:

- **Temperature:** 0.3 (low for structured JSON output)
- **Max tokens:** 2,048
- **Max retries:** 2 with exponential backoff (2s, 4s)
- **Timeout:** 30 seconds per call
- **JSON extraction:** Strips markdown fences, regex fallback for embedded JSON

### 4.2 Fallback Architecture

Every LLM-powered function has a paired deterministic fallback:

| Function | LLM Method | Fallback Method |
|----------|-----------|-----------------|
| NL Interpretation | `interpret()` | `_interpret_fallback()` — keyword extraction + regex |
| Autonomous Creation | `auto_create()` | `_auto_create_fallback()` — threshold rules |
| Prioritization | `prioritize()` | `_prioritize_fallback()` — score map + keyword boost |
| Provider Matching | `match_providers()` | `_match_fallback()` — weighted scoring formula |
| Cost Recommendation | `recommend_cost()` | `_cost_fallback()` — historical ratio comparison |
| Verification | `verify()` | `_verify_fallback()` — metric comparison with directionality |
| Forecast | `forecast()` | `_forecast_narrative_fallback()` — statistical model |

### 4.3 System Prompt

All LLM calls share a base system prompt:

> "You are an AI assistant for a predictive maintenance (PdM) platform managing HVAC/R equipment across commercial facilities. You generate structured JSON outputs for work order management. Always respond with valid JSON only — no markdown fences, no explanation text outside the JSON object."

---

## 5. Autonomous WO Creation from PdM Signals

**Method:** `WorkOrderLLMService.auto_create()`  
**Endpoint:** `POST /api/v1/workorders/auto-create`

### 5.1 Input: SensorSignal

Each signal from the PdM model agents contains:

| Field | Type | Description |
|-------|------|-------------|
| `asset_id` | str | Equipment identifier |
| `sensor_type` | str | Type of sensor (temp, pressure, vibration, etc.) |
| `anomaly_type` | str | Classification of anomaly detected |
| `change_score` | float (0–1) | Change detection score from ChangeDetectionAgent |
| `persistence_hours` | float | Duration the anomaly has persisted |
| `regime` | str | Operating regime (startup, steady_state, shutdown, unknown) |
| `fault_hypothesis` | str | Fault class from FaultHypothesisAgent |
| `fault_probability` | float (0–1) | Probability of the hypothesized fault |
| `sensor_trust` | float (0–1) | Sensor trust score from SensorTrustAgent |
| `telemetry_snapshot` | Dict[str, float] | Current sensor readings |

### 5.2 Decision Criteria

The LLM (and fallback) applies these rules:

| Condition | Decision |
|-----------|----------|
| `change_score > 0.6` AND `persistence_hours > 4` AND `sensor_trust > 0.7` | **Create WO** |
| `fault_probability > 0.8` OR safety-related fault hypothesis | **Elevate to CRITICAL** |
| `persistence_hours < 2` (transient) | **Do NOT create** |
| `sensor_trust < 0.5` (unreliable) | **Do NOT create** |
| Regime = STARTUP | Consider anomaly may be transient |

### 5.3 Output: AutoCreateWOResponse

| Field | Type | Description |
|-------|------|-------------|
| `should_create` | bool | Whether signals warrant WO creation |
| `title` | str | Descriptive title based on diagnosis |
| `description` | str | Detailed description with diagnostic context |
| `asset_id` | str | Target equipment |
| `priority` | enum | critical / high / medium / low |
| `problem_type` | str | Classified problem type |
| `diagnostic_context` | str | Technical summary of model detections |
| `recommended_tags` | List[str] | Classification tags |
| `confidence` | float (0–1) | Decision confidence |
| `rationale` | str | Explanation of why WO should/should not be created |

### 5.4 CMMS Bridge

When `should_create=True`, the API route automatically submits to the ExecutionEngine:

```python
wo = WorkOrderRequest(
    title=result.title,
    description=result.description,
    asset_id=result.asset_id,
    priority=result.priority.value,
    work_type="corrective",
    trade="HVAC",
    diagnostic_summary=result.diagnostic_context,
    created_by="workorder_llm_service",
    correlation_id=request.site_id,
)
engine.cmms.submit_work_order(wo)
```

---

## 6. Natural Language Work Order Interpretation

**Method:** `WorkOrderLLMService.interpret()`  
**Endpoint:** `POST /api/v1/workorders/interpret`

### 6.1 Input

| Field | Type | Description |
|-------|------|-------------|
| `text` | str | Free-text issue description |
| `voice_transcript` | str (optional) | Voice-to-text transcript |
| `context` | Dict (optional) | Current location, recent alerts, etc. |

### 6.2 LLM Extraction

The LLM extracts structured fields from unstructured text:

- **Title** — Short descriptive title (max 80 chars)
- **Description** — Full cleaned description
- **Asset ID** — Equipment ID if mentioned (e.g., RTU-001, AHU-003)
- **Estate/Location** — Building/floor/room if mentioned
- **Priority** — Inferred from severity keywords
- **Problem type** — One of: Temperature Control, Mechanical, Refrigerant/Leak, Electrical, Controls/BMS, Airflow, General
- **Symptoms** — Extracted symptom list
- **Clarifications** — Questions for the user when information is ambiguous

### 6.3 Fallback Heuristics

When the LLM is unavailable, keyword-based classification activates:

| Keywords Detected | Problem Type | Priority Boost |
|-------------------|-------------|----------------|
| temp, hot, cold, freez, overheat | Temperature Control | — |
| noise, vibrat, grind, rattle | Mechanical | — |
| leak, refrigerant, oil, water | Refrigerant/Leak | → HIGH |
| urgent, emergency, immediate, critical, safety | *(unchanged)* | → CRITICAL |
| alarm, fault, error, trip | *(unchanged)* | *(adds fault_code symptom)* |

Asset ID is extracted via regex: `[A-Za-z]{2,4}[-\s]?\d{3}`

---

## 7. AI Prioritization & Impact Assessment

**Method:** `WorkOrderLLMService.prioritize()`  
**Endpoint:** `POST /api/v1/workorders/prioritize`

### 7.1 Impact Assessment Dimensions

The LLM evaluates every work order across multiple operational impact dimensions:

| Dimension | Output | Description |
|-----------|--------|-------------|
| `safety_risk` | High / Medium / Low | Life safety, food safety, environmental hazard |
| `revenue_impact` | Dollar estimate | Estimated revenue loss from inaction |
| `sla_breach_risk` | 0.0–1.0 | Probability of SLA breach |
| `brand_impact` | Yes / No | Customer-visible impact |
| `priority_score` | 0–100 | Composite priority score |
| `recommended_sla_hours` | int | Recommended SLA window |
| `rationale` | str | 2–3 sentence explanation |

### 7.2 Scoring Guidelines

| Score Range | Urgency | Action |
|-------------|---------|--------|
| **90–100** | Immediate | Safety risk or cascading failure potential |
| **70–89** | Urgent | Active degradation with SLA/revenue impact |
| **50–69** | Moderate | Schedule within maintenance window |
| **30–49** | Low | Plan for next PM cycle |
| **0–29** | Informational | Monitor only |

### 7.3 Fallback Scoring

```
base_score = {critical: 90, high: 70, medium: 50, low: 30}
+ 10 if source is AI_SENSOR or PDM_ALERT
+ 15 if safety keywords detected (safety, leak, fire, hazard)
+ 5  if critical keywords detected (critical, failure, down)
```

---

## 8. Intelligent Provider Matching & Dispatch

**Method:** `WorkOrderLLMService.match_providers()`  
**Endpoint:** `POST /api/v1/workorders/match`

### 8.1 Provider Profile

Each service provider is modeled with:

| Field | Type | Description |
|-------|------|-------------|
| `id` | str | Provider identifier |
| `name` | str | Company name |
| `specialty` | str | Primary trade/skill area |
| `rating` | float | Historical performance rating |
| `ftfr` | float (0–1) | First-time fix rate |
| `avg_cost` | float | Average cost per job |
| `avg_response_hrs` | float | Average response time |
| `proximity_miles` | float | Distance to site |
| `certifications` | List[str] | Professional certifications |
| `available` | bool | Currently accepting dispatch |

### 8.2 Matching Criteria (Weighted)

| Criterion | Weight | Description |
|-----------|--------|-------------|
| **Skill match** | 30% | Provider specialty vs. problem type |
| **FTFR** | 25% | First-time fix rate history |
| **Availability** | 15% | Currently available for dispatch |
| **Response time** | 15% | Average response hours vs. SLA requirement |
| **Proximity** | 10% | Distance to site |
| **Cost** | 5% | Average cost relative to estimate |

**For CRITICAL priority:** Response time and availability weights are elevated.  
**Unavailable providers:** Scored below 20 (effectively excluded).

### 8.3 Output

Each provider receives a `match_score` (0–100), `recommended` flag, and natural-language `rationale`. The top-ranked provider is auto-recommended if none are explicitly flagged by the LLM.

---

## 9. Cost & Approval Recommendation

**Method:** `WorkOrderLLMService.recommend_cost()`  
**Endpoint:** `POST /api/v1/workorders/recommend-cost`

### 9.1 Decision Framework

The LLM compares estimated cost against historical similar work orders:

| Decision | Confidence | Trigger |
|----------|-----------|---------|
| **approve** | > 0.8 | Cost within 120% of historical average |
| **review** | 0.5–0.8 | Cost 120–180% of average, or unusual scope |
| **reject** | > 0.7 | Cost > 200% of average with no justification, or compliance violation |

### 9.2 Fallback Logic

```python
ratio = estimated_cost / historical_average

if ratio < 1.2:   action = "approve", confidence = 0.90
if ratio < 1.8:   action = "review",  confidence = 0.70
if ratio >= 1.8:  action = "review",  confidence = 0.60
```

### 9.3 Output

| Field | Description |
|-------|-------------|
| `action` | approve / reject / review |
| `confidence` | 0.0–1.0 |
| `reason` | Detailed explanation referencing historical comparisons |
| `historical_comparison` | How cost compares to similar past work |
| `risk_factors` | List of financial risk factors |

---

## 10. Post-Service Verification

**Method:** `WorkOrderLLMService.verify()`  
**Endpoint:** `POST /api/v1/workorders/verify`

### 10.1 Purpose

After a technician completes service, the system compares **pre-service** and **post-service** metrics to determine if the fix was effective. If verification fails, the work order is flagged for reopen.

### 10.2 Input

| Field | Description |
|-------|-------------|
| `work_order_id` | WO being verified |
| `title` / `asset_id` / `problem_type` | Context from the original WO |
| `pre_service_metrics` | Dict[str, float] — readings before service |
| `post_service_metrics` | Dict[str, float] — readings after service |
| `service_description` | What the technician reported doing |

### 10.3 Verification Criteria

- Key metrics should show improvement (lower anomaly scores, stable temperatures)
- Sensor readings should return to baseline operating range
- If metrics are unchanged or worse → flag for reopen
- Some improvements may take 24–48h to materialize

### 10.4 Directionality (Fallback)

The fallback distinguishes metric direction:

| Keywords in Metric Name | Direction |
|------------------------|-----------|
| score, anomaly, deviation, error, vibration, noise, leak | **Lower is better** |
| *(all others: efficiency, capacity, etc.)* | **Higher is better** |

**Pass threshold:** ≥60% of overlapping metrics show improvement.  
**Confidence:** `ratio_improved × 0.9`

### 10.5 Output

| Field | Description |
|-------|-------------|
| `passed` | bool — whether verification passed |
| `confidence` | 0.0–1.0 |
| `post_metrics_improved` | bool — majority of metrics improved |
| `evidence_summary` | Detailed pre/post comparison |
| `reopen_reason` | If failed, explanation of what remains unresolved |
| `recommendations` | Follow-up actions (e.g., "Schedule follow-up inspection within 48h") |

---

## 11. Predictive Forecast & Narrative

**Method:** `WorkOrderLLMService.forecast()`  
**Endpoint:** `POST /api/v1/workorders/forecast`

### 11.1 Statistical Forecast Model

Generates daily work order volume predictions using a simple seasonal + trend model:

```
predicted = base_rate × day_of_week_factor × seasonal_factor

day_of_week_factor = 0.6 on weekends, 1.0 on weekdays
seasonal_factor = 1.0 + 0.15 × sin(2π × day_of_year / 365)
```

`base_rate` is computed from the trailing 30-day average of historical WO counts.

### 11.2 LLM Narrative

The LLM generates a 3–5 sentence natural-language interpretation including:

- Key trends and seasonal patterns
- Risk drivers (assets with risk scores > 0.7)
- Risk heat map by estate
- Seasonal factors identified

### 11.3 Output

| Field | Description |
|-------|-------------|
| `points` | List of daily forecast points with confidence bands and risk drivers |
| `narrative` | LLM-generated interpretation |
| `risk_estates` | Dict[estate_name, risk_score] |

---

## 12. Workflow Agents (Case Triage Pipeline)

**File:** `predictive_maintenance/agents/workflow_agents.py`

Three event-driven workflow agents process cases from the PdM orchestrator:

### 12.1 CaseTriageAgent

**Trigger:** `CASE_CREATED` event  
**Output:** `CASE_TRIAGED` event with triage decision

| Severity | Decision | Priority Score |
|----------|----------|----------------|
| high | `dispatch` | 0.8 |
| *(other)* | `triage` | 0.5 |

### 12.2 EvidenceToActionAgent

**Trigger:** `CASE_TRIAGED` event  
**Output:** `MAINTENANCE_PACKET_CREATED` event

Builds a maintenance packet containing:
- Problem statement
- Evidence items (telemetry snapshots, trend data)
- Likely root causes
- Recommended actions
- Safety notes

### 12.3 WorkOrderComposerAgent

**Trigger:** `CASE_TRIAGED` event (only if `triage_decision == "dispatch"`)  
**Output:** `WORK_ORDER_DRAFTED` event

Composes a work order with:
- Title and description
- Priority level
- Estimated parts list
- Estimated duration (default: 2.0 hours)

### 12.4 Integrated Orchestrator Flow

The `IntegratedPDMOrchestrator` chains model agents with workflow agents:

```
1. Model agents analyze telemetry (Layers 0-4)
2. Orchestrator determines should_alert + alert_type
3. If alert_type in ["action", "dispatch"]:
   a. CaseTriageAgent triages the case
   b. EvidenceToActionAgent builds maintenance packet
4. If alert_type == "dispatch":
   c. WorkOrderComposerAgent drafts WO
```

---

## 13. Execution Engine (Closed-Loop CMMS)

**File:** `loweconex_platform/execution/execution_engine.py`

### 13.1 ExecutionEngine

Orchestrates the full closed-loop execution pipeline:

```
Recommendation Generation (KPI Crews)
        ↓
Human Review / Approval Gate
        ↓
Work Order Creation in CMMS
        ↓
Control Action Execution (with safety checks)
        ↓
Outcome Tracking & M&V Reconciliation
```

### 13.2 WorkOrderRequest (Execution Model)

| Field | Description |
|-------|-------------|
| `wo_id` | UUID, auto-generated |
| `title` / `description` | Work order details |
| `priority` | emergency / critical / high / medium / low / planned |
| `status` | draft / submitted / approved / in_progress / completed / verified / cancelled |
| `company_id` / `location_id` / `asset_id` | Entity references |
| `work_type` | preventive, corrective, inspection, project |
| `trade` | HVAC, refrigeration, electrical, plumbing |
| `estimated_hours` / `estimated_cost_usd` | Labor and cost estimates |
| `evidence_artifact_ids` | Linked evidence bundles |
| `diagnostic_summary` | AI-generated diagnostic context |
| `recommended_parts` | Suggested parts list |
| `category` / `subcategory` / `failure_code` | Auto-categorization from KPI/case |
| `close_out_code` / `close_out_notes` | Completion details |
| `actual_hours` / `actual_cost_usd` | Post-completion actuals |
| `external_id` / `external_system` | CMMS reference |
| `correlation_id` | Links WO to originating recommendation/case |

### 13.3 CMMSConnector

Abstract interface for external CMMS/ITSM systems:

| Method | Description |
|--------|-------------|
| `submit_work_order(wo)` | Create WO in external system |
| `update_work_order(wo_id, updates)` | Update existing WO |
| `attach_evidence(wo_id, artifact_ids)` | Attach evidence bundles |
| `close_work_order(wo_id, close_code, ...)` | Close with completion details |

Concrete implementations connect to **Maximo**, **ServiceNow**, **eMaint**, **Fiix**, or other CMMS platforms.

### 13.4 Control Actions

The ExecutionEngine also manages control actions (setpoint changes, schedule modifications, equipment enable/disable) with a full safety pipeline:

| Action Type | Description |
|-------------|-------------|
| `setpoint_change` | Modify a BMS setpoint |
| `schedule_change` | Change equipment schedule |
| `mode_change` | Switch operating mode |
| `equipment_enable` / `equipment_disable` | Turn equipment on/off |
| `alarm_suppress` | Suppress a known-good alarm |
| `work_order` | Create a work order |
| `notification` | Send alert notification |

### 13.5 Safety Policy Pipeline

Every control action passes through registered safety policies before execution:

```
propose_action(action)
    ↓
FOR each safety_policy:
    IF policy(action) == False:
        → status = REJECTED, reason = "Blocked by safety policy"
        → Logged to ControlActionLog
        → STOP
    ↓
IF requires_approval:
    → status = PROPOSED, await human approval
ELSE:
    → execute_action()
```

### 13.6 Action Status Flow

```
PROPOSED → APPROVED → EXECUTING → COMPLETED
                              ↓
                          FAILED
                              ↓
                        ROLLED_BACK
    ↓
REJECTED (safety policy or human)
```

### 13.7 Control Action Log

Immutable audit trail recording every action lifecycle event:

| Field | Description |
|-------|-------------|
| `log_id` | Unique log entry ID |
| `action_id` | Action being tracked |
| `event` | proposed / safety_blocked / approved / executing / completed / rolled_back |
| `status` | Current status at time of event |
| `timestamp` | Event timestamp |
| `actor` | Who performed the action |
| `snapshot` | Full action state at time of event |

---

## 14. Autopilot Orchestration Runtime

**File:** `predictive_maintenance/autopilot/orchestrator/runtime.py`

### 14.1 OrchestrationRuntime

Main execution engine for autopilot runs with durable checkpointing. Coordinates:

- Playbook loading and step sequencing
- Checkpoint creation and restoration
- Approval workflow
- Step execution
- Error handling and escalation

### 14.2 RunContext

Every run maintains a context object containing:

| Field | Description |
|-------|-------------|
| `run_id` / `thread_id` / `tenant_id` | Identity |
| `site_id` / `asset_id` | Target |
| `playbook` | Active playbook definition |
| `step_index` | Current step position |
| `points` | Current BMS point values |
| `point_history` | Historical point values |
| `variables` | Computed variables during execution |
| `policy` | Site/tenant policy constraints |
| `overrides` | Active override flags |
| `step_results` | Per-step execution results |
| `actions_taken` | Log of all actions performed |
| `errors` | Error messages |

### 14.3 Execution Flow

```
1. start_run(run_id)
   ├── Load run from DB
   ├── Load playbook from registry
   ├── Load site/tenant policy
   ├── Create initial checkpoint
   └── Return RunContext

2. execute_run(context)
   ├── Check preconditions (expression-based)
   │   └── If failed → status = FAILED
   ├── FOR each step in playbook.steps:
   │   ├── Check if approval required (risk tier + action type)
   │   │   └── If yes → create approval, checkpoint, AWAIT
   │   ├── Execute step via StepExecutor
   │   ├── Store result
   │   ├── Handle errors (RETRY / SKIP / ESCALATE / ABORT)
   │   └── Checkpoint after step
   └── Run verification checks
       ├── If passed → outcome = RESOLVED
       └── If failed → outcome = PARTIAL
```

### 14.4 StepExecutor

Executes individual playbook steps with type-specific handlers:

| Step Type | Handler | Description |
|-----------|---------|-------------|
| `READ` | `_execute_read` | Read BMS point values |
| `WRITE_POINT` | `_execute_write_point` | Write setpoint with TTL and correlation ID |
| `CREATE_TICKET` | `_execute_create_ticket` | Create CMMS work order |
| `UPDATE_TICKET` | `_execute_update_ticket` | Update existing work order |
| `NOTIFY` | `_execute_notify` | Send notifications (email, SMS, push) |
| `WAIT` | `_execute_wait` | Wait for duration (checkpointed in production) |
| `COMPUTE` | `_execute_compute` | Evaluate expression, store result |
| `RUN_TEST` | `_execute_run_test` | Run diagnostic test |
| `ESCALATE` | `_execute_escalate` | Escalate to human or vendor |

### 14.5 Durable Checkpointing

After every step, the runtime creates a checkpoint containing the full `RunContext` state. This enables:

- **Resume after crash** — `resume_run(run_id)` restores from latest checkpoint
- **Resume after approval** — When approval completes, run resumes from checkpoint
- **Audit trail** — Full execution history preserved

---

## 15. Playbook System

**File:** `predictive_maintenance/autopilot/playbook/schema.py`

### 15.1 PlaybookDefinition

A playbook is a templated remediation procedure for a specific asset class and fault type:

| Field | Description |
|-------|-------------|
| `id` / `version` | Identity and version (semver) |
| `name` | Human-readable name |
| `asset_class` | HVAC, REFRIGERATION, LIGHTING, ELECTRICAL, PLUMBING, OTHER |
| `fault_type` | Specific fault this playbook addresses |
| `risk_tier` | LOW / MEDIUM / HIGH |
| `triggers` | Expression-based activation conditions |
| `preconditions` | Must-pass conditions before execution |
| `steps` | Ordered list of execution steps |
| `verification` | Post-execution verification checks |
| `escalation` | Escalation configuration |
| `evidence` | Evidence capture requirements |

### 15.2 Trigger & Precondition Expressions

Triggers and preconditions use an expression language evaluated against the run context:

```json
{
  "triggers": [
    {"expr": "points['zone_temp'] > policy['max_zone_temp']", "description": "Zone temp exceeded"}
  ],
  "preconditions": [
    {"expr": "not overrides['maintenance_mode']", "on_fail": "BLOCK"},
    {"expr": "points['compressor_status'] == 1", "on_fail": "TICKET_ONLY"}
  ]
}
```

**Precondition failure actions:**

| Action | Behavior |
|--------|----------|
| `BLOCK` | Abort entire playbook |
| `TICKET_ONLY` | Skip control actions, only create ticket |
| `ESCALATE` | Create escalation event |

### 15.3 Evidence Capture

Each playbook defines evidence requirements:

| Field | Default | Description |
|-------|---------|-------------|
| `capture_windows_sec.before` | 3600 (1h) | Telemetry window before incident |
| `capture_windows_sec.after` | 3600 (1h) | Telemetry window after remediation |
| `required_points` | [] | Specific BMS points to capture |
| `include_regime_history` | true | Include operating regime history |
| `include_alert_history` | true | Include recent alert history |

### 15.4 Escalation Configuration

| Field | Default | Description |
|-------|---------|-------------|
| `create_ticket` | true | Auto-create CMMS ticket on escalation |
| `priority` | P2 | Escalation ticket priority |
| `notify_roles` | [] | Roles to notify |
| `vendor_dispatch` | false | Auto-dispatch to vendor |
| `call_tree` | [] | Ordered list of contacts |

### 15.5 Verification Checks

Post-execution verification expressions with observation windows:

```json
{
  "verification": [
    {
      "expr": "points['zone_temp'] < policy['max_zone_temp']",
      "window_sec": 900,
      "must_hold": true,
      "description": "Zone temp must return to normal within 15 min"
    }
  ]
}
```

---

## 16. Approval Workflow (Human-in-the-Loop)

**File:** `predictive_maintenance/autopilot/orchestrator/approval.py`

### 16.1 Risk Tier-Based Approval

| Risk Tier | READ | WRITE_POINT | CREATE_TICKET | ESCALATE |
|-----------|------|-------------|---------------|----------|
| **LOW** | Auto | Auto | Auto | Auto |
| **MEDIUM** | Auto | **Approval** | Auto | **Approval** |
| **HIGH** | Auto | **Approval** | Auto | **Approval** |

Site/tenant policy can override via `auto_approve_risk_tiers` list.

### 16.2 Approval Flow

```
Step requires approval
    ↓
ApprovalManager.create_approval()
    ├── Create ApprovalModel in DB
    ├── Set run to pending_approval
    ├── Notify approvers (email, SMS, push)
    └── Return approval_id
    ↓
Checkpoint saved, run paused
    ↓
Approver reviews (UI / API)
    ↓
ApprovalManager.record_decision()
    ├── APPROVE → run resumes from checkpoint
    ├── EDIT → run resumes with modified parameters
    └── REJECT → run terminated, reason recorded
```

### 16.3 Approval Statuses

| Status | Description |
|--------|-------------|
| `pending` | Awaiting human decision |
| `approved` | Approved, run may proceed |
| `rejected` | Rejected, run terminated |
| `expired` | Timed out (default: 60 minutes) |

### 16.4 Approval Decisions

| Decision | Effect |
|----------|--------|
| `APPROVE` | Execute step as proposed |
| `EDIT` | Execute step with modified parameters |
| `REJECT` | Terminate run with rejection reason |

---

## 17. CMMS Connectors

### 17.1 Execution Engine Connector (`loweconex_platform/execution/`)

Generic interface for CMMS writeback:

```python
class CMMSConnector:
    def submit_work_order(wo: WorkOrderRequest) -> Dict
    def update_work_order(wo_id, updates) -> Dict
    def attach_evidence(wo_id, artifact_ids) -> Dict
    def close_work_order(wo_id, close_code, notes, actual_hours, actual_cost) -> Dict
```

### 17.2 Autopilot CMMS Connector (`predictive_maintenance/autopilot/connectors/cmms.py`)

Abstract interface with richer operations for playbook execution:

```python
class CMSSConnector(ConnectorBase):
    def create_ticket(title, description, priority, asset_id, site_id, run_id, tags) -> Dict
    def update_ticket(ticket_id, updates) -> Dict
    def get_ticket(ticket_id) -> WorkOrder
    def attach_evidence(ticket_id, evidence_pack_url, evidence_pack_id) -> ConnectorResponse
    def add_note(ticket_id, note, note_type) -> ConnectorResponse
    def list_tickets(site_id, asset_id, status, limit) -> List[WorkOrder]
```

### 17.3 Mock Connector

`MockCMSSConnector` provides a fully functional in-memory implementation for development and testing, with:

- Ticket creation with auto-generated IDs (`TKT-{hex}`)
- Full CRUD operations
- Evidence attachment tracking
- Note history per ticket
- Operation audit logging

### 17.4 WorkOrder (Autopilot Model)

| Field | Description |
|-------|-------------|
| `ticket_id` | Unique identifier (TKT-XXXXXXXX) |
| `title` / `description` | Work order content |
| `priority` | P1 / P2 / P3 / P4 |
| `status` | open / in_progress / completed / cancelled |
| `asset_id` / `site_id` / `run_id` | References |
| `assigned_to` / `assigned_team` | Assignment |
| `evidence_pack_url` / `attachments` | Evidence |
| `due_date` / `completed_at` | Timing |
| `technician_notes` / `resolution_notes` | Notes |
| `tags` | Classification tags |

---

## 18. Recommendation Tracking & Outcome M&V

**Class:** `RecommendationTracker` (in `execution_engine.py`)

### 18.1 Recommendation Lifecycle

```
CREATE → PENDING → ACCEPTED/PARTIALLY_ACCEPTED/REJECTED/DEFERRED
                        ↓
                   IMPLEMENTED (linked to WO IDs)
                        ↓
                   OUTCOME ASSESSED (actual vs. estimated savings)
```

### 18.2 RecommendationRecord

| Category | Fields |
|----------|--------|
| **Identity** | `rec_id`, `title`, `description`, `kpi_name`, `company_id`, `location_id` |
| **Recommendation** | `recommended_action`, `estimated_savings_usd`, `estimated_cost_usd`, `payback_months`, `confidence` |
| **Acceptance** | `acceptance_status`, `accepted_by`, `accepted_ts`, `rejection_reason`, `modifications` |
| **Implementation** | `implemented`, `implementation_date`, `work_order_ids`, `action_ids` |
| **Outcome** | `actual_savings_usd`, `actual_cost_usd`, `outcome_notes`, `outcome_assessed_ts` |

### 18.3 Acceptance Statuses

| Status | Description |
|--------|-------------|
| `pending` | Awaiting decision |
| `accepted` | Accepted as-is |
| `partially_accepted` | Accepted with modifications |
| `rejected` | Rejected with reason |
| `deferred` | Deferred to future period |
| `expired` | Decision window expired |

### 18.4 Portfolio Analytics

The tracker computes aggregate metrics:

| Metric | Description |
|--------|-------------|
| `acceptance_rate` | % of recommendations accepted |
| `implementation_rate` | % of accepted recommendations implemented |
| `realization_rate` | `total_actual_savings / total_estimated_savings` |

These metrics feed back into KPI confidence calibration and model retraining.

---

## 19. A/B Testing Framework

**Method:** `WorkOrderLLMService.ab_test()` and `compute_ab_baseline()`

### 19.1 The 12 A/B Test KPIs

| Metric ID | Description | Baseline Source |
|-----------|-------------|-----------------|
| `alert_to_wo` | % of PdM alerts that became WOs | Alert→WO join |
| `wo_volume` | Total WOs per month | WorkOrderModel count |
| `reactive_pct` | % reactive/emergency WOs | WO type classification |
| `proactive_pct` | % planned/PM WOs | WO type classification |
| `mttr` | Mean time to repair (hours) | opened_at → closed_at |
| `mttd` | Mean time to dispatch (hours) | opened_at → dispatched_at |
| `ftfr` | First-time fix rate % | Completed without reopen |
| `avg_cost` | Average cost per WO ($) | WO cost field |
| `sla_compliance` | % of WOs meeting SLA | Priority-based window check |
| `reopen_rate` | % of WOs reopened | Same-asset WO within 7 days |
| `downtime_hrs` | Avg equipment downtime hours | Alert created → resolved |
| `nif_rate` | No-issue-found dispatch rate % | Feedback outcome |

### 19.2 AI Improvement Factors

Documented improvement projections for the AI work order system:

| Metric | Mode | Factor | Rationale |
|--------|------|--------|-----------|
| `alert_to_wo` | target | 89% | Autonomous creation → high conversion |
| `wo_volume` | multiply | ×0.72 | Proactive reduces cascade failures |
| `reactive_pct` | target | 22% | PdM shifts to planned maintenance |
| `proactive_pct` | target | 78% | Mirror of reactive reduction |
| `mttr` | multiply | ×0.37 | Better diagnostics = faster repair |
| `mttd` | multiply | ×0.23 | AI dispatch eliminates manual delay |
| `ftfr` | target | 91% | Right diagnosis → right fix |
| `avg_cost` | multiply | ×0.65 | Proactive maintenance is cheaper |
| `sla_compliance` | target | 96% | Faster detection + dispatch |
| `reopen_rate` | target | 3% | Post-service verification catches failures |
| `downtime_hrs` | multiply | ×0.25 | Proactive intervention |
| `nif_rate` | target | 3% | AI triage eliminates false dispatches |

### 19.3 Baseline Computation

The `compute_ab_baseline()` method queries the persistence layer:

1. **Database query** — WorkOrderModel, AlertModel, FeedbackModel for the time window
2. **Metric computation** — Each of the 12 metrics computed with provenance tracking
3. **Gap filling** — Missing metrics filled from KPIConfig or industry defaults
4. **Predicted column** — Apply improvement factors to compute AI-projected values
5. **LLM narrative** — Generate analytical comparison (4–8 sentences)

**Provenance tracking** records whether each metric was: `db_computed`, `kpi_config`, `estimated`, or `default`.

---

## 20. API Endpoints

**File:** `predictive_maintenance/api/routes/workorder_routes.py`  
**Base path:** `/api/v1/workorders`

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/status` | Service health & LLM availability |
| `POST` | `/interpret` | NL text → structured WO draft |
| `POST` | `/auto-create` | PdM signals → autonomous WO + CMMS submission |
| `POST` | `/prioritize` | AI impact assessment & priority scoring |
| `POST` | `/match` | Intelligent provider matching & dispatch |
| `POST` | `/recommend-cost` | Cost & approval recommendation |
| `POST` | `/verify` | Post-service verification |
| `POST` | `/forecast` | Predictive forecast + LLM narrative |
| `POST` | `/ab-test` | A/B test comparison analysis |
| `GET` | `/ab-baseline` | Real DB-computed A/B baseline metrics |

### 20.1 Status Response

```json
{
  "status": "healthy",
  "llm_available": true,
  "model": "gpt-4",
  "fallback_active": false
}
```

---

## 21. End-to-End Flow Diagrams

### Flow A: PdM Signal → Autonomous Work Order

```
1. Streaming telemetry arrives via MQTT/BACnet
   └─▶ StreamingIngestService → TwinStore + PdM Kernel

2. PdM Kernel detects anomaly
   └─▶ RegimeDetectionAgent → SensorTrustAgent → BehaviorModelAgent
       → ChangeDetectionAgent → FaultHypothesisAgent → DecisionPolicyAgent

3. Collaborative voting determines alert
   └─▶ IntegratedPDMOrchestrator: should_alert=True, alert_type="dispatch"

4. Workflow agents process case
   └─▶ CaseTriageAgent: decision="dispatch"
       → EvidenceToActionAgent: maintenance packet created
       → WorkOrderComposerAgent: WO drafted

5. AI WO Service enriches
   └─▶ WorkOrderLLMService.auto_create(signals)
       ├── LLM evaluates: should_create=True, priority=HIGH
       ├── Generates title, description, diagnostic_context
       └── Assigns problem_type, recommended_tags

6. Submit to CMMS
   └─▶ ExecutionEngine.cmms.submit_work_order(wo)
       └── External CMMS creates WO, returns external_id

7. AI prioritization
   └─▶ WorkOrderLLMService.prioritize(wo)
       └── priority_score=78, safety_risk=Medium, SLA=24h

8. Provider matching
   └─▶ WorkOrderLLMService.match_providers(wo, providers)
       └── Top provider: match_score=87, FTFR=92%, 2h response

9. Cost approval
   └─▶ WorkOrderLLMService.recommend_cost(wo, history)
       └── action=approve, confidence=0.88

10. Service completed by technician

11. Post-service verification
    └─▶ WorkOrderLLMService.verify(pre_metrics, post_metrics)
        ├── passed=True → status=VERIFIED
        └── passed=False → status=REOPENED, reopen_reason logged
```

### Flow B: Autopilot Playbook Execution

```
1. Incident detected by PdM system
   └─▶ PlaybookRegistry selects matching playbook
       (asset_class=HVAC, fault_type=high_discharge_temp)

2. OrchestrationRuntime.start_run(run_id)
   ├── Load playbook, policy, create RunContext
   └── Initial checkpoint saved

3. execute_run(context)
   ├── Check preconditions (all must pass)
   │
   ├── Step 1: READ
   │   └── Read BMS points: zone_temp, supply_air_temp, discharge_pressure
   │
   ├── Step 2: COMPUTE
   │   └── Calculate delta_t = discharge_temp - supply_temp
   │
   ├── Step 3: WRITE_POINT (requires approval for MEDIUM/HIGH risk)
   │   ├── ApprovalManager.create_approval()
   │   ├── Checkpoint saved, run paused
   │   ├── Human approves via UI
   │   ├── Run resumes from checkpoint
   │   └── Write new setpoint via BMS connector
   │
   ├── Step 4: WAIT (observation period)
   │   └── Wait 300s, checkpoint saved
   │
   ├── Step 5: READ (re-read points)
   │   └── Check if temps stabilized
   │
   ├── Step 6: CREATE_TICKET (if issue persists)
   │   └── CMMS connector creates work order
   │
   └── Verification checks
       └── zone_temp < max_zone_temp within 15 min window

4. Outcome: RESOLVED / PARTIAL / FAILED
   └── Final checkpoint, run status updated in DB
```

### Flow C: Recommendation → Implementation → Outcome

```
1. KPI Crew generates recommendation
   └─▶ RecommendationTracker.create(rec)
       (estimated_savings=$12,000/yr, payback=6mo)

2. Human reviews recommendation
   ├── RecommendationTracker.accept(rec_id, "facility_mgr")
   └── OR .reject(rec_id, "Budget constraints")

3. If accepted → Create work order
   └─▶ ExecutionEngine.create_work_order_from_recommendation(rec_id)
       ├── Build WorkOrderRequest from recommendation fields
       ├── Submit to CMMS
       └── Link WO ID to recommendation

4. Technician completes work

5. Record implementation
   └─▶ RecommendationTracker.record_implementation(rec_id, date, wo_ids)

6. Post-implementation M&V (after observation period)
   └─▶ RecommendationTracker.record_outcome(
           rec_id, actual_savings=10800, actual_cost=3200
       )

7. Portfolio analytics
   └─▶ RecommendationTracker.acceptance_rate()
       {acceptance_rate: 0.72, implementation_rate: 0.65,
        realization_rate: 0.90}
```
