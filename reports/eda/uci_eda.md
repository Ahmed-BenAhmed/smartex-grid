# UCI Household Power EDA

## Dataset Description

The UCI Individual Household Electric Power Consumption dataset contains one-minute measurements from a single household, including active power, reactive power, voltage, current intensity, and sub-metering values. The prepared project file converts active power into kWh per minute for the common meter schema.

## Contribution to the Project

This dataset is useful as a small validation dataset. It allows fast ingestion tests, schema checks, anomaly rule experiments, and quick model iterations before running the larger London workload.

## Summary

| Metric | Value |
|---|---:|
| Rows analyzed | 100,000 |
| Meters | 1 |
| Sources | uci_household_power |
| Start time | 2006-12-16 17:24:00 |
| End time | 2007-02-24 04:11:00 |
| Duration days | 69.45 |
| Duplicate meter-time rows | 0 |
| Missing kWh after cleaning | 0 |
| Mean kWh | 0.027438 |
| Median kWh | 0.023600 |
| Std kWh | 0.022396 |
| Min kWh | 0.003233 |
| Max kWh | 0.156833 |
| Candidate spikes, IQR rule | 29 |

## Top Meters by Total Consumption

| meter_id | rows | mean_kwh | total_kwh | max_kwh |
|---|---:|---:|---:|---:|
| UCI_HOUSEHOLD_001 | 100,000 | 0.027438 | 2743.759 | 0.157 |

## Figures

### Uci Kwh Distribution

![uci kwh distribution](C:/Users/21260/IdeaProjects/smartex-grid/reports/eda/figures/uci_kwh_distribution.png)

**Color meaning:** The figure uses one color only, so color does not encode a category; the shape of the curve or bars is the important signal.

**Insight:** Shows how consumption values are distributed. A long right tail indicates occasional high-load periods, which are important candidates for peak detection and anomaly thresholds.

### Uci Hourly Profile

![uci hourly profile](C:/Users/21260/IdeaProjects/smartex-grid/reports/eda/figures/uci_hourly_profile.png)

**Color meaning:** The figure uses one color only, so color does not encode a category; the shape of the curve or bars is the important signal.

**Insight:** Shows the average consumption by hour of day. Morning or evening peaks reveal daily routines and help choose useful temporal features for forecasting models.

### Uci Daily Total

![uci daily total](C:/Users/21260/IdeaProjects/smartex-grid/reports/eda/figures/uci_daily_total.png)

**Color meaning:** Each color represents a different meter_id, so the lines compare daily load behavior between meters.

**Insight:** Shows total daily consumption over time. Stable bands suggest regular behavior, while sudden jumps, drops, or gaps point to seasonality, missing data, unusual demand, or meter-specific changes.
