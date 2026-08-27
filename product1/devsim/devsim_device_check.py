"""DEVSIM verification entry point.

This is intentionally a scaffold: device geometry, contacts, doping and
recombination models must be specified after the first optical/solar-cell
candidate is selected. The script checks that DEVSIM can be imported.
"""
from __future__ import annotations


def check_import() -> None:
    try:
        import devsim  # noqa: F401
    except ImportError as exc:
        raise RuntimeError(
            "DEVSIM is not installed. Install it separately, then rerun."
        ) from exc
    print("DEVSIM import: OK")


if __name__ == "__main__":
    check_import()
