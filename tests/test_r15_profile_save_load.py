"""Round 15 / R15-T7 (BH-8, BH-9): Save Profile overwrite confirmation,
reserved name guard, and load_profile_data clearing missing text fields.

Covers R15-AC-21..25. Uses stubs only: no real Tk window, no real files.
"""
import copy
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import database_connect_gui as app  # noqa: E402

GUI = app.DatabaseConnectorGUI
KEY = app.PROFILE_STORED_PASSWORD_KEY
STORED = "dpapi:QUJD"
RESERVED_MSG = "ชื่อนี้สงวนไว้ กรุณาใช้ชื่ออื่น"


class _FakeEntry:
    def __init__(self, value: str = "") -> None:
        self.value = value

    def get(self, *_args) -> str:
        return self.value

    def set(self, value) -> None:
        self.value = value

    def delete(self, *_args) -> None:
        self.value = ""

    def insert(self, _index, value) -> None:
        self.value = str(value) + self.value


class _FakeLog:
    def __init__(self) -> None:
        self.log = []

    def insert(self, _index, value) -> None:
        self.log.append(value)

    def delete(self, *_args) -> None:
        pass

    def see(self, *_args) -> None:
        pass


def _profiles():
    return {
        "A": {"db_type": "PostgreSQL", "db_user": "ua", "db_password": "pa",
              "db_host": "ha", "db_port": "5432", "db_name": "da",
              "sql_query": "SELECT a"},
        "B": {"db_type": "MySQL", "db_user": "ub", "db_password": "pb",
              "db_host": "hb", "db_port": "3306", "db_name": "db",
              "sql_query": "SELECT b"},
    }


# ---------------------------------------------------------------- save dialog


class SaveProfileDialogTests(unittest.TestCase):
    def make_stub(self, current: str, profiles=None):
        stub = mock.MagicMock()
        stub._block_if_busy.return_value = False
        stub.saved_profiles = profiles if profiles is not None else _profiles()
        stub.save_profiles = mock.Mock(return_value=True)
        stub.profile_combo.get.return_value = current
        stub.db_type = _FakeEntry("Oracle")
        stub.db_user = _FakeEntry("new_user")
        stub.db_password = _FakeEntry("new_pw")
        stub.db_host = _FakeEntry("new_host")
        stub.db_port = _FakeEntry("1521")
        stub.db_name = _FakeEntry("new_db")
        stub.sql_context = _FakeEntry("SELECT new")
        stub.results_text = _FakeLog()
        return stub

    def run_save(self, stub, typed_name: str, answer: bool = True):
        """Open dialog, type name, click Save. Returns (dialog, askyesno, showwarning)."""
        commands = {}

        def button(*_args, **kwargs):
            if "command" in kwargs:
                commands[kwargs.get("text")] = kwargs["command"]
            return mock.MagicMock()

        fake_tk = mock.MagicMock()
        dialog = mock.MagicMock(name="dialog")
        fake_tk.Toplevel.return_value = dialog
        fake_ttk = mock.MagicMock()
        fake_ttk.Button.side_effect = button
        fake_ttk.Entry.return_value.get.return_value = typed_name
        with mock.patch.object(app, "tk", fake_tk), \
                mock.patch.object(app, "ttk", fake_ttk), \
                mock.patch.object(app.messagebox, "showinfo"), \
                mock.patch.object(app.messagebox, "showerror"), \
                mock.patch.object(app.messagebox, "showwarning") as showwarning, \
                mock.patch.object(app.messagebox, "askyesno",
                                  return_value=answer) as askyesno:
            GUI.save_profile_dialog(stub)
            commands["Save"]()
        return dialog, askyesno, showwarning

    # R15-AC-21 ------------------------------------------------------------
    def test_ac21_other_existing_name_no_keeps_everything(self):
        stub = self.make_stub("A")
        before = copy.deepcopy(stub.saved_profiles)
        dialog, askyesno, _ = self.run_save(stub, "B", answer=False)
        askyesno.assert_called_once()
        self.assertIn("B", askyesno.call_args[0][1])
        self.assertIs(askyesno.call_args.kwargs.get("parent"), dialog)
        self.assertEqual(stub.saved_profiles, before)
        stub.save_profiles.assert_not_called()
        stub.save_last_used_profile.assert_not_called()
        dialog.destroy.assert_not_called()

    def test_ac21_other_existing_name_yes_overwrites(self):
        stub = self.make_stub("A")
        dialog, askyesno, _ = self.run_save(stub, "B", answer=True)
        askyesno.assert_called_once()
        b = stub.saved_profiles["B"]
        self.assertEqual(b["db_user"], "new_user")
        self.assertEqual(b["db_password"], "new_pw")
        self.assertEqual(b["db_host"], "new_host")
        self.assertEqual(b["db_type"], "Oracle")
        self.assertEqual(stub.saved_profiles["A"], _profiles()["A"])
        stub.save_profiles.assert_called_once()
        stub.save_last_used_profile.assert_called_once_with("B")
        dialog.destroy.assert_called_once()

    def test_ac21_typed_name_with_spaces_still_asks(self):
        stub = self.make_stub("A")
        before = copy.deepcopy(stub.saved_profiles)
        dialog, askyesno, _ = self.run_save(stub, "  B  ", answer=False)
        askyesno.assert_called_once()
        self.assertEqual(stub.saved_profiles, before)
        stub.save_profiles.assert_not_called()
        dialog.destroy.assert_not_called()

    def test_edge_empty_current_profile_existing_name_asks(self):
        stub = self.make_stub("")
        before = copy.deepcopy(stub.saved_profiles)
        dialog, askyesno, _ = self.run_save(stub, "A", answer=False)
        askyesno.assert_called_once()
        self.assertIn("A", askyesno.call_args[0][1])
        self.assertEqual(stub.saved_profiles, before)
        stub.save_profiles.assert_not_called()
        dialog.destroy.assert_not_called()

    # R15-AC-22 ------------------------------------------------------------
    def test_ac22_current_name_no_prompt_and_saves(self):
        stub = self.make_stub("A")
        dialog, askyesno, _ = self.run_save(stub, "A")
        askyesno.assert_not_called()
        self.assertEqual(stub.saved_profiles["A"]["db_user"], "new_user")
        stub.save_profiles.assert_called_once()
        dialog.destroy.assert_called_once()

    def test_ac22_new_name_no_prompt_and_saves(self):
        stub = self.make_stub("A")
        dialog, askyesno, _ = self.run_save(stub, "C")
        askyesno.assert_not_called()
        self.assertIn("C", stub.saved_profiles)
        self.assertEqual(stub.saved_profiles["A"], _profiles()["A"])
        self.assertEqual(stub.saved_profiles["B"], _profiles()["B"])
        stub.save_profiles.assert_called_once()
        stub.save_last_used_profile.assert_called_once_with("C")
        dialog.destroy.assert_called_once()

    def test_ac22_new_name_when_no_profiles_no_prompt(self):
        stub = self.make_stub("", profiles={})
        dialog, askyesno, _ = self.run_save(stub, "C")
        askyesno.assert_not_called()
        self.assertIn("C", stub.saved_profiles)
        stub.save_profiles.assert_called_once()

    def test_ac22_current_name_keeps_stored_password_when_empty(self):
        profiles = _profiles()
        profiles["A"]["db_password"] = ""
        profiles["A"][KEY] = STORED
        stub = self.make_stub("A", profiles)
        stub.db_password = _FakeEntry("")
        _, askyesno, _ = self.run_save(stub, "A")
        askyesno.assert_not_called()
        self.assertEqual(stub.saved_profiles["A"]["db_password"], "")
        self.assertEqual(stub.saved_profiles["A"][KEY], STORED)
        stub.save_profiles.assert_called_once()

    def test_ac22_current_name_new_password_drops_stored(self):
        profiles = _profiles()
        profiles["A"][KEY] = STORED
        stub = self.make_stub("A", profiles)
        _, askyesno, _ = self.run_save(stub, "A")
        askyesno.assert_not_called()
        self.assertEqual(stub.saved_profiles["A"]["db_password"], "new_pw")
        self.assertNotIn(KEY, stub.saved_profiles["A"])

    def test_ac22_new_name_does_not_inherit_stored_password(self):
        profiles = _profiles()
        profiles["A"][KEY] = STORED
        stub = self.make_stub("A", profiles)
        stub.db_password = _FakeEntry("")
        self.run_save(stub, "C")
        self.assertNotIn(KEY, stub.saved_profiles["C"])

    def test_ac22_port_cleaned_on_save(self):
        stub = self.make_stub("A")
        stub.db_port = _FakeEntry("3802:3802")
        self.run_save(stub, "A")
        self.assertEqual(stub.saved_profiles["A"]["db_port"], "3802")

    # R15-AC-23 ------------------------------------------------------------
    def test_ac23_reserved_name_blocked(self):
        for typed in ("last_used_profile", "  last_used_profile  "):
            for current in ("A", ""):
                with self.subTest(typed=typed, current=current):
                    stub = self.make_stub(current)
                    before = copy.deepcopy(stub.saved_profiles)
                    dialog, askyesno, showwarning = self.run_save(stub, typed)
                    showwarning.assert_called_once_with(
                        "Warning", RESERVED_MSG, parent=dialog
                    )
                    askyesno.assert_not_called()
                    self.assertEqual(stub.saved_profiles, before)
                    self.assertNotIn("last_used_profile", stub.saved_profiles)
                    stub.save_profiles.assert_not_called()
                    stub.save_last_used_profile.assert_not_called()
                    dialog.destroy.assert_not_called()

    def test_ac23_same_message_as_new_profile(self):
        # New Profile dialog uses exactly this text for the reserved name
        import inspect
        src = inspect.getsource(GUI)
        self.assertGreaterEqual(
            src.count(f'messagebox.showwarning("Warning", "{RESERVED_MSG}", parent=dialog)'),
            2,
        )

    def test_reserved_name_case_sensitive_is_allowed(self):
        stub = self.make_stub("A")
        _, askyesno, showwarning = self.run_save(stub, "Last_Used_Profile")
        showwarning.assert_not_called()
        askyesno.assert_not_called()
        self.assertIn("Last_Used_Profile", stub.saved_profiles)

    def test_empty_name_warns_and_does_not_save(self):
        for typed in ("", "   "):
            with self.subTest(typed=typed):
                stub = self.make_stub("A")
                before = copy.deepcopy(stub.saved_profiles)
                dialog, askyesno, showwarning = self.run_save(stub, typed)
                showwarning.assert_called_once()
                askyesno.assert_not_called()
                self.assertEqual(stub.saved_profiles, before)
                stub.save_profiles.assert_not_called()
                dialog.destroy.assert_not_called()

    def test_save_failure_after_yes_rolls_back(self):
        stub = self.make_stub("A")
        stub.save_profiles.return_value = False
        before = copy.deepcopy(stub.saved_profiles)
        dialog, askyesno, _ = self.run_save(stub, "B", answer=True)
        askyesno.assert_called_once()
        self.assertEqual(stub.saved_profiles, before)
        dialog.destroy.assert_not_called()


# --------------------------------------------------------- load_profile_data


class LoadProfileDataTests(unittest.TestCase):
    def make_stub(self, profiles):
        stub = mock.MagicMock()
        stub.saved_profiles = profiles
        stub.LEGACY_DEFAULT_SQL_QUERIES = GUI.LEGACY_DEFAULT_SQL_QUERIES
        stub.DEFAULT_SQL_QUERY = GUI.DEFAULT_SQL_QUERY
        stub.db_type = _FakeEntry("Oracle")
        stub.db_user = _FakeEntry("prev_user")
        stub.db_password = _FakeEntry("prev_pw")
        stub.db_host = _FakeEntry("prev_host")
        stub.db_port = _FakeEntry("9999")
        stub.db_name = _FakeEntry("prev_db")
        stub.sql_context = _FakeEntry("SELECT previous")
        stub.results_text = _FakeLog()
        return stub

    def load(self, stub, name):
        with mock.patch.object(app.messagebox, "showerror") as showerror:
            GUI.load_profile_data(stub, name)
        showerror.assert_not_called()

    def fields(self, stub):
        return {
            "db_type": stub.db_type.get(), "db_user": stub.db_user.get(),
            "db_password": stub.db_password.get(), "db_host": stub.db_host.get(),
            "db_port": stub.db_port.get(), "db_name": stub.db_name.get(),
            "sql": stub.sql_context.get(),
        }

    # R15-AC-24 ------------------------------------------------------------
    def test_ac24_missing_text_keys_cleared_after_full_profile(self):
        profiles = {
            "A": {"db_type": "Oracle", "db_user": "ua", "db_password": "pa",
                  "db_host": "ha", "db_port": "1521", "db_name": "da",
                  "sql_query": "SELECT a"},
            "B": {"db_type": "PostgreSQL", "db_host": "hb"},
        }
        stub = self.make_stub(profiles)
        self.load(stub, "A")
        f = self.fields(stub)
        self.assertEqual(
            (f["db_user"], f["db_password"], f["db_host"], f["db_port"], f["db_name"]),
            ("ua", "pa", "ha", "1521", "da"),
        )
        self.load(stub, "B")
        f = self.fields(stub)
        self.assertEqual(f["db_user"], "")
        self.assertEqual(f["db_password"], "")
        self.assertEqual(f["db_port"], "")
        self.assertEqual(f["db_name"], "")
        self.assertEqual(f["db_host"], "hb")
        self.assertEqual(f["db_type"], "PostgreSQL")
        self.assertEqual(stub._active_profile, "B")

    def test_ac24_empty_profile_clears_all_text_fields(self):
        stub = self.make_stub({"E": {}})
        self.load(stub, "E")
        f = self.fields(stub)
        for key in ("db_user", "db_password", "db_host", "db_port", "db_name"):
            with self.subTest(key=key):
                self.assertEqual(f[key], "")

    # R15-AC-25 ------------------------------------------------------------
    def test_ac25_missing_db_type_and_sql_keep_previous(self):
        stub = self.make_stub({"N": {"db_user": "un"}})
        self.load(stub, "N")
        f = self.fields(stub)
        self.assertEqual(f["db_type"], "Oracle")
        self.assertEqual(f["sql"], "SELECT previous")
        self.assertEqual(f["db_user"], "un")

    def test_ac25_full_profile_same_as_before_with_port_cleanup(self):
        stub = self.make_stub({
            "F": {"db_type": "MySQL", "db_user": "uf", "db_password": "pf",
                  "db_host": "hf", "db_port": "3802:3802", "db_name": "df",
                  "sql_query": "  SELECT f  "},
        })
        self.load(stub, "F")
        self.assertEqual(self.fields(stub), {
            "db_type": "MySQL", "db_user": "uf", "db_password": "pf",
            "db_host": "hf", "db_port": "3802", "db_name": "df", "sql": "SELECT f",
        })

    def test_ac25_legacy_or_empty_sql_uses_default(self):
        legacy = next(iter(GUI.LEGACY_DEFAULT_SQL_QUERIES))
        for sql in ("", "   ", legacy):
            with self.subTest(sql=sql):
                stub = self.make_stub({"S": {"sql_query": sql}})
                self.load(stub, "S")
                self.assertEqual(stub.sql_context.get(), GUI.DEFAULT_SQL_QUERY)

    def test_port_int_value_loaded_as_text(self):
        stub = self.make_stub({"I": {"db_port": 1521}})
        self.load(stub, "I")
        self.assertEqual(stub.db_port.get(), "1521")

    def test_unknown_profile_shows_error(self):
        stub = self.make_stub({})
        with mock.patch.object(app.messagebox, "showerror") as showerror:
            GUI.load_profile_data(stub, "missing")
        showerror.assert_called_once()
        self.assertEqual(stub.db_user.get(), "prev_user")


if __name__ == "__main__":
    unittest.main()
