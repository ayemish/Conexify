# Arctic Pulse PM UI - AAO Requirements Gap Analysis

**Date:** January 28, 2026  
**Scope:** Comparison of current PM UI implementation against Autonomous Asset Operations (AAO) functional requirements

---

## Executive Summary

The current PM UI implements **ML Ops / Model Governance** features (Section 13 of AAO spec) but is **missing the majority of operational AAO capabilities**. The UI focuses on the "learning loop" for predictive maintenance models rather than the full observe → diagnose → resolve workflow.

### Models Currently Implemented (3 Models)

| Model | Version | Stage | Purpose |
|-------|---------|-------|---------|
| Anomaly Detection | v2.1.0 | Production | Detect anomalous equipment behavior |
| Failure Prediction | v1.3.0 | Production | Predict equipment failures (24h horizon) |
| RUL Estimation | v3.0.0-beta | Staging | Remaining Useful Life estimation |

---

## Current Implementation Coverage

### ✅ IMPLEMENTED (Partial or Full)

#### Section 13: Model and Detection Governance (ML Ops UI)
| Requirement | Status | Implementation |
|-------------|--------|----------------|
| 13.1 Model Registry View | ✅ Full | `ModelsPage.tsx` - Lists models by type, version, stage, metrics |
| 13.1 Performance Metrics | ✅ Full | Accuracy, F1 Score, AUC-ROC displayed per model |
| 13.1 Drift Indicators | ⚠️ Partial | Alerts exist but no dedicated drift visualization |
| 13.2 Feedback Loop Tools | ❌ Missing | No operator labeling UI in case cockpit |
| 13.3 Safety Metrics | ⚠️ Partial | Error rates shown in `MetricsPage.tsx` |

#### Section 9: Playbooks (A/B Experiments proxy)
| Requirement | Status | Implementation |
|-------------|--------|----------------|
| 9.1 Playbook Library | ⚠️ Proxy | `ExperimentsPage.tsx` - A/B experiments, not playbooks |
| 9.3 Playbook Testing/Simulation | ⚠️ Partial | Experiment comparison but no historical simulation |
| 9.4 Deployment Controls | ⚠️ Partial | Traffic split controls exist |

#### Section 8: Action Review & Approvals
| Requirement | Status | Implementation |
|-------------|--------|----------------|
| 8.1 Approvals Inbox | ✅ Full | `GovernancePage.tsx` - Pending approvals view |
| 8.2 Approval Workflows | ⚠️ Partial | Approve/Reject actions, no modification workflow |
| 8.2 Denial Reasons | ❌ Missing | No structured denial reason capture |
| 8.3 Batch Approvals | ❌ Missing | Individual approvals only |

#### Section 14: Audit, Security, Governance
| Requirement | Status | Implementation |
|-------------|--------|----------------|
| 14.1 Audit Log Explorer | ✅ Full | `GovernancePage.tsx` - Audit tab with export |
| 14.1 Searchable/Filterable | ❌ Missing | No search/filter on audit logs |
| 14.2 Policy Management UI | ❌ Missing | No policy configuration |
| 14.3 Data Governance View | ❌ Missing | No data lineage or quality view |

#### Section 4: Dashboard Widgets (AAO Command Center)
| Requirement | Status | Implementation |
|-------------|--------|----------------|
| 4.1 Fleet Health | ❌ Missing | No asset fleet health overview |
| 4.1 Exceptions Queue Summary | ⚠️ Partial | Alerts shown, not case queue |
| 4.1 Autonomy Status | ❌ Missing | No autonomous action tracking |
| 4.1 Operational Outcomes | ❌ Missing | No savings/uptime metrics |
| 4.1 Integration Health | ⚠️ Partial | `HealthPage.tsx` - Component health only |

---

## ❌ MAJOR GAPS (Not Implemented)

### Section 2: Roles and Permissions (RBAC)
- **No RBAC implementation** - All users see all features
- No tenant/portfolio/site/asset scoping
- No "You can do this now" / "Approval required" / "Not permitted" indicators
- No dual-approval (two-key) workflow

### Section 3: Global Shell and Navigation
- ❌ **No Workspace/Tenant Selector** - Single context only
- ❌ **No Global Search** - Cannot search assets, cases, work orders
- ❌ **No Notifications Center** - No unified alert/escalation view
- ❌ **No Global Assistant Panel** - No conversational AI interface

### Section 5: Asset Explorer
- ❌ **No Asset Hierarchy** - No portfolio → site → equipment tree
- ❌ **No Asset Summary Panel** - No equipment detail view
- ❌ **No Telemetry/Events View** - No time-series charting

### Section 6: Case Queue (Operations Center)
- ❌ **No Case Queue** - No operations triage view
- ❌ **No Queue Prioritization** - No severity/SLA/confidence scoring
- ❌ **No Bulk Actions** - No assign/acknowledge/merge

### Section 7: Case Detail "Cockpit"
- ❌ **No Case Cockpit** - Core operational view missing
- ❌ **No Diagnosis Panel** - No root cause analysis display
- ❌ **No Evidence Panel** - No telemetry snapshots
- ❌ **No Recommended Actions** - No AI-suggested actions
- ❌ **No Case Timeline** - No immutable audit trail
- ❌ **No Evidence Packet Export** - No PDF/JSON bundle

### Section 10: Controls Writeback (BMS/SCADA)
- ❌ **No Control Action Composer** - Cannot write to equipment
- ❌ **No Execution Status** - No command progress tracking
- ❌ **No Safe Mode** - No emergency freeze capability

### Section 11: Work Management (CMMS/EAM)
- ❌ **No Work Order Creation** - Cannot create/assign work orders
- ❌ **No Work Order Lifecycle** - No status tracking
- ❌ **No Dispatch Board** - No scheduling view
- ❌ **No Technician Portal** - No completion workflow

### Section 12: Outcomes and Measurement (M&V)
- ❌ **No Outcome Dashboard** - No verified savings view
- ❌ **No Attribution** - No per-site/per-action breakdown
- ❌ **No Response Time Metrics** - No detect→resolve tracking

### Section 15: Administration and Integrations
- ❌ **No Connector Management** - No BMS/CMMS/IoT setup
- ❌ **No User Management** - No invite/roles/MFA
- ❌ **No Notification Rules** - No escalation configuration

---

## Gap Analysis by User Journey (Section 1.2)

| User Role | Support Level | Notes |
|-----------|---------------|-------|
| **Operator** | 🔴 10% | No case queue, no action execution, no resolution workflow |
| **Supervisor** | 🔴 15% | No SLA management, no escalations, limited approvals |
| **Customer/Asset Owner** | 🔴 5% | No outcomes view, no savings reports, no action history |
| **Technician/Vendor** | 🔴 0% | No work order view, no completion workflow |
| **Admin/Governance** | 🟡 30% | Basic audit logs, no RBAC/integrations/data governance |
| **AI Ops / ML** | 🟢 70% | Model registry, experiments, retraining, governance |

---

## Recommended Prioritization

### Phase 1: Core Operations (Critical)
1. **Asset Explorer** (Section 5) - Foundation for all operations
2. **Case Queue** (Section 6) - Operator triage workflow
3. **Case Cockpit** (Section 7) - Single-pane operations view
4. **RBAC** (Section 2) - Permission model

### Phase 2: Action & Resolution
5. **Recommended Actions** - AI suggestions in case cockpit
6. **Work Order Integration** (Section 11) - CMMS connectivity
7. **Controls Writeback** (Section 10) - BMS/SCADA commands

### Phase 3: Governance & Outcomes
8. **Policy Management** (Section 14.2) - Action constraints
9. **Outcomes Dashboard** (Section 12) - M&V reporting
10. **Notifications Center** (Section 3.3) - Unified alerts

### Phase 4: Advanced Features
11. **Global Assistant** (Section 3.4) - Conversational AI
12. **Playbooks** (Section 9) - Full workflow automation
13. **Dispatch Board** (Section 11.3) - Scheduling

---

## Current vs Required Architecture

```
CURRENT (ML Ops Focus):
┌─────────────────────────────────────────────────────┐
│                    PM UI (pm-ui)                    │
├─────────────────────────────────────────────────────┤
│ Dashboard │ Models │ Experiments │ Retraining │     │
│           │        │             │            │     │
│ Governance │ Health │ Metrics    │            │     │
└─────────────────────────────────────────────────────┘

REQUIRED (Full AAO):
┌─────────────────────────────────────────────────────┐
│              AAO Command Center (Global)            │
├──────────┬──────────┬──────────┬───────────────────┤
│ Asset    │ Case     │ Case     │ Work Orders       │
│ Explorer │ Queue    │ Cockpit  │ & Dispatch        │
├──────────┴──────────┴──────────┴───────────────────┤
│ Controls Writeback │ Playbooks │ Outcomes (M&V)    │
├────────────────────┴───────────┴───────────────────┤
│ ML Ops (Current)   │ Admin & Integrations          │
│ Models/Experiments │ RBAC/Connectors/Policies      │
│ Retraining/Govern  │                               │
└────────────────────┴───────────────────────────────┘
```

---

## Conclusion

The current PM UI covers approximately **15-20%** of the AAO functional requirements, focused primarily on **ML model lifecycle management** (Section 13). The core operational workflows (observe → diagnose → resolve) that enable the primary user journeys (Operator, Supervisor, Customer, Technician) are **not implemented**.

**The 3 models (Anomaly Detection, Failure Prediction, RUL Estimation) are properly displayed** in the Model Registry and Dashboard, but the infrastructure to act on their predictions operationally does not exist in the current UI.
