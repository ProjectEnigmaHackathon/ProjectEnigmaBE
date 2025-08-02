"""
Real Confluence API Implementation

Provides real Confluence API integration using the atlassian-python-api library.
"""

import asyncio
import logging
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional

# Fix beautifulsoup4 import issue for atlassian package
if "beautifulsoup4" not in sys.modules:
    import bs4

    sys.modules["beautifulsoup4"] = bs4

from atlassian.confluence import Confluence
from requests.exceptions import ConnectionError, HTTPError, Timeout

from ..base.confluence_interface import (
    ConfluenceInterface,
    ConfluencePage,
    ConfluenceSpace,
)
from ..exceptions import (
    APIConnectionError,
    ConfluenceAuthenticationError,
    ConfluenceError,
    ConfluencePageNotFoundError,
    ConfluencePageVersionError,
    ConfluenceRateLimitError,
    ConfluenceSpaceNotFoundError,
)
from ..rate_limiter import get_rate_limiter
from ...core.config import get_settings

logger = logging.getLogger(__name__)


class RealConfluenceClient(ConfluenceInterface):
    """Real implementation of Confluence API client using atlassian-python-api."""

    def __init__(self, base_url: str, username: str, token: str):
        self.base_url = base_url
        self.username = username
        self.token = token
        self._client: Optional[Confluence] = None
        self._authenticated = False
        self.rate_limiter = get_rate_limiter()

    def _get_client(self) -> Confluence:
        """Get or create Confluence client instance."""
        if self._client is None:
            try:
                # Determine if this is a cloud instance
                is_cloud = "atlassian.net" in self.base_url

                self._client = Confluence(
                    url=self.base_url,
                    username=self.username,
                    password=self.token,
                    cloud=is_cloud,
                    timeout=30,
                )
            except Exception as e:
                logger.error(f"Failed to create Confluence client: {str(e)}")
                raise APIConnectionError("Confluence", self.base_url, str(e))

        return self._client

    def _convert_confluence_page(self, page_data: Dict[str, Any]) -> ConfluencePage:
        """Convert Confluence page data to ConfluencePage model."""
        try:
            # Extract content if available
            content = None
            if "body" in page_data and "storage" in page_data["body"]:
                content = page_data["body"]["storage"]["value"]

            # Extract author information
            author = "unknown"
            if "history" in page_data and "createdBy" in page_data["history"]:
                author = page_data["history"]["createdBy"].get("displayName", "unknown")
            elif "version" in page_data and "by" in page_data["version"]:
                author = page_data["version"]["by"].get("displayName", "unknown")

            return ConfluencePage(
                id=page_data["id"],
                title=page_data["title"],
                space_key=page_data["space"]["key"],
                url=f"{self.base_url.rstrip('/')}/spaces/{page_data['space']['key']}/pages/{page_data['id']}",
                content=content,
                created_at=page_data.get("history", {}).get(
                    "createdDate", datetime.now().isoformat()
                ),
                updated_at=(
                    page_data["version"]["when"]
                    if "version" in page_data
                    else datetime.now().isoformat()
                ),
                author=author,
                version=page_data["version"]["number"] if "version" in page_data else 1,
            )
        except Exception as e:
            logger.error(f"Failed to convert Confluence page: {str(e)}")
            raise ConfluenceError(f"Failed to parse Confluence page: {str(e)}")

    def _convert_confluence_space(self, space_data: Dict[str, Any]) -> ConfluenceSpace:
        """Convert Confluence space data to ConfluenceSpace model."""
        try:
            return ConfluenceSpace(
                key=space_data["key"],
                name=space_data["name"],
                description=space_data.get("description", {})
                .get("plain", {})
                .get("value", ""),
                url=f"{self.base_url.rstrip('/')}/spaces/{space_data['key']}",
                type=space_data.get("type", "global"),
            )
        except Exception as e:
            logger.error(f"Failed to convert Confluence space: {str(e)}")
            raise ConfluenceError(f"Failed to parse Confluence space: {str(e)}")

    def _generate_deployment_content(
        self, release_version: str, repositories: List[Dict[str, Any]]
    ) -> str:
        """Generate standardized deployment documentation content."""
        content = f"""
<h1>Deployment Documentation - {release_version}</h1>

<h2>Release Information</h2>
<table>
<tbody>
<tr><th>Release Version</th><td>{release_version}</td></tr>
<tr><th>Date</th><td>{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</td></tr>
<tr><th>Repositories</th><td>{len(repositories)}</td></tr>
</tbody>
</table>

<h2>Deployment Plan</h2>
<table>
<thead>
<tr>
<th>Repository</th>
<th>Jenkins Job</th>
<th>Pull Request</th>
<th>Release Branch</th>
</tr>
</thead>
<tbody>
"""

        for repo in repositories:
            repo_name = repo.get("name", "Unknown")
            jenkins_url = repo.get(
                "jenkins_url", f"https://jenkins.company.com/job/deploy-{repo_name}"
            )
            pr_url = repo.get(
                "pr_url", f"https://github.com/mock-org/{repo_name}/pull/1"
            )
            branch = repo.get("release_branch", f"release/{release_version}")

            content += f"""
<tr>
<td>{repo_name}</td>
<td><a href="{jenkins_url}">Deploy Job</a></td>
<td><a href="{pr_url}">PR Link</a></td>
<td><code>{branch}</code></td>
</tr>"""

        content += """
</tbody>
</table>

<h2>Rollback Plan</h2>
<table>
<thead>
<tr>
<th>Repository</th>
<th>Rollback Branch</th>
<th>Rollback Job</th>
</tr>
</thead>
<tbody>
"""

        for repo in repositories:
            repo_name = repo.get("name", "Unknown")
            rollback_branch = repo.get(
                "rollback_branch", f"rollback/v-{release_version}"
            )
            rollback_url = repo.get(
                "rollback_url", f"https://jenkins.company.com/job/rollback-{repo_name}"
            )

            content += f"""
<tr>
<td>{repo_name}</td>
<td><code>{rollback_branch}</code></td>
<td><a href="{rollback_url}">Rollback Job</a></td>
</tr>"""

        content += """
</tbody>
</table>

<h2>Deployment Steps</h2>
<ol>
<li>Verify all pull requests are approved and ready</li>
<li>Execute deployment jobs in the order listed above</li>
<li>Monitor application health after each deployment</li>
<li>Verify release functionality in production</li>
</ol>

<h2>Rollback Steps</h2>
<ol>
<li>Identify the issue and confirm rollback decision</li>
<li>Execute rollback jobs for affected services</li>
<li>Verify system stability after rollback</li>
<li>Document the rollback reason and lessons learned</li>
</ol>

<p><em>This page was automatically generated by Project Enigma on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</em></p>
"""

        return content

    async def authenticate(self) -> bool:
        """Authenticate with Confluence API."""
        try:
            await self.rate_limiter.acquire("confluence", "auth")

            client = self._get_client()

            # Test authentication by getting current user
            settings = get_settings()
            user_info = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: client.get_user_details_by_accountid(
                    settings.atlassian_account_id
                ),
            )

            self._authenticated = True
            logger.info(
                f"Successfully authenticated with Confluence as {user_info.get('displayName', self.username)}"
            )
            return True

        except HTTPError as e:
            logger.error(f"Confluence authentication failed: {str(e)}")
            if e.response.status_code == 401:
                raise ConfluenceAuthenticationError("Invalid username or token")
            elif e.response.status_code == 403:
                raise ConfluenceAuthenticationError(
                    "Access forbidden - check permissions"
                )
            else:
                raise ConfluenceAuthenticationError(f"Authentication failed: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error during Confluence authentication: {str(e)}")
            raise APIConnectionError("Confluence", self.base_url, str(e))

    async def get_spaces(self) -> List[ConfluenceSpace]:
        """Get all accessible spaces."""
        try:
            await self.rate_limiter.acquire("confluence", "get_spaces")

            client = self._get_client()

            # Get spaces
            spaces_data = await asyncio.get_event_loop().run_in_executor(
                None, lambda: client.get_all_spaces(expand="description")
            )

            # Convert to ConfluenceSpace objects
            spaces = []
            for space_data in spaces_data["results"]:
                try:
                    space = self._convert_confluence_space(space_data)
                    spaces.append(space)
                except Exception as e:
                    logger.warning(
                        f"Failed to convert space {space_data.get('key', 'unknown')}: {str(e)}"
                    )
                    continue

            logger.info(f"Retrieved {len(spaces)} Confluence spaces")
            return spaces

        except HTTPError as e:
            logger.error(f"Confluence get spaces failed: {str(e)}")
            if e.response.status_code == 429:
                raise ConfluenceRateLimitError()
            elif e.response.status_code == 401:
                raise ConfluenceAuthenticationError("Authentication expired")
            else:
                raise ConfluenceError(f"Failed to get spaces: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error getting Confluence spaces: {str(e)}")
            raise ConfluenceError(f"Failed to get spaces: {str(e)}")

    async def get_page(self, page_id: str) -> Optional[ConfluencePage]:
        """Get a specific page by ID."""
        try:
            await self.rate_limiter.acquire("confluence", "get_page")

            client = self._get_client()

            # Get page
            page_data = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: client.get_page_by_id(
                    page_id, expand="body.storage,version,space,history.createdBy"
                ),
            )

            return self._convert_confluence_page(page_data)

        except HTTPError as e:
            if e.response.status_code == 404:
                logger.warning(f"Confluence page not found: {page_id}")
                return None
            elif e.response.status_code == 429:
                raise ConfluenceRateLimitError()
            elif e.response.status_code == 401:
                raise ConfluenceAuthenticationError("Authentication expired")
            else:
                logger.error(f"Confluence get page failed: {str(e)}")
                raise ConfluenceError(f"Failed to get page {page_id}: {str(e)}")
        except Exception as e:
            logger.error(
                f"Unexpected error getting Confluence page {page_id}: {str(e)}"
            )
            raise ConfluenceError(f"Failed to get page: {str(e)}")

    async def create_page(
        self, space_key: str, title: str, content: str, parent_id: Optional[str] = None
    ) -> ConfluencePage:
        """Create a new page."""
        try:
            await self.rate_limiter.acquire("confluence", "create_page")

            client = self._get_client()

            # Create page
            page_data = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: client.create_page(
                    space=space_key,
                    title=title,
                    body=content,
                    parent_id=parent_id,
                    type="page",
                    representation="storage",
                ),
            )

            logger.info(f"Created Confluence page: {title} in space {space_key}")

            # Get the full page data with all required fields
            full_page_data = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: client.get_page_by_id(
                    page_data["id"],
                    expand="body.storage,version,space,history.createdBy",
                ),
            )

            return self._convert_confluence_page(full_page_data)

        except HTTPError as e:
            logger.error(f"Confluence create page failed: {str(e)}")
            if e.response.status_code == 404:
                raise ConfluenceSpaceNotFoundError(space_key)
            elif e.response.status_code == 429:
                raise ConfluenceRateLimitError()
            elif e.response.status_code == 401:
                raise ConfluenceAuthenticationError("Authentication expired")
            else:
                raise ConfluenceError(f"Failed to create page: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error creating Confluence page: {str(e)}")
            raise ConfluenceError(f"Failed to create page: {str(e)}")

    async def update_page(
        self, page_id: str, title: str, content: str, version: int
    ) -> ConfluencePage:
        """Update an existing page."""
        try:
            await self.rate_limiter.acquire("confluence", "update_page")

            client = self._get_client()

            # Update page
            page_data = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: client.update_page(
                    page_id=page_id,
                    title=title,
                    body=content,
                    representation="storage",
                ),
            )

            logger.info(f"Updated Confluence page: {title} (version {version + 1})")

            # Get the full page data with all required fields
            full_page_data = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: client.get_page_by_id(
                    page_id, expand="body.storage,version,space,history.createdBy"
                ),
            )

            return self._convert_confluence_page(full_page_data)

        except HTTPError as e:
            logger.error(f"Confluence update page failed: {str(e)}")
            if e.response.status_code == 404:
                raise ConfluencePageNotFoundError(page_id)
            elif e.response.status_code == 409:
                # Version conflict
                raise ConfluencePageVersionError(page_id, version + 1, version)
            elif e.response.status_code == 429:
                raise ConfluenceRateLimitError()
            elif e.response.status_code == 401:
                raise ConfluenceAuthenticationError("Authentication expired")
            else:
                raise ConfluenceError(f"Failed to update page: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error updating Confluence page: {str(e)}")
            raise ConfluenceError(f"Failed to update page: {str(e)}")

    async def search_pages(
        self, space_key: str, title: Optional[str] = None
    ) -> List[ConfluencePage]:
        """Search for pages in a space."""
        try:
            await self.rate_limiter.acquire("confluence", "search_pages")

            client = self._get_client()

            # Build CQL query
            cql = f'space = "{space_key}" AND type = "page"'
            if title:
                cql += f' AND title ~ "{title}"'

            # Search pages
            search_results = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: client.cql(
                    cql, expand="body.storage,version,space,history.createdBy"
                ),
            )

            # Convert to ConfluencePage objects
            pages = []
            for page_data in search_results["results"]:
                try:
                    page = self._convert_confluence_page(page_data)
                    pages.append(page)
                except Exception as e:
                    logger.warning(
                        f"Failed to convert page {page_data.get('id', 'unknown')}: {str(e)}"
                    )
                    continue

            logger.info(f"Found {len(pages)} pages in space {space_key}")
            return pages

        except HTTPError as e:
            logger.error(f"Confluence search pages failed: {str(e)}")
            if e.response.status_code == 404:
                raise ConfluenceSpaceNotFoundError(space_key)
            elif e.response.status_code == 429:
                raise ConfluenceRateLimitError()
            elif e.response.status_code == 401:
                raise ConfluenceAuthenticationError("Authentication expired")
            else:
                raise ConfluenceError(f"Failed to search pages: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error searching Confluence pages: {str(e)}")
            raise ConfluenceError(f"Failed to search pages: {str(e)}")

    async def delete_page(self, page_id: str) -> bool:
        """Delete a page."""
        try:
            await self.rate_limiter.acquire("confluence", "delete_page")

            client = self._get_client()

            # Delete page
            await asyncio.get_event_loop().run_in_executor(
                None, lambda: client.remove_page(page_id)
            )

            logger.info(f"Deleted Confluence page: {page_id}")
            return True

        except HTTPError as e:
            if e.response.status_code == 404:
                logger.warning(f"Confluence page not found for deletion: {page_id}")
                return False
            elif e.response.status_code == 429:
                raise ConfluenceRateLimitError()
            elif e.response.status_code == 401:
                raise ConfluenceAuthenticationError("Authentication expired")
            else:
                logger.error(f"Confluence delete page failed: {str(e)}")
                raise ConfluenceError(f"Failed to delete page: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error deleting Confluence page: {str(e)}")
            raise ConfluenceError(f"Failed to delete page: {str(e)}")

    async def create_deployment_page(
        self, space_key: str, release_version: str, repositories: List[Dict[str, Any]]
    ) -> ConfluencePage:
        """Create a standardized deployment documentation page."""
        title = f"Deployment Documentation - {release_version}"
        content = self._generate_deployment_content(release_version, repositories)

        return await self.create_page(space_key, title, content)

    async def validate_connection(self) -> Dict[str, Any]:
        """Validate the connection and return server information."""
        try:
            await self.rate_limiter.acquire("confluence", "validate")

            client = self._get_client()

            # Get user info and server info
            settings = get_settings()
            user_info = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: client.get_user_details_by_accountid(
                    settings.atlassian_account_id
                ),
            )

            # Try to get server info (may not be available on all instances)
            try:
                server_info = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: client.get_server_info()
                )
            except:
                server_info = {"title": "Confluence Server", "version": "Unknown"}

            return {
                "status": "connected",
                "server_title": server_info.get("title", "Confluence Server"),
                "version": server_info.get("version", "Unknown"),
                "base_url": self.base_url,
                "user": self.username,
                "display_name": user_info.get("displayName", self.username),
                "account_id": user_info.get("accountId", ""),
                "is_cloud": "atlassian.net" in self.base_url,
            }

        except HTTPError as e:
            logger.error(f"Confluence connection validation failed: {str(e)}")
            if e.response.status_code == 401:
                raise ConfluenceAuthenticationError("Invalid credentials")
            else:
                raise ConfluenceError(f"Connection validation failed: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error validating Confluence connection: {str(e)}")
            raise APIConnectionError("Confluence", self.base_url, str(e))
