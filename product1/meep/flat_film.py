from __future__ import annotations

import csv
import json
from pathlib import Path

import meep as mp
import numpy as np

import baseline_glass as baseline


AIR_REFRACTIVE_INDEX = 1.0
GLASS_REFRACTIVE_INDEX = baseline.GLASS_REFRACTIVE_INDEX

# Ideal single-layer anti-reflection index:
# n_film = sqrt(n_air * n_glass)
FILM_REFRACTIVE_INDEX = float(
    np.sqrt(AIR_REFRACTIVE_INDEX * GLASS_REFRACTIVE_INDEX)
)

DESIGN_WAVELENGTH_UM = 0.55

# Quarter-wave optical thickness:
# d = wavelength / (4 * n_film)
FILM_THICKNESS_UM = (
    DESIGN_WAVELENGTH_UM
    / (4 * FILM_REFRACTIVE_INDEX)
)

RESOLUTION = 200

MODEL_NAME = (
    "1D ideal quarter-wave anti-reflection "
    "film on glass"
)

MODEL_ROLE = (
    "Theoretical optical upper bound, "
    "not a final manufacturable material"
)

RESULTS_DIRECTORY = (
    Path(__file__).resolve().parents[1]
    / "results"
)

CSV_PATH = RESULTS_DIRECTORY / "flat_film_ideal_ar.csv"
SUMMARY_PATH = (
    RESULTS_DIRECTORY
    / "flat_film_ideal_ar_summary.json"
)


def run_film_simulation(incident_reflection_data):
    baseline.RESOLUTION = RESOLUTION

    glass = mp.Medium(index=GLASS_REFRACTIVE_INDEX)
    film = mp.Medium(index=FILM_REFRACTIVE_INDEX)

    geometry = [
        # Existing glass substrate from z = 0 toward +z
        mp.Block(
            size=mp.Vector3(
                mp.inf,
                mp.inf,
                0.5 * baseline.CELL_LENGTH_UM,
            ),
            center=mp.Vector3(
                z=0.25 * baseline.CELL_LENGTH_UM
            ),
            material=glass,
        ),
        # Thin-film layer immediately above the glass
        mp.Block(
            size=mp.Vector3(
                mp.inf,
                mp.inf,
                FILM_THICKNESS_UM,
            ),
            center=mp.Vector3(
                z=-0.5 * FILM_THICKNESS_UM
            ),
            material=film,
        ),
    ]

    simulation = baseline.create_simulation(geometry)

    reflection_monitor = simulation.add_flux(
        baseline.FREQUENCY_CENTER,
        baseline.FREQUENCY_WIDTH,
        baseline.NUMBER_OF_FREQUENCIES,
        mp.FluxRegion(
            center=mp.Vector3(
                z=baseline.REFLECTION_MONITOR_Z
            )
        ),
    )

    transmission_monitor = simulation.add_flux(
        baseline.FREQUENCY_CENTER,
        baseline.FREQUENCY_WIDTH,
        baseline.NUMBER_OF_FREQUENCIES,
        mp.FluxRegion(
            center=mp.Vector3(
                z=baseline.TRANSMISSION_MONITOR_Z
            )
        ),
    )

    simulation.load_minus_flux_data(
        reflection_monitor,
        incident_reflection_data,
    )

    simulation.run(
        until_after_sources=mp.stop_when_fields_decayed(
            50,
            mp.Ex,
            mp.Vector3(
                z=baseline.TRANSMISSION_MONITOR_Z
            ),
            1e-9,
        )
    )

    reflected_flux = np.asarray(
        mp.get_fluxes(reflection_monitor),
        dtype=float,
    )
    transmitted_flux = np.asarray(
        mp.get_fluxes(transmission_monitor),
        dtype=float,
    )

    simulation.reset_meep()

    return reflected_flux, transmitted_flux


def analytic_single_layer_reflectance(
    wavelengths_um: np.ndarray,
) -> np.ndarray:
    n0 = AIR_REFRACTIVE_INDEX
    n1 = FILM_REFRACTIVE_INDEX
    n2 = GLASS_REFRACTIVE_INDEX

    r01 = (n0 - n1) / (n0 + n1)
    r12 = (n1 - n2) / (n1 + n2)

    phase_thickness = (
        2 * np.pi * n1 * FILM_THICKNESS_UM
        / wavelengths_um
    )

    round_trip_phase = np.exp(
        2j * phase_thickness
    )

    reflection_amplitude = (
        r01 + r12 * round_trip_phase
    ) / (
        1 + r01 * r12 * round_trip_phase
    )

    return np.abs(reflection_amplitude) ** 2


def main() -> None:
    RESULTS_DIRECTORY.mkdir(parents=True, exist_ok=True)

    baseline.RESOLUTION = RESOLUTION

    (
        frequencies,
        incident_reflection_flux,
        incident_transmission_flux,
        incident_reflection_data,
    ) = baseline.run_reference_simulation()

    reflected_flux, transmitted_flux = run_film_simulation(
        incident_reflection_data
    )

    minimum_incident_flux = max(
        np.max(np.abs(incident_transmission_flux)) * 1e-8,
        1e-15,
    )

    valid = (
        np.abs(incident_reflection_flux)
        > minimum_incident_flux
    ) & (
        np.abs(incident_transmission_flux)
        > minimum_incident_flux
    )

    wavelengths_um = 1 / frequencies[valid]
    wavelengths_nm = wavelengths_um * 1000

    reflectance = (
        -reflected_flux[valid]
        / incident_reflection_flux[valid]
    )

    transmittance = (
        transmitted_flux[valid]
        / incident_transmission_flux[valid]
    )

    energy_residual = (
        1 - reflectance - transmittance
    )

    analytic_reflectance = (
        analytic_single_layer_reflectance(
            wavelengths_um
        )
    )

    analytic_error = np.abs(
        reflectance - analytic_reflectance
    )

    bare_glass_reflectance = (
        (
            AIR_REFRACTIVE_INDEX
            - GLASS_REFRACTIVE_INDEX
        )
        / (
            AIR_REFRACTIVE_INDEX
            + GLASS_REFRACTIVE_INDEX
        )
    ) ** 2

    design_index = int(
        np.argmin(
            np.abs(
                wavelengths_nm
                - DESIGN_WAVELENGTH_UM * 1000
            )
        )
    )

    minimum_index = int(np.argmin(reflectance))
    order = np.argsort(wavelengths_nm)

    with CSV_PATH.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(
            [
                "wavelength_nm",
                "meep_reflectance",
                "analytic_reflectance",
                "meep_transmittance",
                "energy_residual",
                "bare_glass_reflectance",
            ]
        )

        for index in order:
            writer.writerow(
                [
                    float(wavelengths_nm[index]),
                    float(reflectance[index]),
                    float(analytic_reflectance[index]),
                    float(transmittance[index]),
                    float(energy_residual[index]),
                    float(bare_glass_reflectance),
                ]
            )

    summary = {
        "model": MODEL_NAME,
        "model_role": MODEL_ROLE,
        "meep_version": mp.__version__,
        "resolution_pixels_per_um": RESOLUTION,
        "air_refractive_index": AIR_REFRACTIVE_INDEX,
        "film_refractive_index": (
            FILM_REFRACTIVE_INDEX
        ),
        "glass_refractive_index": (
            GLASS_REFRACTIVE_INDEX
        ),
        "design_wavelength_nm": (
            DESIGN_WAVELENGTH_UM * 1000
        ),
        "film_thickness_nm": (
            FILM_THICKNESS_UM * 1000
        ),
        "bare_glass_fresnel_reflectance": float(
            bare_glass_reflectance
        ),
        "evaluated_wavelength_nm": float(
            wavelengths_nm[design_index]
        ),
        "reflectance_at_design_wavelength": float(
            reflectance[design_index]
        ),
        "transmittance_at_design_wavelength": float(
            transmittance[design_index]
        ),
        "minimum_meep_reflectance": float(
            reflectance[minimum_index]
        ),
        "minimum_reflectance_wavelength_nm": float(
            wavelengths_nm[minimum_index]
        ),
        "mean_reflectance_unweighted_frequency_grid": (
            float(np.mean(reflectance))
        ),
        "mean_transmittance_unweighted_frequency_grid": (
            float(np.mean(transmittance))
        ),
        "maximum_analytic_reflectance_error": float(
            np.max(analytic_error)
        ),
        "maximum_energy_residual": float(
            np.max(np.abs(energy_residual))
        ),
        "warning": (
            "Unweighted spectral values are not "
            "electrical power-gain results."
        ),
    }

    with SUMMARY_PATH.open(
        "w",
        encoding="utf-8",
    ) as summary_file:
        json.dump(summary, summary_file, indent=2)

    print()
    print(f"{MODEL_NAME} simulation completed.")
    print(
        "Film index        : "
        f"{FILM_REFRACTIVE_INDEX:.6f}"
    )
    print(
        "Film thickness    : "
        f"{FILM_THICKNESS_UM * 1000:.3f} nm"
    )
    print(
        "Bare-glass R      : "
        f"{bare_glass_reflectance * 100:.4f}%"
    )
    print(
        f"Film R near "
        f"{wavelengths_nm[design_index]:.2f} nm: "
        f"{reflectance[design_index] * 100:.4f}%"
    )
    print(
        f"Film T near "
        f"{wavelengths_nm[design_index]:.2f} nm: "
        f"{transmittance[design_index] * 100:.4f}%"
    )
    print(
        "Minimum Meep R    : "
        f"{reflectance[minimum_index] * 100:.4f}% "
        f"at {wavelengths_nm[minimum_index]:.2f} nm"
    )
    print(
        "Max analytic error: "
        f"{np.max(analytic_error):.6e}"
    )
    print(
        "Max energy error  : "
        f"{np.max(np.abs(energy_residual)):.6e}"
    )
    print(f"CSV result        : {CSV_PATH}")
    print(f"Summary result    : {SUMMARY_PATH}")


if __name__ == "__main__":
    main()