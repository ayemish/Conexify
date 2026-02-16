"""
Platform configuration for the Loweconex Digital Twin ROI platform.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional
from enum import Enum


class Environment(Enum):
    DEV = "dev"
    STAGING = "staging"
    PRODUCTION = "production"


@dataclass
class RedisConfig:
    url: str = "redis://localhost:6379"
    stream_maxlen: int = 100_000
    consumer_group_prefix: str = "loweconex"
    dead_letter_stream: str = "loweconex:dlq"
    retry_max: int = 3
    retry_backoff_ms: int = 1000


@dataclass
class DatabaseConfig:
    url: str = "postgresql://localhost:5432/loweconex"
    pool_size: int = 10
    max_overflow: int = 20


@dataclass
class TwinStoreConfig:
    backend: str = "in_memory"  # "in_memory" | "postgresql" | "redis"
    timeseries_backend: str = "in_memory"  # "in_memory" | "timescaledb" | "influxdb"
    event_store_backend: str = "in_memory"  # "in_memory" | "postgresql" | "redis_streams"


@dataclass
class CrewAIConfig:
    verbose: bool = True
    max_retries: int = 3
    timeout_seconds: int = 300
    llm_model: str = "gpt-4"
    temperature: float = 0.0


@dataclass
class ROIEngineConfig:
    discount_rate: float = 0.08
    analysis_horizon_years: int = 3
    confidence_levels: List[str] = field(default_factory=lambda: ["low", "medium", "high"])
    double_counting_policy: str = "first_claim"  # "first_claim" | "split" | "highest_confidence"


@dataclass
class ReportConfig:
    output_dir: str = "./reports"
    pdf_enabled: bool = True
    json_enabled: bool = True
    web_enabled: bool = True
    pptx_enabled: bool = True


@dataclass
class PlatformConfig:
    environment: Environment = Environment.DEV
    redis: RedisConfig = field(default_factory=RedisConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    twin_store: TwinStoreConfig = field(default_factory=TwinStoreConfig)
    crewai: CrewAIConfig = field(default_factory=CrewAIConfig)
    roi_engine: ROIEngineConfig = field(default_factory=ROIEngineConfig)
    report: ReportConfig = field(default_factory=ReportConfig)
    artifact_store_path: str = "./artifacts"
    log_level: str = "INFO"

    # Enterprise module feature flags
    lineage_enabled: bool = True
    semantic_ontology_enabled: bool = True
    schema_registry_enabled: bool = True
    mv_verification_enabled: bool = True
    mlops_enabled: bool = True
    ai_risk_enabled: bool = True
    data_quality_enabled: bool = True
    execution_engine_enabled: bool = True
    security_controls_enabled: bool = True
    operating_model_enabled: bool = True
    benchmarking_enabled: bool = True
    agent_ops_enabled: bool = True

    # KPI crews to enable (all by default)
    enabled_kpis: List[str] = field(default_factory=lambda: [
        "work_order_reduction",
        "ppm_maximization",
        "energy_reduction",
        "refrigerant_leak_reduction",
        "food_waste_reduction",
        "call_center_volume_reduction",
        "service_bureau_reduction",
        "asset_failure_prediction",
        "asset_uptime_increase",
        "food_temp_diagnostics_improvement",
        "food_safety_compliance",
        "esg_compliance",
        "preventive_maintenance_optimization",
        "capex_lifecycle_optimization",
    ])

    # Prompt library: role-specific prompt templates keyed by agent role
    prompt_library: Dict[str, str] = field(default_factory=lambda: {
        "research": (
            "You are a Research Analyst specializing in building analytics standards. "
            "Use the load_research_snippets tool to ground your output in authoritative references. "
            "Output JSON with formulas, benchmarks, required_inputs, and citations."
        ),
        "extraction": (
            "You are a Data Extraction Lead. Use read_twin, query_timeseries, and query_events tools "
            "to build a validated KPI input contract. Report all data gaps with severity."
        ),
        "calculation": (
            "You are a Calculation Lead. Invoke the domain calculation tool, then use write_twin to "
            "apply patches and store_artifact to persist results. Be rigorous about units and baselines."
        ),
        "qa": (
            "You are a QA & Reconciliation agent. Verify savings ordering, confidence bounds, "
            "and cross-check against source data using read_twin and query_events. "
            "Block publication if results fail sanity checks."
        ),
        "orchestrator": (
            "You are the Orchestrator coordinating the full analytics pipeline. "
            "Respect KPI dependency order, resolve double-counting via the decision ledger, "
            "and produce a composite result with executive summary."
        ),
    })


# Global system prompt for all agents
SYSTEM_PROMPT = """You are an enterprise analytics agent operating on a governed digital-twin platform.
Rules:
- Do not invent data. If an input is missing, emit a GAP with required fields.
- Every numeric output must include: unit, time window, and provenance (source datasets and filters).
- Produce machine-readable JSON that matches the provided schema, then a brief human explanation.
- Identify double-counting risks when aggregating savings.
- When unsure, choose conservative assumptions and list them explicitly."""

EVIDENCE_GROUNDING_SUFFIX = """
For each claim, reference one of:
- telemetry_point_ids + time ranges
- event_ids / work_order_ids
- tariff ids
- model_version + feature_set hash
If no reference exists, mark the claim as "unverified"."""
