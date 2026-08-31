"""Screen practical carrier/interface stacks for the SolarFlow retrofit skin.

This script extends the validated simplified optical stack into a first
physical-product screen.  It compares:

    baseline:       air -> existing AR -> glass
    active-only:    air -> retrofit coating -> existing AR -> glass
    physical stack: air -> retrofit coating -> carrier -> interface
                    -> existing AR -> glass

The calculation is a normal-incidence, lossless, nondispersive transfer-matrix
screen over 300--1200 nm, weighted by the Solcore AM1.5G power spectrum.  Thick
carrier/interface layers are phase-averaged so that the ranking is not driven
by unrealistic coherent Fabry-Perot fringes from one exact micrometre-scale
thickness.

It is an engineering screen, not a material claim, electrical-power result,
annual-yield estimate, durability test or module-warranty assessment.
"""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import TwoSlopeNorm


# Validated simplified-stack inputs.
AIR_REFRACTIVE_INDEX = 1.0
GLASS_REFRACTIVE_INDEX = 1.52
EXISTING_AR_REFRACTIVE_INDEX = 1.28
EXISTING_AR_THICKNESS_NM = 100.0
RETROFIT_REFRACTIVE_INDEX = 1.100474
RETROFIT_THICKNESS_NM = 118.791

# Exploratory physical-product grid.  These are generic optical properties,
# not assignments to specific commercial carrier materials.
CARRIER_REFRACTIVE_INDICES = (1.35, 1.40, 1.50, 1.60)
CARRIER_THICKNESSES_UM = (25.0, 50.0, 100.0, 200.0)

WAVELENGTH_MIN_NM = 300.0
WAVELENGTH_MAX_NM = 1200.0
WAVELENGTH_STEP_NM = 1.0
PHASE_REFERENCE_WAVELENGTH_NM = 750.0
DEFAULT_PHASE_SAMPLES = 11

REPO_ROOT = Path(__file__).resolve().parents[2]
RESULTS_DIR = REPO_ROOT / "product1" / "results"
FIGURES_DIR = RESULTS_DIR / "figures"


@dataclass(frozen=True)
class InterfaceCase:
    name: str
    refractive_index: float | None
    thickness_um: float
    description: str


INTERFACE_CASES = (
    InterfaceCase(
        name="optical_contact",
        refractive_index=None,
        thickness_um=0.0,
        description="Carrier directly coupled to the existing AR surface; no explicit gap layer.",
    ),
    InterfaceCase(
        name="air_gap_10um",
        refractive_index=1.0,
        thickness_um=10.0,
        description="Controlled nominal 10 um air gap between carrier and module surface.",
    ),
    InterfaceCase(
        name="reversible_coupling_n1p40_25um",
        refractive_index=1.40,
        thickness_um=25.0,
        description="Generic reversible optical-coupling layer; not a selected adhesive or gel.",
    ),
)


@dataclass(frozen=True)
class ScreenResult:
    interface_mode: str
    carrier_refractive_index: float
    carrier_thickness_um: float
    interface_refractive_index: float | None
    interface_thickness_um: float
    transmitted_power_w_m2: float
    weighted_transmittance_percent: float
    additional_power_vs_baseline_w_m2: float
    absolute_gain_vs_baseline_percentage_points: float
    relative_gain_vs_baseline_percent: float
    gain_retention_vs_active_only_percent: float
    maximum_energy_residual: float


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="AM1.5G-weighted carrier/interface TMM screen for SolarFlow."
    )
    parser.add_argument(
        "--phase-samples",
        type=int,
        default=DEFAULT_PHASE_SAMPLES,
        help=(
            "Number of deterministic phase samples per thick layer "
            f"(default: {DEFAULT_PHASE_SAMPLES})."
        ),
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run optical-kernel checks without importing Solcore.",
    )
    return parser.parse_args()


def wavelengths_nm() -> np.ndarray:
    return np.arange(
        WAVELENGTH_MIN_NM,
        WAVELENGTH_MAX_NM + 0.5 * WAVELENGTH_STEP_NM,
        WAVELENGTH_STEP_NM,
        dtype=float,
    )


def multiply_layer(
    a: np.ndarray,
    b: np.ndarray,
    c: np.ndarray,
    d: np.ndarray,
    refractive_index: float,
    thickness_nm: float,
    wavelength_nm: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Right-multiply a vectorized characteristic matrix by one layer."""
    phase = 2.0 * np.pi * refractive_index * thickness_nm / wavelength_nm
    cosine = np.cos(phase)
    sine = np.sin(phase)

    layer_a = cosine
    layer_b = 1j * sine / refractive_index
    layer_c = 1j * refractive_index * sine
    layer_d = cosine

    return (
        a * layer_a + b * layer_c,
        a * layer_b + b * layer_d,
        c * layer_a + d * layer_c,
        c * layer_b + d * layer_d,
    )


def optical_response(
    layers: Iterable[tuple[float, float]],
    wavelength_nm: np.ndarray,
    incident_index: float = AIR_REFRACTIVE_INDEX,
    substrate_index: float = GLASS_REFRACTIVE_INDEX,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return vectorized (R, T, |1-R-T|) at normal incidence."""
    ones = np.ones_like(wavelength_nm, dtype=complex)
    zeros = np.zeros_like(wavelength_nm, dtype=complex)
    a, b, c, d = ones, zeros, zeros, ones

    for refractive_index, thickness_nm in layers:
        if refractive_index <= 0.0:
            raise ValueError("Every refractive index must be positive.")
        if thickness_nm < 0.0:
            raise ValueError("Every layer thickness must be non-negative.")
        a, b, c, d = multiply_layer(
            a,
            b,
            c,
            d,
            refractive_index,
            thickness_nm,
            wavelength_nm,
        )

    denominator = incident_index * (a + b * substrate_index) + (
        c + d * substrate_index
    )
    reflection_amplitude = (
        incident_index * (a + b * substrate_index) - (c + d * substrate_index)
    ) / denominator
    transmission_amplitude = 2.0 * incident_index / denominator

    reflectance = np.abs(reflection_amplitude) ** 2
    transmittance = (
        substrate_index / incident_index
    ) * np.abs(transmission_amplitude) ** 2
    residual = np.abs(1.0 - reflectance - transmittance)
    return reflectance.real, transmittance.real, residual.real


def phase_offsets_nm(refractive_index: float, sample_count: int) -> np.ndarray:
    """Return deterministic thickness offsets spanning one phase cycle."""
    if sample_count < 1:
        raise ValueError("phase sample count must be at least 1")
    if sample_count == 1:
        return np.array([0.0])

    optical_period_nm = PHASE_REFERENCE_WAVELENGTH_NM / refractive_index
    centered_fraction = (
        np.arange(sample_count, dtype=float) + 0.5
    ) / sample_count - 0.5
    return centered_fraction * optical_period_nm


def physical_stack_response(
    wavelength_nm: np.ndarray,
    carrier_index: float,
    carrier_thickness_um: float,
    interface: InterfaceCase,
    phase_samples: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Phase-average a complete retrofit/carrier/interface stack."""
    carrier_nominal_nm = carrier_thickness_um * 1000.0
    carrier_offsets = phase_offsets_nm(carrier_index, phase_samples)

    if interface.refractive_index is None:
        interface_offsets = np.array([0.0])
    else:
        interface_offsets = phase_offsets_nm(
            interface.refractive_index,
            phase_samples,
        )

    reflectance_sum = np.zeros_like(wavelength_nm, dtype=float)
    transmittance_sum = np.zeros_like(wavelength_nm, dtype=float)
    residual_max = np.zeros_like(wavelength_nm, dtype=float)
    number_of_realizations = 0

    for carrier_offset_nm in carrier_offsets:
        carrier_thickness_nm = carrier_nominal_nm + carrier_offset_nm
        if carrier_thickness_nm <= 0.0:
            raise ValueError("Phase offset produced a non-positive carrier thickness.")

        for interface_offset_nm in interface_offsets:
            layers = [
                (RETROFIT_REFRACTIVE_INDEX, RETROFIT_THICKNESS_NM),
                (carrier_index, carrier_thickness_nm),
            ]

            if interface.refractive_index is not None:
                interface_thickness_nm = (
                    interface.thickness_um * 1000.0 + interface_offset_nm
                )
                if interface_thickness_nm <= 0.0:
                    raise ValueError(
                        "Phase offset produced a non-positive interface thickness."
                    )
                layers.append(
                    (interface.refractive_index, interface_thickness_nm)
                )

            layers.append(
                (EXISTING_AR_REFRACTIVE_INDEX, EXISTING_AR_THICKNESS_NM)
            )

            reflectance, transmittance, residual = optical_response(
                layers,
                wavelength_nm,
            )
            reflectance_sum += reflectance
            transmittance_sum += transmittance
            residual_max = np.maximum(residual_max, residual)
            number_of_realizations += 1

    return (
        reflectance_sum / number_of_realizations,
        transmittance_sum / number_of_realizations,
        residual_max,
    )


def _extract_spectrum_output(
    spectrum_output: object,
    requested_wavelength_nm: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Normalize common Solcore LightSource.spectrum return forms."""
    if isinstance(spectrum_output, (tuple, list)) and len(spectrum_output) >= 2:
        returned_x = np.asarray(spectrum_output[0], dtype=float).squeeze()
        returned_y = np.asarray(spectrum_output[1], dtype=float).squeeze()
    else:
        array = np.asarray(spectrum_output, dtype=float)
        if array.ndim == 2 and array.shape[0] >= 2:
            returned_x = array[0].squeeze()
            returned_y = array[1].squeeze()
        else:
            returned_x = requested_wavelength_nm
            returned_y = array.squeeze()

    if returned_y.shape != requested_wavelength_nm.shape:
        if returned_x.shape != returned_y.shape:
            raise RuntimeError(
                "Could not interpret the wavelength and irradiance arrays returned by Solcore."
            )
        returned_y = np.interp(requested_wavelength_nm, returned_x, returned_y)
        returned_x = requested_wavelength_nm

    return returned_x, returned_y


def load_am15g_power_density(wavelength_nm: np.ndarray) -> np.ndarray:
    """Load AM1.5G spectral irradiance in W m^-2 nm^-1 from Solcore."""
    try:
        from solcore.light_source import LightSource
    except ImportError as error:
        raise RuntimeError(
            "Solcore is required for the AM1.5G run. Activate the solarflow-full "
            "environment, then rerun this script."
        ) from error

    source = LightSource(
        source_type="standard",
        version="AM1.5g",
        x=wavelength_nm,
        output_units="power_density_per_nm",
        concentration=1,
    )

    try:
        spectrum_output = source.spectrum(wavelength_nm)
    except TypeError:
        spectrum_output = source.spectrum()

    returned_x, power_density = _extract_spectrum_output(
        spectrum_output,
        wavelength_nm,
    )
    if not np.allclose(returned_x, wavelength_nm):
        power_density = np.interp(wavelength_nm, returned_x, power_density)

    if not np.all(np.isfinite(power_density)) or np.any(power_density < 0.0):
        raise RuntimeError("Solcore returned an invalid AM1.5G power-density array.")

    incident_power = integrate(power_density, wavelength_nm)
    if not 700.0 <= incident_power <= 1000.0:
        raise RuntimeError(
            "Unexpected integrated AM1.5G power over 300-1200 nm: "
            f"{incident_power:.3f} W/m^2. Check wavelength and output units."
        )

    return power_density


def integrate(y: np.ndarray, x: np.ndarray) -> float:
    """Numerically integrate with NumPy 1.x/2.x compatibility."""
    if hasattr(np, "trapezoid"):
        return float(np.trapezoid(y, x))
    return float(np.trapz(y, x))


def solar_weighted_power(
    transmittance: np.ndarray,
    power_density_w_m2_nm: np.ndarray,
    wavelength_nm: np.ndarray,
) -> float:
    return integrate(
        power_density_w_m2_nm * transmittance,
        wavelength_nm,
    )


def calculate_screen(
    wavelength_nm: np.ndarray,
    power_density_w_m2_nm: np.ndarray,
    phase_samples: int,
) -> tuple[
    list[ScreenResult],
    dict[str, float],
    dict[str, np.ndarray],
    dict[tuple[str, float, float], np.ndarray],
]:
    incident_power = integrate(power_density_w_m2_nm, wavelength_nm)

    baseline_r, baseline_t, baseline_residual = optical_response(
        [(EXISTING_AR_REFRACTIVE_INDEX, EXISTING_AR_THICKNESS_NM)],
        wavelength_nm,
    )
    active_r, active_t, active_residual = optical_response(
        [
            (RETROFIT_REFRACTIVE_INDEX, RETROFIT_THICKNESS_NM),
            (EXISTING_AR_REFRACTIVE_INDEX, EXISTING_AR_THICKNESS_NM),
        ],
        wavelength_nm,
    )

    baseline_power = solar_weighted_power(
        baseline_t,
        power_density_w_m2_nm,
        wavelength_nm,
    )
    active_power = solar_weighted_power(
        active_t,
        power_density_w_m2_nm,
        wavelength_nm,
    )
    active_additional_power = active_power - baseline_power

    reference = {
        "incident_power_w_m2": incident_power,
        "baseline_power_w_m2": baseline_power,
        "baseline_weighted_transmittance_percent": 100.0
        * baseline_power
        / incident_power,
        "active_only_power_w_m2": active_power,
        "active_only_additional_power_w_m2": active_additional_power,
        "active_only_absolute_gain_percentage_points": 100.0
        * active_additional_power
        / incident_power,
        "active_only_relative_gain_percent": 100.0
        * active_additional_power
        / baseline_power,
        "baseline_maximum_energy_residual": float(np.max(baseline_residual)),
        "active_only_maximum_energy_residual": float(np.max(active_residual)),
    }
    reference_spectra = {
        "baseline_reflectance": baseline_r,
        "baseline_transmittance": baseline_t,
        "active_only_reflectance": active_r,
        "active_only_transmittance": active_t,
    }

    results: list[ScreenResult] = []
    candidate_transmittance: dict[tuple[str, float, float], np.ndarray] = {}

    for interface in INTERFACE_CASES:
        for carrier_index in CARRIER_REFRACTIVE_INDICES:
            for carrier_thickness_um in CARRIER_THICKNESSES_UM:
                _, transmittance, residual = physical_stack_response(
                    wavelength_nm=wavelength_nm,
                    carrier_index=carrier_index,
                    carrier_thickness_um=carrier_thickness_um,
                    interface=interface,
                    phase_samples=phase_samples,
                )
                transmitted_power = solar_weighted_power(
                    transmittance,
                    power_density_w_m2_nm,
                    wavelength_nm,
                )
                additional_power = transmitted_power - baseline_power
                if active_additional_power > 0.0:
                    gain_retention = 100.0 * additional_power / active_additional_power
                else:
                    gain_retention = float("nan")

                result = ScreenResult(
                    interface_mode=interface.name,
                    carrier_refractive_index=carrier_index,
                    carrier_thickness_um=carrier_thickness_um,
                    interface_refractive_index=interface.refractive_index,
                    interface_thickness_um=interface.thickness_um,
                    transmitted_power_w_m2=transmitted_power,
                    weighted_transmittance_percent=100.0
                    * transmitted_power
                    / incident_power,
                    additional_power_vs_baseline_w_m2=additional_power,
                    absolute_gain_vs_baseline_percentage_points=100.0
                    * additional_power
                    / incident_power,
                    relative_gain_vs_baseline_percent=100.0
                    * additional_power
                    / baseline_power,
                    gain_retention_vs_active_only_percent=gain_retention,
                    maximum_energy_residual=float(np.max(residual)),
                )
                results.append(result)
                candidate_transmittance[
                    (interface.name, carrier_index, carrier_thickness_um)
                ] = transmittance

    return results, reference, reference_spectra, candidate_transmittance


def write_csv(results: list[ScreenResult]) -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    path = RESULTS_DIR / "carrier_interface_screen.csv"
    fieldnames = list(asdict(results[0]).keys())
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(asdict(result) for result in results)
    return path


def result_grid(
    results: list[ScreenResult],
    interface_name: str,
) -> np.ndarray:
    matrix = np.empty(
        (len(CARRIER_REFRACTIVE_INDICES), len(CARRIER_THICKNESSES_UM)),
        dtype=float,
    )
    for result in results:
        if result.interface_mode != interface_name:
            continue
        row = CARRIER_REFRACTIVE_INDICES.index(result.carrier_refractive_index)
        column = CARRIER_THICKNESSES_UM.index(result.carrier_thickness_um)
        matrix[row, column] = result.relative_gain_vs_baseline_percent
    return matrix


def write_heatmap(results: list[ScreenResult]) -> Path:
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    path = FIGURES_DIR / "carrier_interface_screen_heatmap.png"

    matrices = [result_grid(results, item.name) for item in INTERFACE_CASES]
    limit = max(float(np.max(np.abs(matrix))) for matrix in matrices)
    if limit == 0.0:
        limit = 1.0
    norm = TwoSlopeNorm(vmin=-limit, vcenter=0.0, vmax=limit)

    figure, axes = plt.subplots(1, len(INTERFACE_CASES), figsize=(14.4, 4.8))
    figure.subplots_adjust(left=0.07, right=0.91, bottom=0.22, top=0.82, wspace=0.25)

    image = None
    for axis, interface, matrix in zip(axes, INTERFACE_CASES, matrices):
        image = axis.imshow(
            matrix,
            cmap="RdYlGn",
            norm=norm,
            aspect="auto",
        )
        axis.set_title(interface.name.replace("_", "\n"), fontsize=10)
        axis.set_xlabel("Carrier thickness (µm)")
        axis.set_xticks(
            range(len(CARRIER_THICKNESSES_UM)),
            [f"{value:.0f}" for value in CARRIER_THICKNESSES_UM],
        )
        axis.set_yticks(
            range(len(CARRIER_REFRACTIVE_INDICES)),
            [f"{value:.2f}" for value in CARRIER_REFRACTIVE_INDICES],
        )

        for row in range(matrix.shape[0]):
            for column in range(matrix.shape[1]):
                axis.text(
                    column,
                    row,
                    f"{matrix[row, column]:+.3f}%",
                    ha="center",
                    va="center",
                    fontsize=7.5,
                )

    axes[0].set_ylabel("Generic carrier refractive index")
    figure.suptitle(
        "SolarFlow Carrier / Interface Screen — Relative Optical Gain vs Baseline",
        fontsize=14,
    )
    if image is not None:
        colorbar = figure.colorbar(image, ax=axes, fraction=0.025, pad=0.035)
        colorbar.set_label("AM1.5G-weighted relative gain (%)")
    figure.text(
        0.5,
        0.055,
        "Normal incidence, lossless nondispersive indices, 300–1200 nm; thick layers phase-averaged.",
        ha="center",
        fontsize=8,
    )
    figure.savefig(path, dpi=220)
    plt.close(figure)
    return path


def write_spectra_figure(
    results: list[ScreenResult],
    reference_spectra: dict[str, np.ndarray],
    candidate_transmittance: dict[tuple[str, float, float], np.ndarray],
    wavelength_nm: np.ndarray,
) -> Path:
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    path = FIGURES_DIR / "carrier_interface_best_spectra.png"
    best = max(results, key=lambda item: item.relative_gain_vs_baseline_percent)
    best_key = (
        best.interface_mode,
        best.carrier_refractive_index,
        best.carrier_thickness_um,
    )

    figure, axis = plt.subplots(figsize=(8.4, 4.9))
    axis.plot(
        wavelength_nm,
        100.0 * reference_spectra["baseline_transmittance"],
        label="Baseline: existing AR",
        linewidth=1.8,
    )
    axis.plot(
        wavelength_nm,
        100.0 * reference_spectra["active_only_transmittance"],
        label="Active-only ideal stack",
        linewidth=1.8,
    )
    axis.plot(
        wavelength_nm,
        100.0 * candidate_transmittance[best_key],
        label=(
            f"Best physical screen: {best.interface_mode}, "
            f"n={best.carrier_refractive_index:.2f}, "
            f"{best.carrier_thickness_um:.0f} µm"
        ),
        linewidth=1.8,
    )
    axis.set_title("SolarFlow Screening Spectra")
    axis.set_xlabel("Wavelength (nm)")
    axis.set_ylabel("Transmittance (%)")
    axis.grid(alpha=0.25)
    axis.legend(fontsize=8)
    figure.tight_layout()
    figure.savefig(path, dpi=220)
    plt.close(figure)
    return path


def write_summary(
    results: list[ScreenResult],
    reference: dict[str, float],
    phase_samples: int,
) -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    path = RESULTS_DIR / "carrier_interface_screen_summary.json"
    ranked = sorted(
        results,
        key=lambda item: item.relative_gain_vs_baseline_percent,
        reverse=True,
    )
    positive = [
        item for item in ranked if item.relative_gain_vs_baseline_percent > 0.0
    ]
    if positive:
        recommended_next_action = (
            "Shortlist positive physical-stack cases, then re-optimize the retrofit "
            "index/thickness around each complete stack before angle screening."
        )
    else:
        recommended_next_action = (
            "The current n=1.100474, 118.791 nm coating does not survive the added "
            "carrier/interface assumptions. Re-optimize the coating for the complete "
            "physical stack before rejecting the removable-skin concept."
        )
    best_by_interface = {
        interface.name: asdict(
            max(
                (
                    item
                    for item in results
                    if item.interface_mode == interface.name
                ),
                key=lambda item: item.relative_gain_vs_baseline_percent,
            )
        )
        for interface in INTERFACE_CASES
    }

    payload = {
        "model": "Normal-incidence lossless nondispersive transfer-matrix screen",
        "purpose": "Test whether a practical carrier/interface can retain positive broadband optical gain.",
        "status": "Engineering screen only; not a selected material or electrical-power claim.",
        "baseline_stack": "air -> existing AR -> cover glass",
        "active_only_stack": "air -> retrofit coating -> existing AR -> cover glass",
        "physical_stack": "air -> retrofit coating -> carrier -> interface -> existing AR -> cover glass",
        "wavelength_range_nm": [WAVELENGTH_MIN_NM, WAVELENGTH_MAX_NM],
        "wavelength_step_nm": WAVELENGTH_STEP_NM,
        "solar_spectrum": "Solcore standard AM1.5G power density",
        "phase_averaging": {
            "enabled": True,
            "samples_per_thick_layer": phase_samples,
            "reference_wavelength_nm": PHASE_REFERENCE_WAVELENGTH_NM,
            "reason": "Suppress exact-thickness coherent fringes in micrometre-scale layers.",
        },
        "fixed_indices_and_thicknesses": {
            "air_refractive_index": AIR_REFRACTIVE_INDEX,
            "glass_refractive_index": GLASS_REFRACTIVE_INDEX,
            "existing_ar_refractive_index": EXISTING_AR_REFRACTIVE_INDEX,
            "existing_ar_thickness_nm": EXISTING_AR_THICKNESS_NM,
            "retrofit_refractive_index": RETROFIT_REFRACTIVE_INDEX,
            "retrofit_thickness_nm": RETROFIT_THICKNESS_NM,
        },
        "carrier_grid": {
            "refractive_indices": CARRIER_REFRACTIVE_INDICES,
            "thicknesses_um": CARRIER_THICKNESSES_UM,
            "note": "Generic lossless nondispersive carriers; no commercial material assignment.",
        },
        "interface_cases": [asdict(item) for item in INTERFACE_CASES],
        "reference_results": reference,
        "number_of_candidates": len(results),
        "number_of_positive_gain_candidates": len(positive),
        "recommended_next_action": recommended_next_action,
        "best_candidate": asdict(ranked[0]),
        "worst_candidate": asdict(ranked[-1]),
        "best_candidate_by_interface": best_by_interface,
        "top_five_candidates": [asdict(item) for item in ranked[:5]],
        "screening_flags": {
            "any_positive_candidate": bool(positive),
            "all_energy_residuals_below_1e-10": all(
                item.maximum_energy_residual < 1e-10 for item in results
            ),
            "active_only_result_in_expected_neighborhood": (
                0.5 <= reference["active_only_relative_gain_percent"] <= 0.9
            ),
        },
        "limitations": [
            "Normal incidence only; angle and polarization are not included.",
            "All layers are lossless and nondispersive.",
            "Carrier haze, absorption, UV aging, water, dirt and roughness are not included.",
            "The existing JA Solar coating is still an assumed n=1.28, 100 nm layer.",
            "Optical gain is not electrical module-power or annual-energy gain.",
        ],
    }

    with path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2, allow_nan=False)
        file.write("\n")
    return path


def print_results(
    results: list[ScreenResult],
    reference: dict[str, float],
    outputs: Iterable[Path],
) -> None:
    ranked = sorted(
        results,
        key=lambda item: item.relative_gain_vs_baseline_percent,
        reverse=True,
    )
    positive_count = sum(
        item.relative_gain_vs_baseline_percent > 0.0 for item in results
    )

    print("Carrier/interface AM1.5G TMM screen completed.")
    print(f"Incident power in band : {reference['incident_power_w_m2']:.3f} W/m²")
    print(f"Baseline power         : {reference['baseline_power_w_m2']:.3f} W/m²")
    print(f"Active-only power      : {reference['active_only_power_w_m2']:.3f} W/m²")
    print(
        "Active-only gain       : "
        f"{reference['active_only_relative_gain_percent']:+.4f}%"
    )
    print(
        f"Positive candidates    : {positive_count}/{len(results)}\n"
    )
    print("Top 10 physical-stack candidates")
    print(
        "rank  interface                         n_carrier  d_carrier  "
        "gain vs baseline  ideal retained"
    )
    for rank, result in enumerate(ranked[:10], start=1):
        print(
            f"{rank:>4}  {result.interface_mode:<32} "
            f"{result.carrier_refractive_index:>9.2f}  "
            f"{result.carrier_thickness_um:>7.0f} µm  "
            f"{result.relative_gain_vs_baseline_percent:>+14.4f}%  "
            f"{result.gain_retention_vs_active_only_percent:>+12.2f}%"
        )

    best = ranked[0]
    print("\nBest candidate")
    print(f"Interface              : {best.interface_mode}")
    print(f"Carrier index          : {best.carrier_refractive_index:.2f}")
    print(f"Carrier thickness      : {best.carrier_thickness_um:.0f} µm")
    print(f"Transmitted power      : {best.transmitted_power_w_m2:.3f} W/m²")
    print(
        "Additional power       : "
        f"{best.additional_power_vs_baseline_w_m2:+.3f} W/m²"
    )
    print(
        "Relative optical gain  : "
        f"{best.relative_gain_vs_baseline_percent:+.4f}%"
    )
    print(
        "Ideal gain retained    : "
        f"{best.gain_retention_vs_active_only_percent:+.2f}%"
    )

    if positive_count:
        print(
            "Decision               : Shortlist positive cases and re-optimize "
            "the coating for each complete stack."
        )
    else:
        print(
            "Decision               : The current coating does not survive the "
            "added physical layers. Re-optimize n/thickness for the complete "
            "stack before rejecting the concept."
        )

    print("\nOutputs")
    for output in outputs:
        print(f"- {output}")
    print(
        "\nWARNING: Screening assumptions only; do not report these values as "
        "electrical module power or a selected commercial material."
    )


def run_self_test() -> None:
    test_wavelengths = np.array([300.0, 550.0, 1200.0])

    # Empty-stack Fresnel response: air -> glass.
    reflectance, transmittance, residual = optical_response([], test_wavelengths)
    expected_r = (
        (AIR_REFRACTIVE_INDEX - GLASS_REFRACTIVE_INDEX)
        / (AIR_REFRACTIVE_INDEX + GLASS_REFRACTIVE_INDEX)
    ) ** 2
    if not np.allclose(reflectance, expected_r, atol=1e-13):
        raise AssertionError("Empty-stack Fresnel reflectance check failed.")
    if not np.allclose(transmittance, 1.0 - expected_r, atol=1e-13):
        raise AssertionError("Empty-stack Fresnel transmittance check failed.")
    if float(np.max(residual)) >= 1e-12:
        raise AssertionError("Empty-stack energy-conservation check failed.")

    # Regression check against the approved 550 nm sensitivity model.
    _, baseline_t, _ = optical_response(
        [(EXISTING_AR_REFRACTIVE_INDEX, EXISTING_AR_THICKNESS_NM)],
        np.array([550.0]),
    )
    _, active_t, active_residual = optical_response(
        [
            (RETROFIT_REFRACTIVE_INDEX, RETROFIT_THICKNESS_NM),
            (EXISTING_AR_REFRACTIVE_INDEX, EXISTING_AR_THICKNESS_NM),
        ],
        np.array([550.0]),
    )
    relative_change = 100.0 * (active_t[0] / baseline_t[0] - 1.0)
    if not np.isclose(relative_change, -0.1306, atol=5e-5):
        raise AssertionError(
            "550 nm regression check failed: "
            f"calculated {relative_change:+.6f}% instead of -0.1306%."
        )
    if float(np.max(active_residual)) >= 1e-12:
        raise AssertionError("Coated-stack energy-conservation check failed.")

    print("Self-test passed: Fresnel, 550 nm regression and energy conservation.")


def main() -> None:
    arguments = parse_arguments()
    if arguments.self_test:
        run_self_test()
        return

    if arguments.phase_samples < 1:
        raise SystemExit("--phase-samples must be at least 1")

    wavelength_nm = wavelengths_nm()
    power_density_w_m2_nm = load_am15g_power_density(wavelength_nm)
    results, reference, reference_spectra, candidate_transmittance = calculate_screen(
        wavelength_nm=wavelength_nm,
        power_density_w_m2_nm=power_density_w_m2_nm,
        phase_samples=arguments.phase_samples,
    )

    csv_path = write_csv(results)
    summary_path = write_summary(results, reference, arguments.phase_samples)
    heatmap_path = write_heatmap(results)
    spectra_path = write_spectra_figure(
        results,
        reference_spectra,
        candidate_transmittance,
        wavelength_nm,
    )
    print_results(
        results,
        reference,
        (csv_path, summary_path, heatmap_path, spectra_path),
    )


if __name__ == "__main__":
    main()
