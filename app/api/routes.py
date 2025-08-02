"""
API Routes Configuration

This module defines all API routes for the Project Enigma backend,
including chat endpoints, repository management, and health checks.
"""

import structlog
from fastapi import APIRouter

from app.api.endpoints import chat, health, repositories, workflow

logger = structlog.get_logger()

# Create the main API router
api_router = APIRouter()

# Include endpoint routers with debugging
try:
    logger.info("Loading health endpoints", routes_count=len(health.router.routes))
    api_router.include_router(health.router, prefix="/health", tags=["health"])
    
    logger.info("Loading chat endpoints", routes_count=len(chat.router.routes))
    api_router.include_router(chat.router, prefix="/chat", tags=["chat"])
    
    logger.info("Loading repository endpoints", routes_count=len(repositories.router.routes))
    api_router.include_router(
        repositories.router, prefix="/repositories", tags=["repositories"]
    )
    
    logger.info("Loading workflow endpoints", routes_count=len(workflow.router.routes))
    api_router.include_router(workflow.router, prefix="/workflow", tags=["workflow"])
    
    logger.info("All API routers loaded successfully", total_routes=len(api_router.routes))
    
except Exception as e:
    logger.error("Failed to load API routers", error=str(e))
    raise
