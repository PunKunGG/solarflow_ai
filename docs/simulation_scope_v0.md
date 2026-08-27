# Retrofit Optical Film Simulation Scope v0.1

## Goal

Compare the optical performance of an existing floating photovoltaic
module with removable optical film designs installed on its front glass.

The film does not generate electricity directly. It aims to increase
the amount of sunlight transmitted through the existing module cover glass.

## Target application

Representative double-glass floating photovoltaic module based on the
Sirindhorn Dam Hydro-Floating Solar Hybrid use case.

The exact module model and material datasheet are not yet available.
Initial simulations therefore use documented representative optical properties.

## Compared designs

1. Bare cover glass baseline
2. Cover glass with representative anti-reflective coating
3. Cover glass with flat retrofit film
4. Cover glass with microstructured retrofit film

## Optical stack

Air
→ Microstructured film surface
→ Transparent film base
→ Removable optical coupling layer
→ Existing module cover glass

## Initial simulation conditions

- Wavelength range: 300–1200 nm
- Initial incident angle: 0 degrees
- Later angle sweep: 15, 30, 45 and 60 degrees
- Initial model: 2D periodic unit cell
- Primary solver: Meep FDTD

## Output metrics

- Spectral reflectance (R)
- Spectral transmittance (T)
- Energy conservation error
- Solar-spectrum-weighted transmittance improvement

## Guardrails

- Raw flux values must not be reported as reflectance or transmittance.
- Every design must use a reference normalization simulation.
- A result at one wavelength must not be reported as total power gain.
- Electrical power improvement must not be claimed until the optical
  result is connected to Solcore.
- Simulation results are not a substitute for laboratory or field validation.

## Out of scope for v0.1

- Final material selection
- Manufacturing process
- Long-term UV and moisture durability
- Mechanical loading and wind resistance
- Environmental safety certification
- Field-tested electricity gain