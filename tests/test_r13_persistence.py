"""R13-T4: retry delays pinned, write_json_atomic failure paths, Load Preset
with non-dict elements in saved_jobs.

R13-AC-13, R13-AC-14, R13-AC-16 (Round 13). Every file lives in a
TemporaryDirectory; messagebox and Tk widgets are fakes.
"""

import copy
import json
import os
import sys
import tempfile
import unittest
from typing import Any, Dict, List
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import database_connect_gui as app  # noqa: E402
from test_bugfix_h3 import fake_dialog_widgets, make_job_stub  # noqa: E402

_REAL_REPLACE = os.replace


# R13-AC-13
class RetryDelaysTests(unittest.TestCase):
    def test_ac13_export_replace_retry_delays_pinned(self):
        self.assertEqual(app.EXPORT_REPLACE_RETRY_DELAYS, (0.2, 0.5, 1.0))
        self.assertLessEqual(sum(app.EXPORT_REPLACE_RETRY_DELAYS), 2.0)


# R13-AC-14
class WriteJsonAtomicTests(unittest.TestCase):
    ORIGINAL = '[{"name": "เดิม", "query": "SELECT 1"}]'.encode("utf-8")

    def _setup_file(self, folder: str) -> str:
        path = os.path.join(folder, "saved_jobs.json")
        with open(path, "wb") as handle:
            handle.write(self.ORIGINAL)
        return path

    def _assert_untouched(self, folder: str, path: str, replace_spy: mock.Mock) -> None:
        with open(path, "rb") as handle:
            self.assertEqual(handle.read(), self.ORIGINAL)
        self.assertFalse(os.path.exists(f"{path}.tmp"))
        self.assertEqual(sorted(os.listdir(folder)), ["saved_jobs.json"])
        replace_spy.assert_not_called()

    def test_ac14_json_dump_type_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._setup_file(tmp)
            with mock.patch.object(app.os, "replace", wraps=_REAL_REPLACE) as spy:
                with self.assertRaises(TypeError):
                    app.write_json_atomic(path, [{"bad": object()}])
            self._assert_untouched(tmp, path, spy)

    def test_ac14_fsync_errors_propagate_same_instance(self):
        for label, error in (("OSError", OSError(5, "fsync failed")),
                             ("KeyboardInterrupt", KeyboardInterrupt())):
            with self.subTest(error=label), tempfile.TemporaryDirectory() as tmp:
                path = self._setup_file(tmp)
                with mock.patch.object(app.os, "replace", wraps=_REAL_REPLACE) as spy, \
                        mock.patch.object(app.os, "fsync", side_effect=error):
                    with self.assertRaises(type(error)) as caught:
                        app.write_json_atomic(path, [{"name": "ใหม่"}])
                self.assertIs(caught.exception, error)
                self._assert_untouched(tmp, path, spy)

    def test_ac14_json_dump_keyboard_interrupt(self):
        error = KeyboardInterrupt()
        with tempfile.TemporaryDirectory() as tmp:
            path = self._setup_file(tmp)
            with mock.patch.object(app.os, "replace", wraps=_REAL_REPLACE) as spy, \
                    mock.patch.object(app.json, "dump", side_effect=error):
                with self.assertRaises(KeyboardInterrupt) as caught:
                    app.write_json_atomic(path, [1])
            self.assertIs(caught.exception, error)
            self._assert_untouched(tmp, path, spy)

    def test_success_still_replaces(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._setup_file(tmp)
            app.write_json_atomic(path, [{"name": "ใหม่"}])
            with open(path, encoding="utf-8") as handle:
                self.assertEqual(json.load(handle), [{"name": "ใหม่"}])
            self.assertEqual(os.listdir(tmp), ["saved_jobs.json"])


# R13-AC-16
class LoadPresetNonDictTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.folder = self._tmp.name
        self.job_p1 = {"name": "a", "query": "SELECT 1", "profile": "P1"}
        self.job_p2 = {"name": "b", "query": "SELECT 2", "profile": "P2"}
        self.jobs: List[Any] = [self.job_p1, None, "junk", self.job_p2]
        self.stub = make_job_stub(self.jobs)
        self.stub.jobs_file = os.path.join(self.folder, "saved_jobs.json")
        self.stub._jobs_save_blocked = False
        self.stub.profile_combo = mock.Mock()
        self.stub.profile_combo.get.return_value = "P1"
        self.preset_job: Dict[str, Any] = {"name": "from-preset", "query": "SELECT 3"}
        with open(os.path.join(self.folder, "preset_one.json"), "w", encoding="utf-8") as h:
            json.dump({"created": "2026-11-23T10:00:00", "jobs": [self.preset_job]}, h)

    def test_ac16_non_dict_elements_kept_in_order(self):
        with fake_dialog_widgets() as widgets, \
                mock.patch.object(app, "messagebox") as mb:
            mb.askyesno.return_value = True
            self.stub.load_preset_dialog()
            listbox = widgets["listboxes"][0]
            self.assertEqual(len(listbox.items), 1, listbox.items)
            listbox.curselection = lambda: (0,)
            load = next(b for b in widgets["tk_buttons"] if b.command is not None)
            try:
                load.command()
            except Exception as error:  # noqa: BLE001 - Tk would swallow it
                self.fail(f"exception escaped the Load callback: {error!r}")

        mb.showerror.assert_not_called()
        mb.askyesno.assert_called_once()
        self.assertIn("replace current 1 jobs", mb.askyesno.call_args.args[1])
        expected = [None, "junk", self.job_p2,
                    dict(self.preset_job, profile="P1")]
        self.assertEqual(self.stub.saved_jobs, expected)
        self.assertIs(self.stub.saved_jobs[2], self.job_p2)
        with open(self.stub.jobs_file, encoding="utf-8") as handle:
            self.assertEqual(json.load(handle), expected)
        self.assertFalse(os.path.exists(self.stub.jobs_file + ".tmp"))
        self.stub.update_jobs_list.assert_called_once_with()
        mb.showinfo.assert_called_once()
        self.assertEqual(self.job_p1, {"name": "a", "query": "SELECT 1", "profile": "P1"})

    def test_ac16_answer_no_changes_nothing(self):
        before = copy.deepcopy(self.jobs)
        with fake_dialog_widgets() as widgets, \
                mock.patch.object(app, "messagebox") as mb:
            mb.askyesno.return_value = False
            self.stub.load_preset_dialog()
            widgets["listboxes"][0].curselection = lambda: (0,)
            next(b for b in widgets["tk_buttons"] if b.command is not None).command()
        self.assertIn("replace current 1 jobs", mb.askyesno.call_args.args[1])
        self.assertIs(self.stub.saved_jobs, self.jobs)
        self.assertEqual(self.stub.saved_jobs, before)
        self.assertFalse(os.path.exists(self.stub.jobs_file))
        mb.showerror.assert_not_called()


if __name__ == "__main__":
    unittest.main()
