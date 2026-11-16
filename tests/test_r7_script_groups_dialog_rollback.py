"""R7-T6 / R7-T7 (R7-5): the 8 actions of the Script Groups window roll back
when script_groups.json cannot be saved.

Covers R7-AC-21 .. R7-AC-27. Uses a real (withdrawn) Tk root and the real
dialog; the buttons are found by their text and pressed with invoke().
APP_DIR is a temporary directory, so the real script_groups.json is never
touched. Skipped when no display is available.
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

PROFILE = "P1"

BTN_NEW = "＋ New Group"
BTN_RENAME = "✎  Rename"
BTN_DELETE_GROUP = "\U0001F5D1  Delete"
BTN_ADD_SQL = "＋ Add SQL"
BTN_FROM_JOBS = "\U0001F558  From Saved Jobs"
BTN_EDIT = "✎ Edit"
BTN_REMOVE = "\U0001F5D1 Remove"
BTN_UP = "↑"
BTN_DOWN = "↓"

# (label for subTest, button text) - move_script counts as one action, two buttons
ACTIONS = (
    ("new_group", BTN_NEW),
    ("rename_group", BTN_RENAME),
    ("delete_group", BTN_DELETE_GROUP),
    ("add_sql", BTN_ADD_SQL),
    ("add_from_jobs", BTN_FROM_JOBS),
    ("edit_script", BTN_EDIT),
    ("delete_script", BTN_REMOVE),
    ("move_up", BTN_UP),
    ("move_down", BTN_DOWN),
)
FAILURES = ("blocked", "write_error")


def _initial_groups():
    return [
        {
            "name": "Alpha",
            "profile": PROFILE,
            "created": "2026-01-01 00:00:00",
            "scripts": [{"name": "a1", "query": "SELECT 1", "created": "2026-01-01 00:00:00"}],
        },
        {
            "name": "Foreign",
            "profile": "P2",
            "created": "2026-01-02 00:00:00",
            "scripts": [{"name": "f1", "query": "SELECT 'other profile'"}],
        },
        {
            "name": "Beta",
            "profile": PROFILE,
            "created": "2026-01-03 00:00:00",
            "scripts": [
                {"name": "b1", "query": "SELECT 'b1'"},
                {
                    "name": "b2",
                    "query": "SELECT * FROM t WHERE a IN (:ACC)",
                    "sql_template": "SELECT * FROM t WHERE a IN (:ACC)",
                    "excel_parameters": {
                        "ACC": {"column": "acct", "values": ["1", "2", ["nested", {"k": 1}]]},
                        "list": [{"deep": {"deeper": [1, 2, 3]}}],
                    },
                },
                {"name": "b3", "query": "SELECT 'b3'"},
            ],
        },
        {"name": "Gamma", "profile": PROFILE, "created": "2026-01-04 00:00:00", "scripts": []},
    ]


def _saved_form(groups):
    """Groups as save_script_groups writes them (no `_*` keys, no run_index)."""
    return [
        dict(
            group,
            scripts=[
                {k: v for k, v in script.items() if not k.startswith("_") and k != "run_index"}
                for script in group.get("scripts", [])
            ],
        )
        for group in groups
    ]


class _DialogCase(unittest.TestCase):
    """Opens the real Script Groups window on a withdrawn root."""

    def setUp(self):
        try:
            self.root = app.tk.Tk()
        except app.tk.TclError as error:  # pragma: no cover - no display
            self.skipTest(f"Tk not available: {error}")
        self.addCleanup(self._destroy_root)
        self.root.withdraw()

        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        patcher = mock.patch.object(app, "APP_DIR", self._tmp.name)
        patcher.start()
        self.addCleanup(patcher.stop)
        patcher = mock.patch.object(app, "messagebox")
        self.messagebox = patcher.start()
        self.addCleanup(patcher.stop)
        self.messagebox.askyesno.return_value = True

        self.path = os.path.join(self._tmp.name, "script_groups.json")
        with open(self.path, "w", encoding="utf-8") as handle:
            json.dump({"version": 1, "groups": _initial_groups()}, handle, indent=2)

        self.gui = app.DatabaseConnectorGUI(self.root)
        self.root.update_idletasks()
        self.gui.profile_combo.set(PROFILE)

        self.new_script = {"name": "new script", "query": "SELECT 'new'"}
        self.edit_result = {"name": "edited", "query": "SELECT 'edited'"}
        self.picked_jobs = [
            {"name": "job one", "query": "SELECT 'j1'", "profile": PROFILE, "run_index": 4,
             "_export_dataframe": object(), "_private": 1},
            {"name": "job two", "query": "SELECT 'j2'", "profile": PROFILE},
        ]
        self.gui._ask_group_text = mock.Mock(return_value="Delta")
        self.gui._edit_group_script_dialog = mock.Mock(side_effect=self._edit_dialog)
        self.gui._current_profile_jobs = mock.Mock(side_effect=lambda: list(self.picked_jobs))
        self.gui._pick_jobs_dialog = mock.Mock(side_effect=lambda _parent, jobs: list(jobs))
        self.save_spy = mock.Mock(wraps=self.gui.save_script_groups)
        self.gui.save_script_groups = self.save_spy

        self.gui.show_script_groups_dialog()
        self.dialog = self.gui._script_groups_window
        self.root.update()
        self.messagebox.reset_mock()
        self.messagebox.askyesno.return_value = True

        listboxes = [w for w in self._walk(self.dialog) if isinstance(w, app.tk.Listbox)]
        self.assertEqual(len(listboxes), 2)
        self.scripts_box = next(w for w in listboxes if int(w.cget("height")) == 9)
        self.groups_box = next(w for w in listboxes if w is not self.scripts_box)

    def _destroy_root(self):
        try:
            # the app's polling timers would otherwise fire on a dead interpreter
            for timer in self.root.tk.splitlist(self.root.tk.call("after", "info")):
                self.root.after_cancel(timer)
            self.root.destroy()
        except app.tk.TclError:
            pass

    def _edit_dialog(self, _parent, _title, script=None):
        return dict(self.new_script if script is None else self.edit_result)

    # ---- widgets ---------------------------------------------------------
    def _walk(self, widget):
        for child in widget.winfo_children():
            yield child
            yield from self._walk(child)

    def button(self, text):
        found = [
            w for w in self._walk(self.dialog)
            if isinstance(w, app.ttk.Button) and w.cget("text") == text
        ]
        self.assertEqual(len(found), 1, "button not found exactly once")
        return found[0]

    def press(self, text):
        button = self.button(text)
        self.assertNotIn("disabled", button.state(), "button is disabled - nothing selected?")
        button.invoke()
        self.root.update()

    def select_group(self, name):
        # <<ListboxSelect>> is not delivered to a withdrawn window, so the
        # group is chosen through the hook the window registers for imports
        # (refresh_groups(select_name=...)), which also redraws the scripts.
        self.gui._script_groups_refresh(name)
        self.root.update()
        self.assertEqual(self.selected_group_name(), name)
        self.assertEqual(
            self.scripts_box.get(0, app.tk.END), self.script_rows(self.gui.script_groups, name)
        )

    def select_script(self, index):
        self.scripts_box.selection_clear(0, app.tk.END)
        self.scripts_box.selection_set(index)
        self.root.update()
        self.assertEqual(self.scripts_box.curselection(), (index,))

    def select(self, group_name="Beta", script_index=1):
        self.select_group(group_name)
        if script_index is not None:
            self.select_script(script_index)

    # ---- state -----------------------------------------------------------
    def profile_groups(self, groups=None):
        groups = self.gui.script_groups if groups is None else groups
        return [g for g in groups if g.get("profile") == PROFILE]

    def group(self, name, groups=None):
        groups = self.gui.script_groups if groups is None else groups
        return next(g for g in groups if g["name"] == name and g.get("profile") == PROFILE)

    def selected_group_name(self):
        selection = self.groups_box.curselection()
        if not selection:
            return None
        return self.profile_groups()[selection[0]]["name"]

    def file_bytes(self):
        with open(self.path, "rb") as handle:
            return handle.read()

    def file_groups(self):
        with open(self.path, "r", encoding="utf-8") as handle:
            return json.load(handle)["groups"]

    def group_rows(self, groups):
        return tuple(
            f"{g['name']}  ({len(g.get('scripts', []))})" for g in self.profile_groups(groups)
        )

    def script_rows(self, groups, group_name):
        scripts = self.group(group_name, groups).get("scripts", [])
        return tuple(f"{n}. {s.get('name', '')}" for n, s in enumerate(scripts, 1))

    def assert_window_shows(self, groups, group_name, script_index):
        """Both listboxes show `groups`, with `group_name` / `script_index` selected."""
        self.assertEqual(self.groups_box.get(0, app.tk.END), self.group_rows(groups))
        names = [g["name"] for g in self.profile_groups(groups)]
        self.assertEqual(self.groups_box.curselection(), (names.index(group_name),))
        self.assertEqual(
            self.scripts_box.get(0, app.tk.END), self.script_rows(groups, group_name)
        )
        expected = () if script_index is None else (script_index,)
        self.assertEqual(self.scripts_box.curselection(), expected)

    def assert_memory_equals_file(self):
        self.assertEqual(_saved_form(self.gui.script_groups), self.file_groups())

    # ---- failure injection -------------------------------------------------
    def fail_saves(self, mode):
        """Make save_script_groups fail; returns a function that removes the cause."""
        if mode == "blocked":
            self.gui._script_groups_save_blocked = True

            def release():
                self.gui._script_groups_save_blocked = False

            return release
        patcher = mock.patch.object(
            app, "write_json_atomic", side_effect=OSError("disk is full")
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        return patcher.stop

    def press_expecting_rollback(self, button_text, group_name="Beta", script_index=1):
        """Press with saving broken and check R7-AC-21 / 22 / 23."""
        snapshot = copy.deepcopy(self.gui.script_groups)
        live_list = self.gui.script_groups
        disk = self.file_bytes()
        self.save_spy.reset_mock()
        self.messagebox.reset_mock()
        self.messagebox.askyesno.return_value = True

        self.press(button_text)

        # R7-AC-21
        self.assertEqual(self.gui.script_groups, snapshot)
        self.assertIs(self.gui.script_groups, live_list)
        self.assertEqual(self.save_spy.call_count, 1)
        self.assertEqual(self.file_bytes(), disk)
        self.assertFalse(os.path.exists(self.path + ".tmp"))
        # R7-AC-22
        self.assert_window_shows(snapshot, group_name, script_index)
        # R7-AC-23
        self.assertEqual(self.messagebox.showerror.call_count, 1)
        self.assertEqual(self.messagebox.showerror.call_args[0][0], "Script Groups")
        self.messagebox.showinfo.assert_not_called()
        self.messagebox.showwarning.assert_not_called()
        return snapshot


# ------------------------------------------------------------------ fixture sanity
class DialogFixtureTests(_DialogCase):
    def test_window_lists_only_groups_of_the_profile(self):
        self.assertEqual(
            self.groups_box.get(0, app.tk.END), ("Alpha  (1)", "Beta  (3)", "Gamma  (0)")
        )
        self.select()
        self.assertEqual(self.scripts_box.get(0, app.tk.END), ("1. b1", "2. b2", "3. b3"))
        for _label, text in ACTIONS:
            self.assertNotIn("disabled", self.button(text).state())
        self.save_spy.assert_not_called()


# ------------------------------------------- failed save: R7-AC-21 / 22 / 23 (T6, T7)
class FailedSaveRollsBackTests(_DialogCase):
    def _run(self, button_text, mode):
        self.select("Beta", 1)
        self.fail_saves(mode)
        return self.press_expecting_rollback(button_text)

    def test_new_group_blocked(self):
        self._run(BTN_NEW, "blocked")
        self.gui._ask_group_text.assert_called_once()

    def test_new_group_write_error(self):
        self._run(BTN_NEW, "write_error")

    def test_rename_group_blocked(self):
        self._run(BTN_RENAME, "blocked")
        self.assertEqual(self.selected_group_name(), "Beta")  # old name, not "Delta"
        self.assertNotIn("Delta", [g["name"] for g in self.gui.script_groups])

    def test_rename_group_write_error(self):
        self._run(BTN_RENAME, "write_error")
        self.assertEqual(self.selected_group_name(), "Beta")
        self.assertNotIn("Delta", [g["name"] for g in self.gui.script_groups])

    def test_delete_group_blocked(self):
        self._run(BTN_DELETE_GROUP, "blocked")
        self.messagebox.askyesno.assert_called_once()

    def test_delete_group_write_error(self):
        self._run(BTN_DELETE_GROUP, "write_error")

    def test_add_sql_blocked(self):
        self._run(BTN_ADD_SQL, "blocked")
        self.gui._edit_group_script_dialog.assert_called_once()

    def test_add_sql_write_error(self):
        self._run(BTN_ADD_SQL, "write_error")

    def test_add_from_jobs_blocked(self):
        self._run(BTN_FROM_JOBS, "blocked")
        self.gui._pick_jobs_dialog.assert_called_once()

    def test_add_from_jobs_write_error(self):
        self._run(BTN_FROM_JOBS, "write_error")

    def test_edit_script_blocked(self):
        snapshot = self._run(BTN_EDIT, "blocked")
        # the popped template keys came back with their nested values
        script = self.group("Beta")["scripts"][1]
        self.assertEqual(script, self.group("Beta", snapshot)["scripts"][1])
        self.assertIn("sql_template", script)
        self.assertEqual(script["excel_parameters"]["list"], [{"deep": {"deeper": [1, 2, 3]}}])

    def test_edit_script_write_error(self):
        self._run(BTN_EDIT, "write_error")
        self.assertIn("excel_parameters", self.group("Beta")["scripts"][1])

    def test_delete_script_blocked(self):
        self._run(BTN_REMOVE, "blocked")
        self.messagebox.askyesno.assert_called_once()

    def test_delete_script_write_error(self):
        self._run(BTN_REMOVE, "write_error")

    def test_move_up_blocked(self):
        self._run(BTN_UP, "blocked")

    def test_move_up_write_error(self):
        self._run(BTN_UP, "write_error")

    def test_move_down_blocked(self):
        self._run(BTN_DOWN, "blocked")

    def test_move_down_write_error(self):
        self._run(BTN_DOWN, "write_error")


class FailedSaveSelectionEdgeTests(_DialogCase):
    """R7-Q-4: the previous selection comes back, also at the edges."""

    def test_last_script_is_selected_again_after_failed_remove(self):
        for mode in FAILURES:
            with self.subTest(mode=mode):
                self.select("Beta", 2)
                release = self.fail_saves(mode)
                self.press_expecting_rollback(BTN_REMOVE, "Beta", 2)
                release()

    def test_last_script_is_selected_again_after_failed_edit_and_move(self):
        self.select("Beta", 2)
        self.fail_saves("blocked")
        self.press_expecting_rollback(BTN_EDIT, "Beta", 2)
        self.press_expecting_rollback(BTN_UP, "Beta", 2)
        self.select_script(0)
        self.press_expecting_rollback(BTN_DOWN, "Beta", 0)

    def test_group_without_scripts(self):
        for mode in FAILURES:
            with self.subTest(mode=mode):
                self.select("Gamma", None)
                release = self.fail_saves(mode)
                for text in (BTN_ADD_SQL, BTN_FROM_JOBS, BTN_RENAME, BTN_DELETE_GROUP, BTN_NEW):
                    self.press_expecting_rollback(text, "Gamma", None)
                release()

    def test_single_script_group(self):
        self.select("Alpha", 0)
        self.fail_saves("write_error")
        for text in (BTN_REMOVE, BTN_EDIT, BTN_ADD_SQL, BTN_DELETE_GROUP, BTN_RENAME):
            self.press_expecting_rollback(text, "Alpha", 0)

    def test_new_group_when_profile_has_no_group(self):
        self.gui.script_groups[:] = [g for g in self.gui.script_groups if g["profile"] == "P2"]
        self.gui._script_groups_refresh()
        self.root.update()
        self.assertEqual(self.groups_box.size(), 0)
        snapshot = copy.deepcopy(self.gui.script_groups)
        disk = self.file_bytes()
        for mode in FAILURES:
            with self.subTest(mode=mode):
                release = self.fail_saves(mode)
                self.messagebox.reset_mock()
                self.save_spy.reset_mock()
                self.press(BTN_NEW)
                release()

                self.assertEqual(self.gui.script_groups, snapshot)
                self.assertEqual(self.save_spy.call_count, 1)
                self.assertEqual(self.file_bytes(), disk)
                self.assertEqual(self.groups_box.size(), 0)
                self.assertEqual(self.scripts_box.size(), 0)
                self.assertEqual(self.messagebox.showerror.call_count, 1)
                self.assertIn("disabled", self.button(BTN_RENAME).state())

    def test_repeated_failures_never_change_anything(self):
        self.select("Beta", 1)
        self.fail_saves("blocked")
        original = copy.deepcopy(self.gui.script_groups)
        for _round in range(2):
            for _label, text in ACTIONS:
                self.press_expecting_rollback(text)
        self.assertEqual(self.gui.script_groups, original)
        self.assertEqual(self.file_groups(), _initial_groups())


# ---------------------------------------------- R7-AC-24: next action edits live data
class ActionAfterRollbackTests(_DialogCase):
    def assert_added_to_beta(self):
        beta_file = self.group("Beta", self.file_groups())
        self.assertEqual([s["name"] for s in beta_file["scripts"]],
                         ["b1", "b2", "b3", "new script"])
        beta_live = self.group("Beta")
        self.assertTrue(any(g is beta_live for g in self.gui.script_groups))
        self.assertEqual(beta_live["scripts"][-1]["query"], "SELECT 'new'")
        self.assert_memory_equals_file()
        self.assertNotIn("Delta", [g["name"] for g in self.file_groups()])

    def test_rename_then_edit_fail_then_add_sql_succeeds(self):
        for mode in FAILURES:
            with self.subTest(mode=mode):
                self.select("Beta", 1)
                release = self.fail_saves(mode)
                self.press_expecting_rollback(BTN_RENAME)
                self.press_expecting_rollback(BTN_EDIT)
                release()
                self.messagebox.reset_mock()
                self.save_spy.reset_mock()
                before = copy.deepcopy(self.gui.script_groups)

                self.press(BTN_ADD_SQL)

                self.assertEqual(self.save_spy.call_count, 1)
                self.messagebox.showerror.assert_not_called()
                self.assert_added_to_beta()
                # nothing but the new script changed
                after = copy.deepcopy(self.gui.script_groups)
                self.group("Beta", after)["scripts"].pop()
                self.assertEqual(after, before)
                self.assertEqual(self.group("Beta")["scripts"][1]["name"], "b2")
                self.assert_window_shows(self.gui.script_groups, "Beta", 3)
                # put the fixture back for the next mode
                self.group("Beta")["scripts"].pop()
                self.assertTrue(self.gui.save_script_groups())
                self.gui._script_groups_refresh()
                self.root.update()

    def test_every_failed_action_leaves_the_window_on_live_objects(self):
        for label, text in ACTIONS:
            for mode in FAILURES:
                with self.subTest(action=label, mode=mode):
                    self.select("Beta", 1)
                    release = self.fail_saves(mode)
                    self.press_expecting_rollback(text)
                    release()
                    self.messagebox.reset_mock()

                    self.press(BTN_ADD_SQL)

                    self.messagebox.showerror.assert_not_called()
                    self.assert_added_to_beta()
                    self.assert_window_shows(self.gui.script_groups, "Beta", 3)
                    # put the fixture back for the next action
                    self.group("Beta")["scripts"].pop()
                    self.assertTrue(self.gui.save_script_groups())
                    self.gui._script_groups_refresh()
                    self.root.update()

    def test_rename_succeeds_after_failed_rename(self):
        self.select("Beta", 1)
        release = self.fail_saves("write_error")
        self.press_expecting_rollback(BTN_RENAME)
        release()
        self.messagebox.reset_mock()

        self.press(BTN_RENAME)

        self.messagebox.showerror.assert_not_called()
        self.assertEqual([g["name"] for g in self.profile_groups()], ["Alpha", "Delta", "Gamma"])
        self.assertEqual([g["name"] for g in self.file_groups()],
                         ["Alpha", "Foreign", "Delta", "Gamma"])
        self.assert_memory_equals_file()
        self.assertEqual(self.selected_group_name(), "Delta")

    def test_edit_and_move_after_rollback_change_the_saved_script(self):
        self.select("Beta", 1)
        release = self.fail_saves("blocked")
        self.press_expecting_rollback(BTN_DELETE_GROUP)
        self.press_expecting_rollback(BTN_UP)
        release()
        self.messagebox.reset_mock()

        self.press(BTN_EDIT)
        self.press(BTN_DOWN)

        self.messagebox.showerror.assert_not_called()
        names = [s["name"] for s in self.group("Beta", self.file_groups())["scripts"]]
        self.assertEqual(names, ["b1", "b3", "edited"])
        self.assert_memory_equals_file()
        self.assert_window_shows(self.gui.script_groups, "Beta", 2)


# ------------------------------------------------------- R7-AC-25: success unchanged
class SuccessfulSaveTests(_DialogCase):
    def setUp(self):
        super().setUp()
        self.select("Beta", 1)
        self.live_list = self.gui.script_groups

    def assert_saved_once(self):
        self.assertEqual(self.save_spy.call_count, 1)
        self.messagebox.showerror.assert_not_called()
        self.assertIs(self.gui.script_groups, self.live_list)
        self.assert_memory_equals_file()

    def test_new_group(self):
        self.press(BTN_NEW)

        self.assert_saved_once()
        added = self.gui.script_groups[-1]
        self.assertEqual((added["name"], added["profile"], added["scripts"]),
                         ("Delta", PROFILE, []))
        self.assertIn("created", added)
        self.assertEqual(self.file_groups()[-1]["name"], "Delta")
        self.assert_window_shows(self.gui.script_groups, "Delta", None)

    def test_rename_group(self):
        self.press(BTN_RENAME)

        self.assert_saved_once()
        self.assertEqual([g["name"] for g in self.file_groups()],
                         ["Alpha", "Foreign", "Delta", "Gamma"])
        self.assertEqual(len(self.group("Delta")["scripts"]), 3)
        self.assert_window_shows(self.gui.script_groups, "Delta", 0)

    def test_delete_group(self):
        self.press(BTN_DELETE_GROUP)

        self.assert_saved_once()
        self.assertEqual([g["name"] for g in self.file_groups()], ["Alpha", "Foreign", "Gamma"])
        self.assertEqual(self.groups_box.get(0, app.tk.END), ("Alpha  (1)", "Gamma  (0)"))
        self.assertEqual(len(self.groups_box.curselection()), 1)

    def test_add_sql(self):
        self.press(BTN_ADD_SQL)

        self.assert_saved_once()
        scripts = self.group("Beta", self.file_groups())["scripts"]
        self.assertEqual([s["name"] for s in scripts], ["b1", "b2", "b3", "new script"])
        self.assertIn("created", scripts[-1])
        self.assert_window_shows(self.gui.script_groups, "Beta", 3)

    def test_add_from_jobs(self):
        self.press(BTN_FROM_JOBS)

        self.assert_saved_once()
        scripts = self.group("Beta", self.file_groups())["scripts"]
        self.assertEqual([s["name"] for s in scripts], ["b1", "b2", "b3", "job one", "job two"])
        for added in self.group("Beta")["scripts"][3:]:
            self.assertEqual(sorted(added), ["created", "name", "query"])
        self.assert_window_shows(self.gui.script_groups, "Beta", 4)

    def test_edit_script(self):
        self.press(BTN_EDIT)

        self.assert_saved_once()
        script = self.group("Beta", self.file_groups())["scripts"][1]
        self.assertEqual(script, {"name": "edited", "query": "SELECT 'edited'"})
        self.assert_window_shows(self.gui.script_groups, "Beta", 1)

    def test_delete_script(self):
        self.press(BTN_REMOVE)

        self.assert_saved_once()
        scripts = self.group("Beta", self.file_groups())["scripts"]
        self.assertEqual([s["name"] for s in scripts], ["b1", "b3"])
        self.assert_window_shows(self.gui.script_groups, "Beta", 1)

    def test_move_up(self):
        self.press(BTN_UP)

        self.assert_saved_once()
        scripts = self.group("Beta", self.file_groups())["scripts"]
        self.assertEqual([s["name"] for s in scripts], ["b2", "b1", "b3"])
        self.assert_window_shows(self.gui.script_groups, "Beta", 0)

    def test_move_down(self):
        self.press(BTN_DOWN)

        self.assert_saved_once()
        scripts = self.group("Beta", self.file_groups())["scripts"]
        self.assertEqual([s["name"] for s in scripts], ["b1", "b3", "b2"])
        self.assert_window_shows(self.gui.script_groups, "Beta", 2)

    def test_other_profile_group_is_never_touched(self):
        # Rename turns Beta into Delta, New Group then adds Epsilon
        self.gui._ask_group_text = mock.Mock(side_effect=["Delta", "Epsilon"])
        for text in (BTN_ADD_SQL, BTN_FROM_JOBS, BTN_EDIT, BTN_REMOVE, BTN_UP, BTN_DOWN,
                     BTN_RENAME, BTN_NEW):
            self.press(text)
        self.select("Delta", 0)
        self.press(BTN_DELETE_GROUP)

        self.assertEqual(self.save_spy.call_count, 9)
        self.assertEqual([g["name"] for g in self.file_groups()],
                         ["Alpha", "Foreign", "Gamma", "Epsilon"])
        foreign = [g for g in self.file_groups() if g["profile"] == "P2"]
        self.assertEqual(foreign, [_initial_groups()[1]])
        self.assertEqual(self.group("Alpha", self.file_groups()), _initial_groups()[0])
        self.assert_memory_equals_file()
        self.messagebox.showerror.assert_not_called()


class TruthySaveResultTests(_DialogCase):
    """R7-AC-27: a truthy (non-bool) result of save_script_groups is a success."""

    def test_mock_save_is_treated_as_success_for_every_action(self):
        self.gui.save_script_groups = mock.Mock()
        expected_selection = {
            BTN_NEW: ("Delta", None),
            BTN_ADD_SQL: ("Delta", 0),
            BTN_FROM_JOBS: ("Delta", 2),
            BTN_UP: ("Delta", 1),
            BTN_DOWN: ("Delta", 2),
            BTN_EDIT: ("Delta", 2),
            BTN_REMOVE: ("Delta", 1),
        }
        for text, (group_name, script_index) in expected_selection.items():
            with self.subTest(button=text.encode("ascii", "backslashreplace").decode()):
                self.gui.save_script_groups.reset_mock()
                self.press(text)
                self.assertEqual(self.gui.save_script_groups.call_count, 1)
                self.assert_window_shows(self.gui.script_groups, group_name, script_index)
        self.assertEqual([s["name"] for s in self.group("Delta")["scripts"]],
                         ["new script", "job one"])

        self.gui._ask_group_text.return_value = "Epsilon"
        self.press(BTN_RENAME)
        self.assertEqual(self.selected_group_name(), "Epsilon")
        self.press(BTN_DELETE_GROUP)
        self.assertEqual(self.groups_box.get(0, app.tk.END),
                         ("Alpha  (1)", "Beta  (3)", "Gamma  (0)"))
        self.messagebox.showerror.assert_not_called()
        self.assertEqual(self.file_groups(), _initial_groups())  # the mock never wrote


# ------------------------------------------------------ R7-AC-26: cancelled / no-op
class CancelledActionTests(_DialogCase):
    def setUp(self):
        super().setUp()
        self.select("Beta", 1)
        self.snapshot = copy.deepcopy(self.gui.script_groups)
        self.disk = self.file_bytes()
        # a save here would fail loudly - it must not even be attempted
        self.gui._script_groups_save_blocked = True

    def assert_nothing_happened(self, script_index=1):
        self.save_spy.assert_not_called()
        self.assertEqual(self.gui.script_groups, self.snapshot)
        self.assertEqual(self.file_bytes(), self.disk)
        self.messagebox.showerror.assert_not_called()
        self.assert_window_shows(self.snapshot, "Beta", script_index)

    def test_new_group_empty_name(self):
        for name in (None, ""):
            with self.subTest(name=name):
                self.gui._ask_group_text.return_value = name
                self.press(BTN_NEW)
                self.assert_nothing_happened()

    def test_new_group_duplicate_name(self):
        for name in ("Alpha", "beta"):
            with self.subTest(name=name):
                self.messagebox.reset_mock()
                self.gui._ask_group_text.return_value = name
                self.press(BTN_NEW)
                self.assert_nothing_happened()
                self.assertEqual(self.messagebox.showwarning.call_count, 1)

    def test_new_group_without_profile(self):
        self.gui.profile_combo.set("")
        self.press(BTN_NEW)
        self.save_spy.assert_not_called()
        self.gui._ask_group_text.assert_not_called()
        self.assertEqual(self.gui.script_groups, self.snapshot)
        self.assertEqual(self.file_bytes(), self.disk)
        self.assertEqual(self.messagebox.showwarning.call_count, 1)

    def test_rename_cancelled_or_same_name(self):
        for name in (None, "", "Beta"):
            with self.subTest(name=name):
                self.gui._ask_group_text.return_value = name
                self.press(BTN_RENAME)
                self.assert_nothing_happened()

    def test_rename_to_existing_name(self):
        self.gui._ask_group_text.return_value = "gamma"
        self.press(BTN_RENAME)
        self.assert_nothing_happened()
        self.assertEqual(self.messagebox.showwarning.call_count, 1)

    def test_delete_group_answered_no(self):
        self.messagebox.askyesno.return_value = False
        self.press(BTN_DELETE_GROUP)
        self.assert_nothing_happened()
        self.messagebox.askyesno.assert_called_once()

    def test_add_sql_cancelled(self):
        for result in (None, {}):
            with self.subTest(result=result):
                self.gui._edit_group_script_dialog = mock.Mock(return_value=result)
                self.press(BTN_ADD_SQL)
                self.assert_nothing_happened()

    def test_add_from_jobs_nothing_picked(self):
        for chosen in ([], None):
            with self.subTest(chosen=chosen):
                self.gui._pick_jobs_dialog = mock.Mock(return_value=chosen)
                self.press(BTN_FROM_JOBS)
                self.assert_nothing_happened()

    def test_add_from_jobs_profile_has_no_jobs(self):
        self.picked_jobs = []
        self.press(BTN_FROM_JOBS)
        self.assert_nothing_happened()
        self.gui._pick_jobs_dialog.assert_not_called()
        self.assertEqual(self.messagebox.showinfo.call_count, 1)

    def test_edit_script_cancelled(self):
        self.gui._edit_group_script_dialog = mock.Mock(return_value=None)
        self.press(BTN_EDIT)
        self.assert_nothing_happened()
        self.assertIn("sql_template", self.group("Beta")["scripts"][1])

    def test_delete_script_answered_no(self):
        self.messagebox.askyesno.return_value = False
        self.press(BTN_REMOVE)
        self.assert_nothing_happened()

    def test_move_up_at_top(self):
        self.select_script(0)
        self.press(BTN_UP)
        self.assert_nothing_happened(script_index=0)

    def test_move_down_at_bottom(self):
        self.select_script(2)
        self.press(BTN_DOWN)
        self.assert_nothing_happened(script_index=2)


if __name__ == "__main__":
    unittest.main()
