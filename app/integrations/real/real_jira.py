"""
Real JIRA API Implementation

Provides real JIRA API integration using the python-jira library.
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from jira import JIRA
from jira.exceptions import JIRAError

from ..auth_manager import AuthenticationManager
from ..base.jira_interface import JiraInterface, JiraTicket
from ..exceptions import APIConnectionError, JiraAuthenticationError
from ..exceptions import JiraError as CustomJiraError
from ..exceptions import (
    JiraProjectNotFoundError,
    JiraRateLimitError,
    JiraTicketNotFoundError,
)
from ..rate_limiter import get_rate_limiter
from ...core.config import get_settings

logger = logging.getLogger(__name__)


class RealJiraClient(JiraInterface):
    """Real implementation of JIRA API client using python-jira."""

    def __init__(self, base_url: str, username: str, token: str):
        self.base_url = base_url
        self.username = username
        self.token = token
        self._client: Optional[JIRA] = None
        self._authenticated = False
        self.rate_limiter = get_rate_limiter()

    def _get_client(self) -> JIRA:
        """Get or create JIRA client instance."""
        if self._client is None:
            try:
                self._client = JIRA(
                    server=self.base_url,
                    basic_auth=(self.username, self.token),
                    timeout=30,
                )
            except Exception as e:
                logger.error(f"Failed to create JIRA client: {str(e)}")
                raise APIConnectionError("JIRA", self.base_url, str(e))

        return self._client

    def _convert_jira_issue_to_ticket(self, issue) -> JiraTicket:
        """Convert JIRA issue object to JiraTicket model."""
        try:
            # Extract fix version
            fix_version = None
            if hasattr(issue.fields, "fixVersions") and issue.fields.fixVersions:
                fix_version = issue.fields.fixVersions[0].name

            # Extract assignee
            assignee = None
            if hasattr(issue.fields, "assignee") and issue.fields.assignee:
                assignee = (
                    issue.fields.assignee.emailAddress
                    or issue.fields.assignee.displayName
                )

            return JiraTicket(
                key=issue.key,
                summary=issue.fields.summary,
                status=issue.fields.status.name,
                assignee=assignee,
                fix_version=fix_version,
                issue_type=issue.fields.issuetype.name,
                created=issue.fields.created,
                updated=issue.fields.updated,
                description=getattr(issue.fields, "description", ""),
                project_key=issue.fields.project.key,
            )
        except Exception as e:
            logger.error(f"Failed to convert JIRA issue {issue.key}: {str(e)}")
            raise CustomJiraError(f"Failed to parse JIRA issue: {str(e)}")

    async def authenticate(self) -> bool:
        """Authenticate with JIRA API."""
        try:
            await self.rate_limiter.acquire("jira", "auth")

            client = self._get_client()

            # Test authentication by getting server info
            await asyncio.get_event_loop().run_in_executor(
                None, lambda: client.server_info()
            )

            self._authenticated = True
            logger.info(f"Successfully authenticated with JIRA at {self.base_url}")
            return True

        except JIRAError as e:
            logger.error(f"JIRA authentication failed: {str(e)}")
            if e.status_code == 401:
                raise JiraAuthenticationError("Invalid username or token")
            elif e.status_code == 403:
                raise JiraAuthenticationError("Access forbidden - check permissions")
            else:
                raise JiraAuthenticationError(f"Authentication failed: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error during JIRA authentication: {str(e)}")
            raise APIConnectionError("JIRA", self.base_url, str(e))

    async def get_tickets_by_fix_version(
        self, fix_version: str, project_keys: Optional[List[str]] = None
    ) -> List[JiraTicket]:
        """Get all tickets for a specific fix version."""
        try:
            await self.rate_limiter.acquire("jira", "search")

            client = self._get_client()

            # Build JQL query
            jql_parts = [f'fixVersion = "{fix_version}"']

            if project_keys:
                project_filter = " OR ".join(
                    [f'project = "{key}"' for key in project_keys]
                )
                jql_parts.append(f"({project_filter})")

            jql = " AND ".join(jql_parts)

            logger.info(f"Searching JIRA tickets with JQL: {jql}")

            # Execute search
            issues = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: client.search_issues(jql, maxResults=1000, expand="changelog"),
            )

            # Convert to tickets
            tickets = []
            for issue in issues:
                try:
                    ticket = self._convert_jira_issue_to_ticket(issue)
                    tickets.append(ticket)
                except Exception as e:
                    logger.warning(f"Failed to convert issue {issue.key}: {str(e)}")
                    continue

            logger.info(f"Found {len(tickets)} tickets for fix version {fix_version}")
            return tickets

        except JIRAError as e:
            logger.error(f"JIRA search failed: {str(e)}")
            if e.status_code == 429:
                raise JiraRateLimitError()
            elif e.status_code == 401:
                raise JiraAuthenticationError("Authentication expired")
            else:
                raise CustomJiraError(f"Search failed: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error during JIRA search: {str(e)}")
            raise CustomJiraError(f"Search failed: {str(e)}")

    async def get_ticket(self, ticket_key: str) -> Optional[JiraTicket]:
        """Get a specific ticket by key."""
        try:
            await self.rate_limiter.acquire("jira", "get_issue")

            client = self._get_client()

            # Get issue
            issue = await asyncio.get_event_loop().run_in_executor(
                None, lambda: client.issue(ticket_key, expand="changelog")
            )

            return self._convert_jira_issue_to_ticket(issue)

        except JIRAError as e:
            if e.status_code == 404:
                logger.warning(f"JIRA ticket not found: {ticket_key}")
                return None
            elif e.status_code == 429:
                raise JiraRateLimitError()
            elif e.status_code == 401:
                raise JiraAuthenticationError("Authentication expired")
            else:
                logger.error(f"JIRA get ticket failed: {str(e)}")
                raise CustomJiraError(f"Failed to get ticket {ticket_key}: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error getting JIRA ticket {ticket_key}: {str(e)}")
            raise CustomJiraError(f"Failed to get ticket: {str(e)}")

    async def search_tickets(self, jql: str, max_results: int = 50) -> List[JiraTicket]:
        """Search tickets using JQL."""
        try:
            await self.rate_limiter.acquire("jira", "search")

            client = self._get_client()

            logger.info(f"Executing JQL search: {jql}")

            # Execute search
            issues = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: client.search_issues(
                    jql, maxResults=max_results, expand="changelog"
                ),
            )

            # Convert to tickets
            tickets = []
            for issue in issues:
                try:
                    ticket = self._convert_jira_issue_to_ticket(issue)
                    tickets.append(ticket)
                except Exception as e:
                    logger.warning(f"Failed to convert issue {issue.key}: {str(e)}")
                    continue

            logger.info(f"JQL search returned {len(tickets)} tickets")
            return tickets

        except JIRAError as e:
            logger.error(f"JIRA JQL search failed: {str(e)}")
            if e.status_code == 429:
                raise JiraRateLimitError()
            elif e.status_code == 401:
                raise JiraAuthenticationError("Authentication expired")
            else:
                raise CustomJiraError(f"JQL search failed: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error during JQL search: {str(e)}")
            raise CustomJiraError(f"JQL search failed: {str(e)}")

    async def get_projects(self) -> List[Dict[str, Any]]:
        """Get all accessible projects."""
        try:
            await self.rate_limiter.acquire("jira", "get_projects")

            client = self._get_client()

            # Get projects
            projects = await asyncio.get_event_loop().run_in_executor(
                None, lambda: client.projects()
            )

            # Convert to dict format
            project_list = []
            for project in projects:
                project_dict = {
                    "key": project.key,
                    "name": project.name,
                    "description": getattr(project, "description", ""),
                    "lead": getattr(project, "lead", {}).get("displayName", ""),
                    "projectCategory": getattr(project, "projectCategory", {}).get(
                        "name", ""
                    ),
                }
                project_list.append(project_dict)

            logger.info(f"Retrieved {len(project_list)} JIRA projects")
            return project_list

        except JIRAError as e:
            logger.error(f"JIRA get projects failed: {str(e)}")
            if e.status_code == 429:
                raise JiraRateLimitError()
            elif e.status_code == 401:
                raise JiraAuthenticationError("Authentication expired")
            else:
                raise CustomJiraError(f"Failed to get projects: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error getting JIRA projects: {str(e)}")
            raise CustomJiraError(f"Failed to get projects: {str(e)}")

    async def validate_connection(self) -> Dict[str, Any]:
        """Validate the connection and return server information."""
        try:
            await self.rate_limiter.acquire("jira", "server_info")

            client = self._get_client()

            # Get server info and user info
            server_info = await asyncio.get_event_loop().run_in_executor(
                None, lambda: client.server_info()
            )

            settings = get_settings()
            user = await asyncio.get_event_loop().run_in_executor(
                None, lambda: client.user(settings.atlassian_account_id)
            )

            return {
                "status": "connected",
                "server_title": server_info.get("serverTitle", "Unknown"),
                "version": server_info.get("version", "Unknown"),
                "base_url": self.base_url,
                "user": self.username,
                "display_name": user.displayName if user else self.username,
                "deployment_type": server_info.get("deploymentType", "Unknown"),
            }

        except JIRAError as e:
            logger.error(f"JIRA connection validation failed: {str(e)}")
            if e.status_code == 401:
                raise JiraAuthenticationError("Invalid credentials")
            else:
                raise CustomJiraError(f"Connection validation failed: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error validating JIRA connection: {str(e)}")
            raise APIConnectionError("JIRA", self.base_url, str(e))
