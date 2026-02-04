"""
PDM Distributed Tracing

OpenTelemetry-compatible distributed tracing.
"""

import logging
import time
from contextlib import contextmanager
from typing import Optional, Dict, Any, Callable
from functools import wraps
import uuid

logger = logging.getLogger(__name__)

# Try to import OpenTelemetry
OTEL_AVAILABLE = False
try:
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.exporter.jaeger.thrift import JaegerExporter
    from opentelemetry.trace import Status, StatusCode
    OTEL_AVAILABLE = True
except ImportError:
    logger.debug("OpenTelemetry not installed. Using no-op tracing.")


# =============================================================================
# No-op Tracing Fallback
# =============================================================================

class NoOpSpan:
    """No-op span for when tracing is disabled"""
    
    def __init__(self, name: str = ""):
        self.name = name
        self.attributes: Dict[str, Any] = {}
        self.start_time = time.time()
        self.span_id = str(uuid.uuid4())[:16]
    
    def set_attribute(self, key: str, value: Any):
        self.attributes[key] = value
    
    def set_status(self, status, description: str = None):
        pass
    
    def record_exception(self, exception: Exception):
        pass
    
    def add_event(self, name: str, attributes: Dict[str, Any] = None):
        pass
    
    def end(self):
        pass
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            self.record_exception(exc_val)
        self.end()
        return False


class NoOpTracer:
    """No-op tracer for when tracing is disabled"""
    
    def start_span(self, name: str, **kwargs) -> NoOpSpan:
        return NoOpSpan(name)
    
    def start_as_current_span(self, name: str, **kwargs):
        return NoOpSpan(name)


class NoOpTracerProvider:
    """No-op tracer provider"""
    
    def get_tracer(self, name: str, version: str = None) -> NoOpTracer:
        return NoOpTracer()


# Global tracer instance
_tracer_provider = None
_tracer = None


def setup_tracing(
    service_name: str = "pdm",
    jaeger_host: str = "localhost",
    jaeger_port: int = 6831,
    enabled: bool = True,
) -> bool:
    """
    Set up distributed tracing.
    
    Args:
        service_name: Name of the service for tracing
        jaeger_host: Jaeger agent host
        jaeger_port: Jaeger agent UDP port
        enabled: Whether tracing is enabled
    
    Returns:
        True if tracing was set up successfully
    """
    global _tracer_provider, _tracer
    
    if not enabled:
        _tracer_provider = NoOpTracerProvider()
        _tracer = _tracer_provider.get_tracer(service_name)
        logger.info("Tracing disabled, using no-op tracer")
        return True
    
    if not OTEL_AVAILABLE:
        _tracer_provider = NoOpTracerProvider()
        _tracer = _tracer_provider.get_tracer(service_name)
        logger.warning("OpenTelemetry not available, using no-op tracer")
        return False
    
    try:
        # Create resource
        resource = Resource.create({
            "service.name": service_name,
            "service.version": "1.0.0",
        })
        
        # Create tracer provider
        _tracer_provider = TracerProvider(resource=resource)
        
        # Create Jaeger exporter
        jaeger_exporter = JaegerExporter(
            agent_host_name=jaeger_host,
            agent_port=jaeger_port,
        )
        
        # Add span processor
        _tracer_provider.add_span_processor(
            BatchSpanProcessor(jaeger_exporter)
        )
        
        # Set as global tracer provider
        trace.set_tracer_provider(_tracer_provider)
        
        # Get tracer
        _tracer = trace.get_tracer(service_name)
        
        logger.info(f"Tracing configured with Jaeger at {jaeger_host}:{jaeger_port}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to set up tracing: {e}")
        _tracer_provider = NoOpTracerProvider()
        _tracer = _tracer_provider.get_tracer(service_name)
        return False


def get_tracer():
    """Get the global tracer instance"""
    global _tracer
    if _tracer is None:
        setup_tracing(enabled=False)
    return _tracer


@contextmanager
def trace_span(
    name: str,
    attributes: Dict[str, Any] = None,
    kind: str = "internal",
):
    """
    Context manager for creating trace spans.
    
    Args:
        name: Span name
        attributes: Span attributes
        kind: Span kind (internal, server, client, producer, consumer)
    
    Usage:
        with trace_span("process_telemetry", {"asset_id": "RTU_001"}):
            # do work
    """
    tracer = get_tracer()
    
    if OTEL_AVAILABLE and not isinstance(tracer, NoOpTracer):
        from opentelemetry.trace import SpanKind
        kind_map = {
            "internal": SpanKind.INTERNAL,
            "server": SpanKind.SERVER,
            "client": SpanKind.CLIENT,
            "producer": SpanKind.PRODUCER,
            "consumer": SpanKind.CONSUMER,
        }
        span_kind = kind_map.get(kind, SpanKind.INTERNAL)
        
        with tracer.start_as_current_span(name, kind=span_kind) as span:
            if attributes:
                for key, value in attributes.items():
                    span.set_attribute(key, value)
            try:
                yield span
            except Exception as e:
                span.record_exception(e)
                span.set_status(Status(StatusCode.ERROR, str(e)))
                raise
    else:
        span = NoOpSpan(name)
        if attributes:
            for key, value in attributes.items():
                span.set_attribute(key, value)
        try:
            yield span
        finally:
            span.end()


def traced(
    name: str = None,
    attributes: Dict[str, Any] = None,
    kind: str = "internal",
):
    """
    Decorator to trace function execution.
    
    Args:
        name: Span name (defaults to function name)
        attributes: Additional span attributes
        kind: Span kind
    
    Usage:
        @traced("process_telemetry")
        def process_telemetry(asset_id: str, data: dict):
            pass
    """
    def decorator(func: Callable):
        span_name = name or func.__name__
        
        @wraps(func)
        def wrapper(*args, **kwargs):
            span_attributes = dict(attributes or {})
            span_attributes["function"] = func.__name__
            span_attributes["module"] = func.__module__
            
            with trace_span(span_name, span_attributes, kind) as span:
                try:
                    result = func(*args, **kwargs)
                    return result
                except Exception as e:
                    span.set_attribute("error", True)
                    span.set_attribute("error.message", str(e))
                    raise
        
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            span_attributes = dict(attributes or {})
            span_attributes["function"] = func.__name__
            span_attributes["module"] = func.__module__
            
            with trace_span(span_name, span_attributes, kind) as span:
                try:
                    result = await func(*args, **kwargs)
                    return result
                except Exception as e:
                    span.set_attribute("error", True)
                    span.set_attribute("error.message", str(e))
                    raise
        
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return wrapper
    
    return decorator


class TracingMiddleware:
    """ASGI middleware for automatic request tracing"""
    
    def __init__(self, app, service_name: str = "pdm-api"):
        self.app = app
        self.service_name = service_name
    
    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        
        tracer = get_tracer()
        
        # Extract trace context from headers
        span_name = f"{scope.get('method', 'HTTP')} {scope.get('path', '/')}"
        
        with trace_span(span_name, kind="server") as span:
            span.set_attribute("http.method", scope.get("method", ""))
            span.set_attribute("http.url", scope.get("path", ""))
            span.set_attribute("http.scheme", scope.get("scheme", "http"))
            
            client = scope.get("client")
            if client:
                span.set_attribute("net.peer.ip", client[0])
                span.set_attribute("net.peer.port", client[1])
            
            status_code = 500
            
            async def send_wrapper(message):
                nonlocal status_code
                if message["type"] == "http.response.start":
                    status_code = message.get("status", 500)
                    span.set_attribute("http.status_code", status_code)
                    if status_code >= 400:
                        span.set_attribute("error", True)
                await send(message)
            
            try:
                await self.app(scope, receive, send_wrapper)
            except Exception as e:
                span.record_exception(e)
                span.set_attribute("error", True)
                raise
