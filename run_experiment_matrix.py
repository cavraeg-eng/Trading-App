#!/usr/bin/env python3
"""Run, summarize, and promote a concrete RL experiment matrix."""

from __future__ import annotations

import argparse
import csv
import json
import math
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional


MIN_PROFITABLE_FOLD_RATIO = 0.50
MAX_AVG_DRAWDOWN = 0.25
MIN_AVG_SHARPE = 0.0
MIN_AVG_NUM_TRADES = 5.0
DEFAULT_MIN_WINNER_TIMESTEPS = 200000


@dataclass(frozen=True)
class ExperimentSpec:
    """Definition for a single experiment run."""

    name: str
    model: str
    architecture: str
    window_size: int
    timesteps: int
    train_days: int
    test_days: int
    timesteps_per_fold: int
    rationale: str


def get_experiment_matrix() -> List[ExperimentSpec]:
    """Return the recommended PPO/SAC experiment matrix."""
    return [
        ExperimentSpec(
            name="ppo_mlp_control",
            model="PPO",
            architecture="mlp",
            window_size=48,
            timesteps=125000,
            train_days=180,
            test_days=30,
            timesteps_per_fold=50000,
            rationale="Control run to benchmark whether sequence models add value.",
        ),
        ExperimentSpec(
            name="ppo_lstm_baseline",
            model="PPO",
            architecture="lstm",
            window_size=64,
            timesteps=150000,
            train_days=180,
            test_days=30,
            timesteps_per_fold=60000,
            rationale="Primary baseline for temporal pattern learning and regime shifts.",
        ),
        ExperimentSpec(
            name="ppo_transformer_long_context",
            model="PPO",
            architecture="transformer",
            window_size=96,
            timesteps=175000,
            train_days=210,
            test_days=30,
            timesteps_per_fold=70000,
            rationale="Longer context test for market structure and cyclical pattern capture.",
        ),
        ExperimentSpec(
            name="sac_mlp_control",
            model="SAC",
            architecture="mlp",
            window_size=48,
            timesteps=150000,
            train_days=180,
            test_days=30,
            timesteps_per_fold=60000,
            rationale="Continuous-control baseline without sequence extractor complexity.",
        ),
        ExperimentSpec(
            name="sac_lstm_adaptive",
            model="SAC",
            architecture="lstm",
            window_size=64,
            timesteps=175000,
            train_days=210,
            test_days=30,
            timesteps_per_fold=70000,
            rationale="Adaptive action sizing with sequence memory for changing regimes.",
        ),
        ExperimentSpec(
            name="sac_transformer_regime",
            model="SAC",
            architecture="transformer",
            window_size=96,
            timesteps=200000,
            train_days=210,
            test_days=30,
            timesteps_per_fold=80000,
            rationale="Highest-capacity setup for long-range dependencies and regime transitions.",
        ),
    ]


def build_walk_forward_command(
    python_bin: str,
    data_path: Path,
    output_root: Path,
    spec: ExperimentSpec,
    symbols: List[str],
) -> List[str]:
    """Build the CLI command for an experiment."""
    command = [
        python_bin,
        "train.py",
        "--data-path",
        str(data_path),
        "--output",
        str(output_root / spec.name),
        "--model",
        spec.model,
        "--architecture",
        spec.architecture,
        "--window-size",
        str(spec.window_size),
        "--timesteps",
        str(spec.timesteps),
        "--walk-forward",
        "--train-days",
        str(spec.train_days),
        "--test-days",
        str(spec.test_days),
        "--timesteps-per-fold",
        str(spec.timesteps_per_fold),
    ]
    if symbols:
        command.extend(["--symbols", *symbols])
    return command


def build_retrain_command(
    python_bin: str,
    data_path: Path,
    output_root: Path,
    winner: Dict,
    symbols: List[str],
    winner_timesteps: int,
    optimize_hyperparams: bool,
) -> List[str]:
    """Build the full-data retraining command for the winning setup."""
    output_dir = output_root / "winner_retrain"
    command = [
        python_bin,
        "train.py",
        "--data-path",
        str(data_path),
        "--output",
        str(output_dir),
        "--model",
        str(winner["model"]),
        "--architecture",
        str(winner["architecture"]),
        "--window-size",
        str(int(winner["window_size"])),
        "--timesteps",
        str(winner_timesteps),
    ]
    if not optimize_hyperparams:
        command.append("--no-optimize")
    if symbols:
        command.extend(["--symbols", *symbols])
    return command


def load_summary(summary_path: Path) -> Dict:
    """Load a walk-forward summary if present."""
    if not summary_path.exists():
        return {}
    return json.loads(summary_path.read_text())


def score_sort_key(summary: Dict) -> float:
    """Sort summaries by the persisted composite score."""
    return float(summary.get("composite_score", float("-inf")))


def evaluate_promotion_gates(summary: Dict) -> List[str]:
    """Return failing promotion gates for a summary."""
    failures = []
    if float(summary.get("profitable_fold_ratio", 0.0)) < MIN_PROFITABLE_FOLD_RATIO:
        failures.append(
            f"profitable_fold_ratio<{MIN_PROFITABLE_FOLD_RATIO:.0%}"
        )
    if float(summary.get("average_max_drawdown", 1.0)) > MAX_AVG_DRAWDOWN:
        failures.append(f"average_max_drawdown>{MAX_AVG_DRAWDOWN:.0%}")
    if float(summary.get("average_sharpe_ratio", 0.0)) <= MIN_AVG_SHARPE:
        failures.append("average_sharpe_ratio<=0")
    if float(summary.get("average_num_trades", 0.0)) < MIN_AVG_NUM_TRADES:
        failures.append(f"average_num_trades<{MIN_AVG_NUM_TRADES:.0f}")
    return failures


def build_ranking_row(spec: ExperimentSpec, summary: Dict) -> Dict:
    """Combine experiment metadata and summary metrics into one ranking row."""
    gate_failures = evaluate_promotion_gates(summary)
    return {
        "name": spec.name,
        "model": spec.model,
        "architecture": spec.architecture,
        "window_size": spec.window_size,
        "timesteps": spec.timesteps,
        "train_days": spec.train_days,
        "test_days": spec.test_days,
        "timesteps_per_fold": spec.timesteps_per_fold,
        "average_total_return": float(summary.get("average_total_return", 0.0)),
        "average_sharpe_ratio": float(summary.get("average_sharpe_ratio", 0.0)),
        "average_max_drawdown": float(summary.get("average_max_drawdown", 0.0)),
        "average_win_rate": float(summary.get("average_win_rate", 0.0)),
        "average_num_trades": float(summary.get("average_num_trades", 0.0)),
        "profitable_fold_ratio": float(summary.get("profitable_fold_ratio", 0.0)),
        "composite_score": float(summary.get("composite_score", float("-inf"))),
        "promotion_ready": not gate_failures,
        "gate_failures": ", ".join(gate_failures) if gate_failures else "none",
        "rationale": spec.rationale,
    }


def collect_rankings(output_root: Path, experiments: Iterable[ExperimentSpec]) -> List[Dict]:
    """Collect ranking rows for all experiments with completed summaries."""
    rankings = []
    for spec in experiments:
        summary = load_summary(output_root / spec.name / "walk_forward_summary.json")
        if summary:
            rankings.append(build_ranking_row(spec, summary))
    return rankings


def rank_results(rankings: List[Dict]) -> List[Dict]:
    """Sort and annotate ranking rows."""
    ranked = sorted(rankings, key=score_sort_key, reverse=True)
    for rank, row in enumerate(ranked, start=1):
        row["rank"] = rank
    return ranked


def load_fold_results(results_path: Path) -> List[Dict]:
    """Load walk-forward fold rows if present."""
    if not results_path.exists():
        return []

    with results_path.open(newline="") as file_handle:
        return list(csv.DictReader(file_handle))


def build_stability_row(spec: ExperimentSpec, summary: Dict, folds: List[Dict]) -> Dict:
    """Build a fold-stability summary row for an experiment."""
    returns = [float(row.get("total_return", 0.0) or 0.0) for row in folds]
    sharpes = [float(row.get("sharpe_ratio", 0.0) or 0.0) for row in folds]
    drawdowns = [float(row.get("max_drawdown", 0.0) or 0.0) for row in folds]

    mean_return = float(summary.get("average_total_return", 0.0))
    return_std = (
        float(math.sqrt(sum((value - mean_return) ** 2 for value in returns) / len(returns)))
        if returns
        else 0.0
    )
    drawdown_spread = float(max(drawdowns) - min(drawdowns)) if drawdowns else 0.0
    sharpe_spread = float(max(sharpes) - min(sharpes)) if sharpes else 0.0
    negative_fold_ratio = (
        float(sum(1 for value in returns if value < 0) / len(returns))
        if returns
        else 0.0
    )

    stability_score = float(
        summary.get("composite_score", float("-inf"))
        - return_std * 50.0
        - drawdown_spread * 20.0
        - negative_fold_ratio * 10.0
    )

    return {
        "name": spec.name,
        "model": spec.model,
        "architecture": spec.architecture,
        "num_folds": len(folds),
        "average_total_return": mean_return,
        "return_std_dev": return_std,
        "best_fold_return": max(returns) if returns else 0.0,
        "worst_fold_return": min(returns) if returns else 0.0,
        "average_sharpe_ratio": float(summary.get("average_sharpe_ratio", 0.0)),
        "sharpe_spread": sharpe_spread,
        "average_max_drawdown": float(summary.get("average_max_drawdown", 0.0)),
        "drawdown_spread": drawdown_spread,
        "negative_fold_ratio": negative_fold_ratio,
        "profitable_fold_ratio": float(summary.get("profitable_fold_ratio", 0.0)),
        "stability_score": stability_score,
    }


def build_stability_report(output_root: Path, experiments: Iterable[ExperimentSpec]) -> List[Dict]:
    """Create fold-stability rows from completed experiment outputs."""
    rows = []
    for spec in experiments:
        summary = load_summary(output_root / spec.name / "walk_forward_summary.json")
        folds = load_fold_results(output_root / spec.name / "walk_forward_results.csv")
        if summary and folds:
            rows.append(build_stability_row(spec, summary, folds))

    rows.sort(key=lambda row: float(row["stability_score"]), reverse=True)
    for rank, row in enumerate(rows, start=1):
        row["stability_rank"] = rank
    return rows


def write_stability_report(output_root: Path, rows: List[Dict]) -> None:
    """Persist a markdown and CSV fold-stability report."""
    csv_path = output_root / "experiment_stability.csv"
    md_path = output_root / "experiment_stability.md"

    fieldnames = [
        "stability_rank",
        "name",
        "model",
        "architecture",
        "num_folds",
        "average_total_return",
        "return_std_dev",
        "best_fold_return",
        "worst_fold_return",
        "average_sharpe_ratio",
        "sharpe_spread",
        "average_max_drawdown",
        "drawdown_spread",
        "negative_fold_ratio",
        "profitable_fold_ratio",
        "stability_score",
    ]

    with csv_path.open("w", newline="") as file_handle:
        writer = csv.DictWriter(file_handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    lines = [
        "# RL Fold Stability Report",
        "",
        "| Rank | Experiment | Model | Arch | Avg Return | Return Std | Worst Fold | Avg Max DD | Neg Folds | Stability Score |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row["stability_rank"]),
                    row["name"],
                    row["model"],
                    row["architecture"],
                    f'{row["average_total_return"]:.2%}',
                    f'{row["return_std_dev"]:.2%}',
                    f'{row["worst_fold_return"]:.2%}',
                    f'{row["average_max_drawdown"]:.2%}',
                    f'{row["negative_fold_ratio"]:.0%}',
                    f'{row["stability_score"]:.2f}',
                ]
            )
            + " |"
        )

    md_path.write_text("\n".join(lines) + "\n")


def select_best_winner(rankings: List[Dict], allow_unsafe: bool = False) -> Optional[Dict]:
    """Select the best winner, preferring promotion-ready setups."""
    if not rankings:
        return None

    for row in rankings:
        if row.get("promotion_ready"):
            return row

    if allow_unsafe:
        return rankings[0]

    return None


def write_rankings(output_root: Path, rankings: List[Dict]) -> None:
    """Persist experiment ranking outputs."""
    csv_path = output_root / "experiment_ranking.csv"
    md_path = output_root / "experiment_ranking.md"

    fieldnames = [
        "rank",
        "name",
        "model",
        "architecture",
        "window_size",
        "timesteps",
        "train_days",
        "test_days",
        "timesteps_per_fold",
        "average_total_return",
        "average_sharpe_ratio",
        "average_max_drawdown",
        "average_win_rate",
        "average_num_trades",
        "profitable_fold_ratio",
        "composite_score",
        "promotion_ready",
        "gate_failures",
        "rationale",
    ]

    with csv_path.open("w", newline="") as file_handle:
        writer = csv.DictWriter(file_handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rankings)

    lines = [
        "# RL Experiment Ranking",
        "",
        "| Rank | Experiment | Model | Arch | Avg Return | Avg Sharpe | Avg Max DD | Profitable Folds | Ready | Score |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in rankings:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row["rank"]),
                    row["name"],
                    row["model"],
                    row["architecture"],
                    f'{row["average_total_return"]:.2%}',
                    f'{row["average_sharpe_ratio"]:.2f}',
                    f'{row["average_max_drawdown"]:.2%}',
                    f'{row["profitable_fold_ratio"]:.0%}',
                    "yes" if row["promotion_ready"] else "no",
                    f'{row["composite_score"]:.2f}',
                ]
            )
            + " |"
        )

    md_path.write_text("\n".join(lines) + "\n")


def write_winner_artifacts(
    output_root: Path,
    winner: Dict,
    retrain_command: List[str],
) -> None:
    """Persist winner selection metadata and the retraining command."""
    output_root.mkdir(parents=True, exist_ok=True)

    json_path = output_root / "winner_selection.json"
    md_path = output_root / "winner_selection.md"
    script_path = output_root / "winner_retrain.sh"

    winner_payload = {
        "winner": winner,
        "retrain_command": retrain_command,
    }
    json_path.write_text(json.dumps(winner_payload, indent=2))

    markdown = [
        "# Winner Selection",
        "",
        f"- **Experiment:** `{winner['name']}`",
        f"- **Model:** `{winner['model']}`",
        f"- **Architecture:** `{winner['architecture']}`",
        f"- **Promotion ready:** `{'yes' if winner['promotion_ready'] else 'no'}`",
        f"- **Gate failures:** `{winner['gate_failures']}`",
        f"- **Composite score:** `{winner['composite_score']:.2f}`",
        f"- **Average return:** `{winner['average_total_return']:.2%}`",
        f"- **Average Sharpe:** `{winner['average_sharpe_ratio']:.2f}`",
        f"- **Average max drawdown:** `{winner['average_max_drawdown']:.2%}`",
        "",
        "## Full-data retrain command",
        "",
        "```bash",
        " ".join(retrain_command),
        "```",
    ]
    md_path.write_text("\n".join(markdown) + "\n")

    script_lines = [
        "#!/usr/bin/env bash",
        "set -euo pipefail",
        " ".join(retrain_command),
        "",
    ]
    script_path.write_text("\n".join(script_lines))
    script_path.chmod(0o755)


def print_plan(experiments: Iterable[ExperimentSpec], output_root: Path) -> None:
    """Print the experiment plan."""
    print("Recommended experiment matrix:")
    for spec in experiments:
        print(
            f"- {spec.name}: {spec.model}/{spec.architecture}, "
            f"window={spec.window_size}, walk-forward={spec.train_days}/{spec.test_days}, "
            f"timesteps_per_fold={spec.timesteps_per_fold}"
        )
    print(f"\nOutputs will be stored under: {output_root}")


def main() -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Run, summarize, and promote the RL experiment matrix")
    parser.add_argument(
        "--python-bin",
        default=sys.executable,
        help="Python interpreter to use for launching train.py",
    )
    parser.add_argument(
        "--data-path",
        type=Path,
        default=Path("./data"),
        help="Path to training data for train.py",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("./models/experiment_matrix"),
        help="Directory for experiment outputs and rankings",
    )
    parser.add_argument(
        "--symbol",
        action="append",
        default=[],
        dest="symbols",
        help="Repeatable symbol override for train.py",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually execute the experiment matrix",
    )
    parser.add_argument(
        "--summarize-only",
        action="store_true",
        help="Only summarize completed runs without printing experiment commands",
    )
    parser.add_argument(
        "--promote-winner",
        action="store_true",
        help="Select the best completed experiment and write winner artifacts",
    )
    parser.add_argument(
        "--retrain-best",
        action="store_true",
        help="Retrain the promoted winner on the full dataset",
    )
    parser.add_argument(
        "--allow-unsafe-winner",
        action="store_true",
        help="Allow promotion even if no experiment passes the promotion gates",
    )
    parser.add_argument(
        "--winner-timesteps",
        type=int,
        default=0,
        help="Override retraining timesteps for the promoted winner",
    )
    parser.add_argument(
        "--winner-optimize",
        action="store_true",
        help="Enable hyperparameter optimization during winner retraining",
    )

    args = parser.parse_args()
    args.output_root.mkdir(parents=True, exist_ok=True)

    experiments = get_experiment_matrix()
    if not args.summarize_only:
        print_plan(experiments, args.output_root)

    for spec in experiments:
        command = build_walk_forward_command(
            python_bin=args.python_bin,
            data_path=args.data_path,
            output_root=args.output_root,
            spec=spec,
            symbols=args.symbols,
        )
        if not args.summarize_only:
            print("\n$ " + " ".join(command))

        if args.execute:
            completed = subprocess.run(command, check=False)
            if completed.returncode != 0:
                print(f"Experiment failed: {spec.name}", file=sys.stderr)
                return completed.returncode

    rankings = rank_results(collect_rankings(args.output_root, experiments))
    if rankings:
        write_rankings(args.output_root, rankings)
        print(f"\nSaved ranking outputs to {args.output_root}")
        stability_rows = build_stability_report(args.output_root, experiments)
        if stability_rows:
            write_stability_report(args.output_root, stability_rows)
            print(f"Saved stability outputs to {args.output_root}")
    else:
        print(
            "\nNo walk-forward summaries found yet. Run again with --execute to generate them.",
        )

    if args.promote_winner or args.retrain_best:
        winner = select_best_winner(rankings, allow_unsafe=args.allow_unsafe_winner)
        if winner is None:
            print(
                "\nNo promotion-ready winner found. "
                "Use --allow-unsafe-winner to override the safety gates.",
                file=sys.stderr,
            )
            return 1

        winner_timesteps = args.winner_timesteps or max(
            int(winner["timesteps"]),
            DEFAULT_MIN_WINNER_TIMESTEPS,
        )
        retrain_command = build_retrain_command(
            python_bin=args.python_bin,
            data_path=args.data_path,
            output_root=args.output_root,
            winner=winner,
            symbols=args.symbols,
            winner_timesteps=winner_timesteps,
            optimize_hyperparams=args.winner_optimize,
        )
        write_winner_artifacts(args.output_root, winner, retrain_command)

        print(
            "\nPromoted winner: "
            f"{winner['name']} ({winner['model']}/{winner['architecture']})"
        )
        print("$ " + " ".join(retrain_command))

        if args.retrain_best:
            completed = subprocess.run(retrain_command, check=False)
            if completed.returncode != 0:
                print("Winner retraining failed.", file=sys.stderr)
                return completed.returncode

    return 0


if __name__ == "__main__":
    raise SystemExit(main())