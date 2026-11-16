"""R2-T3 / R2-T4 (M9): Reset Parameter in detected mode (R2-AC-15..22).

_reset_sql_in_lists on real SQLite, plus the dialog's nested functions
(build_detected_sql / refresh_sql_preview / reset_selected) compiled from the
source with fakes. The popup itself is Manual/GUI.
"""

import ast
import inspect
import os
import re
import sqlite3
import sys
import textwrap
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import database_connect_gui as app  # noqa: E402

GUI = app.DatabaseConnectorGUI


def norm(sql):
    return re.sub(r"\s+", " ", sql).strip()


def reset(sql, remove):
    """remove: {list index: set of tokens to drop}."""
    lists = GUI._detect_sql_in_lists(sql)
    return GUI._reset_sql_in_lists(sql, lists, remove)


def reset_all_values(sql, index=0):
    lists = GUI._detect_sql_in_lists(sql)
    return GUI._reset_sql_in_lists(sql, lists, {index: set(lists[index]["tokens"])})


ROWS = [("1001", "A"), ("1002", "B"), ("1003", "A")]


def acct_db(test):
    con = sqlite3.connect(":memory:")
    test.addCleanup(con.close)
    con.execute("CREATE TABLE acct (acc_no TEXT, status TEXT, flag TEXT)")
    con.executemany("INSERT INTO acct VALUES (?, ?, 'N')", ROWS)
    con.commit()
    return con


class SpecTests(unittest.TestCase):
    def test_r2_ac15_delete_becomes_1_eq_0(self):
        out = reset("DELETE FROM acct WHERE acc_no IN ('1001','1002')", {0: {"'1001'", "'1002'"}})
        self.assertEqual(norm(out), "DELETE FROM acct WHERE 1=0")
        self.assertNotEqual(norm(out), "DELETE FROM acct")

    def test_r2_ac16_zero_rows_on_sqlite(self):
        for sql in ("DELETE FROM acct WHERE acc_no IN ('1001','1002')",
                    "UPDATE acct SET flag='Y' WHERE acc_no IN ('1001')"):
            with self.subTest(sql=sql):
                con = acct_db(self)
                cur = con.execute(reset_all_values(sql))
                self.assertEqual(cur.rowcount, 0)
                self.assertEqual(con.execute("SELECT COUNT(*) FROM acct").fetchone()[0], 3)
                self.assertEqual(con.execute("SELECT COUNT(*) FROM acct WHERE flag='Y'").fetchone()[0], 0)

    def test_r2_ac17_and_status(self):
        out = reset_all_values("DELETE FROM acct WHERE status='A' AND acc_no IN ('1001')")
        self.assertEqual(norm(out), "DELETE FROM acct WHERE status='A' AND 1=0")
        con = acct_db(self)
        self.assertEqual(con.execute(out).rowcount, 0)

    def test_r2_ac18_select(self):
        out = reset_all_values("SELECT * FROM acct WHERE acc_no IN ('1001')")
        self.assertEqual(norm(out), "SELECT * FROM acct WHERE 1=0")
        self.assertEqual(acct_db(self).execute(out).fetchall(), [])

    def test_r2_ac19_some_values_left(self):
        out = reset("SELECT * FROM acct WHERE acc_no IN ('1001','1002','1003')", {0: {"'1002'"}})
        self.assertEqual(out, "SELECT * FROM acct WHERE acc_no IN ('1001', '1003')")

    def test_r2_ac20_or_status(self):
        sql = "DELETE FROM acct WHERE status='A' OR acc_no IN ('1001')"
        out = reset_all_values(sql)
        con = acct_db(self)
        con.execute(out)
        left = sorted(r[0] for r in con.execute("SELECT acc_no FROM acct"))
        self.assertEqual(left, ["1002"])  # exactly the status='A' rows were deleted

    def test_r2_ac21_not_in_rejected(self):
        sql = "DELETE FROM acct WHERE acc_no NOT IN ('1001')"
        with self.assertRaises(ValueError) as ctx:
            reset_all_values(sql)
        msg = str(ctx.exception)
        self.assertIn("NOT IN", msg)
        self.assertIn("every row", msg)

    def test_not_in_partial_removal_allowed(self):
        out = reset("DELETE FROM acct WHERE acc_no NOT IN ('1001','1002')", {0: {"'1001'"}})
        self.assertEqual(out, "DELETE FROM acct WHERE acc_no NOT IN ('1002')")


class SpellingAndShapeTests(unittest.TestCase):
    def test_not_in_spellings(self):
        for sql in ("DELETE FROM t WHERE c not in ('1')",
                    "DELETE FROM t WHERE c NOT\nIN ('1')",
                    "DELETE FROM t WHERE c NOT    IN    ('1')",
                    "DELETE FROM t WHERE c NOT\tIN\t('1')",
                    "DELETE FROM t WHERE c Not In('1')",
                    "DELETE FROM t WHERE c NOT\r\nIN ('1')"):
            with self.subTest(sql=repr(sql)):
                with self.assertRaises(ValueError):
                    reset_all_values(sql)

    def test_in_spellings(self):
        for sql in ("DELETE FROM t WHERE c in ('1')", "DELETE FROM t WHERE c\nIN\n('1')",
                    "DELETE FROM t WHERE c IN('1')"):
            with self.subTest(sql=repr(sql)):
                self.assertEqual(norm(reset_all_values(sql)), "DELETE FROM t WHERE 1=0")

    def test_column_ending_in_not_is_not_not_in(self):
        # a column named "...not" must not be mistaken for NOT IN
        out = reset_all_values("DELETE FROM t WHERE is_not IN ('1')")
        self.assertEqual(norm(out), "DELETE FROM t WHERE 1=0")

    def test_several_lists_positions(self):
        sql = ("DELETE FROM t WHERE a IN ('1','2') AND b IN ('x','y','z') "
               "AND c IN (5, 6)")
        lists = GUI._detect_sql_in_lists(sql)
        self.assertEqual([i["column"] for i in lists], ["a", "b", "c"])
        out = GUI._reset_sql_in_lists(sql, lists, {0: {"'1'", "'2'"}, 1: {"'y'"}, 2: {"5"}})
        self.assertEqual(out, "DELETE FROM t WHERE 1=0 AND b IN ('x', 'z') AND c IN (6)")

    def test_several_lists_one_not_in_emptied_raises_whole_call(self):
        sql = "DELETE FROM t WHERE a IN ('1','2') AND b NOT IN ('x') AND c IN ('q','r')"
        lists = GUI._detect_sql_in_lists(sql)
        with self.assertRaises(ValueError):
            GUI._reset_sql_in_lists(sql, lists, {0: {"'1'"}, 1: {"'x'"}, 2: {"'q'", "'r'"}})

    def test_qualified_and_quoted_columns(self):
        cases = [
            ("DELETE FROM t a WHERE a.col IN ('1')", "DELETE FROM t a WHERE 1=0"),
            ('DELETE FROM t WHERE "My Col" IN (\'1\')', "DELETE FROM t WHERE 1=0"),
            ('DELETE FROM t WHERE s . "c" IN (\'1\')', "DELETE FROM t WHERE 1=0"),
        ]
        for sql, expected in cases:
            with self.subTest(sql=sql):
                self.assertEqual(norm(reset_all_values(sql)), expected)

    def test_subquery_in_list_not_detected(self):
        sql = "DELETE FROM t WHERE id IN (SELECT id FROM u) AND c IN ('1')"
        lists = GUI._detect_sql_in_lists(sql)
        self.assertEqual([i["column"] for i in lists], ["c"])
        out = GUI._reset_sql_in_lists(sql, lists, {0: {"'1'"}})
        self.assertEqual(out, "DELETE FROM t WHERE id IN (SELECT id FROM u) AND 1=0")

    def test_quoted_values_with_comma_and_paren(self):
        sql = "SELECT * FROM t WHERE c IN ('a,b', 'x)y', 'O''Brien')"
        out = reset(sql, {0: {"'x)y'"}})
        self.assertEqual(out, "SELECT * FROM t WHERE c IN ('a,b', 'O''Brien')")

    def test_nothing_selected_returns_same_sql(self):
        sql = "DELETE FROM t WHERE c IN ('1')"
        self.assertEqual(reset(sql, {}), sql)
        self.assertEqual(reset(sql, {0: set()}), sql)

    def test_remove_sql_condition_is_gone(self):
        self.assertFalse(hasattr(GUI, "_remove_sql_condition"))
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(root, "database_connect_gui.py"), encoding="utf-8") as fh:
            self.assertNotIn("_remove_sql_condition", fh.read())


class CommentAndStringLiteralTests(unittest.TestCase):
    """IN (...) text inside comments / string literals is never a list."""

    def test_in_inside_string_literal_not_detected(self):
        sql = "UPDATE acct SET note = 'moved acc IN (1)' WHERE acc IN (5)"
        lists = GUI._detect_sql_in_lists(sql)
        self.assertEqual([(i["column"], i["tokens"]) for i in lists], [("acc", ["5"])])
        out = GUI._reset_sql_in_lists(sql, lists, {0: {"5"}})
        self.assertEqual(out, "UPDATE acct SET note = 'moved acc IN (1)' WHERE 1=0")

    def test_in_inside_block_comment_not_detected(self):
        sql = "DELETE FROM acct WHERE /* IN (1) */ acc_no IN ('1001')"
        lists = GUI._detect_sql_in_lists(sql)
        self.assertEqual([(i["column"], i["tokens"]) for i in lists], [("acc_no", ["'1001'"])])
        out = GUI._reset_sql_in_lists(sql, lists, {0: {"'1001'"}})
        self.assertEqual(out, "DELETE FROM acct WHERE /* IN (1) */ 1=0")

    def test_in_inside_comment_only_finds_nothing(self):
        for sql in ("SELECT * FROM acct /* acc_no IN (1) */",
                    "SELECT * FROM acct -- acc_no IN ('1001')\n",
                    "SELECT 'acc_no IN (1)' FROM acct"):
            with self.subTest(sql=sql):
                self.assertEqual(GUI._detect_sql_in_lists(sql), [])

    def test_line_comment_between_column_and_in(self):
        sql = "DELETE FROM acct WHERE acc_no -- account list\nIN ('1001')"
        lists = GUI._detect_sql_in_lists(sql)
        self.assertEqual([i["column"] for i in lists], ["acc_no"])
        self.assertEqual(reset_all_values(sql), "DELETE FROM acct WHERE 1=0")

    def test_comment_between_column_and_in_zero_rows_on_sqlite(self):
        for sql in ("DELETE FROM acct WHERE acc_no -- NOT\nIN ('1001')",
                    "DELETE FROM acct WHERE acc_no /* list */ IN ('1001')"):
            with self.subTest(sql=sql):
                con = acct_db(self)
                con.execute(reset_all_values(sql))
                self.assertEqual(con.execute("SELECT COUNT(*) FROM acct").fetchone()[0], 3)

    def test_real_not_with_comment_between_still_rejected(self):
        sql = "DELETE FROM acct WHERE acc_no NOT /* x */ IN ('1001')"
        with self.assertRaises(ValueError):
            reset_all_values(sql)


class NegatedInTests(unittest.TestCase):
    """NOT not directly in front of IN: an emptied list must not turn into 'every row'."""

    CASES = [
        "DELETE FROM acct WHERE NOT (acc_no IN ('1001'))",
        "DELETE FROM acct WHERE NOT acc_no IN ('1001')",
        "DELETE FROM acct WHERE status = 'B' AND NOT (acc_no IN ('1001'))",
    ]

    def test_negated_in_never_deletes_more_than_original(self):
        for sql in self.CASES:
            with self.subTest(sql=sql):
                try:
                    out = reset_all_values(sql)
                except ValueError:
                    continue  # refused like NOT IN: fine
                con = acct_db(self)
                deleted = con.execute(out).rowcount
                ref = acct_db(self)
                original = ref.execute(sql).rowcount
                self.assertLessEqual(
                    deleted, original,
                    f"{sql!r} -> {out!r} deletes {deleted} rows, original deletes {original}",
                )


class NotOfOtherPredicateTests(unittest.TestCase):
    """Bug 4: a NOT that belongs to another predicate must not block a plain IN."""

    def test_plain_in_after_other_not_becomes_1_eq_0(self):
        cases = [
            ("DELETE FROM acct WHERE status IS NOT NULL AND acc_no IN ('1001')",
             "DELETE FROM acct WHERE status IS NOT NULL AND 1=0"),
            ("DELETE FROM acct WHERE NOT EXISTS (SELECT 1 FROM u WHERE u.id = acct.acc_no) "
             "AND acc_no IN ('1001')",
             "DELETE FROM acct WHERE NOT EXISTS (SELECT 1 FROM u WHERE u.id = acct.acc_no) "
             "AND 1=0"),
            ("DELETE FROM acct WHERE status NOT IN ('9') AND acc_no IN ('1001')",
             "DELETE FROM acct WHERE status NOT IN ('9') AND 1=0"),
            ("DELETE FROM acct WHERE NOT status = 'B' AND acc_no IN ('1001')",
             "DELETE FROM acct WHERE NOT status = 'B' AND 1=0"),
            ("DELETE FROM acct WHERE (NOT status = 'B') AND acc_no IN ('1001')",
             "DELETE FROM acct WHERE (NOT status = 'B') AND 1=0"),
            ("DELETE FROM acct WHERE status <> 'NOT' AND acc_no IN ('1001') -- NOT",
             "DELETE FROM acct WHERE status <> 'NOT' AND 1=0 -- NOT"),
        ]
        for sql, expected in cases:
            with self.subTest(sql=sql):
                lists = GUI._detect_sql_in_lists(sql)
                index = [i["column"] for i in lists].index("acc_no")
                out = reset_all_values(sql, index)
                self.assertEqual(norm(out), expected)

    def test_is_not_null_zero_rows_on_sqlite(self):
        out = reset_all_values("DELETE FROM acct WHERE status IS NOT NULL AND acc_no IN ('1001')")
        con = acct_db(self)
        self.assertEqual(con.execute(out).rowcount, 0)
        self.assertEqual(con.execute("SELECT COUNT(*) FROM acct").fetchone()[0], 3)

    def test_true_negations_still_rejected(self):
        for sql in (
            "DELETE FROM acct WHERE acc_no NOT IN ('1001')",
            "DELETE FROM acct WHERE status IS NOT NULL AND acc_no NOT IN ('1001')",
            "DELETE FROM acct WHERE NOT acc_no IN ('1001')",
            "DELETE FROM acct WHERE NOT acct.acc_no IN ('1001')",
            "DELETE FROM acct WHERE NOT (acc_no IN ('1001'))",
            "DELETE FROM acct WHERE NOT ((acc_no IN ('1001')))",
            "DELETE FROM acct WHERE status = 'B' AND NOT (acc_no IN ('1001'))",
            "DELETE FROM acct WHERE NOT (status = 'A' AND acc_no IN ('1001'))",
            "DELETE FROM acct WHERE NOT (status = 'A' OR (flag = 'N' AND acc_no IN ('1001')))",
            "DELETE FROM acct WHERE NOT\n(acc_no IN ('1001'))",
            "DELETE FROM acct WHERE NOT EXISTS (SELECT 1 FROM u WHERE acc_no IN ('1001'))",
            "DELETE FROM acct WHERE id NOT IN (SELECT id FROM u WHERE acc_no IN ('1001'))",
        ):
            with self.subTest(sql=sql):
                lists = GUI._detect_sql_in_lists(sql)
                index = [i["column"] for i in lists].index(
                    "acct.acc_no" if "acct.acc_no" in sql else "acc_no")
                with self.assertRaises(ValueError):
                    reset_all_values(sql, index)

    def test_not_in_closed_group_before_does_not_count(self):
        sql = "DELETE FROM acct WHERE NOT (status = 'B') AND acc_no IN ('1001')"
        self.assertEqual(norm(reset_all_values(sql)),
                         "DELETE FROM acct WHERE NOT (status = 'B') AND 1=0")


class ColumnShapeTests(unittest.TestCase):
    """QA round 2 Bugs 6-8: only a plain column starting a predicate is
    detected; keywords are never the column; subqueries and comment commas
    never become values."""

    def test_keyword_is_never_the_column(self):
        for sql in (
            "DELETE FROM acct WHERE CASE WHEN status = 'A' THEN 1 ELSE 0 END IN (1)",
            "DELETE FROM acct WHERE NOT IN ('1001')",
            "SELECT * FROM acct WHERE IN ('1001')",
            "SELECT * FROM acct WHERE status = 'A' AND IN ('1001')",
            "SELECT * FROM acct WHERE (SELECT 1) IN (1)",
        ):
            with self.subTest(sql=sql):
                self.assertEqual(GUI._detect_sql_in_lists(sql), [])

    def test_operator_before_column_not_detected(self):
        for sql in (
            "DELETE FROM acct WHERE 1 - n IN (5)",
            "DELETE FROM acct WHERE 0 * n IN (5)",
            "DELETE FROM acct WHERE status || acc_no IN ('A1001')",
            "DELETE FROM acct WHERE x = acc_no IN ('1001')",
        ):
            with self.subTest(sql=sql):
                self.assertEqual(GUI._detect_sql_in_lists(sql), [])

    def test_allowed_leads_still_detected(self):
        for sql, column in (
            ("acc_no IN ('1001')", "acc_no"),
            ("DELETE FROM acct WHERE acc_no IN ('1001')", "acc_no"),
            ("DELETE FROM acct WHERE NOT acc_no IN ('1001')", "acc_no"),
            ("DELETE FROM acct WHERE (acc_no IN ('1001'))", "acc_no"),
            ("SELECT CASE WHEN acc_no IN ('1001') THEN 1 END FROM acct", "acc_no"),
            ("DELETE FROM acct WHERE flag = 'N' OR /* c */ acc_no IN ('1001')", "acc_no"),
            ("SELECT * FROM acct a JOIN acct b ON b.acc_no IN ('1001')", "b.acc_no"),
            ("SELECT status FROM acct GROUP BY status HAVING status IN ('A')", "status"),
        ):
            with self.subTest(sql=sql):
                self.assertEqual([i["column"] for i in GUI._detect_sql_in_lists(sql)], [column])

    def test_subquery_after_comment_not_detected(self):
        for sql in (
            "DELETE FROM acct WHERE acc_no IN (-- scope\n SELECT acc_no FROM acct)",
            "DELETE FROM acct WHERE acc_no IN (/* c */ select acc_no FROM acct)",
            "DELETE FROM acct WHERE acc_no IN (WITH t AS (SELECT 1) SELECT 1 FROM t)",
        ):
            with self.subTest(sql=sql):
                self.assertEqual(GUI._detect_sql_in_lists(sql), [])

    def test_comma_in_comment_does_not_split_values(self):
        sql = "DELETE FROM acct WHERE acc_no IN ('1001', -- x, 1\n '1002')"
        (item,) = GUI._detect_sql_in_lists(sql)
        self.assertEqual(item["tokens"], ["'1001'", "'1002'"])
        self.assertEqual(norm(reset(sql, {0: {"'1001'"}})),
                         "DELETE FROM acct WHERE acc_no IN ('1002')")

    def test_empty_value_or_comment_inside_value_not_detected(self):
        for sql in (
            "DELETE FROM acct WHERE acc_no IN ('1001', , '1002')",
            "DELETE FROM acct WHERE n IN (1 /* c */ + 2)",
        ):
            with self.subTest(sql=sql):
                self.assertEqual(GUI._detect_sql_in_lists(sql), [])


LKP_ROWS = [("1001", "C"), ("1002", "D"), ("1003", "E")]


def acct_lkp_db(test):
    con = acct_db(test)
    con.execute("CREATE TABLE lkp (code TEXT, seg TEXT)")
    con.executemany("INSERT INTO lkp VALUES (?, ?)", LKP_ROWS)
    con.commit()
    return con


def touched(test, sql):
    """Rows a DELETE touches on a fresh acct + lkp database."""
    return acct_lkp_db(test).execute(sql).rowcount


def seg_list(sql):
    lists = GUI._detect_sql_in_lists(sql)
    return [i["column"] for i in lists].index(
        next(i["column"] for i in lists if i["column"].lower().endswith("seg"))), lists


def unchecked_reset(sql, remove):
    """What the reset would write for the seg list without any safety check."""
    index, lists = seg_list(sql)
    item = lists[index]
    remaining = [t for t in item["tokens"] if t not in remove]
    if remaining:
        start, end = item["vals_span"]
        return sql[:start] + ", ".join(remaining) + sql[end:]
    start, end = item["span"]
    return sql[:start] + "1=0" + sql[end:]


class NestedListWhitelistTests(unittest.TestCase):
    """Review 🔴 / 🟠: an IN list inside a subquery / group may be reset only
    when every enclosing level is provably positive; any other reset of it
    (partial or empty) raises ValueError, so it can never widen a DELETE."""

    ALL = {"'C'", "'D'"}
    PARTIAL = {"'C'"}

    # (sql, rows the original deletes) — checked on SQLite: the unchecked
    # rewrite deletes more rows, so the reset must be refused
    WIDENING_ON_SQLITE = [
        ("DELETE FROM acct WHERE NOT acc_no IN "
         "(SELECT code FROM lkp WHERE seg IN ('C', 'D'))", 1),
        ("DELETE FROM acct WHERE NOT status IN "
         "(SELECT status FROM acct JOIN lkp ON code = acc_no WHERE seg IN ('C', 'D'))", 0),
        ("DELETE FROM acct WHERE acc_no NOT IN "
         "(SELECT code FROM lkp WHERE seg IN ('C', 'D'))", 1),
        ("DELETE FROM acct WHERE NOT EXISTS "
         "(SELECT 1 FROM lkp WHERE code = acc_no AND seg IN ('C', 'D'))", 1),
        ("DELETE FROM acct WHERE NOT (acc_no IN "
         "(SELECT code FROM lkp WHERE seg IN ('C', 'D')))", 1),
        ("DELETE FROM acct WHERE acc_no IN (SELECT acc_no FROM acct "
         "EXCEPT SELECT code FROM lkp WHERE seg IN ('C', 'D'))", 1),
        ("DELETE FROM acct WHERE acc_no IN (SELECT a.acc_no FROM acct a LEFT JOIN lkp b "
         "ON b.code = a.acc_no AND b.seg IN ('C', 'D') WHERE b.code IS NULL)", 1),
        ("DELETE FROM acct WHERE acc_no IN (SELECT a.acc_no FROM acct a LEFT OUTER JOIN lkp b "
         "ON (b.code = a.acc_no AND b.seg IN ('C', 'D')) WHERE b.code IS NULL)", 1),
        ("DELETE FROM acct WHERE acc_no IN (SELECT a.acc_no FROM lkp b RIGHT JOIN acct a "
         "ON b.code = a.acc_no AND b.seg IN ('C', 'D') WHERE b.code IS NULL)", 1),
        ("DELETE FROM acct WHERE acc_no IN (SELECT a.acc_no FROM acct a FULL JOIN lkp b "
         "ON b.code = a.acc_no AND b.seg IN ('C', 'D') WHERE b.code IS NULL)", 1),
        ("DELETE FROM acct WHERE (SELECT COUNT(*) FROM lkp WHERE lkp.code = acct.acc_no "
         "AND lkp.seg IN ('C', 'D')) = 0", 1),
        ("DELETE FROM acct WHERE 0 = (SELECT COUNT(*) FROM lkp WHERE lkp.code = acct.acc_no "
         "AND lkp.seg IN ('C', 'D'))", 1),
    ]
    # Oracle / other dialects (not on SQLite): refused by the same rules
    REFUSED_OTHER = [
        "DELETE FROM acct WHERE acc_no <> ALL (SELECT code FROM lkp WHERE seg IN ('C', 'D'))",
        "DELETE FROM acct WHERE NOT acc_no = ANY (SELECT code FROM lkp WHERE seg IN ('C', 'D'))",
        "DELETE FROM acct WHERE acc_no = SOME (SELECT code FROM lkp WHERE seg IN ('C', 'D'))",
        "DELETE FROM acct WHERE acc_no IN (SELECT acc_no FROM acct "
        "MINUS SELECT code FROM lkp WHERE seg IN ('C', 'D'))",
        "DELETE FROM acct WHERE acc_no IN (SELECT acc_no FROM acct "
        "INTERSECT SELECT code FROM lkp WHERE seg IN ('C', 'D'))",
        "DELETE FROM acct WHERE CASE WHEN acc_no IN (SELECT code FROM lkp "
        "WHERE seg IN ('C', 'D')) THEN 0 ELSE 1 END = 1",
        "DELETE FROM acct WHERE acc_no IN (SELECT code FROM lkp "
        "WHERE seg IN ('C', 'D') AND ROWNUM <= 1)",
        "DELETE FROM acct a WHERE a.acc_no IN (SELECT code FROM lkp b "
        "WHERE CASE WHEN b.seg IN ('C', 'D') THEN 0 ELSE 1 END = 1)",
        # rows of a grouped / aggregated subquery are not monotone in its WHERE
        "DELETE FROM acct WHERE status IN (SELECT a.status FROM acct a JOIN lkp b "
        "ON b.code = a.acc_no WHERE b.seg IN ('C', 'D') GROUP BY a.status "
        "HAVING COUNT(*) < 2)",
        "DELETE FROM acct WHERE acc_no IN (SELECT MIN(code) FROM lkp WHERE seg IN ('C', 'D'))",
        "DELETE FROM acct WHERE EXISTS (SELECT 1 FROM lkp WHERE code = acc_no "
        "AND seg IN ('C', 'D') HAVING COUNT(*) < 2)",
    ]

    def test_widening_forms_refused_and_widen_on_sqlite(self):
        for sql, original in self.WIDENING_ON_SQLITE:
            for remove in (self.ALL, self.PARTIAL):
                with self.subTest(sql=sql, remove=sorted(remove)):
                    self.assertEqual(touched(self, sql), original)
                    index, _lists = seg_list(sql)
                    with self.assertRaises(ValueError) as ctx:
                        reset(sql, {index: remove})
                    self.assertIn("Cannot reset", str(ctx.exception))
            with self.subTest(sql=sql, check="unchecked rewrite widens"):
                self.assertGreater(touched(self, unchecked_reset(sql, self.ALL)), original)

    def test_other_dialect_forms_refused(self):
        for sql in self.REFUSED_OTHER:
            for remove in (self.ALL, self.PARTIAL):
                with self.subTest(sql=sql, remove=sorted(remove)):
                    index, _lists = seg_list(sql)
                    with self.assertRaises(ValueError):
                        reset(sql, {index: remove})

    def test_error_names_the_real_reason(self):
        cases = [
            ("DELETE FROM acct WHERE x NOT IN (SELECT x FROM lkp WHERE seg IN ('C'))",
             "NOT IN (subquery)"),
            ("DELETE FROM acct WHERE NOT x IN (SELECT x FROM lkp WHERE seg IN ('C'))",
             "NOT column IN (subquery)"),
            ("DELETE FROM acct WHERE NOT EXISTS (SELECT 1 FROM lkp WHERE seg IN ('C'))",
             "NOT EXISTS"),
            ("DELETE FROM acct WHERE x <> ALL (SELECT x FROM lkp WHERE seg IN ('C'))",
             "ALL"),
            ("DELETE FROM acct WHERE x IN (SELECT x FROM acct MINUS "
             "SELECT x FROM lkp WHERE seg IN ('C'))", "MINUS"),
            ("DELETE FROM acct WHERE x IN (SELECT a.x FROM acct a LEFT JOIN lkp b "
             "ON b.k = a.k AND b.seg IN ('C') WHERE b.k IS NULL)", "outer"),
        ]
        for sql, reason in cases:
            with self.subTest(sql=sql):
                index, _lists = seg_list(sql)
                with self.assertRaises(ValueError) as ctx:
                    reset(sql, {index: {"'C'"}})
                message = str(ctx.exception)
                self.assertTrue(message.startswith("Cannot reset seg IN (...)")
                                or message.startswith("Cannot reset b.seg IN (...)"), message)
                self.assertIn(reason, message)
                self.assertNotIn("seg NOT IN", message)

    def test_positive_nested_forms_still_reset_and_never_widen(self):
        cases = [
            "DELETE FROM acct WHERE acc_no IN (SELECT code FROM lkp WHERE seg IN ('C', 'D'))",
            "DELETE FROM acct WHERE acct.acc_no IN "
            "(SELECT lkp.code FROM lkp WHERE lkp.code > '0' AND lkp.seg IN ('C', 'D'))",
            "DELETE FROM acct WHERE EXISTS "
            "(SELECT 1 FROM lkp WHERE lkp.code = acct.acc_no AND lkp.seg IN ('C', 'D'))",
            "DELETE FROM acct WHERE acc_no IN (SELECT a.acc_no FROM acct a INNER JOIN lkp b "
            "ON b.code = a.acc_no AND b.seg IN ('C', 'D'))",
            "DELETE FROM acct WHERE acc_no IN (SELECT a.acc_no FROM acct a JOIN lkp b "
            "ON b.code = a.acc_no AND b.seg IN ('C', 'D'))",
            "DELETE FROM acct WHERE flag = 'N' AND (status = 'Z' OR acc_no IN "
            "(SELECT DISTINCT code FROM lkp WHERE (seg IN ('C', 'D'))))",
            "DELETE FROM acct WHERE acc_no IN (SELECT code FROM lkp WHERE seg IN ('C', 'D') "
            "UNION SELECT code FROM lkp WHERE code = '0000')",
            "UPDATE acct SET flag = 'Y' WHERE acc_no IN "
            "(SELECT code FROM lkp WHERE seg IN ('C', 'D'))",
        ]
        for sql in cases:
            for remove in (self.ALL, self.PARTIAL):
                with self.subTest(sql=sql, remove=sorted(remove)):
                    index, _lists = seg_list(sql)
                    out = reset(sql, {index: remove})
                    self.assertEqual(out, unchecked_reset(sql, remove))
                    if remove == self.ALL:
                        self.assertIn("1=0", out)
                        self.assertEqual(touched(self, out), 0)
                    self.assertLessEqual(touched(self, out), touched(self, sql))

    def test_top_level_behaviour_unchanged(self):
        self.assertEqual(
            norm(reset_all_values("DELETE FROM acct WHERE (status = 'A' OR acc_no IN ('1001'))",
                                  0)),
            "DELETE FROM acct WHERE (status = 'A' OR 1=0)")
        self.assertEqual(
            norm(reset("DELETE FROM acct WHERE acc_no NOT IN ('1001', '1002')",
                       {0: {"'1001'"}})),
            "DELETE FROM acct WHERE acc_no NOT IN ('1002')")
        with self.assertRaises(ValueError) as ctx:
            reset_all_values("DELETE FROM acct WHERE acc_no NOT IN ('1001')")
        self.assertIn("acc_no NOT IN (...)", str(ctx.exception))
        with self.assertRaises(ValueError) as ctx:
            reset_all_values("DELETE FROM acct WHERE NOT acc_no IN ('1001')")
        self.assertIn("NOT acc_no IN (...)", str(ctx.exception))


class TrackedModeResetTests(unittest.TestCase):
    """Bug 3: Auto WHERE column emptied by Reset in UPDATE / DELETE -> 1=0."""

    KEY = "WHERE acc_no"

    def _stub(self, template, sql_values="'1001'", extra=None):
        stub = GUI.__new__(GUI)
        stub.sql_template = template
        stub._excel_parameter_values = {self.KEY: (GUI.AUTO_WHERE_PARAMETER, sql_values)}
        stub._excel_parameter_values.update(extra or {})
        stub._excel_parameterized_sql = None
        stub.root = mock.Mock()
        stub.sql_context = _Text(stub._render_sql_template())
        return stub

    def _reset(self, stub):
        with mock.patch.object(app, "messagebox") as mb:
            stub.reset_single_parameter(self.KEY)
        mb.showerror.assert_not_called()
        return stub.sql_context.content

    def test_delete_with_where_affects_no_rows(self):
        stub = self._stub("DELETE FROM acct WHERE status='A'")
        out = self._reset(stub)
        self.assertEqual(norm(out), "DELETE FROM acct WHERE (status='A') AND 1=0")
        self.assertEqual(stub._excel_parameter_values[self.KEY], (GUI.AUTO_WHERE_PARAMETER, ""))
        self.assertEqual(stub._excel_parameterized_sql, out)
        con = acct_db(self)
        self.assertEqual(con.execute(out).rowcount, 0)
        self.assertEqual(con.execute("SELECT COUNT(*) FROM acct").fetchone()[0], 3)

    def test_delete_without_where_affects_no_rows(self):
        out = self._reset(self._stub("DELETE FROM acct"))
        self.assertEqual(norm(out), "DELETE FROM acct WHERE 1=0")
        con = acct_db(self)
        self.assertEqual(con.execute(out).rowcount, 0)
        self.assertEqual(con.execute("SELECT COUNT(*) FROM acct").fetchone()[0], 3)

    def test_update_with_and_without_where_affects_no_rows(self):
        for template, expected in (
            ("UPDATE acct SET flag='Y' WHERE status='A'",
             "UPDATE acct SET flag='Y' WHERE (status='A') AND 1=0"),
            ("UPDATE acct SET flag='Y'", "UPDATE acct SET flag='Y' WHERE 1=0"),
            ("UPDATE acct SET flag='Y';", "UPDATE acct SET flag='Y' WHERE 1=0;"),
        ):
            with self.subTest(template=template):
                out = self._reset(self._stub(template))
                self.assertEqual(norm(out), expected)
                con = acct_db(self)
                self.assertEqual(con.execute(out.rstrip(";")).rowcount, 0)
                self.assertEqual(
                    con.execute("SELECT COUNT(*) FROM acct WHERE flag='Y'").fetchone()[0], 0)

    def test_other_auto_where_column_kept(self):
        stub = self._stub("DELETE FROM acct", extra={
            "WHERE status": (GUI.AUTO_WHERE_PARAMETER, "'A'")})
        out = self._reset(stub)
        self.assertEqual(norm(out), "DELETE FROM acct WHERE 1=0 AND status IN ('A')")
        self.assertEqual(acct_db(self).execute(out).rowcount, 0)

    def test_select_drops_condition_as_before(self):
        stub = self._stub("SELECT * FROM acct WHERE status='A'")
        out = self._reset(stub)
        self.assertEqual(out, "SELECT * FROM acct WHERE status='A'")
        self.assertNotIn(self.KEY, stub._excel_parameter_values)
        self.assertIsNone(stub._excel_parameterized_sql)

    def test_reset_parameter_value(self):
        auto = GUI.AUTO_WHERE_PARAMETER
        self.assertEqual(GUI._reset_parameter_value("DELETE FROM t", auto, ["'1'", "'2'"]),
                         (auto, "'1', '2'"))
        self.assertEqual(GUI._reset_parameter_value("DELETE FROM t", auto, []), (auto, ""))
        self.assertEqual(GUI._reset_parameter_value("WITH c AS (SELECT 1 FROM u) "
                                                    "UPDATE t SET a = 1", auto, []), (auto, ""))
        self.assertIsNone(GUI._reset_parameter_value("SELECT * FROM t", auto, []))
        self.assertIsNone(GUI._reset_parameter_value("DELETE FROM t", ":ACC", []))
        self.assertIsNone(GUI._reset_parameter_value("DELETE FROM t", GUI.IN_COLUMN_PARAMETER, []))

    def test_normal_render_unchanged(self):
        stub = self._stub("DELETE FROM acct WHERE status='A'", sql_values="'1001', '1003'")
        out = stub._render_sql_template()
        self.assertEqual(norm(out), "DELETE FROM acct WHERE (status='A') AND acc_no IN ('1001', '1003')")
        self.assertEqual(acct_db(self).execute(out).rowcount, 2)

    def test_dialog_build_reset_values_keeps_empty_auto_where(self):
        tree = ast.parse(textwrap.dedent(inspect.getsource(GUI.show_reset_parameter_dialog)))
        func = next(n for n in ast.walk(tree)
                    if isinstance(n, ast.FunctionDef) and n.name == "build_reset_values")
        factory = ast.parse("def _factory(self, column_selected, column_tokens):\n"
                            "    return build_reset_values\n")
        factory.body[0].body.insert(0, func)
        ast.fix_missing_locations(factory)
        ns: dict = {}
        exec(compile(factory, "<build_reset_values>", "exec"), vars(app).copy(), ns)
        for template, expected in (("DELETE FROM acct WHERE status='A'", ""), ("SELECT * FROM acct", None)):
            with self.subTest(template=template):
                stub = self._stub(template)
                build = ns["_factory"](stub, {self.KEY: {"'1001'"}}, {self.KEY: ["'1001'"]})
                values = build()
                if expected is None:
                    self.assertEqual(values, {})
                else:
                    self.assertEqual(values, {self.KEY: (GUI.AUTO_WHERE_PARAMETER, expected)})
                    out = stub._render_sql_template(values)
                    self.assertEqual(acct_db(self).execute(out).rowcount, 0)


def _compile_dialog_functions(env):
    """build_detected_sql / refresh_sql_preview / reset_selected from the real dialog."""
    tree = ast.parse(textwrap.dedent(inspect.getsource(GUI.show_reset_parameter_dialog)))
    wanted = ("build_detected_sql", "refresh_sql_preview", "reset_selected")
    funcs = {n.name: n for n in ast.walk(tree)
             if isinstance(n, ast.FunctionDef) and n.name in wanted}
    assert set(funcs) == set(wanted), funcs.keys()
    names = sorted(env)
    factory = ast.parse(
        f"def _factory({', '.join(names)}):\n    return build_detected_sql, refresh_sql_preview, reset_selected\n"
    )
    for name in reversed(wanted):
        factory.body[0].body.insert(0, funcs[name])
    ast.fix_missing_locations(factory)
    ns: dict = {}
    exec(compile(factory, "<reset_dialog>", "exec"), vars(app).copy(), ns)
    return ns["_factory"](**{n: env[n] for n in names})


class _Text:
    def __init__(self, content=""):
        self.content = content
        self.calls = []

    def get(self, *_a):
        return self.content

    def delete(self, *_a):
        self.calls.append("delete")
        self.content = ""

    def insert(self, _i, value):
        self.calls.append("insert")
        self.content += value

    def config(self, **_k):
        pass


class DialogTests(unittest.TestCase):
    """R2-T4 / R2-AC-22 (logic)."""

    def _env(self, sql, chosen_tokens):
        stub = GUI.__new__(GUI)
        stub.sql_context = _Text(sql)
        stub._excel_parameter_values = {}
        detected = GUI._detect_sql_in_lists(sql)
        column_selected = {"0": set(chosen_tokens)}
        env = {
            "self": stub,
            "source_sql": sql,
            "detected": detected,
            "detected_mode": True,
            "column_selected": column_selected,
            "column_tokens": {"0": detected[0]["tokens"]},
            "selected_of": lambda key: column_selected.get(key, set()),
            "sql_preview": _Text(),
            "dialog": mock.Mock(name="dialog"),
            "render_sql": mock.Mock(name="render_sql"),
            "build_reset_values": mock.Mock(name="build_reset_values"),
            "write_sql": mock.Mock(name="write_sql"),
            "close_after_selected": False,
        }
        return stub, env

    def test_empty_in_preview_equals_applied_sql(self):
        sql = "DELETE FROM acct WHERE acc_no IN ('1001')"
        stub, env = self._env(sql, {"'1001'"})
        with mock.patch.object(app, "messagebox") as mb:
            # compile inside the patch: the functions see module globals at compile time
            _build, refresh, apply = _compile_dialog_functions(env)
            refresh()
            preview = env["sql_preview"].content
            apply()
        mb.showerror.assert_not_called()
        self.assertEqual(norm(preview), "DELETE FROM acct WHERE 1=0")
        self.assertEqual(stub.sql_context.content, preview)
        env["dialog"].destroy.assert_called_once_with()
        self.assertIn("WHERE", stub.sql_context.content)

    def test_not_in_rejected_in_preview_and_apply(self):
        sql = "DELETE FROM acct WHERE acc_no NOT IN ('1001')"
        stub, env = self._env(sql, {"'1001'"})
        with mock.patch.object(app, "messagebox") as mb:
            # compile inside the patch: the functions see module globals at compile time
            _build, refresh, apply = _compile_dialog_functions(env)
            refresh()
            preview = env["sql_preview"].content
            apply()
        self.assertTrue(preview.startswith(sql + "\n\n-- "))
        self.assertIn("every row", preview)
        mb.showerror.assert_called_once()
        self.assertEqual(mb.showerror.call_args.args[0], "Reset Error")
        self.assertIs(mb.showerror.call_args.kwargs.get("parent"), env["dialog"])
        self.assertEqual(stub.sql_context.content, sql)  # Editor unchanged
        self.assertEqual(stub.sql_context.calls, [])
        env["dialog"].destroy.assert_not_called()

    def test_apply_computes_sql_once(self):
        sql = "SELECT * FROM acct WHERE acc_no IN ('1001','1002')"
        stub, env = self._env(sql, {"'1002'"})
        with mock.patch.object(GUI, "_reset_sql_in_lists",
                               side_effect=GUI._reset_sql_in_lists) as rs:
            with mock.patch.object(app, "messagebox"):
                _b, _r, apply = _compile_dialog_functions(env)
                apply()
        self.assertEqual(rs.call_count, 1)
        self.assertEqual(stub.sql_context.content, "SELECT * FROM acct WHERE acc_no IN ('1001')")


if __name__ == "__main__":
    unittest.main()
