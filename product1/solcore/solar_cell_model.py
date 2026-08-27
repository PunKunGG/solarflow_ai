"""Solcore adapter for the next-stage electrical model."""
from __future__ import annotations

try:
    from solcore import material
    from solcore.solar_cell import SolarCell
    from solcore.solar_cell_solver import solar_cell_solver
except ImportError as exc:  # pragma: no cover
    material = SolarCell = solar_cell_solver = None
    _SOLCORE_IMPORT_ERROR = exc


def build_baseline():
    if material is None:
        raise RuntimeError(
            "Solcore is not installed. Install Solcore in the solarflow environment "
            "before running the electrical model."
        ) from _SOLCORE_IMPORT_ERROR

    si = material("Si")
    device = SolarCell([
        si(thickness=180e-6),
    ])
    return device


def run(device, temperature=300, illumination=1):
    if solar_cell_solver is None:
        raise RuntimeError("Solcore unavailable")
    options = {
        "optics_method": "BL",
        "voltages": [0, 0.9, 200],
        "internal_voltages": [0, 0.9, 200],
        "mpp": True,
        "light_source": "standard",
    }
    solar_cell_solver(device, task=["short_circuit", "iv_curve"], user_options=options)
    return device.iv
