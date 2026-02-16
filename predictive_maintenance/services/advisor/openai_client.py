"""OpenAI client wrapper with availability detection and tool-calling support.

Provides a unified interface for chat completions with function/tool calling,
gracefully degrading when the OpenAI package or API key is unavailable.
"""

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

try:
    import openai as _openai_mod  # type: ignore
except Exception:
    _openai_mod = None


@dataclass
class ToolDefinition:
    """OpenAI function-calling tool definition."""
    name: str
    description: str
    parameters: Dict[str, Any]
    handler: Callable


@dataclass
class ChatResponse:
    """Wrapper around an OpenAI chat completion response."""
    content: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None
    finish_reason: Optional[str] = None
    model: Optional[str] = None
    raw: Any = None


class OpenAIClient:
    """OpenAI chat completion client with tool-calling support.

    Parameters
    ----------
    model : str
        Chat model name.
    temperature : float
        Sampling temperature.
    max_tokens : int
        Maximum response tokens.
    api_key : str, optional
        OpenAI API key. Falls back to OPENAI_API_KEY env var.
    """

    def __init__(
        self,
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        api_key: Optional[str] = None,
    ):
        env_api_key = os.environ.get("OPENAI_API_KEY")
        if not env_api_key:
            for k, v in os.environ.items():
                if k.lower() == "openai_api_key":
                    env_api_key = v
                    break
        cfg_api_key = None
        try:
            from predictive_maintenance.config import settings
            cfg_api_key = settings.openai.api_key
        except Exception:
            cfg_api_key = None
        self.model = model or os.environ.get("OPENAI_MODEL", "gpt-4-turbo-preview")
        self.temperature = temperature
        self.max_tokens = max_tokens
        self._api_key = api_key or env_api_key or cfg_api_key
        self._client = None
        self.functions: Dict[str, ToolDefinition] = {}
        self._init_client()

    def _init_client(self):
        """Initialize the OpenAI client if possible."""
        if _openai_mod is None or not self._api_key:
            return
        try:
            self._client = _openai_mod.OpenAI(api_key=self._api_key)
        except Exception as exc:
            logger.warning("Failed to initialize OpenAI client: %s", exc)
            self._client = None

    @property
    def is_available(self) -> bool:
        """True when both the openai package is installed and a valid API key is configured."""
        return self._client is not None and bool(self._api_key)

    def register_tool(self, tool: ToolDefinition):
        """Register a tool for function calling."""
        self.functions[tool.name] = tool

    def _build_tools_payload(self) -> List[Dict[str, Any]]:
        """Build OpenAI tools parameter from registered tools."""
        tools = []
        for tool in self.functions.values():
            tools.append({
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                },
            })
        return tools

    def chat(
        self,
        messages: List[Dict[str, Any]],
        use_tools: bool = True,
    ) -> ChatResponse:
        """Send a chat completion request.

        Parameters
        ----------
        messages : list of dict
            OpenAI-format messages (role, content, etc.).
        use_tools : bool
            Whether to include registered tools in the request.

        Returns
        -------
        ChatResponse
            Parsed response with content and/or tool_calls.
        """
        if not self.is_available:
            return ChatResponse(content=None, finish_reason="unavailable")

        kwargs: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }

        if use_tools and self.functions:
            kwargs["tools"] = self._build_tools_payload()
            kwargs["tool_choice"] = "auto"

        try:
            response = self._client.chat.completions.create(**kwargs)
            choice = response.choices[0]
            message = choice.message

            tool_calls = None
            if hasattr(message, "tool_calls") and message.tool_calls:
                tool_calls = []
                for tc in message.tool_calls:
                    tool_calls.append({
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    })

            return ChatResponse(
                content=message.content,
                tool_calls=tool_calls,
                finish_reason=choice.finish_reason,
                model=response.model,
                raw=response,
            )
        except Exception as exc:
            logger.error("OpenAI chat completion failed: %s", exc)
            return ChatResponse(content=None, finish_reason="error")

    def chat_stream(
        self,
        messages: List[Dict[str, Any]],
        use_tools: bool = False,
    ):
        """Yield content chunks from a streaming chat completion.

        Yields str tokens as they arrive.  Does NOT support tool-calling
        in streaming mode (OpenAI tool_calls in streamed responses require
        accumulation logic — use the non-streaming ``chat()`` for that).
        """
        if not self.is_available:
            yield "[Advisor unavailable — OpenAI API key not configured]"
            return

        kwargs: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "stream": True,
        }

        try:
            response = self._client.chat.completions.create(**kwargs)
            for chunk in response:
                delta = chunk.choices[0].delta if chunk.choices else None
                if delta and delta.content:
                    yield delta.content
        except Exception as exc:
            logger.error("OpenAI streaming failed: %s", exc)
            yield f"\n[Streaming error: {exc}]"

    def execute_tool_call(self, tool_call: Dict[str, Any]) -> Any:
        """Execute a single tool call and return the result."""
        func_name = tool_call["function"]["name"]
        args_str = tool_call["function"]["arguments"]

        tool = self.functions.get(func_name)
        if not tool:
            return {"error": f"Unknown tool: {func_name}"}

        try:
            args = json.loads(args_str) if args_str else {}
            result = tool.handler(**args)
            return result
        except Exception as exc:
            logger.error("Tool execution failed for %s: %s", func_name, exc)
            return {"error": str(exc)}
