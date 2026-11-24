"""R15-T5 (BH-4): dates before 1900-01-01 are exported to Excel as text.

Covers R15-AC-10 (``excel_db_value`` directly) and R15-AC-11 (real export
into a temporary directory). No database, no real Tk.
"""

import datetime as dt
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import database_connect_gui as app  # noqa: E402

pd = app.pd
UTC = dt.timezone.utc
BANGKOK = dt.timezone(dt.timedelta(hours=7))
DATE_FORMATS = ("yyyy-mm-dd", "yyyy-mm-dd hh:mm:ss.000", "hh:mm:ss")


# ----------------------------------------------------------------- R15-AC-10
class ExcelDbValuePre1900Tests(unittest.TestCase):
    def assert_text(self, value):
        result = app.excel_db_value(value)
        self.assertIsInstance(result, str, repr(value))
        self.assertEqual(result, app.format_db_value(value), repr(value))
        return result

    def test_min_date_constant(self):
        self.assertEqual(app.EXCEL_MIN_DATE, dt.date(1900, 1, 1))

    def test_ac10_values_before_1900_become_text(self):
        for value in (
            dt.date(1899, 12, 31),
            dt.datetime(1850, 6, 1, 12, 0),
            pd.Timestamp("1800-01-01"),
            dt.datetime(1899, 12, 31, 23, 59, 59, tzinfo=UTC),
        ):
            with self.subTest(value=repr(value)):
                self.assert_text(value)

    def test_expected_text_values(self):
        self.assertEqual(self.assert_text(dt.date(1899, 12, 31)), "1899-12-31")
        self.assertEqual(
            self.assert_text(dt.datetime(1850, 6, 1, 12, 0)), "1850-06-01 12:00:00.000"
        )
        self.assertEqual(
            self.assert_text(pd.Timestamp("1800-01-01")), "1800-01-01 00:00:00.000"
        )

    def test_other_early_values(self):
        for value in (
            dt.date(1, 1, 1),
            dt.date(1000, 6, 15),
            dt.date(1899, 1, 1),
            dt.datetime(1, 1, 1),
            dt.datetime(1899, 12, 31, 23, 59, 59, 999999),
            dt.datetime(1899, 12, 31, 23, 59, 59, 999999, tzinfo=UTC),
            dt.datetime(1850, 1, 1, tzinfo=BANGKOK),
            pd.Timestamp("1899-12-31 23:59:59.999999"),
            pd.Timestamp("1700-03-04 05:06:07", tz="Asia/Bangkok"),
            pd.Timestamp("1899-12-31 12:00", tz="UTC"),
        ):
            with self.subTest(value=repr(value)):
                self.assert_text(value)

    def test_boundary_last_microsecond_before_1900_is_text(self):
        value = dt.datetime(1899, 12, 31, 23, 59, 59, 999999)
        self.assertEqual(self.assert_text(value), "1899-12-31 23:59:59.999")

    def test_tz_compared_after_dropping_tz(self):
        # 1900-01-01 00:00 UTC -> local naive 1900-01-01: still a date
        result = app.excel_db_value(dt.datetime(1900, 1, 1, tzinfo=UTC))
        self.assertIsInstance(result, dt.datetime)
        self.assertIsNone(result.tzinfo)
        self.assertEqual(result, dt.datetime(1900, 1, 1))
        # 1900-01-01 00:30 +07:00 is 1899 in UTC but the local wall time is 1900
        result = app.excel_db_value(dt.datetime(1900, 1, 1, 0, 30, tzinfo=BANGKOK))
        self.assertEqual(result, dt.datetime(1900, 1, 1, 0, 30))
        self.assertIsNone(result.tzinfo)
        # 1899-12-31 23:00 -05:00 is 1900 in UTC but local wall time is 1899 -> text
        value = dt.datetime(1899, 12, 31, 23, 0, tzinfo=dt.timezone(dt.timedelta(hours=-5)))
        self.assert_text(value)

    def test_values_from_1900_unchanged(self):
        cases = [
            (dt.date(1900, 1, 1), dt.date(1900, 1, 1), dt.date),
            (dt.date(2024, 1, 15), dt.date(2024, 1, 15), dt.date),
            (dt.datetime(1900, 1, 1, 0, 0), dt.datetime(1900, 1, 1), dt.datetime),
            (
                pd.Timestamp("2024-01-15 10:30"),
                dt.datetime(2024, 1, 15, 10, 30),
                dt.datetime,
            ),
            (
                pd.Timestamp("2024-01-15 10:30", tz="Asia/Bangkok"),
                dt.datetime(2024, 1, 15, 10, 30),
                dt.datetime,
            ),
            (
                dt.datetime(2024, 1, 15, 10, 30, tzinfo=UTC),
                dt.datetime(2024, 1, 15, 10, 30),
                dt.datetime,
            ),
        ]
        for value, expected, kind in cases:
            with self.subTest(value=repr(value)):
                result = app.excel_db_value(value)
                self.assertNotIsInstance(result, str)
                self.assertIsInstance(result, kind)
                if kind is dt.date:
                    self.assertNotIsInstance(result, dt.datetime)
                else:
                    self.assertIsNone(result.tzinfo)
                self.assertEqual(result, expected)

    def test_time_unchanged(self):
        for value in (dt.time(8, 0), dt.time(0, 0), dt.time(23, 59, 59, 999999)):
            with self.subTest(value=value):
                result = app.excel_db_value(value)
                self.assertIsInstance(result, dt.time)
                self.assertEqual(result, value)

    def test_nat_and_none_are_null(self):
        self.assertEqual(app.excel_db_value(pd.NaT), app.DB_NULL_TEXT)
        self.assertEqual(app.excel_db_value(None), app.DB_NULL_TEXT)

    def test_other_types_unchanged(self):
        self.assertEqual(app.excel_db_value(42), 42)
        self.assertEqual(app.excel_db_value(1.5), 1.5)
        self.assertEqual(app.excel_db_value(True), "true")
        self.assertEqual(app.excel_db_value("1899-12-31"), "1899-12-31")


# ------------------------------------------------------------- export helpers
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


class _ExportCase(unittest.TestCase):
    JOB = "Old dates"
    QUERY = "SELECT * FROM t"

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.export_path = os.path.join(self._tmp.name, "export.xlsx")
        self.output = ""

    def run_export(self, frame, read=False):
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
        if read:
            stub.read_sql_dataframe = mock.Mock(return_value=frame)
            job = {"name": self.JOB, "query": self.QUERY}
        else:
            stub.read_sql_dataframe = mock.Mock(side_effect=AssertionError("no read"))
            job = {"name": self.JOB, "query": self.QUERY, "_export_dataframe": frame}

        with mock.patch.object(
            app.filedialog, "asksaveasfilename", return_value=self.export_path
        ), mock.patch.object(app.threading, "Thread", _ImmediateThread), mock.patch.object(
            app, "messagebox"
        ) as messagebox:
            stub.export_jobs_to_excel(jobs_override=[job])

        self.output = "".join(stub.results_text.inserted)
        self.assertNotIn("EXPORT EXCEL FAILED", self.output)
        messagebox.showerror.assert_not_called()
        self.assertRegex(self.output, r"Status: \S+ Success")
        if read:
            stub.read_sql_dataframe.assert_called_once()
        workbook = load_workbook(self.export_path)
        self.addCleanup(workbook.close)
        ws = workbook[self.JOB]
        self.assertNotEqual(ws["A1"].value, "Status", "job sheet is a Failed sheet")
        return ws

    def assert_text_cell(self, cell, original):
        self.assertEqual(cell.data_type, "s", cell.coordinate)
        self.assertFalse(cell.is_date, cell.coordinate)
        self.assertEqual(cell.value, app.format_db_value(original), cell.coordinate)
        self.assertNotIn(cell.number_format, DATE_FORMATS, cell.coordinate)
        self.assertEqual(cell.number_format, "@", cell.coordinate)

    def assert_date_cell(self, cell, expected, fmt):
        self.assertTrue(cell.is_date, cell.coordinate)
        self.assertEqual(cell.number_format, fmt, cell.coordinate)
        self.assertEqual(cell.value, expected, cell.coordinate)


# ----------------------------------------------------------------- R15-AC-11
class ExportPre1900Tests(_ExportCase):
    def test_ac11_date_column_first_row_text_second_row_date(self):
        for read in (False, True):
            with self.subTest(read=read):
                frame = pd.DataFrame(
                    {"D": [dt.date(1899, 12, 31), dt.date(1900, 1, 1)]}
                )
                ws = self.run_export(frame, read=read)
                self.assertEqual(ws["A1"].value, "D")
                self.assert_text_cell(ws["A2"], dt.date(1899, 12, 31))
                self.assertEqual(ws["A2"].value, "1899-12-31")
                self.assert_date_cell(ws["A3"], dt.datetime(1900, 1, 1), "yyyy-mm-dd")

    def test_datetime64_column_mixed_before_and_after_1900(self):
        stamps = [
            pd.Timestamp("1850-06-01 12:00:00"),
            pd.Timestamp("1899-12-31 23:59:59.999"),
            pd.Timestamp("1900-01-01 00:00:00"),
            pd.Timestamp("2024-01-15 10:30:00"),
        ]
        frame = pd.DataFrame({"TS": pd.Series(stamps)})
        self.assertTrue(pd.api.types.is_datetime64_any_dtype(frame["TS"]))
        ws = self.run_export(frame)

        self.assert_text_cell(ws["A2"], stamps[0])
        self.assertEqual(ws["A2"].value, "1850-06-01 12:00:00.000")
        self.assert_text_cell(ws["A3"], stamps[1])
        self.assertEqual(ws["A3"].value, "1899-12-31 23:59:59.999")
        fmt = "yyyy-mm-dd hh:mm:ss.000"
        self.assert_date_cell(ws["A4"], dt.datetime(1900, 1, 1), fmt)
        self.assert_date_cell(ws["A5"], dt.datetime(2024, 1, 15, 10, 30), fmt)

    def test_tz_datetime64_column_mixed_before_and_after_1900(self):
        series = pd.Series(
            pd.to_datetime(
                ["1800-01-01 08:00:00", "1899-12-31 23:00:00", "1900-01-01 00:30:00",
                 "2026-03-04 05:06:07"]
            )
        ).dt.tz_localize("Asia/Bangkok")
        self.assertIsInstance(series.dtype, pd.DatetimeTZDtype)
        for read in (False, True):
            with self.subTest(read=read):
                frame = pd.DataFrame({"TZ": series, "N": [1, 2, 3, 4]})
                ws = self.run_export(frame, read=read)

                self.assert_text_cell(ws["A2"], series.iloc[0])
                self.assertTrue(ws["A2"].value.startswith("1800-01-01 08:00:00"))
                self.assert_text_cell(ws["A3"], series.iloc[1])
                self.assertTrue(ws["A3"].value.startswith("1899-12-31 23:00:00"))
                fmt = "yyyy-mm-dd hh:mm:ss.000"
                self.assert_date_cell(ws["A4"], dt.datetime(1900, 1, 1, 0, 30), fmt)
                self.assert_date_cell(ws["A5"], dt.datetime(2026, 3, 4, 5, 6, 7), fmt)
                self.assertEqual([ws[f"B{r}"].value for r in range(2, 6)], [1, 2, 3, 4])

    def test_object_column_with_pre1900_datetime_and_nat(self):
        frame = pd.DataFrame(
            {"X": pd.Series(
                [dt.datetime(1899, 6, 1, 1, 2, 3), None, dt.datetime(2001, 2, 3, 4, 5, 6)],
                dtype=object,
            )}
        )
        ws = self.run_export(frame)
        self.assert_text_cell(ws["A2"], dt.datetime(1899, 6, 1, 1, 2, 3))
        self.assertEqual(ws["A3"].value, app.DB_NULL_TEXT)
        self.assert_date_cell(
            ws["A4"], dt.datetime(2001, 2, 3, 4, 5, 6), "yyyy-mm-dd hh:mm:ss.000"
        )

    def test_all_pre1900_date_column(self):
        values = [dt.date(1, 1, 1), dt.date(1066, 10, 14), dt.date(1899, 12, 31)]
        ws = self.run_export(pd.DataFrame({"D": values}))
        for r, value in enumerate(values, start=2):
            self.assert_text_cell(ws.cell(row=r, column=1), value)


if __name__ == "__main__":
    unittest.main()
