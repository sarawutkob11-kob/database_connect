"""R16-T2: Import Script Groups rejects a Saved Jobs file (R16-AC-10 .. R16-AC-13).

Rule (R16-Q-1 (a)): any item (dict) with key 'query' and without key 'scripts'
makes the whole file invalid. No Tk, no real app files: APP_DIR is a tempdir,
messagebox / filedialog are patched.
"""

import copy
import inspect
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import database_connect_gui as app  # noqa: E402

INVALID_MSG = "Not a valid Script Groups file:\n"
JOB_MSG_TAIL = " looks like a Saved Job, not a group (it has 'query' but no 'scripts' list)"

SAVED_JOBS = [
    {"name": "Daily", "query": "SELECT 1", "profile": "QA"},
    {"name": "Weekly", "query": "SELECT 2", "profile": "QA"},
]
OLD_JOBS_NO_PROFILE = [
    {"name": "Daily", "query": "SELECT 1"},
    {"name": "Weekly", "query": "SELECT 2"},
]
MIXED = {"groups": [
    {"name": "G1", "scripts": [{"query": "SELECT 1"}]},
    {"name": "Daily", "query": "SELECT 2"},
]}


def parse(data):
    return app.parse_script_groups_import(data)


# ----------------------------------------------------------------------
# R16-AC-10 / R16-AC-12: parse rejects Saved Jobs data
# ----------------------------------------------------------------------
class TestParseRejectsSavedJobs(unittest.TestCase):
    def assert_job_error(self, data, label="'Daily'"):
        with self.assertRaises(ValueError) as cm:
            parse(data)
        msg = str(cm.exception)
        self.assertIn("scripts", msg)
        self.assertEqual(msg, label + JOB_MSG_TAIL)
        return msg

    def test_bare_list_saved_jobs(self):
        self.assert_job_error(copy.deepcopy(SAVED_JOBS))

    def test_wrapped_in_groups(self):
        self.assert_job_error({"groups": copy.deepcopy(SAVED_JOBS)})

    def test_wrapped_with_type_header(self):
        self.assert_job_error({"type": "script_groups", "version": 1,
                               "groups": copy.deepcopy(SAVED_JOBS)})

    def test_old_job_without_profile(self):
        self.assert_job_error(copy.deepcopy(OLD_JOBS_NO_PROFILE))
        self.assert_job_error({"groups": copy.deepcopy(OLD_JOBS_NO_PROFILE)})

    def test_single_job(self):
        self.assert_job_error([{"name": "Daily", "query": "SELECT 1"}])

    def test_first_job_item_is_named(self):
        # 'Daily' comes first, so it is the one reported
        msg = self.assert_job_error(copy.deepcopy(SAVED_JOBS))
        self.assertNotIn("Weekly", msg)

    def test_query_value_does_not_matter(self):
        for q in ("", None, 5, [], {"x": 1}, "   "):
            with self.subTest(query=q):
                self.assert_job_error([{"name": "Daily", "query": q}])

    def test_job_with_extra_job_keys(self):
        self.assert_job_error([{"name": "Daily", "query": "SELECT 1", "profile": "QA",
                                "created": "2025-01-01 00:00:00", "target": "T"}])

    # R16-AC-12
    def test_mixed_file_raises(self):
        self.assert_job_error(copy.deepcopy(MIXED))

    def test_mixed_bare_list_job_last(self):
        data = [{"name": "G1", "scripts": [{"query": "SELECT 1"}]},
                {"name": "G2", "scripts": []},
                {"name": "Daily", "query": "SELECT 2"}]
        self.assert_job_error(data)

    def test_mixed_job_after_dropped_items(self):
        data = ["x", None, {"name": "", "scripts": []},
                {"name": "G1", "scripts": [{"query": "SELECT 1"}]},
                {"name": "Daily", "query": "SELECT 2"}]
        self.assert_job_error(data)

    def test_job_check_before_script_sql_check(self):
        # raw list checked before the SQL check: the Job error wins
        data = [{"name": "Bad", "scripts": [{"name": "no sql"}]},
                {"name": "Daily", "query": "SELECT 2"}]
        self.assert_job_error(data)

    def test_input_not_mutated(self):
        data = copy.deepcopy(MIXED)
        before = copy.deepcopy(data)
        with self.assertRaises(ValueError):
            parse(data)
        self.assertEqual(data, before)


class TestJobLabel(unittest.TestCase):
    """label = 'item N' (1-based in the raw list) when name is not non-empty text."""

    def msg_of(self, data):
        with self.assertRaises(ValueError) as cm:
            parse(data)
        return str(cm.exception)

    def test_no_name(self):
        self.assertEqual(self.msg_of([{"query": "SELECT 1"}]), "item 1" + JOB_MSG_TAIL)

    def test_empty_name(self):
        self.assertEqual(self.msg_of([{"name": "", "query": "SELECT 1"}]), "item 1" + JOB_MSG_TAIL)

    def test_blank_name(self):
        self.assertEqual(self.msg_of([{"name": "   ", "query": "x"}]), "item 1" + JOB_MSG_TAIL)

    def test_non_str_names(self):
        for name in (5, None, 0, 1.5, ["a"], {"a": 1}, True):
            with self.subTest(name=name):
                self.assertEqual(self.msg_of([{"name": name, "query": "x"}]),
                                 "item 1" + JOB_MSG_TAIL)

    def test_position_counts_raw_list(self):
        # dropped / non-dict items before the job still count
        data = ["x", 42, None, {"name": "", "scripts": []},
                {"name": "G", "scripts": [{"query": "SELECT 1"}]},
                {"name": "", "query": "SELECT 2"}]
        self.assertEqual(self.msg_of(data), "item 6" + JOB_MSG_TAIL)

    def test_position_in_wrapped_groups(self):
        data = {"groups": [{"name": "G1", "scripts": []}, {"query": "SELECT 2"}]}
        self.assertEqual(self.msg_of(data), "item 2" + JOB_MSG_TAIL)

    def test_name_kept_as_is_with_spaces(self):
        self.assertEqual(self.msg_of([{"name": " Daily ", "query": "x"}]),
                         "' Daily '" + JOB_MSG_TAIL)

    def test_thai_name(self):
        self.assertEqual(self.msg_of([{"name": "งานรายวัน", "query": "x"}]),
                         "'งานรายวัน'" + JOB_MSG_TAIL)


# ----------------------------------------------------------------------
# R16-AC-13: valid files unchanged
# ----------------------------------------------------------------------
class TestParseValidUnchanged(unittest.TestCase):
    def test_name_only_item_still_kept(self):
        data = [{"name": "A"}]
        out = parse(data)
        self.assertEqual(out, [{"name": "A"}])
        self.assertIs(out[0], data[0])

    def test_name_only_items_bare_and_wrapped(self):
        data = [{"name": "A"}, {"name": "B", "created": "c"}]
        self.assertEqual([g["name"] for g in parse(data)], ["A", "B"])
        self.assertEqual([g["name"] for g in parse({"groups": data})], ["A", "B"])

    def test_query_and_scripts_list_is_group(self):
        data = [{"name": "Both", "query": "SELECT 0", "scripts": [{"query": "SELECT 1"}]},
                {"name": "BothEmpty", "query": "SELECT 0", "scripts": []}]
        out = parse(data)
        self.assertEqual([g["name"] for g in out], ["Both", "BothEmpty"])
        self.assertIs(out[0], data[0])
        self.assertIs(out[1], data[1])

    def test_query_and_scripts_not_list_dropped_not_raised(self):
        # has 'scripts' key -> not a Job item; old filter drops it
        data = [{"name": "X", "query": "q", "scripts": "bad"},
                {"name": "Y", "query": "q", "scripts": None},
                {"name": "Keep", "scripts": []}]
        self.assertEqual([g["name"] for g in parse(data)], ["Keep"])

    def test_query_inside_scripts_only_is_fine(self):
        data = {"groups": [{"name": "G", "scripts": [{"name": "s", "query": "SELECT 1"}]}]}
        self.assertEqual([g["name"] for g in parse(data)], ["G"])

    def test_non_dict_items_with_query_text(self):
        # strings / lists are not dict items -> not Jobs, just dropped
        data = ["query", ["query"], {"name": "G", "scripts": []}]
        self.assertEqual([g["name"] for g in parse(data)], ["G"])

    def test_export_payload_round_trip(self):
        groups = [
            {"name": "G1", "profile": "P1", "created": "2025-01-01 00:00:00",
             "scripts": [{"name": "a", "query": "SELECT 1", "_tmp": 1, "run_index": 2},
                         {"name": "b", "query": "SELECT 2"}]},
            {"name": "Empty", "profile": "P1", "created": None, "scripts": []},
        ]
        payload = app.build_script_groups_export(groups, "P1", now="2026-01-01 00:00:00")
        payload = json.loads(json.dumps(payload))  # as written / read from disk
        out = parse(payload)
        self.assertEqual([g["name"] for g in out], ["G1", "Empty"])
        self.assertEqual(out[0]["scripts"], [{"name": "a", "query": "SELECT 1"},
                                             {"name": "b", "query": "SELECT 2"}])
        self.assertEqual(out[1]["scripts"], [])
        self.assertIs(out[0], payload["groups"][0])

    def test_internal_script_groups_json(self):
        data = {"version": 1, "groups": [
            {"name": "G1", "profile": "P1", "created": "c", "scripts": [{"query": "SELECT 1"}]},
            {"name": "G2", "profile": "P2", "created": "c", "scripts": []},
        ]}
        out = parse(data)
        self.assertEqual([g["name"] for g in out], ["G1", "G2"])
        self.assertIs(out[1], data["groups"][1])

    def test_old_filter_rules_kept(self):
        data = ["x", 42, None, {"scripts": []}, {"name": "", "scripts": []},
                {"name": 5, "scripts": []}, {"name": "S", "scripts": "bad"},
                {"name": "Keep", "scripts": [{"query": "SELECT 1"}]}, {"name": "NoKey"}]
        self.assertEqual([g["name"] for g in parse(data)], ["Keep", "NoKey"])

    def test_script_without_sql_error_unchanged(self):
        with self.assertRaises(ValueError) as cm:
            parse([{"name": "MyGroup", "scripts": [{"name": "s"}]}])
        self.assertEqual(str(cm.exception), "group 'MyGroup' has a script without SQL")

    def test_no_groups_list_error_unchanged(self):
        for data in ({}, {"groups": None}, "text", None):
            with self.subTest(data=data):
                with self.assertRaises(ValueError) as cm:
                    parse(data)
                self.assertEqual(str(cm.exception), "no 'groups' list in this file")

    def test_empty_list(self):
        self.assertEqual(parse([]), [])
        self.assertEqual(parse({"groups": []}), [])


# ----------------------------------------------------------------------
# R16-AC-11 / R16-AC-12 / R16-AC-13 through import_script_groups
# ----------------------------------------------------------------------
class ImportBase(unittest.TestCase):
    """Real load / save of script_groups.json inside a temp APP_DIR."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.app_dir = os.path.join(self.tmp.name, "app")
        os.makedirs(self.app_dir)
        p_dir = mock.patch.object(app, "APP_DIR", self.app_dir)
        p_dir.start()
        self.addCleanup(p_dir.stop)
        self.groups_path = os.path.join(self.app_dir, "script_groups.json")
        existing = {"version": 1, "groups": [
            {"name": "Existing", "profile": "P1", "created": "2025-01-01 00:00:00",
             "scripts": [{"name": "s", "query": "SELECT OLD"}]},
            {"name": "Other", "profile": "P2", "created": "2025-01-01 00:00:00",
             "scripts": [{"query": "SELECT P2"}]},
        ]}
        with open(self.groups_path, "w", encoding="utf-8") as fh:
            json.dump(existing, fh, indent=2)
        with open(self.groups_path, "rb") as fh:
            self.file_bytes = fh.read()

        self.src = os.path.join(self.tmp.name, "picked.json")
        self.stub = app.DatabaseConnectorGUI.__new__(app.DatabaseConnectorGUI)
        self.stub.root = object()
        self.stub.results_text = mock.Mock()
        self.stub.profile_combo = mock.Mock()
        self.stub.profile_combo.get.return_value = "P1"
        real_save = self.stub.save_script_groups
        self.stub.save_script_groups = mock.Mock(wraps=real_save)
        self.stub._ensure_script_groups_loaded()  # real load from temp APP_DIR
        self.sg_ref = self.stub.script_groups
        self.sg_before = copy.deepcopy(self.stub.script_groups)
        self.assertEqual([g["name"] for g in self.sg_ref], ["Existing", "Other"])

        p_mb = mock.patch.object(app, "messagebox")
        p_fd = mock.patch.object(app, "filedialog")
        self.mb = p_mb.start()
        self.fd = p_fd.start()
        self.addCleanup(p_mb.stop)
        self.addCleanup(p_fd.stop)
        self.fd.askopenfilename.return_value = self.src
        self.mb.askyesno.return_value = True
        self.mb.askyesnocancel.return_value = True
        self.window = object()  # stands for the Script Groups dialog (parent)

    def write_src(self, data):
        with open(self.src, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False)

    def run_import(self, via):
        if via == "sidebar":
            return self.stub.sidebar_import_script_groups(), self.stub.root
        return self.stub.import_script_groups(self.window), self.window

    def imported_lines(self):
        return [c for c in self.stub.results_text.insert.call_args_list
                if any("Imported" in str(a) for a in c.args)]


class TestImportRejectsSavedJobs(ImportBase):
    def assert_rejected(self, data, via, label="'Daily'"):
        self.write_src(data)
        result, parent = self.run_import(via)
        self.assertIsNone(result)
        self.mb.showerror.assert_called_once()
        args, kwargs = self.mb.showerror.call_args
        self.assertEqual(args[0], "Import Groups")
        self.assertTrue(args[1].startswith(INVALID_MSG), args[1])
        self.assertEqual(args[1], INVALID_MSG + label + JOB_MSG_TAIL)
        self.assertIn("scripts", args[1])
        self.assertIs(kwargs.get("parent"), parent)
        self.fd.askopenfilename.assert_called_once()
        self.assertIs(self.fd.askopenfilename.call_args.kwargs.get("parent"), parent)
        self.mb.askyesno.assert_not_called()
        self.mb.askyesnocancel.assert_not_called()
        self.mb.showinfo.assert_not_called()
        self.mb.showwarning.assert_not_called()
        self.stub.save_script_groups.assert_not_called()
        self.assertIs(self.stub.script_groups, self.sg_ref)
        self.assertEqual(self.stub.script_groups, self.sg_before)
        self.assertEqual(self.imported_lines(), [])
        self.stub.results_text.insert.assert_not_called()
        with open(self.groups_path, "rb") as fh:
            self.assertEqual(fh.read(), self.file_bytes)
        self.assertFalse(os.path.exists(os.path.join(self.app_dir, "script_groups_backup.json")))
        self.assertEqual(sorted(os.listdir(self.app_dir)), ["script_groups.json"])

    # R16-AC-11
    def test_bare_list_window(self):
        self.assert_rejected(copy.deepcopy(SAVED_JOBS), "window")

    def test_bare_list_sidebar(self):
        self.assert_rejected(copy.deepcopy(SAVED_JOBS), "sidebar")

    def test_wrapped_window(self):
        self.assert_rejected({"groups": copy.deepcopy(SAVED_JOBS)}, "window")

    def test_wrapped_sidebar(self):
        self.assert_rejected({"groups": copy.deepcopy(SAVED_JOBS)}, "sidebar")

    def test_old_jobs_no_profile_window(self):
        self.assert_rejected(copy.deepcopy(OLD_JOBS_NO_PROFILE), "window")

    def test_old_jobs_no_profile_sidebar(self):
        self.assert_rejected(copy.deepcopy(OLD_JOBS_NO_PROFILE), "sidebar")

    # R16-AC-12
    def test_mixed_window_g1_not_imported(self):
        self.assert_rejected(copy.deepcopy(MIXED), "window")
        self.assertNotIn("G1", [g["name"] for g in self.stub.script_groups])

    def test_mixed_sidebar_g1_not_imported(self):
        self.assert_rejected(copy.deepcopy(MIXED), "sidebar")
        self.assertNotIn("G1", [g["name"] for g in self.stub.script_groups])

    def test_unnamed_job_label(self):
        self.assert_rejected([{"name": "G", "scripts": []}, {"query": "SELECT 1"}],
                             "sidebar", label="item 2")

    def test_real_saved_jobs_file_shape(self):
        # what save_jobs writes: a bare list of job dicts
        jobs = [{"name": "Daily", "query": "SELECT 1", "profile": "QA",
                 "created": "2025-01-01 00:00:00"}]
        self.assert_rejected(jobs, "window")


class TestImportValidStillWorks(ImportBase):
    """R16-AC-13 through the real import flow (real save into temp APP_DIR)."""

    def read_saved(self):
        with open(self.groups_path, encoding="utf-8") as fh:
            return json.load(fh)

    def assert_imported(self, result, names, via_parent):
        self.mb.showerror.assert_not_called()
        self.mb.askyesno.assert_called_once()
        self.assertIs(self.mb.askyesno.call_args.kwargs.get("parent"), via_parent)
        self.stub.save_script_groups.assert_called_once_with()
        self.assertIs(self.stub.script_groups, self.sg_ref)
        p1 = [g["name"] for g in self.stub.script_groups if g.get("profile") == "P1"]
        self.assertEqual(p1, ["Existing"] + names)
        self.assertEqual(result, names[-1])
        saved = self.read_saved()
        self.assertEqual([g["name"] for g in saved["groups"] if g.get("profile") == "P1"],
                         ["Existing"] + names)
        self.assertEqual(len(self.imported_lines()), 1)

    def test_export_then_import_round_trip_window(self):
        src_groups = [
            {"name": "R1", "profile": "PX", "created": "2025-02-02 00:00:00",
             "scripts": [{"name": "a", "query": "SELECT 1", "_tmp": 1, "run_index": 0}]},
            {"name": "REmpty", "profile": "PX", "created": None, "scripts": []},
        ]
        self.write_src(app.build_script_groups_export(src_groups, "PX"))
        result = self.stub.import_script_groups(self.window)
        self.assert_imported(result, ["R1", "REmpty"], self.window)
        r1 = next(g for g in self.read_saved()["groups"] if g["name"] == "R1")
        self.assertEqual(r1["scripts"], [{"name": "a", "query": "SELECT 1"}])

    def test_export_then_import_round_trip_sidebar(self):
        src_groups = [{"name": "R1", "profile": "PX", "created": None,
                       "scripts": [{"query": "SELECT 1"}]}]
        self.write_src(app.build_script_groups_export(src_groups, "PX"))
        result = self.stub.sidebar_import_script_groups()
        self.assert_imported(result, ["R1"], self.stub.root)

    def test_name_only_items(self):
        self.write_src([{"name": "A"}, {"name": "B"}])
        result = self.stub.sidebar_import_script_groups()
        self.assert_imported(result, ["A", "B"], self.stub.root)

    def test_query_plus_scripts_item(self):
        self.write_src({"groups": [{"name": "Both", "query": "SELECT 0",
                                    "scripts": [{"query": "SELECT 1"}]}]})
        result = self.stub.import_script_groups(self.window)
        self.assert_imported(result, ["Both"], self.window)

    def test_internal_file_shape(self):
        self.write_src({"version": 1, "groups": [
            {"name": "N1", "profile": "P9", "created": "c", "scripts": [{"query": "SELECT 1"}]}]})
        result = self.stub.import_script_groups(self.window)
        self.assert_imported(result, ["N1"], self.window)

    def test_script_without_sql_still_invalid(self):
        self.write_src({"groups": [{"name": "Bad", "scripts": [{"name": "x"}]}]})
        self.assertIsNone(self.stub.import_script_groups(self.window))
        self.mb.showerror.assert_called_once_with(
            "Import Groups", INVALID_MSG + "group 'Bad' has a script without SQL",
            parent=self.window)
        self.stub.save_script_groups.assert_not_called()
        with open(self.groups_path, "rb") as fh:
            self.assertEqual(fh.read(), self.file_bytes)


class TestSourceShape(unittest.TestCase):
    """The dialog and sidebar still go through import_script_groups (design R16-D3)."""

    def test_dialog_and_sidebar_delegate(self):
        dialog_src = inspect.getsource(app.DatabaseConnectorGUI.show_script_groups_dialog)
        self.assertIn("self.import_script_groups(dialog)", dialog_src)
        side_src = inspect.getsource(app.DatabaseConnectorGUI.sidebar_import_script_groups)
        self.assertIn("self.import_script_groups(self.root)", side_src)

    def test_docstring_mentions_saved_job(self):
        self.assertIn("Saved Job", app.parse_script_groups_import.__doc__)


if __name__ == "__main__":
    unittest.main()
