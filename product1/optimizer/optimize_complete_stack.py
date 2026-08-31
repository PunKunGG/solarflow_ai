"""Re-optimize the SolarFlow coating for a complete carrier stack.

The previous carrier/interface screen inserted the original coating candidate
without re-optimizing it.  This script fixes the most promising architecture
(optical contact, 50 um generic carrier), then uses Optuna to optimize the
retrofit refractive index and thickness for each carrier index from 1.20 to
1.40.  The result is a feasibility boundary: the highest carrier index for
which the complete stack can still outperform the assumed existing module.

Stack order
-----------
    baseline: air -> existing AR -> glass
    complete: air -> optimized coating -> carrier -> existing AR -> glass

The calculation is an AM1.5G-weighted, normal-incidence, lossless,
nondispersive TMM screen.  Thick-carrier interference is phase-averaged.
It is not an electrical-power, annual-yield, durability or material claim.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np

from product1.analysis import carrier_interface_screen as screen


CARRIER_REFRACTIVE_INDICES = tuple(
    float(value) for value in np.round(np.arange(1.20, 1.4001, 0.02), 2)
)
CARRIER_THICKNESS_UM = 50.0

RETROFIT_INDEX_MIN = 1.02
RETROFIT_INDEX_MAX = 1.30
RETROFIT_THICKNESS_MIN_NM = 50.0
RETROFIT_THICKNESS_MAX_NM = 250.0

DEFAULT_TRIALS_PER_INDEX = 140
DEFAULT_OPTIMIZATION_PHASE_SAMPLES = 7
DEFAULT_VALIDATION_PHASE_SAMPLES = 31
RANDOM_SEED = 20260831

REPO_ROOT = Path(__file__).resolve().parents[2]
RESULTS_DIR = REPO_ROOT / "product1" / "results"
FIGURES_DIR = RESULTS_DIR / "figures"


@dataclass(frozen=True)
class OptimizedResult:
    carrier_refractive_index: float
    carrier_thickness_um: float
    optimized_retrofit_refractive_index: float
    optimized_retrofit_thickness_nm: float
    transmitted_power_w_m2: float
    weighted_transmittance_percent: float
    additional_power_vs_baseline_w_m2: float
    absolute_gain_vs_baseline_percentage_points: float
    relative_gain_vs_baseline_percent: float
    gain_retention_vs_active_only_percent: float
    maximum_energy_residual: float
    optimization_trial_number: int
    passes_positive_gain_gate: bool


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Re-optimize SolarFlow coating for complete carrier stacks."
    )
    parser.add_argument(
        "--trials-per-index",
        type=int,
        default=DEFAULT_TRIALS_PER_INDEX,
        help=f"Optuna trials for each carrier index (default: {DEFAULT_TRIALS_PER_INDEX}).",
    )
    parser.add_argument(
        "--phase-samples",
        type=int,
        default=DEFAULT_OPTIMIZATION_PHASE_SAMPLES,
        help=(
            "Carrier phase samples used during optimization "
            f"(default: {DEFAULT_OPTIMIZATION_PHASE_SAMPLES})."
        ),
    )
    parser.add_argument(
        "--validation-phase-samples",
        type=int,
        default=DEFAULT_VALIDATION_PHASE_SAMPLES,
        help=(
            "Carrier phase samples for final candidate evaluation "
            f"(default: {DEFAULT_VALIDATION_PHASE_SAMPLES})."
        ),
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run optical and threshold checks without importing Solcore or Optuna.",
    )
    return parser.parse_args()


def complete_stack_response(
    wavelength_nm: np.ndarray,
    carrier_refractive_index: float,
    retrofit_refractive_index: float,
    retrofit_thickness_nm: float,
    phase_samples: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return phase-averaged R, T and maximum energy residual."""
    offsets_nm = screen.phase_offsets_nm(
        carrier_refractive_index,
        phase_samples,
    )
    carrier_nominal_nm = CARRIER_THICKNESS_UM * 1000.0

    reflectance_sum = np.zeros_like(wavelength_nm, dtype=float)
    transmittance_sum = np.zeros_like(wavelength_nm, dtype=float)
    maximum_residual = np.zeros_like(wavelength_nm, dtype=float)

    for offset_nm in offsets_nm:
        layers = [
            (retrofit_refractive_index, retrofit_thickness_nm),
            (carrier_refractive_index, carrier_nominal_nm + offset_nm),
            (
                screen.EXISTING_AR_REFRACTIVE_INDEX,
                screen.EXISTING_AR_THICKNESS_NM,
            ),
        ]
        reflectance, transmittance, residual = screen.optical_response(
            layers,
            wavelength_nm,
        )
        reflectance_sum += reflectance
        transmittance_sum += transmittance
        maximum_residual = np.maximum(maximum_residual, residual)

    number_of_samples = len(offsets_nm)
    return (
        reflectance_sum / number_of_samples,
        transmittance_sum / number_of_samples,
        maximum_residual,
    )


def calculate_references(
    wavelength_nm: np.ndarray,
    power_density_w_m2_nm: np.ndarray,
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
            (
                screen.RETROFIT_REFRACTIVE_INDEX,
                screen.RETROFIT_THICKNESS_NM,
            ),
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
    active_additional_power = active_power - baseline_power

    reference = {
        "incident_power_w_m2": incident_power,
        "baseline_power_w_m2": baseline_power,
        "baseline_weighted_transmittance_percent": 100.0
        * baseline_power
        / incident_power,
        "active_only_power_w_m2": active_power,
        "active_only_additional_power_w_m2": active_additional_power,
        "active_only_relative_gain_percent": 100.0
        * active_additional_power
        / baseline_power,
        "baseline_maximum_energy_residual": float(np.max(baseline_residual)),
        "active_only_maximum_energy_residual": float(np.max(active_residual)),
    }
    spectra = {
        "baseline_reflectance": baseline_r,
        "baseline_transmittance": baseline_t,
        "active_only_reflectance": active_r,
        "active_only_transmittance": active_t,
    }
    return reference, spectra


def optimize_for_carrier_index(
    carrier_refractive_index: float,
    wavelength_nm: np.ndarray,
    power_density_w_m2_nm: np.ndarray,
    baseline_power_w_m2: float,
    trials_per_index: int,
    phase_samples: int,
    validation_phase_samples: int,
) -> tuple[OptimizedResult, list[dict[str, Any]], np.ndarray]:
    try:
        import optuna
    except ImportError as error:
        raise RuntimeError(
            "Optuna is required. Activate solarflow-full and run "
            "`python -m pip install optuna` if it is missing."
        ) from error

    optuna.logging.set_verbosity(optuna.logging.WARNING)
    sampler = optuna.samplers.TPESampler(
        seed=RANDOM_SEED + int(round(carrier_refractive_index * 1000.0)),
        n_startup_trials=min(24, max(8, trials_per_index // 5)),
    )
    study = optuna.create_study(direction="maximize", sampler=sampler)

    # Two physically informed starting points plus the old active-only design.
    quarter_wave_index = math.sqrt(carrier_refractive_index)
    quarter_wave_thickness_nm = 600.0 / (4.0 * quarter_wave_index)
    study.enqueue_trial(
        {
            "retrofit_refractive_index": screen.RETROFIT_REFRACTIVE_INDEX,
            "retrofit_thickness_nm": screen.RETROFIT_THICKNESS_NM,
        }
    )
    study.enqueue_trial(
        {
            "retrofit_refractive_index": min(
                RETROFIT_INDEX_MAX,
                max(RETROFIT_INDEX_MIN, quarter_wave_index),
            ),
            "retrofit_thickness_nm": min(
                RETROFIT_THICKNESS_MAX_NM,
                max(RETROFIT_THICKNESS_MIN_NM, quarter_wave_thickness_nm),
            ),
        }
    )

    def objective(trial: Any) -> float:
        retrofit_index = trial.suggest_float(
            "retrofit_refractive_index",
            RETROFIT_INDEX_MIN,
            RETROFIT_INDEX_MAX,
        )
        retrofit_thickness_nm = trial.suggest_float(
            "retrofit_thickness_nm",
            RETROFIT_THICKNESS_MIN_NM,
            RETROFIT_THICKNESS_MAX_NM,
        )
        _, transmittance, _ = complete_stack_response(
            wavelength_nm=wavelength_nm,
            carrier_refractive_index=carrier_refractive_index,
            retrofit_refractive_index=retrofit_index,
            retrofit_thickness_nm=retrofit_thickness_nm,
            phase_samples=phase_samples,
        )
        transmitted_power = screen.solar_weighted_power(
            transmittance,
            power_density_w_m2_nm,
            wavelength_nm,
        )
        return 100.0 * (transmitted_power / baseline_power_w_m2 - 1.0)

    study.optimize(objective, n_trials=trials_per_index, show_progress_bar=False)

    best_index = float(study.best_params["retrofit_refractive_index"])
    best_thickness_nm = float(study.best_params["retrofit_thickness_nm"])
    _, final_transmittance, final_residual = complete_stack_response(
        wavelength_nm=wavelength_nm,
        carrier_refractive_index=carrier_refractive_index,
        retrofit_refractive_index=best_index,
        retrofit_thickness_nm=best_thickness_nm,
        phase_samples=validation_phase_samples,
    )
    transmitted_power = screen.solar_weighted_power(
        final_transmittance,
        power_density_w_m2_nm,
        wavelength_nm,
    )
    incident_power = screen.integrate(power_density_w_m2_nm, wavelength_nm)
    additional_power = transmitted_power - baseline_power_w_m2

    # The active-only additional power is recomputed from the two reference
    # stacks so this function remains independently reproducible.
    _, active_t, _ = screen.optical_response(
        [
            (
                screen.RETROFIT_REFRACTIVE_INDEX,
                screen.RETROFIT_THICKNESS_NM,
            ),
            (
                screen.EXISTING_AR_REFRACTIVE_INDEX,
                screen.EXISTING_AR_THICKNESS_NM,
            ),
        ],
        wavelength_nm,
    )
    active_power = screen.solar_weighted_power(
        active_t,
        power_density_w_m2_nm,
        wavelength_nm,
    )
    active_additional_power = active_power - baseline_power_w_m2
    gain_retention = (
        100.0 * additional_power / active_additional_power
        if active_additional_power > 0.0
        else float("nan")
    )
    relative_gain = 100.0 * additional_power / baseline_power_w_m2

    result = OptimizedResult(
        carrier_refractive_index=carrier_refractive_index,
        carrier_thickness_um=CARRIER_THICKNESS_UM,
        optimized_retrofit_refractive_index=best_index,
        optimized_retrofit_thickness_nm=best_thickness_nm,
        transmitted_power_w_m2=transmitted_power,
        weighted_transmittance_percent=100.0
        * transmitted_power
        / incident_power,
        additional_power_vs_baseline_w_m2=additional_power,
        absolute_gain_vs_baseline_percentage_points=100.0
        * additional_power
        / incident_power,
        relative_gain_vs_baseline_percent=relative_gain,
        gain_retention_vs_active_only_percent=gain_retention,
        maximum_energy_residual=float(np.max(final_residual)),
        optimization_trial_number=int(study.best_trial.number),
        passes_positive_gain_gate=relative_gain > 0.0,
    )

    trial_rows: list[dict[str, Any]] = []
    for trial in study.trials:
        if trial.value is None:
            continue
        trial_rows.append(
            {
                "carrier_refractive_index": carrier_refractive_index,
                "trial_number": int(trial.number),
                "retrofit_refractive_index": float(
                    trial.params["retrofit_refractive_index"]
                ),
                "retrofit_thickness_nm": float(
                    trial.params["retrofit_thickness_nm"]
                ),
                "optimization_relative_gain_percent": float(trial.value),
                "trial_state": str(trial.state.name),
            }
        )

    return result, trial_rows, final_transmittance


def estimate_zero_crossing(results: list[OptimizedResult]) -> dict[str, Any]:
    """Linearly interpolate the first positive-to-negative gain crossing."""
    ordered = sorted(results, key=lambda item: item.carrier_refractive_index)
    crossings: list[dict[str, float]] = []

    for lower, upper in zip(ordered[:-1], ordered[1:]):
        lower_gain = lower.relative_gain_vs_baseline_percent
        upper_gain = upper.relative_gain_vs_baseline_percent
        if lower_gain == 0.0:
            crossing = lower.carrier_refractive_index
        elif lower_gain * upper_gain < 0.0:
            crossing = lower.carrier_refractive_index + (
                -lower_gain
                * (upper.carrier_refractive_index - lower.carrier_refractive_index)
                / (upper_gain - lower_gain)
            )
        else:
            continue

        crossings.append(
            {
                "lower_carrier_refractive_index": lower.carrier_refractive_index,
                "lower_gain_percent": lower_gain,
                "upper_carrier_refractive_index": upper.carrier_refractive_index,
                "upper_gain_percent": upper_gain,
                "interpolated_zero_gain_carrier_refractive_index": crossing,
            }
        )

    positive = [
        result for result in ordered if result.relative_gain_vs_baseline_percent > 0.0
    ]
    return {
        "crossings": crossings,
        "highest_sampled_positive_carrier_index": (
            max(item.carrier_refractive_index for item in positive)
            if positive
            else None
        ),
        "interpretation": (
            "A crossing is a screening estimate, not a material specification. "
            "Confirm it with denser carrier-index sampling and measured optical constants."
        ),
    }


def write_best_results_csv(results: list[OptimizedResult]) -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    path = RESULTS_DIR / "complete_stack_reoptimization.csv"
    with path.open("w", encoding="utf-8", newline="") as file:
        fieldnames = list(asdict(results[0]).keys())
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(asdict(result) for result in results)
    return path


def write_trials_csv(trial_rows: list[dict[str, Any]]) -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    path = RESULTS_DIR / "complete_stack_reoptimization_trials.csv"
    with path.open("w", encoding="utf-8", newline="") as file:
        fieldnames = list(trial_rows[0].keys())
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(trial_rows)
    return path


def write_summary(
    results: list[OptimizedResult],
    reference: dict[str, float],
    threshold: dict[str, Any],
    arguments: argparse.Namespace,
) -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    path = RESULTS_DIR / "complete_stack_reoptimization_summary.json"
    best = max(results, key=lambda item: item.relative_gain_vs_baseline_percent)
    positive = [item for item in results if item.passes_positive_gain_gate]
    highest_positive = (
        max(positive, key=lambda item: item.carrier_refractive_index)
        if positive
        else None
    )

    if highest_positive is None:
        decision = (
            "No sampled carrier index retained positive gain. Prefer the direct "
            "removable-coating concept or redesign the physical stack."
        )
    else:
        decision = (
            "A low-index optical-contact carrier remains numerically feasible. "
            "Use the interpolated crossing as a carrier-index design target, then "
            "verify candidate materials with measured dispersion and absorption."
        )

    payload = {
        "model": "Complete-stack Optuna re-optimization with phase-averaged TMM",
        "status": "Engineering feasibility screen only",
        "stack": "air -> optimized retrofit coating -> carrier -> assumed existing AR -> glass",
        "interface": "optical contact",
        "carrier_thickness_um": CARRIER_THICKNESS_UM,
        "carrier_refractive_indices": CARRIER_REFRACTIVE_INDICES,
        "retrofit_search_space": {
            "refractive_index": [RETROFIT_INDEX_MIN, RETROFIT_INDEX_MAX],
            "thickness_nm": [
                RETROFIT_THICKNESS_MIN_NM,
                RETROFIT_THICKNESS_MAX_NM,
            ],
        },
        "optimization": {
            "sampler": "Optuna TPE with deterministic per-index seed",
            "trials_per_carrier_index": arguments.trials_per_index,
            "optimization_phase_samples": arguments.phase_samples,
            "validation_phase_samples": arguments.validation_phase_samples,
            "random_seed_base": RANDOM_SEED,
        },
        "reference_results": reference,
        "number_of_positive_sampled_carrier_indices": len(positive),
        "best_overall_result": asdict(best),
        "highest_sampled_positive_index_result": (
            asdict(highest_positive) if highest_positive is not None else None
        ),
        "zero_gain_boundary": threshold,
        "decision": decision,
        "results": [asdict(item) for item in results],
        "limitations": [
            "Carrier indices are generic constants, not commercial-material assignments.",
            "All layers are lossless and nondispersive.",
            "Normal incidence only; angle and polarization are not included.",
            "The existing AR layer remains an unverified n=1.28, 100 nm assumption.",
            "Positive optical gain is not electrical or annual-energy gain.",
        ],
    }
    with path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2, allow_nan=False)
        file.write("\n")
    return path


def write_optimization_figure(
    results: list[OptimizedResult],
    threshold: dict[str, Any],
) -> Path:
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    path = FIGURES_DIR / "complete_stack_reoptimization.png"
    ordered = sorted(results, key=lambda item: item.carrier_refractive_index)
    carrier_indices = np.array(
        [item.carrier_refractive_index for item in ordered],
        dtype=float,
    )
    gains = np.array(
        [item.relative_gain_vs_baseline_percent for item in ordered],
        dtype=float,
    )
    retrofit_indices = np.array(
        [item.optimized_retrofit_refractive_index for item in ordered],
        dtype=float,
    )
    retrofit_thicknesses = np.array(
        [item.optimized_retrofit_thickness_nm for item in ordered],
        dtype=float,
    )

    figure, axes = plt.subplots(3, 1, figsize=(8.2, 8.0), sharex=True)
    figure.subplots_adjust(left=0.12, right=0.96, bottom=0.10, top=0.91, hspace=0.13)

    axes[0].plot(carrier_indices, gains, marker="o", color="#1976d2")
    axes[0].axhline(0.0, color="black", linewidth=1.0, linestyle="--")
    axes[0].fill_between(
        carrier_indices,
        gains,
        0.0,
        where=gains >= 0.0,
        color="#43a047",
        alpha=0.18,
    )
    axes[0].fill_between(
        carrier_indices,
        gains,
        0.0,
        where=gains < 0.0,
        color="#e53935",
        alpha=0.15,
    )
    axes[0].set_ylabel("Relative gain (%)")
    axes[0].grid(alpha=0.25)

    crossings = threshold["crossings"]
    if crossings:
        crossing_index = crossings[0][
            "interpolated_zero_gain_carrier_refractive_index"
        ]
        axes[0].axvline(
            crossing_index,
            color="#f57c00",
            linewidth=1.3,
            linestyle=":",
            label=f"Estimated zero-gain n = {crossing_index:.3f}",
        )
        axes[0].legend(fontsize=8)

    axes[1].plot(carrier_indices, retrofit_indices, marker="o", color="#7b1fa2")
    axes[1].plot(
        carrier_indices,
        np.sqrt(carrier_indices),
        linestyle="--",
        color="#757575",
        label="sqrt(n_carrier) reference",
    )
    axes[1].set_ylabel("Optimized coating n")
    axes[1].grid(alpha=0.25)
    axes[1].legend(fontsize=8)

    axes[2].plot(
        carrier_indices,
        retrofit_thicknesses,
        marker="o",
        color="#00897b",
    )
    axes[2].set_ylabel("Optimized thickness (nm)")
    axes[2].set_xlabel("Generic carrier refractive index")
    axes[2].grid(alpha=0.25)

    figure.suptitle("SolarFlow Complete-Stack Re-optimization")
    figure.savefig(path, dpi=220)
    plt.close(figure)
    return path


def write_spectra_figure(
    results: list[OptimizedResult],
    reference_spectra: dict[str, np.ndarray],
    candidate_spectra: dict[float, np.ndarray],
    wavelength_nm: np.ndarray,
) -> Path:
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    path = FIGURES_DIR / "complete_stack_reoptimization_spectra.png"

    positive = [item for item in results if item.passes_positive_gain_gate]
    selected = (
        max(positive, key=lambda item: item.carrier_refractive_index)
        if positive
        else max(results, key=lambda item: item.relative_gain_vs_baseline_percent)
    )

    figure, axis = plt.subplots(figsize=(8.5, 4.9))
    axis.plot(
        wavelength_nm,
        100.0 * reference_spectra["baseline_transmittance"],
        label="Baseline: existing AR",
        linewidth=1.7,
    )
    axis.plot(
        wavelength_nm,
        100.0 * reference_spectra["active_only_transmittance"],
        label="Active-only ideal stack",
        linewidth=1.7,
    )
    axis.plot(
        wavelength_nm,
        100.0 * candidate_spectra[selected.carrier_refractive_index],
        label=(
            "Boundary candidate: "
            f"carrier n={selected.carrier_refractive_index:.2f}, "
            f"coating n={selected.optimized_retrofit_refractive_index:.3f}, "
            f"d={selected.optimized_retrofit_thickness_nm:.1f} nm"
        ),
        linewidth=1.7,
    )
    axis.set_title("SolarFlow Re-optimized Complete-Stack Spectrum")
    axis.set_xlabel("Wavelength (nm)")
    axis.set_ylabel("Transmittance (%)")
    axis.grid(alpha=0.25)
    axis.legend(fontsize=8)
    figure.tight_layout()
    figure.savefig(path, dpi=220)
    plt.close(figure)
    return path


def print_results(
    results: list[OptimizedResult],
    reference: dict[str, float],
    threshold: dict[str, Any],
    outputs: list[Path],
) -> None:
    ordered = sorted(results, key=lambda item: item.carrier_refractive_index)
    print("Complete-stack Optuna re-optimization completed.")
    print(f"Incident power in band : {reference['incident_power_w_m2']:.3f} W/m²")
    print(f"Baseline power         : {reference['baseline_power_w_m2']:.3f} W/m²")
    print(
        "Active-only gain       : "
        f"{reference['active_only_relative_gain_percent']:+.4f}%\n"
    )
    print(
        "carrier n   coating n   coating d   power       gain       gate"
    )
    for result in ordered:
        gate = "PASS" if result.passes_positive_gain_gate else "FAIL"
        print(
            f"   {result.carrier_refractive_index:.2f}       "
            f"{result.optimized_retrofit_refractive_index:.4f}      "
            f"{result.optimized_retrofit_thickness_nm:6.1f} nm   "
            f"{result.transmitted_power_w_m2:7.3f}   "
            f"{result.relative_gain_vs_baseline_percent:+8.4f}%   "
            f"{gate}"
        )

    positive = [item for item in ordered if item.passes_positive_gain_gate]
    print()
    if positive:
        highest_positive = positive[-1]
        print(
            "Highest sampled positive carrier n : "
            f"{highest_positive.carrier_refractive_index:.2f}"
        )
        print(
            "Its optimized coating              : "
            f"n={highest_positive.optimized_retrofit_refractive_index:.5f}, "
            f"d={highest_positive.optimized_retrofit_thickness_nm:.2f} nm"
        )
        print(
            "Its relative optical gain          : "
            f"{highest_positive.relative_gain_vs_baseline_percent:+.4f}%"
        )
    else:
        print("No sampled carrier index passed the positive-gain gate.")

    crossings = threshold["crossings"]
    if crossings:
        print(
            "Interpolated zero-gain carrier n    : "
            f"{crossings[0]['interpolated_zero_gain_carrier_refractive_index']:.4f}"
        )
    else:
        print("Interpolated zero-gain carrier n    : not bracketed")

    print("\nOutputs")
    for output in outputs:
        print(f"- {output}")
    print(
        "\nWARNING: This boundary is a generic-index feasibility screen, not a "
        "commercial material selection or electrical-power claim."
    )


def run_self_test() -> None:
    screen.run_self_test()

    sample_results = [
        OptimizedResult(
            carrier_refractive_index=1.20,
            carrier_thickness_um=50.0,
            optimized_retrofit_refractive_index=1.10,
            optimized_retrofit_thickness_nm=130.0,
            transmitted_power_w_m2=830.0,
            weighted_transmittance_percent=99.0,
            additional_power_vs_baseline_w_m2=2.0,
            absolute_gain_vs_baseline_percentage_points=0.2,
            relative_gain_vs_baseline_percent=0.20,
            gain_retention_vs_active_only_percent=30.0,
            maximum_energy_residual=1e-15,
            optimization_trial_number=1,
            passes_positive_gain_gate=True,
        ),
        OptimizedResult(
            carrier_refractive_index=1.22,
            carrier_thickness_um=50.0,
            optimized_retrofit_refractive_index=1.11,
            optimized_retrofit_thickness_nm=130.0,
            transmitted_power_w_m2=826.0,
            weighted_transmittance_percent=98.5,
            additional_power_vs_baseline_w_m2=-2.0,
            absolute_gain_vs_baseline_percentage_points=-0.2,
            relative_gain_vs_baseline_percent=-0.20,
            gain_retention_vs_active_only_percent=-30.0,
            maximum_energy_residual=1e-15,
            optimization_trial_number=2,
            passes_positive_gain_gate=False,
        ),
    ]
    threshold = estimate_zero_crossing(sample_results)
    crossing = threshold["crossings"][0][
        "interpolated_zero_gain_carrier_refractive_index"
    ]
    if not math.isclose(crossing, 1.21, abs_tol=1e-12):
        raise AssertionError("Zero-gain interpolation self-test failed.")

    test_wavelengths = np.array([400.0, 550.0, 900.0])
    _, _, residual = complete_stack_response(
        wavelength_nm=test_wavelengths,
        carrier_refractive_index=1.25,
        retrofit_refractive_index=1.12,
        retrofit_thickness_nm=130.0,
        phase_samples=5,
    )
    if float(np.max(residual)) >= 1e-12:
        raise AssertionError("Complete-stack energy-conservation self-test failed.")
    print("Complete-stack optimizer self-test passed.")


def main() -> None:
    arguments = parse_arguments()
    if arguments.self_test:
        run_self_test()
        return

    if arguments.trials_per_index < 2:
        raise SystemExit("--trials-per-index must be at least 2")
    if arguments.phase_samples < 1 or arguments.validation_phase_samples < 1:
        raise SystemExit("Phase sample counts must be at least 1")

    wavelength_nm = screen.wavelengths_nm()
    power_density_w_m2_nm = screen.load_am15g_power_density(wavelength_nm)
    reference, reference_spectra = calculate_references(
        wavelength_nm,
        power_density_w_m2_nm,
    )

    results: list[OptimizedResult] = []
    all_trial_rows: list[dict[str, Any]] = []
    candidate_spectra: dict[float, np.ndarray] = {}

    for position, carrier_index in enumerate(
        CARRIER_REFRACTIVE_INDICES,
        start=1,
    ):
        print(
            f"Optimizing carrier n={carrier_index:.2f} "
            f"({position}/{len(CARRIER_REFRACTIVE_INDICES)}) ..."
        )
        result, trial_rows, transmittance = optimize_for_carrier_index(
            carrier_refractive_index=carrier_index,
            wavelength_nm=wavelength_nm,
            power_density_w_m2_nm=power_density_w_m2_nm,
            baseline_power_w_m2=reference["baseline_power_w_m2"],
            trials_per_index=arguments.trials_per_index,
            phase_samples=arguments.phase_samples,
            validation_phase_samples=arguments.validation_phase_samples,
        )
        results.append(result)
        all_trial_rows.extend(trial_rows)
        candidate_spectra[carrier_index] = transmittance
        print(
            f"  best coating n={result.optimized_retrofit_refractive_index:.5f}, "
            f"d={result.optimized_retrofit_thickness_nm:.2f} nm, "
            f"gain={result.relative_gain_vs_baseline_percent:+.4f}%"
        )

    threshold = estimate_zero_crossing(results)
    best_results_path = write_best_results_csv(results)
    trials_path = write_trials_csv(all_trial_rows)
    summary_path = write_summary(results, reference, threshold, arguments)
    optimization_figure_path = write_optimization_figure(results, threshold)
    spectra_figure_path = write_spectra_figure(
        results,
        reference_spectra,
        candidate_spectra,
        wavelength_nm,
    )
    print_results(
        results,
        reference,
        threshold,
        [
            best_results_path,
            trials_path,
            summary_path,
            optimization_figure_path,
            spectra_figure_path,
        ],
    )


if __name__ == "__main__":
    main()
