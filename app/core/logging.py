"""
Enhanced Structured Logging with Security Sanitization

This module provides comprehensive logging capabilities with automatic
sanitization of sensitive information and integration with the alert system.
"""

import json
import logging
import re
import sys
import functools
import inspect
import traceback
from datetime import datetime
from typing import Any, Dict, List, Optional, Union, Callable
from enum import Enum

import structlog
from structlog.typing import EventDict, Processor

from app.core.alerts import alert_manager, AlertCategory, AlertSeverity


class LogLevel(Enum):
    """Log levels for the enhanced logging system."""
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


def custom_formatter(logger: Any, name: str, event_dict: EventDict) -> str:
    """
    Custom formatter that outputs logs in the desired format:
    2025-08-02 17:32:17 [info ] line_number=123 path=/api/workflow/approval function=send_message error_detail=Some error
    """
    # Extract timestamp
    timestamp = event_dict.get('timestamp', datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'))
    
    # Extract log level
    level = event_dict.get('level', 'info')
    level_str = f"[{level:<5}]"
    
    # Extract key information
    line_number = event_dict.get('line_number', 'N/A')
    path = event_dict.get('path', event_dict.get('file_name', 'N/A'))
    function = event_dict.get('function_name', 'N/A')
    error_detail = event_dict.get('error_message', event_dict.get('error_detail', ''))
    
    # Build the log message
    parts = [f"{timestamp} {level_str}"]
    
    # Add line number
    if line_number != 'N/A':
        parts.append(f"line_number={line_number}")
    
    # Add path (for API endpoints, use the route path; otherwise use file path)
    if path != 'N/A':
        parts.append(f"path={path}")
    
    # Add function name
    if function != 'N/A':
        parts.append(f"function={function}")
    
    # Add error detail if present
    if error_detail:
        parts.append(f"error_detail={error_detail}")
    
    # Add the main event message
    event = event_dict.get('event', '')
    if event:
        parts.append(event)
    
    # Add additional context for API endpoints
    if event_dict.get('endpoint_type') == 'api':
        method = event_dict.get('method', '')
        url = event_dict.get('url', '')
        if method and url:
            parts.append(f"method={method} url={url}")
    
    # Add execution time if present
    execution_time = event_dict.get('execution_time_ms')
    if execution_time:
        parts.append(f"execution_time_ms={execution_time:.2f}")
    
    return " ".join(parts)


class SecuritySanitizer:
    """Sanitizes sensitive information from log messages and data."""
    
    # Patterns for sensitive information
    SENSITIVE_PATTERNS = [
        # API tokens and keys
        (r'(?i)(token|key|secret|password|auth)[\s]*[=:]\s*["\']?([a-zA-Z0-9+/=]{10,})["\']?', 'REDACTED'),
        (r'(?i)bearer\s+([a-zA-Z0-9+/=]{10,})', 'bearer REDACTED'),
        (r'(?i)authorization:\s*([a-zA-Z0-9+/=\s]{10,})', 'authorization: REDACTED'),
        
        # Database connection strings
        (r'(?i)://[^:]+:([^@]+)@', '://user:REDACTED@'),
        
        # File paths (Windows and Unix)
        (r'[A-Za-z]:\\(?:[^\\/:*?"<>|\r\n]+\\)*[^\\/:*?"<>|\r\n]*', 'PATH_REDACTED'),
        (r'/(?:home|root|usr|var|etc)/[^\s]+', 'PATH_REDACTED'),
        
        # Email addresses
        (r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', 'EMAIL_REDACTED'),
        
        # IP addresses (optional - might be needed for debugging)
        # (r'\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b', 'IP_REDACTED'),
        
        # Credit card numbers
        (r'\b(?:\d{4}[-\s]?){3}\d{4}\b', 'CARD_REDACTED'),
        
        # Social security numbers
        (r'\b\d{3}-\d{2}-\d{4}\b', 'SSN_REDACTED'),
    ]
    
    # Fields that should be completely removed
    SENSITIVE_FIELDS = {
        'password', 'secret', 'token', 'api_key', 'private_key',
        'access_token', 'refresh_token', 'authorization', 'auth_header'
    }
    
    # Fields that should be partially masked
    MASKABLE_FIELDS = {
        'username', 'email', 'phone', 'user_id'
    }
    
    @classmethod
    def sanitize_string(cls, text: str) -> str:
        """Sanitize a string by removing/masking sensitive information."""
        if not isinstance(text, str):
            return text
        
        sanitized = text
        for pattern, replacement in cls.SENSITIVE_PATTERNS:
            sanitized = re.sub(pattern, replacement, sanitized)
        
        return sanitized
    
    @classmethod
    def sanitize_dict(cls, data: Dict[str, Any]) -> Dict[str, Any]:
        """Sanitize a dictionary by removing/masking sensitive fields."""
        if not isinstance(data, dict):
            return data
        
        sanitized = {}
        for key, value in data.items():
            key_lower = key.lower()
            
            # Remove sensitive fields completely
            if key_lower in cls.SENSITIVE_FIELDS:
                sanitized[key] = 'REDACTED'
            # Mask partially sensitive fields
            elif key_lower in cls.MASKABLE_FIELDS:
                sanitized[key] = cls._mask_value(value)
            # Recursively sanitize nested structures
            elif isinstance(value, dict):
                sanitized[key] = cls.sanitize_dict(value)
            elif isinstance(value, list):
                sanitized[key] = cls.sanitize_list(value)
            elif isinstance(value, str):
                sanitized[key] = cls.sanitize_string(value)
            else:
                sanitized[key] = value
        
        return sanitized
    
    @classmethod
    def sanitize_list(cls, data: List[Any]) -> List[Any]:
        """Sanitize a list by processing each element."""
        if not isinstance(data, list):
            return data
        
        sanitized = []
        for item in data:
            if isinstance(item, dict):
                sanitized.append(cls.sanitize_dict(item))
            elif isinstance(item, list):
                sanitized.append(cls.sanitize_list(item))
            elif isinstance(item, str):
                sanitized.append(cls.sanitize_string(item))
            else:
                sanitized.append(item)
        
        return sanitized
    
    @classmethod
    def _mask_value(cls, value: Any) -> str:
        """Mask a value by showing only first and last characters."""
        if not isinstance(value, str) or len(value) <= 3:
            return 'MASKED'
        
        if len(value) <= 6:
            return value[0] + '*' * (len(value) - 2) + value[-1]
        else:
            return value[:2] + '*' * (len(value) - 4) + value[-2:]


def security_sanitizer_processor(logger: Any, name: str, event_dict: EventDict) -> EventDict:
    """Structlog processor to sanitize sensitive information."""
    # Sanitize the main event message
    if 'event' in event_dict:
        event_dict['event'] = SecuritySanitizer.sanitize_string(str(event_dict['event']))
    
    # Sanitize all other fields
    sanitized_dict = SecuritySanitizer.sanitize_dict(event_dict)
    
    return sanitized_dict


def alert_processor(logger: Any, name: str, event_dict: EventDict) -> EventDict:
    """Structlog processor to trigger alerts based on log levels and content."""
    level = event_dict.get('level', '').upper()
    event = event_dict.get('event', '')
    
    # Trigger alerts for critical errors
    if level == 'CRITICAL':
        # Don't await here as this is a sync processor
        # The alert will be handled asynchronously
        pass
    elif level == 'ERROR':
        # Check for specific error patterns
        if 'authentication' in event.lower():
            # Authentication errors will be handled by specific alert functions
            pass
        elif 'api' in event.lower() and ('timeout' in event.lower() or 'outage' in event.lower()):
            # API outage detection
            pass
    
    return event_dict


def performance_processor(logger: Any, name: str, event_dict: EventDict) -> EventDict:
    """Structlog processor to track performance metrics."""
    # Add performance tracking if response_time_ms is present
    if 'response_time_ms' in event_dict:
        response_time = event_dict['response_time_ms']
        
        # Log slow requests
        if response_time > 5000:  # 5 seconds
            event_dict['performance_issue'] = 'slow_request'
        elif response_time > 10000:  # 10 seconds
            event_dict['performance_issue'] = 'very_slow_request'
    
    return event_dict


def context_processor(logger: Any, name: str, event_dict: EventDict) -> EventDict:
    """Structlog processor to add contextual information."""
    # Add timestamp if not present
    if 'timestamp' not in event_dict:
        event_dict['timestamp'] = datetime.utcnow().isoformat()
    
    # Add service information
    event_dict['service'] = 'project-enigma-backend'
    event_dict['version'] = '0.1.0'
    
    return event_dict


def setup_enhanced_logging(
    log_level: str = "INFO",
    enable_json: bool = False,
    enable_security_sanitization: bool = True,
    enable_alerts: bool = True
) -> None:
    """
    Set up enhanced structured logging with security features.
    
    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        enable_json: Whether to use JSON formatting (default: False for custom format)
        enable_security_sanitization: Whether to sanitize sensitive information
        enable_alerts: Whether to enable alert integration
    """
    # Configure standard logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, log_level.upper()),
    )
    
    # Build processor chain
    processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S"),
        structlog.processors.StackInfoRenderer(),
        context_processor,
        performance_processor,
    ]
    
    # Add security sanitization if enabled
    if enable_security_sanitization:
        processors.append(security_sanitizer_processor)
    
    # Add alert integration if enabled
    if enable_alerts:
        processors.append(alert_processor)
    
    # Add final formatting
    if enable_json:
        processors.extend([
            structlog.dev.set_exc_info,
            structlog.processors.JSONRenderer()
        ])
    else:
        processors.extend([
            structlog.dev.set_exc_info,
            custom_formatter
        ])
    
    # Configure structlog
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, log_level.upper())
        ),
        logger_factory=structlog.WriteLoggerFactory(),
        context_class=structlog.threadlocal.wrap_dict(dict),
        cache_logger_on_first_use=True,
    )


class EnhancedLogger:
    """Enhanced logger with automatic alert integration and security features."""
    
    def __init__(self, name: str):
        self.logger = structlog.get_logger(name)
        self.name = name
    
    def debug(self, message: str, **kwargs):
        """Log debug message."""
        self.logger.debug(message, **kwargs)
    
    def info(self, message: str, **kwargs):
        """Log info message."""
        self.logger.info(message, **kwargs)
    
    def warning(self, message: str, **kwargs):
        """Log warning message."""
        self.logger.warning(message, **kwargs)
    
    def error(self, message: str, **kwargs):
        """Log error message."""
        self.logger.error(message, **kwargs)
    
    def critical(self, message: str, **kwargs):
        """Log critical message."""
        self.logger.critical(message, **kwargs)
    
    async def error_with_alert(
        self,
        message: str,
        category: AlertCategory = AlertCategory.SYSTEM_RESOURCE,
        severity: AlertSeverity = AlertSeverity.MEDIUM,
        **kwargs
    ):
        """Log error and trigger alert."""
        self.logger.error(message, **kwargs)
        
        await alert_manager.trigger_alert(
            category=category,
            title=f"Error in {self.name}",
            description=message,
            metadata=kwargs,
            severity=severity
        )
    
    async def critical_with_alert(
        self,
        message: str,
        category: AlertCategory = AlertCategory.SYSTEM_RESOURCE,
        **kwargs
    ):
        """Log critical message and trigger critical alert."""
        self.logger.critical(message, **kwargs)
        
        await alert_manager.trigger_alert(
            category=category,
            title=f"Critical error in {self.name}",
            description=message,
            metadata=kwargs,
            severity=AlertSeverity.CRITICAL
        )


def get_logger(name: str) -> EnhancedLogger:
    """Get an enhanced logger instance."""
    return EnhancedLogger(name)


def log_function_call(
    level: LogLevel = LogLevel.INFO,
    include_args: bool = True,
    include_result: bool = False,
    include_execution_time: bool = True,
    log_errors: bool = True
):
    """
    Decorator to log function calls with detailed information.
    
    Args:
        level: Log level for the function call
        include_args: Whether to log function arguments
        include_result: Whether to log function result
        include_execution_time: Whether to log execution time
        log_errors: Whether to log errors with full traceback
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            # Get function metadata
            func_name = func.__name__
            module_name = func.__module__
            file_name = inspect.getfile(func)
            line_number = inspect.getsourcelines(func)[1]
            
            # Create logger
            logger = get_logger(f"{module_name}.{func_name}")
            
            # Prepare log context
            log_context = {
                "function_name": func_name,
                "module_name": module_name,
                "file_name": file_name,
                "line_number": line_number,
                "is_async": True
            }
            
            # Log function entry
            if include_args:
                # Sanitize arguments for logging
                sanitized_args = SecuritySanitizer.sanitize_list(list(args))
                sanitized_kwargs = SecuritySanitizer.sanitize_dict(kwargs)
                log_context.update({
                    "args": sanitized_args,
                    "kwargs": sanitized_kwargs
                })
            
            start_time = datetime.utcnow()
            getattr(logger, level.value)(
                f"Function call started: {func_name}",
                **log_context
            )
            
            try:
                # Execute function
                result = await func(*args, **kwargs)
                
                # Calculate execution time
                execution_time = (datetime.utcnow() - start_time).total_seconds() * 1000
                
                # Log successful completion
                completion_context = {
                    "function_name": func_name,
                    "module_name": module_name,
                    "file_name": file_name,
                    "line_number": line_number,
                    "is_async": True,
                    "status": "success"
                }
                
                if include_execution_time:
                    completion_context["execution_time_ms"] = execution_time
                
                if include_result:
                    completion_context["result"] = SecuritySanitizer.sanitize_dict(result) if isinstance(result, dict) else str(result)
                
                getattr(logger, level.value)(
                    f"Function call completed: {func_name}",
                    **completion_context
                )
                
                return result
                
            except Exception as e:
                # Calculate execution time
                execution_time = (datetime.utcnow() - start_time).total_seconds() * 1000
                
                # Log error with full context
                error_context = {
                    "function_name": func_name,
                    "module_name": module_name,
                    "file_name": file_name,
                    "line_number": line_number,
                    "is_async": True,
                    "status": "error",
                    "error_type": type(e).__name__,
                    "error_message": str(e)
                }
                
                if include_execution_time:
                    error_context["execution_time_ms"] = execution_time
                
                if log_errors:
                    error_context["traceback"] = traceback.format_exc()
                
                logger.error(
                    f"Function call failed: {func_name}",
                    **error_context
                )
                
                # Re-raise the exception
                raise
        
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            # Get function metadata
            func_name = func.__name__
            module_name = func.__module__
            file_name = inspect.getfile(func)
            line_number = inspect.getsourcelines(func)[1]
            
            # Create logger
            logger = get_logger(f"{module_name}.{func_name}")
            
            # Prepare log context
            log_context = {
                "function_name": func_name,
                "module_name": module_name,
                "file_name": file_name,
                "line_number": line_number,
                "is_async": False
            }
            
            # Log function entry
            if include_args:
                # Sanitize arguments for logging
                sanitized_args = SecuritySanitizer.sanitize_list(list(args))
                sanitized_kwargs = SecuritySanitizer.sanitize_dict(kwargs)
                log_context.update({
                    "args": sanitized_args,
                    "kwargs": sanitized_kwargs
                })
            
            start_time = datetime.utcnow()
            getattr(logger, level.value)(
                f"Function call started: {func_name}",
                **log_context
            )
            
            try:
                # Execute function
                result = func(*args, **kwargs)
                
                # Calculate execution time
                execution_time = (datetime.utcnow() - start_time).total_seconds() * 1000
                
                # Log successful completion
                completion_context = {
                    "function_name": func_name,
                    "module_name": module_name,
                    "file_name": file_name,
                    "line_number": line_number,
                    "is_async": False,
                    "status": "success"
                }
                
                if include_execution_time:
                    completion_context["execution_time_ms"] = execution_time
                
                if include_result:
                    completion_context["result"] = SecuritySanitizer.sanitize_dict(result) if isinstance(result, dict) else str(result)
                
                getattr(logger, level.value)(
                    f"Function call completed: {func_name}",
                    **completion_context
                )
                
                return result
                
            except Exception as e:
                # Calculate execution time
                execution_time = (datetime.utcnow() - start_time).total_seconds() * 1000
                
                # Log error with full context
                error_context = {
                    "function_name": func_name,
                    "module_name": module_name,
                    "file_name": file_name,
                    "line_number": line_number,
                    "is_async": False,
                    "status": "error",
                    "error_type": type(e).__name__,
                    "error_message": str(e)
                }
                
                if include_execution_time:
                    error_context["execution_time_ms"] = execution_time
                
                if log_errors:
                    error_context["traceback"] = traceback.format_exc()
                
                logger.error(
                    f"Function call failed: {func_name}",
                    **error_context
                )
                
                # Re-raise the exception
                raise
        
        # Return appropriate wrapper based on function type
        if inspect.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator


def log_api_endpoint(
    level: LogLevel = LogLevel.INFO,
    include_request: bool = True,
    include_response: bool = False,
    include_execution_time: bool = True,
    log_errors: bool = True
):
    """
    Decorator specifically for API endpoints with request/response logging.
    
    Args:
        level: Log level for the endpoint call
        include_request: Whether to log request details
        include_response: Whether to log response details
        include_execution_time: Whether to log execution time
        log_errors: Whether to log errors with full traceback
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # Get function metadata
            func_name = func.__name__
            module_name = func.__module__
            file_name = inspect.getfile(func)
            line_number = inspect.getsourcelines(func)[1]
            
            # Create logger
            logger = get_logger(f"api.{module_name}.{func_name}")
            
            # Extract request information if available
            request_info = {}
            if args and hasattr(args[0], '__class__') and 'Request' in str(args[0].__class__):
                request = args[0]
                request_info = {
                    "method": getattr(request, 'method', 'UNKNOWN'),
                    "url": str(getattr(request, 'url', 'UNKNOWN')),
                    "client_ip": getattr(request, 'client', ('UNKNOWN', 0))[0] if hasattr(request, 'client') else 'UNKNOWN',
                    "user_agent": getattr(request, 'headers', {}).get('user-agent', 'UNKNOWN')
                }
            
            # Prepare log context
            log_context = {
                "function_name": func_name,
                "module_name": module_name,
                "file_name": file_name,
                "line_number": line_number,
                "endpoint_type": "api",
                "is_async": True
            }
            
            if include_request and request_info:
                log_context.update(request_info)
            
            if include_request and kwargs:
                log_context["request_data"] = SecuritySanitizer.sanitize_dict(kwargs)
            
            start_time = datetime.utcnow()
            getattr(logger, level.value)(
                f"API endpoint called: {func_name}",
                **log_context
            )
            
            try:
                # Execute function
                result = await func(*args, **kwargs)
                
                # Calculate execution time
                execution_time = (datetime.utcnow() - start_time).total_seconds() * 1000
                
                # Log successful completion
                completion_context = {
                    "function_name": func_name,
                    "module_name": module_name,
                    "file_name": file_name,
                    "line_number": line_number,
                    "endpoint_type": "api",
                    "is_async": True,
                    "status": "success"
                }
                
                if include_execution_time:
                    completion_context["execution_time_ms"] = execution_time
                
                if include_response:
                    completion_context["response_data"] = SecuritySanitizer.sanitize_dict(result) if isinstance(result, dict) else str(result)
                
                getattr(logger, level.value)(
                    f"API endpoint completed: {func_name}",
                    **completion_context
                )
                
                return result
                
            except Exception as e:
                # Calculate execution time
                execution_time = (datetime.utcnow() - start_time).total_seconds() * 1000
                
                # Log error with full context
                error_context = {
                    "function_name": func_name,
                    "module_name": module_name,
                    "file_name": file_name,
                    "line_number": line_number,
                    "endpoint_type": "api",
                    "is_async": True,
                    "status": "error",
                    "error_type": type(e).__name__,
                    "error_message": str(e)
                }
                
                if include_execution_time:
                    error_context["execution_time_ms"] = execution_time
                
                if log_errors:
                    error_context["traceback"] = traceback.format_exc()
                
                logger.error(
                    f"API endpoint failed: {func_name}",
                    **error_context
                )
                
                # Re-raise the exception
                raise
        
        return wrapper
    
    return decorator


def log_workflow_function(
    level: LogLevel = LogLevel.INFO,
    include_state: bool = True,
    include_result: bool = False,
    include_execution_time: bool = True,
    log_errors: bool = True
):
    """
    Decorator specifically for workflow functions with state logging.
    
    Args:
        level: Log level for the workflow function call
        include_state: Whether to log workflow state
        include_result: Whether to log function result
        include_execution_time: Whether to log execution time
        log_errors: Whether to log errors with full traceback
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            # Get function metadata
            func_name = func.__name__
            module_name = func.__module__
            file_name = inspect.getfile(func)
            line_number = inspect.getsourcelines(func)[1]
            
            # Create logger
            logger = get_logger(f"workflow.{module_name}.{func_name}")
            
            # Extract workflow state if available
            workflow_state = {}
            if args and isinstance(args[0], dict):
                workflow_state = args[0]
            elif 'state' in kwargs:
                workflow_state = kwargs['state']
            
            # Prepare log context
            log_context = {
                "function_name": func_name,
                "module_name": module_name,
                "file_name": file_name,
                "line_number": line_number,
                "function_type": "workflow",
                "is_async": True
            }
            
            if include_state and workflow_state:
                log_context["workflow_state"] = SecuritySanitizer.sanitize_dict(workflow_state)
            
            if kwargs:
                log_context["function_params"] = SecuritySanitizer.sanitize_dict(kwargs)
            
            start_time = datetime.utcnow()
            getattr(logger, level.value)(
                f"Workflow function called: {func_name}",
                **log_context
            )
            
            try:
                # Execute function
                result = await func(*args, **kwargs)
                
                # Calculate execution time
                execution_time = (datetime.utcnow() - start_time).total_seconds() * 1000
                
                # Log successful completion
                completion_context = {
                    "function_name": func_name,
                    "module_name": module_name,
                    "file_name": file_name,
                    "line_number": line_number,
                    "function_type": "workflow",
                    "is_async": True,
                    "status": "success"
                }
                
                if include_execution_time:
                    completion_context["execution_time_ms"] = execution_time
                
                if include_result:
                    completion_context["result"] = SecuritySanitizer.sanitize_dict(result) if isinstance(result, dict) else str(result)
                
                getattr(logger, level.value)(
                    f"Workflow function completed: {func_name}",
                    **completion_context
                )
                
                return result
                
            except Exception as e:
                # Calculate execution time
                execution_time = (datetime.utcnow() - start_time).total_seconds() * 1000
                
                # Log error with full context
                error_context = {
                    "function_name": func_name,
                    "module_name": module_name,
                    "file_name": file_name,
                    "line_number": line_number,
                    "function_type": "workflow",
                    "is_async": True,
                    "status": "error",
                    "error_type": type(e).__name__,
                    "error_message": str(e)
                }
                
                if include_execution_time:
                    error_context["execution_time_ms"] = execution_time
                
                if log_errors:
                    error_context["traceback"] = traceback.format_exc()
                
                logger.error(
                    f"Workflow function failed: {func_name}",
                    **error_context
                )
                
                # Re-raise the exception
                raise
        
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            # Get function metadata
            func_name = func.__name__
            module_name = func.__module__
            file_name = inspect.getfile(func)
            line_number = inspect.getsourcelines(func)[1]
            
            # Create logger
            logger = get_logger(f"workflow.{module_name}.{func_name}")
            
            # Extract workflow state if available
            workflow_state = {}
            if args and isinstance(args[0], dict):
                workflow_state = args[0]
            elif 'state' in kwargs:
                workflow_state = kwargs['state']
            
            # Prepare log context
            log_context = {
                "function_name": func_name,
                "module_name": module_name,
                "file_name": file_name,
                "line_number": line_number,
                "function_type": "workflow",
                "is_async": False
            }
            
            if include_state and workflow_state:
                log_context["workflow_state"] = SecuritySanitizer.sanitize_dict(workflow_state)
            
            if kwargs:
                log_context["function_params"] = SecuritySanitizer.sanitize_dict(kwargs)
            
            start_time = datetime.utcnow()
            getattr(logger, level.value)(
                f"Workflow function called: {func_name}",
                **log_context
            )
            
            try:
                # Execute function
                result = func(*args, **kwargs)
                
                # Calculate execution time
                execution_time = (datetime.utcnow() - start_time).total_seconds() * 1000
                
                # Log successful completion
                completion_context = {
                    "function_name": func_name,
                    "module_name": module_name,
                    "file_name": file_name,
                    "line_number": line_number,
                    "function_type": "workflow",
                    "is_async": False,
                    "status": "success"
                }
                
                if include_execution_time:
                    completion_context["execution_time_ms"] = execution_time
                
                if include_result:
                    completion_context["result"] = SecuritySanitizer.sanitize_dict(result) if isinstance(result, dict) else str(result)
                
                getattr(logger, level.value)(
                    f"Workflow function completed: {func_name}",
                    **completion_context
                )
                
                return result
                
            except Exception as e:
                # Calculate execution time
                execution_time = (datetime.utcnow() - start_time).total_seconds() * 1000
                
                # Log error with full context
                error_context = {
                    "function_name": func_name,
                    "module_name": module_name,
                    "file_name": file_name,
                    "line_number": line_number,
                    "function_type": "workflow",
                    "is_async": False,
                    "status": "error",
                    "error_type": type(e).__name__,
                    "error_message": str(e)
                }
                
                if include_execution_time:
                    error_context["execution_time_ms"] = execution_time
                
                if log_errors:
                    error_context["traceback"] = traceback.format_exc()
                
                logger.error(
                    f"Workflow function failed: {func_name}",
                    **error_context
                )
                
                # Re-raise the exception
                raise
        
        # Return appropriate wrapper based on function type
        if inspect.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator


# Example usage and testing
def test_security_sanitization():
    """Test the security sanitization functionality."""
    test_data = {
        "username": "john.doe@example.com",
        "password": "super_secret_password",
        "api_token": "abc123def456ghi789",
        "message": "User authentication failed with token=secret123 from /home/user/app",
        "nested": {
            "secret": "another_secret",
            "normal_field": "normal_value"
        },
        "list_data": [
            {"password": "list_secret"},
            "some normal string with token=hidden123"
        ]
    }
    
    sanitized = SecuritySanitizer.sanitize_dict(test_data)
    print("Original:", json.dumps(test_data, indent=2))
    print("Sanitized:", json.dumps(sanitized, indent=2))


if __name__ == "__main__":
    # Set up enhanced logging
    setup_enhanced_logging(
        log_level="DEBUG",
        enable_json=True,
        enable_security_sanitization=True,
        enable_alerts=True
    )
    
    # Test logging
    logger = get_logger("test")
    logger.info("Test message", user="john", sensitive_token="secret123")
    
    # Test sanitization
    test_security_sanitization()