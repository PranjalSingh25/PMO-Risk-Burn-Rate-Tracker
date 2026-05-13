# Power BI Dashboard Setup

Build an executive dashboard from the three CSV files in `/output/`.

## 1. Import

1. Open Power BI Desktop
2. Home > Get Data > Text/CSV
3. Import all three files:

| File | Purpose |
|------|---------|
| `fact_daily_telemetry.csv` | Main fact table (daily spend per project) |
| `dim_alert_log.csv` | Alert events |
| `kpi_executive_summary.csv` | One row per project with KPIs |

4. In Power Query Editor, verify types:
   - `date` = Date
   - `*_usd` columns = Decimal Number
   - `overrun_pct` = Decimal Number

## 2. Relationships

Model View > create these relationships:

```
fact_daily_telemetry.project_id  -->  kpi_executive_summary.project_id
fact_daily_telemetry.project_id  -->  dim_alert_log.project_id
```

Both are Many-to-One.

## 3. DAX Measures

In the `fact_daily_telemetry` table:

```
Total Actual Spend = SUM(fact_daily_telemetry[actual_daily_spend_usd])

Total Planned Spend = SUM(fact_daily_telemetry[planned_daily_spend_usd])

Burn Rate % = DIVIDE([Total Actual Spend], [Total Planned Spend]) - 1

Active Critical Alerts =
    CALCULATE(
        COUNTROWS(dim_alert_log),
        dim_alert_log[alert_type] = "CRITICAL"
    )

Active Warnings =
    CALCULATE(
        COUNTROWS(dim_alert_log),
        dim_alert_log[alert_type] = "WARNING"
    )

Avg Health Score = AVERAGE(kpi_executive_summary[health_score])

Budget Variance = [Total Actual Spend] - [Total Planned Spend]
```

## 4. Visuals

### Gantt Chart

Install "Gantt Chart by MAQ Software" from AppSource (free).

Settings:
- Task: `client`
- Start Date: `project_start_date`
- End Date: `project_end_date`
- Legend: `deployment_status`

### Burn Rate Chart

Line and Clustered Column Chart:
- X-axis: `date` (Day)
- Columns: `planned_daily_spend_usd`
- Line: `actual_daily_spend_usd`
- Legend: `project_id`

### KPI Cards

Four card visuals at the top:
- Critical Overruns (red if > 0)
- Warnings (yellow if > 0)
- Budget Variance (red if > 0)
- Avg Health Score (green if > 85)

Format > Conditional formatting > Font color for color rules.

### Status Matrix

Matrix visual from `kpi_executive_summary`:
- Rows: `project_id`, `client`
- Values: `overrun_pct_display`, `health_score`, `status_flag`

Conditional formatting on `overrun_pct_display`: red > 10%, orange 5-10%, green < 5%.

## 5. Dark Theme

View > Themes > Browse for themes. Create and import this `.json`:

```json
{
  "name": "Dark Dashboard",
  "dataColors": [
    "#00D4FF", "#FF4444", "#00FF7F", "#FFA500",
    "#7B68EE", "#FFD700", "#20B2AA", "#FF69B4"
  ],
  "background": "#0D1117",
  "foreground": "#C9D1D9",
  "tableAccent": "#00D4FF",
  "visualStyles": {
    "*": {
      "*": {
        "background": [{"color": {"solid": {"color": "#161B22"}}}],
        "border": [{"color": {"solid": {"color": "#30363D"}}}],
        "fontColor": [{"color": {"solid": {"color": "#C9D1D9"}}}]
      }
    }
  }
}
```

Set canvas background to `#0D1117`, visual backgrounds to `#161B22`.

## 6. Layout

Top row: 4 KPI cards. Left: Gantt chart. Right: Burn rate chart. Bottom: Status matrix. Title bar at top.

## 7. Export

File > Export to PDF or take a screenshot for your portfolio.

## Power Query Help

```m
// Format overrun as percentage string
= Table.AddColumn(Source, "Overrun Display", each 
    Text.From(Number.Round([overrun_pct] * 100, 1)) & "%")

// Health score categories
= Table.AddColumn(Source, "Health Category", each 
    if [health_score] >= 90 then "Excellent"
    else if [health_score] >= 75 then "Good"
    else if [health_score] >= 60 then "At Risk"
    else "Critical")
```
