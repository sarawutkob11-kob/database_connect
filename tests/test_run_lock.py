"""T7: UI lock while a run is in progress (AC-31; AC-12 logic part).

Fake widgets follow design section 4: cget("state"), config(state=...),
winfo_exists(); fake menu: entryconfig(index, **kw). No Tk window.
"""

import os
import sys
import threading
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import database_connect_gui as app  # noqa: E402

GUI = app.DatabaseConnectorGUI


class _TclObjLike:
    def __init__(self, value: str) -> None:
        self._value = value

    def __str__(self) -> str:
        return self._value

    def __eq__(self, other) -> bool:
        return other is self

    __hash__ = object.__hash__


class FakeWidget:
    def __init__(self, name: str, state="normal", *, alive=True, tcl_error=False,
                 tcl_obj=False, text="") -> None:
        self.name = name
        self.state = state
        self.alive = alive
        self.tcl_error = tcl_error
        self.tcl_obj = tcl_obj
        self.text = text
        self.config_calls: list = []

    def cget(self, key):
        if self.tcl_error:
            raise app.tk.TclError(f"invalid command name {self.name}")
        if key == "text":
            return self.text
        return _TclObjLike(self.state) if self.tcl_obj else self.state

    def __getitem__(self, key):
        return self.cget(key)

    def config(self, **kw):
        if self.tcl_error:
            raise app.tk.TclError(f"invalid command name {self.name}")
        self.config_calls.append(kw)
        self.state = kw.get("state", self.state)

    configure = config

    def winfo_exists(self):
        if self.tcl_error:
            raise app.tk.TclError("gone")
        return 1 if self.alive else 0

    def __repr__(self) -> str:
        return f"<FakeWidget {self.name} {self.state}>"


class FakeMenu:
    def __init__(self) -> None:
        self.entry_calls: list = []

    def entryconfig(self, index, **kw):
        self.entry_calls.append((index, kw))


def make_stub(*, engine=True, n_job_buttons=2):
    stub = GUI.__new__(GUI)
    stub.engine = mock.Mock(name="engine") if engine else None
    stub.connect_btn = FakeWidget("connect")
    stub.profile_combo = FakeWidget("combo", "readonly")
    stub.execute_btn = FakeWidget("execute", "disabled")
    stub.inspect_btn = FakeWidget("inspect", "disabled")
    stub.run_all_btn = FakeWidget("run_all")
    stub.export_excel_btn = FakeWidget("export")
    stub._profile_action_buttons = [FakeWidget(n) for n in ("import", "save", "new")]
    stub._profile_menu = FakeMenu()
    stub._job_run_buttons = [FakeWidget(f"run{i}") for i in range(n_job_buttons)]
    return stub


def fixed_widgets(stub):
    return [stub.connect_btn, stub.profile_combo, stub.execute_btn, stub.inspect_btn,
            stub.run_all_btn, stub.export_excel_btn]


def all_widgets(stub):
    return (fixed_widgets(stub) + list(stub._profile_action_buttons)
            + list(stub._job_run_buttons) + [b for b, _ in getattr(stub, "_run_lock_extra", [])])


class ApplyRunLockTests(unittest.TestCase):
    """AC-31"""

    def test_busy_then_idle_with_engine(self):
        stub = make_stub()
        group_run = FakeWidget("group_run")
        group_export = FakeWidget("group_export")
        stub._register_run_lock_button(group_run, lambda: "normal")
        stub._register_run_lock_button(group_export, lambda: "normal")

        stub._apply_run_lock(True)
        for w in all_widgets(stub):
            self.assertEqual(w.state, "disabled", w)
        self.assertEqual(stub._profile_menu.entry_calls, [(0, {"state": "disabled"})])

        stub._apply_run_lock(False)
        for w in all_widgets(stub):
            expected = "readonly" if w is stub.profile_combo else "normal"
            self.assertEqual(w.state, expected, w)
        self.assertEqual(stub._profile_menu.entry_calls[-1], (0, {"state": "normal"}))
        self.assertEqual(len(stub._profile_menu.entry_calls), 2)
        # combobox must never be set to plain "normal" (would allow typing)
        self.assertNotIn({"state": "normal"}, stub.profile_combo.config_calls)

    def test_idle_without_engine_keeps_run_and_tables_disabled(self):
        stub = make_stub(engine=False)
        stub._apply_run_lock(True)
        stub._apply_run_lock(False)
        self.assertEqual(stub.execute_btn.state, "disabled")
        self.assertEqual(stub.inspect_btn.state, "disabled")
        for w in (stub.connect_btn, stub.run_all_btn, stub.export_excel_btn,
                  *stub._profile_action_buttons, *stub._job_run_buttons):
            self.assertEqual(w.state, "normal", w)
        self.assertEqual(stub.profile_combo.state, "readonly")

    def test_idle_without_engine_from_enabled_state_disables_run(self):
        stub = make_stub(engine=False)
        stub.execute_btn.state = "normal"
        stub.inspect_btn.state = "normal"
        stub._apply_run_lock(False)
        self.assertEqual(stub.execute_btn.state, "disabled")
        self.assertEqual(stub.inspect_btn.state, "disabled")

    def test_engine_attribute_missing_counts_as_not_connected(self):
        stub = make_stub()
        del stub.engine
        stub.execute_btn.state = "normal"
        stub._apply_run_lock(False)
        self.assertEqual(stub.execute_btn.state, "disabled")

    def test_idle_state_disabled_is_respected(self):
        stub = make_stub()
        empty_group = FakeWidget("group_run", "disabled")
        stub._register_run_lock_button(empty_group, lambda: "disabled")
        stub._apply_run_lock(False)
        self.assertEqual(empty_group.state, "disabled")
        self.assertEqual(empty_group.config_calls, [])
        stub._apply_run_lock(True)
        stub._apply_run_lock(False)
        self.assertEqual(empty_group.state, "disabled")

    def test_idle_state_is_evaluated_each_time(self):
        stub = make_stub()
        has_scripts = {"value": False}
        btn = FakeWidget("group_run", "disabled")
        stub._register_run_lock_button(
            btn, lambda: "normal" if has_scripts["value"] else "disabled"
        )
        stub._apply_run_lock(False)
        self.assertEqual(btn.state, "disabled")
        has_scripts["value"] = True
        stub._apply_run_lock(False)
        self.assertEqual(btn.state, "normal")

    def test_idle_state_not_called_while_busy(self):
        stub = make_stub()
        idle = mock.Mock(return_value="normal")
        stub._register_run_lock_button(FakeWidget("g"), idle)
        stub._apply_run_lock(True)
        idle.assert_not_called()

    def test_repeated_poll_does_not_reconfigure(self):
        stub = make_stub()
        stub._register_run_lock_button(FakeWidget("g"), lambda: "normal")
        stub._apply_run_lock(True)
        counts = [len(w.config_calls) for w in all_widgets(stub)]
        stub._apply_run_lock(True)
        self.assertEqual([len(w.config_calls) for w in all_widgets(stub)], counts)
        stub._apply_run_lock(False)
        counts = [len(w.config_calls) for w in all_widgets(stub)]
        stub._apply_run_lock(False)
        self.assertEqual([len(w.config_calls) for w in all_widgets(stub)], counts)

    def test_tcl_obj_states_are_compared_as_text(self):
        stub = make_stub()
        for w in all_widgets(stub):
            w.tcl_obj = True
        stub._apply_run_lock(False)  # already in idle states (execute/inspect differ)
        self.assertEqual(stub.connect_btn.config_calls, [])
        self.assertEqual(stub.profile_combo.config_calls, [])
        self.assertEqual(stub.run_all_btn.config_calls, [])
        self.assertEqual(stub.execute_btn.config_calls, [{"state": "normal"}])


class DeadWidgetTests(unittest.TestCase):
    def test_destroyed_job_buttons_are_dropped(self):
        stub = make_stub(n_job_buttons=0)
        alive = FakeWidget("alive")
        gone = FakeWidget("gone", alive=False)
        broken = FakeWidget("broken", tcl_error=True)
        stub._job_run_buttons = [alive, gone, broken]
        stub._apply_run_lock(True)
        self.assertEqual(stub._job_run_buttons, [alive])
        self.assertEqual(alive.state, "disabled")
        self.assertEqual(gone.config_calls, [])

    def test_destroyed_extra_buttons_are_dropped(self):
        stub = make_stub()
        alive = FakeWidget("alive")
        gone = FakeWidget("gone", alive=False)
        broken = FakeWidget("broken", tcl_error=True)
        idle_gone = mock.Mock(return_value="normal")
        for btn, idle in ((alive, lambda: "normal"), (gone, idle_gone), (broken, idle_gone)):
            stub._register_run_lock_button(btn, idle)
        stub._apply_run_lock(False)
        self.assertEqual([b for b, _ in stub._run_lock_extra], [alive])
        idle_gone.assert_not_called()

    def test_exists_but_config_raises_is_dropped(self):
        class HalfDead(FakeWidget):
            def winfo_exists(self):
                return 1

        stub = make_stub(n_job_buttons=0)
        half = HalfDead("half", tcl_error=True)
        stub._job_run_buttons = [half]
        stub._register_run_lock_button(HalfDead("half2", tcl_error=True), lambda: "normal")
        stub._apply_run_lock(True)
        self.assertEqual(stub._job_run_buttons, [])
        self.assertEqual(stub._run_lock_extra, [])

    def test_broken_fixed_widget_or_menu_does_not_raise(self):
        stub = make_stub()
        stub.connect_btn = FakeWidget("connect", tcl_error=True)

        class BadMenu:
            def entryconfig(self, *_a, **_k):
                raise app.tk.TclError("menu gone")

        stub._profile_menu = BadMenu()
        stub._apply_run_lock(True)  # must not raise
        self.assertEqual(stub.run_all_btn.state, "disabled")


class BareStubTests(unittest.TestCase):
    def test_no_optional_attributes(self):
        stub = GUI.__new__(GUI)
        stub._apply_run_lock(True)
        stub._apply_run_lock(False)
        self.assertEqual(stub._job_run_buttons, [])
        self.assertEqual(stub._run_lock_extra, [])

    def test_register_creates_list(self):
        stub = GUI.__new__(GUI)
        btn = FakeWidget("b")
        stub._register_run_lock_button(btn, lambda: "normal")
        self.assertEqual(len(stub._run_lock_extra), 1)
        self.assertIs(stub._run_lock_extra[0][0], btn)
        self.assertEqual(btn.config_calls, [])  # registering alone changes nothing


class SetWidgetStateTests(unittest.TestCase):
    def test_same_state_no_config(self):
        for tcl_obj in (False, True):
            with self.subTest(tcl_obj=tcl_obj):
                w = FakeWidget("w", "disabled", tcl_obj=tcl_obj)
                self.assertIs(GUI._set_widget_state(w, "disabled"), True)
                self.assertEqual(w.config_calls, [])

    def test_different_state_configures_once(self):
        for tcl_obj in (False, True):
            with self.subTest(tcl_obj=tcl_obj):
                w = FakeWidget("w", "normal", tcl_obj=tcl_obj)
                self.assertIs(GUI._set_widget_state(w, "disabled"), True)
                self.assertEqual(w.config_calls, [{"state": "disabled"}])

    def test_tcl_error_returns_false(self):
        self.assertIs(GUI._set_widget_state(FakeWidget("w", tcl_error=True), "normal"), False)

    def test_widget_alive(self):
        self.assertIs(GUI._widget_alive(FakeWidget("a")), True)
        self.assertIs(GUI._widget_alive(FakeWidget("b", alive=False)), False)
        self.assertIs(GUI._widget_alive(FakeWidget("c", tcl_error=True)), False)


class RefreshStopButtonsTests(unittest.TestCase):
    def make_poll_stub(self, *, busy: bool):
        stub = GUI.__new__(GUI)
        stub._active_db_lock = threading.Lock()
        stub._active_db_connections = {}
        stub._batch_running = False
        stub._running_job_ids = {1} if busy else set()
        stub.execute_btn = FakeWidget("execute", text="▶  Run")
        stub.export_excel_btn = FakeWidget("export", text="Export")
        stub.inspect_btn = FakeWidget("inspect", text="Tables")
        stub._stop_buttons = []
        stub.root = mock.Mock(name="root")
        return stub

    def test_calls_apply_run_lock_with_is_busy_and_reschedules(self):
        for busy in (True, False):
            with self.subTest(busy=busy):
                stub = self.make_poll_stub(busy=busy)
                with mock.patch.object(GUI, "_apply_run_lock") as lock:
                    stub._refresh_stop_buttons()
                lock.assert_called_once_with(busy)
                stub.root.after.assert_called_once_with(300, stub._refresh_stop_buttons)

    def test_real_lock_applied_during_poll(self):
        stub = self.make_poll_stub(busy=True)
        stub.connect_btn = FakeWidget("connect")
        job_btn = FakeWidget("run1")
        stub._job_run_buttons = [job_btn]
        stub._refresh_stop_buttons()
        self.assertEqual(stub.connect_btn.state, "disabled")
        self.assertEqual(job_btn.state, "disabled")
        self.assertEqual(stub.execute_btn.state, "disabled")
        stub.root.after.assert_called_once()

        stub._running_job_ids.clear()
        stub.engine = mock.Mock()
        stub._refresh_stop_buttons()
        self.assertEqual(stub.connect_btn.state, "normal")
        self.assertEqual(job_btn.state, "normal")
        self.assertEqual(stub.execute_btn.state, "normal")
        self.assertEqual(stub.root.after.call_count, 2)


class LockPollRobustnessTests(unittest.TestCase):
    """Fix from the T7 finding: a failing lock step must never stop the poll."""

    def test_idle_state_tcl_error_drops_entry_without_raising(self):
        stub = make_stub()
        good = FakeWidget("good", "disabled")
        bad = FakeWidget("bad", "disabled")

        def broken_idle():
            raise app.tk.TclError('invalid command name ".groups_box"')

        stub._register_run_lock_button(good, lambda: "normal")
        stub._register_run_lock_button(bad, broken_idle)
        stub._apply_run_lock(False)  # must not raise
        self.assertEqual([b for b, _ in stub._run_lock_extra], [good])
        self.assertEqual(good.state, "normal")
        self.assertEqual(bad.config_calls, [])
        # the rest of the lock was still applied
        self.assertEqual(stub.connect_btn.state, "normal")
        self.assertEqual(stub.profile_combo.state, "readonly")

    def test_idle_state_not_called_while_busy_so_not_dropped(self):
        stub = make_stub()
        btn = FakeWidget("g")

        def broken_idle():
            raise app.tk.TclError("gone")

        stub._register_run_lock_button(btn, broken_idle)
        stub._apply_run_lock(True)
        self.assertEqual([b for b, _ in stub._run_lock_extra], [btn])
        self.assertEqual(btn.state, "disabled")

    def test_set_extra_lock_state_direct(self):
        stub = make_stub()
        btn = FakeWidget("b", "normal")

        def broken_idle():
            raise app.tk.TclError("gone")

        self.assertIs(stub._set_extra_lock_state(btn, broken_idle, False), False)
        self.assertIs(stub._set_extra_lock_state(btn, broken_idle, True), True)
        self.assertEqual(btn.state, "disabled")
        self.assertIs(stub._set_extra_lock_state(btn, lambda: "normal", False), True)
        self.assertEqual(btn.state, "normal")
        self.assertIs(
            stub._set_extra_lock_state(FakeWidget("x", tcl_error=True), lambda: "normal", False),
            False,
        )

    def _poll_stub(self):
        return RefreshStopButtonsTests.make_poll_stub(None, busy=False)

    def test_poll_reschedules_when_apply_run_lock_raises(self):
        for exc in (app.tk.TclError("gone"), RuntimeError("boom"), AttributeError("x")):
            with self.subTest(exc=type(exc).__name__):
                stub = self._poll_stub()
                with mock.patch.object(GUI, "_apply_run_lock", side_effect=exc), \
                        mock.patch("builtins.print"):
                    stub._refresh_stop_buttons()  # must not raise
                stub.root.after.assert_called_once_with(300, stub._refresh_stop_buttons)

    def test_poll_reschedules_when_is_busy_raises(self):
        for exc in (app.tk.TclError("gone"), ValueError("boom")):
            with self.subTest(exc=type(exc).__name__):
                stub = self._poll_stub()
                with mock.patch.object(GUI, "_is_busy", side_effect=exc), \
                        mock.patch.object(GUI, "_apply_run_lock") as lock, \
                        mock.patch("builtins.print"):
                    stub._refresh_stop_buttons()
                lock.assert_not_called()
                stub.root.after.assert_called_once_with(300, stub._refresh_stop_buttons)

    def test_poll_with_broken_idle_state_keeps_running(self):
        stub = self._poll_stub()
        stub.connect_btn = FakeWidget("connect", "disabled")

        def broken_idle():
            raise app.tk.TclError("gone")

        stub._register_run_lock_button(FakeWidget("g"), broken_idle)
        stub._refresh_stop_buttons()
        self.assertEqual(stub._run_lock_extra, [])
        self.assertEqual(stub.connect_btn.state, "normal")
        stub.root.after.assert_called_once_with(300, stub._refresh_stop_buttons)


class WiringSourceTests(unittest.TestCase):
    """The lock is wired to the widgets named in design section 4."""

    @classmethod
    def setUpClass(cls):
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "database_connect_gui.py")
        with open(path, encoding="utf-8") as fh:
            cls.source = fh.read()

    def test_profile_menu_delete_is_entry_zero(self):
        self.assertIn("self._profile_menu = more_menu", self.source)
        self.assertRegex(self.source, r"more_menu = tk\.Menu\([^)]*tearoff=0")
        idx = self.source.index("more_menu = tk.Menu(")
        first_add = self.source.index("more_menu.add", idx)
        self.assertTrue(
            self.source.startswith('more_menu.add_command(label="Delete profile"', first_add)
        )

    def test_profile_action_buttons_exclude_export(self):
        self.assertIn('if _text != "Export":\n                self._profile_action_buttons.append(_b)',
                      self.source)

    def test_job_run_buttons_collected(self):
        self.assertIn("self._job_run_buttons = []", self.source)
        self.assertIn('if kind == "run":\n                    self._job_run_buttons.append(b)',
                      self.source)

    def test_script_group_buttons_registered(self):
        self.assertIn("self._register_run_lock_button(btn, group_run_idle_state)", self.source)
        self.assertIn("set_enabled(btn, has_scripts and not self._is_busy())", self.source)


if __name__ == "__main__":
    unittest.main()
