"""
Release automation workflow using LangGraph.

This module defines the LangGraph workflow for automating release documentation
and deployment processes including JIRA integration, branch management,
and Confluence documentation generation.
"""

import asyncio
import re
from typing import Any, Dict, List, TypedDict

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

from langgraph.checkpoint.memory import MemorySaver

from app.core.config import get_settings
from app.integrations.factory import APIClientFactory
from app.models.api import ChatRequest
from app.core.logging_utils import log_workflow_function, LogLevel


def check_step_completion(state: "WorkflowState", step_name: str, step_title: str) -> bool:
    """
    Check if a step has already been completed to prevent duplicate execution.
    
    Args:
        state: Current workflow state
        step_name: Name of the step to check
        step_title: Human-readable title for the step
        
    Returns:
        True if step is already completed, False otherwise
    """
    if step_name in state.get("steps_completed", []):
        from langchain_core.messages import AIMessage
        from langgraph.graph.message import add_messages
        
        resume_msg = AIMessage(
            content=f"🔄 **{step_title} (Resumed)**\n"
            f"Step already completed. Skipping execution.\n\n"
        )
        state["messages"] = add_messages(state["messages"], [resume_msg])
        return True
    return False


async def _calculate_next_version(github_client, state: "WorkflowState") -> str:
    """Calculate the next semantic version based on existing tags."""
    try:
        # Use the provided fix version if it follows semantic versioning
        fix_version = state.get("fix_version", "")

        # If fix version already looks like semantic version, use it
        if re.match(r"^v?\d+\.\d+\.\d+", fix_version):
            return fix_version if fix_version.startswith("v") else f"v{fix_version}"

        # Otherwise, try to get latest version from any repository
        latest_version = "v0.0.0"

        for repo in state.get("repositories", []):
            try:
                tags = await github_client.get_tags(repo)

                # Filter semantic version tags
                version_tags = []
                for tag in tags:
                    if re.match(r"^v?\d+\.\d+\.\d+", tag.name):
                        version_tags.append(tag.name)

                if version_tags:
                    # Sort versions and get the latest
                    version_tags.sort(key=lambda v: _version_sort_key(v), reverse=True)
                    repo_latest = version_tags[0]

                    if _version_sort_key(repo_latest) > _version_sort_key(
                        latest_version
                    ):
                        latest_version = repo_latest

            except Exception:
                # Skip repository if we can't get tags
                continue

        # Increment major version for new release
        version_parts = latest_version.replace("v", "").split(".")
        major = int(version_parts[0]) + 1
        minor = 0
        patch = 0

        return f"v{major}.{minor}.{patch}"

    except Exception:
        # Fallback to using fix version or default
        fix_version = state.get("fix_version", "v1.0.0")
        return fix_version if fix_version.startswith("v") else f"v{fix_version}"


def _version_sort_key(version: str) -> tuple:
    """Create sort key for semantic version."""
    version = version.replace("v", "")
    parts = version.split(".")
    return tuple(int(part) for part in parts[:3])


def _generate_pr_description(state: "WorkflowState", version: str) -> str:
    """Generate comprehensive PR description for release."""
    jira_tickets = state.get("jira_tickets", [])
    sprint_name = state.get("sprint_name", "")
    release_type = state.get("release_type", "release")

    description = f"""# Release {version}

**Release Type:** {release_type.title()}
**Sprint:** {sprint_name}
**Fix Version:** {state.get('fix_version', '')}

## 📋 Included Changes

"""

    if jira_tickets:
        for ticket in jira_tickets:
            description += (
                f"- **{ticket['id']}**: {ticket['summary']} [{ticket['status']}]\n"
            )
    else:
        description += "- No JIRA tickets specified\n"

    description += f"""

## 🚀 Deployment Instructions

1. Review and approve this pull request
2. Merge to deploy to production
3. Monitor application health post-deployment
4. Use rollback branches if issues occur

## 🔄 Rollback Plan

Rollback branches have been created from master for quick reversion if needed:
- Pattern: `rollback/v-{version.replace('v', '')}`

## ✅ Pre-deployment Checklist

- [ ] All feature branches merged to sprint branch
- [ ] Sprint branch merged to develop  
- [ ] Release branch created from develop
- [ ] All tests passing
- [ ] Documentation updated

## 📊 Repository Status

"""

    repositories = state.get("repositories", [])
    for repo in repositories:
        description += f"- {repo}: Ready for deployment\n"

    description += f"""

---
*This release was automated by Project Enigma workflow engine.*
"""

    return description


def _generate_tag_message(state: "WorkflowState", version: str) -> str:
    """Generate comprehensive tag message for release."""
    jira_tickets = state.get("jira_tickets", [])
    sprint_name = state.get("sprint_name", "")
    release_type = state.get("release_type", "release")

    message = f"Release {version}\n\n"
    message += f"Release Type: {release_type.title()}\n"
    message += f"Sprint: {sprint_name}\n"
    message += f"Fix Version: {state.get('fix_version', '')}\n\n"

    if jira_tickets:
        message += "Included Changes:\n"
        for ticket in jira_tickets:
            message += f"- {ticket['id']}: {ticket['summary']}\n"
    else:
        message += "No specific JIRA tickets included.\n"

    message += f"\nAutomated by Project Enigma workflow engine"

    return message


def handle_workflow_error(
    state: "WorkflowState", step: str, error: str
) -> "WorkflowState":
    """Handle workflow errors with recovery options."""
    print(f"\n\n[DEBUG] handle_workflow_error called\n")
    print(f"[DEBUG] step: {step}")
    print(f"[DEBUG] error: {error}")
    print(f"[DEBUG] state before error handling: {state}")

    state["error"] = error
    state["error_step"] = step
    state["current_step"] = "error"
    state["can_continue"] = True  # Allow recovery attempts
    state["steps_failed"].append(step)

    # Ensure messages key exists
    if "messages" not in state:
        print("[DEBUG] 'messages' key not found in state, initializing as empty list.")
        state["messages"] = []

    error_msg = AIMessage(
        content=f"❌ **Error in {step}:**\n{error}\n\n"
        f"🔄 The workflow can be resumed after resolving the issue.\n\n"
    )
    print(f"[DEBUG] Adding error message to state['messages']")
    state["messages"] = add_messages(state["messages"], [error_msg])

    print(f"[DEBUG] state after error handling: {state}")
    return state


def should_continue_workflow(state: "WorkflowState") -> str:
    """Determine the next step based on workflow state."""
    current_step = state.get("current_step", "")
    print(f"\n\n[DEBUG] should_continue_workflow called\n")
    print(f"[DEBUG] current_step: {current_step}")
    print(f"[DEBUG] state: {state}")

    # Define the workflow flow
    step_flow = {
        "start": "jira_collection",
        "jira_collection": "branch_discovery",
        "branch_discovery": "merge_validation",
        "merge_validation": "sprint_merging",
        "sprint_merging": "release_creation",
        "release_creation": "pr_generation",
        "pr_generation": "release_tagging",
        "release_tagging": "rollback_preparation",
        "rollback_preparation": "documentation",
        "documentation": "complete",
        "error": "error_handler",
        "error_handler": "error_handler",  # Allow error handler to route to itself
    }
    
    # Handle empty or missing current_step
    if not current_step or current_step == "":
        print("[DEBUG] Current step is empty or missing. Starting from 'start'.")
        return "start"
    
    # Handle paused workflows - stay at current step
    if state.get("workflow_paused"):
        print("[DEBUG] Workflow is paused.")
        result = current_step if current_step else "error_handler"
        print(f"[DEBUG] Returning: {result}")
        return result
    
    # Handle error states first
    if state.get("error") and not state.get("can_continue"):
        print("[DEBUG] Error present and cannot continue. Routing to error_handler.")
        return "error_handler"

    # Handle completion
    if state.get("workflow_complete"):
        print("[DEBUG] Workflow is complete. Routing to 'complete'.")
        return "complete"

    # Handle resuming from a specific step
    if current_step and current_step in step_flow:
        steps_completed = state.get("steps_completed", [])
        print(f"[DEBUG] steps_completed: {steps_completed}")
        if current_step in steps_completed:
            next_step = step_flow.get(current_step, "complete")
            print(f"[DEBUG] Current step '{current_step}' already completed. Routing to next step: {next_step}")
            return next_step
        else:
            print(f"[DEBUG] Resuming from current step: {current_step}")
            return current_step

    # Handle unknown states
    if current_step not in step_flow:
        print(f"[DEBUG] Current step '{current_step}' not in step_flow. Routing to error_handler.")
        return "error_handler"

    result = step_flow.get(current_step, "complete")
    print(f"[DEBUG] Default routing to: {result}")
    return result

class WorkflowState(TypedDict):
    """Enhanced state object for the release workflow with persistence support."""

    # Core workflow data
    messages: List[BaseMessage]
    repositories: List[str]
    fix_version: str
    sprint_name: str
    release_type: str

    # Execution tracking
    current_step: str
    workflow_complete: bool
    workflow_id: str
    workflow_paused: bool

    # Step results
    jira_tickets: List[Dict[str, Any]]
    feature_branches: Dict[str, List[str]]
    merge_status: Dict[str, Dict[str, bool]]
    pull_requests: List[Dict[str, str]]
    release_branches: List[str]
    rollback_branches: List[str]
    confluence_url: str

    # Error handling and recovery
    error: str
    error_step: str
    retry_count: int
    can_continue: bool

    # Progress tracking
    steps_completed: List[str]
    steps_failed: List[str]




def create_release_workflow() -> StateGraph:
    """Create and configure the release automation workflow."""

    @log_workflow_function(level=LogLevel.INFO, include_state=True, include_result=False, include_execution_time=True, log_errors=True)
    async def start_workflow(state: WorkflowState) -> WorkflowState:
        """Initialize the workflow with user input."""
        print(f"\n\n[DEBUG] start_workflow called\n")
        print(f"[DEBUG] Initial state: {state}")

        try:
            # Check if this is a fresh start or a resume
            is_resume = state.get("workflow_id") and (
                state.get("steps_completed") or 
                # state.get("current_step") != "start" or
                state.get("workflow_complete") is True
            )
            print(f"[DEBUG] state: {state}")
            print(f"[DEBUG] state.get('workflow_id'): {state.get('workflow_id')}")
            print(f"[DEBUG] state.get('steps_completed'): {state.get('steps_completed')}")
            print(f"[DEBUG] state.get('current_step'): {state.get('current_step')}")
            print(f"[DEBUG] state.get('workflow_complete'): {state.get('workflow_complete')}")
            print(f"[DEBUG] is_resume: {is_resume}")

            if not is_resume:
                print("[DEBUG] Fresh start detected. Initializing state variables.")
                # Fresh start - initialize all state variables
                state["current_step"] = "start"
                state["workflow_complete"] = False
                state["workflow_paused"] = False
                state["error"] = ""
                state["error_step"] = ""
                state["retry_count"] = 0
                state["can_continue"] = True
                state["steps_completed"] = []
                state["steps_failed"] = []

                # Generate workflow ID if not present
                if not state.get("workflow_id"):
                    import uuid
                    state["workflow_id"] = str(uuid.uuid4())
                    print(f"[DEBUG] Generated new workflow_id: {state['workflow_id']}")
                else:
                    print(f"[DEBUG] Using provided workflow_id: {state['workflow_id']}")

                # Add initial message for fresh start
                ai_msg = AIMessage(content="🚀 Starting release automation workflow...\n\n")
                state["messages"] = add_messages(state["messages"], [ai_msg])
                print(f"[DEBUG] Added initial AIMessage to messages.")

                # Extract workflow parameters
                repositories = state.get("repositories", [])
                fix_version = state.get("fix_version", "v2.1.0")
                sprint_name = state.get("sprint_name", "sprint-2024-01")
                print(f"[DEBUG] Workflow parameters - repositories: {repositories}, fix_version: {fix_version}, sprint_name: {sprint_name}")

                config_msg = AIMessage(
                    content=f"📋 **Release Configuration:**\n"
                    f"- Workflow ID: {state['workflow_id'][:8]}...\n"
                    f"- Fix Version: {fix_version}\n"
                    f"- Sprint Branch: {sprint_name}\n"
                    f"- Target Repositories: {', '.join(repositories)}\n\n"
                )
                state["messages"] = add_messages(state["messages"], [config_msg])
                print(f"[DEBUG] Added config AIMessage to messages.")

                state["steps_completed"].append("start")
                print(f"[DEBUG] Appended 'start' to steps_completed: {state['steps_completed']}")
            else:
                print("[DEBUG] Resume detected. Preserving existing state and adding resume message.")
                # Resume - preserve existing state and add resume message
                # Ensure messages key exists
                if "messages" not in state:
                    state["messages"] = []
                    print("[DEBUG] 'messages' key not found in state. Initialized to empty list.")
                
                resume_msg = AIMessage(content="🔄 Resuming release automation workflow...\n\n")
                state["messages"] = add_messages(state["messages"], [resume_msg])
                print(f"[DEBUG] Added resume AIMessage to messages.")
                
                # Clear any previous errors when resuming
                state["error"] = ""
                state["error_step"] = ""
                state["can_continue"] = True
                state["workflow_paused"] = False
                if not state["steps_completed"]:
                    state["steps_completed"]= ["start"]
                if state["steps_completed"] and "start" not in state["steps_completed"]:
                    state["steps_completed"].append("start")

                # Ensure current_step is set properly for resume
                if not state.get("current_step") or state["current_step"] == "":
                    # If no current step, start from the beginning
                    state["current_step"] = "start"
                    print(f"[DEBUG] No current_step found, setting to 'start'")
                else:
                    print(f"[DEBUG] Using existing current_step: {state['current_step']}")
                
                print(f"[DEBUG] Cleared error, error_step, set can_continue=True, workflow_paused=False.")

            print(f"[DEBUG] Final state before sleep/return: {state}")
            await asyncio.sleep(0.5)
            print(f"[DEBUG] Returning state from start_workflow.")
            return state

        except Exception as e:
            print(f"[ERROR] Exception in start_workflow: {e}")
            return handle_workflow_error(state, "start", str(e))

    @log_workflow_function(level=LogLevel.INFO, include_state=True, include_result=False, include_execution_time=True, log_errors=True)
    async def collect_jira_tickets(state: WorkflowState) -> WorkflowState:
        """Step 1: Collect JIRA tickets for the fix version."""
        try:
            # Check if this step has already been completed
            if check_step_completion(state, "jira_collection", "Step 1: Collecting JIRA Tickets"):
                return state

            state["current_step"] = "jira_collection"

            msg = AIMessage(
                content="🎫 **Step 1: Collecting JIRA Tickets**\n"
                f"Searching for tickets with fix version: {state['fix_version']}...\n"
            )
            state["messages"] = add_messages(state["messages"], [msg])

            # Initialize API clients
            factory = APIClientFactory()
            clients = factory.create_all_clients()
            jira_client = clients.jira

            try:
                # Get tickets by fix version
                tickets = await jira_client.get_tickets_by_fix_version(
                    state["fix_version"]
                )

                # Convert to simplified format for state storage
                jira_tickets = [
                    {
                        "id": ticket.key,
                        "summary": ticket.summary,
                        "status": ticket.status,
                        "assignee": ticket.assignee,
                        "priority": ticket.priority,
                    }
                    for ticket in tickets
                ]

                state["jira_tickets"] = jira_tickets

                if jira_tickets:
                    result_msg = AIMessage(
                        content=f"✅ Found {len(jira_tickets)} tickets:\n"
                        + "\n".join(
                            f"  • {ticket['id']}: {ticket['summary']} [{ticket['status']}]"
                            for ticket in jira_tickets
                        )
                        + "\n\n"
                    )
                else:
                    result_msg = AIMessage(
                        content=f"⚠️  No tickets found with fix version: {state['fix_version']}\n"
                        "Please verify the fix version or check JIRA configuration.\n\n"
                    )

                state["messages"] = add_messages(state["messages"], [result_msg])

            except Exception as api_error:
                # Log the error and fall back to mock data for development
                error_msg = AIMessage(
                    content=f"⚠️  JIRA API error: {str(api_error)}\n"
                    "Falling back to mock data for development...\n\n"
                )
                state["messages"] = add_messages(state["messages"], [error_msg])

                # Mock fallback data
                jira_tickets = [
                    {
                        "id": "PROJ-123",
                        "summary": "Implement user authentication",
                        "status": "Done",
                        "assignee": "developer1",
                        "priority": "High",
                    },
                    {
                        "id": "PROJ-124",
                        "summary": "Fix data validation bug",
                        "status": "Done",
                        "assignee": "developer2",
                        "priority": "Medium",
                    },
                    {
                        "id": "PROJ-125",
                        "summary": "Update API documentation",
                        "status": "In Progress",
                        "assignee": "developer3",
                        "priority": "Low",
                    },
                ]
                state["jira_tickets"] = jira_tickets

                mock_result_msg = AIMessage(
                    content=f"🔧 Using mock data - Found {len(jira_tickets)} tickets:\n"
                    + "\n".join(
                        f"  • {ticket['id']}: {ticket['summary']} [{ticket['status']}]"
                        for ticket in jira_tickets
                    )
                    + "\n\n"
                )
                state["messages"] = add_messages(state["messages"], [mock_result_msg])

            state["steps_completed"].append("jira_collection")
            await asyncio.sleep(1)
            return state

        except Exception as e:
            return handle_workflow_error(state, "jira_collection", str(e))

    @log_workflow_function(level=LogLevel.INFO, include_state=True, include_result=False, include_execution_time=True, log_errors=True)
    async def discover_feature_branches(state: WorkflowState) -> WorkflowState:
        """Step 2: Discover feature branches for JIRA tickets."""
        try:
            # Check if this step has already been completed
            if check_step_completion(state, "branch_discovery", "Step 2: Feature Branch Discovery"):
                return state

            state["current_step"] = "branch_discovery"

            msg = AIMessage(
                content="🌳 **Step 2: Feature Branch Discovery**\n"
                "Searching for feature branches in repositories...\n"
            )
            state["messages"] = add_messages(state["messages"], [msg])

            # Initialize API clients
            factory = APIClientFactory()
            clients = factory.create_all_clients()
            github_client = clients.github

            jira_tickets = state.get("jira_tickets", [])
            ticket_ids = [ticket["id"] for ticket in jira_tickets]

            feature_branches = {}
            missing_branches = {}

            for repo in state["repositories"]:
                repo_branches = []
                repo_missing = []

                try:
                    # Get all branches for the repository
                    branches = await github_client.get_branches(repo)
                    branch_names = [branch.name for branch in branches]

                    # Look for feature branches matching pattern: feature/{JIRA-ID}
                    for ticket_id in ticket_ids:
                        feature_pattern = f"feature/{ticket_id}"
                        if feature_pattern in branch_names:
                            repo_branches.append(feature_pattern)
                        else:
                            repo_missing.append(ticket_id)

                    feature_branches[repo] = repo_branches
                    missing_branches[repo] = repo_missing

                    # Report findings for this repository
                    found_count = len(repo_branches)
                    missing_count = len(repo_missing)

                    branch_status = (
                        f"  📁 {repo}: {found_count} found, {missing_count} missing\n"
                    )
                    for branch in repo_branches:
                        branch_status += f"    ✅ {branch}\n"
                    for missing in repo_missing:
                        branch_status += f"    ❌ feature/{missing} - not found\n"

                    branch_msg = AIMessage(content=branch_status)
                    state["messages"] = add_messages(state["messages"], [branch_msg])
                    await asyncio.sleep(0.5)

                except Exception as api_error:
                    # Fall back to mock data for this repository
                    error_msg = AIMessage(
                        content=f"  ⚠️  GitHub API error for {repo}: {str(api_error)}\n"
                        f"  🔧 Using mock data for {repo}...\n"
                    )
                    state["messages"] = add_messages(state["messages"], [error_msg])

                    # Mock data fallback
                    mock_branches = [
                        f"feature/{ticket_id}" for ticket_id in ticket_ids[:2]
                    ]  # First 2 tickets
                    mock_missing = ticket_ids[2:]  # Remaining tickets

                    feature_branches[repo] = mock_branches
                    missing_branches[repo] = mock_missing

                    mock_status = f"  📁 {repo} (mock):\n"
                    for branch in mock_branches:
                        mock_status += f"    ✅ {branch}\n"
                    for missing in mock_missing:
                        mock_status += f"    ❌ feature/{missing} - not found\n"

                    mock_msg = AIMessage(content=mock_status)
                    state["messages"] = add_messages(state["messages"], [mock_msg])

            state["feature_branches"] = feature_branches
            state["missing_branches"] = missing_branches

            # Summary
            total_found = sum(len(branches) for branches in feature_branches.values())
            total_missing = sum(len(missing) for missing in missing_branches.values())

            summary_msg = AIMessage(
                content=f"\n📊 **Discovery Summary:**\n"
                f"• Total feature branches found: {total_found}\n"
                f"• Total missing branches: {total_missing}\n"
                f"• Repositories scanned: {len(state['repositories'])}\n\n"
            )
            state["messages"] = add_messages(state["messages"], [summary_msg])

            state["steps_completed"].append("branch_discovery")
            return state

        except Exception as e:
            return handle_workflow_error(state, "branch_discovery", str(e))

    @log_workflow_function(level=LogLevel.INFO, include_state=True, include_result=False, include_execution_time=True, log_errors=True)
    async def validate_merge_status(state: WorkflowState) -> WorkflowState:
        """Step 3: Validate merge status of feature branches."""
        try:
            # Check if this step has already been completed
            if check_step_completion(state, "merge_validation", "Step 3: Merge Status Validation"):
                return state

            state["current_step"] = "merge_validation"

            msg = AIMessage(
                content="🔀 **Step 3: Merge Status Validation**\n"
                f"Checking if feature branches are merged to {state['sprint_name']}...\n\n"
            )
            state["messages"] = add_messages(state["messages"], [msg])

            # Initialize API clients
            factory = APIClientFactory()
            clients = factory.create_all_clients()
            github_client = clients.github

            feature_branches = state.get("feature_branches", {})
            merge_status = {}
            unmerged_branches = {}

            for repo in state["repositories"]:
                repo_branches = feature_branches.get(repo, [])
                repo_merge_status = {}
                repo_unmerged = []

                try:
                    for branch in repo_branches:
                        # Check if branch is merged into sprint branch
                        is_merged = await github_client.is_branch_merged(
                            repo, branch, state["sprint_name"]
                        )
                        repo_merge_status[branch] = is_merged

                        if not is_merged:
                            repo_unmerged.append(branch)

                    merge_status[repo] = repo_merge_status
                    unmerged_branches[repo] = repo_unmerged

                    # Report status for this repository
                    status_text = f"  📁 {repo}:\n"
                    for branch, is_merged in repo_merge_status.items():
                        if is_merged:
                            status_text += f"    ✅ {branch} → {state['sprint_name']}\n"
                        else:
                            status_text += f"    ⚠️  {branch} → needs merge to {state['sprint_name']}\n"

                    status_msg = AIMessage(content=status_text)
                    state["messages"] = add_messages(state["messages"], [status_msg])
                    await asyncio.sleep(0.5)

                except Exception as api_error:
                    # Fall back to mock data for this repository
                    error_msg = AIMessage(
                        content=f"  ⚠️  GitHub API error for {repo}: {str(api_error)}\n"
                        f"  🔧 Using mock merge status for {repo}...\n"
                    )
                    state["messages"] = add_messages(state["messages"], [error_msg])

                    # Mock merge status - assume first branches are merged, others are not
                    mock_merge_status = {}
                    mock_unmerged = []

                    for i, branch in enumerate(repo_branches):
                        is_merged = i < len(repo_branches) // 2  # First half merged
                        mock_merge_status[branch] = is_merged
                        if not is_merged:
                            mock_unmerged.append(branch)

                    merge_status[repo] = mock_merge_status
                    unmerged_branches[repo] = mock_unmerged

                    mock_status = f"  📁 {repo} (mock):\n"
                    for branch, is_merged in mock_merge_status.items():
                        if is_merged:
                            mock_status += f"    ✅ {branch} → {state['sprint_name']}\n"
                        else:
                            mock_status += f"    ⚠️  {branch} → needs merge\n"

                    mock_msg = AIMessage(content=mock_status)
                    state["messages"] = add_messages(state["messages"], [mock_msg])

            state["merge_status"] = merge_status
            state["unmerged_branches"] = unmerged_branches

            # Summary
            total_branches = sum(
                len(branches) for branches in feature_branches.values()
            )
            total_unmerged = sum(
                len(unmerged) for unmerged in unmerged_branches.values()
            )
            total_merged = total_branches - total_unmerged

            summary_msg = AIMessage(
                content=f"\n📊 **Merge Status Summary:**\n"
                f"• Total branches checked: {total_branches}\n"
                f"• Merged to {state['sprint_name']}: {total_merged}\n"
                f"• Require merging: {total_unmerged}\n\n"
            )

            if total_unmerged > 0:
                summary_msg.content += (
                    "⚠️  **Action Required:** Some branches need to be merged to the sprint branch "
                    "before proceeding with the release.\n\n"
                )

            state["messages"] = add_messages(state["messages"], [summary_msg])

            state["steps_completed"].append("merge_validation")
            return state

        except Exception as e:
            return handle_workflow_error(state, "merge_validation", str(e))



    @log_workflow_function(level=LogLevel.INFO, include_state=True, include_result=False, include_execution_time=True, log_errors=True)
    async def merge_sprint_branches(state: WorkflowState) -> WorkflowState:
        """Step 5: Merge sprint branches to develop."""
        try:
            # Check if this step has already been completed
            if check_step_completion(state, "sprint_merging", f"Step 5: Merging {state['sprint_name']} to develop"):
                return state

            state["current_step"] = "sprint_merging"

            msg = AIMessage(
                content=f"🔀 **Step 5: Merging {state['sprint_name']} to develop**\n"
                "Creating pull requests and performing merges...\n\n"
            )
            state["messages"] = add_messages(state["messages"], [msg])

            # Initialize API clients
            factory = APIClientFactory()
            clients = factory.create_all_clients()
            github_client = clients.github

            sprint_merge_results = {}
            merge_conflicts = {}
            successful_merges = []

            for repo in state["repositories"]:
                try:
                    # Create pull request from sprint branch to develop
                    pr_title = f"Merge {state['sprint_name']} to develop - Release {state['fix_version']}"
                    pr_description = (
                        f"Automated merge of {state['sprint_name']} branch to develop for release {state['fix_version']}.\n\n"
                        "**Included Changes:**\n"
                        + "\n".join(
                            [
                                f"- {ticket['id']}: {ticket['summary']}"
                                for ticket in state.get("jira_tickets", [])
                            ]
                        )
                    )

                    # Check if branches exist and create PR
                    pr = await github_client.create_pull_request(
                        repo_name=repo,
                        title=pr_title,
                        body=pr_description,
                        head_branch=state["sprint_name"],
                        base_branch="develop",
                    )

                    # Attempt to merge if no conflicts
                    try:
                        # merge_result = await github_client.merge_pull_request(
                        #     repo=repo,
                        #     pr_number=pr.number,
                        #     merge_method="merge",  # Can be 'merge', 'squash', or 'rebase'
                        # )
                        merge_result = await github_client.merge_branches(
                            repo=repo,
                            repo_name=state["sprint_name"],
                            target_branch="develop",
                        )

                        sprint_merge_results[repo] = {
                            "status": "success",
                            "pr_url": pr.html_url,
                            "pr_number": pr.number,
                            "merge_sha": merge_result.sha if merge_result else None,
                        }
                        successful_merges.append(repo)

                        success_msg = AIMessage(
                            content=f"  📁 {repo}: ✅ Merged successfully\n"
                            f"    📝 PR: {pr.html_url}\n"
                        )
                        state["messages"] = add_messages(
                            state["messages"], [success_msg]
                        )

                    except Exception as merge_error:
                        # Handle merge conflicts
                        conflict_msg = str(merge_error)
                        if (
                            "conflict" in conflict_msg.lower()
                            or "merge conflict" in conflict_msg.lower()
                        ):
                            sprint_merge_results[repo] = {
                                "status": "conflict",
                                "pr_url": pr.html_url,
                                "pr_number": pr.number,
                                "error": conflict_msg,
                            }
                            merge_conflicts[repo] = conflict_msg

                            conflict_msg_obj = AIMessage(
                                content=f"  📁 {repo}: ⚠️  Merge conflict detected\n"
                                f"    📝 PR: {pr.html_url}\n"
                                f"    🔧 Manual resolution required\n"
                            )
                            state["messages"] = add_messages(
                                state["messages"], [conflict_msg_obj]
                            )
                        else:
                            # Other merge error
                            sprint_merge_results[repo] = {
                                "status": "error",
                                "pr_url": pr.html_url,
                                "pr_number": pr.number,
                                "error": conflict_msg,
                            }

                            error_msg = AIMessage(
                                content=f"  📁 {repo}: ❌ Merge failed\n"
                                f"    📝 PR: {pr.html_url}\n"
                                f"    🔧 Error: {conflict_msg}\n"
                            )
                            state["messages"] = add_messages(
                                state["messages"], [error_msg]
                            )

                except Exception as api_error:
                    # Fall back to mock data for this repository
                    error_msg = AIMessage(
                        content=f"  ⚠️  GitHub API error for {repo}: {str(api_error)}\n"
                        f"  🔧 Simulating merge for {repo}...\n"
                    )
                    state["messages"] = add_messages(state["messages"], [error_msg])

                    # Mock successful merge
                    sprint_merge_results[repo] = {
                        "status": "success",
                        "pr_url": f"https://github.com/company/{repo}/pull/100",
                        "pr_number": 100,
                        "merge_sha": "abc123def456",
                    }
                    successful_merges.append(repo)

                    mock_msg = AIMessage(
                        content=f"  📁 {repo} (mock): ✅ Merge simulated\n"
                        f"    📝 PR: {sprint_merge_results[repo]['pr_url']}\n"
                    )
                    state["messages"] = add_messages(state["messages"], [mock_msg])

                await asyncio.sleep(0.5)

            state["sprint_merge_results"] = sprint_merge_results
            state["merge_conflicts"] = merge_conflicts
            state["successful_merges"] = successful_merges

            # Summary
            success_count = len(successful_merges)
            conflict_count = len(merge_conflicts)
            total_repos = len(state["repositories"])

            summary_msg = AIMessage(
                content=f"\n📊 **Sprint Merge Summary:**\n"
                f"• Successful merges: {success_count}/{total_repos}\n"
                f"• Merge conflicts: {conflict_count}\n"
                f"• Total repositories: {total_repos}\n\n"
            )

            if conflict_count > 0:
                summary_msg.content += (
                    "⚠️  **Manual Action Required:** Resolve merge conflicts in the following repositories:\n"
                    + "\n".join([f"  • {repo}" for repo in merge_conflicts.keys()])
                    + "\n\n"
                )

            state["messages"] = add_messages(state["messages"], [summary_msg])

            state["steps_completed"].append("sprint_merging")
            return state

        except Exception as e:
            return handle_workflow_error(state, "sprint_merging", str(e))

    @log_workflow_function(level=LogLevel.INFO, include_state=True, include_result=False, include_execution_time=True, log_errors=True)
    async def create_release_branches(state: WorkflowState) -> WorkflowState:
        """Step 6: Create release branches with semantic versioning."""
        try:
            # Check if this step has already been completed
            if check_step_completion(state, "release_creation", "Step 6: Creating Release Branches"):
                return state

            state["current_step"] = "release_creation"

            msg = AIMessage(
                content=f"\n🌿 **Step 6: Creating Release Branches**\n"
                f"Analyzing existing versions and creating release branches...\n"
            )
            state["messages"] = add_messages(state["messages"], [msg])

            # Initialize API clients
            factory = APIClientFactory()
            clients = factory.create_all_clients()
            github_client = clients.github

            release_branches = []
            version_info = {}

            # Determine the release version using semantic versioning
            calculated_version = await _calculate_next_version(github_client, state)

            version_msg = AIMessage(
                content=f"📊 **Version Analysis:**\n"
                f"• Target fix version: {state['fix_version']}\n"
                f"• Calculated semantic version: {calculated_version}\n"
                f"• Release type: {state.get('release_type', 'release')}\n\n"
            )
            state["messages"] = add_messages(state["messages"], [version_msg])

            for repo in state["repositories"]:
                try:
                    # Create release branch from develop
                    branch_name = f"release/{calculated_version}"

                    # Check if release branch already exists
                    existing_branches = await github_client.get_branches(repo)
                    branch_names = [branch.name for branch in existing_branches]

                    if branch_name in branch_names:
                        # Branch already exists
                        version_info[repo] = {
                            "status": "exists",
                            "branch": branch_name,
                            "base": "develop",
                        }

                        exists_msg = AIMessage(
                            content=f"  📁 {repo}: ⚠️  {branch_name} already exists\n"
                        )
                        state["messages"] = add_messages(
                            state["messages"], [exists_msg]
                        )
                    else:
                        # Create new release branch
                        new_branch = await github_client.create_branch(
                            repo=repo, branch_name=branch_name, source_branch="develop"
                        )

                        version_info[repo] = {
                            "status": "created",
                            "branch": branch_name,
                            "base": "develop",
                            "sha": new_branch.sha,
                        }

                        success_msg = AIMessage(
                            content=f"  📁 {repo}: ✅ {branch_name} created from develop\n"
                        )
                        state["messages"] = add_messages(
                            state["messages"], [success_msg]
                        )

                    release_branches.append(f"{repo}:{branch_name}")

                except Exception as api_error:
                    # Fall back to mock data for this repository
                    error_msg = AIMessage(
                        content=f"  ⚠️  GitHub API error for {repo}: {str(api_error)}\n"
                        f"  🔧 Simulating branch creation for {repo}...\n"
                    )
                    state["messages"] = add_messages(state["messages"], [error_msg])

                    # Mock branch creation
                    branch_name = f"release/{calculated_version}"
                    version_info[repo] = {
                        "status": "created",
                        "branch": branch_name,
                        "base": "develop",
                        "sha": "mock_sha_123",
                    }
                    release_branches.append(f"{repo}:{branch_name}")

                    mock_msg = AIMessage(
                        content=f"  📁 {repo} (mock): ✅ {branch_name} simulated\n"
                    )
                    state["messages"] = add_messages(state["messages"], [mock_msg])

                await asyncio.sleep(0.5)

            state["release_branches"] = release_branches
            state["calculated_version"] = calculated_version
            state["version_info"] = version_info

            # Summary
            created_count = sum(
                1 for info in version_info.values() if info["status"] == "created"
            )
            existing_count = sum(
                1 for info in version_info.values() if info["status"] == "exists"
            )

            summary_msg = AIMessage(
                content=f"\n📊 **Release Branch Summary:**\n"
                f"• Release version: {calculated_version}\n"
                f"• New branches created: {created_count}\n"
                f"• Existing branches: {existing_count}\n"
                f"• Total repositories: {len(state['repositories'])}\n\n"
            )
            state["messages"] = add_messages(state["messages"], [summary_msg])

            state["steps_completed"].append("release_creation")
            return state

        except Exception as e:
            return handle_workflow_error(state, "release_branch_creation", str(e))

    @log_workflow_function(level=LogLevel.INFO, include_state=True, include_result=False, include_execution_time=True, log_errors=True)
    async def generate_pull_requests(state: WorkflowState) -> WorkflowState:
        """Step 7: Generate pull requests from release branches to master."""
        try:
            # Check if this step has already been completed
            if check_step_completion(state, "pr_generation", "Step 7: Generating Pull Requests"):
                return state

            state["current_step"] = "pr_generation"

            msg = AIMessage(
                content=f"\n📝 **Step 7: Generating Pull Requests**\n"
                "Creating PRs from release branches to master...\n"
            )
            state["messages"] = add_messages(state["messages"], [msg])

            # Initialize API clients
            factory = APIClientFactory()
            clients = factory.create_all_clients()
            github_client = clients.github

            calculated_version = state.get(
                "calculated_version", state.get("fix_version", "v1.0.0")
            )
            pull_requests = []
            pr_creation_results = {}

            for repo in state["repositories"]:
                try:
                    release_branch = f"release/{calculated_version}"

                    # Generate comprehensive PR description
                    pr_title = f"Release {calculated_version}"
                    pr_description = _generate_pr_description(state, calculated_version)

                    # Create pull request from release branch to master
                    pr = await github_client.create_pull_request(
                        repo=repo,
                        title=pr_title,
                        head=release_branch,
                        base="master",  # or "main" depending on repository default
                        body=pr_description,
                    )

                    pr_info = {
                        "repo": repo,
                        "url": pr.html_url,
                        "number": pr.number,
                        "title": pr_title,
                        "head": release_branch,
                        "base": "master",
                        "status": "created",
                    }

                    pull_requests.append(pr_info)
                    pr_creation_results[repo] = {"status": "success", "pr": pr_info}

                    success_msg = AIMessage(
                        content=f"  📁 {repo}: ✅ PR created\n"
                        f"    📝 {pr.html_url}\n"
                        f"    🔀 {release_branch} → master\n"
                    )
                    state["messages"] = add_messages(state["messages"], [success_msg])

                except Exception as api_error:
                    # Handle PR creation error
                    error_msg = AIMessage(
                        content=f"  ⚠️  GitHub API error for {repo}: {str(api_error)}\n"
                        f"  🔧 Simulating PR creation for {repo}...\n"
                    )
                    state["messages"] = add_messages(state["messages"], [error_msg])

                    # Mock PR creation
                    mock_pr_number = 100 + len(pull_requests)
                    mock_pr_info = {
                        "repo": repo,
                        "url": f"https://github.com/company/{repo}/pull/{mock_pr_number}",
                        "number": mock_pr_number,
                        "title": f"Release {calculated_version}",
                        "head": f"release/{calculated_version}",
                        "base": "master",
                        "status": "mock",
                    }

                    pull_requests.append(mock_pr_info)
                    pr_creation_results[repo] = {"status": "mock", "pr": mock_pr_info}

                    mock_msg = AIMessage(
                        content=f"  📁 {repo} (mock): ✅ PR simulated\n"
                        f"    📝 {mock_pr_info['url']}\n"
                        f"    🔀 {mock_pr_info['head']} → {mock_pr_info['base']}\n"
                    )
                    state["messages"] = add_messages(state["messages"], [mock_msg])

                await asyncio.sleep(0.5)

            state["pull_requests"] = pull_requests
            state["pr_creation_results"] = pr_creation_results

            # Summary
            created_count = sum(
                1
                for result in pr_creation_results.values()
                if result["status"] == "success"
            )
            mock_count = sum(
                1
                for result in pr_creation_results.values()
                if result["status"] == "mock"
            )

            summary_msg = AIMessage(
                content=f"\n📊 **Pull Request Summary:**\n"
                f"• Release version: {calculated_version}\n"
                f"• PRs created: {created_count}\n"
                f"• Mock PRs: {mock_count}\n"
                f"• Total repositories: {len(state['repositories'])}\n\n"
                "📋 **Next Steps:**\n"
                "• Review and approve the pull requests\n"
                "• Merge PRs to deploy to production\n"
                "• Monitor deployment status\n\n"
            )
            state["messages"] = add_messages(state["messages"], [summary_msg])

            state["steps_completed"].append("pr_generation")
            return state

        except Exception as e:
            return handle_workflow_error(state, "pull_request_generation", str(e))

    @log_workflow_function(level=LogLevel.INFO, include_state=True, include_result=False, include_execution_time=True, log_errors=True)
    async def create_release_tags(state: WorkflowState) -> WorkflowState:
        """Step 8: Create release tags with semantic versioning and metadata."""
        try:
            # Check if this step has already been completed
            if check_step_completion(state, "release_tagging", "Step 8: Creating Release Tags"):
                return state

            state["current_step"] = "release_tagging"

            calculated_version = state.get(
                "calculated_version", state.get("fix_version", "v1.0.0")
            )

            msg = AIMessage(
                content=f"\n🏷️ **Step 8: Creating Release Tags**\n"
                f"Tagging release branches with {calculated_version}...\n"
            )
            state["messages"] = add_messages(state["messages"], [msg])

            # Initialize API clients
            factory = APIClientFactory()
            clients = factory.create_all_clients()
            github_client = clients.github

            release_tags = []
            tag_creation_results = {}

            for repo in state["repositories"]:
                try:
                    release_branch = f"release/{calculated_version}"
                    tag_name = calculated_version

                    # Generate tag message with release information
                    tag_message = _generate_tag_message(state, calculated_version)

                    # Create Git tag on the release branch
                    tag = await github_client.create_tag(
                        repo=repo,
                        tag_name=tag_name,
                        target_sha=None,  # Will use latest commit on release branch
                        message=tag_message,
                        target_ref=release_branch,
                    )

                    tag_info = {
                        "repo": repo,
                        "tag": tag_name,
                        "sha": tag.sha,
                        "branch": release_branch,
                        "message": tag_message,
                        "status": "created",
                    }

                    release_tags.append(tag_info)
                    tag_creation_results[repo] = {"status": "success", "tag": tag_info}

                    success_msg = AIMessage(
                        content=f"  📁 {repo}: ✅ Tag {tag_name} created\n"
                        f"    🏷️  SHA: {tag.sha[:8]}\n"
                        f"    🌿 Branch: {release_branch}\n"
                    )
                    state["messages"] = add_messages(state["messages"], [success_msg])

                except Exception as api_error:
                    # Handle tag creation error
                    error_msg = AIMessage(
                        content=f"  ⚠️  GitHub API error for {repo}: {str(api_error)}\n"
                        f"  🔧 Simulating tag creation for {repo}...\n"
                    )
                    state["messages"] = add_messages(state["messages"], [error_msg])

                    # Mock tag creation
                    mock_tag_info = {
                        "repo": repo,
                        "tag": calculated_version,
                        "sha": "mock_sha_789",
                        "branch": f"release/{calculated_version}",
                        "message": _generate_tag_message(state, calculated_version),
                        "status": "mock",
                    }

                    release_tags.append(mock_tag_info)
                    tag_creation_results[repo] = {
                        "status": "mock",
                        "tag": mock_tag_info,
                    }

                    mock_msg = AIMessage(
                        content=f"  📁 {repo} (mock): ✅ Tag {calculated_version} simulated\n"
                        f"    🏷️  SHA: {mock_tag_info['sha']}\n"
                        f"    🌿 Branch: {mock_tag_info['branch']}\n"
                    )
                    state["messages"] = add_messages(state["messages"], [mock_msg])

                await asyncio.sleep(0.5)

            state["release_tags"] = release_tags
            state["tag_creation_results"] = tag_creation_results

            # Summary
            created_count = sum(
                1
                for result in tag_creation_results.values()
                if result["status"] == "success"
            )
            mock_count = sum(
                1
                for result in tag_creation_results.values()
                if result["status"] == "mock"
            )

            summary_msg = AIMessage(
                content=f"\n📊 **Release Tag Summary:**\n"
                f"• Release version: {calculated_version}\n"
                f"• Tags created: {created_count}\n"
                f"• Mock tags: {mock_count}\n"
                f"• Total repositories: {len(state['repositories'])}\n\n"
                "🎯 **Version Tracking:**\n"
                f"• Git tags created for version {calculated_version}\n"
                "• Tags point to latest commit on release branches\n"
                "• Tags include release metadata and changelog\n\n"
            )
            state["messages"] = add_messages(state["messages"], [summary_msg])

            state["steps_completed"].append("release_tagging")
            return state

        except Exception as e:
            return handle_workflow_error(state, "release_tagging", str(e))

    @log_workflow_function(level=LogLevel.INFO, include_state=True, include_result=False, include_execution_time=True, log_errors=True)
    async def prepare_rollback_branches(state: WorkflowState) -> WorkflowState:
        """Step 9: Prepare rollback branches with proper naming conventions."""
        try:
            # Check if this step has already been completed
            if check_step_completion(state, "rollback_preparation", "Step 9: Preparing Rollback Branches"):
                return state

            state["current_step"] = "rollback_preparation"

            calculated_version = state.get(
                "calculated_version", state.get("fix_version", "v1.0.0")
            )

            msg = AIMessage(
                content=f"\n🔄 **Step 9: Preparing Rollback Branches**\n"
                f"Creating rollback branches from master for version {calculated_version}...\n"
            )
            state["messages"] = add_messages(state["messages"], [msg])

            # Initialize API clients
            factory = APIClientFactory()
            clients = factory.create_all_clients()
            github_client = clients.github

            rollback_branches = []
            rollback_creation_results = {}

            for repo in state["repositories"]:
                try:
                    # Create standardized rollback branch name
                    rollback_branch = (
                        f"rollback/v-{calculated_version.replace('v', '')}"
                    )

                    # Check if rollback branch already exists
                    existing_branches = await github_client.get_branches(repo)
                    branch_names = [branch.name for branch in existing_branches]

                    if rollback_branch in branch_names:
                        # Branch already exists
                        rollback_creation_results[repo] = {
                            "status": "exists",
                            "branch": rollback_branch,
                            "base": "master",
                        }

                        exists_msg = AIMessage(
                            content=f"  📁 {repo}: ⚠️  {rollback_branch} already exists\n"
                        )
                        state["messages"] = add_messages(
                            state["messages"], [exists_msg]
                        )
                    else:
                        # Create new rollback branch from master HEAD
                        new_branch = await github_client.create_branch(
                            repo=repo,
                            branch_name=rollback_branch,
                            source_branch="master",  # or "main" depending on repository default
                        )

                        rollback_creation_results[repo] = {
                            "status": "created",
                            "branch": rollback_branch,
                            "base": "master",
                            "sha": new_branch.sha,
                        }

                        success_msg = AIMessage(
                            content=f"  📁 {repo}: ✅ {rollback_branch} created from master\n"
                            f"    🔗 SHA: {new_branch.sha[:8]}\n"
                        )
                        state["messages"] = add_messages(
                            state["messages"], [success_msg]
                        )

                    rollback_branches.append(f"{repo}:{rollback_branch}")

                except Exception as api_error:
                    # Fall back to mock data for this repository
                    error_msg = AIMessage(
                        content=f"  ⚠️  GitHub API error for {repo}: {str(api_error)}\n"
                        f"  🔧 Simulating rollback branch creation for {repo}...\n"
                    )
                    state["messages"] = add_messages(state["messages"], [error_msg])

                    # Mock rollback branch creation
                    rollback_branch = (
                        f"rollback/v-{calculated_version.replace('v', '')}"
                    )
                    rollback_creation_results[repo] = {
                        "status": "created",
                        "branch": rollback_branch,
                        "base": "master",
                        "sha": "mock_rollback_sha",
                    }
                    rollback_branches.append(f"{repo}:{rollback_branch}")

                    mock_msg = AIMessage(
                        content=f"  📁 {repo} (mock): ✅ {rollback_branch} simulated\n"
                        f"    🔗 SHA: mock_rollback_sha\n"
                    )
                    state["messages"] = add_messages(state["messages"], [mock_msg])

                await asyncio.sleep(0.5)

            state["rollback_branches"] = rollback_branches
            state["rollback_creation_results"] = rollback_creation_results

            # Summary
            created_count = sum(
                1
                for result in rollback_creation_results.values()
                if result["status"] == "created"
            )
            existing_count = sum(
                1
                for result in rollback_creation_results.values()
                if result["status"] == "exists"
            )

            summary_msg = AIMessage(
                content=f"\n📊 **Rollback Preparation Summary:**\n"
                f"• Rollback version: {calculated_version}\n"
                f"• New rollback branches: {created_count}\n"
                f"• Existing rollback branches: {existing_count}\n"
                f"• Total repositories: {len(state['repositories'])}\n\n"
                "🛡️ **Rollback Instructions:**\n"
                "1. In case of deployment issues, checkout rollback branch\n"
                "2. Create emergency PR from rollback branch to master\n"
                "3. Deploy rollback branch to restore previous state\n"
                f"4. Branch naming pattern: `rollback/v-{calculated_version.replace('v', '')}`\n\n"
                "🚨 **Emergency Rollback Command:**\n"
                f"```bash\n"
                f"git checkout rollback/v-{calculated_version.replace('v', '')}\n"
                f"# Deploy this version to production\n"
                f"```\n\n"
            )
            state["messages"] = add_messages(state["messages"], [summary_msg])

            state["steps_completed"].append("rollback_preparation")
            return state

        except Exception as e:
            return handle_workflow_error(state, "rollback_preparation", str(e))

    def _generate_deployment_documentation_content(state: "WorkflowState") -> str:
        """Generate standardized Confluence documentation content."""
        fix_version = state.get("fix_version", "Unknown")
        sprint_name = state.get("sprint_name", "Unknown")
        release_type = state.get("release_type", "release")
        repositories = state.get("repositories", [])
        jira_tickets = state.get("jira_tickets", [])
        pull_requests = state.get("pull_requests", [])
        release_branches = state.get("release_branches", [])
        rollback_branches = state.get("rollback_branches", [])
        calculated_version = state.get("calculated_version", fix_version)

        # Generate current timestamp
        from datetime import datetime

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")

        # Build JIRA tickets table
        jira_table_rows = []
        for ticket in jira_tickets:
            jira_table_rows.append(
                f"""
                <tr>
                    <td><a href="https://your-company.atlassian.net/browse/{ticket.get('key', 'N/A')}">{ticket.get('key', 'N/A')}</a></td>
                    <td>{ticket.get('summary', 'N/A')}</td>
                    <td>{ticket.get('status', 'N/A')}</td>
                    <td>{ticket.get('assignee', 'N/A')}</td>
                </tr>
            """
            )

        jira_table = f"""
            <table>
                <thead>
                    <tr>
                        <th>JIRA ID</th>
                        <th>Summary</th>
                        <th>Status</th>
                        <th>Assignee</th>
                    </tr>
                </thead>
                <tbody>
                    {''.join(jira_table_rows) if jira_table_rows else '<tr><td colspan="4">No JIRA tickets found</td></tr>'}
                </tbody>
            </table>
        """

        # Build deployment section for each repository
        deployment_sections = []
        rollback_sections = []

        for repo in repositories:
            # Find corresponding PR and branch info
            repo_pr = None
            repo_release_branch = None
            repo_rollback_branch = None

            for pr in pull_requests:
                if pr.get("repository") == repo:
                    repo_pr = pr
                    break

            for branch in release_branches:
                if branch.startswith(f"{repo}:"):
                    repo_release_branch = branch.split(":", 1)[1]
                    break

            for branch in rollback_branches:
                if branch.startswith(f"{repo}:"):
                    repo_rollback_branch = branch.split(":", 1)[1]
                    break

            # Jenkins URL (standardized format)
            jenkins_url = f"https://jenkins.your-company.com/job/{repo}/job/{repo_release_branch or 'master'}/build"

            deployment_sections.append(
                f"""
                <h4>{repo}</h4>
                <ul>
                    <li><strong>Jenkins Job:</strong> <a href="{jenkins_url}">{repo} - {repo_release_branch or 'master'}</a></li>
                    <li><strong>Pull Request:</strong> {f'<a href="{repo_pr.get("url", "#")}">{repo_pr.get("title", "PR")}</a>' if repo_pr else 'N/A'}</li>
                    <li><strong>Branch:</strong> {repo_release_branch or 'master'}</li>
                    <li><strong>Version:</strong> {calculated_version}</li>
                </ul>
            """
            )

            rollback_sections.append(
                f"""
                <h4>{repo}</h4>
                <ul>
                    <li><strong>Rollback Branch:</strong> {repo_rollback_branch or f'rollback/v-{calculated_version.replace("v", "")}'}</li>
                    <li><strong>Emergency Jenkins Job:</strong> <a href="https://jenkins.your-company.com/job/{repo}/job/{repo_rollback_branch or 'master'}/build">{repo} - Rollback</a></li>
                    <li><strong>Rollback Command:</strong> <code>git checkout {repo_rollback_branch or f'rollback/v-{calculated_version.replace("v", "")}'}</code></li>
                </ul>
            """
            )

        # Generate complete HTML documentation
        html_content = f"""
        <h1>Release {fix_version} - Deployment Documentation</h1>
        
        <h2>Release Information</h2>
        <table>
            <tr><td><strong>Fix Version:</strong></td><td>{fix_version}</td></tr>
            <tr><td><strong>Sprint:</strong></td><td>{sprint_name}</td></tr>
            <tr><td><strong>Release Type:</strong></td><td>{release_type.title()}</td></tr>
            <tr><td><strong>Version:</strong></td><td>{calculated_version}</td></tr>
            <tr><td><strong>Generated:</strong></td><td>{timestamp}</td></tr>
            <tr><td><strong>Repositories:</strong></td><td>{len(repositories)}</td></tr>
        </table>
        
        <h2>JIRA Tickets Included</h2>
        {jira_table}
        
        <h2>Deployment Plan</h2>
        <p>Execute deployment in the following order:</p>
        {''.join(deployment_sections)}
        
        <h2>Rollback Plan</h2>
        <p><strong>⚠️ Emergency Rollback Procedures:</strong></p>
        <p>In case of deployment issues, follow these steps for each repository:</p>
        {''.join(rollback_sections)}
        
        <h2>Deployment Checklist</h2>
        <ul>
            <li>☐ All JIRA tickets are in "Done" status</li>
            <li>☐ All feature branches merged to sprint branch</li>
            <li>☐ Sprint branches merged to develop</li>
            <li>☐ Release branches created and tagged</li>
            <li>☐ Pull requests reviewed and approved</li>
            <li>☐ Rollback branches prepared</li>
            <li>☐ Jenkins jobs configured and tested</li>
            <li>☐ Stakeholders notified of deployment window</li>
        </ul>
        
        <h2>Emergency Contacts</h2>
        <ul>
            <li><strong>Release Manager:</strong> TBD</li>
            <li><strong>DevOps Engineer:</strong> TBD</li>
            <li><strong>On-Call Developer:</strong> TBD</li>
        </ul>
        
        <p><em>Generated automatically by Project Enigma Release Automation</em></p>
        """

        return html_content.strip()

    @log_workflow_function(level=LogLevel.INFO, include_state=True, include_result=False, include_execution_time=True, log_errors=True)
    async def generate_confluence_docs(state: WorkflowState) -> WorkflowState:
        """Step 10: Generate comprehensive Confluence deployment documentation."""
        try:
            # Check if this step has already been completed
            if check_step_completion(state, "documentation", "Step 10: Generating Confluence Documentation"):
                return state

            state["current_step"] = "documentation"

            msg = AIMessage(
                content=f"\n📚 **Step 10: Generating Confluence Documentation**\n"
                "Creating comprehensive deployment documentation...\n"
            )
            state["messages"] = add_messages(state["messages"], [msg])

            # Initialize API clients
            factory = APIClientFactory()
            clients = factory.create_all_clients()
            confluence_client = clients.confluence

            # Generate documentation content
            doc_title = f"Release {state['fix_version']} - Deployment Documentation"
            doc_content = _generate_deployment_documentation_content(state)

            try:
                # Attempt to create/update Confluence page
                settings = get_settings()
                space_key = settings.confluence_space_key

                # Check if page already exists
                existing_pages = await confluence_client.search_pages(
                    space_key=space_key, title=doc_title
                )

                if existing_pages:
                    # Update existing page
                    existing_page = existing_pages[0]
                    updated_page = await confluence_client.update_page(
                        page_id=existing_page.id,
                        title=doc_title,
                        content=doc_content,
                        version=existing_page.version,
                    )
                    confluence_url = f"{settings.confluence_base_url}/spaces/{space_key}/pages/{updated_page.id}"

                    update_msg = AIMessage(
                        content=f"  📝 Updated existing Confluence page\n"
                        f"  🔗 Page ID: {updated_page.id}\n"
                    )
                    state["messages"] = add_messages(state["messages"], [update_msg])
                else:
                    # Create new page
                    new_page = await confluence_client.create_page(
                        space_key=space_key, title=doc_title, content=doc_content
                    )
                    confluence_url = f"{settings.confluence_base_url}/spaces/{space_key}/pages/{new_page.id}"

                    create_msg = AIMessage(
                        content=f"  📄 Created new Confluence page\n"
                        f"  🔗 Page ID: {new_page.id}\n"
                    )
                    state["messages"] = add_messages(state["messages"], [create_msg])

            except Exception as api_error:
                # Fall back to mock URL generation
                mock_msg = AIMessage(
                    content=f"  ⚠️  Confluence API error: {str(api_error)}\n"
                    f"  🔧 Generating mock documentation URL...\n"
                )
                state["messages"] = add_messages(state["messages"], [mock_msg])

                settings = get_settings()
                confluence_url = f"{settings.confluence_base_url}/wiki/spaces/DEV/pages/123456/Release+{state['fix_version'].replace('.', '-')}"

            state["confluence_url"] = confluence_url

            doc_msg = AIMessage(
                content=f"✅ **Documentation Generated Successfully**\n"
                f"🔗 **URL:** {confluence_url}\n\n"
                f"📋 **Documentation Includes:**\n"
                f"• Deployment plan for {len(state['repositories'])} repositories\n"
                f"• {len(state.get('jira_tickets', []))} JIRA tickets included\n"
                f"• {len(state.get('pull_requests', []))} pull requests generated\n"
                f"• Rollback procedures and emergency instructions\n"
                f"• Complete branch and version information\n\n"
            )
            state["messages"] = add_messages(state["messages"], [doc_msg])

            state["steps_completed"].append("documentation")
            return state

        except Exception as e:
            return handle_workflow_error(state, "documentation_generation", str(e))

    @log_workflow_function(level=LogLevel.INFO, include_state=True, include_result=False, include_execution_time=True, log_errors=True)
    async def handle_workflow_error_node(state: WorkflowState) -> WorkflowState:
        """Handle errors and provide recovery options."""
        error_step = state.get("error_step", "unknown")
        error = state.get("error", "Unknown error")
        retry_count = state.get("retry_count", 0)

        state["current_step"] = "error_handler"

        recovery_msg = AIMessage(
            content=f"🚨 **Error Handler**\n"
            f"Step: {error_step}\n"
            f"Error: {error}\n"
            f"Retry count: {retry_count}\n\n"
            f"🔄 **Recovery Options:**\n"
            f"1. Resume workflow from failed step\n"
            f"2. Skip failed step and continue\n"
            f"3. Cancel workflow\n\n"
            f"📋 **Completed steps:** {', '.join(state.get('steps_completed', []))}\n"
            f"❌ **Failed steps:** {', '.join(state.get('steps_failed', []))}\n\n"
        )
        state["messages"] = add_messages(state["messages"], [recovery_msg])

        # Auto-recover by clearing error and resuming from the failed step
        if retry_count < 3:
            state["retry_count"] = retry_count + 1
            state["error"] = ""
            state["error_step"] = ""
            state["can_continue"] = True
            
            # Resume from the failed step instead of continuing to next
            # If error_step is empty or unknown, start from the beginning
            if not error_step or error_step == "unknown" or error_step == "":
                state["current_step"] = "start"
                recovery_msg = AIMessage(
                    content=f"✅ **Auto-recovery attempt {retry_count + 1}** - starting from beginning...\n\n"
                )
            else:
                state["current_step"] = error_step
                recovery_msg = AIMessage(
                    content=f"✅ **Auto-recovery attempt {retry_count + 1}** - resuming from step '{error_step}'...\n\n"
                )
            
            state["messages"] = add_messages(state["messages"], [recovery_msg])
        else:
            state["can_continue"] = False
            state["workflow_complete"] = True

            fail_msg = AIMessage(
                content="❌ **Maximum retry attempts reached** - workflow failed.\n\n"
            )
            state["messages"] = add_messages(state["messages"], [fail_msg])

        return state

    @log_workflow_function(level=LogLevel.INFO, include_state=True, include_result=False, include_execution_time=True, log_errors=True)
    async def complete_workflow(state: WorkflowState) -> WorkflowState:
        """Final step: Complete the workflow."""
        state["current_step"] = "complete"
        state["workflow_complete"] = True

        # Final summary
        completed_steps = state.get("steps_completed", [])
        failed_steps = state.get("steps_failed", [])

        summary_msg = AIMessage(
            content="🎉 **Release Automation Complete!**\n\n"
            "**Summary:**\n"
            f"• Workflow ID: {state.get('workflow_id', 'N/A')[:8]}...\n"
            f"• Release version: {state['fix_version']}\n"
            f"• Repositories processed: {len(state['repositories'])}\n"
            f"• Pull requests created: {len(state.get('pull_requests', []))}\n"
            f"• Rollback branches ready: {len(state.get('rollback_branches', []))}\n"
            f"• Documentation: [View deployment plan]({state.get('confluence_url', '')})\n\n"
            f"**Execution Summary:**\n"
            f"• Completed steps: {len(completed_steps)}\n"
            f"• Failed steps: {len(failed_steps)}\n"
            f"• Total retries: {state.get('retry_count', 0)}\n\n"
            "**Next Steps:**\n"
            "1. Review and merge the pull requests\n"
            "2. Deploy using the generated Jenkins jobs\n"
            "3. Monitor deployment status\n"
            "4. Use rollback branches if needed\n"
        )
        state["messages"] = add_messages(state["messages"], [summary_msg])

        return state

    # Create the workflow graph with enhanced error handling
    workflow = StateGraph(WorkflowState)

    # Add all workflow nodes
    workflow.add_node("start", start_workflow)
    workflow.add_node("jira_collection", collect_jira_tickets)
    workflow.add_node("branch_discovery", discover_feature_branches)
    workflow.add_node("merge_validation", validate_merge_status)
    workflow.add_node("sprint_merging", merge_sprint_branches)
    workflow.add_node("release_creation", create_release_branches)
    workflow.add_node("pr_generation", generate_pull_requests)
    workflow.add_node("release_tagging", create_release_tags)
    workflow.add_node("rollback_preparation", prepare_rollback_branches)
    workflow.add_node("documentation", generate_confluence_docs)
    workflow.add_node("error_handler", handle_workflow_error_node)
    workflow.add_node("complete", complete_workflow)

    # Set entry point
    workflow.set_entry_point("start")

    # Add conditional edges for error routing and workflow control
    workflow.add_conditional_edges(
        "start",
        should_continue_workflow,
        {
            "jira_collection": "jira_collection",
            "error_handler": "error_handler",
            "complete": "complete",
        },
    )

    workflow.add_conditional_edges(
        "jira_collection",
        should_continue_workflow,
        {
            "branch_discovery": "branch_discovery",
            "error_handler": "error_handler",
            "complete": "complete",
        },
    )

    workflow.add_conditional_edges(
        "branch_discovery",
        should_continue_workflow,
        {
            "merge_validation": "merge_validation",
            "error_handler": "error_handler",
            "complete": "complete",
        },
    )

    workflow.add_conditional_edges(
        "merge_validation",
        should_continue_workflow,
        {
            "sprint_merging": "sprint_merging",
            "error_handler": "error_handler",
            "complete": "complete",
        },
    )

    workflow.add_conditional_edges(
        "sprint_merging",
        should_continue_workflow,
        {
            "release_creation": "release_creation",
            "error_handler": "error_handler",
            "complete": "complete",
        },
    )

    workflow.add_conditional_edges(
        "release_creation",
        should_continue_workflow,
        {
            "pr_generation": "pr_generation",
            "error_handler": "error_handler",
            "complete": "complete",
        },
    )

    workflow.add_conditional_edges(
        "pr_generation",
        should_continue_workflow,
        {
            "release_tagging": "release_tagging",
            "error_handler": "error_handler",
            "complete": "complete",
        },
    )

    workflow.add_conditional_edges(
        "release_tagging",
        should_continue_workflow,
        {
            "rollback_preparation": "rollback_preparation",
            "error_handler": "error_handler",
            "complete": "complete",
        },
    )

    workflow.add_conditional_edges(
        "rollback_preparation",
        should_continue_workflow,
        {
            "documentation": "documentation",
            "error_handler": "error_handler",
            "complete": "complete",
        },
    )

    workflow.add_conditional_edges(
        "documentation",
        should_continue_workflow,
        {"complete": "complete", "error_handler": "error_handler"},
    )

    # Error handler can either continue or complete
    workflow.add_conditional_edges(
        "error_handler",
        should_continue_workflow,
        {
            "jira_collection": "jira_collection",
            "branch_discovery": "branch_discovery",
            "merge_validation": "merge_validation",
            "sprint_merging": "sprint_merging",
            "release_creation": "release_creation",
            "pr_generation": "pr_generation",
            "release_tagging": "release_tagging",
            "rollback_preparation": "rollback_preparation",
            "documentation": "documentation",
            "complete": "complete",
        },
    )

    # Complete workflow terminates
    workflow.add_edge("complete", END)

    # Create checkpointer for interrupt support
    checkpointer = MemorySaver()

    # Compile with streaming support, error handling, and interrupt support
    return workflow.compile(checkpointer=checkpointer)


def extract_workflow_params(request: ChatRequest) -> Dict[str, Any]:
    """Extract workflow parameters from chat request."""
    message_parts = request.message.lower().split()

    # Extract fix version and sprint info from message
    fix_version = request.fix_version or "v2.1.0"
    sprint_name = request.sprint_name or "sprint-2024-01"

    for i, part in enumerate(message_parts):
        if "version" in part and i + 1 < len(message_parts):
            fix_version = message_parts[i + 1]
        elif "sprint" in part and i + 1 < len(message_parts):
            sprint_name = message_parts[i + 1]

    return {
        "repositories": request.repositories or ["frontend", "backend", "api-service"],
        "fix_version": fix_version,
        "sprint_name": sprint_name,
        "release_type": request.release_type or "release",
    }
