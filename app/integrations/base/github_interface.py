"""
GitHub API Interface

Abstract base class defining the contract for GitHub API operations.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class GitHubBranch(BaseModel):
    """GitHub branch model."""

    name: str
    sha: str
    protected: bool
    url: str


class GitHubPullRequest(BaseModel):
    """GitHub pull request model."""

    number: int
    title: str
    body: Optional[str] = None
    state: str
    head_branch: str
    base_branch: str
    url: str
    created_at: str
    updated_at: str
    merged_at: Optional[str] = None
    author: str


class GitHubTag(BaseModel):
    """GitHub tag model."""

    name: str
    sha: str
    url: str
    tagger: Optional[str] = None
    date: Optional[str] = None
    message: Optional[str] = None


class GitHubRepository(BaseModel):
    """GitHub repository model."""

    name: str
    full_name: str
    default_branch: str
    url: str
    clone_url: str
    private: bool


class GitHubInterface(ABC):
    """Abstract interface for GitHub API operations."""

    @abstractmethod
    async def authenticate(self) -> bool:
        """
        Authenticate with GitHub API.

        Returns:
            bool: True if authentication successful, False otherwise
        """
        pass

    @abstractmethod
    async def get_repository(self, repo_name: str) -> Optional[GitHubRepository]:
        """
        Get repository information.

        Args:
            repo_name: Repository name in format "owner/repo"

        Returns:
            Optional[GitHubRepository]: Repository info if found, None otherwise
        """
        pass

    @abstractmethod
    async def get_branches(self, repo_name: str) -> List[GitHubBranch]:
        """
        Get all branches for a repository.

        Args:
            repo_name: Repository name in format "owner/repo"

        Returns:
            List[GitHubBranch]: List of branches
        """
        pass

    @abstractmethod
    async def find_feature_branches(
        self, repo_name: str, ticket_ids: List[str]
    ) -> Dict[str, Optional[GitHubBranch]]:
        """
        Find feature branches for JIRA ticket IDs.

        Args:
            repo_name: Repository name in format "owner/repo"
            ticket_ids: List of JIRA ticket IDs

        Returns:
            Dict[str, Optional[GitHubBranch]]: Map of ticket ID to branch (None if not found)
        """
        pass

    @abstractmethod
    async def check_merge_status(
        self, repo_name: str, source_branch: str, target_branch: str
    ) -> Dict[str, Any]:
        """
        Check if source branch is merged into target branch.

        Args:
            repo_name: Repository name in format "owner/repo"
            source_branch: Source branch name
            target_branch: Target branch name

        Returns:
            Dict[str, Any]: Merge status information
        """
        pass

    @abstractmethod
    async def create_pull_request(
        self, repo_name: str, title: str, body: str, head_branch: str, base_branch: str
    ) -> GitHubPullRequest:
        """
        Create a pull request.

        Args:
            repo_name: Repository name in format "owner/repo"
            title: PR title
            body: PR description
            head_branch: Source branch
            base_branch: Target branch

        Returns:
            GitHubPullRequest: Created pull request
        """
        pass

    @abstractmethod
    async def merge_branches(
        self, repo_name: str, source_branch: str, target_branch: str
    ) -> Dict[str, Any]:
        """
        Merge source branch into target branch.

        Args:
            repo_name: Repository name in format "owner/repo"
            source_branch: Source branch name
            target_branch: Target branch name

        Returns:
            Dict[str, Any]: Merge result information
        """
        pass

    @abstractmethod
    async def create_branch(
        self, repo_name: str, branch_name: str, source_branch: str = "main"
    ) -> GitHubBranch:
        """
        Create a new branch.

        Args:
            repo_name: Repository name in format "owner/repo"
            branch_name: New branch name
            source_branch: Branch to create from

        Returns:
            GitHubBranch: Created branch
        """
        pass

    @abstractmethod
    async def create_tag(
        self, repo_name: str, tag_name: str, sha: str, message: str
    ) -> GitHubTag:
        """
        Create a tag.

        Args:
            repo_name: Repository name in format "owner/repo"
            tag_name: Tag name
            sha: Commit SHA to tag
            message: Tag message

        Returns:
            GitHubTag: Created tag
        """
        pass

    @abstractmethod
    async def get_tags(self, repo_name: str) -> List[GitHubTag]:
        """
        Get all tags for a repository.

        Args:
            repo_name: Repository name in format "owner/repo"

        Returns:
            List[GitHubTag]: List of tags
        """
        pass

    @abstractmethod
    async def validate_connection(self) -> Dict[str, Any]:
        """
        Validate the connection and return user information.

        Returns:
            Dict[str, Any]: User information and connection status
        """
        pass
