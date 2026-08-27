from __future__ import annotations

import csv
import importlib.metadata as metadata
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
from solcore.light_source import LightSource


PRODUCT1_DIRECTORY = Path(__file__).resolve().parents[1]
RESULTS_DIRECTORY = PRODUCT1_DIRECTORY / "results"

BASELINE_PATH = (
    RESULTS_DIRECTORY
    / "convergence"
    / "baseline_glass_res_200.csv"
)

FILM_PATH = RESULTS_DIRECTORY / "flat_film_ideal_ar.csv"

OUTPUT_CSV_PATH = (
    RESULTS_DIRECTORY
    / "solar_weighted_optics_ideal_ar.csv"
)

OUTPUT_JSON_PATH = (
    RESULTS_DIRECTORY
    / "solar_weighted_optics_ideal_ar.json"
)

FIGURES_DIRECTORY = RESULTS_DIRECTORY / "figures"

OUTPUT_FIGURE_PATH = (
    FIGURES_DIRECTORY
    / "am15g_transmitted_optical_power.png"
)


def read_spectrum(
    path: Path,
    transmittance_column: str,
):
    wavelengths = []
    transmittance = []

    with path.open("r", encoding="utf-8") as csv_file:
        reader = csv.DictReader(csv_file)

        for row in reader:
            wavelengths.append(
                float(row["wavelength_nm"])
            )
            transmittance.append(
                float(row[transmittance_column])
            )

    wavelengths_array = np.asarray(wavelengths)
    transmittance_array = np.asarray(transmittance)

    order = np.argsort(wavelengths_array)

    return (
        wavelengths_array[order],
        transmittance_array[order],
    )


def integrate_spectrum(
    values: np.ndarray,
    wavelengths_nm: np.ndarray,
) -> float:
    return float(
        np.trapezoid(values, wavelengths_nm)
    )


def main() -> None:
    FIGURES_DIRECTORY.mkdir(
        parents=True,
        exist_ok=True,
    )

    (
        wavelengths_nm,
        baseline_transmittance,
    ) = read_spectrum(
        BASELINE_PATH,
        "transmittance",
    )

    (
        film_wavelengths_nm,
        film_transmittance_raw,
    ) = read_spectrum(
        FILM_PATH,
        "meep_transmittance",
    )

    film_transmittance = np.interp(
        wavelengths_nm,
        film_wavelengths_nm,
        film_transmittance_raw,
    )

    am15g_source = LightSource(
        source_type="standard",
        version="AM1.5g",
        x=wavelengths_nm,
    )

    (
        solar_wavelengths_nm,
        solar_irradiance,
    ) = am15g_source.spectrum()

    solar_wavelengths_nm = np.asarray(
        solar_wavelengths_nm,
        dtype=float,
    )
    solar_irradiance = np.asarray(
        solar_irradiance,
        dtype=float,
    )

    baseline_transmitted_spectrum = (
        solar_irradiance
        * baseline_transmittance
    )

    film_transmitted_spectrum = (
        solar_irradiance
        * film_transmittance
    )

    incident_power = integrate_spectrum(
        solar_irradiance,
        solar_wavelengths_nm,
    )

    baseline_transmitted_power = integrate_spectrum(
        baseline_transmitted_spectrum,
        solar_wavelengths_nm,
    )

    film_transmitted_power = integrate_spectrum(
        film_transmitted_spectrum,
        solar_wavelengths_nm,
    )

    baseline_weighted_transmittance = (
        baseline_transmitted_power
        / incident_power
    )

    film_weighted_transmittance = (
        film_transmitted_power
        / incident_power
    )

    absolute_gain_percentage_points = (
        film_weighted_transmittance
        - baseline_weighted_transmittance
    ) * 100

    relative_optical_gain_percent = (
        film_transmitted_power
        / baseline_transmitted_power
        - 1
    ) * 100

    with OUTPUT_CSV_PATH.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as csv_file:
        writer = csv.writer(csv_file)

        writer.writerow(
            [
                "wavelength_nm",
                "am15g_irradiance_w_m2_nm",
                "baseline_transmittance",
                "film_transmittance",
                "baseline_transmitted_w_m2_nm",
                "film_transmitted_w_m2_nm",
            ]
        )

        for index in range(len(wavelengths_nm)):
            writer.writerow(
                [
                    float(solar_wavelengths_nm[index]),
                    float(solar_irradiance[index]),
                    float(
                        baseline_transmittance[index]
                    ),
                    float(film_transmittance[index]),
                    float(
                        baseline_transmitted_spectrum[index]
                    ),
                    float(
                        film_transmitted_spectrum[index]
                    ),
                ]
            )

    summary = {
        "model": (
            "AM1.5G-weighted optical transmission "
            "comparison"
        ),
        "solcore_version": metadata.version("solcore"),
        "wavelength_min_nm": float(
            wavelengths_nm.min()
        ),
        "wavelength_max_nm": float(
            wavelengths_nm.max()
        ),
        "incident_power_in_band_w_m2": incident_power,
        "baseline_transmitted_power_w_m2": (
            baseline_transmitted_power
        ),
        "ideal_film_transmitted_power_w_m2": (
            film_transmitted_power
        ),
        "baseline_weighted_transmittance": (
            baseline_weighted_transmittance
        ),
        "ideal_film_weighted_transmittance": (
            film_weighted_transmittance
        ),
        "absolute_gain_percentage_points": (
            absolute_gain_percentage_points
        ),
        "relative_optical_gain_percent": (
            relative_optical_gain_percent
        ),
        "warning": (
            "Optical power gain only. This is not "
            "electrical module power or energy yield."
        ),
    }

    with OUTPUT_JSON_PATH.open(
        "w",
        encoding="utf-8",
    ) as json_file:
        json.dump(summary, json_file, indent=2)

    figure, axes = plt.subplots(
        2,
        1,
        figsize=(10, 8),
        sharex=True,
    )

    axes[0].plot(
        solar_wavelengths_nm,
        solar_irradiance,
        color="goldenrod",
        linewidth=1.5,
    )

    axes[0].set_ylabel(
        "AM1.5G irradiance\n(W m⁻² nm⁻¹)"
    )
    axes[0].set_title(
        "AM1.5G-Weighted Optical Transmission"
    )
    axes[0].grid(alpha=0.3)

    axes[1].plot(
        solar_wavelengths_nm,
        baseline_transmitted_spectrum,
        label="Bare glass",
        linewidth=1.5,
    )

    axes[1].plot(
        solar_wavelengths_nm,
        film_transmitted_spectrum,
        label="Ideal flat film",
        linewidth=1.5,
    )

    axes[1].set_xlabel("Wavelength (nm)")
    axes[1].set_ylabel(
        "Transmitted irradiance\n(W m⁻² nm⁻¹)"
    )
    axes[1].grid(alpha=0.3)
    axes[1].legend()

    figure.tight_layout()
    figure.savefig(
        OUTPUT_FIGURE_PATH,
        dpi=180,
        bbox_inches="tight",
    )

    print()
    print("AM1.5G weighting completed.")
    print(
        "Incident power in band      : "
        f"{incident_power:.3f} W/m²"
    )
    print(
        "Bare-glass transmitted power: "
        f"{baseline_transmitted_power:.3f} W/m²"
    )
    print(
        "Ideal-film transmitted power: "
        f"{film_transmitted_power:.3f} W/m²"
    )
    print(
        "Absolute optical gain       : "
        f"{absolute_gain_percentage_points:.4f} "
        "percentage points"
    )
    print(
        "Relative optical gain       : "
        f"{relative_optical_gain_percent:.4f}%"
    )
    print(f"Summary: {OUTPUT_JSON_PATH}")
    print(f"Figure : {OUTPUT_FIGURE_PATH}")


if __name__ == "__main__":
    main()