"""Data validation for OHLCV DataFrames.

Catches empty frames, missing columns, stale data, anomalous jumps,
and other quality issues before data reaches consumers.
"""

import time
from typing import Optional, Tuple

import numpy as np
import pandas as pd

from trading_bot.config import get_logger

logger = get_logger(__name__)


# Timeframe durations in seconds for staleness checks
_TIMEFRAME_SECONDS = {
    "1m": 60, "5m": 300, "15m": 900,
    "1h": 3600, "4h": 14400, "1d": 86400,
}

REQUIRED_COLUMNS = {"open", "high", "low", "close", "volume"}

# Maximum allowed gap between consecutive candles as multiple of expected interval
MAX_STALENESS_MULTIPLE = 3.0

# Maximum allowed single-candle price jump (percentage)
MAX_PRICE_JUMP_PCT = 10.0


def _stale_threshold_seconds(
    symbol: str,
    timeframe: str,
    source_type: Optional[str],
    trade_style: Optional[str],
) -> float:
    expected = _TIMEFRAME_SECONDS.get(timeframe, 3600)
    threshold = expected * MAX_STALENESS_MULTIPLE

    if symbol == "XAU/USD" and source_type == "synthetic_spot_from_futures" and trade_style == "scalp":
        if timeframe == "1m":
            return 30 * 60
        if timeframe == "5m":
            return 45 * 60

    return threshold


def _price_jump_threshold_pct(
    symbol: str,
    timeframe: str,
    source_type: Optional[str],
    trade_style: Optional[str],
) -> float:
    if symbol == "XAU/USD" and source_type == "synthetic_spot_from_futures" and trade_style == "scalp":
        if timeframe == "1m":
            return 35.0
        if timeframe == "5m":
            return 25.0
    return MAX_PRICE_JUMP_PCT


def _should_warn_price_jump(
    symbol: str,
    timeframe: str,
    source_type: Optional[str],
    trade_style: Optional[str],
) -> bool:
    if symbol == "XAU/USD" and source_type == "synthetic_spot_from_futures" and trade_style == "scalp":
        return False
    return True


def _is_likely_futures_roll_gap(
    symbol: str,
    timeframe: str,
    source_type: Optional[str],
    big_jumps: pd.Series,
) -> bool:
    if symbol != "XAU/USD" or timeframe != "1d" or source_type != "futures":
        return False
    if big_jumps.empty:
        return False

    max_jump_pct = float(big_jumps.max()) * 100
    return len(big_jumps) <= 3 and max_jump_pct >= 8.0


def validate_ohlcv(
    df: Optional[pd.DataFrame],
    symbol: str,
    timeframe: str = "1h",
    min_rows: int = 5,
    source_type: Optional[str] = None,
    trade_style: Optional[str] = None,
) -> Tuple[Optional[pd.DataFrame], list]:
    """Validate an OHLCV DataFrame and return (clean_df, issues).

    Args:
        df: DataFrame to validate (may be None).
        symbol: Trading symbol for logging context.
        timeframe: Expected timeframe for staleness detection.
        min_rows: Minimum acceptable number of rows.

    Returns:
        Tuple of (validated DataFrame or None, list of issue descriptions).
        If the DataFrame fails critical checks, returns (None, issues).
    """
    issues: list = []

    # ── Critical: empty or None ──────────────────────────────────────────────
    if df is None or df.empty:
        issues.append("empty_or_none")
        logger.warning("Validation failed: empty data", symbol=symbol)
        return None, issues

    # ── Critical: required columns ───────────────────────────────────────────
    cols = set(df.columns.str.lower())
    missing = REQUIRED_COLUMNS - cols
    if missing:
        issues.append(f"missing_columns:{','.join(sorted(missing))}")
        logger.warning(
            "Validation failed: missing columns",
            symbol=symbol,
            missing=list(missing),
        )
        return None, issues

    # ── Critical: minimum row count ──────────────────────────────────────────
    if len(df) < min_rows:
        issues.append(f"insufficient_rows:{len(df)}")
        logger.warning(
            "Validation failed: insufficient rows",
            symbol=symbol,
            rows=len(df),
            min_required=min_rows,
        )
        return None, issues

    # ── Warning: NaN / Inf in OHLC ───────────────────────────────────────────
    ohlc_cols = [c for c in ["open", "high", "low", "close"] if c in df.columns]
    nan_count = df[ohlc_cols].isna().sum().sum()
    inf_count = np.isinf(df[ohlc_cols].select_dtypes(include=[np.number])).sum().sum()
    if nan_count > 0 or inf_count > 0:
        issues.append(f"nan_inf_values:nan={nan_count},inf={inf_count}")
        logger.warning(
            "Data contains NaN/Inf",
            symbol=symbol,
            nan_count=int(nan_count),
            inf_count=int(inf_count),
        )
        # Drop rows with NaN in OHLC but don't fail entirely
        df = df.dropna(subset=ohlc_cols)
        if len(df) < min_rows:
            issues.append("insufficient_rows_after_nan_cleanup")
            return None, issues

    # ── Warning: high < low ──────────────────────────────────────────────────
    if "high" in df.columns and "low" in df.columns:
        bad_hl = (df["high"] < df["low"]).sum()
        if bad_hl > 0:
            issues.append(f"high_below_low:{bad_hl}")
            logger.warning(
                "Found rows where high < low",
                symbol=symbol,
                count=int(bad_hl),
            )

    # ── Warning: anomalous price jumps ───────────────────────────────────────
    if "close" in df.columns and len(df) > 1:
        jump_threshold_pct = _price_jump_threshold_pct(symbol, timeframe, source_type, trade_style)
        pct_change = df["close"].pct_change().abs()
        big_jumps = pct_change[pct_change > jump_threshold_pct / 100.0]
        if len(big_jumps) > 0:
            max_jump = float(pct_change.max()) * 100
            if _is_likely_futures_roll_gap(symbol, timeframe, source_type, big_jumps):
                issues.append(f"futures_roll_gap:{len(big_jumps)}_bars,max={max_jump:.1f}%")
                logger.info(
                    "Likely futures roll gap detected",
                    symbol=symbol,
                    jump_count=len(big_jumps),
                    max_jump_pct=round(max_jump, 1),
                    timeframe=timeframe,
                )
            else:
                issues.append(f"price_jump:{len(big_jumps)}_bars,max={max_jump:.1f}%")
                if _should_warn_price_jump(symbol, timeframe, source_type, trade_style):
                    logger.warning(
                        "Anomalous price jumps detected",
                        symbol=symbol,
                        jump_count=len(big_jumps),
                        max_jump_pct=round(max_jump, 1),
                    )
                else:
                    logger.info(
                        "Synthetic spot price jump tolerated",
                        symbol=symbol,
                        jump_count=len(big_jumps),
                        max_jump_pct=round(max_jump, 1),
                        timeframe=timeframe,
                    )

    # ── Warning: stale data ──────────────────────────────────────────────────
    if hasattr(df.index, 'tz') or isinstance(df.index, pd.DatetimeIndex):
        try:
            latest_ts = df.index[-1]
            if hasattr(latest_ts, 'timestamp'):
                latest_epoch = latest_ts.timestamp()
            else:
                latest_epoch = pd.Timestamp(latest_ts).timestamp()
            age = time.time() - latest_epoch
            stale_threshold = _stale_threshold_seconds(symbol, timeframe, source_type, trade_style)
            if age > stale_threshold:
                hours_old = age / 3600
                issues.append(f"stale_data:{hours_old:.1f}h_old")
                logger.warning(
                    "Data may be stale",
                    symbol=symbol,
                    hours_old=round(hours_old, 1),
                    timeframe=timeframe,
                )
        except Exception:
            pass  # Don't fail validation on timestamp parsing issues

    return df, issues


def validate_spot_price(
    price: Optional[float],
    symbol: str,
    source: str,
    reference_price: Optional[float] = None,
    max_deviation_pct: float = 1.0,
) -> Tuple[bool, list]:
    """Validate a spot price value.

    Args:
        price: The price to validate.
        symbol: Symbol for logging.
        source: Source name for logging.
        reference_price: Optional reference price for deviation check.
        max_deviation_pct: Maximum allowed deviation from reference (%).

    Returns:
        Tuple of (is_valid, list of issue descriptions).
    """
    issues: list = []

    if price is None:
        issues.append("null_price")
        return False, issues

    if price <= 0:
        issues.append(f"non_positive_price:{price}")
        return False, issues

    if not np.isfinite(price):
        issues.append(f"non_finite_price:{price}")
        return False, issues

    # Cross-source deviation check
    if reference_price is not None and reference_price > 0:
        deviation_pct = abs(price - reference_price) / reference_price * 100
        if deviation_pct > max_deviation_pct:
            issues.append(
                f"source_deviation:{source}={price:.2f}"
                f"_vs_ref={reference_price:.2f}"
                f"_dev={deviation_pct:.2f}%"
            )
            logger.warning(
                "Spot price deviation exceeds threshold",
                symbol=symbol,
                source=source,
                price=price,
                reference=reference_price,
                deviation_pct=round(deviation_pct, 2),
                threshold_pct=max_deviation_pct,
            )

    return len(issues) == 0, issues
