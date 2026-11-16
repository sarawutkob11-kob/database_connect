"""Round 6: Import Groups must not report success when script_groups.json
was not saved (R6-AC-1 .. R6-AC-11).

No Tk windows: the app is a ``__new__`` stub, dialogs are mocked, and every
file lives in a TemporaryDirectory (APP_DIR is patched to it). The real
``save_script_groups`` is used for both failure kinds (blocked flag and a
write/backup error).
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

BLOCKED_MSG = (
    "script_groups.json could not be read when the app started, "
    "so it is not overwritten. Restart the app to load your groups again."
)
IMPORTED_MARK = "📥 Imported"

FAIL_MODES = ("blocked", "write", "backup")
SCENARIOS = ("noclash", "yes", "no")


def make_stub():
    stub = app.DatabaseConnectorGUI.__new__(app.DatabaseConnectorGUI)
    stub.root = object()
    stub.results_text = mock.Mock()
    stub.profile_combo = mock.Mock()
    stub.profile_combo.get.return_value = "P1"
    return stub


def initial_groups():
    """P1 groups with nested script values plus groups of another profile."""
    return [
        {
            "name": "G1",
            "profile": "P1",
            "created": "2025-01-01 00:00:00",
            "scripts": [
                {
                    "name": "a",
                    "query": "SELECT 1",
                    "params": {"x": [1, 2, {"deep": "v"}], "y": None},
                    "tags": ["t1", ["n1", "n2"]],
                    "_tmp": {"k": 1},
                    "run_index": 4,
                },
                {"name": "b", "query": "SELECT 2"},
            ],
        },
        {
            "name": "Shared",
            "profile": "P2",
            "created": "2025-02-02 00:00:00",
            "scripts": [{"name": "p2", "query": "SELECT 'P2'", "meta": {"m": [9]}}],
        },
        {
            "name": "G2",
            "profile": "P1",
            "created": "2025-03-03 00:00:00",
            "scripts": [{"name": "c", "query": "SELECT 3", "opts": [{"o": 1}]}],
        },
        {
            "name": "G1",
            "profile": "P2",
            "created": "2025-04-04 00:00:00",
            "scripts": [{"name": "d", "query": "SELECT 4"}],
        },
    ]


def import_payload(scenario):
    if scenario == "noclash":
        return {"type": "script_groups", "groups": [
            {"name": "New1", "scripts": [{"query": "NEW1", "params": {"a": [1]}}]},
            {"name": "New2", "scripts": [{"query": "NEW2"}]},
        ]}
    # clash on G1 (case-insensitive) and G2 of profile P1
    return {"type": "script_groups", "groups": [
        {"name": "g1", "scripts": [{"query": "IMPORTED1"}]},
        {"name": "G2", "scripts": [{"query": "IMPORTED2"}]},
        {"name": "Fresh", "scripts": [{"query": "IMPORTED3"}]},
    ]}


class R6Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.app_dir = os.path.join(self.tmp.name, "appdir")
        os.makedirs(self.app_dir)
        p_dir = mock.patch.object(app, "APP_DIR", self.app_dir)
        p_dir.start()
        self.addCleanup(p_dir.stop)
        self.sg_path = os.path.join(self.app_dir, "script_groups.json")
        self.backup_path = os.path.join(self.app_dir, "script_groups_backup.json")
        self.src = os.path.join(self.tmp.name, "in.json")

        self.stub = make_stub()
        self.stub.script_groups = initial_groups()
        self.sg_ref = self.stub.script_groups
        self.sg_before = copy.deepcopy(self.stub.script_groups)

        # existing file on disk (different from memory on purpose)
        with open(self.sg_path, "w", encoding="utf-8") as fh:
            json.dump({"version": 1, "groups": [{"name": "OnDisk", "profile": "P1",
                                                 "scripts": []}]}, fh)
        self.disk_before = self.read_bytes(self.sg_path)

        p_mb = mock.patch.object(app, "messagebox")
        p_fd = mock.patch.object(app, "filedialog")
        self.mb = p_mb.start()
        self.fd = p_fd.start()
        self.addCleanup(p_mb.stop)
        self.addCleanup(p_fd.stop)
        self.fd.askopenfilename.return_value = self.src
        self.mb.askyesno.return_value = True
        self.mb.askyesnocancel.return_value = True
        self.parent = object()

    @staticmethod
    def read_bytes(path):
        with open(path, "rb") as fh:
            return fh.read()

    def read_json(self, path):
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)

    def write_src(self, data):
        with open(self.src, "w", encoding="utf-8") as fh:
            json.dump(data, fh)

    def logged_text(self):
        return "".join(str(a) for c in self.stub.results_text.insert.call_args_list
                       for a in c.args)

    def assert_disk_unchanged(self):
        self.assertEqual(self.read_bytes(self.sg_path), self.disk_before)
        self.assertFalse(os.path.exists(self.sg_path + ".tmp"))

    def failure_patches(self, mode):
        """Return a list of started patches that make the real save fail."""
        if mode == "blocked":
            self.stub._script_groups_save_blocked = True
            return []
        if mode == "write":
            self.stub._script_groups_backup_done = True
            p = mock.patch.object(app, "write_json_atomic",
                                  side_effect=OSError("disk locked"))
        elif mode == "backup":
            p = mock.patch("shutil.copy2", side_effect=OSError("backup locked"))
        else:  # pragma: no cover
            raise ValueError(mode)
        p.start()
        self.addCleanup(p.stop)
        return [p]

    def set_answer(self, scenario):
        if scenario == "yes":
            self.mb.askyesnocancel.return_value = True
        elif scenario == "no":
            self.mb.askyesnocancel.return_value = False


# ----------------------------------------------------------------------
# R6-T1: save_script_groups returns bool (R6-AC-1 .. R6-AC-3)
# ----------------------------------------------------------------------
class TestSaveReturnsBool(R6Base):
    def test_annotation_is_bool(self):
        self.assertIs(app.DatabaseConnectorGUI.save_script_groups.__annotations__.get("return"),
                      bool)

    # R6-AC-1
    def test_blocked_returns_false(self):
        self.stub._script_groups_save_blocked = True
        with mock.patch.object(app, "write_json_atomic") as w, \
                mock.patch("shutil.copy2") as cp:
            result = self.stub.save_script_groups()
        self.assertIs(result, False)
        self.assertIsInstance(result, bool)
        self.mb.showerror.assert_called_once_with("Script Groups", BLOCKED_MSG)
        w.assert_not_called()
        cp.assert_not_called()
        self.assert_disk_unchanged()
        self.assertFalse(os.path.exists(self.backup_path))
        self.assertEqual(self.stub.script_groups, self.sg_before)

    def test_blocked_returns_false_when_no_file(self):
        os.remove(self.sg_path)
        self.stub._script_groups_save_blocked = True
        self.assertIs(self.stub.save_script_groups(), False)
        self.assertFalse(os.path.exists(self.sg_path))
        self.mb.showerror.assert_called_once()

    # R6-AC-2
    def test_write_oserror_returns_false(self):
        self.stub._script_groups_backup_done = True
        with mock.patch.object(app, "write_json_atomic",
                               side_effect=OSError("disk locked")) as w:
            result = self.stub.save_script_groups()
        self.assertIs(result, False)
        w.assert_called_once()
        self.mb.showerror.assert_called_once_with(
            "Script Groups", "Cannot save script_groups.json:\ndisk locked")
        self.assert_disk_unchanged()

    def test_real_write_failure_returns_false(self):
        # the real write_json_atomic runs; only the final swap (os.replace) fails
        self.stub._script_groups_backup_done = True
        with mock.patch.object(app.os, "replace", side_effect=PermissionError("in use")):
            result = self.stub.save_script_groups()
        self.assertIs(result, False)
        self.mb.showerror.assert_called_once()
        self.assertTrue(self.mb.showerror.call_args.args[1].startswith(
            "Cannot save script_groups.json:\n"))
        self.assertEqual(self.read_bytes(self.sg_path), self.disk_before)

    def test_backup_copy_failure_returns_false(self):
        with mock.patch("shutil.copy2", side_effect=OSError("backup locked")), \
                mock.patch.object(app, "write_json_atomic") as w:
            result = self.stub.save_script_groups()
        self.assertIs(result, False)
        w.assert_not_called()
        self.mb.showerror.assert_called_once_with(
            "Script Groups", "Cannot save script_groups.json:\nbackup locked")
        self.assert_disk_unchanged()
        self.assertFalse(getattr(self.stub, "_script_groups_backup_done", False))

    def test_backup_method_raises_returns_false(self):
        self.stub._backup_script_groups_once = mock.Mock(side_effect=OSError("bk"))
        result = self.stub.save_script_groups()
        self.assertIs(result, False)
        self.mb.showerror.assert_called_once_with(
            "Script Groups", "Cannot save script_groups.json:\nbk")
        self.assert_disk_unchanged()

    def test_non_oserror_also_false(self):
        self.stub._script_groups_backup_done = True
        with mock.patch.object(app, "write_json_atomic", side_effect=TypeError("bad")):
            self.assertIs(self.stub.save_script_groups(), False)
        self.mb.showerror.assert_called_once()

    # R6-AC-3
    def test_success_returns_true_and_content(self):
        result = self.stub.save_script_groups()
        self.assertIs(result, True)
        self.assertIsInstance(result, bool)
        self.mb.showerror.assert_not_called()
        data = self.read_json(self.sg_path)
        self.assertEqual(data["version"], 1)
        self.assertEqual(set(data), {"version", "groups"})
        expected = copy.deepcopy(self.sg_before)
        for g in expected:
            g["scripts"] = [{k: v for k, v in s.items()
                             if not k.startswith("_") and k != "run_index"}
                            for s in g["scripts"]]
        self.assertEqual(data["groups"], expected)
        # memory is not stripped
        self.assertEqual(self.stub.script_groups, self.sg_before)
        # first save of the session made a backup of the old file
        self.assertEqual(self.read_bytes(self.backup_path), self.disk_before)

    def test_success_without_existing_file(self):
        os.remove(self.sg_path)
        self.assertIs(self.stub.save_script_groups(), True)
        self.assertTrue(os.path.exists(self.sg_path))
        self.assertFalse(os.path.exists(self.backup_path))

    def test_success_empty_list(self):
        self.stub.script_groups[:] = []
        self.assertIs(self.stub.save_script_groups(), True)
        self.assertEqual(self.read_json(self.sg_path), {"version": 1, "groups": []})

    def test_blocked_false_is_explicit_not_falsy_none(self):
        self.stub._script_groups_save_blocked = True
        self.assertIsNotNone(self.stub.save_script_groups())


# ----------------------------------------------------------------------
# R6-T2: import rollback on save failure (R6-AC-4 .. R6-AC-10)
# ----------------------------------------------------------------------
class TestImportRollback(R6Base):
    def run_failure(self, mode, scenario, via_sidebar=False):
        self.write_src(import_payload(scenario))
        self.set_answer(scenario)
        self.failure_patches(mode)
        save_spy = mock.Mock(wraps=self.stub.save_script_groups)
        self.stub.save_script_groups = save_spy
        if via_sidebar:
            self.stub.root = self.parent
            result = self.stub.sidebar_import_script_groups()
        else:
            result = self.stub.import_script_groups(self.parent)
        return result, save_spy

    def assert_rolled_back(self, result, save_spy):
        self.assertIsNone(result)
        self.assertIs(self.stub.script_groups, self.sg_ref)          # R6-AC-10
        self.assertEqual(self.stub.script_groups, self.sg_before)    # R6-AC-4..7
        save_spy.assert_called_once_with()
        self.assertNotIn(IMPORTED_MARK, self.logged_text())          # R6-AC-8
        self.stub.results_text.insert.assert_not_called()
        self.stub.results_text.see.assert_not_called()
        self.mb.showinfo.assert_not_called()
        self.mb.showerror.assert_called_once()                       # only the save error
        self.assertEqual(self.mb.showerror.call_args.args[0], "Script Groups")
        self.assert_disk_unchanged()

    def test_matrix_modes_and_answers(self):
        for mode in FAIL_MODES:
            for scenario in SCENARIOS:
                with self.subTest(mode=mode, scenario=scenario):
                    self.setUp()
                    result, spy = self.run_failure(mode, scenario)
                    self.assert_rolled_back(result, spy)
                    names = [g["name"] for g in self.stub.script_groups]
                    for leftover in ("New1", "New2", "Fresh", "g1", "G1 (2)", "g1 (2)",
                                     "G2 (2)"):
                        self.assertNotIn(leftover, names)

    # R6-AC-4
    def test_blocked_noclash(self):
        result, spy = self.run_failure("blocked", "noclash")
        self.assert_rolled_back(result, spy)
        self.mb.askyesno.assert_called_once()
        self.mb.showerror.assert_called_once_with("Script Groups", BLOCKED_MSG)

    # R6-AC-5
    def test_write_failure_noclash(self):
        result, spy = self.run_failure("write", "noclash")
        self.assert_rolled_back(result, spy)
        self.mb.showerror.assert_called_once_with(
            "Script Groups", "Cannot save script_groups.json:\ndisk locked")

    # R6-AC-6
    def test_yes_replaced_groups_restored_in_place(self):
        for mode in ("blocked", "write"):
            with self.subTest(mode=mode):
                self.setUp()
                old_g1 = self.sg_ref[0]
                result, spy = self.run_failure(mode, "yes")
                self.assert_rolled_back(result, spy)
                self.assertEqual([(g["name"], g["profile"]) for g in self.stub.script_groups],
                                 [("G1", "P1"), ("Shared", "P2"), ("G2", "P1"), ("G1", "P2")])
                self.assertEqual(self.stub.script_groups[0], old_g1)
                queries = [s["query"] for g in self.stub.script_groups for s in g["scripts"]]
                self.assertFalse([q for q in queries if q.startswith("IMPORTED")])

    # R6-AC-7
    def test_no_keep_both_renamed_copies_removed(self):
        for mode in ("blocked", "write"):
            with self.subTest(mode=mode):
                self.setUp()
                result, spy = self.run_failure(mode, "no")
                self.assert_rolled_back(result, spy)
                self.assertFalse([g for g in self.stub.script_groups if "(" in g["name"]])
                self.assertEqual(len(self.stub.script_groups), len(self.sg_before))

    def test_nested_values_deep_equal_and_independent(self):
        result, spy = self.run_failure("write", "yes")
        self.assert_rolled_back(result, spy)
        s = self.stub.script_groups[0]["scripts"][0]
        self.assertEqual(s["params"], {"x": [1, 2, {"deep": "v"}], "y": None})
        self.assertEqual(s["tags"], ["t1", ["n1", "n2"]])
        self.assertEqual(s["_tmp"], {"k": 1})
        self.assertEqual(s["run_index"], 4)
        self.assertEqual(self.stub.script_groups[1], self.sg_before[1])
        self.assertEqual(self.stub.script_groups[3], self.sg_before[3])

    # R6-AC-8 through the sidebar
    def test_sidebar_returns_none(self):
        for mode in FAIL_MODES:
            for scenario in SCENARIOS:
                with self.subTest(mode=mode, scenario=scenario):
                    self.setUp()
                    result, spy = self.run_failure(mode, scenario, via_sidebar=True)
                    self.assert_rolled_back(result, spy)
                    self.fd.askopenfilename.assert_called_once()
                    self.assertIs(self.fd.askopenfilename.call_args.kwargs["parent"],
                                  self.parent)

    # R6-AC-9
    def test_refresh_once_with_none_after_rollback(self):
        for mode in FAIL_MODES:
            for scenario in SCENARIOS:
                with self.subTest(mode=mode, scenario=scenario):
                    self.setUp()
                    seen = []

                    def cb(name):
                        seen.append((name, self.stub.script_groups is self.sg_ref,
                                     copy.deepcopy(self.stub.script_groups)))

                    callback = mock.Mock(side_effect=cb)
                    self.stub._script_groups_refresh = callback
                    self.stub._script_groups_window = mock.Mock(winfo_exists=lambda: True)
                    result, spy = self.run_failure(mode, scenario)
                    self.assert_rolled_back(result, spy)
                    callback.assert_called_once_with(None)
                    self.assertEqual(len(seen), 1)
                    self.assertIsNone(seen[0][0])
                    self.assertTrue(seen[0][1])
                    self.assertEqual(seen[0][2], self.sg_before)

    def test_refresh_after_save_not_before(self):
        order = []
        self.write_src(import_payload("noclash"))
        self.stub._script_groups_save_blocked = True
        real_save = self.stub.save_script_groups

        def save():
            order.append("save")
            return real_save()

        self.stub.save_script_groups = save
        self.stub._refresh_script_groups_window = lambda name=None: order.append(
            ("refresh", name, copy.deepcopy(self.stub.script_groups)))
        self.assertIsNone(self.stub.import_script_groups(self.parent))
        self.assertEqual(order, ["save", ("refresh", None, self.sg_before)])

    def test_window_closed_no_error(self):
        for window in (None, mock.Mock(winfo_exists=lambda: False), "absent"):
            with self.subTest(window=window):
                self.setUp()
                callback = mock.Mock()
                self.stub._script_groups_refresh = callback
                if window != "absent":
                    self.stub._script_groups_window = window
                result, spy = self.run_failure("blocked", "yes")
                self.assert_rolled_back(result, spy)
                callback.assert_not_called()
                self.assertIsNone(self.stub._script_groups_refresh)

    def test_no_refresh_attrs_no_error(self):
        result, spy = self.run_failure("write", "no")
        self.assert_rolled_back(result, spy)

    def test_flags_untouched_by_rollback(self):
        result, _ = self.run_failure("blocked", "yes")
        self.assertIsNone(result)
        self.assertTrue(self.stub._script_groups_save_blocked)

    def test_retry_after_failure_succeeds(self):
        # backup failed once -> next import saves for real and keeps the data
        self.write_src(import_payload("noclash"))
        with mock.patch("shutil.copy2", side_effect=OSError("locked")):
            self.assertIsNone(self.stub.import_script_groups(self.parent))
        self.assertEqual(self.stub.script_groups, self.sg_before)
        self.assertEqual(self.read_bytes(self.sg_path), self.disk_before)
        self.assertEqual(self.stub.import_script_groups(self.parent), "New2")
        self.assertIs(self.stub.script_groups, self.sg_ref)
        on_disk = self.read_json(self.sg_path)["groups"]
        self.assertEqual([g["name"] for g in on_disk],
                         ["G1", "Shared", "G2", "G1", "New1", "New2"])

    def test_empty_initial_list_rollback(self):
        self.stub.script_groups[:] = []
        self.sg_before = []
        result, spy = self.run_failure("write", "noclash")
        self.assert_rolled_back(result, spy)
        self.assertEqual(self.stub.script_groups, [])


# ----------------------------------------------------------------------
# R6-AC-11: success path unchanged (real save on tempdir)
# ----------------------------------------------------------------------
class TestImportSuccessUnchanged(R6Base):
    def run_ok(self, scenario):
        self.write_src(import_payload(scenario))
        self.set_answer(scenario)
        order = []
        real_save = self.stub.save_script_groups

        def save():
            order.append("save")
            ok = real_save()
            self.assertIs(ok, True)
            return ok

        self.stub.save_script_groups = mock.Mock(side_effect=save)
        callback = mock.Mock(side_effect=lambda name: order.append(("refresh", name)))
        self.stub._script_groups_refresh = callback
        self.stub._script_groups_window = mock.Mock(winfo_exists=lambda: True)
        self.stub.results_text.insert.side_effect = lambda *a: order.append("log")
        result = self.stub.import_script_groups(self.parent)
        return result, order

    def assert_common(self, result, order, last, n_incoming):
        self.assertEqual(result, last)
        self.stub.save_script_groups.assert_called_once_with()
        self.assertEqual(order, ["save", ("refresh", last), "log"])
        self.stub.results_text.insert.assert_called_once()
        args = self.stub.results_text.insert.call_args.args
        self.assertEqual(args[1], f"📥 Imported {n_incoming} group(s) from {self.src}\n")
        self.stub.results_text.see.assert_called_once()
        self.mb.showerror.assert_not_called()
        self.assertIs(self.stub.script_groups, self.sg_ref)
        on_disk = self.read_json(self.sg_path)
        self.assertEqual([g["name"] for g in on_disk["groups"]],
                         [g["name"] for g in self.stub.script_groups])
        self.assertNotEqual(self.read_bytes(self.sg_path), self.disk_before)

    def test_noclash(self):
        result, order = self.run_ok("noclash")
        self.assert_common(result, order, "New2", 2)
        self.assertEqual([g["name"] for g in self.stub.script_groups],
                         ["G1", "Shared", "G2", "G1", "New1", "New2"])
        self.assertEqual(self.stub.script_groups[:4], self.sg_before)

    def test_yes_replace(self):
        result, order = self.run_ok("yes")
        self.assert_common(result, order, "Fresh", 3)
        pairs = [(g["name"], g["profile"]) for g in self.stub.script_groups]
        self.assertEqual(pairs, [("Shared", "P2"), ("G1", "P2"), ("g1", "P1"),
                                 ("G2", "P1"), ("Fresh", "P1")])
        self.assertEqual(self.stub.script_groups[2]["scripts"], [{"query": "IMPORTED1"}])

    def test_no_keep_both(self):
        result, order = self.run_ok("no")
        self.assert_common(result, order, "Fresh", 3)
        self.assertEqual([g["name"] for g in self.stub.script_groups],
                         ["G1", "Shared", "G2", "G1", "g1 (2)", "G2 (2)", "Fresh"])
        self.assertEqual(self.stub.script_groups[:4], self.sg_before)

    def test_sidebar_success_returns_last_name(self):
        self.write_src(import_payload("noclash"))
        self.stub.root = self.parent
        self.assertEqual(self.stub.sidebar_import_script_groups(), "New2")
        self.assertIn(IMPORTED_MARK, self.logged_text())

    def test_truthy_mock_save_still_success(self):
        # design R6-R3: `if not save()` keeps Mock() (truthy) as success
        self.write_src(import_payload("noclash"))
        self.stub.save_script_groups = mock.Mock()
        self.assertEqual(self.stub.import_script_groups(self.parent), "New2")
        self.assertIn(IMPORTED_MARK, self.logged_text())

    def test_falsy_none_save_is_failure(self):
        self.write_src(import_payload("noclash"))
        self.stub.save_script_groups = mock.Mock(return_value=None)
        self.assertIsNone(self.stub.import_script_groups(self.parent))
        self.assertEqual(self.stub.script_groups, self.sg_before)
        self.assertIs(self.stub.script_groups, self.sg_ref)


# ----------------------------------------------------------------------
# R6-AC-12: Cancel / invalid file / no profile do not snapshot or save
# ----------------------------------------------------------------------
class TestNoSaveOnEarlyExit(R6Base):
    def setUp(self):
        super().setUp()
        self.stub.save_script_groups = mock.Mock(return_value=True)

    def assert_untouched(self, result):
        self.assertIsNone(result)
        self.stub.save_script_groups.assert_not_called()
        self.assertIs(self.stub.script_groups, self.sg_ref)
        self.assertEqual(self.stub.script_groups, self.sg_before)
        self.assert_disk_unchanged()

    def test_cancel_on_clash(self):
        self.write_src(import_payload("yes"))
        self.mb.askyesnocancel.return_value = None
        with mock.patch.object(app.copy, "deepcopy", wraps=copy.deepcopy) as dc:
            self.assert_untouched(self.stub.import_script_groups(self.parent))
        dc.assert_not_called()

    def test_no_on_noclash_confirm(self):
        self.write_src(import_payload("noclash"))
        self.mb.askyesno.return_value = False
        self.assert_untouched(self.stub.import_script_groups(self.parent))

    def test_invalid_file(self):
        with open(self.src, "w", encoding="utf-8") as fh:
            fh.write("{ broken")
        self.assert_untouched(self.stub.import_script_groups(self.parent))

    def test_no_profile(self):
        self.stub.profile_combo.get.return_value = ""
        self.assert_untouched(self.stub.import_script_groups(self.parent))


if __name__ == "__main__":
    unittest.main()
