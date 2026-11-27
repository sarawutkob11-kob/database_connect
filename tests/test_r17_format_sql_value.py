"""QA for R17-T1 (R17-AC-1..8, R17-AC-10).

format_sql_value must treat numpy floating scalars (float16/float32/...)
like Python float: integral values -> int literal, NaN -> NULL.
Pure function test: no Tk window, no database, no files.
"""

import math
import os
import sys
import unittest
from decimal import Decimal

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import database_connect_gui as app  # noqa: E402

fmt = app.format_sql_value


class R17FormatSqlValueTest(unittest.TestCase):
    def check(self, cases):
        for value, expected in cases:
            with self.subTest(value=value, type=type(value).__name__):
                result = fmt(value)
                self.assertIsInstance(result, str)
                self.assertEqual(result, expected)

    # R17-AC-1
    def test_ac1_float32_integral(self):
        self.check([(np.float32(1001.0), "1001")])

    # R17-AC-2
    def test_ac2_float16_float32_integral_pos_neg_zero(self):
        self.check([
            (np.float16(5.0), "5"),
            (np.float32(-3.0), "-3"),
            (np.float32(0.0), "0"),
            (np.float16(0.0), "0"),
            (np.float16(-7.0), "-7"),
            (np.float32(-0.0), "0"),
            (np.float16(-0.0), "0"),
            (np.float32(16777216.0), "16777216"),  # 2**24, float32 exact
            (np.float16(2048.0), "2048"),
            (np.float32(1e10), "10000000000"),
        ])

    def test_ac2_no_decimal_point_for_any_integral_numpy_float(self):
        for dtype in (np.float16, np.float32, np.float64):
            for n in (-100, -1, 0, 1, 42, 1001):
                with self.subTest(dtype=dtype.__name__, n=n):
                    self.assertEqual(fmt(dtype(n)), str(n))

    # R17-AC-3
    def test_ac3_non_integral_unchanged(self):
        for value in (np.float32(1.5), np.float32(-2.75), np.float16(0.5),
                      np.float32(0.1), np.float16(-1.25)):
            with self.subTest(value=value, type=type(value).__name__):
                self.assertEqual(fmt(value), str(value))
        self.assertEqual(fmt(np.float32(1.5)), "1.5")

    # R17-AC-4
    def test_ac4_python_nan_float64_nan_none(self):
        self.check([
            (float("nan"), "NULL"),
            (np.float64("nan"), "NULL"),
            (np.nan, "NULL"),
            (None, "NULL"),
        ])

    # R17-AC-10
    def test_ac10_numpy_low_precision_nan_is_null(self):
        self.check([
            (np.float32("nan"), "NULL"),
            (np.float16("nan"), "NULL"),
            (-np.float32("nan"), "NULL"),
        ])

    # R17-AC-5
    def test_ac5_bool_and_numpy_bool(self):
        self.check([
            (True, "1"),
            (False, "0"),
            (np.bool_(True), "1"),
            (np.bool_(False), "0"),
        ])

    # R17-AC-6
    def test_ac6_python_float_and_float64_unchanged(self):
        self.check([
            (1001.0, "1001"),
            (np.float64(1001.0), "1001"),
            (1.5, "1.5"),
            (np.float64(2.25), "2.25"),
            (-0.0, "0"),
            (-3.0, "-3"),
        ])

    # R17-AC-7
    def test_ac7_infinity_no_crash_same_as_str(self):
        for value in (float("inf"), float("-inf"),
                      np.float64("inf"), np.float64("-inf"),
                      np.float32("inf"), np.float32("-inf"),
                      np.float16("inf"), np.float16("-inf")):
            with self.subTest(value=value, type=type(value).__name__):
                result = fmt(value)  # must not raise OverflowError
                self.assertEqual(result, str(value))
                self.assertIn(result, ("inf", "-inf"))

    # R17-AC-8
    def test_ac8_other_types_unchanged(self):
        self.check([
            (0, "0"),
            (1001, "1001"),
            (-5, "-5"),
            (np.int64(42), "42"),
            (np.int32(-7), "-7"),
            ("abc", "'abc'"),
            ("O'Brien", "'O''Brien'"),
            ("", "''"),
            ("1.0", "'1.0'"),
            ("nan", "'nan'"),
            (Decimal("1.50"), "1.50"),
            (Decimal("1001"), "1001"),
        ])

    def test_list_helper_with_mixed_numpy_floats(self):
        values = [np.float32(1001.0), np.float32("nan"), np.float16(1.5),
                  1.0, None, "x", np.bool_(True)]
        self.assertEqual(app.format_sql_value_list(values),
                         "1001, NULL, 1.5, 1, NULL, 'x', 1")

    def test_numpy_array_elements_from_float32_column(self):
        arr = np.array([1.0, 2.5, np.nan, -4.0], dtype=np.float32)
        self.assertEqual([fmt(v) for v in arr], ["1", "2.5", "NULL", "-4"])
        self.assertTrue(math.isnan(float(arr[2])))


if __name__ == "__main__":
    unittest.main()
