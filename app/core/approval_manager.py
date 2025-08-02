"""
Approval management utilities for workflow checkpoints.

This module provides approval checkpoint creation and management
to avoid circular imports between workflow and API modules.
"""

import uuid
from datetime import datetime, timedelta
from typing import Any, Dict

# Global store for pending approvals (in production, use Redis)
pending_approvals: Dict[str, Dict[str, Any]] = {}
approval_timeouts: Dict[str, datetime] = {}


def create_approval_checkpoint(
    workflow_id: str, message: str, timeout_minutes: int = 30
) -> str:
    """
    Create a new approval checkpoint for a workflow.

    Args:
        workflow_id: The workflow ID requiring approval
        message: The approval message/description
        timeout_minutes: Approval timeout in minutes

    Returns:
        approval_id: Unique approval identifier
    """
    approval_id = str(uuid.uuid4())

    approval_data = {
        "approval_id": approval_id,
        "workflow_id": workflow_id,
        "message": message,
        "created_at": datetime.now().isoformat(),
        "status": "pending",
    }

    pending_approvals[workflow_id] = approval_data
    approval_timeouts[workflow_id] = datetime.now() + timedelta(minutes=timeout_minutes)

    return approval_id


def get_pending_approval(workflow_id: str) -> Dict[str, Any]:
    """Get pending approval data for a workflow."""
    return pending_approvals.get(workflow_id)


def list_pending_approvals() -> Dict[str, Dict[str, Any]]:
    """List all pending approvals."""
    return pending_approvals.copy()


def remove_approval(workflow_id: str) -> bool:
    """Remove an approval checkpoint."""
    if workflow_id in pending_approvals:
        pending_approvals.pop(workflow_id)
        approval_timeouts.pop(workflow_id, None)
        return True
    return False


def is_approval_expired(workflow_id: str) -> bool:
    """Check if an approval has expired."""
    if workflow_id not in approval_timeouts:
        return False
    return datetime.now() > approval_timeouts[workflow_id] 