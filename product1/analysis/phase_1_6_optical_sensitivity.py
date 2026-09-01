"""Phase 1.6A conditional optical uncertainty envelope for SolarFlow.

This script evaluates a deterministic grid of uncertain optical inputs for:

    baseline: air -> assumed existing AR -> representative glass

    retrofit: air -> active layer -> release primer
                  -> assumed existing AR -> representative glass

Every retrofit case is compared with a baseline using the same existing-AR
assumptions. Results are weighted with the Solcore AM1.5G power spectrum over
300--1200 nm by default.

The calculation is an assumption-sensitivity study. Grid fractions are not
probabilities. It is not a measured-material result, electrical-power result,
annual-yield estimate, durability test, or field validation.
"""

from __future__ import annotations

import argparse
import csv
import itertools
import json
import math
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import TwoSlopeNorm

from product1.analysis import carrier_interface_screen as screen


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = REPO_ROOT / "configs" / "phase_1_6_sensitivity.yaml"
RESULTS_DIR = REPO_ROOT / "product1" / "results"
FIGURES_DIR = RESULTS_DIR / "figures"

CSV_PATH = RESULTS_DIR / "phase_1_6_optical_sensitivity.csv"
SUMMARY_PATH = RESULTS_DIR / "phase_1_6_optical_sensitivity_summary.json"
HEATMAP_PATH = FIGURES_DIR / "phase_1_6_ar_robustness_heatmap.png"
DISTRIBUTION_PATH = FIGURES_DIR / "phase_1_6_gain_distribution.png"


@dataclass(frozen=True)
class OpticalCase:
    existing_ar_refractive_index: float
    existing_ar_thickness_nm: float
    active_refractive_index: float
    active_extinction_coefficient: float
    active_thickness_nm: float
    primer_refractive_index: float
    primer_thickness_nm: float
    incident_power_w_m2: float
    baseline_transmitted_power_w_m2: float
    retrofit_transmitted_power_w_m2: float
    additional_transmitted_power_w_m2: float
    baseline_weighted_transmittance_percent: float
    retrofit_weighted_transmittance_percent: float
    absolute_gain_percentage_points: float
    relative_gain_percent: float
    retrofit_absorbed_power_w_m2: float
    retrofit_weighted_absorptance_percent: float
    passes_positive_gain_gate: bool
    passes_provisional_margin_gate: bool
    maximum_physical_violation: float


PARAMETER_FIELDS = (
    "existing_ar_refractive_index",
    "existing_ar_thickness_nm",
    "active_refractive_index",
    "active_extinction_coefficient",
    "active_thickness_nm",
    "primer_refractive_index",
    "primer_thickness_nm",
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="SolarFlow Phase 1.6A conditional optical sensitivity grid."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help=(
            "Path to the JSON-syntax YAML configuration "
            f"(default: {DEFAULT_CONFIG_PATH.relative_to(REPO_ROOT)})."
        ),
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run kernel and configuration checks without importing Solcore.",
    )
    return parser.parse_args()


def load_config(path: Path) -> dict[str, Any]:
    """Load the JSON-syntax YAML file without adding a PyYAML dependency."""
    if not path.exists():
        raise FileNotFoundError(f"Phase 1.6 configuration not found: {path}")
    try:
        with path.open("r", encoding="utf-8") as file:
            config = json.load(file)
    except json.JSONDecodeError as error:
        raise ValueError(
            "The Phase 1.6 .yaml file intentionally uses JSON syntax. "
            "Keep it valid JSON/YAML 1.2 or add an explicit YAML parser."
        ) from error
    validate_config(config)
    return config


def _require_finite_positive(values: Iterable[Any], name: str) -> list[float]:
    result = [float(value) for value in values]
    if not result:
        raise ValueError(f"{name} must contain at least one value.")
    if not np.all(np.isfinite(result)) or any(value <= 0.0 for value in result):
        raise ValueError(f"{name} values must be finite and positive.")
    return result


def validate_config(config: dict[str, Any]) -> None:
    required_sections = ("model", "gates", "nominal_stack", "sweep", "provenance")
    missing_sections = [name for name in required_sections if name not in config]
    if missing_sections:
        raise ValueError(f"Missing config sections: {missing_sections}")

    model = config["model"]
    wavelength_min = float(model["wavelength_min_nm"])
    wavelength_max = float(model["wavelength_max_nm"])
    wavelength_step = float(model["wavelength_step_nm"])
    if wavelength_min <= 0.0 or wavelength_max <= wavelength_min:
        raise ValueError("The wavelength interval is invalid.")
    if wavelength_step <= 0.0:
        raise ValueError("wavelength_step_nm must be positive.")

    _require_finite_positive(
        [model["incident_refractive_index"]],
        "incident_refractive_index",
    )
    _require_finite_positive(
        [model["glass_refractive_index"]],
        "glass_refractive_index",
    )

    sweep = config["sweep"]
    for name in PARAMETER_FIELDS:
        if name not in sweep:
            raise ValueError(f"Missing sweep parameter: {name}")
        values = [float(value) for value in sweep[name]]
        if not values or not np.all(np.isfinite(values)):
            raise ValueError(f"Sweep parameter {name} is empty or non-finite.")
        if name == "active_extinction_coefficient":
            if any(value < 0.0 for value in values):
                raise ValueError("Extinction coefficients must be non-negative.")
        elif any(value <= 0.0 for value in values):
            raise ValueError(f"Sweep parameter {name} must be positive.")

    gates = config["gates"]
    if float(gates["provisional_margin_percent"]) < float(
        gates["positive_gain_percent"]
    ):
        raise ValueError("The provisional margin cannot be below the positive gate.")

    nominal = config["nominal_stack"]
    for name in PARAMETER_FIELDS:
        value = float(nominal[name])
        if not math.isfinite(value):
            raise ValueError(f"Nominal parameter {name} must be finite.")
        if name == "active_extinction_coefficient":
            if value < 0.0:
                raise ValueError("Nominal extinction coefficient cannot be negative.")
        elif value <= 0.0:
            raise ValueError(f"Nominal parameter {name} must be positive.")


def wavelengths_nm(config: dict[str, Any]) -> np.ndarray:
    model = config["model"]
    start = float(model["wavelength_min_nm"])
    stop = float(model["wavelength_max_nm"])
    step = float(model["wavelength_step_nm"])
    return np.arange(start, stop + 0.5 * step, step, dtype=float)


def multiply_layer(
    a: np.ndarray,
    b: np.ndarray,
    c: np.ndarray,
    d: np.ndarray,
    refractive_index: complex,
    thickness_nm: float,
    wavelength_nm: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Right-multiply a vectorized characteristic matrix by one layer."""
    phase = 2.0 * np.pi * refractive_index * thickness_nm / wavelength_nm
    cosine = np.cos(phase)
    sine = np.sin(phase)
    layer_a = cosine
    layer_b = 1j * sine / refractive_index
    layer_c = 1j * refractive_index * sine
    layer_d = cosine
    return (
        a * layer_a + b * layer_c,
        a * layer_b + b * layer_d,
        c * layer_a + d * layer_c,
        c * layer_b + d * layer_d,
    )


def optical_response(
    layers: Iterable[tuple[float, float, float]],
    wavelength_nm: np.ndarray,
    incident_index: float,
    substrate_index: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Return R, T, inferred A, and a non-physical-value diagnostic.

    Each layer is ``(n, k, thickness_nm)`` and uses ``n - i*k`` for the
    time-harmonic convention of this characteristic-matrix implementation.
    Absorptance is inferred from ``1-R-T`` and is not an independent solver
    cross-check.
    """
    ones = np.ones_like(wavelength_nm, dtype=complex)
    zeros = np.zeros_like(wavelength_nm, dtype=complex)
    a, b, c, d = ones, zeros, zeros, ones

    for real_index, extinction_coefficient, thickness_nm in layers:
        if real_index <= 0.0:
            raise ValueError("Every real refractive index must be positive.")
        if extinction_coefficient < 0.0:
            raise ValueError("Every extinction coefficient must be non-negative.")
        if thickness_nm < 0.0:
            raise ValueError("Every layer thickness must be non-negative.")
        complex_index = complex(real_index, -extinction_coefficient)
        a, b, c, d = multiply_layer(
            a,
            b,
            c,
            d,
            complex_index,
            thickness_nm,
            wavelength_nm,
        )

    denominator = incident_index * (a + b * substrate_index) + (
        c + d * substrate_index
    )
    reflection_amplitude = (
        incident_index * (a + b * substrate_index) - (c + d * substrate_index)
    ) / denominator
    transmission_amplitude = 2.0 * incident_index / denominator

    reflectance = np.abs(reflection_amplitude) ** 2
    transmittance = (
        substrate_index / incident_index
    ) * np.abs(transmission_amplitude) ** 2
    absorptance = 1.0 - reflectance - transmittance

    tolerance = 1e-12
    reflectance = np.where(np.abs(reflectance) < tolerance, 0.0, reflectance)
    transmittance = np.where(np.abs(transmittance) < tolerance, 0.0, transmittance)
    absorptance = np.where(np.abs(absorptance) < tolerance, 0.0, absorptance)

    physical_violation = np.maximum.reduce(
        (
            np.maximum(-reflectance, 0.0),
            np.maximum(-transmittance, 0.0),
            np.maximum(-absorptance, 0.0),
            np.maximum(reflectance - 1.0, 0.0),
            np.maximum(transmittance - 1.0, 0.0),
            np.maximum(absorptance - 1.0, 0.0),
        )
    )
    return (
        reflectance.real,
        transmittance.real,
        absorptance.real,
        physical_violation.real,
    )


def evaluate_case(
    parameters: dict[str, float],
    wavelength_nm: np.ndarray,
    power_density_w_m2_nm: np.ndarray,
    config: dict[str, Any],
    baseline_cache: dict[tuple[float, float], tuple[np.ndarray, float]],
) -> OpticalCase:
    model = config["model"]
    incident_index = float(model["incident_refractive_index"])
    glass_index = float(model["glass_refractive_index"])
    positive_gate = float(config["gates"]["positive_gain_percent"])
    margin_gate = float(config["gates"]["provisional_margin_percent"])

    incident_power = screen.integrate(power_density_w_m2_nm, wavelength_nm)
    ar_key = (
        parameters["existing_ar_refractive_index"],
        parameters["existing_ar_thickness_nm"],
    )
    if ar_key not in baseline_cache:
        _, baseline_t, _, baseline_violation = optical_response(
            [
                (
                    parameters["existing_ar_refractive_index"],
                    0.0,
                    parameters["existing_ar_thickness_nm"],
                )
            ],
            wavelength_nm,
            incident_index,
            glass_index,
        )
        baseline_power = screen.solar_weighted_power(
            baseline_t,
            power_density_w_m2_nm,
            wavelength_nm,
        )
        baseline_cache[ar_key] = (baseline_t, baseline_power)
        if float(np.max(baseline_violation)) > 1e-9:
            raise RuntimeError("Baseline TMM returned a non-physical response.")
    else:
        _, baseline_power = baseline_cache[ar_key]

    _, retrofit_t, retrofit_a, retrofit_violation = optical_response(
        [
            (
                parameters["active_refractive_index"],
                parameters["active_extinction_coefficient"],
                parameters["active_thickness_nm"],
            ),
            (
                parameters["primer_refractive_index"],
                0.0,
                parameters["primer_thickness_nm"],
            ),
            (
                parameters["existing_ar_refractive_index"],
                0.0,
                parameters["existing_ar_thickness_nm"],
            ),
        ],
        wavelength_nm,
        incident_index,
        glass_index,
    )
    retrofit_power = screen.solar_weighted_power(
        retrofit_t,
        power_density_w_m2_nm,
        wavelength_nm,
    )
    absorbed_power = screen.solar_weighted_power(
        retrofit_a,
        power_density_w_m2_nm,
        wavelength_nm,
    )
    additional_power = retrofit_power - baseline_power
    relative_gain = 100.0 * additional_power / baseline_power

    return OpticalCase(
        **parameters,
        incident_power_w_m2=incident_power,
        baseline_transmitted_power_w_m2=baseline_power,
        retrofit_transmitted_power_w_m2=retrofit_power,
        additional_transmitted_power_w_m2=additional_power,
        baseline_weighted_transmittance_percent=100.0
        * baseline_power
        / incident_power,
        retrofit_weighted_transmittance_percent=100.0
        * retrofit_power
        / incident_power,
        absolute_gain_percentage_points=100.0
        * additional_power
        / incident_power,
        relative_gain_percent=relative_gain,
        retrofit_absorbed_power_w_m2=absorbed_power,
        retrofit_weighted_absorptance_percent=100.0
        * absorbed_power
        / incident_power,
        passes_positive_gain_gate=relative_gain > positive_gate,
        passes_provisional_margin_gate=relative_gain >= margin_gate,
        maximum_physical_violation=float(np.max(retrofit_violation)),
    )


def calculate_grid(
    wavelength_nm: np.ndarray,
    power_density_w_m2_nm: np.ndarray,
    config: dict[str, Any],
) -> list[OpticalCase]:
    sweep = config["sweep"]
    value_lists = [[float(value) for value in sweep[name]] for name in PARAMETER_FIELDS]
    baseline_cache: dict[tuple[float, float], tuple[np.ndarray, float]] = {}
    results: list[OpticalCase] = []

    for values in itertools.product(*value_lists):
        parameters = dict(zip(PARAMETER_FIELDS, values))
        results.append(
            evaluate_case(
                parameters,
                wavelength_nm,
                power_density_w_m2_nm,
                config,
                baseline_cache,
            )
        )
    return results


def expected_case_count(config: dict[str, Any]) -> int:
    return math.prod(len(config["sweep"][name]) for name in PARAMETER_FIELDS)


def subset_statistics(results: list[OpticalCase]) -> dict[str, Any]:
    if not results:
        return {"case_count": 0}
    gains = np.array([item.relative_gain_percent for item in results], dtype=float)
    positive_count = sum(item.passes_positive_gain_gate for item in results)
    margin_count = sum(item.passes_provisional_margin_gate for item in results)
    return {
        "case_count": len(results),
        "minimum_relative_gain_percent": float(np.min(gains)),
        "percentile_05_relative_gain_percent": float(np.percentile(gains, 5.0)),
        "median_relative_gain_percent": float(np.median(gains)),
        "percentile_95_relative_gain_percent": float(np.percentile(gains, 95.0)),
        "maximum_relative_gain_percent": float(np.max(gains)),
        "positive_gain_case_count": positive_count,
        "positive_gain_case_fraction": positive_count / len(results),
        "provisional_margin_case_count": margin_count,
        "provisional_margin_case_fraction": margin_count / len(results),
        "all_cases_positive": positive_count == len(results),
        "all_cases_pass_provisional_margin": margin_count == len(results),
    }


def main_effect_spreads(results: list[OpticalCase]) -> list[dict[str, Any]]:
    ranking: list[dict[str, Any]] = []
    for field in PARAMETER_FIELDS:
        grouped: dict[float, list[float]] = defaultdict(list)
        for item in results:
            grouped[float(getattr(item, field))].append(item.relative_gain_percent)
        means = {
            f"{level:.9g}": float(np.mean(values))
            for level, values in sorted(grouped.items())
        }
        mean_values = list(means.values())
        ranking.append(
            {
                "parameter": field,
                "mean_gain_by_level_percent": means,
                "main_effect_spread_percent": max(mean_values) - min(mean_values),
            }
        )
    return sorted(
        ranking,
        key=lambda item: item["main_effect_spread_percent"],
        reverse=True,
    )


def write_csv(results: list[OpticalCase]) -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    with CSV_PATH.open("w", encoding="utf-8", newline="") as file:
        fieldnames = list(asdict(results[0]).keys())
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(asdict(item) for item in results)
    return CSV_PATH


def write_summary(
    results: list[OpticalCase],
    nominal: OpticalCase,
    config: dict[str, Any],
) -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    lossless = [item for item in results if item.active_extinction_coefficient == 0.0]
    absorption_stress = [
        item for item in results if item.active_extinction_coefficient > 0.0
    ]
    overall = subset_statistics(results)
    lossless_stats = subset_statistics(lossless)
    absorption_stats = subset_statistics(absorption_stress)
    worst = min(results, key=lambda item: item.relative_gain_percent)
    best = max(results, key=lambda item: item.relative_gain_percent)

    if overall["all_cases_pass_provisional_margin"]:
        decision = (
            "Every case in the defined deterministic grid retains the provisional "
            "optical margin. This is conditional robustness, not physical validation."
        )
    elif overall["all_cases_positive"]:
        decision = (
            "Every defined case remains optically positive, but at least one case "
            "falls below the provisional margin. Measure the highest-ranked unknowns."
        )
    else:
        decision = (
            "The current architecture is not positive throughout the defined "
            "uncertainty grid. Use the sensitivity ranking to prioritize measurements "
            "and do not freeze a physical design."
        )

    payload = {
        "phase": config.get("phase", "1.6A"),
        "title": config.get("title"),
        "scientific_status": config.get("scientific_status"),
        "model": config["model"],
        "gates": config["gates"],
        "expected_case_count": expected_case_count(config),
        "overall_grid": overall,
        "lossless_subset_k_equals_zero": lossless_stats,
        "absorption_stress_subset_k_greater_than_zero": absorption_stats,
        "nominal_stack_result": asdict(nominal),
        "worst_defined_case": asdict(worst),
        "best_defined_case": asdict(best),
        "main_effect_ranking": main_effect_spreads(results),
        "parameter_provenance": config["provenance"],
        "references": config.get("references", []),
        "decision": decision,
        "warnings": config.get("required_warnings", []),
        "outputs": [
            str(CSV_PATH.relative_to(REPO_ROOT)),
            str(SUMMARY_PATH.relative_to(REPO_ROOT)),
            str(HEATMAP_PATH.relative_to(REPO_ROOT)),
            str(DISTRIBUTION_PATH.relative_to(REPO_ROOT)),
        ],
    }
    with SUMMARY_PATH.open("w", encoding="utf-8") as file:
        json.dump(payload, file, indent=2, ensure_ascii=False)
        file.write("\n")
    return SUMMARY_PATH


def ar_worst_case_matrix(
    results: list[OpticalCase],
    ar_indices: list[float],
    ar_thicknesses_nm: list[float],
    lossless_only: bool,
) -> np.ndarray:
    matrix = np.empty((len(ar_indices), len(ar_thicknesses_nm)), dtype=float)
    for row, ar_index in enumerate(ar_indices):
        for column, ar_thickness in enumerate(ar_thicknesses_nm):
            candidates = [
                item.relative_gain_percent
                for item in results
                if item.existing_ar_refractive_index == ar_index
                and item.existing_ar_thickness_nm == ar_thickness
                and (
                    not lossless_only
                    or item.active_extinction_coefficient == 0.0
                )
            ]
            matrix[row, column] = min(candidates)
    return matrix


def annotate_heatmap(axis: plt.Axes, matrix: np.ndarray) -> None:
    for row in range(matrix.shape[0]):
        for column in range(matrix.shape[1]):
            axis.text(
                column,
                row,
                f"{matrix[row, column]:+.3f}%",
                ha="center",
                va="center",
                fontsize=8,
            )


def write_heatmap(results: list[OpticalCase], config: dict[str, Any]) -> Path:
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    ar_indices = [
        float(value) for value in config["sweep"]["existing_ar_refractive_index"]
    ]
    ar_thicknesses = [
        float(value) for value in config["sweep"]["existing_ar_thickness_nm"]
    ]
    lossless_matrix = ar_worst_case_matrix(
        results,
        ar_indices,
        ar_thicknesses,
        lossless_only=True,
    )
    full_matrix = ar_worst_case_matrix(
        results,
        ar_indices,
        ar_thicknesses,
        lossless_only=False,
    )
    limit = max(
        float(np.max(np.abs(lossless_matrix))),
        float(np.max(np.abs(full_matrix))),
        0.1,
    )
    norm = TwoSlopeNorm(vmin=-limit, vcenter=0.0, vmax=limit)

    figure, axes = plt.subplots(1, 2, figsize=(12.8, 5.2))
    image = None
    for axis, matrix, title in (
        (axes[0], lossless_matrix, "Worst case with active k = 0"),
        (axes[1], full_matrix, "Worst case including absorption stress"),
    ):
        image = axis.imshow(matrix, cmap="RdYlGn", norm=norm, aspect="auto")
        axis.set_title(title)
        axis.set_xlabel("Assumed existing-AR thickness (nm)")
        axis.set_xticks(
            range(len(ar_thicknesses)),
            [f"{value:.0f}" for value in ar_thicknesses],
        )
        axis.set_yticks(
            range(len(ar_indices)),
            [f"{value:.2f}" for value in ar_indices],
        )
        annotate_heatmap(axis, matrix)
    axes[0].set_ylabel("Assumed existing-AR refractive index")
    figure.suptitle("SolarFlow Phase 1.6A - Worst Relative Optical Gain")
    if image is not None:
        colorbar = figure.colorbar(image, ax=axes, fraction=0.025, pad=0.035)
        colorbar.set_label("AM1.5G-weighted relative optical gain (%)")
    figure.text(
        0.5,
        0.02,
        "Deterministic assumption grid; not probability, electrical power, or measured module performance.",
        ha="center",
        fontsize=8,
    )
    figure.subplots_adjust(left=0.08, right=0.91, bottom=0.16, top=0.84, wspace=0.22)
    figure.savefig(HEATMAP_PATH, dpi=220)
    plt.close(figure)
    return HEATMAP_PATH


def write_distribution(results: list[OpticalCase], config: dict[str, Any]) -> Path:
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    lossless = [
        item.relative_gain_percent
        for item in results
        if item.active_extinction_coefficient == 0.0
    ]
    absorption = [
        item.relative_gain_percent
        for item in results
        if item.active_extinction_coefficient > 0.0
    ]
    margin = float(config["gates"]["provisional_margin_percent"])

    figure, axis = plt.subplots(figsize=(8.6, 5.0))
    axis.hist(lossless, bins=40, alpha=0.70, label="k = 0 subset")
    axis.hist(absorption, bins=40, alpha=0.55, label="k > 0 stress subset")
    axis.axvline(0.0, color="black", linewidth=1.2, label="Positive-gain gate")
    axis.axvline(
        margin,
        color="#e36b00",
        linestyle="--",
        linewidth=1.5,
        label=f"Provisional margin: {margin:.2f}%",
    )
    axis.set_title("SolarFlow Phase 1.6A Deterministic Gain Distribution")
    axis.set_xlabel("AM1.5G-weighted relative optical gain (%)")
    axis.set_ylabel("Defined scenario count")
    axis.grid(alpha=0.25)
    axis.legend()
    figure.tight_layout()
    figure.savefig(DISTRIBUTION_PATH, dpi=220)
    plt.close(figure)
    return DISTRIBUTION_PATH


def print_results(
    results: list[OpticalCase],
    nominal: OpticalCase,
    config: dict[str, Any],
    output_paths: list[Path],
) -> None:
    overall = subset_statistics(results)
    lossless = subset_statistics(
        [item for item in results if item.active_extinction_coefficient == 0.0]
    )
    ranking = main_effect_spreads(results)
    worst = min(results, key=lambda item: item.relative_gain_percent)

    print("SolarFlow Phase 1.6A optical uncertainty envelope completed.")
    print(f"Defined deterministic cases : {len(results)}")
    print(f"Nominal relative gain       : {nominal.relative_gain_percent:+.4f}%")
    print(f"Overall minimum gain        : {overall['minimum_relative_gain_percent']:+.4f}%")
    print(f"Overall median gain         : {overall['median_relative_gain_percent']:+.4f}%")
    print(
        "Positive cases             : "
        f"{overall['positive_gain_case_count']}/{overall['case_count']} "
        f"({100.0 * overall['positive_gain_case_fraction']:.2f}%)"
    )
    print(
        "Cases passing +0.10% gate  : "
        f"{overall['provisional_margin_case_count']}/{overall['case_count']} "
        f"({100.0 * overall['provisional_margin_case_fraction']:.2f}%)"
    )
    print(
        "Lossless minimum gain       : "
        f"{lossless['minimum_relative_gain_percent']:+.4f}%"
    )
    print(
        "Worst defined case          : "
        f"AR n={worst.existing_ar_refractive_index:.3f}, "
        f"AR d={worst.existing_ar_thickness_nm:.1f} nm, "
        f"active n={worst.active_refractive_index:.6f}, "
        f"k={worst.active_extinction_coefficient:.1e}, "
        f"active d={worst.active_thickness_nm:.3f} nm, "
        f"primer n={worst.primer_refractive_index:.3f}, "
        f"primer d={worst.primer_thickness_nm:.1f} nm"
    )
    print("Top main-effect spreads:")
    for item in ranking[:3]:
        print(
            f"  {item['parameter']}: "
            f"{item['main_effect_spread_percent']:.4f} percentage points"
        )
    print("Outputs:")
    for path in output_paths:
        print(f"  - {path}")
    print()
    print("WARNING: Grid fractions are not probabilities or confidence levels.")
    print("WARNING: Optical assumption sensitivity is not electrical or field gain.")
    for warning in config.get("required_warnings", []):
        print(f"WARNING: {warning}")


def run_self_test(config_path: Path) -> None:
    config = load_config(config_path)
    wavelength = np.array([450.0, 550.0, 650.0, 750.0], dtype=float)
    incident_index = float(config["model"]["incident_refractive_index"])
    substrate_index = float(config["model"]["glass_refractive_index"])

    reflectance, transmittance, absorptance, violation = optical_response(
        [],
        wavelength,
        incident_index,
        substrate_index,
    )
    expected_r = ((incident_index - substrate_index) / (incident_index + substrate_index)) ** 2
    if not np.allclose(reflectance, expected_r, atol=1e-12):
        raise AssertionError("Bare-interface Fresnel reflectance regression failed.")
    if not np.allclose(transmittance, 1.0 - expected_r, atol=1e-12):
        raise AssertionError("Bare-interface Fresnel transmittance regression failed.")
    if not np.allclose(absorptance, 0.0, atol=1e-12):
        raise AssertionError("Lossless bare interface reported absorption.")
    if float(np.max(violation)) > 1e-12:
        raise AssertionError("Bare-interface response is non-physical.")

    _, _, absorbing_a, absorbing_violation = optical_response(
        [(1.10, 1e-3, 120.0)],
        wavelength,
        incident_index,
        substrate_index,
    )
    if not np.all(absorbing_a > 0.0):
        raise AssertionError("Absorbing-film sign convention regression failed.")
    if float(np.max(absorbing_violation)) > 1e-10:
        raise AssertionError("Absorbing-film response is non-physical.")

    small_power_density = np.ones_like(wavelength)
    nominal_parameters = {
        name: float(config["nominal_stack"][name]) for name in PARAMETER_FIELDS
    }
    nominal = evaluate_case(
        nominal_parameters,
        wavelength,
        small_power_density,
        config,
        {},
    )
    if not math.isfinite(nominal.relative_gain_percent):
        raise AssertionError("Nominal-case calculation returned a non-finite gain.")
    if expected_case_count(config) < 1:
        raise AssertionError("Expected grid size must be positive.")
    print("Phase 1.6A self-test passed.")
    print(f"Configured deterministic cases: {expected_case_count(config)}")


def main() -> None:
    args = parse_arguments()
    config_path = args.config
    if not config_path.is_absolute():
        config_path = REPO_ROOT / config_path

    if args.self_test:
        run_self_test(config_path)
        return

    config = load_config(config_path)
    wavelength = wavelengths_nm(config)
    print(f"Loading AM1.5G spectrum for {len(wavelength)} wavelength points...")
    power_density = screen.load_am15g_power_density(wavelength)
    print(f"Evaluating {expected_case_count(config)} deterministic cases...")
    results = calculate_grid(wavelength, power_density, config)

    nominal_parameters = {
        name: float(config["nominal_stack"][name]) for name in PARAMETER_FIELDS
    }
    nominal = evaluate_case(
        nominal_parameters,
        wavelength,
        power_density,
        config,
        {},
    )

    csv_path = write_csv(results)
    summary_path = write_summary(results, nominal, config)
    heatmap_path = write_heatmap(results, config)
    distribution_path = write_distribution(results, config)
    print_results(
        results,
        nominal,
        config,
        [csv_path, summary_path, heatmap_path, distribution_path],
    )


if __name__ == "__main__":
    main()
