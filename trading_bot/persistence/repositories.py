"""Compatibility facade for domain-specific persistence repositories.

Prefer importing new persistence code from the domain modules in
`trading_bot.persistence` instead of adding to this facade.
"""

from trading_bot.persistence.settings import (
    get_setting,
    set_setting,
    get_all_settings,
    delete_setting,
)

from trading_bot.persistence.scanners import (
    save_scanner,
    get_saved_scanners,
    update_scanner,
    delete_scanner,
)

from trading_bot.persistence.paper_trading import (
    get_paper_account,
    update_paper_balance,
    insert_paper_order,
    save_strategy_performance_snapshot,
    get_strategy_performance_snapshot,
    get_paper_positions,
    get_paper_history,
    reset_paper_account,
)

from trading_bot.persistence.copy_trading import (
    get_copy_settings,
    update_copy_settings,
    insert_copy_trade,
    get_open_copy_trades,
    get_copy_trade,
    get_open_copy_trade_for_signal,
    update_copy_trade,
    count_copy_history,
    get_copy_history,
)

from trading_bot.persistence.signals import (
    get_signal_prediction,
    insert_signal_prediction,
    insert_signal_outcome,
    get_signal_metrics,
    get_signal_outcome_summary,
)

from trading_bot.persistence.alerts import (
    create_alert,
    get_alerts,
    get_unread_count,
    mark_read,
    mark_all_read,
    get_recent_alert,
)

from trading_bot.persistence.automation import (
    insert_automation_execution,
    get_automation_executions,
    count_recent_automation_executions,
)

from trading_bot.persistence.trade_ledger import (
    upsert_trade_ledger_entry,
    update_trade_ledger_status,
    get_trade_ledger_entries,
    get_trade_ledger_metrics,
)

__all__ = [
    "get_setting",
    "set_setting",
    "get_all_settings",
    "delete_setting",
    "save_scanner",
    "get_saved_scanners",
    "update_scanner",
    "delete_scanner",
    "get_paper_account",
    "update_paper_balance",
    "insert_paper_order",
    "save_strategy_performance_snapshot",
    "get_strategy_performance_snapshot",
    "get_paper_positions",
    "get_paper_history",
    "reset_paper_account",
    "get_copy_settings",
    "update_copy_settings",
    "insert_copy_trade",
    "get_open_copy_trades",
    "get_copy_trade",
    "get_open_copy_trade_for_signal",
    "update_copy_trade",
    "count_copy_history",
    "get_copy_history",
    "get_signal_prediction",
    "insert_signal_prediction",
    "insert_signal_outcome",
    "get_signal_metrics",
    "get_signal_outcome_summary",
    "create_alert",
    "get_alerts",
    "get_unread_count",
    "mark_read",
    "mark_all_read",
    "get_recent_alert",
    "insert_automation_execution",
    "get_automation_executions",
    "count_recent_automation_executions",
    "upsert_trade_ledger_entry",
    "update_trade_ledger_status",
    "get_trade_ledger_entries",
    "get_trade_ledger_metrics",
]
