"""Monitoring and alerting module."""

__all__ = ["AlertManager", "Dashboard"]


def __getattr__(name: str):
    if name == "AlertManager":
        from trading_bot.monitoring.alerts import AlertManager

        return AlertManager
    if name == "Dashboard":
        from trading_bot.monitoring.dashboard import Dashboard

        return Dashboard
    raise AttributeError(name)
