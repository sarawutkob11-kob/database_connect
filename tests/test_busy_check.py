"""T1: central busy check (_is_busy / _log_blocked / _block_if_busy).

AC-20, AC-21, AC-22, AC-23 at logic level. No Tk window, no database.
"""

import os
import sys
import threading
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import database_connect_gui as app  # noqa: E402


class _FakeButton:
    def __init__(self, text: str = "") -> None:
        self.text = text

    def cget(self, key: str):
        if key != "text":
            raise KeyError(key)
        return self.text


class _FakeText:
    """results_text fake with insert + see."""

    def __init__(self) -> None:
        self.inserted: list = []
        self.seen: list = []
        self.calls: list = []

    def insert(self, index, value) -> None:
        self.inserted.append((index, value))
        self.calls.append("insert")

    def see(self, index) -> None:
        self.seen.append(index)
        self.calls.append("see")


def make_stub(
    *,
    running_job_ids=None,
    with_running_job_ids: bool = True,
    connections=None,
    batch_running: bool = False,
    execute_text: str = "▶  Run",
    export_text: str = "Export Excel",
    inspect_text: str = "Tables",
):
    stub = app.DatabaseConnectorGUI.__new__(app.DatabaseConnectorGUI)
    stub._active_db_lock = threading.Lock()
    stub._active_db_connections = dict(connections or {})
    stub._batch_running = batch_running
    stub.execute_btn = _FakeButton(execute_text)
    stub.export_excel_btn = _FakeButton(export_text)
    stub.inspect_btn = _FakeButton(inspect_text)
    if with_running_job_ids:
        stub._running_job_ids = set(running_job_ids or ())
    stub.results_text = _FakeText()
    return stub


class IsBusyTests(unittest.TestCase):
    def test_ac23_idle_is_not_busy(self):
        self.assertIs(make_stub()._is_busy(), False)

    def test_ac20_single_job_running_is_busy(self):
        stub = make_stub(running_job_ids={"job-1"})
        # Sanity: the old check alone would miss this case.
        self.assertFalse(stub._is_query_running())
        self.assertIs(stub._is_busy(), True)

    def test_ac21_active_connection_is_busy(self):
        stub = make_stub(connections={object(): object()})
        self.assertIs(stub._is_busy(), True)

    def test_ac22_inspect_loading_is_busy(self):
        stub = make_stub(inspect_text="⏳ Loading...")
        self.assertFalse(stub._is_query_running())
        self.assertIs(stub._is_busy(), True)

    def test_batch_running_is_busy(self):
        self.assertIs(make_stub(batch_running=True)._is_busy(), True)

    def test_execute_loading_is_busy(self):
        self.assertIs(make_stub(execute_text="⏳ Loading...")._is_busy(), True)

    def test_export_exporting_is_busy(self):
        self.assertIs(make_stub(export_text="⏳ Exporting...")._is_busy(), True)

    def test_missing_running_job_ids_attribute_does_not_crash(self):
        stub = make_stub(with_running_job_ids=False)
        self.assertFalse(hasattr(stub, "_running_job_ids"))
        self.assertIs(stub._is_busy(), False)

    def test_running_job_ids_none_is_not_busy(self):
        stub = make_stub()
        stub._running_job_ids = None
        self.assertIs(stub._is_busy(), False)

    def test_empty_containers_are_not_busy(self):
        for empty in (set(), [], {}, ()):
            with self.subTest(empty=empty):
                stub = make_stub()
                stub._running_job_ids = empty
                self.assertIs(stub._is_busy(), False)

    def test_multiple_jobs_running_is_busy(self):
        self.assertIs(make_stub(running_job_ids={"a", "b"})._is_busy(), True)

    def test_inspect_text_without_loading_is_not_busy(self):
        for text in ("Tables", "", "📋 Tables", "loading"):
            with self.subTest(text=text):
                # "Loading" check is case-sensitive like _is_query_running.
                self.assertIs(make_stub(inspect_text=text)._is_busy(), False)

    def test_returns_bool(self):
        self.assertIsInstance(make_stub(running_job_ids={"x"})._is_busy(), bool)
        self.assertIsInstance(make_stub()._is_busy(), bool)


class LogBlockedTests(unittest.TestCase):
    def test_writes_message_and_scrolls_without_popup(self):
        stub = make_stub()
        with mock.patch.object(app, "messagebox") as mb, \
                mock.patch.object(app, "ui_dialog") as dlg:
            stub._log_blocked("Connect")
        self.assertEqual(len(stub.results_text.inserted), 1)
        index, message = stub.results_text.inserted[0]
        self.assertEqual(index, app.tk.END)
        self.assertIn("Connect", message)
        self.assertTrue(message.endswith("\n"))
        self.assertEqual(
            message,
            "⏳ Connect: ทำไม่ได้ระหว่างที่มีงานรันอยู่ — "
            "รอให้งานเสร็จหรือกด ⏹ Stop ก่อน\n",
        )
        self.assertEqual(stub.results_text.seen, [app.tk.END])
        self.assertEqual(stub.results_text.calls, ["insert", "see"])
        self.assertEqual(mb.mock_calls, [])
        dlg.assert_not_called()

    def test_action_name_is_used_verbatim(self):
        for action in ("Run", "Change profile", "Import profiles", ""):
            with self.subTest(action=action):
                stub = make_stub()
                stub._log_blocked(action)
                _, message = stub.results_text.inserted[0]
                self.assertTrue(message.startswith(f"⏳ {action}: "))
                self.assertEqual(message.count("\n"), 1)


class BlockIfBusyTests(unittest.TestCase):
    def test_busy_returns_true_and_logs_once(self):
        stub = make_stub(running_job_ids={"job-1"})
        with mock.patch.object(app, "messagebox") as mb:
            self.assertIs(stub._block_if_busy("Run"), True)
        self.assertEqual(len(stub.results_text.inserted), 1)
        self.assertIn("Run", stub.results_text.inserted[0][1])
        self.assertEqual(len(stub.results_text.seen), 1)
        self.assertEqual(mb.mock_calls, [])

    def test_idle_returns_false_and_writes_nothing(self):
        stub = make_stub()
        self.assertIs(stub._block_if_busy("Run"), False)
        self.assertEqual(stub.results_text.calls, [])

    def test_each_busy_source_blocks(self):
        cases = {
            "job": dict(running_job_ids={"j"}),
            "connection": dict(connections={1: 2}),
            "inspect": dict(inspect_text="Loading"),
            "batch": dict(batch_running=True),
            "execute": dict(execute_text="Loading"),
            "export": dict(export_text="Exporting"),
        }
        for name, kwargs in cases.items():
            with self.subTest(source=name):
                stub = make_stub(**kwargs)
                self.assertIs(stub._block_if_busy("Connect"), True)
                self.assertEqual(stub.results_text.calls, ["insert", "see"])

    def test_uses_is_busy(self):
        stub = make_stub()
        with mock.patch.object(
            app.DatabaseConnectorGUI, "_is_busy", return_value=True
        ) as busy, mock.patch.object(
            app.DatabaseConnectorGUI, "_log_blocked"
        ) as log:
            self.assertIs(stub._block_if_busy("Tables"), True)
        busy.assert_called_once_with()
        log.assert_called_once_with("Tables")

    def test_missing_running_job_ids_idle_does_not_crash(self):
        stub = make_stub(with_running_job_ids=False)
        self.assertIs(stub._block_if_busy("Run"), False)


if __name__ == "__main__":
    unittest.main()
