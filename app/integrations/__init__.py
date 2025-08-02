"""
API Integration Layer

This module provides the API integration layer for Project Enigma, supporting
both mock and real API implementations with configuration-based switching.
"""

from .auth_manager import AuthenticationManager
from .exceptions import (
    APIIntegrationError,
    AuthenticationError,
    ConfluenceError,
    GitHubError,
    JiraError,
    RateLimitError,
)
from .factory import create_api_clients, get_api_factory, validate_api_connections
from .rate_limiter import get_rate_limiter

__all__ = [
    "create_api_clients",
    "validate_api_connections",
    "get_api_factory",
    "AuthenticationManager",
    "get_rate_limiter",
    "APIIntegrationError",
    "AuthenticationError",
    "RateLimitError",
    "JiraError",
    "GitHubError",
    "ConfluenceError",
]
