# SolarFlow AI — Phase 1.5 Research Record
## Actual Module Optical + Spectral Characterization — Desk/Document Research Boundary

**Research date:** 1 September 2026  
**Reference module:** JA Solar JAM72D10-405/MB (390–410/MB family)  
**Research rule:** Do not invent measurements or substitute generic values for actual-module data.

---

# 1. Phase objective

Phase 1.5 is restricted to the evidence that can be established now from public documents and published literature.

The phase is considered successful only when we can clearly distinguish:

- **KNOWN / DOCUMENTED**
- **SIMULATION**
- **LITERATURE PRECEDENT**
- **INFERENCE**
- **UNKNOWN / MEASUREMENT REQUIRED**

No electrical gain or annual-energy gain is calculated in this phase.

---

# 2. Actual module identity — CLOSED WITH DOCUMENTARY EVIDENCE

JA Solar's official JAM72D10 390–410/MB documentation identifies the 405 W member as:

- Rated maximum power: 405 W
- Voc: 49.82 V
- Vmp: 42.28 V
- Isc: 10.20 A
- Imp: 9.58 A
- Module efficiency: 19.8%
- Cells: 144 (6 × 24)
- Module dimensions: 2037 ± 2 mm × 1005 ± 2 mm × 30 ± 1 mm
- Front glass / back glass: 2.0 mm / 2.0 mm
- Cell: mono
- Module family: bifacial, half-cell, MBB / PERCIUM
- Operating temperature: −40 °C to +85 °C
- NOCT: 45 ± 2 °C
- Bifaciality: 70% ±10% in the 2020 390–410/MB/1500V sheet

Source: JA Solar official product documentation.

### Important interpretation

These values establish the module family and external construction class, but they do NOT reveal the exact optical formulation of the front-surface anti-reflective treatment.

---

# 3. Module construction evidence from the JA Solar EPD

The 2022 JA Solar/EPDItaly Environmental Product Declaration covers the JAM72D10-XXX/MB family.

For JAM72D10-XXX/MB it reports:

- Tempered glass
- POE (polyolefin elastomer)
- Monocrystalline solar cell
- Silica gel
- Junction box
- Solder
- No polymer backsheet listed for this double-glass family

It also identifies the JAM72D10-XXX/MB family as a bifacial double-glass module family using MBB bifacial PERCIUM cells and half-cell configuration.

### Critical boundary

The EPD is a material-composition document, not an optical-stack specification.

It does NOT provide, at the resolution needed by SolarFlow:

- AR layer chemical composition
- AR layer thickness
- AR n(lambda)
- AR k(lambda)
- surface-roughness distribution
- angular reflectance/transmittance
- module EQE / spectral responsivity

Therefore the exact factory optical stack remains UNKNOWN.

---

# 4. Actual module spectral response — NOT CLOSED

A search was performed for public, model-specific:

- JAM72D10-405/MB EQE
- JAM72D10-405/MB spectral response
- JAM72D10-405/MB spectral responsivity
- JAM72D10-405/MB quantum efficiency

No sufficiently authoritative, model-specific measured spectral-response dataset was located.

### Therefore

    SR_actual(lambda) = UNKNOWN

    EQE_actual(lambda) = UNKNOWN

The datasheet Isc value cannot uniquely reconstruct EQE(lambda). This is an inverse problem: many spectral-response functions can integrate to the same broadband short-circuit current under a given spectrum.

### Research consequence

Do NOT use a generic PERC EQE curve and label it as the actual module response.

The correct next evidence source is:

1. manufacturer-provided spectral response, OR
2. direct measurement of the actual module.

---

# 5. Actual factory optical stack — NOT CLOSED

Public documents verify the double-glass construction and family-level material composition.

However, the exact front optical stack is not documented at the required level.

The current SolarFlow model uses an assumed front AR representation:

    n_AR = 1.28
    d_AR = 100 nm

These must remain:

    STATUS = ASSUMPTION

They are NOT established factory specifications.

### Consequence

The current optimized active layer:

    n_active = 1.092934
    d_active = 116.736 nm

is an optimization result conditional on the assumed baseline stack.

It is not yet the physical optimum for the real JAM72D10-405/MB surface.

---

# 6. Candidate low-index material research — PARTIALLY CLOSED

A significant positive result was found.

## Candidate A — Methylated hollow silica nanoparticles

A peer-reviewed Materials Letters study reports antireflective coatings fabricated from hollow silica nanoparticles modified with methyltriethoxysilane.

Reported refractive-index tuning:

    n ≈ 1.09–1.15

The study also reports hydrophobicity with water contact angle up to approximately 122.5°.

This directly overlaps the SolarFlow optimizer result:

    SolarFlow optimum n ≈ 1.092934

### Classification

- Existence of an n≈1.09 material class: **LITERATURE PRECEDENT**
- Exact SolarFlow formulation: **NOT PROVEN**
- Exact n(lambda) dataset for our candidate: **NOT AVAILABLE**
- Exact k(lambda) dataset for our candidate: **NOT AVAILABLE**
- Long-term PV-module durability: **NOT PROVEN**

Source:
Tao et al., Materials Letters (2016), DOI 10.1016/j.matlet.2016.07.042.

---

# 7. Candidate B — Methylated hollow-silica porous films

A later study reports porous films with:

    n ≈ 1.08–1.14

and describes humidity-resistant antireflective behavior.

This is especially relevant because the physical risk in the SolarFlow design is not whether n≈1.09 can exist; it is whether the low-index porous architecture remains optically and mechanically stable under moisture and abrasion.

### Classification

- n≈1.08–1.14 achievable in fabricated porous films: **LITERATURE PRECEDENT**
- Humidity-resistant behavior demonstrated in laboratory study: **LITERATURE EXPERIMENT**
- 25–30 year module-field durability: **NOT PROVEN**

Source:
Ren et al., Journal of Porous Materials (2018), DOI 10.1007/s10934-017-0420-3.

---

# 8. Candidate C — Graded-index silica architecture

A published study fabricated five-layer graded-index silica nanostructured films.

Reported index progression:

    approximately 1.33 → 1.11

with layer thicknesses of approximately 50 nm in the reported structure.

The study reports broadband/omnidirectional AR performance across approximately 380–1600 nm.

Another published nanostructured silica architecture used index values around:

    1.09 / 1.22 / 1.33

with fabricated films on glass.

### Research implication

The literature supports a real alternative to a single ultra-low-index layer:

    Air
      ↓
    low-n layer
      ↓
    intermediate-n layer
      ↓
    higher-n layer
      ↓
    glass

This may provide a different trade-off between:

- broadband optical performance
- angular response
- achievable material properties
- mechanical robustness

But it has NOT been run through SolarFlow against the actual module stack yet.

Classification: **CANDIDATE ARCHITECTURE / REQUIRES SIMULATION**

---

# 9. Conventional dense SiO2

Published optical-constant data for fused silica give approximately:

    n ~ 1.45–1.47 through the visible/NIR region

with low extinction over the solar range in appropriate datasets.

Therefore dense fused silica cannot simply replace the SolarFlow n≈1.093 active layer.

Classification:

    As direct low-index replacement: NOT ATTRACTIVE
    As part of a graded/hybrid architecture: POSSIBLE

Source examples:
- Malitson 1965 fused-silica dispersion
- Franta et al. 2016 thin-film n,k dataset

---

# 10. MgF2

The RefractiveIndex.INFO database entry based on Dodge (1984) gives MgF2 ordinary/extraordinary refractive-index datasets over 0.2–7 µm.

At visible wavelengths the index is substantially higher than 1.09.

Therefore:

    MgF2 single-layer → not an optical substitute for n≈1.093

but:

    MgF2 + lower-index silica architecture → candidate for re-optimization

Classification: **SECONDARY CANDIDATE**

---

# 11. Why n≈1.093 is physically meaningful but not yet a material selection

The optimizer result:

    n = 1.092934

is close to experimentally fabricated hollow/porous silica index ranges.

This closes an important feasibility question:

> An effective refractive index around 1.09 is physically realizable in published fabricated optical coatings.

However, it does NOT close:

> Can the same material be fabricated on the exact JA Solar glass/AR surface, at 116.736 nm, with the required spectral n(lambda), k(lambda), haze, adhesion, abrasion resistance, humidity stability, and removability?

Those remain open.

---

# 12. Current material model must NOT use

Do not use:

    n(lambda) = 1.092934
    k(lambda) = 0

over the entire simulation range as if this were a measured material.

That would convert a literature-precedent class back into an idealized material.

The correct representation is:

    n = n(lambda, process, porosity, RH, T)

    k = k(lambda, process, porosity, RH, T)

once measured data are available.

---

# 13. Standards confirmed for the eventual measurement handoff

IEC 61853-2:2026 is the current edition of the PV module performance/energy-rating Part 2 standard and explicitly covers:

- spectral responsivity
- incidence angle
- nominal module operating temperature

It is applicable to bifacial PV modules.

IEC 60904-8:2014 covers measurement of spectral responsivity of PV devices, including requirements for series-connected modules.

IEC TS 60904-1-2:2024 + AMD1:2026 covers I-V measurement of bifacial PV devices and applies to complete PV modules.

These are measurement references for the next team, but no laboratory result is claimed here.

---

# 14. Evidence status matrix

| Item | Status | What is actually known |
|---|---|---|
| JAM72D10-405/MB 405 W identity | CLOSED | Official JA Solar documentation |
| 144 half-cell configuration | CLOSED | Official JA Solar documentation |
| Double-glass 2.0/2.0 mm | CLOSED | Official JA Solar documentation |
| POE family-level composition | CLOSED | JA Solar EPD |
| Monocrystalline cell family | CLOSED | JA Solar EPD/data sheet |
| Bifacial architecture | CLOSED | JA Solar documentation |
| Bifaciality reference | CLOSED | JA Solar datasheet |
| Actual EQE/SR of this exact module | OPEN | No authoritative public dataset found |
| Actual factory AR chemistry | OPEN | Not publicly specified |
| Actual AR thickness | OPEN | Not publicly specified |
| Actual AR n(lambda) | OPEN | Not publicly specified |
| Actual AR k(lambda) | OPEN | Not publicly specified |
| n≈1.09 material class exists | CLOSED as literature precedent | Hollow/porous silica literature |
| Exact candidate n(lambda) for SolarFlow | OPEN | Needs candidate-specific data |
| Exact candidate k(lambda) | OPEN | Needs candidate-specific data |
| Candidate humidity dependence | PARTIAL | Laboratory literature exists |
| Long-term module durability | OPEN | Requires testing |
| Actual optical transmission of module | OPEN | Requires measurement |
| Actual angular optical response | OPEN | Requires measurement |
| Electrical gain | OPEN | Must follow spectral-response/electrical coupling |
| Annual energy gain | OPEN | Must wait for later phases |

---

# 15. Research conclusion — Phase 1.5 stopping point

We have reached the maximum scientifically defensible boundary for desk/document research.

## We HAVE closed

1. The actual module family and major construction parameters.
2. The fact that the module is a bifacial double-glass architecture.
3. Family-level material composition.
4. The existence of real fabricated ultra-low-index silica architectures near n≈1.09.
5. The existence of graded-index silica architectures that can use n≈1.1–1.3 ranges.
6. The correct standards framework for the eventual measurements.

## We HAVE NOT closed

1. Actual JAM72D10-405/MB module spectral response.
2. Actual JAM72D10-405/MB EQE.
3. Exact factory AR composition.
4. Exact factory AR thickness.
5. Actual n(lambda), k(lambda) of the factory AR.
6. Candidate coating n(lambda), k(lambda) for the exact film/process we would fabricate.

Therefore the research must STOP HERE rather than move to electrical simulation.

---

# 16. Handoff package for the second research team

The second team should receive this exact evidence statement:

> “SolarFlow's current optical optimization has identified an idealized low-index target near n=1.093 and thickness near 116.7 nm. Published literature demonstrates fabricated porous/hollow silica AR architectures with effective refractive indices around 1.08–1.15, so the target is physically plausible. However, the actual optical stack and spectral response of the reference JAM72D10-405/MB module remain experimentally unverified. No electrical energy gain should be inferred until module spectral responsivity, front optical behavior, and candidate-material n(lambda)/k(lambda) are measured and coupled into the electrical model.”

## Requested experimental evidence

### Module
- spectral responsivity SR(lambda)
- I-V at controlled conditions
- front spectral reflectance R(lambda)
- total/diffuse reflectance if possible
- haze
- angular R/T behavior if possible
- surface roughness

### Optical stack
- ellipsometry where practical
- layer thickness
- n(lambda)
- k(lambda)
- chemical identification where needed

### Candidate material
- n(lambda)
- k(lambda)
- thickness
- haze
- roughness
- humidity dependence
- temperature dependence
- abrasion/adhesion/removal behavior

Once these measurements exist, they become the input boundary for the next stage.

---

# 17. Final decision

**Phase 1.5 is not “failed.” It has reached its natural experimental boundary.**

The correct status is:

    DOCUMENTARY RESEARCH = COMPLETE
    ACTUAL MODULE OPTICAL DATA = PENDING MEASUREMENT
    ACTUAL MODULE SPECTRAL DATA = PENDING MEASUREMENT
    REAL MATERIAL n/k = PENDING MATERIAL CHARACTERIZATION

Therefore:

    DO NOT calculate electrical gain yet.
    DO NOT claim 0.67% optical gain = power gain.
    DO NOT freeze 116.736 nm as the physical prototype.
    DO NOT treat n=1.092934 as a selected commercial material.

The next step belongs to the laboratory/research team once the above measurements are available.
