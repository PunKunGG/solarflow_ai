from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import meep as mp
import numpy as np
from solcore.light_source import LightSource

from product1.analysis.stacked_retrofit_tmm import (
    EXISTING_AR_REFRACTIVE_INDEX,
    EXISTING_AR_THICKNESS_NM,
    RESULTS_DIRECTORY,
    WAVELENGTH_NM,
    stack_reflectance,
)


OPTIMIZER_PATH = RESULTS_DIRECTORY / "flat_retrofit_optuna_summary.json"

WAVELENGTH_MIN_UM = 0.3
WAVELENGTH_MAX_UM = 1.2

FREQUENCY_MIN = 1 / WAVELENGTH_MAX_UM
FREQUENCY_MAX = 1 / WAVELENGTH_MIN_UM
FREQUENCY_CENTER = (FREQUENCY_MIN + FREQUENCY_MAX) / 2
FREQUENCY_WIDTH = FREQUENCY_MAX - FREQUENCY_MIN

# Keep the source wider than the monitor band so the edge frequencies
# have enough incident power for stable normalization.
SOURCE_FREQUENCY_WIDTH = FREQUENCY_WIDTH * 1.2
SOURCE_CUTOFF = 8.0

NUMBER_OF_FREQUENCIES = 181
DEFAULT_RESOLUTIONS = [200, 300]

# The longest requested wavelength is 1.2 um. A 1.5 um PML and extra
# free-space padding reduce long-wavelength boundary contamination.
PML_THICKNESS_UM = 1.5
CELL_LENGTH_UM = 14.0
CELL_WIDTH_UM = 0.1

SOURCE_X = -4.0
REFLECTION_X = -2.5
TRANSMISSION_X = 2.5
DECAY_PROBE_X = TRANSMISSION_X

# Meep checks the field maximum over this time window after the source
# finishes. The run ends only when the field has decayed by this factor.
FIELD_DECAY_CHECK_INTERVAL = 50
FIELD_DECAY_TOLERANCE = 1e-9

GLASS_REFRACTIVE_INDEX = 1.52

MAXIMUM_ALLOWED_ERROR = 2e-3
MAXIMUM_GAIN_DIFFERENCE_PERCENT = 0.1
MAXIMUM_HIGH_RESOLUTION_GAIN_SPREAD_PERCENT = 0.05

# Every requested spectral point must have at least this fraction of the
# peak incident flux. If not, validation fails instead of silently dropping
# weak-source points.
MINIMUM_RELATIVE_INCIDENT_FLUX = 1e-6


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Validate the optimized retrofit stack with adaptive Meep "
            "field decay and an optional resolution convergence sweep."
        )
    )
    parser.add_argument(
        "--resolutions",
        nargs="+",
        type=int,
        default=DEFAULT_RESOLUTIONS,
        help="Meep resolutions in pixels/um, e.g. 150 200 250 300.",
    )
    return parser.parse_args()


def load_candidate() -> tuple[float, float]:
    summary = json.loads(OPTIMIZER_PATH.read_text(encoding="utf-8"))
    candidate = summary["results"]["engineered_low_index"]
    return (
        float(candidate["best_refractive_index"]),
        float(candidate["best_thickness_nm"]),
    )


def make_geometry(
    retrofit_index: float | None = None,
    retrofit_thickness_nm: float | None = None,
) -> list[mp.Block]:
    glass = mp.Block(
        center=mp.Vector3(CELL_LENGTH_UM / 4),
        size=mp.Vector3(CELL_LENGTH_UM / 2, mp.inf, mp.inf),
        material=mp.Medium(index=GLASS_REFRACTIVE_INDEX),
    )

    ar_thickness_um = EXISTING_AR_THICKNESS_NM / 1000
    existing_ar = mp.Block(
        center=mp.Vector3(-ar_thickness_um / 2),
        size=mp.Vector3(ar_thickness_um, mp.inf, mp.inf),
        material=mp.Medium(index=EXISTING_AR_REFRACTIVE_INDEX),
    )

    geometry = [glass, existing_ar]

    if retrofit_index is not None and retrofit_thickness_nm is not None:
        retrofit_thickness_um = retrofit_thickness_nm / 1000
        retrofit = mp.Block(
            center=mp.Vector3(
                -ar_thickness_um - retrofit_thickness_um / 2
            ),
            size=mp.Vector3(
                retrofit_thickness_um,
                mp.inf,
                mp.inf,
            ),
            material=mp.Medium(index=retrofit_index),
        )
        geometry.append(retrofit)

    return geometry


def make_simulation(
    geometry: list[mp.Block],
    resolution: int,
) -> mp.Simulation:
    source = mp.Source(
        src=mp.GaussianSource(
            frequency=FREQUENCY_CENTER,
            fwidth=SOURCE_FREQUENCY_WIDTH,
            cutoff=SOURCE_CUTOFF,
            is_integrated=True,
        ),
        component=mp.Ez,
        center=mp.Vector3(SOURCE_X, 0),
        size=mp.Vector3(0, CELL_WIDTH_UM),
    )

    return mp.Simulation(
        cell_size=mp.Vector3(CELL_LENGTH_UM, CELL_WIDTH_UM),
        geometry=geometry,
        sources=[source],
        boundary_layers=[
            mp.PML(PML_THICKNESS_UM, direction=mp.X),
        ],
        resolution=resolution,
        k_point=mp.Vector3(),
        eps_averaging=True,
    )


def add_monitors(simulation: mp.Simulation) -> tuple[Any, Any]:
    reflection = simulation.add_flux(
        FREQUENCY_CENTER,
        FREQUENCY_WIDTH,
        NUMBER_OF_FREQUENCIES,
        mp.FluxRegion(
            center=mp.Vector3(REFLECTION_X, 0),
            size=mp.Vector3(0, CELL_WIDTH_UM),
            direction=mp.X,
        ),
    )

    transmission = simulation.add_flux(
        FREQUENCY_CENTER,
        FREQUENCY_WIDTH,
        NUMBER_OF_FREQUENCIES,
        mp.FluxRegion(
            center=mp.Vector3(TRANSMISSION_X, 0),
            size=mp.Vector3(0, CELL_WIDTH_UM),
            direction=mp.X,
        ),
    )

    return reflection, transmission


def run_until_fields_decay(simulation: mp.Simulation) -> None:
    simulation.run(
        until_after_sources=mp.stop_when_fields_decayed(
            FIELD_DECAY_CHECK_INTERVAL,
            mp.Ez,
            mp.Vector3(DECAY_PROBE_X, 0),
            FIELD_DECAY_TOLERANCE,
        )
    )


def run_reference(
    resolution: int,
) -> tuple[np.ndarray, np.ndarray, Any]:
    simulation = make_simulation([], resolution)
    reflection, transmission = add_monitors(simulation)

    run_until_fields_decay(simulation)

    frequencies = np.asarray(
        mp.get_flux_freqs(transmission),
        dtype=float,
    )
    incident_flux = np.asarray(
        mp.get_fluxes(transmission),
        dtype=float,
    )
    reflection_data = simulation.get_flux_data(reflection)

    simulation.reset_meep()
    return frequencies, incident_flux, reflection_data


def run_device(
    geometry: list[mp.Block],
    reflection_data: Any,
    resolution: int,
) -> tuple[np.ndarray, np.ndarray]:
    simulation = make_simulation(geometry, resolution)
    reflection, transmission = add_monitors(simulation)

    simulation.load_minus_flux_data(reflection, reflection_data)
    run_until_fields_decay(simulation)

    reflected_flux = -np.asarray(
        mp.get_fluxes(reflection),
        dtype=float,
    )
    transmitted_flux = np.asarray(
        mp.get_fluxes(transmission),
        dtype=float,
    )

    simulation.reset_meep()
    return reflected_flux, transmitted_flux


def integrated_power(
    solar_irradiance: np.ndarray,
    transmittance: np.ndarray,
) -> float:
    return float(
        np.trapezoid(
            solar_irradiance * transmittance,
            WAVELENGTH_NM,
        )
    )


def maximum_at_wavelength(
    values: np.ndarray,
    wavelength_nm: np.ndarray,
    mask: np.ndarray,
) -> tuple[float, float]:
    valid_indices = np.flatnonzero(mask)
    if valid_indices.size == 0:
        raise RuntimeError("No spectral points are valid for validation.")

    local_index = int(np.argmax(values[mask]))
    global_index = int(valid_indices[local_index])
    return (
        float(values[global_index]),
        float(wavelength_nm[global_index]),
    )


def output_paths(resolution: int) -> tuple[Path, Path, Path]:
    stem = f"optimized_stack_meep_validation_r{resolution}"
    csv_path = RESULTS_DIRECTORY / f"{stem}.csv"
    json_path = RESULTS_DIRECTORY / f"{stem}.json"
    figure_path = RESULTS_DIRECTORY / "figures" / f"{stem}.png"
    return csv_path, json_path, figure_path


def write_spectral_csv(
    path: Path,
    wavelength_nm: np.ndarray,
    incident_flux_relative: np.ndarray,
    validation_mask: np.ndarray,
    existing_r: np.ndarray,
    existing_t: np.ndarray,
    existing_tmm_r: np.ndarray,
    existing_tmm_t: np.ndarray,
    stacked_r: np.ndarray,
    stacked_t: np.ndarray,
    stacked_tmm_r: np.ndarray,
    stacked_tmm_t: np.ndarray,
    existing_residual: np.ndarray,
    stacked_residual: np.ndarray,
    existing_tmm_error: np.ndarray,
    stacked_tmm_error: np.ndarray,
) -> None:
    with path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(
            [
                "wavelength_nm",
                "incident_flux_relative",
                "used_for_validation",
                "existing_reflectance_meep",
                "existing_transmittance_meep",
                "existing_reflectance_tmm",
                "existing_transmittance_tmm",
                "stacked_reflectance_meep",
                "stacked_transmittance_meep",
                "stacked_reflectance_tmm",
                "stacked_transmittance_tmm",
                "existing_energy_residual",
                "stacked_energy_residual",
                "existing_reflectance_tmm_error",
                "stacked_reflectance_tmm_error",
            ]
        )
        writer.writerows(
            zip(
                wavelength_nm,
                incident_flux_relative,
                validation_mask.astype(int),
                existing_r,
                existing_t,
                existing_tmm_r,
                existing_tmm_t,
                stacked_r,
                stacked_t,
                stacked_tmm_r,
                stacked_tmm_t,
                existing_residual,
                stacked_residual,
                existing_tmm_error,
                stacked_tmm_error,
            )
        )


def write_validation_figure(
    path: Path,
    wavelength_nm: np.ndarray,
    existing_r: np.ndarray,
    stacked_r: np.ndarray,
    stacked_t: np.ndarray,
    existing_t: np.ndarray,
    stacked_tmm_r: np.ndarray,
    stacked_tmm_t: np.ndarray,
    existing_tmm_t: np.ndarray,
    existing_residual: np.ndarray,
    stacked_residual: np.ndarray,
    validation_mask: np.ndarray,
    resolution: int,
) -> None:
    figure, axes = plt.subplots(3, 1, figsize=(10, 11), sharex=True)

    axes[0].plot(
        wavelength_nm,
        existing_r * 100,
        label="Existing AR — Meep",
    )
    axes[0].plot(
        wavelength_nm,
        stacked_r * 100,
        label="Optimized stack — Meep",
    )
    axes[0].plot(
        wavelength_nm,
        stacked_tmm_r * 100,
        "--",
        label="Optimized stack — TMM",
    )
    axes[0].set_ylabel("Reflectance (%)")
    axes[0].set_title(
        f"Optimized Retrofit Validation — Resolution {resolution}"
    )
    axes[0].grid(alpha=0.3)
    axes[0].legend()

    axes[1].plot(
        wavelength_nm,
        (stacked_t - existing_t) * 100,
        label="Meep",
    )
    axes[1].plot(
        wavelength_nm,
        (stacked_tmm_t - existing_tmm_t) * 100,
        "--",
        label="TMM",
    )
    axes[1].axhline(0, color="black", linewidth=1)
    axes[1].set_ylabel("Transmission change\n(percentage points)")
    axes[1].grid(alpha=0.3)
    axes[1].legend()

    residual_floor = 1e-12
    axes[2].semilogy(
        wavelength_nm,
        np.maximum(existing_residual, residual_floor),
        label="Existing AR residual",
    )
    axes[2].semilogy(
        wavelength_nm,
        np.maximum(stacked_residual, residual_floor),
        label="Stacked residual",
    )
    axes[2].axhline(
        MAXIMUM_ALLOWED_ERROR,
        color="black",
        linestyle="--",
        linewidth=1,
        label="Validation tolerance",
    )
    if not np.all(validation_mask):
        axes[2].scatter(
            wavelength_nm[~validation_mask],
            np.maximum(stacked_residual[~validation_mask], residual_floor),
            marker="x",
            label="Insufficient source power",
        )
    axes[2].set_xlabel("Wavelength (nm)")
    axes[2].set_ylabel("|R + T - 1|")
    axes[2].grid(alpha=0.3)
    axes[2].legend()

    figure.tight_layout()
    figure.savefig(path, dpi=180)
    plt.close(figure)


def validate_resolution(
    resolution: int,
    retrofit_index: float,
    retrofit_thickness_nm: float,
    solar_irradiance: np.ndarray,
    incident_solar_power: float,
) -> dict[str, Any]:
    print(f"\n=== Resolution {resolution} ===")

    frequencies, incident_flux, reflection_data = run_reference(resolution)

    existing_reflected_flux, existing_transmitted_flux = run_device(
        make_geometry(),
        reflection_data,
        resolution,
    )
    stacked_reflected_flux, stacked_transmitted_flux = run_device(
        make_geometry(retrofit_index, retrofit_thickness_nm),
        reflection_data,
        resolution,
    )

    wavelength_nm = 1000 / frequencies
    order = np.argsort(wavelength_nm)

    wavelength_nm = wavelength_nm[order]
    incident_flux = incident_flux[order]
    existing_reflected_flux = existing_reflected_flux[order]
    existing_transmitted_flux = existing_transmitted_flux[order]
    stacked_reflected_flux = stacked_reflected_flux[order]
    stacked_transmitted_flux = stacked_transmitted_flux[order]

    peak_incident_flux = float(np.max(np.abs(incident_flux)))
    if not np.isfinite(peak_incident_flux) or peak_incident_flux <= 0:
        raise RuntimeError("Reference run returned invalid incident flux.")

    incident_flux_relative = np.abs(incident_flux) / peak_incident_flux
    validation_mask = (
        incident_flux_relative >= MINIMUM_RELATIVE_INCIDENT_FLUX
    )
    source_covers_full_band = bool(np.all(validation_mask))

    if np.any(np.abs(incident_flux[validation_mask]) == 0):
        raise RuntimeError("Zero incident flux in the validation band.")

    existing_r = existing_reflected_flux / incident_flux
    existing_t = existing_transmitted_flux / incident_flux
    stacked_r = stacked_reflected_flux / incident_flux
    stacked_t = stacked_transmitted_flux / incident_flux

    finite_spectra = bool(
        np.all(
            np.isfinite(
                np.concatenate(
                    [existing_r, existing_t, stacked_r, stacked_t]
                )
            )
        )
    )

    existing_layers = [
        (EXISTING_AR_REFRACTIVE_INDEX, EXISTING_AR_THICKNESS_NM)
    ]
    stacked_layers = [
        (retrofit_index, retrofit_thickness_nm),
        (EXISTING_AR_REFRACTIVE_INDEX, EXISTING_AR_THICKNESS_NM),
    ]

    existing_tmm_r = stack_reflectance(wavelength_nm, existing_layers)
    stacked_tmm_r = stack_reflectance(wavelength_nm, stacked_layers)
    existing_tmm_t = 1 - existing_tmm_r
    stacked_tmm_t = 1 - stacked_tmm_r

    existing_residual = np.abs(existing_r + existing_t - 1)
    stacked_residual = np.abs(stacked_r + stacked_t - 1)
    existing_tmm_error = np.abs(existing_r - existing_tmm_r)
    stacked_tmm_error = np.abs(stacked_r - stacked_tmm_r)

    max_existing_error, max_existing_error_nm = maximum_at_wavelength(
        existing_tmm_error,
        wavelength_nm,
        validation_mask,
    )
    max_stacked_error, max_stacked_error_nm = maximum_at_wavelength(
        stacked_tmm_error,
        wavelength_nm,
        validation_mask,
    )
    max_existing_residual, max_existing_residual_nm = (
        maximum_at_wavelength(
            existing_residual,
            wavelength_nm,
            validation_mask,
        )
    )
    max_stacked_residual, max_stacked_residual_nm = maximum_at_wavelength(
        stacked_residual,
        wavelength_nm,
        validation_mask,
    )

    full_band_mask = np.ones_like(validation_mask, dtype=bool)
    full_max_existing_residual, full_max_existing_residual_nm = (
        maximum_at_wavelength(
            existing_residual,
            wavelength_nm,
            full_band_mask,
        )
    )
    full_max_stacked_residual, full_max_stacked_residual_nm = (
        maximum_at_wavelength(
            stacked_residual,
            wavelength_nm,
            full_band_mask,
        )
    )

    existing_meep_solar_t = np.interp(
        WAVELENGTH_NM,
        wavelength_nm,
        existing_t,
    )
    stacked_meep_solar_t = np.interp(
        WAVELENGTH_NM,
        wavelength_nm,
        stacked_t,
    )
    existing_tmm_solar_t = 1 - stack_reflectance(
        WAVELENGTH_NM,
        existing_layers,
    )
    stacked_tmm_solar_t = 1 - stack_reflectance(
        WAVELENGTH_NM,
        stacked_layers,
    )

    existing_meep_power = integrated_power(
        solar_irradiance,
        existing_meep_solar_t,
    )
    stacked_meep_power = integrated_power(
        solar_irradiance,
        stacked_meep_solar_t,
    )
    existing_tmm_power = integrated_power(
        solar_irradiance,
        existing_tmm_solar_t,
    )
    stacked_tmm_power = integrated_power(
        solar_irradiance,
        stacked_tmm_solar_t,
    )

    additional_power = stacked_meep_power - existing_meep_power
    absolute_gain = additional_power / incident_solar_power * 100
    meep_relative_gain = (
        stacked_meep_power / existing_meep_power - 1
    ) * 100
    tmm_relative_gain = (
        stacked_tmm_power / existing_tmm_power - 1
    ) * 100
    gain_difference = abs(meep_relative_gain - tmm_relative_gain)

    passes_validation = bool(
        finite_spectra
        and source_covers_full_band
        and max_existing_error <= MAXIMUM_ALLOWED_ERROR
        and max_stacked_error <= MAXIMUM_ALLOWED_ERROR
        and max_existing_residual <= MAXIMUM_ALLOWED_ERROR
        and max_stacked_residual <= MAXIMUM_ALLOWED_ERROR
        and gain_difference <= MAXIMUM_GAIN_DIFFERENCE_PERCENT
    )

    csv_path, json_path, figure_path = output_paths(resolution)
    figure_path.parent.mkdir(parents=True, exist_ok=True)

    write_spectral_csv(
        csv_path,
        wavelength_nm,
        incident_flux_relative,
        validation_mask,
        existing_r,
        existing_t,
        existing_tmm_r,
        existing_tmm_t,
        stacked_r,
        stacked_t,
        stacked_tmm_r,
        stacked_tmm_t,
        existing_residual,
        stacked_residual,
        existing_tmm_error,
        stacked_tmm_error,
    )

    summary: dict[str, Any] = {
        "model": "Meep validation of Optuna low-index retrofit candidate",
        "candidate": {
            "refractive_index": retrofit_index,
            "thickness_nm": retrofit_thickness_nm,
        },
        "simulation": {
            "meep_version": mp.__version__,
            "resolution_pixels_per_um": resolution,
            "number_of_frequencies": NUMBER_OF_FREQUENCIES,
            "source_frequency_width": SOURCE_FREQUENCY_WIDTH,
            "monitor_frequency_width": FREQUENCY_WIDTH,
            "source_cutoff": SOURCE_CUTOFF,
            "pml_thickness_um": PML_THICKNESS_UM,
            "cell_length_um": CELL_LENGTH_UM,
            "termination": "adaptive field decay after source",
            "field_decay_check_interval": FIELD_DECAY_CHECK_INTERVAL,
            "field_decay_tolerance": FIELD_DECAY_TOLERANCE,
        },
        "source_coverage": {
            "minimum_relative_incident_flux_required": (
                MINIMUM_RELATIVE_INCIDENT_FLUX
            ),
            "minimum_relative_incident_flux_observed": float(
                np.min(incident_flux_relative)
            ),
            "valid_points": int(np.count_nonzero(validation_mask)),
            "total_points": int(validation_mask.size),
            "covers_full_requested_band": source_covers_full_band,
        },
        "meep_solar_weighted_result": {
            "incident_power_w_m2": incident_solar_power,
            "existing_ar_power_w_m2": existing_meep_power,
            "stacked_power_w_m2": stacked_meep_power,
            "additional_power_w_m2": additional_power,
            "absolute_gain_percentage_points": absolute_gain,
            "relative_gain_percent": meep_relative_gain,
        },
        "tmm_solar_weighted_result": {
            "existing_ar_power_w_m2": existing_tmm_power,
            "stacked_power_w_m2": stacked_tmm_power,
            "relative_gain_percent": tmm_relative_gain,
        },
        "validation": {
            "maximum_allowed_error": MAXIMUM_ALLOWED_ERROR,
            "maximum_gain_difference_percent_allowed": (
                MAXIMUM_GAIN_DIFFERENCE_PERCENT
            ),
            "finite_spectra": finite_spectra,
            "maximum_existing_tmm_error": max_existing_error,
            "maximum_existing_tmm_error_wavelength_nm": (
                max_existing_error_nm
            ),
            "maximum_stacked_tmm_error": max_stacked_error,
            "maximum_stacked_tmm_error_wavelength_nm": (
                max_stacked_error_nm
            ),
            "maximum_existing_energy_residual": max_existing_residual,
            "maximum_existing_energy_residual_wavelength_nm": (
                max_existing_residual_nm
            ),
            "maximum_stacked_energy_residual": max_stacked_residual,
            "maximum_stacked_energy_residual_wavelength_nm": (
                max_stacked_residual_nm
            ),
            "full_band_maximum_existing_energy_residual": (
                full_max_existing_residual
            ),
            "full_band_maximum_existing_energy_residual_wavelength_nm": (
                full_max_existing_residual_nm
            ),
            "full_band_maximum_stacked_energy_residual": (
                full_max_stacked_residual
            ),
            "full_band_maximum_stacked_energy_residual_wavelength_nm": (
                full_max_stacked_residual_nm
            ),
            "relative_gain_difference_percent": gain_difference,
            "passes_validation": passes_validation,
        },
        "outputs": {
            "csv": str(csv_path),
            "json": str(json_path),
            "figure": str(figure_path),
        },
        "warning": "Optical gain is not electrical power gain.",
    }

    json_path.write_text(
        json.dumps(summary, indent=2),
        encoding="utf-8",
    )

    write_validation_figure(
        figure_path,
        wavelength_nm,
        existing_r,
        stacked_r,
        stacked_t,
        existing_t,
        stacked_tmm_r,
        stacked_tmm_t,
        existing_tmm_t,
        existing_residual,
        stacked_residual,
        validation_mask,
        resolution,
    )

    print(f"Candidate n         : {retrofit_index:.6f}")
    print(f"Candidate thickness : {retrofit_thickness_nm:.3f} nm")
    print(f"Source coverage     : {np.count_nonzero(validation_mask)}/{validation_mask.size}")
    print(f"Existing AR power   : {existing_meep_power:.3f} W/m²")
    print(f"Stacked power       : {stacked_meep_power:.3f} W/m²")
    print(f"Additional power    : {additional_power:.3f} W/m²")
    print(f"Meep relative gain  : {meep_relative_gain:.4f}%")
    print(f"TMM relative gain   : {tmm_relative_gain:.4f}%")
    print(f"Gain difference     : {gain_difference:.4f}%")
    print(
        "Existing TMM error  : "
        f"{max_existing_error:.6e} at {max_existing_error_nm:.2f} nm"
    )
    print(
        "Stacked TMM error   : "
        f"{max_stacked_error:.6e} at {max_stacked_error_nm:.2f} nm"
    )
    print(
        "Existing residual   : "
        f"{max_existing_residual:.6e} at "
        f"{max_existing_residual_nm:.2f} nm"
    )
    print(
        "Stacked residual    : "
        f"{max_stacked_residual:.6e} at "
        f"{max_stacked_residual_nm:.2f} nm"
    )
    print(f"Passes validation   : {passes_validation}")
    print(f"CSV                 : {csv_path}")
    print(f"JSON                : {json_path}")
    print(f"Figure              : {figure_path}")

    return summary


def write_convergence_outputs(
    summaries: list[dict[str, Any]],
) -> dict[str, Any]:
    ordered = sorted(
        summaries,
        key=lambda item: item["simulation"]["resolution_pixels_per_um"],
    )

    resolutions = np.asarray(
        [
            item["simulation"]["resolution_pixels_per_um"]
            for item in ordered
        ],
        dtype=int,
    )
    meep_gains = np.asarray(
        [
            item["meep_solar_weighted_result"]["relative_gain_percent"]
            for item in ordered
        ],
        dtype=float,
    )
    existing_residuals = np.asarray(
        [
            item["validation"]["maximum_existing_energy_residual"]
            for item in ordered
        ],
        dtype=float,
    )
    stacked_residuals = np.asarray(
        [
            item["validation"]["maximum_stacked_energy_residual"]
            for item in ordered
        ],
        dtype=float,
    )
    individual_passes = [
        bool(item["validation"]["passes_validation"]) for item in ordered
    ]

    if len(ordered) >= 2:
        high_resolution_gain_spread = float(
            abs(meep_gains[-1] - meep_gains[-2])
        )
        compared_resolutions = [int(resolutions[-2]), int(resolutions[-1])]
    else:
        high_resolution_gain_spread = 0.0
        compared_resolutions = [int(resolutions[-1])]

    final_resolution_passes = bool(individual_passes[-1])
    passes_convergence = bool(
        final_resolution_passes
        and high_resolution_gain_spread
        <= MAXIMUM_HIGH_RESOLUTION_GAIN_SPREAD_PERCENT
    )

    convergence_csv = RESULTS_DIRECTORY / "optimized_stack_meep_convergence.csv"
    convergence_json = RESULTS_DIRECTORY / "optimized_stack_meep_convergence.json"
    convergence_figure = (
        RESULTS_DIRECTORY
        / "figures"
        / "optimized_stack_meep_convergence.png"
    )
    convergence_figure.parent.mkdir(parents=True, exist_ok=True)

    with convergence_csv.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(
            [
                "resolution_pixels_per_um",
                "meep_relative_gain_percent",
                "maximum_existing_energy_residual",
                "maximum_stacked_energy_residual",
                "passes_individual_validation",
            ]
        )
        writer.writerows(
            zip(
                resolutions,
                meep_gains,
                existing_residuals,
                stacked_residuals,
                individual_passes,
            )
        )

    convergence_summary: dict[str, Any] = {
        "model": "Meep resolution convergence for optimized retrofit stack",
        "resolutions_pixels_per_um": resolutions.tolist(),
        "meep_relative_gain_percent": meep_gains.tolist(),
        "maximum_existing_energy_residual": existing_residuals.tolist(),
        "maximum_stacked_energy_residual": stacked_residuals.tolist(),
        "individual_validation_passes": individual_passes,
        "high_resolution_pair": compared_resolutions,
        "high_resolution_gain_spread_percent": (
            high_resolution_gain_spread
        ),
        "maximum_high_resolution_gain_spread_percent_allowed": (
            MAXIMUM_HIGH_RESOLUTION_GAIN_SPREAD_PERCENT
        ),
        "final_resolution_passes_validation": final_resolution_passes,
        "passes_convergence": passes_convergence,
        "note": (
            "Coarse resolutions are diagnostic. The convergence gate uses "
            "the two highest resolutions and requires the highest-resolution "
            "run to pass the strict individual validation criteria."
        ),
    }
    convergence_json.write_text(
        json.dumps(convergence_summary, indent=2),
        encoding="utf-8",
    )

    figure, axes = plt.subplots(2, 1, figsize=(9, 8), sharex=True)
    axes[0].plot(resolutions, meep_gains, marker="o", label="Meep gain")
    axes[0].axhline(
        ordered[-1]["tmm_solar_weighted_result"]["relative_gain_percent"],
        color="black",
        linestyle="--",
        label="TMM gain",
    )
    axes[0].set_ylabel("Relative optical gain (%)")
    axes[0].grid(alpha=0.3)
    axes[0].legend()

    axes[1].semilogy(
        resolutions,
        existing_residuals,
        marker="o",
        label="Existing AR residual",
    )
    axes[1].semilogy(
        resolutions,
        stacked_residuals,
        marker="o",
        label="Stacked residual",
    )
    axes[1].axhline(
        MAXIMUM_ALLOWED_ERROR,
        color="black",
        linestyle="--",
        label="Validation tolerance",
    )
    axes[1].set_xlabel("Resolution (pixels/um)")
    axes[1].set_ylabel("Maximum |R + T - 1|")
    axes[1].grid(alpha=0.3)
    axes[1].legend()

    figure.tight_layout()
    figure.savefig(convergence_figure, dpi=180)
    plt.close(figure)

    print("\n=== Convergence summary ===")
    print(f"High-resolution pair : {compared_resolutions}")
    print(
        "Gain spread          : "
        f"{high_resolution_gain_spread:.6f}%"
    )
    print(f"Final run passes     : {final_resolution_passes}")
    print(f"Passes convergence  : {passes_convergence}")
    print(f"CSV                  : {convergence_csv}")
    print(f"JSON                 : {convergence_json}")
    print(f"Figure               : {convergence_figure}")

    return convergence_summary


def main() -> None:
    args = parse_arguments()
    resolutions = sorted(set(args.resolutions))

    if not resolutions or any(resolution <= 0 for resolution in resolutions):
        raise ValueError("All resolutions must be positive integers.")

    RESULTS_DIRECTORY.mkdir(parents=True, exist_ok=True)

    retrofit_index, retrofit_thickness_nm = load_candidate()

    source = LightSource(
        source_type="standard",
        version="AM1.5g",
        x=WAVELENGTH_NM,
        output_units="power_density_per_nm",
    )
    _, solar_irradiance = source.spectrum()
    solar_irradiance = np.asarray(solar_irradiance, dtype=float)
    incident_solar_power = float(
        np.trapezoid(solar_irradiance, WAVELENGTH_NM)
    )

    summaries = [
        validate_resolution(
            resolution,
            retrofit_index,
            retrofit_thickness_nm,
            solar_irradiance,
            incident_solar_power,
        )
        for resolution in resolutions
    ]

    write_convergence_outputs(summaries)


if __name__ == "__main__":
    main()
