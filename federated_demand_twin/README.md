# Federated Demand Forecasting + Bayesian Decision Twin MVP

> **Version 0.2** - Consolidated MVP Requirements Implementation

Enterprise-grade demand forecasting system combining federated learning, Bayesian uncertainty quantification, and AI-driven decision orchestration.

## 🎯 Executive Summary

This MVP demonstrates for an imaginary enterprise customer ("RetailCo"):

1. **Behind-the-firewall data control**: Raw sales and sensitive operational data remain in RetailCo's network
2. **Federated learning workflow**: Trains/updates demand forecasting models without exporting raw sales
3. **Local inference**: Produces probabilistic forecasts (quantiles) locally
4. **Controlled outbound summaries**: Only approved forecast summaries transmitted to vendor cloud
5. **Bayesian decisioning + optimization**: Translates forecast uncertainty into inventory outcomes and recommends actions
6. **Digital twin**: Stateful simulation service for scenario evaluation
7. **Agentic DOS (CrewAI)**: Orchestrates runs, produces decision packs, monitors outcomes

## 📁 Project Structure

```
federated_demand_twin/
├── customer/                    # Customer-side components (behind firewall)
│   ├── connectors/             # Data ingestion and synthetic generation
│   │   └── synthetic_generator.py
│   ├── fl_client/              # Federated learning client
│   │   ├── demand_model.py     # N-BEATS-inspired forecasting model
│   │   └── client.py           # Flower FL client
│   ├── inference/              # Local inference and reconciliation
│   │   └── reconciliation.py   # Hierarchical forecast reconciliation
│   └── publisher/              # Summary publishing (outbound)
│
├── vendor/                      # Vendor cloud services
│   ├── fl_server/              # Federated learning coordinator
│   │   └── server.py           # Flower FL server with model registry
│   ├── bayesian_engine/        # Bayesian decision engine
│   │   └── decision_engine.py  # PyMC-based uncertainty quantification
│   ├── optimizer/              # Inventory optimization
│   │   └── inventory_optimizer.py  # OR-Tools constrained optimization
│   ├── digital_twin/           # Digital twin simulation
│   │   └── twin_service.py     # Stateful inventory simulation
│   └── agents/                 # CrewAI decision orchestration
│       └── decision_os.py      # Agent-based pipeline orchestration
│
├── shared/                      # Shared schemas and utilities
│   └── schemas/
│       └── data_contracts.py   # Pydantic data contracts (Section 6)
│
├── docker/                      # Docker configuration
│   ├── docker-compose.yml      # Full stack deployment
│   ├── Dockerfile.customer     # Customer environment
│   └── Dockerfile.vendor       # Vendor services
│
├── tests/                       # Test suite
├── run_demo.py                 # End-to-end demo script
├── requirements.txt            # Python dependencies
└── README.md                   # This file
```

## 🚀 Quick Start

### Prerequisites

- Python 3.11+
- Docker & Docker Compose (optional, for containerized demo)

### Installation

```bash
# Clone and navigate to project
cd federated_demand_twin

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### Run Demo (Single Command)

```bash
# NFR-4.1: End-to-end pipeline with a single command
python run_demo.py --rounds 20 --skus 50 --seed 42
```

### Docker Compose (Full Stack)

```bash
cd docker
docker-compose up --build
```

## 📊 Functional Requirements Coverage

| Requirement | Description | Status |
|-------------|-------------|--------|
| **FR-1** | Customer-side data control and processing | ✅ |
| **FR-2** | Federated learning workflow (client + server) | ✅ |
| **FR-3** | Local probabilistic forecasting | ✅ |
| **FR-4** | Hierarchical coherence (reconciliation) | ✅ |
| **FR-5** | Summary publishing (minimum necessary) | ✅ |
| **FR-6** | Bayesian decision engine | ✅ |
| **FR-7** | Optimization service (deterministic) | ✅ |
| **FR-8** | Digital twin simulation | ✅ |
| **FR-9** | Agentic Decision Operating System | ✅ |

## 🔒 Privacy & Security

### Data Boundary Enforcement (FR-1, FR-5)

- **Raw sales data**: NEVER leaves customer environment
- **Exportable summaries**: Only `demand_forecast_summary` and `covariate_summary`
- **FL messages**: Model updates only, not training data

### Privacy Controls (FR-2.4, NFR-1)

```python
# Configuration toggles for privacy features
ClientConfig(
    enable_secure_aggregation=True,   # SecAgg+ via Flower
    enable_differential_privacy=True,  # DP noise injection
    dp_epsilon=1.0,                    # Privacy budget
)
```

### Explicit Disclaimers

> ⚠️ **FL Relevance Risk**: FL's strongest value emerges across multiple data silos. This MVP demonstrates orchestration capability for a single customer.

> ⚠️ **Privacy Risk**: FL does not inherently guarantee privacy. Gradient/model-update leakage risks exist. Mitigations (SecAgg, DP) are provided as toggles.

## 📈 Data Contracts (Section 6)

### Customer-Side Tables (Private)

```python
# Never exported
sales_history(sku_id, store_id, week_start, units, revenue, price, promo_flag)
inventory_state(sku_id, store_id, week_start, on_hand, on_order, backorders)
supply_params(sku_id, supplier_id, lead_time_weeks, MOQ, case_pack, capacity_flags)
hierarchy_map(sku_id, subcategory_id, category_id, region_id)
```

### Exportable Summaries (Customer → Vendor)

```python
# Only these cross the firewall
demand_forecast_summary(entity_id, week_start, q10, q50, q90, model_version)
covariate_summary(entity_id, week_start, promo_intensity_index, price_index, event_flags)
```

### FL Messages

```python
model_update(round_id, client_id, weights_delta, metrics)  # Client → Server
global_model(model_version, weights, config_hash)           # Server → Client
```

## 🧪 Acceptance Tests

| Test | Description | Command |
|------|-------------|---------|
| AT-1 | Data boundary (no raw sales export) | Verified in logs |
| AT-2 | FL rounds (≥10 completed) | `--rounds 20` |
| AT-3 | Forecast outputs (q10/q50/q90) | Check `forecasts.parquet` |
| AT-4 | Hierarchy coherence | MinT reconciliation verified |
| AT-5 | Bayesian posteriors (2+ KPIs) | Stockout + margin impact |
| AT-6 | Optimization (feasible under constraints) | MOQ/lead-time satisfied |
| AT-7 | Decision pack (rationale + alerts) | `reports/decision_pack_*.md` |

## 🛠️ Technology Stack

| Component | Library | Purpose |
|-----------|---------|---------|
| **Federated Learning** | Flower | FL orchestration with SecAgg+ |
| **Forecasting** | PyTorch | N-BEATS-inspired model |
| **Reconciliation** | SciPy | MinT hierarchical coherence |
| **Bayesian Inference** | PyMC | Uncertainty quantification |
| **Optimization** | OR-Tools | Constrained inventory optimization |
| **Simulation** | SimPy + NumPy | Digital twin Monte Carlo |
| **Orchestration** | CrewAI | Agent-based pipeline control |
| **API** | FastAPI | Service endpoints |
| **Containers** | Docker | Deployment packaging |

## 📋 Sprint Implementation

| Sprint | Focus | Status |
|--------|-------|--------|
| Sprint 1 | Repo scaffolding + schemas + synthetic generator | ✅ |
| Sprint 2 | FL server + client; global model versioning | ✅ |
| Sprint 3 | Local inference + quantiles; hierarchical reconciliation | ✅ |
| Sprint 4 | Bayesian decision engine + constrained optimization | ✅ |
| Sprint 5 | Digital twin + CrewAI orchestration/reporting | ✅ |

## 📦 Output Artifacts

After running `run_demo.py`:

```
demo_output/
├── data/
│   ├── sales_history.parquet      # Synthetic sales (private)
│   ├── inventory_state.parquet    # Inventory positions
│   ├── supply_params.parquet      # Supply chain params
│   └── hierarchy_map.parquet      # SKU hierarchy
├── models/
│   └── registry/                  # Versioned FL models
├── forecasts.parquet              # Reconciled forecasts
├── optimization_results.csv       # Recommended policies
├── reports/
│   ├── decision_pack_*.json       # Machine-readable pack
│   └── decision_pack_*.md         # Human-readable report
├── logs/
│   └── optimization_audit.json    # FR-7.2 audit trail
└── demo_summary.json              # Pipeline summary
```

## 🔮 Phase 2 Roadmap (Post-MVP)

- **SLOTH Integration**: Replace post-hoc reconciliation with hierarchy-aware learning
- **Multi-Retailer FL**: Demonstrate cross-organization federated learning
- **Production Hardening**: Enterprise IT acceptance, security audit
- **Advanced UI**: Interactive dashboard (beyond notebook/markdown)
- **Real SecAgg**: Full secure aggregation implementation

## 📚 References

- [Flower Documentation](https://flower.dev/docs/)
- [PyMC Documentation](https://www.pymc.io/welcome.html)
- [OR-Tools Documentation](https://developers.google.com/optimization)
- [CrewAI Documentation](https://docs.crewai.com/)
- [MinT Reconciliation](https://otexts.com/fpp3/reconciliation.html)

## 📄 License

MIT License - See LICENSE file for details.

---

**Built for RetailCo MVP Demo** | Version 0.2 | 2024
