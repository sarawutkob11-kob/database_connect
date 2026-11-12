# Tasks — Bugfix C1, C2, H1, H2

> อ้างอิง: `docs/spec.md` (AC-1 ถึง AC-38), `docs/design.md`
> สถานะ: `[ ]` ยังไม่เริ่ม, `[~]` กำลังทำ, `[x]` เสร็จและ test ผ่าน, `[!]` ติดปัญหา
> ไฟล์ source ทุก task คือ `database_connect_gui.py` (ยกเว้น T14) เลขบรรทัดเป็นค่าก่อนเริ่มแก้
> ทุก task: test เดิมต้องยังผ่าน (`python -m unittest discover -s tests -p "test_*.py"`)
> ลำดับต่างจากที่หัวหน้าแนะนำเล็กน้อย: helper busy (T1) มาก่อน H2 (T2) เพราะ AC-27 ต้อง log เมื่อ busy

---

- [x] T1: Busy check กลาง
  - ไฟล์: `database_connect_gui.py` — เมธอดใหม่ `_is_busy`, `_log_blocked`, `_block_if_busy` (วางใกล้ `_is_query_running` 7312)
  - ทำอะไร: `_is_busy()` = `_is_query_running()` หรือ `_running_job_ids` ไม่ว่าง หรือ `inspect_btn` แสดง "Loading"; `_log_blocked(action)` เขียนข้อความตาม design ข้อ 3 ลง `results_text` + `see(END)` ไม่มี popup; `_block_if_busy(action)` คืน True และ log เมื่อ busy ยังไม่ต้องเรียกใช้ที่ไหน
  - AC ที่ครอบคลุม: AC-20, AC-21, AC-22, AC-23 (ระดับ logic)

- [x] T2: H2 — Ctrl+Enter เคารพสถานะปุ่ม Run
  - ไฟล์: `database_connect_gui.py` — เมธอดใหม่ `_on_sql_ctrl_enter`; binding `<Control-Return>` 2660-2665
  - ทำอะไร: เทียบ `str(self.execute_btn["state"]) == "disabled"` ถ้าปิดอยู่และ `_is_busy()` ให้ `_log_blocked("Run")` แล้วจบ มิฉะนั้นเรียก `execute_query()` เปลี่ยน binding ให้ชี้เมธอดนี้ คืน None เหมือนเดิม
  - AC ที่ครอบคลุม: AC-27, AC-28, AC-29

- [x] T3: C2 — อ่าน script_groups.json ไม่ได้ต้องบล็อกการบันทึก
  - ไฟล์: `database_connect_gui.py` — `load_script_groups` 3950-3961, `save_script_groups` 3963 (เฉพาะส่วนต้น)
  - ทำอะไร: ใน except ของ load ใช้ `self._script_groups_save_blocked = self._handle_unreadable_file(path, "Script Groups", e)` แทน `showerror` แล้วคืน `[]`; ไม่มีไฟล์ → `[]` โดยไม่ตั้ง flag; ต้น `save_script_groups` ถ้า flag True ให้ `showerror` ตามข้อความใน design ข้อ 6 แล้ว return โดยไม่แตะไฟล์ใด
  - AC ที่ครอบคลุม: AC-14, AC-15

- [x] T4: C2 — กติกา backup ครั้งแรกของเซสชัน + เขียนแบบ atomic
  - ไฟล์: `database_connect_gui.py` — `save_script_groups` 3972-3984, เมธอดใหม่ `_backup_script_groups_once`
  - ทำอะไร: ครั้งแรกของเซสชัน (`_script_groups_backup_done` ยังไม่ True) เรียก `_backup_script_groups_once(path)` ซึ่งตั้ง flag เป็น True เสมอ และ copy เป็น `script_groups_backup.json` เฉพาะเมื่อไฟล์มีอยู่และ `json.load` ได้; เปลี่ยนการเขียนเป็น `write_json_atomic(path, {"version": 1, "groups": clean}, indent=2)` คงการตัด key `_*` และ `run_index`
  - AC ที่ครอบคลุม: AC-16, AC-17, AC-18, AC-19, AC-36
  - หมายเหตุ (เปลี่ยนตามคำขอของผู้ใช้หลัง T15): `_backup_script_groups_once` ตั้ง `_script_groups_backup_done = True` เฉพาะเมื่อขั้น backup จบโดยไม่มี error (copy สำเร็จ หรือไม่มีไฟล์ / ไฟล์ไม่ใช่ JSON ที่อ่านได้) ถ้า `copy2` ล้มเหลว flag ยังเป็น False การบันทึกครั้งนั้นถูกปฏิเสธ (showerror เหมือนเดิม) และการบันทึกครั้งถัดไปจะลอง backup ใหม่

- [x] T5: C1 — บล็อก Connect และการเปลี่ยน/แก้/ลบ/Import Profile ระหว่างรัน
  - ไฟล์: `database_connect_gui.py` — `connect_database` 6987, `on_profile_selected` 9982, `load_profile_data` 10033, `save_profile_dialog` 10094 (+ `save()` 10159), `new_profile_dialog` 10174, `delete_profile` 10439, `import_profiles_dialog` 3012
  - ทำอะไร: ใส่ `_block_if_busy(<action>)` บรรทัดแรกของแต่ละเมธอดตามตาราง design ข้อ 3 (connect ต้องอยู่ก่อนแก้ช่อง port 6994); เพิ่ม `_active_profile` (ตั้งใน `load_profile_data` เมื่อสำเร็จ และใน `save()` ของ save_profile_dialog); `on_profile_selected` ที่ถูกบล็อกให้ `profile_combo.set(_active_profile)` และไม่เรียก `load_profile_data` / `update_jobs_list`
  - AC ที่ครอบคลุม: AC-1, AC-2, AC-3, AC-4, AC-32, AC-33, AC-34

- [x] T6: C1 — บล็อกการเริ่มงานใหม่ทุกประเภทระหว่างรัน
  - ไฟล์: `database_connect_gui.py` — `execute_query` 7537, `run_job` 8834 (ลบเช็คเดิม 8849-8862), `run_selected_job` 8949 (ลบเช็ค 8977), `export_jobs_to_excel` 9388, `list_tables` 8273, wrapper `_ui_run_selected_job` 2810-2818, `run_group` ใน Script Groups 4549-4559
  - ทำอะไร: ใส่ `_block_if_busy` บรรทัดแรกตาม design ข้อ 3 (execute_query ต้องอยู่ก่อน `results_text.delete`); wrapper เช็ค `_is_busy()` ก่อน reset `_ui_progress`; `run_group` ลบเช็ค `_batch_running` + `messagebox.showinfo` (ให้ `run_selected_job` บล็อกและ log เอง)
  - AC ที่ครอบคลุม: AC-5, AC-6

- [x] T7: C1 — ปิด/เปิดปุ่มตามสถานะ busy (UI lock)
  - ไฟล์: `database_connect_gui.py` — `__init__` 2073-2092 (เก็บ `_profile_menu`, `_profile_action_buttons`), `update_jobs_list` 3487/3578-3585 (`_job_run_buttons`), Script Groups 4399-4400 และ 4753-4754, `_refresh_stop_buttons` 7436; เมธอดใหม่ `_register_run_lock_button`, `_apply_run_lock`, `_set_widget_state`
  - ทำอะไร: `_apply_run_lock(busy)` ตั้ง state ตามตาราง design ข้อ 4 (combobox ตอนว่าง = `readonly`, Run/Tables ตอนว่าง = normal เฉพาะเมื่อ `self.engine` ไม่ใช่ None, Delete profile ผ่าน `entryconfig(0, ...)`, ตัด widget ที่ถูกทำลายออกจาก list); `_refresh_stop_buttons` เรียก `_apply_run_lock(self._is_busy())` ทุกรอบ; ลงทะเบียน Run Group / Export Group พร้อม `idle_state` และให้ `update_buttons` ไม่เปิดปุ่มทั้งสองระหว่าง busy
  - AC ที่ครอบคลุม: AC-31, AC-12, AC-13

- [x] T8: C1 — ConnectionInfo / RunTarget และการเก็บ snapshot ตอน Connect
  - ไฟล์: `database_connect_gui.py` — import `typing`, class ใหม่ `ConnectionInfo`, `RunTarget` (หลัง `SqlAssessment` ~250), `connect_database` 7041, `_replace_engine` 7061, `_reset_profile_connection_state` 10022, เมธอดใหม่ `_capture_run_target`
  - ทำอะไร: สร้าง dataclass ตาม design ข้อ 2 (ไม่มีรหัสผ่าน, `target_label`, `log_target`, `run_log_header` ให้ข้อความเหมือนรูปแบบเดิม); `_replace_engine(engine, info=None)` ตั้ง `_run_target`; Connect สำเร็จส่ง `ConnectionInfo` ที่อ่านจากช่องตอนนั้น; reset profile ล้าง `_run_target`; `_capture_run_target()` ตาม design ข้อ 5
  - AC ที่ครอบคลุม: AC-2 (ยังทำงานเหมือนเดิม), เป็นฐานของ AC-9, AC-10, AC-11, AC-35

- [x] T9: C1 — engine ของงานใน read/modify + SQL Editor + Job เดี่ยว
  - ไฟล์: `database_connect_gui.py` — `read_sql_dataframe` 7109, `_execute_modification` 7166, `_execute_query_background` 6197, `execute_query` 7549-7572, `run_job` 8864-8947, `_start_stoppable_run` 7322
  - ทำอะไร: เพิ่ม parameter `engine=None` (None → `self.engine`) ใน 3 เมธอดแรก; `execute_query` และ `run_job` จับ `target = self._capture_run_target()` ก่อน `_confirm_data_change` แล้วส่ง `engine=target.engine` ให้ worker และ `target=target` ให้ `_confirm_data_change` / `_start_stoppable_run`; `_start_stoppable_run(target=None)` ส่งต่อให้ `_log_run_context`; ใน task นี้เพิ่ม parameter `target=None` ให้ `_confirm_data_change` และ `_log_run_context` ไว้ก่อน (ยังไม่ใช้ค่า ใช้จริงใน T11); worker ห้ามอ่าน `self.engine`
  - AC ที่ครอบคลุม: AC-7, AC-8, AC-9 (worker ของ `_execute_query_background` และ `run_job`)

- [x] T10: C1 — engine ของงานใน Run All / Run Group / Export / list_tables
  - ไฟล์: `database_connect_gui.py` — `run_selected_job` 8980-9153, `export_jobs_to_excel` 9427-9558, `list_tables` 8275-8539
  - ทำอะไร: จับ `target` ครั้งเดียวบน main thread ตามตาราง design ข้อ 5; `run_all_jobs` และ `worker` ของ Export ส่ง `engine=target.engine`; `fetch_tables_in_background` ใช้ `target.engine` แทน `self.engine` ทุกจุด และ `db_type` จาก `target.info` (fallback อ่าน `self.db_type.get()` บน main thread ก่อนเริ่ม thread); ไม่แตะส่วน `temp_engine` 8393-8400
  - AC ที่ครอบคลุม: AC-9 (Run All 2 Job, Export)

- [x] T11: C1 — หน้ายืนยันและ Run log ใช้ปลายทางของงานจริง
  - ไฟล์: `database_connect_gui.py` — `_confirm_data_change` 7454-7535, `_log_run_context` 7383-7396, เมธอดใหม่ `_confirm_destination`
  - ทำอะไร: `_confirm_data_change(jobs, target=None)` ใช้ `profile, target_text = self._confirm_destination(target)` แทนการอ่านช่อง 7477-7481 / 7491; `_log_run_context(target=None)` เขียน `info.run_log_header()` ผ่าน `_write_run_log` ไม่อ่านช่องบนหน้าจอ ไม่มีรหัสผ่าน
  - AC ที่ครอบคลุม: AC-10, AC-11, AC-35

- [x] T12: H1 — แถบเหลือง / status bar / Stop แสดงทุกครั้งที่มีงานรัน
  - ไฟล์: `database_connect_gui.py` — `_refresh_live_ui` 2846-2874, `run_job` (หลัง `running_jobs.add`), `stop_running_queries` 7407, `_refresh_stop_buttons` 7439, เมธอดใหม่ `_running_banner_state`
  - ทำอะไร: `_refresh_live_ui` ใช้ `busy = self._is_busy()` และข้อความ/โหมด progress จาก `_running_banner_state(elapsed)` ตามตาราง design ข้อ 7; `run_job` ตั้ง `_ui_progress` เป็น kind `"job"` พร้อมชื่อ Job; Stop (ปุ่ม + guard) ใช้ `_is_busy()`
  - AC ที่ครอบคลุม: AC-20, AC-21, AC-22, AC-23 (ผ่าน `_refresh_live_ui`), AC-24, AC-25

- [x] T13: H1 — ปุ่ม Stop ในหน้าต่าง Loading ของ list_tables
  - ไฟล์: `database_connect_gui.py` — `list_tables` 8289-8307, เมธอดใหม่ `_create_list_tables_loading_dialog`
  - ทำอะไร: ย้ายโค้ดสร้างหน้าต่าง Loading มาไว้ในเมธอดใหม่ (คง `grab_set()`) เพิ่มปุ่ม `ui_rbutton(dialog, "⏹  Stop", self.stop_running_queries, "danger", "sm")` และ `self._register_stop_button(btn)`; `list_tables` เรียกเมธอดนี้
  - AC ที่ครอบคลุม: AC-37, AC-38

- [x] T14: README
  - ไฟล์: `README.md` บรรทัด 47, 51
  - ทำอะไร: ระบุว่าแถบสีเหลืองขึ้นทุกครั้งที่มี Query / Job รัน รวมปุ่ม ▶ (แสดงชื่อ Job), กด Stop ได้ระหว่างโหลดรายการ Table (ปุ่ม Stop ในหน้าต่าง Loading), และระหว่างรันจะกด Connect / เปลี่ยน-แก้-ลบ-Import Profile / เริ่มงานอื่นไม่ได้ (ปุ่มเป็นสีเทา เหตุผลแสดงใน Execution Logs)
  - AC ที่ครอบคลุม: AC-26

- [x] T15: Regression ทั้งชุด
  - ไฟล์: — (qa-tester รันอย่างเดียว)
  - ทำอะไร: รัน `python -m unittest discover -s tests -p "test_*.py"` หลังทุก task เสร็จ และรวบรวม checklist Manual/GUI (AC-13, AC-25, AC-29, AC-37) ให้หัวหน้า
  - AC ที่ครอบคลุม: AC-30
  - ผล: `Ran 319 tests ... OK` (รันซ้ำด้วย `-W always` ไม่มี warning), `python -m py_compile database_connect_gui.py` ผ่าน; AC แบบ unittest ทุกข้อมี test (ดูตาราง "AC → ไฟล์ test" ด้านล่าง)

---

## Manual GUI checklist (ผู้ใช้ทดสอบเอง)

> เตรียม: เปิดแอปด้วย `python database_connect_gui.py`, มี Profile ที่ต่อได้ และ Saved Jobs อย่างน้อย 2 ตัว (ควรมี 1 ตัวที่รันนาน เช่น query ที่ใช้เวลา 20-30 วินาที)
> ข้อที่ต้องใช้ **Oracle จริง**: AC-25 (และ AC-37 ถ้าต้องการเห็นการยกเลิก query จริง) ข้ออื่นใช้ฐานข้อมูลใดก็ได้
> query รันนานตัวอย่าง: Oracle `SELECT COUNT(*) FROM all_objects a, all_objects b WHERE ROWNUM < 50000000` / PostgreSQL `SELECT pg_sleep(30)` / MySQL `SELECT SLEEP(30)` / SQL Server `WAITFOR DELAY '00:00:30'`

- [ ] **AC-13 ปุ่มเป็นสีเทาระหว่างรัน** (ฐานข้อมูลใดก็ได้)
  1. Connect แล้วเริ่มงานรันนานทีละแบบ: ▶ Run (SQL Editor), ▶ ของ Job การ์ดหนึ่ง, ▶ Run all, ⇩ Export, ▦ Tables, และ ▶ Run Group ในหน้าต่าง Script Groups
  2. ระหว่างรันแต่ละแบบ ดูปุ่ม
     - คาดหวัง: Connect, combobox Profile, Import / Save / ＋ New, เมนู ⋯ → Delete profile, ▶ Run, ▶ ของทุกการ์ด, Run all, Export, Tables, Run Group / Export Group เป็นสีเทากดไม่ได้ (ปุ่ม Export profile, ⋯ เอง และ Save as Job ไม่อยู่ใน lock)
- [ ] **AC-12 ปุ่มกลับมาใช้ได้หลังงานจบ** (ฐานข้อมูลใดก็ได้)
  1. ทำต่อจาก AC-13 ทั้ง 3 กรณี: ปล่อยให้จบสำเร็จ / ใช้ SQL ผิดให้ error / กด ⏹ Stop
     - คาดหวัง: ภายใน ~0.3 วินาทีหลังงานจบ ปุ่มทั้งหมดในข้อ AC-13 กลับมากดได้ combobox Profile เลือกได้แต่พิมพ์ไม่ได้ (readonly) Run / Tables กดได้เฉพาะตอนต่อฐานข้อมูลอยู่
- [ ] **AC-25 Job เดี่ยวบน Oracle: แถบเหลือง + Stop** (**ต้องใช้ Oracle จริง**)
  1. Connect Oracle แล้วกด ▶ ของ Job ที่รันนาน (เช่นชื่อ `Daily Balance`)
     - คาดหวัง: ภายใน ~0.5 วินาที แถบเหลืองขึ้น ข้อความ `กำลังรัน Job · Daily Balance · 00:0x` มีปุ่ม ⏹ Stop กดได้ และ status bar มุมล่างแสดง `Running…`
  2. กด ⏹ Stop
     - คาดหวัง: Execution Logs มี `⏹ Stop requested — cancelled 1 running query(ies)...` Job จบด้วย error `ORA-01013: user requested cancel` แถบเหลืองหายไป และ status bar กลับเป็น `Ready`
- [ ] **AC-24 (การแสดงผล) ข้อความแถบเหลือง** (ฐานข้อมูลใดก็ได้)
  - คาดหวัง: Run all → `กำลังรัน Job i / N · <ชื่อ> · mm:ss` พร้อม progress bar แบบเต็มขึ้นเรื่อย ๆ; Export → `กำลัง Export Excel · mm:ss`; SQL Editor / Tables → `กำลังรัน SQL · mm:ss`
- [ ] **AC-29 Ctrl+Enter ระหว่าง Run all** (ฐานข้อมูลใดก็ได้)
  1. กด ▶ Run all ด้วย Job ที่รันนาน แล้วคลิกใน SQL Editor กด `Ctrl+Enter`
     - คาดหวัง: ไม่มี SQL ใหม่รัน ไม่มีหน้ายืนยัน / หน้าต่าง Loading / popup ใหม่ และ Execution Logs มีบรรทัด `⏳ Run: ทำไม่ได้ระหว่างที่มีงานรันอยู่ — รอให้งานเสร็จหรือกด ⏹ Stop ก่อน`
  2. หลัง Run all จบ กด `Ctrl+Enter` อีกครั้ง → SQL ใน Editor รันตามปกติ
- [ ] **AC-37 ปุ่ม Stop ในหน้าต่าง Loading ของ Tables** (ฐานข้อมูลใดก็ได้; Oracle เห็นการยกเลิกจริง)
  1. Connect ฐานข้อมูลที่มี schema / table เยอะ (ปล่อยช่อง Database ว่างเพื่อให้โหลดนานขึ้น) แล้วกด ▦ Tables
     - คาดหวัง: หน้าต่าง `Loading Tables...` มีปุ่ม ⏹ Stop ซึ่งกดได้ภายใน ~0.3 วินาที
  2. กด ⏹ Stop
     - คาดหวัง: Execution Logs มี `⏹ Stop requested ...` (ข้อนี้คือสิ่งที่ AC-37 ต้องการ); หน้าต่าง Loading ปิดเองเมื่อโหลดจบ และปุ่ม Tables กลับเป็น `▦ Tables`
     - ข้อจำกัดเดิม (R5, ไม่ใช่บั๊กของรอบนี้): worker ของ Tables ไม่เช็ค Stop: Oracle จะยกเลิกเฉพาะ query ที่กำลังรัน แล้วโหลด schema ถัดไปต่อ (รายการอาจไม่ครบ); PostgreSQL / MySQL / SQL Server ยกเลิกไม่ได้ จะรอจนโหลดเสร็จ
- [ ] **AC-26 README** (อ่านเอกสาร)
  - เปิด `README.md` หัวข้อ "### 2. SQL Editor" บรรทัด 47, 51, 52 ตรวจว่าตรงกับที่เห็นจากข้อด้านบน (Stop ใช้ได้ทุกงาน ยกเว้นตอนหน้าต่าง Loading ของ SQL Editor เปิดอยู่; แถบเหลืองขึ้นทุกครั้งพร้อมชื่อ Job; ปุ่มเทาจนกว่างานจบจริง)
- [ ] **ข้อสังเกตเพิ่มเติม (ไม่มี AC)**: SQL Editor ▶ Run กับ query รันนาน → ปิดหน้าต่าง Loading ด้วย X → คาดหวัง: ปุ่ม Run ยังเป็น `⏳ Loading...` จนกว่า query จะจบ และกด ⏹ Stop ในแถบเหลืองได้ (ยืนยันว่าพฤติกรรมนี้เป็นที่ต้องการ)

## ตาราง AC → ไฟล์ test (unittest)

| AC | ไฟล์ test |
|---|---|
| AC-1, AC-2, AC-3, AC-4, AC-32, AC-33, AC-34 | `tests/test_profile_connect_block.py` (AC-2 เพิ่มใน `tests/test_run_target.py`) |
| AC-5, AC-6 | `tests/test_run_entry_block.py` |
| AC-7, AC-8, AC-9 | `tests/test_run_engine.py`, `tests/test_run_engine_batch.py` (AC-8 รวม `ExecuteModificationTests` เดิม) |
| AC-10, AC-11, AC-35 | `tests/test_confirm_destination.py`, `tests/test_run_target.py` |
| AC-12 (logic), AC-31 | `tests/test_run_lock.py` |
| AC-14, AC-15 | `tests/test_script_groups_block.py` |
| AC-16, AC-17, AC-18, AC-19, AC-36 | `tests/test_script_groups_backup.py` (AC-18 load ใน `test_script_groups_block.py`) |
| AC-20, AC-21, AC-22, AC-23 | `tests/test_busy_check.py`, `tests/test_running_banner.py` |
| AC-24 (logic) | `tests/test_running_banner.py` |
| AC-27, AC-28 | `tests/test_ctrl_enter.py` |
| AC-30 | ทั้งชุด (T15) |
| AC-38 | `tests/test_list_tables_stop.py` |
| Manual | AC-12 (สถานะปุ่ม), AC-13, AC-24 (การแสดงผล), AC-25, AC-26, AC-29, AC-37 |

---

## ตาราง AC → Task

| AC | Task | AC | Task | AC | Task |
|---|---|---|---|---|---|
| AC-1 | T5 | AC-14 | T3 | AC-27 | T2 |
| AC-2 | T5, T8 | AC-15 | T3 | AC-28 | T2 |
| AC-3 | T5 | AC-16 | T4 | AC-29 | T2 |
| AC-4 | T5 | AC-17 | T4 | AC-30 | T15 |
| AC-5 | T6 | AC-18 | T4 | AC-31 | T7 |
| AC-6 | T6 | AC-19 | T4 | AC-32 | T5 |
| AC-7 | T9 | AC-20 | T1, T12 | AC-33 | T5 |
| AC-8 | T9 | AC-21 | T1, T12 | AC-34 | T5 |
| AC-9 | T9, T10 | AC-22 | T1, T12 | AC-35 | T11 |
| AC-10 | T11 | AC-23 | T1, T12 | AC-36 | T4 |
| AC-11 | T11 | AC-24 | T12 | AC-37 | T13 |
| AC-12 | T7 | AC-25 | T12 | AC-38 | T13 |
| AC-13 | T7 | AC-26 | T14 | | |
