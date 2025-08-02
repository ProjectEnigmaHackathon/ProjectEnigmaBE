"""
Enhanced Logging Utilities for API and Workflow Modules

This module provides comprehensive logging decorators and utilities
that automatically log function calls with file name, line number,
function name, and detailed error information.
"""

import functools
import inspect
import traceback
from datetime import datetime
from typing import Any, Callable, Dict
from enum import Enum

from app.core.logging import get_logger, SecuritySanitizer


class LogLevel(Enum):
    """Log levels for the enhanced logging system."""
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


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
            path = "N/A"
            if args and hasattr(args[0], '__class__') and 'Request' in str(args[0].__class__):
                request = args[0]
                # Extract the route path
                if hasattr(request, 'url'):
                    path = str(request.url.path)
                elif hasattr(request, 'scope') and 'path' in request.scope:
                    path = request.scope['path']
                
                request_info = {
                    "method": getattr(request, 'method', 'UNKNOWN'),
                    "url": str(getattr(request, 'url', 'UNKNOWN')),
                    "path": path,
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
                "is_async": True,
                "path": path  # Include the API path
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
                    "status": "success",
                    "path": path  # Include the API path
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
                    "error_message": str(e),
                    "path": path  # Include the API path
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


def log_error_with_context(
    logger_name: str,
    error: Exception,
    context: Dict[str, Any] = None,
    include_traceback: bool = True
):
    """
    Utility function to log errors with detailed context.
    
    Args:
        logger_name: Name for the logger
        error: The exception that occurred
        context: Additional context to include in the log
        include_traceback: Whether to include the full traceback
    """
    logger = get_logger(logger_name)
    
    # Get current frame information
    frame = inspect.currentframe().f_back
    file_name = frame.f_code.co_filename
    line_number = frame.f_lineno
    function_name = frame.f_code.co_name
    
    error_context = {
        "error_type": type(error).__name__,
        "error_message": str(error),
        "file_name": file_name,
        "line_number": line_number,
        "function_name": function_name
    }
    
    if context:
        error_context.update(SecuritySanitizer.sanitize_dict(context))
    
    if include_traceback:
        error_context["traceback"] = traceback.format_exc()
    
    logger.error(
        f"Error occurred in {function_name}",
        **error_context
    ) 