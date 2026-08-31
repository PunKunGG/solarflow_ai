"""Reproduce the SolarFlow 550 nm existing-AR sensitivity screen.

Model
-----
Normal-incidence, coherent, lossless thin-film transfer matrix:

Baseline: air -> existing AR -> glass
Retrofit: air -> retrofit layer -> existing AR -> glass

This is a single-wavelength screening calculation.  It is not the validated
300-1200 nm AM1.5G Meep/TMM calculation and is not an electrical-power model.
"""

from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import TwoSlopeNorm


WAVELENGTH_NM = 550.0
AIR_REFRACTIVE_INDEX = 1.0
GLASS_REFRACTIVE_INDEX = 1.52

RETROFIT_REFRACTIVE_INDEX = 1.100474
RETROFIT_THICKNESS_NM = 118.791

EXISTING_AR_REFRACTIVE_INDICES = (1.25, 1.28, 1.30, 1.35)
EXISTING_AR_THICKNESSES_NM = (80.0, 100.0, 120.0, 140.0)

REPO_ROOT = Path(__file__).resolve().parents[2]
RESULTS_DIR = REPO_ROOT / "product1" / "results"
FIGURES_DIR = RESULTS_DIR / "figures"


# Values printed in the collaborating-team document, rounded to four decimals.
# They are used only as a regression check, not as calculation inputs.
DOCUMENT_REFERENCE = {
    (1.25, 80.0): (99.2229, 99.3337, 0.1117),
    (1.25, 100.0): (99.8914, 99.3628, -0.5292),
    (1.25, 120.0): (99.8914, 99.2819, -0.6102),
    (1.25, 140.0): (99.2229, 99.1172, -0.1065),
    (1.28, 80.0): (99.2094, 99.6061, 0.3998),
    (1.28, 100.0): (99.8091, 99.6787, -0.1306),
    (1.28, 120.0): (99.7160, 99.5848, -0.1316),
    (1.28, 140.0): (98.9645, 99.3564, 0.3960),
    (1.30, 80.0): (99.1451, 99.7399, 0.5999),
    (1.30, 100.0): (99.6892, 99.8285, 0.1397),
    (1.30, 120.0): (99.5376, 99.7201, 0.1834),
    (1.30, 140.0): (98.7476, 99.4529, 0.7143),
    (1.35, 80.0): (98.7930, 99.9045, 1.1251),
    (1.35, 100.0): (99.1780, 99.9965, 0.8253),
    (1.35, 120.0): (98.9098, 99.8464, 0.9469),
    (1.35, 140.0): (98.0957, 99.5111, 1.4428),
}


@dataclass(frozen=True)
class Result:
    existing_ar_refractive_index: float
    existing_ar_thickness_nm: float
    baseline_reflectance_percent: float
    baseline_transmittance_percent: float
    retrofit_reflectance_percent: float
    retrofit_transmittance_percent: float
    absolute_change_percentage_points: float
    relative_change_percent: float
    baseline_energy_residual: float
    retrofit_energy_residual: float


def layer_matrix(refractive_index: float, thickness_nm: float, wavelength_nm: float) -> np.ndarray:
    """Return the 2x2 characteristic matrix of one lossless layer."""
    phase = 2.0 * np.pi * refractive_index * thickness_nm / wavelength_nm
    cosine = np.cos(phase)
    sine = np.sin(phase)
    return np.array(
        [
            [cosine, 1j * sine / refractive_index],
            [1j * refractive_index * sine, cosine],
        ],
        dtype=complex,
    )


def optical_response(
    layers: list[tuple[float, float]],
    wavelength_nm: float = WAVELENGTH_NM,
    incident_index: float = AIR_REFRACTIVE_INDEX,
    substrate_index: float = GLASS_REFRACTIVE_INDEX,
) -> tuple[float, float, float]:
    """Return (R, T, |1-R-T|) for a normal-incidence lossless stack."""
    system = np.eye(2, dtype=complex)
    for refractive_index, thickness_nm in layers:
        system = system @ layer_matrix(refractive_index, thickness_nm, wavelength_nm)

    a, b, c, d = system.ravel()
    denominator = incident_index * (a + b * substrate_index) + (c + d * substrate_index)

    reflection_amplitude = (
        incident_index * (a + b * substrate_index) - (c + d * substrate_index)
    ) / denominator
    transmission_amplitude = 2.0 * incident_index / denominator

    reflectance = float(abs(reflection_amplitude) ** 2)
    transmittance = float((substrate_index / incident_index) * abs(transmission_amplitude) ** 2)
    residual = abs(1.0 - reflectance - transmittance)
    return reflectance, transmittance, residual


def calculate_grid() -> list[Result]:
    results: list[Result] = []

    for existing_index in EXISTING_AR_REFRACTIVE_INDICES:
        for existing_thickness in EXISTING_AR_THICKNESSES_NM:
            baseline_layers = [(existing_index, existing_thickness)]
            retrofit_layers = [
                (RETROFIT_REFRACTIVE_INDEX, RETROFIT_THICKNESS_NM),
                (existing_index, existing_thickness),
            ]

            baseline_r, baseline_t, baseline_residual = optical_response(baseline_layers)
            retrofit_r, retrofit_t, retrofit_residual = optical_response(retrofit_layers)

            absolute_change = (retrofit_t - baseline_t) * 100.0
            relative_change = ((retrofit_t / baseline_t) - 1.0) * 100.0

            results.append(
                Result(
                    existing_ar_refractive_index=existing_index,
                    existing_ar_thickness_nm=existing_thickness,
                    baseline_reflectance_percent=baseline_r * 100.0,
                    baseline_transmittance_percent=baseline_t * 100.0,
                    retrofit_reflectance_percent=retrofit_r * 100.0,
                    retrofit_transmittance_percent=retrofit_t * 100.0,
                    absolute_change_percentage_points=absolute_change,
                    relative_change_percent=relative_change,
                    baseline_energy_residual=baseline_residual,
                    retrofit_energy_residual=retrofit_residual,
                )
            )

    return results


def validate_against_document(results: list[Result]) -> dict[str, object]:
    errors: list[float] = []
    mismatches: list[dict[str, object]] = []

    for result in results:
        key = (result.existing_ar_refractive_index, result.existing_ar_thickness_nm)
        expected = DOCUMENT_REFERENCE[key]
        calculated = (
            result.baseline_transmittance_percent,
            result.retrofit_transmittance_percent,
            result.relative_change_percent,
        )
        row_errors = [abs(actual - target) for actual, target in zip(calculated, expected)]
        errors.extend(row_errors)

        if any(round(actual, 4) != target for actual, target in zip(calculated, expected)):
            mismatches.append(
                {
                    "existing_ar_refractive_index": key[0],
                    "existing_ar_thickness_nm": key[1],
                    "expected": expected,
                    "calculated": calculated,
                }
            )

    return {
        "matches_document_after_rounding_to_4_decimals": not mismatches,
        "maximum_absolute_rounding_error": max(errors),
        "mismatches": mismatches,
    }


def write_csv(results: list[Result]) -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    path = RESULTS_DIR / "ar_sensitivity_550nm.csv"
    fieldnames = list(asdict(results[0]).keys())
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(asdict(result) for result in results)
    return path


def write_heatmap(results: list[Result]) -> Path:
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    path = FIGURES_DIR / "ar_sensitivity_550nm_heatmap.png"

    matrix = np.empty(
        (len(EXISTING_AR_REFRACTIVE_INDICES), len(EXISTING_AR_THICKNESSES_NM)),
        dtype=float,
    )
    for result in results:
        row = EXISTING_AR_REFRACTIVE_INDICES.index(result.existing_ar_refractive_index)
        column = EXISTING_AR_THICKNESSES_NM.index(result.existing_ar_thickness_nm)
        matrix[row, column] = result.relative_change_percent

    limit = float(np.max(np.abs(matrix)))
    figure, axis = plt.subplots(figsize=(8.2, 4.8))
    figure.subplots_adjust(left=0.12, right=0.87, bottom=0.23, top=0.86)
    image = axis.imshow(
        matrix,
        cmap="RdYlGn",
        norm=TwoSlopeNorm(vmin=-limit, vcenter=0.0, vmax=limit),
        aspect="auto",
    )

    axis.set_title("Retrofit Relative Transmittance Change at 550 nm", fontsize=15)
    axis.set_xlabel("Assumed existing-AR thickness (nm)")
    axis.set_ylabel("Assumed existing-AR refractive index")
    axis.set_xticks(range(len(EXISTING_AR_THICKNESSES_NM)), [f"{x:.0f}" for x in EXISTING_AR_THICKNESSES_NM])
    axis.set_yticks(range(len(EXISTING_AR_REFRACTIVE_INDICES)), [f"{x:.2f}" for x in EXISTING_AR_REFRACTIVE_INDICES])

    for row in range(matrix.shape[0]):
        for column in range(matrix.shape[1]):
            value = matrix[row, column]
            axis.text(column, row, f"{value:+.4f}%", ha="center", va="center", fontsize=9)

    colorbar = figure.colorbar(image, ax=axis)
    colorbar.set_label("Relative change (%)")
    figure.text(
        0.5,
        0.035,
        "Single-wavelength, lossless normal-incidence TMM screen; not an AM1.5G or field-power result.",
        ha="center",
        fontsize=8,
    )
    figure.savefig(path, dpi=220)
    plt.close(figure)
    return path


def write_summary(results: list[Result], validation: dict[str, object]) -> Path:
    path = RESULTS_DIR / "ar_sensitivity_550nm_summary.json"
    best = max(results, key=lambda item: item.relative_change_percent)
    worst = min(results, key=lambda item: item.relative_change_percent)

    payload = {
        "model": "Normal-incidence coherent lossless thin-film transfer matrix",
        "baseline_stack": "air -> existing AR -> glass",
        "retrofit_stack": "air -> retrofit layer -> existing AR -> glass",
        "wavelength_nm": WAVELENGTH_NM,
        "air_refractive_index": AIR_REFRACTIVE_INDEX,
        "glass_refractive_index": GLASS_REFRACTIVE_INDEX,
        "retrofit_refractive_index": RETROFIT_REFRACTIVE_INDEX,
        "retrofit_thickness_nm": RETROFIT_THICKNESS_NM,
        "existing_ar_refractive_indices": EXISTING_AR_REFRACTIVE_INDICES,
        "existing_ar_thicknesses_nm": EXISTING_AR_THICKNESSES_NM,
        "number_of_cases": len(results),
        "best_case": asdict(best),
        "worst_case": asdict(worst),
        "maximum_energy_residual": max(
            max(item.baseline_energy_residual, item.retrofit_energy_residual)
            for item in results
        ),
        "document_regression_check": validation,
        "limitations": [
            "Single wavelength only (550 nm)",
            "Normal incidence only",
            "Lossless and nondispersive refractive indices",
            "No surface texture, scattering, absorption, temperature or environmental effects",
            "Not an AM1.5G-weighted optical result",
            "Not an electrical-power or field-performance prediction",
        ],
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def print_results(results: list[Result], validation: dict[str, object]) -> None:
    print("550 nm AR sensitivity screening completed.\n")
    print(" n_AR   d_AR (nm)   Baseline T (%)   Retrofit T (%)   Relative change (%)")
    print("-----   ---------   --------------   --------------   -------------------")
    for result in results:
        print(
            f"{result.existing_ar_refractive_index:5.2f}"
            f"   {result.existing_ar_thickness_nm:9.0f}"
            f"   {result.baseline_transmittance_percent:14.4f}"
            f"   {result.retrofit_transmittance_percent:14.4f}"
            f"   {result.relative_change_percent:+19.4f}"
        )

    print()
    print(
        "Matches document at 4 decimals:",
        validation["matches_document_after_rounding_to_4_decimals"],
    )
    print("WARNING: This is a 550 nm screening model, not AM1.5G or electrical power.")


def main() -> None:
    results = calculate_grid()
    validation = validate_against_document(results)

    csv_path = write_csv(results)
    summary_path = write_summary(results, validation)
    figure_path = write_heatmap(results)

    print_results(results, validation)
    print(f"CSV:     {csv_path}")
    print(f"JSON:    {summary_path}")
    print(f"Heatmap: {figure_path}")

    if not validation["matches_document_after_rounding_to_4_decimals"]:
        raise RuntimeError("Calculated values do not reproduce the document table.")


if __name__ == "__main__":
    main()
