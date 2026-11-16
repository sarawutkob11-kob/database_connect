"""T8: ConnectionInfo / RunTarget and the snapshot taken at Connect.

AC-2 (still works), base of AC-9/AC-10/AC-11/AC-35. No Tk window; create_engine
is patched to an in-memory SQLite engine.
"""

import dataclasses
import os
import sys
import threading
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import database_connect_gui as app  # noqa: E402

GUI = app.DatabaseConnectorGUI
ConnectionInfo = app.ConnectionInfo
RunTarget = app.RunTarget
PASSWORD = "S3cr3t-P@ss!"


def info(**kw) -> ConnectionInfo:
    base = dict(profile="P1", db_type="Oracle", user="scott", host="host1",
                port="1521", database="SVC")
    base.update(kw)
    return ConnectionInfo(**base)


class _FakeEntry:
    def __init__(self, value: str = "") -> None:
        self.value = value

    def get(self, *_a):
        return self.value

    def set(self, value):
        self.value = value

    def delete(self, *_a):
        self.value = ""

    def insert(self, _i, value):
        self.value = value


class _FakeButton:
    def __init__(self, text="", state="normal"):
        self.text = text
        self.state = state

    def cget(self, key):
        return self.text if key == "text" else self.state

    def __getitem__(self, key):
        return self.cget(key)

    def config(self, **kw):
        self.state = kw.get("state", self.state)
        self.text = kw.get("text", self.text)

    configure = config


class _FakeText:
    def __init__(self):
        self.inserted = []

    def insert(self, _i, value):
        self.inserted.append(value)

    def see(self, *_a):
        pass


def make_stub(*, profile="P1", db_type="PostgreSQL", user="  app_user ",
              host=" db.local ", port="5432:5432", database=" sales "):
    stub = GUI.__new__(GUI)
    stub._active_db_lock = threading.Lock()
    stub._active_db_connections = {}
    stub._running_job_ids = set()
    stub._batch_running = False
    stub.execute_btn = _FakeButton("▶  Run", "disabled")
    stub.export_excel_btn = _FakeButton("Export")
    stub.inspect_btn = _FakeButton("Tables", "disabled")
    stub.status_label = _FakeButton("")
    stub.results_text = _FakeText()
    stub.profile_combo = _FakeEntry(profile)
    stub.db_type = _FakeEntry(db_type)
    stub.db_user = _FakeEntry(user)
    stub.db_password = _FakeEntry(PASSWORD)
    stub.db_host = _FakeEntry(host)
    stub.db_port = _FakeEntry(port)
    stub.db_name = _FakeEntry(database)
    stub.engine = None
    stub.root = mock.Mock(name="root")
    return stub


class ConnectionInfoTests(unittest.TestCase):
    def test_fields_and_frozen(self):
        names = [f.name for f in dataclasses.fields(ConnectionInfo)]
        self.assertEqual(names, ["profile", "db_type", "user", "host", "port", "database"])
        ci = info()
        with self.assertRaises(dataclasses.FrozenInstanceError):
            ci.host = "other"  # type: ignore[misc]

    def test_run_target_fields_and_frozen(self):
        self.assertEqual([f.name for f in dataclasses.fields(RunTarget)], ["engine", "info"])
        rt = RunTarget(object(), None)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            rt.engine = None  # type: ignore[misc]

    def test_no_password_like_field(self):
        for cls in (ConnectionInfo, RunTarget):
            for f in dataclasses.fields(cls):
                self.assertNotRegex(f.name.lower(), r"pass|pwd|secret|url|conn_str|string")

    def test_target_label(self):
        self.assertEqual(info().target_label(), "Oracle · host1 / SVC")
        self.assertEqual(info(database="").target_label(), "Oracle · host1")
        self.assertEqual(info(host="").target_label(), "Oracle")
        self.assertEqual(info(host="", database="SVC").target_label(), "Oracle")

    def test_log_target(self):
        self.assertEqual(info().log_target(), "scott@host1:1521/SVC")
        self.assertEqual(info(port="").log_target(), "scott@host1/SVC")
        self.assertEqual(info(database="").log_target(), "scott@host1:1521")
        self.assertEqual(info(port="", database="").log_target(), "scott@host1")

    def test_run_log_header(self):
        self.assertEqual(
            info().run_log_header(),
            "\n===== RUN  profile=P1  Oracle  scott@host1:1521/SVC =====\n",
        )
        self.assertEqual(
            info(profile="").run_log_header(),
            "\n===== RUN  profile=-  Oracle  scott@host1:1521/SVC =====\n",
        )


def _old_run_log_line(profile, db_type, user, host, port, database):
    """Copied verbatim from git HEAD _log_run_context (reads screen fields)."""
    user, host, port, database = user.strip(), host.strip(), port.strip(), database.strip()
    target = f"{user}@{host}" + (f":{port}" if port else "") + (f"/{database}" if database else "")
    return (
        f"\n===== RUN  profile={profile or '-'}  "
        f"{db_type}  {target} =====\n"
    )


def _old_confirm_destination(profile, db_type, user, host, port, database):
    """Copied verbatim from git HEAD _confirm_data_change (profile + 'Database' row)."""
    target = db_type
    host = host.strip()
    database = database.strip()
    if host:
        target += f" · {host}" + (f" / {database}" if database else "")
    return profile or "-", target


def capture_confirm_dialog(stub, jobs, **kwargs):
    """Run _confirm_data_change with ui_dialog patched; return (labels, dialog kwargs)."""
    captured = {}

    def fake_dialog(*args, build_body=None, **kw):
        captured["args"] = args
        captured["kw"] = kw
        captured["body"] = build_body
        return False

    labels = []

    def fake_label(*_a, **kw):
        labels.append(kw.get("text"))
        return mock.Mock()

    with mock.patch.object(app, "ui_dialog", side_effect=fake_dialog), \
            mock.patch.object(app, "ui_round_frame", return_value=(mock.Mock(), mock.Mock())), \
            mock.patch.object(app.tk, "Label", side_effect=fake_label), \
            mock.patch.object(app.tk, "Frame", return_value=mock.Mock()):
        result = stub._confirm_data_change(jobs, **kwargs)
        captured["body"](mock.Mock())
    return result, labels, captured


def shown_destination(labels):
    return (labels[labels.index("Profile") + 1], labels[labels.index("Database") + 1])


class FormatMatchesOldCodeTests(unittest.TestCase):
    """Text from the snapshot equals what the old code (git HEAD) built from the fields."""

    CASES = [
        dict(profile="P1", db_type="Oracle", user="scott", host="host1", port="1521", database="SVC"),
        dict(profile="", db_type="MySQL", user="root", host="h", port="", database=""),
        dict(profile="Prod", db_type="PostgreSQL", user="u", host="", port="5432", database="db"),
        dict(profile="X", db_type="Microsoft SQL Server", user="sa", host="sql1", port="1433", database=""),
    ]

    def _snapshot_stub(self, case):
        stub = make_stub(profile="OTHER", db_type="Other", user="other", host="other-host",
                         port="9", database="otherdb")  # screen differs on purpose
        engine = mock.Mock(name="E")
        stub.engine = engine
        stub._run_target = RunTarget(engine, ConnectionInfo(**case))
        return stub

    def test_run_log_header_equals_old_format(self):
        for case in self.CASES:
            with self.subTest(case=case):
                old = _old_run_log_line(**case)
                self.assertEqual(ConnectionInfo(**case).run_log_header(), old)
                for pass_target in (False, True):
                    stub = self._snapshot_stub(case)
                    written = []
                    stub._write_run_log = written.append
                    if pass_target:
                        stub._log_run_context(stub._run_target)
                    else:
                        stub._log_run_context()
                    self.assertEqual(written, [old])

    def test_confirm_dialog_equals_old_format(self):
        for case in self.CASES:
            with self.subTest(case=case):
                old_profile, old_label = _old_confirm_destination(**case)
                self.assertEqual(ConnectionInfo(**case).target_label(), old_label)
                for pass_target in (False, True):
                    stub = self._snapshot_stub(case)
                    kw = {"target": stub._run_target} if pass_target else {}
                    _r, labels, _c = capture_confirm_dialog(
                        stub, [{"name": "J", "query": "DELETE FROM t"}], **kw
                    )
                    self.assertEqual(shown_destination(labels), (old_profile, old_label))
                    self.assertEqual(GUI._confirm_destination(stub._run_target),
                                     (old_profile, old_label))


class NoPasswordTests(unittest.TestCase):
    def test_password_never_stored(self):
        from sqlalchemy import create_engine as real_create_engine

        stub = make_stub()
        engine = real_create_engine("sqlite://")
        self.addCleanup(engine.dispose)
        with mock.patch.object(app, "create_engine", return_value=engine), \
                mock.patch.object(app, "messagebox"):
            stub.connect_database()
        ci = stub._run_target.info
        texts = [repr(ci), str(ci), repr(stub._run_target), ci.target_label(),
                 ci.log_target(), ci.run_log_header()]
        texts += [str(v) for v in dataclasses.asdict(ci).values()]
        for t in texts:
            self.assertNotIn(PASSWORD, t)
            self.assertNotIn("S3cr3t", t)


class ConnectSnapshotTests(unittest.TestCase):
    """AC-2 + snapshot"""

    def _connect(self, stub):
        from sqlalchemy import create_engine as real_create_engine

        engine = real_create_engine("sqlite://")
        self.addCleanup(engine.dispose)
        with mock.patch.object(app, "create_engine", return_value=engine), \
                mock.patch.object(app, "messagebox") as mb:
            stub.connect_database()
        mb.showerror.assert_not_called()
        return engine

    def test_connect_sets_engine_and_run_target(self):
        stub = make_stub()
        old = mock.Mock(name="old_engine")
        stub.engine = old
        engine = self._connect(stub)
        self.assertIs(stub.engine, engine)
        self.assertIsInstance(stub._run_target, RunTarget)
        self.assertIs(stub._run_target.engine, engine)
        self.assertEqual(
            stub._run_target.info,
            ConnectionInfo(profile="P1", db_type="PostgreSQL", user="app_user",
                           host="db.local", port="5432", database="sales"),
        )
        old.dispose.assert_called_once_with()
        self.assertEqual(stub.db_port.value, "5432")

    def test_empty_profile_and_database(self):
        stub = make_stub(profile="", database="")
        self._connect(stub)
        ci = stub._run_target.info
        self.assertEqual(ci.profile, "")
        self.assertEqual(ci.database, "")
        self.assertIn("profile=-", ci.run_log_header())

    def test_ac11_base_profile_change_after_connect_keeps_snapshot(self):
        stub = make_stub(profile="P1", host="hostP1")
        self._connect(stub)
        stub.profile_combo.set("P2")
        stub.db_host.set("hostP2")
        stub.db_type.set("Oracle")
        ci = stub._capture_run_target().info
        self.assertEqual(ci.profile, "P1")
        self.assertEqual(ci.host, "hostP1")
        self.assertEqual(ci.db_type, "PostgreSQL")

    def test_connect_failure_clears_run_target(self):
        stub = make_stub()
        old_engine = mock.Mock(name="old")
        stub.engine = old_engine
        stub._run_target = RunTarget(old_engine, info())
        failing = mock.Mock(name="failing_engine")
        failing.connect.side_effect = RuntimeError("ORA-12541")
        with mock.patch.object(app, "create_engine", return_value=failing), \
                mock.patch.object(app, "messagebox"), \
                mock.patch.object(GUI, "_show_connection_error") as show_err, \
                mock.patch.object(GUI, "_track_engine_connections"):
            stub.connect_database()
        show_err.assert_called_once()
        self.assertIsNone(stub.engine)
        self.assertIsNone(stub._run_target)
        failing.dispose.assert_called_once_with()
        old_engine.dispose.assert_called_once_with()

    def test_missing_fields_do_not_touch_target(self):
        stub = make_stub()
        stub.db_password.set("")
        engine = mock.Mock()
        stub.engine = engine
        stub._run_target = RunTarget(engine, info())
        with mock.patch.object(app, "create_engine") as ce, \
                mock.patch.object(app, "messagebox") as mb:
            stub.connect_database()
        ce.assert_not_called()
        mb.showerror.assert_called_once()
        self.assertIs(stub._run_target.engine, engine)


class ReplaceEngineTests(unittest.TestCase):
    def test_replace_with_info(self):
        stub = make_stub()
        old, new = mock.Mock(name="old"), mock.Mock(name="new")
        stub.engine = old
        ci = info()
        stub._replace_engine(new, ci)
        self.assertIs(stub.engine, new)
        self.assertEqual(stub._run_target, RunTarget(new, ci))
        self.assertIs(stub._run_target.info, ci)
        old.dispose.assert_called_once_with()
        new.dispose.assert_not_called()

    def test_replace_without_info(self):
        stub = make_stub()
        new = mock.Mock()
        stub._replace_engine(new)
        self.assertEqual(stub._run_target, RunTarget(new, None))

    def test_replace_with_none(self):
        stub = make_stub()
        old = mock.Mock(name="old")
        stub.engine = old
        stub._run_target = RunTarget(old, info())
        stub._replace_engine(None)
        self.assertIsNone(stub.engine)
        self.assertIsNone(stub._run_target)
        old.dispose.assert_called_once_with()

    def test_same_engine_not_disposed(self):
        stub = make_stub()
        e = mock.Mock()
        stub.engine = e
        stub._replace_engine(e, info())
        e.dispose.assert_not_called()
        self.assertIs(stub._run_target.engine, e)

    def test_dispose_error_is_ignored(self):
        stub = make_stub()
        old = mock.Mock()
        old.dispose.side_effect = RuntimeError("x")
        stub.engine = old
        new = mock.Mock()
        stub._replace_engine(new, info())
        self.assertIs(stub.engine, new)


class ResetProfileTests(unittest.TestCase):
    def test_reset_clears_run_target(self):
        stub = make_stub()
        engine = mock.Mock()
        stub.engine = engine
        stub._run_target = RunTarget(engine, info())
        stub.execute_btn.state = "normal"
        stub._reset_profile_connection_state(engine)
        self.assertIsNone(stub.engine)
        self.assertIsNone(stub._run_target)
        engine.dispose.assert_called_once_with()
        self.assertIsNone(stub._capture_run_target())

    def test_reset_skipped_after_reconnect_keeps_target(self):
        stub = make_stub()
        old, new = mock.Mock(), mock.Mock()
        stub.engine = new
        target = RunTarget(new, info())
        stub._run_target = target
        stub._reset_profile_connection_state(old)
        self.assertIs(stub._run_target, target)

    def test_reset_waits_while_busy_and_keeps_target(self):
        stub = make_stub()
        engine = mock.Mock()
        stub.engine = engine
        target = RunTarget(engine, info())
        stub._run_target = target
        stub._running_job_ids = {1}
        stub._reset_profile_connection_state(engine)
        self.assertIs(stub._run_target, target)
        stub.root.after.assert_called_once()


class CaptureRunTargetTests(unittest.TestCase):
    def test_not_connected(self):
        stub = make_stub()
        self.assertIsNone(stub._capture_run_target())
        stub._run_target = RunTarget(mock.Mock(), info())  # stale target, no engine
        self.assertIsNone(stub._capture_run_target())

    def test_no_engine_attribute(self):
        stub = GUI.__new__(GUI)
        self.assertIsNone(stub._capture_run_target())

    def test_same_object_returned(self):
        stub = make_stub()
        e = mock.Mock()
        stub._replace_engine(e, info())
        self.assertIs(stub._capture_run_target(), stub._run_target)

    def test_engine_set_directly_gives_target_without_info(self):
        stub = make_stub()
        e = mock.Mock()
        stub.engine = e  # e.g. tests that set stub.engine directly
        self.assertEqual(stub._capture_run_target(), RunTarget(e, None))

    def test_mismatched_target_engine(self):
        stub = make_stub()
        a, b = mock.Mock(name="a"), mock.Mock(name="b")
        stub._run_target = RunTarget(a, info())
        stub.engine = b
        captured = stub._capture_run_target()
        self.assertIs(captured.engine, b)
        self.assertIsNone(captured.info)


if __name__ == "__main__":
    unittest.main()
