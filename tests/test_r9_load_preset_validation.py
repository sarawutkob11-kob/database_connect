"""R9-T2: Load Preset must not lose the current profile's jobs (Bugfix B2).

R9-AC-1 .. R9-AC-14 (Round 9). No Tk window, no database: widgets come from
``fake_dialog_widgets`` (tests/test_bugfix_h3.py), ``messagebox`` is always
patched and every file lives in a TemporaryDirectory. The only code path that
prints (preset list skipping a bad file, R9-AC-7) runs with sys.stdout
patched, so nothing outside cp874 reaches the real console.
"""

import copy
import io
import json
import os
import sys
import tempfile
import unittest
from typing import Any, Callable, Dict, List, Optional, Tuple
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import database_connect_gui as app  # noqa: E402
from test_bugfix_h3 import fake_dialog_widgets, make_job_stub  # noqa: E402

_REAL_JSON_LOAD = json.load

# "Initial state": PROD and UAT jobs interleaved, nested values and Thai text.
INITIAL_JOBS: List[Dict[str, Any]] = [
    {
        "name": "P-job0",
        "query": "SELECT * FROM ลูกค้า WHERE id = 0",
        "profile": "PROD",
        "excel_parameters": {"WHERE acc_no": ["AUTO_WHERE", "'A', 'B'"]},
        "tags": ["ไทย", 1, None],
    },
    {
        "name": "U-job",
        "query": "SELECT 'งาน' FROM dual",
        "profile": "UAT",
        "meta": {"nested": {"deep": ["x", "ข"]}},
    },
    {
        "name": "P-job1",
        "query": "DELETE FROM t WHERE c = 'ค'",
        "profile": "PROD",
        "run_index": 3,
    },
    {
        "name": "P-job2",
        "query": "UPDATE t SET a = 1",
        "profile": "PROD",
        "database": "ฐานข้อมูล",
        "options": [{"k": [1, 2]}, "z"],
    },
]


def ok_job(name: str) -> Dict[str, Any]:
    return {"name": name, "query": f"SELECT '{name}' FROM dual"}


NON_DICT_ELEMENTS: List[Tuple[str, Any]] = [
    ("None", None),
    ("int 1", 1),
    ("str x", "x"),
    ("empty list", []),
    ("True", True),
]
_BAD_VALUES: List[Tuple[str, Any]] = [
    ("None", None),
    ("number", 5),
    ("list", ["x"]),
    ("empty", ""),
    ("spaces", "   "),
]

# (label, element, reason fragment expected in the message)
BAD_ELEMENTS: List[Tuple[str, Any, str]] = (
    [(f"not dict {label}", value, "is not a job object") for label, value in NON_DICT_ELEMENTS]
    + [
        ("missing query", {"name": "no-query"}, "'query'"),
        ("missing name", {"query": "SELECT 1"}, "'name'"),
    ]
    + [(f"name {label}", {"name": value, "query": "SELECT 1"}, "'name'")
       for label, value in _BAD_VALUES]
    + [(f"query {label}", {"name": "n", "query": value}, "'query'")
       for label, value in _BAD_VALUES]
)


def read_bytes(path: str) -> bytes:
    with open(path, "rb") as handle:
        return handle.read()


def read_json(path: str) -> Any:
    with open(path, encoding="utf-8") as handle:
        return _REAL_JSON_LOAD(handle)


class LoadPresetBase(unittest.TestCase):
    """Fixture: real saved_jobs.json + PROD profile + patched messagebox."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.folder = self._tmp.name
        self.jobs = copy.deepcopy(INITIAL_JOBS)
        self.job_objects = list(self.jobs)
        self.before = copy.deepcopy(self.jobs)

        self.stub = make_job_stub(self.jobs)
        self.stub.jobs_file = os.path.join(self.folder, "saved_jobs.json")
        self.stub._jobs_save_blocked = False
        self.stub.profile_combo = mock.Mock()
        self.stub.profile_combo.get.return_value = "PROD"

        with mock.patch.object(app, "messagebox"):
            self.assertIs(self.stub.save_jobs(), True)  # real save_jobs writes the file
        self.jobs_bytes = read_bytes(self.stub.jobs_file)
        self.assertEqual(read_json(self.stub.jobs_file), self.before)

        self.loaded_objects: List[Any] = []

    # ---------------------------------------------------------------- helpers
    def write_preset(self, name: str, data: Any) -> str:
        path = os.path.join(self.folder, f"preset_{name}.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False)
        return path

    def _capturing_load(self, handle: Any, *args: Any, **kwargs: Any) -> Any:
        data = _REAL_JSON_LOAD(handle, *args, **kwargs)
        self.loaded_objects.append(data)
        return data

    def open_dialog(self, widgets: Dict[str, list]) -> Tuple[Any, Any, Callable[[], None]]:
        """Open load_preset_dialog, keeping the dicts the dialog read (preset_data)."""
        with mock.patch.object(app.json, "load", side_effect=self._capturing_load):
            self.stub.load_preset_dialog()
        dialog = widgets["toplevels"][0]
        listbox = widgets["listboxes"][0]
        load_button = next(b for b in widgets["tk_buttons"] if b.command is not None)
        return dialog, listbox, load_button.command

    def select(self, listbox: Any, preset_name: str) -> None:
        matches = [i for i, item in enumerate(listbox.items)
                   if item.startswith(f"{preset_name} (")]
        self.assertEqual(len(matches), 1, listbox.items)
        index = matches[0]
        listbox.curselection = lambda: (index,)

    def press(self, command: Callable[[], None]) -> Optional[BaseException]:
        """Press Load like Tk does: an exception must not escape (it would be lost)."""
        try:
            command()
        except Exception as error:  # noqa: BLE001 - recorded and asserted on
            return error
        return None

    def assert_saved_jobs_unchanged(self) -> None:
        self.assertIs(self.stub.saved_jobs, self.jobs)
        self.assertEqual(len(self.stub.saved_jobs), len(self.job_objects))
        for current, original in zip(self.stub.saved_jobs, self.job_objects):
            self.assertIs(current, original)
        self.assertEqual(self.stub.saved_jobs, self.before)

    def assert_no_success(self, messagebox: Any, dialog: Any) -> None:
        self.stub.update_jobs_list.assert_not_called()
        self.assertEqual(self.stub.results_text.inserted, [])
        messagebox.showinfo.assert_not_called()
        self.assertFalse(dialog.destroyed)

    def assert_jobs_file_unchanged(self) -> None:
        self.assertEqual(read_bytes(self.stub.jobs_file), self.jobs_bytes)


# --------------------------------------------------------------------------
# R9-AC-1 .. R9-AC-4: broken preset is rejected before touching anything
# --------------------------------------------------------------------------
class BrokenPresetRejectedTests(LoadPresetBase):

    def _reject_case(self, preset_jobs: List[Any], position: int, reason: str) -> None:
        preset = {"created": "2026-01-02T10:00:00", "jobs": preset_jobs}
        preset_path = self.write_preset("broken", preset)
        preset_bytes = read_bytes(preset_path)

        with fake_dialog_widgets() as widgets, \
                mock.patch.object(app, "messagebox") as messagebox, \
                mock.patch.object(self.stub, "save_jobs",
                                  wraps=self.stub.save_jobs) as save_spy:
            messagebox.askyesno.return_value = True
            dialog, listbox, command = self.open_dialog(widgets)
            self.select(listbox, "broken")
            escaped = self.press(command)

        # R9-AC-1
        self.assertIsNone(escaped, f"exception escaped the Load callback: {escaped!r}")
        self.assert_saved_jobs_unchanged()

        # R9-AC-2
        messagebox.askyesno.assert_not_called()
        self.stub.profile_combo.get.assert_not_called()
        save_spy.assert_not_called()
        self.assert_no_success(messagebox, dialog)
        messagebox.showwarning.assert_not_called()

        # R9-AC-3
        messagebox.showerror.assert_called_once()
        args, kwargs = messagebox.showerror.call_args
        self.assertIs(kwargs.get("parent"), dialog)
        self.assertEqual(args[0], "Invalid Preset")
        message = args[1]
        self.assertIn("'broken'", message)
        self.assertIn(f"Job #{position} ", message)
        self.assertIn(reason, message)

        # R9-AC-4
        self.assert_jobs_file_unchanged()
        self.assertEqual(read_bytes(preset_path), preset_bytes)
        self.assertEqual(len(self.loaded_objects), 1)
        preset_in_dialog = self.loaded_objects[0]
        self.assertEqual(preset_in_dialog, preset)
        for element in preset_in_dialog["jobs"]:
            if isinstance(element, dict):
                self.assertNotIn("profile", element)

    def _fresh(self) -> None:
        """Each subTest gets its own folder/stub/state."""
        self.doCleanups()
        self.setUp()

    def test_bad_element_in_middle_is_reported_as_job_2(self) -> None:
        for label, element, reason in BAD_ELEMENTS:
            with self.subTest(element=label):
                self._fresh()
                self._reject_case([ok_job("ok1"), copy.deepcopy(element), ok_job("ok3")],
                                  2, reason)

    def test_bad_element_first_is_reported_as_job_1(self) -> None:
        for label, element, reason in BAD_ELEMENTS:
            with self.subTest(element=label):
                self._fresh()
                self._reject_case([copy.deepcopy(element), ok_job("ok2"), ok_job("ok3")],
                                  1, reason)

    def test_bad_element_last_is_reported_as_job_3(self) -> None:
        for label, element, reason in BAD_ELEMENTS:
            with self.subTest(element=label):
                self._fresh()
                self._reject_case([ok_job("ok1"), ok_job("ok2"), copy.deepcopy(element)],
                                  3, reason)

    def test_probe_case_ok_then_null(self) -> None:
        self._reject_case([ok_job("ok"), None], 2, "is not a job object")

    def test_first_broken_element_is_reported_when_2_and_3_are_broken(self) -> None:
        self._reject_case([ok_job("ok"), {"name": "", "query": "SELECT 1"}, None],
                          2, "'name'")

    def test_dict_missing_both_keys_is_rejected(self) -> None:
        self._reject_case([ok_job("ok"), {"database": "x"}], 2, "Job #2 ")

    def test_position_twelve_is_not_confused_with_one(self) -> None:
        jobs: List[Any] = [ok_job(f"ok{i}") for i in range(1, 12)] + [{"name": "x"}]
        self._reject_case(jobs, 12, "'query'")


# --------------------------------------------------------------------------
# R9-AC-5 / R9-AC-6 / R9-AC-7
# --------------------------------------------------------------------------
class AfterRejectTests(LoadPresetBase):

    def _reject_then_save_new(self, preset_jobs: List[Any]) -> None:
        self.write_preset("broken", {"created": "2026-01-02", "jobs": preset_jobs})
        with fake_dialog_widgets() as widgets, \
                mock.patch.object(app, "messagebox") as messagebox:
            messagebox.askyesno.return_value = True
            _dialog, listbox, command = self.open_dialog(widgets)
            self.select(listbox, "broken")
            escaped = self.press(command)  # Tk would swallow it; keep going like the probe

            new_job = {"name": "new", "query": "SELECT 9", "profile": "PROD"}
            self.stub.saved_jobs.append(new_job)
            self.assertIs(self.stub.save_jobs(), True)

        on_disk = read_json(self.stub.jobs_file)
        self.assertEqual([job.get("name") for job in on_disk],
                         ["P-job0", "U-job", "P-job1", "P-job2", "new"])
        self.assertEqual(on_disk, self.before + [new_job])
        self.assertIsNone(escaped, f"exception escaped the Load callback: {escaped!r}")

    def test_next_save_keeps_all_original_jobs_probe(self) -> None:
        """R9-AC-5: opposite of the probe result ['U-job', 'ok', 'new']."""
        self._reject_then_save_new([ok_job("ok"), None])

    def test_next_save_keeps_all_original_jobs_bad_dict(self) -> None:
        """R9-AC-5 with a dict element that has no valid query."""
        self._reject_then_save_new([ok_job("ok"), {"name": "q", "query": 7}, ok_job("ok3")])

    def test_good_preset_loads_after_broken_one_in_same_dialog(self) -> None:
        """R9-AC-6."""
        self.write_preset("broken", {"created": "2026-01-02",
                                     "jobs": [ok_job("bad-ok"), [], ok_job("bad-ok3")]})
        good_jobs = [ok_job("good1"), dict(ok_job("good2"), profile="UAT")]
        good_path = self.write_preset("good", {"created": "2026-01-03", "jobs": good_jobs})
        good_bytes = read_bytes(good_path)
        u_job = self.job_objects[1]

        with fake_dialog_widgets() as widgets, \
                mock.patch.object(app, "messagebox") as messagebox:
            messagebox.askyesno.return_value = True
            dialog, listbox, command = self.open_dialog(widgets)

            self.select(listbox, "broken")
            self.assertIsNone(self.press(command))
            messagebox.showerror.assert_called_once()
            messagebox.askyesno.assert_not_called()
            self.assert_saved_jobs_unchanged()

            self.select(listbox, "good")
            self.assertIsNone(self.press(command))

        messagebox.showerror.assert_called_once()  # only the first (reject) one
        messagebox.askyesno.assert_called_once_with(
            "Confirm Load",
            "Load preset 'good'?\n\nThis will replace current 3 jobs with 2 jobs from preset.",
            parent=dialog,
        )
        expected = [
            self.before[1],
            {"name": "good1", "query": "SELECT 'good1' FROM dual", "profile": "PROD"},
            {"name": "good2", "query": "SELECT 'good2' FROM dual", "profile": "PROD"},
        ]
        self.assertEqual(self.stub.saved_jobs, expected)
        self.assertIs(self.stub.saved_jobs[0], u_job)
        self.assertEqual(read_json(self.stub.jobs_file), expected)
        self.stub.update_jobs_list.assert_called_once_with()
        messagebox.showinfo.assert_called_once()
        self.assertTrue(dialog.destroyed)
        self.assertEqual(read_bytes(good_path), good_bytes)

    def test_preset_list_unchanged_and_bad_files_skipped(self) -> None:
        """R9-AC-7."""
        self.write_preset("broken", {"created": "2026-01-02T10:00:00",
                                     "jobs": [ok_job("a"), None, ok_job("c")]})
        self.write_preset("good", {"created": "2026-01-03T11:00:00",
                                   "jobs": [ok_job("g")]})
        with open(os.path.join(self.folder, "preset_corrupt.json"), "w",
                  encoding="utf-8") as handle:
            handle.write("{not json")
        self.write_preset("jobsint", {"created": "2026-01-04", "jobs": 5})

        stdout = io.StringIO()
        with fake_dialog_widgets() as widgets, \
                mock.patch.object(app, "messagebox") as messagebox, \
                mock.patch("sys.stdout", stdout):
            _dialog, listbox, _command = self.open_dialog(widgets)

        self.assertEqual(sorted(listbox.items), [
            "broken (3 jobs) - 2026-01-02",
            "good (1 jobs) - 2026-01-03",
        ])
        skipped = [line for line in stdout.getvalue().splitlines() if "skipped" in line]
        self.assertEqual(len(skipped), 2, stdout.getvalue())
        self.assertTrue(any("preset_corrupt.json" in line for line in skipped))
        self.assertTrue(any("preset_jobsint.json" in line for line in skipped))
        messagebox.showerror.assert_not_called()
        self.assert_saved_jobs_unchanged()
        self.assert_jobs_file_unchanged()


# --------------------------------------------------------------------------
# R9-AC-8: unexpected exception is rolled back
# --------------------------------------------------------------------------
class UnexpectedExceptionRollbackTests(LoadPresetBase):

    def test_exception_in_save_jobs_is_rolled_back_and_reported(self) -> None:
        preset_path = self.write_preset("good", {"created": "2026-01-03",
                                                 "jobs": [ok_job("g1"), ok_job("g2")]})
        preset_bytes = read_bytes(preset_path)

        def mutate_then_raise() -> bool:
            self.stub.saved_jobs.append({"name": "temporary"})
            self.stub.saved_jobs[0]["meta"]["nested"]["deep"].append("changed")
            self.stub.saved_jobs[0]["name"] = "renamed"
            raise RuntimeError("boom")

        self.stub.save_jobs = mock.Mock(side_effect=mutate_then_raise)

        with fake_dialog_widgets() as widgets, \
                mock.patch.object(app, "messagebox") as messagebox:
            messagebox.askyesno.return_value = True
            dialog, listbox, command = self.open_dialog(widgets)
            self.select(listbox, "good")
            escaped = self.press(command)

        self.assertIsNone(escaped, f"exception escaped the Load callback: {escaped!r}")
        self.stub.save_jobs.assert_called_once_with()
        self.assert_saved_jobs_unchanged()
        self.assert_no_success(messagebox, dialog)
        messagebox.showerror.assert_called_once()
        args, kwargs = messagebox.showerror.call_args
        self.assertIs(kwargs.get("parent"), dialog)
        self.assertIn("boom", args[1])
        self.assertIn("'good'", args[1])
        self.assert_jobs_file_unchanged()
        self.assertEqual(read_bytes(preset_path), preset_bytes)

    def test_exception_while_filtering_jobs_is_rolled_back(self) -> None:
        """The try also covers the filter / append loop, not just save_jobs."""
        self.write_preset("good", {"created": "2026-01-03", "jobs": [ok_job("g1")]})

        class _FailsOnThirdIteration(list):
            # 1: count for askyesno, 2: snapshot list(), 3: filter inside try
            iterations = 0

            def __iter__(self) -> Any:
                type(self).iterations += 1
                if type(self).iterations == 3:
                    raise RuntimeError("filter broke")
                return super().__iter__()

        flaky = _FailsOnThirdIteration(self.jobs)
        self.stub.saved_jobs = flaky
        save_spy = mock.Mock(side_effect=AssertionError("save_jobs must not run"))
        self.stub.save_jobs = save_spy

        with fake_dialog_widgets() as widgets, \
                mock.patch.object(app, "messagebox") as messagebox:
            messagebox.askyesno.return_value = True
            dialog, listbox, command = self.open_dialog(widgets)
            self.select(listbox, "good")
            escaped = self.press(command)

        self.assertIsNone(escaped, f"exception escaped the Load callback: {escaped!r}")
        self.assertEqual(_FailsOnThirdIteration.iterations, 3, "filter step was not reached")
        save_spy.assert_not_called()
        self.assertIs(self.stub.saved_jobs, flaky)
        self.assertEqual(list(flaky), self.before)
        self.assert_no_success(messagebox, dialog)
        messagebox.showerror.assert_called_once()
        args, kwargs = messagebox.showerror.call_args
        self.assertIs(kwargs.get("parent"), dialog)
        self.assertIn("filter broke", args[1])
        self.assert_jobs_file_unchanged()

    def test_non_dict_in_current_jobs_does_not_escape_before_confirm(self) -> None:
        """A broken element already in saved_jobs: the confirm count skips it."""
        self.write_preset("good", {"created": "2026-01-03", "jobs": [ok_job("g1")]})
        self.jobs.append(None)
        self.job_objects.append(None)
        self.before.append(None)

        with fake_dialog_widgets() as widgets, \
                mock.patch.object(app, "messagebox") as messagebox:
            messagebox.askyesno.return_value = False
            dialog, listbox, command = self.open_dialog(widgets)
            self.select(listbox, "good")
            escaped = self.press(command)

        self.assertIsNone(escaped, f"exception escaped the Load callback: {escaped!r}")
        messagebox.askyesno.assert_called_once()
        self.assertIn("replace current 3 jobs", messagebox.askyesno.call_args.args[1])
        self.assert_saved_jobs_unchanged()
        self.assert_no_success(messagebox, dialog)
        self.assert_jobs_file_unchanged()


# --------------------------------------------------------------------------
# R9-AC-9 .. R9-AC-12: normal presets behave as before
# --------------------------------------------------------------------------
class NormalPresetTests(LoadPresetBase):

    def test_good_preset_loads_like_before(self) -> None:
        """R9-AC-9."""
        preset_jobs = [
            {
                "name": "  ชื่องาน  ",
                "query": "\nSELECT * FROM ตาราง\n",
                "database": "DB1",
                "run_index": 2,
                "excel_parameters": {"WHERE x": ["AUTO_WHERE", "'1'"]},
            },
            {
                "name": "second",
                "query": "SELECT 2",
                "profile": "UAT",
                "db_type": "Oracle",
                "nested": {"a": [1, {"b": None}]},
            },
        ]
        preset_path = self.write_preset("good", {"created": "2026-01-03",
                                                 "jobs": preset_jobs})
        preset_bytes = read_bytes(preset_path)
        u_job = self.job_objects[1]

        with fake_dialog_widgets() as widgets, \
                mock.patch.object(app, "messagebox") as messagebox:
            messagebox.askyesno.return_value = True
            dialog, listbox, command = self.open_dialog(widgets)
            self.select(listbox, "good")
            escaped = self.press(command)

        self.assertIsNone(escaped)
        messagebox.askyesno.assert_called_once_with(
            "Confirm Load",
            "Load preset 'good'?\n\nThis will replace current 3 jobs with 2 jobs from preset.",
            parent=dialog,
        )
        expected = [self.before[1]] + [dict(copy.deepcopy(job), profile="PROD")
                                       for job in preset_jobs]
        self.assertEqual(self.stub.saved_jobs, expected)
        self.assertIs(self.stub.saved_jobs[0], u_job)
        self.assertEqual(read_json(self.stub.jobs_file), self.stub.saved_jobs)
        self.stub.update_jobs_list.assert_called_once_with()
        inserted = self.stub.results_text.inserted
        self.assertTrue(any("Loaded preset: good" in line for line in inserted))
        self.assertTrue(any("Jobs loaded: 2" in line for line in inserted))
        messagebox.showinfo.assert_called_once()
        self.assertIs(messagebox.showinfo.call_args.kwargs.get("parent"), dialog)
        self.assertTrue(dialog.destroyed)
        messagebox.showerror.assert_not_called()
        self.assertEqual(read_bytes(preset_path), preset_bytes)

    def test_answer_no_changes_nothing(self) -> None:
        """R9-AC-10."""
        self.write_preset("good", {"created": "2026-01-03", "jobs": [ok_job("g")]})
        with fake_dialog_widgets() as widgets, \
                mock.patch.object(app, "messagebox") as messagebox, \
                mock.patch.object(self.stub, "save_jobs",
                                  wraps=self.stub.save_jobs) as save_spy:
            messagebox.askyesno.return_value = False
            dialog, listbox, command = self.open_dialog(widgets)
            self.select(listbox, "good")
            self.assertIsNone(self.press(command))

        messagebox.askyesno.assert_called_once()
        save_spy.assert_not_called()
        self.assert_saved_jobs_unchanged()
        self.assert_no_success(messagebox, dialog)
        messagebox.showerror.assert_not_called()
        messagebox.showwarning.assert_not_called()
        self.assert_jobs_file_unchanged()
        self.assertEqual(self.loaded_objects[0]["jobs"], [ok_job("g")])

    def test_empty_or_missing_jobs_key_keeps_old_behaviour(self) -> None:
        """R9-AC-11."""
        cases = [
            ("empty", {"created": "2026-01-05", "jobs": []}),
            ("nokey", {"created": "2026-01-05"}),
        ]
        for name, preset in cases:
            with self.subTest(preset=name):
                self.doCleanups()
                self.setUp()
                self.write_preset(name, preset)
                with fake_dialog_widgets() as widgets, \
                        mock.patch.object(app, "messagebox") as messagebox:
                    messagebox.askyesno.return_value = True
                    dialog, listbox, command = self.open_dialog(widgets)
                    self.assertEqual(listbox.items, [f"{name} (0 jobs) - 2026-01-05"])
                    self.select(listbox, name)
                    self.assertIsNone(self.press(command))

                messagebox.askyesno.assert_called_once()
                self.assertIn("with 0 jobs", messagebox.askyesno.call_args.args[1])
                self.assertIn("replace current 3 jobs", messagebox.askyesno.call_args.args[1])
                self.assertEqual(self.stub.saved_jobs, [self.before[1]])
                self.assertEqual(read_json(self.stub.jobs_file), [self.before[1]])
                messagebox.showinfo.assert_called_once()
                messagebox.showerror.assert_not_called()
                self.assertTrue(dialog.destroyed)

    def test_no_selection_warns_without_checking(self) -> None:
        """R9-AC-12 (a broken preset is present but not selected)."""
        self.write_preset("broken", {"created": "2026-01-02", "jobs": [None]})
        with fake_dialog_widgets() as widgets, \
                mock.patch.object(app, "messagebox") as messagebox, \
                mock.patch.object(self.stub, "save_jobs",
                                  wraps=self.stub.save_jobs) as save_spy:
            messagebox.askyesno.return_value = True
            dialog, listbox, command = self.open_dialog(widgets)
            listbox.curselection = lambda: ()
            self.assertIsNone(self.press(command))

        messagebox.showwarning.assert_called_once_with(
            "Warning", "Please select a preset", parent=dialog)
        messagebox.showerror.assert_not_called()
        messagebox.askyesno.assert_not_called()
        self.stub.profile_combo.get.assert_not_called()
        save_spy.assert_not_called()
        self.assert_saved_jobs_unchanged()
        self.assert_no_success(messagebox, dialog)
        self.assert_jobs_file_unchanged()


# --------------------------------------------------------------------------
# R9-AC-13 / R9-AC-14: save failure rollback (R5-H-3) unchanged
# --------------------------------------------------------------------------
class SaveFailureRollbackTests(LoadPresetBase):

    def _load_good(self) -> Tuple[Any, Any, str, bytes]:
        preset_path = self.write_preset("good", {"created": "2026-01-03",
                                                 "jobs": [ok_job("g1"), ok_job("g2")]})
        preset_bytes = read_bytes(preset_path)
        with fake_dialog_widgets() as widgets, \
                mock.patch.object(app, "messagebox") as messagebox:
            messagebox.askyesno.return_value = True
            dialog, listbox, command = self.open_dialog(widgets)
            self.select(listbox, "good")
            escaped = self.press(command)
        self.assertIsNone(escaped, f"exception escaped the Load callback: {escaped!r}")
        return messagebox, dialog, preset_path, preset_bytes

    def test_save_jobs_false_restores_without_extra_error(self) -> None:
        """R9-AC-13."""
        def mutate_then_fail() -> bool:
            self.stub.saved_jobs[0]["meta"] = {"changed": True}
            self.stub.saved_jobs.append({"name": "temporary"})
            return False

        self.stub.save_jobs = mock.Mock(side_effect=mutate_then_fail)
        messagebox, dialog, preset_path, preset_bytes = self._load_good()

        self.stub.save_jobs.assert_called_once_with()
        self.assert_saved_jobs_unchanged()
        self.assert_no_success(messagebox, dialog)
        messagebox.showerror.assert_not_called()
        self.assertEqual(read_bytes(preset_path), preset_bytes)
        self.assert_jobs_file_unchanged()

    def test_real_save_jobs_write_error(self) -> None:
        """R9-AC-14 (a): write_json_atomic raises OSError."""
        with mock.patch.object(app, "write_json_atomic", side_effect=OSError("disk full")):
            messagebox, dialog, preset_path, preset_bytes = self._load_good()

        self.assert_saved_jobs_unchanged()
        self.assert_jobs_file_unchanged()
        self.assert_no_success(messagebox, dialog)
        messagebox.showerror.assert_called_once()
        self.assertTrue(messagebox.showerror.call_args.args[1].startswith("Failed to save jobs:"))
        self.assertEqual(read_bytes(preset_path), preset_bytes)

    def test_real_save_jobs_blocked(self) -> None:
        """R9-AC-14 (b): _jobs_save_blocked = True."""
        self.stub._jobs_save_blocked = True
        messagebox, dialog, preset_path, preset_bytes = self._load_good()

        self.assert_saved_jobs_unchanged()
        self.assert_jobs_file_unchanged()
        self.assert_no_success(messagebox, dialog)
        messagebox.showerror.assert_called_once()
        self.assertIn("could not be read when the app started",
                      messagebox.showerror.call_args.args[1])
        self.assertEqual(read_bytes(preset_path), preset_bytes)


if __name__ == "__main__":
    unittest.main()
