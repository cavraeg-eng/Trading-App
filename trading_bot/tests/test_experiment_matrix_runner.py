import json
import subprocess
from pathlib import Path


def _write_summary(path: Path, payload: dict) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "walk_forward_summary.json").write_text(json.dumps(payload))


def _write_folds(path: Path, rows: list[dict]) -> None:
    path.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "fold",
        "total_return",
        "sharpe_ratio",
        "max_drawdown",
        "win_rate",
        "num_trades",
    ]
    lines = [",".join(fieldnames)]
    for row in rows:
        lines.append(",".join(str(row.get(field, "")) for field in fieldnames))
    (path / "walk_forward_results.csv").write_text("\n".join(lines) + "\n")


def test_experiment_matrix_summary_and_promotion(tmp_path: Path):
    output_root = tmp_path / "experiment_matrix"

    _write_summary(
        output_root / "ppo_lstm_baseline",
        {
            "num_folds": 3,
            "average_total_return": 0.14,
            "average_sharpe_ratio": 1.2,
            "average_max_drawdown": 0.12,
            "average_win_rate": 0.57,
            "average_num_trades": 11,
            "profitable_fold_ratio": 0.67,
            "composite_score": 14.3,
        },
    )
    _write_folds(
        output_root / "ppo_lstm_baseline",
        [
            {"fold": 1, "total_return": 0.12, "sharpe_ratio": 1.1, "max_drawdown": 0.10, "win_rate": 0.56, "num_trades": 10},
            {"fold": 2, "total_return": 0.18, "sharpe_ratio": 1.4, "max_drawdown": 0.13, "win_rate": 0.58, "num_trades": 12},
            {"fold": 3, "total_return": 0.11, "sharpe_ratio": 1.0, "max_drawdown": 0.11, "win_rate": 0.57, "num_trades": 11},
        ],
    )
    _write_summary(
        output_root / "sac_transformer_regime",
        {
            "num_folds": 3,
            "average_total_return": 0.05,
            "average_sharpe_ratio": -0.1,
            "average_max_drawdown": 0.31,
            "average_win_rate": 0.49,
            "average_num_trades": 4,
            "profitable_fold_ratio": 0.33,
            "composite_score": 2.1,
        },
    )
    _write_folds(
        output_root / "sac_transformer_regime",
        [
            {"fold": 1, "total_return": -0.03, "sharpe_ratio": -0.2, "max_drawdown": 0.28, "win_rate": 0.45, "num_trades": 3},
            {"fold": 2, "total_return": 0.10, "sharpe_ratio": 0.1, "max_drawdown": 0.31, "win_rate": 0.50, "num_trades": 4},
            {"fold": 3, "total_return": 0.08, "sharpe_ratio": -0.1, "max_drawdown": 0.34, "win_rate": 0.52, "num_trades": 5},
        ],
    )

    result = subprocess.run(
        [
            "python3",
            "run_experiment_matrix.py",
            "--output-root",
            str(output_root),
            "--summarize-only",
            "--promote-winner",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "Promoted winner: ppo_lstm_baseline" in result.stdout

    ranking_csv = output_root / "experiment_ranking.csv"
    stability_md = output_root / "experiment_stability.md"
    winner_json = output_root / "winner_selection.json"
    winner_script = output_root / "winner_retrain.sh"

    assert ranking_csv.exists()
    assert stability_md.exists()
    assert winner_json.exists()
    assert winner_script.exists()

    winner_payload = json.loads(winner_json.read_text())
    assert winner_payload["winner"]["name"] == "ppo_lstm_baseline"
    assert winner_payload["winner"]["promotion_ready"] is True
    assert "--architecture lstm" in " ".join(winner_payload["retrain_command"])


def test_experiment_matrix_requires_safe_winner_without_override(tmp_path: Path):
    output_root = tmp_path / "experiment_matrix"

    _write_summary(
        output_root / "sac_transformer_regime",
        {
            "num_folds": 3,
            "average_total_return": 0.02,
            "average_sharpe_ratio": -0.2,
            "average_max_drawdown": 0.4,
            "average_win_rate": 0.4,
            "average_num_trades": 2,
            "profitable_fold_ratio": 0.33,
            "composite_score": 0.8,
        },
    )
    _write_folds(
        output_root / "sac_transformer_regime",
        [
            {"fold": 1, "total_return": -0.05, "sharpe_ratio": -0.4, "max_drawdown": 0.39, "win_rate": 0.42, "num_trades": 2},
            {"fold": 2, "total_return": 0.03, "sharpe_ratio": -0.1, "max_drawdown": 0.41, "win_rate": 0.38, "num_trades": 2},
            {"fold": 3, "total_return": 0.08, "sharpe_ratio": -0.1, "max_drawdown": 0.40, "win_rate": 0.40, "num_trades": 2},
        ],
    )

    result = subprocess.run(
        [
            "python3",
            "run_experiment_matrix.py",
            "--output-root",
            str(output_root),
            "--summarize-only",
            "--promote-winner",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "No promotion-ready winner found" in result.stderr