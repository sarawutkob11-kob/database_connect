"""T12: yellow banner / status bar / Stop follow every kind of run (H1).

AC-20..AC-23 through the poll, AC-24 banner text, run_job progress lifecycle,
stop_running_queries guard, _refresh_live_ui (compiled from __init__ with fakes).
No Tk window. AC-25 is Manual/GUI.
"""

import ast
import inspect
import os
import sys
import textwrap
import threading
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import database_connect_gui as app  # noqa: E402

GUI = app.DatabaseConnectorGUI


class FakeWidget:
    def __init__(self, text="", state="normal", alive=True):
        self.text = text
        self.state = state
        self.alive = alive
        self.config_calls = []

    def cget(self, key):
        return self.text if key == "text" else self.state

    def __getitem__(self, key):
        return self.cget(key)

    def config(self, **kw):
        self.config_calls.append(kw)
        self.state = kw.get("state", self.state)
        self.text = kw.get("text", self.text)

    configure = config

    def winfo_exists(self):
        return 1 if self.alive else 0


class FakeText:
    def __init__(self):
        self.inserted = []

    def insert(self, _i, v):
        self.inserted.append(v)

    def see(self, *_a):
        pass


def make_stub(*, job=False, connection=None, inspect_text="▦  Tables", batch=False,
              export_text="⇩  Export", execute_text="▶  Run", progress=None):
    stub = GUI.__new__(GUI)
    stub._active_db_lock = threading.Lock()
    stub._active_db_connections = {object(): connection} if connection is not None else {}
    stub._running_job_ids = {12345} if job else set()
    stub._batch_running = batch
    stub.execute_btn = FakeWidget(execute_text)
    stub.export_excel_btn = FakeWidget(export_text)
    stub.inspect_btn = FakeWidget(inspect_text)
    stub.save_job_btn = FakeWidget("Save")
    stub.results_text = FakeText()
    stub._stop_event = threading.Event()
    stub._stop_buttons = []
    stub.root = mock.Mock(name="root")
    stub._ui_progress = progress if progress is not None else {
        "total": 0, "index": 0, "name": "", "kind": None}
    return stub


BUSY_CASES = {
    "AC-20 single job": dict(job=True, progress={"total": 0, "index": 0,
                                                 "name": "Daily Balance", "kind": "job"}),
    "AC-21 connection": dict(connection=object()),
    "AC-22 inspect loading": dict(inspect_text="⏳ Loading..."),
    "batch": dict(batch=True),
    "export": dict(export_text="⏳ Exporting..."),
    "sql editor": dict(execute_text="⏳ Loading..."),
}


class StopButtonPollTests(unittest.TestCase):
    """AC-20..AC-23 through _refresh_stop_buttons."""

    def _poll(self, stub):
        with mock.patch.object(GUI, "_apply_run_lock") as lock:
            stub._refresh_stop_buttons()
        return lock

    def test_busy_enables_stop_buttons(self):
        for case, kwargs in BUSY_CASES.items():
            with self.subTest(case=case):
                stub = make_stub(**kwargs)
                b1, b2 = FakeWidget(state="disabled"), FakeWidget(state="disabled")
                stub._stop_buttons = [b1, b2]
                lock = self._poll(stub)
                self.assertEqual((b1.state, b2.state), ("normal", "normal"))
                lock.assert_called_once_with(True)
                stub.root.after.assert_called_once_with(300, stub._refresh_stop_buttons)

    def test_idle_disables_stop_buttons(self):
        stub = make_stub()
        b = FakeWidget(state="normal")
        stub._stop_buttons = [b]
        lock = self._poll(stub)
        self.assertEqual(b.state, "disabled")
        lock.assert_called_once_with(False)
        stub.root.after.assert_called_once_with(300, stub._refresh_stop_buttons)

    def test_is_busy_called_once_per_poll(self):
        stub = make_stub(job=True)
        with mock.patch.object(GUI, "_is_busy", return_value=True) as busy, \
                mock.patch.object(GUI, "_apply_run_lock"):
            stub._refresh_stop_buttons()
        busy.assert_called_once_with()

    def test_dead_stop_button_dropped(self):
        stub = make_stub(job=True)
        alive, dead = FakeWidget(state="disabled"), FakeWidget(alive=False)
        stub._stop_buttons = [alive, dead]
        self._poll(stub)
        self.assertEqual(stub._stop_buttons, [alive])

    def test_no_reconfigure_when_same(self):
        stub = make_stub(job=True)
        b = FakeWidget(state="normal")
        stub._stop_buttons = [b]
        self._poll(stub)
        self.assertEqual(b.config_calls, [])

    def test_busy_check_error_still_reschedules(self):
        stub = make_stub()
        with mock.patch.object(GUI, "_is_busy", side_effect=RuntimeError("x")), \
                mock.patch.object(GUI, "_apply_run_lock") as lock, \
                mock.patch("builtins.print"):
            stub._refresh_stop_buttons()
        lock.assert_not_called()
        stub.root.after.assert_called_once_with(300, stub._refresh_stop_buttons)


class BannerTextTests(unittest.TestCase):
    """AC-24"""

    def test_single_job_with_name(self):
        stub = make_stub(job=True, progress={"total": 0, "index": 0,
                                             "name": "Daily Balance", "kind": "job"})
        self.assertEqual(stub._running_banner_state(5),
                         ("กำลังรัน Job · Daily Balance · 00:05", None))

    def test_single_job_without_name(self):
        stub = make_stub(job=True, progress={"total": 0, "index": 0, "name": "", "kind": "job"})
        self.assertEqual(stub._running_banner_state(5), ("กำลังรัน Job · 00:05", None))

    def test_single_job_kind_without_running_id_falls_back(self):
        stub = make_stub(progress={"total": 0, "index": 0, "name": "X", "kind": "job"})
        self.assertEqual(stub._running_banner_state(5), ("กำลังรัน SQL · 00:05", None))

    def test_sql_editor_and_list_tables(self):
        for kwargs in (dict(execute_text="⏳ Loading..."), dict(inspect_text="⏳ Loading..."),
                       dict(connection=object())):
            with self.subTest(**{k: str(v) for k, v in kwargs.items()}):
                stub = make_stub(**kwargs)
                self.assertEqual(stub._running_banner_state(65), ("กำลังรัน SQL · 01:05", None))

    def test_batch(self):
        stub = make_stub(batch=True, progress={"total": 5, "index": 2, "name": "X", "kind": "jobs"})
        self.assertEqual(stub._running_banner_state(65), ("กำลังรัน Job 2 / 5 · X · 01:05", 20.0))

    def test_batch_first_job_and_no_name(self):
        stub = make_stub(batch=True, progress={"total": 4, "index": 0, "name": "", "kind": "jobs"})
        self.assertEqual(stub._running_banner_state(0), ("กำลังรัน Job 1 / 4 · 00:00", 0.0))

    def test_batch_without_total_is_not_batch_text(self):
        stub = make_stub(batch=True, progress={"total": 0, "index": 0, "name": "", "kind": "jobs"})
        self.assertEqual(stub._running_banner_state(3), ("กำลังรัน SQL · 00:03", None))

    def test_export(self):
        stub = make_stub(export_text="⏳ Exporting...")
        self.assertEqual(stub._running_banner_state(65), ("กำลัง Export Excel · 01:05", None))

    def test_precedence(self):
        both = make_stub(batch=True, export_text="⏳ Exporting...", job=True,
                         progress={"total": 3, "index": 1, "name": "A", "kind": "jobs"})
        self.assertTrue(both._running_banner_state(1)[0].startswith("กำลังรัน Job 1 / 3"))
        exp_job = make_stub(export_text="⏳ Exporting...", job=True,
                            progress={"total": 0, "index": 0, "name": "J", "kind": "job"})
        self.assertEqual(exp_job._running_banner_state(1)[0], "กำลัง Export Excel · 00:01")
        job_sql = make_stub(job=True, execute_text="⏳ Loading...",
                            progress={"total": 0, "index": 0, "name": "J", "kind": "job"})
        self.assertEqual(job_sql._running_banner_state(1)[0], "กำลังรัน Job · J · 00:01")

    def test_clock_format(self):
        stub = make_stub()
        for seconds, clock in ((0, "00:00"), (59, "00:59"), (60, "01:00"), (65, "01:05"),
                               (3599, "59:59"), (3600, "60:00")):
            with self.subTest(seconds=seconds):
                self.assertEqual(stub._running_banner_state(seconds)[0], f"กำลังรัน SQL · {clock}")

    def test_missing_progress_attribute(self):
        stub = make_stub(job=True)
        del stub._ui_progress
        self.assertEqual(stub._running_banner_state(5), ("กำลังรัน SQL · 00:05", None))


class _ThreadCapture:
    def __init__(self):
        self.targets = []

    def __call__(self, target=None, daemon=None, **_kw):
        self.targets.append(target)
        return mock.Mock()


class RunJobProgressTests(unittest.TestCase):
    def _stub(self):
        stub = make_stub()
        stub.engine = mock.Mock(name="engine")
        stub.saved_jobs = []
        stub.profile_combo = mock.Mock(get=mock.Mock(return_value="P1"))
        stub.after_calls = []
        stub.root.after.side_effect = lambda _ms, fn: stub.after_calls.append(fn)
        stub._prepare_run_sql = mock.Mock(side_effect=lambda jobs: [j["query"] for j in jobs])
        stub._confirm_data_change = mock.Mock(return_value=True)
        stub._start_stoppable_run = mock.Mock()
        for name in ("_start_job_result_report", "_finish_job_result_report",
                     "_clear_results_grid", "_show_results_grid_sets", "update_job_status"):
            setattr(stub, name, mock.Mock(name=name))
        return stub

    def _start(self, stub, job):
        threads = _ThreadCapture()
        with mock.patch.object(app.threading, "Thread", side_effect=threads):
            stub.run_job(job)
        self.assertEqual(len(threads.targets), 1)
        return threads.targets[0]

    def _finish(self, stub, worker):
        worker()
        calls, stub.after_calls = stub.after_calls, []
        for fn in calls:
            fn()

    def test_progress_set_on_start(self):
        stub = self._stub()
        job = {"name": "Daily Balance", "query": "SELECT 1", "profile": "P1"}
        self._start(stub, job)
        self.assertEqual(stub._ui_progress,
                         {"total": 0, "index": 0, "name": "Daily Balance", "kind": "job"})
        self.assertIn(id(job), stub._running_job_ids)
        self.assertEqual(stub._running_banner_state(5),
                         ("กำลังรัน Job · Daily Balance · 00:05", None))
        self.assertTrue(stub._is_busy())

    def test_progress_cleared_after_success_error_stop(self):
        import pandas as pd

        outcomes = {
            "success": dict(return_value=pd.DataFrame({"a": [1]})),
            "error": dict(side_effect=RuntimeError("ORA-00942: table or view does not exist")),
            "stop": dict(side_effect=RuntimeError("ORA-01013: user requested cancel")),
        }
        for name, behaviour in outcomes.items():
            with self.subTest(outcome=name):
                stub = self._stub()
                stub.read_sql_dataframe = mock.Mock(**behaviour)
                job = {"name": "J", "query": "SELECT 1", "profile": "P1"}
                worker = self._start(stub, job)
                self._finish(stub, worker)
                self.assertEqual(stub._running_job_ids, set())
                self.assertIsNone(stub._ui_progress["kind"])
                self.assertEqual(stub._ui_progress["name"], "")
                self.assertFalse(stub._is_busy())
                expected = "success" if name == "success" else "error"
                self.assertEqual(stub.update_job_status.call_args_list[-1].args[2], expected)

    def test_batch_progress_not_reset_by_finish(self):
        stub = self._stub()
        stub.read_sql_dataframe = mock.Mock(side_effect=RuntimeError("x"))
        job = {"name": "J", "query": "SELECT 1", "profile": "P1"}
        worker = self._start(stub, job)
        batch_progress = {"total": 3, "index": 2, "name": "B", "kind": "jobs"}
        stub._ui_progress = batch_progress
        self._finish(stub, worker)
        self.assertIs(stub._ui_progress, batch_progress)
        self.assertEqual(stub._ui_progress["kind"], "jobs")

    def test_not_reset_while_another_job_id_remains(self):
        stub = self._stub()
        stub.read_sql_dataframe = mock.Mock(return_value=mock.MagicMock())
        job = {"name": "J", "query": "SELECT 1", "profile": "P1"}
        worker = self._start(stub, job)
        other_id = object()
        stub._running_job_ids.add(id(other_id))  # another single job still running
        self._finish(stub, worker)
        self.assertEqual(stub._running_job_ids, {id(other_id)})
        self.assertEqual(stub._ui_progress["kind"], "job")
        self.assertEqual(stub.execute_btn.state, "disabled")  # buttons stay off too


class StopRunningQueriesTests(unittest.TestCase):
    def test_busy_only_from_single_job(self):
        stub = make_stub(job=True)
        stub.stop_running_queries()
        self.assertTrue(stub._stop_event.is_set())
        self.assertEqual(len(stub.results_text.inserted), 1)
        self.assertIn("Stop requested", stub.results_text.inserted[0])

    def test_busy_only_from_inspect_loading(self):
        stub = make_stub(inspect_text="⏳ Loading...")
        stub.stop_running_queries()
        self.assertTrue(stub._stop_event.is_set())
        self.assertIn("Stop requested", stub.results_text.inserted[0])

    def test_connection_with_cancel(self):
        conn = mock.Mock()
        stub = make_stub(connection=conn)
        stub.stop_running_queries()
        conn.cancel.assert_called_once_with()
        self.assertIn("cancelled 1", stub.results_text.inserted[0])

    def test_idle_does_nothing(self):
        stub = make_stub()
        self.assertIsNone(stub.stop_running_queries())
        self.assertFalse(stub._stop_event.is_set())
        self.assertEqual(stub.results_text.inserted, [])


LIVE_UI_FREE_NAMES = (
    "status_bar", "_run_clock", "rb_progress", "rb_text", "running_banner",
    "excel_strip", "excel_strip_text", "_sb_activity", "_sb_conn", "_sb_excel",
    "_sb_log", "_sb_cursor", "_excel_summary",
)


def _build_refresh_live_ui(stub, widgets):
    tree = ast.parse(textwrap.dedent(inspect.getsource(GUI.__init__)))
    found = [n for n in ast.walk(tree)
             if isinstance(n, ast.FunctionDef) and n.name == "_refresh_live_ui"]
    assert len(found) == 1
    args = ", ".join(("self",) + LIVE_UI_FREE_NAMES)
    factory = ast.parse(f"def _factory({args}):\n    return _refresh_live_ui\n")
    factory.body[0].body.insert(0, found[0])
    ast.fix_missing_locations(factory)
    import time as _time

    namespace: dict = {}
    module_globals = vars(app).copy()
    # locals of __init__ the closure also uses: `import time` and `FL = UI`
    module_globals.update(time=_time, FL=app.UI)
    exec(compile(factory, "<_refresh_live_ui>", "exec"), module_globals, namespace)
    return namespace["_factory"](stub, *(widgets[n] for n in LIVE_UI_FREE_NAMES))


class RefreshLiveUiTests(unittest.TestCase):
    def _widgets(self, mapped=False):
        w = {n: mock.MagicMock(name=n) for n in LIVE_UI_FREE_NAMES}
        w["_run_clock"] = {"start": None}
        w["_excel_summary"] = lambda: []
        w["status_bar"].winfo_exists.return_value = True
        w["running_banner"].winfo_ismapped.return_value = mapped
        w["excel_strip"].winfo_ismapped.return_value = False
        w["rb_progress"].cget.return_value = "determinate"
        w["rb_text"].cget.return_value = ""
        w["_sb_activity"] = [mock.MagicMock(name="dot"), mock.MagicMock(name="label")]
        w["_sb_conn"] = [mock.MagicMock(), mock.MagicMock()]
        w["_sb_excel"] = [mock.MagicMock(), mock.MagicMock()]
        return w

    def _stub(self, **kwargs):
        stub = make_stub(**kwargs)
        stub.status_label = FakeWidget("❌ Not Connected")
        stub.sql_context = mock.Mock(index=mock.Mock(return_value="1.0"))
        stub.results_notebook = mock.Mock()
        stub._log_dir = "logs"
        return stub

    def test_busy_single_job_shows_banner_and_running(self):
        stub = self._stub(job=True, progress={"total": 0, "index": 0,
                                              "name": "Daily Balance", "kind": "job"})
        w = self._widgets(mapped=False)
        refresh = _build_refresh_live_ui(stub, w)
        refresh()
        w["running_banner"].pack.assert_called_once()
        texts = [c.kwargs.get("text") for c in w["rb_text"].config.call_args_list]
        self.assertTrue(any(t and t.startswith("กำลังรัน Job · Daily Balance · ") for t in texts))
        w["rb_progress"].config.assert_any_call(mode="indeterminate")
        w["_sb_activity"][1].config.assert_called_with(text="Running…")
        w["status_bar"].after.assert_called_once()
        self.assertIsNotNone(w["_run_clock"]["start"])

    def test_busy_from_each_source_shows_banner(self):
        for case, kwargs in BUSY_CASES.items():
            with self.subTest(case=case):
                stub = self._stub(**kwargs)
                w = self._widgets(mapped=False)
                _build_refresh_live_ui(stub, w)()
                w["running_banner"].pack.assert_called_once()
                w["_sb_activity"][1].config.assert_called_with(text="Running…")

    def test_batch_sets_determinate_value(self):
        stub = self._stub(batch=True, progress={"total": 5, "index": 2, "name": "X", "kind": "jobs"})
        w = self._widgets()
        _build_refresh_live_ui(stub, w)()
        w["rb_progress"].__setitem__.assert_called_with("value", 20.0)

    def test_idle_hides_banner_and_ready(self):
        stub = self._stub()
        w = self._widgets(mapped=True)
        w["_run_clock"]["start"] = 123.0
        _build_refresh_live_ui(stub, w)()
        w["running_banner"].pack_forget.assert_called_once()
        w["running_banner"].pack.assert_not_called()
        w["_sb_activity"][1].config.assert_called_with(text="Ready")
        self.assertIsNone(w["_run_clock"]["start"])
        w["status_bar"].after.assert_called_once()

    def test_uses_is_busy(self):
        stub = self._stub()
        w = self._widgets(mapped=False)
        with mock.patch.object(GUI, "_is_busy", return_value=True) as busy:
            _build_refresh_live_ui(stub, w)()
        busy.assert_called()
        w["running_banner"].pack.assert_called_once()


if __name__ == "__main__":
    unittest.main()
