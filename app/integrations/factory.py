"""
API Integration Factory

Factory for creating API client instances with configuration-based switching
between mock and real implementations.
"""

import logging
from dataclasses import dataclass
from typing import Any, Dict, Tuple

from ..core.config import get_settings
from .auth_manager import AuthenticationManager

# Import interfaces
from .base import ConfluenceInterface, GitHubInterface, JiraInterface
from .exceptions import InvalidConfigurationError

# Import mock implementations
from .mock import MockConfluenceClient, MockGitHubClient, MockJiraClient

# Import real implementations (will be implemented next)
from .real import RealConfluenceClient, RealGitHubClient, RealJiraClient

logger = logging.getLogger(__name__)


@dataclass
class APIClients:
    """Container for all API client instances."""

    jira: JiraInterface
    github: GitHubInterface
    confluence: ConfluenceInterface
    auth_manager: AuthenticationManager


class APIClientFactory:
    """Factory for creating API client instances."""

    def __init__(self):
        self.settings = get_settings()
        self.auth_manager = AuthenticationManager()

    def _create_jira_client(self, use_mock: bool = None) -> JiraInterface:
        """Create JIRA client instance."""
        if use_mock is None:
            use_mock = self.settings.use_mock_apis

        if use_mock:
            logger.info("Creating mock JIRA client")
            return MockJiraClient(
                base_url=self.settings.jira_base_url,
                username=self.settings.jira_username,
                token=self.settings.jira_token,
            )
        else:
            logger.info("Creating real JIRA client")
            return RealJiraClient(
                base_url=self.settings.jira_base_url,
                username=self.settings.jira_username,
                token=self.settings.jira_token,
            )

    def _create_github_client(self, use_mock: bool = None) -> GitHubInterface:
        """Create GitHub client instance."""
        if use_mock is None:
            use_mock = self.settings.use_mock_apis

        if use_mock:
            logger.info("Creating mock GitHub client")
            return MockGitHubClient(
                token=self.settings.github_token,
                organization=self.settings.github_organization,
            )
        else:
            logger.info("Creating real GitHub client")
            return RealGitHubClient(
                token=self.settings.github_token,
                organization=self.settings.github_organization,
            )

    def _create_confluence_client(self, use_mock: bool = None) -> ConfluenceInterface:
        """Create Confluence client instance."""
        if use_mock is None:
            use_mock = self.settings.use_mock_apis

        if use_mock:
            logger.info("Creating mock Confluence client")
            return MockConfluenceClient(
                base_url=self.settings.confluence_base_url,
                username=self.settings.confluence_username,
                token=self.settings.confluence_token,
            )
        else:
            logger.info("Creating real Confluence client")
            return RealConfluenceClient(
                base_url=self.settings.confluence_base_url,
                username=self.settings.confluence_username,
                token=self.settings.confluence_token,
            )

    def create_client(
        self, service: str, use_mock: bool = None
    ) -> JiraInterface | GitHubInterface | ConfluenceInterface:
        """
        Create a single API client.

        Args:
            service: Service name (jira, github, confluence)
            use_mock: Override mock setting for this client

        Returns:
            API client instance

        Raises:
            InvalidConfigurationError: If service is unknown
        """
        if service == "jira":
            return self._create_jira_client(use_mock)
        elif service == "github":
            return self._create_github_client(use_mock)
        elif service == "confluence":
            return self._create_confluence_client(use_mock)
        else:
            raise InvalidConfigurationError(service, "unknown service")

    def create_all_clients(self, use_mock: bool = None) -> APIClients:
        """
        Create all API client instances.

        Args:
            use_mock: Override mock setting for all clients

        Returns:
            APIClients: Container with all client instances
        """
        logger.info(
            f"Creating API clients (use_mock: {use_mock or self.settings.use_mock_apis})"
        )

        return APIClients(
            jira=self._create_jira_client(use_mock),
            github=self._create_github_client(use_mock),
            confluence=self._create_confluence_client(use_mock),
            auth_manager=self.auth_manager,
        )

    async def validate_all_connections(
        self, use_mock: bool = None
    ) -> Dict[str, Dict[str, Any]]:
        """
        Validate connections for all API services.

        Args:
            use_mock: Override mock setting for validation

        Returns:
            Dict[str, Dict[str, Any]]: Validation results for all services
        """
        if use_mock is None:
            use_mock = self.settings.use_mock_apis

        if use_mock:
            logger.info("Validating mock API connections")
            # For mock APIs, just validate credential format
            results = {}
            for service in ["jira", "github", "confluence"]:
                is_valid, error_message = self.auth_manager.validate_credentials(
                    service
                )
                results[service] = {
                    "valid": is_valid,
                    "service": service,
                    "mock": True,
                    "error_message": error_message if not is_valid else None,
                }
            return results
        else:
            logger.info("Validating real API connections")
            # For real APIs, test actual connections
            validation_results = await self.auth_manager.validate_all_connections()
            return {
                service: {
                    "valid": result.valid,
                    "service": service,
                    "mock": False,
                    "error_message": result.error_message,
                    "user_info": result.user_info,
                }
                for service, result in validation_results.items()
            }

    def get_client_info(self, use_mock: bool = None) -> Dict[str, Any]:
        """
        Get information about client configuration.

        Args:
            use_mock: Override mock setting

        Returns:
            Dict[str, Any]: Client configuration information
        """
        if use_mock is None:
            use_mock = self.settings.use_mock_apis

        return {
            "use_mock_apis": use_mock,
            "environment": self.settings.environment,
            "services": {
                "jira": {
                    "mock": use_mock,
                    "configured": bool(
                        self.settings.jira_base_url
                        and self.settings.jira_username
                        and self.settings.jira_token
                    ),
                    "base_url": (
                        self.settings.jira_base_url if not use_mock else "mock://jira"
                    ),
                },
                "github": {
                    "mock": use_mock,
                    "configured": bool(self.settings.github_token),
                    "organization": (
                        self.settings.github_organization
                        if not use_mock
                        else "mock-org"
                    ),
                },
                "confluence": {
                    "mock": use_mock,
                    "configured": bool(
                        self.settings.confluence_base_url
                        and self.settings.confluence_username
                        and self.settings.confluence_token
                    ),
                    "base_url": (
                        self.settings.confluence_base_url
                        if not use_mock
                        else "mock://confluence"
                    ),
                },
            },
        }


# Global factory instance
_global_factory: APIClientFactory = None


def get_api_factory() -> APIClientFactory:
    """Get the global API factory instance."""
    global _global_factory
    if _global_factory is None:
        _global_factory = APIClientFactory()
    return _global_factory


def create_api_clients(use_mock: bool = None) -> APIClients:
    """
    Convenience function to create all API clients.

    Args:
        use_mock: Override mock setting

    Returns:
        APIClients: Container with all client instances
    """
    factory = get_api_factory()
    return factory.create_all_clients(use_mock)


async def validate_api_connections(use_mock: bool = None) -> Dict[str, Dict[str, Any]]:
    """
    Convenience function to validate all API connections.

    Args:
        use_mock: Override mock setting

    Returns:
        Dict[str, Dict[str, Any]]: Validation results
    """
    factory = get_api_factory()
    return await factory.validate_all_connections(use_mock)
