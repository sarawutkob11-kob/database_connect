"""R2-T-fix (M9) — nested IN-list Reset whitelist (_in_list_reset_refusal).

Detected mode: an IN list inside parentheses / a subquery may be reset only
when every enclosing level is provably positive; otherwise ValueError.

- Safety invariant on SQLite: a reset never makes a statement touch more rows
  than the original (a refusal or a SQL error counts as safe). Generated over
  nested NOT / EXISTS / NOT EXISTS / IN / NOT IN subqueries, inner and outer
  joins, scalar subqueries compared to values, UNION / EXCEPT / INTERSECT.
- WideningHoleTests: forms that still widen (bug evidence, see docs/tasks.md).
- Oracle old-style outer join (+): not runnable on SQLite, checked by rule.
- Usability: realistic positive nesting still resets; forms now refused.
- Pure SELECT skips the whitelist (user decision); statement-level
  MINUS / EXCEPT / HAVING rules and the emptied-NOT rule still apply.
- Dialog flow: preview shows "-- <message>", Confirm applies nothing.
- Error text names the real reason.

No Tk window, no real database (SQLite :memory:).
"""

import itertools
import os
import re
import sqlite3
import sys
import unittest
from typing import Optional
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import database_connect_gui as app  # noqa: E402
from test_r2_reset_parameter_qa import _Text, compile_nested  # noqa: E402

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
    con.execute("CREATE TABLE tgt (k TEXT)")
    con.executemany("INSERT INTO acct VALUES (?, ?, ?, ?, ?)", ACCT_ROWS)
    con.executemany("INSERT INTO lkp VALUES (?, ?)", LKP_ROWS)
    con.commit()
    return con


def affected(test: unittest.TestCase, sql: str) -> Optional[int]:
    """Rows touched (SELECT: returned) on fresh tables, None on a SQL error."""
    con = make_db(test)
    sql = sql.rstrip().rstrip(";")
    try:
        cursor = con.execute(sql)
        if re.match(r"\s*(SELECT|WITH)\b", sql, flags=re.IGNORECASE):
            return len(cursor.fetchall())
        return cursor.rowcount
    except sqlite3.Error:
        return None


def detect(sql: str) -> list:
    return GUI._detect_sql_in_lists(sql)


def index_of(sql: str, column: str) -> int:
    return [i["column"].lower() for i in detect(sql)].index(column.lower())


def reset(sql: str, column: str, remove: Optional[set] = None) -> str:
    """Reset `remove` (default: every value) of the list of `column`."""
    lists = detect(sql)
    index = index_of(sql, column)
    chosen = set(lists[index]["tokens"]) if remove is None else set(remove)
    return GUI._reset_sql_in_lists(sql, lists, {index: chosen})


def own_negated(sql: str, item: dict) -> bool:
    """The list's own predicate is `col NOT IN (` / `NOT col IN (`: removing
    some values widens by design (the user drops an exclusion)."""
    head = sql[:item["vals_span"][0]]
    head = re.sub(r"/\*.*?\*/|--[^\n]*\n", " ", head, flags=re.S)
    return bool(re.search(r"\bNOT\s+(\S+\s+)?IN\s*\(\s*$|\bNOT\s+[\w.\"]+\s+IN\s*\(\s*$",
                          head, flags=re.I))


class InvariantMixin:
    def assert_never_widens(self, sql: str) -> int:
        """Every detected list: drop all values, and each single value. A
        refusal or a SQL error is safe. Partial drops of a list whose own
        predicate is negated are skipped (wider by design)."""
        before = affected(self, sql)
        self.assertIsNotNone(before, f"original SQL must run on SQLite: {sql!r}")
        lists = detect(sql)
        executed = 0
        for index, item in enumerate(lists):
            choices = [set(item["tokens"])]
            if not own_negated(sql, item):
                choices += [{t} for t in item["tokens"]]
            for chosen in choices:
                try:
                    out = GUI._reset_sql_in_lists(sql, lists, {index: chosen})
                except ValueError:
                    continue
                after = affected(self, out)
                if after is None:
                    continue
                executed += 1
                self.assertLessEqual(
                    after, before,
                    f"\nlist {item['column']!r} drop {sorted(chosen)!r}\n  {sql}\n-> {out}\n"
                    f"  touches {after} rows, original {before}")
        return executed


# ======================================================================
# 1. Safety invariant — generated nested forms on SQLite
# ======================================================================
class GeneratedNestedInvariantTests(InvariantMixin, unittest.TestCase):
    # {p}: a predicate over lkp (code, seg); correlated where it refers to acct
    WRAPPERS = [
        # IN / NOT IN subquery, NOT in its three spellings
        "DELETE FROM acct WHERE grp IN (SELECT code FROM lkp WHERE {p})",
        "DELETE FROM acct WHERE grp NOT IN (SELECT code FROM lkp WHERE {p})",
        "DELETE FROM acct WHERE NOT grp IN (SELECT code FROM lkp WHERE {p})",
        "DELETE FROM acct WHERE NOT (grp IN (SELECT code FROM lkp WHERE {p}))",
        "DELETE FROM acct WHERE flag = 'N' AND NOT (n > 5 OR grp IN (SELECT code FROM lkp WHERE {p}))",
        # EXISTS / NOT EXISTS
        "DELETE FROM acct WHERE EXISTS (SELECT 1 FROM lkp WHERE lkp.code = acct.grp AND {p})",
        "DELETE FROM acct WHERE NOT EXISTS (SELECT 1 FROM lkp WHERE lkp.code = acct.grp AND {p})",
        "DELETE FROM acct WHERE flag = 'N' AND NOT (EXISTS (SELECT 1 FROM lkp "
        "WHERE lkp.code = acct.grp AND {p}))",
        "DELETE FROM acct WHERE flag = 'Z' OR (EXISTS (SELECT 1 FROM lkp "
        "WHERE lkp.code = acct.grp AND {p}) AND n >= 0)",
        # inner joins (ON and WHERE)
        "DELETE FROM acct WHERE acc_no IN (SELECT a.acc_no FROM acct a JOIN lkp "
        "ON lkp.code = a.grp AND {p})",
        "DELETE FROM acct WHERE acc_no IN (SELECT a.acc_no FROM acct a INNER JOIN lkp "
        "ON (lkp.code = a.grp AND {p}))",
        "DELETE FROM acct WHERE acc_no IN (SELECT a.acc_no FROM acct a INNER JOIN lkp "
        "ON lkp.code = a.grp WHERE {p})",
        # outer joins: list in the ON (anti-join) and in the WHERE (post-join filter)
        "DELETE FROM acct WHERE acc_no IN (SELECT a.acc_no FROM acct a LEFT JOIN lkp "
        "ON lkp.code = a.grp AND {p} WHERE lkp.code IS NULL)",
        "DELETE FROM acct WHERE acc_no IN (SELECT a.acc_no FROM acct a LEFT OUTER JOIN lkp "
        "ON (lkp.code = a.grp AND {p}) WHERE lkp.code IS NULL)",
        "DELETE FROM acct WHERE acc_no IN (SELECT a.acc_no FROM lkp RIGHT JOIN acct a "
        "ON lkp.code = a.grp AND {p} WHERE lkp.code IS NULL)",
        "DELETE FROM acct WHERE acc_no IN (SELECT a.acc_no FROM lkp FULL JOIN acct a "
        "ON lkp.code = a.grp AND {p} WHERE lkp.code IS NULL)",
        "DELETE FROM acct WHERE acc_no IN (SELECT a.acc_no FROM acct a LEFT JOIN lkp "
        "ON lkp.code = a.grp WHERE lkp.code IS NULL OR {p})",
        # scalar subqueries compared to values
        "DELETE FROM acct WHERE (SELECT COUNT(*) FROM lkp WHERE lkp.code = acct.grp AND {p}) = 0",
        "DELETE FROM acct WHERE 0 < (SELECT COUNT(*) FROM lkp WHERE lkp.code = acct.grp AND {p})",
        "DELETE FROM acct WHERE (SELECT MIN(code) FROM lkp WHERE lkp.code = acct.grp AND {p}) IS NULL",
        "DELETE FROM acct WHERE grp = (SELECT code FROM lkp WHERE lkp.code = acct.grp AND {p})",
        "DELETE FROM acct WHERE COALESCE((SELECT code FROM lkp WHERE lkp.code = acct.grp "
        "AND {p}), 'none') = 'none'",
        # set operators inside the subquery
        "DELETE FROM acct WHERE grp IN (SELECT code FROM lkp WHERE {p} UNION SELECT 'G9')",
        "DELETE FROM acct WHERE grp IN (SELECT 'G9' UNION ALL SELECT code FROM lkp WHERE {p})",
        "DELETE FROM acct WHERE grp IN (SELECT code FROM lkp EXCEPT SELECT code FROM lkp WHERE {p})",
        "DELETE FROM acct WHERE grp IN (SELECT code FROM lkp WHERE {p} EXCEPT SELECT 'G9')",
        "DELETE FROM acct WHERE grp IN (SELECT code FROM lkp INTERSECT SELECT code FROM lkp WHERE {p})",
        # multi-level
        "DELETE FROM acct WHERE grp IN (SELECT code FROM lkp l1 WHERE l1.code IN "
        "(SELECT code FROM lkp WHERE {p}))",
        "DELETE FROM acct WHERE grp IN (SELECT code FROM lkp l1 WHERE l1.code NOT IN "
        "(SELECT code FROM lkp WHERE {p}))",
        "DELETE FROM acct WHERE grp IN (SELECT code FROM lkp l1 WHERE NOT EXISTS "
        "(SELECT 1 FROM lkp WHERE lkp.code = l1.code AND {p}))",
        "DELETE FROM acct WHERE NOT EXISTS (SELECT 1 FROM lkp l1 WHERE l1.code = acct.grp "
        "AND l1.code IN (SELECT code FROM lkp WHERE {p}))",
        # grouping / limits / negation after the group
        "DELETE FROM acct WHERE grp IN (SELECT code FROM lkp WHERE {p} GROUP BY code "
        "HAVING COUNT(*) = 1)",
        "DELETE FROM acct WHERE grp IN (SELECT code FROM lkp WHERE {p} ORDER BY code LIMIT 1)",
        "DELETE FROM acct WHERE grp IN (SELECT code FROM lkp WHERE {p}) IS NOT TRUE",
        "DELETE FROM acct WHERE (grp IN (SELECT code FROM lkp WHERE {p})) = 0",
        "DELETE FROM acct WHERE 1 - (grp IN (SELECT code FROM lkp WHERE {p}))",
        "DELETE FROM acct WHERE NOT COALESCE(grp IN (SELECT code FROM lkp WHERE {p}), 0)",
        # UPDATE / INSERT ... SELECT / SELECT
        "UPDATE acct SET flag = 'X' WHERE EXISTS (SELECT 1 FROM lkp "
        "WHERE lkp.code = acct.grp AND {p})",
        "UPDATE acct SET flag = 'X' WHERE NOT EXISTS (SELECT 1 FROM lkp "
        "WHERE lkp.code = acct.grp AND {p})",
        "UPDATE acct SET flag = (SELECT MAX(seg) FROM lkp WHERE {p}) WHERE flag = 'N'",
        "INSERT INTO tgt SELECT acc_no FROM acct WHERE grp IN (SELECT code FROM lkp WHERE {p})",
        "INSERT INTO tgt SELECT acc_no FROM acct WHERE NOT EXISTS (SELECT 1 FROM lkp "
        "WHERE lkp.code = acct.grp AND {p})",
        "SELECT * FROM acct WHERE grp NOT IN (SELECT code FROM lkp WHERE {p})",
        "SELECT * FROM (SELECT * FROM lkp WHERE {p}) v",
    ]
    PREDICATES = [
        "seg IN ('CORP', 'RETAIL')",
        "lkp.seg IN ('CORP', 'RETAIL')",
        "code IN ('G1', 'G2')",
        "(seg IN ('CORP', 'RETAIL'))",
        "(code = 'G9' OR seg IN ('CORP', 'RETAIL'))",
        "seg /* c */ IN ('CORP', -- x, y\n 'RETAIL')",
        "seg NOT IN ('CORP', 'RETAIL')",
        "NOT seg IN ('CORP')",
    ]

    # User decision (R2-T-fix): a pure SELECT only reads, so it skips the
    # whitelist; the invariant covers the statements that write.
    WRITE_WRAPPERS = [w for w in WRAPPERS if not w.startswith("SELECT")]

    def test_nested_invariant_generated(self):
        executed = 0
        checked = 0
        for wrapper, pred in itertools.product(self.WRITE_WRAPPERS, self.PREDICATES):
            sql = wrapper.format(p=pred)
            if affected(self, sql) is None:
                continue
            checked += 1
            with self.subTest(sql=sql):
                executed += self.assert_never_widens(sql)
        self.assertGreater(checked, 250)
        self.assertGreater(executed, 60)  # positive nesting still resets

    def test_nested_negation_refuses_every_reset(self):
        """Any reset (partial or empty) of a positive list under a negated /
        compared level must raise — not just emptying it."""
        negated = [w for w in self.WRITE_WRAPPERS
                   if re.search(r"\bNOT\b|EXCEPT|INTERSECT|LEFT|RIGHT|FULL|COUNT|MIN\(|"
                                r"= \(|IS NOT TRUE|\) = 0|1 - |COALESCE|GROUP BY|LIMIT|"
                                r"FROM \(SELECT|SET flag = \(", w)
                   and "WHERE {p} EXCEPT" not in w and "WHERE lkp.code IS NULL OR" not in w]
        self.assertGreater(len(negated), 20)
        for wrapper in negated:
            sql = wrapper.format(p="seg IN ('CORP', 'RETAIL')")
            for remove in ({"'CORP'", "'RETAIL'"}, {"'CORP'"}):
                with self.subTest(sql=sql, remove=sorted(remove)):
                    with self.assertRaises(ValueError):
                        reset(sql, "seg", remove)


# ======================================================================
# 2. Widening holes still open — bug evidence (fail until fixed)
# ======================================================================
class WideningHoleTests(InvariantMixin, unittest.TestCase):
    def test_case_when_nested_list_never_widens(self):
        """CASE WHEN <nested list> OR ... THEN: WHEN is taken as a positive
        lead and OR as a positive follow, so the CASE is never seen."""
        for sql in (
            "DELETE FROM acct WHERE CASE WHEN (n IN (1, 0)) OR flag = 'Q' "
            "THEN 0 ELSE 1 END = 1",
            "DELETE FROM acct WHERE CASE WHEN EXISTS (SELECT 1 FROM lkp WHERE code = grp "
            "AND seg IN ('CORP', 'RETAIL')) OR 1 = 2 THEN 0 ELSE 1 END = 1",
            "DELETE FROM acct WHERE CASE WHEN grp IN (SELECT code FROM lkp "
            "WHERE seg IN ('CORP', 'RETAIL')) OR 1 = 2 THEN 0 ELSE 1 END = 1",
            "DELETE FROM acct WHERE flag = CASE WHEN EXISTS (SELECT 1 FROM lkp "
            "WHERE code = grp AND seg IN ('CORP', 'RETAIL')) AND 1 = 1 THEN 'Z' ELSE 'N' END",
        ):
            with self.subTest(sql=sql):
                self.assert_never_widens(sql)

    def test_inner_join_on_under_later_right_or_full_join_never_widens(self):
        """The list is in an INNER JOIN ON, but that join result is the
        null-supplying side of a later RIGHT / FULL JOIN (anti-join)."""
        for kind in ("RIGHT", "RIGHT OUTER", "FULL"):
            sql = ("DELETE FROM acct WHERE acc_no IN (SELECT a.acc_no FROM lkp b "
                   "JOIN acct x ON x.grp = b.code AND b.seg IN ('CORP', 'RETAIL') "
                   f"{kind} JOIN acct a ON a.acc_no = x.acc_no WHERE x.acc_no IS NULL)")
            with self.subTest(sql=sql):
                self.assert_never_widens(sql)

    def test_top_level_set_difference_never_widens(self):
        """Top-level list on the right of EXCEPT / MINUS (INSERT ... SELECT,
        SELECT): the review's MINUS rule is applied only to nested lists."""
        for sql in (
            "INSERT INTO tgt SELECT acc_no FROM acct "
            "EXCEPT SELECT acc_no FROM acct WHERE status IN ('A', 'B')",
            "SELECT acc_no FROM acct EXCEPT SELECT acc_no FROM acct WHERE status IN ('A', 'B')",
        ):
            with self.subTest(sql=sql):
                self.assert_never_widens(sql)
        oracle = ("INSERT INTO tgt SELECT acc_no FROM acct "
                  "MINUS SELECT acc_no FROM acct WHERE status IN ('A', 'B')")
        with self.subTest(sql=oracle):
            with self.assertRaises(ValueError):
                reset(oracle, "status")


# ======================================================================
# 3. Oracle old-style outer join (+) — not runnable on SQLite
# ======================================================================
class OracleOuterJoinTests(unittest.TestCase):
    def test_list_on_outer_joined_column_with_plus_not_detected(self):
        """`b.seg(+) IN (...)` is part of the join condition (emptying it would
        widen an anti-join) — it is never detected, so it cannot be reset.
        (Oracle also rejects (+) with IN: ORA-01719.)"""
        for sql in (
            "SELECT a.acc_no FROM acct a, lkp b WHERE a.grp = b.code(+) AND b.seg(+) IN ('C')",
            "DELETE FROM acct WHERE acc_no IN (SELECT a.acc_no FROM acct a, lkp b "
            "WHERE b.code(+) = a.grp AND b.seg(+) IN ('C') AND b.code IS NULL)",
            "DELETE FROM acct WHERE acc_no IN (SELECT a.acc_no FROM acct a, lkp b "
            "WHERE b.code(+) = a.grp AND (b.seg(+) IN ('C')) AND b.code IS NULL)",
            "DELETE FROM acct WHERE acc_no IN (SELECT a.acc_no FROM acct a, lkp b "
            "WHERE b.code(+) = a.grp AND b.seg (+) IN ('C', 'D') AND b.code IS NULL)",
        ):
            with self.subTest(sql=sql):
                self.assertEqual(detect(sql), [])

    def test_not_exists_with_plus_refused(self):
        sql = ("DELETE FROM acct a WHERE NOT EXISTS (SELECT 1 FROM lkp b "
               "WHERE b.code(+) = a.grp AND b.seg IN ('C', 'D'))")
        for remove in ({"'C'", "'D'"}, {"'C'"}):
            with self.subTest(remove=sorted(remove)):
                with self.assertRaises(ValueError) as ctx:
                    reset(sql, "b.seg", remove)
                self.assertIn("NOT EXISTS", str(ctx.exception))

    def test_post_join_filters_reset(self):
        """A list without (+) is a filter applied after the outer join (ANDed
        in WHERE): fewer values -> a subset of rows, so the reset is allowed."""
        cases = [
            ("SELECT a.acc_no FROM acct a, lkp b WHERE a.grp = b.code(+) AND b.seg IN ('C', 'D')",
             "b.seg"),
            ("DELETE FROM acct WHERE acc_no IN (SELECT a.acc_no FROM acct a, lkp b "
             "WHERE b.code(+) = a.grp AND b.code IS NULL AND a.status IN ('C', 'D'))", "a.status"),
            ("DELETE FROM acct WHERE acc_no IN (SELECT a.acc_no FROM acct a, lkp b "
             "WHERE b.code(+) = a.grp AND b.code IS NULL AND b.seg IN ('C', 'D'))", "b.seg"),
        ]
        for sql, column in cases:
            with self.subTest(sql=sql):
                self.assertIn("IN ('D')", reset(sql, column, {"'C'"}))
                self.assertIn("AND 1=0", reset(sql, column))


# ======================================================================
# 4. Usability — realistic positive nesting still resets
# ======================================================================
class PositiveNestingUsabilityTests(unittest.TestCase):
    CASES = [
        ("DELETE FROM acct WHERE grp IN (SELECT code FROM lkp WHERE seg IN ('C', 'D'))", "seg"),
        ("DELETE FROM acct WHERE EXISTS (SELECT 1 FROM lkp WHERE lkp.code = acct.grp "
         "AND lkp.seg IN ('C', 'D'))", "lkp.seg"),
        ("DELETE FROM acct WHERE acc_no IN (SELECT a.acc_no FROM acct a INNER JOIN lkp b "
         "ON b.code = a.grp AND b.seg IN ('C', 'D'))", "b.seg"),
        ("UPDATE acct a SET a.flag = 'X' WHERE EXISTS (SELECT 1 FROM lkp l INNER JOIN acct b "
         "ON b.grp = l.code AND l.seg IN ('C', 'D') WHERE b.acc_no = a.acc_no)", "l.seg"),
        ("DELETE FROM acct WHERE grp IN (SELECT l.code FROM lkp l WHERE l.seg IN "
         "(SELECT x.seg FROM lkp x WHERE x.code IN (SELECT a.grp FROM acct a "
         "WHERE a.status IN ('C', 'D'))))", "a.status"),
        ("DELETE FROM acct a /* target */\n WHERE a.grp IN (SELECT l.code FROM lkp l -- lookup\n"
         "   WHERE l.flag = 'Y'\n     AND l.seg IN ('C', -- corp\n 'D' /* d */))", "l.seg"),
        ("DELETE FROM FCT_ACCT t WHERE t.N_RUN_SKEY IN (SELECT r.N_RUN_SKEY FROM DIM_RUN r "
         "WHERE r.V_RUN_TYPE IN ('C', 'D')) AND t.FIC_MIS_DATE = DATE '2024-01-31'",
         "r.V_RUN_TYPE"),
        ("DELETE FROM acct WHERE flag = 'N' AND (status = 'Z' OR grp IN "
         "(SELECT DISTINCT code FROM lkp WHERE (seg IN ('C', 'D'))))", "seg"),
        ("DELETE FROM acct WHERE grp IN (SELECT code FROM lkp WHERE seg IN ('C', 'D') "
         "UNION SELECT code FROM lkp2 WHERE x = 1)", "seg"),
        ("INSERT INTO tgt SELECT acc_no FROM acct WHERE grp IN "
         "(SELECT code FROM lkp WHERE seg IN ('C', 'D'))", "seg"),
        ("SELECT * FROM acct WHERE EXISTS (SELECT 1 FROM lkp WHERE code = grp "
         "AND seg IN ('C', 'D'))", "seg"),
        ("DELETE FROM acct WHERE grp IN (WITH x AS (SELECT 1 FROM dual) "
         "SELECT code FROM lkp WHERE seg IN ('C', 'D'))", "seg"),
    ]

    def test_partial_and_full_reset_allowed(self):
        for sql, column in self.CASES:
            with self.subTest(sql=sql):
                partial = reset(sql, column, {"'C'"})
                self.assertNotIn("'C'", partial.replace("-- corp", ""))
                self.assertIn("'D'", partial)
                full = reset(sql, column)
                self.assertIn("1=0", full)
                self.assertNotIn("'C'", full.replace("-- corp", ""))

    def test_full_reset_shapes(self):
        sql = self.CASES[0][0]
        self.assertEqual(norm(reset(sql, "seg")),
                         "DELETE FROM acct WHERE grp IN (SELECT code FROM lkp WHERE 1=0)")
        sql = self.CASES[2][0]
        self.assertEqual(norm(reset(sql, "b.seg")),
                         "DELETE FROM acct WHERE acc_no IN (SELECT a.acc_no FROM acct a "
                         "INNER JOIN lkp b ON b.code = a.grp AND 1=0)")

    def test_now_refused_forms(self):
        """USABILITY NOTE (B): refused in statements that write (safe).
        The pure SELECT forms are allowed again (user decision), see
        PureSelectRevertTests. Pinned so a change is noticed. (R2-T-fix2:
        `INSERT INTO tgt WITH x AS (... IN ...) SELECT ... FROM x` now resets,
        see tests/test_r2_reset_t2t_plsql.py.)"""
        cases = [
            ("DELETE FROM acct WHERE (grp, status) IN (SELECT code, 'A' FROM lkp "
             "WHERE seg IN ('C', 'D'))", "seg", "not `column IN (subquery)`"),
            ("DELETE FROM acct WHERE grp IN (SELECT code FROM lkp INTERSECT "
             "SELECT code FROM lkp WHERE seg IN ('C', 'D'))", "seg", "INTERSECT"),
            ("MERGE INTO acct t USING (SELECT * FROM lkp WHERE seg IN ('C', 'D')) s "
             "ON (t.grp = s.code) WHEN MATCHED THEN UPDATE SET t.flag = 'X'", "seg", "USING"),
            ("UPDATE acct SET flag = (SELECT MAX(seg) FROM lkp WHERE seg IN ('C', 'D'))",
             "seg", "compared scalar subquery (after =)"),
        ]
        for sql, column, reason in cases:
            with self.subTest(sql=sql):
                with self.assertRaises(ValueError) as ctx:
                    reset(sql, column, {"'C'"})
                self.assertIn(reason, str(ctx.exception))
        sql = ("SELECT grp, COUNT(*) FROM acct WHERE grp IN (SELECT code FROM lkp "
               "WHERE seg IN ('C', 'D')) GROUP BY grp")
        # top-level GROUP BY without HAVING does not block a list
        self.assertIn("IN ('D')", reset(sql, "seg", {"'C'"}))


# ======================================================================
# 4b. User decision: a pure SELECT skips the whitelist (pre-whitelist rules)
# ======================================================================
class PureSelectRevertTests(unittest.TestCase):
    ALLOWED = [
        ("SELECT * FROM (SELECT * FROM acct WHERE status IN ('C', 'D')) v "
         "WHERE v.flag = 'N'", "status"),
        ("WITH x AS (SELECT * FROM acct WHERE status IN ('C', 'D')) SELECT * FROM x",
         "status"),
        ("SELECT acc_no, (SELECT seg FROM lkp WHERE code = grp AND seg IN ('C', 'D')) s "
         "FROM acct", "seg"),
        ("SELECT * FROM acct WHERE NOT (status IN ('C', 'D') AND flag = 'Z')", "status"),
        ("SELECT * FROM acct WHERE (grp, status) IN (SELECT code, 'A' FROM lkp "
         "WHERE seg IN ('C', 'D'))", "seg"),
        ("SELECT * FROM acct WHERE grp IN (SELECT code FROM lkp INTERSECT "
         "SELECT code FROM lkp WHERE seg IN ('C', 'D'))", "seg"),
        ("SELECT * FROM acct WHERE grp IN (SELECT code FROM lkp MINUS "
         "SELECT code FROM lkp WHERE seg IN ('C', 'D'))", "seg"),
        ("SELECT a.acc_no FROM acct a LEFT JOIN lkp b ON b.code = a.grp "
         "AND b.seg IN ('C', 'D')", "b.seg"),
        ("SELECT CASE WHEN status IN ('C', 'D') THEN 1 ELSE 0 END FROM acct", "status"),
        ("SELECT * FROM acct WHERE grp NOT IN (SELECT code FROM lkp WHERE seg IN ('C', 'D'))",
         "seg"),
        ("-- note\nSELECT * FROM acct WHERE grp IN (SELECT code FROM lkp "
         "WHERE seg IN ('C', 'D') GROUP BY code HAVING COUNT(*) = 1);", "seg"),
    ]

    def test_partial_reset_allowed(self):
        for sql, column in self.ALLOWED:
            with self.subTest(sql=sql):
                out = reset(sql, column, {"'C'"})
                self.assertIn("'D'", out)
                self.assertNotIn("'C'", out)

    def test_full_reset_allowed_without_negation(self):
        for sql, column in self.ALLOWED[:3] + self.ALLOWED[4:9] + self.ALLOWED[10:]:
            with self.subTest(sql=sql):
                self.assertIn("1=0", reset(sql, column))

    def test_emptied_under_negation_still_refused(self):
        """The emptied-NOT-IN rule of before the whitelist stays for SELECT."""
        for sql, column, reason in (
            ("SELECT * FROM acct WHERE status NOT IN ('C', 'D')", "status",
             "status NOT IN (...) would have no values left"),
            ("SELECT * FROM acct WHERE NOT status IN ('C', 'D')", "status",
             "NOT status IN (...) would have no values left"),
            ("SELECT * FROM acct WHERE NOT (status IN ('C', 'D') AND flag = 'Z')", "status",
             "inside NOT (...)"),
            ("SELECT * FROM acct WHERE NOT EXISTS (SELECT 1 FROM lkp WHERE code = grp "
             "AND seg IN ('C', 'D'))", "seg", "inside NOT EXISTS (subquery)"),
            ("SELECT * FROM acct WHERE grp NOT IN (SELECT code FROM lkp "
             "WHERE seg IN ('C', 'D'))", "seg", "inside NOT IN (subquery)"),
            ("SELECT * FROM acct WHERE NOT grp IN (SELECT code FROM lkp "
             "WHERE seg IN ('C', 'D'))", "seg", "inside NOT column IN (subquery)"),
        ):
            with self.subTest(sql=sql):
                with self.assertRaises(ValueError) as ctx:
                    reset(sql, column)
                self.assertIn(reason, str(ctx.exception))
                self.assertIn("every row", str(ctx.exception))

    def test_statement_level_rules_still_apply_to_select(self):
        for sql, reason in (
            ("SELECT acc_no FROM acct EXCEPT SELECT acc_no FROM acct "
             "WHERE status IN ('C', 'D')", "after EXCEPT"),
            ("SELECT acc_no FROM acct MINUS SELECT acc_no FROM acct "
             "WHERE status IN ('C', 'D')", "after MINUS"),
            ("SELECT grp FROM acct WHERE status IN ('C', 'D') GROUP BY grp "
             "HAVING COUNT(*) = 1", "HAVING"),
        ):
            for remove in (None, {"'C'"}):
                with self.subTest(sql=sql, remove=remove):
                    with self.assertRaises(ValueError) as ctx:
                        reset(sql, "status", remove)
                    self.assertIn(reason, str(ctx.exception))

    def test_statements_that_write_keep_the_whitelist(self):
        """INSERT ... SELECT, CREATE TABLE AS, SELECT INTO, several statements
        and unknown statement types are not a pure SELECT (fail safe).
        R2-T-fix2: an inline view in a comma / inner-joined FROM of INSERT
        ... SELECT (also after a WITH) now resets; the others stay refused."""
        inner = "SELECT * FROM (SELECT * FROM acct WHERE status IN ('C', 'D')) v"
        for sql in (
            f"CREATE TABLE tgt AS {inner}",
            "SELECT * INTO tgt FROM (SELECT * FROM acct WHERE status IN ('C', 'D')) v",
            f"{inner}; DELETE FROM acct WHERE 1 = 1",
            f"BEGIN {inner}; END;",
            f"({inner})",
        ):
            with self.subTest(sql=sql):
                with self.assertRaises(ValueError):
                    reset(sql, "status", {"'C'"})
        for sql in (f"INSERT INTO tgt {inner}",
                    f"WITH x AS (SELECT 1 FROM dual) INSERT INTO tgt {inner}"):
            with self.subTest(sql=sql):
                self.assertIn("IN ('D')", reset(sql, "status", {"'C'"}))
        self.assertIn("IN ('D')", reset(inner, "status", {"'C'"}))
        self.assertIn("IN ('D')", reset(inner + ";", "status", {"'C'"}))

    def test_case_still_refused_in_writes_not_in_select(self):
        select = "SELECT * FROM acct WHERE CASE WHEN n IN (1, 0) THEN 0 ELSE 1 END = 1"
        self.assertIn("1=0", reset(select, "n"))
        delete = "DELETE FROM acct WHERE CASE WHEN n IN (1, 0) THEN 0 ELSE 1 END = 1"
        with self.assertRaises(ValueError) as ctx:
            reset(delete, "n", {"1"})
        self.assertIn("CASE", str(ctx.exception))


# ======================================================================
# 4c. Bug 11 follow-up: top-level list before GROUP BY ... HAVING
# ======================================================================
class TopLevelHavingTests(InvariantMixin, unittest.TestCase):
    SQL = ("INSERT INTO tgt SELECT grp FROM acct WHERE flag IN ('N', 'Z') "
           "GROUP BY grp HAVING COUNT(*) = 1")

    def test_unchecked_reset_widens_on_sqlite(self):
        unchecked = self.SQL.replace("IN ('N', 'Z')", "IN ('N')")
        self.assertEqual((affected(self, self.SQL), affected(self, unchecked)), (2, 3))

    def test_refused_partial_and_full(self):
        for remove in (None, {"'Z'"}):
            with self.subTest(remove=remove):
                with self.assertRaises(ValueError) as ctx:
                    reset(self.SQL, "flag", remove)
                self.assertIn("GROUP BY ... HAVING", str(ctx.exception))
        self.assertEqual(self.assert_never_widens(self.SQL), 0)

    def test_list_in_having_or_without_having_allowed(self):
        for sql in (
            "INSERT INTO tgt SELECT grp FROM acct GROUP BY grp HAVING grp IN ('G1', 'G2')",
            "INSERT INTO tgt SELECT grp FROM acct WHERE flag IN ('N', 'Z') GROUP BY grp",
            "INSERT INTO tgt SELECT grp FROM acct WHERE flag IN ('N', 'Z') "
            "UNION SELECT code FROM lkp GROUP BY code HAVING COUNT(*) = 1",
        ):
            with self.subTest(sql=sql):
                self.assertGreater(self.assert_never_widens(sql), 0)

    def test_nested_list_under_statement_level_except_refused(self):
        sql = ("INSERT INTO tgt SELECT acc_no FROM acct EXCEPT SELECT acc_no FROM acct "
               "WHERE grp IN (SELECT code FROM lkp WHERE seg IN ('CORP', 'RETAIL')))")
        with self.assertRaises(ValueError) as ctx:
            reset(sql, "seg", {"'CORP'"})
        self.assertIn("after EXCEPT", str(ctx.exception))


# ======================================================================
# 4d. Bug 10 follow-up: inner JOIN ON in a FROM with any outer join
# ======================================================================
class InnerJoinWithOuterJoinTests(unittest.TestCase):
    def test_refused_when_from_has_outer_join(self):
        for sql in (
            "DELETE FROM acct WHERE acc_no IN (SELECT a.acc_no FROM lkp b JOIN acct x "
            "ON x.grp = b.code AND b.seg IN ('C', 'D') LEFT JOIN acct a ON a.acc_no = x.acc_no)",
            "DELETE FROM acct WHERE acc_no IN (SELECT a.acc_no FROM acct a LEFT JOIN lkp c "
            "ON c.code = a.grp INNER JOIN lkp b ON b.code = a.grp AND b.seg IN ('C', 'D'))",
            "INSERT INTO tgt SELECT x.acc_no FROM lkp b JOIN acct x ON x.grp = b.code "
            "AND b.seg IN ('C', 'D') FULL JOIN acct a ON a.acc_no = x.acc_no",
        ):
            with self.subTest(sql=sql):
                with self.assertRaises(ValueError) as ctx:
                    reset(sql, "b.seg", {"'C'"})
                self.assertIn("outer", str(ctx.exception))

    def test_outer_join_in_other_level_does_not_block(self):
        sql = ("DELETE FROM acct WHERE acc_no IN (SELECT a.acc_no FROM acct a JOIN lkp b "
               "ON b.code = a.grp AND b.seg IN ('C', 'D') WHERE a.grp IN (SELECT l.code "
               "FROM lkp l LEFT JOIN acct z ON z.grp = l.code))")
        self.assertIn("IN ('D')", reset(sql, "b.seg", {"'C'"}))


# ======================================================================
# 5. Dialog flow (detected mode) with the real nested functions
# ======================================================================
class DetectedDialogFlowTests(unittest.TestCase):
    def run_dialog(self, sql: str, column: str, remove: Optional[set] = None):
        stub = GUI.__new__(GUI)
        stub.sql_context = _Text(sql)
        stub._excel_parameter_values = {}
        stub.root = mock.Mock(name="root")
        detected = detect(sql)
        index = index_of(sql, column)
        key = str(index)
        chosen = set(detected[index]["tokens"]) if remove is None else set(remove)
        column_selected = {key: chosen}
        env = {
            "self": stub,
            "detected_mode": True,
            "detected": detected,
            "source_sql": sql,
            "column_selected": column_selected,
            "column_tokens": {str(i): item["tokens"] for i, item in enumerate(detected)},
            "column_var": mock.Mock(name="column_var"),
            "dialog": mock.Mock(name="dialog"),
            "close_after_selected": False,
            "render_column_list": mock.Mock(name="render_column_list"),
            "render_values": mock.Mock(name="render_values"),
            "sql_preview": _Text(),
        }
        with mock.patch.object(app, "messagebox") as mb:
            funcs = compile_nested(
                GUI.show_reset_parameter_dialog,
                ("load_tokens", "selected_of", "build_reset_values", "render_sql",
                 "build_detected_sql", "refresh_sql_preview", "write_sql", "reset_selected"),
                env,
            )
            funcs["refresh_sql_preview"]()
            preview = env["sql_preview"].content
            funcs["reset_selected"]()
        return stub, env, mb, preview

    REFUSED = [
        ("DELETE FROM acct WHERE NOT grp IN (SELECT code FROM lkp WHERE seg IN ('C', 'D'))",
         "seg", "NOT column IN (subquery)"),
        ("DELETE FROM acct WHERE NOT EXISTS (SELECT 1 FROM lkp WHERE code = grp "
         "AND seg IN ('C', 'D'))", "seg", "NOT EXISTS"),
        ("DELETE FROM acct WHERE grp IN (SELECT code FROM lkp MINUS SELECT code FROM lkp "
         "WHERE seg IN ('C', 'D'))", "seg", "MINUS"),
        ("DELETE FROM acct WHERE acc_no IN (SELECT a.acc_no FROM acct a LEFT JOIN lkp b "
         "ON b.code = a.grp AND b.seg IN ('C', 'D') WHERE b.code IS NULL)", "b.seg", "outer"),
    ]

    def test_refusal_preview_and_confirm_applies_nothing(self):
        for sql, column, reason in self.REFUSED:
            for remove in (None, {"'C'"}):
                with self.subTest(sql=sql, remove=remove):
                    stub, env, mb, preview = self.run_dialog(sql, column, remove)
                    self.assertTrue(preview.startswith(sql + "\n\n-- Cannot reset "), preview)
                    self.assertIn(reason, preview.split("\n\n-- ", 1)[1])
                    mb.showerror.assert_called_once()
                    self.assertEqual(mb.showerror.call_args.args[0], "Reset Error")
                    self.assertIn(reason, mb.showerror.call_args.args[1])
                    self.assertIs(mb.showerror.call_args.kwargs.get("parent"), env["dialog"])
                    self.assertEqual(stub.sql_context.content, sql)
                    env["dialog"].destroy.assert_not_called()

    def test_positive_nesting_preview_equals_applied(self):
        sql = "DELETE FROM acct WHERE grp IN (SELECT code FROM lkp WHERE seg IN ('C', 'D'))"
        stub, env, mb, preview = self.run_dialog(sql, "seg")
        mb.showerror.assert_not_called()
        self.assertEqual(norm(preview),
                         "DELETE FROM acct WHERE grp IN (SELECT code FROM lkp WHERE 1=0)")
        self.assertEqual(stub.sql_context.content, preview)
        env["dialog"].destroy.assert_called_once_with()


# ======================================================================
# 6. Error text names the real reason
# ======================================================================
class ErrorTextTests(unittest.TestCase):
    CASES = [
        ("DELETE FROM acct WHERE grp NOT IN (SELECT code FROM lkp WHERE seg IN ('C'))",
         "NOT IN (subquery)"),
        ("DELETE FROM acct WHERE NOT grp IN (SELECT code FROM lkp WHERE seg IN ('C'))",
         "NOT column IN (subquery)"),
        ("DELETE FROM acct WHERE NOT EXISTS (SELECT 1 FROM lkp WHERE seg IN ('C'))",
         "NOT EXISTS"),
        ("DELETE FROM acct WHERE NOT (grp IN (SELECT code FROM lkp WHERE seg IN ('C')))",
         "NOT (...)"),
        ("DELETE FROM acct WHERE grp <> ALL (SELECT code FROM lkp WHERE seg IN ('C'))",
         "quantified comparison (ALL"),
        ("DELETE FROM acct WHERE grp = ANY (SELECT code FROM lkp WHERE seg IN ('C'))",
         "quantified comparison (ANY"),
        ("DELETE FROM acct WHERE grp IN (SELECT code FROM lkp MINUS "
         "SELECT code FROM lkp WHERE seg IN ('C'))", "MINUS"),
        ("DELETE FROM acct WHERE grp IN (SELECT code FROM lkp EXCEPT "
         "SELECT code FROM lkp WHERE seg IN ('C'))", "EXCEPT"),
        ("DELETE FROM acct WHERE acc_no IN (SELECT a.acc_no FROM acct a FULL JOIN lkp b "
         "ON b.code = a.grp AND b.seg IN ('C') WHERE b.code IS NULL)", "outer"),
        ("DELETE FROM acct WHERE (SELECT COUNT(*) FROM lkp WHERE code = grp "
         "AND seg IN ('C')) = 0", "scalar subquery"),
        ("DELETE FROM acct WHERE grp IN (SELECT code FROM lkp WHERE seg IN ('C') "
         "GROUP BY code HAVING COUNT(*) = 1)", "GROUP"),
        ("DELETE FROM acct WHERE grp IN (SELECT MAX(code) FROM lkp WHERE seg IN ('C'))",
         "MAX"),
        ("DELETE FROM acct WHERE grp IN (SELECT code FROM lkp WHERE seg IN ('C') "
         "AND ROWNUM <= 1)", "ROWNUM"),
        ("DELETE FROM acct WHERE grp IN (SELECT code FROM lkp WHERE seg IN ('C')) = 0",
         "compared"),
        ("DELETE FROM acct WHERE EXISTS (SELECT 1 FROM lkp WHERE CASE WHEN seg IN ('C') "
         "THEN 1 ELSE 0 END = 1)", "CASE"),
    ]

    def test_reason_and_column_named(self):
        for sql, reason in self.CASES:
            with self.subTest(sql=sql):
                lists = detect(sql)
                self.assertEqual(len(lists), 1)
                column = lists[0]["column"]
                self.assertIn(column, ("seg", "b.seg"))
                with self.assertRaises(ValueError) as ctx:
                    reset(sql, column, {"'C'"})
                message = str(ctx.exception)
                self.assertTrue(message.startswith(f"Cannot reset {column} IN (...): it is "),
                                message)
                self.assertIn(reason, message)
                self.assertNotIn("seg NOT IN", message)
                self.assertIn("edit the SQL by hand", message)

    def test_own_negation_messages(self):
        top = "DELETE FROM acct WHERE seg NOT IN ('C')"
        with self.assertRaises(ValueError) as ctx:
            reset(top, "seg")
        self.assertTrue(str(ctx.exception).startswith("seg NOT IN (...) would have no values left"))
        nested = "DELETE FROM acct WHERE EXISTS (SELECT 1 FROM lkp WHERE code = grp AND NOT seg IN ('C'))"
        with self.assertRaises(ValueError) as ctx:
            reset(nested, "seg")
        self.assertTrue(str(ctx.exception).startswith("NOT seg IN (...) would have no values left"))


# ======================================================================
# 7. QA round after bugs 9-11 + pure-SELECT scope change
# ======================================================================
class ExtendedWriteInvariantTests(InvariantMixin, unittest.TestCase):
    """Generated invariant for statements that write: parenthesised joins
    with an outer join inside / outside, CASE nested in function calls, a
    closed CASE ... END before the list, UPDATE ... FROM. {b} / {c} is a
    predicate on alias b / c."""
    WRAPPERS = [
        # outer join inside a parenthesised join; list in the outer inner-JOIN ON
        "DELETE FROM acct WHERE acc_no IN (SELECT a.acc_no FROM acct a JOIN (lkp b LEFT JOIN "
        "lkp c ON c.code = b.code) ON b.code = a.grp AND {b})",
        "INSERT INTO tgt SELECT a.acc_no FROM acct a JOIN (lkp b LEFT JOIN lkp c "
        "ON c.code = b.code) ON b.code = a.grp AND {b}",
        # list in the ON of the outer join inside the parentheses
        "DELETE FROM acct WHERE acc_no IN (SELECT a.acc_no FROM acct a JOIN (lkp b LEFT JOIN "
        "lkp c ON c.code = b.code AND {c}) ON b.code = a.grp WHERE c.code IS NULL)",
        # parenthesised inner join that is the null-supplying side of an outer join
        "DELETE FROM acct WHERE acc_no IN (SELECT a.acc_no FROM acct a LEFT JOIN (lkp b JOIN "
        "lkp c ON c.code = b.code AND {c}) ON b.code = a.grp WHERE b.code IS NULL)",
        "INSERT INTO tgt SELECT a.acc_no FROM acct a LEFT JOIN (lkp b JOIN lkp c "
        "ON c.code = b.code AND {c}) ON b.code = a.grp WHERE b.code IS NULL",
        "DELETE FROM acct WHERE acc_no IN (SELECT a.acc_no FROM acct a LEFT JOIN (lkp b JOIN "
        "lkp c ON c.code = b.code) ON b.code = a.grp AND {b} WHERE b.code IS NULL)",
        "DELETE FROM acct WHERE acc_no IN (SELECT a.acc_no FROM (lkp b JOIN acct x "
        "ON x.grp = b.code AND {b}) RIGHT JOIN acct a ON a.acc_no = x.acc_no "
        "WHERE x.acc_no IS NULL)",
        "DELETE FROM acct WHERE acc_no IN (SELECT a.acc_no FROM acct a JOIN (lkp b JOIN "
        "lkp c ON c.code = b.code AND {c}) ON b.code = a.grp)",
        # inner join followed by an outer join; comma join after an outer join
        "DELETE FROM acct WHERE acc_no IN (SELECT a.acc_no FROM acct a JOIN lkp b "
        "ON b.code = a.grp AND {b} LEFT JOIN lkp c ON c.code = a.grp AND c.seg = 'X' "
        "WHERE c.code IS NULL)",
        "DELETE FROM acct WHERE acc_no IN (SELECT a.acc_no FROM acct a LEFT JOIN lkp c "
        "ON c.code = a.grp, lkp b WHERE b.code = a.grp AND {b})",
        # UPDATE ... FROM (SQLite / PostgreSQL)
        "UPDATE acct SET flag = 'X' FROM lkp b WHERE b.code = acct.grp AND {b}",
        "UPDATE acct SET flag = 'X' FROM lkp b LEFT JOIN lkp c ON c.code = b.code AND {c} "
        "WHERE c.code IS NULL AND b.code = acct.grp",
        "UPDATE acct SET flag = 'X' FROM lkp b JOIN lkp c ON c.code = b.code AND {c} "
        "RIGHT JOIN acct z ON z.grp = b.code WHERE b.code IS NULL AND z.acc_no = acct.acc_no",
        # CASE nested in function calls
        "DELETE FROM acct WHERE COALESCE(CASE WHEN EXISTS (SELECT 1 FROM lkp b "
        "WHERE b.code = acct.grp AND {b}) THEN 1 END, 0) = 0",
        "DELETE FROM acct WHERE ABS(CASE WHEN acct.grp IN (SELECT b.code FROM lkp b "
        "WHERE {b}) THEN 0 ELSE 1 END) = 1",
        "DELETE FROM acct WHERE IFNULL(NULLIF(CASE WHEN EXISTS (SELECT 1 FROM lkp b "
        "WHERE b.code = acct.grp AND {b}) THEN 0 END, 5), 1) = 1",
        "DELETE FROM acct WHERE flag = 'N' AND LENGTH(CASE WHEN EXISTS (SELECT 1 FROM lkp b "
        "WHERE b.code = acct.grp AND {b}) THEN '' ELSE 'xx' END) = 2",
        "UPDATE acct SET flag = 'Q' WHERE flag <> COALESCE(CASE WHEN EXISTS (SELECT 1 "
        "FROM lkp b WHERE b.code = acct.grp AND {b}) THEN 'N' END, 'X')",
        "DELETE FROM acct WHERE MAX(0, CASE WHEN (n > 5 OR EXISTS (SELECT 1 FROM lkp b "
        "WHERE b.code = acct.grp AND {b})) THEN 0 ELSE 1 END) = 1",
        "INSERT INTO tgt SELECT acc_no FROM acct WHERE COALESCE(CASE WHEN grp IN "
        "(SELECT b.code FROM lkp b WHERE {b}) THEN NULL ELSE 1 END, 0) = 1",
    ]
    # a closed CASE ... END before the list: still resettable
    CLOSED_CASE = [
        "DELETE FROM acct WHERE CASE WHEN flag = 'Z' THEN 1 ELSE 0 END = 0 AND grp IN "
        "(SELECT b.code FROM lkp b WHERE {b})",
        "DELETE FROM acct WHERE EXISTS (SELECT 1 FROM lkp b WHERE CASE b.seg WHEN 'X' THEN 1 "
        "ELSE 0 END = 0 AND b.code = acct.grp AND {b})",
        "DELETE FROM acct WHERE COALESCE(CASE WHEN n > 9 THEN 1 END, 0) = 0 AND EXISTS "
        "(SELECT 1 FROM lkp b WHERE b.code = acct.grp AND {b})",
        "DELETE FROM acct WHERE grp IN (SELECT b.code FROM lkp b WHERE CASE WHEN "
        "b.code = 'G9' THEN 1 ELSE 0 END = 0 AND {b})",
        "UPDATE acct SET flag = CASE WHEN n > 0 THEN 'P' ELSE 'M' END WHERE grp IN "
        "(SELECT b.code FROM lkp b WHERE {b})",
    ]
    PREDICATES = [
        "{t}.seg IN ('CORP', 'RETAIL')",
        "{t}.code IN ('G1', 'G2')",
        "({t}.seg IN ('CORP', 'RETAIL'))",
        "({t}.code = 'G9' OR {t}.seg IN ('CORP', 'RETAIL'))",
        "{t}.seg NOT IN ('CORP', 'RETAIL')",
        "NOT {t}.seg IN ('CORP')",
    ]

    def build(self, wrapper: str, pred: str) -> str:
        return wrapper.format(b=pred.format(t="b"), c=pred.format(t="c"))

    def test_extended_invariant_generated(self):
        checked = 0
        for wrapper, pred in itertools.product(self.WRAPPERS + self.CLOSED_CASE,
                                               self.PREDICATES):
            sql = self.build(wrapper, pred)
            self.assertIsNotNone(affected(self, sql), sql)
            checked += 1
            with self.subTest(sql=sql):
                self.assert_never_widens(sql)
        self.assertEqual(checked, 150)

    def test_outer_join_inside_parenthesised_join_keeps_outer_on_resettable(self):
        sql = self.build(self.WRAPPERS[0], self.PREDICATES[0])
        self.assertIn("IN ('RETAIL')", reset(sql, "b.seg", {"'CORP'"}))
        self.assertIn("AND 1=0)", reset(sql, "b.seg"))
        self.assertEqual(self.assert_never_widens(sql), 3)

    def test_parenthesised_outer_join_lists_refused(self):
        for wrapper, column in ((self.WRAPPERS[2], "c.seg"), (self.WRAPPERS[3], "c.seg"),
                                (self.WRAPPERS[5], "b.seg"), (self.WRAPPERS[6], "b.seg")):
            sql = self.build(wrapper, self.PREDICATES[0])
            for remove in (None, {"'CORP'"}):
                with self.subTest(sql=sql, remove=remove):
                    with self.assertRaises(ValueError):
                        reset(sql, column, remove)

    def test_case_nested_in_function_refused(self):
        for wrapper in self.WRAPPERS[13:]:
            sql = self.build(wrapper, self.PREDICATES[0])
            for remove in (None, {"'CORP'"}):
                with self.subTest(sql=sql, remove=remove):
                    with self.assertRaises(ValueError) as ctx:
                        reset(sql, "b.seg", remove)
                    self.assertIn("CASE", str(ctx.exception))
        top = "DELETE FROM acct WHERE COALESCE(CASE WHEN n IN (1, 0) THEN NULL ELSE 1 END, 0) = 0"
        with self.assertRaises(ValueError) as ctx:
            reset(top, "n", {"1"})
        self.assertIn("inside a CASE expression", str(ctx.exception))

    def test_closed_case_before_list_still_resets(self):
        for wrapper in self.CLOSED_CASE:
            sql = self.build(wrapper, self.PREDICATES[0])
            with self.subTest(sql=sql):
                self.assertIn("IN ('RETAIL')", reset(sql, "b.seg", {"'CORP'"}))
                self.assertIn("1=0", reset(sql, "b.seg"))
                self.assertEqual(self.assert_never_widens(sql), 3)
        top = ("DELETE FROM acct WHERE flag = 'N' AND CASE WHEN status = 'A' THEN 1 ELSE 0 END "
               "= 1 OR n IN (1, 2)")
        self.assertIn("OR 1=0", reset(top, "n"))
        self.assertEqual(self.assert_never_widens(top), 3)


class NonSqliteWriteFormsTests(unittest.TestCase):
    """Forms SQLite cannot run, checked by rule: data-modifying CTEs,
    SELECT ... FOR UPDATE, PL/SQL blocks containing DELETE, MERGE."""

    def assert_refused(self, sql: str, column: str, reason: Optional[str] = None):
        for remove in (None, {detect(sql)[index_of(sql, column)]["tokens"][0]}):
            with self.subTest(sql=sql, remove=remove):
                with self.assertRaises(ValueError) as ctx:
                    reset(sql, column, remove)
                if reason:
                    self.assertIn(reason, str(ctx.exception))

    def test_data_modifying_ctes_use_the_whitelist(self):
        for sql, column in (
            ("WITH d AS (DELETE FROM acct WHERE status IN ('A', 'B') RETURNING *) "
             "SELECT * FROM d", "status"),
            ("WITH d AS (DELETE FROM acct WHERE NOT (status IN ('A', 'B')) RETURNING *) "
             "SELECT * FROM d", "status"),
            ("WITH d AS (UPDATE acct SET flag = 'X' WHERE NOT EXISTS (SELECT 1 FROM lkp "
             "WHERE code = grp AND seg IN ('CORP', 'RETAIL')) RETURNING *) SELECT * FROM d",
             "seg"),
            ("WITH d AS (DELETE FROM acct WHERE grp NOT IN (SELECT code FROM lkp "
             "WHERE seg IN ('CORP', 'RETAIL')) RETURNING *) SELECT COUNT(*) FROM d", "seg"),
        ):
            tokens = list(app._scan_sql(sql))
            self.assertFalse(GUI._is_pure_select(sql, tokens), sql)
            self.assert_refused(sql, column)

    def test_select_for_update_uses_the_whitelist(self):
        for sql, column, reason in (
            ("SELECT * FROM (SELECT * FROM acct WHERE status IN ('A', 'B')) v FOR UPDATE",
             "status", "after FROM"),
            ("SELECT * FROM acct WHERE grp NOT IN (SELECT code FROM lkp "
             "WHERE seg IN ('CORP', 'RETAIL')) FOR UPDATE", "seg", "NOT IN (subquery)"),
            ("SELECT * FROM acct a WHERE NOT EXISTS (SELECT 1 FROM lkp WHERE code = a.grp "
             "AND seg IN ('CORP', 'RETAIL')) FOR UPDATE OF a.flag", "seg", "NOT EXISTS"),
            ("SELECT * FROM acct WHERE CASE WHEN status IN ('A', 'B') THEN 0 ELSE 1 END = 1 "
             "FOR UPDATE NOWAIT", "status", "CASE"),
        ):
            self.assertFalse(GUI._is_pure_select(sql, list(app._scan_sql(sql))))
            self.assert_refused(sql, column, reason)
        top = "SELECT * FROM acct WHERE status IN ('A', 'B') FOR UPDATE"
        self.assertEqual(norm(reset(top, "status")),
                         "SELECT * FROM acct WHERE 1=0 FOR UPDATE")

    def test_plsql_blocks_with_delete(self):
        refused = [
            ("BEGIN DELETE FROM acct WHERE NOT EXISTS (SELECT 1 FROM lkp WHERE code = grp "
             "AND seg IN ('CORP', 'RETAIL')); COMMIT; END;", "seg", "NOT EXISTS"),
            ("BEGIN DELETE FROM tgt WHERE k IN (SELECT acc_no FROM acct MINUS SELECT acc_no "
             "FROM acct WHERE status IN ('A', 'B')); END;", "status", "MINUS"),
            ("BEGIN DELETE FROM tgt WHERE CASE WHEN k IN ('1', '2') THEN 0 ELSE 1 END = 1; END;",
             "k", "CASE"),
            ("BEGIN FOR r IN (SELECT acc_no FROM acct WHERE NOT (status IN ('A', 'B'))) LOOP "
             "DELETE FROM acct WHERE acc_no = r.acc_no; END LOOP; END;", "status", "NOT (...)"),
            ("BEGIN FOR r IN (SELECT acc_no FROM acct WHERE status IN ('A', 'B')) LOOP "
             "DELETE FROM acct WHERE acc_no = r.acc_no; END LOOP; END;", "status", None),
            ("BEGIN DELETE FROM acct WHERE acc_no IN (SELECT acc_no FROM acct WHERE status "
             "IN ('A', 'B') GROUP BY acc_no HAVING COUNT(*) = 1); END;", "status", "GROUP"),
            ("BEGIN CASE WHEN 1 = 1 THEN DELETE FROM acct WHERE NOT (n IN (1, 2)); "
             "END CASE; END;", "n", "NOT (...)"),
        ]
        for sql, column, reason in refused:
            self.assertFalse(GUI._is_pure_select(sql, list(app._scan_sql(sql))))
            self.assert_refused(sql, column, reason)
        # a positive DELETE inside a block (incl. a PL/SQL CASE statement) resets
        for sql, column, expected in (
            ("BEGIN DELETE FROM acct WHERE status IN ('A', 'B'); END;", "status",
             "BEGIN DELETE FROM acct WHERE 1=0; END;"),
            ("BEGIN DELETE FROM acct WHERE grp IN (SELECT code FROM lkp "
             "WHERE seg IN ('CORP')); END;", "seg",
             "BEGIN DELETE FROM acct WHERE grp IN (SELECT code FROM lkp WHERE 1=0); END;"),
            ("BEGIN CASE WHEN 1 = 1 THEN DELETE FROM acct WHERE n IN (1, 2); END CASE; END;",
             "n", "BEGIN CASE WHEN 1 = 1 THEN DELETE FROM acct WHERE 1=0; END CASE; END;"),
        ):
            with self.subTest(sql=sql):
                self.assertEqual(norm(reset(sql, column)), expected)

    def test_known_limit_plsql_control_flow_negation(self):
        """Former KNOWN LIMIT (B), fixed in R2-T-fix2 (user approved): a list
        whose result drives PL/SQL control flow (SELECT ... INTO, IF
        condition) is refused, partial or full."""
        for sql, column, expected in (
            ("DECLARE v NUMBER; BEGIN SELECT COUNT(*) INTO v FROM acct WHERE status IN "
             "('A', 'B'); IF v = 0 THEN DELETE FROM acct; END IF; END;", "status",
             "SELECT ... INTO"),
            ("BEGIN IF v_run = 1 AND v_type IN ('A', 'B') THEN NULL; ELSE DELETE FROM acct; "
             "END IF; END;", "v_type", "PL/SQL IF / ELSIF condition"),
        ):
            for remove in (None, {"'A'"}):
                with self.subTest(sql=sql, remove=remove):
                    with self.assertRaises(ValueError) as ctx:
                        reset(sql, column, remove)
                    self.assertIn(expected, str(ctx.exception))

    def test_merge(self):
        on = ("MERGE INTO acct t USING lkp s ON (t.grp = s.code AND s.seg IN ('CORP', 'RETAIL')) "
              "WHEN NOT MATCHED THEN INSERT (acc_no) VALUES (s.code)")
        self.assert_refused(on, "s.seg")
        using = ("MERGE INTO acct t USING (SELECT * FROM lkp WHERE seg IN ('CORP', 'RETAIL')) s "
                 "ON (t.grp = s.code) WHEN NOT MATCHED THEN INSERT (acc_no) VALUES (s.code)")
        self.assert_refused(using, "seg", "USING")
        case = ("MERGE INTO acct t USING lkp s ON (t.grp = s.code) WHEN MATCHED THEN UPDATE "
                "SET t.flag = 'X' WHERE CASE WHEN s.seg IN ('CORP', 'RETAIL') THEN 0 ELSE 1 "
                "END = 1")
        self.assert_refused(case, "s.seg", "CASE")
        # WHEN MATCHED THEN is not a CASE: the update / delete filter resets
        for sql in (
            "MERGE INTO acct t USING lkp s ON (t.grp = s.code) WHEN MATCHED THEN UPDATE "
            "SET t.flag = 'X' WHERE s.seg IN ('CORP', 'RETAIL')",
            "MERGE INTO acct t USING lkp s ON (t.grp = s.code) WHEN MATCHED THEN UPDATE "
            "SET t.flag = 'X' DELETE WHERE s.seg IN ('CORP', 'RETAIL')",
        ):
            with self.subTest(sql=sql):
                self.assertIn("WHERE s.seg IN ('RETAIL')", reset(sql, "s.seg", {"'CORP'"}))
                self.assertTrue(norm(reset(sql, "s.seg")).endswith("WHERE 1=0"))


class PureSelectRoundTwoTests(InvariantMixin, unittest.TestCase):
    """Pure SELECT (user decision): inline views, CTEs and select-list
    subqueries reset again (partial and full); emptied NOT forms refused."""
    CASES = [
        ("WITH a AS (SELECT * FROM acct WHERE status IN ('A', 'B')), b AS (SELECT * FROM a "
         "WHERE grp IN (SELECT code FROM lkp WHERE seg IN ('CORP', 'RETAIL'))) SELECT * FROM b",
         "seg", 3, (2, 1, 0)),
        ("WITH a AS (SELECT * FROM acct WHERE status IN ('A', 'B')) SELECT * FROM a",
         "status", 3, (1, 2, 0)),
        ("select v.acc_no from (select x.* from acct x join lkp l on l.code = x.grp "
         "and l.seg in ('CORP', 'RETAIL')) v where v.flag = 'N'", "l.seg", 3, (2, 1, 0)),
        ("SELECT acc_no, (SELECT COUNT(*) FROM lkp WHERE code = grp AND seg IN "
         "('CORP', 'RETAIL')) AS c FROM acct", "seg", 4, (4, 4, 4)),
        ("SELECT 'DELETE' AS op, upd FROM (SELECT acc_no, flag AS upd FROM acct "
         "WHERE status IN ('A', 'B')) v", "status", 3, (1, 2, 0)),
    ]

    def test_partial_and_full_reset_rows(self):
        for sql, column, before, (drop_first, drop_second, drop_all) in self.CASES:
            with self.subTest(sql=sql):
                self.assertTrue(GUI._is_pure_select(sql, list(app._scan_sql(sql))))
                self.assertEqual(affected(self, sql), before)
                tokens = detect(sql)[index_of(sql, column)]["tokens"]
                self.assertEqual(affected(self, reset(sql, column, {tokens[0]})), drop_first)
                self.assertEqual(affected(self, reset(sql, column, {tokens[1]})), drop_second)
                full = reset(sql, column)
                self.assertIn("1=0", full)
                self.assertEqual(affected(self, full), drop_all)

    def test_comments_and_strings_do_not_make_it_a_write(self):
        sql = ("-- delete old rows first\nSELECT 'UPDATE' AS x FROM (SELECT * FROM acct "
               "WHERE status IN ('A', 'B') /* insert into later */) v")
        self.assertTrue(GUI._is_pure_select(sql, list(app._scan_sql(sql))))
        self.assertIn("IN ('B')", reset(sql, "status", {"'A'"}))

    def test_emptied_not_forms_refused(self):
        for sql, column in (
            ("WITH x AS (SELECT * FROM acct WHERE NOT EXISTS (SELECT 1 FROM lkp "
             "WHERE code = grp AND seg IN ('CORP', 'RETAIL'))) SELECT * FROM x", "seg"),
            ("SELECT * FROM (SELECT * FROM acct WHERE NOT (status IN ('A', 'B'))) v", "status"),
            ("SELECT acc_no, (SELECT 1 FROM lkp WHERE code NOT IN (SELECT code FROM lkp "
             "WHERE seg IN ('CORP', 'RETAIL')) LIMIT 1) FROM acct", "seg"),
            ("SELECT * FROM acct WHERE status NOT IN ('A', 'B')", "status"),
        ):
            with self.subTest(sql=sql):
                with self.assertRaises(ValueError) as ctx:
                    reset(sql, column)
                self.assertIn("every row", str(ctx.exception))
                # partial removal stays allowed in a pure SELECT
                first = detect(sql)[index_of(sql, column)]["tokens"][0]
                self.assertNotIn(first, reset(sql, column, {first}))


class RealisticWriteUsabilityTests(unittest.TestCase):
    """OFSAA-style statements that write, positive nesting: still reset."""
    CASES = [
        ("DELETE FROM FCT_ACCT t WHERE t.FIC_MIS_DATE = DATE '2024-01-31' AND EXISTS "
         "(SELECT 1 FROM DIM_RUN r WHERE r.N_RUN_SKEY = t.N_RUN_SKEY AND r.V_RUN_TYPE "
         "IN ('C', 'D'))", "r.V_RUN_TYPE"),
        ("INSERT INTO STG_ACCT (ACC, SEG) SELECT a.ACC, b.SEG FROM ACCT a JOIN LKP b "
         "ON b.CODE = a.GRP AND b.SEG IN ('C', 'D') WHERE a.FIC_MIS_DATE = DATE '2024-01-31'",
         "b.SEG"),
        ("INSERT INTO STG_ACCT SELECT a.ACC FROM ACCT a LEFT JOIN LKP b ON b.CODE = a.GRP "
         "WHERE a.STATUS IN ('C', 'D')", "a.STATUS"),
        ("DELETE FROM ACCT WHERE ACC IN (SELECT a.ACC FROM ACCT a LEFT JOIN LKP b "
         "ON b.CODE = a.GRP WHERE a.STATUS IN ('C', 'D'))", "a.STATUS"),
        ("UPDATE FCT_ACCT t SET t.F_FLAG = 'Y' WHERE t.N_CUST_SKEY IN (SELECT c.N_CUST_SKEY "
         "FROM DIM_CUST c WHERE c.V_TYPE IN ('C', 'D')) AND t.FIC_MIS_DATE = DATE '2024-01-31'",
         "c.V_TYPE"),
        ("MERGE INTO FCT_ACCT t USING STG_ACCT s ON (t.ACC = s.ACC) WHEN MATCHED THEN "
         "UPDATE SET t.BAL = s.BAL WHERE s.V_TYPE IN ('C', 'D')", "s.V_TYPE"),
        ("DELETE FROM FCT_ACCT t WHERE CASE WHEN t.N_DAYS > 30 THEN 1 ELSE 0 END = 1 "
         "AND t.N_RUN_SKEY IN (SELECT N_RUN_SKEY FROM DIM_RUN WHERE V_RUN_TYPE IN ('C', 'D'))",
         "V_RUN_TYPE"),
    ]

    def test_partial_and_full_reset_allowed(self):
        for sql, column in self.CASES:
            with self.subTest(sql=sql):
                self.assertIn("('D')", reset(sql, column, {"'C'"}))
                self.assertIn("1=0", reset(sql, column))


class DialogRoundTwoTests(DetectedDialogFlowTests):
    REFUSED = [
        ("DELETE FROM acct WHERE CASE WHEN EXISTS (SELECT 1 FROM lkp WHERE code = grp "
         "AND seg IN ('C', 'D')) OR 1 = 2 THEN 0 ELSE 1 END = 1", "seg", "CASE"),
        ("INSERT INTO tgt SELECT grp FROM acct WHERE status IN ('C', 'D') GROUP BY grp "
         "HAVING COUNT(*) = 1", "status", "HAVING"),
        ("INSERT INTO tgt SELECT acc_no FROM acct EXCEPT SELECT acc_no FROM acct "
         "WHERE status IN ('C', 'D')", "status", "after EXCEPT"),
        ("DELETE FROM acct WHERE acc_no IN (SELECT a.acc_no FROM lkp b JOIN acct x "
         "ON x.grp = b.code AND b.seg IN ('C', 'D') RIGHT JOIN acct a ON a.acc_no = x.acc_no "
         "WHERE x.acc_no IS NULL)", "b.seg", "outer"),
    ]

    def test_positive_nesting_preview_equals_applied(self):
        """Pure SELECT inline view: partial reset previewed and applied."""
        sql = "SELECT * FROM (SELECT * FROM acct WHERE status IN ('C', 'D')) v"
        stub, env, mb, preview = self.run_dialog(sql, "status", {"'C'"})
        mb.showerror.assert_not_called()
        self.assertEqual(norm(preview),
                         "SELECT * FROM (SELECT * FROM acct WHERE status IN ('D')) v")
        self.assertEqual(stub.sql_context.content, preview)

    def test_new_wording_renders(self):
        """Header and detected-mode footer labels of the real dialog (Tk mocked)."""
        stub = GUI.__new__(GUI)
        stub.sql_context = _Text("DELETE FROM acct WHERE status IN ('A', 'B')")
        stub._excel_parameter_values = {}
        stub.root = mock.MagicMock(name="root")
        tk_mock = mock.MagicMock(name="tk")
        tk_mock.END = "end"
        tk_mock.StringVar.return_value.get.return_value = ""
        pair = lambda *a, **k: (mock.MagicMock(), mock.MagicMock())  # noqa: E731
        with mock.patch.object(app, "tk", tk_mock), \
                mock.patch.object(app, "ui_button", pair), \
                mock.patch.object(app, "ui_round_frame", pair), \
                mock.patch.object(app, "messagebox") as mb:
            stub.show_reset_parameter_dialog()
        mb.showwarning.assert_not_called()
        texts = [c.kwargs.get("text") for c in tk_mock.Label.call_args_list]
        header = next(t for t in texts if t and t.startswith("เลือกคอลัมน์ แล้วติ๊กค่า"))
        self.assertIn("IN-list ที่เอาออกครบจะกลายเป็น 1=0", header)
        self.assertIn("ถ้า Reset แล้วอาจกระทบแถวมากขึ้นใน UPDATE/DELETE/INSERT/MERGE "
                      "จะ Reset ไม่ได้", header)
        self.assertNotIn("ไม่กระทบแถวใด", header)
        footer = next(t for t in texts if t and t.startswith("ค่าจาก IN (...) ใน SQL"))
        self.assertIn("UPDATE/DELETE/INSERT/MERGE จะ Reset ไม่ได้", footer)
        self.assertNotIn("ไม่กระทบแถวใด", footer)
        readme = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                              "README.md")
        with open(readme, encoding="utf-8") as handle:
            text = handle.read()
        self.assertIn("ถ้า Reset แล้วอาจกระทบแถวมากขึ้นใน UPDATE/DELETE/INSERT/MERGE "
                      "จะ Reset ไม่ได้", text)


if __name__ == "__main__":
    unittest.main()
