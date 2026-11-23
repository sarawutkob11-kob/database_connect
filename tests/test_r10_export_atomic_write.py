"""R10-T2: Export Excel writes a temp file and replaces the target only on success (B3).

Covers R10-AC-1 .. R10-AC-19 (R10-AC-20 is the focused run of the older tests).

Every file lives in a tempfile.TemporaryDirectory(); no database, no real Tk.
Nothing is printed to the real stdout. Assertions on the Execution Logs (which
contain emoji / Thai) use assertTrue with an ASCII-only message.
"""

import builtins
import ctypes
import os
import queue
import re
import stat
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest import mock

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(TESTS_DIR))
if TESTS_DIR not in sys.path:
    sys.path.append(TESTS_DIR)

import numpy as np  # noqa: E402
from openpyxl import Workbook, load_workbook  # noqa: E402
from openpyxl.workbook.workbook import Workbook as _OpenpyxlWorkbook  # noqa: E402

import database_connect_gui as app  # noqa: E402
import test_r7_excel_cell_limit as r7  # noqa: E402  (module only: its classes are not re-collected)

APP_DIR = os.path.dirname(os.path.abspath(app.__file__))
REAL_REPLACE = os.replace
REAL_REMOVE = os.remove
REAL_OS_OPEN = os.open
REAL_OPEN = builtins.open
TEMP_RE = re.compile(r"^export\..+\.tmp\.xlsx$")
STANDARD_SHEETS = ["Success job", "No data job", "Skipped job", "Failed job"]


# ------------------------------------------------------------------ fakes
class _FakeText:
    def __init__(self):
        self.inserted = []

    def delete(self, *_args):
        pass

    def insert(self, _index, value):
        self.inserted.append(value)

    def see(self, _index):
        pass


class _FakeButton:
    def config(self, **_kwargs):
        pass


class _ImmediateThread:
    def __init__(self, target, daemon=None):
        self.target = target
        self.daemon = daemon

    def start(self):
        self.target()


# ---------------------------------------------------------------- helpers
def read_bytes(path):
    with REAL_OPEN(path, "rb") as handle:
        return handle.read()


def make_old_workbook(path):
    """The user's existing report: sheet 'Old' with values we can recognise."""
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Old"
    sheet["A1"] = "old-value"
    sheet["B2"] = 12345
    workbook.save(path)
    return read_bytes(path)


def workbook_cells(path):
    """[(sheet, [(coordinate, value, data_type), ...]), ...] read with openpyxl."""
    workbook = load_workbook(path)
    try:
        return [
            (
                ws.title,
                [(c.coordinate, c.value, c.data_type) for row in ws.iter_rows() for c in row],
            )
            for ws in workbook.worksheets
        ]
    finally:
        workbook.close()


def sheet_names(path):
    workbook = load_workbook(path)
    try:
        return list(workbook.sheetnames)
    finally:
        workbook.close()


def same_path(candidate, target):
    if not isinstance(candidate, (str, bytes, os.PathLike)):
        return False
    try:
        candidate = os.fsdecode(os.fspath(candidate))
    except TypeError:
        return False
    return os.path.normcase(os.path.abspath(candidate)) == os.path.normcase(
        os.path.abspath(target)
    )


def standard_jobs():
    return [
        {"name": "Success job", "query": "SELECT id, name FROM data_table"},
        {"name": "No data job", "query": "SELECT id FROM empty_table"},
        {"name": "Skipped job", "query": "UPDATE t SET c = 1"},
        {"name": "Failed job", "query": "SELECT * FROM broken_table"},
    ]


def standard_query(query):
    if "data_table" in query:
        return app.pd.DataFrame({"id": [1, 2], "name": ["alpha", "=1+1"]})
    if "empty_table" in query:
        return app.pd.DataFrame(columns=["id"])
    if "broken_table" in query:
        raise RuntimeError("table is broken")
    return app.pd.DataFrame({"v": [query[-1:]]})


def _windows_lock_api():
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)  # private instance
    create = kernel32.CreateFileW
    create.argtypes = [
        wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
        wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
    ]
    create.restype = wintypes.HANDLE
    close = kernel32.CloseHandle
    close.argtypes = [wintypes.HANDLE]
    close.restype = wintypes.BOOL
    return create, close


# ------------------------------------------------------------------- base
class _R10Case(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.use_folder(self._tmp.name)
        self.stop_event = threading.Event()
        self.on_query = standard_query
        self.read_sql_calls = []
        self.replace_calls = []
        self.target_bytes_at_replace = []
        self.replace_error = None
        self.messagebox = None
        self.output = ""
        self.thread_cls = None
        # same number of retries, no waiting
        delays = mock.patch.object(app, "EXPORT_REPLACE_RETRY_DELAYS",
                                   (0.0,) * len(app.EXPORT_REPLACE_RETRY_DELAYS))
        delays.start()
        self.addCleanup(delays.stop)

    # ---- folder / files
    def use_folder(self, folder):
        os.makedirs(folder, exist_ok=True)
        self.folder = folder
        self.export_path = os.path.join(folder, "export.xlsx")

    def new_subfolder(self, name):
        self.use_folder(os.path.join(self._tmp.name, name))

    def make_old_file(self):
        self.old_bytes = make_old_workbook(self.export_path)
        self.before_names = set(os.listdir(self.folder))
        return self.old_bytes

    def listing(self):
        return set(os.listdir(self.folder))

    def new_names(self):
        return self.listing() - self.before_names

    # ---- stub
    def _read_sql(self, query, engine=None):
        self.read_sql_calls.append(query)
        return self.on_query(query)

    def _replace(self, src, dst, *args, **kwargs):
        self.replace_calls.append((src, dst))
        self.target_bytes_at_replace.append(
            read_bytes(dst) if os.path.exists(dst) else None
        )
        if self.replace_error is not None:
            raise self.replace_error
        return REAL_REPLACE(src, dst, *args, **kwargs)

    def make_stub(self):
        stub = app.DatabaseConnectorGUI.__new__(app.DatabaseConnectorGUI)
        stub._block_if_busy = mock.Mock(return_value=False)
        stub._block_if_profile_mismatch = mock.Mock(return_value=False)
        stub._capture_run_target = mock.Mock(return_value=app.RunTarget(mock.Mock(), None))
        stub._reuse_last_run_results = mock.Mock(
            side_effect=lambda items: [dict(item) for item in items]
        )
        stub._start_stoppable_run = mock.Mock()
        stub._stop_event = self.stop_event
        stub.engine = mock.Mock()
        stub.results_text = _FakeText()
        stub.export_excel_btn = _FakeButton()
        stub.root = mock.Mock()
        stub.root.after.side_effect = lambda _delay, callback: callback()
        stub.read_sql_dataframe = self._read_sql
        return stub

    def run_export(self, jobs, extra_patches=(), save_path=None):
        stub = self.make_stub()
        self.stub = stub
        path = self.export_path if save_path is None else save_path
        patches = [
            mock.patch.object(app.filedialog, "asksaveasfilename", return_value=path),
            mock.patch.object(app.threading, "Thread", _ImmediateThread),
            mock.patch.object(app, "messagebox"),
            mock.patch.object(app.os, "replace", side_effect=self._replace),
        ] + list(extra_patches)
        started = []
        try:
            for patcher in patches:
                started.append(patcher.start())
            self.messagebox = started[2]
            stub.export_jobs_to_excel(jobs_override=jobs)
        finally:
            for patcher in reversed(patches[: len(started)]):
                patcher.stop()
            self.output = "".join(stub.results_text.inserted)

    # ---- assertions
    def assert_output_has(self, text):
        self.assertTrue(text in self.output, f"Execution Logs lack {ascii(text)}")

    def assert_output_lacks(self, text):
        self.assertFalse(text in self.output, f"Execution Logs contain {ascii(text)}")

    def assert_target_unchanged(self):
        self.assertTrue(os.path.exists(self.export_path), "the old file is gone")
        current = read_bytes(self.export_path)
        self.assertTrue(
            current == self.old_bytes,
            f"old file changed: {len(self.old_bytes)} -> {len(current)} bytes",
        )
        self.assertEqual(sheet_names(self.export_path), ["Old"])

    def assert_no_temp_left(self, expected_new=()):
        self.assertEqual(self.new_names(), set(expected_new))

    def assert_one_error(self, *fragments, absent=()):
        mb = self.messagebox
        self.assertEqual(mb.showerror.call_count, 1, "showerror must be shown once")
        title, message = mb.showerror.call_args[0][:2]
        self.assertEqual(title, "Export Error")
        for fragment in fragments:
            self.assertTrue(fragment in message, f"dialog lacks {ascii(fragment)}: {ascii(message)}")
            self.assert_output_has(fragment)
        for fragment in absent:
            self.assertFalse(fragment in message, f"dialog has {ascii(fragment)}: {ascii(message)}")
            self.assert_output_lacks(fragment)
        mb.showinfo.assert_not_called()
        self.assert_output_has("EXPORT EXCEL FAILED")
        self.assertEqual(self.output.count("EXPORT EXCEL FAILED"), 1, "on_done ran once")
        return message

    def assert_success_dialog(self):
        mb = self.messagebox
        mb.showerror.assert_not_called()
        self.assertEqual(mb.showinfo.call_count, 1)
        self.assertEqual(mb.showinfo.call_args[0][0], "Export Success")
        self.assert_output_lacks("EXPORT EXCEL FAILED")

    def counts(self):
        found = {}
        for label, pattern in (
            ("ok", r"Success: (\d+)\n"),
            ("warnings", r"Warning: (\d+)\n"),
            ("failed", r"Failed: (\d+)\n"),
            ("skipped", r"Skipped \(not SELECT\): (\d+)\n"),
        ):
            matches = re.findall(pattern, self.output)
            self.assertEqual(len(matches), 1, f"summary line for {label}")
            found[label] = int(matches[0])
        return found


# ------------------------------------------- old file untouched (R10-AC-1..4)
class OldFileUntouchedDuringExportTests(_R10Case):
    def test_ac1_old_file_intact_whenever_a_query_runs(self):
        self.make_old_file()
        seen = []

        def query(sql):
            seen.append(read_bytes(self.export_path))
            return standard_query(sql)

        self.on_query = query
        self.run_export(standard_jobs())

        self.assertEqual(len(seen), 3)  # data, empty, broken (Skipped is not run)
        for index, content in enumerate(seen, 1):
            self.assertTrue(
                content == self.old_bytes,
                f"query #{index}: target was {len(content)} bytes, "
                f"expected the old {len(self.old_bytes)} bytes",
            )
        self.assert_success_dialog()

    def test_ac2_written_to_a_temp_file_then_replaced_once(self):
        self.make_old_file()
        target_writes = []

        def open_spy(file, mode="r", *args, **kwargs):
            if same_path(file, self.export_path) and any(c in mode for c in "wax+"):
                target_writes.append(("open", mode))
            return REAL_OPEN(file, mode, *args, **kwargs)

        write_flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_APPEND

        def os_open_spy(path, flags, *args, **kwargs):
            if same_path(path, self.export_path) and flags & write_flags:
                target_writes.append(("os.open", flags))
            return REAL_OS_OPEN(path, flags, *args, **kwargs)

        writer_spy = mock.MagicMock(wraps=app.pd.ExcelWriter)
        self.run_export(
            standard_jobs(),
            extra_patches=[
                mock.patch.object(builtins, "open", side_effect=open_spy),
                mock.patch.object(app.os, "open", side_effect=os_open_spy),
                mock.patch.object(app.pd, "ExcelWriter", writer_spy),
            ],
        )

        self.assertEqual(target_writes, [], "target opened to create / truncate / write")
        self.assertEqual(writer_spy.call_count, 1)
        first_arg = writer_spy.call_args[0][0]
        self.assertFalse(same_path(first_arg, self.export_path),
                         "ExcelWriter received the target path")
        self.assertEqual(writer_spy.call_args[1].get("engine"), "openpyxl")

        self.assertEqual(len(self.replace_calls), 1)
        src, dst = self.replace_calls[0]
        self.assertTrue(same_path(dst, self.export_path))
        self.assertEqual(os.path.normcase(os.path.dirname(os.path.abspath(src))),
                         os.path.normcase(os.path.abspath(self.folder)))
        self.assertRegex(os.path.basename(src), TEMP_RE)  # R10-Q-1, no "~$" prefix
        self.assertTrue(self.target_bytes_at_replace[0] == self.old_bytes,
                        "target changed before os.replace")
        self.assertEqual(sheet_names(self.export_path), STANDARD_SHEETS)
        self.assert_no_temp_left()
        self.assert_success_dialog()

    def test_ac3_existing_user_files_are_never_touched(self):
        user_files = {
            "export.tmp.xlsx": b"user file: export.tmp.xlsx",
            "export.xlsx.tmp": b"user file: export.xlsx.tmp",
            "export.12345678.tmp.xlsx": b"user file: random-looking temp name",
            "~$export.xlsx": b"user file: excel owner file",
            "notes.txt": b"keep me",
        }
        cases = (
            ("success", standard_jobs(), True),
            ("fatal_before_sheet", [{"name": "Broken job"}], False),
            ("fatal_after_sheet",
             [{"name": "Good", "query": "SELECT v FROM t1"}, {"name": "Broken job"}], False),
        )
        for label, jobs, succeeds in cases:
            with self.subTest(case=label):
                self.new_subfolder(label)
                for name, content in user_files.items():
                    with REAL_OPEN(os.path.join(self.folder, name), "wb") as handle:
                        handle.write(content)
                self.make_old_file()

                self.run_export(jobs)

                for name, content in user_files.items():
                    path = os.path.join(self.folder, name)
                    self.assertTrue(os.path.exists(path), f"{name} was deleted")
                    self.assertTrue(read_bytes(path) == content, f"{name} was changed")
                self.assert_no_temp_left()
                if succeeds:
                    self.assertEqual(sheet_names(self.export_path), STANDARD_SHEETS)
                    self.assert_success_dialog()
                else:
                    self.assert_target_unchanged()
                    self.assert_one_error("KeyError")

    def test_ac4_killed_process_leaves_the_old_file_intact(self):
        old_bytes = self.make_old_file()
        child_script = r'''
import sys, time
repo, export_path = sys.argv[1], sys.argv[2]
sys.path.insert(0, repo)
from unittest import mock
import database_connect_gui as app

class Text:
    def delete(self, *a): pass
    def insert(self, *a): pass
    def see(self, *a): pass

class Button:
    def config(self, **k): pass

class Thread:
    def __init__(self, target, daemon=None): self.target = target
    def start(self): self.target()

def read_sql(query, engine=None):
    if "second_table" in query:
        print("IN_QUERY", flush=True)
        time.sleep(300)
    return app.pd.DataFrame({"v": [1, 2, 3]})

stub = app.DatabaseConnectorGUI.__new__(app.DatabaseConnectorGUI)
stub._block_if_busy = mock.Mock(return_value=False)
stub._capture_run_target = mock.Mock(return_value=app.RunTarget(mock.Mock(), None))
stub._reuse_last_run_results = mock.Mock(side_effect=lambda items: [dict(i) for i in items])
stub._start_stoppable_run = mock.Mock()
stub._stop_event = mock.Mock(is_set=mock.Mock(return_value=False))
stub.engine = mock.Mock()
stub.results_text = Text()
stub.export_excel_btn = Button()
stub.root = mock.Mock()
stub.root.after.side_effect = lambda _d, cb: cb()
stub.read_sql_dataframe = read_sql
jobs = [{"name": "first", "query": "SELECT v FROM first_table"},
        {"name": "second", "query": "SELECT v FROM second_table"}]
with mock.patch.object(app.filedialog, "asksaveasfilename", return_value=export_path), \
        mock.patch.object(app.threading, "Thread", Thread), \
        mock.patch.object(app, "messagebox"):
    stub.export_jobs_to_excel(jobs_override=jobs)
print("FINISHED", flush=True)
'''
        log_dir = tempfile.TemporaryDirectory()
        self.addCleanup(log_dir.cleanup)
        stderr_path = os.path.join(log_dir.name, "child_stderr.txt")
        env = dict(os.environ, PYTHONIOENCODING="utf-8")
        with REAL_OPEN(stderr_path, "wb") as stderr_file:
            child = subprocess.Popen(
                [sys.executable, "-c", child_script, APP_DIR, self.export_path],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=stderr_file,
                cwd=log_dir.name,
                env=env,
            )
        try:
            lines = queue.Queue()

            def pump():
                for raw in iter(child.stdout.readline, b""):
                    lines.put(raw.strip())
                lines.put(None)

            threading.Thread(target=pump, daemon=True).start()
            reached = False
            while True:
                try:
                    line = lines.get(timeout=120)
                except queue.Empty:
                    break
                if line is None or line == b"FINISHED":
                    break
                if line == b"IN_QUERY":
                    reached = True
                    break
            if not reached:
                child.kill()
                child.wait(timeout=30)
                err = read_bytes(stderr_path).decode("utf-8", "replace")[-2000:]
                self.fail(f"child never reached the second query; stderr: {ascii(err)}")

            during = read_bytes(self.export_path)
            child.kill()
            child.wait(timeout=30)
        finally:
            if child.poll() is None:
                child.kill()
                child.wait(timeout=30)
            child.stdout.close()

        self.assertTrue(during == old_bytes,
                        f"while exporting the target was {len(during)} bytes")
        self.assertTrue(os.path.exists(self.export_path), "the old file is gone")
        after = read_bytes(self.export_path)
        self.assertTrue(after == old_bytes,
                        f"after kill the target was {len(after)} bytes, expected {len(old_bytes)}")
        self.assertEqual(sheet_names(self.export_path), ["Old"])
        # a leftover temp file is allowed here (R10-Q-6)


# ----------------------------------------------- successful export (R10-AC-5..8)
class SuccessfulExportTests(_R10Case):
    def test_ac5_result_matches_an_export_to_a_new_path(self):
        self.make_old_file()
        self.run_export(standard_jobs())
        self.assert_success_dialog()
        self.assertEqual(
            self.counts(), {"ok": 2, "warnings": 0, "failed": 1, "skipped": 1}
        )
        self.assert_no_temp_left()
        over_old = workbook_cells(self.export_path)

        fresh_folder = os.path.join(self._tmp.name, "fresh")
        os.makedirs(fresh_folder)
        fresh_path = os.path.join(fresh_folder, "export.xlsx")
        self.run_export(standard_jobs(), save_path=fresh_path)
        self.assert_success_dialog()
        self.assertEqual(os.listdir(fresh_folder), ["export.xlsx"])
        fresh = workbook_cells(fresh_path)

        self.assertEqual([name for name, _ in over_old], STANDARD_SHEETS)
        self.assertTrue(over_old == fresh, "workbook over the old file differs from a fresh export")
        all_values = [value for _, cells in over_old for _, value, _ in cells]
        self.assertNotIn("old-value", all_values)
        self.assertNotIn(12345, all_values)
        # literal strings and the SQL annotation are kept
        cells = dict((coord, (value, kind)) for coord, value, kind in over_old[0][1])
        self.assertEqual(cells["B3"], ("=1+1", "s"))
        self.assertEqual(cells["A5"], ("SELECT id, name FROM data_table", "s"))
        no_data = dict((coord, (value, kind)) for coord, value, kind in over_old[1][1])
        self.assertEqual(no_data["A3"], ("SELECT id FROM empty_table", "s"))

    def test_ac6_new_target_is_created_without_leftovers(self):
        self.before_names = self.listing()
        self.assertFalse(os.path.exists(self.export_path))

        self.run_export(standard_jobs())

        self.assert_success_dialog()
        self.assertEqual(sheet_names(self.export_path), STANDARD_SHEETS)
        self.assert_no_temp_left(expected_new={"export.xlsx"})

    def test_ac7_logs_and_dialog_show_only_the_target_path(self):
        self.make_old_file()
        self.run_export(standard_jobs())

        self.assert_success_dialog()
        self.messagebox.showwarning.assert_not_called()
        self.assert_output_has(f"📁 File: {self.export_path}\n")
        self.assert_output_has(f"📁 Saved to: {self.export_path}\n")
        message = self.messagebox.showinfo.call_args[0][1]
        self.assertTrue(self.export_path in message, "dialog lacks the target path")

        self.assertEqual(len(self.replace_calls), 1)
        temp_path = self.replace_calls[0][0]
        temp_name = os.path.basename(temp_path)
        for text in (temp_path, temp_name, ".tmp.xlsx"):
            self.assert_output_lacks(text)
            self.assertFalse(text in message, f"dialog shows {ascii(text)}")

    def test_ac8_per_job_failures_are_not_fatal(self):
        self.make_old_file()
        too_many = app.pd.DataFrame(
            {"v": np.zeros(app.EXCEL_MAX_DATA_ROWS + 1, dtype=np.int8)}
        )

        def query(sql):
            if "huge_table" in sql:
                return too_many
            return standard_query(sql)

        self.on_query = query
        jobs = [
            {"name": "Good A", "query": "SELECT id, name FROM data_table"},
            {"name": "Read error", "query": "SELECT * FROM broken_table"},
            {"name": "Row limit", "query": "SELECT v FROM huge_table"},
            {"name": "Good B", "query": "SELECT v FROM other"},
        ]
        self.run_export(jobs)

        self.assert_success_dialog()
        self.assertEqual(self.counts(), {"ok": 2, "warnings": 0, "failed": 2, "skipped": 0})
        self.assertEqual(sheet_names(self.export_path), [job["name"] for job in jobs])
        workbook = load_workbook(self.export_path)
        try:
            for name, error_part in (("Read error", "table is broken"),
                                     ("Row limit", "1,048,575")):
                ws = workbook[name]
                self.assertEqual([c.value for c in ws[1]], ["Status", "Error", "Query"])
                self.assertEqual(ws["A2"].value, "Failed")
                self.assertIn(error_part, ws["B2"].value)
        finally:
            workbook.close()
        self.assertEqual(len(self.replace_calls), 1)
        self.assert_no_temp_left()


# ------------------------------------------------------ fatal (R10-AC-9..13)
class FatalExportTests(_R10Case):
    FATAL_AFTER_SHEET = [
        {"name": "Good", "query": "SELECT id, name FROM data_table"},
        {"name": "Broken job"},
    ]
    FATAL_BEFORE_SHEET = [{"name": "Broken job"}, {"name": "Good", "query": "SELECT 1"}]

    def assert_fatal_keyerror(self):
        self.assert_target_unchanged()
        self.assert_no_temp_left()
        self.assertEqual(self.replace_calls, [])
        self.assert_one_error(
            "KeyError", "query",
            absent=("IndexError", "At least one sheet must be visible"),
        )
        self.assert_output_has("Error: KeyError: ")

    def test_ac9_fatal_after_a_sheet_keeps_the_old_file(self):
        self.make_old_file()
        self.run_export(self.FATAL_AFTER_SHEET)
        self.assert_fatal_keyerror()
        self.assertEqual(self.read_sql_calls, ["SELECT id, name FROM data_table"])

    def test_ac10_fatal_before_any_sheet_shows_the_real_error(self):
        self.make_old_file()
        self.run_export(self.FATAL_BEFORE_SHEET)
        self.assert_fatal_keyerror()
        self.assertEqual(self.read_sql_calls, [])

    def test_ac9_ac10_fatal_without_an_old_file_creates_nothing(self):
        for label, jobs in (("after", self.FATAL_AFTER_SHEET),
                            ("before", self.FATAL_BEFORE_SHEET)):
            with self.subTest(case=label):
                self.new_subfolder(label)
                self.before_names = self.listing()
                self.run_export(jobs)
                self.assertFalse(os.path.exists(self.export_path))
                self.assert_no_temp_left()
                self.assert_one_error("KeyError", absent=("IndexError",))

    @staticmethod
    def _failing_save(written):
        def save(_workbook, filename):
            if hasattr(filename, "write"):
                filename.write(b"PK\x03\x04partial workbook")
            else:
                with REAL_OPEN(filename, "wb") as handle:
                    handle.write(b"PK\x03\x04partial workbook")
            written.append(True)
            raise OSError("disk full")

        return save

    def test_ac11_save_failure_keeps_the_old_file(self):
        self.make_old_file()
        written = []
        self.run_export(
            [{"name": "Good", "query": "SELECT id, name FROM data_table"}],
            extra_patches=[mock.patch.object(
                _OpenpyxlWorkbook, "save", autospec=True,
                side_effect=self._failing_save(written))],
        )
        self.assertEqual(written, [True], "save was not reached")
        self.assert_target_unchanged()
        self.assert_no_temp_left()
        self.assertEqual(self.replace_calls, [])
        self.assert_one_error("disk full", "OSError")

    def test_ac11_save_failure_without_an_old_file_creates_nothing(self):
        self.before_names = self.listing()
        self.run_export(
            [{"name": "Good", "query": "SELECT id, name FROM data_table"}],
            extra_patches=[mock.patch.object(
                _OpenpyxlWorkbook, "save", autospec=True,
                side_effect=self._failing_save([]))],
        )
        self.assertFalse(os.path.exists(self.export_path))
        self.assert_no_temp_left()
        self.assert_one_error("disk full")

    def test_ac12_temp_that_cannot_be_deleted_is_logged_not_raised(self):
        denied = PermissionError(13, "Access is denied")
        cases = (
            ("keyerror", FatalExportTests.FATAL_AFTER_SHEET, [], "KeyError"),
            ("disk_full", [{"name": "Good", "query": "SELECT id, name FROM data_table"}],
             [mock.patch.object(_OpenpyxlWorkbook, "save", autospec=True,
                                side_effect=self._failing_save([]))],
             "disk full"),
        )
        for label, jobs, patches, cause in cases:
            with self.subTest(case=label):
                self.new_subfolder(label)
                self.make_old_file()
                remove_spy = mock.Mock(side_effect=denied)
                self.run_export(
                    jobs,
                    extra_patches=list(patches) + [
                        mock.patch.object(app.os, "remove", remove_spy),
                        mock.patch.object(app.os, "unlink", remove_spy),
                    ],
                )
                leftovers = sorted(self.new_names())
                for name in leftovers:  # clean up ourselves (R10-Q-9 leaves it)
                    REAL_REMOVE(os.path.join(self.folder, name))

                self.assertTrue(remove_spy.called, "the temp file was never deleted")
                self.assertEqual(len(leftovers), 1, f"leftovers: {leftovers}")
                self.assertRegex(leftovers[0], TEMP_RE)
                temp_path = os.path.join(self.folder, leftovers[0])
                lines = [line for line in self.output.splitlines() if temp_path in line]
                self.assertEqual(len(lines), 1, "one log line names the undeleted temp file")
                self.assertTrue("Could not delete temporary file" in lines[0])
                message = self.assert_one_error(cause)
                self.assertNotIn("PermissionError", message)
                self.assertNotIn("Access is denied", message)
                self.assert_target_unchanged()
                self.assertEqual(self.replace_calls, [])

    def test_ac13_base_exception_cleans_up_and_still_propagates(self):
        for label, error, jobs in (
            ("systemexit_after_sheet", SystemExit(3), [
                {"name": "Good", "query": "SELECT id, name FROM data_table"},
                {"name": "Dies", "query": "SELECT v FROM dying_table"}]),
            ("systemexit_first_job", SystemExit(3), [
                {"name": "Dies", "query": "SELECT v FROM dying_table"}]),
            ("keyboard_interrupt", KeyboardInterrupt(), [
                {"name": "Good", "query": "SELECT id, name FROM data_table"},
                {"name": "Dies", "query": "SELECT v FROM dying_table"}]),
        ):
            with self.subTest(case=label):
                self.new_subfolder(label)
                self.make_old_file()

                def query(sql, error=error):
                    if "dying_table" in sql:
                        raise error
                    return standard_query(sql)

                self.on_query = query
                with self.assertRaises(type(error)):
                    self.run_export(jobs)

                self.assert_target_unchanged()
                self.assert_no_temp_left()
                self.assertEqual(self.replace_calls, [])


# ------------------------------------------------ locked target (R10-AC-14/15)
class LockedTargetTests(_R10Case):
    def lock_like_excel(self, path):
        """Hold `path` the way Excel does: read access, share-read only."""
        create, close = _windows_lock_api()
        handle = create(path, 0x80000000, 0x00000001, None, 3, 0, None)
        if handle is None or handle == ctypes.c_void_p(-1).value:
            raise ctypes.WinError(ctypes.get_last_error())
        released = []

        def release():
            if not released:
                released.append(True)
                close(handle)

        self.addCleanup(release)
        with self.assertRaises(PermissionError, msg="the Excel-like lock is not effective"):
            with REAL_OPEN(path, "r+b"):
                pass
        return release

    def assert_failed_before_query(self):
        self.assertEqual(self.read_sql_calls, [])
        self.assertEqual(self.replace_calls, [])
        self.assert_one_error(self.export_path, "PermissionError")
        self.assert_no_temp_left()

    @unittest.skipUnless(sys.platform == "win32", "CreateFileW lock needs Windows")
    def test_ac14_locked_at_start_fails_before_any_query(self):
        self.make_old_file()
        release = self.lock_like_excel(self.export_path)
        self.on_query = mock.Mock(side_effect=AssertionError("query must not run"))

        self.run_export(standard_jobs())

        self.assertTrue(read_bytes(self.export_path) == self.old_bytes)
        release()
        self.assert_target_unchanged()
        self.assert_failed_before_query()

    @unittest.skipIf(hasattr(os, "geteuid") and os.geteuid() == 0, "root ignores read-only")
    def test_ac14_read_only_target_fails_before_any_query(self):
        self.make_old_file()
        os.chmod(self.export_path, stat.S_IREAD)
        self.addCleanup(os.chmod, self.export_path, stat.S_IREAD | stat.S_IWRITE)

        self.run_export(standard_jobs())

        os.chmod(self.export_path, stat.S_IREAD | stat.S_IWRITE)
        self.assert_target_unchanged()
        self.assert_failed_before_query()

    def assert_kept_temp(self, *cause):
        self.assert_target_unchanged()
        new = sorted(self.new_names())
        self.assertEqual(len(new), 1, f"expected only the kept temp file, got {new}")
        self.assertRegex(new[0], TEMP_RE)
        temp_path = os.path.join(self.folder, new[0])
        # PermissionError: first try + one per retry delay, all on the same temp
        self.assertEqual(len(self.replace_calls), 1 + len(app.EXPORT_REPLACE_RETRY_DELAYS))
        for src, dst in self.replace_calls:
            self.assertTrue(same_path(src, temp_path))
            self.assertEqual(dst, self.export_path)
        self.assertEqual(sheet_names(temp_path), ["Job A", "Job B"])
        kept = workbook_cells(temp_path)
        self.assertIn(("A2", 1, "n"), kept[0][1])
        self.assert_one_error(self.export_path, temp_path, *cause)

    @unittest.skipUnless(sys.platform == "win32", "CreateFileW lock needs Windows")
    def test_ac15_locked_during_export_keeps_the_completed_temp(self):
        self.make_old_file()
        releases = []

        def query(sql):
            if "last_table" in sql:
                releases.append(self.lock_like_excel(self.export_path))
            return app.pd.DataFrame({"v": [1, 2]})

        self.on_query = query
        self.run_export([{"name": "Job A", "query": "SELECT v FROM first_table"},
                         {"name": "Job B", "query": "SELECT v FROM last_table"}])
        self.assertEqual(len(releases), 1)
        releases[0]()

        self.assert_kept_temp("PermissionError")

    def test_ac15_replace_failure_keeps_the_completed_temp(self):
        self.make_old_file()
        self.replace_error = PermissionError("locked")
        self.on_query = lambda _sql: app.pd.DataFrame({"v": [1, 2]})

        self.run_export([{"name": "Job A", "query": "SELECT v FROM first_table"},
                         {"name": "Job B", "query": "SELECT v FROM last_table"}])

        self.assert_kept_temp("PermissionError", "locked")

    def test_short_lock_is_retried_and_the_export_succeeds(self):
        self.make_old_file()
        self.before_names = self.listing()
        failures = [PermissionError(13, "held by antivirus")] * 2
        real_replace = self._replace

        def replace(src, dst, *args, **kwargs):
            if failures:
                self.replace_calls.append((src, dst))
                raise failures.pop()
            return real_replace(src, dst, *args, **kwargs)

        self.run_export([{"name": "Good", "query": "SELECT id, name FROM data_table"}],
                        extra_patches=[mock.patch.object(app.os, "replace", side_effect=replace)])

        self.assertEqual(len(self.replace_calls), 3)
        self.assertEqual(len({src for src, _dst in self.replace_calls}), 1)
        self.assert_success_dialog()
        self.assertEqual(sheet_names(self.export_path), ["Good"])
        self.assert_no_temp_left()

    def test_retry_waits_the_configured_delays(self):
        with mock.patch.object(app, "EXPORT_REPLACE_RETRY_DELAYS", (0.2, 0.5)), \
                mock.patch.object(app.os, "replace",
                                  side_effect=[PermissionError("a"), PermissionError("b"), None]) \
                as replace, \
                mock.patch("time.sleep") as sleep:
            app._replace_export_with_retry("src.tmp.xlsx", "dst.xlsx")
        self.assertEqual(replace.call_count, 3)
        self.assertEqual([c.args[0] for c in sleep.call_args_list], [0.2, 0.5])

    def test_errors_other_than_permission_are_not_retried(self):
        self.make_old_file()
        self.replace_error = OSError(28, "No space left on device")
        self.on_query = lambda _sql: app.pd.DataFrame({"v": [1, 2]})

        self.run_export([{"name": "Job A", "query": "SELECT v FROM first_table"},
                         {"name": "Job B", "query": "SELECT v FROM last_table"}])

        self.assertEqual(len(self.replace_calls), 1)
        self.assert_target_unchanged()
        new = sorted(self.new_names())
        self.assertEqual(len(new), 1)
        self.assertRegex(new[0], TEMP_RE)
        self.assert_one_error("OSError", "No space left on device", self.export_path)


# ----------------------------------------------------------- Stop (R10-AC-16/17)
class StopTests(_R10Case):
    def test_ac16_stop_after_first_job_replaces_with_finished_sheets(self):
        self.make_old_file()

        def query(sql):
            self.stop_event.set()
            return app.pd.DataFrame({"v": [1]})

        self.on_query = query
        self.run_export([{"name": f"Job {n}", "query": f"SELECT v FROM t{n}"}
                         for n in (1, 2, 3)])

        self.assertEqual(self.read_sql_calls, ["SELECT v FROM t1"])
        self.assertEqual(sheet_names(self.export_path), ["Job 1"])
        self.assert_output_has("⏹ Stopped — 2 job(s) not exported\n")
        self.assertEqual(len(self.replace_calls), 1)
        self.assert_no_temp_left()

    def test_ac17_stop_before_first_job_writes_the_export_sheet(self):
        self.make_old_file()
        self.stop_event.set()

        self.run_export(standard_jobs())

        self.assertEqual(self.read_sql_calls, [])
        self.assertEqual(sheet_names(self.export_path), ["Export"])
        cells = dict((c, v) for c, v, _ in workbook_cells(self.export_path)[0][1])
        self.assertEqual(cells["A1"], "Status")
        self.assertEqual(cells["A2"], "Stopped")
        self.assertEqual(len(self.replace_calls), 1)
        self.assert_no_temp_left()


# ------------------------------------------------- no export started (R10-AC-18)
class NoExportStartedTests(_R10Case):
    def test_ac18_paths_that_never_start_the_worker_touch_nothing(self):
        cases = ("no_jobs", "dialog_cancelled", "reuse_cancelled", "busy_first",
                 "busy_after_dialogs", "profile_mismatch", "not_connected")
        for case in cases:
            with self.subTest(case=case):
                self.new_subfolder(case)
                self.make_old_file()
                with REAL_OPEN(os.path.join(self.folder, "other.txt"), "wb") as handle:
                    handle.write(b"other")
                files_before = {name: read_bytes(os.path.join(self.folder, name))
                                for name in os.listdir(self.folder)}

                stub = self.make_stub()
                jobs = [] if case == "no_jobs" else standard_jobs()
                save_path = "" if case == "dialog_cancelled" else self.export_path
                if case == "reuse_cancelled":
                    stub._reuse_last_run_results = mock.Mock(return_value=None)
                if case == "busy_first":
                    stub._block_if_busy = mock.Mock(return_value=True)
                if case == "busy_after_dialogs":
                    stub._block_if_busy = mock.Mock(side_effect=[False, True])
                if case == "not_connected":
                    stub.engine = None
                mismatch = mock.Mock(return_value=case == "profile_mismatch")
                thread_cls = mock.Mock()
                with mock.patch.object(app.filedialog, "asksaveasfilename",
                                       return_value=save_path) as ask, \
                        mock.patch.object(app.threading, "Thread", thread_cls), \
                        mock.patch.object(app.DatabaseConnectorGUI,
                                          "_block_if_profile_mismatch", mismatch), \
                        mock.patch.object(app.os, "replace",
                                          side_effect=self._replace), \
                        mock.patch.object(app, "messagebox") as mb:
                    stub.export_jobs_to_excel(jobs_override=jobs)

                thread_cls.assert_not_called()
                stub._start_stoppable_run.assert_not_called()
                self.assertEqual(self.replace_calls, [])
                self.assertEqual(stub.results_text.inserted, [])
                files_after = {name: read_bytes(os.path.join(self.folder, name))
                               for name in os.listdir(self.folder)}
                self.assertTrue(files_after == files_before, "folder content changed")

                expects_dialog = case in ("busy_after_dialogs", "dialog_cancelled",
                                          "reuse_cancelled")
                self.assertEqual(ask.call_count, 1 if expects_dialog else 0)
                if case == "no_jobs":
                    mb.showwarning.assert_called_once_with("Export Excel", "No jobs to export")
                else:
                    mb.showwarning.assert_not_called()
                if case == "not_connected":
                    mb.showerror.assert_called_once_with("Error", "กรุณา Connect Database ก่อน")
                else:
                    mb.showerror.assert_not_called()
                mb.showinfo.assert_not_called()
                if case == "busy_after_dialogs":
                    self.assertEqual(stub._block_if_busy.call_count, 2)


# ------------------------------------- Round 7 cell limit over an old file (R10-AC-19)
class _ExistingTargetMixin:
    """Runs a Round 7 test with the user's old workbook already at the target."""

    def setUp(self):
        super().setUp()
        self.old_bytes = make_old_workbook(self.export_path)
        self.target_folder = os.path.dirname(self.export_path)
        self.names_before = set(os.listdir(self.target_folder))

    def run_export(self, jobs):
        workbook = super().run_export(jobs)
        self.assertEqual(set(os.listdir(self.target_folder)), self.names_before,
                         "temp file left behind")
        self.assertNotIn("Old", workbook.sheetnames)
        self.assertFalse(read_bytes(self.export_path) == self.old_bytes)
        return workbook


class R10ResultCellLimitTests(_ExistingTargetMixin, r7.ResultCellLimitTests):
    pass


class R10SkippedSheetLimitTests(_ExistingTargetMixin, r7.SkippedSheetLimitTests):
    pass


class R10FailedSheetLimitTests(_ExistingTargetMixin, r7.FailedSheetLimitTests):
    pass


class R10NoDataSheetLimitTests(_ExistingTargetMixin, r7.NoDataSheetLimitTests):
    pass


class R10SqlAnnotationLimitTests(_ExistingTargetMixin, r7.SqlAnnotationLimitTests):
    pass


class R10MixedExportCounterTests(_ExistingTargetMixin, r7.MixedExportCounterTests):
    pass


# ------------------------------------- review suggestions (Round 10 follow-up)
class TempHandleAndCreationTests(_R10Case):
    """Handle closed before replace / remove on any OS; mkstemp failure message;
    temp path keeps the separators of the user's path."""

    def _spy_temp_handles(self):
        handles = []
        real_create = app._create_export_temp_file

        def create(file_path):
            handle, temp_path = real_create(file_path)
            handles.append(handle)
            return handle, temp_path

        return handles, mock.patch.object(app, "_create_export_temp_file", side_effect=create)

    def test_handle_is_closed_before_os_replace(self):
        self.make_old_file()
        handles, spy = self._spy_temp_handles()
        closed_at_replace = []
        real_replace = self._replace

        def replace(src, dst, *args, **kwargs):
            closed_at_replace.append(all(h.closed for h in handles))
            return real_replace(src, dst, *args, **kwargs)

        self.run_export([{"name": "Good", "query": "SELECT id, name FROM data_table"}],
                        extra_patches=[spy, mock.patch.object(app.os, "replace",
                                                              side_effect=replace)])
        self.assertEqual(len(handles), 1)
        self.assertEqual(closed_at_replace, [True])
        self.assert_success_dialog()

    def test_handle_is_closed_before_the_temp_is_removed(self):
        self.make_old_file()
        handles, spy = self._spy_temp_handles()
        closed_at_remove = []
        real_remove = os.remove

        def remove(path, *args, **kwargs):
            closed_at_remove.append(all(h.closed for h in handles))
            return real_remove(path, *args, **kwargs)

        self.run_export(FatalExportTests.FATAL_AFTER_SHEET,
                        extra_patches=[spy, mock.patch.object(app.os, "remove",
                                                              side_effect=remove)])
        self.assertEqual(len(handles), 1)
        self.assertEqual(closed_at_remove, [True])
        self.assert_target_unchanged()
        self.assert_no_temp_left()

    def test_mkstemp_failure_names_the_chosen_file_not_a_temp_path(self):
        self.make_old_file()
        temp_like = os.path.join(self.folder, "export.k3j2ab9x.tmp.xlsx")
        failure = FileNotFoundError(2, "No such file or directory", temp_like)
        self.on_query = mock.Mock(side_effect=AssertionError("query must not run"))

        self.run_export(standard_jobs(), extra_patches=[
            mock.patch.object(app.tempfile, "mkstemp", side_effect=failure)])

        self.assertEqual(self.read_sql_calls, [])
        self.assertEqual(self.replace_calls, [])
        self.assert_target_unchanged()
        self.assert_no_temp_left()
        self.assert_one_error(
            "FileNotFoundError", "Cannot create a temporary file next to",
            self.export_path, "No such file or directory",
            absent=(".tmp.xlsx",),
        )

    @unittest.skipUnless(os.altsep, "only one path separator on this OS")
    def test_temp_path_uses_the_separators_of_the_chosen_path(self):
        forward = self.export_path.replace(os.sep, os.altsep)
        for chosen, unwanted in ((forward, os.sep), (self.export_path, os.altsep)):
            with self.subTest(chosen=chosen):
                handle, temp_path = app._create_export_temp_file(chosen)
                handle.close()
                self.addCleanup(os.remove, temp_path)
                self.assertNotIn(unwanted, temp_path)
                self.assertRegex(os.path.basename(temp_path), TEMP_RE)
                self.assertTrue(same_path(os.path.dirname(temp_path), self.folder))


if __name__ == "__main__":
    unittest.main()
