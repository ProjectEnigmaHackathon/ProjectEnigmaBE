"""
Mock JIRA API Implementation

Provides realistic mock responses for JIRA API operations.
"""

import asyncio
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from ..base.jira_interface import JiraInterface, JiraTicket


class MockJiraClient(JiraInterface):
    """Mock implementation of JIRA API client."""

    def __init__(self, base_url: str = "", username: str = "", token: str = ""):
        self.base_url = base_url
        self.username = username
        self.token = token
        self._authenticated = False

        # Mock data
        self._mock_tickets = self._generate_mock_tickets()
        self._mock_projects = self._generate_mock_projects()

    def _generate_mock_tickets(self) -> List[JiraTicket]:
        """Generate realistic mock ticket data."""
        base_date = datetime.now() - timedelta(days=30)

        tickets = []
        projects = ["PROJ", "API", "UI", "CORE"]
        statuses = ["To Do", "In Progress", "Code Review", "Testing", "Done"]
        issue_types = ["Story", "Task", "Bug", "Epic"]

        for i in range(1, 26):  # Generate 25 tickets
            project = projects[i % len(projects)]
            created_date = (base_date + timedelta(days=i)).isoformat()
            updated_date = (base_date + timedelta(days=i, hours=2)).isoformat()

            ticket = JiraTicket(
                key=f"{project}-{i:03d}",
                summary=f"Implement feature {i} for release automation",
                status=statuses[i % len(statuses)],
                assignee=f"developer{(i % 5) + 1}@company.com" if i % 3 != 0 else None,
                fix_version="v2.0.0" if i <= 15 else "v2.1.0" if i <= 20 else None,
                issue_type=issue_types[i % len(issue_types)],
                created=created_date,
                updated=updated_date,
                description=f"This is a detailed description for {project}-{i:03d}. "
                f"It includes acceptance criteria and implementation details.",
                project_key=project,
            )
            tickets.append(ticket)

        return tickets

    def _generate_mock_projects(self) -> List[Dict[str, Any]]:
        """Generate mock project data."""
        return [
            {
                "key": "PROJ",
                "name": "Project Enigma",
                "description": "Main project for release automation",
            },
            {
                "key": "API",
                "name": "API Services",
                "description": "Backend API development",
            },
            {
                "key": "UI",
                "name": "User Interface",
                "description": "Frontend development",
            },
            {
                "key": "CORE",
                "name": "Core Platform",
                "description": "Core platform services",
            },
        ]

    async def authenticate(self) -> bool:
        """Mock authentication - always succeeds."""
        await asyncio.sleep(0.1)  # Simulate network delay
        self._authenticated = True
        return True

    async def get_tickets_by_fix_version(
        self, fix_version: str, project_keys: Optional[List[str]] = None
    ) -> List[JiraTicket]:
        """Get mock tickets for a specific fix version."""
        await asyncio.sleep(0.2)  # Simulate API delay

        filtered_tickets = [
            ticket for ticket in self._mock_tickets if ticket.fix_version == fix_version
        ]

        if project_keys:
            filtered_tickets = [
                ticket
                for ticket in filtered_tickets
                if ticket.project_key in project_keys
            ]

        return filtered_tickets

    async def get_ticket(self, ticket_key: str) -> Optional[JiraTicket]:
        """Get a specific mock ticket."""
        await asyncio.sleep(0.1)  # Simulate API delay

        for ticket in self._mock_tickets:
            if ticket.key == ticket_key:
                return ticket
        return None

    async def search_tickets(self, jql: str, max_results: int = 50) -> List[JiraTicket]:
        """Search mock tickets using simplified JQL."""
        await asyncio.sleep(0.3)  # Simulate API delay

        # Simple JQL parsing for mock purposes
        results = self._mock_tickets.copy()

        if "fixVersion" in jql:
            # Extract fix version from JQL
            parts = jql.split("fixVersion")
            if len(parts) > 1:
                version_part = parts[1].strip()
                if "=" in version_part:
                    version = version_part.split("=")[1].strip().strip("\"'")
                    results = [t for t in results if t.fix_version == version]

        if "project" in jql.lower():
            # Extract project from JQL
            parts = jql.lower().split("project")
            if len(parts) > 1:
                project_part = parts[1].strip()
                if "=" in project_part:
                    project = project_part.split("=")[1].strip().strip("\"'").upper()
                    results = [t for t in results if t.project_key == project]

        return results[:max_results]

    async def get_projects(self) -> List[Dict[str, Any]]:
        """Get mock project information."""
        await asyncio.sleep(0.1)  # Simulate API delay
        return self._mock_projects

    async def validate_connection(self) -> Dict[str, Any]:
        """Validate mock connection."""
        await asyncio.sleep(0.1)  # Simulate API delay
        return {
            "status": "connected",
            "server_title": "Mock JIRA Server",
            "version": "9.4.0",
            "base_url": self.base_url or "https://mock-jira.company.com",
            "user": self.username or "mock-user@company.com",
        }
