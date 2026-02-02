"""
Unified Scenario Advisor - Conversational Interface for CrewAI Agents

Provides an OpenAI-powered chat interface that routes queries to appropriate
agents in the RMN and Demand/Procurement ecosystems.
"""

import uuid
import json
import logging
from typing import Dict, List, Optional, Any, Generator
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from .openai_client import OpenAIClient, ChatMessage, MessageRole, FunctionDefinition

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class Ecosystem(Enum):
    """Available ecosystems"""
    RMN = "rmn"
    DEMAND_PROCUREMENT = "demand_procurement"
    AUTO = "auto"


@dataclass
class AdvisorResponse:
    """Response from the scenario advisor"""
    message: str
    ecosystem: Optional[Ecosystem] = None
    scenario_ids: List[str] = field(default_factory=list)
    data: Optional[Dict[str, Any]] = None
    actions: List[Dict[str, Any]] = field(default_factory=list)
    agent_source: Optional[str] = None
    confidence: float = 0.0
    timestamp: datetime = field(default_factory=datetime.utcnow)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "message": self.message,
            "ecosystem": self.ecosystem.value if self.ecosystem else None,
            "scenario_ids": self.scenario_ids,
            "data": self.data,
            "actions": self.actions,
            "agent_source": self.agent_source,
            "confidence": self.confidence,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class AdvisorSession:
    """A conversation session with the advisor"""
    session_id: str
    created_at: datetime
    messages: List[ChatMessage] = field(default_factory=list)
    ecosystem: Ecosystem = Ecosystem.AUTO
    context: Dict[str, Any] = field(default_factory=dict)
    
    def add_message(self, role: MessageRole, content: str, **kwargs):
        """Add a message to the session"""
        self.messages.append(ChatMessage(role=role, content=content, **kwargs))
    
    def get_history(self) -> List[Dict[str, Any]]:
        """Get conversation history"""
        return [
            {
                "role": m.role.value,
                "content": m.content,
                "timestamp": m.timestamp.isoformat(),
            }
            for m in self.messages
        ]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "created_at": self.created_at.isoformat(),
            "ecosystem": self.ecosystem.value,
            "message_count": len(self.messages),
            "context": self.context,
        }


class UnifiedScenarioAdvisor:
    """
    Unified conversational interface for RMN and Demand/Procurement agents.
    
    Routes user queries to appropriate agents using OpenAI function calling
    and maintains session context for coherent conversations.
    """
    
    SYSTEM_PROMPT = """You are a Scenario Advisory Assistant for retail optimization. You help users explore and understand scenarios in two domains:

## RMN (Retail Media Network) Optimization
You can help with:
- Media spend optimization across channels (Sponsored Search, Display, Connected TV, Email, etc.)
- ROAS (Return on Ad Spend) analysis and improvement
- Incrementality measurement and attribution
- Budget allocation recommendations
- Scenario comparison (Grow Revenue, Maintain Stability, Maximize ROAS, etc.)

## Demand Forecasting & Procurement
You can help with:
- Demand forecasting for SKUs
- Inventory optimization (reorder points, safety stock, EOQ)
- Stockout risk assessment
- Procurement planning and supplier management
- Service level analysis

## Your Approach
1. First understand the user's domain (RMN vs Demand/Procurement) from context
2. Ask clarifying questions if needed
3. Use available tools to fetch real data and scenarios
4. Provide evidence-based recommendations with confidence levels
5. Explain trade-offs between different scenarios
6. Support follow-up questions within the conversation context

Always cite specific data points and probabilities when available. Be concise but thorough."""

    def __init__(
        self,
        openai_client: Optional[OpenAIClient] = None,
    ):
        self.client = openai_client or OpenAIClient()
        self.sessions: Dict[str, AdvisorSession] = {}
        
        # Lazy-loaded agent references
        self._rmn_orchestrator = None
        self._dp_orchestrator = None
        self._scenario_catalog = None
        
        # Register tool functions
        self._register_tools()
        
        logger.info("UnifiedScenarioAdvisor initialized")
    
    def _register_tools(self):
        """Register OpenAI function tools"""
        
        # RMN Tools
        self.client.register_function(FunctionDefinition(
            name="get_rmn_scenarios",
            description="Get available RMN (Retail Media Network) optimization scenarios by category",
            parameters={
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "enum": ["core_outcome", "incrementality", "risk_governance", "portfolio", "operational", "all"],
                        "description": "Scenario category to filter by"
                    }
                },
                "required": []
            },
            handler=self._get_rmn_scenarios
        ))
        
        self.client.register_function(FunctionDefinition(
            name="get_scenario_details",
            description="Get detailed information about a specific RMN scenario",
            parameters={
                "type": "object",
                "properties": {
                    "scenario_id": {
                        "type": "string",
                        "description": "The scenario ID (e.g., 'grow_revenue_brand', 'maximize_roas')"
                    }
                },
                "required": ["scenario_id"]
            },
            handler=self._get_scenario_details
        ))
        
        self.client.register_function(FunctionDefinition(
            name="recommend_rmn_scenario",
            description="Get a scenario recommendation based on user's objective and constraints",
            parameters={
                "type": "object",
                "properties": {
                    "objective": {
                        "type": "string",
                        "description": "User's primary objective (e.g., 'grow revenue', 'improve efficiency', 'reduce risk')"
                    },
                    "risk_appetite": {
                        "type": "string",
                        "enum": ["conservative", "balanced", "aggressive"],
                        "description": "User's risk tolerance"
                    },
                    "budget": {
                        "type": "number",
                        "description": "Available budget in dollars"
                    }
                },
                "required": ["objective"]
            },
            handler=self._recommend_rmn_scenario
        ))
        
        # Demand/Procurement Tools
        self.client.register_function(FunctionDefinition(
            name="get_demand_forecast",
            description="Get demand forecast for a SKU",
            parameters={
                "type": "object",
                "properties": {
                    "sku_id": {
                        "type": "string",
                        "description": "SKU identifier"
                    },
                    "horizon_weeks": {
                        "type": "integer",
                        "description": "Forecast horizon in weeks (default: 13)"
                    }
                },
                "required": ["sku_id"]
            },
            handler=self._get_demand_forecast
        ))
        
        self.client.register_function(FunctionDefinition(
            name="get_inventory_policy",
            description="Get inventory optimization recommendation (reorder point, order quantity, safety stock)",
            parameters={
                "type": "object",
                "properties": {
                    "sku_id": {
                        "type": "string",
                        "description": "SKU identifier"
                    }
                },
                "required": ["sku_id"]
            },
            handler=self._get_inventory_policy
        ))
        
        self.client.register_function(FunctionDefinition(
            name="assess_stockout_risk",
            description="Analyze stockout probability and risk for a SKU",
            parameters={
                "type": "object",
                "properties": {
                    "sku_id": {
                        "type": "string",
                        "description": "SKU identifier"
                    },
                    "current_inventory": {
                        "type": "integer",
                        "description": "Current inventory level"
                    }
                },
                "required": ["sku_id"]
            },
            handler=self._assess_stockout_risk
        ))
        
        self.client.register_function(FunctionDefinition(
            name="compare_dp_scenarios",
            description="Compare different demand/procurement scenarios (baseline, conservative, demand variations)",
            parameters={
                "type": "object",
                "properties": {
                    "sku_id": {
                        "type": "string",
                        "description": "SKU identifier"
                    },
                    "scenarios": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Scenario names to compare (e.g., ['baseline', 'conservative', 'demand_up_20pct'])"
                    }
                },
                "required": ["sku_id"]
            },
            handler=self._compare_dp_scenarios
        ))
        
        self.client.register_function(FunctionDefinition(
            name="get_procurement_plan",
            description="Generate or retrieve procurement plan recommendations",
            parameters={
                "type": "object",
                "properties": {
                    "sku_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of SKU identifiers"
                    }
                },
                "required": []
            },
            handler=self._get_procurement_plan
        ))
    
    # =========================================================================
    # Session Management
    # =========================================================================
    
    def create_session(self, ecosystem: Ecosystem = Ecosystem.AUTO) -> AdvisorSession:
        """Create a new conversation session"""
        session_id = str(uuid.uuid4())
        session = AdvisorSession(
            session_id=session_id,
            created_at=datetime.utcnow(),
            ecosystem=ecosystem,
        )
        
        # Add system message
        session.add_message(MessageRole.SYSTEM, self.SYSTEM_PROMPT)
        
        self.sessions[session_id] = session
        logger.info(f"Created session: {session_id}")
        
        return session
    
    def get_session(self, session_id: str) -> Optional[AdvisorSession]:
        """Get an existing session"""
        return self.sessions.get(session_id)
    
    def delete_session(self, session_id: str) -> bool:
        """Delete a session"""
        if session_id in self.sessions:
            del self.sessions[session_id]
            return True
        return False
    
    # =========================================================================
    # Chat Interface
    # =========================================================================
    
    def send_message(
        self,
        session_id: str,
        message: str,
        stream: bool = False,
    ) -> AdvisorResponse:
        """
        Send a message and get a response.
        
        Args:
            session_id: Session identifier
            message: User's message
            stream: Whether to stream the response
            
        Returns:
            AdvisorResponse with the assistant's reply
        """
        session = self.get_session(session_id)
        if not session:
            return AdvisorResponse(
                message="Session not found. Please create a new session.",
                confidence=0.0,
            )
        
        # Add user message
        session.add_message(MessageRole.USER, message)
        
        # Get response from OpenAI
        response = self.client.chat(session.messages, use_tools=True, stream=stream)
        
        if stream:
            return self._handle_streaming_response(session, response)
        else:
            return self._handle_response(session, response)
    
    def _handle_response(
        self,
        session: AdvisorSession,
        response: Dict[str, Any],
    ) -> AdvisorResponse:
        """Handle non-streaming response"""
        
        # Check for tool calls
        if response.get("tool_calls"):
            return self._handle_tool_calls(session, response)
        
        # Regular message response
        content = response.get("content", "")
        session.add_message(MessageRole.ASSISTANT, content)
        
        # Detect ecosystem from response
        ecosystem = self._detect_ecosystem(content)
        
        return AdvisorResponse(
            message=content,
            ecosystem=ecosystem,
            confidence=0.85 if not response.get("mock") else 0.5,
            agent_source="openai" if not response.get("mock") else "mock",
        )
    
    def _handle_tool_calls(
        self,
        session: AdvisorSession,
        response: Dict[str, Any],
    ) -> AdvisorResponse:
        """Handle response with tool calls"""
        tool_calls = response["tool_calls"]
        all_results = []
        ecosystem = None
        data = {}
        
        for tool_call in tool_calls:
            func_name = tool_call["function"]["name"]
            
            # Execute the tool
            result_str = self.client.execute_tool_call(tool_call)
            result = json.loads(result_str)
            all_results.append(result)
            
            # Detect ecosystem from function name
            if func_name.startswith("get_rmn") or func_name.startswith("recommend_rmn"):
                ecosystem = Ecosystem.RMN
            elif func_name in ["get_demand_forecast", "get_inventory_policy", 
                             "assess_stockout_risk", "compare_dp_scenarios", 
                             "get_procurement_plan"]:
                ecosystem = Ecosystem.DEMAND_PROCUREMENT
            
            # Collect data
            data[func_name] = result
            
            # Add tool result to messages
            session.add_message(
                MessageRole.TOOL,
                result_str,
                tool_call_id=tool_call["id"],
                name=func_name,
            )
        
        # Get final response from OpenAI with tool results
        final_response = self.client.chat(session.messages, use_tools=False)
        content = final_response.get("content", "")
        
        session.add_message(MessageRole.ASSISTANT, content)
        
        # Extract scenario IDs from results
        scenario_ids = []
        for result in all_results:
            if isinstance(result, dict):
                if "scenarios" in result:
                    scenario_ids.extend([s.get("scenario_id", "") for s in result["scenarios"]])
                elif "scenario_id" in result:
                    scenario_ids.append(result["scenario_id"])
        
        return AdvisorResponse(
            message=content,
            ecosystem=ecosystem,
            scenario_ids=scenario_ids,
            data=data,
            confidence=0.9,
            agent_source="tool_chain",
        )
    
    def _handle_streaming_response(
        self,
        session: AdvisorSession,
        response_generator: Generator,
    ) -> Generator[AdvisorResponse, None, None]:
        """Handle streaming response"""
        full_content = ""
        
        for chunk in response_generator:
            if chunk.get("type") == "content":
                full_content += chunk["content"]
                yield AdvisorResponse(
                    message=chunk["content"],
                    confidence=0.0,  # Partial
                )
            elif chunk.get("type") == "done":
                session.add_message(MessageRole.ASSISTANT, full_content)
                yield AdvisorResponse(
                    message=full_content,
                    confidence=0.85,
                    agent_source="openai",
                )
    
    def _detect_ecosystem(self, content: str) -> Optional[Ecosystem]:
        """Detect ecosystem from message content"""
        content_lower = content.lower()
        
        rmn_keywords = ["rmn", "media", "roas", "channel", "incrementality", "attribution", "ad spend"]
        dp_keywords = ["inventory", "stockout", "demand", "forecast", "procurement", "sku", "reorder", "safety stock"]
        
        rmn_score = sum(1 for kw in rmn_keywords if kw in content_lower)
        dp_score = sum(1 for kw in dp_keywords if kw in content_lower)
        
        if rmn_score > dp_score:
            return Ecosystem.RMN
        elif dp_score > rmn_score:
            return Ecosystem.DEMAND_PROCUREMENT
        return None
    
    # =========================================================================
    # Tool Handlers - RMN
    # =========================================================================
    
    def _get_rmn_scenarios(self, category: str = "all") -> Dict[str, Any]:
        """Get RMN scenarios by category"""
        try:
            from ..crews.optimization.scenarios.catalog import (
                get_all_scenarios,
                get_scenarios_by_category,
            )
            
            if category == "all":
                scenarios = get_all_scenarios()
            else:
                scenarios = get_scenarios_by_category(category)
            
            return {
                "scenarios": [
                    {
                        "scenario_id": s.scenario_id,
                        "name": s.name,
                        "description": s.description,
                        "category": s.category.value,
                        "objective_type": s.objective_type.value,
                    }
                    for s in scenarios
                ],
                "count": len(scenarios),
            }
        except ImportError:
            # Return mock data if catalog not available
            return self._mock_rmn_scenarios(category)
    
    def _get_scenario_details(self, scenario_id: str) -> Dict[str, Any]:
        """Get detailed scenario information"""
        try:
            from ..crews.optimization.scenarios.catalog import get_scenario_by_id
            
            scenario = get_scenario_by_id(scenario_id)
            if not scenario:
                return {"error": f"Scenario '{scenario_id}' not found"}
            
            return {
                "scenario_id": scenario.scenario_id,
                "name": scenario.name,
                "description": scenario.description,
                "category": scenario.category.value,
                "objective_type": scenario.objective_type.value,
                "objective_description": scenario.objective_description,
                "default_constraints": scenario.default_constraints.to_dict() if scenario.default_constraints else {},
                "triggers": [
                    {"type": t.trigger_type.value, "description": t.description}
                    for t in scenario.triggers
                ],
                "required_crews": scenario.required_crews,
                "action_templates": scenario.action_templates,
            }
        except ImportError:
            return self._mock_scenario_details(scenario_id)
    
    def _recommend_rmn_scenario(
        self,
        objective: str,
        risk_appetite: str = "balanced",
        budget: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Recommend an RMN scenario based on criteria"""
        objective_lower = objective.lower()
        
        # Simple matching logic
        if "grow" in objective_lower or "revenue" in objective_lower:
            recommended = "grow_revenue_brand"
            rationale = "Growing revenue requires maximizing incremental sales through targeted media optimization."
        elif "efficiency" in objective_lower or "roas" in objective_lower:
            recommended = "maximize_roas"
            rationale = "Efficiency focus means optimizing for return on ad spend above other metrics."
        elif "maintain" in objective_lower or "stable" in objective_lower:
            recommended = "maintain_revenue"
            rationale = "Stability mode minimizes variance while maintaining baseline performance."
        elif "risk" in objective_lower or "decline" in objective_lower:
            recommended = "prevent_decline"
            rationale = "Defensive mode minimizes probability of negative lift."
        elif "test" in objective_lower or "learn" in objective_lower:
            recommended = "experiment_incrementality"
            rationale = "Testing scenarios help learn true incrementality through controlled experiments."
        else:
            recommended = "grow_revenue_brand"
            rationale = "Default recommendation for general optimization goals."
        
        return {
            "recommended_scenario": recommended,
            "rationale": rationale,
            "risk_appetite": risk_appetite,
            "alternatives": [
                {"scenario_id": "maintain_revenue", "fit_score": 0.7},
                {"scenario_id": "maximize_roas", "fit_score": 0.65},
            ],
        }
    
    def _mock_rmn_scenarios(self, category: str) -> Dict[str, Any]:
        """Mock RMN scenarios when catalog unavailable"""
        scenarios = [
            {"scenario_id": "grow_revenue_brand", "name": "Grow Revenue for Brand", 
             "description": "Maximize incremental sales", "category": "core_outcome", "objective_type": "incremental_sales"},
            {"scenario_id": "maintain_revenue", "name": "Maintain Revenue", 
             "description": "Stability mode", "category": "core_outcome", "objective_type": "stability"},
            {"scenario_id": "maximize_roas", "name": "Maximize ROAS", 
             "description": "Efficiency optimization", "category": "core_outcome", "objective_type": "efficiency"},
            {"scenario_id": "prevent_decline", "name": "Prevent Decline", 
             "description": "Defensive triage mode", "category": "core_outcome", "objective_type": "decline_risk_min"},
        ]
        
        if category != "all":
            scenarios = [s for s in scenarios if s["category"] == category]
        
        return {"scenarios": scenarios, "count": len(scenarios)}
    
    def _mock_scenario_details(self, scenario_id: str) -> Dict[str, Any]:
        """Mock scenario details"""
        mock_details = {
            "grow_revenue_brand": {
                "scenario_id": "grow_revenue_brand",
                "name": "Grow Revenue for Brand",
                "description": "Maximize incremental dollar sales for a specific brand",
                "category": "core_outcome",
                "objective_type": "incremental_sales",
                "objective_description": "Maximize incremental $ sales for Brand X",
                "default_constraints": {"roas_floor": 1.0, "max_reallocation_pct": 0.20},
                "triggers": [
                    {"type": "threshold_breach", "description": "Brand revenue gap vs plan"},
                    {"type": "trend_detection", "description": "Competitor share gains"}
                ],
            }
        }
        return mock_details.get(scenario_id, {"error": f"Scenario '{scenario_id}' not found"})
    
    # =========================================================================
    # Tool Handlers - Demand/Procurement
    # =========================================================================
    
    def _get_demand_forecast(
        self,
        sku_id: str,
        horizon_weeks: int = 13,
    ) -> Dict[str, Any]:
        """Get demand forecast for a SKU"""
        # Generate mock forecast data
        import random
        base_demand = random.randint(80, 150)
        
        forecasts = []
        for week in range(horizon_weeks):
            # Add some trend and noise
            trend = week * 0.02
            noise = random.uniform(-0.1, 0.1)
            demand = base_demand * (1 + trend + noise)
            
            forecasts.append({
                "week": week + 1,
                "q10": round(demand * 0.8, 1),
                "q50": round(demand, 1),
                "q90": round(demand * 1.3, 1),
            })
        
        return {
            "sku_id": sku_id,
            "horizon_weeks": horizon_weeks,
            "mean_weekly_demand": round(base_demand, 1),
            "std_weekly_demand": round(base_demand * 0.15, 1),
            "forecasts": forecasts,
            "confidence": 0.85,
        }
    
    def _get_inventory_policy(self, sku_id: str) -> Dict[str, Any]:
        """Get inventory policy recommendation"""
        import random
        
        mean_demand = random.randint(80, 150)
        std_demand = mean_demand * 0.15
        lead_time_weeks = random.randint(1, 3)
        
        # Calculate safety stock (z=1.645 for 95% SL)
        z = 1.645
        safety_stock = int(z * std_demand * (lead_time_weeks ** 0.5))
        
        # Calculate reorder point
        reorder_point = int(mean_demand * lead_time_weeks + safety_stock)
        
        # Calculate EOQ
        annual_demand = mean_demand * 52
        ordering_cost = 50
        holding_cost_rate = 0.25
        unit_cost = random.randint(10, 50)
        holding_cost = unit_cost * holding_cost_rate
        eoq = int((2 * annual_demand * ordering_cost / holding_cost) ** 0.5)
        
        return {
            "sku_id": sku_id,
            "reorder_point": reorder_point,
            "order_quantity": eoq,
            "safety_stock": safety_stock,
            "expected_service_level": 0.95,
            "mean_weekly_demand": mean_demand,
            "lead_time_weeks": lead_time_weeks,
            "expected_annual_cost": {
                "holding": round(eoq/2 * holding_cost, 2),
                "ordering": round(annual_demand/eoq * ordering_cost, 2),
            },
        }
    
    def _assess_stockout_risk(
        self,
        sku_id: str,
        current_inventory: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Assess stockout risk for a SKU"""
        import random
        
        # Get policy to compare
        policy = self._get_inventory_policy(sku_id)
        
        if current_inventory is None:
            current_inventory = random.randint(50, 300)
        
        reorder_point = policy["reorder_point"]
        mean_demand = policy["mean_weekly_demand"]
        
        # Calculate risk
        if current_inventory < reorder_point:
            stockout_prob = min(0.9, (reorder_point - current_inventory) / reorder_point)
            risk_level = "high" if stockout_prob > 0.5 else "medium"
        else:
            stockout_prob = 0.05
            risk_level = "low"
        
        days_of_supply = int(current_inventory / (mean_demand / 7))
        
        return {
            "sku_id": sku_id,
            "current_inventory": current_inventory,
            "reorder_point": reorder_point,
            "stockout_probability": round(stockout_prob, 3),
            "risk_level": risk_level,
            "days_of_supply": days_of_supply,
            "recommendation": "Order immediately" if risk_level == "high" else (
                "Monitor closely" if risk_level == "medium" else "Inventory adequate"
            ),
        }
    
    def _compare_dp_scenarios(
        self,
        sku_id: str,
        scenarios: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Compare demand/procurement scenarios"""
        if not scenarios:
            scenarios = ["baseline", "conservative", "demand_up_20pct"]
        
        results = {}
        base_policy = self._get_inventory_policy(sku_id)
        
        for scenario in scenarios:
            if scenario == "baseline":
                results[scenario] = {
                    "service_level": 0.95,
                    "expected_stockouts": 2,
                    "total_annual_cost": 12500,
                    "safety_stock": base_policy["safety_stock"],
                }
            elif scenario == "conservative":
                results[scenario] = {
                    "service_level": 0.98,
                    "expected_stockouts": 0.5,
                    "total_annual_cost": 15200,
                    "safety_stock": int(base_policy["safety_stock"] * 1.5),
                }
            elif scenario == "demand_up_20pct":
                results[scenario] = {
                    "service_level": 0.88,
                    "expected_stockouts": 5,
                    "total_annual_cost": 14800,
                    "safety_stock": base_policy["safety_stock"],
                }
            else:
                results[scenario] = {"error": f"Unknown scenario: {scenario}"}
        
        # Determine recommendation
        best_scenario = min(
            [(k, v) for k, v in results.items() if "error" not in v],
            key=lambda x: x[1]["expected_stockouts"] * 1000 + x[1]["total_annual_cost"],
            default=("baseline", results.get("baseline", {}))
        )
        
        return {
            "sku_id": sku_id,
            "scenarios": results,
            "recommended_scenario": best_scenario[0],
            "recommendation_rationale": f"Best balance of service level ({best_scenario[1].get('service_level', 0):.0%}) and cost",
        }
    
    def _get_procurement_plan(
        self,
        sku_ids: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Get procurement plan recommendations"""
        if not sku_ids:
            sku_ids = ["SKU-001", "SKU-002", "SKU-003"]
        
        plans = []
        for sku_id in sku_ids:
            risk = self._assess_stockout_risk(sku_id)
            
            if risk["risk_level"] in ["high", "medium"]:
                policy = self._get_inventory_policy(sku_id)
                plans.append({
                    "sku_id": sku_id,
                    "action": "order",
                    "quantity": policy["order_quantity"],
                    "priority": 1 if risk["risk_level"] == "high" else 2,
                    "reason": f"{risk['risk_level']} stockout risk, {risk['days_of_supply']} days of supply",
                })
        
        return {
            "plans": plans,
            "total_orders": len(plans),
            "high_priority_count": sum(1 for p in plans if p["priority"] == 1),
        }


# =============================================================================
# Factory Functions
# =============================================================================

def create_advisor(
    api_key: Optional[str] = None,
    model: Optional[str] = None,
) -> UnifiedScenarioAdvisor:
    """Factory function to create a scenario advisor"""
    client = OpenAIClient(api_key=api_key, model=model)
    return UnifiedScenarioAdvisor(openai_client=client)
