# HVACR Predictive Maintenance (PdM) Integration Analysis

## Overview

The HVACR Predictive Maintenance system provides a comprehensive ML-powered solution for equipment failure prediction, anomaly detection, and proactive maintenance planning in Oil & Gas operations. This document outlines the implemented functionality across all phases.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           HVACR PdM System                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │
│  │   Model     │  │  A/B Test   │  │ Retraining  │  │ Governance  │        │
│  │  Registry   │  │  Framework  │  │  Pipeline   │  │  Controls   │        │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘        │
│         │                │                │                │               │
│         └────────────────┴────────────────┴────────────────┘               │
│                                   │                                         │
│                          ┌───────┴───────┐                                 │
│                          │ HVACRPdMSystem │                                 │
│                          └───────┬───────┘                                 │
│                                  │                                          │
│  ┌───────────────────────────────┴───────────────────────────────────┐     │
│  │                    Observability Stack                             │     │
│  ├─────────────┬─────────────┬─────────────┬─────────────┬───────────┤     │
│  │  Metrics    │    API      │ Notifications│  Scheduler  │  Health   │     │
│  │ Collector   │  Endpoints  │   Service    │   & Jobs    │  Checks   │     │
│  └─────────────┴─────────────┴─────────────┴─────────────┴───────────┘     │
│                                  │                                          │
│                          ┌───────┴───────┐                                 │
│                          │   Demo UI     │                                  │
│                          └───────────────┘                                 │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Phase 4: ML Learning Loop System

### Location
`federated_demand_twin/vendor/agents/ecosystems/oil_gas/`

### Components

#### 1. Data Models (`learning_loop_models.py`)

| Model | Description |
|-------|-------------|
| `ModelVersion` | Tracks model versions with semantic versioning, artifacts, and lineage |
| `PerformanceMetrics` | Classification, regression, anomaly detection, and PdM-specific metrics |
| `Experiment` | A/B test configuration with control/treatment variants |
| `ExperimentVariant` | Individual variant in an experiment with metrics tracking |
| `RetrainingTrigger` | Defines conditions that trigger model retraining |
| `RetrainingJob` | Tracks retraining job execution and results |
| `GovernanceApproval` | Approval workflow for model deployments |

**Enumerations:**
- `ModelType`: ANOMALY_DETECTION, FAILURE_PREDICTION, RUL_ESTIMATION, DEMAND_FORECAST, etc.
- `ModelStage`: DEVELOPMENT, STAGING, PRODUCTION, ARCHIVED, DEPRECATED
- `ExperimentStatus`: DRAFT, RUNNING, PAUSED, COMPLETED, STOPPED
- `TrafficSplitStrategy`: RANDOM, STICKY_USER, STICKY_SITE, ROUND_ROBIN, WEIGHTED
- `RetrainingTriggerType`: SCHEDULED, DRIFT_DETECTED, PERFORMANCE_DEGRADATION, DATA_VOLUME, MANUAL, CASE_FEEDBACK
- `ApprovalStatus`: PENDING, APPROVED, REJECTED, AUTO_APPROVED, EXPIRED
- `GovernanceAction`: MODEL_DEPLOY, MODEL_PROMOTE, EXPERIMENT_START, CONFIG_CHANGE, ROLLBACK

#### 2. Model Registry (`learning_loop_registry.py`)

```python
class ModelRegistry:
    def register_model(version: ModelVersion) -> bool
    def get_model(version_id: str) -> Optional[ModelVersion]
    def get_production_model(model_name: str) -> Optional[ModelVersion]
    def promote_model(version_id: str, target_stage: ModelStage) -> bool
    def rollback_model(model_name: str, target_version_id: str) -> bool
    def compare_versions(version_a: str, version_b: str) -> Dict
    def get_model_lineage(version_id: str) -> List[ModelVersion]
```

**Features:**
- Semantic versioning (MAJOR.MINOR.PATCH)
- Stage-based lifecycle management
- Rollback capability with safety checks
- Model lineage tracking
- Version comparison

#### 3. A/B Testing Framework (`learning_loop_abtesting.py`)

```python
class ABTestingFramework:
    def create_experiment(config: Dict) -> Experiment
    def start_experiment(experiment_id: str) -> bool
    def stop_experiment(experiment_id: str) -> bool
    def get_variant(experiment_id: str, context: Dict) -> str
    def record_outcome(experiment_id: str, variant_id: str, metrics: Dict)
    def conclude_experiment(experiment_id: str) -> Dict
```

**Traffic Split Strategies:**
- **Random**: Pure random assignment
- **Sticky User**: Consistent assignment per user
- **Sticky Site**: Consistent assignment per site
- **Round Robin**: Sequential rotation
- **Weighted**: Custom traffic percentages

**Statistical Analysis:**
- Z-test for significance
- Confidence intervals
- Winner determination

#### 4. Retraining Pipeline (`learning_loop_retraining.py`)

```python
class RetrainingPipeline:
    def add_trigger(trigger: RetrainingTrigger)
    def evaluate_triggers(model_name: str) -> List[RetrainingTrigger]
    def create_job(model_name: str, trigger: RetrainingTrigger) -> RetrainingJob
    def execute_job(job_id: str) -> bool
    def record_metrics(model_name: str, metrics: PerformanceMetrics)
    def record_feedback(model_name: str, feedback: Dict)
```

**Trigger Types:**
- **Scheduled**: Cron-based periodic retraining
- **Drift Detection**: Data distribution changes
- **Performance Degradation**: Accuracy drops below threshold
- **Data Volume**: New data exceeds threshold
- **Manual**: Human-triggered retraining
- **Case Feedback**: Triggered by operational feedback

#### 5. Governance Controls (`learning_loop_governance.py`)

```python
class MLGovernanceController:
    def request_approval(action: GovernanceAction, context: Dict) -> GovernanceApproval
    def process_decision(approval_id: str, decision: str, reviewer: str) -> bool
    def validate_action(action: GovernanceAction, actor: str, context: Dict) -> Tuple[bool, str]
    def assess_risk(action: GovernanceAction, context: Dict) -> str
    def get_audit_log(filters: Dict) -> List[Dict]

class RollbackManager:
    def initiate_rollback(model_name: str, target_version: str, reason: str) -> bool
    def execute_rollback(rollback_id: str) -> bool
```

**Risk Assessment Levels:**
- **Low**: Auto-approved actions
- **Medium**: Requires single approval
- **High**: Requires senior approval
- **Critical**: Requires multiple approvals

#### 6. Integrated System (`learning_loop_hvacr.py`)

```python
class HVACRPdMSystem:
    def register_model(model: ModelVersion) -> bool
    def deploy_model(version_id: str, deployed_by: str) -> Tuple[bool, str]
    def create_experiment(config: Dict) -> str
    def get_prediction_model(model_type: ModelType, context: Dict) -> Optional[ModelVersion]
    def record_prediction_outcome(model_name: str, prediction: Dict, actual: Dict)
    def handle_case_feedback(case_id: str, feedback: Dict)
    def trigger_retraining(model_name: str, reason: str) -> str
    def rollback_model(model_name: str, reason: str) -> bool
```

---

## Phase 5: Observability & API Layer

### Location
`federated_demand_twin/vendor/agents/ecosystems/oil_gas/`

### Components

#### 1. Data Models (`observability_models.py`)

| Model | Description |
|-------|-------------|
| `MetricPoint` | Single metric measurement with labels and timestamp |
| `MetricSeries` | Time series of metric points with statistics |
| `AlertRule` | Alert condition definition with threshold and severity |
| `Alert` | Fired alert with state tracking |
| `NotificationChannel` | Notification delivery configuration |
| `Notification` | Individual notification record |
| `ScheduledJob` | Cron-scheduled job definition |
| `JobExecution` | Job execution record with status and duration |
| `ComponentHealth` | Individual component health status |
| `SystemHealth` | Aggregate system health with all components |

**Enumerations:**
- `MetricType`: COUNTER, GAUGE, HISTOGRAM, SUMMARY
- `MetricNamespace`: MODEL, EXPERIMENT, RETRAINING, GOVERNANCE, SYSTEM, CASE
- `AlertSeverity`: CRITICAL, WARNING, INFO
- `AlertState`: PENDING, FIRING, ACKNOWLEDGED, RESOLVED
- `NotificationChannelType`: EMAIL, SLACK, WEBHOOK, PAGERDUTY, IN_APP
- `HealthStatus`: HEALTHY, DEGRADED, UNHEALTHY, UNKNOWN
- `JobStatus`: SCHEDULED, RUNNING, COMPLETED, FAILED, CANCELLED

#### 2. Metrics Collector (`observability_metrics.py`)

```python
class MetricsCollector:
    def record(name: str, value: float, namespace: MetricNamespace, labels: Dict)
    def increment(name: str, delta: float, labels: Dict)
    def get_metric(name: str, namespace: MetricNamespace, labels: Dict) -> MetricPoint
    def query_range(name: str, namespace: MetricNamespace, start: datetime, end: datetime) -> List[MetricPoint]
    def record_model_metrics(model_name: str, version: str, metrics: PerformanceMetrics)
    def record_prediction(model_name: str, version: str, latency_ms: float, is_correct: bool)
    def add_alert_rule(rule: AlertRule)
    def evaluate_alerts() -> List[Alert]
    def export_prometheus() -> str
    def get_dashboard_summary() -> Dict
```

**Built-in Metrics:**
- Model accuracy, F1 score, AUC-ROC
- Prediction latency (p50, p95, p99)
- Prediction count and error rate
- Experiment traffic and outcomes
- Retraining job status
- System resource utilization

#### 3. REST API (`observability_api.py`)

```python
class HVACRPdMAPI:
    # Health & Status
    def get_health() -> Dict
    def get_readiness() -> Dict
    def get_liveness() -> Dict
    
    # Model Management
    def list_models(filters: Dict) -> Dict
    def get_model(version_id: str) -> Dict
    def deploy_model(request: Dict) -> Dict
    def rollback_model(request: Dict) -> Dict
    
    # Experiments
    def list_experiments() -> Dict
    def get_experiment(experiment_id: str) -> Dict
    def create_experiment(request: Dict) -> Dict
    def start_experiment(experiment_id: str) -> Dict
    def stop_experiment(experiment_id: str) -> Dict
    
    # Retraining
    def trigger_retraining(request: Dict) -> Dict
    def list_retraining_jobs() -> Dict
    
    # Governance
    def list_pending_approvals() -> Dict
    def approve_request(approval_id: str, reviewer: str) -> Dict
    def reject_request(approval_id: str, reviewer: str, reason: str) -> Dict
    
    # Metrics & Alerts
    def get_metrics_prometheus() -> str
    def get_metrics_json() -> Dict
    def get_active_alerts() -> Dict
    def acknowledge_alert(alert_id: str, user: str) -> Dict
    
    # Dashboard
    def get_dashboard() -> Dict
```

#### 4. Notification Service (`observability_notifications.py`)

```python
class NotificationService:
    def add_channel(channel: NotificationChannel)
    def remove_channel(channel_id: str)
    def notify_alert(alert: Alert) -> List[Notification]
    def send_custom(channel_id: str, subject: str, body: str, severity: AlertSeverity) -> Notification
    def get_in_app_notifications(user_id: str) -> List[Notification]
    def get_stats() -> Dict
```

**Notification Providers:**
- `WebhookProvider`: HTTP POST to external endpoints
- `EmailProvider`: SMTP email delivery
- `SlackProvider`: Slack webhook integration
- `InAppProvider`: In-application notification storage

**Features:**
- Rate limiting per channel
- Delivery tracking
- Severity-based routing
- Custom metadata support

#### 5. Scheduler (`observability_scheduler.py`)

```python
class Scheduler:
    def add_job(job: ScheduledJob)
    def remove_job(job_id: str)
    def enable_job(job_id: str)
    def disable_job(job_id: str)
    def run_now(job_id: str) -> JobExecution
    def get_job_status() -> List[Dict]
    def get_execution_history(job_id: str) -> List[Dict]
    def tick() -> List[JobExecution]  # Called by scheduler loop

class CronParser:
    def matches(cron_expr: str, dt: datetime) -> bool
    def next_run(cron_expr: str) -> datetime
```

**Default Jobs:**
- `retraining-check`: Evaluate retraining triggers (every 15 min)
- `metrics-aggregation`: Aggregate metrics (every 5 min)
- `alert-check`: Evaluate alert rules (every minute)
- `health-check`: System health check (every 5 min)

**Cron Expression Support:**
- Standard 5-field format: `minute hour day month weekday`
- Step values: `*/15` (every 15)
- Ranges: `1-5`
- Lists: `1,3,5`

#### 6. Health Checks (`observability_health.py`)

```python
class HealthChecker:
    def check_all() -> SystemHealth
    def check_component(name: str) -> ComponentHealth
    def is_healthy() -> bool
    def is_ready() -> bool
    def is_live() -> bool
    def get_uptime_seconds() -> float

class DiagnosticsRunner:
    def run_full_diagnostics() -> Dict
    def check_model_registry() -> Dict
    def check_retraining_pipeline() -> Dict
    def check_governance() -> Dict
    def generate_recommendations() -> List[str]
```

**Monitored Components:**
- Model Registry
- A/B Testing Framework
- Retraining Pipeline
- Governance Controller
- Metrics Collector
- Notification Service

**Probe Types:**
- **Liveness**: Is the system running?
- **Readiness**: Can the system accept traffic?
- **Health**: Overall system status

#### 7. Observability Stack (`observability.py`)

```python
class ObservabilityStack:
    def __init__(system: HVACRPdMSystem)
    def get_status() -> Dict
    
    # Properties
    system: HVACRPdMSystem
    metrics: MetricsCollector
    api: HVACRPdMAPI
    notifications: NotificationService
    scheduler: Scheduler
    health_checker: HealthChecker
```

---

## Phase 6: User Interface

### Location
`federated_demand_twin/demo-ui/src/`

### Components

#### Layout (`components/PredictiveMaintenanceLayout.tsx`)
- Orange/red themed header with HVACR branding
- Sidebar navigation with 7 menu items
- System status card showing HVACR PdM status
- Quick stats (accuracy, alerts)

#### Pages (`pages/pm/`)

| Page | Route | Description |
|------|-------|-------------|
| `PMDashboardPage.tsx` | `/predictive-maintenance` | Overview with metrics, model summary, alerts |
| `PMModelsPage.tsx` | `/predictive-maintenance/models` | Model registry with search, filtering, details |
| `PMExperimentsPage.tsx` | `/predictive-maintenance/experiments` | A/B test management with metrics comparison |
| `PMRetrainingPage.tsx` | `/predictive-maintenance/retraining` | Job queue, execution history, trigger config |
| `PMGovernancePage.tsx` | `/predictive-maintenance/governance` | Approval workflows, audit log |
| `PMHealthPage.tsx` | `/predictive-maintenance/health` | Component health, system resources, diagnostics |
| `PMMetricsPage.tsx` | `/predictive-maintenance/metrics` | Metrics dashboard, alert management |

### Navigation Access

The Predictive Maintenance UI is accessible via the **Actions** dropdown menu in the header of:
- Retail Media Layout
- Demand & Procurement Layout

Menu item appears **above the Logout button** with:
- Wrench icon
- "Predictive Maintenance" title
- "ML Learning Loop System" subtitle

---

## Test Coverage

### Location
`federated_demand_twin/vendor/agents/ecosystems/oil_gas/tests/`

### Test Files

| File | Tests | Coverage |
|------|-------|----------|
| `test_learning_loop.py` | 25+ tests | Phase 4 components |
| `test_observability.py` | 55 tests | Phase 5 components |

### Test Categories

**Phase 4 (Learning Loop):**
- Data model creation and serialization
- Model registry operations (register, promote, rollback)
- A/B testing (create, traffic split, conclude)
- Retraining pipeline (triggers, jobs)
- Governance (approvals, risk assessment)
- End-to-end workflow

**Phase 5 (Observability):**
- Metric recording and querying
- Prometheus export format
- Alert rule evaluation
- REST API endpoints
- Notification delivery
- Scheduler and cron parsing
- Health checks
- End-to-end integration

---

## File Summary

### Phase 4 Files
```
learning_loop_models.py      # Data models and enums
learning_loop_registry.py    # Model versioning and registry
learning_loop_abtesting.py   # A/B testing framework
learning_loop_retraining.py  # Automated retraining pipeline
learning_loop_governance.py  # Approval workflows and audit
learning_loop_hvacr.py       # Integrated HVACRPdMSystem
learning_loop.py             # Module exports
```

### Phase 5 Files
```
observability_models.py      # Observability data models
observability_metrics.py     # Metrics collector
observability_api.py         # REST API endpoints
observability_notifications.py # Alert notifications
observability_scheduler.py   # Job scheduling
observability_health.py      # Health checks and diagnostics
observability.py             # ObservabilityStack integration
```

### UI Files
```
components/PredictiveMaintenanceLayout.tsx  # Layout with sidebar
pages/pm/PMDashboardPage.tsx                # Dashboard
pages/pm/PMModelsPage.tsx                   # Model Registry
pages/pm/PMExperimentsPage.tsx              # A/B Experiments
pages/pm/PMRetrainingPage.tsx               # Retraining Pipeline
pages/pm/PMGovernancePage.tsx               # Governance
pages/pm/PMHealthPage.tsx                   # System Health
pages/pm/PMMetricsPage.tsx                  # Metrics & Alerts
```

---

## Usage Example

```python
from federated_demand_twin.vendor.agents.ecosystems.oil_gas import (
    HVACRPdMSystem,
    ObservabilityStack,
    ModelVersion,
    ModelType,
    PerformanceMetrics,
)

# Initialize system
system = HVACRPdMSystem(site_id="oil-gas-site-1")
stack = ObservabilityStack(system)

# Register a model
model = ModelVersion(
    version_id="anomaly-v1",
    model_name="anomaly_detection",
    model_type=ModelType.ANOMALY_DETECTION,
    version_number="1.0.0",
)
model.validation_metrics = PerformanceMetrics(
    accuracy=0.95, f1_score=0.92
)
system.register_model(model)

# Deploy to production
success, msg = system.deploy_model("anomaly-v1", "admin", skip_approval=True)

# Record predictions
stack.metrics.record_prediction("anomaly_detection", "1.0.0", 15.0, is_correct=True)

# Check health
health = stack.health_checker.check_all()
print(f"System status: {health.overall_status}")

# Get dashboard data via API
dashboard = stack.api.get_dashboard()
```

---

## Future Enhancements

1. **Real ML Model Integration**: Connect to actual ML inference engines
2. **Persistent Storage**: Add database backing for models and metrics
3. **Real Notification Providers**: Implement actual SMTP/Slack/PagerDuty
4. **Kubernetes Integration**: Add K8s health probes and metrics scraping
5. **Advanced Analytics**: Add drift detection algorithms
6. **UI Enhancements**: Real-time updates, charts, export functionality
