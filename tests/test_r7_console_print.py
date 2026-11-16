"""R7-T1: a console that cannot print must not break save_profiles' failure path.

R7-AC-1 .. R7-AC-5. sys.stdout is always patched in these tests, so nothing
outside cp874 reaches the real console (R7-AC-28 mode b).
"""

import copy
import io
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import database_connect_gui as app  # noqa: E402
from test_bugfix_h3 import (  # noqa: E402
    assert_no_success,
    fake_dialog_widgets,
    make_stub,
)

ORIGINAL_BYTES = b'{"P1": {"db_type": "Oracle", "db_host": "on-disk"}}'


def cp874_stdout() -> io.TextIOWrapper:
    """A Thai Windows console: cannot encode the "❌" emoji."""
    return io.TextIOWrapper(io.BytesIO(), encoding="cp874", errors="strict")


class _ClosedPipe:
    """A stdout whose write raises OSError (e.g. closed pipe)."""

    encoding = "utf-8"

    def write(self, _text):
        raise OSError(32, "Broken pipe")

    def flush(self):
        raise OSError(32, "Broken pipe")


def broken_stdouts():
    return [
        ("cp874", cp874_stdout()),
        ("oserror", _ClosedPipe()),
        ("none", None),
    ]


class StdoutFixtureSanityTests(unittest.TestCase):
    """The fixtures really do break print (otherwise the tests below prove nothing)."""

    def test_cp874_stdout_cannot_print_error_symbol(self):
        with self.assertRaises(UnicodeEncodeError):
            print("❌ Cannot save profile!", file=cp874_stdout())

    def test_closed_pipe_raises_oserror(self):
        with self.assertRaises(OSError):
            print("x", file=_ClosedPipe())


class SaveProfilesBrokenStdoutTests(unittest.TestCase):
    """R7-AC-1 / R7-AC-2."""

    def _run(self, stdout):
        with tempfile.TemporaryDirectory() as folder:
            config_file = os.path.join(folder, "db_profiles.json")
            with open(config_file, "wb") as handle:
                handle.write(ORIGINAL_BYTES)
            stub = make_stub()
            stub.config_file = config_file
            stub.get_last_used_profile = mock.Mock(return_value="P1")
            with mock.patch.object(sys, "stdout", stdout), \
                    mock.patch.object(app, "write_json_atomic",
                                      side_effect=OSError("disk locked")), \
                    mock.patch.object(app, "messagebox") as messagebox:
                result = stub.save_profiles()
            with open(config_file, "rb") as handle:
                on_disk = handle.read()
        return result, messagebox, config_file, on_disk

    def test_broken_stdout_returns_false_and_shows_dialog_once(self):
        for label, stdout in broken_stdouts():
            with self.subTest(stdout=label):
                result, messagebox, config_file, on_disk = self._run(stdout)
                self.assertIs(result, False)
                messagebox.showerror.assert_called_once_with(
                    "Save Error",
                    f"❌ Cannot save profile!\n\nError: disk locked\n\nPath: {config_file}",
                )
                messagebox.showinfo.assert_not_called()
                self.assertEqual(on_disk, ORIGINAL_BYTES)

    def test_stdout_none_does_not_raise(self):
        result, messagebox, _config_file, _on_disk = self._run(None)
        self.assertIs(result, False)
        self.assertEqual(messagebox.showerror.call_count, 1)


class SaveProfilesUtf8StdoutTests(unittest.TestCase):
    """R7-AC-5: when the console can print, the message is still printed."""

    def test_failure_still_prints_error_message(self):
        stdout = io.StringIO()
        stub = make_stub()
        stub.config_file = "unused_profiles.json"
        stub.get_last_used_profile = mock.Mock(return_value=None)
        with mock.patch.object(sys, "stdout", stdout), \
                mock.patch.object(app, "write_json_atomic", side_effect=OSError("locked")), \
                mock.patch.object(app, "messagebox") as messagebox:
            result = stub.save_profiles()
        self.assertIs(result, False)
        expected = "❌ Cannot save profile!\n\nError: locked\n\nPath: unused_profiles.json"
        self.assertIn(expected, stdout.getvalue())
        messagebox.showerror.assert_called_once_with("Save Error", expected)

    def test_success_returns_true_and_prints_nothing(self):
        stdout = io.StringIO()
        with tempfile.TemporaryDirectory() as folder:
            stub = make_stub()
            stub.config_file = os.path.join(folder, "db_profiles.json")
            stub.get_last_used_profile = mock.Mock(return_value="P1")
            with mock.patch.object(sys, "stdout", stdout), \
                    mock.patch.object(app, "messagebox") as messagebox:
                result = stub.save_profiles()
            self.assertTrue(os.path.exists(stub.config_file))
        self.assertIs(result, True)
        self.assertEqual(stdout.getvalue(), "")
        messagebox.showerror.assert_not_called()


class OtherSaveFailurePathsTests(unittest.TestCase):
    """R7-AC-3: regression lock - these paths never print, so a broken console is harmless."""

    def _assert_failed_once(self, call, title, message_part):
        stdout = cp874_stdout()
        with mock.patch.object(sys, "stdout", stdout), \
                mock.patch.object(app, "write_json_atomic",
                                  side_effect=OSError("locked")) as write_json, \
                mock.patch.object(app, "messagebox") as messagebox:
            result = call()
        self.assertIs(result, False)
        messagebox.showerror.assert_called_once()
        args = messagebox.showerror.call_args[0]
        self.assertEqual(args[0], title)
        self.assertIn(message_part, args[1])
        stdout.flush()
        self.assertEqual(stdout.buffer.getvalue(), b"")
        return write_json

    def test_save_jobs_blocked(self):
        stub = make_stub()
        stub._jobs_save_blocked = True
        stub.jobs_file = "unused_jobs.json"
        stub.saved_jobs = []
        write_json = self._assert_failed_once(
            stub.save_jobs, "Error", "saved_jobs.json could not be read")
        write_json.assert_not_called()

    def test_save_jobs_write_raises(self):
        stub = make_stub()
        stub.jobs_file = "unused_jobs.json"
        stub.saved_jobs = [{"name": "j", "query": "SELECT 1"}]
        write_json = self._assert_failed_once(
            stub.save_jobs, "Error", "Failed to save jobs:\nlocked")
        write_json.assert_called_once()

    def _script_group_stub(self):
        stub = make_stub()
        stub.script_groups = [{"name": "G", "scripts": [{"name": "s", "sql": "SELECT 1"}]}]
        stub._script_groups_backup_done = True
        stub._script_groups_path = mock.Mock(return_value="unused_groups.json")
        return stub

    def test_save_script_groups_blocked(self):
        stub = self._script_group_stub()
        stub._script_groups_save_blocked = True
        write_json = self._assert_failed_once(
            stub.save_script_groups, "Script Groups", "script_groups.json could not be read")
        write_json.assert_not_called()

    def test_save_script_groups_write_raises(self):
        stub = self._script_group_stub()
        write_json = self._assert_failed_once(
            stub.save_script_groups, "Script Groups", "Cannot save script_groups.json:\nlocked")
        write_json.assert_called_once()

    def test_save_profiles_blocked(self):
        stub = make_stub()
        stub._profiles_save_blocked = True
        stub.config_file = "unused_profiles.json"
        write_json = self._assert_failed_once(
            stub.save_profiles, "Save Error", "db_profiles.json could not be read")
        write_json.assert_not_called()


class CallerRollbackUnderBrokenStdoutTests(unittest.TestCase):
    """R7-AC-4: callers of the real save_profiles roll back under a cp874 console."""

    def _stub(self, folder):
        stub = make_stub()
        stub.config_file = os.path.join(folder, "db_profiles.json")
        with open(stub.config_file, "wb") as handle:
            handle.write(ORIGINAL_BYTES)
        stub.get_last_used_profile = mock.Mock(return_value="P1")
        stub.update_profile_list = mock.Mock()
        stub.load_profile_data = mock.Mock()
        return stub

    def test_delete_profile_rolls_back(self):
        with tempfile.TemporaryDirectory() as folder:
            stub = self._stub(folder)
            before = copy.deepcopy(stub.saved_profiles)
            with mock.patch.object(sys, "stdout", cp874_stdout()), \
                    mock.patch.object(app, "write_json_atomic", side_effect=OSError("locked")), \
                    mock.patch.object(app, "messagebox") as messagebox:
                messagebox.askyesno.return_value = True
                stub.delete_profile()
            with open(stub.config_file, "rb") as handle:
                self.assertEqual(handle.read(), ORIGINAL_BYTES)

        self.assertEqual(stub.saved_profiles, before)
        stub.update_profile_list.assert_not_called()
        messagebox.showerror.assert_called_once()
        assert_no_success(self, stub, messagebox)

    def _run_import(self, merge_mode):
        with tempfile.TemporaryDirectory() as folder:
            stub = self._stub(folder)
            before = copy.deepcopy(stub.saved_profiles)
            imported = {
                "P1": {"db_type": "PostgreSQL", "db_host": "imported-host"},
                "P3": {"db_type": "Oracle", "db_host": "new-host"},
            }
            with fake_dialog_widgets() as widgets, \
                    mock.patch.object(sys, "stdout", cp874_stdout()), \
                    mock.patch.object(app, "write_json_atomic", side_effect=OSError("locked")), \
                    mock.patch.object(app, "messagebox") as messagebox:
                messagebox.askyesno.return_value = True
                stub._show_import_preview_dialog(imported, "profiles.json", "today", 2)
                widgets["variables"][0].set(merge_mode)
                widgets["tk_buttons"][0].command()
            with open(stub.config_file, "rb") as handle:
                self.assertEqual(handle.read(), ORIGINAL_BYTES)
        self.assertEqual(stub.saved_profiles, before)
        stub.update_profile_list.assert_not_called()
        stub.load_profile_data.assert_not_called()
        self.assertEqual(stub.profile_combo.calls, [])
        # Only save_profiles' own "Save Error" dialog - no exception dialog from do_import
        messagebox.showerror.assert_called_once()
        self.assertEqual(messagebox.showerror.call_args[0][0], "Save Error")
        assert_no_success(self, stub, messagebox)

    def test_do_import_merge_rolls_back(self):
        self._run_import(True)

    def test_do_import_replace_rolls_back(self):
        self._run_import(False)


if __name__ == "__main__":
    unittest.main()
