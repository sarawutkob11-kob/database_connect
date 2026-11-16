"""R7-T3 / R7-T4 (R7-3): Excel's 32,767-character cell limit, counted in UTF-16 units.

Covers R7-AC-9 .. R7-AC-15: result cells (C-2), the Skipped / Failed / No Data
sheets and the SQL annotation under the data.

Everything is written to a temporary directory; no database, no real Tk.
Assertions on long strings use assertTrue(a == b) so a failure never dumps
32k characters (or characters outside cp874) to the console.
"""

import os
import re
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import database_connect_gui as app  # noqa: E402

LIMIT = 32767
EMOJI = "\U0001F600"  # 2 UTF-16 units
THAI = "ก"  # 1 UTF-16 unit (BMP)
COLUMN_WARNING = "is over Excel's 32,767-character limit; the cell was left blank."


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


def _pad(prefix: str, total: int, fill: str = "a") -> str:
    """`prefix` followed by `fill` up to exactly `total` characters."""
    return prefix + fill * (total - len(prefix))


class _ExportCase(unittest.TestCase):
    """Runs export_jobs_to_excel on a stub and reads the workbook back."""

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
        # the summary dialog carries the same numbers
        summary = self.messagebox.showinfo.call_args[0][1]
        self.assertIn(
            f"Success: {ok} | Warning: {warnings} | Failed: {failed} | Skipped: {skipped}",
            summary,
        )

    def limit_warnings(self):
        return [line for line in self.output.splitlines() if "32,767" in line]

    def assert_blank(self, cell):
        self.assertIn(cell.value, (None, ""), f"cell {cell.coordinate} should be blank")

    def assert_text(self, cell, expected):
        self.assertTrue(cell.value == expected, f"cell {cell.coordinate} was changed")
        self.assertEqual(cell.data_type, "s", f"cell {cell.coordinate} is not literal text")

    def column_warning(self, job_name, column):
        return f"Warning: Job '{job_name}', column '{column}' {COLUMN_WARNING}"

    def sql_warning(self, job_name, line_no):
        return f"Warning: Job '{job_name}', SQL line {line_no} {COLUMN_WARNING}"


# ---------------------------------------------------------------- helper (R7-T3)
class ExcelTextTooLongHelperTests(unittest.TestCase):
    def test_limit_constant(self):
        self.assertEqual(app.EXCEL_MAX_CELL_CHARS, 32767)

    def test_non_strings_are_never_too_long(self):
        for value in (None, 0, 10 ** 40000, 1.5, True, b"x" * 40000, ["a" * 40000],
                      float("nan"), app.pd.NaT, app.pd.Timestamp("2026-01-01")):
            with self.subTest(kind=type(value).__name__):
                self.assertIs(app._excel_text_too_long(value), False)

    def test_empty_and_short_strings(self):
        for value in ("", "a", "a" * 16383, "a" * 16384, EMOJI * 8191, EMOJI * 8192):
            with self.subTest(length=len(value)):
                self.assertIs(app._excel_text_too_long(value), False)

    def test_ascii_boundary(self):
        self.assertIs(app._excel_text_too_long("a" * (LIMIT - 1)), False)
        self.assertIs(app._excel_text_too_long("a" * LIMIT), False)
        self.assertIs(app._excel_text_too_long("a" * (LIMIT + 1)), True)
        self.assertIs(app._excel_text_too_long("a" * 100000), True)

    def test_thai_bmp_boundary(self):
        self.assertIs(app._excel_text_too_long(THAI * LIMIT), False)
        self.assertIs(app._excel_text_too_long(THAI * (LIMIT + 1)), True)

    def test_astral_characters_count_as_two_units(self):
        self.assertIs(app._excel_text_too_long(EMOJI * 16383), False)  # 32,766 units
        self.assertIs(app._excel_text_too_long(EMOJI * 16383 + "a"), False)  # 32,767
        self.assertIs(app._excel_text_too_long("a" + EMOJI * 16383), False)  # 32,767
        self.assertIs(app._excel_text_too_long(EMOJI * 16384), True)  # 32,768
        self.assertIs(app._excel_text_too_long(EMOJI * 16383 + "ab"), True)  # 32,768

    def test_mixed_text_just_over_half_the_limit(self):
        # 16,384 code points: only the UTF-16 count can tell these apart
        self.assertIs(app._excel_text_too_long("a" * 16384), False)
        self.assertIs(app._excel_text_too_long(EMOJI * 16384), True)
        self.assertIs(app._excel_text_too_long(EMOJI + "a" * (LIMIT - 2)), False)
        self.assertIs(app._excel_text_too_long(EMOJI + "a" * (LIMIT - 1)), True)

    def test_lone_surrogate_does_not_raise(self):
        self.assertIs(app._excel_text_too_long("\ud83d" * LIMIT), False)
        self.assertIs(app._excel_text_too_long("\ud83d" * (LIMIT + 1)), True)
        self.assertIs(app._excel_text_too_long("\ud83d" * 20000), False)
        self.assertIs(app._excel_text_too_long("\udc00" + "a" * 20000), False)

    def test_matches_spec_definition(self):
        for value in ("a" * 20000, THAI * 30000, EMOJI * 16384, EMOJI * 16000 + "a" * 767,
                      EMOJI * 16000 + "a" * 768, THAI * LIMIT, THAI * (LIMIT + 1)):
            with self.subTest(length=len(value)):
                expected = len(value.encode("utf-16-le")) // 2 > 32767
                self.assertIs(app._excel_text_too_long(value), expected)


# ---------------------------------------------------------- result cells (R7-T3)
class ResultCellLimitTests(_ExportCase):
    JOB = "Result cells"

    def export_values(self, values):
        frame = app.pd.DataFrame({"payload": values, "other": ["x"] * len(values)})
        job = {"name": self.JOB, "query": "SELECT payload FROM results",
               "_export_dataframe": frame}
        return self.run_export([job])[self.JOB]

    def test_emoji_over_limit_is_blank_and_counted_as_warning(self):
        ws = self.export_values([EMOJI * 16384, EMOJI * 16383 + "a", "short"])

        self.assert_blank(ws["A2"])
        self.assert_text(ws["A3"], EMOJI * 16383 + "a")
        self.assert_text(ws["A4"], "short")
        self.assert_text(ws["B2"], "x")
        self.assertIn(f"Job '{self.JOB}'", self.output)
        self.assertIn("column 'payload' contains string values over", self.output)
        self.assertNotIn("column 'other'", self.output)
        self.assertEqual(len(self.limit_warnings()), 1)
        self.assertRegex(self.output, r"Status: \S+ Warning")
        self.assert_counts(warnings=1)

    def test_exactly_at_limit_is_written_without_warning(self):
        ws = self.export_values(["a" * LIMIT, THAI * LIMIT, EMOJI * 16383 + "a"])

        self.assert_text(ws["A2"], "a" * LIMIT)
        self.assert_text(ws["A3"], THAI * LIMIT)
        self.assert_text(ws["A4"], EMOJI * 16383 + "a")
        self.assertEqual(self.limit_warnings(), [])
        self.assertRegex(self.output, r"Status: \S+ Success")
        self.assert_counts(ok=1)

    def test_one_unit_over_limit_is_blank(self):
        ws = self.export_values(["a" * (LIMIT + 1), THAI * (LIMIT + 1), "keep"])

        self.assert_blank(ws["A2"])
        self.assert_blank(ws["A3"])
        self.assert_text(ws["A4"], "keep")
        self.assertEqual(len(self.limit_warnings()), 1)  # one line per column
        self.assert_counts(warnings=1)


# ------------------------------------------------------------- Skipped (R7-AC-9)
class SkippedSheetLimitTests(_ExportCase):
    JOB = "Skipped job"
    MESSAGE = "Not a SELECT query - not executed during export"

    def export_query(self, query):
        return self.run_export([{"name": self.JOB, "query": query}])[self.JOB]

    def assert_fixed_cells(self, ws):
        self.assertEqual([c.value for c in ws[1]], ["Status", "Message", "Query"])
        self.assert_text(ws["A2"], "Skipped")
        self.assert_text(ws["B2"], self.MESSAGE)

    def test_oversized_query_is_blank_and_still_counted_as_skipped(self):
        for label, query in (
            ("ascii", _pad("UPDATE t SET c = 1 -- ", LIMIT + 1)),
            ("thai", _pad("UPDATE t SET c = 1 -- ", LIMIT + 1, THAI)),
            ("emoji", "UPDATE t SET c = 1 -- " + EMOJI * 16384),
        ):
            with self.subTest(text=label):
                ws = self.export_query(query)

                self.assert_fixed_cells(ws)
                self.assert_blank(ws["C2"])
                self.assertIn(self.column_warning(self.JOB, "Query"), self.output)
                self.assertEqual(len(self.limit_warnings()), 1)
                self.assert_counts(skipped=1)
                self.read_sql.assert_not_called()

    def test_query_exactly_at_limit_is_written(self):
        for label, fill in (("ascii", "a"), ("thai", THAI)):
            with self.subTest(text=label):
                query = _pad("UPDATE t SET c = 1 -- ", LIMIT, fill)
                ws = self.export_query(query)

                self.assert_fixed_cells(ws)
                self.assert_text(ws["C2"], query)
                self.assertEqual(self.limit_warnings(), [])
                self.assert_counts(skipped=1)

    def test_short_query_is_unchanged(self):
        ws = self.export_query("=UPDATE t SET c = 1")

        self.assert_fixed_cells(ws)
        self.assert_text(ws["C2"], "=UPDATE t SET c = 1")  # literal, not a formula
        self.assertEqual(self.limit_warnings(), [])
        self.assert_counts(skipped=1)


# ------------------------------------------------------------- Failed (R7-AC-10)
class FailedSheetLimitTests(_ExportCase):
    JOB = "Failed job"

    def export_failure(self, query, error_text):
        self.read_sql = mock.Mock(side_effect=RuntimeError(error_text))
        return self.run_export([{"name": self.JOB, "query": query}])[self.JOB]

    def test_oversized_query_and_error_are_both_blank(self):
        ws = self.export_failure(_pad("SELECT c FROM t -- ", LIMIT + 1), "e" * (LIMIT + 1))

        self.assertEqual([c.value for c in ws[1]], ["Status", "Error", "Query"])
        self.assert_text(ws["A2"], "Failed")
        self.assert_blank(ws["B2"])
        self.assert_blank(ws["C2"])
        self.assertIn(self.column_warning(self.JOB, "Error"), self.output)
        self.assertIn(self.column_warning(self.JOB, "Query"), self.output)
        self.assertEqual(len(self.limit_warnings()), 2)
        self.assert_counts(failed=1)

    def test_only_oversized_error_is_blank(self):
        ws = self.export_failure("SELECT c FROM t", THAI * (LIMIT + 1))

        self.assert_text(ws["A2"], "Failed")
        self.assert_blank(ws["B2"])
        self.assert_text(ws["C2"], "SELECT c FROM t")
        self.assertIn(self.column_warning(self.JOB, "Error"), self.output)
        self.assertNotIn(self.column_warning(self.JOB, "Query"), self.output)
        self.assertEqual(len(self.limit_warnings()), 1)
        self.assert_counts(failed=1)

    def test_only_oversized_query_is_blank(self):
        ws = self.export_failure("SELECT c FROM t -- " + EMOJI * 16384, "boom")

        self.assert_text(ws["A2"], "Failed")
        self.assert_text(ws["B2"], "boom")
        self.assert_blank(ws["C2"])
        self.assertIn(self.column_warning(self.JOB, "Query"), self.output)
        self.assertNotIn(self.column_warning(self.JOB, "Error"), self.output)
        self.assertEqual(len(self.limit_warnings()), 1)
        self.assert_counts(failed=1)

    def test_values_exactly_at_limit_are_written(self):
        query = _pad("SELECT c FROM t -- ", LIMIT, THAI)
        ws = self.export_failure(query, "e" * LIMIT)

        self.assert_text(ws["A2"], "Failed")
        self.assert_text(ws["B2"], "e" * LIMIT)
        self.assert_text(ws["C2"], query)
        self.assertEqual(self.limit_warnings(), [])
        self.assert_counts(failed=1)

    def test_short_values_are_unchanged(self):
        ws = self.export_failure("SELECT c FROM t", "=boom")

        self.assert_text(ws["A2"], "Failed")
        self.assert_text(ws["B2"], "=boom")
        self.assert_text(ws["C2"], "SELECT c FROM t")
        self.assertIn("Error : =boom", self.output)
        self.assertEqual(self.limit_warnings(), [])
        self.assert_counts(failed=1)


# ------------------------------------------------------------ No Data (R7-AC-11)
class NoDataSheetLimitTests(_ExportCase):
    JOB = "Empty job"

    def export_lines(self, lines):
        job = {
            "name": self.JOB,
            "query": "\n".join(lines),
            "_export_dataframe": app.pd.DataFrame(columns=["c"]),
        }
        return self.run_export([job])[self.JOB]

    def test_oversized_line_is_blank_and_job_is_a_warning(self):
        for label, long_line in (
            ("ascii", "a" * (LIMIT + 1)),
            ("thai", THAI * (LIMIT + 1)),
            ("emoji", EMOJI * 16384),
        ):
            with self.subTest(text=label):
                ws = self.export_lines(["SELECT c", long_line, "FROM t", "WHERE 1 = 0"])

                self.assertEqual(ws["A1"].value, "c")
                self.assert_blank(ws["A2"])
                self.assert_text(ws["A3"], "SELECT c")
                self.assert_blank(ws["A4"])
                self.assert_text(ws["A5"], "FROM t")
                self.assert_text(ws["A6"], "WHERE 1 = 0")
                self.assertEqual(ws.max_row, 6)
                self.assertIn(self.sql_warning(self.JOB, 2), self.output)
                self.assertEqual(len(self.limit_warnings()), 1)
                self.assert_counts(warnings=1)

    def test_several_oversized_lines_count_one_warning(self):
        ws = self.export_lines(["a" * (LIMIT + 1), "SELECT c FROM t", "b" * (LIMIT + 1)])

        self.assert_blank(ws["A3"])
        self.assert_text(ws["A4"], "SELECT c FROM t")
        self.assert_blank(ws["A5"])
        self.assertIn(self.sql_warning(self.JOB, 1), self.output)
        self.assertIn(self.sql_warning(self.JOB, 3), self.output)
        self.assertEqual(len(self.limit_warnings()), 2)
        self.assert_counts(warnings=1)

    def test_line_exactly_at_limit_is_written_and_job_is_a_success(self):
        for label, line in (("ascii", "a" * LIMIT), ("thai", THAI * LIMIT),
                            ("emoji", EMOJI * 16383 + "a")):
            with self.subTest(text=label):
                ws = self.export_lines(["SELECT c", line, "FROM t"])

                self.assert_text(ws["A3"], "SELECT c")
                self.assert_text(ws["A4"], line)
                self.assert_text(ws["A5"], "FROM t")
                self.assertEqual(self.limit_warnings(), [])
                self.assert_counts(ok=1)

    def test_short_sql_is_unchanged(self):
        ws = self.export_lines(["SELECT c", "=1+1", "FROM t"])

        self.assertEqual(ws["A1"].value, "c")
        self.assert_text(ws["A3"], "SELECT c")
        self.assert_text(ws["A4"], "=1+1")  # literal, not a formula
        self.assert_text(ws["A5"], "FROM t")
        self.assertIn("No Data Found", self.output)
        self.assertEqual(self.limit_warnings(), [])
        self.assert_counts(ok=1)


# ----------------------------------------------------- SQL annotation (R7-AC-12)
class SqlAnnotationLimitTests(_ExportCase):
    JOB = "Data job"

    def export_lines(self, lines, values=("v1", "v2")):
        job = {
            "name": self.JOB,
            "query": "\n".join(lines),
            "_export_dataframe": app.pd.DataFrame({"payload": list(values)}),
        }
        return self.run_export([job])[self.JOB]

    def test_oversized_line_is_blank_and_job_is_a_warning(self):
        for label, long_line in (
            ("ascii", "a" * (LIMIT + 1)),
            ("thai", THAI * (LIMIT + 1)),
            ("emoji", EMOJI * 16384),
        ):
            with self.subTest(text=label):
                ws = self.export_lines(["SELECT payload", long_line, "FROM t"])

                # header row 1, data rows 2-3, blank row 4, SQL from row 5
                self.assertEqual(ws["A1"].value, "payload")
                self.assert_text(ws["A2"], "v1")
                self.assert_text(ws["A3"], "v2")
                self.assert_blank(ws["A4"])
                self.assert_text(ws["A5"], "SELECT payload")
                self.assert_blank(ws["A6"])
                self.assert_text(ws["A7"], "FROM t")
                self.assertEqual(ws.max_row, 7)
                self.assertIn(self.sql_warning(self.JOB, 2), self.output)
                self.assertEqual(len(self.limit_warnings()), 1)
                self.assertRegex(self.output, r"Status: \S+ Warning")
                self.assertNotRegex(self.output, r"Status: \S+ Success")
                self.assert_counts(warnings=1)

    def test_oversized_result_cell_and_sql_line_count_one_warning(self):
        ws = self.export_lines(
            ["SELECT payload", "FROM t", "b" * (LIMIT + 1)],
            values=("a" * (LIMIT + 1), "v2"),
        )

        self.assert_blank(ws["A2"])
        self.assert_text(ws["A3"], "v2")
        self.assert_text(ws["A5"], "SELECT payload")
        self.assert_text(ws["A6"], "FROM t")
        self.assert_blank(ws["A7"])
        self.assertIn("column 'payload' contains string values over", self.output)
        self.assertIn(self.sql_warning(self.JOB, 3), self.output)
        self.assertEqual(len(self.limit_warnings()), 2)
        self.assertEqual(len(re.findall(r"Status: \S+ Warning", self.output)), 1)
        self.assert_counts(warnings=1)

    def test_line_exactly_at_limit_is_written_and_job_is_a_success(self):
        for label, line in (("ascii", "a" * LIMIT), ("thai", THAI * LIMIT),
                            ("emoji", EMOJI * 16383 + "a")):
            with self.subTest(text=label):
                ws = self.export_lines(["SELECT payload", line, "FROM t"])

                self.assert_text(ws["A5"], "SELECT payload")
                self.assert_text(ws["A6"], line)
                self.assert_text(ws["A7"], "FROM t")
                self.assertEqual(self.limit_warnings(), [])
                self.assertRegex(self.output, r"Status: \S+ Success")
                self.assert_counts(ok=1)

    def test_short_sql_is_unchanged(self):
        ws = self.export_lines(["SELECT payload", "=1+1", "FROM t"], values=("=2+2", "v2"))

        self.assert_text(ws["A2"], "=2+2")
        self.assert_text(ws["A3"], "v2")
        self.assert_text(ws["A5"], "SELECT payload")
        self.assert_text(ws["A6"], "=1+1")
        self.assert_text(ws["A7"], "FROM t")
        self.assertEqual(self.limit_warnings(), [])
        self.assert_counts(ok=1)


# ----------------------------------------------------------- mixed run (counters)
class MixedExportCounterTests(_ExportCase):
    def test_each_job_is_counted_once_in_its_own_bucket(self):
        long_line = "a" * (LIMIT + 1)
        frame = app.pd.DataFrame({"payload": ["v1"]})
        self.read_sql = mock.Mock(side_effect=RuntimeError("e" * (LIMIT + 1)))
        jobs = [
            {"name": "ok data", "query": "SELECT payload FROM t",
             "_export_dataframe": frame},
            {"name": "ok empty", "query": "SELECT c FROM t",
             "_export_dataframe": app.pd.DataFrame(columns=["c"])},
            {"name": "warn annotation", "query": "SELECT payload\n" + long_line,
             "_export_dataframe": frame},
            {"name": "warn empty", "query": long_line + "\nSELECT c FROM t",
             "_export_dataframe": app.pd.DataFrame(columns=["c"])},
            {"name": "skipped long", "query": _pad("DELETE FROM t -- ", LIMIT + 1)},
            {"name": "skipped short", "query": "DELETE FROM t"},
            {"name": "failed long", "query": "SELECT c FROM t"},
        ]

        workbook = self.run_export(jobs)

        self.assertEqual(workbook.sheetnames, [job["name"] for job in jobs])
        self.assert_counts(ok=2, warnings=2, failed=1, skipped=2)
        self.assertEqual(len(self.limit_warnings()), 4)
        self.assertIn(self.sql_warning("warn annotation", 2), self.output)
        self.assertIn(self.sql_warning("warn empty", 1), self.output)
        self.assertIn(self.column_warning("skipped long", "Query"), self.output)
        self.assertIn(self.column_warning("failed long", "Error"), self.output)
        self.assert_blank(workbook["skipped long"]["C2"])
        self.assert_text(workbook["skipped short"]["C2"], "DELETE FROM t")
        self.assert_blank(workbook["failed long"]["B2"])
        self.assert_text(workbook["failed long"]["C2"], "SELECT c FROM t")


if __name__ == "__main__":
    unittest.main()
