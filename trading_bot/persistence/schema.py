"""SQLite schema for platform state persistence."""

SCHEMA_SQL = """
-- Key-value settings store
CREATE TABLE IF NOT EXISTS app_settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Saved scanner configurations
CREATE TABLE IF NOT EXISTS saved_scanners (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL,
    config_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Paper trading orders
CREATE TABLE IF NOT EXISTS paper_orders (
    trade_id    TEXT PRIMARY KEY,
    symbol      TEXT NOT NULL,
    side        TEXT NOT NULL,
    quantity    REAL NOT NULL,
    entry_price REAL NOT NULL,
    stop_loss   REAL,
    take_profit_1 REAL,
    take_profit_2 REAL,
    take_profit_3 REAL,
    status      TEXT NOT NULL DEFAULT 'filled',
    pnl         REAL NOT NULL DEFAULT 0.0,
    risk_percent REAL,
    trade_style TEXT,
    confidence  REAL,
    opened_at   TEXT NOT NULL DEFAULT (datetime('now')),
    closed_at   TEXT
);

-- Paper trading account state
CREATE TABLE IF NOT EXISTS paper_account (
    id              INTEGER PRIMARY KEY CHECK (id = 1),
    balance         REAL NOT NULL DEFAULT 10000.0,
    equity          REAL NOT NULL DEFAULT 10000.0,
    initial_balance REAL NOT NULL DEFAULT 10000.0,
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
INSERT OR IGNORE INTO paper_account (id) VALUES (1);

-- Copy trading settings
CREATE TABLE IF NOT EXISTS copy_settings (
    id                          INTEGER PRIMARY KEY CHECK (id = 1),
    enabled                     INTEGER NOT NULL DEFAULT 0,
    max_position_size_lots      REAL NOT NULL DEFAULT 10.0,
    max_risk_percent            REAL NOT NULL DEFAULT 3.0,
    max_concurrent_positions    INTEGER NOT NULL DEFAULT 5,
    lot_size_scale              REAL NOT NULL DEFAULT 1.0,
    auto_close_on_signal_expire INTEGER NOT NULL DEFAULT 1,
    allowed_symbols_json        TEXT NOT NULL DEFAULT '["XAU/USD","EUR/USD","GBP/USD","BTC/USD","ETH/USD"]',
    min_confidence              INTEGER NOT NULL DEFAULT 60,
    updated_at                  TEXT NOT NULL DEFAULT (datetime('now'))
);
INSERT OR IGNORE INTO copy_settings (id) VALUES (1);

-- Copy trading positions
CREATE TABLE IF NOT EXISTS copy_trades (
    copy_trade_id TEXT PRIMARY KEY,
    symbol        TEXT NOT NULL,
    direction     TEXT NOT NULL,
    quantity      REAL NOT NULL,
    entry_price   REAL NOT NULL,
    current_price REAL NOT NULL,
    stop_loss     REAL NOT NULL,
    take_profit1  REAL NOT NULL,
    take_profit2  REAL NOT NULL,
    take_profit3  REAL NOT NULL,
    confidence    INTEGER NOT NULL,
    risk_percent  REAL NOT NULL,
    status        TEXT NOT NULL DEFAULT 'open',
    unrealized_pnl REAL NOT NULL DEFAULT 0.0,
    realized_pnl  REAL NOT NULL DEFAULT 0.0,
    trade_style   TEXT NOT NULL DEFAULT 'swing',
    timeframe     TEXT NOT NULL DEFAULT '1h',
    signal_source TEXT NOT NULL DEFAULT 'AI',
    created_at    REAL NOT NULL,
    closed_at     REAL
);

-- Signal predictions (issued signals for tracking)
CREATE TABLE IF NOT EXISTS signal_predictions (
    signal_id   TEXT PRIMARY KEY,
    symbol      TEXT NOT NULL,
    direction   TEXT NOT NULL,
    confidence  INTEGER NOT NULL,
    entry_min   REAL NOT NULL,
    entry_max   REAL NOT NULL,
    stop_loss   REAL NOT NULL,
    take_profit1 REAL NOT NULL,
    take_profit2 REAL NOT NULL,
    take_profit3 REAL NOT NULL,
    timeframe   TEXT NOT NULL,
    trade_style TEXT,
    source      TEXT NOT NULL DEFAULT 'heuristic',
    price_source TEXT,
    created_at  REAL NOT NULL
);

-- Signal outcomes (resolved predictions)
CREATE TABLE IF NOT EXISTS signal_outcomes (
    signal_id       TEXT PRIMARY KEY REFERENCES signal_predictions(signal_id),
    resolved_reason TEXT NOT NULL,
    resolved_at     REAL NOT NULL,
    exit_price      REAL,
    pnl_pips        REAL,
    direction_correct INTEGER
);

-- Model registry
CREATE TABLE IF NOT EXISTS model_registry (
    model_id    TEXT PRIMARY KEY,
    model_type  TEXT NOT NULL,
    file_path   TEXT NOT NULL,
    metadata_json TEXT,
    is_active   INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Service health snapshots
CREATE TABLE IF NOT EXISTS service_health_snapshots (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    service    TEXT NOT NULL,
    status     TEXT NOT NULL,
    detail     TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""
