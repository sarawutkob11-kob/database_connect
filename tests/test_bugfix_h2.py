"""R5-T6 (H-2): render the first real IN list from SQL tokens."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import database_connect_gui as app  # noqa: E402


class FirstInListTemplateTests(unittest.TestCase):
    def render(self, template):
        stub = app.DatabaseConnectorGUI.__new__(app.DatabaseConnectorGUI)
        stub.sql_template = template
        return stub._render_sql_template({"__FIRST_IN_LIST__": ("", "'replacement'")})

    def test_skips_comment_and_string_decoys(self):
        template = (
            "SELECT 'IN (string)' AS note /* IN (block) */ FROM t "
            "-- IN (line)\nWHERE id IN (1, 2)"
        )

        rendered = self.render(template)

        self.assertEqual(
            rendered,
            "SELECT 'IN (string)' AS note /* IN (block) */ FROM t "
            "-- IN (line)\nWHERE id IN ('replacement')",
        )

    def test_replaces_through_nested_parentheses(self):
        rendered = self.render("SELECT * FROM t WHERE id IN (COALESCE(1, 2), 3)")

        self.assertEqual(rendered, "SELECT * FROM t WHERE id IN ('replacement')")

    def test_raises_when_no_real_in_list_exists(self):
        template = "SELECT 'IN (string)' FROM t -- IN (comment)\n"

        with self.assertRaisesRegex(ValueError, r"template.*IN \(\.\.\.\)"):
            self.render(template)


if __name__ == "__main__":
    unittest.main()