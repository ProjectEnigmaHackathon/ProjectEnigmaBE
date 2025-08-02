"""
Mock GitHub API Implementation

Provides realistic mock responses for GitHub API operations.
"""

import asyncio
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from ..base.github_interface import (
    GitHubBranch,
    GitHubInterface,
    GitHubPullRequest,
    GitHubRepository,
    GitHubTag,
)
from ..exceptions import GitHubMergeConflictError


class MockGitHubClient(GitHubInterface):
    """Mock implementation of GitHub API client."""

    def __init__(self, token: str = "", organization: str = ""):
        self.token = token
        self.organization = organization or "mock-org"
        self._authenticated = False

        # Mock data
        self._mock_repositories = self._generate_mock_repositories()
        self._mock_branches = self._generate_mock_branches()
        self._mock_tags = self._generate_mock_tags()
        self._mock_prs = self._generate_mock_prs()

    def _generate_mock_repositories(self) -> List[GitHubRepository]:
        """Generate mock repository data."""
        repos = []
        repo_names = ["api-service", "frontend-app", "core-platform", "data-processor"]

        for name in repo_names:
            repo = GitHubRepository(
                name=name,
                full_name=f"{self.organization}/{name}",
                default_branch="main",
                url=f"https://github.com/{self.organization}/{name}",
                clone_url=f"https://github.com/{self.organization}/{name}.git",
                private=True,
            )
            repos.append(repo)

        return repos

    def _generate_mock_branches(self) -> Dict[str, List[GitHubBranch]]:
        """Generate mock branch data for each repository."""
        branches_by_repo = {}

        for repo in self._mock_repositories:
            branches = [
                GitHubBranch(
                    name="main",
                    sha="a1b2c3d4e5f6789012345678901234567890abcd",
                    protected=True,
                    url=f"https://github.com/{repo.full_name}/tree/main",
                ),
                GitHubBranch(
                    name="develop",
                    sha="b2c3d4e5f6789012345678901234567890abcdef",
                    protected=True,
                    url=f"https://github.com/{repo.full_name}/tree/develop",
                ),
                GitHubBranch(
                    name="sprint-2024-01",
                    sha="c3d4e5f6789012345678901234567890abcdef12",
                    protected=False,
                    url=f"https://github.com/{repo.full_name}/tree/sprint-2024-01",
                ),
            ]

            # Add feature branches based on JIRA tickets
            feature_tickets = ["PROJ-001", "PROJ-002", "API-003", "UI-004", "CORE-005"]
            for i, ticket in enumerate(feature_tickets):
                if (
                    repo.name in ["api-service", "core-platform"]
                    and "API" in ticket
                    or "CORE" in ticket
                ):
                    branch = GitHubBranch(
                        name=f"feature/{ticket}",
                        sha=f"d{i}e5f6789012345678901234567890abcdef1234",
                        protected=False,
                        url=f"https://github.com/{repo.full_name}/tree/feature/{ticket}",
                    )
                    branches.append(branch)
                elif repo.name == "frontend-app" and "UI" in ticket:
                    branch = GitHubBranch(
                        name=f"feature/{ticket}",
                        sha=f"e{i}f6789012345678901234567890abcdef12345",
                        protected=False,
                        url=f"https://github.com/{repo.full_name}/tree/feature/{ticket}",
                    )
                    branches.append(branch)
                elif "PROJ" in ticket:
                    branch = GitHubBranch(
                        name=f"feature/{ticket}",
                        sha=f"f{i}789012345678901234567890abcdef123456",
                        protected=False,
                        url=f"https://github.com/{repo.full_name}/tree/feature/{ticket}",
                    )
                    branches.append(branch)

            branches_by_repo[repo.full_name] = branches

        return branches_by_repo

    def _generate_mock_tags(self) -> Dict[str, List[GitHubTag]]:
        """Generate mock tag data for each repository."""
        tags_by_repo = {}

        for repo in self._mock_repositories:
            tags = [
                GitHubTag(
                    name="v1.0.0",
                    sha="1234567890abcdef1234567890abcdef12345678",
                    url=f"https://github.com/{repo.full_name}/releases/tag/v1.0.0",
                    tagger="release-bot@company.com",
                    date=(datetime.now() - timedelta(days=60)).isoformat(),
                    message="Release v1.0.0",
                ),
                GitHubTag(
                    name="v1.1.0",
                    sha="2345678901abcdef2345678901abcdef23456789",
                    url=f"https://github.com/{repo.full_name}/releases/tag/v1.1.0",
                    tagger="release-bot@company.com",
                    date=(datetime.now() - timedelta(days=30)).isoformat(),
                    message="Release v1.1.0",
                ),
            ]
            tags_by_repo[repo.full_name] = tags

        return tags_by_repo

    def _generate_mock_prs(self) -> Dict[str, List[GitHubPullRequest]]:
        """Generate mock pull request data."""
        prs_by_repo = {}

        for repo in self._mock_repositories:
            prs = [
                GitHubPullRequest(
                    number=1,
                    title="Release v2.0.0 to main",
                    body="Automated release PR for version 2.0.0",
                    state="open",
                    head_branch="release/v2.0.0",
                    base_branch="main",
                    url=f"https://github.com/{repo.full_name}/pull/1",
                    created_at=(datetime.now() - timedelta(hours=2)).isoformat(),
                    updated_at=datetime.now().isoformat(),
                    merged_at=None,
                    author="release-bot",
                )
            ]
            prs_by_repo[repo.full_name] = prs

        return prs_by_repo

    async def authenticate(self) -> bool:
        """Mock authentication - always succeeds."""
        await asyncio.sleep(0.1)  # Simulate network delay
        self._authenticated = True
        return True

    async def get_repository(self, repo_name: str) -> Optional[GitHubRepository]:
        """Get mock repository information."""
        await asyncio.sleep(0.1)  # Simulate API delay

        for repo in self._mock_repositories:
            if repo.full_name == repo_name or repo.name == repo_name:
                return repo
        return None

    async def get_branches(self, repo_name: str) -> List[GitHubBranch]:
        """Get mock branches for a repository."""
        await asyncio.sleep(0.1)  # Simulate API delay

        return self._mock_branches.get(repo_name, [])

    async def find_feature_branches(
        self, repo_name: str, ticket_ids: List[str]
    ) -> Dict[str, Optional[GitHubBranch]]:
        """Find mock feature branches for JIRA ticket IDs."""
        await asyncio.sleep(0.2)  # Simulate API delay

        branches = self._mock_branches.get(repo_name, [])
        result = {}

        for ticket_id in ticket_ids:
            found_branch = None
            for branch in branches:
                if branch.name == f"feature/{ticket_id}":
                    found_branch = branch
                    break
            result[ticket_id] = found_branch

        return result

    async def check_merge_status(
        self, repo_name: str, source_branch: str, target_branch: str
    ) -> Dict[str, Any]:
        """Check mock merge status between branches."""
        await asyncio.sleep(0.1)  # Simulate API delay

        # Mock logic: feature branches are merged into sprint branches,
        # sprint branches are not yet merged into develop
        if source_branch.startswith("feature/") and target_branch.startswith("sprint-"):
            return {
                "merged": True,
                "merge_commit_sha": "abcdef1234567890abcdef1234567890abcdef12",
                "ahead_by": 0,
                "behind_by": 0,
            }
        elif source_branch.startswith("sprint-") and target_branch == "develop":
            return {
                "merged": False,
                "merge_commit_sha": None,
                "ahead_by": 5,
                "behind_by": 2,
            }
        else:
            return {
                "merged": False,
                "merge_commit_sha": None,
                "ahead_by": 0,
                "behind_by": 0,
            }

    async def create_pull_request(
        self, repo_name: str, title: str, body: str, head_branch: str, base_branch: str
    ) -> GitHubPullRequest:
        """Create a mock pull request."""
        await asyncio.sleep(0.3)  # Simulate API delay

        # Generate new PR number
        existing_prs = self._mock_prs.get(repo_name, [])
        pr_number = len(existing_prs) + 1

        pr = GitHubPullRequest(
            number=pr_number,
            title=title,
            body=body,
            state="open",
            head_branch=head_branch,
            base_branch=base_branch,
            url=f"https://github.com/{repo_name}/pull/{pr_number}",
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat(),
            merged_at=None,
            author="mock-user",
        )

        # Add to mock data
        if repo_name not in self._mock_prs:
            self._mock_prs[repo_name] = []
        self._mock_prs[repo_name].append(pr)

        return pr

    async def merge_pull_request(
        self, repo: str, pr_number: int, merge_method: str = "merge"
    ) -> Dict[str, Any]:
        """Mock merge pull request operation."""
        await asyncio.sleep(0.5)  # Simulate API delay

        # Simulate some merge conflicts for certain PR numbers
        if pr_number % 5 == 0:  # 20% chance of conflict
            raise GitHubMergeConflictError(
                "feature/branch", "main", repo, "Mock merge conflict"
            )

        # Update the PR state in mock data
        if repo in self._mock_prs:
            for pr in self._mock_prs[repo]:
                if pr.number == pr_number:
                    pr.state = "closed"
                    pr.merged_at = datetime.now().isoformat()
                    break

        return {
            "merged": True,
            "sha": f"merged{pr_number}sha1234567890abcdef1234567890abcdef12345678",
            "message": f"Merge pull request #{pr_number} from feature/branch into main",
            "merge_method": merge_method,
        }

    async def merge_branches(
        self, repo_name: str, source_branch: str, target_branch: str
    ) -> Dict[str, Any]:
        """Mock merge branches operation."""
        await asyncio.sleep(0.4)  # Simulate API delay

        return {
            "merged": True,
            "sha": "fedcba0987654321fedcba0987654321fedcba09",
            "message": f"Merged {source_branch} into {target_branch}",
        }

    async def create_branch(
        self, repo_name: str, branch_name: str, source_branch: str = "main"
    ) -> GitHubBranch:
        """Create a mock branch."""
        await asyncio.sleep(0.2)  # Simulate API delay

        branch = GitHubBranch(
            name=branch_name,
            sha="1111222233334444555566667777888899990000",
            protected=False,
            url=f"https://github.com/{repo_name}/tree/{branch_name}",
        )

        # Add to mock data
        if repo_name not in self._mock_branches:
            self._mock_branches[repo_name] = []
        self._mock_branches[repo_name].append(branch)

        return branch

    async def create_tag(
        self, repo_name: str, tag_name: str, sha: str, message: str
    ) -> GitHubTag:
        """Create a mock tag."""
        await asyncio.sleep(0.2)  # Simulate API delay

        tag = GitHubTag(
            name=tag_name,
            sha=sha,
            url=f"https://github.com/{repo_name}/releases/tag/{tag_name}",
            tagger="mock-user@company.com",
            date=datetime.now().isoformat(),
            message=message,
        )

        # Add to mock data
        if repo_name not in self._mock_tags:
            self._mock_tags[repo_name] = []
        self._mock_tags[repo_name].append(tag)

        return tag

    async def get_tags(self, repo_name: str) -> List[GitHubTag]:
        """Get mock tags for a repository."""
        await asyncio.sleep(0.1)  # Simulate API delay

        return self._mock_tags.get(repo_name, [])

    async def validate_connection(self) -> Dict[str, Any]:
        """Validate mock connection."""
        await asyncio.sleep(0.1)  # Simulate API delay

        return {
            "status": "connected",
            "user": "mock-user",
            "login": "mock-user",
            "name": "Mock User",
            "email": "mock-user@company.com",
            "organizations": [self.organization],
        }
