"""Focused QA for R2-T-fix2 PL/SQL and nested write reset rules."""

import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import test_r2_reset_nested_whitelist as nested
from test_r2_reset_nested_whitelist import (
    InvariantMixin,
    detect,
    index_of,
    norm,
    reset,
)
from test_r2_reset_parameter_qa import _Text

GUI = nested.GUI


class ResetRefusalTests(unittest.TestCase):
    def assert_refused(self, sql, column, reason):
        lists = detect(sql)
        index = index_of(sql, column)
        for selected in (None, {lists[index]["tokens"][0]}):
            with self.subTest(sql=sql, selected=selected):
                with self.assertRaises(ValueError) as context:
                    reset(sql, column, selected)
                self.assertIn(reason, str(context.exception))
                self.assertIn("could make the statement affect more rows", str(context.exception))

    def test_plsql_control_flow_and_unidentifiable_statements_refused(self):
        cases = [
            (
                "DECLARE v NUMBER; BEGIN SELECT COUNT(*) INTO v FROM acct "
                "WHERE status IN ('A', 'B'); END;",
                "status",
                "SELECT ... INTO",
            ),
            (
                "BEGIN SELECT COUNT(*) INTO v FROM acct WHERE status IN ('A', 'B'); "
                "DELETE FROM acct WHERE status = 'Z'; END;",
                "status",
                "SELECT ... INTO",
            ),
            (
                "DECLARE CURSOR c IS SELECT acc_no FROM acct WHERE status IN ('A', 'B'); "
                "BEGIN NULL; END;",
                "status",
                "cursor definition",
            ),
            (
                "BEGIN FOR r IN (SELECT acc_no FROM acct WHERE status IN ('A', 'B')) "
                "LOOP DELETE FROM acct WHERE acc_no = r.acc_no; END LOOP; END;",
                "status",
                "PL/SQL FOR loop / cursor",
            ),
            (
                "BEGIN IF status IN ('A', 'B') THEN NULL; END IF; END;",
                "status",
                "PL/SQL IF / ELSIF condition",
            ),
            (
                "BEGIN IF status = 'Z' THEN NULL; ELSIF status IN ('A', 'B') THEN NULL; "
                "END IF; END;",
                "status",
                "PL/SQL IF / ELSIF condition",
            ),
            (
                "BEGIN WHILE status IN ('A', 'B') LOOP NULL; END LOOP; END;",
                "status",
                "PL/SQL WHILE condition",
            ),
            (
                "BEGIN LOOP EXIT WHEN status IN ('A', 'B'); END LOOP; END;",
                "status",
                "PL/SQL EXIT / CONTINUE WHEN condition",
            ),
            (
                "BEGIN CASE WHEN status IN ('A', 'B') THEN NULL; ELSE NULL; END CASE; END;",
                "status",
                "PL/SQL CASE / WHEN condition",
            ),
            (
                "BEGIN CALL route(status IN ('A', 'B')); END;",
                "status",
                "statement that is not UPDATE / DELETE / INSERT / MERGE",
            ),
        ]
        for sql, column, reason in cases:
            with self.subTest(sql=sql):
                self.assert_refused(sql, column, reason)

    def test_previously_known_plsql_control_flow_cases_stay_refused(self):
        cases = [
            (
                "DECLARE v NUMBER; BEGIN SELECT COUNT(*) INTO v FROM acct WHERE status "
                "IN ('A', 'B'); IF v = 0 THEN DELETE FROM acct; END IF; END;",
                "status",
                "SELECT ... INTO",
            ),
            (
                "BEGIN IF v_run = 1 AND v_type IN ('A', 'B') THEN NULL; "
                "ELSE DELETE FROM acct; END IF; END;",
                "v_type",
                "PL/SQL IF / ELSIF condition",
            ),
        ]
        for sql, column, reason in cases:
            self.assert_refused(sql, column, reason)

    def test_nested_write_contexts_refuse_unsafe_wrappers(self):
        cases = [
            (
                "DELETE FROM acct WHERE grp IN (SELECT code FROM lkp WHERE NOT EXISTS "
                "(SELECT 1 FROM acct a WHERE a.grp = lkp.code AND status IN ('A', 'B')))",
                "status",
                "NOT EXISTS",
            ),
            (
                "DELETE FROM acct WHERE grp IN (SELECT code FROM lkp WHERE code NOT IN "
                "(SELECT grp FROM acct WHERE status IN ('A', 'B')))",
                "status",
                "NOT IN (subquery)",
            ),
            (
                "DELETE FROM acct WHERE grp IN (SELECT code FROM lkp WHERE code = ANY "
                "(SELECT grp FROM acct WHERE status IN ('A', 'B')))",
                "status",
                "quantified comparison",
            ),
            (
                "DELETE FROM acct WHERE grp IN (SELECT code FROM lkp WHERE code <> ALL "
                "(SELECT grp FROM acct WHERE status IN ('A', 'B')))",
                "status",
                "quantified comparison",
            ),
            (
                "DELETE FROM acct WHERE grp IN (SELECT code FROM lkp WHERE code = "
                "(SELECT grp FROM acct WHERE status IN ('A', 'B')))",
                "status",
                "compared scalar subquery",
            ),
            (
                "DELETE FROM acct WHERE grp IN (SELECT code FROM lkp WHERE CASE WHEN "
                "status IN ('A', 'B') THEN 1 ELSE 0 END = 1)",
                "status",
                "CASE",
            ),
            (
                "INSERT INTO tgt SELECT acc_no FROM acct EXCEPT SELECT acc_no FROM acct "
                "WHERE status IN ('A', 'B')",
                "status",
                "after EXCEPT",
            ),
            (
                "INSERT INTO tgt SELECT acc_no FROM acct MINUS SELECT acc_no FROM acct "
                "WHERE status IN ('A', 'B')",
                "status",
                "after MINUS",
            ),
        ]
        for sql, column, reason in cases:
            with self.subTest(sql=sql):
                self.assert_refused(sql, column, reason)

    def test_cte_requires_nonrecursive_independent_positive_references(self):
        cases = [
            (
                "WITH chosen AS (SELECT code FROM lkp WHERE seg IN ('CORP', 'RETAIL')) "
                "DELETE FROM acct WHERE grp NOT IN (SELECT code FROM chosen)",
                "seg",
                "NOT IN (subquery)",
            ),
            (
                "WITH chosen AS (SELECT code FROM lkp WHERE seg IN ('CORP', 'RETAIL')) "
                "DELETE FROM acct WHERE grp IN (SELECT code FROM chosen) OR NOT EXISTS "
                "(SELECT 1 FROM chosen c WHERE c.code = acct.grp)",
                "seg",
                "NOT EXISTS",
            ),
            (
                "WITH chosen AS (SELECT code FROM lkp WHERE seg IN ('CORP', 'RETAIL')) "
                "DELETE FROM acct WHERE NOT EXISTS (SELECT 1 FROM chosen c "
                "WHERE c.code = acct.grp)",
                "seg",
                "NOT EXISTS",
            ),
            (
                "WITH chosen AS (SELECT code FROM lkp WHERE seg IN ('CORP', 'RETAIL')) "
                "DELETE FROM acct WHERE grp = (SELECT code FROM chosen LIMIT 1)",
                "seg",
                "compared scalar subquery",
            ),
            (
                "WITH chosen AS (SELECT code FROM lkp WHERE seg IN ('CORP', 'RETAIL')) "
                "DELETE FROM acct WHERE EXISTS (SELECT 1 FROM acct a LEFT JOIN chosen c "
                "ON c.code = a.grp WHERE a.acc_no = acct.acc_no)",
                "seg",
                "outer",
            ),
            (
                "WITH chosen AS (SELECT code FROM lkp WHERE seg IN ('CORP', 'RETAIL')) "
                "DELETE FROM acct WHERE CASE WHEN EXISTS (SELECT 1 FROM chosen c "
                "WHERE c.code = acct.grp) THEN 1 ELSE 0 END = 1",
                "seg",
                "CASE",
            ),
            (
                "WITH RECURSIVE chosen(code) AS (SELECT code FROM lkp WHERE seg IN "
                "('CORP', 'RETAIL') UNION ALL SELECT code FROM chosen) "
                "DELETE FROM acct WHERE grp IN (SELECT code FROM chosen)",
                "seg",
                "recursive WITH",
            ),
            (
                "WITH chosen AS (SELECT code FROM lkp WHERE seg IN ('CORP', 'RETAIL')), "
                "derived AS (SELECT code FROM chosen) DELETE FROM acct WHERE grp IN "
                "(SELECT code FROM derived)",
                "seg",
                "another CTE",
            ),
            (
                "WITH chosen AS (SELECT code FROM lkp WHERE seg IN ('CORP', 'RETAIL')) "
                "INSERT INTO tgt SELECT code FROM lkp EXCEPT SELECT code FROM chosen",
                "seg",
                "after EXCEPT",
            ),
        ]
        for sql, column, reason in cases:
            with self.subTest(sql=sql):
                self.assert_refused(sql, column, reason)

    def test_merge_on_has_its_own_reason_and_text(self):
        sql = (
            "MERGE INTO acct t USING lkp s ON "
            "(t.grp = s.code AND s.seg IN ('CORP', 'RETAIL')) "
            "WHEN NOT MATCHED THEN INSERT (acc_no) VALUES (s.code)"
        )
        self.assert_refused(sql, "s.seg", "MERGE ON condition")
        with self.assertRaises(ValueError) as context:
            reset(sql, "s.seg")
        message = str(context.exception)
        self.assertIn("removing values can change which rows are matched / inserted", message)


class AllowedWriteResetTests(InvariantMixin, unittest.TestCase):
    def test_write_statements_inside_plsql_reset_only_statement_predicates(self):
        cases = [
            (
                "BEGIN DELETE FROM acct WHERE status IN ('A', 'B'); END;",
                "status",
                "BEGIN DELETE FROM acct WHERE 1=0; END;",
            ),
            (
                "BEGIN UPDATE acct SET flag = 'Y' WHERE status IN ('A', 'B'); END;",
                "status",
                "BEGIN UPDATE acct SET flag = 'Y' WHERE 1=0; END;",
            ),
            (
                "BEGIN INSERT INTO tgt SELECT acc_no FROM acct WHERE status IN "
                "('A', 'B'); END;",
                "status",
                "BEGIN INSERT INTO tgt SELECT acc_no FROM acct WHERE 1=0; END;",
            ),
            (
                "BEGIN DELETE FROM acct WHERE acc_no IN (SELECT a.acc_no FROM acct a "
                "JOIN lkp b ON b.code = a.grp AND b.seg IN ('CORP', 'RETAIL')); END;",
                "b.seg",
                "BEGIN DELETE FROM acct WHERE acc_no IN (SELECT a.acc_no FROM acct a "
                "JOIN lkp b ON b.code = a.grp AND 1=0); END;",
            ),
            (
                "BEGIN MERGE INTO acct t USING lkp s ON (t.grp = s.code) WHEN MATCHED "
                "THEN UPDATE SET t.flag = 'X' WHERE s.seg IN ('CORP', 'RETAIL'); END;",
                "s.seg",
                "BEGIN MERGE INTO acct t USING lkp s ON (t.grp = s.code) WHEN MATCHED "
                "THEN UPDATE SET t.flag = 'X' WHERE 1=0; END;",
            ),
        ]
        for sql, column, expected in cases:
            with self.subTest(sql=sql):
                item = detect(sql)[index_of(sql, column)]
                partial = reset(sql, column, {item["tokens"][0]})
                self.assertIn(item["tokens"][1], partial)
                self.assertEqual(norm(reset(sql, column)), norm(expected))

    def test_inner_and_comma_join_inline_views_and_parenthesised_joins_never_widen(self):
        cases = [
            "DELETE FROM acct WHERE acc_no IN (SELECT a.acc_no FROM acct a JOIN lkp b "
            "ON b.code = a.grp AND b.seg IN ('CORP', 'RETAIL'))",
            "DELETE FROM acct WHERE acc_no IN (SELECT a.acc_no FROM acct a, lkp b "
            "WHERE b.code = a.grp AND b.seg IN ('CORP', 'RETAIL'))",
            "DELETE FROM acct WHERE acc_no IN (SELECT v.acc_no FROM (SELECT x.acc_no "
            "FROM acct x JOIN lkp b ON b.code = x.grp WHERE b.seg IN ('CORP', 'RETAIL')) v)",
            "DELETE FROM acct WHERE acc_no IN (SELECT x.acc_no FROM (lkp b JOIN acct x "
            "ON x.grp = b.code) WHERE b.seg IN ('CORP', 'RETAIL'))",
            "INSERT INTO tgt SELECT x.acc_no FROM (lkp b JOIN acct x "
            "ON x.grp = b.code) WHERE b.seg IN ('CORP', 'RETAIL')",
            "UPDATE acct SET flag = 'X' WHERE acc_no IN (SELECT x.acc_no FROM acct x "
            "JOIN (lkp b JOIN lkp c ON c.code = b.code) ON b.code = x.grp "
            "WHERE b.seg IN ('CORP', 'RETAIL'))",
        ]
        for sql in cases:
            with self.subTest(sql=sql):
                self.assertIn("1=0", reset(sql, "b.seg"))
                self.assertGreater(self.assert_never_widens(sql), 0)

    def test_independent_nonrecursive_cte_with_positive_references_never_widens(self):
        statements = [
            "WITH chosen AS (SELECT code FROM lkp WHERE seg IN ('CORP', 'RETAIL')) "
            "DELETE FROM acct WHERE grp IN (SELECT code FROM chosen)",
            "WITH chosen AS (SELECT code FROM lkp WHERE seg IN ('CORP', 'RETAIL')) "
            "DELETE FROM acct WHERE grp IN (SELECT code FROM chosen) AND EXISTS "
            "(SELECT 1 FROM chosen c WHERE c.code = acct.grp)",
        ]
        for sql in statements:
            with self.subTest(sql=sql):
                self.assertIn("1=0", reset(sql, "seg"))
                self.assertGreater(self.assert_never_widens(sql), 0)


class ResetWordingTests(unittest.TestCase):
    def test_dialog_and_readme_warn_that_writes_may_be_affected(self):
        stub = GUI.__new__(GUI)
        stub.sql_context = _Text("DELETE FROM acct WHERE status IN ('A', 'B')")
        stub._excel_parameter_values = {}
        stub.root = mock.MagicMock(name="root")
        tk_mock = mock.MagicMock(name="tk")
        tk_mock.END = "end"
        tk_mock.StringVar.return_value.get.return_value = ""
        pair = lambda *args, **kwargs: (mock.MagicMock(), mock.MagicMock())
        with mock.patch.object(nested.app, "tk", tk_mock), \
                mock.patch.object(nested.app, "ui_button", pair), \
                mock.patch.object(nested.app, "ui_round_frame", pair), \
                mock.patch.object(nested.app, "messagebox") as messagebox:
            stub.show_reset_parameter_dialog()

        self.assertFalse(messagebox.showwarning.called)
        texts = [call.kwargs.get("text") for call in tk_mock.Label.call_args_list]
        header = next(text for text in texts if text and text.startswith("เลือกคอลัมน์ แล้วติ๊กค่า"))
        footer = next(text for text in texts if text and text.startswith("ค่าจาก IN (...) ใน SQL"))
        warning = "ถ้า Reset แล้วอาจกระทบแถวมากขึ้นใน UPDATE/DELETE/INSERT/MERGE จะ Reset ไม่ได้"
        self.assertIn(warning, header)
        self.assertIn("UPDATE/DELETE/INSERT/MERGE จะ Reset ไม่ได้", footer)
        self.assertNotIn("ไม่กระทบแถวใด", header)
        self.assertNotIn("ไม่กระทบแถวใด", footer)

        readme = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "README.md")
        with open(readme, encoding="utf-8") as handle:
            readme_text = handle.read()
        self.assertIn(warning, readme_text)
        self.assertNotIn("ไม่กระทบแถวใด", readme_text)


if __name__ == "__main__":
    unittest.main()