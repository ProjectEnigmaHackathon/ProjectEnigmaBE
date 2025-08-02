"""
Application Configuration Management

This module handles all configuration settings for the Project Enigma backend,
including environment variables, API credentials, and deployment settings.
"""

import os
from functools import lru_cache
from typing import List

from pydantic import Field, validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Application settings
    app_name: str = "Project Enigma Backend"
    environment: str = Field(
        default="development", description="Environment: development, production"
    )
    debug: bool = Field(default=True, description="Enable debug mode")

    # Server settings
    host: str = Field(default="0.0.0.0", description="Server host")
    port: int = Field(default=8000, description="Server port")

    # CORS settings
    allowed_origins: str = Field(
        default="http://localhost:3000,http://localhost:5173,http://127.0.0.1:3000",
        description="Allowed CORS origins (comma-separated)",
    )

    # API Integration settings
    jira_base_url: str = Field(default="", description="JIRA instance base URL")
    jira_username: str = Field(default="", description="JIRA username")
    jira_token: str = Field(default="", description="JIRA API token")

    github_token: str = Field(default="", description="GitHub personal access token")
    github_organization: str = Field(default="", description="GitHub organization name")

    atlassian_account_id: str = Field(default="", description="Atlassian Account ID")
    confluence_base_url: str = Field(
        default="", description="Confluence instance base URL"
    )
    confluence_username: str = Field(default="", description="Confluence username")
    confluence_token: str = Field(default="", description="Confluence API token")
    confluence_space_key: str = Field(
        default="DEV", description="Confluence space key for documentation"
    )

    # Feature flags
    use_mock_apis: bool = Field(
        default=True, description="Use mock APIs instead of real integrations"
    )
    enable_workflow_persistence: bool = Field(
        default=True, description="Enable workflow state persistence"
    )

    # File system settings
    config_directory: str = Field(
        default="config", description="Configuration files directory"
    )
    repositories_config_file: str = Field(
        default="repositories.json", description="Repository configuration file"
    )
    chat_history_directory: str = Field(
        default="data/chat_history", description="Chat history storage directory"
    )

    # Security settings
    secret_key: str = Field(
        default="development-secret-key-change-in-production",
        description="Secret key for sessions",
    )
    openai_api_key: str = Field(
        default="",
        description="OpenAPI Secret key",
    )

    @validator("environment")
    def validate_environment(cls, v):
        """Validate environment setting."""
        if v not in ["development", "production", "testing"]:
            raise ValueError(
                "Environment must be one of: development, production, testing"
            )
        return v

    @validator("allowed_origins")
    def parse_cors_origins(cls, v):
        """Parse CORS origins from string."""
        if isinstance(v, str):
            return v
        return ",".join(v) if isinstance(v, list) else str(v)

    @property
    def allowed_origins_list(self) -> List[str]:
        """Get allowed origins as a list."""
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]

    class Config:
        env_file = ".env"
        env_prefix = "ENIGMA_"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    """Get cached application settings."""
    return Settings()


def get_repositories_config_path() -> str:
    """Get the full path to the repositories configuration file."""
    settings = get_settings()
    return os.path.join(settings.config_directory, settings.repositories_config_file)


def get_chat_history_path() -> str:
    """Get the full path to the chat history directory."""
    settings = get_settings()
    return settings.chat_history_directory
