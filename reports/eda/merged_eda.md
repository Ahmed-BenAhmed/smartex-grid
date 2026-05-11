# Merged London + UCI EDA

## Dataset Description

The merged dataset combines the normalized London Smart Meters rows and UCI household rows into one common schema: time, meter_id, kwh, is_anomaly, and source.

## Contribution to the Project

The merged view validates that the pipeline can handle multiple public sources with different granularities. It is useful for testing source-aware preprocessing, resampling, warehouse aggregation, and dashboards that compare consumption behavior across datasets.

## Summary

| Metric | Value |
|---|---:|
| Rows analyzed | 200,000 |
| Meters | 6 |
| Sources | london_smart_meters, uci_household_power |
| Start time | 2006-12-16 17:24:00 |
| End time | 2014-02-24 23:30:01 |
| Duration days | 2,627.25 |
| Duplicate meter-time rows | 0 |
| Missing kWh after cleaning | 0 |
| Mean kWh | 0.302394 |
| Median kWh | 0.061067 |
| Std kWh | 0.552913 |
| Min kWh | 0.003233 |
| Max kWh | 5.250000 |
| Candidate spikes, IQR rule | 2,300 |

## Top Meters by Total Consumption

| meter_id | rows | mean_kwh | total_kwh | max_kwh |
|---|---:|---:|---:|---:|
| T3 | 19,680 | 1.517753 | 29869.383 | 5.250 |
| T2 | 39,072 | 0.350727 | 13703.593 | 3.516 |
| T1 | 23,904 | 0.252007 | 6023.982 | 2.994 |
| T4 | 10,656 | 0.484944 | 5167.561 | 4.508 |
| T5 | 6,688 | 0.444148 | 2970.463 | 3.642 |
| UCI_HOUSEHOLD_001 | 100,000 | 0.027438 | 2743.759 | 0.157 |

## Figures

### Merged Kwh Distribution

![merged kwh distribution](C:/Users/21260/IdeaProjects/smartex-grid/reports/eda/figures/merged_kwh_distribution.png)

**Color meaning:** The figure uses one color only, so color does not encode a category; the shape of the curve or bars is the important signal.

**Insight:** Shows how consumption values are distributed. A long right tail indicates occasional high-load periods, which are important candidates for peak detection and anomaly thresholds.

### Merged Hourly Profile

![merged hourly profile](C:/Users/21260/IdeaProjects/smartex-grid/reports/eda/figures/merged_hourly_profile.png)

**Color meaning:** Each color represents a dataset source, making it possible to compare London and UCI hourly patterns.

**Insight:** Shows the average consumption by hour of day. Morning or evening peaks reveal daily routines and help choose useful temporal features for forecasting models.

### Merged Daily Total

![merged daily total](C:/Users/21260/IdeaProjects/smartex-grid/reports/eda/figures/merged_daily_total.png)

**Color meaning:** Each color represents a different meter_id, so the lines compare daily load behavior between meters.

**Insight:** Shows total daily consumption over time. Stable bands suggest regular behavior, while sudden jumps, drops, or gaps point to seasonality, missing data, unusual demand, or meter-specific changes.

### Merged Source Boxplot

![merged source boxplot](C:/Users/21260/IdeaProjects/smartex-grid/reports/eda/figures/merged_source_boxplot.png)

**Color meaning:** Each color/category represents a dataset source.

**Insight:** Compares kWh distributions by source. Large scale differences show why source-aware normalization or resampling is needed before training a model on the merged dataset.
