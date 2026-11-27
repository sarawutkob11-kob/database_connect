# Design — database_connect_gui

> งานที่เสร็จแล้ว (Round 1–15) ถูกลบออกจากไฟล์นี้เมื่อ 2026-11-27 เพื่อลด token ตามคำสั่งผู้ใช้ — ดูย้อนหลังได้จาก git history (`git show ef6d896:docs/<file>`) เลขบรรทัดที่อ้างถึง docs เดิมอาจไม่ตรงแล้ว

# Round 16 — Bugfix จาก scripted GUI walk-through (B1, B2, B3)

> spec: `docs/spec.md` Round 16 (R16-AC-1..17); ผู้ใช้อนุมัติ spec 2026-11-27 และตอบคำถามตามค่าแนะนำทุกข้อ:
> - **R16-Q-1 = (ก)** — ไฟล์ไม่ถูกต้องเมื่อมี item อย่างน้อย 1 ตัวที่มี key `query` แต่ไม่มี key `scripts` (ทั้งไฟล์ ไม่ import บางส่วน); ไม่แก้ test เดิม
> - **R16-Q-2** — บรรทัด `⏹ Stop requested ...` อยู่ต้น Execution Logs (หลังล้าง ก่อนผลของงาน) ข้อความเดิมทุกตัวอักษร **ไม่เขียนซ้ำลง run log**
> - **R16-Q-3** — กด Stop หลายครั้ง แสดงทุกบรรทัดตามลำดับที่กด
>
> เลขบรรทัด `database_connect_gui.py` ณ commit `e8fba9e` (คลาดได้เล็กน้อย); ห้าม commit; test เดิมห้ามแก้; test ใหม่ `tests/test_r16_*.py`

## R16-D1. แนวทางรวม

- แก้ไฟล์เดียว `database_connect_gui.py` แบบ minimal diff; ไม่มีไฟล์ / key JSON / dependency ใหม่
- B1: **จำบรรทัด Stop ของงานปัจจุบันไว้ใน list** (`self._stop_lines`) แล้ว**เขียนกลับหลังล้าง Logs ตอนจบ** เฉพาะ 6 จุดที่ล้าง Logs ตอนจบ (Job เดี่ยว / SQL Editor / Tables) โดยเขียนผ่าน `insert` ตัวจริงของ widget ที่ไม่ผ่าน wrapper run log → run log ไม่ซ้ำ (R16-Q-2)
  - เหตุผลที่ไม่ใช้ `_stop_event`: spec R16-5 — event ค้างหลังงานจบ และ Tables ไม่ล้าง event; list ที่ล้างตอน "งานเริ่มจริง" ของทุกชนิดงานบอกได้ตรงว่า "กด Stop ระหว่างงานนี้"
  - เหตุผลที่ไม่ใช้ "ไม่ล้างบรรทัด Stop": `Text.delete("1.0", END)` ลบทั้งหมด การลบแบบเว้นช่วงต้องหา index ของบรรทัดซึ่งเปราะ (ผู้ใช้อาจแก้ Logs / มีข้อความอื่นแทรก) — เขียนกลับง่ายและได้ตำแหน่งตาม R16-Q-2 พอดี
- B2: เพิ่มการตรวจ item แบบ Job ใน `parse_script_groups_import` **ก่อน**ตัวกรองเดิม (กฎไม่สนค่า `name` / `query` ตาม spec)
- B3: pack scrollbar ด้วย `before=jobs_canvas` และใช้ `winfo_manager()` แทน `winfo_ismapped()` เป็นตัวตัดสินว่า "pack อยู่หรือยัง"; เปิดเผย scrollbar + ฟังก์ชัน update เป็น attribute เพื่อทดสอบ
- stub `GUI.__new__` ของ test เดิมไม่มี attribute ใหม่ → โค้ดใหม่อ่านด้วย `getattr(..., default)` / `self.__dict__.setdefault(...)` เสมอ

## R16-D2. B1 — state และ helper ใหม่ (R16-AC-1..9)

### state

| attribute | type | ตั้งค่าที่ | ความหมาย |
|---|---|---|---|
| `self._stop_lines` | `List[str]` | `__init__` ถัด `self._stop_event = threading.Event()` (`:2601`) = `[]` | ข้อความ `msg` ทุกตัวที่ `stop_running_queries` insert ระหว่างงานปัจจุบัน ตามลำดับที่กด |
| `self._results_text_raw_insert` | `Callable[..., Any]` | `_install_run_log_hook()` (ดูด้านล่าง) | `results_text.insert` ตัวจริงก่อนห่อ — เขียน Logs โดยไม่เขียน run log |

### จุดล้าง list ("งานเริ่มจริง")

| ชนิดงาน | จุด | เหตุผล |
|---|---|---|
| Job เดี่ยว, Run all, Export, Run Group, SQL Editor | `_start_stoppable_run` (`:8369-8372`) เพิ่มบรรทัดแรก `self._stop_lines = []` (ก่อน `self._stop_event.clear()`) | ทุกงานเหล่านี้เรียกก่อน `_start_job_result_report()` ตอนเริ่ม (`run_job :10116` ก่อน `:10133`, `run_selected_job :10250` ก่อน `:10264`, `execute_query :8703`) |
| Tables | `list_tables` (`:9483`) — เพิ่ม `self._stop_lines = []` ก่อน `self.results_text.insert(tk.END, "Fetching database schema information...\n\n")` (หลัง early return ทุกตัว ก่อนปุ่มเป็น `⏳ Loading...`) | Tables ไม่เรียก `_start_stoppable_run` (spec R16-5); **ไม่**เพิ่ม `_stop_event.clear()` (นอก scope — out of scope ข้อ Tables worker) |

ผล R16-AC-6: งานใหม่ทุกชนิดเริ่มด้วย list ว่าง; กด Stop ตอนไม่ busy → `stop_running_queries` return ที่ `:8454` ก่อนบันทึก → list ไม่เปลี่ยน

### `stop_running_queries` (`:8452-8479`)

หลัง `self.results_text.insert(tk.END, msg)` (`:8478`) เพิ่ม:

```python
self.__dict__.setdefault("_stop_lines", []).append(msg)
```

(รูปแบบเดียวกับ `_running_job_ids` `:10102` — stub ที่ไม่มี attribute ไม่พัง; ข้อความที่ insert ไม่เปลี่ยน → `tests/test_running_banner.py:308-333`, `tests/test_list_tables_stop.py:228-230` ผลเดิม)

### helper ใหม่ (วางถัดจาก `_start_stoppable_run`)

```python
def _replay_stop_lines(self) -> None:
    """Write the Stop lines of the current run again (Logs were just cleared
    at the end of the run). Not written to the run log: it already has them."""
    lines = getattr(self, "_stop_lines", None)
    if not lines:
        return
    insert = getattr(self, "_results_text_raw_insert", None) or self.results_text.insert
    for line in lines:
        insert(tk.END, line)

def _clear_results_keep_stop_lines(self) -> None:
    """End of a Job / SQL Editor / Tables run: clear Execution Logs, then put
    back this run's Stop lines first (R16-Q-2)."""
    self.results_text.delete("1.0", tk.END)
    self._replay_stop_lines()
```

- ไม่มี Stop → `lines` ว่าง → เหลือแค่ `delete` เหมือนเดิมทุกตัวอักษร (R16-AC-5)
- `insert` ใช้ข้อความเดิมทุกตัวอักษร (รวม `\n` นำหน้า) → Logs ขึ้นต้นด้วยบรรทัดว่างแล้วบรรทัด Stop (เหมือนที่ผู้ใช้เห็นก่อนจบ)
- ไม่เรียก `see` (ผู้เรียกทุกจุดเรียก `see(tk.END)` ภายหลังอยู่แล้วหรือไม่เคยเรียก — คงเดิม)
- fallback `self.results_text.insert` ใช้กับ stub ที่ไม่ได้ติดตั้ง hook (ไม่มี run log ให้ซ้ำอยู่แล้ว)

### `_install_run_log_hook` — ย้าย wrapper `:3371-3379` เป็น method (เพื่อให้ test R16-AC-7 ใช้โค้ดจริง)

```python
def _install_run_log_hook(self) -> None:
    """Everything inserted into Execution Logs is also appended to the run
    log; keep the unwrapped insert for text that must not be logged twice."""
    raw_insert = self.results_text.insert

    def _insert_and_log(index, chars, *args):
        result = raw_insert(index, chars, *args)
        if isinstance(chars, str):
            self._write_run_log(chars)
        return result

    self._results_text_raw_insert = raw_insert
    self.results_text.insert = _insert_and_log
```

- `__init__` `:3371-3379` แทนด้วย `self._install_run_log_hook()` (หลัง `self._init_run_log()` `:3370` เหมือนเดิม) — พฤติกรรมเดิมทุกอย่าง (ตรวจแล้วไม่มี test อ้าง `_log_insert` / `_insert_and_log`)

### จุดที่เปลี่ยนการล้างตอนจบ (6 จุด)

| ทาง | จุดเดิม | เปลี่ยนเป็น |
|---|---|---|
| Job เดี่ยว (`run_job.finish`) | `self._start_job_result_report()` `:10154` | `self._start_job_result_report(keep_stop_lines=True)` |
| SQL — DML | `on_modification_success` `:8748` `self.results_text.delete("1.0", tk.END)` | `self._clear_results_keep_stop_lines()` |
| SQL — SELECT | `on_query_success` `:8778` | `self._clear_results_keep_stop_lines()` |
| SQL — error (dialog ปิดแล้ว / เรียกตรง) | `on_query_error` `:8808` | `self._clear_results_keep_stop_lines()` |
| SQL — error (dialog เปิด) | `on_query_error_enhanced` `:7182` | `self._clear_results_keep_stop_lines()` |
| Tables — พบตาราง | `on_list_tables_success` `:9785` | `self._clear_results_keep_stop_lines()` |

`_start_job_result_report` (`:10060-10061`):

```python
def _start_job_result_report(self, keep_stop_lines: bool = False) -> None:
    if keep_stop_lines:
        self._clear_results_keep_stop_lines()
    else:
        self.results_text.delete("1.0", tk.END)
```

- ตอนเริ่มงาน (`:10133`, `:10264`) เรียกแบบไม่มี argument → ไม่เขียนกลับ (R16-AC-6 ชั้นที่สอง แม้ list ยังไม่ถูกล้าง)
- test เดิม 6 ไฟล์ที่ `mock.Mock()` แทน `_start_job_result_report` รับ keyword ได้ และไม่มี test ใด assert argument ของมัน (ตรวจ grep แล้ว)
- ทางที่**ไม่**ล้าง Logs ไม่แตะ: `on_list_tables_error` (`:9824`), `on_list_tables_success` list ว่าง (`:9817`), Run all / Export / Run Group (R16-AC-4 ส่วนหลัง, R16-AC-9 — บรรทัด Stop อยู่หนึ่งครั้งตามเดิม)
- `execute_query` `:8694` (`delete` ตอน**เริ่ม**) ไม่แตะ
- `on_query_error_enhanced` ทาง dialog ปิด (`:7112-7115`) เรียก `on_query_error` → เขียนกลับครั้งเดียว (ไม่ซ้ำ)

### ลำดับข้อความ (R16-AC-1, R16-Q-2)

Job เดี่ยวที่กด Stop แล้ว error: `delete` → `\n⏹ Stop requested — cancelled 1 running query(ies); remaining jobs are skipped.\n` → ผลของ `update_job_status` → บล็อก `Total` / `Success` / `Fail` — ไม่มีบรรทัด Stop ซ้ำ (บรรทัดที่ insert ตอนกดถูก `delete` ไปแล้ว)

### thread safety

`stop_running_queries` (ปุ่ม) และ callback จบทุกตัว (`root.after`) รันบน main thread ทั้งหมด → ไม่ต้องใช้ lock; worker thread ไม่แตะ `_stop_lines`

## R16-D3. B2 — `parse_script_groups_import` ปฏิเสธไฟล์ Saved Jobs (R16-AC-10..13)

แก้ `parse_script_groups_import` (`:1163-1183`) — เพิ่มลูปตรวจ**หลัง** `if not isinstance(incoming, list): raise` (`:1170-1171`) และ**ก่อน** list comprehension กรอง (`:1172`):

```python
for position, item in enumerate(incoming, start=1):
    if isinstance(item, dict) and "query" in item and "scripts" not in item:
        name = item.get("name")
        label = f"'{name}'" if isinstance(name, str) and name.strip() else f"item {position}"
        raise ValueError(
            f"{label} looks like a Saved Job, not a group "
            "(it has 'query' but no 'scripts' list)"
        )
```

- ตรวจกับ list ดิบ (ก่อนกรอง) → item แบบ Job ที่ชื่อว่าง / ไม่ใช่ str ก็ทำให้ทั้งไฟล์ไม่ถูกต้อง ("ไม่สนค่าของ `name` / `query`" ตามนิยาม spec); label ใช้ `item <ลำดับ>` เมื่อ name ไม่ใช่ข้อความหรือเป็นข้อความว่าง (ชื่อว่าง `''` อ่านไม่รู้เรื่อง)
- ไฟล์ผสม (R16-AC-12) → raise ก่อนคืนอะไร → ไม่ import `G1`
- ข้อความ error มีคำว่า `scripts` (R16-AC-10); ผู้เรียก `import_script_groups` (`:4743-4749`) ห่อด้วย `except Exception` อยู่แล้ว → `showerror("Import Groups", "Not a valid Script Groups file:\n<msg>", parent=parent)` แล้ว `return None` ก่อน `askyesno*` / deepcopy / merge / save (R16-AC-11) — **ไม่ต้องแก้ `import_script_groups` / `sidebar_import_script_groups`**
- docstring เพิ่มหนึ่งประโยค: `Raises ValueError when an item looks like a Saved Job ('query' without 'scripts').`
- ไม่กระทบ (R16-AC-13): `build_script_groups_export` มี `scripts` ทุกกลุ่ม; `{"name": "A"}` ไม่มี `query`; item ที่มีทั้ง `query` + `scripts` ผ่านไปตัวกรองเดิม; ไฟล์ `script_groups.json` ภายในมี `scripts` ทุกกลุ่ม; ตัวกรองเดิม / `ValueError` เรื่อง script ไม่มี SQL ไม่แตะ; ตรวจ `tests/test_r3_script_groups_io.py:172-200`, `:1003`, `:1074` แล้วไม่มี item ที่มี `query` แต่ไม่มี `scripts`

## R16-D4. B3 — scrollbar ของ Saved Jobs (R16-AC-14..16)

แก้ nested `update_jobs_scroll_state` (`:3022-3031`):

```python
def update_jobs_scroll_state():
    bounds = jobs_canvas.bbox("all")
    jobs_canvas.configure(scrollregion=bounds or (0, 0, 0, 0))
    if jobs_content_overflows():
        if jobs_scrollbar.winfo_manager() != "pack":
            jobs_scrollbar.pack(side="right", fill="y", before=jobs_canvas)
    else:
        jobs_canvas.yview_moveto(0)
        if jobs_scrollbar.winfo_manager():
            jobs_scrollbar.pack_forget()
```

- `before=jobs_canvas` → pack ได้ที่ด้านขวาก่อน canvas (`expand=True`) จะกินที่ → มีความกว้างจริง (สาเหตุหลักของ B3)
- เปลี่ยนตัวตัดสินจาก `winfo_ismapped()` เป็น `winfo_manager()`: `winfo_ismapped()` เป็น 0 เมื่อ widget ถูก pack แต่ไม่ได้แสดง (ความกว้าง 0 / root ยังไม่ map / withdraw) → เดิมทำให้ (ก) pack ซ้ำทุกครั้ง (ข) `pack_forget` ไม่ทำงานตอนไม่ล้น; `winfo_manager()` บอกสถานะ pack ตรง ๆ → scrollbar อยู่ใน `pack_slaves()` ครั้งเดียว (R16-AC-15), เรียกซ้ำหลายครั้งไม่ re-pack (R16-AC-16)
- pack ครั้งแรก `:3012-3013` ไม่แตะ (ลำดับถูกอยู่แล้ว); `jobs_content_overflows`, `configure_jobs_scroll`, `resize_jobs_canvas`, mouse wheel ไม่แตะ
- เปิดเผยเพื่อทดสอบ (ถัด `self.jobs_list_frame = jobs_list_frame` `:3059`; `self.jobs_canvas` มีอยู่แล้ว `:3058`):

```python
self.jobs_scrollbar = jobs_scrollbar
self._update_jobs_scroll_state = update_jobs_scroll_state
```

  ไม่เปลี่ยน layout / สี / ขนาด / mouse wheel

## R16-D5. ไฟล์ที่แก้

| ไฟล์ | สิ่งที่แก้ | B |
|---|---|---|
| `database_connect_gui.py` | `parse_script_groups_import` (`:1163-1183`) | B2 |
| `database_connect_gui.py` | `__init__`: `_stop_lines` (`:2601`), `update_jobs_scroll_state` (`:3022-3031`), attribute `jobs_scrollbar` / `_update_jobs_scroll_state` (`:3059`), wrapper → `self._install_run_log_hook()` (`:3371-3379`) | B1, B3 |
| `database_connect_gui.py` | method ใหม่ `_install_run_log_hook`, `_replay_stop_lines`, `_clear_results_keep_stop_lines`; `_start_stoppable_run` (`:8369`), `stop_running_queries` (`:8478`), `_start_job_result_report` (`:10060`), `run_job.finish` (`:10154`), `on_query_error_enhanced` (`:7182`), `on_modification_success` (`:8748`), `on_query_success` (`:8778`), `on_query_error` (`:8808`), `list_tables` (`:9483`), `on_list_tables_success` (`:9785`) | B1 |
| `tests/test_r16_stop_lines.py` | ใหม่ | B1 |
| `tests/test_r16_import_saved_jobs.py` | ใหม่ | B2 |
| `tests/test_r16_jobs_scrollbar.py` | ใหม่ | B3 |

## R16-D6. ความเสี่ยงและผลกระทบ

| # | ความเสี่ยง | การควบคุม |
|---|---|---|
| R16-R1 | B3 ทดสอบด้วย root ที่ `withdraw()` — Tk อาจไม่คำนวณ geometry ของลูกจน `winfo_width()` ยังเป็น 1 → เช็คความกว้าง / ตำแหน่งใน R16-AC-15 ทำไม่ได้ | QA ตั้ง `root.geometry("1100x680")` + `update_idletasks()` ก่อนวัด; ถ้ายังได้ 1 ให้**หยุดแล้วแจ้งหัวหน้า** (อย่าเปลี่ยน AC เอง — ทางเลือกคือ deiconify นอกจอ ซึ่งต้องให้ผู้ใช้อนุญาต) |
| R16-R2 | B3 เปลี่ยน `winfo_ismapped` → `winfo_manager` เปลี่ยนพฤติกรรมตอนเปิดแอป: เดิม scrollbar ที่ pack ไว้ตอนสร้าง (`:3012`) ไม่ถูก `pack_forget` ระหว่างที่ root ยังไม่ map แม้ไม่ล้น → ตอนนี้ถูกซ่อนตามกฎ "ไม่ล้น = ไม่ pack" | ตรงกับ R16-AC-15 และพฤติกรรมที่ตั้งใจของโค้ดเดิม; qa-tester ตรวจด้วยตาว่าหน้าต่างจริงไม่มี layout กระตุก (Manual) |
| R16-R3 | B1 เขียนกลับด้วย `_results_text_raw_insert` — ถ้าวันหน้ามีโค้ดแทน `results_text` ด้วย widget ใหม่ ตัวแปรจะชี้ widget เก่า | วันนี้ `results_text` สร้างครั้งเดียว; `_install_run_log_hook` เป็นที่เดียวที่ตั้งค่า (ระบุใน docstring) |
| R16-R4 | B1 run_job: test เดิมที่ mock `_start_stoppable_run` (`tests/test_running_banner.py:232`) → list ไม่ถูกล้างตอนเริ่ม | test เหล่านั้น mock `_start_job_result_report` ด้วย → ไม่มีการเขียนกลับ; ผลเดิม |
| R16-R5 | B1 Logs ตอนจบขึ้นต้นด้วยบรรทัดว่าง (msg มี `\n` นำหน้า) | ตั้งใจ — R16-Q-2 "ข้อความเดิมทุกตัวอักษร" |
| R16-R6 | B2 กฎเข้มขึ้น: ไฟล์ที่เคย import ได้ (กลุ่มว่างขยะจาก saved_jobs) ตอนนี้ error | ตั้งใจตาม R16-Q-1; ไฟล์ที่แอปนี้ export ไม่โดน (R16-D3) |
| R16-R7 | B1 Tables ไม่ล้าง `_stop_event` (เดิม) — ไม่เกี่ยวกับการแสดงผลแล้วเพราะใช้ `_stop_lines` | ไม่แก้ (out of scope) |

## R16-D7. แผน test (`tests/test_r16_*.py`)

ร่วม: stub `GUI.__new__` + `_FakeText` (เก็บข้อความจริง: `insert(index, chars)` ต่อท้าย, `delete("1.0", END)` ล้าง, `get("1.0", END)` คืนข้อความ + `"\n"`, `see` no-op), patch `app.messagebox`, `root.after` เรียกทันที, `app.threading.Thread` เก็บ target แล้วเรียกเอง (แบบ `_ThreadCapture` ใน `tests/test_running_banner.py`), connection stub ใน `_active_db_connections` ที่มี / ไม่มี `cancel`, `_active_db_lock = threading.Lock()`, `_stop_event = threading.Event()`; ไม่ต่อ DB จริง

| ไฟล์ | AC | วิธีหลัก |
|---|---|---|
| `test_r16_stop_lines.py` | 1-9 | `run_job` จริง (`_start_stoppable_run` จริงโดย patch `_log_run_context`, `_start_job_result_report` / `_finish_job_result_report` / `update_job_status` จริงหรือ stub ที่เขียนข้อความลง fake text; `_clear_results_grid` / `_show_results_grid_sets` Mock); กด Stop ระหว่าง `run_job(...)` กับการเรียก worker; SQL Editor: `execute_query` จริงโดย patch `_create_loading_dialog_with_retry` / `_execute_query_background` แล้วเรียก `on_*` จริงด้วย dialog Mock (`winfo_exists` 0 / 1); Tables: `list_tables` จริงแบบ `tests/test_list_tables_stop.py:145` แล้วเรียก `on_list_tables_success` / `on_list_tables_error` จริง (`show_table_popup` Mock); AC-5 เทียบข้อความกับ oracle ที่ได้จากการรันทางเดียวกันโดยไม่กด Stop + ตรวจไม่มี `Stop requested`; AC-7 เรียก `GUI._install_run_log_hook(stub)` บน fake text โดย patch `_write_run_log` เป็นตัวบันทึก แล้วนับข้อความที่มี `⏹ Stop requested`; AC-9 `run_selected_job` / `export_jobs_to_excel` แบบ `tests/test_r15_run_all_and_polls.py` / `tests/test_r14_jobs_redaction.py` |
| `test_r16_import_saved_jobs.py` | 10-13 | unit `parse_script_groups_import`; `import_script_groups(parent)` / `sidebar_import_script_groups()` แบบ `tests/test_r3_script_groups_io.py` (`filedialog.askopenfilename` คืนไฟล์ใน temp dir, `save_script_groups` Mock) |
| `test_r16_jobs_scrollbar.py` | 14-16 | Tk จริง withdraw แบบ `tests/test_r3_script_groups_io.py:1643-1663` (APP_DIR temp, patch `messagebox`) → `gui.jobs_canvas`, `gui.jobs_scrollbar`, `gui.jobs_list_frame`, `gui._update_jobs_scroll_state`; ล้น = ใส่ `tk.Frame(gui.jobs_container, height=60)` หลายอันจนสูงเกิน canvas; ไม่ล้น = destroy ลูกทั้งหมด; skip เมื่อ `TclError`; destroy root ใน `finally` (ดู R16-R1) |

R16-AC-17 = R16-T4 (regression สอง encoding)

## R16-D8. AC → Task

| AC | Task | AC | Task | AC | Task |
|---|---|---|---|---|---|
| R16-AC-1 | R16-T3 | R16-AC-2 | R16-T3 | R16-AC-3 | R16-T3 |
| R16-AC-4 | R16-T3 | R16-AC-5 | R16-T3 | R16-AC-6 | R16-T3 |
| R16-AC-7 | R16-T3 | R16-AC-8 | R16-T3 | R16-AC-9 | R16-T3 |
| R16-AC-10 | R16-T2 | R16-AC-11 | R16-T2 | R16-AC-12 | R16-T2 |
| R16-AC-13 | R16-T2 | R16-AC-14 | R16-T1 | R16-AC-15 | R16-T1 |
| R16-AC-16 | R16-T1 | R16-AC-17 | R16-T1..T3 (test ใหม่), R16-T4 | | |
