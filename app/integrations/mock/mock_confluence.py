"""
Mock Confluence API Implementation

Provides realistic mock responses for Confluence API operations.
"""

import asyncio
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from ..base.confluence_interface import (
    ConfluenceInterface,
    ConfluencePage,
    ConfluenceSpace,
)


class MockConfluenceClient(ConfluenceInterface):
    """Mock implementation of Confluence API client."""

    def __init__(self, base_url: str = "", username: str = "", token: str = ""):
        self.base_url = base_url
        self.username = username
        self.token = token
        self._authenticated = False

        # Mock data
        self._mock_spaces = self._generate_mock_spaces()
        self._mock_pages = self._generate_mock_pages()
        self._page_counter = 100  # For generating new page IDs

    def _generate_mock_spaces(self) -> List[ConfluenceSpace]:
        """Generate mock space data."""
        return [
            ConfluenceSpace(
                key="DEV",
                name="Development Documentation",
                description="Documentation for development processes and releases",
                url="https://mock-confluence.company.com/spaces/DEV",
                type="global",
            ),
            ConfluenceSpace(
                key="PROJ",
                name="Project Enigma",
                description="Project Enigma specific documentation",
                url="https://mock-confluence.company.com/spaces/PROJ",
                type="global",
            ),
            ConfluenceSpace(
                key="OPS",
                name="Operations",
                description="Operations and deployment documentation",
                url="https://mock-confluence.company.com/spaces/OPS",
                type="global",
            ),
        ]

    def _generate_mock_pages(self) -> List[ConfluencePage]:
        """Generate mock page data."""
        base_date = datetime.now() - timedelta(days=7)

        return [
            ConfluencePage(
                id="1001",
                title="Release Process Documentation",
                space_key="DEV",
                url="https://mock-confluence.company.com/pages/1001",
                content="<h1>Release Process</h1><p>This page documents our release process...</p>",
                created_at=(base_date + timedelta(days=1)).isoformat(),
                updated_at=(base_date + timedelta(days=2)).isoformat(),
                author="dev-lead@company.com",
                version=3,
            ),
            ConfluencePage(
                id="1002",
                title="Deployment Guidelines",
                space_key="OPS",
                url="https://mock-confluence.company.com/pages/1002",
                content="<h1>Deployment Guidelines</h1><p>Guidelines for safe deployments...</p>",
                created_at=(base_date + timedelta(days=2)).isoformat(),
                updated_at=(base_date + timedelta(days=3)).isoformat(),
                author="ops-lead@company.com",
                version=2,
            ),
            ConfluencePage(
                id="1003",
                title="Project Enigma Overview",
                space_key="PROJ",
                url="https://mock-confluence.company.com/pages/1003",
                content="<h1>Project Enigma</h1><p>Overview of the Project Enigma release automation tool...</p>",
                created_at=(base_date + timedelta(days=3)).isoformat(),
                updated_at=(base_date + timedelta(days=4)).isoformat(),
                author="project-manager@company.com",
                version=1,
            ),
        ]

    def _generate_deployment_content(
        self, release_version: str, repositories: List[Dict[str, Any]]
    ) -> str:
        """Generate standardized deployment documentation content."""
        content = f"""
<h1>Deployment Documentation - {release_version}</h1>

<h2>Release Information</h2>
<ul>
<li><strong>Release Version:</strong> {release_version}</li>
<li><strong>Date:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</li>
<li><strong>Repositories:</strong> {len(repositories)}</li>
</ul>

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
<td>{branch}</td>
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
<td>{rollback_branch}</td>
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
        """Mock authentication - always succeeds."""
        await asyncio.sleep(0.1)  # Simulate network delay
        self._authenticated = True
        return True

    async def get_spaces(self) -> List[ConfluenceSpace]:
        """Get mock spaces."""
        await asyncio.sleep(0.1)  # Simulate API delay
        return self._mock_spaces

    async def get_page(self, page_id: str) -> Optional[ConfluencePage]:
        """Get a specific mock page."""
        await asyncio.sleep(0.1)  # Simulate API delay

        for page in self._mock_pages:
            if page.id == page_id:
                return page
        return None

    async def create_page(
        self, space_key: str, title: str, content: str, parent_id: Optional[str] = None
    ) -> ConfluencePage:
        """Create a mock page."""
        await asyncio.sleep(0.3)  # Simulate API delay

        self._page_counter += 1
        page_id = str(self._page_counter)

        page = ConfluencePage(
            id=page_id,
            title=title,
            space_key=space_key,
            url=f"https://mock-confluence.company.com/pages/{page_id}",
            content=content,
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat(),
            author=self.username or "mock-user@company.com",
            version=1,
        )

        # Add to mock data
        self._mock_pages.append(page)

        return page

    async def update_page(
        self, page_id: str, title: str, content: str, version: int
    ) -> ConfluencePage:
        """Update a mock page."""
        await asyncio.sleep(0.3)  # Simulate API delay

        # Find existing page
        for i, page in enumerate(self._mock_pages):
            if page.id == page_id:
                # Create updated page
                updated_page = ConfluencePage(
                    id=page_id,
                    title=title,
                    space_key=page.space_key,
                    url=page.url,
                    content=content,
                    created_at=page.created_at,
                    updated_at=datetime.now().isoformat(),
                    author=self.username or "mock-user@company.com",
                    version=version + 1,
                )

                # Replace in mock data
                self._mock_pages[i] = updated_page
                return updated_page

        # If page not found, raise an error
        raise ValueError(f"Page with ID {page_id} not found")

    async def search_pages(
        self, space_key: str, title: Optional[str] = None
    ) -> List[ConfluencePage]:
        """Search mock pages."""
        await asyncio.sleep(0.2)  # Simulate API delay

        results = [page for page in self._mock_pages if page.space_key == space_key]

        if title:
            results = [page for page in results if title.lower() in page.title.lower()]

        return results

    async def delete_page(self, page_id: str) -> bool:
        """Delete a mock page."""
        await asyncio.sleep(0.2)  # Simulate API delay

        for i, page in enumerate(self._mock_pages):
            if page.id == page_id:
                del self._mock_pages[i]
                return True

        return False

    async def create_deployment_page(
        self, space_key: str, release_version: str, repositories: List[Dict[str, Any]]
    ) -> ConfluencePage:
        """Create a standardized deployment documentation page."""
        await asyncio.sleep(0.4)  # Simulate API delay

        title = f"Deployment Documentation - {release_version}"
        content = self._generate_deployment_content(release_version, repositories)

        return await self.create_page(space_key, title, content)

    async def validate_connection(self) -> Dict[str, Any]:
        """Validate mock connection."""
        await asyncio.sleep(0.1)  # Simulate API delay

        return {
            "status": "connected",
            "server_title": "Mock Confluence Server",
            "version": "7.19.0",
            "base_url": self.base_url or "https://mock-confluence.company.com",
            "user": self.username or "mock-user@company.com",
            "spaces_count": len(self._mock_spaces),
        }
