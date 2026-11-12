"""T6: no new run of any kind may start while a run is busy (AC-5, AC-6).

No Tk window, no database: threading.Thread, messagebox, filedialog and
tk.Toplevel are patched.
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


class _FakeButton:
    def __init__(self, text: str = "", state: str = "normal") -> None:
        self.text = text
        self.state = state
        self.config_calls: list = []

    def cget(self, key):
        return self.text if key == "text" else self.state

    def __getitem__(self, key):
        return self.cget(key)

    def config(self, **kw):
        self.config_calls.append(kw)
        self.state = kw.get("state", self.state)
        self.text = kw.get("text", self.text)

    configure = config


class _FakeText:
    def __init__(self, content: str = "") -> None:
        self.content = content
        self.inserted: list = []
        self.seen: list = []
        self.deleted: list = []

    def insert(self, _index, value):
        self.inserted.append(value)

    def see(self, index):
        self.seen.append(index)

    def delete(self, *args):
        self.deleted.append(args)

    def get(self, *_args):
        return self.content


class _FakeEntry:
    def __init__(self, value: str = "") -> None:
        self.value = value

    def get(self):
        return self.value


BUSY_CASES = {
    "export": dict(export_text="⏳ Exporting..."),
    "other_job": dict(running=True),
    "batch": dict(batch=True),
    "inspect_loading": dict(inspect_text="⏳ Loading..."),
    "execute_loading": dict(execute_text="⏳ Loading..."),
    "connection": dict(connection=True),
}


def make_stub(*, export_text="Export Excel", running=False, batch=False,
              inspect_text="Tables", execute_text="▶  Run", connection=False):
    stub = GUI.__new__(GUI)
    stub._active_db_lock = threading.Lock()
    stub._active_db_connections = {object(): object()} if connection else {}
    stub._running_job_ids = {id(object())} if running else set()
    stub._batch_running = batch
    stub.execute_btn = _FakeButton(execute_text)
    stub.export_excel_btn = _FakeButton(export_text)
    stub.inspect_btn = _FakeButton(inspect_text)
    stub.save_job_btn = _FakeButton("Save Job")
    stub.results_text = _FakeText()
    stub.sql_context = _FakeText("SELECT 1 FROM dual")
    stub.db_name = _FakeEntry("")
    stub.profile_combo = _FakeEntry("P1")
    stub.engine = mock.Mock(name="engine")
    stub.root = mock.Mock(name="root")
    stub.saved_jobs = []
    stub._confirm_data_change = mock.Mock(name="_confirm_data_change", return_value=True)
    stub._prepare_run_sql = mock.Mock(
        name="_prepare_run_sql", side_effect=lambda jobs: [j["query"] for j in jobs]
    )
    stub._start_stoppable_run = mock.Mock(name="_start_stoppable_run")
    stub._reuse_last_run_results = mock.Mock(name="_reuse_last_run_results")
    stub.get_jobs_to_run = mock.Mock(name="get_jobs_to_run", return_value=[])
    stub._current_profile_jobs = mock.Mock(name="_current_profile_jobs", return_value=[])
    stub._start_job_result_report = mock.Mock()
    stub._clear_results_grid = mock.Mock()
    stub.update_job_status = mock.Mock()
    return stub


class _Patched:
    """Patch every way a run could start or a window could open."""

    def __enter__(self):
        self._patches = [
            mock.patch.object(app.threading, "Thread"),
            mock.patch.object(app, "messagebox"),
            mock.patch.object(app, "filedialog"),
            mock.patch.object(app.tk, "Toplevel"),
            mock.patch.object(app, "ui_dialog"),
        ]
        self.thread, self.mb, self.fd, self.toplevel, self.dialog = (
            p.start() for p in self._patches
        )
        return self

    def __exit__(self, *exc):
        for p in reversed(self._patches):
            p.stop()
        return False


def assert_refused(test, stub, patched, action: str, log_count: int = 1) -> None:
    patched.thread.assert_not_called()
    test.assertEqual(patched.mb.mock_calls, [])
    test.assertEqual(patched.fd.mock_calls, [])
    patched.toplevel.assert_not_called()
    patched.dialog.assert_not_called()
    stub._confirm_data_change.assert_not_called()
    stub._prepare_run_sql.assert_not_called()
    stub._start_stoppable_run.assert_not_called()
    test.assertEqual(len(stub.results_text.inserted), log_count, stub.results_text.inserted)
    for message in stub.results_text.inserted:
        test.assertTrue(message.startswith(f"⏳ {action}: "), message)
        test.assertTrue(message.endswith("\n"))
    test.assertEqual(stub.results_text.deleted, [])
    for btn in (stub.execute_btn, stub.inspect_btn, stub.save_job_btn, stub.export_excel_btn):
        test.assertEqual(btn.config_calls, [])


class RunJobWhileExportingTests(unittest.TestCase):
    """AC-5"""

    def test_run_job_refused_while_exporting(self):
        stub = make_stub(export_text="⏳ Exporting...")
        job = {"name": "J1", "query": "SELECT 1", "profile": "P1"}
        with _Patched() as p:
            self.assertIsNone(stub.run_job(job))
        assert_refused(self, stub, p, "Run Job")
        self.assertNotIn(id(job), stub._running_job_ids)
        self.assertEqual(stub._running_job_ids, set())
        stub.update_job_status.assert_not_called()


class AllEntriesRefusedWhileBusyTests(unittest.TestCase):
    """AC-6"""

    def _check(self, call, action: str) -> None:
        for case, kwargs in BUSY_CASES.items():
            with self.subTest(busy=case):
                stub = make_stub(**kwargs)
                before_ids = set(stub._running_job_ids)
                with _Patched() as p:
                    self.assertIsNone(call(stub))
                assert_refused(self, stub, p, action)
                self.assertEqual(stub._running_job_ids, before_ids)

    def test_run_job(self):
        self._check(lambda s: s.run_job({"name": "J", "query": "SELECT 1"}), "Run Job")

    def test_run_selected_job_without_override(self):
        def call(stub):
            result = stub.run_selected_job()
            stub.get_jobs_to_run.assert_not_called()
            return result
        self._check(call, "Run all")

    def test_run_selected_job_with_override(self):
        jobs = [{"name": "A", "query": "SELECT 1"}, {"name": "B", "query": "SELECT 2"}]

        def call(stub):
            result = stub.run_selected_job(jobs_override=jobs)
            for job in jobs:
                self.assertNotIn("run_index", job)
            return result
        self._check(call, "Run all")

    def test_run_selected_job_empty_list_no_warning(self):
        # "No jobs to run" must not pop up while busy
        self._check(lambda s: s.run_selected_job(jobs_override=[]), "Run all")

    def test_export_jobs_to_excel(self):
        def call(stub):
            result = stub.export_jobs_to_excel(
                jobs_override=[{"name": "A", "query": "SELECT 1"}], file_prefix="G"
            )
            stub._reuse_last_run_results.assert_not_called()
            return result
        self._check(call, "Export")

    def test_export_jobs_to_excel_without_override(self):
        def call(stub):
            result = stub.export_jobs_to_excel()
            stub.get_jobs_to_run.assert_not_called()
            return result
        self._check(call, "Export")

    def test_execute_query(self):
        self._check(lambda s: s.execute_query(), "Run")

    def test_list_tables(self):
        self._check(lambda s: s.list_tables(), "Tables")


class SameJobTwiceTests(unittest.TestCase):
    def test_second_click_on_same_job_is_refused(self):
        stub = make_stub()
        job = {"name": "J1", "query": "SELECT 1", "profile": "P1"}
        stub.saved_jobs = [job]
        with _Patched() as p:
            stub.run_job(job)  # idle: starts (thread is a mock, so it never finishes)
            self.assertEqual(p.thread.call_count, 1)
            self.assertIn(id(job), stub._running_job_ids)
            log_before = len(stub.results_text.inserted)
            stub.run_job(job)  # second click
            self.assertEqual(p.thread.call_count, 1)
            self.assertEqual(p.mb.mock_calls, [])
        self.assertEqual(stub._confirm_data_change.call_count, 1)
        new_logs = stub.results_text.inserted[log_before:]
        self.assertEqual(len(new_logs), 1)
        self.assertTrue(new_logs[0].startswith("⏳ Run Job: "))


class IdleBehaviourTests(unittest.TestCase):
    """When idle the entries behave as before."""

    def test_run_job_idle_starts_thread(self):
        stub = make_stub()
        job = {"name": "J1", "query": "SELECT 1", "profile": "P1"}
        stub.saved_jobs = [job]
        with _Patched() as p:
            stub.run_job(job)
        p.thread.assert_called_once()
        p.thread.return_value.start.assert_called_once_with()
        stub._confirm_data_change.assert_called_once()
        # T9: the run's target is passed on (captured once, engine at start time)
        stub._start_stoppable_run.assert_called_once()
        target = stub._start_stoppable_run.call_args.kwargs["target"]
        self.assertIsInstance(target, app.RunTarget)
        self.assertIs(target.engine, stub.engine)
        self.assertIs(stub._confirm_data_change.call_args.kwargs["target"], target)
        self.assertIn(id(job), stub._running_job_ids)
        self.assertEqual(stub.execute_btn.state, "disabled")
        self.assertFalse(any(m.startswith("⏳ Run Job:") for m in stub.results_text.inserted))

    def test_run_job_idle_confirm_cancel_does_not_add_id(self):
        stub = make_stub()
        stub._confirm_data_change.return_value = False
        job = {"name": "J1", "query": "DELETE FROM t"}
        with _Patched() as p:
            stub.run_job(job)
        p.thread.assert_not_called()
        self.assertNotIn(id(job), stub._running_job_ids)

    def test_run_job_idle_without_running_ids_attribute(self):
        stub = make_stub()
        del stub._running_job_ids
        job = {"name": "J1", "query": "SELECT 1"}
        with _Patched() as p:
            stub.run_job(job)
        p.thread.assert_called_once()
        self.assertEqual(stub._running_job_ids, {id(job)})

    def test_run_job_idle_without_engine_shows_error(self):
        stub = make_stub()
        stub.engine = None
        with _Patched() as p:
            stub.run_job({"name": "J", "query": "SELECT 1"})
        p.mb.showerror.assert_called_once()
        p.thread.assert_not_called()

    def test_run_selected_job_idle_empty_warns(self):
        stub = make_stub()
        with _Patched() as p:
            stub.run_selected_job(jobs_override=[])
        p.mb.showwarning.assert_called_once_with("Warning", "No jobs to run")

    def test_run_selected_job_idle_sets_run_index(self):
        stub = make_stub()
        stub.engine = None  # stop right after the job list is prepared
        jobs = [{"name": "A", "query": "SELECT 1"}, {"name": "B", "query": "SELECT 2"}]
        with _Patched() as p:
            stub.run_selected_job(jobs_override=jobs)
        self.assertEqual([j["run_index"] for j in jobs], [1, 2])
        p.mb.showerror.assert_called_once()

    def test_execute_query_idle_without_engine(self):
        stub = make_stub()
        stub.engine = None
        with _Patched() as p:
            stub.execute_query()
        p.mb.showerror.assert_called_once()

    def test_execute_query_idle_clears_results_and_confirms(self):
        stub = make_stub()
        stub._confirm_data_change.return_value = False  # user cancels
        with _Patched() as p:
            stub.execute_query()
        self.assertEqual(stub.results_text.deleted, [("1.0", app.tk.END)])
        stub._confirm_data_change.assert_called_once()
        p.thread.assert_not_called()

    def test_list_tables_idle_without_engine(self):
        stub = make_stub()
        stub.engine = None
        with _Patched() as p:
            stub.list_tables()
        p.mb.showerror.assert_called_once()

    def test_export_idle_without_engine(self):
        stub = make_stub()
        stub.engine = None
        with _Patched() as p:
            stub.export_jobs_to_excel(jobs_override=[{"name": "A", "query": "SELECT 1"}])
        p.mb.showerror.assert_called_once()
        p.fd.asksaveasfilename.assert_not_called()

    def test_export_idle_opens_save_dialog(self):
        stub = make_stub()
        with _Patched() as p:
            p.fd.asksaveasfilename.return_value = ""  # user cancels
            stub.export_jobs_to_excel(jobs_override=[{"name": "A", "query": "SELECT 1"}])
        p.fd.asksaveasfilename.assert_called_once()


class ExportRecheckTests(unittest.TestCase):
    """Review fix 2: a run that starts during the save dialog / reuse question blocks Export."""

    JOBS = [{"name": "A", "query": "SELECT 1"}]

    def _make_busy(self, stub, how):
        if how == "job":
            stub._running_job_ids.add(id(object()))
        elif how == "batch":
            stub._batch_running = True
        elif how == "conn":
            stub._active_db_connections[object()] = object()

    def _assert_blocked(self, stub, p):
        p.thread.assert_not_called()
        stub._start_stoppable_run.assert_not_called()
        self.assertEqual(stub.results_text.deleted, [])
        self.assertEqual(stub.export_excel_btn.config_calls, [])
        self.assertEqual(len(stub.results_text.inserted), 1, stub.results_text.inserted)
        self.assertTrue(stub.results_text.inserted[0].startswith("⏳ Export: "))
        for name in ("showinfo", "showwarning", "showerror", "askyesno"):
            getattr(p.mb, name).assert_not_called()

    def test_busy_during_save_dialog(self):
        for how in ("job", "batch", "conn"):
            with self.subTest(busy=how):
                stub = make_stub()
                stub._reuse_last_run_results = mock.Mock(side_effect=lambda jobs: list(jobs))

                def pick(**_kw):
                    self._make_busy(stub, how)
                    return "out.xlsx"

                with _Patched() as p:
                    p.fd.asksaveasfilename.side_effect = pick
                    stub.export_jobs_to_excel(jobs_override=self.JOBS)
                self._assert_blocked(stub, p)

    def test_busy_during_reuse_question(self):
        for how in ("job", "batch", "conn"):
            with self.subTest(busy=how):
                stub = make_stub()

                def reuse(jobs):
                    self._make_busy(stub, how)
                    return list(jobs)

                stub._reuse_last_run_results = mock.Mock(side_effect=reuse)
                with _Patched() as p:
                    p.fd.asksaveasfilename.return_value = "out.xlsx"
                    stub.export_jobs_to_excel(jobs_override=self.JOBS)
                stub._reuse_last_run_results.assert_called_once()
                self._assert_blocked(stub, p)

    def test_idle_export_starts(self):
        stub = make_stub()
        stub._reuse_last_run_results = mock.Mock(side_effect=lambda jobs: list(jobs))
        with _Patched() as p:
            p.fd.asksaveasfilename.return_value = "out.xlsx"
            stub.export_jobs_to_excel(jobs_override=self.JOBS)
        stub._start_stoppable_run.assert_called_once()
        p.thread.assert_called_once()
        self.assertEqual(stub.results_text.deleted, [("1.0", app.tk.END)])
        self.assertEqual(stub.export_excel_btn.text, "⏳ Exporting...")
        self.assertFalse(any(m.startswith("⏳ Export:") for m in stub.results_text.inserted))

    def test_recheck_is_right_before_start(self):
        """Source order: the second guard sits after _reuse_last_run_results and
        immediately before _start_stoppable_run."""
        tree = ast.parse(textwrap.dedent(inspect.getsource(GUI.export_jobs_to_excel)))
        body = tree.body[0].body
        idx_start = next(
            i for i, n in enumerate(body)
            if isinstance(n, ast.Expr) and isinstance(n.value, ast.Call)
            and getattr(n.value.func, "attr", "") == "_start_stoppable_run"
        )
        guard = body[idx_start - 1]
        self.assertIsInstance(guard, ast.If)
        self.assertEqual(guard.test.func.attr, "_block_if_busy")
        self.assertEqual(guard.test.args[0].value, "Export")
        guards = [n for n in body if isinstance(n, ast.If)
                  and isinstance(n.test, ast.Call)
                  and getattr(n.test.func, "attr", "") == "_block_if_busy"]
        self.assertEqual(len(guards), 2)


def _nested_function(outer, name: str) -> ast.FunctionDef:
    tree = ast.parse(textwrap.dedent(inspect.getsource(outer)))
    found = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == name]
    if len(found) != 1:
        raise AssertionError(f"expected one nested {name}, found {len(found)}")
    return found[0]


def _build_wrapper(stub, orig):
    """Compile the real _ui_run_selected_job from __init__ with a stub self."""
    func = _nested_function(GUI.__init__, "_ui_run_selected_job")
    factory = ast.parse(
        "def _factory(self, _orig_run_selected_job):\n    return _ui_run_selected_job\n"
    )
    factory.body[0].body.insert(0, func)
    ast.fix_missing_locations(factory)
    namespace: dict = {}
    exec(compile(factory, "<_ui_run_selected_job>", "exec"), vars(app).copy(), namespace)
    return namespace["_factory"](stub, orig)


class RunSelectedWrapperTests(unittest.TestCase):
    def test_busy_keeps_progress(self):
        stub = make_stub(running=True)
        progress = {"total": 5, "index": 2, "name": "Running one", "kind": "jobs"}
        stub._ui_progress = progress
        snapshot = dict(progress)
        orig = mock.Mock(name="orig_run_selected_job")
        wrapper = _build_wrapper(stub, orig)
        for override in (None, [{"name": "A"}]):
            with self.subTest(override=override):
                wrapper(override)
                self.assertIs(stub._ui_progress, progress)
                self.assertEqual(stub._ui_progress, snapshot)
                orig.assert_called_with(override)
        stub.get_jobs_to_run.assert_not_called()

    def test_idle_resets_progress(self):
        stub = make_stub()
        stub._ui_progress = {"total": 9, "index": 9, "name": "old", "kind": "jobs"}
        orig = mock.Mock(name="orig_run_selected_job")
        wrapper = _build_wrapper(stub, orig)
        wrapper([{"name": "A"}, {"name": "B"}])
        self.assertEqual(
            stub._ui_progress, {"total": 2, "index": 0, "name": "", "kind": "jobs"}
        )
        orig.assert_called_once_with([{"name": "A"}, {"name": "B"}])

    def test_busy_wrapper_with_real_run_selected_job_logs(self):
        stub = make_stub(batch=True)
        progress = {"total": 3, "index": 1, "name": "x", "kind": "jobs"}
        stub._ui_progress = progress
        wrapper = _build_wrapper(stub, lambda jo=None: GUI.run_selected_job(stub, jo))
        with _Patched() as p:
            wrapper([{"name": "A", "query": "SELECT 1"}])
        assert_refused(self, stub, p, "Run all")
        self.assertEqual(stub._ui_progress, {"total": 3, "index": 1, "name": "x", "kind": "jobs"})


class RunGroupSourceTests(unittest.TestCase):
    def _run_group(self) -> ast.FunctionDef:
        for name, member in inspect.getmembers(GUI, inspect.isfunction):
            try:
                src = inspect.getsource(member)
            except (OSError, TypeError):
                continue
            if "def run_group(" in src:
                return _nested_function(member, "run_group")
        raise AssertionError("run_group not found")

    def test_no_busy_popup_and_delegates(self):
        func = self._run_group()
        src = ast.unparse(func)
        self.assertNotIn("showinfo", src)
        self.assertNotIn("_batch_running", src)
        calls = [
            n for n in ast.walk(func)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
            and n.func.attr == "run_selected_job"
        ]
        self.assertEqual(len(calls), 1)
        # engine check kept
        self.assertIn("self.engine", src)


if __name__ == "__main__":
    unittest.main()
