"""R5-T5: bytes in Excel exports use the database value formatter."""

import ast
import inspect
import os
import re
import sys
import textwrap
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import database_connect_gui as app  # noqa: E402


def get_clean_value(formatter):
    source = textwrap.dedent(
        inspect.getsource(app.DatabaseConnectorGUI.export_jobs_to_excel)
    )
    tree = ast.parse(source)
    function = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "clean_value"
    )
    namespace = {
        "excel_db_value": app.excel_db_value,
        "format_db_value": formatter,
        "illegal_chars": re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]"),
    }
    module = ast.fix_missing_locations(ast.Module(body=[function], type_ignores=[]))
    exec(compile(module, "<clean_value>", "exec"), namespace)
    return namespace["clean_value"]


class CleanValueBytesTests(unittest.TestCase):
    def test_bytes_are_passed_directly_to_format_db_value(self):
        value = b"\x00\xff\x80"
        formatter = mock.Mock(return_value="formatted-hex")
        clean_value = get_clean_value(formatter)

        result = clean_value(value)

        formatter.assert_called_once_with(value)
        self.assertEqual(result, "formatted-hex")

    def test_bytes_result_is_formatter_hex_and_non_bytes_stay_typed(self):
        clean_value = get_clean_value(app.format_db_value)

        self.assertEqual(clean_value(b"\x00\xff\x80"), "00FF80")
        self.assertEqual(clean_value(42), 42)


if __name__ == "__main__":
    unittest.main()