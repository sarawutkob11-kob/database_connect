"""T4: script_groups backup once per session + atomic write.

AC-16, AC-17, AC-18 (save part), AC-19, AC-36. Temp folders only, messagebox mocked.
"""

import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import database_connect_gui as app  # noqa: E402

CORRUPT = '{"version": 1, "groups": [ BROKEN'


def make_stub(folder: str):
    stub = app.DatabaseConnectorGUI.__new__(app.DatabaseConnectorGUI)
    path = os.path.join(folder, "script_groups.json")
    stub._script_groups_path = lambda: path
    stub.script_groups = []
    return stub, path, os.path.join(folder, "script_groups_backup.json")


def write_groups(path: str, *names: str) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"version": 1, "groups": [{"name": n, "scripts": []} for n in names]}, fh)


def group_names(path: str) -> list:
    with open(path, encoding="utf-8") as fh:
        return [g["name"] for g in json.load(fh)["groups"]]


def read(path: str) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def groups(*names: str) -> list:
    return [{"name": n, "scripts": []} for n in names]


class CorruptFileKeepsBackupTests(unittest.TestCase):
    """AC-16"""

    def test_good_backup_not_overwritten_by_corrupt_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            stub, path, backup = make_stub(tmp)
            write_groups(backup, "OLD")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(CORRUPT)
            backup_before = (read(backup), os.stat(backup).st_mtime_ns)
            stub.script_groups = groups("NEW")
            with mock.patch.object(app, "messagebox") as mb:
                stub.save_script_groups()
            mb.showerror.assert_not_called()
            self.assertEqual((read(backup), os.stat(backup).st_mtime_ns), backup_before)
            self.assertEqual(group_names(backup), ["OLD"])
            self.assertEqual(group_names(path), ["NEW"])

    def test_corrupt_file_without_backup_creates_no_backup(self):
        with tempfile.TemporaryDirectory() as tmp:
            stub, path, backup = make_stub(tmp)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(CORRUPT)
            stub.script_groups = groups("NEW")
            with mock.patch.object(app, "messagebox"):
                stub.save_script_groups()
            self.assertFalse(os.path.exists(backup))
            self.assertEqual(group_names(path), ["NEW"])


class BackupOncePerSessionTests(unittest.TestCase):
    """AC-17"""

    def test_two_saves_keep_first_backup(self):
        with tempfile.TemporaryDirectory() as tmp:
            stub, path, backup = make_stub(tmp)
            write_groups(path, "G1")
            with mock.patch.object(app, "messagebox") as mb:
                stub.script_groups = groups("G2")
                stub.save_script_groups()
                self.assertEqual(group_names(backup), ["G1"])
                self.assertEqual(group_names(path), ["G2"])
                stub.script_groups = groups("G3")
                stub.save_script_groups()
            mb.showerror.assert_not_called()
            self.assertEqual(group_names(backup), ["G1"])
            self.assertEqual(group_names(path), ["G3"])
            self.assertIs(stub._script_groups_backup_done, True)

    def test_backup_helper_called_only_on_first_save(self):
        with tempfile.TemporaryDirectory() as tmp:
            stub, path, _ = make_stub(tmp)
            write_groups(path, "G1")
            real = app.DatabaseConnectorGUI._backup_script_groups_once
            with mock.patch.object(
                app.DatabaseConnectorGUI, "_backup_script_groups_once",
                autospec=True, side_effect=real,
            ) as helper, mock.patch.object(app, "messagebox"):
                for _ in range(3):
                    stub.save_script_groups()
            self.assertEqual(helper.call_count, 1)
            self.assertEqual(helper.call_args[0][1], path)


class NewSessionBackupTests(unittest.TestCase):
    """AC-36"""

    def test_first_save_creates_backup_and_new_session_refreshes_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            stub, path, backup = make_stub(tmp)
            write_groups(path, "G1")
            self.assertFalse(os.path.exists(backup))
            with mock.patch.object(app, "messagebox") as mb:
                stub.script_groups = groups("G2")
                stub.save_script_groups()
                self.assertEqual(group_names(backup), ["G1"])
                stub.script_groups = groups("G3")
                stub.save_script_groups()
                self.assertEqual(group_names(backup), ["G1"])

                # new session: fresh stub, no state from before
                stub2, path2, backup2 = make_stub(tmp)
                self.assertEqual((path2, backup2), (path, backup))
                self.assertFalse(hasattr(stub2, "_script_groups_backup_done"))
                stub2.script_groups = groups("G4")
                stub2.save_script_groups()
            mb.showerror.assert_not_called()
            self.assertEqual(group_names(backup), ["G3"])
            self.assertEqual(group_names(path), ["G4"])


class NoFileTests(unittest.TestCase):
    """AC-18 (save part, with load)"""

    def test_missing_file_load_then_save(self):
        with tempfile.TemporaryDirectory() as tmp:
            stub, path, backup = make_stub(tmp)
            with mock.patch.object(app, "messagebox") as mb:
                stub.script_groups = stub.load_script_groups()
                self.assertEqual(stub.script_groups, [])
                stub.script_groups.append({"name": "G1", "scripts": []})
                stub.save_script_groups()
            self.assertEqual(mb.mock_calls, [])
            self.assertIs(getattr(stub, "_script_groups_save_blocked", False), False)
            self.assertEqual(group_names(path), ["G1"])
            self.assertFalse(os.path.exists(backup))
            self.assertEqual(sorted(os.listdir(tmp)), ["script_groups.json"])


class AtomicWriteTests(unittest.TestCase):
    """AC-19"""

    def test_no_tmp_left_and_keys_stripped(self):
        with tempfile.TemporaryDirectory() as tmp:
            stub, path, _ = make_stub(tmp)
            stub.script_groups = [
                {
                    "name": "G1",
                    "scripts": [
                        {"name": "s1", "sql": "SELECT 1", "_status": "ok", "run_index": 3},
                        {"name": "s2", "sql": "SELECT 'ไทย'", "_row": 1},
                    ],
                }
            ]
            with mock.patch.object(app, "messagebox") as mb:
                stub.save_script_groups()
            mb.showerror.assert_not_called()
            self.assertFalse(os.path.exists(path + ".tmp"))
            self.assertEqual(
                [n for n in os.listdir(tmp) if n.endswith(".tmp")], []
            )
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
            self.assertEqual(
                data,
                {
                    "version": 1,
                    "groups": [
                        {
                            "name": "G1",
                            "scripts": [
                                {"name": "s1", "sql": "SELECT 1"},
                                {"name": "s2", "sql": "SELECT 'ไทย'"},
                            ],
                        }
                    ],
                },
            )
            # in-memory data is not mutated
            self.assertIn("_status", stub.script_groups[0]["scripts"][0])
            self.assertIn("ไทย", read(path))  # ensure_ascii=False

    def test_uses_write_json_atomic(self):
        with tempfile.TemporaryDirectory() as tmp:
            stub, path, _ = make_stub(tmp)
            stub.script_groups = groups("G1")
            with mock.patch.object(app, "write_json_atomic") as atomic, \
                    mock.patch.object(app, "messagebox"):
                stub.save_script_groups()
            atomic.assert_called_once()
            args, kwargs = atomic.call_args
            self.assertEqual(args[0], path)
            self.assertEqual(args[1], {"version": 1, "groups": groups("G1")})
            self.assertEqual(kwargs.get("indent", args[2] if len(args) > 2 else None), 2)

    def test_write_failure_shows_error_and_keeps_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            stub, path, _ = make_stub(tmp)
            write_groups(path, "G1")
            stub.script_groups = groups("G2")
            with mock.patch.object(
                app, "write_json_atomic", side_effect=OSError("locked")
            ), mock.patch.object(app, "messagebox") as mb:
                stub.save_script_groups()
            self.assertEqual(mb.showerror.call_count, 1)
            self.assertIn("locked", mb.showerror.call_args[0][1])
            self.assertEqual(group_names(path), ["G1"])


class BackupCopyFailureTests(unittest.TestCase):
    def test_copy_failure_shows_error_and_does_not_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            stub, path, backup = make_stub(tmp)
            write_groups(path, "G1")
            before = (read(path), os.stat(path).st_mtime_ns)
            stub.script_groups = groups("G2")
            with mock.patch("shutil.copy2", side_effect=OSError("disk full")), \
                    mock.patch.object(app, "messagebox") as mb:
                stub.save_script_groups()
            self.assertEqual(mb.showerror.call_count, 1)
            self.assertIn("disk full", mb.showerror.call_args[0][1])
            self.assertEqual((read(path), os.stat(path).st_mtime_ns), before)
            self.assertFalse(os.path.exists(backup))
            self.assertFalse(os.path.exists(path + ".tmp"))
            # retry rule: a failed backup does not count as done
            self.assertIs(getattr(stub, "_script_groups_backup_done", False), False)

    def test_next_save_retries_backup(self):
        import shutil

        real_copy2 = shutil.copy2
        with tempfile.TemporaryDirectory() as tmp:
            stub, path, backup = make_stub(tmp)
            write_groups(path, "G1")
            old = read(path)
            calls = {"n": 0}

            def flaky_copy2(src, dst, *a, **k):
                calls["n"] += 1
                if calls["n"] == 1:
                    raise OSError("file locked by OneDrive")
                return real_copy2(src, dst, *a, **k)

            with mock.patch("shutil.copy2", side_effect=flaky_copy2), \
                    mock.patch.object(app, "messagebox") as mb:
                stub.script_groups = groups("G2")
                stub.save_script_groups()  # backup fails -> refused
                self.assertEqual(mb.showerror.call_count, 1)
                self.assertEqual(read(path), old)
                self.assertFalse(os.path.exists(backup))
                self.assertFalse(os.path.exists(path + ".tmp"))
                self.assertIs(getattr(stub, "_script_groups_backup_done", False), False)

                stub.save_script_groups()  # retry: backup OK, then write
            self.assertEqual(calls["n"], 2)
            self.assertEqual(mb.showerror.call_count, 1)
            self.assertEqual(read(backup), old)
            self.assertEqual(group_names(backup), ["G1"])
            self.assertEqual(group_names(path), ["G2"])
            self.assertIs(stub._script_groups_backup_done, True)
            self.assertFalse(os.path.exists(path + ".tmp"))

    def test_third_save_after_retry_does_not_backup_again(self):
        import shutil

        real_copy2 = shutil.copy2
        with tempfile.TemporaryDirectory() as tmp:
            stub, path, backup = make_stub(tmp)
            write_groups(path, "G1")
            seq = [OSError("locked"), None, None]

            def flaky_copy2(src, dst, *a, **k):
                err = seq.pop(0)
                if err:
                    raise err
                return real_copy2(src, dst, *a, **k)

            with mock.patch("shutil.copy2", side_effect=flaky_copy2) as cp, \
                    mock.patch.object(app, "messagebox"):
                stub.script_groups = groups("G2")
                stub.save_script_groups()  # fails
                stub.save_script_groups()  # backup G1, write G2
                stub.script_groups = groups("G3")
                stub.save_script_groups()  # no backup: G1 stays
            self.assertEqual(cp.call_count, 2)
            self.assertEqual(group_names(backup), ["G1"])
            self.assertEqual(group_names(path), ["G3"])

    def test_copy_fails_twice_nothing_written(self):
        with tempfile.TemporaryDirectory() as tmp:
            stub, path, backup = make_stub(tmp)
            write_groups(path, "G1")
            before = (read(path), os.stat(path).st_mtime_ns)
            with mock.patch("shutil.copy2", side_effect=OSError("disk full")) as cp, \
                    mock.patch.object(app, "messagebox") as mb, \
                    mock.patch.object(app, "write_json_atomic",
                                      wraps=app.write_json_atomic) as atomic:
                stub.script_groups = groups("G2")
                stub.save_script_groups()
                self.assertEqual((read(path), os.stat(path).st_mtime_ns), before)
                stub.script_groups = groups("G3")
                stub.save_script_groups()
            self.assertEqual(cp.call_count, 2)  # retried on the second save
            self.assertEqual(mb.showerror.call_count, 2)
            atomic.assert_not_called()
            self.assertEqual((read(path), os.stat(path).st_mtime_ns), before)
            self.assertEqual(group_names(path), ["G1"])
            self.assertFalse(os.path.exists(backup))
            self.assertFalse(os.path.exists(path + ".tmp"))
            self.assertIs(getattr(stub, "_script_groups_backup_done", False), False)

    def test_helper_raises_and_keeps_flag_false(self):
        with tempfile.TemporaryDirectory() as tmp:
            stub, path, _ = make_stub(tmp)
            write_groups(path, "G1")
            with mock.patch("shutil.copy2", side_effect=PermissionError("denied")):
                with self.assertRaises(PermissionError):
                    stub._backup_script_groups_once(path)
            self.assertIs(getattr(stub, "_script_groups_backup_done", False), False)

    def test_write_failure_after_backup_keeps_backup_done(self):
        with tempfile.TemporaryDirectory() as tmp:
            stub, path, backup = make_stub(tmp)
            write_groups(path, "G1")
            stub.script_groups = groups("G2")
            with mock.patch.object(app, "write_json_atomic", side_effect=OSError("locked")), \
                    mock.patch.object(app, "messagebox") as mb:
                stub.save_script_groups()
            mb.showerror.assert_called_once()
            self.assertEqual(group_names(backup), ["G1"])
            self.assertEqual(group_names(path), ["G1"])
            self.assertIs(stub._script_groups_backup_done, True)


class LockedFileTests(unittest.TestCase):
    """Review fix 1: a locked file (PermissionError) is not 'broken JSON'."""

    def _lock_reads(self, path, times):
        """Patch open(): reading `path` raises PermissionError the first `times` times."""
        import builtins

        real_open = builtins.open
        state = {"left": times, "hits": 0}

        def fake_open(file, mode="r", *a, **k):
            if os.path.abspath(str(file)) == os.path.abspath(path) and "r" in mode \
                    and "+" not in mode and state["left"] > 0:
                state["left"] -= 1
                state["hits"] += 1
                raise PermissionError(13, "The process cannot access the file", str(file))
            return real_open(file, mode, *a, **k)

        return mock.patch("builtins.open", side_effect=fake_open), state

    def test_locked_on_first_save_then_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            stub, path, backup = make_stub(tmp)
            write_groups(path, "G1")
            pre_session = read(path)
            before = (pre_session, os.stat(path).st_mtime_ns)
            patcher, state = self._lock_reads(path, 1)
            with patcher, mock.patch.object(app, "messagebox") as mb:
                stub.script_groups = groups("G2")
                stub.save_script_groups()
                self.assertEqual(state["hits"], 1)
                self.assertEqual(mb.showerror.call_count, 1)
                self.assertIn("Cannot save", mb.showerror.call_args[0][1])
                self.assertEqual((read(path), os.stat(path).st_mtime_ns), before)
                self.assertFalse(os.path.exists(backup))
                self.assertFalse(os.path.exists(path + ".tmp"))
                self.assertIs(getattr(stub, "_script_groups_backup_done", False), False)

                stub.save_script_groups()  # unlocked now
            self.assertEqual(mb.showerror.call_count, 1)
            self.assertEqual(read(backup), pre_session)
            self.assertEqual(group_names(path), ["G2"])
            self.assertIs(stub._script_groups_backup_done, True)
            self.assertFalse(os.path.exists(path + ".tmp"))

    def test_locked_twice_never_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            stub, path, backup = make_stub(tmp)
            write_groups(path, "G1")
            before = (read(path), os.stat(path).st_mtime_ns)
            patcher, _state = self._lock_reads(path, 2)
            with patcher, mock.patch.object(app, "messagebox") as mb:
                stub.script_groups = groups("G2")
                stub.save_script_groups()
                stub.save_script_groups()
            self.assertEqual(mb.showerror.call_count, 2)
            self.assertEqual((read(path), os.stat(path).st_mtime_ns), before)
            self.assertFalse(os.path.exists(backup))
            self.assertIs(getattr(stub, "_script_groups_backup_done", False), False)

    def test_bad_bytes_file_is_broken_not_locked(self):
        with tempfile.TemporaryDirectory() as tmp:
            stub, path, backup = make_stub(tmp)
            write_groups(backup, "OLD")
            backup_before = (read(backup), os.stat(backup).st_mtime_ns)
            with open(path, "wb") as fh:
                fh.write(b"\xff\xfe\x00\x81 not utf-8 \xc3\x28")
            stub.script_groups = groups("NEW")
            with mock.patch.object(app, "messagebox") as mb:
                stub.save_script_groups()
            mb.showerror.assert_not_called()
            self.assertIs(stub._script_groups_backup_done, True)
            self.assertEqual((read(backup), os.stat(backup).st_mtime_ns), backup_before)
            self.assertEqual(group_names(path), ["NEW"])

    def test_corrupt_json_flag_true_and_backup_kept(self):
        with tempfile.TemporaryDirectory() as tmp:
            stub, path, backup = make_stub(tmp)
            write_groups(backup, "OLD")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(CORRUPT)
            stub.script_groups = groups("NEW")
            with mock.patch.object(app, "messagebox") as mb:
                stub.save_script_groups()
            mb.showerror.assert_not_called()
            self.assertIs(stub._script_groups_backup_done, True)
            self.assertEqual(group_names(backup), ["OLD"])
            self.assertEqual(group_names(path), ["NEW"])

    def test_no_file_saves_without_backup(self):
        with tempfile.TemporaryDirectory() as tmp:
            stub, path, backup = make_stub(tmp)
            stub.script_groups = groups("G1")
            with mock.patch.object(app, "messagebox") as mb:
                stub.save_script_groups()
            mb.showerror.assert_not_called()
            self.assertIs(stub._script_groups_backup_done, True)
            self.assertFalse(os.path.exists(backup))
            self.assertEqual(group_names(path), ["G1"])


class BackupHelperTests(unittest.TestCase):
    def test_sets_flag_even_when_file_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            stub, path, backup = make_stub(tmp)
            stub._backup_script_groups_once(path)
            self.assertIs(stub._script_groups_backup_done, True)
            self.assertFalse(os.path.exists(backup))

    def test_sets_flag_when_file_corrupt(self):
        with tempfile.TemporaryDirectory() as tmp:
            stub, path, backup = make_stub(tmp)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(CORRUPT)
            stub._backup_script_groups_once(path)
            self.assertIs(stub._script_groups_backup_done, True)
            self.assertFalse(os.path.exists(backup))

    def test_copies_readable_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            stub, path, backup = make_stub(tmp)
            write_groups(path, "G1")
            stub._backup_script_groups_once(path)
            self.assertEqual(read(backup), read(path))
            self.assertIs(stub._script_groups_backup_done, True)

    def test_is_readable_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            good = os.path.join(tmp, "good.json")
            bad = os.path.join(tmp, "bad.json")
            empty = os.path.join(tmp, "empty.json")
            write_groups(good, "G1")
            with open(bad, "w", encoding="utf-8") as fh:
                fh.write(CORRUPT)
            open(empty, "w", encoding="utf-8").close()
            self.assertIs(app.DatabaseConnectorGUI._is_readable_json(good), True)
            self.assertIs(app.DatabaseConnectorGUI._is_readable_json(bad), False)
            self.assertIs(app.DatabaseConnectorGUI._is_readable_json(empty), False)
            self.assertIs(
                app.DatabaseConnectorGUI._is_readable_json(os.path.join(tmp, "missing.json")),
                False,
            )
            bad_bytes = os.path.join(tmp, "bytes.json")
            with open(bad_bytes, "wb") as fh:
                fh.write(b"\xff\xfe\x00\x81")
            self.assertIs(app.DatabaseConnectorGUI._is_readable_json(bad_bytes), False)

    def test_is_readable_json_raises_on_locked_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            good = os.path.join(tmp, "good.json")
            write_groups(good, "G1")
            for exc in (PermissionError(13, "locked"), OSError(5, "I/O error")):
                with self.subTest(exc=type(exc).__name__):
                    with mock.patch("builtins.open", side_effect=exc):
                        with self.assertRaises(type(exc)):
                            app.DatabaseConnectorGUI._is_readable_json(good)


if __name__ == "__main__":
    unittest.main()
