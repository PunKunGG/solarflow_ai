"""Phase 1.6B measured-module spectral-response proxy ensemble.

The script combines the conditional optical sensitivity grid from Phase 1.6A
with normalized median spectral-response (SR) curves measured on three
commercial mono-Si PERC reference modules.  For each optical case it computes

    integral(E_AM1.5G * SR_proxy * T_retrofit/T_baseline)
    ---------------------------------------------------  - 1
              integral(E_AM1.5G * SR_proxy)

and reports the result as a *relative normalized-photocurrent proxy gain*.

The SR curves are not measurements of JA Solar JAM72D10-405/MB.  They are
normalized and therefore cannot establish absolute current, module power,
efficiency, or annual energy yield.  The optical stack remains conditional on
the Phase 1.6A assumptions.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import itertools
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import matplotlib.pyplot as plt
import numpy as np

from product1.analysis import carrier_interface_screen as screen
from product1.analysis import phase_1_6_optical_sensitivity as phase1a


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = REPO_ROOT / "configs" / "phase_1_6b_proxy_sr.yaml"
RESULTS_DIR = REPO_ROOT / "product1" / "results"
FIGURES_DIR = RESULTS_DIR / "figures"

CSV_PATH = RESULTS_DIR / "phase_1_6b_proxy_sr.csv"
SUMMARY_PATH = RESULTS_DIR / "phase_1_6b_proxy_sr_summary.json"
DISTRIBUTION_PATH = FIGURES_DIR / "phase_1_6b_proxy_gain_distribution.png"
NOMINAL_SPECTRAL_PATH = FIGURES_DIR / "phase_1_6b_nominal_spectral_weighting.png"


@dataclass(frozen=True)
class ProxyCurve:
    proxy_id: str
    label: str
    group: str
    role: str
    limitation: str
    wavelength_nm: np.ndarray
    normalized_sr: np.ndarray
    source_attributes: dict[str, Any]


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="SolarFlow Phase 1.6B measured-module SR proxy ensemble."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help="Path to the JSON-syntax YAML Phase 1.6B configuration.",
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=None,
        help="Override the local sr_library.nc path from the configuration.",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run deterministic kernel tests without Solcore, xarray, or NetCDF data.",
    )
    return parser.parse_args()


def resolve_repo_path(path_value: str | Path) -> Path:
    path = Path(path_value).expanduser()
    return path if path.is_absolute() else REPO_ROOT / path


def load_json_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Configuration not found: {path}")
    try:
        with path.open("r", encoding="utf-8") as file:
            config = json.load(file)
    except json.JSONDecodeError as error:
        raise ValueError(
            "The .yaml files use JSON syntax (valid YAML 1.2). Keep this file "
            "valid JSON or add an explicit YAML parser."
        ) from error
    validate_config(config)
    return config


def validate_config(config: dict[str, Any]) -> None:
    required = (
        "phase_1_6a_config",
        "dataset",
        "proxies",
        "gates",
        "interpretation",
        "required_warnings",
    )
    missing = [name for name in required if name not in config]
    if missing:
        raise ValueError(f"Missing Phase 1.6B configuration sections: {missing}")

    if not config["proxies"]:
        raise ValueError("At least one SR proxy must be configured.")
    proxy_ids = [str(item["id"]) for item in config["proxies"]]
    groups = [str(item["group"]) for item in config["proxies"]]
    if len(proxy_ids) != len(set(proxy_ids)):
        raise ValueError("Proxy identifiers must be unique.")
    if len(groups) != len(set(groups)):
        raise ValueError("NetCDF group names must be unique.")

    positive_gate = float(config["gates"]["positive_gain_percent"])
    margin_gate = float(config["gates"]["provisional_margin_percent"])
    if not math.isfinite(positive_gate) or not math.isfinite(margin_gate):
        raise ValueError("Gain gates must be finite.")
    if margin_gate < positive_gate:
        raise ValueError("The provisional margin cannot be below the positive gate.")


def validate_dataset_file(path: Path) -> dict[str, Any]:
    """Reject common migration-page/download failures and record provenance."""
    if not path.exists():
        raise FileNotFoundError(
            f"SR library not found: {path}\n"
            "Download the actual NetCDF resource as described in "
            "data/external/README.md."
        )
    if not path.is_file():
        raise ValueError(f"SR library path is not a file: {path}")

    size_bytes = path.stat().st_size
    with path.open("rb") as file:
        prefix = file.read(512)
    lowered = prefix.lower().lstrip()
    if lowered.startswith((b"<!doctype html", b"<html", b"<head", b"<body")):
        raise ValueError(
            f"{path} is HTML, not NetCDF. The former download URL may have "
            "redirected to the DuraMAT migration page."
        )
    if size_bytes < 10_000:
        raise ValueError(
            f"{path} is only {size_bytes} bytes and is unlikely to be the "
            "reported spectral-response NetCDF resource."
        )

    digest = hashlib.sha256()
    with path.open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(block)
    return {
        "resolved_path": str(path.resolve()),
        "size_bytes": size_bytes,
        "sha256": digest.hexdigest(),
    }


def _json_safe_attributes(attributes: dict[str, Any]) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    for key, value in attributes.items():
        if isinstance(value, (str, int, float, bool)) or value is None:
            safe[str(key)] = value
        elif isinstance(value, np.generic):
            safe[str(key)] = value.item()
        else:
            safe[str(key)] = str(value)
    return safe


def _wavelength_dimension(data_array: Any) -> str:
    name_tokens = ("wavelength", "wave", "lambda", "wl")
    for dimension in data_array.dims:
        if any(token in dimension.lower() for token in name_tokens):
            return str(dimension)

    for coordinate_name, coordinate in data_array.coords.items():
        if coordinate.ndim != 1 or coordinate.dims[0] not in data_array.dims:
            continue
        units = str(coordinate.attrs.get("units", "")).lower()
        if any(token in coordinate_name.lower() for token in name_tokens):
            return str(coordinate.dims[0])
        if any(token in units for token in ("nm", "nanomet", "microm", "µm")):
            return str(coordinate.dims[0])

    plausible = [dimension for dimension in data_array.dims if data_array.sizes[dimension] >= 20]
    if len(plausible) == 1:
        return str(plausible[0])
    raise ValueError(
        f"Could not identify the wavelength dimension in SR variable with "
        f"dimensions {data_array.dims}."
    )


def _convert_wavelength_to_nm(values: np.ndarray, units: str) -> np.ndarray:
    units_lower = units.lower().replace(" ", "")
    result = np.asarray(values, dtype=float)
    if "nm" in units_lower or "nanomet" in units_lower:
        factor = 1.0
    elif "µm" in units_lower or "um" in units_lower or "microm" in units_lower:
        factor = 1000.0
    elif units_lower in ("m", "meter", "metre", "meters", "metres"):
        factor = 1.0e9
    elif not units_lower:
        finite = result[np.isfinite(result)]
        if not finite.size:
            raise ValueError("Wavelength coordinate contains no finite values.")
        maximum = float(np.max(finite))
        if maximum < 5.0:
            factor = 1000.0
        else:
            factor = 1.0
    else:
        raise ValueError(f"Unsupported wavelength units: {units!r}")
    return result * factor


def load_proxy_curve(dataset_path: Path, definition: dict[str, Any]) -> ProxyCurve:
    try:
        import xarray as xr
    except ImportError as error:
        raise RuntimeError(
            "Phase 1.6B requires xarray and an HDF5/NetCDF backend. Install "
            "them in solarflow-full with: python -m pip install xarray h5netcdf"
        ) from error

    group = str(definition["group"])
    variable = str(definition.get("variable", "sr"))
    try:
        with xr.open_dataset(dataset_path, group=group) as dataset:
            if variable not in dataset:
                raise KeyError(
                    f"Group {group!r} does not contain variable {variable!r}; "
                    f"available variables: {list(dataset.data_vars)}"
                )
            data_array = dataset[variable].load().squeeze(drop=True)
            dataset_attributes = _json_safe_attributes(dict(dataset.attrs))
            variable_attributes = _json_safe_attributes(dict(data_array.attrs))
    except Exception as error:
        raise RuntimeError(
            f"Could not read NetCDF group {group!r} and variable {variable!r} "
            f"from {dataset_path}: {error}"
        ) from error

    wavelength_dimension = _wavelength_dimension(data_array)
    other_dimensions = [
        dimension for dimension in data_array.dims if dimension != wavelength_dimension
    ]
    if other_dimensions:
        data_array = data_array.median(dim=other_dimensions, skipna=True)
    if data_array.ndim != 1:
        raise ValueError(
            f"SR variable {group}/{variable} could not be reduced to one dimension."
        )

    if wavelength_dimension in data_array.coords:
        coordinate = data_array.coords[wavelength_dimension]
    else:
        raise ValueError(
            f"SR variable {group}/{variable} has no coordinate for "
            f"dimension {wavelength_dimension!r}."
        )

    wavelength = _convert_wavelength_to_nm(
        np.asarray(coordinate.values),
        str(coordinate.attrs.get("units", "")),
    )
    response = np.asarray(data_array.values, dtype=float)
    valid = np.isfinite(wavelength) & np.isfinite(response) & (response >= 0.0)
    wavelength = wavelength[valid]
    response = response[valid]
    if wavelength.size < 20:
        raise ValueError(f"SR curve {group!r} has fewer than 20 valid samples.")

    order = np.argsort(wavelength)
    wavelength = wavelength[order]
    response = response[order]
    unique_wavelength, unique_indices = np.unique(wavelength, return_index=True)
    response = response[unique_indices]
    wavelength = unique_wavelength

    peak = float(np.max(response))
    if peak <= 0.0:
        raise ValueError(f"SR curve {group!r} has no positive response.")
    response = response / peak
    if float(np.min(wavelength)) > 400.0 or float(np.max(wavelength)) < 1000.0:
        raise ValueError(
            f"SR curve {group!r} spans {wavelength.min():.1f}-"
            f"{wavelength.max():.1f} nm, which is unexpectedly narrow."
        )

    attributes = {
        "dataset": dataset_attributes,
        "variable": variable_attributes,
        "wavelength_dimension": wavelength_dimension,
        "original_sample_count": int(wavelength.size),
        "source_wavelength_min_nm": float(np.min(wavelength)),
        "source_wavelength_max_nm": float(np.max(wavelength)),
        "analysis_normalization": "divided by finite non-negative curve maximum",
    }
    return ProxyCurve(
        proxy_id=str(definition["id"]),
        label=str(definition["label"]),
        group=group,
        role=str(definition.get("role", "measured-module proxy")),
        limitation=str(definition.get("limitation", "Not the target module.")),
        wavelength_nm=wavelength,
        normalized_sr=response,
        source_attributes=attributes,
    )


def interpolate_proxy(curve: ProxyCurve, wavelength_nm: np.ndarray) -> np.ndarray:
    interpolated = np.interp(
        wavelength_nm,
        curve.wavelength_nm,
        curve.normalized_sr,
        left=0.0,
        right=0.0,
    )
    if not np.all(np.isfinite(interpolated)) or np.any(interpolated < 0.0):
        raise RuntimeError(f"Interpolation produced invalid values for {curve.proxy_id}.")
    return interpolated


def integrate(y: np.ndarray, x: np.ndarray) -> float:
    if hasattr(np, "trapezoid"):
        return float(np.trapezoid(y, x))
    return float(np.trapz(y, x))


def relative_proxy_gain_percent(
    wavelength_nm: np.ndarray,
    spectral_weight: np.ndarray,
    transmission_modifier: np.ndarray,
) -> tuple[float, float, float]:
    baseline = integrate(spectral_weight, wavelength_nm)
    if not math.isfinite(baseline) or baseline <= 0.0:
        raise ValueError("A proxy spectral weight integrates to a non-positive value.")
    retrofit = integrate(spectral_weight * transmission_modifier, wavelength_nm)
    gain = 100.0 * (retrofit - baseline) / baseline
    return baseline, retrofit, gain


def parameter_combinations(config_1_6a: dict[str, Any]) -> Iterable[dict[str, float]]:
    sweep = config_1_6a["sweep"]
    value_lists = [
        [float(value) for value in sweep[name]] for name in phase1a.PARAMETER_FIELDS
    ]
    for values in itertools.product(*value_lists):
        yield dict(zip(phase1a.PARAMETER_FIELDS, values, strict=True))


def stack_transmittances(
    parameters: dict[str, float],
    wavelength_nm: np.ndarray,
    config_1_6a: dict[str, Any],
    baseline_cache: dict[tuple[float, float], tuple[np.ndarray, float]],
) -> tuple[np.ndarray, np.ndarray, float]:
    model = config_1_6a["model"]
    incident_index = float(model["incident_refractive_index"])
    glass_index = float(model["glass_refractive_index"])
    ar_key = (
        parameters["existing_ar_refractive_index"],
        parameters["existing_ar_thickness_nm"],
    )
    if ar_key not in baseline_cache:
        _, baseline_t, _, baseline_violation = phase1a.optical_response(
            [(ar_key[0], 0.0, ar_key[1])],
            wavelength_nm,
            incident_index,
            glass_index,
        )
        baseline_cache[ar_key] = (baseline_t, float(np.max(baseline_violation)))
    baseline_t, baseline_violation = baseline_cache[ar_key]

    _, retrofit_t, _, retrofit_violation = phase1a.optical_response(
        [
            (
                parameters["active_refractive_index"],
                parameters["active_extinction_coefficient"],
                parameters["active_thickness_nm"],
            ),
            (
                parameters["primer_refractive_index"],
                0.0,
                parameters["primer_thickness_nm"],
            ),
            (
                parameters["existing_ar_refractive_index"],
                0.0,
                parameters["existing_ar_thickness_nm"],
            ),
        ],
        wavelength_nm,
        incident_index,
        glass_index,
    )
    maximum_violation = max(baseline_violation, float(np.max(retrofit_violation)))
    if maximum_violation > 1.0e-9:
        raise RuntimeError(
            f"TMM physical-bound violation {maximum_violation:.3e} exceeds tolerance."
        )
    if np.any(baseline_t <= 1.0e-12):
        raise RuntimeError("Baseline transmittance is too small for a stable ratio.")
    return baseline_t, retrofit_t, maximum_violation


def is_nominal_case(
    parameters: dict[str, float], config_1_6a: dict[str, Any]
) -> bool:
    nominal = config_1_6a["nominal_stack"]
    return all(
        math.isclose(parameters[name], float(nominal[name]), rel_tol=0.0, abs_tol=1e-12)
        for name in phase1a.PARAMETER_FIELDS
    )


def evaluate_grid(
    wavelength_nm: np.ndarray,
    power_density_w_m2_nm: np.ndarray,
    proxy_curves: list[ProxyCurve],
    config_1_6a: dict[str, Any],
    config_1_6b: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    positive_gate = float(config_1_6b["gates"]["positive_gain_percent"])
    margin_gate = float(config_1_6b["gates"]["provisional_margin_percent"])
    interpolated = {
        curve.proxy_id: interpolate_proxy(curve, wavelength_nm)
        for curve in proxy_curves
    }
    spectral_weights = {
        curve.proxy_id: power_density_w_m2_nm * interpolated[curve.proxy_id]
        for curve in proxy_curves
    }

    baseline_cache: dict[tuple[float, float], tuple[np.ndarray, float]] = {}
    rows: list[dict[str, Any]] = []
    case_summaries: list[dict[str, Any]] = []
    nominal_payload: dict[str, Any] | None = None

    for case_id, parameters in enumerate(parameter_combinations(config_1_6a), start=1):
        baseline_t, retrofit_t, physical_violation = stack_transmittances(
            parameters,
            wavelength_nm,
            config_1_6a,
            baseline_cache,
        )
        modifier = retrofit_t / baseline_t
        gains: list[float] = []
        case_is_nominal = is_nominal_case(parameters, config_1_6a)
        nominal_proxy_rows: list[dict[str, Any]] = []

        for curve in proxy_curves:
            baseline_response, retrofit_response, gain = relative_proxy_gain_percent(
                wavelength_nm,
                spectral_weights[curve.proxy_id],
                modifier,
            )
            gains.append(gain)
            row = {
                "case_id": case_id,
                **parameters,
                "proxy_id": curve.proxy_id,
                "proxy_label": curve.label,
                "proxy_group": curve.group,
                "baseline_normalized_response_integral": baseline_response,
                "retrofit_normalized_response_integral": retrofit_response,
                "relative_photocurrent_proxy_gain_percent": gain,
                "passes_positive_gain_gate": gain > positive_gate,
                "passes_provisional_margin_gate": gain >= margin_gate,
                "is_nominal_optical_case": case_is_nominal,
                "maximum_tmm_physical_violation": physical_violation,
            }
            rows.append(row)
            if case_is_nominal:
                nominal_proxy_rows.append(row)

        case_minimum = float(np.min(gains))
        case_median = float(np.median(gains))
        case_maximum = float(np.max(gains))
        case_summaries.append(
            {
                "case_id": case_id,
                **parameters,
                "minimum_proxy_gain_percent": case_minimum,
                "median_proxy_gain_percent": case_median,
                "maximum_proxy_gain_percent": case_maximum,
                "all_proxies_positive": case_minimum > positive_gate,
                "all_proxies_pass_provisional_margin": case_minimum >= margin_gate,
            }
        )
        if case_is_nominal:
            nominal_payload = {
                "parameters": parameters,
                "by_proxy": nominal_proxy_rows,
                "minimum_proxy_gain_percent": case_minimum,
                "median_proxy_gain_percent": case_median,
                "maximum_proxy_gain_percent": case_maximum,
                "baseline_transmittance": baseline_t,
                "retrofit_transmittance": retrofit_t,
                "transmission_modifier": modifier,
                "interpolated_sr": interpolated,
                "spectral_weights": spectral_weights,
            }

    if nominal_payload is None:
        raise RuntimeError("The Phase 1.6A nominal point is not present in its sweep grid.")
    return rows, case_summaries, nominal_payload


def distribution_statistics(values: np.ndarray) -> dict[str, float]:
    return {
        "minimum_percent": float(np.min(values)),
        "percentile_05_percent": float(np.percentile(values, 5.0)),
        "median_percent": float(np.median(values)),
        "percentile_95_percent": float(np.percentile(values, 95.0)),
        "maximum_percent": float(np.max(values)),
    }


def write_csv(rows: list[dict[str, Any]]) -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    with CSV_PATH.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return CSV_PATH


def write_summary(
    rows: list[dict[str, Any]],
    case_summaries: list[dict[str, Any]],
    nominal_payload: dict[str, Any],
    proxy_curves: list[ProxyCurve],
    dataset_metadata: dict[str, Any],
    config_1_6a: dict[str, Any],
    config_1_6b: dict[str, Any],
) -> Path:
    positive_gate = float(config_1_6b["gates"]["positive_gain_percent"])
    margin_gate = float(config_1_6b["gates"]["provisional_margin_percent"])
    by_proxy: dict[str, Any] = {}
    for curve in proxy_curves:
        proxy_rows = [row for row in rows if row["proxy_id"] == curve.proxy_id]
        gains = np.array(
            [row["relative_photocurrent_proxy_gain_percent"] for row in proxy_rows]
        )
        positive_count = int(np.sum(gains > positive_gate))
        margin_count = int(np.sum(gains >= margin_gate))
        by_proxy[curve.proxy_id] = {
            "label": curve.label,
            "group": curve.group,
            "role": curve.role,
            "limitation": curve.limitation,
            "source_attributes": curve.source_attributes,
            "grid_statistics": distribution_statistics(gains),
            "positive_case_count": positive_count,
            "positive_case_fraction": positive_count / gains.size,
            "provisional_margin_case_count": margin_count,
            "provisional_margin_case_fraction": margin_count / gains.size,
        }

    minimum_gains = np.array(
        [item["minimum_proxy_gain_percent"] for item in case_summaries]
    )
    all_positive_count = int(
        sum(item["all_proxies_positive"] for item in case_summaries)
    )
    all_margin_count = int(
        sum(item["all_proxies_pass_provisional_margin"] for item in case_summaries)
    )
    worst_case = min(
        case_summaries, key=lambda item: item["minimum_proxy_gain_percent"]
    )
    nominal_rows = [
        {
            key: value
            for key, value in row.items()
            if key
            in (
                "proxy_id",
                "proxy_label",
                "proxy_group",
                "baseline_normalized_response_integral",
                "retrofit_normalized_response_integral",
                "relative_photocurrent_proxy_gain_percent",
                "passes_positive_gain_gate",
                "passes_provisional_margin_gate",
            )
        }
        for row in nominal_payload["by_proxy"]
    ]

    if all_margin_count == len(case_summaries):
        decision = (
            "All defined optical cases retain the provisional margin for every "
            "measured SR proxy. This remains proxy-weighted conditional evidence."
        )
    elif all_positive_count == len(case_summaries):
        decision = (
            "All defined optical cases remain positive for every measured SR proxy, "
            "but at least one falls below the provisional margin."
        )
    else:
        decision = (
            "At least one defined optical case is non-positive for at least one "
            "measured SR proxy. Do not freeze an electrical-performance claim."
        )

    payload = {
        "phase": config_1_6b.get("phase", "1.6B"),
        "title": config_1_6b.get("title"),
        "scientific_status": config_1_6b.get("scientific_status"),
        "quantity_reported": config_1_6b["interpretation"]["output_quantity"],
        "dataset": {**config_1_6b["dataset"], **dataset_metadata},
        "optical_model": config_1_6a["model"],
        "gates": config_1_6b["gates"],
        "optical_case_count": len(case_summaries),
        "proxy_count": len(proxy_curves),
        "evaluated_case_proxy_combinations": len(rows),
        "nominal_optical_case": {
            "parameters": nominal_payload["parameters"],
            "by_proxy": nominal_rows,
            "ensemble_minimum_gain_percent": nominal_payload[
                "minimum_proxy_gain_percent"
            ],
            "ensemble_median_gain_percent": nominal_payload[
                "median_proxy_gain_percent"
            ],
            "ensemble_maximum_gain_percent": nominal_payload[
                "maximum_proxy_gain_percent"
            ],
        },
        "grid_by_proxy": by_proxy,
        "across_proxy_conservative_grid": {
            **distribution_statistics(minimum_gains),
            "all_proxies_positive_case_count": all_positive_count,
            "all_proxies_positive_case_fraction": all_positive_count
            / len(case_summaries),
            "all_proxies_margin_case_count": all_margin_count,
            "all_proxies_margin_case_fraction": all_margin_count
            / len(case_summaries),
            "worst_case": worst_case,
        },
        "decision": decision,
        "interpretation": config_1_6b["interpretation"],
        "required_warnings": config_1_6b["required_warnings"],
        "outputs": [str(CSV_PATH), str(SUMMARY_PATH), str(DISTRIBUTION_PATH), str(NOMINAL_SPECTRAL_PATH)],
    }
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    with SUMMARY_PATH.open("w", encoding="utf-8") as file:
        json.dump(payload, file, indent=2, ensure_ascii=False)
        file.write("\n")
    return SUMMARY_PATH


def plot_distributions(
    rows: list[dict[str, Any]], proxy_curves: list[ProxyCurve], config: dict[str, Any]
) -> Path:
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    values = [
        np.array(
            [
                row["relative_photocurrent_proxy_gain_percent"]
                for row in rows
                if row["proxy_id"] == curve.proxy_id
            ]
        )
        for curve in proxy_curves
    ]
    labels = [curve.label for curve in proxy_curves]
    margin = float(config["gates"]["provisional_margin_percent"])

    figure, axis = plt.subplots(figsize=(10.5, 6.2))
    parts = axis.violinplot(values, showmeans=False, showmedians=True, showextrema=True)
    for body, color in zip(parts["bodies"], ("#4c78a8", "#59a14f", "#f28e2b")):
        body.set_facecolor(color)
        body.set_edgecolor("black")
        body.set_alpha(0.72)
    axis.axhline(0.0, color="black", linewidth=1.2)
    axis.axhline(
        margin,
        color="#e66101",
        linestyle="--",
        linewidth=1.5,
        label=f"Provisional margin: {margin:.2f}%",
    )
    axis.set_xticks(np.arange(1, len(labels) + 1), labels, rotation=10, ha="right")
    axis.set_ylabel("Relative normalized-photocurrent proxy gain (%)")
    axis.set_title("SolarFlow Phase 1.6B — SR-proxy uncertainty distributions")
    axis.grid(axis="y", alpha=0.25)
    axis.legend(loc="best")
    figure.text(
        0.5,
        0.012,
        "Measured normalized SR proxies; conditional optical grid; not electrical module power.",
        ha="center",
        fontsize=9,
    )
    figure.tight_layout(rect=(0.0, 0.04, 1.0, 1.0))
    figure.savefig(DISTRIBUTION_PATH, dpi=220)
    plt.close(figure)
    return DISTRIBUTION_PATH


def plot_nominal_spectral_weighting(
    wavelength_nm: np.ndarray,
    proxy_curves: list[ProxyCurve],
    nominal_payload: dict[str, Any],
) -> Path:
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    figure, (axis_sr, axis_modifier) = plt.subplots(2, 1, figsize=(10.5, 8.0), sharex=True)
    for curve in proxy_curves:
        axis_sr.plot(
            wavelength_nm,
            nominal_payload["interpolated_sr"][curve.proxy_id],
            linewidth=1.8,
            label=curve.label,
        )
    axis_sr.set_ylabel("Normalized SR (relative)")
    axis_sr.set_title("Phase 1.6B nominal spectral weighting inputs")
    axis_sr.set_ylim(bottom=0.0)
    axis_sr.grid(alpha=0.25)
    axis_sr.legend(loc="best")

    modifier_percent = 100.0 * (nominal_payload["transmission_modifier"] - 1.0)
    axis_modifier.plot(wavelength_nm, modifier_percent, color="#7b3294", linewidth=1.8)
    axis_modifier.axhline(0.0, color="black", linewidth=1.0)
    axis_modifier.set_xlabel("Wavelength (nm)")
    axis_modifier.set_ylabel("Retrofit/baseline change (%)")
    axis_modifier.grid(alpha=0.25)
    figure.text(
        0.5,
        0.012,
        "SR curves are proxies, not JAM72D10-405/MB measurements; relative weighting only.",
        ha="center",
        fontsize=9,
    )
    figure.tight_layout(rect=(0.0, 0.04, 1.0, 1.0))
    figure.savefig(NOMINAL_SPECTRAL_PATH, dpi=220)
    plt.close(figure)
    return NOMINAL_SPECTRAL_PATH


def run_self_test() -> None:
    wavelength = np.arange(300.0, 1201.0, 1.0)
    power = 0.4 + np.exp(-0.5 * ((wavelength - 650.0) / 220.0) ** 2)
    response = np.exp(-0.5 * ((wavelength - 780.0) / 240.0) ** 2)
    spectral_weight = power * response

    _, _, zero_gain = relative_proxy_gain_percent(
        wavelength, spectral_weight, np.ones_like(wavelength)
    )
    if not math.isclose(zero_gain, 0.0, abs_tol=1.0e-12):
        raise AssertionError(f"Unity-modifier test failed: {zero_gain}")

    _, _, one_percent_gain = relative_proxy_gain_percent(
        wavelength, spectral_weight, np.full_like(wavelength, 1.01)
    )
    if not math.isclose(one_percent_gain, 1.0, abs_tol=1.0e-10):
        raise AssertionError(f"Constant-modifier test failed: {one_percent_gain}")

    _, _, scaled_response_gain = relative_proxy_gain_percent(
        wavelength, 17.0 * spectral_weight, np.full_like(wavelength, 1.01)
    )
    if not math.isclose(scaled_response_gain, one_percent_gain, abs_tol=1.0e-10):
        raise AssertionError("Normalized-SR scale-invariance test failed.")

    reflectance, transmittance, absorptance, violation = phase1a.optical_response(
        [(1.25, 0.0, 100.0)], wavelength, 1.0, 1.52
    )
    if float(np.max(np.abs(reflectance + transmittance + absorptance - 1.0))) > 1e-10:
        raise AssertionError("Lossless TMM conservation test failed.")
    if float(np.max(violation)) > 1e-10:
        raise AssertionError("Lossless TMM physical-bound test failed.")
    print("Phase 1.6B proxy-SR self-test passed.")


def main() -> None:
    arguments = parse_arguments()
    if arguments.self_test:
        run_self_test()
        return

    config_path = arguments.config.resolve()
    config_1_6b = load_json_yaml(config_path)
    config_1_6a_path = resolve_repo_path(config_1_6b["phase_1_6a_config"])
    config_1_6a = phase1a.load_config(config_1_6a_path)

    dataset_path = (
        arguments.dataset.expanduser()
        if arguments.dataset is not None
        else resolve_repo_path(config_1_6b["dataset"]["path"])
    )
    dataset_metadata = validate_dataset_file(dataset_path)
    proxy_curves = [
        load_proxy_curve(dataset_path, definition)
        for definition in config_1_6b["proxies"]
    ]

    wavelength_nm = phase1a.wavelengths_nm(config_1_6a)
    print(f"Loading AM1.5G spectrum for {wavelength_nm.size} wavelength points...")
    power_density = screen.load_am15g_power_density(wavelength_nm)
    expected_cases = phase1a.expected_case_count(config_1_6a)
    print(
        f"Evaluating {expected_cases} optical cases against "
        f"{len(proxy_curves)} measured SR proxies..."
    )
    rows, case_summaries, nominal_payload = evaluate_grid(
        wavelength_nm,
        power_density,
        proxy_curves,
        config_1_6a,
        config_1_6b,
    )

    csv_path = write_csv(rows)
    distribution_path = plot_distributions(rows, proxy_curves, config_1_6b)
    nominal_spectral_path = plot_nominal_spectral_weighting(
        wavelength_nm, proxy_curves, nominal_payload
    )
    summary_path = write_summary(
        rows,
        case_summaries,
        nominal_payload,
        proxy_curves,
        dataset_metadata,
        config_1_6a,
        config_1_6b,
    )

    all_positive = sum(item["all_proxies_positive"] for item in case_summaries)
    all_margin = sum(
        item["all_proxies_pass_provisional_margin"] for item in case_summaries
    )
    worst_case = min(
        case_summaries, key=lambda item: item["minimum_proxy_gain_percent"]
    )
    print("SolarFlow Phase 1.6B measured-proxy SR screen completed.")
    print(f"Dataset SHA-256             : {dataset_metadata['sha256']}")
    print(f"Optical cases               : {len(case_summaries)}")
    print(f"Case-proxy combinations     : {len(rows)}")
    print("Nominal relative photocurrent-proxy gains:")
    for row in nominal_payload["by_proxy"]:
        print(
            f"  {row['proxy_id']:<22}: "
            f"{row['relative_photocurrent_proxy_gain_percent']:+.4f}%"
        )
    print(
        "Nominal ensemble min/median/max: "
        f"{nominal_payload['minimum_proxy_gain_percent']:+.4f}% / "
        f"{nominal_payload['median_proxy_gain_percent']:+.4f}% / "
        f"{nominal_payload['maximum_proxy_gain_percent']:+.4f}%"
    )
    print(
        f"All proxies positive        : {all_positive}/{len(case_summaries)} "
        f"({100.0 * all_positive / len(case_summaries):.2f}%)"
    )
    print(
        f"All proxies pass +0.10%     : {all_margin}/{len(case_summaries)} "
        f"({100.0 * all_margin / len(case_summaries):.2f}%)"
    )
    print(
        "Worst across-proxy case     : "
        f"{worst_case['minimum_proxy_gain_percent']:+.4f}%"
    )
    print("Outputs:")
    for path in (csv_path, summary_path, distribution_path, nominal_spectral_path):
        print(f"  - {path}")
    print()
    for warning in config_1_6b["required_warnings"]:
        print(f"WARNING: {warning}")


if __name__ == "__main__":
    main()
