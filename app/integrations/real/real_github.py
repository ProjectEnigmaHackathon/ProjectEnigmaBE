"""
Real GitHub API Implementation

Provides real GitHub API integration using the PyGithub library.
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from github import Github
from github.GithubException import (
    BadCredentialsException,
    GithubException,
    UnknownObjectException,
)

from ..base.github_interface import (
    GitHubBranch,
    GitHubInterface,
    GitHubPullRequest,
    GitHubRepository,
    GitHubTag,
)
from ..exceptions import (
    APIConnectionError,
    GitHubAuthenticationError,
    GitHubBranchNotFoundError,
    GitHubError,
    GitHubMergeConflictError,
    GitHubRateLimitError,
    GitHubRepositoryNotFoundError,
    ResourceNotFoundError,
)
from ..rate_limiter import get_rate_limiter

logger = logging.getLogger(__name__)


class RealGitHubClient(GitHubInterface):
    """Real implementation of GitHub API client using PyGithub."""

    def __init__(self, token: str, organization: str = ""):
        self.token = token
        self.organization = organization
        self._client: Optional[Github] = None
        self._authenticated = False
        self.rate_limiter = get_rate_limiter()

    def _get_client(self) -> Github:
        """Get or create GitHub client instance."""
        if self._client is None:
            try:
                self._client = Github(self.token, timeout=30)
            except Exception as e:
                logger.error(f"Failed to create GitHub client: {str(e)}")
                raise APIConnectionError("GitHub", "https://api.github.com", str(e))

        return self._client

    def _convert_github_branch(self, branch, repo_full_name: str) -> GitHubBranch:
        """Convert GitHub branch object to GitHubBranch model."""
        try:
            return GitHubBranch(
                name=branch.name,
                sha=branch.commit.sha,
                protected=branch.protected,
                url=f"https://github.com/{repo_full_name}/tree/{branch.name}",
            )
        except Exception as e:
            logger.error(f"Failed to convert GitHub branch: {str(e)}")
            raise GitHubError(f"Failed to parse GitHub branch: {str(e)}")

    def _convert_github_pr(self, pr, repo_full_name: str) -> GitHubPullRequest:
        """Convert GitHub pull request object to GitHubPullRequest model."""
        try:
            return GitHubPullRequest(
                number=pr.number,
                title=pr.title,
                body=pr.body,
                state=pr.state,
                head_branch=pr.head.ref,
                base_branch=pr.base.ref,
                url=pr.html_url,
                created_at=pr.created_at.isoformat(),
                updated_at=pr.updated_at.isoformat(),
                merged_at=pr.merged_at.isoformat() if pr.merged_at else None,
                author=pr.user.login,
            )
        except Exception as e:
            logger.error(f"Failed to convert GitHub PR: {str(e)}")
            raise GitHubError(f"Failed to parse GitHub PR: {str(e)}")

    def _convert_github_tag(self, tag, repo_full_name: str) -> GitHubTag:
        """Convert GitHub tag object to GitHubTag model."""
        try:
            # Try to get tag details if it's an annotated tag
            tagger = None
            date = None
            message = None

            try:
                if hasattr(tag, "object") and tag.object.type == "tag":
                    tag_obj = tag.object
                    if hasattr(tag_obj, "tagger") and tag_obj.tagger:
                        tagger = tag_obj.tagger.email
                        date = tag_obj.tagger.date.isoformat()
                    if hasattr(tag_obj, "message"):
                        message = tag_obj.message
            except:
                pass  # Fall back to basic info

            return GitHubTag(
                name=tag.name,
                sha=tag.commit.sha,
                url=f"https://github.com/{repo_full_name}/releases/tag/{tag.name}",
                tagger=tagger,
                date=date,
                message=message,
            )
        except Exception as e:
            logger.error(f"Failed to convert GitHub tag: {str(e)}")
            raise GitHubError(f"Failed to parse GitHub tag: {str(e)}")

    def _convert_github_repo(self, repo) -> GitHubRepository:
        """Convert GitHub repository object to GitHubRepository model."""
        try:
            return GitHubRepository(
                name=repo.name,
                full_name=repo.full_name,
                default_branch=repo.default_branch,
                url=repo.html_url,
                clone_url=repo.clone_url,
                private=repo.private,
            )
        except Exception as e:
            logger.error(f"Failed to convert GitHub repository: {str(e)}")
            raise GitHubError(f"Failed to parse GitHub repository: {str(e)}")

    async def authenticate(self) -> bool:
        """Authenticate with GitHub API."""
        try:
            await self.rate_limiter.acquire("github", "auth")

            client = self._get_client()

            # Test authentication by getting user info
            user = await asyncio.get_event_loop().run_in_executor(
                None, lambda: client.get_user()
            )

            self._authenticated = True
            logger.info(f"Successfully authenticated with GitHub as {user.login}")
            return True

        except BadCredentialsException as e:
            logger.error(f"GitHub authentication failed: Invalid token")
            raise GitHubAuthenticationError("Invalid GitHub token")
        except GithubException as e:
            logger.error(f"GitHub authentication failed: {str(e)}")
            if e.status == 401:
                raise GitHubAuthenticationError("Invalid GitHub token")
            elif e.status == 403:
                raise GitHubAuthenticationError(
                    "Access forbidden - check token permissions"
                )
            else:
                raise GitHubAuthenticationError(f"Authentication failed: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error during GitHub authentication: {str(e)}")
            raise APIConnectionError("GitHub", "https://api.github.com", str(e))

    async def get_repository(self, repo_name: str) -> Optional[GitHubRepository]:
        """Get repository information."""
        try:
            await self.rate_limiter.acquire("github", "get_repo")

            client = self._get_client()

            # Get repository
            repo = await asyncio.get_event_loop().run_in_executor(
                None, lambda: client.get_repo(repo_name)
            )

            return self._convert_github_repo(repo)

        except UnknownObjectException:
            logger.warning(f"GitHub repository not found: {repo_name}")
            return None
        except GithubException as e:
            if e.status == 404:
                return None
            elif e.status == 429:
                raise GitHubRateLimitError()
            elif e.status == 401:
                raise GitHubAuthenticationError("Authentication expired")
            else:
                logger.error(f"GitHub get repository failed: {str(e)}")
                raise GitHubError(f"Failed to get repository {repo_name}: {str(e)}")
        except Exception as e:
            logger.error(
                f"Unexpected error getting GitHub repository {repo_name}: {str(e)}"
            )
            raise GitHubError(f"Failed to get repository: {str(e)}")

    async def get_branches(self, repo_name: str) -> List[GitHubBranch]:
        """Get all branches for a repository."""
        try:
            await self.rate_limiter.acquire("github", "get_branches")

            client = self._get_client()
            repo = await asyncio.get_event_loop().run_in_executor(
                None, lambda: client.get_repo(repo_name)
            )

            # Get branches
            branches = await asyncio.get_event_loop().run_in_executor(
                None, lambda: list(repo.get_branches())
            )

            # Convert to GitHubBranch objects
            github_branches = []
            for branch in branches:
                try:
                    github_branch = self._convert_github_branch(branch, repo_name)
                    github_branches.append(github_branch)
                except Exception as e:
                    logger.warning(f"Failed to convert branch {branch.name}: {str(e)}")
                    continue

            logger.info(f"Retrieved {len(github_branches)} branches for {repo_name}")
            return github_branches

        except UnknownObjectException:
            raise GitHubRepositoryNotFoundError(repo_name)
        except GithubException as e:
            if e.status == 404:
                raise GitHubRepositoryNotFoundError(repo_name)
            elif e.status == 429:
                raise GitHubRateLimitError()
            elif e.status == 401:
                raise GitHubAuthenticationError("Authentication expired")
            else:
                logger.error(f"GitHub get branches failed: {str(e)}")
                raise GitHubError(f"Failed to get branches for {repo_name}: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error getting GitHub branches: {str(e)}")
            raise GitHubError(f"Failed to get branches: {str(e)}")

    async def find_feature_branches(
        self, repo_name: str, ticket_ids: List[str]
    ) -> Dict[str, Optional[GitHubBranch]]:
        """Find feature branches for JIRA ticket IDs."""
        try:
            # Get all branches first
            branches = await self.get_branches(repo_name)

            # Create a map of branch names to branch objects
            branch_map = {branch.name: branch for branch in branches}

            # Find feature branches for each ticket
            result = {}
            for ticket_id in ticket_ids:
                feature_branch_name = f"feature/{ticket_id}"
                found_branch = branch_map.get(feature_branch_name)
                result[ticket_id] = found_branch

                if found_branch:
                    logger.info(
                        f"Found feature branch {feature_branch_name} for {ticket_id}"
                    )
                else:
                    logger.warning(
                        f"Feature branch {feature_branch_name} not found for {ticket_id}"
                    )

            return result

        except Exception as e:
            logger.error(f"Failed to find feature branches: {str(e)}")
            raise GitHubError(f"Failed to find feature branches: {str(e)}")

    async def check_merge_status(
        self, repo_name: str, source_branch: str, target_branch: str
    ) -> Dict[str, Any]:
        """Check if source branch is merged into target branch."""
        try:
            await self.rate_limiter.acquire("github", "compare_branches")

            client = self._get_client()
            repo = await asyncio.get_event_loop().run_in_executor(
                None, lambda: client.get_repo(repo_name)
            )

            # Compare branches
            comparison = await asyncio.get_event_loop().run_in_executor(
                None, lambda: repo.compare(target_branch, source_branch)
            )

            # Check if branches are identical (merged)
            is_merged = comparison.ahead_by == 0 and comparison.behind_by == 0

            return {
                "merged": is_merged,
                "merge_commit_sha": None,  # Would need to check commit history for exact merge commit
                "ahead_by": comparison.ahead_by,
                "behind_by": comparison.behind_by,
                "status": comparison.status,
            }

        except UnknownObjectException:
            raise GitHubRepositoryNotFoundError(repo_name)
        except GithubException as e:
            if e.status == 404:
                # One of the branches doesn't exist
                raise GitHubBranchNotFoundError(f"{source_branch} or {target_branch}")
            elif e.status == 429:
                raise GitHubRateLimitError()
            elif e.status == 401:
                raise GitHubAuthenticationError("Authentication expired")
            else:
                logger.error(f"GitHub branch comparison failed: {str(e)}")
                raise GitHubError(f"Failed to compare branches: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error comparing branches: {str(e)}")
            raise GitHubError(f"Failed to compare branches: {str(e)}")

    async def create_pull_request(
        self, repo_name: str, title: str, body: str, head_branch: str, base_branch: str
    ) -> GitHubPullRequest:
        """Create a pull request."""
        try:
            await self.rate_limiter.acquire("github", "create_pr")

            client = self._get_client()
            repo = await asyncio.get_event_loop().run_in_executor(
                None, lambda: client.get_repo(repo_name)
            )

            # Create pull request
            pr = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: repo.create_pull(
                    title=title, body=body, head=head_branch, base=base_branch
                ),
            )

            logger.info(f"Created PR #{pr.number}: {title}")
            return self._convert_github_pr(pr, repo_name)

        except UnknownObjectException:
            raise GitHubRepositoryNotFoundError(repo_name)
        except GithubException as e:
            if e.status == 422:
                # Validation failed - likely branch doesn't exist or PR already exists
                raise GitHubError(
                    f"PR creation failed - check if branches exist and PR doesn't already exist: {str(e)}"
                )
            elif e.status == 404:
                raise GitHubRepositoryNotFoundError(repo_name)
            elif e.status == 429:
                raise GitHubRateLimitError()
            elif e.status == 401:
                raise GitHubAuthenticationError("Authentication expired")
            else:
                logger.error(f"GitHub create PR failed: {str(e)}")
                raise GitHubError(f"Failed to create PR: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error creating PR: {str(e)}")
            raise GitHubError(f"Failed to create PR: {str(e)}")

    async def merge_branches(
        self, repo_name: str, source_branch: str, target_branch: str
    ) -> Dict[str, Any]:
        """Merge source branch into target branch."""
        try:
            await self.rate_limiter.acquire("github", "merge_branches")

            client = self._get_client()
            repo = await asyncio.get_event_loop().run_in_executor(
                None, lambda: client.get_repo(repo_name)
            )

            # Get source branch SHA
            source_ref = await asyncio.get_event_loop().run_in_executor(
                None, lambda: repo.get_branch(source_branch)
            )

            # Merge branches
            merge = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: repo.merge(
                    base=target_branch,
                    head=source_ref.commit.sha,
                    commit_message=f"Merge {source_branch} into {target_branch}",
                ),
            )

            logger.info(f"Successfully merged {source_branch} into {target_branch}")
            return {
                "merged": True,
                "sha": merge.sha,
                "message": f"Merged {source_branch} into {target_branch}",
            }

        except UnknownObjectException:
            raise GitHubRepositoryNotFoundError(repo_name)
        except GithubException as e:
            if e.status == 409:
                # Merge conflict
                raise GitHubMergeConflictError(source_branch, target_branch, repo_name)
            elif e.status == 404:
                raise GitHubBranchNotFoundError(f"{source_branch} or {target_branch}")
            elif e.status == 429:
                raise GitHubRateLimitError()
            elif e.status == 401:
                raise GitHubAuthenticationError("Authentication expired")
            else:
                logger.error(f"GitHub merge failed: {str(e)}")
                raise GitHubError(f"Failed to merge branches: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error merging branches: {str(e)}")
            raise GitHubError(f"Failed to merge branches: {str(e)}")

    async def create_branch(
        self, repo_name: str, branch_name: str, source_branch: str = "main"
    ) -> GitHubBranch:
        """Create a new branch."""
        try:
            await self.rate_limiter.acquire("github", "create_branch")

            client = self._get_client()
            repo = await asyncio.get_event_loop().run_in_executor(
                None, lambda: client.get_repo(repo_name)
            )

            # Get source branch SHA
            source_ref = await asyncio.get_event_loop().run_in_executor(
                None, lambda: repo.get_branch(source_branch)
            )

            # Create new branch
            await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: repo.create_git_ref(
                    ref=f"refs/heads/{branch_name}", sha=source_ref.commit.sha
                ),
            )

            # Get the created branch
            new_branch = await asyncio.get_event_loop().run_in_executor(
                None, lambda: repo.get_branch(branch_name)
            )

            logger.info(f"Created branch {branch_name} from {source_branch}")
            return self._convert_github_branch(new_branch, repo_name)

        except UnknownObjectException:
            raise GitHubRepositoryNotFoundError(repo_name)
        except GithubException as e:
            if e.status == 422:
                # Branch already exists or validation failed
                raise GitHubError(
                    f"Branch creation failed - branch may already exist: {str(e)}"
                )
            elif e.status == 404:
                raise GitHubBranchNotFoundError(source_branch)
            elif e.status == 429:
                raise GitHubRateLimitError()
            elif e.status == 401:
                raise GitHubAuthenticationError("Authentication expired")
            else:
                logger.error(f"GitHub create branch failed: {str(e)}")
                raise GitHubError(f"Failed to create branch: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error creating branch: {str(e)}")
            raise GitHubError(f"Failed to create branch: {str(e)}")

    async def create_tag(
        self, repo_name: str, tag_name: str, sha: str, message: str
    ) -> GitHubTag:
        """Create a tag."""
        try:
            await self.rate_limiter.acquire("github", "create_tag")

            client = self._get_client()
            repo = await asyncio.get_event_loop().run_in_executor(
                None, lambda: client.get_repo(repo_name)
            )

            # Create tag
            tag = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: repo.create_git_tag(
                    tag=tag_name, message=message, object=sha, type="commit"
                ),
            )

            # Create reference
            await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: repo.create_git_ref(ref=f"refs/tags/{tag_name}", sha=tag.sha),
            )

            logger.info(f"Created tag {tag_name} at {sha}")
            return GitHubTag(
                name=tag_name,
                sha=sha,
                url=f"https://github.com/{repo_name}/releases/tag/{tag_name}",
                tagger=None,  # Would need to get from tag object
                date=datetime.now().isoformat(),
                message=message,
            )

        except UnknownObjectException:
            raise GitHubRepositoryNotFoundError(repo_name)
        except GithubException as e:
            if e.status == 422:
                # Tag already exists or validation failed
                raise GitHubError(
                    f"Tag creation failed - tag may already exist: {str(e)}"
                )
            elif e.status == 404:
                raise GitHubRepositoryNotFoundError(repo_name)
            elif e.status == 429:
                raise GitHubRateLimitError()
            elif e.status == 401:
                raise GitHubAuthenticationError("Authentication expired")
            else:
                logger.error(f"GitHub create tag failed: {str(e)}")
                raise GitHubError(f"Failed to create tag: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error creating tag: {str(e)}")
            raise GitHubError(f"Failed to create tag: {str(e)}")

    async def get_tags(self, repo_name: str) -> List[GitHubTag]:
        """Get all tags for a repository."""
        try:
            await self.rate_limiter.acquire("github", "get_tags")

            client = self._get_client()
            repo = await asyncio.get_event_loop().run_in_executor(
                None, lambda: client.get_repo(repo_name)
            )

            # Get tags
            tags = await asyncio.get_event_loop().run_in_executor(
                None, lambda: list(repo.get_tags())
            )

            # Convert to GitHubTag objects
            github_tags = []
            for tag in tags:
                try:
                    github_tag = self._convert_github_tag(tag, repo_name)
                    github_tags.append(github_tag)
                except Exception as e:
                    logger.warning(f"Failed to convert tag {tag.name}: {str(e)}")
                    continue

            logger.info(f"Retrieved {len(github_tags)} tags for {repo_name}")
            return github_tags

        except UnknownObjectException:
            raise GitHubRepositoryNotFoundError(repo_name)
        except GithubException as e:
            if e.status == 404:
                raise GitHubRepositoryNotFoundError(repo_name)
            elif e.status == 429:
                raise GitHubRateLimitError()
            elif e.status == 401:
                raise GitHubAuthenticationError("Authentication expired")
            else:
                logger.error(f"GitHub get tags failed: {str(e)}")
                raise GitHubError(f"Failed to get tags for {repo_name}: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error getting GitHub tags: {str(e)}")
            raise GitHubError(f"Failed to get tags: {str(e)}")

    async def validate_connection(self) -> Dict[str, Any]:
        """Validate the connection and return user information."""
        try:
            await self.rate_limiter.acquire("github", "get_user")

            client = self._get_client()

            # Get user info
            user = await asyncio.get_event_loop().run_in_executor(
                None, lambda: client.get_user()
            )

            # Get organizations
            orgs = await asyncio.get_event_loop().run_in_executor(
                None, lambda: list(user.get_orgs())
            )

            return {
                "status": "connected",
                "user": user.login,
                "name": user.name or user.login,
                "email": user.email,
                "organizations": [org.login for org in orgs],
                "rate_limit": client.get_rate_limit().core.remaining,
            }

        except BadCredentialsException:
            raise GitHubAuthenticationError("Invalid GitHub token")
        except GithubException as e:
            if e.status == 401:
                raise GitHubAuthenticationError("Invalid GitHub token")
            else:
                raise GitHubError(f"Connection validation failed: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error validating GitHub connection: {str(e)}")
            raise APIConnectionError("GitHub", "https://api.github.com", str(e))
