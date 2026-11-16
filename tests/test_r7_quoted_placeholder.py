"""R7-T5 (R7-4): a '...' literal whose whole content is one placeholder is detected.

Covers R7-AC-16 .. R7-AC-20. Pure functions only; no Tk, no files.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import database_connect_gui as app  # noqa: E402


def detect(sql):
    return app._detect_sql_placeholders(sql)


def render(template, values):
    stub = app.DatabaseConnectorGUI.__new__(app.DatabaseConnectorGUI)
    stub.sql_template = template
    return stub._render_sql_template(values)


class QuotedPlaceholderDetectedTests(unittest.TestCase):
    """R7-AC-16"""

    def test_colon_placeholder_in_quotes(self):
        self.assertEqual(detect("WHERE a IN (':ACC')"), [":ACC"])

    def test_single_brace_placeholder_in_quotes(self):
        self.assertEqual(detect("WHERE a = '{acc}'"), ["{acc}"])

    def test_double_brace_placeholder_in_quotes(self):
        self.assertEqual(detect("WHERE a = '{{ ACC }}'"), ["{{ ACC }}"])

    def test_returned_value_has_no_quotes(self):
        for sql in ("SELECT ':ACC'", "SELECT '{ACC}'", "SELECT '{{ACC}}'", "':A_1'", "':_x'"):
            with self.subTest(sql=sql):
                found = detect(sql)
                self.assertEqual(len(found), 1)
                self.assertNotIn("'", found[0])
                self.assertIn(found[0], sql)

    def test_same_shape_as_unquoted_placeholder(self):
        for name in (":ACC", "{ACC}", "{{ACC}}", "{ ACC }", "{{ ACC }}"):
            with self.subTest(name=name):
                self.assertEqual(detect(f"WHERE a = '{name}'"), detect(f"WHERE a = {name}"))
                self.assertEqual(detect(f"WHERE a = '{name}'"), [name])

    def test_several_quoted_placeholders_in_order(self):
        sql = "WHERE a = ':A' AND b = '{B}' AND c IN (':C', '{{ D }}')"
        self.assertEqual(detect(sql), [":A", "{B}", ":C", "{{ D }}"])

    def test_quoted_placeholder_at_edges_of_sql(self):
        self.assertEqual(detect("':ACC'"), [":ACC"])
        self.assertEqual(detect("':ACC' = a"), [":ACC"])
        self.assertEqual(detect("a = ':ACC'"), [":ACC"])


class LongerLiteralNotDetectedTests(unittest.TestCase):
    """R7-AC-17: M-1 stays - a placeholder inside a longer literal is text."""

    NOT_DETECTED = (
        "'HH24:MI:SS'",
        "'text {x}'",
        "'a :ACC'",
        "' :ACC'",
        "':ACC '",
        "':ACC:B'",
        "'::x'",
        "':1'",
        "''",
        "':'",
        "'{}'",
        "'{1}'",
        "':ACC,:B'",
        "':ACC' ':B'".replace("' '", "''"),  # ':ACC'':B' = one literal with an escaped quote
        "'{x} text'",
        "'{x}{y}'",
        "':A-B'",
        "'\n:ACC'",
    )

    def test_literals_that_are_not_exactly_one_placeholder(self):
        for literal in self.NOT_DETECTED:
            with self.subTest(literal=literal):
                self.assertEqual(detect(f"SELECT {literal} FROM t"), [])
                self.assertEqual(detect(literal), [])

    def test_to_char_time_format(self):
        self.assertEqual(detect("SELECT TO_CHAR(d, 'HH24:MI:SS') FROM t"), [])

    def test_comments_are_not_scanned(self):
        for sql in (
            "SELECT 1 /* ':ACC' */ FROM t",
            "SELECT 1 -- ':ACC'\nFROM t",
            "SELECT 1 -- ':ACC'",
            "/* '{ACC}' */ SELECT 1",
            "SELECT 1 -- '{{ ACC }}'",
        ):
            with self.subTest(sql=sql):
                self.assertEqual(detect(sql), [])

    def test_double_quoted_identifier_is_not_detected(self):
        for sql in ('SELECT ":ACC" FROM t', 'SELECT "{ACC}" FROM t', 'SELECT "{{ ACC }}" FROM t'):
            with self.subTest(sql=sql):
                self.assertEqual(detect(sql), [])

    def test_dollar_quoted_string_is_not_detected(self):
        for sql in ("SELECT $$:ACC$$", "SELECT $tag$:ACC$tag$", "SELECT $${ACC}$$"):
            with self.subTest(sql=sql):
                self.assertEqual(detect(sql), [])

    def test_unterminated_literal_does_not_raise_or_detect(self):
        for sql in ("SELECT '", "'", "SELECT ':ACC", "SELECT '{ACC}"):
            with self.subTest(sql=sql):
                self.assertEqual(detect(sql), [])

    def test_empty_sql(self):
        self.assertEqual(detect(""), [])

    def test_unquoted_detection_is_unchanged(self):
        self.assertEqual(detect("WHERE a = :ACC AND b = {B} AND c = {{ C }}"),
                         [":ACC", "{B}", "{{ C }}"])
        self.assertEqual(detect("SELECT value::type, a:b, 12:30 FROM t"), [])

    def test_mixed_real_and_text_literals(self):
        sql = "SELECT TO_CHAR(d, 'HH24:MI:SS'), ':ACC', 'x :NOPE', \":ID\" FROM t -- ':C'"
        self.assertEqual(detect(sql), [":ACC"])


class DuplicateAndOrderTests(unittest.TestCase):
    """R7-AC-18"""

    def test_colon_bare_then_quoted_appears_once(self):
        self.assertEqual(detect("WHERE a = :ACC AND b = ':ACC'"), [":ACC"])

    def test_colon_quoted_then_bare_appears_once(self):
        self.assertEqual(detect("WHERE a = ':ACC' AND b = :ACC"), [":ACC"])

    def test_brace_bare_and_quoted_appears_once(self):
        self.assertEqual(detect("WHERE a = {ACC} AND b = '{ACC}'"), ["{ACC}"])
        self.assertEqual(detect("WHERE a = '{ACC}' AND b = {ACC}"), ["{ACC}"])

    def test_order_follows_first_position(self):
        sql = "WHERE a = ':B' AND b = :A AND c = :B AND d = '{C}' AND e = ':A' AND f = {C}"
        self.assertEqual(detect(sql), [":B", ":A", "{C}"])

    def test_quoted_first_keeps_its_position_before_later_bare(self):
        self.assertEqual(detect("SELECT '{X}', :Y, {X}, ':Y', ':Z'"), ["{X}", ":Y", ":Z"])


class DetectThenRenderTests(unittest.TestCase):
    """R7-AC-19: what detect returns can be passed to _render_sql_template."""

    def test_quoted_colon_placeholder(self):
        template = "WHERE a IN (':ACC')"
        (parameter,) = detect(template)
        self.assertEqual(parameter, ":ACC")
        self.assertEqual(render(template, {"ACC": (parameter, "'1'")}), "WHERE a IN ('1')")

    def test_quoted_brace_placeholder(self):
        template = "WHERE a IN ('{ACC}')"
        (parameter,) = detect(template)
        self.assertEqual(parameter, "{ACC}")
        self.assertEqual(render(template, {"ACC": (parameter, "'1'")}), "WHERE a IN ('1')")

    def test_quoted_double_brace_placeholder(self):
        template = "WHERE a IN ('{{ACC}}')"
        (parameter,) = detect(template)
        self.assertEqual(render(template, {"ACC": (parameter, "'1', '2'")}),
                         "WHERE a IN ('1', '2')")

    def test_render_leaves_longer_literals_alone(self):
        template = "SELECT TO_CHAR(d, 'HH24:MI:SS') FROM t WHERE a IN (':ACC')"
        (parameter,) = detect(template)
        self.assertEqual(
            render(template, {"ACC": (parameter, "'1'")}),
            "SELECT TO_CHAR(d, 'HH24:MI:SS') FROM t WHERE a IN ('1')",
        )


class ExistingM1CaseTests(unittest.TestCase):
    """R7-AC-20: only ':literal' is new in the M-1 sample."""

    def test_m1_sample(self):
        sql = (
            "SELECT :real_bind, {braced}, {{double_braced}}, value::type, "
            "TO_CHAR(created_at, 'HH24:MI:SS'), ':literal' FROM records "
            "/* :block_comment */ -- :line_comment\n"
            "WHERE note = 'text {not_a_bind}' AND id = :real_bind"
        )
        found = detect(sql)
        self.assertEqual(found, [":real_bind", "{braced}", "{{double_braced}}", ":literal"])
        for unwanted in (":MI", ":SS", "{not_a_bind}", ":block_comment", ":line_comment",
                         ":type"):
            self.assertNotIn(unwanted, found)


if __name__ == "__main__":
    unittest.main()
