"""R15-T10: BH-7 (Run all stops after a failed DML job: say how many were not run)
and BH-13 (self-rescheduling polls stay on the main root while self.root is a
dialog). R15-AC-19, R15-AC-20, R15-AC-36, R15-AC-37.

No real database: read_sql_dataframe / _execute_modification are stubs.
threading.Thread is captured and run in the test thread; root.after callbacks
are collected and run in order, like the Tk main loop would.
"""

from __future__ import annotations

import ast
import inspect as pyinspect
import os
import sys
import textwrap
import threading
import time
import tkinter as tk
import unittest
from typing import Any, Callable, List, Optional
from unittest import mock

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import database_connect_gui as app  # noqa: E402

GUI = app.DatabaseConnectorGUI

DML_STOP_TEXT = "⛔ Stopped — a data-modification job failed — {n} job(s) not run\n"
USER_STOP_TEXT = "⏹ Stopped — {n} job(s) not run\n"


# ------------------------------------------------------------------ helpers
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


class _Text:
    def __init__(self) -> None:
        self.inserted: List[str] = []

    def insert(self, _index: Any, value: str) -> None:
        self.inserted.append(value)

    def see(self, *_a: Any) -> None:
        pass

    def delete(self, *_a: Any) -> None:
        pass


class _Entry:
    def __init__(self, value: str = "") -> None:
        self.value = value

    def get(self) -> str:
        return self.value


class _ThreadCapture:
    def __init__(self) -> None:
        self.targets: List[Callable[[], None]] = []

    def __call__(self, target=None, daemon=None, **_kw):
        self.targets.append(target)
        return mock.Mock()


def make_run_stub() -> GUI:
    stub = GUI.__new__(GUI)
    stub._active_db_lock = threading.Lock()
    stub._active_db_connections = {}
    stub._running_job_ids = set()
    stub._batch_running = False
    stub._stop_event = threading.Event()
    stub.engine = mock.Mock(name="engine")
    for name in ("execute_btn", "inspect_btn", "save_job_btn", "run_all_btn"):
        setattr(stub, name, _Btn(name))
    stub.export_excel_btn = _Btn("⇩  Export")
    stub.results_text = _Text()
    stub.db_type = _Entry("SQLite")
    stub.db_name = _Entry("")
    stub.profile_combo = _Entry("P1")
    stub.root = mock.Mock(name="root")
    stub.after_calls = []
    stub.root.after.side_effect = lambda _ms, fn: stub.after_calls.append(fn)
    stub._prepare_run_sql = mock.Mock(side_effect=lambda jobs: [j["query"] for j in jobs])
    stub._confirm_data_change = mock.Mock(return_value=True)
    stub._start_stoppable_run = mock.Mock()
    stub._start_job_result_report = mock.Mock()
    stub._clear_results_grid = mock.Mock()
    stub.update_job_status = mock.Mock()
    # The real show_batch_summary writes the Total block first (via
    # _finish_job_result_report); keep that so line order can be checked.
    stub.show_batch_summary = mock.Mock(
        side_effect=lambda s, e, _jr, _t: GUI._finish_job_result_report(stub, s + e, s, e)
    )
    stub.show_batch_error = mock.Mock()
    stub._current_profile_jobs = mock.Mock(return_value=[])
    stub.get_jobs_to_run = mock.Mock(return_value=[])
    return stub


class RunAllNotRunLineTests(unittest.TestCase):
    """R15-AC-19 / R15-AC-20 (BH-7)."""

    def setUp(self) -> None:
        sleep = mock.patch("time.sleep")
        sleep.start()
        self.addCleanup(sleep.stop)

    def _run(self, jobs, *, fail=(), stop_after: Optional[int] = None):
        """Run `jobs` through run_selected_job.

        fail: job names whose SQL raises. stop_after: Stop is pressed while the
        job with this 1-based index runs (it still finishes)."""
        stub = make_run_stub()
        executed: List[str] = []
        by_query = {j["query"]: j for j in jobs}

        def run(sql, engine=None):
            executed.append(by_query[sql]["name"])
            if stop_after is not None and len(executed) == stop_after:
                stub._stop_event.set()
            if by_query[sql]["name"] in fail:
                raise RuntimeError(f"boom {by_query[sql]['name']}")
            if stub.is_select_query(sql):
                return pd.DataFrame({"a": [1]})
            return 1

        stub.read_sql_dataframe = mock.Mock(side_effect=run)
        stub._execute_modification = mock.Mock(side_effect=run)
        threads = _ThreadCapture()
        with mock.patch.object(app.threading, "Thread", side_effect=threads), \
                mock.patch.object(app, "messagebox") as mb:
            stub.run_selected_job(jobs_override=jobs)
            self.assertEqual(len(threads.targets), 1)
            threads.targets[0]()
            # the worker must not write to the widget itself (only via root.after)
            self.assertFalse(any("not run" in t for t in stub.results_text.inserted))
            calls, stub.after_calls = stub.after_calls, []
            for fn in calls:
                fn()
        mb.showerror.assert_not_called()
        stub.show_batch_error.assert_not_called()
        stub.show_batch_summary.assert_called_once()
        return stub, executed

    @staticmethod
    def _jobs(*specs):
        return [{"name": name, "query": sql} for name, sql in specs]

    def _counts(self, stub):
        success, errors, job_results, total = stub.show_batch_summary.call_args.args
        return success + errors, success, errors, [r["Name"] for r in job_results], total

    def _not_run_lines(self, stub):
        return [t for t in stub.results_text.inserted if "not run" in t]

    def _total_index(self, stub):
        idx = [i for i, t in enumerate(stub.results_text.inserted) if "Total   :" in t]
        self.assertEqual(len(idx), 1, stub.results_text.inserted)
        return idx[0]

    # ---- R15-AC-19
    def test_ac19_delete_fails_second_of_four(self):
        jobs = self._jobs(("J1", "SELECT 1 AS a"), ("J2", "DELETE FROM t"),
                          ("J3", "SELECT 3 AS a"), ("J4", "SELECT 4 AS a"))
        stub, executed = self._run(jobs, fail={"J2"})
        lines = self._not_run_lines(stub)
        self.assertEqual(lines, [DML_STOP_TEXT.format(n=2)])
        self.assertTrue(lines[0].endswith("2 job(s) not run\n"))
        line_idx = stub.results_text.inserted.index(lines[0])
        self.assertLess(line_idx, self._total_index(stub))
        total, success, errors, names, total_jobs = self._counts(stub)
        self.assertEqual((total, success, errors), (2, 1, 1))
        self.assertEqual(names, ["J1", "J2"])
        self.assertEqual(total_jobs, 4)
        self.assertEqual(executed, ["J1", "J2"])  # J3, J4 never run
        text = "".join(stub.results_text.inserted)
        self.assertIn("Total   : 2\nSuccess : 1\nFail    : 1\n", text)
        self.assertNotIn("⏹", text)

    def test_ac19_line_is_after_error_status_and_before_summary(self):
        jobs = self._jobs(("J1", "SELECT 1 AS a"), ("J2", "UPDATE t SET a = 1"),
                          ("J3", "SELECT 3 AS a"), ("J4", "SELECT 4 AS a"))
        order: List[str] = []
        stub2 = make_run_stub()
        stub2.update_job_status = mock.Mock(
            side_effect=lambda i, j, status, *a, **k: order.append(f"{status}:{j['name']}")
        )
        stub2.show_batch_summary = mock.Mock(side_effect=lambda *a: order.append("summary"))
        stub2.results_text.insert = lambda _i, v: order.append(f"text:{v}")

        def run(sql, engine=None):
            if sql.startswith("UPDATE"):
                raise RuntimeError("boom")
            return pd.DataFrame({"a": [1]})

        stub2.read_sql_dataframe = mock.Mock(side_effect=run)
        stub2._execute_modification = mock.Mock(side_effect=run)
        threads = _ThreadCapture()
        with mock.patch.object(app.threading, "Thread", side_effect=threads), \
                mock.patch.object(app, "messagebox"):
            stub2.run_selected_job(jobs_override=jobs)
            threads.targets[0]()
            for fn in stub2.after_calls:
                fn()
        line = f"text:{DML_STOP_TEXT.format(n=2)}"
        self.assertIn(line, order)
        self.assertLess(order.index("error:J2"), order.index(line))
        self.assertLess(order.index(line), order.index("summary"))
        self.assertEqual(order.count(line), 1)

    def test_one_job_not_run_when_dml_fails_third_of_four(self):
        jobs = self._jobs(("J1", "SELECT 1 AS a"), ("J2", "SELECT 2 AS a"),
                          ("J3", "INSERT INTO t VALUES (1)"), ("J4", "SELECT 4 AS a"))
        stub, executed = self._run(jobs, fail={"J3"})
        self.assertEqual(self._not_run_lines(stub), [DML_STOP_TEXT.format(n=1)])
        self.assertEqual(executed, ["J1", "J2", "J3"])
        self.assertEqual(self._counts(stub)[:3], (3, 2, 1))

    def test_dml_fails_first_of_three(self):
        jobs = self._jobs(("J1", "DELETE FROM t"), ("J2", "SELECT 2 AS a"),
                          ("J3", "SELECT 3 AS a"))
        stub, executed = self._run(jobs, fail={"J1"})
        self.assertEqual(self._not_run_lines(stub), [DML_STOP_TEXT.format(n=2)])
        self.assertEqual(executed, ["J1"])
        self.assertEqual(self._counts(stub)[:3], (1, 0, 1))

    # ---- R15-AC-20
    def test_ac20a_dml_fails_as_last_job_no_not_run(self):
        jobs = self._jobs(("J1", "SELECT 1 AS a"), ("J2", "SELECT 2 AS a"),
                          ("J3", "DELETE FROM t"))
        stub, executed = self._run(jobs, fail={"J3"})
        self.assertEqual(self._not_run_lines(stub), [])
        self.assertNotIn("not run", "".join(stub.results_text.inserted))
        self.assertNotIn("⛔", "".join(stub.results_text.inserted))
        self.assertEqual(executed, ["J1", "J2", "J3"])
        self.assertEqual(self._counts(stub)[:3], (3, 2, 1))

    def test_ac20a_single_dml_job_fails_no_not_run(self):
        stub, executed = self._run(self._jobs(("J1", "DELETE FROM t")), fail={"J1"})
        self.assertNotIn("not run", "".join(stub.results_text.inserted))
        self.assertEqual(self._counts(stub)[:3], (1, 0, 1))

    def test_ac20b_all_jobs_pass_no_not_run(self):
        jobs = self._jobs(("J1", "SELECT 1 AS a"), ("J2", "DELETE FROM t"),
                          ("J3", "SELECT 3 AS a"), ("J4", "SELECT 4 AS a"))
        stub, executed = self._run(jobs)
        self.assertNotIn("not run", "".join(stub.results_text.inserted))
        self.assertEqual(executed, ["J1", "J2", "J3", "J4"])
        self.assertEqual(self._counts(stub)[:3], (4, 4, 0))

    def test_ac20c_select_fails_and_run_continues_no_not_run(self):
        jobs = self._jobs(("J1", "SELECT 1 AS a"), ("J2", "SELECT 2 AS a"),
                          ("J3", "SELECT 3 AS a"), ("J4", "SELECT 4 AS a"))
        stub, executed = self._run(jobs, fail={"J2"})
        self.assertNotIn("not run", "".join(stub.results_text.inserted))
        self.assertEqual(executed, ["J1", "J2", "J3", "J4"])
        self.assertEqual(self._counts(stub)[:3], (4, 3, 1))

    def test_ac20d_stop_before_second_of_four_only_old_line(self):
        jobs = self._jobs(("J1", "SELECT 1 AS a"), ("J2", "DELETE FROM t"),
                          ("J3", "SELECT 3 AS a"), ("J4", "SELECT 4 AS a"))
        stub, executed = self._run(jobs, stop_after=1)
        self.assertEqual(self._not_run_lines(stub), [USER_STOP_TEXT.format(n=3)])
        text = "".join(stub.results_text.inserted)
        self.assertNotIn("⛔", text)
        self.assertNotIn("data-modification job failed", text)
        self.assertEqual(executed, ["J1"])
        self.assertEqual(self._counts(stub)[:3], (1, 1, 0))
        self.assertLess(stub.results_text.inserted.index(USER_STOP_TEXT.format(n=3)),
                        self._total_index(stub))


# --------------------------------------------------------------- BH-13 polls
def make_poll_stub(*, busy: bool = False) -> GUI:
    stub = GUI.__new__(GUI)
    stub._active_db_lock = threading.Lock()
    stub._active_db_connections = {}
    stub._batch_running = False
    stub._running_job_ids = {1} if busy else set()
    stub.execute_btn = _Btn("▶  Run")
    stub.export_excel_btn = _Btn("Export")
    stub.inspect_btn = _Btn("Tables")
    stub._stop_buttons = []
    return stub


class PollRootTests(unittest.TestCase):
    def test_poll_root_prefers_main_root(self):
        stub = make_poll_stub()
        stub.root = mock.Mock(name="dialog")
        stub._main_root = mock.Mock(name="main")
        self.assertIs(stub._poll_root(), stub._main_root)

    def test_poll_root_falls_back_without_main_root(self):
        stub = make_poll_stub()
        stub.root = mock.Mock(name="root")
        self.assertIs(stub._poll_root(), stub.root)
        stub._main_root = None
        self.assertIs(stub._poll_root(), stub.root)

    def test_init_stores_main_root(self):
        src = pyinspect.getsource(GUI.__init__)
        self.assertRegex(src, r"self\._main_root\s*=\s*root\b")


class RefreshStopButtonsMainRootTests(unittest.TestCase):
    """R15-AC-36 with stubs."""

    def _stub(self, *, busy: bool, with_main: bool = True):
        stub = make_poll_stub(busy=busy)
        stub.root = mock.Mock(name="dialog")
        if with_main:
            stub._main_root = mock.Mock(name="main")
        return stub

    def test_normal_path_reschedules_on_main_root(self):
        for busy in (True, False):
            with self.subTest(busy=busy):
                stub = self._stub(busy=busy)
                with mock.patch.object(GUI, "_apply_run_lock") as lock:
                    stub._refresh_stop_buttons()
                lock.assert_called_once_with(busy)
                stub._main_root.after.assert_called_once_with(300, stub._refresh_stop_buttons)
                stub.root.after.assert_not_called()

    def test_is_busy_raises_reschedules_on_main_root(self):
        stub = self._stub(busy=False)
        with mock.patch.object(GUI, "_is_busy", side_effect=ValueError("boom")), \
                mock.patch.object(GUI, "_apply_run_lock") as lock, \
                mock.patch("builtins.print"):
            stub._refresh_stop_buttons()
        lock.assert_not_called()
        stub._main_root.after.assert_called_once_with(300, stub._refresh_stop_buttons)
        stub.root.after.assert_not_called()

    def test_apply_run_lock_raises_reschedules_on_main_root(self):
        stub = self._stub(busy=True)
        with mock.patch.object(GUI, "_apply_run_lock", side_effect=RuntimeError("x")), \
                mock.patch("builtins.print"):
            stub._refresh_stop_buttons()
        stub._main_root.after.assert_called_once_with(300, stub._refresh_stop_buttons)
        stub.root.after.assert_not_called()

    def test_root_restored_to_main_same_result(self):
        stub = make_poll_stub()
        main = mock.Mock(name="main")
        stub.root = main
        stub._main_root = main
        with mock.patch.object(GUI, "_apply_run_lock"):
            stub._refresh_stop_buttons()
        main.after.assert_called_once_with(300, stub._refresh_stop_buttons)

    def test_stub_without_main_root_keeps_old_behaviour(self):
        stub = self._stub(busy=False, with_main=False)
        with mock.patch.object(GUI, "_apply_run_lock"):
            stub._refresh_stop_buttons()
        stub.root.after.assert_called_once_with(300, stub._refresh_stop_buttons)
        stub2 = self._stub(busy=False, with_main=False)
        with mock.patch.object(GUI, "_is_busy", side_effect=ValueError("b")), \
                mock.patch("builtins.print"):
            stub2._refresh_stop_buttons()
        stub2.root.after.assert_called_once_with(300, stub2._refresh_stop_buttons)


def _build_refresh_target_summary(stub, target_main, target_sub):
    """The real closure from GUI.__init__ (same approach as
    tests/test_r11_connection_target_snapshot.py)."""
    tree = ast.parse(textwrap.dedent(pyinspect.getsource(GUI.__init__)))
    found = [n for n in ast.walk(tree)
             if isinstance(n, ast.FunctionDef) and n.name == "_refresh_target_summary"]
    assert len(found) == 1
    factory = ast.parse(
        "def _factory(self, target_main, target_sub):\n    return _refresh_target_summary\n"
    )
    factory.body[0].body.insert(0, found[0])
    ast.fix_missing_locations(factory)
    namespace: dict = {}
    exec(compile(factory, "<_refresh_target_summary>", "exec"), vars(app).copy(), namespace)
    return namespace["_factory"](stub, target_main, target_sub)


class RefreshTargetSummaryMainRootTests(unittest.TestCase):
    """R15-AC-37."""

    def _stub(self, *, keep: bool, with_main: bool = True):
        stub = GUI.__new__(GUI)
        stub.root = mock.Mock(name="dialog")
        if with_main:
            stub._main_root = mock.Mock(name="main")
        stub._update_target_summary = mock.Mock(return_value=keep)
        return stub

    def test_reschedules_on_main_root(self):
        stub = self._stub(keep=True)
        tm, ts = object(), object()
        refresh = _build_refresh_target_summary(stub, tm, ts)
        refresh()
        stub._update_target_summary.assert_called_once_with(tm, ts)
        stub._main_root.after.assert_called_once_with(500, refresh)
        stub.root.after.assert_not_called()

    def test_false_does_not_reschedule(self):
        stub = self._stub(keep=False)
        refresh = _build_refresh_target_summary(stub, object(), object())
        refresh()
        stub._update_target_summary.assert_called_once()
        stub._main_root.after.assert_not_called()
        stub.root.after.assert_not_called()

    def test_stub_without_main_root_keeps_old_behaviour(self):
        stub = self._stub(keep=True, with_main=False)
        refresh = _build_refresh_target_summary(stub, object(), object())
        refresh()
        stub.root.after.assert_called_once_with(500, refresh)
        stub2 = self._stub(keep=False, with_main=False)
        _build_refresh_target_summary(stub2, object(), object())()
        stub2.root.after.assert_not_called()


# ---------------------------------------------------------------- real Tk
class RealTkPollSurvivesDialogTests(unittest.TestCase):
    """R15-AC-36/37 with a real Tk: a poll scheduled while self.root was an
    Edit dialog keeps running after that dialog is destroyed."""

    def setUp(self) -> None:
        try:
            self.main = tk.Tk()
        except tk.TclError as e:  # pragma: no cover - no display
            self.skipTest(f"no Tk display: {e}")
        self.main.withdraw()
        self.bg_errors: List[str] = []
        # Collect background errors (e.g. "invalid command name") instead of
        # letting Tk open its error dialog.
        self.main.tk.createcommand("bgerror", lambda *a: self.bg_errors.append(" ".join(map(str, a))))
        self.dialog = tk.Toplevel(self.main)
        self.dialog.withdraw()
        self.addCleanup(self._destroy_main)

    def _destroy_main(self) -> None:
        try:
            self.main.destroy()
        except tk.TclError:
            pass

    def _pump(self, seconds: float, until: Callable[[], bool]) -> None:
        end = time.monotonic() + seconds
        while time.monotonic() < end and not until():
            self.main.update()
            time.sleep(0.01)

    def test_stop_buttons_poll_survives_dialog_destroy(self):
        stub = make_poll_stub()
        stub._main_root = self.main
        stub.root = self.dialog  # Edit Job swapped self.root
        calls: List[float] = []

        def counting():
            calls.append(time.monotonic())
            if len(calls) < 4:
                GUI._refresh_stop_buttons(stub)

        stub._refresh_stop_buttons = counting
        with mock.patch.object(GUI, "_apply_run_lock") as lock, \
                mock.patch("builtins.print") as prn:
            counting()  # first poll while self.root is the dialog
            self.dialog.destroy()
            stub.root = self.main  # Edit Job restores backup_root
            self._pump(3.0, lambda: len(calls) >= 4)
        self.assertGreaterEqual(len(calls), 4, f"poll died; bgerrors={self.bg_errors}")
        prn.assert_not_called()  # normal path, not the _is_busy-failed path
        self.assertEqual(lock.call_count, 3)  # the 4th call ends the test poll
        self.assertEqual(self.bg_errors, [])

    def test_target_summary_poll_survives_dialog_destroy(self):
        stub = GUI.__new__(GUI)
        stub._main_root = self.main
        stub.root = self.dialog
        results = iter([True, True, True, False])
        seen: List[int] = []

        def update(_m, _s):
            seen.append(1)
            return next(results)

        stub._update_target_summary = update
        refresh = _build_refresh_target_summary(stub, None, None)
        refresh()
        self.dialog.destroy()
        stub.root = self.main
        self._pump(4.0, lambda: len(seen) >= 4)
        self.assertEqual(len(seen), 4, f"poll died; bgerrors={self.bg_errors}")
        # False stops the poll: no 5th call
        self._pump(0.8, lambda: False)
        self.assertEqual(len(seen), 4)
        self.assertEqual(self.bg_errors, [])


if __name__ == "__main__":
    unittest.main()
