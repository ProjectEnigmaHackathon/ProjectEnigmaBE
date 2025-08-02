"""
Alert System for Critical Failures

This module provides a comprehensive alerting system for monitoring critical
failures, authentication issues, API outages, and workflow failures.
"""

import asyncio
import json
import time
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional

import structlog
from pydantic import BaseModel, Field

logger = structlog.get_logger()


class AlertSeverity(str, Enum):
    """Alert severity levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AlertCategory(str, Enum):
    """Alert categories."""
    AUTHENTICATION = "authentication"
    API_OUTAGE = "api_outage"
    WORKFLOW_FAILURE = "workflow_failure"
    SYSTEM_RESOURCE = "system_resource"
    DATA_CORRUPTION = "data_corruption"
    SECURITY = "security"
    PERFORMANCE = "performance"


class AlertStatus(str, Enum):
    """Alert status."""
    ACTIVE = "active"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"
    SUPPRESSED = "suppressed"


class Alert(BaseModel):
    """Alert model."""
    id: str = Field(..., description="Unique alert identifier")
    title: str = Field(..., description="Alert title")
    description: str = Field(..., description="Alert description")
    severity: AlertSeverity = Field(..., description="Alert severity")
    category: AlertCategory = Field(..., description="Alert category")
    status: AlertStatus = Field(default=AlertStatus.ACTIVE, description="Alert status")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    resolved_at: Optional[datetime] = Field(None, description="Resolution timestamp")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")
    count: int = Field(default=1, description="Number of occurrences")
    last_occurrence: datetime = Field(default_factory=datetime.utcnow)


class AlertRule(BaseModel):
    """Alert rule configuration."""
    category: AlertCategory
    severity: AlertSeverity
    threshold: int = 1
    window_minutes: int = 5
    enabled: bool = True
    suppress_minutes: int = 30


class AlertManager:
    """
    Alert management system for handling critical failures and notifications.
    """
    
    def __init__(self):
        self.alerts: Dict[str, Alert] = {}
        self.rules: Dict[AlertCategory, AlertRule] = self._init_default_rules()
        self.suppressed_alerts: Dict[str, datetime] = {}
        self.alert_counts: Dict[str, List[datetime]] = {}
        
    def _init_default_rules(self) -> Dict[AlertCategory, AlertRule]:
        """Initialize default alert rules."""
        return {
            AlertCategory.AUTHENTICATION: AlertRule(
                category=AlertCategory.AUTHENTICATION,
                severity=AlertSeverity.CRITICAL,
                threshold=3,
                window_minutes=5,
                suppress_minutes=15
            ),
            AlertCategory.API_OUTAGE: AlertRule(
                category=AlertCategory.API_OUTAGE,
                severity=AlertSeverity.HIGH,
                threshold=2,
                window_minutes=10,
                suppress_minutes=30
            ),
            AlertCategory.WORKFLOW_FAILURE: AlertRule(
                category=AlertCategory.WORKFLOW_FAILURE,
                severity=AlertSeverity.MEDIUM,
                threshold=1,
                window_minutes=1,
                suppress_minutes=10
            ),
            AlertCategory.SYSTEM_RESOURCE: AlertRule(
                category=AlertCategory.SYSTEM_RESOURCE,
                severity=AlertSeverity.HIGH,
                threshold=1,
                window_minutes=5,
                suppress_minutes=20
            ),
            AlertCategory.DATA_CORRUPTION: AlertRule(
                category=AlertCategory.DATA_CORRUPTION,
                severity=AlertSeverity.CRITICAL,
                threshold=1,
                window_minutes=1,
                suppress_minutes=60
            ),
            AlertCategory.SECURITY: AlertRule(
                category=AlertCategory.SECURITY,
                severity=AlertSeverity.CRITICAL,
                threshold=1,
                window_minutes=1,
                suppress_minutes=30
            ),
            AlertCategory.PERFORMANCE: AlertRule(
                category=AlertCategory.PERFORMANCE,
                severity=AlertSeverity.LOW,
                threshold=5,
                window_minutes=15,
                suppress_minutes=60
            ),
        }
    
    def _generate_alert_id(self, category: AlertCategory, title: str) -> str:
        """Generate unique alert ID."""
        import hashlib
        content = f"{category.value}_{title}_{datetime.utcnow().date()}"
        return hashlib.md5(content.encode()).hexdigest()[:12]
    
    def _should_suppress_alert(self, alert_id: str, rule: AlertRule) -> bool:
        """Check if alert should be suppressed."""
        if alert_id in self.suppressed_alerts:
            suppress_until = self.suppressed_alerts[alert_id] + timedelta(minutes=rule.suppress_minutes)
            if datetime.utcnow() < suppress_until:
                return True
            else:
                # Remove expired suppression
                del self.suppressed_alerts[alert_id]
        return False
    
    def _check_threshold(self, alert_id: str, rule: AlertRule) -> bool:
        """Check if alert threshold is met."""
        if alert_id not in self.alert_counts:
            self.alert_counts[alert_id] = []
        
        current_time = datetime.utcnow()
        window_start = current_time - timedelta(minutes=rule.window_minutes)
        
        # Clean old occurrences
        self.alert_counts[alert_id] = [
            occurrence for occurrence in self.alert_counts[alert_id]
            if occurrence > window_start
        ]
        
        # Add current occurrence
        self.alert_counts[alert_id].append(current_time)
        
        return len(self.alert_counts[alert_id]) >= rule.threshold
    
    async def trigger_alert(
        self,
        category: AlertCategory,
        title: str,
        description: str,
        metadata: Optional[Dict[str, Any]] = None,
        severity: Optional[AlertSeverity] = None
    ) -> Optional[Alert]:
        """
        Trigger an alert with automatic deduplication and threshold checking.
        """
        rule = self.rules.get(category)
        if not rule or not rule.enabled:
            return None
        
        alert_id = self._generate_alert_id(category, title)
        
        # Check if alert should be suppressed
        if self._should_suppress_alert(alert_id, rule):
            logger.debug("Alert suppressed", alert_id=alert_id, category=category.value)
            return None
        
        # Check threshold
        if not self._check_threshold(alert_id, rule):
            logger.debug("Alert threshold not met", alert_id=alert_id, category=category.value)
            return None
        
        # Use rule severity if not overridden
        alert_severity = severity or rule.severity
        
        # Create or update alert
        if alert_id in self.alerts:
            alert = self.alerts[alert_id]
            alert.count += 1
            alert.last_occurrence = datetime.utcnow()
            alert.updated_at = datetime.utcnow()
            alert.status = AlertStatus.ACTIVE
            if metadata:
                alert.metadata.update(metadata)
        else:
            alert = Alert(
                id=alert_id,
                title=title,
                description=description,
                severity=alert_severity,
                category=category,
                metadata=metadata or {}
            )
            self.alerts[alert_id] = alert
        
        # Suppress future identical alerts
        self.suppressed_alerts[alert_id] = datetime.utcnow()
        
        # Log alert
        logger.warning(
            "Alert triggered",
            alert_id=alert_id,
            title=title,
            category=category.value,
            severity=alert_severity.value,
            count=alert.count
        )
        
        # Send notifications (async)
        asyncio.create_task(self._send_notifications(alert))
        
        return alert
    
    async def _send_notifications(self, alert: Alert):
        """Send alert notifications to configured channels."""
        try:
            # Log-based notification (always available)
            logger.error(
                "ALERT",
                alert_id=alert.id,
                title=alert.title,
                description=alert.description,
                severity=alert.severity.value,
                category=alert.category.value,
                count=alert.count,
                metadata=alert.metadata
            )
            
            # In production, add additional notification channels:
            # - Email notifications
            # - Slack/Teams webhooks
            # - SMS alerts for critical issues
            # - PagerDuty integration
            
            if alert.severity == AlertSeverity.CRITICAL:
                await self._send_critical_notification(alert)
                
        except Exception as e:
            logger.error("Failed to send alert notification", error=str(e), alert_id=alert.id)
    
    async def _send_critical_notification(self, alert: Alert):
        """Send critical alert notification."""
        # Placeholder for critical alert handling
        # In production, this would integrate with:
        # - PagerDuty
        # - SMS gateway
        # - Emergency contact systems
        
        logger.critical(
            "CRITICAL ALERT - IMMEDIATE ACTION REQUIRED",
            alert_id=alert.id,
            title=alert.title,
            description=alert.description,
            category=alert.category.value,
            metadata=alert.metadata
        )
    
    def acknowledge_alert(self, alert_id: str) -> bool:
        """Acknowledge an alert."""
        if alert_id in self.alerts:
            self.alerts[alert_id].status = AlertStatus.ACKNOWLEDGED
            self.alerts[alert_id].updated_at = datetime.utcnow()
            logger.info("Alert acknowledged", alert_id=alert_id)
            return True
        return False
    
    def resolve_alert(self, alert_id: str) -> bool:
        """Resolve an alert."""
        if alert_id in self.alerts:
            self.alerts[alert_id].status = AlertStatus.RESOLVED
            self.alerts[alert_id].resolved_at = datetime.utcnow()
            self.alerts[alert_id].updated_at = datetime.utcnow()
            logger.info("Alert resolved", alert_id=alert_id)
            return True
        return False
    
    def get_active_alerts(self) -> List[Alert]:
        """Get all active alerts."""
        return [
            alert for alert in self.alerts.values()
            if alert.status == AlertStatus.ACTIVE
        ]
    
    def get_alert_summary(self) -> Dict[str, Any]:
        """Get alert summary statistics."""
        alerts = list(self.alerts.values())
        active_alerts = [a for a in alerts if a.status == AlertStatus.ACTIVE]
        
        return {
            "total_alerts": len(alerts),
            "active_alerts": len(active_alerts),
            "critical_alerts": len([a for a in active_alerts if a.severity == AlertSeverity.CRITICAL]),
            "high_alerts": len([a for a in active_alerts if a.severity == AlertSeverity.HIGH]),
            "alerts_by_category": {
                category.value: len([a for a in active_alerts if a.category == category])
                for category in AlertCategory
            },
            "oldest_unresolved": min([a.created_at for a in active_alerts], default=None),
        }


# Global alert manager instance
alert_manager = AlertManager()


# Convenience functions for common alert scenarios
async def alert_authentication_failure(
    username: str = None,
    ip_address: str = None,
    service: str = None,
    metadata: Dict[str, Any] = None
):
    """Alert for authentication failures."""
    title = f"Authentication failure{f' for {username}' if username else ''}"
    description = f"Failed authentication attempt{f' from {ip_address}' if ip_address else ''}{f' on {service}' if service else ''}"
    
    alert_metadata = metadata or {}
    if username:
        alert_metadata["username"] = username
    if ip_address:
        alert_metadata["ip_address"] = ip_address
    if service:
        alert_metadata["service"] = service
    
    return await alert_manager.trigger_alert(
        category=AlertCategory.AUTHENTICATION,
        title=title,
        description=description,
        metadata=alert_metadata
    )


async def alert_api_outage(
    service: str,
    endpoint: str = None,
    status_code: int = None,
    error_message: str = None,
    metadata: Dict[str, Any] = None
):
    """Alert for API outages."""
    title = f"{service} API outage"
    description = f"API service {service} is experiencing issues"
    if endpoint:
        description += f" on endpoint {endpoint}"
    if status_code:
        description += f" (HTTP {status_code})"
    
    alert_metadata = metadata or {}
    alert_metadata.update({
        "service": service,
        "endpoint": endpoint,
        "status_code": status_code,
        "error_message": error_message
    })
    
    return await alert_manager.trigger_alert(
        category=AlertCategory.API_OUTAGE,
        title=title,
        description=description,
        metadata=alert_metadata
    )


async def alert_workflow_failure(
    workflow_id: str,
    step: str = None,
    error_message: str = None,
    metadata: Dict[str, Any] = None
):
    """Alert for workflow failures."""
    title = f"Workflow failure: {workflow_id}"
    description = f"Workflow {workflow_id} failed"
    if step:
        description += f" at step {step}"
    if error_message:
        description += f": {error_message}"
    
    alert_metadata = metadata or {}
    alert_metadata.update({
        "workflow_id": workflow_id,
        "step": step,
        "error_message": error_message
    })
    
    return await alert_manager.trigger_alert(
        category=AlertCategory.WORKFLOW_FAILURE,
        title=title,
        description=description,
        metadata=alert_metadata
    )


async def alert_system_resource(
    resource_type: str,
    current_value: float,
    threshold: float,
    metadata: Dict[str, Any] = None
):
    """Alert for system resource issues."""
    title = f"High {resource_type} usage"
    description = f"{resource_type} usage is {current_value:.1f}% (threshold: {threshold:.1f}%)"
    
    alert_metadata = metadata or {}
    alert_metadata.update({
        "resource_type": resource_type,
        "current_value": current_value,
        "threshold": threshold
    })
    
    return await alert_manager.trigger_alert(
        category=AlertCategory.SYSTEM_RESOURCE,
        title=title,
        description=description,
        metadata=alert_metadata
    )


async def alert_security_issue(
    issue_type: str,
    description: str,
    metadata: Dict[str, Any] = None
):
    """Alert for security issues."""
    title = f"Security issue: {issue_type}"
    
    return await alert_manager.trigger_alert(
        category=AlertCategory.SECURITY,
        title=title,
        description=description,
        metadata=metadata,
        severity=AlertSeverity.CRITICAL
    )