"""SQLite persistence layer for the trading bot.

New repository code should live in the domain module that owns the persisted
concept: settings, scanners, paper_trading, copy_trading, signals, alerts,
automation, or trade_ledger. Keep `repositories` as a compatibility facade for
older imports rather than adding new persistence behavior there.
"""
