"""Round 2 H4 — table data is reloaded when the file changes (R2-AC-27..33).

Run:  python -m unittest discover -s tests -p "test_*.py"
"""

import builtins
import datetime as _dt
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import database_connect_gui as app  # noqa: E402

GUI = app.DatabaseConnectorGUI
SQL = "SELECT * FROM a WHERE c IN ({TABLE_T_C})"
MTIME_1 = 1_700_000_000.0
MTIME_2 = MTIME_1 + 60.0
MISSING_TEXT = "table data file is missing or cannot be read"


class _FakeText:
    def __init__(self):
        self.log = []

    def insert(self, _index, value):
        self.log.append(value)

    def delete(self, *_args):
        pass

    def see(self, *_args):
        pass

    def timestamp_lines(self):
        return [line for line in self.log if line.startswith("📅 Table data:")]


def _payload(timestamp, values):
    return {"timestamp": timestamp, "tables": {"t": {"column_data": {"c": values}}}}


class _TableDataCase(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.path = os.path.join(folder.name, "mail_table_data.json")

    def write(self, content, mtime):
        with open(self.path, "w", encoding="utf-8") as f:
            if isinstance(content, str):
                f.write(content)
            else:
                json.dump(content, f)
        os.utime(self.path, (mtime, mtime))

    def make_stub(self):
        stub = type("Stub", (), {})()
        stub.results_text = _FakeText()
        stub.loaded_table_data = None
        stub.last_table_data_mtime = None
        stub.table_data_file = self.path
        stub._current_table_data_tables = lambda: GUI._current_table_data_tables(stub)
        return stub

    def prepare(self, stub, jobs):
        errors = []
        with mock.patch.object(
            app.messagebox, "showerror", side_effect=lambda *a, **k: errors.append(a)
        ):
            return GUI._prepare_run_sql(stub, jobs), errors


class CurrentTableDataTablesTests(_TableDataCase):
    def test_first_call_loads_file_and_records_mtime(self):
        self.write(_payload("T1", ["111"]), MTIME_1)
        stub = self.make_stub()
        tables = stub._current_table_data_tables()
        self.assertEqual(tables, {"t": {"column_data": {"c": ["111"]}}})
        self.assertEqual(stub.loaded_table_data["timestamp"], "T1")
        self.assertEqual(stub.last_table_data_mtime, os.path.getmtime(self.path))

    def test_mtime_change_reloads_new_values(self):  # R2-AC-27
        self.write(_payload("T1", ["111"]), MTIME_1)
        stub = self.make_stub()
        stub._current_table_data_tables()
        self.write(_payload("T2", ["222", "333"]), MTIME_2)
        tables = stub._current_table_data_tables()
        self.assertEqual(tables["t"]["column_data"]["c"], ["222", "333"])
        self.assertEqual(stub.loaded_table_data["timestamp"], "T2")
        self.assertEqual(stub.last_table_data_mtime, os.path.getmtime(self.path))
        self.assertEqual(stub.last_table_data_mtime, MTIME_2)

    def test_older_mtime_also_reloads(self):
        """Compared with != (a file replaced by an older copy is still reloaded)."""
        self.write(_payload("T2", ["222"]), MTIME_2)
        stub = self.make_stub()
        stub._current_table_data_tables()
        self.write(_payload("T1", ["111"]), MTIME_1)
        tables = stub._current_table_data_tables()
        self.assertEqual(tables["t"]["column_data"]["c"], ["111"])
        self.assertEqual(stub.last_table_data_mtime, MTIME_1)

    def test_unchanged_mtime_does_not_reopen_file(self):  # R2-AC-29
        self.write(_payload("T1", ["111"]), MTIME_1)
        stub = self.make_stub()
        first = stub._current_table_data_tables()
        real_open = builtins.open
        with mock.patch.object(builtins, "open", side_effect=real_open) as opened:
            second = stub._current_table_data_tables()
            third = stub._current_table_data_tables()
        opened.assert_not_called()
        self.assertEqual(second, first)
        self.assertEqual(third, first)

    def test_cache_with_matching_mtime_is_used_without_reading(self):
        """Data loaded elsewhere (dialog / Auto-sync) with the same mtime is reused."""
        self.write(_payload("T1", ["from-file"]), MTIME_1)
        stub = self.make_stub()
        stub.loaded_table_data = _payload("T0", ["in-memory"])
        stub.last_table_data_mtime = os.path.getmtime(self.path)
        with mock.patch.object(builtins, "open", side_effect=AssertionError("opened")):
            tables = stub._current_table_data_tables()
        self.assertEqual(tables["t"]["column_data"]["c"], ["in-memory"])

    def test_cache_without_mtime_is_reloaded(self):
        """loaded_table_data set but last_table_data_mtime None -> read the file."""
        self.write(_payload("T1", ["from-file"]), MTIME_1)
        stub = self.make_stub()
        stub.loaded_table_data = _payload("T0", ["stale"])
        tables = stub._current_table_data_tables()
        self.assertEqual(tables["t"]["column_data"]["c"], ["from-file"])

    def test_stub_without_mtime_attribute_still_works(self):
        self.write(_payload("T1", ["111"]), MTIME_1)
        stub = self.make_stub()
        del stub.last_table_data_mtime  # instance attribute removed
        self.assertFalse(hasattr(stub, "last_table_data_mtime"))
        tables = stub._current_table_data_tables()
        self.assertEqual(tables["t"]["column_data"]["c"], ["111"])

    def test_broken_json_returns_none_and_keeps_cache(self):  # R2-AC-30
        self.write(_payload("T1", ["111"]), MTIME_1)
        stub = self.make_stub()
        stub._current_table_data_tables()
        old_data, old_mtime = stub.loaded_table_data, stub.last_table_data_mtime
        self.write('{"timestamp": "T2", "tables": {', MTIME_2)
        self.assertIsNone(stub._current_table_data_tables())
        # Cache untouched -> next call tries the file again
        self.assertIs(stub.loaded_table_data, old_data)
        self.assertEqual(stub.last_table_data_mtime, old_mtime)
        # Still broken -> still None (never the stale data)
        self.assertIsNone(stub._current_table_data_tables())

    def test_recovers_after_broken_file_is_fixed(self):
        self.write(_payload("T1", ["111"]), MTIME_1)
        stub = self.make_stub()
        stub._current_table_data_tables()
        self.write("not json", MTIME_2)
        self.assertIsNone(stub._current_table_data_tables())
        self.write(_payload("T3", ["999"]), MTIME_2 + 60)
        tables = stub._current_table_data_tables()
        self.assertEqual(tables["t"]["column_data"]["c"], ["999"])
        self.assertEqual(stub.last_table_data_mtime, MTIME_2 + 60)

    def test_empty_file_returns_none(self):
        self.write("", MTIME_1)
        stub = self.make_stub()
        self.assertIsNone(stub._current_table_data_tables())
        self.assertIsNone(stub.loaded_table_data)
        self.assertIsNone(stub.last_table_data_mtime)

    def test_non_dict_json_returns_none_and_keeps_cache(self):
        self.write(_payload("T1", ["111"]), MTIME_1)
        stub = self.make_stub()
        stub._current_table_data_tables()
        old_data = stub.loaded_table_data
        self.write([1, 2, 3], MTIME_2)
        self.assertIsNone(stub._current_table_data_tables())
        self.assertIs(stub.loaded_table_data, old_data)
        self.assertEqual(stub.last_table_data_mtime, MTIME_1)

    def test_tables_not_a_dict_returns_none(self):
        self.write({"timestamp": "T1", "tables": []}, MTIME_1)
        stub = self.make_stub()
        self.assertIsNone(stub._current_table_data_tables())

    def test_deleted_file_returns_none(self):  # R2-AC-31
        self.write(_payload("T1", ["111"]), MTIME_1)
        stub = self.make_stub()
        stub._current_table_data_tables()
        os.remove(self.path)
        self.assertIsNone(stub._current_table_data_tables())

    def test_never_created_file_returns_none(self):
        stub = self.make_stub()
        self.assertIsNone(stub._current_table_data_tables())

    def test_read_permission_error_returns_none(self):
        self.write(_payload("T1", ["111"]), MTIME_1)
        stub = self.make_stub()
        stub._current_table_data_tables()
        self.write(_payload("T2", ["222"]), MTIME_2)
        with mock.patch.object(builtins, "open", side_effect=PermissionError("locked")):
            self.assertIsNone(stub._current_table_data_tables())
        self.assertEqual(stub.last_table_data_mtime, MTIME_1)


class AutoSyncSharesMtimeTests(_TableDataCase):
    """R2-AC-27: Auto-sync must not reload a file Run has already loaded."""

    def test_auto_sync_does_not_reload_after_run_loaded_file(self):
        self.write(_payload("T1", ["111"]), MTIME_1)
        stub = self.make_stub()
        stub._current_table_data_tables()
        self.write(_payload("T2", ["222"]), MTIME_2)
        stub._current_table_data_tables()  # Run picks up the new file

        sync = mock.MagicMock()
        sync.table_data_file = self.path
        sync.last_table_data_mtime = stub.last_table_data_mtime
        sync.loaded_table_data = stub.loaded_table_data
        with mock.patch.object(builtins, "open", side_effect=AssertionError("reloaded")):
            GUI.check_and_sync_table_data(sync)
        sync.auto_replace_table_variables.assert_not_called()
        self.assertIs(sync.loaded_table_data, stub.loaded_table_data)
        sync.schedule_next_sync_check.assert_called_once()


class PrepareRunSqlTableDataTests(_TableDataCase):
    def test_second_run_uses_new_values(self):  # R2-AC-28
        self.write(_payload("T1", ["111"]), MTIME_1)
        stub = self.make_stub()
        job = {"name": "J", "query": SQL}
        first, errors1 = self.prepare(stub, [job])
        self.write(_payload("T2", ["222", "333"]), MTIME_2)
        second, errors2 = self.prepare(stub, [job])
        self.assertEqual(first, ["SELECT * FROM a WHERE c IN ('111')"])
        self.assertEqual(second, ["SELECT * FROM a WHERE c IN ('222', '333')"])
        self.assertEqual(errors1 + errors2, [])
        self.assertEqual(job["query"], SQL)

    def test_broken_json_blocks_run_and_never_uses_stale_data(self):  # R2-AC-30
        self.write(_payload("T1", ["111"]), MTIME_1)
        stub = self.make_stub()
        self.prepare(stub, [{"name": "J", "query": SQL}])
        stub.results_text.log.clear()
        self.write("{broken", MTIME_2)
        prepared, errors = self.prepare(stub, [{"name": "J", "query": SQL}])
        self.assertIsNone(prepared)
        self.assertEqual(len(errors), 1)
        message = errors[0][1]
        self.assertIn(MISSING_TEXT, message)
        self.assertIn("mail_table_data.json", message)
        self.assertIn("try again", message)
        self.assertNotIn("111", message)
        self.assertEqual(stub.results_text.timestamp_lines(), [])

    def test_deleted_file_blocks_run(self):  # R2-AC-31
        self.write(_payload("T1", ["111"]), MTIME_1)
        stub = self.make_stub()
        self.prepare(stub, [{"name": "J", "query": SQL}])
        os.remove(self.path)
        prepared, errors = self.prepare(stub, [{"name": "J", "query": SQL}])
        self.assertIsNone(prepared)
        self.assertEqual(len(errors), 1)
        self.assertIn(MISSING_TEXT, errors[0][1])

    def test_every_job_with_variables_is_reported(self):
        stub = self.make_stub()  # file never created
        jobs = [
            {"name": "A", "query": SQL},
            {"name": "Plain", "query": "SELECT 1"},
            {"name": "B", "query": "SELECT {TABLE_T_C}"},
        ]
        prepared, errors = self.prepare(stub, jobs)
        self.assertIsNone(prepared)
        self.assertEqual(len(errors), 1)
        message = errors[0][1]
        self.assertIn(f"• A — {MISSING_TEXT}", message)
        self.assertIn(f"• B — {MISSING_TEXT}", message)
        self.assertNotIn("Plain", message)

    def test_plain_sql_runs_without_table_file(self):
        stub = self.make_stub()  # file never created
        prepared, errors = self.prepare(stub, [{"name": "J", "query": "SELECT 1"}])
        self.assertEqual(prepared, ["SELECT 1"])
        self.assertEqual(errors, [])
        self.assertEqual(stub.results_text.timestamp_lines(), [])

    def test_two_calls_write_two_timestamp_lines(self):  # R2-AC-32
        self.write(_payload("T1", ["111"]), MTIME_1)
        stub = self.make_stub()
        self.prepare(stub, [{"name": "J", "query": SQL}])
        self.prepare(stub, [{"name": "J", "query": SQL}])
        lines = stub.results_text.timestamp_lines()
        self.assertEqual(len(lines), 2)
        expected = app.table_data_source_text(_payload("T1", ["111"]), MTIME_1)
        self.assertEqual(lines, [expected, expected])
        self.assertIn("T1", lines[0])

    def test_one_timestamp_line_per_call_with_many_jobs(self):
        self.write(_payload("T1", ["111"]), MTIME_1)
        stub = self.make_stub()
        jobs = [{"name": "A", "query": SQL}, {"name": "B", "query": "SELECT {TABLE_T_C}"}]
        prepared, errors = self.prepare(stub, jobs)
        self.assertEqual(len(prepared), 2)
        self.assertEqual(len(stub.results_text.timestamp_lines()), 1)

    def test_timestamp_line_shows_new_data_after_reload(self):
        self.write(_payload("T1", ["111"]), MTIME_1)
        stub = self.make_stub()
        self.prepare(stub, [{"name": "J", "query": SQL}])
        self.write(_payload("T2", ["222"]), MTIME_2)
        self.prepare(stub, [{"name": "J", "query": SQL}])
        lines = stub.results_text.timestamp_lines()
        self.assertIn("timestamp T1", lines[0])
        self.assertIn("timestamp T2", lines[1])
        self.assertIn(_dt.datetime.fromtimestamp(MTIME_2).strftime("%Y-%m-%d %H:%M:%S"), lines[1])


class ExportTimestampLineTests(_TableDataCase):
    """R2-AC-33 (unit part): Export writes the timestamp line and uses fresh data."""

    def make_export_stub(self, jobs):
        stub = mock.MagicMock()
        stub._block_if_busy.return_value = False
        stub.engine = object()
        stub.get_jobs_to_run.return_value = jobs
        stub._reuse_last_run_results.side_effect = lambda j: j
        stub.results_text = _FakeText()
        stub.table_data_file = self.path
        stub.loaded_table_data = None
        stub.last_table_data_mtime = None
        stub._current_table_data_tables = lambda: GUI._current_table_data_tables(stub)
        return stub

    def run_export(self, stub):
        out = os.path.join(os.path.dirname(self.path), "out.xlsx")
        with mock.patch.object(app.filedialog, "asksaveasfilename", return_value=out), \
                mock.patch.object(app.threading, "Thread") as thread, \
                mock.patch.object(app.messagebox, "showerror"), \
                mock.patch.object(app.messagebox, "showwarning"):
            GUI.export_jobs_to_excel(stub)
        thread.return_value.start.assert_called_once()
        return thread

    def test_export_writes_timestamp_line(self):
        self.write(_payload("T1", ["111"]), MTIME_1)
        stub = self.make_export_stub([{"name": "J", "query": SQL}])
        self.run_export(stub)
        lines = stub.results_text.timestamp_lines()
        self.assertEqual(lines, [app.table_data_source_text(_payload("T1", ["111"]), MTIME_1)])

    def test_export_uses_reloaded_file(self):
        self.write(_payload("T1", ["111"]), MTIME_1)
        stub = self.make_export_stub([{"name": "J", "query": SQL}])
        stub._current_table_data_tables()
        self.write(_payload("T2", ["222"]), MTIME_2)
        self.run_export(stub)
        lines = stub.results_text.timestamp_lines()
        self.assertEqual(len(lines), 1)
        self.assertIn("timestamp T2", lines[0])
        self.assertEqual(stub.loaded_table_data["timestamp"], "T2")

    def test_export_without_table_variables_writes_no_line(self):
        self.write(_payload("T1", ["111"]), MTIME_1)
        stub = self.make_export_stub([{"name": "J", "query": "SELECT 1"}])
        self.run_export(stub)
        self.assertEqual(stub.results_text.timestamp_lines(), [])

    def test_export_with_missing_file_writes_no_line(self):
        stub = self.make_export_stub([{"name": "J", "query": SQL}])
        self.run_export(stub)
        self.assertEqual(stub.results_text.timestamp_lines(), [])


class TableDataSourceTextTests(unittest.TestCase):
    def test_timestamp_and_mtime(self):
        text = app.table_data_source_text({"timestamp": "2026-11-13 09:00:00"}, MTIME_1)
        modified = _dt.datetime.fromtimestamp(MTIME_1).strftime("%Y-%m-%d %H:%M:%S")
        self.assertEqual(
            text,
            f"📅 Table data: timestamp 2026-11-13 09:00:00 · file modified {modified}\n",
        )

    def test_missing_timestamp_shows_dash(self):
        text = app.table_data_source_text({"tables": {}}, MTIME_1)
        self.assertIn("timestamp - ·", text)
        self.assertTrue(text.endswith("\n"))

    def test_empty_timestamp_shows_dash(self):
        self.assertIn("timestamp - ·", app.table_data_source_text({"timestamp": ""}, MTIME_1))

    def test_missing_mtime_shows_dash(self):
        text = app.table_data_source_text({"timestamp": "T1"}, None)
        self.assertEqual(text, "📅 Table data: timestamp T1 · file modified -\n")

    def test_no_data_and_no_mtime(self):
        self.assertEqual(
            app.table_data_source_text(None, None),
            "📅 Table data: timestamp - · file modified -\n",
        )

    def test_non_dict_data(self):
        self.assertIn("timestamp - ·", app.table_data_source_text(["x"], MTIME_1))

    def test_bad_mtime_values_show_dash(self):
        for bad in ("abc", float("nan"), 1e20, -1e20):
            with self.subTest(mtime=bad):
                text = app.table_data_source_text({"timestamp": "T1"}, bad)
                self.assertTrue(text.endswith("file modified -\n"), text)

    def test_single_line(self):
        text = app.table_data_source_text({"timestamp": "T1"}, MTIME_1)
        self.assertEqual(text.count("\n"), 1)


if __name__ == "__main__":
    unittest.main()
