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

`broker_context` carries optional broker/account details for risk-aware suggestions. `source_context` identifies the initiating surface, including scanner presets, watchlists, automation templates, live workspace, journal, or direct API calls.

## Response shape

`PredictionResponse` always includes:

- `prediction_id`
- the original `request`
- `symbol`, `asset_class`, `timeframe`, and `strategy_mode`
- `recommendation`
- numeric `confidence` and bucketed `confidence_band`
- structured `rationale` with summary text, renderable evidence factors, conflicts, blockers, and next conditions
- structured `warnings`
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

## Explainable rationale

`PredictionResponse.rationale` is a structured object that lets scanner, workspace, journal, and automation consumers render the explanation without parsing prose.

The object includes:

- `summary`: concise trader-readable explanation that avoids profitability promises.
- `confidence_label`: stable confidence bucket for UI copy.
- `primary_reasons`: supportive, weak, or neutral evidence factors.
- `conflicts`: evidence that reduces conviction or warns against immediate action.
- `blockers`: hard blockers that explain no-trade states.
- `next_conditions`: conditions that must remain true or improve before action.

Each rationale factor includes:

- `category`: machine-readable contributor such as `trend`, `momentum`, `volatility`, `support_resistance`, `spread`, `account_risk`, `data_quality`, `confidence`, or `validation`.
- `stance`: one of `supportive`, `conflicting`, `weak`, `neutral`, or `blocking`.
- `strength`: one of `strong`, `medium`, or `weak`.
- `message`: display-safe explanation text.
- optional `direction`, `source`, and `weight`.

Buy and sell suggestions must include `primary_reasons`. No-trade suggestions must include `blockers` and `next_conditions`. Hold suggestions should explain why waiting is preferred and what would need to improve before a trade becomes valid.

## Recommendation states

The contract supports four states:

- `buy`
- `sell`
- `hold`
- `no_trade`

`hold` means the system has a valid neutral view that can still be displayed. `no_trade` means the system intentionally refuses an actionable setup because of a machine-readable reason such as `insufficient_data`, `stale_data`, `low_confidence`, `market_closed`, `risk_limits`, `conflicting_signals`, `unsupported_asset`, `model_unavailable`, `reward_risk_compressed`, or `automation_disabled`.

## Consumer compatibility

- Scanner cards should use `suggestion_card`, `confidence_band`, `warnings`, and `no_trade_reason` for sorting, filtering, and display.
- Live workspace charts should use `chart.entry_zone`, `chart.stop_loss`, `chart.take_profit_targets`, `chart.invalidation_level`, `chart.support`, and `chart.resistance`.
- Journal records should persist `prediction_id`, `recommendation`, `confidence`, setup levels, and structured `rationale` with resulting trade outcomes.
- Automation should treat `no_trade` as a successful non-execution result. It should gate live orders on recommendation, confidence, freshness, warnings, risk/reward, and broker risk checks.

## API boundaries

The contract is exposed through:

- `GET /api/predictions/contract`
- `POST /api/predictions/suggestion`
- `GET /api/predictions/suggestion/{symbol}`

These endpoints prove the contract is usable without implementing a full model inference engine. Current suggestions adapt the existing heuristic market analysis into the stable prediction shape.