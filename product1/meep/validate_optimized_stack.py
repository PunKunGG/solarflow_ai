from __future__ import annotations

import csv
import json

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


OPTIMIZER_PATH = (
    RESULTS_DIRECTORY
    / "flat_retrofit_optuna_summary.json"
)

CSV_PATH = (
    RESULTS_DIRECTORY
    / "optimized_stack_meep_validation.csv"
)

JSON_PATH = (
    RESULTS_DIRECTORY
    / "optimized_stack_meep_validation.json"
)

FIGURE_PATH = (
    RESULTS_DIRECTORY
    / "figures"
    / "optimized_stack_meep_validation.png"
)

WAVELENGTH_MIN_UM = 0.3
WAVELENGTH_MAX_UM = 1.2

FREQUENCY_MIN = 1 / WAVELENGTH_MAX_UM
FREQUENCY_MAX = 1 / WAVELENGTH_MIN_UM
FREQUENCY_CENTER = (
    FREQUENCY_MIN + FREQUENCY_MAX
) / 2
FREQUENCY_WIDTH = (
    FREQUENCY_MAX - FREQUENCY_MIN
)
SOURCE_FREQUENCY_WIDTH = (
    FREQUENCY_WIDTH * 1.2
)

NUMBER_OF_FREQUENCIES = 181
RESOLUTION = 300
PML_THICKNESS_UM = 1.0
CELL_LENGTH_UM = 12.0
CELL_WIDTH_UM = 0.1
RUN_TIME = 150

SOURCE_X = -3.5
REFLECTION_X = -2.0
TRANSMISSION_X = 2.0

GLASS_REFRACTIVE_INDEX = 1.52

MAXIMUM_ALLOWED_ERROR = 2e-3
MAXIMUM_GAIN_DIFFERENCE_PERCENT = 0.1


def load_candidate() -> tuple[float, float]:
    summary = json.loads(
        OPTIMIZER_PATH.read_text(
            encoding="utf-8"
        )
    )

    candidate = summary["results"][
        "engineered_low_index"
    ]

    return (
        float(
            candidate["best_refractive_index"]
        ),
        float(
            candidate["best_thickness_nm"]
        ),
    )


def make_geometry(
    retrofit_index: float | None = None,
    retrofit_thickness_nm: float | None = None,
) -> list[mp.Block]:
    glass = mp.Block(
        center=mp.Vector3(
            CELL_LENGTH_UM / 4
        ),
        size=mp.Vector3(
            CELL_LENGTH_UM / 2,
            mp.inf,
            mp.inf,
        ),
        material=mp.Medium(
            epsilon=(
                GLASS_REFRACTIVE_INDEX ** 2
            )
        ),
    )

    ar_thickness_um = (
        EXISTING_AR_THICKNESS_NM / 1000
    )

    existing_ar = mp.Block(
        center=mp.Vector3(
            -ar_thickness_um / 2
        ),
        size=mp.Vector3(
            ar_thickness_um,
            mp.inf,
            mp.inf,
        ),
        material=mp.Medium(
            epsilon=(
                EXISTING_AR_REFRACTIVE_INDEX
                ** 2
            )
        ),
    )

    geometry = [
        glass,
        existing_ar,
    ]

    if (
        retrofit_index is not None
        and retrofit_thickness_nm is not None
    ):
        retrofit_thickness_um = (
            retrofit_thickness_nm / 1000
        )

        retrofit = mp.Block(
            center=mp.Vector3(
                -ar_thickness_um
                - retrofit_thickness_um / 2
            ),
            size=mp.Vector3(
                retrofit_thickness_um,
                mp.inf,
                mp.inf,
            ),
            material=mp.Medium(
                epsilon=(
                    retrofit_index ** 2
                )
            ),
        )

        geometry.append(retrofit)

    return geometry


def make_simulation(
    geometry: list[mp.Block],
) -> mp.Simulation:
    source = mp.Source(
        src=mp.GaussianSource(
            frequency=FREQUENCY_CENTER,
            fwidth=FREQUENCY_WIDTH,
            is_integrated=True,
        ),
        component=mp.Ez,
        center=mp.Vector3(
            SOURCE_X,
            0,
        ),
        size=mp.Vector3(
            0,
            CELL_WIDTH_UM,
        ),
    )

    return mp.Simulation(
        cell_size=mp.Vector3(
            CELL_LENGTH_UM,
            CELL_WIDTH_UM,
        ),
        geometry=geometry,
        sources=[source],
        boundary_layers=[
            mp.PML(
                PML_THICKNESS_UM,
                direction=mp.X,
            )
        ],
        resolution=RESOLUTION,
        k_point=mp.Vector3(),
    )


def add_monitors(
    simulation: mp.Simulation,
) -> tuple[object, object]:
    reflection = simulation.add_flux(
        FREQUENCY_CENTER,
        FREQUENCY_WIDTH,
        NUMBER_OF_FREQUENCIES,
        mp.FluxRegion(
            center=mp.Vector3(
                REFLECTION_X,
                0,
            ),
            size=mp.Vector3(
                0,
                CELL_WIDTH_UM,
            ),
            direction=mp.X,
        ),
    )

    transmission = simulation.add_flux(
        FREQUENCY_CENTER,
        FREQUENCY_WIDTH,
        NUMBER_OF_FREQUENCIES,
        mp.FluxRegion(
            center=mp.Vector3(
                TRANSMISSION_X,
                0,
            ),
            size=mp.Vector3(
                0,
                CELL_WIDTH_UM,
            ),
            direction=mp.X,
        ),
    )

    return reflection, transmission


def run_reference() -> tuple[
    np.ndarray,
    np.ndarray,
    object,
]:
    simulation = make_simulation([])

    reflection, transmission = (
        add_monitors(simulation)
    )

    simulation.run(
        until=RUN_TIME
    )

    frequencies = np.asarray(
        mp.get_flux_freqs(transmission),
        dtype=float,
    )

    incident_flux = np.asarray(
        mp.get_fluxes(transmission),
        dtype=float,
    )

    reflection_data = (
        simulation.get_flux_data(
            reflection
        )
    )

    simulation.reset_meep()

    return (
        frequencies,
        incident_flux,
        reflection_data,
    )


def run_device(
    geometry: list[mp.Block],
    incident_flux: np.ndarray,
    reflection_data: object,
) -> tuple[np.ndarray, np.ndarray]:
    simulation = make_simulation(
        geometry
    )

    reflection, transmission = (
        add_monitors(simulation)
    )

    simulation.load_minus_flux_data(
        reflection,
        reflection_data,
    )

    simulation.run(
        until=RUN_TIME
    )

    reflected_flux = -np.asarray(
        mp.get_fluxes(reflection),
        dtype=float,
    )

    transmitted_flux = np.asarray(
        mp.get_fluxes(transmission),
        dtype=float,
    )

    simulation.reset_meep()

    return (
        reflected_flux / incident_flux,
        transmitted_flux / incident_flux,
    )


def integrated_power(
    solar_irradiance: np.ndarray,
    transmittance: np.ndarray,
) -> float:
    return float(
        np.trapezoid(
            solar_irradiance
            * transmittance,
            WAVELENGTH_NM,
        )
    )


def main() -> None:
    FIGURE_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    (
        retrofit_index,
        retrofit_thickness_nm,
    ) = load_candidate()

    (
        frequencies,
        incident_flux,
        reflection_data,
    ) = run_reference()

    (
        existing_r,
        existing_t,
    ) = run_device(
        make_geometry(),
        incident_flux,
        reflection_data,
    )

    (
        stacked_r,
        stacked_t,
    ) = run_device(
        make_geometry(
            retrofit_index,
            retrofit_thickness_nm,
        ),
        incident_flux,
        reflection_data,
    )

    wavelength_nm = (
        1000 / frequencies
    )

    order = np.argsort(
        wavelength_nm
    )

    wavelength_nm = wavelength_nm[order]
    existing_r = existing_r[order]
    existing_t = existing_t[order]
    stacked_r = stacked_r[order]
    stacked_t = stacked_t[order]

    existing_layers = [
        (
            EXISTING_AR_REFRACTIVE_INDEX,
            EXISTING_AR_THICKNESS_NM,
        )
    ]

    stacked_layers = [
        (
            retrofit_index,
            retrofit_thickness_nm,
        ),
        (
            EXISTING_AR_REFRACTIVE_INDEX,
            EXISTING_AR_THICKNESS_NM,
        ),
    ]

    existing_tmm_r = stack_reflectance(
        wavelength_nm,
        existing_layers,
    )

    stacked_tmm_r = stack_reflectance(
        wavelength_nm,
        stacked_layers,
    )

    existing_tmm_t = (
        1 - existing_tmm_r
    )

    stacked_tmm_t = (
        1 - stacked_tmm_r
    )

    existing_residual = np.abs(
        existing_r
        + existing_t
        - 1
    )

    stacked_residual = np.abs(
        stacked_r
        + stacked_t
        - 1
    )

    existing_tmm_error = np.abs(
        existing_r
        - existing_tmm_r
    )

    stacked_tmm_error = np.abs(
        stacked_r
        - stacked_tmm_r
    )

    source = LightSource(
        source_type="standard",
        version="AM1.5g",
        x=WAVELENGTH_NM,
        output_units=(
            "power_density_per_nm"
        ),
    )

    _, solar_irradiance = (
        source.spectrum()
    )

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

    existing_tmm_solar_t = (
        1
        - stack_reflectance(
            WAVELENGTH_NM,
            existing_layers,
        )
    )

    stacked_tmm_solar_t = (
        1
        - stack_reflectance(
            WAVELENGTH_NM,
            stacked_layers,
        )
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

    additional_power = (
        stacked_meep_power
        - existing_meep_power
    )

    absolute_gain = (
        additional_power
        / incident_power
        * 100
    )

    meep_relative_gain = (
        (
            stacked_meep_power
            / existing_meep_power
        )
        - 1
    ) * 100

    tmm_relative_gain = (
        (
            stacked_tmm_power
            / existing_tmm_power
        )
        - 1
    ) * 100

    gain_difference = abs(
        meep_relative_gain
        - tmm_relative_gain
    )

    max_existing_error = float(
        np.max(
            existing_tmm_error
        )
    )

    max_stacked_error = float(
        np.max(
            stacked_tmm_error
        )
    )

    max_existing_residual = float(
        np.max(
            existing_residual
        )
    )

    max_stacked_residual = float(
        np.max(
            stacked_residual
        )
    )

    passes_validation = (
        max_existing_error
        <= MAXIMUM_ALLOWED_ERROR
        and max_stacked_error
        <= MAXIMUM_ALLOWED_ERROR
        and max_existing_residual
        <= MAXIMUM_ALLOWED_ERROR
        and max_stacked_residual
        <= MAXIMUM_ALLOWED_ERROR
        and gain_difference
        <= MAXIMUM_GAIN_DIFFERENCE_PERCENT
    )

    with CSV_PATH.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as csv_file:
        writer = csv.writer(
            csv_file
        )

        writer.writerow(
            [
                "wavelength_nm",
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
            ]
        )

        writer.writerows(
            zip(
                wavelength_nm,
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
            )
        )

    summary = {
        "model": (
            "Meep validation of Optuna "
            "low-index retrofit candidate"
        ),
        "candidate": {
            "refractive_index": (
                retrofit_index
            ),
            "thickness_nm": (
                retrofit_thickness_nm
            ),
        },
        "simulation": {
            "meep_version": (
                mp.__version__
            ),
            "resolution_pixels_per_um": (
                RESOLUTION
            ),
            "number_of_frequencies": (
                NUMBER_OF_FREQUENCIES
            ),
            "run_time": RUN_TIME,
        },
        "meep_solar_weighted_result": {
            "incident_power_w_m2": (
                incident_power
            ),
            "existing_ar_power_w_m2": (
                existing_meep_power
            ),
            "stacked_power_w_m2": (
                stacked_meep_power
            ),
            "additional_power_w_m2": (
                additional_power
            ),
            "absolute_gain_percentage_points": (
                absolute_gain
            ),
            "relative_gain_percent": (
                meep_relative_gain
            ),
        },
        "tmm_solar_weighted_result": {
            "existing_ar_power_w_m2": (
                existing_tmm_power
            ),
            "stacked_power_w_m2": (
                stacked_tmm_power
            ),
            "relative_gain_percent": (
                tmm_relative_gain
            ),
        },
        "validation": {
            "maximum_existing_tmm_error": (
                max_existing_error
            ),
            "maximum_stacked_tmm_error": (
                max_stacked_error
            ),
            "maximum_existing_energy_residual": (
                max_existing_residual
            ),
            "maximum_stacked_energy_residual": (
                max_stacked_residual
            ),
            "relative_gain_difference_percent": (
                gain_difference
            ),
            "passes_validation": (
                passes_validation
            ),
        },
        "warning": (
            "Optical gain is not "
            "electrical power gain."
        ),
    }

    JSON_PATH.write_text(
        json.dumps(
            summary,
            indent=2,
        ),
        encoding="utf-8",
    )

    figure, axes = plt.subplots(
        2,
        1,
        figsize=(10, 8),
        sharex=True,
    )

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

    axes[0].set_ylabel(
        "Reflectance (%)"
    )

    axes[0].set_title(
        "Meep Validation of "
        "Optimized Retrofit"
    )

    axes[0].grid(alpha=0.3)
    axes[0].legend()

    axes[1].plot(
        wavelength_nm,
        (
            stacked_t
            - existing_t
        )
        * 100,
        label="Meep",
    )

    axes[1].plot(
        wavelength_nm,
        (
            stacked_tmm_t
            - existing_tmm_t
        )
        * 100,
        "--",
        label="TMM",
    )

    axes[1].axhline(
        0,
        color="black",
        linewidth=1,
    )

    axes[1].set_xlabel(
        "Wavelength (nm)"
    )

    axes[1].set_ylabel(
        "Transmission change "
        "(percentage points)"
    )

    axes[1].grid(alpha=0.3)
    axes[1].legend()

    figure.tight_layout()

    figure.savefig(
        FIGURE_PATH,
        dpi=180,
    )

    plt.close(figure)

    print(
        "Optimized stack Meep "
        "validation completed."
    )

    print(
        f"Candidate n         : "
        f"{retrofit_index:.6f}"
    )

    print(
        f"Candidate thickness : "
        f"{retrofit_thickness_nm:.3f} nm"
    )

    print(
        f"Existing AR power   : "
        f"{existing_meep_power:.3f} W/m²"
    )

    print(
        f"Stacked power       : "
        f"{stacked_meep_power:.3f} W/m²"
    )

    print(
        f"Additional power    : "
        f"{additional_power:.3f} W/m²"
    )

    print(
        f"Absolute gain       : "
        f"{absolute_gain:.4f} "
        "percentage points"
    )

    print(
        f"Meep relative gain  : "
        f"{meep_relative_gain:.4f}%"
    )

    print(
        f"TMM relative gain   : "
        f"{tmm_relative_gain:.4f}%"
    )

    print(
        f"Gain difference     : "
        f"{gain_difference:.4f}%"
    )

    print(
        f"Existing TMM error  : "
        f"{max_existing_error:.6e}"
    )

    print(
        f"Stacked TMM error   : "
        f"{max_stacked_error:.6e}"
    )

    print(
        f"Existing residual   : "
        f"{max_existing_residual:.6e}"
    )

    print(
        f"Stacked residual    : "
        f"{max_stacked_residual:.6e}"
    )

    print(
        f"Passes validation   : "
        f"{passes_validation}"
    )

    print(
        f"CSV                 : "
        f"{CSV_PATH}"
    )

    print(
        f"JSON                : "
        f"{JSON_PATH}"
    )

    print(
        f"Figure              : "
        f"{FIGURE_PATH}"
    )


if __name__ == "__main__":
    main()