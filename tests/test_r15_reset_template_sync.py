"""QA for R15-T1 (BH-1, R15-AC-1..4): main-window Reset template syncs the
parameter state with the SQL editor before choosing tracked / detected mode.

No Tk window (tk / ttk / scrolledtext / ui helpers mocked), no real database
(SQLite :memory:), no files touched.
"""

import ast
import contextlib
import inspect
import os
import sqlite3
import sys
import textwrap
import unittest
from typing import Dict, List, Optional
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import database_connect_gui as app  # noqa: E402
from test_r2_reset_parameter_qa import _Text, compile_nested  # noqa: E402

GUI = app.DatabaseConnectorGUI

T = "DELETE FROM t WHERE id IN ({IDS})"
R = "DELETE FROM t WHERE id IN (1, 2, 3)"
EDITED = R + " AND branch='BKK'"
CONFIRM = "↩  Confirm · Reset ค่าที่เลือก"
RESET_ALL = "Reset All Parameters"
NO_LIST_WARNING = "No parameter loaded and no IN (...) list found in the SQL"


class _Var:
    def __init__(self, master=None, value=None, **_kw):
        self.value = "" if value is None else value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value

    def trace_add(self, *_a, **_k):
        return "trace"


class _BoolVar(_Var):
    def __init__(self, master=None, value=False, **_kw):
        super().__init__(master, value=bool(value))


class DialogHarness:
    """Records buttons / checkbuttons of the mocked Reset dialog."""

    def __init__(self) -> None:
        self.buttons: Dict[str, object] = {}
        self.tk = mock.MagicMock(name="tk")
        self.tk.END = "end"
        self.tk.SINGLE = "single"
        self.tk.WORD = "word"
        self.tk.StringVar = _Var
        self.tk.BooleanVar = _BoolVar
        self.state_at_toplevel: Optional[dict] = None
        self.stub = None

        def toplevel(*_a, **_k):
            stub = self.stub
            self.state_at_toplevel = {
                "template": getattr(stub, "sql_template", None),
                "values": dict(stub._excel_parameter_values),
                "rendered": getattr(stub, "_excel_parameterized_sql", None),
            }
            return mock.MagicMock(name="dialog")

        self.tk.Toplevel.side_effect = toplevel

    def ui_button(self, _parent, text, command, **_kw):
        self.buttons[text] = command
        return mock.MagicMock(), mock.MagicMock()

    @staticmethod
    def ui_round_frame(*_a, **_k):
        return mock.MagicMock(), mock.MagicMock()

    @contextlib.contextmanager
    def patched(self):
        with mock.patch.object(app, "tk", self.tk), \
                mock.patch.object(app, "ttk", mock.MagicMock(name="ttk")), \
                mock.patch.object(app, "scrolledtext", mock.MagicMock(name="scrolledtext")), \
                mock.patch.object(app, "ui_button", self.ui_button), \
                mock.patch.object(app, "ui_round_frame", self.ui_round_frame), \
                mock.patch.object(app, "messagebox") as mb:
            self.mb = mb
            yield self

    @property
    def dialog_opened(self) -> bool:
        return self.tk.Toplevel.called

    def tick(self, display: str) -> None:
        """Tick the most recently rendered checkbox whose text is `display`."""
        calls = [c for c in self.tk.Checkbutton.call_args_list
                 if c.kwargs.get("text") == display]
        assert calls, f"no checkbox {display!r}: " + repr(
            [c.kwargs.get("text") for c in self.tk.Checkbutton.call_args_list])
        kwargs = calls[-1].kwargs
        kwargs["variable"].set(True)
        kwargs["command"]()

    def checkbox_texts(self) -> List[str]:
        return [c.kwargs.get("text") for c in self.tk.Checkbutton.call_args_list]


def make_main(editor: str, template=None, values=None, rendered=None):
    stub = GUI.__new__(GUI)
    stub.sql_context = _Text(editor)
    stub.sql_template = template
    stub._excel_parameter_values = dict(values or {})
    stub._excel_parameterized_sql = rendered
    stub.root = mock.MagicMock(name="root")
    stub.debug_mode = _Var(value=False)
    return stub


def loaded_main(editor: str):
    """State after Load Excel of T with 1, 2, 3 (R15 definition), editor = `editor`."""
    stub = make_main(editor, T, {"IDS": ("{IDS}", "1, 2, 3")}, R)
    return stub


def branch_db(test: unittest.TestCase) -> sqlite3.Connection:
    con = sqlite3.connect(":memory:")
    test.addCleanup(con.close)
    con.execute("CREATE TABLE t (id INTEGER, branch TEXT)")
    con.executemany("INSERT INTO t VALUES (?, ?)", [
        (1, "BKK"), (1, "CNX"), (2, "BKK"), (2, "CNX"), (3, "BKK"), (3, "CNX"), (4, "BKK"),
    ])
    con.commit()
    return con


def deleted_rows(test: unittest.TestCase, sql: str) -> set:
    con = branch_db(test)
    before = set(con.execute("SELECT id, branch FROM t").fetchall())
    con.execute(sql)
    after = set(con.execute("SELECT id, branch FROM t").fetchall())
    return before - after


class SanityTests(unittest.TestCase):
    def test_definition_renders_r(self):
        stub = loaded_main(R)
        self.assertEqual(stub._render_sql_template(), R)

    def test_sync_is_first_statement_of_show_reset_parameter_dialog(self):
        tree = ast.parse(textwrap.dedent(inspect.getsource(GUI.show_reset_parameter_dialog)))
        func = tree.body[0]
        first = func.body[0]
        self.assertIsInstance(first, ast.Expr)
        self.assertEqual(ast.unparse(first.value), "self._sync_parameter_state_with_editor()")


# ======================================================================
# R15-AC-1: edited after Load Excel -> detected mode, user condition kept
# ======================================================================
class AC1EditedAfterLoadTests(unittest.TestCase):
    def run_reset(self, editor: str):
        stub = loaded_main(editor)
        h = DialogHarness()
        h.stub = stub
        with h.patched():
            stub.show_reset_parameter_dialog()
            state = dict(h.state_at_toplevel or {})
            buttons = dict(h.buttons)
            h.tick("2")
            h.buttons[CONFIRM]()
            mb = h.mb
        return stub, h, state, buttons, mb

    def test_detected_mode_and_condition_kept(self):
        stub, h, state, buttons, mb = self.run_reset(EDITED)
        self.assertTrue(h.dialog_opened)
        mb.showwarning.assert_not_called()
        mb.showerror.assert_not_called()
        # state synced before the dialog opened
        self.assertEqual(state, {"template": EDITED, "values": {}, "rendered": None})
        # detected mode: no Reset All, values come from the current IN-list
        self.assertNotIn(RESET_ALL, buttons)
        self.assertIn(CONFIRM, buttons)
        for value in ("1", "2", "3"):
            self.assertIn(value, h.checkbox_texts())
        self.assertEqual(stub.sql_context.content,
                         "DELETE FROM t WHERE id IN (1, 3) AND branch='BKK'")
        self.assertEqual(stub.sql_template, EDITED)
        self.assertEqual(stub._excel_parameter_values, {})
        self.assertIsNone(stub._excel_parameterized_sql)

    def test_trailing_newline_in_editor_is_ignored_in_template(self):
        stub, _h, state, buttons, _mb = self.run_reset(EDITED + "\n")
        self.assertEqual(state["template"], EDITED)
        self.assertNotIn(RESET_ALL, buttons)
        self.assertEqual(stub.sql_context.content,
                         "DELETE FROM t WHERE id IN (1, 3) AND branch='BKK'")

    def test_sqlite_delete_never_wider_than_edited_sql(self):
        stub, *_ = self.run_reset(EDITED)
        after_reset = deleted_rows(self, stub.sql_context.content)
        edited = deleted_rows(self, EDITED)
        self.assertEqual(after_reset, {(1, "BKK"), (3, "BKK")})
        self.assertTrue(after_reset <= edited)
        # no row of another branch is touched (old bug: IN (1, 3) without branch)
        self.assertFalse(any(branch != "BKK" for _id, branch in after_reset))
        widened = deleted_rows(self, "DELETE FROM t WHERE id IN (1, 3)")
        self.assertLess(len(after_reset), len(widened))

    def test_edit_in_middle_of_sql_also_synced(self):
        edited = "DELETE FROM t WHERE branch='BKK' AND id IN (1, 2, 3)"
        stub, _h, state, buttons, _mb = self.run_reset(edited)
        self.assertEqual(state["template"], edited)
        self.assertNotIn(RESET_ALL, buttons)
        self.assertEqual(stub.sql_context.content,
                         "DELETE FROM t WHERE branch='BKK' AND id IN (1, 3)")

    def test_cancel_after_sync_leaves_editor_unchanged(self):
        stub = loaded_main(EDITED)
        h = DialogHarness()
        h.stub = stub
        with h.patched():
            stub.show_reset_parameter_dialog()
        self.assertEqual(stub.sql_context.content, EDITED)


# ======================================================================
# R15-AC-2: editor replaced with SQL without IN-list -> warning, no overwrite
# ======================================================================
class AC2NoInListTests(unittest.TestCase):
    def test_warning_and_editor_untouched(self):
        sql = "SELECT * FROM hr.employees"
        stub = loaded_main(sql)
        h = DialogHarness()
        h.stub = stub
        with h.patched():
            stub.show_reset_parameter_dialog()
        h.mb.showwarning.assert_called_once_with(
            "Reset Parameter", NO_LIST_WARNING, parent=stub.root)
        self.assertFalse(h.dialog_opened)
        self.assertEqual(h.buttons, {})
        self.assertEqual(stub.sql_context.content, sql)
        self.assertNotIn("DELETE", stub.sql_context.content)
        # state synced (tracked values dropped), editor not written
        self.assertEqual(stub.sql_template, sql)
        self.assertEqual(stub._excel_parameter_values, {})
        self.assertIsNone(stub._excel_parameterized_sql)

    def test_empty_editor_warns_and_stays_empty(self):
        stub = loaded_main("")
        h = DialogHarness()
        h.stub = stub
        with h.patched():
            stub.show_reset_parameter_dialog()
        h.mb.showwarning.assert_called_once_with(
            "Reset Parameter", NO_LIST_WARNING, parent=stub.root)
        self.assertFalse(h.dialog_opened)
        self.assertEqual(stub.sql_context.content, "")

    def test_second_press_still_warns_without_writing(self):
        sql = "SELECT * FROM hr.employees"
        stub = loaded_main(sql)
        for _ in range(2):
            h = DialogHarness()
            h.stub = stub
            with h.patched():
                stub.show_reset_parameter_dialog()
            h.mb.showwarning.assert_called_once()
            self.assertEqual(stub.sql_context.content, sql)


# ======================================================================
# R15-AC-3: editor == R (maybe trailing \n) -> tracked mode as before
# ======================================================================
class AC3UnchangedEditorTests(unittest.TestCase):
    EDITORS = (R, R + "\n")

    def open(self, editor: str):
        stub = loaded_main(editor)
        h = DialogHarness()
        h.stub = stub
        return stub, h

    def test_tracked_mode_reset_selected(self):
        for editor in self.EDITORS:
            with self.subTest(editor=editor):
                stub, h = self.open(editor)
                with h.patched():
                    stub.show_reset_parameter_dialog()
                    self.assertEqual(h.state_at_toplevel, {
                        "template": T, "values": {"IDS": ("{IDS}", "1, 2, 3")}, "rendered": R})
                    self.assertIn(RESET_ALL, h.buttons)
                    h.tick("2")
                    h.buttons[CONFIRM]()
                    h.mb.showerror.assert_not_called()
                self.assertEqual(stub.sql_context.content, "DELETE FROM t WHERE id IN (1, 3)")
                self.assertEqual(stub.sql_template, T)
                self.assertEqual(stub._excel_parameter_values, {"IDS": ("{IDS}", "1, 3")})
                self.assertEqual(stub._excel_parameterized_sql,
                                 "DELETE FROM t WHERE id IN (1, 3)")

    def test_tracked_mode_reset_all(self):
        for editor in self.EDITORS:
            with self.subTest(editor=editor):
                stub, h = self.open(editor)
                with h.patched():
                    stub.show_reset_parameter_dialog()
                    self.assertIn(RESET_ALL, h.buttons)
                    h.buttons[RESET_ALL]()
                self.assertEqual(stub.sql_context.content, T)
                self.assertEqual(stub._excel_parameter_values, {})
                self.assertIsNone(stub._excel_parameterized_sql)

    def test_editor_equal_to_template_keeps_tracked_state(self):
        """Values loaded but editor shows the template itself: rule leaves state alone."""
        stub = make_main(T, T, {"IDS": ("{IDS}", "1, 2, 3")}, R)
        stub._sync_parameter_state_with_editor()
        self.assertEqual(stub.sql_template, T)
        self.assertEqual(stub._excel_parameter_values, {"IDS": ("{IDS}", "1, 2, 3")})
        self.assertEqual(stub._excel_parameterized_sql, R)

    def test_only_trailing_newlines_ignored_other_whitespace_counts(self):
        stub = loaded_main(R + "\n\n")
        stub._sync_parameter_state_with_editor()
        self.assertEqual(stub._excel_parameterized_sql, R)
        stub = loaded_main(R + " ")
        stub._sync_parameter_state_with_editor()
        self.assertEqual(stub._excel_parameter_values, {})
        self.assertEqual(stub.sql_template, R + " ")


# ======================================================================
# R15-AC-4: never loaded Excel -> unchanged; Edit Job / Edit Script unchanged
# ======================================================================
def _noop_sync(self):
    return None


class AC4NoExcelTests(unittest.TestCase):
    def run_main(self, editor: str, baseline: bool):
        stub = make_main(editor)
        h = DialogHarness()
        h.stub = stub
        patcher = (mock.patch.object(GUI, "_sync_parameter_state_with_editor", _noop_sync)
                   if baseline else contextlib.nullcontext())
        with patcher, h.patched():
            stub.show_reset_parameter_dialog()
            buttons = sorted(h.buttons)
            h.tick("2")
            h.buttons[CONFIRM]()
        return (stub.sql_context.content, stub.sql_template, dict(stub._excel_parameter_values),
                stub._excel_parameterized_sql, buttons)

    def test_detected_mode_same_as_before(self):
        editor = "DELETE FROM t WHERE id IN (1, 2, 3)"
        new = self.run_main(editor, baseline=False)
        old = self.run_main(editor, baseline=True)
        self.assertEqual(new, old)
        self.assertEqual(new[0], "DELETE FROM t WHERE id IN (1, 3)")
        self.assertIsNone(new[1])
        self.assertEqual(new[2], {})
        self.assertIsNone(new[3])
        self.assertNotIn(RESET_ALL, new[4])

    def test_sync_does_nothing_without_values(self):
        cases = [
            (None, None),
            ("SELECT 1", None),          # stale template, values empty
            ("SELECT 1", "SELECT 2"),
        ]
        for template, rendered in cases:
            with self.subTest(template=template, rendered=rendered):
                stub = make_main("DELETE FROM t WHERE id IN (1)", template, {}, rendered)
                stub._sync_parameter_state_with_editor()
                self.assertEqual(stub.sql_template, template)
                self.assertEqual(stub._excel_parameter_values, {})
                self.assertEqual(stub._excel_parameterized_sql, rendered)

    def test_stub_without_template_attribute_does_not_crash(self):
        stub = GUI.__new__(GUI)
        stub.sql_context = _Text("DELETE FROM t WHERE id IN (1)")
        stub._excel_parameter_values = {}
        stub._sync_parameter_state_with_editor()  # no AttributeError
        self.assertFalse(hasattr(stub, "sql_template"))


class AC4EditDialogsTests(unittest.TestCase):
    """reset_parameter_for_edit (Edit Job) and run_excel_tool (Edit Script):
    query_text / edit state / main state must equal the pre-fix result."""

    MAIN = ("SELECT * FROM main WHERE x IN ('a')", "SELECT * FROM main WHERE x IN ({X})",
            {"X": ("{X}", "'a'")}, "SELECT * FROM main WHERE x IN ('a')")

    # (query in the edit box, edit state template, values, rendered)
    CASES = [
        ("unchanged", R, T, {"IDS": ("{IDS}", "1, 2, 3")}, R),
        ("unchanged_nl", R + "\n", T, {"IDS": ("{IDS}", "1, 2, 3")}, R),
        ("edited", EDITED, T, {"IDS": ("{IDS}", "1, 2, 3")}, R),
        ("no_excel", R, None, {}, None),
    ]

    def make_self(self):
        editor, template, values, rendered = self.MAIN
        return make_main(editor, template, values, rendered)

    def main_state(self, stub):
        return (stub.sql_context.content, stub.sql_template,
                dict(stub._excel_parameter_values), stub._excel_parameterized_sql)

    def run_edit_job(self, query, template, values, rendered, baseline):
        stub = self.make_self()
        main_context = stub.sql_context
        main_root = stub.root
        query_text = _Text(query)
        state = {"template": template, "values": dict(values), "rendered": rendered}
        dialog = mock.MagicMock(name="edit_dialog")
        funcs = compile_nested(GUI.edit_job, ("sync_edit_parameter_state",
                                              "reset_parameter_for_edit"),
                               {"query_text": query_text, "edit_excel_state": state,
                                "self": stub, "dialog": dialog})
        h = DialogHarness()
        h.stub = stub

        def show(*a, **k):
            result = original(stub, *a, **k)
            h.tick("2")
            h.buttons[CONFIRM]()
            return result

        original = GUI.show_reset_parameter_dialog
        patcher = (mock.patch.object(GUI, "_sync_parameter_state_with_editor", _noop_sync)
                   if baseline else contextlib.nullcontext())
        with patcher, h.patched(), \
                mock.patch.object(stub, "show_reset_parameter_dialog", side_effect=show):
            funcs["reset_parameter_for_edit"]()
        self.assertIs(stub.sql_context, main_context)
        self.assertIs(stub.root, main_root)
        return (query_text.content, state["template"], dict(state["values"]),
                state["rendered"], sorted(h.buttons), self.main_state(stub))

    def run_edit_script(self, query, template, values, rendered, baseline):
        stub = self.make_self()
        main_context = stub.sql_context
        query_text = _Text(query)
        state = {"template": template, "values": dict(values), "rendered": rendered}
        dialog = mock.MagicMock(name="script_dialog")
        funcs = compile_nested(GUI._edit_group_script_dialog,
                               ("sync_parameter_state", "run_excel_tool"),
                               {"query_text": query_text, "excel_state": state,
                                "self": stub, "dialog": dialog})
        h = DialogHarness()
        h.stub = stub

        def tool():
            stub.show_reset_parameter_dialog(close_after_selected=True, wait=True)
            h.tick("2")
            h.buttons[CONFIRM]()

        patcher = (mock.patch.object(GUI, "_sync_parameter_state_with_editor", _noop_sync)
                   if baseline else contextlib.nullcontext())
        with patcher, h.patched():
            funcs["run_excel_tool"](tool)
        self.assertIs(stub.sql_context, main_context)
        return (query_text.content, state["template"], dict(state["values"]),
                state["rendered"], sorted(h.buttons), self.main_state(stub))

    def test_edit_job_same_as_before_fix(self):
        for name, query, template, values, rendered in self.CASES:
            with self.subTest(case=name):
                new = self.run_edit_job(query, template, values, rendered, baseline=False)
                old = self.run_edit_job(query, template, values, rendered, baseline=True)
                self.assertEqual(new, old)
                self.assertEqual(new[5], self.MAIN)  # main state restored

    def test_edit_script_same_as_before_fix(self):
        for name, query, template, values, rendered in self.CASES:
            with self.subTest(case=name):
                new = self.run_edit_script(query, template, values, rendered, baseline=False)
                old = self.run_edit_script(query, template, values, rendered, baseline=True)
                self.assertEqual(new, old)
                self.assertEqual(new[5], self.MAIN)

    def test_edit_job_expected_results(self):
        # unchanged -> tracked mode, value 2 removed via template
        out = self.run_edit_job(R, T, {"IDS": ("{IDS}", "1, 2, 3")}, R, baseline=False)
        self.assertEqual(out[0], "DELETE FROM t WHERE id IN (1, 3)")
        self.assertEqual(out[1:4], (T, {"IDS": ("{IDS}", "1, 3")},
                                    "DELETE FROM t WHERE id IN (1, 3)"))
        self.assertIn(RESET_ALL, out[4])
        # edited -> detected mode, condition kept
        out = self.run_edit_job(EDITED, T, {"IDS": ("{IDS}", "1, 2, 3")}, R, baseline=False)
        self.assertEqual(out[0], "DELETE FROM t WHERE id IN (1, 3) AND branch='BKK'")
        self.assertEqual(out[1:4], (EDITED, {}, None))
        self.assertNotIn(RESET_ALL, out[4])


if __name__ == "__main__":
    unittest.main()
