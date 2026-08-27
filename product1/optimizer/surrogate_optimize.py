"""Dry-run optimizer for workflow testing.

IMPORTANT: This is a software-pipeline test only. It is NOT a physical solar
model and its scores must never be presented as research evidence.
"""
from __future__ import annotations

import argparse
import json
import math
import random
from pathlib import Path


def surrogate_score(height_nm: float, width_nm: float, period_nm: float) -> float:
    # A deliberately simple smooth landscape for testing the optimizer UI.
    a = math.exp(-((height_nm - 240.0) / 110.0) ** 2)
    b = math.exp(-((width_nm - 260.0) / 150.0) ** 2)
    c = math.exp(-((period_nm - 620.0) / 220.0) ** 2)
    return 0.75 + 0.20 * (a * b * c)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", type=int, default=25)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", type=Path, default=Path("results/surrogate_best.json"))
    args = ap.parse_args()

    rng = random.Random(args.seed)
    best = None
    history = []
    for i in range(args.trials):
        d = {
            "height_nm": rng.uniform(50, 500),
            "width_nm": rng.uniform(50, 500),
            "period_nm": rng.uniform(250, 1000),
        }
        score = surrogate_score(**d)
        row = {"trial": i + 1, **d, "score": score}
        history.append(row)
        if best is None or score > best["score"]:
            best = row

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({"WARNING": "surrogate only", "best": best, "history": history}, indent=2))
    print(json.dumps(best, indent=2))


if __name__ == "__main__":
    main()
