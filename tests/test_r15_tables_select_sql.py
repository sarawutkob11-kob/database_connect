"""R15-T4 (BH-5): Tables double-click SQL uses the row's Schema, the db_type of
the Tables run, and quotes identifiers only when needed.

R15-AC-12, R15-AC-13, R15-AC-14, R15-AC-15, R15-AC-16 (Round 15). No Tk window,
no database: stub GUI from the Round 11 tests, threading.Thread captured and run
by hand, root.after callbacks run by hand, show_table_popup mocked so the
double-click callback can be called directly.
"""

import os
import sys
import unittest
from typing import Any, Callable, List, Optional
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import database_connect_gui as app  # noqa: E402
from test_r11_connection_target_snapshot import _Thread, make_stub  # noqa: E402

GUI = app.DatabaseConnectorGUI
ConnectionInfo = app.ConnectionInfo
RunTarget = app.RunTarget

ORACLE_INFO = ConnectionInfo(
    profile="P1", db_type="Oracle", user="hr", host="ora-db", port="1521",
    database="ORCLPDB",
)
ORACLE_SCREEN = dict(
    db_type="Oracle", db_user="hr", db_password="pw-ora", db_host="ora-db",
    db_port="1521", db_name="ORCLPDB",
)
MSSQL = "Microsoft SQL Server"


class _SqlEditor:
    def __init__(self) -> None:
        self.value = "old query"

    def delete(self, *_a: Any) -> None:
        self.value = ""

    def insert(self, _i: Any, value: str) -> None:
        self.value = value


# ------------------------------------------------------------- pure helper
class TablesSelectSqlTests(unittest.TestCase):
    def sql(self, db_type: str, row: tuple) -> str:
        return app._tables_select_sql(db_type, *row)

    # R15-AC-12
    def test_ac12_oracle_uses_schema_not_database(self):
        self.assertEqual(self.sql("Oracle", ("ORCLPDB", "hr", "employees")),
                         "SELECT * FROM hr.employees")

    # R15-AC-13
    def test_ac13_mysql_uses_schema_backticks(self):
        self.assertEqual(self.sql("MySQL", ("appdb", "sales", "orders")),
                         "SELECT * FROM `sales`.`orders`")

    # R15-AC-14
    def test_ac14_postgresql_and_sql_server(self):
        self.assertEqual(self.sql("PostgreSQL", ("mydb", "public", "orders")),
                         "SELECT * FROM public.orders")
        self.assertEqual(self.sql(MSSQL, ("db1", "dbo", "Orders")),
                         "SELECT * FROM [db1].[dbo].[Orders]")

    # R15-AC-15 (every value in the spec, in order)
    def test_ac15_special_names(self):
        cases = [
            ("Oracle", ("X", "hr", "My Table"), 'SELECT * FROM hr."My Table"'),
            ("PostgreSQL", ("d", "Sales", "Order Items"),
             'SELECT * FROM "Sales"."Order Items"'),
            ("PostgreSQL", ("d", "public", 'a"b'), 'SELECT * FROM public."a""b"'),
            ("PostgreSQL", ("d", "public", "order"), 'SELECT * FROM public."order"'),
            ("PostgreSQL", ("d", "public", 2024), 'SELECT * FROM public."2024"'),
            ("MySQL", ("d", "s", "a`b"), "SELECT * FROM `s`.`a``b`"),
            (MSSQL, ("db", "dbo", "t]x"), "SELECT * FROM [db].[dbo].[t]]x]"),
        ]
        for db_type, row, expected in cases:
            with self.subTest(db_type=db_type, row=row):
                self.assertEqual(self.sql(db_type, row), expected)

    def test_int_names_every_db_type(self):
        cases = [
            ("Oracle", (1, 2024, 7), 'SELECT * FROM "2024"."7"'),
            ("MySQL", (1, 2024, 7), "SELECT * FROM `2024`.`7`"),
            (MSSQL, (1, 2024, 7), "SELECT * FROM [1].[2024].[7]"),
            ("PostgreSQL", (1, 2024, 7), 'SELECT * FROM "2024"."7"'),
        ]
        for db_type, row, expected in cases:
            with self.subTest(db_type=db_type):
                self.assertEqual(self.sql(db_type, row), expected)

    def test_oracle_case_rules(self):
        # Oracle: lower case = unquoted (case-insensitive); upper/mixed case kept
        self.assertEqual(self.sql("Oracle", ("P", "hr", "employees")),
                         "SELECT * FROM hr.employees")
        self.assertEqual(self.sql("Oracle", ("P", "HR", "EMPLOYEES")),
                         'SELECT * FROM "HR"."EMPLOYEES"')
        self.assertEqual(self.sql("Oracle", ("P", "Hr", "Emp")),
                         'SELECT * FROM "Hr"."Emp"')
        # Oracle reserved word / leading digit / special char
        self.assertEqual(self.sql("Oracle", ("P", "hr", "select")),
                         'SELECT * FROM hr."select"')
        self.assertEqual(self.sql("Oracle", ("P", "hr", "1tab")),
                         'SELECT * FROM hr."1tab"')
        self.assertEqual(self.sql("Oracle", ("P", "hr", 'a"b')),
                         'SELECT * FROM hr."a""b"')

    def test_postgresql_more_quoting(self):
        cases = [
            (("d", "my schema", "t"), 'SELECT * FROM "my schema".t'),
            (("d", "public", "user"), 'SELECT * FROM public."user"'),
            (("d", "public", "select"), 'SELECT * FROM public."select"'),
            (("d", "public", "Orders"), 'SELECT * FROM public."Orders"'),
            (("d", "public", "a-b"), 'SELECT * FROM public."a-b"'),
            (("d", "public", "order_items"), "SELECT * FROM public.order_items"),
        ]
        for row, expected in cases:
            with self.subTest(row=row):
                self.assertEqual(self.sql("PostgreSQL", row), expected)

    def test_sql_server_bracket_everywhere(self):
        self.assertEqual(self.sql(MSSQL, ("a]b", "c]]d", "e f")),
                         "SELECT * FROM [a]]b].[c]]]]d].[e f]")

    def test_mysql_ignores_database_and_doubles_every_backtick(self):
        self.assertEqual(self.sql("MySQL", ("ignored`db", "s`", "``t")),
                         "SELECT * FROM `s```.`````t`")

    def test_empty_names_do_not_crash(self):
        self.assertEqual(self.sql(MSSQL, ("", "", "")), "SELECT * FROM [].[].[]")
        self.assertEqual(self.sql("MySQL", ("", "", "")), "SELECT * FROM ``.``")
        pg = self.sql("PostgreSQL", ("", "", "t"))
        self.assertTrue(pg.startswith("SELECT * FROM "))
        self.assertTrue(pg.endswith(".t"))

    # point 4: unknown db_type -> PostgreSQL rules
    def test_unknown_db_type_uses_postgresql_rules(self):
        rows = [
            ("mydb", "public", "orders"), ("d", "Sales", "Order Items"),
            ("d", "public", "order"), ("d", "public", 2024), ("d", "public", 'a"b'),
        ]
        for db_type in ("SQLite", "", "oracle", "mysql", "Unknown DB"):
            for row in rows:
                with self.subTest(db_type=db_type, row=row):
                    self.assertEqual(self.sql(db_type, row), self.sql("PostgreSQL", row))
        self.assertEqual(self.sql("SQLite", ("d", "public", "order")),
                         'SELECT * FROM public."order"')

    def test_quote_identifier_helper(self):
        q = app._quote_identifier_if_needed
        self.assertEqual(q("employees", "Oracle"), "employees")
        self.assertEqual(q("EMP", "Oracle"), '"EMP"')
        self.assertEqual(q("orders", "PostgreSQL"), "orders")
        self.assertEqual(q("Orders", "PostgreSQL"), '"Orders"')
        self.assertEqual(q(2024, "PostgreSQL"), '"2024"')
        self.assertEqual(q("order", "Whatever"), '"order"')

    def test_no_driver_import_needed(self):
        # Base dialects only: works even if oracledb / psycopg2 are missing
        blocked = {"oracledb": None, "cx_Oracle": None, "psycopg2": None}
        with mock.patch.dict(sys.modules, blocked):
            self.assertEqual(self.sql("Oracle", ("P", "hr", "employees")),
                             "SELECT * FROM hr.employees")
            self.assertEqual(self.sql("PostgreSQL", ("d", "public", "order")),
                             'SELECT * FROM public."order"')


# ------------------------------------------------------------- callback
class _CallbackBase(unittest.TestCase):
    def popup_callback(self, stub: Any, rows: List[tuple], *args: Any,
                       **kwargs: Any) -> Callable[[Any], None]:
        """Run the real on_list_tables_success; return the double-click callback."""
        stub.sql_context = _SqlEditor()
        stub.show_table_popup = mock.Mock()
        table_list = [{"Database": d, "Schema": s, "Table": t} for d, s, t in rows]
        with mock.patch.object(app, "messagebox"):
            GUI.on_list_tables_success(stub, table_list, mock.Mock(name="dlg"), *args,
                                       **kwargs)
        stub.show_table_popup.assert_called_once()
        return stub.show_table_popup.call_args.kwargs["on_double_click"]


class CallbackDbTypeTests(_CallbackBase):
    def test_db_type_keyword_wins_over_field(self):
        stub = make_stub(dict(ORACLE_SCREEN, db_type="MySQL"))
        cb = self.popup_callback(stub, [("ORCLPDB", "hr", "employees")], True,
                                 db_type="Oracle")
        cb(("ORCLPDB", "hr", "employees"))
        self.assertEqual(stub.sql_context.value, "SELECT * FROM hr.employees")
        self.assertIn("\n📝 Inserted query: SELECT * FROM hr.employees\n",
                      stub.results_text.inserted)

    # point 3: older callers (no db_type) read the field at double-click time
    def test_old_caller_without_db_type_reads_field(self):
        for field, expected in (
            ("MySQL", "SELECT * FROM `hr`.`employees`"),
            ("Oracle", "SELECT * FROM hr.employees"),
            (MSSQL, "SELECT * FROM [ORCLPDB].[hr].[employees]"),
        ):
            with self.subTest(field=field):
                stub = make_stub(dict(ORACLE_SCREEN, db_type="PostgreSQL"))
                cb = self.popup_callback(stub, [("ORCLPDB", "hr", "employees")], True)
                stub.db_type.value = field  # changed after the callback was built
                cb(("ORCLPDB", "hr", "employees"))
                self.assertEqual(stub.sql_context.value, expected)
                self.assertIn("db_type", stub._reads)

    def test_old_positional_two_args(self):
        stub = make_stub(dict(ORACLE_SCREEN, db_type="MySQL"))
        cb = self.popup_callback(stub, [("a", "s", "t")])
        cb(("a", "s", "t"))
        self.assertEqual(stub.sql_context.value, "SELECT * FROM `s`.`t`")

    def test_db_type_given_field_is_not_read(self):
        stub = make_stub(dict(ORACLE_SCREEN, db_type="MySQL"))
        cb = self.popup_callback(stub, [("ORCLPDB", "hr", "employees")], True,
                                 db_type="Oracle")
        stub.db_type.forbid_get = True
        cb(("ORCLPDB", "hr", "employees"))  # would raise if the field were read
        self.assertEqual(stub.sql_context.value, "SELECT * FROM hr.employees")

    def test_wrong_number_of_values_is_ignored(self):
        stub = make_stub()
        cb = self.popup_callback(stub, [("d", "s", "t")], True, db_type="PostgreSQL")
        cb(("s", "t"))
        self.assertEqual(stub.sql_context.value, "old query")

    def test_int_table_name_from_tk(self):
        stub = make_stub()
        cb = self.popup_callback(stub, [("d", "public", "2024")], True,
                                 db_type="PostgreSQL")
        cb(("d", "public", 2024))
        self.assertEqual(stub.sql_context.value, 'SELECT * FROM public."2024"')


# ------------------------------------------------------------- R15-AC-16 end to end
class ListTablesDbTypeSnapshotTests(_CallbackBase):
    def setUp(self) -> None:
        self.prints: List[str] = []

    def _print(self, *args: Any, **_kw: Any) -> None:
        self.prints.append(" ".join(str(a) for a in args))

    def run_tables(self, stub: Any) -> Any:
        threads: List[_Thread] = []

        def make_thread(target, args=(), daemon=None):
            thread = _Thread(target, args, daemon)
            threads.append(thread)
            return thread

        with mock.patch.object(app.threading, "Thread", side_effect=make_thread), \
                mock.patch.object(app, "messagebox"), \
                mock.patch("builtins.print", side_effect=self._print):
            stub.list_tables()
        self.assertEqual(len(threads), 1)
        inspector = mock.Mock(name="inspector")
        inspector.get_schema_names.return_value = ["hr"]
        inspector.get_table_names.return_value = ["employees"]
        with mock.patch.object(app, "inspect", return_value=inspector), \
                mock.patch.object(app, "create_engine", return_value=mock.MagicMock()), \
                mock.patch("builtins.print", side_effect=self._print):
            threads[0].run()
        for call in list(stub.root.after.call_args_list):
            if call.args and call.args[0] == 0:
                call.args[1]()
        stub.on_list_tables_error.assert_not_called()
        stub.on_list_tables_success.assert_called_once()
        return stub.on_list_tables_success.call_args

    def double_click(self, stub: Any, call: Any) -> str:
        self.assertEqual(call.args[0],
                         [{"Database": "ORCLPDB", "Schema": "hr", "Table": "employees"}])
        cb = self.popup_callback(stub, [("ORCLPDB", "hr", "employees")], *call.args[2:],
                                 **call.kwargs)
        cb(("ORCLPDB", "hr", "employees"))
        return stub.sql_context.value

    def test_ac16_snapshot_oracle_then_field_changed_to_mysql(self):
        stub = make_stub(dict(ORACLE_SCREEN, db_type="MySQL"))
        engine = mock.MagicMock(name="engine_ora")
        stub.engine = engine
        stub._run_target = RunTarget(engine, ORACLE_INFO)
        call = self.run_tables(stub)
        self.assertEqual(call.kwargs.get("db_type"), "Oracle")
        stub.db_type.value = "MySQL"
        self.assertEqual(self.double_click(stub, call), "SELECT * FROM hr.employees")

    def test_ac16_info_none_field_oracle_at_start_then_mysql(self):
        stub = make_stub(ORACLE_SCREEN)
        engine = mock.MagicMock(name="engine_ora")
        stub.engine = engine
        stub._run_target = RunTarget(engine, None)
        call = self.run_tables(stub)
        self.assertEqual(call.kwargs.get("db_type"), "Oracle")
        stub.db_type.value = "MySQL"  # changed before the double-click
        self.assertEqual(self.double_click(stub, call), "SELECT * FROM hr.employees")

    def test_list_tables_positional_args_unchanged(self):
        stub = make_stub(ORACLE_SCREEN)
        engine = mock.MagicMock(name="engine_ora")
        stub.engine = engine
        stub._run_target = RunTarget(engine, ORACLE_INFO)
        call = self.run_tables(stub)
        self.assertEqual(len(call.args), 3)
        self.assertIs(call.args[2], True)


if __name__ == "__main__":
    unittest.main()
