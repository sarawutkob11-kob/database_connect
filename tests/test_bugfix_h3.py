"""R5-T1: profile save results roll back callers when persistence fails."""

import copy
import json
import os
import sys
import tempfile
import threading
import unittest
from contextlib import ExitStack, contextmanager
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import database_connect_gui as app  # noqa: E402


class _FakeWidget:
    def __init__(self, **kwargs):
        self.value = kwargs.get("value", "")
        self.text = kwargs.get("text", "")
        self.command = kwargs.get("command")
        self.calls = []
        self.inserted = []
        self.destroyed = False

    def __getattr__(self, name):
        if name.startswith("winfo_"):
            return lambda *args, **kwargs: 800
        return lambda *args, **kwargs: self

    def get(self, *_args):
        return self.value

    def set(self, value):
        self.value = value

    def trace_add(self, *_args):
        return None

    def insert(self, _index, value):
        self.inserted.append(value)
        self.value = value

    def delete(self, *_args):
        self.value = ""

    def current(self, *args):
        self.calls.append(("current",) + args)

    def config(self, **kwargs):
        self.calls.append(("config", kwargs))

    configure = config

    def cget(self, key):
        return self.text if key == "text" else self.value

    def destroy(self):
        self.destroyed = True


class _FakeVariable:
    def __init__(self, value=None, **_kwargs):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value

    def trace_add(self, *_args):
        return None


class _FakeListbox(_FakeWidget):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.items = []

    def insert(self, _index, value):
        self.items.append(value)

    def size(self):
        return len(self.items)

    def curselection(self):
        return (0,) if self.items else ()


@contextmanager
def fake_dialog_widgets():
    captures = {
        "entries": [], "tk_buttons": [], "ttk_buttons": [], "ui_buttons": [], "variables": [],
        "listboxes": [], "text_widgets": [], "toplevels": [],
    }

    def widget_factory(*_args, **kwargs):
        return _FakeWidget(**kwargs)

    def entry_factory(*_args, **kwargs):
        widget = _FakeWidget(**kwargs)
        captures["entries"].append(widget)
        return widget

    def listbox_factory(*_args, **kwargs):
        widget = _FakeListbox(**kwargs)
        captures["listboxes"].append(widget)
        return widget

    def text_factory(*_args, **kwargs):
        widget = _FakeWidget(**kwargs)
        captures["text_widgets"].append(widget)
        return widget

    def toplevel_factory(*_args, **kwargs):
        widget = _FakeWidget(**kwargs)
        captures["toplevels"].append(widget)
        return widget

    def tk_button_factory(*_args, **kwargs):
        widget = _FakeWidget(**kwargs)
        captures["tk_buttons"].append(widget)
        return widget

    def ttk_button_factory(*_args, **kwargs):
        widget = _FakeWidget(**kwargs)
        captures["ttk_buttons"].append(widget)
        return widget

    def variable_factory(*_args, **kwargs):
        variable = _FakeVariable(**kwargs)
        captures["variables"].append(variable)
        return variable

    with ExitStack() as stack:
        for name in ("Frame", "Canvas", "Label", "LabelFrame", "Scrollbar", "Radiobutton"):
            stack.enter_context(mock.patch.object(app.tk, name, side_effect=widget_factory))
        stack.enter_context(mock.patch.object(app.tk, "Toplevel", side_effect=toplevel_factory))
        stack.enter_context(mock.patch.object(app.tk, "Listbox", side_effect=listbox_factory))
        stack.enter_context(mock.patch.object(app.tk, "Text", side_effect=text_factory))
        stack.enter_context(mock.patch.object(app.tk, "Button", side_effect=tk_button_factory))
        stack.enter_context(mock.patch.object(app.tk, "Entry", side_effect=entry_factory))
        stack.enter_context(mock.patch.object(app.tk, "StringVar", side_effect=variable_factory))
        stack.enter_context(mock.patch.object(app.tk, "BooleanVar", side_effect=variable_factory))
        stack.enter_context(mock.patch.object(app.ttk, "Entry", side_effect=entry_factory))
        stack.enter_context(mock.patch.object(app.ttk, "Button", side_effect=ttk_button_factory))
        for name in ("Label", "Frame", "LabelFrame", "Scrollbar"):
            stack.enter_context(mock.patch.object(app.ttk, name, side_effect=widget_factory))
        yield captures


def make_stub(profiles=None):
    stub = app.DatabaseConnectorGUI.__new__(app.DatabaseConnectorGUI)
    stub._active_db_lock = threading.Lock()
    stub._active_db_connections = {}
    stub._running_job_ids = set()
    stub._block_if_busy = mock.Mock(return_value=False)
    stub.execute_btn = _FakeWidget(text="Run")
    stub.inspect_btn = _FakeWidget(text="Tables")
    stub.saved_profiles = copy.deepcopy(profiles if profiles is not None else {
        "P1": {"db_type": "Oracle", "db_host": "old-host", "nested": {"keep": True}},
        "P2": {"db_type": "MySQL", "db_host": "other-host"},
    })
    stub.profile_combo = _FakeWidget(value="P1")
    stub.db_type = _FakeVariable("Oracle")
    stub.db_user = _FakeVariable("user")
    stub.db_password = _FakeVariable("secret")
    stub.db_host = _FakeVariable("new-host")
    stub.db_port = _FakeWidget(value="1521:extra")
    stub.db_name = _FakeVariable("SERVICE")
    stub.sql_context = _FakeWidget(value="SELECT 1")
    stub.results_text = _FakeWidget()
    stub.root = _FakeWidget()
    stub.DEFAULT_SQL_QUERY = "SELECT 1"
    return stub


def assert_no_success(test, stub, messagebox):
    test.assertEqual(stub.results_text.inserted, [])
    messagebox.showinfo.assert_not_called()


class SaveProfilesResultTests(unittest.TestCase):
    def test_save_profiles_returns_true_after_atomic_write(self):
        with tempfile.TemporaryDirectory() as folder:
            stub = make_stub()
            stub.config_file = os.path.join(folder, "db_profiles.json")
            stub.get_last_used_profile = mock.Mock(return_value="P1")
            with mock.patch.object(app, "messagebox") as messagebox:
                result = stub.save_profiles()
            self.assertIs(result, True)
            with open(stub.config_file, encoding="utf-8") as profile_file:
                self.assertEqual(json.load(profile_file)["P1"]["db_host"], "old-host")
            messagebox.showerror.assert_not_called()

    def test_save_profiles_returns_false_when_write_raises(self):
        stub = make_stub()
        stub.config_file = "unused.json"
        stub.get_last_used_profile = mock.Mock(return_value=None)
        with mock.patch.object(app, "write_json_atomic", side_effect=OSError("locked")), \
                mock.patch.object(app, "messagebox") as messagebox:
            result = stub.save_profiles()
        self.assertIs(result, False)
        messagebox.showerror.assert_called_once()

    def test_save_profiles_returns_false_when_save_is_blocked(self):
        stub = make_stub()
        stub._profiles_save_blocked = True
        stub.config_file = "unused.json"
        with mock.patch.object(app, "write_json_atomic") as write_json, \
                mock.patch.object(app, "messagebox"):
            result = stub.save_profiles()
        self.assertIs(result, False)
        write_json.assert_not_called()


class SaveProfileDialogFailureTests(unittest.TestCase):
    def test_overwrite_failure_restores_profiles_and_leaves_port_and_ui_unchanged(self):
        stub = make_stub()
        before = copy.deepcopy(stub.saved_profiles)
        stub.save_profiles = mock.Mock(return_value=False)
        stub.save_last_used_profile = mock.Mock()
        stub.update_profile_list = mock.Mock()
        with fake_dialog_widgets() as widgets, \
                mock.patch.object(app, "messagebox") as messagebox:
            stub.save_profile_dialog()
            widgets["entries"][0].value = "P1"
            save_button = next(button for button in widgets["ttk_buttons"]
                               if button.command is not None)
            save_button.command()

        self.assertEqual(stub.saved_profiles, before)
        self.assertEqual(stub.db_port.get(), "1521:extra")
        stub.save_last_used_profile.assert_not_called()
        stub.update_profile_list.assert_not_called()
        self.assertEqual(stub.profile_combo.calls, [])
        self.assertFalse(hasattr(stub, "_active_profile"))
        assert_no_success(self, stub, messagebox)


class NewProfileDialogFailureTests(unittest.TestCase):
    def test_create_failure_rolls_back_without_switching_or_success_output(self):
        stub = make_stub()
        before = copy.deepcopy(stub.saved_profiles)
        stub.save_profiles = mock.Mock(return_value=False)
        stub.save_last_used_profile = mock.Mock()
        stub.update_profile_list = mock.Mock()
        stub.load_profile_data = mock.Mock()

        def fake_ui_button(_parent, text, command, **_kwargs):
            button = _FakeWidget(text=text, command=command)
            widgets["ui_buttons"].append(button)
            return _FakeWidget(), button

        with fake_dialog_widgets() as widgets, \
                mock.patch.object(app, "ui_round_frame", return_value=(_FakeWidget(), _FakeWidget())), \
            mock.patch.object(app, "ui_round_frame_set"), \
            mock.patch.object(app, "ui_button", side_effect=fake_ui_button), \
                mock.patch.object(app, "messagebox") as messagebox:
            stub._create_centered_dialog = mock.Mock(return_value=_FakeWidget())
            stub.new_profile_dialog()
            entries = widgets["entries"]
            entries[0].value = "P3"
            entries[1].value = "new-host"
            entries[2].value = "1521:extra"
            entries[3].value = "SERVICE"
            entries[4].value = "user"
            entries[5].value = "secret"
            create_button = next(button for button in widgets["ui_buttons"]
                                 if button.text == "＋  สร้าง Profile")
            create_button.command()

        self.assertEqual(stub.saved_profiles, before)
        stub.save_last_used_profile.assert_not_called()
        stub.update_profile_list.assert_not_called()
        stub.load_profile_data.assert_not_called()
        self.assertEqual(stub.profile_combo.calls, [])
        assert_no_success(self, stub, messagebox)


class DeleteProfileFailureTests(unittest.TestCase):
    def test_delete_failure_restores_profiles_without_refresh_or_success(self):
        stub = make_stub()
        before = copy.deepcopy(stub.saved_profiles)
        stub.save_profiles = mock.Mock(return_value=False)
        stub.update_profile_list = mock.Mock()
        with mock.patch.object(app, "messagebox") as messagebox:
            messagebox.askyesno.return_value = True
            stub.delete_profile()

        self.assertEqual(stub.saved_profiles, before)
        stub.update_profile_list.assert_not_called()
        assert_no_success(self, stub, messagebox)


class ImportProfileFailureTests(unittest.TestCase):
    def _run_import_failure(self, merge_mode):
        stub = make_stub()
        before = copy.deepcopy(stub.saved_profiles)
        stub.save_profiles = mock.Mock(return_value=False)
        stub.update_profile_list = mock.Mock()
        stub.load_profile_data = mock.Mock()
        imported = {
            "P1": {"db_type": "PostgreSQL", "db_host": "imported-host"},
            "P3": {"db_type": "Oracle", "db_host": "new-host"},
        }
        with fake_dialog_widgets() as widgets, \
                mock.patch.object(app, "messagebox") as messagebox:
            dialog = _FakeWidget()
            stub._show_import_preview_dialog(imported, "profiles.json", "today", 2)
            widgets["variables"][0].set(merge_mode)
            import_button = widgets["tk_buttons"][0]
            import_button.command()

        return stub, before, dialog, messagebox

    def test_merge_failure_restores_full_profile_mapping_without_success(self):
        stub, before, _dialog, messagebox = self._run_import_failure(True)
        self.assertEqual(stub.saved_profiles, before)
        stub.update_profile_list.assert_not_called()
        stub.load_profile_data.assert_not_called()
        self.assertEqual(stub.profile_combo.calls, [])
        assert_no_success(self, stub, messagebox)

    def test_replace_failure_restores_full_profile_mapping_without_success(self):
        stub, before, _dialog, messagebox = self._run_import_failure(False)
        self.assertEqual(stub.saved_profiles, before)
        stub.update_profile_list.assert_not_called()
        stub.load_profile_data.assert_not_called()
        self.assertEqual(stub.profile_combo.calls, [])
        assert_no_success(self, stub, messagebox)
        messagebox.askyesno.assert_called_once()


class SaveJobsResultTests(unittest.TestCase):
    def test_save_jobs_returns_true_after_atomic_write(self):
        with tempfile.TemporaryDirectory() as folder:
            stub = make_stub()
            stub.jobs_file = os.path.join(folder, "saved_jobs.json")
            stub.saved_jobs = [{"name": "job", "query": "SELECT 1"}]

            with mock.patch.object(app, "messagebox") as messagebox:
                result = stub.save_jobs()

            self.assertIs(result, True)
            with open(stub.jobs_file, encoding="utf-8") as jobs_file:
                self.assertEqual(json.load(jobs_file), stub.saved_jobs)
            messagebox.showerror.assert_not_called()

    def test_save_jobs_returns_false_when_write_raises(self):
        stub = make_stub()
        stub.jobs_file = "unused.json"
        stub.saved_jobs = []

        with mock.patch.object(app, "write_json_atomic", side_effect=OSError("locked")), \
                mock.patch.object(app, "messagebox") as messagebox:
            result = stub.save_jobs()

        self.assertIs(result, False)
        messagebox.showerror.assert_called_once()

    def test_save_jobs_returns_false_when_save_is_blocked(self):
        stub = make_stub()
        stub._jobs_save_blocked = True
        stub.jobs_file = "unused.json"
        stub.saved_jobs = []

        with mock.patch.object(app, "write_json_atomic") as write_json, \
                mock.patch.object(app, "messagebox") as messagebox:
            result = stub.save_jobs()

        self.assertIs(result, False)
        write_json.assert_not_called()
        messagebox.showerror.assert_called_once()


def make_job_stub(jobs=None):
    stub = make_stub()
    stub.saved_jobs = jobs if jobs is not None else []
    stub.sql_context = _FakeWidget(value="SELECT 1 FROM source")
    stub.sql_template = None
    stub._excel_parameter_values = {}
    stub._excel_parameterized_sql = None
    stub._excel_state_for_job = mock.Mock(return_value={})
    stub._excel_state_from_job = mock.Mock(return_value=(None, {}, None))
    stub.update_jobs_list = mock.Mock()
    return stub


class SaveJobDialogTests(unittest.TestCase):
    def _invoke_save(self, stub, widgets):
        stub.save_job_dialog()
        widgets["entries"][0].value = "new job"
        save_button = next(button for button in widgets["tk_buttons"]
                           if button.command is not None)
        save_button.command()

    def test_save_failure_rolls_back_without_report_refresh_or_close(self):
        existing_job = {
            "name": "existing", "query": "SELECT 0", "metadata": {"tags": ["keep"]}
        }
        initial_jobs = [existing_job]
        stub = make_job_stub(initial_jobs)
        before = copy.deepcopy(initial_jobs)

        def fail_after_in_place_mutation():
            stub.saved_jobs[0]["metadata"]["tags"].append("write side effect")
            stub.saved_jobs[0]["metadata"]["changed"] = True
            stub.saved_jobs.append({"name": "temporary"})
            return False

        stub.save_jobs = mock.Mock(side_effect=fail_after_in_place_mutation)

        with fake_dialog_widgets() as widgets, \
                mock.patch.object(app, "messagebox") as messagebox:
            self._invoke_save(stub, widgets)

        self.assertIs(stub.saved_jobs, initial_jobs)
        self.assertIs(stub.saved_jobs[0], existing_job)
        self.assertEqual(stub.saved_jobs, before)
        stub.update_jobs_list.assert_not_called()
        self.assertEqual(stub.results_text.inserted, [])
        messagebox.showinfo.assert_not_called()
        self.assertFalse(widgets["toplevels"][0].destroyed)

    def test_save_success_keeps_job_and_reports_refresh(self):
        stub = make_job_stub()
        stub.save_jobs = mock.Mock(return_value=True)

        with fake_dialog_widgets() as widgets, \
                mock.patch.object(app, "messagebox") as messagebox:
            self._invoke_save(stub, widgets)

        self.assertEqual(len(stub.saved_jobs), 1)
        self.assertEqual(stub.saved_jobs[0]["name"], "new job")
        self.assertEqual(stub.saved_jobs[0]["query"], "SELECT 1 FROM source")
        stub.update_jobs_list.assert_called_once_with()
        self.assertTrue(any("Job saved: new job" in line for line in stub.results_text.inserted))
        messagebox.showinfo.assert_called_once()
        self.assertTrue(widgets["toplevels"][0].destroyed)


class EditJobSaveTests(unittest.TestCase):
    def _invoke_save(self, stub, widgets):
        stub.edit_job(0)
        widgets["entries"][0].value = "renamed job"
        widgets["text_widgets"][0].value = "UPDATE source SET value = 2"
        save_button = next(button for button in widgets["ttk_buttons"]
                           if button.text == "Save Changes")
        save_button.command()

    def test_edit_failure_restores_same_job_without_success_effects(self):
        original_job = {
            "name": "old job", "query": "SELECT 1", "profile": "P1",
            "metadata": {"tags": ["keep"]},
        }
        stub = make_job_stub([original_job])
        before = copy.deepcopy(original_job)

        def fail_after_in_place_mutation():
            original_job["metadata"]["tags"].append("write side effect")
            original_job["metadata"]["changed"] = True
            return False

        stub.save_jobs = mock.Mock(side_effect=fail_after_in_place_mutation)

        with fake_dialog_widgets() as widgets, \
                mock.patch.object(app, "messagebox") as messagebox:
            self._invoke_save(stub, widgets)

        self.assertIs(stub.saved_jobs[0], original_job)
        self.assertEqual(original_job, before)
        stub.update_jobs_list.assert_not_called()
        self.assertEqual(stub.results_text.inserted, [])
        messagebox.showinfo.assert_not_called()
        self.assertFalse(widgets["toplevels"][0].destroyed)

    def test_edit_success_keeps_changes_and_reports_refresh(self):
        original_job = {"name": "old job", "query": "SELECT 1", "profile": "P1"}
        stub = make_job_stub([original_job])
        stub.save_jobs = mock.Mock(return_value=True)

        with fake_dialog_widgets() as widgets, \
                mock.patch.object(app, "messagebox") as messagebox:
            self._invoke_save(stub, widgets)

        self.assertEqual(original_job["name"], "renamed job")
        self.assertEqual(original_job["query"], "UPDATE source SET value = 2")
        stub.update_jobs_list.assert_called_once_with()
        self.assertTrue(any("Job updated: renamed job" in line
                            for line in stub.results_text.inserted))
        messagebox.showinfo.assert_called_once()
        self.assertTrue(widgets["toplevels"][0].destroyed)


class LoadPresetTests(unittest.TestCase):
    def _invoke_load(self, stub, widgets):
        stub.load_preset_dialog()
        load_button = next(button for button in widgets["tk_buttons"]
                           if button.command is not None)
        load_button.command()

    def _make_preset(self, folder):
        preset_path = os.path.join(folder, "preset_sample.json")
        preset = {
            "created": "2026-01-01",
            "jobs": [{"name": "loaded job", "query": "SELECT 2"}],
        }
        with open(preset_path, "w", encoding="utf-8") as preset_file:
            json.dump(preset, preset_file)
        return preset_path, preset

    def test_load_failure_restores_jobs_without_success_effects(self):
        with tempfile.TemporaryDirectory() as folder:
            _preset_path, preset = self._make_preset(folder)
            original_jobs = [
                {
                    "name": "current", "query": "SELECT 1", "profile": "P1",
                    "metadata": {"tags": ["keep"]},
                },
                {"name": "other profile", "query": "SELECT 3", "profile": "P2"},
            ]
            original_current_job = original_jobs[0]
            original_other_job = original_jobs[1]
            stub = make_job_stub(original_jobs)
            stub.jobs_file = os.path.join(folder, "saved_jobs.json")
            before = copy.deepcopy(original_jobs)

            def fail_after_in_place_mutation():
                stub.saved_jobs[0]["metadata"] = {"tags": ["changed"]}
                stub.saved_jobs.append({"name": "temporary"})
                return False

            stub.save_jobs = mock.Mock(side_effect=fail_after_in_place_mutation)

            with fake_dialog_widgets() as widgets, \
                    mock.patch.object(app, "messagebox") as messagebox:
                messagebox.askyesno.return_value = True
                self._invoke_load(stub, widgets)

            self.assertIs(stub.saved_jobs, original_jobs)
            self.assertIs(stub.saved_jobs[0], original_current_job)
            self.assertIs(stub.saved_jobs[1], original_other_job)
            self.assertEqual(stub.saved_jobs, before)
            stub.update_jobs_list.assert_not_called()
            self.assertEqual(stub.results_text.inserted, [])
            messagebox.showinfo.assert_not_called()
            self.assertFalse(widgets["toplevels"][0].destroyed)
            with open(_preset_path, encoding="utf-8") as preset_file:
                self.assertEqual(json.load(preset_file), preset)

    def test_load_success_replaces_current_profile_jobs_and_reports(self):
        with tempfile.TemporaryDirectory() as folder:
            self._make_preset(folder)
            original_jobs = [
                {"name": "current", "query": "SELECT 1", "profile": "P1"},
                {"name": "other profile", "query": "SELECT 3", "profile": "P2"},
            ]
            stub = make_job_stub(original_jobs)
            stub.jobs_file = os.path.join(folder, "saved_jobs.json")
            stub.save_jobs = mock.Mock(return_value=True)

            with fake_dialog_widgets() as widgets, \
                    mock.patch.object(app, "messagebox") as messagebox:
                messagebox.askyesno.return_value = True
                self._invoke_load(stub, widgets)

            self.assertEqual(stub.saved_jobs, [
                {"name": "other profile", "query": "SELECT 3", "profile": "P2"},
                {"name": "loaded job", "query": "SELECT 2", "profile": "P1"},
            ])
            stub.update_jobs_list.assert_called_once_with()
            self.assertTrue(any("Loaded preset: sample" in line
                                for line in stub.results_text.inserted))
            messagebox.showinfo.assert_called_once()
            self.assertTrue(widgets["toplevels"][0].destroyed)