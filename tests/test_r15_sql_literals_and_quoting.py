"""QA for R15-T9 (BH-11, BH-12; R15-AC-30..35, R15-R8).

BH-11: Excel column names are quoted by db_type (MySQL backtick, others ").
BH-12: SQL literals from Excel / table data (dates, big floats, bool).

No Tk window (tk mocked / nested functions compiled from source), no real
database, Excel files only inside tempfile.TemporaryDirectory().
"""

import datetime as dt
import os
import sys
import tempfile
import unittest
import zipfile
from decimal import Decimal
from unittest import mock

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import database_connect_gui as app  # noqa: E402
from test_r2_reset_parameter_qa import _Text, compile_nested  # noqa: E402
from test_r15_reset_template_sync import CONFIRM, DialogHarness, make_main  # noqa: E402

GUI = app.DatabaseConnectorGUI
AUTO = "AUTO"


def norm(sql: str) -> str:
    return " ".join(sql.split())


class _Var:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


def info(db_type: str) -> "app.ConnectionInfo":
    return app.ConnectionInfo(profile="P", db_type=db_type, user="u", host="h",
                              port="1", database="d")


def make_stub(field=None, connected_db_type=None, connected_info_none=False,
              template="SELECT * FROM orders"):
    """GUI stub. field=None -> no db_type attribute at all."""
    stub = GUI.__new__(GUI)
    if field is not None:
        stub.db_type = _Var(field)
    if connected_db_type is not None or connected_info_none:
        engine = mock.Mock(name="engine")
        stub.engine = engine
        stub._run_target = app.RunTarget(
            engine, None if connected_info_none else info(connected_db_type))
    stub.sql_template = template
    stub._excel_parameter_values = {}
    stub._excel_parameterized_sql = None
    stub.sql_context = _Text(template)
    stub.debug_mode = _Var(False)
    return stub


def confirm_auto_where(stub, column_values: dict, ticked: dict, dataframe=None,
                       load_from_dataframe=False):
    """Run the real nested build_pending_values / apply_parameters of the
    Load Excel dialog in auto WHERE mode; returns the messagebox mock."""
    if dataframe is None:
        dataframe = pd.DataFrame({c: [] for c in column_values})
    column_lookup = {str(c): c for c in dataframe.columns}
    values_store = {} if load_from_dataframe else dict(column_values)
    env = {
        "self": stub,
        "parameter_var": _Var(AUTO),
        "auto_where_choice": AUTO,
        "column_selected": {c: set(v) for c, v in ticked.items()},
        "column_values": values_store,
        "column_lookup": column_lookup,
        "sheet_data": {"dataframe": dataframe},
        "column_var": _Var(next(iter(column_lookup))),
        "sheet_var": _Var("Sheet1"),
        "dialog": mock.MagicMock(name="excel_dialog"),
        "file_path": "book.xlsx",
    }
    funcs = compile_nested(
        GUI.load_excel_template_dialog,
        ("is_auto_where", "selected_of", "columns_with_selection", "load_column_values",
         "build_pending_values", "apply_parameters"),
        env,
    )
    if load_from_dataframe:
        for column in column_lookup:
            funcs["load_column_values"](column)
    with mock.patch.object(app, "messagebox") as mb:
        funcs["apply_parameters"]()
    return mb, values_store


# ======================================================================
# R15-AC-30: _sql_column_identifier by db_type
# ======================================================================
class AC30ColumnIdentifierTests(unittest.TestCase):
    Q = staticmethod(GUI._sql_column_identifier)

    def test_mysql_backticks(self):
        self.assertEqual(self.Q("Order Date", "MySQL"), "`Order Date`")
        self.assertEqual(self.Q("a`b", "MySQL"), "`a``b`")
        self.assertEqual(self.Q('a"b', "MySQL"), '`a"b`')

    def test_other_databases_double_quotes(self):
        for db in ("Oracle", "PostgreSQL", "Microsoft SQL Server", "", None):
            with self.subTest(db=db):
                self.assertEqual(self.Q("Order Date", db), '"Order Date"')
                self.assertEqual(self.Q('a"b', db), '"a""b"')

    def test_default_argument_is_double_quotes(self):
        self.assertEqual(self.Q("Order Date"), '"Order Date"')

    def test_plain_names_never_quoted(self):
        for db in ("MySQL", "Oracle", "PostgreSQL", "Microsoft SQL Server", None):
            for name in ("CUST_ID", "t.col", "s.t.c", "_x$1#"):
                with self.subTest(db=db, name=name):
                    self.assertEqual(self.Q(name, db), name)

    def test_surrounding_spaces_stripped(self):
        self.assertEqual(self.Q("  CUST_ID ", "MySQL"), "CUST_ID")
        self.assertEqual(self.Q(" Order Date ", "MySQL"), "`Order Date`")

    def test_non_string_header(self):
        self.assertEqual(self.Q(2024, "MySQL"), "`2024`")
        self.assertEqual(self.Q(2024, "Oracle"), '"2024"')


# ======================================================================
# R15-AC-31 / R15-Q-7: db_type source + Load Excel Confirm
# ======================================================================
class AC31DbTypeSourceTests(unittest.TestCase):
    def test_connected_snapshot_wins_over_field(self):
        stub = make_stub(field="Oracle", connected_db_type="MySQL")
        self.assertEqual(stub._sql_identifier_db_type(), "MySQL")
        stub = make_stub(field="MySQL", connected_db_type="Oracle")
        self.assertEqual(stub._sql_identifier_db_type(), "Oracle")

    def test_not_connected_uses_field(self):
        self.assertEqual(make_stub(field="MySQL")._sql_identifier_db_type(), "MySQL")
        self.assertEqual(make_stub(field="Oracle")._sql_identifier_db_type(), "Oracle")

    def test_engine_without_info_uses_field(self):
        stub = make_stub(field="MySQL", connected_info_none=True)
        self.assertEqual(stub._sql_identifier_db_type(), "MySQL")

    def test_stale_run_target_ignored(self):
        stub = make_stub(field="Oracle", connected_db_type="MySQL")
        stub.engine = mock.Mock(name="other_engine")  # reconnected without info
        self.assertEqual(stub._sql_identifier_db_type(), "Oracle")

    def test_stub_without_db_type_is_empty(self):
        self.assertEqual(make_stub(field=None)._sql_identifier_db_type(), "")


class AC31ConfirmTests(unittest.TestCase):
    def confirm(self, stub):
        mb, _ = confirm_auto_where(stub, {"Order Date": ["x", "y"]}, {"Order Date": ["x"]})
        mb.showwarning.assert_not_called()
        mb.showinfo.assert_called_once()
        return norm(stub.sql_context.content)

    def assert_backtick(self, sql, stub):
        self.assertIn("`Order Date` IN ('x')", sql)
        self.assertNotIn('"Order Date"', sql)
        self.assertEqual(sql, "SELECT * FROM orders WHERE `Order Date` IN ('x')")
        self.assertIn("WHERE `Order Date`", stub._excel_parameter_values)

    def assert_double(self, sql, stub):
        self.assertEqual(sql, 'SELECT * FROM orders WHERE "Order Date" IN (\'x\')')
        self.assertNotIn("`", sql)
        self.assertIn('WHERE "Order Date"', stub._excel_parameter_values)

    def test_connected_mysql_field_other(self):
        stub = make_stub(field="Oracle", connected_db_type="MySQL")
        self.assert_backtick(self.confirm(stub), stub)

    def test_not_connected_field_mysql(self):
        stub = make_stub(field="MySQL")
        self.assert_backtick(self.confirm(stub), stub)

    def test_field_oracle(self):
        stub = make_stub(field="Oracle")
        self.assert_double(self.confirm(stub), stub)

    def test_connected_oracle_field_mysql(self):
        stub = make_stub(field="MySQL", connected_db_type="Oracle")
        self.assert_double(self.confirm(stub), stub)

    def test_stub_without_db_type(self):
        stub = make_stub(field=None)
        self.assertEqual(stub._sql_identifier_db_type(), "")
        self.assert_double(self.confirm(stub), stub)

    def test_plain_column_not_quoted_mysql(self):
        stub = make_stub(field="MySQL")
        confirm_auto_where(stub, {"CUST_ID": ["1"]}, {"CUST_ID": ["1"]})
        self.assertEqual(norm(stub.sql_context.content),
                         "SELECT * FROM orders WHERE CUST_ID IN ('1')")


# ======================================================================
# R15-AC-32: excel_value_text
# ======================================================================
class AC32ExcelValueTextTests(unittest.TestCase):
    CASES = [
        (pd.Timestamp("2024-01-15"), "2024-01-15"),
        (dt.datetime(2024, 1, 15), "2024-01-15"),
        (dt.date(2024, 1, 15), "2024-01-15"),
        (pd.Timestamp("2024-01-15 10:30:00"), "2024-01-15 10:30:00"),
        (1.2345678901234568e16, "12345678901234568"),
        (1e20, "100000000000000000000"),
        (-1e16, "-10000000000000000"),
        (1234.0, "1234"),
        (1.5, "1.5"),
        ("abc", "abc"),
    ]

    def test_spec_values(self):
        for value, expected in self.CASES:
            with self.subTest(value=repr(value)):
                out = app.excel_value_text(value)
                self.assertEqual(out, expected)
                self.assertNotIn("e+", out)
                self.assertNotIn(" 00:00:00", out)

    def test_numpy_float64(self):
        self.assertEqual(app.excel_value_text(np.float64(1.2345678901234568e16)),
                         "12345678901234568")
        self.assertEqual(app.excel_value_text(np.float64(1234.0)), "1234")

    def test_values_kept_as_before(self):
        self.assertEqual(app.excel_value_text(12.5), "12.5")
        self.assertEqual(app.excel_value_text("0012"), "0012")
        self.assertEqual(app.excel_value_text(7), "7")
        self.assertEqual(app.excel_value_text(-0.0), "0")
        self.assertEqual(app.excel_value_text(float("inf")), "inf")
        self.assertEqual(app.excel_value_text(""), "")

    def test_midnight_with_tz_or_fraction_unchanged(self):
        aware = pd.Timestamp("2024-01-15", tz="UTC")
        self.assertEqual(app.excel_value_text(aware), str(aware))
        aware_dt = dt.datetime(2024, 1, 15, tzinfo=dt.timezone.utc)
        self.assertEqual(app.excel_value_text(aware_dt), str(aware_dt))
        nano = pd.Timestamp("2024-01-15 00:00:00.000000001")
        self.assertEqual(app.excel_value_text(nano), str(nano))
        micro = dt.datetime(2024, 1, 15, 0, 0, 0, 1)
        self.assertEqual(app.excel_value_text(micro), str(micro))
        self.assertEqual(app.excel_value_text(dt.datetime(2024, 1, 15, 0, 0, 1)),
                         "2024-01-15 00:00:01")


# ======================================================================
# R15-AC-33: _format_excel_sql_values + end-to-end real Excel
# ======================================================================
class AC33FormatExcelSqlValuesTests(unittest.TestCase):
    def setUp(self):
        self.stub = GUI.__new__(GUI)

    def test_spec_values(self):
        self.assertEqual(
            self.stub._format_excel_sql_values(
                [pd.Timestamp("2024-01-15"), pd.Timestamp("2024-01-15 10:30")]),
            "'2024-01-15', '2024-01-15 10:30:00'")
        self.assertEqual(self.stub._format_excel_sql_values([1.2345678901234568e16]),
                         "12345678901234568")

    def test_other_values_unchanged(self):
        self.assertEqual(self.stub._format_excel_sql_values(
            [1234.0, 12.5, 7, "O'Brien", "'ABC'", None, float("nan")]),
            "1234, 12.5, 7, 'O''Brien', 'ABC'")
        self.assertEqual(self.stub._format_excel_sql_values([]), "")
        self.assertEqual(self.stub._format_excel_sql_values([dt.date(2024, 1, 15)]),
                         "'2024-01-15'")


class AC33EndToEndExcelTests(unittest.TestCase):
    BIG = 12345678901234567

    def write_book(self, path):
        from openpyxl import Workbook

        wb = Workbook()
        ws = wb.active
        ws.title = "Sheet1"
        ws.append(["Order Date", "Big", "Order No"])
        ws.append([dt.datetime(2024, 1, 15), self.BIG, 1001])
        ws.append([dt.datetime(2024, 1, 16), None, None])  # blank -> float column
        ws.append([dt.datetime(2024, 1, 17, 10, 30), 5, 1002])
        wb.save(path)
        # openpyxl writes the int with 16 significant digits; put the exact
        # 17-digit number in the cell XML (as Excel files from other tools can)
        with zipfile.ZipFile(path) as z:
            parts = {n: z.read(n) for n in z.namelist()}
        sheet = "xl/worksheets/sheet1.xml"
        written = repr(float(self.BIG)).encode()  # b"1.2345678901234568e+16"
        if written not in parts[sheet]:
            written = b"1.234567890123457e+16"
        self.assertIn(written, parts[sheet])
        parts[sheet] = parts[sheet].replace(written, str(self.BIG).encode())
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
            for name, data in parts.items():
                z.writestr(name, data)

    def test_rendered_sql_has_no_exponent_or_midnight(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "book.xlsx")
            self.write_book(path)
            with open(path, "rb") as f:
                df = pd.read_excel(f, sheet_name="Sheet1")
        # precondition: the number column really arrives as float
        self.assertEqual(df["Big"].dtype, np.float64)
        self.assertEqual(df["Order No"].dtype, np.float64)
        self.assertTrue(pd.api.types.is_datetime64_any_dtype(df["Order Date"]))

        stub = make_stub(field="Oracle")
        mb, values = confirm_auto_where(stub, {}, {}, dataframe=df, load_from_dataframe=True)
        # values shown in the dialog
        self.assertEqual(values["Order Date"],
                         ["2024-01-15", "2024-01-16", "2024-01-17 10:30:00"])
        big_text = values["Big"][0]
        self.assertTrue(big_text.isdigit(), big_text)
        self.assertEqual(len(big_text), 17)
        # float cannot hold 12345678901234567 exactly (> 2**53): it becomes ...568
        self.assertEqual(big_text, str(int(float(self.BIG))))
        self.assertEqual(big_text, "12345678901234568")
        self.assertEqual(values["Order No"], ["1001", "1002"])

        # tick everything and Confirm
        mb.reset_mock()
        stub2 = make_stub(field="Oracle")
        mb, _ = confirm_auto_where(stub2, values, {c: list(v) for c, v in values.items()},
                                   dataframe=df)
        mb.showwarning.assert_not_called()
        sql = stub2.sql_context.content
        self.assertIn("'2024-01-15'", sql)
        self.assertIn("'2024-01-17 10:30:00'", sql)
        self.assertNotIn("e+", sql)
        self.assertNotIn("E+", sql)
        self.assertNotIn(" 00:00:00", sql)
        self.assertNotIn(".0'", sql)
        self.assertIn("'12345678901234568'", sql)
        self.assertEqual(
            norm(sql),
            "SELECT * FROM orders WHERE \"Order Date\" IN ('2024-01-15', '2024-01-16', "
            "'2024-01-17 10:30:00') AND Big IN ('12345678901234568', '5') "
            "AND \"Order No\" IN ('1001', '1002')")


# ======================================================================
# R15-AC-34 / AC-35: format_sql_value, render_table_variables
# ======================================================================
class AC34FormatSqlValueTests(unittest.TestCase):
    CASES = [
        (1001.0, "1001"),
        (np.float64(1001.0), "1001"),
        (1.2345678901234568e16, "12345678901234568"),
        (1001.5, "1001.5"),
        (5, "5"),
        (Decimal("1.10"), "1.10"),
        ("O'Brien", "'O''Brien'"),
        (None, "NULL"),
        (float("nan"), "NULL"),
    ]

    def test_spec_values(self):
        for value, expected in self.CASES:
            with self.subTest(value=repr(value)):
                self.assertEqual(app.format_sql_value(value), expected)

    def test_more_values(self):
        self.assertEqual(app.format_sql_value(np.float64("nan")), "NULL")
        self.assertEqual(app.format_sql_value(np.int64(7)), "7")
        self.assertEqual(app.format_sql_value(1e20), "100000000000000000000")
        self.assertEqual(app.format_sql_value(-0.0), "0")
        self.assertEqual(app.format_sql_value(""), "''")
        self.assertEqual(app.format_sql_value("True"), "'True'")

    def test_datetime_not_touched_r15_q9(self):
        self.assertEqual(app.format_sql_value(pd.Timestamp("2024-01-15")), "2024-01-15 00:00:00")

    def test_render_table_variables_float_column(self):
        tables = {"orders": {"column_data": {"id": [1001.0, 1002.0]}}}
        result = app.render_table_variables("x IN ({TABLE_ORDERS_ID})", tables)
        self.assertTrue(result.ok)
        self.assertEqual(result.sql, "x IN (1001, 1002)")
        self.assertEqual(app.format_sql_value_list([1001.0, 1002.0]), "1001, 1002")

    def test_render_table_variables_numpy_and_bool(self):
        tables = {"t": {"column_data": {
            "a": list(np.array([1001.0, 1002.5])),
            "b": [True, False, np.bool_(True)],
        }}}
        result = app.render_table_variables("{TABLE_T_A} / {TABLE_T_B}", tables)
        self.assertEqual(result.sql, "1001, 1002.5 / 1, 0, 1")


class AC35BoolTests(unittest.TestCase):
    def test_bool_values(self):
        self.assertEqual(app.format_sql_value(True), "1")
        self.assertEqual(app.format_sql_value(False), "0")
        self.assertEqual(app.format_sql_value(np.bool_(True)), "1")
        self.assertEqual(app.format_sql_value(np.bool_(False)), "0")
        joined = app.format_sql_value_list([True, False, np.bool_(True)])
        self.assertEqual(joined, "1, 0, 1")
        self.assertNotIn("True", joined)
        self.assertNotIn("False", joined)


# ======================================================================
# R15-R8 (record only): Reset detected mode on backtick `Order Date` IN (...)
# ======================================================================
SQL_BT = "SELECT * FROM orders WHERE `Order Date` IN ('x', 'y')"


class R8BacktickResetTests(unittest.TestCase):
    def test_detected(self):
        items = GUI._detect_sql_in_lists(SQL_BT)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["column"], "`Order Date`")
        self.assertEqual(items[0]["tokens"], ["'x'", "'y'"])

    def test_main_window_reset(self):
        stub = make_main(SQL_BT)
        h = DialogHarness()
        h.stub = stub
        with h.patched():
            stub.show_reset_parameter_dialog()
            self.assertEqual(h.checkbox_texts(), ["x", "y"])
            h.tick("x")
            h.buttons[CONFIRM]()
            mb = h.mb
        mb.showwarning.assert_not_called()
        mb.showerror.assert_not_called()
        self.assertEqual(stub.sql_context.content,
                         "SELECT * FROM orders WHERE `Order Date` IN ('y')")

    def test_main_window_reset_last_value(self):
        stub = make_main("SELECT * FROM orders WHERE `Order Date` IN ('x')")
        h = DialogHarness()
        h.stub = stub
        with h.patched():
            stub.show_reset_parameter_dialog()
            h.tick("x")
            h.buttons[CONFIRM]()
        self.assertEqual(stub.sql_context.content, "SELECT * FROM orders WHERE 1=0")

    def test_edit_job_reset(self):
        stub = make_main("SELECT 1 FROM main")
        main_state = (stub.sql_context, stub.sql_context.content, stub.root)
        query_text = _Text(SQL_BT)
        state = {"template": None, "values": {}, "rendered": None}
        funcs = compile_nested(GUI.edit_job, ("sync_edit_parameter_state",
                                              "reset_parameter_for_edit"),
                               {"query_text": query_text, "edit_excel_state": state,
                                "self": stub, "dialog": mock.MagicMock(name="edit_dialog")})
        h = DialogHarness()
        h.stub = stub
        original = GUI.show_reset_parameter_dialog
        texts = []

        def show(*a, **k):
            result = original(stub, *a, **k)
            texts.extend(h.checkbox_texts())
            h.tick("x")
            h.buttons[CONFIRM]()
            return result

        with h.patched(), mock.patch.object(stub, "show_reset_parameter_dialog",
                                            side_effect=show):
            funcs["reset_parameter_for_edit"]()
            mb = h.mb
        mb.showwarning.assert_not_called()
        mb.showerror.assert_not_called()
        self.assertEqual(texts, ["x", "y"])
        self.assertEqual(query_text.content,
                         "SELECT * FROM orders WHERE `Order Date` IN ('y')")
        self.assertEqual((stub.sql_context, stub.sql_context.content, stub.root), main_state)


if __name__ == "__main__":
    unittest.main()
