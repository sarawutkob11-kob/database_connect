"""R16-T1 (B3): Saved Jobs scrollbar is packed before the canvas (R16-AC-14..16).

Builds the real main window on a withdrawn Tk root with APP_DIR in a tempdir.
Skipped when Tk cannot start (no display). The root is always destroyed and is
never deiconified.

Per the user's decision on R16-R1 (2026-11-27): under a withdrawn root
``winfo_width()/winfo_height()`` stay at 1, so the pixel checks of R16-AC-15
(scrollbar width > 1, canvas right edge <= scrollbar x) are replaced by pack
state checks: ``winfo_manager()``, ``pack_slaves()`` order / uniqueness and
``pack_info()``. The "not overflowing" state is forced by faking the canvas
height (``jobs_canvas.winfo_height`` patched to a large value).
"""

import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import database_connect_gui as app  # noqa: E402

BIG_HEIGHT = 100000  # fake canvas height: content never overflows


class JobsScrollbarTestBase(unittest.TestCase):
    def setUp(self):
        try:
            self.root = app.tk.Tk()
        except app.tk.TclError as e:  # pragma: no cover - no display
            self.skipTest(f"Tk not available: {e}")
        self.root.withdraw()
        self.addCleanup(self._destroy_root)
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        for p in (
            mock.patch.object(app, "APP_DIR", self._tmp.name),
            mock.patch.object(app, "messagebox"),
        ):
            p.start()
            self.addCleanup(p.stop)
        self.gui = app.DatabaseConnectorGUI(self.root)
        self.root.geometry("1100x680")
        self.root.update_idletasks()
        self.canvas = self.gui.jobs_canvas
        self.sb = self.gui.jobs_scrollbar
        self.frame = self.gui.jobs_list_frame
        self._height_patch = None

    def _destroy_root(self):
        self._unfake_height()
        try:
            self.root.destroy()
        except app.tk.TclError:
            pass

    # ---- helpers ------------------------------------------------------
    def _fake_height(self):
        if self._height_patch is None:
            self._height_patch = mock.patch.object(
                self.canvas, "winfo_height", return_value=BIG_HEIGHT
            )
            self._height_patch.start()

    def _unfake_height(self):
        if self._height_patch is not None:
            self._height_patch.stop()
            self._height_patch = None

    def _add_jobs(self, n=12):
        for _ in range(n):
            app.tk.Frame(self.gui.jobs_container, height=60, width=50).pack(fill="x")
        self.root.update_idletasks()

    def _clear_jobs(self):
        for c in list(self.gui.jobs_container.winfo_children()):
            c.destroy()
        self.root.update_idletasks()

    def _make_overflow(self):
        """Ensure content is taller than the canvas (real height)."""
        self._unfake_height()
        if not self.gui.jobs_container.winfo_children():
            self._add_jobs()
        self.root.update_idletasks()
        bounds = self.canvas.bbox("all")
        self.assertIsNotNone(bounds)
        self.assertGreater(bounds[3] - bounds[1], self.canvas.winfo_height() + 1,
                           "setup: content should overflow the canvas")

    def _make_fit(self, clear=True):
        """Simulate a profile without jobs (clear) and fake a tall canvas."""
        if clear:
            self._clear_jobs()
        self._fake_height()

    def _update(self):
        self.gui._update_jobs_scroll_state()
        self.root.update_idletasks()

    def _assert_overflow_state(self):
        self.assertEqual(self.sb.winfo_manager(), "pack")
        info = self.sb.pack_info()
        self.assertEqual(str(info["side"]), "right")
        self.assertEqual(str(info["fill"]), "y")
        slaves = self.frame.pack_slaves()
        self.assertEqual(slaves.count(self.sb), 1, f"scrollbar must appear once: {slaves}")
        self.assertEqual(slaves.count(self.canvas), 1)
        self.assertLess(slaves.index(self.sb), slaves.index(self.canvas),
                        f"scrollbar must be packed before canvas: {slaves}")
        bounds = self.canvas.bbox("all")
        self.assertEqual(
            tuple(int(float(v)) for v in str(self.canvas.cget("scrollregion")).split()),
            tuple(bounds),
        )

    def _assert_fit_state(self):
        self.assertEqual(self.sb.winfo_manager(), "")
        self.assertNotIn(self.sb, self.frame.pack_slaves())
        self.assertIn(self.canvas, self.frame.pack_slaves())
        self.assertEqual(self.canvas.yview()[0], 0.0)


class TestExposedAttributes(JobsScrollbarTestBase):
    def test_attributes_exposed(self):
        self.assertIsInstance(self.sb, app.ttk.Scrollbar)
        self.assertIsInstance(self.canvas, app.tk.Canvas)
        self.assertTrue(callable(self.gui._update_jobs_scroll_state))
        self.assertIs(self.sb.master, self.frame)
        self.assertIs(self.canvas.master, self.frame)

    def test_canvas_pack_info_unchanged(self):
        info = self.canvas.pack_info()
        self.assertEqual(str(info["side"]), "left")
        self.assertEqual(str(info["fill"]), "both")
        self.assertIn(str(info["expand"]), ("1", "True", "true"))


class TestOverflowPack(JobsScrollbarTestBase):
    """R16-AC-14."""

    def test_overflow_packs_scrollbar_before_canvas(self):
        self._make_overflow()
        self._update()
        self._assert_overflow_state()

    def test_overflow_after_forget_repacks_before_canvas(self):
        # Start hidden (empty list), then overflow -> must be re-packed before canvas
        self._make_fit()
        self._update()
        self._assert_fit_state()
        self._make_overflow()
        self._update()
        self._assert_overflow_state()

    def test_overflow_from_forced_forget_state(self):
        self.sb.pack_forget()
        self._make_overflow()
        self._update()
        self._assert_overflow_state()


class TestCycles(JobsScrollbarTestBase):
    """R16-AC-15 (pixel part replaced by pack-state checks, see module doc)."""

    def test_overflow_fit_cycles(self):
        self._make_overflow()
        self._update()
        self._assert_overflow_state()
        for i in range(4):
            with self.subTest(cycle=i, step="fit"):
                self.canvas.yview_moveto(0.5)
                self._make_fit()
                self._update()
                self._assert_fit_state()
            with self.subTest(cycle=i, step="overflow"):
                self._make_overflow()
                self._update()
                self._assert_overflow_state()

    def test_cycles_without_clearing_content(self):
        # Only the fake height flips the state; content is kept
        self._make_overflow()
        for i in range(3):
            self._update()
            self._assert_overflow_state()
            self._make_fit(clear=False)
            self._update()
            self._assert_fit_state()
            self._unfake_height()
        self._update()
        self._assert_overflow_state()

    def test_fit_forgets_under_withdrawn_root(self):
        self._make_overflow()
        self._update()
        self.assertEqual(self.sb.winfo_manager(), "pack")
        self.assertFalse(self.root.winfo_ismapped())
        self._make_fit(clear=False)
        self._update()
        self._assert_fit_state()

    def test_fit_repeated_stays_hidden(self):
        self._make_fit()
        for _ in range(3):
            self._update()
            self._assert_fit_state()

    def test_fit_resets_yview(self):
        self._make_overflow()
        self._update()
        self.canvas.yview_moveto(0.6)
        self._make_fit(clear=False)
        self._update()
        self.assertEqual(self.canvas.yview()[0], 0.0)

    def test_empty_content_scrollregion(self):
        self._make_fit()
        self._update()
        bounds = self.canvas.bbox("all")
        sr = str(self.canvas.cget("scrollregion")).split()
        if bounds is None:
            self.assertEqual([int(float(v)) for v in sr], [0, 0, 0, 0])
        else:
            self.assertEqual(tuple(int(float(v)) for v in sr), tuple(bounds))


class TestRepeatedOverflow(JobsScrollbarTestBase):
    """R16-AC-16."""

    def test_repeated_calls_keep_order_and_scrollregion(self):
        self._make_overflow()
        self._update()
        self._assert_overflow_state()
        before_info = dict(self.sb.pack_info())
        for _ in range(5):
            self._update()
            self._assert_overflow_state()
        after_info = dict(self.sb.pack_info())
        self.assertEqual(str(before_info["side"]), str(after_info["side"]))
        self.assertEqual(str(before_info["fill"]), str(after_info["fill"]))

    def test_repeated_calls_do_not_repack(self):
        self._make_overflow()
        self._update()
        with mock.patch.object(self.sb, "pack", wraps=self.sb.pack) as pk, \
                mock.patch.object(self.sb, "pack_forget", wraps=self.sb.pack_forget) as pf:
            for _ in range(4):
                self._update()
        pk.assert_not_called()
        pf.assert_not_called()
        self._assert_overflow_state()

    def test_overflow_with_more_jobs_added(self):
        self._make_overflow()
        self._update()
        for _ in range(3):
            self._add_jobs(3)
            self._update()
            self._assert_overflow_state()


if __name__ == "__main__":
    unittest.main()
