"""QA round 3 for R2-T-fix (M9): Bugs 6 / 7 / 8 retest of _detect_sql_in_lists.

- Realistic OFSAA / Oracle forms are still detected (no usability regression).
- Values are split on _scan_sql comma tokens (comments per line, negatives,
  DATE / TIMESTAMP literals) and the rewrite stays valid.
- Safety invariant on SQLite: a detected-mode reset never touches more rows
  than the original SQL (a refusal or a SQL error counts as safe).
- Known limits (exotic, not failures) are pinned so a change is noticed.

No Tk window, no real database (SQLite :memory:).
"""

import itertools
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_r2_reset_parameter_qa2 import GUI, InvariantMixin, affected  # noqa: E402


def detect(sql: str) -> list:
    return [(item["column"], item["tokens"]) for item in GUI._detect_sql_in_lists(sql)]


def drop(sql: str, index: int, tokens: set) -> str:
    lists = GUI._detect_sql_in_lists(sql)
    return GUI._reset_sql_in_lists(sql, lists, {index: tokens})


# ======================================================================
# 1. Realistic forms are still detected
# ======================================================================
class RealisticDetectionTests(InvariantMixin, unittest.TestCase):
    def test_common_oracle_forms_detected(self):
        cases = [
            ("SELECT * FROM t WHERE t.col IN ('a', 'b')", [("t.col", ["'a'", "'b'"])]),
            ("SELECT * FROM t WHERE x = 1 AND t.\"COL\" IN ('a')", [('t."COL"', ["'a'"])]),
            ("SELECT * FROM t WHERE x = 1 OR col IN (1, 2)", [("col", ["1", "2"])]),
            ("SELECT * FROM a JOIN b ON a.x = b.x AND b.y IN ('A', 'B')",
             [("b.y", ["'A'", "'B'"])]),
            ("SELECT * FROM a JOIN b ON b.y IN ('A')", [("b.y", ["'A'"])]),
            ("SELECT CASE WHEN col IN ('A', 'B') THEN 1 ELSE 0 END FROM t",
             [("col", ["'A'", "'B'"])]),
            ("SELECT * FROM t WHERE col NOT IN ('a')", [("col", ["'a'"])]),
            ("SELECT * FROM t WHERE NOT col IN ('a')", [("col", ["'a'"])]),
            ("SELECT * FROM t WHERE (col IN ('a') OR x IN ('b'))",
             [("col", ["'a'"]), ("x", ["'b'"])]),
            ("SELECT grp FROM t GROUP BY grp HAVING grp IN ('G1')", [("grp", ["'G1'"])]),
            ("select * from t where col in ('a') and status in ('X')",
             [("col", ["'a'"]), ("status", ["'X'"])]),
            ("SELECT * FROM t WHERE sch.tbl.col IN ('a')", [("sch.tbl.col", ["'a'"])]),
            ("SELECT * FROM t t1 WHERE t1.v_branch_code IN ('001','002') AND t1.n_amt > 0",
             [("t1.v_branch_code", ["'001'", "'002'"])]),
            ("SELECT * FROM t WHERE x = 1 AND\n  -- note\n  col IN ('a')", [("col", ["'a'"])]),
            ("SELECT * FROM t WHERE x = 1 AND /* c */ col IN ('a')", [("col", ["'a'"])]),
            ("MERGE INTO t USING s ON (t.id = s.id AND s.c IN ('a')) "
             "WHEN MATCHED THEN UPDATE SET t.v = s.v", [("s.c", ["'a'"])]),
            ("UPDATE t SET a = 1 WHERE col IN ('a')", [("col", ["'a'"])]),
            ("DELETE FROM t WHERE col IN ('a'); DELETE FROM u WHERE col IN ('b')",
             [("col", ["'a'"]), ("col", ["'b'"])]),
            ("SELECT * FROM t WHERE col IN ('a') AND c2 IN (SELECT x FROM y)",
             [("col", ["'a'"])]),
            ("SELECT * FROM t WHERE col IN (:a, :b)", [("col", [":a", ":b"])]),
            ("SELECT * FROM t WHERE col IN ( 'a' , 'b' )", [("col", ["'a'", "'b'"])]),
            ("SELECT * FROM t WHERE col IN ('a', 'a')", [("col", ["'a'"])]),
            ("SELECT * FROM t WHERE LEVEL IN (1, 2)", [("LEVEL", ["1", "2"])]),
            ("SELECT * FROM t WHERE col IN ('a')\n/", [("col", ["'a'"])]),
        ]
        for sql, expected in cases:
            with self.subTest(sql=sql):
                self.assertEqual(detect(sql), expected)

    def test_multiline_one_value_per_line(self):
        sql = "SELECT * FROM acct\nWHERE acc_no IN (\n  '1001',\n  '1002',\n  '1003'\n)"
        self.assertEqual(detect(sql), [("acc_no", ["'1001'", "'1002'", "'1003'"])])
        self.assertEqual(drop(sql, 0, {"'1002'"}),
                         "SELECT * FROM acct\nWHERE acc_no IN ('1001', '1003')")
        self.assertGreater(self.assert_never_widens(sql), 0)

    def test_trailing_comment_per_line(self):
        sql = ("SELECT * FROM acct\nWHERE acc_no IN (\n"
               "  '1001', -- branch A, main\n"
               "  '1002', -- branch B\n"
               "  '1003'  -- branch C\n)")
        self.assertEqual(detect(sql), [("acc_no", ["'1001'", "'1002'", "'1003'"])])
        out = drop(sql, 0, {"'1002'"})
        self.assertEqual(out, "SELECT * FROM acct\nWHERE acc_no IN ('1001', '1003')")
        self.assertEqual(affected(self, out), 2)
        self.assertEqual(drop(sql, 0, {"'1001'", "'1002'", "'1003'"}),
                         "SELECT * FROM acct\nWHERE 1=0")
        self.assertGreater(self.assert_never_widens(sql), 0)

    def test_comment_before_comma_and_block_comments(self):
        cases = [
            "DELETE FROM acct WHERE acc_no IN ('1001' -- a, b\n, '1002')",
            "DELETE FROM acct WHERE acc_no IN ('1001' /* x, y */, '1002')",
            "DELETE FROM acct WHERE acc_no IN ('1001', /* x, y */ '1002')",
        ]
        for sql in cases:
            with self.subTest(sql=sql):
                self.assertEqual(detect(sql), [("acc_no", ["'1001'", "'1002'"])])
                self.assertEqual(drop(sql, 0, {"'1001'"}),
                                 "DELETE FROM acct WHERE acc_no IN ('1002')")
                self.assertGreater(self.assert_never_widens(sql), 0)

    def test_negative_numbers(self):
        sql = "DELETE FROM acct WHERE n IN (-1, 0, +2)"
        self.assertEqual(detect(sql), [("n", ["-1", "0", "+2"])])
        self.assertEqual(drop(sql, 0, {"0"}), "DELETE FROM acct WHERE n IN (-1, +2)")
        self.assertEqual(affected(self, drop(sql, 0, {"0"})), 2)  # n = -1 and n = 2
        self.assertGreater(self.assert_never_widens(sql), 0)

    def test_date_and_timestamp_literals(self):
        sql = ("SELECT * FROM t WHERE fic_mis_date IN (DATE '2024-01-01', "
               "DATE '2024-02-01', TIMESTAMP '2024-03-01 00:00:00')")
        self.assertEqual(detect(sql), [("fic_mis_date", [
            "DATE '2024-01-01'", "DATE '2024-02-01'", "TIMESTAMP '2024-03-01 00:00:00'"])])
        self.assertEqual(
            drop(sql, 0, {"DATE '2024-02-01'"}),
            "SELECT * FROM t WHERE fic_mis_date IN (DATE '2024-01-01', "
            "TIMESTAMP '2024-03-01 00:00:00')")

    def test_expression_values_kept_whole(self):
        sql = "SELECT * FROM t WHERE col IN ('a' || 'b', 'c', 1 - 2)"
        self.assertEqual(detect(sql), [("col", ["'a' || 'b'", "'c'", "1 - 2"])])


# ======================================================================
# 2. Bugs 6 / 7 / 8 — fixed and never widen
# ======================================================================
class Bug678RetestTests(InvariantMixin, unittest.TestCase):
    def test_bug6_operator_before_column_not_detected(self):
        for op in ("1 - ", "0 + ", "2 * ", "- ", "'x' || ", "1 = ", "0 < ", "n % 2 + "):
            sql = f"DELETE FROM acct WHERE {op}n IN (5)"
            with self.subTest(sql=sql):
                self.assertEqual(detect(sql), [])
                self.assert_never_widens(sql)

    def test_bug6_function_or_expression_column_not_detected(self):
        for sql in ("SELECT * FROM t WHERE UPPER(col) IN ('A')",
                    "SELECT * FROM t WHERE NVL(col, 'x') IN ('A')",
                    "SELECT * FROM t WHERE (t.col) IN ('A')",
                    "SELECT * FROM t WHERE n + 0 IN (1)"):
            with self.subTest(sql=sql):
                self.assertEqual(detect(sql), [])

    def test_bug7_comment_before_subquery_select_or_with(self):
        for head in ("-- c\n SELECT", "/* c */ SELECT", "/*a*/ -- b\n select",
                     "-- c\n WITH"):
            sql = (f"DELETE FROM acct WHERE acc_no IN ({head} acc_no FROM acct "
                   "WHERE flag = 'Z' ORDER BY flag, acc_no)")
            with self.subTest(sql=sql):
                self.assertEqual([c for c, _ in detect(sql)], [])

    def test_bug7_inner_list_of_subquery_still_detected(self):
        sql = ("DELETE FROM acct WHERE acc_no IN (-- c\n SELECT acc_no FROM acct "
               "WHERE flag IN ('Z', 'Y'))")
        self.assertEqual(detect(sql), [("flag", ["'Z'", "'Y'"])])
        self.assertGreater(self.assert_never_widens(sql), 0)

    def test_bug8_comment_inside_value_skips_list(self):
        for sql in ("DELETE FROM acct WHERE acc_no IN ('1001' /* x */ || '', '1002')",
                    "DELETE FROM acct WHERE n IN (- /* x */ 1, 2)",
                    "SELECT * FROM t WHERE d IN (DATE /* c */ '2024-01-01')"):
            with self.subTest(sql=sql):
                self.assertEqual(detect(sql), [])

    def test_bug8_empty_values_skip_list(self):
        for sql in ("SELECT * FROM t WHERE col IN ()",
                    "SELECT * FROM t WHERE col IN ('a',)",
                    "SELECT * FROM t WHERE col IN (, 'a')",
                    "SELECT * FROM t WHERE col IN ('a',, 'b')",
                    "SELECT * FROM t WHERE col IN (/* only */)"):
            with self.subTest(sql=sql):
                self.assertEqual(detect(sql), [])

    def test_bug8_commas_in_comments_never_split(self):
        sql = ("DELETE FROM acct WHERE acc_no IN ('1001', -- '1003', '1004'\n"
               " '1002' /* , '1003' */)")
        self.assertEqual(detect(sql), [("acc_no", ["'1001'", "'1002'"])])
        out = drop(sql, 0, {"'1001'"})
        self.assertEqual(out, "DELETE FROM acct WHERE acc_no IN ('1002')")
        self.assertEqual(affected(self, out), 1)
        self.assertGreater(self.assert_never_widens(sql), 0)

    def test_keywords_never_taken_as_column(self):
        for sql in ("SELECT * FROM t WHERE x = 1 AND IN ('a')",
                    "SELECT * FROM t WHERE NOT IN ('a')",
                    "SELECT * FROM t WHERE x IS NULL IN ('a')"):
            with self.subTest(sql=sql):
                self.assertNotIn("NULL", [c.upper() for c, _ in detect(sql)])
                self.assertNotIn("AND", [c.upper() for c, _ in detect(sql)])
                self.assertNotIn("NOT", [c.upper() for c, _ in detect(sql)])


# ======================================================================
# 3. Safety invariant — generated combinations on SQLite
# ======================================================================
class GeneratedInvariantTests(InvariantMixin, unittest.TestCase):
    PREFIXES = [
        "DELETE FROM acct WHERE {p}",
        "DELETE FROM acct WHERE flag = 'N' AND {p}",
        "DELETE FROM acct WHERE flag = 'Z' OR {p}",
        "DELETE FROM acct WHERE ({p})",
        "DELETE FROM acct WHERE NOT ({p})",
        "DELETE FROM acct WHERE grp IS NOT NULL AND NOT ({p} AND n >= 0)",
        "DELETE FROM acct WHERE NOT EXISTS (SELECT 1 FROM lkp WHERE lkp.code = acct.grp AND {p})",
        "DELETE FROM acct WHERE grp NOT IN (SELECT code FROM lkp WHERE {p})",
        "DELETE FROM acct WHERE grp IN (SELECT code FROM lkp WHERE {p})",
        "UPDATE acct SET flag = 'X' WHERE {p} AND n IS NOT NULL",
        "SELECT * FROM acct WHERE {p}",
    ]
    PREDICATES = [
        "{c} IN ({v})",
        "{c} NOT IN ({v})",
        "NOT {c} IN ({v})",
        "{c} /* c */ IN ({v})",
        "{c}\n-- c\nIN ({v})",
        "1 - {c} IN ({v})",
        "'' || {c} IN ({v})",
    ]
    LISTS = {
        "acc_no": ["'1001', '1002'", "'1001', -- x, y\n '1003'",
                   "'1001' /* , '1004' */, '1002'", "\n  '1001', -- a\n  '1002' -- b\n"],
        "n": ["-1, 0", "1, /* 2, */ 0"],
    }

    def _predicates(self, prefix: str):
        lkp_scope = "lkp" in prefix
        for pred, (col, lists) in itertools.product(self.PREDICATES, self.LISTS.items()):
            if lkp_scope:
                yield pred.format(c="seg", v="'CORP', 'RETAIL'")
                break
            for values in lists:
                yield pred.format(c=col, v=values)
        if lkp_scope:
            for pred in self.PREDICATES[1:]:
                yield pred.format(c="lkp.seg", v="'CORP', /* x, y */ 'RETAIL'")

    def assert_emptying_never_widens(self, sql: str) -> int:
        """Under a NOT, dropping some values of a list widens by design (the
        user removed an exclusion), so only emptying a list is checked: it
        must be refused or touch no more rows."""
        before = affected(self, sql)
        lists = GUI._detect_sql_in_lists(sql)
        executed = 0
        for index, item in enumerate(lists):
            try:
                out = GUI._reset_sql_in_lists(sql, lists, {index: set(item["tokens"])})
            except ValueError:
                continue
            after = affected(self, out)
            if after is None:
                continue
            executed += 1
            self.assertLessEqual(after, before, f"\n  {sql!r}\n-> {out!r}")
        return executed

    def test_invariant_generated(self):
        count = 0
        for prefix in self.PREFIXES:
            for pred in self._predicates(prefix):
                sql = prefix.format(p=pred)
                if affected(self, sql) is None:
                    continue
                negated = "NOT" in prefix or "NOT" in pred
                with self.subTest(sql=sql):
                    if negated:
                        count += self.assert_emptying_never_widens(sql)
                    else:
                        count += self.assert_never_widens(sql)
        self.assertGreater(count, 100)


# ======================================================================
# 4. Known limits (exotic) — current behaviour pinned, not failures
# ======================================================================
class KnownLimitRound3Tests(unittest.TestCase):
    def test_known_limit_lists_not_detected(self):
        """KNOWN LIMIT: not detected (fewer lists, never unsafe). TO_DATE /
        function values were not detected before this fix either; the others
        were detected by the old regex. (R2-T-fix2: PL/SQL `IF v IN (...)` is
        detected again and refused with a reason, see test_r2_reset_t2t_plsql.)"""
        for sql in (
            "SELECT * FROM t WHERE d IN (TO_DATE('2024-01-01', 'YYYY-MM-DD'))",
            "SELECT * FROM t START WITH col IN ('a') CONNECT BY PRIOR id = pid",
            "SELECT col IN ('a', 'b') AS is_ab FROM t",
        ):
            with self.subTest(sql=sql):
                self.assertEqual(detect(sql), [])

    def test_known_limit_semantic_negation_widens(self):
        """KNOWN LIMIT (same family as the pinned CASE limit of round 1): a
        top-level list negated by what follows it. Present before this fix too.
        The nested forms (COUNT(*) = 0, LEFT JOIN anti-join, `1 - (...)`,
        COALESCE(...) = 0) are now refused, see
        test_nested_semantic_negation_rejected."""
        cases = [
            ("DELETE FROM acct WHERE n IN (1) IS NOT TRUE", 3, 4),
            ("DELETE FROM acct WHERE flag = 'N' AND n IN (1) = 0", 2, 3),
        ]
        for sql, before, after in cases:
            with self.subTest(sql=sql):
                lists = GUI._detect_sql_in_lists(sql)
                self.assertEqual(len(lists), 1)
                out = GUI._reset_sql_in_lists(sql, lists, {0: set(lists[0]["tokens"])})
                self.assertIn("1=0", out)
                self.assertEqual((affected(self, sql), affected(self, out)), (before, after))

    def test_nested_semantic_negation_rejected(self):
        """Review 🟠: these nested forms widened to every row; the nested-list
        whitelist now refuses any reset of the list (ValueError)."""
        for sql in (
            "DELETE FROM acct WHERE (SELECT COUNT(*) FROM lkp WHERE lkp.code = acct.grp "
            "AND lkp.seg IN ('CORP')) = 0",
            "DELETE FROM acct WHERE acc_no IN (SELECT a.acc_no FROM acct a LEFT JOIN lkp b "
            "ON b.code = a.grp AND b.seg IN ('CORP') WHERE b.code IS NULL)",
            "DELETE FROM acct WHERE 1 - (n IN (1))",
            "DELETE FROM acct WHERE COALESCE(NULL, n IN (1)) = 0",
        ):
            with self.subTest(sql=sql):
                lists = GUI._detect_sql_in_lists(sql)
                self.assertEqual(len(lists), 1)
                with self.assertRaises(ValueError):
                    GUI._reset_sql_in_lists(sql, lists, {0: set(lists[0]["tokens"])})


if __name__ == "__main__":
    unittest.main()
