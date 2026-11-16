"""R2-T2 (H3): Auto WHERE adds conditions at the right place (R2-AC-1..14).

Pure functions + in-memory SQLite to prove UPDATE/DELETE never touch more rows.
"""

import os
import re
import sqlite3
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import database_connect_gui as app  # noqa: E402

GUI = app.DatabaseConnectorGUI
APPEND = GUI._append_where_conditions
CX = [("C", "'x'")]


def norm(sql: str) -> str:
    return re.sub(r"\s+", " ", sql).strip()


def top_where_count(sql: str) -> int:
    tokens = list(app._scan_sql(app._mark_oracle_slash_lines(sql)))
    return sum(1 for t in tokens if t[0] == "word" and t[1] == "WHERE" and t[2] == 0)


def where_followed_by(test, sql, column="C"):
    """There is a depth-0 WHERE token (outside comments) and 'C IN' after the new WHERE."""
    tokens = [t for t in app._scan_sql(app._mark_oracle_slash_lines(sql)) if t[2] == 0]
    words = [(t[1], i) for i, t in enumerate(tokens) if t[0] == "word"]
    test.assertTrue(any(w == "WHERE" for w, _ in words), sql)
    col_idx = [i for i, t in enumerate(tokens) if t[0] == "word" and t[1] == column]
    test.assertTrue(col_idx, sql)
    nxt = tokens[col_idx[-1] + 1]
    test.assertEqual((nxt[0], nxt[1]), ("word", "IN"))


class SpecExamplesTests(unittest.TestCase):
    def test_r2_ac1_or_wrapped(self):
        sql = "UPDATE acct SET flag='Y' WHERE status='A' OR status='B'"
        out = APPEND(sql, [("ACC_NO", "'1','2'")])
        self.assertEqual(
            norm(out),
            norm("UPDATE acct SET flag='Y' WHERE (status='A' OR status='B') AND ACC_NO IN ('1','2')"),
        )

    def test_r2_ac2_sqlite_update_changes_only_targets(self):
        sql = "UPDATE acct SET flag='Y' WHERE status='A' OR status='B'"
        out = APPEND(sql, [("ACC_NO", "'1','2'")])
        con = sqlite3.connect(":memory:")
        self.addCleanup(con.close)
        con.execute("CREATE TABLE acct (acc_no TEXT, status TEXT, flag TEXT)")
        con.executemany("INSERT INTO acct VALUES (?, ?, 'N')",
                        [("1", "A"), ("2", "B"), ("3", "A"), ("4", "B")])
        con.execute(out)
        changed = [r[0] for r in con.execute("SELECT acc_no FROM acct WHERE flag='Y' ORDER BY acc_no")]
        self.assertEqual(changed, ["1", "2"])

    def test_r2_ac3_order_by_stays_last(self):
        out = APPEND("SELECT * FROM t WHERE a = 1 ORDER BY a", CX)
        self.assertEqual(norm(out), "SELECT * FROM t WHERE (a = 1) AND C IN ('x') ORDER BY a")

    def test_r2_ac4_no_where_with_order_by(self):
        out = APPEND("SELECT * FROM t ORDER BY a", CX)
        self.assertEqual(norm(out), "SELECT * FROM t WHERE C IN ('x') ORDER BY a")

    def test_r2_ac5_group_by_having(self):
        sql = "SELECT a, COUNT(*) FROM t WHERE x = 1 GROUP BY a HAVING COUNT(*) > 1"
        self.assertEqual(
            norm(APPEND(sql, CX)),
            "SELECT a, COUNT(*) FROM t WHERE (x = 1) AND C IN ('x') GROUP BY a HAVING COUNT(*) > 1",
        )

    def test_r2_ac6_where_only_in_subquery(self):
        sql = "SELECT * FROM (SELECT * FROM t WHERE x = 1) s"
        self.assertEqual(norm(APPEND(sql, CX)),
                         "SELECT * FROM (SELECT * FROM t WHERE x = 1) s WHERE C IN ('x')")

    def test_r2_ac7_subquery_in_condition(self):
        sql = "SELECT * FROM t WHERE id IN (SELECT id FROM u WHERE y = 2)"
        self.assertEqual(norm(APPEND(sql, CX)),
                         "SELECT * FROM t WHERE (id IN (SELECT id FROM u WHERE y = 2)) AND C IN ('x')")

    def test_r2_ac8_where_in_string_or_comment(self):
        sql = "SELECT 'WHERE' AS w FROM t -- WHERE x"
        out = APPEND(sql, CX)
        self.assertEqual(top_where_count(out), 1)
        where_followed_by(self, out)
        self.assertEqual(norm(out), "SELECT 'WHERE' AS w FROM t WHERE C IN ('x') -- WHERE x")
        block = "SELECT * FROM t /* WHERE a = 1 */"
        out2 = APPEND(block, CX)
        self.assertEqual(top_where_count(out2), 1)
        where_followed_by(self, out2)

    def test_r2_ac9_terminators(self):
        self.assertEqual(APPEND("SELECT * FROM t;", CX), "SELECT * FROM t\nWHERE C IN ('x');")
        out = APPEND("SELECT * FROM t\n/", CX)
        self.assertTrue(out.endswith("\n/"))
        self.assertEqual(norm(out), "SELECT * FROM t WHERE C IN ('x') /")
        out = APPEND("DELETE FROM t WHERE a = 1;\n", CX)
        self.assertEqual(out, "DELETE FROM t WHERE (a = 1)\nAND C IN ('x');\n")

    def test_r2_ac10_two_conditions_delete(self):
        out = APPEND("DELETE FROM t WHERE x = 1", [("C1", "'a'"), ("C2", "'b'")])
        self.assertEqual(norm(out), "DELETE FROM t WHERE (x = 1) AND C1 IN ('a') AND C2 IN ('b')")
        self.assertEqual(top_where_count(out), 1)

    def test_r2_ac11_cte_where_not_counted(self):
        sql = "WITH x AS (SELECT * FROM u WHERE k = 1) SELECT * FROM x"
        self.assertEqual(norm(APPEND(sql, CX)),
                         "WITH x AS (SELECT * FROM u WHERE k = 1) SELECT * FROM x WHERE C IN ('x')")

    def test_r2_ac12_uncertain_raises(self):
        cases = {
            "SELECT a FROM t UNION SELECT a FROM u": "UNION",
            "SELECT a FROM t INTERSECT SELECT a FROM u": "INTERSECT",
            "SELECT a FROM t EXCEPT SELECT a FROM u": "EXCEPT",
            "SELECT a FROM t MINUS SELECT a FROM u": "MINUS",
            "SELECT 1 FROM t; DELETE FROM t": "more than one",
            "SELECT 1 FROM dual\n/\nDELETE FROM t": "more than one",
            "INSERT INTO t SELECT * FROM u": "INSERT",
            "MERGE INTO t USING u ON (t.id = u.id) WHEN MATCHED THEN UPDATE SET a = 1": "MERGE",
            "BEGIN DELETE FROM t; END;": "BEGIN",
            "DECLARE x NUMBER; BEGIN NULL; END;": "DECLARE",
            "SELECT * FROM t WHERE (a = 1": "unbalanced",
            "SELECT * FROM t WHERE a = 1)": "unbalanced",
            "": "empty",
            ";": "empty",
            "SELECT 1": "without FROM",
            "UPDATE t": "without SET",
            "SELECT * FROM t WHERE ORDER BY a": "no condition",
            "SELECT * FROM t WHERE": "no condition",
            "CREATE TABLE x AS SELECT * FROM t": "CREATE",
            "(SELECT * FROM t)": "must start",
        }
        for sql, reason in cases.items():
            with self.subTest(sql=sql):
                with self.assertRaises(ValueError) as ctx:
                    APPEND(sql, CX)
                self.assertIn(reason.lower(), str(ctx.exception).lower())

    def test_r2_ac12_set_op_inside_subquery_is_fine(self):
        sql = "SELECT * FROM (SELECT a FROM t UNION SELECT a FROM u) s"
        self.assertEqual(norm(APPEND(sql, CX)),
                         "SELECT * FROM (SELECT a FROM t UNION SELECT a FROM u) s WHERE C IN ('x')")

    def test_r2_ac14_empty_conditions_and_plain(self):
        for sql in ("anything at all ((( ", "SELECT * FROM t WHERE a=1 OR b=2", ""):
            self.assertEqual(APPEND(sql, []), sql)
        self.assertEqual(norm(APPEND("SELECT * FROM t", CX)), "SELECT * FROM t WHERE C IN ('x')")


class MoreLayoutTests(unittest.TestCase):
    def test_crlf_and_slash_line(self):
        out = APPEND("SELECT * FROM t\r\nWHERE a = 1 OR b = 2\r\n/\r\n", CX)
        self.assertTrue(out.endswith("\r\n/\r\n"))
        self.assertEqual(norm(out), "SELECT * FROM t WHERE (a = 1 OR b = 2) AND C IN ('x') /")

    def test_order_group_as_names(self):
        sql = "SELECT order_no, \"order\" FROM t WHERE grp = 1 OR order_type = 2 ORDER BY order_no"
        out = APPEND(sql, CX)
        self.assertEqual(norm(out), norm(
            "SELECT order_no, \"order\" FROM t WHERE (grp = 1 OR order_type = 2) AND C IN ('x') ORDER BY order_no"))
        # ORDER / GROUP not followed by BY are not clauses
        sql2 = "SELECT * FROM t WHERE a = 1 OR \"GROUP\" = 2"
        self.assertEqual(norm(APPEND(sql2, CX)),
                         "SELECT * FROM t WHERE (a = 1 OR \"GROUP\" = 2) AND C IN ('x')")

    def test_tail_clauses_after_new_condition(self):
        cases = [
            ("SELECT * FROM t WHERE a = 1 OR b = 2 FOR UPDATE",
             "SELECT * FROM t WHERE (a = 1 OR b = 2) AND C IN ('x') FOR UPDATE"),
            ("SELECT * FROM t ORDER BY a FETCH FIRST 10 ROWS ONLY",
             "SELECT * FROM t WHERE C IN ('x') ORDER BY a FETCH FIRST 10 ROWS ONLY"),
            ("SELECT * FROM t WHERE a = 1 LIMIT 5 OFFSET 2",
             "SELECT * FROM t WHERE (a = 1) AND C IN ('x') LIMIT 5 OFFSET 2"),
            ("SELECT * FROM t OFFSET 5 ROWS",
             "SELECT * FROM t WHERE C IN ('x') OFFSET 5 ROWS"),
            ("DELETE FROM t WHERE a = 1 OR b = 2 RETURNING id",
             "DELETE FROM t WHERE (a = 1 OR b = 2) AND C IN ('x') RETURNING id"),
            ("UPDATE t SET a = 1 RETURNING id",
             "UPDATE t SET a = 1 WHERE C IN ('x') RETURNING id"),
            ("SELECT * FROM t WHERE a = 1 OPTION (MAXDOP 1)",
             "SELECT * FROM t WHERE (a = 1) AND C IN ('x') OPTION (MAXDOP 1)"),
            ("SELECT * FROM emp START WITH mgr IS NULL CONNECT BY PRIOR id = mgr",
             "SELECT * FROM emp WHERE C IN ('x') START WITH mgr IS NULL CONNECT BY PRIOR id = mgr"),
            ("DELETE FROM t ORDER BY id LIMIT 5",
             "DELETE FROM t WHERE C IN ('x') ORDER BY id LIMIT 5"),
        ]
        for sql, expected in cases:
            with self.subTest(sql=sql):
                self.assertEqual(norm(APPEND(sql, CX)), expected)

    def test_update_without_where(self):
        self.assertEqual(norm(APPEND("UPDATE t SET a = 1, b = 'x'", CX)),
                         "UPDATE t SET a = 1, b = 'x' WHERE C IN ('x')")
        self.assertEqual(norm(APPEND("UPDATE t SET a = (SELECT MAX(v) FROM u WHERE u.k = t.k)", CX)),
                         "UPDATE t SET a = (SELECT MAX(v) FROM u WHERE u.k = t.k) WHERE C IN ('x')")

    def test_delete_without_from_keyword(self):
        self.assertEqual(norm(APPEND("DELETE t WHERE a = 1 OR b = 2", CX)),
                         "DELETE t WHERE (a = 1 OR b = 2) AND C IN ('x')")

    def test_comment_between_condition_and_order_by(self):
        sql = "SELECT * FROM t WHERE a = 1 OR b = 2 -- old filter\nORDER BY a"
        out = APPEND(sql, CX)
        self.assertEqual(out,
                         "SELECT * FROM t WHERE (a = 1 OR b = 2)\nAND C IN ('x') -- old filter\nORDER BY a")
        sql2 = "SELECT * FROM t WHERE a = 1 /* keep */ ORDER BY a"
        self.assertEqual(APPEND(sql2, CX),
                         "SELECT * FROM t WHERE (a = 1)\nAND C IN ('x') /* keep */ ORDER BY a")

    def test_comment_inside_condition_kept_inside_parens(self):
        sql = "DELETE FROM t WHERE a = 1 -- first\nOR b = 2"
        out = APPEND(sql, CX)
        self.assertEqual(out, "DELETE FROM t WHERE (a = 1 -- first\nOR b = 2)\nAND C IN ('x')")

    def test_trailing_line_comment_no_where(self):
        out = APPEND("SELECT * FROM t -- note", CX)
        self.assertEqual(out, "SELECT * FROM t\nWHERE C IN ('x') -- note")

    def test_block_comment_with_where(self):
        sql = "SELECT * FROM t /* WHERE a = 1 OR */ WHERE b = 2"
        self.assertEqual(norm(APPEND(sql, CX)),
                         "SELECT * FROM t /* WHERE a = 1 OR */ WHERE (b = 2) AND C IN ('x')")

    def test_quoted_where_column(self):
        sql = 'SELECT "where", [where], `where` FROM t WHERE "where" = 1 OR x = 2'
        self.assertEqual(norm(APPEND(sql, CX)), norm(
            'SELECT "where", [where], `where` FROM t WHERE ("where" = 1 OR x = 2) AND C IN (\'x\')'))

    def test_deep_subqueries(self):
        sql = ("SELECT (SELECT MAX(z) FROM (SELECT z FROM w WHERE q = 1 ORDER BY z) zz WHERE 1=1) m "
               "FROM (SELECT * FROM (SELECT * FROM t WHERE a = 1 OR b = 2) i WHERE c = 3) o "
               "ORDER BY m")
        out = APPEND(sql, CX)
        self.assertEqual(norm(out), norm(sql.replace(" ORDER BY m", " WHERE C IN ('x') ORDER BY m")))
        self.assertEqual(top_where_count(out), 1)

    def test_multiple_ctes(self):
        sql = ("WITH a AS (SELECT * FROM t WHERE x = 1), b AS (SELECT * FROM a WHERE y = 2 ORDER BY y) "
               "SELECT * FROM b WHERE z = 3 OR z = 4 ORDER BY z")
        out = APPEND(sql, CX)
        self.assertEqual(norm(out), norm(sql.replace("WHERE z = 3 OR z = 4 ORDER BY z",
                                                     "WHERE (z = 3 OR z = 4) AND C IN ('x') ORDER BY z")))

    def test_with_delete(self):
        sql = "WITH d AS (SELECT id FROM u WHERE k = 1) DELETE FROM t WHERE id IN (SELECT id FROM d) OR f = 1"
        self.assertEqual(norm(APPEND(sql, CX)), norm(
            "WITH d AS (SELECT id FROM u WHERE k = 1) DELETE FROM t WHERE (id IN (SELECT id FROM d) OR f = 1) "
            "AND C IN ('x')"))

    def test_with_insert_rejected(self):
        with self.assertRaises(ValueError):
            APPEND("WITH d AS (SELECT 1 FROM t) INSERT INTO u SELECT * FROM d", CX)

    def test_two_top_level_wheres_rejected(self):
        with self.assertRaises(ValueError):
            APPEND("SELECT * FROM t WHERE a = 1 WHERE b = 2", CX)

    def test_layout_values(self):
        sql = "SELECT * FROM t WHERE a = 1 ORDER BY a;"
        lay = app._sql_where_layout(sql)
        self.assertEqual(sql[lay.condition[0]:lay.condition[1]], "a = 1")
        self.assertEqual(lay.insert_at, lay.condition[1])
        lay2 = app._sql_where_layout("SELECT * FROM t ORDER BY a")
        self.assertIsNone(lay2.condition)
        self.assertEqual("SELECT * FROM t ORDER BY a"[:lay2.insert_at], "SELECT * FROM t")


class NeverWiderOnSqliteTests(unittest.TestCase):
    """Heart of H3: rows touched after Auto WHERE ⊆ rows of (original filter AND new filter)."""

    ROWS = [(i, s, g) for i, (s, g) in enumerate(
        [(s, g) for s in "ABCD" for g in ("x", "y", "z")], start=1)]

    TEMPLATES = [
        "UPDATE t SET flag = 'Y' WHERE s = 'A' OR s = 'B'",
        "UPDATE t SET flag = 'Y' WHERE s = 'A' OR s = 'B' AND g = 'y'",
        "UPDATE t SET flag = 'Y' WHERE (s = 'A') OR (s = 'B')",
        "UPDATE t SET flag = 'Y' WHERE s IN ('A','B') OR g = 'z' -- note",
        "UPDATE t SET flag = 'Y' WHERE s = 'A' OR id IN (SELECT id FROM t WHERE g = 'x' OR g = 'y')",
        "UPDATE t SET flag = 'Y' WHERE NOT s = 'A' OR g = 'z';",
        "UPDATE t SET flag = 'Y'",
        "UPDATE t SET flag = CASE WHEN s = 'A' THEN 'Y' ELSE 'Y' END WHERE s = 'A' OR s = 'C'",
        "WITH k AS (SELECT id FROM t WHERE s = 'A' OR s = 'B') "
        "UPDATE t SET flag = 'Y' WHERE id IN (SELECT id FROM k) OR g = 'z'",
        "UPDATE t SET flag = 'Y' WHERE s = 'A' OR s = 'B'\n/",
        "UPDATE t SET flag = 'Y' WHERE s = 'A' /* OR 1=1 */ OR s = 'D'",
    ]

    def _db(self):
        con = sqlite3.connect(":memory:")
        self.addCleanup(con.close)
        con.execute("CREATE TABLE t (id INTEGER, s TEXT, g TEXT, flag TEXT)")
        con.executemany("INSERT INTO t VALUES (?, ?, ?, 'N')", self.ROWS)
        return con

    def _flagged(self, con):
        return {r[0] for r in con.execute("SELECT id FROM t WHERE flag = 'Y'")}

    def test_update_never_wider(self):
        conds = [("g", "'x','y'")]
        for sql in self.TEMPLATES:
            with self.subTest(sql=sql):
                out = APPEND(sql, conds)
                runnable = out.replace("\n/", "")
                con = self._db()
                con.execute(app.strip_sql_terminator(runnable))
                got = self._flagged(con)
                ref = self._db()
                ref.execute(app.strip_sql_terminator(sql.replace("\n/", "")))
                original = self._flagged(ref)
                allowed = {r[0] for r in self.ROWS if r[2] in ("x", "y")}
                self.assertEqual(got, original & allowed)

    def test_delete_never_wider(self):
        conds = [("s", "'A'"), ("g", "'x'")]
        for where in ("s = 'A' OR s = 'B'", "g = 'x' OR 1 = 1", "s <> 'C' OR g = 'z' -- tail"):
            with self.subTest(where=where):
                sql = f"DELETE FROM t WHERE {where}"
                con = self._db()
                con.execute(APPEND(sql, conds))
                left = {r[0] for r in con.execute("SELECT id FROM t")}
                ref = self._db()
                ref.execute(sql)
                ref_left = {r[0] for r in ref.execute("SELECT id FROM t")}
                deleted = {r[0] for r in self.ROWS} - left
                ref_deleted = {r[0] for r in self.ROWS} - ref_left
                target = {r[0] for r in self.ROWS if r[1] == "A" and r[2] == "x"}
                self.assertEqual(deleted, ref_deleted & target)

    def test_select_never_wider(self):
        con = self._db()
        sql = "SELECT id FROM t WHERE s = 'A' OR s = 'B' ORDER BY id"
        rows = [r[0] for r in con.execute(APPEND(sql, [("g", "'z'")]))]
        self.assertEqual(rows, [r[0] for r in self.ROWS if r[1] in "AB" and r[2] == "z"])


class RenderTemplateTests(unittest.TestCase):
    """R2-AC-13 (logic part): ValueError reaches the callers, which already catch it."""

    def _stub(self, template, values):
        stub = GUI.__new__(GUI)
        stub.sql_template = template
        stub._excel_parameter_values = dict(values)
        return stub

    def test_union_raises(self):
        stub = self._stub("SELECT a FROM t UNION SELECT a FROM u",
                          {"WHERE ACC_NO": (GUI.AUTO_WHERE_PARAMETER, "'1','2'")})
        with self.assertRaises(ValueError) as ctx:
            stub._render_sql_template()
        self.assertIn("UNION", str(ctx.exception))

    def test_where_rendered(self):
        stub = self._stub("UPDATE acct SET flag='Y' WHERE status='A' OR status='B'",
                          {"WHERE ACC_NO": (GUI.AUTO_WHERE_PARAMETER, "'1','2'")})
        self.assertEqual(norm(stub._render_sql_template()),
                         "UPDATE acct SET flag='Y' WHERE (status='A' OR status='B') AND ACC_NO IN ('1','2')")

    def test_reset_single_parameter_catches_error(self):
        stub = self._stub("SELECT a FROM t UNION SELECT a FROM u", {
            "WHERE A": (GUI.AUTO_WHERE_PARAMETER, "'1'"),
            "WHERE B": (GUI.AUTO_WHERE_PARAMETER, "'2'"),
        })
        stub.root = mock.Mock()
        stub.sql_context = mock.Mock()
        with mock.patch.object(app, "messagebox") as mb:
            stub.reset_single_parameter("WHERE A")
        mb.showerror.assert_called_once()
        stub.sql_context.delete.assert_not_called()
        self.assertIn("WHERE A", stub._excel_parameter_values)

    def test_callers_catch_value_error(self):
        import inspect

        src = inspect.getsource(GUI)
        # Excel Import Apply restores previous values and warns
        self.assertRegex(src, r"rendered_sql = self\._render_sql_template\(\)\s*\n\s*except ValueError")
        self.assertIn("self._excel_parameter_values.update(previous_values)", src)
        # preview of Excel Import and of Reset, and Reset Apply
        self.assertRegex(src, r"preview_sql = self\._render_sql_template\(preview_values\)\s*\n\s*except ValueError")
        self.assertRegex(src, r"preview_sql = render_sql\(build_reset_values\(\)\)\s*\n\s*except ValueError")
        self.assertRegex(src, r"rendered_sql = render_sql\(new_values\)\s*\n\s*except ValueError")


if __name__ == "__main__":
    unittest.main()
