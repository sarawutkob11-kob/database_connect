"""T13: Stop button in the list_tables Loading window (AC-38; AC-37 is Manual/GUI).

tk.Toplevel, ttk and ui_rbutton are patched with MagicMock (design section 7).
"""

import os
import sys
import threading
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import database_connect_gui as app  # noqa: E402

GUI = app.DatabaseConnectorGUI


class FakeWidget:
    def __init__(self, text="", state="normal"):
        self.text = text
        self.state = state

    def cget(self, key):
        return self.text if key == "text" else self.state

    def __getitem__(self, key):
        return self.cget(key)

    def config(self, **kw):
        self.state = kw.get("state", self.state)
        self.text = kw.get("text", self.text)

    configure = config


class FakeText:
    def __init__(self):
        self.inserted = []

    def insert(self, _i, v):
        self.inserted.append(v)

    def see(self, *_a):
        pass

    def delete(self, *_a):
        pass


class FakeEntry:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value


def make_stub():
    stub = GUI.__new__(GUI)
    stub._active_db_lock = threading.Lock()
    stub._active_db_connections = {}
    stub._running_job_ids = set()
    stub._batch_running = False
    stub._stop_event = threading.Event()
    stub._stop_buttons = []
    stub.execute_btn = FakeWidget("▶  Run")
    stub.export_excel_btn = FakeWidget("⇩  Export")
    stub.inspect_btn = FakeWidget("▦  Tables")
    stub.results_text = FakeText()
    stub.db_type = FakeEntry("PostgreSQL")
    stub.db_name = FakeEntry("")
    stub.engine = mock.MagicMock(name="engine")
    stub.root = mock.Mock(name="root")
    return stub


class _Patches:
    def __enter__(self):
        self._p = [
            mock.patch.object(app.tk, "Toplevel"),
            mock.patch.object(app, "ttk"),
            mock.patch.object(app, "ui_rbutton"),
        ]
        self.toplevel, self.ttk, self.rbutton = (p.start() for p in self._p)
        self.dialog = self.toplevel.return_value
        self.dialog.winfo_screenwidth.return_value = 1920
        self.dialog.winfo_screenheight.return_value = 1080
        self.dialog.winfo_width.return_value = 300
        self.dialog.winfo_height.return_value = 250
        self.button = self.rbutton.return_value
        return self

    def __exit__(self, *exc):
        for p in reversed(self._p):
            p.stop()
        return False


class LoadingDialogTests(unittest.TestCase):
    """AC-38"""

    def test_dialog_has_stop_button_registered(self):
        stub = make_stub()
        stub._register_stop_button = mock.Mock(name="_register_stop_button")
        with _Patches() as p:
            dialog = stub._create_list_tables_loading_dialog()
        self.assertIs(dialog, p.dialog)
        p.toplevel.assert_called_once_with(stub.root)
        p.dialog.grab_set.assert_called_once_with()
        p.rbutton.assert_called_once()
        args, kwargs = p.rbutton.call_args
        params = list(args) + list(kwargs.values())
        self.assertIs(args[0], p.dialog)
        self.assertIn(stub.stop_running_queries, params)
        self.assertEqual(args[2] if len(args) > 2 else kwargs.get("command"),
                         stub.stop_running_queries)
        self.assertTrue(any("Stop" in str(a) for a in params))
        p.button.pack.assert_called_once()
        stub._register_stop_button.assert_called_once_with(p.button)

    def test_real_register_disables_button_and_tracks_it(self):
        stub = make_stub()
        with _Patches() as p:
            stub._create_list_tables_loading_dialog()
        self.assertEqual(stub._stop_buttons, [p.button])
        p.button.config.assert_called_with(state="disabled")

    def test_list_tables_uses_new_dialog_and_starts_thread(self):
        stub = make_stub()
        dialog = mock.Mock(name="dialog")
        with mock.patch.object(GUI, "_create_list_tables_loading_dialog",
                               return_value=dialog) as create, \
                mock.patch.object(app.threading, "Thread") as thread, \
                mock.patch.object(app.tk, "Toplevel") as toplevel:
            stub.list_tables()
        create.assert_called_once_with()
        toplevel.assert_not_called()  # the window is built only by the new method
        thread.assert_called_once()
        thread.return_value.start.assert_called_once_with()
        self.assertEqual(stub.inspect_btn.text, "⏳ Loading...")
        self.assertEqual(stub.inspect_btn.state, "disabled")

    def test_worker_hands_the_same_dialog_to_success(self):
        stub = make_stub()
        stub.db_name = FakeEntry("db")
        dialog = mock.Mock(name="dialog")
        targets = []
        stub.root.after.side_effect = lambda _ms, fn: fn()
        stub.on_list_tables_success = mock.Mock()
        inspector = mock.Mock()
        inspector.get_schema_names.return_value = []
        with mock.patch.object(GUI, "_create_list_tables_loading_dialog", return_value=dialog), \
                mock.patch.object(app.threading, "Thread",
                                  side_effect=lambda target=None, **k: targets.append(target)
                                  or mock.Mock()), \
                mock.patch.object(app, "inspect", return_value=inspector):
            stub.list_tables()
            targets[0]()
        self.assertIs(stub.on_list_tables_success.call_args.args[1], dialog)


class AfterFinishTests(unittest.TestCase):
    def test_success_closes_window_and_resets_tables(self):
        for table_list in ([], [{"Database": "d", "Schema": "s", "Table": "t"}]):
            with self.subTest(n=len(table_list)):
                stub = make_stub()
                stub.inspect_btn = FakeWidget("⏳ Loading...", "disabled")
                stub.show_table_popup = mock.Mock()
                dialog = mock.Mock()
                with mock.patch.object(app, "messagebox"):
                    stub.on_list_tables_success(table_list, dialog, True)
                dialog.destroy.assert_called_once_with()
                self.assertEqual((stub.inspect_btn.state, stub.inspect_btn.text),
                                 ("normal", "▦  Tables"))

    def test_error_closes_window_and_resets_tables(self):
        stub = make_stub()
        stub.inspect_btn = FakeWidget("⏳ Loading...", "disabled")
        dialog = mock.Mock()
        with mock.patch.object(app, "messagebox") as mb:
            stub.on_list_tables_error(RuntimeError("ORA-01013: user requested cancel"), dialog)
        dialog.destroy.assert_called_once_with()
        self.assertEqual((stub.inspect_btn.state, stub.inspect_btn.text), ("normal", "▦  Tables"))
        mb.showerror.assert_called_once()

    def test_error_with_already_closed_window(self):
        stub = make_stub()
        dialog = mock.Mock()
        dialog.destroy.side_effect = app.tk.TclError("gone")
        with mock.patch.object(app, "messagebox"):
            stub.on_list_tables_error(RuntimeError("x"), dialog)
        self.assertEqual(stub.inspect_btn.text, "▦  Tables")


class PollTests(unittest.TestCase):
    def _poll(self, stub):
        with mock.patch.object(GUI, "_apply_run_lock"):
            stub._refresh_stop_buttons()

    def test_closed_window_button_removed(self):
        stub = make_stub()
        alive = mock.Mock(name="alive")
        alive.winfo_exists.return_value = 1
        alive.__getitem__ = mock.Mock(return_value="disabled")
        gone = mock.Mock(name="gone")
        gone.winfo_exists.return_value = 0
        broken = mock.Mock(name="broken")
        broken.winfo_exists.side_effect = app.tk.TclError("bad window path")
        stub._stop_buttons = [alive, gone, broken]
        self._poll(stub)
        self.assertEqual(stub._stop_buttons, [alive])
        gone.config.assert_not_called()

    def test_loading_enables_registered_button_and_stop_works(self):
        stub = make_stub()
        with _Patches() as p:
            stub._create_list_tables_loading_dialog()
        btn = p.button
        state = {"value": "disabled"}
        btn.winfo_exists.return_value = 1
        btn.__getitem__ = mock.Mock(side_effect=lambda k: state["value"])
        btn.config.side_effect = lambda **kw: state.update(value=kw.get("state", state["value"]))
        stub.inspect_btn = FakeWidget("⏳ Loading...", "disabled")
        self._poll(stub)
        self.assertEqual(state["value"], "normal")
        # the button's command = stop_running_queries
        stub.stop_running_queries()
        self.assertTrue(stub._stop_event.is_set())
        self.assertIn("Stop requested", stub.results_text.inserted[-1])
        # Tables finished: next poll disables it again
        stub.inspect_btn = FakeWidget("▦  Tables")
        self._poll(stub)
        self.assertEqual(state["value"], "disabled")


class SqlEditorDialogUntouchedTests(unittest.TestCase):
    """The SQL Editor Loading window is out of scope (spec/design R8)."""

    def test_sql_editor_dialog_has_no_stop_button(self):
        import inspect as _inspect

        src = _inspect.getsource(GUI._create_loading_dialog_with_retry)
        self.assertIn("grab_set()", src)
        self.assertNotIn("_register_stop_button", src)
        self.assertNotIn("stop_running_queries", src)


if __name__ == "__main__":
    unittest.main()
