"""
OpenAI Client Wrapper for Scenario Advisory

Provides a clean interface for OpenAI API with function calling support.
"""

import os
import json
import logging
from typing import Dict, List, Optional, Any, Generator, Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Check for OpenAI availability
try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    logger.warning("OpenAI package not installed. Install with: pip install openai")


class MessageRole(Enum):
    """Chat message roles"""
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    FUNCTION = "function"
    TOOL = "tool"


@dataclass
class ChatMessage:
    """A chat message in the conversation"""
    role: MessageRole
    content: str
    name: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None
    tool_call_id: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to OpenAI message format"""
        msg = {
            "role": self.role.value,
            "content": self.content,
        }
        if self.name:
            msg["name"] = self.name
        if self.tool_call_id:
            msg["tool_call_id"] = self.tool_call_id
        return msg
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ChatMessage":
        """Create from dictionary"""
        return cls(
            role=MessageRole(data.get("role", "user")),
            content=data.get("content", ""),
            name=data.get("name"),
            tool_calls=data.get("tool_calls"),
            tool_call_id=data.get("tool_call_id"),
        )


@dataclass
class FunctionDefinition:
    """OpenAI function definition for tool calling"""
    name: str
    description: str
    parameters: Dict[str, Any]
    handler: Optional[Callable] = None
    
    def to_tool_dict(self) -> Dict[str, Any]:
        """Convert to OpenAI tool format"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            }
        }


class OpenAIClient:
    """
    OpenAI API client with function calling support.
    
    Handles:
    - Chat completions with streaming
    - Function/tool calling
    - Conversation history management
    - Error handling and retries
    """
    
    DEFAULT_MODEL = "gpt-4-turbo-preview"
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ):
        self.model = model or os.getenv("OPENAI_MODEL", self.DEFAULT_MODEL)
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.functions: Dict[str, FunctionDefinition] = {}
        
        if not OPENAI_AVAILABLE:
            self.client = None
            logger.warning("OpenAI client not initialized - package not available")
            return
        
        api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not api_key:
            self.client = None
            logger.warning("OpenAI API key not found. Set OPENAI_API_KEY environment variable.")
            return
        
        self.client = OpenAI(api_key=api_key)
        logger.info(f"OpenAI client initialized with model: {self.model}")
    
    @property
    def is_available(self) -> bool:
        """Check if client is properly configured"""
        return self.client is not None
    
    def register_function(self, func_def: FunctionDefinition):
        """Register a function for tool calling"""
        self.functions[func_def.name] = func_def
        logger.debug(f"Registered function: {func_def.name}")
    
    def get_tools(self) -> List[Dict[str, Any]]:
        """Get all registered tools in OpenAI format"""
        return [f.to_tool_dict() for f in self.functions.values()]
    
    def chat(
        self,
        messages: List[ChatMessage],
        use_tools: bool = True,
        stream: bool = False,
    ) -> Dict[str, Any]:
        """
        Send a chat completion request.
        
        Args:
            messages: List of chat messages
            use_tools: Whether to include registered tools
            stream: Whether to stream the response
            
        Returns:
            Response dict with 'content', 'tool_calls', 'usage'
        """
        if not self.is_available:
            return self._mock_response(messages)
        
        # Build request
        request_messages = [m.to_dict() for m in messages]
        
        kwargs = {
            "model": self.model,
            "messages": request_messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        
        if use_tools and self.functions:
            kwargs["tools"] = self.get_tools()
            kwargs["tool_choice"] = "auto"
        
        try:
            if stream:
                return self._stream_chat(kwargs)
            else:
                response = self.client.chat.completions.create(**kwargs)
                return self._parse_response(response)
        except Exception as e:
            logger.error(f"OpenAI API error: {e}")
            return {
                "content": f"I apologize, but I encountered an error: {str(e)}",
                "tool_calls": None,
                "usage": None,
                "error": str(e),
            }
    
    def _parse_response(self, response) -> Dict[str, Any]:
        """Parse OpenAI response"""
        choice = response.choices[0]
        message = choice.message
        
        result = {
            "content": message.content or "",
            "tool_calls": None,
            "usage": {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            } if response.usage else None,
            "finish_reason": choice.finish_reason,
        }
        
        if message.tool_calls:
            result["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": tc.type,
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    }
                }
                for tc in message.tool_calls
            ]
        
        return result
    
    def _stream_chat(self, kwargs) -> Generator[Dict[str, Any], None, None]:
        """Stream chat response"""
        kwargs["stream"] = True
        
        try:
            stream = self.client.chat.completions.create(**kwargs)
            
            full_content = ""
            tool_calls = []
            
            for chunk in stream:
                delta = chunk.choices[0].delta
                
                if delta.content:
                    full_content += delta.content
                    yield {
                        "type": "content",
                        "content": delta.content,
                        "done": False,
                    }
                
                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        if tc.index >= len(tool_calls):
                            tool_calls.append({
                                "id": tc.id,
                                "type": "function",
                                "function": {"name": "", "arguments": ""}
                            })
                        if tc.function.name:
                            tool_calls[tc.index]["function"]["name"] = tc.function.name
                        if tc.function.arguments:
                            tool_calls[tc.index]["function"]["arguments"] += tc.function.arguments
            
            # Final result
            yield {
                "type": "done",
                "content": full_content,
                "tool_calls": tool_calls if tool_calls else None,
                "done": True,
            }
            
        except Exception as e:
            logger.error(f"Streaming error: {e}")
            yield {
                "type": "error",
                "content": str(e),
                "done": True,
            }
    
    def execute_tool_call(self, tool_call: Dict[str, Any]) -> str:
        """Execute a tool call and return the result"""
        func_name = tool_call["function"]["name"]
        
        if func_name not in self.functions:
            return json.dumps({"error": f"Unknown function: {func_name}"})
        
        func_def = self.functions[func_name]
        
        if not func_def.handler:
            return json.dumps({"error": f"No handler for function: {func_name}"})
        
        try:
            args = json.loads(tool_call["function"]["arguments"])
            result = func_def.handler(**args)
            return json.dumps(result, default=str)
        except Exception as e:
            logger.error(f"Tool execution error for {func_name}: {e}")
            return json.dumps({"error": str(e)})
    
    def _mock_response(self, messages: List[ChatMessage]) -> Dict[str, Any]:
        """Generate mock response when OpenAI is not available"""
        last_user_msg = ""
        for msg in reversed(messages):
            if msg.role == MessageRole.USER:
                last_user_msg = msg.content.lower()
                break
        
        # Basic keyword matching for mock responses
        if "scenario" in last_user_msg or "recommend" in last_user_msg:
            content = """Based on your query, I can help you explore different scenarios. 
            
**For RMN (Retail Media):**
- Grow Revenue for Brand - maximize incremental sales
- Maintain Revenue - stability mode with risk management
- Maximize ROAS - efficiency optimization

**For Demand & Procurement:**
- Baseline - current inventory policy evaluation
- Conservative - higher safety stock for risk mitigation
- Demand sensitivity - stress testing demand variations

Which ecosystem and scenario would you like to explore?"""
        
        elif "stockout" in last_user_msg or "risk" in last_user_msg:
            content = """I can analyze stockout risk for your inventory. 

Key factors I consider:
- Current inventory levels vs reorder point
- Demand variability and forecast accuracy
- Lead time uncertainty
- Service level targets

To provide a specific assessment, please specify which SKU or product category you'd like me to analyze."""
        
        elif "forecast" in last_user_msg or "demand" in last_user_msg:
            content = """I can help with demand forecasting analysis.

Our forecasting approach includes:
- Historical demand patterns
- Seasonality adjustments
- Promotional impact
- Endogenous factors (basket dynamics, penetration)

Would you like me to generate a forecast for a specific SKU or review the methodology?"""
        
        else:
            content = """I'm your Scenario Advisory assistant. I can help you with:

**RMN (Retail Media Network):**
- Channel optimization and budget allocation
- ROAS and incrementality analysis
- Scenario recommendations

**Demand & Procurement:**
- Demand forecasting
- Inventory optimization (reorder points, safety stock)
- Stockout risk assessment
- Procurement planning

What would you like to explore?"""
        
        return {
            "content": content,
            "tool_calls": None,
            "usage": None,
            "mock": True,
        }
