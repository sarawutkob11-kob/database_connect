"""R16-T3 (B1): the ⏹ Stop requested line stays in Execution Logs after a
single Job / SQL Editor / Tables run ends (R16-AC-1..9, R16-Q-2, R16-Q-3).

No Tk window and no real database: DatabaseConnectorGUI.__new__ stubs with a
FakeText that keeps the real text (insert / delete("1.0", END) / get).
threading.Thread is captured so the worker runs when the test says so (Stop is
pressed in between); root.after callbacks are collected and run in order.
The run-log hook is the real _install_run_log_hook with _write_run_log mocked
(records every chunk written to the run log).
"""

from __future__ import annotations

import inspect as pyinspect
import os
import sys
import tempfile
import threading
import tkinter as tk
import unittest
from typing import Any, Callable, List, Optional
from unittest import mock

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import database_connect_gui as app  # noqa: E402

GUI = app.DatabaseConnectorGUI

STOP_CANCELLED = (
    "\n⏹ Stop requested — cancelled 1 running query(ies); remaining jobs are skipped.\n"
)
STOP_NO_CANCEL = (
    "\n⏹ Stop requested — remaining jobs are skipped. "
    "This database driver cannot cancel a running query, so the current one finishes first.\n"
)
SEP57 = "=" * 57
SEP150 = "=" * 150


# ------------------------------------------------------------------ fakes
class FakeText:
    """Execution Logs: keeps the real text."""

    def __init__(self) -> None:
        self.content = ""
        self.insert_calls = 0

    def insert(self, index: Any, chars: Any, *_tags: Any) -> None:
        assert index in (tk.END, "end"), index
        self.insert_calls += 1
        self.content += chars

    def delete(self, start: Any, end: Any = None) -> None:
        assert (start, end) == ("1.0", tk.END), (start, end)
        self.content = ""

    def get(self, start: Any, end: Any) -> str:
        assert (start, end) == ("1.0", tk.END)
        return self.content + "\n"

    def see(self, *_a: Any) -> None:
        pass


class _Btn:
    def __init__(self, text: str = "") -> None:
        self.text = text
        self.state = "normal"

    def cget(self, key: str) -> str:
        return self.text if key == "text" else self.state

    def __getitem__(self, key: str) -> str:
        return self.cget(key)

    def config(self, **kw: Any) -> None:
        self.state = kw.get("state", self.state)
        self.text = kw.get("text", self.text)

    configure = config


class _Var:
    def __init__(self, value: Any = "") -> None:
        self.value = value

    def get(self) -> Any:
        return self.value

    def set(self, value: Any) -> None:
        self.value = value


class _ThreadCapture:
    def __init__(self) -> None:
        self.targets: List[Callable[..., None]] = []
        self.args: List[tuple] = []

    def __call__(self, target=None, args=(), daemon=None, **_kw):
        self.targets.append(target)
        self.args.append(tuple(args))
        return mock.Mock()

    def run(self, i: int = -1) -> None:
        self.targets[i](*self.args[i])


class _CancelConn:
    def __init__(self) -> None:
        self.cancel_calls = 0

    def cancel(self) -> None:
        self.cancel_calls += 1


def make_stub(*, hook: bool = True) -> GUI:
    stub = GUI.__new__(GUI)
    stub._active_db_lock = threading.Lock()
    stub._active_db_connections = {}
    stub._running_job_ids = set()
    stub._batch_running = False
    stub._stop_event = threading.Event()
    stub._stop_buttons = []
    stub._stop_lines = []  # as __init__ sets it
    stub.engine = mock.Mock(name="engine")
    stub.execute_btn = _Btn("▶  Run")
    stub.inspect_btn = _Btn("▦  Tables")
    stub.export_excel_btn = _Btn("⇩  Export")
    stub.save_job_btn = _Btn("Save")
    stub.run_all_btn = _Btn("Run all")
    stub.results_text = FakeText()
    stub.db_type = _Var("PostgreSQL")
    stub.db_name = _Var("db")
    stub.profile_combo = _Var("P1")
    stub.saved_jobs = []
    stub.debug_mode = _Var(False)
    stub.open_result_popups = _Var(False)
    stub.sql_context = mock.Mock(name="sql_context")
    stub.root = mock.Mock(name="root")
    stub.after_calls = []
    stub.root.after.side_effect = lambda _ms, fn: stub.after_calls.append(fn)
    stub._prepare_run_sql = mock.Mock(side_effect=lambda jobs: [j["query"] for j in jobs])
    stub._confirm_data_change = mock.Mock(return_value=True)
    stub._clear_results_grid = mock.Mock(name="_clear_results_grid")
    stub._show_results_grid_sets = mock.Mock(name="_show_results_grid_sets")
    stub._show_results_grid = mock.Mock(name="_show_results_grid")
    stub.show_table_popup = mock.Mock(name="show_table_popup")
    stub._current_profile_jobs = mock.Mock(return_value=[])
    stub.get_jobs_to_run = mock.Mock(return_value=[])
    stub.run_log: List[str] = []
    stub._write_run_log = mock.Mock(side_effect=stub.run_log.append)
    if hook:
        stub._install_run_log_hook()
    return stub


def drain(stub: GUI) -> None:
    while stub.after_calls:
        calls, stub.after_calls = stub.after_calls, []
        for fn in calls:
            fn()


def logs(stub: GUI) -> str:
    return stub.results_text.content


def run_log_stop_count(stub: GUI) -> int:
    return sum(chunk.count("Stop requested") for chunk in stub.run_log)


def job_block(name: str, status: str, *, rows: int = 0, cols: int = 0,
              error: Optional[str] = None, qt: str = "1.25") -> str:
    body = (
        f"Job Name    : {name}\n"
        f"Query Time  : {qt} sec\n"
        f"Rows        : {rows:,}\n"
        f"Columns     : {cols}\n"
        f"Status      : {status}\n"
    )
    if error is not None:
        body += f"Error       : {error}\n"
    return f"{SEP57}\n" + body


def total_block(total: int, ok: int, fail: int) -> str:
    return (
        f"\n{SEP57}\n"
        f"Total   : {total}\nSuccess : {ok}\nFail    : {fail}\n"
        f"{SEP57}\n"
    )


class _Base(unittest.TestCase):
    def setUp(self) -> None:
        patches = [
            mock.patch.object(app, "messagebox"),
            mock.patch("time.sleep"),
        ]
        self.mb = patches[0].start()
        patches[1].start()
        for p in patches:
            self.addCleanup(p.stop)

    # ---------------- single job (run_job)
    def start_job(self, stub: GUI, job: dict) -> _ThreadCapture:
        threads = _ThreadCapture()
        with mock.patch.object(app.threading, "Thread", side_effect=threads):
            stub.run_job(job)
        self.assertEqual(len(threads.targets), 1)
        return threads

    def finish_job(self, stub: GUI, threads: _ThreadCapture) -> None:
        clock = iter([10.0, 11.25])
        with mock.patch("time.perf_counter", side_effect=lambda: next(clock, 11.25)):
            threads.run()
        drain(stub)

    @staticmethod
    def press_stop(stub: GUI, conn: Optional[_CancelConn] = None) -> None:
        if conn is not None:
            stub._active_db_connections = {1: conn}
        stub.stop_running_queries()
        stub._active_db_connections = {}

    def job_error_run(self, stub: GUI, name: str = "J", stops: int = 1,
                      conn_first: bool = True) -> None:
        stub.read_sql_dataframe = mock.Mock(
            side_effect=RuntimeError("ORA-01013: user requested cancel"))
        threads = self.start_job(stub, {"name": name, "query": "SELECT 1", "profile": "P1"})
        for i in range(stops):
            self.press_stop(stub, _CancelConn() if (conn_first and i == 0) else None)
        self.finish_job(stub, threads)

    # ---------------- SQL Editor (execute_query)
    def start_sql(self, stub: GUI, sql: str = "SELECT 1") -> mock.Mock:
        stub.sql_context.get.return_value = sql + "\n"
        dialog = mock.MagicMock(name="loading_dialog")
        stub._create_loading_dialog_with_retry = mock.Mock(return_value=dialog)
        stub._execute_query_background = mock.Mock(name="_execute_query_background")
        stub.execute_query()
        stub._execute_query_background.assert_called_once()
        self.assertEqual(stub.execute_btn.text, "⏳ Loading...")
        return dialog

    # ---------------- Tables (list_tables)
    def start_tables(self, stub: GUI) -> _ThreadCapture:
        stub._create_list_tables_loading_dialog = mock.Mock(
            return_value=mock.MagicMock(name="tables_dialog"))
        threads = _ThreadCapture()
        with mock.patch.object(app.threading, "Thread", side_effect=threads):
            stub.list_tables()
        self.assertEqual(len(threads.targets), 1)
        self.assertEqual(stub.inspect_btn.text, "⏳ Loading...")
        return threads

    def finish_tables(self, stub: GUI, threads: _ThreadCapture, *,
                      tables=("t1",), error: Optional[Exception] = None) -> None:
        inspector = mock.Mock(name="inspector")
        if error is not None:
            inspector.get_schema_names.side_effect = error
        else:
            inspector.get_schema_names.return_value = ["public"] if tables else []
            inspector.get_table_names.return_value = list(tables)
        with mock.patch.object(app, "inspect", return_value=inspector):
            threads.run()
        drain(stub)
        self.assertEqual(stub.inspect_btn.text, "▦  Tables")


TABLES_OK = (
    "✅ Found 1 tables across 1 schemas in 1 database(s)\n\n"
    "Opening results in new window...\n"
    "💡 Tip: Double-click on a table to insert it into SQL Query\n"
)


# =================================================================== AC-1 / AC-8
class SingleJobStopTests(_Base):
    def test_ac1_stop_then_error_order_and_once(self):
        stub = make_stub()
        self.job_error_run(stub)
        expected = (
            STOP_CANCELLED
            + job_block("J", "Fail", error="ORA-01013: user requested cancel")
            + total_block(1, 0, 1)
        )
        self.assertEqual(logs(stub), expected)
        self.assertEqual(logs(stub).count("Stop requested"), 1)
        self.assertEqual(stub.results_text.get("1.0", tk.END), expected + "\n")
        self.assertEqual(stub._running_job_ids, set())

    def test_ac1_logs_before_finish_had_running_line_and_stop(self):
        stub = make_stub()
        stub.read_sql_dataframe = mock.Mock(side_effect=RuntimeError("x"))
        threads = self.start_job(stub, {"name": "J", "query": "SELECT 1", "profile": "P1"})
        self.press_stop(stub, _CancelConn())
        self.assertEqual(logs(stub), "⏳ Running: J ...\n" + STOP_CANCELLED)
        self.assertEqual(stub._stop_lines, [STOP_CANCELLED])
        self.finish_job(stub, threads)
        self.assertNotIn("⏳ Running", logs(stub))  # Logs were still cleared

    def test_ac2_no_cancel_driver_select_success(self):
        stub = make_stub()
        stub.read_sql_dataframe = mock.Mock(return_value=pd.DataFrame({"a": [1, 2]}))
        threads = self.start_job(stub, {"name": "J", "query": "SELECT a FROM t", "profile": "P1"})
        self.press_stop(stub)
        self.finish_job(stub, threads)
        self.assertEqual(
            logs(stub),
            STOP_NO_CANCEL + job_block("J", "Success", rows=2, cols=1) + total_block(1, 1, 0),
        )

    def test_ac2_no_cancel_driver_dml_success(self):
        stub = make_stub()
        stub._execute_modification = mock.Mock(return_value=5)
        threads = self.start_job(
            stub, {"name": "J", "query": "UPDATE t SET a = 1", "profile": "P1"})
        self.press_stop(stub)
        self.finish_job(stub, threads)
        self.assertEqual(
            logs(stub),
            STOP_NO_CANCEL + job_block("J", "Success", rows=5, cols=0) + total_block(1, 1, 0),
        )
        self.assertEqual(logs(stub).count("Stop requested"), 1)

    def test_ac8_two_presses_all_lines_in_order(self):
        stub = make_stub()
        self.job_error_run(stub, stops=2)  # 1st cancels, 2nd: nothing to cancel
        self.assertTrue(logs(stub).startswith(STOP_CANCELLED + STOP_NO_CANCEL + SEP57))
        self.assertEqual(logs(stub).count("Stop requested"), 2)
        self.assertEqual(run_log_stop_count(stub), 2)

    def test_ac8_two_identical_presses_both_kept(self):
        stub = make_stub()
        stub.read_sql_dataframe = mock.Mock(side_effect=RuntimeError("e"))
        threads = self.start_job(stub, {"name": "J", "query": "SELECT 1", "profile": "P1"})
        self.press_stop(stub, _CancelConn())
        self.press_stop(stub, _CancelConn())
        self.press_stop(stub)
        self.finish_job(stub, threads)
        self.assertTrue(logs(stub).startswith(
            STOP_CANCELLED + STOP_CANCELLED + STOP_NO_CANCEL + SEP57 + "\nJob Name"))
        self.assertEqual(logs(stub).count("Stop requested"), 3)

    def test_ac7_run_log_once_per_press(self):
        stub = make_stub()
        self.job_error_run(stub)
        self.assertEqual(run_log_stop_count(stub), 1)
        joined = "".join(stub.run_log)
        self.assertEqual(joined.count(STOP_CANCELLED), 1)
        # the hook still logs everything else of the run
        self.assertIn("Total   : 1\nSuccess : 0\nFail    : 1\n", joined)
        self.assertIn("Error       : ORA-01013: user requested cancel\n", joined)

    def test_finish_calls_report_with_keep_stop_lines(self):
        stub = make_stub()
        stub.read_sql_dataframe = mock.Mock(side_effect=RuntimeError("e"))
        stub._start_job_result_report = mock.Mock(name="_start_job_result_report")
        threads = self.start_job(stub, {"name": "J", "query": "SELECT 1", "profile": "P1"})
        self.assertEqual(stub._start_job_result_report.call_args_list, [mock.call()])
        self.finish_job(stub, threads)
        self.assertEqual(stub._start_job_result_report.call_args_list[-1],
                         mock.call(keep_stop_lines=True))


# =================================================================== AC-3
class SqlEditorStopTests(_Base):
    def _check(self, stub: GUI, body: str) -> None:
        self.assertEqual(logs(stub), STOP_NO_CANCEL + body)
        self.assertEqual(logs(stub).count("Stop requested"), 1)
        self.assertEqual(run_log_stop_count(stub), 1)
        self.assertEqual(stub.execute_btn.text, "▶  Run")

    def test_query_success(self):
        stub = make_stub()
        dialog = self.start_sql(stub)
        self.press_stop(stub)
        stub.on_query_success(pd.DataFrame({"a": [1, 2]}), "SELECT 1", dialog)
        self._check(stub, "✅ Query executed successfully!\n📊 Total Rows: 2\n"
                          "📋 Total Columns: 1\n\nOpening results in new window...\n")

    def test_modification_success(self):
        stub = make_stub()
        sql = "UPDATE t SET a = 1"
        dialog = self.start_sql(stub, sql)
        self.press_stop(stub, _CancelConn())
        stub.on_modification_success(3, sql, dialog)
        body = (f"{SEP150}\n✅ ✏️ UPDATE Statement Executed Successfully!\n{SEP150}\n\n"
                f"📊 Rows Affected: 3\n\nSQL Statement:\n{sql}\n\n{'─' * 150}\n")
        self.assertEqual(logs(stub), STOP_CANCELLED + body)
        self.assertEqual(run_log_stop_count(stub), 1)

    def test_query_error_direct(self):
        stub = make_stub()
        dialog = self.start_sql(stub)
        self.press_stop(stub)
        stub.on_query_error("ORA-01013: user requested cancel", dialog)
        self._check(stub, f"❌ QUERY ERROR\n{SEP150}\n\nError: ORA-01013: user requested cancel\n\n")

    def test_enhanced_dialog_closed_replays_once(self):
        for closed in ("zero", "tclerror"):
            with self.subTest(closed=closed):
                stub = make_stub()
                dialog = self.start_sql(stub)
                if closed == "zero":
                    dialog.winfo_exists.return_value = 0
                else:
                    dialog.winfo_exists.side_effect = tk.TclError("gone")
                self.press_stop(stub)
                details = {"type": "DatabaseError", "message": "ORA-01013: user requested cancel",
                           "traceback": "tb"}
                stub.on_query_error_enhanced(details, dialog)
                self._check(stub, f"❌ QUERY ERROR\n{SEP150}\n\n"
                                  "Error: ORA-01013: user requested cancel\n\n")

    def test_enhanced_dialog_open(self):
        stub = make_stub()
        dialog = self.start_sql(stub)
        dialog.winfo_exists.return_value = 1
        dialog.button_frame.winfo_children.return_value = []
        self.press_stop(stub)
        details = {"type": "DatabaseError", "message": "boom", "traceback": "tb"}
        with mock.patch.object(app.tk, "Button"):
            stub.on_query_error_enhanced(details, dialog)
        self._check(stub, f"❌ QUERY ERROR\n{SEP150}\n\n"
                          "Error Type: DatabaseError\nError Message: boom\n\n")

    def test_enhanced_dialog_open_debug_mode(self):
        stub = make_stub()
        stub.debug_mode = _Var(True)
        dialog = self.start_sql(stub)
        dialog.winfo_exists.return_value = 1
        dialog.button_frame.winfo_children.return_value = []
        self.press_stop(stub)
        with mock.patch.object(app.tk, "Button"):
            stub.on_query_error_enhanced({"type": "T", "message": "M", "traceback": "TB"}, dialog)
        self.assertTrue(logs(stub).startswith(STOP_NO_CANCEL + "❌ QUERY ERROR\n"))
        self.assertTrue(logs(stub).endswith("TB\n" + SEP150 + "\n"))
        self.assertEqual(logs(stub).count("Stop requested"), 1)

    def test_stop_lines_reset_when_sql_starts(self):
        stub = make_stub()
        stub._stop_lines = ["\n⏹ Stop requested — old\n"]
        self.start_sql(stub)
        self.assertEqual(stub._stop_lines, [])
        self.assertNotIn("Stop requested", logs(stub))


# =================================================================== AC-4
class TablesStopTests(_Base):
    def test_success_with_tables(self):
        stub = make_stub()
        threads = self.start_tables(stub)
        self.press_stop(stub, _CancelConn())
        self.finish_tables(stub, threads)
        self.assertEqual(logs(stub), STOP_CANCELLED + TABLES_OK)
        self.assertEqual(run_log_stop_count(stub), 1)
        stub.show_table_popup.assert_called_once()

    def test_error_path_keeps_one_line(self):
        stub = make_stub()
        threads = self.start_tables(stub)
        self.press_stop(stub)
        self.finish_tables(stub, threads, error=RuntimeError("ORA-01013: user requested cancel"))
        self.assertEqual(
            logs(stub),
            "Fetching database schema information...\n\n" + STOP_NO_CANCEL
            + "❌ Error: ORA-01013: user requested cancel\n\n",
        )
        self.assertEqual(logs(stub).count("Stop requested"), 1)
        self.assertEqual(run_log_stop_count(stub), 1)

    def test_empty_list_keeps_one_line(self):
        stub = make_stub()
        threads = self.start_tables(stub)
        self.press_stop(stub)
        self.finish_tables(stub, threads, tables=())
        self.assertEqual(
            logs(stub),
            "Fetching database schema information...\n\n" + STOP_NO_CANCEL
            + "⚠️ No tables found in database\n\n",
        )
        self.assertEqual(run_log_stop_count(stub), 1)

    def test_two_presses_in_order(self):
        stub = make_stub()
        threads = self.start_tables(stub)
        self.press_stop(stub, _CancelConn())
        self.press_stop(stub)
        self.finish_tables(stub, threads)
        self.assertEqual(logs(stub), STOP_CANCELLED + STOP_NO_CANCEL + TABLES_OK)
        self.assertEqual(run_log_stop_count(stub), 2)


# =================================================================== AC-5
class NoStopUnchangedTests(_Base):
    """No Stop: Logs end text = the pre-fix text, character for character."""

    def test_job_error_and_success(self):
        stub = make_stub()
        stub.read_sql_dataframe = mock.Mock(side_effect=RuntimeError("ORA-00942: no table"))
        threads = self.start_job(stub, {"name": "J", "query": "SELECT 1", "profile": "P1"})
        self.finish_job(stub, threads)
        self.assertEqual(logs(stub), job_block("J", "Fail", error="ORA-00942: no table")
                         + total_block(1, 0, 1))
        stub = make_stub()
        stub._execute_modification = mock.Mock(return_value=1234)
        threads = self.start_job(stub, {"name": "J2", "query": "DELETE FROM t", "profile": "P1"})
        self.finish_job(stub, threads)
        self.assertEqual(logs(stub), job_block("J2", "Success", rows=1234) + total_block(1, 1, 0))

    def test_sql_paths(self):
        cases = {
            "select": (lambda s, d: s.on_query_success(pd.DataFrame({"a": [1]}), "SELECT 1", d),
                       "✅ Query executed successfully!\n📊 Total Rows: 1\n📋 Total Columns: 1\n\n"
                       "Opening results in new window...\n"),
            "dml": (lambda s, d: s.on_modification_success(1000, "DELETE FROM t", d),
                    f"{SEP150}\n✅ 🗑️ DELETE Statement Executed Successfully!\n{SEP150}\n\n"
                    f"📊 Rows Affected: 1,000\n\nSQL Statement:\nDELETE FROM t\n\n{'─' * 150}\n"),
            "error": (lambda s, d: s.on_query_error("bad", d),
                      f"❌ QUERY ERROR\n{SEP150}\n\nError: bad\n\n"),
        }
        for name, (finish, expected) in cases.items():
            with self.subTest(path=name):
                stub = make_stub()
                dialog = self.start_sql(stub)
                finish(stub, dialog)
                self.assertEqual(logs(stub), expected)

    def test_enhanced_open_and_closed(self):
        for is_open in (True, False):
            with self.subTest(dialog_open=is_open):
                stub = make_stub()
                dialog = self.start_sql(stub)
                dialog.winfo_exists.return_value = 1 if is_open else 0
                dialog.button_frame.winfo_children.return_value = []
                with mock.patch.object(app.tk, "Button"):
                    stub.on_query_error_enhanced({"type": "T", "message": "M", "traceback": ""},
                                                 dialog)
                expected = (f"❌ QUERY ERROR\n{SEP150}\n\nError Type: T\nError Message: M\n\n"
                            if is_open else f"❌ QUERY ERROR\n{SEP150}\n\nError: M\n\n")
                self.assertEqual(logs(stub), expected)

    def test_tables_paths(self):
        stub = make_stub()
        self.finish_tables(stub, self.start_tables(stub))
        self.assertEqual(logs(stub), TABLES_OK)
        stub = make_stub()
        self.finish_tables(stub, self.start_tables(stub), error=RuntimeError("boom"))
        self.assertEqual(logs(stub),
                         "Fetching database schema information...\n\n❌ Error: boom\n\n")

    def test_no_stop_no_extra_insert_calls(self):
        """Replay writes nothing when there was no Stop (only the delete)."""
        stub = make_stub(hook=False)
        stub.results_text.content = "old text"
        before = stub.results_text.insert_calls
        stub._clear_results_keep_stop_lines()
        self.assertEqual(logs(stub), "")
        self.assertEqual(stub.results_text.insert_calls, before)


# =================================================================== AC-6
class PreviousRunStopNotCarriedTests(_Base):
    def _job_a_stopped(self) -> GUI:
        stub = make_stub()
        self.job_error_run(stub, name="A")
        self.assertIn("Stop requested", logs(stub))
        self.assertTrue(stub._stop_event.is_set())  # still set after the run ended
        self.assertFalse(stub._is_busy())
        return stub

    def test_a_next_job(self):
        stub = self._job_a_stopped()
        stub.read_sql_dataframe = mock.Mock(return_value=pd.DataFrame({"a": [1]}))
        threads = self.start_job(stub, {"name": "B", "query": "SELECT 1", "profile": "P1"})
        self.assertEqual(logs(stub), "⏳ Running: B ...\n")  # start does not replay
        self.assertEqual(stub._stop_lines, [])
        self.finish_job(stub, threads)
        self.assertEqual(logs(stub), job_block("B", "Success", rows=1, cols=1)
                         + total_block(1, 1, 0))

    def test_b_execute_query(self):
        stub = self._job_a_stopped()
        dialog = self.start_sql(stub)
        stub.on_query_error("bad", dialog)
        self.assertEqual(logs(stub), f"❌ QUERY ERROR\n{SEP150}\n\nError: bad\n\n")

    def test_c_list_tables_event_still_set(self):
        stub = self._job_a_stopped()
        threads = self.start_tables(stub)
        self.assertTrue(stub._stop_event.is_set())  # Tables does not clear the event
        self.assertEqual(stub._stop_lines, [])
        self.finish_tables(stub, threads)
        self.assertEqual(logs(stub), TABLES_OK)

    def test_run_all_start_does_not_replay(self):
        stub = self._job_a_stopped()
        stub.read_sql_dataframe = mock.Mock(return_value=pd.DataFrame({"a": [1]}))
        threads = _ThreadCapture()
        with mock.patch.object(app.threading, "Thread", side_effect=threads):
            stub.run_selected_job(jobs_override=[{"name": "R1", "query": "SELECT 1"}])
        self.assertEqual(logs(stub), "")
        threads.run()
        drain(stub)
        self.assertNotIn("Stop requested", logs(stub))

    def test_stop_while_idle_then_new_job(self):
        stub = make_stub()
        stub.stop_running_queries()  # not busy: returns at once
        self.assertEqual(stub._stop_lines, [])
        self.assertEqual(logs(stub), "")
        self.assertFalse(stub._stop_event.is_set())
        stub.read_sql_dataframe = mock.Mock(side_effect=RuntimeError("e"))
        threads = self.start_job(stub, {"name": "B", "query": "SELECT 1", "profile": "P1"})
        self.finish_job(stub, threads)
        self.assertNotIn("Stop requested", logs(stub))

    def test_stop_while_idle_after_stopped_job_adds_nothing(self):
        stub = self._job_a_stopped()
        lines_before = list(stub._stop_lines)
        text_before = logs(stub)
        stub.stop_running_queries()
        self.assertEqual(stub._stop_lines, lines_before)
        self.assertEqual(logs(stub), text_before)
        # and the next run of each kind starts clean
        threads = self.start_tables(stub)
        self.finish_tables(stub, threads, tables=())
        self.assertNotIn("Stop requested", logs(stub).split("Fetching")[-1])

    def test_tables_blocked_before_start_keeps_nothing_new(self):
        """Tables refused (not connected) does not reset nor replay."""
        stub = make_stub()
        stub.engine = None
        stub._stop_lines = [STOP_CANCELLED]
        stub.list_tables()
        self.assertEqual(logs(stub), "")
        self.mb.showerror.assert_called_once()


# =================================================================== AC-9
class BatchUnchangedTests(_Base):
    JOBS = [{"name": f"J{i}", "query": f"SELECT {i} AS a"} for i in range(1, 5)]

    def _run_all(self, *, override: bool) -> GUI:
        stub = make_stub()
        jobs = [dict(j) for j in self.JOBS]
        if not override:
            stub.get_jobs_to_run.return_value = jobs
            stub._current_profile_jobs.return_value = jobs
        first = {"done": False}

        def read(sql, engine=None):
            if not first["done"]:
                first["done"] = True
                stub.stop_running_queries()  # Stop before job 2
            return pd.DataFrame({"a": [1]})

        stub.read_sql_dataframe = mock.Mock(side_effect=read)
        threads = _ThreadCapture()
        with mock.patch.object(app.threading, "Thread", side_effect=threads):
            if override:
                stub.run_selected_job(jobs_override=jobs)  # Run Group
            else:
                stub.run_selected_job()
        threads.run()
        drain(stub)
        return stub

    def test_run_all_and_run_group(self):
        for override in (False, True):
            with self.subTest(run_group=override):
                stub = self._run_all(override=override)
                text = logs(stub)
                self.assertEqual(text.count(STOP_NO_CANCEL), 1)
                self.assertEqual(text.count("Stop requested"), 1)
                self.assertEqual(text.count("⏹ Stopped — 3 job(s) not run\n"), 1)
                self.assertEqual(text.count("Total   :"), 1)
                self.assertIn(total_block(1, 1, 0), text)
                self.assertTrue(text.startswith(STOP_NO_CANCEL))
                self.assertLess(text.index("Stop requested"), text.index("Job Name    : J1"))
                self.assertLess(text.index("Job Name    : J1"), text.index("⏹ Stopped"))
                self.assertLess(text.index("⏹ Stopped"), text.index("Total   :"))
                self.assertEqual(run_log_stop_count(stub), 1)
                self.assertFalse(stub._batch_running)

    def test_export_stop_before_second_job(self):
        stub = make_stub()
        jobs = [dict(j) for j in self.JOBS]
        first = {"done": False}

        def read(sql, engine=None):
            if not first["done"]:
                first["done"] = True
                stub.stop_running_queries()
            return pd.DataFrame({"a": [1]})

        stub.read_sql_dataframe = mock.Mock(side_effect=read)
        stub._reuse_last_run_results = mock.Mock(side_effect=lambda js: list(js))
        with tempfile.TemporaryDirectory() as folder:
            out = os.path.join(folder, "out.xlsx")
            threads = _ThreadCapture()
            with mock.patch.object(app.threading, "Thread", side_effect=threads), \
                    mock.patch.object(app, "filedialog") as fd:
                fd.asksaveasfilename.return_value = out
                stub.export_jobs_to_excel(jobs_override=jobs)
            threads.run()
            drain(stub)
        text = logs(stub)
        self.assertEqual(text.count(STOP_NO_CANCEL), 1)
        self.assertEqual(text.count("Stop requested"), 1)
        self.assertEqual(text.count("⏹ Stopped — 3 job(s) not exported\n"), 1)
        self.assertIn("🏁 Export Excel Completed", text)
        self.assertTrue(text.startswith(SEP150 + "\n📤 Export Excel Started\n"))
        self.assertEqual(run_log_stop_count(stub), 1)
        self.assertEqual(stub.export_excel_btn.text, "⇩  Export")


# =================================================================== R16-D2 details
class HelperAndStubSafetyTests(_Base):
    def test_init_wires_state_and_hook(self):
        src = pyinspect.getsource(GUI.__init__)
        self.assertIn("self._stop_lines", src)
        self.assertIn("self._install_run_log_hook()", src)
        self.assertNotIn("_insert_and_log", src)  # wrapper moved to the method
        self.assertLess(src.index("self._init_run_log()"),
                        src.index("self._install_run_log_hook()"))

    def test_hook_keeps_raw_insert_and_logs_strings_only(self):
        stub = make_stub()
        self.assertIsNotNone(stub._results_text_raw_insert)
        stub.results_text.insert(tk.END, "abc\n")
        stub.results_text.insert(tk.END, "tagged\n", "tag1")
        self.assertEqual(stub.run_log, ["abc\n", "tagged\n"])
        stub._results_text_raw_insert(tk.END, "raw\n")
        self.assertEqual(stub.run_log, ["abc\n", "tagged\n"])
        self.assertEqual(logs(stub), "abc\ntagged\nraw\n")

    def test_replay_uses_raw_insert(self):
        stub = make_stub()
        stub._stop_lines = [STOP_CANCELLED, STOP_NO_CANCEL]
        stub.results_text.insert(tk.END, "x\n")
        stub.run_log.clear()
        stub._clear_results_keep_stop_lines()
        self.assertEqual(logs(stub), STOP_CANCELLED + STOP_NO_CANCEL)
        self.assertEqual(stub.run_log, [])
        self.assertEqual(stub._stop_lines, [STOP_CANCELLED, STOP_NO_CANCEL])  # not consumed

    def test_start_job_result_report_default_only_clears(self):
        stub = make_stub()
        stub._stop_lines = [STOP_CANCELLED]
        stub.results_text.insert(tk.END, "x\n")
        stub._start_job_result_report()
        self.assertEqual(logs(stub), "")
        stub._start_job_result_report(keep_stop_lines=True)
        self.assertEqual(logs(stub), STOP_CANCELLED)

    def test_bare_stub_without_new_attributes(self):
        stub = GUI.__new__(GUI)
        stub.results_text = FakeText()
        stub.results_text.content = "old"
        self.assertFalse(hasattr(stub, "_stop_lines"))
        self.assertFalse(hasattr(stub, "_results_text_raw_insert"))
        stub._replay_stop_lines()
        stub._clear_results_keep_stop_lines()
        stub._start_job_result_report(keep_stop_lines=True)
        stub._start_job_result_report()
        self.assertEqual(logs(stub), "")
        # Stop on a bare stub creates the list; replay falls back to insert
        stub._active_db_lock = threading.Lock()
        stub._active_db_connections = {}
        stub._stop_event = threading.Event()
        stub._running_job_ids = {1}
        stub.execute_btn = _Btn("▶  Run")
        stub.export_excel_btn = _Btn("⇩  Export")
        stub.inspect_btn = _Btn("▦  Tables")
        stub.stop_running_queries()
        self.assertEqual(stub._stop_lines, [STOP_NO_CANCEL])
        stub._clear_results_keep_stop_lines()
        self.assertEqual(logs(stub), STOP_NO_CANCEL)

    def test_bare_stub_on_query_error(self):
        stub = GUI.__new__(GUI)
        stub.results_text = FakeText()
        stub.engine = None
        stub.execute_btn = _Btn("⏳ Loading...")
        stub.on_query_error("bad", mock.Mock())
        self.assertEqual(logs(stub), f"❌ QUERY ERROR\n{SEP150}\n\nError: bad\n\n")

    def test_stop_message_text_unchanged(self):
        stub = make_stub()
        stub._running_job_ids = {1}
        self.press_stop(stub, _CancelConn())
        self.assertEqual(logs(stub), STOP_CANCELLED)
        self.assertEqual(stub._stop_lines, [STOP_CANCELLED])
        self.assertEqual(stub.run_log, [STOP_CANCELLED])


if __name__ == "__main__":
    unittest.main()
