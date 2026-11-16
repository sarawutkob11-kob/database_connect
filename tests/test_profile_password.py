import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import database_connect_gui as app  # noqa: E402

STORED = "dpapi:QUJD"
KEY = app.PROFILE_STORED_PASSWORD_KEY


def _dpapi_fails():
    return mock.patch.object(app, "_dpapi_transform", side_effect=Exception("bad key"))


class ProfilePasswordTests(unittest.TestCase):
    def test_unprotect_password_returns_empty_when_dpapi_fails(self):
        with _dpapi_fails():
            self.assertEqual(app.unprotect_password(STORED), "")

    def test_plain_text_password_returned_as_is(self):
        self.assertEqual(app.unprotect_password("plain"), "plain")

    def test_decrypt_profile_keeps_ciphertext_out_of_password_field(self):
        profile = {"db_password": STORED}
        with _dpapi_fails():
            app.decrypt_profile_password(profile)
        self.assertEqual(profile["db_password"], "")
        self.assertEqual(profile[KEY], STORED)

    def test_save_writes_back_kept_ciphertext_when_password_empty(self):
        disk = app.profile_password_for_disk({"db_password": "", KEY: STORED})
        self.assertEqual(disk["db_password"], STORED)
        self.assertNotIn(KEY, disk)

    def test_save_uses_new_password_when_entered(self):
        with mock.patch.object(app, "protect_password", side_effect=lambda p: "enc:" + p):
            disk = app.profile_password_for_disk({"db_password": "new", KEY: STORED})
        self.assertEqual(disk["db_password"], "enc:new")
        self.assertNotIn(KEY, disk)

    def test_round_trip_does_not_wipe_undecryptable_password(self):
        profile = {"db_password": STORED}
        with _dpapi_fails():
            app.decrypt_profile_password(profile)
        self.assertEqual(app.profile_password_for_disk(profile)["db_password"], STORED)

    def test_decrypt_profile_without_password_adds_nothing(self):
        for profile in ({}, {"db_password": ""}, {"db_password": None}):
            with self.subTest(profile=profile):
                app.decrypt_profile_password(profile)
                self.assertNotIn(KEY, profile)

    def test_decrypt_profile_plain_password_kept(self):
        profile = {"db_password": "plain", KEY: "dpapi:OLD"}
        app.decrypt_profile_password(profile)
        self.assertEqual(profile["db_password"], "plain")
        self.assertNotIn(KEY, profile)

    def test_decrypt_profile_success_does_not_keep_ciphertext(self):
        with mock.patch.object(app, "_dpapi_transform", return_value=b"secret"):
            profile = {"db_password": STORED}
            app.decrypt_profile_password(profile)
        self.assertEqual(profile["db_password"], "secret")
        self.assertNotIn(KEY, profile)

    def test_profile_password_for_disk_does_not_mutate_input(self):
        profile = {"db_password": "", KEY: STORED}
        app.profile_password_for_disk(profile)
        self.assertEqual(profile, {"db_password": "", KEY: STORED})

    def test_profile_password_for_disk_empty_without_kept(self):
        disk = app.profile_password_for_disk({"db_password": ""})
        self.assertEqual(disk["db_password"], "")
        self.assertNotIn(KEY, disk)


# ----------------------------------------------------------------------
# GUI-level paths (stubbed, no Tk window): Import / Export / save / connect
# ----------------------------------------------------------------------
GUI = app.DatabaseConnectorGUI


class _FakeText:
    def __init__(self):
        self.log = []

    def insert(self, _index, value):
        self.log.append(value)

    def delete(self, *_args):
        pass

    def see(self, *_args):
        pass


class _FakeEntry:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value

    def delete(self, *_args):
        self.value = ""

    def insert(self, _index, value):
        self.value = str(value) + self.value


def _fake_protect(plain):
    if not plain or str(plain).startswith(app._DPAPI_PREFIX):
        return plain
    return app._DPAPI_PREFIX + "ENC(" + plain + ")"


class _TempDirCase(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.dir = folder.name


class ImportProfilesPasswordTests(_TempDirCase):
    """Import must never put the undecryptable 'dpapi:...' into the profile password."""

    def make_stub(self, saved_profiles):
        stub = mock.MagicMock()
        stub.saved_profiles = saved_profiles
        stub.results_text = _FakeText()
        return stub

    def run_import(self, stub, imported_profiles, merge=True):
        """Open the import preview with mocked Tk and press "Import Profiles"."""
        commands = {}

        def button(*_args, **kwargs):
            if "command" in kwargs and "text" in kwargs:
                commands[kwargs["text"]] = kwargs["command"]
            return mock.MagicMock()

        fake_tk = mock.MagicMock()
        fake_tk.Button.side_effect = button
        fake_tk.BooleanVar.return_value.get.return_value = merge
        with mock.patch.object(app, "tk", fake_tk), \
                mock.patch.object(app, "ttk", mock.MagicMock()), \
                mock.patch.object(app.messagebox, "showinfo"), \
                mock.patch.object(app.messagebox, "askyesno", return_value=True), \
                mock.patch.object(app.messagebox, "showerror") as showerror:
            GUI._show_import_preview_dialog(
                stub, imported_profiles, os.path.join(self.dir, "x.json"), "Unknown", 1
            )
            import_command = next(c for t, c in commands.items() if "Import Profiles" in t)
            with _dpapi_fails():
                import_command()
        showerror.assert_not_called()
        stub.save_profiles.assert_called_once()

    def test_dpapi_failure_keeps_existing_working_password(self):
        """The reported bug: result was 'dpapi:...' instead of 'MyWorkingPass'."""
        stub = self.make_stub({"P": {"db_type": "PostgreSQL", "db_password": "MyWorkingPass"}})
        imported = {"P": {"db_type": "PostgreSQL", "db_host": "h", "db_password": STORED}}
        self.run_import(stub, imported)
        profile = stub.saved_profiles["P"]
        self.assertEqual(profile["db_password"], "MyWorkingPass")
        self.assertNotIn(KEY, profile)
        self.assertEqual(profile["db_host"], "h")

    def test_dpapi_failure_keeps_password_in_replace_mode(self):
        stub = self.make_stub({"P": {"db_password": "MyWorkingPass"}})
        self.run_import(stub, {"P": {"db_password": STORED}}, merge=False)
        self.assertEqual(stub.saved_profiles["P"]["db_password"], "MyWorkingPass")

    def test_dpapi_failure_for_new_profile_gives_empty_password(self):
        stub = self.make_stub({})
        self.run_import(stub, {"New": {"db_password": STORED}})
        profile = stub.saved_profiles["New"]
        self.assertEqual(profile["db_password"], "")
        self.assertNotIn(STORED, json.dumps(profile))

    def test_dpapi_failure_keeps_existing_kept_ciphertext(self):
        mine = "dpapi:MINE"
        stub = self.make_stub({"P": {"db_password": "", KEY: mine}})
        self.run_import(stub, {"P": {"db_password": STORED}})
        profile = stub.saved_profiles["P"]
        self.assertEqual(profile["db_password"], "")
        self.assertEqual(profile[KEY], mine)
        self.assertEqual(app.profile_password_for_disk(profile)["db_password"], mine)

    def test_plain_password_in_file_replaces_existing(self):
        stub = self.make_stub({"P": {"db_password": "Old", KEY: "dpapi:MINE"}})
        self.run_import(stub, {"P": {"db_password": "NewPlain"}})
        profile = stub.saved_profiles["P"]
        self.assertEqual(profile["db_password"], "NewPlain")
        self.assertNotIn(KEY, profile)

    def test_file_with_internal_key_is_not_trusted(self):
        """A crafted export holding _stored_db_password must not inject it."""
        stub = self.make_stub({})
        self.run_import(stub, {"P": {"db_password": "", KEY: "dpapi:INJECTED"}})
        self.assertNotIn(KEY, stub.saved_profiles["P"])

    def test_file_without_password_keeps_existing(self):
        stub = self.make_stub({"P": {"db_password": "MyWorkingPass"}})
        self.run_import(stub, {"P": {"db_password": ""}})
        self.assertEqual(stub.saved_profiles["P"]["db_password"], "MyWorkingPass")


class ExportProfilesPasswordTests(_TempDirCase):
    def export(self, saved_profiles, include_passwords):
        out = os.path.join(self.dir, "export.json")
        stub = mock.MagicMock()
        stub.saved_profiles = saved_profiles
        stub.results_text = _FakeText()
        with mock.patch.object(app.filedialog, "asksaveasfilename", return_value=out), \
                mock.patch.object(app.messagebox, "askyesnocancel", return_value=include_passwords), \
                mock.patch.object(app.messagebox, "showinfo"), \
                mock.patch.object(app.messagebox, "showerror") as showerror:
            GUI.export_profiles_dialog(stub)
        showerror.assert_not_called()
        with open(out, "r", encoding="utf-8") as f:
            raw = f.read()
        return raw, json.loads(raw)

    def profiles(self):
        return {
            "Broken": {"db_type": "Oracle", "db_password": "", KEY: STORED},
            "Good": {"db_type": "MySQL", "db_password": "plainpw"},
        }

    def test_include_passwords_has_no_ciphertext_or_internal_key(self):
        saved = self.profiles()
        raw, data = self.export(saved, True)
        self.assertNotIn(STORED, raw)
        self.assertNotIn("dpapi:", raw)
        self.assertNotIn(KEY, raw)
        self.assertEqual(data["profiles"]["Broken"]["db_password"], "")
        self.assertEqual(data["profiles"]["Good"]["db_password"], "plainpw")
        # In-memory profile keeps its ciphertext for the next save
        self.assertEqual(saved["Broken"][KEY], STORED)

    def test_without_passwords_has_no_ciphertext_or_internal_key(self):
        raw, data = self.export(self.profiles(), False)
        self.assertNotIn("dpapi:", raw)
        self.assertNotIn(KEY, raw)
        self.assertNotIn("plainpw", raw)


class ProfilesForDiskTests(_TempDirCase):
    def make_stub(self, saved_profiles):
        stub = mock.MagicMock()
        stub.saved_profiles = saved_profiles
        stub.config_file = os.path.join(self.dir, "db_profiles.json")
        stub.get_last_used_profile.return_value = None
        stub._profiles_save_refused.return_value = False
        stub._profiles_for_disk.side_effect = lambda *a: GUI._profiles_for_disk(stub, *a)
        return stub

    def test_profiles_for_disk_never_contains_internal_key(self):
        stub = self.make_stub({
            "Broken": {"db_password": "", KEY: STORED},
            "Good": {"db_password": "pw", KEY: "dpapi:OLD"},
            "Empty": {"db_password": ""},
        })
        with mock.patch.object(app, "protect_password", side_effect=_fake_protect):
            data = GUI._profiles_for_disk(stub)
        for name in ("Broken", "Good", "Empty"):
            self.assertNotIn(KEY, data[name])
        self.assertEqual(data["Broken"]["db_password"], STORED)
        self.assertEqual(data["Good"]["db_password"], "dpapi:ENC(pw)")
        self.assertEqual(data["Empty"]["db_password"], "")
        # saved_profiles itself is not changed
        self.assertEqual(stub.saved_profiles["Broken"][KEY], STORED)

    def test_save_and_load_round_trip_on_disk(self):
        stub = self.make_stub({"Broken": {"db_password": "", KEY: STORED}})
        with mock.patch.object(app, "protect_password", side_effect=_fake_protect):
            GUI.save_profiles(stub)
        with open(stub.config_file, "r", encoding="utf-8") as f:
            raw = f.read()
        self.assertNotIn(KEY, raw)
        self.assertEqual(json.loads(raw)["Broken"]["db_password"], STORED)

        with _dpapi_fails():
            loaded = GUI.load_profiles(stub)
        self.assertEqual(loaded["Broken"]["db_password"], "")
        self.assertEqual(loaded["Broken"][KEY], STORED)


class UndecryptableProfileNeverConnectsTests(_TempDirCase):
    def load(self):
        config = os.path.join(self.dir, "db_profiles.json")
        with open(config, "w", encoding="utf-8") as f:
            json.dump({
                "P": {"db_type": "PostgreSQL", "db_user": "u", "db_password": STORED,
                      "db_host": "h", "db_port": "5432", "db_name": "d"},
                "last_used_profile": "P",
            }, f)
        stub = mock.MagicMock()
        stub.config_file = config
        with _dpapi_fails():
            stub.saved_profiles = GUI.load_profiles(stub)
        return stub

    def test_load_profiles_never_puts_ciphertext_in_password(self):
        stub = self.load()
        self.assertEqual(stub.saved_profiles["P"]["db_password"], "")
        self.assertEqual(stub.saved_profiles["P"][KEY], STORED)

    def test_password_field_never_gets_ciphertext(self):
        stub = self.load()
        stub.db_password = _FakeEntry("previous")
        GUI.load_profile_data(stub, "P")
        self.assertEqual(stub.db_password.get(), "")

    def test_connect_never_uses_ciphertext(self):
        stub = self.load()
        stub.db_password = _FakeEntry("")
        GUI.load_profile_data(stub, "P")
        stub._block_if_busy.return_value = False
        stub.db_type = _FakeEntry("PostgreSQL")
        stub.db_user = _FakeEntry("u")
        stub.db_host = _FakeEntry("h")
        stub.db_port = _FakeEntry("5432")
        stub.db_name = _FakeEntry("d")
        stub.results_text = _FakeText()
        with mock.patch.object(app.messagebox, "showerror") as showerror, \
                mock.patch.object(app, "create_engine", create=True) as create_engine:
            GUI.connect_database(stub)
        showerror.assert_called_once()  # empty password -> "fill in all fields"
        stub.get_connection_string.assert_not_called()
        create_engine.assert_not_called()
        self.assertNotIn(STORED, repr(stub.mock_calls))

    def test_save_profile_dialog_keeps_ciphertext_when_password_empty(self):
        stub = self.load()
        stub._block_if_busy.return_value = False
        stub.db_password = _FakeEntry("")
        stub.db_port = _FakeEntry("5432")
        stub.profile_combo.get.return_value = "P"
        commands = {}

        def button(*_args, **kwargs):
            if "command" in kwargs:
                commands[kwargs.get("text")] = kwargs["command"]
            return mock.MagicMock()

        fake_ttk = mock.MagicMock()
        fake_ttk.Button.side_effect = button
        fake_ttk.Entry.return_value.get.return_value = "P"
        with mock.patch.object(app, "tk", mock.MagicMock()), \
                mock.patch.object(app, "ttk", fake_ttk), \
                mock.patch.object(app.messagebox, "showinfo"), \
                mock.patch.object(app.messagebox, "showwarning"):
            GUI.save_profile_dialog(stub)
            commands["Save"]()
        profile = stub.saved_profiles["P"]
        self.assertEqual(profile["db_password"], "")
        self.assertEqual(profile[KEY], STORED)
        stub.save_profiles.assert_called_once()

    def test_save_profile_dialog_new_password_drops_ciphertext(self):
        stub = self.load()
        stub._block_if_busy.return_value = False
        stub.db_password = _FakeEntry("typed")
        stub.db_port = _FakeEntry("5432")
        commands = {}

        def button(*_args, **kwargs):
            if "command" in kwargs:
                commands[kwargs.get("text")] = kwargs["command"]
            return mock.MagicMock()

        fake_ttk = mock.MagicMock()
        fake_ttk.Button.side_effect = button
        fake_ttk.Entry.return_value.get.return_value = "P"
        with mock.patch.object(app, "tk", mock.MagicMock()), \
                mock.patch.object(app, "ttk", fake_ttk), \
                mock.patch.object(app.messagebox, "showinfo"), \
                mock.patch.object(app.messagebox, "showwarning"):
            GUI.save_profile_dialog(stub)
            commands["Save"]()
        profile = stub.saved_profiles["P"]
        self.assertEqual(profile["db_password"], "typed")
        self.assertNotIn(KEY, profile)


if __name__ == "__main__":
    unittest.main()
