"""R13-T4: Connect / "ทดสอบการเชื่อมต่อ" errors never show the password.

R13-AC-1 .. R13-AC-6 (Round 13). No Tk window, no database: the GUI is a stub
from DatabaseConnectorGUI.__new__ (make_stub of the Round 11 tests),
create_engine / messagebox / ui_dialog / ui_round_frame / tk.Label / print
are patched. Nothing is written outside the test process.
"""

import os
import re
import sys
import unittest
from typing import Any, Dict, List, Tuple
from unittest import mock
from urllib.parse import quote_plus

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import database_connect_gui as app  # noqa: E402
from test_r11_connection_target_snapshot import UAT_SCREEN, make_stub  # noqa: E402

GUI = app.DatabaseConnectorGUI

# ---------------------------------------------------------------- shared data
PW = "S3cr;t}PW-13"  # ; and } -> ODBC writes {S3cr;t}}PW-13}
LEAKS = (PW, quote_plus(PW), "S3cr", "PW-13", "}}PW-13", "%7D%7DPW-13")
ODBC = app.build_sqlserver_odbc_connect("D", "h", "1", "db", "u", PW) + ";Encrypt=yes"
ERR1 = (
    "(pyodbc.InterfaceError) ('28000', \"[Microsoft][ODBC Driver 17 for SQL Server] "
    f"{ODBC} ... Login failed for user 'u'. (18456)\")"
)
ERR2 = "mssql+pyodbc:///?odbc_connect=" + quote_plus(ODBC) + " Login failed for user 'u'."
ERR3 = "bad password S3cr;t}PW-13 for u"
# (label, error text, words that must survive)
SECRET_ERRORS: Tuple[Tuple[str, str, Tuple[str, ...]], ...] = (
    ("odbc_raw", ERR1, ("Login failed for user 'u'",)),
    ("odbc_connect_url", ERR2, ("Login failed for user 'u'",)),
    ("verbatim", ERR3, ("bad password", "for u")),
)
PLAIN_ERRORS = (
    'could not translate host name "x" to address',
    "Login timeout expired",
    "(Background on this error at: https://sqlalche.me/e/20/e3q8)",
)
CONNECT_PREFIX = "❌ Connection Error: "
TEST_FAIL_PREFIX = "✕  เชื่อมต่อไม่สำเร็จ: "
SCREEN = dict(UAT_SCREEN, db_password=PW)


class _LeakAsserts(unittest.TestCase):
    def assert_no_leak(self, texts: List[str]) -> None:
        for text in texts:
            for leak in LEAKS:
                self.assertNotIn(leak, text)

    def assert_kept(self, text: str, keep: Tuple[str, ...]) -> None:
        for word in keep:
            self.assertIn(word, text)


# ---------------------------------------------------------------- connect_database
class _ConnectBase(_LeakAsserts):
    def setUp(self) -> None:
        self.prints: List[str] = []

    def _print(self, *args: Any, **_kw: Any) -> None:
        self.prints.append(" ".join(str(a) for a in args))

    def connect_failing(self, stub: Any, error: BaseException, where: str = "connect"):
        """Real connect_database; `where` = connect | create_engine | connection_string."""
        engine = mock.MagicMock(name="engine_new")
        engine.connect.side_effect = error
        ce_kw: Dict[str, Any] = dict(return_value=engine)
        if where == "create_engine":
            ce_kw = dict(side_effect=error)
        if where == "connection_string":
            stub.get_connection_string = mock.Mock(side_effect=error)
        with mock.patch.object(app, "create_engine", **ce_kw), \
                mock.patch.object(app, "messagebox") as mb, \
                mock.patch("builtins.print", side_effect=self._print):
            stub.connect_database()
        return engine, mb


class ConnectDatabaseRedactionTests(_ConnectBase):
    # R13-AC-1
    def test_ac1_execution_log_and_prints_have_no_password(self):
        for label, err, keep in SECRET_ERRORS:
            with self.subTest(error=label):
                stub = make_stub(SCREEN)
                self.prints = []
                engine, mb = self.connect_failing(stub, RuntimeError(err))
                inserted = stub.results_text.inserted
                self.assert_no_leak(inserted + self.prints)
                errors = [t for t in inserted if t.startswith(CONNECT_PREFIX)]
                self.assertEqual(len(errors), 1, inserted)
                self.assert_kept(errors[0], keep)
                # the dialog gets the same redacted text
                stub._show_connection_error.assert_called_once()
                shown = str(stub._show_connection_error.call_args.args[0])
                self.assert_no_leak([shown])
                self.assert_kept(shown, keep)
                self.assertEqual(errors[0], f"{CONNECT_PREFIX}{shown}\n\n")
                self.assert_no_leak([str(c) for c in mb.mock_calls])
                engine.dispose.assert_called_once_with()

    # R13-AC-3
    def test_ac3_create_engine_or_connection_string_raises(self):
        for where in ("create_engine", "connection_string"):
            with self.subTest(where=where):
                stub = make_stub(SCREEN)
                old = mock.MagicMock(name="engine_old")
                stub.engine = old
                stub.execute_btn.state = "normal"
                stub.inspect_btn.state = "normal"
                self.prints = []
                self.connect_failing(stub, RuntimeError(ERR1), where=where)
                inserted = stub.results_text.inserted
                self.assert_no_leak(inserted + self.prints)
                errors = [t for t in inserted if t.startswith(CONNECT_PREFIX)]
                self.assertEqual(len(errors), 1, inserted)
                self.assertIn("Login failed for user 'u'", errors[0])
                shown = str(stub._show_connection_error.call_args.args[0])
                self.assert_no_leak([shown])
                # behaviour kept: no engine, failed status, buttons off
                self.assertIsNone(stub.engine)
                self.assertIsNone(stub._run_target)
                old.dispose.assert_called_once_with()
                self.assertEqual(stub.status_label.text, "❌ Connection Failed")
                self.assertEqual(stub.execute_btn.state, "disabled")
                self.assertEqual(stub.inspect_btn.state, "disabled")

    # R13-AC-4
    def test_ac4_short_password_masked_by_pattern_only(self):
        err = ("[ODBC] DRIVER={D};SERVER=h,1;UID={u};PWD={pw1};Encrypt=yes "
               "Login failed for user 'u'. see pw1x table")
        stub = make_stub(dict(UAT_SCREEN, db_password="pw1"))
        self.connect_failing(stub, RuntimeError(err))
        errors = [t for t in stub.results_text.inserted if t.startswith(CONNECT_PREFIX)]
        self.assertEqual(len(errors), 1)
        self.assertIn("PWD=***;Encrypt=yes", errors[0])
        self.assertNotIn("{pw1}", errors[0])
        self.assertIn("see pw1x table", errors[0])  # 4-character rule kept
        self.assertIn("Login failed for user 'u'", errors[0])

    # R13-AC-6
    def test_ac6_plain_errors_unchanged(self):
        for err in PLAIN_ERRORS:
            with self.subTest(error=err):
                stub = make_stub(SCREEN)
                self.connect_failing(stub, RuntimeError(err))
                self.assertIn(f"{CONNECT_PREFIX}{err}\n\n", stub.results_text.inserted)
                stub._show_connection_error.assert_called_once()
                self.assertEqual(str(stub._show_connection_error.call_args.args[0]), err)


# R13-AC-2
class ConnectionErrorDialogTests(_ConnectBase):
    def run_dialog(self, err: str) -> Tuple[Dict[str, Any], List[str], List[str]]:
        stub = make_stub(SCREEN)
        del stub._show_connection_error  # the real dialog builder
        calls: Dict[str, Any] = {}
        labels: List[str] = []

        def fake_dialog(parent, title, heading, subtitle="", **kw):
            calls.update(kw, title=title, heading=heading, subtitle=subtitle)
            kw["build_body"](mock.MagicMock(name="frame"))
            return None

        def fake_label(*_a, **kw):
            labels.append(str(kw.get("text", "")))
            return mock.MagicMock(name="label")

        with mock.patch.object(app, "ui_dialog", side_effect=fake_dialog), \
                mock.patch.object(app, "ui_round_frame",
                                  return_value=(mock.MagicMock(), mock.MagicMock())), \
                mock.patch.object(app.tk, "Label", side_effect=fake_label):
            self.connect_failing(stub, RuntimeError(err))
        self.assertTrue(calls, "ui_dialog was not called")
        return calls, labels, stub.results_text.inserted

    def test_ac2_dialog_message_subtitle_and_labels_have_no_password(self):
        for label, err, keep in SECRET_ERRORS:
            with self.subTest(error=label):
                calls, labels, inserted = self.run_dialog(err)
                texts = [str(calls["message"]), str(calls["subtitle"]),
                         str(calls["heading"]), str(calls["title"])] + labels + inserted
                self.assert_no_leak(texts)
                red_box = labels[0]  # the first Label is the red box with the error
                self.assert_kept(red_box, keep)
                self.assert_kept(str(calls["message"]), keep)

    def test_ac2_cut_at_400_happens_after_redaction(self):
        # Raw text placed so that character 399 falls just after "PW-13" (before
        # its closing brace): cutting first would leave "...}PW-13" visible.
        end_of_secret = ERR1.index("PW-13}") + len("PW-13")
        cases = {
            "secret_at_cut": "x" * (399 - end_of_secret - 1) + " " + ERR1,
            "secret_past_cut": "x" * 500 + " " + ERR1,
            "secret_near_end": "y" * 380 + " " + ERR1,
        }
        self.assertEqual(cases["secret_at_cut"][:399][-5:], "PW-13")
        for label, err in cases.items():
            with self.subTest(case=label):
                calls, labels, inserted = self.run_dialog(err)
                red_box = labels[0]
                self.assertLessEqual(len(red_box), 400)
                self.assertTrue(red_box.endswith("…"), red_box[-20:])
                self.assert_no_leak(labels + [str(calls["message"])] + inserted)
                self.assertNotIn("PW-1", red_box)
                self.assertNotIn("S3c", red_box)


# ---------------------------------------------------------------- _run_connection_test
class RunConnectionTestTests(_LeakAsserts):
    """R13-AC-5 / R13-AC-6: New Profile "ทดสอบการเชื่อมต่อ" result text."""

    ARGS = ("PostgreSQL", "u", PW, "h", "5432", "db")

    def run_test(self, error: BaseException = None, where: str = "connect",
                 args: Tuple[str, ...] = ARGS):
        stub = make_stub(SCREEN)
        engine = mock.MagicMock(name="probe_engine")
        ce_kw: Dict[str, Any] = dict(return_value=engine)
        if error is not None and where == "connect":
            engine.connect.side_effect = error
        elif error is not None:
            ce_kw = dict(side_effect=error)
        with mock.patch.object(app, "create_engine", **ce_kw) as ce, \
                mock.patch("builtins.print") as pr:
            ok, msg = GUI._run_connection_test(stub, *args)
        for call in pr.call_args_list:
            self.assert_no_leak([str(call)])
        return ok, msg, engine, ce

    def test_ac5_errors_with_password_are_redacted(self):
        for where in ("connect", "create_engine"):
            for label, err, keep in SECRET_ERRORS:
                with self.subTest(where=where, error=label):
                    ok, msg, engine, _ce = self.run_test(RuntimeError(err), where)
                    self.assertIs(ok, False)
                    self.assertTrue(msg.startswith(TEST_FAIL_PREFIX), msg)
                    self.assertLessEqual(len(msg), 300)
                    self.assert_no_leak([msg])
                    self.assert_kept(msg, keep)
                    if where == "connect":
                        engine.dispose.assert_called_once_with()

    def test_ac5_multiline_first_line_blank(self):
        err = "\n   \n" + ERR1 + "\nsecond line PWD={S3cr;t}}PW-13}"
        ok, msg, engine, _ce = self.run_test(RuntimeError(err))
        self.assertIs(ok, False)
        expected_line = app.redact_secrets(ERR1, PW).strip()
        self.assertEqual(msg, TEST_FAIL_PREFIX + expected_line)
        self.assertNotIn("second line", msg)
        self.assert_no_leak([msg])
        engine.dispose.assert_called_once_with()

    def test_ac5_multiline_secret_on_first_non_blank_line(self):
        err = "\n\nbad password S3cr;t}PW-13 for u\nnext"
        ok, msg, _e, _ce = self.run_test(RuntimeError(err))
        self.assertEqual(msg, TEST_FAIL_PREFIX + "bad password *** for u")

    def test_ac5_long_message_secret_near_the_end_cut_after_redaction(self):
        # raw message cut at 299 would end right after "PW-13" (before its "}")
        end_of_secret = ERR1.index("PW-13}") + len("PW-13")
        filler = 299 - len(TEST_FAIL_PREFIX) - end_of_secret - 1
        err = "z" * filler + " " + ERR1
        self.assertEqual((TEST_FAIL_PREFIX + err)[:299][-5:], "PW-13")
        for case, error_text in (("secret_at_cut", err), ("long_tail", "q" * 400 + ERR1)):
            with self.subTest(case=case):
                ok, msg, _e, _ce = self.run_test(RuntimeError(error_text))
                self.assertIs(ok, False)
                self.assertLessEqual(len(msg), 300)
                self.assertTrue(msg.endswith("…"))
                self.assert_no_leak([msg])
                self.assertNotIn("PW-1", msg)
                self.assertNotIn("S3c", msg)

    def test_ac5_success_message_and_dispose(self):
        ok, msg, engine, ce = self.run_test()
        self.assertIs(ok, True)
        self.assertRegex(msg, r"^✓  ทดสอบเชื่อมต่อสำเร็จ · PostgreSQL · \d+ ms$")
        engine.dispose.assert_called_once_with()
        conn = engine.connect.return_value.__enter__.return_value
        self.assertEqual(str(conn.execute.call_args.args[0]), "SELECT 1")
        self.assertEqual(ce.call_args.kwargs.get("connect_args"), {"timeout": 10})

    def test_ac5_oracle_success_uses_dual(self):
        args = ("Oracle", "u", PW, "h", "1521", "orcl")
        stub = make_stub(SCREEN)
        stub.get_connection_string = mock.Mock(return_value="oracle+x://")
        engine = mock.MagicMock(name="probe_engine")
        with mock.patch.object(app, "create_engine", return_value=engine):
            ok, msg = GUI._run_connection_test(stub, *args)
        self.assertIs(ok, True)
        self.assertTrue(re.match(r"^✓  ทดสอบเชื่อมต่อสำเร็จ · Oracle · \d+ ms$", msg), msg)
        conn = engine.connect.return_value.__enter__.return_value
        self.assertEqual(str(conn.execute.call_args.args[0]), "SELECT 1 FROM DUAL")
        engine.dispose.assert_called_once_with()

    def test_ac5_connection_string_never_in_result(self):
        # the URL built with the password goes to create_engine only
        _ok, msg, _e, ce = self.run_test(RuntimeError("boom"))
        self.assertIn(quote_plus(PW), ce.call_args.args[0])
        self.assertEqual(msg, TEST_FAIL_PREFIX + "boom")

    # R13-AC-6
    def test_ac6_plain_errors_unchanged(self):
        for err in PLAIN_ERRORS:
            with self.subTest(error=err):
                ok, msg, _e, _ce = self.run_test(RuntimeError(err))
                self.assertIs(ok, False)
                self.assertEqual(msg, TEST_FAIL_PREFIX + err)

    def test_new_profile_dialog_uses_the_helper(self):
        import inspect as pyinspect

        body = pyinspect.getsource(GUI.new_profile_dialog)
        self.assertIn("self._run_connection_test(", body)
        self.assertNotIn("str(error).splitlines()", body)


if __name__ == "__main__":
    unittest.main()
