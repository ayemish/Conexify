# Operations Autopilot

The Operations Autopilot extends the Predictive Maintenance system from **detection-only** to a full **detect → decide → act → verify → document → learn** autonomous remediation loop.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        Operations Autopilot                      │
├─────────────────────────────────────────────────────────────────┤
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────────┐ │
│  │ Playbook │  │ Orchestr │  │ Connecto │  │   Verification   │ │
│  │   DSL    │──│  Runtime │──│   rs     │──│     Engine       │ │
│  └──────────┘  └──────────┘  └──────────┘  └──────────────────┘ │
│       │              │              │               │           │
│  ┌────┴────┐   ┌─────┴─────┐  ┌────┴────┐   ┌──────┴───────┐   │
│  │ Parser  │   │Checkpoint │  │  BMS    │   │   Evidence   │   │
│  │Validator│   │ Manager   │  │  CMMS   │   │   Packs      │   │
│  │Registry │   │ Approvals │  │  Notify │   │   Export     │   │
│  └─────────┘   └───────────┘  └─────────┘   └──────────────┘   │
├─────────────────────────────────────────────────────────────────┤
│  ┌──────────────────────┐  ┌────────────────────────────────┐   │
│  │     Estate Brain     │  │     Compliance Autopilot       │   │
│  │  ┌───────┐ ┌───────┐ │  │  ┌─────────┐ ┌─────────────┐  │   │
│  │  │  RAG  │ │  KG   │ │  │  │  F-Gas  │ │  Logbook    │  │   │
│  │  └───────┘ └───────┘ │  │  │ Tracker │ │  Generator  │  │   │
│  │     ┌─────────┐      │  │  └─────────┘ └─────────────┘  │   │
│  │     │ Planner │      │  │                                │   │
│  │     └─────────┘      │  │                                │   │
│  └──────────────────────┘  └────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

## Quick Start

### 1. Run Database Migration

```bash
cd predictive_maintenance
alembic upgrade head
```

### 2. Create a Playbook

```yaml
# playbooks/my_playbook.yaml
id: pb-example-001
name: Example Playbook
version: "1.0.0"
asset_class: RTU
fault_type: high_temperature
risk_tier: LOW

steps:
  - id: read_values
    type: READ
    params:
      point_ids: [zone_temp, setpoint]
  
  - id: adjust_setpoint
    type: WRITE_POINT
    params:
      point_id: setpoint
      value: 74
      ttl_seconds: 3600

verification:
  - expr: "zone_temp < 78"
    window_sec: 600
    must_hold: true
```

### 3. Register the Playbook

```python
from predictive_maintenance.autopilot.playbook import PlaybookParser, PlaybookRegistry

parser = PlaybookParser()
registry = PlaybookRegistry(session_factory)

with open("playbooks/my_playbook.yaml") as f:
    definition = parser.parse_yaml(f.read())

registry.create(definition.to_dict(), created_by="admin")
```

### 4. Create an Incident

```python
POST /api/v1/incidents
{
  "tenant_id": "tenant-001",
  "site_id": "site-001", 
  "asset_id": "RTU-001",
  "fault_type": "high_temperature",
  "severity": "medium",
  "source": "pdm_alert",
  "trigger_evidence": {"zone_temp": 82.5}
}
```

### 5. Start an Autopilot Run

```python
POST /api/v1/runs
{
  "incident_id": "INC-XXXXXXXX",
  "playbook_id": "pb-example-001"
}

# Then execute
POST /api/v1/runs/{run_id}/execute
```

## Module Structure

```
autopilot/
├── schemas.py           # Domain entities
├── models.py            # SQLAlchemy models
├── repositories.py      # Data access layer
├── routes.py            # REST API endpoints
│
├── playbook/            # Playbook DSL
│   ├── schema.py        # Playbook structure
│   ├── parser.py        # YAML/JSON parser
│   ├── expressions.py   # Expression evaluator
│   └── registry.py      # Playbook CRUD
│
├── orchestrator/        # Execution Runtime
│   ├── runtime.py       # Main orchestrator
│   ├── checkpoint.py    # Durable checkpoints
│   └── approval.py      # Human approvals
│
├── connectors/          # External Integrations
│   ├── base.py          # Plugin interface
│   ├── bms.py           # BMS read/write
│   ├── cmms.py          # Work orders
│   └── notification.py  # Alerts
│
├── verification/        # Post-Action Validation
│   ├── engine.py        # Verification checks
│   └── evidence.py      # Audit artifacts
│
├── knowledge/           # Estate Brain
│   ├── graph.py         # Knowledge graph
│   ├── brain.py         # RAG + KG queries
│   └── planner.py       # Context-aware planning
│
├── compliance/          # Regulatory Compliance
│   └── fgas.py          # EU F-gas 517/2014
│
└── playbooks/           # Example Playbooks
    ├── condenser_fouling.yaml
    ├── refrigerant_leak.yaml
    └── high_discharge_temp.yaml
```

## Playbook DSL Reference

### Top-Level Fields

| Field | Required | Description |
|-------|----------|-------------|
| `id` | Yes | Unique playbook identifier |
| `name` | Yes | Human-readable name |
| `version` | Yes | Semantic version |
| `asset_class` | Yes | Asset type (RTU, AHU, Chiller, etc.) |
| `fault_type` | Yes | Fault this playbook addresses |
| `risk_tier` | Yes | LOW, MEDIUM, or HIGH |
| `triggers` | No | Conditions that activate playbook |
| `preconditions` | No | Must be true before execution |
| `steps` | Yes | Ordered list of actions |
| `verification` | No | Post-action validation |
| `escalation` | No | Failure handling |
| `evidence` | No | Evidence pack configuration |

### Step Types

| Type | Description | Key Params |
|------|-------------|------------|
| `READ` | Read point values | `point_ids` |
| `WRITE_POINT` | Write a control point | `point_id`, `value`, `ttl_seconds` |
| `CREATE_TICKET` | Create CMMS work order | `title`, `description`, `priority` |
| `UPDATE_TICKET` | Update existing ticket | `ticket_id`, `updates` |
| `NOTIFY` | Send notification | `recipients`, `channel`, `message` |
| `WAIT` | Pause execution | `duration_seconds` |
| `COMPUTE` | Calculate a value | `expression`, `output` |
| `RUN_TEST` | Execute diagnostic | `test_id`, `test_params` |
| `ESCALATE` | Escalate to human/vendor | `type`, `reason` |

### Expression Language

Expressions are used in triggers, preconditions, step conditions, and verification.

```yaml
# Comparison operators
expr: "zone_temp > 75"
expr: "pressure <= 250"
expr: "status == 'running'"

# Logical operators
expr: "zone_temp > 75 and outdoor_temp > 80"
expr: "severity == 'high' or severity == 'critical'"
expr: "not override_active('setpoint')"

# Arithmetic
expr: "zone_temp - setpoint"
expr: "fan_speed * 1.1"

# Built-in functions
expr: "avg(zone_temp)"           # Average over history
expr: "delta(pressure)"          # Change over window
expr: "slope(temp)"              # Trend direction
expr: "in_band(temp, 70, 76)"    # Range check
expr: "min(value, 100)"          # Clamp value
expr: "max(value, 0)"

# Policy references
expr: "abs(delta) < policy.max_setpoint_delta"
```

## Risk Tiers & Approvals

| Risk Tier | Auto-Execute | Approval Required |
|-----------|--------------|-------------------|
| LOW | All steps | None |
| MEDIUM | READ, COMPUTE, NOTIFY | WRITE_POINT, ESCALATE |
| HIGH | READ, COMPUTE | All control actions |

Approvals are managed via the `/api/v1/approvals` endpoint:

```python
# List pending approvals
GET /api/v1/approvals?status=pending

# Submit decision
POST /api/v1/approvals/{approval_id}/decision
{
  "decision": "APPROVE",  # or "REJECT" or "EDIT"
  "decided_by": "operator@example.com",
  "decision_notes": "Approved for execution"
}
```

## Checkpoints & Recovery

The orchestrator creates durable checkpoints:
- After each step completion
- Before approval requests
- On errors

To resume from a checkpoint:

```python
POST /api/v1/runs/{run_id}/resume
{
  "checkpoint_id": "CHK-XXXXXXXX"  # Optional, defaults to latest
}
```

## Evidence Packs

After run completion, generate an evidence pack:

```python
GET /api/v1/runs/{run_id}/evidence

# Response includes:
{
  "pack_id": "EVD-XXXXXXXX",
  "content_hash": "sha256:...",
  "before_telemetry_window": {...},
  "actions": [...],
  "approvals": [...],
  "after_telemetry_window": {...},
  "verification_results": [...],
  "outcome": "RESOLVED"
}
```

Export formats: JSON, HTML, PDF (text-based).

## F-Gas Compliance

For refrigerant systems, the compliance module tracks:
- Asset refrigerant metadata (type, charge, GWP, CO2e)
- Leak check scheduling per EU F-gas thresholds
- Refrigerant transactions (top-up, recovery)
- Compliance logbook generation

```python
from predictive_maintenance.autopilot.compliance import (
    FGasComplianceService,
    RefrigerantAsset,
    RefrigerantType,
)

service = FGasComplianceService(session_factory)

# Register asset
asset = RefrigerantAsset(
    asset_id="RTU-001",
    tenant_id="tenant-001",
    site_id="site-001",
    refrigerant_type=RefrigerantType.R410A,
    charge_kg=50.0,
    original_charge_kg=50.0,
)
service.register_asset(asset)

# Generate compliance logbook
logbook = service.generate_logbook("RTU-001")
print(logbook.to_text())
```

## Connectors

### Implementing a Custom Connector

```python
from predictive_maintenance.autopilot.connectors import (
    BMSConnector,
    ConnectorConfig,
    connector,
)

@connector("my_bms")
class MyBMSConnector(BMSConnector):
    def connect(self) -> bool:
        # Establish connection
        self._connected = True
        return True
    
    def read_points(self, point_ids, window_seconds=0):
        # Read from your BMS
        return {...}
    
    def write_point(self, point_id, value, ttl_seconds, correlation_id):
        # Write to your BMS
        return ConnectorResponse(success=True, data={...})
```

### Registering Connectors

```python
from predictive_maintenance.autopilot.connectors import ConnectorRegistry

config = ConnectorConfig(
    name="production_bms",
    connector_type="my_bms",
    base_url="https://bms.example.com",
    api_key="...",
)

connector = ConnectorRegistry.create(config)
connector.connect()
```

## Testing

Run autopilot tests:

```bash
pytest tests/test_autopilot/ -v
```

Test coverage includes:
- Expression evaluator
- Playbook parser and validation
- Connector operations
- F-gas compliance calculations

## API Reference

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/incidents` | POST | Create incident |
| `/api/v1/incidents` | GET | List incidents |
| `/api/v1/incidents/{id}` | GET | Get incident |
| `/api/v1/runs` | POST | Create run |
| `/api/v1/runs` | GET | List runs |
| `/api/v1/runs/{id}` | GET | Get run details |
| `/api/v1/runs/{id}/execute` | POST | Start execution |
| `/api/v1/runs/{id}/cancel` | POST | Cancel run |
| `/api/v1/runs/{id}/resume` | POST | Resume from checkpoint |
| `/api/v1/runs/{id}/evidence` | GET | Get evidence pack |
| `/api/v1/approvals` | GET | List approvals |
| `/api/v1/approvals/{id}` | GET | Get approval |
| `/api/v1/approvals/{id}/decision` | POST | Submit decision |
| `/api/v1/playbooks` | GET | List playbooks |
| `/api/v1/playbooks/{id}` | GET | Get playbook |
