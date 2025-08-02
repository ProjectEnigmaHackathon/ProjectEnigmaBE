"""Repository management service with JSON persistence and atomic operations."""

import json
import os
import shutil
import tempfile
import time
import uuid

try:
    import fcntl

    HAS_FCNTL = True
except ImportError:
    # Windows doesn't have fcntl, we'll use file-based locking
    HAS_FCNTL = False
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..core.exceptions import (
    ConfigurationError,
    RepositoryExistsError,
    RepositoryNotFoundError,
)
from ..models.api import RepositoryConfig, RepositoryConfigList, RepositoryRequest


class RepositoryService:
    """Service for managing repository configurations with atomic operations and backup."""

    def __init__(self, config_path: str = "config/repositories.json"):
        self.config_path = Path(config_path)
        self.backup_dir = self.config_path.parent / "backups"
        self.lock_file = self.config_path.with_suffix(".lock")

        # Ensure directories exist
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.backup_dir.mkdir(parents=True, exist_ok=True)

        # Initialize config file if it doesn't exist
        if not self.config_path.exists():
            self._initialize_config()

    def _initialize_config(self) -> None:
        """Initialize empty configuration file."""
        initial_config = RepositoryConfigList(
            repositories=[],
            metadata={
                "version": "1.0",
                "created_at": datetime.utcnow().isoformat(),
                "last_updated": datetime.utcnow().isoformat(),
                "total_repositories": 0,
            },
        )
        self._write_config_atomic(initial_config)

    @contextmanager
    def _file_lock(self):
        """Context manager for file locking to handle concurrent access."""
        if HAS_FCNTL:
            # Unix-style file locking
            lock_fd = None
            try:
                # Create lock file
                lock_fd = os.open(
                    str(self.lock_file), os.O_CREAT | os.O_WRONLY | os.O_TRUNC
                )

                # Acquire exclusive lock with timeout
                try:
                    fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except (IOError, OSError):
                    # If we can't get the lock immediately, wait a bit and try again
                    time.sleep(0.1)
                    fcntl.flock(lock_fd, fcntl.LOCK_EX)

                yield

            finally:
                if lock_fd is not None:
                    fcntl.flock(lock_fd, fcntl.LOCK_UN)
                    os.close(lock_fd)
                    # Clean up lock file
                    try:
                        os.unlink(str(self.lock_file))
                    except OSError:
                        pass
        else:
            # Windows-compatible file-based locking
            max_attempts = 50
            attempt = 0

            while attempt < max_attempts:
                try:
                    # Try to create lock file exclusively
                    lock_fd = os.open(
                        str(self.lock_file), os.O_CREAT | os.O_EXCL | os.O_WRONLY
                    )
                    os.close(lock_fd)
                    break
                except (OSError, IOError):
                    # Lock file exists, wait and retry
                    time.sleep(0.05)
                    attempt += 1

            if attempt >= max_attempts:
                raise IOError("Could not acquire file lock after multiple attempts")

            try:
                yield
            finally:
                # Clean up lock file
                try:
                    os.unlink(str(self.lock_file))
                except OSError:
                    pass

    def _create_backup(self) -> Optional[Path]:
        """Create a backup of the current configuration."""
        if not self.config_path.exists():
            return None

        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        backup_path = self.backup_dir / f"repositories_{timestamp}.json"

        try:
            shutil.copy2(str(self.config_path), str(backup_path))

            # Keep only the latest 10 backups
            backups = sorted(self.backup_dir.glob("repositories_*.json"))
            if len(backups) > 10:
                for old_backup in backups[:-10]:
                    old_backup.unlink()

            return backup_path
        except Exception as e:
            # Log the error but don't fail the operation
            print(f"Warning: Failed to create backup: {e}")
            return None

    def _read_config(self) -> RepositoryConfigList:
        """Read configuration from file with validation."""
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            # Validate and parse the configuration
            config = RepositoryConfigList(**data)
            return config

        except FileNotFoundError:
            # Return empty config if file doesn't exist
            return RepositoryConfigList()
        except json.JSONDecodeError as e:
            raise ConfigurationError(f"Invalid JSON in configuration file: {e}")
        except Exception as e:
            raise ConfigurationError(f"Failed to read configuration: {e}")

    def _write_config_atomic(self, config: RepositoryConfigList) -> None:
        """Write configuration atomically using temporary file."""
        # Update metadata
        config.metadata.update(
            {
                "last_updated": datetime.utcnow().isoformat(),
                "total_repositories": len(config.repositories),
            }
        )

        # Convert to JSON with proper formatting
        config_data = config.dict()

        # Write to temporary file first
        temp_fd, temp_path = tempfile.mkstemp(
            suffix=".tmp", dir=str(self.config_path.parent), text=True
        )

        try:
            with os.fdopen(temp_fd, "w", encoding="utf-8") as f:
                json.dump(config_data, f, indent=2, ensure_ascii=False, default=str)
                f.flush()
                os.fsync(f.fileno())  # Ensure data is written to disk

            # Atomically replace the original file
            shutil.move(temp_path, str(self.config_path))

        except Exception:
            # Clean up temporary file on error
            try:
                os.unlink(temp_path)
            except OSError:
                pass
            raise

    def list_repositories(self) -> List[RepositoryConfig]:
        """Get list of all repositories."""
        with self._file_lock():
            config = self._read_config()
            return [repo for repo in config.repositories if repo.is_active]

    def get_repository(self, repo_id: str) -> RepositoryConfig:
        """Get a specific repository by ID."""
        with self._file_lock():
            config = self._read_config()

            for repo in config.repositories:
                if repo.id == repo_id and repo.is_active:
                    return repo

            raise RepositoryNotFoundError(f"Repository with ID '{repo_id}' not found")

    def create_repository(self, request: RepositoryRequest) -> RepositoryConfig:
        """Create a new repository configuration."""
        with self._file_lock():
            # Create backup before making changes
            self._create_backup()

            config = self._read_config()

            # Check for duplicate names
            for repo in config.repositories:
                if repo.is_active and repo.name.lower() == request.name.lower():
                    raise RepositoryExistsError(
                        f"Repository with name '{request.name}' already exists"
                    )

            # Create new repository
            new_repo = RepositoryConfig(
                id=str(uuid.uuid4()),
                name=request.name,
                url=request.url,
                description=request.description,
                is_active=True,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )

            config.repositories.append(new_repo)
            self._write_config_atomic(config)

            return new_repo

    def update_repository(
        self, repo_id: str, request: RepositoryRequest
    ) -> RepositoryConfig:
        """Update an existing repository configuration."""
        with self._file_lock():
            # Create backup before making changes
            self._create_backup()

            config = self._read_config()

            # Find the repository to update
            repo_to_update = None
            for i, repo in enumerate(config.repositories):
                if repo.id == repo_id and repo.is_active:
                    repo_to_update = repo
                    repo_index = i
                    break

            if not repo_to_update:
                raise RepositoryNotFoundError(
                    f"Repository with ID '{repo_id}' not found"
                )

            # Check for duplicate names (excluding current repository)
            for repo in config.repositories:
                if (
                    repo.is_active
                    and repo.id != repo_id
                    and repo.name.lower() == request.name.lower()
                ):
                    raise RepositoryExistsError(
                        f"Repository with name '{request.name}' already exists"
                    )

            # Update repository
            updated_repo = RepositoryConfig(
                id=repo_to_update.id,
                name=request.name,
                url=request.url,
                description=request.description,
                is_active=True,
                created_at=repo_to_update.created_at,
                updated_at=datetime.utcnow(),
            )

            config.repositories[repo_index] = updated_repo
            self._write_config_atomic(config)

            return updated_repo

    def delete_repository(self, repo_id: str) -> bool:
        """Delete a repository configuration (soft delete)."""
        with self._file_lock():
            # Create backup before making changes
            self._create_backup()

            config = self._read_config()

            # Find and soft delete the repository
            for repo in config.repositories:
                if repo.id == repo_id and repo.is_active:
                    repo.is_active = False
                    repo.updated_at = datetime.utcnow()
                    self._write_config_atomic(config)
                    return True

            raise RepositoryNotFoundError(f"Repository with ID '{repo_id}' not found")

    def get_statistics(self) -> Dict[str, Any]:
        """Get repository statistics."""
        with self._file_lock():
            config = self._read_config()

            active_repos = [repo for repo in config.repositories if repo.is_active]

            return {
                "total_repositories": len(active_repos),
                "total_ever_created": len(config.repositories),
                "last_updated": config.metadata.get("last_updated"),
                "backup_count": (
                    len(list(self.backup_dir.glob("repositories_*.json")))
                    if self.backup_dir.exists()
                    else 0
                ),
            }

    def restore_from_backup(self, backup_filename: str) -> bool:
        """Restore configuration from a backup file."""
        backup_path = self.backup_dir / backup_filename

        if not backup_path.exists():
            raise ConfigurationError(f"Backup file '{backup_filename}' not found")

        with self._file_lock():
            try:
                # Validate the backup file first
                with open(backup_path, "r", encoding="utf-8") as f:
                    backup_data = json.load(f)

                # Validate structure
                RepositoryConfigList(**backup_data)

                # Create a backup of current config before restoring
                self._create_backup()

                # Replace current config with backup
                shutil.copy2(str(backup_path), str(self.config_path))

                return True

            except Exception as e:
                raise ConfigurationError(f"Failed to restore from backup: {e}")

    def list_backups(self) -> List[Dict[str, Any]]:
        """List available backup files."""
        backups = []

        if self.backup_dir.exists():
            for backup_path in sorted(
                self.backup_dir.glob("repositories_*.json"), reverse=True
            ):
                stat = backup_path.stat()
                backups.append(
                    {
                        "filename": backup_path.name,
                        "created_at": datetime.fromtimestamp(stat.st_ctime).isoformat(),
                        "size": stat.st_size,
                    }
                )

        return backups
