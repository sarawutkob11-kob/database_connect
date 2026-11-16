"""Unit tests for the pure helpers in database_connect_gui (no GUI, no database).

Run:  python -m unittest discover -s tests -p "test_*.py"
"""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import database_connect_gui as app  # noqa: E402
from database_connect_gui import SqlRisk, assess_sql, split_sql_statements  # noqa: E402


class SqlClassificationTests(unittest.TestCase):
    def assertRisk(self, sql, risk, count=1, command=None):
        result = assess_sql(sql)
        self.assertEqual(result.risk, risk, f"{sql!r} -> {result}")
        self.assertEqual(result.statement_count, count, f"{sql!r} -> {result}")
        if command is not None:
            self.assertEqual(result.command, command)

    def test_line_comment_then_select(self):
        self.assertRisk("-- comment\nSELECT 1;", SqlRisk.READ_ONLY, command="SELECT")

    def test_block_comment_and_semicolon_in_string(self):
        self.assertRisk("/* comment */ SELECT ';' AS value;", SqlRisk.READ_ONLY)

    def test_cte_select(self):
        self.assertRisk("WITH x AS (SELECT 1 AS id) SELECT * FROM x;", SqlRisk.READ_ONLY)

    def test_cte_delete_is_not_read_only(self):
        self.assertRisk(
            "WITH x AS (SELECT 1 AS id) DELETE FROM target WHERE id IN (SELECT id FROM x);",
            SqlRisk.DATA_CHANGE,
            command="DELETE",
        )

    def test_cte_update_is_not_read_only(self):
        self.assertRisk(
            "WITH x AS (SELECT 1 AS id) UPDATE target SET flag = 1;",
            SqlRisk.DATA_CHANGE,
            command="UPDATE",
        )

    def test_keyword_inside_string_is_ignored(self):
        self.assertRisk("SELECT 'DELETE FROM x' AS text", SqlRisk.READ_ONLY)

    def test_plsql_block_is_one_unknown_statement(self):
        sql = "BEGIN\n  UPDATE target SET flag = 1;\nEND;\n/\n"
        self.assertRisk(sql, SqlRisk.UNKNOWN, command="BEGIN")

    def test_multi_statement_detected_with_worst_risk(self):
        self.assertRisk("SELECT 1; DELETE FROM target;", SqlRisk.DATA_CHANGE, count=2)

    def test_oracle_slash_terminator(self):
        self.assertRisk("SELECT * FROM dual\n/", SqlRisk.READ_ONLY)

    def test_doubled_quote_escape(self):
        self.assertRisk("SELECT * FROM t WHERE n = 'O''Brien; DROP'", SqlRisk.READ_ONLY)

    def test_quoted_identifiers(self):
        self.assertRisk('SELECT "a;b", [c;d], `e;f` FROM t', SqlRisk.READ_ONLY)

    def test_parenthesized_select(self):
        self.assertRisk("(SELECT 1) UNION (SELECT 2)", SqlRisk.READ_ONLY)

    def test_dml(self):
        for cmd in ("INSERT INTO t VALUES (1)", "UPDATE t SET a=1", "DELETE FROM t",
                    "MERGE INTO t USING s ON (1=1) WHEN MATCHED THEN UPDATE SET a=1"):
            self.assertRisk(cmd, SqlRisk.DATA_CHANGE)

    def test_ddl(self):
        for cmd in ("CREATE TABLE t (id INT)", "ALTER TABLE t ADD c INT", "DROP TABLE t",
                    "TRUNCATE TABLE t", "COMMENT ON TABLE t IS 'x'",
                    "CREATE OR REPLACE VIEW v AS SELECT 1 FROM dual"):
            self.assertRisk(cmd, SqlRisk.SCHEMA_CHANGE)

    def test_admin(self):
        for cmd in ("ALTER SYSTEM SET x=1", "DROP DATABASE d", "CREATE USER u IDENTIFIED BY p",
                    "DROP USER u", "GRANT SELECT ON t TO u", "REVOKE SELECT ON t FROM u",
                    "SHUTDOWN"):
            self.assertRisk(cmd, SqlRisk.ADMIN)

    def test_procedure_calls_are_unknown(self):
        for cmd in ("CALL p()", "EXEC p", "EXECUTE p", "DECLARE x NUMBER; BEGIN NULL; END;"):
            self.assertRisk(cmd, SqlRisk.UNKNOWN)

    def test_create_procedure_body_is_one_statement(self):
        sql = (
            "CREATE OR REPLACE PROCEDURE p AS\nBEGIN\n  UPDATE t SET a = 1;\n"
            "  COMMIT;\nEND;\n/"
        )
        self.assertRisk(sql, SqlRisk.SCHEMA_CHANGE)

    def test_create_table_with_type_column_still_splits(self):
        self.assertRisk("CREATE TABLE t (type VARCHAR2(10)); DROP TABLE x", SqlRisk.SCHEMA_CHANGE, count=2)

    def test_begin_transaction_is_not_a_block(self):
        # BEGIN is UNKNOWN, which ranks riskier than the DELETE
        self.assertRisk("BEGIN; DELETE FROM t", SqlRisk.UNKNOWN, count=2)

    def test_select_into_creates_table(self):
        self.assertRisk("SELECT * INTO new_t FROM t", SqlRisk.SCHEMA_CHANGE)

    def test_select_for_update_is_select(self):
        self.assertRisk("SELECT * FROM t FOR UPDATE", SqlRisk.READ_ONLY)

    def test_explain_variants(self):
        self.assertRisk("EXPLAIN SELECT 1", SqlRisk.READ_ONLY)
        self.assertRisk("EXPLAIN ANALYZE DELETE FROM t", SqlRisk.UNKNOWN)
        self.assertRisk("EXPLAIN PLAN FOR SELECT 1 FROM dual", SqlRisk.UNKNOWN)

    def test_show_and_describe(self):
        self.assertRisk("SHOW TABLES", SqlRisk.READ_ONLY)
        self.assertRisk("DESCRIBE t", SqlRisk.READ_ONLY)

    def test_empty_and_comment_only(self):
        self.assertEqual(assess_sql("").statement_count, 0)
        self.assertEqual(assess_sql("-- nothing\n/* here */").statement_count, 0)

    def test_postgres_dollar_quote(self):
        self.assertRisk("SELECT $$a; DELETE$$ AS x", SqlRisk.READ_ONLY)

    def test_split_keeps_original_text(self):
        self.assertEqual(
            split_sql_statements("SELECT 'a;b' FROM t;\nSELECT 2;"),
            ["SELECT 'a;b' FROM t", "SELECT 2"],
        )


class IsSelectQueryCompatTests(unittest.TestCase):
    """is_select_query keeps its contract (True = run as a result set)."""

    def is_select(self, sql):
        return app.DatabaseConnectorGUI.is_select_query(None, sql)

    def test_previous_true_cases_still_true(self):
        for sql in ("SELECT 1", "  select * from t", "WITH a AS (SELECT 1) SELECT * FROM a",
                    "(SELECT 1)", "-- c\nSELECT 1"):
            self.assertTrue(self.is_select(sql), sql)

    def test_previous_false_cases_still_false(self):
        for sql in ("UPDATE t SET a=1", "INSERT INTO t VALUES (1)", "DELETE FROM t", "CALL p()"):
            self.assertFalse(self.is_select(sql), sql)

    def test_fixed_cases(self):
        self.assertTrue(self.is_select("/* c */ SELECT 1"))
        self.assertFalse(self.is_select("WITH a AS (SELECT 1) DELETE FROM t"))


class TableVariableTests(unittest.TestCase):
    TABLES = {
        "Accounts": {"column_data": {"ACCOUNT NO": ["A1", "O'Brien", "A1"], "AMT": [1, 2.5]}},
        "my_tbl": {"column_data": {"col_x": [7]}},
    }

    def test_variable_name_matches_insert_dialog(self):
        self.assertEqual(app.table_variable_name("Accounts", "ACCOUNT NO"), "{TABLE_ACCOUNTS_ACCOUNT_NO}")

    def test_replaces_all_occurrences_and_escapes_once(self):
        sql = "SELECT * FROM t WHERE a IN ({TABLE_ACCOUNTS_ACCOUNT_NO}) OR b IN ({TABLE_ACCOUNTS_ACCOUNT_NO})"
        result = app.render_table_variables(sql, self.TABLES)
        self.assertTrue(result.ok)
        expected = "'A1', 'O''Brien', 'A1'"
        self.assertEqual(result.sql.count(expected), 2)
        self.assertNotIn("O'''", result.sql)
        self.assertEqual(result.replaced_tokens, ("{TABLE_ACCOUNTS_ACCOUNT_NO}",))

    def test_numbers_stay_numeric(self):
        result = app.render_table_variables("x IN ({TABLE_ACCOUNTS_AMT})", self.TABLES)
        self.assertEqual(result.sql, "x IN (1, 2.5)")

    def test_none_becomes_null(self):
        result = app.render_table_variables("{TABLE_T_C}", {"t": {"column_data": {"c": ["a", None]}}})
        self.assertEqual(result.sql, "'a', NULL")

    def test_underscore_names_resolved_by_metadata(self):
        result = app.render_table_variables("{TABLE_MY_TBL_COL_X}", self.TABLES)
        self.assertEqual(result.sql, "7")

    def test_token_like_text_is_not_replaced(self):
        sql = "SELECT 'TABLE_ACCOUNTS_AMT', {TABLE_ACCOUNTS_AMT}x FROM t"
        result = app.render_table_variables(sql, self.TABLES)
        self.assertEqual(result.sql, "SELECT 'TABLE_ACCOUNTS_AMT', 1, 2.5x FROM t")

    def test_ambiguous_token_fails_without_change(self):
        tables = {"A_B": {"column_data": {"C": [1]}}, "A": {"column_data": {"B_C": [2]}}}
        sql = "SELECT {TABLE_A_B_C}"
        result = app.render_table_variables(sql, tables)
        self.assertFalse(result.ok)
        self.assertEqual(result.ambiguous_tokens, ("{TABLE_A_B_C}",))
        self.assertEqual(result.sql, sql)

    def test_missing_token_fails_atomically(self):
        sql = "SELECT {TABLE_ACCOUNTS_AMT}, {TABLE_NOPE_X}"
        result = app.render_table_variables(sql, self.TABLES)
        self.assertFalse(result.ok)
        self.assertEqual(result.missing_tokens, ("{TABLE_NOPE_X}",))
        self.assertEqual(result.sql, sql)

    def test_empty_values_count_as_missing(self):
        result = app.render_table_variables("{TABLE_T_C}", {"t": {"column_data": {"c": []}}})
        self.assertFalse(result.ok)

    def test_template_survives_repeated_syncs(self):
        template = "SELECT * FROM t WHERE id IN ({TABLE_T_C})"
        first = app.render_table_variables(template, {"t": {"column_data": {"c": [1]}}})
        second = app.render_table_variables(template, {"t": {"column_data": {"c": [2, 3]}}})
        self.assertEqual(first.sql, "SELECT * FROM t WHERE id IN (1)")
        self.assertEqual(second.sql, "SELECT * FROM t WHERE id IN (2, 3)")
        self.assertEqual(template, "SELECT * FROM t WHERE id IN ({TABLE_T_C})")

    def test_find_table_variables(self):
        self.assertEqual(
            app.find_table_variables("{TABLE_A_B} {TABLE_C_D} {TABLE_A_B}"),
            ("{TABLE_A_B}", "{TABLE_C_D}"),
        )

    def test_no_tables_means_all_missing(self):
        result = app.render_table_variables("{TABLE_A_B}", None)
        self.assertEqual(result.missing_tokens, ("{TABLE_A_B}",))


class _FakeText:
    def __init__(self, text=""):
        self.text = text
        self.log = []

    def insert(self, _index, value):
        self.log.append(value)

    def get(self, *_args):
        return self.text


class PrepareRunSqlTests(unittest.TestCase):
    """_prepare_run_sql fills variables / blocks multi-statement SQL without Tk."""

    def make_stub(self, tables):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        path = os.path.join(folder.name, "mail_table_data.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"timestamp": "T1", "tables": tables}, f)
        stub = type("Stub", (), {})()
        stub.results_text = _FakeText()
        stub.loaded_table_data = None
        stub.last_table_data_mtime = None
        stub.table_data_file = path
        stub._current_table_data_tables = (
            lambda: app.DatabaseConnectorGUI._current_table_data_tables(stub)
        )
        return stub

    def run_prepare(self, stub, jobs):
        errors = []
        original = app.messagebox.showerror
        app.messagebox.showerror = lambda *a, **k: errors.append(a)
        try:
            return app.DatabaseConnectorGUI._prepare_run_sql(stub, jobs), errors
        finally:
            app.messagebox.showerror = original

    def test_fills_variables_and_keeps_job_text(self):
        stub = self.make_stub({"t": {"column_data": {"c": ["x"]}}})
        job = {"name": "J", "query": "SELECT * FROM a WHERE c IN ({TABLE_T_C})"}
        prepared, errors = self.run_prepare(stub, [job])
        self.assertEqual(prepared, ["SELECT * FROM a WHERE c IN ('x')"])
        self.assertEqual(errors, [])
        self.assertIn("{TABLE_T_C}", job["query"])

    def test_missing_variable_blocks_run(self):
        stub = self.make_stub({})
        prepared, errors = self.run_prepare(stub, [{"name": "J", "query": "SELECT {TABLE_X_Y}"}])
        self.assertIsNone(prepared)
        self.assertEqual(len(errors), 1)

    def test_multi_statement_blocked(self):
        stub = self.make_stub({})
        prepared, errors = self.run_prepare(stub, [{"name": "J", "query": "SELECT 1; DELETE FROM t"}])
        self.assertIsNone(prepared)
        self.assertIn("more than one", errors[0][1])

    def test_plain_sql_passes_unchanged(self):
        stub = self.make_stub({})
        sql = "SELECT * FROM t;\n"
        prepared, errors = self.run_prepare(stub, [{"name": None, "query": sql}])
        self.assertEqual(prepared, [sql])
        self.assertEqual(errors, [])


class QueryTemplateValidationTests(unittest.TestCase):
    def test_valid_file(self):
        data = {"Lookup": {"query": "SELECT 1", "created": "2026-01-01"}, "Reset": {"query": "UPDATE t SET a=1"}}
        templates, error = app.validate_query_templates(data)
        self.assertIsNone(error)
        self.assertEqual(templates, data)

    def test_rejects_whole_file_on_one_bad_entry(self):
        for bad in (
            [],
            {"": {"query": "SELECT 1"}},
            {"x" * 101: {"query": "SELECT 1"}},
            {"a": "SELECT 1"},
            {"a": {"query": ""}},
            {"a": {"query": 5}},
            {"a": {"query": "SELECT 1", "created": 5}},
            {"ok": {"query": "SELECT 1"}, "bad": {}},
            {"a": {"query": "x" * (app.MAX_TEMPLATE_SQL_LENGTH + 1)}},
            {f"t{i}": {"query": "SELECT 1"} for i in range(app.MAX_TEMPLATE_COUNT + 1)},
        ):
            templates, error = app.validate_query_templates(bad)
            self.assertIsNone(templates)
            self.assertTrue(error)

    def test_label_shows_category_without_changing_name(self):
        self.assertEqual(app.query_template_label("Customer", "SELECT 1"), "[READ ONLY] Customer")
        self.assertEqual(app.query_template_label("Reset", "UPDATE t SET a=1"), "[DATA CHANGE] Reset")
        self.assertEqual(app.query_template_label("Stg", "CREATE TABLE s (a INT)"), "[SCHEMA CHANGE] Stg")
        self.assertEqual(app.query_template_label("Two", "SELECT 1; SELECT 2"), "[MULTI-STATEMENT] Two")


class SqlServerDriverTests(unittest.TestCase):
    def test_driver_18_preferred(self):
        installed = ["SQL Server", "ODBC Driver 17 for SQL Server", "ODBC Driver 18 for SQL Server"]
        self.assertEqual(app.select_sqlserver_odbc_driver(installed), "ODBC Driver 18 for SQL Server")

    def test_driver_17_when_18_absent(self):
        installed = ["SQL Server", "ODBC Driver 17 for SQL Server"]
        self.assertEqual(app.select_sqlserver_odbc_driver(installed), "ODBC Driver 17 for SQL Server")

    def test_legacy_only_when_modern_absent(self):
        self.assertEqual(app.select_sqlserver_odbc_driver(["SQL Server Native Client 11.0", "SQL Server"]),
                         "SQL Server Native Client 11.0")
        self.assertEqual(app.select_sqlserver_odbc_driver(["Microsoft Access Driver", "SQL Server"]), "SQL Server")

    def test_case_insensitive_keeps_installed_spelling(self):
        self.assertEqual(app.select_sqlserver_odbc_driver(["odbc driver 17 for sql server"]),
                         "odbc driver 17 for sql server")

    def test_preferred_driver_from_settings(self):
        installed = ["SQL Server", "ODBC Driver 18 for SQL Server"]
        self.assertEqual(app.select_sqlserver_odbc_driver(installed, preferred="sql server"), "SQL Server")
        # preferred but not installed → normal priority
        self.assertEqual(app.select_sqlserver_odbc_driver(installed, preferred="Nope"),
                         "ODBC Driver 18 for SQL Server")

    def test_no_driver_lists_installed(self):
        with self.assertRaises(RuntimeError) as ctx:
            app.select_sqlserver_odbc_driver(["Microsoft Access Driver"])
        self.assertIn("Microsoft Access Driver", str(ctx.exception))

    def test_connect_string_legacy_driver(self):
        s = app.build_sqlserver_odbc_connect("SQL Server", "db1", "1433", "", "sa", "pw")
        self.assertEqual(s, "DRIVER={SQL Server};SERVER=db1,1433;DATABASE={master};UID={sa};PWD={pw}")

    def test_connect_string_modern_driver_encrypts(self):
        s = app.build_sqlserver_odbc_connect("ODBC Driver 18 for SQL Server", "h", "1433", "app", "u", "p")
        self.assertTrue(s.endswith(";Encrypt=yes;TrustServerCertificate=yes"))
        self.assertIn("DATABASE={app}", s)

    def test_special_characters_in_password(self):
        s = app.build_sqlserver_odbc_connect("SQL Server", "h", "1433", "d", "u", "a;b}c{=d")
        self.assertIn("PWD={a;b}}c{=d}", s)
        from urllib.parse import parse_qs, quote_plus
        url = "mssql+pyodbc:///?odbc_connect=" + quote_plus(s)
        self.assertEqual(parse_qs(url.split("?", 1)[1])["odbc_connect"][0], s)

    def test_get_connection_string_uses_detected_driver(self):
        import types
        fake = types.ModuleType("pyodbc")
        fake.drivers = lambda: ["SQL Server", "ODBC Driver 17 for SQL Server"]
        stub = type("Stub", (), {"_load_app_settings": lambda self: {}})()
        original = sys.modules.get("pyodbc")
        sys.modules["pyodbc"] = fake
        try:
            url = app.DatabaseConnectorGUI.get_connection_string(
                stub, "Microsoft SQL Server", "u", "p;w", "h", "1433", ""
            )
        finally:
            if original is None:
                sys.modules.pop("pyodbc", None)
            else:
                sys.modules["pyodbc"] = original
        from urllib.parse import parse_qs
        conn = parse_qs(url.split("?", 1)[1])["odbc_connect"][0]
        self.assertIn("DRIVER={ODBC Driver 17 for SQL Server}", conn)
        self.assertIn("DATABASE={master}", conn)
        self.assertIn("PWD={p;w}", conn)
        self.assertEqual(stub.sqlserver_odbc_driver, "ODBC Driver 17 for SQL Server")


class ConnectionTrackingTests(unittest.TestCase):
    def make_stub(self):
        import threading
        stub = type("Stub", (), {})()
        stub._active_db_connections = {}
        stub._active_db_lock = threading.Lock()
        return stub

    def track(self, stub, engine):
        app.DatabaseConnectorGUI._track_engine_connections(stub, engine)

    def test_checkout_and_checkin(self):
        from sqlalchemy import create_engine, text
        stub = self.make_stub()
        engine = create_engine("sqlite://")
        self.addCleanup(engine.dispose)
        self.track(stub, engine)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            self.assertEqual(len(stub._active_db_connections), 1)
        self.assertEqual(stub._active_db_connections, {})

    def test_new_engine_keeps_running_connection_of_old_engine(self):
        from sqlalchemy import create_engine
        stub = self.make_stub()
        old = create_engine("sqlite://")
        self.addCleanup(old.dispose)
        self.track(stub, old)
        conn = old.connect()
        new = create_engine("sqlite://")
        self.addCleanup(new.dispose)
        self.track(stub, new)  # reconnect while old one is busy
        self.assertEqual(len(stub._active_db_connections), 1)
        conn.close()
        self.assertEqual(stub._active_db_connections, {})

    def test_invalidated_connection_is_removed(self):
        from sqlalchemy import create_engine
        stub = self.make_stub()
        engine = create_engine("sqlite://")
        self.addCleanup(engine.dispose)
        self.track(stub, engine)
        conn = engine.connect()
        conn.invalidate()
        conn.close()
        self.assertEqual(stub._active_db_connections, {})


class StripSqlTerminatorTests(unittest.TestCase):
    def test_trailing_semicolon_removed_from_dml(self):
        self.assertEqual(app.strip_sql_terminator("UPDATE t SET a = 1;  \n"), "UPDATE t SET a = 1")

    def test_oracle_slash_line_removed(self):
        self.assertEqual(app.strip_sql_terminator("DELETE FROM t;\n/\n"), "DELETE FROM t")

    def test_plsql_block_keeps_end_semicolon(self):
        sql = "BEGIN\n  NULL;\nEND;\n/"
        self.assertEqual(app.strip_sql_terminator(sql), "BEGIN\n  NULL;\nEND;")

    def test_create_trigger_keeps_end_semicolon(self):
        sql = "CREATE OR REPLACE TRIGGER x BEFORE INSERT ON t FOR EACH ROW BEGIN :NEW.a := 1; END;"
        self.assertEqual(app.strip_sql_terminator(sql), sql)

    def test_block_comment_end_is_not_a_slash_terminator(self):
        self.assertEqual(app.strip_sql_terminator("UPDATE t SET a = 1 /* x */"), "UPDATE t SET a = 1 /* x */")


class ExecuteModificationTests(unittest.TestCase):
    def test_runs_raw_sql_without_bind_parsing(self):
        from sqlalchemy import create_engine
        stub = type("Stub", (), {})()
        stub.engine = create_engine("sqlite://")
        with stub.engine.connect() as conn:
            conn.exec_driver_sql("CREATE TABLE t (a TEXT)")
            conn.exec_driver_sql("INSERT INTO t VALUES ('x')")
            conn.commit()
        rows = app.DatabaseConnectorGUI._execute_modification(
            stub, "UPDATE t SET a = 'note :x and 50%';"
        )
        self.assertEqual(rows, 1)
        with stub.engine.connect() as conn:
            self.assertEqual(conn.exec_driver_sql("SELECT a FROM t").scalar(), "note :x and 50%")
        stub.engine.dispose()


class AtomicJsonTests(unittest.TestCase):
    def test_writes_and_leaves_no_temp_file(self):
        import json
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "jobs.json")
            app.write_json_atomic(path, [{"name": "ก"}])
            app.write_json_atomic(path, [{"name": "ข"}])
            with open(path, encoding="utf-8") as f:
                self.assertEqual(json.load(f), [{"name": "ข"}])
            self.assertEqual(os.listdir(folder), ["jobs.json"])

    def test_preserve_unreadable_file_makes_copy(self):
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "db_profiles.json")
            with open(path, "w", encoding="utf-8") as f:
                f.write("{broken")
            copy = app.preserve_unreadable_file(path)
            self.assertTrue(copy and os.path.exists(copy))
            with open(copy, encoding="utf-8") as f:
                self.assertEqual(f.read(), "{broken")


class ExcelValueTests(unittest.TestCase):
    def test_float_whole_number_drops_dot_zero(self):
        self.assertEqual(app.excel_value_text(1234.0), "1234")

    def test_other_values_unchanged(self):
        self.assertEqual(app.excel_value_text(12.5), "12.5")
        self.assertEqual(app.excel_value_text("0012"), "0012")
        self.assertEqual(app.excel_value_text(7), "7")

    def test_numpy_float_from_column_with_blanks(self):
        import io
        import pandas as pd
        buf = io.BytesIO()
        pd.DataFrame({"acct": [1234, None, 5678]}).to_excel(buf, index=False)
        buf.seek(0)
        values = pd.read_excel(buf)["acct"].dropna().tolist()
        self.assertEqual([app.excel_value_text(v) for v in values], ["1234", "5678"])

    def test_format_values_strips_quotes_on_both_ends(self):
        stub = type("Stub", (), {})()
        result = app.DatabaseConnectorGUI._format_excel_sql_values(stub, ["'ABC'", "O'Brien"])
        self.assertEqual(result, "'ABC', 'O''Brien'")


class ColonParameterTests(unittest.TestCase):
    def render(self, template, values):
        stub = app.DatabaseConnectorGUI.__new__(app.DatabaseConnectorGUI)
        stub.sql_template = template
        return stub._render_sql_template(values)

    def test_prefix_parameter_does_not_touch_longer_name(self):
        sql = self.render(
            "WHERE a IN (:ACC) AND b IN (:ACC_TYPE)", {"ACC": (":ACC", "'1', '2'")}
        )
        self.assertEqual(sql, "WHERE a IN ('1', '2') AND b IN (:ACC_TYPE)")

    def test_quoted_parameter_still_replaced(self):
        sql = self.render("WHERE a IN (':ACC')", {"ACC": (":ACC", "'1'")})
        self.assertEqual(sql, "WHERE a IN ('1')")


if __name__ == "__main__":
    unittest.main()
