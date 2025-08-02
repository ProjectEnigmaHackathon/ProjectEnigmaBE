"""
Jira Tools for LangGraph Workflows

This module provides tools for Jira operations that can be used
in LangGraph workflows, wrapping the Jira interface methods.
"""

import asyncio
from typing import Any, Dict, List, Optional

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from app.integrations.factory import create_api_clients


class GetTicketsByFixVersionInput(BaseModel):
    """Input for getting tickets by fix version."""
    fix_version: str = Field(description="Fix version to search for (e.g., 'v1.0.0')")
    project_keys: Optional[List[str]] = Field(default=None, description="Optional list of project keys to filter by")


class GetTicketInput(BaseModel):
    """Input for getting a specific ticket."""
    ticket_key: str = Field(description="Jira ticket key (e.g., 'PROJ-123')")


class SearchTicketsInput(BaseModel):
    """Input for searching tickets using JQL."""
    jql: str = Field(description="JQL (Jira Query Language) search string")
    max_results: int = Field(default=50, description="Maximum number of results to return")


class GetProjectsInput(BaseModel):
    """Input for getting all accessible projects."""
    pass


class ValidateConnectionInput(BaseModel):
    """Input for validating Jira connection."""
    pass


class JiraTools:
    """Collection of Jira tools for LangGraph workflows."""

    def __init__(self, use_mock: bool = True):
        """Initialize Jira tools with API clients."""
        self.clients = create_api_clients(use_mock=use_mock)
        self.jira_client = self.clients.jira

    async def _ensure_authenticated(self):
        """Ensure Jira client is authenticated."""
        if not hasattr(self.jira_client, '_authenticated') or not self.jira_client._authenticated:
            await self.jira_client.authenticate()

    class GetTicketsByFixVersionTool(BaseTool):
        """Tool for getting tickets by fix version."""
        name: str = "get_tickets_by_fix_version"
        description: str = "Get all Jira tickets for a specific fix version"
        args_schema: type = GetTicketsByFixVersionInput
        jira_tools: Any = None

        def __init__(self, jira_tools_instance):
            super().__init__(jira_tools=jira_tools_instance)

        def _run(self, fix_version: str, project_keys: Optional[List[str]] = None) -> Dict[str, Any]:
            """Get tickets by fix version (synchronous)."""
            import asyncio
            return asyncio.run(self._arun(fix_version, project_keys))

        async def _arun(self, fix_version: str, project_keys: Optional[List[str]] = None) -> Dict[str, Any]:
            """Get tickets by fix version."""
            await self.jira_tools._ensure_authenticated()
            tickets = await self.jira_tools.jira_client.get_tickets_by_fix_version(fix_version, project_keys)
            return {
                "fix_version": fix_version,
                "project_keys": project_keys,
                "ticket_count": len(tickets),
                "tickets": [
                    {
                        "key": ticket.key,
                        "summary": ticket.summary,
                        "status": ticket.status,
                        "assignee": ticket.assignee,
                        "fix_version": ticket.fix_version,
                        "issue_type": ticket.issue_type,
                        "created": ticket.created,
                        "updated": ticket.updated,
                        "description": ticket.description,
                        "project_key": ticket.project_key
                    }
                    for ticket in tickets
                ]
            }

    class GetTicketTool(BaseTool):
        """Tool for getting a specific ticket."""
        name: str = "get_ticket"
        description: str = "Get a specific Jira ticket by key"
        args_schema: type = GetTicketInput
        jira_tools: Any = None

        def __init__(self, jira_tools_instance):
            super().__init__(jira_tools=jira_tools_instance)

        def _run(self, ticket_key: str) -> Dict[str, Any]:
            """Get a specific ticket (synchronous)."""
            import asyncio
            return asyncio.run(self._arun(ticket_key))

        async def _arun(self, ticket_key: str) -> Dict[str, Any]:
            """Get a specific ticket."""
            await self.jira_tools._ensure_authenticated()
            ticket = await self.jira_tools.jira_client.get_ticket(ticket_key)
            if ticket:
                return {
                    "found": True,
                    "ticket": {
                        "key": ticket.key,
                        "summary": ticket.summary,
                        "status": ticket.status,
                        "assignee": ticket.assignee,
                        "fix_version": ticket.fix_version,
                        "issue_type": ticket.issue_type,
                        "created": ticket.created,
                        "updated": ticket.updated,
                        "description": ticket.description,
                        "project_key": ticket.project_key
                    }
                }
            else:
                return {"found": False, "error": f"Ticket '{ticket_key}' not found"}

    class SearchTicketsTool(BaseTool):
        """Tool for searching tickets using JQL."""
        name: str = "search_tickets"
        description: str = "Search Jira tickets using JQL (Jira Query Language)"
        args_schema: type = SearchTicketsInput
        jira_tools: Any = None

        def __init__(self, jira_tools_instance):
            super().__init__(jira_tools=jira_tools_instance)

        def _run(self, jql: str, max_results: int = 50) -> Dict[str, Any]:
            """Search tickets using JQL (synchronous)."""
            import asyncio
            return asyncio.run(self._arun(jql, max_results))

        async def _arun(self, jql: str, max_results: int = 50) -> Dict[str, Any]:
            """Search tickets using JQL."""
            await self.jira_tools._ensure_authenticated()
            tickets = await self.jira_tools.jira_client.search_tickets(jql, max_results)
            return {
                "jql": jql,
                "max_results": max_results,
                "ticket_count": len(tickets),
                "tickets": [
                    {
                        "key": ticket.key,
                        "summary": ticket.summary,
                        "status": ticket.status,
                        "assignee": ticket.assignee,
                        "fix_version": ticket.fix_version,
                        "issue_type": ticket.issue_type,
                        "created": ticket.created,
                        "updated": ticket.updated,
                        "description": ticket.description,
                        "project_key": ticket.project_key
                    }
                    for ticket in tickets
                ]
            }

    class GetProjectsTool(BaseTool):
        """Tool for getting all accessible projects."""
        name: str = "get_projects"
        description: str = "Get all accessible Jira projects"
        args_schema: type = GetProjectsInput
        jira_tools: Any = None

        def __init__(self, jira_tools_instance):
            super().__init__(jira_tools=jira_tools_instance)

        def _run(self) -> Dict[str, Any]:
            """Get projects (synchronous)."""
            import asyncio
            return asyncio.run(self._arun())

        async def _arun(self) -> Dict[str, Any]:
            """Get all accessible projects."""
            await self.jira_tools._ensure_authenticated()
            projects = await self.jira_tools.jira_client.get_projects()
            return {
                "project_count": len(projects),
                "projects": [
                    {
                        "key": project["key"],
                        "name": project["name"],
                        "description": project["description"],
                        "lead": project["lead"],
                        "project_category": project["projectCategory"]
                    }
                    for project in projects
                ]
            }

    class ValidateConnectionTool(BaseTool):
        """Tool for validating Jira connection."""
        name: str = "validate_jira_connection"
        description: str = "Validate the Jira API connection and get server information"
        args_schema: type = ValidateConnectionInput
        jira_tools: Any = None

        def __init__(self, jira_tools_instance):
            super().__init__(jira_tools=jira_tools_instance)

        def _run(self) -> Dict[str, Any]:
            """Validate Jira connection (synchronous)."""
            import asyncio
            return asyncio.run(self._arun())

        async def _arun(self) -> Dict[str, Any]:
            """Validate Jira connection."""
            await self.jira_tools._ensure_authenticated()
            connection_info = await self.jira_tools.jira_client.validate_connection()
            return {
                "status": "connected",
                "connection_info": connection_info
            }

    def get_tools(self) -> List[BaseTool]:
        """Get all Jira tools."""
        return [
            self.GetTicketsByFixVersionTool(self),
            self.GetTicketTool(self),
            self.SearchTicketsTool(self),
            self.GetProjectsTool(self),
            self.ValidateConnectionTool(self),
        ] 