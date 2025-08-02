"""
Base API Interface Classes

This module defines the abstract base classes that all API implementations must follow.
"""

from .confluence_interface import ConfluenceInterface
from .github_interface import GitHubInterface
from .jira_interface import JiraInterface

__all__ = ["JiraInterface", "GitHubInterface", "ConfluenceInterface"]
