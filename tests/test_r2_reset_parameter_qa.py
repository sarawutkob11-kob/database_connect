"""QA for R2-T-fix (M9): Reset Parameter fixes A (detected mode) and B (tracked mode).

Fix A: _has_negated_in_before / _reset_sql_in_lists — adversarial NOT / comment /
string / nesting cases, each checked on SQLite: the reset SQL must never touch
more rows than the original SQL (R2-US-2).
Fix B: Auto WHERE column emptied in UPDATE / DELETE stays (AUTO_WHERE, "") and
renders as 1=0 — two columns, re-import, Reset all, save-as-job + reload, and
unchanged rendering when values are present.

No Tk window, no real database (SQLite :memory:), files only in TemporaryDirectory.
"""

import ast
import inspect
import json
import os
import re
import sqlite3
import sys
import tempfile
import textwrap
import unittest
from typing import Optional
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import database_connect_gui as app  # noqa: E402

GUI = app.DatabaseConnectorGUI
AUTO = GUI.AUTO_WHERE_PARAMETER
ROWS = [("1001", "A", "N"), ("1002", "B", "N"), ("1003", "A", "Z")]


def norm(sql: str) -> str:
    return re.sub(r"\s+", " ", sql).strip()


def acct_db(test: unittest.TestCase) -> sqlite3.Connection:
    con = sqlite3.connect(":memory:")
    test.addCleanup(con.close)
    con.execute("CREATE TABLE acct (acc_no TEXT, status TEXT, flag TEXT)")
    con.executemany("INSERT INTO acct VALUES (?, ?, ?)", ROWS)
    con.commit()
    return con


def affected(test: unittest.TestCase, sql: str) -> int:
    """Rows touched by sql on a fresh acct table (SELECT: rows returned)."""
    con = acct_db(test)
    sql = sql.rstrip().rstrip(";")
    if norm(sql).upper().startswith("SELECT"):
        return len(con.execute(sql).fetchall())
    return con.execute(sql).rowcount


def index_of(lists: list, column: str) -> int:
    return [i["column"].lower() for i in lists].index(column.lower())


def reset_column(sql: str, column: str = "acc_no") -> str:
    """Remove every value of the IN list of `column` (detected mode)."""
    lists = GUI._detect_sql_in_lists(sql)
    index = index_of(lists, column)
    return GUI._reset_sql_in_lists(sql, lists, {index: set(lists[index]["tokens"])})


def compile_nested(outer, wanted: tuple, env: dict) -> dict:
    """Compile nested functions `wanted` of method `outer` with `env` as closure."""
    tree = ast.parse(textwrap.dedent(inspect.getsource(outer)))
    funcs = {n.name: n for n in ast.walk(tree)
             if isinstance(n, ast.FunctionDef) and n.name in wanted}
    assert set(funcs) == set(wanted), sorted(funcs)
    names = sorted(env)
    factory = ast.parse(
        f"def _factory({', '.join(names)}):\n    return {{{', '.join(repr(w) + ': ' + w for w in wanted)}}}\n"
    )
    for name in reversed(wanted):
        factory.body[0].body.insert(0, funcs[name])
    ast.fix_missing_locations(factory)
    ns: dict = {}
    module_globals = vars(app).copy()
    module_globals["messagebox"] = _MessageboxProxy()  # follows mock.patch of app.messagebox
    exec(compile(factory, f"<{outer.__name__}>", "exec"), module_globals, ns)
    return ns["_factory"](**{n: env[n] for n in names})


class _MessageboxProxy:
    def __getattr__(self, name):
        return getattr(app.messagebox, name)


class _Text:
    def __init__(self, content: str = "") -> None:
        self.content = content

    def get(self, *_a):
        return self.content

    def delete(self, *_a):
        self.content = ""

    def insert(self, _i, value):
        self.content += value

    def config(self, **_k):
        pass


class _Var:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


# ======================================================================
# Fix A — detected mode
# ======================================================================
class FixAAdversarialTests(unittest.TestCase):
    def assert_becomes_1_eq_0(self, sql: str, expected: Optional[str] = None,
                              column: str = "acc_no") -> str:
        out = reset_column(sql, column)
        self.assertIn("1=0", out)
        if expected is not None:
            self.assertEqual(norm(out), norm(expected))
        self.assertLessEqual(affected(self, out), affected(self, sql),
                             f"{sql!r} -> {out!r} touches more rows than the original")
        return out

    def assert_rejected(self, sql: str, column: str = "acc_no") -> None:
        with self.assertRaises(ValueError) as ctx:
            reset_column(sql, column)
        self.assertIn("every row", str(ctx.exception))

    # --- mixed case and newlines between NOT and IN ---
    def test_mixed_case_newlines_negations_rejected(self):
        for sql in (
            "DELETE FROM acct WHERE acc_no\n  not\n  In ('1001')",
            "DELETE FROM acct WHERE acc_no nOt\r\n\r\niN('1001')",
            "delete from acct where NoT\n  acc_no\n  in ('1001')",
            "DELETE FROM acct WHERE nOT\n(\n acc_no IN ('1001'))",
            "DELETE FROM acct WHERE not exists\n(select 1 from acct b where acc_no in ('1001'))",
            "DELETE FROM acct WHERE status Not\nIn\n(select status from acct b where acc_no in ('1001'))",
        ):
            with self.subTest(sql=sql):
                self.assert_rejected(sql)

    def test_mixed_case_plain_in_becomes_1_eq_0(self):
        for sql, expected in (
            ("delete from acct where status is not null and acc_no\nIn\n('1001')",
             "delete from acct where status is not null and 1=0"),
            ("DELETE FROM acct WHERE status Is\nNot\nNull AND acc_no in('1001')",
             "DELETE FROM acct WHERE status Is Not Null AND 1=0"),
            ("update acct set flag='Y' where not exists (select 1 from acct b where b.status='Q')\n"
             " and acc_no IN ('1001','1002')",
             "update acct set flag='Y' where not exists (select 1 from acct b where b.status='Q') "
             "and 1=0"),
        ):
            with self.subTest(sql=sql):
                self.assert_becomes_1_eq_0(sql, expected)

    # --- NOT inside comments / strings right before IN ---
    def test_not_in_string_before_in_is_ignored(self):
        for sql in (
            "DELETE FROM acct WHERE status = 'NOT' AND acc_no IN ('1001')",
            "DELETE FROM acct WHERE status <> 'x NOT' AND acc_no IN ('1001')",
            "DELETE FROM acct WHERE status <> 'NOT (' AND acc_no IN ('1001')",
        ):
            with self.subTest(sql=sql):
                self.assert_becomes_1_eq_0(sql)

    def test_not_in_comment_on_other_predicate_is_ignored(self):
        for sql in (
            "DELETE FROM acct WHERE status = 'A' /* NOT */ AND acc_no IN ('1001')",
            "DELETE FROM acct WHERE status = 'x' -- NOT\n OR acc_no IN ('1001')",
            "DELETE FROM acct WHERE /* NOT ( */ acc_no IN ('1001')",
        ):
            with self.subTest(sql=sql):
                self.assert_becomes_1_eq_0(sql)

    def test_real_not_with_comment_between_is_rejected(self):
        for sql in (
            "DELETE FROM acct WHERE NOT -- why\n acc_no IN ('1001')",
            "DELETE FROM acct WHERE NOT /* x */ acc_no IN ('1001')",
            "DELETE FROM acct WHERE NOT /* ) */ (acc_no IN ('1001'))",
        ):
            with self.subTest(sql=sql):
                self.assert_rejected(sql)

    def test_line_comment_between_column_and_in_never_widens(self):
        """`acc_no -- note<newline>IN (...)` is a plain IN on acc_no.

        Emptying it must not touch more rows than the original DELETE.
        """
        for sql in (
            "DELETE FROM acct WHERE acc_no -- NOT\nIN ('1001')",
            "DELETE FROM acct WHERE acc_no -- account list\nIN ('1001')",
        ):
            with self.subTest(sql=sql):
                lists = GUI._detect_sql_in_lists(sql)
                self.assertEqual(len(lists), 1)
                try:
                    out = GUI._reset_sql_in_lists(sql, lists, {0: set(lists[0]["tokens"])})
                except ValueError:
                    continue  # refusing is safe
                self.assertLessEqual(
                    affected(self, out), affected(self, sql),
                    f"{sql!r} -> {out!r} touches more rows than the original")

    # --- nested parentheses ---
    def test_nested_group_becomes_1_eq_0(self):
        for sql, expected in (
            ("DELETE FROM acct WHERE status='A' AND (flag='Z' OR acc_no IN ('1001'))",
             "DELETE FROM acct WHERE status='A' AND (flag='Z' OR 1=0)"),
            ("DELETE FROM acct WHERE status='A' AND ((flag='Z') OR (acc_no IN ('1001')))",
             "DELETE FROM acct WHERE status='A' AND ((flag='Z') OR (1=0))"),
            ("DELETE FROM acct WHERE NOT (status='B') AND (flag='Z' OR acc_no IN ('1001'))",
             "DELETE FROM acct WHERE NOT (status='B') AND (flag='Z' OR 1=0)"),
            ("DELETE FROM acct WHERE (status IN ('A') OR (flag NOT IN ('q') AND acc_no IN ('1001')))",
             "DELETE FROM acct WHERE (status IN ('A') OR (flag NOT IN ('q') AND 1=0))"),
            ("SELECT * FROM acct WHERE status='A' AND (flag='Z' OR acc_no IN ('1001'))",
             "SELECT * FROM acct WHERE status='A' AND (flag='Z' OR 1=0)"),
        ):
            with self.subTest(sql=sql):
                self.assert_becomes_1_eq_0(sql, expected)

    def test_nested_group_wrapped_in_not_rejected(self):
        for sql in (
            "DELETE FROM acct WHERE NOT (status='A' AND (flag='Z' OR acc_no IN ('1001')))",
            "DELETE FROM acct WHERE flag='N' AND NOT ((status='A') OR (flag='Z' OR acc_no IN ('1001')))",
            "DELETE FROM acct WHERE (NOT (flag='Z' OR (acc_no IN ('1001'))))",
            "UPDATE acct SET flag='Y' WHERE NOT (UPPER(status)='A' AND acc_no IN ('1001'))",
        ):
            with self.subTest(sql=sql):
                self.assert_rejected(sql)

    def test_closed_function_call_before_list_is_skipped(self):
        self.assert_becomes_1_eq_0(
            "DELETE FROM acct WHERE NOT (UPPER(status) = 'B') AND acc_no IN ('1001')",
            "DELETE FROM acct WHERE NOT (UPPER(status) = 'B') AND 1=0")

    # --- several IN lists, only one negated ---
    def test_multiple_lists_only_one_negated(self):
        sql = "DELETE FROM acct WHERE status NOT IN ('B') AND acc_no IN ('1001','1003') AND flag IN ('N')"
        out = self.assert_becomes_1_eq_0(sql, column="acc_no")
        self.assertEqual(out, "DELETE FROM acct WHERE status NOT IN ('B') AND 1=0 AND flag IN ('N')")
        self.assert_becomes_1_eq_0(sql, column="flag")
        self.assert_rejected(sql, column="status")

    def test_multiple_lists_negated_one_partly_and_others_emptied(self):
        sql = "DELETE FROM acct WHERE status NOT IN ('B','C') OR acc_no IN ('1001') OR flag IN ('Z')"
        lists = GUI._detect_sql_in_lists(sql)
        out = GUI._reset_sql_in_lists(sql, lists, {0: {"'C'"}, 1: {"'1001'"}, 2: {"'Z'"}})
        self.assertEqual(out, "DELETE FROM acct WHERE status NOT IN ('B') OR 1=0 OR 1=0")
        self.assertLessEqual(affected(self, out), affected(self, sql))

    def test_multiple_lists_negation_scoped_to_its_group(self):
        sql = ("DELETE FROM acct WHERE NOT (status IN ('B')) AND (acc_no IN ('1001') "
               "OR NOT (flag IN ('Q')))")
        lists = GUI._detect_sql_in_lists(sql)
        self.assertEqual([i["column"] for i in lists], ["status", "acc_no", "flag"])
        self.assert_becomes_1_eq_0(sql, column="acc_no")
        self.assert_rejected(sql, column="status")
        self.assert_rejected(sql, column="flag")

    def test_rejection_leaves_no_partial_sql(self):
        sql = "DELETE FROM acct WHERE acc_no IN ('1001') AND NOT (flag IN ('Z'))"
        lists = GUI._detect_sql_in_lists(sql)
        with self.assertRaises(ValueError):
            GUI._reset_sql_in_lists(sql, lists, {0: {"'1001'"}, 1: {"'Z'"}})

    def test_not_col_in_subquery_rejected(self):
        """Review 🔴: `NOT x IN (SELECT ... WHERE col IN (...))` — emptying the inner
        list would make the outer NOT match every row, so the reset is refused
        (was wrongly pinned as a known limit: 1 row -> 3 rows)."""
        sql = ("DELETE FROM acct WHERE NOT status IN "
               "(SELECT status FROM acct WHERE acc_no IN ('1001'))")
        self.assert_rejected(sql)

    def test_nested_negation_without_not_paren_rejected(self):
        """Nested in a function call or a compared group: not provably positive,
        so the whitelist refuses the reset."""
        for sql in (
            "DELETE FROM acct WHERE NOT COALESCE(acc_no IN ('1001'), 0)",
            "DELETE FROM acct WHERE (acc_no IN ('1001')) = 0",
        ):
            with self.subTest(sql=sql):
                self.assert_rejected(sql)

    # --- formerly a known limit, now refused (QA bug 9: CASE at any level) ---
    def test_known_limit_negation_without_not_paren_shape(self):
        """Was a KNOWN LIMIT (top-level negation through CASE widened 2 -> 3
        rows). Bug 9 fix: a list inside an open CASE is refused at every
        level in UPDATE / DELETE, partial or empty."""
        sql = "DELETE FROM acct WHERE CASE WHEN acc_no IN ('1001') THEN 0 ELSE 1 END = 1"
        unchecked = "DELETE FROM acct WHERE CASE WHEN 1=0 THEN 0 ELSE 1 END = 1"
        self.assertEqual((affected(self, sql), affected(self, unchecked)), (2, 3))
        with self.assertRaises(ValueError) as ctx:
            reset_column(sql)
        self.assertIn("CASE", str(ctx.exception))


# ======================================================================
# Fix B — tracked mode (Auto WHERE from Excel)
# ======================================================================
class _TrackedBase(unittest.TestCase):
    TEMPLATE = "DELETE FROM acct WHERE flag='N'"
    VALUES = {
        "WHERE acc_no": (AUTO, "'1001', '1002'"),
        "WHERE status": (AUTO, "'A', 'B'"),
    }

    def make_stub(self, template: Optional[str] = None, values: Optional[dict] = None):
        stub = GUI.__new__(GUI)
        stub.sql_template = self.TEMPLATE if template is None else template
        stub._excel_parameter_values = dict(self.VALUES if values is None else values)
        stub._excel_parameterized_sql = None
        stub.root = mock.Mock(name="root")
        stub.debug_mode = _Var(False)
        rendered = stub._render_sql_template()
        stub.sql_context = _Text(rendered)
        stub._excel_parameterized_sql = rendered
        return stub

    def dialog_functions(self, stub, close_after_selected: bool = False) -> dict:
        self.column_selected: dict = {}
        self.column_tokens: dict = {}
        self.column_var = _Var("")
        self.dialog = mock.Mock(name="dialog")
        env = {
            "self": stub,
            "detected_mode": False,
            "detected": [],
            "source_sql": "",
            "column_selected": self.column_selected,
            "column_tokens": self.column_tokens,
            "column_var": self.column_var,
            "dialog": self.dialog,
            "close_after_selected": close_after_selected,
            "render_column_list": mock.Mock(name="render_column_list"),
            "render_values": mock.Mock(name="render_values"),
            "sql_preview": _Text(),
        }
        self.env = env
        funcs = compile_nested(
            GUI.show_reset_parameter_dialog,
            ("load_tokens", "selected_of", "build_reset_values", "render_sql",
             "build_detected_sql", "refresh_sql_preview", "write_sql", "reset_selected",
             "reset_all"),
            env,
        )
        funcs["load_tokens"]()
        return funcs

    def tick_all(self, key: str) -> None:
        self.column_selected[key] = set(self.column_tokens[key])


class FixBTwoColumnsTests(_TrackedBase):
    def test_reset_single_parameter_both_columns(self):
        stub = self.make_stub()
        with mock.patch.object(app, "messagebox") as mb:
            stub.reset_single_parameter("WHERE acc_no")
            first = stub.sql_context.content
            stub.reset_single_parameter("WHERE status")
            second = stub.sql_context.content
        mb.showerror.assert_not_called()
        self.assertEqual(norm(first), "DELETE FROM acct WHERE (flag='N') AND 1=0 AND status IN ('A', 'B')")
        self.assertEqual(norm(second), "DELETE FROM acct WHERE (flag='N') AND 1=0 AND 1=0")
        self.assertEqual(stub._excel_parameter_values,
                         {"WHERE acc_no": (AUTO, ""), "WHERE status": (AUTO, "")})
        self.assertEqual(stub._excel_parameterized_sql, second)
        self.assertEqual(affected(self, first), 0)
        self.assertEqual(affected(self, second), 0)

    def test_reset_single_parameter_twice_same_column_is_stable(self):
        stub = self.make_stub()
        with mock.patch.object(app, "messagebox"):
            stub.reset_single_parameter("WHERE acc_no")
            once = stub.sql_context.content
            stub.reset_single_parameter("WHERE acc_no")
        self.assertEqual(stub.sql_context.content, once)
        self.assertIn("1=0", once)

    def test_dialog_reset_one_column_then_the_other(self):
        stub = self.make_stub()
        f = self.dialog_functions(stub)
        with mock.patch.object(app, "messagebox") as mb:
            self.column_var.set("WHERE acc_no")
            self.tick_all("WHERE acc_no")
            f["refresh_sql_preview"]()
            preview = self.env["sql_preview"].content
            f["reset_selected"]()
            first = stub.sql_context.content
            self.assertEqual(norm(preview), norm(first))
            self.dialog.destroy.assert_not_called()  # status still has values
            self.assertEqual(self.column_tokens["WHERE acc_no"], [])
            self.assertEqual(self.column_selected, {})

            self.tick_all("WHERE status")
            f["reset_selected"]()
            second = stub.sql_context.content
        mb.showerror.assert_not_called()
        mb.showwarning.assert_not_called()
        self.assertEqual(norm(first), "DELETE FROM acct WHERE (flag='N') AND 1=0 AND status IN ('A', 'B')")
        self.assertEqual(norm(second), "DELETE FROM acct WHERE (flag='N') AND 1=0 AND 1=0")
        self.assertEqual(affected(self, first), 0)
        self.assertEqual(affected(self, second), 0)
        self.dialog.destroy.assert_called_once_with()  # nothing left -> dialog closes
        self.assertEqual(stub._excel_parameterized_sql, second)

    def test_dialog_partial_reset_keeps_dialog_open(self):
        stub = self.make_stub()
        f = self.dialog_functions(stub)
        self.column_selected["WHERE acc_no"] = {"'1002'"}
        with mock.patch.object(app, "messagebox"):
            f["reset_selected"]()
        out = stub.sql_context.content
        self.assertEqual(norm(out), "DELETE FROM acct WHERE (flag='N') AND acc_no IN ('1001') "
                                    "AND status IN ('A', 'B')")
        self.assertEqual(affected(self, out), 1)
        self.dialog.destroy.assert_not_called()
        self.assertEqual(self.column_tokens["WHERE acc_no"], ["'1001'"])

    def test_dialog_close_after_selected_still_closes(self):
        stub = self.make_stub()
        f = self.dialog_functions(stub, close_after_selected=True)
        self.column_selected["WHERE acc_no"] = {"'1002'"}
        with mock.patch.object(app, "messagebox"):
            f["reset_selected"]()
        self.dialog.destroy.assert_called_once_with()

    def test_dialog_select_template_all_reset_closes_and_restores_template(self):
        stub = self.make_stub(template="SELECT * FROM acct WHERE flag='N'")
        f = self.dialog_functions(stub)
        self.tick_all("WHERE acc_no")
        self.tick_all("WHERE status")
        with mock.patch.object(app, "messagebox"):
            f["reset_selected"]()
        self.assertEqual(stub._excel_parameter_values, {})
        self.assertEqual(stub.sql_context.content, "SELECT * FROM acct WHERE flag='N'")
        self.assertIsNone(stub._excel_parameterized_sql)
        self.dialog.destroy.assert_called_once_with()

    def test_dialog_reopened_after_full_reset_has_nothing_to_tick(self):
        stub = self.make_stub(values={"WHERE acc_no": (AUTO, "")})
        f = self.dialog_functions(stub)
        self.assertEqual(self.column_tokens, {"WHERE acc_no": []})
        with mock.patch.object(app, "messagebox") as mb:
            f["reset_selected"]()
        mb.showwarning.assert_called_once()
        self.assertEqual(norm(stub.sql_context.content), "DELETE FROM acct WHERE (flag='N') AND 1=0")

    def test_dialog_render_error_keeps_state(self):
        # emptied Auto WHERE where the statement type cannot be told -> kept, layout raises
        stub = GUI.__new__(GUI)
        stub.sql_template = "MERGE INTO acct USING x ON (1=1)"
        stub._excel_parameter_values = {"WHERE acc_no": (AUTO, "'1001'")}
        stub._excel_parameterized_sql = "rendered"
        stub.sql_context = _Text("rendered")
        stub.debug_mode = _Var(False)
        f = self.dialog_functions(stub)
        self.tick_all("WHERE acc_no")
        with mock.patch.object(app, "messagebox") as mb:
            f["reset_selected"]()
        mb.showerror.assert_called_once()
        self.assertEqual(stub._excel_parameter_values, {"WHERE acc_no": (AUTO, "'1001'")})
        self.assertEqual(stub.sql_context.content, "rendered")

    def test_reset_all_clears_state(self):
        stub = self.make_stub()
        with mock.patch.object(app, "messagebox") as mb:
            stub.reset_single_parameter("WHERE acc_no")
            stub.reset_single_parameter("WHERE status")
            stub.reset_all_parameters()
        mb.showinfo.assert_called_once()
        self.assertEqual(stub._excel_parameter_values, {})
        self.assertIsNone(stub._excel_parameterized_sql)
        self.assertEqual(stub.sql_context.content, self.TEMPLATE)

    def test_dialog_reset_all_button_clears_state(self):
        stub = self.make_stub(values={"WHERE acc_no": (AUTO, ""), "WHERE status": (AUTO, "'A'")})
        f = self.dialog_functions(stub)
        with mock.patch.object(app, "messagebox"):
            f["reset_all"]()
        self.assertEqual(stub._excel_parameter_values, {})
        self.assertEqual(stub.sql_context.content, self.TEMPLATE)
        self.dialog.destroy.assert_called_once_with()

    def test_capture_template_keeps_emptied_state(self):
        stub = self.make_stub()
        with mock.patch.object(app, "messagebox"):
            stub.reset_single_parameter("WHERE acc_no")
        rendered = stub.sql_context.content
        self.assertEqual(stub._capture_sql_template(rendered + "\n"), self.TEMPLATE)
        self.assertEqual(stub._excel_parameter_values["WHERE acc_no"], (AUTO, ""))


class FixBReimportTests(_TrackedBase):
    """Excel Import (apply_parameters, real code) after a full Reset."""

    def import_values(self, stub, column: str, values: list) -> mock.Mock:
        dialog = mock.Mock(name="excel_dialog")
        env = {
            "self": stub,
            "parameter_var": _Var("AUTO"),
            "auto_where_choice": "AUTO",
            "column_selected": {column: set(values)},
            "column_values": {column: list(values)},
            "column_lookup": {column: column},
            "sheet_data": {"dataframe": object()},
            "column_var": _Var(column),
            "sheet_var": _Var("Sheet1"),
            "dialog": dialog,
            "file_path": "book.xlsx",
        }
        funcs = compile_nested(
            GUI.load_excel_template_dialog,
            ("is_auto_where", "selected_of", "columns_with_selection", "build_pending_values",
             "apply_parameters"),
            env,
        )
        with mock.patch.object(app, "messagebox") as mb:
            funcs["apply_parameters"]()
        mb.showwarning.assert_not_called()
        return dialog

    def test_reimport_restores_normal_rendering(self):
        stub = self.make_stub()
        with mock.patch.object(app, "messagebox"):
            stub.reset_single_parameter("WHERE acc_no")
        self.assertIn("1=0", stub.sql_context.content)
        dialog = self.import_values(stub, "acc_no", ["1003"])
        out = stub.sql_context.content
        self.assertEqual(norm(out), "DELETE FROM acct WHERE (flag='N') AND acc_no IN ('1003') "
                                    "AND status IN ('A', 'B')")
        self.assertNotIn("1=0", out)
        self.assertEqual(stub._excel_parameter_values["WHERE acc_no"], (AUTO, "'1003'"))
        self.assertEqual(stub._excel_parameterized_sql, out)
        self.assertEqual(affected(self, out), 0)  # 1003 has flag 'Z'
        dialog.destroy.assert_called_once_with()

    def test_reimport_after_both_emptied(self):
        stub = self.make_stub()
        with mock.patch.object(app, "messagebox"):
            stub.reset_single_parameter("WHERE acc_no")
            stub.reset_single_parameter("WHERE status")
        self.import_values(stub, "status", ["A"])
        out = stub.sql_context.content
        # acc_no is still emptied -> still 1=0 for that column
        self.assertEqual(norm(out), "DELETE FROM acct WHERE (flag='N') AND 1=0 AND status IN ('A')")
        self.assertEqual(affected(self, out), 0)
        self.import_values(stub, "acc_no", ["1001", "1002"])
        out = stub.sql_context.content
        self.assertEqual(norm(out), "DELETE FROM acct WHERE (flag='N') AND acc_no IN ('1001', '1002') "
                                    "AND status IN ('A')")
        self.assertEqual(affected(self, out), 1)


class FixBPersistenceTests(_TrackedBase):
    """Save-as-job (excel_parameters on the job) -> saved_jobs.json -> reload."""

    def test_emptied_state_survives_save_and_reload(self):
        stub = self.make_stub()
        with mock.patch.object(app, "messagebox"):
            stub.reset_single_parameter("WHERE acc_no")
        query = stub.sql_context.content
        job = {"name": "j", "profile": "P", "query": query}
        job.update(stub._excel_state_for_job(query, stub.sql_template,
                                             stub._excel_parameter_values,
                                             stub._excel_parameterized_sql))
        self.assertEqual(job["excel_parameters"]["WHERE acc_no"], [AUTO, ""])

        with tempfile.TemporaryDirectory() as tmp:
            loader = GUI.__new__(GUI)
            loader.jobs_file = os.path.join(tmp, "saved_jobs.json")
            loader.saved_profiles = {"P": {}}
            loader._jobs_save_blocked = False
            loader.saved_jobs = [job]
            with mock.patch.object(app, "messagebox") as mb:
                loader.save_jobs()
            mb.showerror.assert_not_called()
            with open(loader.jobs_file, encoding="utf-8") as fh:
                self.assertEqual(json.load(fh)[0]["excel_parameters"]["WHERE acc_no"], [AUTO, ""])
            loaded = loader.load_jobs()

        fresh = GUI.__new__(GUI)
        fresh._apply_job_excel_state(loaded[0])
        self.assertEqual(fresh.sql_template, self.TEMPLATE)
        self.assertEqual(fresh._excel_parameter_values,
                         {"WHERE acc_no": (AUTO, ""), "WHERE status": (AUTO, "'A', 'B'")})
        self.assertEqual(fresh._excel_parameterized_sql, query)
        # the reloaded state renders to exactly the saved query, and the job runs as 0 rows
        self.assertEqual(fresh._render_sql_template(), query)
        self.assertEqual(affected(self, loaded[0]["query"]), 0)

    def test_saved_query_carries_1_eq_0_even_without_excel_state(self):
        # the job's "query" itself (what Run executes) already contains 1=0
        stub = self.make_stub(values={"WHERE acc_no": (AUTO, "'1001'")})
        with mock.patch.object(app, "messagebox"):
            stub.reset_single_parameter("WHERE acc_no")
        query = stub.sql_context.content
        self.assertEqual(norm(query), "DELETE FROM acct WHERE (flag='N') AND 1=0")
        state = GUI._excel_state_for_job(query, stub.sql_template, stub._excel_parameter_values,
                                         stub._excel_parameterized_sql)
        self.assertEqual(state["excel_parameters"], {"WHERE acc_no": [AUTO, ""]})


class FixBRenderingUnchangedTests(unittest.TestCase):
    def test_append_where_with_values_unchanged(self):
        cases = [
            ("SELECT * FROM t", [("C", "'x'")], "SELECT * FROM t WHERE C IN ('x')"),
            ("DELETE FROM acct WHERE status='A' OR flag='Z'", [("acc_no", "'1001', '1003'")],
             "DELETE FROM acct WHERE (status='A' OR flag='Z') AND acc_no IN ('1001', '1003')"),
            ("SELECT status, COUNT(*) FROM acct GROUP BY status ORDER BY status;",
             [("acc_no", "'1001'"), ("flag", "'N'")],
             "SELECT status, COUNT(*) FROM acct WHERE acc_no IN ('1001') AND flag IN ('N') "
             "GROUP BY status ORDER BY status;"),
            ("UPDATE acct SET flag='Y'", [("acc_no", "1001")],
             "UPDATE acct SET flag='Y' WHERE acc_no IN (1001)"),
        ]
        for sql, conditions, expected in cases:
            with self.subTest(sql=sql):
                self.assertEqual(norm(GUI._append_where_conditions(sql, conditions)), expected)
        self.assertEqual(GUI._append_where_conditions("SELECT * FROM t", []), "SELECT * FROM t")

    def test_blank_values_render_1_eq_0(self):
        for blank in ("", "   "):
            with self.subTest(blank=repr(blank)):
                self.assertEqual(
                    norm(GUI._append_where_conditions("DELETE FROM acct", [("acc_no", blank)])),
                    "DELETE FROM acct WHERE 1=0")

    def test_run_export_values_on_sqlite(self):
        stub = GUI.__new__(GUI)
        stub.sql_template = "UPDATE acct SET flag='Y' WHERE status='A'"
        stub._excel_parameter_values = {"WHERE acc_no": (AUTO, "'1001', '1002'")}
        out = stub._render_sql_template()
        self.assertEqual(norm(out), "UPDATE acct SET flag='Y' WHERE (status='A') AND acc_no IN ('1001', '1002')")
        con = acct_db(self)
        self.assertEqual(con.execute(out).rowcount, 1)

    def test_other_parameter_kinds_return_to_placeholder(self):
        for template in ("DELETE FROM acct WHERE acc_no = :ACC", "SELECT * FROM acct WHERE acc_no = :ACC"):
            with self.subTest(template=template):
                self.assertIsNone(GUI._reset_parameter_value(template, ":ACC", []))
                self.assertIsNone(GUI._reset_parameter_value(template, "__FIRST_IN_LIST__", []))
                self.assertIsNone(GUI._reset_parameter_value(template, GUI.IN_COLUMN_PARAMETER, []))

    def test_reset_parameter_value_statement_types(self):
        cases = [
            ("SELECT * FROM t", None),
            ("select * from t", None),
            ("-- note\n/* c */ SELECT * FROM t", None),
            ("WITH c AS (SELECT 1 FROM u) SELECT * FROM c", None),
            ("DELETE FROM t", (AUTO, "")),
            ("update t set a = 1", (AUTO, "")),
            ("WITH c AS (SELECT 1 FROM u) DELETE FROM t", (AUTO, "")),
            ("", (AUTO, "")),
            (None, (AUTO, "")),
            ("(SELECT * FROM t)", (AUTO, "")),
            ("MERGE INTO t USING u ON (1=1)", (AUTO, "")),
        ]
        for template, expected in cases:
            with self.subTest(template=template):
                self.assertEqual(GUI._reset_parameter_value(template, AUTO, []), expected)

    def test_where_main_command(self):
        cases = [
            ("SELECT 1 FROM t", "SELECT"),
            ("  delete from t;", "DELETE"),
            ("WITH a AS (SELECT 1 FROM u) UPDATE t SET x = 1", "UPDATE"),
            ("DELETE FROM t\n/\n", "DELETE"),
            ("", None),
            (None, None),
            ("BEGIN NULL; END;", None),
            ("INSERT INTO t SELECT * FROM u", None),
            ("WITH a AS (SELECT 1 FROM u)", None),
            ("-- only a comment", None),
        ]
        for sql, expected in cases:
            with self.subTest(sql=sql):
                self.assertEqual(app._where_main_command(sql), expected)


if __name__ == "__main__":
    unittest.main()
