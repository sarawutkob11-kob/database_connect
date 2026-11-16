"""R5-T10: export text beginning with '=' remains a literal Excel string."""

import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import database_connect_gui as app  # noqa: E402


class _FakeText:
    def delete(self, *_args):
        pass

    def insert(self, *_args):
        pass

    def see(self, *_args):
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


class _FailingFrame:
    def copy(self):
        raise ValueError("=failure literal")


class ExportLiteralTextTests(unittest.TestCase):
    def test_leading_equals_is_saved_as_literal_in_all_export_paths(self):
        from openpyxl import load_workbook

        with tempfile.TemporaryDirectory(prefix="test_bugfix_m2_") as temp_dir:
            export_path = os.path.join(temp_dir, "export.xlsx")
            jobs = [
                {
                    "name": "Annotation",
                    "query": "=annotation literal\nannotation second line",
                    "_export_dataframe": app.pd.DataFrame({"result": ["ok"]}),
                },
                {
                    "name": "No Data",
                    "query": "=no data literal\nno data second line",
                    "_export_dataframe": app.pd.DataFrame(columns=["result"]),
                },
                {
                    "name": "Failed",
                    "query": "=failed query literal",
                    "_export_dataframe": _FailingFrame(),
                },
                {"name": "Skipped", "query": "=skipped query literal"},
            ]

            stub = app.DatabaseConnectorGUI.__new__(app.DatabaseConnectorGUI)
            stub._block_if_busy = mock.Mock(return_value=False)
            stub._block_if_profile_mismatch = mock.Mock(return_value=False)
            stub._capture_run_target = mock.Mock(
                return_value=app.RunTarget(mock.Mock(name="engine"), None)
            )
            stub._reuse_last_run_results = mock.Mock(
                side_effect=lambda export_jobs: [dict(job) for job in export_jobs]
            )
            stub._start_stoppable_run = mock.Mock()
            stub._stop_event = _StopEvent()
            stub.engine = mock.Mock(name="engine")
            stub.results_text = _FakeText()
            stub.export_excel_btn = _FakeButton()
            stub.root = mock.Mock(name="root")
            stub.root.after.side_effect = lambda _delay, callback: callback()

            with mock.patch.object(
                app.filedialog, "asksaveasfilename", return_value=export_path
            ), mock.patch.object(app.threading, "Thread", _ImmediateThread), mock.patch.object(
                app, "messagebox"
            ):
                stub.export_jobs_to_excel(jobs_override=jobs)

            workbook = load_workbook(export_path, data_only=False)
            try:
                def assert_literal(sheet_name, coordinate, expected):
                    cell = workbook[sheet_name][coordinate]
                    self.assertEqual(cell.data_type, "s", (sheet_name, coordinate))
                    self.assertEqual(cell.value, expected, (sheet_name, coordinate))

                assert_literal("Annotation", "A4", "=annotation literal")
                assert_literal("No Data", "A3", "=no data literal")
                assert_literal("No Data", "A4", "no data second line")

                assert_literal("Failed", "A2", "Failed")
                assert_literal("Failed", "B2", "=failure literal")
                assert_literal("Failed", "C2", "=failed query literal")

                assert_literal("Skipped", "A2", "Skipped")
                assert_literal(
                    "Skipped", "B2", "Not a SELECT query - not executed during export"
                )
                assert_literal("Skipped", "C2", "=skipped query literal")
            finally:
                workbook.close()


if __name__ == "__main__":
    unittest.main()
