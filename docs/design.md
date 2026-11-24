# Design — Bugfix C1, C2, H1, H2

> อ้างอิง: `docs/spec.md` (อนุมัติแล้ว, AC-1 ถึง AC-38, การตัดสินใจ Q1-Q8)
> ไฟล์ที่แก้: `database_connect_gui.py`, `README.md` (บรรทัด 47, 51) และ test ใหม่ใน `tests/`
> เลขบรรทัดอ้างอิงโค้ดบน branch `ui/remove-duplicate-buttons` ณ วันที่เขียน (อาจเลื่อนเมื่อแก้ทีละ task)

---

## 1. ภาพรวมแนวทาง

แก้ 4 บัคด้วยกลไกกลาง 4 อย่าง และไม่ refactor ส่วนอื่น:

| กลไก | แก้บัค | สรุป |
|---|---|---|
| **A. Busy check กลาง** `_is_busy()` + `_block_if_busy(action)` | C1, H1, H2 | จุดเดียวที่ตอบว่า "มีงานรันอยู่" ตามนิยามใน spec ทุกทางเข้าที่เริ่มงาน/สลับฐานข้อมูลเรียก `_block_if_busy` บรรทัดแรก ถ้าบล็อกจะเขียนเหตุผลลง Execution Logs (ไม่มี popup) |
| **B. UI lock** `_apply_run_lock(busy)` | C1 (Q2) | ปิด/เปิดปุ่มตามสถานะ busy เรียกจาก poll เดิม `_refresh_stop_buttons` (ทุก 300 ms) |
| **C. Run target snapshot** `ConnectionInfo` + `RunTarget` | C1 (Q5, Q6) | ตอน Connect สำเร็จเก็บ engine คู่กับข้อมูลปลายทาง (ไม่มีรหัสผ่าน) ทุกงานจับ `RunTarget` ครั้งเดียวตอนเริ่ม แล้วส่ง engine ตัวนั้นให้ worker, หน้ายืนยัน และ Run log |
| **D. Script Groups save-block + backup ครั้งแรกของเซสชัน** | C2 (Q4) | ใช้ `_handle_unreadable_file` เดิม + flag `_script_groups_save_blocked` + เขียนด้วย `write_json_atomic` |

H1 แก้ด้วยการให้ banner/status bar/Stop ใช้ `_is_busy()` และแยกข้อความ banner เป็นเมธอด ส่วน H2 ย้าย lambda ของ `<Control-Return>` เป็นเมธอดที่เทียบ state ด้วย `str()`

### เหตุผลที่เลือก

- **บล็อกที่ทางเข้า + ปิดปุ่ม (ไม่ใช่ lock/queue)**: Q1 ห้ามงานซ้อนทุกประเภท จึงพอแค่ตรวจที่ทางเข้า ปุ่มที่ถูกปิดเป็นแค่ด่านแรก ทางเข้าอื่น (shortcut, Retry ของ Connection Error, ปุ่ม Retry ใน Loading, callback ที่ค้างอยู่) ถูกจับด้วย `_block_if_busy` อีกชั้น
- **Snapshot แยกจาก `engine.url`**: spec ข้อ 5 ระบุว่า URL ของ SQL Server ไม่มี host และมีรหัสผ่านใน `odbc_connect` จึงเก็บค่าที่อ่านจากช่องตอน Connect สำเร็จ ผูกกับ engine ตัวนั้น
- **ยังคงมี `self.engine`**: โค้ดเดิมหลายจุดอ่าน `self.engine` (เช็ค "connected", `_reuse_last_run_results`, Script Groups ฯลฯ) จึงเพิ่ม `self._run_target` คู่กัน ไม่เปลี่ยนความหมายของ `self.engine`
- **UI lock แบบคำนวณ state จากสถานะปัจจุบันทุก poll (stateless)**: ไม่ต้องจำว่าใครปิดปุ่ม ปุ่มที่มีเงื่อนไขของตัวเองส่ง callable บอก state ตอนว่าง
- **list_tables เลือกวิธี "เพิ่มปุ่ม Stop ในหน้าต่าง Loading" (Q7)**: คง `grab_set()` ไว้เหมือนเดิม ผู้ใช้ยังกดอย่างอื่นในหน้าต่างหลักไม่ได้ระหว่างโหลด (พฤติกรรมเดิม) แค่เพิ่มทางกด Stop ทดสอบได้ตาม AC-38 ทางเลือก "มีปุ่ม Stop ลงทะเบียนผ่าน `_register_stop_button`"
- **แยก logic เป็นเมธอดเล็กที่ไม่แตะ Tk** เพื่อให้ test ใช้ stub (`DatabaseConnectorGUI.__new__` หรือ `type("Stub", (), {})()`) ได้ตาม spec ข้อ 5

---

## 2. Data model ใหม่ (module level)

วางต่อจาก `class SqlAssessment` (~บรรทัด 250) เพิ่ม `from typing import Any, Callable, Optional` ที่ส่วน import (ไม่ใช้ syntax `X | None` เพื่อไม่ผูกกับ Python 3.10+)

```python
@dataclass(frozen=True)
class ConnectionInfo:
    """Where a connected engine points. Never holds the password."""
    profile: str
    db_type: str
    user: str
    host: str
    port: str
    database: str

    def target_label(self) -> str:
        """Confirm dialog format (unchanged): 'Oracle · host1 / SVC'.

        No host -> db_type only; no database -> 'Oracle · host1'.
        """

    def log_target(self) -> str:
        """Run log format (unchanged): 'user@host:port/database'
        (':port' and '/database' only when set)."""

    def run_log_header(self) -> str:
        """'\\n===== RUN  profile=<profile or ->  <db_type>  <log_target> =====\\n'"""


@dataclass(frozen=True)
class RunTarget:
    """Engine + its ConnectionInfo, captured once when a run starts."""
    engine: Any
    info: Optional[ConnectionInfo]  # None only for engines set without connect_database (tests)
```

- ห้ามมี field รหัสผ่าน หรือ connection string / URL ใน 2 class นี้
- รูปแบบข้อความต้องเหมือนโค้ดเดิมทุกตัวอักษร (`_confirm_data_change` 7477-7481, `_log_run_context` 7386-7394) แค่เปลี่ยนแหล่งข้อมูล

### Attribute ใหม่บน `DatabaseConnectorGUI`

| Attribute | Type | ตั้งที่ | ความหมาย |
|---|---|---|---|
| `_run_target` | `Optional[RunTarget]` | `_replace_engine`, `_reset_profile_connection_state` | engine ปัจจุบัน + ข้อมูลปลายทางตอน Connect สำเร็จ |
| `_active_profile` | `str` | `load_profile_data` (สำเร็จ), `save_profile_dialog.save()` | ชื่อ Profile ที่โหลดอยู่ ใช้คืนค่า combobox เมื่อถูกบล็อก |
| `_profile_action_buttons` | `list` | `__init__` (ลูป Import/Save/New ~2085) | ปุ่ม Import / Save / ＋ New (ไม่รวม Export profile) |
| `_profile_menu` | `tk.Menu` | `__init__` (`more_menu` ~2073) | เมนู ⋯ ซึ่ง index 0 คือ "Delete profile" |
| `_job_run_buttons` | `list` | `update_jobs_list` (reset ทุกครั้งที่ rebuild) | ปุ่ม ▶ ของทุกการ์ด |
| `_run_lock_extra` | `list[tuple[widget, Callable[[], str]]]` | `_register_run_lock_button` | ปุ่มในหน้าต่างอื่น (Run Group / Export Group) + state ตอนว่าง |
| `_script_groups_save_blocked` | `bool` | `load_script_groups` | True = ห้ามเขียน `script_groups.json` ในเซสชันนี้ |
| `_script_groups_backup_done` | `bool` | `save_script_groups` | True = เซสชันนี้ผ่านการบันทึกครั้งแรกแล้ว (ไม่ backup ซ้ำ) |

ทุกตัวอ่านด้วย `getattr(self, name, default)` เพื่อให้ stub ใน test ไม่ต้องตั้งครบ

---

## 3. A — Busy check กลาง (C1, H1, H2)

```python
def _is_busy(self) -> bool:
    """A run is in progress (spec section 4 definition):
    _is_query_running() or _running_job_ids not empty or inspect_btn shows 'Loading'."""

def _log_blocked(self, action: str) -> None:
    """Write why `action` was refused to Execution Logs (results_text). No popup."""

def _block_if_busy(self, action: str) -> bool:
    """True (and _log_blocked(action)) when _is_busy(); False otherwise."""
```

- `_is_query_running()` (7312) **คงไว้ตามเดิม** ไม่เปลี่ยนความหมาย (ใช้ใน `_reset_profile_connection_state`)
- `_is_busy` อ่าน `self._running_job_ids` ด้วย `getattr(..., None)` และ `self.inspect_btn.cget("text")`
- ข้อความที่ `_log_blocked` เขียน (ขึ้นบรรทัดใหม่ท้าย แล้ว `results_text.see(tk.END)`):
  `⏳ {action}: ทำไม่ได้ระหว่างที่มีงานรันอยู่ — รอให้งานเสร็จหรือกด ⏹ Stop ก่อน\n`
- `_log_blocked` ห้ามเรียก `messagebox` / `ui_dialog`
- test fake ของ `results_text` ต้องมี `insert` และ `see` (`_FakeText` เดิมไม่มี `see` QA เพิ่มเองใน test ใหม่)

### จุดที่เรียก `_block_if_busy` (บรรทัดแรกของเมธอด ก่อน popup/file dialog/การแก้ช่องใด ๆ)

| เมธอด | action ที่ log | หมายเหตุ |
|---|---|---|
| `connect_database` (6987) | `"Connect"` | ก่อนบรรทัด 6994 ที่แก้ช่อง port ครอบคลุม Retry ของ `_show_connection_error` (7107) |
| `on_profile_selected` (9982) | `"เปลี่ยน Profile"` | ถ้าบล็อก: `profile_combo.set(self._active_profile)` แล้ว return ห้ามเรียก `load_profile_data` และ `update_jobs_list` |
| `import_profiles_dialog` (3012) | `"Import Profile"` | ก่อน `filedialog` |
| `delete_profile` (10439) | `"ลบ Profile"` | ก่อน `askyesno` |
| `save_profile_dialog` (10094) | `"บันทึก Profile"` | ก่อนสร้าง Toplevel |
| `new_profile_dialog` (10174) | `"สร้าง Profile"` | ก่อนสร้าง dialog |
| `execute_query` (7537) | `"Run"` | ก่อนเช็ค engine และก่อน `results_text.delete` (ไม่ให้ข้อความถูกลบ) ครอบคลุม Ctrl+Enter และปุ่ม Retry ใน Loading |
| `run_job` (8834) | `"Run Job"` | แทนที่ 2 เช็คเดิม (`_batch_running` 8849-8854 และ `id(job) in running_jobs` 8857-8862) เพราะ `_is_busy` ครอบคลุมทั้งคู่ |
| `run_selected_job` (8949) | `"Run all"` | บรรทัดแรก ก่อนตั้ง `run_index` และก่อน popup "No jobs to run" ลบเช็ค `_batch_running` เดิม (8977) |
| `export_jobs_to_excel` (9388) | `"Export"` | ก่อนเช็ค engine / openpyxl / file dialog |
| `list_tables` (8273) | `"Tables"` | ก่อนเช็ค engine (Q1 ห้ามเริ่มงานใหม่ทุกประเภท) |

### จุดที่ต้องแก้ร่วม

- **wrapper `_ui_run_selected_job` (2810)**: ปัจจุบัน reset `self._ui_progress` ก่อนเรียกของเดิม ถ้าถูกบล็อก banner ของ Run All ที่รันอยู่จะเพี้ยน → ต้องเช็ค `if self._is_busy(): return _orig_run_selected_job(jobs_override)` (ของเดิมจะ log แล้ว return) ก่อน reset progress
- **`run_group` ใน Script Groups (4549)**: ลบเช็ค `_batch_running` + `messagebox.showinfo` (4556-4558) เพราะ `run_selected_job` บล็อกและ log เอง (Q2 ไม่ใช้ popup) เช็ค engine เดิมคงไว้
- `update_profile_list` (9957) **ไม่ต้องใส่ guard**: ผู้เรียกทุกตัว (import 3280, save 10156, new 10408, delete 10456, `__init__` 2046) ถูกบล็อกแล้ว หรือรันก่อนมีงาน
- ไม่ต้องเช็คซ้ำใน callback `save()` / `create()` ของ dialog Profile: dialog เหล่านี้ `grab_set()` ระหว่างเปิดจึงเริ่มงานใหม่ไม่ได้ และเปิดไม่ได้ระหว่างมีงาน

### `_active_profile`

- `load_profile_data`: ตั้ง `self._active_profile = profile_name` หลังโหลดสำเร็จ (ก่อน `results_text.insert` 10070)
- `save_profile_dialog.save()`: ตั้ง `self._active_profile = profile_name` หลัง `profile_combo.current(...)` (10159)
- `on_profile_selected` ที่ถูกบล็อกใช้ `getattr(self, "_active_profile", "")`

---

## 4. B — UI lock (C1, Q2)

```python
def _register_run_lock_button(self, button, idle_state: Callable[[], str]) -> None:
    """Lock `button` while a run is in progress; idle_state() gives its state when idle."""

def _apply_run_lock(self, busy: bool) -> None:
    """Set every run/connect/profile control to disabled while busy, else its idle state."""

@staticmethod
def _set_widget_state(widget, state: str) -> bool:
    """config(state=...) only when str(widget.cget('state')) differs.
    Returns False when the widget is gone (TclError)."""
```

### Widget และ state ตอนว่าง (`busy=False`)

| Widget | busy=True | busy=False |
|---|---|---|
| `connect_btn` | disabled | normal |
| `profile_combo` | disabled | **readonly** (state เดิมตอนสร้าง 2043 ห้ามเป็น normal เพราะจะพิมพ์ได้) |
| `_profile_action_buttons` (Import / Save / ＋ New) | disabled | normal |
| `_profile_menu` entry index 0 ("Delete profile") | `entryconfig(0, state="disabled")` | `entryconfig(0, state="normal")` |
| `execute_btn` | disabled | normal ถ้า `self.engine is not None` มิฉะนั้น disabled |
| `inspect_btn` | disabled | normal ถ้า `self.engine is not None` มิฉะนั้น disabled |
| `run_all_btn` | disabled | normal |
| `export_excel_btn` | disabled | normal |
| `_job_run_buttons` (▶ ทุกการ์ด) | disabled | normal |
| `_run_lock_extra` (Run Group / Export Group) | disabled | `idle_state()` |

- ปุ่มใน list แบบ dynamic (`_job_run_buttons`, `_run_lock_extra`) ถ้า widget ถูกทำลายแล้ว (`_set_widget_state` คืน False หรือ `winfo_exists()` เป็น False) ให้ตัดทิ้งจาก list
- ปุ่ม Export Profile, ⋯ (more_btn ซึ่งมี "Config file location"), Save as Job ไม่อยู่ใน lock (ไม่อยู่ใน AC-13)
- โปรโตคอลของ fake widget ใน test: `cget("state")`, `config(state=...)`, `winfo_exists()`; fake menu: `entryconfig(index, **kw)`

### จุดที่เรียก

- `_refresh_stop_buttons` (7436): คำนวณ `busy = self._is_busy()` ครั้งเดียว ใช้ทั้ง state ของปุ่ม Stop (ดูข้อ 7) และเรียก `self._apply_run_lock(busy)` ก่อน reschedule
- เก็บ widget ใน `__init__`: `self._profile_menu = more_menu` และ `self._profile_action_buttons.append(_b)` สำหรับ Import / Save / ＋ New ในลูป 2085-2092 (`self._profile_action_buttons = []` ก่อนลูป)
- `update_jobs_list` (3487): ตั้ง `self._job_run_buttons = []` ก่อนสร้างการ์ด และ append ปุ่มที่ `kind == "run"` (ลูป 3578-3585)
- Script Groups (4753-4754): หลังสร้าง `run_btn`, `export_btn` เรียก `self._register_run_lock_button(btn, lambda: "normal" if <group ปัจจุบันมี scripts> else "disabled")` และใน `update_buttons` (4399-4400) เปลี่ยนเป็น `set_enabled(btn, has_scripts and not self._is_busy())` เพื่อไม่ให้การเลือกกลุ่มเปิดปุ่มระหว่างรัน

### ความสัมพันธ์กับโค้ดเดิมที่ตั้ง state เอง

โค้ดเดิมปิด/เปิด `execute_btn`, `inspect_btn`, `run_all_btn`, `export_excel_btn` เองตอนเริ่ม/จบงาน (เช่น 7565, 8892, 8991, 9228-9232, 9441, 9453) **คงไว้ทั้งหมด** เพราะสอดคล้องกัน: ระหว่างรัน `_is_busy()` เป็น True lock จึงปิดเหมือนกัน หลังงานจบ โค้ดเดิมเปิดคืน และ lock ให้ผลเดียวกัน (ยกเว้น Run / Tables เมื่อไม่มี engine ซึ่ง lock จะปิดไว้ ถูกต้องตาม AC-31)

---

## 5. C — Run target snapshot (C1, Q5, Q6)

### การสร้างและล้าง snapshot

```python
def _replace_engine(self, engine, info: Optional[ConnectionInfo] = None) -> None:
    """Make `engine` current, remember its ConnectionInfo, dispose the old pool.
    engine None -> _run_target None."""

def _capture_run_target(self) -> Optional[RunTarget]:
    """Main thread, once per run: self._run_target if it belongs to self.engine;
    RunTarget(self.engine, None) if engine has no info; None if not connected."""
```

- `connect_database` (6987): ค่าที่อ่านจากช่องมีอยู่แล้วที่ 6988-6993 หลัง Connect สำเร็จสร้าง
  `ConnectionInfo(profile=self.profile_combo.get() or "", db_type=db_type, user=user.strip(), host=host.strip(), port=port, database=database.strip())`
  แล้วเรียก `self._replace_engine(engine, info)` (แทน 7041) ห้ามส่ง `password`
- กรณี Connect ล้มเหลว `self._replace_engine(None)` (7032) ทำให้ `_run_target = None` อยู่แล้ว
- `_reset_profile_connection_state` (10022): ตอนตั้ง `self.engine = None` ให้ตั้ง `self._run_target = None` ด้วย
- `_capture_run_target` ตรวจ `self._run_target.engine is self.engine` ถ้าไม่ตรง (เช่น test ตั้ง `stub.engine` เอง) คืน `RunTarget(self.engine, None)`

### การส่ง engine ให้ worker (AC-7, AC-8, AC-9)

```python
def read_sql_dataframe(self, sql_query: str, engine: Any = None) -> pd.DataFrame:
    """engine None -> self.engine (backward compatible)."""

def _execute_modification(self, sql_query: str, engine: Any = None) -> int:
    """engine None -> self.engine (backward compatible)."""

def _execute_query_background(self, sql_query: str, loading_dialog, engine: Any = None) -> None:
```

- ใน `read_sql_dataframe` ทุกจุดที่ใช้ `self.engine` (7122, 7127) ใช้ตัวแปร local `engine` แทน ใน `_execute_modification` (7175) เช่นกัน
- ทุกงานจับ `target = self._capture_run_target()` **บน main thread ครั้งเดียว** หลังผ่าน guard/เช็ค engine และ **ก่อน** `_confirm_data_change` แล้วใช้ `target` ตัวเดียวกันกับหน้ายืนยัน, Run log และ worker:

| งาน | จับ target ที่ | worker ใช้ |
|---|---|---|
| SQL Editor `execute_query` | ก่อน `_confirm_data_change` (7554) | ส่ง `engine=target.engine` ให้ `_execute_query_background` → `read_sql_dataframe(..., engine=engine)` / `_execute_modification(..., engine=engine)` (6219, 6231) และ debug print 6210 ใช้ `engine.dialect.name` |
| Job เดี่ยว `run_job` | ก่อน `_confirm_data_change` (8868) | `run_in_background` (8932, 8935) |
| Run All / Run Group `run_selected_job` | ก่อน `_confirm_data_change` (8985) | `run_all_jobs` (9040, 9074) |
| Export `export_jobs_to_excel` | ก่อน `_reuse_last_run_results` (9427) | `worker` (9558) |
| `list_tables` | หลังเช็ค engine (8275) | `fetch_tables_in_background`: ทุก `self.engine` (8322, 8378, 8494) ใช้ `target.engine` และ `db_type` ใช้ `target.info.db_type` ถ้ามี info (fallback `self.db_type.get()` อ่านบน main thread ก่อนเริ่ม thread) |

- worker ห้ามอ่าน `self.engine` หรือ `self._run_target` ระหว่างรัน (AC-9)
- `_start_stoppable_run(self, target: Optional[RunTarget] = None)` ส่ง `target` ต่อให้ `_log_run_context(target)`
- list_tables: ส่วนสร้าง `temp_engine` ต่อ database (8393-8400) ซึ่งอ่าน user/password/host/port จากช่องบนหน้าจอ **คงไว้ตามเดิม** (ดูความเสี่ยงข้อ R4)

### หน้ายืนยันและ Run log (AC-10, AC-11, AC-35)

```python
def _confirm_destination(self, target: Optional[RunTarget]) -> tuple[str, str]:
    """(profile, database label) for the confirm dialog, from the run's
    ConnectionInfo — never from the screen fields. No info -> ('-', '-')."""

def _confirm_data_change(self, jobs: list[dict], target: Optional[RunTarget] = None) -> bool:
    """target None -> self._capture_run_target()."""

def _log_run_context(self, target: Optional[RunTarget] = None) -> None:
    """Write target.info.run_log_header() via _write_run_log.
    target None -> _capture_run_target(); no info -> header with '-' values."""
```

- `_confirm_data_change`: แทน 7477-7481 และ 7491 ด้วย `profile, target_text = self._confirm_destination(target)` (เปลี่ยนชื่อตัวแปร local `target` เดิมเป็น `target_text` เพื่อไม่ชนกับ parameter) ส่วนอื่นของ dialog ไม่เปลี่ยน
- `_log_run_context`: ไม่อ่าน `db_user/db_host/db_port/db_name/db_type/profile_combo` อีก ไม่ต้องมี `try/except tk.TclError`
- ผู้เรียกทุกตัวในข้อ 5 ส่ง `target=target` ให้ `_confirm_data_change` และ `_start_stoppable_run`

---

## 6. D — Script Groups (C2, Q4)

### `load_script_groups` (3950)

```python
def load_script_groups(self) -> list[dict]:
```
- ไม่มีไฟล์ → คืน `[]` ไม่ตั้ง flag ไม่เตือน (AC-18)
- อ่าน/parse ไม่ได้ (`except Exception as e`) → `self._script_groups_save_blocked = self._handle_unreadable_file(path, "Script Groups", e)` แล้วคืน `[]` (แทน `messagebox.showerror` เดิมที่ 3960) — `_handle_unreadable_file` แสดง warning และสร้าง `script_groups_unreadable_<เวลา>.json` เอง (AC-14)
- อ่านได้ → เหมือนเดิม

### `save_script_groups` (3963)

```python
def save_script_groups(self) -> None:

def _backup_script_groups_once(self, path: str) -> None:
    """First save of the session only: copy `path` to <name>_backup.json when it
    exists and is readable JSON. Marks the session as done either way."""
```

ลำดับ:
1. ถ้า `getattr(self, "_script_groups_save_blocked", False)` → `messagebox.showerror("Script Groups", "script_groups.json could not be read when the app started, so it is not overwritten. Restart the app to load your groups again.")` แล้ว return ไม่แตะไฟล์ใด (AC-15, popup ได้ตาม spec)
2. สร้าง `clean` เหมือนเดิม (ตัด key ที่ขึ้นต้น `_` และ `run_index`)
3. ใน `try`: ถ้า `not getattr(self, "_script_groups_backup_done", False)` → `self._backup_script_groups_once(path)`
4. `write_json_atomic(path, {"version": 1, "groups": clean}, indent=2)` (แทน tmp-file เขียนเอง 3979-3982; ไม่ทิ้ง `.tmp` AC-19)
5. `except Exception` → `messagebox.showerror` เดิม

`_backup_script_groups_once`:
- ตั้ง `self._script_groups_backup_done = True` เสมอ (ครั้งแรกของเซสชันจบแล้วไม่ว่าผลเป็นอย่างไร)
- ถ้า `os.path.exists(path)` และ `json.load` ไฟล์ได้ → `shutil.copy2(path, os.path.splitext(path)[0] + "_backup.json")`
- ไฟล์เสีย → ไม่ copy (backup เดิมคงอยู่ AC-16) / ไม่มีไฟล์ → ไม่สร้าง backup (AC-18)

ผลตาม AC: AC-17 (บันทึก 2 ครั้ง backup ยังเป็น G1), AC-36 (stub ใหม่ = เซสชันใหม่ → backup ถูกอัปเดต)

---

## 7. H1 — Banner, status bar, Stop

```python
def _running_banner_state(self, elapsed_seconds: int) -> tuple[str, Optional[float]]:
    """Text of the yellow banner and the determinate progress (0-100),
    or None for an indeterminate bar. Reads only flags/button text — no Tk calls
    other than cget."""
```

กติกาข้อความ (`clock = f"{m:02d}:{s:02d}"`):

| ลำดับ | เงื่อนไข | ข้อความ | progress |
|---|---|---|---|
| 1 | `_batch_running` และ `_ui_progress["total"]` | เดิม: `กำลังรัน Job {i} / {N}[ · name] · {clock}` | `100 * max(index-1, 0) / total` |
| 2 | `export_excel_btn` แสดง "Exporting" | เดิม: `กำลัง Export Excel · {clock}` | None |
| 3 | `_running_job_ids` ไม่ว่าง และ `_ui_progress["kind"] == "job"` | ใหม่: `กำลังรัน Job · {name} · {clock}` (ไม่มีชื่อ → `กำลังรัน Job · {clock}`) | None |
| 4 | อื่น ๆ (SQL Editor, list_tables) | เดิม: `กำลังรัน SQL · {clock}` | None |

- `run_job`: หลัง `running_jobs.add(id(job))` ตั้ง `self._ui_progress = {"total": 0, "index": 0, "name": job.get("name", ""), "kind": "job"}`
- `_refresh_live_ui` (2846-2849): `busy = self._is_busy()` แทน 3 flag เดิม และส่วน banner (2857-2874) เรียก `self._running_banner_state(elapsed)` แล้วตั้งโหมด progress ตามค่าที่คืน (float → determinate + value, None → indeterminate + start) การ pack/forget banner และ status bar "Running…" ใช้ `busy` เดิม
- `_refresh_stop_buttons` (7439) และ guard ใน `stop_running_queries` (7407) ใช้ `self._is_busy()` แทน `_is_query_running()` → Stop กดได้ทุกครั้งที่ busy รวม list_tables (วิธี cancel ของ driver ไม่เปลี่ยน)

### list_tables Loading window (Q7)

```python
def _create_list_tables_loading_dialog(self) -> "tk.Toplevel":
    """The 'Loading Tables...' window (code moved from 8289-8307) plus a
    ⏹ Stop button: ui_rbutton(dialog, '⏹  Stop', self.stop_running_queries, 'danger', 'sm')
    registered with self._register_stop_button(button)."""
```
- ย้ายโค้ดสร้าง Toplevel/Label/Progressbar 8289-8307 มาไว้ในเมธอดนี้ คง `grab_set()` ไว้ เพิ่มปุ่ม Stop ใต้ progress bar
- `list_tables` เรียกเมธอดนี้แทนโค้ดเดิม ส่วนอื่นไม่เปลี่ยน ปุ่มปิด/เปิดเองผ่าน poll `_refresh_stop_buttons` (disabled ตอนลงทะเบียน → normal ภายใน 300 ms เพราะ `inspect_btn` แสดง Loading)
- ปุ่มถูกตัดออกจาก `_stop_buttons` อัตโนมัติเมื่อหน้าต่างปิด (`winfo_exists`) — `on_list_tables_success/error` ปิดหน้าต่างเหมือนเดิม
- test (AC-38) patch `app.tk.Toplevel`, `app.ttk.Label`, `app.ttk.Progressbar`, `app.ui_rbutton` ด้วย `MagicMock` แล้วตรวจว่า `ui_rbutton` ถูกเรียกด้วย command `stub.stop_running_queries` และ `_register_stop_button` ได้ปุ่มนั้น

---

## 8. H2 — Ctrl+Enter

```python
def _on_sql_ctrl_enter(self, _event=None) -> None:
    """Ctrl+Enter = Run button: does nothing while Run is disabled
    (logs the reason when a run is in progress)."""
```
- `if str(self.execute_btn["state"]) == "disabled":` → ถ้า `self._is_busy()` ให้ `self._log_blocked("Run")` แล้ว return; มิฉะนั้น `self.execute_query()`
- binding (2660-2665) เปลี่ยนเป็น `self.sql_context.bind("<Control-Return>", self._on_sql_ctrl_enter)`
- คืน `None` เหมือน lambda เดิม (ไม่เปลี่ยนพฤติกรรมการพิมพ์ของ Text widget)

---

## 9. ไฟล์และเมธอดที่แตะ (สรุป)

| ไฟล์ | ส่วน | การเปลี่ยน |
|---|---|---|
| `database_connect_gui.py` | import | `from typing import Any, Callable, Optional` |
| | module (~250) | `ConnectionInfo`, `RunTarget` |
| | `__init__` UI (2073-2092, 2660-2665, 2810-2818, 2846-2874) | เก็บ `_profile_menu` / `_profile_action_buttons`, binding Ctrl+Enter, wrapper run_selected_job, `_refresh_live_ui` |
| | `update_jobs_list` (3487) | `_job_run_buttons` |
| | Script Groups (3950-3984, 4399, 4549-4559, 4753) | C2 + lock ปุ่ม Run/Export Group + ลบ popup ใน `run_group` |
| | `import_profiles_dialog`, `save_profile_dialog`, `new_profile_dialog`, `delete_profile`, `on_profile_selected`, `load_profile_data`, `_reset_profile_connection_state` | guard + `_active_profile` + ล้าง `_run_target` |
| | `connect_database`, `_replace_engine` | guard + snapshot |
| | `read_sql_dataframe`, `_execute_modification`, `_execute_query_background` | parameter `engine` |
| | `_start_stoppable_run`, `_log_run_context`, `_confirm_data_change` | ใช้ `RunTarget` |
| | `execute_query`, `run_job`, `run_selected_job`, `export_jobs_to_excel`, `list_tables` | guard + จับ target + ส่ง engine |
| | `stop_running_queries`, `_refresh_stop_buttons` | `_is_busy` + `_apply_run_lock` |
| | เมธอดใหม่ | `_is_busy`, `_log_blocked`, `_block_if_busy`, `_on_sql_ctrl_enter`, `_register_run_lock_button`, `_apply_run_lock`, `_set_widget_state`, `_capture_run_target`, `_confirm_destination`, `_backup_script_groups_once`, `_running_banner_state`, `_create_list_tables_loading_dialog` |
| `README.md` | บรรทัด 47, 51 (+ 1 บรรทัดเรื่องห้าม Connect/เปลี่ยน Profile/เริ่มงานอื่นระหว่างรัน) | AC-26 |
| `tests/` | ไฟล์ test ใหม่ (qa-tester เป็นผู้เขียน) | AC แบบ unittest |

ไม่แก้: `_create_loading_dialog_with_retry` (6122/6129, out of scope), วิธี cancel ใน `stop_running_queries`, หน้า New/Edit Profile ทดสอบเชื่อมต่อ, `show_batch_summary` (`"engine": self.engine` ยังถูกต้องเพราะ Connect ถูกบล็อกระหว่างรัน)

---

## 10. ความเสี่ยงและผลกระทบ

| # | ความเสี่ยง | ผลกระทบ / การลด |
|---|---|---|
| R1 | UI lock ตั้ง state ทุก 300 ms อาจชนกับโค้ดที่ตั้ง state ปุ่มเอง | ใช้กับ widget ในตารางข้อ 4 เท่านั้น และค่าที่ตั้งตรงกับโค้ดเดิมในทุกสถานะ ปุ่มที่มีเงื่อนไขของตัวเอง (Run Group) ใช้ `idle_state` |
| R2 | ช่วง ≤300 ms หลังเริ่มงานที่ปุ่มยังไม่เทา | ทุกทางเข้ามี `_block_if_busy` อยู่แล้ว กดซ้ำได้แค่ข้อความใน Execution Logs |
| R3 | wrapper `_ui_run_selected_job` reset progress ก่อนถูกบล็อก | แก้ในข้อ 3 (เช็ค busy ก่อน reset) |
| R4 | list_tables (ไม่ระบุ database, ไม่ใช่ Oracle) สร้าง `temp_engine` จากช่อง user/password/host/port ใน worker thread ซึ่งอาจไม่ตรงกับ engine ที่ Connect ไว้ ถ้าผู้ใช้แก้ช่องหลัง Connect | **อยู่นอก spec** ไม่แก้ในงานนี้ — แจ้งหัวหน้า |
| R5 | กด Stop ระหว่าง list_tables บน PostgreSQL / MySQL / SQL Server ยกเลิก query ไม่ได้ (driver) และ worker ไม่เช็ค `_stop_event` | ตรงกับพฤติกรรมเดิมของ Stop (spec ไม่ให้เปลี่ยนวิธี cancel) README ระบุข้อจำกัดนี้อยู่แล้ว |
| R6 | `load_script_groups` ที่ไฟล์เป็น JSON ถูกต้องแต่โครงสร้างผิด (เช่น `"groups"` เป็น dict) ยังคืน `[]` แบบเงียบโดยไม่บล็อกการบันทึก | spec AC-14 ครอบคลุมเฉพาะ JSON เสีย — **แจ้งหัวหน้า** ไม่ได้ออกแบบเพิ่ม |
| R7 | `RunTarget.info` เป็น None (engine ที่ไม่ได้มาจาก `connect_database`) หน้ายืนยัน/Run log จะแสดง `-` | ในแอปจริงทุก engine มาจาก `connect_database` เกิดเฉพาะใน test |
| R8 | Loading ของ SQL Editor (`_create_loading_dialog_with_retry` 6129) ยัง `grab_set()` จึงกด Stop ในหน้าต่างหลักไม่ได้ระหว่าง SQL Editor รัน | out of scope ตาม spec — แจ้งหัวหน้าแล้วใน spec |
| R9 | การเปลี่ยน `save_script_groups` มาใช้ `write_json_atomic` เพิ่ม `fsync` | ช้าขึ้นเล็กน้อย ไฟล์ปลอดภัยขึ้น ผลลัพธ์บนดิสก์เหมือนเดิม (indent=2, ensure_ascii=False) |
| R10 | test เดิม `ExecuteModificationTests` | parameter `engine` เป็น optional → ผ่านเหมือนเดิม (AC-8) |

---
---

# Round 2 — Bugfix H3, M9, M3, H4

> อ้างอิง: `docs/spec.md` หัวข้อ "Round 2" (R2-AC-1 ถึง R2-AC-34, การตัดสินใจ R2-Q-1 ถึง R2-Q-8)
> เลขบรรทัดอ้างอิงโค้ดหลัง commit `2f4779b` (Round 1) ไฟล์ที่แก้: `database_connect_gui.py` เท่านั้น (+ test ใน `tests/`)

## R2-D1. ภาพรวมแนวทาง

| บัค | แนวทาง | เหตุผล |
|---|---|---|
| M3 | ย้ายการเช็ค `_SQL_SLASH_MARK` ใน `_scan_sql` ไปไว้**ก่อน** `c.isspace()` และแยกการ mark บรรทัด `/` เป็น helper `_mark_oracle_slash_lines` ที่ใช้ร่วมกับ H3 | `"\x1e".isspace()` เป็น True marker จึงไม่เคยถูกเห็น การย้ายลำดับเปลี่ยนน้อยที่สุด (marker ยาว 1 อักขระเท่าเดิม offset ของข้อความต้นฉบับยังตรงกัน) ไม่ต้องเปลี่ยน marker |
| H3 | ฟังก์ชัน pure ใหม่ `_sql_where_layout(sql)` ใช้ token จาก `_scan_sql` (เฉพาะ depth 0) หาตำแหน่ง WHERE / เงื่อนไขเดิม / จุดแทรก แล้ว `_append_where_conditions` ประกอบ SQL ใหม่ ครอบเงื่อนไขเดิมด้วยวงเล็บเสมอ ไม่แน่ใจ → `ValueError` | ใช้ scanner เดียวกับ `assess_sql` จึงข้าม string / comment / subquery / CTE ได้ถูกต้องโดยไม่ต้องเขียน parser ใหม่ (R2-5) |
| M9 | `_reset_sql_in_lists`: ค่าใน `IN (...)` ถูกเอาออกหมด → แทนทั้งเงื่อนไข `<col> IN (...)` ด้วย `1=0`; ถ้าเป็น `NOT IN` → `ValueError` ไม่คืน SQL; dialog จับ error ทั้ง preview และ Apply | `1=0` แทนที่ตรงตำแหน่งเดิมจึงไม่ต้องยุ่งกับ AND/OR/WHERE รอบข้าง ผลทางตรรกะถูกทุกกรณี (AND → ไม่มีแถว, OR → เหลือเงื่อนไขอื่น) |
| H4 | `_current_table_data_tables` เช็ค `os.path.getmtime` ทุกครั้ง โหลดใหม่เมื่อ mtime ต่างจาก `last_table_data_mtime` ไฟล์หาย / อ่านไม่ได้ → คืน `None` (ไม่ใช้ข้อมูลเก่า) และ `_prepare_run_sql` / Export เขียนบรรทัดเวลาข้อมูลลง Execution Logs ทุกครั้ง | จุดเดียวที่ Run / Export / Auto-sync ใช้ร่วมกัน ใช้ `last_table_data_mtime` ตัวเดียวกับ Auto-sync จึงไม่โหลดซ้ำ (R2-AC-27) |

## R2-D2. M3 — บรรทัด `/` เป็นตัวคั่น statement

```python
def _mark_oracle_slash_lines(sql: str) -> str:
    """Replace the '/' of every line holding only '/' with _SQL_SLASH_MARK.
    Same length as `sql`, so token offsets match the original text."""
```

- ย้ายบรรทัด 415 (`_SQL_SLASH_LINE_RE.sub(...)`) มาเป็นฟังก์ชันนี้ `split_sql_statements` เรียกใช้แทน
- `_scan_sql` (319): ย้ายบล็อก `if c == _SQL_SLASH_MARK: yield ("sep", ...)` (368-371) ขึ้นไปก่อน `if c.isspace()` (329) ไม่แก้ส่วนอื่น
- ข้อความ statement ที่ `split_sql_statements` คืนตัดจาก `sql` ต้นฉบับ (ไม่ใช่ `marked`) เหมือนเดิม จึงไม่มี marker หลุด (R2-AC-26)

### ผลกระทบที่ตรวจแล้ว

| ผู้ใช้ | ผล |
|---|---|
| `split_sql_statements` | บรรทัด `/` ปิด statement จริง `"X\n/"` คืน `["X"]` (เดิมคืน `"X\n/"` รวม `/`) ผู้ใช้ข้อความนี้มีแค่ `assess_sql` |
| `_classify_sql_statement`, `strip_sql_terminator` | เรียก `_scan_sql` กับข้อความดิบที่ไม่มี marker → ไม่เปลี่ยน (เว้นแต่ผู้ใช้พิมพ์อักขระ `\x1e` เองซึ่งไม่เกิดในทางปฏิบัติ) |
| `assess_sql` / `is_select_query` | `SELECT ..\n/\nDELETE ..` → 2 statement, DATA_CHANGE, `is_select_query` False |
| `_prepare_run_sql` | script หลาย statement ที่คั่นด้วย `/` ถูกบล็อก "more than one SQL statement" (พฤติกรรมตั้งใจ R2-5) |
| Export (`worker` เช็ค `is_select_query` + `statement_count > 1`) | skip ไม่รัน |
| `_confirm_data_change` | risk ถูกต้องขึ้น (แต่ `_prepare_run_sql` บล็อกก่อนถึง) |
| test เดิม `test_oracle_slash_terminator`, `test_plsql_block_is_one_unknown_statement`, `test_create_procedure_body_is_one_statement`, `StripSqlTerminatorTests` | ยังได้ 1 statement / ผลเดิม |

## R2-D3. H3 — Auto WHERE

### Interface

```python
@dataclass(frozen=True)
class _WhereLayout:
    insert_at: int                         # offset right after the last token of the main statement's
                                           # filter part (before trailing clauses / terminators / comments)
    condition: Optional[tuple[int, int]]   # (start, end) of the existing top-level WHERE condition;
                                           # None when there is no top-level WHERE


def _sql_where_layout(sql: str) -> _WhereLayout:
    """Where Auto WHERE may add conditions to `sql` (module level, pure).
    Raises ValueError (message says why) whenever the place is not certain."""


@staticmethod
def _append_where_conditions(sql: str, conditions: list[tuple[str, str]]) -> str:  # signature เดิม
```

### อัลกอริทึม `_sql_where_layout`

ทำงานบน `marked = _mark_oracle_slash_lines(sql)`; `tokens = list(_scan_sql(marked))` (offset ตรงกับ `sql`)

1. **วงเล็บ**: นับ token punct `(` กับ `)` ไม่เท่ากัน → `ValueError("Auto WHERE: unbalanced parentheses")` (ต้องนับเองเพราะ `_scan_sql` clamp depth ที่ 0)
2. **terminator ท้าย**: ตัด token ท้ายที่เป็น `semi` / `sep` ออกทั้งหมด → `body` ถ้าว่าง → `ValueError("Auto WHERE: SQL is empty")` ถ้า `body` ยังมี `semi` / `sep` → `ValueError("... more than one statement")`
3. **ประเภท statement**: word แรกต้องอยู่ที่ depth 0 (มิฉะนั้น ValueError) ถ้าเป็น `WITH` หา word ที่ depth 0 ตัวแรกหลังจากนั้นที่อยู่ใน `{SELECT, UPDATE, DELETE, INSERT, MERGE}` (word ใน CTE body อยู่ depth ≥ 1 จึงไม่ถูกนับ) คำสั่งหลักต้องเป็น `SELECT` / `UPDATE` / `DELETE` เท่านั้น อย่างอื่น (INSERT, MERGE, BEGIN, DECLARE, CREATE ฯลฯ) → `ValueError("Auto WHERE supports SELECT / UPDATE / DELETE only (found <X>)")` ให้ `main` = index ของ token คำสั่งหลัก
4. **พิจารณาเฉพาะ token depth 0 ตั้งแต่ `main` ถึงท้าย `body`** (`top`)
   - มี word `UNION` / `INTERSECT` / `EXCEPT` / `MINUS` → `ValueError` (R2-Q-2)
   - word `WHERE` มากกว่า 1 ตัว → `ValueError`
5. **จุดเริ่มค้นหา clause ท้าย** (`search_from`): ตำแหน่ง WHERE ถ้ามี; มิฉะนั้น SELECT → word `FROM` ตัวแรกใน `top` (ไม่มี → `ValueError("... SELECT without FROM")`), UPDATE → word `SET` ตัวแรก (ไม่มี → ValueError), DELETE → token คำสั่งหลัก
6. **clause ท้าย**: token แรกใน `top` หลัง `search_from` ที่เข้ารูปแบบต่อไปนี้ = `clause` (ไม่มี = None)
   - คู่คำ: `GROUP BY`, `ORDER BY`, `CONNECT BY`, `START WITH` (เช็คคำถัดไปใน `top` เพื่อไม่ชนชื่อคอลัมน์)
   - คำเดี่ยว: `HAVING`, `LIMIT`, `OFFSET`, `FETCH`, `FOR`, `RETURNING`, `WINDOW`, `OPTION`
7. **ตำแหน่ง**: `last` = token สุดท้ายของ `body` ที่อยู่ก่อน `clause` (ถ้ามี clause) → `insert_at = last.end`
   - ถ้ามี WHERE: `condition = (start ของ token ถัดจาก WHERE, insert_at)` ถ้า WHERE ไม่มี token ตามหลังก่อน clause → `ValueError("... WHERE has no condition")`
   - ใช้ offset ของ token เสมอ (ไม่ใช่ตำแหน่ง whitespace/comment) จึงไม่มีวงเล็บปิดไปอยู่ใน `--` comment และไม่มีเงื่อนไขใหม่ไปอยู่หลัง comment

### `_append_where_conditions`

- `conditions` ว่าง → คืน `sql` เดิมทุกตัวอักษร (ไม่เรียก layout) (R2-AC-14)
- `layout = _sql_where_layout(sql)` (ปล่อย `ValueError` ขึ้นไป)
- `added = "\nAND ".join(f"{column} IN ({sql_values})" for column, sql_values in conditions)`
- มี WHERE: `sql[:s] + "(" + sql[s:e] + ")" + "\nAND " + added + sql[e:]` (R2-Q-3 ครอบทุกครั้ง)
- ไม่มี WHERE: `sql[:insert_at] + "\nWHERE " + added + sql[insert_at:]`
- `sql[insert_at:]` เริ่มด้วย whitespace / comment / clause / terminator เดิม ทำให้ ORDER BY, `;`, บรรทัด `/` ยังอยู่ท้ายสุด (R2-AC-3, 9)

### ทางเดินของ error (R2-AC-13)

`_render_sql_template` (10939) ไม่ต้องแก้ `ValueError` วิ่งขึ้นไปยัง caller เดิมที่จับไว้แล้ว: Excel Import Apply (12040-12046 คืนค่า `_excel_parameter_values` เดิม + `showwarning` + Editor ไม่เปลี่ยน), preview ของ Reset (11303), Reset Apply (11425), `reset_single_parameter` (10950)

### ตัวอย่างที่ต้องได้ (normalize whitespace)

| Input | ผล |
|---|---|
| `UPDATE acct SET flag='Y' WHERE status='A' OR status='B'` | `... WHERE (status='A' OR status='B') AND ACC_NO IN ('1','2')` |
| `SELECT * FROM t ORDER BY a` | `SELECT * FROM t WHERE C IN ('x') ORDER BY a` |
| `SELECT * FROM (SELECT * FROM t WHERE x = 1) s` | `... ) s WHERE C IN ('x')` |
| `SELECT 'WHERE' AS w FROM t -- WHERE x` | `SELECT 'WHERE' AS w FROM t WHERE C IN ('x') -- WHERE x` |
| `SELECT * FROM t;` | `SELECT * FROM t WHERE C IN ('x');` |

## R2-D4. M9 — Reset Parameter (detected mode)

```python
@classmethod
def _reset_sql_in_lists(cls, sql: str, in_lists: list[dict], selected: dict[int, set]) -> str:
    """Drop selected tokens from each IN list. A list left empty becomes 1=0
    (IN) — or ValueError when the same list is negated by NOT outside strings/comments,
    because an emptied list would otherwise match every row."""
```

- เหลือค่า → เหมือนเดิม (R2-AC-19)
- เหลือ 0 ค่า: สแกน `sql[:vals_start]` ด้วย `_scan_sql()` แล้วจับคำว่า `NOT` ที่อยู่นอก string/comment; ถ้าเจอ ให้ `raise ValueError(f"{column} NOT IN (...) would have no values left, which matches every row — keep at least one value or edit the SQL by hand")` (R2-AC-21)
  - ครอบคลุมแบบ `col NOT IN (...)`, `NOT (col IN (...))`, `NOT (a = 1 AND col IN (...))`, และเวอร์ชันที่มี case/whitespace/newlines ต่างกัน
  - ถ้าตรวจไม่ชัดเจนก็ fail-safe: ยกเลิก rewrite แทนที่จะเขียน `1=0`
  - เป็น `IN` ธรรมดา → `sql = sql[:span_start] + "1=0" + sql[span_end:]` (แทนทั้ง `<col> IN (...)` ตาม `item["span"]`)
- ยังวนจาก list ท้ายไปต้นเหมือนเดิม (offset ไม่เลื่อน) raise ระหว่างทาง = ผู้เรียกไม่ได้ SQL ใดเลย
- `_remove_sql_condition` (11036) ไม่มีผู้เรียกอื่น → ลบทิ้ง (เป็นต้นเหตุของบัค ไม่ควรถูกเรียกใหม่โดยไม่ตั้งใจ)

### Dialog `show_reset_parameter_dialog`

- `refresh_sql_preview` (11297-11299): detected mode ครอบ `build_detected_sql()` ด้วย `try/except ValueError as error` → `preview_sql = f"{source_sql}\n\n-- {error}"` (รูปแบบเดียวกับ tracked mode 11304)
- `reset_selected` (11416-11421): `try: new_sql = build_detected_sql() except ValueError as error: messagebox.showerror("Reset Error", str(error), parent=dialog); return` → Editor ไม่เปลี่ยน หน้าต่างยังเปิดอยู่ ใช้ `new_sql` ตัวเดียวกับที่คำนวณ จึงตรงกับ preview (R2-AC-22)

## R2-D5. H4 — table data ล่าสุด

```python
def _current_table_data_tables(self) -> Optional[dict]:
    """Tables of the table-data file, reloaded whenever its mtime changes.
    File missing / unreadable / not a dict -> None (never falls back to old data)."""


def table_data_source_text(data: Optional[dict], mtime: Optional[float]) -> str:   # module level, pure
    """'📅 Table data: timestamp <data["timestamp"] or -> · file modified <YYYY-MM-DD HH:MM:SS or ->\\n'"""
```

### `_current_table_data_tables` (7358)

1. `mtime = os.path.getmtime(self.table_data_file)`; `OSError` (ไฟล์หาย) → print แล้วคืน `None` (R2-Q-7, R2-AC-31)
2. ถ้า `self.loaded_table_data` เป็น dict และ `getattr(self, "last_table_data_mtime", None) == mtime` → ใช้ข้อมูลในหน่วยความจำ ไม่เปิดไฟล์ (R2-AC-29)
3. มิฉะนั้นอ่านไฟล์ใหม่ `OSError` / `ValueError` หรือไม่ใช่ dict → print แล้วคืน `None` **โดยไม่แก้** `loaded_table_data` / `last_table_data_mtime` (ครั้งถัดไปจะลองอ่านใหม่; R2-Q-6, R2-AC-30)
4. อ่านได้ → `self.loaded_table_data = data`, `self.last_table_data_mtime = mtime` (Auto-sync ที่เทียบ `current_mtime > last_table_data_mtime` จะไม่โหลดซ้ำ R2-AC-27)
5. คืน `data["tables"]` ถ้าเป็น dict มิฉะนั้น `None`

ใช้ `!=` เทียบ mtime (ไม่ใช่ `>`) เพื่อรองรับไฟล์ที่ถูกแทนด้วยไฟล์เวลาเก่ากว่า ไม่แตะ `check_and_sync_table_data` และ `load_table_data_dialog`

### `_prepare_run_sql` (7310)

- เมื่อเจอ job แรกที่มี table variable เรียก `_current_table_data_tables()` ครั้งเดียวต่อการเรียก (เหมือนเดิม) แล้ว:
  - ได้ dict → เขียน `table_data_source_text(self.loaded_table_data, self.last_table_data_mtime)` ลง `results_text` **ครั้งเดียวต่อการเรียก** `_prepare_run_sql` (R2-AC-32: เรียก 2 ครั้ง = 2 บรรทัด)
  - ได้ `None` → ทุก job ที่มี table variable ได้ problem `• {name} — table data file is missing or cannot be read ({os.path.basename(table_data_file)}) — try again` (แทนข้อความ "no data") แล้วคืน `None` ผ่าน `showerror` เดิม (R2-AC-30, 31)
- อ่าน `self.loaded_table_data` / `self.last_table_data_mtime` เป็น attribute (ไม่เรียกเมธอดใหม่) เพื่อให้ stub แบบ `type("Stub", ...)` ใน test ใช้ต่อได้

### Export (`export_jobs_to_excel`, `export_tables` ~9773)

- หลังได้ `export_tables` ที่ไม่ใช่ `None` ให้เขียนบรรทัด `table_data_source_text(...)` ลง `results_text` (R2-AC-33) ถ้าได้ `None` worker เดิมจะ fail job นั้นด้วย "Table variable has no data" อยู่แล้ว (ไม่รันด้วยข้อมูลเก่า) — ไม่ต้องแก้ worker

### การปรับ fixture `PrepareRunSqlTests.make_stub` (tests 241-249) — qa-tester ทำ

ปัจจุบันใส่ `loaded_table_data` ในหน่วยความจำ + `table_data_file = "unused.json"` (ไม่มีไฟล์) หลัง R2-Q-7 จะได้ "ไฟล์หาย = ไม่รัน" ทำให้ `test_fills_variables_and_keeps_job_text` ล้ม ปรับเป็น:

```python
def make_stub(self, tables):
    folder = tempfile.TemporaryDirectory()
    self.addCleanup(folder.cleanup)
    path = os.path.join(folder.name, "mail_table_data.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"timestamp": "T1", "tables": tables}, f)
    stub = type("Stub", (), {})()
    stub.results_text = _FakeText()
    stub.loaded_table_data = None
    stub.last_table_data_mtime = None
    stub.table_data_file = path
    stub._current_table_data_tables = (
        lambda: app.DatabaseConnectorGUI._current_table_data_tables(stub)
    )
    return stub
```
สิ่งที่ test เดิมตรวจไม่เปลี่ยน (เปลี่ยนเฉพาะที่มาของข้อมูล)

## R2-D6. ไฟล์ / เมธอดที่แตะ (Round 2)

| ส่วน | การเปลี่ยน |
|---|---|
| module (~303-432) | `_mark_oracle_slash_lines` ใหม่, ลำดับเช็คใน `_scan_sql`, `split_sql_statements` ใช้ helper |
| module (หลัง `assess_sql` ~511) | `_WhereLayout`, `_sql_where_layout` ใหม่ |
| module (ส่วน table variables ~517+) | `table_data_source_text` ใหม่ |
| `_append_where_conditions` (10878) | เขียนใหม่ด้วย `_sql_where_layout` |
| `_remove_sql_condition` (11036) | ลบ |
| `_reset_sql_in_lists` (11053) | `1=0` / `ValueError` |
| `show_reset_parameter_dialog` (11297-11299, 11416-11421) | จับ `ValueError` |
| `_current_table_data_tables` (7358), `_prepare_run_sql` (7310), `export_jobs_to_excel` (~9773) | H4 |
| `tests/test_database_connect_gui_core.py` `PrepareRunSqlTests.make_stub` | ปรับ fixture (qa-tester) |

## R2-D7. ความเสี่ยง

| # | ความเสี่ยง | ผลกระทบ / การลด |
|---|---|---|
| R2-R1 | รายการ clause ท้ายของ H3 (คู่คำ/คำเดี่ยว) อาจไม่ครบทุก dialect หรือชนชื่อคอลัมน์ที่ไม่ได้ quote เช่นคอลัมน์ชื่อ `LIMIT` / `OFFSET` / `OPTION` ใน WHERE | คำส่วนใหญ่เป็น reserved word ของ DB หลัก คู่คำเช็คคำถัดไปเพื่อลดการชน ถ้าแทรกผิดที่ SQL จะ syntax error (ไม่กระทบแถวเกิน) และผู้ใช้เห็น SQL ใน Editor ก่อนรัน |
| R2-R2 | ผลของ Auto WHERE เปลี่ยนรูป (วงเล็บ, ขึ้นบรรทัด) | ตามที่ spec R2-5 ยอมรับ |
| R2-R3 | SQL ที่เคยใช้ Auto WHERE ได้ (เช่นมี UNION, INSERT ... SELECT) จะถูกปฏิเสธ | ตั้งใจตาม R2-Q-1/Q-2 ข้อความ error บอกเหตุผล |
| R2-R4 | M3 ทำให้ script Oracle หลาย block ที่เคยรันเป็นก้อนเดียวถูกบล็อก | ตั้งใจตาม R2-5 |
| R2-R5 | H4 เพิ่ม `os.path.getmtime` ทุกครั้งที่เตรียมรันด้วย table variable (ไฟล์บน OneDrive) | เรียกครั้งเดียวต่อการรันบน main thread เวลาน้อยมาก ถ้า OneDrive ล็อกไฟล์ระหว่าง sync จะได้ "อ่านไม่ได้ — ลองใหม่" ซึ่งปลอดภัยกว่าใช้ค่าเก่า |
| R2-R6 | `auto_replace_table_variables` (5974, Auto-sync) ก็เรียก `_current_table_data_tables` จะได้ `None` ถ้าไฟล์หาย | แค่รายงาน variable ที่เติมไม่ได้ใน log ของ Auto-sync ไม่รันอะไร |
| R2-R7 | test เดิม `PrepareRunSqlTests` ล้มทันทีหลังแก้ `_current_table_data_tables` ถ้า fixture ยังไม่ปรับ | ปรับ fixture ใน task เดียวกัน (R2-T5) |

---
---

# Round 3 — Feature: ปุ่ม Import / Export Groups ที่ Sidebar

> อ้างอิง: `docs/spec.md` หัวข้อ "Round 3" (R3-AC-1 ถึง R3-AC-18)
> การตัดสินใจของผู้ใช้: R3-Q-1 ยืนยัน R3-A1 ถึง A4 ทั้งหมด; **R3-Q-2 = ปุ่มอยู่แถวใหม่ใต้แถว `Preset 💾 Save 📂 Load`** ข้อความเต็ม `⇧  Import Groups` / `⇩  Export Groups`; R3-Q-3 = คงพฤติกรรมเดิม (ไม่มีกลุ่ม → info "no groups to export")
> หมายเหตุ: R3-AC-16 ใน spec ยังเขียนว่า "เรียงในแถวเดียว" — design นี้ทำตามการตัดสินใจ R3-Q-2 (แถวใหม่) หัวหน้า/PM ต้องแก้ข้อความ AC ใน spec (architect แก้ spec ไม่ได้)
> เลขบรรทัดอ้างอิง `database_connect_gui.py` บน branch `ui/remove-duplicate-buttons` (working tree ปัจจุบัน) อาจเลื่อนได้ ให้ค้นด้วยชื่อฟังก์ชัน

## R3-D1. ภาพรวมแนวทาง

แยก logic ของ nested function `export_groups` (4835-4897) / `import_groups` (4899-4996) ใน `show_script_groups_dialog` ออกเป็น 3 ชั้น:

| ชั้น | อยู่ที่ | ใช้ Tk | หน้าที่ |
|---|---|---|---|
| 1. pure helper | module level | ไม่ใช้ | สร้าง payload, ตั้งชื่อไฟล์, parse/validate ข้อมูลไฟล์, หา clash, merge เข้า list กลุ่ม |
| 2. instance method ที่ใช้ร่วม | `DatabaseConnectorGUI` | ใช้ (messagebox / filedialog ผ่าน `parent`) | flow ครบของ Export / Import: ถาม, เปิด file dialog, เขียน/อ่านไฟล์, `save_script_groups()`, log ลง `results_text`, refresh หน้าต่าง Script Groups ที่เปิดอยู่ |
| 3. จุดเรียก | closure ใน dialog + handler ของ sidebar | — | แค่ส่ง `parent` และข้อมูลบริบท (dialog: กลุ่มของ state + กลุ่มที่เลือก; sidebar: ทุกกลุ่มของ Profile ปัจจุบัน ไม่มีกลุ่มที่เลือก) |

เหตุผล:
- spec R3-5 ห้ามคัดลอก logic ซ้ำ และต้องมี pure helper อย่างน้อย 3 ตัวที่ test ได้โดยไม่เปิด Tk
- ชั้น 2 รับ `parent` จึงได้ messagebox parent = dialog (R3-AC-17) หรือ `self.root` (R3-A4) จากโค้ดเดียวกัน
- พฤติกรรม "ไม่ถาม all / only one" ของ sidebar (R3-A2) ได้มาโดยธรรมชาติ: sidebar ส่ง `selected=None` เงื่อนไขเดิม `selected is not None and len(groups) > 1` จึงไม่เข้า
- การ refresh dialog (R3-A3) ใช้ callback ที่ dialog ลงทะเบียนไว้บน instance และล้างเมื่อ dialog ถูก destroy — ทั้ง Import จาก dialog และจาก sidebar refresh ผ่านทางเดียวกัน จึงไม่มีการอ้าง closure ของ dialog ที่ปิดไปแล้ว
- บันทึกผ่าน `save_script_groups()` ตัวเดิมเท่านั้น → `_script_groups_save_blocked` (Round 1 C2) ใช้กับ sidebar อัตโนมัติ

ข้อความ messagebox, title, ข้อความ log, รูปแบบไฟล์, ลำดับการถาม คัดลอกจากโค้ดเดิมทุกตัวอักษร (ไม่เปลี่ยนพฤติกรรม)

## R3-D2. Pure helper (module level)

วางต่อจาก `query_template_label` (~830) ก่อน `select_sqlserver_odbc_driver` ใช้ `json`, `re`, `pd` ที่ import อยู่แล้ว type hint ใช้ `list` / `dict` / `Optional` ตามสไตล์ไฟล์

```python
SCRIPT_GROUPS_FILE_TYPE = "script_groups"
SCRIPT_GROUPS_FILE_VERSION = 1


def _script_groups_now() -> str:
    """'YYYY-MM-DD HH:MM:SS' ของเวลาปัจจุบัน (pd.Timestamp.now() เหมือนโค้ดเดิม)."""


def build_script_groups_export(groups: list, profile: str, now: Optional[str] = None) -> dict:
    """payload ของไฟล์ export (R3-AC-1)

    คืน {"type": "script_groups", "version": 1, "exported": now or _script_groups_now(),
         "profile": profile, "groups": [{"name", "created", "scripts"}, ...]}
    - แต่ละกลุ่มมีแค่ 3 key: name = g["name"], created = g.get("created"), scripts
    - script ตัด key ที่ขึ้นต้นด้วย "_" และ "run_index" (dict ใหม่ ไม่แก้ object เดิม)
    - ลำดับกลุ่ม/script ตาม input
    """


def script_groups_export_filename(label: Optional[str], stamp: str) -> str:
    """f"script_groups_{safe}_{stamp}.json" โดย safe = re.sub(r'[\\/:*?"<>|]', "_", str(label)).strip()
    ถ้าว่างใช้ "groups" (ตรรกะเดิม 4855) — label None ให้ถือเป็น "" """


def parse_script_groups_import(data: Any) -> list:
    """แปลงข้อมูลจาก json.load เป็น list กลุ่มที่ import ได้ (R3-AC-2, R3-AC-3)

    - data เป็น dict → ใช้ data.get("groups"); นอกนั้นใช้ data ตรง ๆ
    - ไม่ใช่ list → raise ValueError("no 'groups' list in this file")
    - กรองทิ้ง: ไม่ใช่ dict / name ไม่ใช่ str / name.strip() ว่าง / "scripts" มีแต่ไม่ใช่ list
    - script ที่ไม่ใช่ dict หรือไม่มี "query" (falsy) → raise ValueError(f"group '{name}' has a script without SQL")
    - คืน list ของ dict กลุ่มเดิม (object เดียวกับใน data, ไม่ copy — merge จะ copy เอง)
    - list ว่างเป็นผลปกติ (ผู้เรียกแจ้ง "No groups found in this file")
    """


def script_group_name_clashes(script_groups: list, incoming: list, profile: str) -> list:
    """ชื่อของกลุ่มใน incoming (ตามลำดับ, ตัวสะกดของไฟล์) ที่ชนชื่อ (ไม่สนตัวพิมพ์)
    กับกลุ่มของ profile นี้ใน script_groups (ตรรกะเดิม 4935-4937)"""


def merge_imported_script_groups(script_groups: list, incoming: list, profile: str,
                                 replace: bool, now: Optional[str] = None) -> Optional[str]:
    """เพิ่ม incoming เข้า script_groups (แก้ list นี้ in place) คืนชื่อกลุ่มสุดท้ายที่เพิ่ม
    (None ถ้า incoming ว่าง) — ตรรกะเดิม 4965-4990 ทุกขั้น:

    - existing = {name.lower(): g} ของกลุ่มที่ profile ตรง, taken = set ของชื่อ lower เดียวกัน
    - ต่อกลุ่ม: old = existing.pop(name.lower(), None)
        old is not None and replace → script_groups.remove(old) (ใช้ชื่อเดิมจากไฟล์)
        elif name.lower() in taken → หา n เริ่ม 2 ที่ f"{name} ({n})".lower() ไม่อยู่ใน taken
      taken.add(name.lower()) แล้ว append
        {"name", "profile": profile, "created": g.get("created") or now,
         "imported": now, "scripts": json.loads(json.dumps(g.get("scripts", []), default=str))}
    - now = now or _script_groups_now() คำนวณครั้งเดียวต่อการเรียก
    - กลุ่มของ profile อื่นไม่ถูกแตะ (R3-AC-4)
    """
```

หมายเหตุ AC:
- R3-AC-6: ชื่อซ้ำกันเองในไฟล์ → `existing.pop` ทำให้แทนที่กลุ่มเดิมแค่ครั้งเดียว กลุ่มที่สองชนกับ `taken` จึงได้ `G1 (2)`
- R3-AC-7: `json.dumps(..., default=str)` แปลง `Timestamp` เป็น string และได้ copy ใหม่

## R3-D3. Instance method ที่ใช้ร่วม (`DatabaseConnectorGUI`)

วางในส่วน Script Groups ต่อจาก `_backup_script_groups_once` (~4224) ก่อน `show_script_groups_dialog`

```python
def _ensure_script_groups_loaded(self) -> list:
    """ถ้ายังไม่มี attribute script_groups → self.script_groups = self.load_script_groups()
    คืน self.script_groups (R3-AC-14) — show_script_groups_dialog (4493-4494) เรียกเมธอดนี้แทนโค้ดเดิม"""


def export_script_groups(self, parent: Any, groups: list, profile: str,
                         selected: Optional[dict] = None) -> Optional[str]:
    """flow Export เดิม (4835-4897) คืน path ที่เขียนสำเร็จ หรือ None

    1. groups ว่าง → showinfo("Export Groups", "This profile has no groups to export", parent=parent)
    2. selected is not None and len(groups) > 1 → askyesnocancel ข้อความเดิม (ใช้ profile, selected["name"])
       None → return; scope_all = answer
    3. chosen = groups if scope_all else [selected]; label = profile if scope_all else selected["name"]
    4. filedialog.asksaveasfilename(parent=parent, title="Export Script Groups", defaultextension=".json",
       filetypes=[("JSON files", "*.json")],
       initialfile=script_groups_export_filename(label, pd.Timestamp.now().strftime("%Y%m%d_%H%M%S")))
       "" → return None (ไม่มีไฟล์ ไม่มี log — R3-AC-10)
    5. data = build_script_groups_export(chosen, profile); เขียนด้วย open(..., "w", encoding="utf-8")
       + json.dump(indent=2, ensure_ascii=False) (เหมือนเดิม ไม่เปลี่ยนเป็น atomic)
       error → showerror("Export Groups", f"Cannot write file:\n{e}", parent=parent); return None
    6. log "📤 Exported {len(chosen)} group(s), {count} script(s) → {file_path}\n" + see(END)
       แล้ว showinfo ข้อความเดิม parent=parent
    """


def import_script_groups(self, parent: Any) -> Optional[str]:
    """flow Import เดิม (4899-4996) คืนชื่อกลุ่มสุดท้ายที่ import หรือ None ถ้าไม่ได้ import

    1. self._ensure_script_groups_loaded()
    2. profile = self.profile_combo.get(); ว่าง → showwarning("Import Groups", "Please select a profile first",
       parent=parent) ไม่เปิด file dialog (R3-AC-11)
    3. askopenfilename(parent=parent, title="Import Script Groups", filetypes=[เดิม]); "" → None
    4. try: open/json.load → parse_script_groups_import(data)
       except Exception as e → showerror("Import Groups", f"Not a valid Script Groups file:\n{e}", parent=parent)
       (คง except Exception เหมือนเดิม: ครอบ OSError, JSONDecodeError, UnicodeDecodeError, ValueError)
    5. incoming ว่าง → showinfo("Import Groups", "No groups found in this file", parent=parent)
    6. clashes = script_group_name_clashes(...); summary 15 บรรทัดแรก + "... and N more" (ข้อความเดิม 4938-4944)
       มี clash → askyesnocancel ข้อความเดิม (None → return None; replace = answer)
       ไม่มี clash → askyesno ข้อความเดิม (False → return None; replace = False)
    7. last = merge_imported_script_groups(self.script_groups, incoming, profile, replace)
    8. self.save_script_groups()  (ครั้งเดียว — ถ้า _script_groups_save_blocked จะโชว์ error เดิมเอง)
    9. self._refresh_script_groups_window(last)
    10. log "📥 Imported {len(incoming)} group(s) from {file_path}\n" + see(END); return last
    ลำดับ 8 → 9 → 10 ตรงกับโค้ดเดิม (save → refresh_groups → log)
    """


def _refresh_script_groups_window(self, select_name: Optional[str] = None) -> None:
    """เรียก callback refresh ของหน้าต่าง Script Groups ที่เปิดอยู่ (R3-A3, R3-AC-15)

    callback = getattr(self, "_script_groups_refresh", None); None → return
    window = getattr(self, "_script_groups_window", None)
    window is None หรือ not window.winfo_exists() → self._script_groups_refresh = None; return
    มิฉะนั้น callback(select_name)
    """


def sidebar_export_script_groups(self) -> None:
    """ปุ่ม ⇩ Export Groups ของ sidebar (R3-A2, R3-A4)
    self._ensure_script_groups_loaded(); profile = self.profile_combo.get()
    groups = [g for g in self.script_groups if g.get("profile") == profile]
    self.export_script_groups(self.root, groups, profile)   # selected=None → ไม่ถาม all/one"""


def sidebar_import_script_groups(self) -> None:
    """ปุ่ม ⇧ Import Groups ของ sidebar: self.import_script_groups(self.root)"""
```

R3-Q-3: `profile_combo` ว่างตอน Export จาก sidebar → กรองกลุ่มที่ `profile == ""` เหมือน dialog เดิม ปกติไม่มี → info "no groups to export" (ไม่เพิ่ม check ใหม่)

## R3-D4. การแก้ `show_script_groups_dialog`

| จุด | การเปลี่ยน |
|---|---|
| 4493-4494 | ใช้ `self._ensure_script_groups_loaded()` |
| `export_groups` (4835-4897) | เหลือ 1 บรรทัด: `self.export_script_groups(dialog, state["groups"], state["profile"], current_group())` |
| `import_groups` (4899-4996) | เหลือ 1 บรรทัด: `self.import_script_groups(dialog)` — refresh รายการผ่าน callback ที่ลงทะเบียน (dialog เปิดอยู่จึงถูกเรียกแน่นอน) |
| ก่อน `refresh_groups()` ตัวสุดท้าย (5046) | ลงทะเบียน `self._script_groups_refresh = lambda name=None: refresh_groups(select_name=name)` (เก็บ reference ไว้ในตัวแปร local `registered`) และ bind `<Destroy>` |
| `<Destroy>` handler | `dialog.bind("<Destroy>", _on_destroy, add="+")` โดย `_on_destroy(event)` ทำงานเฉพาะ `event.widget is dialog` (event ของ child ทุกตัวส่งมาที่ Toplevel ด้วย) และล้างเฉพาะเมื่อ `getattr(self, "_script_groups_refresh", None) is registered` (กันการล้าง callback ของหน้าต่างใหม่) |

ปุ่มในหัว dialog (5007-5008) ผูกกับ closure เดิม `import_groups` / `export_groups` ไม่ต้องแก้

## R3-D5. ปุ่มที่ Sidebar (R3-Q-2: แถวใหม่)

ในส่วน Presets (2591-2601) ต่อจาก `presets_inner` ก่อน `presets.pack(...)`:

```python
groups_io = tk.Frame(presets, bg=UI["surface"])
groups_io.pack(fill="x", padx=8, pady=(0, 6))
_ghost(groups_io, "⇧  Import Groups", self.sidebar_import_script_groups, bg=UI["surface"]).pack(side="left")
_ghost(groups_io, "⇩  Export Groups", self.sidebar_export_script_groups, bg=UI["surface"]).pack(side="left")
```
- ลำดับ Import → Export ตรงกับหัว dialog และ spec
- `presets_inner` pady เดิม `6` เปลี่ยนเป็น `(6, 2)` ได้ถ้าแถวห่างเกิน — ปรับตามตาที่ developer เห็น (ไม่บังคับ) ห้ามเปลี่ยนส่วนอื่นของแถว Preset
- ไม่เพิ่ม label หน้าแถวใหม่ (spec ไม่ได้ขอ)

## R3-D6. Data model

ไม่เปลี่ยน รูปแบบไฟล์ export (`type`, `version=1`, `exported`, `profile`, `groups`) และ `script_groups.json` เหมือนเดิม attribute ใหม่บน instance:

| attribute | type | ค่า |
|---|---|---|
| `_script_groups_refresh` | `Optional[Callable[[Optional[str]], None]]` | ตั้งตอนเปิด dialog, `None` เมื่อ dialog ถูก destroy หรือพบว่าหน้าต่างไม่อยู่แล้ว |

## R3-D7. แนวทาง test (สำหรับ qa-tester)

ไฟล์ใหม่ `tests/test_r3_script_groups_io.py` — ไม่เปิด Tk:
- helper (R3-AC-1 ถึง 7): เรียกฟังก์ชัน module ตรง ส่ง `now="2026-01-01 00:00:00"` เพื่อ assert ค่าแน่นอน (และอีก test ที่ไม่ส่ง `now` ตรวจ regex รูปแบบเวลา)
- flow (R3-AC-8 ถึง 15): stub `DatabaseConnectorGUI.__new__` แบบ `tests/test_script_groups_block.py::make_stub` + `stub.root = object()` (sentinel ใช้ตรวจ `parent`), `stub.profile_combo = mock.Mock(get=...)`, `stub.results_text = mock.Mock()`, `stub.save_script_groups = mock.Mock()` (หรือใช้ของจริงกับ `_script_groups_path` ใน tempdir สำหรับ R3-AC-14 / การบล็อก), `mock.patch.object(app, "filedialog")` / `mock.patch.object(app, "messagebox")`
- R3-AC-14: stub ที่ไม่มี attribute `script_groups` + `script_groups.json` ใน tempdir มีกลุ่มเดิม → หลัง import ไฟล์มีทั้งกลุ่มเดิมและกลุ่มใหม่
- R3-AC-15: ตั้ง `stub._script_groups_refresh = mock.Mock()` + `stub._script_groups_window = mock.Mock(winfo_exists=lambda: True)` → ถูกเรียกด้วยชื่อสุดท้าย; `winfo_exists` คืน False → ไม่เรียกและ attribute เป็น None; ไม่มี attribute เลย → ไม่ error
- R3-AC-17 (unittest ส่วน dialog): `export_script_groups(parent=sentinel, groups=[2 กลุ่ม], profile, selected=g)` → `askyesnocancel` ถูกเรียกด้วย `parent=sentinel`; ตอบ No → ไฟล์มีกลุ่มเดียว ชื่อไฟล์ใช้ชื่อกลุ่ม

## R3-D8. ไฟล์ / เมธอดที่แตะ (Round 3)

| ส่วน | การเปลี่ยน |
|---|---|
| module (หลัง `query_template_label` ~830) | ใหม่: ค่าคงที่ 2 ตัว, `_script_groups_now`, `build_script_groups_export`, `script_groups_export_filename`, `parse_script_groups_import`, `script_group_name_clashes`, `merge_imported_script_groups` |
| `DatabaseConnectorGUI` ส่วน Script Groups (~4224) | ใหม่: `_ensure_script_groups_loaded`, `export_script_groups`, `import_script_groups`, `_refresh_script_groups_window`, `sidebar_export_script_groups`, `sidebar_import_script_groups` |
| `show_script_groups_dialog` (4491-5046) | ใช้ `_ensure_script_groups_loaded`, closure export/import เหลือบรรทัดเดียว, ลงทะเบียน/ล้าง `_script_groups_refresh` |
| UI build, Presets (2591-2601) | แถวใหม่ `groups_io` 2 ปุ่ม |
| `tests/test_r3_script_groups_io.py` | ใหม่ (qa-tester) |

ไม่แตะ: `load_script_groups`, `save_script_groups`, `manual/`, `robot_tests/` (อ้างแค่ `_script_groups_window` ซึ่งไม่เปลี่ยน), README (spec Round 3 ไม่ได้ขอ)

## R3-D9. ความเสี่ยง

| # | ความเสี่ยง | ผลกระทบ / การลด |
|---|---|---|
| R3-R1 | refactor ทำให้พฤติกรรมปุ่มใน dialog เปลี่ยนโดยไม่ตั้งใจ (ข้อความ, parent, ลำดับถาม) | คัดลอกข้อความเดิมตรงตัว; test R3-AC-17 ส่วน unittest + Manual/GUI; diff ของ closure ต้องเหลือแค่การ delegate |
| R3-R2 | `<Destroy>` ของ Toplevel ถูกเรียกจาก child ทุกตัว ถ้าไม่เช็ก `event.widget is dialog` callback อาจถูกล้างตอน widget ลูกถูกทำลาย (เช่น listbox rebuild) | เช็ก `event.widget is dialog` + identity ของ callback; `_refresh_script_groups_window` เช็ก `winfo_exists()` ซ้ำอีกชั้น |
| R3-R3 | `_script_groups_save_blocked` = True: Import แก้ `self.script_groups` ในหน่วยความจำ, `save_script_groups()` แสดง error แต่ยัง refresh และเขียน log "📥 Imported" | เป็นพฤติกรรมเดิมของ dialog (spec ให้ "บล็อกแบบเดียวกับใน dialog") ไม่เปลี่ยนใน round นี้ — ถ้าต้องการให้ไม่ log/ไม่แก้ memory เมื่อบล็อก ต้องเพิ่มใน spec |
| R3-R4 | `save_script_groups()` เรียก messagebox โดยไม่มี `parent` | เหมือนเดิม; จาก sidebar parent ปริยายคือ root อยู่แล้ว |
| R3-R5 | sidebar Import/Export กดได้ระหว่างมีงานรัน | spec ระบุ out of scope (ไม่กระทบ engine / Profile) — ไม่ลงทะเบียน run-lock |
| R3-R6 | แถวใหม่ทำให้พื้นที่รายการ Jobs ใน sidebar เตี้ยลง ~1 แถวปุ่ม | ยอมรับตาม R3-Q-2; ตรวจใน Manual/GUI (R3-AC-16) |
| R3-R7 | เลขบรรทัดในเอกสารอ้าง working tree ที่ยังมีงาน Round 2 ค้าง (R2-T-fix2 `[~]`) | developer ค้นด้วยชื่อฟังก์ชัน; ส่วนที่แตะไม่ซ้อนกับ Reset Parameter |

---
---

# Round 4 — Bugfix: Profile mismatch guard และ Excel row limit

> อ้างอิง: `docs/spec.md` หัวข้อ Round 4 (R4-AC-1 ถึง R4-AC-9)
> ขอบเขต: ปฏิเสธการเริ่มงานเมื่อ Profile ที่เลือกไม่ตรงกับ connection snapshot และทำให้ Job ที่เกิน Excel row limit ล้มเหลวโดยไม่เขียนผลบางส่วน

## R4-D1. ภาพรวมแนวทาง

ใช้ `RunTarget` / `ConnectionInfo` ที่มีจาก Round 1 เป็นแหล่งข้อมูลอ้างอิงเดียวสำหรับตรวจ Profile ไม่สร้างหรือสลับ engine อัตโนมัติ เพิ่ม guard กลางที่ใช้กับทุก entry point ของงานที่ใช้ connection ร่วมกัน และให้ข้อความปฏิเสธลง Execution Logs โดยระบุ Profile ที่เลือกกับ Profile ของ connection

สำหรับ Excel ให้ตรวจ `len(df)` เทียบกับขีดจำกัดข้อมูล 1,048,575 แถวก่อนเรียก `DataFrame.to_excel` สำหรับ sheet ผลลัพธ์ หากเกินให้ raise `ValueError` ที่ระบุ limit เข้าสู่ exception handler ต่อ Job เดิม ซึ่งเพิ่ม Failed count และเขียน sheet Failed แล้ววนต่อ Job ถัดไป ห้าม slice / truncate DataFrame

การแยก QA ออกจาก implementation ทำให้แต่ละ finding มีชุด focused tests ที่รันแยกได้ ก่อน task regression ทั้งชุด.

## R4-D2. Profile mismatch guard

```python
def _block_if_profile_mismatch(self, action: str) -> bool:
    """Log and return True only when the selected and connected Profiles
    are both known and differ; do not mutate the Profile or connection."""
```

- อ่านชื่อที่เลือกจาก `profile_combo.get()` และชื่อที่ผูกกับ engine ปัจจุบันจาก `_capture_run_target().info.profile` (ตรวจว่า target ยังอ้างถึง `self.engine` ตาม abstraction เดิม)
- ใช้กติกาที่แนะนำใน R4-Q-1: เปรียบเทียบเฉพาะเมื่อชื่อทั้งสองฝั่งไม่ว่าง; เมื่อไม่มี snapshot / Profile ใดว่าง ให้คงพฤติกรรมเดิม ไม่เดาจาก `engine.url`
- เมื่อ mismatch ให้เขียนข้อความลง `results_text` ว่างานไม่ได้เริ่ม พร้อมชื่อ Profile ที่เลือกและ Profile ที่ connection ใช้อยู่ แล้วคืน `True`; ไม่เรียก `messagebox`, ไม่แก้ `profile_combo`, `engine` หรือ `_run_target`
- เรียกหลัง `_block_if_busy(...)` และก่อนเช็ค/ใช้ connection, แสดง confirmation, เปิด file dialog, metadata query หรือสร้าง worker ใน `run_job`, `run_selected_job`, `export_jobs_to_excel`, `execute_query` และ `list_tables`
- กรณีตรงกันปล่อยให้ flow เดิมทำงานและใช้ `RunTarget.engine`; `connect_database` / `_replace_engine` ยังคงสร้าง snapshot ใหม่เมื่อ Connect สำเร็จ จึงเชื่อม Profile B แล้วเริ่มงานต่อได้ตามปกติ

## R4-D3. Excel worksheet row limit

```python
EXCEL_MAX_DATA_ROWS = 1_048_575


def _ensure_excel_row_limit(row_count: int) -> None:
    """Raise ValueError when a Job exceeds Excel's data-row capacity."""
```

- ใช้ค่าคงที่ร่วมกันทั้ง production check และ focused tests; header หนึ่งแถวไม่รวมใน `row_count`
- เรียก validation ใน `export_jobs_to_excel.worker` เมื่อ DataFrame พร้อมและก่อนเขียน sheet ผลลัพธ์ (รวมถึงก่อน any write ที่อาจทำให้ Job ดูเหมือนสำเร็จ)
- จำนวนแถวมากกว่า limit: raise ข้อความ error ที่ระบุ `1,048,575` แถวข้อมูล; exception handler ต่อ Job เพิ่ม Failed และสร้าง sheet Failed ตามเดิม โดยไม่เขียนแถวจาก DataFrame
- จำนวนแถวเท่ากับ limit หรือน้อยกว่า: ไม่เปลี่ยน DataFrame และใช้การเขียน / formatting เดิมครบถ้วน
- ไม่เปลี่ยนจำนวน sheet, รูปแบบ workbook, การตั้งชื่อ sheet หรือการนับ Skipped ของ SQL ที่ไม่ใช่ SELECT

## R4-D4. ไฟล์และการทดสอบ

| ไฟล์ | หน้าที่ |
|---|---|
| `database_connect_gui.py` | เพิ่ม guard Profile mismatch ที่ entry points ห้าตัว และใช้ row-limit constant / validator ใน worker ของ Export |
| `tests/test_r4_profile_mismatch.py` | QA focused tests: mismatch/refusal/logging, matching path, การเชื่อมต่อ Profile ใหม่และการคง engine/snapshot เดิมเมื่อถูกปฏิเสธ |
| `tests/test_r4_excel_row_limit.py` | QA focused tests: เกิน limit เป็น Failed ไม่มีการเขียน DataFrame บางส่วน, boundary ที่ limit เขียนครบ, และ Job ถัดไปสำเร็จ |
| `docs/design.md`, `docs/tasks.md` | แผนงานและการจัดสรร AC ของ Round 4 เท่านั้น |

การทดสอบใช้ stub / mock ของ GUI, DataFrame และ Excel writer ตาม spec; ไม่เปิด Tk และไม่ต่อฐานข้อมูลจริง.

## R4-D5. ความเสี่ยงและผลกระทบ

| # | ความเสี่ยง | ผลกระทบ / การลด |
|---|---|---|
| R4-R1 | ชื่อ Profile ว่างหรือไม่มี snapshot | ตาม R4-Q-1 ไม่ปฏิเสธเมื่อเทียบไม่ได้ เพื่อคง backward compatibility; ไม่อนุมานชื่อจาก URL |
| R4-R2 | Profile ถูกเปลี่ยนในหน้าจอโดยไม่ได้ Connect ใหม่ | งานทั้งห้าประเภทถูกปฏิเสธพร้อมข้อความชัดเจน; ไม่เปลี่ยน connection ให้อัตโนมัติ |
| R4-R3 | การตรวจ row limit เกิดหลังเริ่มเขียน sheet | วาง validation ก่อน `to_excel` ของผลลัพธ์; exception handler ต่อ Job มีไว้สร้าง sheet Failed และวนต่อ ไม่บันทึกผล DataFrame บางส่วน |
| R4-R4 | test boundary ใช้ DataFrame ขนาดใหญ่จริงทำให้ช้า/กินหน่วยความจำ | ใช้ DataFrame / writer stub ที่จำลอง `len` และยืนยัน call arguments โดยไม่สร้างล้านแถวจริง |

## R4-D6. AC → Task

| AC | Task | AC | Task | AC | Task |
|---|---|---|---|---|---|
| R4-AC-1 | R4-T1, R4-T2 | R4-AC-4 | R4-T1, R4-T2 | R4-AC-7 | R4-T3, R4-T4 |
| R4-AC-2 | R4-T1, R4-T2 | R4-AC-5 | R4-T1, R4-T2 | R4-AC-8 | R4-T3, R4-T4 |
| R4-AC-3 | R4-T1, R4-T2 | R4-AC-6 | R4-T3, R4-T4 | R4-AC-9 | R4-T5 |

---

# Round 5 — Profile, Export, SQL parsing และ UI thread safety

> อ้างอิง: `docs/spec.md` หัวข้อ Round 5 (R5-AC-1 ถึง R5-AC-13)
> ขอบเขต: เฉพาะ bug 12 รายการใน R5-2; ไม่แก้หรือ refactor พฤติกรรมนอก AC
> งานพัฒนาและ QA ใช้ `unittest`; แต่ละ bug มีไฟล์ test ตาม ID ใน spec

## R5-D1. แนวทาง

แก้เฉพาะจุดตัดสินใจเดิมใน `database_connect_gui.py` โดยใช้กลไกที่มีอยู่แล้ว: `write_json_atomic` สำหรับการบันทึกแบบ atomic, `_scan_sql` สำหรับการอ่าน SQL, `format_db_value` สำหรับรูปแบบค่า DB, และ `root.after` สำหรับผลลัพธ์จาก worker ไม่เพิ่ม framework หรือ abstraction กลางที่ไม่จำเป็น

ทำตามลำดับ priority ที่อนุมัติ: C-1 ก่อน H-3 โดย C-1 ครอบคลุม success path และ H-3 ตามมารับรอง rollback เมื่อ persistence ล้มเหลว; แยก H-3 เป็น Profile กับ Job callers. จากนั้นทำ conversion/validation ก่อนเขียน workbook, ใช้ `_scan_sql` แยกสำหรับ First IN list และ placeholder, และจัดการ Tables snapshot กับ SQL/test-connection worker คนละ task ตาม worker boundary.

## R5-D2. ไฟล์และ interface

| ไฟล์ | หน้าที่ |
|---|---|
| `database_connect_gui.py` | แก้ save result/callers, Profile-job guard, export values/cells, SQL token lookup, Tables worker inputs/disposal, query debug snapshot, test-connection UI scheduling, close confirmation และ preset overwrite |
| `tests/test_bugfix_c1.py` | R5-AC-1: profile selection refresh และปฏิเสธ Job ของ Profile อื่น |
| `tests/test_bugfix_h3.py` | R5-AC-2: bool ของ save methods และ rollback ของ callers ทั้งเจ็ด |
| `tests/test_bugfix_c2.py` | R5-AC-3: ขีดจำกัด string cell และสถานะ warning ของ Job |
| `tests/test_bugfix_c3.py` | R5-AC-4: bytes ผ่าน `format_db_value` |
| `tests/test_bugfix_h2.py` | R5-AC-5: First IN list จาก SQL token เท่านั้น |
| `tests/test_bugfix_m1.py` | R5-AC-6: placeholder tokenization |
| `tests/test_bugfix_h1.py` | R5-AC-7: Tables worker snapshot, disposal และ bind parameter |
| `tests/test_bugfix_m3.py` | R5-AC-8: debug snapshot และ UI callback ของ test connection |
| `tests/test_bugfix_m2.py` | R5-AC-9: string literal ใน annotation / status sheets |
| `tests/test_bugfix_m4.py` | R5-AC-10: ยืนยันก่อนปิดระหว่าง busy |
| `tests/test_bugfix_m5.py` | R5-AC-11: preset ชนชื่อ, cancel, atomic write |
| `tests/test_bugfix_m6.py` | R5-AC-12: reload Profile ที่ active หลัง import สำเร็จ |

ไม่กำหนด public API ใหม่ นอกจากให้ `save_profiles() -> bool` และ `save_jobs() -> bool` คืน `True` เมื่อเขียนสำเร็จและ `False` เมื่อถูกบล็อกหรือเขียนไม่สำเร็จ; helper อื่นให้เป็น local helper หรือเมธอดเล็กเฉพาะจุดตามรูปแบบรอบเดิม.

## R5-D3. Persistence และ Profile behavior

### H-3 — ผลบันทึกและ rollback

- `save_profiles` / `save_jobs`: คืน bool ทุกทางออก รวมกรณี save-blocked; เก็บการรายงาน error เดิม และใช้ `write_json_atomic` ต่อไป
- ก่อนเปลี่ยน `saved_profiles` หรือ `saved_jobs` ใน caller ที่ระบุ ให้เก็บ snapshot ของค่าเดิม; ถ้า save คืน `False` ให้คืน mapping/list และ record ที่แก้ไขกลับค่าเดิม แล้ว return ก่อน success log/message, UI refresh, profile switch หรือการปิด dialog ที่เดิมทำหลังสำเร็จ
- `save_profile_dialog.save` ต้องไม่คงการ normalize `db_port` ใน widget เมื่อ write ล้มเหลว: ให้ normalize หลัง save สำเร็จ หรือคืนค่าช่องเป็นค่าก่อน action
- Profile callers: `save_profile_dialog.save`, `new_profile_dialog.create`, `delete_profile`, `do_import`. Snapshot ต้องคืนทั้งสมาชิกและข้อมูลก่อน action; import replace/merge ต้องคืน mapping ทั้งชุดเมื่อเขียนไม่สำเร็จ
- Job callers: `save_job_dialog.save`, `edit_job.save_changes`, `load_preset_dialog`. กรณีแก้ dict เดิมให้เก็บและคืนค่าของ dict ด้วย; กรณีแทนรายการให้คืนรายการเดิมทั้งชุด
- ห้ามรายงานความสำเร็จจาก caller เมื่อ save ล้มเหลว; ให้ save method เป็นจุดแสดง error เพื่อไม่แสดง error ซ้ำ
- งานบันทึกอื่นที่ไม่ได้ระบุใน R5-AC-2 ไม่เปลี่ยน flow เพิ่มเติมเพียงเพราะ return type เปลี่ยน

### C-1 และ M-6 — สอดคล้องกับ Profile ที่เลือก

- เมื่อ `save_profile_dialog.save` บันทึกสำเร็จ ให้เลือก Profile ตามเดิม แล้วเรียก `update_jobs_list()` หลังเลือกเสร็จ; เมื่อบันทึกล้มเหลวใช้ rollback ของ H-3 และไม่เปลี่ยน Profile ที่เลือก
- ที่ต้นทาง `run_job(job)`, เปรียบเทียบ `job.get("profile")` กับ `profile_combo.get()`; ถ้าไม่ตรงให้เขียนเหตุผลลง Execution Logs แล้ว return ก่อน confirmation หรือสร้าง worker
- `do_import`: เก็บชื่อ Profile ที่ active ก่อน import; หลัง save สำเร็จเท่านั้น ถ้า import เขียนทับชื่อนั้นให้เรียก `load_profile_data(active)` เพื่ออัปเดต fields/connection; import Profile อื่นไม่ reload; save ล้มเหลวใช้ rollback H-3 และไม่ reload

## R5-D4. Export และ SQL parsing

### Excel (C-2, C-3, M-2)

- `clean_value` สำหรับ `bytes` เรียก `format_db_value(x)` โดยตรงก่อนเส้นทางแปลง string ทั่วไป; ห้าม decode bytes เป็น UTF-16LE/UTF-8
- ก่อน `DataFrame.to_excel` ตรวจ string cells ทุก column; ค่าเกิน 32,767 ตัวอักษรต้องไม่ถูกส่งให้ writer, ให้ cell ว่างแทน, และ log warning ระบุชื่อ Job กับชื่อ column; ติดตาม Job เป็น warning ไม่ใช่ success ปกติ (ใช้สถานะ/ตัวนับ warning ในผล Export ที่มีอยู่ใน flow นี้)
- สำหรับข้อความที่ต้องเป็น literal ใน SQL annotation, No Data, Failed และ Skipped sheets, หลังสร้าง cell ด้วย `ws.cell(...)` กำหนด `cell.data_type = 's'`; สำหรับแถวที่เกิดจาก `DataFrame.to_excel` ให้บังคับเซลล์ข้อความขึ้นต้น `=` เป็น string หลังสร้าง sheet
- คงการจัดรูปแบบและโครงสร้าง workbook ที่ไม่เกี่ยวกับสาม AC นี้

### SQL tokens (H-2, M-1)

- `_render_sql_template` หา `IN` และวงเล็บ list จาก token/ตำแหน่งที่ `_scan_sql` คืน โดยข้าม string/comment; แทน `__FIRST_IN_LIST__` ด้วย span ของ list จริงตัวแรกเท่านั้น; ถ้าไม่มี list จริงให้ raise `ValueError` ที่ระบุว่าไม่พบ `IN (...)` ใน SQL template
- การตรวจ placeholder ใช้ token ของ `_scan_sql` ไม่ค้น regex บน SQL ดิบ; token ใน string/comment ไม่ใช่ placeholder, `::` เป็น cast ไม่ใช่ placeholder และ colon ในเวลา `HH24:MI:SS` ไม่ใช่ placeholder
- คงรูปแบบการ render และ placeholder ที่ถูกต้องเดิม ไม่เปลี่ยน parser ส่วนอื่น

## R5-D5. Worker และ UI thread

- `list_tables`: อ่าน `db_user`, `db_password`, `db_host`, `db_port` (และค่า database type/schema ที่ worker ต้องใช้) จาก Tk Variables บน main thread ก่อนสร้าง worker; ส่งค่า snapshot เป็น arguments/local values ให้ worker และห้ามอ่าน Tk Variable จาก worker
- `temp_engine` ของ Tables ต้อง dispose ใน `finally` ครอบทั้งทางสำเร็จและ exception; SQL Server schema discovery ใช้ `text(...)` พร้อม bind parameter ไม่ interpolate schema ด้วย f-string
- `_execute_query_background`: อ่าน `debug_mode` หนึ่งครั้งบน main thread แล้วส่งค่าเข้า worker; worker ใช้ snapshot ไม่เรียก Tk Variable ซ้ำ
- `test_connection`: เก็บค่าจาก fields ก่อนสร้าง thread; worker ทำเฉพาะงาน connection/คำนวณผล แล้วส่งการเปลี่ยน widget, ตรวจ dialog และแสดงผลไป callback ที่จัดตารางด้วย `root.after`; การอ่าน widget/`winfo_exists` อยู่ใน callback บน main thread
- ไม่เปลี่ยนวิธี cancel query, engine หลัก หรือพฤติกรรมการเชื่อมต่ออื่น

## R5-D6. Preset และการปิดแอป

- `on_closing`: เมื่อ `_is_busy()` เป็น True ถาม Yes/No ก่อน `root.destroy()`; No คือไม่ทำลาย root, Yes คือทำลาย root; เมื่อ idle คงพฤติกรรมเดิม
- บันทึก preset: หา filename ที่ชนกันโดยไม่สน case (สอดคล้อง Windows); เมื่อพบให้ขอยืนยันก่อน write; Cancel ไม่แตะไฟล์; หลังยืนยันใช้ `write_json_atomic`; write failure ต้องไม่ทำลายไฟล์เดิมและไม่แสดง success

## R5-D7. ความเสี่ยงและผลกระทบ

| # | ความเสี่ยง | การควบคุม |
|---|---|---|
| R5-R1 | rollback H-3 ไม่ครบ โดยเฉพาะ dict ของ Job ที่ถูกแก้ in-place หรือ import แบบ replace | snapshot ก่อน mutation และทดสอบ state เดิมทุก caller ใน `test_bugfix_h3.py`; ห้ามส่ง success/UI update เมื่อ save เป็น False |
| R5-R2 | worker อ่าน Tk Variable หลังเริ่ม thread | capture ค่าใน main thread และให้ tests ตรวจ arguments/snapshot รวมถึงแยก callback UI ผ่าน `root.after` |
| R5-R3 | การตรวจ/ทำความสะอาด cell เกิดหลังเขียน Excel | ตรวจ string ก่อน `to_excel`; ทดสอบว่า writer ไม่ได้รับค่าที่ยาวเกิน limit และ Job เป็น warning |
| R5-R4 | parser จับ token ใน comment/string หรือ placeholder เทียม | ใช้ `_scan_sql` และทดสอบกรณี comment, literal, cast และเวลาอย่างชัดเจน |
| R5-R5 | preset overwrite หรือ profile/job write ล้มเหลวทำให้ข้อมูลเดิมหาย | atomic write สำหรับ preset และ rollback ใน memory สำหรับ callers ตาม AC |

## R5-D8. AC → Task

| AC | Task | AC | Task | AC | Task |
|---|---|---|---|---|---|
| R5-AC-1 | R5-T1 | R5-AC-2 | R5-T2, R5-T3 | R5-AC-3 | R5-T4 |
| R5-AC-4 | R5-T5 | R5-AC-5 | R5-T6 | R5-AC-6 | R5-T7 |
| R5-AC-7 | R5-T8 | R5-AC-8 | R5-T9 | R5-AC-9 | R5-T10 |
| R5-AC-10 | R5-T11 | R5-AC-11 | R5-T12 | R5-AC-12 | R5-T13 |
| R5-AC-13 | R5-T14 | | | | |

## R5-D9. Execution sequence

ทำตามลำดับ C-1, H-3, C-2, C-3, H-2, M-1, H-1, M-3, M-2, M-4, M-5, M-6 แล้วจึง regression เต็มชุด โดยแยก H-3 เป็นงาน rollback ของ Profile และ Job; developer ทำทีละ task และหยุดให้ QA รัน focused test ของ task นั้นก่อนเริ่ม task ถัดไป

---

# Round 6 — Bugfix: Import Groups รายงานสำเร็จแม้บันทึก `script_groups.json` ไม่สำเร็จ

> อ้างอิง: `docs/spec.md` หัวข้อ Round 6 (R6-AC-1 ถึง R6-AC-13); R6-Q-1 ใช้คำตอบที่แนะนำ: refresh ด้วย `None` เพื่อคงกลุ่มที่เลือกอยู่เดิม
> Precedent: Round 5 H-3 (R5-D3) — save method คืน `bool`, caller เก็บ snapshot และ rollback เมื่อ `False`, save method เป็นจุดเดียวที่แสดง error
> ขอบเขต: แก้ 2 เมธอดใน `database_connect_gui.py` เท่านั้น ไม่แก้ Round ก่อนหน้า

## R6-D1. แนวทาง

ใช้รูปแบบเดียวกับ R5 H-3: ให้ `save_script_groups()` บอกผลด้วย `bool` และให้ `import_script_groups` (caller เดียวที่อยู่ใน scope) snapshot ก่อน mutate แล้ว rollback เมื่อบันทึกไม่สำเร็จ ไม่เพิ่ม dialog/log ใหม่ — error dialog เดิมใน `save_script_groups()` เพียงพอ (R6-2 out of scope)

เหตุผลที่ snapshot ด้วย `copy.deepcopy` ทั้ง list: `merge_imported_script_groups` แก้ `self.script_groups` in place ทั้ง append, `remove` กลุ่มเดิม (Replace) และ insert ตำแหน่งเดิม การ diff ย้อนกลับซับซ้อนและเสี่ยงกว่า; ขนาดข้อมูล Script Groups เล็ก deepcopy จึงไม่มีต้นทุนที่มีนัย `copy` ถูก import แล้วที่บรรทัด 3 ของ `database_connect_gui.py`

เหตุผลที่ rollback แบบ in-place (`self.script_groups[:] = snapshot`): closure ใน `show_script_groups_dialog` และส่วนอื่นอ้าง list object เดียวกัน การ rebind attribute จะทำให้ผู้อ้างเดิมเห็นข้อมูลค้าง (R6-AC-10)

## R6-D2. ไฟล์ / เมธอดที่แตะ

| ไฟล์ | การเปลี่ยน |
|---|---|
| `database_connect_gui.py` — `save_script_groups` (~4392-4413) | เพิ่ม `-> bool`; ทาง blocked `return False`; ใน `except` หลัง `showerror` `return False`; หลัง `write_json_atomic` สำเร็จ `return True` |
| `database_connect_gui.py` — `import_script_groups` (~4489-4525) | snapshot ก่อน merge, ตรวจผล save, rollback + refresh(`None`) + `return None` เมื่อล้มเหลว |
| `tests/test_r3_script_groups_io.py:876` | mock `side_effect` ต้องคืน `True` (ดู R6-D5) |
| `tests/test_script_groups_block.py:154` | `assertIsNone(stub.save_script_groups())` ต้องเปลี่ยนเป็น `assertIs(..., False)` (ดู R6-D5 / R6-R1) |
| `tests/test_r6_import_save_failure.py` (ใหม่) | R6-AC-1 ถึง R6-AC-11 |

ไม่แตะ: `merge_imported_script_groups`, `parse_script_groups_import`, `_backup_script_groups_once`, `_refresh_script_groups_window`, `sidebar_import_script_groups`, callers อื่นของ `save_script_groups()` ใน `show_script_groups_dialog` (~5038-5147)

## R6-D3. Interface

```python
def save_script_groups(self) -> bool:
    """True = written to disk; False = blocked or write/backup failed (error already shown)."""

def import_script_groups(self, parent: Any) -> Optional[str]:  # signature เดิม
    """... Returns the last imported group name, or None when nothing was imported
    (including when saving failed and the import was rolled back)."""
```

ข้อความ / title / จำนวนครั้งของ `messagebox.showerror` ทั้งสองทางใน `save_script_groups` คงเดิมทุกตัวอักษร (R6-AC-1, R6-AC-2) ไม่ต้องเพิ่ม type hint ให้เมธอดอื่น

## R6-D4. Flow ใน `import_script_groups`

ส่วนก่อน `replace = self._ask_import_mode(...)` / `if replace is None: return None` คงเดิมทั้งหมด (R6-AC-12: Cancel / ไฟล์ผิด / ไม่มี Profile ไม่ snapshot ไม่ save) จากนั้นแทนบรรทัด 4520-4525 ด้วยลำดับนี้

1. `snapshot = copy.deepcopy(self.script_groups)` — **หลัง** ผู้ใช้ยืนยัน และ **ก่อน** `merge_imported_script_groups(...)`
2. `last_name = merge_imported_script_groups(self.script_groups, incoming, profile, replace)` (เดิม)
3. `if not self.save_script_groups():` — ใช้ `not` ไม่ใช่ `is False` เพื่อให้ `mock.Mock()` เดิม (truthy) ยังเป็นทางสำเร็จ
   - `self.script_groups[:] = snapshot` (in-place, R6-AC-10)
   - `self._refresh_script_groups_window(None)` — **หลัง** rollback (R6-AC-9, R6-Q-1); helper เดิมจัดการกรณีหน้าต่างปิด/ไม่เคยเปิดอยู่แล้ว
   - `return None` — ไม่เขียน `📥 Imported`, ไม่ `see`, ไม่มี showinfo (R6-AC-4..8)
4. ทางสำเร็จคงเดิม: `self._refresh_script_groups_window(last_name)` → `results_text.insert(... 📥 Imported ...)` → `see` → `return last_name` (ลำดับ save → refresh → log ตาม R6-AC-11 / R3-AC-12 / R3-AC-15)

ไม่แตะ `_script_groups_save_blocked` / `_script_groups_backup_done` ระหว่าง rollback; ไฟล์บนดิสก์ไม่ถูกเขียนอยู่แล้วเมื่อ save ล้มเหลว `sidebar_import_script_groups()` คืนค่าจาก `import_script_groups` จึงได้ `None` โดยอัตโนมัติ (R6-AC-8)

## R6-D5. ผลกระทบกับ test เดิม

| ไฟล์:บรรทัด | สาเหตุ | การแก้ (ค่าคืน/assertion ที่ขัดกับ spec เท่านั้น) |
|---|---|---|
| `tests/test_r3_script_groups_io.py:876` | `side_effect = lambda: order.append("save")` คืน `None` → หลังแก้กลายเป็นทางล้มเหลว ทำให้ `test_order_save_refresh_log` ล้ม | ให้ side_effect คืน `True` เช่น `lambda: order.append("save") or True`; assertion `order == ["save", ("refresh", "G2"), "log"]` คงเดิม |
| `tests/test_script_groups_block.py:154` | `self.assertIsNone(stub.save_script_groups())` ในกรณี blocked — ขัดกับ R6-AC-1 ที่กำหนดให้คืน `False` | เปลี่ยนเป็น `self.assertIs(stub.save_script_groups(), False)`; assertion อื่นในเทสนั้นคงเดิม **(spec R6-5 ไม่ได้ระบุไฟล์นี้ — แจ้งหัวหน้าแล้ว)** |

ไม่กระทบ: mock `save_script_groups = mock.Mock()` (บรรทัด 689, 1006, 1077, 1132) และ `order.save` (1539) คืน Mock ที่ truthy; test ที่เรียก `save_script_groups()` จริงใน `tests/test_script_groups_backup.py` / `test_script_groups_block.py` ไม่ได้ตรวจค่าคืน (นอกจากบรรทัด 154)

## R6-D6. แนวทาง test (`tests/test_r6_import_save_failure.py`)

- Stub ด้วย `DatabaseConnectorGUI.__new__` ตามรูปแบบ `ImportFlowBase` ใน `tests/test_r3_script_groups_io.py`; patch `app.filedialog`, `app.messagebox`; ใช้ `tempfile` สำหรับไฟล์ import และ `script_groups.json` (patch `_script_groups_path`)
- ทางล้มเหลวใช้ `save_script_groups` **จริง** (ไม่ mock) สองแบบ: `_script_groups_save_blocked = True` และ patch `app.write_json_atomic` ให้ raise `OSError` — เพื่อทดสอบการเชื่อมต่อระหว่างสองเมธอด
- ข้อมูลเริ่มต้นต้องมีกลุ่มของ Profile อื่นและ script ที่มี key ซ้อน (dict/list) แล้วเทียบ `assertEqual(self.stub.script_groups, before)` และ `assertIs(self.stub.script_groups, original_list)`
- R6-AC-9: callback refresh ตรวจ `self.stub.script_groups == before` ภายใน side_effect และ `assert_called_once_with(None)`; กรณีหน้าต่างปิดไม่มี error
- R6-AC-11: ใช้ `save_script_groups` จริงบน tempdir (คืน `True`) สำหรับไม่ชน / Yes / No

## R6-D7. ความเสี่ยง

| # | ความเสี่ยง | การควบคุม |
|---|---|---|
| R6-R1 | test เดิม `tests/test_script_groups_block.py:154` assert ค่าคืน `None` ซึ่งขัด R6-AC-1 — spec R6-5 ระบุแค่ `test_r3_script_groups_io.py:876` | แก้ assertion เป็น `assertIs(..., False)` ใน R6-T1 (ผลโดยตรงของ AC ที่อนุมัติ) — หัวหน้ายืนยันกับผู้ใช้ได้ถ้าต้องการ |
| R6-R2 | rollback แบบ rebind (`self.script_groups = snapshot`) ทำให้หน้าต่าง Script Groups ที่เปิดอยู่อ้าง list เก่า | บังคับ slice assignment และทดสอบ `is` (R6-AC-10) |
| R6-R3 | เช็ก `is False` แทน `not` ทำให้ mock ที่คืน `None` ผ่านเป็นสำเร็จ หรือเช็ก `is True` ทำให้ `mock.Mock()` เดิมล้ม | ใช้ `if not self.save_script_groups():` ตาม spec R6-5 |
| R6-R4 | Snapshot ผิดจุด (ก่อน `_ask_import_mode`) ไม่ผิดผล แต่เพิ่มงานในทาง Cancel; snapshot หลัง merge จะ rollback ไม่ได้ | snapshot ระหว่าง `if replace is None` กับ merge เท่านั้น |
| R6-R5 | callers อื่นของ `save_script_groups()` ยังไม่ตรวจค่าคืน — บัคลักษณะเดียวกันยังมีใน dialog | อยู่นอก scope ตาม R6-2; ไม่แก้รอบนี้ |

## R6-D8. AC → Task

| AC | Task | AC | Task | AC | Task |
|---|---|---|---|---|---|
| R6-AC-1 | R6-T1 | R6-AC-2 | R6-T1 | R6-AC-3 | R6-T1 |
| R6-AC-4 | R6-T2 | R6-AC-5 | R6-T2 | R6-AC-6 | R6-T2 |
| R6-AC-7 | R6-T2 | R6-AC-8 | R6-T2 | R6-AC-9 | R6-T2 |
| R6-AC-10 | R6-T2 | R6-AC-11 | R6-T2 | R6-AC-12 | R6-T2, R6-T3 |
| R6-AC-13 | R6-T3 | | | | |

---

# Round 7 — Bugfix: ผลค้างจาก Round 5 / Round 6 review (R7-1 ถึง R7-5)

> อ้างอิง: `docs/spec.md` หัวข้อ Round 7 (R7-AC-1 ถึง R7-AC-28)
> คำตอบ R7-Q ที่ผู้ใช้อนุมัติ (ค่าแนะนำทั้งหมด): **Q-1** คง `print` ไว้แบบมี guard; **Q-2** ไม่ตรวจ placeholder ใน double quote; **Q-3** Skipped / Failed คงตัวนับเดิม เพิ่มแค่ log warning; **Q-4** หลัง rollback เลือกกลุ่มเดิมตาม **ชื่อก่อนแก้** และ script index ก่อนกด (หรือ index ใกล้สุด); **Q-5** บรรทัด SQL ที่เกิน limit เว้นว่าง
> Precedent: R5-D3 (H-3: save คืน bool + caller rollback), R5-D4 (C-2 / M-1 / M-2), R6-D1 / R6-D4 (deepcopy snapshot + rollback in-place + `if not self.save_script_groups():`)
> ขอบเขต: แก้ `database_connect_gui.py` แบบ minimal diff ไม่ refactor ไม่ rename ไม่แก้ Round ก่อนหน้า; เลขบรรทัดอ้างอิง ณ 2026-11-16

## R7-D1. แนวทาง

ห้าจุดแก้แยกกันไม่ขึ้นต่อกัน แต่ละจุดใช้กลไกที่มีอยู่แล้วในไฟล์:

| R7 | จุดแก้ | กลไกที่ใช้ซ้ำ |
|---|---|---|
| R7-1 | `save_profiles` except branch (~10798-10802) | ครอบ `print` ด้วย `try / except Exception: pass` |
| R7-2 | `run_job` (~9639-9641) | default เดียวกับ `update_jobs_list` (~3921) / `_current_profile_jobs` (~4054) |
| R7-3 | `export_jobs_to_excel` worker (~10325-10633) + module helper ใหม่ 1 ตัว | พฤติกรรม C-2 เดิม (เว้นว่าง + log + `warnings`) และ `write_literal_cell` / `force_literal_strings` เดิม |
| R7-4 | `_detect_sql_placeholders` (~458-494) | token `"string"` จาก `_scan_sql`, `_SQL_BRACED_PLACEHOLDER_RE` |
| R7-5 | 8 closure ใน `show_script_groups_dialog` (~5029-5157) | snapshot / rollback แบบ R6-D4 + `refresh_groups` / `refresh_scripts` เดิม |

เหตุผลหลัก: ทุกจุดคือ contract ที่ Round 5 / 6 ตั้งไว้แล้วแต่ครอบไม่ครบ จึงขยาย contract เดิมไปยังจุดที่ขาด ไม่สร้างกลไกใหม่ ยกเว้น helper นับความยาว UTF-16 ตัวเดียว (R7-3) ที่ spec กำหนดให้ใช้ร่วมกันทุก cell

## R7-D2. R7-1 — `print` ใน failure path ต้องไม่ทำให้ raise

ไฟล์: `database_connect_gui.py` — `save_profiles` (~10798-10802) เท่านั้น

```python
        except Exception as e:
            error_msg = f"❌ Cannot save profile!\n\nError: {str(e)}\n\nPath: {self.config_file}"
            try:
                print(error_msg)
            except Exception:
                pass  # console that cannot encode / is closed must not break return False
            messagebox.showerror("Save Error", error_msg)
            return False
```

- ข้อความ `error_msg`, title `"Save Error"`, จำนวนครั้ง `showerror`, ลำดับ print → showerror → `return False` คงเดิม (R7-AC-1, R7-AC-5 / R7-Q-1)
- `sys.stdout is None`: `print` ของ Python ไม่ทำอะไรเมื่อ `sys.stdout` เป็น `None` จึงผ่านอยู่แล้ว guard ครอบไว้เผื่อ (R7-AC-2)
- `_profiles_save_refused`, `save_jobs` (~9478-9492), `save_script_groups` (~4392-4416) **ไม่มี** `print` ใน failure path → ไม่แก้โค้ด; R7-AC-3 เป็น regression lock (ห้าม developer เพิ่ม `print` ในสามจุดนี้)
- Callers ของ R5-AC-2 (`delete_profile` ~11334, `do_import` ~3656 ฯลฯ) ไม่มี `print` เอง จึงได้ rollback ตาม R5 โดยอัตโนมัติเมื่อ `save_profiles` คืน `False` (R7-AC-4)
- ไม่แก้ `print` อื่น (`:95`, `:218`, `:10812` ฯลฯ) ตาม out of scope

## R7-D3. R7-2 — `run_job` ใช้ default Profile เหมือนรายการ Job

ไฟล์: `database_connect_gui.py` — `run_job` (~9639-9641)

```python
        selected_profile = self.profile_combo.get()
        job_profile = job.get("profile", selected_profile)
        if job_profile != selected_profile:
            ...  # ข้อความ ⛔ และ return เดิม
```

- สลับลำดับ 2 บรรทัด (อ่าน `selected_profile` ก่อน) แล้วใส่ default; ข้อความ `⛔` เดิมคงไว้
- กรณี key `"profile"` มีค่า `None` ชัดเจน: `get` คืน `None` → ไม่ตรง → ปฏิเสธ เหมือน `update_jobs_list` / `_current_profile_jobs` ที่กรองออก (สอดคล้องตาม R7-AC-8)
- ขั้นถัดไป (`_capture_run_target` → `_block_if_profile_mismatch`) ไม่เปลี่ยน (R7-AC-6, R7-AC-7)
- ไม่แตะ `job.get("profile")` ที่ Save / Load Preset (~5253, ~5458, ~5479) ตาม out of scope

## R7-D4. R7-3 — ขยายการตรวจ 32,767 ของ C-2 + นับแบบ UTF-16

### Module helper ใหม่ (วางใต้ `_ensure_excel_row_limit` ~114-120)

```python
EXCEL_MAX_CELL_CHARS = 32_767


def _excel_text_too_long(value: object) -> bool:
    """True when `value` is a str over Excel's cell limit, counted in UTF-16 code units."""
    if not isinstance(value, str):
        return False
    if len(value) <= EXCEL_MAX_CELL_CHARS // 2:  # every code point is at most 2 units
        return False
    if len(value) > EXCEL_MAX_CELL_CHARS:  # every code point is at least 1 unit
        return True
    return len(value.encode("utf-16-le", "surrogatepass")) // 2 > EXCEL_MAX_CELL_CHARS
```

- นิยามตรงกับ spec (`len(value.encode("utf-16-le")) // 2 > 32767`) สำหรับ string ที่ encode ได้; ใช้ `"surrogatepass"` เพื่อไม่ให้ lone surrogate (เช่นจากข้อมูล DB) ทำให้ helper raise จน Job / export ทั้งชุดล้ม — ผลการนับของ string ปกติไม่ต่างกัน
- fast path สองชั้นทำให้ cell ส่วนใหญ่ (สั้น) ไม่ต้อง encode → ต้นทุนเทียบเท่าการเช็ก `len` เดิม
- helper เป็น pure function → test ได้โดยตรงโดยไม่เปิด workbook

### จุดที่ใช้ helper ใน worker ของ `export_jobs_to_excel`

| ตำแหน่ง | ปัจจุบัน | หลังแก้ | ตัวนับ |
|---|---|---|---|
| cell ผลลัพธ์ C-2 (~10512-10515) | `isinstance(value, str) and len(value) > 32767` | `_excel_text_too_long` (ข้อความ log C-2 เดิมไม่เปลี่ยน) | Warning (เดิม) |
| sheet Skipped (~10406-10414) | `DataFrame({"Status", "Message", "Query"})` | ผ่าน `blank_oversized_cells` ก่อนสร้าง DataFrame | Skipped คงเดิม (R7-Q-3) |
| sheet Failed (~10630-10632) | `DataFrame({"Status", "Error", "Query"})` | ผ่าน `blank_oversized_cells` ก่อนสร้าง DataFrame | Failed คงเดิม (R7-Q-3) |
| sheet No Data (~10439-10443) | `write_literal_cell` ทุกบรรทัด | ข้ามการเขียนบรรทัดที่เกิน (แถวว่าง) | เกิน ≥ 1 บรรทัด → `warnings += 1` แทน `ok += 1` |
| SQL annotation (`append_sql_annotation` ~10340-10355, เรียกที่ ~10555) | `write_literal_cell` ทุกบรรทัด | ข้ามบรรทัดที่เกิน, คืน `bool` | OR เข้ากับ `job_warning` → Warning **1 ครั้ง**ต่อ Job |

### Local helper ใหม่ใน `worker()` (วางถัดจาก `force_literal_strings`)

```python
            def sql_line_too_long(job_name: str, line_no: int, line: str) -> bool:
                """Log and return True when one SQL line cannot fit in a cell."""

            def blank_oversized_cells(job_name: str, values: dict) -> dict:
                """Copy of a Skipped / Failed row with oversized values set to "" (one log per column)."""
```

- รูปแบบ log (ต้องมีชื่อ Job, ตำแหน่ง และ `32,767` — ล้อรูปแบบ C-2 ที่ `tests/test_bugfix_c2.py` ตรวจ `Job '<name>'` / `column '<col>'`):
  - column: `⚠️ Warning: Job '<job_name>', column '<col>' is over Excel's 32,767-character limit; the cell was left blank.\n`
  - SQL: `⚠️ Warning: Job '<job_name>', SQL line <n> is over Excel's 32,767-character limit; the cell was left blank.\n` — `<n>` นับจาก 1 ตามลำดับใน `splitlines()`
- `blank_oversized_cells` คืน dict ใหม่ลำดับ key เดิม แล้วสร้าง `pd.DataFrame({k: [v] for k, v in checked.items()})` → เมื่อไม่มีค่าเกิน workbook เหมือนเดิมทุกประการ (R7-AC-15); `force_literal_strings` เรียกต่อเหมือนเดิม
- Skipped: ทั้ง `Status` / `Message` / `Query` ผ่าน helper (Status / Message เป็นค่าคงที่ จึงเกินได้จริงเฉพาะ `Query`) — R7-AC-9
- Failed: ทำภายใน `except Exception as job_err:` เดิม หลังบรรทัด log `Error :` เดิม; log เดิมที่พิมพ์ error เต็มไม่เปลี่ยน — R7-AC-10
- No Data: ใช้ `start_row + line_no` เดิมเพื่อให้บรรทัดอื่นอยู่แถวเดิม; บรรทัดที่เกินแค่ `continue` (ไม่เขียน cell) — R7-AC-11
- `append_sql_annotation(ws, sql_text, job_name) -> bool`: ทางเต็มแผ่น (row limit) log เดิมแล้ว `return False`; ไม่มีบรรทัด → `return False`; เขียนบรรทัดแบบเดียวกับ No Data คืน `True` ถ้ามีบรรทัดถูกเว้น; จุดเรียกเป็น `if append_sql_annotation(ws, sql_text, job_name): job_warning = True` ภายใน `try` เดิม (~10553-10559) ซึ่งอยู่ก่อนการตัดสิน `if job_warning:` (~10610) → log `Status: ⚠️ Warning` และนับ 1 ครั้งแม้ cell ผลลัพธ์ก็เกินด้วย (R7-AC-12)
- นับขอบเขต: 32,767 units เขียนครบ ไม่มี warning; 32,768 → ว่าง + warning (R7-AC-13); `"😀" * 16384` ใน cell ผลลัพธ์ → ว่าง + warning (R7-AC-14)
- ไม่แตะ: ชื่อ column, sheet `Export` ตอน Stop, `write_literal_cell` / `force_literal_strings` (R5-AC-9 / M-2 คงเดิม)

## R7-D5. R7-4 — placeholder ที่เป็นเนื้อหาทั้ง literal `'...'`

ไฟล์: `database_connect_gui.py` — `_detect_sql_placeholders` (~458-494)

เพิ่มกิ่งก่อน `if kind != "punct": continue` ภายใน loop เดิม:

```python
_SQL_COLON_PLACEHOLDER_RE = re.compile(r":[A-Za-z_][A-Za-z0-9_]*")  # module level ข้าง _SQL_BRACED_PLACEHOLDER_RE

        if kind == "string":
            if len(value) >= 2 and value[0] == "'" and value[-1] == "'":
                inner = value[1:-1]
                if (_SQL_COLON_PLACEHOLDER_RE.fullmatch(inner)
                        or _SQL_BRACED_PLACEHOLDER_RE.fullmatch(inner)):
                    placeholders.append(inner)
            continue
```

- เฉพาะ token `"string"` ที่ขึ้นต้นและลงท้ายด้วย `'` → `$tag$` string (ขึ้นต้น `$`) และ `"..."` (kind `ident`, R7-Q-2) ไม่ถูกตรวจ; comment ไม่ถูก yield โดย `_scan_sql` อยู่แล้ว (R7-AC-17)
- `len(value) >= 2` กัน literal ที่ไม่ปิด (`'` ตัวเดียวท้าย SQL); ไม่ trim ช่องว่าง → `' :ACC'`, `':ACC '` ไม่ผ่าน; `':ACC:B'`, `'::x'`, `':1'`, `''`, `'HH24:MI:SS'`, `'text {x}'`, `'a :ACC'` ไม่ fullmatch (R7-AC-17)
- ค่าที่ append คือ `inner` (ไม่มี quote) → รูปเดียวกับ placeholder ไม่มี quote; `dict.fromkeys` เดิมตัดซ้ำตามลำดับพบครั้งแรก เพราะ token ถูกเดินตามตำแหน่ง (R7-AC-16, R7-AC-18)
- `_render_sql_template` ไม่แก้: regex `(?P<quote>['"]?)...(?P=quote)` แทนที่ `':ACC'` / `'{ACC}'` รวม quote อยู่แล้ว (R7-AC-19)
- caller เดียวคือ Load Excel (~13273) → `':ACC'` กลับมาอยู่ใน parameter choices ตาม R7-US-4

## R7-D6. R7-5 — rollback ใน 8 action ของ `show_script_groups_dialog`

ไฟล์: `database_connect_gui.py` — closure ใน `show_script_groups_dialog` (~5029-5157)

### Local helper ใหม่ (วางหลัง `name_taken` ~5023-5026)

```python
        def save_or_rollback(
            snapshot: list,  # deep copy of self.script_groups
            select_name: Optional[str],
            select_index: Optional[int],
        ) -> bool:
            """Save; on failure put self.script_groups back (in place) and redraw from it."""
            if self.save_script_groups():
                return True
            self.script_groups[:] = snapshot
            refresh_groups(select_name=select_name)
            if select_index is not None:
                refresh_scripts(select_index=select_index)
            return False
```

- type hint ใช้ `list` / `dict` เปล่า (ไฟล์ยังไม่ใช้ `list[...]` ที่ใดและ local function ประเมิน annotation ตอน `def`) เพื่อไม่ผูกกับเวอร์ชัน Python
- ใช้ `if self.save_script_groups():` (truthy) ตาม R7-AC-27 / R6-R3 → `mock.Mock()` เดิมยังเป็นทางสำเร็จ
- rollback แบบ in-place → `self.script_groups` เป็น object เดิม (R7-AC-21)
- ต้องเรียก **`refresh_groups`** เสมอ (ไม่ใช่แค่ `refresh_scripts`) เพราะ `state["groups"]` ถือ dict กลุ่มเดิมที่ถูกแทนด้วย deep copy แล้ว; `refresh_groups` สร้าง `state["groups"]` ใหม่จาก `self.script_groups` → action ถัดไปแก้ object ปัจจุบัน (R7-AC-24)
- ต้องส่ง `select_name` **ที่จับไว้ก่อนแก้** เสมอ: `refresh_groups(None)` ใช้ `current_group()["name"]` จาก dict ค้าง ซึ่งใน `rename_group` เป็นชื่อใหม่ไปแล้ว → จะเลือกผิดกลุ่ม (ดู R7-R3)
- `refresh_scripts` clamp index ให้อยู่ในช่วงอยู่แล้ว → "index ใกล้สุด" ตาม R7-Q-4 ได้ฟรี
- error dialog มาจาก `save_script_groups()` เท่านั้น ไม่เพิ่ม dialog / log ใหม่ (R7-AC-23)

### การเปลี่ยนในแต่ละ action

ทุก action: จับ `prev_name` / `prev_index` และ `snapshot = copy.deepcopy(self.script_groups)` **หลัง** ผ่านทาง cancel / ชื่อซ้ำ / `askyesno` / ขอบเขต (R7-AC-26: ทางเหล่านั้นไม่ snapshot ไม่ save) และ **ก่อน** การแก้ข้อมูล; แทน `self.save_script_groups()` ด้วย `if not save_or_rollback(snapshot, prev_name, prev_index): return`; บรรทัด refresh ทางสำเร็จคงเดิมทุกตัวอักษร (R7-AC-25)

| # | Action | `prev_name` (เลือกหลัง rollback) | `prev_index` | จุด snapshot |
|---|---|---|---|---|
| 1 | `new_group` | ชื่อของ `current_group()` ก่อน append (หรือ `None` ถ้ายังไม่มีกลุ่ม) — คงกลุ่มที่เลือกเดิม | `current_script_index()` | หลังเช็ก `name_taken`, ก่อน `append` |
| 2 | `rename_group` | `group["name"]` **ก่อน** `group["name"] = name` | `current_script_index()` | หลังเช็ก `name_taken`, ก่อนกำหนดชื่อ |
| 3 | `delete_group` | `group["name"]` (กลุ่มที่ถูกลบกลับมาและถูกเลือก) | `current_script_index()` | หลัง `askyesno` = Yes, ก่อน `remove` |
| 4 | `add_sql` | `group["name"]` | `current_script_index()` | หลัง `if not result: return` และหลัง `result["created"] = ...`, ก่อน `append` |
| 5 | `add_from_jobs` | `group["name"]` | `current_script_index()` | หลัง `if not chosen: return`, ก่อน loop `append` |
| 6 | `edit_script` | `group["name"]` | `index` | หลัง `if not result: return`, ก่อน `script.pop(...)` |
| 7 | `delete_script` | `group["name"]` | `index` | หลัง `askyesno` = Yes, ก่อน `del` |
| 8 | `move_script` | `group["name"]` | `index` (ตำแหน่งก่อนสลับ) | ภายใน `if 0 <= target < len(scripts):`, ก่อนสลับ |

ไม่แตะ: `save_script_groups`, `import_script_groups` (R6), `_refresh_script_groups_window`, `registered`, `run_group` / `export_group`

## R7-D7. ผลกระทบกับ test เดิม

| ไฟล์ | เปลี่ยน? | เหตุผล |
|---|---|---|
| `tests/test_bugfix_m1.py:21-24` | **ต้องเปลี่ยน** | ค่าคาดหวังเป็น `[":real_bind", "{braced}", "{{double_braced}}", ":literal"]` (R7-AC-20) — แก้แค่ list ที่คาดหวัง ส่วน SQL และกรณี `'HH24:MI:SS'` / `'text {not_a_bind}'` / comment / `value::type` คงเดิม |
| `tests/test_bugfix_c2.py` | ไม่เปลี่ยน | ASCII 32,767 / 32,768 ให้ผลเดิมภายใต้การนับ UTF-16; log C-2 เดิมไม่เปลี่ยน (R7-AC-15) |
| `tests/test_bugfix_m2.py` | ไม่เปลี่ยน | `write_literal_cell` / `force_literal_strings` เดิม (R7-AC-15) |
| `tests/test_bugfix_c1.py`, `tests/test_r4_profile_mismatch.py`, `tests/test_run_entry_block.py`, `tests/test_run_engine.py`, `tests/test_running_banner.py` | ไม่เปลี่ยน | Job ใน test มี `"profile"` ครบ หรือถูก busy block ก่อนถึงจุดเทียบ (`test_run_entry_block.py:181`) (R7-AC-7) |
| `tests/test_bugfix_h3.py` | ไม่เปลี่ยน | ผ่านใน mode (ข) ของ R7-AC-28 ได้ด้วยผล R7-1 |
| `tests/test_r3_script_groups_io.py`, `tests/test_script_groups_block.py`, `tests/test_r6_import_save_failure.py`, `tests/test_script_groups_backup.py` | ไม่คาดว่าต้องเปลี่ยน | ไม่มี test ใดกด 8 action ของหน้าต่าง (ไม่พบ `_ask_group_text` / `_edit_group_script_dialog` / `_pick_jobs_dialog` ใน tests); mock `save_script_groups` เดิมเป็น `mock.Mock()` (truthy) หรือคืน `True` แล้ว — ถ้า QA พบ mock คืน `None` ในทางสำเร็จของ 8 action ให้ปรับเฉพาะค่าคืนเป็น `True` (R7-AC-27) |

## R7-D8. แนวทาง test (สำหรับ qa-tester)

| ไฟล์ใหม่ | แนวทาง |
|---|---|
| `tests/test_r7_console_print.py` | stub `DatabaseConnectorGUI.__new__`; patch `sys.stdout` เป็น `io.TextIOWrapper(io.BytesIO(), encoding="cp874", errors="strict")`, stub ที่ `write` raise `OSError`, และ `None`; patch `app.write_json_atomic` raise `OSError`, `app.messagebox`; `config_file` ใน tempdir ตรวจเนื้อหาไม่เปลี่ยน; R7-AC-4 ใช้ fixture แบบ `tests/test_bugfix_h3.py`; R7-AC-5 ใช้ `io.StringIO` |
| `tests/test_r7_run_job_legacy_profile.py` | ตาม fixture ของ `tests/test_bugfix_c1.py:139`; mock `_capture_run_target` / `_block_if_profile_mismatch` (คืน `True` เพื่อหยุดหลังจุดที่ต้องการ) และตรวจว่าถูกเรียก; matrix R7-AC-8 เทียบกับ `_current_profile_jobs()` จริง |
| `tests/test_r7_excel_cell_limit.py` | ตามแนวทาง `tests/test_bugfix_c2.py` (`_ImmediateThread`, `root.after` เรียกทันที, `openpyxl.load_workbook`); Skipped = `query` ไม่ใช่ SELECT ไม่มี `_export_dataframe`; Failed = `read_sql_dataframe` mock raise; No Data = `_export_dataframe` ว่าง; annotation = `_export_dataframe` มีข้อมูล + query หลายบรรทัด; ข้อความยาวใช้ `"a" * n`, `"ก" * n`, `"😀" * 16384`; ตรวจตัวนับจากบรรทัด `Success: / Warning: / Failed: / Skipped` ของ `on_done`; helper `_excel_text_too_long` test ตรงได้ |
| `tests/test_r7_quoted_placeholder.py` | เรียก `app._detect_sql_placeholders` โดยตรง; R7-AC-19 ใช้ stub ที่ตั้ง `sql_template` และเรียก `_render_sql_template({...})` ตาม `tests/test_database_connect_gui_core.py:542-544` |
| `tests/test_r7_script_groups_dialog_rollback.py` | Tk จริงแบบ `withdraw()` + skip เมื่อไม่มี display ตาม `tests/test_r3_script_groups_io.py:1715-1756`; `APP_DIR` = tempdir; หา button จากข้อความ แล้ว `invoke()` — **ttk button ที่ disabled จะไม่ทำงานเมื่อ `invoke()`** ต้องให้มีกลุ่ม / script ถูกเลือกก่อน (`update_buttons`); สองแบบล้มเหลว: `_script_groups_save_blocked = True` และ patch `app.write_json_atomic` raise `OSError`; spy `save_script_groups` ด้วย `mock.Mock(wraps=...)`; อ่าน listbox ด้วย `get(0, END)` / `curselection()`; ทุก test ที่ทำให้ save ล้มเหลวต้อง patch `messagebox` |

ทุก test ใหม่ห้าม `print` อักขระนอก cp874 ลง stdout จริง (ต้องผ่าน R7-AC-28 mode (ข))

## R7-D9. ความเสี่ยงและผลกระทบ

| # | ความเสี่ยง | การควบคุม |
|---|---|---|
| R7-R1 | R7-1: แก้ `print` อื่นหรือเปลี่ยนข้อความ error เกินขอบเขต | แก้เฉพาะ `save_profiles` except branch; R7-AC-5 lock ว่ายัง print เมื่อ console รองรับ |
| R7-R2 | R7-AC-28 mode (ข) อาจล้มจาก `print` อื่นที่ไม่อยู่ใน scope (เช่น test ใหม่หรือเดิมที่ทำให้โค้ด print อีโมจิโดยไม่ patch `print`) | QA รันทั้งสอง mode ใน R7-T8; ถ้าพบจุดอื่นนอก `save_profiles` ให้รายงานหัวหน้า ไม่แก้เอง (out of scope) |
| R7-R3 | R7-5: rollback แล้วเรียก `refresh_scripts` อย่างเดียว → `state["groups"]` ถือ dict ค้าง; action ถัดไปแก้ object ที่ไม่อยู่ใน `self.script_groups` แล้วบันทึกไม่ติด (R7-AC-24) | `save_or_rollback` เรียก `refresh_groups` เสมอ; test R7-AC-24 ตรวจไฟล์บนดิสก์หลัง action ถัดไป |
| R7-R4 | R7-5: `refresh_groups(None)` หลัง rollback ของ `rename_group` เลือกตามชื่อใน dict ค้าง (ชื่อใหม่) → ไม่พบ → เลือกกลุ่มแรกแทนกลุ่มเดิม | จับ `prev_name` ก่อนแก้ และส่งเข้า `refresh_groups(select_name=prev_name)` ทุก action |
| R7-R5 | R7-5: snapshot ก่อนเช็ก cancel / askyesno → ไม่ผิดผลแต่ปน; snapshot หลังแก้ → rollback ไม่ได้ | ตาราง R7-D6 กำหนดจุด snapshot ต่อ action; R7-AC-26 ตรวจทางยกเลิกไม่เรียก save |
| R7-R6 | R7-3: helper raise (lone surrogate) ภายใน `except job_err` ของ Failed → กลายเป็น fatal error ของ export ทั้งชุด | `encode(..., "surrogatepass")` ไม่ raise; helper รับ `object` และคืน `False` เมื่อไม่ใช่ `str` |
| R7-R7 | R7-3: ต้นทุนการ encode ทุก cell ของ DataFrame ใหญ่ | fast path สองชั้น: encode เฉพาะ string ยาว 16,384-32,767 code points |
| R7-R8 | R7-3: เปลี่ยน UTF-16 ทำให้ cell ผลลัพธ์นอก BMP ที่เดิมผ่านกลายเป็น Warning | เป็นพฤติกรรมที่ spec ตั้งใจ (R7-5 ข้อจำกัด, R7-AC-14) |
| R7-R9 | R7-3: No Data path เดิมไม่มีบรรทัด `Status:`; spec ไม่ได้กำหนดให้เพิ่ม | ไม่เพิ่มบรรทัด Status ใน No Data (log แค่ warning ของบรรทัด SQL + นับ Warning) เพื่อไม่ออกแบบเกิน spec |
| R7-R10 | R7-4: Load Excel จะแสดง placeholder `':ACC'` เพิ่มขึ้นในตัวเลือก — template เดิมที่มีแค่ IN list แต่มี literal รูป `':X'` จะได้ตัวเลือก placeholder แทน IN list | เป็นผลที่ผู้ใช้อนุมัติ (R7-4 "คืน" การตรวจ); กระทบ `tests/test_bugfix_m1.py` เท่านั้น |
| R7-R11 | R7-5 test ต้องใช้ Tk จริง; ใน CI ไม่มี display จะ skip → ไม่มีการตรวจจริง | ตามแนวทาง test เดิม (spec R7-5); เครื่องผู้ใช้ Windows มี display |

## R7-D10. AC → Task

| AC | Task | AC | Task | AC | Task |
|---|---|---|---|---|---|
| R7-AC-1 | R7-T1 | R7-AC-2 | R7-T1 | R7-AC-3 | R7-T1 |
| R7-AC-4 | R7-T1 | R7-AC-5 | R7-T1 | R7-AC-6 | R7-T2 |
| R7-AC-7 | R7-T2 | R7-AC-8 | R7-T2 | R7-AC-9 | R7-T4 |
| R7-AC-10 | R7-T4 | R7-AC-11 | R7-T4 | R7-AC-12 | R7-T4 |
| R7-AC-13 | R7-T3, R7-T4 | R7-AC-14 | R7-T3 | R7-AC-15 | R7-T3, R7-T4 |
| R7-AC-16 | R7-T5 | R7-AC-17 | R7-T5 | R7-AC-18 | R7-T5 |
| R7-AC-19 | R7-T5 | R7-AC-20 | R7-T5 | R7-AC-21 | R7-T6, R7-T7 |
| R7-AC-22 | R7-T6, R7-T7 | R7-AC-23 | R7-T6, R7-T7 | R7-AC-24 | R7-T7 |
| R7-AC-25 | R7-T6, R7-T7 | R7-AC-26 | R7-T6, R7-T7 | R7-AC-27 | R7-T6, R7-T7, R7-T8 |
| R7-AC-28 | R7-T8 | | | | |

---

# Round 8 — Bugfix B1: `load_jobs` ทิ้ง Job ทั้งหมดเมื่อเขียน migration กลับไม่สำเร็จ

> อ้างอิง: `docs/spec.md` หัวข้อ Round 8 (R8-AC-1 ถึง R8-AC-15)
> คำตอบ R8-Q ที่ผู้ใช้อนุมัติ: **Q-1** แจ้งด้วย `print` 1 บรรทัดลง console ครอบ guard แบบ R7-1 (`try / except Exception: pass`) ไม่มี dialog; **Q-2** ลบ `saved_jobs.json.tmp` ที่ค้างแบบ best-effort ใน `load_jobs` เท่านั้น ห้ามแก้ `write_json_atomic`; **Q-3** ไม่ retry
> Precedent: R7-D2 (guard `print` ใน failure path)
> ขอบเขต: แก้ **เฉพาะ `load_jobs`** ใน `database_connect_gui.py` (~9482-9521) แบบ minimal diff; ไม่แตะ `write_json_atomic` (:71-79), `preserve_unreadable_file` (:82-96), `_handle_unreadable_file` (~9523-9545), `save_jobs` (~9547-9561), loader อื่น และบัค B2-B16; เลขบรรทัดอ้างอิง ณ 2026-11-20

## R8-D1. แนวทาง

ต้นเหตุ: `write_json_atomic(self.jobs_file, jobs, indent=4)` (~9513-9514) อยู่ใน `try` เดียวกับ `open` / `json.load` / validate ทำให้ exception ของ "การเขียน" ตกไป `except Exception` (~9518-9521) ที่ออกแบบไว้สำหรับ "ไฟล์อ่านไม่ได้" → `_handle_unreadable_file` + `return []`

แก้โดย **ย้ายการเขียนกลับออกไปนอก `try` เดิม** แล้วครอบด้วย `try` ของตัวเอง:

- `try` เดิม = อ่าน / parse / validate / เติม `"profile"` ใน memory เท่านั้น — `except` เดิมไม่เปลี่ยนแม้แต่ตัวอักษร (R8-AC-12, R8-AC-13)
- `try` ใหม่ = `write_json_atomic` เท่านั้น — ล้มแล้ว: ลบ `.tmp` (best-effort) → `print` (มี guard) → ไปต่อที่ `return jobs`
- ไม่สร้าง helper / method ใหม่, ไม่เพิ่ม flag (R8-Q-3), ไม่มี dialog (R8-Q-1)

เหตุผลที่เลือกย้ายออกนอก `try` แทนการซ้อน `try` ไว้ข้างใน: ทำให้เห็นชัดว่า `except` เดิมจับได้เฉพาะความล้มเหลวของการอ่าน และไม่มีทางที่ exception ใด ๆ จากทางเขียนกลับ (รวม guard ที่อาจถูกแก้ภายหลัง) จะไหลไป `_handle_unreadable_file` ได้อีก

## R8-D2. โค้ดหลังแก้ — `load_jobs` (~9482-9521)

```python
    def load_jobs(self):
        """Load saved jobs from file"""

        if not os.path.exists(self.jobs_file):
            return []

        try:

            with open(self.jobs_file, "r", encoding="utf-8") as f:

                jobs = json.load(f)

            if not isinstance(jobs, list) or not all(isinstance(job, dict) for job in jobs):
                raise ValueError("saved_jobs.json must contain a list of jobs")

            modified = False

            for job in jobs:
                ...  # loop เติม "profile" เดิมทุกตัวอักษร (~9499-9510)

        except Exception as e:
            print(f"Error loading jobs: {e}")
            self._jobs_save_blocked = self._handle_unreadable_file(self.jobs_file, "Saved Jobs", e)
            return []

        # บันทึกกลับเฉพาะกรณีพบข้อมูลเก่า
        if modified:
            try:
                write_json_atomic(self.jobs_file, jobs, indent=4)
            except Exception as e:
                # The file was read fine: keep the jobs (migrated in memory);
                # the next successful save_jobs() writes them to disk.
                try:
                    os.remove(f"{self.jobs_file}.tmp")
                except Exception:
                    pass  # best-effort cleanup only (R8-Q-2)
                try:
                    print(f"Cannot write migrated jobs back to {self.jobs_file}: {e}")
                except Exception:
                    pass  # console that cannot encode / is closed must not break loading

        return jobs
```

รายละเอียดที่ developer ต้องทำตาม:

| จุด | ข้อกำหนด | AC |
|---|---|---|
| ส่วนที่ย้าย | ย้ายเฉพาะ 3 บรรทัด `# บันทึกกลับ...` / `if modified:` / `write_json_atomic(...)` และ `return jobs` ออกไปหลัง `except`; ส่วนอื่นใน `try` (open, validate, loop) ไม่เปลี่ยน | R8-AC-10, R8-AC-11 |
| `except` เดิม | ข้อความ `print(f"Error loading jobs: {e}")`, การเรียก `_handle_unreadable_file(self.jobs_file, "Saved Jobs", e)`, `return []` คงเดิมทุกตัวอักษร (ไม่เพิ่ม guard ให้ print นี้ — นอก scope) | R8-AC-12, R8-AC-13 |
| อาร์กิวเมนต์ write-back | `write_json_atomic(self.jobs_file, jobs, indent=4)` เดิม; ต้องเรียกผ่านชื่อ module-level `write_json_atomic` (ไม่ import ใหม่ ไม่ bind local) เพื่อให้ `mock.patch.object(app, "write_json_atomic", ...)` มีผล | R8-AC-1 (ข), R8-AC-9, R8-AC-11 |
| except ของ write-back | จับ `Exception` (ไม่ใช่ `BaseException`) ไม่ re-raise; ไม่แตะ `self._jobs_save_blocked`, ไม่เรียก `_handle_unreadable_file` / `messagebox` | R8-AC-1, R8-AC-3, R8-AC-4 |
| ลบ `.tmp` | path = `f"{self.jobs_file}.tmp"` (สูตรเดียวกับ `write_json_atomic` :74); ใช้ **`os.remove`** (AC-6 patch `os.remove`) ไม่ใช้ `os.unlink` / `pathlib`; ไม่เช็ก `os.path.exists` ก่อน — แบบ (ข) ไม่มีไฟล์ → `FileNotFoundError` ถูกกลืนโดย `except Exception: pass`; ลบเฉพาะไฟล์นี้ไฟล์เดียว | R8-AC-6 |
| ลำดับ | ลบ `.tmp` ก่อน แล้ว `print` — แต่ละขั้นมี `try` แยกกัน ขั้นหนึ่งล้มไม่ข้ามอีกขั้น | R8-AC-6, R8-AC-7 |
| ข้อความ log | `Cannot write migrated jobs back to {self.jobs_file}: {e}` — 1 บรรทัด, 1 ครั้ง, มี path เต็ม (จึงมี `saved_jobs.json`) และ `str(e)`; ข้อความเป็น ASCII ล้วน ไม่มีอีโมจิ (ลดโอกาสล้มบน cp874) | R8-AC-7 |
| guard ของ `print` | `try: print(...) except Exception: pass` แบบ R7-D2 — ครอบ `UnicodeEncodeError` (path นอก cp874), `OSError` จาก `write`; `sys.stdout is None` → `print` ไม่ทำอะไรอยู่แล้ว | R8-AC-7 |
| ค่าคืน | `jobs` object เดียวกับที่ parse และเติม `"profile"` แล้ว (ทั้งทางสำเร็จและทางเขียนกลับล้ม) | R8-AC-1, R8-AC-2, R8-AC-8 |
| ไม่มี migrate | `modified` เป็น `False` → ไม่เข้า `if` → ไม่เรียก `write_json_atomic` ไม่มี print (พฤติกรรมเดิม) | R8-AC-9, R8-AC-11 |
| ไม่มีไฟล์ | `if not os.path.exists(...)` เดิมไม่แตะ | R8-AC-14 |

หมายเหตุ: `modified` และ `jobs` ถูกกำหนดค่าเสมอเมื่อมาถึงหลัง `except` (ทางที่ไม่ได้กำหนดค่าจะ `return []` ไปแล้ว) จึงไม่มี `UnboundLocalError`

## R8-D3. เส้นทาง exception หลังแก้

| สถานการณ์ | จุดที่ raise | ผล |
|---|---|---|
| ไม่มีไฟล์ | — | `return []` (เดิม) |
| เปิด / decode / `json.load` ไม่ได้, ไม่ใช่ list ของ dict | ใน `try` เดิม | `except` เดิม → print เดิม → `_handle_unreadable_file` → `_jobs_save_blocked` = (สำเนาไม่ได้) → `return []` (เดิม) |
| อ่านได้, ไม่ต้อง migrate | — | `return jobs` ไม่เขียนไฟล์ (เดิม) |
| อ่านได้, migrate, เขียนกลับสำเร็จ | — | ไฟล์ถูกเขียน `indent=4`, `return jobs` (เดิม) |
| อ่านได้, migrate, `write_json_atomic` ล้มก่อนสร้าง `.tmp` (แบบ ข) | `try` ใหม่ | `os.remove` → `FileNotFoundError` กลืน → print guard → `return jobs` |
| อ่านได้, migrate, `os.replace` ล้ม (แบบ ก, `.tmp` ถูกสร้างแล้วและ file handle ปิดแล้วเพราะออกจาก `with` ก่อน `os.replace`) | `try` ใหม่ | `os.remove(.tmp)` สำเร็จ → print guard → `return jobs`; `saved_jobs.json` ไม่เปลี่ยน (`os.replace` ไม่ได้แตะไฟล์ปลายทาง) |
| เหมือนข้างบน แต่ `os.remove` ล้มด้วย | `try` ใหม่ | กลืน → `.tmp` ค้าง (ไม่ทำให้ข้อมูลเสีย — save ครั้งถัดไปเปิด `"w"` ทับ) → print guard → `return jobs` |
| เขียนกลับล้ม และ `print` ล้ม (cp874 strict / `write` raise `OSError`) | guard | กลืน → `return jobs` |

ผลต่อ save ครั้งถัดไป (R8-AC-8): `_jobs_save_blocked` คงค่าที่ caller ตั้งไว้ (`False`) → `save_jobs()` เขียน `self.saved_jobs` ทั้งหมด (มี `"profile"` ครบ) ด้วย `indent` default ของ `save_jobs` → Job เดิมไม่หาย; `load_jobs()` ครั้งถัดไปไม่มี Job ต้อง migrate จึงไม่เรียก `write_json_atomic` (R8-AC-9)

## R8-D4. Data model

ไม่เปลี่ยน schema ของ `saved_jobs.json`, ไม่เพิ่ม attribute / flag ใหม่ใน `DatabaseConnectorGUI`

## R8-D5. ผลกระทบกับ test เดิม

| ไฟล์ | เปลี่ยน? | เหตุผล |
|---|---|---|
| `tests/test_r2_reset_parameter_qa.py:579-590` | ไม่เปลี่ยน | เรียก `load_jobs()` กับไฟล์ที่มี `"profile"` ครบ → ไม่เข้า write-back |
| `tests/test_bugfix_h3.py`, `tests/test_r7_console_print.py` | ไม่เปลี่ยน | ใช้ `save_jobs` กับ `_jobs_save_blocked` / `write_json_atomic` raise — ไม่ผ่าน `load_jobs` (R8-AC-13) |
| `tests/test_script_groups_block.py`, `tests/test_bugfix_m5.py` | ไม่เปลี่ยน | ไม่เรียก `load_jobs` |

ไม่พบ test เดิมที่เรียก `load_jobs` กับไฟล์รุ่นเก่าหรือไฟล์เสีย → ไม่คาดว่ามี test เดิมต้องแก้ (R8-AC-15)

## R8-D6. แนวทาง test (`tests/test_r8_load_jobs_writeback.py`)

- Fixture: stub แบบ `tests/test_r2_reset_parameter_qa.py:579-590` — `GUI.__new__(GUI)`, `jobs_file = os.path.join(tmp, "saved_jobs.json")` ใน `tempfile.TemporaryDirectory()`, `saved_profiles`, `_jobs_save_blocked = False`; ไม่เปิด Tk จริง; patch `app.messagebox` ทุก test (assert `showwarning` / `showerror` / `showinfo` ไม่ถูกเรียก หรือถูกเรียกตาม AC-12)
- "ไฟล์รุ่นเก่า": อย่างน้อย 2 Job — ตัวที่ไม่มี `"profile"` + ตัวที่มี `"profile": "P2"`, มีค่าซ้อน dict / list และอักษรไทย; เขียนด้วย `json.dump(..., ensure_ascii=False)` แล้วเก็บ bytes ไว้เทียบ (R8-AC-5)
- เขียนกลับล้มสองแบบ (ใช้ `subTest` หรือ helper ร่วม): (ก) `mock.patch.object(app.os, "replace", side_effect=PermissionError(...))`; (ข) `mock.patch.object(app, "write_json_atomic", side_effect=OSError(...))`
- R8-AC-3: spy `_handle_unreadable_file` ด้วย `mock.patch.object(GUI, "_handle_unreadable_file")` แล้ว `assert_not_called()`
- R8-AC-4: `os.listdir(tmp)` ไม่มีชื่อที่มี `_unreadable_`; `assertIs(stub._jobs_save_blocked, False)`
- R8-AC-6: แบบ (ก) → `assertFalse(os.path.exists(jobs_file + ".tmp"))`; กรณี `os.remove` ล้ม: patch `app.os.remove` raise `OSError` **ภายใน `with` ที่จบก่อนออกจาก `TemporaryDirectory`** (ไม่เช่นนั้น cleanup ของ tempdir บน Windows จะพังเพราะ `os.remove` ยังถูก patch); ตรวจค่าคืนครบตาม R8-AC-1
- R8-AC-7: `mock.patch.object(app.sys, "stdout", io.StringIO())` (หรือ `contextlib.redirect_stdout`) → นับบรรทัดที่มี `saved_jobs.json` และ `str(error)` = 1; จากนั้นทำซ้ำ R8-AC-1..5 ภายใต้ stdout `io.TextIOWrapper(io.BytesIO(), encoding="cp874", errors="strict")` (ใช้ path / ข้อความ error ที่มีอักขระนอก cp874 เช่นอีโมจิใน message ของ `OSError` เพื่อบังคับ `UnicodeEncodeError`) และ stub ที่ `write` raise `OSError`
- R8-AC-8 / R8-AC-9: ต่อจาก AC-1 — ออกจาก patch แล้ว `stub.saved_jobs = loaded`, append `{"name": "NEW", "profile": "P1", ...}`, `assertIs(stub.save_jobs(), True)`, `json.load` ไฟล์ = Job เดิม (พร้อม `"profile"`) + `NEW`; แล้ว `mock.patch.object(app, "write_json_atomic", wraps=app.write_json_atomic)` เรียก `load_jobs()` อีกครั้ง → `assert_not_called()` และค่าคืนเท่ากับไฟล์
- R8-AC-10: ไม่ patch — ค่าคืนพร้อม `"profile"`, `json.load` ไฟล์ == ค่าคืน, เนื้อไฟล์ตรงกับ `json.dumps(expected, indent=4, ensure_ascii=False)`, ไม่มี `.tmp` / `_unreadable_`, ไม่มี dialog
- R8-AC-11: ไฟล์ที่ทุก Job มี `"profile"` และ `[]` → `wraps` spy `assert_not_called()`, bytes และ `os.stat(...).st_mtime_ns` ไม่เปลี่ยน
- R8-AC-12: 4 แบบ (`[{"name": "a",`, `{}`, `[1]`, bytes `b"\xff\xfe\x00"` ที่ decode UTF-8 ไม่ได้) → `[]`, `showwarning` 1 ครั้ง title `"Saved Jobs not loaded"` ข้อความ `startswith("Cannot read saved_jobs.json:")`, มีสำเนา `saved_jobs_unreadable_*.json` bytes เท่าเดิม, `_jobs_save_blocked` = `False`, `write_json_atomic` spy ไม่ถูกเรียก, ไฟล์เดิมไม่เปลี่ยน; capture stdout ด้วย `io.StringIO` เพราะ `print("Error loading jobs: ...")` เดิมไม่มี guard
- R8-AC-13: JSON เสีย + `mock.patch.object(app, "preserve_unreadable_file", return_value=None)` → `[]`, `_jobs_save_blocked` = `True`, `save_jobs()` คืน `False` และไฟล์ไม่เปลี่ยน
- R8-AC-14: ไม่มีไฟล์ → `[]`, ไม่มี dialog, `os.listdir(tmp) == []`
- ทุก test ห้าม print อักขระนอก cp874 ลง stdout จริง — test ที่ทำให้โค้ด print ต้อง capture stdout เสมอ (R8-AC-15 mode ข)

## R8-D7. ความเสี่ยงและผลกระทบ

| # | ความเสี่ยง | การควบคุม |
|---|---|---|
| R8-R1 | developer แก้เกิน: ใส่ guard ให้ `print("Error loading jobs")` เดิม, แก้ `write_json_atomic` ให้ลบ `.tmp`, หรือแตะ `load_profiles` / `load_script_groups` | ขอบเขต R8-D2 ระบุเฉพาะส่วนที่ย้าย + `try` ใหม่; code review ตรวจ diff ว่าอยู่ใน `load_jobs` เท่านั้น |
| R8-R2 | ใช้ `os.unlink` / `pathlib.Path.unlink` แทน `os.remove` → test R8-AC-6 ที่ patch `os.remove` ไม่มีผล | R8-D2 กำหนด `os.remove` ชัดเจน |
| R8-R3 | ลบ `.tmp` เมื่อ `write_json_atomic` ล้มแบบ (ข) อาจลบ `.tmp` ค้างจาก session อื่น | ยอมรับได้: `.tmp` เป็นไฟล์ชั่วคราวของไฟล์นี้เท่านั้น ไม่มีข้อมูลที่ต้องเก็บ (spec R8-5); `save_jobs` ทำงาน synchronous บน UI thread และ `load_jobs` ถูกเรียกใน `__init__` ก่อน save ใด ๆ จึงไม่ชนกับ save ที่กำลังทำ |
| R8-R4 | migration ค้างใน memory: ถ้าผู้ใช้ไม่ save ใน session นี้ ไฟล์ยังเป็นรุ่นเก่า | ตาม spec R8-5 — เปิดครั้งถัดไปจะ migrate ใหม่ (ผล deterministic เดิม: Profile แรก / `"DEFAULT"`); ไม่ retry ตาม R8-Q-3 |
| R8-R5 | กรณีหายาก: ตอนเปิดแอปครั้งถัดไปลำดับ / ชุด `saved_profiles` เปลี่ยน → Job รุ่นเก่าอาจได้ Profile แรกคนละตัวกับ session ก่อน | เป็นพฤติกรรมเดิมของกฎ "Profile แรก" (นอก scope — spec R8-2) |
| R8-R6 | test R8-AC-6 patch `os.remove` ค้างระหว่าง cleanup ของ `TemporaryDirectory` → error ตอน teardown | R8-D6 กำหนดให้ปลด patch ก่อนออกจาก tempdir |
| R8-R7 | `print("Error loading jobs")` เดิมไม่มี guard: บนเครื่อง cp874 ที่ path มีอักขระนอก cp874 ทางไฟล์เสียยัง raise ได้ | เป็นพฤติกรรมเดิมที่ spec ห้ามแก้ (R8-AC-12 "พฤติกรรมเดิม"); ถ้าต้องการแก้ให้เปิด Round ใหม่ |

## R8-D8. AC → Task

| AC | Task | AC | Task | AC | Task |
|---|---|---|---|---|---|
| R8-AC-1 | R8-T1, R8-T2 | R8-AC-2 | R8-T1, R8-T2 | R8-AC-3 | R8-T1, R8-T2 |
| R8-AC-4 | R8-T1, R8-T2 | R8-AC-5 | R8-T1, R8-T2 | R8-AC-6 | R8-T1, R8-T2 |
| R8-AC-7 | R8-T1, R8-T2 | R8-AC-8 | R8-T1, R8-T2 | R8-AC-9 | R8-T1, R8-T2 |
| R8-AC-10 | R8-T1, R8-T2 | R8-AC-11 | R8-T1, R8-T2 | R8-AC-12 | R8-T1, R8-T2 |
| R8-AC-13 | R8-T1, R8-T2 | R8-AC-14 | R8-T1, R8-T2 | R8-AC-15 | R8-T3 |

---

# Round 9 — Bugfix B2: Load Preset ที่มี element เสียทำให้ Job ของ Profile ปัจจุบันหาย

> อ้างอิง: `docs/spec.md` หัวข้อ Round 9 (R9-AC-1 ถึง R9-AC-16)
> คำตอบ R9-Q ที่ผู้ใช้อนุมัติ: **Q-1** ปฏิเสธทั้งไฟล์; **Q-2** แสดง preset ในรายการตามเดิม แล้ว `showerror` ตอนกด Load; **Q-3** element ต้องเป็น dict ที่ `"name"` และ `"query"` เป็น `str` ที่ `.strip()` แล้วไม่ว่าง; **Q-4** `"jobs": []` / ไม่มี key `"jobs"` ไม่ถือว่าเสีย; **Q-5** exception ไม่คาดคิด → `_restore_jobs_snapshot` + `showerror` พร้อมข้อความ exception ไม่ re-raise; **Q-6** รันเฉพาะ focused ในรอบนี้ (R9-AC-16 เลื่อน)
> ขอบเขต: แก้ **เฉพาะ `load_selected`** (nested function ใน `load_preset_dialog`, `database_connect_gui.py` ~5515-5575) แบบ minimal diff; ไม่แตะส่วนสร้างรายการ preset (~5497-5513), `save_jobs` (~9559-9573), `_restore_jobs_snapshot` (~9575-9580), `write_json_atomic`, `load_jobs` (Round 8 ยังไม่ commit) และบัค B3-B16; เลขบรรทัดอ้างอิง ณ 2026-11-20

## R9-D1. แนวทาง

ต้นเหตุ: `load_selected` แทนที่ `self.saved_jobs` (~5547-5549) แล้ว loop `job["profile"] = current_profile` (~5552-5556) โดยไม่ตรวจ element ก่อน และมี rollback เฉพาะทาง `save_jobs()` คืน `False` (~5558-5562) → element ที่ไม่ใช่ dict ทำให้ `TypeError` หลุดออกจาก callback ขณะที่ `self.saved_jobs` ถูกแทนที่ไปครึ่งทาง

แก้สองชั้น ทั้งหมดอยู่ใน `load_selected`:

1. **Validate ก่อนแตะข้อมูล** (R9-D2) — หลังดึง `jobs = data.get("jobs", [])` และ **ก่อน** คำนวณ `current_profile_jobs` / `askyesno`: วนตรวจทุก element ตามนิยาม R9-Q-3 เจอตัวแรกที่เสีย → `showerror` 1 ครั้ง + `return` (ไม่ถาม ไม่แก้อะไร dialog ยังเปิด)
2. **Rollback exception ที่ไม่คาดคิด** (R9-D3) — ครอบช่วง "กรอง `self.saved_jobs` → loop → `self.save_jobs()`" ด้วย `try / except Exception` ที่เรียก `_restore_jobs_snapshot` เดิมแล้ว `showerror` + `return`; ทาง `save_jobs()` คืน `False` (R5-H-3) คงเดิมทุกประการ โดยย้ายการตรวจค่าคืนออกมานอก `try`

ทางเลือกที่ไม่เลือก:

- **helper ระดับ module** (เช่น `find_invalid_preset_job`) — spec R9-5 จำกัดให้แก้เฉพาะ `load_selected`; การตรวจมี 3 เงื่อนไข ~12 บรรทัด inline ได้ไม่ซับซ้อน และ test ทุก AC ทดสอบผ่านปุ่ม Load อยู่แล้ว จึงไม่สร้าง helper / method ใหม่
- **ตรวจตอนสร้างรายการ** — ขัด R9-Q-2
- **ข้ามเฉพาะ element เสีย** — ขัด R9-Q-1

## R9-D2. จุด validate และข้อความ `showerror`

ตำแหน่ง: ต่อจากบรรทัด `jobs = data.get("jobs", [])` (~5522) ทันที — ก่อน `current_profile = self.profile_combo.get()` (~5524), ก่อน `current_profile_jobs` และก่อน `askyesno` ดังนั้นทาง reject ไม่อ่าน `profile_combo`, ไม่แตะ `self.saved_jobs` และไม่แตะ dict ใน `preset_data`

ลำดับการตรวจต่อ element (หยุดที่ element แรกที่เสีย ลำดับ 1-based ด้วย `enumerate(jobs, start=1)`):

| ลำดับ | เงื่อนไขเสีย | `problem` (ข้อความ ASCII) |
|---|---|---|
| 1 | `not isinstance(job, dict)` (รวม `None`, `1`, `"x"`, `[]`, `True`) | `is not a job object` |
| 2 | `job.get("name")` ไม่ใช่ `str` หรือ `.strip()` ว่าง (รวมไม่มี key) | `has no valid 'name' (must be non-empty text)` |
| 3 | `job.get("query")` ไม่ใช่ `str` หรือ `.strip()` ว่าง (รวมไม่มี key) | `has no valid 'query' (must be non-empty text)` |

หมายเหตุ: `True` ไม่ใช่ `dict` จึงตกข้อ 1; `isinstance(True, str)` เป็น `False` จึงไม่มีกรณี bool หลุดผ่านข้อ 2/3; ไม่ตรวจ key อื่น (รวม `"profile"`) ตาม R9-5

โค้ดหลังแก้ (ส่วนต้นของ `load_selected`):

```python
        def load_selected():
            selection = preset_listbox.curselection()
            if not selection:
                messagebox.showwarning("Warning", "Please select a preset", parent=dialog)
                return

            preset_name, preset_path, data = preset_data[selection[0]]
            jobs = data.get("jobs", [])

            # ตรวจทุก Job ใน preset ก่อนแตะข้อมูลใด ๆ (R9: ปฏิเสธทั้งไฟล์)
            for position, job in enumerate(jobs, start=1):
                if not isinstance(job, dict):
                    problem = "is not a job object"
                elif not isinstance(job.get("name"), str) or not job["name"].strip():
                    problem = "has no valid 'name' (must be non-empty text)"
                elif not isinstance(job.get("query"), str) or not job["query"].strip():
                    problem = "has no valid 'query' (must be non-empty text)"
                else:
                    continue
                messagebox.showerror(
                    "Invalid Preset",
                    f"Preset '{preset_name}' cannot be loaded.\n\n"
                    f"Job #{position} {problem}.\n\n"
                    "Your current jobs were not changed.",
                    parent=dialog,
                )
                return

            current_profile = self.profile_combo.get()
            ...  # current_profile_jobs / askyesno เดิมทุกตัวอักษร
```

| ข้อกำหนด | รายละเอียด | AC |
|---|---|---|
| title | `"Invalid Preset"` | R9-AC-3 |
| ข้อความ | มี `'<preset_name>'` และ `Job #<position>` (position ของ element **แรก** ที่เสีย) + เหตุผล + `Your current jobs were not changed.`; ASCII ล้วนยกเว้นชื่อ preset | R9-AC-3 |
| `parent` | `parent=dialog` (keyword) | R9-AC-3 |
| จำนวนครั้ง | 1 ครั้งต่อการกด Load แล้ว `return` ทันที — ไม่ `askyesno`, ไม่ `save_jobs`, ไม่ `update_jobs_list`, ไม่เขียน `results_text`, ไม่ `showinfo`, ไม่ `dialog.destroy()` | R9-AC-1, R9-AC-2 |
| ไม่มีผลข้างเคียง | ไม่มีการกำหนดค่าใด ๆ ให้ `self.saved_jobs` หรือ dict ของ preset → ดิสก์ไม่เปลี่ยน, `save_jobs()` ภายหลังเขียน Job เดิมครบ, preset ปกติอื่นโหลดได้ใน dialog เดิม | R9-AC-4, R9-AC-5, R9-AC-6 |
| ไม่กระทบ `[]` / ไม่มี `"jobs"` | loop ไม่ทำงาน → เข้าทางเดิม (`with 0 jobs`) | R9-AC-11 |
| ไม่มี selection | `showwarning` เดิมอยู่ก่อน validate | R9-AC-12 |
| ส่วนสร้างรายการ | ไม่แก้ ~5497-5513 → listbox เหมือนเดิม | R9-AC-7 |

## R9-D3. ขอบเขต `try` / rollback และความสัมพันธ์กับ R5-H-3

โค้ดหลังแก้ (ส่วนหลัง `if result:`):

```python
            if result:

                current_profile = self.profile_combo.get()

                saved_jobs_before = self.saved_jobs
                original_jobs = list(saved_jobs_before)
                jobs_snapshot = copy.deepcopy(original_jobs)

                try:
                    # ลบเฉพาะ Job ของ Profile ปัจจุบัน
                    self.saved_jobs = [
                        job for job in self.saved_jobs if job.get("profile") != current_profile
                    ]

                    # เพิ่ม Profile ให้ Job เก่า
                    for job in jobs:

                        job["profile"] = current_profile

                        self.saved_jobs.append(job)

                    saved = self.save_jobs()
                except Exception as e:
                    self._restore_jobs_snapshot(
                        saved_jobs_before, original_jobs, jobs_snapshot
                    )
                    messagebox.showerror(
                        "Load Preset Failed",
                        f"Preset '{preset_name}' was not loaded. "
                        "Your current jobs were not changed.\n\n"
                        f"{type(e).__name__}: {e}",
                        parent=dialog,
                    )
                    return

                if not saved:
                    self._restore_jobs_snapshot(
                        saved_jobs_before, original_jobs, jobs_snapshot
                    )
                    return
                self.update_jobs_list()
                ...  # results_text / showinfo / dialog.destroy() เดิมทุกตัวอักษร
```

| ข้อกำหนด | รายละเอียด | AC |
|---|---|---|
| snapshot | 3 บรรทัด `saved_jobs_before` / `original_jobs` / `jobs_snapshot` อยู่ **นอกและก่อน** `try` ตามโค้ดเดิม (spec R9-5) — `except` จึงอ้างถึงได้เสมอ | R9-AC-8 |
| ขอบเขต `try` | เริ่มที่การกรอง `self.saved_jobs` จบที่ `saved = self.save_jobs()` เท่านั้น; `askyesno`, `update_jobs_list`, `results_text`, `showinfo`, `dialog.destroy()` อยู่นอก `try` (exception หลัง save สำเร็จ = Out of scope ตาม spec R9-2) | R9-AC-8 |
| `except` | จับ `Exception` (ไม่ใช่ `BaseException`), ไม่ re-raise; ลำดับ: `_restore_jobs_snapshot(...)` ก่อน แล้ว `showerror` แล้ว `return` | R9-AC-8 |
| ข้อความ exception | title `"Load Preset Failed"`; ข้อความมี `'<preset_name>'` และ `f"{type(e).__name__}: {e}"` (กรณี `RuntimeError("boom")` → มี `boom`); `parent=dialog`; 1 ครั้ง | R9-AC-8 |
| ทาง `save_jobs()` คืน `False` (R5-H-3) | ตรรกะเดิม (`_restore_jobs_snapshot` + `return`) ย้ายมาอยู่หลัง `try` โดยใช้ตัวแปร `saved`; **ไม่** เพิ่ม `showerror` — error dialog มาจาก `save_jobs` เองเท่านั้น (1 ครั้ง) | R9-AC-13, R9-AC-14 |
| `save_jobs` จริงที่ล้ม | `write_json_atomic` raise ถูกจับใน `save_jobs` แล้วคืน `False` → ไม่ไปถึง `except` ใหม่ → ไม่มี dialog ซ้ำ; `_jobs_save_blocked` เหมือนกัน | R9-AC-14 |
| preset ปกติ | ข้อความ `askyesno`, ลำดับ Job, การตั้ง `"profile"`, `results_text`, `showinfo`, `destroy` เดิมทุกตัวอักษร | R9-AC-9, R9-AC-10 |
| ห้ามแตะ | `save_jobs`, `_restore_jobs_snapshot` ไม่เปลี่ยน; `current_profile` ยังอ่าน `profile_combo.get()` สองครั้งตามเดิม (ไม่ refactor) | R9-AC-15 |

ความสัมพันธ์กับ rollback R5-H-3 เดิม: กลไก restore เดียวกัน (`_restore_jobs_snapshot` คืน list object เดิม + dict object เดิมพร้อมค่าตาม deep-copy) ถูกใช้ทั้งสองทาง — ทาง `False` (เดิม) และทาง exception (ใหม่) — จึงได้คุณสมบัติ "identity + ค่า" เดียวกันที่ `tests/test_bugfix_h3.py` `LoadPresetTests` lock ไว้ และไม่ต้องแก้ test เดิม (`test_load_failure_restores_jobs_without_success_effects` ใช้ `save_jobs` mock ที่คืน `False` → เข้าทาง `if not saved:` เหมือนเดิม; ไม่มี `showerror` ถูก assert ใน test นั้น)

## R9-D4. เส้นทางหลังแก้

| สถานการณ์ | ผล |
|---|---|
| ไม่ได้เลือก | `showwarning` เดิม → return |
| element เสีย (ตำแหน่งใดก็ได้) | `showerror("Invalid Preset", ..., parent=dialog)` → return; ไม่มีอะไรเปลี่ยน |
| preset ปกติ / `[]` / ไม่มี `"jobs"` + ตอบ No | ไม่เปลี่ยน (เดิม) |
| + ตอบ Yes + save สำเร็จ | แทนที่ + บันทึก + success (เดิม) |
| + ตอบ Yes + `save_jobs()` คืน `False` | restore เงียบ (dialog มาจาก `save_jobs`) → return (เดิม) |
| + ตอบ Yes + exception ใน filter / loop / `save_jobs` | restore → `showerror("Load Preset Failed", ...)` → return (ใหม่) |
| + ตอบ Yes + exception หลัง save สำเร็จ (`update_jobs_list` ฯลฯ) | หลุดออกเหมือนเดิม (Out of scope) |

## R9-D5. Data model

ไม่เปลี่ยน schema ของ `saved_jobs.json` / `preset_*.json`, ไม่เพิ่ม attribute / method / helper / flag ใหม่

## R9-D6. ผลกระทบกับ test เดิม

| ไฟล์ | เปลี่ยน? | เหตุผล |
|---|---|---|
| `tests/test_bugfix_h3.py` `LoadPresetTests` | ไม่เปลี่ยน | preset ตัวอย่าง `{"name": "loaded job", "query": "SELECT 2"}` ผ่าน validate; ทาง `False` คงเดิม |
| `tests/test_bugfix_m5.py`, `tests/test_r3_script_groups_io.py` | ไม่เปลี่ยน | ทดสอบ `save_preset_dialog` / Script Groups — ไม่ผ่าน `load_selected` |
| `tests/test_r8_load_jobs_writeback.py` | ไม่เปลี่ยน | ทดสอบ `load_jobs` ซึ่งไม่ถูกแตะ |

## R9-D7. แนวทาง test (`tests/test_r9_load_preset_validation.py`)

- Fixture: import `make_job_stub`, `fake_dialog_widgets` จาก `tests/test_bugfix_h3.py` (หรือคัดลอกรูปแบบเดียวกัน); `stub.profile_combo = _FakeWidget(value="PROD")` (หรือตั้ง `.value`); `stub.jobs_file` ใน `tempfile.TemporaryDirectory()`; `stub._jobs_save_blocked = False`; เขียน `saved_jobs.json` เริ่มต้นด้วย `save_jobs()` จริง แล้วเก็บ bytes; `mock.patch.object(app, "messagebox")` ทุก test; กด Load ด้วย `command()` ของปุ่มแรกที่มี `command`
- "สถานะเริ่มต้น": `P-job0`, `U-job`, `P-job1`, `P-job2` (สลับลำดับ) มีค่าซ้อน dict / list และอักษรไทย; เก็บ list object, dict object แต่ละตัว และ `copy.deepcopy` ไว้เทียบ (นิยาม "`saved_jobs` ไม่เปลี่ยน")
- **การเลือก preset**: `_FakeListbox.curselection` คืน `(0,)` เสมอเมื่อมี item → R9-AC-6 ต้อง override บน instance หลัง `load_preset_dialog()` เช่น `listbox.curselection = lambda: (index,)` โดยหา `index` จาก `listbox.items` ที่ขึ้นต้นด้วยชื่อ preset (อย่าสมมติลำดับของ `os.listdir`); R9-AC-12 ใช้ `lambda: ()`; R9-AC-1..4 ใช้โฟลเดอร์ที่มี preset เดียว
- R9-AC-1..4: matrix ด้วย `subTest` — ไม่ใช่ dict (`None`, `1`, `"x"`, `[]`, `True`); ไม่มี `"query"`; ไม่มี `"name"`; `"query"` / `"name"` เป็น `None`, `5`, `["x"]`, `""`, `"   "`; วาง element เสียตำแหน่งกลาง (`[ok, bad, ok]` → `Job #2`), แรก (`#1`), สุดท้าย (`#3`), กรณี probe `[ok, None]` (`#2`) และกรณี element ที่ 2 และ 3 เสีย (`#2`); assert `showerror` 1 ครั้ง `kwargs["parent"] is dialog`, ข้อความมีชื่อ preset และ `#<n>` (ตรวจด้วย `f"Job #{n} "` เพื่อไม่ให้ `#1` ชนกับ `#12`), `askyesno` / `showinfo` ไม่ถูกเรียก, `save_jobs` spy (`mock.patch.object(stub, "save_jobs", wraps=stub.save_jobs)`) ไม่ถูกเรียก, `update_jobs_list` ไม่ถูกเรียก, `results_text.inserted == []`, dialog ไม่ `destroyed`, bytes ของ `saved_jobs.json` และ preset เท่าเดิม, dict ปกติใน `preset_data` ไม่ถูกเพิ่ม key `"profile"` (จับ object ที่ dialog อ่านด้วย `mock.patch.object(app.json, "load", side_effect=<ฟังก์ชันที่เรียก json.load จริงแล้วเก็บผลลง list>)` ระหว่าง `load_preset_dialog()` แล้วหลังกด Load ตรวจว่า Job ปกติใน object นั้นไม่มี `"profile"`)
- R9-AC-5: หลัง AC-1 (save_jobs จริง) append `new` (`"profile": "PROD"`) → `assertIs(stub.save_jobs(), True)`, `json.load` ไฟล์ = 4 Job เดิมตามลำดับ + `new`
- R9-AC-7: โฟลเดอร์มี preset เสีย + ปกติ + JSON เสีย + `"jobs": 5` → `listbox.items` มี 2 รายการตามรูปแบบ `"<name> (<n> jobs) - <created[:10]>"`; capture stdout ด้วย `io.StringIO` แล้วยืนยันมี `skipped` 2 บรรทัด
- R9-AC-8: `stub.save_jobs = mock.Mock(side_effect=...)` ที่ append ลง `stub.saved_jobs` + แก้ค่าซ้อนของ `U-job` แล้ว `raise RuntimeError("boom")` → identity + ค่า, `showerror` 1 ครั้ง ข้อความมี `boom` และ `parent=dialog`, ไม่มี success, bytes ดิสก์เท่าเดิม
- R9-AC-9..11: ตาม spec (ใช้ `save_jobs` จริง); R9-AC-9 ตรวจข้อความ `askyesno` เต็มตามโค้ดเดิม
- R9-AC-13: `save_jobs` mock แก้ in-place แล้วคืน `False` → `showerror.assert_not_called()`
- R9-AC-14: (ก) `mock.patch.object(app, "write_json_atomic", side_effect=OSError("disk"))` (ข) `stub._jobs_save_blocked = True` → `showerror` 1 ครั้ง ข้อความขึ้นต้น `Failed to save jobs:` / มี `could not be read when the app started`, ไม่มี `showinfo`
- ทุก test ห้าม print อักขระนอก cp874 ลง stdout จริง — ทางที่โค้ด `print` (R9-AC-7) ต้อง capture stdout

## R9-D8. ความเสี่ยงและผลกระทบ

| # | ความเสี่ยง | การควบคุม |
|---|---|---|
| R9-R1 | developer วาง validate หลัง `askyesno` หรือหลังคำนวณ `current_profile_jobs` → ผู้ใช้ถูกถามยืนยันก่อน reject (ผิด R9-AC-2) | R9-D2 ระบุตำแหน่งต่อจาก `jobs = data.get(...)` ทันที; test assert `askyesno.assert_not_called()` |
| R9-R2 | ใส่ `showerror` ในทาง `save_jobs()` คืน `False` หรือครอบ `if not saved` ไว้ใน `try` แล้วรวมทาง → dialog ซ้ำ | R9-D3 แยกทางชัดเจน; R9-AC-13 / R9-AC-14 assert จำนวน `showerror` |
| R9-R3 | `try` กว้างเกินจนครอบ `update_jobs_list` / `showinfo` → rollback memory ทั้งที่ไฟล์ถูกเขียนแล้ว (memory ≠ ดิสก์) | R9-D3 จบ `try` ที่ `saved = self.save_jobs()` |
| R9-R4 | ทาง exception: loop อาจตั้ง `"profile"` ให้ dict ใน `preset_data` ไปบางส่วนก่อน exception — ไม่ถูก restore | ยอมรับตาม spec R9-2 Out of scope (ไม่กระทบไฟล์ preset และ `saved_jobs`; ถูกเขียนทับเมื่อโหลดครั้งถัดไป) |
| R9-R5 | ถ้า `_restore_jobs_snapshot` เองหรือ `messagebox.showerror` raise ภายใน `except` → หลุดออกจาก callback | โอกาสต่ำมาก (in-memory ล้วน); ไม่เพิ่ม guard ซ้อนเพื่อไม่ขยาย scope |
| R9-R6 | preset ที่ผู้ใช้แก้มือแล้วมี `"name"` / `"query"` เป็นค่าไม่ใช่ string (เช่นตัวเลข) ซึ่งเดิมโหลดได้ จะถูกปฏิเสธ | เป็นพฤติกรรมที่ผู้ใช้อนุมัติใน R9-Q-3; ข้อความบอกตำแหน่งและเหตุผลให้แก้ไฟล์ได้ |
| R9-R7 | test ต้องควบคุม `curselection` เอง (`_FakeListbox` คืน `(0,)` เสมอ) และลำดับ `os.listdir` | R9-D7 กำหนดให้หา index จาก `listbox.items` |
| R9-R8 | diff ไปแตะ `load_jobs` (Round 8 ยังไม่ commit) หรือส่วนสร้างรายการ | code review ตรวจว่า hunk ใหม่อยู่ใน `load_selected` เท่านั้น (diff รวมกับ Round 8 จะมี hunk ของ `load_jobs` อยู่แล้ว — ต้องไม่เปลี่ยนจากเดิม) |
| R9-R9 | full suite (R9-AC-16) ไม่ได้รันในรอบนี้ — regression นอก focused อาจไม่ถูกจับ | ผู้ใช้สั่งเลื่อน (R9-Q-6); R9-T3 คงสถานะ `[ ]` |

## R9-D9. AC → Task

| AC | Task | AC | Task | AC | Task |
|---|---|---|---|---|---|
| R9-AC-1 | R9-T1, R9-T2 | R9-AC-2 | R9-T1, R9-T2 | R9-AC-3 | R9-T1, R9-T2 |
| R9-AC-4 | R9-T1, R9-T2 | R9-AC-5 | R9-T1, R9-T2 | R9-AC-6 | R9-T1, R9-T2 |
| R9-AC-7 | R9-T1, R9-T2 | R9-AC-8 | R9-T1, R9-T2 | R9-AC-9 | R9-T1, R9-T2 |
| R9-AC-10 | R9-T1, R9-T2 | R9-AC-11 | R9-T1, R9-T2 | R9-AC-12 | R9-T1, R9-T2 |
| R9-AC-13 | R9-T1, R9-T2 | R9-AC-14 | R9-T1, R9-T2 | R9-AC-15 | R9-T2 |
| R9-AC-16 | R9-T3 | | | | |

---

# Round 10 — Bugfix B3: Export Excel ทำไฟล์ `.xlsx` เดิมหายเมื่อ export ไม่จบ

> อ้างอิง: `docs/spec.md` หัวข้อ Round 10 (R10-AC-1 ถึง R10-AC-21)
> คำตอบ R10-Q ที่ผู้ใช้อนุมัติ (ทุกข้อตามค่าแนะนำ): **Q-1** temp ชื่อไม่ซ้ำ `<stem>.<สุ่ม>.tmp.xlsx` สร้างแบบ exclusive (`tempfile.mkstemp`) ในโฟลเดอร์ปลายทาง; **Q-2** Stop = พฤติกรรมเดิม (workbook บางส่วนแทนที่ปลายทาง แต่ผ่าน temp + `os.replace`); **Q-3** ไฟล์ปลายทางล็อก: ตรวจตอนเริ่มแล้ว fail เร็ว / `os.replace` ล้ม → เก็บ temp ที่สมบูรณ์ไว้ แจ้งทั้งสอง path ไม่ retry; **Q-4** fatal หลังมี sheet → คงไฟล์เดิม ลบ temp; **Q-5** ปรับเฉพาะ harness ของ `tests/test_r4_excel_row_limit.py` ไม่แตะ assertion; **Q-6** ไม่ล้าง temp ค้างอัตโนมัติ; **Q-7** Job ไม่มี `"query"` ยัง fatal แต่แสดงสาเหตุจริง; **Q-8** ไม่รวมจุดเขียนไฟล์อื่น; **Q-9** ลบ temp ไม่ได้ → log 1 บรรทัด; **Q-10** รันเฉพาะ focused (R10-AC-21 เลื่อน)
> ขอบเขต: `database_connect_gui.py` — import ส่วนหัว, helper ระดับ module ใหม่ 4 ตัว (วางต่อจาก `_excel_text_too_long` ~126-134) และ `worker()` ใน `export_jobs_to_excel` (~10430-10806) เท่านั้น; **ไม่แตะ** ส่วนก่อนเริ่ม worker (~10318-10429), `on_done` (~10392-10416), เนื้อ loop ราย Job (~10503-10798), `write_json_atomic`, `load_jobs` / `load_preset_dialog` (Round 8-9 ยังไม่ commit) และ B4-B16; เลขบรรทัดอ้างอิง ณ 2026-11-20
> **หมายเหตุ (2026-11-23, Round 13)**: "ไม่ retry" ใน Q-3 ข้างบน **ถูกแทนที่โดย R12-5** — `os.replace` ที่ล้มด้วย `PermissionError` ถูก retry ตาม `EXPORT_REPLACE_RETRY_DELAYS = (0.2, 0.5, 1.0)` (`_replace_export_with_retry`) ก่อนเข้าทางเก็บ temp + แจ้ง path; error อื่นไม่ retry (pin ด้วย R13-AC-13)

## R10-D1. แนวทาง

ต้นเหตุ: `with pd.ExcelWriter(file_path, engine="openpyxl") as writer:` (~10502) เปิด `file_path` แบบ `"wb"` ตั้งแต่ก่อน Job แรก และ `ExcelWriter.__exit__` เรียก `close()` → save workbook **ทุกครั้ง** แม้ body จะ raise (ทำให้ workbook บางส่วนทับไฟล์เดิม หรือ raise `IndexError: At least one sheet must be visible` ทับ exception ต้นเหตุ)

แก้ 4 จุด (ทั้งหมดใน worker + helper):

1. **ตรวจปลายทางก่อนรัน query** — `_ensure_export_target_writable(file_path)` เปิดไฟล์เดิม (ถ้ามี) ด้วย `os.open(..., O_RDWR)` แบบ **ไม่ truncate ไม่ create** แล้วปิดทันที: Excel ถือ handle แบบ share-read → `PermissionError` ทันที (คง fail เร็วแบบเดิม, R10-AC-14); ไฟล์ยังไม่มี → ไม่ทำอะไร (ไม่สร้างไฟล์ที่ `file_path`)
2. **เขียนลง temp ที่เป็นของเราเอง** — `_create_export_temp_file(file_path)` ใช้ `tempfile.mkstemp(dir=<โฟลเดอร์ปลายทาง>, prefix=f"{stem}.", suffix=".tmp.xlsx")` (exclusive, ไม่ชนไฟล์ผู้ใช้ — R10-AC-3) แล้วห่อ fd เป็น binary file object ส่งให้ `pd.ExcelWriter` **เป็น handle ไม่ใช่ path** — เหตุผล: worker เป็นเจ้าของ handle จึงปิดได้เองเสมอโดยไม่ต้องเรียก `writer.close()` (ซึ่งจะ save) และไม่ต้องแตะ attribute private ของ pandas; บน Windows ต้องปิด handle ก่อนจึงลบ temp ได้
3. **save เฉพาะเมื่อ body จบปกติ** — `_excel_writer_saved_on_success(handle)` เป็น `contextlib.contextmanager` ที่ `yield writer` แล้วเรียก `writer.close()` **เฉพาะเมื่อไม่มี exception**; exception ใน body หลุดผ่าน `yield` โดยไม่ save → ไม่มี `IndexError` บังสาเหตุ (R10-AC-10) และไม่เสียเวลา save workbook ที่จะทิ้ง; ใช้เป็น `with` แทนบรรทัดเดิม จึง **ไม่ต้องเลื่อน indent ของ loop ~290 บรรทัด**
4. **แทนที่ในขั้นเดียว + cleanup ใน `finally`** — ลำดับ save (`writer.close()`) → ปิด handle → `os.replace(temp_path, file_path)`; ทุกทางที่ไม่ถึง `os.replace` สำเร็จ (ยกเว้น `os.replace` ล้มตาม Q-3) ลบ temp ใน `finally` (ครอบ `BaseException` — R10-AC-13) แบบ best-effort ผ่าน `_discard_export_temp`

ทางเลือกที่ไม่เลือก:

- **ส่ง `temp_path` (str) ให้ `pd.ExcelWriter`** — pandas เปิด handle เองและปิดได้ทางเดียวคือ `close()` (save) หรือ `writer._handles` (private); ถ้าไม่ปิด `os.remove` บน Windows ล้มเพราะไฟล์ยังเปิดอยู่
- **คง `with pd.ExcelWriter(...)` แล้ว `try/except` ข้างใน** — ต้องเลื่อน indent ทั้ง loop และ `__exit__` ยัง save / raise `IndexError` อยู่ดี
- **ชื่อ temp ตายตัว / `%TEMP%`** — ขัด R10-Q-1 / R10-AC-2 / R10-AC-3
- **ใช้ `write_json_atomic`** — JSON เท่านั้นและใช้ชื่อตายตัว `<path>.tmp` (Out of scope ตาม spec)

## R10-D2. Helper ระดับ module ใหม่ (วางต่อจาก `_excel_text_too_long` ~134)

Import ที่ต้องเพิ่มที่ส่วนหัวไฟล์ (~2-15): `import contextlib`, `import tempfile` (เรียงตามตัวอักษรในกลุ่ม stdlib) และเติม `BinaryIO`, `Iterator` ใน `from typing import ...` เดิม

```python
def _ensure_export_target_writable(file_path: str) -> None:
    """Fail now (before any query runs) when an existing export target cannot be
    written, e.g. it is open in Excel. Never creates, truncates or changes the file."""
    if not os.path.exists(file_path):
        return
    try:
        fd = os.open(file_path, os.O_RDWR | getattr(os, "O_BINARY", 0))
    except OSError as exc:
        raise type(exc)(
            f"Cannot write to {file_path}. The file may be read-only or open in "
            f"Excel or another program. ({exc.strerror or exc})"
        ) from exc
    os.close(fd)


def _create_export_temp_file(file_path: str) -> Tuple[BinaryIO, str]:
    """Create `<stem>.<random>.tmp.xlsx` next to `file_path` (exclusive) and
    return (open binary handle, temp path)."""
    folder = os.path.dirname(os.path.abspath(file_path))
    stem = os.path.splitext(os.path.basename(file_path))[0] or "export"
    fd, temp_path = tempfile.mkstemp(prefix=f"{stem}.", suffix=".tmp.xlsx", dir=folder)
    try:
        return os.fdopen(fd, "wb"), temp_path
    except BaseException:
        os.close(fd)
        _discard_export_temp(temp_path)
        raise


@contextlib.contextmanager
def _excel_writer_saved_on_success(handle: BinaryIO) -> Iterator[Any]:
    """`pd.ExcelWriter` on `handle` that saves the workbook only when the
    `with` body finishes without an exception."""
    writer = pd.ExcelWriter(handle, engine="openpyxl")
    yield writer
    writer.close()


def _discard_export_temp(temp_path: str) -> Optional[str]:
    """Best-effort delete; returns "<Type>: <message>" when it failed, else None."""
    try:
        os.remove(temp_path)
    except FileNotFoundError:
        return None
    except OSError as exc:
        return f"{type(exc).__name__}: {exc.strerror or exc}"
    return None
```

| ข้อกำหนด | รายละเอียด | AC |
|---|---|---|
| ข้อความ lock ตอนเริ่ม | สร้าง exception ใหม่ชนิดเดียวกับต้นเหตุ (`PermissionError` เมื่อ Excel ถือไฟล์) ข้อความมี `file_path` แบบ **ตัวอักษรตรง** — ห้ามพึ่ง `str(exc)` ของ OS เพราะ path อยู่ในรูป `repr` (backslash ซ้อน) ทำให้ `file_path in message` ไม่จริงบน Windows | R10-AC-14 |
| `os.open` แทน `open(...)` | ไม่ผ่าน `builtins.open`, ไม่มี `O_CREAT` / `O_TRUNC` / `O_APPEND` → ไม่สร้าง ไม่ตัด ไม่เขียน ไม่เปลี่ยน mtime; ไฟล์ read-only ก็ fail เร็วเช่นกัน (เดิม `"wb"` ก็ fail) | R10-AC-1, R10-AC-14, R10-AC-18 |
| ชื่อ temp | `<stem>.<สุ่ม 8 ตัว>.tmp.xlsx` ในโฟลเดอร์เดียวกับ `file_path` (path สัมพัทธ์ → `abspath`); ไม่มี prefix `~$`; `mkstemp` ใช้ `O_EXCL` จึงไม่ทับไฟล์ที่มีอยู่ | R10-AC-2, R10-AC-3 |
| writer | `pd.ExcelWriter(handle, engine="openpyxl")` — pandas ไม่ปิด handle ที่ผู้เรียกส่งมา; `writer.close()` = `book.save(handle)` เนื้อหาเหมือนเดิม | R10-AC-5, R10-AC-19 |
| ลบ temp | `os.remove` (ไม่ใช่ `os.unlink` — test ต้อง patch `os.remove`); ไม่ raise; ไฟล์หายไปแล้วถือว่าสำเร็จ | R10-AC-12 |

## R10-D3. โค้ดหลังแก้ — `worker()` (~10501-10806)

ส่วนต้นของ `worker()` (local helper ทั้งหมด ~10431-10499) **ไม่เปลี่ยน**; แทนที่ `try:` (~10501) / `with pd.ExcelWriter(file_path, ...)` (~10502) / `except` (~10800-10801) ดังนี้ — body ของ `with` (loop ราย Job + sheet `Export`, ~10503-10798) คงเดิมทุกตัวอักษรและ indent เดิม:

```python
            temp_handle: Optional[BinaryIO] = None
            temp_path: Optional[str] = None
            keep_temp = False
            try:
                _ensure_export_target_writable(file_path)
                temp_handle, temp_path = _create_export_temp_file(file_path)
                with _excel_writer_saved_on_success(temp_handle) as writer:
                    for idx, job in enumerate(jobs, 1):
                        ...  # เดิมทุกตัวอักษร รวม Stop (break), job["query"], try ราย Job
                    if not writer.sheets:
                        ...  # sheet "Export" เดิม

                temp_handle.close()  # flush ให้ครบก่อน replace (Windows: ต้องปิดก่อน rename)
                try:
                    os.replace(temp_path, file_path)
                except OSError as replace_err:
                    keep_temp = True
                    fatal_error = (
                        f"{type(replace_err).__name__}: Could not replace {file_path} "
                        f"({replace_err.strerror or replace_err}). The file may be open in "
                        "Excel or another program.\n"
                        f"The completed export was kept at: {temp_path}\n"
                        "Close the file, then rename the kept file to replace it."
                    )
                else:
                    temp_path = None  # ไม่มีอะไรต้องลบแล้ว

            except Exception as e:
                fatal_error = f"{type(e).__name__}: {str(e)}"
            finally:
                if temp_handle is not None and not temp_handle.closed:
                    try:
                        temp_handle.close()
                    except OSError:
                        pass
                if temp_path is not None and not keep_temp:
                    remove_error = _discard_export_temp(temp_path)
                    if remove_error:
                        log(f"⚠️ Could not delete temporary file: {temp_path} ({remove_error})\n")

            elapsed = time_module.time() - start_all
            self.root.after(
                0, lambda: on_done(ok, failed, skipped, warnings, elapsed, fatal_error)
            )
```

### ขอบเขต `try / except / finally` และเส้นทางทั้งหมด

| สถานการณ์ | save | `os.replace` | temp | `fatal_error` → `on_done` | AC |
|---|---|---|---|---|---|
| สำเร็จ (รวม Job Failed / Skipped / No Data ราย Job — ถูกจับใน `try` ราย Job เดิม ไม่ถึงชั้นนี้) | ✔ | ✔ 1 ครั้ง `dst == file_path` | ถูก rename เป็น `file_path` | `None` → `📁 Saved to: <file_path>` + `showinfo` เดิม (temp path ไม่ปรากฏ) | R10-AC-1, 2, 5, 6, 7, 8, 19 |
| Stop ระหว่างทาง / ก่อน Job แรก (`break` = จบ body ปกติ) | ✔ (sheet ที่เสร็จ / sheet `Export`) | ✔ | rename | ข้อความเดิม (B12 ไม่แตะ) | R10-AC-16, 17 |
| fatal ใน body (`KeyError: 'query'` ~10508, error ใน `except job_err` ฯลฯ) ก่อน/หลังมี sheet | ✘ (contextmanager ไม่ถึง `close()`) | ✘ | ลบใน `finally` | `"KeyError: 'query'"` — สาเหตุจริง ไม่มี `IndexError` | R10-AC-9, 10, 3 |
| save ล้ม (`writer.close()` / `Workbook.save` raise) หรือ `temp_handle.close()` ล้ม (flush) | ล้ม | ✘ | ปิด handle (เงียบ) แล้วลบ | `"OSError: disk full"` | R10-AC-11 |
| ลบ temp ไม่ได้ หลัง fatal / save ล้ม | — | ✘ | ค้าง | สาเหตุต้นเหตุเดิม (ไม่ใช่ `PermissionError` ของการลบ); Execution Logs +1 บรรทัด `⚠️ Could not delete temporary file: <temp_path> (...)` (ส่งผ่าน `log()` ก่อน `on_done`) | R10-AC-12 |
| ปลายทางล็อกตอนเริ่ม / read-only | ✘ | ✘ | ยังไม่สร้าง (`_ensure_...` อยู่ก่อน `mkstemp`) | `"PermissionError: Cannot write to <file_path>. ..."`; `read_sql_dataframe` ไม่ถูกเรียก | R10-AC-14 |
| `mkstemp` ล้ม (โฟลเดอร์เขียนไม่ได้) | ✘ | ✘ | ไม่มี | สาเหตุจาก `mkstemp` ก่อนรัน query | (fail เร็วเหมือนเดิม) |
| `os.replace` ล้ม (ล็อกระหว่าง export / read-only) | ✔ | ล้ม | **เก็บไว้** (`keep_temp`) | ข้อความมี `PermissionError`, `file_path`, temp path, วิธีแก้; ไม่มี `showinfo` | R10-AC-15 |
| `BaseException` ที่ไม่ใช่ `Exception` (`SystemExit`, `KeyboardInterrupt`) | ✘ | ✘ | ลบใน `finally` | ไม่ถูกจับ หลุดออกจาก worker เหมือนเดิม (`on_done` ไม่ถูกเรียก — เหมือนเดิม) | R10-AC-13 |
| ปิดแอป / kill process | — | ✘ | อาจค้าง (Q-6) | — ; ไฟล์เดิมไม่ถูกเปิดเพื่อเขียนเลยจึงคงอยู่ | R10-AC-4 |
| ไม่มี Job / ยกเลิก dialog / busy / Profile ไม่ตรง / ไม่มี engine | ไม่เริ่ม worker — โค้ดส่วนนี้ไม่ถูกแตะ | | | ข้อความเดิม | R10-AC-18 |

หมายเหตุสำคัญ:

- **ลำดับ** ต้องเป็น `_ensure_export_target_writable` → `_create_export_temp_file` → `with` → `temp_handle.close()` → `os.replace`; ห้ามสร้าง temp ก่อนตรวจล็อก (ไม่งั้นทาง R10-AC-14 ต้องลบ temp เพิ่มโดยไม่จำเป็น)
- `fatal_error` ของทาง replace ล้มถูกตั้งภายใน `try` (ไม่ raise) จึงไม่ผ่าน `except Exception` และ `finally` เห็น `keep_temp = True` → ไม่ลบ
- ห้ามใช้ `str(replace_err)` ตรง ๆ ในข้อความ — มี `repr` ของทั้งสอง path (backslash ซ้อน); ใช้ `strerror` (fallback `str(exc)` เมื่อ test raise `PermissionError("locked")` ที่ไม่มี `strerror`)
- `on_done` **ไม่เปลี่ยน** — ทาง Q-3 / ทาง fatal ทั้งหมดผ่าน `fatal_error` เดิม: Execution Logs `❌ EXPORT EXCEL FAILED` + `Error: <fatal_error>` และ `showerror("Export Error", f"Export Excel ไม่สำเร็จ:\n\n{fatal_error}")` 1 ครั้ง ไม่มี `showinfo`
- log `📁 File: <file_path>` (~10376) และ `📁 Saved to: <file_path>` (~10408) ใช้ `file_path` ปลายทางตามเดิม — temp path ไม่ถูกส่งเข้า `log()` ในทางสำเร็จ / Stop
- ข้อความใหม่ทั้งหมดใน `fatal_error` เป็น ASCII + path (path อาจเป็นไทย) — ไป `results_text` / `messagebox` เท่านั้น ไม่ `print`
- ตัวแปร `writer` ยังชื่อเดิม (body อ้าง `writer.sheets`, `to_excel(writer, ...)`)

## R10-D4. Data model

ไม่เปลี่ยน schema ใด ๆ, ไม่เพิ่ม attribute บน `DatabaseConnectorGUI`; เพิ่มเฉพาะ helper ระดับ module 4 ตัวใน R10-D2 และ import `contextlib`, `tempfile`, `BinaryIO`, `Iterator`

## R10-D5. ผลกระทบกับ test เดิม

| ไฟล์ | เปลี่ยน? | เหตุผล |
|---|---|---|
| `tests/test_r4_excel_row_limit.py` | **ปรับ harness** (R10-Q-5) — qa-tester ทำ | (1) `asksaveasfilename` คืน `"export.xlsx"` สัมพัทธ์ → `mkstemp` / `os.replace` จะสร้างไฟล์ใน cwd ของ repo: ให้ `run_export` สร้าง `tempfile.TemporaryDirectory()` และคืน `os.path.join(<tmp>, "export.xlsx")`; (2) `_FakeWriter` ไม่มี `close()` → `_excel_writer_saved_on_success` จะ `AttributeError` → fatal → `showerror`: เพิ่ม `def close(self): pass` ใน `_FakeWriter`; `os.replace` ของจริงจะย้าย temp ว่าง (fake writer ไม่เขียน handle) เป็น `export.xlsx` ใน tmp — ไม่ต้อง stub; **ไม่แตะ assertion ใด** |
| `tests/test_r7_excel_cell_limit.py`, `tests/test_bugfix_c2.py`, `tests/test_bugfix_m2.py`, `tests/test_run_engine_batch.py` (`ExportEngineTests`) | ไม่เปลี่ยน | ใช้ pandas / openpyxl จริงใน `TemporaryDirectory`, path ปลายทางยังไม่มีไฟล์ → `_ensure_...` ข้าม, workbook ถูก replace เข้า path เดิม |
| `tests/test_r2_table_data_refresh.py`, `tests/test_run_entry_block.py`, `tests/test_r4_profile_mismatch.py` | ไม่เปลี่ยน | mock `Thread` / ยกเลิก dialog → worker ไม่รัน; ส่วนก่อนเริ่ม worker ไม่ถูกแตะ (AST order test ของ `test_run_entry_block` ยังผ่าน) |
| `tests/test_bugfix_c3.py`, `tests/test_r2_oracle_slash.py`, `tests/test_confirm_destination.py` | ไม่เปลี่ยน | ตรวจ source ของ `export_jobs_to_excel` (`clean_value`, `statement_count > 1`, `_start_stoppable_run`) ซึ่งยังอยู่ใน body ที่ไม่เปลี่ยน |
| `tests/test_r8_load_jobs_writeback.py`, `tests/test_r9_load_preset_validation.py` | ไม่เปลี่ยน | ไม่เกี่ยวกับ export |

## R10-D6. แนวทาง test (`tests/test_r10_export_atomic_write.py`)

- Fixture: คัดลอกรูปแบบ `_ExportCase` ของ `tests/test_r7_excel_cell_limit.py` (stub จาก `__new__`, `root.after` เรียกทันที, `_ImmediateThread`, patch `asksaveasfilename` / `messagebox`) แต่ **ไม่** assert ว่าไม่มี `showerror` ใน helper กลาง; `_stop_event` เป็น `threading.Event()` จริงเพื่อ set ได้; `read_sql_dataframe` เป็น callback ของ test; "ไฟล์เดิม" สร้างด้วย `openpyxl` (sheet `Old` ค่า `"old-value"`) แล้วเก็บ bytes + ชุดชื่อไฟล์ในโฟลเดอร์
- spy `os.replace`: `mock.patch.object(app.os, "replace", wraps=os.replace)` (ต้องอ้าง `os.replace` ตัวจริงก่อน patch); temp path = `call_args[0][0]` หรือไฟล์ใหม่ที่ลงท้าย `.tmp.xlsx`
- R10-AC-1: callback อ่าน bytes ของ `file_path` ทุกครั้งที่ถูกเรียก แล้วเทียบกับไฟล์เดิม
- R10-AC-2: นอกจาก spy `os.replace` แล้ว spy `app.pd.ExcelWriter` (wraps) ยืนยันว่า argument แรก **ไม่ใช่** `file_path` (เป็น file object ที่ `.name` อยู่ในโฟลเดอร์เดียวกัน) และ bytes ของ `file_path` ก่อน `os.replace` (อ่านใน side_effect ของ spy) เท่าไฟล์เดิม — "เปิดด้วย mode เขียน" ตีความเป็นการเปิดที่ truncate / create / เขียนข้อมูล (`_ensure_export_target_writable` เปิด `O_RDWR` แบบไม่เขียนโดยเจตนาตาม spec R10-5 — ดู R10-R2)
- R10-AC-3: วาง `<stem>.tmp.xlsx`, `<stem>.xlsx.tmp` และไฟล์อื่นไว้ก่อน แล้วรัน 3 แบบ (สำเร็จ / fatal ก่อน / fatal หลัง)
- R10-AC-4: `subprocess.Popen([sys.executable, "-c", <child script>])` — child สร้าง stub เดียวกัน (import `database_connect_gui` ด้วย `sys.path` ของ repo), Job ที่สอง callback `print("IN_QUERY", flush=True)` แล้ว `time.sleep(60)`; parent อ่าน stdout จนเจอ `IN_QUERY` → `kill()` → `wait()` → เทียบ bytes; child ห้าม print อักขระนอก ASCII; มี timeout ฝั่ง parent
- R10-AC-5: export ชุดมาตรฐานสองครั้ง (ทับไฟล์เดิม / path ใหม่) เทียบ `sheetnames`, ทุก cell `(value, data_type)` ด้วย `openpyxl`
- R10-AC-9 / 10: Job ไม่มี `"query"` ตำแหน่ง 2 / 1; assert `showerror` 1 ครั้ง title `"Export Error"` มี `KeyError` และ `query`, ไม่มี `IndexError` / `At least one sheet must be visible`
- R10-AC-11: `mock.patch("openpyxl.workbook.workbook.Workbook.save", side_effect=<เขียน bytes บางส่วนลง handle แล้ว raise OSError("disk full")>)`
- R10-AC-12: patch `app.os.remove` ให้ raise `PermissionError` (เฉพาะช่วง export; หลัง test ลบ temp เองเพื่อ cleanup `TemporaryDirectory`); assert log มีบรรทัดที่มี temp path, `showerror` มี `KeyError` / `disk full` และไม่มี `PermissionError`
- R10-AC-13: callback raise `SystemExit` → `assertRaises(SystemExit)` รอบ `export_jobs_to_excel`
- R10-AC-14 / 15 (Windows): `ctypes.windll.kernel32.CreateFileW(path, GENERIC_READ, FILE_SHARE_READ, None, OPEN_EXISTING, 0, None)` ถือ handle แล้ว `CloseHandle` ใน `addCleanup`; skip เมื่อ `sys.platform != "win32"`; AC-15 แบบไม่ขึ้นกับ OS: patch `app.os.replace` ให้ raise `PermissionError("locked")`; ตรวจว่า temp ที่เก็บไว้เปิดด้วย `openpyxl` ได้ครบทุก sheet แล้วลบเองตอน cleanup
- R10-AC-16 / 17: `_stop_event.set()` ใน callback ของ Job ที่ 1 / ก่อนเรียก export
- R10-AC-18: matrix 7 กรณีด้วย `subTest`; ยืนยัน `Thread` ไม่ถูกสร้าง และชุดไฟล์ + bytes ไม่เปลี่ยน
- R10-AC-19: reuse ข้อมูล / ฟังก์ชันตรวจของ `tests/test_r7_excel_cell_limit.py` (import ได้) กับไฟล์เดิมที่มีอยู่ก่อน
- ห้าม print อักขระนอก cp874 ลง stdout จริง

## R10-D7. ความเสี่ยงและผลกระทบ

| # | ความเสี่ยง | การควบคุม |
|---|---|---|
| R10-R1 | **เปลี่ยนพฤติกรรมโดยตั้งใจ**: fatal หลังมี sheet เดิมได้ workbook บางส่วน ตอนนี้ไฟล์เดิมคงอยู่ (Q-4) | ผู้ใช้อนุมัติแล้ว; ข้อความ fatal เดิมยังแสดง |
| R10-R2 | การตรวจล็อกตอนเริ่มเปิด `file_path` ด้วย `O_RDWR` (ไม่ตัด / ไม่เขียน) — ถ้า QA ตีความ R10-AC-2 "ไม่มีการเปิด `file_path` ด้วย mode เขียน" ตามตัวอักษรจะขัด; เป็นวิธีที่ spec R10-5 แนะนำเอง | R10-D6 กำหนดให้ AC-2 ตรวจ "ไม่ truncate / ไม่ create / bytes ไม่เปลี่ยน / `ExcelWriter` ไม่ได้รับ `file_path`"; **หัวหน้าควรยืนยันการตีความนี้** |
| R10-R3 | Excel บางรุ่น / โปรแกรมอื่นเปิดไฟล์แบบ share-write → ผ่านการตรวจตอนเริ่ม แต่ `os.replace` ล้มตอนท้าย | เข้าทาง Q-3: temp สมบูรณ์ถูกเก็บ + แจ้งทั้งสอง path |
| R10-R4 | ต้องการพื้นที่ดิสก์ ~2 เท่าชั่วขณะ (ไฟล์เดิม + temp); OneDrive อาจ sync / ล็อก temp ระหว่างเขียน | save ล้ม → ทาง AC-11 (ไฟล์เดิมคงอยู่); ลบไม่ได้ → log ตาม Q-9 |
| R10-R5 | `os.replace` ไม่เก็บ ACL / attribute / creation time ของไฟล์เดิม; บน POSIX `mkstemp` สร้าง mode `0600` จึงไฟล์ผลลัพธ์อาจสิทธิ์แคบกว่าเดิม | Out of scope ตาม spec R10-2 (แอปเป้าหมายเป็น Windows) |
| R10-R6 | temp ค้างเมื่อปิดแอป / kill / ลบไม่ได้ (ชื่อ `*.tmp.xlsx`) | ยอมรับตาม Q-6 / Q-9 |
| R10-R7 | `_FakeWriter` ของ test_r4 ต้องเพิ่ม `close()` และย้าย path — ถ้า developer รัน test_r4 ก่อน QA ปรับ harness จะล้ม (คาดไว้) | R10-T1 ไม่ใช้ test_r4 ในการตรวจตนเอง; R10-T2 ปรับ harness ก่อนรัน focused |
| R10-R8 | pandas ที่ไม่รองรับ file handle ใน `ExcelWriter` (pandas เก่ามาก) | pandas ≥ 1.2 รองรับ `WriteExcelBuffer`; R10-AC-5 / test_r7 ยืนยันเนื้อหาเหมือนเดิม |
| R10-R9 | diff เลื่อน indent ของ loop ราย Job โดยไม่ตั้งใจ ทำ review ยาก / เสี่ยงแก้เนื้อหา | R10-D3 กำหนดให้ `with` อยู่ indent เดิม; review ตรวจว่า hunk ใน worker มีเฉพาะส่วนหัว / ท้าย |
| R10-R10 | diff ไปแตะ `load_jobs` / `load_preset_dialog` (Round 8-9 ยังไม่ commit) | ห้ามแตะ; review ตรวจว่า hunk ของสองเมธอดนั้นไม่เปลี่ยนจากสถานะปัจจุบัน |
| R10-R11 | full suite (R10-AC-21) ไม่ได้รันรอบนี้ | ผู้ใช้สั่งเลื่อน (Q-10); R10-T3 คง `[ ]`; focused รวม test ที่รัน worker จริงทุกไฟล์ |

## R10-D8. AC → Task

| AC | Task | AC | Task | AC | Task |
|---|---|---|---|---|---|
| R10-AC-1 | R10-T1, R10-T2 | R10-AC-2 | R10-T1, R10-T2 | R10-AC-3 | R10-T1, R10-T2 |
| R10-AC-4 | R10-T1, R10-T2 | R10-AC-5 | R10-T1, R10-T2 | R10-AC-6 | R10-T1, R10-T2 |
| R10-AC-7 | R10-T1, R10-T2 | R10-AC-8 | R10-T1, R10-T2 | R10-AC-9 | R10-T1, R10-T2 |
| R10-AC-10 | R10-T1, R10-T2 | R10-AC-11 | R10-T1, R10-T2 | R10-AC-12 | R10-T1, R10-T2 |
| R10-AC-13 | R10-T1, R10-T2 | R10-AC-14 | R10-T1, R10-T2 | R10-AC-15 | R10-T1, R10-T2 |
| R10-AC-16 | R10-T1, R10-T2 | R10-AC-17 | R10-T1, R10-T2 | R10-AC-18 | R10-T2 |
| R10-AC-19 | R10-T1, R10-T2 | R10-AC-20 | R10-T2 | R10-AC-21 | R10-T3 |

---

# Round 11 — Bugfix B4: Header "target" และ Tables ใช้ค่าจากช่องกรอก ไม่ใช่ connection จริง

> อ้างอิง: `docs/spec.md` หัวข้อ Round 11 (R11-AC-1 ถึง R11-AC-22)
> คำตอบ R11-Q ที่ผู้ใช้อนุมัติ (ทุกข้อตามค่าแนะนำ): **Q-1** เตือนที่ header เท่านั้น (ไม่ block / ไม่ log ตอน Run); **Q-2** ต่อท้าย `target_sub` ด้วย `"  ·  ⚠ ช่อง Details ไม่ตรงกับ connection — กด Connect เพื่อใช้ค่าใหม่"` + สี `#D97706` (= `UI["warn"]`); **Q-3** แก้ Password อย่างเดียวไม่นับว่าไม่ตรง; **Q-4** เทียบ 5 ช่อง `db_type` / `user` / `host` / `port` / `database` หลัง `strip()`, port ตัด `split(":")[0]`, case-sensitive; **Q-5** เก็บ password ใน attribute ส่วนตัวของ GUI ตอน Connect สำเร็จ ผูกกับ engine; **Q-6** มี `info` แต่ไม่มี password ในทาง "ทุก database" ที่ไม่ใช่ Oracle → block ด้วย log `⛔` ให้กด Connect ใหม่; **Q-7** `info is None` → พฤติกรรมเดิม (อ่านช่องกรอก); **Q-8** Save Job / Save Profile ไม่รวม; **Q-9** รันเฉพาะ focused (R11-AC-22 เลื่อน)
> ขอบเขต: `database_connect_gui.py` เท่านั้น — helper ระดับ module 1 ตัว + ค่าคงที่ 1 ตัว (ต่อจาก `RunTarget` ~407-412), `__init__` (บรรทัด `self.engine = None` ~2419 และ closure `_refresh_target_summary` ~2694-2709), `connect_database` (~7715), `_replace_engine` (~7735-7748), method ใหม่ 3 ตัว (ต่อจาก `_capture_run_target` ~7762), `list_tables` (เฉพาะ ~9185-9199), `_reset_profile_connection_state` (~7 บรรทัดรอบ ~11138); **ไม่แตะ** `ConnectionInfo` / `RunTarget` (field), `_capture_run_target`, `_block_if_profile_mismatch`, `_confirm_data_change`, `execute_query`, worker ของ `list_tables` (~9212-9440), `_refresh_conn_badge`, Save Job / Save Profile, hunk ของ Round 8-10 และ B5-B16; เลขบรรทัดอ้างอิง ณ 2026-11-20

## R11-D1. แนวทาง

ต้นเหตุ: มีสองจุดที่อ่าน "ปลายทาง" จากช่องกรอก Details ขณะที่ connection จริงคือ `self._run_target` (snapshot `ConnectionInfo` ตอน Connect)

1. `_refresh_target_summary` (closure ใน `__init__`) สร้างข้อความ header จาก `self.db_host/db_port/db_user/db_name/db_type.get()` ทุก 500 ms
2. `list_tables` อ่าน `db_name` (ตัดสินทาง "ทุก database" / "database ปัจจุบัน" + label คอลัมน์ `Database`) และ user / password / host / port (สร้าง engine ราย DB) จากช่องกรอก

แก้ 3 ส่วน:

1. **Header** — ย้ายเนื้อ closure ไปเป็น method `_update_target_summary(target_main, target_sub) -> bool` ที่ทดสอบได้โดยไม่เปิด Tk: มี `info` → แสดงจาก `info` (รูปแบบเดิม) และถ้าช่องกรอกไม่ตรง (`_details_differ_from(info)`) ต่อท้ายคำเตือน + สี `UI["warn"]`; ไม่มี `info` → แสดงจากช่องกรอกแบบเดิมทุกตัวอักษร; closure เหลือแค่เรียก method แล้ว `after(500, ...)` เมื่อ method คืน `True`
2. **Password ของ connection ปัจจุบัน** — attribute ส่วนตัว `self._connected_password: Optional[Tuple[Any, str]]` เก็บเป็นคู่ `(engine, password)` ตั้งใน `_replace_engine` (parameter ใหม่ `password`) ซึ่งเป็นจุดเดียวที่เปลี่ยน `self.engine` / `self._run_target` อยู่แล้ว → ถูกแทน / ล้างพร้อม engine อัตโนมัติทุกทาง (Connect ใหม่สำเร็จ, Connect ล้ม `_replace_engine(None)`, เรียกตรงจาก test); `_reset_profile_connection_state` ไม่ผ่าน `_replace_engine` จึงล้างเองเพิ่ม 1 บรรทัด; อ่านผ่าน accessor `_connected_password_for(engine)` ที่คืนค่าเฉพาะเมื่อ engine ตรงตัว (`is`) — กัน password ของ engine เก่าหลุดไปใช้กับ engine ใหม่
3. **`list_tables`** — แทนบล็อกอ่านช่องกรอก (~9188-9199) ด้วยการแยกสองทางตาม `target.info`: มี `info` → `db_type` / `current_db_name` / credentials จาก `info` + password จาก accessor (และ block ตาม Q-6 ก่อนแตะ UI); ไม่มี `info` → โค้ดเดิมทุกตัวอักษร (ลำดับการอ่านช่องเหมือนเดิม — `test_bugfix_h1` assert ลำดับ); worker ไม่แก้เลยเพราะใช้ `current_db_name`, `db_type`, `credentials` ที่จับไว้แล้ว

เหตุผลที่เลือก:

- **ผูก password กับ engine ด้วย tuple** แทน attribute เดี่ยว `str` — accessor เทียบ `is` ได้จึงปลอดภัยแม้มีโค้ดอนาคต / test ตั้ง `self.engine` ตรง ๆ โดยไม่ผ่าน `_replace_engine` (เหมือนที่ `_capture_run_target` ทำกับ `_run_target`)
- **ตั้งใน `_replace_engine`** แทนตั้งใน `connect_database` ตรง ๆ — ทุกทางที่แทน engine ล้าง password ให้เองโดยไม่ต้องไล่เติม; test เดิมที่เรียก `_replace_engine(new, ci)` / `_replace_engine(None)` ไม่ต้องแก้ (parameter ใหม่มี default `None`)
- **ไม่ใช้ `engine.url`** (R11-Q-5 ข) และ **ไม่เพิ่ม field ใน `ConnectionInfo` / `RunTarget`** (`test_no_password_like_field`)
- **method คืน `bool`** แทนการปล่อย `tk.TclError` ออกมา — closure รู้ว่าต้องหยุด poll (AC-9) และ test เรียก method ตรงได้โดยไม่ต้องจับ exception

ทางเลือกที่ไม่เลือก:

- อ่าน password จากช่องกรอกเมื่อช่องอื่นตรง (Q-5 ค) — พังเมื่อแก้ Password อย่างเดียว (R11-AC-20)
- เพิ่ม event binding บนช่องกรอกแทน poll — spec R11-5 ให้คง poll 500 ms
- ใช้ `info` ใน `list_tables` แต่คง `self.db_password.get()` — ผสมแหล่งค่า (หัวใจของ B4)

## R11-D2. ของใหม่ระดับ module (ต่อจาก `RunTarget` ~412)

```python
_TARGET_MISMATCH_NOTE = "  ·  ⚠ ช่อง Details ไม่ตรงกับ connection — กด Connect เพื่อใช้ค่าใหม่"


def _target_summary_text(
    db_type: str, user: str, host: str, port: str, database: str
) -> Tuple[str, str]:
    """(main, sub) text of the header target box. Callers pass already-stripped
    user / host / port / database (db_type as given)."""
    main_text = f"{db_type} · {user}@{host}" + (f":{port}" if port else "")
    sub_text = f"Database / Service: {database}" if database else "Database: (default)"
    return main_text, sub_text
```

- ข้อความ 2 บรรทัดคัดลอกจาก `:2701-2702` ทุกตัวอักษร (R11-AC-1 / AC-2 "รูปแบบเดิม")
- `_TARGET_MISMATCH_NOTE` ตรงตาม R11-Q-2 (มี `⚠` และ `Connect`); สีเตือนใช้ `UI["warn"]` ที่มีอยู่แล้ว (`"#D97706"`, ~1165) ไม่สร้างค่าคงที่สีใหม่

## R11-D3. Header — method ใหม่ + closure ที่เหลือ

Method ใหม่ของ `DatabaseConnectorGUI` (วางต่อจาก `_capture_run_target` ~7762):

```python
    def _details_differ_from(self, info: ConnectionInfo) -> bool:
        """True when the Details fields no longer match the connected target
        (R11-Q-4: db_type, user, host, port, database; password / profile ignored)."""
        screen = (
            self.db_type.get().strip(),
            self.db_user.get().strip(),
            self.db_host.get().strip(),
            self.db_port.get().strip().split(":")[0],
            self.db_name.get().strip(),
        )
        connected = (info.db_type.strip(), info.user, info.host, info.port, info.database)
        return screen != connected

    def _update_target_summary(self, target_main: Any, target_sub: Any) -> bool:
        """Show where Run goes under the profile picker.

        Connected with a snapshot: the snapshot, plus a warning when the
        Details fields differ. Otherwise: the Details fields (old behaviour).
        Returns False when the labels are gone (window closed)."""
        try:
            target = self._capture_run_target()
            info = target.info if target is not None else None
            warn = False
            if info is not None:
                main_text, sub_text = _target_summary_text(
                    info.db_type, info.user, info.host, info.port, info.database
                )
                warn = self._details_differ_from(info)
                if warn:
                    sub_text += _TARGET_MISMATCH_NOTE
            else:
                main_text, sub_text = _target_summary_text(
                    self.db_type.get(),
                    self.db_user.get().strip(),
                    self.db_host.get().strip(),
                    self.db_port.get().strip(),
                    self.db_name.get().strip(),
                )
            sub_fg = UI["warn"] if warn else UI["muted"]
            if target_main.cget("text") != main_text:
                target_main.config(text=main_text)
            if target_sub.cget("text") != sub_text:
                target_sub.config(text=sub_text)
            if str(target_sub.cget("fg")) != sub_fg:
                target_sub.config(fg=sub_fg)
        except tk.TclError:
            return False
        return True
```

Closure ใน `__init__` (~2694-2709) หลังแก้ — ชื่อ / ตำแหน่ง / การเรียกครั้งแรก `_refresh_target_summary()` (~2721) คงเดิม:

```python
        def _refresh_target_summary():
            """Read-only: show the connection target under the profile picker."""
            if self._update_target_summary(target_main, target_sub):
                self.root.after(500, _refresh_target_summary)
```

| ข้อกำหนด | รายละเอียด | AC |
|---|---|---|
| ทางไม่มี `info` | `self.db_type.get()` **ไม่ strip** (เหมือน `:2701`), port `strip()` อย่างเดียว **ไม่** `split(":")` — ข้อความเท่าเดิมทุกตัวอักษร; ไม่เรียก `_details_differ_from`; สี `UI["muted"]` | R11-AC-1, R11-AC-7, R11-AC-8 |
| ทางมี `info` | ข้อความจาก `info` เท่านั้น; ช่องกรอกถูกอ่านเฉพาะใน `_details_differ_from` (เพื่อเทียบ) — ค่าในช่องไม่ไปโผล่ในข้อความ | R11-AC-2, R11-AC-3 |
| คำเตือน | ต่อท้าย `target_sub` เท่านั้น; `target_main` ไม่เปลี่ยนสี / ข้อความ; ไม่ระบุช่องที่ต่าง; ไม่เพิ่ม widget | R11-AC-3, R11-Q-2 |
| เกณฑ์ไม่ตรง | ช่องกรอก normalize แบบเดียวกับ `connect_database` (`:7654-7659`, `:7707-7714`): `strip()` ทุกช่อง, port `strip().split(":")[0]`; `info.db_type.strip()` กันกรณี combo มีช่องว่าง; **ไม่** อ่าน `db_password` / `profile_combo`; case-sensitive | R11-AC-4, R11-AC-5, R11-Q-3, R11-Q-4 |
| กลับเป็นปกติ | ไม่มี state ค้าง — ทุก poll คำนวณใหม่จาก `_capture_run_target()` + ช่องกรอก; Connect ใหม่สำเร็จ → `_run_target` ใหม่ตรงกับช่อง; Connect ล้ม / reset → `_capture_run_target()` คืน `None` → ทางไม่มี `info` | R11-AC-6, R11-AC-7 |
| `RunTarget(engine, None)` | `_capture_run_target()` คืน target ที่ `info is None` → ทางช่องกรอกเดิม | R11-AC-8 |
| ไม่ config ซ้ำ | เช็ก `cget("text")` / `cget("fg")` ก่อน `config` ทุกครั้ง (คงแนวเดิม `:2703-2706` + เพิ่ม `fg`) — ค่าคงที่ระหว่าง poll → ไม่มี `config` | R11-AC-9 |
| `tk.TclError` | method คืน `False` ไม่ raise → closure ไม่ตั้ง `after` (เดิม `return` ก่อนถึง `after` `:2707-2709`) | R11-AC-9 |
| การเรียก | header ไม่เขียน Execution Logs / console; อ่าน `_capture_run_target()` ซึ่งไม่แตะ password | R11-AC-18 |

หมายเหตุ: label จริงสร้างด้วย `fg=UI["muted"]` (~2536) จึงไม่มี `config(fg=...)` ใน poll แรกตอนไม่ได้ Connect; Tk คืน `cget("fg")` เป็นสตริงตามที่ตั้ง (`"#64748B"` / `"#D97706"`) — ห่อด้วย `str()` เพราะบาง Tk build คืน `Tcl_Obj`

## R11-D4. Password ของ connection ปัจจุบัน

| จุด | เปลี่ยนอย่างไร | AC |
|---|---|---|
| `__init__` (~2419) | ต่อจาก `self.engine = None` เพิ่ม `self._connected_password: Optional[Tuple[Any, str]] = None` (ระบุ type ไว้ที่จุดประกาศ) | — |
| `_replace_engine` (~7735) | signature → `def _replace_engine(self, engine, info: Optional[ConnectionInfo] = None, password: Optional[str] = None) -> None`; ต่อจากบรรทัด `self._run_target = ...` เพิ่ม `self._connected_password = (engine, password) if engine is not None and password is not None else None`; docstring เติม 1 บรรทัดว่า password ผูกกับ engine และถูกล้างเมื่อ engine ถูกแทน; ส่วน dispose เดิมไม่แตะ | R11-AC-19 |
| `connect_database` ทางสำเร็จ (~7715) | `self._replace_engine(engine, info)` → `self._replace_engine(engine, info, password=password)` — `password` คือค่า `self.db_password.get()` เดิมที่ `:7656` (**ไม่ strip** — ค่าที่ใช้สร้าง engine จริง, spec R11-5) | R11-AC-18, R11-AC-19 (ก), R11-AC-20 |
| `connect_database` ทางล้ม (~7698) | ไม่แก้ — `_replace_engine(None)` ล้าง password ให้แล้ว | R11-AC-19 (ข) |
| `connect_database` ทาง early return (busy / ช่องว่าง `:7663`) | ไม่แก้ — ไม่แตะ engine จึงไม่แตะ password (สอดคล้อง test `test_run_target` ~330 ที่ connection เดิมคงอยู่) | — |
| `_reset_profile_connection_state` (~11138) | ต่อจาก `self._run_target = None` เพิ่ม `self._connected_password = None`; ทางรอ busy / ทาง reconnect แล้ว (`return` ต้นเมธอด) ไม่แตะ | R11-AC-19 (ค) |
| accessor ใหม่ (ต่อจาก `_capture_run_target`) | ด้านล่าง | R11-AC-16, R11-AC-19 |

```python
    def _connected_password_for(self, engine: Any) -> Optional[str]:
        """Password used to create `engine` at Connect; None when `engine` was not
        created by connect_database (or the connection was replaced / cleared).
        Kept in memory only - never logged, printed or saved."""
        stored = getattr(self, "_connected_password", None)
        if stored is None or engine is None or stored[0] is not engine:
            return None
        return stored[1]
```

- `getattr(..., None)` เพราะ stub จาก `__new__` ใน test เดิมไม่มี attribute นี้ (R11-AC-21 — แก้ที่โค้ด ไม่แก้ test)
- "ล้างจริง ไม่ใช่แค่ถูกบัง" (R11-AC-19 ข / ค) = `self._connected_password is None` หลัง Connect ล้ม / reset — test ตรวจได้ทั้งผ่าน accessor และ attribute ตรง
- ห้ามใส่ password ใน `results_text`, `print`, `_write_run_log`, ข้อความ exception ใหม่, หรือ `repr` ของ object ใด; ไม่เพิ่ม field ใน `ConnectionInfo` / `RunTarget`
- ชื่อ attribute ไม่อยู่ใน dataclass → `test_no_password_like_field` ไม่เกี่ยว; `test_password_never_stored` ตรวจเฉพาะ `ConnectionInfo` / `RunTarget` → ผ่านโดยไม่แก้

## R11-D5. `list_tables` — แหล่งค่า (~9185-9199)

ส่วนก่อนหน้า (`_block_if_busy` → `_capture_run_target` → `_block_if_profile_mismatch` → `if not self.engine`) และทุกอย่างตั้งแต่ `self.results_text.insert(... "Fetching database schema information...")` (~9201) ลงไป **ไม่เปลี่ยน**; แทนที่ ~9185-9199 ด้วย:

```python
        # The engine + target of this run, taken once on the main thread;
        # the worker below never reads self.engine or the Details fields
        engine = target.engine
        info = target.info
        if info is not None:
            # Connected through connect_database: everything comes from the
            # snapshot + the password of this engine (never the Details fields)
            db_type = info.db_type
            current_db_name = info.database
            password = self._connected_password_for(engine)
            if password is None and not current_db_name and db_type != "Oracle":
                self.results_text.insert(
                    tk.END,
                    "⛔ Tables ไม่ได้เริ่มงาน: ไม่มีรหัสผ่านของ connection ปัจจุบัน "
                    "— กด Connect ใหม่แล้วลองอีกครั้ง\n",
                )
                self.results_text.see(tk.END)
                return
            connection_credentials = (info.user, password or "", info.host, info.port)
        else:
            db_type = self.db_type.get()

            # Check if user wants to list all databases or just current connection
            current_db_name = self.db_name.get().strip()
            connection_credentials = (
                ...  # 4 บรรทัดเดิม ~9193-9198 ทุกตัวอักษร (getattr db_user / db_password / db_host / db_port)
            )
```

| ข้อกำหนด | รายละเอียด | AC |
|---|---|---|
| ลำดับการอ่านทาง `info is None` | `db_type` → `db_name` → `db_user` → `db_password` → `db_host` → `db_port` → `start` (เท่าเดิม — `test_bugfix_h1` assert ลิสต์นี้); `thread.args == ((user, password, host, port),)` รูปเดิม | R11-AC-17 |
| ทาง `info` ไม่อ่านช่องกรอก | ไม่เรียก `get()` ของ `db_name` / `db_user` / `db_password` / `db_host` / `db_port` / `db_type` ทั้งใน main thread และ worker (worker ใช้ตัวแปรที่จับไว้อยู่แล้ว) | R11-AC-11, R11-AC-12, R11-AC-13 |
| credentials | `(info.user, password, info.host, info.port)` — ลำดับเดียวกับ tuple เดิม worker เรียก `get_connection_string(db_type, credentials[0..3], database)` ได้ `("MySQL", "app", "pw-uat", "uat-db", "3306", "d1")` | R11-AC-11, R11-AC-20 |
| เลือกทาง / label / flag | `current_db_name = info.database` → `if not current_db_name` (ทุก database), `"Database": current_db_name`, `bool(current_db_name)` ใน worker ใช้ค่านี้โดยไม่ต้องแก้ worker | R11-AC-12 |
| จับก่อน `start()` | ค่าทั้งหมดเป็น local / thread args ก่อน `thread.start()`; Connect ใหม่ภายหลังเปลี่ยน `self._connected_password` แต่ไม่เปลี่ยน tuple ที่ส่งไปแล้ว | R11-AC-14 |
| Oracle / database ปัจจุบัน | ไม่ต้องใช้ password → ไม่ block แม้ accessor คืน `None` (`password or ""` ส่งเข้า tuple แต่ worker ไม่ใช้); Oracle ใช้ `inspect(engine)` เดิม | R11-AC-15 |
| block (Q-6) | เงื่อนไข: มี `info` + `info.database == ""` + `db_type != "Oracle"` + accessor คืน `None`; อยู่ **ก่อน** "Fetching..." / `inspect_btn.config(... "⏳ Loading...")` / `root.update()` / loading dialog / `Thread`; Execution Logs 1 บรรทัดขึ้นต้น `⛔ Tables ไม่ได้เริ่มงาน` (รูปแบบเดียวกับ `_block_if_profile_mismatch` `:8111-8116`) ไม่มี `messagebox` | R11-AC-16 |
| ข้อความ block | ไม่มี password / host / user — ASCII + ไทย + `⛔` (ไป `results_text` เท่านั้น ไม่ `print`) | R11-AC-16, R11-AC-18 |
| worker (~9212-9440) | **ไม่แก้แม้แต่ตัวเดียว** — print เดิมพิมพ์เฉพาะชื่อ DB / schema / exception ไม่มี credentials | R11-AC-18 |

## R11-D6. Data model

- ไม่เปลี่ยน `ConnectionInfo` / `RunTarget` / schema ไฟล์ใด
- attribute ใหม่บน `DatabaseConnectorGUI`: `_connected_password: Optional[Tuple[Any, str]]` (memory เท่านั้น, ไม่ถูก save ลง `db_profiles.json` / `saved_jobs.json` / run log)
- ของใหม่ระดับ module: `_TARGET_MISMATCH_NOTE: str`, `_target_summary_text(...) -> Tuple[str, str]`
- method ใหม่: `_details_differ_from(info) -> bool`, `_update_target_summary(target_main, target_sub) -> bool`, `_connected_password_for(engine) -> Optional[str]`
- signature เปลี่ยน (เข้ากันได้ย้อนหลัง): `_replace_engine(self, engine, info=None, password=None)`

## R11-D7. ผลกระทบกับ test เดิม

| ไฟล์ | เปลี่ยน? | เหตุผล |
|---|---|---|
| `tests/test_run_target.py` (`test_no_password_like_field`, `test_password_never_stored`, `ReplaceEngineTests`, `ResetProfileTests`, `CaptureRunTargetTests`) | ไม่เปลี่ยน | ไม่เพิ่ม field ใน dataclass; `_replace_engine` เพิ่ม parameter มี default; `_reset_profile_connection_state` แค่ล้างเพิ่ม; `_capture_run_target` ไม่แตะ |
| `tests/test_bugfix_h1.py` | ไม่เปลี่ยน | stub ใช้ `RunTarget(engine, None)` → ทางเดิม ลำดับการอ่าน + `thread.args` เท่าเดิม |
| `tests/test_run_engine_batch.py` — `test_current_db_inspects_start_engine`, `test_no_info_reads_db_type_before_thread_starts` | ไม่เปลี่ยน | ไม่มี `info` → ทางเดิม |
| `tests/test_run_engine_batch.py` — `test_db_type_from_info_and_inspect_gets_a` | ไม่เปลี่ยน | `info` Oracle + `database=""` → ไม่ต้องใช้ password ไม่ block; stub ไม่มี `db_user` ฯลฯ ก็ไม่เป็นไรเพราะทาง `info` ไม่อ่าน |
| `tests/test_run_engine_batch.py` — **`test_info_db_type_wins_over_screen_at_start`** | **ขัดกับ spec — ดู R11-R1** | `info` PostgreSQL + `database=""` + stub ไม่มี password เก็บไว้ = กรณี R11-AC-16 ตรงตัว → ตาม Q-6 ต้อง block ไม่เริ่ม thread แต่ test assert ว่า thread ถูกสร้าง 1 ตัว (`_start` ~360) → **ล้ม** ซึ่งขัด R11-AC-21 "ผ่านโดยไม่แก้ test" |
| `tests/test_list_tables_stop.py`, `tests/test_r4_profile_mismatch.py`, `tests/test_run_entry_block.py`, `tests/test_bugfix_c1.py`, `tests/test_profile_connect_block.py`, `tests/test_confirm_destination.py`, `tests/test_profile_password.py` | ไม่เปลี่ยน | ไม่มี `_run_target` / มี `info.database="db"` (ทาง database ปัจจุบัน) / block ก่อนถึงส่วนที่แก้; AST check ของ `test_profile_connect_block` (statement แรกของ `connect_database` = `if self._block_if_busy`) และ `test_confirm_destination` (`list_tables` ไม่อยู่ใน `EXPECTED`) ไม่กระทบ |
| `tests/test_r8_load_jobs_writeback.py`, `tests/test_r9_load_preset_validation.py`, `tests/test_r10_export_atomic_write.py` | ไม่เปลี่ยน | ไม่เกี่ยว |

## R11-D8. แนวทาง test (`tests/test_r11_connection_target_snapshot.py`)

- Stub จาก `DatabaseConnectorGUI.__new__` แบบ `tests/test_run_target.py::make_stub` (ใช้ `_FakeEntry` ที่มี `forbid_get` แบบ `tests/test_bugfix_h1.py::_Variable` + ลงบันทึกการ `get`); "snapshot UAT" ตั้งด้วย `stub._replace_engine(engine_uat, info, password=...)` หรือกำหนด `_run_target` ตรง (กรณีไม่มี password)
- Label ปลอม: เก็บ `text` / `fg`, `cget(key)`, `config(**kw)` นับจำนวนครั้ง; แบบ `raise tk.TclError` สำหรับ AC-9
- AC-1..8: เรียก `stub._update_target_summary(main, sub)` ตรง; สีเตือน assert `sub.fg == app.UI["warn"]` และ `!= app.UI["muted"]`; ข้อความ assert ว่ามี `⚠` และ `Connect` (ไม่ผูกทั้งประโยค)
- AC-4: `subTest` 5 ช่อง + กรณี `db_password` / `profile_combo` ต่าง (ไม่มีคำเตือน และ `db_password.get` ไม่ถูกเรียก)
- AC-6 (ข) / AC-7 / AC-19: `connect_database` จริงด้วย `mock.patch.object(app, "create_engine", return_value=<sqlite engine จริง หรือ MagicMock ที่ connect ได้>)` + `mock.patch.object(app, "messagebox")`; ทางล้ม `create_engine` `side_effect=RuntimeError`; ต้อง stub `_track_engine_connections`, `_show_connection_error`, `_block_if_busy`
- AC-9 closure: ดึง `_refresh_target_summary` จาก `GUI.__init__` ด้วย AST แบบ `tests/test_running_banner.py` (~344) โดยมี free names `self`, `target_main`, `target_sub` แล้วยืนยันว่า `root.after` ไม่ถูกเรียกเมื่อ label raise `TclError` และถูกเรียก `(500, <closure>)` เมื่อปกติ
- AC-10: `execute_query` แบบ `tests/test_confirm_destination.py` (`_execute_query_background` mock) + `_confirm_data_change` จริงสำหรับ DELETE (patch `ui_dialog`)
- AC-11..17, 20: `threading.Thread` แบบ `test_bugfix_h1::_Thread` (จับ `target` / `args`, `run()` เอง), `get_connection_string` / `get_connect_args` เป็น `Mock`, patch `create_engine` / `inspect` / `print` / `traceback.print_exc`; engine เดิม `MagicMock` คืนรายชื่อ DB
- AC-18: patch `builtins.print` จับทุก argument ระหว่าง `list_tables` + worker; ตรวจ `results_text`, `repr`/`str`/`asdict` ของ `ConnectionInfo` / `RunTarget`, `target_label()` / `log_target()` / `run_log_header()` ว่าไม่มี `"S3cr3t-UAT"`; `_write_run_log` spy (ต้องไม่ถูกเรียกหรือไม่มี password)
- AC-19: ตรวจ `stub._connected_password_for(stub.engine)` และ `stub._connected_password is None`
- ห้าม print อักขระนอก cp874 ลง stdout จริง (ทุก `print` ใน worker ถูก patch)

## R11-D9. ความเสี่ยงและผลกระทบ

| # | ความเสี่ยง | การควบคุม |
|---|---|---|
| R11-R1 | **Spec ขัดกันเอง (ต้องตัดสินก่อนเริ่ม R11-T1)**: `tests/test_run_engine_batch.py::ListTablesEngineTests::test_info_db_type_wins_over_screen_at_start` ใช้ stub `RunTarget(engine_a, ConnectionInfo("P1", "PostgreSQL", "u", "h", "5432", ""))` โดยไม่มี password เก็บไว้ → ตาม R11-Q-6 / R11-AC-16 ต้อง block แต่ test คาดว่า thread เริ่ม → R11-AC-21 ("ผ่านโดยไม่แก้ test") เป็นไปไม่ได้พร้อมกับ R11-AC-16 | ทางเลือก (ก) **แนะนำ**: คง Q-6 ตาม spec แล้วอนุญาตให้ QA ปรับ **harness เท่านั้น** ของ test นั้น 1 บรรทัด — `stub._connected_password = (engine_a, "pw")` ก่อน `self._start(stub)` (ไม่แตะ assertion; เจตนาเดิมของ test คือ "db_type จาก info ชนะช่องกรอก" ยังตรวจครบ) แบบเดียวกับ R10-Q-5; (ข) เปลี่ยน Q-6 ให้ตรวจ password ใน worker เฉพาะเมื่อมี DB ต้องเข้า (test นี้คืนรายชื่อ DB ว่างจึงผ่าน) → ต้องเขียน R11-AC-16 ใหม่ (thread เริ่ม, error ผ่าน `on_list_tables_error`) และเพิ่มโค้ดใน worker; **หัวหน้า / ผู้ใช้ต้องเลือกและแก้ R11-AC-21 หรือ R11-AC-16 ใน spec** — tasks ด้านล่างเขียนตาม (ก) |
| R11-R2 | password อยู่ใน memory นานเท่า connection (เดิมอยู่ใน `engine.url` อยู่แล้ว) | ไม่เพิ่มการเปิดเผย: ไม่ log / print / save; ล้างเมื่อ engine ถูกแทน / reset; R11-AC-18 ตรวจ |
| R11-R3 | worker `print` ข้อความ exception จาก driver (`❌ ERROR accessing database ...: {e}`) — ถ้า driver ใส่ connection string ใน error อาจมี password (พฤติกรรมเดิมตั้งแต่ก่อน R11 เพราะเดิมก็ใช้ password จากช่องกรอก) | Out of scope (worker ไม่แตะ); R11-AC-18 ตรวจด้วย mock ที่ไม่ raise เท่านั้น — แจ้งไว้เป็นข้อสังเกต |
| R11-R4 | `ConnectionInfo.user/host/database` เป็นค่า strip ขณะที่ engine เดิมสร้างจากค่าไม่ strip → engine ราย DB อาจต่างจาก engine หลักเมื่อผู้ใช้กรอกช่องว่าง | spec R11-5 ยอมรับว่าค่าจาก `info` ถูกต้องกว่า |
| R11-R5 | header poll เรียก `_capture_run_target()` + อ่านช่อง 5 ช่องทุก 500 ms | ต้นทุนเท่าเดิมโดยประมาณ (เดิมอ่าน 5 ช่องอยู่แล้ว) |
| R11-R6 | Tk บางเวอร์ชันคืน `cget("fg")` เป็นตัวพิมพ์เล็ก / `Tcl_Obj` → เทียบไม่ตรงแล้ว `config(fg=...)` ทุก poll (ไม่ผิด แค่ซ้ำ) | `str()` ครอบ; ค่า `UI` เป็นตัวพิมพ์ใหญ่ที่ Tk เก็บตามที่ตั้ง |
| R11-R7 | เตือนเกิน: host `UAT-DB` กับ `uat-db` / port `05432` นับว่าต่าง | ตาม Q-4 (เตือนเกินดีกว่าเตือนขาด) |
| R11-R8 | Run / Run Job / Export ยังไม่ block เมื่อช่องไม่ตรง (Q-1) — ผู้ใช้ที่ไม่ดู header ยังสับสนได้ | ผู้ใช้เลือก Q-1 (ก); R11-AC-10 lock ไว้ |
| R11-R9 | diff ไปแตะ hunk Round 8-10 ที่ยังไม่ commit หรือ worker ของ `list_tables` | review ตรวจว่า hunk R11 อยู่เฉพาะจุดใน "ขอบเขต" |
| R11-R10 | full suite (R11-AC-22) ไม่ได้รันรอบนี้ | ผู้ใช้สั่งเลื่อน (Q-9); R11-T3 คง `[ ]` |

## R11-D10. AC → Task

| AC | Task | AC | Task | AC | Task |
|---|---|---|---|---|---|
| R11-AC-1 | R11-T1, R11-T2 | R11-AC-2 | R11-T1, R11-T2 | R11-AC-3 | R11-T1, R11-T2 |
| R11-AC-4 | R11-T1, R11-T2 | R11-AC-5 | R11-T1, R11-T2 | R11-AC-6 | R11-T1, R11-T2 |
| R11-AC-7 | R11-T1, R11-T2 | R11-AC-8 | R11-T1, R11-T2 | R11-AC-9 | R11-T1, R11-T2 |
| R11-AC-10 | R11-T2 | R11-AC-11 | R11-T1, R11-T2 | R11-AC-12 | R11-T1, R11-T2 |
| R11-AC-13 | R11-T1, R11-T2 | R11-AC-14 | R11-T1, R11-T2 | R11-AC-15 | R11-T1, R11-T2 |
| R11-AC-16 | R11-T1, R11-T2 | R11-AC-17 | R11-T1, R11-T2 | R11-AC-18 | R11-T1, R11-T2 |
| R11-AC-19 | R11-T1, R11-T2 | R11-AC-20 | R11-T1, R11-T2 | R11-AC-21 | R11-T2 |
| R11-AC-22 | R11-T3 | | | | |

---

# Round 13 — Follow-up: ข้อเสนอแนะ 🟢 1-9 จาก Code Review Round 12

> อ้างอิง: `docs/spec.md` หัวข้อ Round 13 (R13-AC-1 ถึง R13-AC-18); คำตอบผู้ใช้ 2026-11-23: **Q-1** แก้ (ข) (ค) (ง), (ก) (จ) known limit; **Q-2** ไม่แตะ error ตอนรัน; **Q-3** element ไม่ใช่ dict เก็บไว้ในลำดับเดิม
> ขอบเขตโค้ด: `database_connect_gui.py` เท่านั้น (เลขบรรทัด ณ 2026-11-23); test ใหม่ `tests/test_r13_*.py`; test เดิมแก้ได้เฉพาะ comment `tests/test_r8_load_jobs_writeback.py:305`

## R13-D1. แนวทาง

- **redact ที่ต้นทางข้อความ ครั้งเดียว** แล้วส่งสตริงที่ redact แล้วต่อ (Execution Logs → run log, dialog) — ไม่ต้องแก้ `_show_connection_error` เป็น signature ใหม่ (test เดิมแค่ `assert_called_once`)
- **pattern ใช้ named group `secret` + ฟังก์ชันแทนที่ตัวเดียว** แทนการนับ `pattern.groups` (2 / 3) — เพิ่ม pattern แบบมี quote ได้โดยไม่ต้องมีเงื่อนไขพิเศษ
- **known secret ของ Tables = รหัสที่ worker ถืออยู่ + รหัสที่เก็บไว้** (ส่งทั้งคู่เข้า `redact_secrets(*secrets)`) — รองรับ R13-AC-7 / R13-AC-8 และ test เดิมที่เรียก `on_list_tables_error(stub, error, dialog)` แบบ 2 argument
- **แยก logic "ทดสอบการเชื่อมต่อ" เป็น method** ที่คืน `(ok, text)` ทดสอบได้โดยไม่เปิด dialog / thread

## R13-D2. `redact_secrets` / `_SECRET_PATTERNS` (`:94-121`) — R13-AC-9, 10, 12

Import ระดับ module (กลุ่ม stdlib ต่อจาก `from typing import ...` บรรทัด 17): `from urllib.parse import quote_plus`; ลบ `from urllib.parse import quote_plus` ใน `redact_secrets` (บรรทัด 109). import ภายใน `get_connection_string` (`:7670`) ไม่ต้องแตะ

ใช้ตามนี้ได้ตรง ๆ:

```python
_SECRET_PATTERNS = (
    # PWD / password with a quoted value: keep the quotes, mask what is inside
    # (an unclosed quote masks to the end of the line). DB_PASSWORD= / MY_PWD= count.
    re.compile(
        r"(?i)(?<![a-z0-9])(?:PWD|PASSWORD)\s*=\s*(?P<q>['\"])"
        r"(?P<secret>(?:(?!(?P=q)).)*)"
    ),
    # ODBC connection string: PWD={...} (with }} escapes) or PWD=value
    re.compile(
        r"(?i)(?<![a-z0-9])(?:PWD|PASSWORD)\s*=(?!\s*['\"])\s*"
        r"(?P<secret>\{(?:[^}]|\}\})*\}|[^;&\s'\"]*)"
    ),
    # The same, URL-encoded inside odbc_connect=... (= %3D, ; %3B, { %7B, } %7D)
    re.compile(
        r"(?i)(?:PWD|PASSWORD)%3D"
        r"(?P<secret>%7B(?:(?!%7D).|%7D%7D)*%7D|.*?(?=%3B|&|\s|['\"]|$))"
    ),
    # URL userinfo: scheme://user:password@host (no "/" in the password:
    # the app quote_plus-es it, and http://host:8080/a@b is not userinfo)
    re.compile(r"://[^:/@\s'\"]*:(?P<secret>[^@/\s'\"]+)(?=@)"),
)


def _mask_secret(match: "re.Match[str]") -> str:
    """The whole match with only its `secret` group replaced by ***."""
    base = match.start()
    whole = match.group(0)
    return whole[: match.start("secret") - base] + "***" + whole[match.end("secret") - base:]


def redact_secrets(text: str, *secrets: Optional[str]) -> str:
    """(docstring เดิม)"""
    result = str(text)
    for secret in secrets:
        if secret and len(secret) >= 4:
            for form in {secret, quote_plus(secret)}:
                result = result.replace(form, "***")
    for pattern in _SECRET_PATTERNS:
        result = pattern.sub(_mask_secret, result)
    return result
```

เหตุผลของแต่ละจุด:

| จุด | ของเดิม | ใหม่ | ผล |
|---|---|---|---|
| (ข) quote | `[^;&\s'\"]*` match ว่างหน้า `'` → `password = ***'x'` | pattern quote แยก (ข้อ 1); pattern ปกติมี `=(?!\s*['\"])` ไม่ทับ (`(?!...)` วางหลัง `=` ก่อน `\s*` — ถ้าวางหลัง `\s*` regex จะ backtrack `\s*` แล้ว match ว่างได้) | `password = '***'`, `PWD="***"`, `password='***` |
| (ค) prefix | `\b` ไม่ match หลัง `_` | `(?<![a-z0-9])` (กับ `(?i)`) — `_`, `;`, `{`, ต้นบรรทัด ผ่าน; ตัวอักษร / ตัวเลข ไม่ผ่าน | `DB_PASSWORD=***`, `MY_PWD=***`; `NEWPWD=` ยังไม่ match (เหมือนเดิม) |
| (ง) URL | `[^@\s'\"]+` กิน `8080/a` | ตัด `/` ออก + `(?=@)` | `http://host:8080/a@b` ไม่เปลี่ยน; `postgresql://u:p%40ss@h/db` → `u:***@h/db` |
| (ก) known limit | — | ไม่แก้ | `postgresql://u:p@ss@h/db` → `postgresql://u:***@ss@h/db` (R13-AC-12) |

ตรวจกับ `RedactSecretsTests` เดิม (`tests/test_r11_connection_target_snapshot.py:982-1012`) ด้วยมือแล้ว — ทุก case ให้ผลเท่าเดิม: ODBC `PWD={p@ss;w}}rd};Encrypt=yes` → pattern 2 (ไม่มี quote, `{` ไม่ใช่ quote), URL-encoded → pattern 3 (ไม่เปลี่ยน), `postgresql://user:hunter22@host/db`, `PWD=abc123;UID=x`, `password=hunter22 next`, known secret / secret สั้น / `None` — developer **ต้องรัน** `python -m unittest tests.test_r11_connection_target_snapshot` ยืนยันหลังแก้ (ห้ามแก้ test นั้น)

## R13-D3. Connect — `connect_database` except (`:7764-7779`) — R13-AC-1..4, 6

```python
        except Exception as error:
            ...  # dispose / _replace_engine(None) / ปิดปุ่ม / status เหมือนเดิม
            # A driver error can echo the connection string (SQL Server: PWD=...)
            message = redact_secrets(str(error), password)
            self.results_text.insert(tk.END, f"❌ Connection Error: {message}\n\n")
            self.results_text.see(tk.END)
            self._show_connection_error(message)
            return
```

- `password` = ตัวแปรเดิมที่อ่านจากช่อง Password ตอนกด (`:7730`)
- `_show_connection_error(self, error)` (`:7911`) **ไม่เปลี่ยน signature / logic** — ได้สตริงที่ redact แล้ว จึง `str(error)` ทั้งใน Label (ตัด 400 หลัง redact โดยอัตโนมัติ) และ `ui_dialog(message=...)` ปลอดภัย; แก้แค่ docstring: `error` = ข้อความที่ผู้เรียก redact แล้ว (หรือ exception ที่ไม่มีรหัส)
- `subtitle` มีแค่ profile / db_type — ไม่ต้องแก้

## R13-D4. ทดสอบการเชื่อมต่อ (New Profile, `:11632-11674`) — R13-AC-5, 6

Method ใหม่บน `DatabaseConnectorGUI` (วางก่อน `new_profile_dialog`):

```python
    def _run_connection_test(
        self, db_type: str, user: str, password: str, host: str, port: str, database: str
    ) -> Tuple[bool, str]:
        """Try the details with a throw-away engine (main one untouched).
        Returns (ok, label text): redacted, first non-blank line, cut to 300."""
```

- เนื้อ = ย้ายจาก `work()` (`:11643-11658`) ทั้งก้อน: `import time as _time`, `create_engine(self.get_connection_string(...), connect_args=self.get_connect_args(db_type))`, `engine.connect()` + `SELECT 1` (`FROM DUAL` ถ้า Oracle), `finally: engine.dispose()`
- except: `detail = redact_secrets(str(error), password)` **ก่อน** `splitlines()` → `first = next((ln for ln in detail.splitlines() if ln.strip()), detail)` → `msg = f"✕  เชื่อมต่อไม่สำเร็จ: {first.strip()}"`
- ตัด 300 ใน method (ทั้งสองทาง): `msg if len(msg) <= 300 else msg[:299] + "…"` — ข้อความสำเร็จเหมือนเดิมทุกตัวอักษร
- `work()` เหลือ `outcome = self._run_connection_test(*args)` + `show()` เดิม โดย `result_label.config(text=msg, ...)` (ไม่ตัดซ้ำ)

## R13-D5. Tables — `list_tables` worker + `on_list_tables_error` — R13-AC-7, 8, 9

1. **🟢4 บรรทัดยาว**: ใน `fetch_tables_in_background` (`:9384`) เพิ่ม closure ที่บรรทัดต้นฟังก์ชัน แล้วแทน 3 คู่ "print ข้อความ + print traceback" (`:9438-9441`, `:9546-9551`, `:9564-9567`) ด้วย `log_error(f"...")` ข้อความเดิมทุกตัวอักษร; ลบ `import traceback` ภายในทั้ง 3 จุด (มีระดับ module แล้ว `:14`)

```python
            def log_error(message: str) -> None:
                """print the error + traceback with the password masked."""
                print(redact_secrets(message, credentials[1]))
                print(redact_secrets(traceback.format_exc(), credentials[1]), end="")
```

2. **🟢1 ส่งรหัสของ worker**: `:9612` →

```python
                self.root.after(
                    0, lambda err=e, pw=credentials[1]: self.on_list_tables_error(
                        err, loading_dialog, pw)
                )
```

3. `on_list_tables_error(self, error, loading_dialog, password: Optional[str] = None)` (`:9724`):

```python
        # A driver error can echo the connection string (SQL Server: PWD=...):
        # mask the password the worker used and the one stored for the engine
        stored = getattr(self, "_connected_password", None)
        message = redact_secrets(str(error), password, stored[1] if stored else None)
```

- ส่งทั้งสองค่า: ทาง `info` ที่ worker ไม่ถือรหัส (มี database / Oracle → `credentials[1] == ""` ตาม R12-6) ยัง fallback เป็นรหัสที่เก็บไว้เหมือนเดิม; การเรียก 2 argument เดิมได้ผลเดิม (R13-AC-8)
- ทุกบรรทัดที่มี `redact_secrets(` ต้อง ≤ 95 ตัวอักษร (R13-AC-9) — รวมบรรทัดใหม่ใน R13-D3 / R13-D4

## R13-D6. Load Preset filter (`:5692-5694`) — R13-AC-16

```python
                    self.saved_jobs = [
                        job for job in self.saved_jobs
                        if not isinstance(job, dict) or job.get("profile") != current_profile
                    ]
```

ลำดับเดิมคงอยู่ (comprehension), element ที่ไม่ใช่ dict ถูกเก็บ (R13-Q-3)

## R13-D7. ไม่แก้โค้ด (test / เอกสารเท่านั้น)

- R13-AC-13 (`EXPORT_REPLACE_RETRY_DELAYS` `:230`), R13-AC-14 (`write_json_atomic` `:73-91` รองรับ 3 ทางอยู่แล้ว: `except BaseException` ลบ `.tmp` แล้ว `raise`) — ถ้า test ล้มให้แจ้งเป็น bug อย่าแก้ test ให้ผ่าน
- R13-AC-15 comment `tests/test_r8_load_jobs_writeback.py:305` → `# sys.stdout really None (pythonw): print() returns silently, nothing to swallow`
- R13-AC-11 PM ทำแล้วใน spec (3 จุด); หมายเหตุฝั่ง design ใส่แล้วใน Round 10 ข้างบน

## R13-D8. Data model

ไม่เปลี่ยน — `ConnectionInfo` / `RunTarget` ไม่มี field password (R13-AC-18); ไม่มีไฟล์ / key JSON ใหม่

## R13-D9. แผน test (`tests/test_r13_*.py`)

ค่าคงที่ร่วม: `PW = "S3cr;t}PW-13"`, `LEAKS = (PW, quote_plus(PW), "S3cr", "PW-13", "}}PW-13", "%7D%7DPW-13")`, error (1) / (2) / (3) ตามนิยาม spec — (1) สร้างจาก `app.build_sqlserver_odbc_connect(...)` + `";Encrypt=yes ... Login failed for user 'u'."`; stub แบบ `DatabaseConnectorGUI.__new__` + `_FakeEntry` + fake `results_text` (เก็บ `inserted`) ตาม `tests/test_r11_connection_target_snapshot.py::make_stub`; patch `builtins.print` ทุก test ที่เรียก worker (AC-18)

| ไฟล์ | AC | วิธี |
|---|---|---|
| `test_r13_connect_redaction.py` | R13-AC-1 | `connect_database` จริง, patch `app.create_engine` → engine ที่ `connect.side_effect = RuntimeError(err)`, `app.messagebox`, `_show_connection_error` = Mock, `_track_engine_connections` / `_block_if_busy` stub; subTest (1)(2)(3): ทุก `inserted` ไม่มี LEAKS, มีบรรทัดขึ้นต้น `❌ Connection Error: `, ยังมี `Login failed for user 'u'` (หรือ `bad password` / `for u`) |
| 〃 | R13-AC-2 | `_show_connection_error` จริง, patch `app.ui_dialog` (side_effect เรียก `build_body(frame ปลอม)` แล้วคืน `None`), `app.ui_round_frame` คืน `(Mock, Mock)`, `app.tk.Label` จับ kwargs `text`; ตรวจ `message`, `subtitle`, Label ทุกตัวไม่รั่ว; case ยาว: `"x" * 380 + " " + err(1)` → Label ไม่มีชิ้นส่วนรหัส และลงท้าย `…` |
| 〃 | R13-AC-3 | `get_connection_string` (Mock) หรือ `create_engine` raise err(1); ตรวจผลเหมือน AC-1/2 + `engine is None`, `status_label` = `❌ Connection Failed`, ปุ่ม disabled |
| 〃 | R13-AC-4 | Password `"pw1"`, err `...PWD={pw1};... pw1x table` → `PWD=***`, คำ `pw1x` คงอยู่ |
| 〃 | R13-AC-5 | `GUI._run_connection_test(stub, ...)` กับ `create_engine` raise / `connect` raise × (1)(2)(3) → `ok is False`, ขึ้นต้น `✕  เชื่อมต่อไม่สำเร็จ: `, ไม่รั่ว, `len <= 300`; case error หลายบรรทัดที่บรรทัดแรกว่าง + case ยาว > 300 ที่รหัสอยู่ช่วงท้าย; สำเร็จ → `assertRegex(r"^✓  ทดสอบเชื่อมต่อสำเร็จ · PostgreSQL · \d+ ms$")` และ `dispose` ถูกเรียก |
| 〃 | R13-AC-6 | ข้อความ 3 แบบใน spec ผ่าน AC-1 (`❌ Connection Error: <เดิม>`) และ AC-5 (`✕  เชื่อมต่อไม่สำเร็จ: <เดิม>`) เท่ากันทุกตัวอักษร |
| `test_r13_tables_and_patterns.py` | R13-AC-7 | `_run_target = RunTarget(engine, None)`, ช่อง Password = PW; `threading.Thread` แบบจับ target/args แล้ว `run()` เอง; `root.after` เรียก callback ทันที; ช่อง Database มีค่า + patch `app.inspect` raise err(3) (หลุดถึง except นอกสุด `:9610`); `messagebox` patch → `results_text` + `showerror` ไม่รั่ว |
| 〃 | R13-AC-8 | snapshot `info` (database `""`, PostgreSQL) + `_replace_engine(engine, info, password=PW)`; ให้ worker raise err(3) โดยที่ก่อน `root.after` callback รัน ตั้ง `stub._connected_password = (engine, "Other-pass-99")` → ไม่รั่ว; และเรียก `GUI.on_list_tables_error(stub, err, dlg)` แบบ 2 argument ยังทำงาน |
| 〃 | R13-AC-9 | อ่าน `database_connect_gui.py` (utf-8) ทุกบรรทัดที่มี `redact_secrets(` → `len <= 95`; `"import" not in inspect.getsource(app.redact_secrets)`; `app.quote_plus is urllib.parse.quote_plus` |
| 〃 | R13-AC-10 | `assertEqual` ทุก case ใน spec (subTest) |
| 〃 | R13-AC-12 | 3 assertion ตาม spec (pin known limit) |
| `test_r13_persistence.py` | R13-AC-13 | `assertEqual(app.EXPORT_REPLACE_RETRY_DELAYS, (0.2, 0.5, 1.0))`, `sum <= 2.0` |
| 〃 | R13-AC-14 | temp dir, ไฟล์เดิม bytes X; subTest (ก) data มี `object()` (TypeError จริง), (ข) patch `app.os.fsync` raise `OSError`, (ค) patch `app.os.fsync` raise `KeyboardInterrupt`; `assertRaises` + `is` instance เดียวกัน (ข/ค), bytes = X, ไม่มี `.tmp`, patch `app.os.replace` (wraps) ไม่ถูกเรียก |
| 〃 | R13-AC-16 | ตาม harness ของ `tests/test_r9_load_preset_validation.py` (Load Preset + askyesno Yes + `save_jobs` คืน True): `saved_jobs = [job_P1_a, None, "junk", job_P2_b]` → ผล `[None, "junk", job_P2_b, <preset job>]`, ข้อความ askyesno มี `replace current 1 jobs`, ไม่มี `showerror` |

R13-AC-15 / R13-AC-11 ตรวจด้วย `git diff` / review; R13-AC-17 / 18 = R13-T regression

## R13-D10. ความเสี่ยงและผลกระทบ

| # | ความเสี่ยง | การควบคุม |
|---|---|---|
| R13-R1 | pattern ใหม่ mask เกิน: quote ไม่ปิด (`password='abc ...`) mask ถึงท้ายบรรทัด; `DB_PASSWORD=` ทำให้คำที่ลงท้าย `_PWD=` ใน SQL / ข้อความ error ถูก mask | ฝั่งปลอดภัย, ใช้แค่ Connect / Tables; R13-AC-6 / AC-1 "ไม่ mask เกิน" ล็อกข้อความปกติ |
| R13-R2 | วาง `(?!\s*['\"])` ผิดตำแหน่ง (หลัง `\s*`) → backtrack แล้วได้ `password =*** '***'` | ใช้ regex ตาม R13-D2 ตรง ๆ; R13-AC-10 เทียบทุกตัวอักษร |
| R13-R3 | ลืมเปลี่ยน logic `pattern.groups == 3` → pattern ใหม่ที่มี group `q` ถูกแทนผิด | ใช้ `_mask_secret` ตัวเดียวกับทุก pattern; ทุก pattern ต้องมี group `secret` ที่ match เสมอ (ไม่อยู่ในส่วน optional) |
| R13-R4 | Tables ทาง `info` ที่ worker ไม่ถือรหัส (มี database / Oracle, R12-6) → known secret มาจาก `_connected_password` ตอน error เท่านั้น ถ้ามันถูกเปลี่ยนกลางทาง รหัสแบบตรงตัว (3) ไม่ถูก mask | ไม่เพิ่มรหัสเข้า thread (คง R12-6); Connect ถูก `_block_if_busy` ระหว่าง Tables จึงแทบไม่เกิด; pattern ยังปิด `PWD=` / URL |
| R13-R5 | ย้าย `work()` ไป `_run_connection_test` แล้วเปลี่ยนข้อความสำเร็จ / การตัด 300 โดยไม่ตั้งใจ | R13-AC-5 / AC-6 ตรวจข้อความ; `show()` ไม่ตัดซ้ำ |
| R13-R6 | `log_error` เปลี่ยนข้อความ print ของ worker | ส่ง f-string เดิมทุกตัวอักษร; test เดิมของ R12-7 / R11 ต้องผ่านโดยไม่แก้ |
| R13-R7 | Out of scope ตาม Q-2: error ตอนรัน / reconnect ยังแสดงดิบ | บันทึกเป็นงาน Round ถัดไปถ้าผู้ใช้ต้องการ |

## R13-D11. AC → Task

| AC | Task | AC | Task | AC | Task |
|---|---|---|---|---|---|
| R13-AC-1 | R13-T2, R13-T4 | R13-AC-2 | R13-T2, R13-T4 | R13-AC-3 | R13-T2, R13-T4 |
| R13-AC-4 | R13-T1, R13-T2, R13-T4 | R13-AC-5 | R13-T2, R13-T4 | R13-AC-6 | R13-T1, R13-T2, R13-T4 |
| R13-AC-7 | R13-T3, R13-T4 | R13-AC-8 | R13-T3, R13-T4 | R13-AC-9 | R13-T1, R13-T2, R13-T3, R13-T4 |
| R13-AC-10 | R13-T1, R13-T4 | R13-AC-11 | R13-T4 (review) | R13-AC-12 | R13-T1, R13-T4 |
| R13-AC-13 | R13-T4 | R13-AC-14 | R13-T4 | R13-AC-15 | R13-T4 |
| R13-AC-16 | R13-T3, R13-T4 | R13-AC-17 | R13-T | R13-AC-18 | R13-T4, R13-T |
