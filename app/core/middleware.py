"""
Middleware for performance monitoring, error tracking, and security.

This module provides FastAPI middleware for comprehensive monitoring,
error tracking, and security features.
"""

import time
import uuid
from datetime import datetime
from typing import Callable

import structlog
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.status import HTTP_500_INTERNAL_SERVER_ERROR

from app.api.endpoints.health import record_api_call_time, record_error, record_request

logger = structlog.get_logger()


class PerformanceMonitoringMiddleware(BaseHTTPMiddleware):
    """Middleware for monitoring request performance and collecting metrics."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request with performance monitoring."""
        start_time = time.time()
        request_id = str(uuid.uuid4())
        
        # Add request context
        request.state.request_id = request_id
        request.state.start_time = start_time
        
        # Log request start
        logger.info(
            "Request started",
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            query=str(request.url.query) if request.url.query else None,
            user_agent=request.headers.get("user-agent"),
            client_ip=self._get_client_ip(request)
        )
        
        # Record request in metrics
        record_request()
        
        try:
            # Process request
            response = await call_next(request)
            
            # Calculate response time
            response_time = (time.time() - start_time) * 1000
            
            # Record API call time
            record_api_call_time(response_time)
            
            # Add response headers
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Response-Time"] = f"{response_time:.2f}ms"
            
            # Log successful request
            logger.info(
                "Request completed",
                request_id=request_id,
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                response_time_ms=response_time
            )
            
            return response
            
        except Exception as exc:
            # Calculate response time for error case
            response_time = (time.time() - start_time) * 1000
            
            # Record error in metrics
            record_error()
            
            # Log error with sanitized information
            error_msg = self._sanitize_error_message(str(exc))
            logger.error(
                "Request failed",
                request_id=request_id,
                method=request.method,
                path=request.url.path,
                error_type=type(exc).__name__,
                error_message=error_msg,
                response_time_ms=response_time
            )
            
            # Return sanitized error response
            return JSONResponse(
                status_code=HTTP_500_INTERNAL_SERVER_ERROR,
                content={
                    "error": {
                        "type": "InternalServerError",
                        "message": "An unexpected error occurred",
                        "request_id": request_id,
                        "timestamp": datetime.utcnow().isoformat()
                    }
                },
                headers={
                    "X-Request-ID": request_id,
                    "X-Response-Time": f"{response_time:.2f}ms"
                }
            )

    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP address from request."""
        # Check for X-Forwarded-For header (load balancer/proxy)
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
        
        # Check for X-Real-IP header
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip
        
        # Fall back to direct client IP
        if request.client:
            return request.client.host
        
        return "unknown"

    def _sanitize_error_message(self, error_msg: str) -> str:
        """
        Sanitize error message to prevent information leakage.
        
        Removes sensitive information like API tokens, file paths, etc.
        """
        # List of patterns to sanitize
        sensitive_patterns = [
            "token=",
            "password=",
            "secret=",
            "api_key=",
            "authorization:",
            "bearer ",
            "C:\\",
            "/home/",
            "/var/",
            "/usr/",
            "/etc/",
        ]
        
        sanitized = error_msg.lower()
        
        # Check if message contains sensitive information
        for pattern in sensitive_patterns:
            if pattern in sanitized:
                return "Sensitive information detected in error - details logged securely"
        
        # Limit error message length
        if len(error_msg) > 200:
            return error_msg[:200] + "... (truncated)"
        
        return error_msg


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Middleware for adding security headers to responses."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Add security headers to response."""
        response = await call_next(request)
        
        # Add security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        
        # Add CSP header for API responses (not for static files)
        if request.url.path.startswith("/docs") or request.url.path.startswith("/openapi.json"):
            response.headers["Content-Security-Policy"] = (
                "default-src 'self' https://cdn.jsdelivr.net; "
                "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
                "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
                "img-src 'self' data: https:; "
                "connect-src 'self';"
            )
        elif not request.url.path.startswith("/static"):
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline'; "
                "style-src 'self' 'unsafe-inline'; "
                "img-src 'self' data: https:; "
                "connect-src 'self';"
            )


        return response


class RateLimitingMiddleware(BaseHTTPMiddleware):
    """Simple rate limiting middleware."""

    def __init__(self, app, max_requests: int = 100, window_seconds: int = 60):
        super().__init__(app)
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.request_history = {}

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Apply rate limiting based on client IP."""
        client_ip = self._get_client_ip(request)
        current_time = time.time()
        
        # Skip rate limiting for health checks
        if request.url.path in ["/health", "/health/ready", "/health/live"]:
            return await call_next(request)
        
        # Clean old entries
        self._cleanup_old_entries(current_time)
        
        # Get request history for this IP
        if client_ip not in self.request_history:
            self.request_history[client_ip] = []
        
        client_requests = self.request_history[client_ip]
        
        # Check if rate limit exceeded
        recent_requests = [
            req_time for req_time in client_requests
            if current_time - req_time < self.window_seconds
        ]
        
        if len(recent_requests) >= self.max_requests:
            logger.warning(
                "Rate limit exceeded",
                client_ip=client_ip,
                requests_count=len(recent_requests),
                max_requests=self.max_requests,
                window_seconds=self.window_seconds
            )
            
            return JSONResponse(
                status_code=429,
                content={
                    "error": {
                        "type": "RateLimitExceeded",
                        "message": f"Rate limit exceeded: {self.max_requests} requests per {self.window_seconds} seconds",
                        "retry_after": self.window_seconds
                    }
                },
                headers={
                    "Retry-After": str(self.window_seconds),
                    "X-RateLimit-Limit": str(self.max_requests),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(int(current_time + self.window_seconds))
                }
            )
        
        # Record this request
        self.request_history[client_ip].append(current_time)
        
        # Process request
        response = await call_next(request)
        
        # Add rate limit headers
        remaining = max(0, self.max_requests - len(recent_requests) - 1)
        response.headers["X-RateLimit-Limit"] = str(self.max_requests)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(int(current_time + self.window_seconds))
        
        return response

    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP address from request."""
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
        
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip
        
        if request.client:
            return request.client.host
        
        return "unknown"

    def _cleanup_old_entries(self, current_time: float) -> None:
        """Remove old request entries to prevent memory growth."""
        cutoff_time = current_time - (self.window_seconds * 2)  # Keep some extra history
        
        for client_ip in list(self.request_history.keys()):
            self.request_history[client_ip] = [
                req_time for req_time in self.request_history[client_ip]
                if req_time > cutoff_time
            ]
            
            # Remove empty entries
            if not self.request_history[client_ip]:
                del self.request_history[client_ip]