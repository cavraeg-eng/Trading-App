"""Scanner routes for the trading bot API."""

import json

from fastapi import APIRouter, HTTPException

from trading_bot.api.models import ScannerConfig
from trading_bot.persistence import alerts as alert_repo
from trading_bot.persistence import scanners as scanner_repo
from trading_bot.services.scanner_engine import (
    metadata_payload,
)
from trading_bot.services.scanner_run import (
    DEFAULT_PAIRS,
    ScannerConfigError,
    execute_scanner_run,
    flatten_conditions,
    group_descriptors,
)

router = APIRouter(prefix="/api/scanner", tags=["scanner"])

METALS = {"XAU/USD", "XAG/USD", "XPT/USD", "COPPER/USD"}
CRYPTO = {
    "BTC/USD",
    "ETH/USD",
    "SOL/USD",
    "XRP/USD",
    "BNB/USD",
    "ADA/USD",
    "DOGE/USD",
    "LTC/USD",
    "LINK/USD",
    "DOT/USD",
    "AVAX/USD",
    "MATIC/USD",
}
INDICES = {"US30", "US500", "US100", "UK100", "DE40", "FR40", "JP225", "AU200"}


def _preset_markets(pairs: list[str]) -> list[str]:
    markets: list[str] = []
    if any(pair in METALS for pair in pairs):
        markets.append("metals")
    if any(pair in CRYPTO for pair in pairs):
        markets.append("crypto")
    if any(pair in INDICES for pair in pairs):
        markets.append("indices")
    if any("/" in pair and pair not in METALS and pair not in CRYPTO for pair in pairs):
        markets.append("forex")
    return markets or ["forex"]


def _risk_gate_copy(risk: str) -> list[str]:
    if risk == "low":
        return ["confidence >= 55%", "fresh market data", "risk gate not high"]
    if risk == "high":
        return ["confidence >= 70%", "confirm stop distance", "avoid stale or fallback data"]
    return ["confidence >= 60%", "risk/reward >= 1.20R", "data source healthy"]


def _enrich_presets(presets: list[dict]) -> list[dict]:
    for preset in presets:
        pairs = preset.get("recommended_pairs", [])
        risk = preset.get("risk", "medium")
        markets = _preset_markets(pairs)
        preset["markets"] = markets
        preset["risk_gates"] = _risk_gate_copy(risk)
        preset["action_prompt"] = (
            "Treat matches as execution candidates after setup levels and risk gate pass."
            if risk != "high"
            else "Treat matches as review-first setups until volatility and stop distance are confirmed."
        )
        preset["market_scope"] = ", ".join(item.title() for item in markets)
    return presets


@router.get("/presets")
async def get_presets():
    """Get built-in scanner presets."""
    presets = [
        {
            "id": "apex_current",
            "name": "Apex Current",
            "description": "Tracks mature trend continuation using EMA reclaim, RSI strength, and directional confirmation",
            "icon": "trending-up",
            "category": "Trend follower",
            "best_for": "4H swing continuation when price reclaims the EMA with RSI confirmation.",
            "cadence": "4H",
            "risk": "medium",
            "popularity": "Core",
            "accent": "emerald",
            "logic": "AND",
            "groups": [
                {
                    "id": "trend-core",
                    "name": "Trend confirmation",
                    "logic": "AND",
                    "conditions": [
                        {"indicator": "Price", "operator": "crosses_above", "compare_indicator": "EMA", "value": 0},
                        {"indicator": "RSI", "operator": ">", "value": 50},
                    ],
                }
            ],
            "trade_style": "swing",
            "timeframe": "4h",
            "recommended_pairs": ["EUR/USD", "GBP/USD", "USD/JPY", "XAU/USD", "XAG/USD", "US500"],
            "tags": ["trend", "breakout", "swing"],
            "conditions": [
                {"indicator": "Price", "operator": "crosses_above", "compare_indicator": "EMA", "value": 0},
                {"indicator": "RSI", "operator": ">", "value": 50}
            ]
        },
        {
            "id": "viper_entry",
            "name": "Viper Entry",
            "description": "Hunts precision pullback entries where oversold momentum flips back into confirmation",
            "icon": "zap",
            "category": "Precision entry",
            "best_for": "Fast mean-reversion entries after oversold momentum flips back bullish.",
            "cadence": "1H",
            "risk": "medium",
            "popularity": "Popular",
            "accent": "amber",
            "logic": "AND",
            "groups": [
                {
                    "id": "reversal-entry",
                    "name": "Reversal entry",
                    "logic": "AND",
                    "conditions": [
                        {"indicator": "RSI", "operator": "<", "value": 30},
                        {"indicator": "MACD", "operator": "crosses_above", "compare_indicator": "MACD Signal", "value": 0},
                    ],
                }
            ],
            "trade_style": "swing",
            "timeframe": "1h",
            "recommended_pairs": ["EUR/USD", "GBP/USD", "AUD/USD", "XAU/USD", "BTC/USD"],
            "tags": ["momentum", "reversal"],
            "conditions": [
                {"indicator": "RSI", "operator": "<", "value": 30},
                {"indicator": "MACD", "operator": "crosses_above", "compare_indicator": "MACD Signal", "value": 0}
            ]
        },
        {
            "id": "nova_breaker",
            "name": "Nova Breaker",
            "description": "Detects high-energy breakouts when price expands beyond volatility bands",
            "icon": "activity",
            "category": "Breakout hunter",
            "best_for": "Expansion moves when price pushes outside the upper band with elevated ATR.",
            "cadence": "1H",
            "risk": "high",
            "popularity": "Aggressive",
            "accent": "rose",
            "logic": "AND",
            "trade_style": "swing",
            "timeframe": "1h",
            "recommended_pairs": ["XAU/USD", "XAG/USD", "BTC/USD", "ETH/USD", "US500", "GBP/JPY", "EUR/JPY"],
            "tags": ["volatility", "breakout"],
            "conditions": [
                {"indicator": "Price", "operator": "crosses_above", "compare_indicator": "BB Upper", "value": 0},
                {"indicator": "ATR", "operator": ">", "value": 1.5}
            ]
        },
        {
            "id": "pulse_surge",
            "name": "Pulse Surge",
            "description": "Catches unusual participation bursts before short-term momentum accelerates",
            "icon": "bar-chart",
            "category": "Flow scanner",
            "best_for": "Short-term alerts when activity surges above the recent 20-period baseline.",
            "cadence": "15M",
            "risk": "medium",
            "popularity": "Intraday",
            "accent": "sky",
            "logic": "AND",
            "trade_style": "scalp",
            "timeframe": "15m",
            "recommended_pairs": ["EUR/USD", "GBP/USD", "USD/JPY", "XAU/USD", "BTC/USD"],
            "tags": ["volume", "breakout"],
            "conditions": [
                {"indicator": "Volume", "operator": ">", "value": 2.0}
            ]
        },
        {
            "id": "gravity_snap",
            "name": "Gravity Snap",
            "description": "Finds stretched markets that may snap back after deep oversold pressure",
            "icon": "refresh-cw",
            "category": "Mean reversion",
            "best_for": "Pullbacks near the lower Bollinger zone where RSI is deeply oversold.",
            "cadence": "1H",
            "risk": "low",
            "popularity": "Defensive",
            "accent": "violet",
            "logic": "AND",
            "trade_style": "swing",
            "timeframe": "1h",
            "recommended_pairs": ["EUR/USD", "AUD/USD", "USD/CAD", "NZD/USD", "XAU/USD"],
            "tags": ["mean reversion", "oversold"],
            "conditions": [
                {"indicator": "RSI", "operator": "<", "value": 25},
                {"indicator": "BB", "operator": "<", "value": -1}
            ]
        },
        {
            "id": "sweep_forge",
            "name": "Sweep Forge",
            "description": "Looks for stretched moves with volume confirmation after likely liquidity sweeps",
            "icon": "target",
            "category": "Liquidity hunter",
            "best_for": "Scalp setups where price tags an extreme and participation expands.",
            "cadence": "5M",
            "risk": "high",
            "popularity": "Fast",
            "accent": "amber",
            "logic": "AND",
            "trade_style": "scalp",
            "timeframe": "5m",
            "recommended_pairs": ["EUR/USD", "GBP/USD", "USD/JPY", "XAU/USD"],
            "tags": ["liquidity", "scalp", "volume"],
            "conditions": [
                {"indicator": "RSI", "operator": "<", "value": 35},
                {"indicator": "Volume", "operator": ">", "value": 1.4},
                {"indicator": "BB", "operator": "<=", "value": -0.8}
            ]
        },
        {
            "id": "atlas_pulse",
            "name": "Atlas Pulse",
            "description": "Screens larger-market continuation with slower trend and volume agreement",
            "icon": "shield",
            "category": "Macro swing",
            "best_for": "Cleaner swing scans on majors, gold, indices, and crypto using slower confirmation.",
            "cadence": "1D",
            "risk": "low",
            "popularity": "Stable",
            "accent": "emerald",
            "logic": "AND",
            "trade_style": "swing",
            "timeframe": "1d",
            "recommended_pairs": ["EUR/USD", "USD/JPY", "XAU/USD", "XAG/USD", "BTC/USD", "ETH/USD", "US500"],
            "tags": ["macro", "trend", "confirmation"],
            "conditions": [
                {"indicator": "Price", "operator": ">", "compare_indicator": "EMA", "value": 0},
                {"indicator": "MACD Histogram", "operator": ">", "value": 0},
                {"indicator": "Volume", "operator": ">", "value": 1.0}
            ]
        },
        {
            "id": "aurum_edge",
            "name": "Aurum Edge",
            "description": "Metals scalping scanner for fast gold and silver extremes with participation bursts",
            "icon": "sparkles",
            "category": "Metals scalper",
            "best_for": "Gold, silver, and platinum 5-minute scalp ideas near volatility extremes.",
            "cadence": "5M",
            "risk": "high",
            "popularity": "Metals",
            "accent": "amber",
            "logic": "AND",
            "trade_style": "scalp",
            "timeframe": "5m",
            "recommended_pairs": ["XAU/USD", "XAG/USD", "XPT/USD"],
            "tags": ["metals", "gold", "scalp", "volatility"],
            "conditions": [
                {"indicator": "RSI", "operator": "between", "value": 20, "value2": 38},
                {"indicator": "BB", "operator": "<=", "value": -0.7},
                {"indicator": "Volume", "operator": ">", "value": 1.2}
            ]
        },
        {
            "id": "volt_raider",
            "name": "Volt Raider",
            "description": "Crypto volatility scanner for fast expansions in BTC and high-beta markets",
            "icon": "bot",
            "category": "Crypto volatility",
            "best_for": "Crypto continuation or reversal watchlists during elevated volume and volatility.",
            "cadence": "15M",
            "risk": "high",
            "popularity": "Crypto",
            "accent": "violet",
            "logic": "AND",
            "trade_style": "scalp",
            "timeframe": "15m",
            "recommended_pairs": ["BTC/USD", "ETH/USD", "SOL/USD", "AVAX/USD"],
            "tags": ["crypto", "momentum", "volatility"],
            "conditions": [
                {"indicator": "ATR", "operator": ">", "value": 1.0},
                {"indicator": "Volume", "operator": ">", "value": 1.3},
                {"indicator": "MACD Histogram", "operator": ">", "value": 0}
            ]
        },
    ]
    return {"presets": _enrich_presets(presets)}


@router.get("/metadata")
async def get_scanner_metadata():
    return metadata_payload(["major", "minor", "exotic", "crypto", "commodity", "index"])


@router.post("/scan")
async def run_scan(config: ScannerConfig):
    """Run a scan with the given configuration via the scanner run seam."""
    try:
        scan_run = await execute_scanner_run(config)
        return {
            "results": scan_run.results,
            "total_scanned": scan_run.total_scanned,
            "total_matches": scan_run.total_matches,
            "warnings": scan_run.warnings,
            "request_id": scan_run.request_id,
            "meta": {
                "timeframe": scan_run.timeframe,
                "trade_style": scan_run.trade_style,
                "logic": scan_run.logic,
                "groups": scan_run.groups,
                "scan": scan_run.scan,
            },
        }
    except ScannerConfigError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/saved")
async def get_saved_scanners():
    return {"saved": scanner_repo.get_saved_scanners()}


@router.post("/save")
async def save_scanner(config: ScannerConfig):
    """Save a scanner configuration."""
    scanner_payload = config.model_dump() if hasattr(config, "model_dump") else config.dict()
    scanner_id = scanner_repo.save_scanner(config.name, scanner_payload)
    return {"status": "saved", "name": config.name, "id": scanner_id}


@router.put("/saved/{scanner_id}")
async def update_saved_scanner(scanner_id: int, config: ScannerConfig):
    scanner_payload = config.model_dump() if hasattr(config, "model_dump") else config.dict()
    updated = scanner_repo.update_scanner(scanner_id, config.name, scanner_payload)
    if not updated:
        raise HTTPException(status_code=404, detail="Saved scanner not found")
    return {"status": "updated", "id": scanner_id, "name": config.name}


@router.delete("/saved/{scanner_id}")
async def delete_saved_scanner(scanner_id: int):
    deleted = scanner_repo.delete_scanner(scanner_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Saved scanner not found")
    return {"status": "deleted", "id": scanner_id}


@router.post("/alert")
async def create_scanner_alert(config: ScannerConfig):
    conditions = flatten_conditions(config)
    if not conditions:
        raise HTTPException(status_code=400, detail="Scanner alert requires at least one condition")
    symbol_scope = ", ".join((config.pairs or DEFAULT_PAIRS)[:6])
    alert_id = alert_repo.create_alert(
        symbol=(config.pairs or ["SCAN"])[0],
        alert_type="SCANNER_MATCH",
        title=f"Scanner alert armed: {config.name}",
        message=(
            f"{config.name} will monitor {symbol_scope}"
            + ("…" if len(config.pairs or DEFAULT_PAIRS) > 6 else "")
            + f" on {config.timeframe} / {config.trade_style}."
        ),
        severity="info",
        data=json.dumps(
            {
                "scanner_name": config.name,
                "logic": config.logic,
                "timeframe": config.timeframe,
                "trade_style": config.trade_style,
                "pairs": config.pairs or DEFAULT_PAIRS,
                "groups": [
                    {
                        "name": group["name"],
                        "logic": group["logic"],
                        "conditions": len(group["conditions"]),
                    }
                    for group in group_descriptors(config)
                ],
            }
        ),
    )
    return {"status": "armed", "id": alert_id, "name": config.name}
