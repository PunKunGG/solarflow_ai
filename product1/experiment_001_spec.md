# Experiment 001 — Photon Management Baseline

## Hypothesis
A carefully chosen periodic surface geometry may alter optical reflection/transmission and can potentially increase wavelength-integrated absorption in a silicon-like absorbing layer.

## Important limitation
This first experiment is an optical proof-of-concept only. It does NOT by itself prove higher solar-cell efficiency.

## Control
Flat silicon slab.

## Treatment
A periodic surface relief geometry parameterized by:
- height_nm
- width_nm
- period_nm

## Primary outputs
- Reflection spectrum R(lambda)
- Transmission spectrum T(lambda)
- Absorption spectrum A(lambda) = 1 - R - T

## Secondary outputs
- wavelength-weighted absorption over the chosen spectral band
- convergence vs spatial resolution
- sensitivity to geometry perturbations

## Acceptance criteria before optimization
1. Energy balance is numerically sensible.
2. Increasing resolution changes the key metric by less than the preset tolerance.
3. Flat-control simulation is reproducible.
4. Output CSV contains enough metadata to reproduce the run.
