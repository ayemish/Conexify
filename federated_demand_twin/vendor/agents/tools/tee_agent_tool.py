"""
TEE Agent Tool

Interface for communicating with external TEE agents via Redis message bus.
This tool allows agents in this project to invoke agents in the TEE project.
"""

import json
import redis
import logging
import uuid
from typing import Any, Dict, List, Optional, Callable
from dataclasses import dataclass, asdict
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


class TEEEventType(str, Enum):
    """Event types for TEE agent communication"""
    AGENT_DEPLOYED = "agent.deployed"
    AGENT_STARTED = "agent.started"
    AGENT_PROGRESS = "agent.progress"
    AGENT_COMPLETED = "agent.completed"
    AGENT_ERROR = "agent.error"
    CREW_REQUEST = "crew.request"
    CREW_RESPONSE = "crew.response"
    DATA_DISCOVERED = "data.discovered"
    DATA_VALIDATED = "data.validated"
    DATA_NORMALIZED = "data.normalized"
    DP_APPLIED = "dp.applied"
    DP_RECEIPT_ISSUED = "dp.receipt_issued"


@dataclass
class TEEAgentRequest:
    """Request to a TEE agent"""
    request_id: str
    agent_id: str
    action: str
    parameters: Dict[str, Any]
    source_project: str
    timestamp: str
    callback_channel: Optional[str] = None
    
    def to_json(self) -> str:
        return json.dumps(asdict(self))


@dataclass
class TEEAgentResponse:
    """Response from a TEE agent"""
    request_id: str
    agent_id: str
    status: str  # 'success', 'error', 'in_progress'
    result: Dict[str, Any]
    timestamp: str
    error: Optional[str] = None
    
    @classmethod
    def from_json(cls, json_str: str) -> 'TEEAgentResponse':
        data = json.loads(json_str)
        return cls(**data)


class TEEAgentTool:
    """
    Tool for communicating with TEE agents via Redis message bus.
    
    This tool provides methods to:
    - Invoke TEE agents for data processing
    - Request DP-protected releases
    - Get agent status updates
    - Receive results via callback
    """
    
    # Redis channels
    REQUEST_CHANNEL = "tee:crews"
    RESPONSE_CHANNEL = "retail_media:responses"
    STATUS_CHANNEL = "tee:agents"
    
    # Available TEE agents
    AVAILABLE_AGENTS = {
        "data_connector": {
            "name": "Data Connector Agent",
            "actions": ["discover_sources", "validate_connection", "get_schema", "count_records"]
        },
        "schema_mapper": {
            "name": "Schema Mapper Agent",
            "actions": ["map_schema", "resolve_identity", "get_canonical_id"]
        },
        "metric_engineer": {
            "name": "Metric Engineer Agent",
            "actions": ["compute_metric", "compute_all_metrics", "prepare_for_dp"]
        },
        "dp_steward": {
            "name": "DP Steward Agent",
            "actions": ["release_metric", "release_batch", "get_budget_status"]
        },
        "spend_optimizer": {
            "name": "Spend Optimizer Agent",
            "actions": ["optimize_spend", "get_recommendation_summary"]
        },
        "audit_evidence": {
            "name": "Audit Evidence Agent",
            "actions": ["log_action", "create_evidence_pack", "verify_audit_trail"]
        },
        "proof_agent": {
            "name": "Proof Agent",
            "actions": ["generate_proof", "verify_proof", "generate_range_proof"]
        }
    }
    
    def __init__(
        self,
        redis_host: str = "localhost",
        redis_port: int = 6379,
        project_id: str = "retail_media"
    ):
        self.project_id = project_id
        self.redis_client = redis.Redis(
            host=redis_host,
            port=redis_port,
            decode_responses=True
        )
        self.pubsub = self.redis_client.pubsub()
        self._callbacks: Dict[str, Callable] = {}
        self._pending_requests: Dict[str, TEEAgentRequest] = {}
        
        # Subscribe to response channel
        self.pubsub.subscribe(self.RESPONSE_CHANNEL)
        
        logger.info(f"TEEAgentTool initialized for project: {project_id}")
    
    def invoke_agent(
        self,
        agent_id: str,
        action: str,
        parameters: Dict[str, Any],
        callback: Optional[Callable[[TEEAgentResponse], None]] = None,
        timeout: float = 30.0
    ) -> TEEAgentResponse:
        """
        Invoke a TEE agent to perform an action.
        
        Args:
            agent_id: ID of the TEE agent to invoke
            action: Action to perform
            parameters: Parameters for the action
            callback: Optional callback for async response
            timeout: Timeout in seconds for sync response
            
        Returns:
            TEEAgentResponse with result or status
        """
        if agent_id not in self.AVAILABLE_AGENTS:
            return TEEAgentResponse(
                request_id="",
                agent_id=agent_id,
                status="error",
                result={},
                timestamp=datetime.now().isoformat(),
                error=f"Unknown agent: {agent_id}"
            )
        
        agent_info = self.AVAILABLE_AGENTS[agent_id]
        if action not in agent_info["actions"]:
            return TEEAgentResponse(
                request_id="",
                agent_id=agent_id,
                status="error",
                result={},
                timestamp=datetime.now().isoformat(),
                error=f"Unknown action for {agent_id}: {action}"
            )
        
        # Create request
        request_id = str(uuid.uuid4())
        request = TEEAgentRequest(
            request_id=request_id,
            agent_id=agent_id,
            action=action,
            parameters=parameters,
            source_project=self.project_id,
            timestamp=datetime.now().isoformat(),
            callback_channel=self.RESPONSE_CHANNEL if callback else None
        )
        
        # Store request and callback
        self._pending_requests[request_id] = request
        if callback:
            self._callbacks[request_id] = callback
        
        # Publish request
        self.redis_client.publish(self.REQUEST_CHANNEL, request.to_json())
        logger.info(f"Sent request to TEE agent {agent_id}: {action}")
        
        # For sync mode, wait for response
        if not callback:
            return self._wait_for_response(request_id, timeout)
        
        # For async mode, return pending status
        return TEEAgentResponse(
            request_id=request_id,
            agent_id=agent_id,
            status="pending",
            result={},
            timestamp=datetime.now().isoformat()
        )
    
    def _wait_for_response(self, request_id: str, timeout: float) -> TEEAgentResponse:
        """Wait for a response from TEE agent"""
        import time
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            message = self.pubsub.get_message(timeout=0.1)
            if message and message["type"] == "message":
                try:
                    response = TEEAgentResponse.from_json(message["data"])
                    if response.request_id == request_id:
                        del self._pending_requests[request_id]
                        return response
                except Exception as e:
                    logger.error(f"Failed to parse response: {e}")
            
            time.sleep(0.1)
        
        # Timeout - return error
        return TEEAgentResponse(
            request_id=request_id,
            agent_id=self._pending_requests.get(request_id, TEEAgentRequest("", "", "", {}, "", "")).agent_id,
            status="error",
            result={},
            timestamp=datetime.now().isoformat(),
            error="Request timed out"
        )
    
    def discover_data_sources(self, config: Dict[str, Any]) -> TEEAgentResponse:
        """Discover data sources using the Data Connector agent"""
        return self.invoke_agent(
            agent_id="data_connector",
            action="discover_sources",
            parameters={"config": config}
        )
    
    def validate_connection(self, source_id: str) -> TEEAgentResponse:
        """Validate a data source connection"""
        return self.invoke_agent(
            agent_id="data_connector",
            action="validate_connection",
            parameters={"source_id": source_id}
        )
    
    def map_schema(self, source_id: str, source_schema: Dict[str, Any]) -> TEEAgentResponse:
        """Map a source schema to canonical format"""
        return self.invoke_agent(
            agent_id="schema_mapper",
            action="map_schema",
            parameters={"source_id": source_id, "source_schema": source_schema}
        )
    
    def compute_metrics(
        self,
        data: Dict[str, List[float]],
        grain_key: str
    ) -> TEEAgentResponse:
        """Compute metrics using the Metric Engineer agent"""
        return self.invoke_agent(
            agent_id="metric_engineer",
            action="compute_all_metrics",
            parameters={"data": data, "grain_key": grain_key}
        )
    
    def release_with_dp(
        self,
        metrics: Dict[str, Dict[str, Any]],
        requester_id: str
    ) -> TEEAgentResponse:
        """Release metrics with differential privacy protection"""
        return self.invoke_agent(
            agent_id="dp_steward",
            action="release_batch",
            parameters={"metrics": metrics, "requester_id": requester_id}
        )
    
    def optimize_spend(
        self,
        dp_metrics: Dict[str, Dict[str, Any]],
        total_budget: float,
        constraints: Dict[str, Any]
    ) -> TEEAgentResponse:
        """Optimize spend allocation using DP-protected metrics"""
        return self.invoke_agent(
            agent_id="spend_optimizer",
            action="optimize_spend",
            parameters={
                "dp_metrics": dp_metrics,
                "total_budget": total_budget,
                "constraints": constraints
            }
        )
    
    def get_privacy_budget(self) -> TEEAgentResponse:
        """Get current privacy budget status"""
        return self.invoke_agent(
            agent_id="dp_steward",
            action="get_budget_status",
            parameters={}
        )
    
    def create_evidence_pack(
        self,
        optimization_id: str,
        dp_receipts: List[Dict[str, Any]],
        metrics_summary: Dict[str, Any]
    ) -> TEEAgentResponse:
        """Create an evidence pack for audit"""
        return self.invoke_agent(
            agent_id="audit_evidence",
            action="create_evidence_pack",
            parameters={
                "optimization_id": optimization_id,
                "dp_receipts": dp_receipts,
                "metrics_summary": metrics_summary
            }
        )
    
    def get_agent_status(self, agent_id: str) -> Dict[str, Any]:
        """Get status of a TEE agent"""
        # Get from status stream
        stream_key = f"{self.STATUS_CHANNEL}:stream"
        messages = self.redis_client.xrevrange(stream_key, count=10)
        
        for msg_id, data in messages:
            try:
                event = json.loads(data.get("event", "{}"))
                if event.get("source_agent") == agent_id:
                    return {
                        "agent_id": agent_id,
                        "status": "active",
                        "last_event": event
                    }
            except:
                pass
        
        return {
            "agent_id": agent_id,
            "status": "unknown",
            "last_event": None
        }
    
    def list_available_agents(self) -> List[Dict[str, Any]]:
        """List all available TEE agents"""
        return [
            {
                "id": agent_id,
                "name": info["name"],
                "actions": info["actions"]
            }
            for agent_id, info in self.AVAILABLE_AGENTS.items()
        ]
    
    def close(self):
        """Close the Redis connection"""
        self.pubsub.close()
        self.redis_client.close()


# Singleton instance
_tee_tool: Optional[TEEAgentTool] = None


def get_tee_agent_tool(
    redis_host: str = "localhost",
    redis_port: int = 6379
) -> TEEAgentTool:
    """Get or create the singleton TEE agent tool"""
    global _tee_tool
    if _tee_tool is None:
        _tee_tool = TEEAgentTool(redis_host=redis_host, redis_port=redis_port)
    return _tee_tool
