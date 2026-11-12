"""Capture screenshots of Database Connector for the user manual.

Runs the real database_connect_gui.py, switches it between states with
root.after (no real database connection), grabs each window with
PIL.ImageGrab and draws numbered orange markers on the buttons.

The app runs from a temporary copy with demo profiles / jobs / groups, so
the real db_profiles.json, saved_jobs.json and script_groups.json are never
read or changed and no real host names or passwords show up in the images.

Output: manual/screens/<view>.png  (+ manifest.json listing every marker)
Usage : python manual/capture_screens.py
"""

import ctypes
import datetime as dt
import decimal
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import traceback

import pandas as pd
from PIL import Image, ImageDraw, ImageFont, ImageGrab

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(HERE)
SOURCE = os.path.join(PROJECT, "database_connect_gui.py")
OUT_DIR = os.path.join(HERE, "screens")

WINDOW_GEOMETRY = "1840x1000+10+10"  # physical pixels (process is DPI aware)
MARK_COLOR = (249, 115, 22)  # orange
MARK_FONT = "C:/Windows/Fonts/segoeuib.ttf"

PROFILE = "DEMO_ORACLE"
DEMO_SQL = "SELECT ACCOUNT_NO, CUSTOMER_NAME, BALANCE\nFROM ACCOUNTS\nWHERE ACCOUNT_NO IN ({ACCOUNT_LIST})"


# ---------------------------------------------------------------------------
# Demo data (written to a temp folder next to a copy of the app)
# ---------------------------------------------------------------------------
def write_demo_runtime():
    run_dir = tempfile.mkdtemp(prefix="dbc_manual_")
    shutil.copy2(SOURCE, os.path.join(run_dir, "database_connect_gui.py"))
    now = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    profiles = {
        PROFILE: {
            "db_type": "Oracle",
            "db_host": "db-demo.local",
            "db_port": "1521",
            "db_name": "ORCLPDB",
            "db_user": "demo_user",
            "db_password": "demo",
            "sql_query": DEMO_SQL,
        },
        "DEMO_POSTGRES": {
            "db_type": "PostgreSQL",
            "db_host": "pg-demo.local",
            "db_port": "5432",
            "db_name": "reporting",
            "db_user": "demo_user",
            "db_password": "demo",
            "sql_query": "SELECT\n    *\nFROM Table",
        },
        "last_used_profile": PROFILE,
    }
    jobs = [
        ("บัญชีคงเหลือรายวัน", "SELECT ACCOUNT_NO, BALANCE FROM ACCOUNTS WHERE STATUS = 'A'"),
        ("ลูกค้าใหม่เดือนนี้", "SELECT * FROM CUSTOMERS WHERE OPEN_DATE >= TRUNC(SYSDATE, 'MM')"),
        ("ตรวจรายการโอนค้าง", "SELECT * FROM TRANSFERS WHERE STATUS = 'PENDING'"),
        ("ปรับสถานะบัญชีปิด", "UPDATE ACCOUNTS SET STATUS = 'C' WHERE CLOSE_DATE IS NOT NULL"),
    ]
    saved_jobs = [
        {"name": n, "query": q, "profile": PROFILE, "db_type": "Oracle",
         "database": "ORCLPDB", "created": now}
        for n, q in jobs
    ]
    groups = {
        "version": 1,
        "groups": [
            {
                "name": "ตรวจสอบสิ้นวัน",
                "profile": PROFILE,
                "created": now,
                "scripts": [
                    {"name": "นับบัญชีเปิดใหม่", "query": "SELECT COUNT(*) FROM ACCOUNTS\nWHERE OPEN_DATE = TRUNC(SYSDATE)", "created": now},
                    {"name": "ยอดรวมตามสาขา", "query": "SELECT BRANCH, SUM(BALANCE)\nFROM ACCOUNTS\nGROUP BY BRANCH", "created": now},
                    {"name": "รายการโอนค้าง", "query": "SELECT * FROM TRANSFERS\nWHERE STATUS = 'PENDING'", "created": now},
                ],
            },
            {
                "name": "รายงานประจำเดือน",
                "profile": PROFILE,
                "created": now,
                "scripts": [
                    {"name": "ลูกค้าใหม่", "query": "SELECT * FROM CUSTOMERS", "created": now},
                ],
            },
        ],
    }
    for name, data in (
        ("db_profiles.json", profiles),
        ("saved_jobs.json", saved_jobs),
        ("script_groups.json", groups),
        ("app_settings.json", {"open_result_popups": True}),
    ):
        with open(os.path.join(run_dir, name), "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    excel_path = os.path.join(run_dir, "ACCOUNT_NO_LIST_DEMO.xlsx")
    pd.DataFrame(
        {
            "ACCOUNT_NO": [f"10010000{i:02d}" for i in range(1, 16)],
            "BRANCH": ["BKK", "CNX", "HKT", "KKC", "BKK"] * 3,
            "STATUS": ["A", "A", "C", "A", "A"] * 3,
        }
    ).to_excel(excel_path, sheet_name="Accounts", index=False)
    return run_dir, excel_path


def load_app_module(run_dir, excel_path):
    path = os.path.join(run_dir, "database_connect_gui.py")
    spec = importlib.util.spec_from_file_location("database_connect_gui_demo", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # No real file dialogs or message boxes while capturing
    module.filedialog.askopenfilename = lambda **_k: excel_path
    for name in ("showinfo", "showerror", "showwarning"):
        setattr(module.messagebox, name, lambda *a, **k: print("messagebox:", a))
    return module


def demo_result_sets():
    rows = 40
    df1 = pd.DataFrame(
        {
            "ACCOUNT_NO": [f"10010000{i:02d}" for i in range(1, rows + 1)],
            "CUSTOMER_NAME": [f"CUSTOMER {i:03d}" for i in range(1, rows + 1)],
            "BRANCH": (["BKK", "CNX", "HKT", "KKC"] * rows)[:rows],
            "BALANCE": [decimal.Decimal(f"{(i * 12345.67) % 900000:.2f}") for i in range(1, rows + 1)],
            "OPEN_DATE": [dt.datetime(2024, 1, 1, 9, 30) + dt.timedelta(days=i * 7) for i in range(rows)],
            "CLOSE_DATE": [None] * rows,
        }
    )
    df2 = pd.DataFrame(
        {
            "CUSTOMER_ID": [f"C{i:05d}" for i in range(1, 13)],
            "OPEN_DATE": [dt.date(2026, 11, i) for i in range(1, 13)],
        }
    )
    return [
        ("บัญชีคงเหลือรายวัน", df1, "SELECT ACCOUNT_NO, BALANCE FROM ACCOUNTS WHERE STATUS = 'A'"),
        ("ลูกค้าใหม่เดือนนี้", df2, "SELECT * FROM CUSTOMERS WHERE OPEN_DATE >= TRUNC(SYSDATE, 'MM')"),
    ]


# ---------------------------------------------------------------------------
# Widget lookup and capture helpers
# ---------------------------------------------------------------------------
def walk(widget):
    stack = [widget]
    while stack:
        w = stack.pop(0)
        yield w
        stack.extend(w.winfo_children())


def find_text(parent, text, cls=None, exact=False):
    """First mapped widget under parent whose text option matches."""
    for w in walk(parent):
        try:
            value = str(w.cget("text"))
        except Exception:
            continue
        hit = value.strip() == text if exact else text in value
        if hit and w.winfo_ismapped() and (cls is None or w.winfo_class() == cls):
            return w
    raise LookupError(f"widget with text {text!r} not found")


def value_checks(dialog):
    """Value check boxes of the Load Excel dialog (demo account numbers)."""
    out = []
    for w in walk(dialog):
        try:
            if str(w.cget("text")).strip().startswith("10010000") and hasattr(w, "invoke"):
                out.append(w)
        except Exception:
            pass
    return out


def find_class(parent, cls, index=0):
    found = [w for w in walk(parent) if w.winfo_class() == cls and w.winfo_ismapped()]
    return found[index]


def find_toplevel(root, title):
    for w in root.winfo_children():
        if w.winfo_class() == "Toplevel" and w.title() == title and w.winfo_exists():
            return w
    raise LookupError(f"window {title!r} not found")


def notebook_tab_rects(nb):
    """Screen rects of ttk.Notebook tabs (found with the notebook's own hit test)."""
    nb.update_idletasks()

    def tab_at(x, y):
        hit = nb.tk.call(nb._w, "identify", "tab", x, y)
        return None if hit == "" else int(hit)

    cols = {}
    for y in range(0, 60, 2):
        for x in range(0, nb.winfo_width(), 2):
            i = tab_at(x, y)
            if i is None:
                continue
            x0, y0, x1, y1 = cols.get(i, (x, y, x, y))
            cols[i] = (min(x0, x), min(y0, y), max(x1, x + 2), max(y1, y + 2))
    return {
        i: (nb.winfo_rootx() + x0, nb.winfo_rooty() + y0, x1 - x0, y1 - y0)
        for i, (x0, y0, x1, y1) in cols.items()
    }


def screen_rect(target):
    if isinstance(target, tuple):
        return target
    target.update_idletasks()
    return (target.winfo_rootx(), target.winfo_rooty(), target.winfo_width(), target.winfo_height())


class Capturer:
    def __init__(self, root):
        self.root = root
        self.raw = {}  # name -> (image, origin)
        self.manifest = {}
        os.makedirs(OUT_DIR, exist_ok=True)

    def grab(self, name, top, crop=None):
        """Grab `top` (whole window client area) or just the `crop` widget."""
        try:
            top.attributes("-topmost", True)
        except Exception:
            pass
        top.lift()
        top.update()
        x, y, w, h = screen_rect(crop if crop is not None else top)
        image = ImageGrab.grab(bbox=(x, y, x + w, y + h))
        self.raw[name] = (image, (x, y))
        image.save(os.path.join(OUT_DIR, f"raw_{name}.png"))
        return name

    def view(self, view_name, raw_name, marks, corner="tl"):
        """Save an annotated copy of a raw capture.

        marks: list of (number, target, label[, corner]); target is a widget,
        a list of widgets, or a screen rect (x, y, w, h). corner places the
        number: "tl", "tr" or "bl" of the marked box.
        """
        image, (ox, oy) = self.raw[raw_name]
        rects = []
        for mark in marks:
            number, target, label = mark[:3]
            where = mark[3] if len(mark) > 3 else corner
            targets = target if isinstance(target, list) else [target]
            for t in targets:
                x, y, w, h = screen_rect(t)
                rects.append((number, (x - ox, y - oy, w, h), label, where))
        annotated = draw_marks(image, rects)
        annotated.save(os.path.join(OUT_DIR, f"{view_name}.png"))
        self.manifest[view_name] = {
            "size": annotated.size,
            "marks": [{"n": n, "label": label, "rect": r} for n, r, label, _c in rects],
        }
        print(f"saved {view_name}.png  ({len(rects)} marks)")


def draw_marks(image, rects):
    image = image.convert("RGB").copy()
    draw = ImageDraw.Draw(image)
    W, H = image.size
    radius = max(14, round(W / 85))
    font = ImageFont.truetype(MARK_FONT, round(radius * 1.15))
    line = max(2, radius // 6)
    for _number, (x, y, w, h), _label, _corner in rects:
        draw.rounded_rectangle((x - 2, y - 2, x + w + 2, y + h + 2), radius=6, outline=MARK_COLOR, width=line)
    for number, (x, y, w, h), _label, corner in rects:
        cx = x + w + radius // 3 if corner == "tr" else x - radius // 3
        cy = y + h + radius // 3 if corner == "bl" else y - radius // 3
        if corner == "cr":  # inside the box, right end (empty part of an entry)
            cx, cy = x + w - radius - 8, y + h // 2
        elif corner == "c":
            cx, cy = x + w // 2, y + h // 2
        cx = min(max(cx, radius + 1), W - radius - 1)
        cy = min(max(cy, radius + 1), H - radius - 1)
        draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), fill=MARK_COLOR, outline="white", width=2)
        draw.text((cx, cy), str(number), fill="white", font=font, anchor="mm")
    return image


# ---------------------------------------------------------------------------
# States
# ---------------------------------------------------------------------------
def build_steps(app, root, cap):
    W = {}  # widgets shared between steps

    def layout_parts():
        top = root.grid_slaves(row=0, column=0)[0]
        body = root.grid_slaves(row=2, column=0)[0]
        status = root.grid_slaves(row=3, column=0)[0]
        sidebar, workspace = (root.nametowidget(p) for p in body.panes())
        split = workspace.winfo_children()[0]
        query_card, results_card = (root.nametowidget(p) for p in split.panes())
        return dict(top=top, sidebar=sidebar, workspace=workspace, query=query_card,
                    results=results_card, status=status)

    def s_main_prepare():
        # Look of a connected session (no real connection is opened)
        app.status_label.config(text="✅ Connected (Oracle)", foreground="#27ae60")
        app.execute_btn.config(state="normal")
        app.inspect_btn.config(state="normal")
        jobs = app._current_profile_jobs()
        for job in jobs[:2]:
            app.toggle_job_checked(job, True)
        app.update_jobs_list()
        app._refresh_job_selection_ui()
        app.sql_context.mark_set("insert", "3.0")

    def s_main_capture():
        p = layout_parts()
        W.update(p)
        cap.grab("main", root)
        top = p["top"]
        cap.view("overview", "main", [
            (1, p["top"], "Top bar"),
            (2, p["sidebar"], "Sidebar"),
            (3, p["query"], "SQL editor"),
            (4, p["results"], "Results"),
            (5, p["status"], "Status bar"),
        ])
        cap.view("topbar", "main", [
            (1, app.profile_combo, "Profile"),
            (2, find_text(top, "Database / Service").master, "Target summary"),
            (3, app.creds_toggle_btn, "Details"),
            (4, find_text(top, "Connected", cls="TLabel"), "Connection badge"),
            (5, app.connect_btn, "Connect"),
            (6, find_text(top, "＋ New"), "New"),
            (7, find_text(top, "Save", exact=True), "Save"),
            (8, find_text(top, "Import", exact=True), "Import"),
            (9, find_text(top, "Export", exact=True), "Export"),
            (10, find_text(top, "⋯", exact=True), "More menu"),
        ])
        sb = p["sidebar"]
        first_row_actions = find_text(sb, "▶", exact=True).master
        row_buttons = first_row_actions.winfo_children()
        row_check = [w for w in walk(app.jobs_container) if w.winfo_class() == "Checkbutton"][0]
        cap.grab("sidebar", root, crop=sb)
        cap.view("sidebar", "sidebar", [
            (1, find_text(sb, "Saved Jobs"), "Saved Jobs tab"),
            (2, find_text(sb, "Script Groups"), "Script Groups tab"),
            (3, app.run_all_btn, "Run all / Run selected"),
            (4, app.export_excel_btn, "Export"),
            (5, find_text(sb, "Select all"), "Select all"),
            (6, app.delete_selected_btn, "Delete (n)"),
            (7, row_check, "Row checkbox"),
            (8, row_buttons[0], "Row run"),
            (9, row_buttons[1], "Row edit"),
            (10, row_buttons[2], "Row delete"),
            (11, find_text(sb, "Save", cls="TButton"), "Preset save"),
            (12, find_text(sb, "Load", cls="TButton"), "Preset load"),
        ])
        cap.view("steps", "main", [
            (1, find_text(top, "＋ New"), "New profile"),
            (2, app.connect_btn, "Connect"),
            (3, [app.load_excel_btn, app.execute_btn], "Load Excel / Run"),
            (4, app.save_job_btn, "Save as Job"),
            (5, [app.run_all_btn, app.export_excel_btn], "Run selected / Export"),
            (6, find_text(sb, "Script Groups"), "Script Groups"),
        ])

    def s_details_open():
        app.creds_toggle_btn.invoke()

    def s_details_capture():
        top = W["top"]
        cap.grab("details", root)
        cap.view("details", "details", [
            (1, app.db_type, "Database type"),
            (2, app.db_host, "Host"),
            (3, app.db_port, "Port"),
            (4, app.db_name, "Database / Service"),
            (5, app.db_user, "User"),
            (6, app.db_password, "Password", "c"),
            (7, app.toggle_password_btn, "Eye icon", "tr"),
            (8, app.creds_toggle_btn, "Details toggle", "tr"),
            (9, find_text(top, "Save", exact=True), "Save profile", "bl"),
        ], corner="cr")
        app.creds_toggle_btn.invoke()  # close the drawer again

    def s_excel_open():
        app.load_excel_template_dialog()

    def s_excel_tick():
        dialog = find_toplevel(root, "Load Excel SQL Parameters")
        W["excel"] = dialog
        values = value_checks(dialog)
        for w in values[:4]:
            w.invoke()

    def s_excel_capture():
        d = W["excel"]
        cap.grab("load_excel", d)
        combos = [w for w in walk(d) if w.winfo_class() == "TCombobox"]
        texts = [w for w in walk(d) if w.winfo_class() == "Text" and w.winfo_ismapped()]
        value_box = value_checks(d)[0]
        cap.view("load_excel", "load_excel", [
            (1, combos[0], "Sheet"),
            (2, combos[1], "Parameter"),
            (3, find_class(d, "Listbox"), "Column list"),
            (4, value_box.master.master, "Values"),
            (5, find_text(d, "Select All"), "Select All"),
            (6, find_text(d, "ล้างที่เลือก"), "Clear"),
            (7, find_text(d, "③"), "Selected values"),
            (8, texts[-1], "SQL preview"),
            (9, find_text(d, "Confirm"), "Confirm"),
            (10, find_text(d, "ยกเลิก", exact=True), "Cancel"),
        ])
        W["excel_texts"] = [(str(t), t.winfo_height()) for t in texts]
        find_text(d, "Confirm").invoke()  # put the values into the SQL

    def s_editor_capture():
        q = W["query"]
        cap.grab("editor", root, crop=q)
        cap.view("editor", "editor", [
            (1, app.execute_btn, "Run"),
            (2, app.load_excel_btn, "Load Excel"),
            (3, app.reset_sql_template_btn, "Reset template"),
            (4, app.save_job_btn, "Save as Job"),
            (5, app.inspect_btn, "Tables"),
            (6, find_text(q, "Excel parameter:"), "Excel strip"),
            (7, find_text(q, "เปลี่ยนค่า"), "Change values"),
            (8, app.sql_context, "Editor", "tr"),
        ])

    def s_groups_open():
        app.show_script_groups_dialog()

    def s_groups_select():
        d = app._script_groups_window
        groups_box, scripts_box = [w for w in walk(d) if w.winfo_class() == "Listbox"][:2]
        groups_box.selection_set(0)
        groups_box.event_generate("<<ListboxSelect>>")
        d.update()
        scripts_box.selection_clear(0, "end")
        scripts_box.selection_set(1)
        scripts_box.event_generate("<<ListboxSelect>>")

    def s_groups_capture():
        d = app._script_groups_window
        cap.grab("groups", d)
        lists = [w for w in walk(d) if w.winfo_class() == "Listbox"]
        preview = [w for w in walk(d) if w.winfo_class() == "Text" and w.winfo_ismapped()][-1]
        cap.view("groups", "groups", [
            (1, find_text(d, "New Group"), "New Group"),
            (2, lists[0], "Group list"),
            (3, find_text(d, "Rename"), "Rename"),
            (4, find_text(d, "🗑  Delete"), "Delete group"),
            (5, lists[1], "Script list"),
            (6, [find_text(d, "↑", exact=True), find_text(d, "↓", exact=True)], "Up / Down"),
            (7, find_text(d, "✎ Edit"), "Edit"),
            (8, find_text(d, "Remove"), "Remove"),
            (9, find_text(d, "Add SQL"), "Add SQL"),
            (10, find_text(d, "From Saved Jobs"), "From Saved Jobs"),
            (11, preview, "SQL preview"),
            (12, find_text(d, "Run Group"), "Run Group"),
            (13, find_text(d, "Export Group to Excel"), "Export Group"),
            (14, find_text(d, "Stop"), "Stop"),
            (15, find_text(d, "Import Groups"), "Import Groups"),
            (16, find_text(d, "Export Groups"), "Export Groups"),
        ])
        d.destroy()

    def s_confirm_open():
        jobs = [
            {"name": "ปรับสถานะบัญชีปิด",
             "query": "UPDATE ACCOUNTS SET STATUS = 'C' WHERE CLOSE_DATE IS NOT NULL"},
            {"name": "ล้างตารางชั่วคราว", "query": "DELETE FROM TMP_DAILY_LOAD"},
        ]
        root.after(10, lambda: app._confirm_data_change(jobs))

    def s_confirm_capture():
        d = find_toplevel(root, "Confirm Data Change")
        cap.grab("confirm", d)
        yellow = find_text(d, "ปรับสถานะบัญชีปิด").master
        info = find_text(d, "Profile", exact=True).master
        cap.view("confirm", "confirm", [
            (1, find_text(d, "ยืนยันการแก้ไขข้อมูล").master, "Heading"),
            (2, yellow, "Statements"),
            (3, info, "Profile / Database"),
            (4, find_text(d, "ย้อนกลับไม่ได้"), "Warning"),
            (5, find_text(d, "ยกเลิก", exact=True), "Cancel"),
            (6, find_text(d, "รันและ commit"), "Run and commit"),
        ])
        find_text(d, "ยกเลิก", exact=True).invoke()

    def s_results_show():
        app._show_results_grid_sets(demo_result_sets())

    def s_results_capture():
        r = W["results"]
        tabs = notebook_tab_rects(app.results_notebook)
        cap.grab("results", root, crop=r)
        cap.view("results", "results", [
            (1, tabs[0], "Results Grid tab"),
            (2, tabs[1], "Execution Logs tab"),
            (3, tabs[2], "Error & Debug tab"),
            (4, find_text(r, "Open result windows"), "Open result windows"),
            (5, app._rg_set_btn, "Result set picker"),
            (6, app._rg_info, "Rows x columns"),
            (7, [app._rg_prev_btn, app._rg_next_btn], "Prev / Next"),
            (8, app._rg_export_csv_btn, "Export CSV"),
            (9, app._rg_export_xlsx_btn, "Export Excel"),
            (10, app._rg_tree, "Grid"),
        ])

    def s_running_start():
        app._batch_running = True
        app._ui_progress = {"total": 4, "index": 2, "name": "ลูกค้าใหม่เดือนนี้", "kind": "jobs"}

    def s_running_capture():
        r = W["results"]
        status = W["status"]
        cap.grab("running", root)
        banner_text = find_text(r, "กำลังรัน Job")
        banner = banner_text.master.master
        cap.view("running", "running", [
            (1, banner_text, "Banner text"),
            (2, find_class(banner, "TProgressbar"), "Progress", "bl"),
            (3, find_text(banner, "Stop"), "Banner stop"),
            (4, find_text(status, "Running"), "Status Running"),
        ])
        app._batch_running = False

    return [
        (s_main_prepare, 1500),
        (s_main_capture, 300),
        (s_details_open, 900),
        (s_details_capture, 300),
        (s_excel_open, 1500),
        (s_excel_tick, 900),
        (s_excel_capture, 1200),
        (s_editor_capture, 300),
        (s_groups_open, 1200),
        (s_groups_select, 900),
        (s_groups_capture, 400),
        (s_confirm_open, 1200),
        (s_confirm_capture, 500),
        (s_results_show, 1000),
        (s_results_capture, 300),
        (s_running_start, 1500),
        (s_running_capture, 500),
    ]


def main():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)  # sharp text, real pixel sizes
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

    run_dir, excel_path = write_demo_runtime()
    module = load_app_module(run_dir, excel_path)

    import tkinter as tk

    root = tk.Tk()
    app = module.DatabaseConnectorGUI(root)
    root.geometry(WINDOW_GEOMETRY)
    root.attributes("-topmost", True)
    cap = Capturer(root)
    steps = build_steps(app, root, cap)
    errors = []

    def run(i=0):
        if i >= len(steps):
            root.after(300, root.destroy)
            return
        fn, delay = steps[i]
        try:
            fn()
        except Exception:
            errors.append(fn.__name__)
            traceback.print_exc()
        root.after(delay, lambda: run(i + 1))

    root.after(2000, run)
    root.mainloop()

    with open(os.path.join(OUT_DIR, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(cap.manifest, f, indent=2, ensure_ascii=False)
    shutil.rmtree(run_dir, ignore_errors=True)
    if errors:
        print("FAILED steps:", ", ".join(errors))
        sys.exit(1)
    print("done:", OUT_DIR)


if __name__ == "__main__":
    main()
