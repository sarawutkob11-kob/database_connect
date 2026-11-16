"""Focused QA for the Round 4 Excel worksheet row limit."""

import os
import sys
import threading
import unittest
from collections import defaultdict
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import database_connect_gui as app  # noqa: E402

GUI = app.DatabaseConnectorGUI


class _FakeEntry:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value


class _FakeButton:
    def __init__(self):
        self.config_calls = []

    def config(self, **kwargs):
        self.config_calls.append(kwargs)


class _FakeText:
    def __init__(self):
        self.inserted = []
        self.deleted = []
        self.seen = []

    def insert(self, _index, value):
        self.inserted.append(value)

    def delete(self, *args):
        self.deleted.append(args)

    def see(self, index):
        self.seen.append(index)


class _FakeCell:
    def __init__(self):
        self.value = None
        self.fill = None
        self.border = None
        self.number_format = None
        self.data_type = "s"


class _FakeColumnDimension:
    width = None


class _FakeWorksheet:
    def __init__(self):
        self.max_column = 1
        self.max_row = 1
        self.header = [_FakeCell()]
        self.freeze_panes = None
        self.column_dimensions = defaultdict(_FakeColumnDimension)
        self.cell_writes = []

    def __getitem__(self, _key):
        return self.header

    def cell(self, row, column, value=None):
        self.cell_writes.append((row, column, value))
        self.max_row = max(self.max_row, row)
        self.max_column = max(self.max_column, column)
        cell = _FakeCell()
        cell.value = value
        return cell

    def iter_rows(self, **_kwargs):
        return [[_FakeCell()]]


class _FakeWriter:
    def __init__(self):
        self.sheets = {}
        self.writes = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def add_sheet(self, sheet_name, max_row=1):
        worksheet = _FakeWorksheet()
        worksheet.max_row = max_row
        self.sheets[sheet_name] = worksheet


class _FakeSeries:
    dtype = object

    def map(self, function):
        return _FakeSeries([function(value) for value in self.values])

    def astype(self, _type):
        return _FakeSeries([str(value) for value in self.values])

    def max(self):
        return max(self.values, default=0)

    def __init__(self, values=("sample",)):
        self.values = list(values)


class _FakeResultFrame:
    """Represents a large result by its row count, without allocating rows."""

    def __init__(self, row_count, writer):
        self.row_count = row_count
        self.writer = writer
        self.columns = ["value"]
        self.shape = (row_count, 1)
        self.empty = row_count == 0
        self.value = _FakeSeries(["sample"])

    def __len__(self):
        return self.row_count

    def copy(self):
        return _FakeResultFrame(self.row_count, self.writer)

    def __getitem__(self, _column):
        return self.value

    def __setitem__(self, _column, series):
        self.value = series

    def head(self, _count):
        return self

    def to_excel(self, writer, sheet_name, index):
        self.writer.writes.append(
            {"kind": "result", "sheet": sheet_name, "rows": len(self), "index": index}
        )
        writer.add_sheet(sheet_name, max_row=self.row_count + 1)


class _FakeFailureFrame:
    def __init__(self, values, writer):
        self.values = values
        self.writer = writer

    def to_excel(self, writer, sheet_name, index):
        self.writer.writes.append(
            {
                "kind": "failed",
                "sheet": sheet_name,
                "values": self.values,
                "index": index,
            }
        )
        writer.add_sheet(sheet_name, max_row=2)


class _ImmediateThread:
    def __init__(self, target, daemon=None):
        self.target = target
        self.daemon = daemon

    def start(self):
        self.target()


class _StopEvent:
    def is_set(self):
        return False


def make_stub(jobs):
    stub = GUI.__new__(GUI)
    stub.profile_combo = _FakeEntry("Profile A")
    stub.results_text = _FakeText()
    stub.export_excel_btn = _FakeButton()
    stub.root = mock.Mock(name="root")
    stub.root.after.side_effect = lambda _delay, callback: callback()
    stub._stop_event = _StopEvent()
    stub._block_if_busy = mock.Mock(return_value=False)
    stub._block_if_profile_mismatch = mock.Mock(return_value=False)
    engine = mock.Mock(name="engine")
    stub.engine = engine
    stub._capture_run_target = mock.Mock(
        return_value=app.RunTarget(
            engine,
            app.ConnectionInfo(
                profile="Profile A",
                db_type="PostgreSQL",
                user="user",
                host="localhost",
                port="5432",
                database="db",
            ),
        )
    )
    stub._reuse_last_run_results = mock.Mock(side_effect=lambda export_jobs: export_jobs)
    stub._start_stoppable_run = mock.Mock()
    return stub


def run_export(test_case, jobs, row_counts):
    stub = make_stub(jobs)
    writer = _FakeWriter()
    frames = {
        id(job): _FakeResultFrame(row_counts[job["name"]], writer)
        for job in jobs
    }

    def dataframe_factory(values):
        return _FakeFailureFrame(values, writer)

    with mock.patch.object(app.pd, "ExcelWriter", return_value=writer), \
            mock.patch.object(app.pd, "DataFrame", side_effect=dataframe_factory), \
            mock.patch.object(app.filedialog, "asksaveasfilename", return_value="export.xlsx"), \
            mock.patch.object(app.threading, "Thread", side_effect=lambda **kwargs: _ImmediateThread(**kwargs)), \
            mock.patch.object(app, "messagebox") as messagebox:
        with mock.patch.object(
            stub,
            "_reuse_last_run_results",
            side_effect=lambda export_jobs: [
                dict(job, _export_dataframe=frames[id(job)]) for job in export_jobs
            ],
        ):
            stub.export_jobs_to_excel(jobs_override=jobs)

    test_case.assertFalse(messagebox.showerror.called)
    test_case.assertFalse(messagebox.showwarning.called)
    return stub, writer


class ExcelRowLimitExportTests(unittest.TestCase):
    def test_over_limit_job_fails_without_writing_its_result_frame(self):
        job = {"name": "TooMany", "query": "SELECT 1"}
        stub, writer = run_export(
            self,
            [job],
            {"TooMany": app.EXCEL_MAX_DATA_ROWS + 1},
        )

        self.assertIn("TooMany", writer.sheets)
        result_writes = [write for write in writer.writes if write["kind"] == "result"]
        failed_writes = [write for write in writer.writes if write["kind"] == "failed"]
        self.assertEqual(result_writes, [])
        self.assertEqual(len(failed_writes), 1)
        self.assertIn("Failed", failed_writes[0]["values"]["Status"])
        self.assertIn("1,048,575", failed_writes[0]["values"]["Error"][0])
        self.assertTrue(any("Success: 0" in item for item in stub.results_text.inserted))
        self.assertTrue(any("Failed: 1" in item for item in stub.results_text.inserted))

    def test_limit_boundary_is_written_without_truncation(self):
        job = {"name": "AtLimit", "query": "SELECT 1"}
        stub, writer = run_export(
            self,
            [job],
            {"AtLimit": app.EXCEL_MAX_DATA_ROWS},
        )

        self.assertIn("AtLimit", writer.sheets)
        result_writes = [write for write in writer.writes if write["kind"] == "result"]
        failed_writes = [write for write in writer.writes if write["kind"] == "failed"]
        self.assertEqual(len(result_writes), 1)
        self.assertEqual(result_writes[0]["rows"], app.EXCEL_MAX_DATA_ROWS)
        self.assertEqual(result_writes[0]["index"], False)
        self.assertEqual(failed_writes, [])
        worksheet = writer.sheets["AtLimit"]
        self.assertEqual(worksheet.max_row, app.EXCEL_MAX_DATA_ROWS + 1)
        self.assertEqual(worksheet.cell_writes, [])
        self.assertTrue(
            any(
                "SQL annotation not added because the worksheet is full" in item
                and "1,048,576" in item
                for item in stub.results_text.inserted
            )
        )
        self.assertTrue(any("Success: 1" in item for item in stub.results_text.inserted))
        self.assertTrue(any("Failed: 0" in item for item in stub.results_text.inserted))

    def test_sql_annotation_is_written_when_it_fits(self):
        job = {"name": "Small", "query": "SELECT 1"}
        _stub, writer = run_export(self, [job], {"Small": 2})

        worksheet = writer.sheets["Small"]
        self.assertEqual(worksheet.cell_writes, [(5, 1, "SELECT 1")])
        self.assertEqual(worksheet.max_row, 5)

    def test_export_continues_after_over_limit_job_and_reports_counts(self):
        oversized = {"name": "TooMany", "query": "SELECT 1"}
        following = {"name": "Following", "query": "SELECT 2"}
        stub, writer = run_export(
            self,
            [oversized, following],
            {
                "TooMany": app.EXCEL_MAX_DATA_ROWS + 1,
                "Following": 23,
            },
        )

        self.assertIn("TooMany", writer.sheets)
        self.assertIn("Following", writer.sheets)
        failed_writes = [write for write in writer.writes if write["kind"] == "failed"]
        result_writes = [write for write in writer.writes if write["kind"] == "result"]
        self.assertEqual(len(failed_writes), 1)
        self.assertEqual(failed_writes[0]["sheet"], "TooMany")
        self.assertEqual(len(result_writes), 1)
        self.assertEqual(result_writes[0]["sheet"], "Following")
        self.assertEqual(result_writes[0]["rows"], 23)
        self.assertTrue(any("Success: 1" in item for item in stub.results_text.inserted))
        self.assertTrue(any("Failed: 1" in item for item in stub.results_text.inserted))


if __name__ == "__main__":
    unittest.main()
