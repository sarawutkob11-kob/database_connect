"""T2: Ctrl+Enter respects the Run button state (AC-27, AC-28).

No Tk window, no database. AC-29 is Manual/GUI.
"""

import os
import re
import sys
import threading
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import database_connect_gui as app  # noqa: E402


class _TclObjLike:
    """Not a str, but str() gives the state name (like a Tcl_Obj)."""

    def __init__(self, value: str) -> None:
        self._value = value

    def __str__(self) -> str:
        return self._value

    def __eq__(self, other) -> bool:  # Tcl_Obj never equals a plain str
        return other is self


class _FakeButton:
    def __init__(self, text: str = "", state=None) -> None:
        self.text = text
        self.state = state

    def cget(self, key: str):
        if key == "text":
            return self.text
        if key == "state":
            return self.state
        raise KeyError(key)

    def __getitem__(self, key: str):
        return self.cget(key)


class _FakeText:
    def __init__(self) -> None:
        self.inserted: list = []
        self.seen: list = []

    def insert(self, index, value) -> None:
        self.inserted.append((index, value))

    def see(self, index) -> None:
        self.seen.append(index)


def make_stub(state, *, running_job_ids=None, execute_text="▶  Run"):
    stub = app.DatabaseConnectorGUI.__new__(app.DatabaseConnectorGUI)
    stub._active_db_lock = threading.Lock()
    stub._active_db_connections = {}
    stub._batch_running = False
    stub._running_job_ids = set(running_job_ids or ())
    stub.execute_btn = _FakeButton(execute_text, state)
    stub.export_excel_btn = _FakeButton("Export Excel")
    stub.inspect_btn = _FakeButton("Tables")
    stub.results_text = _FakeText()
    stub.execute_query = mock.Mock(name="execute_query")
    return stub


class CtrlEnterDisabledTests(unittest.TestCase):
    """AC-27"""

    def test_tcl_obj_disabled_and_busy_logs_and_does_not_run(self):
        state = _TclObjLike("disabled")
        self.assertNotIsInstance(state, str)
        self.assertFalse(state == "disabled")  # old `== "disabled"` check fails
        stub = make_stub(state, running_job_ids={"job-1"})
        with mock.patch.object(app, "messagebox") as mb, \
                mock.patch.object(app, "ui_dialog") as dlg:
            result = stub._on_sql_ctrl_enter(object())
        self.assertIsNone(result)
        stub.execute_query.assert_not_called()
        self.assertEqual(len(stub.results_text.inserted), 1)
        index, message = stub.results_text.inserted[0]
        self.assertEqual(index, app.tk.END)
        self.assertTrue(message.startswith("⏳ Run: "))
        self.assertTrue(message.endswith("\n"))
        self.assertEqual(stub.results_text.seen, [app.tk.END])
        self.assertEqual(mb.mock_calls, [])
        dlg.assert_not_called()

    def test_tcl_obj_disabled_busy_by_loading_button(self):
        stub = make_stub(_TclObjLike("disabled"), execute_text="⏳ Loading...")
        stub._on_sql_ctrl_enter()
        stub.execute_query.assert_not_called()
        self.assertEqual(len(stub.results_text.inserted), 1)

    def test_tcl_obj_disabled_not_busy_does_nothing(self):
        stub = make_stub(_TclObjLike("disabled"))
        with mock.patch.object(app, "messagebox") as mb:
            result = stub._on_sql_ctrl_enter(object())
        self.assertIsNone(result)
        stub.execute_query.assert_not_called()
        self.assertEqual(stub.results_text.inserted, [])
        self.assertEqual(stub.results_text.seen, [])
        self.assertEqual(mb.mock_calls, [])

    def test_str_disabled_busy_blocks(self):
        stub = make_stub("disabled", running_job_ids={"j"})
        stub._on_sql_ctrl_enter()
        stub.execute_query.assert_not_called()
        self.assertEqual(len(stub.results_text.inserted), 1)

    def test_str_disabled_not_busy_does_nothing(self):
        stub = make_stub("disabled")
        stub._on_sql_ctrl_enter()
        stub.execute_query.assert_not_called()
        self.assertEqual(stub.results_text.inserted, [])


class CtrlEnterNormalTests(unittest.TestCase):
    """AC-28"""

    def test_normal_runs_once(self):
        for state in ("normal", _TclObjLike("normal")):
            for event in (None, object()):
                with self.subTest(state=type(state).__name__, event=event):
                    stub = make_stub(state)
                    if event is None:
                        result = stub._on_sql_ctrl_enter()
                    else:
                        result = stub._on_sql_ctrl_enter(event)
                    self.assertIsNone(result)
                    stub.execute_query.assert_called_once_with()
                    self.assertEqual(stub.results_text.inserted, [])

    def test_active_state_also_runs(self):
        # Anything other than "disabled" behaves like the Run button being enabled.
        stub = make_stub("active")
        stub._on_sql_ctrl_enter()
        stub.execute_query.assert_called_once_with()

    def test_return_value_of_execute_query_is_not_propagated(self):
        stub = make_stub("normal")
        stub.execute_query.return_value = "break"
        self.assertIsNone(stub._on_sql_ctrl_enter())


class CtrlEnterBindingTests(unittest.TestCase):
    def setUp(self) -> None:
        path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "database_connect_gui.py",
        )
        with open(path, encoding="utf-8") as fh:
            self.source = fh.read()

    def test_binding_points_at_new_method(self):
        self.assertRegex(
            self.source,
            r'self\.sql_context\.bind\(\s*"<Control-Return>"\s*,\s*'
            r"self\._on_sql_ctrl_enter\s*\)",
        )

    def test_no_other_control_return_binding(self):
        binds = re.findall(r'bind\(\s*["\']<Control-Return>["\']\s*,([^\n]*)', self.source)
        self.assertEqual(len(binds), 1, binds)
        self.assertNotIn("lambda", binds[0])

    def test_method_exists_with_optional_event(self):
        import inspect

        sig = inspect.signature(app.DatabaseConnectorGUI._on_sql_ctrl_enter)
        params = list(sig.parameters.values())
        self.assertEqual(len(params), 2)
        self.assertIsNot(params[1].default, inspect.Parameter.empty)


if __name__ == "__main__":
    unittest.main()
