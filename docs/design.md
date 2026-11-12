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
