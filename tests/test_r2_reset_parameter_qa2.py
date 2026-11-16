"""QA round 2 for R2-T-fix (M9), Bug 5: token-based _detect_sql_in_lists.

Checks the detection changes flagged by the developer (no-space forms, [x] / `x`
identifiers, UPPER(x) NOT IN, comments inside values and inside dotted columns),
comment / string skipping, real-looking OFSAA SQL, and the core invariant on
SQLite: a detected-mode reset never touches more rows than the original SQL
(a refusal (ValueError) or a SQL error is a safe outcome).

No Tk window, no real database (SQLite :memory:).
"""

import itertools
import os
import re
import sqlite3
import sys
import unittest
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import database_connect_gui as app  # noqa: E402

GUI = app.DatabaseConnectorGUI

ACCT_ROWS = [
    ("1001", "A", "N", 1, "G1"),
    ("1002", "B", "N", 2, "G2"),
    ("1003", "A", "Z", -1, "G1"),
    ("1004", "C", "N", 0, "G3"),
]
LKP_ROWS = [("G1", "RETAIL"), ("G2", "CORP"), ("G3", "RETAIL")]


def norm(sql: str) -> str:
    return re.sub(r"\s+", " ", sql).strip()


def make_db(test: unittest.TestCase) -> sqlite3.Connection:
    con = sqlite3.connect(":memory:")
    test.addCleanup(con.close)
    con.execute("CREATE TABLE acct (acc_no TEXT, status TEXT, flag TEXT, n INTEGER, grp TEXT)")
    con.execute("CREATE TABLE lkp (code TEXT, seg TEXT)")
    con.executemany("INSERT INTO acct VALUES (?, ?, ?, ?, ?)", ACCT_ROWS)
    con.executemany("INSERT INTO lkp VALUES (?, ?)", LKP_ROWS)
    con.commit()
    return con


def affected(test: unittest.TestCase, sql: str) -> Optional[int]:
    """Rows touched by sql on fresh tables, or None when SQLite rejects it."""
    con = make_db(test)
    sql = sql.rstrip().rstrip(";")
    try:
        if re.match(r"\s*(--[^\n]*\n\s*)*SELECT\b", sql, flags=re.IGNORECASE):
            return len(con.execute(sql).fetchall())
        return con.execute(sql).rowcount
    except sqlite3.Error:
        return None



def columns(sql: str) -> list:
    return [item["column"] for item in GUI._detect_sql_in_lists(sql)]


class InvariantMixin:
    def assert_never_widens(self, sql: str) -> int:
        """Try every detected list with: all tokens, and each single token.

        Returns how many rewrites were actually executed.
        """
        before = affected(self, sql)
        self.assertIsNotNone(before, f"original SQL must run: {sql!r}")
        lists = GUI._detect_sql_in_lists(sql)
        executed = 0
        for index, item in enumerate(lists):
            choices = [set(item["tokens"])] + [{t} for t in item["tokens"]]
            for chosen in choices:
                try:
                    out = GUI._reset_sql_in_lists(sql, lists, {index: chosen})
                except ValueError:
                    continue  # refused: safe
                after = affected(self, out)
                if after is None:
                    continue  # SQL error: nothing touched
                executed += 1
                self.assertLessEqual(
                    after, before,
                    f"\nlist {item['column']!r} drop {sorted(chosen)!r}\n"
                    f"  {sql!r}\n-> {out!r}\n  touches {after} rows, original {before}")
        return executed


# ======================================================================
# Detection changes flagged by the developer
# ======================================================================
class FlaggedDetectionTests(InvariantMixin, unittest.TestCase):
    # 1. no-space forms
    def test_no_space_forms_detected(self):
        for sql, column in (
            ("DELETE FROM acct WHERE \"acc_no\"IN ('1001')", '"acc_no"'),
            ("DELETE FROM acct WHERE acct.acc_no IN('1001')", "acct.acc_no"),
            ("DELETE FROM acct WHERE acc_no IN('1001','1002')", "acc_no"),
            ("DELETE FROM acct WHERE acct.\"acc_no\"IN('1001')", 'acct."acc_no"'),
        ):
            with self.subTest(sql=sql):
                lists = GUI._detect_sql_in_lists(sql)
                self.assertEqual([i["column"] for i in lists], [column])
                start, end = lists[0]["span"]
                self.assertTrue(sql[start:end].startswith(column))
                self.assertTrue(sql[start:end].endswith(")"))
                self.assert_never_widens(sql)

    def test_no_space_form_resets_to_1_eq_0(self):
        sql = "DELETE FROM acct WHERE \"acc_no\"IN ('1001')"
        lists = GUI._detect_sql_in_lists(sql)
        out = GUI._reset_sql_in_lists(sql, lists, {0: set(lists[0]["tokens"])})
        self.assertEqual(out, "DELETE FROM acct WHERE 1=0")

    # 2. [col] and `col`
    def test_bracket_and_backtick_identifiers(self):
        for sql, column in (
            ("DELETE FROM acct WHERE [acc_no] IN ('1001')", "[acc_no]"),
            ("DELETE FROM acct WHERE `acc_no` IN ('1001')", "`acc_no`"),
            ("DELETE FROM acct WHERE [acct].[acc_no] IN ('1001')", "[acct].[acc_no]"),
        ):
            with self.subTest(sql=sql):
                lists = GUI._detect_sql_in_lists(sql)
                self.assertEqual([i["column"] for i in lists], [column])
                self.assertEqual(lists[0]["tokens"], ["'1001'"])
                out = GUI._reset_sql_in_lists(sql, lists, {0: {"'1001'"}})
                self.assertEqual(out, "DELETE FROM acct WHERE 1=0")
                self.assertEqual(affected(self, out), 0)

    # 3. function call before [NOT] IN: skipped, never NOT as the column
    def test_function_call_lists_are_skipped(self):
        for sql in (
            "DELETE FROM acct WHERE UPPER(acc_no) NOT IN ('1001')",
            "DELETE FROM acct WHERE UPPER(acc_no) IN ('1001')",
            "DELETE FROM acct WHERE TRIM(acct.status) NOT IN ('A', 'B')",
        ):
            with self.subTest(sql=sql):
                self.assertEqual(GUI._detect_sql_in_lists(sql), [])

    def test_not_is_never_the_column(self):
        sqls = [
            "DELETE FROM acct WHERE UPPER(acc_no) NOT IN ('1001') AND flag IN ('N')",
            "DELETE FROM acct WHERE acc_no NOT IN ('1001')",
            "DELETE FROM acct WHERE NOT acc_no IN ('1001')",
            "DELETE FROM acct WHERE acc_no NOT\n IN ('1001')",
        ]
        for sql in sqls:
            with self.subTest(sql=sql):
                cols = [c.upper() for c in columns(sql)]
                self.assertNotIn("NOT", cols)
        self.assertEqual(columns(sqls[0]), ["flag"])

    def test_function_call_not_in_other_lists_still_safe(self):
        sql = "DELETE FROM acct WHERE UPPER(status) NOT IN ('C') AND acc_no IN ('1001', '1002')"
        self.assertEqual(columns(sql), ["acc_no"])
        self.assertGreater(self.assert_never_widens(sql), 0)

    # 4. comment with a quote inside the values
    def test_comment_with_quote_in_values(self):
        sql = "DELETE FROM acct WHERE acc_no IN ('1001', /* ' */ '1002')"
        lists = GUI._detect_sql_in_lists(sql)
        self.assertEqual(len(lists), 1)
        self.assertEqual(lists[0]["tokens"][0], "'1001'")
        self.assertEqual(len(lists[0]["tokens"]), 2)
        self.assertGreater(self.assert_never_widens(sql), 0)

    def test_comment_with_quotes_variants_never_widen(self):
        for sql in (
            "DELETE FROM acct WHERE acc_no IN ('1001', /* it's */ '1002', '1003')",
            "DELETE FROM acct WHERE acc_no IN ('1001', -- it's\n '1002')",
            "DELETE FROM acct WHERE acc_no IN ('1001', /* 'x', 'y' */ '1002')",
            "DELETE FROM acct WHERE acc_no IN ('1001', -- '1004',\n '1002')",
            "DELETE FROM acct WHERE acc_no IN ('1001', '1002' -- old\n, '1003')",
        ):
            with self.subTest(sql=sql):
                self.assert_never_widens(sql)

    # 5. comment inside a dotted column
    def test_comment_inside_dotted_column(self):
        for sql in (
            "DELETE FROM acct WHERE acct /*c*/ . acc_no IN ('1001')",
            "DELETE FROM acct WHERE acct. /*c*/acc_no IN ('1001')",
            "DELETE FROM acct WHERE acct -- c\n.acc_no IN ('1001')",
        ):
            with self.subTest(sql=sql):
                lists = GUI._detect_sql_in_lists(sql)
                self.assertEqual([i["column"] for i in lists], ["acct.acc_no"])
                out = GUI._reset_sql_in_lists(sql, lists, {0: {"'1001'"}})
                self.assertEqual(out, "DELETE FROM acct WHERE 1=0")  # whole predicate replaced
                self.assertEqual(affected(self, out), 0)


# ======================================================================
# Comments and string literals are never detected
# ======================================================================
class CommentStringSkipTests(unittest.TestCase):
    def test_in_inside_comment_or_string_not_detected(self):
        sql = ("SELECT * FROM acct WHERE status = 'x IN (1)' -- flag IN ('N')\n"
               " AND /* grp IN ('G1') */ acc_no IN ('1001') AND n <> 'n IN (2)'")
        self.assertEqual(columns(sql), ["acc_no"])

    def test_list_ending_in_comment_or_string_paren(self):
        sql = "SELECT * FROM acct WHERE acc_no IN ('1001', ')', '1002' /* ) */)"
        lists = GUI._detect_sql_in_lists(sql)
        self.assertEqual(len(lists), 1)
        self.assertEqual(lists[0]["tokens"][:2], ["'1001'", "')'"])
        self.assertTrue(sql[lists[0]["span"][0]:lists[0]["span"][1]].endswith("*/)"))

    def test_nested_unclosed_select_skipped(self):
        for sql in (
            "SELECT * FROM acct WHERE acc_no IN ((1001))",
            "SELECT * FROM acct WHERE acc_no IN ('1001'",
            "SELECT * FROM acct WHERE acc_no IN ()",
            "SELECT * FROM acct WHERE acc_no IN (SELECT acc_no FROM acct)",
            "SELECT * FROM acct WHERE acc_no IN (\n  select acc_no from acct)",
            "SELECT * FROM acct WHERE acc_no IN (TRIM('1001'))",
            "",
            None,
        ):
            with self.subTest(sql=sql):
                self.assertEqual(GUI._detect_sql_in_lists(sql), [])

    def test_return_format(self):
        sql = "SELECT * FROM acct a WHERE a.acc_no IN ('1001', '1001', '1002')"
        (item,) = GUI._detect_sql_in_lists(sql)
        self.assertEqual(set(item), {"column", "span", "vals_span", "tokens"})
        self.assertEqual(item["column"], "a.acc_no")
        self.assertEqual(item["tokens"], ["'1001'", "'1002'"])  # de-duplicated, order kept
        self.assertEqual(sql[item["span"][0]:item["span"][1]], "a.acc_no IN ('1001', '1001', '1002')")
        self.assertEqual(sql[item["vals_span"][0]:item["vals_span"][1]], "'1001', '1001', '1002'")


# ======================================================================
# Real-looking OFSAA SQL
# ======================================================================
OFSAA_SQLS = [
    # multi-line, aliases, several lists
    """SELECT a.acc_no, a.status, l.seg
FROM acct a
JOIN lkp l ON l.code = a.grp
WHERE a.status IN ('A', 'B')
  AND l.seg IN ('RETAIL',
                'CORP')
  AND a.flag NOT IN ('Z')
ORDER BY a.acc_no""",
    # UPDATE with IN inside a subquery
    """UPDATE acct
   SET flag = 'Y'
 WHERE grp IN (SELECT code FROM lkp WHERE seg IN ('RETAIL'))
   AND acc_no IN ('1001', '1003', '1004')""",
    # DELETE with EXISTS subquery and comments
    """-- cleanup of test accounts
DELETE FROM acct
 WHERE acct.acc_no IN ('1001', '1002', '1004')  /* ticket 42 */
   AND EXISTS (SELECT 1 FROM lkp l
                WHERE l.code = acct.grp
                  AND l.seg IN ('RETAIL', 'CORP'))""",
    # NOT EXISTS with an inner list, outer plain list
    """DELETE FROM acct
 WHERE status IN ('A', 'C')
   AND NOT EXISTS (SELECT 1 FROM lkp WHERE lkp.code = acct.grp AND lkp.seg IN ('CORP'))""",
    # OR groups
    """DELETE FROM acct
 WHERE (status IN ('A') AND flag IN ('N'))
    OR (status IN ('C') AND n IN (0, 5))""",
]


class OfsaaSqlTests(InvariantMixin, unittest.TestCase):
    def test_detection_columns(self):
        expected = [
            ["a.status", "l.seg", "a.flag"],
            ["seg", "acc_no"],
            ["acct.acc_no", "l.seg"],
            ["status", "lkp.seg"],
            ["status", "flag", "status", "n"],
        ]
        for sql, cols in zip(OFSAA_SQLS, expected):
            with self.subTest(sql=sql[:40]):
                self.assertEqual(columns(sql), cols)

    def test_multiline_tokens(self):
        lists = GUI._detect_sql_in_lists(OFSAA_SQLS[0])
        self.assertEqual(lists[1]["tokens"], ["'RETAIL'", "'CORP'"])

    def test_invariant_every_list_every_choice(self):
        for sql in OFSAA_SQLS:
            with self.subTest(sql=sql[:40]):
                self.assertGreater(self.assert_never_widens(sql), 0)

    def test_invariant_pairs_of_lists_emptied(self):
        for sql in OFSAA_SQLS:
            lists = GUI._detect_sql_in_lists(sql)
            before = affected(self, sql)
            for a, b in itertools.combinations(range(len(lists)), 2):
                selected = {a: set(lists[a]["tokens"]), b: set(lists[b]["tokens"])}
                with self.subTest(sql=sql[:40], lists=(a, b)):
                    try:
                        out = GUI._reset_sql_in_lists(sql, lists, selected)
                    except ValueError:
                        continue
                    after = affected(self, out)
                    if after is not None:
                        self.assertLessEqual(after, before, out)


# ======================================================================
# Core invariant: cases that currently widen (BUGS, see report)
# ======================================================================
class WideningBugTests(InvariantMixin, unittest.TestCase):
    def test_operator_before_column_never_widens(self):
        """`1 - n IN (5)`: the column is taken as `n` and `n IN (5)` becomes
        `1=0`, giving `1 - 1=0` -> `0=0` -> every row."""
        for sql in (
            "DELETE FROM acct WHERE 1 - n IN (5)",
            "DELETE FROM acct WHERE 0 * n IN (5)",
            "DELETE FROM acct WHERE status || acc_no IN ('A1001')",
        ):
            with self.subTest(sql=sql):
                self.assert_never_widens(sql)

    def test_comment_before_subquery_select_never_widens(self):
        """`IN (-- note<newline> SELECT ...)` is not skipped as a subquery; its
        ORDER BY comma splits it into "values" and dropping one widens."""
        sql = ("DELETE FROM acct WHERE acc_no IN (-- scope\n"
               " SELECT acc_no FROM acct WHERE status = 'B' ORDER BY flag, acc_no)")
        self.assert_never_widens(sql)

    def test_comment_with_comma_in_values_never_widens(self):
        """A comma inside a comment splits the comment into value tokens;
        dropping a fragment un-comments the rest of it."""
        sql = ("DELETE FROM acct WHERE acc_no IN ('1001', -- x, 1) OR (1=1 OR acc_no = --\n"
               " '1003')")
        self.assert_never_widens(sql)


if __name__ == "__main__":
    unittest.main()
