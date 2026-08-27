from __future__ import annotations

import csv
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from solcore.light_source import LightSource


PRODUCT_DIRECTORY = Path(__file__).resolve().parents[1]
RESULTS_DIRECTORY = PRODUCT_DIRECTORY / "results"
FIGURES_DIRECTORY = RESULTS_DIRECTORY / "figures"

OUTPUT_CSV_PATH = (
    RESULTS_DIRECTORY
    / "am15g_optical_baseline_comparison.csv"
)

OUTPUT_JSON_PATH = (
    RESULTS_DIRECTORY
    / "am15g_optical_baseline_comparison.json"
)

OUTPUT_FIGURE_PATH = (
    FIGURES_DIRECTORY
    / "am15g_optical_baseline_comparison.png"
)

CASE_PATHS = {
    "Bare glass": (
        RESULTS_DIRECTORY / "baseline_glass.csv"
    ),
    "Existing AR 100 nm": (
        RESULTS_DIRECTORY
        / "existing_ar_n1p28_100nm.csv"
    ),
    "Existing AR 180 nm": (
        RESULTS_DIRECTORY
        / "existing_ar_n1p28_180nm.csv"
    ),
    "Ideal flat film": (
        RESULTS_DIRECTORY / "flat_film_ideal_ar.csv"
    ),
}

WAVELENGTH_MIN_NM = 300.0
WAVELENGTH_MAX_NM = 1200.0
WAVELENGTH_STEP_NM = 1.0


def load_transmittance(
    path: Path,
) -> tuple[np.ndarray, np.ndarray]:
    with path.open(
        "r",
        encoding="utf-8",
        newline="",
    ) as csv_file:
        reader = csv.DictReader(csv_file)
        fieldnames = reader.fieldnames or []
        rows = list(reader)

    transmission_column = next(
        (
            candidate
            for candidate in (
                "meep_transmittance",
                "transmittance",
                "T",
            )
            if candidate in fieldnames
        ),
        None,
    )

    if transmission_column is None:
        raise KeyError(
            f"No transmittance column found in {path}. "
            f"Available columns: {fieldnames}"
        )

    wavelength_nm = np.array(
        [
            float(row["wavelength_nm"])
            for row in rows
        ],
        dtype=float,
    )

    transmittance = np.array(
        [
            float(row[transmission_column])
            for row in rows
        ],
        dtype=float,
    )

    order = np.argsort(wavelength_nm)

    return (
        wavelength_nm[order],
        transmittance[order],
    )


def calculate_gain(
    candidate_power: float,
    reference_power: float,
    incident_power: float,
) -> dict[str, float]:
    return {
        "additional_transmitted_power_w_m2": (
            candidate_power - reference_power
        ),
        "absolute_gain_percentage_points": (
            (
                candidate_power
                - reference_power
            )
            / incident_power
            * 100
        ),
        "relative_gain_percent": (
            (
                candidate_power
                / reference_power
            )
            - 1
        )
        * 100,
    }


def main() -> None:
    FIGURES_DIRECTORY.mkdir(
        parents=True,
        exist_ok=True,
    )

    analysis_wavelength_nm = np.arange(
        WAVELENGTH_MIN_NM,
        WAVELENGTH_MAX_NM
        + WAVELENGTH_STEP_NM,
        WAVELENGTH_STEP_NM,
    )

    source = LightSource(
        source_type="standard",
        version="AM1.5g",
        x=analysis_wavelength_nm,
        output_units="power_density_per_nm",
    )

    (
        solar_wavelength_nm,
        solar_irradiance,
    ) = source.spectrum()

    solar_wavelength_nm = np.asarray(
        solar_wavelength_nm,
        dtype=float,
    )

    solar_irradiance = np.asarray(
        solar_irradiance,
        dtype=float,
    )

    incident_power = float(
        np.trapezoid(
            solar_irradiance,
            solar_wavelength_nm,
        )
    )

    spectra: dict[str, np.ndarray] = {}
    results: dict[str, dict[str, float]] = {}

    for case_name, path in CASE_PATHS.items():
        wavelength_nm, transmittance = (
            load_transmittance(path)
        )

        interpolated_transmittance = np.interp(
            solar_wavelength_nm,
            wavelength_nm,
            transmittance,
        )

        transmitted_spectral_power = (
            solar_irradiance
            * interpolated_transmittance
        )

        transmitted_power = float(
            np.trapezoid(
                transmitted_spectral_power,
                solar_wavelength_nm,
            )
        )

        weighted_transmittance = (
            transmitted_power
            / incident_power
        )

        spectra[case_name] = (
            interpolated_transmittance
        )

        results[case_name] = {
            "transmitted_power_w_m2": (
                transmitted_power
            ),
            "solar_weighted_transmittance": (
                weighted_transmittance
            ),
            "solar_weighted_transmittance_percent": (
                weighted_transmittance * 100
            ),
        }

    bare_power = results[
        "Bare glass"
    ]["transmitted_power_w_m2"]

    for case_name, case_result in results.items():
        case_result.update(
            calculate_gain(
                candidate_power=case_result[
                    "transmitted_power_w_m2"
                ],
                reference_power=bare_power,
                incident_power=incident_power,
            )
        )

    ideal_power = results[
        "Ideal flat film"
    ]["transmitted_power_w_m2"]

    headroom = {
        "versus_existing_ar_100nm": (
            calculate_gain(
                candidate_power=ideal_power,
                reference_power=results[
                    "Existing AR 100 nm"
                ]["transmitted_power_w_m2"],
                incident_power=incident_power,
            )
        ),
        "versus_existing_ar_180nm": (
            calculate_gain(
                candidate_power=ideal_power,
                reference_power=results[
                    "Existing AR 180 nm"
                ]["transmitted_power_w_m2"],
                incident_power=incident_power,
            )
        ),
    }

    with OUTPUT_CSV_PATH.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as csv_file:
        fieldnames = [
            "case",
            "transmitted_power_w_m2",
            "solar_weighted_transmittance_percent",
            "additional_power_vs_bare_w_m2",
            "absolute_gain_vs_bare_percentage_points",
            "relative_gain_vs_bare_percent",
        ]

        writer = csv.DictWriter(
            csv_file,
            fieldnames=fieldnames,
        )

        writer.writeheader()

        for case_name, case_result in results.items():
            writer.writerow(
                {
                    "case": case_name,
                    "transmitted_power_w_m2": (
                        case_result[
                            "transmitted_power_w_m2"
                        ]
                    ),
                    "solar_weighted_transmittance_percent": (
                        case_result[
                            "solar_weighted_transmittance_percent"
                        ]
                    ),
                    "additional_power_vs_bare_w_m2": (
                        case_result[
                            "additional_transmitted_power_w_m2"
                        ]
                    ),
                    "absolute_gain_vs_bare_percentage_points": (
                        case_result[
                            "absolute_gain_percentage_points"
                        ]
                    ),
                    "relative_gain_vs_bare_percent": (
                        case_result[
                            "relative_gain_percent"
                        ]
                    ),
                }
            )

    summary = {
        "analysis": (
            "AM1.5G-weighted optical baseline "
            "headroom comparison"
        ),
        "analysis_role": (
            "Compares separate optical baselines. "
            "This is not yet a stacked retrofit model."
        ),
        "wavelength_min_nm": WAVELENGTH_MIN_NM,
        "wavelength_max_nm": WAVELENGTH_MAX_NM,
        "incident_power_in_band_w_m2": (
            incident_power
        ),
        "cases": results,
        "ideal_film_headroom": headroom,
        "warning": (
            "Optical transmission gain is not "
            "electrical power gain."
        ),
    }

    OUTPUT_JSON_PATH.write_text(
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

    for case_name, transmittance in spectra.items():
        axes[0].plot(
            solar_wavelength_nm,
            transmittance * 100,
            label=case_name,
        )

        axes[1].plot(
            solar_wavelength_nm,
            solar_irradiance * transmittance,
            label=case_name,
        )

    axes[0].set_ylabel("Transmittance (%)")
    axes[0].set_title(
        "Optical Baselines under AM1.5G"
    )
    axes[0].grid(alpha=0.3)
    axes[0].legend()

    axes[1].set_xlabel("Wavelength (nm)")
    axes[1].set_ylabel(
        "Transmitted spectral power "
        "(W m$^{-2}$ nm$^{-1}$)"
    )
    axes[1].grid(alpha=0.3)
    axes[1].legend()

    figure.tight_layout()
    figure.savefig(
        OUTPUT_FIGURE_PATH,
        dpi=180,
    )
    plt.close(figure)

    print(
        "AM1.5G optical baseline comparison "
        "completed."
    )
    print(
        f"Incident power in band: "
        f"{incident_power:.3f} W/m²"
    )

    for case_name, case_result in results.items():
        print()
        print(case_name)
        print(
            "  Transmitted power: "
            f"{case_result['transmitted_power_w_m2']:.3f} "
            "W/m²"
        )
        print(
            "  Weighted T: "
            f"{case_result['solar_weighted_transmittance_percent']:.4f}%"
        )
        print(
            "  Relative gain vs bare: "
            f"{case_result['relative_gain_percent']:.4f}%"
        )

    print()
    print("Ideal-film optical headroom:")
    for reference_name, gain in headroom.items():
        print(
            f"  {reference_name}: "
            f"{gain['relative_gain_percent']:.4f}%"
        )

    print()
    print(f"CSV: {OUTPUT_CSV_PATH}")
    print(f"JSON: {OUTPUT_JSON_PATH}")
    print(f"Figure: {OUTPUT_FIGURE_PATH}")
    print()
    print(
        "WARNING: These are separate baseline "
        "models, not a stacked retrofit result."
    )


if __name__ == "__main__":
    main()