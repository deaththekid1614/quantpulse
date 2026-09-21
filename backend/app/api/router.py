"""Aggregates all API sub-routers under /api."""
from fastapi import APIRouter

from app.api.routes import (
    features,
    fundamentals,
    health,
    indices,
    movers,
    news,
    prices,
    securities,
    snapshot,
    stats,
)

api_router = APIRouter()
api_router.include_router(health.router,       tags=["health"])
api_router.include_router(securities.router,   tags=["securities"])
api_router.include_router(prices.router,       tags=["prices"])
api_router.include_router(features.router,     tags=["features"])
api_router.include_router(snapshot.router,     tags=["snapshot"])
api_router.include_router(stats.router,        tags=["stats"])
api_router.include_router(fundamentals.router, tags=["fundamentals"])
api_router.include_router(news.router,         tags=["news"])
api_router.include_router(indices.router,      tags=["indices"])
api_router.include_router(movers.router,       tags=["movers"])