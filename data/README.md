# Project Datasets

This project uses one main smart-meter dataset and one lightweight validation dataset.

## Main Dataset

### London Smart Meters, cleaned Zenodo version

- Source: https://zenodo.org/records/4656091
- Size: 219.7 MB compressed
- Granularity: 30 minutes
- Coverage: 5,560 household time series, November 2011 to February 2014
- Role: primary dataset for clustering, forecasting, hourly/daily warehouse aggregates, and Grafana dashboards.

### Morocco High-Resolution Smart Meters (UCI)

- Source: https://archive.ics.uci.edu/dataset/1158/high-resolution+load+dataset+from+smart+meters+across+various+cities+in+morocco
- Size: ~21 MB (Data Morocco.xlsx in UCI archive) — may vary depending on the archive
- Granularity: mixed (10 minutes for some cities, 30 minutes for others)
- Coverage: Laâyoune, Boujdour, Marrakech, Foum Eloued — domestic and industrial profiles
- Role: recommended primary dataset for projects targeting Morocco; can be resampled to 15-min, hourly, and daily granularities.

### Nigeria Energy & Utilities Household Smart Meter

- Source: https://huggingface.co/datasets/electricsheepafrica/nigerian_energy_and_utilities_household_smart_meter
- Size: 200,000 rows
- Granularity: hourly in the current mirror
- Coverage: 10 DisCos, feeder-level and tariff-band metadata
- Role: secondary African dataset for validation, clustering, tariff analysis, and anomaly experiments.

## Test Dataset

### UCI Individual Household Electric Power Consumption

- Source: https://archive.ics.uci.edu/dataset/235/individual+household+electric+power+consumption
- Size: 19.7 MB compressed, 126.8 MB extracted
- Granularity: 1 minute
- Coverage: one household, December 2006 to November 2010
- Role: small dataset for ingestion tests, anomaly logic, and fast model experiments.

## Optional Anomaly Dataset

### REFIT Electrical Load Measurements

- Source: https://pureportal.strath.ac.uk/en/datasets/refit-electrical-load-measurements/
- Size: 368 MB cleaned, 666 MB raw
- Granularity: 8 seconds
- Coverage: 20 UK households with aggregate and appliance-level readings
- Role: optional dataset for detailed anomaly and appliance-level tests.

## Local Layout

Downloaded archives are stored in `data/raw/`.

Prepared CSV files are stored in `data/processed/` with this common schema:

```csv
time,meter_id,kwh,is_anomaly,source
```

The `is_anomaly` field is initialized to `false` for public datasets without labels. The ML pipeline can later populate anomaly events from residuals or statistical rules.

## Conversion Assumptions

- Morocco non-Marrakech files are converted from amperes to estimated kW using `Estimated_kW = 230 × I × 0.9 / 1000 = 0.207 × I`.
- This is an approximation and should be revisited if more precise voltage or power-factor metadata becomes available.
