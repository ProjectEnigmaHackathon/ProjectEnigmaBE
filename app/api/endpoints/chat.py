"""
Chat Endpoints

Chat interface for interacting with the release automation workflow.
Provides message handling, workflow state management, and streaming responses.
"""

import asyncio
import json
import uuid
from typing import AsyncGenerator, Dict, List, Optional
from datetime import datetime

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, HumanMessage
from pydantic import ValidationError

from app.models.api import (
    ChatRequest,
    ChatResponse,
    WorkflowStatus,

    ErrorResponse,
)
from app.workflows.workflow_manager import get_workflow_manager
from app.workflows.release_workflow import extract_workflow_params
from app.workflows.orchestrator import get_orchestrator
from app.workflows.workflow_registry import get_workflow_manager_by_type, get_workflow_manager_by_id
from app.core.logging_utils import log_api_endpoint, LogLevel

router = APIRouter()


def create_initial_workflow_state(request: ChatRequest, workflow_type: str) -> Dict[str, any]:
    """Create initial workflow state from chat request."""
    
    if workflow_type == "release":
        # Extract workflow parameters for release workflow
        params = extract_workflow_params(request)
        
        # Create initial state matching Release WorkflowState TypedDict
        initial_state = {
            # Workflow type identification
            "workflow_type": workflow_type,
            
            # Core workflow data
            "messages": [HumanMessage(content=request.message)],
            "repositories": params["repositories"],
            "fix_version": params["fix_version"],
            "sprint_name": params["sprint_name"],
            "release_type": params["release_type"],
            
            # Execution tracking
            "current_step": "start",
            "workflow_complete": False,
            "workflow_id": str(uuid.uuid4()),
            "workflow_paused": False,
            
            # Step results (initialize empty)
            "jira_tickets": [],
            "feature_branches": {},
            "merge_status": {},
            "pull_requests": [],
            "release_branches": [],
            "rollback_branches": [],
            "confluence_url": "",
            
            # Error handling and recovery
            "error": "",
            "error_step": "",
            "retry_count": 0,
            "can_continue": True,
            
            # Progress tracking
            "steps_completed": [],
            "steps_failed": [],
        }
    else:  # qa workflow
        # Create initial state for QA workflow
        initial_state = {
            # Workflow type identification
            "workflow_type": workflow_type,
            
            # Core data
            "messages": [HumanMessage(content=request.message)],
            "repositories": request.repositories or [],
            
            # Execution tracking
            "workflow_id": str(uuid.uuid4()),
            "current_step": "start",
            "workflow_complete": False,
            "workflow_paused": False,
            
            # Error handling
            "error": "",
            "can_continue": True,
        }
    
    return initial_state


def map_workflow_status(workflow_status: str) -> WorkflowStatus:
    """Map workflow manager status to API WorkflowStatus enum."""
    status_mapping = {
        "running": WorkflowStatus.IN_PROGRESS,
        "paused": WorkflowStatus.AWAITING_APPROVAL,  # Changed from PENDING to AWAITING_APPROVAL
        "completed": WorkflowStatus.COMPLETED,
        "failed": WorkflowStatus.FAILED,
        "cancelled": WorkflowStatus.CANCELLED,
    }
    return status_mapping.get(workflow_status, WorkflowStatus.PENDING)


def format_workflow_messages(messages: List) -> List[Dict[str, any]]:
    """Format workflow messages for API response."""
    formatted_messages = []
    
    for msg in messages:
        if hasattr(msg, 'content'):
            # It's a message object
            formatted_messages.append({
                "type": msg.__class__.__name__,
                "content": msg.content,
                "timestamp": getattr(msg, 'timestamp', None),
            })
        elif isinstance(msg, dict) and "content" in msg:
            # It's already a dictionary with content
            formatted_messages.append({
                "type": msg.get("type", "UnknownMessage"),
                "content": msg.get("content", ""),
                "timestamp": msg.get("timestamp", None),
            })
        else:
            # Fallback for unknown message types
            formatted_messages.append({
                "type": "UnknownMessage",
                "content": str(msg),
                "timestamp": None,
            })
    
    return formatted_messages


@router.post("/", response_model=ChatResponse)
@log_api_endpoint(level=LogLevel.INFO, include_request=True, include_response=False, include_execution_time=True, log_errors=True)
async def send_message(request: ChatRequest):
    """
    Send a chat message and start/continue workflow execution.
    
    This endpoint handles both new workflow starts and continuation of existing workflows.
    Uses LLM orchestrator to decide between QA and Release workflows.
    """
    try:
        # Check if this is a continuation of an existing workflow
        if request.session_id:
            # Try to find existing workflow across all managers
            workflow_manager = get_workflow_manager_by_id(request.session_id)
            if workflow_manager:
                # Resume existing workflow
                success = await workflow_manager.resume_workflow(request.session_id)
                if not success:
                    raise HTTPException(
                        status_code=400,
                        detail="Failed to resume workflow. It may be completed or invalid."
                    )
                
                workflow_id = request.session_id
            else:
                # Session ID provided but workflow not found, start new
                # Use orchestrator to classify workflow type
                orchestrator = get_orchestrator()
                classification = await orchestrator.classify_workflow(request.message)
                workflow_type = classification["workflow_type"]
                
                # Get appropriate workflow manager
                workflow_manager = get_workflow_manager_by_type(workflow_type)
                if not workflow_manager:
                    raise HTTPException(
                        status_code=500,
                        detail=f"Workflow manager not found for type: {workflow_type}"
                    )
                
                initial_state = create_initial_workflow_state(request, workflow_type)
                workflow_id = await workflow_manager.start_workflow(initial_state)
        else:
            # Start new workflow - use orchestrator to classify
            orchestrator = get_orchestrator()
            classification = await orchestrator.classify_workflow(request.message)
            workflow_type = classification["workflow_type"]
            
            print(f"Orchestrator classified message as: {workflow_type} (confidence: {classification.get('confidence', 'N/A')})")
            print(f"Reasoning: {classification.get('reasoning', 'N/A')}")
            
            # Get appropriate workflow manager
            workflow_manager = get_workflow_manager_by_type(workflow_type)
            if not workflow_manager:
                raise HTTPException(
                    status_code=500,
                    detail=f"Workflow manager not found for type: {workflow_type}"
                )
            
            initial_state = create_initial_workflow_state(request, workflow_type)
            workflow_id = await workflow_manager.start_workflow(initial_state)
        
        # Get current workflow status
        status_info = workflow_manager.get_workflow_status(workflow_id)
        if not status_info:
            raise HTTPException(status_code=500, detail="Failed to get workflow status")
        

        # Format response data without interrupt handling
        
        # Format response data
        response_data = {
            "workflow_id": workflow_id,
            "session_id": workflow_id,  # Use workflow_id as session_id
            "current_step": status_info["metadata"]["current_step"],
            "messages": format_workflow_messages(status_info["state"].get("messages", [])),
        }
        

        
        # Determine appropriate message based on status
        if status_info["metadata"]["status"] == "completed":
            message = "Workflow completed successfully."
            message_type = "workflow_completed"
        elif status_info["metadata"]["status"] == "failed":
            message = "Workflow failed. Check status for error details."
            message_type = "workflow_failed"
        else:
            message = "Workflow started successfully. Check status for updates."
            message_type = "workflow_started"
        
        # Format response
        response = ChatResponse(
            message=message,
            message_type=message_type,
            workflow_status=map_workflow_status(status_info["metadata"]["status"]),
            data=response_data,
            requires_approval=False,
        )
        
        return response
        
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/status/{workflow_id}")
@log_api_endpoint(level=LogLevel.INFO, include_request=True, include_response=False, include_execution_time=True, log_errors=True)
async def get_workflow_status(workflow_id: str):
    """Get current status of a workflow."""
    try:
        workflow_manager = get_workflow_manager_by_id(workflow_id)
        if not workflow_manager:
            raise HTTPException(status_code=404, detail="Workflow not found")
            
        status_info = workflow_manager.get_workflow_status(workflow_id)
        
        if not status_info:
            raise HTTPException(status_code=404, detail="Workflow not found")
        
        # # Check if workflow is interrupted
        # is_interrupted = workflow_manager.is_workflow_interrupted(workflow_id)
        # interrupt_data = None
        # if is_interrupted:
        #     interrupt_data = workflow_manager.get_interrupt_data(workflow_id)
        
        return {
            "workflow_id": workflow_id,
            "status": map_workflow_status(status_info["metadata"]["status"]),
            "current_step": status_info["metadata"]["current_step"],
            "execution_time": status_info["metadata"]["execution_time"],
            "error_count": status_info["metadata"]["error_count"],
            "last_error": status_info["metadata"]["last_error"],
            "messages": format_workflow_messages(status_info["state"].get("messages", [])),
            "is_running": status_info["is_running"],
            "is_interrupted": False,
            "requires_approval": False,
            "steps_completed": status_info["state"].get("steps_completed", []),
            "steps_failed": status_info["state"].get("steps_failed", []),
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/stream/{workflow_id}")
@log_api_endpoint(level=LogLevel.INFO, include_request=True, include_response=False, include_execution_time=True, log_errors=True)
async def stream_workflow_updates(workflow_id: str):
    """
    Stream real-time workflow updates.
    
    Returns a Server-Sent Events stream of workflow state changes.
    """
    async def generate_stream() -> AsyncGenerator[str, None]:
        workflow_manager = get_workflow_manager_by_id(workflow_id)
        if not workflow_manager:
            error_data = {"error": f"Workflow not found: {workflow_id}"}
            yield f"data: {json.dumps(error_data)}\n\n"
            return
        
        try:
            async for update in workflow_manager.get_workflow_stream(workflow_id):
                # Check if workflow is interrupted
                # is_interrupted = workflow_manager.is_workflow_interrupted(workflow_id)
                # interrupt_data = None
                # if is_interrupted:
                #     interrupt_data = workflow_manager.get_interrupt_data(workflow_id)
                
                # Format the update for SSE
                sse_data = {
                    "workflow_id": update["workflow_id"],
                    "status": map_workflow_status(update["metadata"]["status"]),
                    "current_step": update["metadata"]["current_step"],
                    "execution_time": update["metadata"]["execution_time"],
                    "messages": format_workflow_messages(update["state"].get("messages", [])),
                    "is_interrupted": False,
                    "requires_approval": False,
                    "timestamp": update["timestamp"],
                }
                
                yield f"data: {json.dumps(sse_data)}\n\n"
                
                # Check if workflow is complete
                if update["metadata"]["status"] in ["completed", "failed", "cancelled"]:
                    break
                    
        except Exception as e:
            error_data = {"error": str(e)}
            yield f"data: {json.dumps(error_data)}\n\n"
    
    return StreamingResponse(
        generate_stream(),
        media_type="text/plain",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Content-Type": "text/event-stream",
        }
    )


@router.websocket("/ws/{workflow_id}")
@log_api_endpoint(level=LogLevel.INFO, include_request=True, include_response=False, include_execution_time=True, log_errors=True)
async def websocket_workflow_updates(websocket: WebSocket, workflow_id: str):
    """WebSocket endpoint for real-time workflow updates."""
    await websocket.accept()
    
    try:
        workflow_manager = get_workflow_manager_by_id(workflow_id)
        if not workflow_manager:
            error_data = {"error": f"Workflow not found: {workflow_id}"}
            await websocket.send_text(json.dumps(error_data))
            return
        
        async for update in workflow_manager.get_workflow_stream(workflow_id):
            # # Check if workflow is interrupted
            # is_interrupted = workflow_manager.is_workflow_interrupted(workflow_id)
            # interrupt_data = None
            # if is_interrupted:
            #     interrupt_data = workflow_manager.get_interrupt_data(workflow_id)
            
            # Format the update for WebSocket
            ws_data = {
                "workflow_id": update["workflow_id"],
                "status": map_workflow_status(update["metadata"]["status"]),
                "current_step": update["metadata"]["current_step"],
                "execution_time": update["metadata"]["execution_time"],
                "messages": format_workflow_messages(update["state"].get("messages", [])),
                "is_interrupted": False,
                "requires_approval": False,
                "timestamp": update["timestamp"],
            }
            
            await websocket.send_text(json.dumps(ws_data))
            
            # Check if workflow is complete
            if update["metadata"]["status"] in ["completed", "failed", "cancelled"]:
                break
                
    except WebSocketDisconnect:
        print(f"WebSocket disconnected for workflow {workflow_id}")
    except Exception as e:
        error_data = {"error": str(e)}
        await websocket.send_text(json.dumps(error_data))











@router.post("/pause/{workflow_id}")
@log_api_endpoint(level=LogLevel.INFO, include_request=True, include_response=False, include_execution_time=True, log_errors=True)
async def pause_workflow(workflow_id: str):
    """Pause a running workflow."""
    try:
        workflow_manager = get_workflow_manager_by_id(workflow_id)
        if not workflow_manager:
            raise HTTPException(status_code=404, detail="Workflow not found")
        success = await workflow_manager.pause_workflow(workflow_id)
        
        if not success:
            raise HTTPException(
                status_code=400, 
                detail="Workflow is not running or cannot be paused"
            )
        
        return {"message": "Workflow paused successfully", "workflow_id": workflow_id}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("/cancel/{workflow_id}")
@log_api_endpoint(level=LogLevel.INFO, include_request=True, include_response=False, include_execution_time=True, log_errors=True)
async def cancel_workflow(workflow_id: str):
    """Cancel a workflow."""
    try:
        workflow_manager = get_workflow_manager_by_id(workflow_id)
        if not workflow_manager:
            raise HTTPException(status_code=404, detail="Workflow not found")
        success = await workflow_manager.cancel_workflow(workflow_id)
        
        if not success:
            raise HTTPException(
                status_code=400, 
                detail="Workflow cannot be cancelled"
            )
        
        return {"message": "Workflow cancelled successfully", "workflow_id": workflow_id}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/list")
@log_api_endpoint(level=LogLevel.INFO, include_request=True, include_response=False, include_execution_time=True, log_errors=True)
async def list_workflows():
    """List all active workflows from all workflow types."""
    try:
        from app.workflows.workflow_registry import get_workflow_registry
        registry = get_workflow_registry()
        all_workflows = registry.get_all_workflows()
        
        # Flatten workflows from all types
        workflows = []
        for workflow_type, type_workflows in all_workflows.items():
            for workflow in type_workflows:
                workflow["workflow_type"] = workflow_type
                workflows.append(workflow)
        
        return {
            "workflows": workflows,
            "total": len(workflows),
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.delete("/{workflow_id}")
@log_api_endpoint(level=LogLevel.INFO, include_request=True, include_response=False, include_execution_time=True, log_errors=True)
async def delete_workflow(workflow_id: str):
    """Delete a workflow and its associated data."""
    try:
        workflow_manager = get_workflow_manager_by_id(workflow_id)
        if not workflow_manager:
            raise HTTPException(status_code=404, detail="Workflow not found")
            
        success = workflow_manager.state_store.delete_workflow(workflow_id)
        
        if not success:
            raise HTTPException(status_code=404, detail="Workflow not found")
        
        return {"message": "Workflow deleted successfully", "workflow_id": workflow_id}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")