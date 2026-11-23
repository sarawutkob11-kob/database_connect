"""T10: Run All / Run Group, Export and list_tables keep the engine of the start time (AC-9).

SQLite files in a TemporaryDirectory are engine A and engine B (different data).
threading.Thread is patched so the worker only runs when the test says so;
root.after callbacks are collected. No Tk window.
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


def make_db(test, folder, name, value, table="t"):
    from sqlalchemy import create_engine

    engine = create_engine(f"sqlite:///{os.path.join(folder, name)}.db")
    test.addCleanup(engine.dispose)
    with engine.connect() as conn:
        conn.exec_driver_sql(f"CREATE TABLE {table} (a TEXT)")
        conn.exec_driver_sql(f"INSERT INTO {table} VALUES ('{value}')")
        conn.commit()
    return engine


def values(engine, table="t"):
    with engine.connect() as conn:
        return [r[0] for r in conn.exec_driver_sql(f"SELECT a FROM {table} ORDER BY a")]


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
    def __init__(self):
        self.inserted = []

    def insert(self, _i, v):
        self.inserted.append(v)

    def see(self, *_a):
        pass

    def delete(self, *_a):
        pass


class _Entry:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class _ThreadCapture:
    def __init__(self):
        self.targets = []

    def __call__(self, target=None, daemon=None, **_kw):
        self.targets.append(target)
        return mock.Mock()

    def run_all(self):
        for target in self.targets:
            target()


def make_stub(engine, info=None):
    stub = GUI.__new__(GUI)
    stub._active_db_lock = threading.Lock()
    stub._active_db_connections = {}
    stub._running_job_ids = set()
    stub._batch_running = False
    stub._stop_event = threading.Event()
    stub.engine = engine
    if info is not None:
        stub._run_target = app.RunTarget(engine, info)
    for name in ("execute_btn", "inspect_btn", "save_job_btn", "run_all_btn"):
        setattr(stub, name, _Btn(name))
    stub.export_excel_btn = _Btn("⇩  Export")
    stub.inspect_btn = _Btn("▦  Tables")
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
    stub.show_batch_summary = mock.Mock()
    stub.show_batch_error = mock.Mock()
    stub._current_profile_jobs = mock.Mock(return_value=[])
    stub.get_jobs_to_run = mock.Mock(return_value=[])
    return stub


def run_after_calls(stub):
    calls, stub.after_calls = stub.after_calls, []
    for fn in calls:
        fn()


class _SwapAfterFirstJob:
    """Wraps the real read/modify: after job 1 finishes, self.engine becomes B."""

    def __init__(self, stub, new_engine):
        self.stub = stub
        self.new_engine = new_engine
        self.engines_passed = []

    def _after(self):
        if len(self.engines_passed) == 1:
            self.stub.engine = self.new_engine
            self.stub._run_target = app.RunTarget(self.new_engine, None)

    def read(self, sql, engine=None):
        self.engines_passed.append(engine)
        try:
            return GUI.read_sql_dataframe(self.stub, sql, engine=engine)
        finally:
            self._after()

    def modify(self, sql, engine=None):
        self.engines_passed.append(engine)
        try:
            return GUI._execute_modification(self.stub, sql, engine=engine)
        finally:
            self._after()

    def install(self):
        self.stub.read_sql_dataframe = self.read
        self.stub._execute_modification = self.modify


class RunAllEngineTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.a = make_db(self, tmp.name, "a", "from_A")
        self.b = make_db(self, tmp.name, "b", "from_B")
        sleep = mock.patch("time.sleep")
        sleep.start()
        self.addCleanup(sleep.stop)

    def _run(self, jobs, *, override: bool, info=None):
        stub = make_stub(self.a, info)
        if not override:
            stub.get_jobs_to_run.return_value = jobs
            stub._current_profile_jobs.return_value = jobs
        swap = _SwapAfterFirstJob(stub, self.b)
        swap.install()
        threads = _ThreadCapture()
        with mock.patch.object(app.threading, "Thread", side_effect=threads), \
                mock.patch.object(app, "messagebox") as mb:
            if override:
                stub.run_selected_job(jobs_override=jobs)
            else:
                stub.run_selected_job()
            self.assertEqual(len(threads.targets), 1)
            threads.run_all()
            run_after_calls(stub)
        mb.showerror.assert_not_called()
        stub.show_batch_error.assert_not_called()
        return stub, swap

    def _results(self, stub):
        stub.show_batch_summary.assert_called_once()
        success, errors, job_results, total = stub.show_batch_summary.call_args.args
        return success, errors, job_results, total

    def test_run_all_second_job_stays_on_a(self):
        jobs = [{"name": "J1", "query": "SELECT a FROM t"},
                {"name": "J2", "query": "SELECT a FROM t"}]
        stub, swap = self._run(jobs, override=False)
        self.assertIs(stub.engine, self.b)  # the swap really happened
        success, errors, job_results, total = self._results(stub)
        self.assertEqual((success, errors, total), (2, 0, 2))
        self.assertEqual([list(r["_data"]["a"]) for r in job_results],
                         [["from_A"], ["from_A"]])
        self.assertEqual(swap.engines_passed, [self.a, self.a])

    def test_run_group_override_second_job_stays_on_a(self):
        jobs = [{"name": "G1", "query": "SELECT a FROM t"},
                {"name": "G2", "query": "SELECT a FROM t"}]
        stub, swap = self._run(jobs, override=True)
        _s, _e, job_results, _t = self._results(stub)
        self.assertEqual([list(r["_data"]["a"]) for r in job_results],
                         [["from_A"], ["from_A"]])
        self.assertEqual(swap.engines_passed, [self.a, self.a])
        stub.get_jobs_to_run.assert_not_called()

    def test_dml_after_swap_changes_only_a(self):
        """C1 scenario: the UPDATE of job 2 must not reach the new connection B."""
        jobs = [{"name": "J1", "query": "SELECT a FROM t"},
                {"name": "J2", "query": "UPDATE t SET a = 'changed'"}]
        for override in (False, True):
            with self.subTest(override=override):
                stub, swap = self._run([dict(j) for j in jobs], override=override)
                success, errors, job_results, _t = self._results(stub)
                self.assertEqual((success, errors), (2, 0))
                self.assertEqual(job_results[1]["_data"], 1)
                self.assertEqual(values(self.a), ["changed"])
                self.assertEqual(values(self.b), ["from_B"])
                self.assertEqual(swap.engines_passed, [self.a, self.a])

    def test_dml_first_then_select_after_swap(self):
        jobs = [{"name": "J1", "query": "UPDATE t SET a = 'x1'"},
                {"name": "J2", "query": "SELECT a FROM t"}]
        stub, _swap = self._run(jobs, override=True)
        _s, _e, job_results, _t = self._results(stub)
        self.assertEqual(list(job_results[1]["_data"]["a"]), ["x1"])
        self.assertEqual(values(self.b), ["from_B"])

    def test_swap_before_worker_starts(self):
        stub = make_stub(self.a)
        jobs = [{"name": "J1", "query": "UPDATE t SET a = 'early'"}]
        threads = _ThreadCapture()
        with mock.patch.object(app.threading, "Thread", side_effect=threads):
            stub.run_selected_job(jobs_override=jobs)
        stub.engine = self.b
        threads.run_all()
        run_after_calls(stub)
        self.assertEqual(values(self.a), ["early"])
        self.assertEqual(values(self.b), ["from_B"])

    def test_same_target_to_confirm_and_start(self):
        ci = app.ConnectionInfo("P1", "SQLite", "u", "h", "", "")
        stub = make_stub(self.a, ci)
        with mock.patch.object(app.threading, "Thread"):
            stub.run_selected_job(jobs_override=[{"name": "J", "query": "SELECT a FROM t"}])
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
            stub.run_selected_job(jobs_override=[{"name": "J", "query": "SELECT 1"}])
        self.assertEqual(cap.call_count, 1)


class ExportEngineTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.folder = tmp.name
        self.a = make_db(self, tmp.name, "a", "from_A")
        self.b = make_db(self, tmp.name, "b", "from_B")

    def _export(self, stub, jobs, out):
        stub._reuse_last_run_results = mock.Mock(side_effect=lambda js: list(js))
        threads = _ThreadCapture()
        with mock.patch.object(app.threading, "Thread", side_effect=threads), \
                mock.patch.object(app, "filedialog") as fd, \
                mock.patch.object(app, "messagebox") as mb:
            fd.asksaveasfilename.return_value = out
            stub.export_jobs_to_excel(jobs_override=jobs)
            self.assertEqual(len(threads.targets), 1)
            return threads, mb

    def _cells(self, path):
        import openpyxl

        wb = openpyxl.load_workbook(path)
        try:
            return [c for ws in wb.worksheets for row in ws.iter_rows(values_only=True)
                    for c in row]
        finally:
            wb.close()

    def test_export_reads_from_start_engine(self):
        out = os.path.join(self.folder, "out.xlsx")
        stub = make_stub(self.a)
        jobs = [{"name": "J1", "query": "SELECT a FROM t"},
                {"name": "J2", "query": "SELECT a FROM t"}]
        threads, mb = self._export(stub, jobs, out)
        stub.engine = self.b  # swap before the worker runs
        stub._run_target = app.RunTarget(self.b, None)
        with mock.patch.object(app, "messagebox") as mb2:
            threads.run_all()
            run_after_calls(stub)
        mb2.showerror.assert_not_called()
        mb2.showinfo.assert_called_once()
        cells = self._cells(out)
        self.assertEqual(cells.count("from_A"), 2)
        self.assertNotIn("from_B", cells)

    def test_export_worker_never_reads_self_engine(self):
        out = os.path.join(self.folder, "out2.xlsx")
        stub = make_stub(self.a)
        threads, _ = self._export(stub, [{"name": "J1", "query": "SELECT a FROM t"}], out)
        poisoned = mock.Mock(name="B")
        poisoned.raw_connection.side_effect = AssertionError("worker read self.engine")
        stub.engine = poisoned
        with mock.patch.object(app, "messagebox") as mb:
            threads.run_all()
            run_after_calls(stub)
        mb.showerror.assert_not_called()
        poisoned.raw_connection.assert_not_called()
        self.assertIn("from_A", self._cells(out))

    def test_start_gets_captured_target(self):
        ci = app.ConnectionInfo("P1", "SQLite", "u", "h", "", "")
        stub = make_stub(self.a, ci)
        self._export(stub, [{"name": "J", "query": "SELECT a FROM t"}],
                     os.path.join(self.folder, "x.xlsx"))
        target = stub._start_stoppable_run.call_args.kwargs["target"]
        self.assertIs(target, stub._run_target)
        self.assertIs(target.engine, self.a)


class ListTablesEngineTests(unittest.TestCase):
    def _start(self, stub):
        threads = _ThreadCapture()
        stub._stop_buttons = []  # T13: the Loading window registers a Stop button
        with mock.patch.object(app.threading, "Thread", side_effect=threads), \
                mock.patch.object(app.tk, "Toplevel"), \
                mock.patch.object(app, "ttk"), \
                mock.patch.object(app, "ui_rbutton"), \
                mock.patch.object(app, "messagebox"):
            stub.list_tables()
        self.assertEqual(len(threads.targets), 1)
        return threads

    def _finish(self, stub, threads):
        stub.on_list_tables_success = mock.Mock()
        stub.on_list_tables_error = mock.Mock()
        with mock.patch("builtins.print"), mock.patch("traceback.print_exc"):
            threads.run_all()
        run_after_calls(stub)
        stub.on_list_tables_error.assert_not_called()
        stub.on_list_tables_success.assert_called_once()
        return stub.on_list_tables_success.call_args.args[0]

    def test_current_db_inspects_start_engine(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        a = make_db(self, tmp.name, "a", "x", table="only_in_a")
        b = make_db(self, tmp.name, "b", "x", table="only_in_b")
        stub = make_stub(a)
        stub.db_name.set("main_db")
        threads = self._start(stub)
        stub.engine = b
        stub._run_target = app.RunTarget(b, None)
        tables = self._finish(stub, threads)
        names = {t["Table"] for t in tables}
        self.assertIn("only_in_a", names)
        self.assertNotIn("only_in_b", names)

    def _fake_engine(self, rows):
        engine = mock.MagicMock(name="A")
        conn = mock.MagicMock(name="conn")
        engine.connect.return_value.__enter__.return_value = conn
        conn.execute.return_value = rows
        return engine, conn

    def test_db_type_from_info_and_inspect_gets_a(self):
        engine_a, conn = self._fake_engine([("SCOTT",)])
        ci = app.ConnectionInfo("P1", "Oracle", "u", "h", "1521", "")
        stub = make_stub(engine_a, ci)
        stub.db_type.set("Oracle")
        threads = self._start(stub)
        # after start: reconnect elsewhere and change the screen field
        engine_b = mock.Mock(name="B")
        engine_b.connect.side_effect = AssertionError("worker used self.engine")
        stub.engine = engine_b
        stub._run_target = app.RunTarget(engine_b, None)
        stub.db_type.set("MySQL")  # would take the temp_engine path if read now
        inspector = mock.Mock()
        inspector.get_table_names.return_value = ["EMP"]
        with mock.patch.object(app, "inspect", return_value=inspector) as insp, \
                mock.patch.object(app, "create_engine") as ce:
            tables = self._finish(stub, threads)
        ce.assert_not_called()
        insp.assert_called_once_with(engine_a)
        engine_b.connect.assert_not_called()
        sql = str(conn.execute.call_args.args[0])
        self.assertIn("all_users", sql)  # Oracle query: db_type came from info
        self.assertEqual(tables, [{"Database": "SCOTT", "Schema": "SCOTT", "Table": "EMP"}])

    def test_info_db_type_wins_over_screen_at_start(self):
        engine_a, conn = self._fake_engine([])
        ci = app.ConnectionInfo("P1", "PostgreSQL", "u", "h", "5432", "")
        stub = make_stub(engine_a, ci)
        stub.db_type.set("MySQL")  # screen already differs when Tables is clicked
        stub._replace_engine(engine_a, ci, password="pw")  # same engine: no dispose
        threads = self._start(stub)
        self._finish(stub, threads)
        self.assertIn("pg_database", str(conn.execute.call_args.args[0]))

    def test_no_info_reads_db_type_before_thread_starts(self):
        engine_a, conn = self._fake_engine([])
        stub = make_stub(engine_a)  # engine set directly: RunTarget(engine, None)
        stub.db_type.set("PostgreSQL")
        threads = self._start(stub)
        stub.db_type.set("MySQL")  # changed after start, before the worker runs
        stub.engine = mock.Mock(name="B")
        self._finish(stub, threads)
        self.assertIn("pg_database", str(conn.execute.call_args.args[0]))
        engine_a.connect.assert_called_once()


if __name__ == "__main__":
    unittest.main()
