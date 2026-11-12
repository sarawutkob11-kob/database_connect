"""T5: block Connect / profile switch / edit / delete / import while a run is busy.

AC-1, AC-2, AC-3, AC-4, AC-32, AC-33, AC-34. No Tk window, no real database
(create_engine is patched to an in-memory SQLite engine).
"""

import copy
import json
import os
import sys
import tempfile
import threading
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import database_connect_gui as app  # noqa: E402

BLOCK_PREFIX = "⏳ "


class _FakeButton:
    def __init__(self, text: str = "", state: str = "normal") -> None:
        self.text = text
        self.state = state
        self.config_calls: list = []

    def cget(self, key):
        return self.text if key == "text" else self.state

    def __getitem__(self, key):
        return self.cget(key)

    def config(self, **kw):
        self.config_calls.append(kw)
        if "state" in kw:
            self.state = kw["state"]
        if "text" in kw:
            self.text = kw["text"]

    configure = config


class _FakeEntry:
    def __init__(self, value: str = "") -> None:
        self.value = value
        self.calls: list = []

    def get(self, *_args):
        return self.value

    def set(self, value):
        self.calls.append(("set", value))
        self.value = value

    def delete(self, *_args):
        self.calls.append(("delete",))
        self.value = ""

    def insert(self, _index, value):
        self.calls.append(("insert", value))
        self.value = value

    def current(self, *_args):
        self.calls.append(("current",) + _args)


class _FakeText:
    def __init__(self) -> None:
        self.inserted: list = []
        self.seen: list = []
        self.other_calls: list = []

    def insert(self, index, value):
        self.inserted.append(value)

    def see(self, index):
        self.seen.append(index)

    def delete(self, *args):
        self.other_calls.append(("delete",) + args)

    def get(self, *_args):
        return ""


def make_stub(*, busy_by: str = "", profiles=None):
    """busy_by: '' (idle), 'job' (_running_job_ids) or 'conn' (_active_db_connections)."""
    stub = app.DatabaseConnectorGUI.__new__(app.DatabaseConnectorGUI)
    stub._active_db_lock = threading.Lock()
    stub._active_db_connections = {object(): object()} if busy_by == "conn" else {}
    stub._running_job_ids = {"job-1"} if busy_by == "job" else set()
    stub._batch_running = False
    stub.execute_btn = _FakeButton("▶  Run")
    stub.export_excel_btn = _FakeButton("Export Excel")
    stub.inspect_btn = _FakeButton("Tables")
    stub.status_label = _FakeButton("")
    stub.results_text = _FakeText()
    stub.sql_context = _FakeText()
    stub.db_type = _FakeEntry("PostgreSQL")
    stub.db_user = _FakeEntry("user")
    stub.db_password = _FakeEntry("pw")
    stub.db_host = _FakeEntry("localhost")
    stub.db_port = _FakeEntry("5432:5432")
    stub.db_name = _FakeEntry("db")
    stub.profile_combo = _FakeEntry("")
    stub.saved_profiles = copy.deepcopy(
        profiles if profiles is not None else {
            "P1": {"db_type": "PostgreSQL", "db_host": "h1"},
            "P2": {"db_type": "MySQL", "db_host": "h2"},
        }
    )
    stub.engine = None
    stub.root = mock.Mock(name="root")
    return stub


def assert_blocked_log(test: unittest.TestCase, stub, action: str) -> None:
    test.assertEqual(len(stub.results_text.inserted), 1, stub.results_text.inserted)
    message = stub.results_text.inserted[0]
    test.assertTrue(message.startswith(f"{BLOCK_PREFIX}{action}: "), message)
    test.assertTrue(message.endswith("\n"))
    test.assertEqual(len(stub.results_text.seen), 1)


def assert_no_popup(test: unittest.TestCase, mb: mock.Mock) -> None:
    for name in ("showinfo", "showwarning", "showerror", "askyesno", "askokcancel",
                 "askyesnocancel", "askquestion"):
        getattr(mb, name).assert_not_called()


BUSY_SOURCES = ("job", "conn")


def file_state(path: str) -> tuple:
    with open(path, encoding="utf-8") as fh:
        return fh.read(), os.stat(path).st_mtime_ns


class ConnectBlockedTests(unittest.TestCase):
    """AC-1"""

    def test_busy_connect_does_nothing_but_log(self):
        for source in BUSY_SOURCES:
            with self.subTest(busy_by=source):
                stub = make_stub(busy_by=source)
                engine_a = mock.Mock(name="engine_A")
                stub.engine = engine_a
                with mock.patch.object(app, "create_engine") as ce, \
                        mock.patch.object(app, "messagebox") as mb, \
                        mock.patch.object(app, "ui_dialog") as dlg:
                    self.assertIsNone(stub.connect_database())
                ce.assert_not_called()
                self.assertIs(stub.engine, engine_a)
                engine_a.dispose.assert_not_called()
                self.assertEqual(stub.db_port.calls, [])
                self.assertEqual(stub.db_port.value, "5432:5432")
                self.assertEqual(stub.execute_btn.config_calls, [])
                self.assertEqual(stub.inspect_btn.config_calls, [])
                self.assertEqual(stub.status_label.config_calls, [])
                assert_blocked_log(self, stub, "Connect")
                self.assertIn("Stop", stub.results_text.inserted[0])
                assert_no_popup(self, mb)
                dlg.assert_not_called()


class ConnectIdleTests(unittest.TestCase):
    """AC-2"""

    def test_idle_connect_swaps_engine(self):
        from sqlalchemy import create_engine as real_create_engine

        stub = make_stub()
        old_engine = mock.Mock(name="old_engine")
        stub.engine = old_engine
        new_engine = real_create_engine("sqlite://")
        self.addCleanup(new_engine.dispose)
        with mock.patch.object(app, "create_engine", return_value=new_engine) as ce, \
                mock.patch.object(app, "messagebox") as mb:
            stub.connect_database()
        ce.assert_called_once()
        self.assertIs(stub.engine, new_engine)
        old_engine.dispose.assert_called_once_with()
        self.assertEqual(stub.db_port.value, "5432")  # port cleaned like before
        self.assertEqual(stub.execute_btn.state, "normal")
        self.assertEqual(stub.inspect_btn.state, "normal")
        self.assertIn("Connected", stub.status_label.text)
        mb.showinfo.assert_called_once()
        mb.showerror.assert_not_called()
        self.assertFalse(any(m.startswith(BLOCK_PREFIX) for m in stub.results_text.inserted))
        # connection was checked in again after the SELECT 1 test
        self.assertEqual(stub._active_db_connections, {})


class ProfileSwitchBlockedTests(unittest.TestCase):
    """AC-3"""

    def test_busy_switch_restores_active_profile(self):
        for source in BUSY_SOURCES:
            with self.subTest(busy_by=source):
                stub = make_stub(busy_by=source)
                stub._active_profile = "P1"
                stub.profile_combo.value = "P2"
                engine = mock.Mock(name="engine")
                stub.engine = engine
                stub.load_profile_data = mock.Mock(name="load_profile_data")
                stub.update_jobs_list = mock.Mock(name="update_jobs_list")
                with mock.patch.object(app, "messagebox") as mb:
                    self.assertIsNone(stub.on_profile_selected(object()))
                stub.load_profile_data.assert_not_called()
                stub.update_jobs_list.assert_not_called()
                self.assertEqual(stub.profile_combo.calls, [("set", "P1")])
                self.assertEqual(stub.profile_combo.get(), "P1")
                self.assertIs(stub.engine, engine)
                engine.dispose.assert_not_called()
                for field in (stub.db_type, stub.db_user, stub.db_password,
                              stub.db_host, stub.db_port, stub.db_name):
                    self.assertEqual(field.calls, [])
                self.assertEqual(stub.sql_context.inserted, [])
                self.assertEqual(stub.sql_context.other_calls, [])
                assert_blocked_log(self, stub, "เปลี่ยน Profile")
                assert_no_popup(self, mb)

    def test_busy_switch_without_active_profile_sets_empty(self):
        stub = make_stub(busy_by="job")
        stub.profile_combo.value = "P2"
        stub.load_profile_data = mock.Mock()
        stub.update_jobs_list = mock.Mock()
        self.assertFalse(hasattr(stub, "_active_profile"))
        with mock.patch.object(app, "messagebox"):
            stub.on_profile_selected()
        self.assertEqual(stub.profile_combo.calls, [("set", "")])
        stub.load_profile_data.assert_not_called()
        assert_blocked_log(self, stub, "เปลี่ยน Profile")


class ProfileSwitchIdleTests(unittest.TestCase):
    """AC-4"""

    def test_idle_switch_loads_new_profile(self):
        stub = make_stub()
        stub._active_profile = "P1"
        stub.profile_combo.value = "P2"
        stub.load_profile_data = mock.Mock(name="load_profile_data")
        stub.update_jobs_list = mock.Mock(name="update_jobs_list")
        stub.on_profile_selected()
        stub.load_profile_data.assert_called_once_with("P2")
        stub.update_jobs_list.assert_called_once_with()
        self.assertEqual(stub.profile_combo.calls, [])
        self.assertEqual(stub.results_text.inserted, [])

    def test_idle_switch_sets_active_profile_via_real_load(self):
        stub = make_stub()
        stub._active_profile = "P1"
        stub.profile_combo.value = "P2"
        stub._reset_profile_session_state = mock.Mock()
        stub.update_jobs_list = mock.Mock()
        with mock.patch.object(app, "messagebox") as mb:
            stub.on_profile_selected()
        mb.showerror.assert_not_called()
        self.assertEqual(stub._active_profile, "P2")
        self.assertEqual(stub.db_type.value, "MySQL")
        self.assertEqual(stub.db_host.value, "h2")
        stub._reset_profile_session_state.assert_called_once_with()
        self.assertTrue(any("P2" in m for m in stub.results_text.inserted))

    def test_failed_load_keeps_previous_active_profile(self):
        stub = make_stub()
        stub._active_profile = "P1"
        stub._reset_profile_session_state = mock.Mock(side_effect=RuntimeError("boom"))
        stub.update_jobs_list = mock.Mock()
        with mock.patch.object(app, "messagebox") as mb:
            stub.load_profile_data("P2")
        mb.showerror.assert_called_once()
        self.assertEqual(stub._active_profile, "P1")


class ImportProfilesBlockedTests(unittest.TestCase):
    """AC-32"""

    def test_busy_import_opens_no_dialog(self):
        for source in BUSY_SOURCES:
            with self.subTest(busy_by=source), tempfile.TemporaryDirectory() as tmp:
                profiles_file = os.path.join(tmp, "db_profiles.json")
                stub = make_stub(busy_by=source)
                with open(profiles_file, "w", encoding="utf-8") as fh:
                    json.dump(stub.saved_profiles, fh)
                stub.config_file = profiles_file
                stub.profiles_file = profiles_file
                before_profiles = copy.deepcopy(stub.saved_profiles)
                before_file = file_state(profiles_file)
                stub.save_profiles = mock.Mock(name="save_profiles")
                stub.update_profile_list = mock.Mock(name="update_profile_list")
                with mock.patch.object(app, "filedialog") as fd, \
                        mock.patch.object(app, "messagebox") as mb:
                    self.assertIsNone(stub.import_profiles_dialog())
                fd.askopenfilename.assert_not_called()
                self.assertEqual(fd.mock_calls, [])
                stub.save_profiles.assert_not_called()
                stub.update_profile_list.assert_not_called()
                self.assertEqual(stub.saved_profiles, before_profiles)
                self.assertEqual(file_state(profiles_file), before_file)
                assert_blocked_log(self, stub, "Import Profile")
                assert_no_popup(self, mb)


class ImportRecheckAfterFileDialogTests(unittest.TestCase):
    """Review fix 2: a run that starts while the file dialog is open blocks the import."""

    def _profile_file(self, tmp):
        path = os.path.join(tmp, "export.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"profiles": {"P9": {"db_type": "Oracle", "db_host": "h9"}},
                       "exported_date": "2026-01-01", "total_profiles": 1}, fh)
        return path

    def _run(self, tmp, *, become_busy: str):
        stub = make_stub()
        before = copy.deepcopy(stub.saved_profiles)
        path = self._profile_file(tmp)
        stub._show_import_preview_dialog = mock.Mock(name="_show_import_preview_dialog")

        def pick_file(**_kw):
            if become_busy == "job":
                stub._running_job_ids.add(1)
            elif become_busy == "conn":
                stub._active_db_connections[object()] = object()
            return path

        import builtins

        real_open = builtins.open
        opened = []

        def tracking_open(file, *a, **k):
            opened.append(os.path.abspath(str(file)))
            return real_open(file, *a, **k)

        with mock.patch.object(app, "filedialog") as fd, \
                mock.patch.object(app, "messagebox") as mb, \
                mock.patch("builtins.open", side_effect=tracking_open):
            fd.askopenfilename.side_effect = pick_file
            stub.import_profiles_dialog()
        return stub, before, path, opened, fd, mb

    def test_busy_after_file_dialog_blocks(self):
        for source in BUSY_SOURCES:
            with self.subTest(busy_by=source), tempfile.TemporaryDirectory() as tmp:
                stub, before, path, opened, fd, mb = self._run(tmp, become_busy=source)
                fd.askopenfilename.assert_called_once()
                self.assertNotIn(os.path.abspath(path), opened)  # file not read
                stub._show_import_preview_dialog.assert_not_called()
                self.assertEqual(stub.saved_profiles, before)
                assert_blocked_log(self, stub, "Import Profile")
                assert_no_popup(self, mb)

    def test_idle_import_reads_file_and_shows_preview(self):
        with tempfile.TemporaryDirectory() as tmp:
            stub, _before, path, opened, _fd, mb = self._run(tmp, become_busy="")
            self.assertIn(os.path.abspath(path), opened)
            stub._show_import_preview_dialog.assert_called_once()
            args = stub._show_import_preview_dialog.call_args.args
            self.assertEqual(args[0], {"P9": {"db_type": "Oracle", "db_host": "h9"}})
            self.assertEqual(args[1:], (path, "2026-01-01", 1))
            self.assertEqual(stub.results_text.inserted, [])
            mb.showerror.assert_not_called()

    def test_cancelled_file_dialog_does_nothing(self):
        stub = make_stub()
        stub._show_import_preview_dialog = mock.Mock()
        with mock.patch.object(app, "filedialog") as fd, \
                mock.patch.object(app, "messagebox") as mb:
            fd.askopenfilename.return_value = ""
            stub.import_profiles_dialog()
        stub._show_import_preview_dialog.assert_not_called()
        self.assertEqual(stub.results_text.inserted, [])
        assert_no_popup(self, mb)


class DeleteProfileBlockedTests(unittest.TestCase):
    """AC-33"""

    def test_busy_delete_does_not_ask_or_delete(self):
        for source in BUSY_SOURCES:
            with self.subTest(busy_by=source):
                stub = make_stub(busy_by=source)
                stub._active_profile = "P1"
                stub.profile_combo.value = "P1"
                before = copy.deepcopy(stub.saved_profiles)
                stub.save_profiles = mock.Mock(name="save_profiles")
                stub.update_profile_list = mock.Mock(name="update_profile_list")
                with mock.patch.object(app, "messagebox") as mb:
                    self.assertIsNone(stub.delete_profile())
                mb.askyesno.assert_not_called()
                self.assertIn("P1", stub.saved_profiles)
                self.assertEqual(stub.saved_profiles, before)
                stub.save_profiles.assert_not_called()
                stub.update_profile_list.assert_not_called()
                assert_blocked_log(self, stub, "ลบ Profile")
                assert_no_popup(self, mb)

    def test_idle_delete_still_asks(self):
        stub = make_stub()
        stub.profile_combo.value = "P1"
        stub.save_profiles = mock.Mock()
        stub.update_profile_list = mock.Mock()
        with mock.patch.object(app, "messagebox") as mb:
            mb.askyesno.return_value = False
            stub.delete_profile()
        mb.askyesno.assert_called_once()
        self.assertIn("P1", stub.saved_profiles)


class SaveNewProfileBlockedTests(unittest.TestCase):
    """AC-34"""

    def _run_blocked(self, method_name: str, action: str, source: str) -> None:
        stub = make_stub(busy_by=source)
        stub._active_profile = "P1"
        stub.profile_combo.value = "P1"
        before = copy.deepcopy(stub.saved_profiles)
        stub._create_centered_dialog = mock.Mock(name="_create_centered_dialog")
        stub.save_profiles = mock.Mock(name="save_profiles")
        stub.load_profile_data = mock.Mock(name="load_profile_data")
        with mock.patch.object(app.tk, "Toplevel") as toplevel, \
                mock.patch.object(app, "messagebox") as mb:
            self.assertIsNone(getattr(stub, method_name)())
        toplevel.assert_not_called()
        stub._create_centered_dialog.assert_not_called()
        stub.save_profiles.assert_not_called()
        stub.load_profile_data.assert_not_called()
        self.assertEqual(stub.saved_profiles, before)
        self.assertEqual(stub._active_profile, "P1")
        self.assertEqual(stub.profile_combo.calls, [])
        assert_blocked_log(self, stub, action)
        assert_no_popup(self, mb)

    def test_busy_save_profile_dialog(self):
        for source in BUSY_SOURCES:
            with self.subTest(busy_by=source):
                self._run_blocked("save_profile_dialog", "บันทึก Profile", source)

    def test_busy_new_profile_dialog(self):
        for source in BUSY_SOURCES:
            with self.subTest(busy_by=source):
                self._run_blocked("new_profile_dialog", "สร้าง Profile", source)


class GuardIsFirstLineTests(unittest.TestCase):
    """The guard must run before any popup / dialog / field change."""

    def test_guard_is_first_statement(self):
        import ast
        import inspect
        import textwrap

        expected = {
            "import_profiles_dialog": "Import Profile",
            "connect_database": "Connect",
            "on_profile_selected": "เปลี่ยน Profile",
            "save_profile_dialog": "บันทึก Profile",
            "new_profile_dialog": "สร้าง Profile",
            "delete_profile": "ลบ Profile",
        }
        for name, action in expected.items():
            with self.subTest(method=name):
                src = textwrap.dedent(inspect.getsource(getattr(app.DatabaseConnectorGUI, name)))
                body = ast.parse(src).body[0].body
                if (isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant)
                        and isinstance(body[0].value.value, str)):
                    body = body[1:]  # skip docstring
                first = body[0]
                self.assertIsInstance(first, ast.If)
                call = first.test
                self.assertIsInstance(call, ast.Call)
                self.assertEqual(call.func.attr, "_block_if_busy")
                self.assertEqual(call.args[0].value, action)


if __name__ == "__main__":
    unittest.main()
