from __future__ import annotations

import csv
import json
from pathlib import Path

import baseline_glass as baseline


RESOLUTIONS = (50, 100, 200)

OUTPUT_DIRECTORY = (
    Path(__file__).resolve().parents[1]
    / "results"
    / "convergence"
)

SUMMARY_CSV_PATH = OUTPUT_DIRECTORY / "baseline_convergence.csv"
SUMMARY_JSON_PATH = OUTPUT_DIRECTORY / "baseline_convergence.json"


def main() -> None:
    OUTPUT_DIRECTORY.mkdir(parents=True, exist_ok=True)

    summaries = []

    for resolution in RESOLUTIONS:
        print()
        print("=" * 60)
        print(f"Running resolution = {resolution} pixels/um")
        print("=" * 60)

        baseline.RESOLUTION = resolution
        baseline.CSV_PATH = (
            OUTPUT_DIRECTORY
            / f"baseline_glass_res_{resolution}.csv"
        )
        baseline.SUMMARY_PATH = (
            OUTPUT_DIRECTORY
            / f"baseline_glass_res_{resolution}_summary.json"
        )

        baseline.main()

        with baseline.SUMMARY_PATH.open(
            "r",
            encoding="utf-8",
        ) as summary_file:
            summaries.append(json.load(summary_file))

    with SUMMARY_CSV_PATH.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(
            [
                "resolution_pixels_per_um",
                "mean_reflectance",
                "mean_transmittance",
                "maximum_fresnel_error",
                "maximum_energy_residual",
            ]
        )

        for summary in summaries:
            writer.writerow(
                [
                    summary["resolution_pixels_per_um"],
                    summary["mean_reflectance"],
                    summary["mean_transmittance"],
                    summary["maximum_fresnel_error"],
                    summary["maximum_energy_residual"],
                ]
            )

    reflectance_change = abs(
        summaries[-1]["mean_reflectance"]
        - summaries[-2]["mean_reflectance"]
    )

    convergence_result = {
        "resolutions": list(RESOLUTIONS),
        "summaries": summaries,
        "reflectance_change_100_to_200": reflectance_change,
        "passes_initial_tolerance": (
            reflectance_change < 5e-4
            and summaries[-1]["maximum_fresnel_error"] < 1e-3
            and summaries[-1]["maximum_energy_residual"] < 1e-3
        ),
    }

    with SUMMARY_JSON_PATH.open(
        "w",
        encoding="utf-8",
    ) as json_file:
        json.dump(convergence_result, json_file, indent=2)

    print()
    print("Convergence summary")
    print("-" * 60)

    for summary in summaries:
        print(
            f"Resolution {summary['resolution_pixels_per_um']:>3}: "
            f"R={summary['mean_reflectance']:.6f}, "
            f"Fresnel error="
            f"{summary['maximum_fresnel_error']:.6e}, "
            f"energy error="
            f"{summary['maximum_energy_residual']:.6e}"
        )

    print("-" * 60)
    print(
        "R change 100 -> 200: "
        f"{reflectance_change:.6e}"
    )
    print(
        "Passes tolerance: "
        f"{convergence_result['passes_initial_tolerance']}"
    )
    print(f"Summary CSV: {SUMMARY_CSV_PATH}")
    print(f"Summary JSON: {SUMMARY_JSON_PATH}")


if __name__ == "__main__":
    main()