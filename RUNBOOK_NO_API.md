# SolarFlow AI — No-API Execution Runbook

This runbook is the reproducible path for Product 1 → Product 3 without any OpenAI API.
OpenAI can be added later as an optional orchestration layer; it is NOT required for the core numerical workflow.

## Product 1
1. Install Ubuntu/WSL2 and Miniconda/Anaconda on the user's PC.
2. Create the `solarflow` environment from `environment.yml`.
3. Install MEEP from conda-forge (`pymeep`).
4. Install Solcore in the same environment (or its current documented installation method).
5. Install DEVSIM according to its official package/release instructions.
6. Run Experiment 001: flat vs periodic silicon optical structure with MEEP.
7. Validate the numerical setup using convergence tests (resolution and runtime duration).
8. Feed optical absorption spectrum into the electrical model.
9. Run a parameter sweep/optimization using a numerical optimizer (Optuna/SciPy).
10. Store every experiment as JSON/CSV with geometry, simulator version, parameters, and results.

## Product 2
1. Freeze the winning architecture only after numerical validation.
2. Convert the geometry to a manufacturing-friendly design.
3. Specify material, feature size, thickness, tolerance, substrate/interface, and fabrication route.
4. Fabricate small coupons first.
5. Build at least one control and one treatment sample.
6. Characterize optical and electrical performance.
7. Reject the design if the optical gain does not translate into electrical gain or if reliability is unacceptable.

## Product 3
1. Select a compatible EGAT module/site.
2. Do not modify the floating structure or module encapsulation in the first pilot.
3. Start with small A/B testing: control module(s) vs treated module(s).
4. Match irradiance, module temperature, orientation, time and environmental conditions.
5. Log DC power, energy, temperature and irradiance continuously.
6. Compare normalized energy yield (e.g., kWh/kWp) rather than raw power alone.
7. Expand from module → small array → pilot array only after repeatable improvement is demonstrated.

## Scientific rule
Never present the dry-run surrogate numbers as physics results. Only simulator outputs from the validated MEEP/Solcore/DEVSIM environment may be reported as simulation evidence.
