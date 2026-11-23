"""R14-T3: Run (P1-P6) and Stop (P12) errors never show the password.

R14-AC-1 .. R14-AC-6, R14-AC-13 / R14-AC-14 (Run), R14-AC-15, R14-AC-16 (P1-P6,
P12), R14-AC-17 (static part). No Tk window and no database: the GUI is a stub
from DatabaseConnectorGUI.__new__ (make_stub of tests/test_run_engine.py),
threading.Thread only keeps the worker until the test runs it, tk widgets /
messagebox / print are patched, read_sql_dataframe raises inside a real
function (real traceback). Nothing is written to disk.

Shared constants and helpers here are also used by test_r14_jobs_redaction.py
and test_r14_export_redaction.py.
"""

import dataclasses
import os
import re
import sys
import threading
import unittest
from typing import Any, Dict, List
from unittest import mock
from urllib.parse import quote_plus

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import database_connect_gui as app  # noqa: E402
import test_run_engine as tre  # noqa: E402

GUI = app.DatabaseConnectorGUI

# ---------------------------------------------------------------- shared data
PW = "S3cr;t}PW-14"  # ; and } -> ODBC writes {S3cr;t}}PW-14}
LEAKS = (PW, quote_plus(PW), "S3cr", "PW-14", "}}PW-14", "%7D%7DPW-14")
OTHER_PW = "Other-PW-99"  # the password of the engine after a reconnect
FIELD_PW = "field-pw-x"  # what the Password field shows (never the run's password)
ODBC = app.build_sqlserver_odbc_connect("D", "h", "1", "db", "u", PW) + ";Encrypt=yes"
ERR1 = (
    "(pyodbc.InterfaceError) ('28000', \"[Microsoft][ODBC Driver 17 for SQL Server] "
    f"{ODBC} ... Login failed for user 'u'. (18456)\")"
)
ERR2 = "mssql+pyodbc:///?odbc_connect=" + quote_plus(ODBC) + " Login failed for user 'u'."
ERR3 = "bad password S3cr;t}PW-14 for u"
# (label, error text, words that must survive)
SECRET_ERRORS = (
    ("odbc_raw", ERR1, ("Login failed for user 'u'",)),
    ("odbc_connect_url", ERR2, ("Login failed for user 'u'",)),
    ("verbatim", ERR3, ("bad password", "for u")),
)
PATTERN_ERRORS = SECRET_ERRORS[:2]  # masked even without a known password
SQLA_ERR = (
    "(sqlite3.OperationalError) no such table: x\n"
    "[SQL: SELECT 1]\n"
    "(Background on this error at: https://sqlalche.me/e/20/f405)"
)
PLAIN_ERRORS = (
    ("ora_00942", "ORA-00942: table or view does not exist"),
    ("host_name", 'could not translate host name "x" to address'),
    ("sqlalchemy", SQLA_ERR),
)
SQL = "SELECT a FROM t WHERE note = 'x'"
_TIMES = re.compile(r"\d+\.\d+")


def identity_redact(text, *_secrets):
    """Stand-in for redact_secrets: the behaviour before Round 14 (no masking)."""
    return str(text)


def normalize(value: Any) -> Any:
    """Durations differ between two runs; everything else must be equal."""
    if isinstance(value, str):
        return _TIMES.sub("N.NN", value)
    if isinstance(value, (list, tuple)):
        return [normalize(v) for v in value]
    if isinstance(value, dict):
        return {k: normalize(v) for k, v in value.items()}
    return value


class _Engine:
    """Engine stand-in; only the dialect name is read (debug print)."""

    def __init__(self, name):
        self.name = name
        self.dialect = type("Dialect", (), {"name": "sqlite"})()


E = _Engine("E")
E2 = _Engine("E2")


class _CountingEntry:
    """Password field: counts every get()."""

    def __init__(self, value):
        self.value = value
        self.get_calls = 0

    def get(self, *_a):
        self.get_calls += 1
        return self.value


def raiser(err: str):
    def _raise(*_a, **_kw):
        raise RuntimeError(err)

    return _raise


def make_dialog(open_=True):
    dialog = mock.MagicMock(name="loading_dialog")
    dialog.winfo_exists.return_value = open_
    dialog.button_frame.winfo_children.return_value = []
    return dialog


def make_r14_stub(engine=E, password=PW, owner=None, debug=False):
    """make_stub + the stored Connect password (owner, password) or None."""
    stub = tre.make_stub(engine)
    stub._connected_password = None if password is None else (owner or engine, password)
    stub.db_password = _CountingEntry(FIELD_PW)
    stub.debug_mode = tre._Var(debug)
    stub.sql_context = tre._Text(SQL)
    stub._write_run_log = mock.Mock(name="_write_run_log")
    return stub


def reconnect(stub):
    """What a Connect while the run waits does to the stub."""
    stub._connected_password = (E2, OTHER_PW)
    stub.engine = E2


class R14Case(unittest.TestCase):
    """print is patched in every test; leak checks never echo the text."""

    def setUp(self):
        self.prints: List[str] = []
        patcher = mock.patch("builtins.print", side_effect=self._print)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _print(self, *args, **_kw):
        self.prints.append(" ".join(str(a) for a in args))

    def assert_no_leak(self, label: str, texts) -> None:
        for number, text in enumerate(texts):
            text = str(text)
            for leak_no, leak in enumerate(LEAKS):
                if leak in text:
                    self.fail(f"{label}: password fragment #{leak_no} in item {number}")

    def assert_kept(self, label: str, text: str, keep) -> None:
        for word in keep:
            self.assertTrue(word in text, f"{label}: masked too much, lost {word!r}")

    def assert_same(self, label: str, actual: str, expected: str) -> None:
        """Equality without printing the values (they may hold the password)."""
        self.assertTrue(actual == expected, f"{label}: text differs")


# ---------------------------------------------------------------- Run harness
def run_query(stub, *, swap=False, dialog_open=True, enhanced_real=True,
              caller="execute_query", extra=None):
    """Run a query on the stub; the worker runs after the (optional) reconnect.

    caller: execute_query | bg_no_args | bg_engine (older callers of
    _execute_query_background that pass no password).
    Returns a dict of every destination.
    """
    dialog = make_dialog(dialog_open)
    stub._create_loading_dialog_with_retry = mock.Mock(return_value=dialog)
    if enhanced_real:
        del stub.on_query_error_enhanced  # the real handler
    threads = tre._ThreadCapture()
    with mock.patch.object(app.threading, "Thread", side_effect=threads), \
            mock.patch.object(app, "messagebox") as mb, \
            mock.patch.object(app.tk, "Button"):
        if caller == "execute_query":
            stub.execute_query()
        elif caller == "bg_no_args":
            stub._execute_query_background(SQL, dialog)
        else:
            stub._execute_query_background(SQL, dialog, engine=E, debug_mode=stub.debug_mode.get())
        started_gets = stub.db_password.get_calls
        if swap:
            reconnect(stub)
        threads.run_all()
        tre.run_after_calls(stub)
    return {
        "details": getattr(stub, "last_error_details", None),
        "inserted": list(stub.results_text.inserted),
        "run_log": [str(c) for c in stub._write_run_log.call_args_list],
        "showerror": [list(c.args) for c in mb.showerror.call_args_list],
        "gets_after_start": stub.db_password.get_calls - started_gets,
        "gets": stub.db_password.get_calls,
    }


def open_details_dialog(stub, details) -> Dict[str, Any]:
    """Real _show_error_details_dialog with fake widgets; presses Copy Error Details."""
    labels: List[str] = []
    texts: List[mock.MagicMock] = []
    buttons: List[dict] = []

    def label(*_a, **kw):
        labels.append(kw.get("text", ""))
        return mock.MagicMock()

    def text(*_a, **_kw):
        widget = mock.MagicMock()
        texts.append(widget)
        return widget

    def button(*_a, **kw):
        buttons.append(kw)
        return mock.MagicMock()

    with mock.patch.multiple(
        app.tk,
        Toplevel=mock.MagicMock(),
        Frame=mock.MagicMock(),
        LabelFrame=mock.MagicMock(),
        Scrollbar=mock.MagicMock(),
        Label=label,
        Text=text,
        Button=button,
    ), mock.patch.object(app, "messagebox"):
        GUI._show_error_details_dialog(stub, details)
        copy = [b["command"] for b in buttons if "Copy Error Details" in b.get("text", "")]
        copy[0]()
    return {
        "labels": labels,
        "text_inserts": [c.args[1] for w in texts for c in w.insert.call_args_list],
        "clipboard": [c.args[0] for c in stub.root.clipboard_append.call_args_list],
    }


class _DebugText:
    """ScrolledText of the Error & Debug tab."""

    def __init__(self, *_a, **_kw):
        self.inserted: List[str] = []
        self.after_fns = []

    def winfo_exists(self):
        return True

    def insert(self, _index, text, *_tags):
        self.inserted.append(text)

    def after(self, _ms, fn):
        self.after_fns.append(fn)

    def __getattr__(self, _name):
        return lambda *_a, **_kw: None


def build_debug_tab(stub) -> _DebugText:
    """Real _build_error_debug_tab with fake widgets; _poll_last_error runs once."""
    made: List[_DebugText] = []

    def scrolled(*a, **kw):
        widget = _DebugText(*a, **kw)
        made.append(widget)
        return widget

    stub.results_notebook = mock.MagicMock()
    stub.results_notebook.select.return_value = "other-tab"
    stub._main_mousewheel = mock.Mock()
    with mock.patch.object(app.tk, "Frame", mock.MagicMock()), \
            mock.patch.object(app.tk, "Checkbutton", mock.MagicMock()), \
            mock.patch.object(app, "ui_round_check", mock.Mock()), \
            mock.patch.object(app, "ui_button",
                              mock.Mock(return_value=(mock.MagicMock(), mock.MagicMock()))), \
            mock.patch.object(app.scrolledtext, "ScrolledText", side_effect=scrolled):
        GUI._build_error_debug_tab(stub, mock.MagicMock(name="tab"))
    return made[0]


def stop_with_cancel_error(err, *, engine=True, password=PW):
    stub = GUI.__new__(GUI)
    stub._is_busy = lambda: True
    stub._stop_event = threading.Event()
    stub._active_db_lock = threading.Lock()
    conn = mock.Mock(name="dbapi_connection")
    conn.cancel.side_effect = RuntimeError(err)
    stub._active_db_connections = {1: conn}
    stub.results_text = tre._Text()
    stub.db_password = _CountingEntry(FIELD_PW)
    if engine:
        stub.engine = E
        stub._connected_password = None if password is None else (E, password)
    GUI.stop_running_queries(stub)
    return stub


# ---------------------------------------------------------------- AC-1 / AC-2
class RunWorkerTests(R14Case):
    def _run(self, err, debug=False, **kw):
        stub = make_r14_stub(debug=debug)
        stub.read_sql_dataframe = raiser(err)
        return stub, run_query(stub, **kw)

    def test_ac1_last_error_details_masked(self):
        for label, err, keep in SECRET_ERRORS:
            for debug in (False, True):
                with self.subTest(error=label, debug=debug):
                    _stub, out = self._run(err, debug=debug)
                    d = out["details"]
                    self.assertIsNotNone(d)
                    self.assert_no_leak("message", [d["message"]])
                    self.assert_no_leak("traceback", [d["traceback"]])
                    self.assert_kept("message", d["message"], keep)
                    self.assertEqual(d["type"], "RuntimeError")
                    self.assertEqual(d["query"], SQL)
                    self.assertTrue(d["traceback"].startswith("Traceback (most recent call last)"))
                    self.assertTrue(d["traceback"].rstrip("\n").endswith(
                        "RuntimeError: " + d["message"]), "traceback lost its last line")

    def test_ac2_debug_prints_masked(self):
        for label, err, _keep in SECRET_ERRORS:
            with self.subTest(error=label):
                self.prints.clear()
                self._run(err, debug=True)
                self.assert_no_leak("print", self.prints)
                joined = "\n".join(self.prints)
                self.assertIn("Error Message: ", joined)
                self.assertIn("Full Traceback:\n", joined)
                self.assertIn(f"Query: {SQL}", joined)  # the user's SQL is not touched

    def test_ac17_details_keys_hold_no_password(self):
        _stub, out = self._run(ERR1)
        self.assertEqual(set(out["details"]), {"type", "message", "traceback", "query"})


# ---------------------------------------------------------------- AC-3
class RunErrorDisplayTests(R14Case):
    def test_ac3_execution_logs_masked(self):
        for label, err, keep in SECRET_ERRORS:
            for debug in (False, True):
                with self.subTest(error=label, debug=debug):
                    stub = make_r14_stub(debug=debug)
                    stub.read_sql_dataframe = raiser(err)
                    out = run_query(stub)
                    self.assert_no_leak("results_text", out["inserted"])
                    self.assert_no_leak("run log", out["run_log"])
                    lines = [t for t in out["inserted"] if t.startswith("Error Message: ")]
                    self.assertEqual(len(lines), 1)
                    self.assert_kept("Error Message", lines[0], keep)
                    self.assertEqual("Debug Traceback:\n" in out["inserted"], debug)
                    self.assertFalse(any("Error in error handler" in p for p in self.prints))

    def test_ac3_handler_called_directly(self):
        """on_query_error_enhanced given masked details keeps them masked."""
        for label, err, _keep in SECRET_ERRORS:
            with self.subTest(error=label):
                stub = make_r14_stub(debug=True)
                stub.read_sql_dataframe = raiser(err)
                details = run_query(stub, enhanced_real=False)["details"]
                stub2 = make_r14_stub(debug=True)
                with mock.patch.object(app.tk, "Button"):
                    GUI.on_query_error_enhanced(stub2, details, make_dialog(True))
                self.assert_no_leak("results_text", stub2.results_text.inserted)
                self.assertIn("Debug Traceback:\n", stub2.results_text.inserted)


# ---------------------------------------------------------------- AC-4 / AC-5
class RunDetailsDialogAndDebugTabTests(R14Case):
    def _details(self, err):
        stub = make_r14_stub()
        stub.read_sql_dataframe = raiser(err)
        run_query(stub, enhanced_real=False)
        return stub, stub.last_error_details

    def test_ac4_dialog_and_clipboard_masked(self):
        for label, err, keep in SECRET_ERRORS:
            with self.subTest(error=label):
                stub, details = self._details(err)
                out = open_details_dialog(stub, details)
                self.assert_no_leak("Label text", out["labels"])
                self.assert_no_leak("Text insert", out["text_inserts"])
                self.assert_no_leak("clipboard", out["clipboard"])
                message = [t for t in out["labels"] if t.startswith("Message: ")]
                self.assertEqual(len(message), 1)
                self.assert_kept("Label", message[0], keep)
                self.assertEqual(len(out["clipboard"]), 1)
                self.assertIn(f"Query:\n{SQL}\n\n", out["clipboard"][0])
                self.assertIn("Traceback:\n", out["clipboard"][0])
                self.assertIn(SQL, out["text_inserts"])  # Failed Query box unchanged

    def test_ac5_error_debug_tab_masked(self):
        for label, err, keep in SECRET_ERRORS:
            with self.subTest(error=label):
                stub, _details = self._details(err)
                debug_text = build_debug_tab(stub)
                self.assertTrue(debug_text.inserted, "_poll_last_error rendered nothing")
                self.assert_no_leak("debug_text", debug_text.inserted)
                self.assertIn("TRACEBACK\n", debug_text.inserted)
                summary = [t for t in debug_text.inserted if t.startswith("RuntimeError: ")]
                self.assertEqual(len(summary), 1)
                self.assert_kept("type: message", summary[0], keep)
                self.assertIn(f"{SQL}\n\n", debug_text.inserted)  # QUERY unchanged

    def test_ac5_later_poll_shows_new_error_masked(self):
        stub, _details = self._details(ERR1)
        debug_text = build_debug_tab(stub)
        _other, stub.last_error_details = self._details(ERR3)  # a later failed run
        debug_text.inserted.clear()
        debug_text.after_fns[-1]()
        self.assertTrue(debug_text.inserted)
        self.assert_no_leak("debug_text (next poll)", debug_text.inserted)


# ---------------------------------------------------------------- AC-6
class RunOnQueryErrorTests(R14Case):
    def test_ac6_dialog_closed_before_error(self):
        for label, err, keep in SECRET_ERRORS:
            with self.subTest(error=label):
                stub = make_r14_stub()
                stub.read_sql_dataframe = raiser(err)
                out = run_query(stub, dialog_open=False)
                self.assert_no_leak("results_text", out["inserted"])
                self.assertEqual(len(out["showerror"]), 1)
                self.assert_no_leak("showerror", out["showerror"][0])
                self.assert_kept("showerror", out["showerror"][0][1], keep)
                self.assertEqual(out["showerror"][0][0], "Query Error")

    def test_ac6_raw_exception_passed_directly(self):
        for label, err, keep in SECRET_ERRORS:
            with self.subTest(error=label):
                stub = make_r14_stub()
                stub.engine = E
                with mock.patch.object(app, "messagebox") as mb:
                    GUI.on_query_error(stub, RuntimeError(err), mock.MagicMock())
                self.assert_no_leak("results_text", stub.results_text.inserted)
                self.assert_no_leak("showerror", mb.showerror.call_args.args)
                lines = [t for t in stub.results_text.inserted if t.startswith("Error: ")]
                self.assertEqual(len(lines), 1)
                self.assert_kept("Error line", lines[0], keep)
                self.assertTrue(mb.showerror.call_args.args[1].startswith(
                    "Failed to execute query:\n\n"))
                self.assertEqual(stub.execute_btn.state, "normal")


# ---------------------------------------------------------------- AC-13 / AC-14 (Run)
class RunPasswordSourceTests(R14Case):
    def _all_outputs(self, out):
        d = out["details"]
        return [d["message"], d["traceback"], *out["inserted"], *out["run_log"],
                *[a for c in out["showerror"] for a in c], *self.prints]

    def test_ac13_reconnect_while_running_uses_start_password(self):
        for caller in ("execute_query", "bg_no_args", "bg_engine"):
            for dialog_open in (True, False):
                with self.subTest(caller=caller, dialog_open=dialog_open):
                    self.prints.clear()
                    stub = make_r14_stub(debug=True)
                    stub.read_sql_dataframe = raiser(ERR3)
                    out = run_query(stub, swap=True, dialog_open=dialog_open, caller=caller)
                    self.assertIs(stub.engine, E2)
                    self.assert_no_leak("all destinations", self._all_outputs(out))
                    self.assert_kept("message", out["details"]["message"], ("bad password",))
                    self.assertEqual(out["gets_after_start"], 0, "Password field read in worker")
                    self.assertEqual(out["gets"], 0, "Password field read")

    def test_ac13_details_dialog_and_tab_after_reconnect(self):
        stub = make_r14_stub()
        stub.read_sql_dataframe = raiser(ERR3)
        run_query(stub, swap=True, enhanced_real=False)
        dialog = open_details_dialog(stub, stub.last_error_details)
        tab = build_debug_tab(stub)
        self.assert_no_leak("dialog", dialog["labels"] + dialog["text_inserts"]
                            + dialog["clipboard"])
        self.assert_no_leak("debug tab", tab.inserted)

    def test_ac14_engine_not_from_connect_pattern_only(self):
        for owner_case in ("none", "other_engine"):
            for label, err, keep in SECRET_ERRORS:
                with self.subTest(stored=owner_case, error=label):
                    if owner_case == "none":
                        stub = make_r14_stub(password=None, debug=True)
                    else:
                        stub = make_r14_stub(password=PW, owner=E2, debug=True)
                    stub.read_sql_dataframe = raiser(err)
                    out = run_query(stub)
                    d = out["details"]
                    if err is ERR3:
                        # known limit (R14-Q-3): no known password -> left as is
                        self.assert_same("message", d["message"], err)
                    else:
                        self.assert_no_leak("message/traceback", [d["message"], d["traceback"]])
                        self.assert_no_leak("results_text", out["inserted"])
                        self.assert_kept("message", d["message"], keep)
                    self.assertEqual(out["gets"], 0, "Password field read (no fallback)")


# ---------------------------------------------------------------- AC-15 (P12)
class StopCancelErrorTests(R14Case):
    def _cancel_lines(self):
        return [p for p in self.prints if p.startswith("Stop: cancel failed: ")]

    def test_ac15_cancel_error_masked(self):
        for label, err, keep in SECRET_ERRORS:
            with self.subTest(error=label):
                self.prints.clear()
                stub = stop_with_cancel_error(err)
                lines = self._cancel_lines()
                self.assertEqual(len(lines), 1)
                self.assert_no_leak("print", self.prints)
                self.assert_kept("print", lines[0], keep)
                self.assertTrue(stub._stop_event.is_set())
                self.assertEqual(stub.db_password.get_calls, 0)

    def test_ac15_no_engine_yet_pattern_only(self):
        """Stop before any Connect: no engine attribute -> patterns only."""
        for label, err, _keep in SECRET_ERRORS:
            with self.subTest(error=label):
                self.prints.clear()
                stop_with_cancel_error(err, engine=False)
                lines = self._cancel_lines()
                self.assertEqual(len(lines), 1)
                if err is ERR3:
                    self.assert_same("print", lines[0], "Stop: cancel failed: " + err)
                else:
                    self.assert_no_leak("print", self.prints)

    def test_ac15_engine_without_stored_password(self):
        self.prints.clear()
        stop_with_cancel_error(ERR1, password=None)
        self.assert_no_leak("print", self.prints)
        self.assertEqual(len(self._cancel_lines()), 1)


# ---------------------------------------------------------------- AC-16 (P1-P6, P12)
class RunPlainErrorUnchangedTests(R14Case):
    """Errors without a password: every destination equals the pre-R14 output.

    Oracle: the same path run again with redact_secrets patched to identity.
    """

    def _collect_run(self, err, debug, dialog_open):
        self.prints.clear()
        stub = make_r14_stub(debug=debug)
        stub.read_sql_dataframe = raiser(err)
        out = run_query(stub, dialog_open=dialog_open)
        result = {k: out[k] for k in ("details", "inserted", "run_log", "showerror")}
        result["prints"] = list(self.prints)
        if dialog_open:
            result["dialog"] = open_details_dialog(stub, stub.last_error_details)
            result["tab"] = build_debug_tab(stub).inserted
        return result

    def test_ac16_run_paths_equal_oracle(self):
        for label, err in PLAIN_ERRORS:
            for debug in (False, True):
                for dialog_open in (True, False):
                    with self.subTest(error=label, debug=debug, dialog_open=dialog_open):
                        actual = self._collect_run(err, debug, dialog_open)
                        with mock.patch.object(app, "redact_secrets", identity_redact):
                            expected = self._collect_run(err, debug, dialog_open)
                        self.assertEqual(actual, expected)
                        d = actual["details"]
                        self.assertEqual(d["message"], err)
                        self.assertTrue(d["traceback"].rstrip("\n").endswith("RuntimeError: " + err))
                        if dialog_open:
                            self.assertIn(f"Error Message: {err}\n\n", actual["inserted"])
                            self.assertIn(f"Message: {err}", actual["dialog"]["labels"])
                            self.assertIn(f"RuntimeError: {err}\n\n", actual["tab"])
                        else:
                            self.assertIn(f"Error: {err}\n\n", actual["inserted"])
                            self.assertEqual(actual["showerror"],
                                             [["Query Error", f"Failed to execute query:\n\n{err}"]])
                        if debug:
                            self.assertIn(f"Error Message: {err}", actual["prints"])

    def test_ac16_on_query_error_direct_unchanged(self):
        for label, err in PLAIN_ERRORS:
            with self.subTest(error=label):
                stub = make_r14_stub()
                with mock.patch.object(app, "messagebox") as mb:
                    GUI.on_query_error(stub, RuntimeError(err), mock.MagicMock())
                self.assertEqual(stub.results_text.inserted,
                                 ["❌ QUERY ERROR\n", "=" * 150 + "\n\n", f"Error: {err}\n\n"])
                mb.showerror.assert_called_once_with(
                    "Query Error", f"Failed to execute query:\n\n{err}")

    def test_ac16_stop_print_unchanged(self):
        for label, err in PLAIN_ERRORS:
            with self.subTest(error=label):
                self.prints.clear()
                stop_with_cancel_error(err)
                self.assertEqual(self.prints, [f"Stop: cancel failed: {err}"])


# ---------------------------------------------------------------- AC-17 (static)
class StaticRulesTests(unittest.TestCase):
    def test_redact_lines_at_most_95(self):
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "database_connect_gui.py")
        with open(path, encoding="utf-8") as handle:
            lines = [ln.rstrip("\r\n") for ln in handle if "redact_secrets(" in ln]
        self.assertGreaterEqual(len(lines), 12)  # R13 + R14 call sites
        for line in lines:
            self.assertLessEqual(len(line), 95, line)

    def test_no_password_field_in_run_records(self):
        for cls in (app.RunTarget, app.ConnectionInfo):
            names = [f.name.lower() for f in dataclasses.fields(cls)]
            self.assertFalse([n for n in names if "pass" in n or "pwd" in n], cls.__name__)


if __name__ == "__main__":
    unittest.main()
