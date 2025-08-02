"""
Health Monitoring and Metrics Endpoints

This module provides comprehensive health monitoring endpoints with system
status, API connectivity checks, and performance metrics.
"""

import asyncio
import time
from datetime import datetime
from typing import Any, Dict, List

import psutil
import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.core.config import Settings, get_settings
from app.integrations.auth_manager import AuthenticationManager as AuthManager
from app.models.api import HealthResponse, MetricsResponse, SystemStatus
from app.core.logging_utils import log_api_endpoint, LogLevel

logger = structlog.get_logger()
router = APIRouter()

# Global metrics storage (in production, use Redis or database)
_metrics_store = {
    "request_count": 0,
    "error_count": 0,
    "workflow_executions": 0,
    "api_call_times": [],
    "workflow_times": [],
    "last_health_check": None,
}


class HealthCheckResult(BaseModel):
    """Health check result for individual components."""
    service: str
    status: str
    response_time_ms: float
    error: str = None
    details: Dict[str, Any] = {}


class SystemMetrics(BaseModel):
    """System resource metrics."""
    cpu_percent: float
    memory_percent: float
    disk_percent: float
    uptime_seconds: float


async def check_api_connectivity(auth_manager: AuthManager) -> List[HealthCheckResult]:
    """Check connectivity to external APIs."""
    results = []
    
    # Check JIRA connectivity
    try:
        start_time = time.time()
        # Mock connectivity check - replace with actual API call
        await asyncio.sleep(0.1)  # Simulate API call
        response_time = (time.time() - start_time) * 1000
        
        results.append(HealthCheckResult(
            service="jira",
            status="healthy",
            response_time_ms=response_time,
            details={"endpoint": "JIRA API", "authenticated": True}
        ))
    except Exception as e:
        results.append(HealthCheckResult(
            service="jira",
            status="unhealthy",
            response_time_ms=0,
            error=str(e)
        ))
    
    # Check GitHub connectivity
    try:
        start_time = time.time()
        # Mock connectivity check - replace with actual API call
        await asyncio.sleep(0.1)  # Simulate API call
        response_time = (time.time() - start_time) * 1000
        
        results.append(HealthCheckResult(
            service="github",
            status="healthy",
            response_time_ms=response_time,
            details={"endpoint": "GitHub API", "authenticated": True}
        ))
    except Exception as e:
        results.append(HealthCheckResult(
            service="github",
            status="unhealthy",
            response_time_ms=0,
            error=str(e)
        ))
    
    # Check Confluence connectivity
    try:
        start_time = time.time()
        # Mock connectivity check - replace with actual API call
        await asyncio.sleep(0.1)  # Simulate API call
        response_time = (time.time() - start_time) * 1000
        
        results.append(HealthCheckResult(
            service="confluence",
            status="healthy",
            response_time_ms=response_time,
            details={"endpoint": "Confluence API", "authenticated": True}
        ))
    except Exception as e:
        results.append(HealthCheckResult(
            service="confluence",
            status="unhealthy",
            response_time_ms=0,
            error=str(e)
        ))
    
    return results


def get_system_metrics() -> SystemMetrics:
    """Get current system resource metrics."""
    try:
        # Get CPU usage
        cpu_percent = psutil.cpu_percent(interval=1)
        
        # Get memory usage
        memory = psutil.virtual_memory()
        memory_percent = memory.percent
        
        # Get disk usage
        disk = psutil.disk_usage('/')
        disk_percent = (disk.used / disk.total) * 100
        
        # Get system uptime
        boot_time = psutil.boot_time()
        uptime_seconds = time.time() - boot_time
        
        return SystemMetrics(
            cpu_percent=cpu_percent,
            memory_percent=memory_percent,
            disk_percent=disk_percent,
            uptime_seconds=uptime_seconds
        )
    except Exception as e:
        logger.warning("Failed to get system metrics", error=str(e))
        return SystemMetrics(
            cpu_percent=0.0,
            memory_percent=0.0,
            disk_percent=0.0,
            uptime_seconds=0.0
        )


@router.get("/health", response_model=HealthResponse)
@log_api_endpoint(level=LogLevel.INFO, include_request=True, include_response=False, include_execution_time=True, log_errors=True)
async def health_check(
    settings: Settings = Depends(get_settings)
) -> HealthResponse:
    """
    Comprehensive health check endpoint.
    
    Returns system status, API connectivity, and basic metrics.
    """
    start_time = time.time()
    
    try:
        # Update metrics
        _metrics_store["last_health_check"] = datetime.utcnow().isoformat()
        
        # Get system metrics
        system_metrics = get_system_metrics()
        
        # Check API connectivity (with timeout)
        auth_manager = AuthManager()
        try:
            api_checks = await asyncio.wait_for(
                check_api_connectivity(auth_manager), 
                timeout=5.0
            )
        except asyncio.TimeoutError:
            api_checks = [
                HealthCheckResult(
                    service="all_apis",
                    status="timeout",
                    response_time_ms=5000,
                    error="Health check timeout"
                )
            ]
        
        # Determine overall status
        overall_status = SystemStatus.HEALTHY
        if any(check.status == "unhealthy" for check in api_checks):
            overall_status = SystemStatus.DEGRADED
        if any(check.status == "timeout" for check in api_checks):
            overall_status = SystemStatus.UNHEALTHY
            
        # Check critical system resources
        if (system_metrics.cpu_percent > 90 or 
            system_metrics.memory_percent > 90 or 
            system_metrics.disk_percent > 95):
            overall_status = SystemStatus.DEGRADED
        
        response_time = (time.time() - start_time) * 1000
        
        logger.info(
            "Health check completed",
            status=overall_status.value,
            response_time_ms=response_time,
            api_checks_count=len(api_checks)
        )
        
        return HealthResponse(
            status=overall_status,
            timestamp=datetime.utcnow(),
            response_time_ms=response_time,
            version="0.1.0",
            environment=settings.environment,
            system_metrics=system_metrics.dict(),
            api_connectivity=[check.dict() for check in api_checks],
            uptime_seconds=system_metrics.uptime_seconds
        )
        
    except Exception as e:
        logger.error("Health check failed", error=str(e))
        return HealthResponse(
            status=SystemStatus.UNHEALTHY,
            timestamp=datetime.utcnow(),
            response_time_ms=(time.time() - start_time) * 1000,
            version="0.1.0",
            environment=settings.environment,
            error=f"Health check failed: {str(e)}"
        )


@router.get("/health/ready")
@log_api_endpoint(level=LogLevel.INFO, include_request=True, include_response=False, include_execution_time=True, log_errors=True)
async def readiness_check() -> Dict[str, Any]:
    """
    Kubernetes-style readiness probe.
    
    Returns simple status for load balancer health checks.
    """
    try:
        # Quick checks for readiness
        auth_manager = AuthManager()
        
        # Check if we can access configuration
        settings = get_settings()
        
        return {
            "status": "ready",
            "timestamp": datetime.utcnow().isoformat(),
            "service": "project-enigma-backend"
        }
    except Exception as e:
        logger.error("Readiness check failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service not ready"
        )


@router.get("/health/live")
@log_api_endpoint(level=LogLevel.INFO, include_request=True, include_response=False, include_execution_time=True, log_errors=True)
async def liveness_check() -> Dict[str, Any]:
    """
    Kubernetes-style liveness probe.
    
    Returns basic application liveness status.
    """
    return {
        "status": "alive",
        "timestamp": datetime.utcnow().isoformat(),
        "service": "project-enigma-backend",
        "pid": psutil.Process().pid
    }


@router.get("/metrics", response_model=MetricsResponse)
@log_api_endpoint(level=LogLevel.INFO, include_request=True, include_response=False, include_execution_time=True, log_errors=True)
async def get_metrics() -> MetricsResponse:
    """
    Get detailed application metrics and performance data.
    """
    try:
        # Calculate average response times
        avg_api_time = (
            sum(_metrics_store["api_call_times"]) / len(_metrics_store["api_call_times"])
            if _metrics_store["api_call_times"] else 0
        )
        
        avg_workflow_time = (
            sum(_metrics_store["workflow_times"]) / len(_metrics_store["workflow_times"])
            if _metrics_store["workflow_times"] else 0
        )
        
        # Calculate error rate
        total_requests = _metrics_store["request_count"]
        error_rate = (
            (_metrics_store["error_count"] / total_requests * 100)
            if total_requests > 0 else 0
        )
        
        # Get current system metrics
        system_metrics = get_system_metrics()
        
        return MetricsResponse(
            timestamp=datetime.utcnow(),
            request_count=_metrics_store["request_count"],
            error_count=_metrics_store["error_count"],
            workflow_executions=_metrics_store["workflow_executions"],
            error_rate_percent=error_rate,
            avg_api_response_time_ms=avg_api_time,
            avg_workflow_time_ms=avg_workflow_time,
            system_metrics=system_metrics.dict(),
            uptime_seconds=system_metrics.uptime_seconds
        )
        
    except Exception as e:
        logger.error("Metrics collection failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to collect metrics"
        )


def record_request():
    """Record a new request in metrics."""
    _metrics_store["request_count"] += 1


def record_error():
    """Record an error in metrics."""
    _metrics_store["error_count"] += 1


def record_api_call_time(duration_ms: float):
    """Record API call duration."""
    _metrics_store["api_call_times"].append(duration_ms)
    # Keep only last 100 measurements
    if len(_metrics_store["api_call_times"]) > 100:
        _metrics_store["api_call_times"] = _metrics_store["api_call_times"][-100:]


def record_workflow_time(duration_ms: float):
    """Record workflow execution duration."""
    _metrics_store["workflow_times"].append(duration_ms)
    _metrics_store["workflow_executions"] += 1
    # Keep only last 50 measurements
    if len(_metrics_store["workflow_times"]) > 50:
        _metrics_store["workflow_times"] = _metrics_store["workflow_times"][-50:]