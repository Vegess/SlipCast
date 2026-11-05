# Using SlipCast data in Tableau and Power BI

SlipCast's screens answer the common questions. When you want your own cuts (by
quarter, by customer label, or alongside other company data), export the data and
build on it in a BI tool.

## 1. Export

On a project's **Delivery** tab, click **Export for Tableau / Power BI**. You get a zip
with five tidy CSV files: one row per entity, `snake_case` columns, ISO 8601 dates
(`2026-11-05` for dates, `2026-11-05T14:03:00` for timestamps, all UTC).

| File | One row per | Key columns |
|---|---|---|
| `tickets.csv` | ticket | `ticket_id`, `type`, `theme`, `status`, `owner`, `created_at`, `completed_at`, `due_date`, `planned_days`, `cycle_days`, `finished_late`, `quality_score`, `slip_risk` |
| `events.csv` | status change | `ticket_id`, `from_status`, `to_status`, `changed_at` |
| `cycle_times.csv` | finished ticket | `ticket_id`, `type`, `theme`, `owner`, `completed_at`, `cycle_days`, `finished_late` |
| `weekly_throughput.csv` | week (last 26) | `week_start`, `tickets_finished` |
| `forecasts.csv` | forecast in the ledger | `forecast_id`, `kind`, `subject_id`, `made_at`, `p50_date`, `p85_date`, `p10_days`…`p90_days`, `actual_date`, `actual_days`, `hit_p85` |

`README.txt` in the zip explains every column. **Export to Excel** gives the same data
as a formatted workbook if you'd rather stay in a spreadsheet.

Relationships: `events.ticket_id`, `cycle_times.ticket_id` and
`forecasts.subject_id` (for `ticket_reference_class` rows) all point to
`tickets.ticket_id`.

## 2. Connect

### Tableau (Desktop or Public)

1. Unzip the export into a folder.
2. **Connect → To a File → Text file**, and choose `tickets.csv`.
3. Drag `events.csv` onto the canvas. Tableau creates a *relationship*; set it to
   `ticket_id = ticket_id`. Do the same for `cycle_times.csv`.
   Add `forecasts.csv` with `subject_id = ticket_id`.
4. Check the field types in the data source tab: `created_at`, `completed_at`,
   `changed_at` and `made_at` should be **Date & Time**; `due_date` and `week_start`
   should be **Date**. Tableau usually detects ISO dates automatically.
5. Set `finished_late` and `hit_p85` to **Number (whole)** so you can average them
   into rates.

To refresh, export again into the same folder with the same file names and choose
**Data → Refresh**.

### Power BI Desktop

1. Unzip the export.
2. **Get data → Folder**, pick the folder, then **Combine & Transform** is *not*
   needed: instead choose **Transform data** and keep each file as its own query
   (or use **Get data → Text/CSV** once per file).
3. In Power Query, check types: timestamps as **Date/Time**, `due_date` and
   `week_start` as **Date**, `cycle_days`, `planned_days`, `slip_risk` as **Decimal
   number**, `finished_late` and `hit_p85` as **Whole number**.
   ISO dates parse correctly in any locale.
4. **Close & Apply**, then in **Model view** create relationships
   `tickets[ticket_id] 1 → * events[ticket_id]` and
   `tickets[ticket_id] 1 → * cycle_times[ticket_id]`.
5. Add a date table (`Modeling → New table → Dates = CALENDARAUTO()`) and relate it to
   `cycle_times[completed_at]` (as a date) for time intelligence.

Useful measures (DAX):

```DAX
Median cycle days = MEDIAN ( cycle_times[cycle_days] )
P85 cycle days    = PERCENTILE.INC ( cycle_times[cycle_days], 0.85 )
Slip rate         = AVERAGE ( cycle_times[finished_late] )
Forecast hit rate = AVERAGE ( forecasts[hit_p85] )
```

## 3. Three dashboards worth building

### A. Cycle-time control chart

*Is work getting faster or slower, and which tickets were outliers?*

- Source: `cycle_times.csv`.
- X axis: `completed_at` (exact date). Y axis: `cycle_days`. Mark type: circle.
- Colour by `type` (or `theme`).
- Reference lines: median and 85th percentile of `cycle_days` (Tableau: Analytics pane
  → Reference Line → Percentile 50 and 85; Power BI: Analytics pane → Percentile line).
- Add a filter on `owner` and a date-range filter on `completed_at`.
- Read it: dots above the P85 line are the tickets worth a retro. A rising cloud means
  the process is slowing down; a tighter cloud means estimates will be more reliable.

### B. Throughput trend

*How much does the team finish each week, and is it stable?*

- Source: `weekly_throughput.csv`.
- X axis: `week_start` (week). Y axis: `tickets_finished` as bars.
- Add a 4-week moving average line (Tableau: Quick Table Calculation → Moving Average,
  previous 3 values; Power BI: a measure with `AVERAGEX ( DATESINPERIOD ( … , -28, DAY ) … )`).
- Exclude the last row from averages: it is the current, partial week.
- Read it: SlipCast's forecast resamples the last 12 complete weeks, so a recent drop
  here will push the forecast dates out.

### C. Slip rate by theme

*Which areas of the product miss their due dates most often?*

- Source: `cycle_times.csv` (finished tickets only).
- Rows: `theme`. Measure: average of `finished_late` (format as %), sorted descending.
- Add count of `ticket_id` as a label so small themes don't mislead; filter to themes
  with at least 8 tickets.
- Optional second view: the same with `type` or `owner` on rows, or a heat map of
  `theme` × `type`.
- Read it: a theme with a high slip rate *and* a long median cycle time needs bigger
  estimates or a closer look at its dependencies; SlipCast's write-time check already
  warns when a new ticket resembles these.

## 4. Bonus: check the forecasts yourself

Filter `forecasts.csv` to `kind = ticket_reference_class` and plot `actual_days`
against `p85_days`. Points below the diagonal were forecasts SlipCast got right. The
average of `hit_p85` should be close to 0.85; if it isn't, the Track record section
of the Forecast tab says so too.
