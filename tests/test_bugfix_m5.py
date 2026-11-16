"""R5-T12: confirm preset overwrite and preserve data on failure."""

import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import database_connect_gui as app  # noqa: E402


class _FakeWidget:
    def __init__(self, **kwargs):
        self.value = kwargs.get("value", "")
        self.text = kwargs.get("text", "")
        self.command = kwargs.get("command")
        self.destroyed = False

    def __getattr__(self, name):
        return lambda *args, **kwargs: self

    def get(self, *_args):
        return self.value

    def destroy(self):
        self.destroyed = True


class SavePresetOverwriteTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.preset_path = os.path.join(self.temp_dir.name, "preset_Foo.json")
        self.original_bytes = b'{"original": true}\n'
        with open(self.preset_path, "wb") as preset_file:
            preset_file.write(self.original_bytes)

        self.stub = app.DatabaseConnectorGUI.__new__(app.DatabaseConnectorGUI)
        self.stub.profile_combo = mock.Mock()
        self.stub.profile_combo.get.return_value = "Active"
        self.stub.saved_jobs = [{"profile": "Active", "name": "job-one"}]
        self.stub.jobs_file = os.path.join(self.temp_dir.name, "jobs.json")
        self.stub.root = mock.Mock()
        self.stub.root.winfo_screenwidth.return_value = 1200
        self.stub.root.winfo_screenheight.return_value = 900
        self.stub.results_text = mock.Mock()

        self.widgets = {"entries": [], "buttons": [], "dialogs": []}

        def widget_factory(*_args, **kwargs):
            return _FakeWidget(**kwargs)

        def entry_factory(*_args, **kwargs):
            entry = _FakeWidget(**kwargs)
            self.widgets["entries"].append(entry)
            return entry

        def button_factory(*_args, **kwargs):
            button = _FakeWidget(**kwargs)
            self.widgets["buttons"].append(button)
            return button

        def dialog_factory(*_args, **kwargs):
            dialog = _FakeWidget(**kwargs)
            self.widgets["dialogs"].append(dialog)
            return dialog

        self.widget_patches = mock.patch.multiple(
            app.tk,
            Frame=mock.DEFAULT,
            Label=mock.DEFAULT,
            Button=mock.DEFAULT,
            Entry=mock.DEFAULT,
            Toplevel=mock.DEFAULT,
        )
        patched = self.widget_patches.start()
        self.addCleanup(self.widget_patches.stop)
        patched["Frame"].side_effect = widget_factory
        patched["Label"].side_effect = widget_factory
        patched["Button"].side_effect = button_factory
        patched["Entry"].side_effect = entry_factory
        patched["Toplevel"].side_effect = dialog_factory

        self.dialog_patches = mock.patch.multiple(
            app.messagebox,
            showwarning=mock.DEFAULT,
            askyesno=mock.DEFAULT,
            showinfo=mock.DEFAULT,
            showerror=mock.DEFAULT,
        )
        self.messagebox_mocks = self.dialog_patches.start()
        self.addCleanup(self.dialog_patches.stop)

        self.timestamp_patch = mock.patch.object(app.pd, "Timestamp")
        self.timestamp_cls = self.timestamp_patch.start()
        self.addCleanup(self.timestamp_patch.stop)
        self.timestamp_cls.now.return_value.isoformat.return_value = "2026-11-16T12:00:00"

        self.stub.save_preset_dialog()
        self.name_entry = self.widgets["entries"][0]
        self.name_entry.value = "foo"
        self.save_callback = next(
            button.command
            for button in self.widgets["buttons"]
            if button.text == "\U0001f4be Save"
        )

    def test_declining_case_insensitive_collision_preserves_file_without_success(self):
        self.messagebox_mocks["askyesno"].return_value = False

        with mock.patch.object(app, "write_json_atomic") as writer:
            self.save_callback()

        self.messagebox_mocks["askyesno"].assert_called_once_with(
            "Overwrite Preset",
            "Preset 'preset_Foo.json' already exists. Overwrite it?",
            parent=self.widgets["dialogs"][0],
        )
        writer.assert_not_called()
        with open(self.preset_path, "rb") as preset_file:
            self.assertEqual(preset_file.read(), self.original_bytes)
        self.messagebox_mocks["showinfo"].assert_not_called()
        self.messagebox_mocks["showerror"].assert_not_called()
        self.stub.results_text.delete.assert_not_called()
        self.assertFalse(self.widgets["dialogs"][0].destroyed)

    def test_confirming_case_insensitive_collision_atomically_overwrites_file(self):
        self.messagebox_mocks["askyesno"].return_value = True

        with mock.patch.object(app, "write_json_atomic", wraps=app.write_json_atomic) as writer:
            self.save_callback()

        writer.assert_called_once()
        self.assertEqual(writer.call_args.args[0], self.preset_path)
        self.assertEqual(writer.call_args.kwargs["indent"], 2)
        with open(self.preset_path, "r", encoding="utf-8") as preset_file:
            saved_preset = json.load(preset_file)
        self.assertEqual(saved_preset["jobs"][0]["name"], "job-one")
        self.assertEqual(saved_preset["created"], "2026-11-16T12:00:00")
        self.messagebox_mocks["showinfo"].assert_called_once()
        self.messagebox_mocks["showerror"].assert_not_called()
        self.assertTrue(self.widgets["dialogs"][0].destroyed)

    def test_write_failure_preserves_file_and_reports_error_without_success(self):
        self.messagebox_mocks["askyesno"].return_value = True

        with mock.patch.object(
            app, "write_json_atomic", side_effect=OSError("disk write failed")
        ) as writer:
            self.save_callback()

        writer.assert_called_once()
        self.messagebox_mocks["showerror"].assert_called_once_with(
            "Error",
            "Failed to save preset:\ndisk write failed",
            parent=self.widgets["dialogs"][0],
        )
        self.messagebox_mocks["showinfo"].assert_not_called()
        with open(self.preset_path, "rb") as preset_file:
            self.assertEqual(preset_file.read(), self.original_bytes)
        self.stub.results_text.delete.assert_not_called()
        self.assertFalse(self.widgets["dialogs"][0].destroyed)


if __name__ == "__main__":
    unittest.main()
