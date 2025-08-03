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
from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect, status, BackgroundTasks
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, HumanMessage
from pydantic import ValidationError
import structlog

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

logger = structlog.get_logger()
router = APIRouter()

# Constants for logging
APPLICATION_NAME = "ProjectEnigmaBE"
filename = __file__.split('/')[-1]


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


def extract_messages_from_state(state: Dict[str, any]) -> List:
    """Extract messages from workflow state, handling both flat and channel-based structures."""
    messages = []
    
    # Check if we have channel-based data (accumulated state with chatbot/tools channels)
    has_channels = any(channel in state for channel in ['chatbot', 'tools', 'agent'])
    
    if has_channels:
        # Handle LangGraph channel-based structure (e.g., QA workflow)
        # For accumulated state, we need to collect messages from all channels in chronological order
        
        # First, include any initial flat messages (from the original workflow state)
        if "messages" in state and isinstance(state["messages"], list):
            messages.extend(state["messages"])
        
        # Then, collect all messages from channels
        all_channel_messages = []
        channels_to_check = ['chatbot', 'tools', 'start', 'agent']
        
        for channel in channels_to_check:
            if channel in state and isinstance(state[channel], dict):
                channel_data = state[channel]
                if "messages" in channel_data:
                    if isinstance(channel_data["messages"], list):
                        for msg in channel_data["messages"]:
                            all_channel_messages.append((channel, msg))
                    elif hasattr(channel_data["messages"], 'content'):
                        # Single message object
                        all_channel_messages.append((channel, channel_data["messages"]))
        
        # For QA workflow, we want to reconstruct the conversation flow:
        # 1. Initial human message (from flat messages or chatbot channel)
        # 2. AI message with tool calls (from chatbot channel)  
        # 3. Tool response (from tools channel)
        # 4. Final AI response (from chatbot channel)
        
        # Sort messages to maintain conversation flow
        # Human messages first, then AI messages with tool calls, then tool messages, then final AI messages
        def message_sort_key(channel_msg_tuple):
            channel, msg = channel_msg_tuple
            msg_type = msg.__class__.__name__ if hasattr(msg, '__class__') else 'Unknown'
            
            # Priority order for conversation flow
            if msg_type == 'HumanMessage':
                return (0, 0)  # Human messages first
            elif msg_type == 'AIMessage':
                # Check if it has tool calls
                has_tool_calls = (
                    (hasattr(msg, 'tool_calls') and msg.tool_calls) or
                    (hasattr(msg, 'additional_kwargs') and 
                     msg.additional_kwargs.get('tool_calls'))
                )
                if has_tool_calls:
                    return (1, 0)  # AI messages with tool calls
                else:
                    return (3, 0)  # Final AI messages
            elif msg_type == 'ToolMessage':
                return (2, 0)  # Tool responses
            else:
                return (4, 0)  # Other messages last
        
        # Sort and extract just the messages from channels
        if all_channel_messages:
            sorted_messages = sorted(all_channel_messages, key=message_sort_key)
            channel_messages = [msg for channel, msg in sorted_messages]
            
            # Add channel messages, avoiding duplicates with initial flat messages
            for msg in channel_messages:
                if msg not in messages:
                    messages.append(msg)
        
        return messages
    else:
        # Handle flat structure (e.g., release workflow) - no channels detected
        if "messages" in state and isinstance(state["messages"], list):
            return state["messages"]
        
        # If no messages found anywhere, try to find any message-like objects
        for key, value in state.items():
            if hasattr(value, 'content') or (isinstance(value, dict) and "content" in value):
                messages.append(value)
        
        return messages


def format_workflow_messages(state_or_messages) -> List[Dict[str, any]]:
    """Format workflow messages for API response."""
    # If it's a state dict, extract messages first
    if isinstance(state_or_messages, dict):
        messages = extract_messages_from_state(state_or_messages)
    else:
        messages = state_or_messages if isinstance(state_or_messages, list) else []
    
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
            "messages": format_workflow_messages(status_info["state"]),
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
            "messages": format_workflow_messages(status_info["state"]),
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
async def stream_workflow_updates(workflow_id: str, request: Request):
    """
    Stream real-time AI message content from workflow updates.
    
    Returns a Server-Sent Events stream containing only AI message content
    with timestamps, filtering out all other workflow data.
    """
    # Simple state tracking
    class StreamState:
        def __init__(self):
            self.full_content = ""
            self.last_status = "running"
    
    state = StreamState()
    background_tasks = BackgroundTasks()
    
    # Background task for cleanup/logging
    async def cleanup_stream(completed=False, error=None):
        try:
            await logger.ainfo({
                "message": f"Workflow stream ended: {workflow_id}",
                "status": "completed" if completed else "disconnected",
                "content_length": len(state.full_content),
                "final_status": state.last_status,
                "error": str(error) if error else None,
                "appName": APPLICATION_NAME,
                "fileName": filename,
                "methodName": "cleanup_stream",
            })
        except Exception as cleanup_error:
            await logger.aerror({
                "message": f"Error in stream cleanup: {str(cleanup_error)}",
                "appName": APPLICATION_NAME,
                "fileName": filename,
                "methodName": "cleanup_stream",
            }, cleanup_error)
    
    async def generate_stream() -> AsyncGenerator[str, None]:
        workflow_manager = get_workflow_manager_by_id(workflow_id)
        if not workflow_manager:
            error_msg = f"Workflow not found: {workflow_id}"
            yield f"Error: {error_msg}\n\n"
            await cleanup_stream(True, Exception(error_msg))
            return
        
        try:
            async for update in workflow_manager.get_workflow_stream(workflow_id):
                # Check for client disconnection
                if await request.is_disconnected():
                    disconnect_error = Exception("Client disconnected during streaming")
                    await cleanup_stream(False, disconnect_error)
                    break
                
                # Update status tracking
                current_status = update["metadata"]["status"]
                state.last_status = current_status
                
                # Extract and filter AI messages only
                messages = format_workflow_messages(update["state"])
                ai_messages = [msg for msg in messages if msg.get("type") == "AIMessage"]
                
                # Stream only AI message content as raw text
                for ai_msg in ai_messages:
                    content = ai_msg.get("content", "")
                    if content.strip():  # Only send non-empty content
                        state.full_content += content
                        yield f"{content}"
                
                # Check if workflow is complete
                if current_status in ["completed", "failed", "cancelled"]:
                    await cleanup_stream(True, None)
                    break
                    
        except asyncio.CancelledError:
            # Handle client disconnection via cancellation
            cancel_error = Exception("Client disconnected (cancelled) before completion")
            await cleanup_stream(False, cancel_error)
            raise
            
        except Exception as e:
            await cleanup_stream(True, e)
            yield f"Error: {str(e)}\n\n"
    
    # Add cleanup task to background
    background_tasks.add_task(cleanup_stream, False, None)
    
    return StreamingResponse(
        generate_stream(),
        media_type="text/plain; charset=utf-8",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Content-Type-Options": "nosniff",
        },
        status_code=status.HTTP_200_OK,
        background=background_tasks,
    )


@router.get("/stream-sse/{workflow_id}")
@log_api_endpoint(level=LogLevel.INFO, include_request=True, include_response=False, include_execution_time=True, log_errors=True)
async def stream_workflow_updates_sse(workflow_id: str, request: Request):
    """
    Stream real-time AI message content using Server-Sent Events format.
    
    This endpoint provides proper SSE formatting for better browser and Postman support.
    Use this endpoint when you need proper SSE event streaming.
    """
    # Simple state tracking
    class StreamState:
        def __init__(self):
            self.full_content = ""
            self.last_status = "running"
    
    state = StreamState()
    background_tasks = BackgroundTasks()
    
    # Background task for cleanup/logging
    async def cleanup_stream(completed=False, error=None):
        try:
            await logger.ainfo({
                "message": f"SSE Workflow stream ended: {workflow_id}",
                "status": "completed" if completed else "disconnected",
                "content_length": len(state.full_content),
                "final_status": state.last_status,
                "error": str(error) if error else None,
                "appName": APPLICATION_NAME,
                "fileName": filename,
                "methodName": "cleanup_stream_sse",
            })
        except Exception as cleanup_error:
            await logger.aerror({
                "message": f"Error in SSE stream cleanup: {str(cleanup_error)}",
                "appName": APPLICATION_NAME,
                "fileName": filename,
                "methodName": "cleanup_stream_sse",
            }, cleanup_error)
    
    async def generate_sse_stream() -> AsyncGenerator[str, None]:
        workflow_manager = get_workflow_manager_by_id(workflow_id)
        if not workflow_manager:
            error_msg = f"Workflow not found: {workflow_id}"
            yield f"data: {json.dumps({'error': error_msg})}\n\n"
            await cleanup_stream(True, Exception(error_msg))
            return
        
        try:
            async for update in workflow_manager.get_workflow_stream(workflow_id):
                # Check for client disconnection
                if await request.is_disconnected():
                    disconnect_error = Exception("Client disconnected during SSE streaming")
                    await cleanup_stream(False, disconnect_error)
                    break
                
                # Update status tracking
                current_status = update["metadata"]["status"]
                state.last_status = current_status
                
                # Extract and filter AI messages only
                messages = format_workflow_messages(update["state"])
                ai_messages = [msg for msg in messages if msg.get("type") == "AIMessage"]
                
                # Stream AI message content in SSE format
                for ai_msg in ai_messages:
                    content = ai_msg.get("content", "")
                    if content.strip():  # Only send non-empty content
                        state.full_content += content
                        # Proper SSE format with JSON data
                        sse_data = {
                            "content": content,
                            "workflow_id": workflow_id,
                            "status": current_status,
                            "timestamp": datetime.now().isoformat()
                        }
                        yield f"data: {json.dumps(sse_data)}\n\n"
                
                # Send status updates
                status_data = {
                    "type": "status",
                    "workflow_id": workflow_id,
                    "status": current_status,
                    "timestamp": datetime.now().isoformat()
                }
                yield f"data: {json.dumps(status_data)}\n\n"
                
                # Check if workflow is complete
                if current_status in ["completed", "failed", "cancelled"]:
                    await cleanup_stream(True, None)
                    # Send completion event
                    completion_data = {
                        "type": "completion",
                        "workflow_id": workflow_id,
                        "status": current_status,
                        "timestamp": datetime.now().isoformat()
                    }
                    yield f"data: {json.dumps(completion_data)}\n\n"
                    break
                    
        except asyncio.CancelledError:
            # Handle client disconnection via cancellation
            cancel_error = Exception("Client disconnected (cancelled) before SSE completion")
            await cleanup_stream(False, cancel_error)
            raise
            
        except Exception as e:
            await cleanup_stream(True, e)
            error_data = {"error": str(e), "timestamp": datetime.now().isoformat()}
            yield f"data: {json.dumps(error_data)}\n\n"
    
    # Add cleanup task to background
    background_tasks.add_task(cleanup_stream, False, None)
    
    return StreamingResponse(
        generate_sse_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
        status_code=status.HTTP_200_OK,
        background=background_tasks,
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
                "messages": format_workflow_messages(update["state"]),
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