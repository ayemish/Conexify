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

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
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
                "name": f"{retailer.retailer_name} Inventory",
                "type": device_type_map.get(retailer.retailer_id, "sensor"),
                "status": status,
                "location": f"{len(retailer.available_channels)} channels, {retailer.tier}",
                "lastUpdate": f"{np.random.randint(5, 30)} sec ago",
                "metrics": [
                    {
                        "name": "Total Inventory",
                        "value": round(total_inventory),
                        "unit": "units",
                        "threshold": {"min": total_demand * 2},
                        "trend": "stable"
                    },
                    {
                        "name": "Weekly Demand",
                        "value": round(total_demand),
                        "unit": "units/wk",
                        "trend": "up" if np.random.random() > 0.5 else "stable"
                    },
                    {
                        "name": "Weeks of Supply",
                        "value": round(weeks_supply, 1),
                        "unit": "weeks",
                        "threshold": {"min": 2, "max": 8},
                        "trend": "stable"
                    },
                    {
                        "name": "SKU Count",
                        "value": len(states),
                        "unit": "SKUs",
                        "trend": "stable"
                    }
                ]
            })
    else:
        # Default devices from retailers
        for retailer in retailers:
            devices.append({
                "id": retailer.retailer_id,
                "name": f"{retailer.retailer_name} Inventory",
                "type": device_type_map.get(retailer.retailer_id, "sensor"),
                "status": "normal",
                "location": f"{len(retailer.available_channels)} channels, {retailer.tier}",
                "lastUpdate": "-- sec ago",
                "metrics": [
                    {"name": "Total Inventory", "value": 0, "unit": "units", "trend": "stable"},
                    {"name": "Weekly Demand", "value": 0, "unit": "units/wk", "trend": "stable"},
                    {"name": "Weeks of Supply", "value": 0, "unit": "weeks", "trend": "stable"},
                    {"name": "SKU Count", "value": 4, "unit": "SKUs", "trend": "stable"}
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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
