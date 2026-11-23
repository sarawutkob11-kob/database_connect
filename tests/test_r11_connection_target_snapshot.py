"""R11-T2: header target + Tables use the connection snapshot (bug B4).

R11-AC-1 .. R11-AC-20. No Tk window, no real database: the GUI is a stub from
DatabaseConnectorGUI.__new__, labels / entries / buttons are fakes, threading.
Thread is captured and run by hand, create_engine / inspect / messagebox /
ui_dialog / print are patched. Nothing outside cp874 is printed to stdout.
"""

import ast
import dataclasses
import inspect as pyinspect
import os
import sys
import textwrap
import threading
import unittest
from typing import Any, Dict, List, Optional
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import database_connect_gui as app  # noqa: E402

GUI = app.DatabaseConnectorGUI
ConnectionInfo = app.ConnectionInfo
RunTarget = app.RunTarget
MUTED = app.UI["muted"]
WARN = app.UI["warn"]

UAT_PW = "S3cr3t-UAT"
PROD_PW = "S3cr3t-PROD"
FIELDS = ("db_type", "db_user", "db_password", "db_host", "db_port", "db_name")

# "snapshot UAT" / "screen PROD" from spec R11-4
UAT_INFO = ConnectionInfo(
    profile="P1", db_type="PostgreSQL", user="app", host="uat-db", port="5432",
    database="UAT",
)
UAT_SCREEN = dict(
    db_type="PostgreSQL", db_user="app", db_password=UAT_PW, db_host="uat-db",
    db_port="5432", db_name="UAT",
)
PROD_SCREEN = dict(UAT_SCREEN, db_host="prod-db", db_name="PROD")

# "all databases" snapshot of R11-AC-11
MYSQL_ALL_INFO = ConnectionInfo(
    profile="P1", db_type="MySQL", user="app", host="uat-db", port="3306", database="",
)
MYSQL_PROD_SCREEN = dict(
    db_type="MySQL", db_user="other", db_password="pw-prod", db_host="prod-db",
    db_port="9999", db_name="",
)


# ---------------------------------------------------------------- fakes
class _Entry:
    """Entry / StringVar / Combobox: records every get(), can forbid get()."""

    def __init__(self, name: str, value: str, log: List[str]) -> None:
        self.name = name
        self.value = value
        self.log = log
        self.forbid_get = False

    def get(self, *_a):
        if self.forbid_get:
            raise AssertionError(f"read the Details field {self.name}")
        self.log.append(self.name)
        return self.value

    def set(self, value):
        self.value = value

    def delete(self, *_a):
        self.value = ""

    def insert(self, _i, value):
        self.value = value


class _Label:
    """Header label: remembers text / fg and every config() call."""

    def __init__(self, text: str = "", fg: str = MUTED, closed: bool = False) -> None:
        self.text = text
        self.fg = fg
        self.closed = closed
        self.config_calls: List[Dict[str, Any]] = []

    def cget(self, key):
        return {"text": self.text, "fg": self.fg}[key]

    def config(self, **kw):
        if self.closed:
            raise app.tk.TclError('invalid command name ".!label"')
        self.config_calls.append(kw)
        self.text = kw.get("text", self.text)
        self.fg = kw.get("fg", self.fg)

    configure = config


class _ClosedLabel(_Label):
    """Window destroyed: every Tk call raises TclError."""

    def cget(self, key):
        raise app.tk.TclError('invalid command name ".!label"')

    def config(self, **kw):
        raise app.tk.TclError('invalid command name ".!label"')


class _Button:
    def __init__(self, text="", state="normal"):
        self.text = text
        self.state = state
        self.config_calls: List[Dict[str, Any]] = []

    def cget(self, key):
        return self.text if key == "text" else self.state

    def __getitem__(self, key):
        return self.cget(key)

    def config(self, **kw):
        self.config_calls.append(kw)
        self.state = kw.get("state", self.state)
        self.text = kw.get("text", self.text)

    configure = config


class _Text:
    def __init__(self):
        self.inserted: List[str] = []

    def insert(self, _i, value):
        self.inserted.append(value)

    def see(self, *_a):
        pass

    def delete(self, *_a):
        pass


class _Thread:
    def __init__(self, target, args=(), daemon=None):
        self.target = target
        self.args = args
        self.started = False

    def start(self):
        self.started = True

    def run(self):
        self.target(*self.args)


def make_stub(screen: Optional[Dict[str, str]] = None, profile: str = "P1"):
    screen = dict(UAT_SCREEN if screen is None else screen)
    stub = GUI.__new__(GUI)
    stub._reads = []
    stub._active_db_lock = threading.Lock()
    stub._active_db_connections = {}
    stub._running_job_ids = set()
    stub._batch_running = False
    stub.execute_btn = _Button("▶  Run", "disabled")
    stub.export_excel_btn = _Button("Export")
    stub.inspect_btn = _Button("Tables", "disabled")
    stub.status_label = _Button("")
    stub.results_text = _Text()
    stub.profile_combo = _Entry("profile_combo", profile, stub._reads)
    for name in FIELDS:
        setattr(stub, name, _Entry(name, screen[name], stub._reads))
    stub.engine = None
    stub._run_target = None
    stub.root = mock.Mock(name="root")
    stub._block_if_busy = mock.Mock(return_value=False)
    stub._track_engine_connections = mock.Mock()
    stub._show_connection_error = mock.Mock()
    stub._write_run_log = mock.Mock()
    stub._create_list_tables_loading_dialog = mock.Mock(return_value=mock.Mock(name="dlg"))
    stub.on_list_tables_success = mock.Mock()
    stub.on_list_tables_error = mock.Mock()
    return stub


def set_screen(stub, screen: Dict[str, str]) -> None:
    for name in FIELDS:
        getattr(stub, name).value = screen[name]


def set_snapshot(stub, info: ConnectionInfo = UAT_INFO, password: Optional[str] = None,
                 engine: Any = None):
    """Snapshot without connect_database. With a password it goes through
    _replace_engine (no knowledge of how the password is stored); without one
    the attributes are set directly so `_connected_password` stays absent."""
    engine = engine if engine is not None else mock.MagicMock(name="engine_uat")
    if password is not None:
        stub._replace_engine(engine, info, password=password)
    else:
        stub.engine = engine
        stub._run_target = RunTarget(engine, info)
    return engine


def db_list_engine(names, name="engine_uat"):
    engine = mock.MagicMock(name=name)
    conn = engine.connect.return_value.__enter__.return_value
    conn.execute.return_value = [(n,) for n in names]
    return engine, conn


def connect(stub, engine=None, fail=False, refused=False):
    """Real connect_database with create_engine / messagebox patched."""
    if fail:
        kw = dict(side_effect=RuntimeError("cannot reach server"))
    else:
        kw = dict(return_value=engine if engine is not None else mock.MagicMock(name="eng"))
    with mock.patch.object(app, "create_engine", **kw), \
            mock.patch.object(app, "messagebox") as mb:
        stub.connect_database()
    if not fail and not refused:
        mb.showerror.assert_not_called()
    return mb


# ---------------------------------------------------------------- header
class HeaderTests(unittest.TestCase):
    def _header(self, stub, main=None, sub=None):
        main = main or _Label()
        sub = sub or _Label()
        result = stub._update_target_summary(main, sub)
        self.assertIs(result, True)
        return main, sub

    def assert_no_warning(self, main, sub):
        self.assertNotIn("⚠", main.text)
        self.assertNotIn("⚠", sub.text)
        self.assertEqual(sub.fg, MUTED)

    def assert_warning(self, main, sub):
        self.assertIn("⚠", sub.text)
        self.assertIn("Connect", sub.text)
        self.assertEqual(sub.fg, WARN)
        self.assertNotEqual(sub.fg, MUTED)
        self.assertNotIn("⚠", main.text)
        for call in main.config_calls:
            self.assertNotIn("fg", call)  # target_main keeps its colour

    # R11-AC-1
    def test_ac1_not_connected_shows_screen_fields_stripped(self):
        stub = make_stub(dict(
            db_type="PostgreSQL", db_user="  app ", db_password="x", db_host=" h1 ",
            db_port=" 5432 ", db_name=" sales ",
        ))
        main, sub = self._header(stub)
        self.assertEqual(main.text, "PostgreSQL · app@h1:5432")
        self.assertEqual(sub.text, "Database / Service: sales")
        self.assert_no_warning(main, sub)

    def test_ac1_not_connected_empty_port_and_database(self):
        stub = make_stub(dict(UAT_SCREEN, db_port="  ", db_name=""))
        main, sub = self._header(stub)
        self.assertEqual(main.text, "PostgreSQL · app@uat-db")
        self.assertEqual(sub.text, "Database: (default)")
        self.assert_no_warning(main, sub)

    # R11-AC-2
    def test_ac2_snapshot_matching_screen_old_format_no_warning(self):
        stub = make_stub(UAT_SCREEN)
        set_snapshot(stub, password=UAT_PW)
        main, sub = self._header(stub)
        self.assertEqual(main.text, "PostgreSQL · app@uat-db:5432")
        self.assertEqual(sub.text, "Database / Service: UAT")
        self.assert_no_warning(main, sub)
        for call in sub.config_calls:
            self.assertNotIn("fg", call)  # already muted -> no fg config

    def test_ac2_snapshot_all_databases_default_text(self):
        info = dataclasses.replace(UAT_INFO, database="", port="")
        stub = make_stub(dict(UAT_SCREEN, db_port="", db_name=""))
        set_snapshot(stub, info, password=UAT_PW)
        main, sub = self._header(stub)
        self.assertEqual(main.text, "PostgreSQL · app@uat-db")
        self.assertEqual(sub.text, "Database: (default)")
        self.assert_no_warning(main, sub)

    # R11-AC-3
    def test_ac3_prod_screen_shows_snapshot_and_warning(self):
        stub = make_stub(PROD_SCREEN)
        set_snapshot(stub, password=UAT_PW)
        main, sub = self._header(stub)
        self.assertEqual(main.text, "PostgreSQL · app@uat-db:5432")
        self.assertTrue(sub.text.startswith("Database / Service: UAT"))
        self.assertEqual(sub.text, "Database / Service: UAT" + app._TARGET_MISMATCH_NOTE)
        for label in (main, sub):
            self.assertNotIn("prod-db", label.text)
            self.assertNotIn("PROD", label.text)
        self.assert_warning(main, sub)

    def test_ac3_through_the_real_init_closure(self):
        stub = make_stub(PROD_SCREEN)
        set_snapshot(stub, password=UAT_PW)
        main, sub = _Label(), _Label()
        refresh = _build_refresh_target_summary(stub, main, sub)
        refresh()
        self.assertEqual(main.text, "PostgreSQL · app@uat-db:5432")
        self.assertNotIn("prod-db", main.text)
        self.assertNotIn("PROD", sub.text)
        self.assertIn("UAT", sub.text)
        self.assert_warning(main, sub)
        stub.root.after.assert_called_once_with(500, refresh)

    # R11-AC-4
    def test_ac4_each_target_field_counts(self):
        changes = dict(
            db_type="MySQL", db_user="other", db_host="prod-db", db_port="6543",
            db_name="PROD",
        )
        for field, value in changes.items():
            with self.subTest(field=field):
                stub = make_stub(dict(UAT_SCREEN, **{field: value}))
                set_snapshot(stub, password=UAT_PW)
                main, sub = self._header(stub)
                self.assertEqual(main.text, "PostgreSQL · app@uat-db:5432")
                self.assert_warning(main, sub)
                self.assertNotIn(value, main.text)

    def test_ac4_password_change_does_not_count_and_is_not_read(self):
        stub = make_stub(dict(UAT_SCREEN, db_password="another-password"))
        set_snapshot(stub, password=UAT_PW)
        main, sub = self._header(stub)
        self.assert_no_warning(main, sub)
        self.assertNotIn("db_password", stub._reads)

    def test_ac4_profile_change_does_not_count_and_is_not_read(self):
        stub = make_stub(UAT_SCREEN, profile="P2")
        set_snapshot(stub, password=UAT_PW)
        main, sub = self._header(stub)
        self.assert_no_warning(main, sub)
        self.assertNotIn("profile_combo", stub._reads)

    # R11-AC-5
    def test_ac5_whitespace_and_port_suffix_do_not_count(self):
        cases = dict(
            host_spaces=dict(db_host=" uat-db "),
            port_suffix=dict(db_port="5432:x"),
            port_spaces_suffix=dict(db_port=" 5432:1521 "),
            all_spaces=dict(db_type=" PostgreSQL ", db_user=" app ", db_host="  uat-db",
                            db_port="5432 ", db_name=" UAT "),
        )
        for name, change in cases.items():
            with self.subTest(case=name):
                stub = make_stub(dict(UAT_SCREEN, **change))
                set_snapshot(stub, password=UAT_PW)
                main, sub = self._header(stub)
                self.assertEqual(main.text, "PostgreSQL · app@uat-db:5432")
                self.assertEqual(sub.text, "Database / Service: UAT")
                self.assert_no_warning(main, sub)

    def test_ac5_space_before_port_suffix_at_connect_does_not_warn(self):
        # Port "5432 :x" at Connect is stored as "5432 " (strip, then split)
        info = dataclasses.replace(UAT_INFO, port="5432 ")
        for screen_port in ("5432 :x", "5432", " 5432 "):
            with self.subTest(screen_port=screen_port):
                stub = make_stub(dict(UAT_SCREEN, db_port=screen_port))
                set_snapshot(stub, info, password=UAT_PW)
                main, sub = self._header(stub)
                self.assert_no_warning(main, sub)

    def test_ac5_comparison_is_case_sensitive(self):
        stub = make_stub(dict(UAT_SCREEN, db_host="UAT-DB"))
        set_snapshot(stub, password=UAT_PW)
        main, sub = self._header(stub)
        self.assert_warning(main, sub)

    # R11-AC-6
    def test_ac6a_fixing_the_fields_clears_warning(self):
        stub = make_stub(PROD_SCREEN)
        set_snapshot(stub, password=UAT_PW)
        main, sub = self._header(stub)
        self.assert_warning(main, sub)
        set_screen(stub, UAT_SCREEN)
        self._header(stub, main, sub)
        self.assertEqual(sub.text, "Database / Service: UAT")
        self.assert_no_warning(main, sub)

    def test_ac6b_new_connect_uses_new_values(self):
        stub = make_stub(PROD_SCREEN)
        set_snapshot(stub, password=UAT_PW)
        main, sub = self._header(stub)
        self.assert_warning(main, sub)
        connect(stub)
        self._header(stub, main, sub)
        self.assertEqual(main.text, "PostgreSQL · app@prod-db:5432")
        self.assertEqual(sub.text, "Database / Service: PROD")
        self.assert_no_warning(main, sub)

    # R11-AC-7
    def test_ac7_failed_connect_falls_back_to_fields(self):
        stub = make_stub(PROD_SCREEN)
        set_snapshot(stub, password=UAT_PW)
        main, sub = self._header(stub)
        connect(stub, fail=True)
        self._header(stub, main, sub)
        self.assertEqual(main.text, "PostgreSQL · app@prod-db:5432")
        self.assertEqual(sub.text, "Database / Service: PROD")
        self.assert_no_warning(main, sub)

    def test_ac7_profile_reset_falls_back_to_fields(self):
        stub = make_stub(PROD_SCREEN)
        engine = set_snapshot(stub, password=UAT_PW)
        stub.execute_btn.state = "normal"
        main, sub = self._header(stub)
        stub._reset_profile_connection_state(engine)
        self.assertIsNone(stub.engine)
        self._header(stub, main, sub)
        self.assertEqual(main.text, "PostgreSQL · app@prod-db:5432")
        self.assertEqual(sub.text, "Database / Service: PROD")
        self.assert_no_warning(main, sub)

    # R11-AC-8
    def test_ac8_engine_without_info_uses_fields(self):
        stub = make_stub(PROD_SCREEN)
        engine = mock.MagicMock(name="engine")
        stub.engine = engine
        stub._run_target = RunTarget(engine, None)
        main, sub = self._header(stub)
        self.assertEqual(main.text, "PostgreSQL · app@prod-db:5432")
        self.assertEqual(sub.text, "Database / Service: PROD")
        self.assert_no_warning(main, sub)

    def test_ac8_stale_run_target_of_other_engine_uses_fields(self):
        stub = make_stub(PROD_SCREEN)
        set_snapshot(stub, password=UAT_PW)
        stub.engine = mock.MagicMock(name="set_directly")
        main, sub = self._header(stub)
        self.assertIn("prod-db", main.text)
        self.assert_no_warning(main, sub)

    # R11-AC-9
    def test_ac9_closed_labels_return_false_without_raising(self):
        for label_cls in (_ClosedLabel, lambda: _Label(closed=True)):
            with self.subTest(label=label_cls):
                stub = make_stub(PROD_SCREEN)
                set_snapshot(stub, password=UAT_PW)
                self.assertIs(stub._update_target_summary(label_cls(), label_cls()), False)

    def test_ac9_closure_stops_polling_when_window_closed(self):
        for connected in (False, True):
            with self.subTest(connected=connected):
                stub = make_stub(PROD_SCREEN)
                if connected:
                    set_snapshot(stub, password=UAT_PW)
                refresh = _build_refresh_target_summary(stub, _ClosedLabel(), _ClosedLabel())
                refresh()  # must not raise
                stub.root.after.assert_not_called()

    def test_ac9_closure_reschedules_every_500ms(self):
        stub = make_stub(UAT_SCREEN)
        set_snapshot(stub, password=UAT_PW)
        refresh = _build_refresh_target_summary(stub, _Label(), _Label())
        refresh()
        stub.root.after.assert_called_once_with(500, refresh)

    def test_ac9_no_config_when_nothing_changed(self):
        for screen in (UAT_SCREEN, PROD_SCREEN):
            for connected in (False, True):
                with self.subTest(prod=screen is PROD_SCREEN, connected=connected):
                    stub = make_stub(screen)
                    if connected:
                        set_snapshot(stub, password=UAT_PW)
                    main, sub = self._header(stub)
                    first = (len(main.config_calls), len(sub.config_calls))
                    self._header(stub, main, sub)
                    self._header(stub, main, sub)
                    self.assertEqual(
                        (len(main.config_calls), len(sub.config_calls)), first
                    )

    def test_ac9_warning_colour_set_once_then_restored_once(self):
        stub = make_stub(PROD_SCREEN)
        set_snapshot(stub, password=UAT_PW)
        main, sub = self._header(stub)
        fg_calls = [c for c in sub.config_calls if "fg" in c]
        self.assertEqual(fg_calls, [{"fg": WARN}])
        set_screen(stub, UAT_SCREEN)
        self._header(stub, main, sub)
        fg_calls = [c for c in sub.config_calls if "fg" in c]
        self.assertEqual(fg_calls, [{"fg": WARN}, {"fg": MUTED}])


def _build_refresh_target_summary(stub, target_main, target_sub):
    """The real closure from GUI.__init__ (same approach as test_running_banner)."""
    tree = ast.parse(textwrap.dedent(pyinspect.getsource(GUI.__init__)))
    found = [n for n in ast.walk(tree)
             if isinstance(n, ast.FunctionDef) and n.name == "_refresh_target_summary"]
    assert len(found) == 1
    factory = ast.parse(
        "def _factory(self, target_main, target_sub):\n    return _refresh_target_summary\n"
    )
    factory.body[0].body.insert(0, found[0])
    ast.fix_missing_locations(factory)
    namespace: dict = {}
    exec(compile(factory, "<_refresh_target_summary>", "exec"), vars(app).copy(), namespace)
    return namespace["_factory"](stub, target_main, target_sub)


# ---------------------------------------------------------------- Run (AC-10)
class ExecuteQueryRegressionTests(unittest.TestCase):
    def _stub(self, sql):
        stub = make_stub(PROD_SCREEN)
        engine = set_snapshot(stub, password=UAT_PW)
        stub.sql_context = mock.Mock()
        stub.sql_context.get.return_value = sql
        stub._prepare_run_sql = mock.Mock(side_effect=lambda jobs: [j["query"] for j in jobs])
        stub._start_stoppable_run = mock.Mock()
        stub._create_loading_dialog_with_retry = mock.Mock()
        stub.debug_mode = mock.Mock()
        stub.debug_mode.get.return_value = False
        stub._execute_query_background = mock.Mock()
        return stub, engine

    def test_ac10_select_runs_on_snapshot_engine_without_dialog_or_block(self):
        stub, engine = self._stub("SELECT 1")
        with mock.patch.object(app, "ui_dialog") as dlg, \
                mock.patch.object(app, "messagebox") as mb:
            stub.execute_query()
        dlg.assert_not_called()
        mb.showerror.assert_not_called()
        stub._execute_query_background.assert_called_once()
        self.assertIs(stub._execute_query_background.call_args.kwargs["engine"], engine)
        self.assertFalse(any("⛔" in t for t in stub.results_text.inserted))

    def test_ac10_delete_dialog_still_shows_snapshot_destination(self):
        stub, engine = self._stub("DELETE FROM t")
        with mock.patch.object(app, "ui_dialog", return_value=True) as dlg, \
                mock.patch.object(app, "messagebox"):
            stub.execute_query()
        dlg.assert_called_once()
        message = dlg.call_args.kwargs["message"]
        self.assertIn("PostgreSQL · uat-db / UAT", message)
        self.assertNotIn("prod-db", message)
        self.assertIs(stub._execute_query_background.call_args.kwargs["engine"], engine)


# ---------------------------------------------------------------- list_tables
class _ListTablesBase(unittest.TestCase):
    def setUp(self):
        self.prints: List[str] = []

    def start(self, stub):
        threads: List[_Thread] = []

        def make_thread(target, args=(), daemon=None):
            thread = _Thread(target, args, daemon)
            threads.append(thread)
            return thread

        with mock.patch.object(app.threading, "Thread", side_effect=make_thread), \
                mock.patch.object(app, "messagebox") as mb, \
                mock.patch("builtins.print", side_effect=self._capture_print):
            stub.list_tables()
        self.messagebox = mb
        return threads

    def _capture_print(self, *args, **_kw):
        self.prints.append(" ".join(str(a) for a in args))

    def run_worker(self, stub, thread, inspector=None, temp_engine=None):
        inspector = inspector if inspector is not None else mock.Mock(name="inspector")
        if inspector.get_schema_names._mock_return_value is mock.DEFAULT \
                and inspector.get_schema_names.side_effect is None:
            inspector.get_schema_names.return_value = []
        temp_engine = temp_engine or mock.MagicMock(name="temp_engine")
        with mock.patch.object(app, "create_engine", return_value=temp_engine) as ce, \
                mock.patch.object(app, "inspect", return_value=inspector) as insp, \
                mock.patch("builtins.print", side_effect=self._capture_print), \
                mock.patch("traceback.print_exc"):
            thread.run()
        for call in list(stub.root.after.call_args_list):
            if call.args and call.args[0] == 0:
                call.args[1]()
        stub.on_list_tables_error.assert_not_called()
        stub.on_list_tables_success.assert_called_once()
        return ce, insp

    def success(self, stub):
        args = stub.on_list_tables_success.call_args.args
        return args[0], args[2]  # table_list, flag


class ListTablesSnapshotTests(_ListTablesBase):
    def _mysql_all(self, password="pw-uat", screen=None):
        stub = make_stub(MYSQL_PROD_SCREEN if screen is None else screen)
        engine, conn = db_list_engine(["d1", "d2"])
        set_snapshot(stub, MYSQL_ALL_INFO, password=password, engine=engine)
        stub.get_connection_string = mock.Mock(side_effect=lambda *a: f"cs-{a[-1]}")
        stub.get_connect_args = mock.Mock(return_value={})
        return stub, engine, conn

    # R11-AC-11
    def test_ac11_per_database_engines_use_snapshot_and_stored_password(self):
        stub, engine, conn = self._mysql_all()
        threads = self.start(stub)
        self.assertEqual(len(threads), 1)
        self.assertTrue(threads[0].started)
        ce, _insp = self.run_worker(stub, threads[0])
        self.assertEqual(stub.get_connection_string.call_args_list, [
            mock.call("MySQL", "app", "pw-uat", "uat-db", "3306", "d1"),
            mock.call("MySQL", "app", "pw-uat", "uat-db", "3306", "d2"),
        ])
        self.assertEqual(ce.call_count, 2)
        self.assertIn("SHOW DATABASES", str(conn.execute.call_args.args[0]))
        for call in stub.get_connection_string.call_args_list:
            for screen_value in ("prod-db", "other", "9999", "pw-prod"):
                self.assertNotIn(screen_value, call.args)

    # R11-AC-12
    def test_ac12_all_databases_path_from_snapshot_even_if_screen_has_db(self):
        stub, engine, _conn = self._mysql_all(screen=dict(MYSQL_PROD_SCREEN, db_name="PROD"))
        threads = self.start(stub)
        ce, insp = self.run_worker(stub, threads[0])
        engine.connect.assert_called()
        self.assertEqual(ce.call_count, 2)
        tables, flag = self.success(stub)
        self.assertIs(flag, False)

    def test_ac12_current_database_path_from_snapshot_even_if_screen_empty(self):
        stub = make_stub(dict(PROD_SCREEN, db_name=""))
        engine = set_snapshot(stub)  # current-db path: no password needed
        stub.get_connection_string = mock.Mock()
        inspector = mock.Mock(name="inspector")
        inspector.get_schema_names.return_value = ["public", "information_schema"]
        inspector.get_table_names.return_value = ["t1", "t2"]
        threads = self.start(stub)
        self.assertEqual(len(threads), 1)
        ce, insp = self.run_worker(stub, threads[0], inspector=inspector)
        ce.assert_not_called()
        stub.get_connection_string.assert_not_called()
        insp.assert_called_once_with(engine)
        tables, flag = self.success(stub)
        self.assertIs(flag, True)
        self.assertEqual(tables, [
            {"Database": "UAT", "Schema": "public", "Table": "t1"},
            {"Database": "UAT", "Schema": "public", "Table": "t2"},
        ])

    # R11-AC-13
    def test_ac13_no_details_field_is_read(self):
        for case in ("all_databases", "current_database"):
            with self.subTest(case=case):
                if case == "all_databases":
                    stub, _engine, _conn = self._mysql_all()
                    inspector = None
                else:
                    stub = make_stub(PROD_SCREEN)
                    set_snapshot(stub)
                    inspector = mock.Mock()
                    inspector.get_schema_names.return_value = ["s"]
                    inspector.get_table_names.return_value = ["t"]
                for name in FIELDS:
                    getattr(stub, name).forbid_get = True
                threads = self.start(stub)
                self.assertEqual(len(threads), 1)
                self.run_worker(stub, threads[0], inspector=inspector)
                self.assertEqual([r for r in stub._reads if r in FIELDS], [])

    # R11-AC-14
    def test_ac14_values_captured_before_start_survive_a_new_connect(self):
        stub, _engine, _conn = self._mysql_all()
        threads = self.start(stub)
        self.assertEqual(threads[0].args, (("app", "pw-uat", "uat-db", "3306"),))
        # after start: Connect to another server with another password
        set_screen(stub, dict(MYSQL_PROD_SCREEN, db_password="pw-new", db_name=""))
        new_engine, _ = db_list_engine(["zzz"], name="engine_new")
        connect(stub, engine=new_engine)
        self.assertIs(stub.engine, new_engine)
        stub.get_connection_string.reset_mock()
        self.run_worker(stub, threads[0])
        self.assertEqual(stub.get_connection_string.call_args_list, [
            mock.call("MySQL", "app", "pw-uat", "uat-db", "3306", "d1"),
            mock.call("MySQL", "app", "pw-uat", "uat-db", "3306", "d2"),
        ])
        new_engine.connect.assert_called_once()  # only connect_database's SELECT 1

    # R11-AC-15
    def test_ac15_oracle_all_schemas_uses_engine_without_password(self):
        stub = make_stub(dict(MYSQL_PROD_SCREEN, db_name="PROD"))
        info = ConnectionInfo("P1", "Oracle", "scott", "uat-db", "1521", "")
        engine, conn = db_list_engine(["SCOTT"])
        set_snapshot(stub, info, password=None, engine=engine)
        stub.get_connection_string = mock.Mock()
        inspector = mock.Mock()
        inspector.get_schema_names.return_value = []
        inspector.get_table_names.return_value = ["EMP"]
        threads = self.start(stub)
        self.assertEqual(len(threads), 1)
        ce, insp = self.run_worker(stub, threads[0], inspector=inspector)
        ce.assert_not_called()
        stub.get_connection_string.assert_not_called()
        insp.assert_called_once_with(engine)
        self.assertIn("all_users", str(conn.execute.call_args.args[0]))
        tables, flag = self.success(stub)
        self.assertEqual(tables, [{"Database": "SCOTT", "Schema": "SCOTT", "Table": "EMP"}])
        self.assertIs(flag, False)
        self.assertFalse(any("⛔" in t for t in stub.results_text.inserted))

    # R11-AC-16
    def test_ac16_no_stored_password_blocks_before_anything_starts(self):
        cases = ("no_attribute", "none", "other_engine")
        for case in cases:
            with self.subTest(case=case):
                stub, engine, _conn = self._mysql_all(password=None)
                if case == "none":
                    stub._connected_password = None
                elif case == "other_engine":
                    stub._connected_password = (mock.MagicMock(name="old"), "pw-old")
                else:
                    self.assertFalse(hasattr(stub, "_connected_password"))
                for name in FIELDS:
                    getattr(stub, name).forbid_get = True
                inspect_before = (stub.inspect_btn.text, stub.inspect_btn.state)
                with mock.patch.object(app, "create_engine") as ce, \
                        mock.patch.object(app, "inspect") as insp:
                    threads = self.start(stub)
                self.assertEqual(threads, [])
                ce.assert_not_called()
                insp.assert_not_called()
                stub.get_connection_string.assert_not_called()
                engine.connect.assert_not_called()
                self.assertEqual(len(stub.results_text.inserted), 1)
                line = stub.results_text.inserted[0]
                self.assertTrue(line.startswith("⛔ Tables ไม่ได้เริ่มงาน"), line.encode())
                self.assertIn("Connect", line)
                self.assertTrue(line.endswith("\n"))
                self.assertNotIn("pw-old", line)
                self.assertEqual(stub.inspect_btn.config_calls, [])
                self.assertEqual((stub.inspect_btn.text, stub.inspect_btn.state),
                                 inspect_before)
                stub._create_list_tables_loading_dialog.assert_not_called()
                stub.root.update.assert_not_called()
                self.messagebox.showerror.assert_not_called()
                self.assertEqual([r for r in stub._reads if r in FIELDS], [])

    def test_ac16_block_is_only_for_all_databases_non_oracle(self):
        # same missing password, but current-database path -> runs
        stub = make_stub(PROD_SCREEN)
        set_snapshot(stub)
        threads = self.start(stub)
        self.assertEqual(len(threads), 1)
        self.assertFalse(any("⛔" in t for t in stub.results_text.inserted))

    # R11-AC-17
    def test_ac17_no_info_keeps_reading_fields_in_old_order(self):
        stub = make_stub(dict(MYSQL_PROD_SCREEN))
        engine, _conn = db_list_engine(["d1"])
        stub.engine = engine
        stub._run_target = RunTarget(engine, None)
        stub._connected_password = (engine, "pw-uat")  # ignored: no snapshot
        stub.get_connection_string = mock.Mock(return_value="cs")
        stub.get_connect_args = mock.Mock(return_value={})
        threads = self.start(stub)
        self.assertEqual(
            [r for r in stub._reads if r in FIELDS],
            ["db_type", "db_name", "db_user", "db_password", "db_host", "db_port"],
        )
        self.assertEqual(threads[0].args, (("other", "pw-prod", "prod-db", "9999"),))
        self.run_worker(stub, threads[0])
        stub.get_connection_string.assert_called_once_with(
            "MySQL", "other", "pw-prod", "prod-db", "9999", "d1"
        )


# ---------------------------------------------------------------- password
class ConnectedPasswordTests(_ListTablesBase):
    def _connected(self, screen, password, names=("d1",)):
        stub = make_stub(dict(screen, db_password=password))
        engine, _conn = db_list_engine(list(names), name="engine_a")
        connect(stub, engine=engine)
        self.assertIs(stub.engine, engine)
        return stub, engine

    # R11-AC-18
    def test_ac18_password_reaches_worker_but_no_log_print_or_snapshot(self):
        screen = dict(MYSQL_PROD_SCREEN, db_host="uat-db", db_user="app", db_port="3306")
        stub, engine = self._connected(screen, UAT_PW, names=("d1", "d2"))
        stub.get_connection_string = mock.Mock(side_effect=lambda *a: f"cs-{a[-1]}")
        stub.get_connect_args = mock.Mock(return_value={})
        threads = self.start(stub)
        self.run_worker(stub, threads[0])
        self.assertEqual(stub.get_connection_string.call_args_list, [
            mock.call("MySQL", "app", UAT_PW, "uat-db", "3306", "d1"),
            mock.call("MySQL", "app", UAT_PW, "uat-db", "3306", "d2"),
        ])
        ci = stub._run_target.info
        texts = [repr(ci), str(ci), repr(stub._run_target), str(stub._run_target),
                 ci.target_label(), ci.log_target(), ci.run_log_header()]
        texts += [str(v) for v in dataclasses.asdict(ci).values()]
        texts += stub.results_text.inserted
        texts += self.prints
        texts += [str(c) for c in stub._write_run_log.call_args_list]
        texts += [str(c) for c in self.messagebox.mock_calls]
        self.assertTrue(self.prints)  # the worker did print (patched)
        for t in texts:
            self.assertNotIn(UAT_PW, t)
            self.assertNotIn("S3cr3t", t)

    def test_ac18_real_sqlite_connect_snapshot_has_no_password(self):
        from sqlalchemy import create_engine as real_create_engine

        stub = make_stub(dict(UAT_SCREEN, db_name=""))
        engine = real_create_engine("sqlite://")
        self.addCleanup(engine.dispose)
        with mock.patch.object(app, "create_engine", return_value=engine), \
                mock.patch.object(app, "messagebox") as mb, \
                mock.patch("builtins.print", side_effect=self._capture_print):
            stub.connect_database()
        mb.showerror.assert_not_called()
        self.assertEqual(stub._connected_password_for(engine), UAT_PW)
        ci = stub._run_target.info
        texts = [repr(ci), str(ci), repr(stub._run_target), ci.target_label(),
                 ci.log_target(), ci.run_log_header()]
        texts += [str(v) for v in dataclasses.asdict(ci).values()]
        texts += stub.results_text.inserted + self.prints
        texts += [str(c) for c in stub._write_run_log.call_args_list]
        texts += [str(c) for c in mb.mock_calls]
        for t in texts:
            self.assertNotIn(UAT_PW, t)
            self.assertNotIn("S3cr3t", t)
        main, sub = _Label(), _Label()
        stub._update_target_summary(main, sub)
        self.assertNotIn("S3cr3t", main.text + sub.text)

    def test_ac18_password_kept_unstripped(self):
        stub, engine = self._connected(UAT_SCREEN, "  pw with spaces  ")
        self.assertEqual(stub._connected_password_for(engine), "  pw with spaces  ")

    # R11-AC-19
    def test_ac19a_second_connect_replaces_password(self):
        stub, engine_a = self._connected(UAT_SCREEN, "pw-A")
        self.assertEqual(stub._connected_password_for(engine_a), "pw-A")
        set_screen(stub, dict(PROD_SCREEN, db_password="pw-B"))
        engine_b, _ = db_list_engine([], name="engine_b")
        connect(stub, engine=engine_b)
        self.assertIs(stub.engine, engine_b)
        self.assertEqual(stub._connected_password_for(engine_b), "pw-B")
        self.assertIsNone(stub._connected_password_for(engine_a))
        self.assertEqual(stub._connected_password, (engine_b, "pw-B"))
        self.assertNotIn("pw-A", repr(stub._connected_password))

    def test_ac19b_failed_connect_clears_password(self):
        stub, engine_a = self._connected(UAT_SCREEN, "pw-A")
        set_screen(stub, dict(PROD_SCREEN, db_password="pw-B"))
        connect(stub, fail=True)
        self.assertIsNone(stub.engine)
        self.assertIsNone(stub._connected_password)
        self.assertIsNone(stub._connected_password_for(engine_a))
        self.assertIsNone(stub._connected_password_for(None))
        stub._show_connection_error.assert_called_once()

    def test_ac19b_failed_first_connect_stores_nothing(self):
        stub = make_stub(dict(UAT_SCREEN, db_password="pw-A"))
        connect(stub, fail=True)
        self.assertIsNone(stub._connected_password)

    def test_ac19c_profile_reset_clears_password(self):
        stub, engine_a = self._connected(UAT_SCREEN, "pw-A")
        stub.execute_btn.state = "normal"
        stub._reset_profile_connection_state(engine_a)
        self.assertIsNone(stub.engine)
        self.assertIsNone(stub._connected_password)
        self.assertIsNone(stub._connected_password_for(engine_a))

    def test_ac19c_reset_skipped_after_reconnect_keeps_password(self):
        stub, engine_a = self._connected(UAT_SCREEN, "pw-A")
        stub._reset_profile_connection_state(mock.Mock(name="older_engine"))
        self.assertEqual(stub._connected_password_for(engine_a), "pw-A")

    def test_ac19_early_return_keeps_current_connection(self):
        stub, engine_a = self._connected(UAT_SCREEN, "pw-A")
        stub.db_password.value = ""  # Connect refused: empty password field
        mb = connect(stub, engine=mock.MagicMock(name="never_used"), refused=True)
        mb.showerror.assert_called_once()
        self.assertIs(stub.engine, engine_a)
        self.assertEqual(stub._connected_password_for(engine_a), "pw-A")

    def test_ac19_accessor_requires_the_same_engine(self):
        stub = make_stub()
        engine = mock.MagicMock(name="e")
        self.assertIsNone(stub._connected_password_for(engine))  # attribute absent
        stub._connected_password = (engine, "pw")
        self.assertEqual(stub._connected_password_for(engine), "pw")
        self.assertIsNone(stub._connected_password_for(mock.MagicMock(name="other")))
        self.assertIsNone(stub._connected_password_for(None))

    def test_ac19_replace_engine_binds_and_clears(self):
        stub = make_stub()
        e1, e2 = mock.MagicMock(name="e1"), mock.MagicMock(name="e2")
        stub._replace_engine(e1, UAT_INFO, password="pw-1")
        self.assertEqual(stub._connected_password, (e1, "pw-1"))
        stub._replace_engine(e2, UAT_INFO)  # no password given -> cleared
        self.assertIsNone(stub._connected_password)
        stub._replace_engine(e1, UAT_INFO, password="pw-1")
        stub._replace_engine(None, password="pw-x")
        self.assertIsNone(stub._connected_password)

    # R11-AC-20
    def test_ac20_editing_password_field_does_not_change_tables_password(self):
        screen = dict(MYSQL_PROD_SCREEN, db_host="uat-db", db_user="app", db_port="3306")
        stub, _engine = self._connected(screen, "pw-A")
        stub.db_password.value = "pw-B"  # typed, no Connect
        stub.get_connection_string = mock.Mock(return_value="cs")
        stub.get_connect_args = mock.Mock(return_value={})
        threads = self.start(stub)
        self.run_worker(stub, threads[0])
        stub.get_connection_string.assert_called_once_with(
            "MySQL", "app", "pw-A", "uat-db", "3306", "d1"
        )

    # review follow-up: password only goes to the thread when it is used
    def test_password_not_passed_to_thread_when_worker_does_not_use_it(self):
        oracle_all = ConnectionInfo(profile="P1", db_type="Oracle", user="scott",
                                    host="ora", port="1521", database="")
        cases = (
            ("current_database", UAT_INFO, ""),
            ("oracle_all_schemas", oracle_all, ""),
            ("mysql_all_databases", MYSQL_ALL_INFO, UAT_PW),
        )
        for label, info, expected in cases:
            with self.subTest(case=label):
                stub = make_stub(PROD_SCREEN)
                set_snapshot(stub, info, password=UAT_PW)
                threads = self.start(stub)
                self.assertEqual(len(threads), 1)
                self.assertEqual(threads[0].args[0][1], expected)
                for value in threads[0].args[0]:
                    if expected == "":
                        self.assertNotIn("S3cr3t", value)

    # review follow-up: driver errors must not echo the password
    def test_worker_error_output_is_redacted(self):
        stub = make_stub(MYSQL_PROD_SCREEN)
        engine, _conn = db_list_engine(["d1"])
        set_snapshot(stub, MYSQL_ALL_INFO, password=UAT_PW, engine=engine)
        engine.connect.side_effect = RuntimeError(
            f"login failed for mysql://app:{UAT_PW}@uat-db/ (password={UAT_PW})")
        stub.get_connection_string = mock.Mock(return_value="cs")
        stub.get_connect_args = mock.Mock(return_value={})
        threads = self.start(stub)
        self.run_worker(stub, threads[0])
        joined = "\n".join(self.prints)
        self.assertIn("login failed", joined)
        self.assertIn("RuntimeError", joined)  # the traceback is still shown
        self.assertNotIn("S3cr3t", joined)

    def test_on_list_tables_error_is_redacted(self):
        odbc = app.build_sqlserver_odbc_connect(
            "ODBC Driver 17 for SQL Server", "h", "1433", "db", "u", UAT_PW)
        from urllib.parse import quote_plus

        encoded = "mssql+pyodbc:///?odbc_connect=" + quote_plus(odbc)
        for label, stored in (("stored", True), ("not_stored", False)):
            with self.subTest(case=label):
                stub = make_stub()
                if stored:
                    set_snapshot(stub, password=UAT_PW)
                error = RuntimeError(f"(pyodbc.Error) [{odbc}] [{encoded}]")
                dialog = mock.Mock(name="loading")
                with mock.patch.object(app, "messagebox") as mb:
                    GUI.on_list_tables_error(stub, error, dialog)
                dialog.destroy.assert_called_once_with()
                texts = stub.results_text.inserted + [str(c) for c in mb.mock_calls]
                self.assertTrue(any("pyodbc.Error" in t for t in texts))
                for text in texts:
                    self.assertNotIn("S3cr3t", text)
                self.assertEqual(stub.inspect_btn.state, "normal")


class RedactSecretsTests(unittest.TestCase):
    def test_patterns_and_known_secret(self):
        from urllib.parse import quote_plus

        # รหัสมี ; และ } -> ODBC เขียนเป็น {p@ss;w}}rd} (encoded: %7Bp%40ss%3Bw%7D%7Drd%7D)
        # จึงต้องเทียบผลทั้งบรรทัด: ถ้า regex จัดการ }} / %7D%7D ไม่ได้ จะ mask แค่ครึ่งเดียว
        pw = "p@ss;w}rd"
        odbc = app.build_sqlserver_odbc_connect("D", "h", "1", "db", "u", pw)
        self.assertIn("PWD={p@ss;w}}rd}", odbc)  # ยืนยันรูปที่ใช้ทดสอบ
        odbc += ";Encrypt=yes"  # มีข้อความต่อท้าย: mask ต้องหยุดตรงปีกกาปิดของรหัส
        prefix = "DRIVER={D};SERVER=h,1;DATABASE={db};UID={u};"
        url = "mssql+pyodbc:///?odbc_connect="
        cases = [
            (odbc, prefix + "PWD=***;Encrypt=yes"),
            (url + quote_plus(odbc),
             url + quote_plus(prefix + "PWD=") + "***" + quote_plus(";Encrypt=yes")),
            ("postgresql://user:hunter22@host/db", "postgresql://user:***@host/db"),
            ("PWD=abc123;UID=x", "PWD=***;UID=x"),
            ("password=hunter22 next", "password=*** next"),
        ]
        for text, expected in cases:
            with self.subTest(text=text):
                plain = app.redact_secrets(text)
                self.assertEqual(plain, expected)
                for leak in ("p@ss", "p%40ss", "w}}rd", "rd}", "%7D%7Drd", "hunter22", "abc123"):
                    self.assertNotIn(leak, plain)

    def test_known_secret_verbatim_and_short_secret_ignored(self):
        self.assertEqual(app.redact_secrets("error near S3cr3t-UAT", UAT_PW), "error near ***")
        self.assertEqual(app.redact_secrets("a table", "a"), "a table")  # too short
        self.assertEqual(app.redact_secrets("nothing here", None, ""), "nothing here")


if __name__ == "__main__":
    unittest.main()
