"""Focused QA for the Round 4 Profile mismatch guard (R4-AC-1 to R4-AC-5)."""

import os
import sys
import threading
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import database_connect_gui as app  # noqa: E402

GUI = app.DatabaseConnectorGUI


class _FakeEntry:
    def __init__(self, value=""):
        self.value = value
        self.calls = []

    def get(self, *_args):
        return self.value

    def set(self, value):
        self.calls.append(value)
        self.value = value

    def delete(self, *_args):
        self.value = ""

    def insert(self, _index, value):
        self.value = value


class _FakeButton:
    def __init__(self, text="", state="normal"):
        self.text = text
        self.state = state
        self.config_calls = []

    def cget(self, key):
        return self.text if key == "text" else self.state

    def config(self, **kwargs):
        self.config_calls.append(kwargs)
        self.text = kwargs.get("text", self.text)
        self.state = kwargs.get("state", self.state)

    configure = config


class _FakeText:
    def __init__(self, value=""):
        self.value = value
        self.inserted = []
        self.deleted = []
        self.seen = []

    def insert(self, _index, value):
        self.inserted.append(value)

    def delete(self, *args):
        self.deleted.append(args)

    def see(self, index):
        self.seen.append(index)

    def get(self, *_args):
        return self.value


def make_stub(*, selected="Profile B", connected="Profile A", with_info=True):
    stub = GUI.__new__(GUI)
    stub.profile_combo = _FakeEntry(selected)
    stub.results_text = _FakeText()
    stub.sql_context = _FakeText("SELECT 1")
    stub.db_type = _FakeEntry("PostgreSQL")
    stub.db_user = _FakeEntry("user")
    stub.db_password = _FakeEntry("password")
    stub.db_host = _FakeEntry("localhost")
    stub.db_port = _FakeEntry("5432")
    stub.db_name = _FakeEntry("db")
    stub.execute_btn = _FakeButton("Run")
    stub.inspect_btn = _FakeButton("Tables")
    stub.export_excel_btn = _FakeButton("Export Excel")
    stub.status_label = _FakeButton()
    stub.root = mock.Mock(name="root")
    stub._active_db_lock = threading.Lock()
    stub._active_db_connections = {}
    stub._running_job_ids = set()
    stub._batch_running = False
    stub._block_if_busy = mock.Mock(return_value=False)

    engine = mock.Mock(name="engine_A")
    info = app.ConnectionInfo(
        profile=connected,
        db_type="PostgreSQL",
        user="user",
        host="localhost",
        port="5432",
        database="db",
    ) if with_info else None
    target = app.RunTarget(engine, info)
    stub.engine = engine
    stub._run_target = target
    stub.saved_jobs = []
    stub._prepare_run_sql = mock.Mock(side_effect=lambda jobs: [job["query"] for job in jobs])
    stub._confirm_data_change = mock.Mock(return_value=False)
    stub._start_stoppable_run = mock.Mock()
    stub._create_loading_dialog_with_retry = mock.Mock(return_value=mock.Mock())
    stub._execute_query_background = mock.Mock()
    stub._create_list_tables_loading_dialog = mock.Mock(return_value=mock.Mock())
    stub.read_sql_dataframe = mock.Mock()
    stub.get_jobs_to_run = mock.Mock(return_value=[])
    stub._current_profile_jobs = mock.Mock(return_value=[])
    stub._start_job_result_report = mock.Mock()
    stub._clear_results_grid = mock.Mock()
    stub.update_job_status = mock.Mock()
    stub.run_all_btn = _FakeButton()
    stub.save_job_btn = _FakeButton()
    return stub


def entry_calls(stub):
    job = {
        "name": "Daily",
        "query": "SELECT 1",
        "profile": stub.profile_combo.get(),
    }
    stub.saved_jobs = [job]
    return {
        "run_job": lambda: stub.run_job(job),
        "run_selected_job": lambda: stub.run_selected_job(jobs_override=[dict(job)]),
        "export_jobs_to_excel": lambda: stub.export_jobs_to_excel(
            jobs_override=[job], file_prefix="Group"
        ),
        "execute_query": lambda: stub.execute_query(),
        "list_tables": lambda: stub.list_tables(),
    }


class ProfileMismatchEntryPointTests(unittest.TestCase):
    def test_all_five_entry_points_refuse_mismatch_without_side_effects(self):
        for name in (
            "run_job",
            "run_selected_job",
            "export_jobs_to_excel",
            "execute_query",
            "list_tables",
        ):
            with self.subTest(entry_point=name):
                stub = make_stub()
                engine = stub.engine
                target = stub._run_target
                selected_before = stub.profile_combo.get()

                with mock.patch.object(app.threading, "Thread") as thread, \
                        mock.patch.object(app, "messagebox") as messagebox, \
                        mock.patch.object(app, "filedialog") as filedialog, \
                        mock.patch.object(app, "ui_dialog") as ui_dialog:
                    entry_calls(stub)[name]()

                self.assertEqual(len(stub.results_text.inserted), 1)
                log = stub.results_text.inserted[0]
                self.assertIn("Profile B", log)
                self.assertIn("Profile A", log)
                self.assertIn("ไม่ได้เริ่มงาน", log)
                self.assertTrue(log.endswith("\n"))
                self.assertEqual(stub.results_text.seen, [app.tk.END])
                self.assertEqual(stub.profile_combo.get(), selected_before)
                self.assertEqual(stub.profile_combo.calls, [])
                self.assertIs(stub.engine, engine)
                self.assertIs(stub._run_target, target)
                self.assertIs(stub._run_target.engine, engine)

                stub._prepare_run_sql.assert_not_called()
                stub._confirm_data_change.assert_not_called()
                stub._start_stoppable_run.assert_not_called()
                stub._execute_query_background.assert_not_called()
                stub._create_loading_dialog_with_retry.assert_not_called()
                stub._create_list_tables_loading_dialog.assert_not_called()
                stub.read_sql_dataframe.assert_not_called()
                thread.assert_not_called()
                filedialog.assert_not_called()
                ui_dialog.assert_not_called()
                messagebox.assert_not_called()

    def test_mismatch_guard_does_not_block_when_profile_cannot_be_compared(self):
        cases = (
            (make_stub(selected="Profile B", with_info=False), "no snapshot info"),
            (make_stub(selected="", connected="Profile A"), "empty selected profile"),
            (make_stub(selected="Profile B", connected=""), "empty connected profile"),
            (make_stub(selected="  Profile A  ", connected="Profile A"), "trimmed match"),
        )
        for stub, label in cases:
            with self.subTest(case=label):
                target = stub._capture_run_target()
                self.assertFalse(stub._block_if_profile_mismatch("Run", target=target))
                self.assertEqual(stub.results_text.inserted, [])

    def test_missing_snapshot_keeps_run_job_flow_available(self):
        stub = make_stub(selected="Profile B", with_info=False)
        job = {"name": "Daily", "query": "SELECT 1", "profile": "Profile B"}
        stub.saved_jobs = [job]

        with mock.patch.object(app.threading, "Thread") as thread:
            stub.run_job(job)

        self.assertEqual(stub.results_text.inserted, [])
        stub._prepare_run_sql.assert_called_once_with([job])
        stub._confirm_data_change.assert_called_once()
        target = stub._confirm_data_change.call_args.kwargs["target"]
        self.assertIs(target.engine, stub.engine)
        self.assertIsNone(target.info)
        thread.assert_not_called()  # confirmation stub deliberately cancels

    def test_matching_profile_reaches_each_entry_point(self):
        for name in (
            "run_job",
            "run_selected_job",
            "export_jobs_to_excel",
            "execute_query",
            "list_tables",
        ):
            with self.subTest(entry_point=name):
                stub = make_stub(selected="Profile A", connected="Profile A")
                with mock.patch.object(app.threading, "Thread") as thread, \
                        mock.patch.object(app, "messagebox") as messagebox, \
                        mock.patch.object(app, "filedialog") as filedialog, \
                        mock.patch.object(app, "ui_dialog"):
                    filedialog.asksaveasfilename.return_value = ""
                    entry_calls(stub)[name]()

                self.assertFalse(
                    any("ไม่ได้เริ่มงาน" in line for line in stub.results_text.inserted)
                )
                if name in ("run_job", "run_selected_job", "execute_query"):
                    stub._prepare_run_sql.assert_called_once()
                    stub._confirm_data_change.assert_called_once()
                    target = stub._confirm_data_change.call_args.kwargs["target"]
                    self.assertIs(target.engine, stub.engine)
                elif name == "export_jobs_to_excel":
                    filedialog.asksaveasfilename.assert_called_once()
                else:
                    stub._create_list_tables_loading_dialog.assert_called_once()
                    thread.assert_called_once()
                self.assertEqual(stub.profile_combo.get(), "Profile A")
                messagebox.assert_not_called()

    def test_connecting_selected_profile_replaces_engine_and_snapshot(self):
        from sqlalchemy import create_engine as real_create_engine

        stub = make_stub(selected="Profile B", connected="Profile A")
        old_engine = stub.engine
        new_engine = real_create_engine("sqlite://")
        self.addCleanup(new_engine.dispose)
        stub._track_engine_connections = mock.Mock()

        with mock.patch.object(app, "create_engine", return_value=new_engine), \
                mock.patch.object(app, "messagebox") as messagebox:
            stub.connect_database()

        self.assertIs(stub.engine, new_engine)
        self.assertIsInstance(stub._run_target, app.RunTarget)
        self.assertIs(stub._run_target.engine, new_engine)
        self.assertEqual(stub._run_target.info.profile, "Profile B")
        old_engine.dispose.assert_called_once_with()

        job = {"name": "Daily", "query": "SELECT 1", "profile": "Profile B"}
        stub.saved_jobs = [job]
        stub._prepare_run_sql.reset_mock()
        stub._confirm_data_change.reset_mock()
        stub.run_job(job)

        stub._prepare_run_sql.assert_called_once_with([job])
        target = stub._confirm_data_change.call_args.kwargs["target"]
        self.assertIs(target.engine, new_engine)
        self.assertEqual(target.info.profile, "Profile B")
        messagebox.showerror.assert_not_called()
        self.assertFalse(any("ไม่ได้เริ่มงาน" in line for line in stub.results_text.inserted))


if __name__ == "__main__":
    unittest.main()
