"""
API Request and Response Models

This module defines Pydantic models for API requests, responses, and data validation
used throughout the Project Enigma backend.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, validator


class HealthStatus(str, Enum):
    """Health status enumeration."""

    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    ERROR = "error"


class SystemStatus(str, Enum):
    """System status enumeration for comprehensive health checks."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


class ReleaseType(str, Enum):
    """Release type enumeration."""

    RELEASE = "release"
    HOTFIX = "hotfix"


class WorkflowStatus(str, Enum):
    """Workflow execution status."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    AWAITING_APPROVAL = "awaiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RepositoryConfig(BaseModel):
    """Repository configuration model."""

    id: str = Field(..., description="Unique repository identifier")
    name: str = Field(..., description="Repository name")
    url: str = Field(..., description="Repository URL")
    description: Optional[str] = Field(None, description="Repository description")
    is_active: bool = Field(True, description="Whether the repository is active")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class RepositoryRequest(BaseModel):
    """Repository creation/update request model."""

    name: str = Field(..., description="Repository name")
    url: str = Field(..., description="Repository URL")
    description: Optional[str] = Field(None, description="Repository description")

    @validator("name")
    def validate_name(cls, v):
        """Validate repository name."""
        if not v or len(v.strip()) < 1:
            raise ValueError("Repository name cannot be empty")
        if len(v) > 100:
            raise ValueError("Repository name cannot exceed 100 characters")
        return v.strip()

    @validator("url")
    def validate_url(cls, v):
        """Validate repository URL."""
        if not v.startswith(("http://", "https://", "git@")):
            raise ValueError("Repository URL must be a valid HTTP or Git URL")
        return v


class RepositoryConfigList(BaseModel):
    """Repository configuration list with metadata."""

    repositories: List[RepositoryConfig] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)


class ChatRequest(BaseModel):
    """Chat message request model."""

    message: str = Field(..., description="User message content")
    repositories: List[str] = Field(default=[], description="Selected repository IDs")
    release_type: Optional[ReleaseType] = Field(None, description="Type of release")
    sprint_name: Optional[str] = Field(None, description="Sprint branch name")
    fix_version: Optional[str] = Field(None, description="JIRA fix version")
    session_id: Optional[str] = Field(None, description="Chat session identifier")

    @validator("message")
    def validate_message(cls, v):
        """Validate chat message."""
        if not v or len(v.strip()) < 1:
            raise ValueError("Message cannot be empty")
        if len(v) > 5000:
            raise ValueError("Message cannot exceed 5000 characters")
        return v.strip()


class ChatResponse(BaseModel):
    """Chat message response model."""

    message: str = Field(..., description="AI response message")
    message_type: str = Field(default="text", description="Type of message")
    workflow_status: Optional[WorkflowStatus] = Field(
        None, description="Current workflow status"
    )
    data: Optional[Dict[str, Any]] = Field(None, description="Additional response data")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    requires_approval: bool = Field(
        False, description="Whether user approval is required"
    )


class WorkflowState(BaseModel):
    """Workflow state model."""

    workflow_id: str = Field(..., description="Unique workflow identifier")
    status: WorkflowStatus = Field(..., description="Current workflow status")
    repositories: List[str] = Field(..., description="Target repository IDs")
    release_type: ReleaseType = Field(..., description="Type of release")
    sprint_name: str = Field(..., description="Sprint branch name")
    fix_version: str = Field(..., description="JIRA fix version")
    current_step: Optional[str] = Field(None, description="Current workflow step")
    steps_completed: List[str] = Field(
        default=[], description="Completed workflow steps"
    )
    error_message: Optional[str] = Field(None, description="Error message if failed")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    data: Dict[str, Any] = Field(default={}, description="Workflow execution data")





class ErrorResponse(BaseModel):
    """Standard error response model."""

    error: Dict[str, Any] = Field(..., description="Error details")


class HealthResponse(BaseModel):
    """Comprehensive health check response model."""

    status: SystemStatus = Field(..., description="Overall system status")
    timestamp: datetime = Field(..., description="Response timestamp")
    response_time_ms: float = Field(..., description="Health check response time")
    version: str = Field(..., description="Service version")
    environment: str = Field(..., description="Environment name")
    system_metrics: Optional[Dict[str, Any]] = Field(
        None, description="System resource metrics"
    )
    api_connectivity: Optional[List[Dict[str, Any]]] = Field(
        None, description="API connectivity checks"
    )
    uptime_seconds: float = Field(..., description="System uptime in seconds")
    error: Optional[str] = Field(None, description="Error message if unhealthy")


class MetricsResponse(BaseModel):
    """Application metrics response model."""

    timestamp: datetime = Field(..., description="Metrics collection timestamp")
    request_count: int = Field(..., description="Total number of requests")
    error_count: int = Field(..., description="Total number of errors")
    workflow_executions: int = Field(..., description="Total workflow executions")
    error_rate_percent: float = Field(..., description="Error rate percentage")
    avg_api_response_time_ms: float = Field(
        ..., description="Average API response time"
    )
    avg_workflow_time_ms: float = Field(
        ..., description="Average workflow execution time"
    )
    system_metrics: Dict[str, Any] = Field(..., description="Current system metrics")
    uptime_seconds: float = Field(..., description="System uptime in seconds")


class RepositoryListResponse(BaseModel):
    """Repository list response model."""

    repositories: List[RepositoryConfig] = Field(
        ..., description="List of repositories"
    )
    total: int = Field(..., description="Total number of repositories")


class ChatHistoryResponse(BaseModel):
    """Chat history response model."""

    messages: List[Dict[str, Any]] = Field(..., description="Chat message history")
    session_id: str = Field(..., description="Chat session identifier")
    total_messages: int = Field(..., description="Total number of messages")
