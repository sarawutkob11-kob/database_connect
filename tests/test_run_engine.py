"""T9: a run uses the engine captured when it started (AC-7, AC-8, AC-9).

SQL Editor (execute_query / _execute_query_background) and single Job (run_job).
Two SQLite databases in a TemporaryDirectory play engine A and engine B.
threading.Thread is patched so the worker runs only when the test says so.
"""

import os
import sys
import tempfile
import threading
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import database_connect_gui as app  # noqa: E402

GUI = app.DatabaseConnectorGUI


def make_db(test: unittest.TestCase, folder: str, name: str, value: str):
    from sqlalchemy import create_engine

    engine = create_engine(f"sqlite:///{os.path.join(folder, name)}.db")
    test.addCleanup(engine.dispose)
    with engine.connect() as conn:
        conn.exec_driver_sql("CREATE TABLE t (a TEXT)")
        conn.exec_driver_sql(f"INSERT INTO t VALUES ('{value}')")
        conn.commit()
    return engine


def values(engine) -> list:
    with engine.connect() as conn:
        return [r[0] for r in conn.exec_driver_sql("SELECT a FROM t ORDER BY a")]


class _Btn:
    def __init__(self, text=""):
        self.text = text
        self.state = "normal"

    def cget(self, key):
        return self.text if key == "text" else self.state

    def __getitem__(self, key):
        return self.cget(key)

    def config(self, **kw):
        self.state = kw.get("state", self.state)
        self.text = kw.get("text", self.text)

    configure = config


class _Text:
    def __init__(self, content=""):
        self.content = content
        self.inserted = []

    def insert(self, _i, v):
        self.inserted.append(v)

    def see(self, *_a):
        pass

    def delete(self, *_a):
        pass

    def get(self, *_a):
        return self.content


class _Var:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value


class _Entry(_Var):
    pass


class _ThreadCapture:
    """Replaces threading.Thread: keeps the target, runs it only on demand."""

    def __init__(self):
        self.targets = []

    def __call__(self, target=None, daemon=None, **_kw):
        self.targets.append(target)
        thread = mock.Mock()
        return thread

    def run_all(self):
        for target in self.targets:
            target()


def make_stub(engine):
    stub = GUI.__new__(GUI)
    stub._active_db_lock = threading.Lock()
    stub._active_db_connections = {}
    stub._running_job_ids = set()
    stub._batch_running = False
    stub.engine = engine
    stub.execute_btn = _Btn("▶  Run")
    stub.export_excel_btn = _Btn("Export")
    stub.inspect_btn = _Btn("Tables")
    stub.save_job_btn = _Btn("Save")
    stub.results_text = _Text()
    stub.sql_context = _Text()
    stub.profile_combo = _Entry("P1")
    stub.debug_mode = _Var(False)
    stub.saved_jobs = []
    stub.root = mock.Mock(name="root")
    stub.after_calls = []
    stub.root.after.side_effect = lambda _ms, fn: stub.after_calls.append(fn)
    stub._prepare_run_sql = mock.Mock(side_effect=lambda jobs: [j["query"] for j in jobs])
    stub._confirm_data_change = mock.Mock(return_value=True)
    stub._start_stoppable_run = mock.Mock()
    stub._start_job_result_report = mock.Mock()
    stub._finish_job_result_report = mock.Mock()
    stub._clear_results_grid = mock.Mock()
    stub._show_results_grid_sets = mock.Mock()
    stub.update_job_status = mock.Mock()
    stub.on_query_success = mock.Mock()
    stub.on_modification_success = mock.Mock()
    stub.on_query_error_enhanced = mock.Mock()
    return stub


def run_after_calls(stub):
    calls, stub.after_calls = stub.after_calls, []
    for fn in calls:
        fn()


class ExplicitEngineTests(unittest.TestCase):
    """AC-7"""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)  # runs after the engines are disposed
        self.a = make_db(self, tmp.name, "a", "from_A")
        self.b = make_db(self, tmp.name, "b", "from_B")
        self.stub = make_stub(self.b)

    def test_read_uses_given_engine(self):
        df = self.stub.read_sql_dataframe("SELECT a FROM t;", engine=self.a)
        self.assertEqual(list(df["a"]), ["from_A"])

    def test_modify_uses_given_engine_only(self):
        rows = self.stub._execute_modification("UPDATE t SET a = 'changed';", engine=self.a)
        self.assertEqual(rows, 1)
        self.assertEqual(values(self.a), ["changed"])
        self.assertEqual(values(self.b), ["from_B"])

    def test_insert_on_given_engine_only(self):
        self.stub._execute_modification("INSERT INTO t VALUES ('new')", engine=self.a)
        self.assertEqual(values(self.a), ["from_A", "new"])
        self.assertEqual(values(self.b), ["from_B"])


class DefaultEngineTests(unittest.TestCase):
    """AC-8: no engine given -> self.engine"""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.b = make_db(self, tmp.name, "b", "from_B")
        self.stub = make_stub(self.b)

    def test_read_defaults_to_self_engine(self):
        self.assertEqual(list(self.stub.read_sql_dataframe("SELECT a FROM t")["a"]), ["from_B"])
        self.assertEqual(
            list(self.stub.read_sql_dataframe("SELECT a FROM t", engine=None)["a"]), ["from_B"]
        )

    def test_modify_defaults_to_self_engine(self):
        self.stub._execute_modification("UPDATE t SET a = 'x'")
        self.assertEqual(values(self.b), ["x"])


class RunJobEngineTests(unittest.TestCase):
    """AC-9 for run_job: the worker runs on the engine of the start time."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.a = make_db(self, tmp.name, "a", "from_A")
        self.b = make_db(self, tmp.name, "b", "from_B")

    def _start(self, query):
        stub = make_stub(self.a)
        job = {"name": "J1", "query": query, "profile": "P1"}
        stub.saved_jobs = [job]
        threads = _ThreadCapture()
        with mock.patch.object(app.threading, "Thread", side_effect=threads), \
                mock.patch.object(app, "messagebox") as mb:
            stub.run_job(job)
        mb.showerror.assert_not_called()
        self.assertEqual(len(threads.targets), 1)
        return stub, job, threads

    def test_select_runs_on_start_engine_after_swap(self):
        stub, job, threads = self._start("SELECT a FROM t")
        stub.engine = self.b  # e.g. a reconnect while the job waits
        stub._run_target = app.RunTarget(self.b, None)
        threads.run_all()
        run_after_calls(stub)
        status_call = stub.update_job_status.call_args_list[-1]
        self.assertEqual(status_call.args[2], "success")
        self.assertEqual(list(status_call.args[3]["a"]), ["from_A"])
        self.assertNotIn(id(job), stub._running_job_ids)

    def test_modify_runs_on_start_engine_after_swap(self):
        stub, _job, threads = self._start("UPDATE t SET a = 'changed'")
        stub.engine = self.b
        threads.run_all()
        run_after_calls(stub)
        self.assertEqual(values(self.a), ["changed"])
        self.assertEqual(values(self.b), ["from_B"])

    def test_worker_never_reads_self_engine(self):
        stub, _job, threads = self._start("SELECT a FROM t")
        poisoned = mock.Mock(name="B_must_not_be_used")
        poisoned.raw_connection.side_effect = AssertionError("worker used self.engine")
        poisoned.connect.side_effect = AssertionError("worker used self.engine")
        stub.engine = poisoned
        threads.run_all()
        run_after_calls(stub)
        self.assertEqual(stub.update_job_status.call_args_list[-1].args[2], "success")
        poisoned.raw_connection.assert_not_called()
        poisoned.connect.assert_not_called()

    def test_same_target_to_confirm_and_start(self):
        stub = make_stub(self.a)
        ci = app.ConnectionInfo("P1", "SQLite", "u", "h", "", "")
        stub._run_target = app.RunTarget(self.a, ci)
        job = {"name": "J1", "query": "SELECT a FROM t"}
        with mock.patch.object(app.threading, "Thread"):
            stub.run_job(job)
        confirm_target = stub._confirm_data_change.call_args.kwargs["target"]
        start_target = stub._start_stoppable_run.call_args.kwargs["target"]
        self.assertIs(confirm_target, start_target)
        self.assertIs(confirm_target, stub._run_target)
        self.assertIs(confirm_target.engine, self.a)
        self.assertIs(confirm_target.info, ci)

    def test_target_captured_once(self):
        stub = make_stub(self.a)
        real = GUI._capture_run_target
        with mock.patch.object(GUI, "_capture_run_target", autospec=True,
                               side_effect=real) as cap, \
                mock.patch.object(app.threading, "Thread"):
            stub.run_job({"name": "J", "query": "SELECT 1"})
        self.assertEqual(cap.call_count, 1)

    def test_confirm_cancel_starts_nothing(self):
        stub = make_stub(self.a)
        stub._confirm_data_change.return_value = False
        with mock.patch.object(app.threading, "Thread") as th:
            stub.run_job({"name": "J", "query": "DELETE FROM t"})
        th.assert_not_called()
        stub._start_stoppable_run.assert_not_called()
        self.assertEqual(values(self.a), ["from_A"])


class QueryBackgroundEngineTests(unittest.TestCase):
    """AC-9 for _execute_query_background (SQL Editor worker)."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.a = make_db(self, tmp.name, "a", "from_A")
        self.b = make_db(self, tmp.name, "b", "from_B")

    def _run(self, query, *, debug, pass_engine):
        stub = make_stub(self.a)
        stub.debug_mode = _Var(debug)
        threads = _ThreadCapture()
        dialog = mock.Mock(name="loading_dialog")
        with mock.patch.object(app.threading, "Thread", side_effect=threads):
            if pass_engine:
                stub._execute_query_background(query, dialog, engine=self.a)
            else:
                stub._execute_query_background(query, dialog)
        stub.engine = self.b  # swap before the worker runs
        with mock.patch("builtins.print") as printed:
            threads.run_all()
        run_after_calls(stub)
        return stub, dialog, printed

    def test_select_goes_to_start_engine(self):
        for debug in (False, True):
            for pass_engine in (True, False):
                with self.subTest(debug=debug, pass_engine=pass_engine):
                    stub, dialog, printed = self._run(
                        "SELECT a FROM t", debug=debug, pass_engine=pass_engine
                    )
                    stub.on_query_error_enhanced.assert_not_called()
                    stub.on_query_success.assert_called_once()
                    df, sql, dlg = stub.on_query_success.call_args.args
                    self.assertEqual(list(df["a"]), ["from_A"])
                    self.assertIs(dlg, dialog)
                    if debug:
                        printed_text = " ".join(str(c.args[0]) for c in printed.call_args_list
                                                if c.args)
                        self.assertIn("Engine: sqlite", printed_text)

    def test_modify_goes_to_start_engine(self):
        for debug in (False, True):
            with self.subTest(debug=debug):
                stub, _dialog, _ = self._run(
                    "UPDATE t SET a = 'via_A'", debug=debug, pass_engine=True
                )
                stub.on_query_error_enhanced.assert_not_called()
                stub.on_modification_success.assert_called_once()
                self.assertEqual(stub.on_modification_success.call_args.args[0], 1)
                self.assertEqual(values(self.a), ["via_A"])
                self.assertEqual(values(self.b), ["from_B"])

    def test_debug_path_never_touches_self_engine(self):
        stub = make_stub(self.a)
        stub.debug_mode = _Var(True)
        threads = _ThreadCapture()
        with mock.patch.object(app.threading, "Thread", side_effect=threads):
            stub._execute_query_background("SELECT a FROM t", mock.Mock(), engine=self.a)
        poisoned = mock.Mock(name="B")
        type(poisoned).dialect = mock.PropertyMock(side_effect=AssertionError("self.engine read"))
        poisoned.raw_connection.side_effect = AssertionError("self.engine read")
        stub.engine = poisoned
        with mock.patch("builtins.print"):
            threads.run_all()
        run_after_calls(stub)
        stub.on_query_error_enhanced.assert_not_called()
        stub.on_query_success.assert_called_once()


class ExecuteQueryTargetTests(unittest.TestCase):
    """execute_query captures the target once and passes engine=target.engine."""

    def _stub(self, engine, info=None):
        stub = make_stub(engine)
        if info is not None:
            stub._run_target = app.RunTarget(engine, info)
        stub.sql_context = _Text("SELECT a FROM t")
        stub._create_loading_dialog_with_retry = mock.Mock(name="loading")
        stub._execute_query_background = mock.Mock(name="bg")
        return stub

    def test_same_target_everywhere(self):
        engine = mock.Mock(name="A")
        ci = app.ConnectionInfo("P1", "Oracle", "u", "h", "1521", "SVC")
        stub = self._stub(engine, ci)
        with mock.patch.object(app, "messagebox"):
            stub.execute_query()
        confirm_target = stub._confirm_data_change.call_args.kwargs["target"]
        start_target = stub._start_stoppable_run.call_args.kwargs["target"]
        self.assertIs(confirm_target, start_target)
        self.assertIs(confirm_target, stub._run_target)
        self.assertIs(confirm_target.engine, engine)
        args, kwargs = stub._execute_query_background.call_args
        self.assertIs(kwargs["engine"], engine)
        self.assertEqual(args[0], "SELECT a FROM t")
        self.assertIs(args[1], stub._create_loading_dialog_with_retry.return_value)

    def test_engine_set_directly_still_passed(self):
        engine = mock.Mock(name="A")
        stub = self._stub(engine)
        stub.execute_query()
        target = stub._confirm_data_change.call_args.kwargs["target"]
        self.assertEqual(target, app.RunTarget(engine, None))
        self.assertIs(stub._execute_query_background.call_args.kwargs["engine"], engine)

    def test_end_to_end_swap_before_worker(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        a = make_db(self, tmp.name, "a", "from_A")
        b = make_db(self, tmp.name, "b", "from_B")
        stub = make_stub(a)
        stub.sql_context = _Text("SELECT a FROM t")
        stub._create_loading_dialog_with_retry = mock.Mock(name="loading")
        threads = _ThreadCapture()
        with mock.patch.object(app.threading, "Thread", side_effect=threads):
            stub.execute_query()
        stub.engine = b
        threads.run_all()
        run_after_calls(stub)
        stub.on_query_success.assert_called_once()
        self.assertEqual(list(stub.on_query_success.call_args.args[0]["a"]), ["from_A"])

    def test_confirm_cancel_no_worker(self):
        stub = self._stub(mock.Mock())
        stub._confirm_data_change.return_value = False
        stub.execute_query()
        stub._execute_query_background.assert_not_called()
        stub._start_stoppable_run.assert_not_called()


class StartStoppableRunTests(unittest.TestCase):
    def test_target_passed_to_log_run_context(self):
        stub = GUI.__new__(GUI)
        stub._stop_event = threading.Event()
        stub._stop_event.set()
        target = app.RunTarget(mock.Mock(), None)
        with mock.patch.object(GUI, "_log_run_context") as log:
            stub._start_stoppable_run(target=target)
        self.assertFalse(stub._stop_event.is_set())
        log.assert_called_once_with(target)

    def test_default_none(self):
        stub = GUI.__new__(GUI)
        stub._stop_event = threading.Event()
        with mock.patch.object(GUI, "_log_run_context") as log:
            stub._start_stoppable_run()
        log.assert_called_once_with(None)


if __name__ == "__main__":
    unittest.main()
