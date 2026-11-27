# Tasks — database_connect_gui

> งานที่เสร็จแล้ว (Round 1–15) ถูกลบออกจากไฟล์นี้เมื่อ 2026-11-27 เพื่อลด token ตามคำสั่งผู้ใช้ — ดูย้อนหลังได้จาก git history (`git show ef6d896:docs/<file>`) เลขบรรทัดที่อ้างถึง docs เดิมอาจไม่ตรงแล้ว

## งานค้าง — Manual GUI checklist (ผู้ใช้ทดสอบเอง)

> เตรียม: เปิดแอปด้วย `python database_connect_gui.py`, มี Profile ที่ต่อได้ และ Saved Jobs อย่างน้อย 2 ตัว (ควรมี 1 ตัวที่รันนาน เช่น query ที่ใช้เวลา 20-30 วินาที)
> query รันนานตัวอย่าง: Oracle `SELECT COUNT(*) FROM all_objects a, all_objects b WHERE ROWNUM < 50000000` / PostgreSQL `SELECT pg_sleep(30)` / MySQL `SELECT SLEEP(30)` / SQL Server `WAITFOR DELAY '00:00:30'`
> M3 / M9 รอ Round 16 (B3 / B2); AC-25 ข้อ 2 รอ Round 16 (B1) + ต้องใช้ Oracle จริง; M2 ต้องดูสี/hover ด้วยตา; หลัง R16-T1 ดูด้วยตาว่าหน้าต่างไม่กระตุกตอนเปิดแอปที่มี Job น้อย (R16-R2)

- [ ] **AC-25 Job เดี่ยวบน Oracle: แถบเหลือง + Stop** (**ต้องใช้ Oracle จริง**)
  1. Connect Oracle แล้วกด ▶ ของ Job ที่รันนาน (เช่นชื่อ `Daily Balance`)
     - คาดหวัง: ภายใน ~0.5 วินาที แถบเหลืองขึ้น ข้อความ `กำลังรัน Job · Daily Balance · 00:0x` มีปุ่ม ⏹ Stop กดได้ และ status bar มุมล่างแสดง `Running…`
  2. กด ⏹ Stop
     - คาดหวัง: Execution Logs มี `⏹ Stop requested — cancelled 1 running query(ies)...` Job จบด้วย error `ORA-01013: user requested cancel` แถบเหลืองหายไป และ status bar กลับเป็น `Ready`
- [ ] M2. ปุ่มแถวใหม่สไตล์ ghost เดียวกับ Save / Load (สี/ขนาด/hover) พื้นหลังสีเดียวกับแถบ Preset
- [ ] M3. ที่ขนาดหน้าต่างเริ่มต้น (1200x900) และขนาดเล็กสุด (1100x680) ข้อความปุ่มไม่ถูกตัด/ไม่ล้นขอบ sidebar; รายการ Saved Jobs ยังเลื่อนดูได้ปกติ
- [ ] M9. Import ไฟล์ที่ไม่ใช่ Script Groups (เช่น `saved_jobs.json` สำเนา หรือไฟล์ข้อความ) → error "Not a valid Script Groups file" กลุ่มไม่เปลี่ยน

# Round 16 — Bugfix จาก scripted GUI walk-through (B1, B2, B3)

> design: `docs/design.md` หัวข้อ Round 16 (R16-D1..D8); ผู้ใช้อนุมัติ spec 2026-11-27 และตอบตามค่าแนะนำทุกข้อ: R16-Q-1 = (ก) (มี item ที่มี `query` แต่ไม่มี `scripts` ≥ 1 ตัว → ทั้งไฟล์ไม่ถูกต้อง), R16-Q-2 (บรรทัด Stop ต้น Logs หลังล้าง ก่อนผล ข้อความเดิม ไม่เขียนซ้ำลง run log), R16-Q-3 (กดหลายครั้ง แสดงทุกบรรทัดตามลำดับ); ห้าม commit; test เดิมห้ามแก้ (ถ้าขัดกับ AC ให้หยุดแล้วแจ้งหัวหน้า — R16-AC-17); test ใหม่ `tests/test_r16_*.py`; ทุก task: developer แก้โค้ด → qa-tester เขียน test ของ task + รัน test ที่ระบุ + full suite ต้องผ่าน
> ก่อนเริ่ม R16-T1: qa-tester บันทึกจำนวน test ของ full suite ปัจจุบัน (baseline ของ R16-AC-17) ไว้ใต้ R16-T4
> ลำดับ: B3 → B2 → B1 → regression (แต่ละ task อิสระต่อกัน แต่แก้ไฟล์เดียวกัน — ทำทีละ task)

- [x] R16-T1: B3 — scrollbar ของ Saved Jobs pack ก่อน canvas
  - ไฟล์: `database_connect_gui.py` — nested `update_jobs_scroll_state` ใน `__init__` (`:3022-3031`), ถัด `self.jobs_list_frame = jobs_list_frame` (`:3059`); test `tests/test_r16_jobs_scrollbar.py` (Tk จริง withdraw, skip เมื่อไม่มี display)
  - ทำอะไร: ตาม R16-D4 — ล้น: `if jobs_scrollbar.winfo_manager() != "pack": jobs_scrollbar.pack(side="right", fill="y", before=jobs_canvas)`; ไม่ล้น: `yview_moveto(0)` แล้ว `if jobs_scrollbar.winfo_manager(): jobs_scrollbar.pack_forget()`; เพิ่ม `self.jobs_scrollbar = jobs_scrollbar` และ `self._update_jobs_scroll_state = update_jobs_scroll_state`; ไม่แตะ pack ครั้งแรก `:3012-3013`, mouse wheel, layout / สี / ขนาด; ถ้า `winfo_width()` ใต้ root ที่ withdraw ยังเป็น 1 หลังตั้ง `root.geometry("1100x680")` + `update_idletasks()` ให้หยุดแล้วแจ้งหัวหน้า (R16-R1); รัน `python -m unittest tests.test_r3_script_groups_io tests.test_r7_script_groups_dialog_rollback` ต้องผ่าน
  - AC ที่ครอบคลุม: R16-AC-14, R16-AC-15, R16-AC-16
  - ขึ้นกับ: -
  - ผล QA (2026-11-27): `tests/test_r16_jobs_scrollbar.py` 14 test ผ่าน; `tests.test_r3_script_groups_io` + `tests.test_r7_script_groups_dialog_rollback` Ran 198 OK; full suite (`PYTHONIOENCODING=utf-8`) Ran 1437 tests OK (= baseline 1423 + 14); รัน test ชุดใหม่กับโค้ด HEAD (เพิ่มแค่ 2 บรรทัด expose attribute) → FAILED 10/14 รวมกรณีลำดับ pack (`[canvas, scrollbar]`), ไม่ล้นแล้วไม่ pack_forget, และ re-pack ทุกครั้ง
  - หมายเหตุ R16-R1 (ผู้ใช้อนุมัติ 2026-11-27): root ที่ withdraw ให้ `winfo_width/height` = 1 จึงตรวจส่วนพิกเซลของ R16-AC-15 (ความกว้าง scrollbar > 1, ขอบขวา canvas ≤ x ของ scrollbar) ด้วยวิธีแทน: ปลอมความสูง canvas (patch `jobs_canvas.winfo_height` เป็นค่าใหญ่) เพื่อบังคับกรณีไม่ล้น แล้วตรวจ `winfo_manager()`, `pack_slaves()` (scrollbar ก่อน canvas, ปรากฏครั้งเดียว, ไม่ล้น → ไม่อยู่ใน pack_slaves), `pack_info()` (side=right, fill=y) — ไม่ deiconify / ไม่ตรวจพิกเซลจริง; ยังเหลือตรวจด้วยตาตาม R16-R2 (Manual)
- [x] R16-T2: B2 — Import Groups ปฏิเสธไฟล์ Saved Jobs
  - ไฟล์: `database_connect_gui.py` — `parse_script_groups_import` (`:1163-1183`); test `tests/test_r16_import_saved_jobs.py`
  - ทำอะไร: ตาม R16-D3 — ลูปตรวจ list ดิบหลัง `:1170-1171` ก่อนตัวกรอง `:1172`: item ที่เป็น dict มี key `"query"` และไม่มี key `"scripts"` → `raise ValueError(f"{label} looks like a Saved Job, not a group (it has 'query' but no 'scripts' list)")` (`label` = `'<name>'` เมื่อ name เป็นข้อความไม่ว่าง ไม่งั้น `item <ลำดับเริ่ม 1>`); เพิ่มประโยคใน docstring; **ไม่แก้** `import_script_groups` / `sidebar_import_script_groups` (error dialog เดิม `:4747-4749` จัดการให้); รัน `python -m unittest tests.test_r3_script_groups_io tests.test_r6_import_save_failure tests.test_r7_script_groups_dialog_rollback tests.test_script_groups_block tests.test_script_groups_backup` ต้องผ่าน
  - AC ที่ครอบคลุม: R16-AC-10, R16-AC-11, R16-AC-12, R16-AC-13
  - ขึ้นกับ: -
  - ผล QA (2026-11-27): `tests/test_r16_import_saved_jobs.py` 51 test ผ่าน (parse: bare list / `{"groups"}` / Job ไม่มี profile / ไฟล์ผสม / label `item N` กรณีไม่มี name, name ว่าง, ช่องว่าง, ไม่ใช่ str, นับตำแหน่งใน list ดิบ; import จริงผ่าน `import_script_groups(window)` และ `sidebar_import_script_groups()` ด้วย APP_DIR temp + load/save จริง → `showerror("Import Groups", "Not a valid Script Groups file:\n...")` parent ถูก, ไม่เรียก askyesno*/showinfo, ไม่ save, list object/เนื้อหาเดิม, ไฟล์ `script_groups.json` ไบต์เดิม ไม่มี backup; regression `{"name": "A"}`, query+scripts, export → import round-trip, ไฟล์ภายใน, error script ไม่มี SQL เดิม); `tests.test_r3_script_groups_io` + `test_r6_import_save_failure` + `test_r7_script_groups_dialog_rollback` + `test_script_groups_block` + `test_script_groups_backup` Ran 271 OK; full suite (`PYTHONIOENCODING=utf-8`) Ran 1488 tests OK (= 1437 + 51); รัน test ชุดใหม่กับโค้ด HEAD → FAILED 32/51 test (43 failures รวม subTest) — ที่ผ่านคือ test regression AC-13 ตามคาด
- [x] R16-T3: B1 — บรรทัด Stop ยังอยู่ใน Execution Logs หลังงาน Job เดี่ยว / SQL Editor / Tables จบ
  - ไฟล์: `database_connect_gui.py` — `__init__` (`self._stop_lines = []` ถัด `:2601`; แทน wrapper `:3371-3379` ด้วย `self._install_run_log_hook()`), method ใหม่ `_install_run_log_hook` / `_replay_stop_lines` / `_clear_results_keep_stop_lines` (ถัด `_start_stoppable_run` `:8369`), `_start_stoppable_run` (`:8369-8372`), `stop_running_queries` (`:8478`), `_start_job_result_report` (`:10060-10061`), `run_job.finish` (`:10154`), `on_query_error_enhanced` (`:7182`), `on_modification_success` (`:8748`), `on_query_success` (`:8778`), `on_query_error` (`:8808`), `list_tables` (`:9483`), `on_list_tables_success` (`:9785`); test `tests/test_r16_stop_lines.py`
  - ทำอะไร: ตาม R16-D2 —
    1. `stop_running_queries`: หลัง insert `msg` → `self.__dict__.setdefault("_stop_lines", []).append(msg)` (ข้อความ / ลำดับ insert เดิม)
    2. ล้าง list เมื่องานเริ่มจริง: บรรทัดแรกของ `_start_stoppable_run` = `self._stop_lines = []`; `list_tables` ก่อน insert `Fetching database schema information...` (หลัง early return ทุกตัว) = `self._stop_lines = []` (ไม่เพิ่ม `_stop_event.clear()`)
    3. `_install_run_log_hook` เก็บ `self._results_text_raw_insert` (insert ที่ไม่เขียน run log) แล้วห่อ `results_text.insert` แบบเดิม
    4. `_replay_stop_lines` เขียน `_stop_lines` ด้วย raw insert (fallback `results_text.insert`); `_clear_results_keep_stop_lines` = `delete("1.0", END)` + replay
    5. `_start_job_result_report(self, keep_stop_lines: bool = False)`; `run_job.finish` เรียกด้วย `keep_stop_lines=True`; ตอนเริ่ม (`:10133`, `:10264`) ไม่แก้
    6. แทน `self.results_text.delete("1.0", tk.END)` ด้วย `self._clear_results_keep_stop_lines()` 5 จุด (`:7182`, `:8748`, `:8778`, `:8808`, `:9785`); ไม่แตะ `execute_query :8694`, `on_list_tables_error`, list ว่าง `:9817`, Run all / Export / Run Group, และ `delete` จุดอื่น (`:4348`, `:4363`, `:4563`, `:4595`, `:5619`, `:5809`, `:10021`, `:10718`)
    - รัน `python -m unittest tests.test_running_banner tests.test_list_tables_stop tests.test_run_engine tests.test_run_engine_batch tests.test_r15_run_all_and_polls tests.test_r14_run_redaction tests.test_r14_jobs_redaction tests.test_run_entry_block tests.test_r4_profile_mismatch tests.test_run_lock tests.test_r11_connection_target_snapshot tests.test_r13_tables_and_patterns tests.test_r15_tables_select_sql tests.test_r7_console_print` ต้องผ่าน
  - AC ที่ครอบคลุม: R16-AC-1, R16-AC-2, R16-AC-3, R16-AC-4, R16-AC-5, R16-AC-6, R16-AC-7, R16-AC-8, R16-AC-9
  - ขึ้นกับ: -
  - ผล QA (2026-11-27): `tests/test_r16_stop_lines.py` 40 test ผ่าน (FakeText เก็บข้อความจริง + `_install_run_log_hook` จริง + `_write_run_log` mock; Job เดี่ยว Stop→error ตรงทุกตัวอักษร `ล้าง → บรรทัด Stop → ผล update_job_status → Total` บรรทัด Stop ครั้งเดียว; driver ไม่มี cancel SELECT/DML สำเร็จ; กด 2-3 ครั้งแสดงทุกบรรทัดตามลำดับ; SQL Editor ทั้ง 4 ทาง + enhanced dialog ปิด (winfo_exists 0 / TclError) replay ครั้งเดียว + debug mode; Tables สำเร็จ / error / list ว่าง; run log ได้บรรทัด Stop ครั้งเดียวต่อการกด; ไม่กด Stop → Logs ตรงทุกตัวอักษรทุกทาง; งานใหม่ (Job / SQL / Tables ที่ `_stop_event` ยัง set / Run all start) ไม่มีบรรทัด Stop ของงานก่อน; กด Stop ตอน idle ไม่เพิ่ม `_stop_lines`; Run all / Run Group / Export 4 Job กด Stop ก่อน Job 2 → บรรทัด Stop 1 ครั้ง + `⏹ Stopped — 3 job(s) not run/exported` 1 ครั้ง; stub `__new__` ไม่มี `_stop_lines` / `_results_text_raw_insert` ไม่ crash); test ที่ระบุใน task Ran 292 OK; full suite (`PYTHONIOENCODING=utf-8`) Ran 1528 tests OK (= 1488 + 40); รัน test ชุดใหม่กับโค้ด HEAD (จำลอง wrapper เดิม) → FAILED 29/40 — ที่ผ่านคือ test "ไม่กด Stop เหมือนเดิม" / batch / Tables error-list ว่าง / idle Stop ตามคาด
- [x] R16-T4: Regression ทั้งชุด สอง mode encoding
  - ไฟล์: - (รันเท่านั้น)
  - ทำอะไร: `python -m unittest discover -s tests -p "test_*.py"` (ก) `PYTHONIOENCODING=utf-8`, (ข) ไม่ตั้ง (cp874) + redirect stdout/stderr ไปไฟล์ → `OK` ทั้งคู่ จำนวนเท่ากัน ≥ baseline (บันทึกก่อนเริ่ม R16-T1) + test ใหม่ใน `tests/test_r16_*.py`; `git diff tests/` ต้องไม่มี test เดิมถูกแก้; `git status` ไม่มีไฟล์ใหม่ / เปลี่ยนใน APP_DIR (`script_groups.json`, `saved_jobs.json`, `db_profiles.json`, `*_unreadable_*`) และ `logs/`
  - baseline full suite ก่อน Round 16: Ran 1423 tests, OK (`PYTHONIOENCODING=utf-8`)
  - AC ที่ครอบคลุม: R16-AC-17
  - ขึ้นกับ: R16-T1, R16-T2, R16-T3
  - ผล QA (2026-11-27): (ก) `PYTHONIOENCODING=utf-8` → Ran 1528 tests OK; (ข) ไม่ตั้ง (stdout encoding `cp874`) + redirect stdout/stderr ไปไฟล์ → Ran 1528 tests OK; 1528 = baseline 1423 + test r16 105 (scrollbar 14 + import 51 + stop lines 40); `git diff tests/` ว่าง (test เดิมไม่ถูกแก้ มีแค่ไฟล์ใหม่ `tests/test_r16_*.py` 3 ไฟล์); `script_groups.json` / `saved_jobs.json` / `db_profiles.json` / `logs/` ขนาดและ mtime เดิมก่อน-หลังรัน (ไฟล์เหล่านี้อยู่ใน .gitignore จึงตรวจด้วย snapshot `ls`), ไม่มี `*_unreadable_*`

## ตาราง R16-AC → Task

| AC | Task | AC | Task | AC | Task |
|---|---|---|---|---|---|
| R16-AC-1 | R16-T3 | R16-AC-2 | R16-T3 | R16-AC-3 | R16-T3 |
| R16-AC-4 | R16-T3 | R16-AC-5 | R16-T3 | R16-AC-6 | R16-T3 |
| R16-AC-7 | R16-T3 | R16-AC-8 | R16-T3 | R16-AC-9 | R16-T3 |
| R16-AC-10 | R16-T2 | R16-AC-11 | R16-T2 | R16-AC-12 | R16-T2 |
| R16-AC-13 | R16-T2 | R16-AC-14 | R16-T1 | R16-AC-15 | R16-T1 |
| R16-AC-16 | R16-T1 | R16-AC-17 | R16-T1..T3 (test ใหม่), R16-T4 | | |
