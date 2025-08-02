"""
Authentication Manager

Handles secure credential management and token validation for all API integrations.
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Tuple

from ..core.config import get_settings
from .exceptions import (
    AuthenticationError,
    ConfluenceAuthenticationError,
    GitHubAuthenticationError,
    InvalidConfigurationError,
    JiraAuthenticationError,
)

logger = logging.getLogger(__name__)


@dataclass
class APICredentials:
    """Container for API credentials."""

    service: str
    base_url: Optional[str] = None
    username: Optional[str] = None
    token: Optional[str] = None
    organization: Optional[str] = None

    def is_valid(self) -> bool:
        """Check if credentials are valid."""
        if self.service == "jira":
            return bool(self.base_url and self.username and self.token)
        elif self.service == "github":
            return bool(self.token)
        elif self.service == "confluence":
            return bool(self.base_url and self.username and self.token)
        return False


@dataclass
class ValidationResult:
    """Result of credential validation."""

    valid: bool
    service: str
    error_message: Optional[str] = None
    user_info: Optional[Dict[str, Any]] = None
    validated_at: Optional[datetime] = None


class AuthenticationManager:
    """Manages authentication and credential validation for all API services."""

    def __init__(self):
        self.settings = get_settings()
        self._validation_cache: Dict[str, ValidationResult] = {}
        self._cache_ttl = timedelta(
            minutes=15
        )  # Cache validation results for 15 minutes

    def get_credentials(self, service: str) -> APICredentials:
        """
        Get credentials for a specific service.

        Args:
            service: Service name (jira, github, confluence)

        Returns:
            APICredentials: Credentials for the service

        Raises:
            InvalidConfigurationError: If service is unknown or credentials are missing
        """
        if service == "jira":
            return APICredentials(
                service="jira",
                base_url=self.settings.jira_base_url,
                username=self.settings.jira_username,
                token=self.settings.jira_token,
            )
        elif service == "github":
            return APICredentials(
                service="github",
                token=self.settings.github_token,
                organization=self.settings.github_organization,
            )
        elif service == "confluence":
            return APICredentials(
                service="confluence",
                base_url=self.settings.confluence_base_url,
                username=self.settings.confluence_username,
                token=self.settings.confluence_token,
            )
        else:
            raise InvalidConfigurationError(service, "unknown service")

    def validate_credentials(self, service: str) -> Tuple[bool, str]:
        """
        Validate credentials for a service without making API calls.

        Args:
            service: Service name to validate

        Returns:
            Tuple[bool, str]: (is_valid, error_message)
        """
        try:
            credentials = self.get_credentials(service)

            if not credentials.is_valid():
                missing_fields = []
                if service == "jira":
                    if not credentials.base_url:
                        missing_fields.append("base_url")
                    if not credentials.username:
                        missing_fields.append("username")
                    if not credentials.token:
                        missing_fields.append("token")
                elif service == "github":
                    if not credentials.token:
                        missing_fields.append("token")
                elif service == "confluence":
                    if not credentials.base_url:
                        missing_fields.append("base_url")
                    if not credentials.username:
                        missing_fields.append("username")
                    if not credentials.token:
                        missing_fields.append("token")

                return (
                    False,
                    f"Missing required fields for {service}: {', '.join(missing_fields)}",
                )

            return True, ""

        except Exception as e:
            return False, str(e)

    def _is_cache_valid(self, service: str) -> bool:
        """Check if cached validation result is still valid."""
        if service not in self._validation_cache:
            return False

        result = self._validation_cache[service]
        if not result.validated_at:
            return False

        return datetime.now() - result.validated_at < self._cache_ttl

    async def validate_connection(
        self, service: str, force_refresh: bool = False
    ) -> ValidationResult:
        """
        Validate connection to a service by making a test API call.

        Args:
            service: Service name to validate
            force_refresh: Skip cache and force fresh validation

        Returns:
            ValidationResult: Validation result with connection status
        """
        # Check cache first
        if not force_refresh and self._is_cache_valid(service):
            logger.info(f"Using cached validation result for {service}")
            return self._validation_cache[service]

        logger.info(f"Validating connection to {service}")

        # Validate credentials format first
        is_valid, error_message = self.validate_credentials(service)
        if not is_valid:
            result = ValidationResult(
                valid=False,
                service=service,
                error_message=error_message,
                validated_at=datetime.now(),
            )
            self._validation_cache[service] = result
            return result

        # Test actual connection
        try:
            credentials = self.get_credentials(service)

            if service == "jira":
                user_info = await self._test_jira_connection(credentials)
            elif service == "github":
                user_info = await self._test_github_connection(credentials)
            elif service == "confluence":
                user_info = await self._test_confluence_connection(credentials)
            else:
                raise InvalidConfigurationError(service, "unknown service")

            result = ValidationResult(
                valid=True,
                service=service,
                user_info=user_info,
                validated_at=datetime.now(),
            )

        except Exception as e:
            logger.error(f"Connection validation failed for {service}: {str(e)}")
            result = ValidationResult(
                valid=False,
                service=service,
                error_message=str(e),
                validated_at=datetime.now(),
            )

        # Cache the result
        self._validation_cache[service] = result
        return result

    async def _test_jira_connection(
        self, credentials: APICredentials
    ) -> Dict[str, Any]:
        """Test JIRA connection."""
        try:
            from jira import JIRA

            # Create JIRA client
            jira_client = JIRA(
                server=credentials.base_url,
                basic_auth=(credentials.username, credentials.token),
            )

            # Test connection by getting server info
            server_info = jira_client.server_info()
            user = jira_client.user(credentials.username)

            return {
                "server_title": server_info.get("serverTitle", "Unknown"),
                "version": server_info.get("version", "Unknown"),
                "user": credentials.username,
                "display_name": user.displayName if user else credentials.username,
            }

        except Exception as e:
            raise JiraAuthenticationError(f"JIRA connection test failed: {str(e)}")

    async def _test_github_connection(
        self, credentials: APICredentials
    ) -> Dict[str, Any]:
        """Test GitHub connection."""
        try:
            from github import Github

            # Create GitHub client
            github_client = Github(credentials.token)

            # Test connection by getting user info
            user = github_client.get_user()

            return {
                "login": user.login,
                "name": user.name or user.login,
                "email": user.email,
                "organizations": [org.login for org in user.get_orgs()],
            }

        except Exception as e:
            raise GitHubAuthenticationError(f"GitHub connection test failed: {str(e)}")

    async def _test_confluence_connection(
        self, credentials: APICredentials
    ) -> Dict[str, Any]:
        """Test Confluence connection."""
        try:
            from atlassian import Confluence

            # Create Confluence client
            confluence_client = Confluence(
                url=credentials.base_url,
                username=credentials.username,
                password=credentials.token,
                cloud=True,  # Assume cloud instance
            )

            # Test connection by getting user info and server info
            user_info = confluence_client.get_current_user()

            return {
                "user": credentials.username,
                "display_name": user_info.get("displayName", credentials.username),
                "account_id": user_info.get("accountId"),
                "base_url": credentials.base_url,
            }

        except Exception as e:
            raise ConfluenceAuthenticationError(
                f"Confluence connection test failed: {str(e)}"
            )

    async def validate_all_connections(
        self, force_refresh: bool = False
    ) -> Dict[str, ValidationResult]:
        """
        Validate connections to all configured services.

        Args:
            force_refresh: Skip cache and force fresh validation

        Returns:
            Dict[str, ValidationResult]: Validation results for all services
        """
        services = ["jira", "github", "confluence"]
        tasks = [
            self.validate_connection(service, force_refresh) for service in services
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        validation_results = {}
        for service, result in zip(services, results):
            if isinstance(result, Exception):
                validation_results[service] = ValidationResult(
                    valid=False,
                    service=service,
                    error_message=str(result),
                    validated_at=datetime.now(),
                )
            else:
                validation_results[service] = result

        return validation_results

    def clear_cache(self, service: Optional[str] = None):
        """
        Clear validation cache.

        Args:
            service: Optional service to clear cache for. If None, clears all.
        """
        if service:
            self._validation_cache.pop(service, None)
            logger.info(f"Cleared validation cache for {service}")
        else:
            self._validation_cache.clear()
            logger.info("Cleared all validation cache")

    def get_cache_status(self) -> Dict[str, Dict[str, Any]]:
        """Get status of validation cache."""
        status = {}
        now = datetime.now()

        for service, result in self._validation_cache.items():
            if result.validated_at:
                age = now - result.validated_at
                is_valid = age < self._cache_ttl
            else:
                age = None
                is_valid = False

            status[service] = {
                "cached": True,
                "valid": result.valid,
                "age_seconds": age.total_seconds() if age else None,
                "cache_valid": is_valid,
                "validated_at": (
                    result.validated_at.isoformat() if result.validated_at else None
                ),
            }

        return status
