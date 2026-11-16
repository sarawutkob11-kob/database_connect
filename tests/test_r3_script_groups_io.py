"""R3-T1: pure Script Groups import/export helpers (R3-AC-1 .. R3-AC-7).

No Tk, no real files: helpers are called directly with in-memory data.
"""

import copy
import json
import os
import re
import sys
import tempfile
import unittest
from unittest import mock

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import database_connect_gui as app  # noqa: E402

NOW = "2026-01-01 00:00:00"
STAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$")


def grp(name, profile="P1", scripts=None, created="2025-05-05 10:00:00", **extra):
    g = {
        "name": name,
        "profile": profile,
        "created": created,
        "scripts": scripts if scripts is not None else [{"name": "s", "query": "SELECT 1"}],
    }
    g.update(extra)
    return g


def names_of(groups, profile):
    return [g["name"] for g in groups if g.get("profile") == profile]


# ----------------------------------------------------------------------
# R3-AC-1 build_script_groups_export
# ----------------------------------------------------------------------
class TestBuildExport(unittest.TestCase):
    def setUp(self):
        self.groups = [
            grp(
                "G1",
                scripts=[
                    {"name": "a", "query": "SELECT 1", "target": "T", "_tmp": 1, "run_index": 3, "_x": "y"},
                    {"name": "b", "query": "SELECT 2"},
                ],
                imported="2025-06-06 00:00:00",
                extra_key="drop me",
            ),
            grp("G2", scripts=[{"name": "c", "query": "SELECT 3", "run_index": 0}], created=None),
        ]
        self.before = copy.deepcopy(self.groups)

    def test_constants(self):
        self.assertEqual(app.SCRIPT_GROUPS_FILE_TYPE, "script_groups")
        self.assertEqual(app.SCRIPT_GROUPS_FILE_VERSION, 1)

    def test_payload_shape(self):
        payload = app.build_script_groups_export(self.groups, "P1", now=NOW)
        self.assertEqual(payload["type"], "script_groups")
        self.assertEqual(payload["version"], 1)
        self.assertEqual(payload["exported"], NOW)
        self.assertEqual(payload["profile"], "P1")
        self.assertEqual(set(payload), {"type", "version", "exported", "profile", "groups"})
        self.assertEqual(len(payload["groups"]), 2)
        for g in payload["groups"]:
            self.assertEqual(set(g), {"name", "created", "scripts"})
        self.assertEqual([g["name"] for g in payload["groups"]], ["G1", "G2"])
        self.assertEqual(payload["groups"][0]["created"], "2025-05-05 10:00:00")
        self.assertIsNone(payload["groups"][1]["created"])

    def test_runtime_keys_stripped_other_keys_kept(self):
        payload = app.build_script_groups_export(self.groups, "P1", now=NOW)
        s0 = payload["groups"][0]["scripts"][0]
        self.assertEqual(s0, {"name": "a", "query": "SELECT 1", "target": "T"})
        self.assertEqual(payload["groups"][0]["scripts"][1], {"name": "b", "query": "SELECT 2"})
        self.assertEqual(payload["groups"][1]["scripts"], [{"name": "c", "query": "SELECT 3"}])

    def test_input_not_mutated(self):
        app.build_script_groups_export(self.groups, "P1", now=NOW)
        self.assertEqual(self.groups, self.before)

    def test_payload_is_json_serialisable(self):
        payload = app.build_script_groups_export(self.groups, "P1", now=NOW)
        self.assertEqual(json.loads(json.dumps(payload)), payload)

    def test_exported_format_when_now_omitted(self):
        payload = app.build_script_groups_export(self.groups, "P1")
        self.assertRegex(payload["exported"], STAMP_RE)

    def test_now_helper_format(self):
        self.assertRegex(app._script_groups_now(), STAMP_RE)

    def test_empty_groups(self):
        payload = app.build_script_groups_export([], "P1", now=NOW)
        self.assertEqual(payload["groups"], [])

    def test_group_without_scripts_key(self):
        payload = app.build_script_groups_export([{"name": "G"}], "P1", now=NOW)
        self.assertEqual(payload["groups"], [{"name": "G", "created": None, "scripts": []}])

    def test_round_trip_through_parse(self):
        payload = app.build_script_groups_export(self.groups, "P1", now=NOW)
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "x.json")
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(payload, fh)
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
        parsed = app.parse_script_groups_import(data)
        self.assertEqual([g["name"] for g in parsed], ["G1", "G2"])


class TestExportFilename(unittest.TestCase):
    STAMP = "20260101_000000"

    def test_plain(self):
        self.assertEqual(
            app.script_groups_export_filename("P1", self.STAMP),
            "script_groups_P1_20260101_000000.json",
        )

    def test_unsafe_characters_replaced(self):
        self.assertEqual(
            app.script_groups_export_filename('a\\b/c:d*e?f"g<h>i|j', self.STAMP),
            "script_groups_a_b_c_d_e_f_g_h_i_j_20260101_000000.json",
        )

    def test_strip_whitespace(self):
        self.assertEqual(
            app.script_groups_export_filename("  G 1  ", self.STAMP),
            "script_groups_G 1_20260101_000000.json",
        )

    def test_empty_none_blank_fallback(self):
        for label in ("", None, "   "):
            with self.subTest(label=label):
                self.assertEqual(
                    app.script_groups_export_filename(label, self.STAMP),
                    "script_groups_groups_20260101_000000.json",
                )

    def test_only_unsafe_chars_not_empty(self):
        # '/' becomes '_' so the result is not empty -> no fallback
        self.assertEqual(
            app.script_groups_export_filename("/", self.STAMP),
            "script_groups___20260101_000000.json",
        )


# ----------------------------------------------------------------------
# R3-AC-2 / R3-AC-3 parse_script_groups_import
# ----------------------------------------------------------------------
class TestParseImport(unittest.TestCase):
    def valid_groups(self):
        return [
            {"name": "G1", "created": "c", "scripts": [{"query": "SELECT 1"}]},
            {"name": "G2", "scripts": []},
        ]

    def test_dict_and_list_equivalent(self):
        from_dict = app.parse_script_groups_import({"type": "script_groups", "groups": self.valid_groups()})
        from_list = app.parse_script_groups_import(self.valid_groups())
        self.assertEqual(from_dict, from_list)
        self.assertEqual([g["name"] for g in from_dict], ["G1", "G2"])

    def test_invalid_groups_filtered(self):
        data = [
            "not a dict",
            42,
            None,
            {"scripts": [{"query": "SELECT 1"}]},          # no name
            {"name": "", "scripts": []},                    # empty name
            {"name": "   ", "scripts": []},                 # blank name
            {"name": 5, "scripts": []},                     # non-str name
            {"name": "BadScripts", "scripts": "SELECT 1"},  # scripts not list
            {"name": "BadScripts2", "scripts": {"query": "x"}},
            {"name": "BadScripts3", "scripts": None},
            {"name": "Keep", "scripts": [{"query": "SELECT 1"}]},
            {"name": "NoScriptsKey"},                        # missing key is kept
        ]
        out = app.parse_script_groups_import(data)
        self.assertEqual([g["name"] for g in out], ["Keep", "NoScriptsKey"])

    def test_returns_same_objects(self):
        data = self.valid_groups()
        out = app.parse_script_groups_import(data)
        self.assertIs(out[0], data[0])

    def test_empty_list_is_ok(self):
        self.assertEqual(app.parse_script_groups_import([]), [])
        self.assertEqual(app.parse_script_groups_import({"groups": []}), [])

    def test_all_filtered_gives_empty(self):
        self.assertEqual(app.parse_script_groups_import([{"name": ""}, "x"]), [])

    def test_no_groups_list_raises(self):
        for data in ({}, {"groups": None}, {"groups": "x"}, {"groups": {"name": "G"}},
                     "text", 3, None, {"version": 1}):
            with self.subTest(data=data):
                with self.assertRaises(ValueError) as cm:
                    app.parse_script_groups_import(data)
                self.assertIn("groups", str(cm.exception))

    def test_script_without_query_raises_with_group_name(self):
        cases = [
            [{"name": "MyGroup", "scripts": [{"name": "s"}]}],
            [{"name": "MyGroup", "scripts": [{"query": ""}]}],
            [{"name": "MyGroup", "scripts": [{"query": None}]}],
            [{"name": "MyGroup", "scripts": ["SELECT 1"]}],          # non-dict script
            [{"name": "MyGroup", "scripts": [{"query": "SELECT 1"}, None]}],
            {"groups": [{"name": "OK", "scripts": [{"query": "x"}]},
                        {"name": "MyGroup", "scripts": [{}]}]},
        ]
        for data in cases:
            with self.subTest(data=data):
                with self.assertRaises(ValueError) as cm:
                    app.parse_script_groups_import(data)
                self.assertIn("MyGroup", str(cm.exception))
                self.assertIn("SQL", str(cm.exception))

    def test_dropped_group_bad_script_not_checked(self):
        # a filtered-out group (scripts not list) must not trigger the SQL error
        out = app.parse_script_groups_import([{"name": "", "scripts": [{}]},
                                              {"name": "G", "scripts": [{"query": "x"}]}])
        self.assertEqual([g["name"] for g in out], ["G"])


# ----------------------------------------------------------------------
# clashes
# ----------------------------------------------------------------------
class TestNameClashes(unittest.TestCase):
    def test_case_insensitive_file_spelling_profile_scoped(self):
        sg = [grp("G1", "P1"), grp("Other", "P2"), grp("g3", "P1")]
        incoming = [{"name": "g1"}, {"name": "G2"}, {"name": "OTHER"}, {"name": "G3"}]
        self.assertEqual(app.script_group_name_clashes(sg, incoming, "P1"), ["g1", "G3"])
        self.assertEqual(app.script_group_name_clashes(sg, incoming, "P2"), ["OTHER"])
        self.assertEqual(app.script_group_name_clashes(sg, incoming, "P3"), [])

    def test_empty(self):
        self.assertEqual(app.script_group_name_clashes([], [{"name": "G"}], "P1"), [])
        self.assertEqual(app.script_group_name_clashes([grp("G")], [], "P1"), [])


# ----------------------------------------------------------------------
# R3-AC-4 .. R3-AC-7 merge_imported_script_groups
# ----------------------------------------------------------------------
class TestMerge(unittest.TestCase):
    def setUp(self):
        self.p1_g1 = grp("G1", "P1", scripts=[{"query": "OLD"}])
        self.p2_g1 = grp("G1", "P2", scripts=[{"query": "P2"}])
        self.sg = [self.p1_g1, self.p2_g1]
        self.p2_before = copy.deepcopy(self.p2_g1)
        self.incoming = [
            {"name": "g1", "created": "2024-01-01 00:00:00", "scripts": [{"query": "NEW1"}]},
            {"name": "G2", "scripts": [{"query": "NEW2"}]},
        ]

    # R3-AC-4
    def test_replace_true(self):
        last = app.merge_imported_script_groups(self.sg, self.incoming, "P1", True, now=NOW)
        self.assertEqual(last, "G2")
        p1 = [g for g in self.sg if g["profile"] == "P1"]
        self.assertEqual([g["name"].lower() for g in p1].count("g1"), 1)
        self.assertNotIn(self.p1_g1, self.sg)
        self.assertEqual(names_of(self.sg, "P1"), ["g1", "G2"])  # keeps file spelling
        g1 = next(g for g in p1 if g["name"] == "g1")
        g2 = next(g for g in p1 if g["name"] == "G2")
        self.assertEqual(g1["scripts"], [{"query": "NEW1"}])
        self.assertEqual(g1["profile"], "P1")
        self.assertEqual(g1["created"], "2024-01-01 00:00:00")  # from file
        self.assertEqual(g1["imported"], NOW)
        self.assertEqual(g2["created"], NOW)  # missing -> now
        self.assertEqual(g2["imported"], NOW)
        self.assertEqual(set(g1), {"name", "profile", "created", "imported", "scripts"})
        # P2 untouched (same object, same content)
        self.assertIn(self.p2_g1, self.sg)
        self.assertEqual(self.p2_g1, self.p2_before)
        self.assertEqual(len(self.sg), 3)

    def test_created_empty_string_falls_back_to_now(self):
        app.merge_imported_script_groups(self.sg, [{"name": "X", "created": ""}], "P1", True, now=NOW)
        self.assertEqual(self.sg[-1]["created"], NOW)

    def test_now_omitted_created_equals_imported(self):
        app.merge_imported_script_groups(self.sg, [{"name": "X"}, {"name": "Y"}], "P1", True)
        x, y = self.sg[-2], self.sg[-1]
        self.assertRegex(x["imported"], STAMP_RE)
        self.assertEqual(x["created"], x["imported"])
        self.assertEqual(x["imported"], y["imported"])  # computed once per call

    # R3-AC-5
    def test_replace_false(self):
        last = app.merge_imported_script_groups(self.sg, self.incoming, "P1", False, now=NOW)
        self.assertEqual(last, "G2")
        self.assertIn(self.p1_g1, self.sg)
        self.assertEqual(names_of(self.sg, "P1"), ["G1", "g1 (2)", "G2"])
        self.assertEqual(self.p2_g1, self.p2_before)

    def test_replace_false_suffix_3_when_2_taken(self):
        self.sg.append(grp("G1 (2)", "P1"))
        last = app.merge_imported_script_groups(self.sg, [self.incoming[0]], "P1", False, now=NOW)
        self.assertEqual(last, "g1 (3)")
        self.assertEqual(names_of(self.sg, "P1"), ["G1", "G1 (2)", "g1 (3)"])

    def test_suffix_ignores_other_profile_names(self):
        self.sg.append(grp("G1 (2)", "P2"))
        last = app.merge_imported_script_groups(self.sg, [self.incoming[0]], "P1", False, now=NOW)
        self.assertEqual(last, "g1 (2)")

    def test_no_clash_new_profile(self):
        last = app.merge_imported_script_groups(self.sg, [{"name": "G1"}], "P3", False, now=NOW)
        self.assertEqual(last, "G1")
        self.assertEqual(names_of(self.sg, "P3"), ["G1"])
        self.assertEqual(self.sg[-1]["scripts"], [])  # missing scripts key -> []

    # R3-AC-6
    def test_same_name_twice_replace_true(self):
        incoming = [{"name": "G1", "scripts": [{"query": "A"}]},
                    {"name": "G1", "scripts": [{"query": "B"}]}]
        last = app.merge_imported_script_groups(self.sg, incoming, "P1", True, now=NOW)
        self.assertEqual(last, "G1 (2)")
        self.assertNotIn(self.p1_g1, self.sg)
        self.assertEqual(names_of(self.sg, "P1"), ["G1", "G1 (2)"])
        self.assertEqual(self.sg[-2]["scripts"], [{"query": "A"}])
        self.assertEqual(self.sg[-1]["scripts"], [{"query": "B"}])
        self.assertEqual(self.p2_g1, self.p2_before)

    def test_same_name_twice_replace_false(self):
        incoming = [{"name": "G1"}, {"name": "G1"}]
        last = app.merge_imported_script_groups(self.sg, incoming, "P1", False, now=NOW)
        self.assertEqual(last, "G1 (3)")
        self.assertEqual(names_of(self.sg, "P1"), ["G1", "G1 (2)", "G1 (3)"])

    def test_same_name_twice_no_existing(self):
        incoming = [{"name": "N"}, {"name": "n"}]
        last = app.merge_imported_script_groups(self.sg, incoming, "P1", True, now=NOW)
        self.assertEqual(last, "n (2)")
        self.assertEqual(names_of(self.sg, "P1"), ["G1", "N", "n (2)"])

    def test_empty_incoming_returns_none(self):
        before = copy.deepcopy(self.sg)
        self.assertIsNone(app.merge_imported_script_groups(self.sg, [], "P1", True, now=NOW))
        self.assertEqual(self.sg, before)

    def test_in_place_same_list(self):
        ref = self.sg
        app.merge_imported_script_groups(self.sg, self.incoming, "P1", True, now=NOW)
        self.assertIs(ref, self.sg)

    # R3-AC-7
    def test_timestamp_to_str_and_deep_copy(self):
        ts = pd.Timestamp("2025-03-04 05:06:07")
        src_script = {"query": "SELECT 1", "when": ts, "nested": {"list": [1, 2]}}
        incoming = [{"name": "T", "scripts": [src_script]}]
        app.merge_imported_script_groups(self.sg, incoming, "P1", True, now=NOW)
        new = self.sg[-1]["scripts"][0]
        self.assertIsInstance(new["when"], str)
        self.assertEqual(new["when"], str(ts))
        self.assertIsNot(new, src_script)
        self.assertIsNot(self.sg[-1]["scripts"], incoming[0]["scripts"])
        src_script["query"] = "CHANGED"
        src_script["nested"]["list"].append(3)
        incoming[0]["scripts"].append({"query": "more"})
        self.assertEqual(new["query"], "SELECT 1")
        self.assertEqual(new["nested"], {"list": [1, 2]})
        self.assertEqual(len(self.sg[-1]["scripts"]), 1)
        json.dumps(self.sg[-1])  # fully JSON-serialisable

    def test_incoming_group_not_mutated(self):
        incoming = copy.deepcopy(self.incoming)
        app.merge_imported_script_groups(self.sg, incoming, "P1", False, now=NOW)
        self.assertEqual(incoming, self.incoming)

    def test_parse_then_merge_pipeline(self):
        data = {"type": "script_groups", "groups": [
            {"name": "g1", "scripts": [{"query": "X"}]},
            {"name": "", "scripts": []},
            {"name": "G9", "scripts": "bad"},
        ]}
        incoming = app.parse_script_groups_import(data)
        self.assertEqual(app.script_group_name_clashes(self.sg, incoming, "P1"), ["g1"])
        last = app.merge_imported_script_groups(self.sg, incoming, "P1", False, now=NOW)
        self.assertEqual(last, "g1 (2)")


# ----------------------------------------------------------------------
# R3-T2: export_script_groups / _ensure_script_groups_loaded
# (R3-AC-1 in flow, R3-AC-10 export, R3-AC-14 ensure, R3-AC-17 dialog export)
# ----------------------------------------------------------------------
FNAME_RE_TMPL = r"^script_groups_{label}_\d{{8}}_\d{{6}}\.json$"


def make_flow_stub():
    stub = app.DatabaseConnectorGUI.__new__(app.DatabaseConnectorGUI)
    stub.root = object()
    stub.results_text = mock.Mock()
    return stub


def two_groups():
    return [
        grp("G1", scripts=[{"name": "a", "query": "SELECT 1", "_tmp": 1, "run_index": 2, "target": "T"},
                           {"name": "b", "query": "SELECT 2"}]),
        grp("G2", scripts=[{"name": "c", "query": "SELECT 3", "run_index": 0}]),
    ]


class ExportFlowBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.out = os.path.join(self.tmp.name, "out.json")
        self.stub = make_flow_stub()
        self.parent = object()
        p1 = mock.patch.object(app, "messagebox")
        p2 = mock.patch.object(app, "filedialog")
        self.mb = p1.start()
        self.fd = p2.start()
        self.addCleanup(p1.stop)
        self.addCleanup(p2.stop)
        self.fd.asksaveasfilename.return_value = self.out

    def read_out(self):
        with open(self.out, encoding="utf-8") as fh:
            return json.load(fh)

    def assert_all_parents(self):
        calls = (self.mb.showinfo.call_args_list + self.mb.askyesnocancel.call_args_list
                 + self.mb.showerror.call_args_list + self.mb.showwarning.call_args_list
                 + self.fd.asksaveasfilename.call_args_list)
        self.assertTrue(calls)
        for c in calls:
            self.assertIs(c.kwargs.get("parent"), self.parent, c)


class TestExportFlow(ExportFlowBase):
    def test_empty_groups_info_no_dialog(self):
        result = self.stub.export_script_groups(self.parent, [], "P1")
        self.assertIsNone(result)
        self.mb.showinfo.assert_called_once_with(
            "Export Groups", "This profile has no groups to export", parent=self.parent)
        self.fd.asksaveasfilename.assert_not_called()
        self.mb.askyesnocancel.assert_not_called()
        self.stub.results_text.insert.assert_not_called()
        self.assertFalse(os.path.exists(self.out))

    def test_empty_groups_with_selected_still_info(self):
        result = self.stub.export_script_groups(self.parent, [], "P1", selected={"name": "X"})
        self.assertIsNone(result)
        self.mb.askyesnocancel.assert_not_called()
        self.fd.asksaveasfilename.assert_not_called()
        self.assert_all_parents()

    def test_selected_none_never_asks_exports_all(self):
        groups = two_groups()
        result = self.stub.export_script_groups(self.parent, groups, "P1")
        self.assertEqual(result, self.out)
        self.mb.askyesnocancel.assert_not_called()
        data = self.read_out()
        self.assertEqual([g["name"] for g in data["groups"]], ["G1", "G2"])
        initial = self.fd.asksaveasfilename.call_args.kwargs["initialfile"]
        self.assertRegex(initial, FNAME_RE_TMPL.format(label="P1"))
        self.assert_all_parents()

    def test_file_dialog_kwargs(self):
        self.stub.export_script_groups(self.parent, two_groups(), "P1")
        kw = self.fd.asksaveasfilename.call_args.kwargs
        self.assertEqual(kw["title"], "Export Script Groups")
        self.assertEqual(kw["defaultextension"], ".json")
        self.assertEqual(kw["filetypes"], [("JSON files", "*.json")])

    def test_output_file_content(self):
        groups = two_groups()
        before = copy.deepcopy(groups)
        self.stub.export_script_groups(self.parent, groups, "P1")
        data = self.read_out()
        self.assertEqual(set(data), {"type", "version", "exported", "profile", "groups"})
        self.assertEqual(data["type"], "script_groups")
        self.assertEqual(data["version"], 1)
        self.assertEqual(data["profile"], "P1")
        self.assertRegex(data["exported"], STAMP_RE)
        for g in data["groups"]:
            self.assertEqual(set(g), {"name", "created", "scripts"})
            for s in g["scripts"]:
                self.assertNotIn("run_index", s)
                self.assertFalse(any(k.startswith("_") for k in s))
        self.assertEqual(data["groups"][0]["scripts"][0], {"name": "a", "query": "SELECT 1", "target": "T"})
        self.assertEqual(data["groups"][1]["scripts"], [{"name": "c", "query": "SELECT 3"}])
        self.assertEqual(groups, before)  # in-memory groups untouched

    def test_utf8_non_ascii_written_raw(self):
        groups = [grp("กลุ่ม", scripts=[{"query": "SELECT 'ทดสอบ'"}])]
        self.stub.export_script_groups(self.parent, groups, "P1")
        with open(self.out, encoding="utf-8") as fh:
            text = fh.read()
        self.assertIn("กลุ่ม", text)  # ensure_ascii=False

    def test_log_line_exact_and_return_path(self):
        result = self.stub.export_script_groups(self.parent, two_groups(), "P1")
        self.assertEqual(result, self.out)
        self.stub.results_text.insert.assert_called_once_with(
            app.tk.END, f"📤 Exported 2 group(s), 3 script(s) → {self.out}\n")
        self.stub.results_text.see.assert_called_once_with(app.tk.END)

    def test_success_info_message(self):
        self.stub.export_script_groups(self.parent, two_groups(), "P1")
        self.mb.showinfo.assert_called_once_with(
            "Export Groups", f"Exported 2 group(s), 3 script(s)\n\n{self.out}", parent=self.parent)
        self.mb.showerror.assert_not_called()

    def test_save_cancel_no_write_no_log(self):
        self.fd.asksaveasfilename.return_value = ""
        result = self.stub.export_script_groups(self.parent, two_groups(), "P1")
        self.assertIsNone(result)
        self.assertEqual(os.listdir(self.tmp.name), [])
        self.stub.results_text.insert.assert_not_called()
        self.mb.showinfo.assert_not_called()
        self.mb.showerror.assert_not_called()

    def test_write_error(self):
        bad = os.path.join(self.tmp.name, "missing_dir", "out.json")
        self.fd.asksaveasfilename.return_value = bad
        result = self.stub.export_script_groups(self.parent, two_groups(), "P1")
        self.assertIsNone(result)
        self.mb.showerror.assert_called_once()
        args, kwargs = self.mb.showerror.call_args
        self.assertEqual(args[0], "Export Groups")
        self.assertTrue(args[1].startswith("Cannot write file:\n"), args[1])
        self.assertGreater(len(args[1]), len("Cannot write file:\n"))
        self.assertIs(kwargs["parent"], self.parent)
        self.stub.results_text.insert.assert_not_called()
        self.mb.showinfo.assert_not_called()
        self.assertFalse(os.path.exists(bad))

    def test_write_error_from_json_dump(self):
        with mock.patch.object(app.json, "dump", side_effect=TypeError("boom")):
            result = self.stub.export_script_groups(self.parent, two_groups(), "P1")
        self.assertIsNone(result)
        self.mb.showerror.assert_called_once_with(
            "Export Groups", "Cannot write file:\nboom", parent=self.parent)
        self.stub.results_text.insert.assert_not_called()

    def test_group_without_scripts_counts_zero(self):
        result = self.stub.export_script_groups(self.parent, [{"name": "E", "profile": "P1"}], "P1")
        self.assertEqual(result, self.out)
        self.stub.results_text.insert.assert_called_once_with(
            app.tk.END, f"📤 Exported 1 group(s), 0 script(s) → {self.out}\n")


class TestExportScopeQuestion(ExportFlowBase):
    """R3-AC-17 export part: all / only-selected question in the dialog."""

    def test_asks_when_selected_and_more_than_one(self):
        groups = two_groups()
        self.mb.askyesnocancel.return_value = True
        self.stub.export_script_groups(self.parent, groups, "P1", selected=groups[1])
        self.mb.askyesnocancel.assert_called_once_with(
            "Export Groups",
            "Export ALL 2 groups of profile 'P1'?\n\nYes = all groups\nNo = only 'G2'",
            parent=self.parent,
        )
        self.assert_all_parents()

    def test_yes_exports_all_filename_profile(self):
        groups = two_groups()
        self.mb.askyesnocancel.return_value = True
        result = self.stub.export_script_groups(self.parent, groups, "P1", selected=groups[1])
        self.assertEqual(result, self.out)
        self.assertEqual([g["name"] for g in self.read_out()["groups"]], ["G1", "G2"])
        initial = self.fd.asksaveasfilename.call_args.kwargs["initialfile"]
        self.assertRegex(initial, FNAME_RE_TMPL.format(label="P1"))

    def test_no_exports_only_selected_filename_group(self):
        groups = two_groups()
        self.mb.askyesnocancel.return_value = False
        result = self.stub.export_script_groups(self.parent, groups, "P1", selected=groups[1])
        self.assertEqual(result, self.out)
        data = self.read_out()
        self.assertEqual([g["name"] for g in data["groups"]], ["G2"])
        self.assertEqual(data["profile"], "P1")
        initial = self.fd.asksaveasfilename.call_args.kwargs["initialfile"]
        self.assertRegex(initial, FNAME_RE_TMPL.format(label="G2"))
        self.stub.results_text.insert.assert_called_once_with(
            app.tk.END, f"📤 Exported 1 group(s), 1 script(s) → {self.out}\n")
        self.assert_all_parents()

    def test_no_with_unsafe_group_name(self):
        groups = two_groups()
        groups[1]["name"] = "a/b:c"
        self.mb.askyesnocancel.return_value = False
        self.stub.export_script_groups(self.parent, groups, "P1", selected=groups[1])
        initial = self.fd.asksaveasfilename.call_args.kwargs["initialfile"]
        self.assertRegex(initial, FNAME_RE_TMPL.format(label="a_b_c"))

    def test_cancel_no_file_dialog(self):
        groups = two_groups()
        self.mb.askyesnocancel.return_value = None
        result = self.stub.export_script_groups(self.parent, groups, "P1", selected=groups[0])
        self.assertIsNone(result)
        self.fd.asksaveasfilename.assert_not_called()
        self.stub.results_text.insert.assert_not_called()
        self.mb.showinfo.assert_not_called()
        self.assertEqual(os.listdir(self.tmp.name), [])

    def test_selected_with_single_group_no_question(self):
        groups = two_groups()[:1]
        result = self.stub.export_script_groups(self.parent, groups, "P1", selected=groups[0])
        self.assertEqual(result, self.out)
        self.mb.askyesnocancel.assert_not_called()
        initial = self.fd.asksaveasfilename.call_args.kwargs["initialfile"]
        self.assertRegex(initial, FNAME_RE_TMPL.format(label="P1"))

    def test_no_then_save_cancel(self):
        groups = two_groups()
        self.mb.askyesnocancel.return_value = False
        self.fd.asksaveasfilename.return_value = ""
        self.assertIsNone(self.stub.export_script_groups(self.parent, groups, "P1", selected=groups[0]))
        self.stub.results_text.insert.assert_not_called()


class TestEnsureLoaded(unittest.TestCase):
    def test_loads_once_when_missing(self):
        stub = app.DatabaseConnectorGUI.__new__(app.DatabaseConnectorGUI)
        loaded = [grp("G1")]
        stub.load_script_groups = mock.Mock(return_value=loaded)
        self.assertFalse(hasattr(stub, "script_groups"))
        self.assertIs(stub._ensure_script_groups_loaded(), loaded)
        self.assertIs(stub.script_groups, loaded)
        self.assertIs(stub._ensure_script_groups_loaded(), loaded)
        stub.load_script_groups.assert_called_once_with()

    def test_existing_attr_not_reloaded(self):
        stub = app.DatabaseConnectorGUI.__new__(app.DatabaseConnectorGUI)
        existing = []
        stub.script_groups = existing
        stub.load_script_groups = mock.Mock(return_value=[grp("X")])
        self.assertIs(stub._ensure_script_groups_loaded(), existing)
        stub.load_script_groups.assert_not_called()

    def test_real_load_from_tempdir(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "script_groups.json")
            with open(path, "w", encoding="utf-8") as fh:
                json.dump([grp("Old")], fh)
            stub = app.DatabaseConnectorGUI.__new__(app.DatabaseConnectorGUI)
            stub._script_groups_path = lambda: path
            with mock.patch.object(app, "messagebox"):
                groups = stub._ensure_script_groups_loaded()
            self.assertEqual([g["name"] for g in groups], ["Old"])


class TestDialogDelegates(unittest.TestCase):
    """The dialog closure delegates instead of duplicating the export flow."""

    def test_source(self):
        import inspect
        src = inspect.getsource(app.DatabaseConnectorGUI.show_script_groups_dialog)
        self.assertIn(
            'self.export_script_groups(dialog, state["groups"], state["profile"], current_group())', src)
        self.assertIn("self._ensure_script_groups_loaded()", src)
        self.assertNotIn("Export ALL", src)
        self.assertNotIn("Cannot write file", src)
        module_src = inspect.getsource(app)
        self.assertEqual(module_src.count("Export ALL"), 1)


# ----------------------------------------------------------------------
# R3-T3: import_script_groups / _ask_import_mode / _refresh_script_groups_window
# (R3-AC-10 import, R3-AC-11, R3-AC-12, R3-AC-13, R3-AC-14 import, R3-AC-15 logic,
#  R3-AC-17 dialog import)
# ----------------------------------------------------------------------
INVALID_MSG = "Not a valid Script Groups file:\n"


class ImportFlowBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.src = os.path.join(self.tmp.name, "in.json")
        self.stub = make_flow_stub()
        self.stub.profile_combo = mock.Mock()
        self.stub.profile_combo.get.return_value = "P1"
        self.stub.save_script_groups = mock.Mock()
        self.p1_g1 = grp("G1", "P1", scripts=[{"query": "OLD"}])
        self.p2_g1 = grp("G1", "P2", scripts=[{"query": "P2"}])
        self.stub.script_groups = [self.p1_g1, self.p2_g1]
        self.sg_ref = self.stub.script_groups
        self.sg_before = copy.deepcopy(self.stub.script_groups)
        self.parent = object()
        p1 = mock.patch.object(app, "messagebox")
        p2 = mock.patch.object(app, "filedialog")
        self.mb = p1.start()
        self.fd = p2.start()
        self.addCleanup(p1.stop)
        self.addCleanup(p2.stop)
        self.fd.askopenfilename.return_value = self.src
        self.mb.askyesno.return_value = True
        self.mb.askyesnocancel.return_value = True

    def write_src(self, data, raw=None):
        with open(self.src, "w", encoding="utf-8") as fh:
            if raw is not None:
                fh.write(raw)
            else:
                json.dump(data, fh)

    def assert_nothing_done(self):
        self.assertIs(self.stub.script_groups, self.sg_ref)
        self.assertEqual(self.stub.script_groups, self.sg_before)
        self.stub.save_script_groups.assert_not_called()
        self.stub.results_text.insert.assert_not_called()

    def assert_all_parents(self):
        calls = (self.mb.showinfo.call_args_list + self.mb.askyesnocancel.call_args_list
                 + self.mb.askyesno.call_args_list
                 + self.mb.showerror.call_args_list + self.mb.showwarning.call_args_list
                 + self.fd.askopenfilename.call_args_list)
        self.assertTrue(calls)
        for c in calls:
            self.assertIs(c.kwargs.get("parent"), self.parent, c)


class TestImportCancelAndErrors(ImportFlowBase):
    # R3-AC-11
    def test_empty_profile_warning_no_file_dialog(self):
        self.stub.profile_combo.get.return_value = ""
        self.assertIsNone(self.stub.import_script_groups(self.parent))
        self.mb.showwarning.assert_called_once_with(
            "Import Groups", "Please select a profile first", parent=self.parent)
        self.fd.askopenfilename.assert_not_called()
        self.assert_nothing_done()

    def test_empty_profile_still_loads_groups_first(self):
        stub = make_flow_stub()
        stub.profile_combo = mock.Mock(get=mock.Mock(return_value=""))
        stub.load_script_groups = mock.Mock(return_value=[])
        with mock.patch.object(app, "messagebox"), mock.patch.object(app, "filedialog") as fd:
            self.assertIsNone(stub.import_script_groups(self.parent))
            fd.askopenfilename.assert_not_called()
        stub.load_script_groups.assert_called_once_with()

    # R3-AC-10 (import)
    def test_file_dialog_cancel(self):
        self.fd.askopenfilename.return_value = ""
        self.assertIsNone(self.stub.import_script_groups(self.parent))
        self.fd.askopenfilename.assert_called_once_with(
            parent=self.parent, title="Import Script Groups",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")])
        self.mb.showerror.assert_not_called()
        self.mb.showinfo.assert_not_called()
        self.mb.askyesno.assert_not_called()
        self.mb.askyesnocancel.assert_not_called()
        self.assert_nothing_done()

    # R3-AC-13
    def _assert_invalid(self):
        self.assertIsNone(self.stub.import_script_groups(self.parent))
        self.mb.showerror.assert_called_once()
        args, kwargs = self.mb.showerror.call_args
        self.assertEqual(args[0], "Import Groups")
        self.assertTrue(args[1].startswith(INVALID_MSG), args[1])
        self.assertIs(kwargs["parent"], self.parent)
        self.mb.askyesno.assert_not_called()
        self.mb.askyesnocancel.assert_not_called()
        self.assert_nothing_done()
        return args[1]

    def test_broken_json(self):
        self.write_src(None, raw="{ not json")
        self._assert_invalid()

    def test_no_groups_list(self):
        self.write_src({"type": "script_groups", "version": 1})
        msg = self._assert_invalid()
        self.assertIn("groups", msg)

    def test_script_without_sql(self):
        self.write_src({"groups": [{"name": "Bad", "scripts": [{"name": "x"}]}]})
        msg = self._assert_invalid()
        self.assertIn("Bad", msg)

    def test_missing_file(self):
        self.fd.askopenfilename.return_value = os.path.join(self.tmp.name, "nope.json")
        self._assert_invalid()

    def test_not_utf8(self):
        with open(self.src, "wb") as fh:
            fh.write(b'{"groups": [{"name": "\xff\xfe"}]}')
        self._assert_invalid()

    def test_empty_groups_info(self):
        self.write_src({"groups": []})
        self.assertIsNone(self.stub.import_script_groups(self.parent))
        self.mb.showinfo.assert_called_once_with(
            "Import Groups", "No groups found in this file", parent=self.parent)
        self.mb.showerror.assert_not_called()
        self.mb.askyesno.assert_not_called()
        self.assert_nothing_done()

    def test_all_filtered_info(self):
        self.write_src([{"name": ""}, "x", {"name": "S", "scripts": "bad"}])
        self.assertIsNone(self.stub.import_script_groups(self.parent))
        self.mb.showinfo.assert_called_once_with(
            "Import Groups", "No groups found in this file", parent=self.parent)
        self.assert_nothing_done()


class TestImportClash(ImportFlowBase):
    """R3-AC-12: Yes / No / Cancel with a name clash."""

    def setUp(self):
        super().setUp()
        self.write_src({"type": "script_groups", "groups": [
            {"name": "g1", "created": "2024-01-01 00:00:00", "scripts": [{"query": "NEW1"}]},
            {"name": "G2", "scripts": [{"query": "NEW2"}]},
        ]})

    def test_yes_replaces(self):
        self.mb.askyesnocancel.return_value = True
        last = self.stub.import_script_groups(self.parent)
        self.assertEqual(last, "G2")
        self.assertIs(self.stub.script_groups, self.sg_ref)
        self.assertNotIn(self.p1_g1, self.stub.script_groups)
        self.assertEqual(names_of(self.stub.script_groups, "P1"), ["g1", "G2"])
        self.assertEqual(self.stub.script_groups[0], self.sg_before[1])  # P2 untouched
        g1 = next(g for g in self.stub.script_groups if g["name"] == "g1")
        self.assertEqual(g1["profile"], "P1")
        self.assertEqual(g1["created"], "2024-01-01 00:00:00")
        self.assertRegex(g1["imported"], STAMP_RE)
        self.stub.save_script_groups.assert_called_once_with()
        self.stub.results_text.insert.assert_called_once_with(
            app.tk.END, f"📥 Imported 2 group(s) from {self.src}\n")
        self.stub.results_text.see.assert_called_once_with(app.tk.END)
        self.mb.askyesno.assert_not_called()
        self.assert_all_parents()

    def test_no_keeps_both(self):
        self.mb.askyesnocancel.return_value = False
        last = self.stub.import_script_groups(self.parent)
        self.assertEqual(last, "G2")
        self.assertIn(self.p1_g1, self.stub.script_groups)
        self.assertEqual(names_of(self.stub.script_groups, "P1"), ["G1", "g1 (2)", "G2"])
        self.assertEqual(names_of(self.stub.script_groups, "P2"), ["G1"])
        self.stub.save_script_groups.assert_called_once_with()
        self.stub.results_text.insert.assert_called_once_with(
            app.tk.END, f"📥 Imported 2 group(s) from {self.src}\n")

    def test_cancel_nothing(self):
        self.mb.askyesnocancel.return_value = None
        self.assertIsNone(self.stub.import_script_groups(self.parent))
        self.assert_nothing_done()
        self.mb.askyesno.assert_not_called()

    def test_clash_message_text(self):
        self.mb.askyesnocancel.return_value = None
        self.stub.import_script_groups(self.parent)
        self.mb.askyesnocancel.assert_called_once_with(
            "Import Groups",
            "Import 2 group(s) into profile 'P1':\n\n"
            "• g1  (1 scripts)  ← already exists\n"
            "• G2  (1 scripts)\n\n"
            "1 group name(s) already exist.\n"
            "Yes = replace them\nNo = keep both (imported copy gets a new name)\n"
            "Cancel = do not import",
            parent=self.parent,
        )

    def test_order_save_refresh_log(self):
        order = []
        self.stub.save_script_groups.side_effect = lambda: order.append("save") or True
        self.stub._refresh_script_groups_window = lambda name: order.append(("refresh", name))
        self.stub.results_text.insert.side_effect = lambda *a: order.append("log")
        self.stub.import_script_groups(self.parent)
        self.assertEqual(order, ["save", ("refresh", "G2"), "log"])


class TestImportNoClash(ImportFlowBase):
    def setUp(self):
        super().setUp()
        self.write_src([{"name": "New", "scripts": [{"query": "A"}, {"query": "B"}]}])

    def test_confirm_yes_imports(self):
        last = self.stub.import_script_groups(self.parent)
        self.assertEqual(last, "New")
        self.mb.askyesno.assert_called_once_with(
            "Import Groups",
            "Import 1 group(s) into profile 'P1'?\n\n• New  (2 scripts)",
            parent=self.parent)
        self.mb.askyesnocancel.assert_not_called()
        self.assertEqual(names_of(self.stub.script_groups, "P1"), ["G1", "New"])
        self.stub.save_script_groups.assert_called_once_with()
        self.stub.results_text.insert.assert_called_once_with(
            app.tk.END, f"📥 Imported 1 group(s) from {self.src}\n")
        self.assert_all_parents()

    def test_confirm_no_nothing(self):
        self.mb.askyesno.return_value = False
        self.assertIsNone(self.stub.import_script_groups(self.parent))
        self.assert_nothing_done()

    def test_other_profile_name_not_a_clash(self):
        self.stub.profile_combo.get.return_value = "P2"
        self.write_src([{"name": "zzz", "scripts": []}])
        self.assertEqual(self.stub.import_script_groups(self.parent), "zzz")
        self.mb.askyesnocancel.assert_not_called()


class TestAskImportModeSummary(unittest.TestCase):
    def setUp(self):
        self.stub = make_flow_stub()
        self.stub.script_groups = [grp("G0", "P1")]
        self.parent = object()

    def run_mode(self, incoming, yes=True):
        with mock.patch.object(app, "messagebox") as mb:
            mb.askyesno.return_value = yes
            mb.askyesnocancel.return_value = "SENTINEL"
            result = self.stub._ask_import_mode(self.parent, incoming, "P1")
        return result, mb

    def test_truncates_after_15(self):
        incoming = [{"name": f"N{i}", "scripts": []} for i in range(20)]
        result, mb = self.run_mode(incoming)
        self.assertIs(result, False)
        msg = mb.askyesno.call_args.args[1]
        lines = [ln for ln in msg.split("\n") if ln.startswith("• ")]
        self.assertEqual(len(lines), 15)
        self.assertTrue(msg.endswith("• N14  (0 scripts)\n... and 5 more"), msg)
        self.assertNotIn("N15", msg)
        self.assertIs(mb.askyesno.call_args.kwargs["parent"], self.parent)

    def test_exactly_15_no_more_line(self):
        incoming = [{"name": f"N{i}"} for i in range(15)]
        _, mb = self.run_mode(incoming)
        self.assertNotIn("more", mb.askyesno.call_args.args[1])

    def test_16_one_more(self):
        incoming = [{"name": f"N{i}"} for i in range(16)]
        _, mb = self.run_mode(incoming)
        self.assertTrue(mb.askyesno.call_args.args[1].endswith("\n... and 1 more"))

    def test_clash_returns_askyesnocancel_value(self):
        incoming = [{"name": "g0"}] + [{"name": f"N{i}"} for i in range(16)]
        result, mb = self.run_mode(incoming)
        self.assertEqual(result, "SENTINEL")
        mb.askyesno.assert_not_called()
        msg = mb.askyesnocancel.call_args.args[1]
        self.assertIn("• g0  (0 scripts)  ← already exists", msg)
        self.assertIn("... and 2 more", msg)
        self.assertIn("1 group name(s) already exist.", msg)
        self.assertIs(mb.askyesnocancel.call_args.kwargs["parent"], self.parent)

    def test_no_clash_no_returns_none(self):
        result, _ = self.run_mode([{"name": "X"}], yes=False)
        self.assertIsNone(result)


class TestImportEnsureLoaded(unittest.TestCase):
    """R3-AC-14 (import): no script_groups attribute + real file in tempdir."""

    def test_old_and_new_groups_in_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = os.path.join(tmp, "script_groups.json")
            with open(store, "w", encoding="utf-8") as fh:
                json.dump({"version": 1, "groups": [grp("Old", "P1"), grp("Other", "P2")]}, fh)
            src = os.path.join(tmp, "in.json")
            with open(src, "w", encoding="utf-8") as fh:
                json.dump({"type": "script_groups", "groups": [
                    {"name": "New", "scripts": [{"query": "SELECT 9"}]}]}, fh)
            stub = make_flow_stub()
            stub.profile_combo = mock.Mock(get=mock.Mock(return_value="P1"))
            stub._script_groups_path = lambda: store
            self.assertFalse(hasattr(stub, "script_groups"))
            with mock.patch.object(app, "messagebox") as mb, \
                    mock.patch.object(app, "filedialog") as fd:
                fd.askopenfilename.return_value = src
                mb.askyesno.return_value = True
                last = stub.import_script_groups(object())
                mb.showerror.assert_not_called()
            self.assertEqual(last, "New")
            with open(store, encoding="utf-8") as fh:
                saved = json.load(fh)
            names = [(g["name"], g["profile"]) for g in saved["groups"]]
            self.assertEqual(names, [("Old", "P1"), ("Other", "P2"), ("New", "P1")])
            self.assertTrue(os.path.exists(os.path.join(tmp, "script_groups_backup.json")))
            stub.results_text.insert.assert_called_once_with(
                app.tk.END, f"📥 Imported 1 group(s) from {src}\n")


class TestRefreshWindow(unittest.TestCase):
    """R3-AC-15 logic."""

    def test_callback_gets_last_name_after_import(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "in.json")
            with open(src, "w", encoding="utf-8") as fh:
                json.dump([{"name": "A"}, {"name": "B"}], fh)
            stub = make_flow_stub()
            stub.profile_combo = mock.Mock(get=mock.Mock(return_value="P1"))
            stub.save_script_groups = mock.Mock()
            stub.script_groups = []
            cb = mock.Mock()
            stub._script_groups_refresh = cb
            stub._script_groups_window = mock.Mock(winfo_exists=lambda: True)
            with mock.patch.object(app, "messagebox") as mb, \
                    mock.patch.object(app, "filedialog") as fd:
                fd.askopenfilename.return_value = src
                mb.askyesno.return_value = True
                self.assertEqual(stub.import_script_groups(object()), "B")
            cb.assert_called_once_with("B")
            self.assertIs(stub._script_groups_refresh, cb)

    def test_callback_not_called_on_cancel(self):
        stub = make_flow_stub()
        stub.profile_combo = mock.Mock(get=mock.Mock(return_value="P1"))
        stub.script_groups = []
        cb = mock.Mock()
        stub._script_groups_refresh = cb
        stub._script_groups_window = mock.Mock(winfo_exists=lambda: True)
        with mock.patch.object(app, "messagebox"), mock.patch.object(app, "filedialog") as fd:
            fd.askopenfilename.return_value = ""
            stub.import_script_groups(object())
        cb.assert_not_called()

    def test_window_gone_clears_and_not_called(self):
        stub = make_flow_stub()
        cb = mock.Mock()
        stub._script_groups_refresh = cb
        stub._script_groups_window = mock.Mock(winfo_exists=lambda: False)
        stub._refresh_script_groups_window("X")
        cb.assert_not_called()
        self.assertIsNone(stub._script_groups_refresh)

    def test_window_none_clears(self):
        stub = make_flow_stub()
        cb = mock.Mock()
        stub._script_groups_refresh = cb
        stub._script_groups_window = None
        stub._refresh_script_groups_window("X")
        cb.assert_not_called()
        self.assertIsNone(stub._script_groups_refresh)

    def test_no_attrs_no_error(self):
        stub = make_flow_stub()
        stub._refresh_script_groups_window("X")
        stub._refresh_script_groups_window()

    def test_callback_without_window_attr(self):
        stub = make_flow_stub()
        cb = mock.Mock()
        stub._script_groups_refresh = cb
        stub._refresh_script_groups_window("X")
        cb.assert_not_called()
        self.assertIsNone(stub._script_groups_refresh)

    def test_default_select_name_none(self):
        stub = make_flow_stub()
        cb = mock.Mock()
        stub._script_groups_refresh = cb
        stub._script_groups_window = mock.Mock(winfo_exists=lambda: True)
        stub._refresh_script_groups_window()
        cb.assert_called_once_with(None)

    def test_import_ok_without_refresh_attrs(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "in.json")
            with open(src, "w", encoding="utf-8") as fh:
                json.dump([{"name": "A"}], fh)
            stub = make_flow_stub()
            stub.profile_combo = mock.Mock(get=mock.Mock(return_value="P1"))
            stub.save_script_groups = mock.Mock()
            stub.script_groups = []
            with mock.patch.object(app, "messagebox") as mb, \
                    mock.patch.object(app, "filedialog") as fd:
                fd.askopenfilename.return_value = src
                mb.askyesno.return_value = True
                self.assertEqual(stub.import_script_groups(object()), "A")


class TestDialogImportDelegates(unittest.TestCase):
    """R3-AC-17 import part + refresh registration (source check, no Tk)."""

    @classmethod
    def setUpClass(cls):
        import inspect
        cls.src = inspect.getsource(app.DatabaseConnectorGUI.show_script_groups_dialog)
        cls.module_src = inspect.getsource(app)

    def test_import_closure_delegates(self):
        self.assertRegex(self.src, r"def import_groups\(\):\n\s+self\.import_script_groups\(dialog\)\n")
        self.assertNotIn("Not a valid Script Groups file", self.src)
        self.assertNotIn("askopenfilename", self.src)
        self.assertEqual(self.module_src.count("Not a valid Script Groups file"), 1)
        self.assertEqual(self.module_src.count("No groups found in this file"), 1)

    def test_refresh_registered_and_destroy_guarded(self):
        self.assertIn("self._script_groups_refresh = registered", self.src)
        self.assertIn("refresh_groups(select_name=name)", self.src)
        self.assertIn('dialog.bind("<Destroy>", _on_destroy, add="+")', self.src)
        self.assertIn("event.widget is dialog", self.src)
        self.assertIn('getattr(self, "_script_groups_refresh", None) is registered', self.src)
        # registration happens before the final refresh_groups()
        reg = self.src.index("self._script_groups_refresh = registered")
        self.assertLess(reg, self.src.rindex("refresh_groups()"))
        self.assertIn("self._script_groups_window = dialog", self.src)

    def test_import_button_wired(self):
        self.assertIn('"⇧  Import Groups", import_groups', self.src)


# ----------------------------------------------------------------------
# R3-T4: sidebar handlers + sidebar row (R3-AC-8 .. R3-AC-15 through the sidebar)
# ----------------------------------------------------------------------
class SidebarBase(unittest.TestCase):
    """Stub app; root is a sentinel so every parent= can be checked against it."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.out = os.path.join(self.tmp.name, "out.json")
        self.src = os.path.join(self.tmp.name, "in.json")
        self.stub = make_flow_stub()
        self.root = self.stub.root
        self.stub.profile_combo = mock.Mock()
        self.stub.profile_combo.get.return_value = "P1"
        self.stub.save_script_groups = mock.Mock()
        self.g1 = grp("G1", "P1", scripts=[
            {"name": "a", "query": "SELECT 1", "_tmp": 1, "run_index": 3, "target": "T"},
            {"name": "b", "query": "SELECT 2"}])
        self.g2 = grp("G2", "P1", scripts=[{"name": "c", "query": "SELECT 3"}])
        self.g3 = grp("G3", "P2", scripts=[{"name": "d", "query": "SELECT 4"}])
        self.stub.script_groups = [self.g1, self.g3, self.g2]
        self.sg_ref = self.stub.script_groups
        self.sg_before = copy.deepcopy(self.stub.script_groups)
        p1 = mock.patch.object(app, "messagebox")
        p2 = mock.patch.object(app, "filedialog")
        self.mb = p1.start()
        self.fd = p2.start()
        self.addCleanup(p1.stop)
        self.addCleanup(p2.stop)
        self.fd.asksaveasfilename.return_value = self.out
        self.fd.askopenfilename.return_value = self.src
        self.mb.askyesno.return_value = True
        self.mb.askyesnocancel.return_value = True

    def write_src(self, data=None, raw=None):
        with open(self.src, "w", encoding="utf-8") as fh:
            if raw is not None:
                fh.write(raw)
            else:
                json.dump(data, fh)

    def read_out(self):
        with open(self.out, encoding="utf-8") as fh:
            return json.load(fh)

    def all_dialog_calls(self):
        return (self.mb.showinfo.call_args_list + self.mb.showwarning.call_args_list
                + self.mb.showerror.call_args_list + self.mb.askyesno.call_args_list
                + self.mb.askyesnocancel.call_args_list
                + self.fd.asksaveasfilename.call_args_list
                + self.fd.askopenfilename.call_args_list)

    def assert_parent_is_root(self):
        calls = self.all_dialog_calls()
        self.assertTrue(calls)
        for c in calls:
            self.assertIs(c.kwargs.get("parent"), self.root, c)

    def assert_groups_unchanged(self):
        self.assertIs(self.stub.script_groups, self.sg_ref)
        self.assertEqual(self.stub.script_groups, self.sg_before)


class TestSidebarHandlersShape(unittest.TestCase):
    def test_methods_exist_and_take_no_args(self):
        import inspect
        for name in ("sidebar_export_script_groups", "sidebar_import_script_groups"):
            fn = getattr(app.DatabaseConnectorGUI, name)
            params = list(inspect.signature(fn).parameters)
            self.assertEqual(params, ["self"], name)

    def test_export_delegates_with_root_no_selected_and_returns_result(self):
        stub = make_flow_stub()
        stub.profile_combo = mock.Mock(get=mock.Mock(return_value="P1"))
        a, b, c = grp("A", "P1"), grp("B", "P2"), grp("C", "P1")
        stub.script_groups = [a, b, c]
        with mock.patch.object(app.DatabaseConnectorGUI, "export_script_groups",
                               autospec=True, return_value="RESULT") as m:
            self.assertEqual(stub.sidebar_export_script_groups(), "RESULT")
        m.assert_called_once()
        args, kwargs = m.call_args
        self.assertIs(args[0], stub)
        self.assertIs(args[1], stub.root)
        self.assertEqual(args[2], [a, c])
        self.assertIs(args[2][0], a)
        self.assertEqual(args[3], "P1")
        self.assertEqual(len(args), 4)
        self.assertNotIn("selected", kwargs)

    def test_import_delegates_with_root_and_returns_result(self):
        stub = make_flow_stub()
        with mock.patch.object(app.DatabaseConnectorGUI, "import_script_groups",
                               autospec=True, return_value="LAST") as m:
            self.assertEqual(stub.sidebar_import_script_groups(), "LAST")
        m.assert_called_once_with(stub, stub.root)

    def test_import_delegated_none_returned(self):
        stub = make_flow_stub()
        with mock.patch.object(app.DatabaseConnectorGUI, "import_script_groups",
                               autospec=True, return_value=None):
            self.assertIsNone(stub.sidebar_import_script_groups())


class TestSidebarExport(SidebarBase):
    # R3-AC-8
    def test_exports_current_profile_groups_without_scope_question(self):
        result = self.stub.sidebar_export_script_groups()
        self.assertEqual(result, self.out)
        self.mb.askyesnocancel.assert_not_called()
        data = self.read_out()
        self.assertEqual(data["type"], "script_groups")
        self.assertEqual(data["version"], 1)
        self.assertRegex(data["exported"], STAMP_RE)
        self.assertEqual(data["profile"], "P1")
        self.assertEqual([g["name"] for g in data["groups"]], ["G1", "G2"])
        for g in data["groups"]:
            self.assertEqual(set(g), {"name", "created", "scripts"})
        self.assertEqual(data["groups"][0]["scripts"][0],
                         {"name": "a", "query": "SELECT 1", "target": "T"})
        self.assert_groups_unchanged()

    def test_default_filename(self):
        self.stub.sidebar_export_script_groups()
        kwargs = self.fd.asksaveasfilename.call_args.kwargs
        self.assertRegex(kwargs["initialfile"], FNAME_RE_TMPL.format(label="P1"))
        self.assertEqual(kwargs["title"], "Export Script Groups")
        self.assertEqual(kwargs["defaultextension"], ".json")

    def test_default_filename_unsafe_profile(self):
        g = grp("X", 'a/b:c')
        self.stub.script_groups = [g]
        self.stub.profile_combo.get.return_value = 'a/b:c'
        self.stub.sidebar_export_script_groups()
        initial = self.fd.asksaveasfilename.call_args.kwargs["initialfile"]
        self.assertRegex(initial, FNAME_RE_TMPL.format(label="a_b_c"))

    def test_log_line(self):
        self.stub.sidebar_export_script_groups()
        self.stub.results_text.insert.assert_called_once_with(
            app.tk.END, f"📤 Exported 2 group(s), 3 script(s) → {self.out}\n")
        self.stub.results_text.see.assert_called_with(app.tk.END)

    def test_every_dialog_parent_is_root(self):
        self.stub.sidebar_export_script_groups()
        self.mb.showinfo.assert_called_once()  # success info
        self.assert_parent_is_root()

    def test_single_group_profile(self):
        self.stub.profile_combo.get.return_value = "P2"
        self.stub.sidebar_export_script_groups()
        self.mb.askyesnocancel.assert_not_called()
        self.assertEqual([g["name"] for g in self.read_out()["groups"]], ["G3"])
        self.assertEqual(self.read_out()["profile"], "P2")

    def test_export_does_not_save_store(self):
        self.stub.sidebar_export_script_groups()
        self.stub.save_script_groups.assert_not_called()

    # R3-AC-9
    def test_no_groups_info_no_file_dialog(self):
        self.stub.profile_combo.get.return_value = "P9"
        self.assertIsNone(self.stub.sidebar_export_script_groups())
        self.mb.showinfo.assert_called_once_with(
            "Export Groups", "This profile has no groups to export", parent=self.root)
        self.fd.asksaveasfilename.assert_not_called()
        self.mb.askyesnocancel.assert_not_called()
        self.stub.results_text.insert.assert_not_called()
        self.assertEqual(os.listdir(self.tmp.name), [])

    def test_empty_store_info(self):
        self.stub.script_groups = []
        self.assertIsNone(self.stub.sidebar_export_script_groups())
        self.mb.showinfo.assert_called_once_with(
            "Export Groups", "This profile has no groups to export", parent=self.root)
        self.fd.asksaveasfilename.assert_not_called()

    def test_empty_profile_info(self):
        # R3-Q-3: no profile selected -> groups of profile "" (none) -> same info
        self.stub.profile_combo.get.return_value = ""
        self.assertIsNone(self.stub.sidebar_export_script_groups())
        self.mb.showinfo.assert_called_once_with(
            "Export Groups", "This profile has no groups to export", parent=self.root)
        self.fd.asksaveasfilename.assert_not_called()

    # R3-AC-10 (export)
    def test_cancel_save_dialog(self):
        self.fd.asksaveasfilename.return_value = ""
        self.assertIsNone(self.stub.sidebar_export_script_groups())
        self.assertEqual(os.listdir(self.tmp.name), [])
        self.stub.results_text.insert.assert_not_called()
        self.mb.showinfo.assert_not_called()
        self.mb.showerror.assert_not_called()
        self.assert_groups_unchanged()
        self.stub.save_script_groups.assert_not_called()


class TestSidebarImport(SidebarBase):
    def clash_file(self):
        self.write_src({"type": "script_groups", "version": 1, "groups": [
            {"name": "g1", "created": "2024-01-01 00:00:00",
             "scripts": [{"name": "n", "query": "SELECT NEW"}]},
            {"name": "G9", "scripts": [{"query": "SELECT 9"}]}]})

    # R3-AC-10 (import)
    def test_cancel_open_dialog(self):
        self.fd.askopenfilename.return_value = ""
        self.assertIsNone(self.stub.sidebar_import_script_groups())
        self.assert_groups_unchanged()
        self.stub.save_script_groups.assert_not_called()
        self.stub.results_text.insert.assert_not_called()
        self.mb.showerror.assert_not_called()
        self.assert_parent_is_root()

    # R3-AC-11
    def test_no_profile_warning(self):
        self.stub.profile_combo.get.return_value = ""
        self.assertIsNone(self.stub.sidebar_import_script_groups())
        self.mb.showwarning.assert_called_once_with(
            "Import Groups", "Please select a profile first", parent=self.root)
        self.fd.askopenfilename.assert_not_called()
        self.assert_groups_unchanged()
        self.stub.save_script_groups.assert_not_called()

    # R3-AC-12
    def test_clash_yes_replaces(self):
        self.clash_file()
        self.mb.askyesnocancel.return_value = True
        self.assertEqual(self.stub.sidebar_import_script_groups(), "G9")
        self.assertIs(self.stub.script_groups, self.sg_ref)
        p1 = [g for g in self.stub.script_groups if g["profile"] == "P1"]
        self.assertEqual(sorted(g["name"] for g in p1), ["G2", "G9", "g1"])
        new = next(g for g in p1 if g["name"] == "g1")
        self.assertEqual(new["scripts"], [{"name": "n", "query": "SELECT NEW"}])
        self.assertEqual(new["created"], "2024-01-01 00:00:00")
        self.assertIn("imported", new)
        self.assertNotIn(self.g1, self.stub.script_groups)
        self.assertIn(self.g3, self.stub.script_groups)
        self.assertEqual(self.g3, self.sg_before[1])
        self.stub.save_script_groups.assert_called_once_with()
        self.stub.results_text.insert.assert_called_once_with(
            app.tk.END, f"📥 Imported 2 group(s) from {self.src}\n")
        self.mb.askyesno.assert_not_called()
        self.assert_parent_is_root()

    def test_clash_no_keeps_both(self):
        self.clash_file()
        self.mb.askyesnocancel.return_value = False
        self.assertEqual(self.stub.sidebar_import_script_groups(), "G9")
        p1 = names_of(self.stub.script_groups, "P1")
        self.assertEqual(p1, ["G1", "G2", "g1 (2)", "G9"])
        self.assertIn(self.g1, self.stub.script_groups)
        self.stub.save_script_groups.assert_called_once_with()
        self.stub.results_text.insert.assert_called_once_with(
            app.tk.END, f"📥 Imported 2 group(s) from {self.src}\n")
        self.assert_parent_is_root()

    def test_clash_cancel_nothing(self):
        self.clash_file()
        self.mb.askyesnocancel.return_value = None
        self.assertIsNone(self.stub.sidebar_import_script_groups())
        self.assert_groups_unchanged()
        self.stub.save_script_groups.assert_not_called()
        self.stub.results_text.insert.assert_not_called()
        self.assert_parent_is_root()

    def test_no_clash_confirm(self):
        self.write_src([{"name": "New", "scripts": [{"query": "SELECT 1"}]}])
        self.assertEqual(self.stub.sidebar_import_script_groups(), "New")
        self.mb.askyesno.assert_called_once()
        self.mb.askyesnocancel.assert_not_called()
        self.assertEqual(names_of(self.stub.script_groups, "P1"), ["G1", "G2", "New"])
        self.stub.save_script_groups.assert_called_once_with()
        self.assert_parent_is_root()

    def test_no_clash_declined(self):
        self.write_src([{"name": "New", "scripts": [{"query": "SELECT 1"}]}])
        self.mb.askyesno.return_value = False
        self.assertIsNone(self.stub.sidebar_import_script_groups())
        self.assert_groups_unchanged()
        self.stub.save_script_groups.assert_not_called()
        self.stub.results_text.insert.assert_not_called()

    def test_imports_into_current_profile_only(self):
        self.stub.profile_combo.get.return_value = "P2"
        self.write_src({"profile": "P1", "groups": [{"name": "Z", "scripts": []}]})
        self.assertEqual(self.stub.sidebar_import_script_groups(), "Z")
        self.assertEqual(names_of(self.stub.script_groups, "P2"), ["G3", "Z"])
        self.assertEqual(names_of(self.stub.script_groups, "P1"), ["G1", "G2"])

    # R3-AC-13
    def assert_invalid(self):
        self.assertIsNone(self.stub.sidebar_import_script_groups())
        self.mb.showerror.assert_called_once()
        args, kwargs = self.mb.showerror.call_args
        self.assertEqual(args[0], "Import Groups")
        self.assertTrue(args[1].startswith(INVALID_MSG), args[1])
        self.assertIs(kwargs.get("parent"), self.root)
        self.assert_groups_unchanged()
        self.stub.save_script_groups.assert_not_called()
        self.stub.results_text.insert.assert_not_called()
        self.mb.askyesno.assert_not_called()
        self.mb.askyesnocancel.assert_not_called()

    def test_broken_json(self):
        self.write_src(raw="{not json")
        self.assert_invalid()

    def test_no_groups_list(self):
        self.write_src({"type": "script_groups", "groups": "nope"})
        self.assert_invalid()

    def test_dict_without_groups(self):
        self.write_src({"type": "script_groups"})
        self.assert_invalid()

    def test_script_without_sql(self):
        self.write_src({"groups": [{"name": "Bad", "scripts": [{"name": "x"}]}]})
        self.assert_invalid()
        self.assertIn("Bad", self.mb.showerror.call_args.args[1])

    def test_empty_file(self):
        self.write_src(raw="")
        self.assert_invalid()

    def test_no_groups_found_info(self):
        self.write_src({"groups": []})
        self.assertIsNone(self.stub.sidebar_import_script_groups())
        self.mb.showinfo.assert_called_once_with(
            "Import Groups", "No groups found in this file", parent=self.root)
        self.assert_groups_unchanged()
        self.stub.save_script_groups.assert_not_called()


class TestSidebarEnsureLoaded(unittest.TestCase):
    """R3-AC-14 via the sidebar: no script_groups attr + real store in a tempdir."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = os.path.join(self.tmp.name, "script_groups.json")
        with open(self.store, "w", encoding="utf-8") as fh:
            json.dump({"version": 1, "groups": [
                grp("Old", "P1", scripts=[{"name": "o", "query": "SELECT OLD"}]),
                grp("Other", "P2")]}, fh)
        with open(self.store, "rb") as fh:
            self.store_bytes = fh.read()
        self.stub = make_flow_stub()
        self.stub.profile_combo = mock.Mock(get=mock.Mock(return_value="P1"))
        self.stub._script_groups_path = lambda: self.store
        self.assertFalse(hasattr(self.stub, "script_groups"))
        p1 = mock.patch.object(app, "messagebox")
        p2 = mock.patch.object(app, "filedialog")
        self.mb = p1.start()
        self.fd = p2.start()
        self.addCleanup(p1.stop)
        self.addCleanup(p2.stop)

    def test_sidebar_export_loads_first(self):
        out = os.path.join(self.tmp.name, "out.json")
        self.fd.asksaveasfilename.return_value = out
        self.assertEqual(self.stub.sidebar_export_script_groups(), out)
        self.mb.showerror.assert_not_called()
        with open(out, encoding="utf-8") as fh:
            data = json.load(fh)
        self.assertEqual([g["name"] for g in data["groups"]], ["Old"])
        self.assertEqual(data["groups"][0]["scripts"], [{"name": "o", "query": "SELECT OLD"}])
        self.assertEqual([g["name"] for g in self.stub.script_groups], ["Old", "Other"])
        with open(self.store, "rb") as fh:
            self.assertEqual(fh.read(), self.store_bytes)  # store not touched

    def test_sidebar_export_loads_once(self):
        self.fd.asksaveasfilename.return_value = ""
        with mock.patch.object(app.DatabaseConnectorGUI, "load_script_groups",
                               autospec=True, return_value=[]) as load:
            self.stub.sidebar_export_script_groups()
            self.stub.sidebar_export_script_groups()
        self.assertEqual(load.call_count, 1)

    def test_sidebar_export_no_store_file(self):
        os.remove(self.store)
        self.assertIsNone(self.stub.sidebar_export_script_groups())
        self.mb.showinfo.assert_called_once_with(
            "Export Groups", "This profile has no groups to export", parent=self.stub.root)
        self.assertEqual(self.stub.script_groups, [])

    def test_sidebar_import_preserves_existing(self):
        src = os.path.join(self.tmp.name, "in.json")
        with open(src, "w", encoding="utf-8") as fh:
            json.dump({"type": "script_groups", "groups": [
                {"name": "New", "scripts": [{"query": "SELECT 9"}]}]}, fh)
        self.fd.askopenfilename.return_value = src
        self.mb.askyesno.return_value = True
        self.assertEqual(self.stub.sidebar_import_script_groups(), "New")
        self.mb.showerror.assert_not_called()
        with open(self.store, encoding="utf-8") as fh:
            saved = json.load(fh)
        self.assertEqual([(g["name"], g["profile"]) for g in saved["groups"]],
                         [("Old", "P1"), ("Other", "P2"), ("New", "P1")])
        self.assertEqual(saved["groups"][0]["scripts"], [{"name": "o", "query": "SELECT OLD"}])
        self.stub.results_text.insert.assert_called_once_with(
            app.tk.END, f"📥 Imported 1 group(s) from {src}\n")

    def test_sidebar_import_no_profile_still_loads(self):
        self.stub.profile_combo.get.return_value = ""
        self.assertIsNone(self.stub.sidebar_import_script_groups())
        self.assertEqual([g["name"] for g in self.stub.script_groups], ["Old", "Other"])
        self.fd.askopenfilename.assert_not_called()


class TestSidebarRefresh(SidebarBase):
    """R3-AC-15 via the sidebar import."""

    def setUp(self):
        super().setUp()
        self.write_src([{"name": "A", "scripts": []}, {"name": "B", "scripts": []}])

    def test_open_window_refreshed_with_last_name(self):
        cb = mock.Mock()
        self.stub._script_groups_refresh = cb
        self.stub._script_groups_window = mock.Mock(winfo_exists=lambda: True)
        order = mock.Mock()
        self.stub.save_script_groups = order.save
        cb.side_effect = lambda name: order.refresh(name)
        self.stub.results_text = order.text
        self.assertEqual(self.stub.sidebar_import_script_groups(), "B")
        cb.assert_called_once_with("B")
        self.assertIs(self.stub._script_groups_refresh, cb)
        names = [c[0] for c in order.mock_calls]
        self.assertEqual(names[:3], ["save", "refresh", "text.insert"])

    def test_closed_window_no_error_and_cleared(self):
        cb = mock.Mock()
        self.stub._script_groups_refresh = cb
        self.stub._script_groups_window = mock.Mock(winfo_exists=lambda: False)
        self.assertEqual(self.stub.sidebar_import_script_groups(), "B")
        cb.assert_not_called()
        self.assertIsNone(self.stub._script_groups_refresh)
        self.stub.save_script_groups.assert_called_once_with()

    def test_never_opened_no_error(self):
        self.assertFalse(hasattr(self.stub, "_script_groups_refresh"))
        self.assertEqual(self.stub.sidebar_import_script_groups(), "B")
        self.stub.results_text.insert.assert_called_once()

    def test_reimport_after_close(self):
        cb = mock.Mock()
        self.stub._script_groups_refresh = cb
        win = mock.Mock()
        win.winfo_exists.return_value = True
        self.stub._script_groups_window = win
        self.stub.sidebar_import_script_groups()
        cb.assert_called_once_with("B")
        win.winfo_exists.return_value = False  # user closed the window
        self.mb.askyesnocancel.return_value = False  # clashes now -> keep both
        self.assertEqual(self.stub.sidebar_import_script_groups(), "B (2)")
        cb.assert_called_once()  # not called again
        self.assertIsNone(self.stub._script_groups_refresh)

    def test_not_called_when_import_cancelled(self):
        cb = mock.Mock()
        self.stub._script_groups_refresh = cb
        self.stub._script_groups_window = mock.Mock(winfo_exists=lambda: True)
        self.mb.askyesno.return_value = False
        self.stub.sidebar_import_script_groups()
        cb.assert_not_called()

    def test_export_never_refreshes(self):
        cb = mock.Mock()
        self.stub._script_groups_refresh = cb
        self.stub._script_groups_window = mock.Mock(winfo_exists=lambda: True)
        self.stub.sidebar_export_script_groups()
        cb.assert_not_called()


class TestSidebarRowSource(unittest.TestCase):
    """R3-AC-16 (code part): new row under Preset Save/Load wired to sidebar handlers."""

    @classmethod
    def setUpClass(cls):
        import inspect
        cls.src = inspect.getsource(app.DatabaseConnectorGUI.__init__)

    def test_row_frame_in_presets(self):
        self.assertRegex(self.src, r'groups_io = tk\.Frame\(presets, bg=UI\["surface"\]\)')
        self.assertIn("groups_io.pack(", self.src)

    def test_buttons_wired_to_sidebar_handlers(self):
        self.assertRegex(
            self.src,
            r'_ghost\(\s*groups_io,\s*"⇧  Import Groups",\s*self\.sidebar_import_script_groups,'
            r'\s*bg=UI\["surface"\]\s*\)\.pack\(side="left"\)')
        self.assertRegex(
            self.src,
            r'_ghost\(\s*groups_io,\s*"⇩  Export Groups",\s*self\.sidebar_export_script_groups,'
            r'\s*bg=UI\["surface"\]\s*\)\.pack\(side="left"\)')

    def test_order_below_save_load_before_presets_pack(self):
        s = self.src
        inner_pack = s.index("presets_inner.pack(")
        save = s.index('"💾  Save"')
        load = s.index('"📂  Load"')
        row = s.index("groups_io = tk.Frame(")
        imp = s.index('"⇧  Import Groups"')
        exp = s.index('"⇩  Export Groups"')
        presets_pack = s.index("presets.pack(")
        self.assertLess(inner_pack, save)
        self.assertLess(save, load)
        self.assertLess(load, row)
        self.assertLess(row, imp)
        self.assertLess(imp, exp)
        self.assertLess(exp, presets_pack)

    def test_save_load_row_untouched(self):
        self.assertIn('_ghost(presets_inner, "💾  Save", self.save_preset_dialog, bg=UI["surface"])',
                      self.src)
        self.assertIn('_ghost(presets_inner, "📂  Load", self.load_preset_dialog, bg=UI["surface"])',
                      self.src)
        # the new buttons are not in the Save/Load row
        self.assertNotRegex(self.src, r"_ghost\(\s*presets_inner,\s*\"[⇧⇩]")

    def test_each_button_once_in_init(self):
        self.assertEqual(self.src.count('"⇧  Import Groups"'), 1)
        self.assertEqual(self.src.count('"⇩  Export Groups"'), 1)


class TestSidebarRowBuild(unittest.TestCase):
    """Build the real main window (withdrawn) with APP_DIR in a tempdir.

    Skipped when Tk cannot start (no display). The root is always destroyed.
    """

    def test_row_built_below_save_load(self):
        try:
            root = app.tk.Tk()
        except app.tk.TclError as e:  # pragma: no cover - no display
            self.skipTest(f"Tk not available: {e}")
        try:
            root.withdraw()
            with tempfile.TemporaryDirectory() as tmp, \
                    mock.patch.object(app, "APP_DIR", tmp), \
                    mock.patch.object(app, "messagebox"), \
                    mock.patch.object(app.DatabaseConnectorGUI, "sidebar_import_script_groups",
                                      autospec=True, return_value=None) as imp, \
                    mock.patch.object(app.DatabaseConnectorGUI, "sidebar_export_script_groups",
                                      autospec=True, return_value=None) as exp:
                gui = app.DatabaseConnectorGUI(root)
                root.update_idletasks()
                found = {}

                def walk(w):
                    for c in w.winfo_children():
                        try:
                            text = c.cget("text")
                        except Exception:
                            text = None
                        if isinstance(text, str) and text in (
                                "💾  Save", "📂  Load", "⇧  Import Groups", "⇩  Export Groups"):
                            found.setdefault(text, []).append(c)
                        walk(c)

                walk(root)
                for t in ("💾  Save", "📂  Load", "⇧  Import Groups", "⇩  Export Groups"):
                    self.assertIn(t, found)
                imp_btns = found["⇧  Import Groups"]
                exp_btns = found["⇩  Export Groups"]
                # only one sidebar pair (the Script Groups dialog is not open)
                self.assertEqual(len(imp_btns), 1)
                self.assertEqual(len(exp_btns), 1)
                imp_btn, exp_btn = imp_btns[0], exp_btns[0]
                save_btn = next(b for b in found["💾  Save"]
                                if any(b.master is l.master for l in found["📂  Load"]))
                row = imp_btn.master
                self.assertIs(exp_btn.master, row)
                self.assertIsNot(row, save_btn.master)
                presets = save_btn.master.master
                self.assertIs(row.master, presets)
                packed = presets.pack_slaves()
                self.assertIn(row, packed)
                self.assertLess(packed.index(save_btn.master), packed.index(row))
                row_slaves = row.pack_slaves()
                self.assertLess(row_slaves.index(imp_btn), row_slaves.index(exp_btn))
                self.assertEqual(imp_btn.winfo_class(), save_btn.winfo_class())
                self.assertEqual(str(imp_btn.cget("style")).split(".")[1:],
                                 str(save_btn.cget("style")).split(".")[1:])
                imp_btn.invoke()
                imp.assert_called_once_with(gui)
                exp.assert_not_called()
                exp_btn.invoke()
                exp.assert_called_once_with(gui)
                # nothing written to the real app folder: APP_DIR is the tempdir
        finally:
            try:
                root.destroy()
            except app.tk.TclError:
                pass


class TestScriptGroupsDialogCallbackLifecycle(unittest.TestCase):
    """The refresh callback belongs to the dialog, not its child widgets."""

    def test_callback_survives_child_destroy_and_resets_between_dialogs(self):
        try:
            root = app.tk.Tk()
        except app.tk.TclError as e:  # pragma: no cover - no display
            self.skipTest(f"Tk not available: {e}")
        try:
            root.withdraw()
            with tempfile.TemporaryDirectory() as tmp, \
                    mock.patch.object(app, "APP_DIR", tmp), \
                    mock.patch.object(app, "messagebox"):
                gui = app.DatabaseConnectorGUI(root)
                root.update_idletasks()

                gui.show_script_groups_dialog()
                dialog_a = gui._script_groups_window
                callback_a = gui._script_groups_refresh
                self.assertIsNotNone(callback_a)

                children = dialog_a.winfo_children()
                self.assertTrue(children)
                children[0].destroy()
                self.assertIs(gui._script_groups_refresh, callback_a)

                dialog_a.destroy()
                self.assertIsNone(gui._script_groups_refresh)

                gui.show_script_groups_dialog()
                dialog_b = gui._script_groups_window
                callback_b = gui._script_groups_refresh
                self.assertIsNotNone(callback_b)
                self.assertIsNot(callback_b, callback_a)

                dialog_b.destroy()
                self.assertIsNone(gui._script_groups_refresh)
        finally:
            try:
                root.destroy()
            except app.tk.TclError:
                pass


if __name__ == "__main__":
    unittest.main()
