"""Optimize practical support layers for the SolarFlow direct coating.

Four coherent, normal-incidence TMM stacks are compared under the Solcore
AM1.5G spectrum from 300 to 1200 nm:

1. air -> active coating -> existing AR -> glass
2. air -> protective topcoat -> active coating -> existing AR -> glass
3. air -> active coating -> release primer -> existing AR -> glass
4. air -> protective topcoat -> active coating -> release primer
       -> existing AR -> glass

Optuna re-optimizes every included layer.  Protective and release layers are
generic lossless index/thickness ranges, not selected materials.  The purpose
is to determine whether adding practical functions immediately destroys the
modeled optical margin, not to produce a manufacturing recipe.
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


ACTIVE_INDEX_RANGE = (1.02, 1.30)
ACTIVE_THICKNESS_RANGE_NM = (50.0, 250.0)
PROTECTIVE_INDEX_RANGE = (1.30, 1.55)
PROTECTIVE_THICKNESS_RANGE_NM = (50.0, 300.0)
RELEASE_INDEX_RANGE = (1.20, 1.50)
RELEASE_THICKNESS_RANGE_NM = (20.0, 150.0)

DEFAULT_TRIALS_PER_SCENARIO = 240
RANDOM_SEED = 20260831
PROVISIONAL_PRACTICAL_MARGIN_PERCENT = 0.10

REPO_ROOT = Path(__file__).resolve().parents[2]
RESULTS_DIR = REPO_ROOT / "product1" / "results"
FIGURES_DIR = RESULTS_DIR / "figures"


@dataclass(frozen=True)
class Scenario:
    name: str
    include_protective_topcoat: bool
    include_release_primer: bool
    description: str


SCENARIOS = (
    Scenario(
        name="active_only_reference",
        include_protective_topcoat=False,
        include_release_primer=False,
        description="Re-optimized direct active coating without a support layer.",
    ),
    Scenario(
        name="protective_topcoat",
        include_protective_topcoat=True,
        include_release_primer=False,
        description="Generic protective layer above the active coating.",
    ),
    Scenario(
        name="release_primer",
        include_protective_topcoat=False,
        include_release_primer=True,
        description="Generic removal-support layer below the active coating.",
    ),
    Scenario(
        name="protective_and_release",
        include_protective_topcoat=True,
        include_release_primer=True,
        description="Both generic protective and removal-support layers.",
    ),
)


@dataclass(frozen=True)
class OptimizedScenarioResult:
    scenario: str
    active_refractive_index: float
    active_thickness_nm: float
    protective_refractive_index: float | None
    protective_thickness_nm: float | None
    release_refractive_index: float | None
    release_thickness_nm: float | None
    transmitted_power_w_m2: float
    weighted_transmittance_percent: float
    additional_power_vs_baseline_w_m2: float
    absolute_gain_vs_baseline_percentage_points: float
    relative_gain_vs_baseline_percent: float
    gain_retention_vs_validated_active_percent: float
    maximum_energy_residual: float
    best_trial_number: int
    passes_positive_gain_gate: bool
    passes_provisional_practical_margin_gate: bool
    active_parameter_near_boundary: bool
    protective_parameter_near_boundary: bool | None
    release_parameter_near_boundary: bool | None


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Optimize practical layers for the SolarFlow direct coating."
    )
    parser.add_argument(
        "--trials-per-scenario",
        type=int,
        default=DEFAULT_TRIALS_PER_SCENARIO,
        help=(
            "Number of Optuna trials for each of four scenarios "
            f"(default: {DEFAULT_TRIALS_PER_SCENARIO})."
        ),
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run optical-kernel checks without importing Solcore or Optuna.",
    )
    return parser.parse_args()


def stack_response(
    wavelength_nm: np.ndarray,
    scenario: Scenario,
    active_refractive_index: float,
    active_thickness_nm: float,
    protective_refractive_index: float | None = None,
    protective_thickness_nm: float | None = None,
    release_refractive_index: float | None = None,
    release_thickness_nm: float | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return R, T and energy residual for one direct-coating stack."""
    layers: list[tuple[float, float]] = []

    if scenario.include_protective_topcoat:
        if protective_refractive_index is None or protective_thickness_nm is None:
            raise ValueError("Protective-layer parameters are required.")
        layers.append(
            (protective_refractive_index, protective_thickness_nm)
        )

    layers.append((active_refractive_index, active_thickness_nm))

    if scenario.include_release_primer:
        if release_refractive_index is None or release_thickness_nm is None:
            raise ValueError("Release-layer parameters are required.")
        layers.append((release_refractive_index, release_thickness_nm))

    layers.append(
        (
            screen.EXISTING_AR_REFRACTIVE_INDEX,
            screen.EXISTING_AR_THICKNESS_NM,
        )
    )
    return screen.optical_response(layers, wavelength_nm)


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
    validated_r, validated_t, validated_residual = screen.optical_response(
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
    validated_power = screen.solar_weighted_power(
        validated_t,
        power_density_w_m2_nm,
        wavelength_nm,
    )
    validated_additional_power = validated_power - baseline_power

    reference = {
        "incident_power_w_m2": incident_power,
        "baseline_power_w_m2": baseline_power,
        "baseline_weighted_transmittance_percent": 100.0
        * baseline_power
        / incident_power,
        "validated_active_power_w_m2": validated_power,
        "validated_active_additional_power_w_m2": validated_additional_power,
        "validated_active_relative_gain_percent": 100.0
        * validated_additional_power
        / baseline_power,
        "baseline_maximum_energy_residual": float(np.max(baseline_residual)),
        "validated_active_maximum_energy_residual": float(
            np.max(validated_residual)
        ),
    }
    spectra = {
        "baseline_reflectance": baseline_r,
        "baseline_transmittance": baseline_t,
        "validated_active_reflectance": validated_r,
        "validated_active_transmittance": validated_t,
    }
    return reference, spectra


def near_boundary(
    value: float,
    bounds: tuple[float, float],
    fraction: float = 0.03,
) -> bool:
    lower, upper = bounds
    tolerance = fraction * (upper - lower)
    return value <= lower + tolerance or value >= upper - tolerance


def suggest_parameters(trial: Any, scenario: Scenario) -> dict[str, float | None]:
    parameters: dict[str, float | None] = {
        "active_refractive_index": trial.suggest_float(
            "active_refractive_index",
            *ACTIVE_INDEX_RANGE,
        ),
        "active_thickness_nm": trial.suggest_float(
            "active_thickness_nm",
            *ACTIVE_THICKNESS_RANGE_NM,
        ),
        "protective_refractive_index": None,
        "protective_thickness_nm": None,
        "release_refractive_index": None,
        "release_thickness_nm": None,
    }
    if scenario.include_protective_topcoat:
        parameters["protective_refractive_index"] = trial.suggest_float(
            "protective_refractive_index",
            *PROTECTIVE_INDEX_RANGE,
        )
        parameters["protective_thickness_nm"] = trial.suggest_float(
            "protective_thickness_nm",
            *PROTECTIVE_THICKNESS_RANGE_NM,
        )
    if scenario.include_release_primer:
        parameters["release_refractive_index"] = trial.suggest_float(
            "release_refractive_index",
            *RELEASE_INDEX_RANGE,
        )
        parameters["release_thickness_nm"] = trial.suggest_float(
            "release_thickness_nm",
            *RELEASE_THICKNESS_RANGE_NM,
        )
    return parameters


def enqueue_starting_points(study: Any, scenario: Scenario) -> None:
    validated: dict[str, float] = {
        "active_refractive_index": screen.RETROFIT_REFRACTIVE_INDEX,
        "active_thickness_nm": screen.RETROFIT_THICKNESS_NM,
    }
    if scenario.include_protective_topcoat:
        validated.update(
            {
                "protective_refractive_index": PROTECTIVE_INDEX_RANGE[0],
                "protective_thickness_nm": PROTECTIVE_THICKNESS_RANGE_NM[0],
            }
        )
    if scenario.include_release_primer:
        validated.update(
            {
                "release_refractive_index": 1.28,
                "release_thickness_nm": RELEASE_THICKNESS_RANGE_NM[0],
            }
        )
    study.enqueue_trial(validated)

    quarter_wave: dict[str, float] = {
        "active_refractive_index": math.sqrt(1.28),
        "active_thickness_nm": 600.0 / (4.0 * math.sqrt(1.28)),
    }
    if scenario.include_protective_topcoat:
        quarter_wave.update(
            {
                "protective_refractive_index": 1.30,
                "protective_thickness_nm": 75.0,
            }
        )
    if scenario.include_release_primer:
        quarter_wave.update(
            {
                "release_refractive_index": 1.28,
                "release_thickness_nm": 25.0,
            }
        )
    study.enqueue_trial(quarter_wave)


def optimize_scenario(
    scenario: Scenario,
    wavelength_nm: np.ndarray,
    power_density_w_m2_nm: np.ndarray,
    reference: dict[str, float],
    trials_per_scenario: int,
) -> tuple[OptimizedScenarioResult, list[dict[str, Any]], np.ndarray]:
    try:
        import optuna
    except ImportError as error:
        raise RuntimeError(
            "Optuna is required. Activate solarflow-full and install Optuna if missing."
        ) from error

    optuna.logging.set_verbosity(optuna.logging.WARNING)
    scenario_position = [item.name for item in SCENARIOS].index(scenario.name)
    sampler = optuna.samplers.TPESampler(
        seed=RANDOM_SEED + scenario_position,
        n_startup_trials=min(40, max(12, trials_per_scenario // 5)),
    )
    study = optuna.create_study(direction="maximize", sampler=sampler)
    enqueue_starting_points(study, scenario)

    def objective(trial: Any) -> float:
        parameters = suggest_parameters(trial, scenario)
        _, transmittance, _ = stack_response(
            wavelength_nm=wavelength_nm,
            scenario=scenario,
            **parameters,
        )
        power = screen.solar_weighted_power(
            transmittance,
            power_density_w_m2_nm,
            wavelength_nm,
        )
        return 100.0 * (
            power / reference["baseline_power_w_m2"] - 1.0
        )

    study.optimize(
        objective,
        n_trials=trials_per_scenario,
        show_progress_bar=False,
    )

    best = study.best_params
    parameters: dict[str, float | None] = {
        "active_refractive_index": float(best["active_refractive_index"]),
        "active_thickness_nm": float(best["active_thickness_nm"]),
        "protective_refractive_index": (
            float(best["protective_refractive_index"])
            if scenario.include_protective_topcoat
            else None
        ),
        "protective_thickness_nm": (
            float(best["protective_thickness_nm"])
            if scenario.include_protective_topcoat
            else None
        ),
        "release_refractive_index": (
            float(best["release_refractive_index"])
            if scenario.include_release_primer
            else None
        ),
        "release_thickness_nm": (
            float(best["release_thickness_nm"])
            if scenario.include_release_primer
            else None
        ),
    }
    _, final_transmittance, final_residual = stack_response(
        wavelength_nm=wavelength_nm,
        scenario=scenario,
        **parameters,
    )
    transmitted_power = screen.solar_weighted_power(
        final_transmittance,
        power_density_w_m2_nm,
        wavelength_nm,
    )
    incident_power = reference["incident_power_w_m2"]
    baseline_power = reference["baseline_power_w_m2"]
    additional_power = transmitted_power - baseline_power
    relative_gain = 100.0 * additional_power / baseline_power
    validated_additional = reference["validated_active_additional_power_w_m2"]
    retention = (
        100.0 * additional_power / validated_additional
        if validated_additional > 0.0
        else float("nan")
    )

    active_boundary = near_boundary(
        float(parameters["active_refractive_index"]),
        ACTIVE_INDEX_RANGE,
    ) or near_boundary(
        float(parameters["active_thickness_nm"]),
        ACTIVE_THICKNESS_RANGE_NM,
    )
    protective_boundary = (
        near_boundary(
            float(parameters["protective_refractive_index"]),
            PROTECTIVE_INDEX_RANGE,
        )
        or near_boundary(
            float(parameters["protective_thickness_nm"]),
            PROTECTIVE_THICKNESS_RANGE_NM,
        )
        if scenario.include_protective_topcoat
        else None
    )
    release_boundary = (
        near_boundary(
            float(parameters["release_refractive_index"]),
            RELEASE_INDEX_RANGE,
        )
        or near_boundary(
            float(parameters["release_thickness_nm"]),
            RELEASE_THICKNESS_RANGE_NM,
        )
        if scenario.include_release_primer
        else None
    )

    result = OptimizedScenarioResult(
        scenario=scenario.name,
        active_refractive_index=float(parameters["active_refractive_index"]),
        active_thickness_nm=float(parameters["active_thickness_nm"]),
        protective_refractive_index=parameters["protective_refractive_index"],
        protective_thickness_nm=parameters["protective_thickness_nm"],
        release_refractive_index=parameters["release_refractive_index"],
        release_thickness_nm=parameters["release_thickness_nm"],
        transmitted_power_w_m2=transmitted_power,
        weighted_transmittance_percent=100.0
        * transmitted_power
        / incident_power,
        additional_power_vs_baseline_w_m2=additional_power,
        absolute_gain_vs_baseline_percentage_points=100.0
        * additional_power
        / incident_power,
        relative_gain_vs_baseline_percent=relative_gain,
        gain_retention_vs_validated_active_percent=retention,
        maximum_energy_residual=float(np.max(final_residual)),
        best_trial_number=int(study.best_trial.number),
        passes_positive_gain_gate=relative_gain > 0.0,
        passes_provisional_practical_margin_gate=(
            relative_gain >= PROVISIONAL_PRACTICAL_MARGIN_PERCENT
        ),
        active_parameter_near_boundary=active_boundary,
        protective_parameter_near_boundary=protective_boundary,
        release_parameter_near_boundary=release_boundary,
    )

    trial_rows: list[dict[str, Any]] = []
    for trial in study.trials:
        if trial.value is None:
            continue
        row: dict[str, Any] = {
            "scenario": scenario.name,
            "trial_number": int(trial.number),
            "relative_gain_percent": float(trial.value),
            "trial_state": str(trial.state.name),
        }
        row.update(trial.params)
        trial_rows.append(row)

    return result, trial_rows, final_transmittance


def write_results_csv(results: list[OptimizedScenarioResult]) -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    path = RESULTS_DIR / "direct_coating_support_layer_optimization.csv"
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(asdict(results[0]).keys()))
        writer.writeheader()
        writer.writerows(asdict(item) for item in results)
    return path


def write_trials_csv(trials: list[dict[str, Any]]) -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    path = RESULTS_DIR / "direct_coating_support_layer_trials.csv"
    fieldnames = [
        "scenario",
        "trial_number",
        "relative_gain_percent",
        "trial_state",
        "active_refractive_index",
        "active_thickness_nm",
        "protective_refractive_index",
        "protective_thickness_nm",
        "release_refractive_index",
        "release_thickness_nm",
    ]
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        for trial in trials:
            writer.writerow({field: trial.get(field) for field in fieldnames})
    return path


def decision_from_results(results: list[OptimizedScenarioResult]) -> str:
    by_name = {result.scenario: result for result in results}
    complete = by_name["protective_and_release"]
    protective = by_name["protective_topcoat"]
    release = by_name["release_primer"]

    if complete.passes_provisional_practical_margin_gate:
        return (
            "The complete protective-plus-release stack retains the provisional "
            "optical margin. Advance it to angle/polarization screening, while "
            "retaining all generic-material caveats."
        )
    if protective.passes_provisional_practical_margin_gate:
        return (
            "The protective-only stack retains margin, but the release layer does "
            "not. Advance the protective stack and treat removability as a chemical "
            "or process requirement rather than a separate optical layer."
        )
    if release.passes_provisional_practical_margin_gate:
        return (
            "The release-only stack retains margin, but the protective layer does "
            "not. Advance the release stack and redesign protection without adding "
            "the screened topcoat."
        )
    return (
        "No support-layer scenario retains the provisional margin. Keep the bare "
        "direct coating as the optical reference and solve durability/removability "
        "through material chemistry or process design before adding optical layers."
    )


def write_summary(
    results: list[OptimizedScenarioResult],
    reference: dict[str, float],
    trials_per_scenario: int,
) -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    path = RESULTS_DIR / "direct_coating_support_layer_summary.json"
    payload = {
        "model": "AM1.5G-weighted coherent TMM support-layer optimization",
        "status": "Engineering screen only; generic layers, not selected materials",
        "stacks": [asdict(scenario) for scenario in SCENARIOS],
        "search_ranges": {
            "active_refractive_index": ACTIVE_INDEX_RANGE,
            "active_thickness_nm": ACTIVE_THICKNESS_RANGE_NM,
            "protective_refractive_index": PROTECTIVE_INDEX_RANGE,
            "protective_thickness_nm": PROTECTIVE_THICKNESS_RANGE_NM,
            "release_refractive_index": RELEASE_INDEX_RANGE,
            "release_thickness_nm": RELEASE_THICKNESS_RANGE_NM,
        },
        "optimization": {
            "algorithm": "Optuna TPE",
            "trials_per_scenario": trials_per_scenario,
            "random_seed_base": RANDOM_SEED,
        },
        "provisional_practical_margin_percent": PROVISIONAL_PRACTICAL_MARGIN_PERCENT,
        "reference_results": reference,
        "results": [asdict(result) for result in results],
        "decision": decision_from_results(results),
        "limitations": [
            "Normal incidence only; angle and polarization are not included.",
            "All refractive indices are lossless and nondispersive.",
            "Layer ranges are generic and do not identify commercial materials.",
            "Mechanical protection and removability are not proven by optical optimization.",
            "The existing AR remains an assumed n=1.28, 100 nm layer.",
            "Optical transmission gain is not electrical or annual-energy gain.",
        ],
    }
    with path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2, allow_nan=False)
        file.write("\n")
    return path


def write_comparison_figure(results: list[OptimizedScenarioResult]) -> Path:
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    path = FIGURES_DIR / "direct_coating_support_layer_optimization.png"
    labels = [
        "Active\nonly",
        "Protective\ntopcoat",
        "Release\nprimer",
        "Protective +\nrelease",
    ]
    gains = np.array(
        [result.relative_gain_vs_baseline_percent for result in results]
    )
    colors = ["#2e7d32" if value >= 0.0 else "#c62828" for value in gains]

    figure, axis = plt.subplots(figsize=(8.2, 4.9))
    bars = axis.bar(labels, gains, color=colors, alpha=0.88)
    axis.axhline(0.0, color="black", linewidth=1.0)
    axis.axhline(
        PROVISIONAL_PRACTICAL_MARGIN_PERCENT,
        color="#ef6c00",
        linestyle="--",
        linewidth=1.2,
        label=f"Provisional margin gate: {PROVISIONAL_PRACTICAL_MARGIN_PERCENT:.2f}%",
    )
    for bar, value in zip(bars, gains):
        vertical = 4 if value >= 0.0 else -14
        axis.annotate(
            f"{value:+.4f}%",
            (bar.get_x() + bar.get_width() / 2.0, value),
            xytext=(0, vertical),
            textcoords="offset points",
            ha="center",
            va="bottom" if value >= 0.0 else "top",
            fontsize=9,
        )
    axis.set_title("SolarFlow Direct-Coating Support-Layer Screen")
    axis.set_ylabel("AM1.5G-weighted relative optical gain (%)")
    axis.grid(axis="y", alpha=0.25)
    axis.legend(fontsize=8)
    figure.tight_layout()
    figure.savefig(path, dpi=220)
    plt.close(figure)
    return path


def write_spectra_figure(
    results: list[OptimizedScenarioResult],
    reference_spectra: dict[str, np.ndarray],
    optimized_spectra: dict[str, np.ndarray],
    wavelength_nm: np.ndarray,
) -> Path:
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    path = FIGURES_DIR / "direct_coating_support_layer_spectra.png"

    figure, axis = plt.subplots(figsize=(8.6, 5.0))
    axis.plot(
        wavelength_nm,
        100.0 * reference_spectra["baseline_transmittance"],
        label="Baseline existing AR",
        linewidth=1.8,
    )
    axis.plot(
        wavelength_nm,
        100.0 * reference_spectra["validated_active_transmittance"],
        label="Validated active-only candidate",
        linewidth=1.8,
    )
    for result in results:
        if result.scenario == "active_only_reference":
            continue
        axis.plot(
            wavelength_nm,
            100.0 * optimized_spectra[result.scenario],
            label=result.scenario.replace("_", " "),
            linewidth=1.35,
            alpha=0.9,
        )
    axis.set_title("SolarFlow Optimized Support-Layer Spectra")
    axis.set_xlabel("Wavelength (nm)")
    axis.set_ylabel("Transmittance (%)")
    axis.grid(alpha=0.25)
    axis.legend(fontsize=8)
    figure.tight_layout()
    figure.savefig(path, dpi=220)
    plt.close(figure)
    return path


def print_results(
    results: list[OptimizedScenarioResult],
    reference: dict[str, float],
    outputs: list[Path],
) -> None:
    print("Direct-coating practical-layer optimization completed.")
    print(f"Incident power in band : {reference['incident_power_w_m2']:.3f} W/m²")
    print(f"Baseline power         : {reference['baseline_power_w_m2']:.3f} W/m²")
    print(
        "Validated active gain  : "
        f"{reference['validated_active_relative_gain_percent']:+.4f}%\n"
    )
    print(
        "scenario                     gain       retained    margin gate  boundary flag"
    )
    for result in results:
        boundary_flag = any(
            flag is True
            for flag in (
                result.active_parameter_near_boundary,
                result.protective_parameter_near_boundary,
                result.release_parameter_near_boundary,
            )
        )
        gate = (
            "PASS"
            if result.passes_provisional_practical_margin_gate
            else "FAIL"
        )
        print(
            f"{result.scenario:<28} "
            f"{result.relative_gain_vs_baseline_percent:>+8.4f}%   "
            f"{result.gain_retention_vs_validated_active_percent:>+8.2f}%   "
            f"{gate:^11}  "
            f"{'YES' if boundary_flag else 'NO'}"
        )
        print(
            "  active     : "
            f"n={result.active_refractive_index:.5f}, "
            f"d={result.active_thickness_nm:.2f} nm"
        )
        if result.protective_refractive_index is not None:
            print(
                "  protective : "
                f"n={result.protective_refractive_index:.5f}, "
                f"d={result.protective_thickness_nm:.2f} nm"
            )
        if result.release_refractive_index is not None:
            print(
                "  release    : "
                f"n={result.release_refractive_index:.5f}, "
                f"d={result.release_thickness_nm:.2f} nm"
            )

    print("\nDecision")
    print(decision_from_results(results))
    print("\nOutputs")
    for output in outputs:
        print(f"- {output}")
    print(
        "\nWARNING: Generic lossless layers only. A PASS does not prove protection, "
        "removability, manufacturability or electrical gain."
    )


def run_self_test() -> None:
    screen.run_self_test()
    wavelength_nm = np.array([350.0, 550.0, 1000.0])
    for scenario in SCENARIOS:
        kwargs: dict[str, float | None] = {
            "protective_refractive_index": 1.35
            if scenario.include_protective_topcoat
            else None,
            "protective_thickness_nm": 80.0
            if scenario.include_protective_topcoat
            else None,
            "release_refractive_index": 1.28
            if scenario.include_release_primer
            else None,
            "release_thickness_nm": 30.0
            if scenario.include_release_primer
            else None,
        }
        _, _, residual = stack_response(
            wavelength_nm=wavelength_nm,
            scenario=scenario,
            active_refractive_index=1.10,
            active_thickness_nm=120.0,
            **kwargs,
        )
        if float(np.max(residual)) >= 1e-12:
            raise AssertionError(
                f"Energy-conservation self-test failed for {scenario.name}."
            )

    if not near_boundary(1.021, ACTIVE_INDEX_RANGE):
        raise AssertionError("Lower-bound detection self-test failed.")
    if near_boundary(1.15, ACTIVE_INDEX_RANGE):
        raise AssertionError("Interior boundary detection self-test failed.")
    print("Direct-coating support-layer optimizer self-test passed.")


def main() -> None:
    arguments = parse_arguments()
    if arguments.self_test:
        run_self_test()
        return
    if arguments.trials_per_scenario < 4:
        raise SystemExit("--trials-per-scenario must be at least 4")

    wavelength_nm = screen.wavelengths_nm()
    power_density_w_m2_nm = screen.load_am15g_power_density(wavelength_nm)
    reference, reference_spectra = calculate_references(
        wavelength_nm,
        power_density_w_m2_nm,
    )

    results: list[OptimizedScenarioResult] = []
    trial_rows: list[dict[str, Any]] = []
    optimized_spectra: dict[str, np.ndarray] = {}
    for position, scenario in enumerate(SCENARIOS, start=1):
        print(
            f"Optimizing {scenario.name} ({position}/{len(SCENARIOS)}) ..."
        )
        result, scenario_trials, transmittance = optimize_scenario(
            scenario=scenario,
            wavelength_nm=wavelength_nm,
            power_density_w_m2_nm=power_density_w_m2_nm,
            reference=reference,
            trials_per_scenario=arguments.trials_per_scenario,
        )
        results.append(result)
        trial_rows.extend(scenario_trials)
        optimized_spectra[scenario.name] = transmittance
        print(
            f"  gain={result.relative_gain_vs_baseline_percent:+.4f}%, "
            f"active n={result.active_refractive_index:.5f}, "
            f"d={result.active_thickness_nm:.2f} nm"
        )

    results_path = write_results_csv(results)
    trials_path = write_trials_csv(trial_rows)
    summary_path = write_summary(
        results,
        reference,
        arguments.trials_per_scenario,
    )
    comparison_path = write_comparison_figure(results)
    spectra_path = write_spectra_figure(
        results,
        reference_spectra,
        optimized_spectra,
        wavelength_nm,
    )
    print_results(
        results,
        reference,
        [results_path, trials_path, summary_path, comparison_path, spectra_path],
    )


if __name__ == "__main__":
    main()
