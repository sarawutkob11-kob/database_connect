"""R15-T2 (BH-2): Export Excel handles duplicate column names by position.

Covers R15-AC-5 and R15-AC-6, plus regressions for unique columns, column
names cleaned by ILLEGAL_CHARACTERS_RE and the 32,767-character check.
Both the preloaded (``_export_dataframe`` -> ``preloaded_df.copy()``) path and
the freshly-read (``read_sql_dataframe``) path are exercised.

Everything is written to a temporary directory; no database, no real Tk.
"""

import datetime as dt
import os
import re
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import database_connect_gui as app  # noqa: E402

pd = app.pd
LIMIT = 32767


class _FakeText:
    def __init__(self):
        self.inserted = []

    def delete(self, *_args):
        pass

    def insert(self, _index, value):
        self.inserted.append(value)

    def see(self, _index):
        pass


class _FakeButton:
    def config(self, **_kwargs):
        pass


class _ImmediateThread:
    def __init__(self, target, daemon=None):
        self.target = target
        self.daemon = daemon

    def start(self):
        self.target()


class _StopEvent:
    def is_set(self):
        return False


def _frame(columns, rows):
    """DataFrame with (possibly duplicate) column names."""
    return pd.DataFrame([list(r) for r in rows], columns=list(columns))


def _bangkok(*stamps):
    return pd.Series(pd.to_datetime(list(stamps))).dt.tz_localize("Asia/Bangkok")


class _ExportCase(unittest.TestCase):
    JOB = "Dup job"
    QUERY = "SELECT * FROM t"

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.export_path = os.path.join(self._tmp.name, "export.xlsx")
        self.read_sql = mock.Mock(side_effect=AssertionError("read_sql not expected"))
        self.messagebox = None
        self.output = ""

    def run_export(self, jobs):
        from openpyxl import load_workbook

        stub = app.DatabaseConnectorGUI.__new__(app.DatabaseConnectorGUI)
        stub._block_if_busy = mock.Mock(return_value=False)
        stub._block_if_profile_mismatch = mock.Mock(return_value=False)
        stub._capture_run_target = mock.Mock(return_value=app.RunTarget(mock.Mock(), None))
        stub._reuse_last_run_results = mock.Mock(
            side_effect=lambda items: [dict(item) for item in items]
        )
        stub._start_stoppable_run = mock.Mock()
        stub._stop_event = _StopEvent()
        stub.engine = mock.Mock()
        stub.results_text = _FakeText()
        stub.export_excel_btn = _FakeButton()
        stub.root = mock.Mock()
        stub.root.after.side_effect = lambda _delay, callback: callback()
        stub.read_sql_dataframe = self.read_sql

        with mock.patch.object(
            app.filedialog, "asksaveasfilename", return_value=self.export_path
        ), mock.patch.object(app.threading, "Thread", _ImmediateThread), mock.patch.object(
            app, "messagebox"
        ) as messagebox:
            stub.export_jobs_to_excel(jobs_override=jobs)

        self.messagebox = messagebox
        self.output = "".join(stub.results_text.inserted)
        self.assertNotIn("EXPORT EXCEL FAILED", self.output)
        messagebox.showerror.assert_not_called()
        workbook = load_workbook(self.export_path)
        self.addCleanup(workbook.close)
        return workbook

    def export_preloaded(self, frame):
        job = {"name": self.JOB, "query": self.QUERY, "_export_dataframe": frame}
        return self.run_export([job])[self.JOB]

    def export_read(self, frame):
        self.read_sql = mock.Mock(return_value=frame)
        ws = self.run_export([{"name": self.JOB, "query": self.QUERY}])[self.JOB]
        self.read_sql.assert_called_once()
        return ws

    def export_both(self):
        """Yield (label, exporter) for the preloaded and the freshly-read path."""
        return (("preloaded", self.export_preloaded), ("read", self.export_read))

    # ---- assertions ----------------------------------------------------
    def counts(self):
        found = {}
        for label, pattern in (
            ("ok", r"Success: (\d+)\n"),
            ("warnings", r"Warning: (\d+)\n"),
            ("failed", r"Failed: (\d+)\n"),
            ("skipped", r"Skipped \(not SELECT\): (\d+)\n"),
        ):
            matches = re.findall(pattern, self.output)
            self.assertEqual(len(matches), 1, f"summary line for {label}")
            found[label] = int(matches[0])
        return found

    def assert_counts(self, ok=0, warnings=0, failed=0, skipped=0):
        self.assertEqual(
            self.counts(),
            {"ok": ok, "warnings": warnings, "failed": failed, "skipped": skipped},
        )
        summary = self.messagebox.showinfo.call_args[0][1]
        self.assertIn(
            f"Success: {ok} | Warning: {warnings} | Failed: {failed} | Skipped: {skipped}",
            summary,
        )

    def assert_success_sheet(self, ws):
        self.assertRegex(self.output, r"Status: \S+ Success")
        self.assertNotRegex(self.output, r"Status: \S+ Failed")
        self.assertNotEqual(ws["A1"].value, "Status", "job sheet is a Failed sheet")
        self.assert_counts(ok=1)

    def header(self, ws, n):
        return [ws.cell(row=1, column=c).value for c in range(1, n + 1)]

    def row(self, ws, r, n):
        return [ws.cell(row=r, column=c).value for c in range(1, n + 1)]


# ------------------------------------------------------------------ R15-AC-5
class DuplicateColumnBasicTests(_ExportCase):
    def test_id_name_id_exports_success_with_positional_values(self):
        for label, export in self.export_both():
            with self.subTest(path=label):
                frame = _frame(["ID", "NAME", "ID"], [(1, "a\x01b", 2)])
                ws = export(frame)

                self.assert_success_sheet(ws)
                self.assertEqual(self.header(ws, 3), ["ID", "NAME", "ID"])
                self.assertEqual(self.row(ws, 2, 3), [1, "ab", 2])
                self.assertIsNone(ws.cell(row=1, column=4).value)
                self.assertIn("Columns: 3\n", self.output)

    def test_multiple_rows_and_triplicate_names(self):
        frame = _frame(
            ["X", "X", "X"],
            [(1, "p\x02", 3.5), (None, "q", 4), (7, "r\x1f s", None)],
        )
        ws = self.export_preloaded(frame)

        self.assert_success_sheet(ws)
        self.assertEqual(self.header(ws, 3), ["X", "X", "X"])
        self.assertEqual(self.row(ws, 2, 3), [1, "p", 3.5])
        self.assertEqual(self.row(ws, 3, 3), [app.DB_NULL_TEXT, "q", 4])
        self.assertEqual(self.row(ws, 4, 3), [7, "r s", app.DB_NULL_TEXT])

    def test_preloaded_frame_is_not_modified(self):
        frame = _frame(["ID", "NAME", "ID"], [(1, "a\x01b", 2)])
        snapshot = frame.copy()
        self.export_preloaded(frame)

        self.assertEqual(list(frame.columns), ["ID", "NAME", "ID"])
        self.assertTrue(frame.equals(snapshot))


# ------------------------------------------------------------------ R15-AC-6
class DuplicateColumnTypeTests(_ExportCase):
    def test_duplicate_tz_columns_are_made_naive_local_time(self):
        for label, export in self.export_both():
            with self.subTest(path=label):
                frame = pd.concat(
                    [
                        _bangkok("2026-01-02 03:04:05", "2026-12-31 23:59:58"),
                        _bangkok("2025-06-15 12:00:00", "2024-02-29 00:00:01"),
                    ],
                    axis=1,
                )
                frame.columns = ["TS", "TS"]
                ws = export(frame)

                self.assert_success_sheet(ws)
                self.assertEqual(self.header(ws, 2), ["TS", "TS"])
                expected = [
                    [dt.datetime(2026, 1, 2, 3, 4, 5), dt.datetime(2025, 6, 15, 12, 0, 0)],
                    [dt.datetime(2026, 12, 31, 23, 59, 58),
                     dt.datetime(2024, 2, 29, 0, 0, 1)],
                ]
                for r, values in enumerate(expected, start=2):
                    for c, value in enumerate(values, start=1):
                        cell = ws.cell(row=r, column=c)
                        self.assertIsInstance(cell.value, dt.datetime, cell.coordinate)
                        self.assertIsNone(cell.value.tzinfo, cell.coordinate)
                        self.assertEqual(cell.value, value, cell.coordinate)

    def test_duplicate_columns_of_different_types(self):
        for label, export in self.export_both():
            with self.subTest(path=label):
                frame = pd.concat(
                    [
                        pd.Series(["a\x01b", "c\x0bd", "plain"], dtype=object),
                        pd.Series([10, 20, 30]),
                    ],
                    axis=1,
                )
                frame.columns = ["V", "V"]
                self.assertEqual(frame.iloc[:, 0].dtype, object)
                self.assertNotEqual(frame.iloc[:, 1].dtype, object)
                ws = export(frame)

                self.assert_success_sheet(ws)
                self.assertEqual(self.header(ws, 2), ["V", "V"])
                self.assertEqual([ws.cell(row=r, column=1).value for r in (2, 3, 4)],
                                 ["ab", "cd", "plain"])
                self.assertEqual([ws.cell(row=r, column=2).value for r in (2, 3, 4)],
                                 [10, 20, 30])
                for r in (2, 3, 4):
                    self.assertIsInstance(ws.cell(row=r, column=2).value, int)

    def test_duplicate_mixed_tz_text_number(self):
        frame = pd.concat(
            [
                _bangkok("2026-03-04 05:06:07"),
                pd.Series(["x\x01y"]),
                pd.Series([42]),
            ],
            axis=1,
        )
        frame.columns = ["C", "C", "C"]
        ws = self.export_preloaded(frame)

        self.assert_success_sheet(ws)
        self.assertEqual(self.header(ws, 3), ["C", "C", "C"])
        self.assertEqual(self.row(ws, 2, 3), [dt.datetime(2026, 3, 4, 5, 6, 7), "xy", 42])


# --------------------------------------------------------------- regressions
class UniqueColumnRegressionTests(_ExportCase):
    def test_unique_columns_unchanged(self):
        for label, export in self.export_both():
            with self.subTest(path=label):
                frame = pd.DataFrame(
                    {
                        "ID": [1, 2],
                        "NAME": ["a\x01b", "  keep spaces  "],
                        "TS": _bangkok("2026-01-02 03:04:05", "2026-01-03 00:00:00"),
                        "AMT": [1.5, None],
                    }
                )
                ws = export(frame)

                self.assert_success_sheet(ws)
                self.assertEqual(self.header(ws, 4), ["ID", "NAME", "TS", "AMT"])
                self.assertEqual(
                    self.row(ws, 2, 4), [1, "ab", dt.datetime(2026, 1, 2, 3, 4, 5), 1.5]
                )
                self.assertEqual(
                    self.row(ws, 3, 4),
                    [2, "  keep spaces  ", dt.datetime(2026, 1, 3), app.DB_NULL_TEXT],
                )

    def test_column_names_are_cleaned_by_illegal_characters_re(self):
        for label, export in self.export_both():
            with self.subTest(path=label):
                frame = _frame(["A\x01B", "N\x02", "A\x01B"], [(1, "v", 2)])
                ws = export(frame)

                self.assert_success_sheet(ws)
                self.assertEqual(self.header(ws, 3), ["AB", "N", "AB"])
                self.assertEqual(self.row(ws, 2, 3), [1, "v", 2])

    def test_non_string_column_names_still_written(self):
        frame = _frame([1, 1, "x"], [("a", "b", "c")])
        ws = self.export_preloaded(frame)

        self.assert_success_sheet(ws)
        self.assertEqual([str(v) for v in self.header(ws, 3)], ["1", "1", "x"])
        self.assertEqual(self.row(ws, 2, 3), ["a", "b", "c"])

    def test_oversized_cell_in_duplicate_column_is_blank_and_warns(self):
        for label, export in self.export_both():
            with self.subTest(path=label):
                frame = _frame(
                    ["ID", "TXT", "TXT"],
                    [(1, "short", "a" * (LIMIT + 1)), (2, "b" * LIMIT, "ok")],
                )
                ws = export(frame)

                self.assertEqual(self.header(ws, 3), ["ID", "TXT", "TXT"])
                self.assertEqual(ws["A2"].value, 1)
                self.assertEqual(ws["B2"].value, "short")
                self.assertIn(ws["C2"].value, (None, ""))
                self.assertTrue(ws["B3"].value == "b" * LIMIT, "B3 changed")
                self.assertEqual(ws["C3"].value, "ok")
                warnings = [ln for ln in self.output.splitlines() if "32,767" in ln]
                self.assertEqual(len(warnings), 1)
                self.assertIn(f"Job '{self.JOB}', column 'TXT'", warnings[0])
                self.assertRegex(self.output, r"Status: \S+ Warning")
                self.assert_counts(warnings=1)

    def test_oversized_cell_in_unique_column_still_warns(self):
        frame = pd.DataFrame({"P": ["a" * (LIMIT + 1), "x"], "Q": ["y", "z"]})
        ws = self.export_preloaded(frame)

        self.assertIn(ws["A2"].value, (None, ""))
        self.assertEqual(ws["A3"].value, "x")
        self.assertEqual([ws["B2"].value, ws["B3"].value], ["y", "z"])
        self.assertIn("column 'P' contains string values over", self.output)
        self.assert_counts(warnings=1)

    def test_empty_frame_with_duplicate_columns_is_no_data(self):
        frame = pd.DataFrame(columns=["ID", "ID"])
        ws = self.export_preloaded(frame)

        self.assertEqual(self.header(ws, 2), ["ID", "ID"])
        self.assertIn("No Data Found", self.output)
        self.assertEqual(ws["A3"].value, self.QUERY)
        self.assert_counts(ok=1)


if __name__ == "__main__":
    unittest.main()
