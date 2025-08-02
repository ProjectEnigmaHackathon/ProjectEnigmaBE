"""
JIRA API Interface

Abstract base class defining the contract for JIRA API operations.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class JiraTicket(BaseModel):
    """JIRA ticket model."""

    key: str
    summary: str
    status: str
    assignee: Optional[str] = None
    fix_version: Optional[str] = None
    issue_type: str
    created: str
    updated: str
    description: Optional[str] = None
    project_key: str


class JiraInterface(ABC):
    """Abstract interface for JIRA API operations."""

    @abstractmethod
    async def authenticate(self) -> bool:
        """
        Authenticate with JIRA API.

        Returns:
            bool: True if authentication successful, False otherwise
        """
        pass

    @abstractmethod
    async def get_tickets_by_fix_version(
        self, fix_version: str, project_keys: Optional[List[str]] = None
    ) -> List[JiraTicket]:
        """
        Get all tickets for a specific fix version.

        Args:
            fix_version: The fix version to filter by
            project_keys: Optional list of project keys to filter by

        Returns:
            List[JiraTicket]: List of tickets matching the fix version
        """
        pass

    @abstractmethod
    async def get_ticket(self, ticket_key: str) -> Optional[JiraTicket]:
        """
        Get a specific ticket by key.

        Args:
            ticket_key: The JIRA ticket key (e.g., "PROJ-123")

        Returns:
            Optional[JiraTicket]: The ticket if found, None otherwise
        """
        pass

    @abstractmethod
    async def search_tickets(self, jql: str, max_results: int = 50) -> List[JiraTicket]:
        """
        Search tickets using JQL.

        Args:
            jql: The JQL query string
            max_results: Maximum number of results to return

        Returns:
            List[JiraTicket]: List of tickets matching the query
        """
        pass

    @abstractmethod
    async def get_projects(self) -> List[Dict[str, Any]]:
        """
        Get all accessible projects.

        Returns:
            List[Dict[str, Any]]: List of project information
        """
        pass

    @abstractmethod
    async def validate_connection(self) -> Dict[str, Any]:
        """
        Validate the connection and return server information.

        Returns:
            Dict[str, Any]: Server information and connection status
        """
        pass
