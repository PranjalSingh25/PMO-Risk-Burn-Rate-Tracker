import pandas as pd
import numpy as np
import os
import sys
from pathlib import Path

BASE_DIR   = Path(__file__).resolve().parent.parent
RAW_PATH   = BASE_DIR / "data" / "raw_telemetry.csv"
CLEAN_PATH = BASE_DIR / "data" / "clean_telemetry.csv"

def ingest(path: str) -> pd.DataFrame:
    print("\n[1/5] Reading raw telemetry...")
    if not os.path.exists(path):
        sys.exit(f"  File not found: {path}\n  Run 01_generate_data.py first.")
    df = pd.read_csv(path, low_memory=False)
    print(f"  Loaded {len(df):,} rows x {len(df.columns)} columns")
    nulls = df.isnull().sum().sum()
    if nulls:
        print(f"  Found {nulls} null values")
    return df


def clean(df: pd.DataFrame) -> pd.DataFrame:
    print("\n[2/5] Cleaning...")

    original_len = len(df)

    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    invalid_dates = df["date"].isnull().sum()
    if invalid_dates > 0:
        print(f"  Dropping {invalid_dates} rows with bad dates")
        df = df.dropna(subset=["date"])

    df = df.sort_values(["project_id", "date"]).reset_index(drop=True)

    numeric_cols = [
        "actual_daily_spend_usd",
        "hw_cost_actual_usd",
        "labor_hours",
        "shipping_delay_days",
    ]
    for col in numeric_cols:
        null_count = df[col].isnull().sum()
        if null_count > 0:
            df[col] = df.groupby("project_id")[col].transform(
                lambda x: x.fillna(x.median())
            )
            print(f"  {col}: filled {null_count} nulls with project median")

    for col in ["actual_daily_spend_usd", "hw_cost_actual_usd"]:
        grp = df.groupby("project_id")[col]
        mean = grp.transform("mean")
        std  = grp.transform("std")
        outlier_mask = (df[col] - mean).abs() > 3 * std
        outlier_count = outlier_mask.sum()
        if outlier_count:
            df.loc[outlier_mask, col] = mean + 2.5 * std
            print(f"  {col}: capped {outlier_count} outliers (>3 sigma)")

    df["client"]            = df["client"].str.strip()
    df["region"]            = df["region"].str.strip().str.upper()
    df["deployment_status"] = df["deployment_status"].str.strip()

    df["month"]           = df["date"].dt.to_period("M").astype(str)
    df["week"]            = df["date"].dt.isocalendar().week.astype(int)
    df["day_of_week"]     = df["date"].dt.day_name()
    df["is_weekend"]      = df["date"].dt.weekday >= 5

    df["daily_spend_variance_usd"] = (
        df["actual_daily_spend_usd"] - df["planned_daily_spend_usd"]
    ).round(2)

    print(f"  {original_len:,} -> {len(df):,} rows after cleaning")
    return df


def recalculate_cumulative(df: pd.DataFrame) -> pd.DataFrame:
    print("\n[3/5] Recalculating cumulative spend...")
    df["cumulative_actual_usd"] = (
        df.groupby("project_id")["actual_daily_spend_usd"]
        .cumsum()
        .round(2)
    )
    df["cumulative_planned_usd"] = (
        df.groupby("project_id")["planned_daily_spend_usd"]
        .cumsum()
        .round(2)
    )
    print("  Done")
    return df


def enrich(df: pd.DataFrame) -> pd.DataFrame:
    print("\n[4/5] Adding project metadata...")

    project_meta = df.groupby("project_id").agg(
        project_start_date = ("date", "min"),
        project_end_date   = ("date", "max"),
        total_planned_usd  = ("planned_daily_spend_usd", "sum"),
    ).reset_index()

    df = df.merge(project_meta, on="project_id", how="left")

    df["days_elapsed"] = (df["date"] - df["project_start_date"]).dt.days + 1
    df["project_duration_days"] = (
        (df["project_end_date"] - df["project_start_date"]).dt.days + 1
    )
    df["pct_timeline_elapsed"] = (
        df["days_elapsed"] / df["project_duration_days"]
    ).round(4)

    print("  Added start/end dates, duration, timeline %, total budget")
    return df


def validate_and_save(df: pd.DataFrame) -> pd.DataFrame:
    print("\n[5/5] Validating and saving...")

    assert df["date"].isnull().sum() == 0,              "Date nulls remain"
    assert df["project_id"].isnull().sum() == 0,        "Project ID nulls remain"
    assert df["actual_daily_spend_usd"].isnull().sum() == 0, "Spend nulls remain"
    assert (df["actual_daily_spend_usd"] >= 0).all(),   "Negative spend values"

    os.makedirs(str(CLEAN_PATH.parent), exist_ok=True)
    df.to_csv(str(CLEAN_PATH), index=False)
    print(f"  Saved -> {CLEAN_PATH}")

    print(f"\n  Rows        : {len(df):,}")
    print(f"  Projects    : {df['project_id'].nunique()}")
    print(f"  Date range  : {df['date'].min().date()} to {df['date'].max().date()}")
    print(f"  Total planned : ${df.groupby('project_id')['planned_daily_spend_usd'].sum().sum():,.0f}")
    print(f"  Total actual  : ${df.groupby('project_id')['actual_daily_spend_usd'].sum().sum():,.0f}")

    return df


def run_pipeline() -> pd.DataFrame:
    print("=" * 60)
    print("  Phase 2: Processing Pipeline")
    print("=" * 60)

    df = ingest(str(RAW_PATH))
    df = clean(df)
    df = recalculate_cumulative(df)
    df = enrich(df)
    df = validate_and_save(df)

    print(f"\n  Pipeline complete. Shape: {df.shape}")
    print("=" * 60)
    return df


if __name__ == "__main__":
    run_pipeline()
