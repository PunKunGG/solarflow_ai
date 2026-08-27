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

EXISTING_AR_CSV_PATH = (
    RESULTS_DIRECTORY
    / "existing_ar_n1p28_100nm.csv"
)

OUTPUT_CSV_PATH = (
    RESULTS_DIRECTORY
    / "stacked_retrofit_tmm.csv"
)

OUTPUT_JSON_PATH = (
    RESULTS_DIRECTORY
    / "stacked_retrofit_tmm_summary.json"
)

OUTPUT_FIGURE_PATH = (
    FIGURES_DIRECTORY
    / "stacked_retrofit_tmm.png"
)

AIR_REFRACTIVE_INDEX = 1.0
GLASS_REFRACTIVE_INDEX = 1.52

EXISTING_AR_REFRACTIVE_INDEX = 1.28
EXISTING_AR_THICKNESS_NM = 100.0

DESIGN_WAVELENGTH_NM = 550.0

RETROFIT_REFRACTIVE_INDEX = np.sqrt(
    AIR_REFRACTIVE_INDEX
    * GLASS_REFRACTIVE_INDEX
)

RETROFIT_THICKNESS_NM = (
    DESIGN_WAVELENGTH_NM
    / (
        4
        * RETROFIT_REFRACTIVE_INDEX
    )
)

WAVELENGTH_NM = np.arange(
    300.0,
    1201.0,
    1.0,
)


def stack_reflectance(
    wavelength_nm: np.ndarray,
    layers: list[tuple[float, float]],
) -> np.ndarray:
    m11 = np.ones_like(
        wavelength_nm,
        dtype=complex,
    )
    m12 = np.zeros_like(
        wavelength_nm,
        dtype=complex,
    )
    m21 = np.zeros_like(
        wavelength_nm,
        dtype=complex,
    )
    m22 = np.ones_like(
        wavelength_nm,
        dtype=complex,
    )

    for refractive_index, thickness_nm in layers:
        phase = (
            2
            * np.pi
            * refractive_index
            * thickness_nm
            / wavelength_nm
        )

        layer11 = np.cos(phase)
        layer12 = (
            1j
            * np.sin(phase)
            / refractive_index
        )
        layer21 = (
            1j
            * refractive_index
            * np.sin(phase)
        )
        layer22 = np.cos(phase)

        next11 = (
            m11 * layer11
            + m12 * layer21
        )
        next12 = (
            m11 * layer12
            + m12 * layer22
        )
        next21 = (
            m21 * layer11
            + m22 * layer21
        )
        next22 = (
            m21 * layer12
            + m22 * layer22
        )

        m11 = next11
        m12 = next12
        m21 = next21
        m22 = next22

    optical_admittance = (
        (
            m21
            + m22 * GLASS_REFRACTIVE_INDEX
        )
        / (
            m11
            + m12 * GLASS_REFRACTIVE_INDEX
        )
    )

    reflection_amplitude = (
        AIR_REFRACTIVE_INDEX
        - optical_admittance
    ) / (
        AIR_REFRACTIVE_INDEX
        + optical_admittance
    )

    return np.abs(
        reflection_amplitude
    ) ** 2


def load_existing_ar_meep() -> tuple[
    np.ndarray,
    np.ndarray,
    np.ndarray,
]:
    with EXISTING_AR_CSV_PATH.open(
        "r",
        encoding="utf-8",
        newline="",
    ) as csv_file:
        rows = list(
            csv.DictReader(csv_file)
        )

    wavelength_nm = np.array(
        [
            float(row["wavelength_nm"])
            for row in rows
        ],
        dtype=float,
    )

    reflectance = np.array(
        [
            float(row["meep_reflectance"])
            for row in rows
        ],
        dtype=float,
    )

    transmittance = np.array(
        [
            float(row["meep_transmittance"])
            for row in rows
        ],
        dtype=float,
    )

    order = np.argsort(wavelength_nm)

    return (
        wavelength_nm[order],
        reflectance[order],
        transmittance[order],
    )


def weighted_result(
    solar_irradiance: np.ndarray,
    transmittance: np.ndarray,
) -> tuple[float, float]:
    incident_power = float(
        np.trapezoid(
            solar_irradiance,
            WAVELENGTH_NM,
        )
    )

    transmitted_power = float(
        np.trapezoid(
            solar_irradiance
            * transmittance,
            WAVELENGTH_NM,
        )
    )

    weighted_transmittance = (
        transmitted_power
        / incident_power
    )

    return (
        transmitted_power,
        weighted_transmittance,
    )


def main() -> None:
    FIGURES_DIRECTORY.mkdir(
        parents=True,
        exist_ok=True,
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

    existing_ar_reflectance = (
        stack_reflectance(
            WAVELENGTH_NM,
            [
                (
                    EXISTING_AR_REFRACTIVE_INDEX,
                    EXISTING_AR_THICKNESS_NM,
                ),
            ],
        )
    )

    stacked_reflectance = stack_reflectance(
        WAVELENGTH_NM,
        [
            (
                RETROFIT_REFRACTIVE_INDEX,
                RETROFIT_THICKNESS_NM,
            ),
            (
                EXISTING_AR_REFRACTIVE_INDEX,
                EXISTING_AR_THICKNESS_NM,
            ),
        ],
    )

    existing_ar_transmittance = (
        1
        - existing_ar_reflectance
    )

    stacked_transmittance = (
        1
        - stacked_reflectance
    )

    (
        meep_wavelength_nm,
        meep_reflectance,
        meep_transmittance,
    ) = load_existing_ar_meep()

    interpolated_meep_reflectance = np.interp(
        WAVELENGTH_NM,
        meep_wavelength_nm,
        meep_reflectance,
    )

    interpolated_meep_transmittance = np.interp(
        WAVELENGTH_NM,
        meep_wavelength_nm,
        meep_transmittance,
    )

    maximum_meep_tmm_error = float(
        np.max(
            np.abs(
                existing_ar_reflectance
                - interpolated_meep_reflectance
            )
        )
    )

    (
        existing_power,
        existing_weighted_transmittance,
    ) = weighted_result(
        solar_irradiance,
        existing_ar_transmittance,
    )

    (
        stacked_power,
        stacked_weighted_transmittance,
    ) = weighted_result(
        solar_irradiance,
        stacked_transmittance,
    )

    additional_power = (
        stacked_power
        - existing_power
    )

    absolute_gain_percentage_points = (
        (
            stacked_power
            - existing_power
        )
        / incident_power
        * 100
    )

    relative_gain_percent = (
        (
            stacked_power
            / existing_power
        )
        - 1
    ) * 100

    with OUTPUT_CSV_PATH.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as csv_file:
        fieldnames = [
            "wavelength_nm",
            "solar_irradiance_w_m2_nm",
            "existing_ar_reflectance_tmm",
            "existing_ar_transmittance_tmm",
            "existing_ar_reflectance_meep",
            "existing_ar_transmittance_meep",
            "stacked_retrofit_reflectance_tmm",
            "stacked_retrofit_transmittance_tmm",
            "stacked_minus_existing_transmittance",
        ]

        writer = csv.DictWriter(
            csv_file,
            fieldnames=fieldnames,
        )

        writer.writeheader()

        for index, wavelength_nm in enumerate(
            WAVELENGTH_NM
        ):
            writer.writerow(
                {
                    "wavelength_nm": wavelength_nm,
                    "solar_irradiance_w_m2_nm": (
                        solar_irradiance[index]
                    ),
                    "existing_ar_reflectance_tmm": (
                        existing_ar_reflectance[index]
                    ),
                    "existing_ar_transmittance_tmm": (
                        existing_ar_transmittance[index]
                    ),
                    "existing_ar_reflectance_meep": (
                        interpolated_meep_reflectance[
                            index
                        ]
                    ),
                    "existing_ar_transmittance_meep": (
                        interpolated_meep_transmittance[
                            index
                        ]
                    ),
                    "stacked_retrofit_reflectance_tmm": (
                        stacked_reflectance[index]
                    ),
                    "stacked_retrofit_transmittance_tmm": (
                        stacked_transmittance[index]
                    ),
                    "stacked_minus_existing_transmittance": (
                        stacked_transmittance[index]
                        - existing_ar_transmittance[index]
                    ),
                }
            )

    summary = {
        "model": (
            "Direct-contact flat retrofit film "
            "over representative existing AR"
        ),
        "model_role": (
            "Naive stacked-film baseline, "
            "not an optimized final design"
        ),
        "assumptions": {
            "air_gap": False,
            "adhesive_layer": False,
            "angle_of_incidence_degrees": 0,
            "existing_ar_refractive_index": (
                EXISTING_AR_REFRACTIVE_INDEX
            ),
            "existing_ar_thickness_nm": (
                EXISTING_AR_THICKNESS_NM
            ),
            "retrofit_refractive_index": float(
                RETROFIT_REFRACTIVE_INDEX
            ),
            "retrofit_thickness_nm": float(
                RETROFIT_THICKNESS_NM
            ),
        },
        "incident_power_in_band_w_m2": (
            incident_power
        ),
        "existing_ar": {
            "transmitted_power_w_m2": (
                existing_power
            ),
            "weighted_transmittance_percent": (
                existing_weighted_transmittance
                * 100
            ),
        },
        "stacked_retrofit": {
            "transmitted_power_w_m2": (
                stacked_power
            ),
            "weighted_transmittance_percent": (
                stacked_weighted_transmittance
                * 100
            ),
        },
        "stacked_gain_vs_existing_ar": {
            "additional_power_w_m2": (
                additional_power
            ),
            "absolute_gain_percentage_points": (
                absolute_gain_percentage_points
            ),
            "relative_gain_percent": (
                relative_gain_percent
            ),
        },
        "validation": {
            "maximum_existing_ar_meep_tmm_error": (
                maximum_meep_tmm_error
            ),
        },
        "warning": (
            "Optical gain is not electrical "
            "power gain."
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

    axes[0].plot(
        WAVELENGTH_NM,
        existing_ar_reflectance * 100,
        label="Existing AR 100 nm",
    )

    axes[0].plot(
        WAVELENGTH_NM,
        stacked_reflectance * 100,
        label="AR + naive retrofit",
    )

    axes[0].set_ylabel("Reflectance (%)")
    axes[0].set_title(
        "Direct-Contact Stacked Retrofit Baseline"
    )
    axes[0].grid(alpha=0.3)
    axes[0].legend()

    axes[1].plot(
        WAVELENGTH_NM,
        (
            stacked_transmittance
            - existing_ar_transmittance
        )
        * 100,
        color="tab:red",
    )

    axes[1].axhline(
        0,
        color="black",
        linewidth=1,
    )

    axes[1].set_xlabel("Wavelength (nm)")
    axes[1].set_ylabel(
        "Transmission change "
        "(percentage points)"
    )
    axes[1].grid(alpha=0.3)

    figure.tight_layout()
    figure.savefig(
        OUTPUT_FIGURE_PATH,
        dpi=180,
    )
    plt.close(figure)

    print(
        "Stacked retrofit TMM screening completed."
    )
    print(
        f"Retrofit index      : "
        f"{RETROFIT_REFRACTIVE_INDEX:.6f}"
    )
    print(
        f"Retrofit thickness  : "
        f"{RETROFIT_THICKNESS_NM:.3f} nm"
    )
    print(
        f"Existing AR power   : "
        f"{existing_power:.3f} W/m²"
    )
    print(
        f"Stacked power       : "
        f"{stacked_power:.3f} W/m²"
    )
    print(
        f"Additional power    : "
        f"{additional_power:.3f} W/m²"
    )
    print(
        f"Absolute gain       : "
        f"{absolute_gain_percentage_points:.4f} "
        "percentage points"
    )
    print(
        f"Relative gain       : "
        f"{relative_gain_percent:.4f}%"
    )
    print(
        f"Max Meep-TMM error  : "
        f"{maximum_meep_tmm_error:.6e}"
    )
    print(f"CSV                 : {OUTPUT_CSV_PATH}")
    print(f"JSON                : {OUTPUT_JSON_PATH}")
    print(f"Figure              : {OUTPUT_FIGURE_PATH}")


if __name__ == "__main__":
    main()