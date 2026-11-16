"""R7-T2: run_job treats a Job without "profile" as belonging to the selected Profile.

R7-AC-6 .. R7-AC-8.
"""

import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import database_connect_gui as app  # noqa: E402
from test_bugfix_c1 import _FakeText  # noqa: E402

GUI = app.DatabaseConnectorGUI
REFUSED = "Run Job ไม่ได้เริ่มงาน"
_MISSING = object()


def make_stub(selected="P1", jobs=None):
    stub = GUI.__new__(GUI)
    stub._block_if_busy = mock.Mock(return_value=False)
    stub._running_job_ids = set()
    stub.profile_combo = mock.Mock(get=mock.Mock(return_value=selected))
    stub.results_text = _FakeText()
    stub.engine = mock.Mock(name="engine")
    stub.saved_jobs = jobs if jobs is not None else []
    stub.target = mock.Mock(name="run_target")
    stub._capture_run_target = mock.Mock(return_value=stub.target)
    stub._prepare_run_sql = mock.Mock()
    stub._confirm_data_change = mock.Mock(return_value=False)
    stub._start_stoppable_run = mock.Mock()
    return stub


def make_job(profile=_MISSING):
    job = {"name": "Daily", "query": "SELECT 1"}
    if profile is not _MISSING:
        job["profile"] = profile
    return job


def run(stub, job):
    """Run the job; the profile-mismatch block returns True so the run stops right there."""
    with mock.patch.object(GUI, "_block_if_profile_mismatch",
                           return_value=True) as block, \
            mock.patch.object(app.threading, "Thread") as thread, \
            mock.patch.object(app, "messagebox") as messagebox:
        result = stub.run_job(job)
    return result, block, thread, messagebox


def refused(stub):
    return any(REFUSED in line for line in stub.results_text.inserted)


class LegacyJobTests(unittest.TestCase):
    def test_job_without_profile_key_is_not_refused_and_proceeds(self):  # R7-AC-6
        stub = make_stub("P1")
        job = make_job()
        _result, block, thread, messagebox = run(stub, job)

        self.assertFalse(refused(stub))
        self.assertEqual(stub.results_text.inserted, [])
        stub._capture_run_target.assert_called_once_with()
        block.assert_called_once_with(stub, "Run Job", target=stub.target)
        thread.assert_not_called()
        messagebox.showerror.assert_not_called()
        self.assertNotIn("profile", job)  # the saved job is not rewritten

    def test_job_without_key_behaves_like_job_with_selected_profile(self):  # R7-AC-6
        outcomes = []
        for job in (make_job(), make_job("P1")):
            stub = make_stub("P1")
            _result, block, _thread, _mb = run(stub, job)
            outcomes.append((stub.results_text.inserted, stub._capture_run_target.call_count,
                             block.call_count))
        self.assertEqual(outcomes[0], outcomes[1])
        self.assertEqual(outcomes[0], ([], 1, 1))

    def test_legacy_job_reaches_confirmation_when_target_matches(self):  # R7-AC-6
        stub = make_stub("P1")
        stub._prepare_run_sql = mock.Mock(side_effect=lambda jobs: [j["query"] for j in jobs])
        job = make_job()
        with mock.patch.object(GUI, "_block_if_profile_mismatch", return_value=False), \
                mock.patch.object(app.threading, "Thread") as thread:
            stub.run_job(job)
        self.assertFalse(refused(stub))
        stub._prepare_run_sql.assert_called_once_with([job])
        stub._confirm_data_change.assert_called_once()
        stub._start_stoppable_run.assert_not_called()
        thread.assert_not_called()  # confirmation stub simulates Cancel


class MismatchStillRefusedTests(unittest.TestCase):
    def test_other_profile_is_refused(self):  # R7-AC-7
        stub = make_stub("P1")
        result, block, thread, messagebox = run(stub, make_job("P2"))

        self.assertIsNone(result)
        self.assertEqual(len(stub.results_text.inserted), 1)
        log = stub.results_text.inserted[0]
        self.assertTrue(log.startswith("⛔"))
        self.assertIn(REFUSED, log)
        self.assertIn("'P2'", log)
        self.assertIn("'P1'", log)
        stub._capture_run_target.assert_not_called()
        block.assert_not_called()
        stub._confirm_data_change.assert_not_called()
        thread.assert_not_called()
        messagebox.assert_not_called()

    def test_explicit_none_profile_is_refused(self):  # R7-D3 / R7-AC-8
        stub = make_stub("P1")
        _result, block, thread, _mb = run(stub, make_job(None))

        self.assertTrue(refused(stub))
        self.assertIn("'None'", stub.results_text.inserted[0])
        stub._capture_run_target.assert_not_called()
        block.assert_not_called()
        thread.assert_not_called()

    def test_busy_block_still_runs_first(self):
        stub = make_stub("P1")
        stub._block_if_busy = mock.Mock(return_value=True)
        _result, block, _thread, _mb = run(stub, make_job("P2"))
        self.assertEqual(stub.results_text.inserted, [])
        stub.profile_combo.get.assert_not_called()
        block.assert_not_called()


class ConsistencyWithJobListTests(unittest.TestCase):
    """R7-AC-8: run_job decides "matches Profile" exactly like _current_profile_jobs()."""

    def test_matrix_matches_current_profile_jobs(self):
        cases = {
            "no key": make_job(),
            "P1": make_job("P1"),
            "P2": make_job("P2"),
            "None": make_job(None),
        }
        expected_in_list = {"no key": True, "P1": True, "P2": False, "None": False}
        for label, job in cases.items():
            with self.subTest(job_profile=label):
                stub = make_stub("P1", jobs=[job])
                in_list = any(j is job for j in stub._current_profile_jobs())
                self.assertEqual(in_list, expected_in_list[label])

                run(stub, job)
                accepted = not refused(stub)
                self.assertEqual(accepted, in_list)
                self.assertEqual(stub._capture_run_target.called, in_list)


if __name__ == "__main__":
    unittest.main()
