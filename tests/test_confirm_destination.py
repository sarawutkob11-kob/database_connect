"""T11: confirm dialog and Run log show the run's real destination (AC-10, AC-11, AC-35, R7).

The screen fields are changed after Connect; the snapshot (RunTarget.info)
must win. ui_dialog / tk.Label are patched, _write_run_log is captured.
"""

import ast
import inspect
import os
import sys
import textwrap
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import database_connect_gui as app  # noqa: E402
from test_run_target import (  # noqa: E402
    capture_confirm_dialog,
    make_stub,
    shown_destination,
)

GUI = app.DatabaseConnectorGUI
ConnectionInfo = app.ConnectionInfo
RunTarget = app.RunTarget
SECRET = "secret"
DML = [{"name": "J1", "query": "UPDATE t SET a = 1"}]


def connected_stub():
    """Connected to P1 / Oracle / host1 / SVC; afterwards the screen says P2 / host2."""
    stub = make_stub(profile="P2", db_type="MySQL", user="other", host="host2",
                     port="3306", database="OTHERDB")
    stub.db_password.set(SECRET)
    engine = mock.Mock(name="engine_P1")
    stub.engine = engine
    stub._run_target = RunTarget(
        engine, ConnectionInfo("P1", "Oracle", "scott", "host1", "1521", "SVC")
    )
    return stub


def all_dialog_text(labels, captured) -> str:
    parts = [str(t) for t in labels if t is not None]
    parts += [str(a) for a in captured["args"]]
    parts += [str(v) for v in captured["kw"].values()]
    return "\n".join(parts)


class ConfirmDestinationTests(unittest.TestCase):
    """AC-10"""

    def test_destination_from_snapshot(self):
        stub = connected_stub()
        self.assertEqual(GUI._confirm_destination(stub._run_target),
                         ("P1", "Oracle · host1 / SVC"))
        self.assertEqual(stub._confirm_destination(stub._run_target),
                         ("P1", "Oracle · host1 / SVC"))

    def test_dialog_shows_host1_never_host2_or_password(self):
        for pass_target in (True, False):
            with self.subTest(pass_target=pass_target):
                stub = connected_stub()
                kw = {"target": stub._run_target} if pass_target else {}
                result, labels, captured = capture_confirm_dialog(stub, DML, **kw)
                self.assertIs(result, False)
                self.assertEqual(shown_destination(labels), ("P1", "Oracle · host1 / SVC"))
                text = all_dialog_text(labels, captured)
                self.assertIn("message", captured["kw"])
                for forbidden in ("host2", SECRET, "P2", "OTHERDB", "MySQL"):
                    self.assertNotIn(forbidden, text)

    def test_select_only_is_not_prompted(self):
        stub = connected_stub()
        with mock.patch.object(app, "ui_dialog") as dlg:
            self.assertIs(stub._confirm_data_change([{"name": "S", "query": "SELECT 1"}]), True)
        dlg.assert_not_called()

    def test_dialog_result_is_returned(self):
        stub = connected_stub()
        with mock.patch.object(app, "ui_dialog", return_value=True), \
                mock.patch.object(app, "ui_round_frame", return_value=(mock.Mock(), mock.Mock())):
            self.assertIs(stub._confirm_data_change(DML, target=stub._run_target), True)

    def test_screen_fields_not_read(self):
        stub = connected_stub()
        for name in ("db_type", "db_user", "db_password", "db_host", "db_port", "db_name",
                     "profile_combo"):
            field = mock.Mock(name=name)
            field.get.side_effect = AssertionError(f"{name} read")
            setattr(stub, name, field)
        _r, labels, _c = capture_confirm_dialog(stub, DML)
        self.assertEqual(shown_destination(labels), ("P1", "Oracle · host1 / SVC"))
        written = []
        stub._write_run_log = written.append
        stub._log_run_context()
        self.assertEqual(len(written), 1)


class ProfileSnapshotTests(unittest.TestCase):
    """AC-11"""

    def test_combo_changed_after_connect_shows_p1(self):
        for pass_target in (True, False):
            with self.subTest(pass_target=pass_target):
                stub = connected_stub()
                stub.profile_combo.set("P2")
                kw = {"target": stub._run_target} if pass_target else {}
                _r, labels, _c = capture_confirm_dialog(stub, DML, **kw)
                self.assertEqual(shown_destination(labels)[0], "P1")

    def test_real_connect_then_switch_combo(self):
        from sqlalchemy import create_engine as real_create_engine

        stub = make_stub(profile="P1", db_type="PostgreSQL", user="u", host="host1",
                         port="5432", database="db1")
        engine = real_create_engine("sqlite://")
        self.addCleanup(engine.dispose)
        with mock.patch.object(app, "create_engine", return_value=engine), \
                mock.patch.object(app, "messagebox"):
            stub.connect_database()
        stub.profile_combo.set("P2")
        stub.db_host.set("host2")
        _r, labels, _c = capture_confirm_dialog(stub, DML)
        self.assertEqual(shown_destination(labels), ("P1", "PostgreSQL · host1 / db1"))

    def test_empty_profile_shows_dash(self):
        stub = connected_stub()
        stub._run_target = RunTarget(stub.engine,
                                     ConnectionInfo("", "Oracle", "u", "h", "", ""))
        _r, labels, _c = capture_confirm_dialog(stub, DML)
        self.assertEqual(shown_destination(labels), ("-", "Oracle · h"))


class RunLogTests(unittest.TestCase):
    """AC-35"""

    def test_run_line_from_snapshot(self):
        for pass_target in (True, False):
            with self.subTest(pass_target=pass_target):
                stub = connected_stub()
                written = []
                stub._write_run_log = written.append
                if pass_target:
                    stub._log_run_context(stub._run_target)
                else:
                    stub._log_run_context(target=None)
                self.assertEqual(len(written), 1)
                line = written[0]
                self.assertIn("===== RUN", line)
                self.assertIn("profile=P1", line)
                self.assertIn("host1", line)
                for forbidden in ("P2", "host2", SECRET, "OTHERDB", "MySQL"):
                    self.assertNotIn(forbidden, line)
                self.assertEqual(
                    line, "\n===== RUN  profile=P1  Oracle  scott@host1:1521/SVC =====\n"
                )

    def test_start_stoppable_run_logs_snapshot(self):
        import threading

        stub = connected_stub()
        stub._stop_event = threading.Event()
        written = []
        stub._write_run_log = written.append
        stub._start_stoppable_run(target=stub._run_target)
        self.assertEqual(written,
                         ["\n===== RUN  profile=P1  Oracle  scott@host1:1521/SVC =====\n"])

    def test_given_target_wins_over_current(self):
        stub = connected_stub()
        other = RunTarget(mock.Mock(), ConnectionInfo("PX", "MySQL", "x", "hx", "", ""))
        written = []
        stub._write_run_log = written.append
        stub._log_run_context(other)
        self.assertIn("profile=PX", written[0])
        self.assertNotIn("P1", written[0])


class NoInfoTests(unittest.TestCase):
    """R7: engine without ConnectionInfo / not connected -> '-'"""

    def test_confirm_destination_none(self):
        self.assertEqual(GUI._confirm_destination(None), ("-", "-"))
        self.assertEqual(GUI._confirm_destination(RunTarget(mock.Mock(), None)), ("-", "-"))

    def test_dialog_with_engine_but_no_info(self):
        stub = make_stub(host="host2")
        stub.engine = mock.Mock()  # set directly: RunTarget(engine, None)
        _r, labels, captured = capture_confirm_dialog(stub, DML)
        self.assertEqual(shown_destination(labels), ("-", "-"))
        self.assertNotIn("host2", all_dialog_text(labels, captured))

    def test_dialog_with_no_engine(self):
        stub = make_stub(host="host2")
        stub.engine = None
        _r, labels, _c = capture_confirm_dialog(stub, DML)
        self.assertEqual(shown_destination(labels), ("-", "-"))

    def test_log_without_info_or_engine(self):
        for engine in (None, mock.Mock()):
            with self.subTest(engine=engine):
                stub = make_stub(profile="P2", host="host2")
                stub.engine = engine
                written = []
                stub._write_run_log = written.append
                stub._log_run_context()
                self.assertEqual(written, ["\n===== RUN  profile=-  -  - =====\n"])

    def test_log_with_target_without_info(self):
        stub = make_stub(profile="P2", host="host2")
        written = []
        stub._write_run_log = written.append
        stub._log_run_context(RunTarget(mock.Mock(), None))
        self.assertEqual(written, ["\n===== RUN  profile=-  -  - =====\n"])

    def test_bare_stub_does_not_crash(self):
        stub = GUI.__new__(GUI)
        written = []
        stub._write_run_log = written.append
        stub._log_run_context()
        self.assertEqual(written, ["\n===== RUN  profile=-  -  - =====\n"])


class CallersPassTargetTests(unittest.TestCase):
    """Every run entry passes the same captured target to confirm and start."""

    EXPECTED = {
        "execute_query": ("_confirm_data_change", "_start_stoppable_run"),
        "run_job": ("_confirm_data_change", "_start_stoppable_run"),
        "run_selected_job": ("_confirm_data_change", "_start_stoppable_run"),
        "export_jobs_to_excel": ("_start_stoppable_run",),
    }

    def test_target_keyword_passed(self):
        for method, callees in self.EXPECTED.items():
            with self.subTest(method=method):
                tree = ast.parse(textwrap.dedent(inspect.getsource(getattr(GUI, method))))
                captures = [
                    n for n in ast.walk(tree)
                    if isinstance(n, ast.Assign) and isinstance(n.value, ast.Call)
                    and isinstance(n.value.func, ast.Attribute)
                    and n.value.func.attr == "_capture_run_target"
                ]
                self.assertEqual(len(captures), 1)
                target_name = captures[0].targets[0].id
                for callee in callees:
                    calls = [
                        n for n in ast.walk(tree)
                        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                        and n.func.attr == callee
                    ]
                    self.assertEqual(len(calls), 1, callee)
                    kw = {k.arg: k.value for k in calls[0].keywords}
                    self.assertIn("target", kw, callee)
                    self.assertIsInstance(kw["target"], ast.Name)
                    self.assertEqual(kw["target"].id, target_name)


if __name__ == "__main__":
    unittest.main()
