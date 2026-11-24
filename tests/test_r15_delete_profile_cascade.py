"""R15-T8 (BH-10): delete_profile asks whether to delete the profile's Jobs /
Script Groups, saves Profile -> Job -> Groups, and rolls back a failed step.

R15-R2: every stub sets ``script_groups`` and mocks (or redirects to a temp dir)
save_jobs / save_script_groups, so APP_DIR files are never read or written.
"""

import copy
import json
import os
import sys
import tempfile
import threading
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import database_connect_gui as app  # noqa: E402


class _Combo:
    def __init__(self, value: str = "") -> None:
        self.value = value

    def get(self, *_args) -> str:
        return self.value


class _Text:
    def __init__(self) -> None:
        self.inserted: list = []

    def insert(self, _index, value) -> None:
        self.inserted.append(value)

    def see(self, *_args) -> None:
        return None

    @property
    def joined(self) -> str:
        return "".join(self.inserted)


JOB_P1 = {"name": "p-job-1", "query": "SELECT 1", "profile": "P"}
JOB_P2 = {"name": "p-job-2", "query": "SELECT 2", "profile": "P"}
JOB_Q = {"name": "q-job", "query": "SELECT 3", "profile": "Q"}
JOB_LEGACY = {"name": "legacy-job", "query": "SELECT 4"}
GROUP_P = {"name": "p-group", "profile": "P", "scripts": []}
GROUP_Q = {"name": "q-group", "profile": "Q", "scripts": []}

def _copy(item):
    return dict(item) if isinstance(item, dict) else item


ORDER_FIELDS = ("save_profiles", "save_jobs", "save_script_groups")


def make_stub(profile: str = "P", jobs=None, groups=None, results=None):
    """Stub with the R15 definition: P has 2 jobs + 1 group, Q has 1 job +
    1 group, plus one legacy job without a ``profile`` key."""
    stub = app.DatabaseConnectorGUI.__new__(app.DatabaseConnectorGUI)
    stub._active_db_lock = threading.Lock()
    stub._active_db_connections = {}
    stub._running_job_ids = set()
    stub._block_if_busy = mock.Mock(return_value=False)
    stub.profile_combo = _Combo(profile)
    stub.saved_profiles = {
        "P": {"db_type": "Oracle", "db_host": "p-host"},
        "Q": {"db_type": "Oracle", "db_host": "q-host"},
        "EMPTY": {"db_type": "Oracle", "db_host": "e-host"},
    }
    stub.saved_jobs = [_copy(j) for j in (jobs if jobs is not None
                                         else [JOB_P1, JOB_Q, JOB_P2, JOB_LEGACY])]
    stub.script_groups = [_copy(g) for g in (groups if groups is not None
                                            else [GROUP_P, GROUP_Q])]
    stub.results_text = _Text()
    stub.update_profile_list = mock.Mock()
    stub._refresh_script_groups_window = mock.Mock()
    stub.load_script_groups = mock.Mock(
        side_effect=AssertionError("must not read script_groups.json"))
    stub._script_groups_path = mock.Mock(
        side_effect=AssertionError("must not touch APP_DIR script_groups.json"))
    stub.jobs_file = os.path.join(tempfile.gettempdir(), "__never_used__.json")

    calls: list = []
    results = results or {}

    def _make(name):
        def _save():
            calls.append(name)
            return results.get(name, True)
        return mock.Mock(side_effect=_save)

    for name in ORDER_FIELDS:
        setattr(stub, name, _make(name))
    stub._save_calls = calls
    return stub


def names(items):
    return [item["name"] for item in items]


class DeleteProfileYesTests(unittest.TestCase):
    """R15-AC-26."""

    def test_yes_asks_with_counts_and_deletes_only_p_items_in_order(self):
        stub = make_stub()
        jobs_obj, groups_obj = stub.saved_jobs, stub.script_groups
        with mock.patch.object(app, "messagebox") as mb:
            mb.askyesnocancel.return_value = True
            stub.delete_profile()

        mb.askyesno.assert_not_called()
        mb.askyesnocancel.assert_called_once()
        message = mb.askyesnocancel.call_args[0][1]
        self.assertIn("'P'", message)
        self.assertIn("2 Job", message)
        self.assertIn("1 Script Group", message)

        self.assertNotIn("P", stub.saved_profiles)
        self.assertIn("Q", stub.saved_profiles)
        self.assertEqual(names(stub.saved_jobs), ["q-job", "legacy-job"])
        self.assertEqual(names(stub.script_groups), ["q-group"])
        # in-place: same list objects
        self.assertIs(stub.saved_jobs, jobs_obj)
        self.assertIs(stub.script_groups, groups_obj)
        self.assertEqual(stub._save_calls, list(ORDER_FIELDS))
        stub._refresh_script_groups_window.assert_called_once_with(None)
        stub.update_profile_list.assert_called_once()
        mb.showinfo.assert_called_once()
        mb.showwarning.assert_not_called()
        self.assertIn("Deleted profile: P", stub.results_text.joined)

    def test_yes_removes_deleted_jobs_from_checked_ids(self):
        stub = make_stub()
        p1, q = stub.saved_jobs[0], stub.saved_jobs[1]
        stub._checked_job_ids = {id(p1), id(q)}
        checked_obj = stub._checked_job_ids
        with mock.patch.object(app, "messagebox") as mb:
            mb.askyesnocancel.return_value = True
            stub.delete_profile()
        self.assertEqual(stub._checked_job_ids, {id(q)})
        self.assertIs(stub._checked_job_ids, checked_obj)

    def test_yes_writes_files_in_temp_dir(self):
        """Real save_jobs / save_script_groups, redirected to a temp dir."""
        with tempfile.TemporaryDirectory() as folder:
            stub = make_stub()
            stub.jobs_file = os.path.join(folder, "saved_jobs.json")
            groups_path = os.path.join(folder, "script_groups.json")
            stub._script_groups_path = mock.Mock(return_value=groups_path)
            del stub.save_jobs
            del stub.save_script_groups
            with mock.patch.object(app, "messagebox") as mb:
                mb.askyesnocancel.return_value = True
                stub.delete_profile()
            with open(stub.jobs_file, encoding="utf-8") as f:
                self.assertEqual(names(json.load(f)), ["q-job", "legacy-job"])
            with open(groups_path, encoding="utf-8") as f:
                self.assertEqual(names(json.load(f)["groups"]), ["q-group"])
            mb.showerror.assert_not_called()

    def test_only_groups_skips_save_jobs(self):
        stub = make_stub(jobs=[JOB_Q, JOB_LEGACY])
        jobs_before = copy.deepcopy(stub.saved_jobs)
        with mock.patch.object(app, "messagebox") as mb:
            mb.askyesnocancel.return_value = True
            stub.delete_profile()
        message = mb.askyesnocancel.call_args[0][1]
        self.assertIn("0 Job", message)
        self.assertIn("1 Script Group", message)
        self.assertEqual(stub._save_calls, ["save_profiles", "save_script_groups"])
        self.assertEqual(stub.saved_jobs, jobs_before)
        self.assertEqual(names(stub.script_groups), ["q-group"])
        mb.showwarning.assert_not_called()

    def test_only_jobs_skips_save_script_groups(self):
        stub = make_stub(groups=[GROUP_Q])
        with mock.patch.object(app, "messagebox") as mb:
            mb.askyesnocancel.return_value = True
            stub.delete_profile()
        message = mb.askyesnocancel.call_args[0][1]
        self.assertIn("2 Job", message)
        self.assertIn("0 Script Group", message)
        self.assertEqual(stub._save_calls, ["save_profiles", "save_jobs"])
        self.assertEqual(names(stub.saved_jobs), ["q-job", "legacy-job"])
        self.assertEqual(names(stub.script_groups), ["q-group"])
        stub._refresh_script_groups_window.assert_not_called()


class DeleteProfileNoCancelTests(unittest.TestCase):
    """R15-AC-27."""

    def test_no_deletes_profile_only(self):
        stub = make_stub()
        jobs_before = copy.deepcopy(stub.saved_jobs)
        groups_before = copy.deepcopy(stub.script_groups)
        with mock.patch.object(app, "messagebox") as mb:
            mb.askyesnocancel.return_value = False
            stub.delete_profile()
        self.assertNotIn("P", stub.saved_profiles)
        self.assertEqual(stub.saved_jobs, jobs_before)
        self.assertEqual(stub.script_groups, groups_before)
        self.assertEqual(stub._save_calls, ["save_profiles"])
        stub.save_jobs.assert_not_called()
        stub.save_script_groups.assert_not_called()
        mb.showinfo.assert_called_once()
        mb.showwarning.assert_not_called()

    def test_cancel_changes_nothing_and_saves_nothing(self):
        stub = make_stub()
        profiles_before = copy.deepcopy(stub.saved_profiles)
        jobs_before = copy.deepcopy(stub.saved_jobs)
        groups_before = copy.deepcopy(stub.script_groups)
        with mock.patch.object(app, "messagebox") as mb:
            mb.askyesnocancel.return_value = None
            stub.delete_profile()
        self.assertEqual(stub.saved_profiles, profiles_before)
        self.assertEqual(stub.saved_jobs, jobs_before)
        self.assertEqual(stub.script_groups, groups_before)
        self.assertEqual(stub._save_calls, [])
        stub.update_profile_list.assert_not_called()
        self.assertEqual(stub.results_text.inserted, [])
        mb.showinfo.assert_not_called()
        mb.showwarning.assert_not_called()


class DeleteProfileWithoutItemsTests(unittest.TestCase):
    """R15-AC-28."""

    def test_empty_profile_uses_original_askyesno(self):
        stub = make_stub(profile="EMPTY")
        jobs_before = copy.deepcopy(stub.saved_jobs)
        groups_before = copy.deepcopy(stub.script_groups)
        with mock.patch.object(app, "messagebox") as mb:
            mb.askyesno.return_value = True
            stub.delete_profile()
        mb.askyesnocancel.assert_not_called()
        mb.askyesno.assert_called_once_with(
            "Confirm Delete", "ต้องการลบ Profile 'EMPTY' หรือไม่?")
        self.assertNotIn("EMPTY", stub.saved_profiles)
        self.assertEqual(stub.saved_jobs, jobs_before)
        self.assertEqual(stub.script_groups, groups_before)
        self.assertEqual(stub._save_calls, ["save_profiles"])
        mb.showinfo.assert_called_once_with("Success", "ลบ Profile 'EMPTY' เรียบร้อย")
        self.assertIn("Deleted profile: EMPTY", stub.results_text.joined)

    def test_empty_profile_answer_no_keeps_everything(self):
        stub = make_stub(profile="EMPTY")
        profiles_before = copy.deepcopy(stub.saved_profiles)
        with mock.patch.object(app, "messagebox") as mb:
            mb.askyesno.return_value = False
            stub.delete_profile()
        self.assertEqual(stub.saved_profiles, profiles_before)
        self.assertEqual(stub._save_calls, [])

    def test_legacy_job_without_profile_key_is_not_counted(self):
        stub = make_stub(profile="EMPTY",
                         jobs=[JOB_LEGACY, {"name": "x", "profile": None}])
        with mock.patch.object(app, "messagebox") as mb:
            mb.askyesno.return_value = True
            stub.delete_profile()
        mb.askyesnocancel.assert_not_called()
        self.assertEqual(len(stub.saved_jobs), 2)

    def test_non_dict_entries_are_ignored(self):
        stub = make_stub(jobs=["junk", JOB_P1, None], groups=[GROUP_Q, 5])
        with mock.patch.object(app, "messagebox") as mb:
            mb.askyesnocancel.return_value = True
            stub.delete_profile()
        self.assertIn("1 Job", mb.askyesnocancel.call_args[0][1])
        self.assertEqual(stub.saved_jobs, ["junk", None])
        self.assertEqual(stub.script_groups, [GROUP_Q, 5])
        self.assertEqual(stub._save_calls, ["save_profiles", "save_jobs"])


class DeleteProfileRollbackTests(unittest.TestCase):
    """R15-AC-29 (ก)(ข)(ค)."""

    def _run(self, results):
        stub = make_stub(results=results)
        state = {
            "profiles": copy.deepcopy(stub.saved_profiles),
            "jobs": copy.deepcopy(stub.saved_jobs),
            "groups": copy.deepcopy(stub.script_groups),
            "jobs_obj": stub.saved_jobs,
            "groups_obj": stub.script_groups,
            "profiles_obj": stub.saved_profiles,
        }
        with mock.patch.object(app, "messagebox") as mb:
            mb.askyesnocancel.return_value = True
            stub.delete_profile()
        return stub, mb, state

    def _assert_same_objects(self, stub, state):
        self.assertIs(stub.saved_jobs, state["jobs_obj"])
        self.assertIs(stub.script_groups, state["groups_obj"])
        self.assertIs(stub.saved_profiles, state["profiles_obj"])

    def test_a_profiles_save_fails_rolls_back_everything(self):
        stub, mb, state = self._run({"save_profiles": False})
        self.assertEqual(stub.saved_profiles, state["profiles"])
        self.assertEqual(stub.saved_jobs, state["jobs"])
        self.assertEqual(stub.script_groups, state["groups"])
        self._assert_same_objects(stub, state)
        self.assertEqual(stub._save_calls, ["save_profiles"])
        stub.update_profile_list.assert_not_called()
        mb.showinfo.assert_not_called()

    def test_b_jobs_save_fails_keeps_jobs_and_groups(self):
        stub, mb, state = self._run({"save_jobs": False})
        self.assertNotIn("P", stub.saved_profiles)
        self.assertEqual(stub.saved_jobs, state["jobs"])
        self.assertEqual(stub.script_groups, state["groups"])
        # same dict objects back in the same order
        self.assertEqual([id(j) for j in stub.saved_jobs],
                         [id(j) for j in state["jobs_obj"]])
        self._assert_same_objects(stub, state)
        self.assertEqual(stub._save_calls, ["save_profiles", "save_jobs"])
        stub._refresh_script_groups_window.assert_not_called()
        mb.showinfo.assert_not_called()
        mb.showwarning.assert_called_once()
        warning = mb.showwarning.call_args[0][1]
        self.assertIn("Job", warning)
        self.assertIn("ไม่สำเร็จ", warning)
        self.assertIn(warning, stub.results_text.joined)
        self.assertIn("Deleted profile: P", stub.results_text.joined)

    def test_b_jobs_save_fails_keeps_checked_ids(self):
        stub = make_stub(results={"save_jobs": False})
        stub._checked_job_ids = {id(stub.saved_jobs[0])}
        before = set(stub._checked_job_ids)
        with mock.patch.object(app, "messagebox") as mb:
            mb.askyesnocancel.return_value = True
            stub.delete_profile()
        self.assertEqual(stub._checked_job_ids, before)

    def test_c_groups_save_fails_keeps_groups_only(self):
        stub, mb, state = self._run({"save_script_groups": False})
        self.assertNotIn("P", stub.saved_profiles)
        self.assertEqual(names(stub.saved_jobs), ["q-job", "legacy-job"])
        self.assertEqual(stub.script_groups, state["groups"])
        self._assert_same_objects(stub, state)
        self.assertEqual(stub._save_calls, list(ORDER_FIELDS))
        stub._refresh_script_groups_window.assert_not_called()
        mb.showinfo.assert_not_called()
        mb.showwarning.assert_called_once()
        warning = mb.showwarning.call_args[0][1]
        self.assertIn("Script Group", warning)
        self.assertIn("ไม่สำเร็จ", warning)
        self.assertIn(warning, stub.results_text.joined)


class DeleteProfileGuardTests(unittest.TestCase):
    def test_busy_blocks_before_any_dialog(self):
        stub = make_stub()
        stub._block_if_busy = mock.Mock(return_value=True)
        with mock.patch.object(app, "messagebox") as mb:
            stub.delete_profile()
        mb.askyesno.assert_not_called()
        mb.askyesnocancel.assert_not_called()
        self.assertEqual(stub._save_calls, [])

    def test_unknown_or_empty_profile_warns(self):
        for value in ("", "MISSING"):
            stub = make_stub(profile=value)
            with mock.patch.object(app, "messagebox") as mb:
                stub.delete_profile()
            mb.showwarning.assert_called_once()
            mb.askyesnocancel.assert_not_called()
            self.assertEqual(stub._save_calls, [])


if __name__ == "__main__":
    unittest.main()
