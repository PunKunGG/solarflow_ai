from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import numpy as np
import optuna
from solcore.light_source import LightSource

from product1.analysis.stacked_retrofit_tmm import (
    EXISTING_AR_REFRACTIVE_INDEX,
    EXISTING_AR_THICKNESS_NM,
    RESULTS_DIRECTORY,
    WAVELENGTH_NM,
    stack_reflectance,
)


N_TRIALS_PER_STUDY = 600
RANDOM_SEED = 42

OUTPUT_TRIALS_PATH = (
    RESULTS_DIRECTORY
    / "flat_retrofit_optuna_trials.csv"
)

OUTPUT_SUMMARY_PATH = (
    RESULTS_DIRECTORY
    / "flat_retrofit_optuna_summary.json"
)

SEARCH_SPACES = {
    "practical_polymer": {
        "refractive_index_min": 1.30,
        "refractive_index_max": 1.60,
        "thickness_nm_min": 20.0,
        "thickness_nm_max": 1000.0,
        "description": (
            "Homogeneous polymer-like flat film"
        ),
    },
    "engineered_low_index": {
        "refractive_index_min": 1.02,
        "refractive_index_max": 1.30,
        "thickness_nm_min": 20.0,
        "thickness_nm_max": 500.0,
        "description": (
            "Engineered porous or effective-index film"
        ),
    },
}


def transmitted_power(
    solar_irradiance: np.ndarray,
    refractive_index: float | None = None,
    thickness_nm: float | None = None,
) -> float:
    layers: list[tuple[float, float]] = []

    if (
        refractive_index is not None
        and thickness_nm is not None
    ):
        layers.append(
            (
                refractive_index,
                thickness_nm,
            )
        )

    layers.append(
        (
            EXISTING_AR_REFRACTIVE_INDEX,
            EXISTING_AR_THICKNESS_NM,
        )
    )

    reflectance = stack_reflectance(
        WAVELENGTH_NM,
        layers,
    )

    transmittance = 1 - reflectance

    return float(
        np.trapezoid(
            solar_irradiance * transmittance,
            WAVELENGTH_NM,
        )
    )


def calculate_metrics(
    candidate_power: float,
    baseline_power: float,
    incident_power: float,
) -> dict[str, float]:
    return {
        "transmitted_power_w_m2": candidate_power,
        "additional_power_w_m2": (
            candidate_power - baseline_power
        ),
        "absolute_gain_percentage_points": (
            (
                candidate_power
                - baseline_power
            )
            / incident_power
            * 100
        ),
        "relative_gain_percent": (
            (
                candidate_power
                / baseline_power
            )
            - 1
        )
        * 100,
    }


def run_study(
    study_name: str,
    search_space: dict[str, Any],
    solar_irradiance: np.ndarray,
    seed: int,
) -> optuna.Study:
    def objective(
        trial: optuna.Trial,
    ) -> float:
        refractive_index = trial.suggest_float(
            "refractive_index",
            search_space[
                "refractive_index_min"
            ],
            search_space[
                "refractive_index_max"
            ],
        )

        thickness_nm = trial.suggest_float(
            "thickness_nm",
            search_space[
                "thickness_nm_min"
            ],
            search_space[
                "thickness_nm_max"
            ],
        )

        return transmitted_power(
            solar_irradiance=solar_irradiance,
            refractive_index=refractive_index,
            thickness_nm=thickness_nm,
        )

    sampler = optuna.samplers.TPESampler(
        seed=seed,
        n_startup_trials=50,
    )

    study = optuna.create_study(
        study_name=study_name,
        direction="maximize",
        sampler=sampler,
    )

    study.enqueue_trial(
        {
            "refractive_index": search_space[
                "refractive_index_min"
            ],
            "thickness_nm": search_space[
                "thickness_nm_min"
            ],
        }
    )

    study.optimize(
        objective,
        n_trials=N_TRIALS_PER_STUDY,
        show_progress_bar=False,
    )

    return study


def main() -> None:
    optuna.logging.set_verbosity(
        optuna.logging.WARNING
    )

    source = LightSource(
        source_type="standard",
        version="AM1.5g",
        x=WAVELENGTH_NM,
        output_units="power_density_per_nm",
    )

    _, solar_irradiance = source.spectrum()

    solar_irradiance = np.asarray(
        solar_irradiance,
        dtype=float,
    )

    incident_power = float(
        np.trapezoid(
            solar_irradiance,
            WAVELENGTH_NM,
        )
    )

    baseline_power = transmitted_power(
        solar_irradiance=solar_irradiance,
    )

    studies: dict[str, optuna.Study] = {}
    results: dict[str, dict[str, Any]] = {}

    for index, (
        study_name,
        search_space,
    ) in enumerate(SEARCH_SPACES.items()):
        study = run_study(
            study_name=study_name,
            search_space=search_space,
            solar_irradiance=solar_irradiance,
            seed=RANDOM_SEED + index,
        )

        studies[study_name] = study

        best_refractive_index = float(
            study.best_params[
                "refractive_index"
            ]
        )

        best_thickness_nm = float(
            study.best_params[
                "thickness_nm"
            ]
        )

        best_power = float(
            study.best_value
        )

        results[study_name] = {
            "description": search_space[
                "description"
            ],
            "best_refractive_index": (
                best_refractive_index
            ),
            "best_thickness_nm": (
                best_thickness_nm
            ),
            **calculate_metrics(
                candidate_power=best_power,
                baseline_power=baseline_power,
                incident_power=incident_power,
            ),
            "best_parameter_at_boundary": {
                "refractive_index_near_minimum": (
                    best_refractive_index
                    <= search_space[
                        "refractive_index_min"
                    ]
                    + 0.01
                ),
                "thickness_near_minimum": (
                    best_thickness_nm
                    <= search_space[
                        "thickness_nm_min"
                    ]
                    + 5
                ),
            },
        }

    with OUTPUT_TRIALS_PATH.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as csv_file:
        fieldnames = [
            "study",
            "trial_number",
            "state",
            "refractive_index",
            "thickness_nm",
            "transmitted_power_w_m2",
            "relative_gain_vs_no_retrofit_percent",
        ]

        writer = csv.DictWriter(
            csv_file,
            fieldnames=fieldnames,
        )

        writer.writeheader()

        for study_name, study in studies.items():
            for trial in study.trials:
                if trial.value is None:
                    continue

                trial_power = float(
                    trial.value
                )

                writer.writerow(
                    {
                        "study": study_name,
                        "trial_number": (
                            trial.number
                        ),
                        "state": (
                            trial.state.name
                        ),
                        "refractive_index": (
                            trial.params.get(
                                "refractive_index"
                            )
                        ),
                        "thickness_nm": (
                            trial.params.get(
                                "thickness_nm"
                            )
                        ),
                        "transmitted_power_w_m2": (
                            trial_power
                        ),
                        "relative_gain_vs_no_retrofit_percent": (
                            (
                                trial_power
                                / baseline_power
                                - 1
                            )
                            * 100
                        ),
                    }
                )

    summary = {
        "model": (
            "Optuna TPE search for a homogeneous "
            "flat retrofit layer over existing AR"
        ),
        "objective": (
            "Maximize AM1.5G-weighted transmitted "
            "optical power from 300 to 1200 nm"
        ),
        "optimizer": {
            "library": "Optuna",
            "sampler": "TPESampler",
            "seed": RANDOM_SEED,
            "trials_per_study": (
                N_TRIALS_PER_STUDY
            ),
        },
        "baseline": {
            "description": (
                "Existing AR without retrofit"
            ),
            "transmitted_power_w_m2": (
                baseline_power
            ),
        },
        "search_spaces": SEARCH_SPACES,
        "results": results,
        "warning": (
            "Optimized optical power is not "
            "electrical power. Material ranges "
            "are exploratory assumptions."
        ),
    }

    OUTPUT_SUMMARY_PATH.write_text(
        json.dumps(
            summary,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(
        "Flat retrofit Optuna search completed."
    )
    print(
        f"Baseline power: "
        f"{baseline_power:.3f} W/m²"
    )

    for study_name, result in results.items():
        print()
        print(study_name)
        print(
            "  Best refractive index: "
            f"{result['best_refractive_index']:.6f}"
        )
        print(
            "  Best thickness: "
            f"{result['best_thickness_nm']:.3f} nm"
        )
        print(
            "  Transmitted power: "
            f"{result['transmitted_power_w_m2']:.3f} "
            "W/m²"
        )
        print(
            "  Additional power: "
            f"{result['additional_power_w_m2']:.3f} "
            "W/m²"
        )
        print(
            "  Absolute gain: "
            f"{result['absolute_gain_percentage_points']:.4f} "
            "percentage points"
        )
        print(
            "  Relative gain: "
            f"{result['relative_gain_percent']:.4f}%"
        )
        print(
            "  Boundary flags: "
            f"{result['best_parameter_at_boundary']}"
        )

    print()
    print(f"Trials: {OUTPUT_TRIALS_PATH}")
    print(f"Summary: {OUTPUT_SUMMARY_PATH}")


if __name__ == "__main__":
    main()