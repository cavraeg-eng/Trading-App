"""Main FastAPI application for the trading bot."""

import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Track start time for uptime calculation
start_time = time.time()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    print("Trading Bot API starting...")
    yield
    # Shutdown
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
    allow_origins=["http://localhost:3002", "http://localhost:3003", "http://localhost:3004", "http://localhost:3005", "http://localhost:3006", "http://localhost:3007", "http://localhost:3008", "http://localhost:3009", "http://localhost:3010", "http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Import and include routers
from trading_bot.api.routes import scanner, signals, sentiment, broker, social, market
from trading_bot.api.routes.backtest_routes import router as backtest_router
from trading_bot.api.routes.paper_trading import router as paper_trading_router

app.include_router(scanner.router)
app.include_router(signals.router)
app.include_router(sentiment.router)
app.include_router(broker.router)
app.include_router(social.router)
app.include_router(market.router)
app.include_router(backtest_router)
app.include_router(paper_trading_router)


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
