from __future__ import annotations

import csv
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np


PRODUCT1_DIRECTORY = Path(__file__).resolve().parents[1]
RESULTS_DIRECTORY = PRODUCT1_DIRECTORY / "results"

BASELINE_PATH = (
    RESULTS_DIRECTORY
    / "convergence"
    / "baseline_glass_res_200.csv"
)

FILM_PATH = RESULTS_DIRECTORY / "flat_film_ideal_ar.csv"

FIGURES_DIRECTORY = RESULTS_DIRECTORY / "figures"
OUTPUT_PATH = (
    FIGURES_DIRECTORY
    / "bare_glass_vs_ideal_flat_film.png"
)


def read_columns(
    path: Path,
    wavelength_column: str,
    reflectance_column: str,
    transmittance_column: str,
):
    wavelengths = []
    reflectance = []
    transmittance = []

    with path.open("r", encoding="utf-8") as csv_file:
        reader = csv.DictReader(csv_file)

        for row in reader:
            wavelengths.append(
                float(row[wavelength_column])
            )
            reflectance.append(
                float(row[reflectance_column])
            )
            transmittance.append(
                float(row[transmittance_column])
            )

    wavelengths_array = np.asarray(wavelengths)
    order = np.argsort(wavelengths_array)

    return (
        wavelengths_array[order],
        np.asarray(reflectance)[order],
        np.asarray(transmittance)[order],
    )


def main() -> None:
    FIGURES_DIRECTORY.mkdir(
        parents=True,
        exist_ok=True,
    )

    (
        baseline_wavelengths,
        baseline_reflectance,
        baseline_transmittance,
    ) = read_columns(
        BASELINE_PATH,
        "wavelength_nm",
        "reflectance",
        "transmittance",
    )

    (
        film_wavelengths,
        film_reflectance,
        film_transmittance,
    ) = read_columns(
        FILM_PATH,
        "wavelength_nm",
        "meep_reflectance",
        "meep_transmittance",
    )

    figure, axes = plt.subplots(
        2,
        1,
        figsize=(10, 8),
        sharex=True,
    )

    axes[0].plot(
        baseline_wavelengths,
        baseline_reflectance * 100,
        label="Bare glass",
        linewidth=2,
    )

    axes[0].plot(
        film_wavelengths,
        film_reflectance * 100,
        label="Ideal flat film",
        linewidth=2,
    )

    axes[0].axvline(
        550,
        color="gray",
        linestyle="--",
        linewidth=1,
        label="Design wavelength (550 nm)",
    )

    axes[0].set_ylabel("Reflectance (%)")
    axes[0].set_title(
        "Bare Glass vs Ideal Quarter-Wave Film"
    )
    axes[0].grid(alpha=0.3)
    axes[0].legend()

    axes[1].plot(
        baseline_wavelengths,
        baseline_transmittance * 100,
        label="Bare glass",
        linewidth=2,
    )

    axes[1].plot(
        film_wavelengths,
        film_transmittance * 100,
        label="Ideal flat film",
        linewidth=2,
    )

    axes[1].axvline(
        550,
        color="gray",
        linestyle="--",
        linewidth=1,
    )

    axes[1].set_xlabel("Wavelength (nm)")
    axes[1].set_ylabel("Transmittance (%)")
    axes[1].set_xlim(300, 1200)
    axes[1].grid(alpha=0.3)
    axes[1].legend()

    figure.tight_layout()
    figure.savefig(
        OUTPUT_PATH,
        dpi=180,
        bbox_inches="tight",
    )

    print(f"Figure created: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()