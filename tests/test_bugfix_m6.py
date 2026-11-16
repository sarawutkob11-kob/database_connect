"""R5-T4: importing Profiles refreshes the active Profile only after save."""

import copy
import os
import sys
import unittest
from contextlib import ExitStack
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import database_connect_gui as app  # noqa: E402


class _FakeWidget:
    def __init__(self, **kwargs):
        self.value = kwargs.get("value", "")
        self.text = kwargs.get("text", "")
        self.command = kwargs.get("command")
        self.inserted = []

    def __getattr__(self, name):
        if name.startswith("winfo_"):
            return lambda *args, **kwargs: 800
        return lambda *args, **kwargs: self

    def get(self, *_args):
        return self.value

    def set(self, value):
        self.value = value

    def delete(self, *_args):
        self.value = ""

    def insert(self, _index, value):
        self.value = value
        self.inserted.append(value)

    def config(self, **kwargs):
        self.text = kwargs.get("text", self.text)

    configure = config


class _FakeVariable:
    def __init__(self, value=None, **_kwargs):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class ImportProfileRefreshTests(unittest.TestCase):
    def setUp(self):
        self.stub = app.DatabaseConnectorGUI.__new__(app.DatabaseConnectorGUI)
        self.stub.saved_profiles = {
            "Active": {
                "db_type": "Oracle",
                "db_user": "old-user",
                "db_password": "old-password",
                "db_host": "old-host",
                "db_port": "1521",
                "db_name": "old-service",
                "sql_query": "SELECT old",
            },
            "Other": {"db_type": "MySQL", "db_host": "other-host"},
        }
        self.stub.profile_combo = _FakeWidget(value="Active")
        self.stub.results_text = _FakeWidget()
        self.stub.root = _FakeWidget()
        self.stub.db_type = _FakeVariable("Oracle")
        self.stub.db_user = _FakeWidget(value="old-user")
        self.stub.db_password = _FakeWidget(value="old-password")
        self.stub.db_host = _FakeWidget(value="old-host")
        self.stub.db_port = _FakeWidget(value="1521")
        self.stub.db_name = _FakeWidget(value="old-service")
        self.stub.sql_context = _FakeWidget(value="SELECT old")
        self.stub.DEFAULT_SQL_QUERY = "SELECT 1"
        self.stub.LEGACY_DEFAULT_SQL_QUERIES = set()
        self.stub.engine = object()
        self.stub.loaded_excel_data = object()
        self.stub._excel_parameter_values = {"old": "value"}
        self.stub._excel_parameterized_sql = "old sql"
        self.stub.sql_template = "old template"
        self.stub._excel_selected_values = ["old"]
        self.stub._reset_profile_connection_state = mock.Mock()
        self.stub.update_jobs_list = mock.Mock()
        self.stub.update_profile_list = mock.Mock()

    def _import(self, imported_profiles, save_result=True):
        widgets = {"buttons": [], "variables": []}

        def widget_factory(*_args, **kwargs):
            return _FakeWidget(**kwargs)

        def button_factory(*_args, **kwargs):
            button = _FakeWidget(**kwargs)
            widgets["buttons"].append(button)
            return button

        def variable_factory(*_args, **kwargs):
            variable = _FakeVariable(**kwargs)
            widgets["variables"].append(variable)
            return variable

        with ExitStack() as stack:
            for name in (
                "Frame", "Canvas", "Label", "LabelFrame", "Scrollbar", "Listbox",
                "Radiobutton",
            ):
                stack.enter_context(mock.patch.object(app.tk, name, side_effect=widget_factory))
            stack.enter_context(mock.patch.object(app.tk, "Toplevel", side_effect=widget_factory))
            stack.enter_context(mock.patch.object(app.tk, "Button", side_effect=button_factory))
            stack.enter_context(mock.patch.object(app.tk, "BooleanVar", side_effect=variable_factory))
            stack.enter_context(mock.patch.object(app.ttk, "Scrollbar", side_effect=widget_factory))
            stack.enter_context(mock.patch.object(app, "messagebox"))

            self.stub.save_profiles = mock.Mock(return_value=save_result)
            self.stub.load_profile_data = mock.Mock(
                side_effect=lambda profile: app.DatabaseConnectorGUI.load_profile_data(
                    self.stub, profile
                )
            )
            self.stub._show_import_preview_dialog(
                imported_profiles, "profiles.json", "today", len(imported_profiles)
            )
            next(button for button in widgets["buttons"] if button.command).command()

        return widgets

    def test_import_overwriting_active_profile_reloads_imported_fields_and_engine_path(self):
        old_engine = self.stub.engine
        imported = {
            "Active": {
                "db_type": "PostgreSQL",
                "db_user": "imported-user",
                "db_password": "imported-password",
                "db_host": "imported-host",
                "db_port": "5432:5432",
                "db_name": "imported-db",
                "sql_query": "SELECT imported",
            }
        }

        self._import(imported)

        self.stub.save_profiles.assert_called_once()
        self.stub.load_profile_data.assert_called_once_with("Active")
        self.assertEqual(self.stub.db_type.get(), "PostgreSQL")
        self.assertEqual(self.stub.db_user.get(), "imported-user")
        self.assertEqual(self.stub.db_password.get(), "imported-password")
        self.assertEqual(self.stub.db_host.get(), "imported-host")
        self.assertEqual(self.stub.db_port.get(), "5432")
        self.assertEqual(self.stub.db_name.get(), "imported-db")
        self.assertEqual(self.stub.sql_context.get(), "SELECT imported")
        self.assertIsNone(self.stub.loaded_excel_data)
        self.assertEqual(self.stub._excel_parameter_values, {})
        self.stub._reset_profile_connection_state.assert_called_once_with(old_engine)
        self.assertIs(self.stub._active_profile, "Active")

    def test_import_of_non_active_profile_does_not_reload_current_profile(self):
        imported = {"Other": {"db_type": "SQLite", "db_host": "imported-other"}}

        self._import(imported)

        self.stub.save_profiles.assert_called_once()
        self.stub.load_profile_data.assert_not_called()
        self.assertEqual(self.stub.saved_profiles["Other"]["db_host"], "imported-other")
        self.assertEqual(self.stub.db_host.get(), "old-host")

    def test_failed_save_rolls_back_import_and_does_not_reload(self):
        before = copy.deepcopy(self.stub.saved_profiles)
        imported = {
            "Active": {"db_type": "PostgreSQL", "db_host": "unsaved-host"},
            "New": {"db_type": "SQLite", "db_host": "new-host"},
        }

        self._import(imported, save_result=False)

        self.stub.save_profiles.assert_called_once()
        self.stub.load_profile_data.assert_not_called()
        self.stub.update_profile_list.assert_not_called()
        self.assertEqual(self.stub.saved_profiles, before)
        self.assertEqual(self.stub.results_text.inserted, [])