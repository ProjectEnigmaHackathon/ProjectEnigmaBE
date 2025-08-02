"""
Confluence Tools for LangGraph Workflows

This module provides tools for Confluence operations that can be used
in LangGraph workflows, wrapping the Confluence interface methods.
"""

import asyncio
from typing import Any, Dict, List, Optional

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from app.integrations.factory import create_api_clients


class GetSpacesInput(BaseModel):
    """Input for getting all accessible spaces."""
    pass


class GetPageInput(BaseModel):
    """Input for getting a specific page."""
    page_id: str = Field(description="Confluence page ID")


class CreatePageInput(BaseModel):
    """Input for creating a new page."""
    space_key: str = Field(description="Confluence space key")
    title: str = Field(description="Page title")
    content: str = Field(description="Page content in HTML format")
    parent_id: Optional[str] = Field(default=None, description="Optional parent page ID")


class UpdatePageInput(BaseModel):
    """Input for updating an existing page."""
    page_id: str = Field(description="Confluence page ID")
    title: str = Field(description="Page title")
    content: str = Field(description="Page content in HTML format")
    version: int = Field(description="Current page version number")


class SearchPagesInput(BaseModel):
    """Input for searching pages in a space."""
    space_key: str = Field(description="Confluence space key")
    title: Optional[str] = Field(default=None, description="Optional title to search for")


class DeletePageInput(BaseModel):
    """Input for deleting a page."""
    page_id: str = Field(description="Confluence page ID")


class CreateDeploymentPageInput(BaseModel):
    """Input for creating a deployment documentation page."""
    space_key: str = Field(description="Confluence space key")
    release_version: str = Field(description="Release version (e.g., 'v1.0.0')")
    repositories: List[Dict[str, Any]] = Field(description="List of repository information for deployment")


class ValidateConnectionInput(BaseModel):
    """Input for validating Confluence connection."""
    pass


class ConfluenceTools:
    """Collection of Confluence tools for LangGraph workflows."""

    def __init__(self, use_mock: bool = True):
        """Initialize Confluence tools with API clients."""
        self.clients = create_api_clients(use_mock=use_mock)
        self.confluence_client = self.clients.confluence

    async def _ensure_authenticated(self):
        """Ensure Confluence client is authenticated."""
        if not hasattr(self.confluence_client, '_authenticated') or not self.confluence_client._authenticated:
            await self.confluence_client.authenticate()

    class GetSpacesTool(BaseTool):
        """Tool for getting all accessible spaces."""
        name: str = "get_spaces"
        description: str = "Get all accessible Confluence spaces"
        args_schema: type = GetSpacesInput
        confluence_tools: Any = None

        def __init__(self, confluence_tools_instance):
            super().__init__(confluence_tools=confluence_tools_instance)

        def _run(self) -> Dict[str, Any]:
            """Get spaces (synchronous)."""
            import asyncio
            return asyncio.run(self._arun())

        async def _arun(self) -> Dict[str, Any]:
            """Get all accessible spaces."""
            await self.confluence_tools._ensure_authenticated()
            spaces = await self.confluence_tools.confluence_client.get_spaces()
            return {
                "space_count": len(spaces),
                "spaces": [
                    {
                        "key": space.key,
                        "name": space.name,
                        "description": space.description,
                        "url": space.url,
                        "type": space.type
                    }
                    for space in spaces
                ]
            }

    class GetPageTool(BaseTool):
        """Tool for getting a specific page."""
        name: str = "get_page"
        description: str = "Get a specific Confluence page by ID"
        args_schema: type = GetPageInput
        confluence_tools: Any = None

        def __init__(self, confluence_tools_instance):
            super().__init__(confluence_tools=confluence_tools_instance)

        def _run(self, page_id: str) -> Dict[str, Any]:
            """Get a specific page (synchronous)."""
            import asyncio
            return asyncio.run(self._arun(page_id))

        async def _arun(self, page_id: str) -> Dict[str, Any]:
            """Get a specific page."""
            await self.confluence_tools._ensure_authenticated()
            page = await self.confluence_tools.confluence_client.get_page(page_id)
            if page:
                return {
                    "found": True,
                    "page": {
                        "id": page.id,
                        "title": page.title,
                        "space_key": page.space_key,
                        "url": page.url,
                        "content": page.content,
                        "created_at": page.created_at,
                        "updated_at": page.updated_at,
                        "author": page.author,
                        "version": page.version
                    }
                }
            else:
                return {"found": False, "error": f"Page '{page_id}' not found"}

    class CreatePageTool(BaseTool):
        """Tool for creating a new page."""
        name: str = "create_page"
        description: str = "Create a new Confluence page"
        args_schema: type = CreatePageInput
        confluence_tools: Any = None

        def __init__(self, confluence_tools_instance):
            super().__init__(confluence_tools=confluence_tools_instance)

        def _run(self, space_key: str, title: str, content: str, parent_id: Optional[str] = None) -> Dict[str, Any]:
            """Create a new page (synchronous)."""
            import asyncio
            return asyncio.run(self._arun(space_key, title, content, parent_id))

        async def _arun(self, space_key: str, title: str, content: str, parent_id: Optional[str] = None) -> Dict[str, Any]:
            """Create a new page."""
            await self.confluence_tools._ensure_authenticated()
            page = await self.confluence_tools.confluence_client.create_page(space_key, title, content, parent_id)
            return {
                "created": True,
                "page": {
                    "id": page.id,
                    "title": page.title,
                    "space_key": page.space_key,
                    "url": page.url,
                    "content": page.content,
                    "created_at": page.created_at,
                    "updated_at": page.updated_at,
                    "author": page.author,
                    "version": page.version
                }
            }

    class UpdatePageTool(BaseTool):
        """Tool for updating an existing page."""
        name: str = "update_page"
        description: str = "Update an existing Confluence page"
        args_schema: type = UpdatePageInput
        confluence_tools: Any = None

        def __init__(self, confluence_tools_instance):
            super().__init__(confluence_tools=confluence_tools_instance)

        def _run(self, page_id: str, title: str, content: str, version: int) -> Dict[str, Any]:
            """Update an existing page (synchronous)."""
            import asyncio
            return asyncio.run(self._arun(page_id, title, content, version))

        async def _arun(self, page_id: str, title: str, content: str, version: int) -> Dict[str, Any]:
            """Update an existing page."""
            await self.confluence_tools._ensure_authenticated()
            page = await self.confluence_tools.confluence_client.update_page(page_id, title, content, version)
            return {
                "updated": True,
                "page": {
                    "id": page.id,
                    "title": page.title,
                    "space_key": page.space_key,
                    "url": page.url,
                    "content": page.content,
                    "created_at": page.created_at,
                    "updated_at": page.updated_at,
                    "author": page.author,
                    "version": page.version
                }
            }

    class SearchPagesTool(BaseTool):
        """Tool for searching pages in a space."""
        name: str = "search_pages"
        description: str = "Search for pages in a Confluence space"
        args_schema: type = SearchPagesInput
        confluence_tools: Any = None

        def __init__(self, confluence_tools_instance):
            super().__init__(confluence_tools=confluence_tools_instance)

        def _run(self, space_key: str, title: Optional[str] = None) -> Dict[str, Any]:
            """Search pages (synchronous)."""
            import asyncio
            return asyncio.run(self._arun(space_key, title))

        async def _arun(self, space_key: str, title: Optional[str] = None) -> Dict[str, Any]:
            """Search for pages in a space."""
            await self.confluence_tools._ensure_authenticated()
            pages = await self.confluence_tools.confluence_client.search_pages(space_key, title)
            return {
                "space_key": space_key,
                "title_filter": title,
                "page_count": len(pages),
                "pages": [
                    {
                        "id": page.id,
                        "title": page.title,
                        "space_key": page.space_key,
                        "url": page.url,
                        "content": page.content,
                        "created_at": page.created_at,
                        "updated_at": page.updated_at,
                        "author": page.author,
                        "version": page.version
                    }
                    for page in pages
                ]
            }

    class DeletePageTool(BaseTool):
        """Tool for deleting a page."""
        name: str = "delete_page"
        description: str = "Delete a Confluence page"
        args_schema: type = DeletePageInput
        confluence_tools: Any = None

        def __init__(self, confluence_tools_instance):
            super().__init__(confluence_tools=confluence_tools_instance)

        def _run(self, page_id: str) -> Dict[str, Any]:
            """Delete a page (synchronous)."""
            import asyncio
            return asyncio.run(self._arun(page_id))

        async def _arun(self, page_id: str) -> Dict[str, Any]:
            """Delete a page."""
            await self.confluence_tools._ensure_authenticated()
            success = await self.confluence_tools.confluence_client.delete_page(page_id)
            return {
                "deleted": success,
                "page_id": page_id
            }

    class CreateDeploymentPageTool(BaseTool):
        """Tool for creating a deployment documentation page."""
        name: str = "create_deployment_page"
        description: str = "Create a standardized deployment documentation page"
        args_schema: type = CreateDeploymentPageInput
        confluence_tools: Any = None

        def __init__(self, confluence_tools_instance):
            super().__init__(confluence_tools=confluence_tools_instance)

        def _run(self, space_key: str, release_version: str, repositories: List[Dict[str, Any]]) -> Dict[str, Any]:
            """Create deployment page (synchronous)."""
            import asyncio
            return asyncio.run(self._arun(space_key, release_version, repositories))

        async def _arun(self, space_key: str, release_version: str, repositories: List[Dict[str, Any]]) -> Dict[str, Any]:
            """Create a deployment documentation page."""
            await self.confluence_tools._ensure_authenticated()
            page = await self.confluence_tools.confluence_client.create_deployment_page(space_key, release_version, repositories)
            return {
                "created": True,
                "page": {
                    "id": page.id,
                    "title": page.title,
                    "space_key": page.space_key,
                    "url": page.url,
                    "content": page.content,
                    "created_at": page.created_at,
                    "updated_at": page.updated_at,
                    "author": page.author,
                    "version": page.version
                },
                "release_version": release_version,
                "repository_count": len(repositories)
            }

    class ValidateConnectionTool(BaseTool):
        """Tool for validating Confluence connection."""
        name: str = "validate_confluence_connection"
        description: str = "Validate the Confluence API connection and get server information"
        args_schema: type = ValidateConnectionInput
        confluence_tools: Any = None

        def __init__(self, confluence_tools_instance):
            super().__init__(confluence_tools=confluence_tools_instance)

        def _run(self) -> Dict[str, Any]:
            """Validate Confluence connection (synchronous)."""
            import asyncio
            return asyncio.run(self._arun())

        async def _arun(self) -> Dict[str, Any]:
            """Validate Confluence connection."""
            await self.confluence_tools._ensure_authenticated()
            connection_info = await self.confluence_tools.confluence_client.validate_connection()
            return {
                "status": "connected",
                "connection_info": connection_info
            }

    def get_tools(self) -> List[BaseTool]:
        """Get all Confluence tools."""
        return [
            self.GetSpacesTool(self),
            self.GetPageTool(self),
            self.CreatePageTool(self),
            self.UpdatePageTool(self),
            self.SearchPagesTool(self),
            self.DeletePageTool(self),
            self.CreateDeploymentPageTool(self),
            self.ValidateConnectionTool(self),
        ] 