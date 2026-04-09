# API Routes

<cite>
**Referenced Files in This Document**
- [server.py](file://trading_bot/api/server.py)
- [scanner.py](file://trading_bot/api/routes/scanner.py)
- [signals.py](file://trading_bot/api/routes/signals.py)
- [sentiment.py](file://trading_bot/api/routes/sentiment.py)
- [broker.py](file://trading_bot/api/routes/broker.py)
- [social.py](file://trading_bot/api/routes/social.py)
- [market.py](file://trading_bot/api/routes/market.py)
- [backtest_routes.py](file://trading_bot/api/routes/backtest_routes.py)
- [paper_trading.py](file://trading_bot/api/routes/paper_trading.py)
- [models.py](file://trading_bot/api/models.py)
</cite>

## Table of Contents
1. [Introduction](#introduction)
2. [Project Structure](#project-structure)
3. [Core Components](#core-components)
4. [Architecture Overview](#architecture-overview)
5. [Detailed Component Analysis](#detailed-component-analysis)
6. [Dependency Analysis](#dependency-analysis)
7. [Performance Considerations](#performance-considerations)
8. [Troubleshooting Guide](#troubleshooting-guide)
9. [Conclusion](#conclusion)

## Introduction
This document provides a comprehensive overview of the API routes powering the AI Trading Bot backend. It explains the routing structure, endpoint categories, request/response models, and operational behavior across modules such as market data, technical analysis, scanning, signals, sentiment, broker connectivity, social features, backtesting, and paper trading. The goal is to enable developers and integrators to understand how to interact with the API and leverage its capabilities effectively.

## Project Structure
The API is implemented as a FastAPI application with modular routers grouped by functional domain. Each router defines endpoints under a consistent `/api/<module>` prefix, enabling clear separation of concerns and scalable maintenance.

```mermaid
graph TB
Server["FastAPI Server<br/>server.py"] --> RouterScanner["Scanner Router<br/>scanner.py"]
Server --> RouterSignals["Signals Router<br/>signals.py"]
Server --> RouterSentiment["Sentiment Router<br/>sentiment.py"]
Server --> RouterBroker["Broker Router<br/>broker.py"]
Server --> RouterSocial["Social Router<br/>social.py"]
Server --> RouterMarket["Market Router<br/>market.py"]
Server --> RouterBacktest["Backtest Router<br/>backtest_routes.py"]
Server --> RouterPaper["Paper Trading Router<br/>paper_trading.py"]
RouterScanner --> Models["Models<br/>models.py"]
RouterSignals --> Models
RouterSentiment --> Models
RouterBroker --> Models
RouterSocial --> Models
RouterMarket --> Models
RouterBacktest --> Models
RouterPaper --> Models
```

**Diagram sources**
- [server.py:55-66](file://trading_bot/api/server.py#L55-L66)
- [scanner.py:19](file://trading_bot/api/routes/scanner.py#L19)
- [signals.py:17](file://trading_bot/api/routes/signals.py#L17)
- [sentiment.py](file://trading_bot/api/routes/sentiment.py)
- [broker.py:15](file://trading_bot/api/routes/broker.py#L15)
- [social.py:12](file://trading_bot/api/routes/social.py#L12)
- [market.py:18](file://trading_bot/api/routes/market.py#L18)
- [backtest_routes.py:23](file://trading_bot/api/routes/backtest_routes.py#L23)
- [paper_trading.py:7](file://trading_bot/api/routes/paper_trading.py#L7)
- [models.py:1-142](file://trading_bot/api/models.py#L1-L142)

**Section sources**
- [server.py:55-66](file://trading_bot/api/server.py#L55-L66)
- [models.py:1-142](file://trading_bot/api/models.py#L1-L142)

## Core Components
- Scanner: Evaluates market conditions across multiple instruments and timeframes using technical indicators to produce ranked matches and trade signals.
- Signals: Generates persistent trading signals with entry zones, stop-loss, and take-profit targets, including lifecycle management and status computation.
- Market: Provides OHLCV data retrieval (real via yfinance with fallback to synthetic), technical analysis, and multi-timeframe evaluations.
- Sentiment: Aggregates and exposes market sentiment metrics for symbols and trending movements.
- Broker: Manages broker connections (CCXT/OANDA/Alpaca), order placement, positions, balances, and order history.
- Social: Offers leaderboard, social feed, user profiles, and trending symbol insights.
- Backtest: Executes historical strategy simulations with performance metrics and equity curves.
- Paper Trading: Simulates trading actions and maintains a paper account state for testing.

**Section sources**
- [scanner.py:19](file://trading_bot/api/routes/scanner.py#L19)
- [signals.py:17](file://trading_bot/api/routes/signals.py#L17)
- [market.py:18](file://trading_bot/api/routes/market.py#L18)
- [sentiment.py](file://trading_bot/api/routes/sentiment.py)
- [broker.py:15](file://trading_bot/api/routes/broker.py#L15)
- [social.py:12](file://trading_bot/api/routes/social.py#L12)
- [backtest_routes.py:23](file://trading_bot/api/routes/backtest_routes.py#L23)
- [paper_trading.py:7](file://trading_bot/api/routes/paper_trading.py#L7)

## Architecture Overview
The API follows a layered architecture:
- Application Layer: FastAPI server initializes middleware and includes routers.
- Domain Routers: Each router encapsulates endpoints for a specific domain.
- Shared Models: Pydantic models define request/response schemas used across routers.
- External Integrations: Market data via yfinance, broker integrations via broker manager, sentiment via analyzer.

```mermaid
graph TB
subgraph "Application Layer"
S["FastAPI Server<br/>server.py"]
S --> M1["CORS Middleware"]
S --> M2["NoCache Middleware"]
S --> Routers["Routers Included"]
end
subgraph "Domain Routers"
RS["scanner.py"]
RSi["signals.py"]
RSe["sentiment.py"]
RB["broker.py"]
RSoc["social.py"]
RM["market.py"]
RBT["backtest_routes.py"]
RP["paper_trading.py"]
end
subgraph "Shared Models"
M["models.py"]
end
S --> RS
S --> RSi
S --> RSe
S --> RB
S --> RSoc
S --> RM
S --> RBT
S --> RP
RS --> M
RSi --> M
RSe --> M
RB --> M
RSoc --> M
RM --> M
RBT --> M
RP --> M
```

**Diagram sources**
- [server.py:25-66](file://trading_bot/api/server.py#L25-L66)
- [models.py:1-142](file://trading_bot/api/models.py#L1-L142)

## Detailed Component Analysis

### Scanner Routes
Endpoints:
- GET /api/scanner/presets: Returns predefined scanning configurations.
- POST /api/scanner/scan: Runs a scan with a given configuration, returning matched symbols with scores and indicator values.
- POST /api/scanner/save: Saves a scanner configuration.

Processing logic:
- Parallel evaluation of instruments using ThreadPoolExecutor.
- Indicator calculations (RSI, MACD, EMA, Bollinger Bands, ATR, Volume) with robustness checks.
- Condition evaluation supports operators (> , < , >= , <= , = , between , crosses_above , crosses_below ).
- Scoring computed as proportion of matched conditions under AND/OR logic.
- Signal determination based on RSI thresholds.

```mermaid
sequenceDiagram
participant Client as "Client"
participant Scanner as "Scanner Router"
participant Market as "Market Functions"
participant Pool as "ThreadPoolExecutor"
Client->>Scanner : POST /api/scanner/scan (ScannerConfig)
Scanner->>Pool : submit(evaluate_single_pair(symbol, conditions, logic))
loop For each symbol
Pool->>Market : fetch_data_yf(symbol, timeframe)
Market-->>Pool : DataFrame
Pool->>Market : calculate_* (RSI, MACD, EMA, BB, ATR)
Market-->>Pool : Indicator values
Pool->>Scanner : Evaluation result
end
Scanner-->>Client : {results, total_scanned, total_matches}
```

**Diagram sources**
- [scanner.py:317-352](file://trading_bot/api/routes/scanner.py#L317-L352)
- [scanner.py:102-315](file://trading_bot/api/routes/scanner.py#L102-L315)
- [market.py:206-233](file://trading_bot/api/routes/market.py#L206-L233)

**Section sources**
- [scanner.py:45-99](file://trading_bot/api/routes/scanner.py#L45-L99)
- [scanner.py:317-352](file://trading_bot/api/routes/scanner.py#L317-L352)

### Signals Routes
Endpoints:
- GET /api/signals/current: Returns current signals for selected symbols with indicator breakdowns.
- GET /api/signals/breakdown/{symbol}: Returns a persistent signal with entry zones, stop-loss, take-profit levels, and status.
- GET /api/signals/history: Returns historical signal entries.
- POST /api/signals/reset/{symbol}: Resets a signal for testing.

Lifecycle and status computation:
- Persistent signal storage keyed by symbol with lifecycle tracking.
- Status computed based on age, price proximity to entry zone, and stop-loss breaches.
- Cooldown and expiration windows enforced.
- Indicator contributions generated with weights and directional alignment.

```mermaid
flowchart TD
Start(["GET /api/signals/breakdown/{symbol}"]) --> CheckActive["Check existing active signal"]
CheckActive --> Exists{"Exists and not resolved?"}
Exists --> |Yes| Recompute["Recompute status and TP/SL checks"]
Recompute --> Resolved{"Resolved?"}
Resolved --> |Yes| Cooldown["Apply cooldown or expire"]
Cooldown --> Generate["Generate new signal"]
Resolved --> |No| ReturnExisting["Return existing signal"]
Exists --> |No| CooldownCheck["Check cooldown"]
CooldownCheck --> OnCooldown{"In cooldown?"}
OnCooldown --> |Yes| Hold["Return HOLD placeholder"]
OnCooldown --> |No| Generate
Generate --> Persist["Persist signal"]
Persist --> ReturnNew["Return new signal"]
ReturnExisting --> End(["Response"])
ReturnNew --> End
Hold --> End
```

**Diagram sources**
- [signals.py:158-337](file://trading_bot/api/routes/signals.py#L158-L337)
- [signals.py:340-382](file://trading_bot/api/routes/signals.py#L340-L382)

**Section sources**
- [signals.py:461-554](file://trading_bot/api/routes/signals.py#L461-L554)
- [signals.py:158-337](file://trading_bot/api/routes/signals.py#L158-L337)

### Market Routes
Endpoints:
- GET /api/market/analysis/{symbol}: Comprehensive technical analysis with entry range, stop-loss, take-profit levels, and multi-timeframe alignment.
- GET /api/market/recommendations: Recommendations across multiple symbols with Sharpe and volatility metrics.
- GET /api/market/candles/{symbol}: OHLCV candles with caching and fallback to synthetic data.

Key features:
- Real data via yfinance with fallback to synthetic candles.
- Caching with TTL per timeframe.
- Indicator computations (RSI, MACD, EMA, Bollinger Bands, ATR).
- Multi-timeframe analysis and volatility assessment.

```mermaid
sequenceDiagram
participant Client as "Client"
participant Market as "Market Router"
participant YF as "yfinance"
participant Cache as "In-memory Cache"
Client->>Market : GET /api/market/analysis/{symbol}?timeframe&trade_style
Market->>Cache : get_cached_data(key, timeframe)
alt Cache hit
Cache-->>Market : cached analysis
Market-->>Client : analysis
else Cache miss
Market->>YF : fetch_data_yf(symbol, timeframe)
alt Real data available
YF-->>Market : DataFrame
Market->>Market : calculate indicators
Market->>Cache : set_cached_data
Market-->>Client : analysis
else Fallback
Market-->>Client : mock analysis
end
end
```

**Diagram sources**
- [market.py:536-577](file://trading_bot/api/routes/market.py#L536-L577)
- [market.py:206-233](file://trading_bot/api/routes/market.py#L206-L233)
- [market.py:117-133](file://trading_bot/api/routes/market.py#L117-L133)

**Section sources**
- [market.py:536-627](file://trading_bot/api/routes/market.py#L536-L627)
- [market.py:682-742](file://trading_bot/api/routes/market.py#L682-L742)

### Sentiment Routes
Endpoints:
- GET /api/sentiment/overview: Overall sentiment overview across symbols.
- GET /api/sentiment/symbol/{symbol}: Detailed sentiment data for a symbol.
- GET /api/sentiment/trending: Trending sentiment changes filtered by label.

Implementation:
- Uses a sentiment analyzer to compute scores and trends.
- Returns last_updated timestamps derived from full sentiment data.

**Section sources**
- [sentiment.py:15-58](file://trading_bot/api/routes/sentiment.py#L15-L58)

### Broker Routes
Endpoints:
- GET /api/broker/list: Available brokers.
- POST /api/broker/connect/{broker_id}: Connect with credentials (supports CCXT/OANDA/Alpaca).
- POST /api/broker/disconnect/{broker_id}: Disconnect from a broker.
- GET /api/broker/status/{broker_id}: Connection status and metadata.
- GET /api/broker/active: Currently active broker.
- POST /api/broker/active/{broker_id}: Set active broker.
- POST /api/broker/order: Place an order.
- GET /api/broker/positions: Current positions (filtered by broker/symbol).
- GET /api/broker/orders: Order history (mocked).
- GET /api/broker/balance/{broker_id}: Account balance and margin.
- DELETE /api/broker/order/{broker_id}/{order_id}: Cancel an order.

Behavior:
- Validates broker existence and connection state.
- Maps order sides/types to internal enums.
- Returns mock data when live data is unavailable.

**Section sources**
- [broker.py:35-160](file://trading_bot/api/routes/broker.py#L35-L160)
- [broker.py:212-372](file://trading_bot/api/routes/broker.py#L212-L372)

### Social Routes
Endpoints:
- GET /api/social/leaderboard: Trading leaderboard with performance metrics.
- GET /api/social/feed: Social trading feed with signal posts.
- POST /api/social/share: Share a signal to the feed.
- POST /api/social/like/{post_id}: Like a post.
- GET /api/social/user/{username}: User profile information.
- GET /api/social/trending-symbols: Trending symbols by mentions and sentiment.

Implementation:
- Mock data generation for leaderboard, feed, and user stats.
- Timestamps randomized within configurable bounds.

**Section sources**
- [social.py:49-226](file://trading_bot/api/routes/social.py#L49-L226)

### Backtest Routes
Endpoints:
- POST /api/backtest/run: Execute a backtest over a date range with performance metrics.

Processing:
- Downloads historical data via yfinance.
- Computes indicators per bar and generates signals.
- Simulates trades with position sizing based on risk percent and ATR.
- Calculates metrics: total return, Sharpe ratio, max drawdown, win rate, profit factor.
- Builds equity curve for visualization.

```mermaid
flowchart TD
Start(["POST /api/backtest/run"]) --> Fetch["Download historical data"]
Fetch --> Bars{"Enough bars?"}
Bars --> |No| Error["Return error"]
Bars --> |Yes| Loop["Iterate bars"]
Loop --> Indicators["Compute RSI, MACD, EMA, BB, ATR"]
Indicators --> Signal["Determine signal (>=3 bullish/bearish counts)"]
Signal --> Trade{"Open/Close position?"}
Trade --> OpenLong["Open long if none"]
Trade --> OpenShort["Open short if none"]
Trade --> ClosePos["Close opposite position if exists"]
OpenLong --> Record["Record trade and update equity"]
OpenShort --> Record
ClosePos --> Record
Record --> Next["Next bar"]
Next --> Loop
Loop --> Finalize["Close remaining position at end"]
Finalize --> Metrics["Compute metrics (return, Sharpe, drawdown, win rate, profit factor)"]
Metrics --> Curve["Build equity curve"]
Curve --> End(["Return results"])
```

**Diagram sources**
- [backtest_routes.py:64-284](file://trading_bot/api/routes/backtest_routes.py#L64-L284)

**Section sources**
- [backtest_routes.py:64-284](file://trading_bot/api/routes/backtest_routes.py#L64-L284)

### Paper Trading Routes
Endpoints:
- POST /api/trading/paper-order: Place a simulated paper trade.
- GET /api/trading/paper-positions: Current paper positions.
- GET /api/trading/paper-account: Paper account summary.
- DELETE /api/trading/paper-reset: Reset paper account to initial state.

Behavior:
- Validates order parameters and sufficient balance.
- Maintains in-memory state for positions and trades history.
- Returns standardized responses for paper execution.

**Section sources**
- [paper_trading.py:32-113](file://trading_bot/api/routes/paper_trading.py#L32-L113)

## Dependency Analysis
- Router-to-router dependencies:
  - Scanner depends on Market functions for indicator calculations.
  - Signals depends on Market for live price caching and base prices.
  - Backtest reuses Market indicator computations for signal logic.
- Shared models:
  - All routers import and use Pydantic models for request/response validation and serialization.
- External integrations:
  - Market relies on yfinance for OHLCV data.
  - Broker integrates with broker manager for connectivity and order execution.
  - Sentiment integrates with analyzer for sentiment metrics.

```mermaid
graph TB
Scanner["scanner.py"] --> Market["market.py"]
Signals["signals.py"] --> Market
Backtest["backtest_routes.py"] --> Market
Broker["broker.py"] --> Models["models.py"]
Social["social.py"] --> Models
Market --> Models
Scanner --> Models
Signals --> Models
Backtest --> Models
Paper["paper_trading.py"] --> Models
```

**Diagram sources**
- [scanner.py:11-14](file://trading_bot/api/routes/scanner.py#L11-L14)
- [signals.py:12](file://trading_bot/api/routes/signals.py#L12)
- [backtest_routes.py:11-18](file://trading_bot/api/routes/backtest_routes.py#L11-L18)
- [models.py:1-142](file://trading_bot/api/models.py#L1-L142)

**Section sources**
- [scanner.py:11-14](file://trading_bot/api/routes/scanner.py#L11-L14)
- [signals.py:12](file://trading_bot/api/routes/signals.py#L12)
- [backtest_routes.py:11-18](file://trading_bot/api/routes/backtest_routes.py#L11-L18)
- [models.py:1-142](file://trading_bot/api/models.py#L1-L142)

## Performance Considerations
- Caching:
  - Market router caches analysis and recommendations with TTL to reduce yfinance load.
  - Signals router caches live prices to minimize external calls.
- Parallelization:
  - Scanner uses a thread pool to evaluate multiple symbols concurrently.
- Data fallback:
  - Market and backtest provide synthetic candles when real data is unavailable, ensuring responsiveness.
- Precision and rounding:
  - Price and indicator values are rounded appropriately to instrument precision, preventing floating-point inconsistencies.

[No sources needed since this section provides general guidance]

## Troubleshooting Guide
Common issues and resolutions:
- Health check:
  - Endpoint: GET /api/health
  - Purpose: Verify service availability and uptime.
  - Response includes status, version, and uptime in seconds.
- CORS errors:
  - Ensure client origin is included in allowed origins in server configuration.
- Rate limiting and caching:
  - Market endpoints cache results; wait for TTL to refresh.
- Broker connectivity:
  - Use GET /api/broker/status/{broker_id} to confirm connection and latency.
  - Validate credentials for CCXT/OANDA/Alpaca endpoints.
- Scanner timeouts:
  - Increase worker count or reduce symbol list; ensure network access to yfinance.
- Signals cooldown:
  - After TP/SL resolution, a cooldown period prevents immediate re-entry; wait for cooldown to expire.

**Section sources**
- [server.py:69-76](file://trading_bot/api/server.py#L69-L76)
- [market.py:117-133](file://trading_bot/api/routes/market.py#L117-L133)
- [signals.py:231-263](file://trading_bot/api/routes/signals.py#L231-L263)
- [broker.py:116-134](file://trading_bot/api/routes/broker.py#L116-L134)

## Conclusion
The API provides a cohesive set of endpoints spanning market data, technical analysis, scanning, signals, sentiment, broker management, social features, backtesting, and paper trading. Its modular design, robust caching, and fallback mechanisms ensure reliability and scalability. Developers can integrate these endpoints to build powerful trading applications, dashboards, and automation systems around the AI Trading Bot.