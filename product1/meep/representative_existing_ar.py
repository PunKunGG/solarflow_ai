from __future__ import annotations

from dataclasses import dataclass

import flat_film


@dataclass(frozen=True)
class CoatingCase:
    label: str
    refractive_index: float
    thickness_nm: float
    description: str


CASES = (
    CoatingCase(
        label="existing_ar_n1p28_100nm",
        refractive_index=1.28,
        thickness_nm=100,
        description=(
            "Representative optically optimized "
            "porous-silica AR coating"
        ),
    ),
    CoatingCase(
        label="existing_ar_n1p28_180nm",
        refractive_index=1.28,
        thickness_nm=180,
        description=(
            "Representative thicker porous-silica "
            "AR coating reported in literature"
        ),
    ),
)


def run_case(case: CoatingCase) -> None:
    thickness_um = case.thickness_nm / 1000

    flat_film.FILM_REFRACTIVE_INDEX = (
        case.refractive_index
    )

    flat_film.FILM_THICKNESS_UM = thickness_um

    # Wavelength at which this layer satisfies
    # the quarter-wave condition.
    flat_film.DESIGN_WAVELENGTH_UM = (
        4
        * case.refractive_index
        * thickness_um
    )

    flat_film.MODEL_NAME = case.description

    flat_film.MODEL_ROLE = (
        "Representative existing-module baseline; "
        "not confirmed as the Sirindhorn module coating"
    )

    flat_film.CSV_PATH = (
        flat_film.RESULTS_DIRECTORY
        / f"{case.label}.csv"
    )

    flat_film.SUMMARY_PATH = (
        flat_film.RESULTS_DIRECTORY
        / f"{case.label}_summary.json"
    )

    flat_film.main()


def main() -> None:
    for case in CASES:
        print()
        print("=" * 70)
        print(f"Running case: {case.label}")
        print("=" * 70)

        run_case(case)


if __name__ == "__main__":
    main()