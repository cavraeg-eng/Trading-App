# RL Experiment Matrix

This is the concrete experiment plan for comparing RL variants on market pattern learning, signal quality, and regime adaptation.

## Goal

Identify the best combination of:

- algorithm: `PPO` vs `SAC`
- feature extractor: `MLP` vs `LSTM` vs `Transformer`
- context length: `window_size`

using **walk-forward validation** as the primary selection method.

## Core Matrix

| Experiment | Model | Architecture | Window | Train/Test Days | Timesteps/Fold | Why it matters |
| --- | --- | --- | --- | --- | --- | --- |
| `ppo_mlp_control` | PPO | MLP | 48 | 180 / 30 | 50,000 | Control run to check whether sequence models actually add edge |
| `ppo_lstm_baseline` | PPO | LSTM | 64 | 180 / 30 | 60,000 | Primary baseline for temporal dependencies and trend persistence |
| `ppo_transformer_long_context` | PPO | Transformer | 96 | 210 / 30 | 70,000 | Tests longer context and cyclical pattern recognition |
| `sac_mlp_control` | SAC | MLP | 48 | 180 / 30 | 60,000 | Control for continuous-action behavior without sequence memory |
| `sac_lstm_adaptive` | SAC | LSTM | 64 | 210 / 30 | 70,000 | Strong candidate for adaptive position sizing across regimes |
| `sac_transformer_regime` | SAC | Transformer | 96 | 210 / 30 | 80,000 | Highest-capacity setup for long-range structure and regime shifts |

## Selection Criteria

Rank experiments by:

1. **Composite walk-forward score**
2. **Average Sharpe ratio**
3. **Average total return**
4. **Average max drawdown**
5. **Profitable fold ratio**

### Hard promotion gates

Promote an experiment only if it passes all of these:

- profitable fold ratio `>= 50%`
- average max drawdown `<= 25%`
- average Sharpe ratio `> 0`
- average number of trades high enough to avoid inactive policies

### Composite score

The trainer writes `walk_forward_summary.json` with a score based on:

- higher return
- higher Sharpe
- higher win rate
- lower drawdown
- penalty for too-few trades

## Recommended Process

### Phase 1: Compare the full matrix

Run all 6 experiments with walk-forward validation:

```bash
python3 run_experiment_matrix.py --data-path ./data --execute
```

### Phase 2: Pick top 2

Select the best two experiments based on:

- best composite score
- best profitable fold ratio
- best drawdown stability

### Phase 3: Full retraining for the winner

Retrain the winner on the full dataset with standard training:

```bash
python3 train.py --data-path ./data --model PPO --architecture lstm --window-size 64 --timesteps 200000
```

## Outputs

Each experiment writes to its own directory under `models/experiment_matrix/`:

- `walk_forward_results.csv`
- `walk_forward_summary.json`

The matrix runner also writes:

- `models/experiment_matrix/experiment_ranking.csv`
- `models/experiment_matrix/experiment_ranking.md`
- `models/experiment_matrix/experiment_stability.csv`
- `models/experiment_matrix/experiment_stability.md`
- `models/experiment_matrix/winner_selection.json`
- `models/experiment_matrix/winner_selection.md`
- `models/experiment_matrix/winner_retrain.sh`

## Fold Stability Review

Use the stability report to find the setup that is not only high-scoring, but also consistent across folds:

- lower return volatility across folds
- smaller drawdown spread
- fewer negative folds
- better worst-fold behavior

This is especially useful when two experiments have similar average return but one is much less fragile.

## Summarize and Promote Workflow

After experiments finish, you can rank and promote the winner without rerunning the matrix:

```bash
# Summarize all completed runs
python3 run_experiment_matrix.py --summarize-only

# Promote the best promotion-ready winner
python3 run_experiment_matrix.py --summarize-only --promote-winner

# Promote and retrain the winner on full data
python3 run_experiment_matrix.py --summarize-only --promote-winner --retrain-best
```

If no experiment passes the promotion gates, you can still force selection:

```bash
python3 run_experiment_matrix.py --summarize-only --promote-winner --allow-unsafe-winner
```

You can also override full-data retraining timesteps:

```bash
python3 run_experiment_matrix.py --summarize-only --promote-winner --retrain-best --winner-timesteps 250000
```

## Notes

- Use `LSTM` as the practical default when you want the best balance of stability and sequence awareness.
- Use `Transformer` when longer context seems important and you have enough data.
- Treat `MLP` as a control, not the expected winner.
- `SAC` is most useful when smoother continuous sizing matters more than discrete-style stability.