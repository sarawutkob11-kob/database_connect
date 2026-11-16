"""R5-T4: oversized string cells are omitted from Excel exports with a warning."""

import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import database_connect_gui as app  # noqa: E402


class _FakeText:
    def __init__(self):
        self.inserted = []

    def delete(self, *_args):
        pass

    def insert(self, _index, value):
        self.inserted.append(value)

    def see(self, _index):
        pass


class _FakeButton:
    def config(self, **_kwargs):
        pass


class _ImmediateThread:
    def __init__(self, target, daemon=None):
        self.target = target
        self.daemon = daemon

    def start(self):
        self.target()


class _StopEvent:
    def is_set(self):
        return False


class ExcelStringLimitTests(unittest.TestCase):
    def test_oversized_value_is_blank_and_job_is_counted_as_warning(self):
        from openpyxl import load_workbook

        job_name = "Long result"
        column_name = "payload"
        file_descriptor, export_path = tempfile.mkstemp(
            prefix="test_bugfix_c2_", suffix=".xlsx"
        )
        os.close(file_descriptor)
        dataframe = app.pd.DataFrame(
            {column_name: ["a" * 32767, "b" * 32768]}
        )
        stub = app.DatabaseConnectorGUI.__new__(app.DatabaseConnectorGUI)
        stub._block_if_busy = mock.Mock(return_value=False)
        stub._block_if_profile_mismatch = mock.Mock(return_value=False)
        stub._capture_run_target = mock.Mock(return_value=app.RunTarget(mock.Mock(), None))
        stub._reuse_last_run_results = mock.Mock(
            side_effect=lambda jobs: [dict(job) for job in jobs]
        )
        stub._start_stoppable_run = mock.Mock()
        stub._stop_event = _StopEvent()
        stub.engine = mock.Mock()
        stub.results_text = _FakeText()
        stub.export_excel_btn = _FakeButton()
        stub.root = mock.Mock()
        stub.root.after.side_effect = lambda _delay, callback: callback()
        job = {
            "name": job_name,
            "query": "SELECT payload FROM results",
            "_export_dataframe": dataframe,
        }

        try:
            with mock.patch.object(
                app.filedialog, "asksaveasfilename", return_value=export_path
            ), mock.patch.object(
                app.threading, "Thread", _ImmediateThread
            ), mock.patch.object(app, "messagebox"):
                stub.export_jobs_to_excel(jobs_override=[job])

            workbook = load_workbook(export_path, read_only=True, data_only=True)
            try:
                worksheet = workbook[job_name]
                self.assertEqual(worksheet["A2"].value, "a" * 32767)
                self.assertIsNone(worksheet["A3"].value)
            finally:
                workbook.close()

            output = "".join(stub.results_text.inserted)
            self.assertIn(f"Job '{job_name}'", output)
            self.assertIn(f"column '{column_name}'", output)
            self.assertIn("Success: 0", output)
            self.assertIn("Warning: 1", output)
        finally:
            if os.path.exists(export_path):
                os.remove(export_path)


if __name__ == "__main__":
    unittest.main()