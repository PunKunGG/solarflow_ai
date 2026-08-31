"""Map the optical tolerance of the optimized SolarFlow release primer.

The support-layer optimizer selected a release primer at both lower search
bounds (approximately n=1.20 and d=20 nm).  This script does not re-optimize
the active coating.  It fixes the selected active layer and sweeps primer
index/thickness to reveal whether a useful positive-gain operating window
exists or whether the optimizer merely tried to make the primer disappear.

The calculation is an AM1.5G-weighted, normal-incidence, coherent, lossless,
nondispersive TMM screen.  Generic refractive indices are not materials.
"""

from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import TwoSlopeNorm

from product1.analysis import carrier_interface_screen as screen


PRIMER_REFRACTIVE_INDICES = (1.05, 1.10, 1.15, 1.20, 1.25, 1.30, 1.35, 1.40)
PRIMER_THICKNESSES_NM = (0.0, 5.0, 10.0, 20.0, 30.0, 50.0, 75.0, 100.0, 150.0)
PROVISIONAL_MARGIN_PERCENT = 0.10

REPO_ROOT = Path(__file__).resolve().parents[2]
RESULTS_DIR = REPO_ROOT / "product1" / "results"
FIGURES_DIR = RESULTS_DIR / "figures"
SOURCE_SUMMARY_PATH = RESULTS_DIR / "direct_coating_support_layer_summary.json"


@dataclass(frozen=True)
class SensitivityResult:
    primer_refractive_index: float
    primer_thickness_nm: float
    transmitted_power_w_m2: float
    weighted_transmittance_percent: float
    additional_power_vs_baseline_w_m2: float
    relative_gain_vs_baseline_percent: float
    passes_positive_gain_gate: bool
    passes_provisional_margin_gate: bool
    maximum_energy_residual: float


def load_selected_candidate() -> dict[str, float]:
    if not SOURCE_SUMMARY_PATH.exists():
        raise FileNotFoundError(
            "Missing direct_coating_support_layer_summary.json. Run "
            "product1.optimizer.optimize_direct_coating_layers first."
        )

    with SOURCE_SUMMARY_PATH.open("r", encoding="utf-8") as file:
        payload = json.load(file)
    selected = next(
        item for item in payload["results"] if item["scenario"] == "release_primer"
    )
    required = (
        "active_refractive_index",
        "active_thickness_nm",
        "release_refractive_index",
        "release_thickness_nm",
    )
    if any(selected.get(key) is None for key in required):
        raise RuntimeError("The release-primer candidate is incomplete in the source summary.")
    return {key: float(selected[key]) for key in required}


def calculate_reference(
    wavelength_nm: np.ndarray,
    power_density_w_m2_nm: np.ndarray,
    active_refractive_index: float,
    active_thickness_nm: float,
) -> tuple[dict[str, float], dict[str, np.ndarray]]:
    incident_power = screen.integrate(power_density_w_m2_nm, wavelength_nm)
    baseline_r, baseline_t, baseline_residual = screen.optical_response(
        [
            (
                screen.EXISTING_AR_REFRACTIVE_INDEX,
                screen.EXISTING_AR_THICKNESS_NM,
            )
        ],
        wavelength_nm,
    )
    active_r, active_t, active_residual = screen.optical_response(
        [
            (active_refractive_index, active_thickness_nm),
            (
                screen.EXISTING_AR_REFRACTIVE_INDEX,
                screen.EXISTING_AR_THICKNESS_NM,
            ),
        ],
        wavelength_nm,
    )
    baseline_power = screen.solar_weighted_power(
        baseline_t,
        power_density_w_m2_nm,
        wavelength_nm,
    )
    active_power = screen.solar_weighted_power(
        active_t,
        power_density_w_m2_nm,
        wavelength_nm,
    )
    reference = {
        "incident_power_w_m2": incident_power,
        "baseline_power_w_m2": baseline_power,
        "fixed_active_power_w_m2": active_power,
        "fixed_active_relative_gain_percent": 100.0
        * (active_power - baseline_power)
        / baseline_power,
        "baseline_maximum_energy_residual": float(np.max(baseline_residual)),
        "fixed_active_maximum_energy_residual": float(np.max(active_residual)),
    }
    spectra = {
        "baseline_reflectance": baseline_r,
        "baseline_transmittance": baseline_t,
        "fixed_active_reflectance": active_r,
        "fixed_active_transmittance": active_t,
    }
    return reference, spectra


def calculate_grid(
    wavelength_nm: np.ndarray,
    power_density_w_m2_nm: np.ndarray,
    selected: dict[str, float],
    reference: dict[str, float],
) -> tuple[list[SensitivityResult], dict[tuple[float, float], np.ndarray]]:
    incident_power = reference["incident_power_w_m2"]
    baseline_power = reference["baseline_power_w_m2"]
    results: list[SensitivityResult] = []
    spectra: dict[tuple[float, float], np.ndarray] = {}

    for primer_index in PRIMER_REFRACTIVE_INDICES:
        for primer_thickness_nm in PRIMER_THICKNESSES_NM:
            _, transmittance, residual = screen.optical_response(
                [
                    (
                        selected["active_refractive_index"],
                        selected["active_thickness_nm"],
                    ),
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
            result = SensitivityResult(
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
            results.append(result)
            spectra[(primer_index, primer_thickness_nm)] = transmittance

    return results, spectra


def result_matrix(results: list[SensitivityResult]) -> np.ndarray:
    matrix = np.empty(
        (len(PRIMER_REFRACTIVE_INDICES), len(PRIMER_THICKNESSES_NM)),
        dtype=float,
    )
    for result in results:
        row = PRIMER_REFRACTIVE_INDICES.index(result.primer_refractive_index)
        column = PRIMER_THICKNESSES_NM.index(result.primer_thickness_nm)
        matrix[row, column] = result.relative_gain_vs_baseline_percent
    return matrix


def nearest_grid_result(
    results: list[SensitivityResult],
    primer_index: float,
    primer_thickness_nm: float,
) -> SensitivityResult:
    return min(
        results,
        key=lambda item: (
            abs(item.primer_refractive_index - primer_index)
            + abs(item.primer_thickness_nm - primer_thickness_nm) / 100.0
        ),
    )


def maximum_passing_thickness_by_index(
    results: list[SensitivityResult],
) -> dict[str, float | None]:
    output: dict[str, float | None] = {}
    for primer_index in PRIMER_REFRACTIVE_INDICES:
        passing = [
            item.primer_thickness_nm
            for item in results
            if item.primer_refractive_index == primer_index
            and item.passes_provisional_margin_gate
        ]
        output[f"{primer_index:.2f}"] = max(passing) if passing else None
    return output


def write_csv(results: list[SensitivityResult]) -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    path = RESULTS_DIR / "release_primer_sensitivity.csv"
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(asdict(results[0]).keys()))
        writer.writeheader()
        writer.writerows(asdict(item) for item in results)
    return path


def write_summary(
    results: list[SensitivityResult],
    selected: dict[str, float],
    reference: dict[str, float],
) -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    path = RESULTS_DIR / "release_primer_sensitivity_summary.json"
    closest = nearest_grid_result(
        results,
        selected["release_refractive_index"],
        selected["release_thickness_nm"],
    )
    passing = [item for item in results if item.passes_provisional_margin_gate]
    nonzero_passing = [item for item in passing if item.primer_thickness_nm > 0.0]
    passing_at_least_50 = [
        item for item in passing if item.primer_thickness_nm >= 50.0
    ]
    maximum_by_index = maximum_passing_thickness_by_index(results)

    if passing_at_least_50:
        decision = (
            "A nonzero primer window extends to at least 50 nm in the generic grid. "
            "Select a conservative interior candidate and test active-layer and primer tolerances."
        )
    elif nonzero_passing:
        decision = (
            "Only an ultrathin primer window retains the provisional margin. Treat removability "
            "as a material/process hypothesis and do not claim a robust release layer yet."
        )
    else:
        decision = (
            "No nonzero primer case retains the provisional margin. The optimizer was effectively "
            "removing the primer; redesign the removal mechanism."
        )

    payload = {
        "model": "Fixed-active release-primer AM1.5G TMM sensitivity screen",
        "status": "Generic optical feasibility only",
        "fixed_selected_candidate": selected,
        "primer_refractive_indices": PRIMER_REFRACTIVE_INDICES,
        "primer_thicknesses_nm": PRIMER_THICKNESSES_NM,
        "provisional_margin_percent": PROVISIONAL_MARGIN_PERCENT,
        "reference_results": reference,
        "closest_grid_point_to_optimizer": asdict(closest),
        "number_of_cases": len(results),
        "number_passing_positive_gain": sum(
            item.passes_positive_gain_gate for item in results
        ),
        "number_passing_provisional_margin": len(passing),
        "number_nonzero_primer_cases_passing_margin": len(nonzero_passing),
        "any_case_at_or_above_50nm_passing_margin": bool(passing_at_least_50),
        "maximum_passing_thickness_nm_by_primer_index": maximum_by_index,
        "best_case": asdict(
            max(results, key=lambda item: item.relative_gain_vs_baseline_percent)
        ),
        "worst_case": asdict(
            min(results, key=lambda item: item.relative_gain_vs_baseline_percent)
        ),
        "decision": decision,
        "limitations": [
            "The active coating is fixed at one optimized candidate.",
            "Primer indices are generic, lossless and nondispersive.",
            "Thickness 0 nm is a no-primer optical control, not a product layer.",
            "Normal incidence only; angle and polarization are not included.",
            "Passing optics does not prove adhesion, release behavior or durability.",
        ],
    }
    with path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2, allow_nan=False)
        file.write("\n")
    return path


def write_heatmap(
    results: list[SensitivityResult],
    selected: dict[str, float],
) -> Path:
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    path = FIGURES_DIR / "release_primer_sensitivity_heatmap.png"
    matrix = result_matrix(results)
    limit = float(np.max(np.abs(matrix)))
    if limit == 0.0:
        limit = 1.0

    figure, axis = plt.subplots(figsize=(10.0, 5.5))
    image = axis.imshow(
        matrix,
        cmap="RdYlGn",
        norm=TwoSlopeNorm(vmin=-limit, vcenter=0.0, vmax=limit),
        aspect="auto",
    )
    axis.set_title("SolarFlow Release-Primer Sensitivity — Fixed Active Coating")
    axis.set_xlabel("Generic primer thickness (nm)")
    axis.set_ylabel("Generic primer refractive index")
    axis.set_xticks(
        range(len(PRIMER_THICKNESSES_NM)),
        [f"{value:.0f}" for value in PRIMER_THICKNESSES_NM],
    )
    axis.set_yticks(
        range(len(PRIMER_REFRACTIVE_INDICES)),
        [f"{value:.2f}" for value in PRIMER_REFRACTIVE_INDICES],
    )

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
                fontsize=6.8,
            )

    selected_row = min(
        range(len(PRIMER_REFRACTIVE_INDICES)),
        key=lambda position: abs(
            PRIMER_REFRACTIVE_INDICES[position]
            - selected["release_refractive_index"]
        ),
    )
    selected_column = min(
        range(len(PRIMER_THICKNESSES_NM)),
        key=lambda position: abs(
            PRIMER_THICKNESSES_NM[position]
            - selected["release_thickness_nm"]
        ),
    )
    axis.scatter(
        [selected_column],
        [selected_row],
        marker="s",
        s=170,
        facecolors="none",
        edgecolors="#1565c0",
        linewidths=2.0,
        label="Nearest grid point to optimizer",
    )
    axis.legend(loc="upper right", fontsize=8)
    colorbar = figure.colorbar(image, ax=axis)
    colorbar.set_label("AM1.5G-weighted relative optical gain (%)")
    figure.text(
        0.5,
        0.015,
        f"* passes provisional +{PROVISIONAL_MARGIN_PERCENT:.2f}% margin; 0 nm is the no-primer control.",
        ha="center",
        fontsize=8,
    )
    figure.tight_layout(rect=(0.0, 0.04, 1.0, 1.0))
    figure.savefig(path, dpi=220)
    plt.close(figure)
    return path


def print_results(
    results: list[SensitivityResult],
    selected: dict[str, float],
    reference: dict[str, float],
    outputs: list[Path],
) -> None:
    closest = nearest_grid_result(
        results,
        selected["release_refractive_index"],
        selected["release_thickness_nm"],
    )
    maximum_by_index = maximum_passing_thickness_by_index(results)
    print("Release-primer sensitivity screen completed.")
    print(
        "Fixed active coating       : "
        f"n={selected['active_refractive_index']:.6f}, "
        f"d={selected['active_thickness_nm']:.3f} nm"
    )
    print(
        "Optimizer primer          : "
        f"n={selected['release_refractive_index']:.6f}, "
        f"d={selected['release_thickness_nm']:.3f} nm"
    )
    print(
        "Fixed-active no-primer gain: "
        f"{reference['fixed_active_relative_gain_percent']:+.4f}%"
    )
    print(
        "Nearest grid-point gain   : "
        f"{closest.relative_gain_vs_baseline_percent:+.4f}% "
        f"at n={closest.primer_refractive_index:.2f}, "
        f"d={closest.primer_thickness_nm:.0f} nm\n"
    )
    print("Maximum primer thickness passing +0.10% margin")
    for primer_index, thickness in maximum_by_index.items():
        text = f"{thickness:.0f} nm" if thickness is not None else "none"
        print(f"  n={primer_index}: {text}")

    passing_50 = any(
        item.passes_provisional_margin_gate
        and item.primer_thickness_nm >= 50.0
        for item in results
    )
    print("\nDecision")
    if passing_50:
        print(
            "A primer window reaches at least 50 nm. Select an interior candidate "
            "for combined active/primer tolerance testing."
        )
    else:
        print(
            "The passing primer window is ultrathin or absent. Do not claim a robust "
            "release layer; treat removability as a material/process hypothesis."
        )

    print("\nOutputs")
    for output in outputs:
        print(f"- {output}")
    print(
        "\nWARNING: Optical sensitivity only. Passing does not demonstrate physical release behavior."
    )


def main() -> None:
    selected = load_selected_candidate()
    wavelength_nm = screen.wavelengths_nm()
    power_density_w_m2_nm = screen.load_am15g_power_density(wavelength_nm)
    reference, _ = calculate_reference(
        wavelength_nm,
        power_density_w_m2_nm,
        selected["active_refractive_index"],
        selected["active_thickness_nm"],
    )
    results, _ = calculate_grid(
        wavelength_nm,
        power_density_w_m2_nm,
        selected,
        reference,
    )
    csv_path = write_csv(results)
    summary_path = write_summary(results, selected, reference)
    heatmap_path = write_heatmap(results, selected)
    print_results(
        results,
        selected,
        reference,
        [csv_path, summary_path, heatmap_path],
    )


if __name__ == "__main__":
    main()
