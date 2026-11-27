# Spec — database_connect_gui

> งานที่เสร็จแล้ว (Round 1–15) ถูกลบออกจากไฟล์นี้เมื่อ 2026-11-27 เพื่อลด token ตามคำสั่งผู้ใช้ — ดูย้อนหลังได้จาก git history (`git show ef6d896:docs/<file>`) เลขบรรทัดที่อ้างถึง docs เดิมอาจไม่ตรงแล้ว

# Round 16 — Bugfix จาก scripted GUI walk-through (B1, B2, B3)

> ใช้เลข `R16-AC-x` / `R16-Q-x` แยกจาก Round ก่อนหน้า ไม่แก้เนื้อหา Round ก่อนหน้า
> ที่มา: qa-tester รัน scripted GUI walk-through บนหน้าต่างจริง (2026-11-27) พบ 3 บั๊กจาก checklist Manual ใน `docs/tasks.md` (AC-25 ข้อ 2 / AC-37 ข้อ 2 `:106-121`, M9 `:346`, M3 `:338`) — ผู้ใช้อนุมัติให้เปิด Round นี้แก้ทั้ง 3 ข้อ (2026-11-27)
> เลขบรรทัด `database_connect_gui.py` ณ 2026-11-27 (commit `e8fba9e`) อาจคลาดเล็กน้อย
> สถานะ: **ผู้ใช้อนุมัติแล้ว** (จุดอนุมัติที่ 1, 2026-11-27) — R16-Q-1 = (ก) item ที่มี `query` แต่ไม่มี `scripts` → ทั้งไฟล์ไม่ถูกต้อง; R16-Q-2 = บรรทัด ⏹ ไว้ต้น Execution Logs ข้อความเดิม ไม่เขียนซ้ำลง run log; R16-Q-3 = แสดงทุกบรรทัดตามลำดับที่กด

### R16-1. เป้าหมาย / ปัญหา

| B | ปัญหา (สรุป) | จุดในโค้ด |
|---|---|---|
| B1 | บรรทัด `⏹ Stop requested — ...` ที่ `stop_running_queries` เขียนลง Execution Logs (`results_text`) **หายไปทันทีที่งานจบ** สำหรับ Job เดี่ยว (▶ ของการ์ด), SQL Editor (▶ Run) และ ▦ Tables เพราะ callback ตอนจบล้าง `results_text` ทั้งหมดก่อนเขียนผล — ผู้ใช้ไม่เห็นว่า Stop ทำงานแล้ว (ในไฟล์ `logs/run_*.log` ยังมีครบ); Run all / Export / Run Group ไม่เป็น (ไม่ล้างตอนจบ) | เขียนบรรทัด: `stop_running_queries` `:8452-8479`; ล้างตอนจบ: `run_job.finish` → `_start_job_result_report()` `:10154` (`:10060-10061`), `on_modification_success` `:8748`, `on_query_success` `:8778`, `on_query_error` `:8808`, `on_query_error_enhanced` `:7182`, `on_list_tables_success` `:9785`; ตัว wrapper ที่ทำให้ทุก `results_text.insert` ถูกเขียนลง run log `:3371-3379`; `_stop_event` ถูกล้างเฉพาะใน `_start_stoppable_run` `:8369-8372` (Tables ไม่ได้เรียก) |
| B2 | Import Script Groups ด้วยไฟล์สำเนา `saved_jobs.json` (list ของ Job dict เช่น `[{"name": "Daily", "query": "SELECT 1", "profile": "QA"}]`) **ไม่ขึ้น error** แต่ถาม `Import N group(s)` และถ้าตอบ Yes ได้กลุ่มว่าง (0 scripts) ชื่อเดียวกับ Job | `parse_script_groups_import` `:1163-1183` — รับ bare list `:1169` และ item ที่มี `name` แต่ไม่มี key `scripts` ผ่าน (ถือเป็น `scripts = []`) `:1177`; ผู้เรียก `import_script_groups` `:4743-4752` |
| B3 | scrollbar ของรายการ Saved Jobs **ไม่แสดง** (`winfo_ismapped() == 0`, ไม่มีพื้นที่) หลังสลับไป Profile ที่ไม่มี Job แล้วกลับมา หรือหลังเพิ่ม Job จนล้นกรอบ — `update_jobs_scroll_state` เรียก `jobs_scrollbar.pack(side="right", fill="y")` โดยไม่มี `before=jobs_canvas` จึงถูก pack ต่อจาก canvas (ที่ `expand=True` กินที่หมดแล้ว); mouse wheel ยังเลื่อนได้; มีมาตั้งแต่ initial commit | pack ครั้งแรก `:3012-3013` (ลำดับถูก), `update_jobs_scroll_state` `:3022-3031` (pack ซ้ำ `:3027`, `pack_forget` `:3031`) |

ผู้ได้ประโยชน์: ผู้ใช้ที่กด ⏹ Stop แล้วต้องการยืนยันว่า Stop ทำงาน (B1), ผู้ใช้ที่เลือกไฟล์ผิดตอน Import Groups (B2 — ไม่ได้กลุ่มว่างขยะ), ผู้ใช้ที่มี Saved Jobs มากกว่าที่กรอบแสดงได้ (B3 — เห็น / ลาก scrollbar ได้)

### R16-2. ขอบเขต

#### In scope
- B1: หลังงานแบบ Job เดี่ยว / SQL Editor / Tables จบ (สำเร็จ, error หรือถูกยกเลิก) ถ้ามีการกด Stop ระหว่างงานนั้น บรรทัด `⏹ Stop requested ...` ของงานนั้นต้องยังอยู่ใน Execution Logs ตาม R16-Q-2 / R16-Q-3; ถ้าไม่มีการกด Stop ระหว่างงานนั้น ผลใน Execution Logs เหมือนเดิมทุกตัวอักษร (ยังล้าง Logs เดิมตามปกติ); วิธีทำ (เขียนซ้ำหลังล้าง / ไม่ล้างบรรทัดนั้น / ฯลฯ) ให้ architect กำหนด
- B2: `parse_script_groups_import` (และจึง `import_script_groups` ทั้งจาก sidebar และจากหน้าต่าง Script Groups) ปฏิเสธไฟล์ที่เป็นรูปแบบ Saved Jobs ตามกฎใน R16-Q-1 → แสดง error `Not a valid Script Groups file` เดิม, กลุ่มไม่เปลี่ยน
- B3: `update_jobs_scroll_state` pack scrollbar กลับไว้**ก่อน** `jobs_canvas` (ด้านขวา) ทุกครั้งที่ต้องแสดง

#### Out of scope
- เปลี่ยนข้อความของบรรทัด Stop, ข้อความ `⏹ Stopped — N job(s) not run`, หรือพฤติกรรมของ Run all / Export / Run Group (ไม่ล้าง Logs ตอนจบอยู่แล้ว — ต้องคงผลเดิม ไม่มีบรรทัดซ้ำ)
- เปลี่ยนให้ Tables worker เช็ค Stop (ข้อจำกัดเดิม R5 ที่ระบุใน `docs/tasks.md:122`), เปิดให้กด Stop ได้ขณะหน้าต่าง Loading ของ SQL Editor เปิด
- เลิกล้าง Execution Logs ตอนเริ่ม / จบงานโดยทั่วไป หรือเปลี่ยนรูปแบบผลลัพธ์อื่นใน Logs
- เปลี่ยนรูปแบบไฟล์ที่ `export_script_groups` / `build_script_groups_export` เขียน, เพิ่มการตรวจ `type` / `version` ของไฟล์ import, เพิ่มข้อความ error แยกตามชนิดไฟล์อื่น (Profile export, Preset, Query templates — ถูกปฏิเสธอยู่แล้วเพราะไม่มี `groups` list)
- ปรับ layout / ขนาด / สไตล์ของ sidebar หรือ scrollbar, เปลี่ยน mouse wheel; หัวข้อ M2 / M3 ส่วนอื่น (ข้อความปุ่มถูกตัดที่ 1100x680) — Round นี้แก้เฉพาะ scrollbar
- แก้ test เดิม, commit

### R16-3. User stories
- **R16-US-1** (B1): ในฐานะผู้ใช้ที่กด ⏹ Stop ระหว่างรัน Job / SQL / Tables ฉันต้องการเห็นบรรทัด `⏹ Stop requested ...` ใน Execution Logs หลังงานจบ เพื่อรู้ว่าผลที่เห็น (เช่น `ORA-01013`) มาจากการกด Stop ของฉัน
- **R16-US-2** (B2): ในฐานะผู้ใช้ที่เลือกไฟล์ผิด (สำเนา `saved_jobs.json`) ตอน Import Groups ฉันต้องการให้แอปบอกว่าไฟล์ไม่ถูกต้อง เพื่อไม่ได้กลุ่มว่างที่ต้องตามลบเอง
- **R16-US-3** (B3): ในฐานะผู้ใช้ที่มี Saved Jobs ล้นกรอบ ฉันต้องการเห็น scrollbar ของรายการเสมอเมื่อเนื้อหาล้น เพื่อรู้ว่ามี Job ซ่อนอยู่และลากเลื่อนได้

### R16-4. Acceptance criteria

วิธีทดสอบ: `unittest` แบบ stub เหมือน Round 13-15 (`DatabaseConnectorGUI.__new__`, `_FakeText` ที่เก็บข้อความจริงและรองรับ `delete("1.0", END)` / `insert` / `get`, patch `messagebox` / `filedialog`, `root.after` เรียกทันที, `threading.Thread` เก็บ target ไว้เรียกเองเพื่อกด Stop ระหว่างงาน, connection stub ที่มี / ไม่มี `cancel`) ไม่ต่อ DB จริง; B3 ใช้ `tk.Tk()` จริงแบบ `withdraw()` และ skip เมื่อไม่มี display แบบ `tests/test_r7_script_groups_dialog_rollback.py`; ไฟล์ test ใหม่อยู่ใน `tests/test_r16_*.py`

#### B1 — บรรทัด Stop หายหลังงานจบ (ตาม R16-Q-2 / R16-Q-3)

นิยาม:
- **บรรทัด Stop** = ข้อความที่ `stop_running_queries()` insert ลง `results_text` (สองแบบ: `⏹ Stop requested — cancelled {N} running query(ies); remaining jobs are skipped.` และ `⏹ Stop requested — remaining jobs are skipped. This database driver cannot cancel a running query, so the current one finishes first.`)
- **กด Stop ระหว่างงาน X** = `stop_running_queries()` ถูกเรียกขณะ `_is_busy()` เป็นจริง หลังงาน X เริ่ม และก่อน callback จบของงาน X ทำงาน
- **ข้อความ Logs ตอนจบ** = `results_text.get("1.0", END)` หลัง callback จบของงานทำงานครบ

| AC | Given / When / Then |
|---|---|
| R16-AC-1 (B1) | **Given** `run_job(job)` เริ่มแล้ว (worker ยังไม่ทำงาน), connection ที่ active มี `cancel()` → กด Stop (Logs มี `⏹ Stop requested — cancelled 1 running query(ies); remaining jobs are skipped.`) **When** worker จบด้วย error `ORA-01013: user requested cancel` แล้ว `finish("error", ...)` ทำงาน **Then** ข้อความ Logs ตอนจบมีบรรทัด Stop นั้นครบทุกตัวอักษร **หนึ่งครั้ง**, ยังมีผลของ Job (ข้อความ error ที่ `update_job_status` เขียน) และบล็อก `Total   : 1` / `Success : 0` / `Fail    : 1` เหมือนเดิม, ตำแหน่งตาม R16-Q-2 (default: บรรทัด Stop อยู่ก่อนผลของ Job) |
| R16-AC-2 (B1) | **Given** `run_job` เริ่ม, connection ไม่มี `cancel` → กด Stop (บรรทัด Stop แบบ "This database driver cannot cancel ...") **When** worker จบ**สำเร็จ** (SELECT คืน DataFrame และอีกกรณี DML คืน rows affected) **Then** ข้อความ Logs ตอนจบมีบรรทัด Stop แบบนั้นหนึ่งครั้ง และผลสำเร็จ + `Total   : 1` / `Success : 1` / `Fail    : 0` เหมือนเดิม |
| R16-AC-3 (B1) | **Given** `execute_query()` (SQL Editor) เริ่มแล้ว และกด Stop ระหว่างงาน **When** งานจบผ่านแต่ละทาง: `on_query_success`, `on_modification_success`, `on_query_error` (หน้าต่าง Loading ถูกปิดไปแล้ว — ทาง `on_query_error_enhanced` ที่ dialog ไม่อยู่), และ `on_query_error_enhanced` ที่ dialog ยังเปิด **Then** ข้อความ Logs ตอนจบของทุกทางมีบรรทัด Stop หนึ่งครั้ง และยังมีหัวข้อเดิมของทางนั้นครบ (`✅ Query executed successfully!` / `Statement Executed Successfully!` + `Rows Affected` / `❌ QUERY ERROR` + `Error: ...` / `❌ QUERY ERROR` + `Error Type:`) |
| R16-AC-4 (B1) | **Given** `list_tables()` เริ่มแล้ว (หน้าต่าง Loading Tables) และกด Stop ระหว่างงาน **When** worker จบด้วย `on_list_tables_success` ที่มีตารางอย่างน้อย 1 แถว **Then** ข้อความ Logs ตอนจบมีบรรทัด Stop หนึ่งครั้ง และยังมี `✅ Found ... tables ...`, `Opening results in new window...`, `💡 Tip: ...` เหมือนเดิม; กรณีจบด้วย `on_list_tables_error` หรือ `on_list_tables_success` ที่ list ว่าง (ทางที่ไม่ล้าง Logs) บรรทัด Stop ยังอยู่**หนึ่งครั้ง** (ไม่ถูกเขียนซ้ำ) |
| R16-AC-5 (B1) | **Given** ไม่มีการกด Stop ระหว่างงาน **When** งานจบด้วยทุกทางใน R16-AC-1..4 **Then** ข้อความ Logs ตอนจบเท่ากับผลก่อนแก้ทุกตัวอักษร (Logs ยังถูกล้างแล้วเขียนผลใหม่เหมือนเดิม, ไม่มีคำว่า `Stop requested`) |
| R16-AC-6 (B1) | **Given** งานก่อนหน้า (เช่น `run_job` Job A) ถูกกด Stop และจบไปแล้ว (`_stop_event` อาจยัง set อยู่) **When** เริ่มงานใหม่ที่**ไม่**กด Stop — (ก) `run_job` Job B (ข) `execute_query` (ค) `list_tables` (ซึ่งไม่เรียก `_start_stoppable_run`) — แล้วงานจบ **Then** ข้อความ Logs ตอนจบไม่มีบรรทัด Stop (บรรทัด Stop ของงานก่อนไม่ถูกนำกลับมา); และกรณีกด Stop ตอนไม่มีงานรัน (`_is_busy()` เป็นเท็จ — `stop_running_queries` return ทันที) แล้วเริ่มงานใหม่ที่ไม่กด Stop ก็ไม่มีบรรทัด Stop |
| R16-AC-7 (B1) | **Given** สถานการณ์ R16-AC-1 / R16-AC-3 / R16-AC-4 โดย `results_text.insert` ถูกห่อแบบเดียวกับ `:3371-3379` (หรือ patch `_write_run_log` ให้บันทึกข้อความ) **When** งานจบ **Then** run log ได้รับข้อความที่มี `⏹ Stop requested` **ครั้งเดียวต่อการกด Stop หนึ่งครั้ง** (การแสดงซ้ำใน Logs ไม่เขียนซ้ำลง run log) ตาม R16-Q-2 |
| R16-AC-8 (B1) | **Given** กด Stop **สองครั้ง**ระหว่าง `run_job` เดียวกัน (ครั้งแรก cancel ได้ 1, ครั้งที่สองยัง busy) **When** งานจบ **Then** ข้อความ Logs ตอนจบเป็นไปตาม R16-Q-3 (default: บรรทัด Stop ทั้งสองบรรทัดตามลำดับที่กด) |
| R16-AC-9 (B1) | **Given** Run all 4 Job (`run_selected_job`) และอีกกรณี Export (`export_jobs_to_excel`) ที่กด Stop ก่อน Job ที่ 2 **When** จบ **Then** ข้อความ Logs ตอนจบเหมือนก่อนแก้: บรรทัด Stop **หนึ่งครั้ง** (ไม่ซ้ำ), `⏹ Stopped — 3 job(s) not run` บรรทัดเดียว (Run all), บล็อก `Total` เดิม; test เดิม `tests/test_running_banner.py`, `tests/test_list_tables_stop.py`, `tests/test_run_engine_batch.py`, `tests/test_r15_run_all_and_polls.py` ผ่านโดยไม่แก้ |

#### B2 — Import Script Groups ด้วยไฟล์ Saved Jobs (ตาม R16-Q-1)

นิยาม: **item แบบ Job** = dict ใน list `groups` (หรือ bare list) ที่มี key `"query"` ที่ระดับ item และ**ไม่มี** key `"scripts"` (ไม่สนค่าของ `name` / `query`)

| AC | Given / When / Then |
|---|---|
| R16-AC-10 (B2) | **Given** data = `[{"name": "Daily", "query": "SELECT 1", "profile": "QA"}, {"name": "Weekly", "query": "SELECT 2", "profile": "QA"}]` (รูปแบบ `saved_jobs.json`), อีกกรณีห่อเป็น `{"groups": <list เดียวกัน>}`, และอีกกรณี Job เก่าที่ไม่มี key `profile` **When** `parse_script_groups_import(data)` **Then** raise `ValueError` ที่ข้อความมีคำว่า `scripts` (ข้อความเต็มตาม R16-Q-1) |
| R16-AC-11 (B2) | **Given** Profile `P1` มีกลุ่มอยู่แล้ว และไฟล์ JSON ตาม R16-AC-10 **When** `import_script_groups(parent)` (และ `sidebar_import_script_groups()`) เลือกไฟล์นั้น **Then** `messagebox.showerror("Import Groups", ..., parent=parent)` ถูกเรียกหนึ่งครั้งโดยข้อความขึ้นต้นด้วย `Not a valid Script Groups file:\n`; ไม่เรียก `askyesno` / `askyesnocancel` / `showinfo`; `script_groups` เท่าเดิม (object เดิม เนื้อหาเดิม); `save_script_groups` ไม่ถูกเรียก; ไม่มีบรรทัด `📥 Imported` ใน Logs; คืน `None` |
| R16-AC-12 (B2) | **Given** ไฟล์ผสม: `{"groups": [{"name": "G1", "scripts": [{"query": "SELECT 1"}]}, {"name": "Daily", "query": "SELECT 2"}]}` **When** parse / import **Then** ทั้งไฟล์ไม่ถูกต้องตาม R16-Q-1 (default: raise `ValueError` → error dialog, ไม่ import `G1`) |
| R16-AC-13 (B2) | **Given** ไฟล์ที่ถูกต้องเดิม: (ก) payload จาก `build_script_groups_export` ที่มีกลุ่ม scripts ไม่ว่าง และกลุ่ม `scripts: []` จริง (ข) bare list ของกลุ่ม (ค) item `{"name": "A"}` ที่ไม่มีทั้ง `scripts` และ `query` (ง) item ที่มีทั้ง `query` และ `scripts` เป็น list (ถือเป็นกลุ่ม) (จ) ไฟล์ `script_groups.json` ภายในแอป (`{"version": 1, "groups": [...]}` ที่แต่ละกลุ่มมี `profile`) **When** parse / import **Then** ผลเหมือนก่อนแก้ทุกกรณี (ได้กลุ่มครบ ลำดับเดิม object เดิม; import สำเร็จ); กฎการกรองเดิม (ชื่อว่าง / ไม่ใช่ str / `scripts` ไม่ใช่ list ถูกตัดทิ้ง, script ไม่มี SQL → `ValueError` ที่มีชื่อกลุ่ม) คงเดิม; test เดิม `tests/test_r3_script_groups_io.py` และ `tests/test_r6_import_save_failure.py` ผ่านโดยไม่แก้ |

#### B3 — scrollbar ของ Saved Jobs

นิยาม: สร้าง sidebar ของหน้าต่างหลักด้วย Tk จริงแบบ `withdraw()` (APP_DIR ชี้ temp dir แบบ test build check ของ R3) แล้วเข้าถึง `jobs_canvas`, scrollbar, frame ที่ครอบ และฟังก์ชัน `update_jobs_scroll_state` ผ่านช่องทางที่ architect กำหนด (เช่นเก็บเป็น attribute); "ล้น" = ใส่ widget ลงใน `jobs_container` จนสูงเกินความสูงของ canvas แล้ว `update_idletasks()`; "ไม่ล้น" = ล้าง `jobs_container` จนว่าง; เนื่องจาก root ถูก withdraw `winfo_ismapped()` เป็น 0 เสมอ AC จึงตรวจด้วย `winfo_manager()` / `pack_slaves()` / ตำแหน่ง geometry แทน

| AC | Given / When / Then |
|---|---|
| R16-AC-14 (B3) | **Given** เนื้อหาล้น **When** เรียก `update_jobs_scroll_state` **Then** scrollbar ถูก pack (`winfo_manager() == "pack"`), `pack_info()` มี `side == "right"` และ `fill == "y"`, และใน `pack_slaves()` ของ frame ที่ครอบ scrollbar อยู่**ก่อน** `jobs_canvas` |
| R16-AC-15 (B3) | **Given** เริ่มจากล้น **When** วนรอบ ล้น → ไม่ล้น → ล้น อย่างน้อย 3 รอบ (จำลองสลับไป Profile ที่ไม่มี Job แล้วกลับมา และเพิ่ม Job จนล้น) เรียก `update_jobs_scroll_state` + `update_idletasks()` ทุกขั้น **Then** ทุกขั้นที่ล้น: ผลตาม R16-AC-14, scrollbar ปรากฏใน `pack_slaves()` ครั้งเดียว, `winfo_width()` ของ scrollbar > 1 และขอบขวาของ canvas (`winfo_x() + winfo_width()`) ≤ `winfo_x()` ของ scrollbar (มีพื้นที่จริงทางขวา ไม่ถูกเบียดเป็น 0); ทุกขั้นที่ไม่ล้น: scrollbar ไม่ถูก pack (`winfo_manager() == ""`) และ `yview()[0] == 0.0` เหมือนเดิม |
| R16-AC-16 (B3) | **Given** เนื้อหาล้น **When** เรียก `update_jobs_scroll_state` ซ้ำหลายครั้งติดกัน (ไม่มีขั้นไม่ล้นคั่น) **Then** ลำดับ `pack_slaves()` ยังเป็น scrollbar ก่อน canvas และ `scrollregion` ของ canvas เท่ากับ `bbox("all")` เหมือนเดิม |

#### ข้อกำหนดเดิมที่ต้องคง

| AC | Given / When / Then |
|---|---|
| R16-AC-17 | **Given** แก้ครบ **When** รัน `python -m unittest discover -s tests -p "test_*.py"` สองแบบ ((ก) `PYTHONIOENCODING=utf-8`, (ข) ไม่ตั้ง บน `cp874` + redirect stdout/stderr ไปไฟล์) **Then** ทั้งสองแบบ `OK` จำนวน test เท่ากัน และ ≥ จำนวน test ของ full suite ก่อนเริ่ม Round 16 (qa-tester บันทึกไว้ตอนเริ่ม) + จำนวน test ใหม่ใน `tests/test_r16_*.py`; test เดิมไม่ถูกแก้ (ถ้า test เดิมขัดกับ AC ข้อใดของ Round นี้ ให้หยุดแล้วแจ้งหัวหน้าก่อนแก้) |

**สรุปจำนวน AC Round 16**: 17 ข้อ (B1: 9, B2: 4, B3: 3, ข้อกำหนดเดิม: 1)

### R16-5. ข้อจำกัด / สมมติฐาน
- B1: ทุก `results_text.insert` ถูกเขียนลง run log ผ่าน wrapper `:3371-3379` — ถ้าแสดงบรรทัด Stop ซ้ำด้วย `results_text.insert` ปกติ run log จะมีบรรทัดซ้ำ (R16-AC-7 กันไว้); ไฟล์ run log ไม่ใช่สิ่งที่ผู้ใช้รายงานว่าผิด จึงต้องคงเหมือนเดิม
- B1: `_stop_event` ไม่ใช่ตัวบอกที่เชื่อได้ว่า "กด Stop ระหว่างงานนี้" — Tables ไม่ล้าง event ตอนเริ่ม และ event ค้างหลังงานจบจนกว่างานถัดไปจะเริ่ม (R16-AC-6 กันไว้) — กลไกที่ใช้จำบรรทัด Stop ของงาน ให้ architect กำหนด
- B1: SQL Editor ปกติกด Stop ในหน้าต่างหลักไม่ได้ขณะหน้าต่าง Loading เปิด (grab — ข้อจำกัดเดิมใน README) จึงเกิดได้เมื่อผู้ใช้ปิดหน้าต่าง Loading ก่อน; R16-AC-3 ครอบทั้งทาง dialog ปิดและเปิดเพื่อความครบ
- B1: test เดิมหลายไฟล์ mock `_start_job_result_report` (เช่น `tests/test_run_engine.py:125`, `tests/test_r15_run_all_and_polls.py:107`) — การแก้ต้องไม่ทำให้ test เหล่านี้พัง; `_start_job_result_report` ถูกเรียกทั้งตอนเริ่ม (`:10133`, `:10264`) และตอนจบ (`:10154`) ของ Job — การนำบรรทัด Stop กลับต้องไม่เกิดตอน**เริ่ม**งานใหม่ (R16-AC-6)
- B2: กฎที่แนะนำ (R16-Q-1 (ก)) เลือกให้เข้ากับ test เดิม: `tests/test_r3_script_groups_io.py:185-188` (item `{"name": "NoScriptsKey"}` ต้องผ่าน), `:1003` และ `:1074` (import ไฟล์ `[{"name": "A"}, ...]` ที่ไม่มี `scripts` ต้องสำเร็จ) — กฎ "item ต้องมี `scripts` เสมอ" หรือ "ทุก item ไม่มี `scripts` → ไม่ถูกต้อง" ขัดกับ test เหล่านี้ (ต้องให้ผู้ใช้อนุญาตแก้ test เดิมก่อน)
- B2: ไฟล์ที่ `build_script_groups_export` เขียน (`:1138-1153`) มี key `scripts` เป็น list ทุกกลุ่ม (รวมกลุ่มว่าง) และไม่มี `query` ระดับกลุ่ม จึงไม่โดนกฎใหม่; ไฟล์ export รุ่นเก่าที่ทำด้วยแอปนี้ก็ใช้ฟังก์ชันเดียวกันมาตั้งแต่ Round 3
- B3: ทดสอบด้วย Tk จริงแบบ withdraw (skip เมื่อไม่มี display); การเปิดเผย widget / ฟังก์ชันเพื่อทดสอบต้องไม่เปลี่ยน layout, สี, ขนาด หรือ mouse wheel
- Minimal diff, PEP 8 + type hints ในโค้ดใหม่; ห้าม commit

### R16-6. คำถามที่ยังไม่มีคำตอบ

AC เขียนตามคำตอบที่แนะนำ ถ้าผู้ใช้ต้องการแบบอื่นให้แจ้งก่อนเริ่ม design

| # | คำถาม | คำตอบที่แนะนำ (default) |
|---|---|---|
| R16-Q-1 (B2) | กฎใหม่ว่าไฟล์แบบใดเป็น "ไม่ใช่ Script Groups file" | **(ก) มี item แบบ Job อย่างน้อย 1 ตัว (dict ที่มี key `query` แต่ไม่มี key `scripts`) → ทั้งไฟล์ไม่ถูกต้อง** (raise `ValueError` ข้อความแนะนำ `"'<name>' looks like a Saved Job, not a group (it has 'query' but no 'scripts' list)"` — ใช้ `item <ลำดับ>` แทนเมื่อ name ไม่ใช่ข้อความ) ใช้กับทั้ง bare list และ `{"groups": [...]}`, รวมไฟล์ผสม (ไม่ import บางส่วน) — ไม่ขัด test เดิม และไม่กระทบไฟล์ export ที่ถูกต้อง (รวมกลุ่ม `scripts: []`). ทางเลือก: (ข) ทุก item ต้องมี `scripts` เป็น list ไม่งั้นไม่ถูกต้อง — เข้มกว่าแต่**ขัด test เดิม** `tests/test_r3_script_groups_io.py:185-188`, `:1003`, `:1074` ต้องอนุญาตแก้ test; (ค) ไม่ถูกต้องเมื่อ**ทุก** item ไม่มี `scripts` — ขัด `:1003`, `:1074` เช่นกัน และไฟล์ผสมยัง import กลุ่มว่างได้ — R16-AC-10..13 |
| R16-Q-2 (B1) | บรรทัด Stop ที่คงไว้หลังงานจบ อยู่ตำแหน่งใดใน Execution Logs และเขียนลง run log ซ้ำหรือไม่ | **อยู่ต้น Logs ต่อจากการล้าง ก่อนผลของงาน** (เรียงตามเวลา: กด Stop ก่อนงานจบ — สอดคล้องกับ Run all ที่บรรทัด Stop อยู่ก่อนบล็อก `Total`), ข้อความเดิมทุกตัวอักษร, **ไม่เขียนซ้ำลง run log** (run log มีอยู่แล้วตอนกด). ทางเลือก: ไว้ท้าย Logs หลังผล / `Total` (เห็นง่ายกว่าแต่ลำดับเวลาไม่ตรง) — R16-AC-1..4, R16-AC-7 |
| R16-Q-3 (B1) | กด Stop หลายครั้งระหว่างงานเดียวกัน ให้แสดงบรรทัด Stop อย่างไร | **แสดงทุกบรรทัดตามลำดับที่กด** (ตรงกับที่ผู้ใช้เห็นก่อนงานจบ และตรงกับ run log). ทางเลือก: แสดงเฉพาะบรรทัดแรก หรือบรรทัดล่าสุด — R16-AC-8 |
