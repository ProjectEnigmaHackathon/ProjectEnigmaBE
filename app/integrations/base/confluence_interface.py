"""
Confluence API Interface

Abstract base class defining the contract for Confluence API operations.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class ConfluencePage(BaseModel):
    """Confluence page model."""

    id: str
    title: str
    space_key: str
    url: str
    content: Optional[str] = None
    created_at: str
    updated_at: str
    author: str
    version: int


class ConfluenceSpace(BaseModel):
    """Confluence space model."""

    key: str
    name: str
    description: Optional[str] = None
    url: str
    type: str


class ConfluenceInterface(ABC):
    """Abstract interface for Confluence API operations."""

    @abstractmethod
    async def authenticate(self) -> bool:
        """
        Authenticate with Confluence API.

        Returns:
            bool: True if authentication successful, False otherwise
        """
        pass

    @abstractmethod
    async def get_spaces(self) -> List[ConfluenceSpace]:
        """
        Get all accessible spaces.

        Returns:
            List[ConfluenceSpace]: List of spaces
        """
        pass

    @abstractmethod
    async def get_page(self, page_id: str) -> Optional[ConfluencePage]:
        """
        Get a specific page by ID.

        Args:
            page_id: The page ID

        Returns:
            Optional[ConfluencePage]: The page if found, None otherwise
        """
        pass

    @abstractmethod
    async def create_page(
        self, space_key: str, title: str, content: str, parent_id: Optional[str] = None
    ) -> ConfluencePage:
        """
        Create a new page.

        Args:
            space_key: Space to create the page in
            title: Page title
            content: Page content (can be HTML or Confluence markup)
            parent_id: Optional parent page ID

        Returns:
            ConfluencePage: Created page
        """
        pass

    @abstractmethod
    async def update_page(
        self, page_id: str, title: str, content: str, version: int
    ) -> ConfluencePage:
        """
        Update an existing page.

        Args:
            page_id: Page ID to update
            title: New page title
            content: New page content
            version: Current page version (for optimistic locking)

        Returns:
            ConfluencePage: Updated page
        """
        pass

    @abstractmethod
    async def search_pages(
        self, space_key: str, title: Optional[str] = None
    ) -> List[ConfluencePage]:
        """
        Search for pages in a space.

        Args:
            space_key: Space to search in
            title: Optional title filter

        Returns:
            List[ConfluencePage]: List of matching pages
        """
        pass

    @abstractmethod
    async def delete_page(self, page_id: str) -> bool:
        """
        Delete a page.

        Args:
            page_id: Page ID to delete

        Returns:
            bool: True if deleted successfully, False otherwise
        """
        pass

    @abstractmethod
    async def create_deployment_page(
        self, space_key: str, release_version: str, repositories: List[Dict[str, Any]]
    ) -> ConfluencePage:
        """
        Create a standardized deployment documentation page.

        Args:
            space_key: Space to create the page in
            release_version: Release version (e.g., "v2.0.0")
            repositories: List of repository deployment information

        Returns:
            ConfluencePage: Created deployment page
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
