# SolarFlow Phase 1.6B — measured-module SR proxy ensemble

## Purpose

Phase 1.6B tests whether the Phase 1.6A optical conclusion changes when the
retrofit spectrum is weighted by measured spectral-response shapes from
commercial mono-Si PERC modules.

This phase closes only one part of the optical-to-electrical gap. It does **not**
replace an EQE/SR measurement of the target JA Solar JAM72D10-405/MB module and
does not produce validated module power.

## Data basis

The input is the processed DuraMAT/Sandia module spectral-response library:

- DuraMAT dataset: <https://datahub.duramat.org/dataset/module-sr-library>
- DuraMAT resource: <https://datahub.duramat.org/dataset/module-sr-library/resource/1004264a-d8d6-4eaf-a0de-4efff68d2fc6>
- OSTI record and DOI: <https://www.osti.gov/biblio/2204677>, DOI
  `10.21948/2204677`
- Sandia processing report: <https://www.osti.gov/servlets/purl/2293575>

The OSTI record describes one stored module from each of 12 commercial module
types being sent to NREL for module quantum-efficiency measurement. The Sandia
report states that the NREL measurements used 40 wavelengths from 310 to
1195 nm and 60–384 locations per module. Sandia used a median response, found
mean-versus-median differences below 1%, converted median QE to spectral
response, normalized it, added zero endpoints at 300 and 1200 nm, and applied
monotonic cubic interpolation at 5 nm spacing.

Phase 1.6B uses all three proposed mono-Si PERC references as an ensemble:

| Proxy | NetCDF group | Role |
|---|---|---|
| Itek Energy IT-360-SE72 | `Itek_360_mono` | architecture-nearest reference proposed by the external review |
| QCells Q.PEAK-G4.1 300 | `Qcells_300_mono` | independent manufacturer/reference construction |
| Mission Solar MSE300SQ5T | `Mission_300_mono` | independent manufacturer/reference construction |

No single proxy is declared equivalent to JAM72D10-405/MB. The Itek module is
also a monofacial/single-glass reference, whereas the target is reported as a
bifacial double-glass module.

## Calculation

For each Phase 1.6A optical case and each normalized SR proxy, the program
calculates

\[
g_{SR}=100\left[
\frac{\int E_{AM1.5G}(\lambda)SR_p(\lambda)
\frac{T_{retro}(\lambda)}{T_{base}(\lambda)}d\lambda}
{\int E_{AM1.5G}(\lambda)SR_p(\lambda)d\lambda}-1\right].
\]

Using the ratio `T_retro/T_base` treats the measured module SR curve as the
baseline spectral response and applies only the modeled front-surface change.
It avoids multiplying the proxy module's already-embedded front optics by the
Phase 1.6A baseline a second time.

The resulting quantity is named:

> relative normalized-photocurrent proxy gain

Because each SR curve is normalized, multiplying an SR curve by any constant
does not change this relative result. Absolute A/W, Isc, Imp, Pmax, efficiency,
and annual yield cannot be recovered.

## Installation and input

Activate the project environment and install the NetCDF reader if needed:

```bash
conda activate solarflow-full
python -m pip install xarray h5netcdf
```

Place the actual NetCDF/HDF5 resource at:

```text
data/external/sr_library.nc
```

Do not commit that file. The DuraMAT resource currently displays `No License
Provided`, and `data/external/.gitignore` excludes downloaded files. Retain the
source URL and let the program record the local file SHA-256 in the result JSON.

The former direct-download link may return an HTML migration page. Confirm the
file type before running:

```bash
file data/external/sr_library.nc
```

## Run sequence

First run the dependency-free calculation tests:

```bash
python -m product1.analysis.phase_1_6b_proxy_sr --self-test
```

Then run the complete ensemble:

```bash
python -m product1.analysis.phase_1_6b_proxy_sr
```

An alternate local dataset path can be supplied without changing the config:

```bash
python -m product1.analysis.phase_1_6b_proxy_sr \
  --dataset /absolute/path/to/sr_library.nc
```

## Outputs

- `product1/results/phase_1_6b_proxy_sr.csv`
- `product1/results/phase_1_6b_proxy_sr_summary.json`
- `product1/results/figures/phase_1_6b_proxy_gain_distribution.png`
- `product1/results/figures/phase_1_6b_nominal_spectral_weighting.png`

The CSV contains every optical-case/proxy combination. The JSON reports each
proxy separately and also reports the across-proxy minimum, median, and maximum.
The conservative grid gate requires every proxy to pass; the code never selects
only the most favorable reference.

## Approved language

> Under the conditional Phase 1.6A optical-stack assumptions, the modeled
> retrofit spectral modifier was reweighted using normalized median spectral
> response measured on three commercial mono-Si PERC reference modules. The
> result is a relative photocurrent-proxy sensitivity ensemble, not a
> JAM72D10-405/MB electrical-power measurement or prediction.

## Avoid

- “The target module gains X% electrical power.”
- “The Itek module is equivalent to JAM72D10-405/MB.”
- “The proxy ensemble validates field performance.”
- “The normalized SR data predict absolute Isc or Pmax.”
- Any claim that grid fractions are probabilities or confidence levels.

## Remaining research gates

1. Measure or obtain EQE/SR for the actual target module or a documented sample
   with the same cell and front-stack construction.
2. Measure baseline and retrofit I–V curves under a calibrated solar simulator.
3. Replace constant optical properties with measured candidate and module
   `n(lambda)`/`k(lambda)` data.
4. Validate wet-state optics, haze, adhesion, durability, thermal behavior, and
   annual energy before a field-performance claim.
