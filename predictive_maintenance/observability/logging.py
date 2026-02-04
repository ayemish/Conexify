"""
PDM Structured Logging

JSON-formatted structured logging with context propagation.
"""

import logging
import json
import sys
import traceback
from datetime import datetime
from typing import Any, Dict, Optional
from contextvars import ContextVar
import uuid

# Context variables for request tracing
_trace_id: ContextVar[Optional[str]] = ContextVar("trace_id", default=None)
_span_id: ContextVar[Optional[str]] = ContextVar("span_id", default=None)
_extra_context: ContextVar[Dict[str, Any]] = ContextVar("extra_context", default={})


def get_trace_id() -> Optional[str]:
    return _trace_id.get()


def set_trace_id(trace_id: str):
    _trace_id.set(trace_id)


def generate_trace_id() -> str:
    return str(uuid.uuid4())


def set_context(**kwargs):
    """Set additional context for logging"""
    current = _extra_context.get()
    _extra_context.set({**current, **kwargs})


def clear_context():
    """Clear logging context"""
    _extra_context.set({})


class JSONFormatter(logging.Formatter):
    """JSON log formatter for structured logging"""
    
    def __init__(self, include_trace: bool = True):
        super().__init__()
        self.include_trace = include_trace
    
    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        
        # Add trace context
        if self.include_trace:
            trace_id = _trace_id.get()
            if trace_id:
                log_data["trace_id"] = trace_id
            
            span_id = _span_id.get()
            if span_id:
                log_data["span_id"] = span_id
        
        # Add extra context
        extra = _extra_context.get()
        if extra:
            log_data["context"] = extra
        
        # Add location info
        log_data["location"] = {
            "file": record.filename,
            "line": record.lineno,
            "function": record.funcName,
        }
        
        # Add exception info
        if record.exc_info:
            log_data["exception"] = {
                "type": record.exc_info[0].__name__ if record.exc_info[0] else None,
                "message": str(record.exc_info[1]) if record.exc_info[1] else None,
                "traceback": traceback.format_exception(*record.exc_info) if record.exc_info[0] else None,
            }
        
        # Add any extra attributes from the record
        for key, value in record.__dict__.items():
            if key not in (
                "name", "msg", "args", "created", "filename", "funcName",
                "levelname", "levelno", "lineno", "module", "msecs",
                "pathname", "process", "processName", "relativeCreated",
                "stack_info", "exc_info", "exc_text", "thread", "threadName",
                "message", "asctime"
            ):
                if not key.startswith("_"):
                    log_data[key] = value
        
        return json.dumps(log_data, default=str)


class TextFormatter(logging.Formatter):
    """Human-readable text formatter"""
    
    def __init__(self, include_trace: bool = True):
        super().__init__()
        self.include_trace = include_trace
    
    def format(self, record: logging.LogRecord) -> str:
        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        
        parts = [
            f"[{timestamp}]",
            f"[{record.levelname:8}]",
            f"[{record.name}]",
        ]
        
        if self.include_trace:
            trace_id = _trace_id.get()
            if trace_id:
                parts.append(f"[{trace_id[:8]}]")
        
        parts.append(record.getMessage())
        
        message = " ".join(parts)
        
        if record.exc_info:
            message += "\n" + "".join(traceback.format_exception(*record.exc_info))
        
        return message


class StructuredLogger:
    """Wrapper for structured logging with context"""
    
    def __init__(self, name: str):
        self.logger = logging.getLogger(name)
    
    def _log(self, level: int, msg: str, **kwargs):
        extra = kwargs.pop("extra", {})
        extra.update(kwargs)
        self.logger.log(level, msg, extra=extra)
    
    def debug(self, msg: str, **kwargs):
        self._log(logging.DEBUG, msg, **kwargs)
    
    def info(self, msg: str, **kwargs):
        self._log(logging.INFO, msg, **kwargs)
    
    def warning(self, msg: str, **kwargs):
        self._log(logging.WARNING, msg, **kwargs)
    
    def error(self, msg: str, exc_info: bool = False, **kwargs):
        self.logger.error(msg, exc_info=exc_info, extra=kwargs)
    
    def critical(self, msg: str, exc_info: bool = False, **kwargs):
        self.logger.critical(msg, exc_info=exc_info, extra=kwargs)
    
    def with_context(self, **kwargs) -> "StructuredLogger":
        """Return logger with additional context set"""
        set_context(**kwargs)
        return self


def setup_logging(
    level: str = "INFO",
    format: str = "json",
    include_trace: bool = True,
):
    """
    Configure logging for the PDM system.
    
    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        format: Output format ("json" or "text")
        include_trace: Include trace_id in logs
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper()))
    
    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Create console handler
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(getattr(logging, level.upper()))
    
    # Set formatter
    if format.lower() == "json":
        formatter = JSONFormatter(include_trace=include_trace)
    else:
        formatter = TextFormatter(include_trace=include_trace)
    
    handler.setFormatter(formatter)
    root_logger.addHandler(handler)
    
    # Configure library loggers
    logging.getLogger("uvicorn").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy").setLevel(logging.WARNING)
    logging.getLogger("redis").setLevel(logging.WARNING)
    
    return root_logger


def get_logger(name: str) -> StructuredLogger:
    """Get a structured logger instance"""
    return StructuredLogger(name)


# Middleware for request tracing
class LoggingMiddleware:
    """ASGI middleware for request logging and trace propagation"""
    
    def __init__(self, app):
        self.app = app
    
    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        
        # Generate or extract trace_id
        trace_id = None
        for header_name, header_value in scope.get("headers", []):
            if header_name.lower() == b"x-trace-id":
                trace_id = header_value.decode()
                break
        
        if not trace_id:
            trace_id = generate_trace_id()
        
        set_trace_id(trace_id)
        
        # Set request context
        set_context(
            method=scope.get("method", ""),
            path=scope.get("path", ""),
            client=scope.get("client", ("", 0))[0],
        )
        
        logger = get_logger("pdm.http")
        logger.info(
            f"{scope.get('method')} {scope.get('path')}",
            event="request_start"
        )
        
        import time
        start_time = time.time()
        
        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                duration = (time.time() - start_time) * 1000
                logger.info(
                    f"{scope.get('method')} {scope.get('path')} -> {message.get('status')}",
                    event="request_end",
                    status_code=message.get("status"),
                    duration_ms=round(duration, 2)
                )
            await send(message)
        
        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            clear_context()
