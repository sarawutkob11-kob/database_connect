"""R5-T11: confirm before closing while a task is running."""

import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import database_connect_gui as app  # noqa: E402


class OnClosingTests(unittest.TestCase):
    def setUp(self):
        self.stub = app.DatabaseConnectorGUI.__new__(app.DatabaseConnectorGUI)
        self.stub._is_busy = mock.Mock()
        self.stub.profile_combo = mock.Mock()
        self.stub.profile_combo.get.return_value = "Active"
        self.stub.saved_profiles = {"Active": {}}
        self.stub.save_last_used_profile = mock.Mock()
        self.stub.root = mock.Mock()

    def test_busy_and_user_declines_does_not_save_profile_or_destroy_root(self):
        self.stub._is_busy.return_value = True

        with mock.patch.object(app.messagebox, "askyesno", return_value=False) as askyesno:
            self.stub.on_closing()

        askyesno.assert_called_once_with(
            "Confirm Exit",
            "A task is still running. Are you sure you want to close the application?",
            parent=self.stub.root,
        )
        self.stub.save_last_used_profile.assert_not_called()
        self.stub.root.destroy.assert_not_called()

    def test_busy_and_user_confirms_saves_profile_and_destroys_root(self):
        self.stub._is_busy.return_value = True

        with mock.patch.object(app.messagebox, "askyesno", return_value=True) as askyesno:
            self.stub.on_closing()

        askyesno.assert_called_once_with(
            "Confirm Exit",
            "A task is still running. Are you sure you want to close the application?",
            parent=self.stub.root,
        )
        self.stub.save_last_used_profile.assert_called_once_with("Active")
        self.stub.root.destroy.assert_called_once_with()

    def test_idle_closes_without_prompt_and_saves_profile(self):
        self.stub._is_busy.return_value = False

        with mock.patch.object(app.messagebox, "askyesno") as askyesno:
            self.stub.on_closing()

        askyesno.assert_not_called()
        self.stub.save_last_used_profile.assert_called_once_with("Active")
        self.stub.root.destroy.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()