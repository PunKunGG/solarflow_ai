"""Generic optimization harness.

By default this file uses a user-provided simulator function. It is deliberately
not coupled to an invented physical score. Connect `evaluate_design()` to the
real MEEP/physics pipeline before reporting any result.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def evaluate_design(height_nm: float, width_nm: float, period_nm: float) -> float:
    """Placeholder: replace with a REAL simulator call.

    Return a scalar objective where larger is better.
    """
    raise RuntimeError(
        "No physical objective is wired here yet. Connect this function to the validated MEEP pipeline."
    )


def main() -> None:
    import optuna

    parser = argparse.ArgumentParser()
    parser.add_argument("--trials", type=int, default=50)
    parser.add_argument("--out", type=Path, default=Path("results/optuna_trials.json"))
    args = parser.parse_args()

    def objective(trial: Any) -> float:
        height = trial.suggest_float("height_nm", 50.0, 500.0)
        width = trial.suggest_float("width_nm", 50.0, 500.0)
        period = trial.suggest_float("period_nm", 250.0, 1000.0)
        return evaluate_design(height, width, period)

    study = optuna.create_study(direction="maximize")
    study.optimize(objective, n_trials=args.trials)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "best_value": study.best_value,
        "best_params": study.best_params,
        "n_trials": len(study.trials),
        "status": "PHYSICAL_OBJECTIVE_REQUIRED",
    }
    args.out.write_text(json.dumps(payload, indent=2))
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
