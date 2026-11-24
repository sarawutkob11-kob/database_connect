"""R15-T3 (BH-3): Treeview uses unique column ids (R15-AC-7..9).

Real Tk (withdrawn root); skipped when no display is available.
messagebox is patched; the clipboard is read back from the real Tk root.
"""

import os
import re
import sys
import unittest
from typing import Any, List
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tkinter as tk  # noqa: E402
from tkinter import ttk  # noqa: E402

import pandas as pd  # noqa: E402

import database_connect_gui as app  # noqa: E402

GUI = app.DatabaseConnectorGUI


def _make_root():
    try:
        root = tk.Tk()
    except tk.TclError as exc:  # no display
        raise unittest.SkipTest(f"Tk not available: {exc}")
    root.withdraw()
    return root


class _TkCase(unittest.TestCase):
    def setUp(self):
        self.root = _make_root()
        self.addCleanup(self._destroy_root)
        self.gui = GUI.__new__(GUI)
        self.gui.root = self.root
        self.gui.canvas = tk.Canvas(self.root)
        self.gui._main_mousewheel = lambda _e=None: None
        patcher = mock.patch.object(app, "messagebox")
        self.mb = patcher.start()
        self.addCleanup(patcher.stop)

    def _destroy_root(self):
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    # ---- helpers ---------------------------------------------------------
    def headings(self, tree) -> List[str]:
        return [str(tree.heading(c, "text")) for c in tree["columns"]]

    def copy(self, tree, items=None) -> str:
        items = list(tree.get_children("")) if items is None else items
        tree.selection_set(items)
        self.root.clipboard_clear()
        self.gui.copy_selected_rows(tree)
        self.mb.showerror.assert_not_called()
        self.mb.showwarning.assert_not_called()
        return self.root.clipboard_get()

    def click_heading(self, tree, index: int) -> None:
        col_id = tree["columns"][index]
        cmd = tree.heading(col_id, "command")
        self.assertTrue(cmd, "heading has no sort command")
        tree.tk.call(cmd)

    def rows(self, tree) -> List[List[str]]:
        return [
            [str(tree.set(item, c)) for c in tree["columns"]] for item in tree.get_children("")
        ]

    def open_popup(self, df, **kw):
        created: List[Any] = []
        real = ttk.Treeview

        class CapturingTreeview(real):  # type: ignore[misc, valid-type]
            def __init__(self, *a, **k):
                super().__init__(*a, **k)
                created.append(self)

        with mock.patch.object(app.ttk, "Treeview", CapturingTreeview):
            popup = self.gui.show_table_popup(df, "SELECT 1", **kw)
        self.assertEqual(len(created), 1)
        self.root.update_idletasks()
        return popup, created[0]


# ---------------------------------------------------------------------------
class TestTreeviewColumnIdsHelper(unittest.TestCase):
    def helper(self):
        fn = getattr(app, "_treeview_column_ids", None)
        self.assertIsNotNone(fn, "_treeview_column_ids missing")
        return fn

    def test_unique_names_kept_as_str(self):
        self.assertEqual(self.helper()(["ID", "NAME"]), ["ID", "NAME"])
        self.assertEqual(
            self.helper()(["Database", "Schema", "Table"]), ["Database", "Schema", "Table"]
        )

    def test_non_str_unique_become_str(self):
        result = self.helper()([0, 1])
        self.assertEqual(result, ["0", "1"])
        self.assertTrue(all(isinstance(x, str) for x in result))

    def test_duplicates_positional(self):
        self.assertEqual(self.helper()(["ID", "NAME", "ID"]), ["c0", "c1", "c2"])

    def test_duplicates_after_str_conversion(self):
        # 1 and "1" are different objects but the same text
        self.assertEqual(self.helper()([1, "1"]), ["c0", "c1"])

    def test_empty(self):
        self.assertEqual(self.helper()([]), [])

    def test_accepts_pandas_index_and_tuple(self):
        self.assertEqual(self.helper()(pd.Index(["A", "A"])), ["c0", "c1"])
        self.assertEqual(self.helper()(("A", "B")), ["A", "B"])

    def test_returns_new_list(self):
        names = ["A", "B"]
        result = self.helper()(names)
        self.assertIsInstance(result, list)
        result.append("X")
        self.assertEqual(names, ["A", "B"])


# ---------------------------------------------------------------------------
class TestPopupDuplicateColumns(_TkCase):
    """R15-AC-7, R15-AC-8."""

    def setUp(self):
        super().setUp()
        df = pd.DataFrame([(1, "a", 2), (3, "b", 0)], columns=["ID", "NAME", "ID"])
        self.popup, self.tree = self.open_popup(df)

    def test_ac7_headings(self):
        self.assertEqual(self.headings(self.tree), ["ID", "NAME", "ID"])
        self.assertEqual(len(set(self.tree["columns"])), 3)

    def test_ac7_clipboard_positional(self):
        self.assertEqual(self.copy(self.tree), "ID\tNAME\tID\n1\ta\t2\n3\tb\t0\n")
        self.mb.showinfo.assert_called_once()

    def test_ac7_rows_positional(self):
        self.assertEqual(self.rows(self.tree), [["1", "a", "2"], ["3", "b", "0"]])

    def test_ac8_sort_third_then_reverse_then_first(self):
        self.click_heading(self.tree, 2)
        self.assertEqual(self.rows(self.tree), [["3", "b", "0"], ["1", "a", "2"]])
        self.click_heading(self.tree, 2)
        self.assertEqual(self.rows(self.tree), [["1", "a", "2"], ["3", "b", "0"]])
        # make column 1 order observable: put the 3-row on top first
        self.click_heading(self.tree, 2)
        self.assertEqual(self.rows(self.tree)[0], ["3", "b", "0"])
        self.click_heading(self.tree, 0)
        self.assertEqual(self.rows(self.tree), [["1", "a", "2"], ["3", "b", "0"]])
        self.click_heading(self.tree, 0)
        self.assertEqual(self.rows(self.tree), [["3", "b", "0"], ["1", "a", "2"]])

    def test_ac8_copy_after_sort_still_positional(self):
        self.click_heading(self.tree, 2)
        self.assertEqual(self.copy(self.tree), "ID\tNAME\tID\n3\tb\t0\n1\ta\t2\n")

    def test_copy_single_selected_row(self):
        second = self.tree.get_children("")[1]
        self.assertEqual(self.copy(self.tree, [second]), "ID\tNAME\tID\n3\tb\t0\n")

    def test_copy_nothing_selected_warns(self):
        self.tree.selection_set([])
        self.gui.copy_selected_rows(self.tree)
        self.mb.showwarning.assert_called_once()
        self.mb.showerror.assert_not_called()


class TestPopupOtherColumnShapes(_TkCase):
    def test_non_str_columns_popup(self):
        df = pd.DataFrame([("x", "y")], columns=[0, 1])
        _popup, tree = self.open_popup(df)
        self.assertEqual(self.headings(tree), ["0", "1"])
        self.assertEqual(self.copy(tree), "0\t1\nx\ty\n")

    def test_leading_zero_text_kept_popup(self):
        df = pd.DataFrame([("0012", "a", "007")], columns=["ID", "NAME", "ID"])
        _popup, tree = self.open_popup(df)
        self.assertEqual(self.copy(tree), "ID\tNAME\tID\n0012\ta\t007\n")

    def test_unique_columns_ids_are_names(self):
        df = pd.DataFrame([(1, "a")], columns=["ID", "NAME"])
        _popup, tree = self.open_popup(df)
        self.assertEqual(list(tree["columns"]), ["ID", "NAME"])
        self.assertEqual(str(tree.set(tree.get_children("")[0], "NAME")), "a")


class TestTablesPopupUnchanged(_TkCase):
    """R15-AC-9 (Tables part): ids are the names; double-click gives 3 values."""

    def setUp(self):
        super().setUp()
        self.df = pd.DataFrame(
            [("db1", "dbo", "T1"), ("db2", "sales", "0012")],
            columns=["Database", "Schema", "Table"],
        )
        self.callback = mock.Mock()
        self.popup, self.tree = self.open_popup(self.df, on_double_click=self.callback)

    def test_ids_are_names(self):
        self.assertEqual(list(self.tree["columns"]), ["Database", "Schema", "Table"])
        self.assertEqual(self.headings(self.tree), ["Database", "Schema", "Table"])
        first = self.tree.get_children("")[0]
        self.assertEqual(self.tree.set(first, "Table"), "T1")

    def test_double_click_values(self):
        first = self.tree.get_children("")[0]
        self.tree.selection_set([first])
        self.gui.on_tree_double_click(None, self.tree, self.callback)
        self.callback.assert_called_once()
        self.assertEqual(list(self.callback.call_args[0][0]), ["db1", "dbo", "T1"])

    def test_double_click_binding(self):
        script = self.tree.bind("<Double-Button-1>")
        self.assertTrue(script, "no <Double-Button-1> binding")
        first = self.tree.get_children("")[0]
        self.tree.selection_set([first])
        for _ in range(2):  # two quick presses = <Double-Button-1>
            self.tree.event_generate("<ButtonPress-1>", x=5, y=5, time=1000)
            self.tree.event_generate("<ButtonRelease-1>", x=5, y=5, time=1001)
        self.root.update()
        self.callback.assert_called_once()
        self.assertEqual(list(self.callback.call_args[0][0]), ["db1", "dbo", "T1"])


# ---------------------------------------------------------------------------
class _ResultsGridCase(_TkCase):
    def setUp(self):
        super().setUp()
        saved_theme = app.ROUND["theme"]
        self.addCleanup(app.ROUND.__setitem__, "theme", saved_theme)
        app.ui_round_init(ttk.Style(self.root))
        tab = tk.Frame(self.root)
        self.gui._build_results_grid_tab(tab)
        self.tree = self.gui._rg_tree

    def show(self, df, page=0):
        self.gui._results_grid_state.update(df=df, sql="SELECT 1", name=None, page=0)
        self.gui._render_results_grid_page(page)
        self.root.update_idletasks()

    def ctrl_c(self) -> str:
        self.tree.selection_set(list(self.tree.get_children("")))
        self.root.clipboard_clear()
        # A withdrawn window gets no keyboard focus, so run the bound
        # <Control-KeyPress> script itself with Ctrl+C event fields.
        script = self.tree.bind("<Control-KeyPress>")
        match = re.search(r"\[(\S+) ([^\]]*)\]", script)
        self.assertIsNotNone(match, f"unexpected binding: {script!r}")
        fields = {"%k": "67", "%K": "c", "%s": "4", "%A": "\x03", "%W": str(self.tree)}
        result = self.tree.tk.call(
            match.group(1), *[fields.get(f, "0") for f in match.group(2).split()]
        )
        self.assertEqual(str(result), "break")
        self.root.update()
        self.mb.showerror.assert_not_called()
        return self.root.clipboard_get()


class TestResultsGridColumns(_ResultsGridCase):
    """R15-AC-9 (Results Grid part)."""

    def test_duplicate_columns_copy(self):
        self.show(pd.DataFrame([(1, "a", 2), (3, "b", 0)], columns=["ID", "NAME", "ID"]))
        self.assertEqual(self.headings(self.tree), ["ID", "NAME", "ID"])
        self.assertEqual(len(set(self.tree["columns"])), 3)
        self.assertEqual(self.copy(self.tree), "ID\tNAME\tID\n1\ta\t2\n3\tb\t0\n")

    def test_duplicate_columns_ctrl_c_binding(self):
        self.show(pd.DataFrame([(1, "a", 2), (3, "b", 0)], columns=["ID", "NAME", "ID"]))
        self.assertEqual(self.ctrl_c(), "ID\tNAME\tID\n1\ta\t2\n3\tb\t0\n")

    def test_non_str_columns_copy(self):
        self.show(pd.DataFrame([("x", "y"), ("p", "q")], columns=[0, 1]))
        self.assertEqual(self.headings(self.tree), ["0", "1"])
        self.assertEqual(self.copy(self.tree), "0\t1\nx\ty\np\tq\n")

    def test_non_str_columns_reversed_copy(self):
        # ids "1","0": the text id must not be read as a column index
        self.show(pd.DataFrame([("x", "y")], columns=[1, 0]))
        self.assertEqual(self.headings(self.tree), ["1", "0"])
        self.assertEqual(self.copy(self.tree), "1\t0\nx\ty\n")

    def test_non_str_columns_ctrl_c(self):
        self.show(pd.DataFrame([("x", "y")], columns=[0, 1]))
        self.assertEqual(self.ctrl_c(), "0\t1\nx\ty\n")

    def test_leading_zero_text_kept(self):
        self.show(pd.DataFrame([("0012", "a", "007")], columns=["ID", "NAME", "ID"]))
        self.assertEqual(self.copy(self.tree), "ID\tNAME\tID\n0012\ta\t007\n")

    def test_leading_zero_text_kept_unique_columns(self):
        self.show(pd.DataFrame([("0012", "1.50")], columns=["CODE", "AMT"]))
        self.assertEqual(self.copy(self.tree), "CODE\tAMT\n0012\t1.50\n")

    def test_unique_columns_ids_are_names(self):
        self.show(pd.DataFrame([(1, "a")], columns=["ID", "NAME"]))
        self.assertEqual(list(self.tree["columns"]), ["ID", "NAME"])

    def test_switch_dup_normal_dup(self):
        dup = pd.DataFrame([(1, "a", 2)], columns=["ID", "NAME", "ID"])
        normal = pd.DataFrame([("k", "v")], columns=["KEY", "VAL"])
        self.show(dup)
        self.assertEqual(self.copy(self.tree), "ID\tNAME\tID\n1\ta\t2\n")
        self.show(normal)
        self.assertEqual(list(self.tree["columns"]), ["KEY", "VAL"])
        self.assertEqual(self.headings(self.tree), ["KEY", "VAL"])
        self.assertEqual(self.copy(self.tree), "KEY\tVAL\nk\tv\n")
        self.show(dup)
        self.assertEqual(self.headings(self.tree), ["ID", "NAME", "ID"])
        self.assertEqual(self.copy(self.tree), "ID\tNAME\tID\n1\ta\t2\n")

    def test_switch_via_result_sets(self):
        dup = pd.DataFrame([(1, "a", 2)], columns=["ID", "NAME", "ID"])
        normal = pd.DataFrame([("k", "v")], columns=["KEY", "VAL"])
        self.gui._results_grid_state["sets"] = [("A", dup, "q1"), ("B", normal, "q2")]
        self.gui._results_grid_state["set_labels"] = ["1. A", "2. B"]
        self.gui._select_results_grid_set(1)
        self.assertEqual(self.copy(self.tree), "KEY\tVAL\nk\tv\n")
        self.gui._select_results_grid_set(0)
        self.assertEqual(self.copy(self.tree), "ID\tNAME\tID\n1\ta\t2\n")

    def test_paging_with_duplicate_columns(self):
        self.gui.RESULTS_GRID_PAGE_SIZE = 2
        df = pd.DataFrame(
            [(1, "a", 2), (3, "b", 0), (5, "c", 9)], columns=["ID", "NAME", "ID"]
        )
        self.show(df, page=1)
        self.assertEqual(self.copy(self.tree), "ID\tNAME\tID\n5\tc\t9\n")


if __name__ == "__main__":
    unittest.main()
