#!/usr/bin/env python3
"""
Project Enigma Backend - FastAPI Application Entry Point

This is the main entry point for the Project Enigma backend API server.
It sets up the FastAPI application with all necessary middleware, routes,
and configurations for development and production environments.
"""

import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import structlog
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.routes import api_router
from app.core.config import get_settings
from app.core.exceptions import setup_exception_handlers
from app.core.middleware import (
    PerformanceMonitoringMiddleware,
    RateLimitingMiddleware,
    SecurityHeadersMiddleware,
)

def setup_logging() -> None:
    """Configure enhanced structured logging for the application."""
    from app.core.logging import setup_enhanced_logging

    settings = get_settings()

    setup_enhanced_logging(
        log_level=(
            settings.log_level.upper() if hasattr(settings, "log_level") else "INFO"
        ),
        enable_json=False,
        enable_security_sanitization=True,
        enable_alerts=True,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager for startup and shutdown events."""
    # Startup
    setup_logging()
    logger = structlog.get_logger()
    logger.info("Starting Project Enigma Backend API")

    # Ensure required directories exist
    settings = get_settings()
    config_dir = Path("config")
    config_dir.mkdir(exist_ok=True)
    
    # Initialize workflow system
    try:
        from app.workflows.initialization import initialize_workflow_system
        initialize_workflow_system()
        logger.info("Workflow system initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize workflow system: {e}")
        # Don't fail startup, but log the error
    
    yield

    # Shutdown
    logger.info("Shutting down Project Enigma Backend API")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()
    logger = structlog.get_logger()

    app = FastAPI(
        title="Project Enigma API",
        description="AI-powered release documentation automation backend",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs" if settings.environment == "development" else None,
        redoc_url="/redoc" if settings.environment == "development" else None,
    )

    # Configure CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Add custom middleware
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(PerformanceMonitoringMiddleware)
    app.add_middleware(RateLimitingMiddleware, max_requests=100, window_seconds=60)

    # Setup exception handlers
    setup_exception_handlers(app)

    # Include API routes with debugging
    try:
        logger.info("Including API routes", router_routes=len(api_router.routes))
        app.include_router(api_router, prefix="/api")
        logger.info("API routes included successfully")
        
        # Debug: Print all registered routes
        for route in app.routes:
            if hasattr(route, 'path'):
                logger.info("Registered route", path=route.path, methods=getattr(route, 'methods', []))
    except Exception as e:
        logger.error("Failed to include API routes", error=str(e))
        raise

    # Serve static files (React frontend) if build directory exists
    frontend_build_paths = [
        Path("../frontend/dist"),  # Production build
        Path("../frontend/build"),  # Alternative build directory
        Path("static"),  # Fallback static directory
    ]

    frontend_path = None
    for path in frontend_build_paths:
        if path.exists() and path.is_dir():
            frontend_path = path
            break

    if frontend_path:
        app.mount(
            "/", StaticFiles(directory=str(frontend_path), html=True), name="frontend"
        )
        logger.info("Static file serving configured", path=str(frontend_path))
    else:
        logger.warning(
            "No frontend build directory found, static file serving disabled"
        )

    return app


# Create the application instance
app = create_app()


# Health check endpoint
@app.get("/health")
async def health_check():
    """Simple health check endpoint."""
    return {"status": "healthy", "service": "project-enigma-backend"}


# Root endpoint
@app.get("/")
async def root():
    """Root endpoint with API information."""
    return {
        "message": "Project Enigma Backend API",
        "version": "0.1.0",
        "docs": "/docs",
        "health": "/health",
        "api_base": "/api"
    }


# Redirect /api/docs to /docs for convenience
@app.get("/api/docs")
async def redirect_to_docs():
    """Redirect to the main docs page."""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/docs")


if __name__ == "__main__":
    settings = get_settings()
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.environment == "development",
        log_level="info",
    )
