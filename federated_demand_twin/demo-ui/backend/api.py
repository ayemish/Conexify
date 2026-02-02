"""
FastAPI Backend for Retail Media Demo UI

Exposes the Python demo functionality via REST API endpoints.
"""

import sys
import os
from pathlib import Path
import asyncio
from typing import Optional
from datetime import datetime
import json
import logging
from contextlib import redirect_stdout, redirect_stderr
import io

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import numpy as np

# Import demo components
from vendor.retail_media.schemas import (
    MediaChannel,
    RetailerConfig,
    ChannelConfig,
    SKUConfig,
    MediaAllocation,
    AllocationStatus,
    ChannelDigitalTwinState,
    ManufacturerProductConfig,
    ManufacturerChannelState,
    ManufacturerRetailerState,
    ManufacturerProductState,
    ManufacturerSimulationResult,
)
from vendor.retail_media.orchestrator import (
    RetailMediaOrchestrator,
    OrchestratorConfig,
)
from vendor.retail_media.bayesian_engine import BayesianEngineConfig
from vendor.retail_media.media_twin import TwinConfig
from vendor.retail_media.agents import AgentConfig

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Retail Media Demo API",
    description="Backend API for the Four-Plane Architecture Demo UI",
    version="1.0.0"
)

# CORS configuration - allow all origins for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global state to store demo results
demo_state = {
    "orchestrator": None,
    "retailers": [],
    "skus": [],
    "decision_pack": None,
    "logs": [],
    "status": "idle",
    "progress": 0,
    "current_step": "",
}


class LogCapture:
    """Capture log messages for streaming to UI"""
    def __init__(self):
        self.logs = []
    
    def write(self, msg):
        if msg.strip():
            self.logs.append({
                "timestamp": datetime.now().isoformat(),
                "message": msg.strip()
            })
    
    def flush(self):
        pass


def get_channel_configs():
    """Get channel configurations"""
    return [
        ChannelConfig(
            channel=MediaChannel.SPONSORED_SEARCH,
            prior_elasticity_mean=0.18,
            prior_elasticity_std=0.04,
            adstock_decay=0.6
        ),
        ChannelConfig(
            channel=MediaChannel.IN_STORE_DISPLAY,
            prior_elasticity_mean=0.22,
            prior_elasticity_std=0.06,
            adstock_decay=0.5
        ),
        ChannelConfig(
            channel=MediaChannel.CONNECTED_TV,
            prior_elasticity_mean=0.10,
            prior_elasticity_std=0.05,
            adstock_decay=0.8
        ),
        ChannelConfig(
            channel=MediaChannel.EMAIL,
            prior_elasticity_mean=0.12,
            prior_elasticity_std=0.03,
            adstock_decay=0.4
        ),
        ChannelConfig(
            channel=MediaChannel.APP_NOTIFICATION,
            prior_elasticity_mean=0.08,
            prior_elasticity_std=0.03,
            adstock_decay=0.3
        ),
        ChannelConfig(
            channel=MediaChannel.WEBSITE_BANNER,
            prior_elasticity_mean=0.06,
            prior_elasticity_std=0.02,
            adstock_decay=0.5
        ),
    ]


def get_retailer_configs():
    """Get retailer configurations"""
    return [
        RetailerConfig(
            retailer_id="walmart",
            retailer_name="Walmart",
            available_channels=[
                MediaChannel.SPONSORED_SEARCH,
                MediaChannel.IN_STORE_DISPLAY,
                MediaChannel.WEBSITE_BANNER
            ],
            min_spend_share=0.15,
            avg_inventory_weeks=5.0,
            stockout_sensitivity=0.8,
            tier="premium",
            attribution_quality=0.9
        ),
        RetailerConfig(
            retailer_id="kroger",
            retailer_name="Kroger",
            available_channels=[
                MediaChannel.SPONSORED_SEARCH,
                MediaChannel.IN_STORE_DISPLAY,
                MediaChannel.EMAIL
            ],
            min_spend_share=0.12,
            avg_inventory_weeks=4.0,
            stockout_sensitivity=1.0,
            tier="premium",
            attribution_quality=0.85
        ),
        RetailerConfig(
            retailer_id="target",
            retailer_name="Target",
            available_channels=[
                MediaChannel.SPONSORED_SEARCH,
                MediaChannel.CONNECTED_TV,
                MediaChannel.APP_NOTIFICATION
            ],
            min_spend_share=0.10,
            avg_inventory_weeks=4.5,
            stockout_sensitivity=0.9,
            tier="premium",
            attribution_quality=0.88
        ),
        RetailerConfig(
            retailer_id="costco",
            retailer_name="Costco",
            available_channels=[
                MediaChannel.IN_STORE_DISPLAY,
                MediaChannel.EMAIL
            ],
            min_spend_share=0.08,
            avg_inventory_weeks=6.0,
            stockout_sensitivity=0.7,
            tier="standard",
            attribution_quality=0.75
        ),
        RetailerConfig(
            retailer_id="albertsons",
            retailer_name="Albertsons",
            available_channels=[
                MediaChannel.SPONSORED_SEARCH,
                MediaChannel.IN_STORE_DISPLAY
            ],
            min_spend_share=0.05,
            avg_inventory_weeks=3.5,
            stockout_sensitivity=1.2,
            tier="standard",
            attribution_quality=0.70
        ),
    ]


def get_sku_configs():
    """Get SKU configurations"""
    return [
        SKUConfig(
            sku_id="bev-sparkling-12",
            sku_name="Sparkling Water 12pk",
            category="beverages",
            brand="AquaPure",
            unit_price=6.99,
            unit_cost=3.50,
            weekly_base_demand=150,
            demand_std=30,
            media_responsiveness=1.1
        ),
        SKUConfig(
            sku_id="bev-energy-4",
            sku_name="Energy Drink 4pk",
            category="beverages",
            brand="PowerUp",
            unit_price=9.99,
            unit_cost=5.00,
            weekly_base_demand=100,
            demand_std=25,
            media_responsiveness=1.3
        ),
        SKUConfig(
            sku_id="snk-protein-6",
            sku_name="Protein Bar 6pk",
            category="snacks",
            brand="FitFuel",
            unit_price=12.99,
            unit_cost=6.50,
            weekly_base_demand=80,
            demand_std=20,
            media_responsiveness=1.0
        ),
        SKUConfig(
            sku_id="snk-trail-16",
            sku_name="Trail Mix 16oz",
            category="snacks",
            brand="NatureBite",
            unit_price=7.99,
            unit_cost=4.00,
            weekly_base_demand=120,
            demand_std=25,
            media_responsiveness=0.9
        ),
    ]


@app.get("/")
async def root():
    """Health check endpoint"""
    return {"status": "ok", "message": "Retail Media Demo API is running"}


@app.get("/api/status")
async def get_status():
    """Get current demo status"""
    return {
        "status": demo_state["status"],
        "progress": demo_state["progress"],
        "current_step": demo_state["current_step"],
        "has_results": demo_state["decision_pack"] is not None
    }


@app.get("/api/logs")
async def get_logs():
    """Get all captured logs"""
    return {"logs": demo_state["logs"]}


@app.post("/api/demo/run")
async def run_demo():
    """Run the complete demo pipeline"""
    global demo_state
    
    if demo_state["status"] == "running":
        raise HTTPException(status_code=400, detail="Demo is already running")
    
    demo_state["status"] = "running"
    demo_state["progress"] = 0
    demo_state["logs"] = []
    
    def add_log(message: str, level: str = "info"):
        demo_state["logs"].append({
            "timestamp": datetime.now().isoformat(),
            "level": level,
            "message": message
        })
    
    try:
        # Step 1: Initialize orchestrator
        add_log("🎯 RETAIL MEDIA SPEND OPTIMIZATION DEMO", "header")
        add_log("Bayesian → Digital Twin → Agent Pipeline")
        demo_state["current_step"] = "Initializing orchestrator"
        demo_state["progress"] = 5
        
        config = OrchestratorConfig(
            n_simulations=1000,
            simulation_weeks=13,
            save_decision_packs=True,
            output_path="./reports/retail_media_demo"
        )
        
        orchestrator = RetailMediaOrchestrator(
            config=config,
            bayesian_config=BayesianEngineConfig(num_samples=1000),
            twin_config=TwinConfig(default_num_simulations=1000),
            agent_config=AgentConfig(max_scenarios=6)
        )
        
        demo_state["orchestrator"] = orchestrator
        add_log("✓ Orchestrator initialized")
        demo_state["progress"] = 10
        
        # Step 2: Register channels
        demo_state["current_step"] = "Registering channels"
        add_log("\n--- Registering Media Channels ---")
        
        for channel_config in get_channel_configs():
            orchestrator.register_channel(channel_config)
            add_log(f"  ✓ {channel_config.channel.value}: prior η={channel_config.prior_elasticity_mean:.2f} ± {channel_config.prior_elasticity_std:.2f}")
        
        demo_state["progress"] = 20
        
        # Step 3: Register retailers
        demo_state["current_step"] = "Registering retailers"
        add_log("\n--- Registering Retail Media Network Partners ---")
        
        retailers = get_retailer_configs()
        for retailer in retailers:
            orchestrator.register_retailer(retailer)
            channels = ", ".join([c.value for c in retailer.available_channels])
            add_log(f"  ✓ {retailer.retailer_name} ({retailer.tier}): {channels}")
        
        demo_state["retailers"] = retailers
        demo_state["progress"] = 30
        
        # Step 4: Register SKUs
        demo_state["current_step"] = "Registering SKUs"
        add_log("\n--- Registering Product SKUs ---")
        
        skus = get_sku_configs()
        for sku in skus:
            orchestrator.register_sku(sku)
            margin = sku.unit_price - sku.unit_cost
            add_log(f"  ✓ {sku.sku_name}: ${sku.unit_price:.2f} (margin ${margin:.2f}), demand {sku.weekly_base_demand}/week")
        
        demo_state["skus"] = skus
        demo_state["progress"] = 40
        
        # Step 5: Initialize twin states
        demo_state["current_step"] = "Initializing Digital Twin"
        add_log("\n--- Initializing Digital Twin States ---")
        
        np.random.seed(42)
        state_count = 0
        for retailer in retailers:
            for sku in skus:
                demand_factor = 1.0 + np.random.uniform(-0.2, 0.3)
                orchestrator.initialize_twin_state(
                    retailer_id=retailer.retailer_id,
                    sku_id=sku.sku_id,
                    initial_inventory=sku.weekly_base_demand * retailer.avg_inventory_weeks,
                    base_demand_mean=sku.weekly_base_demand * demand_factor,
                    base_demand_std=sku.demand_std
                )
                state_count += 1
        
        add_log(f"  ✓ Initialized {state_count} retailer-SKU states")
        twin_summary = orchestrator.twin.get_state_summary()
        add_log(f"  ✓ Twin state summary: {twin_summary}")
        demo_state["progress"] = 50
        
        # Step 6: Federated learning
        demo_state["current_step"] = "Federated Bayesian Learning"
        add_log("\n" + "=" * 70)
        add_log("  FEDERATED BAYESIAN LEARNING")
        add_log("=" * 70)
        add_log("Each retailer contributes local spend/lift data to update posteriors...")
        
        np.random.seed(123)
        categories = ["beverages", "snacks"]
        
        for retailer in retailers:
            add_log(f"\n--- Retailer: {retailer.retailer_name} ---")
            
            for channel in retailer.available_channels:
                for category in categories:
                    n_weeks = 26
                    base_spend = 50000 if retailer.tier == "premium" else 25000
                    spend = np.random.uniform(0.5, 1.5, n_weeks) * base_spend
                    
                    true_elasticity = 0.15 + np.random.uniform(-0.05, 0.10)
                    noise = np.random.normal(0, 0.15, n_weeks)
                    lift = spend / 50000 * true_elasticity * (1 + noise)
                    lift = np.maximum(0.01, lift)
                    
                    posterior = orchestrator.update_elasticity_from_retailer_data(
                        retailer_id=retailer.retailer_id,
                        channel=channel,
                        category=category,
                        spend_history=spend,
                        sales_lift_history=lift
                    )
                    
                    add_log(f"  {channel.value}:{category} → η={posterior.mean:.3f} "
                           f"[{posterior.ci_lower:.3f}, {posterior.ci_upper:.3f}] "
                           f"(evidence: {posterior.evidence_strength:.0%})")
        
        demo_state["progress"] = 65
        
        # Step 7: Create current allocation
        demo_state["current_step"] = "Creating allocation"
        add_log("\n" + "=" * 70)
        add_log("  CURRENT ALLOCATION")
        add_log("=" * 70)
        
        total_budget = 10_000_000
        
        spend = {}
        total_min_share = sum(r.min_spend_share for r in retailers)
        for retailer in retailers:
            retailer_budget = total_budget * (retailer.min_spend_share / total_min_share)
            n_channels = len(retailer.available_channels)
            channel_budget = retailer_budget / n_channels
            spend[retailer.retailer_id] = {
                c.value: channel_budget for c in retailer.available_channels
            }
        
        current_allocation = MediaAllocation(
            allocation_id="current-q1-2024",
            name="Current Q1 2024 Allocation",
            total_budget=total_budget,
            period_weeks=13,
            spend_by_retailer_channel=spend,
            status=AllocationStatus.ACTIVE
        )
        
        add_log(f"Total Budget: ${total_budget/1e6:.1f}M for {current_allocation.period_weeks} weeks")
        add_log("\nCurrent spend by retailer:")
        for retailer_id, channels in current_allocation.spend_by_retailer_channel.items():
            total = sum(channels.values())
            add_log(f"  {retailer_id}: ${total/1e6:.2f}M")
        
        demo_state["progress"] = 75
        
        # Step 8: Generate conversion paths and run pipeline
        demo_state["current_step"] = "Running optimization pipeline"
        add_log("\n" + "=" * 70)
        add_log("  RUNNING OPTIMIZATION PIPELINE")
        add_log("=" * 70)
        add_log("Executing: Bayesian → Twin → Agents...")
        
        np.random.seed(456)
        channels_list = [c.value for c in MediaChannel]
        conversion_paths = []
        for _ in range(500):
            path_length = np.random.choice([1, 2, 3, 4], p=[0.3, 0.35, 0.25, 0.1])
            path = list(np.random.choice(channels_list, size=path_length, replace=True))
            conversion_paths.append(path)
        
        spend_history = {
            c.value: current_allocation.get_channel_total(c.value)
            for c in MediaChannel
        }
        total_incremental_sales = 45_000_000
        
        add_log(f"\nAnalyzing {len(conversion_paths)} conversion paths...")
        add_log(f"Total incremental sales: ${total_incremental_sales/1e6:.1f}M")
        
        decision_pack = orchestrator.run_pipeline(
            current_allocation=current_allocation,
            total_budget=total_budget,
            period_weeks=13,
            conversion_paths=conversion_paths,
            spend_history=spend_history,
            total_incremental_sales=total_incremental_sales
        )
        
        demo_state["decision_pack"] = decision_pack
        demo_state["progress"] = 90
        
        # Step 9: Display results
        demo_state["current_step"] = "Generating results"
        add_log("\n" + "=" * 70)
        add_log("  DECISION PACK RESULTS")
        add_log("=" * 70)
        
        add_log("\n--- Pipeline Steps ---")
        for step in orchestrator.pipeline_steps:
            status_icon = "✓" if step.status == "completed" else "✗"
            add_log(f"  {status_icon} {step.step_name}: {step.result_summary}")
        
        add_log("\n--- Recommended Allocation ---")
        rec = decision_pack.recommended_allocation
        add_log(f"Allocation ID: {rec.allocation_id}")
        add_log(f"Total Budget: ${rec.total_budget/1e6:.1f}M")
        add_log("\nRecommended spend by retailer:")
        for retailer_id, channels in rec.spend_by_retailer_channel.items():
            total = sum(channels.values())
            add_log(f"  {retailer_id}: ${total/1e6:.2f}M")
        
        add_log("\n--- Scenario Comparison ---")
        add_log(f"{'Scenario':<25} {'E[Sales]':>12} {'ROAS':>8} {'Stockout':>10}")
        add_log("-" * 55)
        for scenario_id, result in decision_pack.simulation_results.items():
            add_log(f"{result.scenario_name:<25} ${result.expected_incremental_sales/1e6:>10.1f}M "
                   f"{result.expected_roas:>7.1f}x {result.expected_stockout_rate:>9.1%}")
        
        add_log("\n--- Confidence Metrics ---")
        add_log(f"Overall Confidence: {decision_pack.overall_confidence:.1%}")
        add_log(f"Data Quality Score: {decision_pack.data_quality_score:.1%}")
        
        add_log("\n" + "=" * 70)
        add_log("  EXECUTIVE SUMMARY")
        add_log("=" * 70)
        add_log(decision_pack.executive_summary)
        
        demo_state["progress"] = 100
        demo_state["status"] = "completed"
        demo_state["current_step"] = "Demo complete"
        add_log("\n✅ Demo completed successfully!")
        
        return {
            "status": "success",
            "message": "Demo completed successfully",
            "pack_id": decision_pack.pack_id
        }
        
    except Exception as e:
        demo_state["status"] = "error"
        demo_state["current_step"] = f"Error: {str(e)}"
        add_log(f"❌ Demo failed: {str(e)}", "error")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/demo/results")
async def get_demo_results():
    """Get the current demo results"""
    if demo_state["decision_pack"] is None:
        raise HTTPException(status_code=404, detail="No demo results available. Run the demo first.")
    
    decision_pack = demo_state["decision_pack"]
    orchestrator = demo_state["orchestrator"]
    
    # Build response with all the data needed for the UI
    return {
        "status": demo_state["status"],
        "pack_id": decision_pack.pack_id,
        "created_at": decision_pack.created_at.isoformat() if decision_pack.created_at else None,
        
        # Bayesian model data
        "bayesian": {
            "overall_confidence": decision_pack.overall_confidence,
            "data_quality_score": decision_pack.data_quality_score,
            "posteriors": [
                {
                    "key": key,
                    "mean": post.mean,
                    "ci_lower": post.ci_lower,
                    "ci_upper": post.ci_upper,
                    "n_observations": post.n_observations,
                    "evidence_strength": post.evidence_strength
                }
                for key, post in orchestrator.bayesian_engine.federated_aggregator.get_all_global_posteriors().items()
            ] if orchestrator else []
        },
        
        # Digital Twin data
        "digital_twin": {
            "summary": orchestrator.twin.get_state_summary() if orchestrator else {},
            "states": [
                {
                    "retailer_id": state.retailer_id,
                    "sku_id": state.sku_id,
                    "inventory": state.current_inventory,
                    "demand_mean": state.base_demand_mean,
                    "demand_std": state.base_demand_std,
                    "weeks_of_supply": state.current_inventory / state.base_demand_mean if state.base_demand_mean > 0 else 0
                }
                for state in (orchestrator.twin.states.values() if orchestrator else [])
            ]
        },
        
        # Pipeline/orchestration data
        "orchestration": {
            "steps": [
                {
                    "step_name": step.step_name,
                    "status": step.status,
                    "result_summary": step.result_summary,
                    "started_at": step.started_at.isoformat() if step.started_at else None,
                    "completed_at": step.completed_at.isoformat() if step.completed_at else None
                }
                for step in (orchestrator.pipeline_steps if orchestrator else [])
            ]
        },
        
        # Allocation data
        "allocation": {
            "current": {
                "allocation_id": "current-q1-2024",
                "total_budget": 10_000_000,
                "spend_by_retailer": decision_pack.current_allocation.spend_by_retailer_channel if decision_pack.current_allocation else {}
            },
            "recommended": {
                "allocation_id": decision_pack.recommended_allocation.allocation_id,
                "total_budget": decision_pack.recommended_allocation.total_budget,
                "spend_by_retailer": decision_pack.recommended_allocation.spend_by_retailer_channel
            }
        },
        
        # Scenario simulation results
        "scenarios": [
            {
                "scenario_id": scenario_id,
                "scenario_name": result.scenario_name,
                "expected_sales": result.expected_incremental_sales,
                "sales_ci_lower": result.sales_ci_lower,
                "sales_ci_upper": result.sales_ci_upper,
                "expected_roas": result.expected_roas,
                "stockout_rate": result.expected_stockout_rate
            }
            for scenario_id, result in decision_pack.simulation_results.items()
        ],
        
        # Governance
        "governance": {
            "status": decision_pack.governance_decision.status.value if decision_pack.governance_decision else None,
            "approved": decision_pack.governance_decision.approved if decision_pack.governance_decision else None,
            "checks": [
                {
                    "rule_name": check.rule_name,
                    "passed": check.passed,
                    "message": check.message
                }
                for check in (decision_pack.governance_decision.checks[:5] if decision_pack.governance_decision else [])
            ]
        },
        
        # Executive summary
        "executive_summary": decision_pack.executive_summary,
        "uncertainty_acknowledgment": decision_pack.uncertainty_acknowledgment
    }


@app.get("/api/demo/retailers")
async def get_retailers():
    """Get retailer configurations"""
    return {
        "retailers": [
            {
                "retailer_id": r.retailer_id,
                "retailer_name": r.retailer_name,
                "tier": r.tier,
                "channels": [c.value for c in r.available_channels],
                "min_spend_share": r.min_spend_share,
                "avg_inventory_weeks": r.avg_inventory_weeks
            }
            for r in get_retailer_configs()
        ]
    }


@app.get("/api/demo/channels")
async def get_channels():
    """Get channel configurations"""
    return {
        "channels": [
            {
                "channel": c.channel.value,
                "prior_elasticity_mean": c.prior_elasticity_mean,
                "prior_elasticity_std": c.prior_elasticity_std,
                "adstock_decay": c.adstock_decay
            }
            for c in get_channel_configs()
        ]
    }


@app.get("/api/demo/skus")
async def get_skus():
    """Get SKU configurations"""
    return {
        "skus": [
            {
                "sku_id": s.sku_id,
                "sku_name": s.sku_name,
                "category": s.category,
                "brand": s.brand,
                "unit_price": s.unit_price,
                "unit_cost": s.unit_cost,
                "margin": s.unit_price - s.unit_cost,
                "weekly_base_demand": s.weekly_base_demand
            }
            for s in get_sku_configs()
        ]
    }


# ============================================================================
# UI PAGE DATA ENDPOINTS
# These endpoints return data structured exactly as the UI pages expect
# ============================================================================

@app.get("/api/ui/bayesian")
async def get_bayesian_page_data():
    """
    Get data for BayesianModelPage in the exact format it expects:
    - bayesianPredictions: channel elasticity predictions
    - modelParameters: prior/posterior parameter comparison
    - federatedNodes: retailers as federated learning nodes
    - posteriorConvergenceData: convergence over iterations
    """
    orchestrator = demo_state.get("orchestrator")
    decision_pack = demo_state.get("decision_pack")
    
    # Get channel configs for priors
    channel_configs = {c.channel.value: c for c in get_channel_configs()}
    
    # Build bayesianPredictions from channel posteriors
    bayesian_predictions = []
    if orchestrator:
        posteriors = orchestrator.bayesian_engine.federated_aggregator.get_all_global_posteriors()
        seen_channels = set()
        for key, post in posteriors.items():
            channel = key.split(":")[0] if ":" in key else key
            if channel not in seen_channels:
                seen_channels.add(channel)
                prior_config = channel_configs.get(channel)
                prior_mean = prior_config.prior_elasticity_mean if prior_config else 0.15
                bayesian_predictions.append({
                    "id": f"pred-{channel}",
                    "timestamp": datetime.now().isoformat(),
                    "metric": f"{channel.replace('_', ' ').title()} Elasticity",
                    "predictedValue": round(post.mean, 3),
                    "confidenceInterval": [round(post.ci_lower, 3), round(post.ci_upper, 3)],
                    "probability": min(0.99, post.evidence_strength),
                    "priorMean": prior_mean,
                    "posteriorMean": round(post.mean, 3),
                    "uncertainty": round((post.ci_upper - post.ci_lower) / 2, 4),
                })
    else:
        # Default predictions from channel configs
        for i, (channel, config) in enumerate(channel_configs.items()):
            bayesian_predictions.append({
                "id": f"pred-{i+1}",
                "timestamp": datetime.now().isoformat(),
                "metric": f"{channel.replace('_', ' ').title()} Elasticity",
                "predictedValue": config.prior_elasticity_mean,
                "confidenceInterval": [
                    config.prior_elasticity_mean - 2*config.prior_elasticity_std,
                    config.prior_elasticity_mean + 2*config.prior_elasticity_std
                ],
                "probability": 0.5,
                "priorMean": config.prior_elasticity_mean,
                "posteriorMean": config.prior_elasticity_mean,
                "uncertainty": config.prior_elasticity_std,
            })
    
    # Build modelParameters
    model_parameters = []
    for channel, config in channel_configs.items():
        posterior_mean = config.prior_elasticity_mean
        if orchestrator:
            posteriors = orchestrator.bayesian_engine.federated_aggregator.get_all_global_posteriors()
            for key, post in posteriors.items():
                if key.startswith(channel):
                    posterior_mean = post.mean
                    break
        
        model_parameters.append({
            "name": f"η ({channel.replace('_', ' ')})",
            "prior": config.prior_elasticity_mean,
            "posterior": round(posterior_mean, 3),
            "credibleInterval": [
                round(posterior_mean - config.prior_elasticity_std, 3),
                round(posterior_mean + config.prior_elasticity_std, 3)
            ]
        })
    
    # Build federatedNodes from retailers
    retailers = get_retailer_configs()
    federated_nodes = []
    for i, retailer in enumerate(retailers):
        # Simulate sample counts based on tier
        base_samples = 15000 if retailer.tier == "premium" else 8000
        samples = int(base_samples * (1 + np.random.uniform(-0.2, 0.3)))
        
        federated_nodes.append({
            "id": retailer.retailer_id,
            "name": retailer.retailer_name,
            "location": f"{len(retailer.available_channels)} channels",
            "status": "active" if i < 3 else ("syncing" if i == 3 else "active"),
            "lastSync": f"{np.random.randint(1, 5)} min ago",
            "localSamples": samples,
            "contribution": round(retailer.min_spend_share / sum(r.min_spend_share for r in retailers), 2)
        })
    
    # Build posteriorConvergenceData
    base_prior = 0.15
    final_posterior = 0.18 if not orchestrator else np.mean([p.mean for p in orchestrator.bayesian_engine.federated_aggregator.get_all_global_posteriors().values()])
    
    posterior_convergence = []
    for iteration in range(0, 801, 100):
        progress = iteration / 700
        posterior = base_prior + (final_posterior - base_prior) * min(1.0, progress * 1.2)
        uncertainty = 0.06 * (1 - progress * 0.5)
        posterior_convergence.append({
            "iteration": iteration,
            "prior": base_prior,
            "posterior": round(posterior, 3),
            "lower": round(posterior - uncertainty, 3),
            "upper": round(posterior + uncertainty, 3)
        })
    
    # Aggregation summary
    total_samples = sum(n["localSamples"] for n in federated_nodes)
    
    return {
        "bayesianPredictions": bayesian_predictions[:4],  # Limit to 4 for grid
        "modelParameters": model_parameters[:4],
        "federatedNodes": federated_nodes,
        "posteriorConvergenceData": posterior_convergence,
        "aggregationSummary": {
            "totalSamples": total_samples,
            "activeNodes": len([n for n in federated_nodes if n["status"] == "active"]),
            "syncRounds": 12 if orchestrator else 0,
            "modelUncertainty": round(decision_pack.data_quality_score if decision_pack else 0.5, 2)
        }
    }


@app.get("/api/ui/digital-twin")
async def get_digital_twin_page_data():
    """
    Get data for DigitalTwinPage in the exact format it expects:
    - devices: retailer-SKU states as devices
    - twinActivities: recent twin state changes
    - telemetryHistory: inventory/demand time series
    """
    orchestrator = demo_state.get("orchestrator")
    retailers = get_retailer_configs()
    skus = get_sku_configs()
    
    # Map retailer to device type
    device_type_map = {
        "walmart": "compressor",
        "kroger": "pump",
        "target": "hvac",
        "costco": "valve",
        "albertsons": "sensor"
    }
    
    # Build devices from retailer-SKU twin states
    devices = []
    if orchestrator and orchestrator.twin.states:
        # Group by retailer, show aggregate metrics
        retailer_states = {}
        for state_key, state in orchestrator.twin.states.items():
            # Handle both dict and object access
            if isinstance(state, dict):
                retailer_id = state.get("retailer_id", state_key.split("_")[0] if "_" in state_key else state_key)
            else:
                retailer_id = state.retailer_id
            if retailer_id not in retailer_states:
                retailer_states[retailer_id] = []
            retailer_states[retailer_id].append(state)
        
        for retailer in retailers:
            states = retailer_states.get(retailer.retailer_id, [])
            if not states:
                continue
            
            total_inventory = sum(s.get("current_inventory", 0) if isinstance(s, dict) else s.current_inventory for s in states)
            total_demand = sum(s.get("base_demand_mean", 0) if isinstance(s, dict) else s.base_demand_mean for s in states)
            weeks_supply = total_inventory / total_demand if total_demand > 0 else 0
            
            # Determine status based on inventory health
            if weeks_supply < 2:
                status = "warning"
            elif weeks_supply < 1:
                status = "critical"
            else:
                status = "normal"
            
            devices.append({
                "id": retailer.retailer_id,
                "name": f"{retailer.retailer_name}",
                "type": device_type_map.get(retailer.retailer_id, "sensor"),
                "status": status,
                "location": f"{len(retailer.available_channels)} channels, {retailer.tier}",
                "lastUpdate": f"{np.random.randint(5, 30)} sec ago",
                "metrics": [
                    {
                        "name": "Total Marketing Spend",
                        "value": round(total_inventory),
                        "unit": "$K",
                        "threshold": {"min": total_demand * 2},
                        "trend": "stable"
                    },
                    {
                        "name": "Search",
                        "value": round(total_demand),
                        "unit": "$K/wk",
                        "trend": "up" if np.random.random() > 0.5 else "stable"
                    },
                    {
                        "name": "Revenue",
                        "value": round(weeks_supply, 1),
                        "unit": "$M",
                        "threshold": {"min": 2, "max": 8},
                        "trend": "stable"
                    },
                    {
                        "name": "Display",
                        "value": len(states),
                        "unit": "$K",
                        "trend": "stable"
                    }
                ]
            })
    else:
        # Default devices from retailers
        for retailer in retailers:
            devices.append({
                "id": retailer.retailer_id,
                "name": f"{retailer.retailer_name}",
                "type": device_type_map.get(retailer.retailer_id, "sensor"),
                "status": "normal",
                "location": f"{len(retailer.available_channels)} channels, {retailer.tier}",
                "lastUpdate": "-- sec ago",
                "metrics": [
                    {"name": "Total Marketing Spend", "value": 0, "unit": "$K", "trend": "stable"},
                    {"name": "Search", "value": 0, "unit": "$K/wk", "trend": "stable"},
                    {"name": "Revenue", "value": 0, "unit": "$M", "trend": "stable"},
                    {"name": "Display", "value": 4, "unit": "$K", "trend": "stable"}
                ]
            })
    
    # Build twinActivities from demo logs
    activities = []
    activity_id = 0
    for log in demo_state.get("logs", [])[-20:]:
        msg = log.get("message", "")
        if "Twin" in msg or "inventory" in msg.lower() or "state" in msg.lower():
            activity_id += 1
            activities.append({
                "id": f"act-{activity_id}",
                "timestamp": log.get("timestamp", "")[-8:],
                "type": "telemetry" if "state" in msg.lower() else "action",
                "deviceId": "system",
                "message": msg[:100],
                "severity": "info"
            })
    
    # Add some default activities if none from logs
    if not activities:
        activities = [
            {"id": "act-1", "timestamp": datetime.now().strftime("%H:%M:%S"), "type": "telemetry", "deviceId": "walmart", "message": "Inventory state synchronized", "severity": "info"},
            {"id": "act-2", "timestamp": datetime.now().strftime("%H:%M:%S"), "type": "telemetry", "deviceId": "kroger", "message": "Demand forecast updated", "severity": "info"},
            {"id": "act-3", "timestamp": datetime.now().strftime("%H:%M:%S"), "type": "action", "deviceId": "system", "message": "Twin states initialized for 20 retailer-SKU pairs", "severity": "info"},
        ]
    
    # Build telemetryHistory (inventory over weeks)
    telemetry_history = []
    for week in range(13):
        base_inventory = 1000
        demand_variation = np.sin(week / 2) * 100
        telemetry_history.append({
            "time": f"Week {week + 1}",
            "inventory": int(base_inventory - week * 50 + demand_variation),
            "demand": int(150 + np.random.uniform(-20, 30)),
            "threshold_inventory": 500
        })
    
    return {
        "devices": devices[:4],  # Limit to 4 for grid
        "twinActivities": activities[-6:],  # Last 6 activities
        "telemetryHistory": telemetry_history
    }


@app.get("/api/ui/orchestration")
async def get_orchestration_page_data():
    """
    Get data for OrchestrationPage in the exact format it expects:
    - agents: pipeline agents
    - agentActions: recent agent actions
    - orchestrationSteps: pipeline workflow steps
    - currentCase: current allocation/decision context
    """
    orchestrator = demo_state.get("orchestrator")
    decision_pack = demo_state.get("decision_pack")
    
    # Define the pipeline agents
    agents = [
        {"id": "agent-1", "name": "Attribution Agent", "role": "Channel Attribution", "status": "idle", "avatar": "📊", "description": "Calculates multi-touch attribution using Shapley values"},
        {"id": "agent-2", "name": "Scenario Agent", "role": "Scenario Generation", "status": "idle", "avatar": "🎭", "description": "Generates allocation scenarios for simulation"},
        {"id": "agent-3", "name": "Simulation Agent", "role": "Twin Simulation", "status": "idle", "avatar": "🔮", "description": "Runs Monte Carlo simulations on Digital Twin"},
        {"id": "agent-4", "name": "Optimization Agent", "role": "Budget Optimization", "status": "idle", "avatar": "🎯", "description": "Optimizes allocation based on simulation results"},
        {"id": "agent-5", "name": "Governance Agent", "role": "Policy Validation", "status": "idle", "avatar": "🛡️", "description": "Validates recommendations against business rules"},
        {"id": "agent-6", "name": "Rationale Agent", "role": "Explanation Generation", "status": "idle", "avatar": "📝", "description": "Generates human-readable explanations"},
    ]
    
    # Define orchestration steps mapping to pipeline
    step_names = ["Attribution", "Scenarios", "Simulate", "Optimize", "Govern", "Explain"]
    step_agents = [
        ["Attribution Agent"],
        ["Scenario Agent"],
        ["Simulation Agent"],
        ["Optimization Agent"],
        ["Governance Agent"],
        ["Rationale Agent"]
    ]
    
    orchestration_steps = []
    if orchestrator and orchestrator.pipeline_steps:
        for i, step in enumerate(orchestrator.pipeline_steps):
            status = "completed" if step.status == "completed" else ("active" if step.status == "running" else "pending")
            orchestration_steps.append({
                "id": f"step-{i+1}",
                "name": step.step_name.replace("_", " ").title(),
                "agents": step_agents[i] if i < len(step_agents) else ["Agent"],
                "status": status,
                "startTime": step.started_at.isoformat() if step.started_at else None,
                "endTime": step.completed_at.isoformat() if step.completed_at else None
            })
            # Update agent status based on step
            if i < len(agents):
                agents[i]["status"] = "completed" if status == "completed" else ("processing" if status == "active" else "idle")
    else:
        for i, name in enumerate(step_names):
            orchestration_steps.append({
                "id": f"step-{i+1}",
                "name": name,
                "agents": step_agents[i],
                "status": "pending"
            })
    
    # Build agent actions from pipeline steps
    agent_actions = []
    action_id = 0
    if orchestrator and orchestrator.pipeline_steps:
        for step in orchestrator.pipeline_steps:
            if step.status == "completed":
                action_id += 1
                agent_actions.append({
                    "id": f"action-{action_id}",
                    "agentId": f"agent-{action_id}",
                    "agentName": step.step_name.replace("_", " ").title() + " Agent",
                    "timestamp": step.completed_at.strftime("%H:%M:%S") if step.completed_at else "--:--:--",
                    "action": step.result_summary[:50] if step.result_summary else "Processing...",
                    "target": "pipeline",
                    "status": "completed",
                    "duration": int((step.completed_at - step.started_at).total_seconds() * 1000) if step.completed_at and step.started_at else None
                })
    
    # Build current case from decision pack
    if decision_pack:
        current_case = {
            "id": decision_pack.pack_id,
            "title": "Q1 2024 Media Optimization",
            "status": "complete" if demo_state["status"] == "completed" else "in_progress",
            "priority": "high",
            "createdAt": decision_pack.created_at.isoformat() if decision_pack.created_at else None,
            "assignedAgents": [a["name"] for a in agents if a["status"] == "completed"],
            "alerts": len(decision_pack.simulation_results),
            "hypotheses": len(decision_pack.simulation_results),
            "totalBudget": decision_pack.recommended_allocation.total_budget if decision_pack.recommended_allocation else 10_000_000,
            "confidence": decision_pack.overall_confidence
        }
    else:
        current_case = {
            "id": "PENDING",
            "title": "Awaiting Demo Run",
            "status": "pending",
            "priority": "medium",
            "assignedAgents": [],
            "alerts": 0,
            "hypotheses": 0,
            "totalBudget": 10_000_000,
            "confidence": 0
        }
    
    # Governance info
    governance = {
        "autonomyLevel": "AUTO_LOW_RISK",
        "policyChecks": {"passed": 5, "total": 5},
        "pendingApprovals": 0,
        "auditEntries": len(agent_actions)
    }
    if decision_pack and decision_pack.governance_decision:
        gov = decision_pack.governance_decision
        passed = len([c for c in gov.checks if c.passed])
        governance = {
            "autonomyLevel": gov.status.value if gov.status else "PENDING",
            "policyChecks": {"passed": passed, "total": len(gov.checks)},
            "pendingApprovals": 0 if gov.approved else 1,
            "auditEntries": len(gov.checks)
        }
    
    return {
        "agents": agents,
        "agentActions": agent_actions,
        "orchestrationSteps": orchestration_steps,
        "currentCase": current_case,
        "governance": governance
    }


@app.get("/api/ui/agent-output")
async def get_agent_output_page_data():
    """
    Get data for AgentOutputPage in the exact format it expects:
    - agentOutputs: agent outputs with rationale and evidence
    - agents: same as orchestration agents
    """
    orchestrator = demo_state.get("orchestrator")
    decision_pack = demo_state.get("decision_pack")
    
    # Define agents (same as orchestration)
    agents = [
        {"id": "agent-1", "name": "Attribution Agent", "role": "Channel Attribution", "status": "completed" if decision_pack else "idle", "avatar": "📊"},
        {"id": "agent-2", "name": "Scenario Agent", "role": "Scenario Generation", "status": "completed" if decision_pack else "idle", "avatar": "🎭"},
        {"id": "agent-3", "name": "Simulation Agent", "role": "Twin Simulation", "status": "completed" if decision_pack else "idle", "avatar": "🔮"},
        {"id": "agent-4", "name": "Optimization Agent", "role": "Budget Optimization", "status": "completed" if decision_pack else "idle", "avatar": "🎯"},
        {"id": "agent-5", "name": "Governance Agent", "role": "Policy Validation", "status": "completed" if decision_pack else "idle", "avatar": "🛡️"},
        {"id": "agent-6", "name": "Rationale Agent", "role": "Explanation Generation", "status": "completed" if decision_pack else "idle", "avatar": "📝"},
    ]
    
    agent_outputs = []
    
    if decision_pack:
        # Attribution Agent output
        agent_outputs.append({
            "id": "output-1",
            "agentId": "agent-1",
            "agentName": "Attribution Agent",
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "outputType": "analysis",
            "title": "Multi-Touch Attribution Complete",
            "summary": "Calculated Shapley values for all channels across retailers",
            "details": "Analyzed 500 conversion paths using game-theoretic Shapley value attribution. Sponsored search shows highest marginal contribution, followed by in-store display. Connected TV shows strong assist value but lower last-touch attribution.",
            "confidence": 0.92,
            "rationale": [
                {"step": 1, "description": "Path Collection", "reasoning": "Collected 500 conversion paths from all retailers", "confidence": 1.0},
                {"step": 2, "description": "Shapley Calculation", "reasoning": "Computed marginal contribution for each channel in each coalition", "confidence": 0.95},
                {"step": 3, "description": "Cross-Retailer Normalization", "reasoning": "Normalized attribution weights across retailers by spend share", "confidence": 0.88},
            ],
            "evidence": [
                {"type": "data", "source": "Conversion Paths", "description": "500 multi-touch paths analyzed", "weight": 0.9},
                {"type": "model", "source": "Shapley Values", "description": "Game-theoretic fair attribution", "weight": 0.95},
                {"type": "rule", "source": "Business Rules", "description": "Minimum 7-day attribution window", "weight": 0.8},
            ]
        })
        
        # Scenario Agent output
        scenarios = list(decision_pack.simulation_results.values())
        agent_outputs.append({
            "id": "output-2",
            "agentId": "agent-2",
            "agentName": "Scenario Agent",
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "outputType": "recommendation",
            "title": f"Generated {len(scenarios)} Optimization Scenarios",
            "summary": f"Created allocation scenarios ranging from conservative to aggressive growth",
            "details": f"Generated {len(scenarios)} distinct scenarios: " + ", ".join([s.scenario_name for s in scenarios[:3]]) + ". Each scenario varies channel mix and retailer allocation based on elasticity posteriors and inventory constraints.",
            "confidence": 0.88,
            "rationale": [
                {"step": 1, "description": "Baseline Analysis", "reasoning": "Analyzed current allocation efficiency", "confidence": 0.95},
                {"step": 2, "description": "Constraint Mapping", "reasoning": "Mapped retailer min-spend and inventory constraints", "confidence": 0.9},
                {"step": 3, "description": "Scenario Generation", "reasoning": "Generated scenarios using Latin hypercube sampling", "confidence": 0.85},
            ],
            "evidence": [
                {"type": "data", "source": "Current Allocation", "description": "$10M quarterly budget baseline", "weight": 0.9},
                {"type": "model", "source": "Bayesian Posteriors", "description": "Channel elasticity estimates", "weight": 0.95},
                {"type": "history", "source": "Historical Performance", "description": "26 weeks of spend/lift data", "weight": 0.85},
            ]
        })
        
        # Optimization Agent output
        best_scenario = max(scenarios, key=lambda s: s.expected_roas) if scenarios else None
        if best_scenario:
            agent_outputs.append({
                "id": "output-3",
                "agentId": "agent-4",
                "agentName": "Optimization Agent",
                "timestamp": datetime.now().strftime("%H:%M:%S"),
                "outputType": "decision",
                "title": f"Recommended: {best_scenario.scenario_name}",
                "summary": f"Expected ROAS: {best_scenario.expected_roas:.1f}x with {best_scenario.expected_stockout_rate:.1%} stockout risk",
                "details": f"Selected {best_scenario.scenario_name} as optimal allocation. Expected incremental sales: ${best_scenario.expected_incremental_sales/1e6:.1f}M (90% CI: ${best_scenario.sales_ci_lower/1e6:.1f}M - ${best_scenario.sales_ci_upper/1e6:.1f}M). This scenario maximizes ROAS while keeping stockout risk below threshold.",
                "confidence": decision_pack.overall_confidence,
                "rationale": [
                    {"step": 1, "description": "Simulation Analysis", "reasoning": f"Ran 1000 Monte Carlo simulations per scenario", "confidence": 0.92},
                    {"step": 2, "description": "ROAS Optimization", "reasoning": f"Selected scenario with highest risk-adjusted ROAS", "confidence": 0.88},
                    {"step": 3, "description": "Constraint Validation", "reasoning": "Verified all retailer and inventory constraints met", "confidence": 0.95},
                ],
                "evidence": [
                    {"type": "model", "source": "Monte Carlo Simulation", "description": f"1000 simulations, {best_scenario.expected_roas:.1f}x median ROAS", "weight": 0.95},
                    {"type": "data", "source": "Digital Twin", "description": f"Stockout rate: {best_scenario.expected_stockout_rate:.1%}", "weight": 0.9},
                    {"type": "rule", "source": "Business Constraints", "description": "All min-spend requirements satisfied", "weight": 0.85},
                ]
            })
        
        # Governance Agent output
        if decision_pack.governance_decision:
            gov = decision_pack.governance_decision
            agent_outputs.append({
                "id": "output-4",
                "agentId": "agent-5",
                "agentName": "Governance Agent",
                "timestamp": datetime.now().strftime("%H:%M:%S"),
                "outputType": "action",
                "title": f"Governance Check: {'APPROVED' if gov.approved else 'ESCALATED'}",
                "summary": f"Validated {len(gov.checks)} policy rules, {len([c for c in gov.checks if c.passed])} passed",
                "details": "Performed comprehensive governance validation including budget limits, retailer commitments, risk thresholds, and compliance requirements. " + (f"Escalation reason: {gov.escalation_reason}" if gov.escalation_reason else "All checks passed."),
                "confidence": 0.98,
                "rationale": [
                    {"step": 1, "description": "Budget Validation", "reasoning": "Verified total spend within approved limits", "confidence": 1.0},
                    {"step": 2, "description": "Constraint Check", "reasoning": "Validated retailer min-spend commitments", "confidence": 0.98},
                    {"step": 3, "description": "Risk Assessment", "reasoning": "Evaluated stockout and ROAS risk thresholds", "confidence": 0.95},
                ],
                "evidence": [
                    {"type": "rule", "source": "Policy Engine", "description": f"{len([c for c in gov.checks if c.passed])}/{len(gov.checks)} rules passed", "weight": 0.95},
                    {"type": "data", "source": "Simulation Results", "description": "Risk metrics within tolerance", "weight": 0.9},
                ]
            })
        
        # Rationale Agent output
        agent_outputs.append({
            "id": "output-5",
            "agentId": "agent-6",
            "agentName": "Rationale Agent",
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "outputType": "analysis",
            "title": "Executive Summary Generated",
            "summary": "Created human-readable explanation of recommendation",
            "details": decision_pack.executive_summary[:500] + "..." if len(decision_pack.executive_summary) > 500 else decision_pack.executive_summary,
            "confidence": 0.95,
            "rationale": [
                {"step": 1, "description": "Key Insight Extraction", "reasoning": "Identified top 3 drivers of recommendation", "confidence": 0.95},
                {"step": 2, "description": "Uncertainty Quantification", "reasoning": "Documented confidence intervals and assumptions", "confidence": 0.92},
                {"step": 3, "description": "Narrative Generation", "reasoning": "Created stakeholder-appropriate explanation", "confidence": 0.95},
            ],
            "evidence": [
                {"type": "model", "source": "Decision Pack", "description": "Complete analysis artifacts", "weight": 0.95},
                {"type": "data", "source": "Simulation Results", "description": "Statistical summaries", "weight": 0.9},
            ]
        })
    else:
        # Default output when no demo has run
        agent_outputs.append({
            "id": "output-0",
            "agentId": "agent-1",
            "agentName": "System",
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "outputType": "analysis",
            "title": "Awaiting Demo Execution",
            "summary": "Run the demo to see agent outputs with full rationale",
            "details": "The agent output page will display detailed analysis, recommendations, and decisions from each pipeline agent once the demo is executed. Each output includes a full reasoning chain and supporting evidence.",
            "confidence": 1.0,
            "rationale": [
                {"step": 1, "description": "Initialization", "reasoning": "System ready for demo execution", "confidence": 1.0},
            ],
            "evidence": []
        })
    
    return {
        "agentOutputs": agent_outputs,
        "agents": agents
    }


# ============================================================================
# DEMAND & PROCUREMENT ENDPOINTS
# ============================================================================

# D&P Global state
dp_state = {
    "orchestrator": None,
    "decision_pack": None,
    "logs": [],
    "status": "idle",
    "progress": 0,
    "current_step": "",
    "config": None,
}


def get_dp_sku_configs():
    """Get D&P SKU configurations"""
    from vendor.agents.ecosystems.demand_procurement.schemas import ServiceLevel
    return [
        {"sku_id": "SKU-001", "sku_name": "Widget A", "category": "Widgets", "unit_cost": 25.0, "lead_time_days": 7, "current_inventory": 500, "service_level": ServiceLevel.SILVER},
        {"sku_id": "SKU-002", "sku_name": "Widget B", "category": "Widgets", "unit_cost": 45.0, "lead_time_days": 10, "current_inventory": 300, "service_level": ServiceLevel.SILVER},
        {"sku_id": "SKU-003", "sku_name": "Gadget X", "category": "Gadgets", "unit_cost": 120.0, "lead_time_days": 14, "current_inventory": 150, "service_level": ServiceLevel.GOLD},
        {"sku_id": "SKU-004", "sku_name": "Gadget Y", "category": "Gadgets", "unit_cost": 85.0, "lead_time_days": 12, "current_inventory": 200, "service_level": ServiceLevel.SILVER},
        {"sku_id": "SKU-005", "sku_name": "Component Z", "category": "Components", "unit_cost": 15.0, "lead_time_days": 5, "current_inventory": 1000, "service_level": ServiceLevel.BRONZE},
    ]


def get_dp_supplier_configs():
    """Get D&P supplier configurations"""
    from vendor.agents.ecosystems.demand_procurement.schemas import SupplierTier
    return [
        {"supplier_id": "SUP-001", "supplier_name": "Acme Supplies", "tier": SupplierTier.STRATEGIC, "avg_lead_time_days": 7, "sku_ids": ["SKU-001", "SKU-002"], "on_time_delivery_rate": 0.95, "quality_score": 0.92},
        {"supplier_id": "SUP-002", "supplier_name": "Global Parts", "tier": SupplierTier.PREFERRED, "avg_lead_time_days": 14, "sku_ids": ["SKU-003", "SKU-004"], "on_time_delivery_rate": 0.88, "quality_score": 0.90},
        {"supplier_id": "SUP-003", "supplier_name": "Quick Components", "tier": SupplierTier.APPROVED, "avg_lead_time_days": 5, "sku_ids": ["SKU-005"], "on_time_delivery_rate": 0.92, "quality_score": 0.85},
    ]


@app.get("/api/dp/status")
async def get_dp_status():
    """Get D&P demo status"""
    return {
        "status": dp_state["status"],
        "progress": dp_state["progress"],
        "current_step": dp_state["current_step"],
        "has_results": dp_state["decision_pack"] is not None
    }


@app.get("/api/dp/logs")
async def get_dp_logs():
    """Get D&P logs"""
    return {"logs": dp_state["logs"]}


@app.get("/api/dp/config")
async def get_dp_config():
    """Get D&P configuration"""
    skus = get_dp_sku_configs()
    suppliers = get_dp_supplier_configs()
    return {
        "organization_id": "demo-org",
        "organization_name": "Demo Organization",
        "skus": [{"sku_id": s["sku_id"], "sku_name": s["sku_name"], "category": s["category"], "unit_cost": s["unit_cost"], "lead_time_days": s["lead_time_days"], "current_inventory": s["current_inventory"], "service_level": str(s["service_level"].value)} for s in skus],
        "suppliers": [{"supplier_id": s["supplier_id"], "supplier_name": s["supplier_name"], "tier": str(s["tier"].value), "avg_lead_time_days": s["avg_lead_time_days"], "sku_ids": s["sku_ids"]} for s in suppliers],
        "forecast_horizon_weeks": 13,
        "working_capital_limit": 500000
    }


@app.post("/api/dp/demo/run")
async def run_dp_demo():
    """Run the D&P demo pipeline"""
    global dp_state
    
    if dp_state["status"] == "running":
        raise HTTPException(status_code=400, detail="D&P Demo is already running")
    
    dp_state["status"] = "running"
    dp_state["progress"] = 0
    dp_state["logs"] = []
    
    def add_log(message: str, level: str = "info"):
        dp_state["logs"].append({
            "timestamp": datetime.now().isoformat(),
            "level": level,
            "message": message
        })
    
    try:
        from vendor.agents.ecosystems.demand_procurement import (
            create_demand_procurement_orchestrator,
            SKUConfig, SupplierConfig, ServiceLevel, SupplierTier
        )
        
        add_log("📦 DEMAND & PROCUREMENT OPTIMIZATION DEMO", "header")
        add_log("Forecast → Optimize → Risk → Simulate → Plan → Govern → Report Pipeline")
        dp_state["current_step"] = "Initializing orchestrator"
        dp_state["progress"] = 5
        
        # Get configs
        sku_configs = get_dp_sku_configs()
        supplier_configs = get_dp_supplier_configs()
        
        add_log("\n--- SKU Configuration ---")
        for sku in sku_configs:
            add_log(f"  ✓ {sku['sku_name']} ({sku['sku_id']}): ${sku['unit_cost']:.2f}, LT={sku['lead_time_days']}d, Inv={sku['current_inventory']}")
        dp_state["progress"] = 15
        
        add_log("\n--- Supplier Configuration ---")
        for sup in supplier_configs:
            add_log(f"  ✓ {sup['supplier_name']} ({sup['tier'].value}): LT={sup['avg_lead_time_days']}d, OTD={sup['on_time_delivery_rate']:.0%}")
        dp_state["progress"] = 25
        
        # Create orchestrator
        dp_state["current_step"] = "Creating D&P orchestrator"
        add_log("\n--- Initializing D&P Orchestrator ---")
        
        orchestrator = create_demand_procurement_orchestrator(
            organization_id="demo-org",
            organization_name="Demo Organization",
            skus=sku_configs,
            suppliers=supplier_configs,
            forecast_horizon_weeks=13,
            working_capital_limit=500000
        )
        
        dp_state["orchestrator"] = orchestrator
        add_log(f"  ✓ Orchestrator initialized with {len(sku_configs)} SKUs, {len(supplier_configs)} suppliers")
        dp_state["progress"] = 35
        
        # Generate demand history
        dp_state["current_step"] = "Generating demand history"
        add_log("\n--- Generating Historical Demand Data ---")
        
        np.random.seed(42)
        demand_history = {}
        for sku in sku_configs:
            base_demand = 100 + np.random.uniform(-20, 50)
            seasonality = np.sin(np.arange(52) * 2 * np.pi / 52) * 20
            noise = np.random.normal(0, 10, 52)
            demand_history[sku["sku_id"]] = np.maximum(10, base_demand + seasonality + noise)
            add_log(f"  ✓ {sku['sku_id']}: 52 weeks history, avg={np.mean(demand_history[sku['sku_id']]):.0f}/week")
        
        dp_state["progress"] = 45
        
        # Set current inventory
        current_inventory = {sku["sku_id"]: sku["current_inventory"] for sku in sku_configs}
        
        # Run the pipeline
        dp_state["current_step"] = "Running D&P pipeline"
        add_log("\n" + "=" * 60)
        add_log("  RUNNING DEMAND & PROCUREMENT PIPELINE")
        add_log("=" * 60)
        
        add_log("\nStep 1: Demand Forecasting...")
        dp_state["progress"] = 50
        
        add_log("Step 2: Inventory Optimization...")
        dp_state["progress"] = 60
        
        add_log("Step 3: Risk Assessment...")
        dp_state["progress"] = 70
        
        add_log("Step 4: Scenario Simulation...")
        dp_state["progress"] = 80
        
        # Run the actual pipeline
        decision_pack = orchestrator.run(
            demand_history=demand_history,
            current_inventory=current_inventory
        )
        
        dp_state["decision_pack"] = decision_pack
        dp_state["progress"] = 90
        
        # Log results
        dp_state["current_step"] = "Generating results"
        add_log("\n" + "=" * 60)
        add_log("  DECISION PACK RESULTS")
        add_log("=" * 60)
        
        add_log(f"\nPack ID: {decision_pack.pack_id}")
        add_log(f"Status: {decision_pack.status}")
        add_log(f"Confidence: {decision_pack.confidence_score:.1%}")
        
        add_log("\n--- Forecasts ---")
        for sku_id, forecast in decision_pack.forecasts.items():
            add_log(f"  {sku_id}: Avg {forecast.mean_weekly_demand:.0f}/week, Total {forecast.total_forecast:.0f} (13wk)")
        
        add_log("\n--- Inventory Policies ---")
        for sku_id, policy in decision_pack.policies.items():
            add_log(f"  {sku_id}: ROP={policy.reorder_point}, EOQ={policy.order_quantity}, SS={policy.safety_stock}")
        
        add_log("\n--- Risk Assessments ---")
        for sku_id, risk in decision_pack.risk_assessments.items():
            add_log(f"  {sku_id}: {risk.risk_level.upper()} risk (stockout {risk.stockout_probability:.1%})")
        
        add_log("\n--- Procurement Plans ---")
        for plan in decision_pack.procurement_plans[:5]:
            add_log(f"  {plan.sku_id}: Order {plan.order_quantity} units from {plan.supplier_id} (P{plan.priority})")
        
        add_log("\n--- Scenario Results ---")
        for scenario_id, result in decision_pack.scenario_results.items():
            add_log(f"  {result.scenario_name}: SL={result.expected_service_level:.1%}, Cost=${result.expected_total_cost:,.0f}")
        
        add_log("\n--- Recommendations ---")
        for rec in decision_pack.recommendations[:5]:
            add_log(f"  [{rec['type']}] {rec['sku_id']}: {rec['action']} (P{rec['priority']})")
        
        add_log("\n" + "=" * 60)
        add_log("  EXECUTIVE SUMMARY")
        add_log("=" * 60)
        add_log(decision_pack.executive_summary)
        
        dp_state["progress"] = 100
        dp_state["status"] = "completed"
        dp_state["current_step"] = "Demo complete"
        add_log("\n✅ D&P Demo completed successfully!")
        
        return {
            "status": "success",
            "message": "D&P Demo completed successfully",
            "pack_id": decision_pack.pack_id
        }
        
    except Exception as e:
        dp_state["status"] = "error"
        dp_state["current_step"] = f"Error: {str(e)}"
        add_log(f"❌ D&P Demo failed: {str(e)}", "error")
        import traceback
        add_log(traceback.format_exc(), "error")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/dp/ui/bayesian")
async def get_dp_bayesian_page_data():
    """Get D&P Bayesian page data"""
    decision_pack = dp_state.get("decision_pack")
    skus = get_dp_sku_configs()
    
    # Build predictions from forecasts
    predictions = []
    if decision_pack and decision_pack.forecasts:
        for i, (sku_id, forecast) in enumerate(list(decision_pack.forecasts.items())[:4]):
            sku = next((s for s in skus if s["sku_id"] == sku_id), None)
            predictions.append({
                "id": f"pred-{i+1}",
                "timestamp": datetime.now().isoformat(),
                "metric": f"{sku['sku_name'] if sku else sku_id} Demand",
                "predictedValue": forecast.mean_weekly_demand,
                "confidenceInterval": [forecast.q10[0] if forecast.q10 else forecast.mean_weekly_demand * 0.8, forecast.q90[0] if forecast.q90 else forecast.mean_weekly_demand * 1.2],
                "probability": 0.85,
                "priorMean": forecast.mean_weekly_demand * 0.9,
                "posteriorMean": forecast.mean_weekly_demand,
                "uncertainty": forecast.std_weekly_demand,
            })
    else:
        for i, sku in enumerate(skus[:4]):
            predictions.append({
                "id": f"pred-{i+1}",
                "timestamp": datetime.now().isoformat(),
                "metric": f"{sku['sku_name']} Demand",
                "predictedValue": 100,
                "confidenceInterval": [80, 120],
                "probability": 0.5,
                "priorMean": 100,
                "posteriorMean": 100,
                "uncertainty": 20,
            })
    
    # Model parameters
    parameters = [
        {"name": "μ (Base Demand)", "prior": 100, "posterior": 110 if decision_pack else 100, "credibleInterval": [90, 130]},
        {"name": "σ (Demand Std)", "prior": 25, "posterior": 22 if decision_pack else 25, "credibleInterval": [18, 32]},
        {"name": "LT (Lead Time)", "prior": 10, "posterior": 9 if decision_pack else 10, "credibleInterval": [7, 14]},
        {"name": "SL (Service Level)", "prior": 0.95, "posterior": 0.96 if decision_pack else 0.95, "credibleInterval": [0.92, 0.98]},
    ]
    
    # Federated nodes (SKU categories)
    categories = list(set(s["category"] for s in skus))
    nodes = []
    for i, cat in enumerate(categories):
        cat_skus = [s for s in skus if s["category"] == cat]
        nodes.append({
            "id": f"node-{i+1}",
            "name": cat,
            "location": f"{len(cat_skus)} SKUs",
            "status": "active" if decision_pack else "offline",
            "lastSync": f"{np.random.randint(1, 5)} min ago" if decision_pack else "Never",
            "localSamples": len(cat_skus) * 52 * 4,
            "contribution": round(len(cat_skus) / len(skus), 2)
        })
    
    # Convergence data
    convergence = []
    for iteration in range(0, 801, 100):
        progress = iteration / 700
        posterior = 100 + 10 * min(1.0, progress * 1.2)
        uncertainty = 25 * (1 - progress * 0.3)
        convergence.append({
            "iteration": iteration,
            "prior": 100,
            "posterior": round(posterior, 1),
            "lower": round(posterior - uncertainty, 1),
            "upper": round(posterior + uncertainty, 1)
        })
    
    return {
        "bayesianPredictions": predictions,
        "modelParameters": parameters,
        "federatedNodes": nodes,
        "posteriorConvergenceData": convergence,
        "aggregationSummary": {
            "totalSamples": sum(n["localSamples"] for n in nodes),
            "activeNodes": len([n for n in nodes if n["status"] == "active"]),
            "syncRounds": 12 if decision_pack else 0,
            "modelUncertainty": decision_pack.confidence_score if decision_pack else 0.5
        }
    }


@app.get("/api/dp/ui/digital-twin")
async def get_dp_digital_twin_page_data():
    """Get D&P Digital Twin page data"""
    decision_pack = dp_state.get("decision_pack")
    skus = get_dp_sku_configs()
    
    # Build devices from SKUs
    devices = []
    for i, sku in enumerate(skus[:4]):
        inventory = sku["current_inventory"]
        demand = 100
        if decision_pack and sku["sku_id"] in decision_pack.forecasts:
            demand = decision_pack.forecasts[sku["sku_id"]].mean_weekly_demand
        
        weeks_supply = inventory / demand if demand > 0 else 0
        risk_level = "normal"
        if decision_pack and sku["sku_id"] in decision_pack.risk_assessments:
            risk_level = decision_pack.risk_assessments[sku["sku_id"]].risk_level
        
        status = "normal" if risk_level == "low" else ("warning" if risk_level in ["medium", "high"] else "critical")
        
        devices.append({
            "id": sku["sku_id"],
            "name": sku["sku_name"],
            "type": "sensor",
            "status": status,
            "location": f"{sku['category']}, LT={sku['lead_time_days']}d",
            "lastUpdate": f"{np.random.randint(5, 30)} sec ago",
            "metrics": [
                {"name": "On Hand", "value": inventory, "unit": "units", "trend": "stable"},
                {"name": "Weekly Demand", "value": round(demand), "unit": "units/wk", "trend": "up" if np.random.random() > 0.5 else "stable"},
                {"name": "Weeks of Supply", "value": round(weeks_supply, 1), "unit": "weeks", "trend": "down" if weeks_supply < 3 else "stable"},
            ]
        })
    
    # Activities
    activities = []
    for i, log in enumerate(dp_state.get("logs", [])[-6:]):
        msg = log.get("message", "")
        if any(kw in msg.lower() for kw in ["inventory", "demand", "sku", "forecast", "risk"]):
            activities.append({
                "id": f"act-{i+1}",
                "timestamp": log.get("timestamp", "")[-8:],
                "type": "telemetry",
                "deviceId": "system",
                "message": msg[:80],
                "severity": "info"
            })
    
    if not activities:
        activities = [
            {"id": "act-1", "timestamp": datetime.now().strftime("%H:%M:%S"), "type": "telemetry", "deviceId": "system", "message": "Awaiting demo run", "severity": "info"},
        ]
    
    # Telemetry history
    telemetry = []
    for week in range(13):
        base_inv = 800 - week * 40
        demand_var = np.sin(week / 2) * 50
        telemetry.append({
            "time": f"Week {week + 1}",
            "inventory": int(max(200, base_inv + demand_var)),
            "demand": int(100 + np.random.uniform(-15, 25)),
            "threshold_inventory": 300
        })
    
    return {
        "devices": devices,
        "twinActivities": activities,
        "telemetryHistory": telemetry
    }


@app.get("/api/dp/ui/orchestration")
async def get_dp_orchestration_page_data():
    """Get D&P Orchestration page data"""
    decision_pack = dp_state.get("decision_pack")
    
    # D&P Pipeline agents
    agents = [
        {"id": "agent-1", "name": "Demand Forecaster", "role": "Probabilistic Forecasting", "status": "completed" if decision_pack else "idle", "avatar": "📊", "description": "Generates probabilistic demand forecasts"},
        {"id": "agent-2", "name": "Inventory Optimizer", "role": "Policy Optimization", "status": "completed" if decision_pack else "idle", "avatar": "📦", "description": "Computes ROP, EOQ, safety stock"},
        {"id": "agent-3", "name": "Supplier Manager", "role": "Supplier Selection", "status": "completed" if decision_pack else "idle", "avatar": "🤝", "description": "Manages supplier relationships"},
        {"id": "agent-4", "name": "Risk Analyst", "role": "Risk Assessment", "status": "completed" if decision_pack else "idle", "avatar": "⚠️", "description": "Analyzes stockout and overstock risks"},
        {"id": "agent-5", "name": "Scenario Simulator", "role": "Monte Carlo Simulation", "status": "completed" if decision_pack else "idle", "avatar": "🔮", "description": "Runs what-if scenarios"},
        {"id": "agent-6", "name": "Procurement Planner", "role": "Plan Generation", "status": "completed" if decision_pack else "idle", "avatar": "📋", "description": "Generates procurement plans"},
        {"id": "agent-7", "name": "Governance Agent", "role": "Policy Validation", "status": "completed" if decision_pack else "idle", "avatar": "🛡️", "description": "Validates against business rules"},
        {"id": "agent-8", "name": "Report Writer", "role": "Decision Pack", "status": "completed" if decision_pack else "idle", "avatar": "📝", "description": "Generates decision packs"},
    ]
    
    # Pipeline steps
    steps = [
        {"id": "step-1", "name": "Forecast", "agents": ["Demand Forecaster"], "status": "completed" if decision_pack else "pending"},
        {"id": "step-2", "name": "Optimize", "agents": ["Inventory Optimizer"], "status": "completed" if decision_pack else "pending"},
        {"id": "step-3", "name": "Risk", "agents": ["Risk Analyst"], "status": "completed" if decision_pack else "pending"},
        {"id": "step-4", "name": "Simulate", "agents": ["Scenario Simulator"], "status": "completed" if decision_pack else "pending"},
        {"id": "step-5", "name": "Plan", "agents": ["Procurement Planner"], "status": "completed" if decision_pack else "pending"},
        {"id": "step-6", "name": "Govern", "agents": ["Governance Agent"], "status": "completed" if decision_pack else "pending"},
        {"id": "step-7", "name": "Report", "agents": ["Report Writer"], "status": "completed" if decision_pack else "pending"},
    ]
    
    # Agent actions
    actions = []
    if decision_pack:
        actions = [
            {"id": "action-1", "agentId": "agent-1", "agentName": "Demand Forecaster", "timestamp": datetime.now().strftime("%H:%M:%S"), "action": f"Generated forecasts for {len(decision_pack.forecasts)} SKUs", "target": "pipeline", "status": "completed", "duration": 150},
            {"id": "action-2", "agentId": "agent-2", "agentName": "Inventory Optimizer", "timestamp": datetime.now().strftime("%H:%M:%S"), "action": f"Optimized policies for {len(decision_pack.policies)} SKUs", "target": "pipeline", "status": "completed", "duration": 200},
            {"id": "action-3", "agentId": "agent-4", "agentName": "Risk Analyst", "timestamp": datetime.now().strftime("%H:%M:%S"), "action": f"Assessed risk for {len(decision_pack.risk_assessments)} SKUs", "target": "pipeline", "status": "completed", "duration": 120},
            {"id": "action-4", "agentId": "agent-6", "agentName": "Procurement Planner", "timestamp": datetime.now().strftime("%H:%M:%S"), "action": f"Generated {len(decision_pack.procurement_plans)} procurement orders", "target": "pipeline", "status": "completed", "duration": 180},
        ]
    
    # Current case
    current_case = {
        "id": decision_pack.pack_id if decision_pack else "PENDING",
        "title": "Demand & Procurement Optimization",
        "status": "complete" if decision_pack else "pending",
        "priority": "high",
        "createdAt": decision_pack.created_at.isoformat() if decision_pack else None,
        "assignedAgents": [a["name"] for a in agents if a["status"] == "completed"],
        "alerts": len([r for r in (decision_pack.risk_assessments.values() if decision_pack else []) if getattr(r, 'risk_level', 'low') in ["high", "critical"]]),
        "hypotheses": len(decision_pack.scenario_results) if decision_pack else 0,
        "totalBudget": 500000,
        "confidence": decision_pack.confidence_score if decision_pack else 0
    }
    
    # Governance
    governance = {
        "autonomyLevel": "AUTO_LOW_RISK" if decision_pack and decision_pack.status == "completed" else "PENDING",
        "policyChecks": {"passed": 5 if decision_pack else 0, "total": 5},
        "pendingApprovals": 0 if decision_pack and decision_pack.status == "completed" else 1,
        "auditEntries": len(actions)
    }
    
    return {
        "agents": agents,
        "agentActions": actions,
        "orchestrationSteps": steps,
        "currentCase": current_case,
        "governance": governance
    }


@app.get("/api/dp/ui/agent-output")
async def get_dp_agent_output_page_data():
    """Get D&P Agent Output page data"""
    decision_pack = dp_state.get("decision_pack")
    
    agents = [
        {"id": "agent-1", "name": "Demand Forecaster", "role": "Probabilistic Forecasting", "status": "completed" if decision_pack else "idle", "avatar": "📊"},
        {"id": "agent-2", "name": "Inventory Optimizer", "role": "Policy Optimization", "status": "completed" if decision_pack else "idle", "avatar": "📦"},
        {"id": "agent-4", "name": "Risk Analyst", "role": "Risk Assessment", "status": "completed" if decision_pack else "idle", "avatar": "⚠️"},
        {"id": "agent-6", "name": "Procurement Planner", "role": "Plan Generation", "status": "completed" if decision_pack else "idle", "avatar": "📋"},
        {"id": "agent-8", "name": "Report Writer", "role": "Decision Pack", "status": "completed" if decision_pack else "idle", "avatar": "📝"},
    ]
    
    outputs = []
    
    if decision_pack:
        # Forecaster output
        outputs.append({
            "id": "output-1",
            "agentId": "agent-1",
            "agentName": "Demand Forecaster",
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "outputType": "analysis",
            "title": "Demand Forecasts Generated",
            "summary": f"Generated 13-week probabilistic forecasts for {len(decision_pack.forecasts)} SKUs",
            "details": "Used exponential smoothing with growing uncertainty bands. Forecasts include q10, q50, q90 quantiles for safety stock calculation. Seasonality patterns detected in historical data.",
            "confidence": 0.88,
            "rationale": [
                {"step": 1, "description": "History Analysis", "reasoning": "Analyzed 52 weeks of demand history per SKU", "confidence": 0.95},
                {"step": 2, "description": "Model Fitting", "reasoning": "Applied exponential smoothing with trend detection", "confidence": 0.90},
                {"step": 3, "description": "Uncertainty Quantification", "reasoning": "Computed prediction intervals with growing uncertainty", "confidence": 0.85},
            ],
            "evidence": [
                {"type": "data", "source": "Demand History", "description": "52 weeks x 5 SKUs = 260 data points", "weight": 0.9},
                {"type": "model", "source": "Exponential Smoothing", "description": "Alpha=0.3 smoothing factor", "weight": 0.85},
            ]
        })
        
        # Optimizer output
        outputs.append({
            "id": "output-2",
            "agentId": "agent-2",
            "agentName": "Inventory Optimizer",
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "outputType": "recommendation",
            "title": "Inventory Policies Optimized",
            "summary": f"Computed optimal ROP, EOQ, and safety stock for {len(decision_pack.policies)} SKUs",
            "details": "Policies balance service level targets (90-99%) against holding costs. Safety stock computed using demand uncertainty during lead time. EOQ minimizes total annual cost.",
            "confidence": 0.90,
            "rationale": [
                {"step": 1, "description": "Service Level Mapping", "reasoning": "Mapped service level tiers to Z-scores (Bronze=1.28, Silver=1.65, Gold=2.05)", "confidence": 0.98},
                {"step": 2, "description": "Safety Stock Calculation", "reasoning": "SS = Z * σ_d * √LT accounting for lead time variability", "confidence": 0.92},
                {"step": 3, "description": "EOQ Optimization", "reasoning": "EOQ = √(2*D*K/h) with case-pack rounding", "confidence": 0.88},
            ],
            "evidence": [
                {"type": "model", "source": "Stochastic Inventory Model", "description": "(r,Q) policy optimization", "weight": 0.95},
                {"type": "data", "source": "Forecast Distributions", "description": "Mean and variance by SKU", "weight": 0.9},
            ]
        })
        
        # Risk output
        high_risk = [r for r in decision_pack.risk_assessments.values() if r.risk_level in ["high", "critical"]]
        outputs.append({
            "id": "output-3",
            "agentId": "agent-4",
            "agentName": "Risk Analyst",
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "outputType": "analysis",
            "title": f"Risk Assessment: {len(high_risk)} High-Risk SKUs",
            "summary": f"Analyzed stockout and overstock risks for {len(decision_pack.risk_assessments)} SKUs",
            "details": f"Identified {len(high_risk)} SKUs with elevated risk. Primary drivers: low inventory position relative to demand uncertainty, supplier lead time variability.",
            "confidence": 0.85,
            "rationale": [
                {"step": 1, "description": "Stockout Probability", "reasoning": "P(stockout) based on inventory position vs. demand during lead time", "confidence": 0.88},
                {"step": 2, "description": "Overstock Analysis", "reasoning": "Weeks of supply > 8 indicates overstock risk", "confidence": 0.85},
                {"step": 3, "description": "Risk Scoring", "reasoning": "Weighted combination: 50% stockout + 30% lead time + 20% overstock", "confidence": 0.82},
            ],
            "evidence": [
                {"type": "data", "source": "Inventory Positions", "description": "Current on-hand vs. reorder points", "weight": 0.9},
                {"type": "model", "source": "Risk Model", "description": "Multi-factor risk scoring", "weight": 0.85},
            ]
        })
        
        # Procurement output
        outputs.append({
            "id": "output-4",
            "agentId": "agent-6",
            "agentName": "Procurement Planner",
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "outputType": "decision",
            "title": f"Generated {len(decision_pack.procurement_plans)} Procurement Orders",
            "summary": f"Priority-ranked procurement plans with ${sum(p.total_cost for p in decision_pack.procurement_plans):,.0f} total value",
            "details": "Orders triggered by: below ROP, high risk levels. Assigned to preferred suppliers based on SKU mapping. Priority 1 = critical, Priority 2 = below ROP, Priority 3 = routine.",
            "confidence": decision_pack.confidence_score,
            "rationale": [
                {"step": 1, "description": "Trigger Evaluation", "reasoning": "Check inventory position vs. ROP and risk levels", "confidence": 0.95},
                {"step": 2, "description": "Supplier Assignment", "reasoning": "Map SKUs to preferred suppliers", "confidence": 0.92},
                {"step": 3, "description": "Priority Ranking", "reasoning": "Rank by risk level and days to stockout", "confidence": 0.88},
            ],
            "evidence": [
                {"type": "data", "source": "Inventory Policies", "description": "ROP and EOQ by SKU", "weight": 0.95},
                {"type": "rule", "source": "Supplier Contracts", "description": "Supplier-SKU assignments", "weight": 0.9},
            ]
        })
        
        # Summary output
        outputs.append({
            "id": "output-5",
            "agentId": "agent-8",
            "agentName": "Report Writer",
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "outputType": "analysis",
            "title": "Decision Pack Generated",
            "summary": "Compiled comprehensive procurement decision pack with rationale",
            "details": decision_pack.executive_summary[:400] + "..." if len(decision_pack.executive_summary) > 400 else decision_pack.executive_summary,
            "confidence": 0.95,
            "rationale": [
                {"step": 1, "description": "Data Compilation", "reasoning": "Aggregated forecasts, policies, risks, and plans", "confidence": 0.98},
                {"step": 2, "description": "Insight Extraction", "reasoning": "Identified key recommendations and risk mitigations", "confidence": 0.92},
                {"step": 3, "description": "Summary Generation", "reasoning": "Created executive summary with confidence scores", "confidence": 0.95},
            ],
            "evidence": [
                {"type": "model", "source": "Decision Pack", "description": "Complete analysis artifacts", "weight": 0.95},
            ]
        })
    else:
        outputs.append({
            "id": "output-0",
            "agentId": "agent-1",
            "agentName": "System",
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "outputType": "analysis",
            "title": "Awaiting Demo Execution",
            "summary": "Run the D&P demo to see agent outputs with full rationale",
            "details": "The agent output page will display detailed forecasts, policies, risk assessments, and procurement plans once the demo is executed.",
            "confidence": 1.0,
            "rationale": [{"step": 1, "description": "Initialization", "reasoning": "System ready for demo execution", "confidence": 1.0}],
            "evidence": []
        })
    
    return {
        "agentOutputs": outputs,
        "agents": agents
    }


# ============================================================================
# AGENT COLLABORATION (INTEGRATED WITH MAIN DEMO)
# ============================================================================


@app.get("/api/ui/autonomous-orchestration")
async def get_autonomous_orchestration_page_data():
    """
    Get data for Agent Collaboration Page - uses collaboration events from main demo run.
    This is integrated with the main pipeline, not a separate workflow.
    """
    orchestrator = demo_state.get("orchestrator")
    decision_pack = demo_state.get("decision_pack")
    
    # Define agents that participate in the pipeline
    agents = [
        {"id": "BayesianEngine", "name": "Bayesian Engine", "role": "Elasticity Posteriors", "status": "idle", "avatar": "📊", "track": "analytics"},
        {"id": "AttributionAgent", "name": "Attribution Analyst", "role": "Multi-Touch Attribution", "status": "idle", "avatar": "🎯", "track": "analytics"},
        {"id": "ScenarioAgent", "name": "Scenario Planner", "role": "Scenario Generation", "status": "idle", "avatar": "🎭", "track": "simulation"},
        {"id": "DigitalTwin", "name": "Digital Twin", "role": "Monte Carlo Simulation", "status": "idle", "avatar": "🔮", "track": "simulation"},
        {"id": "OptimizationAgent", "name": "Budget Optimizer", "role": "Allocation Optimization", "status": "idle", "avatar": "💰", "track": "optimization"},
        {"id": "GovernanceAgent", "name": "Governance Validator", "role": "Policy Validation", "status": "idle", "avatar": "🛡️", "track": "governance"},
        {"id": "RationaleAgent", "name": "Business Communicator", "role": "Rationale Generation", "status": "idle", "avatar": "📝", "track": "communication"},
        {"id": "DataPipeline", "name": "Data Pipeline", "role": "Data Ingestion", "status": "idle", "avatar": "📦", "track": "data_quality"},
    ]
    
    # Update agent status based on pipeline steps and collaboration
    if decision_pack:
        for agent in agents:
            agent["status"] = "completed"
    elif orchestrator and orchestrator.pipeline_steps:
        completed_steps = {s.step_name for s in orchestrator.pipeline_steps if s.status == "completed"}
        step_to_agent = {
            "bayesian_calibration": ["BayesianEngine", "DigitalTwin"],
            "attribution": ["AttributionAgent"],
            "scenario_generation": ["ScenarioAgent", "BayesianEngine"],
            "twin_simulation": ["DigitalTwin", "ScenarioAgent"],
            "optimization": ["OptimizationAgent", "GovernanceAgent"],
            "governance": ["GovernanceAgent"],
            "rationale": ["RationaleAgent"],
        }
        for step, agent_ids in step_to_agent.items():
            if step in completed_steps:
                for agent_id in agent_ids:
                    for agent in agents:
                        if agent["id"] == agent_id:
                            agent["status"] = "completed"
    
    # Map pipeline steps to parallel tracks (conceptual parallel work)
    parallel_tracks = [
        {"id": "data_quality", "name": "Data Quality", "type": "data_quality", "status": "pending", "progress": 0, "agents": ["DataPipeline"]},
        {"id": "analytics", "name": "Bayesian Analytics", "type": "analytics", "status": "pending", "progress": 0, "agents": ["BayesianEngine", "AttributionAgent"]},
        {"id": "simulation", "name": "Twin Simulation", "type": "simulation", "status": "pending", "progress": 0, "agents": ["ScenarioAgent", "DigitalTwin"]},
        {"id": "optimization", "name": "Optimization", "type": "optimization", "status": "pending", "progress": 0, "agents": ["OptimizationAgent"]},
        {"id": "governance", "name": "Governance", "type": "governance", "status": "pending", "progress": 0, "agents": ["GovernanceAgent"]},
        {"id": "communication", "name": "Rationale", "type": "communication", "status": "pending", "progress": 0, "agents": ["RationaleAgent"]},
    ]
    
    # Update track status based on pipeline
    if decision_pack:
        for track in parallel_tracks:
            track["status"] = "completed"
            track["progress"] = 1.0
    elif orchestrator and orchestrator.pipeline_steps:
        step_to_track = {
            "bayesian_calibration": "analytics",
            "attribution": "analytics",
            "scenario_generation": "simulation",
            "twin_simulation": "simulation",
            "optimization": "optimization",
            "governance": "governance",
            "rationale": "communication",
        }
        completed_steps = {s.step_name for s in orchestrator.pipeline_steps if s.status == "completed"}
        for step, track_id in step_to_track.items():
            if step in completed_steps:
                for track in parallel_tracks:
                    if track["id"] == track_id:
                        track["status"] = "completed"
                        track["progress"] = 1.0
    
    # Get collaboration events from the decision pack (integrated with main demo)
    collaboration_events = []
    if decision_pack and hasattr(decision_pack, 'collaboration_events'):
        for event in decision_pack.collaboration_events:
            collaboration_events.append({
                "id": event.collaboration_id,
                "timestamp": event.timestamp.strftime("%H:%M:%S") if hasattr(event.timestamp, 'strftime') else str(event.timestamp)[-8:],
                "type": event.collaboration_type.value if hasattr(event.collaboration_type, 'value') else event.collaboration_type,
                "initiator": event.initiator_agent,
                "targets": event.target_agents,
                "topic": event.topic,
                "status": event.outcome or "completed",
            })
    
    # Build collaboration graph from events
    collaboration_graph = {"nodes": [], "edges": []}
    if collaboration_events:
        node_ids = set()
        edge_counts = {}
        for event in collaboration_events:
            node_ids.add(event["initiator"])
            for target in event["targets"]:
                node_ids.add(target)
                edge_key = (event["initiator"], target)
                edge_counts[edge_key] = edge_counts.get(edge_key, 0) + 1
        
        collaboration_graph["nodes"] = [{"id": nid, "role": nid} for nid in node_ids]
        collaboration_graph["edges"] = [
            {"source": src, "target": tgt, "count": cnt, "weight": min(1.0, cnt * 0.2)}
            for (src, tgt), cnt in edge_counts.items()
        ]
    
    # Current case - from main demo
    current_case = {
        "id": decision_pack.pack_id if decision_pack else "PENDING",
        "title": "Media Spend Optimization (Agent Collaboration View)",
        "status": "complete" if demo_state["status"] == "completed" else demo_state["status"],
        "priority": "high",
        "assignedAgents": [a["name"] for a in agents if a["status"] == "completed"],
        "collaborations": len(collaboration_events),
        "parallelTracks": len([t for t in parallel_tracks if t["status"] == "completed"]),
        "totalTracks": len(parallel_tracks),
        "totalBudget": 10_000_000,
        "confidence": decision_pack.overall_confidence if decision_pack else 0,
    }
    
    # Governance from main demo decision pack
    governance_checks = 0
    if decision_pack and decision_pack.governance_decision:
        governance_checks = len(decision_pack.governance_decision.checks)
    
    governance = {
        "autonomyLevel": "COLLABORATIVE",
        "policyChecks": {"passed": governance_checks, "total": max(governance_checks, 5)},
        "pendingApprovals": 0 if decision_pack else 1,
        "auditEntries": len(collaboration_events),
    }
    
    return {
        "agents": agents,
        "parallelTracks": parallel_tracks,
        "collaborationEvents": collaboration_events,
        "collaborationGraph": collaboration_graph,
        "currentCase": current_case,
        "governance": governance,
        "workflowMode": "integrated",
    }


# ============================================================================
# BAYESIAN ANALYTICS ENDPOINTS
# For the Bayesian Analytics (formerly Bayesian Twins) page
# ============================================================================

@app.get("/api/bayesian/brands")
async def get_bayesian_brands():
    """Get Bayesian posterior data for all brands"""
    brands = [
        {
            "brand_id": "brand-001",
            "brand_name": "Acme Foods",
            "category": "Packaged Goods",
            "bayesian_outputs": {
                "incremental_sales": {"mean": 2450000, "std": 245000, "ci": [2010000, 2890000]},
                "efficiency_mean": 1.24,
                "efficiency_std": 0.15,
                "index_mean": 112,
                "lift_vs_prior_period": 8.5,
                "lift_vs_year_ago": 12.3,
                "prob_positive_lift": 0.92,
                "last_updated": datetime.now().isoformat()
            },
            "driver_rankings": [
                {"driver": "Sponsored Search", "prob_top_contributor": 0.45},
                {"driver": "Display", "prob_top_contributor": 0.28},
                {"driver": "Video", "prob_top_contributor": 0.18}
            ]
        },
        {
            "brand_id": "brand-002",
            "brand_name": "Fresh Valley",
            "category": "Beverages",
            "bayesian_outputs": {
                "incremental_sales": {"mean": 1890000, "std": 189000, "ci": [1550000, 2230000]},
                "efficiency_mean": 1.18,
                "efficiency_std": 0.12,
                "index_mean": 108,
                "lift_vs_prior_period": 5.2,
                "lift_vs_year_ago": 9.8,
                "prob_positive_lift": 0.88,
                "last_updated": datetime.now().isoformat()
            },
            "driver_rankings": [
                {"driver": "Video", "prob_top_contributor": 0.38},
                {"driver": "Sponsored Products", "prob_top_contributor": 0.32},
                {"driver": "Display", "prob_top_contributor": 0.20}
            ]
        },
        {
            "brand_id": "brand-003",
            "brand_name": "HomeClean Pro",
            "category": "Household",
            "bayesian_outputs": {
                "incremental_sales": {"mean": 1560000, "std": 156000, "ci": [1280000, 1840000]},
                "efficiency_mean": 0.95,
                "efficiency_std": 0.18,
                "index_mean": 95,
                "lift_vs_prior_period": -2.1,
                "lift_vs_year_ago": 3.5,
                "prob_positive_lift": 0.72,
                "last_updated": datetime.now().isoformat()
            },
            "driver_rankings": [
                {"driver": "Email", "prob_top_contributor": 0.35},
                {"driver": "Display", "prob_top_contributor": 0.30},
                {"driver": "Sponsored Search", "prob_top_contributor": 0.22}
            ]
        },
        {
            "brand_id": "brand-004",
            "brand_name": "TechGear Plus",
            "category": "Electronics",
            "bayesian_outputs": {
                "incremental_sales": {"mean": 3120000, "std": 312000, "ci": [2560000, 3680000]},
                "efficiency_mean": 1.42,
                "efficiency_std": 0.20,
                "index_mean": 125,
                "lift_vs_prior_period": 15.8,
                "lift_vs_year_ago": 22.1,
                "prob_positive_lift": 0.96,
                "last_updated": datetime.now().isoformat()
            },
            "driver_rankings": [
                {"driver": "Sponsored Products", "prob_top_contributor": 0.52},
                {"driver": "Video", "prob_top_contributor": 0.25},
                {"driver": "Display", "prob_top_contributor": 0.15}
            ]
        },
    ]
    return {"brands": brands}


@app.get("/api/bayesian/rmns")
async def get_bayesian_rmns():
    """Get Bayesian posterior data for all RMNs (Retail Media Networks)"""
    rmns = [
        {
            "rmn_id": "rmn-walmart",
            "rmn_name": "Walmart Connect",
            "bayesian_outputs": {
                "incremental_sales": {"mean": 4250000, "std": 425000, "ci": [3480000, 5020000]},
                "efficiency_mean": 1.35,
                "efficiency_std": 0.14,
                "index_mean": 118,
                "prob_best_overall": 0.42,
                "expected_rank": 1.8,
                "last_updated": datetime.now().isoformat()
            },
            "channel_mix": {"search": 0.35, "display": 0.25, "video": 0.22, "email": 0.18}
        },
        {
            "rmn_id": "rmn-amazon",
            "rmn_name": "Amazon Ads",
            "bayesian_outputs": {
                "incremental_sales": {"mean": 5120000, "std": 512000, "ci": [4200000, 6040000]},
                "efficiency_mean": 1.48,
                "efficiency_std": 0.16,
                "index_mean": 128,
                "prob_best_overall": 0.58,
                "expected_rank": 1.2,
                "last_updated": datetime.now().isoformat()
            },
            "channel_mix": {"search": 0.45, "display": 0.20, "video": 0.20, "email": 0.15}
        },
        {
            "rmn_id": "rmn-target",
            "rmn_name": "Target Roundel",
            "bayesian_outputs": {
                "incremental_sales": {"mean": 2890000, "std": 289000, "ci": [2370000, 3410000]},
                "efficiency_mean": 1.22,
                "efficiency_std": 0.13,
                "index_mean": 110,
                "prob_best_overall": 0.28,
                "expected_rank": 2.5,
                "last_updated": datetime.now().isoformat()
            },
            "channel_mix": {"search": 0.30, "display": 0.30, "video": 0.25, "email": 0.15}
        },
        {
            "rmn_id": "rmn-kroger",
            "rmn_name": "Kroger Precision",
            "bayesian_outputs": {
                "incremental_sales": {"mean": 1980000, "std": 198000, "ci": [1620000, 2340000]},
                "efficiency_mean": 1.15,
                "efficiency_std": 0.11,
                "index_mean": 105,
                "prob_best_overall": 0.18,
                "expected_rank": 3.2,
                "last_updated": datetime.now().isoformat()
            },
            "channel_mix": {"search": 0.28, "display": 0.32, "video": 0.18, "email": 0.22}
        },
        {
            "rmn_id": "rmn-instacart",
            "rmn_name": "Instacart Ads",
            "bayesian_outputs": {
                "incremental_sales": {"mean": 1450000, "std": 145000, "ci": [1190000, 1710000]},
                "efficiency_mean": 1.08,
                "efficiency_std": 0.10,
                "index_mean": 98,
                "prob_best_overall": 0.12,
                "expected_rank": 4.1,
                "last_updated": datetime.now().isoformat()
            },
            "channel_mix": {"search": 0.42, "display": 0.28, "video": 0.15, "email": 0.15}
        },
    ]
    return {"rmns": rmns}


@app.get("/api/bayesian/channels/{rmn_id}")
async def get_bayesian_channels(rmn_id: str):
    """Get Bayesian posterior data for channels within a specific RMN"""
    channel_templates = [
        ("sponsored_search", "Sponsored Search", "search"),
        ("sponsored_products", "Sponsored Products", "search"),
        ("display_ad", "Display Advertising", "display"),
        ("video_ad", "Video Advertising", "video"),
        ("email", "Email Marketing", "email"),
    ]
    
    np.random.seed(hash(rmn_id) % 2**32)
    channels = []
    
    for channel_id, channel_name, channel_type in channel_templates:
        base_sales = np.random.uniform(400000, 1200000)
        efficiency = np.random.uniform(0.85, 1.55)
        
        channels.append({
            "channel_id": f"{rmn_id}-{channel_id}",
            "channel_name": channel_name,
            "channel_type": channel_type,
            "rmn_id": rmn_id,
            "bayesian_outputs": {
                "incremental_sales": {
                    "mean": round(base_sales),
                    "std": round(base_sales * 0.1),
                    "ci": [round(base_sales * 0.82), round(base_sales * 1.18)]
                },
                "efficiency_mean": round(efficiency, 2),
                "efficiency_std": round(efficiency * 0.12, 2),
                "index_mean": round(efficiency * 100),
                "elasticity": {
                    "mean": round(np.random.uniform(0.08, 0.25), 3),
                    "std": round(np.random.uniform(0.02, 0.05), 3),
                    "ci": [round(np.random.uniform(0.05, 0.10), 3), round(np.random.uniform(0.20, 0.35), 3)]
                },
                "contribution_mean": round(base_sales),
                "contribution_pct_mean": round(np.random.uniform(0.12, 0.28), 2),
                "prob_efficiency_above_target": round(np.random.uniform(0.65, 0.95), 2),
                "efficiency_target": 1.0,
                "prob_rank_1_within_rmn": round(np.random.uniform(0.10, 0.35), 2),
                "expected_rank_within_rmn": round(np.random.uniform(1.5, 4.5), 1),
                "last_updated": datetime.now().isoformat()
            }
        })
    
    return {"channels": channels, "rmn_id": rmn_id}


@app.get("/api/bayesian/scenario-comparison/{entity_type}/{entity_id}")
async def get_bayesian_scenario_comparison(entity_type: str, entity_id: str):
    """Get scenario comparison with Bayesian posteriors for an entity"""
    np.random.seed(hash(f"{entity_type}-{entity_id}") % 2**32)
    
    current_sales = np.random.uniform(1500000, 3500000)
    optimized_sales = current_sales * np.random.uniform(1.05, 1.20)
    
    current_efficiency = np.random.uniform(0.95, 1.15)
    optimized_efficiency = current_efficiency * np.random.uniform(1.05, 1.15)
    
    return {
        "entity_type": entity_type,
        "entity_id": entity_id,
        "current_scenario": {
            "scenario_name": "Current Allocation",
            "incremental_sales_posterior": {
                "mean": round(current_sales),
                "std": round(current_sales * 0.1),
                "ci": [round(current_sales * 0.82), round(current_sales * 1.18)]
            },
            "efficiency_posterior": {
                "mean": round(current_efficiency, 2),
                "std": round(current_efficiency * 0.12, 2)
            },
            "downside_risk_5pct": round(current_sales * 0.75),
            "downside_risk_10pct": round(current_sales * 0.80)
        },
        "optimized_scenario": {
            "scenario_name": "Optimized Allocation",
            "incremental_sales_posterior": {
                "mean": round(optimized_sales),
                "std": round(optimized_sales * 0.1),
                "ci": [round(optimized_sales * 0.82), round(optimized_sales * 1.18)]
            },
            "efficiency_posterior": {
                "mean": round(optimized_efficiency, 2),
                "std": round(optimized_efficiency * 0.12, 2)
            },
            "downside_risk_5pct": round(optimized_sales * 0.78),
            "downside_risk_10pct": round(optimized_sales * 0.83)
        },
        "comparison": {
            "expected_incremental_sales_delta": round(optimized_sales - current_sales),
            "expected_delta_ci": [
                round((optimized_sales - current_sales) * 0.6),
                round((optimized_sales - current_sales) * 1.4)
            ],
            "expected_efficiency_delta": round(optimized_efficiency - current_efficiency, 2),
            "prob_optimized_beats_current": round(np.random.uniform(0.72, 0.92), 2),
            "prob_optimized_beats_current_by_5pct": round(np.random.uniform(0.55, 0.78), 2),
            "prob_optimized_beats_current_by_10pct": round(np.random.uniform(0.35, 0.58), 2)
        },
        "recommended_allocation": {
            "sponsored_search": round(np.random.uniform(0.25, 0.40), 2),
            "display": round(np.random.uniform(0.18, 0.28), 2),
            "video": round(np.random.uniform(0.15, 0.25), 2),
            "email": round(np.random.uniform(0.10, 0.18), 2),
            "sponsored_products": round(np.random.uniform(0.12, 0.22), 2)
        }
    }


# ============================================================================
# DIGITAL TWIN BY CHANNEL (Channel State)
# ============================================================================

@app.get("/api/digital-twins/channels")
async def get_channel_digital_twins():
    """
    Get digital twin state for all media channels.
    Returns channel-focused metrics replacing inventory metrics.
    """
    channels = []
    for channel in MediaChannel:
        # Create sample channel state with realistic retail media metrics
        state = ChannelDigitalTwinState(
            channel=channel,
            retailer_id="all",
            week=demo_state.get("current_week", 1),
            impressions=np.random.uniform(100000, 5000000),
            clicks=np.random.uniform(5000, 100000),
            conversions=np.random.uniform(500, 10000),
            spend=np.random.uniform(10000, 500000),
            click_through_rate=np.random.uniform(0.01, 0.05),
            conversion_rate=np.random.uniform(0.02, 0.15),
            cost_per_click=np.random.uniform(0.5, 3.0),
            cost_per_acquisition=np.random.uniform(5, 50),
            attributed_revenue=np.random.uniform(50000, 2000000),
            attributed_units=np.random.uniform(1000, 50000),
            roas=np.random.uniform(1.5, 8.0),
            cumulative_adstock=np.random.uniform(0, 100000),
            adstock_decay_rate=0.7,
            audience_reach=np.random.uniform(50000, 500000),
            frequency=np.random.uniform(1.5, 5.0),
            viewability_rate=np.random.uniform(0.6, 0.95),
            elasticity_mean=np.random.uniform(0.1, 0.25),
            elasticity_std=np.random.uniform(0.02, 0.08),
            budget_utilization=np.random.uniform(0.7, 1.0),
            pacing_status=np.random.choice(["on_track", "under_pacing", "over_pacing"]),
        )
        channels.append(state.to_dict())
    
    return {
        "channels": channels,
        "summary": {
            "total_channels": len(channels),
            "total_spend": sum(c["spend"] for c in channels),
            "total_impressions": sum(c["impressions"] for c in channels),
            "total_conversions": sum(c["conversions"] for c in channels),
            "overall_roas": sum(c["attributed_revenue"] for c in channels) / max(1, sum(c["spend"] for c in channels)),
        }
    }


@app.get("/api/digital-twins/channels/{channel_id}")
async def get_channel_digital_twin(channel_id: str):
    """Get digital twin state for a specific media channel."""
    try:
        channel = MediaChannel(channel_id)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Channel '{channel_id}' not found")
    
    state = ChannelDigitalTwinState(
        channel=channel,
        retailer_id="all",
        week=demo_state.get("current_week", 1),
        impressions=np.random.uniform(100000, 5000000),
        clicks=np.random.uniform(5000, 100000),
        conversions=np.random.uniform(500, 10000),
        spend=np.random.uniform(10000, 500000),
        click_through_rate=np.random.uniform(0.01, 0.05),
        conversion_rate=np.random.uniform(0.02, 0.15),
        cost_per_click=np.random.uniform(0.5, 3.0),
        cost_per_acquisition=np.random.uniform(5, 50),
        attributed_revenue=np.random.uniform(50000, 2000000),
        attributed_units=np.random.uniform(1000, 50000),
        roas=np.random.uniform(1.5, 8.0),
        cumulative_adstock=np.random.uniform(0, 100000),
        adstock_decay_rate=0.7,
        audience_reach=np.random.uniform(50000, 500000),
        frequency=np.random.uniform(1.5, 5.0),
        viewability_rate=np.random.uniform(0.6, 0.95),
        elasticity_mean=np.random.uniform(0.1, 0.25),
        elasticity_std=np.random.uniform(0.02, 0.08),
        budget_utilization=np.random.uniform(0.7, 1.0),
        pacing_status=np.random.choice(["on_track", "under_pacing", "over_pacing"]),
    )
    
    return state.to_dict()


# ============================================================================
# MANUFACTURER PRODUCT DIGITAL TWINS
# ============================================================================

# Sample manufacturer products for demo - Kelloggs
SAMPLE_MANUFACTURERS = [
    {"id": "KELLOGGS", "name": "Kellogg's", "products": [
        {"id": "KEL001", "name": "Frosted Flakes", "brand": "Kellogg's", "category": "Cereal"},
        {"id": "KEL002", "name": "Froot Loops", "brand": "Kellogg's", "category": "Cereal"},
        {"id": "KEL003", "name": "Rice Krispies", "brand": "Kellogg's", "category": "Cereal"},
        {"id": "KEL004", "name": "Special K", "brand": "Kellogg's", "category": "Cereal"},
        {"id": "KEL005", "name": "Raisin Bran", "brand": "Kellogg's", "category": "Cereal"},
        {"id": "KEL006", "name": "Corn Flakes", "brand": "Kellogg's", "category": "Cereal"},
        {"id": "KEL007", "name": "Pop-Tarts Strawberry", "brand": "Pop-Tarts", "category": "Toaster Pastries"},
        {"id": "KEL008", "name": "Pop-Tarts Brown Sugar", "brand": "Pop-Tarts", "category": "Toaster Pastries"},
        {"id": "KEL009", "name": "Eggo Waffles", "brand": "Eggo", "category": "Frozen Breakfast"},
        {"id": "KEL010", "name": "Cheez-It Original", "brand": "Cheez-It", "category": "Snacks"},
        {"id": "KEL011", "name": "Pringles Original", "brand": "Pringles", "category": "Snacks"},
        {"id": "KEL012", "name": "Nutri-Grain Bars", "brand": "Nutri-Grain", "category": "Snack Bars"},
    ]},
]

SAMPLE_RETAILERS = ["Amazon", "Walmart", "Target", "Kroger", "Costco"]


@app.get("/api/digital-twins/manufacturers")
async def get_manufacturer_digital_twins():
    """Get list of all manufacturer product digital twins."""
    manufacturers = []
    for mfr in SAMPLE_MANUFACTURERS:
        products = []
        for prod in mfr["products"]:
            config = ManufacturerProductConfig(
                manufacturer_id=mfr["id"],
                manufacturer_name=mfr["name"],
                product_id=prod["id"],
                product_name=prod["name"],
                brand=prod["brand"],
                category=prod["category"],
                msrp=np.random.uniform(10, 100),
                wholesale_price=np.random.uniform(5, 50),
                total_media_budget=np.random.uniform(100000, 2000000),
                preferred_channels=[MediaChannel.SPONSORED_SEARCH, MediaChannel.DISPLAY_AD, MediaChannel.BRAND_STORE],
                target_retailers=SAMPLE_RETAILERS[:3],
            )
            products.append({
                "product_id": prod["id"],
                "product_name": prod["name"],
                "brand": prod["brand"],
                "category": prod["category"],
                "total_media_budget": config.total_media_budget,
            })
        
        manufacturers.append({
            "manufacturer_id": mfr["id"],
            "manufacturer_name": mfr["name"],
            "products": products,
            "total_products": len(products),
        })
    
    return {"manufacturers": manufacturers}


@app.get("/api/digital-twins/manufacturers/{manufacturer_id}")
async def get_manufacturer_digital_twin(manufacturer_id: str):
    """Get digital twin state for a specific manufacturer's products."""
    mfr = next((m for m in SAMPLE_MANUFACTURERS if m["id"] == manufacturer_id), None)
    if not mfr:
        raise HTTPException(status_code=404, detail=f"Manufacturer '{manufacturer_id}' not found")
    
    products = []
    for prod in mfr["products"]:
        # Create manufacturer product state
        state = ManufacturerProductState(
            manufacturer_id=mfr["id"],
            product_id=prod["id"],
            week=demo_state.get("current_week", 1),
        )
        
        # Add retailer states
        for retailer in SAMPLE_RETAILERS[:3]:
            retailer_state = ManufacturerRetailerState(
                retailer_id=retailer,
                week=state.week,
                total_spend=np.random.uniform(10000, 100000),
                total_impressions=np.random.uniform(100000, 1000000),
                total_conversions=np.random.uniform(500, 5000),
                total_revenue=np.random.uniform(50000, 500000),
                share_of_voice=np.random.uniform(0.05, 0.25),
                share_of_shelf=np.random.uniform(0.1, 0.3),
                share_of_search=np.random.uniform(0.05, 0.2),
                category_rank=np.random.randint(1, 10),
                price_index=np.random.uniform(0.9, 1.1),
            )
            
            # Add channel states for this retailer
            for channel in [MediaChannel.SPONSORED_SEARCH, MediaChannel.DISPLAY_AD, MediaChannel.BRAND_STORE, MediaChannel.EMAIL]:
                ch_state = ManufacturerChannelState(
                    channel=channel,
                    week=state.week,
                    spend=np.random.uniform(2000, 30000),
                    impressions=np.random.uniform(20000, 300000),
                    reach=np.random.uniform(10000, 100000),
                    frequency=np.random.uniform(1.5, 4.0),
                    clicks=np.random.uniform(500, 10000),
                    click_through_rate=np.random.uniform(0.01, 0.05),
                    purchases=np.random.uniform(50, 1000),
                    conversion_rate=np.random.uniform(0.02, 0.1),
                    attributed_sales=np.random.uniform(5000, 100000),
                    attributed_units=np.random.uniform(100, 2000),
                    roas=np.random.uniform(1.5, 6.0),
                    brand_search_lift=np.random.uniform(0, 0.15),
                    new_to_brand_percentage=np.random.uniform(0.1, 0.4),
                    cost_per_click=np.random.uniform(0.5, 2.5),
                    cost_per_acquisition=np.random.uniform(5, 40),
                )
                retailer_state.channel_states[channel.value] = ch_state
            
            state.retailer_states[retailer] = retailer_state
        
        # Aggregate metrics
        state.aggregate_from_retailers()
        
        products.append({
            "product_id": prod["id"],
            "product_name": prod["name"],
            "brand": prod["brand"],
            "category": prod["category"],
            "state": state.to_dict(),
        })
    
    return {
        "manufacturer_id": mfr["id"],
        "manufacturer_name": mfr["name"],
        "products": products,
    }


@app.get("/api/digital-twins/manufacturers/{manufacturer_id}/products/{product_id}")
async def get_manufacturer_product_digital_twin(manufacturer_id: str, product_id: str):
    """Get detailed digital twin state for a specific manufacturer product."""
    mfr = next((m for m in SAMPLE_MANUFACTURERS if m["id"] == manufacturer_id), None)
    if not mfr:
        raise HTTPException(status_code=404, detail=f"Manufacturer '{manufacturer_id}' not found")
    
    prod = next((p for p in mfr["products"] if p["id"] == product_id), None)
    if not prod:
        raise HTTPException(status_code=404, detail=f"Product '{product_id}' not found")
    
    # Create detailed product state
    config = ManufacturerProductConfig(
        manufacturer_id=mfr["id"],
        manufacturer_name=mfr["name"],
        product_id=prod["id"],
        product_name=prod["name"],
        brand=prod["brand"],
        category=prod["category"],
        msrp=np.random.uniform(10, 100),
        wholesale_price=np.random.uniform(5, 50),
        total_media_budget=np.random.uniform(100000, 2000000),
        preferred_channels=[MediaChannel.SPONSORED_SEARCH, MediaChannel.DISPLAY_AD, MediaChannel.BRAND_STORE],
        target_retailers=SAMPLE_RETAILERS,
        lifecycle_stage="growth",
    )
    
    state = ManufacturerProductState(
        manufacturer_id=mfr["id"],
        product_id=prod["id"],
        week=demo_state.get("current_week", 1),
        config=config,
        brand_awareness_index=np.random.uniform(0.3, 0.8),
        brand_consideration_index=np.random.uniform(0.2, 0.6),
        brand_loyalty_index=np.random.uniform(0.1, 0.5),
    )
    
    # Add retailer states for all retailers
    for retailer in SAMPLE_RETAILERS:
        retailer_state = ManufacturerRetailerState(
            retailer_id=retailer,
            week=state.week,
            total_spend=np.random.uniform(10000, 100000),
            total_impressions=np.random.uniform(100000, 1000000),
            total_conversions=np.random.uniform(500, 5000),
            total_revenue=np.random.uniform(50000, 500000),
            share_of_voice=np.random.uniform(0.05, 0.25),
            share_of_shelf=np.random.uniform(0.1, 0.3),
            share_of_search=np.random.uniform(0.05, 0.2),
            category_rank=np.random.randint(1, 10),
            price_index=np.random.uniform(0.9, 1.1),
        )
        
        # Add all channel states
        for channel in MediaChannel:
            ch_state = ManufacturerChannelState(
                channel=channel,
                week=state.week,
                spend=np.random.uniform(1000, 20000),
                impressions=np.random.uniform(10000, 200000),
                reach=np.random.uniform(5000, 80000),
                frequency=np.random.uniform(1.5, 4.0),
                clicks=np.random.uniform(200, 8000),
                click_through_rate=np.random.uniform(0.01, 0.05),
                video_views=np.random.uniform(0, 50000) if channel in [MediaChannel.VIDEO_AD, MediaChannel.CONNECTED_TV] else 0,
                video_completion_rate=np.random.uniform(0.3, 0.8) if channel in [MediaChannel.VIDEO_AD, MediaChannel.CONNECTED_TV] else 0,
                add_to_carts=np.random.uniform(100, 2000),
                purchases=np.random.uniform(50, 800),
                conversion_rate=np.random.uniform(0.02, 0.1),
                attributed_sales=np.random.uniform(3000, 80000),
                attributed_units=np.random.uniform(50, 1500),
                roas=np.random.uniform(1.5, 6.0),
                brand_search_lift=np.random.uniform(0, 0.15),
                new_to_brand_percentage=np.random.uniform(0.1, 0.4),
                cost_per_click=np.random.uniform(0.5, 2.5),
                cost_per_acquisition=np.random.uniform(5, 40),
            )
            retailer_state.channel_states[channel.value] = ch_state
        
        state.retailer_states[retailer] = retailer_state
    
    # Aggregate metrics
    state.aggregate_from_retailers()
    
    # Set elasticities
    for channel in MediaChannel:
        state.channel_elasticities[channel.value] = np.random.uniform(0.1, 0.25)
        state.channel_elasticity_uncertainty[channel.value] = np.random.uniform(0.02, 0.08)
    
    return state.to_dict()


@app.get("/api/media-channels")
async def get_media_channels():
    """Get list of all available media channels."""
    channels = []
    for channel in MediaChannel:
        channels.append({
            "id": channel.value,
            "name": channel.value.replace("_", " ").title(),
            "category": _get_channel_category(channel),
        })
    return {"channels": channels}


def _get_channel_category(channel: MediaChannel) -> str:
    """Get the category for a media channel."""
    search_channels = [MediaChannel.SPONSORED_SEARCH, MediaChannel.SPONSORED_PRODUCTS, MediaChannel.SPONSORED_BRANDS]
    display_channels = [MediaChannel.DISPLAY_AD, MediaChannel.WEBSITE_BANNER, MediaChannel.DIGITAL_ENDCAP, MediaChannel.IN_STORE_DISPLAY]
    brand_channels = [MediaChannel.BRAND_STORE, MediaChannel.BRAND_LANDING_PAGE]
    direct_channels = [MediaChannel.EMAIL, MediaChannel.APP_NOTIFICATION, MediaChannel.SMS]
    video_channels = [MediaChannel.CONNECTED_TV, MediaChannel.VIDEO_AD, MediaChannel.STREAMING_AUDIO]
    social_channels = [MediaChannel.SOCIAL_MEDIA, MediaChannel.INFLUENCER]
    programmatic_channels = [MediaChannel.DSP, MediaChannel.OFFSITE_DISPLAY]
    
    if channel in search_channels:
        return "Search & Discovery"
    elif channel in display_channels:
        return "Display Advertising"
    elif channel in brand_channels:
        return "Brand Destinations"
    elif channel in direct_channels:
        return "Direct Marketing"
    elif channel in video_channels:
        return "Video & Connected"
    elif channel in social_channels:
        return "Social & Influencer"
    elif channel in programmatic_channels:
        return "Programmatic"
    return "Other"


# ============================================================================
# RMN DIGITAL TWIN API ENDPOINTS
# ============================================================================

# Sample data for RMN Digital Twins
RMN_COMPANY = {
    "company_id": "kelloggs-001",
    "company_name": "Kellogg's",
    "company_code": "KEL",
    "industry": "Consumer Packaged Goods",
    "country": "US"
}

RMN_BRANDS = [
    {"brand_id": "brand-001", "brand_name": "Frosted Flakes", "brand_code": "FF", "category": "Cereal", "lifecycle_stage": "mature", "default_margin_rate": 0.35},
    {"brand_id": "brand-002", "brand_name": "Pop-Tarts", "brand_code": "PT", "category": "Toaster Pastries", "lifecycle_stage": "mature", "default_margin_rate": 0.32},
    {"brand_id": "brand-003", "brand_name": "Cheez-It", "brand_code": "CI", "category": "Crackers", "lifecycle_stage": "growth", "default_margin_rate": 0.38},
    {"brand_id": "brand-004", "brand_name": "Pringles", "brand_code": "PR", "category": "Snacks", "lifecycle_stage": "mature", "default_margin_rate": 0.30},
    {"brand_id": "brand-005", "brand_name": "Eggo", "brand_code": "EG", "category": "Frozen Breakfast", "lifecycle_stage": "mature", "default_margin_rate": 0.28},
    {"brand_id": "brand-006", "brand_name": "Special K", "brand_code": "SK", "category": "Cereal", "lifecycle_stage": "decline", "default_margin_rate": 0.33},
]

RMN_NETWORKS = [
    {"rmn_id": "rmn-walmart", "rmn_name": "Walmart Connect", "rmn_code": "WMT", "rmn_type": "retailer", "is_rollup_node": False},
    {"rmn_id": "rmn-target", "rmn_name": "Target Roundel", "rmn_code": "TGT", "rmn_type": "retailer", "is_rollup_node": False},
    {"rmn_id": "rmn-amazon", "rmn_name": "Amazon Advertising", "rmn_code": "AMZN", "rmn_type": "marketplace", "is_rollup_node": False},
    {"rmn_id": "rmn-instacart", "rmn_name": "Instacart Ads", "rmn_code": "IC", "rmn_type": "marketplace", "is_rollup_node": False},
    {"rmn_id": "rmn-albertsons", "rmn_name": "Albertsons Media Collective", "rmn_code": "ABS", "rmn_type": "retailer", "is_rollup_node": False},
    {"rmn_id": "rmn-total-us", "rmn_name": "Total US - MultiOutletC", "rmn_code": "TOTAL", "rmn_type": "rollup", "is_rollup_node": True},
]

RMN_CHANNEL_TYPES = ["search", "display", "video", "email"]


@app.get("/api/rmn-twins/company")
async def get_rmn_company():
    """Get the company (organization) digital twin."""
    return {
        **RMN_COMPANY,
        "brands": RMN_BRANDS,
        "total_brands": len(RMN_BRANDS),
        "rmn_count": len([r for r in RMN_NETWORKS if not r["is_rollup_node"]]),
    }


@app.get("/api/rmn-twins/brands")
async def get_rmn_brands():
    """Get all brand digital twins for the company."""
    import random
    brands_with_metrics = []
    for brand in RMN_BRANDS:
        brands_with_metrics.append({
            **brand,
            "total_spend": random.uniform(500000, 5000000),
            "total_incremental_sales": random.uniform(1000000, 15000000),
            "efficiency": random.uniform(1.5, 4.5),
            "active_rmn_programs": random.randint(3, 5),
            "active_campaigns": random.randint(5, 25),
        })
    return {"brands": brands_with_metrics}


@app.get("/api/rmn-twins/brands/{brand_id}")
async def get_rmn_brand(brand_id: str):
    """Get a specific brand digital twin with full details."""
    import random
    brand = next((b for b in RMN_BRANDS if b["brand_id"] == brand_id), None)
    if not brand:
        raise HTTPException(status_code=404, detail=f"Brand '{brand_id}' not found")
    
    # Build RMN programs for this brand
    programs = []
    for rmn in [r for r in RMN_NETWORKS if not r["is_rollup_node"]]:
        program = {
            "brand_rmn_program_id": f"prog-{brand_id}-{rmn['rmn_id']}",
            "brand_id": brand_id,
            "rmn_id": rmn["rmn_id"],
            "rmn_name": rmn["rmn_name"],
            "program_name": f"{brand['brand_name']} on {rmn['rmn_name']}",
            "billing_model": random.choice(["CPC", "CPM", "CPA"]),
            "attribution_window_days": random.choice([7, 14, 30]),
            "spend": random.uniform(100000, 1000000),
            "incremental_sales": random.uniform(200000, 3000000),
            "efficiency": random.uniform(1.5, 4.0),
            "channels": []
        }
        
        # Add channels for this program
        for ch_type in RMN_CHANNEL_TYPES:
            channel = {
                "channel_id": f"ch-{brand_id}-{rmn['rmn_id']}-{ch_type}",
                "channel_name": f"RMN {ch_type.upper()}",
                "channel_type": ch_type,
                "spend": random.uniform(20000, 250000),
                "impressions": random.randint(100000, 5000000),
                "clicks": random.randint(5000, 100000),
                "conversions": random.randint(500, 10000),
                "roas": random.uniform(1.5, 6.0),
                "cpc": random.uniform(0.5, 3.0),
            }
            program["channels"].append(channel)
        
        programs.append(program)
    
    return {
        **brand,
        "programs": programs,
        "total_spend": sum(p["spend"] for p in programs),
        "total_incremental_sales": sum(p["incremental_sales"] for p in programs),
        "overall_efficiency": sum(p["incremental_sales"] for p in programs) / max(1, sum(p["spend"] for p in programs)),
    }


@app.get("/api/rmn-twins/networks")
async def get_rmn_networks():
    """Get all retail media network digital twins."""
    import random
    networks_with_metrics = []
    for rmn in RMN_NETWORKS:
        if rmn["is_rollup_node"]:
            continue
        networks_with_metrics.append({
            **rmn,
            "total_spend": random.uniform(1000000, 10000000),
            "total_incremental_sales": random.uniform(2000000, 30000000),
            "efficiency": random.uniform(1.8, 4.2),
            "active_brands": random.randint(3, 6),
            "active_channels": len(RMN_CHANNEL_TYPES),
        })
    return {"networks": networks_with_metrics}


@app.get("/api/rmn-twins/networks/{rmn_id}")
async def get_rmn_network(rmn_id: str):
    """Get a specific RMN digital twin with full details."""
    import random
    rmn = next((r for r in RMN_NETWORKS if r["rmn_id"] == rmn_id), None)
    if not rmn:
        raise HTTPException(status_code=404, detail=f"RMN '{rmn_id}' not found")
    
    # Build brand programs for this RMN
    programs = []
    for brand in RMN_BRANDS:
        program = {
            "brand_rmn_program_id": f"prog-{brand['brand_id']}-{rmn_id}",
            "brand_id": brand["brand_id"],
            "brand_name": brand["brand_name"],
            "rmn_id": rmn_id,
            "program_name": f"{brand['brand_name']} on {rmn['rmn_name']}",
            "spend": random.uniform(100000, 1000000),
            "incremental_sales": random.uniform(200000, 3000000),
            "efficiency": random.uniform(1.5, 4.0),
        }
        programs.append(program)
    
    # Build channels for this RMN
    channels = []
    for ch_type in RMN_CHANNEL_TYPES:
        channel = {
            "channel_id": f"ch-{rmn_id}-{ch_type}",
            "channel_name": f"RMN {ch_type.upper()}",
            "channel_type": ch_type,
            "total_spend": random.uniform(200000, 2000000),
            "total_impressions": random.randint(1000000, 50000000),
            "total_conversions": random.randint(5000, 100000),
            "avg_roas": random.uniform(1.5, 5.0),
            "active_campaigns": random.randint(10, 50),
        }
        channels.append(channel)
    
    return {
        **rmn,
        "programs": programs,
        "channels": channels,
        "total_spend": sum(p["spend"] for p in programs),
        "total_incremental_sales": sum(p["incremental_sales"] for p in programs),
        "overall_efficiency": sum(p["incremental_sales"] for p in programs) / max(1, sum(p["spend"] for p in programs)),
    }


@app.get("/api/rmn-twins/optimization/scenarios")
async def get_optimization_scenarios():
    """Get optimization scenarios for comparison."""
    import random
    scenarios = [
        {
            "scenario_id": "scenario-current",
            "scenario_name": "Current Allocation",
            "objective": "maintain_revenue",
            "total_spend": 15000000,
            "total_incremental_sales": 45000000,
            "efficiency": 3.0,
        },
        {
            "scenario_id": "scenario-optimized",
            "scenario_name": "Optimized Allocation",
            "objective": "increase_revenue",
            "total_spend": 15000000,
            "total_incremental_sales": 52500000,
            "efficiency": 3.5,
        },
    ]
    
    # Add channel-level recommendations
    for scenario in scenarios:
        scenario["channel_allocation"] = {}
        for ch_type in RMN_CHANNEL_TYPES:
            if scenario["scenario_id"] == "scenario-current":
                allocation = random.uniform(2000000, 5000000)
            else:
                # Optimized shifts budget toward higher-performing channels
                if ch_type in ["search", "display"]:
                    allocation = random.uniform(3500000, 6000000)
                else:
                    allocation = random.uniform(1000000, 3000000)
            scenario["channel_allocation"][ch_type] = allocation
    
    return {
        "scenarios": scenarios,
        "lift": (scenarios[1]["total_incremental_sales"] - scenarios[0]["total_incremental_sales"]) / scenarios[0]["total_incremental_sales"],
    }


@app.get("/api/rmn-twins/performance/summary")
async def get_rmn_performance_summary():
    """Get aggregated performance summary across all RMN programs."""
    import random
    
    # By Brand
    brand_performance = []
    for brand in RMN_BRANDS:
        brand_performance.append({
            "brand_id": brand["brand_id"],
            "brand_name": brand["brand_name"],
            "spend": random.uniform(500000, 3000000),
            "incremental_sales": random.uniform(1000000, 10000000),
            "efficiency": random.uniform(1.5, 4.5),
        })
    
    # By RMN
    rmn_performance = []
    for rmn in [r for r in RMN_NETWORKS if not r["is_rollup_node"]]:
        rmn_performance.append({
            "rmn_id": rmn["rmn_id"],
            "rmn_name": rmn["rmn_name"],
            "spend": random.uniform(1000000, 5000000),
            "incremental_sales": random.uniform(2000000, 15000000),
            "efficiency": random.uniform(1.8, 4.2),
        })
    
    # By Channel Type
    channel_performance = []
    for ch_type in RMN_CHANNEL_TYPES:
        channel_performance.append({
            "channel_type": ch_type,
            "channel_name": f"RMN {ch_type.upper()}",
            "spend": random.uniform(2000000, 8000000),
            "incremental_sales": random.uniform(4000000, 25000000),
            "efficiency": random.uniform(1.5, 4.0),
        })
    
    return {
        "by_brand": brand_performance,
        "by_rmn": rmn_performance,
        "by_channel": channel_performance,
        "total_spend": sum(b["spend"] for b in brand_performance),
        "total_incremental_sales": sum(b["incremental_sales"] for b in brand_performance),
        "overall_efficiency": sum(b["incremental_sales"] for b in brand_performance) / max(1, sum(b["spend"] for b in brand_performance)),
    }


# ============================================================================
# DATA FEDERATION API ENDPOINTS
# ============================================================================

# Database categories
DATABASE_CATEGORIES = [
    'BRAND', 'COMPETITION', 'CONSUMER PROMOTIONS', 'DISTRIBUTION',
    'E-COMM DIGITAL', 'ENVIRONMENTAL FACTORS', 'PAID MEDIA',
    'PUBLIC RELATIONS', 'RETAIL MEDIA', 'SHOPPER MARKETING', 'TRADE SUPPORT'
]

# Retailer configurations for data federation
FEDERATION_RETAILERS = [
    {"id": "walmart", "name": "Walmart", "normalization_crew": "Walmart RMN Normalization Crew"},
    {"id": "target", "name": "Target", "normalization_crew": "Target RMN Normalization Crew"},
    {"id": "amazon", "name": "Amazon", "normalization_crew": "Amazon Ads Normalization Crew"},
    {"id": "instacart", "name": "Instacart", "normalization_crew": "Instacart Ads Normalization Crew"},
    {"id": "albertsons", "name": "Albertsons", "normalization_crew": "Albertsons Media Normalization Crew"},
]

# Simulated database sources
federation_state = {
    "databases": [],
    "agent_teams": [],
    "connections": {}
}

def init_federation_databases():
    """Initialize simulated database sources"""
    databases = []
    db_id = 0
    
    # Brand databases
    for category in ['BRAND', 'PAID MEDIA', 'PUBLIC RELATIONS']:
        db_id += 1
        databases.append({
            "id": f"db_{db_id}",
            "name": f"Brand {category.title()} DB",
            "category": category,
            "owner": "brand",
            "status": np.random.choice(["connection_pending", "agent_deployed", "agent_working", "agent_complete"], p=[0.1, 0.2, 0.3, 0.4]),
            "lastSync": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "recordCount": np.random.randint(10000, 500000),
        })
    
    # Retailer databases
    for retailer in FEDERATION_RETAILERS:
        for category in ['RETAIL MEDIA', 'SHOPPER MARKETING', 'E-COMM DIGITAL', 'DISTRIBUTION']:
            db_id += 1
            databases.append({
                "id": f"db_{db_id}",
                "name": f"{retailer['name']} {category.title()}",
                "category": category,
                "owner": "retailer",
                "retailer": retailer["id"],
                "status": np.random.choice(["connection_pending", "agent_deployed", "agent_working", "agent_complete"], p=[0.1, 0.2, 0.3, 0.4]),
                "lastSync": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "recordCount": np.random.randint(50000, 2000000),
            })
    
    return databases

# Initialize on startup
federation_state["databases"] = init_federation_databases()


@app.get("/api/data-federation/databases")
async def get_federation_databases():
    """Get list of all federated databases with status"""
    return {"databases": federation_state["databases"]}


@app.get("/api/data-federation/retailers")
async def get_federation_retailers():
    """Get list of retailer connections with their databases"""
    retailers = []
    for retailer in FEDERATION_RETAILERS:
        retailer_dbs = [db for db in federation_state["databases"] if db.get("retailer") == retailer["id"]]
        
        # Determine overall status based on database statuses
        statuses = [db["status"] for db in retailer_dbs]
        if all(s == "agent_complete" for s in statuses):
            overall_status = "agent_complete"
        elif any(s == "agent_working" for s in statuses):
            overall_status = "agent_working"
        elif any(s == "agent_deployed" for s in statuses):
            overall_status = "agent_deployed"
        else:
            overall_status = "connection_pending"
        
        retailers.append({
            "id": retailer["id"],
            "name": retailer["name"],
            "databases": retailer_dbs,
            "status": overall_status,
            "normalizationCrew": retailer["normalization_crew"],
            "lastActivity": datetime.now().strftime("%H:%M:%S"),
        })
    
    return {"retailers": retailers}


@app.get("/api/data-federation/agents/status")
async def get_federation_agent_status():
    """Get status of all active agent teams"""
    teams = []
    
    # Data Federation Crew (TEE agents)
    teams.append({
        "teamId": "tee-federation-crew",
        "teamName": "TEE Data Federation Crew",
        "currentPhase": "Data Validation & Privacy Enforcement",
        "overallProgress": 75,
        "agents": [
            {"id": "a1", "name": "Data Connector", "role": "Discovers and validates data sources", "status": "complete", "progress": 100, "lastMessage": "Connected to 23 data sources"},
            {"id": "a2", "name": "Schema Mapper", "role": "Canonicalizes identities across sources", "status": "complete", "progress": 100, "lastMessage": "Mapped 156 schema fields"},
            {"id": "a3", "name": "Metric Engineer", "role": "Computes aggregates and features", "status": "working", "progress": 68, "lastMessage": "Processing retail media metrics..."},
            {"id": "a4", "name": "DP Steward", "role": "Applies differential privacy", "status": "idle", "progress": 0, "lastMessage": "Waiting for pre-DP aggregates"},
            {"id": "a5", "name": "Spend Optimizer", "role": "Optimizes using DP-protected data", "status": "idle", "progress": 0, "lastMessage": "Pending DP release"},
            {"id": "a6", "name": "Audit Agent", "role": "Produces evidence packs", "status": "idle", "progress": 0, "lastMessage": "Ready to collect audit trail"},
            {"id": "a7", "name": "Proof Agent", "role": "Generates ZK proofs (optional)", "status": "idle", "progress": 0, "lastMessage": "ZK proofs disabled"},
        ]
    })
    
    # Add active RMN normalization crews
    for retailer in FEDERATION_RETAILERS[:2]:  # Show first 2 as active
        teams.append({
            "teamId": f"{retailer['id']}-normalization",
            "teamName": retailer["normalization_crew"],
            "currentPhase": "Semantic Normalization",
            "overallProgress": np.random.randint(40, 90),
            "agents": [
                {"id": "n1", "name": "Schema Discovery", "role": "Discovers RMN-specific schemas", "status": "complete", "progress": 100, "lastMessage": f"Found {retailer['name']} API schemas"},
                {"id": "n2", "name": "Attribution Mapper", "role": "Maps attribution models to canonical", "status": "working", "progress": np.random.randint(30, 80), "lastMessage": "Mapping attribution windows..."},
                {"id": "n3", "name": "Taxonomy Translator", "role": "Translates retailer tags/categories", "status": "working", "progress": np.random.randint(20, 70), "lastMessage": "Translating product taxonomy..."},
                {"id": "n4", "name": "Data Validator", "role": "Validates normalized output", "status": "idle", "progress": 0, "lastMessage": "Awaiting normalized data"},
            ]
        })
    
    return {"teams": teams}


@app.post("/api/data-federation/connect")
async def connect_database(request: dict):
    """Initiate connection to a new data source"""
    retailer_id = request.get("retailer_id")
    category = request.get("category")
    
    # Find and update database status
    for db in federation_state["databases"]:
        if db.get("retailer") == retailer_id and db.get("category") == category:
            db["status"] = "agent_deployed"
            return {"success": True, "message": f"Connection initiated for {retailer_id} {category}"}
    
    return {"success": False, "message": "Database not found"}


@app.post("/api/data-federation/deploy-agents")
async def deploy_agents(request: dict):
    """Deploy agent team to a database"""
    database_id = request.get("database_id")
    
    # Find and update database status
    for db in federation_state["databases"]:
        if db["id"] == database_id:
            if db["status"] == "connection_pending":
                db["status"] = "agent_deployed"
            elif db["status"] == "agent_deployed":
                db["status"] = "agent_working"
            return {"success": True, "message": f"Agents deployed to {database_id}", "new_status": db["status"]}
    
    return {"success": False, "message": "Database not found"}


# Activity tracking state
activity_state = {
    "events": [],
    "event_counter": 0
}

# Normalization status state
normalization_state = {
    "status": [
        {
            "retailerId": "walmart",
            "retailerName": "Walmart",
            "crewName": "Walmart Connect Normalization Crew",
            "status": "mapping",
            "currentAgent": "Schema Mapper Agent",
            "campaignsNormalized": 156,
            "performanceRecords": 4520,
            "productsNormalized": 892,
            "errors": 0,
            "lastActivity": "2026-01-30T17:10:00Z"
        },
        {
            "retailerId": "target",
            "retailerName": "Target",
            "crewName": "Target Roundel Normalization Crew",
            "status": "validating",
            "currentAgent": "Data Validator Agent",
            "campaignsNormalized": 89,
            "performanceRecords": 2130,
            "productsNormalized": 456,
            "errors": 2,
            "lastActivity": "2026-01-30T17:08:00Z"
        },
        {
            "retailerId": "amazon",
            "retailerName": "Amazon",
            "crewName": "Amazon Ads Normalization Crew",
            "status": "discovering",
            "currentAgent": "Schema Discovery Agent",
            "campaignsNormalized": 0,
            "performanceRecords": 0,
            "productsNormalized": 0,
            "errors": 0,
            "lastActivity": "2026-01-30T17:12:00Z"
        },
        {
            "retailerId": "instacart",
            "retailerName": "Instacart",
            "crewName": "Instacart Ads Normalization Crew",
            "status": "complete",
            "currentAgent": None,
            "campaignsNormalized": 45,
            "performanceRecords": 1200,
            "productsNormalized": 234,
            "errors": 0,
            "lastActivity": "2026-01-30T17:05:00Z"
        },
        {
            "retailerId": "albertsons",
            "retailerName": "Albertsons",
            "crewName": "Albertsons Media Collective Normalization Crew",
            "status": "idle",
            "currentAgent": None,
            "campaignsNormalized": 0,
            "performanceRecords": 0,
            "productsNormalized": 0,
            "errors": 0,
            "lastActivity": None
        }
    ]
}

# TEE status state
tee_state = {
    "connected": True,
    "agentsAvailable": 7,
    "agentsActive": 3,
    "privacyBudgetUsed": 0.15,
    "privacyBudgetTotal": 1.0,
    "dpReleasesIssued": 24,
    "proofsGenerated": 8,
    "auditTrailEntries": 156,
    "lastHeartbeat": "2026-01-30T17:14:30Z"
}


@app.get("/api/data-federation/organization")
async def get_organization():
    """Get organization data with retailer data sources hierarchy"""
    import random
    
    # Kelloggs organization with retailer data sources
    organization = {
        "id": "kelloggs",
        "name": "Kellogg's",
        "totalDatabases": 0,
        "totalRecords": 0,
        "retailerDataSources": []
    }
    
    retailers_config = [
        {
            "id": "walmart",
            "name": "Walmart",
            "databases": [
                {"id": "wm_retail_media", "name": "Retail Media Performance", "category": "RETAIL MEDIA", "recordCount": 1250000},
                {"id": "wm_shopper", "name": "Shopper Marketing", "category": "SHOPPER MARKETING", "recordCount": 890000},
                {"id": "wm_trade", "name": "Trade Promotions", "category": "TRADE SUPPORT", "recordCount": 456000},
            ]
        },
        {
            "id": "target",
            "name": "Target",
            "databases": [
                {"id": "tgt_roundel", "name": "Roundel Campaign Data", "category": "RETAIL MEDIA", "recordCount": 780000},
                {"id": "tgt_promo", "name": "Consumer Promotions", "category": "CONSUMER PROMOTIONS", "recordCount": 345000},
            ]
        },
        {
            "id": "amazon",
            "name": "Amazon",
            "databases": [
                {"id": "amz_ads", "name": "Amazon Advertising", "category": "RETAIL MEDIA", "recordCount": 2100000},
                {"id": "amz_dsp", "name": "DSP Display", "category": "PAID MEDIA", "recordCount": 890000},
                {"id": "amz_brand", "name": "Brand Analytics", "category": "BRAND", "recordCount": 567000},
            ]
        },
        {
            "id": "instacart",
            "name": "Instacart",
            "databases": [
                {"id": "ic_ads", "name": "Instacart Ads", "category": "RETAIL MEDIA", "recordCount": 456000},
                {"id": "ic_basket", "name": "Basket Analytics", "category": "E-COMM DIGITAL", "recordCount": 234000},
            ]
        },
        {
            "id": "albertsons",
            "name": "Albertsons",
            "databases": [
                {"id": "abs_media", "name": "Media Collective", "category": "RETAIL MEDIA", "recordCount": 567000},
                {"id": "abs_loyalty", "name": "Loyalty Data", "category": "SHOPPER MARKETING", "recordCount": 890000},
            ]
        }
    ]
    
    tee_agents = [
        {"id": "data_connector", "name": "Data Connector"},
        {"id": "schema_mapper", "name": "Schema Mapper"},
        {"id": "metric_engineer", "name": "Metric Engineer"},
        {"id": "dp_steward", "name": "DP Steward"},
        {"id": "spend_optimizer", "name": "Spend Optimizer"},
        {"id": "audit_evidence", "name": "Audit Evidence"},
        {"id": "proof_agent", "name": "Proof Agent"},
    ]
    
    for retailer in retailers_config:
        # Simulate varying statuses
        tee_statuses = ['idle', 'deployed', 'working', 'complete']
        norm_statuses = ['idle', 'discovering', 'mapping', 'validating', 'complete']
        
        # Assign statuses based on retailer for variety
        if retailer["id"] == "walmart":
            tee_status = "working"
            norm_status = "mapping"
        elif retailer["id"] == "target":
            tee_status = "working"
            norm_status = "validating"
        elif retailer["id"] == "amazon":
            tee_status = "deployed"
            norm_status = "discovering"
        elif retailer["id"] == "instacart":
            tee_status = "complete"
            norm_status = "complete"
        else:
            tee_status = "idle"
            norm_status = "idle"
        
        # Create agent list with statuses
        agents = []
        for i, agent in enumerate(tee_agents):
            if tee_status == "complete":
                agent_status = "complete"
            elif tee_status == "working":
                if i < 4:
                    agent_status = "complete"
                elif i == 4:
                    agent_status = "working"
                else:
                    agent_status = "idle"
            elif tee_status == "deployed":
                if i < 2:
                    agent_status = "working"
                else:
                    agent_status = "idle"
            else:
                agent_status = "idle"
            
            agents.append({
                "id": agent["id"],
                "name": agent["name"],
                "status": agent_status,
                "progress": random.randint(40, 95) if agent_status == "working" else None,
                "lastMessage": "Processing batch..." if agent_status == "working" else None
            })
        
        # Build databases with statuses
        databases = []
        for db in retailer["databases"]:
            databases.append({
                **db,
                "status": "ready" if tee_status in ["working", "complete"] else "syncing" if tee_status == "deployed" else "ready"
            })
        
        retailer_source = {
            "id": retailer["id"],
            "name": retailer["name"],
            "connected": True,
            "databases": databases,
            "teeTeam": {
                "status": tee_status,
                "agents": agents,
                "privacyBudgetUsed": random.uniform(0.05, 0.3) if tee_status != "idle" else 0,
                "privacyBudgetTotal": 1.0,
                "dpReleasesIssued": random.randint(10, 50) if tee_status in ["working", "complete"] else 0,
                "proofsGenerated": random.randint(3, 15) if tee_status in ["working", "complete"] else 0,
            },
            "normalizationTeam": {
                "status": norm_status,
                "currentAgent": "Schema Mapper Agent" if norm_status == "mapping" else "Data Validator Agent" if norm_status == "validating" else "Schema Discovery Agent" if norm_status == "discovering" else None,
                "campaignsNormalized": random.randint(50, 200) if norm_status not in ["idle", "discovering"] else 0,
                "performanceRecords": random.randint(1000, 5000) if norm_status not in ["idle", "discovering"] else 0,
                "productsNormalized": random.randint(200, 900) if norm_status not in ["idle", "discovering"] else 0,
                "errors": random.randint(0, 3) if norm_status not in ["idle", "complete"] else 0,
            }
        }
        
        organization["retailerDataSources"].append(retailer_source)
        organization["totalDatabases"] += len(databases)
        organization["totalRecords"] += sum(db["recordCount"] for db in databases)
    
    return organization


@app.get("/api/data-federation/activity")
async def get_activity():
    """Get activity events for the data federation pipeline"""
    import random
    from datetime import datetime, timedelta
    
    # Generate some sample activity events
    activity_types = [
        ("database", "info", "Connection Check", "Validating connection to {retailer} database"),
        ("database", "success", "Data Synced", "Successfully synced {count} records from {retailer}"),
        ("database", "progress", "Scanning Schema", "Discovering schema for {retailer} {category} database"),
        ("normalization", "progress", "Mapping Fields", "Mapping {count} fields to canonical schema"),
        ("normalization", "success", "Batch Complete", "Normalized {count} records for {retailer}"),
        ("tee", "progress", "DP Computing", "Computing differentially private metrics"),
        ("tee", "success", "DP Release", "Released DP-protected metric with ε={epsilon}"),
        ("tee", "info", "Audit Log", "Recorded audit entry for {action}"),
    ]
    
    retailers = ["Walmart", "Target", "Amazon", "Instacart", "Albertsons"]
    categories = ["RETAIL MEDIA", "PAID MEDIA", "E-COMM DIGITAL"]
    
    events = []
    base_time = datetime.now()
    
    for i in range(15):
        event_type = random.choice(activity_types)
        retailer = random.choice(retailers)
        
        message = event_type[3].format(
            retailer=retailer,
            count=random.randint(100, 5000),
            category=random.choice(categories),
            epsilon=round(random.uniform(0.01, 0.1), 3),
            action=random.choice(["metric_release", "proof_generation", "schema_validation"])
        )
        
        events.append({
            "id": f"evt_{i}_{random.randint(1000, 9999)}",
            "timestamp": (base_time - timedelta(seconds=i * random.randint(30, 120))).strftime("%Y-%m-%d %H:%M:%S"),
            "source": event_type[0],
            "level": event_type[1],
            "title": event_type[2],
            "message": message,
            "retailer": retailer if event_type[0] != "tee" else None
        })
    
    return {"events": events}


@app.get("/api/data-federation/normalization/status")
async def get_normalization_status():
    """Get status of all normalization crews"""
    import random
    
    # Simulate some progress
    for status in normalization_state["status"]:
        if status["status"] == "mapping":
            status["campaignsNormalized"] += random.randint(1, 5)
            status["performanceRecords"] += random.randint(10, 50)
            status["productsNormalized"] += random.randint(2, 10)
        elif status["status"] == "discovering":
            if random.random() > 0.7:
                status["status"] = "mapping"
                status["currentAgent"] = "Schema Mapper Agent"
        elif status["status"] == "validating":
            if random.random() > 0.8:
                status["status"] = "complete"
                status["currentAgent"] = None
    
    return {"status": normalization_state["status"]}


@app.get("/api/data-federation/tee/status")
async def get_tee_status():
    """Get TEE environment status"""
    import random
    from datetime import datetime
    
    # Simulate some activity
    if random.random() > 0.7:
        tee_state["dpReleasesIssued"] += 1
        tee_state["privacyBudgetUsed"] = min(1.0, tee_state["privacyBudgetUsed"] + 0.005)
    
    if random.random() > 0.8:
        tee_state["proofsGenerated"] += 1
    
    if random.random() > 0.5:
        tee_state["auditTrailEntries"] += random.randint(1, 3)
    
    tee_state["agentsActive"] = random.randint(1, 5)
    tee_state["lastHeartbeat"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
    
    return tee_state


# ============================================================================
# TEE STATE API ENDPOINTS (Per-Retailer)
# ============================================================================

RETAILER_NAMES = {
    "walmart": "Walmart",
    "target": "Target",
    "amazon": "Amazon",
    "instacart": "Instacart",
    "albertsons": "Albertsons",
}


@app.get("/api/tee/state/{retailer_id}")
async def get_retailer_tee_state(retailer_id: str):
    """Get comprehensive TEE state for a specific retailer dataset."""
    import random
    from datetime import datetime, timedelta
    
    retailer_name = RETAILER_NAMES.get(retailer_id, retailer_id.title())
    dataset_id = f"{retailer_id}_rmn_data_2024"
    
    # Generate release history
    history = []
    base_time = datetime.now()
    aggregate_types = ["count", "sum", "mean", "histogram", "quantile"]
    mechanisms = ["laplace", "gaussian", "thresholded_laplace"]
    
    for i in range(random.randint(5, 15)):
        history.append({
            "receipt_id": f"rcpt-{retailer_id}-{random.randint(10000, 99999)}",
            "job_id": f"job-{retailer_id[:3]}-{random.randint(1000, 9999)}",
            "aggregate_type": random.choice(aggregate_types),
            "epsilon_consumed": round(random.uniform(0.1, 1.5), 3),
            "mechanism": random.choice(mechanisms),
            "released_at": (base_time - timedelta(hours=i * random.randint(1, 12))).isoformat(),
            "integrity_verified": random.random() > 0.1,
            "released_value": round(random.uniform(1000, 50000), 2),
        })
    
    # Assign statuses based on retailer
    if retailer_id == "walmart":
        norm_status = "mapping"
        consumed_epsilon = random.uniform(0.15, 0.35)
    elif retailer_id == "target":
        norm_status = "validating"
        consumed_epsilon = random.uniform(0.25, 0.45)
    elif retailer_id == "amazon":
        norm_status = "discovering"
        consumed_epsilon = random.uniform(0.05, 0.15)
    elif retailer_id == "instacart":
        norm_status = "complete"
        consumed_epsilon = random.uniform(0.40, 0.60)
    else:
        norm_status = "idle"
        consumed_epsilon = 0.0
    
    total_epsilon = 1.0
    
    state = {
        "retailerId": retailer_id,
        "retailerName": retailer_name,
        "health": {
            "status": "healthy",
            "version": "1.2.0",
            "database_healthy": True,
            "redis_healthy": True,
            "keylime_enabled": retailer_id in ["walmart", "target"],
            "keylime_healthy": True if retailer_id in ["walmart", "target"] else None,
            "zk_enabled": retailer_id in ["walmart"],
            "zk_healthy": True if retailer_id == "walmart" else None,
        },
        "budget": {
            "dataset_id": dataset_id,
            "total_epsilon": total_epsilon,
            "consumed_epsilon": round(consumed_epsilon, 3),
            "remaining_epsilon": round(total_epsilon - consumed_epsilon, 3),
            "release_count": len(history),
            "is_exhausted": consumed_epsilon >= total_epsilon,
        },
        "releaseHistory": history,
        "normalization": {
            "status": norm_status,
            "currentAgent": "Schema Mapper Agent" if norm_status == "mapping" else 
                          "Data Validator Agent" if norm_status == "validating" else
                          "Schema Discovery Agent" if norm_status == "discovering" else None,
            "fieldsDiscovered": random.randint(50, 150) if norm_status != "idle" else 0,
            "fieldsMapped": random.randint(30, 100) if norm_status not in ["idle", "discovering"] else 0,
            "recordsValidated": random.randint(10000, 100000) if norm_status in ["validating", "complete"] else 0,
            "errors": [] if norm_status == "complete" else [f"Warning: field mapping for '{random.choice(['ad_type', 'campaign_id', 'spend_amt'])}' may need review"] if random.random() > 0.7 else [],
            "schemaVersion": "v2.1.0" if norm_status in ["mapping", "validating", "complete"] else None,
            "lastUpdated": datetime.now().isoformat(),
        },
        "capabilities": {
            "dpGate": {
                "enabled": True,
                "healthy": True,
                "budgetEnforced": True,
            },
            "keylime": {
                "enabled": retailer_id in ["walmart", "target"],
                "healthy": True if retailer_id in ["walmart", "target"] else None,
            },
            "zkProofs": {
                "enabled": retailer_id == "walmart",
                "healthy": True if retailer_id == "walmart" else None,
            },
        },
    }
    
    return state


# ============================================================================
# BAYESIAN DIGITAL TWIN API ENDPOINTS
# ============================================================================

@app.get("/api/bayesian/entity/{entity_type}/{entity_id}")
async def get_entity_bayesian_state(entity_type: str, entity_id: str):
    """Get comprehensive Bayesian state for a digital twin entity."""
    import random
    from datetime import datetime, timedelta
    
    # Simulate Bayesian posteriors for the entity
    base_incr_sales = random.uniform(500000, 2000000)
    base_efficiency = random.uniform(0.8, 1.5)
    
    state = {
        "entity_type": entity_type,
        "entity_id": entity_id,
        "primary_kpi_posteriors": {
            "incremental_sales": {
                "posterior_mean": base_incr_sales,
                "posterior_std": base_incr_sales * 0.15,
                "ci_90": [base_incr_sales * 0.75, base_incr_sales * 1.25],
                "prob_positive": random.uniform(0.85, 0.99),
                "n_observations": random.randint(50, 200),
                "evidence_strength": random.uniform(0.6, 0.95),
            },
            "efficiency": {
                "posterior_mean": base_efficiency,
                "posterior_std": base_efficiency * 0.1,
                "ci_90": [base_efficiency * 0.85, base_efficiency * 1.15],
                "prob_above_threshold": random.uniform(0.7, 0.95),
                "threshold_value": 1.0,
            },
            "index": {
                "posterior_mean": random.uniform(95, 120),
                "posterior_std": random.uniform(5, 15),
            },
        },
        "lift_decompositions": {
            "prior_period": {
                "baseline_posterior_mean": base_incr_sales * 0.9,
                "actual_posterior_mean": base_incr_sales,
                "lift_posterior_mean": base_incr_sales * 0.1,
                "lift_pct_mean": random.uniform(5, 15),
                "prob_positive_lift": random.uniform(0.75, 0.95),
            },
            "year_ago": {
                "baseline_posterior_mean": base_incr_sales * 0.85,
                "actual_posterior_mean": base_incr_sales,
                "lift_posterior_mean": base_incr_sales * 0.15,
                "lift_pct_mean": random.uniform(10, 20),
                "prob_positive_lift": random.uniform(0.8, 0.98),
            },
        },
        "rankings": {
            "prob_rank_1": random.uniform(0.1, 0.4),
            "prob_top_3": random.uniform(0.4, 0.8),
            "expected_rank": random.uniform(1, 5),
            "total_entities": random.randint(5, 15),
        },
        "last_updated": datetime.now().isoformat(),
        "model_version": "v1.0.0",
    }
    
    return state


@app.get("/api/bayesian/brands")
async def get_brands_bayesian_state():
    """Get Bayesian posteriors for all brands."""
    import random
    from datetime import datetime
    
    brands = [
        {"id": "brand-001", "name": "Frosted Flakes", "category": "Cereal"},
        {"id": "brand-002", "name": "Pop-Tarts", "category": "Toaster Pastries"},
        {"id": "brand-003", "name": "Cheez-It", "category": "Crackers"},
        {"id": "brand-004", "name": "Pringles", "category": "Snacks"},
        {"id": "brand-005", "name": "Eggo", "category": "Frozen Breakfast"},
        {"id": "brand-006", "name": "Special K", "category": "Cereal"},
    ]
    
    result = []
    for brand in brands:
        base_incr = random.uniform(300000, 1500000)
        base_eff = random.uniform(0.7, 1.4)
        
        result.append({
            "brand_id": brand["id"],
            "brand_name": brand["name"],
            "category": brand["category"],
            "bayesian_outputs": {
                "incremental_sales": {
                    "mean": base_incr,
                    "std": base_incr * 0.12,
                    "ci": [base_incr * 0.78, base_incr * 1.22],
                },
                "efficiency_mean": base_eff,
                "efficiency_std": base_eff * 0.08,
                "index_mean": random.uniform(90, 125),
                "lift_vs_prior_period": random.uniform(3, 18),
                "lift_vs_year_ago": random.uniform(5, 22),
                "prob_positive_lift": random.uniform(0.75, 0.98),
                "last_updated": datetime.now().isoformat(),
            },
            "driver_rankings": [
                {"driver": "RMN SEARCH", "prob_top_contributor": random.uniform(0.2, 0.5)},
                {"driver": "RMN DISPLAY", "prob_top_contributor": random.uniform(0.15, 0.35)},
                {"driver": "RMN VIDEO", "prob_top_contributor": random.uniform(0.1, 0.25)},
                {"driver": "RMN EMAIL", "prob_top_contributor": random.uniform(0.05, 0.15)},
            ],
        })
    
    return {"brands": result}


@app.get("/api/bayesian/rmns")
async def get_rmns_bayesian_state():
    """Get Bayesian posteriors for all RMNs."""
    import random
    from datetime import datetime
    
    rmns = [
        {"id": "rmn-walmart", "name": "Walmart Connect"},
        {"id": "rmn-target", "name": "Target Roundel"},
        {"id": "rmn-amazon", "name": "Amazon Advertising"},
        {"id": "rmn-instacart", "name": "Instacart Ads"},
        {"id": "rmn-albertsons", "name": "Albertsons Media Collective"},
    ]
    
    result = []
    for rmn in rmns:
        base_incr = random.uniform(800000, 3000000)
        base_eff = random.uniform(0.9, 1.6)
        
        result.append({
            "rmn_id": rmn["id"],
            "rmn_name": rmn["name"],
            "bayesian_outputs": {
                "incremental_sales": {
                    "mean": base_incr,
                    "std": base_incr * 0.1,
                    "ci": [base_incr * 0.82, base_incr * 1.18],
                },
                "efficiency_mean": base_eff,
                "efficiency_std": base_eff * 0.07,
                "index_mean": random.uniform(92, 118),
                "prob_best_overall": random.uniform(0.05, 0.35),
                "expected_rank": random.uniform(1, 5),
                "last_updated": datetime.now().isoformat(),
            },
            "channel_mix": {
                "search": random.uniform(0.25, 0.45),
                "display": random.uniform(0.2, 0.35),
                "video": random.uniform(0.1, 0.25),
                "email": random.uniform(0.05, 0.15),
            },
        })
    
    return {"rmns": result}


@app.get("/api/bayesian/channels/{rmn_id}")
async def get_channels_bayesian_state(rmn_id: str):
    """Get Bayesian posteriors for channels within an RMN."""
    import random
    from datetime import datetime
    
    channels = ["search", "display", "video", "email"]
    
    result = []
    for ch_type in channels:
        base_incr = random.uniform(100000, 800000)
        base_eff = random.uniform(0.8, 1.8)
        base_elasticity = random.uniform(0.08, 0.25)
        
        result.append({
            "channel_id": f"ch-{rmn_id}-{ch_type}",
            "channel_name": f"RMN {ch_type.upper()}",
            "channel_type": ch_type,
            "rmn_id": rmn_id,
            "bayesian_outputs": {
                "incremental_sales": {
                    "mean": base_incr,
                    "std": base_incr * 0.15,
                    "ci": [base_incr * 0.72, base_incr * 1.28],
                },
                "efficiency_mean": base_eff,
                "efficiency_std": base_eff * 0.1,
                "index_mean": random.uniform(85, 130),
                "elasticity": {
                    "mean": base_elasticity,
                    "std": base_elasticity * 0.2,
                    "ci": [base_elasticity * 0.65, base_elasticity * 1.35],
                },
                "contribution_mean": base_incr,
                "contribution_pct_mean": random.uniform(0.1, 0.4),
                "prob_efficiency_above_target": random.uniform(0.6, 0.95),
                "efficiency_target": 1.0,
                "prob_rank_1_within_rmn": random.uniform(0.1, 0.5),
                "expected_rank_within_rmn": random.uniform(1, 4),
                "last_updated": datetime.now().isoformat(),
            },
        })
    
    return {"channels": result, "rmn_id": rmn_id}


@app.get("/api/bayesian/drivers")
async def get_drivers_bayesian_state():
    """Get Bayesian posteriors for marketing drivers."""
    import random
    from datetime import datetime
    
    drivers = [
        {"id": "driver-rmn-search", "name": "RMN SEARCH", "category": "RETAIL MEDIA", "is_rmn": True},
        {"id": "driver-rmn-display", "name": "RMN DISPLAY", "category": "RETAIL MEDIA", "is_rmn": True},
        {"id": "driver-rmn-video", "name": "RMN VIDEO", "category": "RETAIL MEDIA", "is_rmn": True},
        {"id": "driver-rmn-email", "name": "RMN EMAIL", "category": "RETAIL MEDIA", "is_rmn": True},
        {"id": "driver-tv", "name": "TV", "category": "PAID MEDIA", "is_rmn": False},
        {"id": "driver-digital", "name": "DIGITAL", "category": "PAID MEDIA", "is_rmn": False},
        {"id": "driver-tpd", "name": "TPD", "category": "TRADE SUPPORT", "is_rmn": False},
        {"id": "driver-feature", "name": "FEATURE", "category": "PROMO", "is_rmn": False},
        {"id": "driver-display-promo", "name": "DISPLAY", "category": "PROMO", "is_rmn": False},
    ]
    
    result = []
    for driver in drivers:
        contribution = random.uniform(50000, 500000)
        
        result.append({
            "driver_id": driver["id"],
            "driver_name": driver["name"],
            "driver_category": driver["category"],
            "is_rmn_channel": driver["is_rmn"],
            "bayesian_outputs": {
                "contribution_posterior": {
                    "mean": contribution,
                    "std": contribution * 0.18,
                    "ci": [contribution * 0.68, contribution * 1.32],
                },
                "contribution_pct_posterior": {
                    "mean": random.uniform(0.02, 0.15),
                    "std": random.uniform(0.005, 0.03),
                },
                "prob_rank_1_contributor": random.uniform(0.02, 0.2),
                "prob_top_10_contributor": random.uniform(0.3, 0.9),
                "incremental_probability": random.uniform(0.6, 0.95) if "CANNIBAL" not in driver["name"] else random.uniform(0.1, 0.4),
                "cannibalization_probability": random.uniform(0.05, 0.4) if "CANNIBAL" not in driver["name"] else random.uniform(0.6, 0.9),
                "last_updated": datetime.now().isoformat(),
            },
        })
    
    return {"drivers": result}


@app.get("/api/bayesian/scenario-comparison/{entity_type}/{entity_id}")
async def get_scenario_comparison(entity_type: str, entity_id: str):
    """Get scenario comparison (current vs optimized) for an entity."""
    import random
    from datetime import datetime
    
    current_incr = random.uniform(500000, 2000000)
    optimized_incr = current_incr * random.uniform(1.05, 1.25)
    
    current_eff = random.uniform(0.9, 1.3)
    optimized_eff = current_eff * random.uniform(1.02, 1.15)
    
    return {
        "entity_type": entity_type,
        "entity_id": entity_id,
        "current_scenario": {
            "scenario_name": "current",
            "incremental_sales_posterior": {
                "mean": current_incr,
                "std": current_incr * 0.12,
                "ci": [current_incr * 0.78, current_incr * 1.22],
            },
            "efficiency_posterior": {
                "mean": current_eff,
                "std": current_eff * 0.08,
            },
            "downside_risk_5pct": current_incr * 0.7,
            "downside_risk_10pct": current_incr * 0.78,
        },
        "optimized_scenario": {
            "scenario_name": "optimized",
            "incremental_sales_posterior": {
                "mean": optimized_incr,
                "std": optimized_incr * 0.1,
                "ci": [optimized_incr * 0.82, optimized_incr * 1.18],
            },
            "efficiency_posterior": {
                "mean": optimized_eff,
                "std": optimized_eff * 0.07,
            },
            "downside_risk_5pct": optimized_incr * 0.75,
            "downside_risk_10pct": optimized_incr * 0.82,
        },
        "comparison": {
            "expected_incremental_sales_delta": optimized_incr - current_incr,
            "expected_delta_ci": [(optimized_incr - current_incr) * 0.5, (optimized_incr - current_incr) * 1.5],
            "expected_efficiency_delta": optimized_eff - current_eff,
            "prob_optimized_beats_current": random.uniform(0.75, 0.98),
            "prob_optimized_beats_current_by_5pct": random.uniform(0.6, 0.9),
            "prob_optimized_beats_current_by_10pct": random.uniform(0.4, 0.75),
        },
        "recommended_allocation": {
            "search": random.uniform(0.3, 0.45),
            "display": random.uniform(0.2, 0.3),
            "video": random.uniform(0.15, 0.25),
            "email": random.uniform(0.08, 0.15),
        },
        "computed_at": datetime.now().isoformat(),
        "model_version": "v1.0.0",
    }


@app.get("/api/bayesian/driver-attributions/{entity_type}/{entity_id}")
async def get_driver_attributions(entity_type: str, entity_id: str):
    """Get driver attribution posteriors for an entity."""
    import random
    from datetime import datetime
    
    drivers = [
        "RMN SEARCH", "RMN DISPLAY", "RMN VIDEO", "RMN EMAIL",
        "TV", "DIGITAL", "FEATURE", "DISPLAY", "TPD",
        "COMPETITOR SWITCHING", "NEW BUYER", "BRAND LOYALTY",
    ]
    
    attributions = []
    for driver in drivers:
        contribution = random.uniform(10000, 300000)
        is_incremental = "CANNIBAL" not in driver
        
        attributions.append({
            "driver_name": driver,
            "contribution_posterior": {
                "mean": contribution,
                "std": contribution * 0.2,
                "ci": [contribution * 0.65, contribution * 1.35],
            },
            "contribution_pct_posterior": {
                "mean": random.uniform(0.01, 0.12),
                "std": random.uniform(0.002, 0.02),
            },
            "incremental_probability": random.uniform(0.7, 0.98) if is_incremental else random.uniform(0.1, 0.4),
            "cannibalization_probability": random.uniform(0.02, 0.3) if is_incremental else random.uniform(0.6, 0.9),
            "prob_top_contributor": random.uniform(0.01, 0.15),
            "prob_top_10_contributor": random.uniform(0.2, 0.8),
        })
    
    # Sort by contribution mean
    attributions.sort(key=lambda x: x["contribution_posterior"]["mean"], reverse=True)
    
    return {
        "entity_type": entity_type,
        "entity_id": entity_id,
        "attributions": attributions,
        "total_contribution": sum(a["contribution_posterior"]["mean"] for a in attributions),
        "computed_at": datetime.now().isoformat(),
    }


@app.post("/api/tee/release")
async def submit_tee_release(request: dict):
    """Submit a DP release request."""
    import random
    
    job_id = request.get("job_id", "")
    dataset_id = request.get("dataset_id", "")
    aggregate_type = request.get("aggregate_type", "count")
    raw_value = request.get("raw_value", 0)
    epsilon = request.get("epsilon", 1.0)
    mechanism = request.get("mechanism", "laplace")
    
    if not job_id or not dataset_id:
        return {"success": False, "message": "Missing job_id or dataset_id"}
    
    # Simulate DP noise addition
    if mechanism == "laplace":
        noise = random.uniform(-raw_value * 0.1, raw_value * 0.1)
    elif mechanism == "gaussian":
        noise = random.gauss(0, raw_value * 0.05)
    else:
        noise = random.uniform(-raw_value * 0.15, raw_value * 0.15)
    
    released_value = raw_value + noise
    
    return {
        "success": True,
        "message": f"Successfully released DP-protected value using {mechanism} mechanism with ε={epsilon}",
        "value": round(released_value, 2),
        "receipt_id": f"rcpt-{random.randint(10000, 99999)}",
        "epsilon_consumed": epsilon,
    }


# =============================================================================
# CREW-BASED OPTIMIZATION API ENDPOINTS
# =============================================================================

@app.get("/api/crews/list")
async def list_crews():
    """List all available optimization crews."""
    return {
        "level_crews": [
            {
                "crew_id": "brand_optimization",
                "name": "Brand Level Optimization Crew",
                "description": "Optimizes brand portfolio's retail media spend mix across RMNs and channels",
                "agents": ["brand_portfolio_lead", "brand_performance_analyst", "incrementality_analyst", 
                          "margin_mix_analyst", "budget_allocation_optimizer", "constraints_risk_manager",
                          "recommendation_narrator", "qa_auditor"],
            },
            {
                "crew_id": "rmn_optimization",
                "name": "RMN Level Optimization Crew",
                "description": "Optimizes performance within and across RMNs with retailer-specific action plans",
                "agents": ["rmn_account_lead", "rmn_performance_analyst", "auction_dynamics_specialist",
                          "incrementality_analyst", "budget_allocation_optimizer", "constraints_risk_manager",
                          "recommendation_narrator", "qa_auditor"],
            },
            {
                "crew_id": "campaign_optimization",
                "name": "Campaign & Message Level Optimization Crew",
                "description": "Optimizes campaign structure, targeting, and message/creative strategy",
                "agents": ["campaign_ops_lead", "campaign_performance_analyst", "audience_keyword_analyst",
                          "creative_message_analyst", "experimentation_designer", "bidding_pacing_specialist",
                          "constraints_risk_manager", "recommendation_narrator", "qa_auditor"],
            },
            {
                "crew_id": "channel_optimization",
                "name": "Channel Level Optimization Crew",
                "description": "Optimizes within-channel levers and cross-channel mix with channel playbooks",
                "agents": ["channel_strategy_lead", "search_specialist", "display_specialist",
                          "video_specialist", "email_specialist", "incrementality_analyst",
                          "budget_allocation_optimizer", "constraints_risk_manager", "recommendation_narrator", "qa_auditor"],
            },
        ],
        "scenario_crews": [
            {
                "crew_id": "increase_revenue",
                "name": "Increase Revenue Crew",
                "description": "Maximize incremental dollar sales",
                "objective": "maximize incremental_sales",
                "kpis": ["Incremental sales", "iROAS", "scale headroom", "saturation signals"],
            },
            {
                "crew_id": "increase_margin",
                "name": "Increase Margin Crew",
                "description": "Maximize incremental gross profit",
                "objective": "maximize incremental_sales × gross_margin_rate",
                "kpis": ["Incremental profit", "profit per $ spend", "contribution margin"],
            },
            {
                "crew_id": "maintain_revenue",
                "name": "Maintain Revenue Crew",
                "description": "Minimize spend while maintaining revenue floor",
                "objective": "minimize spend subject to revenue floor",
                "kpis": ["Spend savings", "efficiency", "risk/fragility", "forecast error"],
            },
            {
                "crew_id": "reduce_cost",
                "name": "Reduce Cost Crew",
                "description": "Minimize spend while protecting priority KPIs",
                "objective": "minimize spend with revenue floor",
                "kpis": ["Cost savings", "efficiency", "coverage proxies", "downside risk"],
            },
        ],
    }


@app.get("/api/crews/instances")
async def get_crew_instances():
    """Get all active crew instances organized by entity."""
    import random
    from datetime import datetime, timedelta
    
    brands = ["Brand A", "Brand B", "Brand C", "Brand D", "Brand E", "Brand F"]
    rmns = ["Walmart", "Amazon", "Target", "Instacart"]
    channels = ["Search", "Display", "Video", "Email"]
    
    instances = {
        "brand_crews": [],
        "rmn_crews": [],
        "channel_crews": [],
        "scenario_crews": [],
    }
    
    # Brand crews
    for brand in brands:
        instances["brand_crews"].append({
            "instance_id": f"brand-crew-{brand.lower().replace(' ', '-')}",
            "crew_type": "brand_optimization",
            "entity_id": brand.lower().replace(' ', '-'),
            "entity_name": brand,
            "status": random.choice(["active", "active", "idle", "running"]),
            "last_run": (datetime.now() - timedelta(hours=random.randint(1, 48))).isoformat(),
            "efficiency": random.uniform(1.1, 2.3),
            "total_spend": random.uniform(500000, 3000000),
        })
    
    # RMN crews - each RMN gets its own instance
    for rmn in rmns:
        instances["rmn_crews"].append({
            "instance_id": f"rmn-crew-{rmn.lower()}",
            "crew_type": "rmn_optimization",
            "entity_id": rmn.lower(),
            "entity_name": rmn,
            "status": random.choice(["active", "active", "idle"]),
            "last_run": (datetime.now() - timedelta(hours=random.randint(1, 24))).isoformat(),
            "efficiency": random.uniform(1.0, 2.5),
            "total_spend": random.uniform(1000000, 5000000),
            "channels": channels,
        })
    
    # Channel crews per RMN
    for rmn in rmns:
        for channel in channels:
            instances["channel_crews"].append({
                "instance_id": f"channel-crew-{rmn.lower()}-{channel.lower()}",
                "crew_type": "channel_optimization",
                "rmn_id": rmn.lower(),
                "rmn_name": rmn,
                "channel_id": channel.lower(),
                "channel_name": channel,
                "status": random.choice(["active", "idle"]),
                "efficiency": random.uniform(0.8, 2.8),
                "spend": random.uniform(100000, 800000),
            })
    
    # Active scenario crews
    scenarios = ["increase_revenue", "increase_margin", "maintain_revenue", "reduce_cost"]
    for i, scenario in enumerate(scenarios):
        instances["scenario_crews"].append({
            "instance_id": f"scenario-{scenario}-{i+1}",
            "crew_type": scenario,
            "status": random.choice(["completed", "running", "queued"]),
            "created_at": (datetime.now() - timedelta(hours=random.randint(1, 72))).isoformat(),
            "budget": random.uniform(5000000, 20000000),
            "projected_impact": random.uniform(0.05, 0.20),
        })
    
    return instances


@app.post("/api/crews/run")
async def run_crew(request: dict):
    """Run an optimization crew with specified parameters."""
    import random
    from datetime import datetime
    
    crew_type = request.get("crew_type", "brand_optimization")
    entity_id = request.get("entity_id", "")
    desired_outcome = request.get("desired_outcome", "increase_revenue")
    budget = request.get("budget", 1000000)
    constraints = request.get("constraints", {})
    
    # Simulate crew execution
    execution_time = random.uniform(2.5, 8.0)
    
    # Generate mock optimization result
    if crew_type == "brand_optimization":
        allocations = []
        rmns = ["walmart", "amazon", "target", "instacart"]
        total_spend = 0
        for rmn in rmns:
            current = random.uniform(200000, 600000)
            recommended = current * random.uniform(0.8, 1.3)
            total_spend += recommended
            allocations.append({
                "entity_type": "rmn",
                "entity_id": rmn,
                "entity_name": rmn.title(),
                "current_spend": current,
                "recommended_spend": recommended,
                "spend_delta": recommended - current,
                "spend_delta_pct": (recommended - current) / current,
                "expected_incremental_sales": recommended * random.uniform(1.2, 2.0),
                "expected_efficiency": random.uniform(1.1, 2.2),
                "rationale": f"{'Increase' if recommended > current else 'Decrease'} based on efficiency analysis",
                "actions": [
                    f"{'Increase' if recommended > current else 'Reduce'} budget",
                    "Monitor performance weekly",
                    "Optimize channel mix within RMN",
                ],
            })
    elif crew_type in ["rmn_optimization", "channel_optimization"]:
        allocations = []
        channels = ["search", "display", "video", "email"]
        total_spend = 0
        for channel in channels:
            current = random.uniform(50000, 200000)
            recommended = current * random.uniform(0.7, 1.4)
            total_spend += recommended
            allocations.append({
                "entity_type": "channel",
                "entity_id": channel,
                "entity_name": channel.title(),
                "current_spend": current,
                "recommended_spend": recommended,
                "spend_delta": recommended - current,
                "spend_delta_pct": (recommended - current) / current,
                "expected_incremental_sales": recommended * random.uniform(1.0, 2.5),
                "expected_efficiency": random.uniform(0.9, 2.5),
                "rationale": f"Channel optimization based on response curves",
                "actions": [
                    f"{'Scale' if recommended > current else 'Reduce'} {channel}",
                    "Adjust bid strategies",
                    "Test new audiences/keywords",
                ],
            })
    else:
        allocations = []
        total_spend = budget
    
    # Normalize to budget
    if total_spend > 0:
        scale = budget / total_spend
        for alloc in allocations:
            alloc["recommended_spend"] *= scale
            alloc["spend_delta"] = alloc["recommended_spend"] - alloc["current_spend"]
            alloc["spend_delta_pct"] = alloc["spend_delta"] / alloc["current_spend"] if alloc["current_spend"] > 0 else 0
    
    expected_sales = sum(a["expected_incremental_sales"] for a in allocations)
    
    return {
        "success": True,
        "crew_id": f"{crew_type}-{datetime.now().strftime('%Y%m%d%H%M%S')}",
        "crew_type": crew_type,
        "desired_outcome": desired_outcome,
        "execution_time_seconds": execution_time,
        "output": {
            "executive_summary": f"{crew_type.replace('_', ' ').title()} completed. Recommended reallocation of ${budget:,.0f} "
                                f"across {len(allocations)} entities to achieve ${expected_sales:,.0f} incremental sales.",
            "key_findings": [
                f"Overall efficiency: {expected_sales/budget:.2f} iROAS",
                f"Identified {random.randint(2, 5)} scale opportunities",
                f"Found {random.randint(1, 3)} underperformers to address",
            ],
            "opportunities": [
                f"Scale high-efficiency entities for +{random.uniform(5, 15):.1f}% sales",
                "Test new channels with 10% carveout",
            ],
            "risks": [
                "Response curve uncertainty in low-data entities",
                "Competitive dynamics may shift",
            ],
            "allocations": allocations,
            "total_recommended_spend": budget,
            "expected_incremental_sales": expected_sales,
            "expected_efficiency": expected_sales / budget,
            "constraints_satisfied": True,
            "constraint_violations": [],
        },
        "created_at": datetime.now().isoformat(),
    }


@app.get("/api/crews/rmn/{rmn_id}")
async def get_rmn_crew_details(rmn_id: str):
    """Get detailed information about an RMN-specific crew instance."""
    import random
    from datetime import datetime, timedelta
    
    rmn_names = {
        "walmart": "Walmart",
        "amazon": "Amazon",
        "target": "Target",
        "instacart": "Instacart",
    }
    
    rmn_name = rmn_names.get(rmn_id, rmn_id.title())
    
    channels = ["search", "display", "video", "email"]
    channel_data = {}
    total_spend = 0
    total_sales = 0
    
    for channel in channels:
        spend = random.uniform(100000, 500000)
        sales = spend * random.uniform(1.0, 2.5)
        total_spend += spend
        total_sales += sales
        
        channel_data[channel] = {
            "spend": spend,
            "incremental_sales": sales,
            "efficiency": sales / spend,
            "elasticity": random.uniform(0.08, 0.25),
            "saturation_pct": random.uniform(0.3, 0.8),
            "headroom": random.uniform(0.2, 0.7),
        }
    
    return {
        "crew_instance": {
            "instance_id": f"rmn-crew-{rmn_id}",
            "crew_type": "rmn_optimization",
            "rmn_id": rmn_id,
            "rmn_name": rmn_name,
            "status": "active",
        },
        "agents": [
            {"agent_id": "rmn_account_lead", "role": f"{rmn_name} Account Lead", "status": "ready"},
            {"agent_id": "rmn_performance_analyst", "role": f"{rmn_name} Performance Analyst", "status": "ready"},
            {"agent_id": "auction_dynamics_specialist", "role": "Auction Dynamics Specialist", "status": "ready"},
            {"agent_id": "incrementality_analyst", "role": "Incrementality Analyst", "status": "ready"},
            {"agent_id": "budget_allocation_optimizer", "role": "Budget Allocation Optimizer", "status": "ready"},
            {"agent_id": "constraints_risk_manager", "role": "Constraints & Risk Manager", "status": "ready"},
            {"agent_id": "recommendation_narrator", "role": "Recommendation Narrator", "status": "ready"},
            {"agent_id": "qa_auditor", "role": "QA Auditor", "status": "ready"},
        ],
        "performance": {
            "total_spend": total_spend,
            "total_incremental_sales": total_sales,
            "overall_efficiency": total_sales / total_spend,
            "channel_breakdown": channel_data,
        },
        "constraints": {
            "min_spend_commitment": random.uniform(50000, 200000),
            "channel_floors": {ch: random.uniform(10000, 50000) for ch in channels},
            "channel_ceilings": {ch: random.uniform(500000, 1000000) for ch in channels},
        },
        "last_optimization": {
            "timestamp": (datetime.now() - timedelta(hours=random.randint(1, 24))).isoformat(),
            "improvement_pct": random.uniform(0.03, 0.12),
            "status": "completed",
        },
    }


@app.get("/api/crews/scenarios")
async def list_scenario_library():
    """Get the scenario library with predefined parameter patterns."""
    return {
        "scenarios": [
            {
                "scenario_id": "grow_revenue_10_percent",
                "name": "Grow Revenue 10%",
                "crew": "increase_revenue",
                "description": "Target 10% revenue growth with 15% budget increase",
                "params": {
                    "budget_delta_pct": 0.15,
                    "target_revenue_delta_pct": 0.10,
                    "revenue_floor_pct": 0.95,
                },
            },
            {
                "scenario_id": "maximize_efficiency",
                "name": "Maximize Efficiency",
                "crew": "maintain_revenue",
                "description": "Reduce spend 10% while maintaining 98% of revenue",
                "params": {
                    "budget_delta_pct": -0.10,
                    "revenue_floor_pct": 0.98,
                },
            },
            {
                "scenario_id": "scale_high_performers",
                "name": "Scale High Performers",
                "crew": "increase_revenue",
                "description": "Increase budget 20% with emphasis on search",
                "params": {
                    "budget_delta_pct": 0.20,
                    "channel_emphasis": {
                        "search": 1.5,
                        "display": 1.0,
                        "video": 0.8,
                        "email": 0.7,
                    },
                },
            },
            {
                "scenario_id": "reduce_spend_10_percent",
                "name": "Reduce Spend 10%",
                "crew": "reduce_cost",
                "description": "Cut spend 10% while protecting 90% of revenue",
                "params": {
                    "budget_delta_pct": -0.10,
                    "revenue_floor_pct": 0.90,
                    "require_test_carveout": True,
                },
            },
            {
                "scenario_id": "stress_test_budget_cut",
                "name": "Stress Test: 25% Budget Cut",
                "crew": "reduce_cost",
                "description": "Stress test with 25% budget cut",
                "params": {
                    "budget_delta_pct": -0.25,
                    "revenue_floor_pct": 0.80,
                    "scenario_type": "stress_test",
                },
            },
            {
                "scenario_id": "shift_to_high_margin",
                "name": "Shift to High Margin",
                "crew": "increase_margin",
                "description": "Optimize for margin with 50% margin weight",
                "params": {
                    "margin_weight": 0.5,
                    "volume_weight": 0.3,
                    "brand_priority_weight": 0.2,
                },
            },
        ],
    }


@app.post("/api/crews/scenario/run")
async def run_scenario(request: dict):
    """Run a scenario from the library or with custom parameters."""
    import random
    from datetime import datetime
    
    scenario_id = request.get("scenario_id", "")
    custom_params = request.get("params", {})
    budget = request.get("budget", 10000000)
    
    # Determine scenario type
    if "revenue" in scenario_id or "grow" in scenario_id.lower():
        crew_type = "increase_revenue"
        direction = "maximize"
    elif "margin" in scenario_id:
        crew_type = "increase_margin"
        direction = "maximize"
    elif "maintain" in scenario_id or "efficiency" in scenario_id.lower():
        crew_type = "maintain_revenue"
        direction = "minimize"
    else:
        crew_type = "reduce_cost"
        direction = "minimize"
    
    # Calculate baseline and optimized
    baseline_sales = budget * random.uniform(1.2, 1.8)
    baseline_efficiency = baseline_sales / budget
    
    if direction == "maximize":
        optimized_budget = budget * (1 + custom_params.get("budget_delta_pct", 0.1))
        optimized_sales = baseline_sales * random.uniform(1.08, 1.18)
    else:
        optimized_budget = budget * (1 + custom_params.get("budget_delta_pct", -0.1))
        optimized_sales = baseline_sales * random.uniform(0.92, 1.02)
    
    optimized_efficiency = optimized_sales / optimized_budget
    
    return {
        "success": True,
        "scenario_id": scenario_id or f"custom-{datetime.now().strftime('%Y%m%d%H%M%S')}",
        "crew_type": crew_type,
        "baseline": {
            "total_spend": budget,
            "incremental_sales": baseline_sales,
            "efficiency": baseline_efficiency,
        },
        "optimized": {
            "total_spend": optimized_budget,
            "incremental_sales": optimized_sales,
            "efficiency": optimized_efficiency,
        },
        "comparison": {
            "spend_delta": optimized_budget - budget,
            "spend_delta_pct": (optimized_budget - budget) / budget,
            "sales_delta": optimized_sales - baseline_sales,
            "sales_delta_pct": (optimized_sales - baseline_sales) / baseline_sales,
            "efficiency_delta": optimized_efficiency - baseline_efficiency,
            "prob_success": random.uniform(0.75, 0.95),
        },
        "recommended_allocation": {
            "walmart": random.uniform(0.25, 0.35),
            "amazon": random.uniform(0.20, 0.30),
            "target": random.uniform(0.15, 0.25),
            "instacart": random.uniform(0.10, 0.20),
        },
        "execution_time_seconds": random.uniform(3.0, 10.0),
        "created_at": datetime.now().isoformat(),
    }


# =============================================================================
# DECISION SUPPORT SCENARIO API ENDPOINTS
# =============================================================================

@app.get("/api/scenarios/list")
async def list_scenarios():
    """List all available business decision support scenarios."""
    scenarios = [
        # Core Outcome Scenarios (1-5)
        {
            "scenario_id": "grow_revenue_brand",
            "name": "Grow Revenue for Brand",
            "description": "Maximize incremental dollar sales for a specific brand",
            "category": "core_outcome",
            "objective_type": "incremental_sales",
            "objective_description": "Maximize incremental $ sales for Brand X",
            "default_risk_appetite": "balanced",
            "default_cadence": "weekly",
            "icon": "trending_up",
            "color": "#4CAF50",
            "tags": ["growth", "brand", "revenue"],
            "required_crews": ["brand_optimization", "rmn_optimization", "channel_optimization"],
        },
        {
            "scenario_id": "maintain_revenue",
            "name": "Maintain Revenue (Stability)",
            "description": "Keep incremental sales within target band at lowest risk",
            "category": "core_outcome",
            "objective_type": "stability",
            "objective_description": "Keep incremental sales within ±X% band at lowest risk",
            "default_risk_appetite": "conservative",
            "default_cadence": "weekly",
            "icon": "balance",
            "color": "#2196F3",
            "tags": ["stability", "maintenance", "risk-averse"],
            "required_crews": ["brand_optimization", "rmn_optimization"],
        },
        {
            "scenario_id": "prevent_decline",
            "name": "Prevent Revenue Decline",
            "description": "Minimize probability of negative lift - defensive triage mode",
            "category": "core_outcome",
            "objective_type": "decline_risk_min",
            "objective_description": "Minimize probability of negative lift (maximize P(Δsales ≥ 0))",
            "default_risk_appetite": "conservative",
            "default_cadence": "weekly",
            "icon": "shield",
            "color": "#FF9800",
            "tags": ["defensive", "triage", "risk-mitigation"],
            "required_crews": ["brand_optimization", "rmn_optimization", "channel_optimization"],
        },
        {
            "scenario_id": "grow_margin",
            "name": "Grow Margin (Profit Mode)",
            "description": "Maximize incremental profit = incremental sales × margin rate − media cost",
            "category": "core_outcome",
            "objective_type": "incremental_profit",
            "objective_description": "Maximize incremental profit = incremental sales × margin rate − media cost",
            "default_risk_appetite": "balanced",
            "default_cadence": "weekly",
            "icon": "attach_money",
            "color": "#9C27B0",
            "tags": ["profit", "margin", "efficiency"],
            "required_crews": ["brand_optimization", "rmn_optimization", "campaign_optimization"],
        },
        {
            "scenario_id": "reduce_cost",
            "name": "Reduce Cost (Efficiency Mode)",
            "description": "Achieve target incremental sales with minimum spend",
            "category": "core_outcome",
            "objective_type": "efficiency",
            "objective_description": "Achieve target incremental sales with minimum spend",
            "default_risk_appetite": "balanced",
            "default_cadence": "weekly",
            "icon": "savings",
            "color": "#607D8B",
            "tags": ["cost", "efficiency", "budget"],
            "required_crews": ["brand_optimization", "rmn_optimization", "channel_optimization"],
        },
        # Incrementality-Specific Scenarios (6-12)
        {
            "scenario_id": "true_incrementality",
            "name": "True Incrementality Only",
            "description": "No cannibalization tolerance - maximize truly incremental sales",
            "category": "incrementality",
            "objective_type": "incremental_sales",
            "objective_description": "Maximize incremental sales subject to P(cannibalization > 0) < α",
            "default_risk_appetite": "balanced",
            "default_cadence": "weekly",
            "icon": "verified",
            "color": "#00BCD4",
            "tags": ["incrementality", "cannibalization", "true-lift"],
            "required_crews": ["brand_optimization", "campaign_optimization"],
        },
        {
            "scenario_id": "new_to_brand",
            "name": "New-to-Brand Growth",
            "description": "Maximize incremental new customer sales",
            "category": "incrementality",
            "objective_type": "new_to_brand",
            "objective_description": "Maximize incremental new customer sales",
            "default_risk_appetite": "balanced",
            "default_cadence": "weekly",
            "icon": "person_add",
            "color": "#E91E63",
            "tags": ["acquisition", "new-customers", "growth"],
            "required_crews": ["brand_optimization", "campaign_optimization", "channel_optimization"],
        },
        {
            "scenario_id": "defend_share",
            "name": "Defend Share vs Competitor",
            "description": "Maximize incremental sales in competitive set while reducing share loss probability",
            "category": "incrementality",
            "objective_type": "share_defense",
            "objective_description": "Maximize incremental sales while reducing probability of share loss",
            "default_risk_appetite": "balanced",
            "default_cadence": "weekly",
            "icon": "security",
            "color": "#F44336",
            "tags": ["competitive", "defense", "share"],
            "required_crews": ["brand_optimization", "rmn_optimization", "channel_optimization"],
        },
        {
            "scenario_id": "seasonal_ramp",
            "name": "Seasonal Ramp (Pre-Holiday)",
            "description": "Maximize incremental sales for defined period with diminishing return control",
            "category": "incrementality",
            "objective_type": "incremental_sales",
            "objective_description": "Maximize incremental sales for defined period with diminishing return control",
            "default_risk_appetite": "aggressive",
            "default_cadence": "daily",
            "icon": "event",
            "color": "#FF5722",
            "tags": ["seasonal", "holiday", "ramp"],
            "required_crews": ["brand_optimization", "rmn_optimization", "channel_optimization", "campaign_optimization"],
        },
        # Risk & Governance Scenarios (13-15)
        {
            "scenario_id": "risk_minimized",
            "name": "Risk-Minimized Optimization",
            "description": "Maximize expected incremental sales minus risk penalty",
            "category": "risk_governance",
            "objective_type": "stability",
            "objective_description": "Maximize expected incremental sales minus risk penalty (variance/downside)",
            "default_risk_appetite": "conservative",
            "default_cadence": "weekly",
            "icon": "verified_user",
            "color": "#673AB7",
            "tags": ["risk", "certainty", "conservative"],
            "required_crews": ["brand_optimization", "rmn_optimization"],
        },
        {
            "scenario_id": "explore_exploit",
            "name": "Learning vs Earning",
            "description": "Allocate exploration budget to reduce uncertainty while exploiting known winners",
            "category": "risk_governance",
            "objective_type": "learning",
            "objective_description": "Allocate X% to exploration to reduce uncertainty; rest to exploitation",
            "default_risk_appetite": "balanced",
            "default_cadence": "weekly",
            "icon": "science",
            "color": "#009688",
            "tags": ["learning", "exploration", "experimentation"],
            "required_crews": ["brand_optimization", "campaign_optimization", "channel_optimization"],
        },
        {
            "scenario_id": "audit_ready",
            "name": "Audit-Ready Allocations",
            "description": "Produce defensible, explainable decisions with full evidence trail",
            "category": "risk_governance",
            "objective_type": "incremental_sales",
            "objective_description": "Produce decisions that are defensible with 'why' narratives and evidence",
            "default_risk_appetite": "conservative",
            "default_cadence": "weekly",
            "icon": "fact_check",
            "color": "#8BC34A",
            "tags": ["audit", "explainability", "governance"],
            "required_crews": ["brand_optimization", "rmn_optimization"],
        },
        # Portfolio Management Scenarios (16-18)
        {
            "scenario_id": "company_wide_optimization",
            "name": "Company-Wide Budget Optimization",
            "description": "Maximize total incremental profit under fixed total budget across brands/RMNs",
            "category": "portfolio",
            "objective_type": "incremental_profit",
            "objective_description": "Maximize total incremental profit under a fixed total budget across brands/RMNs",
            "default_risk_appetite": "balanced",
            "default_cadence": "weekly",
            "icon": "account_balance",
            "color": "#FF9800",
            "tags": ["portfolio", "company-wide", "budget"],
            "required_crews": ["brand_optimization", "rmn_optimization", "channel_optimization"],
        },
        {
            "scenario_id": "brand_prioritization",
            "name": "Brand Prioritization Shift",
            "description": "Temporarily favor one brand's growth while protecting another's baseline",
            "category": "portfolio",
            "objective_type": "incremental_sales",
            "objective_description": "Temporarily favor Brand A growth while protecting Brand B baseline",
            "default_risk_appetite": "balanced",
            "default_cadence": "weekly",
            "icon": "swap_horiz",
            "color": "#3F51B5",
            "tags": ["portfolio", "prioritization", "brand"],
            "required_crews": ["brand_optimization", "rmn_optimization"],
        },
        {
            "scenario_id": "shock_response",
            "name": "Reallocation Shock Response",
            "description": "Stabilize outcomes after RMN performance break while re-learning",
            "category": "portfolio",
            "objective_type": "stability",
            "objective_description": "Stabilize outcomes while re-learning after performance shock",
            "default_risk_appetite": "conservative",
            "default_cadence": "daily",
            "icon": "warning",
            "color": "#F44336",
            "tags": ["shock", "recovery", "stabilization"],
            "required_crews": ["brand_optimization", "rmn_optimization", "channel_optimization"],
        },
        # Operational Scenarios (19-21)
        {
            "scenario_id": "pacing_recovery",
            "name": "Pacing & Underdelivery Recovery",
            "description": "Hit monthly spend and outcome targets",
            "category": "operational",
            "objective_type": "incremental_sales",
            "objective_description": "Hit monthly spend and outcome targets",
            "default_risk_appetite": "balanced",
            "default_cadence": "daily",
            "icon": "speed",
            "color": "#00BCD4",
            "tags": ["pacing", "delivery", "operational"],
            "required_crews": ["rmn_optimization", "channel_optimization", "campaign_optimization"],
        },
        {
            "scenario_id": "constraint_breach",
            "name": "Constraint Breach Handling",
            "description": "Automatic safe-mode allocation when constraints are at risk",
            "category": "operational",
            "objective_type": "stability",
            "objective_description": "Handle revenue/margin/spend constraint breach risks",
            "default_risk_appetite": "conservative",
            "default_cadence": "continuous",
            "icon": "report_problem",
            "color": "#FF5722",
            "tags": ["constraint", "breach", "safety"],
            "required_crews": ["brand_optimization", "rmn_optimization"],
        },
        {
            "scenario_id": "data_quality_mode",
            "name": "Data Quality / Uncertainty Mode",
            "description": "Continue optimizing conservatively with measurement uncertainty",
            "category": "operational",
            "objective_type": "stability",
            "objective_description": "Continue optimizing conservatively when data quality is uncertain",
            "default_risk_appetite": "conservative",
            "default_cadence": "weekly",
            "icon": "data_usage",
            "color": "#9E9E9E",
            "tags": ["data-quality", "uncertainty", "conservative"],
            "required_crews": ["brand_optimization", "rmn_optimization"],
        },
    ]
    return {"scenarios": scenarios}


@app.post("/api/scenarios/execute")
async def execute_scenario(request: dict):
    """Execute a business scenario and return decision recommendations."""
    import random
    import uuid
    from datetime import datetime
    
    scenario_id = request.get("scenario_id", "grow_revenue_brand")
    risk_appetite = request.get("risk_appetite", "balanced")
    max_reallocation_pct = request.get("max_reallocation_pct", 0.15)
    exploration_budget_pct = request.get("exploration_budget_pct", 0.10)
    
    # Get scenario details
    scenarios_response = await list_scenarios()
    scenario = next((s for s in scenarios_response["scenarios"] if s["scenario_id"] == scenario_id), None)
    
    if not scenario:
        raise HTTPException(status_code=404, detail=f"Scenario {scenario_id} not found")
    
    # Simulate crew execution
    crews_executed = scenario.get("required_crews", ["brand_optimization"])
    
    # Generate recommended actions
    entities = [
        ("brand", "brand-a", "Brand A"),
        ("rmn", "walmart", "Walmart"),
        ("rmn", "amazon", "Amazon"),
        ("channel", "search", "Sponsored Search"),
    ]
    
    recommended_actions = []
    total_impact = 0
    for i, (entity_type, entity_id, entity_name) in enumerate(entities):
        current = random.uniform(500000, 2000000)
        delta_pct = random.uniform(-0.15, 0.25) * (1 if "grow" in scenario_id or "revenue" in scenario_id else -1)
        delta = current * delta_pct
        recommended = current + delta
        impact = abs(delta) * random.uniform(0.1, 0.2)
        total_impact += impact
        
        recommended_actions.append({
            "action_id": str(uuid.uuid4()),
            "action_type": "reallocate",
            "entity_type": entity_type,
            "entity_id": entity_id,
            "entity_name": entity_name,
            "description": f"{'Increase' if delta > 0 else 'Decrease'} spend by ${abs(delta):,.0f}",
            "current_value": current,
            "recommended_value": recommended,
            "delta": delta,
            "delta_pct": delta_pct * 100,
            "expected_impact": impact,
            "confidence": random.uniform(0.75, 0.95),
            "priority": i + 1,
            "rationale": f"Based on {entity_type} level analysis showing {'high' if delta > 0 else 'low'} incremental potential",
        })
    
    # Generate supporting evidence
    supporting_evidence = [
        {
            "evidence_id": str(uuid.uuid4()),
            "evidence_type": "posterior_distribution",
            "title": "Incremental Lift Distribution",
            "description": "Posterior distribution of expected incremental lift from Bayesian model",
            "metric_name": "incremental_lift",
            "metric_value": 0.15,
            "confidence_interval": [0.10, 0.22],
            "probability": 0.85,
        },
        {
            "evidence_id": str(uuid.uuid4()),
            "evidence_type": "credible_interval",
            "title": "90% Credible Interval for ROAS",
            "description": "90% credible interval for expected ROAS improvement",
            "metric_name": "roas",
            "metric_value": 3.5,
            "confidence_interval": [2.8, 4.2],
        },
        {
            "evidence_id": str(uuid.uuid4()),
            "evidence_type": "probability_statement",
            "title": "Probability of Positive Lift",
            "description": "Probability that the recommended allocation produces positive incremental lift",
            "metric_name": "p_positive_lift",
            "metric_value": 0.92,
            "probability": 0.92,
        },
        {
            "evidence_id": str(uuid.uuid4()),
            "evidence_type": "counterfactual",
            "title": "Counterfactual Comparison",
            "description": "Expected outcome if no changes made vs recommended allocation",
            "metric_name": "counterfactual_delta",
            "metric_value": 25000,
            "confidence_interval": [15000, 35000],
        },
    ]
    
    # Generate reasoning chain
    reasoning_steps = []
    for i, crew_id in enumerate(crews_executed):
        reasoning_steps.append({
            "step_id": str(uuid.uuid4()),
            "step_number": i + 1,
            "crew_id": crew_id,
            "agent_id": f"{crew_id}_analyst",
            "action": f"Analyzed {crew_id.replace('_optimization', '')} level data",
            "input_summary": f"Received current state and constraints for {scenario['name']}",
            "output_summary": f"Found {random.randint(2, 5)} opportunities, {random.randint(1, 2)} risks",
            "reasoning": f"Applied {scenario['objective_type']} objective to identify optimization opportunities at {crew_id.replace('_', ' ')} level",
            "confidence": random.uniform(0.80, 0.95),
        })
    
    overall_confidence = sum(a["confidence"] for a in recommended_actions) / len(recommended_actions)
    
    # Risk assessment
    if overall_confidence > 0.85:
        risk_level = "LOW"
    elif overall_confidence > 0.70:
        risk_level = "MODERATE"
    else:
        risk_level = "HIGH"
    
    decision_recommendation = {
        "recommendation_id": str(uuid.uuid4()),
        "scenario_id": scenario_id,
        "scenario_name": scenario["name"],
        "executive_summary": f"For '{scenario['name']}' scenario: Identified {len(recommended_actions)} recommended actions "
                            f"with expected incremental impact of ${total_impact:,.0f}. "
                            f"Overall confidence: {overall_confidence:.0%}. "
                            f"Primary objective: {scenario['objective_description']}",
        "recommended_actions": recommended_actions,
        "supporting_evidence": supporting_evidence,
        "reasoning_chain": {
            "chain_id": str(uuid.uuid4()),
            "steps": reasoning_steps,
            "crews_involved": crews_executed,
            "cross_crew_messages": [],
        },
        "total_expected_impact": total_impact,
        "overall_confidence": overall_confidence,
        "risk_assessment": f"{risk_level} RISK: Recommendations have {overall_confidence:.0%} average confidence "
                          f"with {risk_appetite} risk appetite setting. "
                          f"Max reallocation: {max_reallocation_pct:.0%} per cycle.",
        "constraints_satisfied": True,
        "constraint_violations": [],
    }
    
    return {
        "success": True,
        "session_id": str(uuid.uuid4()),
        "scenario_id": scenario_id,
        "decision_recommendation": decision_recommendation,
        "execution_time_ms": random.randint(1500, 5000),
        "crews_executed": crews_executed,
        "created_at": datetime.now().isoformat(),
    }


@app.get("/api/scenarios/{scenario_id}")
async def get_scenario_details(scenario_id: str):
    """Get detailed information about a specific scenario."""
    scenarios_response = await list_scenarios()
    scenario = next((s for s in scenarios_response["scenarios"] if s["scenario_id"] == scenario_id), None)
    
    if not scenario:
        raise HTTPException(status_code=404, detail=f"Scenario {scenario_id} not found")
    
    return scenario


@app.post("/api/scenarios/recommend")
async def get_scenario_recommendations(request: dict):
    """
    Get agent-generated scenario recommendations based on current state.
    This endpoint allows agents to analyze the current state and recommend
    the most appropriate scenarios.
    """
    import random
    import uuid
    
    current_state = request.get("current_state", {})
    brand_id = request.get("brand_id")
    
    # Simulate agent analysis of current state
    revenue_trend = current_state.get("revenue_trend", random.uniform(-0.1, 0.15))
    efficiency_trend = current_state.get("efficiency_trend", random.uniform(-0.05, 0.1))
    competitive_pressure = current_state.get("competitive_pressure", random.uniform(0.3, 0.8))
    uncertainty_level = current_state.get("uncertainty_level", random.uniform(0.3, 0.7))
    
    recommendations = []
    
    # Agent logic for scenario recommendations
    if revenue_trend > 0.05:
        recommendations.append({
            "scenario_id": "grow_revenue_brand",
            "scenario_name": "Grow Revenue for Brand",
            "confidence": 0.85,
            "rationale": f"Positive revenue trend ({revenue_trend:.1%}) indicates opportunity to scale",
            "expected_impact": random.uniform(50000, 200000),
            "risk_level": "LOW",
            "triggers_detected": ["positive_revenue_trend"],
            "priority": 1,
        })
    
    if revenue_trend < -0.03:
        recommendations.append({
            "scenario_id": "prevent_decline",
            "scenario_name": "Prevent Revenue Decline",
            "confidence": 0.90,
            "rationale": f"Revenue declining ({revenue_trend:.1%}) - defensive action recommended",
            "expected_impact": abs(revenue_trend) * 500000,
            "risk_level": "HIGH",
            "triggers_detected": ["negative_revenue_trend", "decline_risk"],
            "priority": 1,
        })
    
    if efficiency_trend < -0.02:
        recommendations.append({
            "scenario_id": "reduce_cost",
            "scenario_name": "Reduce Cost (Efficiency Mode)",
            "confidence": 0.80,
            "rationale": f"Efficiency declining ({efficiency_trend:.1%}) - cost optimization needed",
            "expected_impact": random.uniform(30000, 100000),
            "risk_level": "MODERATE",
            "triggers_detected": ["efficiency_decline"],
            "priority": 2,
        })
    
    if competitive_pressure > 0.6:
        recommendations.append({
            "scenario_id": "defend_share",
            "scenario_name": "Defend Share vs Competitor",
            "confidence": 0.88,
            "rationale": f"High competitive pressure ({competitive_pressure:.0%}) detected",
            "expected_impact": random.uniform(40000, 150000),
            "risk_level": "HIGH",
            "triggers_detected": ["competitive_pressure"],
            "priority": 2,
        })
    
    if uncertainty_level > 0.6:
        recommendations.append({
            "scenario_id": "explore_exploit",
            "scenario_name": "Learning vs Earning",
            "confidence": 0.75,
            "rationale": f"High uncertainty ({uncertainty_level:.0%}) - exploration recommended",
            "expected_impact": random.uniform(20000, 80000),
            "risk_level": "MODERATE",
            "triggers_detected": ["high_uncertainty"],
            "priority": 3,
        })
    
    # Default recommendation if none triggered
    if not recommendations:
        recommendations.append({
            "scenario_id": "maintain_revenue",
            "scenario_name": "Maintain Revenue (Stability)",
            "confidence": 0.75,
            "rationale": "Stable conditions - maintenance mode recommended",
            "expected_impact": 0,
            "risk_level": "LOW",
            "triggers_detected": ["stable_state"],
            "priority": 1,
        })
    
    # Sort by priority
    recommendations.sort(key=lambda x: x["priority"])
    
    return {
        "recommendations": recommendations,
        "analysis_summary": {
            "revenue_trend": revenue_trend,
            "efficiency_trend": efficiency_trend,
            "competitive_pressure": competitive_pressure,
            "uncertainty_level": uncertainty_level,
        },
        "generated_by": "scenario_orchestrator_agent",
        "timestamp": datetime.now().isoformat(),
    }


@app.post("/api/scenarios/execute-with-crews")
async def execute_scenario_with_crews(request: dict):
    """
    Execute a scenario using the full crew orchestration system.
    This endpoint coordinates multiple crews (Brand, RMN, Channel, Campaign)
    to collaboratively optimize the selected scenario.
    """
    import random
    import uuid
    from datetime import datetime
    
    scenario_id = request.get("scenario_id", "grow_revenue_brand")
    selection_mode = request.get("selection_mode", "user_selected")
    risk_appetite = request.get("risk_appetite", "balanced")
    max_reallocation_pct = request.get("max_reallocation_pct", 0.15)
    exploration_budget_pct = request.get("exploration_budget_pct", 0.10)
    brand_id = request.get("brand_id")
    current_state = request.get("current_state", {})
    
    # Get scenario details
    scenarios_response = await list_scenarios()
    scenario = next((s for s in scenarios_response["scenarios"] if s["scenario_id"] == scenario_id), None)
    
    if not scenario:
        raise HTTPException(status_code=404, detail=f"Scenario {scenario_id} not found")
    
    session_id = str(uuid.uuid4())
    start_time = datetime.now()
    
    # Execute each crew in sequence
    crew_outputs = {}
    crews_executed = scenario.get("required_crews", ["brand_optimization"])
    
    aggregated_context = dict(current_state)
    all_recommendations = []
    all_evidence = []
    reasoning_steps = []
    
    for i, crew_id in enumerate(crews_executed):
        crew_start = datetime.now()
        
        # Simulate crew execution with realistic outputs
        entities = _get_entities_for_crew(crew_id)
        crew_recommendations = []
        
        for j, (entity_type, entity_id, entity_name) in enumerate(entities):
            current = random.uniform(200000, 800000)
            # Direction based on scenario
            growth_factor = 1 if "grow" in scenario_id or "revenue" in scenario_id else -1
            delta_pct = random.uniform(0, max_reallocation_pct) * growth_factor
            delta = current * delta_pct
            recommended = current + delta
            impact = abs(delta) * random.uniform(0.12, 0.25)
            
            crew_recommendations.append({
                "action_id": str(uuid.uuid4()),
                "source_crew": crew_id,
                "entity_type": entity_type,
                "entity_id": entity_id,
                "entity_name": entity_name,
                "action": "increase" if delta > 0 else "decrease",
                "current_value": current,
                "recommended_value": recommended,
                "delta": delta,
                "delta_pct": delta_pct * 100,
                "expected_impact": impact,
                "confidence": random.uniform(0.78, 0.95),
                "priority": len(all_recommendations) + j + 1,
                "rationale": f"Based on {crew_id.replace('_optimization', '')} level analysis for {scenario['name']}",
            })
        
        all_recommendations.extend(crew_recommendations)
        
        # Generate crew evidence
        crew_evidence = {
            "source": crew_id,
            "type": "crew_analysis",
            "findings": [
                f"Analyzed {len(entities)} {crew_id.replace('_optimization', '')} entities",
                f"Found {random.randint(2, 4)} optimization opportunities",
            ],
            "opportunities": [f"Scale high-performers at {crew_id.replace('_optimization', '')} level"],
            "risks": ["Response curve uncertainty"],
            "confidence": sum(r["confidence"] for r in crew_recommendations) / max(1, len(crew_recommendations)),
        }
        all_evidence.append(crew_evidence)
        
        # Build reasoning step
        crew_duration = int((datetime.now() - crew_start).total_seconds() * 1000) + random.randint(500, 2000)
        reasoning_steps.append({
            "step_number": i + 1,
            "crew_id": crew_id,
            "action": f"Optimized {crew_id.replace('_optimization', '')} level for {scenario['name']}",
            "output_summary": f"Generated {len(crew_recommendations)} recommendations",
            "key_findings": crew_evidence["findings"],
            "confidence": crew_evidence["confidence"],
            "duration_ms": crew_duration,
        })
        
        # Store crew output
        crew_outputs[crew_id] = {
            "recommendations": crew_recommendations,
            "evidence": crew_evidence,
            "duration_ms": crew_duration,
        }
        
        # Update context for next crew
        aggregated_context[f"{crew_id}_completed"] = True
        aggregated_context[f"{crew_id}_insights"] = {
            "top_entities": [r["entity_id"] for r in crew_recommendations if r["delta"] > 0][:3],
            "total_impact": sum(r["expected_impact"] for r in crew_recommendations),
        }
    
    # Calculate overall metrics
    total_impact = sum(r["expected_impact"] for r in all_recommendations)
    avg_confidence = sum(r["confidence"] for r in all_recommendations) / max(1, len(all_recommendations))
    
    # Risk assessment
    if avg_confidence > 0.85:
        risk_level = "LOW"
    elif avg_confidence > 0.70:
        risk_level = "MODERATE"
    else:
        risk_level = "HIGH"
    
    execution_time = int((datetime.now() - start_time).total_seconds() * 1000)
    
    # Build executive summary
    exec_summary = (
        f"Executed '{scenario['name']}' scenario across {len(crews_executed)} crews. "
        f"Generated {len(all_recommendations)} coordinated recommendations with expected impact of "
        f"${total_impact:,.0f}. Overall confidence: {avg_confidence:.0%}. "
        f"Crews collaborated to optimize {scenario['objective_description']}."
    )
    
    return {
        "success": True,
        "session_id": session_id,
        "scenario_id": scenario_id,
        "scenario_name": scenario["name"],
        "selection_mode": selection_mode,
        "crews_executed": crews_executed,
        "crew_outputs": crew_outputs,
        "aggregated_recommendations": all_recommendations,
        "supporting_evidence": all_evidence,
        "reasoning_chain": {
            "steps": reasoning_steps,
            "crews_involved": crews_executed,
            "cross_crew_messages": [],
        },
        "executive_summary": exec_summary,
        "total_expected_impact": total_impact,
        "overall_confidence": avg_confidence,
        "risk_assessment": f"{risk_level} RISK: {avg_confidence:.0%} confidence with {risk_appetite} risk appetite. Max reallocation: {max_reallocation_pct:.0%}",
        "constraints_satisfied": True,
        "constraint_violations": [],
        "execution_time_ms": execution_time,
        "created_at": datetime.now().isoformat(),
    }


def _get_entities_for_crew(crew_id: str):
    """Get entity list for a specific crew type."""
    if crew_id == "brand_optimization":
        return [
            ("brand", "brand-a", "Brand A"),
            ("brand", "brand-b", "Brand B"),
        ]
    elif crew_id == "rmn_optimization":
        return [
            ("rmn", "walmart", "Walmart"),
            ("rmn", "amazon", "Amazon"),
            ("rmn", "target", "Target"),
        ]
    elif crew_id == "channel_optimization":
        return [
            ("channel", "search", "Sponsored Search"),
            ("channel", "display", "Display"),
            ("channel", "video", "Video"),
        ]
    elif crew_id == "campaign_optimization":
        return [
            ("campaign", "campaign-1", "Q1 Awareness"),
            ("campaign", "campaign-2", "Performance Max"),
        ]
    else:
        return [("entity", "entity-1", "Entity 1")]


# ============================================================================
# AGENTS OVERVIEW ENDPOINT
# ============================================================================

@app.get("/api/agents/overview")
async def get_agents_overview():
    """Get all agents across ecosystems for the Agents Overview page"""
    agents = [
        # Data Agents
        {
            "id": "data-quality-agent",
            "name": "Data Quality Agent",
            "role": "Validates and cleanses incoming data streams",
            "category": "data",
            "ecosystem": "core",
            "description": "Monitors data quality metrics, identifies anomalies, and ensures data integrity across all pipelines.",
            "goal": "Maintain 99.9% data quality score across all inputs",
            "status": "active",
            "lastActivity": "2 min ago",
            "tasksCompleted": 1247,
            "avgResponseTime": 45
        },
        {
            "id": "federation-agent",
            "name": "Federation Agent",
            "role": "Orchestrates cross-retailer data federation",
            "category": "data",
            "ecosystem": "tee",
            "description": "Coordinates secure data sharing between retailers using TEE-based federation protocols.",
            "goal": "Enable privacy-preserving analytics across 5+ retailers",
            "status": "active",
            "lastActivity": "5 min ago",
            "tasksCompleted": 89,
            "avgResponseTime": 2500
        },
        # Analytics Agents
        {
            "id": "attribution-agent",
            "name": "Attribution Agent",
            "role": "Multi-touch attribution modeling",
            "category": "analytics",
            "ecosystem": "rmn",
            "description": "Calculates incrementality and attribution for media spend across channels using Bayesian methods.",
            "goal": "Provide accurate ROI measurement for all campaigns",
            "status": "active",
            "lastActivity": "1 min ago",
            "tasksCompleted": 456,
            "avgResponseTime": 1200
        },
        {
            "id": "elasticity-agent",
            "name": "Elasticity Agent",
            "role": "Price and promotion elasticity analysis",
            "category": "analytics",
            "ecosystem": "rmn",
            "description": "Models demand elasticity to optimize pricing and promotional strategies.",
            "goal": "Identify optimal price points for maximum margin",
            "status": "idle",
            "lastActivity": "1 hour ago",
            "tasksCompleted": 234,
            "avgResponseTime": 890
        },
        {
            "id": "demand-forecaster",
            "name": "Demand Forecaster",
            "role": "ML-based demand prediction",
            "category": "analytics",
            "ecosystem": "demand_procurement",
            "description": "Generates probabilistic demand forecasts using ensemble ML models and Bayesian inference.",
            "goal": "Achieve <10% MAPE on 13-week forecasts",
            "status": "working",
            "lastActivity": "Just now",
            "tasksCompleted": 892,
            "avgResponseTime": 3400
        },
        # Simulation Agents
        {
            "id": "digital-twin-agent",
            "name": "Digital Twin Agent",
            "role": "Inventory simulation engine",
            "category": "simulation",
            "ecosystem": "demand_procurement",
            "description": "Simulates inventory dynamics, lead times, and supply chain scenarios.",
            "goal": "Run 1000+ scenarios per optimization cycle",
            "status": "active",
            "lastActivity": "30 sec ago",
            "tasksCompleted": 15678,
            "avgResponseTime": 150
        },
        {
            "id": "scenario-generator",
            "name": "Scenario Generator",
            "role": "What-if analysis for media plans",
            "category": "simulation",
            "ecosystem": "rmn",
            "description": "Generates and evaluates hypothetical media allocation scenarios.",
            "goal": "Explore 50+ scenarios per optimization request",
            "status": "idle",
            "lastActivity": "15 min ago",
            "tasksCompleted": 3421,
            "avgResponseTime": 800
        },
        # Optimization Agents
        {
            "id": "budget-optimizer",
            "name": "Budget Optimizer",
            "role": "Multi-objective budget allocation",
            "category": "optimization",
            "ecosystem": "rmn",
            "description": "Optimizes media budget allocation across retailers and channels using constrained optimization.",
            "goal": "Maximize ROAS while meeting brand guidelines",
            "status": "active",
            "lastActivity": "3 min ago",
            "tasksCompleted": 567,
            "avgResponseTime": 4500
        },
        {
            "id": "inventory-optimizer",
            "name": "Inventory Optimizer",
            "role": "Safety stock and reorder optimization",
            "category": "optimization",
            "ecosystem": "demand_procurement",
            "description": "Calculates optimal reorder points, safety stock levels, and order quantities.",
            "goal": "Minimize working capital while maintaining 98% service level",
            "status": "active",
            "lastActivity": "1 min ago",
            "tasksCompleted": 1123,
            "avgResponseTime": 2100
        },
        # Governance Agents
        {
            "id": "policy-validator",
            "name": "Policy Validator",
            "role": "Business rule enforcement",
            "category": "governance",
            "ecosystem": "core",
            "description": "Validates recommendations against business policies and constraints.",
            "goal": "100% compliance with brand guidelines",
            "status": "active",
            "lastActivity": "1 min ago",
            "tasksCompleted": 2345,
            "avgResponseTime": 50
        },
        {
            "id": "audit-agent",
            "name": "Audit Agent",
            "role": "Decision audit trail management",
            "category": "governance",
            "ecosystem": "core",
            "description": "Maintains complete audit trails for all agent decisions and recommendations.",
            "goal": "Full traceability for regulatory compliance",
            "status": "active",
            "lastActivity": "Just now",
            "tasksCompleted": 8901,
            "avgResponseTime": 25
        },
        # Communication Agents
        {
            "id": "rationale-generator",
            "name": "Rationale Generator",
            "role": "Human-readable explanation synthesis",
            "category": "communication",
            "ecosystem": "core",
            "description": "Generates clear explanations and rationales for agent recommendations.",
            "goal": "Make AI decisions transparent and actionable",
            "status": "idle",
            "lastActivity": "10 min ago",
            "tasksCompleted": 678,
            "avgResponseTime": 1500
        },
        {
            "id": "report-agent",
            "name": "Report Agent",
            "role": "Executive summary generation",
            "category": "communication",
            "ecosystem": "rmn",
            "description": "Creates executive summaries and reports from optimization results.",
            "goal": "Deliver actionable insights to stakeholders",
            "status": "idle",
            "lastActivity": "30 min ago",
            "tasksCompleted": 145,
            "avgResponseTime": 3000
        },
    ]
    
    return {"agents": agents}


# ============================================================================
# SCENARIO ADVISOR ENDPOINTS
# Conversational interface for querying CrewAI agents about scenarios
# ============================================================================

from vendor.agents.conversation import UnifiedScenarioAdvisor, AdvisorSession, AdvisorResponse
from vendor.agents.conversation.scenario_advisor import Ecosystem, create_advisor

# Global advisor instance
_advisor: Optional[UnifiedScenarioAdvisor] = None

def get_advisor() -> UnifiedScenarioAdvisor:
    """Get or create the scenario advisor instance"""
    global _advisor
    if _advisor is None:
        _advisor = create_advisor()
    return _advisor


class AdvisorChatRequest(BaseModel):
    """Request to send a message to the advisor"""
    message: str
    stream: bool = False


class AdvisorSessionRequest(BaseModel):
    """Request to create a new advisor session"""
    ecosystem: str = "auto"  # auto, rmn, demand_procurement


@app.post("/api/advisor/chat")
async def create_advisor_session(request: AdvisorSessionRequest):
    """Create a new advisor chat session"""
    advisor = get_advisor()
    
    # Map string to enum
    ecosystem_map = {
        "auto": Ecosystem.AUTO,
        "rmn": Ecosystem.RMN,
        "demand_procurement": Ecosystem.DEMAND_PROCUREMENT,
    }
    ecosystem = ecosystem_map.get(request.ecosystem, Ecosystem.AUTO)
    
    session = advisor.create_session(ecosystem=ecosystem)
    
    return {
        "session_id": session.session_id,
        "created_at": session.created_at.isoformat(),
        "ecosystem": session.ecosystem.value,
        "message": "Session created. How can I help you with scenario optimization today?"
    }


@app.post("/api/advisor/chat/{session_id}/message")
async def send_advisor_message(session_id: str, request: AdvisorChatRequest):
    """Send a message to the advisor and get a response"""
    advisor = get_advisor()
    
    session = advisor.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Get response
    response = advisor.send_message(
        session_id=session_id,
        message=request.message,
        stream=request.stream,
    )
    
    return {
        "session_id": session_id,
        "response": response.to_dict() if hasattr(response, 'to_dict') else {
            "message": response.message,
            "ecosystem": response.ecosystem.value if response.ecosystem else None,
            "scenario_ids": response.scenario_ids,
            "data": response.data,
            "actions": response.actions,
            "confidence": response.confidence,
        }
    }


@app.get("/api/advisor/chat/{session_id}/history")
async def get_advisor_history(session_id: str):
    """Get conversation history for a session"""
    advisor = get_advisor()
    
    session = advisor.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    return {
        "session_id": session_id,
        "ecosystem": session.ecosystem.value,
        "messages": session.get_history(),
        "context": session.context,
    }


@app.delete("/api/advisor/chat/{session_id}")
async def delete_advisor_session(session_id: str):
    """Delete an advisor session"""
    advisor = get_advisor()
    
    if advisor.delete_session(session_id):
        return {"status": "deleted", "session_id": session_id}
    else:
        raise HTTPException(status_code=404, detail="Session not found")


@app.get("/api/advisor/scenarios/{ecosystem}")
async def get_advisor_scenarios(ecosystem: str):
    """Get available scenarios for an ecosystem"""
    advisor = get_advisor()
    
    if ecosystem == "rmn":
        result = advisor._get_rmn_scenarios(category="all")
        return {
            "ecosystem": "rmn",
            "scenarios": result.get("scenarios", []),
            "categories": ["core_outcome", "incrementality", "risk_governance", "portfolio", "operational"]
        }
    elif ecosystem == "demand_procurement" or ecosystem == "dp":
        # D&P scenarios are more about comparison modes
        return {
            "ecosystem": "demand_procurement",
            "scenarios": [
                {"scenario_id": "baseline", "name": "Baseline", "description": "Current inventory policy evaluation"},
                {"scenario_id": "conservative", "name": "Conservative", "description": "Higher safety stock for risk mitigation"},
                {"scenario_id": "demand_up_20pct", "name": "Demand +20%", "description": "Stress test with 20% demand increase"},
                {"scenario_id": "demand_down_20pct", "name": "Demand -20%", "description": "Test with 20% demand decrease"},
                {"scenario_id": "supply_disruption", "name": "Supply Disruption", "description": "No incoming orders scenario"},
            ],
            "categories": ["baseline", "sensitivity", "stress_test"]
        }
    else:
        raise HTTPException(status_code=400, detail=f"Unknown ecosystem: {ecosystem}")


@app.get("/api/advisor/agents/{ecosystem}")
async def get_advisor_agents(ecosystem: str):
    """Get available agents for an ecosystem"""
    if ecosystem == "rmn":
        return {
            "ecosystem": "rmn",
            "agents": [
                {"id": "data_ingestion", "name": "Data Ingestion Agent", "role": "Validates and preprocesses media data"},
                {"id": "attribution", "name": "Attribution Agent", "role": "Computes channel attribution and incrementality"},
                {"id": "elasticity", "name": "Elasticity Agent", "role": "Maintains Bayesian elasticity posteriors"},
                {"id": "scenario", "name": "Scenario Agent", "role": "Generates and evaluates allocation scenarios"},
                {"id": "twin", "name": "Digital Twin Agent", "role": "Simulates retail media performance"},
                {"id": "optimizer", "name": "Optimizer Agent", "role": "Computes optimal budget allocations"},
                {"id": "governance", "name": "Governance Agent", "role": "Validates decisions against business rules"},
                {"id": "rationale", "name": "Rationale Agent", "role": "Generates explanations and recommendations"},
            ]
        }
    elif ecosystem == "demand_procurement" or ecosystem == "dp":
        return {
            "ecosystem": "demand_procurement",
            "agents": [
                {"id": "demand_forecast", "name": "Demand Forecast Agent", "role": "Generates demand predictions"},
                {"id": "inventory_optimization", "name": "Inventory Optimization Agent", "role": "Computes optimal policies"},
                {"id": "supplier_management", "name": "Supplier Management Agent", "role": "Manages supplier relationships"},
                {"id": "risk_analysis", "name": "Risk Analysis Agent", "role": "Assesses stockout and overstock risks"},
                {"id": "scenario_simulation", "name": "Scenario Simulation Agent", "role": "Runs Monte Carlo simulations"},
                {"id": "procurement_planning", "name": "Procurement Planning Agent", "role": "Generates procurement plans"},
                {"id": "governance", "name": "Governance Agent", "role": "Validates procurement decisions"},
                {"id": "reporting", "name": "Reporting Agent", "role": "Generates summaries and reports"},
            ]
        }
    else:
        raise HTTPException(status_code=400, detail=f"Unknown ecosystem: {ecosystem}")


@app.get("/api/advisor/status")
async def get_advisor_status():
    """Get advisor service status"""
    advisor = get_advisor()
    
    return {
        "status": "available",
        "openai_available": advisor.client.is_available if advisor.client else False,
        "model": advisor.client.model if advisor.client else None,
        "active_sessions": len(advisor.sessions),
        "ecosystems": ["rmn", "demand_procurement"],
    }


# ============================================================================
# UNIFIED TWIN STATE STORE API
# Real data from TwinStateStore with persistence and history
# ============================================================================

# Initialize unified twin manager
_twin_manager = None

def get_twin_manager():
    """Get or create unified twin manager singleton"""
    global _twin_manager
    if _twin_manager is None:
        try:
            from vendor.retail_media.unified_twin_manager import get_unified_twin_manager
            _twin_manager = get_unified_twin_manager()
        except Exception as e:
            logger.error(f"Failed to initialize twin manager: {e}")
            _twin_manager = None
    return _twin_manager


@app.get("/api/twin-store/summary")
async def get_twin_store_summary():
    """Get summary of all twin states in the store"""
    manager = get_twin_manager()
    if not manager:
        return {"error": "Twin manager not available", "summary": {}}
    
    return manager.get_summary()


@app.get("/api/twin-store/rmn")
async def get_all_rmn_twins():
    """Get all RMN twin states"""
    manager = get_twin_manager()
    if not manager:
        return {"rmns": [], "count": 0}
    
    states = manager.get_all_rmn_states()
    return {
        "rmns": [s.dict() for s in states],
        "count": len(states),
    }


@app.get("/api/twin-store/rmn/{retailer_id}")
async def get_rmn_twin(retailer_id: str):
    """Get RMN twin state for a specific retailer"""
    manager = get_twin_manager()
    if not manager:
        raise HTTPException(status_code=503, detail="Twin manager not available")
    
    state = manager.get_rmn_state(retailer_id)
    if not state:
        raise HTTPException(status_code=404, detail=f"RMN state not found for {retailer_id}")
    
    return state.dict()


@app.get("/api/twin-store/rmn/{retailer_id}/history")
async def get_rmn_twin_history(retailer_id: str, limit: int = 50):
    """Get RMN twin state history"""
    manager = get_twin_manager()
    if not manager:
        return {"history": [], "count": 0}
    
    history = manager.get_rmn_history(retailer_id, limit)
    return {"history": history, "count": len(history)}


@app.get("/api/twin-store/brands")
async def get_all_brand_twins(retailer_id: Optional[str] = None):
    """Get all Brand twin states"""
    manager = get_twin_manager()
    if not manager:
        return {"brands": [], "count": 0}
    
    states = manager.get_all_brand_states(retailer_id)
    return {
        "brands": [s.dict() for s in states],
        "count": len(states),
    }


@app.get("/api/twin-store/brands/{retailer_id}/{brand_id}")
async def get_brand_twin(retailer_id: str, brand_id: str):
    """Get Brand twin state"""
    manager = get_twin_manager()
    if not manager:
        raise HTTPException(status_code=503, detail="Twin manager not available")
    
    state = manager.get_brand_state(retailer_id, brand_id)
    if not state:
        raise HTTPException(status_code=404, detail=f"Brand state not found for {retailer_id}/{brand_id}")
    
    return state.dict()


@app.get("/api/twin-store/brands/{retailer_id}/{brand_id}/history")
async def get_brand_twin_history(retailer_id: str, brand_id: str, limit: int = 50):
    """Get Brand twin state history"""
    manager = get_twin_manager()
    if not manager:
        return {"history": [], "count": 0}
    
    history = manager.get_brand_history(retailer_id, brand_id, limit)
    return {"history": history, "count": len(history)}


@app.get("/api/twin-store/campaigns")
async def get_all_campaign_twins(retailer_id: Optional[str] = None):
    """Get all Campaign twin states"""
    manager = get_twin_manager()
    if not manager:
        return {"campaigns": [], "count": 0}
    
    states = manager.get_all_campaign_states(retailer_id)
    return {
        "campaigns": [s.dict() for s in states],
        "count": len(states),
    }


@app.get("/api/twin-store/campaigns/{retailer_id}/{campaign_id}")
async def get_campaign_twin(retailer_id: str, campaign_id: str):
    """Get Campaign twin state"""
    manager = get_twin_manager()
    if not manager:
        raise HTTPException(status_code=503, detail="Twin manager not available")
    
    state = manager.get_campaign_state(retailer_id, campaign_id)
    if not state:
        raise HTTPException(status_code=404, detail=f"Campaign state not found for {retailer_id}/{campaign_id}")
    
    return state.dict()


@app.get("/api/twin-store/channels")
async def get_all_channel_twins(retailer_id: Optional[str] = None):
    """Get all Channel twin states"""
    manager = get_twin_manager()
    if not manager:
        return {"channels": [], "count": 0}
    
    states = manager.get_all_channel_states(retailer_id)
    return {
        "channels": [s.dict() for s in states],
        "count": len(states),
    }


@app.get("/api/twin-store/channels/{retailer_id}/{channel_type}")
async def get_channel_twin(retailer_id: str, channel_type: str):
    """Get Channel twin state"""
    manager = get_twin_manager()
    if not manager:
        raise HTTPException(status_code=503, detail="Twin manager not available")
    
    state = manager.get_channel_state(retailer_id, channel_type)
    if not state:
        raise HTTPException(status_code=404, detail=f"Channel state not found for {retailer_id}/{channel_type}")
    
    return state.dict()


@app.get("/api/twin-store/channels/{retailer_id}/{channel_type}/history")
async def get_channel_twin_history(retailer_id: str, channel_type: str, limit: int = 50):
    """Get Channel twin state history"""
    manager = get_twin_manager()
    if not manager:
        return {"history": [], "count": 0}
    
    history = manager.get_channel_history(retailer_id, channel_type, limit)
    return {"history": history, "count": len(history)}


@app.post("/api/twin-store/ingest/csv")
async def ingest_csv_data(
    twin_type: str,
    retailer_id: str,
    file_path: str,
):
    """
    Ingest CSV data into twin states.
    
    Args:
        twin_type: One of 'rmn', 'brand', 'campaign', 'channel'
        retailer_id: Retailer identifier
        file_path: Path to CSV file
    """
    manager = get_twin_manager()
    if not manager:
        raise HTTPException(status_code=503, detail="Twin manager not available")
    
    try:
        if twin_type == "rmn":
            result = manager.ingest_rmn_csv(file_path, retailer_id)
        elif twin_type == "brand":
            result = manager.ingest_brand_csv(file_path, retailer_id)
        elif twin_type == "campaign":
            result = manager.ingest_campaign_csv(file_path, retailer_id)
        elif twin_type == "channel":
            result = manager.ingest_channel_csv(file_path, retailer_id)
        else:
            raise HTTPException(status_code=400, detail=f"Invalid twin_type: {twin_type}")
        
        return {
            "success": result.success,
            "ingestion_id": result.ingestion_id,
            "records_processed": result.records_processed,
            "records_succeeded": result.records_succeeded,
            "records_failed": result.records_failed,
            "states_created": result.states_created,
            "states_updated": result.states_updated,
            "errors": result.errors[:10] if result.errors else [],  # Limit errors returned
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/twin-store/aggregate/{retailer_id}")
async def compute_rmn_aggregates(retailer_id: str):
    """Compute RMN aggregates from child states"""
    manager = get_twin_manager()
    if not manager:
        raise HTTPException(status_code=503, detail="Twin manager not available")
    
    state = manager.compute_rmn_aggregates(retailer_id)
    if not state:
        raise HTTPException(status_code=404, detail=f"No states found for {retailer_id}")
    
    return state.dict()


@app.get("/api/twin-store/retailer/{retailer_id}/overview")
async def get_retailer_overview(retailer_id: str):
    """Get complete overview for a retailer including all twin types"""
    manager = get_twin_manager()
    if not manager:
        raise HTTPException(status_code=503, detail="Twin manager not available")
    
    rmn = manager.get_rmn_state(retailer_id)
    brands = manager.get_all_brand_states(retailer_id)
    campaigns = manager.get_all_campaign_states(retailer_id)
    channels = manager.get_all_channel_states(retailer_id)
    
    return {
        "retailer_id": retailer_id,
        "rmn": rmn.dict() if rmn else None,
        "brands": {
            "count": len(brands),
            "states": [b.dict() for b in brands],
        },
        "campaigns": {
            "count": len(campaigns),
            "states": [c.dict() for c in campaigns],
        },
        "channels": {
            "count": len(channels),
            "states": [ch.dict() for ch in channels],
        },
    }


@app.post("/api/twin-store/persist")
async def persist_all_twins():
    """Persist all twin states to disk"""
    manager = get_twin_manager()
    if not manager:
        raise HTTPException(status_code=503, detail="Twin manager not available")
    
    manager.persist_all()
    return {"status": "persisted", "summary": manager.get_summary()}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
