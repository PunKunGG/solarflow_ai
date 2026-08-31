"""Angle and polarization screen for the locked SolarFlow optical stack.

The nominal stack is loaded from the passed combined-tolerance result:

    air -> active coating -> release primer -> existing AR -> cover glass

AM1.5G-weighted optical transmission is evaluated at 0, 15, 30, 45 and
60 degrees for TE, TM and their unpolarized average.  The oblique-incidence
transfer matrix applies Snell's law and polarization-dependent optical
admittance.  Projected power includes cos(theta), while relative gain compares
the retrofit and baseline at the same angle, so the projection cancels.

The model is lossless, nondispersive and optical only.  It is not an annual
solar-angle distribution, electrical-power result or field measurement.
"""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from product1.analysis import carrier_interface_screen as screen


INCIDENCE_ANGLES_DEG = (0.0, 15.0, 30.0, 45.0, 60.0)
POLARIZATIONS = ("TE", "TM", "unpolarized")
PROVISIONAL_MARGIN_PERCENT = 0.10

REPO_ROOT = Path(__file__).resolve().parents[2]
RESULTS_DIR = REPO_ROOT / "product1" / "results"
FIGURES_DIR = RESULTS_DIR / "figures"
SOURCE_SUMMARY_PATH = RESULTS_DIR / "combined_active_primer_tolerance_summary.json"


@dataclass(frozen=True)
class AngleResult:
    incidence_angle_deg: float
    polarization: str
    projected_incident_power_w_m2: float
    baseline_transmitted_power_w_m2: float
    retrofit_transmitted_power_w_m2: float
    baseline_weighted_transmittance_percent: float
    retrofit_weighted_transmittance_percent: float
    additional_transmitted_power_w_m2: float
    absolute_gain_percentage_points: float
    relative_gain_percent: float
    passes_positive_gain_gate: bool
    passes_provisional_margin_gate: bool
    baseline_maximum_energy_residual: float
    retrofit_maximum_energy_residual: float


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="SolarFlow angle and TE/TM polarization screen."
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run normal-incidence and Fresnel regression checks without Solcore.",
    )
    return parser.parse_args()


def load_locked_stack() -> dict[str, float]:
    if not SOURCE_SUMMARY_PATH.exists():
        raise FileNotFoundError(
            "Missing combined_active_primer_tolerance_summary.json. Run the "
            "combined tolerance screen first."
        )
    with SOURCE_SUMMARY_PATH.open("r", encoding="utf-8") as file:
        payload = json.load(file)
    if not payload.get("all_cases_pass_provisional_margin", False):
        raise RuntimeError(
            "The source tolerance box did not pass; the optical stack is not locked."
        )
    nominal = payload["nominal_stack"]
    return {
        "active_refractive_index": float(nominal["active_refractive_index"]),
        "active_thickness_nm": float(nominal["active_thickness_nm"]),
        "primer_refractive_index": float(nominal["primer_refractive_index"]),
        "primer_thickness_nm": float(nominal["primer_thickness_nm"]),
    }


def cosine_in_medium(
    incident_index: float,
    medium_index: float,
    incident_angle_rad: float,
) -> complex:
    """Return cos(theta_j) from Snell's law using a stable complex root."""
    sine = incident_index * np.sin(incident_angle_rad) / medium_index
    cosine = np.sqrt(1.0 - complex(sine) ** 2)
    if cosine.real < 0.0:
        cosine = -cosine
    return cosine


def optical_admittance(
    refractive_index: float,
    cosine_angle: complex,
    polarization: str,
) -> complex:
    if polarization == "TE":
        return refractive_index * cosine_angle
    if polarization == "TM":
        return refractive_index / cosine_angle
    raise ValueError("Polarization must be 'TE' or 'TM'.")


def oblique_optical_response(
    layers: list[tuple[float, float]],
    wavelength_nm: np.ndarray,
    incidence_angle_deg: float,
    polarization: str,
    incident_index: float = screen.AIR_REFRACTIVE_INDEX,
    substrate_index: float = screen.GLASS_REFRACTIVE_INDEX,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return vectorized R, T and |1-R-T| for an oblique lossless stack."""
    if polarization not in ("TE", "TM"):
        raise ValueError("Polarization must be 'TE' or 'TM'.")
    if not 0.0 <= incidence_angle_deg < 90.0:
        raise ValueError("Incidence angle must be in [0, 90) degrees.")

    incident_angle_rad = np.deg2rad(incidence_angle_deg)
    incident_cosine = complex(np.cos(incident_angle_rad))
    substrate_cosine = cosine_in_medium(
        incident_index,
        substrate_index,
        incident_angle_rad,
    )
    incident_admittance = optical_admittance(
        incident_index,
        incident_cosine,
        polarization,
    )
    substrate_admittance = optical_admittance(
        substrate_index,
        substrate_cosine,
        polarization,
    )

    ones = np.ones_like(wavelength_nm, dtype=complex)
    zeros = np.zeros_like(wavelength_nm, dtype=complex)
    a, b, c, d = ones, zeros, zeros, ones

    for refractive_index, thickness_nm in layers:
        layer_cosine = cosine_in_medium(
            incident_index,
            refractive_index,
            incident_angle_rad,
        )
        layer_admittance = optical_admittance(
            refractive_index,
            layer_cosine,
            polarization,
        )
        phase = (
            2.0
            * np.pi
            * refractive_index
            * thickness_nm
            * layer_cosine
            / wavelength_nm
        )
        cosine_phase = np.cos(phase)
        sine_phase = np.sin(phase)
        layer_a = cosine_phase
        layer_b = 1j * sine_phase / layer_admittance
        layer_c = 1j * layer_admittance * sine_phase
        layer_d = cosine_phase

        a, b, c, d = (
            a * layer_a + b * layer_c,
            a * layer_b + b * layer_d,
            c * layer_a + d * layer_c,
            c * layer_b + d * layer_d,
        )

    denominator = incident_admittance * (a + b * substrate_admittance) + (
        c + d * substrate_admittance
    )
    reflection_amplitude = (
        incident_admittance * (a + b * substrate_admittance)
        - (c + d * substrate_admittance)
    ) / denominator
    transmission_amplitude = 2.0 * incident_admittance / denominator

    reflectance = np.abs(reflection_amplitude) ** 2
    transmittance = (
        np.real(substrate_admittance / incident_admittance)
        * np.abs(transmission_amplitude) ** 2
    )
    residual = np.abs(1.0 - reflectance - transmittance)
    return reflectance.real, transmittance.real, residual.real


def baseline_layers() -> list[tuple[float, float]]:
    return [
        (
            screen.EXISTING_AR_REFRACTIVE_INDEX,
            screen.EXISTING_AR_THICKNESS_NM,
        )
    ]


def retrofit_layers(locked: dict[str, float]) -> list[tuple[float, float]]:
    return [
        (
            locked["active_refractive_index"],
            locked["active_thickness_nm"],
        ),
        (
            locked["primer_refractive_index"],
            locked["primer_thickness_nm"],
        ),
        (
            screen.EXISTING_AR_REFRACTIVE_INDEX,
            screen.EXISTING_AR_THICKNESS_NM,
        ),
    ]


def calculate_results(
    wavelength_nm: np.ndarray,
    power_density_w_m2_nm: np.ndarray,
    locked: dict[str, float],
) -> tuple[
    list[AngleResult],
    dict[tuple[float, str], dict[str, np.ndarray]],
]:
    incident_band_power = screen.integrate(
        power_density_w_m2_nm,
        wavelength_nm,
    )
    results: list[AngleResult] = []
    spectra: dict[tuple[float, str], dict[str, np.ndarray]] = {}

    for angle_deg in INCIDENCE_ANGLES_DEG:
        polarization_spectra: dict[str, dict[str, np.ndarray]] = {}
        for polarization in ("TE", "TM"):
            baseline_r, baseline_t, baseline_residual = oblique_optical_response(
                baseline_layers(),
                wavelength_nm,
                angle_deg,
                polarization,
            )
            retrofit_r, retrofit_t, retrofit_residual = oblique_optical_response(
                retrofit_layers(locked),
                wavelength_nm,
                angle_deg,
                polarization,
            )
            polarization_spectra[polarization] = {
                "baseline_reflectance": baseline_r,
                "baseline_transmittance": baseline_t,
                "baseline_residual": baseline_residual,
                "retrofit_reflectance": retrofit_r,
                "retrofit_transmittance": retrofit_t,
                "retrofit_residual": retrofit_residual,
            }

        polarization_spectra["unpolarized"] = {
            key: 0.5
            * (
                polarization_spectra["TE"][key]
                + polarization_spectra["TM"][key]
            )
            for key in (
                "baseline_reflectance",
                "baseline_transmittance",
                "baseline_residual",
                "retrofit_reflectance",
                "retrofit_transmittance",
                "retrofit_residual",
            )
        }

        projection = float(np.cos(np.deg2rad(angle_deg)))
        projected_incident_power = incident_band_power * projection
        for polarization in POLARIZATIONS:
            current = polarization_spectra[polarization]
            baseline_power = projection * screen.solar_weighted_power(
                current["baseline_transmittance"],
                power_density_w_m2_nm,
                wavelength_nm,
            )
            retrofit_power = projection * screen.solar_weighted_power(
                current["retrofit_transmittance"],
                power_density_w_m2_nm,
                wavelength_nm,
            )
            additional_power = retrofit_power - baseline_power
            relative_gain = 100.0 * additional_power / baseline_power
            results.append(
                AngleResult(
                    incidence_angle_deg=angle_deg,
                    polarization=polarization,
                    projected_incident_power_w_m2=projected_incident_power,
                    baseline_transmitted_power_w_m2=baseline_power,
                    retrofit_transmitted_power_w_m2=retrofit_power,
                    baseline_weighted_transmittance_percent=100.0
                    * baseline_power
                    / projected_incident_power,
                    retrofit_weighted_transmittance_percent=100.0
                    * retrofit_power
                    / projected_incident_power,
                    additional_transmitted_power_w_m2=additional_power,
                    absolute_gain_percentage_points=100.0
                    * additional_power
                    / projected_incident_power,
                    relative_gain_percent=relative_gain,
                    passes_positive_gain_gate=relative_gain > 0.0,
                    passes_provisional_margin_gate=(
                        relative_gain >= PROVISIONAL_MARGIN_PERCENT
                    ),
                    baseline_maximum_energy_residual=float(
                        np.max(current["baseline_residual"])
                    ),
                    retrofit_maximum_energy_residual=float(
                        np.max(current["retrofit_residual"])
                    ),
                )
            )
            spectra[(angle_deg, polarization)] = current

    return results, spectra


def write_csv(results: list[AngleResult]) -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    path = RESULTS_DIR / "angle_polarization_screen.csv"
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(asdict(results[0]).keys()))
        writer.writeheader()
        writer.writerows(asdict(item) for item in results)
    return path


def result_for(
    results: list[AngleResult],
    angle_deg: float,
    polarization: str,
) -> AngleResult:
    return next(
        item
        for item in results
        if item.incidence_angle_deg == angle_deg
        and item.polarization == polarization
    )


def validation_flags(results: list[AngleResult]) -> dict[str, object]:
    unpolarized = [
        item for item in results if item.polarization == "unpolarized"
    ]
    normal_te = result_for(results, 0.0, "TE")
    normal_tm = result_for(results, 0.0, "TM")
    return {
        "all_unpolarized_angles_positive": all(
            item.passes_positive_gain_gate for item in unpolarized
        ),
        "all_unpolarized_angles_pass_provisional_margin": all(
            item.passes_provisional_margin_gate for item in unpolarized
        ),
        "all_TE_TM_cases_positive": all(
            item.passes_positive_gain_gate
            for item in results
            if item.polarization in ("TE", "TM")
        ),
        "all_energy_residuals_below_1e_10": all(
            max(
                item.baseline_maximum_energy_residual,
                item.retrofit_maximum_energy_residual,
            )
            < 1e-10
            for item in results
        ),
        "normal_incidence_TE_TM_gain_difference_percent": abs(
            normal_te.relative_gain_percent - normal_tm.relative_gain_percent
        ),
        "normal_incidence_TE_TM_match": abs(
            normal_te.relative_gain_percent - normal_tm.relative_gain_percent
        )
        < 1e-10,
    }


def decision_from_flags(flags: dict[str, object]) -> str:
    if flags["all_unpolarized_angles_pass_provisional_margin"]:
        return (
            "The locked stack retains the provisional margin at every tested angle. "
            "Advance to an angle-distribution/annual-yield interpretation and independent validation."
        )
    if flags["all_unpolarized_angles_positive"]:
        return (
            "The locked stack remains positive at every tested angle, but at least one angle "
            "falls below the provisional margin. Quantify the real angle distribution before advancing."
        )
    return (
        "The locked stack is not angle-robust. Re-optimize using a multi-angle objective before "
        "making a broadband field-performance claim."
    )


def write_summary(
    results: list[AngleResult],
    locked: dict[str, float],
) -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    path = RESULTS_DIR / "angle_polarization_screen_summary.json"
    flags = validation_flags(results)
    unpolarized = [
        item for item in results if item.polarization == "unpolarized"
    ]
    payload = {
        "model": "Oblique-incidence AM1.5G-weighted lossless TMM",
        "status": "Optical angle/polarization screen only",
        "locked_stack": locked,
        "existing_ar": {
            "refractive_index": screen.EXISTING_AR_REFRACTIVE_INDEX,
            "thickness_nm": screen.EXISTING_AR_THICKNESS_NM,
        },
        "glass_refractive_index": screen.GLASS_REFRACTIVE_INDEX,
        "incidence_angles_deg": INCIDENCE_ANGLES_DEG,
        "polarizations": POLARIZATIONS,
        "provisional_margin_percent": PROVISIONAL_MARGIN_PERCENT,
        "projection_note": (
            "Reported powers include cos(theta) projection. Relative retrofit gain compares "
            "stacks at the same angle and is independent of that common projection."
        ),
        "results": [asdict(item) for item in results],
        "minimum_unpolarized_gain_case": asdict(
            min(unpolarized, key=lambda item: item.relative_gain_percent)
        ),
        "maximum_unpolarized_gain_case": asdict(
            max(unpolarized, key=lambda item: item.relative_gain_percent)
        ),
        "validation": flags,
        "decision": decision_from_flags(flags),
        "limitations": [
            "The tested angles are discrete and are not an annual solar-angle distribution.",
            "All refractive indices are generic, lossless and nondispersive.",
            "Surface roughness, haze, water, soiling and diffuse irradiance are excluded.",
            "The existing module AR remains an assumed n=1.28, 100 nm layer.",
            "Optical transmission gain is not electrical module or annual-energy gain.",
        ],
    }
    with path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2, allow_nan=False)
        file.write("\n")
    return path


def write_gain_figure(results: list[AngleResult]) -> Path:
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    path = FIGURES_DIR / "angle_polarization_gain.png"
    styles = {
        "TE": ("#1565c0", "o", "--"),
        "TM": ("#c62828", "s", "--"),
        "unpolarized": ("#2e7d32", "o", "-"),
    }

    figure, axis = plt.subplots(figsize=(8.3, 5.0))
    for polarization in POLARIZATIONS:
        selected = [item for item in results if item.polarization == polarization]
        color, marker, linestyle = styles[polarization]
        axis.plot(
            [item.incidence_angle_deg for item in selected],
            [item.relative_gain_percent for item in selected],
            label=polarization,
            color=color,
            marker=marker,
            linestyle=linestyle,
            linewidth=2.0 if polarization == "unpolarized" else 1.3,
        )
    axis.axhline(0.0, color="black", linewidth=1.0)
    axis.axhline(
        PROVISIONAL_MARGIN_PERCENT,
        color="#ef6c00",
        linewidth=1.2,
        linestyle=":",
        label=f"Provisional margin: +{PROVISIONAL_MARGIN_PERCENT:.2f}%",
    )
    axis.set_title("SolarFlow Angle and Polarization Optical Gain")
    axis.set_xlabel("Incidence angle (degrees)")
    axis.set_ylabel("AM1.5G-weighted relative optical gain (%)")
    axis.set_xticks(INCIDENCE_ANGLES_DEG)
    axis.grid(alpha=0.25)
    axis.legend(fontsize=8)
    figure.tight_layout()
    figure.savefig(path, dpi=220)
    plt.close(figure)
    return path


def write_transmittance_figure(results: list[AngleResult]) -> Path:
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    path = FIGURES_DIR / "angle_unpolarized_transmittance.png"
    selected = [
        item for item in results if item.polarization == "unpolarized"
    ]

    figure, axis = plt.subplots(figsize=(8.3, 4.9))
    angles = [item.incidence_angle_deg for item in selected]
    axis.plot(
        angles,
        [item.baseline_weighted_transmittance_percent for item in selected],
        marker="o",
        label="Baseline existing AR",
        linewidth=1.8,
    )
    axis.plot(
        angles,
        [item.retrofit_weighted_transmittance_percent for item in selected],
        marker="o",
        label="Locked active + primer stack",
        linewidth=1.8,
    )
    axis.set_title("Unpolarized Solar-Weighted Transmittance vs Angle")
    axis.set_xlabel("Incidence angle (degrees)")
    axis.set_ylabel("Weighted transmittance (%)")
    axis.set_xticks(INCIDENCE_ANGLES_DEG)
    axis.grid(alpha=0.25)
    axis.legend(fontsize=8)
    figure.tight_layout()
    figure.savefig(path, dpi=220)
    plt.close(figure)
    return path


def write_spectra_figure(
    spectra: dict[tuple[float, str], dict[str, np.ndarray]],
    wavelength_nm: np.ndarray,
) -> Path:
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    path = FIGURES_DIR / "angle_unpolarized_spectra.png"

    figure, axes = plt.subplots(1, 3, figsize=(13.0, 4.1), sharey=True)
    for axis, angle_deg in zip(axes, (0.0, 30.0, 60.0)):
        current = spectra[(angle_deg, "unpolarized")]
        axis.plot(
            wavelength_nm,
            100.0 * current["baseline_transmittance"],
            label="Baseline",
            linewidth=1.5,
        )
        axis.plot(
            wavelength_nm,
            100.0 * current["retrofit_transmittance"],
            label="Retrofit",
            linewidth=1.5,
        )
        axis.set_title(f"{angle_deg:.0f}Â°")
        axis.set_xlabel("Wavelength (nm)")
        axis.grid(alpha=0.2)
    axes[0].set_ylabel("Unpolarized transmittance (%)")
    axes[-1].legend(fontsize=8)
    figure.suptitle("SolarFlow Unpolarized Spectra at Selected Angles")
    figure.tight_layout()
    figure.savefig(path, dpi=220)
    plt.close(figure)
    return path


def print_results(
    results: list[AngleResult],
    locked: dict[str, float],
    outputs: list[Path],
) -> None:
    flags = validation_flags(results)
    print("Angle and polarization screen completed.")
    print(
        "Locked active coating : "
        f"n={locked['active_refractive_index']:.6f}, "
        f"d={locked['active_thickness_nm']:.3f} nm"
    )
    print(
        "Locked release primer : "
        f"n={locked['primer_refractive_index']:.2f}, "
        f"d={locked['primer_thickness_nm']:.0f} nm\n"
    )
    print("angle     TE gain      TM gain      unpolarized gain    margin gate")
    for angle_deg in INCIDENCE_ANGLES_DEG:
        te = result_for(results, angle_deg, "TE")
        tm = result_for(results, angle_deg, "TM")
        unpolarized = result_for(results, angle_deg, "unpolarized")
        gate = "PASS" if unpolarized.passes_provisional_margin_gate else "FAIL"
        print(
            f"{angle_deg:>4.0f}Â°   "
            f"{te.relative_gain_percent:>+9.4f}%   "
            f"{tm.relative_gain_percent:>+9.4f}%   "
            f"{unpolarized.relative_gain_percent:>+15.4f}%   "
            f"{gate}"
        )

    unpolarized_cases = [
        item for item in results if item.polarization == "unpolarized"
    ]
    minimum = min(unpolarized_cases, key=lambda item: item.relative_gain_percent)
    print(
        "\nMinimum unpolarized gain : "
        f"{minimum.relative_gain_percent:+.4f}% at "
        f"{minimum.incidence_angle_deg:.0f}Â°"
    )
    print(
        "All angles positive       : "
        f"{flags['all_unpolarized_angles_positive']}"
    )
    print(
        "All angles pass +0.10%    : "
        f"{flags['all_unpolarized_angles_pass_provisional_margin']}"
    )
    print(
        "Normal TE/TM match        : "
        f"{flags['normal_incidence_TE_TM_match']}"
    )
    print(
        "Energy conservation passes: "
        f"{flags['all_energy_residuals_below_1e_10']}"
    )
    print("\nDecision")
    print(decision_from_flags(flags))
    print("\nOutputs")
    for output in outputs:
        print(f"- {output}")
    print(
        "\nWARNING: Discrete optical-angle screen; not annual electrical energy yield."
    )


def analytic_bare_interface_reflectance(
    incident_index: float,
    substrate_index: float,
    incidence_angle_deg: float,
    polarization: str,
) -> float:
    angle_rad = np.deg2rad(incidence_angle_deg)
    cos_incident = np.cos(angle_rad)
    cos_substrate = cosine_in_medium(
        incident_index,
        substrate_index,
        angle_rad,
    ).real
    if polarization == "TE":
        amplitude = (
            incident_index * cos_incident - substrate_index * cos_substrate
        ) / (
            incident_index * cos_incident + substrate_index * cos_substrate
        )
    else:
        amplitude = (
            substrate_index * cos_incident - incident_index * cos_substrate
        ) / (
            substrate_index * cos_incident + incident_index * cos_substrate
        )
    return float(abs(amplitude) ** 2)


def run_self_test() -> None:
    screen.run_self_test()
    wavelengths = np.array([350.0, 550.0, 1000.0])
    layers = [(1.10, 120.0), (1.28, 100.0)]
    normal_r, normal_t, normal_residual = screen.optical_response(
        layers,
        wavelengths,
    )
    for polarization in ("TE", "TM"):
        oblique_r, oblique_t, oblique_residual = oblique_optical_response(
            layers,
            wavelengths,
            0.0,
            polarization,
        )
        if not np.allclose(oblique_r, normal_r, atol=1e-12):
            raise AssertionError(f"0-degree {polarization} reflectance regression failed.")
        if not np.allclose(oblique_t, normal_t, atol=1e-12):
            raise AssertionError(f"0-degree {polarization} transmittance regression failed.")
        if float(np.max(oblique_residual)) >= 1e-12:
            raise AssertionError(f"0-degree {polarization} energy check failed.")

    for polarization in ("TE", "TM"):
        calculated_r, _, residual = oblique_optical_response(
            [],
            wavelengths,
            45.0,
            polarization,
        )
        expected_r = analytic_bare_interface_reflectance(
            screen.AIR_REFRACTIVE_INDEX,
            screen.GLASS_REFRACTIVE_INDEX,
            45.0,
            polarization,
        )
        if not np.allclose(calculated_r, expected_r, atol=1e-12):
            raise AssertionError(f"45-degree {polarization} Fresnel check failed.")
        if float(np.max(residual)) >= 1e-12:
            raise AssertionError(f"45-degree {polarization} energy check failed.")

    if float(np.max(normal_residual)) >= 1e-12:
        raise AssertionError("Normal-incidence reference energy check failed.")
    print("Angle/polarization self-test passed.")


def main() -> None:
    arguments = parse_arguments()
    if arguments.self_test:
        run_self_test()
        return

    locked = load_locked_stack()
    wavelength_nm = screen.wavelengths_nm()
    power_density_w_m2_nm = screen.load_am15g_power_density(wavelength_nm)
    results, spectra = calculate_results(
        wavelength_nm,
        power_density_w_m2_nm,
        locked,
    )
    csv_path = write_csv(results)
    summary_path = write_summary(results, locked)
    gain_figure_path = write_gain_figure(results)
    transmittance_figure_path = write_transmittance_figure(results)
    spectra_figure_path = write_spectra_figure(spectra, wavelength_nm)
    print_results(
        results,
        locked,
        [
            csv_path,
            summary_path,
            gain_figure_path,
            transmittance_figure_path,
            spectra_figure_path,
        ],
    )


if __name__ == "__main__":
    main()