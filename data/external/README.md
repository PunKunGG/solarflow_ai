# External spectral-response data

Phase 1.6B expects the DuraMAT/Sandia processed module spectral-response
library at:

```text
data/external/sr_library.nc
```

Obtain the NetCDF resource from the DuraMAT dataset page:

- Dataset: <https://datahub.duramat.org/dataset/module-sr-library>
- Resource record: <https://datahub.duramat.org/dataset/module-sr-library/resource/1004264a-d8d6-4eaf-a0de-4efff68d2fc6>
- OSTI record and DOI: <https://www.osti.gov/biblio/2204677>
- Processing method: <https://www.osti.gov/servlets/purl/2293575>

The former direct-download URL may redirect to an HTML migration page. Save
only the actual NetCDF/HDF5 resource. Before running the analysis, check that
the file is not HTML:

```bash
file data/external/sr_library.nc
```

The output should identify NetCDF or HDF5 data. The Phase 1.6B program also
rejects HTML and records the file size and SHA-256 digest in its summary.

The DuraMAT resource page currently displays **No License Provided**. For that
reason, the local `.gitignore` excludes downloaded data. Do not force-add or
redistribute `sr_library.nc` until the data owner clarifies reuse terms.

The following processed groups are used as an ensemble:

- `Itek_360_mono`
- `Qcells_300_mono`
- `Mission_300_mono`

They are measured mono-Si PERC reference modules, not measurements of the JA
Solar JAM72D10-405/MB target. Their normalized SR curves support comparative
spectral weighting only; they cannot establish absolute current or power.
