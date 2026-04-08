"""Execution module for order management."""


def __getattr__(name):
    if name == "PaperTradingExecutor":
        from trading_bot.execution.paper import PaperTradingExecutor
        return PaperTradingExecutor
    if name == "LiveExecutor":
        from trading_bot.execution.live import LiveExecutor
        return LiveExecutor
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["PaperTradingExecutor", "LiveExecutor"]
