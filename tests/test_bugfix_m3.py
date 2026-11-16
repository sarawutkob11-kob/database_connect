"""R5-T9: debug mode snapshots and New Profile UI thread safety."""

import os
import sys
import threading
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import database_connect_gui as app  # noqa: E402


GUI = app.DatabaseConnectorGUI
REAL_THREAD = threading.Thread


class _ThreadVariable:
    def __init__(self, value):
        self.value = value
        self.read_threads = []
        self.forbid_get = False

    def get(self):
        if self.forbid_get:
            raise AssertionError("worker read the Tk debug_mode variable")
        self.read_threads.append(threading.get_ident())
        return self.value

    def trace_add(self, *_args):
        pass


class _HeldThread:
    def __init__(self, target, args=(), daemon=None):
        self.target = target
        self.args = args
        self.daemon = daemon

    def start(self):
        pass


class _TrackedWidget:
    def __init__(self, value="", text="", **kwargs):
        self.value = value
        self.text = text
        self.kwargs = kwargs
        self.calls = []
        self.command = kwargs.get("command")
        self.state = kwargs.get("state")

    def _record(self, name):
        self.calls.append((name, threading.get_ident()))

    def __getattr__(self, name):
        if name.startswith("winfo_"):
            return lambda *args, **kwargs: self._record(name) or 800
        return lambda *args, **kwargs: self._record(name)

    def get(self, *_args):
        self._record("get")
        return self.value

    def set(self, value):
        self._record("set")
        self.value = value

    def cget(self, key):
        self._record("cget")
        return getattr(self, key, self.kwargs.get(key))

    def insert(self, _index, value):
        self._record("insert")
        self.value = value

    def delete(self, *_args):
        self._record("delete")
        self.value = ""

    def config(self, **kwargs):
        self._record("config")
        self.text = kwargs.get("text", self.text)
        self.state = kwargs.get("state", self.state)

    configure = config


class _Root:
    def __init__(self):
        self.after_calls = []

    def after(self, delay, callback):
        self.after_calls.append((delay, callback, threading.get_ident()))

    def update(self):
        pass


class DebugModeSnapshotTests(unittest.TestCase):
    def test_execute_query_reads_debug_mode_once_before_worker_and_passes_snapshot(self):
        main_thread = threading.get_ident()
        stub = GUI.__new__(GUI)
        engine = mock.Mock()
        engine.dialect.name = "sqlite"
        stub.engine = engine
        stub.debug_mode = _ThreadVariable(True)
        stub._block_if_busy = mock.Mock(return_value=False)
        stub._capture_run_target = mock.Mock(return_value=app.RunTarget(engine, None))
        stub._prepare_run_sql = mock.Mock(return_value=["SELECT 1"])
        stub._confirm_data_change = mock.Mock(return_value=True)
        stub._start_stoppable_run = mock.Mock()
        stub._create_loading_dialog_with_retry = mock.Mock(return_value=mock.Mock())
        stub.sql_context = mock.Mock()
        stub.sql_context.get.return_value = "SELECT 1"
        stub.results_text = mock.Mock()
        stub.execute_btn = mock.Mock()
        stub.root = _Root()
        stub.is_select_query = mock.Mock(return_value=True)
        stub.read_sql_dataframe = mock.Mock(return_value=type("Frame", (), {
            "shape": (1, 1), "__len__": lambda self: 1
        })())

        workers = []

        def capture_thread(target, args=(), daemon=None):
            worker = _HeldThread(target, args, daemon)
            workers.append(worker)
            return worker

        with mock.patch.object(app.threading, "Thread", side_effect=capture_thread), \
                mock.patch.object(GUI, "_block_if_profile_mismatch", return_value=False), \
                mock.patch("builtins.print") as debug_print:
            stub.execute_query()

            self.assertEqual(stub.debug_mode.read_threads, [main_thread])
            self.assertEqual(len(workers), 1)
            stub.debug_mode.value = False
            stub.debug_mode.forbid_get = True

            worker_thread = REAL_THREAD(target=workers[0].target)
            worker_thread.start()
            worker_thread.join()

        stub.read_sql_dataframe.assert_called_once_with("SELECT 1", engine=engine)
        self.assertTrue(
            any("Starting query execution" in str(call) for call in debug_print.call_args_list)
        )
        self.assertEqual(len(stub.root.after_calls), 1)


class NewProfileConnectionThreadTests(unittest.TestCase):
    def test_connection_result_is_queued_and_widgets_are_updated_on_main_thread(self):
        main_thread = threading.get_ident()
        stub = GUI.__new__(GUI)
        stub.root = _Root()
        stub._block_if_busy = mock.Mock(return_value=False)
        stub.get_connection_string = mock.Mock(return_value="mock-connection")
        stub.get_connect_args = mock.Mock(return_value={})

        widgets = []
        entries = []
        buttons = []
        variables = []

        def make_widget(*_args, **kwargs):
            widget = _TrackedWidget(**kwargs)
            widgets.append(widget)
            return widget

        def make_entry(*args, **kwargs):
            widget = make_widget(*args, **kwargs)
            entries.append(widget)
            return widget

        def make_variable(*_args, **kwargs):
            variable = _ThreadVariable(kwargs.get("value"))
            variables.append(variable)
            return variable

        test_callback = []

        def make_button(_parent, text, command, **kwargs):
            outer = _TrackedWidget()
            button = _TrackedWidget(text=text, command=command, **kwargs)
            widgets.extend((outer, button))
            buttons.append(button)
            if text.startswith("🔌"):
                test_callback.append(command)
            return outer, button

        workers = []

        def capture_thread(target, args=(), daemon=None):
            worker = _HeldThread(target, args, daemon)
            workers.append(worker)
            return worker

        result_label = None
        test_button = None
        with mock.patch.object(app.tk, "Toplevel", side_effect=make_widget), \
                mock.patch.object(app.tk, "Frame", side_effect=make_widget), \
            mock.patch.object(app.tk, "Canvas", side_effect=make_widget), \
                mock.patch.object(app.tk, "Label", side_effect=make_widget), \
                mock.patch.object(app.tk, "StringVar", side_effect=make_variable), \
                mock.patch.object(app.ttk, "Entry", side_effect=make_entry), \
                mock.patch.object(app.ttk, "Label", side_effect=make_widget), \
                mock.patch.object(app, "ui_round_frame", side_effect=lambda *a, **k: (
                    _TrackedWidget(), _TrackedWidget()
                )), \
                mock.patch.object(app, "ui_round_frame_set") as set_frame, \
                mock.patch.object(app, "ui_button", side_effect=make_button), \
                mock.patch.object(app.threading, "Thread", side_effect=capture_thread), \
                mock.patch.object(app, "create_engine") as create_engine, \
                mock.patch.object(app.messagebox, "showerror") as showerror:
            stub.new_profile_dialog()

            self.assertEqual(len(test_callback), 1)
            self.assertEqual(len(entries), 6)
            result_label = next(
                widget for widget in widgets
                if widget.kwargs.get("wraplength") == 540
            )
            test_button = next(button for button in buttons if button.command)
            entries[1].value = "localhost"
            entries[2].value = "5432"
            entries[3].value = "example"
            entries[4].value = "tester"
            entries[5].value = "secret"
            test_callback[0]()

            self.assertEqual(len(workers), 1)
            engine = create_engine.return_value
            connection = engine.connect.return_value.__enter__.return_value
            worker_thread = REAL_THREAD(target=workers[0].target)
            worker_thread.start()
            worker_thread.join()

            self.assertEqual(len(stub.root.after_calls), 1)
            delay, callback, queued_from = stub.root.after_calls[0]
            self.assertEqual(delay, 0)
            self.assertNotEqual(queued_from, main_thread)
            self.assertTrue(callable(callback))
            self.assertFalse(any(
                call_thread == queued_from
                for widget in widgets
                for _name, call_thread in widget.calls
            ))
            self.assertTrue(connection.execute.called)
            self.assertIn("กำลังทดสอบ", result_label.text)
            self.assertEqual(test_button.state, "disabled")

            callback()

        self.assertIn("ทดสอบเชื่อมต่อสำเร็จ", result_label.text)
        self.assertEqual(test_button.state, "normal")
        self.assertGreaterEqual(set_frame.call_count, 2)
        showerror.assert_not_called()
        self.assertTrue(all(
            call_thread == main_thread
            for widget in widgets
            for _name, call_thread in widget.calls
        ))


if __name__ == "__main__":
    unittest.main()