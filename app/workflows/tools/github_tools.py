"""
GitHub Tools for LangGraph Workflows

This module provides tools for GitHub operations that can be used
in LangGraph workflows, wrapping the GitHub interface methods.
"""

import asyncio
from typing import Any, Dict, List, Optional

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from app.integrations.factory import create_api_clients


class GetRepositoryInput(BaseModel):
    """Input for getting repository information."""
    repo_name: str = Field(description="Repository name in format 'owner/repo' or just 'repo'")


class GetBranchesInput(BaseModel):
    """Input for getting repository branches."""
    repo_name: str = Field(description="Repository name in format 'owner/repo' or just 'repo'")


class FindFeatureBranchesInput(BaseModel):
    """Input for finding feature branches."""
    repo_name: str = Field(description="Repository name in format 'owner/repo' or just 'repo'")
    ticket_ids: List[str] = Field(description="List of JIRA ticket IDs to search for")


class CheckMergeStatusInput(BaseModel):
    """Input for checking merge status."""
    repo_name: str = Field(description="Repository name in format 'owner/repo' or just 'repo'")
    source_branch: str = Field(description="Source branch name")
    target_branch: str = Field(description="Target branch name")


class CreatePullRequestInput(BaseModel):
    """Input for creating a pull request."""
    repo_name: str = Field(description="Repository name in format 'owner/repo' or just 'repo'")
    title: str = Field(description="Pull request title")
    body: str = Field(description="Pull request body/description")
    head_branch: str = Field(description="Source branch name")
    base_branch: str = Field(description="Target branch name")


class MergePullRequestInput(BaseModel):
    """Input for merging a pull request."""
    repo_name: str = Field(description="Repository name in format 'owner/repo' or just 'repo'")
    pr_number: int = Field(description="Pull request number")
    merge_method: str = Field(default="merge", description="Merge method: merge, squash, or rebase")


class GetTagsInput(BaseModel):
    """Input for getting repository tags."""
    repo_name: str = Field(description="Repository name in format 'owner/repo' or just 'repo'")


class CreateTagInput(BaseModel):
    """Input for creating a tag."""
    repo_name: str = Field(description="Repository name in format 'owner/repo' or just 'repo'")
    tag_name: str = Field(description="Tag name (e.g., v1.0.0)")
    sha: str = Field(description="Commit SHA to tag")
    message: str = Field(description="Tag message")


class ValidateConnectionInput(BaseModel):
    """Input for validating GitHub connection."""
    pass


class GitHubTools:
    """Collection of GitHub tools for LangGraph workflows."""

    def __init__(self, use_mock: bool = True):
        """Initialize GitHub tools with API clients."""
        self.clients = create_api_clients(use_mock=use_mock)
        self.github_client = self.clients.github

    async def _ensure_authenticated(self):
        """Ensure GitHub client is authenticated."""
        if not hasattr(self.github_client, '_authenticated') or not self.github_client._authenticated:
            await self.github_client.authenticate()

    class GetRepositoryTool(BaseTool):
        """Tool for getting repository information."""
        name: str = "get_repository"
        description: str = "Get information about a GitHub repository"
        args_schema: type = GetRepositoryInput
        github_tools: Any = None

        def __init__(self, github_tools_instance):
            super().__init__(github_tools=github_tools_instance)

        def _run(self, repo_name: str) -> Dict[str, Any]:
            """Get repository information (synchronous)."""
            import asyncio
            return asyncio.run(self._arun(repo_name))

        async def _arun(self, repo_name: str) -> Dict[str, Any]:
            """Get repository information."""
            await self.github_tools._ensure_authenticated()
            repo = await self.github_tools.github_client.get_repository(repo_name)
            if repo:
                return {
                    "found": True,
                    "repository": {
                        "name": repo.name,
                        "full_name": repo.full_name,
                        "default_branch": repo.default_branch,
                        "url": repo.url,
                        "clone_url": repo.clone_url,
                        "private": repo.private
                    }
                }
            else:
                return {"found": False, "error": f"Repository '{repo_name}' not found"}

    class GetBranchesTool(BaseTool):
        """Tool for getting repository branches."""
        name: str = "get_branches"
        description: str = "Get all branches for a GitHub repository"
        args_schema: type = GetBranchesInput
        github_tools: Any = None

        def __init__(self, github_tools_instance):
            super().__init__(github_tools=github_tools_instance)

        def _run(self, repo_name: str) -> Dict[str, Any]:
            """Get repository branches (synchronous)."""
            import asyncio
            return asyncio.run(self._arun(repo_name))

        async def _arun(self, repo_name: str) -> Dict[str, Any]:
            """Get repository branches."""
            await self.github_tools._ensure_authenticated()
            branches = await self.github_tools.github_client.get_branches(repo_name)
            return {
                "repository": repo_name,
                "branch_count": len(branches),
                "branches": [
                    {
                        "name": branch.name,
                        "sha": branch.sha,
                        "protected": branch.protected,
                        "url": branch.url
                    }
                    for branch in branches
                ]
            }

    class FindFeatureBranchesTool(BaseTool):
        """Tool for finding feature branches by JIRA ticket IDs."""
        name: str = "find_feature_branches"
        description: str = "Find feature branches for specific JIRA ticket IDs"
        args_schema: type = FindFeatureBranchesInput
        github_tools: Any = None

        def __init__(self, github_tools_instance):
            super().__init__(github_tools=github_tools_instance)

        def _run(self, repo_name: str, ticket_ids: List[str]) -> Dict[str, Any]:
            """Find feature branches for ticket IDs (synchronous)."""
            import asyncio
            return asyncio.run(self._arun(repo_name, ticket_ids))

        async def _arun(self, repo_name: str, ticket_ids: List[str]) -> Dict[str, Any]:
            """Find feature branches for ticket IDs."""
            await self.github_tools._ensure_authenticated()
            branches = await self.github_tools.github_client.find_feature_branches(repo_name, ticket_ids)
            return {
                "repository": repo_name,
                "ticket_ids": ticket_ids,
                "found_branches": {
                    ticket_id: {
                        "name": branch.name,
                        "sha": branch.sha,
                        "protected": branch.protected,
                        "url": branch.url
                    } if branch else None
                    for ticket_id, branch in branches.items()
                }
            }

    class CheckMergeStatusTool(BaseTool):
        """Tool for checking merge status between branches."""
        name: str = "check_merge_status"
        description: str = "Check if one branch can be merged into another"
        args_schema: type = CheckMergeStatusInput
        github_tools: Any = None

        def __init__(self, github_tools_instance):
            super().__init__(github_tools=github_tools_instance)

        def _run(self, repo_name: str, source_branch: str, target_branch: str) -> Dict[str, Any]:
            """Check merge status between branches (synchronous)."""
            import asyncio
            return asyncio.run(self._arun(repo_name, source_branch, target_branch))

        async def _arun(self, repo_name: str, source_branch: str, target_branch: str) -> Dict[str, Any]:
            """Check merge status between branches."""
            await self.github_tools._ensure_authenticated()
            status = await self.github_tools.github_client.check_merge_status(repo_name, source_branch, target_branch)
            return {
                "repository": repo_name,
                "source_branch": source_branch,
                "target_branch": target_branch,
                "merge_status": status
            }

    class GetTagsTool(BaseTool):
        """Tool for getting repository tags."""
        name: str = "get_tags"
        description: str = "Get all tags for a GitHub repository"
        args_schema: type = GetTagsInput
        github_tools: Any = None

        def __init__(self, github_tools_instance):
            super().__init__(github_tools=github_tools_instance)

        def _run(self, repo_name: str) -> Dict[str, Any]:
            """Get repository tags (synchronous)."""
            import asyncio
            return asyncio.run(self._arun(repo_name))

        async def _arun(self, repo_name: str) -> Dict[str, Any]:
            """Get repository tags."""
            await self.github_tools._ensure_authenticated()
            tags = await self.github_tools.github_client.get_tags(repo_name)
            return {
                "repository": repo_name,
                "tag_count": len(tags),
                "tags": [
                    {
                        "name": tag.name,
                        "sha": tag.sha,
                        "url": tag.url,
                        "tagger": tag.tagger,
                        "date": tag.date,
                        "message": tag.message
                    }
                    for tag in tags
                ]
            }

    class ValidateConnectionTool(BaseTool):
        """Tool for validating GitHub connection."""
        name: str = "validate_github_connection"
        description: str = "Validate the GitHub API connection and get user information"
        args_schema: type = ValidateConnectionInput
        github_tools: Any = None

        def __init__(self, github_tools_instance):
            super().__init__(github_tools=github_tools_instance)

        def _run(self) -> Dict[str, Any]:
            """Validate GitHub connection (synchronous)."""
            import asyncio
            return asyncio.run(self._arun())

        async def _arun(self) -> Dict[str, Any]:
            """Validate GitHub connection."""
            await self.github_tools._ensure_authenticated()
            connection_info = await self.github_tools.github_client.validate_connection()
            return {
                "status": "connected",
                "connection_info": connection_info
            }

    def get_tools(self) -> List[BaseTool]:
        """Get all GitHub tools."""
        return [
            self.GetRepositoryTool(self),
            self.GetBranchesTool(self),
            self.FindFeatureBranchesTool(self),
            self.CheckMergeStatusTool(self),
            self.GetTagsTool(self),
            self.ValidateConnectionTool(self),
        ] 