# --- Standard library ---
import base64
import ctypes
import datetime as _dt
import decimal
import json
import os
import re
import sys
import threading
import traceback
import tkinter as tk
import tkinter.font as tkfont
from tkinter import filedialog, messagebox, scrolledtext, ttk

# --- Third-party ---
import pandas as pd
from sqlalchemy import create_engine, inspect, text

# ===================================================
# Show query results the same way DBeaver does
# (column names as the database returns them, exact numbers,
#  [NULL] for nulls, DBeaver's default date/time formats)
# ===================================================

DB_NULL_TEXT = "[NULL]"
DB_TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S.%f"  # shown as yyyy-MM-dd HH:mm:ss.SSS
DB_DATE_FORMAT = "%Y-%m-%d"
DB_TIME_FORMAT = "%H:%M:%S"


def format_db_value(value, null_text=DB_NULL_TEXT):
    """Text for one result cell, matching DBeaver's grid."""
    if value is None or value is pd.NaT:
        return null_text
    if isinstance(value, float):
        if value != value:  # NaN
            return null_text
        if value.is_integer() and abs(value) < 1e16:
            return str(int(value))
        return format(decimal.Decimal(repr(value)), "f")
    if isinstance(value, decimal.Decimal):
        if value.is_nan():
            return null_text
        return format(value, "f")
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (_dt.datetime, pd.Timestamp)):
        return value.strftime(DB_TIMESTAMP_FORMAT)[:-3]  # milliseconds
    if isinstance(value, _dt.date):
        return value.strftime(DB_DATE_FORMAT)
    if isinstance(value, _dt.time):
        return value.strftime(DB_TIME_FORMAT)
    if isinstance(value, (bytes, bytearray, memoryview)):
        return bytes(value).hex().upper()
    return str(value)


EXCEL_MAX_EXACT_DIGITS = 15  # Excel keeps only 15 significant digits


def excel_db_value(value):
    """Value for an export cell: numbers and dates keep their real type.

    NULL becomes [NULL]. Numbers longer than Excel can store exactly
    (more than 15 digits, e.g. long account numbers) are written as text
    so no digit is lost.
    """
    if value is None or value is pd.NaT:
        return DB_NULL_TEXT
    if isinstance(value, bool):
        return format_db_value(value)
    if isinstance(value, float):
        if value != value:
            return DB_NULL_TEXT
        return int(value) if value.is_integer() and abs(value) < 1e15 else value
    if isinstance(value, (int, decimal.Decimal)):
        number = decimal.Decimal(value)
        if not number.is_finite():
            return DB_NULL_TEXT
        if len(number.as_tuple().digits) > EXCEL_MAX_EXACT_DIGITS:
            return format_db_value(value)
        return int(number) if number == number.to_integral_value() else float(number)
    if isinstance(value, pd.Timestamp):
        value = value.to_pydatetime()
    if isinstance(value, _dt.datetime):
        return value.replace(tzinfo=None)
    if isinstance(value, (_dt.date, _dt.time)):
        return value
    return format_db_value(value)


def excel_number_format(value):
    """Excel display format for a cell written from excel_db_value()."""
    if isinstance(value, _dt.datetime):
        return "yyyy-mm-dd hh:mm:ss.000"
    if isinstance(value, _dt.date):
        return "yyyy-mm-dd"
    if isinstance(value, _dt.time):
        return "hh:mm:ss"
    if isinstance(value, bool):
        return "@"
    if isinstance(value, int):
        return "0"
    if isinstance(value, float):
        return "General"
    return "@"


# ===================================================
# Password protection for db_profiles.json
# Uses Windows DPAPI (encrypted per Windows user account).
# Old profiles with plain-text passwords are still read normally
# and become encrypted the next time profiles are saved.
# ===================================================

_DPAPI_PREFIX = "dpapi:"


def _dpapi_transform(data, protect):
    from ctypes import wintypes

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    buffer = ctypes.create_string_buffer(data, len(data))
    blob_in = DATA_BLOB(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char)))
    blob_out = DATA_BLOB()
    crypt32 = ctypes.windll.crypt32
    func = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
    CRYPTPROTECT_UI_FORBIDDEN = 0x01
    ok = func(
        ctypes.byref(blob_in),
        None,
        None,
        None,
        None,
        CRYPTPROTECT_UI_FORBIDDEN,
        ctypes.byref(blob_out),
    )
    if not ok:
        raise ctypes.WinError()
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(ctypes.cast(blob_out.pbData, ctypes.c_void_p))


def protect_password(plain):
    """Encrypt a password for storage. Falls back to plain text if DPAPI is unavailable."""
    if not plain or sys.platform != "win32" or str(plain).startswith(_DPAPI_PREFIX):
        return plain
    try:
        encrypted = _dpapi_transform(str(plain).encode("utf-8"), protect=True)
        return _DPAPI_PREFIX + base64.b64encode(encrypted).decode("ascii")
    except Exception as e:
        print(f"Password encryption failed, saving as plain text: {e}")
        return plain


def unprotect_password(stored):
    """Decrypt a stored password. Plain-text (old format) values are returned as-is."""
    if not stored or not str(stored).startswith(_DPAPI_PREFIX):
        return stored
    try:
        raw = base64.b64decode(str(stored)[len(_DPAPI_PREFIX) :])
        return _dpapi_transform(raw, protect=False).decode("utf-8")
    except Exception as e:
        # e.g. file copied from another Windows user/computer
        print(f"Cannot decrypt saved password (please re-enter it): {e}")
        return ""


# ======================================================================
# UI KIT — Modern Enterprise theme (presentation only, no app logic)
# ======================================================================
UI = {
    "bg": "#F8FAFC",
    "navy": "#1E293B",
    "card": "#FFFFFF",
    "border": "#E2E8F0",
    "border_strong": "#CBD5E1",
    "text": "#0F172A",
    "muted": "#64748B",
    "subtle": "#94A3B8",
    "surface": "#F8FAFC",
    "hover": "#F1F5F9",
    "primary": "#2563EB",
    "primary_hover": "#1D4ED8",
    "primary_disabled": "#BFDBFE",
    "primary_soft": "#EFF6FF",
    "success": "#16A34A",
    "success_hover": "#15803D",
    "success_soft": "#F0FDF4",
    "danger": "#DC2626",
    "danger_soft": "#FEF2F2",
    "danger_hover": "#FEE2E2",
    "ok": "#16A34A",
    "warn": "#D97706",
    "off": "#94A3B8",
}
UI_FONT = ("Segoe UI", 10)
UI_FONT_SM = ("Segoe UI", 9)

# Segoe MDL2 Assets glyphs (built into Windows 10/11)
PASSWORD_ICON_SHOW = ""  # eye
PASSWORD_ICON_HIDE = ""  # eye with slash
UI_FONT_SEMI = ("Segoe UI Semibold", 10)
UI_FONT_LABEL = ("Segoe UI Semibold", 9)
UI_FONT_TITLE = ("Segoe UI Semibold", 13)
UI_FONT_MONO = ("Consolas", 10)


def ui_bind_hover(btn, normal_bg, hover_bg):
    """Visual hover feedback only — ignored while the button is disabled."""

    def _enter(_e):
        if str(btn["state"]) != "disabled":
            btn.config(bg=hover_bg)

    def _leave(_e):
        if str(btn["state"]) != "disabled":
            btn.config(bg=normal_bg)

    btn.bind("<Enter>", _enter, add="+")
    btn.bind("<Leave>", _leave, add="+")


def ui_button_style(kind="secondary", size="md"):
    """tk.Button option dict for the given visual kind."""
    pad = {"sm": (10, 3), "md": (14, 6), "lg": (22, 8)}[size]
    font = UI_FONT_SM if size == "sm" else UI_FONT
    base = dict(
        relief="flat",
        bd=0,
        highlightthickness=0,
        cursor="hand2",
        padx=pad[0],
        pady=pad[1],
        font=font,
    )
    if kind == "primary":
        base.update(
            bg=UI["primary"],
            fg="#FFFFFF",
            activebackground=UI["primary_hover"],
            activeforeground="#FFFFFF",
            disabledforeground="#EFF6FF",
            font=UI_FONT_LABEL if size == "sm" else UI_FONT_SEMI,
        )
    elif kind == "success":
        base.update(
            bg=UI["success"],
            fg="#FFFFFF",
            activebackground=UI["success_hover"],
            activeforeground="#FFFFFF",
            disabledforeground="#DCFCE7",
            font=UI_FONT_LABEL if size == "sm" else UI_FONT_SEMI,
        )
    elif kind == "danger":
        base.update(
            bg=UI["danger_soft"],
            fg=UI["danger"],
            activebackground=UI["danger_hover"],
            activeforeground=UI["danger"],
            disabledforeground=UI["subtle"],
        )
    else:  # secondary
        base.update(
            bg=UI["card"],
            fg=UI["text"],
            activebackground=UI["hover"],
            activeforeground=UI["text"],
            disabledforeground=UI["subtle"],
        )
    return base


_UI_HOVER = {
    "primary": ("primary", "primary_hover"),
    "success": ("success", "success_hover"),
    "danger": ("danger_soft", "danger_hover"),
    "secondary": ("card", "hover"),
}


# ----------------------------------------------------------------------
# Rounded components (Figma look): Tk widgets have no corner radius, so
# rounded, anti-aliased images are generated here and used as stretchable
# (9-slice) ttk elements for buttons, inputs, pills and tabs, and as the
# indicator images of check / radio buttons. Presentation only.
# ----------------------------------------------------------------------
import base64 as _b64
import math as _math
import struct as _struct
import zlib as _zlib

ROUND = {"theme": None}


def _rgb(hex_color):
    c = hex_color.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def _png_rgba(w, h, rows):
    raw = b"".join(b"\x00" + bytes(r) for r in rows)

    def chunk(kind, data):
        return (_struct.pack(">I", len(data)) + kind + data
                + _struct.pack(">I", _zlib.crc32(kind + data) & 0xFFFFFFFF))

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", _struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", _zlib.compress(raw)) + chunk(b"IEND", b""))


def _sdf_round_rect(px, py, w, h, r, inset=0.0):
    hw, hh, rr = w / 2 - inset, h / 2 - inset, max(r - inset, 0.0)
    qx, qy = abs(px - w / 2) - (hw - rr), abs(py - h / 2) - (hh - rr)
    return _math.hypot(max(qx, 0), max(qy, 0)) + min(max(qx, qy), 0) - rr


def _seg_dist(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return _math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def _make_image(w, h, r, fill=None, border=None, bw=1.0, stroke=None, stroke_color=None,
                stroke_w=1.6, underline=None):
    """Anti-aliased rounded rectangle as a PhotoImage.

    Big plain shapes are built from a small one (corners computed, middle row /
    column repeated), so a large centre is cheap — and ttk draws it in one go
    instead of tiling a tiny centre thousands of times.
    """
    core = int(2 * _math.ceil(max(r, bw)) + 6)
    if stroke is None and (w > core or h > core):
        sw, sh = min(w, core), min(h, core)
        small = _image_rows(sw, sh, r, fill, border, bw, None, None, stroke_w, underline)
        mx, my = sw // 2, sh // 2
        rows = []
        for row in small:
            mid = row[mx * 4:(mx + 1) * 4]
            rows.append(row[:mx * 4] + mid * (w - sw + 1) + row[(mx + 1) * 4:])
        rows = rows[:my] + [rows[my]] * (h - sh + 1) + rows[my + 1:]
    else:
        rows = _image_rows(w, h, r, fill, border, bw, stroke, stroke_color, stroke_w, underline)
    return tk.PhotoImage(data=_b64.b64encode(_png_rgba(w, h, rows)))


def _image_rows(w, h, r, fill, border, bw, stroke, stroke_color, stroke_w, underline):
    f = _rgb(fill) if fill else None
    b = _rgb(border) if border else None
    s = _rgb(stroke_color) if stroke_color else None
    u = _rgb(underline) if underline else None
    rows = []
    for y in range(h):
        row = []
        for x in range(w):
            px, py = x + 0.5, y + 0.5
            layers = []  # (colour, coverage) painted bottom → top
            if f or b:
                outer = min(max(0.5 - _sdf_round_rect(px, py, w, h, r), 0.0), 1.0)
                inner = min(max(0.5 - _sdf_round_rect(px, py, w, h, r, bw), 0.0), 1.0) if b else outer
                if f:
                    layers.append((f, inner))
                if b:
                    layers.append((b, max(outer - inner, 0.0)))
            if u and y >= h - 2:
                layers.append((u, 1.0))
            if s and stroke:
                d = min(_seg_dist(px, py, *stroke[i], *stroke[i + 1]) for i in range(len(stroke) - 1))
                layers.append((s, min(max(stroke_w / 2 + 0.5 - d, 0.0), 1.0)))
            a, col = 0.0, [0.0, 0.0, 0.0]
            for c, cov in layers:  # "over" compositing
                if cov <= 0:
                    continue
                na = cov + a * (1 - cov)
                col = [(c[i] * cov + col[i] * a * (1 - cov)) / na for i in range(3)]
                a = na
            row += [int(round(v)) for v in col] + [int(round(255 * a))]
        rows.append(row)
    return rows


class RoundTheme:
    """Registers the rounded ttk elements/styles once per application."""

    BUTTONS = {
        # kind: (normal, hover, pressed, disabled) as (fill, border); fg, disabled fg, bold
        "primary": ((("#2563EB", None), ("#1D4ED8", None), ("#1E40AF", None), ("#BFDBFE", None)), "#FFFFFF", "#EFF6FF", True),
        "success": ((("#16A34A", None), ("#15803D", None), ("#166534", None), ("#BBF7D0", None)), "#FFFFFF", "#F0FDF4", True),
        "danger": ((("#FEF2F2", None), ("#FEE2E2", None), ("#FECACA", None), ("#FEF2F2", None)), "#DC2626", "#FCA5A5", False),
        "secondary": ((("#FFFFFF", "#CBD5E1"), ("#F1F5F9", "#CBD5E1"), ("#E2E8F0", "#94A3B8"), ("#F8FAFC", "#E2E8F0")), "#0F172A", "#94A3B8", False),
        "secondary_focus": ((("#FFFFFF", "#60A5FA"), ("#F1F5F9", "#60A5FA"), ("#E2E8F0", "#2563EB"), ("#F8FAFC", "#E2E8F0")), "#0F172A", "#94A3B8", False),
        "soft": ((("#DBEAFE", None), ("#BFDBFE", None), ("#93C5FD", None), ("#EFF6FF", None)), "#2563EB", "#93C5FD", True),
        "ghost": (((None, None), ("#F1F5F9", None), ("#E2E8F0", None), (None, None)), "#2563EB", "#94A3B8", False),
        "ghost_muted": (((None, None), ("#F1F5F9", None), ("#E2E8F0", None), (None, None)), "#64748B", "#94A3B8", False),
        "ghost_danger": (((None, None), ("#FEF2F2", None), ("#FEE2E2", None), (None, None)), "#DC2626", "#FCA5A5", False),
    }
    PADDING = {"lg": (18, 8), "md": (14, 6), "sm": (10, 4), "icon": (4, 1)}
    PILLS = {
        "success": ("#DCFCE7", "#16A34A"), "danger": ("#FEE2E2", "#DC2626"), "warn": ("#FEF3C7", "#D97706"),
        "info": ("#DBEAFE", "#2563EB"), "neutral": ("#F1F5F9", "#64748B"),
    }

    def __init__(self, style):
        self.style = style
        self.images = []  # keep PhotoImages alive
        self._styles = set()
        self._button_elements = {}

        def img(*a, **k):
            i = _make_image(*a, **k)
            self.images.append(i)
            return i

        self._img = img
        # inputs: rounded field (normal / focus / disabled) + chevron
        field = img(320, 44, 6, "#FFFFFF", "#CBD5E1")
        field_focus = img(320, 44, 6, "#FFFFFF", "#2563EB", bw=1.6)
        field_dis = img(320, 44, 6, "#F8FAFC", "#E2E8F0")
        style.element_create("R.field", "image", field, ("disabled", field_dis), ("focus", field_focus),
                             border=7, sticky="nsew", width=24, height=24)
        chevron = img(18, 16, 0, stroke=[(5, 6), (9, 10), (13, 6)], stroke_color="#64748B", stroke_w=1.6)
        style.element_create("R.downarrow", "image", chevron, sticky="")
        style.layout("Fluent.TEntry", [("R.field", {"sticky": "nsew", "children": [
            ("Entry.padding", {"sticky": "nsew", "children": [("Entry.textarea", {"sticky": "nsew"})]})]})])
        style.layout("TEntry", style.layout("Fluent.TEntry"))
        combo = [("R.field", {"sticky": "nsew", "children": [
            ("R.downarrow", {"side": "right", "sticky": ""}),
            ("Combobox.padding", {"expand": "1", "sticky": "nsew", "children": [
                ("Combobox.textarea", {"sticky": "nsew"})]})]})]
        style.layout("Fluent.TCombobox", combo)
        style.layout("TCombobox", combo)
        for name in ("Fluent.TCombobox", "TCombobox"):
            style.configure(name, padding=(8, 5, 4, 5))
        # check / radio indicators
        self.check_off = img(18, 18, 4.5, "#FFFFFF", "#94A3B8", bw=1.4)
        self.check_on = img(18, 18, 4.5, "#2563EB", stroke=[(4.5, 9.5), (7.6, 12.6), (13.5, 5.8)],
                            stroke_color="#FFFFFF", stroke_w=2.0)
        self.radio_off = img(18, 18, 9, "#FFFFFF", "#94A3B8", bw=1.4)
        self.radio_on = img(18, 18, 9, "#FFFFFF", "#2563EB", bw=5.0)
        # tabs: blue underline when selected, light hover
        tab_idle = img(160, 44, 0)
        tab_hover = img(160, 44, 6, "#F1F5F9")
        tab_sel = img(160, 44, 0, underline="#2563EB")
        style.element_create("R.tab", "image", tab_idle, ("selected", tab_sel), ("active", tab_hover),
                             border=(5, 5, 5, 3), sticky="nsew", width=12, height=12)
        style.layout("Fluent.TNotebook.Tab", [("R.tab", {"sticky": "nsew", "children": [
            ("Notebook.padding", {"side": "top", "sticky": "nsew", "children": [
                ("Notebook.label", {"side": "top", "sticky": ""})]})]})])
        style.configure("Fluent.TNotebook.Tab", padding=(14, 8), background=UI["card"])
        style.map("Fluent.TNotebook.Tab", background=[("selected", UI["card"])],
                  foreground=[("selected", UI["primary"]), ("active", UI["text"])])
        # pills (badges)
        for tone, (bg, fg) in self.PILLS.items():
            style.element_create(f"R.pill.{tone}", "image", img(240, 28, 12, bg), border=12, sticky="nsew",
                                 width=26, height=24)

        # rounded LabelFrames (dialogs)
        lf = img(600, 400, 8, "#FFFFFF", "#E2E8F0")
        style.element_create("R.lf", "image", lf, border=9, sticky="nsew", width=20, height=20)
        style.layout("TLabelframe", [("R.lf", {"sticky": "nsew"})])
        self._frame_elements = {}
        self._tk_button_images = {}

    # -- cards --------------------------------------------------------------
    def frame_style(self, fill, border, radius, bg):
        key = (fill.lower(), (border or "").lower(), radius)
        if key not in self._frame_elements:
            element = f"R.card.{fill.lstrip('#')}.{(border or 'none').lstrip('#')}.{radius}"
            self.style.element_create(element, "image", self._img(900, 600, radius, fill, border),
                                      border=radius + 2, sticky="nsew",
                                      width=2 * radius + 6, height=2 * radius + 6)
            self._frame_elements[key] = element
        name = f"{self._frame_elements[key]}.{bg.lstrip('#').lower()}.TFrame".replace("R.card.", "Rc")
        if name not in self._styles:
            self.style.layout(name, [(self._frame_elements[key], {"sticky": "nsew"})])
            self.style.configure(name, background=bg)
            self._styles.add(name)
        return name

    def tk_button_images(self, kind, w, h):
        key = (kind, w, h)
        if key not in self._tk_button_images:
            states, _fg, _dfg, _bold = self.BUTTONS[kind]
            n, hv, pr, d = [self._img(w, h, 6, fill, border) for fill, border in states]
            self._tk_button_images[key] = {"normal": n, "hover": hv, "pressed": pr, "disabled": d}
        return self._tk_button_images[key]

    # -- buttons ------------------------------------------------------------
    def _button_element(self, kind):
        if kind not in self._button_elements:
            states, _fg, _dfg, _bold = self.BUTTONS[kind]
            (n, h, p, d) = [self._img(320, 48, 6, fill, border) for fill, border in states]
            name = f"R.btn.{kind}"
            self.style.element_create(name, "image", n, ("disabled", d), ("pressed", p), ("active", h),
                                      border=7, sticky="nsew", width=24, height=24)
            self._button_elements[kind] = name
        return self._button_elements[kind]

    def button_style(self, kind, size, bg):
        kind = kind if kind in self.BUTTONS else "secondary"
        size = size if size in self.PADDING else "md"
        name = f"{kind}.{size}.{bg.lstrip('#').lower()}.R.TButton"
        if name not in self._styles:
            _states, fg, dfg, bold = self.BUTTONS[kind]
            element = self._button_element(kind)
            self.style.layout(name, [(element, {"sticky": "nsew", "children": [
                ("Button.padding", {"sticky": "nsew", "children": [("Button.label", {"sticky": "nsew"})]})]})])
            font_size = 9 if size in ("sm", "icon") else 10
            self.style.configure(
                name, foreground=fg, background=bg, padding=self.PADDING[size], anchor="center", width=-1,
                font=("Segoe UI Semibold" if bold else "Segoe UI", font_size),
            )
            self.style.map(name, foreground=[("disabled", dfg)], background=[("active", bg)])
            self._styles.add(name)
        return name

    def pill_style(self, tone, bg):
        name = f"{tone}.{bg.lstrip('#').lower()}.Pill.TLabel"
        if name not in self._styles:
            self.style.layout(name, [(f"R.pill.{tone}", {"sticky": "nsew", "children": [
                ("Label.padding", {"sticky": "nsew", "children": [("Label.label", {"sticky": "nsew"})]})]})])
            self.style.configure(name, foreground=self.PILLS[tone][1], background=bg,
                                 padding=(10, 3), font=UI_FONT_LABEL)
            self._styles.add(name)
        return name


def ui_round_init(style):
    # one theme per Tk application (images and ttk elements belong to it)
    theme = ROUND["theme"]
    if theme is None or theme.style.tk is not style.tk:
        ROUND["theme"] = RoundTheme(style)
    return ROUND["theme"]


def _parent_bg(parent):
    try:
        return str(parent.cget("bg"))
    except tk.TclError:
        try:
            return str(ttk.Style(parent).lookup(parent.winfo_class(), "background")) or UI["card"]
        except tk.TclError:
            return UI["card"]


def ui_rbutton(parent, text, command=None, kind="secondary", size="md", state=None, width=None):
    """Rounded button (ttk). Same API the app uses: config(text/state), invoke()."""
    theme = ROUND["theme"]
    bg = _parent_bg(parent)
    if not bg.startswith("#"):
        bg = UI["card"]
    btn = ttk.Button(parent, text=text, command=command, style=theme.button_style(kind, size, bg),
                     cursor="hand2", takefocus=True)
    if state:
        btn.configure(state=state)
    if width:
        btn.configure(width=width)
    return btn


def ui_pill(parent, text, tone="neutral"):
    bg = _parent_bg(parent)
    return ttk.Label(parent, text=text, style=ROUND["theme"].pill_style(tone, bg if bg.startswith("#") else UI["card"]))


def ui_pill_set(label, text, tone):
    bg = str(ttk.Style(label).lookup(label.cget("style"), "background")) or UI["card"]
    label.configure(text=text, style=ROUND["theme"].pill_style(tone, bg))


def ui_round_frame(parent, fill=None, border=None, radius=8, pad=4):
    """Rounded card: returns (outer, inner). Place `outer`; put content in `inner`."""
    theme = ROUND["theme"]
    fill = fill or UI["card"]
    bg = _parent_bg(parent)
    if not bg.startswith("#"):
        bg = UI["card"]
    outer = ttk.Frame(parent, style=theme.frame_style(fill, border, radius, bg))
    inner = tk.Frame(outer, bg=fill, bd=0, highlightthickness=0)
    inner.pack(fill="both", expand=True, padx=pad, pady=pad)
    inner._round_outer = outer
    inner._round_radius = radius
    return outer, inner


def ui_round_frame_set(inner, fill, border=None):
    """Recolour a rounded card made by ui_round_frame (e.g. selected / not selected)."""
    outer = getattr(inner, "_round_outer", None)
    if outer is None:
        return
    bg = str(ttk.Style(outer).lookup(outer.cget("style"), "background")) or UI["card"]
    outer.configure(style=ROUND["theme"].frame_style(fill, border, inner._round_radius, bg))
    inner.configure(bg=fill)


def ui_round_tkbutton(w, kind="secondary", size="md"):
    """Rounded look for an existing tk.Button (same widget, same command and state)."""
    theme = ROUND["theme"]
    if theme is None:
        return
    kind = kind if kind in theme.BUTTONS else "secondary"
    try:
        if not hasattr(w, "_orig_width"):
            w._orig_width = int(w.cget("width") or 0) if not str(w.cget("image")) else 0
        font = tkfont.Font(font=w.cget("font"))
        lines = str(w.cget("text")).split("\n") or [""]
        text_w = max(font.measure(line) for line in lines)
        text_h = font.metrics("linespace") * len(lines)
        padx, pady = theme.PADDING.get(size, (14, 6))
        width = max(text_w, w._orig_width * font.measure("0")) + 2 * padx + 4
        height = max(text_h + 2 * pady + 2, 30 if size != "sm" else 26)
        imgs = theme.tk_button_images(kind, int(width), int(height))
        bg = _parent_bg(w.master)
        if not bg.startswith("#"):
            bg = UI["card"]
        _states, fg, dfg, _bold = theme.BUTTONS[kind]
        w.configure(image=imgs["normal"] if str(w["state"]) != "disabled" else imgs["disabled"],
                    compound="center", width=0, height=0, padx=0, pady=0, bd=0, relief="flat",
                    overrelief="flat", highlightthickness=0, bg=bg, activebackground=bg, fg=fg,
                    activeforeground=fg, disabledforeground=dfg, cursor="hand2")
        w._round_imgs = imgs
        w._ui_bg = str(w.cget("bg")).lower()
        if not getattr(w, "_round_bound", False):
            def _img(name, b=w):
                if getattr(b, "_round_imgs", None) and str(b["state"]) != "disabled":
                    b.configure(image=b._round_imgs[name])

            w.bind("<Enter>", lambda _e: _img("hover"), add="+")
            w.bind("<Leave>", lambda _e: _img("normal"), add="+")
            w.bind("<ButtonPress-1>", lambda _e: _img("pressed"), add="+")
            w.bind("<ButtonRelease-1>", lambda _e: _img("hover"), add="+")
            w._round_bound = True
    except tk.TclError:
        pass


def ui_round_tkbutton_sync(w):
    """Keep the image in step with the button state (normal / disabled)."""
    imgs = getattr(w, "_round_imgs", None)
    if not imgs:
        return
    try:
        want = imgs["disabled"] if str(w["state"]) == "disabled" else None
        current = str(w.cget("image"))
        if want is not None and current != str(want):
            w.configure(image=want)
        elif want is None and current == str(imgs["disabled"]):
            w.configure(image=imgs["normal"])
    except tk.TclError:
        pass


def ui_round_check(widget):
    """Give a tk Checkbutton / Radiobutton the rounded indicator images."""
    theme = ROUND["theme"]
    if theme is None or getattr(widget, "_round_done", False):
        return
    try:
        cls = widget.winfo_class()
        on, off = ((theme.check_on, theme.check_off) if cls == "Checkbutton"
                   else (theme.radio_on, theme.radio_off))
        bg = widget.cget("bg")
        text = str(widget.cget("text"))
        widget.configure(image=off, selectimage=on, indicatoron=False, compound="left",
                         relief="flat", offrelief="flat", overrelief="flat", bd=0,
                         highlightthickness=0, selectcolor=bg, activebackground=bg, cursor="hand2")
        if text and not text.startswith(" "):
            widget.configure(text="  " + text)
        widget._round_done = True
    except tk.TclError:
        pass


def ui_button(parent, text, command, kind="secondary", size="md", **options):
    """Create a themed (rounded) button. Returns (outer, button): place `outer`, keep `button`."""
    btn = ui_rbutton(parent, text, command, kind=kind, size=size,
                     state=options.get("state"), width=options.get("width"))
    return btn, btn


def ui_card(parent):
    """White card with a subtle 1px border."""
    return tk.Frame(
        parent,
        bg=UI["card"],
        bd=0,
        highlightthickness=1,
        highlightbackground=UI["border"],
        highlightcolor=UI["border"],
    )


def ui_card_header(card, title, subtitle=None):
    """Card title row (packed). Returns the header frame; add right-side widgets to it."""
    header = tk.Frame(card, bg=UI["card"])
    header.pack(fill="x", padx=16, pady=(12, 10))
    tk.Label(header, text=title, bg=UI["card"], fg=UI["navy"], font=UI_FONT_TITLE).pack(side="left")
    if subtitle:
        tk.Label(header, text="  " + subtitle, bg=UI["card"], fg=UI["muted"], font=UI_FONT_SM).pack(
            side="left", pady=(3, 0)
        )
    tk.Frame(card, bg=UI["border"], height=1).pack(fill="x")
    return header


def ui_field_label(parent, text):
    return tk.Label(parent, text=text, bg=UI["card"], fg=UI["muted"], font=UI_FONT_LABEL)


def ui_tooltip(widget, text, delay_ms=400, wraplength=720):
    """Small popup with `text` (str or callable) while the mouse rests on `widget`."""
    state = {"after": None, "tip": None}

    def _show():
        state["after"] = None
        value = text() if callable(text) else text
        if not value or state["tip"] is not None:
            return
        try:
            tip = tk.Toplevel(widget)
        except tk.TclError:
            return
        tip.wm_overrideredirect(True)
        tip.attributes("-topmost", True)
        tk.Label(
            tip,
            text=value,
            bg=UI["navy"],
            fg="#FFFFFF",
            font=UI_FONT_SM,
            justify="left",
            wraplength=wraplength,
            padx=8,
            pady=4,
        ).pack()
        x = widget.winfo_pointerx() + 12
        y = widget.winfo_pointery() + 16
        tip.wm_geometry(f"+{x}+{y}")
        state["tip"] = tip

    def _enter(_e):
        if state["after"] is None:
            state["after"] = widget.after(delay_ms, _show)

    def _leave(_e=None):
        if state["after"] is not None:
            widget.after_cancel(state["after"])
            state["after"] = None
        if state["tip"] is not None:
            try:
                state["tip"].destroy()
            except tk.TclError:
                pass
            state["tip"] = None

    widget.bind("<Enter>", _enter, add="+")
    widget.bind("<Leave>", _leave, add="+")
    widget.bind("<ButtonPress>", _leave, add="+")
    widget.bind("<Destroy>", _leave, add="+")


DIALOG_TONES = {
    "warn": ("#FEF3C7", "#D97706", "⚠"),
    "danger": ("#FEE2E2", "#DC2626", "✕"),
    "info": ("#DBEAFE", "#2563EB", "i"),
    "brand": ("#DBEAFE", "#2563EB", "▣"),
}


def ui_dialog(parent, title, heading, subtitle="", tone="info", build_body=None,
              buttons=(("OK", True, "primary"),), cancel_value=None, focus_value=None,
              message="", width=540):
    """Modal dialog in the app style; returns the value of the pressed button.

    build_body(container) adds the dialog content; it may return a function
    that turns the pressed button's value into the final result.
    `message` is a plain-text summary (used for logs/tests, not shown).
    """
    soft, strong, glyph = DIALOG_TONES.get(tone, DIALOG_TONES["info"])
    dialog = tk.Toplevel(parent)
    dialog.title(title)
    dialog.configure(bg=UI["card"])
    dialog.resizable(False, False)
    try:
        dialog.transient(parent.winfo_toplevel())
    except tk.TclError:
        pass
    result = {"value": cancel_value}

    content = tk.Frame(dialog, bg=UI["card"])
    content.pack(fill="both", expand=True, padx=24, pady=(20, 16))
    head = tk.Frame(content, bg=UI["card"])
    head.pack(fill="x")
    badge = tk.Canvas(head, width=40, height=40, bg=UI["card"], highlightthickness=0)
    badge.create_oval(1, 1, 39, 39, fill=soft, outline=soft)
    badge.create_text(20, 20, text=glyph, fill=strong, font=("Segoe UI Semibold", 14))
    badge.pack(side="left", anchor="n", padx=(0, 14))
    titles = tk.Frame(head, bg=UI["card"])
    titles.pack(side="left", fill="x", expand=True)
    tk.Label(titles, text=heading, bg=UI["card"], fg=UI["text"],
             font=("Segoe UI Semibold", 13), anchor="w", justify="left").pack(fill="x")
    if subtitle:
        tk.Label(titles, text=subtitle, bg=UI["card"], fg=UI["muted"], font=UI_FONT,
                 anchor="w", justify="left", wraplength=width - 120).pack(fill="x", pady=(2, 0))

    body = tk.Frame(content, bg=UI["card"])
    body.pack(fill="both", expand=True, pady=(14, 0))
    transform = build_body(body) if build_body else None

    tk.Frame(dialog, bg=UI["border"], height=1).pack(fill="x")
    footer = tk.Frame(dialog, bg=UI["surface"])
    footer.pack(fill="x")
    bar = tk.Frame(footer, bg=UI["surface"])
    bar.pack(side="right", padx=24, pady=12)

    def _finish(value):
        result["value"] = transform(value) if transform else value
        dialog.destroy()

    focus_btn = None
    for label, value, kind in buttons:
        focused = value == focus_value and focus_value is not None
        btn = ui_rbutton(bar, label, lambda v=value: _finish(v),
                         kind="secondary_focus" if focused and kind == "secondary" else kind, size="md")
        btn.pack(side="left", padx=(8, 0))
        if focused or (focus_btn is None and kind == "primary" and focus_value is None):
            focus_btn = btn
    if focus_btn is not None:
        focus_btn.focus_set()
        dialog.bind("<Return>", lambda _e: focus_btn.invoke())
    dialog.bind("<Escape>", lambda _e: _finish(cancel_value))
    dialog.protocol("WM_DELETE_WINDOW", lambda: _finish(cancel_value))

    dialog.update_idletasks()
    w = max(width, dialog.winfo_reqwidth())
    h = dialog.winfo_reqheight()
    try:
        top = parent.winfo_toplevel()
        x = top.winfo_rootx() + (top.winfo_width() - w) // 2
        y = top.winfo_rooty() + (top.winfo_height() - h) // 3
    except tk.TclError:
        x, y = 200, 200
    dialog.geometry(f"{w}x{h}+{max(x, 0)}+{max(y, 0)}")
    try:
        dialog.grab_set()
    except tk.TclError:
        pass
    dialog.wait_window()
    return result["value"]


def ui_fit_text(label, full_text, width_px):
    """Show `full_text` in `label`, cut with … so it fits `width_px` pixels."""
    try:
        font = tkfont.Font(font=label.cget("font"))
    except tk.TclError:
        return
    if width_px <= 0 or font.measure(full_text) <= width_px:
        label.config(text=full_text)
        return
    lo, hi = 0, len(full_text)
    while lo < hi:  # longest prefix that fits together with "…"
        mid = (lo + hi + 1) // 2
        if font.measure(full_text[:mid] + "…") <= width_px:
            lo = mid
        else:
            hi = mid - 1
    label.config(text=full_text[:lo] + "…")


class DialogTheme:
    """Applies the Modern Enterprise theme to every dialog/popup (tk.Toplevel).

    Presentation only: it remaps legacy colors/fonts/reliefs of tk widgets
    after they are created. It never changes text, commands, variables,
    bindings, layout managers or widget state. The main window is untouched.
    """

    # Legacy flat-UI button colors → button kind
    BUTTON_KIND = {
        "#27ae60": "success",
        "#2ecc71": "success",
        "#229954": "success",
        "#16a085": "success",
        "#1abc9c": "success",
        "#3498db": "primary",
        "#2980b9": "primary",
        "#f39c12": "primary",
        "#e67e22": "primary",
        "#e74c3c": "danger",
        "#c0392b": "danger",
        "#9b59b6": "secondary",
        "#8e44ad": "secondary",
        "#95a5a6": "secondary",
        "#7f8c8d": "secondary",
        "#bdc3c7": "secondary",
        "#ecf0f1": "secondary",
        "#f0f0f0": "secondary",
        "systembuttonface": "secondary",
        "#d9d9d9": "secondary",
        "#ffffff": "secondary",
        "white": "secondary",
    }
    # Legacy surface colors → new surface colors
    BG = {
        "#f0f0f0": UI["card"],
        "systembuttonface": UI["card"],
        "#d9d9d9": UI["card"],
        "#ecf0f1": UI["surface"],
        "#f8f9fa": UI["surface"],
        "#f5f5f5": UI["surface"],
        "#e8f4f8": UI["primary_soft"],
        "#fff3cd": "#FFFBEB",
        "#2c3e50": UI["navy"],
        "#34495e": UI["navy"],
        "#27ae60": UI["success"],
        "#3498db": UI["primary"],
        "#e74c3c": UI["danger"],
    }
    # Legacy text colors → new text colors
    FG = {
        "#2c3e50": UI["text"],
        "#34495e": UI["text"],
        "black": UI["text"],
        "#000000": UI["text"],
        "systembuttontext": UI["text"],
        "#7f8c8d": UI["muted"],
        "#95a5a6": UI["muted"],
        "gray": UI["muted"],
        "#27ae60": UI["success"],
        "#2ecc71": UI["success"],
        "#e74c3c": UI["danger"],
        "#c0392b": UI["danger"],
        "#3498db": UI["primary"],
        "#2980b9": UI["primary"],
        "#f39c12": UI["warn"],
        "#e67e22": UI["warn"],
        "blue": UI["primary"],
        "#0000ff": UI["primary"],
        "green": UI["success"],
        "#008000": UI["success"],
        "red": UI["danger"],
        "#ff0000": UI["danger"],
        "darkgreen": UI["success"],
        "darkred": UI["danger"],
        "grey": UI["muted"],
    }
    SANS = {"arial", "helvetica", "ms sans serif", "tahoma", "verdana", "segoe ui"}
    MONO = {"courier", "courier new"}
    ACCENT_TTK_TEXT = {"save", "confirm", "insert values", "apply", "ok"}

    def __init__(self, root, interval_ms=500):
        self.root = root
        self.interval_ms = interval_ms
        self._font_cache = {}
        # Theme a dialog as soon as it is shown; the periodic tick catches
        # widgets that dialogs add later (e.g. refreshed lists, result rows).
        root.bind_class("Toplevel", "<Map>", self._on_map, add="+")
        root.after(interval_ms, self._tick)

    def _on_map(self, event):
        widget = event.widget
        if isinstance(widget, tk.Toplevel):
            try:
                self._walk(widget)
            except Exception:
                pass

    # -- scheduling --------------------------------------------------------
    def _tick(self):
        try:
            for top in self._toplevels(self.root):
                if top.winfo_ismapped():
                    self._walk(top)
        except Exception:
            pass  # theming must never interfere with the application
        try:
            self.root.after(self.interval_ms, self._tick)
        except tk.TclError:
            pass

    def _toplevels(self, widget):
        for child in widget.winfo_children():
            if isinstance(child, tk.Toplevel):
                yield child
            yield from self._toplevels(child)

    def _walk(self, widget):
        try:
            self._theme(widget)
        except tk.TclError:
            return
        for child in widget.winfo_children():
            if isinstance(child, tk.Toplevel):
                continue  # handled as its own top-level
            self._walk(child)

    # -- helpers -------------------------------------------------------------
    @staticmethod
    def _get(widget, option):
        try:
            return str(widget.cget(option)).lower()
        except tk.TclError:
            return None

    def _font(self, widget):
        try:
            spec = widget.cget("font")
        except tk.TclError:
            return
        key = str(spec)
        if key not in self._font_cache:
            new = None
            try:
                actual = tkfont.Font(root=self.root, font=spec).actual()
                family = actual["family"].lower()
                size = actual["size"]
                bold = actual["weight"] == "bold"
                if family in self.SANS:
                    new = ("Segoe UI Semibold" if bold else "Segoe UI", size)
                    if family == "segoe ui" and not bold:
                        new = None  # already themed
                elif family in self.MONO:
                    new = ("Consolas", size, "bold" if bold else "normal")
            except Exception:
                new = None
            self._font_cache[key] = new
        if self._font_cache[key]:
            widget.config(font=self._font_cache[key])

    def _remap(self, widget, option, table):
        value = self._get(widget, option)
        if value in table:
            widget.config(**{option: table[value]})

    # -- per-class theming -------------------------------------------------
    def _theme(self, w):
        cls = w.winfo_class()
        first_time = not getattr(w, "_ui_themed", False)

        if cls == "Button":
            bg = self._get(w, "bg")
            kind = self.BUTTON_KIND.get(bg)
            # First pass, or the logic re-applied a legacy color after theming
            if (
                kind
                and (first_time or bg != getattr(w, "_ui_bg", None))
                and bg != UI["hover"].lower()
            ):
                self._style_button(w, kind)
                if first_time:
                    self._font(w)
                ui_round_tkbutton(w, kind)
                w._ui_bg = self._get(w, "bg")
            elif first_time:
                self._font(w)
            ui_round_tkbutton_sync(w)
        elif not first_time:
            return  # non-button widgets only need one pass
        elif cls == "Toplevel":
            self._remap(w, "bg", self.BG)
        elif cls in ("Frame", "Canvas"):
            self._remap(w, "bg", self.BG)
            if cls == "Frame":
                self._soft_border(w)
        elif cls == "Label" or cls == "Message":
            self._remap(w, "bg", self.BG)
            self._remap(w, "fg", self.FG)
            self._font(w)
        elif cls == "Labelframe":
            self._remap(w, "bg", self.BG)
            self._remap(w, "fg", self.FG)
            w.config(
                relief="flat",
                bd=0,
                highlightthickness=1,
                highlightbackground=UI["border"],
                highlightcolor=UI["border"],
            )
            if self._get(w, "fg") in (None, UI["text"].lower()):
                w.config(fg=UI["navy"])
            self._font(w)
        elif cls in ("Checkbutton", "Radiobutton"):
            self._remap(w, "bg", self.BG)
            self._remap(w, "fg", self.FG)
            w.config(
                activebackground=w.cget("bg"),
                highlightthickness=0,
                bd=0,
                selectcolor="#FFFFFF",
                cursor="hand2",
            )
            self._font(w)
            ui_round_check(w)
        elif cls in ("Entry", "Spinbox"):
            w.config(
                relief="flat",
                bd=0,
                highlightthickness=1,
                highlightbackground=UI["border_strong"],
                highlightcolor=UI["primary"],
                selectbackground="#BFDBFE",
                selectforeground=UI["text"],
            )
            self._remap(w, "bg", self.BG)
            self._font(w)
        elif cls in ("Text", "Listbox"):
            w.config(
                relief="flat",
                bd=0,
                highlightthickness=1,
                highlightbackground=UI["border"],
                highlightcolor=UI["primary"],
                selectbackground="#DBEAFE",
                selectforeground=UI["text"],
            )
            if cls == "Listbox":
                w.config(activestyle="none")
            self._remap(w, "bg", self.BG)
            self._remap(w, "fg", self.FG)
            self._font(w)
        elif cls == "TLabel":
            self._font(w)
        elif cls == "TButton":
            text = str(w.cget("text")).strip().lower()
            style = str(w.cget("style"))
            if style in ("", "TButton", "Accent.TButton") and ROUND["theme"] is not None:
                accent = style == "Accent.TButton" or text in self.ACCENT_TTK_TEXT
                bg = _parent_bg(w.master)
                w.config(style=ROUND["theme"].button_style(
                    "primary" if accent else "secondary", "sm", bg if bg.startswith("#") else UI["card"]),
                    cursor="hand2")
            elif text in self.ACCENT_TTK_TEXT and not style:
                w.config(style="Accent.TButton")
        w._ui_themed = True

    def _soft_border(self, w):
        """Replace a dark 3D/solid relief border with a 1px light border."""
        try:
            relief = str(w.cget("relief"))
            bd = int(float(w.cget("bd")))
        except (tk.TclError, ValueError):
            return
        if bd > 0 and relief in ("solid", "groove", "ridge", "raised", "sunken"):
            w.config(
                relief="flat",
                bd=0,
                highlightthickness=1,
                highlightbackground=UI["border"],
                highlightcolor=UI["border"],
            )

    def _style_button(self, w, kind):
        style = ui_button_style(kind)
        options = {
            k: style[k]
            for k in ("bg", "fg", "activebackground", "activeforeground", "disabledforeground")
        }
        options.update(relief="flat", bd=0, cursor="hand2", overrelief="flat")
        if kind == "secondary":
            options.update(bg=UI["hover"], activebackground=UI["border"])
        options.update(highlightthickness=0)
        try:  # give cramped legacy buttons comfortable padding
            if int(w.cget("padx")) < 10:
                options["padx"] = 12
            if int(w.cget("pady")) < 4:
                options["pady"] = 4
        except (tk.TclError, ValueError):
            pass
        w.config(**options)
        if not getattr(w, "_ui_hover", False):

            def _enter(_e, b=w):
                if str(b["state"]) != "disabled":
                    b._ui_rest_bg = b.cget("bg")
                    hover = {
                        UI["primary"]: UI["primary_hover"],
                        UI["success"]: UI["success_hover"],
                        UI["danger_soft"]: UI["danger_hover"],
                        UI["hover"]: UI["border"],
                    }
                    b.config(bg=hover.get(b._ui_rest_bg, b._ui_rest_bg))

            def _leave(_e, b=w):
                if str(b["state"]) != "disabled" and getattr(b, "_ui_rest_bg", None):
                    b.config(bg=b._ui_rest_bg)

            w.bind("<Enter>", _enter, add="+")
            w.bind("<Leave>", _leave, add="+")
            w._ui_hover = True


class DatabaseConnectorGUI:

    # Starter query shown in the SQL editor (app start, new / empty profiles)
    DEFAULT_SQL_QUERY = "SELECT * FROM Table WHERE Column1 IN ({ACCOUNT_LIST})"

    def __init__(self, root):
        self.root = root
        self.root.title("Database Connector")
        self.root.geometry("1200x900")
        self.root.configure(bg=UI["bg"])

        # Enhanced styling
        self.style = ttk.Style()
        self.style.theme_use("clam")
        # Base ttk styles — used by dialogs/popups (white surfaces)
        self.style.configure("TFrame", background=UI["card"])
        self.style.configure("App.TFrame", background=UI["bg"])  # main window canvas
        self.style.configure(
            "TLabelframe",
            background=UI["card"],
            relief="solid",
            bordercolor=UI["border"],
            lightcolor=UI["card"],
            darkcolor=UI["card"],
        )
        self.style.configure(
            "TLabelframe.Label", background=UI["card"], foreground=UI["navy"], font=UI_FONT_SEMI
        )
        self.style.configure("TLabel", background=UI["card"], foreground=UI["text"], font=UI_FONT)
        # Secondary (default) and Accent (primary) ttk buttons
        self.style.configure(
            "TButton",
            font=UI_FONT,
            relief="flat",
            padding=(10, 4),
            background=UI["hover"],
            foreground=UI["text"],
            bordercolor=UI["hover"],
            lightcolor=UI["hover"],
            darkcolor=UI["hover"],
            focuscolor=UI["hover"],
        )
        self.style.map(
            "TButton",
            background=[("disabled", UI["surface"]), ("active", UI["border"])],
            foreground=[("disabled", UI["subtle"])],
            bordercolor=[("active", UI["border"])],
            lightcolor=[("active", UI["border"])],
            darkcolor=[("active", UI["border"])],
        )
        self.style.configure(
            "Accent.TButton",
            font=UI_FONT_SEMI,
            padding=(12, 4),
            background=UI["primary"],
            foreground="#FFFFFF",
            bordercolor=UI["primary"],
            lightcolor=UI["primary"],
            darkcolor=UI["primary"],
            focuscolor=UI["primary"],
        )
        self.style.map(
            "Accent.TButton",
            background=[("disabled", UI["primary_disabled"]), ("active", UI["primary_hover"])],
            foreground=[("disabled", "#EFF6FF")],
            bordercolor=[("active", UI["primary_hover"])],
            lightcolor=[("active", UI["primary_hover"])],
            darkcolor=[("active", UI["primary_hover"])],
        )
        self.style.configure(
            "TCombobox",
            fieldbackground="#FFFFFF",
            background="#FFFFFF",
            foreground=UI["text"],
            bordercolor=UI["border_strong"],
            lightcolor=UI["border_strong"],
            darkcolor=UI["border_strong"],
            arrowcolor=UI["muted"],
            padding=(6, 4),
            selectbackground="#BFDBFE",
            selectforeground=UI["text"],
        )
        self.style.map(
            "TCombobox",
            fieldbackground=[("readonly", "#FFFFFF")],
            selectbackground=[("readonly", "#FFFFFF")],
            selectforeground=[("readonly", UI["text"])],
            bordercolor=[("focus", UI["primary"])],
        )
        self.style.configure(
            "TEntry",
            fieldbackground="#FFFFFF",
            foreground=UI["text"],
            bordercolor=UI["border_strong"],
            lightcolor=UI["border_strong"],
            darkcolor=UI["border_strong"],
            padding=(6, 4),
            selectbackground="#BFDBFE",
            selectforeground=UI["text"],
        )
        self.style.map(
            "TEntry", bordercolor=[("focus", UI["primary"])], lightcolor=[("focus", UI["primary"])]
        )
        self.style.configure(
            "TCheckbutton", background=UI["card"], foreground=UI["text"], font=UI_FONT
        )
        self.style.map("TCheckbutton", background=[("active", UI["card"])])
        self.style.configure(
            "TRadiobutton", background=UI["card"], foreground=UI["text"], font=UI_FONT
        )
        self.style.map("TRadiobutton", background=[("active", UI["card"])])
        self.style.configure(
            "Treeview",
            font=UI_FONT_SM,
            rowheight=24,
            background="#FFFFFF",
            fieldbackground="#FFFFFF",
            foreground=UI["text"],
            bordercolor=UI["border"],
            borderwidth=0,
        )
        self.style.map(
            "Treeview", background=[("selected", "#DBEAFE")], foreground=[("selected", UI["text"])]
        )
        self.style.configure(
            "Treeview.Heading",
            font=UI_FONT_LABEL,
            background=UI["surface"],
            foreground=UI["muted"],
            bordercolor=UI["border"],
            relief="flat",
            padding=(6, 4),
        )
        self.style.map("Treeview.Heading", background=[("active", UI["hover"])])
        self.style.configure("TNotebook", background=UI["card"], borderwidth=0)
        self.style.configure(
            "TNotebook.Tab",
            font=UI_FONT,
            padding=(12, 5),
            background=UI["surface"],
            foreground=UI["muted"],
        )
        self.style.map(
            "TNotebook.Tab",
            background=[("selected", UI["card"])],
            foreground=[("selected", UI["primary"])],
        )
        self.style.configure(
            "Horizontal.TProgressbar",
            background=UI["primary"],
            troughcolor=UI["hover"],
            bordercolor=UI["hover"],
            lightcolor=UI["primary"],
            darkcolor=UI["primary"],
        )
        self.style.configure(
            "TScrollbar",
            background=UI["hover"],
            troughcolor=UI["card"],
            bordercolor=UI["card"],
            arrowcolor=UI["muted"],
            lightcolor=UI["hover"],
            darkcolor=UI["hover"],
        )
        self.style.map("TScrollbar", background=[("active", UI["border_strong"])])

        # Modern Enterprise theme styles (main window only)
        self.style.configure(
            "Fluent.TEntry",
            fieldbackground="#FFFFFF",
            foreground=UI["text"],
            bordercolor=UI["border_strong"],
            lightcolor=UI["border_strong"],
            darkcolor=UI["border_strong"],
            padding=(8, 5),
            selectbackground="#BFDBFE",
            selectforeground=UI["text"],
        )
        self.style.map(
            "Fluent.TEntry",
            bordercolor=[("focus", UI["primary"])],
            lightcolor=[("focus", UI["primary"])],
            darkcolor=[("focus", UI["primary"])],
        )
        # Password entry: extra right padding so text never runs under the eye icon
        self.style.configure("Password.Fluent.TEntry", padding=(8, 5, 34, 5))
        self.style.configure(
            "Fluent.TCombobox",
            fieldbackground="#FFFFFF",
            background="#FFFFFF",
            foreground=UI["text"],
            bordercolor=UI["border_strong"],
            lightcolor=UI["border_strong"],
            darkcolor=UI["border_strong"],
            arrowcolor=UI["muted"],
            padding=(8, 5),
            selectbackground="#FFFFFF",
            selectforeground=UI["text"],
        )
        self.style.map(
            "Fluent.TCombobox",
            fieldbackground=[("readonly", "#FFFFFF")],
            selectbackground=[("readonly", "#FFFFFF")],
            selectforeground=[("readonly", UI["text"])],
            bordercolor=[("focus", UI["primary"])],
            lightcolor=[("focus", UI["primary"])],
            darkcolor=[("focus", UI["primary"])],
        )
        self.style.configure(
            "Fluent.TNotebook", background=UI["card"], borderwidth=0, tabmargins=(16, 8, 16, 0)
        )
        self.style.configure(
            "Fluent.TNotebook.Tab",
            font=UI_FONT,
            padding=(14, 6),
            background=UI["surface"],
            foreground=UI["muted"],
            bordercolor=UI["border"],
            lightcolor=UI["surface"],
        )
        self.style.map(
            "Fluent.TNotebook.Tab",
            background=[("selected", UI["card"])],
            foreground=[("selected", UI["primary"])],
            lightcolor=[("selected", UI["card"])],
            expand=[("selected", (0, 0, 0, 0))],
        )
        self.style.configure(
            "Fluent.Treeview",
            font=UI_FONT_SM,
            rowheight=24,
            background="#FFFFFF",
            fieldbackground="#FFFFFF",
            foreground=UI["text"],
            bordercolor=UI["border"],
            borderwidth=0,
        )
        self.style.map(
            "Fluent.Treeview",
            background=[("selected", "#DBEAFE")],
            foreground=[("selected", UI["text"])],
        )
        self.style.configure(
            "Fluent.Treeview.Heading",
            font=UI_FONT_LABEL,
            background=UI["surface"],
            foreground=UI["muted"],
            bordercolor=UI["border"],
            relief="flat",
            padding=(6, 4),
        )
        self.style.map("Fluent.Treeview.Heading", background=[("active", UI["hover"])])

        self.engine = None
        self.config_file = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "db_profiles.json"
        )
        self.jobs_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "saved_jobs.json")
        self.saved_profiles = self.load_profiles()
        self.saved_jobs = self.load_jobs()
        self.job_results = {}

        # NEW: Debug mode and table data
        self.debug_mode = tk.BooleanVar(value=True)
        self.last_error_details = None
        self.table_data_file = os.path.join(os.path.dirname(__file__), "mail_table_data.json")
        self.loaded_table_data = None

        self.auto_sync_enabled = tk.BooleanVar(value=False)
        self.sync_interval_seconds = 300  # 5 minutes default
        self.last_table_data_mtime = None
        self.sync_timer_id = None
        self.saved_table_mappings = {}  # Store table-to-variable mappings
        self.query_templates = {}  # Store reusable query templates
        self.loaded_excel_data = None
        self.sql_template = None
        self._excel_parameterized_sql = None
        self._excel_parameter_values = {}
        self._checked_job_ids = set()  # id() of jobs ticked in Saved Jobs list
        # Stop button: set while a stop was requested; DB connections in use
        self._stop_event = threading.Event()
        self._stop_buttons = []
        # Run All / Run Group: open one result window per job (remembered)
        self.open_result_popups = tk.BooleanVar(
            value=bool(self._load_app_settings().get("open_result_popups", True))
        )
        self.open_result_popups.trace_add(
            "write",
            lambda *_: self._save_app_setting(
                "open_result_popups", bool(self.open_result_popups.get())
            ),
        )
        self._active_db_connections = set()
        self._active_db_lock = threading.Lock()

        self.load_table_mappings()

        # Set close event handler
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

        # ==================================================================
        # Main window layout (Figma "01 · Main Screen")
        #   [Top bar: profile + connection]  [Connection details drawer]
        #   [Sidebar: Saved Jobs] | [Workspace: SQL editor / Results]
        #   [Status bar]
        # Presentation only: every widget keeps its attribute name and command.
        # ==================================================================
        import time

        APP_BG = "#F1F5F9"
        SELECTED = "#EFF6FF"
        BRAND_SOFT = "#DBEAFE"
        WARN_SOFT = "#FEF3C7"
        self.root.configure(bg=APP_BG)
        self.root.minsize(1100, 680)
        ui_round_init(self.style)
        self.style.configure(
            "Running.Horizontal.TProgressbar",
            background=UI["warn"],
            troughcolor="#FFFFFF",
            bordercolor=WARN_SOFT,
            lightcolor=UI["warn"],
            darkcolor=UI["warn"],
        )

        # The window no longer scrolls as a whole; dialogs still call
        # self.canvas.bind_all/unbind_all and restore self._main_mousewheel.
        self.canvas = self.root
        self._main_mousewheel = lambda _event: None

        root.columnconfigure(0, weight=1)
        root.rowconfigure(2, weight=1)

        def _hline(parent, color=UI["border"]):
            line = tk.Frame(parent, bg=color, height=1)
            return line

        def _vline(parent, height=22):
            return tk.Frame(parent, bg=UI["border"], width=1, height=height)

        def _ghost(parent, text, command, fg=UI["primary"], bg=None):
            kind = {UI["muted"]: "ghost_muted", UI["danger"]: "ghost_danger"}.get(fg, "ghost")
            return ui_rbutton(parent, text, command, kind=kind, size="sm")

        def _soft_icon_btn(parent, text, command, kind="default", bg_parent=None):
            kind = {"default": "secondary", "primary": "soft", "danger": "danger"}[kind]
            return ui_rbutton(parent, text, command, kind=kind, size="icon")

        # ------------------------------------------------------------------
        # Top bar · profile + connection
        # ------------------------------------------------------------------
        top = tk.Frame(root, bg=UI["card"])
        top.grid(row=0, column=0, sticky="ew")
        _hline(top).pack(side="bottom", fill="x")
        top_inner = tk.Frame(top, bg=UI["card"])
        top_inner.pack(fill="x", padx=16, pady=9)

        tk.Label(top_inner, text="Profile", bg=UI["card"], fg=UI["muted"], font=UI_FONT_LABEL).pack(
            side="left", padx=(0, 8)
        )
        self.profile_combo = ttk.Combobox(
            top_inner, width=18, state="readonly", font=UI_FONT, style="Fluent.TCombobox"
        )
        self.profile_combo.pack(side="left", padx=(0, 12))
        self.update_profile_list()
        self.profile_combo.bind("<<ComboboxSelected>>", self.on_profile_selected)

        target_box = tk.Frame(top_inner, bg=UI["card"])
        target_box.pack(side="left", padx=(0, 8))
        target_main = tk.Label(
            target_box, text="", bg=UI["card"], fg=UI["text"], font=UI_FONT_SEMI, anchor="w"
        )
        target_main.pack(anchor="w")
        target_sub = tk.Label(
            target_box, text="", bg=UI["card"], fg=UI["muted"], font=UI_FONT_SM, anchor="w"
        )
        target_sub.pack(anchor="w")

        # Show / hide the connection fields (same toggle as before)
        self.creds_toggle_btn = ui_rbutton(top_inner, "✎  Details ▾", None, "secondary", "sm")
        self.creds_toggle_btn.pack(side="left", padx=(0, 12))

        _vline(top_inner).pack(side="left", padx=(0, 12))

        conn_badge = ui_pill(top_inner, "●  Not Connected", "danger")
        conn_badge.pack(side="left", padx=(0, 10))

        self.connect_btn = ui_rbutton(top_inner, "🔌  Connect", self.connect_database, "primary", "sm")
        self.connect_btn.pack(side="left")

        # Profile actions (right)
        more_menu = tk.Menu(self.root, tearoff=0, font=UI_FONT_SM)
        more_menu.add_command(label="Delete profile", command=self.delete_profile)
        more_menu.add_separator()
        more_menu.add_command(label="Config file location", command=self.show_config_file_location)
        more_btn = _ghost(top_inner, "⋯", None, fg=UI["muted"])
        more_btn.config(
            command=lambda: more_menu.tk_popup(
                more_btn.winfo_rootx(), more_btn.winfo_rooty() + more_btn.winfo_height()
            ),
        )
        more_btn.pack(side="right")
        self.delete_btn = more_btn  # "Delete profile" lives in this menu
        for _text, _cmd in (
            ("Export", self.export_profiles_dialog),
            ("Import", self.import_profiles_dialog),
            ("Save", self.save_profile_dialog),
            ("＋ New", self.new_profile_dialog),
        ):
            _b = _ghost(top_inner, _text, _cmd)
            _b.pack(side="right", padx=(2, 0))

        # ------------------------------------------------------------------
        # Connection details drawer (hidden until "Details" is pressed)
        # ------------------------------------------------------------------
        form_wrap = tk.Frame(root, bg=UI["surface"])
        form = tk.Frame(form_wrap, bg=UI["surface"])
        form.pack(fill="x", padx=16, pady=(10, 12))
        _hline(form_wrap).pack(side="bottom", fill="x")
        self.creds_expanded = False
        for _c in range(6):
            form.columnconfigure(_c, weight=2 if _c in (1, 3) else 1, uniform="conn")

        def _field(col, label):
            cell = tk.Frame(form, bg=UI["surface"])
            cell.grid(row=0, column=col, sticky="ew", padx=(0 if col == 0 else 10, 0))
            cell.columnconfigure(0, weight=1)
            tk.Label(cell, text=label, bg=UI["surface"], fg=UI["muted"], font=UI_FONT_LABEL).grid(
                row=0, column=0, sticky="w", pady=(0, 4)
            )
            return cell

        _cell = _field(0, "DATABASE TYPE")
        self.db_type = ttk.Combobox(_cell, state="readonly", font=UI_FONT, style="Fluent.TCombobox")
        self.db_type.grid(row=1, column=0, sticky=(tk.W, tk.E))
        self.db_type["values"] = ("PostgreSQL", "MySQL", "Microsoft SQL Server", "Oracle")
        self.db_type.current(0)
        self.db_type.bind("<<ComboboxSelected>>", self.on_db_type_change)

        _cell = _field(1, "HOST")
        self.db_host = ttk.Entry(_cell, font=UI_FONT, style="Fluent.TEntry")
        self.db_host.grid(row=1, column=0, sticky=(tk.W, tk.E))
        self.db_host.insert(0, "test.com")

        _cell = _field(2, "PORT")
        self.db_port = ttk.Entry(_cell, font=UI_FONT, style="Fluent.TEntry")
        self.db_port.grid(row=1, column=0, sticky=(tk.W, tk.E))
        self.db_port.insert(0, "5432")

        _cell = _field(3, "DATABASE / SERVICE NAME")
        self.db_name = ttk.Entry(_cell, font=UI_FONT, style="Fluent.TEntry")
        self.db_name.grid(row=1, column=0, sticky=(tk.W, tk.E))
        self.db_name.insert(0, "test")

        _cell = _field(4, "USER")
        self.db_user = ttk.Entry(_cell, font=UI_FONT, style="Fluent.TEntry")
        self.db_user.grid(row=1, column=0, sticky=(tk.W, tk.E))
        self.db_user.insert(0, "test")

        password_frame = _field(5, "PASSWORD")
        self.db_password = ttk.Entry(
            password_frame, show="*", font=UI_FONT, style="Password.Fluent.TEntry"
        )
        self.db_password.grid(row=1, column=0, sticky=(tk.W, tk.E))
        self.db_password.insert(0, "test")

        # Eye icon sits inside the entry, right-aligned and vertically centered
        self.password_visible = False
        self.toggle_password_btn = tk.Label(
            self.db_password,
            text=PASSWORD_ICON_SHOW,
            font=("Segoe MDL2 Assets", 11),
            bg="#FFFFFF",
            fg=UI["muted"],
            cursor="hand2",
            bd=0,
            padx=4,
        )
        self.toggle_password_btn.place(relx=1.0, rely=0.5, x=-6, anchor="e")
        self.toggle_password_btn.bind("<Button-1>", lambda e: self.toggle_password_visibility())
        self.toggle_password_btn.bind(
            "<Enter>", lambda e: self.toggle_password_btn.config(fg=UI["primary"])
        )
        self.toggle_password_btn.bind("<Leave>", lambda e: self._refresh_password_icon())

        def _entry_ctrl_key(e):
            """Handle Ctrl+C/X/V/A for Entry by Windows keycode — works with any keyboard layout (Thai/EN)."""
            kc = e.keycode
            w = e.widget
            if kc == 67:  # C — Copy
                try:
                    sel = w.selection_get()
                    self.root.clipboard_clear()
                    self.root.clipboard_append(sel)
                except Exception:
                    pass
                return "break"
            elif kc == 88:  # X — Cut
                try:
                    sel = w.selection_get()
                    self.root.clipboard_clear()
                    self.root.clipboard_append(sel)
                    w.delete(tk.SEL_FIRST, tk.SEL_LAST)
                except Exception:
                    pass
                return "break"
            elif kc == 86:  # V — Paste
                try:
                    txt = self.root.clipboard_get()
                    try:
                        w.delete(tk.SEL_FIRST, tk.SEL_LAST)
                    except Exception:
                        pass
                    w.insert(tk.INSERT, txt)
                except Exception:
                    pass
                return "break"
            elif kc == 65:  # A — Select All
                try:
                    w.select_range(0, tk.END)
                    w.icursor(tk.END)
                except Exception:
                    pass
                return "break"

        for _ew in (self.db_user, self.db_password, self.db_host, self.db_port, self.db_name):
            _ew.bind("<Control-KeyPress>", _entry_ctrl_key)

        def _refresh_target_summary():
            """Read-only: show the connection target under the profile picker."""
            try:
                host = self.db_host.get().strip()
                port = self.db_port.get().strip()
                user = self.db_user.get().strip()
                dbn = self.db_name.get().strip()
                main_text = f"{self.db_type.get()} · {user}@{host}" + (f":{port}" if port else "")
                sub_text = f"Database / Service: {dbn}" if dbn else "Database: (default)"
                if target_main.cget("text") != main_text:
                    target_main.config(text=main_text)
                if target_sub.cget("text") != sub_text:
                    target_sub.config(text=sub_text)
            except tk.TclError:
                return
            self.root.after(500, _refresh_target_summary)

        def _toggle_creds():
            self.creds_expanded = not self.creds_expanded
            if self.creds_expanded:
                form_wrap.grid(row=1, column=0, sticky="ew")
                self.creds_toggle_btn.config(text="✎  Details ▴")
            else:
                form_wrap.grid_forget()
                self.creds_toggle_btn.config(text="✎  Details ▾")

        self.creds_toggle_btn.config(command=_toggle_creds)
        _refresh_target_summary()

        # Connection Status — logic still writes here (text/foreground); the badge mirrors it.
        self.status_label = tk.Label(
            top,
            text="❌ Not Connected",
            foreground="#e74c3c",
            font=("Arial", 10, "bold"),
            bg="#ffffff",
        )

        def _refresh_conn_badge():
            """Read-only mirror of self.status_label → badge."""
            try:
                if not conn_badge.winfo_exists():
                    return
                raw = str(self.status_label.cget("text"))
                if raw.startswith("✅"):
                    detail = raw[raw.find("(") + 1 : raw.rfind(")")] if "(" in raw else ""
                    text = "Connected" + (f" · {detail}" if detail else "")
                    tone = "success"
                else:
                    text = raw.replace("❌", "").strip() or "Not Connected"
                    tone = "danger"
                if str(conn_badge.cget("text")) != f"●  {text}":
                    ui_pill_set(conn_badge, f"●  {text}", tone)
            except tk.TclError:
                return
            conn_badge.after(300, _refresh_conn_badge)

        _refresh_conn_badge()

        # ------------------------------------------------------------------
        # Body · sidebar | workspace
        # ------------------------------------------------------------------
        body = tk.PanedWindow(
            root,
            orient=tk.HORIZONTAL,
            bg=UI["border"],
            sashwidth=6,
            sashrelief="flat",
            sashcursor="sb_h_double_arrow",
            bd=0,
            showhandle=False,
            opaqueresize=True,
        )
        body.grid(row=2, column=0, sticky="nsew")
        sidebar = tk.Frame(body, bg=UI["card"])
        workspace = tk.Frame(body, bg=APP_BG)
        body.add(sidebar, minsize=260, width=340, stretch="never")
        body.add(workspace, minsize=600, stretch="always")

        # ---- Sidebar tabs: Saved Jobs (here) / Script Groups (window) ----
        side_tabs = tk.Frame(sidebar, bg=UI["card"])
        side_tabs.pack(fill="x", padx=8)
        _hline(sidebar).pack(fill="x")
        tab_jobs = tk.Frame(side_tabs, bg=UI["card"])
        tab_jobs.pack(side="left")
        tk.Label(
            tab_jobs, text="🕘  Saved Jobs", bg=UI["card"], fg=UI["primary"], font=UI_FONT_SEMI
        ).pack(padx=10, pady=(10, 7))
        tk.Frame(tab_jobs, bg=UI["primary"], height=2).pack(fill="x")
        tab_groups = tk.Label(
            side_tabs,
            text="▤  Script Groups",
            bg=UI["card"],
            fg=UI["muted"],
            font=UI_FONT,
            cursor="hand2",
        )
        tab_groups.pack(side="left", padx=10, pady=(10, 9))
        tab_groups.bind("<Button-1>", lambda _e: self.show_script_groups_dialog())
        tab_groups.bind("<Enter>", lambda _e: tab_groups.config(fg=UI["text"]))
        tab_groups.bind("<Leave>", lambda _e: tab_groups.config(fg=UI["muted"]))

        jobs_frame = tk.Frame(sidebar, bg=UI["card"])
        jobs_frame.pack(fill="both", expand=True)

        # Run / export / new job
        controls_frame = tk.Frame(jobs_frame, bg=UI["card"])
        controls_frame.pack(fill="x", padx=12, pady=(12, 8))
        self.run_all_btn = ui_rbutton(
            controls_frame, "▶  Run all", lambda: self.run_selected_job(), "success", "sm"
        )
        self.run_all_btn.pack(side="left", padx=(0, 6))
        _outer, self.export_excel_btn = ui_button(
            controls_frame, "⇩  Export", self.export_jobs_to_excel, size="sm"
        )
        _outer.pack(side="left")
        _new_job = _soft_icon_btn(controls_frame, "＋", self.save_job_dialog, kind="primary")
        _new_job.pack(side="right")

        # Select All + selection count (+ delete while something is ticked)
        select_frame = tk.Frame(jobs_frame, bg=UI["card"])
        select_frame.pack(fill="x", padx=12, pady=(0, 6))
        self.select_all_jobs_var = tk.BooleanVar(value=False)
        _select_all_cb = tk.Checkbutton(
            select_frame,
            text="Select all",
            variable=self.select_all_jobs_var,
            command=self.toggle_select_all_jobs,
            bg=UI["card"],
            activebackground=UI["card"],
            fg=UI["text"],
            selectcolor="#FFFFFF",
            font=UI_FONT_SM,
            bd=0,
            highlightthickness=0,
            cursor="hand2",
        )
        _select_all_cb.pack(side="left")
        ui_round_check(_select_all_cb)
        self.selected_jobs_label = tk.Label(
            select_frame, text="", bg=UI["card"], fg=UI["primary"], font=UI_FONT_SM
        )
        self.selected_jobs_label.pack(side="left", padx=6)
        # Shown only while at least one job is ticked (packed by _refresh_job_selection_ui)
        self.delete_selected_btn = _ghost(
            select_frame, "🗑  Delete", self.delete_selected_jobs, fg=UI["danger"]
        )

        # Presets (bottom of the sidebar)
        presets = tk.Frame(sidebar, bg=UI["surface"])
        _hline(presets).pack(side="top", fill="x")
        presets_inner = tk.Frame(presets, bg=UI["surface"])
        presets_inner.pack(fill="x", padx=8, pady=6)
        tk.Label(
            presets_inner, text="Preset", bg=UI["surface"], fg=UI["muted"], font=UI_FONT_LABEL
        ).pack(side="left", padx=(4, 6))
        _ghost(presets_inner, "💾  Save", self.save_preset_dialog, bg=UI["surface"]).pack(side="left")
        _ghost(presets_inner, "📂  Load", self.load_preset_dialog, bg=UI["surface"]).pack(side="left")
        presets.pack(side="bottom", fill="x", before=jobs_frame)

        # Jobs list (scrollable)
        jobs_list_frame = tk.Frame(jobs_frame, bg=UI["card"], bd=0, highlightthickness=0)
        jobs_list_frame.pack(fill="both", expand=True, padx=(8, 4))
        jobs_canvas = tk.Canvas(jobs_list_frame, bg=UI["card"], highlightthickness=0, height=200)
        jobs_scrollbar = ttk.Scrollbar(
            jobs_list_frame, orient="vertical", command=jobs_canvas.yview
        )
        self.jobs_container = tk.Frame(jobs_canvas, bg=UI["card"])
        jobs_canvas.configure(yscrollcommand=jobs_scrollbar.set)
        jobs_scrollbar.pack(side="right", fill="y")
        jobs_canvas.pack(side="left", fill="both", expand=True)
        jobs_canvas_window = jobs_canvas.create_window(
            (0, 0), window=self.jobs_container, anchor="nw"
        )

        def jobs_content_overflows():
            bounds = jobs_canvas.bbox("all")
            return bool(bounds and bounds[3] - bounds[1] > jobs_canvas.winfo_height() + 1)

        def update_jobs_scroll_state():
            bounds = jobs_canvas.bbox("all")
            jobs_canvas.configure(scrollregion=bounds or (0, 0, 0, 0))
            if jobs_content_overflows():
                if not jobs_scrollbar.winfo_ismapped():
                    jobs_scrollbar.pack(side="right", fill="y")
            else:
                jobs_canvas.yview_moveto(0)
                if jobs_scrollbar.winfo_ismapped():
                    jobs_scrollbar.pack_forget()

        def configure_jobs_scroll(event):
            jobs_canvas.itemconfig(jobs_canvas_window, width=jobs_canvas.winfo_width())
            jobs_canvas.after_idle(update_jobs_scroll_state)

        def resize_jobs_canvas(event):
            jobs_canvas.itemconfig(jobs_canvas_window, width=event.width)
            jobs_canvas.after_idle(update_jobs_scroll_state)

        self.jobs_container.bind("<Configure>", configure_jobs_scroll)
        jobs_canvas.bind("<Configure>", resize_jobs_canvas)
        jobs_canvas.after_idle(update_jobs_scroll_state)

        def on_jobs_mousewheel(event):
            if jobs_canvas.winfo_exists() and jobs_content_overflows():
                try:
                    jobs_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
                except tk.TclError:
                    pass

        jobs_canvas.bind(
            "<Enter>", lambda _event: jobs_canvas.bind_all("<MouseWheel>", on_jobs_mousewheel)
        )
        jobs_canvas.bind(
            "<Leave>", lambda _event: jobs_canvas.bind_all("<MouseWheel>", self._main_mousewheel)
        )
        self.jobs_canvas = jobs_canvas
        self.jobs_list_frame = jobs_list_frame

        # ---- Workspace: editor card / results card (draggable divider) ----
        split = tk.PanedWindow(
            workspace,
            orient=tk.VERTICAL,
            bg=APP_BG,
            sashwidth=12,
            sashrelief="flat",
            sashcursor="sb_v_double_arrow",
            bd=0,
            showhandle=False,
            opaqueresize=True,
        )
        split.pack(fill="both", expand=True, padx=16, pady=(14, 14))

        def _card(parent):
            return ui_round_frame(parent, fill=UI["card"], border=UI["border"], radius=10, pad=3)

        FL = UI
        _qf_outer, query_frame = _card(split)
        _rc_outer, results_card = _card(split)
        split.add(_qf_outer, minsize=180, height=330, stretch="always")
        split.add(_rc_outer, minsize=200, stretch="always")
        query_frame.columnconfigure(0, weight=1)
        query_frame.rowconfigure(3, weight=1)

        # --- Editor toolbar ---------------------------------------------
        toolbar = tk.Frame(query_frame, bg=FL["card"])
        toolbar.grid(row=0, column=0, sticky="ew")
        tk.Frame(query_frame, bg=FL["border"], height=1).grid(row=1, column=0, sticky="ew")
        tb = tk.Frame(toolbar, bg=FL["card"])
        tb.pack(side="left", padx=12, pady=9)

        self.execute_btn = ui_rbutton(
            tb, "▶  Run", self.execute_query, "primary", "md", state="disabled"
        )
        self.execute_btn.pack(side="left", padx=(0, 8))

        self.stop_btn = ui_rbutton(tb, "⏹  Stop", self.stop_running_queries, "danger", "md")
        self.stop_btn.pack(side="left", padx=(0, 10))
        self._register_stop_button(self.stop_btn)

        _vline(tb).pack(side="left", padx=(0, 10))

        def _tool(text, command, **opts):
            outer, btn = ui_button(tb, text, command, size="sm", **opts)
            outer.pack(side="left", padx=(0, 6))
            return btn

        self.load_excel_btn = _tool("📗  Load Excel", self.load_excel_template_dialog)
        self.reset_sql_template_btn = _tool("↩  Reset template", self.show_reset_parameter_dialog)
        self.save_job_btn = _tool("💾  Save as Job", self.save_job_dialog)
        self.inspect_btn = _tool("▦  Tables", self.list_tables, state="disabled")

        tk.Label(
            toolbar, text="Ctrl + Enter  เพื่อรัน", bg=FL["card"], fg=FL["subtle"], font=UI_FONT_SM
        ).pack(side="right", padx=14)

        # --- Excel parameter strip (shown while Excel values are in the SQL)
        excel_strip = tk.Frame(query_frame, bg=SELECTED)
        excel_strip_text = tk.Label(
            excel_strip, text="", bg=SELECTED, fg=FL["text"], font=UI_FONT_SM, anchor="w"
        )
        tk.Label(excel_strip, text="📗", bg=SELECTED, fg=FL["primary"], font=UI_FONT).pack(
            side="left", padx=(12, 6), pady=5
        )
        excel_strip_text.pack(side="left", pady=5)
        _ghost(
            excel_strip, "✎  เปลี่ยนค่า", self.load_excel_template_dialog, bg=SELECTED
        ).pack(side="right", padx=8)
        tk.Frame(excel_strip, bg=FL["border"], height=1).place(relx=0, rely=1.0, relwidth=1, anchor="sw")

        # --- SQL editor -------------------------------------------------
        editor_border = tk.Frame(query_frame, bg=FL["card"], bd=0)
        editor_border.grid(row=3, column=0, sticky="nsew")
        editor_border.columnconfigure(1, weight=1)
        editor_border.rowconfigure(0, weight=1)

        line_gutter = tk.Canvas(
            editor_border, width=46, bg=FL["surface"], highlightthickness=0, bd=0
        )
        line_gutter.grid(row=0, column=0, sticky="ns")

        self.sql_context = scrolledtext.ScrolledText(
            editor_border,
            height=12,
            width=70,
            font=("Consolas", 11),
            undo=True,
            maxundo=-1,
            bg="#FFFFFF",
            fg=FL["text"],
            insertbackground=FL["text"],
            selectbackground="#BFDBFE",
            selectforeground=FL["text"],
            relief="flat",
            bd=0,
            highlightthickness=0,
            padx=12,
            pady=8,
        )
        self.sql_context.grid(row=0, column=1, sticky=(tk.W, tk.E, tk.N, tk.S))
        self.sql_context.insert(1.0, self.DEFAULT_SQL_QUERY)
        # Defer edit_reset so it runs after widget is fully ready — clears undo stack to fresh start
        self.sql_context.after(200, self.sql_context.edit_reset)

        # Syntax colours (display-only tags; the SQL text itself is untouched)
        self.sql_context.tag_configure("sql_kw", foreground="#7C3AED")
        self.sql_context.tag_configure("sql_str", foreground="#047857")
        self.sql_context.tag_configure("sql_param", foreground="#C2410C")
        self.sql_context.tag_configure("sql_comment", foreground="#94A3B8")
        self.sql_context.tag_raise("sel")
        _sql_kw = re.compile(
            r"\b(SELECT|FROM|WHERE|AND|OR|NOT|IN|IS|NULL|AS|ON|JOIN|LEFT|RIGHT|INNER|OUTER|FULL|"
            r"GROUP|BY|ORDER|HAVING|DISTINCT|UNION|ALL|INSERT|INTO|VALUES|UPDATE|SET|DELETE|"
            r"CREATE|DROP|ALTER|TABLE|WITH|CASE|WHEN|THEN|ELSE|END|LIKE|BETWEEN|EXISTS|ASC|DESC|"
            r"TRUNC|SYSDATE|COUNT|SUM|MIN|MAX|AVG)\b",
            re.IGNORECASE,
        )

        def _highlight_sql(text_value):
            w = self.sql_context
            for tag in ("sql_kw", "sql_str", "sql_param", "sql_comment"):
                w.tag_remove(tag, "1.0", tk.END)
            for pattern, tag in (
                (_sql_kw, "sql_kw"),
                (re.compile(r"\{\{?\s*\w+\s*\}\}?|:\w+"), "sql_param"),
                (re.compile(r"'[^'\n]*'"), "sql_str"),
                (re.compile(r"--[^\n]*"), "sql_comment"),
            ):
                for m in pattern.finditer(text_value):
                    w.tag_add(tag, f"1.0+{m.start()}c", f"1.0+{m.end()}c")

        _gutter_state = {"sig": None, "text": None}

        def _draw_line_numbers():
            """Redraw gutter numbers for the visible lines (read-only on the editor)."""
            line_gutter.delete("all")
            gutter_width = int(line_gutter.cget("width"))
            line_gutter.create_line(gutter_width - 1, 0, gutter_width - 1, 10000, fill=FL["border"])
            current_line = self.sql_context.index(tk.INSERT).split(".")[0]
            index = self.sql_context.index("@0,0")
            while True:
                info = self.sql_context.dlineinfo(index)
                if info is None:
                    break
                line_no = index.split(".")[0]
                line_gutter.create_text(
                    gutter_width - 10,
                    info[1] + info[4] // 2,
                    anchor="e",
                    text=line_no,
                    font=UI_FONT_MONO,
                    fill=FL["text"] if line_no == current_line else FL["subtle"],
                )
                next_index = self.sql_context.index(f"{index}+1line")
                if next_index == index:
                    break
                index = next_index

        def _poll_line_numbers():
            try:
                if not line_gutter.winfo_exists():
                    return
                sig = (
                    self.sql_context.yview(),
                    self.sql_context.index("end"),
                    self.sql_context.index(tk.INSERT),
                    self.sql_context.winfo_height(),
                    self.sql_context.winfo_width(),
                )
                if sig != _gutter_state["sig"]:
                    _gutter_state["sig"] = sig
                    _draw_line_numbers()
                text_value = self.sql_context.get("1.0", "end-1c")
                if text_value != _gutter_state["text"]:
                    _gutter_state["text"] = text_value
                    _highlight_sql(text_value)
            except tk.TclError:
                return
            line_gutter.after(120, _poll_line_numbers)

        _poll_line_numbers()

        def _text_ctrl_key(e):
            """Handle Ctrl+Z/Y/C/X/V for Text/ScrolledText by Windows keycode — works with any keyboard layout (Thai/EN)."""
            kc = e.keycode
            w = e.widget
            if kc == 90:  # Z — Undo
                try:
                    w.edit_undo()
                except Exception:
                    pass
                return "break"
            elif kc == 89:  # Y — Redo
                try:
                    w.edit_redo()
                except Exception:
                    pass
                return "break"
            elif kc == 67:  # C — Copy
                try:
                    sel = w.get(tk.SEL_FIRST, tk.SEL_LAST)
                    self.root.clipboard_clear()
                    self.root.clipboard_append(sel)
                except Exception:
                    pass
                return "break"
            elif kc == 88:  # X — Cut
                try:
                    sel = w.get(tk.SEL_FIRST, tk.SEL_LAST)
                    self.root.clipboard_clear()
                    self.root.clipboard_append(sel)
                    w.delete(tk.SEL_FIRST, tk.SEL_LAST)
                except Exception:
                    pass
                return "break"
            elif kc == 86:  # V — Paste
                try:
                    txt = self.root.clipboard_get()
                    try:
                        w.delete(tk.SEL_FIRST, tk.SEL_LAST)
                    except Exception:
                        pass
                    w.insert(tk.INSERT, txt)
                except Exception:
                    pass
                return "break"
            elif kc == 65:  # A — Select All
                try:
                    w.tag_add(tk.SEL, "1.0", tk.END)
                except Exception:
                    pass
                return "break"

        self.sql_context.bind("<Control-KeyPress>", _text_ctrl_key)

        # Keyboard shortcut binding
        self.sql_context.bind(
            "<Control-Return>",
            lambda _event: (
                self.execute_query() if self.execute_btn["state"] != "disabled" else None
            ),
        )

        # Update jobs list
        self.update_jobs_list()

        # ------------------------------------------------------------------
        # Results card: [running banner] + tabs (Results / Logs / Error)
        # ------------------------------------------------------------------
        running_banner = tk.Frame(results_card, bg=WARN_SOFT)
        rb_left = tk.Frame(running_banner, bg=WARN_SOFT)
        rb_left.pack(side="left", fill="x", expand=True, padx=(14, 10), pady=8)
        rb_text = tk.Label(
            rb_left, text="", bg=WARN_SOFT, fg=UI["text"], font=UI_FONT_SEMI, anchor="w"
        )
        rb_text.pack(fill="x")
        rb_progress = ttk.Progressbar(
            rb_left, style="Running.Horizontal.TProgressbar", mode="determinate", maximum=100
        )
        rb_progress.pack(fill="x", pady=(4, 0))
        _rb_stop = ui_rbutton(running_banner, "⏹  Stop", self.stop_running_queries, "danger", "sm")
        _rb_stop.pack(side="right", padx=12)
        self._register_stop_button(_rb_stop)

        self.results_notebook = ttk.Notebook(results_card, style="Fluent.TNotebook")
        self.results_notebook.pack(fill="both", expand=True)

        # Open result windows (top-right of the tab strip)
        _rw = self._result_windows_checkbox(results_card, UI["card"])
        # positioned on the tab strip, so it moves down with it when the banner shows
        _rw.place(in_=self.results_notebook, relx=1.0, x=-14, y=6, anchor="ne")
        _rw.lift()

        # --- Tab 1: Results Grid (in-window viewer; popup windows still open as before)
        grid_tab = tk.Frame(self.results_notebook, bg=UI["card"])
        self._build_results_grid_tab(grid_tab)

        # --- Tab 2: Execution Logs (the existing results_text widget)
        results_frame = tk.Frame(self.results_notebook, bg=UI["card"])
        results_frame.columnconfigure(0, weight=1)
        results_frame.rowconfigure(1, weight=1)

        log_toolbar = tk.Frame(results_frame, bg=UI["card"])
        log_toolbar.grid(row=0, column=0, sticky="ew", padx=16, pady=(10, 0))
        self._log_file_label = tk.Label(
            log_toolbar, text="", bg=UI["card"], fg=UI["muted"], font=UI_FONT_SM
        )
        self._log_file_label.pack(side="left")
        _outer, _ = ui_button(log_toolbar, "📂 Open Log Folder", self.open_log_folder, size="sm")
        _outer.pack(side="right")

        self.results_text = scrolledtext.ScrolledText(
            results_frame,
            height=12,
            width=140,
            font=UI_FONT_MONO,
            wrap=tk.NONE,
            bg="#FFFFFF",
            fg=UI["text"],
            insertbackground=UI["text"],
            selectbackground="#BFDBFE",
            selectforeground=UI["text"],
            relief="flat",
            bd=0,
            highlightthickness=1,
            highlightbackground=UI["border"],
            highlightcolor=UI["border"],
            padx=10,
            pady=8,
        )
        self.results_text.grid(
            row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=16, pady=(8, 14)
        )

        # Everything written to the Execution Logs is also appended to
        # logs/run_YYYY-MM-DD.log (with a timestamp per line)
        self._init_run_log()
        _log_insert = self.results_text.insert

        def _insert_and_log(index, chars, *args):
            result = _log_insert(index, chars, *args)
            if isinstance(chars, str):
                self._write_run_log(chars)
            return result

        self.results_text.insert = _insert_and_log

        # --- Tab 3: Error & Debug
        debug_tab = tk.Frame(self.results_notebook, bg=UI["card"])
        self._build_error_debug_tab(debug_tab)

        self.results_notebook.add(grid_tab, text="📊 Results Grid")
        self.results_notebook.add(results_frame, text="📋 Execution Logs")
        self.results_notebook.add(debug_tab, text="🐛 Error & Debug")
        self.results_notebook.select(results_frame)

        def _on_results_enter(_event):
            self.results_text.bind_all(
                "<MouseWheel>",
                lambda ev: self.results_text.yview_scroll(int(-1 * (ev.delta / 120)), "units"),
            )

        def _on_results_leave(_event):
            self.results_text.bind_all("<MouseWheel>", self._main_mousewheel)

        self.results_text.bind("<Enter>", _on_results_enter)
        self.results_text.bind("<Leave>", _on_results_leave)
        self.results_text.bind("<Control-KeyPress>", _text_ctrl_key)

        # ------------------------------------------------------------------
        # Status bar
        # ------------------------------------------------------------------
        status_bar = tk.Frame(root, bg=UI["card"])
        status_bar.grid(row=3, column=0, sticky="ew")
        _hline(status_bar).pack(side="top", fill="x")
        sb_inner = tk.Frame(status_bar, bg=UI["card"])
        sb_inner.pack(fill="x", padx=16, pady=3)

        def _status_item(side="left"):
            box = tk.Frame(sb_inner, bg=UI["card"])
            box.pack(side=side, padx=(0, 16) if side == "left" else (16, 0))
            dot = tk.Label(box, text="●", bg=UI["card"], fg=UI["off"], font=("Segoe UI", 8))
            dot.pack(side="left", padx=(0, 4))
            lbl = tk.Label(box, text="", bg=UI["card"], fg=UI["muted"], font=UI_FONT_SM)
            lbl.pack(side="left")
            return dot, lbl

        _sb_activity = _status_item()
        _sb_conn = _status_item()
        _sb_excel = _status_item()
        _sb_cursor = tk.Label(sb_inner, text="", bg=UI["card"], fg=UI["subtle"], font=UI_FONT_SM)
        _sb_cursor.pack(side="right")
        _sb_log = tk.Label(sb_inner, text="", bg=UI["card"], fg=UI["subtle"], font=UI_FONT_SM)
        _sb_log.pack(side="right", padx=(0, 16))

        # Progress of the current run (display only): wrap the existing
        # methods so the banner knows "Job i / N" — behaviour is unchanged.
        self._ui_progress = {"total": 0, "index": 0, "name": "", "kind": None}
        _orig_update_job_status = self.update_job_status
        _orig_run_selected_job = self.run_selected_job

        def _ui_update_job_status(job_num, job, status, *args, **kwargs):
            if status == "running":
                self._ui_progress.update(index=job_num, name=job.get("name", ""))
            return _orig_update_job_status(job_num, job, status, *args, **kwargs)

        def _ui_run_selected_job(jobs_override=None):
            try:
                total = (
                    len(jobs_override) if jobs_override is not None else len(self.get_jobs_to_run())
                )
            except Exception:
                total = 0
            self._ui_progress = {"total": total, "index": 0, "name": "", "kind": "jobs"}
            return _orig_run_selected_job(jobs_override)

        self.update_job_status = _ui_update_job_status
        self.run_selected_job = _ui_run_selected_job

        _run_clock = {"start": None}

        def _excel_summary():
            values = getattr(self, "_excel_parameter_values", {}) or {}
            parts = []
            for key, data in values.items():
                try:
                    parameter, sql_values = data
                except (TypeError, ValueError):
                    continue
                count = len([v for v in str(sql_values).split(",") if v.strip()])
                name = key if parameter == getattr(self, "AUTO_WHERE_PARAMETER", None) else parameter
                parts.append(f"{name} ← {count} ค่า")
            return parts

        def _refresh_live_ui():
            """Poll-only: banner, Excel strip, status bar. Never changes app state."""
            try:
                if not status_bar.winfo_exists():
                    return
                busy_batch = getattr(self, "_batch_running", False)
                busy_exec = "Loading" in str(self.execute_btn.cget("text"))
                busy_export = "Exporting" in str(self.export_excel_btn.cget("text"))
                busy = busy_batch or busy_exec or busy_export
                if busy and _run_clock["start"] is None:
                    _run_clock["start"] = time.time()
                elif not busy:
                    _run_clock["start"] = None

                # Running banner
                if busy:
                    elapsed = int(time.time() - (_run_clock["start"] or time.time()))
                    clock = f"{elapsed // 60:02d}:{elapsed % 60:02d}"
                    prog = self._ui_progress
                    if busy_batch and prog.get("total"):
                        text = (
                            f"กำลังรัน Job {max(prog.get('index', 0), 1)} / {prog['total']}"
                            + (f" · {prog['name']}" if prog.get("name") else "")
                            + f" · {clock}"
                        )
                        if str(rb_progress.cget("mode")) != "determinate":
                            rb_progress.stop()
                            rb_progress.config(mode="determinate")
                        rb_progress["value"] = 100 * max(prog.get("index", 1) - 1, 0) / prog["total"]
                    else:
                        text = ("กำลัง Export Excel" if busy_export else "กำลังรัน SQL") + f" · {clock}"
                        if str(rb_progress.cget("mode")) != "indeterminate":
                            rb_progress.config(mode="indeterminate")
                            rb_progress.start(12)
                    if rb_text.cget("text") != text:
                        rb_text.config(text=text)
                    if not running_banner.winfo_ismapped():
                        running_banner.pack(side="top", fill="x", before=self.results_notebook)
                elif running_banner.winfo_ismapped():
                    rb_progress.stop()
                    running_banner.pack_forget()

                # Excel strip
                parts = _excel_summary()
                if parts:
                    strip_text = "Excel parameter:  " + "   ·   ".join(parts)
                    if excel_strip_text.cget("text") != strip_text:
                        excel_strip_text.config(text=strip_text)
                    if not excel_strip.winfo_ismapped():
                        excel_strip.grid(row=2, column=0, sticky="ew")
                elif excel_strip.winfo_ismapped():
                    excel_strip.grid_forget()

                # Status bar
                _sb_activity[0].config(fg=FL["warn"] if busy else FL["ok"])
                _sb_activity[1].config(text="Running…" if busy else "Ready")
                raw = str(self.status_label.cget("text"))
                connected = raw.startswith("✅")
                _sb_conn[0].config(fg=FL["ok"] if connected else FL["off"])
                _sb_conn[1].config(
                    text=raw.replace("✅", "").strip() if connected else "Not connected"
                )
                _sb_excel[0].config(fg=FL["primary"] if parts else FL["off"])
                _sb_excel[1].config(text=f"Excel: {len(parts)} parameter" if parts else "No Excel")
                try:
                    _sb_log.config(text=f"Log: logs/{os.path.basename(self._run_log_path())}")
                except Exception:
                    pass
                line, col = self.sql_context.index(tk.INSERT).split(".")
                _sb_cursor.config(text=f"Ln {line}, Col {int(col) + 1}")
            except tk.TclError:
                return
            status_bar.after(300, _refresh_live_ui)

        _refresh_live_ui()

        # Apply the Modern Enterprise theme to every dialog/popup (presentation only)
        self._dialog_theme = DialogTheme(self.root)

        self._refresh_stop_buttons()

        # Auto-load last used profile
        self.auto_load_last_profile()

        # Add context menus
        self.setup_context_menus()

    def _create_centered_dialog(self, title, width, height):
        """Helper method to create centered dialog with consistent styling"""
        dialog = tk.Toplevel(self.root)
        dialog.title(title)
        dialog.geometry(f"{width}x{height}")
        dialog.configure(bg="#f0f0f0")
        dialog.transient(self.root)
        dialog.grab_set()

        # Center dialog
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - (width // 2)
        y = (dialog.winfo_screenheight() // 2) - (height // 2)
        dialog.geometry(f"+{x}+{y}")

        return dialog

    def export_profiles_dialog(self):
        """Export profiles to a user-selected JSON file"""
        if not self.saved_profiles:
            messagebox.showinfo(
                "No Profiles", "No profiles to export.\n\nCreate and save a profile first."
            )
            return

        # Ask user where to save
        file_path = filedialog.asksaveasfilename(
            title="Export Profiles",
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            initialfile="db_profiles_backup.json",
        )

        if not file_path:
            return  # User cancelled

        include_passwords = messagebox.askyesnocancel(
            "Export Passwords?",
            "Include passwords in the exported file?\n\n"
            "Yes = include (plain text, so it can be imported on another computer)\n"
            "No = export without passwords (safer - re-enter them after import)",
        )
        if include_passwords is None:
            return  # User cancelled

        try:
            export_profiles = {}
            for name, profile in self.saved_profiles.items():
                profile_copy = dict(profile)
                if not include_passwords:
                    profile_copy["db_password"] = ""
                export_profiles[name] = profile_copy

            # Export profiles with metadata
            export_data = {
                "exported_date": pd.Timestamp.now().isoformat(),
                "total_profiles": len(export_profiles),
                "passwords_included": bool(include_passwords),
                "profiles": export_profiles,
            }

            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(export_data, f, indent=2, ensure_ascii=False)

            # Show success with file location
            self.results_text.insert(tk.END, f"📤 Profiles exported successfully!\n")
            self.results_text.insert(tk.END, f"📁 Location: {file_path}\n")
            self.results_text.insert(tk.END, f"📊 Profiles: {len(self.saved_profiles)}\n\n")
            self.results_text.see(tk.END)

            messagebox.showinfo(
                "Export Success",
                f"✅ Profiles exported successfully!\n\n"
                f"📁 Location:\n{file_path}\n\n"
                f"📊 Total profiles: {len(self.saved_profiles)}\n\n"
                f"💡 You can import this file on any computer.",
            )

        except Exception as e:
            error_msg = f"Failed to export profiles:\n\n{str(e)}"
            self.results_text.insert(tk.END, f"❌ Export failed: {str(e)}\n\n")
            self.results_text.see(tk.END)
            messagebox.showerror("Export Error", error_msg)

    def import_profiles_dialog(self):
        """Import profiles from a user-selected JSON file"""
        # Ask user to select file
        file_path = filedialog.askopenfilename(
            title="Import Profiles", filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )

        if not file_path:
            return  # User cancelled

        try:
            # Load the file
            with open(file_path, "r", encoding="utf-8") as f:
                import_data = json.load(f)

            # Check if it's an export file or raw profile data
            if "profiles" in import_data:
                # New export format
                imported_profiles = import_data["profiles"]
                export_date = import_data.get("exported_date", "Unknown")
                total_count = import_data.get("total_profiles", len(imported_profiles))
            else:
                # Raw profile data (old format)
                imported_profiles = {
                    k: v
                    for k, v in import_data.items()
                    if k != "last_used_profile" and isinstance(v, dict)
                }
                export_date = "Unknown"
                total_count = len(imported_profiles)

            if not imported_profiles:
                messagebox.showwarning(
                    "No Profiles", "No valid profiles found in the selected file."
                )
                return

            # Show preview dialog
            self._show_import_preview_dialog(imported_profiles, file_path, export_date, total_count)

        except json.JSONDecodeError:
            messagebox.showerror(
                "Import Error",
                "Invalid JSON file.\n\n" "Please select a valid profile export file.",
            )
        except Exception as e:
            messagebox.showerror("Import Error", f"Failed to import profiles:\n\n{str(e)}")

    def _show_import_preview_dialog(self, imported_profiles, file_path, export_date, total_count):
        """Show preview dialog before importing profiles"""
        dialog = tk.Toplevel(self.root)
        dialog.title("📥 Import Profiles")
        dialog.geometry("700x600")
        dialog.configure(bg="#f0f0f0")
        dialog.transient(self.root)
        dialog.grab_set()

        # Center dialog
        x = (self.root.winfo_screenwidth() - 700) // 2
        y = (self.root.winfo_screenheight() - 600) // 2
        dialog.geometry(f"+{x}+{y}")

        # Scrollable content container (Canvas + Scrollbar + inner frame)
        outer_frame = tk.Frame(dialog, bg="#ffffff", relief="solid", bd=1)
        outer_frame.pack(fill="both", expand=True, padx=15, pady=15)

        content_canvas = tk.Canvas(outer_frame, bg="#ffffff", highlightthickness=0)
        content_scrollbar = ttk.Scrollbar(
            outer_frame, orient="vertical", command=content_canvas.yview
        )
        content_canvas.configure(yscrollcommand=content_scrollbar.set)

        content_scrollbar.pack(side="right", fill="y")
        content_canvas.pack(side="left", fill="both", expand=True)

        content_frame = tk.Frame(content_canvas, bg="#ffffff")
        content_canvas_window = content_canvas.create_window(
            (0, 0), window=content_frame, anchor="nw"
        )

        def _update_dialog_scrollregion(event=None):
            content_canvas.configure(scrollregion=content_canvas.bbox("all"))

        def _sync_dialog_canvas_width(event):
            content_canvas.itemconfig(content_canvas_window, width=event.width)

        def _on_dialog_mousewheel(event):
            if event.widget.winfo_class() == "Listbox":
                return
            content_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        content_frame.bind("<Configure>", _update_dialog_scrollregion)
        content_canvas.bind("<Configure>", _sync_dialog_canvas_width)
        dialog.bind("<MouseWheel>", _on_dialog_mousewheel)

        # Title
        tk.Label(
            content_frame,
            text="📥 Import Profiles Preview",
            font=("Arial", 14, "bold"),
            bg="#ffffff",
            fg="#2c3e50",
        ).pack(pady=(10, 15))

        # File info
        info_frame = tk.Frame(content_frame, bg="#e8f4f8", relief="solid", bd=1)
        info_frame.pack(fill="both", padx=10, pady=(0, 15))

        info_text = f"📁 File: {os.path.basename(file_path)}\n"
        info_text += (
            f"📅 Exported: " f"{export_date[:19] if export_date != 'Unknown' else 'Unknown'}\n"
        )
        info_text += f"📊 Profiles in file: {total_count}"

        tk.Label(
            info_frame,
            text=info_text,
            font=("Arial", 9),
            bg="#e8f4f8",
            fg="#2c3e50",
            justify="left",
        ).pack(anchor="w", padx=10, pady=8)

        # Current vs Import status
        status_frame = tk.LabelFrame(
            content_frame, text="Import Status", font=("Arial", 11, "bold"), bg="#ffffff"
        )
        status_frame.pack(fill="both", padx=10, pady=(0, 15))

        status_inner = tk.Frame(status_frame, bg="#ffffff")
        status_inner.pack(fill="both", padx=10, pady=10)

        current_count = len(self.saved_profiles)
        new_profiles = [p for p in imported_profiles.keys() if p not in self.saved_profiles]
        existing_profiles = [p for p in imported_profiles.keys() if p in self.saved_profiles]

        tk.Label(
            status_inner,
            text=f"📊 Current profiles: {current_count}",
            font=("Arial", 10),
            bg="#ffffff",
            fg="#2c3e50",
        ).pack(anchor="w", pady=2)
        tk.Label(
            status_inner,
            text=f"➕ New profiles to add: {len(new_profiles)}",
            font=("Arial", 10),
            bg="#ffffff",
            fg="#27ae60",
        ).pack(anchor="w", pady=2)
        tk.Label(
            status_inner,
            text=f"🔄 Existing profiles (will be updated): {len(existing_profiles)}",
            font=("Arial", 10),
            bg="#ffffff",
            fg="#f39c12",
        ).pack(anchor="w", pady=2)
        tk.Label(
            status_inner,
            text=f"📊 Total after import: {len(set(list(self.saved_profiles.keys()) + list(imported_profiles.keys())))}",
            font=("Arial", 10, "bold"),
            bg="#ffffff",
            fg="#3498db",
        ).pack(anchor="w", pady=(10, 2))

        # Profile list
        list_frame = tk.LabelFrame(
            content_frame, text="Profiles to Import", font=("Arial", 11, "bold"), bg="#ffffff"
        )
        list_frame.pack(fill="both", expand=True, padx=10, pady=(0, 15))

        list_inner = tk.Frame(list_frame, bg="#ffffff")
        list_inner.pack(fill="both", expand=True, padx=10, pady=10)

        scrollbar = tk.Scrollbar(list_inner)
        scrollbar.pack(side="right", fill="y")

        profiles_listbox = tk.Listbox(
            list_inner, font=("Arial", 10), yscrollcommand=scrollbar.set, height=10
        )
        profiles_listbox.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=profiles_listbox.yview)

        # Populate list
        for profile_name, profile_data in imported_profiles.items():
            db_type = profile_data.get("db_type", "N/A")
            host = profile_data.get("db_host", "N/A")
            status_icon = "➕" if profile_name not in self.saved_profiles else "🔄"
            profiles_listbox.insert("end", f"{status_icon} {profile_name} ({db_type} @ {host})")

        # Import options
        options_frame = tk.LabelFrame(
            content_frame, text="Import Options", font=("Arial", 11, "bold"), bg="#ffffff"
        )
        options_frame.pack(fill="both", padx=10, pady=(0, 15))

        merge_var = tk.BooleanVar(value=True)

        tk.Radiobutton(
            options_frame,
            text="🔄 Merge (keep existing + add new profiles)",
            variable=merge_var,
            value=True,
            font=("Arial", 10),
            bg="#ffffff",
        ).pack(anchor="w", padx=10, pady=5)

        tk.Radiobutton(
            options_frame,
            text="🔁 Replace (delete all existing profiles)",
            variable=merge_var,
            value=False,
            font=("Arial", 10),
            bg="#ffffff",
        ).pack(anchor="w", padx=10, pady=5)

        # Warning
        warning_frame = tk.Frame(content_frame, bg="#fff3cd", relief="solid", bd=1)
        warning_frame.pack(fill="both", padx=10, pady=(0, 15))

        tk.Label(
            warning_frame,
            text="⚠️ Importing will update existing profiles with the same name.\n"
            "💡 Consider exporting current profiles as backup first.",
            font=("Arial", 9),
            bg="#fff3cd",
            fg="#856404",
            justify="left",
        ).pack(padx=10, pady=8)

        # Buttons
        button_frame = tk.Frame(content_frame, bg="#ffffff")
        button_frame.pack(fill="both", padx=10, pady=(0, 10))

        def do_import():
            try:
                merge_mode = merge_var.get()
                previous_profiles = dict(self.saved_profiles)

                if not merge_mode:
                    # Replace mode - confirm
                    result = messagebox.askyesno(
                        "Confirm Replace",
                        f"⚠️ This will DELETE all {len(self.saved_profiles)} existing profiles!\n\n"
                        f"Are you sure?",
                        parent=dialog,
                    )
                    if not result:
                        return

                    # Clear existing profiles
                    self.saved_profiles.clear()

                # Import profiles
                for profile_name, profile_data in imported_profiles.items():
                    profile_data = dict(profile_data)
                    imported_password = unprotect_password(profile_data.get("db_password", ""))
                    existing_password = previous_profiles.get(profile_name, {}).get(
                        "db_password", ""
                    )
                    # File exported without passwords -> keep the password we already have
                    profile_data["db_password"] = imported_password or existing_password
                    self.saved_profiles[profile_name] = profile_data

                # Save to file
                self.save_profiles()

                # Update UI
                self.update_profile_list()

                # Update results
                self.results_text.insert(tk.END, f"📥 Profiles imported successfully!\n")
                self.results_text.insert(tk.END, f"📊 Total profiles: {len(self.saved_profiles)}\n")
                self.results_text.insert(tk.END, f"➕ New profiles: {len(new_profiles)}\n")
                if merge_mode:
                    self.results_text.insert(
                        tk.END, f"🔄 Updated profiles: {len(existing_profiles)}\n"
                    )
                self.results_text.insert(tk.END, f"\n")
                self.results_text.see(tk.END)

                # Success message
                mode_text = "merged" if merge_mode else "replaced"
                messagebox.showinfo(
                    "Import Success",
                    f"✅ Profiles {mode_text} successfully!\n\n"
                    f"📊 Total profiles now: {len(self.saved_profiles)}\n"
                    f"➕ New: {len(new_profiles)}\n"
                    f"🔄 Updated: {len(existing_profiles) if merge_mode else 0}",
                    parent=dialog,
                )

                dialog.destroy()

            except Exception as e:
                messagebox.showerror(
                    "Import Error", f"Failed to import profiles:\n\n{str(e)}", parent=dialog
                )

        tk.Button(
            button_frame,
            text="📥 Import Profiles",
            command=do_import,
            bg="#27ae60",
            fg="white",
            font=("Arial", 10, "bold"),
            padx=20,
            pady=6,
        ).pack(side="left")

        cancel_btn = tk.Button(
            button_frame,
            text="✖ Cancel",
            width=12,
            height=2,
            bg="#95a5a6",
            fg="white",
            font=("Arial", 10, "bold"),
            command=dialog.destroy,
        )

        cancel_btn.pack(side="left", padx=5)

        _update_dialog_scrollregion()

    def show_config_file_location(self):
        """Show where the config file is/should be located - Helper function"""
        dialog = tk.Toplevel(self.root)
        dialog.title("📁 Config File Location")
        dialog.geometry("600x600")
        dialog.configure(bg="#f0f0f0")
        dialog.transient(self.root)
        dialog.grab_set()

        # Center dialog
        x = (self.root.winfo_screenwidth() - 600) // 2
        y = (self.root.winfo_screenheight() - 400) // 2
        dialog.geometry(f"+{x}+{y}")

        # Content
        content = tk.Frame(dialog, bg="#ffffff", relief="solid", bd=1)
        content.pack(fill="both", expand=True, padx=15, pady=15)

        tk.Label(
            content,
            text="📁 Config File Location",
            font=("Arial", 14, "bold"),
            bg="#ffffff",
            fg="#2c3e50",
        ).pack(pady=(10, 15))

        # File info
        info_frame = tk.LabelFrame(
            content, text="File Information", font=("Arial", 11, "bold"), bg="#ffffff"
        )
        info_frame.pack(fill="both", expand=True, padx=10, pady=(0, 15))

        info_inner = tk.Frame(info_frame, bg="#ffffff")
        info_inner.pack(fill="both", expand=True, padx=10, pady=10)

        # Path
        tk.Label(
            info_inner, text="📁 Full Path:", font=("Arial", 10, "bold"), bg="#ffffff", fg="#2c3e50"
        ).pack(anchor="w", pady=(0, 5))

        path_text = tk.Text(info_inner, height=3, font=("Courier", 9), bg="#f8f9fa", wrap=tk.WORD)
        path_text.pack(fill="both", pady=(0, 10))
        path_text.insert(1.0, self.config_file)
        path_text.config(state="disabled")

        # Status
        file_exists = os.path.exists(self.config_file)
        status_icon = "✅" if file_exists else "❌"
        status_text = "EXISTS" if file_exists else "NOT FOUND"
        status_color = "#27ae60" if file_exists else "#e74c3c"

        tk.Label(
            info_inner,
            text=f"📊 Status: {status_icon} {status_text}",
            font=("Arial", 10, "bold"),
            bg="#ffffff",
            fg=status_color,
        ).pack(anchor="w", pady=(0, 5))

        if file_exists:
            file_size = os.path.getsize(self.config_file)
            tk.Label(
                info_inner,
                text=f"📏 Size: {file_size:,} bytes",
                font=("Arial", 10),
                bg="#ffffff",
                fg="#2c3e50",
            ).pack(anchor="w", pady=(0, 5))

            tk.Label(
                info_inner,
                text=f"📊 Profiles: {len(self.saved_profiles)}",
                font=("Arial", 10),
                bg="#ffffff",
                fg="#2c3e50",
            ).pack(anchor="w")

        # Help text
        help_frame = tk.Frame(content, bg="#e8f4f8", relief="solid", bd=1)
        help_frame.pack(fill="both", padx=10, pady=(0, 15))

        if file_exists:
            help_text = "💡 Tips:\n\n"
        else:
            help_text = "💡 If the file doesn't exist:\n\n"
        help_text += "1. Save a profile to create the file automatically\n"
        help_text += "2. Use 'Export' to backup your profiles\n"
        help_text += "3. Use 'Import' to restore from backup\n"
        help_text += "4. Share exported files between computers"

        tk.Label(
            help_frame,
            text=help_text,
            font=("Arial", 9),
            bg="#e8f4f8",
            fg="#2c3e50",
            justify="left",
        ).pack(padx=10, pady=10)

        # Buttons
        button_frame = tk.Frame(content, bg="#ffffff")
        button_frame.pack(pady=(0, 10))

        def open_folder():
            folder_path = os.path.dirname(self.config_file)
            if os.path.exists(folder_path):
                os.startfile(folder_path)
            else:
                messagebox.showwarning(
                    "Folder Not Found", f"Folder doesn't exist:\n{folder_path}", parent=dialog
                )

        def copy_path():
            self.root.clipboard_clear()
            self.root.clipboard_append(self.config_file)
            messagebox.showinfo("Copied", "Path copied to clipboard!", parent=dialog)

        tk.Button(
            button_frame,
            text="📂 Open Folder",
            command=open_folder,
            bg="#3498db",
            fg="white",
            font=("Arial", 10, "bold"),
            padx=15,
            pady=6,
        ).pack(side="left", padx=5)

        tk.Button(
            button_frame,
            text="📋 Copy Path",
            command=copy_path,
            bg="#9b59b6",
            fg="white",
            font=("Arial", 10, "bold"),
            padx=15,
            pady=6,
        ).pack(side="left", padx=5)

        tk.Button(
            button_frame,
            text="❌ Close",
            command=dialog.destroy,
            bg="#95a5a6",
            fg="white",
            font=("Arial", 10, "bold"),
            padx=15,
            pady=6,
        ).pack(side="left", padx=5)

    def update_jobs_list(self):

        # ป้องกันเรียกก่อนสร้าง UI
        if not hasattr(self, "jobs_container"):
            return

        # Clear current jobs display
        for widget in self.jobs_container.winfo_children():
            widget.destroy()

        current_profile = self.profile_combo.get()

        filtered_jobs = [
            job for job in self.saved_jobs if job.get("profile", current_profile) == current_profile
        ]

        # Forget ticks of jobs that were deleted
        existing_ids = {id(job) for job in self.saved_jobs}
        self._checked_job_ids &= existing_ids

        if not filtered_jobs:
            tk.Label(
                self.jobs_container,
                text="ยังไม่มี Job ของ Profile นี้\nเขียน SQL แล้วกด “＋” หรือ “Save as Job”",
                bg=UI["card"],
                fg=UI["muted"],
                font=UI_FONT_SM,
                justify="center",
            ).pack(fill=tk.X, pady=24)

        SELECTED_BG = "#EFF6FF"
        SELECTED_BORDER = "#BFDBFE"

        def _small_btn(parent, text, command, kind, bg):
            kind = {"run": "soft", "edit": "secondary", "delete": "danger"}[kind]
            return ui_rbutton(parent, text, command, kind=kind, size="icon")

        def _tint(frame, checked):
            """Selected rows get a light blue background (display only)."""
            bg = SELECTED_BG if checked else UI["card"]
            ui_round_frame_set(frame, bg, SELECTED_BORDER if checked else UI["border"])
            stack = [frame]
            while stack:
                w = stack.pop()
                if getattr(w, "_keep_bg", False):
                    continue
                try:
                    w.config(bg=bg)
                    if w.winfo_class() == "Checkbutton":
                        w.config(activebackground=bg, selectcolor=bg)
                except tk.TclError:
                    pass
                stack.extend(w.winfo_children())

        for idx, job in enumerate(filtered_jobs, 1):

            real_idx = self.saved_jobs.index(job)
            is_checked = id(job) in self._checked_job_ids
            row_bg = SELECTED_BG if is_checked else UI["card"]

            _row_outer, job_frame = ui_round_frame(
                self.jobs_container, fill=row_bg,
                border=SELECTED_BORDER if is_checked else UI["border"], radius=8, pad=2,
            )
            _row_outer.pack(fill=tk.X, padx=(0, 4), pady=(8 if idx == 1 else 0, 6))

            job_name = job.get("name", f"Job {idx}")

            check_var = tk.BooleanVar(value=is_checked)
            tk.Checkbutton(
                job_frame,
                variable=check_var,
                command=lambda j=job, v=check_var, f=job_frame: (
                    self.toggle_job_checked(j, v.get()),
                    _tint(f, v.get()),
                ),
                bg=row_bg,
                activebackground=row_bg,
                selectcolor="#FFFFFF",
                bd=0,
                highlightthickness=0,
                cursor="hand2",
            )
            _row_cb = job_frame.winfo_children()[-1]
            _row_cb.pack(side=tk.LEFT, anchor="n", padx=(8, 2), pady=(8, 0))
            ui_round_check(_row_cb)

            # Run / Edit / Delete (right)
            actions = tk.Frame(job_frame, bg=row_bg)
            actions.pack(side=tk.RIGHT, anchor="n", padx=(4, 8), pady=(8, 0))
            for text, command, kind in (
                ("▶", lambda j=job: self.run_job(j), "run"),
                ("✎", lambda i=real_idx: self.edit_job(i), "edit"),
                ("🗑", lambda i=real_idx, n=job_name: self.delete_job(i, n), "delete"),
            ):
                b = _small_btn(actions, text, command, kind, row_bg)
                b._keep_bg = True
                b.pack(side=tk.LEFT, padx=(3, 0))

            text_box = tk.Frame(job_frame, bg=row_bg)
            text_box.pack(side=tk.LEFT, fill=tk.X, expand=True, pady=(6, 7))
            name_row = tk.Frame(text_box, bg=row_bg)
            name_row.pack(fill=tk.X)
            num_label = tk.Label(
                name_row, text=f"{idx:02d}", bg=row_bg, fg=UI["subtle"], font=("Consolas", 9)
            )
            num_label.pack(side=tk.LEFT, padx=(0, 6))
            # width=1: the label never asks for more room than the sidebar gives;
            # the text is fitted (cut with …) to the real width below.
            name_label = tk.Label(
                name_row, text=job_name, width=1, bg=row_bg, fg=UI["text"], font=UI_FONT_SEMI,
                anchor="w",
            )
            name_label.pack(side=tk.LEFT, fill=tk.X, expand=True)
            ui_tooltip(name_label, job_name)
            query_preview = " ".join(str(job.get("query", "")).split())
            sql_label = None
            if query_preview:
                sql_label = tk.Label(
                    text_box,
                    text=query_preview,
                    width=1,
                    bg=row_bg,
                    fg=UI["muted"],
                    font=("Consolas", 8),
                    anchor="w",
                )
                sql_label.pack(fill=tk.X)
                full_sql = str(job.get("query", "")).strip()
                ui_tooltip(sql_label, full_sql if len(full_sql) <= 600 else full_sql[:600] + "…")

            def _fit(event, name=job_name, nl=name_label, num=num_label, sl=sql_label, sq=query_preview):
                ui_fit_text(nl, name, event.width - num.winfo_reqwidth() - 8)
                if sl is not None:
                    ui_fit_text(sl, sq, event.width - 2)

            text_box.bind("<Configure>", _fit)

        self._refresh_job_selection_ui()

    def _current_profile_jobs(self):
        current_profile = self.profile_combo.get()
        return [
            job for job in self.saved_jobs if job.get("profile", current_profile) == current_profile
        ]

    def get_jobs_to_run(self):
        """Checked jobs of the current profile, or all of them if none checked."""
        profile_jobs = self._current_profile_jobs()
        checked = [job for job in profile_jobs if id(job) in self._checked_job_ids]
        return checked or profile_jobs

    def toggle_job_checked(self, job, checked):
        if checked:
            self._checked_job_ids.add(id(job))
        else:
            self._checked_job_ids.discard(id(job))
        self._refresh_job_selection_ui()

    def toggle_select_all_jobs(self):
        profile_ids = {id(job) for job in self._current_profile_jobs()}
        if self.select_all_jobs_var.get():
            self._checked_job_ids |= profile_ids
        else:
            self._checked_job_ids -= profile_ids
        self.update_jobs_list()

    def _refresh_job_selection_ui(self):
        if not hasattr(self, "selected_jobs_label"):
            return
        profile_jobs = self._current_profile_jobs()
        checked_count = sum(id(job) in self._checked_job_ids for job in profile_jobs)
        self.select_all_jobs_var.set(bool(profile_jobs) and checked_count == len(profile_jobs))
        if checked_count:
            self.selected_jobs_label.config(text=f"{checked_count} / {len(profile_jobs)} selected")
            self.run_all_btn.config(text=f"▶  Run selected ({checked_count})")
            delete_text = (
                "🗑  Delete all"
                if checked_count == len(profile_jobs)
                else f"🗑  Delete ({checked_count})"
            )
            self.delete_selected_btn.config(text=delete_text)
            if not self.delete_selected_btn.winfo_ismapped():
                self.delete_selected_btn.pack(side="right", padx=5)
        else:
            self.selected_jobs_label.config(text="")
            self.run_all_btn.config(text="▶  Run all")
            self.delete_selected_btn.pack_forget()

    def delete_selected_jobs(self):
        """Delete every ticked job of the current profile after confirmation."""
        selected = [job for job in self._current_profile_jobs() if id(job) in self._checked_job_ids]
        if not selected:
            return

        names = "\n".join(f"• {job.get('name', '')}" for job in selected[:10])
        if len(selected) > 10:
            names += f"\n... and {len(selected) - 10} more"
        if not messagebox.askyesno(
            "Confirm Delete",
            f"Delete {len(selected)} selected job(s)?\n\n{names}\n\nThis cannot be undone.",
        ):
            return

        selected_ids = {id(job) for job in selected}
        self.saved_jobs = [job for job in self.saved_jobs if id(job) not in selected_ids]
        self._checked_job_ids -= selected_ids
        self.save_jobs()
        self.update_jobs_list()

        self.results_text.delete("1.0", tk.END)
        self.results_text.insert(tk.END, f"🗑️ Deleted {len(selected)} job(s)\n")
        self.results_text.insert(tk.END, f"📊 Remaining: {len(self.saved_jobs)} jobs\n")
        self.results_text.see(tk.END)

    def run_single_job(self, job):
        """Run one saved job using the shared Results format."""
        self.run_job(job)

    def load_job_to_editor(self, job):
        """Load job to SQL editor - CLEAN output"""
        self.sql_context.delete(1.0, tk.END)
        self.sql_context.insert(1.0, job["query"])
        self._apply_job_excel_state(job)

        self.results_text.delete("1.0", tk.END)
        self.results_text.insert(tk.END, f"📝 Loaded: {job['name']}\n")
        self.results_text.insert(tk.END, f"📊 Database: {job.get('database', 'N/A')}\n")
        self.results_text.see(tk.END)

    def edit_job(self, job_idx):
        """Edit job details"""

        if job_idx >= len(self.saved_jobs):
            return

        job = self.saved_jobs[job_idx]

        dialog = tk.Toplevel(self.root)

        dialog.title("✏️ Edit Job")
        dialog.geometry("700x610")
        dialog.configure(bg="#f0f0f0")
        dialog.transient(self.root)
        dialog.grab_set()

        x = (self.root.winfo_screenwidth() - 700) // 2
        y = (self.root.winfo_screenheight() - 550) // 2
        dialog.geometry(f"700x610+{x}+{y}")

        content = tk.Frame(dialog, bg="#ffffff", relief="solid", bd=1)
        content.pack(fill="both", expand=True, padx=15, pady=15)

        tk.Label(
            content, text="✏️ Edit Job", font=("Arial", 14, "bold"), bg="#ffffff", fg="#2c3e50"
        ).pack(pady=(10, 20))

        # Job Name
        tk.Label(content, text="Job Name:", font=("Arial", 10, "bold"), bg="#ffffff").pack(
            anchor="w", padx=10, pady=(0, 5)
        )

        name_entry = tk.Entry(content, font=("Arial", 10), width=60)

        name_entry.pack(padx=10, pady=(0, 15))

        name_entry.insert(0, job["name"])

        # SQL Label
        tk.Label(content, text="SQL Query:", font=("Arial", 10, "bold"), bg="#ffffff").pack(
            anchor="w", padx=10, pady=(0, 5)
        )

        # SQL Editor Frame
        query_frame = tk.Frame(content, bg="#ffffff")

        query_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        query_scroll = tk.Scrollbar(query_frame)

        query_scroll.pack(side="right", fill="y")

        query_text = tk.Text(
            query_frame, height=12, font=("Courier", 9), yscrollcommand=query_scroll.set
        )

        query_text.pack(side="left", fill="both", expand=True)

        query_scroll.config(command=query_text.yview)

        query_text.insert("1.0", job["query"])

        # ===================================================
        # Excel Parameter Tools
        # ===================================================

        tool_frame = ttk.LabelFrame(content, text="Excel Parameter Tools", padding=8)

        tool_frame.pack(fill="x", padx=10, pady=(0, 10))

        excel_button_frame = ttk.Frame(tool_frame)
        excel_button_frame.pack(fill="x")
        job_template, job_values, job_rendered = self._excel_state_from_job(job)
        edit_excel_state = {
            "template": job_template,
            "values": job_values,
            "rendered": job_rendered,
        }

        def sync_edit_parameter_state():
            current_query = query_text.get("1.0", tk.END).rstrip("\n")
            if edit_excel_state["rendered"] == current_query:
                return
            if current_query != edit_excel_state["template"]:
                edit_excel_state["template"] = current_query
                edit_excel_state["values"].clear()
                edit_excel_state["rendered"] = None

        def load_excel_for_edit():

            backup_context = self.sql_context
            backup_root = self.root
            backup_template = self.sql_template
            backup_values = dict(self._excel_parameter_values)
            backup_rendered = self._excel_parameterized_sql

            try:

                self.sql_context = query_text
                self.root = dialog
                sync_edit_parameter_state()
                self.sql_template = edit_excel_state["template"]
                self._excel_parameter_values = edit_excel_state["values"]
                self._excel_parameterized_sql = edit_excel_state["rendered"]
                # wait=True: block until the Excel dialog closes, so the values
                # are written into this Edit dialog (not the main SQL editor)
                self.load_excel_template_dialog(wait=True)
                edit_excel_state["template"] = self.sql_template
                edit_excel_state["values"] = dict(self._excel_parameter_values)
                edit_excel_state["rendered"] = self._excel_parameterized_sql

            finally:

                self.sql_context = backup_context
                self.root = backup_root
                self.sql_template = backup_template
                self._excel_parameter_values = backup_values
                self._excel_parameterized_sql = backup_rendered
                if dialog.winfo_exists():
                    dialog.grab_set()
                    dialog.focus_force()

        def reset_parameter_for_edit():

            backup_context = self.sql_context
            backup_root = self.root
            backup_template = self.sql_template
            backup_values = dict(self._excel_parameter_values)
            backup_rendered = self._excel_parameterized_sql

            try:

                self.sql_context = query_text
                self.root = dialog
                sync_edit_parameter_state()
                self.sql_template = edit_excel_state["template"]
                self._excel_parameter_values = edit_excel_state["values"]
                self._excel_parameterized_sql = edit_excel_state["rendered"]
                self.show_reset_parameter_dialog(close_after_selected=True, wait=True)
                edit_excel_state["template"] = self.sql_template
                edit_excel_state["values"] = dict(self._excel_parameter_values)
                edit_excel_state["rendered"] = self._excel_parameterized_sql

            finally:

                self.sql_context = backup_context
                self.root = backup_root
                self.sql_template = backup_template
                self._excel_parameter_values = backup_values
                self._excel_parameterized_sql = backup_rendered
                if dialog.winfo_exists():
                    dialog.grab_set()
                    dialog.focus_force()

        ttk.Button(excel_button_frame, text="📗 Load Excel", command=load_excel_for_edit).pack(
            side="left", padx=(0, 6)
        )
        ttk.Button(
            excel_button_frame, text="↩ Reset SQL Template", command=reset_parameter_for_edit
        ).pack(side="left")

        def save_changes():
            new_name = name_entry.get().strip()

            new_query = query_text.get("1.0", tk.END).strip()

            if not new_name:
                messagebox.showwarning("Warning", "Job name cannot be empty", parent=dialog)
                return

            if not new_query:
                messagebox.showwarning("Warning", "SQL Query cannot be empty", parent=dialog)
                return

            saved_job = self.saved_jobs[job_idx]
            saved_job["name"] = new_name
            saved_job["query"] = new_query
            saved_job.pop("sql_template", None)
            saved_job.pop("excel_parameters", None)
            saved_job.update(
                self._excel_state_for_job(
                    new_query,
                    edit_excel_state["template"],
                    edit_excel_state["values"],
                    edit_excel_state["rendered"],
                )
            )

            self.save_jobs()
            self.update_jobs_list()

            self.results_text.delete("1.0", tk.END)

            self.results_text.insert(tk.END, f"✅ Job updated: {new_name}\n")

            self.results_text.see(tk.END)

            messagebox.showinfo("Success", "Job updated successfully!", parent=dialog)

            dialog.destroy()

        action_frame = ttk.Frame(content)
        action_frame.pack(fill="x", padx=10, pady=(0, 10))
        ttk.Button(action_frame, text="Save Changes", command=save_changes).pack(
            side="right", padx=(6, 0)
        )
        ttk.Button(action_frame, text="Cancel", command=dialog.destroy).pack(side="right")

    def delete_job(self, job_idx, job_name):
        """Delete job with confirmation"""
        result = messagebox.askyesno(
            "Confirm Delete", f"Delete job '{job_name}'?\n\nThis cannot be undone."
        )
        if result:
            self.saved_jobs.pop(job_idx)
            self.save_jobs()
            self.update_jobs_list()

            self.results_text.delete("1.0", tk.END)
            self.results_text.insert(tk.END, f"🗑️ Deleted: {job_name}\n")
            self.results_text.insert(tk.END, f"📊 Remaining: {len(self.saved_jobs)} jobs\n")
            self.results_text.see(tk.END)

    # ===================================================
    # Script Groups — named sets of scripts per profile, kept apart from
    # the Saved Jobs list (stored in script_groups.json). A script inside a
    # group is its own copy: the same SQL in two groups is two scripts.
    # ===================================================

    def _script_groups_path(self):
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), "script_groups.json")

    def load_script_groups(self):
        path = self._script_groups_path()
        if not os.path.exists(path):
            return []
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            groups = data.get("groups", []) if isinstance(data, dict) else data
            return [g for g in groups if isinstance(g, dict) and g.get("name")]
        except Exception as e:
            messagebox.showerror("Script Groups", f"Cannot read script_groups.json:\n{e}")
            return []

    def save_script_groups(self):
        path = self._script_groups_path()
        clean = []
        for group in self.script_groups:
            scripts = [
                {k: v for k, v in script.items() if not k.startswith("_") and k != "run_index"}
                for script in group.get("scripts", [])
            ]
            clean.append(dict(group, scripts=scripts))
        try:
            # Keep the previous version as script_groups_backup.json, then write
            # to a temp file and swap it in, so a crash never leaves a broken file
            if os.path.exists(path):
                import shutil

                shutil.copy2(path, os.path.splitext(path)[0] + "_backup.json")
            tmp_path = path + ".tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump({"version": 1, "groups": clean}, f, indent=2, ensure_ascii=False)
            os.replace(tmp_path, path)
        except Exception as e:
            messagebox.showerror("Script Groups", f"Cannot save script_groups.json:\n{e}")

    def _ask_group_text(self, parent, title, label, initial=""):
        """Small modal prompt; returns the stripped text or None."""
        dialog = tk.Toplevel(parent)
        dialog.title(title)
        dialog.configure(bg="#f0f0f0")
        dialog.transient(parent)
        dialog.resizable(False, False)
        result = {"value": None}

        content = tk.Frame(dialog, bg="#ffffff", relief="solid", bd=1)
        content.pack(fill="both", expand=True, padx=12, pady=12)
        tk.Label(content, text=label, font=("Arial", 10), bg="#ffffff").pack(
            anchor="w", padx=10, pady=(10, 5)
        )
        entry = tk.Entry(content, font=("Arial", 10), width=50)
        entry.pack(padx=10, pady=(0, 10))
        entry.insert(0, initial)
        entry.select_range(0, tk.END)
        entry.focus_set()

        def ok(_event=None):
            value = entry.get().strip()
            if not value:
                messagebox.showwarning(title, "Please enter a name", parent=dialog)
                return
            result["value"] = value
            dialog.destroy()

        buttons = tk.Frame(content, bg="#ffffff")
        buttons.pack(pady=(0, 10))
        tk.Button(buttons, text="OK", width=10, bg="#27ae60", fg="white", command=ok).pack(
            side="left", padx=4
        )
        tk.Button(buttons, text="Cancel", width=10, bg="#95a5a6", fg="white", command=dialog.destroy).pack(
            side="left", padx=4
        )
        entry.bind("<Return>", ok)
        dialog.bind("<Escape>", lambda _e: dialog.destroy())

        dialog.update_idletasks()
        x = parent.winfo_rootx() + (parent.winfo_width() - dialog.winfo_width()) // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - dialog.winfo_height()) // 3
        dialog.geometry(f"+{max(x, 0)}+{max(y, 0)}")
        dialog.grab_set()
        dialog.wait_window()
        return result["value"]

    def _edit_group_script_dialog(self, parent, title, script=None):
        """Name + SQL editor (with Excel Parameter Tools) for a group script.

        script=None → new script, starting from the default SQL template.
        Returns {"name", "query", ...Excel parameter state} or None if cancelled.
        """
        script = script or {"name": "", "query": self.DEFAULT_SQL_QUERY}

        dialog = tk.Toplevel(parent)
        dialog.title(title)
        dialog.configure(bg="#f0f0f0")
        dialog.transient(parent)
        dialog.geometry("760x620")
        dialog.minsize(560, 460)
        result = {"value": None}

        content = tk.Frame(dialog, bg="#ffffff", relief="solid", bd=1)
        content.pack(fill="both", expand=True, padx=12, pady=12)

        tk.Label(content, text="Script Name:", font=("Arial", 10, "bold"), bg="#ffffff").pack(
            anchor="w", padx=10, pady=(10, 5)
        )
        name_entry = tk.Entry(content, font=("Arial", 10))
        name_entry.pack(fill="x", padx=10, pady=(0, 10))
        name_entry.insert(0, script.get("name", ""))

        tk.Label(content, text="SQL Query:", font=("Arial", 10, "bold"), bg="#ffffff").pack(
            anchor="w", padx=10, pady=(0, 5)
        )
        buttons = tk.Frame(content, bg="#ffffff")
        buttons.pack(side="bottom", pady=10)

        # Excel Parameter Tools — same behaviour as in Edit Job
        tool_frame = ttk.LabelFrame(content, text="Excel Parameter Tools", padding=8)
        tool_frame.pack(side="bottom", fill="x", padx=10, pady=(0, 5))
        excel_button_frame = ttk.Frame(tool_frame)
        excel_button_frame.pack(fill="x")

        query_text = scrolledtext.ScrolledText(content, height=14, font=("Courier", 9), undo=True)
        query_text.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        query_text.insert("1.0", script.get("query", ""))
        query_text.edit_reset()
        name_entry.focus_set()

        tmpl, vals, rendered = self._excel_state_from_job(script)
        excel_state = {"template": tmpl, "values": dict(vals), "rendered": rendered}

        def sync_parameter_state():
            current_query = query_text.get("1.0", tk.END).rstrip("\n")
            if excel_state["rendered"] == current_query:
                return
            if current_query != excel_state["template"]:
                excel_state["template"] = current_query
                excel_state["values"].clear()
                excel_state["rendered"] = None

        def run_excel_tool(tool):
            """Run a main-window Excel tool against this dialog's SQL box."""
            backup_context = self.sql_context
            backup_root = self.root
            backup_template = self.sql_template
            backup_values = dict(self._excel_parameter_values)
            backup_rendered = self._excel_parameterized_sql
            try:
                self.sql_context = query_text
                self.root = dialog
                sync_parameter_state()
                self.sql_template = excel_state["template"]
                self._excel_parameter_values = excel_state["values"]
                self._excel_parameterized_sql = excel_state["rendered"]
                tool()
                excel_state["template"] = self.sql_template
                excel_state["values"] = dict(self._excel_parameter_values)
                excel_state["rendered"] = self._excel_parameterized_sql
            finally:
                self.sql_context = backup_context
                self.root = backup_root
                self.sql_template = backup_template
                self._excel_parameter_values = backup_values
                self._excel_parameterized_sql = backup_rendered
                if dialog.winfo_exists():
                    dialog.grab_set()
                    dialog.focus_force()

        ttk.Button(
            excel_button_frame,
            text="📗 Load Excel",
            command=lambda: run_excel_tool(lambda: self.load_excel_template_dialog(wait=True)),
        ).pack(side="left", padx=(0, 6))
        ttk.Button(
            excel_button_frame,
            text="↩ Reset SQL Template",
            command=lambda: run_excel_tool(
                lambda: self.show_reset_parameter_dialog(close_after_selected=True, wait=True)
            ),
        ).pack(side="left")

        def save():
            new_name = name_entry.get().strip()
            new_query = query_text.get("1.0", tk.END).strip()
            if not new_name:
                messagebox.showwarning(title, "Script name cannot be empty", parent=dialog)
                return
            if not new_query:
                messagebox.showwarning(title, "SQL Query cannot be empty", parent=dialog)
                return
            value = {"name": new_name, "query": new_query}
            value.update(
                self._excel_state_for_job(
                    new_query,
                    excel_state["template"],
                    excel_state["values"],
                    excel_state["rendered"],
                )
            )
            result["value"] = value
            dialog.destroy()

        tk.Button(buttons, text="Save", width=12, bg="#27ae60", fg="white", command=save).pack(
            side="left", padx=5
        )
        tk.Button(buttons, text="Cancel", width=12, bg="#95a5a6", fg="white", command=dialog.destroy).pack(
            side="left", padx=5
        )
        dialog.bind("<Escape>", lambda _e: dialog.destroy())

        dialog.update_idletasks()
        x = parent.winfo_rootx() + (parent.winfo_width() - 760) // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - 620) // 3
        dialog.geometry(f"+{max(x, 0)}+{max(y, 0)}")
        dialog.grab_set()
        dialog.wait_window()
        return result["value"]

    def _pick_jobs_dialog(self, parent, jobs):
        """Multi-select list of saved jobs; returns the chosen jobs (maybe empty)."""
        dialog = tk.Toplevel(parent)
        dialog.title("Add from Saved Jobs")
        dialog.configure(bg="#f0f0f0")
        dialog.transient(parent)
        dialog.geometry("560x460")
        chosen = []

        content = tk.Frame(dialog, bg="#ffffff", relief="solid", bd=1)
        content.pack(fill="both", expand=True, padx=12, pady=12)
        tk.Label(
            content,
            text="Select jobs to copy into the group (Ctrl/Shift for several):",
            font=("Arial", 10),
            bg="#ffffff",
        ).pack(anchor="w", padx=10, pady=(10, 5))

        buttons = tk.Frame(content, bg="#ffffff")
        buttons.pack(side="bottom", pady=10)
        list_frame = tk.Frame(content, bg="#ffffff")
        list_frame.pack(fill="both", expand=True, padx=10, pady=(0, 5))
        scroll = tk.Scrollbar(list_frame)
        scroll.pack(side="right", fill="y")
        listbox = tk.Listbox(
            list_frame, selectmode=tk.EXTENDED, font=("Arial", 10), yscrollcommand=scroll.set
        )
        listbox.pack(side="left", fill="both", expand=True)
        scroll.config(command=listbox.yview)
        for number, job in enumerate(jobs, 1):
            listbox.insert(tk.END, f"{number}. {job.get('name', '')}")

        def add():
            chosen.extend(jobs[i] for i in listbox.curselection())
            if not chosen:
                messagebox.showwarning("Add from Saved Jobs", "Please select a job", parent=dialog)
                return
            dialog.destroy()

        tk.Button(buttons, text="Add to Group", width=14, bg="#27ae60", fg="white", command=add).pack(
            side="left", padx=5
        )
        tk.Button(buttons, text="Cancel", width=12, bg="#95a5a6", fg="white", command=dialog.destroy).pack(
            side="left", padx=5
        )
        listbox.bind("<Double-Button-1>", lambda _e: add())

        dialog.update_idletasks()
        x = parent.winfo_rootx() + (parent.winfo_width() - 560) // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - 460) // 3
        dialog.geometry(f"+{max(x, 0)}+{max(y, 0)}")
        dialog.grab_set()
        dialog.wait_window()
        return chosen

    def show_script_groups_dialog(self):
        """Manage Script Groups of the current profile; run / export a whole group."""
        if not hasattr(self, "script_groups"):
            self.script_groups = self.load_script_groups()

        existing = getattr(self, "_script_groups_window", None)
        if existing is not None and existing.winfo_exists():
            existing.deiconify()
            existing.lift()
            existing.focus_force()
            return

        # Owned by the main window like the result popups: it stays above the
        # main window (which comes forward when a result popup opens), while
        # result popups of a group run can still be raised above it.
        dialog = tk.Toplevel(self.root)
        dialog.transient(self.root)
        self._script_groups_window = dialog
        dialog.title("Script Groups")
        dialog.configure(bg=UI["card"])
        dialog.geometry("1060x660")
        dialog.minsize(860, 500)
        x = self.root.winfo_rootx() + max((self.root.winfo_width() - 1060) // 2, 0)
        y = self.root.winfo_rooty() + max((self.root.winfo_height() - 660) // 3, 0)
        dialog.geometry(f"+{x}+{y}")

        state = {"profile": None, "groups": []}
        CARD, SURF = UI["card"], UI["surface"]

        def _panel(parent):
            return tk.Frame(parent, bg=SURF, highlightthickness=1,
                            highlightbackground=UI["border"], highlightcolor=UI["border"])

        def _listbox(parent, **kw):
            return tk.Listbox(
                parent, font=UI_FONT, exportselection=False, activestyle="none", bd=0,
                highlightthickness=1, highlightbackground=UI["border"], highlightcolor=UI["primary"],
                selectbackground="#DBEAFE", selectforeground=UI["text"], fg=UI["text"], bg=CARD, **kw,
            )

        # Header: title + subtitle (profile), Import / Export on the right
        header = tk.Frame(dialog, bg=CARD)
        header.pack(fill="x", padx=20, pady=(16, 10))
        titles = tk.Frame(header, bg=CARD)
        titles.pack(side="left")
        tk.Label(titles, text="Script Groups", font=("Segoe UI Semibold", 15), bg=CARD,
                 fg=UI["text"]).pack(anchor="w")
        profile_label = tk.Label(titles, text="", font=UI_FONT_SM, bg=CARD, fg=UI["muted"])
        profile_label.pack(anchor="w")
        header_buttons = tk.Frame(header, bg=CARD)
        header_buttons.pack(side="right")

        # Run bar across the bottom of the window
        run_wrap = tk.Frame(dialog, bg=SURF)
        run_wrap.pack(side="bottom", fill="x")
        tk.Frame(run_wrap, bg=UI["border"], height=1).pack(fill="x")
        run_bar = tk.Frame(run_wrap, bg=SURF)
        run_bar.pack(fill="x", padx=20, pady=12)

        body = tk.Frame(dialog, bg=CARD)
        body.pack(fill="both", expand=True, padx=20, pady=(0, 14))
        body.columnconfigure(0, weight=1, minsize=270)
        body.columnconfigure(1, weight=3)
        body.rowconfigure(0, weight=1)

        # ---- Left: groups ------------------------------------------------
        _left_outer, left = ui_round_frame(body, fill=SURF, border=UI["border"], radius=10, pad=3)
        _left_outer.grid(row=0, column=0, sticky="nsew", padx=(0, 16))
        left_head = tk.Frame(left, bg=SURF)
        left_head.pack(fill="x", padx=12, pady=(12, 8))
        tk.Label(left_head, text="กลุ่ม", font=("Segoe UI Semibold", 11), bg=SURF,
                 fg=UI["text"]).pack(side="left")
        group_buttons = tk.Frame(left, bg=SURF)
        group_buttons.pack(side="bottom", fill="x", padx=12, pady=12)
        groups_box = _listbox(left)
        groups_box.pack(fill="both", expand=True, padx=12)

        # ---- Right: scripts of the selected group --------------------------
        right = tk.Frame(body, bg=CARD)
        right.grid(row=0, column=1, sticky="nsew")
        right_head = tk.Frame(right, bg=CARD)
        right_head.pack(fill="x", pady=(0, 8))
        scripts_title = tk.Label(right_head, text="Scripts", font=("Segoe UI Semibold", 11),
                                 bg=CARD, fg=UI["text"])
        scripts_title.pack(side="left")
        script_buttons = tk.Frame(right_head, bg=CARD)
        script_buttons.pack(side="right")

        list_row = tk.Frame(right, bg=CARD)
        list_row.pack(fill="both", expand=True)
        order_buttons = tk.Frame(list_row, bg=CARD)
        order_buttons.pack(side="right", fill="y", padx=(8, 0))
        scripts_box = _listbox(list_row, height=9)
        scripts_box.pack(side="left", fill="both", expand=True)

        tk.Label(right, text="SQL preview", font=UI_FONT_LABEL, bg=CARD, fg=UI["muted"]).pack(
            anchor="w", pady=(10, 4)
        )
        preview = scrolledtext.ScrolledText(
            right, height=7, font=("Consolas", 10), wrap=tk.NONE, bg=SURF, fg=UI["text"], bd=0,
            relief="flat", highlightthickness=1, highlightbackground=UI["border"], padx=10, pady=8,
        )
        preview.pack(fill="both", expand=False)
        preview.config(state="disabled")

        # ---- helpers -----------------------------------------------------
        def current_group():
            sel = groups_box.curselection()
            if not sel or sel[0] >= len(state["groups"]):
                return None
            return state["groups"][sel[0]]

        def current_script_index():
            sel = scripts_box.curselection()
            return sel[0] if sel else None

        def show_preview(text_value):
            preview.config(state="normal")
            preview.delete("1.0", tk.END)
            preview.insert("1.0", text_value)
            preview.config(state="disabled")

        def refresh_groups(select_name=None):
            profile = self.profile_combo.get()
            state["profile"] = profile
            profile_label.config(text=f"เก็บ Script เป็นชุด แยกจาก Saved Jobs · Profile: {profile or '-'}")
            previous = current_group()
            keep = select_name or (previous["name"] if previous else None)
            state["groups"] = [g for g in self.script_groups if g.get("profile") == profile]
            groups_box.delete(0, tk.END)
            for g in state["groups"]:
                groups_box.insert(tk.END, f"{g['name']}  ({len(g.get('scripts', []))})")
            index = 0
            for i, g in enumerate(state["groups"]):
                if g["name"] == keep:
                    index = i
            if state["groups"]:
                groups_box.selection_set(index)
                groups_box.see(index)
            refresh_scripts()

        def refresh_scripts(select_index=None):
            group = current_group()
            scripts_box.delete(0, tk.END)
            if group is None:
                scripts_title.config(text="Scripts")
                show_preview(
                    "No group yet — click '+ New Group' to create one."
                    if not state["groups"]
                    else ""
                )
                update_buttons()
                return
            scripts = group.setdefault("scripts", [])
            scripts_title.config(text=f"{group['name']}   ·   {len(scripts)} scripts · รันตามลำดับ")
            for number, script in enumerate(scripts, 1):
                scripts_box.insert(tk.END, f"{number}. {script.get('name', '')}")
            if scripts:
                index = 0 if select_index is None else max(0, min(select_index, len(scripts) - 1))
                scripts_box.selection_set(index)
                scripts_box.see(index)
                show_preview(scripts[index].get("query", ""))
            else:
                show_preview("This group has no scripts yet — add one with the buttons below.")
            update_buttons()

        def set_enabled(btn, enabled):
            btn.config(state="normal" if enabled else "disabled")

        def update_buttons():
            has_group = current_group() is not None
            has_scripts = has_group and bool(current_group().get("scripts"))
            has_script = has_scripts and current_script_index() is not None
            for btn in (rename_btn, delete_group_btn, add_editor_btn, add_jobs_btn):
                set_enabled(btn, has_group)
            for btn in (edit_btn, delete_script_btn, up_btn, down_btn):
                set_enabled(btn, has_script)
            for btn in (run_btn, export_btn):
                set_enabled(btn, has_scripts)

        def on_script_select(_event=None):
            group = current_group()
            index = current_script_index()
            if group is not None and index is not None:
                show_preview(group["scripts"][index].get("query", ""))
            update_buttons()

        def name_taken(name, ignore=None):
            return any(
                g is not ignore and g["name"].lower() == name.lower() for g in state["groups"]
            )

        # ---- group actions -------------------------------------------------
        def new_group():
            if not self.profile_combo.get():
                messagebox.showwarning("Script Groups", "Please select a profile first", parent=dialog)
                return
            name = self._ask_group_text(dialog, "New Group", "Group name:")
            if not name:
                return
            if name_taken(name):
                messagebox.showwarning("Script Groups", f"Group '{name}' already exists", parent=dialog)
                return
            self.script_groups.append(
                {
                    "name": name,
                    "profile": self.profile_combo.get(),
                    "created": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "scripts": [],
                }
            )
            self.save_script_groups()
            refresh_groups(select_name=name)

        def rename_group():
            group = current_group()
            if group is None:
                return
            name = self._ask_group_text(dialog, "Rename Group", "New group name:", group["name"])
            if not name or name == group["name"]:
                return
            if name_taken(name, ignore=group):
                messagebox.showwarning("Script Groups", f"Group '{name}' already exists", parent=dialog)
                return
            group["name"] = name
            self.save_script_groups()
            refresh_groups(select_name=name)

        def delete_group():
            group = current_group()
            if group is None:
                return
            count = len(group.get("scripts", []))
            if not messagebox.askyesno(
                "Delete Group",
                f"Delete group '{group['name']}' and its {count} script(s)?\n\n"
                "Saved Jobs are not affected. This cannot be undone.",
                parent=dialog,
            ):
                return
            self.script_groups.remove(group)
            self.save_script_groups()
            refresh_groups()

        # ---- script actions ------------------------------------------------
        def add_sql():
            group = current_group()
            if group is None:
                return
            result = self._edit_group_script_dialog(dialog, f"Add SQL to '{group['name']}'")
            if not result:
                return
            result["created"] = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
            group["scripts"].append(result)
            self.save_script_groups()
            refresh_groups()
            refresh_scripts(select_index=len(group["scripts"]) - 1)

        def add_from_jobs():
            group = current_group()
            if group is None:
                return
            jobs = self._current_profile_jobs()
            if not jobs:
                messagebox.showinfo("Script Groups", "This profile has no saved jobs", parent=dialog)
                return
            chosen = self._pick_jobs_dialog(dialog, jobs)
            if not chosen:
                return
            for job in chosen:
                copy_ = json.loads(json.dumps({k: v for k, v in job.items() if not k.startswith("_")}, default=str))
                copy_.pop("run_index", None)
                copy_.pop("profile", None)
                copy_["created"] = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
                group["scripts"].append(copy_)
            self.save_script_groups()
            refresh_groups()
            refresh_scripts(select_index=len(group["scripts"]) - 1)

        def edit_script(_event=None):
            group = current_group()
            index = current_script_index()
            if group is None or index is None:
                return
            script = group["scripts"][index]
            result = self._edit_group_script_dialog(dialog, "Edit Script", script)
            if not result:
                return
            script.pop("sql_template", None)
            script.pop("excel_parameters", None)
            script.update(result)
            self.save_script_groups()
            refresh_scripts(select_index=index)

        def delete_script():
            group = current_group()
            index = current_script_index()
            if group is None or index is None:
                return
            script = group["scripts"][index]
            if not messagebox.askyesno(
                "Delete Script",
                f"Remove '{script.get('name', '')}' from group '{group['name']}'?",
                parent=dialog,
            ):
                return
            del group["scripts"][index]
            self.save_script_groups()
            refresh_groups()
            refresh_scripts(select_index=index)

        def move_script(step):
            group = current_group()
            index = current_script_index()
            if group is None or index is None:
                return
            target = index + step
            scripts = group["scripts"]
            if 0 <= target < len(scripts):
                scripts[index], scripts[target] = scripts[target], scripts[index]
                self.save_script_groups()
                refresh_scripts(select_index=target)

        def group_jobs(group):
            profile = state["profile"]
            return [dict(script, profile=profile) for script in group.get("scripts", [])]

        def run_group():
            group = current_group()
            if group is None or not group.get("scripts"):
                return
            if not self.engine:
                messagebox.showerror("Error", "Please connect to database first", parent=dialog)
                return
            if getattr(self, "_batch_running", False):
                messagebox.showinfo("Script Groups", "Another run is still in progress", parent=dialog)
                return
            self.run_selected_job(jobs_override=group_jobs(group))

        def export_group():
            group = current_group()
            if group is None or not group.get("scripts"):
                return
            self.export_jobs_to_excel(jobs_override=group_jobs(group), file_prefix=group["name"])

        # ---- backup: export / import -----------------------------------------
        def export_groups():
            groups = state["groups"]
            if not groups:
                messagebox.showinfo("Export Groups", "This profile has no groups to export", parent=dialog)
                return
            selected = current_group()
            scope_all = True
            if selected is not None and len(groups) > 1:
                answer = messagebox.askyesnocancel(
                    "Export Groups",
                    f"Export ALL {len(groups)} groups of profile '{state['profile']}'?\n\n"
                    f"Yes = all groups\nNo = only '{selected['name']}'",
                    parent=dialog,
                )
                if answer is None:
                    return
                scope_all = answer
            chosen = groups if scope_all else [selected]
            stamp = pd.Timestamp.now().strftime("%Y%m%d_%H%M%S")
            label = state["profile"] if scope_all else selected["name"]
            safe = re.sub(r'[\\/:*?"<>|]', "_", str(label)).strip() or "groups"
            file_path = filedialog.asksaveasfilename(
                parent=dialog,
                title="Export Script Groups",
                defaultextension=".json",
                filetypes=[("JSON files", "*.json")],
                initialfile=f"script_groups_{safe}_{stamp}.json",
            )
            if not file_path:
                return
            data = {
                "type": "script_groups",
                "version": 1,
                "exported": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"),
                "profile": state["profile"],
                "groups": [
                    {
                        "name": g["name"],
                        "created": g.get("created"),
                        "scripts": [
                            {k: v for k, v in sc.items() if not k.startswith("_") and k != "run_index"}
                            for sc in g.get("scripts", [])
                        ],
                    }
                    for g in chosen
                ],
            }
            try:
                with open(file_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
            except Exception as e:
                messagebox.showerror("Export Groups", f"Cannot write file:\n{e}", parent=dialog)
                return
            count = sum(len(g["scripts"]) for g in data["groups"])
            self.results_text.insert(
                tk.END, f"📤 Exported {len(chosen)} group(s), {count} script(s) → {file_path}\n"
            )
            self.results_text.see(tk.END)
            messagebox.showinfo(
                "Export Groups",
                f"Exported {len(chosen)} group(s), {count} script(s)\n\n{file_path}",
                parent=dialog,
            )

        def import_groups():
            profile = self.profile_combo.get()
            if not profile:
                messagebox.showwarning("Import Groups", "Please select a profile first", parent=dialog)
                return
            file_path = filedialog.askopenfilename(
                parent=dialog,
                title="Import Script Groups",
                filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            )
            if not file_path:
                return
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                incoming = data.get("groups") if isinstance(data, dict) else data
                if not isinstance(incoming, list):
                    raise ValueError("no 'groups' list in this file")
                incoming = [
                    g for g in incoming
                    if isinstance(g, dict) and g.get("name") and isinstance(g.get("scripts", []), list)
                ]
                for g in incoming:
                    for sc in g.get("scripts", []):
                        if not isinstance(sc, dict) or not sc.get("query"):
                            raise ValueError(f"group '{g['name']}' has a script without SQL")
            except Exception as e:
                messagebox.showerror("Import Groups", f"Not a valid Script Groups file:\n{e}", parent=dialog)
                return
            if not incoming:
                messagebox.showinfo("Import Groups", "No groups found in this file", parent=dialog)
                return

            profile_groups = [g for g in self.script_groups if g.get("profile") == profile]
            existing = {g["name"].lower(): g for g in profile_groups}
            clashes = [g["name"] for g in incoming if g["name"].lower() in existing]
            summary = "\n".join(
                f"• {g['name']}  ({len(g.get('scripts', []))} scripts)"
                + ("  ← already exists" if g["name"] in clashes else "")
                for g in incoming[:15]
            )
            if len(incoming) > 15:
                summary += f"\n... and {len(incoming) - 15} more"
            replace = False
            if clashes:
                answer = messagebox.askyesnocancel(
                    "Import Groups",
                    f"Import {len(incoming)} group(s) into profile '{profile}':\n\n{summary}\n\n"
                    f"{len(clashes)} group name(s) already exist.\n"
                    "Yes = replace them\nNo = keep both (imported copy gets a new name)\n"
                    "Cancel = do not import",
                    parent=dialog,
                )
                if answer is None:
                    return
                replace = answer
            elif not messagebox.askyesno(
                "Import Groups",
                f"Import {len(incoming)} group(s) into profile '{profile}'?\n\n{summary}",
                parent=dialog,
            ):
                return

            now = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
            taken = {g["name"].lower() for g in profile_groups}
            last_name = None
            for g in incoming:
                name = g["name"]
                old = existing.get(name.lower())
                if old is not None and replace:
                    self.script_groups.remove(old)
                elif old is not None:
                    n = 2
                    while f"{name} ({n})".lower() in taken:
                        n += 1
                    name = f"{name} ({n})"
                taken.add(name.lower())
                self.script_groups.append(
                    {
                        "name": name,
                        "profile": profile,
                        "created": g.get("created") or now,
                        "imported": now,
                        "scripts": json.loads(json.dumps(g.get("scripts", []), default=str)),
                    }
                )
                last_name = name
            self.save_script_groups()
            refresh_groups(select_name=last_name)
            self.results_text.insert(
                tk.END, f"📥 Imported {len(incoming)} group(s) from {file_path}\n"
            )
            self.results_text.see(tk.END)

        # ---- buttons -------------------------------------------------------
        KIND = {"#27ae60": "success", "#3498db": "secondary", "#e74c3c": "danger", "#95a5a6": "secondary"}

        def _btn(parent, text, command, color="#95a5a6", size="sm", **pack):
            b = ui_rbutton(parent, text, command, kind=KIND.get(color, "secondary"), size=size)
            b.pack(**pack)
            return b

        _btn(left_head, "＋ New Group", new_group, "#27ae60", side="right")
        _btn(header_buttons, "⇧  Import Groups", import_groups, side="left", padx=(0, 6))
        _btn(header_buttons, "⇩  Export Groups", export_groups, side="left")
        rename_btn = _btn(group_buttons, "✎  Rename", rename_group, side="left", padx=(0, 6))
        delete_group_btn = _btn(group_buttons, "🗑  Delete", delete_group, "#e74c3c", side="left")

        up_btn = _btn(order_buttons, "↑", lambda: move_script(-1), side="top", pady=(0, 4), fill="x")
        down_btn = _btn(order_buttons, "↓", lambda: move_script(1), side="top", pady=(0, 12), fill="x")
        edit_btn = _btn(order_buttons, "✎ Edit", edit_script, side="top", pady=(0, 4), fill="x")
        delete_script_btn = _btn(order_buttons, "🗑 Remove", delete_script, "#e74c3c", side="top", fill="x")

        add_editor_btn = _btn(script_buttons, "＋ Add SQL", add_sql, side="left", padx=(0, 6))
        add_jobs_btn = _btn(script_buttons, "🕘  From Saved Jobs", add_from_jobs, side="left")

        run_btn = _btn(run_bar, "▶  Run Group", run_group, "#27ae60", size="md", side="left", padx=(0, 8))
        export_btn = _btn(run_bar, "⇩  Export Group to Excel", export_group, size="md", side="left")
        stop_group_btn = ui_rbutton(run_bar, "⏹  Stop", self.stop_running_queries, "danger", "md")
        stop_group_btn.pack(side="left", padx=8)
        self._register_stop_button(stop_group_btn)
        self._result_windows_checkbox(run_bar, UI["surface"]).pack(side="right")

        groups_box.bind("<<ListboxSelect>>", lambda _e: refresh_scripts())
        groups_box.bind("<Double-Button-1>", lambda _e: rename_group())
        scripts_box.bind("<<ListboxSelect>>", on_script_select)
        scripts_box.bind("<Double-Button-1>", edit_script)

        # Follow the main window's profile while the window stays open
        def _on_focus(_event=None):
            if state["profile"] != self.profile_combo.get():
                refresh_groups()

        dialog.bind("<FocusIn>", _on_focus, add="+")

        refresh_groups()

    def save_preset_dialog(self):
        """Save current jobs as a preset"""
        current_profile = self.profile_combo.get()

        profile_jobs = [job for job in self.saved_jobs if job.get("profile") == current_profile]

        for index, job in enumerate(profile_jobs, start=1):
            job["run_index"] = index

        if not profile_jobs:
            messagebox.showwarning("Warning", "No jobs to run")
            return

        dialog = tk.Toplevel(self.root)
        dialog.title("💾 Save Preset")
        dialog.geometry("550x320")
        dialog.minsize(550, 320)
        dialog.configure(bg="#f0f0f0")
        dialog.transient(self.root)
        dialog.grab_set()

        x = (self.root.winfo_screenwidth() - 550) // 2
        y = (self.root.winfo_screenheight() - 320) // 2

        dialog.geometry(f"550x320+{x}+{y}")

        content = tk.Frame(dialog, bg="#ffffff", relief="solid", bd=1)
        content.pack(fill="both", expand=True, padx=15, pady=15)

        tk.Label(
            content,
            text="💾 Save Jobs as Preset",
            font=("Arial", 12, "bold"),
            bg="#ffffff",
            fg="#2c3e50",
        ).pack(pady=(10, 15))

        tk.Label(content, text="Preset Name:", font=("Arial", 10), bg="#ffffff").pack(pady=(0, 5))

        name_entry = tk.Entry(content, font=("Arial", 10), width=40)
        name_entry.pack(pady=5)
        name_entry.focus()

        tk.Label(
            content,
            text=f"💡 Will save {len(profile_jobs)} jobs",
            font=("Arial", 9, "italic"),
            bg="#ffffff",
            fg="#7f8c8d",
        ).pack(pady=(10, 0))

        def save():
            preset_name = name_entry.get().strip()
            if not preset_name:
                messagebox.showwarning("Warning", "Please enter preset name", parent=dialog)
                return

            preset_file = os.path.join(
                os.path.dirname(self.jobs_file), f"preset_{preset_name}.json"
            )

            try:
                with open(preset_file, "w", encoding="utf-8") as f:
                    json.dump(
                        {"jobs": profile_jobs, "created": pd.Timestamp.now().isoformat()},
                        f,
                        indent=2,
                        ensure_ascii=False,
                    )

                self.results_text.delete("1.0", tk.END)
                self.results_text.insert(tk.END, f"💾 Preset saved: {preset_name}\n")
                self.results_text.insert(tk.END, f"📊 Jobs: {len(profile_jobs)}\n")
                self.results_text.insert(tk.END, f"📁 Location: {preset_file}\n")
                self.results_text.see(tk.END)

                messagebox.showinfo(
                    "Success",
                    f"Preset '{preset_name}' saved!\n\n{len(profile_jobs)} jobs included",
                    parent=dialog,
                )
                dialog.destroy()
            except Exception as e:
                messagebox.showerror("Error", f"Failed to save preset:\n{str(e)}", parent=dialog)

        button_frame = tk.Frame(content, bg="#ffffff")
        button_frame.pack(side=tk.BOTTOM, pady=(20, 15))

        save_btn = tk.Button(
            button_frame,
            text="💾 Save",
            width=12,
            height=2,
            bg="#27ae60",
            fg="white",
            font=("Arial", 10, "bold"),
            command=save,
        )

        save_btn.pack(side="left", padx=5)

        cancel_btn = tk.Button(
            button_frame,
            text="✖ Cancel",
            width=12,
            height=2,
            bg="#95a5a6",
            fg="white",
            font=("Arial", 10, "bold"),
            command=dialog.destroy,
        )

        cancel_btn.pack(side="left", padx=5)

    def load_preset_dialog(self):
        """Load jobs from a preset"""
        preset_dir = os.path.dirname(self.jobs_file)
        preset_files = [
            f for f in os.listdir(preset_dir) if f.startswith("preset_") and f.endswith(".json")
        ]

        if not preset_files:
            messagebox.showinfo("No Presets", "No saved presets found")
            return

        dialog = tk.Toplevel(self.root)
        dialog.title("📂 Load Preset")
        dialog.geometry("600x450")
        dialog.configure(bg="#f0f0f0")
        dialog.transient(self.root)
        dialog.grab_set()

        x = (self.root.winfo_screenwidth() - 600) // 2
        y = (self.root.winfo_screenheight() - 400) // 2
        dialog.geometry(f"+{x}+{y}")

        content = tk.Frame(dialog, bg="#ffffff", relief="solid", bd=1)
        content.pack(fill="both", expand=True, padx=15, pady=15)

        tk.Label(
            content, text="📂 Load Preset", font=("Arial", 14, "bold"), bg="#ffffff", fg="#2c3e50"
        ).pack(pady=(10, 15))

        # Preset list
        list_frame = tk.Frame(content, bg="#ffffff")
        list_frame.pack(fill="both", expand=True, pady=(0, 15))

        scrollbar = tk.Scrollbar(list_frame)
        scrollbar.pack(side="right", fill="y")

        preset_listbox = tk.Listbox(list_frame, font=("Arial", 10), yscrollcommand=scrollbar.set)
        preset_listbox.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=preset_listbox.yview)

        # Populate presets
        preset_data = {}
        for preset_file in preset_files:
            preset_path = os.path.join(preset_dir, preset_file)
            try:
                with open(preset_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    preset_name = preset_file.replace("preset_", "").replace(".json", "")
                    job_count = len(data.get("jobs", []))
                    created = data.get("created", "N/A")
                    preset_listbox.insert(
                        "end", f"{preset_name} ({job_count} jobs) - {created[:10]}"
                    )
                    preset_data[preset_listbox.size() - 1] = (preset_name, preset_path, data)
            except:
                pass

        def load_selected():
            selection = preset_listbox.curselection()
            if not selection:
                messagebox.showwarning("Warning", "Please select a preset", parent=dialog)
                return

            preset_name, preset_path, data = preset_data[selection[0]]
            jobs = data.get("jobs", [])

            current_profile = self.profile_combo.get()

            current_profile_jobs = [
                job for job in self.saved_jobs if job.get("profile") == current_profile
            ]

            result = messagebox.askyesno(
                "Confirm Load",
                f"Load preset '{preset_name}'?\n\n"
                f"This will replace current "
                f"{len(current_profile_jobs)} jobs "
                f"with {len(jobs)} jobs from preset.",
                parent=dialog,
            )
            if result:

                current_profile = self.profile_combo.get()

                # ลบเฉพาะ Job ของ Profile ปัจจุบัน
                self.saved_jobs = [
                    job for job in self.saved_jobs if job.get("profile") != current_profile
                ]

                # เพิ่ม Profile ให้ Job เก่า
                for job in jobs:

                    job["profile"] = current_profile

                    self.saved_jobs.append(job)

                self.save_jobs()
                self.update_jobs_list()

                self.results_text.delete("1.0", tk.END)
                self.results_text.insert(tk.END, f"📂 Loaded preset: {preset_name}\n")
                self.results_text.insert(tk.END, f"📊 Jobs loaded: {len(jobs)}\n")
                self.results_text.see(tk.END)

                messagebox.showinfo(
                    "Success",
                    f"Preset '{preset_name}' loaded!\n\n{len(jobs)} jobs restored",
                    parent=dialog,
                )
                dialog.destroy()

        button_frame = tk.Frame(content, bg="#ffffff")
        button_frame.pack(pady=(15, 15))

        tk.Button(
            button_frame,
            text="📂 Load",
            command=load_selected,
            bg="#3498db",
            fg="white",
            font=("Arial", 10, "bold"),
            padx=20,
            pady=6,
        ).pack(side="left", padx=5)

        cancel_btn = tk.Button(
            button_frame,
            text="✖ Cancel",
            width=12,
            height=2,
            bg="#95a5a6",
            fg="white",
            font=("Arial", 10, "bold"),
            command=dialog.destroy,
        )

        cancel_btn.pack(side="left", padx=5)

    def setup_context_menus(self):
        """Setup right-click context menus for all text fields"""
        # Context menu for Entry widgets
        entry_menu = tk.Menu(self.root, tearoff=0)
        entry_menu.add_command(label="Cut", command=lambda: self.context_cut())
        entry_menu.add_command(label="Copy", command=lambda: self.context_copy())
        entry_menu.add_command(label="Paste", command=lambda: self.context_paste())
        entry_menu.add_separator()
        entry_menu.add_command(label="Select All", command=lambda: self.context_select_all())

        # Context menu for Text widgets
        text_menu = tk.Menu(self.root, tearoff=0)
        text_menu.add_command(label="Cut", command=lambda: self.context_cut_text())
        text_menu.add_command(label="Copy", command=lambda: self.context_copy_text())
        text_menu.add_command(label="Paste", command=lambda: self.context_paste_text())
        text_menu.add_separator()
        text_menu.add_command(label="Select All", command=lambda: self.context_select_all_text())

        # Bind context menus to Entry widgets
        entry_widgets = [self.db_user, self.db_password, self.db_host, self.db_port, self.db_name]
        for widget in entry_widgets:
            widget.bind("<Button-3>", lambda e, m=entry_menu: self.show_context_menu(e, m))

        # Bind context menus to Text widgets
        self.sql_context.bind("<Button-3>", lambda e, m=text_menu: self.show_context_menu(e, m))
        self.results_text.bind("<Button-3>", lambda e, m=text_menu: self.show_context_menu(e, m))

        # Store references
        self.current_widget = None

    def show_context_menu(self, event, menu):
        """Show context menu at cursor position"""
        self.current_widget = event.widget
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def context_cut(self):
        """Cut selected text from Entry widget"""
        if self.current_widget:
            try:
                self.current_widget.event_generate("<<Cut>>")
            except:
                pass

    def context_copy(self):
        """Copy selected text from Entry widget"""
        if self.current_widget:
            try:
                self.current_widget.event_generate("<<Copy>>")
            except:
                pass

    def context_paste(self):
        """Paste clipboard text into Entry widget"""
        if self.current_widget:
            try:
                self.current_widget.event_generate("<<Paste>>")
            except:
                pass

    def context_select_all(self):
        """Select all text in Entry widget"""
        if self.current_widget:
            try:
                self.current_widget.select_range(0, tk.END)
                self.current_widget.icursor(tk.END)
            except:
                pass

    def context_cut_text(self):
        """Cut selected text from Text widget"""
        if self.current_widget:
            try:
                self.current_widget.event_generate("<<Cut>>")
            except:
                pass

    def context_copy_text(self):
        """Copy selected text from Text widget"""
        if self.current_widget:
            try:
                self.current_widget.event_generate("<<Copy>>")
            except:
                pass

    def context_paste_text(self):
        """Paste clipboard text into Text widget"""
        if self.current_widget:
            try:
                self.current_widget.event_generate("<<Paste>>")
            except:
                pass

    def context_select_all_text(self):
        """Select all text in Text widget"""
        if self.current_widget:
            try:
                self.current_widget.tag_add(tk.SEL, "1.0", tk.END)
                self.current_widget.mark_set(tk.INSERT, "1.0")
                self.current_widget.see(tk.INSERT)
            except:
                pass

    def toggle_password_visibility(self):
        """Toggle password visibility"""
        self.password_visible = not self.password_visible
        self.db_password.config(show="" if self.password_visible else "*")
        self._refresh_password_icon()

    def _refresh_password_icon(self):
        """Eye = click to show; crossed eye (blue) = password is visible, click to hide."""
        if self.password_visible:
            self.toggle_password_btn.config(text=PASSWORD_ICON_HIDE, fg=UI["primary"])
        else:
            self.toggle_password_btn.config(text=PASSWORD_ICON_SHOW, fg=UI["muted"])

    def on_db_type_change(self, event):
        """Update default port when database type changes"""
        db_type = self.db_type.get()
        port_defaults = {
            "PostgreSQL": "5432",
            "MySQL": "3306",
            "Microsoft SQL Server": "1433",
            "Oracle": "1521",
        }
        self.db_port.delete(0, tk.END)
        self.db_port.insert(0, port_defaults.get(db_type, "5432"))

    def load_table_data_dialog(self):
        """ENHANCED: Load table data with smart auto-sync and templates"""
        try:
            # Check if table data file exists
            if not os.path.exists(self.table_data_file):
                messagebox.showinfo(
                    "No Table Data",
                    "No table data found from Mail Notify Tool.\n\n"
                    "Please:\n"
                    "1. Select tables in Mail Notify Tool\n"
                    "2. Click 'Run SQL Scripts' button\n"
                    "3. Table data will be automatically exported",
                )
                return

            # ==================================================
            # FORCE CLEAR OLD CACHE
            # ==================================================

            self.loaded_table_data = None

            if hasattr(self, "saved_table_mappings"):
                self.saved_table_mappings = dict(self.saved_table_mappings)

            # Force reload latest file
            with open(self.table_data_file, "r", encoding="utf-8") as f:
                self.loaded_table_data = json.load(f)

            # Update file timestamp
            self.last_table_data_mtime = os.path.getmtime(self.table_data_file)

            tables = self.loaded_table_data.get("tables", {})

            if not tables:
                messagebox.showinfo(
                    "No Tables",
                    "No tables found in exported data.\n\n"
                    "Please select tables in Mail Notify Tool first.",
                )
                return

            # Show ENHANCED table selection dialog
            self.show_enhanced_table_data_selection_dialog(tables)

        except Exception as e:
            messagebox.showerror("Load Error", f"Failed to load table data:\n{str(e)}")

    def show_enhanced_table_data_selection_dialog(self, tables):
        """ENHANCED: Smart table data selection with auto-sync and templates"""
        dialog = self._create_centered_dialog("📊 Smart Table Data Manager", 1200, 850)

        # Suppress main canvas mousewheel scroll while dialog is open
        self.canvas.unbind_all("<MouseWheel>")

        def _restore_main_scroll(e=None):
            self.canvas.bind_all("<MouseWheel>", self._main_mousewheel)

        dialog.bind("<Destroy>", _restore_main_scroll)

        # Content frame
        content_frame = tk.Frame(dialog, bg="#ffffff", relief="solid", bd=1)
        content_frame.pack(fill="both", expand=True, padx=15, pady=15)

        # Title with status indicator
        title_frame = tk.Frame(content_frame, bg="#ffffff")
        title_frame.pack(fill="both", pady=(10, 15))

        tk.Label(
            title_frame,
            text="📊 Smart Table Data Manager",
            font=("Arial", 14, "bold"),
            bg="#ffffff",
            fg="#2c3e50",
        ).pack(side="left")

        # Auto-sync status indicator
        self.sync_status_label = tk.Label(
            title_frame,
            text="🔴 Auto-sync OFF",
            font=("Arial", 9, "bold"),
            bg="#ffffff",
            fg="#e74c3c",
        )
        self.sync_status_label.pack(side="right", padx=10)

        # Info section with file monitoring
        info_frame = tk.Frame(content_frame, bg="#e8f4f8", relief="solid", bd=1)
        info_frame.pack(fill="both", pady=(0, 10))

        phase = self.loaded_table_data.get("phase", "N/A")
        timestamp = self.loaded_table_data.get("timestamp", "N/A")

        info_text = f"📋 Phase: {phase} | 🕒 Exported: {timestamp} | 📊 Tables: {len(tables)}"

        tk.Label(info_frame, text=info_text, font=("Arial", 10), bg="#e8f4f8", fg="#2c3e50").pack(
            pady=8, padx=10
        )

        # NEW: Quick Actions Bar
        quick_actions = tk.Frame(content_frame, bg="#f8f9fa", relief="solid", bd=1)
        quick_actions.pack(fill="both", pady=(0, 10))

        tk.Label(
            quick_actions,
            text="⚡ Quick Actions:",
            font=("Arial", 10, "bold"),
            bg="#f8f9fa",
            fg="#2c3e50",
        ).pack(side="left", padx=10, pady=8)
        tk.Button(
            quick_actions,
            text="🔄 Reload Latest Data",
            command=self.load_table_data_dialog,
            bg="#e67e22",
            fg="white",
            font=("Arial", 9, "bold"),
            relief="flat",
            padx=12,
            pady=4,
        ).pack(side="left", padx=2)

        tk.Button(
            quick_actions,
            text="🔄 Enable Auto-Sync",
            command=lambda: self.toggle_auto_sync(True),
            bg="#27ae60",
            fg="white",
            font=("Arial", 9, "bold"),
            relief="flat",
            padx=12,
            pady=4,
        ).pack(side="left", padx=2)

        tk.Button(
            quick_actions,
            text="💾 Save as Template",
            command=lambda: self.save_query_template_dialog(),
            bg="#3498db",
            fg="white",
            font=("Arial", 9, "bold"),
            relief="flat",
            padx=12,
            pady=4,
        ).pack(side="left", padx=2)

        tk.Button(
            quick_actions,
            text="📋 Load Template",
            command=lambda: self.load_query_template_dialog(tables),
            bg="#9b59b6",
            fg="white",
            font=("Arial", 9, "bold"),
            relief="flat",
            padx=12,
            pady=4,
        ).pack(side="left", padx=2)

        tk.Button(
            quick_actions,
            text="🎯 Smart Map All",
            command=lambda: self.smart_map_all_tables(tables),
            bg="#e67e22",
            fg="white",
            font=("Arial", 9, "bold"),
            relief="flat",
            padx=12,
            pady=4,
        ).pack(side="left", padx=2)

        # Main content - Enhanced 3-column layout
        main_content = tk.Frame(content_frame, bg="#ffffff")
        main_content.pack(fill="both", expand=True, pady=(0, 10))

        # LEFT: Table Selection (30%)
        left_frame = tk.Frame(main_content, bg="#ffffff", width=300)
        left_frame.pack(side="left", fill="both", expand=False, padx=(10, 5))
        left_frame.pack_propagate(False)

        table_frame = tk.LabelFrame(
            left_frame,
            text="① Select Table",
            font=("Arial", 11, "bold"),
            bg="#ffffff",
            fg="#27ae60",
            relief="groove",
            bd=2,
        )
        table_frame.pack(fill="both", expand=True)

        # Table list with icons
        table_list_frame = tk.Frame(table_frame, bg="#ffffff")
        table_list_frame.pack(fill="both", expand=True, padx=10, pady=10)

        table_scrollbar = tk.Scrollbar(table_list_frame)
        table_scrollbar.pack(side="right", fill="y")

        table_listbox = tk.Listbox(
            table_list_frame,
            yscrollcommand=table_scrollbar.set,
            font=("Arial", 10),
            selectmode=tk.SINGLE,
            exportselection=False,
            bg="white",
            selectbackground="#3498db",
            selectforeground="white",
        )
        table_listbox.pack(side="left", fill="both", expand=True)
        table_scrollbar.config(command=table_listbox.yview)

        table_names = list(tables.keys())
        for table_name in table_names:
            table_info = tables[table_name]
            # Add indicator if table has saved mapping
            has_mapping = table_name in self.saved_table_mappings
            icon = "📌" if has_mapping else "📊"
            table_listbox.insert("end", f"{icon} {table_name} ({table_info['columns']} cols)")

        # MIDDLE: Column Selection with Multi-Select (35%)
        middle_frame = tk.Frame(main_content, bg="#ffffff", width=350)
        middle_frame.pack(side="left", fill="both", expand=False, padx=5)
        middle_frame.pack_propagate(False)

        column_frame = tk.LabelFrame(
            middle_frame,
            text="② Select Columns",
            font=("Arial", 11, "bold"),
            bg="#ffffff",
            fg="#3498db",
            relief="groove",
            bd=2,
        )
        column_frame.pack(fill="both", expand=True)

        # Column controls
        column_control_frame = tk.Frame(column_frame, bg="#ffffff")
        column_control_frame.pack(fill="both", padx=10, pady=(10, 5))

        tk.Label(
            column_control_frame,
            text="💡 Ctrl+Click for multiple",
            font=("Arial", 8, "italic"),
            bg="#ffffff",
            fg="#7f8c8d",
        ).pack(side="left")

        def select_all_columns():
            column_listbox.select_set(0, tk.END)
            update_preview()

        def clear_all_columns():
            column_listbox.selection_clear(0, tk.END)
            update_preview()

        tk.Button(
            column_control_frame,
            text="✅ All",
            command=select_all_columns,
            bg="#27ae60",
            fg="white",
            font=("Arial", 7, "bold"),
            padx=6,
            pady=2,
        ).pack(side="right", padx=(2, 0))

        tk.Button(
            column_control_frame,
            text="❌ Clear",
            command=clear_all_columns,
            bg="#e74c3c",
            fg="white",
            font=("Arial", 7, "bold"),
            padx=6,
            pady=2,
        ).pack(side="right")

        column_list_frame = tk.Frame(column_frame, bg="#ffffff")
        column_list_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        column_scrollbar = tk.Scrollbar(column_list_frame)
        column_scrollbar.pack(side="right", fill="y")

        column_listbox = tk.Listbox(
            column_list_frame,
            yscrollcommand=column_scrollbar.set,
            font=("Arial", 10),
            selectmode=tk.EXTENDED,
            exportselection=False,
            bg="white",
            selectbackground="#3498db",
            selectforeground="white",
        )
        column_listbox.pack(side="left", fill="both", expand=True)
        column_scrollbar.config(command=column_listbox.yview)

        # RIGHT: Options & Preview (35%)
        right_frame = tk.Frame(main_content, bg="#ffffff")
        right_frame.pack(side="right", fill="both", expand=True, padx=(5, 10))

        # Insert Mode
        mode_frame = tk.LabelFrame(
            right_frame,
            text="③ Insert Mode",
            font=("Arial", 11, "bold"),
            bg="#ffffff",
            fg="#9b59b6",
            relief="groove",
            bd=2,
        )
        mode_frame.pack(fill="both", pady=(0, 8))

        insert_mode_var = tk.StringVar(value="raw")

        mode_inner = tk.Frame(mode_frame, bg="#ffffff")
        mode_inner.pack(fill="both", padx=10, pady=8)

        tk.Radiobutton(
            mode_inner,
            text="📝 Raw Data (direct insert)",
            variable=insert_mode_var,
            value="raw",
            font=("Arial", 9),
            bg="#ffffff",
            command=lambda: update_preview(),
        ).pack(anchor="w", pady=2)

        tk.Radiobutton(
            mode_inner,
            text="🔤 Variable (for templates)",
            variable=insert_mode_var,
            value="variable",
            font=("Arial", 9),
            bg="#ffffff",
            command=lambda: update_preview(),
        ).pack(anchor="w", pady=2)

        # NEW: Auto-Sync Settings
        sync_frame = tk.LabelFrame(
            right_frame,
            text="🔄 Auto-Sync Settings",
            font=("Arial", 11, "bold"),
            bg="#ffffff",
            fg="#e67e22",
        )
        sync_frame.pack(fill="both", pady=(0, 8))

        sync_inner = tk.Frame(sync_frame, bg="#ffffff")
        sync_inner.pack(fill="both", padx=10, pady=8)

        sync_enabled = tk.Checkbutton(
            sync_inner,
            text="Enable auto-sync when file changes",
            variable=self.auto_sync_enabled,
            font=("Arial", 9),
            bg="#ffffff",
            command=lambda: self.toggle_auto_sync(self.auto_sync_enabled.get()),
        )
        sync_enabled.pack(anchor="w", pady=2)

        interval_frame = tk.Frame(sync_inner, bg="#ffffff")
        interval_frame.pack(fill="both", pady=(5, 0))

        tk.Label(interval_frame, text="Check interval:", font=("Arial", 9), bg="#ffffff").pack(
            side="left"
        )

        interval_var = tk.StringVar(value="300")
        interval_entry = tk.Entry(
            interval_frame, textvariable=interval_var, width=5, font=("Arial", 9)
        )
        interval_entry.pack(side="left", padx=5)

        tk.Label(interval_frame, text="seconds", font=("Arial", 9), bg="#ffffff").pack(side="left")

        def update_sync_interval():
            try:
                self.sync_interval_seconds = int(interval_var.get())
                if self.auto_sync_enabled.get():
                    self.schedule_next_sync_check()
            except:
                pass

        tk.Button(
            interval_frame,
            text="✓",
            command=update_sync_interval,
            bg="#27ae60",
            fg="white",
            font=("Arial", 8, "bold"),
            padx=4,
            pady=1,
        ).pack(side="left", padx=2)

        # Preview
        preview_frame = tk.LabelFrame(
            right_frame, text="👁️ Preview", font=("Arial", 11, "bold"), bg="#ffffff", fg="#e67e22"
        )
        preview_frame.pack(fill="both", expand=True)

        preview_text_frame = tk.Frame(preview_frame, bg="#ffffff")
        preview_text_frame.pack(fill="both", expand=True, padx=10, pady=10)

        preview_scrollbar = tk.Scrollbar(preview_text_frame)
        preview_scrollbar.pack(side="right", fill="y")

        preview_text = tk.Text(
            preview_text_frame,
            height=15,
            font=("Courier", 8),
            bg="#f8f9fa",
            state="disabled",
            wrap=tk.WORD,
            yscrollcommand=preview_scrollbar.set,
        )
        preview_text.pack(side="left", fill="both", expand=True)
        preview_scrollbar.config(command=preview_text.yview)

        # Update preview function
        def update_preview(event=None):
            table_selection = table_listbox.curselection()
            column_selections = column_listbox.curselection()

            preview_text.configure(state="normal")
            preview_text.delete(1.0, tk.END)

            if not table_selection:
                preview_text.insert(tk.END, "Select a table first")
                preview_text.configure(state="disabled")
                return

            selected_table = table_names[table_selection[0]]
            table_data = tables[selected_table]
            column_data_dict = table_data.get("column_data", {})

            if not column_selections:
                preview_text.insert(tk.END, f"Table: {selected_table}\n")
                preview_text.insert(tk.END, f"{'='*50}\n\n")
                preview_text.insert(tk.END, f"Columns ({len(column_data_dict)}):\n\n")
                for col_name in column_data_dict.keys():
                    preview_text.insert(tk.END, f"  • {col_name}\n")
                preview_text.insert(tk.END, "\n💡 Select columns to preview")
                preview_text.configure(state="disabled")
                return

            column_names = list(column_data_dict.keys())
            selected_columns = [column_names[i] for i in column_selections]
            insert_mode = insert_mode_var.get()

            preview_text.insert(tk.END, f"📊 {selected_table}\n")
            preview_text.insert(tk.END, f"Selected: {len(selected_columns)} column(s)\n")
            preview_text.insert(tk.END, f"{'='*50}\n\n")

            for col_name in selected_columns:
                column_values = column_data_dict[col_name]
                preview_text.insert(tk.END, f"📌 {col_name}  ({len(column_values)} values)\n")

                # Show ALL values
                for i, value in enumerate(column_values, 1):
                    preview_text.insert(tk.END, f"   {i}. {value}\n")

                preview_text.insert(tk.END, f"\n{'─'*50}\n\n")

            preview_text.configure(state="disabled")

        # Table selection handler
        def on_table_select(event):
            column_listbox.delete(0, tk.END)

            table_selection = table_listbox.curselection()
            if not table_selection:
                return

            selected_table = table_names[table_selection[0]]
            table_data = tables[selected_table]
            column_data_dict = table_data.get("column_data", {})

            # Populate columns with mapping indicators
            for col_name in column_data_dict.keys():
                col_values = column_data_dict[col_name]
                # Check if this column has saved mapping
                has_mapping = (
                    selected_table in self.saved_table_mappings
                    and col_name in self.saved_table_mappings[selected_table]
                )
                icon = "📌" if has_mapping else "📋"
                column_listbox.insert("end", f"{icon} {col_name} ({len(col_values)} vals)")

            update_preview()

            # Auto-select columns if mapping exists
            if selected_table in self.saved_table_mappings:
                saved_cols = self.saved_table_mappings[selected_table]
                all_cols = list(column_data_dict.keys())
                for saved_col in saved_cols:
                    if saved_col in all_cols:
                        idx = all_cols.index(saved_col)
                        column_listbox.selection_set(idx)
                update_preview()

        # Bind events
        table_listbox.bind("<<ListboxSelect>>", on_table_select)
        column_listbox.bind("<<ListboxSelect>>", update_preview)
        table_listbox.bind("<ButtonRelease-1>", on_table_select)
        column_listbox.bind("<ButtonRelease-1>", update_preview)
        insert_mode_var.trace_add("write", lambda *args: update_preview())

        # Auto-select first table
        if table_names:
            table_listbox.selection_set(0)
            table_listbox.event_generate("<<ListboxSelect>>")
            on_table_select(None)

        # Action Buttons
        button_frame = tk.Frame(content_frame, bg="#ffffff")
        button_frame.pack(fill="both", pady=(0, 10))

        def insert_and_save_mapping():
            table_selection = table_listbox.curselection()
            column_selections = column_listbox.curselection()

            if not table_selection or not column_selections:
                messagebox.showwarning(
                    "No Selection", "Please select table and column(s)", parent=dialog
                )
                return

            selected_table = table_names[table_selection[0]]
            table_data = tables[selected_table]
            column_data_dict = table_data.get("column_data", {})

            column_names = list(column_data_dict.keys())
            selected_columns = [column_names[i] for i in column_selections]

            insert_mode = insert_mode_var.get()
            cursor_pos = self.sql_context.index(tk.INSERT)

            inserted_items = []

            for col_name in selected_columns:
                column_values = column_data_dict[col_name]

                if insert_mode == "variable":
                    safe_table = selected_table.upper().replace(" ", "_").replace("-", "_")
                    safe_col = col_name.upper().replace(" ", "_").replace("-", "_")
                    variable_name = f"{{TABLE_{safe_table}_{safe_col}}}"

                    self.sql_context.insert(cursor_pos, variable_name + " ")
                    inserted_items.append(f"Variable: {variable_name}")
                else:
                    formatted_vals = [
                        f"'{v}'" if isinstance(v, str) else str(v) for v in column_values
                    ]
                    # Normalize column name: strip spaces for SQL matching
                    col_lower = col_name.lower().replace(" ", "")
                    if len(formatted_vals) == 1:
                        new_expr = f"{col_lower} = {formatted_vals[0]}"
                    else:
                        vals_joined = ", ".join(formatted_vals)
                        new_expr = f"{col_lower} in ({vals_joined})"

                    # Smart replace: update existing condition, or append after bare column name
                    import re as _re

                    current_sql = self.sql_context.get(1.0, tk.END).rstrip("\n")
                    col_esc = _re.escape(col_lower)

                    # Case 1: column already has IN(...) or = value → replace the full condition
                    pattern_with_cond = _re.compile(
                        rf'({col_esc})\s*(?:in\s*\([^)]*\)|=\s*(?:\'[^\']*\'|"[^"]*"|\S+))',
                        _re.IGNORECASE,
                    )
                    # Case 2: column exists at end of string or followed only by whitespace/EOL → append condition
                    pattern_bare = _re.compile(rf"({col_esc})\s*$", _re.IGNORECASE | _re.MULTILINE)

                    if pattern_with_cond.search(current_sql):
                        new_sql = pattern_with_cond.sub(new_expr, current_sql, count=1)
                        self.sql_context.delete(1.0, tk.END)
                        self.sql_context.insert(1.0, new_sql)
                        inserted_items.append(f"Updated: {new_expr[:100]}")
                    elif pattern_bare.search(current_sql):
                        if len(formatted_vals) == 1:
                            replacement = rf"\1 = {formatted_vals[0]}"
                        else:
                            vals_joined2 = ", ".join(formatted_vals)
                            replacement = rf"\1 in ({vals_joined2})"
                        new_sql = pattern_bare.sub(replacement, current_sql, count=1)
                        self.sql_context.delete(1.0, tk.END)
                        self.sql_context.insert(1.0, new_sql)
                        inserted_items.append(f"Updated: {new_expr[:100]}")
                    else:
                        self.sql_context.insert(cursor_pos, new_expr + " ")
                        inserted_items.append(f"SQL: {new_expr[:100]}")

            # Save mapping
            if selected_table not in self.saved_table_mappings:
                self.saved_table_mappings[selected_table] = []
            self.saved_table_mappings[selected_table] = selected_columns
            self.save_table_mappings()

            success_msg = f"✅ Inserted {len(selected_columns)} column(s)!\n"
            success_msg += f"📌 Mapping saved for future use\n\n"
            success_msg += "\n".join(inserted_items)

            if insert_mode == "variable" and self.auto_sync_enabled.get():
                success_msg += "\n\n🔄 Auto-sync enabled - variables will update automatically"

            messagebox.showinfo("Success", success_msg, parent=dialog)
            dialog.destroy()

        tk.Button(
            button_frame,
            text="📝 Insert & Save Mapping",
            command=insert_and_save_mapping,
            bg="#27ae60",
            fg="white",
            font=("Arial", 10, "bold"),
            padx=20,
            pady=6,
        ).pack(side="left")

        cancel_btn = tk.Button(
            button_frame,
            text="✖ Cancel",
            width=12,
            height=2,
            bg="#95a5a6",
            fg="white",
            font=("Arial", 10, "bold"),
            command=dialog.destroy,
        )

        cancel_btn.pack(side="left", padx=5)

    # NEW: Auto-sync methods

    def toggle_auto_sync(self, enabled):
        """Toggle auto-sync on/off"""
        if enabled:
            self.auto_sync_enabled.set(True)
            self.sync_status_label.config(text="🟢 Auto-sync ON", fg="#27ae60")
            self.schedule_next_sync_check()
            self.results_text.insert(tk.END, "🔄 Auto-sync enabled\n")
            self.results_text.insert(tk.END, f"   Checking every {self.sync_interval_seconds}s\n\n")
        else:
            self.auto_sync_enabled.set(False)
            self.sync_status_label.config(text="🔴 Auto-sync OFF", fg="#e74c3c")
            if self.sync_timer_id:
                self.root.after_cancel(self.sync_timer_id)
                self.sync_timer_id = None
            self.results_text.insert(tk.END, "⏸️ Auto-sync disabled\n\n")
        self.results_text.see(tk.END)

    def schedule_next_sync_check(self):
        """Schedule next sync check"""
        if self.sync_timer_id:
            self.root.after_cancel(self.sync_timer_id)

        if self.auto_sync_enabled.get():
            self.sync_timer_id = self.root.after(
                self.sync_interval_seconds * 1000,  # Convert to milliseconds
                self.check_and_sync_table_data,
            )

    def check_and_sync_table_data(self):
        """Check if table data file has changed and auto-sync"""
        try:
            if not os.path.exists(self.table_data_file):
                self.schedule_next_sync_check()
                return

            # Check file modification time
            current_mtime = os.path.getmtime(self.table_data_file)

            if self.last_table_data_mtime is None:
                self.last_table_data_mtime = current_mtime
                self.schedule_next_sync_check()
                return

            # File has been modified
            if current_mtime > self.last_table_data_mtime:
                self.last_table_data_mtime = current_mtime

                # Reload table data
                with open(self.table_data_file, "r", encoding="utf-8") as f:
                    self.loaded_table_data = json.load(f)

                # Auto-replace variables in current query
                updated_count = self.auto_replace_table_variables()

                if updated_count > 0:
                    self.results_text.insert(tk.END, f"🔄 Auto-sync triggered!\n")
                    self.results_text.insert(tk.END, f"   Updated {updated_count} variable(s)\n")
                    self.results_text.insert(
                        tk.END, f"   Time: {pd.Timestamp.now().strftime('%H:%M:%S')}\n\n"
                    )
                    self.results_text.see(tk.END)

            # Schedule next check
            self.schedule_next_sync_check()

        except Exception as e:
            print(f"Auto-sync error: {e}")
            self.schedule_next_sync_check()

    def auto_replace_table_variables(self):
        """Automatically replace table variables with current data"""
        try:
            if not self.loaded_table_data:
                return 0

            tables = self.loaded_table_data.get("tables", {})
            sql_query = self.sql_context.get(1.0, tk.END)

            import re

            updated_count = 0

            # Find all {TABLE_*} variables
            pattern = r"\{TABLE_([A-Z0-9_]+)_([A-Z0-9_]+)\}"
            matches = re.findall(pattern, sql_query)

            for table_part, column_part in matches:
                # Find matching table and column
                for table_name, table_data in tables.items():
                    safe_table = table_name.upper().replace(" ", "_").replace("-", "_")

                    if safe_table == table_part:
                        column_data_dict = table_data.get("column_data", {})

                        for col_name, col_values in column_data_dict.items():
                            safe_col = col_name.upper().replace(" ", "_").replace("-", "_")

                            if safe_col == column_part:
                                # Found match - replace variable
                                old_var = f"{{TABLE_{table_part}_{column_part}}}"
                                new_values = ", ".join(
                                    [f"'{v}'" if isinstance(v, str) else str(v) for v in col_values]
                                )

                                sql_query = sql_query.replace(old_var, new_values)
                                updated_count += 1
                                break

            # Update query if changes made
            if updated_count > 0:
                self.sql_context.delete(1.0, tk.END)
                self.sql_context.insert(1.0, sql_query)

            return updated_count

        except Exception as e:
            print(f"Auto-replace error: {e}")
            return 0

    def save_table_mappings(self):
        """Save table-to-column mappings"""
        try:
            mappings_file = os.path.join(os.path.dirname(self.config_file), "table_mappings.json")
            with open(mappings_file, "w", encoding="utf-8") as f:
                json.dump(self.saved_table_mappings, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Failed to save mappings: {e}")

    def load_table_mappings(self):
        """Load saved table mappings"""
        try:
            mappings_file = os.path.join(os.path.dirname(self.config_file), "table_mappings.json")
            if os.path.exists(mappings_file):
                with open(mappings_file, "r", encoding="utf-8") as f:
                    self.saved_table_mappings = json.load(f)
        except:
            self.saved_table_mappings = {}

    def smart_map_all_tables(self, tables):
        """Automatically map all tables based on previous patterns"""
        mapped_count = 0

        for table_name in tables.keys():
            if table_name in self.saved_table_mappings:
                mapped_count += 1

        if mapped_count == 0:
            messagebox.showinfo(
                "No Mappings",
                "No saved mappings found.\n\n" "Select and save columns first to use Smart Map.",
            )
            return

        msg = f"📊 Found saved mappings for {mapped_count} table(s)\n\n"
        msg += "These will be auto-selected when you choose the table.\n\n"
        msg += "💡 Use 'Insert & Save Mapping' to update mappings."

        messagebox.showinfo("Smart Map Status", msg)

    def save_query_template_dialog(self):
        """Save current query as reusable template"""
        sql_query = self.sql_context.get(1.0, tk.END).strip()
        if not sql_query:
            messagebox.showwarning("No Query", "Please enter a query first")
            return

        dialog = self._create_centered_dialog("💾 Save Query Template", 500, 300)

        content = tk.Frame(dialog, bg="#ffffff", relief="solid", bd=1)
        content.pack(fill="both", expand=True, padx=15, pady=15)

        tk.Label(
            content, text="💾 Save Query Template", font=("Arial", 12, "bold"), bg="#ffffff"
        ).pack(pady=(10, 15))

        tk.Label(content, text="Template Name:", font=("Arial", 10), bg="#ffffff").pack(
            anchor="w", padx=10, pady=(0, 5)
        )

        name_entry = tk.Entry(content, font=("Arial", 10), width=50)
        name_entry.pack(padx=10, pady=(0, 10))
        name_entry.focus()

        tk.Label(
            content,
            text=f"Query: {sql_query[:100]}{'...' if len(sql_query) > 100 else ''}",
            font=("Arial", 8),
            bg="#ffffff",
            fg="#7f8c8d",
        ).pack(padx=10)

        def save():
            template_name = name_entry.get().strip()
            if not template_name:
                messagebox.showwarning("No Name", "Enter template name", parent=dialog)
                return

            self.query_templates[template_name] = {
                "query": sql_query,
                "created": pd.Timestamp.now().isoformat(),
            }

            # Save to file
            templates_file = os.path.join(os.path.dirname(self.config_file), "query_templates.json")
            try:
                with open(templates_file, "w", encoding="utf-8") as f:
                    json.dump(self.query_templates, f, indent=2, ensure_ascii=False)

                messagebox.showinfo("Success", f"Template '{template_name}' saved!", parent=dialog)
                dialog.destroy()
            except Exception as e:
                messagebox.showerror("Error", f"Failed to save:\n{e}", parent=dialog)

        button_frame = tk.Frame(content, bg="#ffffff")
        button_frame.pack(pady=(15, 15))

        save_btn = tk.Button(
            button_frame,
            text="💾 Save",
            width=12,
            height=2,
            bg="#27ae60",
            fg="white",
            font=("Arial", 10, "bold"),
            command=save,
        )

        save_btn.pack(side="left", padx=5)

        cancel_btn = tk.Button(
            button_frame,
            text="✖ Cancel",
            width=12,
            height=2,
            bg="#95a5a6",
            fg="white",
            font=("Arial", 10, "bold"),
            command=dialog.destroy,
        )

        cancel_btn.pack(side="left", padx=5)

    def load_query_template_dialog(self, tables):
        """Load saved query template"""
        templates_file = os.path.join(os.path.dirname(self.config_file), "query_templates.json")

        try:
            if os.path.exists(templates_file):
                with open(templates_file, "r", encoding="utf-8") as f:
                    self.query_templates = json.load(f)
        except:
            pass

        if not self.query_templates:
            messagebox.showinfo("No Templates", "No saved templates found")
            return

        dialog = self._create_centered_dialog("📋 Load Query Template", 600, 400)

        content = tk.Frame(dialog, bg="#ffffff", relief="solid", bd=1)
        content.pack(fill="both", expand=True, padx=15, pady=15)

        tk.Label(content, text="📋 Select Template", font=("Arial", 12, "bold"), bg="#ffffff").pack(
            pady=(10, 15)
        )

        list_frame = tk.Frame(content, bg="#ffffff")
        list_frame.pack(fill="both", expand=True, pady=(0, 15))

        scrollbar = tk.Scrollbar(list_frame)
        scrollbar.pack(side="right", fill="y")

        template_listbox = tk.Listbox(list_frame, font=("Arial", 10), yscrollcommand=scrollbar.set)
        template_listbox.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=template_listbox.yview)

        for template_name in self.query_templates.keys():
            template_listbox.insert("end", f"📄 {template_name}")

        def load_selected():
            selection = template_listbox.curselection()
            if not selection:
                messagebox.showwarning("No Selection", "Select a template", parent=dialog)
                return

            template_names = list(self.query_templates.keys())
            selected_name = template_names[selection[0]]
            template_data = self.query_templates[selected_name]

            # Load to editor
            self.sql_context.delete(1.0, tk.END)
            self.sql_context.insert(1.0, template_data["query"])

            self.results_text.insert(tk.END, f"📋 Loaded template: {selected_name}\n\n")
            self.results_text.see(tk.END)

            messagebox.showinfo("Success", f"Template '{selected_name}' loaded!", parent=dialog)
            dialog.destroy()

        button_frame = tk.Frame(content, bg="#ffffff")
        button_frame.pack(pady=(15, 15))

        tk.Button(
            button_frame,
            text="📋 Load",
            command=load_selected,
            bg="#3498db",
            fg="white",
            font=("Arial", 10, "bold"),
            padx=20,
            pady=6,
        ).pack(side="left", padx=5)

        cancel_btn = tk.Button(
            button_frame,
            text="✖ Cancel",
            width=12,
            height=2,
            bg="#95a5a6",
            fg="white",
            font=("Arial", 10, "bold"),
            command=dialog.destroy,
        )

        cancel_btn.pack(side="left", padx=5)

    def _create_loading_dialog_with_retry(self, sql_query):
        """NEW: Create loading dialog with retry capability"""
        loading_dialog = tk.Toplevel(self.root)
        loading_dialog.title("Executing Query...")
        loading_dialog.geometry("400x250")
        loading_dialog.configure(bg="#f0f0f0")
        loading_dialog.transient(self.root)
        loading_dialog.grab_set()

        # Center dialog
        loading_dialog.update_idletasks()
        x = (loading_dialog.winfo_screenwidth() // 2) - (loading_dialog.winfo_width() // 2)
        y = (loading_dialog.winfo_screenheight() // 2) - (loading_dialog.winfo_height() // 2)
        loading_dialog.geometry(f"+{x}+{y}")

        # Content frame
        content_frame = tk.Frame(loading_dialog, bg="#ffffff", relief="solid", bd=1)
        content_frame.pack(fill="both", expand=True, padx=15, pady=15)

        # Status label
        status_label = tk.Label(
            content_frame,
            text="⏳ Executing query...",
            font=("Arial", 11, "bold"),
            bg="#ffffff",
            fg="#2c3e50",
        )
        status_label.pack(pady=(10, 5))

        # Progress bar
        progress = ttk.Progressbar(content_frame, mode="indeterminate", length=300)
        progress.pack(pady=10)
        progress.start(10)

        # Details label
        details_label = tk.Label(
            content_frame, text="Please wait...", font=("Arial", 9), bg="#ffffff", fg="#7f8c8d"
        )
        details_label.pack(pady=5)

        # UI: compact preview of the SQL being executed
        _sql_preview = " ".join(str(sql_query).split())
        if len(_sql_preview) > 90:
            _sql_preview = _sql_preview[:87] + "…"
        tk.Label(
            content_frame,
            text=_sql_preview,
            font=("Consolas", 9),
            bg=UI["surface"],
            fg=UI["muted"],
            wraplength=330,
            justify="left",
            padx=8,
            pady=6,
        ).pack(fill="x", padx=16, pady=(4, 10))

        # Button frame (initially hidden)
        button_frame = tk.Frame(content_frame, bg="#ffffff")

        # Store references
        loading_dialog.status_label = status_label
        loading_dialog.details_label = details_label
        loading_dialog.progress = progress
        loading_dialog.button_frame = button_frame
        loading_dialog.sql_query = sql_query

        # Reset execute button if user closes loading dialog via X
        def _on_loading_close():
            loading_dialog.destroy()
            self.execute_btn.config(state="normal", text="▶  Run")

        loading_dialog.protocol("WM_DELETE_WINDOW", _on_loading_close)

        return loading_dialog

    def _execute_query_background(self, sql_query, loading_dialog):
        """NEW: Execute query in background with comprehensive error logging"""

        def execute_in_background():
            error_details = None

            try:
                # Debug logging
                if self.debug_mode.get():
                    print(f"\n{'='*100}")
                    print(f"🔍 DEBUG: Starting query execution")
                    print(f"Query: {sql_query}")
                    print(f"Engine: {self.engine}")
                    print(f"{'='*100}\n")

                # Check if it's a SELECT query or data modification
                if self.is_select_query(sql_query):
                    if self.debug_mode.get():
                        print("🔍 DEBUG: Detected SELECT query")

                    # Execute SELECT query and get results
                    df = self.read_sql_dataframe(sql_query)

                    if self.debug_mode.get():
                        print(f"✅ DEBUG: Query successful - {len(df)} rows, {df.shape[1]} columns")

                    # Update UI in main thread
                    self.root.after(0, lambda: self.on_query_success(df, sql_query, loading_dialog))
                else:
                    if self.debug_mode.get():
                        print("🔍 DEBUG: Detected data modification query")

                    # Execute UPDATE/INSERT/DELETE statement
                    with self.engine.connect() as conn:
                        result = conn.execute(text(sql_query))
                        conn.commit()
                        rows_affected = result.rowcount

                    if self.debug_mode.get():
                        print(f"✅ DEBUG: Modification successful - {rows_affected} rows affected")

                    # Update UI in main thread with modification result
                    self.root.after(
                        0,
                        lambda: self.on_modification_success(
                            rows_affected, sql_query, loading_dialog
                        ),
                    )

            except Exception as e:
                # Comprehensive error logging
                error_type = type(e).__name__
                error_message = str(e)
                error_traceback = traceback.format_exc()

                # Store error details for retry
                error_details = {
                    "type": error_type,
                    "message": error_message,
                    "traceback": error_traceback,
                    "query": sql_query,
                }

                if self.debug_mode.get():
                    print(f"\n{'='*100}")
                    print(f"❌ DEBUG: Query execution failed")
                    print(f"Error Type: {error_type}")
                    print(f"Error Message: {error_message}")
                    print(f"Full Traceback:\n{error_traceback}")
                    print(f"{'='*100}\n")

                # Store for potential retry
                self.last_error_details = error_details

                # Handle error in main thread
                self.root.after(
                    0, lambda: self.on_query_error_enhanced(error_details, loading_dialog)
                )

        # Start background thread
        thread = threading.Thread(target=execute_in_background, daemon=True)
        thread.start()

    def on_query_error_enhanced(self, error_details, loading_dialog):
        """NEW: Enhanced error handling with detailed debugging and retry option"""
        try:
            # Update loading dialog to show error
            loading_dialog.progress.stop()
            loading_dialog.status_label.config(text="❌ Query Failed", fg="#e74c3c")
            loading_dialog.details_label.config(text="Click 'Show Details' for error information")

            # Reset execute button immediately — don't wait for user to click Close
            self.execute_btn.config(state="normal", text="▶  Run")

            # Release grab so error details sub-dialog can receive input
            loading_dialog.grab_release()
            # Re-bind WM_DELETE_WINDOW (grab already released, just destroy)
            loading_dialog.protocol("WM_DELETE_WINDOW", loading_dialog.destroy)

            # Show retry and details buttons
            loading_dialog.button_frame.pack(pady=(10, 0))

            def retry_query():
                loading_dialog.destroy()
                self.execute_query()  # Retry the query

            def show_error_details():
                self._show_error_details_dialog(error_details)

            def close_dialog():
                loading_dialog.destroy()

            # Clear existing buttons
            for widget in loading_dialog.button_frame.winfo_children():
                widget.destroy()

            # Add buttons
            tk.Button(
                loading_dialog.button_frame,
                text="🔄 Retry",
                command=retry_query,
                bg="#f39c12",
                fg="white",
                font=("Arial", 9, "bold"),
                padx=15,
                pady=5,
            ).pack(side="left", padx=5)

            tk.Button(
                loading_dialog.button_frame,
                text="📋 Show Details",
                command=show_error_details,
                bg="#3498db",
                fg="white",
                font=("Arial", 9, "bold"),
                padx=15,
                pady=5,
            ).pack(side="left", padx=5)

            tk.Button(
                loading_dialog.button_frame,
                text="❌ Close",
                command=close_dialog,
                bg="#95a5a6",
                fg="white",
                font=("Arial", 9, "bold"),
                padx=15,
                pady=5,
            ).pack(side="left", padx=5)

            # Update results text with error
            self.results_text.delete("1.0", tk.END)
            self.results_text.insert(tk.END, "❌ QUERY ERROR\n")
            self.results_text.insert(tk.END, "=" * 150 + "\n\n")
            self.results_text.insert(tk.END, f"Error Type: {error_details['type']}\n")
            self.results_text.insert(tk.END, f"Error Message: {error_details['message']}\n\n")

            if self.debug_mode.get():
                self.results_text.insert(tk.END, "Debug Traceback:\n")
                self.results_text.insert(tk.END, "-" * 150 + "\n")
                self.results_text.insert(tk.END, error_details["traceback"])
                self.results_text.insert(tk.END, "\n" + "=" * 150 + "\n")

            self.results_text.see(tk.END)

        except Exception as e:
            print(f"Error in error handler: {e}")
            traceback.print_exc()
            loading_dialog.destroy()
            self.execute_btn.config(state="normal", text="▶  Run")

    def _show_error_details_dialog(self, error_details):
        """NEW: Show comprehensive error details dialog"""
        dialog = tk.Toplevel(self.root)
        dialog.title("🐛 Error Details")
        dialog.geometry("900x700")
        dialog.configure(bg="#f0f0f0")
        dialog.transient(self.root)
        dialog.grab_set()

        # Content frame
        content_frame = tk.Frame(dialog, bg="#ffffff", relief="solid", bd=1)
        content_frame.pack(fill="both", expand=True, padx=15, pady=15)

        # Title
        tk.Label(
            content_frame,
            text="🐛 Query Execution Error Details",
            font=("Arial", 14, "bold"),
            bg="#ffffff",
            fg="#e74c3c",
        ).pack(pady=(10, 15))

        # Error summary
        summary_frame = tk.LabelFrame(
            content_frame,
            text="Error Summary",
            font=("Arial", 11, "bold"),
            bg="#ffffff",
            fg="#2c3e50",
        )
        summary_frame.pack(fill="both", padx=10, pady=(0, 10))

        tk.Label(
            summary_frame,
            text=f"Type: {error_details['type']}",
            font=("Arial", 10),
            bg="#ffffff",
            fg="#2c3e50",
            anchor="w",
        ).pack(fill="both", padx=10, pady=5)

        tk.Label(
            summary_frame,
            text=f"Message: {error_details['message']}",
            font=("Arial", 10),
            bg="#ffffff",
            fg="#e74c3c",
            anchor="w",
            wraplength=850,
        ).pack(fill="both", padx=10, pady=5)

        # Query that failed
        query_frame = tk.LabelFrame(
            content_frame,
            text="Failed Query",
            font=("Arial", 11, "bold"),
            bg="#ffffff",
            fg="#2c3e50",
        )
        query_frame.pack(fill="both", padx=10, pady=(0, 10))

        query_text = tk.Text(query_frame, height=4, font=("Courier", 9), bg="#f8f9fa", wrap=tk.WORD)
        query_text.pack(fill="both", padx=10, pady=10)
        query_text.insert(1.0, error_details["query"])
        query_text.config(state="disabled")

        # Full traceback
        traceback_frame = tk.LabelFrame(
            content_frame,
            text="Full Traceback (for debugging)",
            font=("Arial", 11, "bold"),
            bg="#ffffff",
            fg="#e67e22",
        )
        traceback_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        traceback_scroll = tk.Scrollbar(traceback_frame)
        traceback_scroll.pack(side="right", fill="y")

        traceback_text = tk.Text(
            traceback_frame,
            font=("Courier", 8),
            height=14,
            bg="#f8f9fa",
            wrap=tk.WORD,
            yscrollcommand=traceback_scroll.set,
        )
        traceback_text.pack(side="left", fill="both", expand=True, padx=10, pady=10)
        traceback_scroll.config(command=traceback_text.yview)

        traceback_text.insert(1.0, error_details["traceback"])
        traceback_text.config(state="disabled")

        # Buttons
        button_frame = tk.Frame(content_frame, bg="#ffffff")
        button_frame.pack(fill="both", padx=10, pady=(0, 10))

        def copy_error():
            error_report = f"Error Type: {error_details['type']}\n"
            error_report += f"Error Message: {error_details['message']}\n\n"
            error_report += f"Query:\n{error_details['query']}\n\n"
            error_report += f"Traceback:\n{error_details['traceback']}"

            self.root.clipboard_clear()
            self.root.clipboard_append(error_report)
            messagebox.showinfo("Copied", "Error details copied to clipboard!", parent=dialog)

        tk.Button(
            button_frame,
            text="📋 Copy Error Details",
            command=copy_error,
            bg="#3498db",
            fg="white",
            font=("Arial", 10, "bold"),
            padx=20,
            pady=6,
        ).pack(side="left")

        tk.Button(
            button_frame,
            text="❌ Close",
            command=dialog.destroy,
            bg="#95a5a6",
            fg="white",
            font=("Arial", 10, "bold"),
            padx=20,
            pady=6,
        ).pack(side="right")

    # UPDATED: Enhanced table data selection dialog with multiple columns and raw data option
    def show_table_data_selection_dialog(self, tables):
        """Show dialog to select table and column(s) for data extraction - ENHANCED: Multiple columns + raw data"""
        dialog = tk.Toplevel(self.root)
        dialog.title("📊 Select Table Column Data")
        dialog.geometry("1100x800")
        dialog.configure(bg="#f0f0f0")
        dialog.transient(self.root)
        dialog.grab_set()

        # Center dialog
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - (dialog.winfo_width() // 2)
        y = (dialog.winfo_screenheight() // 2) - (dialog.winfo_height() // 2)
        dialog.geometry(f"+{x}+{y}")

        # Content frame
        content_frame = tk.Frame(dialog, bg="#ffffff", relief="solid", bd=1)
        content_frame.pack(fill="both", expand=True, padx=15, pady=15)

        # Title
        tk.Label(
            content_frame,
            text="📊 Select Table Column Data for SQL",
            font=("Arial", 14, "bold"),
            bg="#ffffff",
            fg="#2c3e50",
        ).pack(pady=(10, 15))

        # Info section
        info_frame = tk.Frame(content_frame, bg="#e8f4f8", relief="solid", bd=1)
        info_frame.pack(fill="both", pady=(0, 15))

        phase = self.loaded_table_data.get("phase", "N/A")
        timestamp = self.loaded_table_data.get("timestamp", "N/A")

        info_text = f"📋 Phase: {phase} | 🕒 Exported: {timestamp} | 📊 Tables: {len(tables)}"

        tk.Label(
            info_frame,
            text=info_text,
            font=("Arial", 10),
            bg="#e8f4f8",
            fg="#2c3e50",
            justify="center",
        ).pack(pady=8, padx=10)

        # Main content - Split into left and right
        main_content = tk.Frame(content_frame, bg="#ffffff")
        main_content.pack(fill="both", expand=True, pady=(0, 15))

        # LEFT SIDE - Table and Column Selection
        left_frame = tk.Frame(main_content, bg="#ffffff")
        left_frame.pack(side="left", fill="both", expand=True, padx=(10, 5))

        # Table selection
        table_frame = tk.LabelFrame(
            left_frame,
            text="1️⃣ Select Table",
            font=("Arial", 11, "bold"),
            bg="#ffffff",
            fg="#27ae60",
        )
        table_frame.pack(fill="both", pady=(0, 10))

        table_list_frame = tk.Frame(table_frame, bg="#ffffff")
        table_list_frame.pack(fill="both", padx=10, pady=10)

        table_scrollbar = tk.Scrollbar(table_list_frame, orient="vertical")
        table_scrollbar.pack(side="right", fill="y")

        table_listbox = tk.Listbox(
            table_list_frame,
            yscrollcommand=table_scrollbar.set,
            font=("Arial", 10),
            height=6,
            selectmode=tk.SINGLE,
            exportselection=False,
            bg="white",
            selectbackground="#3498db",
            selectforeground="white",
            activestyle="dotbox",
        )
        table_listbox.pack(side="left", fill="both", expand=True)
        table_scrollbar.config(command=table_listbox.yview)

        # Populate tables
        table_names = list(tables.keys())
        for table_name in table_names:
            table_info = tables[table_name]
            table_listbox.insert("end", f"{table_name} ({table_info['columns']} columns)")

        # Column selection with multiple selection
        column_frame = tk.LabelFrame(
            left_frame,
            text="2️⃣ Select Column(s)",
            font=("Arial", 11, "bold"),
            bg="#ffffff",
            fg="#3498db",
        )
        column_frame.pack(fill="both", expand=True, pady=(0, 10))

        # NEW: Multiple selection controls
        column_control_frame = tk.Frame(column_frame, bg="#ffffff")
        column_control_frame.pack(fill="both", padx=10, pady=(10, 5))

        tk.Label(
            column_control_frame,
            text="💡 Ctrl+Click for multiple columns",
            font=("Arial", 9, "italic"),
            bg="#ffffff",
            fg="#7f8c8d",
        ).pack(side="left")

        def select_all_columns():
            column_listbox.select_set(0, tk.END)
            update_preview()

        def clear_all_columns():
            column_listbox.selection_clear(0, tk.END)
            update_preview()

        tk.Button(
            column_control_frame,
            text="✅ Select All",
            command=select_all_columns,
            bg="#27ae60",
            fg="white",
            font=("Arial", 8, "bold"),
            padx=8,
            pady=2,
        ).pack(side="right", padx=(5, 0))

        tk.Button(
            column_control_frame,
            text="❌ Clear",
            command=clear_all_columns,
            bg="#e74c3c",
            fg="white",
            font=("Arial", 8, "bold"),
            padx=8,
            pady=2,
        ).pack(side="right")

        column_list_frame = tk.Frame(column_frame, bg="#ffffff")
        column_list_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        column_scrollbar = tk.Scrollbar(column_list_frame, orient="vertical")
        column_scrollbar.pack(side="right", fill="y")

        # UPDATED: Multiple selection mode
        column_listbox = tk.Listbox(
            column_list_frame,
            yscrollcommand=column_scrollbar.set,
            font=("Arial", 10),
            height=8,
            selectmode=tk.EXTENDED,  # Changed to EXTENDED for multiple selection
            exportselection=False,
            bg="white",
            selectbackground="#3498db",
            selectforeground="white",
            activestyle="dotbox",
        )
        column_listbox.pack(side="left", fill="both", expand=True)
        column_scrollbar.config(command=column_listbox.yview)

        # RIGHT SIDE - Preview and Options
        right_frame = tk.Frame(main_content, bg="#ffffff")
        right_frame.pack(side="right", fill="both", expand=True, padx=(5, 10))

        # NEW: Insert mode selection
        mode_frame = tk.LabelFrame(
            right_frame,
            text="⚙️ Insert Mode",
            font=("Arial", 11, "bold"),
            bg="#ffffff",
            fg="#9b59b6",
        )
        mode_frame.pack(fill="both", pady=(0, 10))

        insert_mode_var = tk.StringVar(value="variable")

        mode_options_frame = tk.Frame(mode_frame, bg="#ffffff")
        mode_options_frame.pack(fill="both", padx=10, pady=10)

        tk.Radiobutton(
            mode_options_frame,
            text="🔤 As Variable (replaceable)",
            variable=insert_mode_var,
            value="variable",
            font=("Arial", 9),
            bg="#ffffff",
        ).pack(anchor="w", pady=2)

        tk.Radiobutton(
            mode_options_frame,
            text="📝 As Raw Data (direct values)",
            variable=insert_mode_var,
            value="raw",
            font=("Arial", 9),
            bg="#ffffff",
        ).pack(anchor="w", pady=2)

        tk.Label(
            mode_frame,
            text="💡 Variable mode: Insert {TABLE_NAME_COLUMN}\n"
            "💡 Raw data mode: Insert actual values directly",
            font=("Arial", 8, "italic"),
            bg="#ffffff",
            fg="#7f8c8d",
            justify="left",
        ).pack(anchor="w", padx=10, pady=(0, 10))

        # Preview
        preview_frame = tk.LabelFrame(
            right_frame,
            text="👁️ Data Preview",
            font=("Arial", 11, "bold"),
            bg="#ffffff",
            fg="#e67e22",
        )
        preview_frame.pack(fill="both", expand=True)

        preview_text_frame = tk.Frame(preview_frame, bg="#ffffff")
        preview_text_frame.pack(fill="both", expand=True, padx=10, pady=10)

        preview_scrollbar = tk.Scrollbar(preview_text_frame)
        preview_scrollbar.pack(side="right", fill="y")

        preview_text = tk.Text(
            preview_text_frame,
            height=20,
            font=("Courier", 9),
            bg="#f8f9fa",
            state="disabled",
            wrap=tk.WORD,
            yscrollcommand=preview_scrollbar.set,
        )
        preview_text.pack(side="left", fill="both", expand=True)
        preview_scrollbar.config(command=preview_text.yview)

        # Update preview function
        def update_preview(event=None):
            table_selection = table_listbox.curselection()
            column_selections = column_listbox.curselection()

            if not table_selection:
                preview_text.configure(state="normal")
                preview_text.delete(1.0, tk.END)
                preview_text.insert(tk.END, "Please select a table first")
                preview_text.configure(state="disabled")
                return

            selected_table = table_names[table_selection[0]]
            table_data = tables[selected_table]
            column_data_dict = table_data.get("column_data", {})

            if not column_selections:
                preview_text.configure(state="normal")
                preview_text.delete(1.0, tk.END)
                preview_text.insert(tk.END, f"Table: {selected_table}\n")
                preview_text.insert(tk.END, f"{'='*60}\n\n")
                preview_text.insert(tk.END, f"Available Columns: {len(column_data_dict)}\n\n")
                for col_name in column_data_dict.keys():
                    preview_text.insert(tk.END, f"• {col_name}\n")
                preview_text.insert(tk.END, "\n💡 Select column(s) to see preview")
                preview_text.configure(state="disabled")
                return

            # Get selected columns
            column_names = list(column_data_dict.keys())
            selected_columns = [column_names[i] for i in column_selections]

            # Update preview
            preview_text.configure(state="normal")
            preview_text.delete(1.0, tk.END)

            preview_text.insert(tk.END, f"Table: {selected_table}\n")
            preview_text.insert(tk.END, f"Selected: {len(selected_columns)} column(s)\n")
            preview_text.insert(tk.END, f"{'='*60}\n\n")

            insert_mode = insert_mode_var.get()

            for col_name in selected_columns:
                column_values = column_data_dict[col_name]
                preview_text.insert(tk.END, f"Column: {col_name}\n")
                preview_text.insert(tk.END, f"Values: {len(column_values)}\n")
                preview_text.insert(tk.END, f"{'-'*60}\n")

                # Show first 5 values
                for i, value in enumerate(column_values[:5], 1):
                    preview_text.insert(tk.END, f"  {i}. {value}\n")

                if len(column_values) > 5:
                    preview_text.insert(tk.END, f"  ... ({len(column_values) - 5} more)\n")

                # Show what will be inserted
                preview_text.insert(tk.END, f"\n📝 Will insert:\n")

                if insert_mode == "variable":
                    safe_table_name = selected_table.upper().replace(" ", "_").replace("-", "_")
                    safe_col_name = col_name.upper().replace(" ", "_").replace("-", "_")
                    variable_name = f"{{TABLE_{safe_table_name}_{safe_col_name}}}"
                    preview_text.insert(tk.END, f"  Variable: {variable_name}\n")
                else:
                    values_str = ", ".join(
                        [f"'{v}'" if isinstance(v, str) else str(v) for v in column_values[:3]]
                    )
                    if len(column_values) > 3:
                        values_str += ", ..."
                    preview_text.insert(tk.END, f"  Raw data: {values_str}\n")

                preview_text.insert(tk.END, f"\n{'─'*60}\n\n")

            preview_text.configure(state="disabled")

        # Update column list when table selection changes
        def on_table_select(event):
            column_listbox.delete(0, tk.END)

            table_selection = table_listbox.curselection()
            if not table_selection:
                return

            selected_table = table_names[table_selection[0]]
            table_data = tables[selected_table]
            column_data_dict = table_data.get("column_data", {})

            # Populate columns
            for col_name, col_values in column_data_dict.items():
                column_listbox.insert("end", f"{col_name} ({len(col_values)} values)")

            update_preview()

        # Bind selection events
        table_listbox.bind("<<ListboxSelect>>", on_table_select)
        column_listbox.bind("<<ListboxSelect>>", update_preview)
        table_listbox.bind("<ButtonRelease-1>", on_table_select)
        column_listbox.bind("<ButtonRelease-1>", update_preview)

        # Also bind to radio button changes
        insert_mode_var.trace_add("write", lambda *args: update_preview())

        # Auto-select first table
        if table_names:
            table_listbox.selection_set(0)
            table_listbox.event_generate("<<ListboxSelect>>")
            on_table_select(None)

        # Buttons
        button_frame = tk.Frame(content_frame, bg="#ffffff")
        button_frame.pack(fill="both", pady=(0, 10))

        def insert_data():
            table_selection = table_listbox.curselection()
            column_selections = column_listbox.curselection()

            if not table_selection or not column_selections:
                messagebox.showwarning(
                    "No Selection", "Please select table and column(s)", parent=dialog
                )
                return

            selected_table = table_names[table_selection[0]]
            table_data = tables[selected_table]
            column_data_dict = table_data.get("column_data", {})

            column_names = list(column_data_dict.keys())
            selected_columns = [column_names[i] for i in column_selections]

            insert_mode = insert_mode_var.get()
            cursor_pos = self.sql_context.index(tk.INSERT)

            inserted_items = []

            for col_name in selected_columns:
                column_values = column_data_dict[col_name]

                if insert_mode == "variable":
                    # Insert as variable
                    safe_table_name = selected_table.upper().replace(" ", "_").replace("-", "_")
                    safe_col_name = col_name.upper().replace(" ", "_").replace("-", "_")
                    variable_name = f"{{TABLE_{safe_table_name}_{safe_col_name}}}"

                    self.sql_context.insert(cursor_pos, variable_name + " ")
                    inserted_items.append(f"Variable: {variable_name}")
                else:
                    # Insert as raw data
                    values_str = ", ".join(
                        [f"'{v}'" if isinstance(v, str) else str(v) for v in column_values]
                    )

                    self.sql_context.insert(cursor_pos, values_str + " ")
                    preview_str = values_str[:100] + "..." if len(values_str) > 100 else values_str
                    inserted_items.append(f"Raw data from {col_name}: {preview_str}")

            # Show success message
            success_msg = f"✅ Inserted {len(selected_columns)} column(s)!\n\n"
            success_msg += "\n".join(inserted_items)

            if insert_mode == "variable":
                success_msg += "\n\n💡 Use 'Replace Variables' if needed"

            messagebox.showinfo("Data Inserted", success_msg, parent=dialog)
            dialog.destroy()

        tk.Button(
            button_frame,
            text="📝 Insert Data",
            command=insert_data,
            bg="#27ae60",
            fg="white",
            font=("Arial", 10, "bold"),
            padx=20,
            pady=6,
        ).pack(side="left")

        cancel_btn = tk.Button(
            button_frame,
            text="✖ Cancel",
            width=12,
            height=2,
            bg="#95a5a6",
            fg="white",
            font=("Arial", 10, "bold"),
            command=dialog.destroy,
        )

        cancel_btn.pack(side="left", padx=5)

    def get_connection_string(self, db_type, user, password, host, port, database):
        """Generate connection string based on database type"""
        # URL encode password to handle special characters
        from urllib.parse import quote_plus

        encoded_password = quote_plus(password)

        # Clean port - ensure it's just the number
        port_clean = port.strip().split(":")[0] if ":" in port else port.strip()

        if db_type == "PostgreSQL":
            if database:
                return (
                    f"postgresql+pg8000://{user}:{encoded_password}@{host}:{port_clean}/{database}"
                )
            else:
                return f"postgresql+pg8000://{user}:{encoded_password}@{host}:{port_clean}"
        elif db_type == "MySQL":
            if database:
                return f"mysql+pymysql://{user}:{encoded_password}@{host}:{port_clean}/{database}"
            else:
                return f"mysql+pymysql://{user}:{encoded_password}@{host}:{port_clean}"
        elif db_type == "Microsoft SQL Server":
            # Use ODBC connection string format to avoid DSN length issues
            if database:
                conn_str = f"DRIVER={{SQL Server}};SERVER={host},{port_clean};DATABASE={database};UID={user};PWD={password}"
            else:
                # Connect to master database by default when no database specified
                # This allows querying all databases in the server
                conn_str = f"DRIVER={{SQL Server}};SERVER={host},{port_clean};DATABASE=master;UID={user};PWD={password}"
            return f"mssql+pyodbc:///?odbc_connect={quote_plus(conn_str)}"
        elif db_type == "Oracle":
            # Oracle connection string format - use oracledb (thin mode - no Oracle Client needed)
            # Clean host in case it contains port
            host_clean = host.split(":")[0] if ":" in host else host
            if database:
                # Use oracledb format: host:port/service_name
                return f"oracle+oracledb://{user}:{encoded_password}@{host_clean}:{port_clean}/?service_name={database}"
            else:
                return f"oracle+oracledb://{user}:{encoded_password}@{host_clean}:{port_clean}"
        else:
            raise ValueError(f"Unsupported database type: {db_type}")

    def get_connect_args(self, db_type):
        if db_type == "PostgreSQL":
            return {"timeout": 10}
        if db_type == "MySQL":
            return {"connect_timeout": 10}
        if db_type == "Microsoft SQL Server":
            return {"timeout": 10}
        return {}

    def connect_database(self):
        db_type = self.db_type.get()
        user = self.db_user.get()
        password = self.db_password.get()
        host = self.db_host.get()
        port = self.db_port.get().strip().split(":")[0]
        database = self.db_name.get()
        self.db_port.delete(0, tk.END)
        self.db_port.insert(0, port)

        if not all((db_type, user, password, host, port)):
            messagebox.showerror(
                "Error", "Please fill in all connection fields (Database is optional)"
            )
            return

        try:
            self.results_text.insert(tk.END, f"Connecting to {db_type} database...\n")
            self.results_text.see(tk.END)
            connection_string = self.get_connection_string(
                db_type, user, password, host, port, database
            )
            self.engine = create_engine(
                connection_string,
                connect_args=self.get_connect_args(db_type),
                # Check a pooled connection before each use and reconnect if the
                # server/firewall dropped it while idle (e.g. ORA-03113, DPI-1080)
                pool_pre_ping=True,
                # Never reuse a connection older than 30 minutes
                pool_recycle=1800,
            )
            self._track_engine_connections(self.engine)
            with self.engine.connect() as connection:
                connection.execute(
                    text("SELECT 1 FROM DUAL" if db_type == "Oracle" else "SELECT 1")
                )

            self.status_label.config(text=f"✅ Connected ({db_type})", foreground="#27ae60")
            self.execute_btn.config(state="normal")
            self.inspect_btn.config(state="normal")
            db_info = f"{db_type} database" + (f": {database}" if database else "")
            self.results_text.insert(tk.END, f"✅ Successfully connected to {db_info}\n\n")
            self.results_text.see(tk.END)
            messagebox.showinfo("Success", f"Connected to {db_type} database successfully!")
        except Exception as error:
            self.status_label.config(text="❌ Connection Failed", foreground="#e74c3c")
            self.results_text.insert(tk.END, f"❌ Connection Error: {error}\n\n")
            self.results_text.see(tk.END)
            self._show_connection_error(error)

    def _show_connection_error(self, error):
        """Connection failed: show the database message and what to check."""
        profile = self.profile_combo.get() or "-"

        def body(frame):
            _box_outer, box = ui_round_frame(frame, fill=UI["danger_soft"], radius=8, pad=2)
            _box_outer.pack(fill="x")
            msg = str(error).strip()
            tk.Label(box, text=msg if len(msg) <= 400 else msg[:399] + "…", bg=UI["danger_soft"],
                     fg=UI["danger"], font=("Consolas", 9), anchor="w", justify="left",
                     wraplength=470).pack(fill="x", padx=12, pady=10)
            tk.Label(frame, text="ลองตรวจสอบ", bg=UI["card"], fg=UI["muted"], font=UI_FONT_LABEL,
                     anchor="w").pack(fill="x", pady=(12, 2))
            for tip in ("•  User / Password ถูกต้อง และยังไม่หมดอายุ",
                        "•  Host, Port และ Database / Service Name",
                        "•  ต่อ VPN / network ของธนาคารอยู่"):
                tk.Label(frame, text=tip, bg=UI["card"], fg=UI["text"], font=UI_FONT,
                         anchor="w").pack(fill="x")

        choice = ui_dialog(
            self.root,
            "Connection Error",
            "เชื่อมต่อฐานข้อมูลไม่สำเร็จ",
            f"Profile {profile} ต่อ {self.db_type.get()} ไม่ได้ ข้อความจากฐานข้อมูล:",
            tone="danger",
            build_body=body,
            buttons=(("แก้ไขข้อมูลเชื่อมต่อ", "edit", "secondary"), ("↻  ลองใหม่", "retry", "primary")),
            cancel_value=None,
            message=str(error),
        )
        if choice == "edit" and not getattr(self, "creds_expanded", True):
            self.creds_toggle_btn.invoke()
        elif choice == "retry":
            self.root.after(50, self.connect_database)

    def read_sql_dataframe(self, sql_query):
        """Run a SELECT through the driver cursor and keep values as returned.

        Unlike pd.read_sql_query this keeps column names exactly as the
        database sends them (Oracle: upper case), fetches Oracle NUMBER as
        Decimal (no float rounding of long numbers), reads LOBs as text and
        keeps NULL as None — so the result matches DBeaver.
        """
        sql = sql_query.strip()
        # DBeaver accepts a trailing ';' or '/', the driver does not
        while sql.endswith(";") or (sql.endswith("/") and not sql.endswith("*/")):
            sql = sql[:-1].rstrip()

        raw_connection = self.engine.raw_connection()
        try:
            dbapi_connection = getattr(raw_connection, "driver_connection", None) or raw_connection
            cursor = raw_connection.cursor()
            try:
                if self.engine.dialect.name == "oracle":
                    import oracledb

                    def _output_type_handler(cur, metadata):
                        type_code = metadata.type_code
                        if type_code is oracledb.DB_TYPE_NUMBER:
                            return cur.var(decimal.Decimal, arraysize=cur.arraysize)
                        if type_code is oracledb.DB_TYPE_CLOB:
                            return cur.var(oracledb.DB_TYPE_LONG, arraysize=cur.arraysize)
                        if type_code is oracledb.DB_TYPE_NCLOB:
                            return cur.var(oracledb.DB_TYPE_LONG_NVARCHAR, arraysize=cur.arraysize)
                        if type_code is oracledb.DB_TYPE_BLOB:
                            return cur.var(oracledb.DB_TYPE_LONG_RAW, arraysize=cur.arraysize)
                        return None

                    driver_cursor = getattr(cursor, "cursor", cursor)
                    try:
                        driver_cursor.outputtypehandler = _output_type_handler
                    except AttributeError:
                        dbapi_connection.outputtypehandler = _output_type_handler
                    driver_cursor.arraysize = 1000

                cursor.execute(sql)
                if cursor.description is None:
                    return pd.DataFrame()
                columns = [str(column[0]) for column in cursor.description]
                rows = cursor.fetchall()
            finally:
                cursor.close()
        finally:
            raw_connection.close()

        df = (
            pd.DataFrame(list(rows), columns=columns, dtype=object)
            if rows
            else pd.DataFrame(columns=columns, dtype=object)
        )
        return df

    def is_select_query(self, query):
        """Check if query is a SELECT statement"""
        query_upper = query.strip().upper()
        # Remove comments
        query_upper = " ".join(
            [line for line in query_upper.split("\n") if not line.strip().startswith("--")]
        )
        # Check if it starts with SELECT, WITH (for CTEs), or contains SELECT in first word
        return (
            query_upper.startswith("SELECT")
            or query_upper.startswith("WITH")
            or query_upper.startswith("(SELECT")
        )

    def _app_settings_path(self):
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), "app_settings.json")

    def _load_app_settings(self):
        try:
            with open(self._app_settings_path(), "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _save_app_setting(self, key, value):
        settings = self._load_app_settings()
        settings[key] = value
        try:
            with open(self._app_settings_path(), "w", encoding="utf-8") as f:
                json.dump(settings, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Cannot save app_settings.json: {e}")

    def _result_windows_checkbox(self, parent, bg):
        """Checkbox bound to the shared 'open result windows' setting."""
        cb = tk.Checkbutton(
            parent,
            text="Open result windows",
            variable=self.open_result_popups,
            bg=bg,
            activebackground=bg,
            selectcolor="#FFFFFF",
            font=UI_FONT_SM,
            bd=0,
            highlightthickness=0,
            cursor="hand2",
        )
        ui_round_check(cb)
        return cb

    def _track_engine_connections(self, engine):
        """Remember which DB connections are in use, so Stop can cancel them."""
        from sqlalchemy import event

        with self._active_db_lock:
            self._active_db_connections.clear()

        def _on_checkout(dbapi_connection, _record, _proxy):
            with self._active_db_lock:
                self._active_db_connections.add(dbapi_connection)

        def _on_checkin(dbapi_connection, _record):
            with self._active_db_lock:
                self._active_db_connections.discard(dbapi_connection)

        event.listen(engine, "checkout", _on_checkout)
        event.listen(engine, "checkin", _on_checkin)

    def _is_query_running(self):
        with self._active_db_lock:
            busy = bool(self._active_db_connections)
        return (
            busy
            or getattr(self, "_batch_running", False)
            or "Loading" in str(self.execute_btn.cget("text"))
            or "Exporting" in str(self.export_excel_btn.cget("text"))
        )

    def _start_stoppable_run(self):
        """Called when a run starts: forget any earlier Stop request."""
        self._stop_event.clear()
        self._log_run_context()

    # ---------------------------------------------------------------
    # Run log file (logs/run_YYYY-MM-DD.log) — never contains passwords
    # ---------------------------------------------------------------
    RUN_LOG_KEEP_DAYS = 90

    def _init_run_log(self):
        self._log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
        self._log_buffer = ""
        self._log_lock = threading.Lock()
        try:
            os.makedirs(self._log_dir, exist_ok=True)
            # Remove log files older than RUN_LOG_KEEP_DAYS
            cutoff = _dt.datetime.now().timestamp() - self.RUN_LOG_KEEP_DAYS * 86400
            for name in os.listdir(self._log_dir):
                path = os.path.join(self._log_dir, name)
                if name.startswith("run_") and name.endswith(".log") and os.path.getmtime(path) < cutoff:
                    os.remove(path)
        except Exception as e:
            print(f"Run log: {e}")
        self._refresh_log_file_label()

    def _run_log_path(self):
        return os.path.join(self._log_dir, f"run_{_dt.date.today():%Y-%m-%d}.log")

    def _refresh_log_file_label(self):
        label = getattr(self, "_log_file_label", None)
        if label is not None:
            label.config(text=f"Saved to logs\\{os.path.basename(self._run_log_path())}")

    def _write_run_log(self, text_value):
        """Append complete lines (timestamped) to today's log file."""
        if not hasattr(self, "_log_lock"):
            return
        with self._log_lock:
            self._log_buffer += text_value
            if "\n" not in self._log_buffer:
                return
            *lines, self._log_buffer = self._log_buffer.split("\n")
            stamp = _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            out = []
            for line in lines:
                line = line.rstrip()
                if not line:
                    continue
                if set(line) <= set("=─-━"):
                    line = "-" * 40  # shorten long separator lines
                out.append(f"{stamp} | {line}\n")
            if not out:
                return
            try:
                with open(self._run_log_path(), "a", encoding="utf-8") as f:
                    f.writelines(out)
            except Exception as e:
                print(f"Run log: cannot write: {e}")
        self._refresh_log_file_label()

    def _log_run_context(self):
        """Log who/where a run goes to (profile and target, no password)."""
        try:
            user = self.db_user.get().strip()
            host = self.db_host.get().strip()
            port = self.db_port.get().strip()
            database = self.db_name.get().strip()
            target = f"{user}@{host}" + (f":{port}" if port else "") + (f"/{database}" if database else "")
            self._write_run_log(
                f"\n===== RUN  profile={self.profile_combo.get() or '-'}  "
                f"{self.db_type.get()}  {target} =====\n"
            )
        except tk.TclError:
            pass

    def open_log_folder(self):
        try:
            os.makedirs(self._log_dir, exist_ok=True)
            os.startfile(self._log_dir)
        except Exception as e:
            messagebox.showerror("Logs", f"Cannot open log folder:\n{self._log_dir}\n\n{e}")

    def stop_running_queries(self):
        """Stop button: cancel the query in progress and skip remaining jobs."""
        if not self._is_query_running():
            return
        self._stop_event.set()
        with self._active_db_lock:
            connections = list(self._active_db_connections)
        cancelled = 0
        for dbapi_connection in connections:
            cancel = getattr(dbapi_connection, "cancel", None)  # Oracle (python-oracledb)
            if cancel is None:
                continue
            try:
                cancel()
                cancelled += 1
            except Exception as e:
                print(f"Stop: cancel failed: {e}")
        if cancelled:
            msg = f"\n⏹ Stop requested — cancelled {cancelled} running query(ies); remaining jobs are skipped.\n"
        else:
            msg = (
                "\n⏹ Stop requested — remaining jobs are skipped. "
                "This database driver cannot cancel a running query, so the current one finishes first.\n"
            )
        self.results_text.insert(tk.END, msg)
        self.results_text.see(tk.END)

    def _register_stop_button(self, button):
        self._stop_buttons.append(button)
        button.config(state="disabled")

    def _refresh_stop_buttons(self):
        """Poll: Stop buttons are enabled only while something runs."""
        try:
            state = "normal" if self._is_query_running() else "disabled"
            alive = []
            for button in self._stop_buttons:
                try:
                    if button.winfo_exists():
                        if str(button["state"]) != state:
                            button.config(state=state)
                        alive.append(button)
                except tk.TclError:
                    pass
            self._stop_buttons = alive
        except tk.TclError:
            return
        self.root.after(300, self._refresh_stop_buttons)

    def _confirm_data_change(self, jobs):
        """Ask before running statements that are not SELECT (they are committed).

        jobs: list of {"name", "query"}. Returns True when nothing needs
        confirming or the user agreed; SELECT-only runs are never prompted.
        """
        changes = [job for job in jobs if not self.is_select_query(job.get("query", ""))]
        if not changes:
            return True

        target = self.db_type.get()
        host = self.db_host.get().strip()
        database = self.db_name.get().strip()
        if host:
            target += f" · {host}" + (f" / {database}" if database else "")

        lines = []
        for job in changes[:10]:
            first_line = " ".join(str(job.get("query", "")).split())[:70]
            lines.append(f"• {job.get('name') or 'SQL Editor'}:  {first_line}")
        if len(changes) > 10:
            lines.append(f"... and {len(changes) - 10} more")
        profile = self.profile_combo.get() or "-"

        def body(frame):
            _box_outer, box = ui_round_frame(frame, fill="#FEF3C7", radius=8, pad=2)
            _box_outer.pack(fill="x")
            for job in changes[:6]:
                tk.Label(box, text=job.get("name") or "SQL Editor", bg="#FEF3C7", fg=UI["text"],
                         font=UI_FONT_SEMI, anchor="w").pack(fill="x", padx=12, pady=(8, 0))
                sql = " ".join(str(job.get("query", "")).split())
                tk.Label(box, text=sql if len(sql) <= 90 else sql[:89] + "…", bg="#FEF3C7",
                         fg=UI["muted"], font=("Consolas", 9), anchor="w").pack(fill="x", padx=12)
            if len(changes) > 6:
                tk.Label(box, text=f"… และอีก {len(changes) - 6} คำสั่ง", bg="#FEF3C7",
                         fg=UI["muted"], font=UI_FONT_SM, anchor="w").pack(fill="x", padx=12)
            tk.Frame(box, bg="#FEF3C7", height=8).pack()
            info = tk.Frame(frame, bg=UI["card"])
            info.pack(fill="x", pady=(12, 0))
            for r, (k, v) in enumerate((("Profile", profile), ("Database", target))):
                tk.Label(info, text=k, bg=UI["card"], fg=UI["muted"], font=UI_FONT_SM).grid(
                    row=r, column=0, sticky="w", padx=(0, 16), pady=1)
                tk.Label(info, text=v, bg=UI["card"], fg=UI["text"], font=UI_FONT_SEMI).grid(
                    row=r, column=1, sticky="w", pady=1)
            tk.Label(frame, text="ⓘ  ย้อนกลับไม่ได้หลัง commit", bg=UI["card"], fg=UI["danger"],
                     font=UI_FONT_SM, anchor="w").pack(fill="x", pady=(10, 0))

        return bool(ui_dialog(
            self.root,
            "Confirm Data Change",
            "ยืนยันการแก้ไขข้อมูล",
            f"มี {len(changes)} คำสั่งที่จะแก้ไขข้อมูลและ commit ทันที ตรวจสอบก่อนกดรัน",
            tone="warn",
            build_body=body,
            buttons=(("ยกเลิก", False, "secondary"), ("▶  รันและ commit", True, "danger")),
            cancel_value=False,
            focus_value=False,
            message=f"{len(changes)} statement(s) will CHANGE DATA and be committed immediately:\n\n"
            + "\n".join(lines)
            + f"\n\nProfile : {profile}\nDatabase: {target}",
        ))

    def execute_query(self):
        """Execute the SQL query with comprehensive error handling and retry capability"""
        if not self.engine:
            messagebox.showerror("Error", "Please connect to database first")
            return

        sql_query = self.sql_context.get(1.0, tk.END).strip()
        if not sql_query:
            messagebox.showerror("Error", "Please enter a SQL query")
            return

        if not self._confirm_data_change([{"name": None, "query": sql_query}]):
            return
        self._start_stoppable_run()

        # Show loading message
        self.results_text.delete("1.0", tk.END)
        self.results_text.insert(tk.END, f"⏳ Executing query...\n")
        self.results_text.insert(tk.END, f"SQL: {sql_query}\n\n")
        self.results_text.insert(tk.END, "⚠️ Please wait, loading data...\n")
        self.results_text.see(tk.END)

        # Disable execute button to prevent multiple clicks
        self.execute_btn.config(state="disabled", text="⏳ Loading...")
        self.root.update()

        # Create loading dialog with retry button
        loading_dialog = self._create_loading_dialog_with_retry(sql_query)

        # Execute query in background thread
        self._execute_query_background(sql_query, loading_dialog)

    def on_modification_success(self, rows_affected, sql_query, loading_dialog):
        """Handle successful UPDATE/INSERT/DELETE execution"""
        try:
            # Close loading dialog
            loading_dialog.destroy()

            # Determine operation type
            query_upper = sql_query.strip().upper()
            if query_upper.startswith("UPDATE"):
                operation = "UPDATE"
                icon = "✏️"
            elif query_upper.startswith("INSERT"):
                operation = "INSERT"
                icon = "➕"
            elif query_upper.startswith("DELETE"):
                operation = "DELETE"
                icon = "🗑️"
            else:
                operation = "MODIFY"
                icon = "⚙️"

            # Update results text
            self.results_text.delete("1.0", tk.END)
            self.results_text.insert(tk.END, f"{'='*150}\n")
            self.results_text.insert(
                tk.END, f"✅ {icon} {operation} Statement Executed Successfully!\n"
            )
            self.results_text.insert(tk.END, f"{'='*150}\n\n")
            self.results_text.insert(tk.END, f"📊 Rows Affected: {rows_affected:,}\n\n")
            self.results_text.insert(tk.END, f"SQL Statement:\n{sql_query}\n\n")
            self.results_text.insert(tk.END, f"{'─'*150}\n")
            self.results_text.see(tk.END)

            # Re-enable execute button
            self.execute_btn.config(state="normal", text="▶  Run")

            # Show success message
            messagebox.showinfo(
                "Success", f"{operation} executed successfully!\n\nRows affected: {rows_affected:,}"
            )

        except Exception as e:
            messagebox.showerror("Error", f"Failed to display results:\n{str(e)}")
            self.execute_btn.config(state="normal", text="▶  Run")

    def on_query_success(self, df, sql_query, loading_dialog):
        """Handle successful query execution"""
        try:
            # Close loading dialog
            loading_dialog.destroy()

            # Update results text
            self.results_text.delete("1.0", tk.END)
            self.results_text.insert(tk.END, f"✅ Query executed successfully!\n")
            self.results_text.insert(tk.END, f"📊 Total Rows: {len(df):,}\n")
            self.results_text.insert(tk.END, f"📋 Total Columns: {df.shape[1]}\n\n")
            self.results_text.insert(tk.END, "Opening results in new window...\n")

            # Re-enable execute button
            self.execute_btn.config(state="normal", text="▶  Run")

            # UI: also mirror the result into the Results Grid tab
            self._show_results_grid(df, sql_query)

            # Show results in popup table window
            self.show_table_popup(df, sql_query)

        except Exception as e:
            messagebox.showerror("Error", f"Failed to display results:\n{str(e)}")
            self.execute_btn.config(state="normal", text="▶  Run")

    def on_query_error(self, error, loading_dialog):
        """Handle query execution error"""
        try:
            # Close loading dialog
            loading_dialog.destroy()
        except:
            pass

        # Update results text
        self.results_text.delete("1.0", tk.END)
        self.results_text.insert(tk.END, "❌ QUERY ERROR\n")
        self.results_text.insert(tk.END, "=" * 150 + "\n\n")
        self.results_text.insert(tk.END, f"Error: {str(error)}\n\n")
        self.results_text.see(tk.END)

        # Re-enable execute button
        self.execute_btn.config(state="normal", text="▶  Run")

        messagebox.showerror("Query Error", f"Failed to execute query:\n\n{str(error)}")

    # ------------------------------------------------------------------
    # Results Drawer UI (presentation only — reuses export_to_csv,
    # export_to_excel_result, copy_selected_rows, _show_error_details_dialog)
    # ------------------------------------------------------------------
    RESULTS_GRID_PAGE_SIZE = 1000

    def _build_results_grid_tab(self, tab):
        # sets: list of (name, df, sql) — one for Execute Query, many for Run All Jobs
        self._results_grid_state = {"df": None, "sql": None, "name": None, "page": 0, "sets": []}
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(1, weight=1)

        toolbar = tk.Frame(tab, bg=UI["card"])
        toolbar.grid(row=0, column=0, sticky="ew", padx=16, pady=(12, 8))

        # Result-set picker (shown only when Run All Jobs produced several results)
        self._rg_set_box = tk.Frame(toolbar, bg=UI["card"])
        ui_field_label(self._rg_set_box, "RESULT").pack(side="left", padx=(0, 6))
        # Native Windows menu instead of ttk.Combobox: the Combobox drop-down is
        # placed using the primary screen size, so on a multi-monitor setup it can
        # open on the wrong screen / behind other windows and become unusable.
        self._rg_set_var = tk.IntVar(value=0)
        self._rg_set_menu = tk.Menu(self.root, tearoff=0, font=UI_FONT_SM)
        self._rg_set_btn = tk.Button(
            self._rg_set_box,
            text="",
            width=42,
            anchor="w",
            font=UI_FONT_SM,
            bg=UI["card"],
            fg=UI["text"],
            activebackground=UI["card"],
            relief="solid",
            bd=1,
            cursor="hand2",
            padx=6,
            command=self._open_results_set_menu,
        )
        ui_round_tkbutton(self._rg_set_btn, "secondary", "sm")
        self._rg_set_btn.pack(side="left")

        self._rg_info = tk.Label(
            toolbar,
            text="No results yet — run a query (Ctrl+Enter)",
            bg=UI["card"],
            fg=UI["muted"],
            font=UI_FONT_SM,
        )
        self._rg_info.pack(side="left")

        _outer, self._rg_export_xlsx_btn = ui_button(
            toolbar,
            "📗 Export Excel",
            lambda: self._results_grid_state["df"] is not None
            and self.export_to_excel_result(
                self._results_grid_state["df"],
                self._results_grid_state["sql"],
                job_name=self._results_grid_state["name"],
            ),
            size="sm",
            state="disabled",
        )
        _outer.pack(side="right")
        _outer, self._rg_export_csv_btn = ui_button(
            toolbar,
            "📄 Export CSV",
            lambda: self._results_grid_state["df"] is not None
            and self.export_to_csv(self._results_grid_state["df"]),
            size="sm",
            state="disabled",
        )
        _outer.pack(side="right", padx=(0, 6))

        tk.Frame(toolbar, bg=UI["border"], width=1, height=22).pack(side="right", padx=10)

        _outer, self._rg_next_btn = ui_button(
            toolbar,
            "Next ▶",
            lambda: self._render_results_grid_page(self._results_grid_state["page"] + 1),
            size="sm",
            state="disabled",
        )
        _outer.pack(side="right")
        self._rg_page_label = tk.Label(
            toolbar, text="Page 1 / 1", bg=UI["card"], fg=UI["text"], font=UI_FONT_SM
        )
        self._rg_page_label.pack(side="right", padx=8)
        _outer, self._rg_prev_btn = ui_button(
            toolbar,
            "◀ Prev",
            lambda: self._render_results_grid_page(self._results_grid_state["page"] - 1),
            size="sm",
            state="disabled",
        )
        _outer.pack(side="right")

        tree_wrap = tk.Frame(
            tab,
            bg=UI["card"],
            highlightthickness=1,
            highlightbackground=UI["border"],
            highlightcolor=UI["border"],
        )
        tree_wrap.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 16))
        tree_wrap.columnconfigure(0, weight=1)
        tree_wrap.rowconfigure(0, weight=1)

        tree = ttk.Treeview(tree_wrap, show="headings", height=18, style="Fluent.Treeview")
        vsb = ttk.Scrollbar(tree_wrap, orient="vertical", command=tree.yview)
        hsb = ttk.Scrollbar(tree_wrap, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        tree.tag_configure("odd", background=UI["surface"])
        self._rg_tree = tree

        def _tree_wheel(ev):
            tree.yview_scroll(int(-1 * (ev.delta / 120)), "units")

        tree.bind("<Enter>", lambda _e: tree.bind_all("<MouseWheel>", _tree_wheel))
        tree.bind("<Leave>", lambda _e: tree.bind_all("<MouseWheel>", self._main_mousewheel))
        # Ctrl+C (any keyboard layout) → existing copy_selected_rows
        tree.bind(
            "<Control-KeyPress>",
            lambda e: (self.copy_selected_rows(tree), "break")[1] if e.keycode == 67 else None,
        )

    def _show_results_grid(self, df, sql_query):
        """Mirror a SELECT result into the Results Grid tab."""
        self._show_results_grid_sets([(None, df, sql_query)])

    def _show_results_grid_sets(self, result_sets):
        """Show one or more (name, df, sql) results; several → picker to switch."""
        if not hasattr(self, "_rg_tree") or not result_sets:
            return
        state = self._results_grid_state
        state["sets"] = list(result_sets)
        state["set_labels"] = [
            f"{i}. {name or 'Result'}  ({len(df):,} rows)"
            for i, (name, df, _sql) in enumerate(result_sets, 1)
        ]
        if len(result_sets) > 1:
            if not self._rg_set_box.winfo_ismapped():
                self._rg_set_box.pack(side="left", padx=(0, 14), before=self._rg_info)
        else:
            self._rg_set_box.pack_forget()
        self._select_results_grid_set(0)
        self.results_notebook.select(0)

    def _clear_results_grid(self, message="No results yet — run a query (Ctrl+Enter)"):
        """Empty the Results Grid so results of a previous run are not shown."""
        if not hasattr(self, "_rg_tree"):
            return
        self._results_grid_state.update(df=None, sql=None, name=None, page=0, sets=[])
        tree = self._rg_tree
        tree.delete(*tree.get_children())
        tree["columns"] = []
        self._results_grid_state["set_labels"] = []
        self._rg_set_btn.config(text="")
        self._rg_set_box.pack_forget()
        self._rg_info.config(text=message, fg=UI["muted"])
        self._rg_page_label.config(text="Page 1 / 1")
        for btn in (
            self._rg_prev_btn,
            self._rg_next_btn,
            self._rg_export_csv_btn,
            self._rg_export_xlsx_btn,
        ):
            btn.config(state="disabled")

    def _select_results_grid_set(self, index):
        sets = self._results_grid_state["sets"]
        if not sets or index < 0 or index >= len(sets):
            return
        name, df, sql_query = sets[index]
        self._results_grid_state.update(df=df, sql=sql_query, name=name, page=0)
        self._rg_set_var.set(index)
        labels = self._results_grid_state.get("set_labels") or []
        if index < len(labels):
            self._rg_set_btn.config(text=f"{labels[index]}   ▾")
        self._render_results_grid_page(0)

    def _open_results_set_menu(self):
        """Drop down the result-set list right under the RESULT button."""
        labels = self._results_grid_state.get("set_labels") or []
        if len(labels) < 2:
            return
        menu = self._rg_set_menu
        menu.delete(0, "end")
        for i, label in enumerate(labels):
            menu.add_radiobutton(
                label=label,
                variable=self._rg_set_var,
                value=i,
                command=lambda idx=i: self._select_results_grid_set(idx),
            )
        btn = self._rg_set_btn
        try:
            menu.tk_popup(btn.winfo_rootx(), btn.winfo_rooty() + btn.winfo_height())
        finally:
            menu.grab_release()

    def _render_results_grid_page(self, page):
        state = self._results_grid_state
        df = state["df"]
        if df is None:
            return
        size = self.RESULTS_GRID_PAGE_SIZE
        total_pages = max(1, (len(df) + size - 1) // size)
        page = max(0, min(page, total_pages - 1))
        state["page"] = page

        tree = self._rg_tree
        tree.delete(*tree.get_children())
        columns = [str(c) for c in df.columns]
        tree["columns"] = columns
        start = page * size
        sample = df.iloc[start : start + 50]
        for pos, col in enumerate(columns):
            longest_value = max([0] + [len(format_db_value(v)) for v in sample.iloc[:, pos]])
            width = max(len(col) * 10, longest_value * 8) + 24
            tree.heading(col, text=col, anchor="w")
            tree.column(col, width=min(360, max(90, width)), anchor="w", stretch=False)

        for i, row in enumerate(df.iloc[start : start + size].itertuples(index=False, name=None)):
            values = [format_db_value(v) for v in row]
            tree.insert("", "end", values=values, tags=("odd",) if i % 2 else ())

        end = min(start + size, len(df))
        name = state.get("name")
        self._rg_info.config(
            text=(f"{name}   ·   " if name else "")
            + f"{len(df):,} rows × {df.shape[1]} columns"
            + (f"   ·   showing {start + 1:,}–{end:,}" if len(df) else ""),
            fg=UI["text"],
        )
        self._rg_page_label.config(text=f"Page {page + 1} / {total_pages}")
        self._rg_prev_btn.config(state="normal" if page > 0 else "disabled")
        self._rg_next_btn.config(state="normal" if page < total_pages - 1 else "disabled")
        self._rg_export_csv_btn.config(state="normal")
        self._rg_export_xlsx_btn.config(state="normal")

    def _build_error_debug_tab(self, tab):
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(1, weight=1)

        toolbar = tk.Frame(tab, bg=UI["card"])
        toolbar.grid(row=0, column=0, sticky="ew", padx=16, pady=(12, 8))

        _debug_cb = tk.Checkbutton(
            toolbar,
            text="Debug mode (console logging)",
            variable=self.debug_mode,
            bg=UI["card"],
            activebackground=UI["card"],
            fg=UI["text"],
            selectcolor="#FFFFFF",
            font=UI_FONT_SM,
            bd=0,
            highlightthickness=0,
            cursor="hand2",
        )
        _debug_cb.pack(side="left")
        ui_round_check(_debug_cb)

        _outer, self._dbg_details_btn = ui_button(
            toolbar,
            "🔍 Full Error Details",
            lambda: self.last_error_details
            and self._show_error_details_dialog(self.last_error_details),
            size="sm",
            state="disabled",
        )
        _outer.pack(side="right")

        debug_text = scrolledtext.ScrolledText(
            tab,
            height=18,
            font=UI_FONT_MONO,
            wrap=tk.WORD,
            bg="#FFFFFF",
            fg=UI["text"],
            relief="flat",
            bd=0,
            highlightthickness=1,
            highlightbackground=UI["border"],
            highlightcolor=UI["border"],
            padx=10,
            pady=8,
        )
        debug_text.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 16))
        debug_text.tag_configure("h", font=UI_FONT_LABEL, foreground=UI["muted"])
        debug_text.tag_configure("err", foreground=UI["danger"], font=UI_FONT_SEMI)
        debug_text.insert("1.0", "No errors recorded in this session.")
        debug_text.config(state="disabled")

        def _wheel(ev):
            debug_text.yview_scroll(int(-1 * (ev.delta / 120)), "units")

        debug_text.bind("<Enter>", lambda _e: debug_text.bind_all("<MouseWheel>", _wheel))
        debug_text.bind(
            "<Leave>", lambda _e: debug_text.bind_all("<MouseWheel>", self._main_mousewheel)
        )

        shown = {"details": None}

        def _poll_last_error():
            """Read-only: render self.last_error_details when it changes."""
            try:
                if not debug_text.winfo_exists():
                    return
                details = self.last_error_details
                if details is not None and details is not shown["details"]:
                    shown["details"] = details
                    debug_text.config(state="normal")
                    debug_text.delete("1.0", tk.END)
                    debug_text.insert(tk.END, "LAST QUERY ERROR\n", "h")
                    debug_text.insert(
                        tk.END,
                        f"{details.get('type', 'Error')}: " f"{details.get('message', '')}\n\n",
                        "err",
                    )
                    debug_text.insert(tk.END, "QUERY\n", "h")
                    debug_text.insert(tk.END, f"{details.get('query', '')}\n\n")
                    debug_text.insert(tk.END, "TRACEBACK\n", "h")
                    debug_text.insert(tk.END, details.get("traceback", ""))
                    debug_text.config(state="disabled")
                    self._dbg_details_btn.config(state="normal")
                    if self.results_notebook.select() != str(tab):
                        self.results_notebook.tab(tab, text="🐛 Error & Debug  ●")
            except tk.TclError:
                return
            debug_text.after(500, _poll_last_error)

        def _on_tab_changed(_e):
            try:
                if self.results_notebook.select() == str(tab):
                    self.results_notebook.tab(tab, text="🐛 Error & Debug")
            except tk.TclError:
                pass

        self.results_notebook.bind("<<NotebookTabChanged>>", _on_tab_changed, add="+")
        _poll_last_error()

    def show_table_popup(self, df, sql_query, on_double_click=None, job_name=None):
        """Show DataFrame in a popup window with Treeview"""
        # Create popup window
        popup = tk.Toplevel(self.root)
        popup.title(
            f"{job_name} - Query Results - {len(df):,} rows × {df.shape[1]} columns"
            if job_name
            else f"Query Results - {len(df):,} rows × {df.shape[1]} columns"
        )
        # Open on the same monitor as the main window (cascade a little for
        # each extra popup) instead of wherever Windows decides
        self._popup_cascade = (getattr(self, "_popup_cascade", -1) + 1) % 8
        offset = 40 + self._popup_cascade * 30
        self.root.update_idletasks()
        popup_w = max(800, min(1200, self.root.winfo_width() - offset))
        popup_h = max(500, min(700, self.root.winfo_height() - offset))
        popup.geometry(
            f"{popup_w}x{popup_h}"
            f"+{self.root.winfo_rootx() + offset}+{self.root.winfo_rooty() + offset}"
        )

        # Pagination state - local to this popup, so several popups
        # (e.g. from Run All Jobs) don't overwrite each other's page
        rows_per_page = 1000
        total_pages = max(1, (len(df) + rows_per_page - 1) // rows_per_page)
        page_state = {"current": 0}

        # Create main frame
        main_frame = ttk.Frame(popup, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        popup.columnconfigure(0, weight=1)
        popup.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(1, weight=1)

        # Info frame
        info_frame = ttk.LabelFrame(main_frame, text="Query Information", padding="10")
        info_frame.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=(0, 10))

        ttk.Label(info_frame, text=f"📊 Total Rows: {len(df):,}", font=("Arial", 10, "bold")).grid(
            row=0, column=0, sticky=tk.W, padx=5
        )
        ttk.Label(
            info_frame, text=f"📋 Total Columns: {df.shape[1]}", font=("Arial", 10, "bold")
        ).grid(row=0, column=1, sticky=tk.W, padx=5)

        # Table frame with scrollbars
        table_frame = ttk.LabelFrame(main_frame, text="Data Preview", padding="10")
        table_frame.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        table_frame.columnconfigure(0, weight=1)
        table_frame.rowconfigure(0, weight=1)

        # Create Treeview with scrollbars
        tree_scroll_y = ttk.Scrollbar(table_frame, orient=tk.VERTICAL)
        tree_scroll_x = ttk.Scrollbar(table_frame, orient=tk.HORIZONTAL)

        tree = ttk.Treeview(
            table_frame,
            columns=list(df.columns),
            show="headings",
            yscrollcommand=tree_scroll_y.set,
            xscrollcommand=tree_scroll_x.set,
            selectmode="extended",
        )

        tree_scroll_y.config(command=tree.yview)
        tree_scroll_x.config(command=tree.xview)

        # Grid layout
        tree.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        tree_scroll_y.grid(row=0, column=1, sticky=(tk.N, tk.S))
        tree_scroll_x.grid(row=1, column=0, sticky=(tk.W, tk.E))

        # Configure columns
        for col in df.columns:
            tree.heading(col, text=col, command=lambda c=col: self.sort_treeview(tree, c, False))
            tree.column(col, width=150, minwidth=100, anchor=tk.W)

        # Add double-click event if callback provided
        if on_double_click:
            tree.bind(
                "<Double-Button-1>", lambda e: self.on_tree_double_click(e, tree, on_double_click)
            )

        # Mousewheel scrolls treeview; suppress main canvas scroll while popup open
        def _tree_mousewheel(e):
            tree.yview_scroll(int(-1 * (e.delta / 120)), "units")
            return "break"

        def _on_tree_enter(e):
            tree.bind_all("<MouseWheel>", _tree_mousewheel)

        def _on_tree_leave(e):
            tree.unbind_all("<MouseWheel>")
            self.canvas.bind_all("<MouseWheel>", self._main_mousewheel)

        def _restore_main_on_close(e=None):
            self.canvas.bind_all("<MouseWheel>", self._main_mousewheel)

        tree.bind("<Enter>", _on_tree_enter)
        tree.bind("<Leave>", _on_tree_leave)
        popup.bind("<Destroy>", _restore_main_on_close)
        # Suppress main scroll while popup window is open
        self.canvas.unbind_all("<MouseWheel>")

        # Pagination info label (create before load_page function)
        page_label = ttk.Label(
            info_frame, text=f"Page 1 of {total_pages}", font=("Arial", 9, "bold")
        )
        page_label.grid(row=0, column=2, sticky=tk.W, padx=20)

        # Buttons frame (created once)
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=2, column=0, pady=10)

        # Function to load data for a page
        def load_page(page_num):
            page_num = max(0, min(page_num, total_pages - 1))
            page_state["current"] = page_num

            # Clear existing data
            for item in tree.get_children():
                tree.delete(item)

            # Calculate row range
            start_row = page_num * rows_per_page
            end_row = min(start_row + rows_per_page, len(df))

            # Insert data for current page
            for idx in range(start_row, end_row):
                row = df.iloc[idx]
                values = [format_db_value(val) for val in row]
                tree.insert("", tk.END, values=values)

            # Update page info
            shown_start = start_row + 1 if end_row > start_row else 0
            page_label.config(
                text=f"Page {page_num + 1} of {total_pages} (Rows {shown_start:,}-{end_row:,} of {len(df):,})"
            )

            # Update button states
            prev_btn.config(state="normal" if page_num > 0 else "disabled")
            next_btn.config(state="normal" if page_num < total_pages - 1 else "disabled")

        # Pagination buttons
        ttk.Button(button_frame, text="⏮️ First", command=lambda: load_page(0)).grid(
            row=0, column=0, padx=5
        )
        prev_btn = ttk.Button(
            button_frame, text="◀️ Previous", command=lambda: load_page(page_state["current"] - 1)
        )
        prev_btn.grid(row=0, column=1, padx=5)

        next_btn = ttk.Button(
            button_frame, text="Next ▶️", command=lambda: load_page(page_state["current"] + 1)
        )
        next_btn.grid(row=0, column=2, padx=5)
        ttk.Button(button_frame, text="Last ⏭️", command=lambda: load_page(total_pages - 1)).grid(
            row=0, column=3, padx=5
        )

        # Separator
        ttk.Separator(button_frame, orient="vertical").grid(row=0, column=4, padx=10, sticky="ns")

        # Action buttons
        ttk.Button(
            button_frame, text="📋 Copy Selected", command=lambda: self.copy_selected_rows(tree)
        ).grid(row=0, column=5, padx=5)
        ttk.Button(
            button_frame, text="💾 Export to CSV", command=lambda: self.export_to_csv(df)
        ).grid(row=0, column=6, padx=5)

        ttk.Button(
            button_frame,
            text="📤 Export Excel",
            command=lambda: self.export_to_excel_result(df, sql_query, job_name),
        ).grid(row=0, column=7, padx=5)

        ttk.Button(button_frame, text="❌ Close", command=popup.destroy).grid(
            row=0, column=8, padx=5
        )

        # Initial data load (also sets Previous/Next button states)
        load_page(0)
        return popup

    def on_tree_double_click(self, event, tree, callback):
        """Handle double-click on tree item"""
        try:
            item = tree.selection()[0]
            values = tree.item(item)["values"]
            if values:
                callback(values)
        except:
            pass

    def sort_treeview(self, tree, col, reverse):
        """Sort treeview by column"""
        data = [(tree.set(child, col), child) for child in tree.get_children("")]
        data.sort(reverse=reverse)
        for index, (val, child) in enumerate(data):
            tree.move(child, "", index)
        tree.heading(col, command=lambda: self.sort_treeview(tree, col, not reverse))

    def copy_selected_rows(self, tree):
        """Copy selected rows to clipboard"""
        try:
            selected = tree.selection()
            if not selected:
                messagebox.showwarning("Warning", "Please select rows to copy")
                return

            # Get column names
            columns = tree["columns"]
            text = "\t".join(columns) + "\n"

            # Get selected rows
            for item in selected:
                values = [tree.set(item, col) for col in columns]
                text += "\t".join(values) + "\n"

            # Copy to clipboard
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
            messagebox.showinfo("Success", f"Copied {len(selected)} rows to clipboard")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to copy: {str(e)}")

    def export_to_csv(self, df):
        """Export DataFrame to CSV file"""
        try:
            file_path = filedialog.asksaveasfilename(
                defaultextension=".csv", filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
            )
            if file_path:
                # Same text as the result grid (DBeaver style), NULL → [NULL]
                df.apply(lambda col: col.map(format_db_value)).to_csv(
                    file_path, index=False, encoding="utf-8-sig"
                )
                messagebox.showinfo("Success", f"Data exported successfully!\n\nFile: {file_path}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to export: {str(e)}")

    def export_to_excel_result(self, df, sql_query, job_name=None):
        """Export only this job using the standard Excel export workflow."""
        job = {
            "name": job_name or "Query_Result",
            "query": sql_query,
            "profile": self.profile_combo.get(),
            "_export_dataframe": df.copy(),
        }
        self.export_jobs_to_excel(jobs_override=[job])

    def list_tables(self):
        """List all schemas and tables in the database"""
        if not self.engine:
            messagebox.showerror("Error", "Please connect to database first")
            return

        # Check if user wants to list all databases or just current connection
        current_db_name = self.db_name.get().strip()

        self.results_text.insert(tk.END, "Fetching database schema information...\n\n")
        self.results_text.see(tk.END)

        # Disable button to prevent multiple clicks
        self.inspect_btn.config(state="disabled", text="⏳ Loading...")
        self.root.update()

        # Create loading dialog
        loading_dialog = tk.Toplevel(self.root)
        loading_dialog.title("Loading Tables...")
        loading_dialog.geometry("300x250")
        loading_dialog.transient(self.root)
        loading_dialog.grab_set()

        # Center dialog
        loading_dialog.update_idletasks()
        x = (loading_dialog.winfo_screenwidth() // 2) - (loading_dialog.winfo_width() // 2)
        y = (loading_dialog.winfo_screenheight() // 2) - (loading_dialog.winfo_height() // 2)
        loading_dialog.geometry(f"+{x}+{y}")

        ttk.Label(loading_dialog, text="⏳ Loading tables...", font=("Arial", 11, "bold")).pack(
            pady=10
        )
        progress = ttk.Progressbar(loading_dialog, mode="indeterminate", length=250)
        progress.pack(pady=10)
        progress.start(10)

        # Execute in background thread
        def fetch_tables_in_background():
            try:
                db_type = self.db_type.get()
                table_list = []

                # Check if we should list all databases or just current
                if not current_db_name:
                    # List all databases - need to query database list first
                    databases_to_check = []

                    # Get database list
                    try:
                        with self.engine.connect() as conn:
                            if db_type == "PostgreSQL":
                                result = conn.execute(
                                    text(
                                        "SELECT datname FROM pg_database WHERE datistemplate = false AND datname NOT IN ('postgres', 'template0', 'template1')"
                                    )
                                )
                                databases_to_check = [row[0] for row in result]
                            elif db_type == "MySQL":
                                result = conn.execute(text("SHOW DATABASES"))
                                databases_to_check = [
                                    row[0]
                                    for row in result
                                    if row[0]
                                    not in [
                                        "mysql",
                                        "information_schema",
                                        "performance_schema",
                                        "sys",
                                    ]
                                ]
                            elif db_type == "Microsoft SQL Server":
                                # Query ALL databases without filtering
                                result = conn.execute(text("""
                                    SELECT name 
                                    FROM sys.databases 
                                    WHERE state_desc = 'ONLINE'
                                    ORDER BY name
                                """))
                                databases_to_check = [row[0] for row in result]
                                print(f"\n{'='*150}")
                                print(f"SQL Server - Found {len(databases_to_check)} databases:")
                                for db in databases_to_check:
                                    print(f"  - {db}")
                                print(f"{'='*150}\n")
                            elif db_type == "Oracle":
                                result = conn.execute(
                                    text(
                                        "SELECT username FROM all_users WHERE username NOT IN ('SYS', 'SYSTEM', 'DBSNMP', 'SYSMAN', 'OUTLN', 'MDSYS', 'ORDSYS', 'EXFSYS', 'DMSYS', 'WMSYS', 'CTXSYS', 'ANONYMOUS', 'XDB', 'XS$NULL', 'OJVMSYS', 'LBACSYS', 'APEX_PUBLIC_USER', 'FLOWS_FILES', 'APEX_040000', 'APEX_040200', 'SPATIAL_CSW_ADMIN_USR', 'SPATIAL_WFS_ADMIN_USR', 'PUBLIC') ORDER BY username"
                                    )
                                )
                                databases_to_check = [row[0] for row in result]
                    except Exception as e:
                        print(f"\n❌ ERROR getting database list for {db_type}: {e}")
                        import traceback

                        traceback.print_exc()
                        databases_to_check = []

                    # For each database, connect and get tables
                    for database in databases_to_check:
                        try:
                            print(f"\n{'─'*150}")
                            print(f"📁 Processing database: {database}")
                            if db_type == "Oracle":
                                # For Oracle, use current connection with schema
                                inspector = inspect(self.engine)
                                try:
                                    tables = inspector.get_table_names(schema=database)
                                    for table in tables:
                                        table_list.append(
                                            {
                                                "Database": database,
                                                "Schema": database,
                                                "Table": table,
                                            }
                                        )
                                except:
                                    pass
                            else:
                                # Create connection for specific database
                                temp_conn_str = self.get_connection_string(
                                    db_type,
                                    self.db_user.get(),
                                    self.db_password.get(),
                                    self.db_host.get(),
                                    self.db_port.get(),
                                    database,
                                )
                                print(f"   🔌 Connecting to {database}...")
                                temp_engine = create_engine(
                                    temp_conn_str, connect_args=self.get_connect_args(db_type)
                                )
                                temp_inspector = inspect(temp_engine)
                                temp_schemas = temp_inspector.get_schema_names()
                                print(
                                    f"   ✅ Connected! Found {len(temp_schemas)} schemas: {temp_schemas}"
                                )

                                # Define skip_schemas based on database type
                                if db_type == "Microsoft SQL Server":
                                    # Only skip true system schemas, not user schemas
                                    skip_schemas = ["information_schema", "sys", "guest"]
                                elif db_type == "PostgreSQL":
                                    skip_schemas = [
                                        "information_schema",
                                        "pg_catalog",
                                        "pg_toast",
                                        "pg_toast_temp_1",
                                    ]
                                else:  # MySQL
                                    skip_schemas = [
                                        "information_schema",
                                        "mysql",
                                        "performance_schema",
                                        "sys",
                                    ]

                                schema_count = 0
                                for schema in temp_schemas:
                                    if schema.lower() in skip_schemas:
                                        print(f"      ⏭️  Skipping system schema: {schema}")
                                        continue

                                    try:
                                        # Use raw SQL for SQL Server to avoid HY104 error
                                        if db_type == "Microsoft SQL Server":
                                            with temp_engine.connect() as temp_conn:
                                                query = text(f"""
                                                    SELECT TABLE_NAME 
                                                    FROM [{database}].INFORMATION_SCHEMA.TABLES 
                                                    WHERE TABLE_SCHEMA = '{schema}' 
                                                    AND TABLE_TYPE = 'BASE TABLE'
                                                    ORDER BY TABLE_NAME
                                                """)
                                                result = temp_conn.execute(query)
                                                tables = [row[0] for row in result]
                                        else:
                                            tables = temp_inspector.get_table_names(schema=schema)

                                        if len(tables) > 0:
                                            print(
                                                f"      ✅ Schema '{schema}': {len(tables)} tables"
                                            )
                                            schema_count += 1
                                            for table in tables:
                                                table_list.append(
                                                    {
                                                        "Database": database,
                                                        "Schema": schema,
                                                        "Table": table,
                                                    }
                                                )
                                        else:
                                            print(
                                                f"      ⚠️  Schema '{schema}': 0 tables (skipping)"
                                            )
                                    except Exception as schema_err:
                                        print(
                                            f"      ❌ Error reading schema '{schema}': {schema_err}"
                                        )
                                        import traceback

                                        traceback.print_exc()
                                        # Skip this schema and continue with others
                                        continue

                                temp_engine.dispose()
                                total_tables = len(
                                    [t for t in table_list if t["Database"] == database]
                                )
                                print(
                                    f"   📊 Completed {database}: {schema_count} schemas, {total_tables} tables total"
                                )
                        except Exception as e:
                            print(f"   ❌ ERROR accessing database {database}: {e}")
                            import traceback

                            traceback.print_exc()
                            pass
                else:
                    # List tables from currently connected database only
                    inspector = inspect(self.engine)
                    schemas = inspector.get_schema_names()

                    for schema in schemas:
                        skip_schemas = [
                            "information_schema",
                            "pg_catalog",
                            "pg_toast",
                            "pg_toast_temp_1",
                            "SYSTEM",
                            "SYS",
                            "MDSYS",
                            "CTXSYS",
                            "XDB",
                            "ORDSYS",
                            "EXFSYS",
                            "WMSYS",
                            "DBSNMP",
                        ]
                        if schema in skip_schemas:
                            continue

                        try:
                            tables = inspector.get_table_names(schema=schema)
                            for table in tables:
                                table_list.append(
                                    {"Database": current_db_name, "Schema": schema, "Table": table}
                                )
                        except:
                            pass

                # Update UI in main thread
                self.root.after(
                    0,
                    lambda: self.on_list_tables_success(
                        table_list, loading_dialog, bool(current_db_name)
                    ),
                )

            except Exception as e:
                # Handle error in main thread
                self.root.after(0, lambda err=e: self.on_list_tables_error(err, loading_dialog))

        # Start background thread
        thread = threading.Thread(target=fetch_tables_in_background, daemon=True)
        thread.start()

    def on_list_tables_success(self, table_list, loading_dialog, has_database=True):
        """Handle successful table listing"""
        try:
            # Close loading dialog
            loading_dialog.destroy()

            # Re-enable button
            self.inspect_btn.config(state="normal", text="▦  Tables")

            # Convert to DataFrame
            if table_list:
                df = pd.DataFrame(table_list)

                # Count unique items
                if "Database" in df.columns:
                    summary = f"✅ Found {len(df)} tables across {df['Schema'].nunique()} schemas in {df['Database'].nunique()} database(s)\n\n"
                else:
                    summary = (
                        f"✅ Found {len(df)} tables across {df['Schema'].nunique()} schemas\n\n"
                    )

                # Update results text
                self.results_text.delete("1.0", tk.END)
                self.results_text.insert(tk.END, summary)
                self.results_text.insert(tk.END, "Opening results in new window...\n")
                self.results_text.insert(
                    tk.END, "💡 Tip: Double-click on a table to insert it into SQL Query\n"
                )

                # Define callback for double-click
                def on_table_double_click(values):
                    # Always expect 3-column format (Database, Schema, Table)
                    if len(values) != 3:
                        return

                    database = values[0]
                    schema = values[1]
                    table = values[2]

                    # Generate query based on database type
                    if self.db_type.get() == "Microsoft SQL Server":
                        query = f"SELECT * FROM [{database}].[{schema}].[{table}]"
                    elif self.db_type.get() == "Oracle":
                        # Oracle uses schema.table format (database is schema in Oracle)
                        query = f"SELECT * FROM {database}.{table}"
                    elif self.db_type.get() == "MySQL":
                        # MySQL: database.table (no schema concept in MySQL like PostgreSQL)
                        query = f"SELECT * FROM {database}.{table}"
                    else:
                        # PostgreSQL: database.schema.table format not directly supported
                        # Use schema.table for currently connected database
                        query = f"SELECT * FROM {schema}.{table}"

                    # Insert into SQL query area
                    self.sql_context.delete(1.0, tk.END)
                    self.sql_context.insert(1.0, query)
                    self.results_text.insert(tk.END, f"\n📝 Inserted query: {query}\n")
                    self.results_text.see(tk.END)

                # Show results in popup table window with double-click handler
                self.show_table_popup(
                    df, "Database Schema Information", on_double_click=on_table_double_click
                )
            else:
                self.results_text.insert(tk.END, "⚠️ No tables found in database\n\n")
                messagebox.showinfo("Info", "No tables found in the database")

        except Exception as e:
            messagebox.showerror("Error", f"Failed to display tables:\n{str(e)}")
            self.inspect_btn.config(state="normal", text="▦  Tables")

    def on_list_tables_error(self, error, loading_dialog):
        """Handle table listing error"""
        try:
            # Close loading dialog
            loading_dialog.destroy()
        except:
            pass

        # Re-enable button
        self.inspect_btn.config(state="normal", text="▦  Tables")

        self.results_text.insert(tk.END, f"❌ Error: {str(error)}\n\n")
        self.results_text.see(tk.END)
        messagebox.showerror("Error", f"Failed to list tables:\n{str(error)}")

    def load_jobs(self):
        """Load saved jobs from file"""

        if not os.path.exists(self.jobs_file):
            return []

        try:

            with open(self.jobs_file, "r", encoding="utf-8") as f:

                jobs = json.load(f)

            modified = False

            for job in jobs:

                # รองรับไฟล์เก่า
                if "profile" not in job:

                    if self.saved_profiles:
                        first_profile = list(self.saved_profiles.keys())[0]
                    else:
                        first_profile = "DEFAULT"

                    job["profile"] = first_profile
                    modified = True

            # บันทึกกลับเฉพาะกรณีพบข้อมูลเก่า
            if modified:

                with open(self.jobs_file, "w", encoding="utf-8") as f:

                    json.dump(jobs, f, indent=4, ensure_ascii=False)

            return jobs

        except Exception as e:
            print(f"Error loading jobs: {e}")
            return []

    def save_jobs(self):
        """Save jobs to file"""
        try:
            with open(self.jobs_file, "w", encoding="utf-8") as f:
                json.dump(self.saved_jobs, f, indent=2, ensure_ascii=False)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save jobs:\n{str(e)}")

    def save_job_dialog(self):
        """Show dialog to save current query as a job - UPDATED: Longer names allowed"""
        sql_query = self.sql_context.get(1.0, tk.END).strip()
        if not sql_query:
            messagebox.showwarning("Warning", "Please enter a SQL query first")
            return

        dialog = tk.Toplevel(self.root)
        dialog.title("💾 Save Job")
        dialog.geometry("550x320")
        dialog.minsize(550, 320)
        dialog.configure(bg="#f0f0f0")
        dialog.transient(self.root)
        dialog.grab_set()

        x = (self.root.winfo_screenwidth() - 550) // 2
        y = (self.root.winfo_screenheight() - 320) // 2
        dialog.geometry(f"+{x}+{y}")

        content = tk.Frame(dialog, bg="#ffffff", relief="solid", bd=1)
        content.pack(fill="both", expand=True, padx=15, pady=15)

        tk.Label(
            content, text="💾 Save Job", font=("Arial", 12, "bold"), bg="#ffffff", fg="#2c3e50"
        ).pack(pady=(10, 15))

        tk.Label(content, text="Job Name (can be long):", font=("Arial", 10), bg="#ffffff").pack(
            anchor="w", padx=10, pady=(0, 5)
        )

        name_entry = tk.Entry(content, font=("Arial", 10), width=60)
        name_entry.pack(padx=10, pady=(0, 10))
        name_entry.focus()

        # Suggest name from query
        if "SELECT" in sql_query.upper():
            parts = sql_query.upper().split("FROM")
            if len(parts) > 1:
                table_part = parts[1].strip().split()[0]
                name_entry.insert(0, f"Query - {table_part}")

        tk.Label(
            content,
            text=f"💡 Query preview: {sql_query[:80]}{'...' if len(sql_query) > 80 else ''}",
            font=("Arial", 8),
            bg="#ffffff",
            fg="#7f8c8d",
        ).pack(padx=10, pady=(5, 20))

        def save():
            job_name = name_entry.get().strip()
            if not job_name:
                messagebox.showwarning("Warning", "Please enter job name", parent=dialog)
                return

            job = {
                "name": job_name,
                "profile": self.profile_combo.get(),
                "query": sql_query,
                "database": self.db_name.get(),
                "db_type": self.db_type.get(),
                "created": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
            job.update(
                self._excel_state_for_job(
                    sql_query,
                    self.sql_template,
                    self._excel_parameter_values,
                    self._excel_parameterized_sql,
                )
            )

            self.saved_jobs.append(job)
            self.save_jobs()
            self.update_jobs_list()

            self.results_text.delete("1.0", tk.END)
            self.results_text.insert(tk.END, f"💾 Job saved: {job_name}\n")
            self.results_text.insert(tk.END, f"📊 Total jobs: {len(self.saved_jobs)}\n")
            self.results_text.see(tk.END)

            messagebox.showinfo(
                "Success", f"Job saved!\n\nTotal: {len(self.saved_jobs)} jobs", parent=dialog
            )
            dialog.destroy()

        button_frame = tk.Frame(content, bg="#ffffff")
        button_frame.pack(side=tk.BOTTOM, pady=(20, 15))

        save_btn = tk.Button(
            button_frame,
            text="💾 Save",
            width=12,
            height=2,
            bg="#27ae60",
            fg="white",
            font=("Arial", 10, "bold"),
            command=save,
        )

        save_btn.pack(side="left", padx=5)

        cancel_btn = tk.Button(
            button_frame,
            text="✖ Cancel",
            width=12,
            height=2,
            bg="#95a5a6",
            fg="white",
            font=("Arial", 10, "bold"),
            command=dialog.destroy,
        )

        cancel_btn.pack(side="left", padx=5)

    def _start_job_result_report(self):
        self.results_text.delete("1.0", tk.END)

    def _finish_job_result_report(self, processed_jobs, successes, failures):
        separator = "=" * 57
        self.results_text.insert(tk.END, f"\n{separator}\n")
        self.results_text.insert(
            tk.END,
            f"Total   : {processed_jobs}\n" f"Success : {successes}\n" f"Fail    : {failures}\n",
        )
        self.results_text.insert(tk.END, f"{separator}\n")
        self.results_text.see(tk.END)

    def run_job(self, job):
        """Run single saved job"""

        if not self.engine:
            messagebox.showerror("Error", "Please connect to database first")
            return

        sql_query = job.get("query", "")

        if not sql_query.strip():
            messagebox.showwarning("Warning", "SQL Query is empty")
            return

        if not self._confirm_data_change([job]):
            return
        self._start_stoppable_run()

        # หาเลขลำดับของ Job ตาม Saved Jobs
        current_profile = self.profile_combo.get()

        profile_jobs = [j for j in self.saved_jobs if j.get("profile") == current_profile]

        job_index = 1

        for idx, j in enumerate(profile_jobs, start=1):
            if j == job:
                job_index = idx
                break

        self._start_job_result_report()
        self._clear_results_grid(f"⏳ Running: {job.get('name', '')} ...")
        self.results_text.insert(tk.END, f"⏳ Running: {job.get('name', '')} ...\n")
        self.results_text.see(tk.END)
        self.update_job_status(job_index, job, "running")

        # Disable buttons while the job runs (same as Run All Jobs)
        self.execute_btn.config(state="disabled")
        self.inspect_btn.config(state="disabled")
        self.save_job_btn.config(state="disabled")

        def finish(status, result_data=None, query_type="select", error=None, query_time=0):
            self.execute_btn.config(state="normal")
            self.inspect_btn.config(state="normal")
            self.save_job_btn.config(state="normal")
            self._start_job_result_report()
            self.update_job_status(
                job_index,
                job,
                status,
                result_data,
                error=error,
                query_type=query_type,
                query_time=query_time,
            )
            if status == "success":
                self._finish_job_result_report(1, 1, 0)
                # Same as Execute Query: mirror SELECT results into the Results Grid tab
                if query_type == "select" and result_data is not None:
                    self._show_results_grid_sets([(job.get("name"), result_data, sql_query)])
                elif query_type != "select":
                    self._clear_results_grid(
                        f"{job.get('name', '')}   ·   {result_data:,} rows affected (no result set)"
                    )
            else:
                self._finish_job_result_report(1, 0, 1)
                self._clear_results_grid(f"❌ {job.get('name', '')} failed — see Execution Logs")

        def run_in_background():
            import time

            start_time = time.perf_counter()
            try:
                if self.is_select_query(sql_query):
                    result_data = self.read_sql_dataframe(sql_query)
                    query_type = "select"
                else:
                    with self.engine.connect() as conn:
                        result = conn.execute(text(sql_query))
                        conn.commit()
                        result_data = result.rowcount
                    query_type = "modify"

                elapsed = time.perf_counter() - start_time
                self.root.after(
                    0, lambda: finish("success", result_data, query_type, query_time=elapsed)
                )

            except Exception as e:
                elapsed = time.perf_counter() - start_time
                self.root.after(0, lambda err=e: finish("error", error=err, query_time=elapsed))

        threading.Thread(target=run_in_background, daemon=True).start()

    def run_selected_job(self, jobs_override=None):
        """Run checked jobs (or all profile jobs) sequentially into Results.

        jobs_override: run exactly these jobs instead (used by Script Groups).
        """
        if jobs_override is not None:
            profile_jobs = list(jobs_override)
            list_numbers = {id(job): number for number, job in enumerate(profile_jobs, start=1)}
        else:
            profile_jobs = self.get_jobs_to_run()
            list_numbers = {
                id(job): number
                for number, job in enumerate(self._current_profile_jobs(), start=1)
            }

        for job in profile_jobs:
            job["run_index"] = list_numbers.get(id(job), 1)

        if not profile_jobs:
            messagebox.showwarning("Warning", "No jobs to run")
            return

        if not self.engine:
            messagebox.showerror("Error", "Please connect to database first")
            return

        # Ignore extra clicks while a run is in progress (each click would
        # otherwise start another run and open another set of popups)
        if getattr(self, "_batch_running", False):
            return

        if not self._confirm_data_change(profile_jobs):
            return
        self._start_stoppable_run()
        self._batch_running = True
        self.run_all_btn.config(state="disabled")

        # Close result windows left over from the previous Run Selected/All,
        # so only the jobs of this run are shown
        for old_popup in getattr(self, "_batch_popups", []):
            try:
                if old_popup.winfo_exists():
                    old_popup.destroy()
            except tk.TclError:
                pass
        self._batch_popups = []

        self._start_job_result_report()
        self._clear_results_grid(f"⏳ Running {len(profile_jobs)} job(s) ...")

        # Disable buttons during execution
        self.execute_btn.config(state="disabled")
        self.inspect_btn.config(state="disabled")
        self.save_job_btn.config(state="disabled")

        # Run jobs in background thread
        def run_all_jobs():
            import time as time_module

            job_results = []  # Store results for summary popup

            try:
                success_count = 0
                error_count = 0

                for idx, job in enumerate(profile_jobs, 1):
                    if self._stop_event.is_set():
                        not_run = len(profile_jobs) - idx + 1
                        self.root.after(
                            0,
                            lambda n=not_run: self.results_text.insert(
                                tk.END, f"⏹ Stopped — {n} job(s) not run\n"
                            ),
                        )
                        break
                    start_time = time_module.time()
                    self.root.after(0, lambda i=idx, j=job: self.update_job_status(i, j, "running"))
                    time_module.sleep(0.1)

                    try:
                        # Check if it's a SELECT query or data modification
                        if self.is_select_query(job["query"]):
                            # Execute SELECT query
                            df = self.read_sql_dataframe(job["query"])
                            elapsed_time = time_module.time() - start_time

                            # Store result
                            job_results.append(
                                {
                                    "Job #": idx,
                                    "Name": job["name"],
                                    "Status": "✅ Success",
                                    "Rows": len(df),
                                    "Columns": df.shape[1],
                                    "Time (s)": f"{elapsed_time:.2f}",
                                    "_job": job,
                                    "_data": df,
                                    "_query_type": "select",
                                    "_error": None,
                                }
                            )

                            self.root.after(
                                0,
                                lambda i=idx, j=job, d=df, qt=elapsed_time: self.update_job_status(
                                    i,
                                    j,
                                    "success",
                                    d,
                                    query_type="select",
                                    query_time=qt,
                                    show_popup=False,
                                ),
                            )
                            success_count += 1
                        else:
                            # Execute UPDATE/INSERT/DELETE statement
                            with self.engine.connect() as conn:
                                result = conn.execute(text(job["query"]))
                                conn.commit()
                                rows_affected = result.rowcount
                            elapsed_time = time_module.time() - start_time

                            # Store result
                            job_results.append(
                                {
                                    "Job #": idx,
                                    "Name": job["name"],
                                    "Status": "✅ Success",
                                    "Rows": rows_affected,
                                    "Columns": 0,
                                    "Time (s)": f"{elapsed_time:.2f}",
                                    "_job": job,
                                    "_data": rows_affected,
                                    "_query_type": "modify",
                                    "_error": None,
                                }
                            )

                            self.root.after(
                                0,
                                lambda i=idx, j=job, r=rows_affected, qt=elapsed_time: self.update_job_status(
                                    i,
                                    j,
                                    "success",
                                    r,
                                    query_type="modify",
                                    query_time=qt,
                                    show_popup=False,
                                ),
                            )
                            success_count += 1
                    except Exception as e:
                        elapsed_time = time_module.time() - start_time
                        error_msg = str(e)

                        # Store error result
                        job_results.append(
                            {
                                "Job #": idx,
                                "Name": job["name"],
                                "Status": "❌ Failed",
                                "Rows": 0,
                                "Columns": 0,
                                "Time (s)": f"{elapsed_time:.2f}",
                                "_job": job,
                                "_data": None,
                                "_query_type": "select",
                                "_error": e,
                            }
                        )

                        self.root.after(
                            0,
                            lambda i=idx, j=job, err=e, qt=elapsed_time: self.update_job_status(
                                i, j, "error", error=err, query_time=qt, show_popup=False
                            ),
                        )
                        error_count += 1

                        # Check if this is a data modification query (UPDATE/INSERT/DELETE)
                        # If so, stop execution immediately
                        if not self.is_select_query(job["query"]):
                            query_upper = job["query"].strip().upper()
                            if query_upper.startswith("UPDATE"):
                                operation = "UPDATE"
                            elif query_upper.startswith("INSERT"):
                                operation = "INSERT"
                            elif query_upper.startswith("DELETE"):
                                operation = "DELETE"
                            else:
                                operation = "Data Modification"

                            # Show critical error message
                            # Stop execution - break the loop
                            break

                # Append the run summary after every job result.
                self.root.after(
                    0,
                    lambda: self.show_batch_summary(
                        success_count, error_count, job_results, len(profile_jobs)
                    ),
                )

            except Exception as e:
                self.root.after(0, lambda err=e: self.show_batch_error(err))

        # Start background thread
        thread = threading.Thread(target=run_all_jobs, daemon=True)
        thread.start()

    def update_job_status(
        self,
        job_num,
        job,
        status,
        data=None,
        error=None,
        query_type="select",
        query_time=0,
        show_popup=True,
    ):
        """Update job execution status in results.

        show_popup=False is used by Run All Jobs: results are written to the
        Results panel only, and one summary window is shown at the end.
        """
        if status == "running":
            return

        elif status == "success":
            if query_type != "select":
                rows = data
                columns = 0
                popup_data = pd.DataFrame({"Rows affected": [data]})
            else:
                rows = len(data)
                columns = data.shape[1]
                popup_data = data

            separator = "=" * 57
            self.results_text.insert(tk.END, f"{separator}\n")
            self.results_text.insert(
                tk.END,
                f"Job Name    : {job['name']}\n"
                f"Query Time  : {query_time:.2f} sec\n"
                f"Rows        : {rows:,}\n"
                f"Columns     : {columns}\n"
                "Status      : Success\n",
            )
            self._write_run_log(f"SQL         : {' '.join(str(job.get('query', '')).split())}\n")
            self.results_text.see(tk.END)
            if not show_popup:
                return
            popup = self.show_table_popup(popup_data, job["query"], job_name=job["name"])
            popup.transient(self.root)
            popup.lift()
            popup.focus_force()

        elif status == "error":
            separator = "=" * 57
            self.results_text.insert(tk.END, f"{separator}\n")
            self.results_text.insert(
                tk.END,
                f"Job Name    : {job['name']}\n"
                f"Query Time  : {query_time:.2f} sec\n"
                "Rows        : 0\n"
                "Columns     : 0\n"
                "Status      : Fail\n"
                f"Error       : {error}\n",
            )
            self._write_run_log(f"SQL         : {' '.join(str(job.get('query', '')).split())}\n")
            self.results_text.see(tk.END)
            if not show_popup:
                return
            self.root.update_idletasks()
            popup_data = pd.DataFrame({"Error": [str(error)]})
            popup = self.show_table_popup(popup_data, job["query"], job_name=job["name"])
            popup.transient(self.root)
            popup.lift()
            popup.focus_force()

    def show_batch_summary(self, success_count, error_count, job_results, total_jobs):

        self.execute_btn.config(state="normal")
        self.inspect_btn.config(state="normal")
        self.save_job_btn.config(state="normal")
        self._batch_running = False
        self.run_all_btn.config(state="normal")
        self._finish_job_result_report(success_count + error_count, success_count, error_count)

        # Keep this run's SELECT results so Export Excel can reuse them
        # instead of running the same queries again
        self._last_run_results = {
            "time": pd.Timestamp.now(),
            "engine": self.engine,
            "items": {
                (r["Name"], str(r["_job"].get("query", "")).strip()): r["_data"]
                for r in job_results
                if r["_error"] is None and r["_query_type"] == "select"
            },
        }

        if not job_results:
            self._clear_results_grid("No result set from this run")
            return

        # Same behaviour as Execute Query, for every job that succeeded:
        # SELECT jobs open their result window and fill the Results Grid;
        # data-modification jobs are reported in the log only.
        # Failed jobs are skipped (they are listed in the log below).
        select_results = [
            r for r in job_results if r["_error"] is None and r["_query_type"] == "select"
        ]
        failed_results = [r for r in job_results if r["_error"] is not None]

        if failed_results:
            self.results_text.insert(
                tk.END,
                f"⚠️ Not shown ({len(failed_results)} failed): "
                + ", ".join(r["Name"] for r in failed_results)
                + "\n",
            )

        if select_results and not self.open_result_popups.get():
            self.results_text.insert(
                tk.END,
                f"📊 {len(select_results)} result(s) in the Results Grid tab "
                "(result windows are turned off)\n",
            )
            self._show_results_grid_sets(
                [(r["Name"], r["_data"], r["_job"]["query"]) for r in select_results]
            )
        elif select_results:
            self.results_text.insert(
                tk.END,
                f"📊 Opening {len(select_results)} result window(s) — "
                "also available in the Results Grid tab\n",
            )
            self._show_results_grid_sets(
                [(r["Name"], r["_data"], r["_job"]["query"]) for r in select_results]
            )

            last_popup = None
            for r in select_results:
                job = r["_job"]
                last_popup = self.show_table_popup(r["_data"], job["query"], job_name=job["name"])
                last_popup.transient(self.root)
                self._batch_popups.append(last_popup)
            if last_popup is not None:
                last_popup.lift()
                last_popup.focus_force()
        else:
            self._clear_results_grid("No SELECT result from this run — see Execution Logs")

        self.results_text.see(tk.END)

    def _reuse_last_run_results(self, jobs):
        """Offer to export results of the last run instead of running again.

        Returns the jobs to export (with cached results attached when the
        user agrees), or None if the user cancelled.
        """
        last = getattr(self, "_last_run_results", None)
        if not last or last.get("engine") is not self.engine or not last.get("items"):
            return jobs
        cached = {}
        for job in jobs:
            if job.get("_export_dataframe") is not None:
                continue
            key = (job.get("name"), str(job.get("query", "")).strip())
            if key in last["items"]:
                cached[id(job)] = last["items"][key]
        if not cached:
            return jobs

        others = len(jobs) - len(cached)
        run_time = last["time"].strftime("%H:%M:%S")

        def body(frame):
            choice = tk.BooleanVar(value=True)

            def option(value, title, desc):
                _card_outer, card = ui_round_frame(frame, fill=UI["card"], border=UI["border"], radius=8, pad=2)
                _card_outer.pack(fill="x", pady=(0, 8))
                card.configure(cursor="hand2")
                rb = tk.Radiobutton(card, variable=choice, value=value, bg=UI["card"],
                                    activebackground=UI["card"], selectcolor="#FFFFFF",
                                    highlightthickness=0, bd=0, cursor="hand2")
                rb.pack(side="left", padx=(12, 6), pady=10, anchor="n")
                ui_round_check(rb)
                col = tk.Frame(card, bg=UI["card"])
                col.pack(side="left", fill="x", expand=True, pady=8)
                t = tk.Label(col, text=title, bg=UI["card"], fg=UI["text"], font=UI_FONT_SEMI, anchor="w")
                t.pack(fill="x")
                d = tk.Label(col, text=desc, bg=UI["card"], fg=UI["muted"], font=UI_FONT_SM,
                             anchor="w", justify="left", wraplength=400)
                d.pack(fill="x")
                for w in (card, col, t, d):
                    w.bind("<Button-1>", lambda _e: choice.set(value))
                return card, (card, col, t, d, rb)

            cards = [
                option(True, "ใช้ผลเดิม (เร็ว)", "Export ทันทีจากผลที่รันไว้"
                       + (f" อีก {others} Job ที่ยังไม่มีผลจะถูกรันให้" if others else "")),
                option(False, "รัน Query ใหม่ทั้งหมด", "ได้ข้อมูลล่าสุด แต่ใช้เวลานานกว่า"),
            ]

            def paint(*_):
                for (card, parts), value in zip(cards, (True, False)):
                    on = choice.get() == value
                    bg = "#EFF6FF" if on else UI["card"]
                    ui_round_frame_set(card, bg, UI["primary"] if on else UI["border"])
                    for w in parts:
                        w.config(bg=bg)
                        if isinstance(w, tk.Radiobutton):
                            w.config(activebackground=bg, selectcolor=bg)

            choice.trace_add("write", paint)
            paint()
            # "Export" returns the chosen option; "Cancel" stays None
            return lambda pressed: choice.get() if pressed else None

        answer = ui_dialog(
            self.root,
            "Export Excel",
            "ใช้ผลจากรอบที่รันล่าสุด?",
            f"{len(cached)} จาก {len(jobs)} Job มีผลจากการรันเมื่อ {run_time} แล้ว เลือกว่าจะ Export อย่างไร",
            tone="info",
            build_body=body,
            buttons=(("ยกเลิก", None, "secondary"), ("⇩  Export Excel", True, "primary")),
            cancel_value=None,
            message=f"{len(cached)} of {len(jobs)} job(s) มีผลจากการรันเมื่อ {run_time}"
            + (f"; the other {others} job(s) will be run" if others else ""),
        )
        if answer is None:
            return None
        if not answer:
            return jobs
        return [
            dict(job, _export_dataframe=cached[id(job)]) if id(job) in cached else job
            for job in jobs
        ]

    def export_jobs_to_excel(self, jobs_override=None, file_prefix=None):
        """Export ผลลัพธ์ของทุก Job ลง Excel - 1 Job = 1 Sheet (ชื่อ Sheet = ชื่อ Job)"""
        import re
        import time as time_module

        if not self.engine:
            messagebox.showerror("Error", "กรุณา Connect Database ก่อน")
            return

        # ตรวจสอบว่ามี openpyxl หรือยัง
        try:
            import openpyxl
            from openpyxl.styles import Border, Side, PatternFill, Font
        except ImportError:
            err = "ไม่พบ library 'openpyxl'\nกรุณารันคำสั่ง: pip install openpyxl"
            self.results_text.insert(tk.END, f"❌ EXPORT EXCEL ERROR\n{err}\n\n")
            self.results_text.see(tk.END)
            messagebox.showerror("Export Error", err)
            return

        # เลือกที่บันทึกไฟล์
        default_name = f"jobs_export_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        if file_prefix:
            safe_prefix = re.sub(r'[\\/:*?"<>|]', "_", str(file_prefix)).strip() or "group"
            default_name = f"{safe_prefix}_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        file_path = filedialog.asksaveasfilename(
            title="Export Jobs to Excel",
            defaultextension=".xlsx",
            filetypes=[("Excel files", "*.xlsx")],
            initialfile=default_name,
        )
        if not file_path:
            return  # User cancelled

        jobs = jobs_override if jobs_override is not None else self.get_jobs_to_run()
        jobs = self._reuse_last_run_results(jobs)
        if jobs is None:
            return  # User cancelled
        self._start_stoppable_run()

        # ---- เขียน log เริ่มต้นลง Results ----
        self.results_text.delete("1.0", tk.END)
        self.results_text.insert(tk.END, f"{'='*150}\n")
        self.results_text.insert(tk.END, f"📤 Export Excel Started\n")
        self.results_text.insert(tk.END, f"📁 File: {file_path}\n")
        self.results_text.insert(tk.END, f"📊 Total Jobs: {len(jobs)}\n")
        self.results_text.insert(tk.END, f"{'='*150}\n\n")
        self.results_text.see(tk.END)

        self.export_excel_btn.config(state="disabled", text="⏳ Exporting...")

        def log(msg):

            # เขียน log ลง Results จาก background thread อย่างปลอดภัย
            def _write(m=msg):
                self.results_text.insert(tk.END, m)
                self.results_text.see(tk.END)

            self.root.after(0, _write)

        def on_done(ok, failed, skipped, elapsed, fatal_error):
            self.export_excel_btn.config(state="normal", text="⇩  Export")
            self.results_text.insert(tk.END, f"\n{'='*150}\n")
            if fatal_error:
                self.results_text.insert(tk.END, f"❌ EXPORT EXCEL FAILED\n")
                self.results_text.insert(tk.END, f"{'='*150}\n")
                self.results_text.insert(tk.END, f"Error: {fatal_error}\n\n")
                self.results_text.see(tk.END)
                messagebox.showerror("Export Error", f"Export Excel ไม่สำเร็จ:\n\n{fatal_error}")
                return
            self.results_text.insert(tk.END, f"🏁 Export Excel Completed ({elapsed:.2f}s)\n")
            self.results_text.insert(tk.END, f"{'='*150}\n")
            self.results_text.insert(tk.END, f"✅ Success: {ok}\n")
            self.results_text.insert(tk.END, f"❌ Failed: {failed}\n")
            self.results_text.insert(tk.END, f"⏭️ Skipped (not SELECT): {skipped}\n")
            self.results_text.insert(tk.END, f"📁 Saved to: {file_path}\n")
            self.results_text.insert(tk.END, f"{'='*150}\n\n")
            self.results_text.see(tk.END)
            messagebox.showinfo(
                "Export Success",
                f"✅ Export Excel เรียบร้อย\n\n"
                f"📁 {file_path}\n\n"
                f"Success: {ok} | Failed: {failed} | Skipped: {skipped}",
            )

        def worker():
            import re

            illegal_chars = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")

            max_rows = 1048575  # Excel รองรับ 1,048,576 แถว (หัก header 1 แถว)
            used_names = set()
            ok = failed = skipped = 0
            fatal_error = None
            start_all = time_module.time()

            try:
                with pd.ExcelWriter(file_path, engine="openpyxl") as writer:
                    for idx, job in enumerate(jobs, 1):
                        if self._stop_event.is_set():
                            log(f"⏹ Stopped — {len(jobs) - idx + 1} job(s) not exported\n")
                            break
                        job_name = job.get("name", f"Job {idx}")
                        query = job["query"]
                        log(f"DEBUG Job Name : {job_name}\n")
                        t0 = time_module.time()

                        # ---- ตั้งชื่อ Sheet จากชื่อ Job (<=31 ตัว, ห้ามมี [ ] : * ? / \ , ห้ามซ้ำ) ----
                        base = re.sub(r"[\[\]\:\*\?\/\\]", "_", str(job_name)).strip().strip("'")
                        base = (base or f"Job{idx}")[:31]
                        sheet = base
                        n = 2
                        while sheet.lower() in used_names:
                            suffix = f"_{n}"
                            sheet = base[: 31 - len(suffix)] + suffix
                            n += 1
                        used_names.add(sheet.lower())

                        log(f"{'─'*150}\n")
                        log(f"▶️ Job #{idx}: {job_name}\n")
                        log(f"   Sheet: {sheet}\n")

                        try:
                            preloaded_df = job.get("_export_dataframe")
                            if preloaded_df is None and not self.is_select_query(query):
                                skipped += 1
                                log(
                                    "   Status: ⏭️ Skipped (ไม่ใช่ SELECT - ไม่รันซ้ำเพื่อความปลอดภัย)\n\n"
                                )
                                pd.DataFrame(
                                    {
                                        "Status": ["Skipped"],
                                        "Message": [
                                            "Not a SELECT query - not executed during export"
                                        ],
                                        "Query": [query],
                                    }
                                ).to_excel(writer, sheet_name=sheet, index=False)
                                continue
                            query_start = time_module.time()
                            df = (
                                preloaded_df.copy()
                                if preloaded_df is not None
                                else self.read_sql_dataframe(query)
                            )
                            query_elapsed = time_module.time() - query_start

                            log(f"Query Time : " f"{query_elapsed:.2f}s\n")
                            if df.empty:

                                log(f"   ⚠️ No Data Found\n")

                                pd.DataFrame(columns=df.columns).to_excel(
                                    writer, sheet_name=sheet, index=False
                                )

                                ws = writer.sheets[sheet]

                                start_row = 3

                                for line_no, line in enumerate(query.splitlines()):

                                    ws.cell(row=start_row + line_no, column=1, value=line)

                                ok += 1

                                continue

                            def clean_value(x):

                                if isinstance(x, bytes):

                                    try:
                                        x = x.decode("utf-16-le")

                                    except Exception:

                                        try:
                                            x = x.decode("utf-8")

                                        except Exception:
                                            x = str(x)

                                # Numbers / dates stay real Excel numbers / dates
                                # (like DBeaver); NULL becomes [NULL]
                                typed = excel_db_value(x)
                                if not isinstance(typed, str):
                                    return typed
                                value = typed.replace("\x00", "")

                                value = illegal_chars.sub("", value)

                                # Keep leading/trailing spaces (e.g. CHAR columns)
                                # so the data matches the database exactly
                                return value

                            for col in df.columns:

                                try:

                                    df[col] = df[col].map(clean_value)

                                except Exception:
                                    pass

                            import re

                            # ตัด timezone ออก (openpyxl เขียน datetime ที่มี tz ไม่ได้)
                            for col in df.columns:
                                if isinstance(df[col].dtype, pd.DatetimeTZDtype):
                                    df[col] = df[col].dt.tz_localize(None)
                                elif df[col].dtype == object:
                                    df[col] = df[col].map(
                                        lambda v: (
                                            illegal_chars.sub("", v) if isinstance(v, str) else v
                                        )
                                    )

                            total_rows = len(df)
                            if total_rows > max_rows:
                                df = df.iloc[:max_rows]
                                log(
                                    f"   ⚠️ Rows เกินขีดจำกัด Excel: export {max_rows:,} จาก {total_rows:,} แถว\n"
                                )
                                log(f"Writing Sheet: {sheet}\n")
                                log(f"Rows: {len(df)}\n")
                                log(f"Columns: {len(df.columns)}\n")
                            from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE

                            def preserve_illegal_chars(value):
                                if pd.isna(value):
                                    return ""

                                value = str(value)

                                value = value.replace("\x00", "")

                                value = illegal_chars.sub("", value)

                                return value.strip()

                            # Clean column names
                            df.columns = [
                                ILLEGAL_CHARACTERS_RE.sub("", str(col)) for col in df.columns
                            ]

                            log(f"Writing Sheet: {sheet}\n")
                            log(f"Rows: {len(df)}\n")
                            log(f"Columns: {len(df.columns)}\n")
                            df.to_excel(writer, sheet_name=sheet, index=False)

                            log(f"✅ Sheet Exported: {sheet}\n\n")

                            ws = writer.sheets[sheet]

                            # =====================================
                            # Header Color (มีข้อมูลหรือไม่มีข้อมูลก็ทำงาน)
                            # =====================================

                            header_fill = PatternFill(fill_type="solid", fgColor="BC9BFF")

                            if ws.max_column > 0:

                                for header_cell in ws[1]:

                                    header_cell.fill = header_fill

                            # =========================================
                            # Append Original SQL Query
                            # =========================================

                            try:
                                sql_text = query
                                start_row = ws.max_row + 2

                                for line_no, line in enumerate(sql_text.splitlines()):

                                    cell = ws.cell(row=start_row + line_no, column=1, value=line)

                            except Exception as e:

                                log(f"Failed to append SQL: {str(e)}\n")
                            ws.freeze_panes = "A2"
                            thin = Side(border_style="thin", color="000000")
                            all_border = Border(left=thin, right=thin, top=thin, bottom=thin)

                            sample_df = df.head(1000)

                            sample_df = df.head(1000)

                            # ใช้แค่ 1000 แถวแรกในการคำนวณความกว้าง
                            sample_df = df.head(1000)

                            for col_idx, col_name in enumerate(df.columns, 1):

                                letter = openpyxl.utils.get_column_letter(col_idx)

                                max_len = len(str(col_name)) + 2

                                try:

                                    longest_value = sample_df[col_name].astype(str).map(len).max()

                                    if pd.isna(longest_value):
                                        longest_value = 0

                                    max_len = max(max_len, longest_value + 2)

                                except Exception:
                                    pass

                                ws.column_dimensions[letter].width = min(max_len, 80)

                            # ใส่ Border เฉพาะ Header + Data เท่านั้น
                            data_last_row = max(len(df) + 1, 1)
                            for row in ws.iter_rows(min_row=1, max_row=data_last_row):
                                data_last_row = max(len(df) + 1, 1)

                            for row in ws.iter_rows(min_row=1, max_row=data_last_row):
                                for cell in row:
                                    cell.number_format = excel_number_format(cell.value)
                                    cell.border = all_border

                            # Header ต้องมีสีเสมอ แม้ไม่มี Data

                            if ws.max_column > 0:
                                for cell in ws[1]:

                                    cell.fill = header_fill
                                    cell.border = all_border
                                    cell.number_format = "@"
                            ok += 1
                            log(f"   Status: ✅ Success ({time_module.time() - t0:.2f}s)\n")
                            log(f"   Rows: {len(df):,} | Columns: {df.shape[1]}\n\n")
                        except Exception as job_err:
                            failed += 1
                            import traceback

                            log("\n=================================\n")
                            log(f"Job Failed : {job_name}\n")
                            log(f"Sheet : {sheet}\n")
                            log(f"Error Type : {type(job_err).__name__}\n")
                            log(f"Error : {str(job_err)}\n")
                            log(traceback.format_exc())
                            log("\n=================================\n")

                            # ยังสร้าง Sheet ของ Job นี้ไว้ เพื่อให้ 1 Job = 1 Sheet ครบ
                            pd.DataFrame(
                                {"Status": ["Failed"], "Error": [str(job_err)], "Query": [query]}
                            ).to_excel(writer, sheet_name=sheet, index=False)

            except Exception as e:
                fatal_error = f"{type(e).__name__}: {str(e)}"

            elapsed = time_module.time() - start_all
            self.root.after(0, lambda: on_done(ok, failed, skipped, elapsed, fatal_error))

        threading.Thread(target=worker, daemon=True).start()

    def show_batch_error(self, error):
        """Show batch execution error"""
        self.results_text.insert(tk.END, f"\n❌ BATCH EXECUTION ERROR\n")
        self.results_text.insert(tk.END, f"{'='*150}\n")
        self.results_text.insert(tk.END, f"Error: {str(error)}\n\n")
        self.results_text.see(tk.END)
        self._clear_results_grid("❌ Batch execution error — see Execution Logs")

        # Re-enable buttons
        self.execute_btn.config(state="normal")
        self.inspect_btn.config(state="normal")
        self.save_job_btn.config(state="normal")
        self._batch_running = False
        self.run_all_btn.config(state="normal")

    def show_critical_error(self, operation, error_msg):
        """Show critical error message when data modification fails"""
        self.results_text.insert(tk.END, f"\n{'='*150}\n")
        self.results_text.insert(tk.END, f"🛑 CRITICAL ERROR - Batch Execution Stopped!\n")
        self.results_text.insert(tk.END, f"{'='*150}\n\n")
        self.results_text.insert(tk.END, f"⚠️ {operation} statement failed!\n")
        self.results_text.insert(
            tk.END, f"⚠️ Stopping all remaining jobs to prevent data corruption.\n\n"
        )
        self.results_text.insert(tk.END, f"Error Details:\n{error_msg}\n\n")
        self.results_text.insert(tk.END, f"{'─'*150}\n")
        self.results_text.insert(tk.END, f"💡 Please fix the error and try again.\n")
        self.results_text.insert(tk.END, f"{'='*150}\n\n")
        self.results_text.see(tk.END)

        # Re-enable buttons
        self.execute_btn.config(state="normal")
        self.inspect_btn.config(state="normal")
        self.save_job_btn.config(state="normal")

    def load_selected_job(self):
        """Load the selected job into the SQL editor"""
        selection = self.jobs_listbox.curselection()
        if not selection:
            messagebox.showwarning("Warning", "Please select a job to load")
            return

        job_idx = selection[0]
        if job_idx >= len(self.saved_jobs):
            return

        job = self.saved_jobs[job_idx]

        # Load query to editor
        self.sql_context.delete(1.0, tk.END)
        self.sql_context.insert(1.0, job["query"])
        self._apply_job_excel_state(job)

        self.results_text.insert(tk.END, f"📝 Loaded job: {job['name']}\n")
        self.results_text.insert(tk.END, f"   Database: {job.get('database', 'N/A')}\n")
        self.results_text.insert(tk.END, f"   Created: {job.get('created', 'N/A')}\n\n")
        self.results_text.see(tk.END)

    def delete_selected_job(self):
        """Delete the selected job"""
        selection = self.jobs_listbox.curselection()
        if not selection:
            messagebox.showwarning("Warning", "Please select a job to delete")
            return

        job_idx = selection[0]
        if job_idx >= len(self.saved_jobs):
            return

        job = self.saved_jobs[job_idx]

        result = messagebox.askyesno(
            "Confirm Delete", f"Delete job '{job['name']}'?\n\nThis cannot be undone."
        )
        if result:
            deleted_job = self.saved_jobs.pop(job_idx)
            self.save_jobs()
            self.update_jobs_list()

            self.results_text.insert(tk.END, f"🗑️ Deleted job: {deleted_job['name']}\n")
            self.results_text.insert(tk.END, f"   Remaining jobs: {len(self.saved_jobs)}\n\n")
            self.results_text.see(tk.END)

            messagebox.showinfo("Success", f"Job '{deleted_job['name']}' deleted successfully!")

    def load_profiles(self):
        """โหลด saved profiles จากไฟล์ (ถอดรหัส password ให้อัตโนมัติ)"""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                # กรอง last_used_profile ออก (ไม่ใช่ profile จริง)
                profiles = {
                    k: dict(v)
                    for k, v in data.items()
                    if k != "last_used_profile" and isinstance(v, dict)
                }
                for profile in profiles.values():
                    if "db_password" in profile:
                        profile["db_password"] = unprotect_password(profile["db_password"])
                return profiles
            except:
                return {}
        return {}

    def _profiles_for_disk(self, last_used_profile=None):
        """สร้างข้อมูลสำหรับเขียนไฟล์ - password ถูกเข้ารหัส, คง last_used_profile เดิมไว้"""
        data = {}
        for name, profile in self.saved_profiles.items():
            profile_copy = dict(profile)
            if profile_copy.get("db_password"):
                profile_copy["db_password"] = protect_password(profile_copy["db_password"])
            data[name] = profile_copy

        if last_used_profile is None:
            last_used_profile = self.get_last_used_profile()
        if last_used_profile and last_used_profile in self.saved_profiles:
            data["last_used_profile"] = last_used_profile
        return data

    def save_profiles(self):
        """บันทึก profiles ลงไฟล์ - ENHANCED with debugging"""
        try:
            # Ensure directory exists
            config_dir = os.path.dirname(self.config_file)
            if config_dir and not os.path.exists(config_dir):
                os.makedirs(config_dir)

            data = self._profiles_for_disk()

            # Save with explicit encoding
            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

        except Exception as e:
            error_msg = f"❌ Cannot save profile!\n\nError: {str(e)}\n\nPath: {self.config_file}"
            print(error_msg)
            messagebox.showerror("Save Error", error_msg)

    def save_last_used_profile(self, profile_name):
        """บันทึก profile ล่าสุดที่ใช้"""
        try:
            data = self._profiles_for_disk(last_used_profile=profile_name)

            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Failed to save last used profile: {str(e)}")

    def get_last_used_profile(self):
        """ดึง profile ล่าสุดที่ใช้"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return data.get("last_used_profile", None)
        except:
            pass
        return None

    def update_profile_list(self):

        profile_names = list(self.saved_profiles.keys())

        self.profile_combo["values"] = profile_names

        if profile_names:
            self.profile_combo.current(0)

        if hasattr(self, "jobs_container"):
            self.update_jobs_list()

    def on_profile_selected(self, event=None):

        profile_name = self.profile_combo.get()

        if profile_name and profile_name in self.saved_profiles:
            self.load_profile_data(profile_name)

        self.update_jobs_list()

    def _reset_profile_session_state(self):
        """Profile load/switch: return Excel + connection indicators to startup defaults.

        Default status bar afterwards: Ready | Not Connected | No Excel Loaded
        """
        # Excel session (cached file + parameter state) — same values as __init__
        self.loaded_excel_data = None
        self._excel_parameter_values.clear()
        self._excel_parameterized_sql = None
        self.sql_template = None
        self._excel_selected_values = []

        # Connection session
        self._reset_profile_connection_state(self.engine)

    def _reset_profile_connection_state(self, engine_at_switch):
        """Clear the previous profile's connection; waits if a query/job is still running."""
        if self.engine is not engine_at_switch:
            return  # user already reconnected after the switch — keep the new connection

        busy = any(
            "Loading" in str(b.cget("text")) for b in (self.execute_btn, self.inspect_btn)
        ) or (self.engine is not None and str(self.execute_btn["state"]) == "disabled")
        if busy:
            self.root.after(500, lambda: self._reset_profile_connection_state(engine_at_switch))
            return

        engine, self.engine = self.engine, None
        if engine is not None:
            try:
                engine.dispose()
            except Exception:
                pass

        self.status_label.config(text="❌ Not Connected", foreground="#e74c3c")
        self.execute_btn.config(state="disabled")
        self.inspect_btn.config(state="disabled")

    def load_profile_data(self, profile_name):
        """โหลดข้อมูลจาก profile"""
        try:
            config = self.saved_profiles[profile_name]

            # Fresh session for this profile: Ready | Not Connected | No Excel Loaded
            self._reset_profile_session_state()

            # Update UI fields
            if "db_type" in config:
                self.db_type.set(config["db_type"])
            if "db_user" in config:
                self.db_user.delete(0, tk.END)
                self.db_user.insert(0, config["db_user"])
            if "db_password" in config:
                self.db_password.delete(0, tk.END)
                self.db_password.insert(0, config["db_password"])
            if "db_host" in config:
                self.db_host.delete(0, tk.END)
                self.db_host.insert(0, config["db_host"])
            if "db_port" in config:
                # Clean port value when loading - remove duplicates like '3802:3802'
                port_value = str(config["db_port"]).strip()
                if ":" in port_value:
                    port_value = port_value.split(":")[0]
                self.db_port.delete(0, tk.END)
                self.db_port.insert(0, port_value)
            if "db_name" in config:
                self.db_name.delete(0, tk.END)
                self.db_name.insert(0, config["db_name"])
            if "sql_query" in config:
                self.sql_context.delete(1.0, tk.END)
                self.sql_context.insert(1.0, config["sql_query"].strip() or self.DEFAULT_SQL_QUERY)

            self.results_text.insert(tk.END, f"📂 Loaded profile: {profile_name}\n\n")

            self.update_jobs_list()
            self.results_text.see(tk.END)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load profile:\n{str(e)}")

    def auto_load_last_profile(self):
        """Auto-load profile ล่าสุดที่ใช้"""
        last_profile = self.get_last_used_profile()
        if last_profile and last_profile in self.saved_profiles:
            # Set combobox to last profile
            profile_names = list(self.saved_profiles.keys())
            if last_profile in profile_names:
                self.profile_combo.current(profile_names.index(last_profile))
                self.load_profile_data(last_profile)
                self.results_text.insert(tk.END, f"✅ Auto-loaded last profile: {last_profile}\n\n")

    def save_profile_dialog(self):
        """แสดง dialog สำหรับบันทึก profile"""
        dialog = tk.Toplevel(self.root)
        dialog.title("Save Profile")
        dialog.geometry("400x250")
        dialog.transient(self.root)
        dialog.grab_set()

        # Center dialog
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - (dialog.winfo_width() // 2)
        y = (dialog.winfo_screenheight() // 2) - (dialog.winfo_height() // 2)
        dialog.geometry(f"+{x}+{y}")

        ttk.Label(dialog, text="Profile Name:").pack(pady=(20, 5))
        name_entry = ttk.Entry(dialog, width=40)
        name_entry.pack(pady=5)
        name_entry.focus()

        # ถ้ามี profile ปัจจุบัน ให้แสดงชื่อเดิม
        current_profile = self.profile_combo.get()
        if current_profile:
            name_entry.insert(0, current_profile)

        if self.saved_profiles:
            ttk.Label(
                dialog,
                text="(Existing profiles will be overwritten)",
                font=("Arial", 8),
                foreground="gray",
            ).pack()

        def save():
            profile_name = name_entry.get().strip()
            if not profile_name:
                messagebox.showwarning("Warning", "กรุณาใส่ชื่อ Profile", parent=dialog)
                return

            # Clean port before saving
            port_value = self.db_port.get().strip()
            if ":" in port_value:
                port_value = port_value.split(":")[0]
                # Update field with cleaned value
                self.db_port.delete(0, tk.END)
                self.db_port.insert(0, port_value)

            # บันทึก settings
            self.saved_profiles[profile_name] = {
                "db_type": self.db_type.get(),
                "db_user": self.db_user.get(),
                "db_password": self.db_password.get(),  # บันทึก password ด้วย
                "db_host": self.db_host.get(),
                "db_port": port_value,  # Use cleaned port value
                "db_name": self.db_name.get(),
                "sql_query": self.sql_context.get(1.0, tk.END).strip(),
            }
            self.save_profiles()

            # บันทึก last used profile
            self.save_last_used_profile(profile_name)

            # อัพเดต combobox
            self.update_profile_list()
            profile_names = list(self.saved_profiles.keys())
            if profile_name in profile_names:
                self.profile_combo.current(profile_names.index(profile_name))

            self.results_text.insert(tk.END, f"💾 Saved profile: {profile_name}\n\n")
            self.results_text.see(tk.END)

            messagebox.showinfo(
                "Success", f"บันทึก Profile '{profile_name}' เรียบร้อย", parent=dialog
            )
            dialog.destroy()

        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(pady=10)
        ttk.Button(btn_frame, text="Save", command=save).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Cancel", command=dialog.destroy).pack(side=tk.LEFT, padx=5)

    def new_profile_dialog(self):
        """แสดง dialog สำหรับสร้าง Profile ใหม่ (กรอกข้อมูลการเชื่อมต่อทั้งหมด)"""
        port_defaults = {
            "PostgreSQL": "5432",
            "MySQL": "3306",
            "Microsoft SQL Server": "1433",
            "Oracle": "1521",
        }
        CARD = UI["card"]

        dialog = self._create_centered_dialog("New Profile", 620, 720)
        dialog.configure(bg=CARD)
        dialog.resizable(False, False)

        body = tk.Frame(dialog, bg=CARD)
        body.pack(fill="both", expand=True, padx=24, pady=(20, 12))
        body.columnconfigure(0, weight=1)

        # Heading
        head = tk.Frame(body, bg=CARD)
        head.pack(fill="x", pady=(0, 14))
        badge = tk.Canvas(head, width=40, height=40, bg=CARD, highlightthickness=0)
        badge.create_oval(1, 1, 39, 39, fill="#DBEAFE", outline="#DBEAFE")
        badge.create_text(20, 20, text="🛢", fill=UI["primary"], font=("Segoe UI", 13))
        badge.pack(side="left", padx=(0, 14))
        titles = tk.Frame(head, bg=CARD)
        titles.pack(side="left", fill="x")
        tk.Label(titles, text="สร้าง Profile ใหม่", bg=CARD, fg=UI["text"],
                 font=("Segoe UI Semibold", 13)).pack(anchor="w")
        tk.Label(titles, text="บันทึกข้อมูลเชื่อมต่อไว้ใช้ครั้งถัดไป เลือก Profile แล้วกด Connect ได้เลย",
                 bg=CARD, fg=UI["muted"], font=UI_FONT_SM).pack(anchor="w")

        def label(parent, text, required=False):
            row = tk.Frame(parent, bg=CARD)
            row.pack(fill="x", pady=(0, 4))
            tk.Label(row, text=text, bg=CARD, fg=UI["text"], font=UI_FONT_LABEL).pack(side="left")
            if required:
                tk.Label(row, text="*", bg=CARD, fg=UI["danger"], font=UI_FONT_LABEL).pack(side="left")

        def helper(parent, text):
            tk.Label(parent, text=text, bg=CARD, fg=UI["muted"], font=UI_FONT_SM,
                     anchor="w").pack(fill="x", pady=(3, 0))

        def entry(parent, show=None):
            e = ttk.Entry(parent, font=UI_FONT, style="Fluent.TEntry", show=show or "")
            e.pack(fill="x")
            return e

        def field(parent, text, required=False, show=None, hint=None):
            box = tk.Frame(parent, bg=CARD)
            label(box, text, required)
            e = entry(box, show)
            if hint:
                helper(box, hint)
            return box, e

        # Profile name
        box, name_entry = field(body, "ชื่อ Profile", True,
                                hint="ตั้งให้รู้ว่าต่อที่ไหน เช่น uat select, prod readonly")
        box.pack(fill="x", pady=(0, 14))

        # Database type: 4 cards
        type_box = tk.Frame(body, bg=CARD)
        type_box.pack(fill="x", pady=(0, 14))
        label(type_box, "ประเภทฐานข้อมูล", True)
        type_var = tk.StringVar(value="PostgreSQL")
        cards_row = tk.Frame(type_box, bg=CARD)
        cards_row.pack(fill="x")
        type_cards = {}
        for col, (db, title) in enumerate((("Oracle", "Oracle"), ("PostgreSQL", "PostgreSQL"),
                                           ("MySQL", "MySQL"), ("Microsoft SQL Server", "SQL Server"))):
            cards_row.columnconfigure(col, weight=1, uniform="type")
            _type_outer, card = ui_round_frame(cards_row, fill=CARD, border=UI["border_strong"], radius=8, pad=2)
            _type_outer.grid(row=0, column=col, sticky="ew", padx=(0 if col == 0 else 8, 0))
            card.configure(cursor="hand2")
            t = tk.Label(card, text=title, bg=CARD, fg=UI["text"], font=UI_FONT_SEMI, anchor="w")
            t.pack(fill="x", padx=12, pady=(8, 0))
            p = tk.Label(card, text=f"port {port_defaults[db]}", bg=CARD, fg=UI["muted"],
                         font=UI_FONT_SM, anchor="w")
            p.pack(fill="x", padx=12, pady=(0, 8))
            for w in (card, t, p):
                w.bind("<Button-1>", lambda _e, v=db: type_var.set(v))
            type_cards[db] = (card, t, p)

        tk.Frame(body, bg=UI["border"], height=1).pack(fill="x", pady=(0, 12))
        tk.Label(body, text="การเชื่อมต่อ", bg=CARD, fg=UI["text"],
                 font=("Segoe UI Semibold", 11)).pack(anchor="w", pady=(0, 8))

        # Host + Port
        row1 = tk.Frame(body, bg=CARD)
        row1.pack(fill="x", pady=(0, 12))
        row1.columnconfigure(0, weight=3)
        row1.columnconfigure(1, weight=1)
        hb, host_entry = field(row1, "Host", True)
        hb.grid(row=0, column=0, sticky="new", padx=(0, 12))
        pb, port_entry = field(row1, "Port", True, hint="ใส่ให้อัตโนมัติตามประเภท")
        pb.grid(row=0, column=1, sticky="new")
        port_entry.insert(0, port_defaults["PostgreSQL"])

        db_box, dbname_entry = field(body, "Database / Service Name",
                                     hint="Oracle ใส่ Service Name · SQL Server ถ้าว่างจะต่อ master")
        db_box.pack(fill="x", pady=(0, 12))

        # User + Password
        row2 = tk.Frame(body, bg=CARD)
        row2.pack(fill="x", pady=(0, 12))
        row2.columnconfigure(0, weight=1, uniform="up")
        row2.columnconfigure(1, weight=1, uniform="up")
        ub, user_entry = field(row2, "User", True)
        ub.grid(row=0, column=0, sticky="new", padx=(0, 12))
        pwb, pass_entry = field(row2, "Password", True, show="*")
        pwb.grid(row=0, column=1, sticky="new")
        pass_entry.configure(style="Password.Fluent.TEntry")
        eye = tk.Label(pass_entry, text=PASSWORD_ICON_SHOW, font=("Segoe MDL2 Assets", 11),
                       bg="#FFFFFF", fg=UI["muted"], cursor="hand2", bd=0, padx=4)
        eye.place(relx=1.0, rely=0.5, x=-6, anchor="e")

        def _toggle_eye(_e=None):
            showing = pass_entry.cget("show") == ""
            pass_entry.configure(show="*" if showing else "")
            eye.config(text=PASSWORD_ICON_SHOW if showing else PASSWORD_ICON_HIDE)

        eye.bind("<Button-1>", _toggle_eye)

        # Test result (hidden until "Test connection" is used)
        _result_outer, result_box = ui_round_frame(body, fill=CARD, radius=8, pad=1)
        _result_outer.pack(fill="x")
        result_label = tk.Label(result_box, text="", bg=CARD, font=UI_FONT_SEMI, anchor="w",
                                justify="left", wraplength=540)

        def _on_type_change(*_):
            db = type_var.get()
            port_entry.delete(0, tk.END)
            port_entry.insert(0, port_defaults.get(db, "5432"))
            for key, (card, t, p) in type_cards.items():
                on = key == db
                bg = "#EFF6FF" if on else CARD
                ui_round_frame_set(card, bg, UI["primary"] if on else UI["border_strong"])
                t.config(bg=bg, fg=UI["primary"] if on else UI["text"],
                         text=(("✓  " if on else "") + t.cget("text").replace("✓  ", "")))
                p.config(bg=bg)

        type_var.trace_add("write", _on_type_change)
        _on_type_change()
        port_entry.delete(0, tk.END)
        port_entry.insert(0, port_defaults["PostgreSQL"])
        name_entry.focus_set()

        for _w in (name_entry, host_entry, port_entry, user_entry, pass_entry, dbname_entry):
            _w.bind("<Return>", lambda _e: create())

        def test_connection():
            """Try the entered details with a throw-away connection (main one untouched)."""
            db_type = type_var.get()
            args = (db_type, user_entry.get().strip(), pass_entry.get(), host_entry.get().strip(),
                    port_entry.get().strip().split(":")[0], dbname_entry.get().strip())
            result_label.config(text="⏳  กำลังทดสอบการเชื่อมต่อ…", bg="#FEF3C7", fg=UI["warn"])
            ui_round_frame_set(result_box, "#FEF3C7")
            result_label.pack(fill="x", padx=12, pady=10)
            test_btn.config(state="disabled")

            def work():
                import time as _time

                start = _time.perf_counter()
                try:
                    engine = create_engine(
                        self.get_connection_string(*args), connect_args=self.get_connect_args(db_type)
                    )
                    try:
                        with engine.connect() as conn:
                            conn.execute(text("SELECT 1 FROM DUAL" if db_type == "Oracle" else "SELECT 1"))
                    finally:
                        engine.dispose()
                    outcome = (True, f"✓  ทดสอบเชื่อมต่อสำเร็จ · {db_type} · {int((_time.perf_counter() - start) * 1000)} ms")
                except Exception as error:
                    first = next((ln for ln in str(error).splitlines() if ln.strip()), str(error))
                    outcome = (False, f"✕  เชื่อมต่อไม่สำเร็จ: {first.strip()}")

                def show():
                    if not dialog.winfo_exists():
                        return
                    ok, msg = outcome
                    bg, fg = (UI["success_soft"], UI["success"]) if ok else (UI["danger_soft"], UI["danger"])
                    ui_round_frame_set(result_box, bg)
                    result_label.config(text=msg if len(msg) <= 300 else msg[:299] + "…", bg=bg, fg=fg)
                    test_btn.config(state="normal")

                try:
                    dialog.after(0, show)
                except (tk.TclError, RuntimeError):
                    pass

            threading.Thread(target=work, daemon=True).start()

        def create():
            profile_name = name_entry.get().strip()
            if not profile_name:
                messagebox.showwarning("Warning", "กรุณาใส่ชื่อ Profile", parent=dialog)
                name_entry.focus_set()
                return
            if profile_name == "last_used_profile":
                messagebox.showwarning("Warning", "ชื่อนี้สงวนไว้ กรุณาใช้ชื่ออื่น", parent=dialog)
                return
            if profile_name in self.saved_profiles:
                messagebox.showwarning(
                    "Warning",
                    f"มี Profile '{profile_name}' อยู่แล้ว\n" "กรุณาใช้ชื่ออื่น",
                    parent=dialog,
                )
                name_entry.focus_set()
                return
            if not host_entry.get().strip():
                messagebox.showwarning("Warning", "กรุณาใส่ Host", parent=dialog)
                host_entry.focus_set()
                return

            port_value = port_entry.get().strip()
            if ":" in port_value:
                port_value = port_value.split(":")[0]

            self.saved_profiles[profile_name] = {
                "db_type": type_var.get(),
                "db_user": user_entry.get().strip(),
                "db_password": pass_entry.get(),
                "db_host": host_entry.get().strip(),
                "db_port": port_value,
                "db_name": dbname_entry.get().strip(),
                "sql_query": self.DEFAULT_SQL_QUERY,
            }
            self.save_profiles()
            self.save_last_used_profile(profile_name)

            # เลือก Profile ใหม่และโหลดข้อมูลเข้าฟอร์ม
            self.update_profile_list()
            profile_names = list(self.saved_profiles.keys())
            self.profile_combo.current(profile_names.index(profile_name))
            self.load_profile_data(profile_name)

            self.results_text.insert(tk.END, f"➕ Created profile: {profile_name}\n\n")
            self.results_text.see(tk.END)
            dialog.destroy()
            messagebox.showinfo("Success", f"สร้าง Profile '{profile_name}' เรียบร้อย")

        # Footer
        tk.Frame(dialog, bg=UI["border"], height=1).pack(fill="x")
        footer = tk.Frame(dialog, bg=UI["surface"])
        footer.pack(fill="x")
        _test_outer, test_btn = ui_button(footer, "🔌  ทดสอบการเชื่อมต่อ", test_connection,
                                          kind="secondary", size="md")
        _test_outer.pack(side=tk.LEFT, padx=24, pady=12)
        _create_outer, _ = ui_button(footer, "＋  สร้าง Profile", create, kind="primary", size="md")
        _create_outer.pack(side=tk.RIGHT, padx=(6, 24), pady=12)
        _cancel_outer, _ = ui_button(footer, "ยกเลิก", dialog.destroy, kind="secondary", size="md")
        _cancel_outer.pack(side=tk.RIGHT, pady=12)

        dialog.bind("<Escape>", lambda _e: dialog.destroy())

        # Size the dialog to its content (and leave room for the test result)
        dialog.update_idletasks()
        w, h = 620, dialog.winfo_reqheight() + 56
        x = (dialog.winfo_screenwidth() - w) // 2
        y = max((dialog.winfo_screenheight() - h) // 2, 0)
        dialog.geometry(f"{w}x{h}+{x}+{y}")

    def delete_profile(self):
        """ลบ profile ที่เลือก"""
        profile_name = self.profile_combo.get()
        if not profile_name:
            messagebox.showwarning("Warning", "กรุณาเลือก Profile ที่ต้องการลบ")
            return

        if profile_name not in self.saved_profiles:
            messagebox.showwarning("Warning", "ไม่พบ Profile นี้")
            return

        result = messagebox.askyesno(
            "Confirm Delete", f"ต้องการลบ Profile '{profile_name}' หรือไม่?"
        )
        if result:
            del self.saved_profiles[profile_name]
            self.save_profiles()
            self.update_profile_list()
            self.results_text.insert(tk.END, f"🗑️ Deleted profile: {profile_name}\n\n")
            self.results_text.see(tk.END)

            messagebox.showinfo("Success", f"ลบ Profile '{profile_name}' เรียบร้อย")

    @staticmethod
    def _excel_state_for_job(query, template, values, rendered):
        """Return job fields that keep the Excel parameter state of a query."""
        query = (query or "").strip()
        if values and template is not None and rendered is not None and query == rendered.strip():
            return {
                "sql_template": template,
                "excel_parameters": {key: list(data) for key, data in values.items()},
            }
        return {}

    @staticmethod
    def _excel_state_from_job(job):
        """Return (template, values, rendered) stored on a job."""
        query = job.get("query", "")
        template = job.get("sql_template")
        stored = job.get("excel_parameters") or {}
        values = {
            key: tuple(data)
            for key, data in stored.items()
            if isinstance(data, (list, tuple)) and len(data) == 2
        }
        if template is None or not values:
            return query, {}, None
        return template, values, query

    def _apply_job_excel_state(self, job):
        """Restore Excel parameter state in the main editor for a loaded job."""
        template, values, rendered = self._excel_state_from_job(job)
        self.sql_template = template
        self._excel_parameter_values = values
        self._excel_parameterized_sql = rendered

    def _capture_sql_template(self, current_sql):
        current_sql = current_sql.rstrip("\n")
        has_rendered_sql = self._excel_parameterized_sql is not None
        query_was_edited = (has_rendered_sql and current_sql != self._excel_parameterized_sql) or (
            not has_rendered_sql
            and self.sql_template is not None
            and current_sql != self.sql_template
        )

        if self.sql_template is None or query_was_edited:
            self.sql_template = current_sql
            self._excel_parameter_values.clear()
            self._excel_parameterized_sql = None
            if self.debug_mode.get():
                print("[Excel Parameter Debug] Captured new SQL template")

        return self.sql_template

    def _format_excel_sql_values(self, values):
        import numbers

        formatted_values = []

        for value in values:

            if pd.isna(value):
                continue

            # Convert to string and clean unwanted quotes
            cleaned_value = str(value).strip()

            # Remove quotes accidentally coming from Excel
            cleaned_value = cleaned_value.rstrip("'")
            cleaned_value = cleaned_value.rstrip('"')

            if isinstance(value, numbers.Number) and not isinstance(value, bool):

                if isinstance(value, float) and value.is_integer():
                    formatted_values.append(str(int(value)))
                else:
                    formatted_values.append(str(value))

            else:

                # Escape single quotes inside the value (O'Brien -> 'O''Brien')
                escaped_value = cleaned_value.replace("'", "''")
                formatted_values.append(f"'{escaped_value}'")

        return ", ".join(formatted_values)

    # Marker stored as the "parameter" of an auto WHERE condition built from
    # an Excel column name (key = "WHERE <column>")
    AUTO_WHERE_PARAMETER = "__AUTO_WHERE__"

    @staticmethod
    def _sql_column_identifier(column_name):
        """Excel header -> SQL column (quoted only if it is not a plain name)."""
        column_name = str(column_name).strip()
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_$#]*(\.[A-Za-z_][A-Za-z0-9_$#]*)*", column_name):
            return column_name
        return '"' + column_name.replace('"', '""') + '"'

    @staticmethod
    def _append_where_conditions(sql, conditions):
        """Add WHERE (or AND when the SQL already has WHERE) conditions."""
        if not conditions:
            return sql
        body = sql.rstrip()
        semicolon = ""
        if body.endswith(";"):
            body, semicolon = body[:-1].rstrip(), ";"
        keyword = "AND" if re.search(r"\bWHERE\b", body, flags=re.IGNORECASE) else "WHERE"
        lines = []
        for column, sql_values in conditions:
            lines.append(f"{keyword} {column} IN ({sql_values})")
            keyword = "AND"
        return body + "\n" + "\n".join(lines) + semicolon

    def _render_sql_template(self, parameter_values=None):
        import re

        if parameter_values is None:
            parameter_values = self._excel_parameter_values

        rendered_sql = self.sql_template
        where_conditions = []
        for parameter_key, parameter_data in parameter_values.items():
            parameter, sql_values = parameter_data
            if parameter == self.AUTO_WHERE_PARAMETER:
                where_conditions.append((parameter_key[len("WHERE ") :], sql_values))
                continue
            if parameter_key == "__FIRST_IN_LIST__":
                rendered_sql, replacements = re.subn(
                    r"(\bIN\s*\()\s*[^)]*(\))",
                    lambda match: f"{match.group(1)}{sql_values}{match.group(2)}",
                    rendered_sql,
                    count=1,
                    flags=re.IGNORECASE,
                )
                if not replacements:
                    raise ValueError("SQL template no longer contains an IN (...) list")
                continue

            if parameter.startswith(":"):
                token_pattern = r"(?P<quote>['\"]?)" + re.escape(parameter) + r"(?P=quote)"
            else:
                parameter_name = parameter.strip("{}").strip()
                token_pattern = (
                    r"(?P<quote>['\"]?)\{\{?\s*" + re.escape(parameter_name) + r"\s*\}\}?(?P=quote)"
                )
            rendered_sql, replacements = re.subn(
                token_pattern, lambda _match: sql_values, rendered_sql, flags=re.IGNORECASE
            )
            if not replacements:
                raise ValueError(f"Parameter {parameter} is not present in the SQL template")

        return self._append_where_conditions(rendered_sql, where_conditions)

    def reset_single_parameter(self, parameter_key):
        if parameter_key not in self._excel_parameter_values:
            return

        previous_value = self._excel_parameter_values.pop(parameter_key)
        try:
            rendered_sql = (
                self._render_sql_template() if self._excel_parameter_values else self.sql_template
            )
        except Exception as error:
            self._excel_parameter_values[parameter_key] = previous_value
            messagebox.showerror("Reset Error", str(error), parent=self.root)
            return

        self.sql_context.delete("1.0", tk.END)
        self.sql_context.insert("1.0", rendered_sql)
        self._excel_parameterized_sql = rendered_sql if self._excel_parameter_values else None

    def reset_all_parameters(self):
        self._excel_parameter_values.clear()
        self._excel_parameterized_sql = None
        if self.sql_template is not None:
            self.sql_context.delete("1.0", tk.END)
            self.sql_context.insert("1.0", self.sql_template)
        if self.debug_mode.get():
            print("[Excel Parameter Debug] All parameters reset to SQL template")
        messagebox.showinfo(
            "Reset SQL Template", "All parameters have been reset.", parent=self.root
        )

    def show_reset_parameter_dialog(self, close_after_selected=False, wait=False):
        if not self._excel_parameter_values:
            messagebox.showwarning("Reset Parameter", "No parameter loaded", parent=self.root)
            return

        dialog = tk.Toplevel(self.root)
        dialog.title("Reset Parameter")
        dialog.geometry("550x450")
        dialog.configure(bg=UI["card"])
        dialog.transient(self.root)
        dialog.grab_set()

        # Header
        header = tk.Frame(dialog, bg=UI["card"])
        header.pack(fill="x", padx=20, pady=(16, 10))
        ttk.Label(header, text="Select parameter to reset", font=UI_FONT_TITLE).pack(anchor="w")
        tk.Label(
            header,
            text="Restore a replaced Excel parameter back to its placeholder in the SQL template.",
            bg=UI["card"],
            fg=UI["muted"],
            font=UI_FONT_SM,
            wraplength=500,
            justify="left",
        ).pack(anchor="w", pady=(2, 0))
        tk.Frame(dialog, bg=UI["border"], height=1).pack(fill="x")

        tk.Label(
            dialog, text="LOADED PARAMETERS", bg=UI["card"], fg=UI["muted"], font=UI_FONT_LABEL
        ).pack(anchor="w", padx=20, pady=(12, 4))

        # Checkbox list (scrollable) so several parameters can be reset at once
        list_border = tk.Frame(
            dialog, bg="#FFFFFF", highlightthickness=1, highlightbackground=UI["border"]
        )
        list_border.pack(fill="both", expand=True, padx=20, pady=(0, 12))
        list_scroll = ttk.Scrollbar(list_border, orient="vertical")
        list_canvas = tk.Canvas(
            list_border, bg="#FFFFFF", highlightthickness=0, bd=0, yscrollcommand=list_scroll.set
        )
        list_scroll.config(command=list_canvas.yview)
        list_scroll.pack(side="right", fill="y")
        list_canvas.pack(side="left", fill="both", expand=True)
        list_inner = tk.Frame(list_canvas, bg="#FFFFFF")
        inner_window = list_canvas.create_window((0, 0), window=list_inner, anchor="nw")
        list_inner.bind(
            "<Configure>", lambda _e: list_canvas.configure(scrollregion=list_canvas.bbox("all"))
        )
        list_canvas.bind(
            "<Configure>", lambda e: list_canvas.itemconfigure(inner_window, width=e.width)
        )

        def _on_list_wheel(event):
            if list_inner.winfo_height() > list_canvas.winfo_height():
                list_canvas.yview_scroll(int(-event.delta / 120), "units")
            return "break"

        list_canvas.bind("<MouseWheel>", _on_list_wheel)
        list_inner.bind("<MouseWheel>", _on_list_wheel)

        parameter_vars = {}  # parameter key -> BooleanVar

        def refresh_parameter_list():
            for widget in list_inner.winfo_children():
                widget.destroy()
            parameter_vars.clear()
            for parameter_key in self._excel_parameter_values:
                var = tk.BooleanVar(value=False)
                parameter_vars[parameter_key] = var
                check = tk.Checkbutton(
                    list_inner,
                    text=parameter_key,
                    variable=var,
                    anchor="w",
                    font=UI_FONT_MONO,
                    bg="#FFFFFF",
                    fg=UI["text"],
                    activebackground="#DBEAFE",
                    selectcolor="#FFFFFF",
                    relief="flat",
                    bd=0,
                    highlightthickness=0,
                )
                check.pack(fill="x", anchor="w", padx=6, pady=1)
                check.bind("<MouseWheel>", _on_list_wheel)
            list_canvas.yview_moveto(0)

        def reset_selected():
            selected_keys = [key for key, var in parameter_vars.items() if var.get()]
            if not selected_keys:
                messagebox.showwarning(
                    "Reset Parameter", "Please select at least one parameter", parent=dialog
                )
                return

            for parameter_key in selected_keys:
                self.reset_single_parameter(parameter_key)
            refresh_parameter_list()
            if close_after_selected or not self._excel_parameter_values:
                dialog.destroy()

        def reset_all():
            self.reset_all_parameters()
            dialog.destroy()

        # Footer actions: [Reset All Parameters]            [Close] [Reset Selected]
        tk.Frame(dialog, bg=UI["border"], height=1).pack(fill="x")
        button_frame = tk.Frame(dialog, bg=UI["surface"])
        button_frame.pack(fill="x")
        _outer, _ = ui_button(button_frame, "Reset All Parameters", reset_all, kind="danger")
        _outer.pack(side="left", padx=(20, 0), pady=12)
        ttk.Button(
            button_frame, text="Reset Selected", command=reset_selected, style="Accent.TButton"
        ).pack(side="right", padx=(6, 20), pady=12)
        ttk.Button(button_frame, text="Close", command=dialog.destroy).pack(side="right", pady=12)

        refresh_parameter_list()

        if wait:
            dialog.wait_window()

    @staticmethod
    def _read_file_bytes_shared(file_path):
        """Read a file even while it is open in Excel.

        Python's open() does not allow FILE_SHARE_DELETE, so it fails with
        PermissionError when Excel holds the workbook. On Windows, fall back to
        CreateFileW with full sharing (read-only, the file is never modified).
        """
        try:
            with open(file_path, "rb") as file:
                return file.read()
        except PermissionError:
            if os.name != "nt":
                raise

        from ctypes import wintypes

        GENERIC_READ = 0x80000000
        FILE_SHARE_ALL = 0x1 | 0x2 | 0x4  # READ | WRITE | DELETE
        OPEN_EXISTING = 3
        FILE_ATTRIBUTE_NORMAL = 0x80
        INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateFileW.argtypes = [
            wintypes.LPCWSTR,
            wintypes.DWORD,
            wintypes.DWORD,
            ctypes.c_void_p,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.HANDLE,
        ]
        kernel32.CreateFileW.restype = wintypes.HANDLE
        kernel32.ReadFile.argtypes = [
            wintypes.HANDLE,
            ctypes.c_void_p,
            wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD),
            ctypes.c_void_p,
        ]
        kernel32.ReadFile.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]

        handle = kernel32.CreateFileW(
            os.path.abspath(file_path),
            GENERIC_READ,
            FILE_SHARE_ALL,
            None,
            OPEN_EXISTING,
            FILE_ATTRIBUTE_NORMAL,
            None,
        )
        if handle is None or handle == INVALID_HANDLE_VALUE:
            error_code = ctypes.get_last_error()
            raise PermissionError(
                f"Cannot read '{file_path}' (Windows error {error_code}). "
                "Close the file in Excel and try again."
            )
        try:
            chunks = []
            buffer = ctypes.create_string_buffer(1024 * 1024)
            bytes_read = wintypes.DWORD(0)
            while True:
                if not kernel32.ReadFile(
                    handle, buffer, len(buffer), ctypes.byref(bytes_read), None
                ):
                    raise OSError(f"ReadFile failed (Windows error {ctypes.get_last_error()})")
                if bytes_read.value == 0:
                    break
                chunks.append(buffer.raw[: bytes_read.value])
            return b"".join(chunks)
        finally:
            kernel32.CloseHandle(handle)

    def load_excel_template_dialog(self, wait=False):
        file_path = filedialog.askopenfilename(
            title="Select Excel File", filetypes=[("Excel Files", "*.xlsx *.xls")], parent=self.root
        )
        if not file_path:
            return

        try:
            import io

            excel_bytes = self._read_file_bytes_shared(file_path)
            with pd.ExcelFile(io.BytesIO(excel_bytes)) as workbook:
                sheet_names = workbook.sheet_names
            if not sheet_names:
                raise ValueError("Workbook has no worksheets")
            sql_template = self._capture_sql_template(self.sql_context.get("1.0", tk.END))
        except Exception as error:
            messagebox.showerror("Excel Import Error", str(error), parent=self.root)
            return

        import re

        placeholder_pattern = r"\{\{?\s*[A-Za-z_][A-Za-z0-9_]*\s*\}\}?|:[A-Za-z_][A-Za-z0-9_]*"
        placeholders = list(dict.fromkeys(re.findall(placeholder_pattern, sql_template)))
        auto_where_choice = "Auto WHERE (Excel column)"
        if placeholders:
            parameter_choices = placeholders + [auto_where_choice]
        elif re.search(r"\bIN\s*\(", sql_template, flags=re.IGNORECASE):
            parameter_choices = ["First IN (...) list", auto_where_choice]
        else:
            parameter_choices = [auto_where_choice]
        parameter_var = tk.StringVar(value=parameter_choices[0])
        sheet_var = tk.StringVar(value=sheet_names[0])
        sheet_data = {"dataframe": None}
        column_lookup = {}
        column_var = tk.StringVar()
        self._excel_selected_values = []

        dialog = tk.Toplevel(self.root)
        dialog.title("Load Excel SQL Parameters")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.geometry("1150x700")
        dialog.minsize(900, 580)
        dialog.configure(bg=UI["card"])
        CARD = UI["card"]

        # Header: title + Excel file
        _head = tk.Frame(dialog, bg=CARD)
        _head.pack(side="top", fill="x", padx=20, pady=(16, 4))
        tk.Label(_head, text="Load Excel → SQL Parameter", bg=CARD, fg=UI["text"],
                 font=("Segoe UI Semibold", 14)).pack(anchor="w")
        tk.Label(_head, text=f"📗  {os.path.basename(file_path)}", bg=CARD, fg=UI["muted"],
                 font=UI_FONT_SM).pack(anchor="w")

        # Footer: Cancel / Confirm (buttons added at the end)
        _footer = tk.Frame(dialog, bg=UI["surface"])
        _footer.pack(side="bottom", fill="x")
        tk.Frame(_footer, bg=UI["border"], height=1).pack(side="top", fill="x")
        _footer_bar = tk.Frame(_footer, bg=UI["surface"])
        _footer_bar.pack(fill="x", padx=20, pady=12)

        content = tk.Frame(dialog, bg=CARD)
        content.pack(fill="both", expand=True, padx=20, pady=(8, 14))
        content.columnconfigure(0, weight=1, uniform="panel")
        content.columnconfigure(1, weight=1, uniform="panel")
        content.columnconfigure(2, weight=1, uniform="panel")
        content.rowconfigure(2, weight=1)

        # ---- Top: Worksheet / SQL parameter ----
        top_frame = tk.Frame(content, bg=CARD)
        top_frame.grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 14))

        tk.Label(top_frame, text="Sheet", bg=CARD, fg=UI["muted"], font=UI_FONT_LABEL).pack(
            side="left", padx=(0, 6))
        sheet_combo = ttk.Combobox(
            top_frame, textvariable=sheet_var, values=sheet_names, state="readonly", width=30
        )
        sheet_combo.pack(side="left", padx=(0, 20))

        tk.Label(top_frame, text="ใส่แทน parameter ใน SQL", bg=CARD, fg=UI["muted"],
                 font=UI_FONT_LABEL).pack(side="left", padx=(0, 6))
        parameter_combo = ttk.Combobox(
            top_frame,
            textvariable=parameter_var,
            values=parameter_choices,
            state="readonly",
            width=30,
        )
        parameter_combo.pack(side="left")

        # ---- Panel titles ----
        _step_font = ("Segoe UI Semibold", 10)
        tk.Label(content, text="①  เลือกคอลัมน์", bg=CARD, fg=UI["primary"], font=_step_font).grid(
            row=1, column=0, sticky="w", padx=(0, 10), pady=(0, 6)
        )
        tk.Label(content, text="②  เลือกค่า", bg=CARD, fg=UI["primary"], font=_step_font).grid(
            row=1, column=1, sticky="w", padx=10, pady=(0, 6)
        )
        selected_title = tk.Label(content, text="③ Selected values", bg=CARD, fg=UI["primary"],
                                  font=_step_font)
        selected_title.grid(row=1, column=2, sticky="w", padx=(10, 0), pady=(0, 6))

        # ---- Per-panel search box (filters only the panel it sits in) ----
        search_jobs = {}

        def debounce(key, fn, delay=150):
            job = search_jobs.pop(key, None)
            if job:
                dialog.after_cancel(job)

            def _run():
                search_jobs.pop(key, None)
                fn()

            search_jobs[key] = dialog.after(delay, _run)

        def cancel_debounce(key):
            job = search_jobs.pop(key, None)
            if job:
                dialog.after_cancel(job)

        def search_ctrl_key(e):
            """Ctrl+C/X/V/A by keycode so it works with Thai/EN keyboard layouts."""
            w = e.widget
            try:
                if e.keycode == 86:  # V
                    try:
                        w.delete(tk.SEL_FIRST, tk.SEL_LAST)
                    except tk.TclError:
                        pass
                    w.insert(tk.INSERT, dialog.clipboard_get().strip())
                elif e.keycode in (67, 88):  # C / X
                    dialog.clipboard_clear()
                    dialog.clipboard_append(w.selection_get())
                    if e.keycode == 88:
                        w.delete(tk.SEL_FIRST, tk.SEL_LAST)
                elif e.keycode == 65:  # A
                    w.select_range(0, tk.END)
                    w.icursor(tk.END)
                else:
                    return None
            except tk.TclError:
                pass
            return "break"

        def make_search(panel, key, on_change):
            var = tk.StringVar()
            row = tk.Frame(panel, bg="#ffffff")
            row.pack(side="top", fill="x", padx=6, pady=(6, 0))
            tk.Label(row, text="🔍", bg="#ffffff", fg="#64748B", font=("Segoe UI", 9)).pack(
                side="left", padx=(0, 4)
            )
            entry = ttk.Entry(row, textvariable=var)
            entry.pack(side="left", fill="x", expand=True)
            tk.Button(
                row,
                text="✕",
                relief="flat",
                bd=0,
                bg="#ffffff",
                fg="#64748B",
                activebackground="#ffffff",
                cursor="hand2",
                command=lambda: (var.set(""), entry.focus_set()),
            ).pack(side="left", padx=(4, 0))
            entry.bind("<Escape>", lambda _e: var.set(""))
            entry.bind("<Control-KeyPress>", search_ctrl_key)
            var.trace_add("write", lambda *_a: debounce(key, on_change))
            return var

        # ---- Panel 1: Column list ----
        _column_panel_outer, column_panel = ui_round_frame(content, fill="#FFFFFF", border=UI["border"], radius=10, pad=3)
        _column_panel_outer.grid(row=2, column=0, sticky="nsew", padx=(0, 10))
        column_search = make_search(column_panel, "columns", lambda: render_column_list())
        column_scroll = ttk.Scrollbar(column_panel, orient="vertical")
        column_list = tk.Listbox(
            column_panel,
            font=UI_FONT,
            selectbackground="#DBEAFE",
            selectforeground=UI["text"],
            selectmode=tk.SINGLE,
            exportselection=False,
            bd=0,
            highlightthickness=0,
            yscrollcommand=column_scroll.set,
        )
        column_scroll.config(command=column_list.yview)
        column_scroll.pack(side="right", fill="y")
        column_list.pack(side="left", fill="both", expand=True, padx=6, pady=6)

        # ---- Panel 2: Values of the column (checkboxes) ----
        _values_panel_outer, values_panel = ui_round_frame(content, fill="#FFFFFF", border=UI["border"], radius=10, pad=3)
        _values_panel_outer.grid(row=2, column=1, sticky="nsew", padx=10)
        values_search = make_search(values_panel, "values", lambda: render_values())

        values_buttons = ttk.Frame(values_panel)
        values_buttons.pack(side="bottom", pady=8)

        values_area = tk.Frame(values_panel, bg="#ffffff")
        values_area.pack(side="top", fill="both", expand=True, padx=6, pady=6)
        values_canvas = tk.Canvas(values_area, bg="#ffffff", highlightthickness=0)
        values_scroll = ttk.Scrollbar(values_area, orient="vertical", command=values_canvas.yview)
        values_inner = tk.Frame(values_canvas, bg="#ffffff")
        values_inner.bind(
            "<Configure>",
            lambda _e: values_canvas.configure(scrollregion=values_canvas.bbox("all")),
        )
        values_canvas.create_window((0, 0), window=values_inner, anchor="nw")
        values_canvas.configure(yscrollcommand=values_scroll.set)
        values_scroll.pack(side="right", fill="y")
        values_canvas.pack(side="left", fill="both", expand=True)

        def _on_values_wheel(event):
            values_canvas.yview_scroll(int(-event.delta / 120), "units")

        values_canvas.bind(
            "<Enter>", lambda _e: values_canvas.bind_all("<MouseWheel>", _on_values_wheel)
        )
        values_canvas.bind("<Leave>", lambda _e: values_canvas.unbind_all("<MouseWheel>"))

        # ---- Panel 3: Selected values ----
        _selected_panel_outer, selected_panel = ui_round_frame(content, fill="#FFFFFF", border=UI["border"], radius=10, pad=3)
        _selected_panel_outer.grid(row=2, column=2, sticky="nsew", padx=(10, 0))
        selected_search = make_search(selected_panel, "selected", lambda: refresh_selected_list())

        selected_buttons = ttk.Frame(selected_panel)
        selected_buttons.pack(side="bottom", pady=8)

        selected_area = tk.Frame(selected_panel, bg="#ffffff")
        selected_area.pack(side="top", fill="both", expand=True, padx=6, pady=6)
        selected_scroll = ttk.Scrollbar(selected_area, orient="vertical")
        selected_list = tk.Listbox(
            selected_area,
            font=UI_FONT,
            selectbackground="#DBEAFE",
            selectforeground=UI["text"],
            bd=0,
            highlightthickness=0,
            activestyle="none",
            yscrollcommand=selected_scroll.set,
        )
        selected_scroll.config(command=selected_list.yview)
        selected_scroll.pack(side="right", fill="y")
        selected_list.pack(side="left", fill="both", expand=True)

        # ---- Bottom: SQL ----
        tk.Label(content, text="SQL ที่จะได้", bg=CARD, fg=UI["muted"], font=UI_FONT_LABEL).grid(
            row=3, column=0, columnspan=3, sticky="w", pady=(14, 4))
        sql_preview = scrolledtext.ScrolledText(
            content, height=5, font=("Consolas", 10), wrap=tk.WORD, bg="#EFF6FF", fg=UI["text"],
            bd=0, relief="flat", highlightthickness=1, highlightbackground="#BFDBFE", padx=10, pady=8,
        )
        sql_preview.grid(row=4, column=0, columnspan=3, sticky="nsew")

        # Ticked values are kept per column, so several columns can be chosen
        column_values = {}  # column -> unique value strings, in Excel order
        column_selected = {}  # column -> set of ticked value strings
        value_vars = {}  # value string -> BooleanVar of the shown column

        def is_auto_where():
            return parameter_var.get() == auto_where_choice

        def selected_of(column_name):
            chosen = column_selected.get(column_name, set())
            return [value for value in column_values.get(column_name, []) if value in chosen]

        def columns_with_selection():
            return [column for column in column_lookup if selected_of(column)]

        def build_pending_values():
            """Parameter entries that Confirm would add, from the current ticks."""
            pending = {}
            if is_auto_where():
                for column in columns_with_selection():
                    sql_values = self._format_excel_sql_values(selected_of(column))
                    if sql_values:
                        sql_column = self._sql_column_identifier(column)
                        pending[f"WHERE {sql_column}"] = (self.AUTO_WHERE_PARAMETER, sql_values)
                return pending

            sql_values = self._format_excel_sql_values(selected_of(column_var.get()))
            if not sql_values:
                return pending
            parameter = parameter_var.get()
            if parameter == "First IN (...) list":
                pending["__FIRST_IN_LIST__"] = (parameter, sql_values)
            else:
                pending[parameter.lstrip(":").strip("{}").strip().upper()] = (parameter, sql_values)
            return pending

        def refresh_sql_preview():
            preview_values = dict(self._excel_parameter_values)
            preview_values.update(build_pending_values())
            try:
                preview_sql = self._render_sql_template(preview_values)
            except ValueError as error:
                preview_sql = f"{sql_template}\n\n-- {error}"
            sql_preview.config(state="normal")
            sql_preview.delete("1.0", tk.END)
            sql_preview.insert("1.0", preview_sql)
            sql_preview.config(state="disabled")

        def refresh_selected_list():
            cancel_debounce("selected")
            query = selected_search.get().strip().lower()
            selected_list.delete(0, tk.END)
            # Show only the values ticked in Panel 2 for the column picked in Panel 1
            column_name = column_var.get()
            values = selected_of(column_name)
            for value in values:
                if query in value.lower():
                    selected_list.insert(tk.END, value)
            total_values = len(column_values.get(column_name, []))
            title = f"③ Selected values ({len(values)} / {total_values})"
            if is_auto_where():
                # Other columns' ticks still go into the WHERE; show the overall count
                used = columns_with_selection()
                if any(column != column_name for column in used):
                    all_count = sum(len(selected_of(column)) for column in used)
                    title += f"  ·  {len(used)} columns, {all_count} total"
            selected_title.config(text=title)
            if query and selected_list.size() == 0:
                selected_list.insert(tk.END, "No matching values")
                selected_list.itemconfig(tk.END, fg="#94A3B8")
            refresh_sql_preview()

        def on_value_toggled(value_str, var):
            chosen = column_selected.setdefault(column_var.get(), set())
            if var.get():
                chosen.add(value_str)
            else:
                chosen.discard(value_str)
            refresh_selected_list()

        def load_column_values(column_name):
            dataframe = sheet_data["dataframe"]
            if dataframe is None or column_name not in column_lookup:
                return
            if column_name not in column_values:
                # dict keeps Excel order and dedupes in O(n)
                column_values[column_name] = list(
                    dict.fromkeys(
                        str(value)
                        for value in dataframe[column_lookup[column_name]].dropna().tolist()
                    )
                )

        def render_values():
            """Show the current column's values that match the Pick-values search."""
            cancel_debounce("values")
            for widget in values_inner.winfo_children():
                widget.destroy()
            value_vars.clear()

            column_name = column_var.get()
            if sheet_data["dataframe"] is not None and column_name in column_lookup:
                load_column_values(column_name)
                query = values_search.get().strip().lower()
                chosen = column_selected.get(column_name, set())
                for value_str in column_values[column_name]:
                    if query and query not in value_str.lower():
                        continue
                    var = tk.BooleanVar(value=value_str in chosen)
                    value_vars[value_str] = var
                    tk.Checkbutton(
                        values_inner,
                        text=value_str,
                        variable=var,
                        anchor="w",
                        bg="#ffffff",
                        command=lambda v=value_str, b=var: on_value_toggled(v, b),
                    ).pack(fill="x", anchor="w")
                if query and not value_vars:
                    tk.Label(
                        values_inner, text="No matching values", bg="#ffffff", fg="#94A3B8"
                    ).pack(anchor="w", padx=4, pady=4)

            values_canvas.yview_moveto(0)
            refresh_selected_list()

        def select_column(column_name):
            changed = column_name != column_var.get()
            column_var.set(column_name)
            load_column_values(column_name)
            if changed and values_search.get():
                values_search.set("")  # new column → start with an empty value search
            render_values()

        def show_column_values(_event=None):
            selection = column_list.curselection()
            if selection:
                select_column(column_list.get(selection[0]))

        def render_column_list():
            """Show column names that match the Select-column search; keep the current pick."""
            cancel_debounce("columns")
            query = column_search.get().strip().lower()
            column_list.delete(0, tk.END)
            for column_name in column_lookup:
                if query and query not in column_name.lower():
                    continue
                column_list.insert(tk.END, column_name)
                if column_name == column_var.get():
                    column_list.selection_set(tk.END)
                    column_list.see(tk.END)

        def update_columns(_event=None):
            column_values.clear()
            column_selected.clear()
            try:
                dataframe = pd.read_excel(io.BytesIO(excel_bytes), sheet_name=sheet_var.get())
                sheet_data["dataframe"] = dataframe
                column_lookup.clear()
                column_lookup.update({str(column): column for column in dataframe.columns})
            except Exception as error:
                sheet_data["dataframe"] = None
                column_lookup.clear()
                messagebox.showerror("Excel Import Error", str(error), parent=dialog)

            column_var.set("")
            select_column(next(iter(column_lookup), ""))
            render_column_list()

        def set_all_values(checked):
            chosen = column_selected.setdefault(column_var.get(), set())
            for value_str, var in value_vars.items():
                var.set(checked)
                if checked:
                    chosen.add(value_str)
                else:
                    chosen.discard(value_str)
            refresh_selected_list()

        def apply_parameters():
            dataframe = sheet_data["dataframe"]
            column_name = column_var.get()
            if dataframe is None or column_name not in column_lookup:
                messagebox.showwarning("Excel Import", "Select a value column", parent=dialog)
                return

            if is_auto_where():
                used_columns = columns_with_selection()
                values = [value for column in used_columns for value in selected_of(column)]
            else:
                used_columns = [column_name]
                values = selected_of(column_name)
            self._excel_selected_values = values

            if not values:
                messagebox.showwarning("Excel Import", "Please select values first", parent=dialog)
                return

            pending = build_pending_values()
            if not pending:
                messagebox.showwarning(
                    "Excel Import", "Selected column has no values", parent=dialog
                )
                return

            parameter = parameter_var.get()
            previous_values = dict(self._excel_parameter_values)
            self._excel_parameter_values.update(pending)

            try:
                rendered_sql = self._render_sql_template()
            except ValueError as error:
                self._excel_parameter_values.clear()
                self._excel_parameter_values.update(previous_values)
                messagebox.showwarning("SQL Parameter Not Found", str(error), parent=dialog)
                return

            self.sql_context.delete("1.0", tk.END)
            self.sql_context.insert("1.0", rendered_sql)
            self._excel_parameterized_sql = rendered_sql
            self.loaded_excel_data = dataframe
            if self.debug_mode.get():
                print(
                    f"[Excel Parameter Debug] file={os.path.basename(file_path)!r}, "
                    f"sheet={sheet_var.get()!r}, columns={used_columns!r}, "
                    f"parameter={parameter!r}, values={len(values)}, "
                    f"replaced_parameters={list(self._excel_parameter_values)}"
                )
            if is_auto_where():
                target = "WHERE " + " AND ".join(used_columns)
            else:
                target = parameter
            messagebox.showinfo(
                "Excel Parameters Loaded",
                f"Loaded {len(values)} values from {', '.join(used_columns)} into {target}.",
                parent=dialog,
            )
            dialog.destroy()

        _o, _ = ui_button(values_buttons, "ล้างที่เลือก", lambda: set_all_values(False), size="sm")
        _o.pack(side="left", padx=4)
        _o, _ = ui_button(values_buttons, "☑  Select All", lambda: set_all_values(True), size="sm")
        _o.pack(side="left", padx=4)
        tk.Label(_footer_bar, text="ติ๊กค่าที่ต้องการ แล้วตรวจ SQL ด้านบนก่อนยืนยัน", bg=UI["surface"],
                 fg=UI["muted"], font=UI_FONT_SM).pack(side="left")
        _o, _ = ui_button(_footer_bar, "✓  Confirm · ใส่ค่าใน SQL", apply_parameters, kind="primary", size="md")
        _o.pack(side="right")
        _o, _ = ui_button(_footer_bar, "ยกเลิก", dialog.destroy, size="md")
        _o.pack(side="right", padx=(0, 8))

        sheet_combo.bind("<<ComboboxSelected>>", update_columns)
        column_list.bind("<<ListboxSelect>>", show_column_values)
        parameter_combo.bind("<<ComboboxSelected>>", lambda _e: refresh_selected_list())

        def _on_dialog_destroy(e):
            if e.widget is not dialog:
                return
            values_canvas.unbind_all("<MouseWheel>")
            for key in list(search_jobs):
                cancel_debounce(key)

        dialog.bind("<Destroy>", _on_dialog_destroy)

        update_columns()

        if wait:
            dialog.wait_window()

    def show_excel_value_selector(self, column_name, values):

        dialog = tk.Toplevel(self.root)
        dialog.title(f"Select Data - {column_name}")
        dialog.geometry("800x700")
        dialog.transient(self.root)
        dialog.grab_set()

        selected_values = []

        tk.Label(
            dialog, text=f"Select Values From Column [{column_name}]", font=("Arial", 12, "bold")
        ).pack(pady=10)

        info_label = tk.Label(
            dialog, text=f"Selected : 0 / {len(values)}", font=("Arial", 10, "bold"), fg="blue"
        )
        info_label.pack()

        search_var = tk.StringVar()

        search_frame = tk.Frame(dialog)
        search_frame.pack(fill="x", padx=10, pady=5)

        tk.Label(search_frame, text="Search").pack(side="left")

        search_entry = tk.Entry(search_frame, textvariable=search_var, width=50)
        search_entry.pack(side="left", padx=5)

        list_frame = tk.Frame(dialog)
        list_frame.pack(fill="both", expand=True, padx=10, pady=10)

        canvas = tk.Canvas(list_frame)

        scrollbar = tk.Scrollbar(list_frame, orient="vertical", command=canvas.yview)

        scrollable_frame = tk.Frame(canvas)

        scrollable_frame.bind(
            "<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")

        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)

        scrollbar.pack(side="right", fill="y")

        checkbox_vars = {}

        def update_counter():

            count = sum(bool(var.get()) for var in checkbox_vars.values())

            info_label.config(text=f"Selected : {count} / {len(values)}")

        def refresh_list():

            for widget in scrollable_frame.winfo_children():
                widget.destroy()

            keyword = search_var.get().lower().strip()

            for value in values:

                value_str = str(value)

                if keyword and keyword not in value_str.lower():
                    continue

                if value_str not in checkbox_vars:
                    checkbox_vars[value_str] = tk.BooleanVar()

                tk.Checkbutton(
                    scrollable_frame,
                    text=value_str,
                    variable=checkbox_vars[value_str],
                    anchor="w",
                    command=update_counter,
                ).pack(fill="x", anchor="w")

        def select_all():

            for var in checkbox_vars.values():
                var.set(True)

            update_counter()

        def clear_all():

            for var in checkbox_vars.values():
                var.set(False)

            update_counter()

        def view_selected():

            selected = [value for value, var in checkbox_vars.items() if var.get()]

            popup = tk.Toplevel(dialog)
            popup.title("Selected Values")
            popup.geometry("600x500")

            tk.Label(
                popup, text=f"Selected Values ({len(selected)})", font=("Arial", 12, "bold")
            ).pack(pady=10)

            txt = scrolledtext.ScrolledText(popup, font=("Consolas", 10))

            txt.pack(fill="both", expand=True, padx=10, pady=10)

            txt.insert(tk.END, "\n".join(map(str, selected)))

            txt.config(state="disabled")

        def export_selected():

            selected = [value for value, var in checkbox_vars.items() if var.get()]

            if not selected:
                messagebox.showwarning("No Selection", "Please select data first", parent=dialog)
                return

            save_path = filedialog.asksaveasfilename(
                defaultextension=".xlsx", filetypes=[("Excel Files", "*.xlsx")]
            )

            if not save_path:
                return

            try:

                pd.DataFrame({column_name: selected}).to_excel(save_path, index=False)

                messagebox.showinfo(
                    "Export Success", f"Saved {len(selected)} records", parent=dialog
                )

            except Exception as error:

                messagebox.showerror("Export Error", str(error), parent=dialog)

        def confirm_selection():

            selected_values.clear()

            selected_values.extend([value for value, var in checkbox_vars.items() if var.get()])

            if not selected_values:

                messagebox.showwarning(
                    "No Selection", "Please select at least 1 value", parent=dialog
                )

                return

            dialog.destroy()

        search_var.trace_add("write", lambda *args: refresh_list())

        refresh_list()

        button_frame = tk.Frame(dialog)
        button_frame.pack(pady=10)

        tk.Button(
            button_frame, text="View Selected", bg="#3498db", fg="white", command=view_selected
        ).pack(side="left", padx=5)

        tk.Button(
            button_frame, text="Select All", bg="#27ae60", fg="white", command=select_all
        ).pack(side="left", padx=5)

        tk.Button(button_frame, text="Clear All", bg="#e74c3c", fg="white", command=clear_all).pack(
            side="left", padx=5
        )

        tk.Button(
            button_frame, text="Export Selected", bg="#8e44ad", fg="white", command=export_selected
        ).pack(side="left", padx=5)

        tk.Button(
            button_frame, text="Confirm", bg="#2ecc71", fg="white", command=confirm_selection
        ).pack(side="left", padx=5)

        dialog.wait_window()

        return selected_values

    def on_closing(self):
        """Handle window close event - save current profile as last used"""
        current_profile = self.profile_combo.get()
        if current_profile and current_profile in self.saved_profiles:
            self.save_last_used_profile(current_profile)
        self.root.destroy()


def main():
    root = tk.Tk()
    app = DatabaseConnectorGUI(root)
    root.state("zoomed")
    root.mainloop()


if __name__ == "__main__":
    main()
