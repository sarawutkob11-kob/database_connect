"""R5-T1: keep the jobs list and single-job execution aligned with Profile."""

import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import database_connect_gui as app  # noqa: E402

GUI = app.DatabaseConnectorGUI


class _FakeWidget:
    def __init__(self, value="", command=None):
        self.value = value
        self.command = command
        self.destroyed = False

    def __getattr__(self, name):
        if name.startswith("winfo_"):
            return lambda *_args, **_kwargs: 800
        return lambda *_args, **_kwargs: self

    def get(self, *_args):
        return self.value

    def insert(self, _index, value):
        self.value = value

    def delete(self, *_args):
        self.value = ""

    def destroy(self):
        self.destroyed = True


class _FakeCombo:
    def __init__(self, value, values):
        self.value = value
        self.values = values
        self.calls = []

    def get(self):
        return self.value

    def current(self, index):
        self.calls.append(index)
        self.value = self.values[index]


class _FakeText:
    def __init__(self):
        self.inserted = []
        self.seen = []

    def insert(self, _index, value):
        self.inserted.append(value)

    def see(self, index):
        self.seen.append(index)


def make_profile_save_stub():
    stub = GUI.__new__(GUI)
    stub._block_if_busy = mock.Mock(return_value=False)
    stub.saved_profiles = {"P1": {}, "P2": {}}
    stub.profile_combo = _FakeCombo("P1", list(stub.saved_profiles))
    stub.db_type = mock.Mock(get=mock.Mock(return_value="PostgreSQL"))
    stub.db_user = mock.Mock(get=mock.Mock(return_value="user"))
    stub.db_password = mock.Mock(get=mock.Mock(return_value=""))
    stub.db_host = mock.Mock(get=mock.Mock(return_value="localhost"))
    stub.db_port = mock.Mock(get=mock.Mock(return_value="5432"))
    stub.db_name = mock.Mock(get=mock.Mock(return_value="db"))
    stub.sql_context = mock.Mock(get=mock.Mock(return_value="SELECT 1"))
    stub.results_text = _FakeText()
    stub.root = _FakeWidget()
    stub.save_profiles = mock.Mock(return_value=True)
    stub.save_last_used_profile = mock.Mock()
    return stub


class ProfileSaveRefreshTests(unittest.TestCase):
    def test_success_refreshes_jobs_after_selecting_saved_profile(self):
        stub = make_profile_save_stub()
        event_order = []
        stub.update_profile_list = mock.Mock()

        def current(index):
            stub.profile_combo.calls.append(index)
            stub.profile_combo.value = stub.profile_combo.values[index]
            event_order.append(("current", stub.profile_combo.get()))

        stub.profile_combo.current = current

        def update_jobs_list():
            event_order.append(("update_jobs_list", stub.profile_combo.get()))

        stub.update_jobs_list = mock.Mock(side_effect=update_jobs_list)
        entries = []
        buttons = []
        dialog = _FakeWidget()

        def entry_factory(*_args, **_kwargs):
            entry = _FakeWidget()
            entries.append(entry)
            return entry

        def button_factory(*_args, **kwargs):
            button = _FakeWidget(command=kwargs.get("command"))
            buttons.append(button)
            return button

        with mock.patch.object(app.tk, "Toplevel", return_value=dialog), \
            mock.patch.object(app.ttk, "Frame", side_effect=lambda *_a, **_k: _FakeWidget()), \
                mock.patch.object(app.ttk, "Label", side_effect=lambda *_a, **_k: _FakeWidget()), \
                mock.patch.object(app.ttk, "Entry", side_effect=entry_factory), \
                mock.patch.object(app.ttk, "Button", side_effect=button_factory), \
                mock.patch.object(app, "messagebox") as messagebox:
            stub.save_profile_dialog()
            entries[0].value = "P2"
            save_button = next(button for button in buttons if button.command is not None)
            save_button.command()

        self.assertEqual(stub.profile_combo.get(), "P2")
        self.assertEqual(event_order, [("current", "P2"), ("update_jobs_list", "P2")])
        stub.update_jobs_list.assert_called_once_with()
        stub.save_profiles.assert_called_once()
        messagebox.showinfo.assert_called_once()
        self.assertTrue(dialog.destroyed)


class RunJobProfileTests(unittest.TestCase):
    def make_stub(self, selected="P1", connected="P1"):
        stub = GUI.__new__(GUI)
        stub._block_if_busy = mock.Mock(return_value=False)
        stub._running_job_ids = set()
        stub.profile_combo = mock.Mock(get=mock.Mock(return_value=selected))
        stub.results_text = _FakeText()
        stub.engine = mock.Mock(name="engine")
        info = app.ConnectionInfo(connected, "PostgreSQL", "user", "host", "5432", "db")
        stub._run_target = app.RunTarget(stub.engine, info)
        stub._prepare_run_sql = mock.Mock(side_effect=lambda jobs: [job["query"] for job in jobs])
        stub._confirm_data_change = mock.Mock(return_value=False)
        stub._start_stoppable_run = mock.Mock()
        return stub

    def test_mismatched_job_profile_logs_and_returns_before_confirmation_or_thread(self):
        stub = self.make_stub(selected="P2", connected="P2")
        job = {"name": "Daily", "query": "SELECT 1", "profile": "P1"}

        with mock.patch.object(app.threading, "Thread") as thread, \
                mock.patch.object(app, "messagebox") as messagebox:
            result = stub.run_job(job)

        self.assertIsNone(result)
        self.assertEqual(len(stub.results_text.inserted), 1)
        log = stub.results_text.inserted[0]
        self.assertIn("ไม่ได้เริ่มงาน", log)
        self.assertIn("P1", log)
        self.assertIn("P2", log)
        self.assertTrue(log.endswith("\n"))
        self.assertEqual(stub.results_text.seen, [app.tk.END])
        stub._prepare_run_sql.assert_not_called()
        stub._confirm_data_change.assert_not_called()
        stub._start_stoppable_run.assert_not_called()
        self.assertEqual(stub._running_job_ids, set())
        thread.assert_not_called()
        messagebox.assert_not_called()

    def test_matching_job_profile_reaches_existing_confirmation_flow(self):
        stub = self.make_stub()
        job = {"name": "Daily", "query": "SELECT 1", "profile": "P1"}

        with mock.patch.object(app.threading, "Thread") as thread:
            stub.run_job(job)

        self.assertEqual(stub.results_text.inserted, [])
        stub._prepare_run_sql.assert_called_once_with([job])
        stub._confirm_data_change.assert_called_once()
        stub._start_stoppable_run.assert_not_called()
        thread.assert_not_called()  # confirmation stub simulates Cancel


if __name__ == "__main__":
    unittest.main()