from __future__ import annotations

import csv
import json
from pathlib import Path

import meep as mp
import numpy as np


# Meep length unit: micrometre (µm)
WAVELENGTH_MIN_UM = 0.3
WAVELENGTH_MAX_UM = 1.2
NUMBER_OF_FREQUENCIES = 181

GLASS_REFRACTIVE_INDEX = 1.52

RESOLUTION = 100
PML_THICKNESS_UM = 1.0
CELL_LENGTH_UM = 12.0

SOURCE_Z = -0.5 * CELL_LENGTH_UM + PML_THICKNESS_UM
REFLECTION_MONITOR_Z = -0.25 * CELL_LENGTH_UM
TRANSMISSION_MONITOR_Z = 0.25 * CELL_LENGTH_UM

FREQUENCY_MIN = 1 / WAVELENGTH_MAX_UM
FREQUENCY_MAX = 1 / WAVELENGTH_MIN_UM
FREQUENCY_CENTER = 0.5 * (FREQUENCY_MIN + FREQUENCY_MAX)
FREQUENCY_WIDTH = FREQUENCY_MAX - FREQUENCY_MIN

RESULTS_DIRECTORY = Path(__file__).resolve().parents[1] / "results"
CSV_PATH = RESULTS_DIRECTORY / "baseline_glass.csv"
SUMMARY_PATH = RESULTS_DIRECTORY / "baseline_glass_summary.json"


def create_simulation(geometry: list[mp.GeometricObject]) -> mp.Simulation:
    source = mp.Source(
        src=mp.GaussianSource(
            frequency=FREQUENCY_CENTER,
            fwidth=FREQUENCY_WIDTH,
        ),
        component=mp.Ex,
        center=mp.Vector3(z=SOURCE_Z),
    )

    return mp.Simulation(
        cell_size=mp.Vector3(z=CELL_LENGTH_UM),
        boundary_layers=[mp.PML(PML_THICKNESS_UM)],
        geometry=geometry,
        sources=[source],
        dimensions=1,
        resolution=RESOLUTION,
    )


def run_reference_simulation():
    simulation = create_simulation(geometry=[])

    reflection_monitor = simulation.add_flux(
        FREQUENCY_CENTER,
        FREQUENCY_WIDTH,
        NUMBER_OF_FREQUENCIES,
        mp.FluxRegion(center=mp.Vector3(z=REFLECTION_MONITOR_Z)),
    )

    transmission_monitor = simulation.add_flux(
        FREQUENCY_CENTER,
        FREQUENCY_WIDTH,
        NUMBER_OF_FREQUENCIES,
        mp.FluxRegion(center=mp.Vector3(z=TRANSMISSION_MONITOR_Z)),
    )

    simulation.run(
        until_after_sources=mp.stop_when_fields_decayed(
            50,
            mp.Ex,
            mp.Vector3(z=TRANSMISSION_MONITOR_Z),
            1e-9,
        )
    )

    incident_reflection_flux = np.asarray(
        mp.get_fluxes(reflection_monitor),
        dtype=float,
    )
    incident_transmission_flux = np.asarray(
        mp.get_fluxes(transmission_monitor),
        dtype=float,
    )
    incident_reflection_data = simulation.get_flux_data(reflection_monitor)
    frequencies = np.asarray(
        mp.get_flux_freqs(transmission_monitor),
        dtype=float,
    )

    simulation.reset_meep()

    return (
        frequencies,
        incident_reflection_flux,
        incident_transmission_flux,
        incident_reflection_data,
    )


def run_glass_simulation(incident_reflection_data):
    glass = mp.Medium(index=GLASS_REFRACTIVE_INDEX)

    geometry = [
        mp.Block(
            size=mp.Vector3(mp.inf, mp.inf, 0.5 * CELL_LENGTH_UM),
            center=mp.Vector3(z=0.25 * CELL_LENGTH_UM),
            material=glass,
        )
    ]

    simulation = create_simulation(geometry)

    reflection_monitor = simulation.add_flux(
        FREQUENCY_CENTER,
        FREQUENCY_WIDTH,
        NUMBER_OF_FREQUENCIES,
        mp.FluxRegion(center=mp.Vector3(z=REFLECTION_MONITOR_Z)),
    )

    transmission_monitor = simulation.add_flux(
        FREQUENCY_CENTER,
        FREQUENCY_WIDTH,
        NUMBER_OF_FREQUENCIES,
        mp.FluxRegion(center=mp.Vector3(z=TRANSMISSION_MONITOR_Z)),
    )

    # Subtract incident fields so the reflection monitor contains
    # only the reflected fields.
    simulation.load_minus_flux_data(
        reflection_monitor,
        incident_reflection_data,
    )

    simulation.run(
        until_after_sources=mp.stop_when_fields_decayed(
            50,
            mp.Ex,
            mp.Vector3(z=TRANSMISSION_MONITOR_Z),
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


def main() -> None:
    RESULTS_DIRECTORY.mkdir(parents=True, exist_ok=True)

    (
        frequencies,
        incident_reflection_flux,
        incident_transmission_flux,
        incident_reflection_data,
    ) = run_reference_simulation()

    reflected_flux, transmitted_flux = run_glass_simulation(
        incident_reflection_data
    )

    minimum_incident_flux = max(
        np.max(np.abs(incident_transmission_flux)) * 1e-8,
        1e-15,
    )

    valid = (
        np.abs(incident_reflection_flux) > minimum_incident_flux
    ) & (
        np.abs(incident_transmission_flux) > minimum_incident_flux
    )

    wavelengths_nm = 1000 / frequencies[valid]

    reflectance = (
        -reflected_flux[valid] / incident_reflection_flux[valid]
    )
    transmittance = (
        transmitted_flux[valid] / incident_transmission_flux[valid]
    )

    energy_residual = 1 - reflectance - transmittance

    fresnel_reflectance = (
        (1 - GLASS_REFRACTIVE_INDEX)
        / (1 + GLASS_REFRACTIVE_INDEX)
    ) ** 2

    fresnel_error = np.abs(reflectance - fresnel_reflectance)

    order = np.argsort(wavelengths_nm)

    with CSV_PATH.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(
            [
                "wavelength_nm",
                "reflectance",
                "transmittance",
                "energy_residual",
                "fresnel_reflectance",
            ]
        )

        for index in order:
            writer.writerow(
                [
                    float(wavelengths_nm[index]),
                    float(reflectance[index]),
                    float(transmittance[index]),
                    float(energy_residual[index]),
                    float(fresnel_reflectance),
                ]
            )

    summary = {
        "model": "1D air-to-glass interface baseline",
        "meep_version": mp.__version__,
        "glass_refractive_index": GLASS_REFRACTIVE_INDEX,
        "resolution_pixels_per_um": RESOLUTION,
        "pml_thickness_um": PML_THICKNESS_UM,
        "number_of_frequencies": NUMBER_OF_FREQUENCIES,
        "wavelength_min_nm": WAVELENGTH_MIN_UM * 1000,
        "wavelength_max_nm": WAVELENGTH_MAX_UM * 1000,
        "valid_frequency_points": int(np.count_nonzero(valid)),
        "mean_reflectance": float(np.mean(reflectance)),
        "mean_transmittance": float(np.mean(transmittance)),
        "analytic_fresnel_reflectance": float(fresnel_reflectance),
        "maximum_fresnel_error": float(np.max(fresnel_error)),
        "maximum_energy_residual": float(
            np.max(np.abs(energy_residual))
        ),
        "warning": (
            "Validation baseline only. This is not an electrical "
            "power-gain result."
        ),
    }

    with SUMMARY_PATH.open("w", encoding="utf-8") as summary_file:
        json.dump(summary, summary_file, indent=2)

    print()
    print("Baseline glass simulation completed.")
    print(f"Analytic Fresnel R : {fresnel_reflectance:.6f}")
    print(f"Mean Meep R       : {np.mean(reflectance):.6f}")
    print(f"Mean Meep T       : {np.mean(transmittance):.6f}")
    print(f"Max Fresnel error : {np.max(fresnel_error):.6e}")
    print(
        "Max energy error  : "
        f"{np.max(np.abs(energy_residual)):.6e}"
    )
    print(f"CSV result        : {CSV_PATH}")
    print(f"Summary result    : {SUMMARY_PATH}")


if __name__ == "__main__":
    main()