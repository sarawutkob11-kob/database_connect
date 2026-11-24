"""Round 15 BH-6: delete_job / delete_selected_jobs roll back when
save_jobs() fails (R15-AC-17, R15-AC-18).

No Tk windows: the app is a ``__new__`` stub, messagebox is mocked and the
jobs file lives in a TemporaryDirectory. The real ``save_jobs`` and
``_restore_jobs_snapshot`` are used; failures come from the blocked flag or
from ``write_json_atomic`` raising.
"""

import copy
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import database_connect_gui as app  # noqa: E402

DELETED_MARK = "🗑️ Deleted"
FAIL_MODES = ("blocked", "write")


class FakeText:
    """Minimal stand-in for the results Text widget."""

    def __init__(self, initial: str = "previous output\n") -> None:
        self.content = initial
        self.inserts: list = []

    def delete(self, *_args) -> None:
        self.content = ""

    def insert(self, _index, text) -> None:
        self.inserts.append(text)
        self.content += text

    def see(self, *_args) -> None:
        pass


def initial_jobs():
    return [
        {"name": "J1", "profile": "P1", "query": "SELECT 1",
         "params": {"x": [1, 2, {"deep": "v"}]}, "tags": ["a", ["b"]]},
        {"name": "J2", "profile": "P1", "query": "SELECT 2",
         "excel": {"rows": [[1, 2], [3]], "file": "f.xlsx"}},
        {"name": "J3", "profile": "P2", "query": "SELECT 3", "meta": {"m": [9]}},
        {"name": "J4", "profile": "P1", "query": "SELECT 4"},
    ]


class _Base(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.jobs_file = os.path.join(self.tmp.name, "saved_jobs.json")

        self.stub = app.DatabaseConnectorGUI.__new__(app.DatabaseConnectorGUI)
        self.stub.root = object()
        self.stub.jobs_file = self.jobs_file
        self.stub.results_text = FakeText()
        self.stub.profile_combo = mock.Mock()
        self.stub.profile_combo.get.return_value = "P1"
        self.stub.saved_jobs = initial_jobs()
        self.stub._checked_job_ids = set()
        self.stub.update_jobs_list = mock.Mock()

        with open(self.jobs_file, "w", encoding="utf-8") as fh:
            json.dump(self.stub.saved_jobs, fh)
        with open(self.jobs_file, "rb") as fh:
            self.file_before = fh.read()

        self.mb = mock.patch.object(app, "messagebox").start()
        self.addCleanup(mock.patch.stopall)
        self.mb.askyesno.return_value = True

    def arm_failure(self, mode: str) -> None:
        if mode == "blocked":
            self.stub._jobs_save_blocked = True
        else:
            mock.patch.object(
                app, "write_json_atomic", side_effect=OSError("disk full")
            ).start()

    def file_bytes(self) -> bytes:
        with open(self.jobs_file, "rb") as fh:
            return fh.read()

    def assert_jobs_restored(self, list_before, items_before, deep_before) -> None:
        self.assertIs(self.stub.saved_jobs, list_before)
        self.assertEqual(len(self.stub.saved_jobs), len(items_before))
        for got, orig in zip(self.stub.saved_jobs, items_before):
            self.assertIs(got, orig)
        self.assertEqual(self.stub.saved_jobs, deep_before)
        self.assertEqual([j["name"] for j in self.stub.saved_jobs],
                         ["J1", "J2", "J3", "J4"])

    def assert_no_success_output(self) -> None:
        self.assertNotIn(DELETED_MARK, self.stub.results_text.content)
        self.assertFalse(any(DELETED_MARK in t for t in self.stub.results_text.inserts))
        self.assertNotIn("Remaining", self.stub.results_text.content)
        self.assertEqual(self.stub.results_text.content, "previous output\n")
        self.stub.update_jobs_list.assert_not_called()


class TestDeleteJobRollback(_Base):
    """R15-AC-17."""

    def test_save_failure_restores_list(self) -> None:
        for mode in FAIL_MODES:
            for idx in (0, 1, 3):
                with self.subTest(mode=mode, idx=idx):
                    self.setUp()
                    self.arm_failure(mode)
                    list_before = self.stub.saved_jobs
                    items_before = list(list_before)
                    deep_before = copy.deepcopy(list_before)
                    name = list_before[idx]["name"]

                    self.stub.delete_job(idx, name)

                    self.assert_jobs_restored(list_before, items_before, deep_before)
                    self.assert_no_success_output()
                    self.mb.showerror.assert_called_once()
                    self.assertEqual(self.file_bytes(), self.file_before)

    def test_save_success_deletes(self) -> None:
        list_before = self.stub.saved_jobs
        j1, j3, j4 = list_before[0], list_before[2], list_before[3]

        self.stub.delete_job(1, "J2")

        self.assertEqual([j["name"] for j in self.stub.saved_jobs], ["J1", "J3", "J4"])
        self.assertIs(self.stub.saved_jobs[0], j1)
        self.assertIs(self.stub.saved_jobs[1], j3)
        self.assertIs(self.stub.saved_jobs[2], j4)
        self.stub.update_jobs_list.assert_called_once()
        content = self.stub.results_text.content
        self.assertIn("🗑️ Deleted: J2\n", content)
        self.assertIn("📊 Remaining: 3 jobs\n", content)
        self.assertNotIn("previous output", content)
        self.mb.showerror.assert_not_called()
        with open(self.jobs_file, encoding="utf-8") as fh:
            self.assertEqual([j["name"] for j in json.load(fh)], ["J1", "J3", "J4"])

    def test_answer_no_changes_nothing(self) -> None:
        self.mb.askyesno.return_value = False
        save = mock.patch.object(self.stub, "save_jobs", create=True).start()
        list_before = self.stub.saved_jobs
        items_before = list(list_before)
        deep_before = copy.deepcopy(list_before)

        self.stub.delete_job(0, "J1")

        self.assert_jobs_restored(list_before, items_before, deep_before)
        self.assert_no_success_output()
        save.assert_not_called()
        self.assertEqual(self.file_bytes(), self.file_before)


class TestDeleteSelectedJobsRollback(_Base):
    """R15-AC-18."""

    def tick(self, *indexes) -> None:
        for i in indexes:
            self.stub._checked_job_ids.add(id(self.stub.saved_jobs[i]))

    def test_save_failure_restores_list_and_checked_ids(self) -> None:
        for mode in FAIL_MODES:
            with self.subTest(mode=mode):
                self.setUp()
                self.arm_failure(mode)
                # Two ticked jobs of the current profile (P1) + one of P2.
                self.tick(0, 3, 2)
                checked_obj = self.stub._checked_job_ids
                checked_before = set(checked_obj)
                list_before = self.stub.saved_jobs
                items_before = list(list_before)
                deep_before = copy.deepcopy(list_before)

                self.stub.delete_selected_jobs()

                self.assert_jobs_restored(list_before, items_before, deep_before)
                self.assertIs(self.stub._checked_job_ids, checked_obj)
                self.assertEqual(self.stub._checked_job_ids, checked_before)
                self.assert_no_success_output()
                self.mb.showerror.assert_called_once()
                self.assertEqual(self.file_bytes(), self.file_before)

    def test_save_success_deletes_selected(self) -> None:
        self.tick(0, 3, 2)  # J3 belongs to P2 -> must not be deleted
        checked_obj = self.stub._checked_job_ids
        j2, j3 = self.stub.saved_jobs[1], self.stub.saved_jobs[2]

        self.stub.delete_selected_jobs()

        self.assertEqual([j["name"] for j in self.stub.saved_jobs], ["J2", "J3"])
        self.assertIs(self.stub.saved_jobs[0], j2)
        self.assertIs(self.stub.saved_jobs[1], j3)
        self.assertIs(self.stub._checked_job_ids, checked_obj)
        self.assertEqual(self.stub._checked_job_ids, {id(j3)})
        self.stub.update_jobs_list.assert_called_once()
        content = self.stub.results_text.content
        self.assertIn("🗑️ Deleted 2 job(s)\n", content)
        self.assertIn("📊 Remaining: 2 jobs\n", content)
        self.mb.showerror.assert_not_called()
        with open(self.jobs_file, encoding="utf-8") as fh:
            self.assertEqual([j["name"] for j in json.load(fh)], ["J2", "J3"])

    def test_answer_no_changes_nothing(self) -> None:
        self.mb.askyesno.return_value = False
        save = mock.patch.object(self.stub, "save_jobs", create=True).start()
        self.tick(0, 3)
        checked_obj = self.stub._checked_job_ids
        checked_before = set(checked_obj)
        list_before = self.stub.saved_jobs
        items_before = list(list_before)
        deep_before = copy.deepcopy(list_before)

        self.stub.delete_selected_jobs()

        self.mb.askyesno.assert_called_once()
        self.assert_jobs_restored(list_before, items_before, deep_before)
        self.assertIs(self.stub._checked_job_ids, checked_obj)
        self.assertEqual(self.stub._checked_job_ids, checked_before)
        self.assert_no_success_output()
        save.assert_not_called()
        self.assertEqual(self.file_bytes(), self.file_before)

    def test_nothing_ticked_returns_without_prompt(self) -> None:
        self.tick(2)  # only a P2 job ticked -> nothing of current profile
        list_before = self.stub.saved_jobs
        deep_before = copy.deepcopy(list_before)

        self.stub.delete_selected_jobs()

        self.mb.askyesno.assert_not_called()
        self.assertIs(self.stub.saved_jobs, list_before)
        self.assertEqual(self.stub.saved_jobs, deep_before)
        self.assert_no_success_output()


if __name__ == "__main__":
    unittest.main()
