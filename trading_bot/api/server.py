"""Main FastAPI application for the trading bot."""

import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from trading_bot.config import get_logger
from trading_bot.persistence.db import PersistenceError, get_default_db_path, init_db
from trading_bot.services.automation_worker import start_worker, stop_worker

# Track start time for uptime calculation
start_time = time.time()
logger = get_logger(__name__)

def get_api_db_path() -> Path:
    return get_default_db_path()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    print("Trading Bot API starting...")
    db_path = get_api_db_path()
    init_db(db_path)
    print(f"SQLite database initialized at {db_path.resolve()}")
    from trading_bot.execution.broker_manager import broker_manager
    from trading_bot.api.routes.paper_trading import restore_paper_trading_state

    try:
        restore_paper_trading_state()
    except PersistenceError as exc:
        logger.warning(
            "Paper trading state restoration skipped; continuing with in-memory defaults",
            error=str(exc),
        )
    await broker_manager.restore_state()
    start_worker()
    yield
    # Shutdown
    await stop_worker()
    print("Trading Bot API shutting down...")


app = FastAPI(
    title="AI Trading Bot API",
    description="FastAPI backend for the AI Trading Bot application",
    version="1.0.0",
    lifespan=lifespan
)

# Configure CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5180", "http://localhost:3002", "http://localhost:3003", "http://localhost:3004", "http://localhost:3005", "http://localhost:3006", "http://localhost:3007", "http://localhost:3008", "http://localhost:3009", "http://localhost:3010", "http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class NoCacheMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response


app.add_middleware(NoCacheMiddleware)

# Import and include routers
from trading_bot.api.routes import scanner, signals, sentiment, broker, social, market, predictions
from trading_bot.api.routes.backtest_routes import router as backtest_router
from trading_bot.api.routes.paper_trading import router as paper_trading_router
from trading_bot.api.routes.copy_trading import router as copy_trading_router
from trading_bot.api.routes.metrics import router as metrics_router
from trading_bot.api.routes.ai_score import router as ai_score_router
from trading_bot.api.routes.alignment import router as alignment_router
from trading_bot.api.routes.alerts import router as alerts_router
from trading_bot.api.routes.datasource_health import router as datasource_health_router
from trading_bot.api.routes.gold_intelligence import router as gold_intelligence_router
from trading_bot.api.routes.opportunities import router as opportunities_router
from trading_bot.api.routes.reporting import router as reporting_router
from trading_bot.api.routes.strategies import router as strategies_router

app.include_router(scanner.router)
app.include_router(signals.router)
app.include_router(sentiment.router)
app.include_router(broker.router)
app.include_router(social.router)
app.include_router(market.router)
app.include_router(backtest_router)
app.include_router(paper_trading_router)
app.include_router(copy_trading_router)
app.include_router(metrics_router)
app.include_router(ai_score_router)
app.include_router(alignment_router)
app.include_router(alerts_router)
app.include_router(datasource_health_router)
app.include_router(gold_intelligence_router)
app.include_router(opportunities_router)
app.include_router(reporting_router)
app.include_router(strategies_router)
app.include_router(predictions.router)


@app.get("/api/health")
async def health():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "version": "1.0.0",
        "uptime": round(time.time() - start_time, 2)
    }


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": "AI Trading Bot API",
        "version": "1.0.0",
        "docs": "/docs"
    }


@app.get("/api/settings")
async def get_app_settings():
    """Get persisted app settings."""
    from trading_bot.persistence import repositories as repo
    return repo.get_all_settings()


@app.post("/api/settings")
async def save_app_settings(body: dict):
    """Save app settings to SQLite."""
    from trading_bot.persistence import repositories as repo
    for key, value in body.items():
        repo.set_setting(key, str(value))
    return {"success": True, "saved_keys": list(body.keys())}
