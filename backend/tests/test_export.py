"""Excel and BI exports (Phase 2E)."""

import csv
import io
import re
import zipfile

import openpyxl

SHEETS = ["README", "Tickets", "Status history", "Cycle times", "Weekly throughput", "Forecast", "Forecast ledger",
          "Model metrics"]  # fmt: skip
CSVS = {"tickets.csv", "events.csv", "cycle_times.csv", "weekly_throughput.csv", "forecasts.csv"}


def test_workbook_opens_with_expected_sheets(client, demo):
    h, pid = demo["headers"], demo["project_id"]
    r = client.get(f"/api/projects/{pid}/export.xlsx", headers=h)
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/vnd.openxmlformats")
    assert 'filename="slipcast-atlas-billing-demo.xlsx"' in r.headers["content-disposition"]
    wb = openpyxl.load_workbook(io.BytesIO(r.content))
    assert wb.sheetnames[: len(SHEETS)] == SHEETS
    tickets = wb["Tickets"]
    header = [c.value for c in tickets[1]]
    assert header[:3] == ["ticket_id", "title", "type"] and all(c.font.bold for c in tickets[1])
    assert tickets.freeze_panes == "A2"
    n_tasks = len(client.get(f"/api/projects/{pid}/tasks", headers=h).json())
    assert tickets.max_row == n_tasks + 1
    created = tickets.cell(row=2, column=header.index("created_at") + 1)
    assert created.is_date, "dates are real Excel dates, not text"
    assert tickets.column_dimensions["B"].width > 20
    metrics = [[c.value for c in row] for row in wb["Model metrics"].iter_rows(min_row=2)]
    assert ["Type classifier", "accuracy"] == metrics[0][:2] and metrics[0][2] > metrics[0][3]
    readme_sheets = {row[0].value for row in wb["README"].iter_rows(min_row=4) if row[0].value}
    assert readme_sheets >= {"Tickets", "Status history", "Model metrics"}


def test_bi_zip_has_tidy_csvs(client, demo):
    h, pid = demo["headers"], demo["project_id"]
    r = client.get(f"/api/projects/{pid}/export/bi.zip", headers=h)
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
    zf = zipfile.ZipFile(io.BytesIO(r.content))
    assert set(zf.namelist()) >= CSVS
    for name in CSVS:
        rows = list(csv.DictReader(io.StringIO(zf.read(name).decode())))
        assert rows, name
        assert all(re.fullmatch(r"[a-z0-9_]+", col) for col in rows[0]), f"snake_case columns in {name}"
    tickets = list(csv.DictReader(io.StringIO(zf.read("tickets.csv").decode())))
    ids = [t["ticket_id"] for t in tickets]
    assert len(ids) == len(set(ids)), "one row per ticket"
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", tickets[0]["created_at"])
    assert all(re.fullmatch(r"(\d{4}-\d{2}-\d{2})?", t["due_date"]) for t in tickets)
    assert {t["finished_late"] for t in tickets} <= {"0", "1", ""}
    weeks = list(csv.DictReader(io.StringIO(zf.read("weekly_throughput.csv").decode())))
    assert len(weeks) == 26 and re.fullmatch(r"\d{4}-\d{2}-\d{2}", weeks[0]["week_start"])


def test_exports_work_for_an_empty_project(client, make_user):
    u = make_user()
    p = client.post(
        f"/api/workspaces/{u['workspace_id']}/projects", json={"name": "Empty"}, headers=u["headers"]
    ).json()
    x = client.get(f"/api/projects/{p['id']}/export.xlsx", headers=u["headers"])
    assert x.status_code == 200
    wb = openpyxl.load_workbook(io.BytesIO(x.content))
    assert wb["Model metrics"]["B2"].value.startswith("Not enough data")
    assert client.get(f"/api/projects/{p['id']}/export/bi.zip", headers=u["headers"]).status_code == 200
