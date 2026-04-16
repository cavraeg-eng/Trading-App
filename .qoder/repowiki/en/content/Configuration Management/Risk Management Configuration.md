# Risk Management Configuration

<cite>
**Referenced Files in This Document**
- [settings.py](file://trading_bot/config/settings.py)
- [manager.py](file://trading_bot/risk/manager.py)
- [sizing.py](file://trading_bot/risk/sizing.py)
- [circuit_breaker.py](file://trading_bot/risk/circuit_breaker.py)
- [paper.py](file://trading_bot/execution/paper.py)
- [live.py](file://trading_bot/execution/live.py)
- [main.py](file://trading_bot/main.py)
- [test_risk.py](file://trading_bot/tests/test_risk.py)
- [README.md](file://README.md)
</cite>

## Update Summary
**Changes Made**
- Enhanced zero-equity detection mechanism in RiskManager
- Improved drawdown calculation algorithms with better edge case handling
- Strengthened position sizing fallback mechanisms for robust operation
- Expanded circuit breaker system with multi-level severity classification
- Added comprehensive emergency stop functionality

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
10. [Appendices](#appendices)

## Introduction
This document provides comprehensive risk management configuration guidance for the trading bot. It explains drawdown controls, position sizing parameters, exposure limits, and volatility targeting settings. It covers max_daily_drawdown, max_position_size, max_total_exposure, and risk_per_trade calculations, along with volatility_target configuration and its impact on position sizing. It includes risk parameter tuning guidelines, stress testing recommendations, and integration with the circuit breaker system. Practical examples demonstrate conservative versus aggressive risk configurations for different market conditions.

**Updated** Enhanced with improved position sizing algorithms, better drawdown calculations, and zero-equity detection mechanisms for robust risk management.

## Project Structure
Risk management spans configuration, sizing, portfolio-level risk control, and circuit breakers. The system integrates with the execution engines (paper and live) and exposes risk metrics for monitoring and alerts.

```mermaid
graph TB
subgraph "Configuration"
CFG["Settings<br/>risk parameters"]
end
subgraph "Risk Core"
RM["RiskManager<br/>portfolio-level controls<br/>Zero-Equity Detection"]
PS["PositionSizer<br/>enhanced position sizing"]
CB["CircuitBreaker<br/>multi-level emergency controls<br/>Emergency Stop"]
end
subgraph "Execution"
PE["PaperExecutor<br/>paper trading"]
LE["LiveExecutor<br/>live trading"]
end
CFG --> RM
CFG --> PS
RM --> PE
RM --> LE
PS --> RM
RM --> CB
```

**Diagram sources**
- [settings.py:58-78](file://trading_bot/config/settings.py#L58-L78)
- [manager.py:58-101](file://trading_bot/risk/manager.py#L58-L101)
- [sizing.py:25-46](file://trading_bot/risk/sizing.py#L25-L46)
- [circuit_breaker.py:32-74](file://trading_bot/risk/circuit_breaker.py#L32-L74)
- [paper.py:70-74](file://trading_bot/execution/paper.py#L70-L74)
- [live.py:56](file://trading_bot/execution/live.py#L56)

**Section sources**
- [settings.py:58-78](file://trading_bot/config/settings.py#L58-L78)
- [manager.py:58-101](file://trading_bot/risk/manager.py#L58-L101)
- [sizing.py:25-46](file://trading_bot/risk/sizing.py#L25-L46)
- [circuit_breaker.py:32-74](file://trading_bot/risk/circuit_breaker.py#L32-L74)
- [paper.py:70-74](file://trading_bot/execution/paper.py#L70-L74)
- [live.py:56](file://trading_bot/execution/live.py#L56)

## Core Components
- **RiskManager**: Portfolio-level risk controller enforcing daily drawdown, position size, total exposure, and trade frequency limits. It computes daily drawdown and maintains open positions with enhanced zero-equity detection and improved drawdown calculations.
- **PositionSizer**: Implements multiple position sizing methods including fixed fraction, Kelly criterion, ATR-based, volatility targeting, and optimal f. It calculates risk_amount, notional, and leverage constraints with robust fallback mechanisms.
- **CircuitBreaker**: Enforces emergency controls including daily loss limits, maximum drawdown, position loss thresholds, consecutive losses, and volatility spikes. It supports automatic actions and cooldowns with multi-level severity classification and emergency stop functionality.
- **Settings**: Centralized risk parameters exposed via configuration, including max_daily_drawdown, max_position_size, max_total_exposure, risk_per_trade, and volatility_target.

Key risk parameters:
- **max_daily_drawdown**: Maximum allowable daily drawdown (fraction of peak equity).
- **max_position_size**: Maximum position size as a fraction of current equity.
- **max_total_exposure**: Maximum total exposure as a fraction of current equity.
- **risk_per_trade**: Risk per trade as a fraction of capital (used in fixed fraction sizing).
- **volatility_target**: Annualized volatility target for volatility targeting sizing.

**Updated** Enhanced with zero-equity detection and improved drawdown calculation algorithms.

**Section sources**
- [manager.py:61-88](file://trading_bot/risk/manager.py#L61-L88)
- [sizing.py:28-46](file://trading_bot/risk/sizing.py#L28-L46)
- [circuit_breaker.py:35-59](file://trading_bot/risk/circuit_breaker.py#L35-L59)
- [settings.py:59-78](file://trading_bot/config/settings.py#L59-L78)

## Architecture Overview
The risk system integrates with the execution engines and configuration. The RiskManager coordinates position opening/closing and enforces limits with enhanced zero-equity detection. PositionSizer computes sizes based on chosen methods with improved fallback mechanisms. CircuitBreaker monitors equity and volatility to trigger protective actions with multi-level severity classification.

```mermaid
sequenceDiagram
participant Exec as "Executor"
participant RM as "RiskManager<br/>Zero-Equity Detection"
participant PS as "PositionSizer<br/>Enhanced Fallbacks"
participant CB as "CircuitBreaker<br/>Multi-Level Controls"
Exec->>CB : check(current_equity, daily_pnl, position_pnls, volatility)
CB-->>Exec : event or None
Exec->>RM : can_open_position(symbol, side, size, price)
RM-->>Exec : (can_trade, reason)
alt can_trade
Exec->>PS : fixed_fraction/calculate size
PS-->>Exec : PositionSize
Exec->>RM : open_position(...)
RM-->>Exec : Position
else reject
Exec-->>Exec : log rejection
end
```

**Diagram sources**
- [main.py:265-279](file://trading_bot/main.py#L265-L279)
- [circuit_breaker.py:88-184](file://trading_bot/risk/circuit_breaker.py#L88-L184)
- [manager.py:102-148](file://trading_bot/risk/manager.py#L102-L148)
- [sizing.py:48-91](file://trading_bot/risk/sizing.py#L48-L91)

## Detailed Component Analysis

### RiskManager: Portfolio-Level Controls with Zero-Equity Detection
Responsibilities:
- Enforce max_daily_drawdown, max_position_size, max_total_exposure, max_trades_per_day, and correlation constraints.
- Track daily PnL, peak equity, current equity, and daily drawdown with enhanced calculation algorithms.
- Manage open positions and compute unrealized PnL updates.
- Trigger circuit breakers and integrate with stop-loss/take-profit logic.
- **New**: Implement zero-equity detection to prevent trading when account balance reaches zero.

Key calculations:
- **Enhanced**: daily_drawdown = (peak_equity - current_equity) / peak_equity with improved edge case handling
- Exposure = sum of notional values of open positions
- Position value = size × price / current_equity

Decision logic flow for position opening with zero-equity detection:

```mermaid
flowchart TD
Start(["can_open_position"]) --> CheckZero["Check zero equity"]
CheckZero --> ZeroOK{"Equity > 0?"}
ZeroOK --> |No| RejectZero["Reject: Zero equity detected"]
ZeroOK --> |Yes| CheckDD["Check daily drawdown"]
CheckDD --> DDOK{"Within limit?"}
DDOK --> |No| Reject1["Reject: daily drawdown limit"]
DDOK --> |Yes| CheckTrades["Check trades today"]
CheckTrades --> TradesOK{"Within limit?"}
TradesOK --> |No| Reject2["Reject: max trades per day"]
TradesOK --> |Yes| CheckPosSize["Compute position value / equity"]
CheckPosSize --> PosOK{"Within max_position_size?"}
PosOK --> |No| Reject3["Reject: position size limit"]
PosOK --> |Yes| CheckExposure["Compute new exposure"]
CheckExposure --> ExpOK{"Within max_total_exposure?"}
ExpOK --> |No| Reject4["Reject: total exposure limit"]
ExpOK --> |Yes| CheckExisting["Check existing position"]
CheckExisting --> ExistingOK{"No existing position?"}
ExistingOK --> |No| Reject5["Reject: already have position"]
ExistingOK --> |Yes| CheckCorr["Check correlation limit"]
CheckCorr --> CorrOK{"Within correlation threshold?"}
CorrOK --> |No| Reject6["Reject: high correlation"]
CorrOK --> |Yes| Approve["Approve"]
```

**Diagram sources**
- [manager.py:102-152](file://trading_bot/risk/manager.py#L102-L152)

**Section sources**
- [manager.py:58-101](file://trading_bot/risk/manager.py#L58-L101)
- [manager.py:102-152](file://trading_bot/risk/manager.py#L102-L152)
- [manager.py:234-237](file://trading_bot/risk/manager.py#L234-L237)
- [manager.py:299-321](file://trading_bot/risk/manager.py#L299-L321)

### PositionSizer: Enhanced Position Sizing Methods
Methods and parameters:
- **fixed_fraction**: Uses risk_per_trade and stop_loss to compute risk_amount and notional, then caps by max_position_size with improved fallback handling.
- **kelly_criterion**: Computes optimal fraction using historical win_rate, avg_win, avg_loss, scaled by kelly_fraction with enhanced error handling.
- **volatility_targeting**: Calculates realized volatility from price history, scales base notional by target_volatility/realized_vol, caps by max_position_size with robust fallback mechanisms.
- **atr_based**: Uses ATR to set stop distance and compute position size, with stop_loss derived from entry_price ± ATR multiplier with improved edge case handling.
- **optimal_f**: Uses historical returns to estimate optimal f and applies safety factor with enhanced numerical stability.

Key formulas:
- risk_amount = capital × risk_per_trade
- notional = min(risk_amount / (price_risk / entry_price), capital × max_position_size)
- realized_vol = std(log_returns) × sqrt(365)
- vol_scalar = target_volatility / realized_vol
- notional = base_notional × vol_scalar (with caps)

Impact of enhanced volatility_target:
- Lower realized volatility increases notional (more risk-on).
- Higher realized volatility decreases notional (more risk-off).
- **Enhanced**: Improved fallback to fixed_fraction sizing when insufficient data or zero volatility detected.
- Combined with risk_per_trade and max_position_size, it dynamically adjusts exposure with robust error handling.

**Section sources**
- [sizing.py:48-91](file://trading_bot/risk/sizing.py#L48-L91)
- [sizing.py:93-140](file://trading_bot/risk/sizing.py#L93-L140)
- [sizing.py:142-195](file://trading_bot/risk/sizing.py#L142-L195)
- [sizing.py:197-238](file://trading_bot/risk/sizing.py#L197-L238)
- [sizing.py:240-289](file://trading_bot/risk/sizing.py#L240-L289)

### CircuitBreaker: Multi-Level Emergency Controls with Emergency Stop
Triggers and actions with severity classification:
- **Daily loss limit**: Exceeds max_daily_loss_pct of current equity (CRITICAL level).
- **Maximum drawdown**: Drawdown reaches max_drawdown_pct (EMERGENCY level).
- **Position loss limit**: Single position loss exceeds max_position_loss_pct (ALERT level).
- **Consecutive losses**: Continuous losing periods reach max_consecutive_losses (WARNING level).
- **Volatility spike**: Current volatility exceeds baseline by max_volatility_spike (WARNING level).

Severity levels and automatic actions:
- **WARNING**: Reduce exposure, reduce position size
- **ALERT**: Close specific position
- **CRITICAL**: Pause trading
- **EMERGENCY**: Close all positions

Cooldown and reset:
- After triggering, a cooldown prevents repeated triggers for cooldown_minutes.
- Reset clears state and resets counters.

**New**: EmergencyStop mechanism for complete trading suspension with automatic handlers.

Integration with RiskManager:
- RiskManager's check_circuit_breakers mirrors drawdown thresholds and consecutive loss checks, complementing CircuitBreaker's broader metrics with enhanced multi-level classification.

**Section sources**
- [circuit_breaker.py:88-184](file://trading_bot/risk/circuit_breaker.py#L88-L184)
- [circuit_breaker.py:237-243](file://trading_bot/risk/circuit_breaker.py#L237-L243)
- [manager.py:299-321](file://trading_bot/risk/manager.py#L299-L321)

### Configuration and Parameter Tuning
Centralized risk parameters:
- **max_daily_drawdown**: Default 0.05 (5%).
- **max_position_size**: Default 0.3 (30%).
- **max_total_exposure**: Default 0.8 (80%).
- **risk_per_trade**: Default 0.02 (2%).
- **volatility_target**: Default 0.15 (15%).

Tuning guidelines:
- **Conservative configuration**:
  - max_daily_drawdown: 0.03–0.05
  - max_position_size: 0.15–0.25
  - max_total_exposure: 0.4–0.6
  - risk_per_trade: 0.01–0.02
  - volatility_target: 0.12–0.15
- **Aggressive configuration**:
  - max_daily_drawdown: 0.06–0.08
  - max_position_size: 0.4–0.6
  - max_total_exposure: 0.7–0.9
  - risk_per_trade: 0.03–0.05
  - volatility_target: 0.15–0.18

Market condition adjustments:
- **Low volatility environments**: Increase volatility_target slightly to reduce over-concentration.
- **High volatility regimes**: Decrease volatility_target to curtail risk-on behavior.
- **Trendy markets**: Consider higher risk_per_trade with tighter position size caps.
- **Sideways markets**: Favor lower risk_per_trade and stricter drawdown limits.

**Updated** Enhanced with improved parameter validation and edge case handling.

**Section sources**
- [settings.py:59-78](file://trading_bot/config/settings.py#L59-L78)
- [README.md:240-255](file://README.md#L240-L255)

### Integration with Execution Engines
- **PaperExecutor**: Initializes RiskManager with configured limits and uses PositionSizer for sizing. Applies slippage and commission in execution with enhanced error handling.
- **LiveExecutor**: Uses RiskManager for pre-trade checks and sizing, then places real orders via exchange APIs with rate limiting and enhanced validation.

```mermaid
classDiagram
class RiskManager {
+float max_daily_drawdown
+float max_position_size
+float max_total_exposure
+float risk_per_trade
+can_open_position(...)
+open_position(...)
+close_position(...)
+get_position_size(...)
+check_circuit_breakers()
+Zero-Equity Detection
}
class PositionSizer {
+float risk_per_trade
+float max_position_size
+float volatility_target
+fixed_fraction(...)
+kelly_criterion(...)
+volatility_targeting(...)
+atr_based(...)
+optimal_f(...)
+Enhanced Fallbacks
}
class PaperTradingExecutor {
+RiskManager risk_manager
+execute_signal(...)
+close_position(...)
+Slippage & Commission
}
class LiveExecutor {
+RiskManager risk_manager
+execute_signal(...)
+close_position(...)
+Rate Limiting
}
PaperTradingExecutor --> RiskManager : "uses"
LiveExecutor --> RiskManager : "uses"
RiskManager --> PositionSizer : "delegates sizing"
```

**Diagram sources**
- [paper.py:70-74](file://trading_bot/execution/paper.py#L70-L74)
- [live.py:56](file://trading_bot/execution/live.py#L56)
- [manager.py:90-93](file://trading_bot/risk/manager.py#L90-L93)

**Section sources**
- [paper.py:115-208](file://trading_bot/execution/paper.py#L115-L208)
- [live.py:115-223](file://trading_bot/execution/live.py#L115-L223)
- [manager.py:323-353](file://trading_bot/risk/manager.py#L323-L353)

## Dependency Analysis
- RiskManager depends on PositionSizer for sizing decisions and on configuration for limits with enhanced zero-equity detection.
- PositionSizer depends on configuration for risk_per_trade, max_position_size, and volatility_target with improved fallback mechanisms.
- CircuitBreaker operates independently but complements RiskManager's drawdown logic with multi-level severity classification.
- Execution engines depend on RiskManager for pre-trade checks and sizing with enhanced validation.

```mermaid
graph LR
Settings["Settings"] --> RiskManager
Settings --> PositionSizer
PositionSizer --> RiskManager
RiskManager --> CircuitBreaker
RiskManager --> PaperExecutor
RiskManager --> LiveExecutor
```

**Diagram sources**
- [settings.py:59-78](file://trading_bot/config/settings.py#L59-L78)
- [manager.py:90-93](file://trading_bot/risk/manager.py#L90-L93)
- [sizing.py:43-46](file://trading_bot/risk/sizing.py#L43-L46)
- [circuit_breaker.py:32-74](file://trading_bot/risk/circuit_breaker.py#L32-L74)
- [paper.py:70-74](file://trading_bot/execution/paper.py#L70-L74)
- [live.py:56](file://trading_bot/execution/live.py#L56)

**Section sources**
- [settings.py:59-78](file://trading_bot/config/settings.py#L59-L78)
- [manager.py:90-93](file://trading_bot/risk/manager.py#L90-L93)
- [sizing.py:43-46](file://trading_bot/risk/sizing.py#L43-L46)
- [circuit_breaker.py:32-74](file://trading_bot/risk/circuit_breaker.py#L32-L74)
- [paper.py:70-74](file://trading_bot/execution/paper.py#L70-L74)
- [live.py:56](file://trading_bot/execution/live.py#L56)

## Performance Considerations
- Position sizing computation is O(1) per trade; overhead is minimal with enhanced fallback mechanisms.
- Daily drawdown and exposure checks are O(n_positions) during updates with improved calculation algorithms.
- Circuit breaker checks are O(1) per cycle with multi-level severity processing.
- Volatility targeting requires sufficient price history; insufficient data falls back to fixed fraction sizing with robust error handling.
- **Enhanced**: Zero-equity detection adds minimal computational overhead while preventing trading failures.

## Troubleshooting Guide
Common issues and resolutions:
- **Position rejected due to daily drawdown limit**: Reduce risk_per_trade or increase max_daily_drawdown cautiously.
- **Position size exceeds limit**: Lower max_position_size or increase capital.
- **Total exposure limit exceeded**: Reduce max_total_exposure or avoid simultaneous positions.
- **Zero-equity detection triggered**: Check account funding and adjust initial capital settings.
- **Circuit breaker triggered**:
  - **Daily loss limit (CRITICAL)**: Pause trading until cooldown ends or reduce risk parameters.
  - **Maximum drawdown (EMERGENCY)**: Emergency close positions or tighten limits.
  - **Consecutive losses (WARNING)**: Reduce position size or switch to conservative mode.
  - **Volatility spike (WARNING)**: Reduce exposure and consider halting new entries.

**New**: EmergencyStop mechanism for complete trading suspension with automatic handlers.

Validation and testing:
- Use unit tests to verify sizing methods and risk checks with enhanced edge case coverage.
- Stress test with extreme scenarios (black swan events, high volatility spikes, zero-equity conditions).
- Backtest with walk-forward analysis to evaluate parameter robustness under various market conditions.

**Section sources**
- [test_risk.py:15-28](file://trading_bot/tests/test_risk.py#L15-L28)
- [test_risk.py:75-91](file://trading_bot/tests/test_risk.py#L75-L91)
- [test_risk.py:114-129](file://trading_bot/tests/test_risk.py#L114-L129)
- [test_risk.py:135-148](file://trading_bot/tests/test_risk.py#L135-L148)

## Conclusion
The risk management system provides robust portfolio-level controls, flexible position sizing, and emergency safeguards with enhanced reliability. Proper configuration of max_daily_drawdown, max_position_size, max_total_exposure, risk_per_trade, and volatility_target enables adaptation to varying market conditions. The enhanced zero-equity detection prevents trading failures, improved drawdown calculations handle edge cases more effectively, and the multi-level circuit breaker system provides comprehensive emergency protection. Conservative setups prioritize capital preservation, while aggressive setups aim for higher growth potential with stricter controls. Integration with execution engines ensures consistent enforcement across paper and live modes, and the enhanced circuit breaker system with emergency stop functionality provides automated protection during adverse conditions.

## Appendices

### Risk Parameter Definitions and Units
- **max_daily_drawdown**: Fraction of peak equity (e.g., 0.05 = 5%).
- **max_position_size**: Fraction of current equity (e.g., 0.3 = 30%).
- **max_total_exposure**: Fraction of current equity (e.g., 0.8 = 80%).
- **risk_per_trade**: Fraction of capital used per trade (e.g., 0.02 = 2%).
- **volatility_target**: Annualized volatility target (e.g., 0.15 = 15%).

### Enhanced Emergency Control Levels
- **WARNING**: Reduced exposure, reduced position size
- **ALERT**: Close specific position
- **CRITICAL**: Pause trading
- **EMERGENCY**: Close all positions

### Example Configurations

Conservative configuration:
- max_daily_drawdown: 0.04
- max_position_size: 0.20
- max_total_exposure: 0.50
- risk_per_trade: 0.015
- volatility_target: 0.13

Aggressive configuration:
- max_daily_drawdown: 0.07
- max_position_size: 0.50
- max_total_exposure: 0.85
- risk_per_trade: 0.04
- volatility_target: 0.17

**Updated** Enhanced with improved parameter validation and emergency control mechanisms.