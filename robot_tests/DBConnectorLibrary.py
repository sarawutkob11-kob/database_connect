# -*- coding: utf-8 -*-
"""Robot Framework keywords for Database Connector GUI.

The keywords drive the real program (database_connect_gui.py) through its
own functions and widgets, in an isolated test folder:

* every test gets a fresh temp folder for db_profiles.json, saved_jobs.json,
  script_groups.json, app_settings.json and logs/ — the real files are never
  touched;
* "Connect" goes through the program's connect_database(), but the engine is
  redirected to a local SQLite file (a python-oracledb-like cancel() is
  provided so Stop can be tested);
* message boxes and file dialogs are answered by the test.
"""
import datetime
import json
import os
import re
import shutil
import sqlite3
import sys
import tempfile
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from robot.api import logger
from robot.api.deco import keyword, library
from sqlalchemy import create_engine as _real_create_engine
from sqlalchemy.pool import QueuePool

try:  # sharp screenshots: real pixel coordinates on high-DPI screens
    import ctypes as _ctypes

    _ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    pass

APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)
import database_connect_gui as appmod  # noqa: E402

PROFILE_MAIN = "test_main"
PROFILE_OTHER = "test_other"
TEST_PASSWORD = "Secret#Pass123"
LONG_SQL = (
    "WITH RECURSIVE r(x) AS (SELECT 1 UNION ALL SELECT x+1 FROM r WHERE x < 400000000) "
    "SELECT COUNT(*) AS N FROM r"
)

SEED_JOBS = [
    ("JOB_ACCOUNTS", "SELECT ACCOUNT_NO, NAME, BALANCE FROM ACCOUNTS ORDER BY ACCOUNT_NO"),
    ("JOB_STATUS", "SELECT ID, STATUS FROM TEST_TABLE ORDER BY ID"),
    ("JOB_BAD", "SELECT * FROM TABLE_NOT_EXIST"),
    ("JOB_COUNT", "SELECT COUNT(*) AS N FROM ACCOUNTS"),
]


class _CancellableSQLite:
    """sqlite3 connection with cancel() from another thread (like python-oracledb)."""

    def __init__(self, path):
        self._c = sqlite3.connect(path, check_same_thread=False)

    def cancel(self):
        self._c.interrupt()

    def __getattr__(self, name):
        return getattr(self._c, name)


def _grab_window_png(hwnd, width, height, path):
    """Capture one window (even if other windows cover it) to a PNG file.

    Uses Windows PrintWindow + GDI and writes the PNG with zlib (no PIL needed).
    """
    import ctypes
    import struct
    import zlib
    from ctypes import wintypes

    user32, gdi32 = ctypes.windll.user32, ctypes.windll.gdi32
    screen_dc = user32.GetDC(0)
    mem_dc = gdi32.CreateCompatibleDC(screen_dc)
    bitmap = gdi32.CreateCompatibleBitmap(screen_dc, width, height)
    gdi32.SelectObject(mem_dc, bitmap)
    PW_RENDERFULLCONTENT = 2
    user32.PrintWindow(wintypes.HWND(hwnd), mem_dc, PW_RENDERFULLCONTENT)

    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [
            ("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG),
            ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD),
            ("biCompression", wintypes.DWORD), ("biSizeImage", wintypes.DWORD),
            ("biXPelsPerMeter", wintypes.LONG), ("biYPelsPerMeter", wintypes.LONG),
            ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD),
        ]

    header = BITMAPINFOHEADER()
    header.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    header.biWidth, header.biHeight = width, -height  # top-down rows
    header.biPlanes, header.biBitCount = 1, 32
    buffer = ctypes.create_string_buffer(width * height * 4)
    gdi32.GetDIBits(mem_dc, bitmap, 0, height, buffer, ctypes.byref(header), 0)
    gdi32.DeleteObject(bitmap)
    gdi32.DeleteDC(mem_dc)
    user32.ReleaseDC(0, screen_dc)

    bgra = buffer.raw
    rgb = bytearray(width * height * 3)
    rgb[0::3], rgb[1::3], rgb[2::3] = bgra[2::4], bgra[1::4], bgra[0::4]
    stride = width * 3
    raw = b"".join(b"\x00" + bytes(rgb[r * stride:(r + 1) * stride]) for r in range(height))

    def chunk(kind, data):
        return (struct.pack(">I", len(data)) + kind + data
                + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF))

    png = (b"\x89PNG\r\n\x1a\n"
           + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b""))
    with open(path, "wb") as f:
        f.write(png)


def _window_handle_and_size(widget):
    """(hwnd, width, height) of a Tk toplevel incl. its title bar."""
    import ctypes
    from ctypes import wintypes

    rect = wintypes.RECT()
    hwnd = int(widget.wm_frame(), 16)
    ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect))
    return hwnd, rect.right - rect.left, rect.bottom - rect.top


def _walk(widget):
    for child in widget.winfo_children():
        yield child
        yield from _walk(child)


def _text_of(widget):
    try:
        return str(widget.cget("text"))
    except tk.TclError:
        return ""


@library(scope="TEST", auto_keywords=False)
class DBConnectorLibrary:
    def __init__(self):
        self.workdir = None
        self.root = None
        self.app = None
        self.asks = []  # (kind, title, message)
        self.messages = []  # (kind, title, message)
        self.answers = []
        self.save_path = None
        self.open_path = None
        self.save_dialog_names = []
        self.engine_kwargs = {}
        self._patched = {}

    # ------------------------------------------------------------ plumbing
    def _patch(self, obj, name, value):
        self._patched.setdefault((obj, name), getattr(obj, name))
        setattr(obj, name, value)

    def _install_patches(self):
        def record(kind):
            def _f(title=None, message=None, **_kw):
                self.messages.append((kind, title, message))
                logger.info(f"[{kind}] {title}: {message}")
                return "ok"
            return _f

        def ask(kind):
            def _f(title=None, message=None, **_kw):
                self.asks.append((kind, title, message))
                # one queue for every question; nothing queued → Yes
                answer = self.answers.pop(0) if self.answers else True
                if answer is None and kind != "askyesnocancel":
                    answer = False
                import html as _html

                label = {True: "Yes", False: "No", None: "Cancel"}[answer]
                logger.info(
                    '<div style="border:1px solid #999;border-radius:4px;max-width:640px;'
                    'font-family:Segoe UI,Tahoma;margin:4px 0">'
                    f'<div style="background:#eee;padding:4px 8px"><b>{_html.escape(str(title))}</b>'
                    f' <span style="color:#888">(หน้าต่างถามยืนยัน)</span></div>'
                    f'<pre style="margin:0;padding:8px;white-space:pre-wrap">{_html.escape(str(message))}</pre>'
                    f'<div style="padding:4px 8px;background:#f7f7f7">เทสตอบ: <b>{label}</b></div></div>',
                    html=True,
                )
                return answer
            return _f

        for kind in ("showinfo", "showwarning", "showerror"):
            self._patch(messagebox, kind, record(kind))
        for kind in ("askyesno", "askyesnocancel", "askokcancel"):
            self._patch(messagebox, kind, ask(kind))

        def save_dialog(**kw):
            self.save_dialog_names.append(kw.get("initialfile"))
            return self.save_path or ""

        self._patch(filedialog, "asksaveasfilename", save_dialog)
        self._patch(filedialog, "askopenfilename", lambda **kw: self.open_path or "")

        db_path = os.path.join(self.workdir, "test.db")

        def fake_create_engine(url, **kwargs):
            # Same options as the program asks for, but on a local SQLite file
            self.engine_kwargs = dict(kwargs)
            options = {k: kwargs[k] for k in ("pool_pre_ping", "pool_recycle") if k in kwargs}
            # QueuePool = the pool Oracle / PostgreSQL / MySQL engines get in real use
            return _real_create_engine(
                "sqlite://",
                creator=lambda: _CancellableSQLite(db_path),
                poolclass=QueuePool,
                **options,
            )

        self._patch(appmod, "create_engine", fake_create_engine)

        # Modal dialogs call grab_set(); if another Tk program on this PC (e.g.
        # the real Database Connector) has a modal window open, Windows refuses
        # the grab. Tests do not need real modality, so ignore that refusal.
        original_grab_set = tk.Misc.grab_set

        def tolerant_grab_set(widget, *args, **kwargs):
            try:
                return original_grab_set(widget, *args, **kwargs)
            except tk.TclError as error:
                if "grab" not in str(error):
                    raise
                return None

        self._patch(tk.Misc, "grab_set", tolerant_grab_set)
        # All data files of the program go to the test folder
        self._patch(appmod, "__file__", os.path.join(self.workdir, "database_connect_gui.py"))

    def _restore_patches(self):
        for (obj, name), value in self._patched.items():
            setattr(obj, name, value)
        self._patched.clear()

    def _seed_files(self):
        profiles = {
            PROFILE_MAIN: {
                "db_type": "PostgreSQL", "db_user": "tester", "db_password": TEST_PASSWORD,
                "db_host": "localhost", "db_port": "5432", "db_name": "testdb",
                "sql_query": "SELECT 1",
            },
            PROFILE_OTHER: {
                "db_type": "PostgreSQL", "db_user": "other", "db_password": TEST_PASSWORD,
                "db_host": "localhost", "db_port": "5432", "db_name": "otherdb",
                "sql_query": "SELECT 1",
            },
            "last_used_profile": PROFILE_MAIN,
        }
        with open(os.path.join(self.workdir, "db_profiles.json"), "w", encoding="utf-8") as f:
            json.dump(profiles, f, ensure_ascii=False, indent=2)
        jobs = [
            {"name": n, "profile": PROFILE_MAIN, "query": q, "database": "testdb",
             "db_type": "PostgreSQL", "created": "2026-11-06 09:00:00"}
            for n, q in SEED_JOBS
        ]
        jobs.append({"name": "OTHER_JOB", "profile": PROFILE_OTHER, "query": "SELECT 1",
                     "database": "otherdb", "db_type": "PostgreSQL", "created": "2026-11-06 09:00:00"})
        with open(os.path.join(self.workdir, "saved_jobs.json"), "w", encoding="utf-8") as f:
            json.dump(jobs, f, ensure_ascii=False, indent=2)

        con = sqlite3.connect(os.path.join(self.workdir, "test.db"))
        con.executescript(
            """
            CREATE TABLE ACCOUNTS (ACCOUNT_NO TEXT, NAME TEXT, BALANCE REAL, NOTE TEXT);
            INSERT INTO ACCOUNTS VALUES ('14764478022247801378', 'O''NEIL', 1500.25, NULL);
            INSERT INTO ACCOUNTS VALUES ('14764478022247801379', 'SOMCHAI', 20.5, 'vip');
            INSERT INTO ACCOUNTS VALUES ('14764478022247801380', 'SUDA', 0, NULL);
            CREATE TABLE TEST_TABLE (ID INTEGER, STATUS TEXT);
            INSERT INTO TEST_TABLE VALUES (1, 'A');
            INSERT INTO TEST_TABLE VALUES (2, 'A');
            CREATE TABLE BIG_NUMBERS (ACCOUNT_NO INTEGER, AMOUNT REAL, NOTE TEXT);
            INSERT INTO BIG_NUMBERS VALUES (1234567890123456789, 10.5, NULL);
            """
        )
        con.commit()
        con.close()

    def _start_app(self):
        self.root = tk.Tk()
        self.root.geometry("1200x800+40+40")
        self.root.report_callback_exception = self._on_tk_error
        self.app = appmod.DatabaseConnectorGUI(self.root)
        self.app.debug_mode.set(False)
        self._pump(300)

    def _stop_app(self):
        if self.root is None:
            return
        # Let running background work finish, then cancel pending timers
        try:
            self.wait_until_idle(timeout=20)
        except Exception:
            pass
        try:
            for after_id in self.root.tk.splitlist(self.root.tk.call("after", "info")):
                try:
                    self.root.tk.call("after", "cancel", str(after_id))
                except tk.TclError:
                    pass
        except tk.TclError:
            pass
        try:
            self.root.destroy()
        except tk.TclError:
            pass
        self.root = None
        self.app = None

    def _on_tk_error(self, exc, val, tb):
        import traceback

        self.messages.append(("tk-error", type(val).__name__, str(val)))
        logger.warn("Tk callback error: " + "".join(traceback.format_exception(exc, val, tb)))

    def _pump(self, ms):
        """Run the Tk event loop for `ms` milliseconds (background threads need it)."""
        self.root.after(int(ms), self.root.quit)
        self.root.mainloop()

    def _busy(self):
        app = self.app
        return (
            getattr(app, "_batch_running", False)
            or "Loading" in _text_of(app.execute_btn)
            or "Loading" in _text_of(app.inspect_btn)
            or "Exporting" in _text_of(app.export_excel_btn)
            or bool(app._active_db_connections)
        )

    def _toplevels(self):
        return [w for w in _walk(self.root) if isinstance(w, tk.Toplevel)]

    def _find_button(self, container, label):
        for w in _walk(container):
            if isinstance(w, (tk.Button, ttk.Button)) and label.lower() in _text_of(w).lower():
                return w
        raise AssertionError(f"Button '{label}' not found")

    def _wait_for_toplevel(self, predicate, timeout=5.0):
        end = time.time() + timeout
        while time.time() < end:
            for top in reversed(self._toplevels()):
                try:
                    if top.winfo_exists() and predicate(top):
                        return top
                except tk.TclError:
                    pass
            self._pump(100)
        raise AssertionError("Expected dialog did not open")

    def _after_dialog(self, predicate, action):
        """Schedule `action(dialog)` for a dialog that a button opens and waits on."""

        def attempt(tries=50):
            for top in reversed(self._toplevels()):
                try:
                    if top.winfo_exists() and predicate(top):
                        action(top)
                        return
                except tk.TclError:
                    pass
            if tries:
                self.root.after(100, lambda: attempt(tries - 1))
            else:
                self.messages.append(("tk-error", "dialog", "dialog never opened"))

        self.root.after(150, attempt)

    @staticmethod
    def _has_title(text_value):
        return lambda top: text_value.lower() in str(top.title()).lower()

    def _log_text(self):
        return self.app.results_text.get("1.0", "end")

    # ---------------------------------------------------------- lifecycle
    @keyword("เปิดโปรแกรมด้วยข้อมูลทดสอบ")
    def open_app(self):
        self.workdir = tempfile.mkdtemp(prefix="dbconn_robot_")
        logger.info(f"Test folder: {self.workdir}")
        self._seed_files()
        self._install_patches()
        self._start_app()

    # -------------------------------------------------------- screenshots
    @keyword("ถ่ายภาพหน้าจอ")
    def take_screenshot(self, title="ภาพหน้าจอ", view="ผลลัพธ์"):
        """Capture the program (main window + open dialogs) into log.html.

        view: "ผลลัพธ์" scrolls the main window to Saved Jobs / Results,
              "บน" shows Connection / SQL editor.
        """
        from robot.libraries.BuiltIn import BuiltIn

        if self.root is None:
            return
        import html as _html

        try:
            if hasattr(self.app.canvas, "yview_moveto"):  # older layout scrolled as a whole
                self.app.canvas.yview_moveto(0.0 if view == "บน" else 1.0)
            self._pump(350)
            windows = [self.root] + [
                t for t in self._toplevels() if t.winfo_exists() and t.winfo_ismapped()
            ]
            out_dir = BuiltIn().get_variable_value("${OUTPUT DIR}")
            test_name = BuiltIn().get_variable_value("${TEST NAME}") or "suite"
            short = re.sub(r"[^A-Za-z0-9_]+", "_", test_name.split(" ")[0]).strip("_") or "test"
            shot_dir = os.path.join(out_dir, "screenshots")
            os.makedirs(shot_dir, exist_ok=True)

            parts = [f"<b>{_html.escape(title)}</b>"]
            for window in windows:
                self._shot_no = getattr(self, "_shot_no", 0) + 1
                name = f"{short}_{self._shot_no}.png"
                hwnd, width, height = _window_handle_and_size(window)
                _grab_window_png(hwnd, width, height, os.path.join(shot_dir, name))
                label = "หน้าหลัก" if window is self.root else str(window.title())
                size = 900 if window is self.root else 640
                parts.append(
                    f'<div style="margin-top:6px;color:#555">หน้าต่าง: {_html.escape(label)}</div>'
                    f'<a href="screenshots/{name}"><img src="screenshots/{name}" '
                    f'width="{size}" style="border:1px solid #ccc"></a>'
                )
            logger.info("".join(parts), html=True)
        except Exception as error:
            logger.warn(f"Screenshot failed: {error}")

    @keyword("ปิดโปรแกรม")
    def close_app(self):
        errors = [m for m in self.messages if m[0] == "tk-error"]
        if self.root is not None:
            self.take_screenshot("หน้าจอตอนจบเทส")
            try:
                import html as _html

                lines = self._log_text().rstrip().splitlines()[-60:]
                logger.info(
                    "<b>ข้อความในแท็บ Execution Logs (60 บรรทัดสุดท้าย)</b>"
                    '<pre style="background:#fafafa;border:1px solid #ddd;padding:8px;'
                    'max-height:420px;overflow:auto">' + _html.escape("\n".join(lines)) + "</pre>",
                    html=True,
                )
            except Exception:
                pass
        self._stop_app()
        self._restore_patches()
        if self.workdir:
            shutil.rmtree(self.workdir, ignore_errors=True)
        if errors:
            raise AssertionError(f"Program raised errors during the test: {errors}")

    @keyword("ปิดแล้วเปิดโปรแกรมใหม่")
    def restart_app(self):
        self._stop_app()
        self._start_app()

    @keyword("รอจนรันเสร็จ")
    def wait_until_idle(self, timeout=30):
        self._pump(400)
        end = time.time() + float(timeout)
        while self._busy():
            if time.time() > end:
                raise AssertionError(f"Still running after {timeout} s")
            self._pump(150)
        self._pump(300)

    @keyword("รอ ${seconds} วินาที")
    def wait_seconds(self, seconds):
        self._pump(float(seconds) * 1000)

    # --------------------------------------------------------- dialogs
    @keyword("ตอบหน้าต่างยืนยันถัดไปว่า")
    def answer_next(self, *answers):
        """Queue answers (Yes / No / Cancel) for the next questions, in order."""
        mapping = {"yes": True, "no": False, "cancel": None}
        for a in answers:
            self.answers.append(mapping[a.strip().lower()])

    @keyword("ล้างคำตอบที่เตรียมไว้")
    def clear_answers(self):
        self.answers = []

    @keyword("จำนวนหน้าต่างยืนยันที่เด้งขึ้น")
    def ask_count(self):
        return len(self.asks)

    @keyword("หน้าต่างยืนยันล่าสุดต้องมีข้อความ")
    def last_ask_contains(self, *texts):
        if not self.asks:
            raise AssertionError("No confirmation was shown")
        message = str(self.asks[-1][2])
        for t in texts:
            if t not in message:
                raise AssertionError(f"'{t}' not in confirmation:\n{message}")

    @keyword("ต้องมีข้อความแจ้งเตือนที่มีคำว่า")
    def message_contains(self, text_value):
        if not any(text_value in str(m[2]) for m in self.messages):
            raise AssertionError(f"No message containing '{text_value}': {self.messages[-5:]}")

    @keyword("ตั้งไฟล์ที่จะบันทึกเป็น")
    def set_save_path(self, filename):
        self.save_path = os.path.join(self.workdir, filename)
        if os.path.exists(self.save_path):
            os.remove(self.save_path)
        return self.save_path

    @keyword("ตั้งไฟล์ที่จะเปิดเป็น")
    def set_open_path(self, path):
        self.open_path = path if os.path.isabs(path) else os.path.join(self.workdir, path)

    @keyword("สร้างไฟล์ JSON ที่ไม่ใช่ไฟล์กลุ่ม")
    def make_bad_json(self, filename="bad.json"):
        path = os.path.join(self.workdir, filename)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"hello": "world"}, f)
        return path

    # ------------------------------------------------------ connection
    @keyword("เชื่อมต่อฐานข้อมูลทดสอบ")
    def connect(self):
        self.app.connect_database()
        self._pump(200)
        self.connection_status_should_be("Connected")

    @keyword("สถานะการเชื่อมต่อต้องเป็น")
    def connection_status_should_be(self, expected):
        status = str(self.app.status_label.cget("text"))
        if expected.lower() == "connected":
            ok = status.startswith("✅")
        else:
            ok = expected.lower() in status.lower()
        if not ok:
            raise AssertionError(f"Connection status is '{status}', expected '{expected}'")

    @keyword("ปุ่ม Execute ต้องกดได้")
    def execute_enabled(self):
        if str(self.app.execute_btn["state"]) == "disabled":
            raise AssertionError("Execute button is disabled")

    @keyword("ตัวเชื่อมต่อต้องตรวจ connection ก่อนใช้และเปลี่ยนใหม่ทุก 30 นาที")
    def engine_options(self):
        if self.engine_kwargs.get("pool_pre_ping") is not True:
            raise AssertionError(f"pool_pre_ping not set: {self.engine_kwargs}")
        if self.engine_kwargs.get("pool_recycle") != 1800:
            raise AssertionError(f"pool_recycle is not 1800: {self.engine_kwargs}")

    @keyword("จำลอง connection ถูกตัดระหว่างเปิดโปรแกรมทิ้งไว้")
    def drop_connection(self):
        pool = self.app.engine.pool
        idle = list(getattr(pool, "_pool").queue)
        if not idle:
            raise AssertionError("No idle pooled connection to drop — run a query first")
        for record in idle:
            record.dbapi_connection.close()

    # --------------------------------------------------------- profile
    @keyword("บันทึก Profile ปัจจุบันเป็นชื่อ")
    def save_profile_as(self, name):
        self.app.save_profile_dialog()
        dialog = self._wait_for_toplevel(self._has_title("Save Profile"))
        entry = next(w for w in _walk(dialog) if w.winfo_class() in ("TEntry", "Entry"))
        entry.delete(0, "end")
        entry.insert(0, name)
        self._find_button(dialog, "Save").invoke()
        self._pump(200)

    @keyword("รหัสผ่านของ Profile ในไฟล์ต้องถูกเข้ารหัส")
    def password_encrypted(self, name, plain=TEST_PASSWORD):
        with open(os.path.join(self.workdir, "db_profiles.json"), encoding="utf-8") as f:
            stored = json.load(f)[name]["db_password"]
        if stored == plain or plain in stored:
            raise AssertionError("Password is stored as plain text")
        if appmod.unprotect_password(stored) != plain:
            raise AssertionError("Stored password cannot be decrypted back")

    @keyword("เลือก Profile")
    def select_profile(self, name):
        self.app.profile_combo.set(name)
        self.app.on_profile_selected()
        self._pump(200)

    @keyword("Profile ที่เลือกอยู่ต้องเป็น")
    def profile_should_be(self, name):
        if self.app.profile_combo.get() != name:
            raise AssertionError(f"Selected profile is '{self.app.profile_combo.get()}'")

    @keyword("รายการ Saved Jobs ต้องเป็น")
    def jobs_should_be(self, *names):
        actual = [j.get("name") for j in self.app._current_profile_jobs()]
        if actual != list(names):
            raise AssertionError(f"Saved Jobs are {actual}, expected {list(names)}")

    @keyword("รายการ Saved Jobs ต้องมี")
    def jobs_should_contain(self, *names):
        actual = [j.get("name") for j in self.app._current_profile_jobs()]
        missing = [n for n in names if n not in actual]
        if missing:
            raise AssertionError(f"Missing jobs {missing}; have {actual}")

    # --------------------------------------------------------- execute
    @keyword("พิมพ์ SQL")
    def type_sql(self, sql):
        self.app.sql_context.delete("1.0", "end")
        self.app.sql_context.insert("1.0", sql)

    @keyword("อ่าน SQL ในช่อง Editor")
    def get_editor_sql(self):
        return self.app.sql_context.get("1.0", "end").strip()

    @keyword("SQL ในช่อง Editor ต้องเป็น")
    def editor_sql_should_be(self, sql):
        actual = self.app.sql_context.get("1.0", "end").strip()
        if actual != sql.strip():
            raise AssertionError(f"Editor SQL is:\n{actual}\nexpected:\n{sql}")

    @keyword("กด Execute")
    def press_execute(self):
        self.app.execute_query()
        self._pump(200)

    @keyword("ผลลัพธ์ใน Results Grid ต้องมี ${rows} แถว")
    def grid_rows(self, rows):
        df = self.app._results_grid_state.get("df")
        if df is None:
            raise AssertionError("Results Grid is empty")
        if len(df) != int(rows):
            raise AssertionError(f"Results Grid has {len(df)} rows, expected {rows}")

    @keyword("ค่าในตาราง Results Grid แถว ${row} คอลัมน์ ${column} ต้องเป็น")
    def grid_value(self, row, column, expected):
        tree = self.app._rg_tree
        items = tree.get_children()
        value = tree.set(items[int(row) - 1], column)
        if str(value) != expected:
            raise AssertionError(f"Cell is '{value}', expected '{expected}'")

    @keyword("Results Grid ต้องมีผลของ")
    def grid_sets(self, *names):
        actual = [n for n, _df, _q in self.app._results_grid_state.get("sets", [])]
        if actual != list(names):
            raise AssertionError(f"Results Grid has {actual}, expected {list(names)}")

    @keyword("ผลจาก SQL ต้องเป็น")
    def db_value(self, sql, expected):
        con = sqlite3.connect(os.path.join(self.workdir, "test.db"))
        try:
            value = con.execute(sql).fetchone()[0]
        finally:
            con.close()
        if str(value) != str(expected):
            raise AssertionError(f"{sql} → {value}, expected {expected}")

    @keyword("แก้ข้อมูลในฐานข้อมูลโดยตรง")
    def db_change(self, sql):
        con = sqlite3.connect(os.path.join(self.workdir, "test.db"))
        con.execute(sql)
        con.commit()
        con.close()

    @keyword("Error ล่าสุดต้องมีข้อความ")
    def last_error_contains(self, text_value):
        details = self.app.last_error_details or {}
        message = f"{details.get('type', '')}: {details.get('message', '')}"
        if text_value.lower() not in message.lower():
            raise AssertionError(f"Last error is '{message}'")

    @keyword("ปิดหน้าต่างที่เปิดค้างทั้งหมด")
    def close_popups(self):
        for top in self._toplevels():
            if top is getattr(self.app, "_script_groups_window", None):
                continue
            try:
                top.destroy()
            except tk.TclError:
                pass
        self._pump(100)

    # ------------------------------------------------- excel parameter
    @keyword("ใส่ค่าจาก Excel แทน")
    def apply_excel_values(self, parameter, *values):
        """Same steps as Load Excel → Confirm, without the file picker."""
        app = self.app
        current = app.sql_context.get("1.0", "end")
        app._capture_sql_template(current)
        sql_values = app._format_excel_sql_values(list(values))
        key = parameter.lstrip(":").strip("{}").strip().upper()
        app._excel_parameter_values[key] = (parameter, sql_values)
        rendered = app._render_sql_template()
        app.sql_context.delete("1.0", "end")
        app.sql_context.insert("1.0", rendered)
        app._excel_parameterized_sql = rendered

    @keyword("คืนค่า SQL Template ทั้งหมด")
    def reset_all(self):
        self.app.reset_all_parameters()

    # ------------------------------------------------------------ jobs
    @keyword("บันทึก SQL เป็น Job ชื่อ")
    def save_job(self, name):
        self.app.save_job_dialog()
        dialog = self._wait_for_toplevel(self._has_title("Save Job"))
        entry = next(w for w in _walk(dialog) if w.winfo_class() == "Entry")
        entry.delete(0, "end")
        entry.insert(0, name)
        self._find_button(dialog, "Save").invoke()
        self._pump(200)

    def _job(self, name):
        for i, job in enumerate(self.app.saved_jobs):
            if job.get("name") == name:
                return i, job
        raise AssertionError(f"Job '{name}' not found")

    @keyword("Job ต้องเก็บค่า Excel parameter ไว้")
    def job_has_excel(self, name):
        with open(os.path.join(self.workdir, "saved_jobs.json"), encoding="utf-8") as f:
            jobs = json.load(f)
        job = next((j for j in jobs if j.get("name") == name), None)
        if not job or not job.get("sql_template") or not job.get("excel_parameters"):
            raise AssertionError(f"Job {name} has no Excel parameter state: {job}")

    @keyword("แก้ Job")
    def edit_job(self, name, new_name, new_sql):
        idx, _job = self._job(name)
        self.app.edit_job(idx)
        dialog = self._wait_for_toplevel(self._has_title("Edit Job"))
        entry = next(w for w in _walk(dialog) if w.winfo_class() == "Entry")
        query = next(w for w in _walk(dialog) if w.winfo_class() == "Text")
        entry.delete(0, "end")
        entry.insert(0, new_name)
        query.delete("1.0", "end")
        query.insert("1.0", new_sql)
        self._find_button(dialog, "Save Changes").invoke()
        self._pump(200)

    @keyword("SQL ของ Job ต้องเป็น")
    def job_sql(self, name, sql):
        _i, job = self._job(name)
        if job.get("query", "").strip() != sql.strip():
            raise AssertionError(f"Job SQL is '{job.get('query')}'")

    @keyword("ติ๊ก Job")
    def tick_jobs(self, *names):
        for name in names:
            _i, job = self._job(name)
            self.app.toggle_job_checked(job, True)
        self.app.update_jobs_list()

    @keyword("กด Delete Selected")
    def delete_selected(self):
        self.app.delete_selected_jobs()
        self._pump(100)

    @keyword("กด Run Job")
    def run_one_job(self, name):
        _i, job = self._job(name)
        self.app.run_job(job)
        self._pump(200)

    @keyword("กด Run All Jobs")
    def run_all(self):
        self.app.run_all_btn.invoke()
        self._pump(200)

    @keyword("สรุปผลการรันต้องเป็น")
    def summary_should_be(self, total, success, fail):
        log = self._log_text()
        expect = {"Total": total, "Success": success, "Fail": fail}
        for label, value in expect.items():
            found = re.findall(rf"^{label}\s*:\s*(\d+)", log, re.M)
            if not found or found[-1] != str(value):
                raise AssertionError(f"{label} is {found[-1] if found else 'missing'}, expected {value}\n{log[-800:]}")

    @keyword("ลำดับ Job ที่รันใน Log ต้องเป็น")
    def run_order(self, *names):
        actual = re.findall(r"^Job Name\s*:\s*(.+?)\s*$", self._log_text(), re.M)
        if actual != list(names):
            raise AssertionError(f"Run order is {actual}, expected {list(names)}")

    @keyword("Log ต้องมีข้อความ")
    def log_contains(self, text_value):
        if text_value not in self._log_text():
            raise AssertionError(f"'{text_value}' not in log:\n{self._log_text()[-1000:]}")

    @keyword("จำนวนหน้าต่างผลลัพธ์ที่เปิดอยู่ต้องเป็น")
    def popup_count(self, count):
        popups = [t for t in self._toplevels() if "query results" in str(t.title()).lower()]
        if len(popups) != int(count):
            raise AssertionError(f"{len(popups)} result windows open, expected {count}")

    # ---------------------------------------------------- script groups
    def _groups_window(self):
        window = getattr(self.app, "_script_groups_window", None)
        if window is None or not window.winfo_exists():
            raise AssertionError("Script Groups window is not open")
        return window

    def _listboxes(self):
        boxes = [w for w in _walk(self._groups_window()) if isinstance(w, tk.Listbox)]
        return boxes[0], boxes[1]  # groups, scripts

    def _group(self, name):
        if not hasattr(self.app, "script_groups"):
            self.app.script_groups = self.app.load_script_groups()
        profile = self.app.profile_combo.get()
        for g in self.app.script_groups:
            if g.get("profile") == profile and g.get("name") == name:
                return g
        raise AssertionError(f"Group '{name}' not found in profile {profile}")

    @keyword("เปิดหน้าต่าง Script Groups")
    def open_groups(self):
        self.app.show_script_groups_dialog()
        self._pump(300)

    @keyword("สร้างกลุ่ม")
    def create_group(self, name):
        def fill(dialog):
            entry = next(w for w in _walk(dialog) if w.winfo_class() == "Entry")
            entry.delete(0, "end")
            entry.insert(0, name)
            self._find_button(dialog, "OK").invoke()

        self._after_dialog(self._has_title("New Group"), fill)
        self._find_button(self._groups_window(), "New Group").invoke()
        self._pump(200)

    @keyword("จำนวนกลุ่มชื่อนี้ต้องเป็น")
    def group_count(self, name, count):
        profile = self.app.profile_combo.get()
        n = sum(1 for g in self.app.script_groups if g.get("profile") == profile and g["name"] == name)
        if n != int(count):
            raise AssertionError(f"{n} groups named '{name}', expected {count}")

    @keyword("กลุ่มที่เห็นในหน้าต่างต้องเป็น")
    def visible_groups(self, *names):
        groups_box, _ = self._listboxes()
        actual = [re.sub(r"\s+\(\d+\)$", "", groups_box.get(i)) for i in range(groups_box.size())]
        if actual != list(names):
            raise AssertionError(f"Groups shown: {actual}, expected {list(names)}")

    @keyword("เลือกกลุ่ม")
    def select_group(self, name):
        groups_box, _ = self._listboxes()
        for i in range(groups_box.size()):
            if re.sub(r"\s+\(\d+\)$", "", groups_box.get(i)) == name:
                groups_box.selection_clear(0, "end")
                groups_box.selection_set(i)
                groups_box.event_generate("<<ListboxSelect>>")
                self._pump(100)
                return
        raise AssertionError(f"Group '{name}' is not in the list")

    def _select_script(self, name):
        _, scripts_box = self._listboxes()
        for i in range(scripts_box.size()):
            if re.sub(r"^\d+\.\s*", "", scripts_box.get(i)) == name:
                scripts_box.selection_clear(0, "end")
                scripts_box.selection_set(i)
                scripts_box.event_generate("<<ListboxSelect>>")
                self._pump(50)
                return
        raise AssertionError(f"Script '{name}' is not in the selected group")

    def _fill_script_dialog(self, name, sql):
        def fill(dialog):
            entry = next(w for w in _walk(dialog) if w.winfo_class() == "Entry")
            box = next(w for w in _walk(dialog) if w.winfo_class() == "Text")
            entry.delete(0, "end")
            entry.insert(0, name)
            box.delete("1.0", "end")
            box.insert("1.0", sql)
            self._find_button(dialog, "Save").invoke()

        return fill

    @keyword("เพิ่ม SQL เข้ากลุ่ม")
    def add_sql(self, group, name, sql):
        self.select_group(group)
        self._after_dialog(self._has_title("Add SQL"), self._fill_script_dialog(name, sql))
        self._find_button(self._groups_window(), "Add SQL").invoke()
        self._pump(200)

    @keyword("คัดลอก Job เข้ากลุ่ม")
    def copy_jobs(self, group, *job_names):
        self.select_group(group)
        jobs = [j.get("name") for j in self.app._current_profile_jobs()]

        def pick(dialog):
            box = next(w for w in _walk(dialog) if isinstance(w, tk.Listbox))
            box.selection_clear(0, "end")
            for n in job_names:
                box.selection_set(jobs.index(n))
            self._find_button(dialog, "Add to Group").invoke()

        self._after_dialog(self._has_title("Saved Jobs"), pick)
        self._find_button(self._groups_window(), "From Saved Jobs").invoke()
        self._pump(200)

    @keyword("แก้ SQL ของ Script")
    def edit_script(self, group, script, sql):
        self.select_group(group)
        self._select_script(script)
        self._after_dialog(self._has_title("Edit Script"), self._fill_script_dialog(script, sql))
        self._find_button(self._groups_window(), "Edit").invoke()
        self._pump(200)

    @keyword("SQL ของ Script ในกลุ่มต้องเป็น")
    def script_sql(self, group, script, sql):
        scripts = [s for s in self._group(group)["scripts"] if s.get("name") == script]
        if not scripts:
            raise AssertionError(f"Script '{script}' not in group '{group}'")
        if scripts[0].get("query", "").strip() != sql.strip():
            raise AssertionError(f"Script SQL is '{scripts[0].get('query')}'")

    @keyword("Script ในกลุ่มต้องเรียงเป็น")
    def scripts_order(self, group, *names):
        actual = [s.get("name") for s in self._group(group)["scripts"]]
        if actual != list(names):
            raise AssertionError(f"Scripts are {actual}, expected {list(names)}")

    @keyword("เลื่อน Script ขึ้น")
    def move_up(self, group, script, times=1):
        self.select_group(group)
        self._select_script(script)
        for _ in range(int(times)):
            self._find_button(self._groups_window(), "↑").invoke()
            self._pump(50)

    @keyword("กด Run Group")
    def run_group(self, group):
        self.select_group(group)
        self._find_button(self._groups_window(), "Run Group").invoke()
        self._pump(200)

    @keyword("กด Export Group to Excel")
    def export_group(self, group):
        self.select_group(group)
        self._find_button(self._groups_window(), "Export Group to Excel").invoke()
        self._pump(200)

    @keyword("หน้าต่าง Script Groups ต้องอยู่เหนือหน้าหลัก")
    def groups_above_main(self):
        order = [str(w) for w in self.root.tk.splitlist(self.root.tk.call("wm", "stackorder", self.root))]
        window = str(self._groups_window())
        main = str(self.root)
        if window not in order or order.index(window) < order.index(main):
            raise AssertionError(f"Window order (bottom → top): {order}")

    @keyword("กด Export Groups")
    def export_groups(self):
        self._find_button(self._groups_window(), "Export Groups").invoke()
        self._pump(200)

    @keyword("กด Import Groups")
    def import_groups(self):
        self._find_button(self._groups_window(), "Import Groups").invoke()
        self._pump(200)

    @keyword("ลบกลุ่ม")
    def delete_group(self, name):
        self.select_group(name)
        self.answer_next("Yes")
        self._find_button(self._groups_window(), "Delete").invoke()
        self._pump(200)

    @keyword("ปิดหน้าต่าง Script Groups")
    def close_groups(self):
        self._groups_window().destroy()
        self._pump(100)

    # ---------------------------------------------------------- export
    @keyword("กด Export Excel")
    def press_export(self):
        self.app.export_excel_btn.invoke()
        self._pump(200)

    @keyword("ชื่อไฟล์ที่เสนอตอน Export ต้องขึ้นต้นด้วย")
    def export_name_prefix(self, prefix):
        name = self.save_dialog_names[-1] if self.save_dialog_names else ""
        if not str(name).startswith(prefix) or not str(name).endswith(".xlsx"):
            raise AssertionError(f"Suggested file name is '{name}'")

    def _workbook(self):
        import openpyxl

        if not self.save_path or not os.path.exists(self.save_path):
            raise AssertionError(f"Excel file was not created: {self.save_path}")
        return openpyxl.load_workbook(self.save_path)

    def _log_workbook(self, wb):
        """Show the first rows of every sheet of the exported file in log.html."""
        import html as _html

        parts = [f"<b>ไฟล์ Excel ที่ได้:</b> {_html.escape(os.path.basename(self.save_path))}"]
        for ws in wb.worksheets:
            rows = []
            for r_idx, row in enumerate(ws.iter_rows(min_row=1, max_row=6, values_only=True)):
                tag = "th" if r_idx == 0 else "td"
                cells = "".join(
                    f'<{tag} style="border:1px solid #ccc;padding:2px 6px'
                    + (';background:#BC9BFF' if r_idx == 0 else "")
                    + f'">{_html.escape("" if v is None else str(v))}</{tag}>'
                    for v in row
                )
                rows.append(f"<tr>{cells}</tr>")
            parts.append(
                f'<div style="margin-top:6px">Sheet <b>{_html.escape(ws.title)}</b> '
                f'({ws.max_row - 1} แถว รวม SQL ท้าย Sheet)</div>'
                f'<table style="border-collapse:collapse;font-size:12px">{"".join(rows)}</table>'
            )
        logger.info("".join(parts), html=True)

    @keyword("ไฟล์ Excel ต้องมี Sheet")
    def sheets_should_be(self, *names):
        wb = self._workbook()
        self._log_workbook(wb)
        actual = wb.sheetnames
        if actual != list(names):
            raise AssertionError(f"Sheets are {actual}, expected {list(names)}")

    @keyword("หัวตารางของ Sheet ต้องเป็นสีม่วงและ freeze แถวหัว")
    def sheet_header(self, sheet):
        ws = self._workbook()[sheet]
        fill = str(ws["A1"].fill.fgColor.rgb or "")
        if not fill.upper().endswith("BC9BFF"):
            raise AssertionError(f"Header fill is {fill}")
        if ws.freeze_panes != "A2":
            raise AssertionError(f"Freeze panes is {ws.freeze_panes}")

    @keyword("Sheet ต้องมี SQL ที่ใช้รันต่อท้าย")
    def sheet_has_sql(self, sheet, sql):
        ws = self._workbook()[sheet]
        values = [str(c.value) for row in ws.iter_rows() for c in row if c.value is not None]
        if not any(sql.strip() in v for v in values):
            raise AssertionError(f"SQL '{sql}' not found in sheet {sheet}")

    @keyword("ค่าใน Sheet ต้องเป็น")
    def sheet_cell(self, sheet, cell, expected, value_type="any"):
        wb = self._workbook()
        logged = getattr(self, "_logged_files", set())
        if self.save_path not in logged:
            self._log_workbook(wb)
            logged.add(self.save_path)
            self._logged_files = logged
        value = wb[sheet][cell].value
        if str(value) != str(expected):
            raise AssertionError(f"{sheet}!{cell} is {value!r}, expected {expected!r}")
        if value_type == "text" and not isinstance(value, str):
            raise AssertionError(f"{sheet}!{cell} is {type(value).__name__}, expected text")
        if value_type == "number" and not isinstance(value, (int, float)):
            raise AssertionError(f"{sheet}!{cell} is {type(value).__name__}, expected a number")

    # ------------------------------------------------------------ stop
    @keyword("ปุ่ม Stop ต้องกดได้")
    def stop_enabled(self):
        if str(self.app.stop_btn["state"]) != "normal":
            raise AssertionError("Stop button is disabled")

    @keyword("ปุ่ม Stop ต้องกดไม่ได้")
    def stop_disabled(self):
        self._pump(400)
        if str(self.app.stop_btn["state"]) != "disabled":
            raise AssertionError("Stop button is enabled")

    @keyword("กด Stop")
    def press_stop(self):
        self.app.stop_btn.invoke()
        self._pump(100)

    @keyword("SQL ที่ใช้เวลานาน")
    def long_sql(self):
        return LONG_SQL

    # ------------------------------------------------ result windows/log
    @keyword("ตั้งค่า Open result windows เป็น")
    def set_result_windows(self, value):
        self.app.open_result_popups.set(str(value).lower() in ("true", "1", "yes", "on"))

    @keyword("ค่า Open result windows ต้องเป็น")
    def result_windows_should_be(self, value):
        expected = str(value).lower() in ("true", "1", "yes", "on")
        if bool(self.app.open_result_popups.get()) != expected:
            raise AssertionError(f"Open result windows is {self.app.open_result_popups.get()}")

    def _today_log(self):
        path = os.path.join(self.workdir, "logs", f"run_{datetime.date.today():%Y-%m-%d}.log")
        if not os.path.exists(path):
            raise AssertionError(f"Log file not found: {path}")
        with open(path, encoding="utf-8") as f:
            return f.read()

    @keyword("ไฟล์ log ของวันนี้ต้องมี")
    def log_file_contains(self, *texts):
        content = self._today_log()
        for t in texts:
            if t not in content:
                raise AssertionError(f"'{t}' not in today's log file")

    @keyword("ไฟล์ log ของวันนี้ต้องไม่มีรหัสผ่าน")
    def log_file_no_password(self):
        if TEST_PASSWORD in self._today_log():
            raise AssertionError("The password was written to the log file")
