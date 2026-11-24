"""R13-T4: Tables errors use the worker's password; redact_secrets patterns.

R13-AC-7, R13-AC-8, R13-AC-9, R13-AC-10, R13-AC-12 (Round 13). No Tk window,
no database: stub GUI from the Round 11 tests, threading.Thread captured and
run by hand, root.after callbacks run by hand, create_engine / inspect /
messagebox / print patched (nothing reaches the real console).
"""

import inspect as pyinspect
import os
import sys
import unittest
import urllib.parse
from typing import Any, Callable, List, Tuple
from unittest import mock
from urllib.parse import quote_plus

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import database_connect_gui as app  # noqa: E402
from test_r11_connection_target_snapshot import (  # noqa: E402
    UAT_SCREEN, _Thread, make_stub,
)
from test_r13_connect_redaction import (  # noqa: E402
    ERR1, ERR2, ERR3, LEAKS, PW, SECRET_ERRORS,
)

GUI = app.DatabaseConnectorGUI
ConnectionInfo = app.ConnectionInfo
RunTarget = app.RunTarget

PG_ALL_INFO = ConnectionInfo(
    profile="P1", db_type="PostgreSQL", user="app", host="uat-db", port="5432", database="",
)
OTHER_PW = "Other-pass-99"


class _TablesBase(unittest.TestCase):
    def setUp(self) -> None:
        self.prints: List[str] = []
        self.after_calls: List[Tuple[Any, Callable[[], None]]] = []

    def _print(self, *args: Any, **_kw: Any) -> None:
        self.prints.append(" ".join(str(a) for a in args))

    def assert_no_leak(self, texts: List[str]) -> None:
        for text in texts:
            for leak in LEAKS:
                self.assertNotIn(leak, text)

    def start(self, stub: Any) -> _Thread:
        threads: List[_Thread] = []

        def make_thread(target, args=(), daemon=None):
            thread = _Thread(target, args, daemon)
            threads.append(thread)
            return thread

        with mock.patch.object(app.threading, "Thread", side_effect=make_thread), \
                mock.patch.object(app, "messagebox"), \
                mock.patch("builtins.print", side_effect=self._print):
            stub.list_tables()
        self.assertEqual(len(threads), 1)
        return threads[0]

    def run_worker(self, thread: _Thread, inspect_kw: dict, create_engine: Any = None) -> None:
        with mock.patch.object(app, "inspect", **inspect_kw), \
                mock.patch.object(app, "create_engine",
                                  return_value=create_engine or mock.MagicMock()), \
                mock.patch("builtins.print", side_effect=self._print):
            thread.run()

    def run_after_callbacks(self, stub: Any):
        with mock.patch.object(app, "messagebox") as mb:
            for call in list(stub.root.after.call_args_list):
                if call.args and call.args[0] == 0:
                    call.args[1]()
        return mb


# R13-AC-7
class WorkerPasswordFromFieldTests(_TablesBase):
    def test_ac7_run_target_without_info_uses_worker_password(self):
        for label, err, _keep in SECRET_ERRORS:
            with self.subTest(error=label):
                self.setUp()
                stub = make_stub(dict(UAT_SCREEN, db_password=PW))  # db_name "UAT"
                engine = mock.MagicMock(name="engine")
                stub.engine = engine
                stub._run_target = RunTarget(engine, None)
                self.assertFalse(hasattr(stub, "_connected_password"))
                del stub.on_list_tables_error  # the real handler
                thread = self.start(stub)
                self.assertEqual(thread.args[0][1], PW)  # the worker holds PW
                self.run_worker(thread, dict(side_effect=RuntimeError(err)))
                stub.on_list_tables_success.assert_not_called()
                mb = self.run_after_callbacks(stub)
                mb.showerror.assert_called_once()
                texts = stub.results_text.inserted + [str(c) for c in mb.mock_calls]
                texts += self.prints
                self.assert_no_leak(texts)
                if label == "verbatim":
                    errors = [t for t in stub.results_text.inserted if t.startswith("❌ Error: ")]
                    self.assertEqual(errors, ["❌ Error: bad password *** for u\n\n"])
                    self.assertEqual(mb.showerror.call_args.args[1],
                                     "Failed to list tables:\nbad password *** for u")
                self.assertEqual(stub.inspect_btn.state, "normal")


# R13-AC-8
class StoredPasswordChangedTests(_TablesBase):
    def test_ac8_stored_password_replaced_before_callback(self):
        stub = make_stub(dict(UAT_SCREEN, db_password="screen-pw-xx"))
        engine = mock.MagicMock(name="engine_pg")
        stub._replace_engine(engine, PG_ALL_INFO, password=PW)
        del stub.on_list_tables_error
        thread = self.start(stub)
        self.assertEqual(thread.args[0][1], PW)  # list-all mode: worker holds PW
        # The worker fails outside the per-database handlers: scheduling the
        # success callback raises (verbatim password in the text, no PWD=)
        state = {"first": True}

        def after(delay, callback):
            if state["first"]:
                state["first"] = False
                raise RuntimeError(ERR3)
            self.after_calls.append((delay, callback))

        stub.root.after = mock.Mock(side_effect=after)
        engine.connect.return_value.__enter__.return_value.execute.return_value = []
        self.run_worker(thread, dict(return_value=mock.Mock()))
        self.assertEqual(len(self.after_calls), 1)
        # Connect again with another password before the callback runs
        stub._connected_password = (engine, OTHER_PW)
        with mock.patch.object(app, "messagebox") as mb:
            self.after_calls[0][1]()
        mb.showerror.assert_called_once()
        texts = stub.results_text.inserted + [str(c) for c in mb.mock_calls] + self.prints
        self.assert_no_leak(texts)
        self.assertIn("❌ Error: bad password *** for u\n\n", stub.results_text.inserted)

    def test_ac8_two_argument_call_still_works(self):
        for label, err, _keep in SECRET_ERRORS:
            with self.subTest(error=label):
                stub = make_stub()
                stub._replace_engine(mock.MagicMock(), PG_ALL_INFO, password=PW)
                dialog = mock.Mock(name="loading")
                with mock.patch.object(app, "messagebox") as mb:
                    GUI.on_list_tables_error(stub, RuntimeError(err), dialog)
                dialog.destroy.assert_called_once_with()
                self.assert_no_leak(stub.results_text.inserted
                                    + [str(c) for c in mb.mock_calls])
                self.assertEqual(stub.inspect_btn.state, "normal")

    def test_ac8_worker_password_only_no_stored(self):
        stub = make_stub()
        with mock.patch.object(app, "messagebox") as mb:
            GUI.on_list_tables_error(stub, RuntimeError(ERR3), mock.Mock(), PW)
        self.assertEqual(stub.results_text.inserted, ["❌ Error: bad password *** for u\n\n"])
        self.assert_no_leak([str(c) for c in mb.mock_calls])

    def test_ac8_none_password_and_stored_none(self):
        stub = make_stub()
        stub._connected_password = None
        with mock.patch.object(app, "messagebox") as mb:
            GUI.on_list_tables_error(stub, RuntimeError("plain failure"), mock.Mock(), None)
        self.assertEqual(stub.results_text.inserted, ["❌ Error: plain failure\n\n"])
        mb.showerror.assert_called_once_with("Error", "Failed to list tables:\nplain failure")


# developer request: log_error in all 3 worker except blocks, no NameError
class WorkerLogErrorTests(_TablesBase):
    def _all_db_stub(self, names):
        stub = make_stub(dict(UAT_SCREEN, db_password="screen-pw-xx"))
        engine = mock.MagicMock(name="engine_pg")
        conn = engine.connect.return_value.__enter__.return_value
        conn.execute.return_value = [(n,) for n in names]
        stub._replace_engine(engine, PG_ALL_INFO, password=PW)
        return stub, engine

    def assert_logged(self, needle: str) -> None:
        joined = "\n".join(self.prints)
        self.assertIn(needle, joined)
        self.assertIn("Traceback (most recent call last)", joined)
        self.assertNotIn("NameError", joined)
        self.assert_no_leak(self.prints)

    def test_database_list_error_is_logged_redacted(self):
        stub, engine = self._all_db_stub([])
        engine.connect.side_effect = RuntimeError(ERR1)
        thread = self.start(stub)
        self.run_worker(thread, dict(return_value=mock.Mock()))
        self.run_after_callbacks(stub)
        stub.on_list_tables_error.assert_not_called()
        stub.on_list_tables_success.assert_called_once()
        self.assert_logged("ERROR getting database list for PostgreSQL")
        self.assert_logged("Login failed for user 'u'")

    def test_schema_and_database_errors_are_logged_redacted(self):
        stub, _engine = self._all_db_stub(["d1", "d2"])
        stub.get_connect_args = mock.Mock(return_value={})

        def conn_str(*args):
            if args[-1] == "d2":
                raise RuntimeError(ERR2)
            return "cs-d1"

        stub.get_connection_string = mock.Mock(side_effect=conn_str)
        inspector = mock.Mock(name="temp_inspector")
        inspector.get_schema_names.return_value = ["s1"]
        inspector.get_table_names.side_effect = RuntimeError(ERR3)
        thread = self.start(stub)
        self.run_worker(thread, dict(return_value=inspector))
        self.run_after_callbacks(stub)
        stub.on_list_tables_error.assert_not_called()
        stub.on_list_tables_success.assert_called_once()
        self.assertEqual(stub.on_list_tables_success.call_args.args[0], [])
        self.assert_logged("❌ Error reading schema 's1': bad password *** for u")
        self.assert_logged("❌ ERROR accessing database d2: mssql+pyodbc")
        self.assertEqual(stub.get_connection_string.call_args_list[0].args[2], PW)


# R13-AC-9
class SourceStyleTests(unittest.TestCase):
    def test_ac9_redact_lines_short_and_module_import(self):
        path = app.__file__
        with open(path, encoding="utf-8") as handle:
            lines = handle.read().splitlines()
        hits = [(n, ln) for n, ln in enumerate(lines, start=1) if "redact_secrets(" in ln]
        self.assertGreaterEqual(len(hits), 6)
        for number, line in hits:
            with self.subTest(line=number):
                self.assertLessEqual(len(line), 95, line)
        self.assertNotIn("import", pyinspect.getsource(app.redact_secrets))
        self.assertIs(app.quote_plus, urllib.parse.quote_plus)


# R13-AC-10
class PatternTests(unittest.TestCase):
    def test_ac10_exact_results(self):
        cases = [
            ("password = 'x y'", "password = '***'"),
            ('PWD="a;b"', 'PWD="***"'),
            ("password='abc", "password='***"),
            ("DB_PASSWORD=abc next", "DB_PASSWORD=*** next"),
            ("MY_PWD=abc;", "MY_PWD=***;"),
            ("http://host:8080/a@b", "http://host:8080/a@b"),
            ("see http://h:80/x?y=a@b", "see http://h:80/x?y=a@b"),
            ("postgresql://u:p%40ss@h/db", "postgresql://u:***@h/db"),
        ]
        for text, expected in cases:
            with self.subTest(text=text):
                self.assertEqual(app.redact_secrets(text), expected)

    def test_ac10_more_edges(self):
        cases = [
            ("", ""),
            ("PWD=", "PWD=***"),
            ("NEWPWD=abc", "NEWPWD=abc"),  # letter before PWD: not a key
            ('x password="q" y', 'x password="***" y'),
            ("Password = abc;", "Password = ***;"),
        ]
        for text, expected in cases:
            with self.subTest(text=text):
                self.assertEqual(app.redact_secrets(text), expected)

    def test_ac10_secret_errors_without_known_secret(self):
        # the patterns alone hide the ODBC forms of PW
        for err in (ERR1, ERR2):
            with self.subTest(err=err[:20]):
                out = app.redact_secrets(err)
                for leak in LEAKS:
                    self.assertNotIn(leak, out)
                self.assertIn("Login failed for user 'u'", out)

    # R13-AC-12
    def test_ac12_known_limits_pinned(self):
        self.assertEqual(app.redact_secrets("postgresql://u:p@ss@h/db"),
                         "postgresql://u:***@ss@h/db")
        self.assertEqual(app.redact_secrets("testing table test_x", "test"),
                         "***ing table ***_x")
        out = app.redact_secrets("postgresql://u:p@ss@h/db", "p@ss")
        self.assertNotIn("p@ss", out)

    def test_known_secret_and_encoded_form(self):
        self.assertEqual(app.redact_secrets(f"a {PW} b {quote_plus(PW)} c", PW),
                         "a *** b *** c")
        self.assertEqual(app.redact_secrets(ERR3, PW), "bad password *** for u")


if __name__ == "__main__":
    unittest.main()
