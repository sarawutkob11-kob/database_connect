"""R8-T2: load_jobs must keep the jobs when the migration write-back fails.

R8-AC-1 .. R8-AC-14 (Round 8 / Bugfix B1). No Tk window, files only inside
TemporaryDirectory, messagebox always patched. Every test that makes the app
print patches sys.stdout, so nothing outside cp874 reaches the real console
(R8-AC-15 mode b).
"""

import copy
import io
import json
import os
import sys
import tempfile
import unittest
from typing import Any, Callable, Dict, List, Optional, Tuple
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import database_connect_gui as app  # noqa: E402

GUI = app.DatabaseConnectorGUI

PROFILES = {"P1": {"db_type": "Oracle"}, "P2": {"db_type": "SQLite"}}

# "Old" file: one job without "profile", one with "P2", nested values and Thai.
LEGACY_JOBS: List[Dict[str, Any]] = [
    {
        "name": "งานเก่า",
        "query": "SELECT * FROM ลูกค้า WHERE id = 1",
        "excel_parameters": {"WHERE acc_no": ["AUTO_WHERE", "'A', 'B'"]},
        "tags": ["ไทย", 1, None, {"k": [1, 2]}],
    },
    {
        "name": "job-p2",
        "profile": "P2",
        "query": "SELECT 1",
        "options": {"nested": {"deep": ["x", "ข"]}},
    },
    {
        "name": "third-no-profile",
        "query": "DELETE FROM t",
    },
]

FAIL_MODES = ("replace", "atomic")  # (a) os.replace raises / (b) write_json_atomic raises


def expected_jobs(first_profile: str) -> List[Dict[str, Any]]:
    jobs = copy.deepcopy(LEGACY_JOBS)
    for job in jobs:
        job.setdefault("profile", first_profile)
    return jobs


def make_stub(tmp: str, profiles: Optional[dict] = None) -> Any:
    stub = GUI.__new__(GUI)
    stub.jobs_file = os.path.join(tmp, "saved_jobs.json")
    stub.saved_profiles = copy.deepcopy(PROFILES if profiles is None else profiles)
    stub._jobs_save_blocked = False
    return stub


def write_bytes(path: str, data: bytes) -> bytes:
    with open(path, "wb") as fh:
        fh.write(data)
    return data


def write_legacy(path: str) -> bytes:
    return write_bytes(path, json.dumps(LEGACY_JOBS, ensure_ascii=False, indent=2).encode("utf-8"))


def read_bytes(path: str) -> bytes:
    with open(path, "rb") as fh:
        return fh.read()


def cp874_stdout() -> io.TextIOWrapper:
    return io.TextIOWrapper(io.BytesIO(), encoding="cp874", errors="strict")


class _ClosedPipe:
    """A stdout whose write raises OSError (e.g. closed pipe)."""

    encoding = "utf-8"

    def write(self, _text: str) -> int:
        raise OSError(32, "Broken pipe")

    def flush(self) -> None:
        raise OSError(32, "Broken pipe")


def failure_patch(mode: str, error: BaseException) -> Any:
    """mock.patch that makes the write-back fail: (a) os.replace / (b) write_json_atomic."""
    if mode == "replace":
        return mock.patch.object(app.os, "replace", side_effect=error)
    return mock.patch.object(app, "write_json_atomic", side_effect=error)


_REAL_OPEN = open


def _open_except_tmp() -> Callable[..., Any]:
    """`open` that refuses only *.tmp paths (a .tmp locked by another program)."""
    def fake_open(path: Any, *args: Any, **kwargs: Any) -> Any:
        if str(path).endswith(".tmp"):
            raise PermissionError(13, "tmp is locked")
        return _REAL_OPEN(path, *args, **kwargs)
    return fake_open


def assert_no_dialog(tc: unittest.TestCase, mb: mock.MagicMock) -> None:
    mb.showwarning.assert_not_called()
    mb.showerror.assert_not_called()
    mb.showinfo.assert_not_called()


class WriteBackFailureTests(unittest.TestCase):
    """R8-AC-1 .. R8-AC-7."""

    def _run_failing_load(
        self,
        mode: str,
        profiles: Optional[dict] = None,
        stdout: Optional[Any] = None,
        error: Optional[BaseException] = None,
    ) -> Tuple[Any, ...]:
        """Returns (result, stub, tmp listing, bytes before, bytes after, stdout, mb, handle spy)."""
        if error is None:
            error = PermissionError(13, "file is locked by OneDrive") if mode == "replace" \
                else OSError(28, "No space left on device")
        out = io.StringIO() if stdout is None else stdout
        with tempfile.TemporaryDirectory() as tmp:
            stub = make_stub(tmp, profiles)
            before = write_legacy(stub.jobs_file)
            with mock.patch.object(app, "messagebox") as mb, \
                    mock.patch.object(GUI, "_handle_unreadable_file") as handle, \
                    mock.patch("sys.stdout", out), \
                    failure_patch(mode, error):
                result = stub.load_jobs()
            listing = sorted(os.listdir(tmp))
            after = read_bytes(stub.jobs_file)
        return result, stub, listing, before, after, out, mb, handle, error

    def _assert_ac1_to_5(
        self,
        result: List[Dict[str, Any]],
        stub: Any,
        listing: List[str],
        before: bytes,
        after: bytes,
        mb: mock.MagicMock,
        handle: mock.MagicMock,
        first_profile: str = "P1",
    ) -> None:
        # AC-1 / AC-2: all jobs, same order and values, missing profile filled
        self.assertEqual(result, expected_jobs(first_profile))
        self.assertEqual([j["name"] for j in result], [j["name"] for j in LEGACY_JOBS])
        self.assertEqual(result[1]["profile"], "P2")
        # AC-3
        assert_no_dialog(self, mb)
        handle.assert_not_called()
        # AC-4
        self.assertFalse([n for n in listing if "_unreadable_" in n], listing)
        self.assertIs(stub._jobs_save_blocked, False)
        # AC-5
        self.assertEqual(after, before)
        self.assertNotIn(b'"profile": "P1"', after)

    def test_ac1_ac3_ac4_ac5_both_failure_modes(self):
        for mode in FAIL_MODES:
            with self.subTest(mode=mode):
                result, stub, listing, before, after, _out, mb, handle, _e = \
                    self._run_failing_load(mode)
                self._assert_ac1_to_5(result, stub, listing, before, after, mb, handle)

    def test_ac2_no_profiles_gives_default(self):
        for mode in FAIL_MODES:
            with self.subTest(mode=mode):
                result, stub, listing, before, after, _out, mb, handle, _e = \
                    self._run_failing_load(mode, profiles={})
                self._assert_ac1_to_5(result, stub, listing, before, after, mb, handle,
                                      first_profile="DEFAULT")
                self.assertEqual(result[0]["profile"], "DEFAULT")
                self.assertEqual(result[2]["profile"], "DEFAULT")

    def test_ac1_first_profile_follows_dict_order(self):
        result, *_ = self._run_failing_load("replace", profiles={"P2": {}, "P1": {}})
        self.assertEqual(result[0]["profile"], "P2")
        self.assertEqual(result[2]["profile"], "P2")

    def test_ac6_tmp_removed_after_replace_failure(self):
        result, _stub, listing, *_ = self._run_failing_load("replace")
        self.assertEqual(result, expected_jobs("P1"))
        self.assertEqual(listing, ["saved_jobs.json"])
        self.assertNotIn("saved_jobs.json.tmp", listing)

    def test_ac6_atomic_failure_without_tmp_is_fine(self):
        # (b) fails before the .tmp exists: os.remove -> FileNotFoundError, swallowed
        result, _stub, listing, *_ = self._run_failing_load("atomic")
        self.assertEqual(result, expected_jobs("P1"))
        self.assertEqual(listing, ["saved_jobs.json"])

    def test_ac6_remove_tmp_uses_jobs_file_tmp_path(self):
        # write_json_atomic removes the .tmp it opened (replace failed)
        with tempfile.TemporaryDirectory() as tmp:
            stub = make_stub(tmp)
            write_legacy(stub.jobs_file)
            with mock.patch.object(app, "messagebox"), \
                    mock.patch("sys.stdout", io.StringIO()), \
                    failure_patch("replace", OSError("x")), \
                    mock.patch.object(app.os, "remove") as remove:
                stub.load_jobs()
            remove.assert_called_once_with(f"{stub.jobs_file}.tmp")

    def test_ac6_tmp_not_created_by_this_call_is_left_alone(self):
        # (b) write_json_atomic fails before opening the .tmp: an existing
        # .tmp (e.g. held by OneDrive) belongs to someone else - no delete
        for case in ("atomic_raises", "open_fails"):
            with self.subTest(case=case):
                with tempfile.TemporaryDirectory() as tmp:
                    stub = make_stub(tmp)
                    write_legacy(stub.jobs_file)
                    other_tmp = write_bytes(f"{stub.jobs_file}.tmp", b"not ours")
                    if case == "atomic_raises":
                        failing = failure_patch("atomic", OSError("x"))
                    else:
                        failing = mock.patch("builtins.open", side_effect=_open_except_tmp())
                    with mock.patch.object(app, "messagebox"), \
                            mock.patch("sys.stdout", io.StringIO()), failing, \
                            mock.patch.object(app.os, "remove") as remove:
                        result = stub.load_jobs()
                    self.assertEqual(result, expected_jobs("P1"))
                    remove.assert_not_called()
                    self.assertEqual(read_bytes(f"{stub.jobs_file}.tmp"), other_tmp)

    def test_ac6_remove_raises_still_returns_jobs_and_prints(self):
        for mode in FAIL_MODES:
            with self.subTest(mode=mode):
                out = io.StringIO()
                with tempfile.TemporaryDirectory() as tmp:
                    stub = make_stub(tmp)
                    before = write_legacy(stub.jobs_file)
                    # os.remove patch ends before TemporaryDirectory cleanup (R8-R6)
                    with mock.patch.object(app, "messagebox") as mb, \
                            mock.patch.object(GUI, "_handle_unreadable_file") as handle, \
                            mock.patch("sys.stdout", out), \
                            failure_patch(mode, PermissionError(13, "locked")), \
                            mock.patch.object(app.os, "remove",
                                              side_effect=OSError(5, "Access is denied")) as remove:
                        result = stub.load_jobs()
                    if mode == "replace":
                        remove.assert_called_once_with(f"{stub.jobs_file}.tmp")
                    else:
                        remove.assert_not_called()  # no .tmp was opened by this call
                    listing = sorted(os.listdir(tmp))
                    after = read_bytes(stub.jobs_file)
                self._assert_ac1_to_5(result, stub, listing, before, after, mb, handle)
                lines = [ln for ln in out.getvalue().splitlines() if ln.strip()]
                self.assertEqual(len(lines), 1, lines)
                self.assertIn("saved_jobs.json", lines[0])
                self.assertIn("locked", lines[0])
                if mode == "replace":
                    # .tmp could not be removed -> it is left, nothing else
                    self.assertEqual(listing, ["saved_jobs.json", "saved_jobs.json.tmp"])

    def test_ac7_one_log_line_with_file_and_error(self):
        for mode in FAIL_MODES:
            with self.subTest(mode=mode):
                result, stub, _l, _b, _a, out, _mb, _h, error = self._run_failing_load(mode)
                self.assertEqual(result, expected_jobs("P1"))
                lines = [ln for ln in out.getvalue().splitlines() if ln.strip()]
                self.assertEqual(len(lines), 1, lines)
                self.assertIn("saved_jobs.json", lines[0])
                self.assertIn(str(error), lines[0])
                self.assertIn(stub.jobs_file, lines[0])
                self.assertNotIn("Error loading jobs", out.getvalue())

    def test_ac7_cp874_console_cannot_encode_message(self):
        error_text = "locked \U0001F512 by sync ❌"
        # precondition: this message really cannot be printed on cp874
        probe = cp874_stdout()
        with self.assertRaises(UnicodeEncodeError):
            print(f"Cannot write migrated jobs back to x: {error_text}", file=probe)
        for mode in FAIL_MODES:
            with self.subTest(mode=mode):
                error = PermissionError(13, error_text) if mode == "replace" else OSError(error_text)
                result, stub, listing, before, after, out, mb, handle, _e = \
                    self._run_failing_load(mode, stdout=cp874_stdout(), error=error)
                self._assert_ac1_to_5(result, stub, listing, before, after, mb, handle)
                self.assertNotIn("saved_jobs.json.tmp", listing)

    def test_ac7_stdout_write_raises_oserror(self):
        for mode in FAIL_MODES:
            with self.subTest(mode=mode):
                result, stub, listing, before, after, _out, mb, handle, _e = \
                    self._run_failing_load(mode, stdout=_ClosedPipe())
                self._assert_ac1_to_5(result, stub, listing, before, after, mb, handle)
                self.assertNotIn("saved_jobs.json.tmp", listing)

    def test_ac7_stdout_none(self):
        # sys.stdout really None (pythonw): print raises AttributeError, swallowed
        for mode in FAIL_MODES:
            with self.subTest(mode=mode):
                with tempfile.TemporaryDirectory() as tmp:
                    stub = make_stub(tmp)
                    write_legacy(stub.jobs_file)
                    with mock.patch.object(app, "messagebox"), \
                            mock.patch("sys.stdout", None), \
                            failure_patch(mode, OSError("x")):
                        self.assertEqual(stub.load_jobs(), expected_jobs("P1"))

    def test_base_exception_not_swallowed(self):
        # write-back guard catches Exception only (R8-D2)
        with tempfile.TemporaryDirectory() as tmp:
            stub = make_stub(tmp)
            write_legacy(stub.jobs_file)
            with mock.patch.object(app, "messagebox"), mock.patch("sys.stdout", io.StringIO()), \
                    failure_patch("atomic", KeyboardInterrupt()):
                with self.assertRaises(KeyboardInterrupt):
                    stub.load_jobs()


class NextSaveTests(unittest.TestCase):
    """R8-AC-8 / R8-AC-9."""

    def test_ac8_ac9_next_save_keeps_old_jobs(self):
        for mode in FAIL_MODES:
            with self.subTest(mode=mode):
                with tempfile.TemporaryDirectory() as tmp:
                    stub = make_stub(tmp)
                    write_legacy(stub.jobs_file)
                    error = PermissionError(13, "locked") if mode == "replace" else OSError("x")
                    with mock.patch.object(app, "messagebox"), \
                            mock.patch("sys.stdout", io.StringIO()), \
                            failure_patch(mode, error):
                        loaded = stub.load_jobs()
                    # patch released
                    stub.saved_jobs = loaded
                    new_job = {"name": "NEW", "profile": "P1", "query": "SELECT 2"}
                    stub.saved_jobs.append(new_job)
                    with mock.patch.object(app, "messagebox") as mb:
                        self.assertIs(stub.save_jobs(), True)
                    mb.showerror.assert_not_called()
                    with open(stub.jobs_file, encoding="utf-8") as fh:
                        on_disk = json.load(fh)
                    self.assertEqual(on_disk, expected_jobs("P1") + [new_job])
                    self.assertEqual(len(on_disk), 4)

                    # AC-9: reload -> nothing to migrate -> no write
                    bytes_before = read_bytes(stub.jobs_file)
                    with mock.patch.object(app, "messagebox") as mb2, \
                            mock.patch.object(app, "write_json_atomic",
                                              wraps=app.write_json_atomic) as spy:
                        again = stub.load_jobs()
                    spy.assert_not_called()
                    assert_no_dialog(self, mb2)
                    self.assertEqual(again, on_disk)
                    self.assertEqual(read_bytes(stub.jobs_file), bytes_before)
                    self.assertEqual(sorted(os.listdir(tmp)), ["saved_jobs.json"])


class RegressionLockTests(unittest.TestCase):
    """R8-AC-10 .. R8-AC-14."""

    def test_ac10_successful_write_back(self):
        out = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp:
            stub = make_stub(tmp)
            write_legacy(stub.jobs_file)
            with mock.patch.object(app, "messagebox") as mb, \
                    mock.patch.object(GUI, "_handle_unreadable_file") as handle, \
                    mock.patch("sys.stdout", out), \
                    mock.patch.object(app, "write_json_atomic",
                                      wraps=app.write_json_atomic) as spy:
                result = stub.load_jobs()
            expected = expected_jobs("P1")
            self.assertEqual(result, expected)
            spy.assert_called_once_with(stub.jobs_file, result, indent=4)
            with open(stub.jobs_file, encoding="utf-8") as fh:
                text = fh.read()
            self.assertEqual(json.loads(text), result)
            self.assertEqual(text, json.dumps(expected, indent=4, ensure_ascii=False))
            self.assertEqual(sorted(os.listdir(tmp)), ["saved_jobs.json"])
            assert_no_dialog(self, mb)
            handle.assert_not_called()
            self.assertIs(stub._jobs_save_blocked, False)
            self.assertEqual(out.getvalue(), "")

    def test_ac11_no_migration_no_write(self):
        cases = {
            "all_have_profile": json.dumps(expected_jobs("P1"), ensure_ascii=False).encode("utf-8"),
            "empty_list": b"[]",
        }
        for label, data in cases.items():
            with self.subTest(case=label):
                out = io.StringIO()
                with tempfile.TemporaryDirectory() as tmp:
                    stub = make_stub(tmp)
                    write_bytes(stub.jobs_file, data)
                    old_ns = 1_500_000_000_000_000_000
                    os.utime(stub.jobs_file, ns=(old_ns, old_ns))
                    with mock.patch.object(app, "messagebox") as mb, \
                            mock.patch("sys.stdout", out), \
                            mock.patch.object(app, "write_json_atomic",
                                              wraps=app.write_json_atomic) as spy:
                        result = stub.load_jobs()
                    spy.assert_not_called()
                    self.assertEqual(result, json.loads(data.decode("utf-8")))
                    self.assertEqual(read_bytes(stub.jobs_file), data)
                    self.assertEqual(os.stat(stub.jobs_file).st_mtime_ns, old_ns)
                    self.assertEqual(sorted(os.listdir(tmp)), ["saved_jobs.json"])
                    assert_no_dialog(self, mb)
                    self.assertEqual(out.getvalue(), "")

    def test_ac12_unreadable_files_unchanged_behaviour(self):
        cases = {
            "broken_json": b'[{"name": "a",',
            "not_list": b"{}",
            "non_dict_member": b"[1]",
            "bad_utf8": b"\xff\xfe\x00",
        }
        for label, data in cases.items():
            with self.subTest(case=label):
                out = io.StringIO()
                with tempfile.TemporaryDirectory() as tmp:
                    stub = make_stub(tmp)
                    write_bytes(stub.jobs_file, data)
                    with mock.patch.object(app, "messagebox") as mb, \
                            mock.patch("sys.stdout", out), \
                            mock.patch.object(app, "write_json_atomic",
                                              wraps=app.write_json_atomic) as spy:
                        result = stub.load_jobs()
                    self.assertEqual(result, [])
                    spy.assert_not_called()
                    mb.showwarning.assert_called_once()
                    title, message = mb.showwarning.call_args[0]
                    self.assertEqual(title, "Saved Jobs not loaded")
                    self.assertTrue(message.startswith("Cannot read saved_jobs.json:"), message)
                    mb.showerror.assert_not_called()
                    mb.showinfo.assert_not_called()
                    copies = [n for n in os.listdir(tmp)
                              if n.startswith("saved_jobs_unreadable_") and n.endswith(".json")]
                    self.assertEqual(len(copies), 1, os.listdir(tmp))
                    self.assertEqual(read_bytes(os.path.join(tmp, copies[0])), data)
                    self.assertIs(stub._jobs_save_blocked, False)
                    self.assertEqual(read_bytes(stub.jobs_file), data)
                    self.assertNotIn(".tmp", "".join(os.listdir(tmp)))
                    self.assertIn("Error loading jobs", out.getvalue())
                    self.assertNotIn("Cannot write migrated jobs back", out.getvalue())

    def test_ac13_unreadable_and_no_copy_blocks_save(self):
        data = b'[{"name": "a",'
        with tempfile.TemporaryDirectory() as tmp:
            stub = make_stub(tmp)
            write_bytes(stub.jobs_file, data)
            with mock.patch.object(app, "messagebox"), \
                    mock.patch("sys.stdout", io.StringIO()), \
                    mock.patch.object(app, "preserve_unreadable_file", return_value=None):
                result = stub.load_jobs()
            self.assertEqual(result, [])
            self.assertIs(stub._jobs_save_blocked, True)
            stub.saved_jobs = [{"name": "NEW", "profile": "P1"}]
            with mock.patch.object(app, "messagebox") as mb:
                self.assertIs(stub.save_jobs(), False)
            mb.showerror.assert_called_once()
            self.assertEqual(read_bytes(stub.jobs_file), data)
            self.assertEqual(sorted(os.listdir(tmp)), ["saved_jobs.json"])

    def test_ac14_missing_file(self):
        out = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp:
            stub = make_stub(tmp)
            with mock.patch.object(app, "messagebox") as mb, \
                    mock.patch("sys.stdout", out), \
                    mock.patch.object(app, "write_json_atomic",
                                      wraps=app.write_json_atomic) as spy:
                result = stub.load_jobs()
            self.assertEqual(result, [])
            spy.assert_not_called()
            assert_no_dialog(self, mb)
            self.assertEqual(os.listdir(tmp), [])
            self.assertIs(stub._jobs_save_blocked, False)
            self.assertEqual(out.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
