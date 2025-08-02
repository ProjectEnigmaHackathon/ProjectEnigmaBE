"""
Exception Handling and Custom Exceptions

This module defines custom exceptions and global exception handling middleware
for the Project Enigma backend API.
"""

import traceback
from typing import Any, Dict

import structlog
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import ValidationError

logger = structlog.get_logger()


class EnigmaBaseException(Exception):
    """Base exception for Project Enigma."""

    def __init__(
        self, message: str, status_code: int = 500, details: Dict[str, Any] = None
    ):
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        super().__init__(self.message)


class WorkflowException(EnigmaBaseException):
    """Exception raised during workflow execution."""

    def __init__(
        self, message: str, workflow_step: str = None, details: Dict[str, Any] = None
    ):
        super().__init__(message, status_code=422, details=details)
        self.workflow_step = workflow_step


class APIIntegrationException(EnigmaBaseException):
    """Exception raised during external API integration."""

    def __init__(
        self, message: str, api_service: str = None, details: Dict[str, Any] = None
    ):
        super().__init__(message, status_code=502, details=details)
        self.api_service = api_service


class ConfigurationException(EnigmaBaseException):
    """Exception raised for configuration-related errors."""

    def __init__(
        self, message: str, config_key: str = None, details: Dict[str, Any] = None
    ):
        super().__init__(message, status_code=500, details=details)
        self.config_key = config_key


class RepositoryException(EnigmaBaseException):
    """Exception raised for repository management errors."""

    def __init__(
        self, message: str, repository_name: str = None, details: Dict[str, Any] = None
    ):
        super().__init__(message, status_code=404, details=details)
        self.repository_name = repository_name


class RepositoryNotFoundError(RepositoryException):
    """Exception raised when a repository is not found."""

    def __init__(self, message: str, repository_name: str = None):
        super().__init__(message, repository_name=repository_name, details={})


class RepositoryExistsError(RepositoryException):
    """Exception raised when trying to create a repository that already exists."""

    def __init__(self, message: str, repository_name: str = None):
        super().__init__(message, repository_name=repository_name, details={})
        self.status_code = 409  # Conflict


class ConfigurationError(ConfigurationException):
    """Exception raised for configuration file errors."""

    def __init__(self, message: str, config_key: str = None):
        super().__init__(message, config_key=config_key, details={})


async def enigma_exception_handler(request: Request, exc: EnigmaBaseException):
    """Handle custom Enigma exceptions."""
    logger.error(
        "Enigma exception occurred",
        exception_type=type(exc).__name__,
        message=exc.message,
        status_code=exc.status_code,
        details=exc.details,
        path=request.url.path,
        method=request.method,
    )

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "type": type(exc).__name__,
                "message": exc.message,
                "details": exc.details,
                "path": request.url.path,
                "timestamp": logger._context.get("timestamp"),
            }
        },
    )


async def http_exception_handler(request: Request, exc: HTTPException):
    """Handle FastAPI HTTP exceptions."""
    logger.warning(
        "HTTP exception occurred",
        status_code=exc.status_code,
        detail=exc.detail,
        path=request.url.path,
        method=request.method,
    )

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "type": "HTTPException",
                "message": exc.detail,
                "status_code": exc.status_code,
                "path": request.url.path,
            }
        },
    )


async def validation_exception_handler(request: Request, exc: ValidationError):
    """Handle Pydantic validation exceptions."""
    logger.warning(
        "Validation exception occurred",
        errors=exc.errors(),
        path=request.url.path,
        method=request.method,
    )

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": {
                "type": "ValidationError",
                "message": "Request validation failed",
                "details": exc.errors(),
                "path": request.url.path,
            }
        },
    )


async def general_exception_handler(request: Request, exc: Exception):
    """Handle all other unexpected exceptions."""
    logger.error(
        "Unexpected exception occurred",
        exception_type=type(exc).__name__,
        message=str(exc),
        traceback=traceback.format_exc(),
        path=request.url.path,
        method=request.method,
    )

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": {
                "type": "InternalServerError",
                "message": "An unexpected error occurred",
                "path": request.url.path,
            }
        },
    )


def setup_exception_handlers(app: FastAPI) -> None:
    """Set up all exception handlers for the FastAPI application."""
    app.add_exception_handler(EnigmaBaseException, enigma_exception_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(ValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, general_exception_handler)

    logger.info("Exception handlers configured successfully")
