"""R14-T3: Export Excel errors (P10 job failed, P11 fatal) never show the password.

R14-AC-10 .. R14-AC-12, R14-AC-13 / R14-AC-14 (Export), R14-AC-16 (P10, P11).
Stub GUI (DatabaseConnectorGUI.__new__), the worker is kept until the test
runs it (so a reconnect can happen in between), root.after runs at once,
filedialog / messagebox / print are patched, read_sql_dataframe is a fake.
The workbook is written only inside a TemporaryDirectory and read back with
openpyxl.
"""

import os
import sys
import tempfile
import threading
import unittest
from unittest import mock

from openpyxl import load_workbook

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import database_connect_gui as app  # noqa: E402
import test_run_engine as tre  # noqa: E402
from test_r14_run_redaction import (  # noqa: E402
    E,
    E2,
    ERR3,
    FIELD_PW,
    PATTERN_ERRORS,
    PLAIN_ERRORS,
    PW,
    SECRET_ERRORS,
    R14Case,
    _CountingEntry,
    identity_redact,
    normalize,
    reconnect,
)

GUI = app.DatabaseConnectorGUI
OK_SQL = "SELECT id FROM data_table"
BAD_SQL = "SELECT *\nFROM broken_table\nWHERE password = 'x'"  # user SQL kept as is
LIMIT_WARNING = "column 'Error' is over Excel's 32,767-character limit"


def make_export_stub(password=PW, owner=None):
    stub = GUI.__new__(GUI)
    stub._block_if_busy = mock.Mock(return_value=False)
    stub._reuse_last_run_results = mock.Mock(
        side_effect=lambda items: [dict(item) for item in items]
    )
    stub._start_stoppable_run = mock.Mock()
    stub._stop_event = threading.Event()
    stub.engine = E
    stub._connected_password = None if password is None else (owner or E, password)
    stub.db_password = _CountingEntry(FIELD_PW)
    stub.results_text = tre._Text()
    stub.export_excel_btn = tre._Btn("Export")
    stub.root = mock.Mock(name="root")
    stub.root.after.side_effect = lambda _delay, callback: callback()
    return stub


def run_export(path, err, *, jobs=None, password=PW, owner=None, swap=False,
               fatal=False):
    """Export jobs A (passes) and B (raises RuntimeError(err)) to `path`."""
    stub = make_export_stub(password=password, owner=owner)

    def read(query, engine=None):
        if "broken_table" in query:
            raise RuntimeError(err)
        return app.pd.DataFrame({"id": [1, 2]})

    stub.read_sql_dataframe = read
    if jobs is None:
        jobs = [{"name": "A", "query": OK_SQL}, {"name": "B", "query": BAD_SQL}]
    threads = tre._ThreadCapture()
    patches = [
        mock.patch.object(app.filedialog, "asksaveasfilename", return_value=path),
        mock.patch.object(app.threading, "Thread", side_effect=threads),
        mock.patch.object(app, "messagebox"),
    ]
    if fatal:
        patches.append(mock.patch.object(app, "_ensure_export_target_writable",
                                         side_effect=RuntimeError(err)))
    started = []
    try:
        for patcher in patches:
            started.append(patcher.start())
        stub.export_jobs_to_excel(jobs_override=jobs)
        self_gets = stub.db_password.get_calls
        if swap:
            reconnect(stub)
        threads.run_all()
    finally:
        for patcher in reversed(patches[: len(started)]):
            patcher.stop()
    mb = started[2]
    return stub, {
        "output": "".join(stub.results_text.inserted),
        "showerror": [list(c.args) for c in mb.showerror.call_args_list],
        "showinfo": [list(c.args) for c in mb.showinfo.call_args_list],
        "gets": stub.db_password.get_calls,
        "gets_after_start": stub.db_password.get_calls - self_gets,
    }


def read_sheets(path):
    """{sheet: [[cell values row by row]]}."""
    workbook = load_workbook(path)
    try:
        return {ws.title: [[c.value for c in row] for row in ws.iter_rows()]
                for ws in workbook.worksheets}
    finally:
        workbook.close()


def failed_row(sheets, name="B"):
    rows = sheets[name]
    return dict(zip(rows[0], rows[1]))


class _ExportCase(R14Case):
    def setUp(self):
        super().setUp()
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.folder = tmp.name
        self.path = os.path.join(tmp.name, "export.xlsx")

    def fresh_path(self):
        if os.path.exists(self.path):
            os.remove(self.path)
        return self.path

    def all_cells(self, sheets):
        return [str(v) for rows in sheets.values() for row in rows for v in row
                if v is not None]


# ---------------------------------------------------------------- AC-10
class ExportJobFailedTests(_ExportCase):
    def test_ac10_failed_sheet_and_logs_masked(self):
        for label, err, keep in SECRET_ERRORS:
            with self.subTest(error=label):
                _stub, out = run_export(self.fresh_path(), err)
                sheets = read_sheets(self.path)
                self.assertEqual(list(sheets), ["A", "B"])
                row = failed_row(sheets)
                self.assertEqual(row["Status"], "Failed")
                self.assert_no_leak("cell Error", [row["Error"]])
                self.assert_kept("cell Error", row["Error"], keep)
                self.assertEqual(row["Query"], BAD_SQL)
                self.assert_no_leak("workbook", self.all_cells(sheets))
                output = out["output"]
                self.assert_no_leak("Execution Logs", [output])
                self.assertIn("Error : ", output)
                self.assertIn("Traceback (most recent call last)", output)
                self.assertIn("Error Type : RuntimeError\n", output)
                self.assertIn("✅ Success: 1\n", output)
                self.assertIn("❌ Failed: 1\n", output)
                self.assertIn("⚠️ Warning: 0\n", output)
                self.assertEqual(out["showerror"], [])
                self.assert_no_leak("showinfo", out["showinfo"])
                self.assertEqual(out["gets"], 0)
                self.assert_no_leak("print", self.prints)


# ---------------------------------------------------------------- AC-11
class ExportCellLimitAfterRedactTests(_ExportCase):
    def test_ac11a_long_raw_short_after_redact_is_written(self):
        count = 2600
        raw = "x " + " ".join([PW] * count) + " end"
        masked = "x " + " ".join(["***"] * count) + " end"
        self.assertGreater(len(raw), app.EXCEL_MAX_CELL_CHARS)
        self.assertLessEqual(len(masked), app.EXCEL_MAX_CELL_CHARS)
        _stub, out = run_export(self.fresh_path(), raw)
        row = failed_row(read_sheets(self.path))
        self.assert_same("cell Error", row["Error"], masked)
        self.assertNotIn(LIMIT_WARNING, out["output"])
        self.assert_no_leak("Execution Logs", [out["output"]])
        self.assertIn("❌ Failed: 1\n", out["output"])

    def test_ac11b_short_raw_long_after_redact_is_blanked(self):
        raw = "PWD=;" * 6000
        self.assertLessEqual(len(raw), app.EXCEL_MAX_CELL_CHARS)
        self.assertGreater(len(app.redact_secrets(raw, PW)), app.EXCEL_MAX_CELL_CHARS)
        _stub, out = run_export(self.fresh_path(), raw)
        row = failed_row(read_sheets(self.path))
        self.assertIn(row["Error"], (None, ""))
        self.assertEqual(row["Status"], "Failed")
        self.assertEqual(row["Query"], BAD_SQL)
        self.assertEqual(out["output"].count(f"Job 'B', {LIMIT_WARNING}"), 1)


# ---------------------------------------------------------------- AC-12
class ExportFatalTests(_ExportCase):
    def test_ac12_fatal_error_masked(self):
        for label, err, keep in SECRET_ERRORS:
            with self.subTest(error=label):
                _stub, out = run_export(self.fresh_path(), err, fatal=True)
                self.assertFalse(os.path.exists(self.path))
                self.assert_no_leak("Execution Logs", [out["output"]])
                lines = [ln for ln in out["output"].split("\n") if ln.startswith("Error: ")]
                self.assertEqual(len(lines), 1)
                self.assertTrue(lines[0].startswith("Error: RuntimeError: "))
                self.assertEqual(len(out["showerror"]), 1)
                title, message = out["showerror"][0][:2]
                self.assertEqual(title, "Export Error")
                self.assert_no_leak("showerror", [message])
                self.assertTrue(message.startswith("Export Excel ไม่สำเร็จ:\n\nRuntimeError: "))
                self.assert_kept("showerror", message, keep)


# ---------------------------------------------------------------- AC-13 / AC-14
class ExportPasswordSourceTests(_ExportCase):
    def test_ac13_reconnect_while_exporting_uses_start_password(self):
        for fatal in (False, True):
            with self.subTest(fatal=fatal):
                stub, out = run_export(self.fresh_path(), ERR3, swap=True, fatal=fatal)
                self.assertIs(stub.engine, E2)
                texts = [out["output"], *[a for c in out["showerror"] for a in c], *self.prints]
                if not fatal:
                    sheets = read_sheets(self.path)
                    texts += self.all_cells(sheets)
                    self.assert_kept("cell Error", failed_row(sheets)["Error"],
                                     ("bad password", "for u"))
                self.assert_no_leak("all destinations", texts)
                self.assertEqual(out["gets"], 0, "Password field read")
                self.assertEqual(out["gets_after_start"], 0)

    def test_ac14_no_stored_password_pattern_only(self):
        for owner_case in ("none", "other_engine"):
            for label, err, keep in SECRET_ERRORS:
                with self.subTest(stored=owner_case, error=label):
                    kw = {"password": None} if owner_case == "none" else {"owner": E2}
                    _stub, out = run_export(self.fresh_path(), err, **kw)
                    row = failed_row(read_sheets(self.path))
                    if err is ERR3:  # known limit (R14-Q-3)
                        self.assert_same("cell Error", row["Error"], err)
                    else:
                        self.assert_no_leak("cell Error", [row["Error"]])
                        self.assert_no_leak("Execution Logs", [out["output"]])
                        self.assert_kept("cell Error", row["Error"], keep)
                    self.assertEqual(out["gets"], 0)
        self.assertEqual(len(PATTERN_ERRORS), 2)


# ---------------------------------------------------------------- AC-16 (P10, P11)
class ExportPlainErrorUnchangedTests(_ExportCase):
    def _collect(self, err, fatal):
        _stub, out = run_export(self.fresh_path(), err, fatal=fatal)
        out = {k: out[k] for k in ("output", "showerror", "showinfo")}
        out["sheets"] = None if fatal else read_sheets(self.path)
        return normalize(out)

    def test_ac16_export_equal_oracle(self):
        for fatal in (False, True):
            for label, err in PLAIN_ERRORS:
                with self.subTest(error=label, fatal=fatal):
                    actual = self._collect(err, fatal)
                    with mock.patch.object(app, "redact_secrets", identity_redact):
                        expected = self._collect(err, fatal)
                    self.assertEqual(actual, expected)
                    output = actual["output"]
                    if fatal:
                        self.assertIn(f"Error: RuntimeError: {normalize(err)}\n\n", output)
                        self.assertEqual(actual["showerror"], [[
                            "Export Error",
                            f"Export Excel ไม่สำเร็จ:\n\nRuntimeError: {normalize(err)}",
                        ]])
                    else:
                        row = failed_row(actual["sheets"])
                        self.assertEqual(row, {"Status": "Failed", "Error": normalize(err),
                                               "Query": BAD_SQL})
                        self.assertIn(f"Error : {normalize(err)}\n", output)
                        self.assertIn("✅ Success: 1\n", output)
                        self.assertIn("⚠️ Warning: 0\n", output)
                        self.assertIn("❌ Failed: 1\n", output)


if __name__ == "__main__":
    unittest.main()
