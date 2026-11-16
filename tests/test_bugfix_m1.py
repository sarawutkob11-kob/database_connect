"""R5-T7 (M-1): detect SQL placeholders from scanner tokens."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import database_connect_gui as app  # noqa: E402


class SqlPlaceholderDetectionTests(unittest.TestCase):
    def test_only_real_placeholders_are_detected(self):
        sql = (
            "SELECT :real_bind, {braced}, {{double_braced}}, value::type, "
            "TO_CHAR(created_at, 'HH24:MI:SS'), ':literal' FROM records "
            "/* :block_comment */ -- :line_comment\n"
            "WHERE note = 'text {not_a_bind}' AND id = :real_bind"
        )

        self.assertEqual(
            app._detect_sql_placeholders(sql),
            [":real_bind", "{braced}", "{{double_braced}}", ":literal"],
        )


if __name__ == "__main__":
    unittest.main()