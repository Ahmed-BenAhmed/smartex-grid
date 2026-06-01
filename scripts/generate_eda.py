"""
Generate EDA reports for London, UCI, and the merged prepared datasets.

Outputs:
    reports/eda/london_eda.md
    reports/eda/uci_eda.md
    reports/eda/merged_eda.md
    reports/eda/figures/*.png
    data/processed/merged_meter_readings.csv
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns


ROOT = Path(__file__).resolve().parents[1]
PROCESSED_DIR = ROOT / "data" / "processed"
REPORT_DIR = ROOT / "reports" / "eda"
FIGURE_DIR = REPORT_DIR / "figures"


def markdown_table(rows: list[tuple[str, object]], headers: tuple[str, str] = ("Metric", "Value")) -> str:
    lines = [f"| {headers[0]} | {headers[1]} |", "|---|---:|"]
    for key, value in rows:
        lines.append(f"| {key} | {value} |")
    return "\n".join(lines)


def read_dataset(path: Path, max_rows: int | None) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Missing {path}. Run `make prepare-data` first.")

    nrows = None if max_rows is None or max_rows <= 0 else max_rows
    df = pd.read_csv(path, nrows=nrows)
    df["time"] = pd.to_datetime(df["time"], errors="coerce")
    df["kwh"] = pd.to_numeric(df["kwh"], errors="coerce")
    df["is_anomaly"] = df["is_anomaly"].astype(str).str.lower().isin(["true", "1", "yes"])
    return df.dropna(subset=["time", "meter_id", "kwh"]).sort_values(["meter_id", "time"])


def write_merged_csv(paths: list[Path], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as out:
        writer = None
        for path in paths:
            with path.open("r", newline="", encoding="utf-8") as handle:
                reader = csv.DictReader(handle)
                if writer is None:
                    writer = csv.DictWriter(out, fieldnames=reader.fieldnames)
                    writer.writeheader()
                for row in reader:
                    writer.writerow(row)


def save_histogram(df: pd.DataFrame, name: str) -> str:
    path = FIGURE_DIR / f"{name}_kwh_distribution.png"
    plt.figure(figsize=(10, 5))
    sns.histplot(df["kwh"], bins=80, kde=True)
    plt.title(f"{name.upper()} kWh distribution")
    plt.xlabel("kWh")
    plt.ylabel("count")
    plt.tight_layout()
    plt.savefig(path, dpi=150)
    plt.close()
    return path.resolve().as_posix()


def save_hourly_profile(df: pd.DataFrame, name: str) -> str:
    path = FIGURE_DIR / f"{name}_hourly_profile.png"
    hourly_df = df.assign(hour=df["time"].dt.hour)
    plt.figure(figsize=(10, 5))
    if "source" in hourly_df.columns and hourly_df["source"].nunique() > 1:
        profile = hourly_df.groupby(["source", "hour"], as_index=False)["kwh"].mean()
        sns.lineplot(data=profile, x="hour", y="kwh", hue="source", marker="o")
        plt.legend(title="source")
    else:
        profile = hourly_df.groupby("hour", as_index=False)["kwh"].mean()
        sns.lineplot(data=profile, x="hour", y="kwh", marker="o", color="#1f77b4")
    plt.title(f"{name.upper()} average consumption by hour")
    plt.xlabel("hour of day")
    plt.ylabel("average kWh")
    plt.xticks(range(0, 24, 2))
    plt.tight_layout()
    plt.savefig(path, dpi=150)
    plt.close()
    return path.resolve().as_posix()


def save_daily_total(df: pd.DataFrame, name: str) -> str:
    path = FIGURE_DIR / f"{name}_daily_total.png"
    daily = (
        df.set_index("time")
        .groupby("meter_id")["kwh"]
        .resample("1D")
        .sum()
        .reset_index()
        .rename(columns={"kwh": "daily_kwh"})
    )

    meter_count = daily["meter_id"].nunique()
    if meter_count > 12:
        top_meters = daily.groupby("meter_id")["daily_kwh"].sum().nlargest(12).index
        daily = daily[daily["meter_id"].isin(top_meters)]

    plt.figure(figsize=(12, 5))
    sns.lineplot(data=daily, x="time", y="daily_kwh", hue="meter_id", alpha=0.75)
    plt.legend(title="meter_id", bbox_to_anchor=(1.02, 1), loc="upper left")
    plt.title(f"{name.upper()} daily consumption totals")
    plt.xlabel("date")
    plt.ylabel("daily kWh")
    plt.tight_layout()
    plt.savefig(path, dpi=150)
    plt.close()
    return path.resolve().as_posix()


def save_source_boxplot(df: pd.DataFrame, name: str) -> str | None:
    if "source" not in df.columns or df["source"].nunique() < 2:
        return None
    path = FIGURE_DIR / f"{name}_source_boxplot.png"
    sample = df.sample(min(len(df), 50_000), random_state=42)
    plt.figure(figsize=(10, 5))
    sns.boxplot(data=sample, x="source", y="kwh", hue="source", showfliers=False, legend=False)
    plt.title("Merged kWh distribution by source")
    plt.xlabel("source")
    plt.ylabel("kWh")
    plt.tight_layout()
    plt.savefig(path, dpi=150)
    plt.close()
    return path.resolve().as_posix()


def detect_candidate_spikes(df: pd.DataFrame) -> pd.DataFrame:
    def mark(group: pd.DataFrame) -> pd.DataFrame:
        q1 = group["kwh"].quantile(0.25)
        q3 = group["kwh"].quantile(0.75)
        iqr = q3 - q1
        threshold = q3 + 3 * iqr
        group = group.copy()
        group["candidate_spike"] = group["kwh"] > threshold
        return group

    return df.groupby("meter_id", group_keys=False).apply(mark, include_groups=False)


def summarize_dataset(df: pd.DataFrame) -> list[tuple[str, object]]:
    candidate_spikes = detect_candidate_spikes(df)
    duplicate_rows = df.duplicated(subset=["time", "meter_id"]).sum()
    time_min = df["time"].min()
    time_max = df["time"].max()
    duration_days = (time_max - time_min).total_seconds() / 86_400 if len(df) else 0

    return [
        ("Rows analyzed", f"{len(df):,}"),
        ("Meters", f"{df['meter_id'].nunique():,}"),
        ("Sources", ", ".join(sorted(df["source"].dropna().unique())) if "source" in df else "n/a"),
        ("Start time", time_min),
        ("End time", time_max),
        ("Duration days", f"{duration_days:,.2f}"),
        ("Duplicate meter-time rows", f"{duplicate_rows:,}"),
        ("Missing kWh after cleaning", f"{df['kwh'].isna().sum():,}"),
        ("Mean kWh", f"{df['kwh'].mean():.6f}"),
        ("Median kWh", f"{df['kwh'].median():.6f}"),
        ("Std kWh", f"{df['kwh'].std():.6f}"),
        ("Min kWh", f"{df['kwh'].min():.6f}"),
        ("Max kWh", f"{df['kwh'].max():.6f}"),
        ("Candidate spikes, IQR rule", f"{candidate_spikes['candidate_spike'].sum():,}"),
    ]


def top_meter_table(df: pd.DataFrame) -> str:
    meter_stats = (
        df.groupby("meter_id")
        .agg(rows=("kwh", "size"), mean_kwh=("kwh", "mean"), total_kwh=("kwh", "sum"), max_kwh=("kwh", "max"))
        .sort_values("total_kwh", ascending=False)
        .head(10)
        .reset_index()
    )
    lines = ["| meter_id | rows | mean_kwh | total_kwh | max_kwh |", "|---|---:|---:|---:|---:|"]
    for row in meter_stats.itertuples(index=False):
        lines.append(f"| {row.meter_id} | {row.rows:,} | {row.mean_kwh:.6f} | {row.total_kwh:.3f} | {row.max_kwh:.3f} |")
    return "\n".join(lines)


DATASET_CONTEXT = {
    "london": {
        "description": (
            "The London Smart Meters dataset contains half-hourly electricity consumption readings "
            "from residential smart meters in London. In this project it is normalized to one row per "
            "meter timestamp with kWh consumption, anomaly placeholder, and source label."
        ),
        "contribution": (
            "This is the main project dataset because it has many households and enough history for "
            "source-level hourly and daily warehouse aggregates, LSTM/Prophet forecasting, anomaly "
            "evaluation, and Grafana load dashboards."
        ),
    },
    "uci": {
        "description": (
            "The UCI Individual Household Electric Power Consumption dataset contains one-minute "
            "measurements from a single household, including active power, reactive power, voltage, "
            "current intensity, and sub-metering values. The prepared project file converts active "
            "power into kWh per minute for the common meter schema."
        ),
        "contribution": (
            "This dataset is useful as a small validation dataset. It allows fast ingestion tests, "
            "schema checks, anomaly rule experiments, and quick model iterations before running the "
            "larger London workload."
        ),
    },
    "merged": {
        "description": (
            "The merged dataset combines the normalized London Smart Meters rows and UCI household "
            "rows into one common schema: time, meter_id, kwh, is_anomaly, and source."
        ),
        "contribution": (
            "The merged view validates that the pipeline can handle multiple public sources with "
            "different granularities. It is useful for testing source-aware preprocessing, resampling, "
            "warehouse aggregation, and dashboards that compare consumption behavior across datasets."
        ),
    },
}


FIGURE_INSIGHTS = {
    "kwh_distribution": (
        "Shows how consumption values are distributed. A long right tail indicates occasional high-load "
        "periods, which are important candidates for peak detection and anomaly thresholds."
    ),
    "hourly_profile": (
        "Shows the average consumption by hour of day. Morning or evening peaks reveal daily routines "
        "and help choose useful temporal features for forecasting models."
    ),
    "daily_total": (
        "Shows total daily consumption over time. Stable bands suggest regular behavior, while sudden "
        "jumps, drops, or gaps point to seasonality, missing data, unusual demand, or meter-specific changes."
    ),
    "source_boxplot": (
        "Compares kWh distributions by source. Large scale differences show why source-aware normalization "
        "or resampling is needed before training a model on the merged dataset."
    ),
}


def color_meaning(name: str, figure: str, df: pd.DataFrame) -> str:
    key = figure_key(figure)
    if key == "daily_total":
        meter_count = df["meter_id"].nunique()
        if meter_count > 12:
            return "Each color represents one of the 12 meters with the highest total consumption in the analyzed sample."
        return "Each color represents a different meter_id, so the lines compare daily load behavior between meters."
    if key == "hourly_profile" and "source" in df.columns and df["source"].nunique() > 1:
        return "Each color represents a dataset source, making it possible to compare London and UCI hourly patterns."
    if key == "source_boxplot":
        return "Each color/category represents a dataset source."
    return "The figure uses one color only, so color does not encode a category; the shape of the curve or bars is the important signal."


def figure_key(figure: str) -> str:
    stem = Path(figure).stem
    for key in FIGURE_INSIGHTS:
        if stem.endswith(key):
            return key
    return stem


def dataset_context_section(name: str) -> list[str]:
    context = DATASET_CONTEXT[name]
    return [
        "## Dataset Description",
        "",
        context["description"],
        "",
        "## Contribution to the Project",
        "",
        context["contribution"],
        "",
    ]


def write_report(df: pd.DataFrame, name: str, title: str) -> Path:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    FIGURE_DIR.mkdir(parents=True, exist_ok=True)

    figures = [
        save_histogram(df, name),
        save_hourly_profile(df, name),
        save_daily_total(df, name),
    ]
    source_boxplot = save_source_boxplot(df, name)
    if source_boxplot:
        figures.append(source_boxplot)

    summary = summarize_dataset(df)
    path = REPORT_DIR / f"{name}_eda.md"
    content = [
        f"# {title}",
        "",
        *dataset_context_section(name),
        "## Summary",
        "",
        markdown_table(summary),
        "",
        "## Top Meters by Total Consumption",
        "",
        top_meter_table(df),
        "",
        "## Figures",
        "",
    ]
    for figure in figures:
        label = Path(figure).stem.replace("_", " ")
        insight = FIGURE_INSIGHTS.get(figure_key(figure), "This figure supports visual inspection of the dataset.")
        colors = color_meaning(name, figure, df)
        content.extend(
            [
                f"### {label.title()}",
                "",
                f"![{label}]({figure})",
                "",
                f"**Color meaning:** {colors}",
                "",
                f"**Insight:** {insight}",
                "",
            ]
        )

    path.write_text("\n".join(content), encoding="utf-8")
    print(f"[eda] wrote {path}")
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate EDA reports for prepared smart-grid datasets.")
    parser.add_argument("--max-rows", type=int, default=500_000, help="Rows loaded per dataset; use 0 for all rows.")
    args = parser.parse_args()

    london_path = PROCESSED_DIR / "london_meter_readings.csv"
    uci_path = PROCESSED_DIR / "uci_meter_readings.csv"
    merged_path = PROCESSED_DIR / "merged_meter_readings.csv"

    write_merged_csv([london_path, uci_path], merged_path)
    print(f"[eda] wrote merged CSV {merged_path}")

    max_rows = None if args.max_rows <= 0 else args.max_rows
    london = read_dataset(london_path, max_rows)
    uci = read_dataset(uci_path, max_rows)
    merged = pd.concat([london, uci], ignore_index=True).sort_values(["source", "meter_id", "time"])

    write_report(london, "london", "London Smart Meters EDA")
    write_report(uci, "uci", "UCI Household Power EDA")
    write_report(merged, "merged", "Merged London + UCI EDA")


if __name__ == "__main__":
    main()
