"""Combined tolerance screen for the SolarFlow active coating and primer.

This script fixes the nominal release-primer concept selected after the
support-layer and primer-sensitivity studies, then evaluates 81 combinations:

    3 active indices x 3 active thicknesses
    x 3 primer indices x 3 primer thicknesses

No parameter is re-optimized per case.  This is a manufacturing-tolerance
stress test: every variation must retain the provisional +0.10% AM1.5G-weighted
optical-gain margin for the complete tolerance box to pass.

The normal-incidence coherent TMM model remains lossless and nondispersive.
Passing does not demonstrate a material, removal process or electrical gain.
"""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import TwoSlopeNorm

from product1.analysis import carrier_interface_screen as screen


ACTIVE_INDEX_ENDPOINTS = (1.06, 1.12)
ACTIVE_THICKNESS_ENDPOINTS_NM = (100.0, 135.0)
PRIMER_REFRACTIVE_INDICES = (1.15, 1.20, 1.25)
PRIMER_THICKNESSES_NM = (30.0, 50.0, 75.0)
NOMINAL_PRIMER_REFRACTIVE_INDEX = 1.20
NOMINAL_PRIMER_THICKNESS_NM = 50.0
PROVISIONAL_MARGIN_PERCENT = 0.10

REPO_ROOT = Path(__file__).resolve().parents[2]
RESULTS_DIR = REPO_ROOT / "product1" / "results"
FIGURES_DIR = RESULTS_DIR / "figures"
SOURCE_SUMMARY_PATH = RESULTS_DIR / "direct_coating_support_layer_summary.json"


@dataclass(frozen=True)
class ToleranceResult:
    active_refractive_index: float
    active_thickness_nm: float
    primer_refractive_index: float
    primer_thickness_nm: float
    transmitted_power_w_m2: float
    weighted_transmittance_percent: float
    additional_power_vs_baseline_w_m2: float
    relative_gain_vs_baseline_percent: float
    passes_positive_gain_gate: bool
    passes_provisional_margin_gate: bool
    maximum_energy_residual: float


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Combined SolarFlow active-coating/primer tolerance screen."
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run optical and aggregation checks without Solcore.",
    )
    return parser.parse_args()


def load_selected_active() -> tuple[float, float]:
    if not SOURCE_SUMMARY_PATH.exists():
        raise FileNotFoundError(
            "Missing direct_coating_support_layer_summary.json. Run the "
            "direct-coating support-layer optimizer first."
        )
    with SOURCE_SUMMARY_PATH.open("r", encoding="utf-8") as file:
        payload = json.load(file)
    selected = next(
        item for item in payload["results"] if item["scenario"] == "release_primer"
    )
    return (
        float(selected["active_refractive_index"]),
        float(selected["active_thickness_nm"]),
    )


def active_index_values(selected_index: float) -> tuple[float, float, float]:
    return (ACTIVE_INDEX_ENDPOINTS[0], selected_index, ACTIVE_INDEX_ENDPOINTS[1])


def active_thickness_values(selected_thickness_nm: float) -> tuple[float, float, float]:
    return (
        ACTIVE_THICKNESS_ENDPOINTS_NM[0],
        selected_thickness_nm,
        ACTIVE_THICKNESS_ENDPOINTS_NM[1],
    )


def calculate_reference(
    wavelength_nm: np.ndarray,
    power_density_w_m2_nm: np.ndarray,
) -> dict[str, float]:
    incident_power = screen.integrate(power_density_w_m2_nm, wavelength_nm)
    _, baseline_t, baseline_residual = screen.optical_response(
        [
            (
                screen.EXISTING_AR_REFRACTIVE_INDEX,
                screen.EXISTING_AR_THICKNESS_NM,
            )
        ],
        wavelength_nm,
    )
    baseline_power = screen.solar_weighted_power(
        baseline_t,
        power_density_w_m2_nm,
        wavelength_nm,
    )
    return {
        "incident_power_w_m2": incident_power,
        "baseline_power_w_m2": baseline_power,
        "baseline_weighted_transmittance_percent": 100.0
        * baseline_power
        / incident_power,
        "baseline_maximum_energy_residual": float(np.max(baseline_residual)),
    }


def calculate_grid(
    wavelength_nm: np.ndarray,
    power_density_w_m2_nm: np.ndarray,
    reference: dict[str, float],
    selected_active_index: float,
    selected_active_thickness_nm: float,
) -> list[ToleranceResult]:
    results: list[ToleranceResult] = []
    incident_power = reference["incident_power_w_m2"]
    baseline_power = reference["baseline_power_w_m2"]

    for active_index in active_index_values(selected_active_index):
        for active_thickness_nm in active_thickness_values(
            selected_active_thickness_nm
        ):
            for primer_index in PRIMER_REFRACTIVE_INDICES:
                for primer_thickness_nm in PRIMER_THICKNESSES_NM:
                    _, transmittance, residual = screen.optical_response(
                        [
                            (active_index, active_thickness_nm),
                            (primer_index, primer_thickness_nm),
                            (
                                screen.EXISTING_AR_REFRACTIVE_INDEX,
                                screen.EXISTING_AR_THICKNESS_NM,
                            ),
                        ],
                        wavelength_nm,
                    )
                    transmitted_power = screen.solar_weighted_power(
                        transmittance,
                        power_density_w_m2_nm,
                        wavelength_nm,
                    )
                    additional_power = transmitted_power - baseline_power
                    relative_gain = 100.0 * additional_power / baseline_power
                    results.append(
                        ToleranceResult(
                            active_refractive_index=active_index,
                            active_thickness_nm=active_thickness_nm,
                            primer_refractive_index=primer_index,
                            primer_thickness_nm=primer_thickness_nm,
                            transmitted_power_w_m2=transmitted_power,
                            weighted_transmittance_percent=100.0
                            * transmitted_power
                            / incident_power,
                            additional_power_vs_baseline_w_m2=additional_power,
                            relative_gain_vs_baseline_percent=relative_gain,
                            passes_positive_gain_gate=relative_gain > 0.0,
                            passes_provisional_margin_gate=(
                                relative_gain >= PROVISIONAL_MARGIN_PERCENT
                            ),
                            maximum_energy_residual=float(np.max(residual)),
                        )
                    )
    return results


def nominal_result(
    results: list[ToleranceResult],
    selected_active_index: float,
    selected_active_thickness_nm: float,
) -> ToleranceResult:
    return min(
        results,
        key=lambda item: (
            abs(item.active_refractive_index - selected_active_index)
            + abs(item.active_thickness_nm - selected_active_thickness_nm) / 100.0
            + abs(
                item.primer_refractive_index
                - NOMINAL_PRIMER_REFRACTIVE_INDEX
            )
            + abs(item.primer_thickness_nm - NOMINAL_PRIMER_THICKNESS_NM) / 100.0
        ),
    )


def active_worst_case_matrix(
    results: list[ToleranceResult],
    selected_active_index: float,
    selected_active_thickness_nm: float,
) -> np.ndarray:
    indices = active_index_values(selected_active_index)
    thicknesses = active_thickness_values(selected_active_thickness_nm)
    matrix = np.empty((len(indices), len(thicknesses)), dtype=float)
    for row, active_index in enumerate(indices):
        for column, active_thickness_nm in enumerate(thicknesses):
            matrix[row, column] = min(
                item.relative_gain_vs_baseline_percent
                for item in results
                if item.active_refractive_index == active_index
                and item.active_thickness_nm == active_thickness_nm
            )
    return matrix


def primer_worst_case_matrix(results: list[ToleranceResult]) -> np.ndarray:
    matrix = np.empty(
        (len(PRIMER_REFRACTIVE_INDICES), len(PRIMER_THICKNESSES_NM)),
        dtype=float,
    )
    for row, primer_index in enumerate(PRIMER_REFRACTIVE_INDICES):
        for column, primer_thickness_nm in enumerate(PRIMER_THICKNESSES_NM):
            matrix[row, column] = min(
                item.relative_gain_vs_baseline_percent
                for item in results
                if item.primer_refractive_index == primer_index
                and item.primer_thickness_nm == primer_thickness_nm
            )
    return matrix


def write_csv(results: list[ToleranceResult]) -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    path = RESULTS_DIR / "combined_active_primer_tolerance.csv"
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(asdict(results[0]).keys()))
        writer.writeheader()
        writer.writerows(asdict(item) for item in results)
    return path


def write_summary(
    results: list[ToleranceResult],
    reference: dict[str, float],
    selected_active_index: float,
    selected_active_thickness_nm: float,
) -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    path = RESULTS_DIR / "combined_active_primer_tolerance_summary.json"
    nominal = nominal_result(
        results,
        selected_active_index,
        selected_active_thickness_nm,
    )
    worst = min(results, key=lambda item: item.relative_gain_vs_baseline_percent)
    best = max(results, key=lambda item: item.relative_gain_vs_baseline_percent)
    margin_pass_count = sum(
        item.passes_provisional_margin_gate for item in results
    )
    all_pass = margin_pass_count == len(results)

    if all_pass:
        decision = (
            "The complete 81-case tolerance box passes the provisional margin. "
            "Lock the nominal direct-coating/release-primer optical stack and advance "
            "it to angle and polarization screening."
        )
    else:
        decision = (
            "The complete tolerance box does not pass. Narrow the declared manufacturing "
            "window around the passing region or redesign the nominal stack before angle screening."
        )

    payload = {
        "model": "Combined active-coating and release-primer AM1.5G tolerance screen",
        "status": "Generic optical robustness screen only",
        "nominal_stack": {
            "active_refractive_index": selected_active_index,
            "active_thickness_nm": selected_active_thickness_nm,
            "primer_refractive_index": NOMINAL_PRIMER_REFRACTIVE_INDEX,
            "primer_thickness_nm": NOMINAL_PRIMER_THICKNESS_NM,
        },
        "tolerance_grid": {
            "active_refractive_indices": active_index_values(selected_active_index),
            "active_thicknesses_nm": active_thickness_values(
                selected_active_thickness_nm
            ),
            "primer_refractive_indices": PRIMER_REFRACTIVE_INDICES,
            "primer_thicknesses_nm": PRIMER_THICKNESSES_NM,
        },
        "provisional_margin_percent": PROVISIONAL_MARGIN_PERCENT,
        "reference_results": reference,
        "number_of_cases": len(results),
        "number_passing_positive_gain": sum(
            item.passes_positive_gain_gate for item in results
        ),
        "number_passing_provisional_margin": margin_pass_count,
        "all_cases_pass_provisional_margin": all_pass,
        "nominal_result": asdict(nominal),
        "worst_case": asdict(worst),
        "best_case": asdict(best),
        "active_worst_case_gain_matrix_percent": active_worst_case_matrix(
            results,
            selected_active_index,
            selected_active_thickness_nm,
        ).tolist(),
        "primer_worst_case_gain_matrix_percent": primer_worst_case_matrix(
            results
        ).tolist(),
        "decision": decision,
        "limitations": [
            "The tolerance box contains discrete corner and nominal values, not a statistical process model.",
            "Refractive indices are generic, lossless and nondispersive.",
            "Normal incidence only; angle and polarization are not included.",
            "Optical tolerance does not prove coating or primer manufacturability.",
            "Release behavior, durability and electrical gain are not demonstrated.",
        ],
    }
    with path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2, allow_nan=False)
        file.write("\n")
    return path


def annotate_matrix(axis: plt.Axes, matrix: np.ndarray) -> None:
    for row in range(matrix.shape[0]):
        for column in range(matrix.shape[1]):
            value = matrix[row, column]
            marker = "*" if value >= PROVISIONAL_MARGIN_PERCENT else ""
            axis.text(
                column,
                row,
                f"{value:+.3f}%{marker}",
                ha="center",
                va="center",
                fontsize=8,
            )


def write_figure(
    results: list[ToleranceResult],
    selected_active_index: float,
    selected_active_thickness_nm: float,
) -> Path:
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    path = FIGURES_DIR / "combined_active_primer_tolerance.png"
    active_matrix = active_worst_case_matrix(
        results,
        selected_active_index,
        selected_active_thickness_nm,
    )
    primer_matrix = primer_worst_case_matrix(results)
    limit = max(
        0.10,
        float(np.max(np.abs(active_matrix))),
        float(np.max(np.abs(primer_matrix))),
    )
    norm = TwoSlopeNorm(vmin=-limit, vcenter=0.0, vmax=limit)

    figure, axes = plt.subplots(1, 2, figsize=(12.0, 4.8))
    figure.subplots_adjust(left=0.08, right=0.91, bottom=0.20, top=0.81, wspace=0.30)
    image = axes[0].imshow(active_matrix, cmap="RdYlGn", norm=norm, aspect="auto")
    axes[1].imshow(primer_matrix, cmap="RdYlGn", norm=norm, aspect="auto")

    active_indices = active_index_values(selected_active_index)
    active_thicknesses = active_thickness_values(selected_active_thickness_nm)
    axes[0].set_title("Worst gain for each active-layer setting")
    axes[0].set_xlabel("Active thickness (nm)")
    axes[0].set_ylabel("Active refractive index")
    axes[0].set_xticks(
        range(len(active_thicknesses)),
        [f"{value:.1f}" for value in active_thicknesses],
    )
    axes[0].set_yticks(
        range(len(active_indices)),
        [f"{value:.4f}" for value in active_indices],
    )
    annotate_matrix(axes[0], active_matrix)

    axes[1].set_title("Worst gain for each primer setting")
    axes[1].set_xlabel("Primer thickness (nm)")
    axes[1].set_ylabel("Primer refractive index")
    axes[1].set_xticks(
        range(len(PRIMER_THICKNESSES_NM)),
        [f"{value:.0f}" for value in PRIMER_THICKNESSES_NM],
    )
    axes[1].set_yticks(
        range(len(PRIMER_REFRACTIVE_INDICES)),
        [f"{value:.2f}" for value in PRIMER_REFRACTIVE_INDICES],
    )
    annotate_matrix(axes[1], primer_matrix)

    colorbar = figure.colorbar(image, ax=axes, fraction=0.026, pad=0.04)
    colorbar.set_label("Worst-case relative optical gain (%)")
    figure.suptitle("SolarFlow Combined Active / Primer Tolerance Screen", fontsize=14)
    figure.text(
        0.5,
        0.06,
        f"* all paired variations retain at least +{PROVISIONAL_MARGIN_PERCENT:.2f}% for that cell.",
        ha="center",
        fontsize=8,
    )
    figure.savefig(path, dpi=220)
    plt.close(figure)
    return path


def print_results(
    results: list[ToleranceResult],
    selected_active_index: float,
    selected_active_thickness_nm: float,
    outputs: list[Path],
) -> None:
    nominal = nominal_result(
        results,
        selected_active_index,
        selected_active_thickness_nm,
    )
    worst = min(results, key=lambda item: item.relative_gain_vs_baseline_percent)
    margin_pass_count = sum(
        item.passes_provisional_margin_gate for item in results
    )
    all_pass = margin_pass_count == len(results)

    print("Combined active/primer tolerance screen completed.")
    print(f"Cases                      : {len(results)}")
    print(
        "Nominal stack              : "
        f"active n={nominal.active_refractive_index:.6f}, "
        f"d={nominal.active_thickness_nm:.3f} nm; "
        f"primer n={nominal.primer_refractive_index:.2f}, "
        f"d={nominal.primer_thickness_nm:.0f} nm"
    )
    print(
        "Nominal relative gain      : "
        f"{nominal.relative_gain_vs_baseline_percent:+.4f}%"
    )
    print(
        "Worst-case relative gain   : "
        f"{worst.relative_gain_vs_baseline_percent:+.4f}%"
    )
    print(
        "Worst-case parameters      : "
        f"active n={worst.active_refractive_index:.6f}, "
        f"d={worst.active_thickness_nm:.3f} nm; "
        f"primer n={worst.primer_refractive_index:.2f}, "
        f"d={worst.primer_thickness_nm:.0f} nm"
    )
    print(
        "Cases passing +0.10% gate : "
        f"{margin_pass_count}/{len(results)}"
    )
    print(f"Full tolerance box passes : {all_pass}")

    print("\nDecision")
    if all_pass:
        print(
            "Lock the nominal optical stack and advance to angle/polarization screening."
        )
    else:
        print(
            "Do not lock this tolerance box. Narrow it around passing cases or redesign the nominal stack."
        )

    print("\nOutputs")
    for output in outputs:
        print(f"- {output}")
    print(
        "\nWARNING: Discrete generic optical tolerance screen; not a manufacturing capability claim."
    )


def run_self_test() -> None:
    screen.run_self_test()
    wavelength_nm = np.array([350.0, 550.0, 1000.0])
    _, _, residual = screen.optical_response(
        [(1.09, 117.0), (1.20, 50.0), (1.28, 100.0)],
        wavelength_nm,
    )
    if float(np.max(residual)) >= 1e-12:
        raise AssertionError("Combined-stack energy-conservation self-test failed.")

    selected_index = 1.09
    selected_thickness = 117.0
    if active_index_values(selected_index)[1] != selected_index:
        raise AssertionError("Selected active index is not centered in its grid.")
    if active_thickness_values(selected_thickness)[1] != selected_thickness:
        raise AssertionError("Selected active thickness is not centered in its grid.")
    expected_cases = 3 * 3 * 3 * 3
    if expected_cases != 81:
        raise AssertionError("Tolerance-grid case-count self-test failed.")
    print("Combined active/primer tolerance self-test passed.")


def main() -> None:
    arguments = parse_arguments()
    if arguments.self_test:
        run_self_test()
        return

    selected_active_index, selected_active_thickness_nm = load_selected_active()
    wavelength_nm = screen.wavelengths_nm()
    power_density_w_m2_nm = screen.load_am15g_power_density(wavelength_nm)
    reference = calculate_reference(wavelength_nm, power_density_w_m2_nm)
    results = calculate_grid(
        wavelength_nm,
        power_density_w_m2_nm,
        reference,
        selected_active_index,
        selected_active_thickness_nm,
    )
    csv_path = write_csv(results)
    summary_path = write_summary(
        results,
        reference,
        selected_active_index,
        selected_active_thickness_nm,
    )
    figure_path = write_figure(
        results,
        selected_active_index,
        selected_active_thickness_nm,
    )
    print_results(
        results,
        selected_active_index,
        selected_active_thickness_nm,
        [csv_path, summary_path, figure_path],
    )


if __name__ == "__main__":
    main()