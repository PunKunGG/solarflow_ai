# SolarFlow AI - Phase 1.6A Assumption and Sensitivity Register

## Conditional optical uncertainty envelope

**Status:** numerical assumption study only  
**Depends on:** Phase 1.5 research record and the locked simplified active/primer stack  
**Does not produce:** validated electrical gain, annual-energy gain, material selection, or prototype specification

---

## 1. Why Phase 1.6A exists

Phase 1.5 established that the exact front optical stack, module EQE/SR, and
candidate-material spectral constants are not available from sufficiently
authoritative public sources. That prevents a real-module-calibrated prediction.

Phase 1.6A asks a narrower question that can be answered without inventing
measurements:

> Does the modeled optical benefit remain positive throughout a clearly defined
> grid of uncertain but traceable input assumptions?

This is an uncertainty-envelope study. It does not estimate the probability
that any scenario occurs in the installed module.

---

## 2. Fixed scientific language

Use:

> Under the defined Phase 1.6A assumption grid, the simplified model retains or
> loses optical margin in the reported fraction of deterministic cases.

Do not use:

- "The real module will gain X%."
- "The coating increases electrical power by X%."
- "The study has X% confidence."
- "The tested refractive indices are the factory coating."
- "The extinction-coefficient sweep represents a selected material."

---

## 3. Source-of-truth stack

The current engineering checkpoint is:

```text
Air
-> active optical layer: n = 1.092934, d = 116.736 nm
-> release primer: n = 1.20, d = 50 nm
-> assumed existing AR: n = 1.28, d = 100 nm
-> representative cover glass: n = 1.52
```

The active/primer stack produced approximately `+0.6667%` AM1.5G-weighted
relative optical gain in the simplified nominal model. Previous convergence,
tolerance, and angle/polarization checks remain numerical checks of that model,
not measurements of the real module.

---

## 4. Parameter register

| Parameter | Phase 1.6A values | Classification | Interpretation |
|---|---:|---|---|
| Existing AR index | 1.25, 1.28, 1.30, 1.35 | ASSUMED RANGE | Exact factory `n(lambda)` is unknown |
| Existing AR thickness | 80, 100, 120, 140 nm | ASSUMED RANGE | Exact factory thickness is unknown |
| Active-layer index | 1.08-1.15 plus 1.092934 | MIXED | Literature-precedent envelope plus optimizer point |
| Active-layer thickness | 100-135 nm | ASSUMED ENGINEERING RANGE | Tolerance around the 116.736 nm point |
| Active-layer `k` | 0, 1e-5, 1e-4, 1e-3 | ASSUMED STRESS RANGE | Tests absorption sensitivity; not measured material data |
| Primer index | 1.15, 1.20, 1.25 | ASSUMED ENGINEERING RANGE | Inherited from the passed tolerance screen |
| Primer thickness | 30, 50, 75 nm | ASSUMED ENGINEERING RANGE | No fabrication process has been selected |
| Glass index | 1.52 | REPRESENTATIVE CONSTANT | Not the measured dispersion of installed glass |

The active-index envelope is supported only as a material-class precedent.
Published hollow/porous silica work reports fabricated low-index films around
the range used here. It does not supply SolarFlow's exact `n(lambda)`,
`k(lambda)`, durability, adhesion, or wet-state behavior.

---

## 5. Model and comparison rule

For every existing-AR scenario, the script compares two stacks using the same
AR assumptions:

```text
Baseline: air -> existing AR -> glass

Retrofit: air -> active layer -> primer -> existing AR -> glass
```

The response is evaluated from 300 to 1200 nm and weighted with Solcore's
standard AM1.5G spectral power density.

The primary metric is:

```text
relative optical gain (%)
  = 100 * (retrofit transmitted power - baseline transmitted power)
        / baseline transmitted power
```

The scenario grid uses constant `n` and `k` within each run. It therefore tests
parameter sensitivity, not real spectral dispersion.

---

## 6. Gates

- Positive-gain gate: relative optical gain greater than `0.00%`
- Provisional-margin gate: relative optical gain at least `+0.10%`
- Lossless subset: active-layer `k = 0`
- Absorption-stress subset: active-layer `k > 0`

The JSON summary must report:

- total deterministic cases
- minimum, 5th percentile, median, 95th percentile, and maximum gain
- count and fraction passing each gate
- lossless-subset results
- absorption-stress-subset results
- worst defined case
- main-effect spread ranking

The pass fraction is only a fraction of the chosen grid. No probability
distribution has been assigned to the unknown physical inputs.

---

## 7. Outputs

```text
product1/results/phase_1_6_optical_sensitivity.csv
product1/results/phase_1_6_optical_sensitivity_summary.json
product1/results/figures/phase_1_6_ar_robustness_heatmap.png
product1/results/figures/phase_1_6_gain_distribution.png
```

The heatmap reports the worst case at each assumed existing-AR grid point. The
distribution figure shows the deterministic scenario spread and project gates.

---

## 8. Execution

From the repository root:

```bash
conda activate solarflow-full
python -m product1.analysis.phase_1_6_optical_sensitivity --self-test
python -m product1.analysis.phase_1_6_optical_sensitivity
```

Optional explicit configuration:

```bash
python -m product1.analysis.phase_1_6_optical_sensitivity \
  --config configs/phase_1_6_sensitivity.yaml
```

---

## 9. Decision boundary after the run

Phase 1.6A may support one of these decisions:

1. **Robust within the defined grid** - every defined case retains the
   provisional margin.
2. **Conditionally positive** - some cases pass and some fail; use the output to
   identify which unknown measurements dominate the decision.
3. **Not robust within the defined grid** - at least one defined region loses
   positive gain; do not freeze the architecture.

None of these decisions authorizes an electrical or field-performance claim.

---

## 10. Deferred Phase 1.6B

An EQE/SR proxy envelope may be added later as a separately labeled exploratory
study. It must use multiple traceable silicon spectral-response datasets and
must never label a generic curve as JAM72D10-405/MB data.

No modeled Pmax value becomes project evidence until the actual module response
and measured baseline I-V data are available.
