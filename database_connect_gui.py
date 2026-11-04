import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog
from sqlalchemy import create_engine, inspect, text
import pandas as pd
import re
import json
import os
import threading
import traceback
import sys
import base64
import ctypes


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
        _fields_ = [
            ("cbData", wintypes.DWORD),
            ("pbData", ctypes.POINTER(ctypes.c_char))
        ]

    buffer = ctypes.create_string_buffer(data, len(data))
    blob_in = DATA_BLOB(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char)))
    blob_out = DATA_BLOB()
    crypt32 = ctypes.windll.crypt32
    func = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
    CRYPTPROTECT_UI_FORBIDDEN = 0x01
    ok = func(
        ctypes.byref(blob_in), None, None, None, None,
        CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(blob_out)
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
        raw = base64.b64decode(str(stored)[len(_DPAPI_PREFIX):])
        return _dpapi_transform(raw, protect=False).decode("utf-8")
    except Exception as e:
        # e.g. file copied from another Windows user/computer
        print(f"Cannot decrypt saved password (please re-enter it): {e}")
        return ""


class DatabaseConnectorGUI:

    def __init__(self, root):
        self.root = root
        self.root.title("Database Connector")
        self.root.geometry("1200x900")
        self.root.configure(bg='#f0f0f0')
        
        # Enhanced styling
        self.style = ttk.Style()
        self.style.theme_use('clam')
        self.style.configure('TFrame', background='#f0f0f0')
        self.style.configure('TLabelframe', background='#ffffff', relief='flat')
        self.style.configure('TLabelframe.Label', background='#ffffff', foreground='#2c3e50',
                           font=('Arial', 11, 'bold'))
        self.style.configure('TLabel', background='#ffffff', foreground='#2c3e50', font=('Arial', 10))
        self.style.configure('TButton', font=('Arial', 10, 'bold'), relief='flat',
                           background='#3498db', foreground='white')
        self.style.map('TButton',
                      background=[('active', '#2980b9'), ('disabled', "#3f5462")])
        self.style.configure('TCombobox', fieldbackground='white', selectbackground='#3498db')
        self.style.configure('TEntry', fieldbackground='white', selectbackground='#3498db')
        
        self.engine = None
        self.config_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "db_profiles.json")
        self.jobs_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "saved_jobs.json")
        self.saved_profiles = self.load_profiles()
        self.saved_jobs = self.load_jobs()
        self.job_results = {}
        
        # NEW: Debug mode and table data
        self.debug_mode = tk.BooleanVar(value=True)
        self.last_error_details = None
        self.table_data_file = os.path.join(os.path.dirname(__file__), 'mail_table_data.json')
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

        self.load_table_mappings()
        
        # Set close event handler
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        # Create canvas with scrollbar for main window
        self.canvas = tk.Canvas(root, bg='#f0f0f0', highlightthickness=0)
        self.canvas.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Add vertical scrollbar
        main_scrollbar = ttk.Scrollbar(root, orient=tk.VERTICAL, command=self.canvas.yview)
        main_scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        self.canvas.configure(yscrollcommand=main_scrollbar.set)
        
        # Configure grid weights
        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)
        
        # Create main container inside canvas
        main_frame = ttk.Frame(self.canvas, padding="10")
        self.canvas_window = self.canvas.create_window((0, 0), window=main_frame, anchor=tk.NW)
        
        # Configure main_frame
        main_frame.columnconfigure(1, weight=1)
        
        # Update scroll region when frame size changes
        def on_frame_configure(event):
            self.canvas.configure(
                scrollregion=self.canvas.bbox("all")
            )
        
        def on_canvas_configure(event):
            self.canvas.itemconfig(self.canvas_window, width=event.width)
        
        main_frame.bind('<Configure>', on_frame_configure)
        self.canvas.bind('<Configure>', on_canvas_configure)
        
        # Bind mousewheel to scroll main page
        def on_mousewheel(event):
            self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        
        self._main_mousewheel = on_mousewheel
        self.canvas.bind_all("<MouseWheel>", on_mousewheel)
        
        # Connection Settings Section
        settings_frame = ttk.LabelFrame(main_frame, text="🔌 Connection Settings", padding="15")
        settings_frame.grid(row=0, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))
        settings_frame.columnconfigure(1, weight=1)
                
        # Profile Selection Section
        profile_frame = ttk.Frame(settings_frame)
        profile_frame.grid(row=0, column=0, columnspan=2, pady=(0, 10), sticky=(tk.W, tk.E))
        
        ttk.Label(profile_frame, text="📁 Profile:", font=('Arial', 10, 'bold')).pack(side=tk.LEFT, padx=(0, 5))
        self.profile_combo = ttk.Combobox(profile_frame, width=25, state="readonly", font=('Arial', 10))
        self.profile_combo.pack(side=tk.LEFT, padx=5)
        self.update_profile_list()
        self.profile_combo.bind('<<ComboboxSelected>>', self.on_profile_selected)
    
        self.delete_btn = tk.Button(profile_frame, text="🗑️ Delete", command=self.delete_profile,
                                   bg='#e74c3c', fg='white', font=('Arial', 9, 'bold'),
                                   relief='flat', padx=15, pady=5, cursor='hand2')
        self.delete_btn.pack(side=tk.LEFT, padx=5)

        tk.Button(profile_frame, text="💾 Save", command=self.save_profile_dialog,
                 bg='#27ae60', fg='white', font=('Arial', 9, 'bold'),
                 relief='flat', padx=15, pady=5, cursor='hand2').pack(side=tk.LEFT, padx=5)

        tk.Button(profile_frame, text="📁 Location", command=self.show_config_file_location,
                bg='#95a5a6', fg='white', font=('Arial', 9, 'bold'),
                relief='flat', padx=15, pady=5, cursor='hand2').pack(side=tk.LEFT, padx=5)
        
        # NEW: Import/Export buttons
        tk.Button(profile_frame, text="📥 Import", command=self.import_profiles_dialog,
                 bg='#3498db', fg='white', font=('Arial', 9, 'bold'),
                 relief='flat', padx=15, pady=5, cursor='hand2').pack(side=tk.LEFT, padx=5)
        
        tk.Button(profile_frame, text="📤 Export", command=self.export_profiles_dialog,
                 bg='#9b59b6', fg='white', font=('Arial', 9, 'bold'),
                 relief='flat', padx=15, pady=5, cursor='hand2').pack(side=tk.LEFT, padx=5)
        
        # Database Type
        ttk.Label(settings_frame, text="📦 Database Type:", font=('Arial', 10, 'bold')).grid(row=1, column=0, sticky=tk.W, pady=5)
        self.db_type = ttk.Combobox(settings_frame, width=38, state="readonly", font=('Arial', 10))
        self.db_type.grid(row=1, column=1, sticky=(tk.W, tk.E), padx=5, pady=5)
        self.db_type['values'] = ('PostgreSQL', 'MySQL', 'Microsoft SQL Server', 'Oracle')
        self.db_type.current(0)
        self.db_type.bind('<<ComboboxSelected>>', self.on_db_type_change)
        
        # Database User
        ttk.Label(settings_frame, text="👤 User:", font=('Arial', 10, 'bold')).grid(row=2, column=0, sticky=tk.W, pady=5)
        self.db_user = ttk.Entry(settings_frame, width=40, font=('Arial', 10))
        self.db_user.grid(row=2, column=1, sticky=(tk.W, tk.E), padx=5, pady=5)
        self.db_user.insert(0, "test")
        
        # Database Password
        ttk.Label(settings_frame, text="🔒 Password:", font=('Arial', 10, 'bold')).grid(row=3, column=0, sticky=tk.W, pady=5)
        password_frame = ttk.Frame(settings_frame)
        password_frame.grid(row=3, column=1, sticky=(tk.W, tk.E), padx=5, pady=5)
        password_frame.columnconfigure(0, weight=1)
        
        self.db_password = ttk.Entry(password_frame, width=35, show="*", font=('Arial', 10))
        self.db_password.grid(row=0, column=0, sticky=(tk.W, tk.E))
        self.db_password.insert(0, "test")
        
        self.password_visible = False
        self.toggle_password_btn = tk.Button(password_frame, text="👁️", width=3,
                                            command=self.toggle_password_visibility,
                                            bg='#ecf0f1', fg='#2c3e50', font=('Arial', 12, 'bold'),
                                            relief='raised', cursor='hand2', bd=2)
        self.toggle_password_btn.grid(row=0, column=1, padx=(5, 0))
        
        # Database Host
        ttk.Label(settings_frame, text="🌐 Host:", font=('Arial', 10, 'bold')).grid(row=4, column=0, sticky=tk.W, pady=5)
        self.db_host = ttk.Entry(settings_frame, width=40, font=('Arial', 10))
        self.db_host.grid(row=4, column=1, sticky=(tk.W, tk.E), padx=5, pady=5)
        self.db_host.insert(0, "test.com")
        
        # Database Port
        ttk.Label(settings_frame, text="🚪 Port:", font=('Arial', 10, 'bold')).grid(row=5, column=0, sticky=tk.W, pady=5)
        self.db_port = ttk.Entry(settings_frame, width=40, font=('Arial', 10))
        self.db_port.grid(row=5, column=1, sticky=(tk.W, tk.E), padx=5, pady=5)
        self.db_port.insert(0, "5432")
        
        # Database Name
        ttk.Label(settings_frame, text="📊 Database:", font=('Arial', 10, 'bold')).grid(row=6, column=0, sticky=tk.W, pady=5)
        self.db_name = ttk.Entry(settings_frame, width=40, font=('Arial', 10))
        self.db_name.grid(row=6, column=1, sticky=(tk.W, tk.E), padx=5, pady=5)
        self.db_name.insert(0, "test")

        def _entry_ctrl_key(e):
            """Handle Ctrl+C/X/V/A for Entry by Windows keycode — works with any keyboard layout (Thai/EN)."""
            kc = e.keycode
            w = e.widget
            if kc == 67:  # C — Copy
                try:
                    sel = w.selection_get()
                    self.root.clipboard_clear()
                    self.root.clipboard_append(sel)
                except Exception: pass
                return 'break'
            elif kc == 88:  # X — Cut
                try:
                    sel = w.selection_get()
                    self.root.clipboard_clear()
                    self.root.clipboard_append(sel)
                    w.delete(tk.SEL_FIRST, tk.SEL_LAST)
                except Exception: pass
                return 'break'
            elif kc == 86:  # V — Paste
                try:
                    txt = self.root.clipboard_get()
                    try: w.delete(tk.SEL_FIRST, tk.SEL_LAST)
                    except Exception: pass
                    w.insert(tk.INSERT, txt)
                except Exception: pass
                return 'break'
            elif kc == 65:  # A — Select All
                try:
                    w.select_range(0, tk.END)
                    w.icursor(tk.END)
                except Exception: pass
                return 'break'

        for _ew in (self.db_user, self.db_password, self.db_host, self.db_port, self.db_name):
            _ew.bind('<Control-KeyPress>', _entry_ctrl_key)

        # Connect Button
        connect_frame = ttk.Frame(settings_frame)
        connect_frame.grid(row=7, column=0, columnspan=2, pady=10)
        
        self.connect_btn = tk.Button(connect_frame, text="🔌 Connect", command=self.connect_database,
                                    bg='#3498db', fg='white', font=('Arial', 11, 'bold'),
                                    relief='flat', padx=30, pady=8, cursor='hand2')
        self.connect_btn.pack()
        
        # Connection Status
        self.status_label = tk.Label(settings_frame, text="❌ Not Connected", foreground="#e74c3c",
                                    font=('Arial', 10, 'bold'), bg='#ffffff')
        self.status_label.grid(row=8, column=0, columnspan=2)
        
        # SQL Query Section
        query_frame = ttk.LabelFrame(main_frame, text="📝 SQL Query", padding="15")
        query_frame.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 10))
        query_frame.columnconfigure(0, weight=1)
        query_frame.rowconfigure(0, weight=1)
        main_frame.rowconfigure(1, weight=1)
        
        # SQL Context Text Area
        self.sql_context = scrolledtext.ScrolledText(query_frame, height=8, width=70, font=('Arial', 10), undo=True, maxundo=-1)
        self.sql_context.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), pady=5)
        self.sql_context.insert(
                1.0,
                "SELECT * FROM Table WHERE Column1 IN ({ACCOUNT_LIST})"
                )
        # Defer edit_reset so it runs after widget is fully ready — clears undo stack to fresh start
        self.sql_context.after(200, self.sql_context.edit_reset)

        def _text_ctrl_key(e):
            """Handle Ctrl+Z/Y/C/X/V for Text/ScrolledText by Windows keycode — works with any keyboard layout (Thai/EN)."""
            kc = e.keycode
            w = e.widget
            if kc == 90:  # Z — Undo
                try: w.edit_undo()
                except Exception: pass
                return 'break'
            elif kc == 89:  # Y — Redo
                try: w.edit_redo()
                except Exception: pass
                return 'break'
            elif kc == 67:  # C — Copy
                try:
                    sel = w.get(tk.SEL_FIRST, tk.SEL_LAST)
                    self.root.clipboard_clear()
                    self.root.clipboard_append(sel)
                except Exception: pass
                return 'break'
            elif kc == 88:  # X — Cut
                try:
                    sel = w.get(tk.SEL_FIRST, tk.SEL_LAST)
                    self.root.clipboard_clear()
                    self.root.clipboard_append(sel)
                    w.delete(tk.SEL_FIRST, tk.SEL_LAST)
                except Exception: pass
                return 'break'
            elif kc == 86:  # V — Paste
                try:
                    txt = self.root.clipboard_get()
                    try: w.delete(tk.SEL_FIRST, tk.SEL_LAST)
                    except Exception: pass
                    w.insert(tk.INSERT, txt)
                except Exception: pass
                return 'break'
            elif kc == 65:  # A — Select All
                try: w.tag_add(tk.SEL, '1.0', tk.END)
                except Exception: pass
                return 'break'

        self.sql_context.bind('<Control-KeyPress>', _text_ctrl_key)
                
        # Query Buttons Frame - REDESIGNED for better UX/UI
        query_buttons = ttk.Frame(query_frame)
        query_buttons.grid(row=1, column=0, pady=10)
        
        # Add subtle background and padding
        query_buttons_inner = tk.Frame(query_buttons, bg='#ecf0f1', relief='flat', bd=0)
        query_buttons_inner.pack(padx=5, pady=5)
        
        # Row 0 - Primary Actions (Data Management)
        primary_label = tk.Label(query_buttons_inner, text="📊 Data Operations",
                                 font=('Arial', 9, 'bold'), bg='#ecf0f1', fg='#34495e')
        primary_label.grid(row=0, column=0, columnspan=3, pady=(5, 8), sticky='w', padx=10)
        
        # Load Table Data - First position
        self.load_excel_btn = tk.Button(
            query_buttons_inner,
            text="📗 Load Excel",
            command=self.load_excel_template_dialog,
            bg='#2ecc71',
            fg='white',
            font=('Arial', 10, 'bold'),
            relief='raised',
            bd=2,
            padx=20,
            pady=8,
            cursor='hand2'
        )
        self.load_excel_btn.grid(row=1, column=1, padx=5, pady=2)

        self.reset_sql_template_btn = tk.Button(
            query_buttons_inner,
            text="↩ Reset SQL Template",
            command=self.show_reset_parameter_dialog,
            bg="#7f8c8d",
            fg="white",
            font=("Arial", 9, "bold"),
            relief="raised",
            bd=2,
            padx=10,
            pady=8,
            cursor="hand2"
        )
        self.reset_sql_template_btn.grid(row=1, column=4, padx=5, pady=2)
        # Execute Query - Second position
        self.execute_btn = tk.Button(query_buttons_inner,
                                     text="▶️ Execute",
                                     command=self.execute_query,
                                     state="disabled",
                                     bg='#27ae60', fg='white',
                                     font=('Arial', 10, 'bold'),
                                     relief='raised', bd=2,
                                     padx=20, pady=8,
                                     cursor='hand2',
                                     activebackground='#229954',
                                     activeforeground='white')
        self.execute_btn.grid(row=1, column=2, padx=5, pady=2)
        
        # Save Job - Third position
        self.save_job_btn = tk.Button(query_buttons_inner,
                                      text="💾 Save Job",
                                      command=self.save_job_dialog,
                                      bg='#f39c12', fg='white',
                                      font=('Arial', 10, 'bold'),
                                      relief='raised', bd=2,
                                      padx=20, pady=8,
                                      cursor='hand2',
                                      activebackground='#e67e22',
                                      activeforeground='white')
        self.save_job_btn.grid(row=1, column=3, padx=5, pady=2)
        
        # Separator line
        separator1 = tk.Frame(query_buttons_inner, height=2, bg='#bdc3c7')
        separator1.grid(row=2, column=0, columnspan=3, sticky='ew', padx=10, pady=8)
        
        # Row 3 - Secondary Actions (Database Tools)
        secondary_label = tk.Label(query_buttons_inner, text="🔧 Database Tools",
                                   font=('Arial', 9, 'bold'), bg='#ecf0f1', fg='#34495e')
        secondary_label.grid(row=3, column=0, columnspan=3, pady=(5, 8), sticky='w', padx=10)
        
        # List Tables - Centered and wider (spans 2 columns)
        self.inspect_btn = tk.Button(query_buttons_inner,
                                     text="📊 List Tables",
                                     command=self.list_tables,
                                     state="disabled",
                                     bg='#8e44ad', fg='white',
                                     font=('Arial', 10, 'bold'),
                                     relief='raised', bd=2,
                                     padx=40, pady=8,  # Wider padding
                                     cursor='hand2',
                                     activebackground='#7d3c98',
                                     activeforeground='white')
        self.inspect_btn.grid(row=4, column=0, columnspan=3, padx=5, pady=2)  # Span all columns
        
        # Keyboard shortcut binding
        self.sql_context.bind('<Control-Return>', lambda _event: self.execute_query() if self.execute_btn['state'] != 'disabled' else None)
        
        # Jobs Section - REDESIGNED with inline action buttons
        jobs_frame = ttk.LabelFrame(main_frame, text="📋 Saved Jobs & Presets", padding="15")
        jobs_frame.grid(row=2, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))
        jobs_frame.columnconfigure(0, weight=1)
        jobs_frame.rowconfigure(1, weight=1)
        
        # Top controls - Add job and preset management
        controls_frame = tk.Frame(jobs_frame, bg='#ffffff')
        controls_frame.pack(fill='both', pady=(0, 10))
        
        tk.Button(controls_frame, text="➕ New Job", command=self.save_job_dialog,
                 bg='#27ae60', fg='white', font=('Arial', 9, 'bold'),
                 relief='flat', padx=15, pady=5, cursor='hand2').pack(side='left', padx=(0, 5))
        
        tk.Button(controls_frame, text="💾 Save as Preset", command=self.save_preset_dialog,
                 bg='#3498db', fg='white', font=('Arial', 9, 'bold'),
                 relief='flat', padx=15, pady=5, cursor='hand2').pack(side='left', padx=5)
        
        tk.Button(controls_frame, text="📂 Load Preset", command=self.load_preset_dialog,
                 bg='#9b59b6', fg='white', font=('Arial', 9, 'bold'),
                 relief='flat', padx=15, pady=5, cursor='hand2').pack(side='left', padx=5)
        
        self.export_excel_btn = tk.Button(controls_frame, text="📤 Export Excel", command=self.export_jobs_to_excel,
                 bg='#16a085', fg='white', font=('Arial', 9, 'bold'),
                 relief='flat', padx=15, pady=5, cursor='hand2')
        self.export_excel_btn.pack(side='left', padx=5)

        tk.Button(controls_frame, text="▶️ Run All Jobs", command=self.run_selected_job,
                 bg='#e67e22', fg='white', font=('Arial', 9, 'bold'),
                 relief='flat', padx=15, pady=5, cursor='hand2').pack(side='right')
        
        # Jobs list frame with scrollbar
        jobs_list_frame = tk.Frame(jobs_frame, bg='#ffffff', relief='solid', bd=1)
        jobs_list_frame.pack(fill='both', expand=True)
        
        # Canvas for scrollable job list
        jobs_canvas = tk.Canvas(jobs_list_frame, bg='#ffffff', highlightthickness=0, height=250)
        jobs_scrollbar = ttk.Scrollbar(jobs_list_frame, orient='vertical', command=jobs_canvas.yview)
        self.jobs_container = tk.Frame(jobs_canvas, bg='#ffffff')
        
        jobs_canvas.configure(yscrollcommand=jobs_scrollbar.set)
        jobs_scrollbar.pack(side='right', fill='y')
        jobs_canvas.pack(side='left', fill='both', expand=True)
        
        # Create window in canvas
        jobs_canvas_window = jobs_canvas.create_window((0, 0), window=self.jobs_container, anchor='nw')
        
        def jobs_content_overflows():
            bounds = jobs_canvas.bbox('all')
            return bool(
                bounds and
                bounds[3] - bounds[1] > jobs_canvas.winfo_height() + 1
            )

        def update_jobs_scroll_state():
            bounds = jobs_canvas.bbox('all')
            jobs_canvas.configure(scrollregion=bounds or (0, 0, 0, 0))
            if jobs_content_overflows():
                if not jobs_scrollbar.winfo_ismapped():
                    jobs_scrollbar.pack(side='right', fill='y')
            else:
                jobs_canvas.yview_moveto(0)
                if jobs_scrollbar.winfo_ismapped():
                    jobs_scrollbar.pack_forget()

        def configure_jobs_scroll(event):
            jobs_canvas.itemconfig(jobs_canvas_window, width=event.width)
            jobs_canvas.after_idle(update_jobs_scroll_state)

        def resize_jobs_canvas(event):
            jobs_canvas.itemconfig(jobs_canvas_window, width=event.width)
            jobs_canvas.after_idle(update_jobs_scroll_state)
        
        self.jobs_container.bind('<Configure>', configure_jobs_scroll)
        jobs_canvas.bind('<Configure>', resize_jobs_canvas)
        jobs_canvas.after_idle(update_jobs_scroll_state)
                
        def on_jobs_mousewheel(event):
            # Check if canvas still exists before scrolling
            if jobs_canvas.winfo_exists() and jobs_content_overflows():
                try:
                    jobs_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
                except tk.TclError:
                    # Widget was destroyed between check and scroll
                    pass
        
        # Scoped binding: scroll jobs list when hovering over it, restore main scroll when leaving
        jobs_canvas.bind("<Enter>", lambda _event: jobs_canvas.bind_all("<MouseWheel>", on_jobs_mousewheel))
        jobs_canvas.bind("<Leave>", lambda _event: jobs_canvas.bind_all("<MouseWheel>", self._main_mousewheel))
        
        # Store references
        self.jobs_canvas = jobs_canvas
        self.jobs_list_frame = jobs_list_frame
        
        # Update jobs list
        self.update_jobs_list()
        
        # Results Section
        results_frame = ttk.LabelFrame(main_frame, text="📊 Results", padding="15")
        results_frame.grid(row=3, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))
        results_frame.columnconfigure(0, weight=1)
        
        # Results Text Area
        self.results_text = scrolledtext.ScrolledText(results_frame, height=30, width=140, font=('Arial', 10), wrap=tk.NONE)
        self.results_text.grid(row=0, column=0, sticky=(tk.W, tk.E))

        # Scoped mouse wheel: scroll results text when hovering, restore main scroll when leaving
        def _on_results_enter(_event):
            self.results_text.bind_all("<MouseWheel>", lambda ev: self.results_text.yview_scroll(int(-1 * (ev.delta / 120)), "units"))

        def _on_results_leave(_event):
            self.results_text.bind_all("<MouseWheel>", self._main_mousewheel)

        self.results_text.bind("<Enter>", _on_results_enter)
        self.results_text.bind("<Leave>", _on_results_leave)
        self.results_text.bind('<Control-KeyPress>', _text_ctrl_key)

        # Auto-load last used profile
        self.auto_load_last_profile()
        
        # Add context menus
        self.setup_context_menus()
    
    def _create_centered_dialog(self, title, width, height):
        """Helper method to create centered dialog with consistent styling"""
        dialog = tk.Toplevel(self.root)
        dialog.title(title)
        dialog.geometry(f"{width}x{height}")
        dialog.configure(bg='#f0f0f0')
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
            messagebox.showinfo("No Profiles", "No profiles to export.\n\nCreate and save a profile first.")
            return
        
        # Ask user where to save
        file_path = filedialog.asksaveasfilename(
            title="Export Profiles",
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            initialfile="db_profiles_backup.json"
        )
        
        if not file_path:
            return  # User cancelled

        include_passwords = messagebox.askyesnocancel(
            "Export Passwords?",
            "Include passwords in the exported file?\n\n"
            "Yes = include (plain text, so it can be imported on another computer)\n"
            "No = export without passwords (safer - re-enter them after import)"
        )
        if include_passwords is None:
            return  # User cancelled

        try:
            export_profiles = {}
            for name, profile in self.saved_profiles.items():
                profile_copy = dict(profile)
                if not include_passwords:
                    profile_copy['db_password'] = ""
                export_profiles[name] = profile_copy

            # Export profiles with metadata
            export_data = {
                'exported_date': pd.Timestamp.now().isoformat(),
                'total_profiles': len(export_profiles),
                'passwords_included': bool(include_passwords),
                'profiles': export_profiles
            }
            
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, indent=2, ensure_ascii=False)
            
            # Show success with file location
            self.results_text.insert(tk.END, f"📤 Profiles exported successfully!\n")
            self.results_text.insert(tk.END, f"📁 Location: {file_path}\n")
            self.results_text.insert(tk.END, f"📊 Profiles: {len(self.saved_profiles)}\n\n")
            self.results_text.see(tk.END)
            
            messagebox.showinfo("Export Success",
                               f"✅ Profiles exported successfully!\n\n"
                               f"📁 Location:\n{file_path}\n\n"
                               f"📊 Total profiles: {len(self.saved_profiles)}\n\n"
                               f"💡 You can import this file on any computer.")
            
        except Exception as e:
            error_msg = f"Failed to export profiles:\n\n{str(e)}"
            self.results_text.insert(tk.END, f"❌ Export failed: {str(e)}\n\n")
            self.results_text.see(tk.END)
            messagebox.showerror("Export Error", error_msg)
    
    def import_profiles_dialog(self):
        """Import profiles from a user-selected JSON file"""
        # Ask user to select file
        file_path = filedialog.askopenfilename(
            title="Import Profiles",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        
        if not file_path:
            return  # User cancelled
        
        try:
            # Load the file
            with open(file_path, 'r', encoding='utf-8') as f:
                import_data = json.load(f)
            
            # Check if it's an export file or raw profile data
            if 'profiles' in import_data:
                # New export format
                imported_profiles = import_data['profiles']
                export_date = import_data.get('exported_date', 'Unknown')
                total_count = import_data.get('total_profiles', len(imported_profiles))
            else:
                # Raw profile data (old format)
                imported_profiles = {k: v for k, v in import_data.items() 
                                   if k != 'last_used_profile' and isinstance(v, dict)}
                export_date = 'Unknown'
                total_count = len(imported_profiles)
            
            if not imported_profiles:
                messagebox.showwarning("No Profiles",
                                     "No valid profiles found in the selected file.")
                return
            
            # Show preview dialog
            self._show_import_preview_dialog(imported_profiles, file_path, export_date, total_count)
            
        except json.JSONDecodeError:
            messagebox.showerror("Import Error",
                               "Invalid JSON file.\n\n"
                               "Please select a valid profile export file.")
        except Exception as e:
            messagebox.showerror("Import Error",
                               f"Failed to import profiles:\n\n{str(e)}")
    
    def _show_import_preview_dialog(self, imported_profiles, file_path, export_date, total_count):
        """Show preview dialog before importing profiles"""
        dialog = tk.Toplevel(self.root)
        dialog.title("📥 Import Profiles")
        dialog.geometry("700x600")
        dialog.configure(bg='#f0f0f0')
        dialog.transient(self.root)
        dialog.grab_set()
        
        # Center dialog
        x = (self.root.winfo_screenwidth() - 700) // 2
        y = (self.root.winfo_screenheight() - 600) // 2
        dialog.geometry(f"+{x}+{y}")
        
        # Scrollable content container (Canvas + Scrollbar + inner frame)
        outer_frame = tk.Frame(dialog, bg='#ffffff', relief='solid', bd=1)
        outer_frame.pack(fill='both', expand=True, padx=15, pady=15)

        content_canvas = tk.Canvas(outer_frame, bg='#ffffff', highlightthickness=0)
        content_scrollbar = ttk.Scrollbar(outer_frame, orient='vertical', command=content_canvas.yview)
        content_canvas.configure(yscrollcommand=content_scrollbar.set)

        content_scrollbar.pack(side='right', fill='y')
        content_canvas.pack(side='left', fill='both', expand=True)

        content_frame = tk.Frame(content_canvas, bg='#ffffff')
        content_canvas_window = content_canvas.create_window((0, 0), window=content_frame, anchor='nw')

        def _update_dialog_scrollregion(event=None):
            content_canvas.configure(scrollregion=content_canvas.bbox('all'))

        def _sync_dialog_canvas_width(event):
            content_canvas.itemconfig(content_canvas_window, width=event.width)

        def _on_dialog_mousewheel(event):
            if event.widget.winfo_class() == 'Listbox':
                return
            content_canvas.yview_scroll(int(-1 * (event.delta / 120)), 'units')

        content_frame.bind('<Configure>', _update_dialog_scrollregion)
        content_canvas.bind('<Configure>', _sync_dialog_canvas_width)
        dialog.bind('<MouseWheel>', _on_dialog_mousewheel)
        
        # Title
        tk.Label(content_frame, text="📥 Import Profiles Preview",
                font=('Arial', 14, 'bold'), bg='#ffffff', fg='#2c3e50').pack(pady=(10, 15))
        
        # File info
        info_frame = tk.Frame(content_frame, bg='#e8f4f8', relief='solid', bd=1)
        info_frame.pack(fill='both', padx=10, pady=(0, 15))
        
        info_text = f"📁 File: {os.path.basename(file_path)}\n"
        info_text += (
                    f"📅 Exported: "
                    f"{export_date[:19] if export_date != 'Unknown' else 'Unknown'}\n"
                    )
        info_text += f"📊 Profiles in file: {total_count}"
        
        tk.Label(info_frame, text=info_text, font=('Arial', 9),
        bg='#e8f4f8', fg='#2c3e50', justify='left').pack(anchor='w', padx=10, pady=8)
        
        # Current vs Import status
        status_frame = tk.LabelFrame(content_frame, text="Import Status",
                                    font=('Arial', 11, 'bold'), bg='#ffffff')
        status_frame.pack(fill='both', padx=10, pady=(0, 15))
        
        status_inner = tk.Frame(status_frame, bg='#ffffff')
        status_inner.pack(fill='both', padx=10, pady=10)
        
        current_count = len(self.saved_profiles)
        new_profiles = [p for p in imported_profiles.keys() if p not in self.saved_profiles]
        existing_profiles = [p for p in imported_profiles.keys() if p in self.saved_profiles]
        
        tk.Label(status_inner, text=f"📊 Current profiles: {current_count}",
                font=('Arial', 10), bg='#ffffff', fg='#2c3e50').pack(anchor='w', pady=2)
        tk.Label(status_inner, text=f"➕ New profiles to add: {len(new_profiles)}",
                font=('Arial', 10), bg='#ffffff', fg='#27ae60').pack(anchor='w', pady=2)
        tk.Label(status_inner, text=f"🔄 Existing profiles (will be updated): {len(existing_profiles)}",
                font=('Arial', 10), bg='#ffffff', fg='#f39c12').pack(anchor='w', pady=2)
        tk.Label(status_inner, text=f"📊 Total after import: {len(set(list(self.saved_profiles.keys()) + list(imported_profiles.keys())))}",
                font=('Arial', 10, 'bold'), bg='#ffffff', fg='#3498db').pack(anchor='w', pady=(10, 2))
        
        # Profile list
        list_frame = tk.LabelFrame(content_frame, text="Profiles to Import",
                                  font=('Arial', 11, 'bold'), bg='#ffffff')
        list_frame.pack(fill='both', expand=True, padx=10, pady=(0, 15))
        
        list_inner = tk.Frame(list_frame, bg='#ffffff')
        list_inner.pack(fill='both', expand=True, padx=10, pady=10)
        
        scrollbar = tk.Scrollbar(list_inner)
        scrollbar.pack(side='right', fill='y')
        
        profiles_listbox = tk.Listbox(list_inner, font=('Arial', 10),
                                      yscrollcommand=scrollbar.set,
                                      height=10)
        profiles_listbox.pack(side='left', fill='both', expand=True)
        scrollbar.config(command=profiles_listbox.yview)
        
        # Populate list
        for profile_name, profile_data in imported_profiles.items():
            db_type = profile_data.get('db_type', 'N/A')
            host = profile_data.get('db_host', 'N/A')
            status_icon = "➕" if profile_name not in self.saved_profiles else "🔄"
            profiles_listbox.insert('end', f"{status_icon} {profile_name} ({db_type} @ {host})")
        
        # Import options
        options_frame = tk.LabelFrame(content_frame, text="Import Options",
                                     font=('Arial', 11, 'bold'), bg='#ffffff')
        options_frame.pack(fill='both', padx=10, pady=(0, 15))
        
        merge_var = tk.BooleanVar(value=True)
        
        tk.Radiobutton(options_frame,
                       text="🔄 Merge (keep existing + add new profiles)",
                       variable=merge_var,
                       value=True,
                       font=('Arial', 10),
                       bg='#ffffff').pack(anchor='w', padx=10, pady=5)
        
        tk.Radiobutton(options_frame,
                       text="🔁 Replace (delete all existing profiles)",
                       variable=merge_var,
                       value=False,
                       font=('Arial', 10),
                       bg='#ffffff').pack(anchor='w', padx=10, pady=5)
        
        # Warning
        warning_frame = tk.Frame(content_frame, bg='#fff3cd', relief='solid', bd=1)
        warning_frame.pack(fill='both', padx=10, pady=(0, 15))
        
        tk.Label(warning_frame,
                text="⚠️ Importing will update existing profiles with the same name.\n"
                     "💡 Consider exporting current profiles as backup first.",
                font=('Arial', 9), bg='#fff3cd', fg='#856404',
                justify='left').pack(padx=10, pady=8)
        
        # Buttons
        button_frame = tk.Frame(content_frame, bg='#ffffff')
        button_frame.pack(fill='both', padx=10, pady=(0, 10))
        
        def do_import():
            try:
                merge_mode = merge_var.get()
                previous_profiles = dict(self.saved_profiles)

                if not merge_mode:
                    # Replace mode - confirm
                    result = messagebox.askyesno("Confirm Replace",
                                                f"⚠️ This will DELETE all {len(self.saved_profiles)} existing profiles!\n\n"
                                                f"Are you sure?",
                                                parent=dialog)
                    if not result:
                        return
                    
                    # Clear existing profiles
                    self.saved_profiles.clear()
                
                # Import profiles
                for profile_name, profile_data in imported_profiles.items():
                    profile_data = dict(profile_data)
                    imported_password = unprotect_password(profile_data.get('db_password', ''))
                    existing_password = previous_profiles.get(profile_name, {}).get('db_password', '')
                    # File exported without passwords -> keep the password we already have
                    profile_data['db_password'] = imported_password or existing_password
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
                    self.results_text.insert(tk.END, f"🔄 Updated profiles: {len(existing_profiles)}\n")
                self.results_text.insert(tk.END, f"\n")
                self.results_text.see(tk.END)
                
                # Success message
                mode_text = "merged" if merge_mode else "replaced"
                messagebox.showinfo("Import Success",
                                   f"✅ Profiles {mode_text} successfully!\n\n"
                                   f"📊 Total profiles now: {len(self.saved_profiles)}\n"
                                   f"➕ New: {len(new_profiles)}\n"
                                   f"🔄 Updated: {len(existing_profiles) if merge_mode else 0}",
                                   parent=dialog)
                
                dialog.destroy()
                
            except Exception as e:
                messagebox.showerror("Import Error",
                                   f"Failed to import profiles:\n\n{str(e)}",
                                   parent=dialog)
        
        tk.Button(button_frame, text="📥 Import Profiles", command=do_import,
                 bg='#27ae60', fg='white', font=('Arial', 10, 'bold'),
                 padx=20, pady=6).pack(side='left')
        
        cancel_btn = tk.Button(
                button_frame,
                text="✖ Cancel",
                width=12,
                height=2,
                bg="#95a5a6",
                fg="white",
                font=("Arial", 10, "bold"),
                command=dialog.destroy
            )

        cancel_btn.pack(
                side="left",
                padx=5
            )

        _update_dialog_scrollregion()
    
    def show_config_file_location(self):
        """Show where the config file is/should be located - Helper function"""
        dialog = tk.Toplevel(self.root)
        dialog.title("📁 Config File Location")
        dialog.geometry("600x550")
        dialog.configure(bg='#f0f0f0')
        dialog.transient(self.root)
        dialog.grab_set()
        
        # Center dialog
        x = (self.root.winfo_screenwidth() - 600) // 2
        y = (self.root.winfo_screenheight() - 400) // 2
        dialog.geometry(f"+{x}+{y}")
        
        # Content
        content = tk.Frame(dialog, bg='#ffffff', relief='solid', bd=1)
        content.pack(fill='both', expand=True, padx=15, pady=15)
        
        tk.Label(content, text="📁 Config File Location",
                font=('Arial', 14, 'bold'), bg='#ffffff', fg='#2c3e50').pack(pady=(10, 15))
        
        # File info
        info_frame = tk.LabelFrame(content, text="File Information",
                                  font=('Arial', 11, 'bold'), bg='#ffffff')
        info_frame.pack(fill='both', expand=True, padx=10, pady=(0, 15))
        
        info_inner = tk.Frame(info_frame, bg='#ffffff')
        info_inner.pack(fill='both', expand=True, padx=10, pady=10)
        
        # Path
        tk.Label(info_inner, text="📁 Full Path:", font=('Arial', 10, 'bold'),
                bg='#ffffff', fg='#2c3e50').pack(anchor='w', pady=(0, 5))
        
        path_text = tk.Text(info_inner, height=3, font=('Courier', 9),
                           bg='#f8f9fa', wrap=tk.WORD)
        path_text.pack(fill='both', pady=(0, 10))
        path_text.insert(1.0, self.config_file)
        path_text.config(state='disabled')
        
        # Status
        file_exists = os.path.exists(self.config_file)
        status_icon = "✅" if file_exists else "❌"
        status_text = "EXISTS" if file_exists else "NOT FOUND"
        status_color = "#27ae60" if file_exists else "#e74c3c"
        
        tk.Label(info_inner, text=f"📊 Status: {status_icon} {status_text}",
                font=('Arial', 10, 'bold'),
                bg='#ffffff', fg=status_color).pack(anchor='w', pady=(0, 5))
        
        if file_exists:
            file_size = os.path.getsize(self.config_file)
            tk.Label(info_inner, text=f"📏 Size: {file_size:,} bytes",
                    font=('Arial', 10),
                    bg='#ffffff', fg='#2c3e50').pack(anchor='w', pady=(0, 5))
            
            tk.Label(info_inner, text=f"📊 Profiles: {len(self.saved_profiles)}",
                    font=('Arial', 10),
                    bg='#ffffff', fg='#2c3e50').pack(anchor='w')
        
        # Help text
        help_frame = tk.Frame(content, bg='#e8f4f8', relief='solid', bd=1)
        help_frame.pack(fill='both', padx=10, pady=(0, 15))
        
        if file_exists:
                help_text = "💡 Tips:\n\n"
        else:
                help_text = "💡 If the file doesn't exist:\n\n"
        help_text += "1. Save a profile to create the file automatically\n"
        help_text += "2. Use 'Export' to backup your profiles\n"
        help_text += "3. Use 'Import' to restore from backup\n"
        help_text += "4. Share exported files between computers"
        
        tk.Label(help_frame, text=help_text, font=('Arial', 9),
                bg='#e8f4f8', fg='#2c3e50', justify='left').pack(padx=10, pady=10)
        
        # Buttons
        button_frame = tk.Frame(content, bg='#ffffff')
        button_frame.pack(pady=(0, 10))
        
        def open_folder():
            folder_path = os.path.dirname(self.config_file)
            if os.path.exists(folder_path):
                os.startfile(folder_path)
            else:
                messagebox.showwarning("Folder Not Found",
                                     f"Folder doesn't exist:\n{folder_path}",
                                     parent=dialog)
        
        def copy_path():
            self.root.clipboard_clear()
            self.root.clipboard_append(self.config_file)
            messagebox.showinfo("Copied", "Path copied to clipboard!", parent=dialog)
        
        tk.Button(button_frame, text="📂 Open Folder", command=open_folder,
                 bg='#3498db', fg='white', font=('Arial', 10, 'bold'),
                 padx=15, pady=6).pack(side='left', padx=5)
        
        tk.Button(button_frame, text="📋 Copy Path", command=copy_path,
                 bg='#9b59b6', fg='white', font=('Arial', 10, 'bold'),
                 padx=15, pady=6).pack(side='left', padx=5)
        
        tk.Button(button_frame, text="❌ Close", command=dialog.destroy,
                 bg='#95a5a6', fg='white', font=('Arial', 10, 'bold'),
                 padx=15, pady=6).pack(side='left', padx=5)

    def update_jobs_list(self):

        # ป้องกันเรียกก่อนสร้าง UI
        if not hasattr(self, "jobs_container"):
            return

        # Clear current jobs display
        for widget in self.jobs_container.winfo_children():
            widget.destroy()

        current_profile = self.profile_combo.get()

        filtered_jobs = [
            job
            for job in self.saved_jobs
            if job.get(
                "profile",
                current_profile
            ) == current_profile
        ]

        for idx, job in enumerate(filtered_jobs, 1):

            real_idx = self.saved_jobs.index(job)

            job_frame = ttk.Frame(self.jobs_container)
            job_frame.pack(fill=tk.X, pady=2)

            job_name = job.get('name', f'Job {idx}')

            ttk.Label(
                job_frame,
                text=f"{idx}. {job_name}",
                font=('Arial', 9)
            ).pack(side=tk.LEFT)

            ttk.Button(
                job_frame,
                text="▶ Run",
                width=8,
                command=lambda j=job: self.run_job(j)
            ).pack(side=tk.RIGHT, padx=1)

            ttk.Button(
                job_frame,
                text="✏ Edit",
                width=8,
                command=lambda i=real_idx: self.edit_job(i)
            ).pack(side=tk.RIGHT, padx=1)

            ttk.Button(
                job_frame,
                text="🗑 Delete",
                width=8,
                command=lambda i=real_idx, n=job_name:
                    self.delete_job(i, n)
            ).pack(side=tk.RIGHT, padx=1)
    
    def run_single_job(self, job):
        """Run one saved job using the shared Results format."""
        self.run_job(job)
    
    def load_job_to_editor(self, job):
        """Load job to SQL editor - CLEAN output"""
        self.sql_context.delete(1.0, tk.END)
        self.sql_context.insert(1.0, job['query'])
        
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
        dialog.geometry("700x550")
        dialog.configure(bg='#f0f0f0')
        dialog.transient(self.root)
        dialog.grab_set()

        x = (self.root.winfo_screenwidth() - 700) // 2
        y = (self.root.winfo_screenheight() - 550) // 2
        dialog.geometry(f"700x550+{x}+{y}")

        content = tk.Frame(
            dialog,
            bg='#ffffff',
            relief='solid',
            bd=1
        )
        content.pack(
            fill='both',
            expand=True,
            padx=15,
            pady=15
        )

        tk.Label(
            content,
            text="✏️ Edit Job",
            font=('Arial', 14, 'bold'),
            bg='#ffffff',
            fg='#2c3e50'
        ).pack(
            pady=(10, 20)
        )

        # Job Name
        tk.Label(
            content,
            text="Job Name:",
            font=('Arial', 10, 'bold'),
            bg='#ffffff'
        ).pack(
            anchor='w',
            padx=10,
            pady=(0, 5)
        )

        name_entry = tk.Entry(
            content,
            font=('Arial', 10),
            width=60
        )

        name_entry.pack(
            padx=10,
            pady=(0, 15)
        )

        name_entry.insert(
            0,
            job['name']
        )

        # SQL Label
        tk.Label(
            content,
            text="SQL Query:",
            font=('Arial', 10, 'bold'),
            bg='#ffffff'
        ).pack(
            anchor='w',
            padx=10,
            pady=(0, 5)
        )

        # SQL Editor Frame
        query_frame = tk.Frame(
            content,
            bg='#ffffff'
        )

        query_frame.pack(
            fill='both',
            expand=True,
            padx=10,
            pady=(0, 10)
        )

        query_scroll = tk.Scrollbar(query_frame)

        query_scroll.pack(
            side='right',
            fill='y'
        )

        query_text = tk.Text(
            query_frame,
            height=12,
            font=('Courier', 9),
            yscrollcommand=query_scroll.set
        )

        query_text.pack(
            side='left',
            fill='both',
            expand=True
        )

        query_scroll.config(
            command=query_text.yview
        )

        query_text.insert(
            "1.0",
            job['query']
        )

        # ===================================================
        # Excel Parameter Tools
        # ===================================================

        tool_frame = ttk.LabelFrame(
            content,
            text="Excel Parameter Tools",
            padding=8
        )

        tool_frame.pack(
            fill="x",
            padx=10,
            pady=(0, 10)
        )

        excel_button_frame = ttk.Frame(tool_frame)
        excel_button_frame.pack(fill="x")
        edit_excel_state = {
            "template": job["query"],
            "values": {},
            "rendered": None
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
                self.show_reset_parameter_dialog(
                    close_after_selected=True,
                    wait=True
                )
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

        ttk.Button(
            excel_button_frame,
            text="📗 Load Excel",
            command=load_excel_for_edit
        ).pack(side="left", padx=(0, 6))
        ttk.Button(
            excel_button_frame,
            text="↩ Reset SQL Template",
            command=reset_parameter_for_edit
        ).pack(side="left")

        def save_changes():
            new_name = name_entry.get().strip()

            new_query = query_text.get(
                "1.0",
                tk.END
            ).strip()

            if not new_name:
                messagebox.showwarning(
                    "Warning",
                    "Job name cannot be empty",
                    parent=dialog
                )
                return

            if not new_query:
                messagebox.showwarning(
                    "Warning",
                    "SQL Query cannot be empty",
                    parent=dialog
                )
                return

            self.saved_jobs[job_idx]['name'] = new_name
            self.saved_jobs[job_idx]['query'] = new_query

            self.save_jobs()
            self.update_jobs_list()

            self.results_text.delete(
                "1.0",
                tk.END
            )

            self.results_text.insert(
                tk.END,
                f"✅ Job updated: {new_name}\n"
            )

            self.results_text.see(
                tk.END
            )

            messagebox.showinfo(
                "Success",
                "Job updated successfully!",
                parent=dialog
            )

            dialog.destroy()

        action_frame = ttk.Frame(content)
        action_frame.pack(fill="x", padx=10, pady=(0, 10))
        ttk.Button(
            action_frame,
            text="Save Changes",
            command=save_changes
        ).pack(side="right", padx=(6, 0))
        ttk.Button(
            action_frame,
            text="Cancel",
            command=dialog.destroy
        ).pack(side="right")
    
    def delete_job(self, job_idx, job_name):
        """Delete job with confirmation"""
        result = messagebox.askyesno("Confirm Delete",
                                f"Delete job '{job_name}'?\n\nThis cannot be undone.")
        if result:
            self.saved_jobs.pop(job_idx)
            self.save_jobs()
            self.update_jobs_list()
            
            self.results_text.delete("1.0", tk.END)
            self.results_text.insert(tk.END, f"🗑️ Deleted: {job_name}\n")
            self.results_text.insert(tk.END, f"📊 Remaining: {len(self.saved_jobs)} jobs\n")
            self.results_text.see(tk.END)
    
    def save_preset_dialog(self):
        """Save current jobs as a preset"""
        current_profile = self.profile_combo.get()

        profile_jobs = [
            job
            for job in self.saved_jobs
            if job.get("profile") == current_profile
        ]
        
        for index, job in enumerate(profile_jobs, start=1):
            job["run_index"] = index

        if not profile_jobs:
            messagebox.showwarning(
                "Warning",
                "No jobs to run"
            )
            return
        
        dialog = tk.Toplevel(self.root)
        dialog.title("💾 Save Preset")
        dialog.geometry("550x320")
        dialog.minsize(550, 320)
        dialog.configure(bg='#f0f0f0')
        dialog.transient(self.root)
        dialog.grab_set()
        
        x = (self.root.winfo_screenwidth() - 550) // 2
        y = (self.root.winfo_screenheight() - 320) // 2

        dialog.geometry(f"550x320+{x}+{y}")
        
        content = tk.Frame(dialog, bg='#ffffff', relief='solid', bd=1)
        content.pack(
            fill='both',
            expand=True,
            padx=15,
            pady=15
        )
        
        tk.Label(content, text="💾 Save Jobs as Preset", font=('Arial', 12, 'bold'),
                bg='#ffffff', fg='#2c3e50').pack(pady=(10, 15))
        
        tk.Label(content, text="Preset Name:", font=('Arial', 10),
                bg='#ffffff').pack(pady=(0, 5))
        
        name_entry = tk.Entry(content, font=('Arial', 10), width=40)
        name_entry.pack(pady=5)
        name_entry.focus()
        
        tk.Label(content, text=f"💡 Will save {len(profile_jobs)} jobs",
                font=('Arial', 9, 'italic'), bg='#ffffff', fg='#7f8c8d').pack(pady=(10, 0))
        
        def save():
            preset_name = name_entry.get().strip()
            if not preset_name:
                messagebox.showwarning("Warning", "Please enter preset name", parent=dialog)
                return
            
            preset_file = os.path.join(os.path.dirname(self.jobs_file), f"preset_{preset_name}.json")
            
            try:
                with open(preset_file, 'w', encoding='utf-8') as f:
                    json.dump({'jobs': profile_jobs, 'created': pd.Timestamp.now().isoformat()},
                             f, indent=2, ensure_ascii=False)
                
                self.results_text.delete("1.0", tk.END)
                self.results_text.insert(tk.END, f"💾 Preset saved: {preset_name}\n")
                self.results_text.insert(tk.END, f"📊 Jobs: {len(profile_jobs)}\n")
                self.results_text.insert(tk.END, f"📁 Location: {preset_file}\n")
                self.results_text.see(tk.END)

                messagebox.showinfo("Success", f"Preset '{preset_name}' saved!\n\n{len(profile_jobs)} jobs included", parent=dialog)
                dialog.destroy()
            except Exception as e:
                messagebox.showerror("Error", f"Failed to save preset:\n{str(e)}", parent=dialog)
        
        button_frame = tk.Frame(content, bg='#ffffff')
        button_frame.pack(
            side=tk.BOTTOM,
            pady=(20, 15)
        )
        
        save_btn = tk.Button(
            button_frame,
            text="💾 Save",
            width=12,
            height=2,
            bg="#27ae60",
            fg="white",
            font=("Arial", 10, "bold"),
            command=save
        )

        save_btn.pack(
            side="left",
            padx=5
        )
        
        cancel_btn = tk.Button(
            button_frame,
            text="✖ Cancel",
            width=12,
            height=2,
            bg="#95a5a6",
            fg="white",
            font=("Arial", 10, "bold"),
            command=dialog.destroy
        )

        cancel_btn.pack(
            side="left",
            padx=5
        )
    
    def load_preset_dialog(self):
        """Load jobs from a preset"""
        preset_dir = os.path.dirname(self.jobs_file)
        preset_files = [f for f in os.listdir(preset_dir) if f.startswith('preset_') and f.endswith('.json')]
        
        if not preset_files:
            messagebox.showinfo("No Presets", "No saved presets found")
            return
        
        dialog = tk.Toplevel(self.root)
        dialog.title("📂 Load Preset")
        dialog.geometry("600x450")
        dialog.configure(bg='#f0f0f0')
        dialog.transient(self.root)
        dialog.grab_set()
        
        x = (self.root.winfo_screenwidth() - 600) // 2
        y = (self.root.winfo_screenheight() - 400) // 2
        dialog.geometry(f"+{x}+{y}")
        
        content = tk.Frame(dialog, bg='#ffffff', relief='solid', bd=1)
        content.pack(fill='both', expand=True, padx=15, pady=15)
        
        tk.Label(content, text="📂 Load Preset", font=('Arial', 14, 'bold'),
                bg='#ffffff', fg='#2c3e50').pack(pady=(10, 15))
        
        # Preset list
        list_frame = tk.Frame(content, bg='#ffffff')
        list_frame.pack(fill='both', expand=True, pady=(0, 15))
        
        scrollbar = tk.Scrollbar(list_frame)
        scrollbar.pack(side='right', fill='y')
        
        preset_listbox = tk.Listbox(list_frame, font=('Arial', 10),
                                    yscrollcommand=scrollbar.set)
        preset_listbox.pack(side='left', fill='both', expand=True)
        scrollbar.config(command=preset_listbox.yview)
        
        # Populate presets
        preset_data = {}
        for preset_file in preset_files:
            preset_path = os.path.join(preset_dir, preset_file)
            try:
                with open(preset_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    preset_name = preset_file.replace('preset_', '').replace('.json', '')
                    job_count = len(data.get('jobs', []))
                    created = data.get('created', 'N/A')
                    preset_listbox.insert('end', f"{preset_name} ({job_count} jobs) - {created[:10]}")
                    preset_data[preset_listbox.size() - 1] = (preset_name, preset_path, data)
            except:
                pass
        
        def load_selected():
            selection = preset_listbox.curselection()
            if not selection:
                messagebox.showwarning("Warning", "Please select a preset", parent=dialog)
                return
            
            preset_name, preset_path, data = preset_data[selection[0]]
            jobs = data.get('jobs', [])

            current_profile = self.profile_combo.get()

            current_profile_jobs = [
                job
                for job in self.saved_jobs
                if job.get("profile") == current_profile
            ]

            result = messagebox.askyesno(
                "Confirm Load",
                f"Load preset '{preset_name}'?\n\n"
                f"This will replace current "
                f"{len(current_profile_jobs)} jobs "
                f"with {len(jobs)} jobs from preset.",
                parent=dialog
            )
            if result:

                current_profile = self.profile_combo.get()
                

                # ลบเฉพาะ Job ของ Profile ปัจจุบัน
                self.saved_jobs = [
                    job
                    for job in self.saved_jobs
                    if job.get("profile") != current_profile
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
                
                messagebox.showinfo("Success", f"Preset '{preset_name}' loaded!\n\n{len(jobs)} jobs restored", parent=dialog)
                dialog.destroy()
        
        button_frame = tk.Frame(content, bg='#ffffff')
        button_frame.pack(
            pady=(15, 15)
        )
        
        tk.Button(button_frame, text="📂 Load", command=load_selected,
                 bg='#3498db', fg='white', font=('Arial', 10, 'bold'),
                 padx=20, pady=6).pack(side='left', padx=5)
        
        cancel_btn = tk.Button(
                button_frame,
                text="✖ Cancel",
                width=12,
                height=2,
                bg="#95a5a6",
                fg="white",
                font=("Arial", 10, "bold"),
                command=dialog.destroy
            )

        cancel_btn.pack(
            side="left",
            padx=5
        )
    
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
        if self.password_visible:
            self.db_password.config(show="*")
            self.toggle_password_btn.config(text="👁️", bg='#ecf0f1', fg='#2c3e50')
            self.password_visible = False
        else:
            self.db_password.config(show="")
            self.toggle_password_btn.config(text="🙈", bg='#f39c12', fg='#2c3e50')
            self.password_visible = True
    
    def on_db_type_change(self, event):
        """Update default port when database type changes"""
        db_type = self.db_type.get()
        port_defaults = {
            'PostgreSQL': '5432',
            'MySQL': '3306',
            'Microsoft SQL Server': '1433',
            'Oracle': '1521'
        }
        self.db_port.delete(0, tk.END)
        self.db_port.insert(0, port_defaults.get(db_type, '5432'))

    def load_table_data_dialog(self):
        """ENHANCED: Load table data with smart auto-sync and templates"""
        try:
            # Check if table data file exists
            if not os.path.exists(self.table_data_file):
                messagebox.showinfo("No Table Data",
                                   "No table data found from Mail Notify Tool.\n\n"
                                   "Please:\n"
                                   "1. Select tables in Mail Notify Tool\n"
                                   "2. Click 'Run SQL Scripts' button\n"
                                   "3. Table data will be automatically exported")
                return
            
            # ==================================================
            # FORCE CLEAR OLD CACHE
            # ==================================================

            self.loaded_table_data = None

            if hasattr(self, "saved_table_mappings"):
                self.saved_table_mappings = dict(self.saved_table_mappings)

            # Force reload latest file
            with open(self.table_data_file, 'r', encoding='utf-8') as f:
                self.loaded_table_data = json.load(f)

            # Update file timestamp
            self.last_table_data_mtime = os.path.getmtime(self.table_data_file)
            
            tables = self.loaded_table_data.get('tables', {})
            
            if not tables:
                messagebox.showinfo("No Tables",
                                   "No tables found in exported data.\n\n"
                                   "Please select tables in Mail Notify Tool first.")
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
        content_frame = tk.Frame(dialog, bg='#ffffff', relief='solid', bd=1)
        content_frame.pack(fill='both', expand=True, padx=15, pady=15)
        
        # Title with status indicator
        title_frame = tk.Frame(content_frame, bg='#ffffff')
        title_frame.pack(fill='both', pady=(10, 15))
        
        tk.Label(title_frame, text="📊 Smart Table Data Manager",
                font=('Arial', 14, 'bold'), bg='#ffffff', fg='#2c3e50').pack(side='left')
        
        # Auto-sync status indicator
        self.sync_status_label = tk.Label(title_frame, text="🔴 Auto-sync OFF",
                                         font=('Arial', 9, 'bold'), bg='#ffffff', fg='#e74c3c')
        self.sync_status_label.pack(side='right', padx=10)
        
        # Info section with file monitoring
        info_frame = tk.Frame(content_frame, bg='#e8f4f8', relief='solid', bd=1)
        info_frame.pack(fill='both', pady=(0, 10))
        
        phase = self.loaded_table_data.get('phase', 'N/A')
        timestamp = self.loaded_table_data.get('timestamp', 'N/A')
        
        info_text = f"📋 Phase: {phase} | 🕒 Exported: {timestamp} | 📊 Tables: {len(tables)}"
        
        tk.Label(info_frame, text=info_text, font=('Arial', 10),
                bg='#e8f4f8', fg='#2c3e50').pack(pady=8, padx=10)
        
        # NEW: Quick Actions Bar
        quick_actions = tk.Frame(content_frame, bg='#f8f9fa', relief='solid', bd=1)
        quick_actions.pack(fill='both', pady=(0, 10))
        
        tk.Label(quick_actions, text="⚡ Quick Actions:", font=('Arial', 10, 'bold'),
                bg='#f8f9fa', fg='#2c3e50').pack(side='left', padx=10, pady=8)
        tk.Button(
                quick_actions,
                text="🔄 Reload Latest Data",
                command=self.load_table_data_dialog,
                bg='#e67e22',
                fg='white',
                font=('Arial', 9, 'bold'),
                relief='flat',
                padx=12,
                pady=4
            ).pack(side='left', padx=2)
        
        tk.Button(quick_actions, text="🔄 Enable Auto-Sync",
                 command=lambda: self.toggle_auto_sync(True),
                 bg='#27ae60', fg='white', font=('Arial', 9, 'bold'),
                 relief='flat', padx=12, pady=4).pack(side='left', padx=2)
        
        tk.Button(quick_actions, text="💾 Save as Template",
                 command=lambda: self.save_query_template_dialog(),
                 bg='#3498db', fg='white', font=('Arial', 9, 'bold'),
                 relief='flat', padx=12, pady=4).pack(side='left', padx=2)
        
        tk.Button(quick_actions, text="📋 Load Template",
                 command=lambda: self.load_query_template_dialog(tables),
                 bg='#9b59b6', fg='white', font=('Arial', 9, 'bold'),
                 relief='flat', padx=12, pady=4).pack(side='left', padx=2)
        
        tk.Button(quick_actions, text="🎯 Smart Map All",
                 command=lambda: self.smart_map_all_tables(tables),
                 bg='#e67e22', fg='white', font=('Arial', 9, 'bold'),
                 relief='flat', padx=12, pady=4).pack(side='left', padx=2)
        
        # Main content - Enhanced 3-column layout
        main_content = tk.Frame(content_frame, bg='#ffffff')
        main_content.pack(fill='both', expand=True, pady=(0, 10))
        
        # LEFT: Table Selection (30%)
        left_frame = tk.Frame(main_content, bg='#ffffff', width=300)
        left_frame.pack(side='left', fill='both', expand=False, padx=(10, 5))
        left_frame.pack_propagate(False)
        
        table_frame = tk.LabelFrame(left_frame, text="① Select Table",
                                   font=('Arial', 11, 'bold'), bg='#ffffff', fg='#27ae60',
                                   relief='groove', bd=2)
        table_frame.pack(fill='both', expand=True)
        
        # Table list with icons
        table_list_frame = tk.Frame(table_frame, bg='#ffffff')
        table_list_frame.pack(fill='both', expand=True, padx=10, pady=10)
        
        table_scrollbar = tk.Scrollbar(table_list_frame)
        table_scrollbar.pack(side='right', fill='y')
        
        table_listbox = tk.Listbox(table_list_frame,
                                  yscrollcommand=table_scrollbar.set,
                                  font=('Arial', 10),
                                  selectmode=tk.SINGLE,
                                  exportselection=False,
                                  bg='white',
                                  selectbackground='#3498db',
                                  selectforeground='white')
        table_listbox.pack(side='left', fill='both', expand=True)
        table_scrollbar.config(command=table_listbox.yview)
        
        table_names = list(tables.keys())
        for table_name in table_names:
            table_info = tables[table_name]
            # Add indicator if table has saved mapping
            has_mapping = table_name in self.saved_table_mappings
            icon = "📌" if has_mapping else "📊"
            table_listbox.insert('end', f"{icon} {table_name} ({table_info['columns']} cols)")
        
        # MIDDLE: Column Selection with Multi-Select (35%)
        middle_frame = tk.Frame(main_content, bg='#ffffff', width=350)
        middle_frame.pack(side='left', fill='both', expand=False, padx=5)
        middle_frame.pack_propagate(False)
        
        column_frame = tk.LabelFrame(middle_frame, text="② Select Columns",
                                    font=('Arial', 11, 'bold'), bg='#ffffff', fg='#3498db',
                                    relief='groove', bd=2)
        column_frame.pack(fill='both', expand=True)
        
        # Column controls
        column_control_frame = tk.Frame(column_frame, bg='#ffffff')
        column_control_frame.pack(fill='both', padx=10, pady=(10, 5))
        
        tk.Label(column_control_frame, text="💡 Ctrl+Click for multiple",
                font=('Arial', 8, 'italic'), bg='#ffffff', fg='#7f8c8d').pack(side='left')
        
        def select_all_columns():
            column_listbox.select_set(0, tk.END)
            update_preview()
        
        def clear_all_columns():
            column_listbox.selection_clear(0, tk.END)
            update_preview()
        
        tk.Button(column_control_frame, text="✅ All", command=select_all_columns,
                 bg='#27ae60', fg='white', font=('Arial', 7, 'bold'),
                 padx=6, pady=2).pack(side='right', padx=(2, 0))
        
        tk.Button(column_control_frame, text="❌ Clear", command=clear_all_columns,
                 bg='#e74c3c', fg='white', font=('Arial', 7, 'bold'),
                 padx=6, pady=2).pack(side='right')
        
        column_list_frame = tk.Frame(column_frame, bg='#ffffff')
        column_list_frame.pack(fill='both', expand=True, padx=10, pady=(0, 10))
        
        column_scrollbar = tk.Scrollbar(column_list_frame)
        column_scrollbar.pack(side='right', fill='y')
        
        column_listbox = tk.Listbox(column_list_frame,
                                    yscrollcommand=column_scrollbar.set,
                                    font=('Arial', 10),
                                    selectmode=tk.EXTENDED,
                                    exportselection=False,
                                    bg='white',
                                    selectbackground='#3498db',
                                    selectforeground='white')
        column_listbox.pack(side='left', fill='both', expand=True)
        column_scrollbar.config(command=column_listbox.yview)
        
        # RIGHT: Options & Preview (35%)
        right_frame = tk.Frame(main_content, bg='#ffffff')
        right_frame.pack(side='right', fill='both', expand=True, padx=(5, 10))
        
        # Insert Mode
        mode_frame = tk.LabelFrame(right_frame, text="③ Insert Mode",
                                  font=('Arial', 11, 'bold'), bg='#ffffff', fg='#9b59b6',
                                  relief='groove', bd=2)
        mode_frame.pack(fill='both', pady=(0, 8))
        
        insert_mode_var = tk.StringVar(value="raw")
        
        mode_inner = tk.Frame(mode_frame, bg='#ffffff')
        mode_inner.pack(fill='both', padx=10, pady=8)
        
        tk.Radiobutton(mode_inner,
                       text="📝 Raw Data (direct insert)",
                       variable=insert_mode_var,
                       value="raw",
                       font=('Arial', 9),
                       bg='#ffffff',
                       command=lambda: update_preview()).pack(anchor='w', pady=2)
        
        tk.Radiobutton(mode_inner,
                       text="🔤 Variable (for templates)",
                       variable=insert_mode_var,
                       value="variable",
                       font=('Arial', 9),
                       bg='#ffffff',
                       command=lambda: update_preview()).pack(anchor='w', pady=2)
        
        # NEW: Auto-Sync Settings
        sync_frame = tk.LabelFrame(right_frame, text="🔄 Auto-Sync Settings",
                                  font=('Arial', 11, 'bold'), bg='#ffffff', fg='#e67e22')
        sync_frame.pack(fill='both', pady=(0, 8))
        
        sync_inner = tk.Frame(sync_frame, bg='#ffffff')
        sync_inner.pack(fill='both', padx=10, pady=8)
        
        sync_enabled = tk.Checkbutton(sync_inner,
                                      text="Enable auto-sync when file changes",
                                      variable=self.auto_sync_enabled,
                                      font=('Arial', 9),
                                      bg='#ffffff',
                                      command=lambda: self.toggle_auto_sync(self.auto_sync_enabled.get()))
        sync_enabled.pack(anchor='w', pady=2)
        
        interval_frame = tk.Frame(sync_inner, bg='#ffffff')
        interval_frame.pack(fill='both', pady=(5, 0))
        
        tk.Label(interval_frame, text="Check interval:",
                font=('Arial', 9), bg='#ffffff').pack(side='left')
        
        interval_var = tk.StringVar(value="300")
        interval_entry = tk.Entry(interval_frame, textvariable=interval_var,
                                 width=5, font=('Arial', 9))
        interval_entry.pack(side='left', padx=5)
        
        tk.Label(interval_frame, text="seconds",
                font=('Arial', 9), bg='#ffffff').pack(side='left')
        
        def update_sync_interval():
            try:
                self.sync_interval_seconds = int(interval_var.get())
                if self.auto_sync_enabled.get():
                    self.schedule_next_sync_check()
            except:
                pass
        
        tk.Button(interval_frame, text="✓", command=update_sync_interval,
                 bg='#27ae60', fg='white', font=('Arial', 8, 'bold'),
                 padx=4, pady=1).pack(side='left', padx=2)
        
        # Preview
        preview_frame = tk.LabelFrame(right_frame, text="👁️ Preview",
                                     font=('Arial', 11, 'bold'), bg='#ffffff', fg='#e67e22')
        preview_frame.pack(fill='both', expand=True)
        
        preview_text_frame = tk.Frame(preview_frame, bg='#ffffff')
        preview_text_frame.pack(fill='both', expand=True, padx=10, pady=10)
        
        preview_scrollbar = tk.Scrollbar(preview_text_frame)
        preview_scrollbar.pack(side='right', fill='y')
        
        preview_text = tk.Text(preview_text_frame, height=15, font=('Courier', 8),
                              bg='#f8f9fa', state='disabled', wrap=tk.WORD,
                              yscrollcommand=preview_scrollbar.set)
        preview_text.pack(side='left', fill='both', expand=True)
        preview_scrollbar.config(command=preview_text.yview)
        
        # Update preview function
        def update_preview(event=None):
            table_selection = table_listbox.curselection()
            column_selections = column_listbox.curselection()
            
            preview_text.configure(state='normal')
            preview_text.delete(1.0, tk.END)
            
            if not table_selection:
                preview_text.insert(tk.END, "Select a table first")
                preview_text.configure(state='disabled')
                return
            
            selected_table = table_names[table_selection[0]]
            table_data = tables[selected_table]
            column_data_dict = table_data.get('column_data', {})
            
            if not column_selections:
                preview_text.insert(tk.END, f"Table: {selected_table}\n")
                preview_text.insert(tk.END, f"{'='*50}\n\n")
                preview_text.insert(tk.END, f"Columns ({len(column_data_dict)}):\n\n")
                for col_name in column_data_dict.keys():
                    preview_text.insert(tk.END, f"  • {col_name}\n")
                preview_text.insert(tk.END, "\n💡 Select columns to preview")
                preview_text.configure(state='disabled')
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
            
            preview_text.configure(state='disabled')
        
        # Table selection handler
        def on_table_select(event):
            column_listbox.delete(0, tk.END)
            
            table_selection = table_listbox.curselection()
            if not table_selection:
                return
            
            selected_table = table_names[table_selection[0]]
            table_data = tables[selected_table]
            column_data_dict = table_data.get('column_data', {})
            
            # Populate columns with mapping indicators
            for col_name in column_data_dict.keys():
                col_values = column_data_dict[col_name]
                # Check if this column has saved mapping
                has_mapping = (selected_table in self.saved_table_mappings and 
                              col_name in self.saved_table_mappings[selected_table])
                icon = "📌" if has_mapping else "📋"
                column_listbox.insert('end', f"{icon} {col_name} ({len(col_values)} vals)")
            
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
        table_listbox.bind('<<ListboxSelect>>', on_table_select)
        column_listbox.bind('<<ListboxSelect>>', update_preview)
        table_listbox.bind('<ButtonRelease-1>', on_table_select)
        column_listbox.bind('<ButtonRelease-1>', update_preview)
        insert_mode_var.trace_add('write', lambda *args: update_preview())
        
        # Auto-select first table
        if table_names:
            table_listbox.selection_set(0)
            table_listbox.event_generate('<<ListboxSelect>>')
            on_table_select(None)
        
        # Action Buttons
        button_frame = tk.Frame(content_frame, bg='#ffffff')
        button_frame.pack(fill='both', pady=(0, 10))
        
        def insert_and_save_mapping():
            table_selection = table_listbox.curselection()
            column_selections = column_listbox.curselection()
            
            if not table_selection or not column_selections:
                messagebox.showwarning("No Selection",
                                     "Please select table and column(s)", parent=dialog)
                return
            
            selected_table = table_names[table_selection[0]]
            table_data = tables[selected_table]
            column_data_dict = table_data.get('column_data', {})
            
            column_names = list(column_data_dict.keys())
            selected_columns = [column_names[i] for i in column_selections]
            
            insert_mode = insert_mode_var.get()
            cursor_pos = self.sql_context.index(tk.INSERT)
            
            inserted_items = []
            
            for col_name in selected_columns:
                column_values = column_data_dict[col_name]
                
                if insert_mode == "variable":
                    safe_table = selected_table.upper().replace(' ', '_').replace('-', '_')
                    safe_col = col_name.upper().replace(' ', '_').replace('-', '_')
                    variable_name = f"{{TABLE_{safe_table}_{safe_col}}}"
                    
                    self.sql_context.insert(cursor_pos, variable_name + " ")
                    inserted_items.append(f"Variable: {variable_name}")
                else:
                    formatted_vals = [f"'{v}'" if isinstance(v, str) else str(v)
                                      for v in column_values]
                    # Normalize column name: strip spaces for SQL matching
                    col_lower = col_name.lower().replace(' ', '')
                    if len(formatted_vals) == 1:
                        new_expr = f"{col_lower} = {formatted_vals[0]}"
                    else:
                        vals_joined = ', '.join(formatted_vals)
                        new_expr = f"{col_lower} in ({vals_joined})"
                    
                    # Smart replace: update existing condition, or append after bare column name
                    import re as _re
                    current_sql = self.sql_context.get(1.0, tk.END).rstrip('\n')
                    col_esc = _re.escape(col_lower)

                    # Case 1: column already has IN(...) or = value → replace the full condition
                    pattern_with_cond = _re.compile(
                        rf'({col_esc})\s*(?:in\s*\([^)]*\)|=\s*(?:\'[^\']*\'|"[^"]*"|\S+))',
                        _re.IGNORECASE
                    )
                    # Case 2: column exists at end of string or followed only by whitespace/EOL → append condition
                    pattern_bare = _re.compile(
                        rf'({col_esc})\s*$',
                        _re.IGNORECASE | _re.MULTILINE
                    )

                    if pattern_with_cond.search(current_sql):
                        new_sql = pattern_with_cond.sub(new_expr, current_sql, count=1)
                        self.sql_context.delete(1.0, tk.END)
                        self.sql_context.insert(1.0, new_sql)
                        inserted_items.append(f"Updated: {new_expr[:100]}")
                    elif pattern_bare.search(current_sql):
                        if len(formatted_vals) == 1:
                            replacement = rf'\1 = {formatted_vals[0]}'
                        else:
                            vals_joined2 = ', '.join(formatted_vals)
                            replacement = rf'\1 in ({vals_joined2})'
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
        
        tk.Button(button_frame, text="📝 Insert & Save Mapping",
                 command=insert_and_save_mapping,
                 bg='#27ae60', fg='white', font=('Arial', 10, 'bold'),
                 padx=20, pady=6).pack(side='left')
        
        cancel_btn = tk.Button(
                button_frame,
                text="✖ Cancel",
                width=12,
                height=2,
                bg="#95a5a6",
                fg="white",
                font=("Arial", 10, "bold"),
                command=dialog.destroy
            )

        cancel_btn.pack(
            side="left",
            padx=5
        )
    # NEW: Auto-sync methods
    
    def toggle_auto_sync(self, enabled):
        """Toggle auto-sync on/off"""
        if enabled:
            self.auto_sync_enabled.set(True)
            self.sync_status_label.config(text="🟢 Auto-sync ON", fg='#27ae60')
            self.schedule_next_sync_check()
            self.results_text.insert(tk.END, "🔄 Auto-sync enabled\n")
            self.results_text.insert(tk.END, f"   Checking every {self.sync_interval_seconds}s\n\n")
        else:
            self.auto_sync_enabled.set(False)
            self.sync_status_label.config(text="🔴 Auto-sync OFF", fg='#e74c3c')
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
                self.check_and_sync_table_data
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
                with open(self.table_data_file, 'r', encoding='utf-8') as f:
                    self.loaded_table_data = json.load(f)
                
                # Auto-replace variables in current query
                updated_count = self.auto_replace_table_variables()
                
                if updated_count > 0:
                    self.results_text.insert(tk.END, f"🔄 Auto-sync triggered!\n")
                    self.results_text.insert(tk.END, f"   Updated {updated_count} variable(s)\n")
                    self.results_text.insert(tk.END, f"   Time: {pd.Timestamp.now().strftime('%H:%M:%S')}\n\n")
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
            
            tables = self.loaded_table_data.get('tables', {})
            sql_query = self.sql_context.get(1.0, tk.END)
            
            import re
            updated_count = 0
            
            # Find all {TABLE_*} variables
            pattern = r'\{TABLE_([A-Z0-9_]+)_([A-Z0-9_]+)\}'
            matches = re.findall(pattern, sql_query)
            
            for table_part, column_part in matches:
                # Find matching table and column
                for table_name, table_data in tables.items():
                    safe_table = table_name.upper().replace(' ', '_').replace('-', '_')
                    
                    if safe_table == table_part:
                        column_data_dict = table_data.get('column_data', {})
                        
                        for col_name, col_values in column_data_dict.items():
                            safe_col = col_name.upper().replace(' ', '_').replace('-', '_')
                            
                            if safe_col == column_part:
                                # Found match - replace variable
                                old_var = f"{{TABLE_{table_part}_{column_part}}}"
                                new_values = ', '.join([f"'{v}'" if isinstance(v, str) else str(v) 
                                                       for v in col_values])
                                
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
            mappings_file = os.path.join(os.path.dirname(self.config_file), 'table_mappings.json')
            with open(mappings_file, 'w', encoding='utf-8') as f:
                json.dump(self.saved_table_mappings, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Failed to save mappings: {e}")
    
    def load_table_mappings(self):
        """Load saved table mappings"""
        try:
            mappings_file = os.path.join(os.path.dirname(self.config_file), 'table_mappings.json')
            if os.path.exists(mappings_file):
                with open(mappings_file, 'r', encoding='utf-8') as f:
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
            messagebox.showinfo("No Mappings",
                               "No saved mappings found.\n\n"
                               "Select and save columns first to use Smart Map.")
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
        
        content = tk.Frame(dialog, bg='#ffffff', relief='solid', bd=1)
        content.pack(fill='both', expand=True, padx=15, pady=15)
        
        tk.Label(content, text="💾 Save Query Template",
                font=('Arial', 12, 'bold'), bg='#ffffff').pack(pady=(10, 15))
        
        tk.Label(content, text="Template Name:",
                font=('Arial', 10), bg='#ffffff').pack(anchor='w', padx=10, pady=(0, 5))
        
        name_entry = tk.Entry(content, font=('Arial', 10), width=50)
        name_entry.pack(padx=10, pady=(0, 10))
        name_entry.focus()
        
        tk.Label(content, text=f"Query: {sql_query[:100]}{'...' if len(sql_query) > 100 else ''}",
                font=('Arial', 8), bg='#ffffff', fg='#7f8c8d').pack(padx=10)
        
        def save():
            template_name = name_entry.get().strip()
            if not template_name:
                messagebox.showwarning("No Name", "Enter template name", parent=dialog)
                return
            
            self.query_templates[template_name] = {
                'query': sql_query,
                'created': pd.Timestamp.now().isoformat()
            }
            
            # Save to file
            templates_file = os.path.join(os.path.dirname(self.config_file), 'query_templates.json')
            try:
                with open(templates_file, 'w', encoding='utf-8') as f:
                    json.dump(self.query_templates, f, indent=2, ensure_ascii=False)
                
                messagebox.showinfo("Success", f"Template '{template_name}' saved!", parent=dialog)
                dialog.destroy()
            except Exception as e:
                messagebox.showerror("Error", f"Failed to save:\n{e}", parent=dialog)
        
        button_frame = tk.Frame(content, bg='#ffffff')
        button_frame.pack(
            pady=(15, 15)
        )
        
        save_btn = tk.Button(
            button_frame,
            text="💾 Save",
            width=12,
            height=2,
            bg="#27ae60",
            fg="white",
            font=("Arial", 10, "bold"),
            command=save
        )

        save_btn.pack(
            side="left",
            padx=5
        )
        
        cancel_btn = tk.Button(
                button_frame,
                text="✖ Cancel",
                width=12,
                height=2,
                bg="#95a5a6",
                fg="white",
                font=("Arial", 10, "bold"),
                command=dialog.destroy
            )

        cancel_btn.pack(
            side="left",
            padx=5
        )
    
    def load_query_template_dialog(self, tables):
        """Load saved query template"""
        templates_file = os.path.join(os.path.dirname(self.config_file), 'query_templates.json')
        
        try:
            if os.path.exists(templates_file):
                with open(templates_file, 'r', encoding='utf-8') as f:
                    self.query_templates = json.load(f)
        except:
            pass
        
        if not self.query_templates:
            messagebox.showinfo("No Templates", "No saved templates found")
            return
        
        dialog = self._create_centered_dialog("📋 Load Query Template", 600, 400)
        
        content = tk.Frame(dialog, bg='#ffffff', relief='solid', bd=1)
        content.pack(fill='both', expand=True, padx=15, pady=15)
        
        tk.Label(content, text="📋 Select Template",
                font=('Arial', 12, 'bold'), bg='#ffffff').pack(pady=(10, 15))
        
        list_frame = tk.Frame(content, bg='#ffffff')
        list_frame.pack(fill='both', expand=True, pady=(0, 15))
        
        scrollbar = tk.Scrollbar(list_frame)
        scrollbar.pack(side='right', fill='y')
        
        template_listbox = tk.Listbox(list_frame, font=('Arial', 10),
                                      yscrollcommand=scrollbar.set)
        template_listbox.pack(side='left', fill='both', expand=True)
        scrollbar.config(command=template_listbox.yview)
        
        for template_name in self.query_templates.keys():
            template_listbox.insert('end', f"📄 {template_name}")
        
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
            self.sql_context.insert(1.0, template_data['query'])
            
            self.results_text.insert(tk.END, f"📋 Loaded template: {selected_name}\n\n")
            self.results_text.see(tk.END)
            
            messagebox.showinfo("Success", f"Template '{selected_name}' loaded!", parent=dialog)
            dialog.destroy()
        
        button_frame = tk.Frame(content, bg='#ffffff')
        button_frame.pack(
            pady=(15, 15)
        )
        
        tk.Button(button_frame, text="📋 Load", command=load_selected,
                 bg='#3498db', fg='white', font=('Arial', 10, 'bold'),
                 padx=20, pady=6).pack(side='left', padx=5)
        
        cancel_btn = tk.Button(
                button_frame,
                text="✖ Cancel",
                width=12,
                height=2,
                bg="#95a5a6",
                fg="white",
                font=("Arial", 10, "bold"),
                command=dialog.destroy
            )

        cancel_btn.pack(
            side="left",
            padx=5
        )
    
    def _create_loading_dialog_with_retry(self, sql_query):
        """NEW: Create loading dialog with retry capability"""
        loading_dialog = tk.Toplevel(self.root)
        loading_dialog.title("Executing Query...")
        loading_dialog.geometry("400x250")
        loading_dialog.configure(bg='#f0f0f0')
        loading_dialog.transient(self.root)
        loading_dialog.grab_set()
        
        # Center dialog
        loading_dialog.update_idletasks()
        x = (loading_dialog.winfo_screenwidth() // 2) - (loading_dialog.winfo_width() // 2)
        y = (loading_dialog.winfo_screenheight() // 2) - (loading_dialog.winfo_height() // 2)
        loading_dialog.geometry(f"+{x}+{y}")
        
        # Content frame
        content_frame = tk.Frame(loading_dialog, bg='#ffffff', relief='solid', bd=1)
        content_frame.pack(fill='both', expand=True, padx=15, pady=15)
        
        # Status label
        status_label = tk.Label(content_frame, text="⏳ Executing query...",
                               font=('Arial', 11, 'bold'), bg='#ffffff', fg='#2c3e50')
        status_label.pack(pady=(10, 5))
        
        # Progress bar
        progress = ttk.Progressbar(content_frame, mode='indeterminate', length=300)
        progress.pack(pady=10)
        progress.start(10)
        
        # Details label
        details_label = tk.Label(content_frame, text="Please wait...",
                                font=('Arial', 9), bg='#ffffff', fg='#7f8c8d')
        details_label.pack(pady=5)
        
        # Button frame (initially hidden)
        button_frame = tk.Frame(content_frame, bg='#ffffff')
        
        # Store references
        loading_dialog.status_label = status_label
        loading_dialog.details_label = details_label
        loading_dialog.progress = progress
        loading_dialog.button_frame = button_frame
        loading_dialog.sql_query = sql_query
        
        # Reset execute button if user closes loading dialog via X
        def _on_loading_close():
            loading_dialog.destroy()
            self.execute_btn.config(state="normal", text="▶️ Execute Query")

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
                    df = pd.read_sql_query(sql_query, self.engine)
                    
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
                    self.root.after(0, lambda: self.on_modification_success(rows_affected, sql_query, loading_dialog))
                
            except Exception as e:
                # Comprehensive error logging
                error_type = type(e).__name__
                error_message = str(e)
                error_traceback = traceback.format_exc()
                
                # Store error details for retry
                error_details = {
                    'type': error_type,
                    'message': error_message,
                    'traceback': error_traceback,
                    'query': sql_query
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
                self.root.after(0, lambda: self.on_query_error_enhanced(error_details, loading_dialog))
        
        # Start background thread
        thread = threading.Thread(target=execute_in_background, daemon=True)
        thread.start()
    
    def on_query_error_enhanced(self, error_details, loading_dialog):
        """NEW: Enhanced error handling with detailed debugging and retry option"""
        try:
            # Update loading dialog to show error
            loading_dialog.progress.stop()
            loading_dialog.status_label.config(text="❌ Query Failed", fg='#e74c3c')
            loading_dialog.details_label.config(text="Click 'Show Details' for error information")
            
            # Reset execute button immediately — don't wait for user to click Close
            self.execute_btn.config(state="normal", text="▶️ Execute Query")
            
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
            tk.Button(loading_dialog.button_frame, text="🔄 Retry", command=retry_query,
                     bg='#f39c12', fg='white', font=('Arial', 9, 'bold'),
                     padx=15, pady=5).pack(side='left', padx=5)
            
            tk.Button(loading_dialog.button_frame, text="📋 Show Details", command=show_error_details,
                     bg='#3498db', fg='white', font=('Arial', 9, 'bold'),
                     padx=15, pady=5).pack(side='left', padx=5)
            
            tk.Button(loading_dialog.button_frame, text="❌ Close", command=close_dialog,
                     bg='#95a5a6', fg='white', font=('Arial', 9, 'bold'),
                     padx=15, pady=5).pack(side='left', padx=5)
            
            # Update results text with error
            self.results_text.delete("1.0", tk.END)
            self.results_text.insert(tk.END, "❌ QUERY ERROR\n")
            self.results_text.insert(tk.END, "=" * 150 + "\n\n")
            self.results_text.insert(tk.END, f"Error Type: {error_details['type']}\n")
            self.results_text.insert(tk.END, f"Error Message: {error_details['message']}\n\n")
            
            if self.debug_mode.get():
                self.results_text.insert(tk.END, "Debug Traceback:\n")
                self.results_text.insert(tk.END, "-" * 150 + "\n")
                self.results_text.insert(tk.END, error_details['traceback'])
                self.results_text.insert(tk.END, "\n" + "=" * 150 + "\n")
            
            self.results_text.see(tk.END)
            
        except Exception as e:
            print(f"Error in error handler: {e}")
            traceback.print_exc()
            loading_dialog.destroy()
            self.execute_btn.config(state="normal", text="▶️ Execute Query")
    
    def _show_error_details_dialog(self, error_details):
        """NEW: Show comprehensive error details dialog"""
        dialog = tk.Toplevel(self.root)
        dialog.title("🐛 Error Details")
        dialog.geometry("900x700")
        dialog.configure(bg='#f0f0f0')
        dialog.transient(self.root)
        dialog.grab_set()
        
        # Content frame
        content_frame = tk.Frame(dialog, bg='#ffffff', relief='solid', bd=1)
        content_frame.pack(fill='both', expand=True, padx=15, pady=15)
        
        # Title
        tk.Label(content_frame, text="🐛 Query Execution Error Details",
                font=('Arial', 14, 'bold'), bg='#ffffff', fg='#e74c3c').pack(pady=(10, 15))
        
        # Error summary
        summary_frame = tk.LabelFrame(content_frame, text="Error Summary",
                                     font=('Arial', 11, 'bold'), bg='#ffffff', fg='#2c3e50')
        summary_frame.pack(fill='both', padx=10, pady=(0, 10))
        
        tk.Label(summary_frame, text=f"Type: {error_details['type']}",
                font=('Arial', 10), bg='#ffffff', fg='#2c3e50',
                anchor='w').pack(fill='both', padx=10, pady=5)
        
        tk.Label(summary_frame, text=f"Message: {error_details['message']}",
                font=('Arial', 10), bg='#ffffff', fg='#e74c3c',
                anchor='w', wraplength=850).pack(fill='both', padx=10, pady=5)
        
        # Query that failed
        query_frame = tk.LabelFrame(content_frame, text="Failed Query",
                                   font=('Arial', 11, 'bold'), bg='#ffffff', fg='#2c3e50')
        query_frame.pack(fill='both', padx=10, pady=(0, 10))
        
        query_text = tk.Text(query_frame, height=4, font=('Courier', 9),
                            bg='#f8f9fa', wrap=tk.WORD)
        query_text.pack(fill='both', padx=10, pady=10)
        query_text.insert(1.0, error_details['query'])
        query_text.config(state='disabled')
        
        # Full traceback
        traceback_frame = tk.LabelFrame(content_frame, text="Full Traceback (for debugging)",
                                       font=('Arial', 11, 'bold'), bg='#ffffff', fg='#e67e22')
        traceback_frame.pack(fill='both', expand=True, padx=10, pady=(0, 10))
        
        traceback_scroll = tk.Scrollbar(traceback_frame)
        traceback_scroll.pack(side='right', fill='y')
        
        traceback_text = tk.Text(traceback_frame, font=('Courier', 8),
                                bg='#f8f9fa', wrap=tk.WORD,
                                yscrollcommand=traceback_scroll.set)
        traceback_text.pack(side='left', fill='both', expand=True, padx=10, pady=10)
        traceback_scroll.config(command=traceback_text.yview)
        
        traceback_text.insert(1.0, error_details['traceback'])
        traceback_text.config(state='disabled')
        
        # Buttons
        button_frame = tk.Frame(content_frame, bg='#ffffff')
        button_frame.pack(fill='both', padx=10, pady=(0, 10))
        
        def copy_error():
            error_report = f"Error Type: {error_details['type']}\n"
            error_report += f"Error Message: {error_details['message']}\n\n"
            error_report += f"Query:\n{error_details['query']}\n\n"
            error_report += f"Traceback:\n{error_details['traceback']}"
            
            self.root.clipboard_clear()
            self.root.clipboard_append(error_report)
            messagebox.showinfo("Copied", "Error details copied to clipboard!", parent=dialog)
        
        tk.Button(button_frame, text="📋 Copy Error Details", command=copy_error,
                 bg='#3498db', fg='white', font=('Arial', 10, 'bold'),
                 padx=20, pady=6).pack(side='left')
        
        tk.Button(button_frame, text="❌ Close", command=dialog.destroy,
                 bg='#95a5a6', fg='white', font=('Arial', 10, 'bold'),
                 padx=20, pady=6).pack(side='right')
    
    # UPDATED: Enhanced table data selection dialog with multiple columns and raw data option
    def show_table_data_selection_dialog(self, tables):
        """Show dialog to select table and column(s) for data extraction - ENHANCED: Multiple columns + raw data"""
        dialog = tk.Toplevel(self.root)
        dialog.title("📊 Select Table Column Data")
        dialog.geometry("1100x800")
        dialog.configure(bg='#f0f0f0')
        dialog.transient(self.root)
        dialog.grab_set()
        
        # Center dialog
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - (dialog.winfo_width() // 2)
        y = (dialog.winfo_screenheight() // 2) - (dialog.winfo_height() // 2)
        dialog.geometry(f"+{x}+{y}")
        
        # Content frame
        content_frame = tk.Frame(dialog, bg='#ffffff', relief='solid', bd=1)
        content_frame.pack(fill='both', expand=True, padx=15, pady=15)
        
        # Title
        tk.Label(content_frame, text="📊 Select Table Column Data for SQL",
                font=('Arial', 14, 'bold'), bg='#ffffff', fg='#2c3e50').pack(pady=(10, 15))
        
        # Info section
        info_frame = tk.Frame(content_frame, bg='#e8f4f8', relief='solid', bd=1)
        info_frame.pack(fill='both', pady=(0, 15))
        
        phase = self.loaded_table_data.get('phase', 'N/A')
        timestamp = self.loaded_table_data.get('timestamp', 'N/A')
        
        info_text = f"📋 Phase: {phase} | 🕒 Exported: {timestamp} | 📊 Tables: {len(tables)}"
        
        tk.Label(info_frame, text=info_text, font=('Arial', 10),
                bg='#e8f4f8', fg='#2c3e50', justify='center').pack(pady=8, padx=10)
        
        # Main content - Split into left and right
        main_content = tk.Frame(content_frame, bg='#ffffff')
        main_content.pack(fill='both', expand=True, pady=(0, 15))
        
        # LEFT SIDE - Table and Column Selection
        left_frame = tk.Frame(main_content, bg='#ffffff')
        left_frame.pack(side='left', fill='both', expand=True, padx=(10, 5))
        
        # Table selection
        table_frame = tk.LabelFrame(left_frame, text="1️⃣ Select Table",
                                   font=('Arial', 11, 'bold'), bg='#ffffff', fg='#27ae60')
        table_frame.pack(fill='both', pady=(0, 10))
        
        table_list_frame = tk.Frame(table_frame, bg='#ffffff')
        table_list_frame.pack(fill='both', padx=10, pady=10)
        
        table_scrollbar = tk.Scrollbar(table_list_frame, orient="vertical")
        table_scrollbar.pack(side='right', fill='y')
        
        table_listbox = tk.Listbox(table_list_frame,
                                  yscrollcommand=table_scrollbar.set,
                                  font=('Arial', 10),
                                  height=6,
                                  selectmode=tk.SINGLE,
                                  exportselection=False,
                                  bg='white',
                                  selectbackground='#3498db',
                                  selectforeground='white',
                                  activestyle='dotbox')
        table_listbox.pack(side='left', fill='both', expand=True)
        table_scrollbar.config(command=table_listbox.yview)
        
        # Populate tables
        table_names = list(tables.keys())
        for table_name in table_names:
            table_info = tables[table_name]
            table_listbox.insert('end', f"{table_name} ({table_info['columns']} columns)")
        
        # Column selection with multiple selection
        column_frame = tk.LabelFrame(left_frame, text="2️⃣ Select Column(s)",
                                    font=('Arial', 11, 'bold'), bg='#ffffff', fg='#3498db')
        column_frame.pack(fill='both', expand=True, pady=(0, 10))
        
        # NEW: Multiple selection controls
        column_control_frame = tk.Frame(column_frame, bg='#ffffff')
        column_control_frame.pack(fill='both', padx=10, pady=(10, 5))
        
        tk.Label(column_control_frame, text="💡 Ctrl+Click for multiple columns",
                font=('Arial', 9, 'italic'), bg='#ffffff', fg='#7f8c8d').pack(side='left')
        
        def select_all_columns():
            column_listbox.select_set(0, tk.END)
            update_preview()
        
        def clear_all_columns():
            column_listbox.selection_clear(0, tk.END)
            update_preview()
        
        tk.Button(column_control_frame, text="✅ Select All", command=select_all_columns,
                 bg='#27ae60', fg='white', font=('Arial', 8, 'bold'),
                 padx=8, pady=2).pack(side='right', padx=(5, 0))
        
        tk.Button(column_control_frame, text="❌ Clear", command=clear_all_columns,
                 bg='#e74c3c', fg='white', font=('Arial', 8, 'bold'),
                 padx=8, pady=2).pack(side='right')
        
        column_list_frame = tk.Frame(column_frame, bg='#ffffff')
        column_list_frame.pack(fill='both', expand=True, padx=10, pady=(0, 10))
        
        column_scrollbar = tk.Scrollbar(column_list_frame, orient="vertical")
        column_scrollbar.pack(side='right', fill='y')
        
        # UPDATED: Multiple selection mode
        column_listbox = tk.Listbox(column_list_frame,
                                    yscrollcommand=column_scrollbar.set,
                                    font=('Arial', 10),
                                    height=8,
                                    selectmode=tk.EXTENDED,  # Changed to EXTENDED for multiple selection
                                    exportselection=False,
                                    bg='white',
                                    selectbackground='#3498db',
                                    selectforeground='white',
                                    activestyle='dotbox')
        column_listbox.pack(side='left', fill='both', expand=True)
        column_scrollbar.config(command=column_listbox.yview)
        
        # RIGHT SIDE - Preview and Options
        right_frame = tk.Frame(main_content, bg='#ffffff')
        right_frame.pack(side='right', fill='both', expand=True, padx=(5, 10))
        
        # NEW: Insert mode selection
        mode_frame = tk.LabelFrame(right_frame, text="⚙️ Insert Mode",
                                   font=('Arial', 11, 'bold'), bg='#ffffff', fg='#9b59b6')
        mode_frame.pack(fill='both', pady=(0, 10))
        
        insert_mode_var = tk.StringVar(value="variable")
        
        mode_options_frame = tk.Frame(mode_frame, bg='#ffffff')
        mode_options_frame.pack(fill='both', padx=10, pady=10)
        
        tk.Radiobutton(mode_options_frame,
                       text="🔤 As Variable (replaceable)",
                       variable=insert_mode_var,
                       value="variable",
                       font=('Arial', 9),
                       bg='#ffffff').pack(anchor='w', pady=2)
        
        tk.Radiobutton(mode_options_frame,
                       text="📝 As Raw Data (direct values)",
                       variable=insert_mode_var,
                       value="raw",
                       font=('Arial', 9),
                       bg='#ffffff').pack(anchor='w', pady=2)
        
        tk.Label(mode_frame, text="💡 Variable mode: Insert {TABLE_NAME_COLUMN}\n"
                                 "💡 Raw data mode: Insert actual values directly",
                font=('Arial', 8, 'italic'), bg='#ffffff', fg='#7f8c8d',
                justify='left').pack(anchor='w', padx=10, pady=(0, 10))
        
        # Preview
        preview_frame = tk.LabelFrame(right_frame, text="👁️ Data Preview",
                                     font=('Arial', 11, 'bold'), bg='#ffffff', fg='#e67e22')
        preview_frame.pack(fill='both', expand=True)
        
        preview_text_frame = tk.Frame(preview_frame, bg='#ffffff')
        preview_text_frame.pack(fill='both', expand=True, padx=10, pady=10)
        
        preview_scrollbar = tk.Scrollbar(preview_text_frame)
        preview_scrollbar.pack(side='right', fill='y')
        
        preview_text = tk.Text(preview_text_frame, height=20, font=('Courier', 9),
                              bg='#f8f9fa', state='disabled', wrap=tk.WORD,
                              yscrollcommand=preview_scrollbar.set)
        preview_text.pack(side='left', fill='both', expand=True)
        preview_scrollbar.config(command=preview_text.yview)
        
        # Update preview function
        def update_preview(event=None):
            table_selection = table_listbox.curselection()
            column_selections = column_listbox.curselection()
            
            if not table_selection:
                preview_text.configure(state='normal')
                preview_text.delete(1.0, tk.END)
                preview_text.insert(tk.END, "Please select a table first")
                preview_text.configure(state='disabled')
                return
            
            selected_table = table_names[table_selection[0]]
            table_data = tables[selected_table]
            column_data_dict = table_data.get('column_data', {})
            
            if not column_selections:
                preview_text.configure(state='normal')
                preview_text.delete(1.0, tk.END)
                preview_text.insert(tk.END, f"Table: {selected_table}\n")
                preview_text.insert(tk.END, f"{'='*60}\n\n")
                preview_text.insert(tk.END, f"Available Columns: {len(column_data_dict)}\n\n")
                for col_name in column_data_dict.keys():
                    preview_text.insert(tk.END, f"• {col_name}\n")
                preview_text.insert(tk.END, "\n💡 Select column(s) to see preview")
                preview_text.configure(state='disabled')
                return
            
            # Get selected columns
            column_names = list(column_data_dict.keys())
            selected_columns = [column_names[i] for i in column_selections]
            
            # Update preview
            preview_text.configure(state='normal')
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
                    safe_table_name = selected_table.upper().replace(' ', '_').replace('-', '_')
                    safe_col_name = col_name.upper().replace(' ', '_').replace('-', '_')
                    variable_name = f"{{TABLE_{safe_table_name}_{safe_col_name}}}"
                    preview_text.insert(tk.END, f"  Variable: {variable_name}\n")
                else:
                    values_str = ', '.join([f"'{v}'" if isinstance(v, str) else str(v) for v in column_values[:3]])
                    if len(column_values) > 3:
                        values_str += ", ..."
                    preview_text.insert(tk.END, f"  Raw data: {values_str}\n")
                
                preview_text.insert(tk.END, f"\n{'─'*60}\n\n")
            
            preview_text.configure(state='disabled')
        
        # Update column list when table selection changes
        def on_table_select(event):
            column_listbox.delete(0, tk.END)
            
            table_selection = table_listbox.curselection()
            if not table_selection:
                return
            
            selected_table = table_names[table_selection[0]]
            table_data = tables[selected_table]
            column_data_dict = table_data.get('column_data', {})
            
            # Populate columns
            for col_name, col_values in column_data_dict.items():
                column_listbox.insert('end', f"{col_name} ({len(col_values)} values)")
            
            update_preview()
        
        # Bind selection events
        table_listbox.bind('<<ListboxSelect>>', on_table_select)
        column_listbox.bind('<<ListboxSelect>>', update_preview)
        table_listbox.bind('<ButtonRelease-1>', on_table_select)
        column_listbox.bind('<ButtonRelease-1>', update_preview)
        
        # Also bind to radio button changes
        insert_mode_var.trace_add('write', lambda *args: update_preview())
        
        # Auto-select first table
        if table_names:
            table_listbox.selection_set(0)
            table_listbox.event_generate('<<ListboxSelect>>')
            on_table_select(None)
        
        # Buttons
        button_frame = tk.Frame(content_frame, bg='#ffffff')
        button_frame.pack(fill='both', pady=(0, 10))
        
        def insert_data():
            table_selection = table_listbox.curselection()
            column_selections = column_listbox.curselection()
            
            if not table_selection or not column_selections:
                messagebox.showwarning("No Selection", "Please select table and column(s)", parent=dialog)
                return
            
            selected_table = table_names[table_selection[0]]
            table_data = tables[selected_table]
            column_data_dict = table_data.get('column_data', {})
            
            column_names = list(column_data_dict.keys())
            selected_columns = [column_names[i] for i in column_selections]
            
            insert_mode = insert_mode_var.get()
            cursor_pos = self.sql_context.index(tk.INSERT)
            
            inserted_items = []
            
            for col_name in selected_columns:
                column_values = column_data_dict[col_name]
                
                if insert_mode == "variable":
                    # Insert as variable
                    safe_table_name = selected_table.upper().replace(' ', '_').replace('-', '_')
                    safe_col_name = col_name.upper().replace(' ', '_').replace('-', '_')
                    variable_name = f"{{TABLE_{safe_table_name}_{safe_col_name}}}"
                    
                    self.sql_context.insert(cursor_pos, variable_name + " ")
                    inserted_items.append(f"Variable: {variable_name}")
                else:
                    # Insert as raw data
                    values_str = ', '.join([f"'{v}'" if isinstance(v, str) else str(v) for v in column_values])
                    
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
        
        tk.Button(button_frame, text="📝 Insert Data", command=insert_data,
                 bg='#27ae60', fg='white', font=('Arial', 10, 'bold'),
                 padx=20, pady=6).pack(side='left')
        
        cancel_btn = tk.Button(
                button_frame,
                text="✖ Cancel",
                width=12,
                height=2,
                bg="#95a5a6",
                fg="white",
                font=("Arial", 10, "bold"),
                command=dialog.destroy
            )

        cancel_btn.pack(
            side="left",
            padx=5
        )
    def _legacy_load_excel_parameter_dialog_old(self):

        file_path = filedialog.askopenfilename(
            title="Select Excel File",
            filetypes=[
                ("Excel Files", "*.xlsx *.xls")
            ]
        )

        if not file_path:
            return

        try:

            df = pd.read_excel(file_path)

            if df.empty:
                messagebox.showwarning(
                    "Warning",
                    "Excel file contains no data"
                )
                return

            current_sql = self.sql_context.get(
                "1.0",
                tk.END
            )

            replaced_count = 0

            for column in df.columns:

                values = (
                    df[column]
                    .dropna()
                    .astype(str)
                    .tolist()
                )

                if not values:
                    continue

                sql_values = ",".join(
                    [f"'{v}'" for v in values]
                )

                placeholder = (
                    "{"
                    + column.upper()
                    + "}"
                )

                if placeholder in current_sql:

                    current_sql = current_sql.replace(
                        placeholder,
                        sql_values
                    )

                    replaced_count += 1

            self.sql_context.delete(
                "1.0",
                tk.END
            )

            self.sql_context.insert(
                "1.0",
                current_sql
            )

            messagebox.showinfo(
                "Success",
                f"Replaced {replaced_count} parameter(s)"
            )

        except Exception as e:

            messagebox.showerror(
                "Excel Error",
                str(e)
            )
        
            
    def _legacy_excel_parameter_loader_original(self):

        file_path = filedialog.askopenfilename(
            title="Select Excel File",
            filetypes=[
                ("Excel Files", "*.xlsx *.xls")
            ]
        )

        if not file_path:
            return

        try:

            df = pd.read_excel(file_path)

            if df.empty:
                messagebox.showwarning(
                    "Warning",
                    "Excel file contains no data"
                )
                return

            current_sql = self.sql_context.get(
                "1.0",
                tk.END
            )

            replaced_count = 0

            for column in df.columns:

                values = (
                    df[column]
                    .dropna()
                    .astype(str)
                    .tolist()
                )

                if not values:
                    continue

                sql_values = ",".join(
                    [f"'{v}'" for v in values]
                )

                placeholder = (
                    "{"
                    + column.upper()
                    + "}"
                )

                if placeholder in current_sql:

                    current_sql = current_sql.replace(
                        placeholder,
                        sql_values
                    )

                    replaced_count += 1

            self.sql_context.delete(
                "1.0",
                tk.END
            )

            self.sql_context.insert(
                "1.0",
                current_sql
            )

            messagebox.showinfo(
                "Success",
                f"Replaced {replaced_count} parameter(s)"
            )

        except Exception as e:

            messagebox.showerror(
                "Excel Error",
                str(e)
            )      
    def get_connection_string(self, db_type, user, password, host, port, database):
        """Generate connection string based on database type"""
        # URL encode password to handle special characters
        from urllib.parse import quote_plus
        encoded_password = quote_plus(password)
        
        # Clean port - ensure it's just the number
        port_clean = port.strip().split(':')[0] if ':' in port else port.strip()
        
        if db_type == 'PostgreSQL':
            if database:
                return f"postgresql+pg8000://{user}:{encoded_password}@{host}:{port_clean}/{database}"
            else:
                return f"postgresql+pg8000://{user}:{encoded_password}@{host}:{port_clean}"
        elif db_type == 'MySQL':
            if database:
                return f"mysql+pymysql://{user}:{encoded_password}@{host}:{port_clean}/{database}"
            else:
                return f"mysql+pymysql://{user}:{encoded_password}@{host}:{port_clean}"
        elif db_type == 'Microsoft SQL Server':
            # Use ODBC connection string format to avoid DSN length issues
            if database:
                conn_str = f"DRIVER={{SQL Server}};SERVER={host},{port_clean};DATABASE={database};UID={user};PWD={password}"
            else:
                # Connect to master database by default when no database specified
                # This allows querying all databases in the server
                conn_str = f"DRIVER={{SQL Server}};SERVER={host},{port_clean};DATABASE=master;UID={user};PWD={password}"
            return f"mssql+pyodbc:///?odbc_connect={quote_plus(conn_str)}"
        elif db_type == 'Oracle':
            # Oracle connection string format - use oracledb (thin mode - no Oracle Client needed)
            # Clean host in case it contains port
            host_clean = host.split(':')[0] if ':' in host else host
            if database:
                # Use oracledb format: host:port/service_name
                return f"oracle+oracledb://{user}:{encoded_password}@{host_clean}:{port_clean}/?service_name={database}"
            else:
                return f"oracle+oracledb://{user}:{encoded_password}@{host_clean}:{port_clean}"
        else:
            raise ValueError(f"Unsupported database type: {db_type}")
    
    def _legacy_excel_parameter_loader_before_connection(self):
        file_path = filedialog.askopenfilename(
            title="Select Excel File",
            filetypes=[("Excel Files", "*.xlsx *.xls")]
        )
        if not file_path:
            return

        try:
            workbook = pd.ExcelFile(file_path)
            sheet_names = workbook.sheet_names
            if not sheet_names:
                messagebox.showwarning("Excel Import", "Workbook has no worksheets")
                return

            first_sheet = pd.read_excel(workbook, sheet_name=sheet_names[0])
            if first_sheet.empty or len(first_sheet.columns) == 0:
                messagebox.showwarning("Excel Import", "Selected worksheet has no data")
                return
        except Exception as error:
            messagebox.showerror("Excel Import Error", str(error))
            return

        import re

        current_sql = self.sql_context.get("1.0", tk.END)
        placeholders = re.findall(
            r"\{\{?[A-Za-z_][A-Za-z0-9_]*\}?\}|:[A-Za-z_][A-Za-z0-9_]*",
            current_sql
        )
        parameter_var = tk.StringVar(
            value=placeholders[0] if placeholders else "{PARAMETER}"
        )
        sheet_var = tk.StringVar(value=sheet_names[0])
        sheet_data = {"dataframe": first_sheet}
        column_lookup = {}

        dialog = tk.Toplevel(self.root)
        dialog.title("Load Excel SQL Parameters")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.geometry("520x250")

        content = ttk.Frame(dialog, padding=16)
        content.pack(fill="both", expand=True)
        content.columnconfigure(1, weight=1)

        ttk.Label(content, text="Worksheet").grid(row=0, column=0, sticky="w", pady=6)
        sheet_combo = ttk.Combobox(
            content,
            textvariable=sheet_var,
            values=sheet_names,
            state="readonly"
        )
        sheet_combo.grid(row=0, column=1, sticky="ew", pady=6)

        ttk.Label(content, text="Value column").grid(row=1, column=0, sticky="w", pady=6)
        column_var = tk.StringVar()
        column_combo = ttk.Combobox(content, textvariable=column_var, state="readonly")
        column_combo.grid(row=1, column=1, sticky="ew", pady=6)

        ttk.Label(content, text="SQL parameter").grid(row=2, column=0, sticky="w", pady=6)
        ttk.Entry(content, textvariable=parameter_var).grid(row=2, column=1, sticky="ew", pady=6)

        def update_columns(_event=None):
            try:
                dataframe = pd.read_excel(workbook, sheet_name=sheet_var.get())
                sheet_data["dataframe"] = dataframe
                column_lookup.clear()
                column_lookup.update({str(column): column for column in dataframe.columns})
                column_names = list(column_lookup)
                column_combo.configure(values=column_names)
                column_var.set(column_names[0] if column_names else "")
            except Exception as error:
                messagebox.showerror("Excel Import Error", str(error), parent=dialog)

        def insert_values():
            dataframe = sheet_data["dataframe"]
            selected_column = column_var.get()
            parameter = parameter_var.get().strip()
            if selected_column not in column_lookup:
                messagebox.showwarning("Excel Import", "Select a value column", parent=dialog)
                return

            values = dataframe[column_lookup[selected_column]].dropna().tolist()
            if not values:
                messagebox.showwarning("Excel Import", "Selected column has no values", parent=dialog)
                return

            sql_values = ", ".join(
                "'" + str(value).replace("'", "''") + "'"
                for value in values
            )
            sql_query = self.sql_context.get("1.0", tk.END)

            # รองรับ Placeholder ที่มี Space ได้
            # {ACCOUNT_LIST}
            # { ACCOUNT_LIST}
            # {ACCOUNT_LIST }
            # { ACCOUNT_LIST }

            placeholder_name = parameter.strip("{}").strip()

            placeholder_pattern = (
                r"\{\s*"
                + re.escape(placeholder_name)
                + r"\s*\}"
            )

            found_placeholder = bool(
                re.search(
                    placeholder_pattern,
                    sql_query,
                    flags=re.IGNORECASE
                )
            )

            if found_placeholder:

                sql_query = re.sub(
                    placeholder_pattern,
                    sql_values,
                    sql_query,
                    flags=re.IGNORECASE
                )

            else:
                
                sql_query, replacement_count = re.subn(
                    r"(\bIN\s*\()\s*(?:\.\.\.|NULL)?\s*(\))",
                    lambda match: f"{match.group(1)}{sql_values}{match.group(2)}",
                    sql_query,
                    count=1,
                    flags=re.IGNORECASE
                )
                if replacement_count == 0:
                    messagebox.showwarning(
                        "SQL Parameter Not Found",
                        "Use a parameter such as {PARAMETER} in the query, or leave an IN (...) list empty.",
                        parent=dialog
                    )
                    return

            self.sql_context.delete("1.0", tk.END)
            self.sql_context.insert("1.0", sql_query)
            self.loaded_excel_data = dataframe
            messagebox.showinfo(
                "Excel Parameters Loaded",
                f"Inserted {len(values)} values from {selected_column}.",
                parent=dialog
            )
            dialog.destroy()

        sheet_combo.bind("<<ComboboxSelected>>", update_columns)
        update_columns()
        button_frame = ttk.Frame(content)
        button_frame.grid(row=3, column=0, columnspan=2, sticky="e", pady=(16, 0))
        ttk.Button(button_frame, text="Insert Values", command=insert_values).pack(side="left", padx=4)
        ttk.Button(button_frame, text="Cancel", command=dialog.destroy).pack(side="left", padx=4)
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
            messagebox.showerror("Error", "Please fill in all connection fields (Database is optional)")
            return

        try:
            self.results_text.insert(tk.END, f"Connecting to {db_type} database...\n")
            self.results_text.see(tk.END)
            connection_string = self.get_connection_string(
                db_type, user, password, host, port, database
            )
            self.engine = create_engine(
                connection_string,
                connect_args=self.get_connect_args(db_type)
            )
            with self.engine.connect() as connection:
                connection.execute(text("SELECT 1 FROM DUAL" if db_type == "Oracle" else "SELECT 1"))

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
            messagebox.showerror("Connection Error", str(error))
    
    def is_select_query(self, query):
        """Check if query is a SELECT statement"""
        query_upper = query.strip().upper()
        # Remove comments
        query_upper = ' '.join([line for line in query_upper.split('\n') if not line.strip().startswith('--')])
        # Check if it starts with SELECT, WITH (for CTEs), or contains SELECT in first word
        return query_upper.startswith('SELECT') or query_upper.startswith('WITH') or query_upper.startswith('(SELECT')
    
    def execute_query(self):
        """Execute the SQL query with comprehensive error handling and retry capability"""
        if not self.engine:
            messagebox.showerror("Error", "Please connect to database first")
            return
        
        sql_query = self.sql_context.get(1.0, tk.END).strip()
        if not sql_query:
            messagebox.showerror("Error", "Please enter a SQL query")
            return
        
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
            if query_upper.startswith('UPDATE'):
                operation = "UPDATE"
                icon = "✏️"
            elif query_upper.startswith('INSERT'):
                operation = "INSERT"
                icon = "➕"
            elif query_upper.startswith('DELETE'):
                operation = "DELETE"
                icon = "🗑️"
            else:
                operation = "MODIFY"
                icon = "⚙️"
            
            # Update results text
            self.results_text.delete("1.0", tk.END)
            self.results_text.insert(tk.END, f"{'='*150}\n")
            self.results_text.insert(tk.END, f"✅ {icon} {operation} Statement Executed Successfully!\n")
            self.results_text.insert(tk.END, f"{'='*150}\n\n")
            self.results_text.insert(tk.END, f"📊 Rows Affected: {rows_affected:,}\n\n")
            self.results_text.insert(tk.END, f"SQL Statement:\n{sql_query}\n\n")
            self.results_text.insert(tk.END, f"{'─'*150}\n")
            self.results_text.see(tk.END)
            
            # Re-enable execute button
            self.execute_btn.config(state="normal", text="▶️ Execute Query")
            
            # Show success message
            messagebox.showinfo("Success", f"{operation} executed successfully!\n\nRows affected: {rows_affected:,}")
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to display results:\n{str(e)}")
            self.execute_btn.config(state="normal", text="▶️ Execute Query")
    
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
            self.execute_btn.config(state="normal", text="▶️ Execute Query")
            
            # Show results in popup table window
            self.show_table_popup(
                df,
                sql_query
            )
                        
        except Exception as e:
            messagebox.showerror("Error", f"Failed to display results:\n{str(e)}")
            self.execute_btn.config(state="normal", text="▶️ Execute Query")
    
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
        self.execute_btn.config(state="normal", text="▶️ Execute Query")
        
        messagebox.showerror("Query Error", f"Failed to execute query:\n\n{str(error)}")
    
    def show_table_popup(
        self,
        df,
        sql_query,
        on_double_click=None,
        job_name=None):
        """Show DataFrame in a popup window with Treeview"""
        # Create popup window
        popup = tk.Toplevel(self.root)
        popup.title(
            f"{job_name} - Query Results - {len(df):,} rows × {df.shape[1]} columns"
            if job_name
            else f"Query Results - {len(df):,} rows × {df.shape[1]} columns"
        )
        popup.geometry("1200x700")
        
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
        
        ttk.Label(info_frame, text=f"📊 Total Rows: {len(df):,}", font=('Arial', 10, 'bold')).grid(row=0, column=0, sticky=tk.W, padx=5)
        ttk.Label(info_frame, text=f"📋 Total Columns: {df.shape[1]}", font=('Arial', 10, 'bold')).grid(row=0, column=1, sticky=tk.W, padx=5)
        
        # Table frame with scrollbars
        table_frame = ttk.LabelFrame(main_frame, text="Data Preview", padding="10")
        table_frame.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        table_frame.columnconfigure(0, weight=1)
        table_frame.rowconfigure(0, weight=1)
        
        # Create Treeview with scrollbars
        tree_scroll_y = ttk.Scrollbar(table_frame, orient=tk.VERTICAL)
        tree_scroll_x = ttk.Scrollbar(table_frame, orient=tk.HORIZONTAL)
        
        tree = ttk.Treeview(table_frame,
                           columns=list(df.columns),
                           show='headings',
                           yscrollcommand=tree_scroll_y.set,
                           xscrollcommand=tree_scroll_x.set,
                           selectmode='extended')
        
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
            tree.bind('<Double-Button-1>', lambda e: self.on_tree_double_click(e, tree, on_double_click))
        
        # Mousewheel scrolls treeview; suppress main canvas scroll while popup open
        def _tree_mousewheel(e):
            tree.yview_scroll(int(-1 * (e.delta / 120)), "units")
            return 'break'

        def _on_tree_enter(e):
            tree.bind_all('<MouseWheel>', _tree_mousewheel)

        def _on_tree_leave(e):
            tree.unbind_all('<MouseWheel>')
            self.canvas.bind_all('<MouseWheel>', self._main_mousewheel)

        def _restore_main_on_close(e=None):
            self.canvas.bind_all('<MouseWheel>', self._main_mousewheel)

        tree.bind('<Enter>', _on_tree_enter)
        tree.bind('<Leave>', _on_tree_leave)
        popup.bind('<Destroy>', _restore_main_on_close)
        # Suppress main scroll while popup window is open
        self.canvas.unbind_all('<MouseWheel>')
        
        # Pagination info label (create before load_page function)
        page_label = ttk.Label(info_frame,
                              text=f"Page 1 of {total_pages}",
                              font=('Arial', 9, 'bold'))
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
                values = [str(val) if pd.notna(val) else '' for val in row]
                tree.insert('', tk.END, values=values)

            # Update page info
            shown_start = start_row + 1 if end_row > start_row else 0
            page_label.config(text=f"Page {page_num + 1} of {total_pages} (Rows {shown_start:,}-{end_row:,} of {len(df):,})")

            # Update button states
            prev_btn.config(state="normal" if page_num > 0 else "disabled")
            next_btn.config(state="normal" if page_num < total_pages - 1 else "disabled")

        # Pagination buttons
        ttk.Button(button_frame, text="⏮️ First",
                  command=lambda: load_page(0)).grid(row=0, column=0, padx=5)
        prev_btn = ttk.Button(button_frame, text="◀️ Previous",
                             command=lambda: load_page(page_state["current"] - 1))
        prev_btn.grid(row=0, column=1, padx=5)

        next_btn = ttk.Button(button_frame, text="Next ▶️",
                             command=lambda: load_page(page_state["current"] + 1))
        next_btn.grid(row=0, column=2, padx=5)
        ttk.Button(button_frame, text="Last ⏭️",
                  command=lambda: load_page(total_pages - 1)).grid(row=0, column=3, padx=5)

        # Separator
        ttk.Separator(button_frame, orient='vertical').grid(row=0, column=4, padx=10, sticky='ns')

        # Action buttons
        ttk.Button(button_frame, text="📋 Copy Selected",
                  command=lambda: self.copy_selected_rows(tree)).grid(row=0, column=5, padx=5)
        ttk.Button(
                button_frame,
                text="💾 Export to CSV",
                command=lambda: self.export_to_csv(df)
            ).grid(row=0, column=6, padx=5)

        ttk.Button(
                button_frame,
                text="📤 Export Excel",
                command=lambda: self.export_to_excel_result(
                    df,
                    sql_query,
                    job_name
                )
            ).grid(row=0, column=7, padx=5)

        ttk.Button(
                button_frame,
                text="❌ Close",
                command=popup.destroy
            ).grid(row=0, column=8, padx=5)

        # Initial data load (also sets Previous/Next button states)
        load_page(0)
        return popup
    
    def on_tree_double_click(self, event, tree, callback):
        """Handle double-click on tree item"""
        try:
            item = tree.selection()[0]
            values = tree.item(item)['values']
            if values:
                callback(values)
        except:
            pass
    
    def sort_treeview(self, tree, col, reverse):
        """Sort treeview by column"""
        data = [(tree.set(child, col), child) for child in tree.get_children('')]
        data.sort(reverse=reverse)
        for index, (val, child) in enumerate(data):
            tree.move(child, '', index)
        tree.heading(col, command=lambda: self.sort_treeview(tree, col, not reverse))
    
    def copy_selected_rows(self, tree):
        """Copy selected rows to clipboard"""
        try:
            selected = tree.selection()
            if not selected:
                messagebox.showwarning("Warning", "Please select rows to copy")
                return
            
            # Get column names
            columns = tree['columns']
            text = '\t'.join(columns) + '\n'
            
            # Get selected rows
            for item in selected:
                values = [tree.set(item, col) for col in columns]
                text += '\t'.join(values) + '\n'
            
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
                defaultextension=".csv",
                filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
            )
            if file_path:
                df.to_csv(file_path, index=False, encoding='utf-8-sig')
                messagebox.showinfo("Success", f"Data exported successfully!\n\nFile: {file_path}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to export: {str(e)}")

    def export_to_excel_result(
        self,
        df,
        sql_query,
        job_name=None):
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
        
        ttk.Label(loading_dialog, text="⏳ Loading tables...",
                 font=('Arial', 11, 'bold')).pack(pady=10)
        progress = ttk.Progressbar(loading_dialog, mode='indeterminate', length=250)
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
                            if db_type == 'PostgreSQL':
                                result = conn.execute(text("SELECT datname FROM pg_database WHERE datistemplate = false AND datname NOT IN ('postgres', 'template0', 'template1')"))
                                databases_to_check = [row[0] for row in result]
                            elif db_type == 'MySQL':
                                result = conn.execute(text("SHOW DATABASES"))
                                databases_to_check = [row[0] for row in result if row[0] not in ['mysql', 'information_schema', 'performance_schema', 'sys']]
                            elif db_type == 'Microsoft SQL Server':
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
                            elif db_type == 'Oracle':
                                result = conn.execute(text("SELECT username FROM all_users WHERE username NOT IN ('SYS', 'SYSTEM', 'DBSNMP', 'SYSMAN', 'OUTLN', 'MDSYS', 'ORDSYS', 'EXFSYS', 'DMSYS', 'WMSYS', 'CTXSYS', 'ANONYMOUS', 'XDB', 'XS$NULL', 'OJVMSYS', 'LBACSYS', 'APEX_PUBLIC_USER', 'FLOWS_FILES', 'APEX_040000', 'APEX_040200', 'SPATIAL_CSW_ADMIN_USR', 'SPATIAL_WFS_ADMIN_USR', 'PUBLIC') ORDER BY username"))
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
                            if db_type == 'Oracle':
                                # For Oracle, use current connection with schema
                                inspector = inspect(self.engine)
                                try:
                                    tables = inspector.get_table_names(schema=database)
                                    for table in tables:
                                        table_list.append({
                                            'Database': database,
                                            'Schema': database,
                                            'Table': table
                                        })
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
                                    database
                                )
                                print(f"   🔌 Connecting to {database}...")
                                temp_engine = create_engine(temp_conn_str, connect_args=self.get_connect_args(db_type))
                                temp_inspector = inspect(temp_engine)
                                temp_schemas = temp_inspector.get_schema_names()
                                print(f"   ✅ Connected! Found {len(temp_schemas)} schemas: {temp_schemas}")
                                
                                # Define skip_schemas based on database type
                                if db_type == 'Microsoft SQL Server':
                                    # Only skip true system schemas, not user schemas
                                    skip_schemas = ['information_schema', 'sys', 'guest']
                                elif db_type == 'PostgreSQL':
                                    skip_schemas = ['information_schema', 'pg_catalog', 'pg_toast', 'pg_toast_temp_1']
                                else:  # MySQL
                                    skip_schemas = ['information_schema', 'mysql', 'performance_schema', 'sys']
                                
                                schema_count = 0
                                for schema in temp_schemas:
                                    if schema.lower() in skip_schemas:
                                        print(f"      ⏭️  Skipping system schema: {schema}")
                                        continue
                                    
                                    try:
                                        # Use raw SQL for SQL Server to avoid HY104 error
                                        if db_type == 'Microsoft SQL Server':
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
                                            print(f"      ✅ Schema '{schema}': {len(tables)} tables")
                                            schema_count += 1
                                            for table in tables:
                                                table_list.append({
                                                    'Database': database,
                                                    'Schema': schema,
                                                    'Table': table
                                                })
                                        else:
                                            print(f"      ⚠️  Schema '{schema}': 0 tables (skipping)")
                                    except Exception as schema_err:
                                        print(f"      ❌ Error reading schema '{schema}': {schema_err}")
                                        import traceback
                                        traceback.print_exc()
                                        # Skip this schema and continue with others
                                        continue
                                
                                temp_engine.dispose()
                                total_tables = len([t for t in table_list if t['Database'] == database])
                                print(f"   📊 Completed {database}: {schema_count} schemas, {total_tables} tables total")
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
                        skip_schemas = ['information_schema', 'pg_catalog', 'pg_toast', 'pg_toast_temp_1', 'SYSTEM', 'SYS', 'MDSYS', 'CTXSYS', 'XDB', 'ORDSYS', 'EXFSYS', 'WMSYS', 'DBSNMP']
                        if schema in skip_schemas:
                            continue
                        
                        try:
                            tables = inspector.get_table_names(schema=schema)
                            for table in tables:
                                table_list.append({
                                    'Database': current_db_name,
                                    'Schema': schema,
                                    'Table': table
                                })
                        except:
                            pass
                
                # Update UI in main thread
                self.root.after(0, lambda: self.on_list_tables_success(table_list, loading_dialog, bool(current_db_name)))
                
            except Exception as e:
                # Handle error in main thread
                self.root.after(0, lambda: self.on_list_tables_error(e, loading_dialog))
        
        # Start background thread
        thread = threading.Thread(target=fetch_tables_in_background, daemon=True)
        thread.start()
    
    def on_list_tables_success(self, table_list, loading_dialog, has_database=True):
        """Handle successful table listing"""
        try:
            # Close loading dialog
            loading_dialog.destroy()
            
            # Re-enable button
            self.inspect_btn.config(state="normal", text="📊 List Tables")
            
            # Convert to DataFrame
            if table_list:
                df = pd.DataFrame(table_list)
                
                # Count unique items
                if 'Database' in df.columns:
                    summary = f"✅ Found {len(df)} tables across {df['Schema'].nunique()} schemas in {df['Database'].nunique()} database(s)\n\n"
                else:
                    summary = f"✅ Found {len(df)} tables across {df['Schema'].nunique()} schemas\n\n"
                
                # Update results text
                self.results_text.delete("1.0", tk.END)
                self.results_text.insert(tk.END, summary)
                self.results_text.insert(tk.END, "Opening results in new window...\n")
                self.results_text.insert(tk.END, "💡 Tip: Double-click on a table to insert it into SQL Query\n")
                
                # Define callback for double-click
                def on_table_double_click(values):
                    # Always expect 3-column format (Database, Schema, Table)
                    if len(values) != 3:
                        return
                    
                    database = values[0]
                    schema = values[1]
                    table = values[2]
                    
                    # Generate query based on database type
                    if self.db_type.get() == 'Microsoft SQL Server':
                        query = f"SELECT * FROM [{database}].[{schema}].[{table}]"
                    elif self.db_type.get() == 'Oracle':
                        # Oracle uses schema.table format (database is schema in Oracle)
                        query = f"SELECT * FROM {database}.{table}"
                    elif self.db_type.get() == 'MySQL':
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
                self.show_table_popup(df, "Database Schema Information", on_double_click=on_table_double_click)
            else:
                self.results_text.insert(tk.END, "⚠️ No tables found in database\n\n")
                messagebox.showinfo("Info", "No tables found in the database")
                
        except Exception as e:
            messagebox.showerror("Error", f"Failed to display tables:\n{str(e)}")
            self.inspect_btn.config(state="normal", text="📊 List Tables")
    
    def on_list_tables_error(self, error, loading_dialog):
        """Handle table listing error"""
        try:
            # Close loading dialog
            loading_dialog.destroy()
        except:
            pass
        
        # Re-enable button
        self.inspect_btn.config(state="normal", text="📊 List Tables")
        
        self.results_text.insert(tk.END, f"❌ Error: {str(error)}\n\n")
        self.results_text.see(tk.END)
        messagebox.showerror("Error", f"Failed to list tables:\n{str(error)}")
    
    def load_jobs(self):
        """Load saved jobs from file"""

        if not os.path.exists(self.jobs_file):
            return []

        try:

            with open(
                self.jobs_file,
                'r',
                encoding='utf-8'
            ) as f:

                jobs = json.load(f)

            modified = False

            for job in jobs:

                # รองรับไฟล์เก่า
                if "profile" not in job:

                    if self.saved_profiles:
                        first_profile = list(
                            self.saved_profiles.keys()
                        )[0]
                    else:
                        first_profile = "DEFAULT"

                    job["profile"] = first_profile
                    modified = True

            # บันทึกกลับเฉพาะกรณีพบข้อมูลเก่า
            if modified:

                with open(
                    self.jobs_file,
                    'w',
                    encoding='utf-8'
                ) as f:

                    json.dump(
                        jobs,
                        f,
                        indent=4,
                        ensure_ascii=False
                    )

            return jobs

        except Exception as e:
            print(f"Error loading jobs: {e}")
            return []
    
    def save_jobs(self):
        """Save jobs to file"""
        try:
            with open(self.jobs_file, 'w', encoding='utf-8') as f:
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
        dialog.configure(bg='#f0f0f0')
        dialog.transient(self.root)
        dialog.grab_set()
        
        x = (self.root.winfo_screenwidth() - 550) // 2
        y = (self.root.winfo_screenheight() - 320) // 2
        dialog.geometry(f"+{x}+{y}")
        
        content = tk.Frame(dialog, bg='#ffffff', relief='solid', bd=1)
        content.pack(fill='both', expand=True, padx=15, pady=15)
        
        tk.Label(content, text="💾 Save Job", font=('Arial', 12, 'bold'),
                bg='#ffffff', fg='#2c3e50').pack(pady=(10, 15))
        
        tk.Label(content, text="Job Name (can be long):", font=('Arial', 10),
                bg='#ffffff').pack(anchor='w', padx=10, pady=(0, 5))
        
        name_entry = tk.Entry(content, font=('Arial', 10), width=60)
        name_entry.pack(padx=10, pady=(0, 10))
        name_entry.focus()
        
        # Suggest name from query
        if 'SELECT' in sql_query.upper():
            parts = sql_query.upper().split('FROM')
            if len(parts) > 1:
                table_part = parts[1].strip().split()[0]
                name_entry.insert(0, f"Query - {table_part}")
        
        tk.Label(content, text=f"💡 Query preview: {sql_query[:80]}{'...' if len(sql_query) > 80 else ''}",
                font=('Arial', 8), bg='#ffffff', fg='#7f8c8d').pack(
                    padx=10,
                    pady=(5, 20)
                )
        
        def save():
            job_name = name_entry.get().strip()
            if not job_name:
                messagebox.showwarning("Warning", "Please enter job name", parent=dialog)
                return
            
            job = {
                'name': job_name,
                'profile': self.profile_combo.get(),
                'query': sql_query,
                'database': self.db_name.get(),
                'db_type': self.db_type.get(),
                'created': pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            
            self.saved_jobs.append(job)
            self.save_jobs()
            self.update_jobs_list()
            
            self.results_text.delete("1.0", tk.END)
            self.results_text.insert(tk.END, f"💾 Job saved: {job_name}\n")
            self.results_text.insert(tk.END, f"📊 Total jobs: {len(self.saved_jobs)}\n")
            self.results_text.see(tk.END)
            
            messagebox.showinfo("Success", f"Job saved!\n\nTotal: {len(self.saved_jobs)} jobs", parent=dialog)
            dialog.destroy()
        
        button_frame = tk.Frame(content, bg='#ffffff')
        button_frame.pack(
            side=tk.BOTTOM,
            pady=(20, 15)
        )
        
        save_btn = tk.Button(
            button_frame,
            text="💾 Save",
            width=12,
            height=2,
            bg="#27ae60",
            fg="white",
            font=("Arial", 10, "bold"),
            command=save
        )

        save_btn.pack(
            side="left",
            padx=5
        )
        
        cancel_btn = tk.Button(
    button_frame,
            text="✖ Cancel",
            width=12,
            height=2,
            bg="#95a5a6",
            fg="white",
            font=("Arial", 10, "bold"),
            command=dialog.destroy
        )

        cancel_btn.pack(
            side="left",
            padx=5
        )
    
    def _start_job_result_report(self):
        self.results_text.delete("1.0", tk.END)

    def _finish_job_result_report(self, processed_jobs, successes, failures):
        separator = "=" * 57
        self.results_text.insert(tk.END, f"\n{separator}\n")
        self.results_text.insert(
            tk.END,
            f"Total   : {processed_jobs}\n"
            f"Success : {successes}\n"
            f"Fail    : {failures}\n"
        )
        self.results_text.insert(tk.END, f"{separator}\n")
        self.results_text.see(tk.END)

    def run_job(self, job):
        """Run single saved job"""

        if not self.engine:
            messagebox.showerror(
                "Error",
                "Please connect to database first"
            )
            return

        sql_query = job.get("query", "")

        if not sql_query.strip():
            messagebox.showwarning(
                "Warning",
                "SQL Query is empty"
            )
            return

        # หาเลขลำดับของ Job ตาม Saved Jobs
        current_profile = self.profile_combo.get()

        profile_jobs = [
            j for j in self.saved_jobs
            if j.get("profile") == current_profile
        ]

        job_index = 1

        for idx, j in enumerate(profile_jobs, start=1):
            if j == job:
                job_index = idx
                break

        self._start_job_result_report()
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
                query_time=query_time
            )
            if status == "success":
                self._finish_job_result_report(1, 1, 0)
            else:
                self._finish_job_result_report(1, 0, 1)

        def run_in_background():
            import time
            start_time = time.perf_counter()
            try:
                if self.is_select_query(sql_query):
                    result_data = pd.read_sql_query(sql_query, self.engine)
                    query_type = "select"
                else:
                    with self.engine.connect() as conn:
                        result = conn.execute(text(sql_query))
                        conn.commit()
                        result_data = result.rowcount
                    query_type = "modify"

                elapsed = time.perf_counter() - start_time
                self.root.after(
                    0,
                    lambda: finish("success", result_data, query_type, query_time=elapsed)
                )

            except Exception as e:
                elapsed = time.perf_counter() - start_time
                self.root.after(
                    0,
                    lambda err=e: finish("error", error=err, query_time=elapsed)
                )

        threading.Thread(target=run_in_background, daemon=True).start()

    def run_selected_job(self):
        """Run profile jobs sequentially and append each result to Results."""
        current_profile = self.profile_combo.get()

        profile_jobs = [
            job
            for job in self.saved_jobs
            if job.get("profile") == current_profile
        ]
        
        for index, job in enumerate(profile_jobs, start=1):
            job["run_index"] = index

        if not profile_jobs:
            messagebox.showwarning(
                "Warning",
                "No jobs to run"
            )
            return
        
        if not self.engine:
            messagebox.showerror("Error", "Please connect to database first")
            return
        
        self._start_job_result_report()
        
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
                
                current_profile = self.profile_combo.get()

                profile_jobs = [
                    job
                    for job in self.saved_jobs
                    if job.get("profile") == current_profile
                ]
                
                for index, job in enumerate(profile_jobs, start=1):
                    job["run_index"] = index

                for idx, job in enumerate(profile_jobs, 1):
                    start_time = time_module.time()
                    self.root.after(0, lambda i=idx, j=job: self.update_job_status(i, j, "running"))
                    time_module.sleep(0.1)
                    
                    try:
                        # Check if it's a SELECT query or data modification
                        if self.is_select_query(job['query']):
                            # Execute SELECT query
                            df = pd.read_sql_query(job['query'], self.engine)
                            elapsed_time = time_module.time() - start_time
                            
                            # Store result
                            job_results.append({
                                'Job #': idx,
                                'Name': job['name'],
                                'Status': '✅ Success',
                                'Rows': len(df),
                                'Columns': df.shape[1],
                                'Time (s)': f"{elapsed_time:.2f}",
                                '_job': job,
                                '_data': df,
                                '_query_type': 'select',
                                '_error': None
                            })

                            self.root.after(
                                0,
                                lambda i=idx, j=job, d=df, qt=elapsed_time:
                                    self.update_job_status(
                                        i,
                                        j,
                                        "success",
                                        d,
                                        query_type="select",
                                        query_time=qt,
                                        show_popup=False
                                    )
                            )
                            success_count += 1
                        else:
                            # Execute UPDATE/INSERT/DELETE statement
                            with self.engine.connect() as conn:
                                result = conn.execute(text(job['query']))
                                conn.commit()
                                rows_affected = result.rowcount
                            elapsed_time = time_module.time() - start_time
                            
                            # Store result
                            job_results.append({
                                'Job #': idx,
                                'Name': job['name'],
                                'Status': '✅ Success',
                                'Rows': rows_affected,
                                'Columns': 0,
                                'Time (s)': f"{elapsed_time:.2f}",
                                '_job': job,
                                '_data': rows_affected,
                                '_query_type': 'modify',
                                '_error': None
                            })

                            self.root.after(
                                0,
                                lambda i=idx, j=job, r=rows_affected, qt=elapsed_time:
                                    self.update_job_status(
                                        i,
                                        j,
                                        "success",
                                        r,
                                        query_type="modify",
                                        query_time=qt,
                                        show_popup=False
                                    )
                            )
                            success_count += 1
                    except Exception as e:
                        elapsed_time = time_module.time() - start_time
                        error_msg = str(e)
                        
                        # Store error result
                        job_results.append({
                            'Job #': idx,
                            'Name': job['name'],
                            'Status': '❌ Failed',
                            'Rows': 0,
                            'Columns': 0,
                            'Time (s)': f"{elapsed_time:.2f}",
                            '_job': job,
                            '_data': None,
                            '_query_type': 'select',
                            '_error': e
                        })

                        self.root.after(
                            0,
                            lambda i=idx, j=job, err=e, qt=elapsed_time:
                                self.update_job_status(
                                    i,
                                    j,
                                    "error",
                                    error=err,
                                    query_time=qt,
                                    show_popup=False
                                )
                        )
                        error_count += 1
                        
                        # Check if this is a data modification query (UPDATE/INSERT/DELETE)
                        # If so, stop execution immediately
                        if not self.is_select_query(job['query']):
                            query_upper = job['query'].strip().upper()
                            if query_upper.startswith('UPDATE'):
                                operation = "UPDATE"
                            elif query_upper.startswith('INSERT'):
                                operation = "INSERT"
                            elif query_upper.startswith('DELETE'):
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
                        success_count,
                        error_count,
                        job_results,
                        len(profile_jobs)
                    )
                )
                
            except Exception as e:
                self.root.after(0, lambda err=e: self.show_batch_error(err))
        
        # Start background thread
        thread = threading.Thread(target=run_all_jobs, daemon=True)
        thread.start()

    def update_job_status(self, job_num, job, status, data=None, error=None, query_type='select', query_time=0, show_popup=True):
        """Update job execution status in results.

        show_popup=False is used by Run All Jobs: results are written to the
        Results panel only, and one summary window is shown at the end.
        """
        if status == "running":
            return
            
        elif status == "success":
            if query_type != 'select':
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
                "Status      : Success\n"
            )
            self.results_text.see(tk.END)
            if not show_popup:
                return
            popup = self.show_table_popup(
                popup_data,
                job["query"],
                job_name=job["name"]
            )
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
                f"Error       : {error}\n"
            )
            self.results_text.see(tk.END)
            if not show_popup:
                return
            self.root.update_idletasks()
            popup_data = pd.DataFrame({"Error": [str(error)]})
            popup = self.show_table_popup(
                popup_data,
                job["query"],
                job_name=job["name"]
            )
            popup.transient(self.root)
            popup.lift()
            popup.focus_force()
    
    def show_batch_summary(
        self,
        success_count,
        error_count,
        job_results,
        total_jobs
    ):

        self.execute_btn.config(state="normal")
        self.inspect_btn.config(state="normal")
        self.save_job_btn.config(state="normal")
        self._finish_job_result_report(
            success_count + error_count,
            success_count,
            error_count
        )

        if not job_results:
            return

        # One summary window for the whole run (instead of one popup per job).
        # Double-click a row to open that job's full result.
        summary_df = pd.DataFrame([
            {k: v for k, v in r.items() if not k.startswith('_')}
            for r in job_results
        ])
        results_by_num = {str(r['Job #']): r for r in job_results}

        def open_job_result(values):
            result = results_by_num.get(str(values[0]))
            if not result:
                return
            job = result['_job']
            if result['_error'] is not None:
                popup_data = pd.DataFrame({"Error": [str(result['_error'])]})
            elif result['_query_type'] != 'select':
                popup_data = pd.DataFrame({"Rows affected": [result['_data']]})
            else:
                popup_data = result['_data']
            popup = self.show_table_popup(
                popup_data,
                job["query"],
                job_name=job["name"]
            )
            popup.transient(self.root)
            popup.lift()
            popup.focus_force()

        self.results_text.insert(
            tk.END,
            "💡 Double-click a job in the summary window to open its result\n"
        )
        self.results_text.see(tk.END)

        summary_popup = self.show_table_popup(
            summary_df,
            "Run All Jobs - Summary",
            on_double_click=open_job_result,
            job_name="Run All Jobs Summary"
        )
        summary_popup.transient(self.root)
        summary_popup.lift()
        summary_popup.focus_force()

    def export_jobs_to_excel(self, jobs_override=None):
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
        file_path = filedialog.asksaveasfilename(
            title="Export Jobs to Excel",
            defaultextension=".xlsx",
            filetypes=[("Excel files", "*.xlsx")],
            initialfile=default_name
        )
        if not file_path:
            return  # User cancelled

        current_profile = self.profile_combo.get()

        jobs = jobs_override if jobs_override is not None else [
            job
            for job in self.saved_jobs
            if job.get("profile") == current_profile
        ]

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
            self.export_excel_btn.config(state="normal", text="📤 Export Excel")
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
                f"Success: {ok} | Failed: {failed} | Skipped: {skipped}"
            )

        def worker():
            import re
            illegal_chars = re.compile(
                r'[\x00-\x08\x0b\x0c\x0e-\x1f]'
            )

            max_rows = 1048575  # Excel รองรับ 1,048,576 แถว (หัก header 1 แถว)
            used_names = set()
            ok = failed = skipped = 0
            fatal_error = None
            start_all = time_module.time()

            try:
                with pd.ExcelWriter(file_path, engine='openpyxl') as writer:
                    for idx, job in enumerate(jobs, 1):
                        job_name = job.get('name', f'Job {idx}')
                        query = job['query']
                        log(f"DEBUG Job Name : {job_name}\n")
                        t0 = time_module.time()

                        # ---- ตั้งชื่อ Sheet จากชื่อ Job (<=31 ตัว, ห้ามมี [ ] : * ? / \ , ห้ามซ้ำ) ----
                        base = re.sub(r'[\[\]\:\*\?\/\\]', '_', str(job_name)).strip().strip("'")
                        base = (base or f"Job{idx}")[:31]
                        sheet = base
                        n = 2
                        while sheet.lower() in used_names:
                            suffix = f"_{n}"
                            sheet = base[:31 - len(suffix)] + suffix
                            n += 1
                        used_names.add(sheet.lower())

                        log(f"{'─'*150}\n")
                        log(f"▶️ Job #{idx}: {job_name}\n")
                        log(f"   Sheet: {sheet}\n")

                        try:
                            preloaded_df = job.get("_export_dataframe")
                            if preloaded_df is None and not self.is_select_query(query):
                                skipped += 1
                                log("   Status: ⏭️ Skipped (ไม่ใช่ SELECT - ไม่รันซ้ำเพื่อความปลอดภัย)\n\n")
                                pd.DataFrame({
                                    'Status': ['Skipped'],
                                    'Message': ['Not a SELECT query - not executed during export'],
                                    'Query': [query]
                                }).to_excel(writer, sheet_name=sheet, index=False)
                                continue
                            query_start = time_module.time()
                            df = (
                                preloaded_df.copy()
                                if preloaded_df is not None
                                else pd.read_sql_query(query, self.engine)
                            )
                            query_elapsed = (
                                time_module.time()
                                - query_start
                            )

                            log(
                                f"Query Time : "
                                f"{query_elapsed:.2f}s\n"
                            )
                            if df.empty:

                                log(f"   ⚠️ No Data Found\n")

                                pd.DataFrame(
                                    columns=df.columns
                                ).to_excel(
                                    writer,
                                    sheet_name=sheet,
                                    index=False
                                )

                                ws = writer.sheets[sheet]

                                start_row = 3

                                for line_no, line in enumerate(query.splitlines()):

                                    ws.cell(
                                        row=start_row + line_no,
                                        column=1,
                                        value=line
                                    )

                                ok += 1

                                continue
                            def clean_value(x):

                                if pd.isna(x):
                                    return ""

                                if isinstance(x, bytes):

                                    try:
                                        x = x.decode("utf-16-le")

                                    except Exception:

                                        try:
                                            x = x.decode("utf-8")

                                        except Exception:
                                            x = str(x)

                                value = str(x)

                                value = value.replace("\x00", "")

                                value = illegal_chars.sub(
                                    "",
                                    value
                                )

                                return value.strip()

                            for col in df.columns:

                                try:

                                    df[col] = df[col].map(
                                        clean_value
                                    )

                                except Exception:
                                    pass

                            import re
                            # ตัด timezone ออก (openpyxl เขียน datetime ที่มี tz ไม่ได้)
                            for col in df.columns:
                                if isinstance(df[col].dtype, pd.DatetimeTZDtype):
                                    df[col] = df[col].dt.tz_localize(None)
                                elif df[col].dtype == object:
                                    df[col] = df[col].map(
                                        lambda v: illegal_chars.sub('', v) if isinstance(v, str) else v
                                    )

                            total_rows = len(df)
                            if total_rows > max_rows:
                                df = df.iloc[:max_rows]
                                log(f"   ⚠️ Rows เกินขีดจำกัด Excel: export {max_rows:,} จาก {total_rows:,} แถว\n")
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
                                ILLEGAL_CHARACTERS_RE.sub("", str(col))
                                for col in df.columns
                            ]

                            log(f"Writing Sheet: {sheet}\n")
                            log(f"Rows: {len(df)}\n")
                            log(f"Columns: {len(df.columns)}\n")
                            df.to_excel(
                                writer,
                                sheet_name=sheet,
                                index=False
                            )

                            log(f"✅ Sheet Exported: {sheet}\n\n")

                            ws = writer.sheets[sheet]

                            # =====================================
                            # Header Color (มีข้อมูลหรือไม่มีข้อมูลก็ทำงาน)
                            # =====================================

                            header_fill = PatternFill(
                                fill_type="solid",
                                fgColor="BC9BFF"
                            )

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

                                    cell = ws.cell(
                                        row=start_row + line_no,
                                        column=1,
                                        value=line
                                    )

                            except Exception as e:

                                log(
                                    f"Failed to append SQL: {str(e)}\n"
                                )
                            ws.freeze_panes = "A2"
                            thin = Side(
                                border_style="thin",
                                color="000000"
                            )
                            all_border = Border(
                                left=thin,
                                right=thin,
                                top=thin,
                                bottom=thin
                            )
                
                            sample_df = df.head(1000)

                            sample_df = df.head(1000)

                            # ใช้แค่ 1000 แถวแรกในการคำนวณความกว้าง
                            sample_df = df.head(1000)

                            for col_idx, col_name in enumerate(df.columns, 1):

                                letter = openpyxl.utils.get_column_letter(col_idx)

                                max_len = len(str(col_name)) + 2

                                try:

                                    longest_value = (
                                        sample_df[col_name]
                                        .astype(str)
                                        .map(len)
                                        .max()
                                    )

                                    if pd.isna(longest_value):
                                        longest_value = 0

                                    max_len = max(
                                        max_len,
                                        longest_value + 2
                                    )

                                except Exception:
                                    pass

                                ws.column_dimensions[letter].width = min(max_len, 80)
                                
                            # ใส่ Border เฉพาะ Header + Data เท่านั้น
                            data_last_row = max(len(df) + 1, 1)
                            for row in ws.iter_rows(
                                min_row=1,
                                max_row=data_last_row
                            ):
                                data_last_row = max(len(df) + 1, 1)

                            for row in ws.iter_rows(
                                    min_row=1,
                                    max_row=data_last_row
                                ):
                                    for cell in row:
                                        cell.number_format = "@"
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
                            pd.DataFrame({
                                'Status': ['Failed'],
                                'Error': [str(job_err)],
                                'Query': [query]
                            }).to_excel(writer, sheet_name=sheet, index=False)

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
        
        # Re-enable buttons
        self.execute_btn.config(state="normal")
        self.inspect_btn.config(state="normal")
        self.save_job_btn.config(state="normal")
        
    
    def show_critical_error(self, operation, error_msg):
        """Show critical error message when data modification fails"""
        self.results_text.insert(tk.END, f"\n{'='*150}\n")
        self.results_text.insert(tk.END, f"🛑 CRITICAL ERROR - Batch Execution Stopped!\n")
        self.results_text.insert(tk.END, f"{'='*150}\n\n")
        self.results_text.insert(tk.END, f"⚠️ {operation} statement failed!\n")
        self.results_text.insert(tk.END, f"⚠️ Stopping all remaining jobs to prevent data corruption.\n\n")
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
        self.sql_context.insert(1.0, job['query'])
        
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
        
        result = messagebox.askyesno("Confirm Delete",
                                     f"Delete job '{job['name']}'?\n\nThis cannot be undone.")
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
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                # กรอง last_used_profile ออก (ไม่ใช่ profile จริง)
                profiles = {k: dict(v) for k, v in data.items() if k != 'last_used_profile' and isinstance(v, dict)}
                for profile in profiles.values():
                    if 'db_password' in profile:
                        profile['db_password'] = unprotect_password(profile['db_password'])
                return profiles
            except:
                return {}
        return {}

    def _profiles_for_disk(self, last_used_profile=None):
        """สร้างข้อมูลสำหรับเขียนไฟล์ - password ถูกเข้ารหัส, คง last_used_profile เดิมไว้"""
        data = {}
        for name, profile in self.saved_profiles.items():
            profile_copy = dict(profile)
            if profile_copy.get('db_password'):
                profile_copy['db_password'] = protect_password(profile_copy['db_password'])
            data[name] = profile_copy

        if last_used_profile is None:
            last_used_profile = self.get_last_used_profile()
        if last_used_profile and last_used_profile in self.saved_profiles:
            data['last_used_profile'] = last_used_profile
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
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

        except Exception as e:
            error_msg = f"❌ Cannot save profile!\n\nError: {str(e)}\n\nPath: {self.config_file}"
            print(error_msg)
            messagebox.showerror("Save Error", error_msg)

    def save_last_used_profile(self, profile_name):
        """บันทึก profile ล่าสุดที่ใช้"""
        try:
            data = self._profiles_for_disk(last_used_profile=profile_name)

            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Failed to save last used profile: {str(e)}")
    
    def get_last_used_profile(self):
        """ดึง profile ล่าสุดที่ใช้"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                return data.get('last_used_profile', None)
        except:
            pass
        return None
    
    def update_profile_list(self):

        profile_names = list(
            self.saved_profiles.keys()
        )

        self.profile_combo["values"] = profile_names

        if profile_names:
            self.profile_combo.current(0)

        if hasattr(self, "jobs_container"):
            self.update_jobs_list()
    def on_profile_selected(self, event=None):

        profile_name = self.profile_combo.get()

        if (
            profile_name and
            profile_name in self.saved_profiles
        ):
            self.load_profile_data(profile_name)

        self.update_jobs_list()
    
    def load_profile_data(self, profile_name):
        """โหลดข้อมูลจาก profile"""
        try:
            config = self.saved_profiles[profile_name]
            
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
                if ':' in port_value:
                    port_value = port_value.split(':')[0]
                self.db_port.delete(0, tk.END)
                self.db_port.insert(0, port_value)
            if "db_name" in config:
                self.db_name.delete(0, tk.END)
                self.db_name.insert(0, config["db_name"])
            if "sql_query" in config:
                self.sql_context.delete(1.0, tk.END)
                self.sql_context.insert(1.0, config["sql_query"])
            
            self.results_text.insert(
                tk.END,
                f"📂 Loaded profile: {profile_name}\n\n"
            )

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
            ttk.Label(dialog, text="(Existing profiles will be overwritten)",
                     font=('Arial', 8), foreground='gray').pack()
        
        def save():
            profile_name = name_entry.get().strip()
            if not profile_name:
                messagebox.showwarning("Warning", "กรุณาใส่ชื่อ Profile", parent=dialog)
                return
            
            # Clean port before saving
            port_value = self.db_port.get().strip()
            if ':' in port_value:
                port_value = port_value.split(':')[0]
                # Update field with cleaned value
                self.db_port.delete(0, tk.END)
                self.db_port.insert(0, port_value)
            
            # บันทึก settings
            self.saved_profiles[profile_name] = {
                'db_type': self.db_type.get(),
                'db_user': self.db_user.get(),
                'db_password': self.db_password.get(),  # บันทึก password ด้วย
                'db_host': self.db_host.get(),
                'db_port': port_value,  # Use cleaned port value
                'db_name': self.db_name.get(),
                'sql_query': self.sql_context.get(1.0, tk.END).strip()
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
            
            messagebox.showinfo("Success", f"บันทึก Profile '{profile_name}' เรียบร้อย", parent=dialog)
            dialog.destroy()
        
        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(pady=10)
        ttk.Button(btn_frame, text="Save", command=save).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Cancel", command=dialog.destroy).pack(side=tk.LEFT, padx=5)
    
    def delete_profile(self):
        """ลบ profile ที่เลือก"""
        profile_name = self.profile_combo.get()
        if not profile_name:
            messagebox.showwarning("Warning", "กรุณาเลือก Profile ที่ต้องการลบ")
            return
        
        if profile_name not in self.saved_profiles:
            messagebox.showwarning("Warning", "ไม่พบ Profile นี้")
            return
        
        result = messagebox.askyesno("Confirm Delete",
                                     f"ต้องการลบ Profile '{profile_name}' หรือไม่?")
        if result:
            del self.saved_profiles[profile_name]
            self.save_profiles()
            self.update_profile_list()
            self.results_text.insert(tk.END, f"🗑️ Deleted profile: {profile_name}\n\n")
            self.results_text.see(tk.END)
            
            messagebox.showinfo("Success", f"ลบ Profile '{profile_name}' เรียบร้อย")
    
    def _capture_sql_template(self, current_sql):
        current_sql = current_sql.rstrip("\n")
        has_rendered_sql = self._excel_parameterized_sql is not None
        query_was_edited = (
            has_rendered_sql and current_sql != self._excel_parameterized_sql
        ) or (
            not has_rendered_sql and
            self.sql_template is not None and
            current_sql != self.sql_template
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
                formatted_values.append(
                    f"'{escaped_value}'"
                )

        return ", ".join(formatted_values)

    def _render_sql_template(self):
        import re

        rendered_sql = self.sql_template
        for parameter_key, parameter_data in self._excel_parameter_values.items():
            parameter, sql_values = parameter_data
            if parameter_key == "__FIRST_IN_LIST__":
                rendered_sql, replacements = re.subn(
                    r"(\bIN\s*\()\s*[^)]*(\))",
                    lambda match: f"{match.group(1)}{sql_values}{match.group(2)}",
                    rendered_sql,
                    count=1,
                    flags=re.IGNORECASE
                )
                if not replacements:
                    raise ValueError("SQL template no longer contains an IN (...) list")
                continue

            if parameter.startswith(":"):
                token_pattern = r"(?P<quote>['\"]?)" + re.escape(parameter) + r"(?P=quote)"
            else:
                parameter_name = parameter.strip("{}").strip()
                token_pattern = (
                    r"(?P<quote>['\"]?)\{\{?\s*"
                    + re.escape(parameter_name)
                    + r"\s*\}\}?(?P=quote)"
                )
            rendered_sql, replacements = re.subn(
                token_pattern,
                lambda _match: sql_values,
                rendered_sql,
                flags=re.IGNORECASE
            )
            if not replacements:
                raise ValueError(f"Parameter {parameter} is not present in the SQL template")

        return rendered_sql
        
    def reset_single_parameter(self, parameter_key):
        if parameter_key not in self._excel_parameter_values:
            return

        previous_value = self._excel_parameter_values.pop(parameter_key)
        try:
            rendered_sql = (
                self._render_sql_template()
                if self._excel_parameter_values
                else self.sql_template
            )
        except Exception as error:
            self._excel_parameter_values[parameter_key] = previous_value
            messagebox.showerror("Reset Error", str(error))
            return

        self.sql_context.delete("1.0", tk.END)
        self.sql_context.insert("1.0", rendered_sql)
        self._excel_parameterized_sql = (
            rendered_sql if self._excel_parameter_values else None
        )


    def reset_all_parameters(self):
        self._excel_parameter_values.clear()
        self._excel_parameterized_sql = None
        if self.sql_template is not None:
            self.sql_context.delete("1.0", tk.END)
            self.sql_context.insert("1.0", self.sql_template)
        if self.debug_mode.get():
            print("[Excel Parameter Debug] All parameters reset to SQL template")
        messagebox.showinfo(
            "Reset SQL Template",
            "All parameters have been reset."
        )

    def show_reset_parameter_dialog(self, close_after_selected=False, wait=False):
        if not self._excel_parameter_values:
            messagebox.showwarning("Reset Parameter", "No parameter loaded")
            return

        dialog = tk.Toplevel(self.root)
        dialog.title("Reset Parameter")
        dialog.geometry("550x450")
        dialog.transient(self.root)
        dialog.grab_set()

        ttk.Label(
            dialog,
            text="Select parameter to reset",
            font=("Arial", 11, "bold")
        ).pack(pady=(10, 5))

        parameter_list = tk.Listbox(
            dialog,
            font=("Arial", 10),
            selectmode=tk.SINGLE,
            exportselection=False
        )
        parameter_list.pack(fill="both", expand=True, padx=10, pady=10)

        def refresh_parameter_list():
            parameter_list.delete(0, tk.END)
            for parameter_key in self._excel_parameter_values:
                parameter_list.insert(tk.END, parameter_key)

        def reset_selected():
            selection = parameter_list.curselection()
            if not selection:
                messagebox.showwarning(
                    "Reset Parameter",
                    "Please select a parameter",
                    parent=dialog
                )
                return

            parameter_key = parameter_list.get(selection[0])
            self.reset_single_parameter(parameter_key)
            refresh_parameter_list()
            if close_after_selected or not self._excel_parameter_values:
                dialog.destroy()

        def reset_all():
            self.reset_all_parameters()
            dialog.destroy()

        button_frame = ttk.Frame(dialog)
        button_frame.pack(pady=10)
        ttk.Button(
            button_frame,
            text="Reset Selected",
            command=reset_selected
        ).pack(side="left", padx=5)
        ttk.Button(
            button_frame,
            text="Reset All Parameters",
            command=reset_all
        ).pack(side="left", padx=5)

        refresh_parameter_list()

        if wait:
            dialog.wait_window()

    def load_excel_template_dialog(self, wait=False):
        file_path = filedialog.askopenfilename(
            title="Select Excel File",
            filetypes=[("Excel Files", "*.xlsx *.xls")]
        )
        if not file_path:
            return

        try:
            with pd.ExcelFile(file_path) as workbook:
                sheet_names = workbook.sheet_names
            if not sheet_names:
                raise ValueError("Workbook has no worksheets")
            sql_template = self._capture_sql_template(
                self.sql_context.get("1.0", tk.END)
            )
        except Exception as error:
            messagebox.showerror("Excel Import Error", str(error))
            return

        import re

        placeholder_pattern = r"\{\{?\s*[A-Za-z_][A-Za-z0-9_]*\s*\}\}?|:[A-Za-z_][A-Za-z0-9_]*"
        placeholders = list(dict.fromkeys(re.findall(placeholder_pattern, sql_template)))
        parameter_choices = placeholders or ["First IN (...) list"]
        parameter_var = tk.StringVar(value=parameter_choices[0])
        sheet_var = tk.StringVar(value=sheet_names[0])
        sheet_data = {"dataframe": None}
        column_lookup = {}
        self._excel_selected_values = []

        dialog = tk.Toplevel(self.root)
        dialog.title("Load Excel SQL Parameters")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.geometry("540x260")

        content = ttk.Frame(dialog, padding=16)
        content.pack(fill="both", expand=True)
        content.columnconfigure(1, weight=1)

        ttk.Label(content, text="Worksheet").grid(row=0, column=0, sticky="w", pady=6)
        sheet_combo = ttk.Combobox(
            content,
            textvariable=sheet_var,
            values=sheet_names,
            state="readonly"
        )
        sheet_combo.grid(row=0, column=1, sticky="ew", pady=6)

        ttk.Label(content, text="Value column").grid(row=1, column=0, sticky="w", pady=6)
        column_var = tk.StringVar()
        column_combo = ttk.Combobox(content, textvariable=column_var, state="readonly")
        column_combo.grid(
            row=1,
            column=1,
            sticky="ew",
            pady=6
        )

        ttk.Label(content, text="SQL parameter").grid(row=2, column=0, sticky="w", pady=6)
        parameter_combo = ttk.Combobox(
            content,
            textvariable=parameter_var,
            values=parameter_choices,
            state="readonly"
        )
        parameter_combo.grid(row=2, column=1, sticky="ew", pady=6)

        def update_columns(_event=None):

            try:

                dataframe = pd.read_excel(
                    file_path,
                    sheet_name=sheet_var.get()
                )

                sheet_data["dataframe"] = dataframe

                column_lookup.clear()

                column_lookup.update({
                    str(column): column
                    for column in dataframe.columns
                })

                column_names = list(column_lookup.keys())

                column_combo["values"] = column_names
                if column_names:
                    column_var.set(column_names[0])
                else:
                    column_var.set("")

            except Exception as error:

                messagebox.showerror(
                    "Excel Import Error",
                    str(error),
                    parent=dialog
                )

        def preview_excel_column(_event=None):

            dataframe = sheet_data["dataframe"]

            column_name = column_var.get()

            if (
                dataframe is None
                or
                column_name not in column_lookup
            ):
                return

            values = (
                dataframe[
                    column_lookup[column_name]
                ]
                .dropna()
                .tolist()
            )

            selected_values = self.show_excel_value_selector(
                column_name,
                values
            )

            if selected_values:
                self._excel_selected_values = selected_values
        
        def apply_parameters():
            dataframe = sheet_data["dataframe"]
            column_name = column_var.get()
            if dataframe is None or column_name not in column_lookup:
                messagebox.showwarning("Excel Import", "Select a value column", parent=dialog)
                return

            values = self._excel_selected_values

            if not values:

                messagebox.showwarning(
                    "Excel Import",
                    "Please select values first",
                    parent=dialog
                )

                return
            sql_values = self._format_excel_sql_values(values)
            if not sql_values:
                messagebox.showwarning("Excel Import", "Selected column has no values", parent=dialog)
                return

            parameter = parameter_var.get()
            if parameter == "First IN (...) list":
                parameter_key = "__FIRST_IN_LIST__"
                self._excel_parameter_values[parameter_key] = (parameter, sql_values)
            else:
                parameter_key = parameter.lstrip(":").strip("{}").strip().upper()
                self._excel_parameter_values[parameter_key] = (parameter, sql_values)

            try:
                rendered_sql = self._render_sql_template()
            except ValueError as error:
                self._excel_parameter_values.pop(parameter_key, None)
                messagebox.showwarning("SQL Parameter Not Found", str(error), parent=dialog)
                return

            self.sql_context.delete("1.0", tk.END)
            self.sql_context.insert("1.0", rendered_sql)
            self._excel_parameterized_sql = rendered_sql
            self.loaded_excel_data = dataframe
            if self.debug_mode.get():
                print(
                    f"[Excel Parameter Debug] file={os.path.basename(file_path)!r}, "
                    f"sheet={sheet_var.get()!r}, column={column_name!r}, "
                    f"parameter={parameter!r}, values={len(values)}, "
                    f"replaced_parameters={list(self._excel_parameter_values)}"
                )
            messagebox.showinfo(
                "Excel Parameters Loaded",
                f"Loaded {len(values)} values from {column_name} into {parameter}.",
                parent=dialog
            )
            dialog.destroy()

        sheet_combo.bind(
            "<<ComboboxSelected>>",
            update_columns
        )

        column_combo.bind(
            "<<ComboboxSelected>>",
            preview_excel_column
        )

        update_columns()
        button_frame = ttk.Frame(content)
        button_frame.grid(row=3, column=0, columnspan=2, sticky="e", pady=(16, 0))
        ttk.Button(button_frame, text="Replace Parameter", command=apply_parameters).pack(side="left", padx=4)
        ttk.Button(button_frame, text="Cancel", command=dialog.destroy).pack(side="left", padx=4)

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
            dialog,
            text=f"Select Values From Column [{column_name}]",
            font=("Arial", 12, "bold")
        ).pack(pady=10)

        info_label = tk.Label(
            dialog,
            text=f"Selected : 0 / {len(values)}",
            font=("Arial", 10, "bold"),
            fg="blue"
        )
        info_label.pack()

        search_var = tk.StringVar()

        search_frame = tk.Frame(dialog)
        search_frame.pack(fill="x", padx=10, pady=5)

        tk.Label(
            search_frame,
            text="Search"
        ).pack(side="left")

        search_entry = tk.Entry(
            search_frame,
            textvariable=search_var,
            width=50
        )
        search_entry.pack(
            side="left",
            padx=5
        )

        list_frame = tk.Frame(dialog)
        list_frame.pack(
            fill="both",
            expand=True,
            padx=10,
            pady=10
        )

        canvas = tk.Canvas(list_frame)

        scrollbar = tk.Scrollbar(
            list_frame,
            orient="vertical",
            command=canvas.yview
        )

        scrollable_frame = tk.Frame(canvas)

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(
                scrollregion=canvas.bbox("all")
            )
        )

        canvas.create_window(
            (0, 0),
            window=scrollable_frame,
            anchor="nw"
        )

        canvas.configure(
            yscrollcommand=scrollbar.set
        )

        canvas.pack(
            side="left",
            fill="both",
            expand=True
        )

        scrollbar.pack(
            side="right",
            fill="y"
        )

        checkbox_vars = {}

        def update_counter():

            count = sum(
                bool(var.get())
                for var in checkbox_vars.values()
            )

            info_label.config(
                text=f"Selected : {count} / {len(values)}"
            )

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
                    command=update_counter
                ).pack(
                    fill="x",
                    anchor="w"
                )

        def select_all():

            for var in checkbox_vars.values():
                var.set(True)

            update_counter()

        def clear_all():

            for var in checkbox_vars.values():
                var.set(False)

            update_counter()

        def view_selected():

            selected = [
                value
                for value, var
                in checkbox_vars.items()
                if var.get()
            ]

            popup = tk.Toplevel(dialog)
            popup.title("Selected Values")
            popup.geometry("600x500")

            tk.Label(
                popup,
                text=f"Selected Values ({len(selected)})",
                font=("Arial", 12, "bold")
            ).pack(pady=10)

            txt = scrolledtext.ScrolledText(
                popup,
                font=("Consolas", 10)
            )

            txt.pack(
                fill="both",
                expand=True,
                padx=10,
                pady=10
            )

            txt.insert(
                tk.END,
                "\n".join(map(str, selected))
            )

            txt.config(state="disabled")

        def export_selected():

            selected = [
                value
                for value, var
                in checkbox_vars.items()
                if var.get()
            ]

            if not selected:
                messagebox.showwarning(
                    "No Selection",
                    "Please select data first",
                    parent=dialog
                )
                return

            save_path = filedialog.asksaveasfilename(
                defaultextension=".xlsx",
                filetypes=[
                    ("Excel Files", "*.xlsx")
                ]
            )

            if not save_path:
                return

            try:

                pd.DataFrame({
                    column_name: selected
                }).to_excel(
                    save_path,
                    index=False
                )

                messagebox.showinfo(
                    "Export Success",
                    f"Saved {len(selected)} records",
                    parent=dialog
                )

            except Exception as error:

                messagebox.showerror(
                    "Export Error",
                    str(error),
                    parent=dialog
                )

        def confirm_selection():

            selected_values.clear()

            selected_values.extend(
                [
                    value
                    for value, var
                    in checkbox_vars.items()
                    if var.get()
                ]
            )

            if not selected_values:

                messagebox.showwarning(
                    "No Selection",
                    "Please select at least 1 value",
                    parent=dialog
                )

                return

            dialog.destroy()

        search_var.trace_add(
            "write",
            lambda *args: refresh_list()
        )

        refresh_list()

        button_frame = tk.Frame(dialog)
        button_frame.pack(
            pady=10
        )

        tk.Button(
            button_frame,
            text="View Selected",
            bg="#3498db",
            fg="white",
            command=view_selected
        ).pack(
            side="left",
            padx=5
        )

        tk.Button(
            button_frame,
            text="Select All",
            bg="#27ae60",
            fg="white",
            command=select_all
        ).pack(
            side="left",
            padx=5
        )

        tk.Button(
            button_frame,
            text="Clear All",
            bg="#e74c3c",
            fg="white",
            command=clear_all
        ).pack(
            side="left",
            padx=5
        )

        tk.Button(
            button_frame,
            text="Export Selected",
            bg="#8e44ad",
            fg="white",
            command=export_selected
        ).pack(
            side="left",
            padx=5
        )

        tk.Button(
            button_frame,
            text="Confirm",
            bg="#2ecc71",
            fg="white",
            command=confirm_selection
        ).pack(
            side="left",
            padx=5
        )

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
    root.state('zoomed')
    root.mainloop()


if __name__ == "__main__":
    main()

