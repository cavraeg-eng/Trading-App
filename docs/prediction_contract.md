# AI prediction and suggestion contract

`ONE-21` defines a single backend-owned contract for AI trading predictions and suggestions. New scanner, live workspace, journal, and automation work should consume `PredictionRequest` and `PredictionResponse` from `trading_bot.api.models` instead of creating local payload shapes.

## Request shape

`PredictionRequest` includes:

- `symbol`
- `asset_class`
- `timeframe`
- `strategy_mode`
- `broker_context`
- `source_context`
- `market_session`
- `requested_at`
- `correlation_symbols`
- `features`

`broker_context` carries optional broker/account details for risk-aware suggestions. `source_context` identifies the initiating surface, including scanner presets, watchlists, automation templates, live workspace, journal, or direct API calls. The current heuristic adapter maps strategy modes to existing market-analysis trade styles as follows: `scalp` uses scalp data, while `swing`, `intraday`, `position`, and `automation` use the swing analysis path until dedicated model adapters exist for those modes.

`broker_context` is advisory, optional, and sanitized. It may include balance/equity, margin availability, open position summaries, symbol exposure, configured risk percentage, daily loss limits, max exposure limits, trading mode, and a context timestamp. It must never include credentials, API keys, tokens, raw broker payloads, connection strings, or sensitive account identifiers. If account context is missing, partial, or stale, the response degrades gracefully with an explicit status and warning.

## Response shape

`PredictionResponse` always includes:

- `prediction_id`
- the original `request`
- `symbol`, `asset_class`, `timeframe`, and `strategy_mode`
- `recommendation`
- numeric `confidence` and bucketed `confidence_band`
- structured `rationale`
- structured `warnings`
- `account_context_status`
- `account_risk_warnings`
- advisory `position_size` and `position_size_reason`
- advisory `trade_allowed`
- `freshness` metadata
- `latency` metadata
- chart-ready `chart` overlays
- suggestion-card-ready `suggestion_card`
- `generated_at`
- consumer `compatibility` guidance

Buy and sell responses must include:

- `entry`
- `stop_loss`
- `take_profit_targets`
- `invalidation_level`
- `risk_reward`

No-trade responses must include `no_trade_reason` and must not include actionable entry, stop, or target levels.

Account-aware suggestions may block or downgrade otherwise actionable setups when advisory context shows stale account data, daily loss limit breaches, unavailable margin, exposure limit breaches, incompatible trading mode, or conflicting open positions. Broker execution safety gates remain authoritative and must still validate any order before placement.

## Recommendation states

The contract supports four states:

- `buy`
- `sell`
- `hold`
- `no_trade`

`hold` means the system has a valid neutral view that can still be displayed. `no_trade` means the system intentionally refuses an actionable setup because of a machine-readable reason such as `insufficient_data`, `stale_data`, `low_confidence`, `market_closed`, `risk_limits`, `conflicting_signals`, `unsupported_asset`, `model_unavailable`, `reward_risk_compressed`, or `automation_disabled`.

## Consumer compatibility

- Scanner cards should use `suggestion_card`, `confidence_band`, `warnings`, and `no_trade_reason` for sorting, filtering, and display.
- Live workspace charts should use `chart.entry_zone`, `chart.stop_loss`, `chart.take_profit_targets`, `chart.invalidation_level`, `chart.support`, and `chart.resistance` for buy/sell recommendations. Hold and no-trade responses should render neutral state copy and avoid actionable trade overlays when those fields are absent.
- Journal records should persist `prediction_id`, `recommendation`, `confidence`, setup levels, and `rationale` with resulting trade outcomes.
- Automation should treat `no_trade` as a successful non-execution result. It should gate live orders on recommendation, confidence, freshness, warnings, risk/reward, and broker risk checks.

## API boundaries

The contract is exposed through:

- `GET /api/predictions/contract`
- `POST /api/predictions/suggestion`
- `GET /api/predictions/suggestion/{symbol}`

These endpoints prove the contract is usable without implementing a full model inference engine. Current suggestions adapt the existing heuristic market analysis into the stable prediction shape.