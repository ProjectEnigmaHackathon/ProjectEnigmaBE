"""
Workflow state management and persistence for LangGraph workflows.

This module provides state management, persistence, error recovery,
and monitoring capabilities for the release automation workflow.
"""

import asyncio
import json
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from threading import Lock
from typing import Any, Dict, List, Optional, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command

from app.core.config import get_settings
from app.core.logging_utils import log_workflow_function, LogLevel


@dataclass
class WorkflowMetadata:
    """Metadata for workflow execution tracking."""

    workflow_id: str
    created_at: datetime
    updated_at: datetime
    status: str  # "running", "paused", "completed", "failed", "cancelled"
    current_step: str
    error_count: int = 0
    last_error: Optional[str] = None
    execution_time: float = 0.0


class WorkflowStateStore:
    """Thread-safe in-memory state store with TTL cleanup."""

    def __init__(self, default_ttl_hours: int = 24):
        self._store: Dict[str, Dict[str, Any]] = {}
        self._metadata: Dict[str, WorkflowMetadata] = {}
        self._lock = Lock()
        self.default_ttl_hours = default_ttl_hours
        self._start_cleanup_task()

    def _start_cleanup_task(self):
        """Start background task for TTL cleanup."""

        def cleanup():
            while True:
                try:
                    self._cleanup_expired()
                    time.sleep(3600)  # Run cleanup every hour
                except Exception as e:
                    print(f"Cleanup task error: {e}")
                    time.sleep(3600)

        import threading

        cleanup_thread = threading.Thread(target=cleanup, daemon=True)
        cleanup_thread.start()

    def _cleanup_expired(self):
        """Remove expired workflow states."""
        with self._lock:
            now = datetime.now()
            expired_ids = []

            for workflow_id, metadata in self._metadata.items():
                if now - metadata.updated_at > timedelta(hours=self.default_ttl_hours):
                    expired_ids.append(workflow_id)

            for workflow_id in expired_ids:
                self._store.pop(workflow_id, None)
                self._metadata.pop(workflow_id, None)
                print(f"Cleaned up expired workflow: {workflow_id}")

    def store_state(
        self, workflow_id: str, state: Dict[str, Any], metadata: WorkflowMetadata
    ) -> None:
        """Store workflow state with metadata."""
        with self._lock:
            metadata.updated_at = datetime.now()
            self._store[workflow_id] = state.copy()
            self._metadata[workflow_id] = metadata

    def get_state(self, workflow_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve workflow state."""
        with self._lock:
            return self._store.get(workflow_id)

    def get_metadata(self, workflow_id: str) -> Optional[WorkflowMetadata]:
        """Retrieve workflow metadata."""
        with self._lock:
            return self._metadata.get(workflow_id)

    def list_workflows(self) -> List[Dict[str, Any]]:
        """List all active workflows."""
        with self._lock:
            return [
                {
                    "workflow_id": workflow_id,
                    "metadata": asdict(metadata),
                    "state_size": len(str(self._store.get(workflow_id, {}))),
                }
                for workflow_id, metadata in self._metadata.items()
            ]

    def delete_workflow(self, workflow_id: str) -> bool:
        """Delete a workflow state."""
        with self._lock:
            state_existed = workflow_id in self._store
            self._store.pop(workflow_id, None)
            self._metadata.pop(workflow_id, None)
            return state_existed


class WorkflowPersistence:
    """File-based persistence for workflow state."""

    def __init__(self, storage_path: Optional[str] = None):
        self.storage_path = Path(storage_path or "data/workflows")
        self.storage_path.mkdir(parents=True, exist_ok=True)

    def save_state(
        self, workflow_id: str, state: Dict[str, Any], metadata: WorkflowMetadata
    ) -> None:
        """Save workflow state to disk."""
        try:
            workflow_file = self.storage_path / f"{workflow_id}.json"

            # Serialize messages properly
            serializable_state = self._serialize_state(state)

            data = {
                "metadata": asdict(metadata),
                "state": serializable_state,
                "saved_at": datetime.now().isoformat(),
            }

            # Atomic write with backup
            temp_file = workflow_file.with_suffix(".tmp")
            with open(temp_file, "w") as f:
                json.dump(data, f, indent=2, default=str)

            temp_file.replace(workflow_file)

        except Exception as e:
            print(f"Failed to save workflow {workflow_id}: {e}")

    def load_state(
        self, workflow_id: str
    ) -> Optional[tuple[Dict[str, Any], WorkflowMetadata]]:
        """Load workflow state from disk."""
        try:
            workflow_file = self.storage_path / f"{workflow_id}.json"

            if not workflow_file.exists():
                return None

            with open(workflow_file, "r") as f:
                data = json.load(f)

            metadata = WorkflowMetadata(**data["metadata"])
            state = self._deserialize_state(data["state"])

            return state, metadata

        except Exception as e:
            print(f"Failed to load workflow {workflow_id}: {e}")
            return None

    def _serialize_state(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Serialize state for JSON storage."""
        serialized = state.copy()

        # Handle messages serialization
        if "messages" in serialized:
            serialized_messages = []
            for msg in serialized["messages"]:
                # Handle both message objects and dictionaries
                if hasattr(msg, 'content'):
                    # It's a message object
                    serialized_messages.append({
                        "type": msg.__class__.__name__,
                        "content": msg.content,
                        "additional_kwargs": getattr(msg, "additional_kwargs", {}),
                    })
                elif isinstance(msg, dict) and "content" in msg:
                    # It's already a dictionary with content
                    serialized_messages.append(msg)
                else:
                    # Fallback for unknown message types
                    serialized_messages.append({
                        "type": "UnknownMessage",
                        "content": str(msg),
                        "additional_kwargs": {},
                    })
            
            serialized["messages"] = serialized_messages

        return serialized

    def _deserialize_state(self, serialized_state: Dict[str, Any]) -> Dict[str, Any]:
        """Deserialize state from JSON storage."""
        state = serialized_state.copy()

        # Handle messages deserialization
        if "messages" in state:
            from langchain_core.messages import AIMessage, HumanMessage

            messages = []
            for msg_data in state["messages"]:
                # Handle both dictionary and object message formats
                if isinstance(msg_data, dict):
                    msg_type = msg_data.get("type", "UnknownMessage")
                    content = msg_data.get("content", "")
                    additional_kwargs = msg_data.get("additional_kwargs", {})
                    
                    if msg_type == "AIMessage":
                        messages.append(
                            AIMessage(
                                content=content,
                                additional_kwargs=additional_kwargs,
                            )
                        )
                    elif msg_type == "HumanMessage":
                        messages.append(
                            HumanMessage(
                                content=content,
                                additional_kwargs=additional_kwargs,
                            )
                        )
                    else:
                        # For unknown message types, keep as dictionary
                        messages.append(msg_data)
                else:
                    # If it's already a message object, keep it as is
                    messages.append(msg_data)

            state["messages"] = messages

        return state


class WorkflowManager:
    """
    Manages LangGraph workflow execution with state persistence,
    error recovery, and monitoring capabilities.
    """

    def __init__(self, workflow: CompiledStateGraph, enable_persistence: bool = True):
        self.workflow = workflow
        self.state_store = WorkflowStateStore()
        self.persistence = WorkflowPersistence() if enable_persistence else None
        self._running_workflows: Dict[str, asyncio.Task] = {}
        self._interrupted_workflows: Dict[str, Dict[str, Any]] = {}

    @log_workflow_function(level=LogLevel.INFO, include_state=True, include_result=False, include_execution_time=True, log_errors=True)
    async def start_workflow(
        self, initial_state: Dict[str, Any], workflow_id: Optional[str] = None
    ) -> str:
        """
        Start a new workflow execution.

        Args:
            initial_state: Initial workflow state
            workflow_id: Optional workflow ID (generated if not provided)

        Returns:
            workflow_id: The workflow execution ID
        """
        if workflow_id is None:
            workflow_id = str(uuid.uuid4())

        metadata = WorkflowMetadata(
            workflow_id=workflow_id,
            created_at=datetime.now(),
            updated_at=datetime.now(),
            status="running",
            current_step="start",
        )

        # Update initial state with the workflow ID
        initial_state["workflow_id"] = workflow_id
        
        # Store initial state
        self.state_store.store_state(workflow_id, initial_state, metadata)

        if self.persistence:
            self.persistence.save_state(workflow_id, initial_state, metadata)

        # Start workflow execution
        task = asyncio.create_task(self._execute_workflow(workflow_id, initial_state))
        self._running_workflows[workflow_id] = task

        return workflow_id

    @log_workflow_function(level=LogLevel.INFO, include_state=True, include_result=False, include_execution_time=True, log_errors=True)
    async def _execute_workflow(self, workflow_id: str, initial_state: Dict[str, Any]):
        """Execute workflow with error handling and state tracking."""
        start_time = time.time()

        try:
            metadata = self.state_store.get_metadata(workflow_id)
            if not metadata:
                raise ValueError(f"Workflow metadata not found: {workflow_id}")

            # Create configurable dict with thread_id for LangGraph checkpointer
            config = {"configurable": {"thread_id": workflow_id}}

            # Stream workflow execution with config
            async for event in self.workflow.astream(initial_state, config=config):
                # Handle different event formats from LangGraph
                if isinstance(event, dict):
                    # Check for interrupts - LangGraph creates __interrupt__ key
                    if "__interrupt__" in event:
                        # Workflow is interrupted, store interrupt data
                        interrupt_data = event["__interrupt__"]
                        
                        # Get the actual state from the most recent non-interrupt event
                        # or from the workflow's current state
                        try:
                            current_state_info = self.workflow.get_state(config)
                            current_state = current_state_info.values if hasattr(current_state_info, 'values') else event
                        except:
                            current_state = event
                        
                        self._interrupted_workflows[workflow_id] = {
                            "interrupt_data": interrupt_data,
                            "state": current_state,
                            "timestamp": datetime.now(),
                        }
                        
                        metadata.status = "paused"
                        metadata.current_step = current_state.get("current_step", "human_approval")
                        metadata.execution_time = time.time() - start_time
                        
                        # Store interrupted state
                        self.state_store.store_state(workflow_id, current_state, metadata)
                        
                        if self.persistence:
                            self.persistence.save_state(workflow_id, current_state, metadata)
                        
                        # Remove from running workflows since it's now paused
                        self._running_workflows.pop(workflow_id, None)
                        return
                    
                    # Regular state update
                    current_state = event
                else:
                    current_state = event

                # Update metadata
                metadata.current_step = current_state.get("current_step", "unknown")
                metadata.execution_time = time.time() - start_time

                # Store updated state
                self.state_store.store_state(workflow_id, current_state, metadata)

                # Persist periodically
                if (
                    self.persistence and metadata.execution_time % 30 < 1
                ):  # Every ~30 seconds
                    self.persistence.save_state(workflow_id, current_state, metadata)

                # Check if workflow is complete
                if current_state.get("workflow_complete", False):
                    metadata.status = "completed"
                    break

                # Check for errors (but not if workflow is paused)
                if current_state.get("error") and not current_state.get("workflow_paused"):
                    metadata.error_count += 1
                    metadata.last_error = current_state["error"]
                    metadata.status = "failed"
                    break

            # Final state save
            final_state = self.state_store.get_state(workflow_id)
            if final_state and self.persistence:
                self.persistence.save_state(workflow_id, final_state, metadata)

        except Exception as e:
            # Handle execution errors
            metadata = self.state_store.get_metadata(workflow_id)
            if metadata:
                # Check if workflow is paused - don't mark as failed if paused
                current_state = self.state_store.get_state(workflow_id)
                if current_state and current_state.get("workflow_paused"):
                    metadata.status = "paused"
                else:
                    metadata.status = "failed"
                    metadata.error_count += 1
                    metadata.last_error = str(e)
                    
                    # Try to save error state
                    error_state = initial_state.copy()
                    error_state["error"] = str(e)
                    error_state["current_step"] = "error"

                    self.state_store.store_state(workflow_id, error_state, metadata)

                    if self.persistence:
                        self.persistence.save_state(workflow_id, error_state, metadata)
                
                metadata.execution_time = time.time() - start_time

        finally:
            # Clean up running workflow tracking
            self._running_workflows.pop(workflow_id, None)

    @log_workflow_function(level=LogLevel.INFO, include_state=True, include_result=False, include_execution_time=True, log_errors=True)
    async def resume_workflow_with_approval(self, workflow_id: str, approval_decision: Dict[str, Any]) -> bool:
        """
        Resume a workflow that was interrupted for human approval.

        Args:
            workflow_id: The workflow ID to resume
            approval_decision: The approval decision from the user

        Returns:
            bool: True if successfully resumed, False otherwise
        """
        if workflow_id not in self._interrupted_workflows:
            return False

        interrupt_info = self._interrupted_workflows[workflow_id]
        
        # For LangGraph interrupts, we simply pass the approval decision as the resume value
        # The interrupt() function in the workflow will receive this value directly
        resume_command = Command(resume=approval_decision)
        
        # Resume workflow execution
        task = asyncio.create_task(self._resume_workflow(workflow_id, resume_command))
        self._running_workflows[workflow_id] = task
        
        # Remove from interrupted workflows
        self._interrupted_workflows.pop(workflow_id, None)
        
        return True

    @log_workflow_function(level=LogLevel.INFO, include_state=True, include_result=False, include_execution_time=True, log_errors=True)
    async def _resume_workflow(self, workflow_id: str, resume_command: Command):
        """Resume workflow execution from an interrupt."""
        start_time = time.time()
        
        try:
            metadata = self.state_store.get_metadata(workflow_id)
            if not metadata:
                raise ValueError(f"Workflow metadata not found: {workflow_id}")

            metadata.status = "running"
            metadata.updated_at = datetime.now()

            # Create configurable dict with thread_id for LangGraph checkpointer
            config = {"configurable": {"thread_id": workflow_id}}

            # Resume workflow execution with config
            async for event in self.workflow.astream(resume_command, config=config):
                # Handle different event formats from LangGraph
                if isinstance(event, dict):
                    # Check for interrupts again
                    if "__interrupt__" in event:
                        # Workflow is interrupted again
                        interrupt_data = event["__interrupt__"]
                        
                        # Get the actual state from the workflow
                        try:
                            current_state_info = self.workflow.get_state(config)
                            current_state = current_state_info.values if hasattr(current_state_info, 'values') else event
                        except:
                            current_state = event
                        
                        self._interrupted_workflows[workflow_id] = {
                            "interrupt_data": interrupt_data,
                            "state": current_state,
                            "timestamp": datetime.now(),
                        }
                        
                        metadata.status = "paused"
                        metadata.current_step = current_state.get("current_step", "unknown")
                        metadata.execution_time = time.time() - start_time
                        
                        # Store interrupted state
                        self.state_store.store_state(workflow_id, current_state, metadata)
                        
                        if self.persistence:
                            self.persistence.save_state(workflow_id, current_state, metadata)
                        
                        # Remove from running workflows since it's now paused
                        self._running_workflows.pop(workflow_id, None)
                        return
                    
                    # Regular state update
                    current_state = event
                else:
                    current_state = event

                # Update metadata
                metadata.current_step = current_state.get("current_step", "unknown")
                metadata.execution_time = time.time() - start_time

                # Store updated state
                self.state_store.store_state(workflow_id, current_state, metadata)

                # Persist periodically
                if (
                    self.persistence and metadata.execution_time % 30 < 1
                ):  # Every ~30 seconds
                    self.persistence.save_state(workflow_id, current_state, metadata)

                # Check if workflow is complete
                if current_state.get("workflow_complete", False):
                    metadata.status = "completed"
                    break

                # Check for errors
                if current_state.get("error"):
                    metadata.error_count += 1
                    metadata.last_error = current_state["error"]
                    metadata.status = "failed"
                    break

            # Final state save
            final_state = self.state_store.get_state(workflow_id)
            if final_state and self.persistence:
                self.persistence.save_state(workflow_id, final_state, metadata)

        except Exception as e:
            # Handle execution errors
            metadata = self.state_store.get_metadata(workflow_id)
            if metadata:
                metadata.status = "failed"
                metadata.error_count += 1
                metadata.last_error = str(e)
                metadata.execution_time = time.time() - start_time

        finally:
            # Clean up running workflow tracking
            self._running_workflows.pop(workflow_id, None)

    @log_workflow_function(level=LogLevel.INFO, include_state=True, include_result=False, include_execution_time=True, log_errors=True)
    async def resume_workflow(self, workflow_id: str) -> bool:
        """
        Resume a paused or failed workflow (legacy method for backward compatibility).

        Args:
            workflow_id: The workflow ID to resume

        Returns:
            bool: True if successfully resumed, False otherwise
        """
        # Try to load from persistence first
        if self.persistence:
            loaded_data = self.persistence.load_state(workflow_id)
            if loaded_data:
                state, metadata = loaded_data
                metadata.status = "running"
                metadata.updated_at = datetime.now()
                self.state_store.store_state(workflow_id, state, metadata)

        # Get current state
        current_state = self.state_store.get_state(workflow_id)
        metadata = self.state_store.get_metadata(workflow_id)

        if not current_state or not metadata:
            return False

        if workflow_id in self._running_workflows:
            return False  # Already running

        # Resume execution
        task = asyncio.create_task(self._execute_workflow(workflow_id, current_state))
        self._running_workflows[workflow_id] = task

        return True

    @log_workflow_function(level=LogLevel.INFO, include_state=True, include_result=False, include_execution_time=True, log_errors=True)
    async def pause_workflow(self, workflow_id: str) -> bool:
        """
        Pause a running workflow.

        Args:
            workflow_id: The workflow ID to pause

        Returns:
            bool: True if successfully paused, False otherwise
        """
        if workflow_id not in self._running_workflows:
            return False

        task = self._running_workflows[workflow_id]
        task.cancel()

        metadata = self.state_store.get_metadata(workflow_id)
        if metadata:
            metadata.status = "paused"
            metadata.updated_at = datetime.now()

        return True

    @log_workflow_function(level=LogLevel.INFO, include_state=True, include_result=False, include_execution_time=True, log_errors=True)
    async def cancel_workflow(self, workflow_id: str) -> bool:
        """
        Cancel a running workflow.

        Args:
            workflow_id: The workflow ID to cancel

        Returns:
            bool: True if successfully cancelled, False otherwise
        """
        if workflow_id in self._running_workflows:
            task = self._running_workflows[workflow_id]
            task.cancel()

        metadata = self.state_store.get_metadata(workflow_id)
        if metadata:
            metadata.status = "cancelled"
            metadata.updated_at = datetime.now()

        return True

    def get_workflow_status(self, workflow_id: str) -> Optional[Dict[str, Any]]:
        """
        Get current workflow status and state.

        Args:
            workflow_id: The workflow ID

        Returns:
            Dict containing status information or None if not found
        """
        state = self.state_store.get_state(workflow_id)
        metadata = self.state_store.get_metadata(workflow_id)

        if not metadata:
            return None

        return {
            "workflow_id": workflow_id,
            "metadata": asdict(metadata),
            "state": state,
            "is_running": workflow_id in self._running_workflows,
        }

    def list_workflows(self) -> List[Dict[str, Any]]:
        """List all workflows with their status."""
        workflows = self.state_store.list_workflows()

        # Add running status
        for workflow in workflows:
            workflow["is_running"] = workflow["workflow_id"] in self._running_workflows

        return workflows

    @log_workflow_function(level=LogLevel.INFO, include_state=True, include_result=False, include_execution_time=True, log_errors=True)
    async def get_workflow_stream(self, workflow_id: str):
        """
        Get real-time stream of workflow state updates.

        Args:
            workflow_id: The workflow ID

        Yields:
            Dict: Current workflow state
        """
        last_update = datetime.min

        while True:
            metadata = self.state_store.get_metadata(workflow_id)

            if not metadata:
                break

            if metadata.updated_at > last_update:
                state = self.state_store.get_state(workflow_id)
                if state:
                    yield {
                        "workflow_id": workflow_id,
                        "metadata": asdict(metadata),
                        "state": state,
                        "timestamp": metadata.updated_at.isoformat(),
                    }
                    last_update = metadata.updated_at

            if metadata.status in ["completed", "failed", "cancelled"]:
                break

            await asyncio.sleep(0.5)  # Poll every 500ms

    def get_interrupted_workflows(self) -> List[Dict[str, Any]]:
        """Get list of workflows that are currently interrupted."""
        return [
            {
                "workflow_id": workflow_id,
                "interrupt_data": info["interrupt_data"],
                "timestamp": info["timestamp"].isoformat(),
                "state": info["state"],
            }
            for workflow_id, info in self._interrupted_workflows.items()
        ]

    def is_workflow_interrupted(self, workflow_id: str) -> bool:
        """Check if a workflow is currently interrupted."""
        return workflow_id in self._interrupted_workflows

    def get_interrupt_data(self, workflow_id: str) -> Optional[Dict[str, Any]]:
        """Get interrupt data for a specific workflow."""
        if workflow_id in self._interrupted_workflows:
            return self._interrupted_workflows[workflow_id]["interrupt_data"]
        return None


# Global workflow manager instance
_workflow_manager: Optional[WorkflowManager] = None


def get_workflow_manager() -> WorkflowManager:
    """Get global workflow manager instance."""
    global _workflow_manager
    if _workflow_manager is None:
        from .release_workflow import create_release_workflow

        workflow = create_release_workflow()
        _workflow_manager = WorkflowManager(workflow)
    return _workflow_manager
