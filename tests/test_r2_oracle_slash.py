"""R2-T1 (M3): an Oracle '/' line separates statements (R2-AC-23..26).

Pure functions only (split_sql_statements, assess_sql, _scan_sql,
_mark_oracle_slash_lines, strip_sql_terminator); _prepare_run_sql via a stub.
"""

import ast
import inspect
import os
import sys
import textwrap
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import database_connect_gui as app  # noqa: E402
from database_connect_gui import SqlRisk, assess_sql, split_sql_statements  # noqa: E402

MARK = "\x1e"


def assert_no_marker(test, statements):
    for s in statements:
        test.assertNotIn(MARK, s)


class SplitOnSlashLineTests(unittest.TestCase):
    def test_r2_ac23_two_plsql_blocks(self):
        sql = "BEGIN NULL; END;\n/\nBEGIN NULL; END;\n/"
        parts = split_sql_statements(sql)
        self.assertEqual(parts, ["BEGIN NULL; END;", "BEGIN NULL; END;"])
        assert_no_marker(self, parts)

    def test_r2_ac24_select_then_delete(self):
        sql = "SELECT 1 FROM dual\n/\nDELETE FROM t\n/"
        self.assertEqual(split_sql_statements(sql), ["SELECT 1 FROM dual", "DELETE FROM t"])
        a = assess_sql(sql)
        self.assertEqual(a.statement_count, 2)
        self.assertIs(a.risk, SqlRisk.DATA_CHANGE)
        stub = app.DatabaseConnectorGUI.__new__(app.DatabaseConnectorGUI)
        self.assertIs(stub.is_select_query(sql), False)

    def test_r2_ac26_edge_cases(self):
        cases = [
            ("SELECT * FROM dual\n/", ["SELECT * FROM dual"]),
            ("SELECT 4 / 2 FROM dual", ["SELECT 4 / 2 FROM dual"]),
            ("SELECT 1 FROM dual\n  /  \nSELECT 2 FROM dual",
             ["SELECT 1 FROM dual", "SELECT 2 FROM dual"]),
            ("SELECT 'a\n/\nb' FROM dual", ["SELECT 'a\n/\nb' FROM dual"]),
        ]
        for sql, expected in cases:
            with self.subTest(sql=sql):
                parts = split_sql_statements(sql)
                self.assertEqual(parts, expected)
                self.assertEqual(assess_sql(sql).statement_count, len(expected))
                assert_no_marker(self, parts)
        self.assertIs(assess_sql("SELECT * FROM dual\n/").risk, SqlRisk.READ_ONLY)
        self.assertIs(assess_sql("SELECT 'a\n/\nb' FROM dual").risk, SqlRisk.READ_ONLY)

    def test_tab_around_slash(self):
        sql = "SELECT 1 FROM dual\n\t/\t\nSELECT 2 FROM dual"
        parts = split_sql_statements(sql)
        self.assertEqual(parts, ["SELECT 1 FROM dual", "SELECT 2 FROM dual"])
        assert_no_marker(self, parts)

    def test_crlf_line_endings(self):
        """SQL saved with Windows line endings (jobs.json / presets / imports)."""
        sql = "SELECT 1 FROM dual\r\n/\r\nDELETE FROM t\r\n/"
        parts = split_sql_statements(sql)
        self.assertEqual(parts, ["SELECT 1 FROM dual", "DELETE FROM t"])
        assert_no_marker(self, parts)
        a = assess_sql(sql)
        self.assertEqual(a.statement_count, 2)
        self.assertIs(a.risk, SqlRisk.DATA_CHANGE)

    def test_mixed_lf_and_crlf(self):
        sql = "SELECT 1 FROM dual\n/\r\nSELECT 2 FROM dual\r\n  /  \nDELETE FROM t\n/"
        parts = split_sql_statements(sql)
        self.assertEqual(parts, ["SELECT 1 FROM dual", "SELECT 2 FROM dual", "DELETE FROM t"])
        assert_no_marker(self, parts)
        for p in parts:
            self.assertNotIn("\r", p)
        self.assertIs(assess_sql(sql).risk, SqlRisk.DATA_CHANGE)

    def test_crlf_marker_keeps_cr_and_length(self):
        sql = "a\r\n/\r\nb\r\n \t/ \r\nc"
        marked = app._mark_oracle_slash_lines(sql)
        self.assertEqual(len(marked), len(sql))
        self.assertEqual(marked, f"a\r\n{MARK}\r\nb\r\n \t{MARK} \r\nc")
        self.assertEqual(marked.count("\r"), sql.count("\r"))

    def test_crlf_division_and_string_untouched(self):
        for sql in ("SELECT 4\r\n/ 2 FROM dual", "SELECT 'x\r\n/\r\ny' FROM dual"):
            with self.subTest(sql=repr(sql)):
                self.assertEqual(split_sql_statements(sql), [sql])

    def test_lone_cr_does_not_crash(self):
        sql = "SELECT 1 FROM dual\r/\rSELECT 2 FROM dual"
        marked = app._mark_oracle_slash_lines(sql)
        self.assertEqual(len(marked), len(sql))
        parts = split_sql_statements(sql)
        self.assertIsInstance(parts, list)
        assert_no_marker(self, parts)
        self.assertGreaterEqual(assess_sql(sql).statement_count, 1)

    def test_slash_line_inside_block_comment_is_not_separator(self):
        sql = "SELECT 1 /* note\n/\nmore */ FROM dual"
        parts = split_sql_statements(sql)
        self.assertEqual(parts, [sql])
        assert_no_marker(self, parts)
        self.assertEqual(assess_sql(sql).statement_count, 1)

    def test_slash_after_line_comment(self):
        # '/' only on a comment line is part of the comment
        self.assertEqual(len(split_sql_statements("SELECT 1 FROM dual -- a / b\nWHERE 1=1")), 1)
        # a '/' line after a '--' comment line is a real separator
        sql = "SELECT 1 FROM dual -- first\n/\nSELECT 2 FROM dual"
        self.assertEqual(len(split_sql_statements(sql)), 2)

    def test_slash_in_quoted_identifier_and_dollar_string(self):
        for sql in ('SELECT "a\n/\nb" FROM dual', "SELECT $$x\n/\ny$$"):
            with self.subTest(sql=repr(sql)):
                parts = split_sql_statements(sql)
                self.assertEqual(parts, [sql])

    def test_single_trailing_slash_and_semicolon(self):
        for sql in ("SELECT 1 FROM dual;\n/", "SELECT 1 FROM dual\n/\n", "/\nSELECT 1 FROM dual"):
            with self.subTest(sql=repr(sql)):
                self.assertEqual(split_sql_statements(sql), ["SELECT 1 FROM dual"])

    def test_only_slashes_or_empty(self):
        for sql in ("/", "\n/\n/\n", "", None, "   "):
            with self.subTest(sql=repr(sql)):
                self.assertEqual(split_sql_statements(sql), [])
                self.assertEqual(assess_sql(sql or "").statement_count, 0)

    def test_create_procedure_then_slash_then_select(self):
        sql = ("CREATE OR REPLACE PROCEDURE p AS\nBEGIN\n  NULL;\nEND;\n/\n"
               "SELECT 1 FROM dual\n/")
        parts = split_sql_statements(sql)
        self.assertEqual(len(parts), 2)
        self.assertTrue(parts[0].endswith("END;"))
        self.assertEqual(parts[1], "SELECT 1 FROM dual")
        self.assertIs(assess_sql(sql).risk, SqlRisk.SCHEMA_CHANGE)

    def test_semicolon_split_unchanged(self):
        self.assertEqual(split_sql_statements("SELECT 1; SELECT 2;"), ["SELECT 1", "SELECT 2"])
        self.assertEqual(split_sql_statements("SELECT 'a;b' FROM t"), ["SELECT 'a;b' FROM t"])


class MarkSlashLinesTests(unittest.TestCase):
    def test_same_length_and_only_slash_lines(self):
        cases = [
            "SELECT 1 FROM dual\n/\nSELECT 2",
            "SELECT 4 / 2 FROM dual",
            "a\n  /  \nb",
            "x\r\n/\r\ny",
            "/* c */\n/\n",
            "SELECT 1 /* x */ FROM t",
            "a //\n/ b\n",
        ]
        for sql in cases:
            with self.subTest(sql=repr(sql)):
                marked = app._mark_oracle_slash_lines(sql)
                self.assertEqual(len(marked), len(sql))
                for i, (o, m) in enumerate(zip(sql, marked)):
                    if o != m:
                        self.assertEqual((o, m), ("/", MARK))
                        line_start = sql.rfind("\n", 0, i) + 1
                        line_end = sql.find("\n", i)
                        line = sql[line_start: len(sql) if line_end < 0 else line_end]
                        self.assertEqual(line.strip(), "/")

    def test_division_untouched(self):
        sql = "SELECT 4 / 2 FROM dual"
        self.assertEqual(app._mark_oracle_slash_lines(sql), sql)
        self.assertEqual(app._mark_oracle_slash_lines("a //\n/ b\n"), "a //\n/ b\n")

    def test_marks_each_slash_line(self):
        self.assertEqual(app._mark_oracle_slash_lines("/\n/"), f"{MARK}\n{MARK}")
        self.assertEqual(app._mark_oracle_slash_lines("a\n  /  \nb"), f"a\n  {MARK}  \nb")

    def test_scan_sees_marker_as_sep(self):
        tokens = list(app._scan_sql(app._mark_oracle_slash_lines("SELECT 1\n/\nSELECT 2")))
        seps = [t for t in tokens if t[0] == "sep"]
        self.assertEqual(len(seps), 1)
        self.assertEqual(seps[0][1], "/")
        self.assertTrue(MARK.isspace())  # why the check must come before isspace()

    def test_scan_unmarked_slash_is_punct(self):
        tokens = list(app._scan_sql("SELECT 1\n/\nSELECT 2"))
        self.assertFalse(any(t[0] == "sep" for t in tokens))


class OtherHelpersUnchangedTests(unittest.TestCase):
    def test_strip_sql_terminator(self):
        self.assertEqual(app.strip_sql_terminator("DELETE FROM t;\n/\n"), "DELETE FROM t")
        self.assertEqual(app.strip_sql_terminator("BEGIN\n  NULL;\nEND;\n/"), "BEGIN\n  NULL;\nEND;")
        self.assertEqual(app.strip_sql_terminator("SELECT 4 / 2 FROM dual"), "SELECT 4 / 2 FROM dual")
        self.assertEqual(app.strip_sql_terminator("UPDATE t SET a = 1 /* x */"),
                         "UPDATE t SET a = 1 /* x */")

    def test_classify_statement(self):
        self.assertEqual(app._classify_sql_statement("SELECT 4 / 2 FROM dual")[1], SqlRisk.READ_ONLY)
        self.assertEqual(app._classify_sql_statement("DELETE FROM t")[1], SqlRisk.DATA_CHANGE)
        self.assertEqual(app._classify_sql_statement("BEGIN NULL; END;")[1], SqlRisk.UNKNOWN)


class _FakeText:
    def __init__(self):
        self.log = []

    def insert(self, _i, v):
        self.log.append(v)

    def see(self, *_a):
        pass


class PrepareRunSqlSlashTests(unittest.TestCase):
    """R2-AC-25"""

    def _prepare(self, jobs):
        stub = type("Stub", (), {})()
        stub.results_text = _FakeText()
        stub._current_table_data_tables = mock.Mock(return_value={})
        with mock.patch.object(app, "messagebox") as mb:
            result = app.DatabaseConnectorGUI._prepare_run_sql(stub, jobs)
        return result, mb

    def test_slash_separated_blocked(self):
        result, mb = self._prepare([{"name": "J", "query": "SELECT 1 FROM dual\n/\nDELETE FROM t\n/"}])
        self.assertIsNone(result)
        mb.showerror.assert_called_once()
        self.assertIn("more than one", mb.showerror.call_args[0][1])
        self.assertIn("J", mb.showerror.call_args[0][1])

    def test_single_statement_with_trailing_slash_passes(self):
        sql = "SELECT * FROM dual\n/"
        result, mb = self._prepare([{"name": "J", "query": sql}])
        self.assertEqual(result, [sql])
        mb.showerror.assert_not_called()

    def test_division_passes(self):
        sql = "SELECT 4 / 2 FROM dual"
        result, mb = self._prepare([{"name": None, "query": sql}])
        self.assertEqual(result, [sql])
        mb.showerror.assert_not_called()


class ExportSkipsMultiStatementTests(unittest.TestCase):
    def test_export_worker_checks_statement_count(self):
        src = textwrap.dedent(inspect.getsource(app.DatabaseConnectorGUI.export_jobs_to_excel))
        tree = ast.parse(src)
        found = False
        for node in ast.walk(tree):
            if (isinstance(node, ast.Compare) and isinstance(node.left, ast.Attribute)
                    and node.left.attr == "statement_count"
                    and isinstance(node.ops[0], ast.Gt)
                    and getattr(node.comparators[0], "value", None) == 1):
                found = True
        self.assertTrue(found, "export must skip SQL with statement_count > 1")
        self.assertIn("ALLOW_MULTI_STATEMENT_SQL", src)
        self.assertIs(app.ALLOW_MULTI_STATEMENT_SQL, False)

    def test_export_skip_condition_true_for_slash_sql(self):
        stub = app.DatabaseConnectorGUI.__new__(app.DatabaseConnectorGUI)
        sql = "SELECT 1 FROM dual\n/\nDELETE FROM t\n/"
        # same condition as the worker: not SELECT or more than one statement
        self.assertTrue(not stub.is_select_query(sql) or assess_sql(sql).statement_count > 1)
        two_selects = "SELECT 1 FROM dual\n/\nSELECT 2 FROM dual"
        self.assertTrue(stub.is_select_query(two_selects))
        self.assertGreater(assess_sql(two_selects).statement_count, 1)


if __name__ == "__main__":
    unittest.main()
