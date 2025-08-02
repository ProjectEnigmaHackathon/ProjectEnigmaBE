"""
Real API Implementations

This module provides real implementations of all API integrations using
actual API clients for JIRA, GitHub, and Confluence.
"""

from .real_confluence import RealConfluenceClient
from .real_github import RealGitHubClient
from .real_jira import RealJiraClient

__all__ = ["RealJiraClient", "RealGitHubClient", "RealConfluenceClient"]
