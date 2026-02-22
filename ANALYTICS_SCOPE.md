# Predictive Maintenance Analytics — Scope Document

**Prepared for:** Data Science Team Review  
**Date:** February 20, 2026  
**Version:** 1.0  

---

## 1. Executive Summary

This platform implements a **radar-inspired, Neyman–Pearson constrained** predictive maintenance system for commercial HVAC/R equipment. The central design principle is **controlling operational false-positive rate** while maximizing fault detection.

The system contains **30+ distinct analytics** organized across:

- **8-layer core detection/diagnosis pipeline** (regime → trust → residuals → change detection → fault hypothesis → RUL → decision policy → utility routing)
- **7 composite/cross-cutting analytics** (health index, fingerprinting, vibration/MCSA, digital twin, fleet correlation, ensemble calibration, explainability)
- **2 deep learning models** (Temporal Fusion Transformer, physics-informed neural networks)
- **4 MLOps analytics** (drift detection, retraining triggers, Thompson sampling, fleet budget)
- **14 KPI computation services** (energy, refrigerant, food waste, uptime, ESG, CapEx, etc.)
- **7 LLM-powered work order analytics**
- **Operations Autopilot** (playbook-driven autonomous remediation)

---

## 2. System Architecture

```
Layer 0 — Context:    RegimeDetectionAgent
Layer 1 — Trust:      SensorTrustAgent
Layer 2 — Behavior:   BehaviorModelAgent, ChangeDetectionAgent
Layer 3 — Diagnosis:  FaultHypothesisAgent, RULEstimationService
Layer 4 — Decision:   DecisionPolicyAgent, DecisionUtilityService
          ↓
  GuardianMergeService (monotonic safety enforcement)
          ↓
  CaseTriageAgent → EvidenceToActionAgent → WorkOrderComposerAgent
          ↓
  Operations Autopilot: Playbook → Execute → Verify → Document → Learn
```

Each layer completes before the next begins. Agents broadcast results downstream and participate in collaborative voting with configurable consensus thresholds.

---

## 3. Core Analytics — Layered Pipeline

### 3.1 Layer 0 — Regime Segmentation

**Service:** `RegimeSegmentationService` (`services/regime_service.py`)

**Function:** Labels every timestamp with an operating regime so downstream models never compare different operating states. Largest single source of false-positive reduction.

**11 Operating Regimes:** OFF, STARTUP, SHUTDOWN, STEADY_COOL, STEADY_HEAT, ECONOMIZER, DEFROST, TRANSIENT, CONTROL_EVENT, RECOVERY, UNKNOWN

**Method:**
1. Deterministic rules based on compressor ON/OFF, fan status, valve positions, temperature rate-of-change, pressure variance
2. Optional HMM refinement (stay-probability 0.85) for temporal coherence

**Key thresholds:** startup duration 300s, startup pressure variance 5.0 psi, defrost temp rise 20°F, transient temp change 5°F, transient pressure change 8 psi, economizer damper 70%, recovery temp gap 3°F.

**Inputs:** Compressor current/power, fan status, temperatures, pressures, valve/damper positions, setpoints.  
**Outputs:** `RegimeSegment` with label, start/end timestamps, confidence, duration.

---

### 3.2 Layer 1 — Sensor Trust

**Service:** `SensorTrustService` (`services/sensor_trust_service.py`)

**Function:** Answers *"Do I trust this sensor right now?"* before any anomaly detection. Prevents the #1 source of false positives: bad telemetry triggering fault alarms.

**Five per-sensor trust checks:**

| Check | Method |
|-------|--------|
| **Drift** | Sliding-window trend over 24h; flagged if drift > 5 units/day |
| **Stuck sensor** | Variance of last 30 samples < threshold (0.01–0.1 by type) |
| **Comms integrity** | Quality codes, interpolation flags, data gaps |
| **Out-of-range** | Physical limits + expected operating range per sensor type |
| **Rate-of-change** | Exceeds physically plausible max rate/minute |

**Example specs:** Suction pressure valid 0–200 psig, expected 20–120 psig, max rate 20 psi/min. Discharge pressure valid 0–600 psig, expected 150–450 psig, max rate 30 psi/min.

**Output:** Per-sensor `SensorTrustScore` [0,1] with per-component scores.  
**Downstream impact:** If `min_sensor_trust` below threshold → Decision Policy will NOT alarm for equipment faults, only sensor integrity.

---

### 3.3 Layer 2 — Behavior Modeling & Residual Analysis

**Service:** `ResidualErrorModelService` (`services/residual_service.py`, `behavior_service.py`)

**Function:** Models expected system behavior under current conditions, measures deviation. Radar-inspired: models the "atmosphere" so only genuine "targets" are flagged.

**Statistical model per (regime, sensor) pair:**
```
r_t | regime, load ~ StudentT(μ, σ(load), ν)
σ(load) = σ_base + σ_load_coef × load_proxy   (heteroskedastic)
adjusted_residual = r_t - φ × r_{t-1}           (AR(1) autocorrelation)
```

- Default ν = 4.0 (heavy-tailed Student-t)
- Min 100 samples before fitting; refits every 500 samples
- 5,000 sample history per (regime, sensor) pair

**Outputs per observation:** residual, z-score, p-value, log-likelihood under healthy-state distribution.

---

### 3.4 Layer 2b — Sequential Change Detection

**Service:** `ChangeDetectionService` (`services/change_detection_service.py`)

**Function:** Detects *persistent* changes in the residual stream — not point anomalies. This is where false positives drop dramatically.

**Three parallel detectors:**

| Detector | Method | Threshold |
|----------|--------|-----------|
| **CUSUM** | Cumulative sum of deviations from mean | 5.0 (slack: 0.5) |
| **GLR** | Log-likelihood ratio "change" vs "no-change" over sliding window | 10.0 (window: 50) |
| **Bayesian OCPD** | Run-length distribution for regime shifts | Integrated |

**Persistence requirements (critical for FP control):**
- Min persistence: 30 minutes
- Must span ≥2 steady-state regime segments
- Stability ≥ 0.7 over last 20 samples

**Joint cross-sensor detection:** CUSUM threshold 8.0, GLR threshold 15.0 across multiple sensors simultaneously.

**Outputs:** `ChangePointDetection` per sensor (score, onset, duration, stability) + `JointChangeDetection`.

---

### 3.5 Layer 3 — Fault Hypothesis (Bayesian Diagnosis)

**Service:** `FaultHypothesisService` (`services/fault_hypothesis_service.py`)

**Function:** Probabilistic hypothesis testing over all fault types — NOT multiclass classification. Maintains full belief state.

**Bayesian formula:**
```
P(fault_i | evidence) ∝ P(evidence | fault_i) × P(fault_i)
P(evidence | fault_i) = Π_j LR_j^(strength_j × confidence_j)
```

**Prior computation from fleet statistics:**
```
rate = base_rate + age_factor × age_years + runtime_factor × (hours/1000) × seasonal_factor
```

| Fault Type | Base Rate/yr | Age Factor | Runtime Factor |
|------------|-------------|------------|---------------|
| Refrigerant Leak | 15% | +2%/yr | +0.5%/1000h |
| Condenser Fouling | 25% | +1%/yr | +0.3%/1000h |
| Compressor Degradation | 5% | +2%/yr | +0.5%/1000h |
| Fan Degradation | 10% | +1.5%/yr | +0.3%/1000h |
| Sensor Drift | 8% | +1%/yr | — |

**6 symptom categories extracted from residuals:**
1. Rising/falling superheat (suction temp z > 2σ)
2. Discharge pressure elevation (z > 2σ)
3. Suction pressure anomalies (z > 2σ)
4. Compressor current anomalies (z > 2σ)
5. Extreme sensor deviations (z > 4σ, suggests sensor issue)
6. Duty cycle increase (>15% above baseline)

**12 fault types supported:** refrigerant leak, refrigerant overcharge, TXV restriction, condenser fouling, evaporator fouling, fan degradation, compressor degradation, sensor drift, sensor stuck, control instability, electrical issue, unknown anomaly.

**Outputs:** Full posterior distribution, top/second fault, `probability_mass_top2`, `is_concentrated` (top > 50%), fault-specific recommended action with confidence qualifier.

---

### 3.6 Layer 3b — Remaining Useful Life (RUL) Estimation

**Service:** `RULEstimationService` (`services/rul_estimation_service.py`)

**Function:** Multi-model RUL with inverse-variance weighting and full uncertainty quantification.

**Three sub-models:**

| Model | Method | Key Parameters |
|-------|--------|---------------|
| **Weibull survival** | Conditional E[T-t\|T>t] via numerical integration | Shape k, scale λ per fault type (e.g., leak: k=1.8, λ=720h) |
| **Exponential degradation** | D(t)=1-exp(-λt), solve for D=0.95 | λ per fault (leak: 0.003/h, evap fouling: 0.008/h) |
| **Trend extrapolation** | Linear regression on z-scores → z=3.0 threshold | Last 100 observations |

**Ensemble:** `weights = 1/(|value - median| + spread)`, 90% CI via log-normal.  
**Confidence:** `fault_probability × model_agreement × data_depth`

**Error tracking from feedback:** MAE, coverage probability, false-early rate, false-late rate, degradation acceleration (2nd derivative).

---

### 3.7 Layer 4 — Decision Policy (FP Budget Enforcement)

**Service:** `DecisionPolicyService` (`services/decision_policy_service.py`)

**Function:** Six sequential hard gates controlling the operational false-positive rate.

| Gate | Rule |
|------|------|
| 1. SENSOR_TRUST | min_sensor_trust ≥ threshold |
| 2. STEADY_STATE_OR_CHANGE | Steady state OR confirmed change |
| 3. CHANGE_PRESENT | ≥1 sensor shows persistent change |
| 4. PERSISTENCE | Change persists ≥ min hours |
| 5. DIAGNOSIS_CONFIDENCE | top_fault_probability ≥ threshold |
| 6. BUDGET | Monthly alerts within budget |

**Three-tier alerts:** SENSOR_INTEGRITY, WATCH, ACTIONABLE.  
**Severity:** CRITICAL (compressor/electrical >70%), HIGH (leak/TXV >60%), MEDIUM (>60%), LOW (<60%).  
**NIF escalation:** If NIF rate ≥ 75% of budget → route to human review before dispatch.

---

### 3.8 Layer 4b — Decision Utility (Expected-Utility Routing)

**Service:** `DecisionUtilityService` (`services/decision_utility_service.py`)

**Function:** Formal expected-utility routing with Value-of-Information and human–AI complementarity.

| Action | Utility |
|--------|---------|
| DISPATCH | p_fault × $5,000 - p_no × ($250 + $300) - budget_penalty |
| HUMAN_REVIEW | p_fault × TPR × $5,000 - p_no × FPR × cost - $40 + VoI + complementarity |
| GATHER_DATA | info_gain(CI_width) - p_fault × $20 × 6h + VoI |
| WATCH | -p_fault × $5,000 × 0.5 |

**VoI peaks when:** uncertainty high (wide CI), probability near 0.5, operator accuracy high.  
**Complementarity:** Boosts review when score > 0.5; penalizes when operator queue > 20 or unavailable.

---

## 4. Composite & Cross-Cutting Analytics

### 4.1 Composite Health Index (PHI)

**Service:** `HealthIndexService` (`services/health_index_service.py`)

Fuses all signals into a single 0–100 score per asset (ISO 13374 CBM framework).

**Weights:** sensor trust 15%, change detection 20%, fault probability 25%, RUL 25%, degradation 15%.  
**Bands:** 90–100 healthy, 70–89 monitoring, 40–69 alert, 10–39 action, 0–9 critical.  
**P-F curve position:** `0.6 × degradation_index + 0.4 × (1 - score/100)`.  
**Error calibration** from technician feedback: false-healthy rate, false-critical rate, mean score error.

### 4.2 Equipment Fingerprint & Hierarchical Modeling

**Service:** `EquipmentFingerprintService` (`services/fingerprint_service.py`)

Three-level hierarchy: global fleet model → per-unit adaptation (sensor offsets/scales) → per-climate/building. Prevents installation differences from being flagged as faults.

### 4.3 Vibration & MCSA

**Service:** `VibrationMCSAService` (`services/vibration_mcsa_service.py`)

**Vibration:** FFT spectral analysis, bearing defect frequencies (BPFO/BPFI/BSF/FTF), ISO 10816 severity, imbalance/misalignment scoring.  
**MCSA:** Broken rotor bar (sideband analysis), eccentricity, stator winding, bearing electrical scores, THD monitoring.  
Both track FP/FN rates from historical feedback.

### 4.4 Digital Twin Simulator

**Service:** `DigitalTwinSimulator` (`services/digital_twin_simulator.py`)

Physics-informed thermodynamic cycle model. Simulates vapor-compression cycle with calibratable parameters. 5 fault degradation models (leak, condenser fouling, compressor, evaporator icing, fan). Enables what-if simulation, parameter estimation, and fault injection for training/validation. Tracks residuals and reports ±2σ uncertainty bands.

### 4.5 Fleet-Wide Cross-Asset Correlation

**Service:** `FleetCorrelationService` (`services/fleet_correlation_service.py`)

Common-cause analysis (simultaneous faults across co-located units), fleet degradation curves by age/type cohort (ISO 14224), transfer learning of fingerprint priors. Tracks false-correlation and missed-correlation rates.

### 4.6 Ensemble Calibration (Conformal Prediction)

**Service:** `EnsembleCalibrationService` (`services/ensemble_calibration_service.py`)

Distribution-free prediction intervals via conformal prediction (90% coverage). Isotonic regression for probability calibration. Adaptive model weighting (decay 0.95 + inverse-MAE boost). Per-model MAE/RMSE/bias/coverage tracking.

### 4.7 Explainability Service

**Service:** `ExplainabilityService` (`services/explainability_service.py`)

SHAP values for feature importance (with simplified fallback), counterfactual explanations, similar case retrieval, natural language summaries, gate explanations from decision pipeline.

---

## 5. ML Models

### 5.1 Temporal Fusion Transformer (TFT)

**File:** `models/temporal_fusion_transformer.py`

Long-horizon RUL forecasting. Variable selection networks, multi-head attention (4 heads), gating mechanisms, quantile regression (0.05/0.25/0.5/0.75/0.95). Encoder 168 steps (7 days hourly), decoder 24 steps. 5 static + 15 temporal + 3 known-future features.

### 5.2 Physics-Informed Constraints

**File:** `models/physics_informed_constraints.py`

Embeds thermodynamic constraints into NN training: energy balance, refrigerant mass conservation, cycle bounds (COP ≤ Carnot), mechanical limits (fan laws), temporal consistency. Soft (penalized) or hard (projected) constraints.

---

## 6. MLOps & Continuous Learning

### 6.1 Concept Drift Detection

**Service:** `DriftDetectionService` (`services/drift_detection_service.py`)

Three parallel detectors: input drift (KL/PSI), prediction drift (Page-Hinkley), label drift (fault frequency shift). Each tracks false-alarm and missed-drift rates.

### 6.2 Retraining Trigger Service

**Service:** `RetrainingTriggerService` (`services/retraining_trigger_service.py`)

Five trigger conditions: case feedback (N consecutive incorrect), drift detected, performance degradation (FP/FN rate exceeds threshold), new data volume, scheduled. Emits `RetrainingRequest` via Redis event bus with full error snapshot.

### 6.3 Adaptive Agent Weights (Thompson Sampling)

**Service:** `AdaptiveAgentWeightService` (`services/adaptive_agent_weights.py`)

Beta(α,β) belief per agent. Thompson Sampling for exploration/exploitation. Contextual bandits per regime/fault-type. Online learning from operator feedback.

### 6.4 Fleet Budget Service

**Service:** `FleetBudgetService` (`services/fleet_budget_service.py`)

Aggregates actionable alert counts across all assets at a site to enforce fleet-level FP budgets beyond per-unit limits.

---

## 7. KPI Analytics Suite (14 KPIs)

**Files:** `services/kpi/` — orchestrator aggregates all 14 KPIs with cross-KPI recommendations, scenario comparison, location ranking, and ROI calculations.

| # | KPI | Methodology |
|---|-----|-------------|
| 1 | **Energy Reduction** | IPMVP Option C, ASHRAE 14-2014; ECM disaggregation (fault correction 35%, setpoint 25%, scheduling 20%, efficiency 15%, DR 5%); kW and kWh separated |
| 2 | **Refrigerant Leak Reduction** | EPA Section 608; GreenChill benchmarks; AHRI 580 energy penalty (50 kWh/lb); per-asset GWP (R-404A: 3,922) |
| 3 | **Work Order Reduction** | FMEA/RCM per SAE JA1011, ISO 14224; category reducibility: controls 50%, mechanical 33%, refrigerant 28%, thermal 35%, structural 10% |
| 4 | **Food Waste Reduction** | Q10 Arrhenius spoilage per FDA Food Code 2022; per-department Q10 (dairy 2.0, meat 3.0, deli 3.5); FMI 2020 shrink baselines |
| 5 | **Asset Failure Prediction** | ISO 14224:2016 failure rates (RTU 5.5%, compressor 4%); P-F interval analysis |
| 6 | **PPM Maximization** | Planned-to-reactive maintenance ratio optimization |
| 7 | **Food Safety Compliance** | HACCP-aligned temperature excursion monitoring |
| 8 | **ESG Compliance** | EPA eGRID2022 (0.000386 tCO2/kWh), GWP impacts, social cost of carbon ($51/tCO2) |
| 9 | **Asset Uptime Increase** | Predictive vs reactive maintenance uptime improvement |
| 10 | **Call Center Reduction** | ICMI 2022 benchmarks ($8–15/call); proactive alert-driven call deflection |
| 11 | **Service Bureau Reduction** | Third-party service cost reduction via in-house PdM |
| 12 | **PM Optimization** | Condition-based vs calendar-based scheduling |
| 13 | **Food Temp Diagnostics** | Temperature monitoring accuracy improvement |
| 14 | **CapEx Lifecycle Optimization** | Replacement timing via degradation curves, 8% discount rate |

**Cross-KPI features:** Double-counting reconciliation, scenario comparison (conservative/moderate/aggressive), location-level rankings, Loweconex platform bridge.

---

## 8. Work Order AI (7 Integration Points)

**Service:** `WorkOrderLLMService` (`services/workorder/llm_service.py`)

| # | Function | Description |
|---|----------|-------------|
| 1 | NL → Structured WO | Natural language → structured work order fields |
| 2 | Auto-Create from PdM | Autonomous WO from alert signals |
| 3 | AI Triage | Risk-scored priority ranking |
| 4 | Provider Matching | Skill, proximity, availability, cost matching |
| 5 | Cost Recommendation | Benchmarked cost estimates |
| 6 | Post-Service Verification | Pre/post telemetry comparison |
| 7 | Forecast Interpretation | NL interpretation of maintenance trends |

Falls back to deterministic heuristics when LLM unavailable.

---

## 9. Operations Autopilot

**Files:** `autopilot/` (40+ files)

Full **detect → decide → act → verify → document → learn** loop.

**Components:** Playbook DSL (YAML), Orchestrator Runtime (checkpoints, approvals, rollback), BMS/CMMS/Notification Connectors, Verification Engine (telemetry expression evaluation), Approval Queue (human-in-the-loop), Estate Brain (RAG + KG + Planner), Compliance Autopilot (F-Gas, logbook), Alert→Incident Bridge (auto-converts actionable alerts to incidents with playbook matching).

---

## 10. Multi-Agent Orchestration

**Files:** `agents/orchestrator.py`, `model_agents.py`

13 agents across 5 layers. Collaborative voting with `AgentOpinion` (strongly agree → abstain), confidence-weighted. Consensus threshold 0.6, min 3 votes. Agent weights optimized via Thompson Sampling. Layer timeout 30s.

---

## 11. Guardian Merge (Safety Layer)

**Service:** `GuardianMergeService` (`services/guardian_merge_service.py`)

**Monotonic safety:** Agents can tighten (downgrade/suppress) but CANNOT relax hard gates. Failed gates → force AUTO_MONITOR. Suppress at ≥70% confidence, escalate at ≥75%, enrich at ≥60%.

---

## 12. Predictive Maintenance Flow — End-to-End Walkthrough

### Step 1: Telemetry Ingestion
Raw sensor readings arrive every 5–15 minutes: pressures, temperatures, currents, fan status, valve positions, ambient conditions per asset.

### Step 2: Regime Segmentation (Layer 0)
`RegimeSegmentationService` classifies operating regime (e.g., STEADY_COOL). If STARTUP/TRANSIENT/DEFROST → suppress anomaly detection for expected transient behavior. Uses deterministic rules + optional HMM refinement.

### Step 3: Sensor Trust (Layer 1)
`SensorTrustService` checks each sensor: stuck (variance < threshold), drift (24h trend), physical range, rate-of-change, comms quality. Produces per-sensor trust score [0,1]. **If min trust < threshold → pipeline blocks equipment fault alarms**, emits sensor integrity alert only.

### Step 4: Behavior Prediction & Residuals (Layer 2)
`ResidualErrorModelService` retrieves fitted Student-t distribution for (regime, sensor) pair. Computes `residual = observed - predicted`, adjusts for AR(1) autocorrelation and load-dependent heteroskedasticity. Outputs z-score, p-value, log-likelihood per sensor.

### Step 5: Sequential Change Detection (Layer 2b)
Three parallel detectors (CUSUM, GLR, Bayesian OCPD) process the residual stream. A change must persist ≥30 minutes, span ≥2 steady-state segments, and have stability ≥0.7 to advance. Joint cross-sensor detection strengthens correlated evidence. **If no persistent change → remain in WATCH mode.**

### Step 6: Fault Hypothesis (Layer 3)
`FaultHypothesisService` extracts symptoms from residual z-scores (superheat, pressures, current, duty cycle). Performs Bayesian evidence fusion with fault-specific likelihood ratios weighted by symptom strength and confidence. Produces full posterior over 12 fault types. **If diagnosis not concentrated → continue gathering evidence (WATCH).**

### Step 7: RUL Estimation (Layer 3b)
Three sub-models (Weibull survival, exponential degradation, trend extrapolation) produce RUL estimates. Combined via inverse-variance weighting with 90% CI. Degradation index, rate, and acceleration tracked. Confidence = fault_probability × agreement × data_depth.

### Step 8: Decision Policy Gates (Layer 4)
Six sequential gates: sensor trust → steady state → change present → persistence → diagnosis confidence → budget. ALL must pass for an actionable alert. NIF rate check routes borderline cases to human review. Severity assigned based on fault type and probability. Impact estimates (energy penalty, downtime risk, comfort risk, cost-if-ignored) attached.

### Step 9: Utility Routing (Layer 4b)
Expected utility computed for DISPATCH, HUMAN_REVIEW, GATHER_DATA, WATCH. Incorporates cost parameters ($250 truck roll, $5,000 missed failure, $300 false alarm), budget state, Value-of-Information, and human–AI complementarity. Selects highest-utility action.

### Step 10: Guardian Merge
Agent advisories merged with kernel decision under monotonic safety constraint. Hard gate failures cannot be overridden. Advisory actions (suppress/downgrade/escalate/enrich) applied only above confidence thresholds.

### Step 11: Alert → Incident Bridge
Actionable alerts auto-converted to autopilot incidents. Deduplicates against open incidents. Auto-matches playbook by fault type and asset class. Creates autopilot Run if playbook found.

### Step 12: Work Order & Remediation
If DISPATCH: WorkOrderComposerAgent generates structured WO with diagnosis, evidence, parts list, provider recommendation. If autopilot playbook matched: orchestrator executes steps (READ → WRITE_POINT → VERIFY) with checkpoint/rollback. Post-service verification compares pre/post telemetry. Feedback loops back to calibrate all upstream models (drift detection, retraining triggers, error rates, Thompson Sampling weights).

---

## 13. Appendix: Fault Types & Sensor Types

**12 Fault Types:** refrigerant_leak, refrigerant_overcharge, txv_restriction, condenser_fouling, evaporator_fouling, fan_degradation, compressor_degradation, sensor_drift, sensor_stuck, control_instability, electrical_issue, unknown_anomaly

**18 Sensor Types:** suction_pressure, discharge_pressure, suction_line_temp, liquid_line_temp, compressor_current, compressor_power, evap_fan_status, condenser_fan_status, valve_position, return_air_temp, supply_air_temp, mixed_air_temp, supply_fan_speed, damper_position, cooling_valve, heating_valve, zone_temp, ambient_temp, ambient_humidity
