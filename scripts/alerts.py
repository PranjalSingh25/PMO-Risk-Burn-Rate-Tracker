import pandas as pd
import numpy as np
import os
import sys
from pathlib import Path
from datetime import datetime

BASE_DIR   = Path(__file__).resolve().parent.parent
CLEAN_PATH = BASE_DIR / "data" / "clean_telemetry.csv"
OUTPUT_DIR = BASE_DIR / "output"

ALERT_THRESHOLD   = 0.10
WARNING_THRESHOLD = 0.05

REPORT_TIMESTAMP  = datetime.now().strftime("%Y%m%d_%H%M%S")


def calculate_burn_rate(df: pd.DataFrame) -> pd.DataFrame:
    df["burn_rate_pct"] = (
        df["cumulative_actual_usd"] / df["cumulative_planned_usd"]
    ).replace([np.inf, -np.inf], np.nan).round(4)

    df["overrun_pct"] = (df["burn_rate_pct"] - 1.0).round(4)

    df["is_critical_overrun"] = df["overrun_pct"] > ALERT_THRESHOLD
    df["is_warning_overrun"]  = (
        (df["overrun_pct"] > WARNING_THRESHOLD) &
        (df["overrun_pct"] <= ALERT_THRESHOLD)
    )

    df["projected_final_spend_usd"] = (
        df["cumulative_actual_usd"] / df["pct_timeline_elapsed"].replace(0, np.nan)
    ).round(2)

    df["projected_overrun_usd"] = (
        df["projected_final_spend_usd"] - df["total_planned_usd"]
    ).round(2)

    # Health score: 100 = perfect, 0 = critical
    # Penalty per 1% over budget: -5 points (capped at -50)
    #   e.g. 5% over = -25, 10%+ over = -50
    # Penalty per shipping delay day: -3 points (capped at -30)
    #   e.g. 5 days delay = -15, 10+ days = -30
    # Combined max penalty: -80, worst project scores 20
    overrun_penalty = (df["overrun_pct"].clip(lower=0) * 100 * 5).clip(upper=50)
    delay_penalty   = (df["shipping_delay_days"] * 3).clip(upper=30)
    df["health_score"] = (100 - overrun_penalty - delay_penalty).clip(lower=0).round(1)

    return df


def run_alert_engine(df: pd.DataFrame) -> pd.DataFrame:
    print("\n" + "=" * 65)
    print("  ALERT ENGINE SCAN")
    print("=" * 65)

    alert_log = []

    critical_first = (
        df[df["is_critical_overrun"]]
        .groupby("project_id")
        .first()
        .reset_index()
    )

    warning_first = (
        df[df["is_warning_overrun"]]
        .groupby("project_id")
        .first()
        .reset_index()
    )

    if len(critical_first) == 0:
        print("\n  No critical overruns.\n")

    for _, row in critical_first.iterrows():
        overrun_pct_str = f"{row['overrun_pct'] * 100:.1f}%"
        overrun_usd     = row["cumulative_actual_usd"] - row["cumulative_planned_usd"]
        proj_overrun    = row["projected_overrun_usd"]

        print(
            f"\n  CRITICAL - {row['project_id']} ({row['client']})\n"
            f"    Region    : {row['region']}\n"
            f"    Date      : {str(row['date'])[:10]}\n"
            f"    Status    : {row['deployment_status']}\n"
            f"    Burn Rate : {overrun_pct_str} over budget\n"
            f"    Overrun   : ${overrun_usd:,.0f}\n"
            f"    Projected : ${proj_overrun:,.0f} total overrun at completion\n"
            f"    Health    : {row['health_score']}/100\n"
            f"  >> Escalate to PMO Director + Finance Lead"
        )

        alert_log.append({
            "alert_type":         "CRITICAL",
            "project_id":         row["project_id"],
            "client":             row["client"],
            "region":             row["region"],
            "alert_date":         str(row["date"])[:10],
            "deployment_status":  row["deployment_status"],
            "overrun_pct":        round(row["overrun_pct"] * 100, 2),
            "overrun_usd":        round(overrun_usd, 2),
            "projected_overrun_usd": round(proj_overrun, 2),
            "health_score":       row["health_score"],
        })

    for _, row in warning_first.iterrows():
        overrun_pct_str = f"{row['overrun_pct'] * 100:.1f}%"
        overrun_usd     = row["cumulative_actual_usd"] - row["cumulative_planned_usd"]

        print(
            f"\n  WARNING - {row['project_id']} ({row['client']})\n"
            f"    {overrun_pct_str} over as of {str(row['date'])[:10]} | "
            f"${overrun_usd:,.0f} variance. Monitor."
        )

        alert_log.append({
            "alert_type":         "WARNING",
            "project_id":         row["project_id"],
            "client":             row["client"],
            "region":             row["region"],
            "alert_date":         str(row["date"])[:10],
            "deployment_status":  row["deployment_status"],
            "overrun_pct":        round(row["overrun_pct"] * 100, 2),
            "overrun_usd":        round(overrun_usd, 2),
            "projected_overrun_usd": round(row["projected_overrun_usd"], 2),
            "health_score":       row["health_score"],
        })

    alert_df = pd.DataFrame(alert_log)
    print("\n" + "=" * 65)
    return alert_df


def build_executive_summary(df: pd.DataFrame) -> pd.DataFrame:
    latest = df.sort_values("date").groupby("project_id").last().reset_index()

    summary = latest[[
        "project_id", "client", "region", "fleet_size",
        "deployment_status", "pct_timeline_elapsed",
        "cumulative_planned_usd", "cumulative_actual_usd",
        "overrun_pct", "projected_final_spend_usd",
        "projected_overrun_usd", "total_planned_usd",
        "health_score", "is_critical_overrun", "is_warning_overrun",
    ]].copy()

    summary["overrun_pct_display"]     = (summary["overrun_pct"] * 100).round(1)
    summary["pct_timeline_display"]    = (summary["pct_timeline_elapsed"] * 100).round(1)
    summary["status_flag"] = summary.apply(
        lambda r: "CRITICAL" if r["is_critical_overrun"]
        else ("WARNING" if r["is_warning_overrun"] else "ON TRACK"),
        axis=1
    )

    return summary.sort_values("overrun_pct", ascending=False)


def export_powerbi_files(df: pd.DataFrame, alerts: pd.DataFrame, summary: pd.DataFrame):
    os.makedirs(str(OUTPUT_DIR), exist_ok=True)

    telemetry_path = OUTPUT_DIR / "fact_daily_telemetry.csv"
    alerts_path    = OUTPUT_DIR / "dim_alert_log.csv"
    summary_path   = OUTPUT_DIR / "kpi_executive_summary.csv"

    df_export = df.copy()
    df_export["date"] = df_export["date"].dt.strftime("%Y-%m-%d")

    df_export.to_csv(str(telemetry_path), index=False)
    alerts.to_csv(str(alerts_path), index=False)
    summary.to_csv(str(summary_path), index=False)

    print(f"\n  Power BI export files:")
    print(f"    {telemetry_path}  ({len(df_export):,} rows)")
    print(f"    {alerts_path}  ({len(alerts)} alerts)")
    print(f"    {summary_path}  ({len(summary)} projects)")


def run_alerts():
    print("=" * 65)
    print("  Phase 3: Burn-Rate Engine & Alerts")
    print("=" * 65)

    if not os.path.exists(str(CLEAN_PATH)):
        sys.exit("  clean_telemetry.csv not found. Run 02_pipeline.py first.")

    df = pd.read_csv(str(CLEAN_PATH), parse_dates=["date"])
    print(f"\n  Loaded {len(df):,} rows")

    df = calculate_burn_rate(df)
    print("  Burn-rate metrics calculated")

    alerts   = run_alert_engine(df)
    summary  = build_executive_summary(df)

    print("\n  PROJECT SUMMARY")
    print("  " + "-" * 85)
    print(f"  {'ID':<9} {'CLIENT':<35} {'STATUS':<25} {'BURN':<8} {'HEALTH'}")
    print("  " + "-" * 85)
    for _, row in summary.iterrows():
        print(
            f"  {row['project_id']:<9} "
            f"{row['client'][:34]:<35} "
            f"{row['status_flag']:<25} "
            f"{row['overrun_pct_display']:>+5.1f}%  "
            f"{row['health_score']:.0f}/100"
        )
    print("  " + "-" * 85)

    export_powerbi_files(df, alerts, summary)

    print(f"\n  Alert engine complete.")
    print("=" * 65)

    return df, alerts, summary


if __name__ == "__main__":
    run_alerts()
