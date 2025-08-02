"""Repository management endpoints."""

from typing import List

import structlog
from fastapi import APIRouter, Depends, HTTPException

from ...core.exceptions import (
    ConfigurationError,
    RepositoryExistsError,
    RepositoryNotFoundError,
)
from ...models.api import RepositoryConfig, RepositoryRequest
from ...services.repository_service import RepositoryService
from ...core.logging_utils import log_api_endpoint, LogLevel

logger = structlog.get_logger()
router = APIRouter()


def get_repository_service() -> RepositoryService:
    """Dependency to get repository service instance."""
    return RepositoryService()


@router.get("/", response_model=List[RepositoryConfig])
@log_api_endpoint(level=LogLevel.INFO, include_request=True, include_response=False, include_execution_time=True, log_errors=True)
async def get_repositories(
    service: RepositoryService = Depends(get_repository_service),
):
    """Get list of configured repositories."""
    try:
        repositories = service.list_repositories()
        logger.info("Retrieved repositories", count=len(repositories))
        return repositories
    except Exception as e:
        logger.error("Failed to retrieve repositories", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to retrieve repositories")


@router.get("/{repo_id}", response_model=RepositoryConfig)
@log_api_endpoint(level=LogLevel.INFO, include_request=True, include_response=False, include_execution_time=True, log_errors=True)
async def get_repository(
    repo_id: str, service: RepositoryService = Depends(get_repository_service)
):
    """Get a specific repository by ID."""
    try:
        repository = service.get_repository(repo_id)
        logger.info("Retrieved repository", repo_id=repo_id, repo_name=repository.name)
        return repository
    except RepositoryNotFoundError as e:
        logger.warning("Repository not found", repo_id=repo_id)
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error("Failed to retrieve repository", repo_id=repo_id, error=str(e))
        raise HTTPException(status_code=500, detail="Failed to retrieve repository")


@router.post("/", response_model=RepositoryConfig, status_code=201)
@log_api_endpoint(level=LogLevel.INFO, include_request=True, include_response=False, include_execution_time=True, log_errors=True)
async def create_repository(
    request: RepositoryRequest,
    service: RepositoryService = Depends(get_repository_service),
):
    """Add a new repository configuration."""
    try:
        repository = service.create_repository(request)
        logger.info(
            "Created repository",
            repo_id=repository.id,
            repo_name=repository.name,
            repo_url=repository.url,
        )
        return repository
    except RepositoryExistsError as e:
        logger.warning("Repository already exists", repo_name=request.name)
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        logger.warning("Invalid repository data", error=str(e))
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.error("Failed to create repository", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to create repository")


@router.put("/{repo_id}", response_model=RepositoryConfig)
@log_api_endpoint(level=LogLevel.INFO, include_request=True, include_response=False, include_execution_time=True, log_errors=True)
async def update_repository(
    repo_id: str,
    request: RepositoryRequest,
    service: RepositoryService = Depends(get_repository_service),
):
    """Update an existing repository configuration."""
    try:
        repository = service.update_repository(repo_id, request)
        logger.info(
            "Updated repository",
            repo_id=repo_id,
            repo_name=repository.name,
            repo_url=repository.url,
        )
        return repository
    except RepositoryNotFoundError as e:
        logger.warning("Repository not found for update", repo_id=repo_id)
        raise HTTPException(status_code=404, detail=str(e))
    except RepositoryExistsError as e:
        logger.warning("Repository name conflict during update", repo_name=request.name)
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        logger.warning("Invalid repository data for update", error=str(e))
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.error("Failed to update repository", repo_id=repo_id, error=str(e))
        raise HTTPException(status_code=500, detail="Failed to update repository")


@router.delete("/{repo_id}", status_code=204)
@log_api_endpoint(level=LogLevel.INFO, include_request=True, include_response=False, include_execution_time=True, log_errors=True)
async def delete_repository(
    repo_id: str, service: RepositoryService = Depends(get_repository_service)
):
    """Delete a repository configuration."""
    try:
        service.delete_repository(repo_id)
        logger.info("Deleted repository", repo_id=repo_id)
        return
    except RepositoryNotFoundError as e:
        logger.warning("Repository not found for deletion", repo_id=repo_id)
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error("Failed to delete repository", repo_id=repo_id, error=str(e))
        raise HTTPException(status_code=500, detail="Failed to delete repository")


@router.get("/stats/summary")
@log_api_endpoint(level=LogLevel.INFO, include_request=True, include_response=False, include_execution_time=True, log_errors=True)
async def get_repository_statistics(
    service: RepositoryService = Depends(get_repository_service),
):
    """Get repository management statistics."""
    try:
        stats = service.get_statistics()
        logger.info("Retrieved repository statistics", stats=stats)
        return stats
    except Exception as e:
        logger.error("Failed to retrieve repository statistics", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to retrieve statistics")


@router.get("/backups/list")
@log_api_endpoint(level=LogLevel.INFO, include_request=True, include_response=False, include_execution_time=True, log_errors=True)
async def list_backups(service: RepositoryService = Depends(get_repository_service)):
    """List available backup files."""
    try:
        backups = service.list_backups()
        logger.info("Retrieved backup list", count=len(backups))
        return {"backups": backups}
    except Exception as e:
        logger.error("Failed to list backups", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to list backups")


@router.post("/backups/restore/{backup_filename}")
@log_api_endpoint(level=LogLevel.INFO, include_request=True, include_response=False, include_execution_time=True, log_errors=True)
async def restore_backup(
    backup_filename: str, service: RepositoryService = Depends(get_repository_service)
):
    """Restore configuration from a backup file."""
    try:
        success = service.restore_from_backup(backup_filename)
        if success:
            logger.info("Restored from backup", backup_filename=backup_filename)
            return {"message": f"Successfully restored from backup: {backup_filename}"}
        else:
            raise HTTPException(status_code=500, detail="Failed to restore from backup")
    except ConfigurationError as e:
        logger.warning(
            "Invalid backup file", backup_filename=backup_filename, error=str(e)
        )
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(
            "Failed to restore backup", backup_filename=backup_filename, error=str(e)
        )
        raise HTTPException(status_code=500, detail="Failed to restore from backup")
