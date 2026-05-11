# London Smart Meters EDA

## Dataset Description

The London Smart Meters dataset contains half-hourly electricity consumption readings from residential smart meters in London. In this project it is normalized to one row per meter timestamp with kWh consumption, anomaly placeholder, and source label.

## Contribution to the Project

This is the main project dataset because it has many households and enough history for load-profile clustering, hourly and daily warehouse aggregates, LSTM/Prophet forecasting per cluster, and Grafana load dashboards.

## Summary

| Metric | Value |
|---|---:|
| Rows analyzed | 100,000 |
| Meters | 5 |
| Sources | london_smart_meters |
| Start time | 2011-12-04 00:00:01 |
| End time | 2014-02-24 23:30:01 |
| Duration days | 813.98 |
| Duplicate meter-time rows | 0 |
| Missing kWh after cleaning | 0 |
| Mean kWh | 0.577350 |
| Median kWh | 0.272000 |
| Std kWh | 0.678030 |
| Min kWh | 0.014000 |
| Max kWh | 5.250000 |
| Candidate spikes, IQR rule | 2,271 |

## Top Meters by Total Consumption

| meter_id | rows | mean_kwh | total_kwh | max_kwh |
|---|---:|---:|---:|---:|
| T3 | 19,680 | 1.517753 | 29869.383 | 5.250 |
| T2 | 39,072 | 0.350727 | 13703.593 | 3.516 |
| T1 | 23,904 | 0.252007 | 6023.982 | 2.994 |
| T4 | 10,656 | 0.484944 | 5167.561 | 4.508 |
| T5 | 6,688 | 0.444148 | 2970.463 | 3.642 |

## Figures

### London Kwh Distribution

![london kwh distribution](C:/Users/21260/IdeaProjects/smartex-grid/reports/eda/figures/london_kwh_distribution.png)

**Color meaning:** The figure uses one color only, so color does not encode a category; the shape of the curve or bars is the important signal.

**Insight:** Shows how consumption values are distributed. A long right tail indicates occasional high-load periods, which are important candidates for peak detection and anomaly thresholds.

### London Hourly Profile

![london hourly profile](C:/Users/21260/IdeaProjects/smartex-grid/reports/eda/figures/london_hourly_profile.png)

**Color meaning:** The figure uses one color only, so color does not encode a category; the shape of the curve or bars is the important signal.

**Insight:** Shows the average consumption by hour of day. Morning or evening peaks reveal daily routines and help choose useful temporal features for forecasting models.

### London Daily Total

![london daily total](C:/Users/21260/IdeaProjects/smartex-grid/reports/eda/figures/london_daily_total.png)

**Color meaning:** Each color represents a different meter_id, so the lines compare daily load behavior between meters.

**Insight:** Shows total daily consumption over time. Stable bands suggest regular behavior, while sudden jumps, drops, or gaps point to seasonality, missing data, unusual demand, or meter-specific changes.
