"""Aggregates all API sub-routers under /api."""
from fastapi import APIRouter

from app.api.routes import (
    features,
    health,
    indices,
    movers,
    prices,
    securities,
    snapshot,
    stats,
)

api_router = APIRouter()
api_router.include_router(health.router,     tags=["health"])
api_router.include_router(securities.router, tags=["securities"])
api_router.include_router(prices.router,     tags=["prices"])
api_router.include_router(features.router,   tags=["features"])
api_router.include_router(snapshot.router,   tags=["snapshot"])
api_router.include_router(indices.router,    tags=["indices"])
api_router.include_router(movers.router,     tags=["movers"])
api_router.include_router(stats.router,      tags=["stats"])