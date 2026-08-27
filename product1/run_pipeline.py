"""One-command Product 1 dry-run.

Runs the software workflow without pretending MEEP/Solcore/DEVSIM are present.
Use this to verify the project plumbing; replace the surrogate stage with the
real simulators once installed.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main() -> None:
    out = ROOT / "results" / "surrogate_best.json"
    subprocess.run([
        sys.executable,
        str(ROOT / "optimizer" / "surrogate_optimize.py"),
        "--trials", "25",
        "--out", str(out),
    ], check=True)
    print(f"Dry-run complete: {out}")
    print("IMPORTANT: replace surrogate stage with real MEEP/Solcore/DEVSIM before using any result scientifically.")


if __name__ == "__main__":
    main()
