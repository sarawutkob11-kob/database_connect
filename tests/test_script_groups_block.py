"""T3: unreadable script_groups.json blocks saving (AC-14, AC-15, AC-18 load part).

Every file lives in a TemporaryDirectory; messagebox is mocked (no Tk window).
"""

import glob
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import database_connect_gui as app  # noqa: E402

CORRUPT = '{"version": 1, "groups": [{"name": "G1", "scripts": [ BROKEN'


def make_stub(folder: str):
    stub = app.DatabaseConnectorGUI.__new__(app.DatabaseConnectorGUI)
    path = os.path.join(folder, "script_groups.json")
    stub._script_groups_path = lambda: path
    stub.script_groups = []
    return stub, path


def write(path: str, text: str) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def read(path: str) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def unreadable_copies(folder: str) -> list:
    return sorted(glob.glob(os.path.join(folder, "script_groups_unreadable_*.json")))


class LoadCorruptTests(unittest.TestCase):
    """AC-14"""

    def test_corrupt_file_copy_ok(self):
        with tempfile.TemporaryDirectory() as tmp:
            stub, path = make_stub(tmp)
            write(path, CORRUPT)
            with mock.patch.object(app, "messagebox") as mb:
                result = stub.load_script_groups()
            self.assertEqual(result, [])
            copies = unreadable_copies(tmp)
            self.assertEqual(len(copies), 1)
            self.assertRegex(
                os.path.basename(copies[0]),
                r"^script_groups_unreadable_\d{8}_\d{6}\.json$",
            )
            self.assertEqual(read(copies[0]), CORRUPT)
            self.assertIs(stub._script_groups_save_blocked, False)
            # warning comes from _handle_unreadable_file; no showerror on load
            self.assertEqual(mb.showwarning.call_count, 1)
            mb.showerror.assert_not_called()
            # original file is left untouched
            self.assertEqual(read(path), CORRUPT)

    def test_corrupt_file_copy_fails_sets_flag_true(self):
        with tempfile.TemporaryDirectory() as tmp:
            stub, path = make_stub(tmp)
            write(path, CORRUPT)
            with mock.patch.object(app, "messagebox") as mb, mock.patch.object(
                app, "preserve_unreadable_file", return_value=None
            ) as preserve:
                result = stub.load_script_groups()
            self.assertEqual(result, [])
            preserve.assert_called_once_with(path)
            self.assertIs(stub._script_groups_save_blocked, True)
            self.assertEqual(mb.showwarning.call_count, 1)
            mb.showerror.assert_not_called()

    def test_flag_equals_handle_unreadable_return(self):
        for ret in (True, False):
            with self.subTest(ret=ret), tempfile.TemporaryDirectory() as tmp:
                stub, path = make_stub(tmp)
                write(path, CORRUPT)
                with mock.patch.object(
                    app.DatabaseConnectorGUI, "_handle_unreadable_file", return_value=ret
                ) as handle:
                    self.assertEqual(stub.load_script_groups(), [])
                handle.assert_called_once()
                args = handle.call_args[0]
                self.assertEqual(args[0], path)
                self.assertEqual(args[1], "Script Groups")
                self.assertIsInstance(args[2], Exception)
                self.assertIs(stub._script_groups_save_blocked, ret)

    def test_empty_file_is_treated_as_unreadable(self):
        with tempfile.TemporaryDirectory() as tmp:
            stub, path = make_stub(tmp)
            write(path, "")
            with mock.patch.object(app, "messagebox"):
                self.assertEqual(stub.load_script_groups(), [])
            self.assertEqual(len(unreadable_copies(tmp)), 1)
            self.assertIs(stub._script_groups_save_blocked, False)

    def test_readable_file_does_not_set_flag(self):
        with tempfile.TemporaryDirectory() as tmp:
            stub, path = make_stub(tmp)
            write(path, json.dumps({"version": 1, "groups": [{"name": "G1", "scripts": []}]}))
            with mock.patch.object(app, "messagebox") as mb:
                result = stub.load_script_groups()
            self.assertEqual([g["name"] for g in result], ["G1"])
            self.assertFalse(hasattr(stub, "_script_groups_save_blocked"))
            self.assertEqual(mb.mock_calls, [])
            self.assertEqual(unreadable_copies(tmp), [])


class LoadMissingTests(unittest.TestCase):
    """AC-18 (load part)"""

    def test_missing_file_returns_empty_silently(self):
        with tempfile.TemporaryDirectory() as tmp:
            stub, path = make_stub(tmp)
            with mock.patch.object(app, "messagebox") as mb:
                self.assertEqual(stub.load_script_groups(), [])
            self.assertEqual(mb.mock_calls, [])
            self.assertFalse(hasattr(stub, "_script_groups_save_blocked"))
            self.assertIs(getattr(stub, "_script_groups_save_blocked", False), False)
            self.assertEqual(os.listdir(tmp), [])


class SaveBlockedTests(unittest.TestCase):
    """AC-15"""

    def test_blocked_save_touches_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            stub, path = make_stub(tmp)
            backup = os.path.join(tmp, "script_groups_backup.json")
            write(path, CORRUPT)
            write(backup, '{"version": 1, "groups": [{"name": "OLD"}]}')
            old_time = 1_600_000_000
            os.utime(path, (old_time, old_time))
            os.utime(backup, (old_time, old_time))
            before = {
                p: (read(p), os.stat(p).st_mtime_ns) for p in (path, backup)
            }
            listing = sorted(os.listdir(tmp))

            stub._script_groups_save_blocked = True
            stub.script_groups = [{"name": "NEW", "scripts": [{"name": "s", "sql": "x"}]}]
            with mock.patch.object(app, "messagebox") as mb, mock.patch.object(
                app, "write_json_atomic"
            ) as atomic:
                self.assertIs(stub.save_script_groups(), False)

            for p, (content, mtime) in before.items():
                self.assertEqual(read(p), content, p)
                self.assertEqual(os.stat(p).st_mtime_ns, mtime, p)
            self.assertEqual(sorted(os.listdir(tmp)), listing)
            atomic.assert_not_called()
            self.assertEqual(mb.showerror.call_count, 1)
            title, message = mb.showerror.call_args[0]
            self.assertEqual(title, "Script Groups")
            self.assertIn("could not be read", message)
            self.assertIn("not overwritten", message)
            mb.showwarning.assert_not_called()

    def test_blocked_save_when_files_do_not_exist(self):
        with tempfile.TemporaryDirectory() as tmp:
            stub, _ = make_stub(tmp)
            stub._script_groups_save_blocked = True
            stub.script_groups = [{"name": "NEW", "scripts": []}]
            with mock.patch.object(app, "messagebox") as mb:
                stub.save_script_groups()
            self.assertEqual(os.listdir(tmp), [])
            self.assertEqual(mb.showerror.call_count, 1)

    def test_end_to_end_copy_fails_then_save_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            stub, path = make_stub(tmp)
            write(path, CORRUPT)
            with mock.patch.object(app, "messagebox") as mb, mock.patch.object(
                app, "preserve_unreadable_file", return_value=None
            ):
                stub.script_groups = stub.load_script_groups()
                stub.script_groups.append({"name": "NEW", "scripts": []})
                stub.save_script_groups()
                stub.save_script_groups()
            self.assertEqual(read(path), CORRUPT)
            self.assertEqual(sorted(os.listdir(tmp)), ["script_groups.json"])
            self.assertEqual(mb.showerror.call_count, 2)

    def test_flag_false_allows_save(self):
        with tempfile.TemporaryDirectory() as tmp:
            stub, path = make_stub(tmp)
            stub._script_groups_save_blocked = False
            stub.script_groups = [{"name": "G2", "scripts": []}]
            with mock.patch.object(app, "messagebox") as mb:
                stub.save_script_groups()
            mb.showerror.assert_not_called()
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
            self.assertEqual([g["name"] for g in data["groups"]], ["G2"])


class C2ScenarioTests(unittest.TestCase):
    """Corrupt file, copy succeeds, save twice: original data still exists."""

    def test_original_data_survives_two_saves(self):
        with tempfile.TemporaryDirectory() as tmp:
            stub, path = make_stub(tmp)
            write(path, CORRUPT)
            with mock.patch.object(app, "messagebox") as mb:
                stub.script_groups = stub.load_script_groups()
                self.assertIs(stub._script_groups_save_blocked, False)
                stub.script_groups.append({"name": "G2", "scripts": []})
                stub.save_script_groups()
                stub.script_groups.append({"name": "G3", "scripts": []})
                stub.save_script_groups()
            mb.showerror.assert_not_called()
            copies = unreadable_copies(tmp)
            self.assertEqual(len(copies), 1)
            self.assertEqual(read(copies[0]), CORRUPT)
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
            self.assertEqual([g["name"] for g in data["groups"]], ["G2", "G3"])
            # T4: backup is never overwritten with the app's own data
            self.assertFalse(
                os.path.exists(os.path.join(tmp, "script_groups_backup.json"))
            )

    def test_existing_good_backup_survives_two_saves(self):
        with tempfile.TemporaryDirectory() as tmp:
            stub, path = make_stub(tmp)
            backup = os.path.join(tmp, "script_groups_backup.json")
            good = json.dumps({"version": 1, "groups": [{"name": "G1", "scripts": []}]})
            write(backup, good)
            write(path, CORRUPT)
            with mock.patch.object(app, "messagebox"):
                stub.script_groups = stub.load_script_groups()
                stub.script_groups.append({"name": "G2", "scripts": []})
                stub.save_script_groups()
                stub.script_groups.append({"name": "G3", "scripts": []})
                stub.save_script_groups()
            self.assertEqual(read(backup), good)
            self.assertEqual(read(unreadable_copies(tmp)[0]), CORRUPT)


if __name__ == "__main__":
    unittest.main()
