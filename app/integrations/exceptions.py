"""
API Integration Exceptions

Custom exception classes for API integration errors with specific error handling
strategies and user-friendly error messages.
"""

from typing import Any, Dict, Optional


class APIIntegrationError(Exception):
    """Base exception for all API integration errors."""

    def __init__(
        self,
        message: str,
        error_code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.details = details or {}


class AuthenticationError(APIIntegrationError):
    """Raised when API authentication fails."""

    def __init__(
        self,
        service: str,
        message: Optional[str] = None,
        error_code: Optional[str] = None,
    ):
        self.service = service
        default_message = (
            f"Authentication failed for {service}. Please check your credentials."
        )
        super().__init__(message or default_message, error_code)


class RateLimitError(APIIntegrationError):
    """Raised when API rate limits are exceeded."""

    def __init__(
        self,
        service: str,
        retry_after: Optional[int] = None,
        message: Optional[str] = None,
    ):
        self.service = service
        self.retry_after = retry_after
        default_message = f"Rate limit exceeded for {service}"
        if retry_after:
            default_message += f". Retry after {retry_after} seconds."
        super().__init__(message or default_message)


class APIConnectionError(APIIntegrationError):
    """Raised when API connection fails."""

    def __init__(
        self,
        service: str,
        endpoint: Optional[str] = None,
        message: Optional[str] = None,
    ):
        self.service = service
        self.endpoint = endpoint
        default_message = f"Failed to connect to {service}"
        if endpoint:
            default_message += f" at {endpoint}"
        super().__init__(message or default_message)


class ResourceNotFoundError(APIIntegrationError):
    """Raised when a requested resource is not found."""

    def __init__(
        self,
        service: str,
        resource_type: str,
        resource_id: str,
        message: Optional[str] = None,
    ):
        self.service = service
        self.resource_type = resource_type
        self.resource_id = resource_id
        default_message = f"{resource_type} '{resource_id}' not found in {service}"
        super().__init__(message or default_message)


class InvalidConfigurationError(APIIntegrationError):
    """Raised when API configuration is invalid."""

    def __init__(self, service: str, config_field: str, message: Optional[str] = None):
        self.service = service
        self.config_field = config_field
        default_message = f"Invalid configuration for {service}: {config_field}"
        super().__init__(message or default_message)


class PermissionError(APIIntegrationError):
    """Raised when API operation is not permitted."""

    def __init__(self, service: str, operation: str, message: Optional[str] = None):
        self.service = service
        self.operation = operation
        default_message = f"Permission denied for {operation} in {service}"
        super().__init__(message or default_message)


# JIRA-specific exceptions
class JiraError(APIIntegrationError):
    """Base exception for JIRA API errors."""

    pass


class JiraAuthenticationError(AuthenticationError):
    """JIRA authentication error."""

    def __init__(self, message: Optional[str] = None):
        super().__init__("JIRA", message)


class JiraTicketNotFoundError(ResourceNotFoundError):
    """JIRA ticket not found error."""

    def __init__(self, ticket_key: str, message: Optional[str] = None):
        super().__init__("JIRA", "ticket", ticket_key, message)


class JiraProjectNotFoundError(ResourceNotFoundError):
    """JIRA project not found error."""

    def __init__(self, project_key: str, message: Optional[str] = None):
        super().__init__("JIRA", "project", project_key, message)


# GitHub-specific exceptions
class GitHubError(APIIntegrationError):
    """Base exception for GitHub API errors."""

    pass


class GitHubAuthenticationError(AuthenticationError):
    """GitHub authentication error."""

    def __init__(self, message: Optional[str] = None):
        super().__init__("GitHub", message)


class GitHubRepositoryNotFoundError(ResourceNotFoundError):
    """GitHub repository not found error."""

    def __init__(self, repo_name: str, message: Optional[str] = None):
        super().__init__("GitHub", "repository", repo_name, message)


class GitHubBranchNotFoundError(ResourceNotFoundError):
    """GitHub branch not found error."""

    def __init__(self, branch_name: str, message: Optional[str] = None):
        super().__init__("GitHub", "branch", branch_name, message)


class GitHubMergeConflictError(APIIntegrationError):
    """GitHub merge conflict error."""

    def __init__(
        self,
        source_branch: str,
        target_branch: str,
        repo_name: str,
        message: Optional[str] = None,
    ):
        self.source_branch = source_branch
        self.target_branch = target_branch
        self.repo_name = repo_name
        default_message = f"Merge conflict when merging {source_branch} into {target_branch} in {repo_name}"
        super().__init__(message or default_message)


# Confluence-specific exceptions
class ConfluenceError(APIIntegrationError):
    """Base exception for Confluence API errors."""

    pass


class ConfluenceAuthenticationError(AuthenticationError):
    """Confluence authentication error."""

    def __init__(self, message: Optional[str] = None):
        super().__init__("Confluence", message)


class ConfluenceSpaceNotFoundError(ResourceNotFoundError):
    """Confluence space not found error."""

    def __init__(self, space_key: str, message: Optional[str] = None):
        super().__init__("Confluence", "space", space_key, message)


class ConfluencePageNotFoundError(ResourceNotFoundError):
    """Confluence page not found error."""

    def __init__(self, page_id: str, message: Optional[str] = None):
        super().__init__("Confluence", "page", page_id, message)


class ConfluencePageVersionError(APIIntegrationError):
    """Confluence page version conflict error."""

    def __init__(
        self,
        page_id: str,
        expected_version: int,
        actual_version: int,
        message: Optional[str] = None,
    ):
        self.page_id = page_id
        self.expected_version = expected_version
        self.actual_version = actual_version
        default_message = (
            f"Page version conflict for page {page_id}. "
            f"Expected version {expected_version}, but current version is {actual_version}"
        )
        super().__init__(message or default_message)


# Rate limiting specific exceptions
class JiraRateLimitError(RateLimitError):
    """JIRA rate limit error."""

    def __init__(
        self, retry_after: Optional[int] = None, message: Optional[str] = None
    ):
        super().__init__("JIRA", retry_after, message)


class GitHubRateLimitError(RateLimitError):
    """GitHub rate limit error."""

    def __init__(
        self, retry_after: Optional[int] = None, message: Optional[str] = None
    ):
        super().__init__("GitHub", retry_after, message)


class ConfluenceRateLimitError(RateLimitError):
    """Confluence rate limit error."""

    def __init__(
        self, retry_after: Optional[int] = None, message: Optional[str] = None
    ):
        super().__init__("Confluence", retry_after, message)
