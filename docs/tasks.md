    - **Teardown follow-up (2026-11-13):** `root.update_idletasks()` หลังสร้าง GUI ระบาย callback `jobs_canvas.after_idle(update_jobs_scroll_state)` ก่อนเปิด/ทำลาย dialogs. `python -m unittest tests.test_r3_script_groups_io -v` → `Ran 145 tests in 5.019s`, `OK`; no Tcl diagnostic appeared.
  - **Follow-up QA (2026-11-13):** เพิ่ม behavioral `TestScriptGroupsDialogCallbackLifecycle` ใน `tests/test_r3_script_groups_io.py`; focused file ผ่าน `145 tests OK` (มี real Tk, ไม่มี skip). Full suite หลังทุก task ผ่าน `Ran 800 tests ... OK`. ระหว่างแสดง progress ของ full suite มี Tcl `invalid command name ... update_jobs_scroll_state`; ทั้งสอง UI test cases ผ่านเมื่อรันแยกโดยไม่มีข้อความนี้ จึงไม่ถือเป็น test failure.
  - **Teardown follow-up (2026-11-13):** `root.update_idletasks()` หลังสร้าง GUI ระบาย callback `jobs_canvas.after_idle(update_jobs_scroll_state)` ก่อนเปิด/ทำลาย dialogs. `python -m unittest tests.test_r3_script_groups_io -v` → `Ran 145 tests in 5.019s`, `OK`; không có Tcl diagnostic.
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

---
---

# Round 2 — Bugfix H3, M9, M3, H4

> อ้างอิง: `docs/spec.md` หัวข้อ "Round 2" (R2-AC-1 ถึง R2-AC-34), `docs/design.md` หัวข้อ "Round 2" (R2-D1 ถึง R2-D7)
> ไฟล์ source: `database_connect_gui.py` เลขบรรทัดเป็นค่าหลัง commit `2f4779b` (ก่อนเริ่ม Round 2)
> ทุก task: test เดิม (รวม Round 1) ต้องยังผ่าน (`python -m unittest discover -s tests -p "test_*.py"`)
> ลำดับ: M3 → H3 (ใช้ `_scan_sql` และ `_mark_oracle_slash_lines` จาก M3) → M9 → H4 → regression

- [x] R2-T1: M3 — บรรทัด `/` ของ Oracle เป็นตัวคั่น statement
  - ไฟล์: `database_connect_gui.py` — ฟังก์ชันใหม่ `_mark_oracle_slash_lines` (ใกล้ `_SQL_SLASH_MARK` 305), `_scan_sql` 319-392, `split_sql_statements` 410-432
  - ทำอะไร: ย้ายบล็อกเช็ค `_SQL_SLASH_MARK` (368-371) ไปไว้ก่อน `c.isspace()` (329); แยก `_SQL_SLASH_LINE_RE.sub(...)` (415) เป็น `_mark_oracle_slash_lines(sql)` แล้วให้ `split_sql_statements` เรียก; ข้อความ statement ที่คืนยังตัดจาก `sql` ต้นฉบับ (design R2-D2)
  - AC ที่ครอบคลุม: R2-AC-23, R2-AC-24, R2-AC-25, R2-AC-26

- [x] R2-T2: H3 — Auto WHERE หาตำแหน่งด้วย `_scan_sql` และครอบเงื่อนไขเดิม
  - ไฟล์: `database_connect_gui.py` — ใหม่ `_WhereLayout` + `_sql_where_layout` (module level หลัง `assess_sql` ~511), เขียนใหม่ `_append_where_conditions` 10877-10891 (signature เดิม, ยังเป็น staticmethod)
  - ทำอะไร: `_sql_where_layout` ทำตามอัลกอริทึม 7 ขั้นใน design R2-D3 (วงเล็บไม่ครบ / หลาย statement / ไม่ใช่ SELECT-UPDATE-DELETE / UNION-INTERSECT-EXCEPT-MINUS ที่ depth 0 / WHERE ซ้ำ / SELECT ไม่มี FROM / WHERE ว่าง → `ValueError` พร้อมเหตุผล); `_append_where_conditions` ครอบเงื่อนไขเดิมด้วยวงเล็บเสมอ แทรกก่อน clause ท้ายและ terminator, `conditions` ว่างคืน SQL เดิม; `_render_sql_template` และ flow Apply (12040-12046) ไม่ต้องแก้
  - AC ที่ครอบคลุม: R2-AC-1, R2-AC-2, R2-AC-3, R2-AC-4, R2-AC-5, R2-AC-6, R2-AC-7, R2-AC-8, R2-AC-9, R2-AC-10, R2-AC-11, R2-AC-12, R2-AC-13, R2-AC-14

- [x] R2-T3: M9 — `_reset_sql_in_lists` ใช้ `1=0` / ปฏิเสธ NOT IN ที่ว่าง
  - ไฟล์: `database_connect_gui.py` — `_reset_sql_in_lists` 11052-11066, ลบ `_remove_sql_condition` 11035-11050 (ไม่มีผู้เรียกอื่น)
  - ทำอะไร: list ที่ค่าหมด: ถ้าข้อความก่อน `(` ของ list เป็น `NOT IN` → `raise ValueError(...)` ตามข้อความใน design R2-D4; มิฉะนั้นแทน `sql[span]` ทั้งก้อนด้วย `1=0`; กรณีเหลือค่าคงเดิม
  - AC ที่ครอบคลุม: R2-AC-15, R2-AC-16, R2-AC-17, R2-AC-18, R2-AC-19, R2-AC-20, R2-AC-21

- [x] R2-T4: M9 — หน้าต่าง Reset Parameter แสดงเหตุผลเมื่อถูกปฏิเสธ
  - ไฟล์: `database_connect_gui.py` — `show_reset_parameter_dialog`: `refresh_sql_preview` 11297-11299, `reset_selected` 11416-11421
  - ทำอะไร: detected mode: preview จับ `ValueError` แล้วแสดง `source_sql + "\n\n-- " + error`; Apply จับ `ValueError` → `messagebox.showerror("Reset Error", ..., parent=dialog)` แล้ว return (Editor ไม่เปลี่ยน หน้าต่างไม่ปิด) และใช้ผลของ `build_detected_sql()` ครั้งเดียวกับที่จะเขียนลง Editor
  - AC ที่ครอบคลุม: R2-AC-22

- [x] R2-T5: H4 — `_current_table_data_tables` โหลดใหม่เมื่อ mtime เปลี่ยน + ปรับ fixture
  - ไฟล์: `database_connect_gui.py` — `_current_table_data_tables` 7358-7372; `tests/test_database_connect_gui_core.py` — `PrepareRunSqlTests.make_stub` 241-249 (qa-tester ปรับตาม design R2-D5)
  - ทำอะไร: `getmtime` ทุกครั้ง; ไฟล์หาย → `None`; mtime เท่า `last_table_data_mtime` และมีข้อมูล → ใช้ข้อมูลเดิมไม่เปิดไฟล์; mtime ต่าง → อ่านใหม่ สำเร็จแล้วอัปเดต `loaded_table_data` + `last_table_data_mtime` อ่านไม่ได้/ไม่ใช่ dict → `None` โดยไม่แตะค่าเดิม (ใช้ `!=` เทียบ mtime, `getattr` สำหรับ `last_table_data_mtime`); fixture เดิมต้องปรับใน task นี้เพราะ `test_fills_variables_and_keeps_job_text` จะล้มทันที
  - AC ที่ครอบคลุม: R2-AC-27, R2-AC-29, R2-AC-30 (ส่วน `None`), R2-AC-31 (ส่วน `None`)

- [x] R2-T6: H4 — log เวลาข้อมูล และไม่รันเมื่อ table data ใช้ไม่ได้
  - ไฟล์: `database_connect_gui.py` — ฟังก์ชันใหม่ `table_data_source_text` (module level ส่วน table variables ~517), `_prepare_run_sql` 7310-7356, `export_jobs_to_excel` (`export_tables` ~9773)
  - ทำอะไร: `_prepare_run_sql` เขียน `table_data_source_text(self.loaded_table_data, self.last_table_data_mtime)` ลง `results_text` ครั้งเดียวต่อการเรียกเมื่อได้ tables (อ่านเป็น attribute ไม่เรียกเมธอดใหม่บน stub); ได้ `None` → problem "table data file is missing or cannot be read ... — try again" ต่อ job แล้วคืน `None` ผ่าน `showerror` เดิม; Export เขียนบรรทัดเดียวกันเมื่อ `export_tables` ไม่ใช่ `None`
  - AC ที่ครอบคลุม: R2-AC-28, R2-AC-30, R2-AC-31, R2-AC-32, R2-AC-33

- [x] R2-T7: Regression ทั้งชุด Round 2
  - ไฟล์: — (qa-tester รันอย่างเดียว)
  - ทำอะไร: รัน `python -m unittest discover -s tests -p "test_*.py"` (test เดิม + Round 1 + Round 2) และรวบรวม checklist Manual/GUI ของ Round 2 (R2-AC-13 ส่วน popup, R2-AC-22, R2-AC-33) ให้หัวหน้า
  - AC ที่ครอบคลุม: R2-AC-34

- [x] R2-T-fix: M9 — แก้บั๊กจากการตรวจ Reset Parameter (ผู้ใช้อนุมัติขยาย M9 ไปครอบ tracked mode)
  - ไฟล์: `database_connect_gui.py` — `_has_negated_in_before` / `_reset_sql_in_lists`, ใหม่ `_where_main_command` (หลัง `_sql_where_layout`), `_append_where_conditions`, ใหม่ `_reset_parameter_value`, `reset_single_parameter`, `show_reset_parameter_dialog` (`build_reset_values`, เงื่อนไขปิดหน้าต่างใน `reset_selected`); `tests/test_r2_reset_parameter.py`
  - ทำอะไร:
    - Bug 4 (detected mode): ถือว่า list ถูก negate เฉพาะ `col NOT IN (`, `NOT col IN (` หรือวงเล็บที่ครอบ predicate นี้ถูกนำหน้าด้วย `NOT` / `NOT EXISTS` / `NOT IN` ส่วน NOT ของ predicate อื่น (`IS NOT NULL`, `NOT EXISTS (...)` ที่ปิดไปแล้ว, `x NOT IN ('9')` ก่อนหน้า) ไม่นับ → IN ธรรมดาได้ `1=0` ตาม R2-Q-4
    - Bug 3 (tracked mode, ผู้ใช้อนุมัติ): Reset จนคอลัมน์ Auto WHERE ไม่เหลือค่าใน UPDATE / DELETE (หรือ statement ที่บอกประเภทไม่ได้) → เก็บ entry ว่างไว้ใน `_excel_parameter_values` และ `_append_where_conditions` render เป็น `1=0` (ไม่มี WHERE เดิม → `WHERE 1=0`) statement จึงไม่กระทบแถวใด; SELECT คงพฤติกรรมเดิม (ทิ้งเงื่อนไข) ; Run/Export ที่มีค่าจริงไม่เปลี่ยน
    - Bug 5 (QA รอบ 1): `_detect_sql_in_lists` เปลี่ยนจาก regex เป็น token ของ `_scan_sql` → `IN (` ใน comment / string literal ไม่ถูกตรวจเป็น list และ comment ระหว่างคอลัมน์กับ `IN` ถูกข้าม (คอลัมน์ถูกต้อง, `1=0` แทนทั้ง predicate)
  - AC ที่ครอบคลุม: R2-AC-15 ถึง R2-AC-21 (ทบทวน), R2-US-2 ใน tracked mode
  - QA รอบ 2 (`tests/test_r2_reset_parameter_qa2.py::WideningBugTests`, 3 test / 4 subTest ล้ม, มีมาตั้งแต่ก่อน fix แต่ไม่ได้อยู่ใน known limit): reset ใน detected mode ทำให้ DELETE กระทบแถวมากกว่าเดิม
    - Bug 6: มี operator นำหน้าคอลัมน์ (`1 - n IN (5)` → `1 - 1=0` → 0 แถว กลายเป็นทุกแถว)
    - Bug 7: comment ก่อน SELECT ใน subquery (`IN (-- c\n SELECT ... ORDER BY flag, acc_no)`) ไม่ถูกข้าม → ตัด token แล้วได้ `IN (acc_no)` (1 → ทุกแถว)
    - Bug 8: comma ใน comment ภายในวงเล็บค่า ทำให้ `_split_sql_values` แยก comment เป็น token → ตัด token แล้วข้อความใน comment หลุดออกมาเป็น SQL (2 → 4 แถว)
  - QA รอบ 3: ผ่าน (`tests/test_r2_reset_parameter_qa3.py`, 18 test; ทั้งชุด 586 test OK) Bug 6/7/8 แก้แล้ว รูปแบบ SQL ทั่วไป (WHERE/AND/OR/ON/CASE WHEN, `t."COL"`, หลายบรรทัด, comment ท้ายบรรทัด, ค่าติดลบ, `DATE '...'`) ยังตรวจพบ
  - Known limits (exotic ให้ผู้ใช้ตัดสิน, pin ไว้ใน `KnownLimitRound3Tests`):
    - ตรวจไม่พบ (ไม่อันตราย แค่ใช้ Reset ไม่ได้): ค่าที่เป็น function เช่น `TO_DATE(...)` (เดิมก็ไม่พบ); `START WITH col IN (...)`, PL/SQL `IF v IN (...)`, select-list `SELECT col IN (...)` (regex เดิมเคยพบ); comment อยู่กลางค่าเดียว เช่น `DATE /* c */ '...'`
    - negation ของ list **ระดับบนสุด** (ไม่อยู่ในวงเล็บ) ที่มาจากสิ่งที่ตามหลังหรือ CASE (มีมาก่อน fix): `n IN (1) IS NOT TRUE`, `n IN (1) = 0`, `CASE WHEN n IN (1) THEN 0 ELSE 1 END = 1` → ล้างค่าจนเป็น `1=0` แล้วกระทบแถวมากขึ้น
    - ลบค่าบางส่วนออกจาก `NOT IN (...)` ระดับบนสุด ทำให้ได้แถวมากขึ้นตามที่ผู้ใช้เลือกเอง (ตั้งใจ ไม่ใช่บั๊ก)
  - ผู้ใช้อนุมัติ: เปลี่ยนข้อความหัว Reset dialog เป็น "ถ้าเอาออกครบทุกค่า: parameter กลับเป็น placeholder, เงื่อนไข IN ใน UPDATE/DELETE จะกลายเป็น 1=0 (ไม่กระทบแถวใด)" และคงพฤติกรรมเดิมของ `reset_selected` ที่ปิดหน้าต่างเองเมื่อไม่เหลือค่า
  - Review รอบ 1 (🔴 1, 🟠 2): แก้แล้ว รอ QA
    - Detected mode: `_has_negated_in_before` ถูกแทนด้วย `_in_list_reset_refusal` (whitelist) — list ที่อยู่ในวงเล็บ/subquery จะ Reset ได้ (บางส่วนหรือทั้งหมด) เฉพาะเมื่อทุกชั้นที่ครอบ "positive" ได้แน่นอน นอกนั้น `ValueError` ที่บอกเหตุผลจริง ปิด `NOT col IN (subquery)`, `<> ALL` / `= ANY` / `SOME`, `MINUS` / `EXCEPT` / `INTERSECT` ก่อน list, LEFT/RIGHT/FULL JOIN ON (ทุกระดับ), scalar subquery ที่ถูกเทียบ (`(SELECT COUNT(*) ...) = 0`), subquery ที่มี GROUP BY / HAVING / aggregate / ROWNUM / LIMIT / FETCH, `1 - (n IN (1))`, `COALESCE(NULL, n IN (1)) = 0`, `(n IN (1)) = 0`, `NOT COALESCE(...)` (known limit เดิมใน qa / qa3 เปลี่ยนเป็นคาด `ValueError`)
    - ข้อความหัว dialog / README / footer ของ detected mode แก้ให้ตรงพฤติกรรม: "ถ้าเอาออกครบทุกค่า: parameter กลับเป็นค่าเดิมใน template; Auto WHERE / IN-list ที่ตรวจพบใน UPDATE/DELETE จะกลายเป็น 1=0 (ไม่กระทบแถวใด)" (ไม่เปลี่ยนพฤติกรรม tracked mode)
    - ผลข้างเคียง: กฎใช้กับทุก statement รวม SELECT ด้วย — list ใน inline view / select-list subquery / NOT (...) จะ Reset ไม่ได้ (ก่อนหน้านี้ Reset บางส่วนได้)
  - QA หลัง Review รอบ 1 (`tests/test_r2_reset_nested_whitelist.py`, 15 test; ทั้งชุด 608 test, ล้ม 3 test / 10 subTest เฉพาะ `WideningHoleTests`): whitelist ปิด NOT / NOT EXISTS / NOT IN / ALL-ANY / MINUS-EXCEPT / outer ON / scalar / aggregate ได้ตาม generated invariant (~350 SQL) แต่ยังมี 3 ทางที่ Reset ทำให้กระทบแถวมากขึ้น
    - **บั๊ก 9: CASE WHEN ที่ครอบ list ซ้อน ไม่ถูกปฏิเสธ**
      - Test: tests/test_r2_reset_nested_whitelist.py::WideningHoleTests::test_case_when_nested_list_never_widens
      - คาดหวัง: `ValueError` (whitelist ระบุว่า "no CASE/THEN")
      - ได้จริง: `DELETE FROM acct WHERE CASE WHEN EXISTS (SELECT 1 FROM lkp WHERE code = grp AND seg IN ('CORP','RETAIL')) OR 1 = 2 THEN 0 ELSE 1 END = 1` → `... AND 1=0) OR ...` ลบ 0 → 4 แถว (ทั้งตาราง); `CASE WHEN (n IN (1, 0)) OR ...` 2 → 4; `flag = CASE WHEN EXISTS (...) AND 1 = 1 THEN 'Z' ELSE 'N' END` 1 → 3
      - สาเหตุ: `WHEN` อยู่ใน `_RESET_POSITIVE_LEADS` และ `OR`/`AND` เป็น positive follow จึงไม่เคยเจอ `THEN`; `_clause_before` มองข้าม CASE แล้วได้ WHERE
      - ขั้นตอนทำซ้ำ: `_reset_sql_in_lists(sql, _detect_sql_in_lists(sql), {0: ทุกค่า})` แล้วรันบน SQLite
      - AC ที่เกี่ยวข้อง: R2-US-2, R2-AC-15 ถึง R2-AC-21 (review 🟠)
    - **บั๊ก 10: list ใน INNER JOIN ON ที่ถูกครอบด้วย RIGHT / FULL JOIN ทีหลัง (anti-join)**
      - Test: tests/test_r2_reset_nested_whitelist.py::WideningHoleTests::test_inner_join_on_under_later_right_or_full_join_never_widens
      - คาดหวัง: `ValueError` (ผลของ inner join นี้เป็นฝั่งที่ถูกเติม NULL ของ RIGHT/FULL JOIN ที่ตามมา)
      - ได้จริง: `DELETE FROM acct WHERE acc_no IN (SELECT a.acc_no FROM lkp b JOIN acct x ON x.grp = b.code AND b.seg IN ('CORP','RETAIL') RIGHT JOIN acct a ON a.acc_no = x.acc_no WHERE x.acc_no IS NULL)` → `1=0` ลบ 0 → 4 แถว (เหมือนกันกับ `RIGHT OUTER` / `FULL`)
      - สาเหตุ: `_is_outer_join_on` ดูแค่ JOIN ของ ON นั้น ไม่ดู JOIN ที่ตามมาใน FROM เดียวกัน
      - AC ที่เกี่ยวข้อง: R2-US-2 (review 🟠 "LEFT/RIGHT/FULL JOIN ON ทุกระดับ")
    - **บั๊ก 11: list ระดับบนสุดหลัง EXCEPT / MINUS (INSERT ... SELECT, SELECT)**
      - Test: tests/test_r2_reset_nested_whitelist.py::WideningHoleTests::test_top_level_set_difference_never_widens
      - คาดหวัง: `ValueError` (กฎ MINUS/EXCEPT ก่อน list ใช้กับ list ซ้อนเท่านั้น)
      - ได้จริง: `INSERT INTO tgt SELECT acc_no FROM acct EXCEPT SELECT acc_no FROM acct WHERE status IN ('A','B')` → `WHERE 1=0` insert 1 → 4 แถว; แบบ `MINUS` (Oracle) ก็ไม่ raise
      - สาเหตุ: list ไม่มีวงเล็บครอบ → `_in_list_reset_refusal` เช็กเฉพาะ outer ON และ NOT ที่ถูกล้าง ไม่เรียก `_subquery_body_refusal` ที่ระดับ statement
      - AC ที่เกี่ยวข้อง: R2-US-2 (review 🟠 MINUS realistic ใน OFSAA)
  - แก้บั๊ก 9–11 แล้ว รอ QA (ทั้งชุด 620 test OK)
    - บั๊ก 9: `_inside_case` (ไล่ย้อนในระดับวงเล็บเดียวกัน นับ CASE/END จนถึง clause word หรือ `(` ที่ครอบ) — list ที่อยู่ใน CASE ที่ยังไม่ปิด ถูกปฏิเสธทุกระดับ (ระดับบนสุด, predicate ของ list ซ้อน, ทุกวงเล็บที่ครอบ) known limit เดิม `CASE WHEN acc_no IN (...) THEN 0 ELSE 1 END = 1` ใน DELETE จึงเปลี่ยนเป็นคาด `ValueError`
    - บั๊ก 10: `_is_outer_join_on` — ON ของ inner JOIN ถูกปฏิเสธด้วยถ้า FROM ระดับเดียวกันมี LEFT/RIGHT/FULL/OUTER JOIN ใด ๆ (`_from_has_outer_join`, ทั้งก่อนและหลัง)
    - บั๊ก 11: `_statement_level_refusal` ใช้กับทุก list (บนสุดและซ้อน, ดูที่ระดับ depth 0): ปฏิเสธเมื่อ branch ของ list อยู่หลัง `MINUS`/`EXCEPT` หรือ branch นั้นมี `HAVING` หลัง list (`INSERT ... WHERE c IN (...) GROUP BY ... HAVING COUNT(*) = 1` ขยายจาก 2 เป็น 3 แถว) — GROUP BY ที่ไม่มี HAVING, aggregate และ row limit ที่ระดับ statement ไม่ทำให้จำนวนแถวเพิ่ม จึงไม่ปฏิเสธ
    - ข้อความ: scalar subquery ที่ถูกเทียบ → "inside a compared scalar subquery (...)" (เดิม `0 = (SELECT ...)` ได้ "not in a WHERE condition"); หัว dialog / footer detected mode / README ไม่สัญญา "ไม่กระทบแถวใด" แล้ว: "IN-list ที่เอาออกครบจะกลายเป็น 1=0; ถ้า Reset แล้วอาจกระทบแถวมากขึ้นใน UPDATE/DELETE จะ Reset ไม่ได้"
  - **ผู้ใช้อนุมัติ (เปลี่ยน scope): SELECT ล้วนกลับไปใช้กฎก่อนมี whitelist**
    - SELECT ล้วน = `_where_main_command` ได้ `SELECT` (รวม `WITH ... SELECT`), มี statement เดียว (`;` ท้ายได้), และไม่มีคำ INSERT/UPDATE/DELETE/MERGE/CREATE/INTO/TRUNCATE/DROP/ALTER ที่ใดเลย (`_is_pure_select`) — INSERT ... SELECT, MERGE, CREATE TABLE AS, SELECT INTO, `SELECT ... FOR UPDATE`, หลาย statement และ statement ที่บอกประเภทไม่ได้ ใช้ whitelist (fail safe)
    - SELECT ล้วน: ไม่ใช้ whitelist ซ้อน / CASE / outer JOIN ON / set operator ในวงเล็บ → inline view, CTE, select-list subquery, `NOT (...)`, row-value IN, INTERSECT/MINUS ใน subquery, LEFT JOIN ON Reset ได้อีก; ยังปฏิเสธการเอาค่าออกครบจาก `col NOT IN (`, `NOT col IN (` และ list ที่อยู่ใต้ `NOT (...)` / `NOT EXISTS` / `NOT IN (subquery)` / `NOT col IN (subquery)` (ข้อความมี "every row")
    - กฎระดับ statement (หลัง MINUS/EXCEPT, ก่อน HAVING) ใช้กับ SELECT ล้วนด้วย เพราะ `WideningHoleTests::test_top_level_set_difference_never_widens` คาดให้ `SELECT ... EXCEPT SELECT ... WHERE status IN (...)` ไม่ขยาย
    - test ที่ pin "now refused" ของ SELECT ปรับตาม (`test_now_refused_forms` เหลือเฉพาะ statement ที่เขียน, `GeneratedNestedInvariantTests` ตรวจเฉพาะ wrapper ที่ไม่ใช่ SELECT) และเพิ่ม `PureSelectRevertTests`, `TopLevelHavingTests`, `InnerJoinWithOuterJoinTests`
  - QA หลังแก้บั๊ก 9–11 + scope SELECT: ผ่าน (`tests/test_r2_reset_nested_whitelist.py` 44 test; ทั้งชุด 637 test OK) ไม่มีปัญหาระดับ (A)
    - เพิ่ม `ExtendedWriteInvariantTests` (150 SQL บน SQLite: parenthesised join ที่มี outer join ข้างใน/นอก, UPDATE ... FROM, CASE ซ้อนใน function, CASE ... END ที่ปิดแล้วก่อน list ยัง Reset ได้), `NonSqliteWriteFormsTests` (data-modifying CTE, `SELECT ... FOR UPDATE`, PL/SQL ที่มี DELETE, MERGE), `PureSelectRoundTwoTests`, `RealisticWriteUsabilityTests`, `DialogRoundTwoTests` (เหตุผล CASE / HAVING / EXCEPT / RIGHT JOIN ใน dialog, ข้อความหัว/footer/README ใหม่)
    - Known limit (B, มีมาก่อน fix ให้ผู้ใช้ตัดสิน, pin ใน `test_known_limit_plsql_control_flow_negation`): list ระดับบนสุดที่ผลไปคุม control flow ของ PL/SQL (`SELECT COUNT(*) INTO v ... WHERE c IN (...); IF v = 0 THEN DELETE ...` หรือ `IF x = 1 AND v IN (...) THEN NULL; ELSE DELETE ...`) ล้างค่าจนเป็น 1=0 แล้ว block ลบแถวที่เดิมไม่ลบ — แก้แล้วใน R2-T-fix2

- [x] R2-T-fix2: M9 — Reset Parameter: ความปลอดภัยของ PL/SQL control flow, รองรับ inline view / CTE ของ T2T, ปรับข้อความ (ผู้ใช้อนุมัติ 3 ข้อ)
  - ไฟล์: `database_connect_gui.py` (กฎปฏิเสธของ `_in_list_reset_refusal`, หัว dialog / footer detected mode), `README.md`, `tests/test_r2_reset_nested_whitelist.py`, `tests/test_r2_reset_t2t_plsql.py`
  - ทำอะไร:
    1. PL/SQL block (ขึ้นต้น DECLARE/BEGIN หรือมี BEGIN ... END ระดับบนสุด): Reset ได้เฉพาะ list ใน WHERE/ON ของ DELETE/UPDATE/INSERT ... SELECT/MERGE ภายใน block และต้องผ่าน whitelist เดิม; ปฏิเสธ `SELECT ... INTO`, cursor / `FOR r IN (...)`, เงื่อนไข IF/ELSIF/WHILE/EXIT WHEN/CASE และ statement ที่ระบุไม่ได้
    2. Statement ที่เขียน: อนุญาต list ใน inline view ของ INNER/plain JOIN หรือ comma FROM (FROM ระดับนั้นไม่มี outer join, body ผ่านกฎ) รวม join ซ้อนในวงเล็บ; อนุญาต list ใน CTE body เมื่อทุกการอ้างถึง CTE อยู่ในตำแหน่ง positive (FROM / INNER JOIN, ไม่มี outer join, ไม่อยู่ใต้ NOT EXISTS / NOT IN / ALL / ANY / scalar / CASE / หลัง MINUS-EXCEPT) และไม่ถูกอ้างจาก CTE อื่น / ไม่ recursive
    3. ข้อความ: MERGE ON มีข้อความของตัวเอง; หัว dialog / footer / README พูดถึง statement ที่เขียน (UPDATE/DELETE/INSERT/MERGE)
  - ผล QA: focused file ผ่าน 9 tests; full suite `python -m unittest discover -s tests -p "test_*.py"` — `Ran 799 tests ... OK` (รันโดย orchestrator)
  - Review follow-up: inline-view/join และ positive-reference CTE cases now assert reset output contains `1=0` and at least one executed invariant check; `python -m unittest tests.test_r2_reset_t2t_plsql -v` — `Ran 9 tests ... OK` (full suite deferred to orchestrator)
  - Latest full-suite follow-up (orchestrator, after positive inline-view/CTE assertion follow-up): `python -m unittest discover -s tests -p "test_*.py"` — `Ran 800 tests in 8.458s`, `OK`; no Tcl diagnostic.

## ตาราง R2-AC → Task

| R2-AC | Task | R2-AC | Task | R2-AC | Task |
|---|---|---|---|---|---|
| R2-AC-1 | R2-T2 | R2-AC-13 | R2-T2 | R2-AC-25 | R2-T1 |
| R2-AC-2 | R2-T2 | R2-AC-14 | R2-T2 | R2-AC-26 | R2-T1 |
| R2-AC-3 | R2-T2 | R2-AC-15 | R2-T3 | R2-AC-27 | R2-T5 |
| R2-AC-4 | R2-T2 | R2-AC-16 | R2-T3 | R2-AC-28 | R2-T6 |
| R2-AC-5 | R2-T2 | R2-AC-17 | R2-T3 | R2-AC-29 | R2-T5 |
| R2-AC-6 | R2-T2 | R2-AC-18 | R2-T3 | R2-AC-30 | R2-T5, R2-T6 |
| R2-AC-7 | R2-T2 | R2-AC-19 | R2-T3 | R2-AC-31 | R2-T5, R2-T6 |
| R2-AC-8 | R2-T2 | R2-AC-20 | R2-T3 | R2-AC-32 | R2-T6 |
| R2-AC-9 | R2-T2 | R2-AC-21 | R2-T3 | R2-AC-33 | R2-T6 |
| R2-AC-10 | R2-T2 | R2-AC-22 | R2-T4 | R2-AC-34 | R2-T7 |
| R2-AC-11 | R2-T2 | R2-AC-23 | R2-T1 | | |
| R2-AC-12 | R2-T2 | R2-AC-24 | R2-T1 | | |

---
---

# Round 3 — Feature: ปุ่ม Import / Export Groups ที่ Sidebar

> อ้างอิง: `docs/spec.md` หัวข้อ "Round 3" (R3-AC-1 ถึง R3-AC-18), `docs/design.md` หัวข้อ "Round 3" (R3-D1 ถึง R3-D9)
> การตัดสินใจ: R3-A1 ถึง A4 ยืนยัน; R3-Q-2 = ปุ่มอยู่**แถวใหม่**ใต้แถว Preset Save/Load; R3-Q-3 = คงพฤติกรรมเดิม
> ไฟล์ source: `database_connect_gui.py` เลขบรรทัดอ้าง working tree บน branch `ui/remove-duplicate-buttons` ให้ค้นด้วยชื่อฟังก์ชัน
> ทุก task: test เดิมทั้งหมดต้องยังผ่าน (`python -m unittest discover -s tests -p "test_*.py"`); test ใหม่ของ Round 3 อยู่ใน `tests/test_r3_script_groups_io.py` (qa-tester)
> ลำดับ: pure helper → ย้าย Export เป็น method → ย้าย Import + refresh callback → sidebar → regression

- [x] R3-T1: Pure helper ของ Script Groups import/export (ไม่ใช้ Tk)
  - ไฟล์: `database_connect_gui.py` — module level ต่อจาก `query_template_label` (~830)
  - ทำอะไร: เพิ่ม `SCRIPT_GROUPS_FILE_TYPE`, `SCRIPT_GROUPS_FILE_VERSION`, `_script_groups_now`, `build_script_groups_export`, `script_groups_export_filename`, `parse_script_groups_import`, `script_group_name_clashes`, `merge_imported_script_groups` ตาม signature และกติกาใน design R3-D2 (คัดลอกตรรกะจาก nested `export_groups` / `import_groups` เดิมทุกขั้น); ยังไม่แก้ dialog ใน task นี้ (โค้ดเดิมทำงานเหมือนเดิม)
  - AC ที่ครอบคลุม: R3-AC-1, R3-AC-2, R3-AC-3, R3-AC-4, R3-AC-5, R3-AC-6, R3-AC-7

- [x] R3-T2: Export เป็น instance method ที่ใช้ร่วม + dialog delegate
  - ไฟล์: `database_connect_gui.py` — ใหม่ `_ensure_script_groups_loaded`, `export_script_groups` (ส่วน Script Groups ต่อจาก `_backup_script_groups_once` ~4224); `show_script_groups_dialog` บรรทัด 4493-4494 และ closure `export_groups` (4835-4897)
  - ทำอะไร: `export_script_groups(parent, groups, profile, selected=None)` ทำ flow เดิมทุกขั้นโดยใช้ helper จาก R3-T1 และ `parent` ที่รับมาในทุก messagebox / filedialog (design R3-D3); `show_script_groups_dialog` ใช้ `_ensure_script_groups_loaded()`; closure `export_groups` เหลือ `self.export_script_groups(dialog, state["groups"], state["profile"], current_group())`
  - AC ที่ครอบคลุม: R3-AC-1 (ใช้จริงใน flow), R3-AC-10 (ส่วน Export), R3-AC-14 (ส่วน `_ensure_script_groups_loaded`), R3-AC-17 (Export ใน dialog)

- [x] R3-T3: Import เป็น instance method ที่ใช้ร่วม + callback refresh ของ dialog
  - ไฟล์: `database_connect_gui.py` — ใหม่ `import_script_groups`, `_refresh_script_groups_window`; `show_script_groups_dialog`: closure `import_groups` (4899-4996), ลงทะเบียน `self._script_groups_refresh` ก่อน `refresh_groups()` ตัวสุดท้าย (~5046) และ bind `<Destroy>`
  - ทำอะไร: `import_script_groups(parent)` ทำ flow เดิม 10 ขั้นตาม design R3-D3 (เรียก `_ensure_script_groups_loaded` ก่อน, บันทึกผ่าน `save_script_groups()` ครั้งเดียว, แล้ว `_refresh_script_groups_window(last)`, แล้ว log); closure `import_groups` เหลือ `self.import_script_groups(dialog)`; ลงทะเบียน/ล้าง callback ตาม design R3-D4 (เช็ก `event.widget is dialog` และ identity ของ callback); `_refresh_script_groups_window` เช็ก `winfo_exists()` และล้าง callback ถ้าหน้าต่างไม่อยู่
  - AC ที่ครอบคลุม: R3-AC-10 (ส่วน Import), R3-AC-11, R3-AC-12, R3-AC-13, R3-AC-14 (ส่วน Import), R3-AC-15 (logic), R3-AC-17 (Import ใน dialog)

- [x] R3-T4: ปุ่ม Import Groups / Export Groups แถวใหม่ใน Sidebar
  - ไฟล์: `database_connect_gui.py` — ใหม่ `sidebar_export_script_groups`, `sidebar_import_script_groups` (ต่อจากเมธอดของ R3-T3); UI build ส่วน Presets (2591-2601)
  - ทำอะไร: handler ตาม design R3-D3 (Export: ensure loaded → กลุ่มทั้งหมดของ `profile_combo.get()` → `export_script_groups(self.root, groups, profile)` ไม่ส่ง `selected`; Import: `import_script_groups(self.root)`); เพิ่ม Frame `groups_io` ใต้ `presets_inner` ใน `presets` มีปุ่ม `_ghost(..., "⇧  Import Groups", ...)` และ `_ghost(..., "⇩  Export Groups", ...)` `bg=UI["surface"]` เรียงซ้ายไปขวา (design R3-D5) ไม่แตะแถว Preset Save/Load นอกจากปรับ pady ได้ตามความเหมาะสม
  - AC ที่ครอบคลุม: R3-AC-8, R3-AC-9, R3-AC-10, R3-AC-11, R3-AC-12, R3-AC-13, R3-AC-14, R3-AC-15, R3-AC-16

- [x] R3-T5: Regression ทั้งชุด Round 3 + checklist Manual/GUI (ส่วน automated ผ่าน; ส่วน Manual/GUI ด้านล่าง **รอผู้ใช้ทดสอบ**)
  - ไฟล์: — (qa-tester รันอย่างเดียว นอกจาก `tests/test_r3_script_groups_io.py` ที่เขียนใน T1-T4)
  - ทำอะไร: รัน `python -m unittest discover -s tests -p "test_*.py"` ทั้งชุด และรวบรวม checklist Manual/GUI ให้หัวหน้า:
    - R3-AC-16: เปิดแอป ดู sidebar ด้านล่าง → แถว `Preset 💾 Save 📂 Load` และแถวใหม่ `⇧ Import Groups  ⇩ Export Groups` สไตล์ ghost เดียวกัน ไม่ล้น/ถูกตัดที่ความกว้าง sidebar ปกติ
    - R3-AC-15: เปิดหน้าต่าง Script Groups ค้างไว้ → Import จาก sidebar → รายการในหน้าต่าง refresh และเลือกกลุ่มสุดท้ายที่ import; ปิดหน้าต่างแล้ว Import อีกครั้ง → ไม่มี error
    - R3-AC-17: ปุ่ม Import / Export ในหัวหน้าต่าง Script Groups ทำงานเหมือนเดิม (ถาม all / only selected เมื่อมี > 1 กลุ่ม, messagebox อยู่บน dialog)
  - AC ที่ครอบคลุม: R3-AC-15 (Manual), R3-AC-16, R3-AC-17 (Manual), R3-AC-18
  - ผล automated (qa-tester, 2026-11-13): `python -m unittest discover -s tests -p "test_*.py"` → `Ran 781 tests ... OK` (R3-AC-18 ผ่าน); `tests/test_r3_script_groups_io.py` 144 test (R3-T4 เพิ่ม 46 รวม build check หน้าต่างหลักแบบ withdrawn ที่ APP_DIR ชี้ tempdir)
  - **Follow-up QA (2026-11-13):** เพิ่ม behavioral `TestScriptGroupsDialogCallbackLifecycle` ใน `tests/test_r3_script_groups_io.py`; focused file ผ่าน `145 tests OK` (มี real Tk, ไม่มี skip). Full suite หลังทุก task ผ่าน `Ran 800 tests ... OK`. ระหว่างแสดง progress ของ full suite มี Tcl `invalid command name ... update_jobs_scroll_state`; ทั้งสอง UI test cases ผ่านเมื่อรันแยกโดยไม่มีข้อความนี้ จึงไม่ถือเป็น test failure.
  - Latest full-suite result after `root.update_idletasks()` teardown cleanup (orchestrator): `python -m unittest discover -s tests -p "test_*.py"` — `Ran 800 tests in 8.458s`, `OK`; no Tcl diagnostic.
  - **Checklist Manual/GUI — รอผู้ใช้รัน** (แนะนำ: สำรอง `script_groups.json` ก่อน หรือใช้ Profile ทดสอบ; ทำเครื่องหมาย `[x]` เมื่อผ่าน)
    - R3-AC-16 หน้าตา sidebar
      - [ ] M1. เปิดแอป → ด้านล่าง sidebar แถวแรก `Preset  💾 Save  📂 Load` เหมือนเดิม และแถวที่สองใต้ลงมา `⇧  Import Groups  ⇩  Export Groups` (Import อยู่ซ้าย)
      - [ ] M2. ปุ่มแถวใหม่สไตล์ ghost เดียวกับ Save / Load (สี/ขนาด/hover) พื้นหลังสีเดียวกับแถบ Preset
      - [ ] M3. ที่ขนาดหน้าต่างเริ่มต้น (1200x900) และขนาดเล็กสุด (1100x680) ข้อความปุ่มไม่ถูกตัด/ไม่ล้นขอบ sidebar; รายการ Saved Jobs ยังเลื่อนดูได้ปกติ
    - Sidebar Export (R3-AC-8 / 9 / 10 ยืนยันบนจอจริง)
      - [ ] M4. เลือก Profile ที่มี ≥ 2 กลุ่ม → `⇩ Export Groups` → **ไม่มี**คำถาม all / only one → file dialog เด้งบนหน้าต่างหลัก ชื่อเริ่มต้น `script_groups_<Profile>_<YYYYmmdd_HHMMSS>.json` → Save → info "Exported ..." และ Results มีบรรทัด `📤 Exported N group(s), M script(s) → <path>`; เปิดไฟล์ดูมีแต่กลุ่มของ Profile นั้น
      - [ ] M5. เลือก Profile ที่ไม่มีกลุ่ม → `⇩ Export Groups` → info "This profile has no groups to export" ไม่มี file dialog
      - [ ] M6. Export แล้วกด Cancel ใน file dialog → ไม่มีไฟล์ ไม่มีบรรทัด log ไม่มี popup
    - Sidebar Import (R3-AC-11 / 12 / 13)
      - [ ] M7. ยังไม่เลือก Profile (ถ้าทำได้) → `⇧ Import Groups` → warning "Please select a profile first"
      - [ ] M8. Import ไฟล์จาก M4 กลับเข้า Profile เดิม → ถามชื่อซ้ำ: No → ได้กลุ่ม `ชื่อ (2)`; ทำซ้ำตอบ Yes → แทนที่ (ไม่มีชื่อซ้ำ); ทำซ้ำตอบ Cancel → ไม่มีอะไรเปลี่ยน; กรณี Yes/No Results มี `📥 Imported N group(s) from <path>`
      - [ ] M9. Import ไฟล์ที่ไม่ใช่ Script Groups (เช่น `saved_jobs.json` สำเนา หรือไฟล์ข้อความ) → error "Not a valid Script Groups file" กลุ่มไม่เปลี่ยน
    - R3-AC-15 refresh หน้าต่าง Script Groups + callback `<Destroy>`
      - [ ] M10. เปิดหน้าต่าง Script Groups ค้างไว้ → กด `⇧ Import Groups` ที่ sidebar → import สำเร็จ → รายการในหน้าต่าง Script Groups refresh ทันที และเลือก (highlight) กลุ่มสุดท้ายที่ import
      - [ ] M11. ในหน้าต่าง Script Groups ที่เปิดอยู่ ทำสิ่งที่ทำลาย/สร้าง widget ลูกใหม่ (เช่น เลือกกลุ่มอื่น, สลับกลุ่มไปมา, ลบ script ในกลุ่ม, rename กลุ่ม) แล้ว Import จาก sidebar อีกครั้ง → หน้าต่างยัง refresh ได้ (child widget destroy ต้อง**ไม่**ล้าง callback)
      - [ ] M12. ปิดหน้าต่าง Script Groups → Import จาก sidebar อีกครั้ง → import สำเร็จ ไม่มี error / traceback ในคอนโซล (callback ถูกล้างเมื่อ dialog ถูก destroy)
      - [ ] M13. เปิดหน้าต่าง Script Groups ใหม่อีกครั้ง → Import จาก sidebar → หน้าต่างใหม่ refresh และเลือกกลุ่มสุดท้าย (callback ของหน้าต่างใหม่ใช้งานได้ ไม่ถูกล้างโดยหน้าต่างเก่า)
    - R3-AC-17 ปุ่มในหัวหน้าต่าง Script Groups (regression)
      - [ ] M14. ในหน้าต่าง Script Groups เลือกกลุ่มหนึ่ง (Profile มี > 1 กลุ่ม) → `⇩ Export Groups` → ถาม "Export ALL N groups ... Yes = all / No = only '<กลุ่ม>'" popup อยู่บนหน้าต่าง Script Groups (ไม่หลบไปหลังหน้าต่างหลัก); No → ชื่อไฟล์ใช้ชื่อกลุ่ม ไฟล์มีกลุ่มเดียว; Yes → ทุกกลุ่ม
      - [ ] M15. `⇧ Import Groups` ในหัวหน้าต่าง → ทุก popup อยู่บนหน้าต่าง Script Groups; import สำเร็จแล้วรายการ refresh และเลือกกลุ่มสุดท้าย เหมือนก่อนแก้

## ตาราง R3-AC → Task

| R3-AC | Task | R3-AC | Task | R3-AC | Task |
|---|---|---|---|---|---|
| R3-AC-1 | R3-T1, R3-T2 | R3-AC-7 | R3-T1 | R3-AC-13 | R3-T3, R3-T4 |
| R3-AC-2 | R3-T1 | R3-AC-8 | R3-T4 | R3-AC-14 | R3-T2, R3-T3, R3-T4 |
| R3-AC-3 | R3-T1 | R3-AC-9 | R3-T4 | R3-AC-15 | R3-T3, R3-T4, R3-T5 |
| R3-AC-4 | R3-T1 | R3-AC-10 | R3-T2, R3-T3, R3-T4 | R3-AC-16 | R3-T4, R3-T5 |
| R3-AC-5 | R3-T1 | R3-AC-11 | R3-T3, R3-T4 | R3-AC-17 | R3-T2, R3-T3, R3-T5 |
| R3-AC-6 | R3-T1 | R3-AC-12 | R3-T3, R3-T4 | R3-AC-18 | R3-T5 |

---
---

# Round 4 — Profile mismatch guard และ Excel row limit

> อ้างอิง: `docs/spec.md` หัวข้อ Round 4 (R4-AC-1 ถึง R4-AC-9), `docs/design.md` หัวข้อ Round 4
> ขอบเขต: เฉพาะ guard ของ Run Job / Run All / Export / SQL Editor / Tables และการปฏิเสธ Export ที่มีแถวเกินขีดจำกัด Excel
> ทุก task ใช้ `unittest`; test ใหม่ไม่เปิด Tk จริงและไม่เชื่อมฐานข้อมูลจริง

- [x] R4-T1: ปฏิเสธงานเมื่อ Profile ที่เลือกไม่ตรงกับ connection snapshot
  - ไฟล์: `database_connect_gui.py` — helper ใหม่ `_block_if_profile_mismatch`; `run_job`, `run_selected_job`, `export_jobs_to_excel`, `execute_query`, `list_tables`; ตรวจ flow `_replace_engine` / `connect_database` เฉพาะส่วนที่สร้าง snapshot
  - ทำอะไร: เปรียบเทียบ Profile ที่เลือกกับ `_run_target.info.profile` ตาม R4-Q-1 (บล็อกเมื่อทั้งสองมีค่าและไม่ตรง); log ชื่อทั้งสอง Profile และแจ้งว่างานไม่ได้เริ่ม; ไม่ใช้ popup ไม่เปลี่ยน Profile/engine/target; เรียก guard หลัง busy guard และก่อน confirmation, file dialog, SQL/metadata worker; กรณีตรงกันคงการใช้ engine ของ `_run_target` และ Connect ใหม่เก็บ snapshot ของ Profile ใหม่
  - AC ที่ครอบคลุม: R4-AC-1, R4-AC-2, R4-AC-3, R4-AC-4, R4-AC-5

- [x] R4-T2: QA focused tests สำหรับ Profile mismatch
  - ไฟล์: `tests/test_r4_profile_mismatch.py`
  - ทำอะไร: ทดสอบ entry points ทั้งห้าเมื่อ mismatch (ไม่มี worker/SQL/file dialog/confirmation และมี log ถูกต้อง), เมื่อชื่อ Profile ตรงกัน, เมื่อเทียบไม่ได้ตาม R4-Q-1, engine/`_run_target` ไม่เปลี่ยนเมื่อถูกปฏิเสธ และ Connect Profile ใหม่แล้ว target ชี้ engine/Profile ใหม่; รันไฟล์ test นี้แยกหลัง R4-T1
  - AC ที่ครอบคลุม: R4-AC-1, R4-AC-2, R4-AC-3, R4-AC-4, R4-AC-5
  - ผล: `python -m unittest tests.test_r4_profile_mismatch -v` — `Ran 5 tests ... OK`

- [x] R4-T3: ปฏิเสธ Excel Job ที่เกิน row limit โดยไม่ตัดข้อมูล
  - ไฟล์: `database_connect_gui.py` — `export_jobs_to_excel.worker`; constant `EXCEL_MAX_DATA_ROWS` และ helper `_ensure_excel_row_limit` ตาม design R4-D3
  - ทำอะไร: ตรวจจำนวนข้อมูลก่อนเขียน sheet ผลลัพธ์; เมื่อมากกว่า 1,048,575 ให้ raise error ระบุ limit เพื่อใช้ exception handler ต่อ Job สร้าง sheet Failed; ห้าม slice DataFrame; คงการเขียนครบเมื่ออยู่ใน limit และให้ worker เดินต่อ Job ถัดไป
  - AC ที่ครอบคลุม: R4-AC-6, R4-AC-7, R4-AC-8

- [x] R4-T4: QA focused tests สำหรับ Excel row limit และการทำงานต่อ
  - ไฟล์: `tests/test_r4_excel_row_limit.py`
  - ทำอะไร: ใช้ DataFrame / writer stub ทดสอบกรณีเกิน limit ว่าไม่เขียนข้อมูลบางส่วนและนับ Failed พร้อม sheet Failed; ทดสอบ 1,048,575 แถวว่าเขียนครบโดยไม่ตัด; ทดสอบ Job เกิน limit ตามด้วย Job ที่ผ่านว่า Job หลังสำเร็จและยอด Success/Failed ตรง; รันไฟล์ test นี้แยกหลัง R4-T3
  - AC ที่ครอบคลุม: R4-AC-6, R4-AC-7, R4-AC-8
  - ผล: `python -m unittest tests.test_r4_excel_row_limit -v` — `Ran 3 tests ... OK`
  - Review follow-up (Round 4 warning): ปรับ FakeWorksheet ให้ติดตาม `max_row` และ cell writes ตามจำนวนแถวที่ DataFrame เขียน; ยืนยัน boundary 1,048,575 แถวยังคง export ครบ, SQL annotation ถูกละทั้งก้อนโดยไม่มี write เกิน 1,048,576 และมีคำเตือนใน Execution Logs; เพิ่มกรณี annotation เขียนได้; `python -m unittest tests.test_r4_excel_row_limit -v` — `Ran 4 tests ... OK`
  - Verification update (orchestrator): `python -m unittest tests.test_r4_excel_row_limit -v` — `Ran 4 tests ... OK`; `python -m unittest discover -s tests -p "test_*.py"` — `Ran 799 tests ... OK`

- [x] R4-T5: Regression ทั้งชุด Round 4
  - ไฟล์: — (QA รันอย่างเดียว)
  - ทำอะไร: รัน `python -m unittest discover -s tests -p "test_*.py"` หลัง R4-T1 ถึง R4-T4 ผ่าน; ยืนยัน test เดิมและ focused tests ใหม่ทั้งหมดผ่าน
  - AC ที่ครอบคลุม: R4-AC-9
  - ผลเดิม: `Ran 789 tests in 9.299s` — `OK`; รวม `tests/test_r4_profile_mismatch.py` และ `tests/test_r4_excel_row_limit.py`
  - Regression follow-up หลังแก้ Round 4 review warning: `Ran 790 tests in 10.578s` — `OK`; รันด้วย `python -m unittest discover -s tests -p "test_*.py"` รวม focused tests ใหม่ทั้งหมด

## ตาราง R4-AC → Task

| R4-AC | Task | R4-AC | Task | R4-AC | Task |
|---|---|---|---|---|---|
| R4-AC-1 | R4-T1, R4-T2 | R4-AC-4 | R4-T1, R4-T2 | R4-AC-7 | R4-T3, R4-T4 |
| R4-AC-2 | R4-T1, R4-T2 | R4-AC-5 | R4-T1, R4-T2 | R4-AC-8 | R4-T3, R4-T4 |
| R4-AC-3 | R4-T1, R4-T2 | R4-AC-6 | R4-T3, R4-T4 | R4-AC-9 | R4-T5 |

---

# Round 5 — Profile, Export, SQL parsing และ UI thread safety

> อ้างอิง: `docs/spec.md` หัวข้อ Round 5 (R5-AC-1 ถึง R5-AC-13), `docs/design.md` หัวข้อ Round 5
> ขอบเขต: เฉพาะ bug 12 รายการที่อนุมัติใน Round 5; source/test ที่ระบุเป็นงานของ developer/qa-tester
> ทุก task เริ่ม `[ ]`; test ใหม่ของแต่ละ bug ต้องอยู่ใน `tests/test_bugfix_<id ตัวพิมพ์เล็กและตัดขีดกลาง>.py`
> แต่ละ bug มี focused unittest ตามไฟล์ที่ระบุ; validation เต็มชุดหลังงาน Round 5: `python -m unittest discover -s tests -p "test_*.py"`
> Developer ทำทีละ task ตามลำดับและหยุดให้ QA รัน focused test ของ task นั้นก่อนเริ่ม task ถัดไป; หากไม่ผ่านให้แก้ task เดิมและให้ QA รันทดสอบซ้ำ

- [x] R5-T1: C-1 — Profile ที่เลือกกับ Job ต้องตรงกัน
  - [x] R5-T1: C-1 — Profile ที่เลือกกับ Job ต้องตรงกัน
  - ไฟล์: `database_connect_gui.py` — `save_profile_dialog.save`, `run_job`; `tests/test_bugfix_c1.py`
  - ทำอะไร: หลังบันทึกสำเร็จและเลือก Profile แล้วเรียก `update_jobs_list()`; ปฏิเสธ Job เมื่อ `job.get("profile")` ไม่ตรงกับ Profile ที่เลือก โดย log เหตุผลและ return ก่อน confirmation หรือ worker
  - ทดสอบ: ตรวจลำดับการเลือก Profile แล้ว refresh; กรณี mismatch ไม่มี confirmation/thread และมี log; กรณีตรงกันคง flow เดิม
  - AC ที่ครอบคลุม: R5-AC-1

- [x] R5-T2: H-3 — ผล save และ rollback ฝั่ง Profile
  - ไฟล์: `database_connect_gui.py` — `save_profiles`, `save_profile_dialog.save`, `new_profile_dialog.create`, `delete_profile`, `do_import`; `tests/test_bugfix_h3.py`
  - ทำอะไร: ให้ `save_profiles()` คืน bool; callers เก็บ snapshot และ rollback เมื่อบันทึกล้มเหลว โดยไม่แสดง success, refresh, สลับ Profile หรือ reload; ครอบคลุม import ทั้ง replace/merge และการคืนค่า widget `db_port`
  - ทดสอบ: ผลคืน True/False, rollback ของทั้งสี่ caller, ไม่มี success output เมื่อ fail
  - AC ที่ครอบคลุม: R5-AC-2 (Profile callers)

- [x] R5-T3: H-3 — ผล save และ rollback ฝั่ง Job / preset load
  - ไฟล์: `database_connect_gui.py` — `save_jobs`, `save_job_dialog.save`, `edit_job.save_changes`, `load_preset_dialog`; `tests/test_bugfix_h3.py`
  - ทำอะไร: ให้ `save_jobs()` คืน bool; snapshot/rollback รายการและ dict ที่แก้ in-place; เมื่อ write fail ห้าม success message/log, refresh หรือปิด dialog
  - ทดสอบ: ผลคืน True/False และ rollback/ไม่มี success behavior สำหรับ create, edit และ load preset
  - AC ที่ครอบคลุม: R5-AC-2 (Job callers)

- [x] R5-T4: C-2 — ตรวจ string cell เกิน Excel limit
  - [x] R5-T4: C-2 — ตรวจ string cell เกิน Excel limit
  - ไฟล์: `database_connect_gui.py` — เตรียมผลใน `export_jobs_to_excel` ก่อน `DataFrame.to_excel`; `tests/test_bugfix_c2.py`
  - ทำอะไร: ไม่ส่ง string ยาวเกิน 32,767 ตัวอักษรให้ writer; log warning พร้อมชื่อ Job และ column และนับ Job เป็น warning ไม่ใช่ success ปกติ
  - ทดสอบ: ค่า 32,768 ไม่ถูกเขียนและมี warning ที่ระบุ Job/column; ค่าไม่เกิน limit ยัง export ได้
  - AC ที่ครอบคลุม: R5-AC-3

- [x] R5-T5: C-3 — แปลง bytes ผ่าน DB formatter
  - ไฟล์: `database_connect_gui.py` — `clean_value` ใน Export worker; `tests/test_bugfix_c3.py`
  - ทำอะไร: สำหรับ `bytes` ใช้ `format_db_value(x)` โดยตรง ไม่ decode เป็น UTF-16LE/UTF-8; คงการจัดการชนิดอื่น
  - ทดสอบ: ตรวจการเรียก formatter และผล hex ที่ถูกส่งไป Excel
  - AC ที่ครอบคลุม: R5-AC-4

- [x] R5-T6: H-2 — หา First IN list จาก SQL token
  - ไฟล์: `database_connect_gui.py` — `_render_sql_template`, การหา `__FIRST_IN_LIST__`; `tests/test_bugfix_h2.py`
  - ทำอะไร: ใช้ `_scan_sql` หา span ของ IN list จริงรายการแรก ข้าม comment/string; เมื่อไม่พบให้ raise `ValueError` ที่ระบุว่าไม่พบ `IN (...)` ใน template
  - ทดสอบ: ไม่แก้ `IN (` ใน comment/string และแทน list จริง; ไม่มี list จริงเกิด error ชัดเจน
  - AC ที่ครอบคลุม: R5-AC-5

- [x] R5-T7: M-1 — ตรวจ placeholder จาก SQL token
  - [x] R5-T7: M-1 — ตรวจ placeholder จาก SQL token
  - ไฟล์: `database_connect_gui.py` — logic ตรวจ placeholder โดยใช้ `_scan_sql`; `tests/test_bugfix_m1.py`
  - ทำอะไร: ตรวจเฉพาะ placeholder จริง; ข้าม string/comment, `::` cast และ colon ในเวลา `HH24:MI:SS`
  - ทดสอบ: SQL เดียวมี placeholder จริงและข้อความลวงทุกกรณี; ตรวจพบเฉพาะ token จริง
  - AC ที่ครอบคลุม: R5-AC-6

- [x] R5-T8: H-1 — ส่ง connection snapshot ให้ Tables worker
  - ไฟล์: `database_connect_gui.py` — `list_tables`, worker, SQL Server schema discovery; `tests/test_bugfix_h1.py`
  - ทำอะไร: อ่าน credentials/ค่าการเชื่อมต่อที่ worker ต้องใช้จาก Tk Variables บน main thread ก่อนเริ่ม thread และส่ง credentials เป็น tuple snapshot; worker ไม่อ่าน widget; dispose `temp_engine` ใน `finally` รวมกรณี schema inspection ล้มเหลว; SQL Server ใช้ `text(...)` และ bind `:schema` โดยไม่ interpolate SQL ด้วย f-string
  - ทดสอบ: ตรวจลำดับการอ่านก่อน thread, snapshot, dispose ทั้ง success/error และ schema bind parameter
  - AC ที่ครอบคลุม: R5-AC-7

- [x] R5-T9: M-3 — Snapshot debug mode และจัด UI callback บน main thread
  - ไฟล์: `database_connect_gui.py` — `_execute_query_background`, `execute_query`, `test_connection`; `tests/test_bugfix_m3.py`
  - ทำอะไร: อ่าน `debug_mode` หนึ่งครั้งก่อนเริ่ม worker และส่งค่าเข้าไป; จัดการ UI ของ `test_connection` ผ่าน `root.after` โดย worker ไม่เรียก Tk
  - ทดสอบ: เปลี่ยน debug flag หลังเริ่ม worker แล้วยืนยันใช้ snapshot; ตรวจ UI/result/dialog ผ่าน `root.after`
  - AC ที่ครอบคลุม: R5-AC-8
  - สถานะ: focused QA passed (`tests.test_bugfix_m3`, 2 tests)

- [x] R5-T10: M-2 — บังคับ status cells เป็น string literal
  - ไฟล์: `database_connect_gui.py` — SQL annotation, No Data, Failed, Skipped sheets ใน Export worker; `tests/test_bugfix_m2.py`
  - ทำอะไร: หลัง `ws.cell(...)` สำหรับ SQL annotation และข้อความ status กำหนด `cell.data_type = 's'` เพื่อให้ข้อความที่ขึ้นต้นด้วย `=` เป็น string ไม่ใช่สูตร
  - ทดสอบ: ตรวจ `data_type == 's'` และ literal value สำหรับ annotation, No Data, Failed, Skipped
  - AC ที่ครอบคลุม: R5-AC-9
  - สถานะ: focused QA passed (`tests.test_bugfix_m2`, 1 test)

- [x] R5-T11: M-4 — ยืนยันก่อนปิดแอประหว่างงาน
  - [x] R5-T11: M-4 — ยืนยันก่อนปิดแอประหว่างงาน (focused QA passed: `tests.test_bugfix_m4`, 3 tests)
  - ไฟล์: `database_connect_gui.py` — `on_closing`; `tests/test_bugfix_m4.py`
  - ทำอะไร: เมื่อ busy ถาม Yes/No; No ไม่ทำลาย root, Yes ทำลาย root; idle คงพฤติกรรมเดิม
  - ทดสอบ: busy/No, busy/Yes และ idle ด้วย mock
  - AC ที่ครอบคลุม: R5-AC-10

- [x] R5-T12: M-5 — ยืนยัน overwrite preset และเขียนแบบ atomic (implementation complete; QA passed: 3 tests)
  - ไฟล์: `database_connect_gui.py` — `save_preset_dialog`; `tests/test_bugfix_m5.py`
  - ทำอะไร: ตรวจชื่อชนแบบ case-insensitive และถามก่อนเขียนทับ; Cancel/write failure รักษาไฟล์เดิม; ใช้ `write_json_atomic`
  - สถานะ: focused QA passed (`tests.test_bugfix_m5`, 3 tests)
  - ทดสอบ: collision ต่าง case, cancel, overwrite สำเร็จ และ write failure
  - AC ที่ครอบคลุม: R5-AC-11

- [x] R5-T13: M-6 — Reload Profile ที่ถูกเขียนทับจาก Import (implementation complete; focused QA passed: `tests.test_bugfix_m6`, 3 tests)
  - ไฟล์: `database_connect_gui.py` — callback `do_import`, `load_profile_data`; `tests/test_bugfix_m6.py`
  - ทำอะไร: logic ที่ต้องการมีอยู่แล้วใน `do_import`: เมื่อ import เขียนทับ Profile ที่ active และ save สำเร็จ เรียก `load_profile_data(active)`; Profile อื่นไม่ reload และ save failure rollback แล้ว return โดยไม่ reload
  - ทดสอบ: active overwrite, import Profile อื่น, และ failure/rollback
  - AC ที่ครอบคลุม: R5-AC-12

- [x] R5-T14: Regression ทั้งชุด Round 5
  - ไฟล์: ทุก test เดิมและ `tests/test_bugfix_*.py` ทั้ง 12 ไฟล์ (QA รันอย่างเดียว)
  - ทำอะไร: หลัง R5-T1 ถึง R5-T13 ผ่าน รัน `python -m unittest discover -s tests -p "test_*.py"`
  - AC ที่ครอบคลุม: R5-AC-13
  - ผล (2026-11-16): `Ran 842 tests in 19.692s — OK` ไม่มี failure/error (ข้อความ stderr เป็น log จาก negative-path tests)

## ตาราง R5-AC → Task

| R5-AC | Task | R5-AC | Task | R5-AC | Task |
|---|---|---|---|---|---|
| R5-AC-1 | R5-T1 | R5-AC-2 | R5-T2, R5-T3 | R5-AC-3 | R5-T4 |
| R5-AC-4 | R5-T5 | R5-AC-5 | R5-T6 | R5-AC-6 | R5-T7 |
| R5-AC-7 | R5-T8 | R5-AC-8 | R5-T9 | R5-AC-9 | R5-T10 |
| R5-AC-10 | R5-T11 | R5-AC-11 | R5-T12 | R5-AC-12 | R5-T13 |
| R5-AC-13 | R5-T14 | | | | |

---

# Round 6 — Bugfix: Import Groups รายงานสำเร็จแม้บันทึก `script_groups.json` ไม่สำเร็จ

> อ้างอิง: `docs/spec.md` หัวข้อ Round 6 (R6-AC-1 ถึง R6-AC-13), `docs/design.md` หัวข้อ Round 6 (R6-D1 ถึง R6-D8)
> R6-Q-1: refresh หลัง rollback ด้วย `None` (คงกลุ่มที่เลือกอยู่เดิม)
> Focused test: `python -m unittest tests.test_r6_import_save_failure tests.test_r3_script_groups_io tests.test_script_groups_block tests.test_script_groups_backup`
> Developer ทำทีละ task และหยุดให้ QA รัน focused test ก่อนเริ่ม task ถัดไป

- [x] R6-T1: `save_script_groups()` คืน `bool` (QA: 12 test ใน `tests/test_r6_import_save_failure.py::TestSaveReturnsBool` ผ่าน)
  - ไฟล์: `database_connect_gui.py` — `save_script_groups` (~4392-4413); `tests/test_script_groups_block.py:154`; `tests/test_r6_import_save_failure.py` (ใหม่)
  - ทำอะไร: เพิ่ม `-> bool`; ทาง `_script_groups_save_blocked` `return False` หลัง `showerror` เดิม; ใน `except` `return False` หลัง `showerror` เดิม; หลัง `write_json_atomic` `return True` ข้อความ/title dialog ไม่เปลี่ยน; แก้ assertion เดิม `assertIsNone(stub.save_script_groups())` ที่ `test_script_groups_block.py:154` เป็น `assertIs(..., False)` (ขัดกับ R6-AC-1 โดยตรง — ดู R6-D5 / R6-R1)
  - ทดสอบ: blocked → `False` (เป็น bool), showerror 1 ครั้ง ข้อความเดิม, `write_json_atomic` ไม่ถูกเรียก, ไฟล์ไม่เปลี่ยน; `write_json_atomic` raise `OSError` และ `_backup_script_groups_once` raise → `False`, showerror `Cannot save script_groups.json:\n<error>` 1 ครั้ง, ไฟล์เดิมไม่เปลี่ยน; tempdir เขียนได้ → `True`, ไม่มี showerror, เนื้อหา `{"version": 1, "groups": [...]}` ตัด key `_*` / `run_index`
  - AC ที่ครอบคลุม: R6-AC-1, R6-AC-2, R6-AC-3

- [x] R6-T2: `import_script_groups` rollback เมื่อบันทึกล้มเหลว (QA: 24 test ใน `tests/test_r6_import_save_failure.py` ผ่าน — rollback 14, success 6, early-exit 4; focused 218 test OK)
  - ไฟล์: `database_connect_gui.py` — `import_script_groups` (~4517-4525); `tests/test_r3_script_groups_io.py:876`; `tests/test_r6_import_save_failure.py`
  - ทำอะไร: หลัง `if replace is None: return None` เก็บ `snapshot = copy.deepcopy(self.script_groups)` ก่อน `merge_imported_script_groups`; `if not self.save_script_groups():` → `self.script_groups[:] = snapshot` → `self._refresh_script_groups_window(None)` → `return None` (ไม่ log `📥 Imported`, ไม่ `see`); ทางสำเร็จคงเดิม (refresh(last_name) → log → return last_name); แก้ mock ที่ `test_r3_script_groups_io.py:876` ให้คืน `True` (เช่น `lambda: order.append("save") or True`) ไม่แก้ assertion
  - ทดสอบ: ใช้ `save_script_groups` จริงทั้งแบบ blocked และ `write_json_atomic` raise `OSError`; ข้อมูลเดิมมีกลุ่ม Profile อื่นและ script ที่มี dict/list ซ้อน — ไม่ชน / ชน+Yes / ชน+No: คืน `None`, `script_groups == snapshot`, `script_groups is` list เดิม, ไม่มี `📥 Imported`, ไม่มี showinfo หลังยืนยัน, save ถูกเรียก 1 ครั้ง, ไฟล์บนดิสก์ไม่เปลี่ยน; ผ่าน `sidebar_import_script_groups()` คืน `None`; หน้าต่างเปิด → refresh callback 1 ครั้งด้วย `None` และขณะเรียก `script_groups == snapshot` แล้ว; หน้าต่างปิด → ไม่มี error; ทางสำเร็จ (save จริงบน tempdir) ไม่ชน/Yes/No ได้ผลตาม R3-AC-12/15 และลำดับ save → refresh(ชื่อสุดท้าย) → log; test Cancel/ไฟล์ผิด/ไม่มี Profile เดิมใน `test_r3_script_groups_io.py` ยังผ่าน
  - AC ที่ครอบคลุม: R6-AC-4, R6-AC-5, R6-AC-6, R6-AC-7, R6-AC-8, R6-AC-9, R6-AC-10, R6-AC-11, R6-AC-12

- [x] R6-T3: Regression ทั้งชุด Round 6 (QA: `PYTHONIOENCODING=utf-8` Ran 878 tests OK; ถ้าไม่ตั้ง UTF-8 และ pipe output, `test_bugfix_h3` error 1 ข้อจาก `print` cp874 ใน `save_profiles` ~10800 — ปัญหา environment นอก Round 6)
  - ไฟล์: ทุก test เดิมและ `tests/test_r6_import_save_failure.py` (QA รันอย่างเดียว)
  - ทำอะไร: หลัง R6-T1 และ R6-T2 ผ่าน รัน `python -m unittest discover -s tests -p "test_*.py"`; ยืนยันว่าเทส Cancel / ไฟล์ไม่ถูกต้อง / ไม่มี Profile (R3-AC-10, 11, 13) ยังผ่าน
  - AC ที่ครอบคลุม: R6-AC-12, R6-AC-13

## ตาราง R6-AC → Task

| R6-AC | Task | R6-AC | Task | R6-AC | Task |
|---|---|---|---|---|---|
| R6-AC-1 | R6-T1 | R6-AC-2 | R6-T1 | R6-AC-3 | R6-T1 |
| R6-AC-4 | R6-T2 | R6-AC-5 | R6-T2 | R6-AC-6 | R6-T2 |
| R6-AC-7 | R6-T2 | R6-AC-8 | R6-T2 | R6-AC-9 | R6-T2 |
| R6-AC-10 | R6-T2 | R6-AC-11 | R6-T2 | R6-AC-12 | R6-T2, R6-T3 |
| R6-AC-13 | R6-T3 | | | | |

---

# Round 7 — Bugfix: ผลค้างจาก Round 5 / Round 6 review (R7-1 ถึง R7-5)

> อ้างอิง: `docs/spec.md` หัวข้อ Round 7 (R7-AC-1 ถึง R7-AC-28), `docs/design.md` หัวข้อ Round 7 (R7-D1 ถึง R7-D10)
> R7-Q-1..5 ใช้คำตอบแนะนำ: guard `print` และคงไว้ / ไม่ตรวจ `"..."` / Skipped-Failed คงตัวนับ + log warning / rollback แล้วเลือกกลุ่มตามชื่อเดิม + script index เดิม / บรรทัด SQL ที่เกินเว้นว่าง
> แต่ละ task แก้จุดเดียวใน `database_connect_gui.py` และมีไฟล์ test ของตัวเอง → developer / QA ทำทีละ task ได้อิสระ; หยุดให้ QA รัน focused test ก่อนเริ่ม task ถัดไป
> ทุก test ใหม่ห้าม print อักขระนอก cp874 ลง stdout จริง (R7-AC-28 mode ข)

- [x] R7-T1: R7-1 — guard `print` ใน `save_profiles` failure path (QA: `tests/test_r7_console_print.py` 14 tests; focused 31 OK; full suite 899 OK)
  - ไฟล์: `database_connect_gui.py` — `save_profiles` except branch (~10798-10802); `tests/test_r7_console_print.py` (ใหม่)
  - ทำอะไร: ครอบ `print(error_msg)` ด้วย `try: ... except Exception: pass` แล้ว `showerror` / `return False` ตามเดิม (R7-D2); ไม่แก้ `save_jobs`, `save_script_groups`, `_profiles_save_refused` (ไม่มี print — เป็น regression lock) และไม่แก้ `print` อื่น
  - ทดสอบ: stdout cp874 strict / `write` raise `OSError` / `sys.stdout = None` + `write_json_atomic` raise → `save_profiles()` คืน `False` (`assertIs`), showerror 1 ครั้ง title `"Save Error"` ข้อความเดิม, ไฟล์ profile ไม่เปลี่ยน; `save_jobs()` / `save_script_groups()` ทั้ง blocked และ write raise + `save_profiles()` กรณี `_profiles_save_blocked` → `False` showerror 1 ครั้ง; `delete_profile` และ `do_import` ภายใต้ stdout cp874 → `saved_profiles` rollback ไม่มี success / exception; stdout `io.StringIO` → ยังมี `error_msg` ใน stdout, สำเร็จคืน `True` ไม่พิมพ์
  - Focused: `python -m unittest tests.test_r7_console_print tests.test_bugfix_h3`
  - AC ที่ครอบคลุม: R7-AC-1, R7-AC-2, R7-AC-3, R7-AC-4, R7-AC-5

- [x] R7-T2: R7-2 — `run_job` ใช้ default Profile กับ Job รุ่นเก่า (QA: `tests/test_r7_run_job_legacy_profile.py` 7 tests; focused 44 OK; full suite 899 OK)
  - ไฟล์: `database_connect_gui.py` — `run_job` (~9639-9641); `tests/test_r7_run_job_legacy_profile.py` (ใหม่)
  - ทำอะไร: อ่าน `selected_profile = self.profile_combo.get()` ก่อน แล้ว `job_profile = job.get("profile", selected_profile)`; ข้อความ `⛔` และ flow ถัดไปคงเดิม (R7-D3)
  - ทดสอบ: Job ไม่มี key + combo `"P1"` → ไม่มี `⛔ Run Job ไม่ได้เริ่มงาน`, `_capture_run_target` / `_block_if_profile_mismatch` ถูกเรียก; `"P2"` vs `"P1"` → ปฏิเสธตาม R5-AC-1; matrix ไม่มี key / `"P1"` / `"P2"` (และ `None` ชัดเจน) ตัดสินตรงกับการอยู่ใน `_current_profile_jobs()`; `tests/test_bugfix_c1.py` ผ่านโดยไม่แก้
  - Focused: `python -m unittest tests.test_r7_run_job_legacy_profile tests.test_bugfix_c1 tests.test_r4_profile_mismatch tests.test_run_entry_block`
  - AC ที่ครอบคลุม: R7-AC-6, R7-AC-7, R7-AC-8

- [x] R7-T3: R7-3 (ส่วน 1) — helper นับ UTF-16 และใช้กับ cell ผลลัพธ์ของ C-2 (QA: `tests/test_r7_excel_cell_limit.py` 29 tests รวม R7-T4; full suite 1007 OK ทั้ง mode utf-8 และ cp874)
  - ไฟล์: `database_connect_gui.py` — module level ใต้ `_ensure_excel_row_limit` (~114-120): `EXCEL_MAX_CELL_CHARS`, `_excel_text_too_long(value: object) -> bool`; C-2 check ใน `export_jobs_to_excel` (~10512-10515); `tests/test_r7_excel_cell_limit.py` (ใหม่)
  - ทำอะไร: เพิ่ม helper ตาม R7-D4 (fast path สองชั้น + `encode("utf-16-le", "surrogatepass")`); เปลี่ยน lambda ของ C-2 เป็น `_excel_text_too_long`; ข้อความ log C-2 เดิมไม่เปลี่ยน
  - ทดสอบ: helper โดยตรง — non-str → `False`, ASCII / ไทย 32,767 → `False`, 32,768 → `True`, `"😀" * 16384` → `True`, `"😀" * 16383 + "a"` → `False`, lone surrogate ไม่ raise; export จริง (แนว `test_bugfix_c2.py`) cell ผลลัพธ์ `"😀" * 16384` ว่าง + warning + นับ Warning, `"😀" * 16383 + "a"` เขียนครบ, 32,767 ไทย/ASCII ไม่มี warning; `tests/test_bugfix_c2.py`, `tests/test_bugfix_m2.py` ผ่านโดยไม่แก้
  - Focused: `python -m unittest tests.test_r7_excel_cell_limit tests.test_bugfix_c2 tests.test_bugfix_m2`
  - AC ที่ครอบคลุม: R7-AC-13 (cell ผลลัพธ์), R7-AC-14, R7-AC-15 (cell ผลลัพธ์)

- [x] R7-T4: R7-3 (ส่วน 2) — เว้นว่างข้อความเกินใน Skipped / Failed / No Data / SQL annotation (QA: `tests/test_r7_excel_cell_limit.py` 29 tests รวม R7-T3; full suite 1007 OK ทั้ง mode utf-8 และ cp874)
  - ขึ้นกับ: R7-T3 (`_excel_text_too_long`)
  - ไฟล์: `database_connect_gui.py` — worker ของ `export_jobs_to_excel`: local helper ใหม่ `sql_line_too_long`, `blank_oversized_cells`; Skipped (~10406-10414), No Data (~10439-10445), `append_sql_annotation` (~10340-10355) + จุดเรียก (~10553-10559), Failed (~10630-10632); `tests/test_r7_excel_cell_limit.py`
  - ทำอะไร: ตาม R7-D4 — Skipped / Failed สร้าง DataFrame จาก `blank_oversized_cells(job_name, {...})` (ตัวนับ Skipped / Failed คงเดิม); No Data ข้ามบรรทัดที่เกิน (แถวอื่นอยู่ที่ `start_row + line_no` เดิม) และถ้ามีบรรทัดถูกเว้น `warnings += 1` แทน `ok += 1`; `append_sql_annotation(ws, sql_text, job_name) -> bool` ข้ามบรรทัดที่เกินและคืน `True` เมื่อมีการเว้น → จุดเรียกตั้ง `job_warning = True`; รูปแบบ log ตาม R7-D4 (ชื่อ Job + `column '<col>'` หรือ `SQL line <n>` + `32,767`)
  - ทดสอบ: Skipped query เกิน → `Query` ว่าง, `Status` = `Skipped`, `Message` เดิม, log มีชื่อ Job / `Query` / `32,767`, นับ Skipped; Failed query และ/หรือ error เกิน → เฉพาะ cell ที่เกินว่าง, log ต่อ column, นับ Failed; No Data บรรทัดเกิน → cell ว่าง, บรรทัดอื่นแถวเดิมเริ่มแถว 3, log ชื่อ Job / SQL / เลขบรรทัด, Warning +1 Success ไม่เพิ่ม; annotation บรรทัดเกิน → cell ว่าง, ตำแหน่งอื่นเดิม, `Status: ⚠️ Warning`, นับ Warning 1 ครั้งแม้ cell ผลลัพธ์เกินด้วย; ขอบ 32,767 / 32,768 ทุกตำแหน่ง; ไม่มีค่าเกิน → workbook / log / ตัวนับเหมือนเดิม และ `data_type == "s"` ตาม R5-AC-9
  - Focused: `python -m unittest tests.test_r7_excel_cell_limit tests.test_bugfix_c2 tests.test_bugfix_m2 tests.test_r4_excel_row_limit`
  - AC ที่ครอบคลุม: R7-AC-9, R7-AC-10, R7-AC-11, R7-AC-12, R7-AC-13, R7-AC-15

- [x] R7-T5: R7-4 — ตรวจ placeholder ที่เป็นเนื้อหาทั้ง literal `'...'` (QA: `tests/test_r7_quoted_placeholder.py` 26 tests; full suite 1007 OK ทั้ง mode utf-8 และ cp874)
  - ไฟล์: `database_connect_gui.py` — module level `_SQL_COLON_PLACEHOLDER_RE` ข้าง `_SQL_BRACED_PLACEHOLDER_RE` (~453); `_detect_sql_placeholders` (~458-494); `tests/test_r7_quoted_placeholder.py` (ใหม่); **`tests/test_bugfix_m1.py:21-24` (แก้ค่าคาดหวัง)**
  - ทำอะไร: เพิ่มกิ่ง `kind == "string"` ก่อน `if kind != "punct": continue` ตาม R7-D5 (`len >= 2`, ขึ้นต้น/ลงท้าย `'`, `fullmatch` ไม่ trim, append `inner`); ไม่แก้ `_render_sql_template`; แก้ `test_bugfix_m1.py` เฉพาะ list ที่คาดหวังเป็น `[":real_bind", "{braced}", "{{double_braced}}", ":literal"]`
  - ทดสอบ: `':ACC'` → `[":ACC"]`, `'{acc}'` → `["{acc}"]`, `'{{ ACC }}'` → `["{{ ACC }}"]`; `'HH24:MI:SS'`, `'text {x}'`, `'a :ACC'`, `' :ACC'`, `':ACC '`, `':ACC:B'`, `'::x'`, `':1'`, `''`, `/* ':ACC' */`, `-- ':ACC'`, `":ACC"`, `$$:ACC$$` → `[]`; `:ACC` + `':ACC'` และ `{ACC}` + `'{ACC}'` ปรากฏครั้งเดียวตามลำดับพบครั้งแรก; detect → `_render_sql_template({"ACC": (":ACC", "'1'")})` ได้ `WHERE a IN ('1')` และรูป `'{ACC}'` เช่นกัน
  - Focused: `python -m unittest tests.test_r7_quoted_placeholder tests.test_bugfix_m1 tests.test_bugfix_h2 tests.test_database_connect_gui_core`
  - AC ที่ครอบคลุม: R7-AC-16, R7-AC-17, R7-AC-18, R7-AC-19, R7-AC-20

- [x] R7-T6: R7-5 (ส่วน 1) — `save_or_rollback` + action ระดับกลุ่ม (`new_group`, `rename_group`, `delete_group`) (QA: `tests/test_r7_script_groups_dialog_rollback.py` 53 tests รวม R7-T7; full suite 1007 OK ทั้ง mode utf-8 และ cp874)
  - ไฟล์: `database_connect_gui.py` — `show_script_groups_dialog`: local helper `save_or_rollback` (หลัง `name_taken` ~5023-5026), `new_group` (~5029-5048), `rename_group` (~5050-5062), `delete_group` (~5064-5078); `tests/test_r7_script_groups_dialog_rollback.py` (ใหม่ — สร้าง harness Tk ที่ R7-T7 ใช้ต่อ)
  - ทำอะไร: ตาม R7-D6 — helper save → ถ้าล้มเหลว `self.script_groups[:] = snapshot` → `refresh_groups(select_name=prev_name)` → `refresh_scripts(select_index=prev_index)` (ถ้าไม่ใช่ `None`) → คืน `False`; ในสาม action จับ `prev_name` (ชื่อ **ก่อน**แก้ / กลุ่มที่เลือกอยู่สำหรับ `new_group`) + `prev_index` + `copy.deepcopy(self.script_groups)` หลังทาง cancel / ชื่อซ้ำ / askyesno และก่อนแก้ข้อมูล; `if not save_or_rollback(...): return`; บรรทัด refresh ทางสำเร็จคงเดิม
  - ทดสอบ: Tk `withdraw()` + skip ไม่มี display; ข้อมูลมีหลายกลุ่มของ `P1` + กลุ่ม Profile อื่น + script ที่มี dict/list ซ้อน; ล้มเหลวสองแบบ (blocked / `write_json_atomic` raise) สำหรับ `＋ New Group`, `✎  Rename`, `🗑  Delete` → `script_groups == snapshot` และ `is` list เดิม, save 1 ครั้ง, ไฟล์ไม่เปลี่ยน, groups / scripts listbox ตรง snapshot, กลุ่มที่เลือก = ชื่อก่อนกด (new_group = กลุ่มเดิม), showerror 1 ครั้ง ไม่มี showinfo; สำเร็จ → ข้อมูล+ไฟล์เปลี่ยน, เลือกชื่อใหม่ (new/rename), ไม่มี showerror; ยกเลิก (ชื่อว่าง, ชื่อซ้ำ, askyesno No) → ไม่เรียก save
  - Focused: `python -m unittest tests.test_r7_script_groups_dialog_rollback tests.test_r3_script_groups_io tests.test_script_groups_block tests.test_r6_import_save_failure`
  - AC ที่ครอบคลุม: R7-AC-21, R7-AC-22, R7-AC-23, R7-AC-25, R7-AC-26, R7-AC-27 (สาม action กลุ่ม)

- [x] R7-T7: R7-5 (ส่วน 2) — action ระดับ script (`add_sql`, `add_from_jobs`, `edit_script`, `delete_script`, `move_script`) (QA: `tests/test_r7_script_groups_dialog_rollback.py` 53 tests รวม R7-T6; full suite 1007 OK ทั้ง mode utf-8 และ cp874)
  - ขึ้นกับ: R7-T6 (`save_or_rollback` และ harness test)
  - ไฟล์: `database_connect_gui.py` — `show_script_groups_dialog`: `add_sql` (~5081-5092), `add_from_jobs` (~5094-5113), `edit_script` (~5115-5128), `delete_script` (~5130-5145), `move_script` (~5147-5157); `tests/test_r7_script_groups_dialog_rollback.py`
  - ทำอะไร: ใช้ `save_or_rollback` ตามตาราง R7-D6 แถว 4-8 (`prev_name = group["name"]`; `prev_index` = `current_script_index()` สำหรับ add, `index` ก่อนแก้สำหรับ edit / delete / move); snapshot ของ `edit_script` ต้องอยู่ก่อน `script.pop(...)`, ของ `move_script` อยู่ใน `if 0 <= target < len(scripts):` ก่อนสลับ
  - ทดสอบ: ล้มเหลวสองแบบสำหรับ `＋ Add SQL`, `🕘  From Saved Jobs`, `✎ Edit`, `🗑 Remove`, `↑`, `↓` → เงื่อนไขเดียวกับ R7-T6 (snapshot, `is`, save 1 ครั้ง, ไฟล์, listbox, script index เดิม, showerror 1 ครั้ง); R7-AC-24: Rename ล้มเหลว → Edit ล้มเหลว → ปลดสาเหตุ → `＋ Add SQL` สำเร็จ → `script_groups.json` มี script ใหม่ในกลุ่มชื่อเดิม และหน่วยความจำ == ไฟล์ (ตัด `_*` / `run_index`); สำเร็จ → add เลือก script สุดท้าย, edit เลือก index เดิม, move เลือก index ปลายทาง; ยกเลิก (dialog คืนค่าว่าง, `_pick_jobs_dialog` ว่าง, askyesno No, move เกินขอบ) → ไม่เรียก save
  - Focused: `python -m unittest tests.test_r7_script_groups_dialog_rollback tests.test_r3_script_groups_io tests.test_script_groups_block tests.test_r6_import_save_failure`
  - AC ที่ครอบคลุม: R7-AC-21, R7-AC-22, R7-AC-23, R7-AC-24, R7-AC-25, R7-AC-26, R7-AC-27 (ห้า action script)

- [x] R7-T8: Regression ทั้งชุด Round 7 (สอง mode encoding) (QA: mode (ก) `PYTHONIOENCODING=utf-8` = Ran 1007 OK; mode (ข) cp874 redirect ไปไฟล์ = Ran 1007 OK; ไม่มี skip; ไม่ต้องแก้ test เดิม)
  - ไฟล์: ทุก test เดิม + `tests/test_r7_*.py` ทั้ง 5 ไฟล์ (QA รันอย่างเดียว)
  - ทำอะไร: หลัง R7-T1 ถึง R7-T7 ผ่าน รัน `python -m unittest discover -s tests -p "test_*.py"` บน Windows code page cp874 สองแบบ: (ก) `PYTHONIOENCODING=utf-8`; (ข) ไม่ตั้ง `PYTHONIOENCODING` / `PYTHONUTF8` และ redirect stdout+stderr ไปไฟล์หรือ pipe (`> out.txt 2>&1`); ยืนยันทั้งสองแบบ `OK` และจำนวน test เท่ากัน (รวม `test_bugfix_h3...test_save_profiles_returns_false_when_write_raises` ใน mode ข); ยืนยัน test เดิมของ Script Groups ผ่าน (ถ้ามี mock คืน `None` ในทางสำเร็จของ 8 action ให้ปรับเป็น `True` เท่านั้น); ถ้า mode (ข) ล้มจาก `print` นอก `save_profiles` ให้รายงานหัวหน้า (นอก scope — R7-R2)
  - AC ที่ครอบคลุม: R7-AC-27, R7-AC-28

## ตาราง R7-AC → Task

| R7-AC | Task | R7-AC | Task | R7-AC | Task |
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

> อ้างอิง: `docs/spec.md` หัวข้อ Round 8 (R8-AC-1 ถึง R8-AC-15), `docs/design.md` หัวข้อ Round 8 (R8-D1 ถึง R8-D8)
> R8-Q ที่ผู้ใช้อนุมัติ: Q-1 `print` 1 บรรทัดมี guard แบบ R7-1 ไม่มี dialog / Q-2 ลบ `<jobs_file>.tmp` best-effort ใน `load_jobs` เท่านั้น ไม่แก้ `write_json_atomic` / Q-3 ไม่ retry
> ขอบเขต: แก้เฉพาะ `load_jobs` ใน `database_connect_gui.py` — บัค B2-B16 อยู่นอกขอบเขต
> ทุก test ใหม่ห้าม print อักขระนอก cp874 ลง stdout จริง (R8-AC-15 mode ข)

- [x] R8-T1: แยก write-back ของ migration ออกจาก `try` ของการอ่านใน `load_jobs`
  - ผล QA: `git diff database_connect_gui.py` มี hunk เดียวอยู่ใน `load_jobs` (9509-9533); test ใหม่ R8-T2 ผ่านทั้งหมด
  - ไฟล์: `database_connect_gui.py` — `load_jobs` (~9482-9521) เท่านั้น
  - ทำอะไร: ตาม R8-D2 — ย้าย `# บันทึกกลับเฉพาะกรณีพบข้อมูลเก่า` / `if modified:` / `write_json_atomic(self.jobs_file, jobs, indent=4)` และ `return jobs` ออกไปหลัง `except` เดิม; ครอบ `write_json_atomic` ด้วย `try / except Exception as e:` ใหม่ ซึ่ง (1) `try: os.remove(f"{self.jobs_file}.tmp") except Exception: pass` (ต้องใช้ `os.remove`) (2) `try: print(f"Cannot write migrated jobs back to {self.jobs_file}: {e}") except Exception: pass` แล้วไปต่อ `return jobs`; ไม่ตั้ง `_jobs_save_blocked`, ไม่เรียก `_handle_unreadable_file` / `messagebox`; `except` เดิม (print `Error loading jobs` + `_handle_unreadable_file` + `return []`) และ loop เติม `"profile"` คงเดิมทุกตัวอักษร; ไม่แตะ `write_json_atomic`, `preserve_unreadable_file`, `_handle_unreadable_file`, `save_jobs`, loader อื่น; ไม่เพิ่ม flag / retry / dialog
  - ตรวจด้วยตนเอง: `python -m unittest tests.test_r2_reset_parameter_qa tests.test_bugfix_h3 tests.test_r7_console_print` ผ่าน
  - AC ที่ครอบคลุม: R8-AC-1 ถึง R8-AC-14 (โค้ด)

- [x] R8-T2: เขียน `tests/test_r8_load_jobs_writeback.py`
  - ผล QA: 18 test ใหม่ OK; focused (r8 + r2_reset_parameter_qa + bugfix_h3 + r7_console_print) `Ran 86 tests` OK ทั้ง PYTHONIOENCODING=utf-8 และ cp874 redirect ไฟล์; รัน test ใหม่กับโค้ดก่อนแก้ (HEAD) ล้ม 14 failures + 5 errors (จับบั๊ก B1 ได้จริง)
  - ขึ้นกับ: R8-T1
  - ไฟล์: `tests/test_r8_load_jobs_writeback.py` (ใหม่)
  - ทำอะไร: ตาม R8-D6 — stub `GUI.__new__` + `jobs_file` ใน `TemporaryDirectory` + `saved_profiles` + `_jobs_save_blocked = False`; patch `app.messagebox` ทุก test; ไฟล์รุ่นเก่า (Job ไม่มี `"profile"` + Job `"P2"`, ค่าซ้อน, ไทย); เขียนกลับล้มสองแบบ (ก) `app.os.replace` raise `PermissionError` (ข) `app.write_json_atomic` raise `OSError`
  - ทดสอบ:
    - AC-1 / AC-2: คืน list ครบ ลำดับและค่าเดิม, Job ไม่มี key ได้ `"P1"` (หรือ `"DEFAULT"` เมื่อ `saved_profiles = {}`), `"P2"` คงเดิม, ไม่มี exception
    - AC-3 / AC-4 / AC-5: ไม่มี `showwarning` / `showerror` / `showinfo`, `_handle_unreadable_file` ไม่ถูกเรียก, ไม่มีไฟล์ `_unreadable_`, `_jobs_save_blocked is False`, bytes ของ `saved_jobs.json` เท่าเดิม
    - AC-6: แบบ (ก) ไม่มี `saved_jobs.json.tmp` เหลือ; `app.os.remove` raise `OSError` → ยังคืนครบไม่มี exception (ปลด patch ก่อนออกจาก tempdir)
    - AC-7: stdout `io.StringIO` → 1 บรรทัดมี `saved_jobs.json` + ข้อความ error; stdout cp874 strict (error message มีอักขระนอก cp874) และ stdout ที่ `write` raise `OSError` → AC-1..5 ยังจริง
    - AC-8 / AC-9: ปลด patch → append `NEW` → `save_jobs()` `is True`, ไม่มี `showerror`, ไฟล์ = Job เดิม (มี `"profile"`) + `NEW`; `load_jobs()` อีกครั้งด้วย `wraps` spy → `write_json_atomic` ไม่ถูกเรียก, ค่าคืน == ไฟล์
    - AC-10: เขียนกลับสำเร็จ → ไฟล์ == ค่าคืน, เนื้อไฟล์ `indent=4`, ไม่มี `.tmp` / `_unreadable_` / dialog
    - AC-11: ทุก Job มี `"profile"` และ `[]` → spy ไม่ถูกเรียก, bytes + `st_mtime_ns` ไม่เปลี่ยน, ไม่มี dialog
    - AC-12: JSON เสีย / `{}` / `[1]` / bytes decode ไม่ได้ → `[]`, `showwarning` 1 ครั้ง title `"Saved Jobs not loaded"` ข้อความขึ้นต้น `Cannot read saved_jobs.json:`, สำเนา `saved_jobs_unreadable_*.json` bytes เท่าเดิม, `_jobs_save_blocked is False`, spy ไม่ถูกเรียก, ไฟล์ไม่เปลี่ยน (capture stdout)
    - AC-13: JSON เสีย + `preserve_unreadable_file` คืน `None` → `[]`, `_jobs_save_blocked is True`, `save_jobs()` คืน `False` ไฟล์ไม่เปลี่ยน
    - AC-14: ไม่มีไฟล์ → `[]`, ไม่มี dialog, directory ว่าง
  - Focused: `python -m unittest tests.test_r8_load_jobs_writeback tests.test_r2_reset_parameter_qa tests.test_bugfix_h3 tests.test_r7_console_print tests.test_script_groups_block`
  - AC ที่ครอบคลุม: R8-AC-1, R8-AC-2, R8-AC-3, R8-AC-4, R8-AC-5, R8-AC-6, R8-AC-7, R8-AC-8, R8-AC-9, R8-AC-10, R8-AC-11, R8-AC-12, R8-AC-13, R8-AC-14

- [x] R8-T3: Regression ทั้งชุด Round 8 (สอง mode encoding)
  - หมายเหตุ: ผู้ใช้สั่งเลื่อน (ยังไม่รันทั้งชุด)
  - สถานะ (2026-11-23): ผ่าน — รันหลังแก้ Round 12 (follow-up) `python -m unittest discover -s tests -p "test_*.py"` → `Ran 1147 tests ... OK` ทั้ง (ก) `PYTHONIOENCODING=utf-8` และ (ข) ไม่ตั้ง (cp874, redirect stdout+stderr ไปไฟล์)
  - ขึ้นกับ: R8-T1, R8-T2
  - ไฟล์: ทุก test เดิม + `tests/test_r8_load_jobs_writeback.py` (QA รันอย่างเดียว)
  - ทำอะไร: รัน `python -m unittest discover -s tests -p "test_*.py"` บน Windows code page cp874 สองแบบตาม R7-AC-28: (ก) `PYTHONIOENCODING=utf-8`; (ข) ไม่ตั้ง `PYTHONIOENCODING` / `PYTHONUTF8` และ redirect stdout+stderr ไปไฟล์หรือ pipe (`> out.txt 2>&1`); ยืนยันทั้งสองแบบ `OK`, จำนวน test เท่ากัน และ ≥ 1007 + จำนวน test ใหม่ของ R8-T2; test เดิมไม่ต้องแก้ — ถ้ามี test เดิมล้มหรือ mode (ข) ล้มจาก `print` นอก `load_jobs` ให้รายงานหัวหน้า ไม่แก้เอง
  - AC ที่ครอบคลุม: R8-AC-15

## ตาราง R8-AC → Task

| R8-AC | Task | R8-AC | Task | R8-AC | Task |
|---|---|---|---|---|---|
| R8-AC-1 | R8-T1, R8-T2 | R8-AC-2 | R8-T1, R8-T2 | R8-AC-3 | R8-T1, R8-T2 |
| R8-AC-4 | R8-T1, R8-T2 | R8-AC-5 | R8-T1, R8-T2 | R8-AC-6 | R8-T1, R8-T2 |
| R8-AC-7 | R8-T1, R8-T2 | R8-AC-8 | R8-T1, R8-T2 | R8-AC-9 | R8-T1, R8-T2 |
| R8-AC-10 | R8-T1, R8-T2 | R8-AC-11 | R8-T1, R8-T2 | R8-AC-12 | R8-T1, R8-T2 |
| R8-AC-13 | R8-T1, R8-T2 | R8-AC-14 | R8-T1, R8-T2 | R8-AC-15 | R8-T3 |

---

# Round 9 — Bugfix B2: Load Preset ที่มี element เสียทำให้ Job ของ Profile ปัจจุบันหาย

> อ้างอิง: `docs/spec.md` หัวข้อ Round 9 (R9-AC-1 ถึง R9-AC-16), `docs/design.md` หัวข้อ Round 9 (R9-D1 ถึง R9-D9)
> R9-Q ที่ผู้ใช้อนุมัติ: Q-1 ปฏิเสธทั้งไฟล์ / Q-2 แสดงในรายการตามเดิม แล้ว `showerror` ตอนกด Load / Q-3 dict + `"name"` และ `"query"` เป็น string ไม่ว่าง / Q-4 `"jobs": []` ไม่ถือว่าเสีย / Q-5 exception ไม่คาดคิด → `_restore_jobs_snapshot` + `showerror` (มีข้อความ exception) ไม่ re-raise / Q-6 รันเฉพาะ focused รอบนี้
> ขอบเขต: แก้เฉพาะ `load_selected` ใน `load_preset_dialog` ของ `database_connect_gui.py` — B1 (Round 8, `load_jobs` ยังไม่ commit) ห้ามแตะ; B3-B16 อยู่นอกขอบเขต
> ทุก test ใหม่ห้าม print อักขระนอก cp874 ลง stdout จริง

- [x] R9-T1: Validate element ของ preset ก่อนแตะข้อมูล + rollback exception ใน `load_selected`
  - ผล QA: focused 57 tests OK ทั้ง PYTHONIOENCODING=utf-8 และ cp874 redirect; diff R9 อยู่ใน `load_selected` เท่านั้น
  - ไฟล์: `database_connect_gui.py` — `load_selected` ใน `load_preset_dialog` (~5515-5575) เท่านั้น
  - ทำอะไร: ตาม R9-D2 / R9-D3
    1. ต่อจาก `jobs = data.get("jobs", [])` ทันที (ก่อน `current_profile = ...`, `current_profile_jobs`, `askyesno`): loop `enumerate(jobs, start=1)` ตรวจตามลำดับ ไม่ใช่ `dict` → `is not a job object`; `"name"` ไม่ใช่ `str` / `.strip()` ว่าง → `has no valid 'name' (must be non-empty text)`; `"query"` เช่นเดียวกัน → `has no valid 'query' (must be non-empty text)`; เจอตัวแรก → `messagebox.showerror("Invalid Preset", f"Preset '{preset_name}' cannot be loaded.\n\nJob #{position} {problem}.\n\nYour current jobs were not changed.", parent=dialog)` แล้ว `return`
    2. คง snapshot 3 บรรทัดไว้นอก/ก่อน `try`; ครอบ "กรอง `self.saved_jobs` → loop ตั้ง `"profile"` + append → `saved = self.save_jobs()`" ด้วย `try / except Exception as e:` ซึ่ง `_restore_jobs_snapshot(saved_jobs_before, original_jobs, jobs_snapshot)` → `messagebox.showerror("Load Preset Failed", f"Preset '{preset_name}' was not loaded. Your current jobs were not changed.\n\n{type(e).__name__}: {e}", parent=dialog)` → `return` (ไม่ re-raise)
    3. หลัง `try`: `if not saved:` → `_restore_jobs_snapshot(...)` + `return` แบบเดิม **ไม่มี** `showerror` เพิ่ม; ส่วน `update_jobs_list` / `results_text` / `showinfo` / `dialog.destroy()` อยู่นอก `try` เดิมทุกตัวอักษร
  - ห้าม: แตะส่วนสร้างรายการ preset (~5497-5513), `save_jobs`, `_restore_jobs_snapshot`, `write_json_atomic`, `load_jobs`; สร้าง helper / method / flag ใหม่; refactor (`profile_combo.get()` สองครั้งคงเดิม)
  - ตรวจด้วยตนเอง: `python -m unittest tests.test_bugfix_h3 tests.test_bugfix_m5 tests.test_r8_load_jobs_writeback` ผ่าน
  - AC ที่ครอบคลุม: R9-AC-1 ถึง R9-AC-14 (โค้ด)

- [x] R9-T2: เขียน `tests/test_r9_load_preset_validation.py` และรัน focused
  - ผล QA: test ใหม่ 19 test (51 subTest ใน matrix) ผ่าน; focused 57 tests OK สอง mode; กับโค้ดก่อน R9 ล้ม 59 (จับบัค B2 ได้ รวมผล probe `['U-job', 'ok', 'new']`); test_r3_script_groups_io 145 OK
  - ขึ้นกับ: R9-T1
  - ไฟล์: `tests/test_r9_load_preset_validation.py` (ใหม่)
  - ทำอะไร: ตาม R9-D7 — ใช้ `make_job_stub` / `fake_dialog_widgets` แบบ `tests/test_bugfix_h3.py`; `profile_combo` = `"PROD"`; `jobs_file` ใน `TemporaryDirectory`; `_jobs_save_blocked = False`; สถานะเริ่มต้น `P-job0`, `U-job`, `P-job1`, `P-job2` (ค่าซ้อน + ไทย) เขียนด้วย `save_jobs()` จริง; patch `app.messagebox` ทุก test; ควบคุม `curselection` บน instance ของ `_FakeListbox` เมื่อต้องเลือก preset อื่น / ไม่เลือก (หา index จาก `listbox.items`)
  - ทดสอบ:
    - AC-1 / AC-2 / AC-3 / AC-4: matrix element เสียด้วย `subTest` (ไม่ใช่ dict 5 แบบ; ไม่มี `"name"` / `"query"`; `None` / ตัวเลข / list / `""` / `"   "`) × ตำแหน่ง กลาง / แรก / สุดท้าย + probe `[ok, None]` + element ที่ 2 และ 3 เสีย → `saved_jobs` ไม่เปลี่ยน (identity + ค่า), ไม่มี `askyesno` / `save_jobs` (spy) / `update_jobs_list` / `results_text` / `showinfo` / destroy, `showerror` 1 ครั้ง `parent=dialog` มีชื่อ preset + `Job #<n> `, bytes `saved_jobs.json` และ preset เท่าเดิม, Job ปกติใน `preset_data` ไม่มี `"profile"`
    - AC-5: ต่อจาก AC-1 append `new` → `save_jobs()` `is True`, ไฟล์ = 4 Job เดิม + `new`
    - AC-6: dialog เดียวกัน reject preset เสียแล้วเลือก preset ปกติ + Yes → สำเร็จตาม AC-9
    - AC-7: listbox แสดงทั้ง preset เสียและปกติด้วยรูปแบบเดิม; JSON เสีย / `"jobs"` ไม่ใช่ list ถูกข้ามพร้อม `skipped` (capture stdout)
    - AC-8: `save_jobs` mock แก้ in-place แล้ว `raise RuntimeError("boom")` → ไม่หลุด, identity + ค่า, `showerror` 1 ครั้งมี `boom`, ไม่มี success, ดิสก์ไม่เปลี่ยน
    - AC-9 / AC-10 / AC-11 / AC-12: preset ปกติ (ข้อความ `askyesno` เต็ม, ลำดับ, `"profile": "PROD"`, ไฟล์ == memory, success ครบ, ไม่มี `showerror`); ตอบ No; `[]` และไม่มี `"jobs"` → `with 0 jobs`, `saved_jobs == [U-job]`; ไม่เลือก → `showwarning` เดิม
    - AC-13: `save_jobs` คืน `False` หลังแก้ in-place → restore, `showerror.assert_not_called()`
    - AC-14: `save_jobs` จริง (ก) `app.write_json_atomic` raise `OSError` (ข) `_jobs_save_blocked = True` → `showerror` 1 ครั้งด้วยข้อความเดิมของ `save_jobs`, ไม่มี `showinfo`, ไฟล์ไม่เปลี่ยน
  - Focused (R9-Q-6): `python -m unittest tests.test_r9_load_preset_validation tests.test_bugfix_h3 tests.test_bugfix_m5 tests.test_r8_load_jobs_writeback` ต้อง OK โดยไม่แก้ test เดิม; แนะนำยืนยันว่า test ใหม่ล้มกับโค้ดก่อนแก้ (จับบัค B2 ได้จริง)
  - AC ที่ครอบคลุม: R9-AC-1, R9-AC-2, R9-AC-3, R9-AC-4, R9-AC-5, R9-AC-6, R9-AC-7, R9-AC-8, R9-AC-9, R9-AC-10, R9-AC-11, R9-AC-12, R9-AC-13, R9-AC-14, R9-AC-15

- [x] R9-T3: Regression ทั้งชุด Round 9 (สอง mode encoding)
  - หมายเหตุ: ผู้ใช้สั่งเลื่อน (ยังไม่รันทั้งชุด — R9-Q-6)
  - สถานะ (2026-11-23): ผ่าน — รันหลังแก้ Round 12 (follow-up) `python -m unittest discover -s tests -p "test_*.py"` → `Ran 1147 tests ... OK` ทั้ง (ก) `PYTHONIOENCODING=utf-8` และ (ข) ไม่ตั้ง (cp874, redirect stdout+stderr ไปไฟล์)
  - ขึ้นกับ: R9-T1, R9-T2
  - ไฟล์: ทุก test เดิม + `tests/test_r9_load_preset_validation.py` (QA รันอย่างเดียว)
  - ทำอะไร: รัน `python -m unittest discover -s tests -p "test_*.py"` บน Windows code page cp874 สองแบบตาม R7-AC-28 / R8-AC-15: (ก) `PYTHONIOENCODING=utf-8`; (ข) ไม่ตั้ง `PYTHONIOENCODING` / `PYTHONUTF8` และ redirect stdout+stderr ไปไฟล์หรือ pipe; ยืนยันทั้งสองแบบ `OK` จำนวน test เท่ากัน และไม่มี test เดิมถูกแก้ — ถ้าล้มให้รายงานหัวหน้า ไม่แก้เอง
  - AC ที่ครอบคลุม: R9-AC-16

## ตาราง R9-AC → Task

| R9-AC | Task | R9-AC | Task | R9-AC | Task |
|---|---|---|---|---|---|
| R9-AC-1 | R9-T1, R9-T2 | R9-AC-2 | R9-T1, R9-T2 | R9-AC-3 | R9-T1, R9-T2 |
| R9-AC-4 | R9-T1, R9-T2 | R9-AC-5 | R9-T1, R9-T2 | R9-AC-6 | R9-T1, R9-T2 |
| R9-AC-7 | R9-T1, R9-T2 | R9-AC-8 | R9-T1, R9-T2 | R9-AC-9 | R9-T1, R9-T2 |
| R9-AC-10 | R9-T1, R9-T2 | R9-AC-11 | R9-T1, R9-T2 | R9-AC-12 | R9-T1, R9-T2 |
| R9-AC-13 | R9-T1, R9-T2 | R9-AC-14 | R9-T1, R9-T2 | R9-AC-15 | R9-T2 |
| R9-AC-16 | R9-T3 | | | | |

---

# Round 10 — Bugfix B3: Export Excel ทำไฟล์ `.xlsx` เดิมหายเมื่อ export ไม่จบ

> อ้างอิง: `docs/spec.md` หัวข้อ Round 10 (R10-AC-1 ถึง R10-AC-21), `docs/design.md` หัวข้อ Round 10 (R10-D1 ถึง R10-D8)
> R10-Q ที่ผู้ใช้อนุมัติ: Q-1 temp `<stem>.<สุ่ม>.tmp.xlsx` ด้วย `mkstemp` ในโฟลเดอร์ปลายทาง / Q-2 Stop คงเดิม (ผ่าน temp + replace) / Q-3 ตรวจล็อกตอนเริ่ม fail เร็ว; replace ล้ม → เก็บ temp แจ้งสอง path ไม่ retry / Q-4 fatal → คงไฟล์เดิม ลบ temp / Q-5 ปรับเฉพาะ harness test_r4 / Q-6 ไม่ล้าง temp ค้าง / Q-7 ไม่มี `"query"` ยัง fatal แต่แสดงสาเหตุจริง / Q-8 ไม่รวมจุดอื่น / Q-9 ลบ temp ไม่ได้ → log 1 บรรทัด / Q-10 รันเฉพาะ focused
> ขอบเขต: `database_connect_gui.py` — import ส่วนหัว, helper ระดับ module 4 ตัว และ `worker()` ใน `export_jobs_to_excel`; ห้ามแตะ `load_jobs` / `load_preset_dialog` (Round 8-9 ยังไม่ commit), `on_done`, ส่วนก่อนเริ่ม worker, เนื้อ loop ราย Job และ B4-B16
> ทุก test ใหม่ห้าม print อักขระนอก cp874 ลง stdout จริง

- [x] R10-T1: เขียนผ่าน temp + `os.replace` ใน worker ของ `export_jobs_to_excel`
  - ผล QA (R10-T2): test ใหม่ 42 ตัวผ่านกับโค้ดนี้; diff R10 อยู่เฉพาะ import / helper 4 ตัว / worker ของ export ไม่แตะ hunk R8-R9
  - ไฟล์: `database_connect_gui.py` เท่านั้น — import (~2-15), helper ใหม่ต่อจาก `_excel_text_too_long` (~134), `worker()` (~10501-10806)
  - ทำอะไร: ตาม R10-D2 / R10-D3
    1. เพิ่ม `import contextlib`, `import tempfile` และ `BinaryIO`, `Iterator` ใน `from typing import ...`
    2. เพิ่ม helper 4 ตัวตาม signature ใน R10-D2: `_ensure_export_target_writable(file_path: str) -> None` (`os.open` `O_RDWR | O_BINARY` ไม่ create / truncate; ล้ม → raise ชนิดเดิม ข้อความ `Cannot write to {file_path}. ...` พร้อม `strerror`), `_create_export_temp_file(file_path: str) -> Tuple[BinaryIO, str]` (`mkstemp(prefix=f"{stem}.", suffix=".tmp.xlsx", dir=<abspath dir>)` + `os.fdopen(fd, "wb")`), `_excel_writer_saved_on_success(handle: BinaryIO) -> Iterator[Any]` (`contextlib.contextmanager`: `pd.ExcelWriter(handle, engine="openpyxl")` → `yield` → `writer.close()` เฉพาะเมื่อไม่มี exception), `_discard_export_temp(temp_path: str) -> Optional[str]` (`os.remove`; `FileNotFoundError` → `None`; `OSError` อื่น → `"<Type>: <strerror>"`)
    3. ใน `worker()`: ประกาศ `temp_handle` / `temp_path` / `keep_temp` ก่อน `try`; แทน `with pd.ExcelWriter(file_path, engine="openpyxl") as writer:` ด้วย `_ensure_export_target_writable(file_path)` → `temp_handle, temp_path = _create_export_temp_file(file_path)` → `with _excel_writer_saved_on_success(temp_handle) as writer:` (indent เดิม, body loop + sheet `Export` ไม่แตะแม้แต่ตัวเดียว)
    4. หลัง `with`: `temp_handle.close()` → `try: os.replace(temp_path, file_path)` / `except OSError` → `keep_temp = True` + `fatal_error` ข้อความตาม R10-D3 (มี `<Type>:`, `file_path`, `strerror`, `The completed export was kept at: {temp_path}`) / `else: temp_path = None`
    5. คง `except Exception as e: fatal_error = f"{type(e).__name__}: {str(e)}"` แล้วเพิ่ม `finally:` ปิด `temp_handle` ถ้ายังเปิด (กลืน `OSError`) และถ้า `temp_path` ไม่ใช่ `None` และไม่ `keep_temp` → `_discard_export_temp`; ล้ม → `log(f"⚠️ Could not delete temporary file: {temp_path} ({remove_error})\n")`
    6. `elapsed` / `self.root.after(... on_done ...)` คงเดิมหลัง `try`
  - ห้าม: แตะ `on_done`, ส่วนก่อนเริ่ม worker (~10318-10429), local helper ใน worker (~10431-10499), เนื้อ loop ราย Job (~10503-10798), `write_json_atomic`, `load_jobs`, `load_preset_dialog`; เปลี่ยนข้อความ log / ตัวนับเดิม; retry; ล้าง temp ค้าง; แตะจุดเขียนไฟล์อื่น (Q-8); แก้ไฟล์ใน `tests/`
  - ตรวจด้วยตนเอง: `python -m unittest tests.test_r7_excel_cell_limit tests.test_bugfix_c2 tests.test_bugfix_m2 tests.test_run_engine_batch tests.test_bugfix_c3 tests.test_r2_oracle_slash tests.test_run_entry_block tests.test_r2_table_data_refresh` ผ่าน (**ไม่รวม** `tests.test_r4_excel_row_limit` — คาดว่าล้มจนกว่า R10-T2 ปรับ harness; R10-R7)
  - AC ที่ครอบคลุม: R10-AC-1 ถึง R10-AC-17, R10-AC-19 (โค้ด)

- [x] R10-T2: ปรับ harness `tests/test_r4_excel_row_limit.py` + เขียน `tests/test_r10_export_atomic_write.py` และรัน focused
  - ผล QA: test ใหม่ 42 ตัว (AC-1..19; AC-14/15 แบบ CreateFileW รันจริงบน win32); harness test_r4 ปรับ 3 จุด (import tempfile, `_FakeWriter.close()`, path ใน TemporaryDirectory) ไม่แตะ assertion; focused 14 ไฟล์ `Ran 246 tests` OK ทั้ง PYTHONIOENCODING=utf-8 และ cp874 redirect; กับโค้ดก่อนแก้ (สำเนาใน scratchpad) ล้ม 24 failures + 4 errors (AC-1 เห็น 0 byte, AC-10 เห็น IndexError); ไม่มีไฟล์แปลกใน repo
  - ขึ้นกับ: R10-T1
  - ไฟล์: `tests/test_r4_excel_row_limit.py` (harness เท่านั้น), `tests/test_r10_export_atomic_write.py` (ใหม่)
  - ทำอะไร:
    1. Harness test_r4 ตาม R10-D5 / R10-Q-5: `run_export` ใช้ `tempfile.TemporaryDirectory()` และให้ `asksaveasfilename` คืน `os.path.join(<tmp>, "export.xlsx")`; เพิ่ม `def close(self): pass` ใน `_FakeWriter`; **ห้ามแตะ assertion**; ยืนยันว่าไม่มีไฟล์ใหม่ใน working directory ของ repo หลังรัน; รายงานรายการบรรทัดที่ปรับ
    2. Test ใหม่ตาม R10-D6 ครบ R10-AC-1 ถึง R10-AC-19 (AC-14 / AC-15 ส่วน `CreateFileW` skip เมื่อไม่ใช่ win32; AC-15 มีแบบ patch `os.replace` ที่ไม่ขึ้นกับ OS; AC-4 ใช้ subprocess + `kill()` — ถ้าทำไม่ได้บนเครื่องนี้ให้ตั้ง `[!]` และรายงาน ไม่ตัด AC เอง)
    3. แนะนำยืนยันว่า test ใหม่ล้มกับโค้ดก่อนแก้ (จับบัค B3 ได้จริง: AC-1 เห็น 0 byte, AC-10 เห็น `IndexError`)
  - Focused (R10-Q-10) — ต้อง `OK` ทั้ง `PYTHONIOENCODING=utf-8` และแบบไม่ตั้ง (cp874, redirect stdout+stderr):
    `python -m unittest tests.test_r10_export_atomic_write tests.test_r7_excel_cell_limit tests.test_bugfix_c2 tests.test_bugfix_m2 tests.test_r4_excel_row_limit tests.test_r2_table_data_refresh tests.test_r4_profile_mismatch tests.test_run_entry_block tests.test_r8_load_jobs_writeback tests.test_r9_load_preset_validation tests.test_run_engine_batch tests.test_bugfix_c3 tests.test_r2_oracle_slash tests.test_confirm_destination`
    (8 ไฟล์แรกตาม R10-AC-21, `test_r8` / `test_r9` ตาม R10-AC-20, 4 ไฟล์ท้ายเพราะรัน worker จริงหรือตรวจ source ของ `export_jobs_to_excel`)
  - AC ที่ครอบคลุม: R10-AC-1, R10-AC-2, R10-AC-3, R10-AC-4, R10-AC-5, R10-AC-6, R10-AC-7, R10-AC-8, R10-AC-9, R10-AC-10, R10-AC-11, R10-AC-12, R10-AC-13, R10-AC-14, R10-AC-15, R10-AC-16, R10-AC-17, R10-AC-18, R10-AC-19, R10-AC-20

- [x] R10-T3: Regression ทั้งชุด Round 10 (สอง mode encoding)
  - หมายเหตุ: ผู้ใช้สั่งเลื่อน (ยังไม่รันทั้งชุด — R10-Q-10)
  - สถานะ (2026-11-23): ผ่าน — รันหลังแก้ Round 12 (follow-up) `python -m unittest discover -s tests -p "test_*.py"` → `Ran 1147 tests ... OK` ทั้ง (ก) `PYTHONIOENCODING=utf-8` และ (ข) ไม่ตั้ง (cp874, redirect stdout+stderr ไปไฟล์)
  - ขึ้นกับ: R10-T1, R10-T2
  - ไฟล์: ทุก test เดิม + `tests/test_r10_export_atomic_write.py` (QA รันอย่างเดียว)
  - ทำอะไร: รัน `python -m unittest discover -s tests -p "test_*.py"` บน Windows code page cp874 สองแบบตาม R7-AC-28: (ก) `PYTHONIOENCODING=utf-8`; (ข) ไม่ตั้ง `PYTHONIOENCODING` / `PYTHONUTF8` และ redirect stdout+stderr ไปไฟล์หรือ pipe; ยืนยันทั้งสองแบบ `OK` จำนวน test เท่ากัน และไม่มี test เดิมถูกแก้นอกจาก harness test_r4 — ถ้าล้มให้รายงานหัวหน้า ไม่แก้เอง
  - AC ที่ครอบคลุม: R10-AC-21

## ตาราง R10-AC → Task

| R10-AC | Task | R10-AC | Task | R10-AC | Task |
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

> อ้างอิง: `docs/spec.md` หัวข้อ Round 11 (R11-AC-1 ถึง R11-AC-22), `docs/design.md` หัวข้อ Round 11 (R11-D1 ถึง R11-D10)
> R11-Q ที่ผู้ใช้อนุมัติ: Q-1 เตือนที่ header เท่านั้น / Q-2 ต่อท้าย `target_sub` + สี `#D97706` (`UI["warn"]`) / Q-3 แก้ Password อย่างเดียวไม่นับ / Q-4 เทียบ 5 ช่องหลัง strip, port `split(":")[0]`, case-sensitive / Q-5 เก็บ password ใน attribute ส่วนตัวตอน Connect ผูกกับ engine / Q-6 ไม่มี password (ทุก database, ไม่ใช่ Oracle) → block `⛔` ให้ Connect ใหม่ / Q-7 `info is None` → พฤติกรรมเดิม / Q-8 Save Job ไม่รวม / Q-9 รันเฉพาะ focused (R11-AC-22 เลื่อน)
> ขอบเขต: `database_connect_gui.py` เท่านั้น ตาม R11-D1 "ขอบเขต"; ห้ามแตะ `ConnectionInfo` / `RunTarget`, `_capture_run_target`, `_block_if_profile_mismatch`, `_confirm_data_change`, `execute_query`, worker ของ `list_tables`, Save Job / Save Profile, hunk Round 8-10 (ยังไม่ commit) และ B5-B16
> **รอตัดสิน R11-R1 ก่อนเริ่ม R11-T1**: `test_run_engine_batch.py::test_info_db_type_wins_over_screen_at_start` ขัดกับ R11-AC-16 / Q-6 — tasks ด้านล่างเขียนตามทางเลือก (ก) ที่แนะนำ (QA ปรับ harness 1 บรรทัด ไม่แตะ assertion); ถ้าเลือก (ข) architect ต้องแก้ R11-D5 / tasks ก่อน
> ทุก test ใหม่ห้าม print อักขระนอก cp874 ลง stdout จริง

- [x] R11-T1: Header + `list_tables` ใช้ snapshot ของ connection และเก็บ / ล้าง password ผูกกับ engine
  - ไฟล์: `database_connect_gui.py` เท่านั้น — ต่อจาก `RunTarget` (~412), `__init__` (`self.engine = None` ~2419, closure `_refresh_target_summary` ~2694-2709), `connect_database` (~7715), `_replace_engine` (~7735-7748), ต่อจาก `_capture_run_target` (~7762), `list_tables` (~9185-9199), `_reset_profile_connection_state` (~11138)
  - ทำอะไร: ตาม R11-D2 ถึง R11-D5
    1. ระดับ module ต่อจาก `RunTarget`: ค่าคงที่ `_TARGET_MISMATCH_NOTE = "  ·  ⚠ ช่อง Details ไม่ตรงกับ connection — กด Connect เพื่อใช้ค่าใหม่"` และ `_target_summary_text(db_type: str, user: str, host: str, port: str, database: str) -> Tuple[str, str]` (ข้อความคัดลอกจาก `:2701-2702` ทุกตัวอักษร)
    2. `__init__`: ต่อจาก `self.engine = None` เพิ่ม `self._connected_password: Optional[Tuple[Any, str]] = None`
    3. `_replace_engine(self, engine, info: Optional[ConnectionInfo] = None, password: Optional[str] = None) -> None`: ต่อจากบรรทัด `self._run_target = ...` เพิ่ม `self._connected_password = (engine, password) if engine is not None and password is not None else None`; ส่วน dispose เดิมไม่แตะ
    4. `connect_database` ทางสำเร็จ: `self._replace_engine(engine, info, password=password)` (password ไม่ strip); ทางล้ม / early return ไม่แก้
    5. `_reset_profile_connection_state`: ต่อจาก `self._run_target = None` เพิ่ม `self._connected_password = None`
    6. Method ใหม่ต่อจาก `_capture_run_target` ตาม signature ใน R11-D3 / R11-D4: `_connected_password_for(self, engine: Any) -> Optional[str]` (`getattr(self, "_connected_password", None)`, คืนค่าเมื่อ `stored[0] is engine` เท่านั้น), `_details_differ_from(self, info: ConnectionInfo) -> bool` (5 ช่อง strip, port `strip().split(":")[0]`, ไม่อ่าน `db_password` / `profile_combo`), `_update_target_summary(self, target_main: Any, target_sub: Any) -> bool` (มี `info` → ข้อความจาก `info` + คำเตือน + `fg=UI["warn"]` เมื่อไม่ตรง; ไม่มี `info` → ข้อความจากช่องกรอกแบบเดิม `fg=UI["muted"]`; เช็ก `cget("text")` / `str(cget("fg"))` ก่อน `config`; `tk.TclError` → คืน `False`)
    7. Closure `_refresh_target_summary` เหลือ `if self._update_target_summary(target_main, target_sub): self.root.after(500, _refresh_target_summary)` (ชื่อ / docstring / การเรียกครั้งแรก ~2721 คงเดิม)
    8. `list_tables`: แทน ~9185-9199 ตาม R11-D5 — `info = target.info`; มี `info` → `db_type = info.db_type`, `current_db_name = info.database`, `password = self._connected_password_for(engine)`, ถ้า `password is None and not current_db_name and db_type != "Oracle"` → `results_text.insert(tk.END, "⛔ Tables ไม่ได้เริ่มงาน: ไม่มีรหัสผ่านของ connection ปัจจุบัน — กด Connect ใหม่แล้วลองอีกครั้ง\n")` + `see(tk.END)` + `return` (ก่อน "Fetching..." / `inspect_btn` / dialog / Thread), ไม่งั้น `connection_credentials = (info.user, password or "", info.host, info.port)`; ไม่มี `info` → โค้ดเดิมทุกตัวอักษร (ลำดับ `db_type` → `db_name` → user → password → host → port)
  - ห้าม: เพิ่ม field ใน `ConnectionInfo` / `RunTarget`; แก้ worker `fetch_tables_in_background` (~9212-9440); ใส่ password ใน log / print / ข้อความใด; แตะ `_capture_run_target`, `_block_if_profile_mismatch`, `_confirm_data_change`, `execute_query`, `_refresh_conn_badge`, Save Job / Save Profile, hunk Round 8-10; เพิ่ม event binding; แก้ไฟล์ใน `tests/`
  - ตรวจด้วยตนเอง: `python -m unittest tests.test_run_target tests.test_bugfix_h1 tests.test_list_tables_stop tests.test_r4_profile_mismatch tests.test_run_entry_block tests.test_confirm_destination tests.test_profile_connect_block` ผ่าน; `tests.test_run_engine_batch` คาดว่าล้ม 1 test (`test_info_db_type_wins_over_screen_at_start`) จนกว่า R11-T2 ปรับ harness ตาม R11-R1 (ก) — ห้ามแก้โค้ดให้ test นั้นผ่านโดยเลี่ยง Q-6
  - AC ที่ครอบคลุม: R11-AC-1 ถึง R11-AC-9, R11-AC-11 ถึง R11-AC-20 (โค้ด)
  - สถานะ developer (2026-11-20): โค้ดครบตาม R11-D2 ถึง R11-D5 ด้วยทางเลือก R11-R1 (ก) ที่ผู้ใช้อนุมัติ — module `:415-426`, `__init__` `:2433`, closure `:2708-2711`, `connect_database` `:7717`, `_replace_engine` `:7737-7757`, method ใหม่ `:7775-7831`, `list_tables` `:9254-9285`, `_reset_profile_connection_state` `:11225`; worker ไม่แตะ; `ast.parse` ผ่าน; `tests.test_bugfix_h1 tests.test_run_engine_batch` 17 tests ล้ม 1 ตามคาด (`test_info_db_type_wins_over_screen_at_start` รอ harness ใน R11-T2) — รอ qa-tester

- [x] R11-T2: เขียน `tests/test_r11_connection_target_snapshot.py` + ปรับ harness ตาม R11-R1 และรัน focused
  - สถานะ qa-tester (2026-11-20): ผ่าน — ไฟล์ใหม่ 45 tests (R11-AC-1 ถึง R11-AC-20); harness 1 บรรทัดใน `tests/test_run_engine_batch.py:424` (`stub._connected_password = (engine_a, "pw")` ก่อน `threads = self._start(stub)`, ไม่แตะ assertion); focused 14 ไฟล์ `Ran 276 tests ... OK` ทั้ง `PYTHONIOENCODING=utf-8` และ cp874 + redirect; กับโค้ดก่อนแก้ (`git show HEAD:database_connect_gui.py`) ไฟล์ใหม่ล้ม 38/45 tests (11 failures + 41 errors นับ subTest) เช่น header แสดง `prod-db`, `get_connection_string` ได้ `other/pw-prod/prod-db/9999` — 7 tests ที่ผ่านกับโค้ดเดิมเป็น regression lock (AC-10 x2, AC-17, AC-9 closure x2, AC-16 ทาง database ปัจจุบัน, AC-18 leak check); R11-AC-22 ยังรอ (R11-T3)
  - ขึ้นกับ: R11-T1 (และคำตอบ R11-R1)
  - ไฟล์: `tests/test_r11_connection_target_snapshot.py` (ใหม่), `tests/test_run_engine_batch.py` (harness 1 บรรทัดเท่านั้น ถ้าอนุมัติ R11-R1 (ก))
  - ทำอะไร:
    1. Harness ตาม R11-R1 (ก): ใน `test_info_db_type_wins_over_screen_at_start` เพิ่ม `stub._connected_password = (engine_a, "pw")` ก่อน `threads = self._start(stub)`; **ห้ามแตะ assertion / test อื่น**; รายงานบรรทัดที่ปรับ
    2. Test ใหม่ตาม R11-D8 ครบ R11-AC-1 ถึง R11-AC-20 (นิยาม "snapshot UAT" / "ช่องกรอก PROD" ตาม spec R11-4): header ผ่าน `_update_target_summary` + closure ผ่าน AST (AC-9); `execute_query` regression (AC-10); `list_tables` + worker ด้วย `_Thread` จับ args, `forbid_get` (AC-13), block `⛔` (AC-16), Oracle (AC-15), info None (AC-17); password ผ่าน `connect_database` จริง (patch `create_engine` / `messagebox`) + `_connected_password_for` / `_connected_password is None` (AC-18, AC-19, AC-20)
    3. แนะนำยืนยันว่า test ใหม่ล้มกับโค้ดก่อนแก้ (จับบัค B4 ได้จริง: header แสดง `prod-db`, `get_connection_string` ได้ค่าจากช่องกรอก)
  - Focused (R11-Q-9) — ต้อง `OK` ทั้ง `PYTHONIOENCODING=utf-8` และแบบไม่ตั้ง (cp874, redirect stdout+stderr):
    `python -m unittest tests.test_r11_connection_target_snapshot tests.test_run_target tests.test_bugfix_h1 tests.test_run_engine_batch tests.test_list_tables_stop tests.test_bugfix_c1 tests.test_r4_profile_mismatch tests.test_run_entry_block tests.test_confirm_destination tests.test_profile_connect_block tests.test_profile_password tests.test_r8_load_jobs_writeback tests.test_r9_load_preset_validation tests.test_r10_export_atomic_write`
    (ไฟล์ใหม่ + 13 ไฟล์ตาม R11-AC-21)
  - AC ที่ครอบคลุม: R11-AC-1, R11-AC-2, R11-AC-3, R11-AC-4, R11-AC-5, R11-AC-6, R11-AC-7, R11-AC-8, R11-AC-9, R11-AC-10, R11-AC-11, R11-AC-12, R11-AC-13, R11-AC-14, R11-AC-15, R11-AC-16, R11-AC-17, R11-AC-18, R11-AC-19, R11-AC-20, R11-AC-21

- [x] R11-T3: Regression ทั้งชุด Round 11 (สอง mode encoding)
  - หมายเหตุ: ผู้ใช้สั่งเลื่อน (ยังไม่รันทั้งชุด — R11-Q-9)
  - สถานะ (2026-11-23): ผ่าน — รันหลังแก้ Round 12 (follow-up) `python -m unittest discover -s tests -p "test_*.py"` → `Ran 1147 tests ... OK` ทั้ง (ก) `PYTHONIOENCODING=utf-8` และ (ข) ไม่ตั้ง (cp874, redirect stdout+stderr ไปไฟล์)
  - ขึ้นกับ: R11-T1, R11-T2
  - ไฟล์: ทุก test เดิม + `tests/test_r11_connection_target_snapshot.py` (QA รันอย่างเดียว)
  - ทำอะไร: รัน `python -m unittest discover -s tests -p "test_*.py"` บน Windows code page cp874 สองแบบตาม R7-AC-28: (ก) `PYTHONIOENCODING=utf-8`; (ข) ไม่ตั้ง `PYTHONIOENCODING` / `PYTHONUTF8` และ redirect stdout+stderr ไปไฟล์หรือ pipe; ยืนยันทั้งสองแบบ `OK` จำนวน test เท่ากัน และไม่มี test เดิมถูกแก้นอกจาก harness ตาม R11-R1 — ถ้าล้มให้รายงานหัวหน้า ไม่แก้เอง
  - AC ที่ครอบคลุม: R11-AC-22

## ตาราง R11-AC → Task

| R11-AC | Task | R11-AC | Task | R11-AC | Task |
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

# Round 12 — Follow-up: ข้อเสนอแนะ 🟢 จาก review Round 8–11 (2026-11-23)

- [x] R12-1 (R8 🟢1): `write_json_atomic` ลบ `.tmp` เองเฉพาะเมื่อ call นี้เปิดไฟล์ได้แล้ว; `load_jobs` ไม่ลบ `.tmp` เอง (ไม่แตะ `.tmp` ที่ไม่ได้สร้าง) — R8-AC-6 tests ปรับตาม + test ใหม่ `test_ac6_tmp_not_created_by_this_call_is_left_alone`
- [x] R12-2 (R8 🟢2–4): `test_ac7_stdout_none` ทดสอบ `sys.stdout = None` จริงทั้งสอง mode; type hints ใน test; comment ใน `load_jobs` เป็นภาษาไทย
- [x] R12-3 (R9 🟢1–2): comprehension `current_profile_jobs` ข้าม element ที่ไม่ใช่ dict; test ใหม่: exception ระหว่าง filter ถูก rollback, element เสียใน `saved_jobs` ไม่หลุด exception ก่อน confirm
- [x] R12-4 (R10 🟢1, 3, 4): `mkstemp` ล้ม → ข้อความอ้าง path ที่ผู้ใช้เลือก (ไม่โชว์ temp path); temp path ใช้ separator แบบเดียวกับ path ที่เลือก; test ใหม่: handle ปิดก่อน `os.replace` / `os.remove` (ไม่ขึ้นกับ OS), `mkstemp` ล้ม, separator
- [x] R12-5 (R10 🟢2): `_replace_export_with_retry` — retry `os.replace` เฉพาะ `PermissionError` รอ `EXPORT_REPLACE_RETRY_DELAYS` = 0.2 / 0.5 / 1.0 วินาที (รวมสูงสุด 4 ครั้ง ~1.7 วินาที) แล้วจึงเก็บ temp + แจ้ง path เหมือนเดิม; error อื่นไม่ retry — ผู้ใช้สั่งแก้ (2026-11-23) แทน R10-Q-3 เดิม; R10-AC-15 จึงเปลี่ยนจาก replace 1 ครั้งเป็น 1 + จำนวน retry; test ใหม่: lock สั้น ๆ แล้วสำเร็จ, ค่า delay, OSError อื่นไม่ retry
- [x] R12-6 (R11 🟢1): ไม่ส่ง password เข้า thread ของ Tables เมื่อ worker ไม่ใช้ (database ปัจจุบัน / Oracle)
- [x] R12-7 (R11 🟢2): `redact_secrets()` ปิด `PWD=` / `password=` (ทั้งแบบปกติและ URL-encoded), userinfo ใน URL และรหัสผ่านที่รู้ค่า — ใช้กับ print / traceback ใน worker ของ Tables และ `on_list_tables_error`
- [x] R12-8 (R11 🟢3–5): `_details_differ_from` strip port ทั้งสองฝั่งหลัง split (`"5432 :x"` ไม่เตือนค้าง); type hints `_replace_engine(engine: Any)` / `_refresh_target_summary() -> None`; test ตั้ง password ผ่าน `_replace_engine` แทน tuple ภายใน
- [x] R12-9 (R12 review 🟡1): `RedactSecretsTests.test_patterns_and_known_secret` เทียบผล `redact_secrets` ทั้งบรรทัด (ODBC / URL-encoded มี `;Encrypt=yes` ต่อท้าย) + ตรวจว่าชิ้นส่วนรหัสในรูปที่ปรากฏจริง (`p@ss`, `p%40ss`, `w}}rd`, `rd}`, `%7D%7Drd`) ไม่หลุด — ยืนยันแล้วว่า test ล้มเมื่อ regex ไม่รองรับ `}}` / `%7D%7D` (mask ได้ครึ่งเดียว)
  - QA: mutation เพิ่ม (patch `app._SECRET_PATTERNS` ใน process): ODBC แบบไม่หยุดที่ `;` (`[^&\s'\"]*` / ต่อท้ายปีกกาปิด) และ URL-encoded แบบไม่หยุดที่ `%3B` → test ล้มทุกแบบ (mask กิน `;Encrypt=yes`); pattern เดิม → ผ่าน. Regression 2 mode (utf-8 / cp874 redirect) → `Ran 1147 tests ... OK` ทั้งคู่
- [x] R12-T: Regression ทั้งชุด สอง mode encoding → `Ran 1147 tests ... OK` ทั้งคู่
