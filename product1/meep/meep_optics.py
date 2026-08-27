"""MEEP optical simulation adapter.

Runs a simple 2D normal-incidence comparison for a flat silicon slab and a
periodic surface-grating candidate. The exact geometry/material model should
be refined before using results in a scientific submission.
"""
from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path
from typing import Iterable

try:
    import meep as mp
except ImportError as exc:  # pragma: no cover
    mp = None
    _MEEP_IMPORT_ERROR = exc


def _sim_one(height_nm: float, width_nm: float, period_nm: float, out_csv: Path,
             resolution: int = 40, structured: bool = True) -> None:
    if mp is None:
        raise RuntimeError(
            "MEEP is not installed. Activate the solarflow conda environment "
            "and install pymeep from conda-forge first."
        ) from _MEEP_IMPORT_ERROR

    # Use microns as the MEEP length unit.
    h = height_nm / 1000.0
    w = width_nm / 1000.0
    p = period_nm / 1000.0

    sx, sy = p, 4.0
    dpml = 1.0
    cell = mp.Vector3(sx, sy + 2 * dpml, 0)
    geometry = [
        mp.Block(
            size=mp.Vector3(mp.inf, sy, mp.inf),
            center=mp.Vector3(0, -0.5 * sy, 0),
            material=mp.Medium(index=3.6),
        )
    ]

    if structured:
        # A simple rectangular ridge at the top surface.
        geometry.append(
            mp.Block(
                size=mp.Vector3(w, h, mp.inf),
                center=mp.Vector3(0, 0.5 * sy + 0.5 * h, 0),
                material=mp.Medium(index=3.6),
            )
        )

    fmin = 1.0 / (1100.0 / 1000.0)
    fmax = 1.0 / (400.0 / 1000.0)
    nfreq = 71

    sim = mp.Simulation(
        cell_size=cell,
        boundary_layers=[mp.PML(dpml, direction=mp.Y)],
        geometry=geometry,
        sources=[
            mp.Source(
                src=mp.GaussianSource(0.5 * (fmin + fmax), fwidth=fmax - fmin),
                component=mp.Ex,
                center=mp.Vector3(0, -0.5 * sy - 0.3, 0),
                size=mp.Vector3(mp.inf, 0, 0),
            )
        ],
        resolution=resolution,
        dimensions=2,
        symmetries=[mp.Mirror(mp.X)],
    )

    refl = sim.add_flux(
        0.5 * (fmin + fmax), fmax - fmin, nfreq,
        mp.FluxRegion(center=mp.Vector3(0, -0.2, 0), size=mp.Vector3(mp.inf, 0, 0))
    )
    tran = sim.add_flux(
        0.5 * (fmin + fmax), fmax - fmin, nfreq,
        mp.FluxRegion(center=mp.Vector3(0, 1.2, 0), size=mp.Vector3(mp.inf, 0, 0))
    )

    sim.run(until_after_sources=80)
    freqs = mp.get_flux_freqs(refl)
    r_flux = mp.get_fluxes(refl)
    t_flux = mp.get_fluxes(tran)

    rows = []
    for f, rf, tf in zip(freqs, r_flux, t_flux):
        wl_um = 1.0 / f
        rows.append({
            "wavelength_nm": wl_um * 1000.0,
            "reflection_proxy": rf,
            "transmission_proxy": tf,
            "absorption_proxy": 1.0 - rf - tf,
        })

    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--height-nm", type=float, default=200)
    ap.add_argument("--width-nm", type=float, default=300)
    ap.add_argument("--period-nm", type=float, default=600)
    ap.add_argument("--flat", action="store_true")
    args = ap.parse_args()
    _sim_one(
        args.height_nm, args.width_nm, args.period_nm, args.out,
        structured=not args.flat,
    )


if __name__ == "__main__":
    main()
