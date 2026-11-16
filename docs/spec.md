# Spec — database_connect_gui

---

## Bugfix: 4 บัคจาก bug-hunter (C1, C2, H1, H2)

> สถานะ: **ผู้ใช้อนุมัติแล้ว** (จุดอนุมัติที่ 1) — ผู้ใช้เลือกคำตอบที่แนะนำครบทั้ง 8 ข้อ ดูหัวข้อ 6 "การตัดสินใจ"
> ไฟล์ที่เกี่ยวข้อง: `database_connect_gui.py`, `README.md` (เฉพาะบรรทัดที่อธิบายปุ่ม Stop / แถบเหลือง ถ้าจำเป็น)
> เลขบรรทัดในเอกสารนี้อ้างอิงจากโค้ดบน branch `ui/remove-duplicate-buttons` ณ วันที่เขียน spec (ตรวจกับโค้ดจริงแล้ว)

### 1. เป้าหมาย

แก้บัค 4 ข้อที่ bug-hunter ยืนยันแล้ว เพื่อให้ผู้ใช้ที่รัน SQL / Job กับฐานข้อมูลธนาคาร:

- **C1 (Critical)**: SQL / Job ทุกตัวในงานเดียวกันรันบนฐานข้อมูลเดียวกับตอนที่กดเริ่มเสมอ ไม่ไหลไปรันบนฐานข้อมูลของ Profile อื่นเพราะมีคนกด Connect, เปลี่ยน/แก้/ลบ/Import Profile ระหว่างรัน และหน้ายืนยันการแก้ข้อมูลกับ Run log ต้องบอกปลายทางที่จะรันจริง
- **C2 (Critical)**: ไม่ทำให้ Script Groups หายถาวร เมื่ออ่าน `script_groups.json` ไม่สำเร็จแล้วผู้ใช้กดบันทึก
- **H1 (High)**: ผู้ใช้กด Stop ได้ทุกครั้งที่มีงานรันอยู่ รวมถึงการรัน Job เดี่ยวด้วยปุ่ม ▶ (regression จาก commit 33d5461) และระหว่าง list_tables
- **H2 (High)**: `Ctrl+Enter` ต้องไม่รัน SQL เมื่อปุ่ม Run ถูกปิดอยู่

ผู้ได้ประโยชน์: ผู้ใช้แอปที่รัน SQL / Job / Export กับหลาย Profile (หลายฐานข้อมูล) และผู้ใช้ Script Groups

### 2. ขอบเขต

#### In scope

| บัค | ตำแหน่งในโค้ด (ยืนยันแล้ว) | สิ่งที่ต้องแก้ |
|---|---|---|
| C1 | `connect_database` 6987-7059, `_replace_engine` 7061-7072 | ห้าม Connect (สร้าง/สลับ engine) ระหว่างที่มีงานรันอยู่ |
| C1 | `on_profile_selected` 9982-9989, `load_profile_data` 10033-10075, `_reset_profile_connection_state` 10006-10031 | ห้ามเปลี่ยน Profile (ช่องเชื่อมต่อ, รายการ Job, SQL Editor) ระหว่างที่มีงานรันอยู่ |
| C1 (Q8) | `import_profiles_dialog` 3012, `delete_profile` 10439, `save_profile_dialog` 10094 (บันทึกทับ Profile ที่ใช้อยู่), `new_profile_dialog` 10174 (หลังสร้างจะสลับไป Profile ใหม่ที่ 10411), `update_profile_list` 9957-9980 | ห้าม Import Profile, ห้ามลบ/แก้ Profile ที่กำลังใช้ และห้ามการกระทำใดที่ทำให้สลับ Profile ระหว่างที่มีงานรันอยู่ |
| C1 | `read_sql_dataframe` 7109 (ใช้ `self.engine` ที่ 7122, 7127), `_execute_modification` 7166 (ใช้ `self.engine` ที่ 7175), worker ใน `_execute_query_background` 6219/6231, `run_job` 8932/8935, `run_selected_job` 9040/9074, `export_jobs_to_excel` 9558 | เก็บ engine เป็น snapshot ตอนเริ่มงาน แล้วให้ worker ใช้ engine ตัวนั้นตลอดงาน |
| C1 (Q1) | `run_job` 8834-8870, `run_selected_job` 8949-8991, `export_jobs_to_excel` 9388-9430, `execute_query` 7537-7556 | ห้ามเริ่มงานใหม่ทุกประเภทระหว่างที่มีงานรันอยู่ (รวม ▶ ของ Job การ์ดอื่น และ Export ระหว่าง Run All) |
| C1 (Q2) | ปุ่ม Connect 2069, combobox Profile 2047, ปุ่ม Run / ▶ / Run All / Export / Run Group / ปุ่มจัดการ Profile | ปิดปุ่ม (สีเทา) ระหว่างรัน ถ้าถูกเรียกทางอื่น (เช่น shortcut) ให้เขียนเหตุผลใน Execution Logs ไม่ใช้ popup |
| C1 (Q6) | `_confirm_data_change` 7454-7491 | แสดง Profile / ปลายทางในรูปแบบเดิม `Oracle · host / db` แต่ใช้ค่าของ engine ที่จะรันจริง (ไม่มีรหัสผ่าน) |
| C1 (Q5) | `_log_run_context` 7383-7396 | บันทึก Profile / Host ลง Run log จาก snapshot ของ engine ที่ใช้จริง ไม่ใช่จากช่องบนหน้าจอ |
| C2 | `load_script_groups` 3950-3961, `save_script_groups` 3963-3984 | ใช้ `_handle_unreadable_file` (8668) + flag บล็อกการบันทึกแบบเดียวกับ `_jobs_save_blocked` / `_profiles_save_blocked` และสร้าง backup ตามกติกา Q4 |
| H1 | `_refresh_live_ui` 2841-2913 (เงื่อนไข busy ที่ 2846-2849), running banner 2673-2686 | ให้แถบเหลือง + ปุ่ม Stop และ status bar ("Running…") แสดงทุกครั้งที่มีงานรัน รวม Job เดี่ยว (▶) และ list_tables แสดงชื่อ Job เมื่อรัน Job เดี่ยว |
| H1 (Q7) | `list_tables` loading dialog 8289-8307 (`grab_set()` ที่ 8294) | หน้าต่าง Loading ต้องไม่ขวางการกด Stop: เพิ่มปุ่ม Stop ในหน้าต่าง Loading หรือเลิก grab หน้าต่างหลัก (developer/architect เลือกได้ 1 วิธี) |
| H1 | `README.md` บรรทัด 47, 51 | อัปเดตให้ตรงพฤติกรรมใหม่ |
| H2 | binding `<Control-Return>` 2660-2665 | เปรียบเทียบ state ด้วย `str(self.execute_btn["state"])` |

#### Out of scope

- บัคอื่นนอกจาก 4 ข้อนี้ แม้จะเจอระหว่างแก้ (ให้รายงานหัวหน้า ห้ามแก้เอง) เช่น loading dialog ของ SQL Editor (`_create_loading_dialog_with_retry` 6122, `grab_set` 6129) ที่อาจขวาง Stop เช่นกัน — ไม่อยู่ในการตัดสินใจ Q7 ซึ่งระบุเฉพาะ list_tables
- การเปลี่ยนวิธี cancel query ของแต่ละ driver (`stop_running_queries` 7405)
- การปรับดีไซน์ UI / ข้อความอื่นที่ไม่เกี่ยวกับ 4 บัค
- การทดสอบเชื่อมต่อในหน้า New/Edit Profile (10340-10347) ซึ่งใช้ engine ชั่วคราวของตัวเอง ไม่กระทบ `self.engine`
- การ refactor ส่วนอื่นของไฟล์

### 3. User stories

- **US-1 (C1)**: ในฐานะผู้ใช้ที่กำลังรัน Run All / Export / Job เดี่ยว ฉันต้องการให้ Job ทุกตัวในงานนั้นรันบนฐานข้อมูลที่ต่อไว้ตอนกดเริ่ม และแอปไม่ยอมให้กด Connect / เปลี่ยน / แก้ / ลบ / Import Profile หรือเริ่มงานอื่นซ้อน เพื่อไม่ให้ UPDATE/DELETE ไปโดนฐานข้อมูลผิดตัว
- **US-2 (C1)**: ในฐานะผู้ใช้ที่กำลังจะรันคำสั่งแก้ข้อมูล ฉันต้องการให้หน้ายืนยันและ Run log แสดงปลายทางที่จะรันจริง เพื่อตัดสินใจและตรวจย้อนหลังได้ถูกต้อง
- **US-3 (C2)**: ในฐานะผู้ใช้ Script Groups ฉันต้องการให้กลุ่มเดิมไม่หายเมื่อแอปอ่านไฟล์ไม่ได้ชั่วคราว (เช่น OneDrive sync ล็อกไฟล์) เพื่อกู้คืนได้
- **US-4 (H1)**: ในฐานะผู้ใช้ที่รัน Job เดี่ยวด้วยปุ่ม ▶ หรือเปิดรายการ Table ฉันต้องการเห็นแถบกำลังรัน (พร้อมชื่อ Job) และกด Stop ได้ เพื่อยกเลิก query ที่รันนานหรือรันผิด
- **US-5 (H2)**: ในฐานะผู้ใช้ ฉันต้องการให้ `Ctrl+Enter` ทำงานเหมือนปุ่ม Run คือรันไม่ได้เมื่อปุ่มถูกปิด เพื่อไม่ให้มี SQL ซ้อนขึ้นมาระหว่างงานอื่นรันอยู่

### 4. Acceptance criteria

คำว่า "มีงานรันอยู่" ในหัวข้อนี้หมายถึง `_is_query_running()` คืนค่า True หรือ `_running_job_ids` ไม่ว่าง หรือปุ่ม Tables (`inspect_btn`) แสดง "Loading"

คำว่า "แจ้งใน Execution Logs" หมายถึงเขียนข้อความเหตุผลลง `results_text` (Execution Logs) **ไม่มี popup** (`messagebox` / `ui_dialog` ต้องไม่ถูกเรียก)

ช่อง "วิธีทดสอบ":
- **unittest** = ทดสอบได้ด้วย `python -m unittest` โดยใช้ stub object (`DatabaseConnectorGUI.__new__` หรือ `type("Stub", (), {})()`) + `unittest.mock.patch` + SQLite in-memory/ไฟล์ใน `tempfile` ตามแนวทาง test เดิมใน `tests/test_database_connect_gui_core.py` ไม่ต้องเปิดหน้าต่าง Tk และไม่ต้องต่อฐานข้อมูลจริง
- **Manual/GUI** = ต้องเปิดแอปและกดเอง (หรือต้องใช้ฐานข้อมูลจริง เช่น Oracle cancel)

#### C1 — ห้ามสลับฐานข้อมูลระหว่างรัน

| AC | Given / When / Then | วิธีทดสอบ |
|---|---|---|
| AC-1 | **Given** มีงานรันอยู่ และ `self.engine` คือ engine A **When** เรียก `connect_database()` (เช่นผ่านปุ่ม Retry ของ Connection Error หรือทางอื่นที่ไม่ใช่ปุ่มที่ถูกปิด) **Then** ไม่มีการเรียก `create_engine`, `self.engine` ยังเป็น A (object เดิม), A ไม่ถูก `dispose()` และแจ้งใน Execution Logs ว่าต้องรอให้งานเสร็จหรือกด Stop ก่อน (ไม่มี popup) | unittest |
| AC-2 | **Given** ไม่มีงานรันอยู่ **When** เรียก `connect_database()` ด้วยข้อมูลถูกต้อง (patch `create_engine` ให้คืน SQLite engine) **Then** ทำงานเหมือนเดิม คือ `self.engine` เปลี่ยนเป็น engine ใหม่ | unittest |
| AC-3 | **Given** มีงานรันอยู่ Profile ที่โหลดอยู่คือ P1 **When** `on_profile_selected` ถูกเรียกขณะ combobox แสดง P2 **Then** `load_profile_data` ไม่ถูกเรียก, combobox กลับไปแสดง P1, ช่องเชื่อมต่อ/SQL Editor/รายการ Job ไม่เปลี่ยน, `self.engine` ไม่เปลี่ยน และแจ้งใน Execution Logs (ไม่มี popup) | unittest |
| AC-4 | **Given** ไม่มีงานรันอยู่ **When** เลือก Profile อื่น **Then** โหลด Profile ใหม่ได้ตามเดิม (`load_profile_data` ถูกเรียกด้วยชื่อ Profile ใหม่) | unittest |
| AC-5 | **Given** Export Excel กำลังรันอยู่ (`export_excel_btn` แสดง "Exporting") **When** เรียก `run_job(job)` **Then** ไม่เริ่ม thread ใหม่, ไม่แสดงหน้ายืนยัน, `job` ไม่ถูกเพิ่มใน `_running_job_ids` และแจ้งใน Execution Logs | unittest |
| AC-6 | **Given** มีงานรันอยู่ (ประเภทใดก็ได้ รวมถึง Job เดี่ยวอีกตัวจาก ▶ ของการ์ดอื่น) **When** เรียก `run_job`, `run_selected_job` (รวม Run Group), `export_jobs_to_excel` หรือ `execute_query` **Then** ไม่มีงานใหม่เริ่ม (ไม่สร้าง thread, ไม่เปิดหน้ายืนยัน, ไม่เปิด file dialog) และแจ้งใน Execution Logs | unittest |
| AC-7 | **Given** `self.engine` คือ engine B และส่ง engine A (SQLite คนละฐานข้อมูล มีข้อมูลต่างกัน) เข้าไปเป็น engine ของงาน **When** เรียก `read_sql_dataframe` และ `_execute_modification` ด้วย engine A **Then** query รัน/แก้ข้อมูลบน A เท่านั้น B ไม่ถูกแตะ | unittest |
| AC-8 | **Given** test เดิม `ExecuteModificationTests` เรียก `_execute_modification(stub, sql)` โดยไม่ส่ง engine **When** รัน test ชุดเดิม **Then** ยังผ่าน (ถ้าไม่ส่ง engine ให้ใช้ `self.engine` เหมือนเดิม) | unittest |
| AC-9 | **Given** เริ่ม Run All ที่มี 2 Job ขณะ `self.engine` = A **When** หลัง Job ที่ 1 เสร็จ มีการเปลี่ยน `self.engine` เป็น B (จำลองด้วยโค้ดใน test) **Then** Job ที่ 2 ยังรันบน A — ใช้หลักเดียวกันกับ worker ของ `run_job`, `export_jobs_to_excel` และ `_execute_query_background` คือทุก worker ใช้ engine ที่เก็บไว้ตอนเริ่มงาน ไม่อ่าน `self.engine` ใหม่ระหว่างรัน | unittest (patch `threading.Thread` ให้รัน target ทันที และ stub `root.after`) |
| AC-10 | **Given** Connect สำเร็จด้วย Oracle host `host1` port 1521 database/service `SVC` รหัสผ่าน `secret` แล้วช่อง Host บนหน้าจอถูกแก้เป็น `host2` (ไม่ได้ Connect ใหม่) **When** สร้างข้อความปลายทางสำหรับหน้ายืนยันการแก้ข้อมูล **Then** ข้อความเป็นรูปแบบเดิม `Oracle · host1 / SVC` ไม่มี `host2` และไม่มี `secret` — ต้องแยก logic สร้างข้อความปลายทางเป็นฟังก์ชัน/เมธอดที่เรียกได้โดยไม่เปิด dialog | unittest |
| AC-11 | **Given** Connect สำเร็จขณะ Profile = P1 แล้ว combobox ถูกเปลี่ยนเป็น P2 (จำลองใน test) **When** สร้างข้อมูลสำหรับหน้ายืนยัน **Then** Profile ที่แสดงคือ P1 (snapshot ตอน Connect สำเร็จ ผูกกับ engine ที่ใช้รัน) | unittest |
| AC-12 | **Given** งานรันจบแล้ว (สำเร็จ, error หรือกด Stop) **When** ตรวจสถานะ **Then** Connect, เปลี่ยน/แก้/ลบ/Import Profile และปุ่ม Run ทุกตัวกลับมาใช้ได้ (ด้าน logic ทดสอบผ่าน AC-2/AC-4/AC-31 เมื่อไม่มีงานรันอยู่) | unittest (logic) + Manual/GUI (สถานะปุ่ม) |
| AC-13 | **Given** เปิดแอป ต่อฐานข้อมูล แล้วกด Run All / Export / ▶ / Run (SQL Editor) / Tables ด้วย query ที่รันนาน **When** ดูหน้าจอระหว่างรัน **Then** ปุ่ม Connect, combobox Profile, ปุ่มจัดการ Profile (Import / Save / New / Delete), ปุ่ม Run, ▶ ของทุกการ์ด, Run All, Export และ Run Group แสดงเป็นสีเทากดไม่ได้ และเมื่องานจบกลับมาใช้ได้ | Manual/GUI |
| AC-31 | **Given** stub ที่มี widget จำลองของปุ่มทั้งหมดใน AC-13 (บันทึกค่า `state` ที่ถูก `config`) **When** เรียก logic ที่ปรับสถานะปุ่มด้วยสถานะ "มีงานรัน" แล้วตามด้วย "ไม่มีงานรัน" **Then** ครั้งแรกทุกปุ่มเป็น `disabled` ครั้งหลังกลับเป็น `normal` (ยกเว้นปุ่มที่ต้องปิดด้วยเหตุผลอื่น เช่น Run / Tables เมื่อยังไม่ Connect ต้องยังปิดอยู่) — ต้องแยก logic นี้เป็นเมธอดที่ทดสอบได้ | unittest |
| AC-32 | **Given** มีงานรันอยู่ **When** เรียก `import_profiles_dialog()` **Then** ไม่เปิด file dialog, `saved_profiles` และไฟล์ `db_profiles.json` ไม่เปลี่ยน และแจ้งใน Execution Logs | unittest |
| AC-33 | **Given** มีงานรันอยู่ และ Profile ที่ใช้อยู่คือ P1 **When** เรียก `delete_profile()` **Then** ไม่ถามยืนยัน, P1 ยังอยู่ใน `saved_profiles`, ไฟล์ไม่เปลี่ยน และแจ้งใน Execution Logs | unittest |
| AC-34 | **Given** มีงานรันอยู่ **When** เรียก `save_profile_dialog()` (บันทึกทับ/แก้ Profile ที่ใช้อยู่) หรือ `new_profile_dialog()` (ซึ่งจะสลับไป Profile ใหม่หลังสร้าง) **Then** ไม่เปิด dialog, `saved_profiles` ไม่เปลี่ยน, Profile ที่ใช้อยู่ไม่ถูกสลับ และแจ้งใน Execution Logs | unittest |
| AC-35 | **Given** Connect สำเร็จด้วย Profile P1 host `host1` แล้วช่อง Profile/Host บนหน้าจอเปลี่ยนเป็น P2/`host2` **When** เริ่มงานและ `_log_run_context` เขียน Run log **Then** บรรทัด `===== RUN ...` มี `profile=P1` และ `host1` ไม่มี `P2` / `host2` และไม่มีรหัสผ่าน | unittest (patch `_write_run_log`) |

#### C2 — Script Groups ไม่หายเมื่ออ่านไฟล์ไม่ได้

ทดสอบโดยให้ `_script_groups_path()` ชี้ไปที่ไฟล์ในโฟลเดอร์ `tempfile.TemporaryDirectory()` และ patch `messagebox`

| AC | Given / When / Then | วิธีทดสอบ |
|---|---|---|
| AC-14 | **Given** `script_groups.json` เป็น JSON เสีย **When** เรียก `load_script_groups()` **Then** คืน `[]`, เรียก `_handle_unreadable_file` (มีไฟล์ `script_groups_unreadable_<เวลา>.json` เกิดขึ้น) และตั้ง flag บล็อกการบันทึกตามค่าที่ `_handle_unreadable_file` คืน (True เมื่อ copy ไม่สำเร็จ) แบบเดียวกับ `_jobs_save_blocked` | unittest |
| AC-15 | **Given** flag บล็อกการบันทึก Script Groups เป็น True **When** เรียก `save_script_groups()` **Then** ไม่เขียน `script_groups.json` และไม่แตะ `script_groups_backup.json` (เนื้อหาและ mtime เท่าเดิม) และแสดงข้อความ error ว่าไม่บันทึกเพราะอ่านไฟล์ไม่ได้ตอนเปิดแอป (กรณีนี้ใช้ popup ได้แบบเดียวกับ `save_jobs` เพราะไม่ใช่การบล็อกระหว่างรัน) | unittest |
| AC-16 | **Given** มี `script_groups_backup.json` ที่ถูกต้อง และ `script_groups.json` ปัจจุบันเป็น JSON เสีย **When** เรียก `save_script_groups()` (flag ไม่บล็อก) **Then** `script_groups_backup.json` ยังเป็นเนื้อหาเดิม (ไม่ถูกทับด้วยไฟล์เสีย) และ `script_groups.json` เป็นข้อมูลใหม่ | unittest |
| AC-17 | **Given** `script_groups.json` อ่านได้ มีกลุ่ม G1 **When** เรียก `save_script_groups()` 2 ครั้งติดกันในเซสชันเดียว (ครั้งแรกบันทึก G2, ครั้งที่สองบันทึก G3) **Then** หลังครั้งแรก `script_groups_backup.json` มี G1 และหลังครั้งที่สองยังมี G1 (ไม่ถูกทับด้วยไฟล์ที่แอปเพิ่งเขียนเอง) ส่วน `script_groups.json` มี G3 | unittest |
| AC-36 | **Given** ไม่มี `script_groups_backup.json` และ `script_groups.json` อ่านได้ มีกลุ่ม G1 **When** บันทึกครั้งแรกของเซสชัน **Then** สร้าง `script_groups_backup.json` ที่มี G1 / และเมื่อเริ่มเซสชันใหม่ (stub ใหม่ ไม่มีสถานะจากเซสชันก่อน) แล้วบันทึกครั้งแรก backup ถูกอัปเดตเป็นไฟล์ล่าสุดก่อนเซสชันนั้น | unittest |
| AC-18 | **Given** ไม่มีไฟล์ `script_groups.json` **When** เรียก `load_script_groups()` แล้ว `save_script_groups()` **Then** คืน `[]` โดยไม่แสดงคำเตือน ไม่ตั้ง flag บล็อก บันทึกไฟล์ใหม่ได้ และไม่สร้าง backup (ไม่มีไฟล์เดิมให้ backup) | unittest |
| AC-19 | **Given** บันทึกสำเร็จ **When** ตรวจโฟลเดอร์ **Then** ไม่มีไฟล์ `script_groups.json.tmp` ค้าง และ `script_groups.json` อ่านกลับได้เป็นข้อมูลที่บันทึก (key ที่ขึ้นต้นด้วย `_` และ `run_index` ถูกตัดออกเหมือนเดิม) | unittest |

#### H1 — ปุ่ม Stop ต้องแสดงและกดได้ทุกครั้งที่มีงานรัน

ต้องแยก logic ตัดสิน "busy" และข้อความแถบเหลืองของ `_refresh_live_ui` ออกเป็นเมธอดที่เรียกได้โดยไม่ต้องสร้างหน้าต่าง เพื่อให้ทดสอบได้

| AC | Given / When / Then | วิธีทดสอบ |
|---|---|---|
| AC-20 | **Given** `_batch_running` False, ปุ่ม Run ไม่ใช่ "Loading", ปุ่ม Export ไม่ใช่ "Exporting" แต่ `_running_job_ids` มี 1 ตัว (Job เดี่ยวจาก ▶) **When** ตรวจสถานะ busy **Then** busy = True | unittest |
| AC-21 | **Given** มี connection ค้างใน `_active_db_connections` (query กำลังรัน) แต่ flag อื่นเป็น False ทั้งหมด **When** ตรวจสถานะ busy **Then** busy = True | unittest |
| AC-22 | **Given** `inspect_btn` แสดง "Loading" (list_tables) **When** ตรวจสถานะ busy **Then** busy = True | unittest |
| AC-23 | **Given** ไม่มีงานใดรัน **When** ตรวจสถานะ busy **Then** busy = False | unittest |
| AC-24 | **Given** busy เพราะรัน Job เดี่ยวชื่อ `Daily Balance` (ไม่ใช่ batch/export) **When** สร้างข้อความในแถบเหลือง **Then** ข้อความมีชื่อ `Daily Balance` และเวลา `mm:ss` (เช่น `กำลังรัน Job · Daily Balance · 00:05`) / กรณี SQL Editor และ list_tables ใช้ข้อความ fallback เดิม `กำลังรัน SQL · mm:ss` / กรณี Run All และ Export ข้อความเหมือนเดิม | unittest (logic ข้อความ) + Manual/GUI (การแสดงผล) |
| AC-25 | **Given** ต่อ Oracle จริง **When** กด ▶ ของ Job ที่รันนาน **Then** ภายใน ~0.5 วินาทีแถบเหลืองขึ้นพร้อมชื่อ Job และปุ่ม Stop ที่กดได้ status bar แสดง "Running…" กด Stop แล้ว query ถูกยกเลิก (ORA-01013) และแถบหายเมื่องานจบ | Manual/GUI |
| AC-37 | **Given** ต่อฐานข้อมูลที่มี Table จำนวนมาก **When** กดปุ่ม Tables (list_tables) แล้วหน้าต่าง Loading ขึ้น **Then** ผู้ใช้กด Stop ได้ (ปุ่ม Stop ในหน้าต่าง Loading หรือปุ่ม Stop ในแถบเหลืองของหน้าต่างหลักที่ไม่ถูก grab) การกด Stop เรียก `stop_running_queries` และเมื่องานจบ หน้าต่าง Loading ปิด ปุ่ม Tables กลับเป็นปกติ | Manual/GUI |
| AC-38 | **Given** stub ของ list_tables ที่ patch `tk.Toplevel` ให้บันทึกการเรียก **When** เปิดหน้าต่าง Loading **Then** ตรงตามวิธีที่เลือก: ไม่เรียก `grab_set()` หรือมีปุ่ม Stop ที่ผูกกับ `stop_running_queries` และลงทะเบียนผ่าน `_register_stop_button` | unittest (ถ้า stub ได้) มิฉะนั้นครอบคลุมด้วย AC-37 |
| AC-26 | **Given** `README.md` บรรทัด 47 และ 51 **When** แก้เสร็จ **Then** ข้อความตรงกับพฤติกรรมจริง: แถบสีเหลืองขึ้นทุกครั้งที่มี Query / Job รัน รวมปุ่ม ▶ (แสดงชื่อ Job) และกด Stop ได้ระหว่างโหลดรายการ Table และระบุว่าระหว่างรันจะกด Connect / เปลี่ยน Profile / เริ่มงานอื่นไม่ได้ | Manual (review เอกสาร) |

#### H2 — Ctrl+Enter ต้องเคารพสถานะปุ่ม Run

ต้องย้าย lambda ของ binding เป็นเมธอด (เช่น handler ของ `<Control-Return>`) เพื่อให้ทดสอบได้

| AC | Given / When / Then | วิธีทดสอบ |
|---|---|---|
| AC-27 | **Given** `execute_btn["state"]` คืน object ที่ไม่ใช่ `str` แต่ `str()` ได้ `"disabled"` (จำลอง Tcl_Obj) **When** เรียก handler ของ `Ctrl+Enter` **Then** `execute_query` ไม่ถูกเรียก และถ้าสาเหตุคือมีงานรันอยู่ ให้แจ้งใน Execution Logs (ไม่มี popup) | unittest |
| AC-28 | **Given** `execute_btn["state"]` เป็น `"normal"` (ทั้งแบบ str และแบบ object ที่ `str()` ได้ `"normal"`) **When** เรียก handler **Then** `execute_query` ถูกเรียก 1 ครั้ง | unittest |
| AC-29 | **Given** เปิดแอป ระหว่างที่ Run All กำลังรัน (ปุ่ม Run ถูกปิด) **When** กด `Ctrl+Enter` ใน SQL Editor **Then** ไม่มี SQL ใหม่รัน ไม่มีหน้ายืนยัน/Loading/popup ใหม่ และมีข้อความเหตุผลใน Execution Logs | Manual/GUI |

#### Regression

| AC | Given / When / Then | วิธีทดสอบ |
|---|---|---|
| AC-30 | **Given** แก้ครบ 4 บัค **When** รัน `python -m unittest discover -s tests -p "test_*.py"` **Then** test เดิมทั้งหมดและ test ใหม่ผ่าน | unittest |

**สรุปจำนวน AC**: 38 ข้อ (AC-1 ถึง AC-38 เลขเรียงตามหมวด ไม่เรียงตามลำดับในเอกสาร เพื่อไม่ให้เลขเดิมเปลี่ยน)
- unittest ล้วน 30 ข้อ
- unittest + Manual/GUI 3 ข้อ: AC-12, AC-24, AC-38 (AC-38 ถ้า stub ไม่ได้ให้ใช้ AC-37 แทน)
- Manual/GUI ล้วน 5 ข้อ: AC-13, AC-25 (ต้องใช้ Oracle จริง), AC-26, AC-29, AC-37

### 5. ข้อจำกัด / สมมติฐาน

- ไม่มี pytest ใช้ `unittest` + `unittest.mock` เท่านั้น test ต้องไม่เปิดหน้าต่าง Tk และไม่ต่อฐานข้อมูลจริง (ใช้ SQLite ของ SQLAlchemy แทน)
- เพื่อให้ทดสอบได้ ยอมให้แยก logic เล็ก ๆ ออกเป็นเมธอด (busy state, ข้อความแถบเหลือง, สถานะปุ่มระหว่างรัน, handler Ctrl+Enter, ข้อความปลายทางของหน้ายืนยัน/Run log, การส่ง engine ให้ worker) โดยไม่เปลี่ยนพฤติกรรมอื่น
- `read_sql_dataframe` / `_execute_modification` ต้อง backward compatible กับการเรียกแบบเดิม (AC-8)
- **ปลายทางของหน้ายืนยันและ Run log (Q5, Q6)**: `engine.url` ใช้แทนข้อมูลปลายทางไม่ได้ทุกกรณี — SQL Server ใช้ URL `mssql+pyodbc:///?odbc_connect=...` (get_connection_string 6965) ซึ่งไม่มี host ใน URL และ `odbc_connect` มีรหัสผ่านอยู่ข้างใน ดังนั้น "ค่าจาก engine ที่ใช้จริง" ให้หมายถึง snapshot ของ Profile / db_type / user / host / port / database ที่เก็บไว้ **ตอน Connect สำเร็จและผูกกับ engine ตัวนั้น** (ห้ามเก็บรหัสผ่านใน snapshot) ไม่ใช่การ parse ค่าจาก `engine.url`
- `_replace_engine` เรียก `dispose()` กับ engine เก่าได้ แต่ปิดเฉพาะ connection ที่ว่างใน pool connection ที่ worker ใช้อยู่จะยังทำงานต่อจนเสร็จ (ตาม docstring เดิม) เมื่อ Connect ถูกบล็อกระหว่างรันแล้ว กรณีนี้ไม่ควรเกิดอยู่แล้ว
- `_handle_unreadable_file` เดิมคืน True (บล็อก) เฉพาะเมื่อ copy ไฟล์ที่อ่านไม่ได้ไม่สำเร็จ spec นี้ใช้กติกาเดียวกันกับ Saved Jobs / Profiles เพื่อความสม่ำเสมอ
- popup ที่มีอยู่เดิมนอกเหนือจากการบล็อกระหว่างรัน (เช่น "Please connect to database first", error ตอนบันทึกไฟล์) คงไว้ตามเดิม การตัดสินใจ Q2 "ไม่ใช้ popup" ใช้เฉพาะข้อความที่บอกว่าถูกบล็อกเพราะมีงานรันอยู่

### 6. การตัดสินใจ (ผู้ใช้เลือกคำตอบที่แนะนำครบ 8 ข้อ)

| # | เรื่อง | การตัดสินใจ | AC ที่เกี่ยวข้อง |
|---|---|---|---|
| Q1 | งานซ้อนกัน | ห้ามเริ่มงานใหม่ทุกประเภทระหว่างมีงานรัน รวม ▶ ของ Job การ์ดอื่น | AC-5, AC-6 |
| Q2 | วิธีบล็อกบน UI | ปิดปุ่มเป็นสีเทา ถ้าถูกเรียกทางอื่น (เช่น shortcut) ให้เขียนเหตุผลใน Execution Logs ไม่มี popup | AC-1, AC-3, AC-5, AC-6, AC-13, AC-27, AC-29, AC-31 ถึง AC-34 |
| Q3 | ข้อความแถบเหลือง | รัน Job เดี่ยวให้แสดงชื่อ Job | AC-24, AC-25 |
| Q4 | backup ของ script_groups | สร้าง backup เฉพาะการบันทึกครั้งแรกของแต่ละเซสชัน และเฉพาะเมื่อไฟล์เดิมเป็น JSON ที่อ่านได้ | AC-16, AC-17, AC-18, AC-36 |
| Q5 | Run log | อยู่ใน scope: `_log_run_context` บันทึก Profile/Host จาก snapshot ของ engine ที่ใช้จริง | AC-35 |
| Q6 | รูปแบบปลายทางในหน้ายืนยัน | คงรูปแบบเดิม `Oracle · host / db` แต่ใช้ค่าของ engine ที่ใช้จริง ไม่มีรหัสผ่าน | AC-10, AC-11 |
| Q7 | list_tables | อยู่ใน scope: หน้าต่าง Loading ต้องไม่ขวาง Stop (เพิ่มปุ่ม Stop ในหน้าต่าง Loading หรือเลิก grab หน้าต่างหลัก) | AC-37, AC-38 |
| Q8 | เปลี่ยน Profile ทางอ้อม | อยู่ใน scope: ระหว่างรันห้าม Import Profile และห้ามลบ/แก้ Profile ที่กำลังใช้ | AC-32, AC-33, AC-34 |

---

## Round 2 — Bugfix: H3, M9, M3, H4

> สถานะ: **ผู้ใช้อนุมัติแล้ว** (จุดอนุมัติที่ 1) — ผู้ใช้เลือกคำตอบที่แนะนำครบทั้ง 8 ข้อ ดูหัวข้อ R2-6 "การตัดสินใจ"
> Round 1 commit แล้วที่ `2f4779b` — Round 2 ใช้เลข AC ของตัวเอง `R2-AC-x` และคำถาม `R2-Q-x` ไม่ชนกับ Round 1
> ไฟล์ที่เกี่ยวข้อง: `database_connect_gui.py` เท่านั้น (เลขบรรทัดตรวจกับโค้ดหลัง commit `2f4779b` แล้ว)

### R2-1. เป้าหมาย

แก้บัค 4 ข้อจากรายงาน bug-hunter ที่ทำให้ SQL ที่รันจริงต่างจากที่ผู้ใช้ตั้งใจ:

- **H3 (High)**: "Auto WHERE (Excel column)" ต่อ `AND col IN (...)` ผิดตำแหน่ง ทำให้ UPDATE/DELETE กระทบแถวมากเกินไป (เพราะ precedence ของ OR) หรือ SQL เสีย (AND ไปอยู่หลัง ORDER BY / หลัง alias ของ subquery)
- **M9 (Medium)**: Reset Parameter (detected mode) เมื่อเอาค่าออกจนหมด จะลบเงื่อนไขทิ้งรวมถึงคำว่า WHERE เช่น `DELETE FROM acct WHERE acc_no IN ('1001','1002')` กลายเป็น `DELETE FROM acct` ซึ่งถ้ารันจะลบทั้งตาราง
- **M3 (Medium)**: ตัวแยก statement ไม่เคยเจอบรรทัด `/` ของ Oracle (marker `\x1e` เป็น whitespace จึงถูกข้ามก่อน) ทำให้ SQL หลาย statement ถูกนับเป็น 1 statement แล้วหลุดการกัน multi-statement และ Export ตัดสินใจ skip ผิด
- **H4 (High)**: ข้อมูล table variable (`mail_table_data.json`) ถูกโหลดครั้งเดียวทั้งเซสชัน เมื่อ Mail Notify Tool export ข้อมูลใหม่ Run / Export ยังใช้ค่าเก่า

ผู้ได้ประโยชน์: ผู้ใช้ที่ใช้ Excel parameter / Reset Parameter / table variable และผู้ใช้ Oracle ที่เขียน script คั่นด้วย `/`

### R2-2. ขอบเขต

#### In scope

| บัค | ตำแหน่งในโค้ด (ยืนยันแล้ว) | สิ่งที่ต้องแก้ |
|---|---|---|
| H3 | `_append_where_conditions` 10877-10891 (ใช้ regex `\bWHERE\b` ทั้งข้อความที่ 10886) เรียกจาก `_render_sql_template` 10939, ตัวเลือก "Auto WHERE (Excel column)" 11585 | หาตำแหน่งด้วย `_scan_sql` เฉพาะ depth 0 ของ statement หลัก, ครอบเงื่อนไข WHERE เดิมด้วยวงเล็บ, แทรกก่อน GROUP BY / HAVING / ORDER BY ฯลฯ และ raise `ValueError` เมื่อไม่แน่ใจแทนการเดา |
| M9 | `_remove_sql_condition` 11035-11050, `_reset_sql_in_lists` 11052-11066 เรียกจาก `show_reset_parameter_dialog` (preview 11293-11299, apply 11416-11421) | เมื่อเอาค่าออกจนหมด แทนเงื่อนไข `IN (...)` นั้นด้วย `1=0` ทุกกรณี (R2-Q-4) ส่วน `NOT IN (...)` ไม่แก้ SQL และแจ้งเหตุผล (R2-Q-5) |
| M3 | `_SQL_SLASH_MARK = "\x1e"` 305, `_scan_sql` 319-392 (เช็ก `isspace()` ที่ 329 ก่อนเช็ก marker ที่ 368), `split_sql_statements` 410-432 | ให้บรรทัด `/` ของ Oracle ถูกนับเป็นตัวคั่น statement จริง (เช็ก marker ก่อน `isspace()` หรือเปลี่ยน marker เป็นอักขระที่ไม่ใช่ whitespace) |
| H4 | `_current_table_data_tables` 7358-7372 เรียกจาก `_prepare_run_sql` 7325 และ Export (`export_tables` ใน `export_jobs_to_excel`) | เช็ก `os.path.getmtime` ทุกครั้งที่เตรียมรัน ถ้าไฟล์เปลี่ยนให้โหลดใหม่ และเขียนเวลาของข้อมูลที่ใช้ลง Execution Logs |

#### Out of scope

- บัคอื่นในรายงาน bug-hunter ที่ไม่ใช่ H3 / M9 / M3 / H4
- พฤติกรรม Reset ในโหมด tracked Excel parameter (`build_reset_values` 11280-11288 ที่คืน placeholder เมื่อค่าหมด) — M9 ครอบเฉพาะ detected mode
  - **อัปเดต (ผู้ใช้อนุมัติภายหลัง, R2-T-fix):** ขยาย M9 ไปครอบ tracked mode เฉพาะคอลัมน์ Auto WHERE: เมื่อ Reset จนไม่เหลือค่าใน UPDATE / DELETE ให้ render เงื่อนไขนั้นเป็น `1=0` (ไม่มี WHERE เดิม → `WHERE 1=0`) แทนการทิ้งเงื่อนไข เพื่อไม่ให้กระทบแถวมากกว่าเดิม; SELECT คงพฤติกรรมเดิม (ทิ้งเงื่อนไข) parameter ชนิดอื่นยังกลับเป็น placeholder เหมือนเดิม
- ชื่อหัว popup "SQL Parameter Not Found" (12045) ที่จะแสดงข้อความ error ของ H3 — ใช้ของเดิม
- การแทนที่ `/` ที่อยู่ในบรรทัดเดียวภายใน string literal (`_SQL_SLASH_LINE_RE.sub` 415) — ปัจจุบัน scanner ข้าม string ทั้งก้อนอยู่แล้ว ไม่ต้องแก้
- Auto-sync ของ table data (`check_and_sync_table_data` 5906-5945) — ไม่เปลี่ยนพฤติกรรม นอกจากใช้ค่า `last_table_data_mtime` ร่วมกัน (R2-AC-27)
- การรองรับ Auto WHERE กับ statement ประเภทอื่นนอกจาก SELECT / UPDATE / DELETE (รวม WITH ... SELECT/UPDATE/DELETE) — ประเภทอื่นให้ raise `ValueError`

### R2-3. User stories

- **R2-US-1 (H3)**: ในฐานะผู้ใช้ที่โหลด Excel แล้วเลือก "Auto WHERE (Excel column)" ฉันต้องการให้เงื่อนไข IN ที่เพิ่มเข้าไปจำกัดแถวเพิ่มจากเงื่อนไขเดิมจริงๆ และอยู่ในตำแหน่งที่ SQL ยังถูกต้อง ถ้าแอปไม่แน่ใจให้บอกฉันแทนการเดา เพื่อไม่ให้ UPDATE/DELETE โดนแถวเกิน
- **R2-US-2 (M9)**: ในฐานะผู้ใช้ที่ Reset Parameter ฉันต้องการให้การเอาค่าออกจนหมดไม่ทำให้ UPDATE/DELETE กลายเป็นคำสั่งที่ไม่มี WHERE เพื่อไม่เผลอลบ/แก้ทั้งตาราง
- **R2-US-3 (M3)**: ในฐานะผู้ใช้ Oracle ที่คั่น statement ด้วยบรรทัด `/` ฉันต้องการให้แอปรู้ว่ามีหลาย statement และจัดประเภทความเสี่ยงถูกต้อง เพื่อให้ตัวกัน multi-statement / หน้ายืนยัน / Export skip ทำงาน
- **R2-US-4 (H4)**: ในฐานะผู้ใช้ table variable ฉันต้องการให้ Run / Export ใช้ข้อมูลล่าสุดจากไฟล์ที่ Mail Notify Tool export และเห็นใน log ว่าใช้ข้อมูลเวลาไหน เพื่อไม่รันด้วยค่าเก่า

### R2-4. Acceptance criteria

ช่อง "วิธีทดสอบ" ใช้ความหมายเดียวกับ Round 1 (**unittest** = `unittest` + `unittest.mock` + stub + SQLite/tempfile ไม่เปิด Tk ไม่ต่อฐานข้อมูลจริง; **Manual/GUI** = เปิดแอปกดเอง)

"เทียบแบบ normalize whitespace" = เทียบหลังแทน whitespace ติดกันด้วยช่องว่างเดียว เพื่อไม่ผูก test กับการขึ้นบรรทัด

#### H3 — Auto WHERE ต่อเงื่อนไขอย่างปลอดภัย

ทดสอบเรียก `DatabaseConnectorGUI._append_where_conditions(sql, [(column, sql_values)])` ตรง (เป็น staticmethod)

| AC | Given / When / Then | วิธีทดสอบ |
|---|---|---|
| R2-AC-1 | **Given** `UPDATE acct SET flag='Y' WHERE status='A' OR status='B'` และเงื่อนไข `(ACC_NO, "'1','2'")` **When** ต่อเงื่อนไข **Then** เงื่อนไขเดิมถูกครอบวงเล็บ ผลเทียบแบบ normalize whitespace เท่ากับ `UPDATE acct SET flag='Y' WHERE (status='A' OR status='B') AND ACC_NO IN ('1','2')` | unittest |
| R2-AC-2 | **Given** ตาราง SQLite `acct(acc_no, status, flag)` มีแถว (1,A), (2,B), (3,A), (4,B) **When** รัน SQL ที่ได้จาก R2-AC-1 **Then** มีแค่แถว acc_no 1 และ 2 ที่ flag='Y' (แถว 3 ซึ่ง status='A' ต้องไม่ถูกแก้) | unittest |
| R2-AC-3 | **Given** `SELECT * FROM t WHERE a = 1 ORDER BY a` **When** ต่อเงื่อนไข `(C, "'x'")` **Then** ได้ `SELECT * FROM t WHERE (a = 1) AND C IN ('x') ORDER BY a` (normalize whitespace) — ORDER BY ยังอยู่ท้ายสุด | unittest |
| R2-AC-4 | **Given** `SELECT * FROM t ORDER BY a` (ไม่มี WHERE) **When** ต่อเงื่อนไข **Then** ได้ `SELECT * FROM t WHERE C IN ('x') ORDER BY a` (normalize whitespace) | unittest |
| R2-AC-5 | **Given** `SELECT a, COUNT(*) FROM t WHERE x = 1 GROUP BY a HAVING COUNT(*) > 1` **When** ต่อเงื่อนไข **Then** เงื่อนไขใหม่อยู่ก่อน `GROUP BY` และ HAVING ไม่ถูกแตะ: `... WHERE (x = 1) AND C IN ('x') GROUP BY a HAVING COUNT(*) > 1` | unittest |
| R2-AC-6 | **Given** `SELECT * FROM (SELECT * FROM t WHERE x = 1) s` (WHERE อยู่ใน subquery เท่านั้น) **When** ต่อเงื่อนไข **Then** subquery ไม่เปลี่ยน และได้ WHERE ใหม่ที่ระดับนอก: `SELECT * FROM (SELECT * FROM t WHERE x = 1) s WHERE C IN ('x')` | unittest |
| R2-AC-7 | **Given** `SELECT * FROM t WHERE id IN (SELECT id FROM u WHERE y = 2)` **When** ต่อเงื่อนไข **Then** ได้ `SELECT * FROM t WHERE (id IN (SELECT id FROM u WHERE y = 2)) AND C IN ('x')` | unittest |
| R2-AC-8 | **Given** SQL ที่มีคำว่า WHERE อยู่ใน string หรือ comment เท่านั้น เช่น `SELECT 'WHERE' AS w FROM t -- WHERE x` **When** ต่อเงื่อนไข **Then** ถือว่าไม่มี WHERE: ผลมี WHERE ใหม่ที่ไม่อยู่ใน comment (ตรวจด้วย `_scan_sql` ว่ามี token word `WHERE` ที่ depth 0 และตามด้วย `C IN`) | unittest |
| R2-AC-9 | **Given** SQL ลงท้ายด้วย `;` หรือบรรทัด `/` ของ Oracle **When** ต่อเงื่อนไข **Then** เงื่อนไขอยู่ก่อน terminator และ terminator ยังอยู่ท้ายสุด (เช่น `SELECT * FROM t;` → `SELECT * FROM t WHERE C IN ('x');`) | unittest |
| R2-AC-10 | **Given** 2 เงื่อนไข `(C1, "'a'")`, `(C2, "'b'")` กับ `DELETE FROM t WHERE x = 1` **When** ต่อเงื่อนไข **Then** ได้ `DELETE FROM t WHERE (x = 1) AND C1 IN ('a') AND C2 IN ('b')` และมีคำว่า WHERE ที่ depth 0 แค่ 1 ครั้ง | unittest |
| R2-AC-11 | **Given** `WITH x AS (SELECT * FROM u WHERE k = 1) SELECT * FROM x` **When** ต่อเงื่อนไข **Then** WHERE ใน CTE ไม่ถูกนับ และได้ `... SELECT * FROM x WHERE C IN ('x')` | unittest |
| R2-AC-12 | **Given** SQL ที่ไม่แน่ใจตำแหน่ง: มี `UNION` / `INTERSECT` / `EXCEPT` / `MINUS` ที่ depth 0, มีหลาย statement, เป็น INSERT / MERGE / PL/SQL block, หรือวงเล็บไม่ครบคู่ **When** ต่อเงื่อนไข **Then** raise `ValueError` ที่มีข้อความบอกเหตุผล และไม่คืน SQL ที่แก้แล้ว (R2-Q-1, R2-Q-2) | unittest |
| R2-AC-13 | **Given** `_render_sql_template` ได้ `ValueError` จาก R2-AC-12 **When** ผู้ใช้กด Apply ในหน้าต่าง Excel Import **Then** SQL Editor ไม่เปลี่ยน, `_excel_parameter_values` กลับเป็นค่าก่อนหน้า และขึ้นข้อความเตือน (ใช้ flow เดิมที่ 12040-12046) | unittest (เรียก `_render_sql_template` กับ stub ให้เห็นว่า raise) + Manual/GUI (popup และ Editor) |
| R2-AC-14 | **Given** `conditions` ว่าง **When** ต่อเงื่อนไข **Then** คืน SQL เดิมทุกตัวอักษร / **Given** `SELECT * FROM t` ธรรมดา **Then** ได้ `SELECT * FROM t WHERE C IN ('x')` (normalize whitespace) เหมือนเดิม | unittest |

#### M9 — Reset Parameter ห้ามทำให้ UPDATE/DELETE ไม่มี WHERE

ทดสอบเรียก `DatabaseConnectorGUI._reset_sql_in_lists(sql, _detect_sql_in_lists(sql), {0: set(tokens)})` ตรง (classmethod) — กติกาตาม R2-Q-4 (A): `IN (...)` ที่ค่าถูกเอาออกจนหมดถูกแทนด้วย `1=0` ทุกประเภท statement ทุกตำแหน่ง และ R2-Q-5: `NOT IN (...)` ที่ค่าหมดให้ raise `ValueError` ไม่แก้ SQL

| AC | Given / When / Then | วิธีทดสอบ |
|---|---|---|
| R2-AC-15 | **Given** `DELETE FROM acct WHERE acc_no IN ('1001','1002')` **When** Reset เอาออกทั้ง `'1001'` และ `'1002'` **Then** ได้ `DELETE FROM acct WHERE 1=0` (normalize whitespace) ไม่ใช่ `DELETE FROM acct` | unittest |
| R2-AC-16 | **Given** ตาราง SQLite `acct` มี 3 แถว **When** รัน SQL ที่ได้จาก R2-AC-15 และกรณีเดียวกันกับ `UPDATE acct SET flag='Y' WHERE acc_no IN ('1001')` **Then** ไม่มีแถวถูกลบ/แก้ (0 rows affected) | unittest |
| R2-AC-17 | **Given** `DELETE FROM acct WHERE status='A' AND acc_no IN ('1001')` **When** Reset เอาออกจนหมด **Then** ได้ `... WHERE status='A' AND 1=0` และรันบน SQLite ลบ 0 แถว (ไม่ใช่ลบทุกแถว status='A') | unittest |
| R2-AC-18 | **Given** `SELECT * FROM acct WHERE acc_no IN ('1001')` **When** Reset เอาออกจนหมด **Then** ได้ `SELECT * FROM acct WHERE 1=0` (SELECT ก็ใช้ `1=0` เหมือนกัน คืน 0 แถว) | unittest |
| R2-AC-19 | **Given** `SELECT * FROM acct WHERE acc_no IN ('1001','1002','1003')` **When** Reset เอาออกแค่ `'1002'` **Then** ได้ `... IN ('1001', '1003')` เหมือนเดิม (ไม่กระทบกรณีเหลือค่า) | unittest |
| R2-AC-20 | **Given** `DELETE FROM acct WHERE status='A' OR acc_no IN ('1001')` **When** Reset เอาออกจนหมด **Then** SQL ที่ได้เมื่อรันบน SQLite ลบเฉพาะแถว status='A' (ผลเท่ากับเงื่อนไข `status='A'`) | unittest |
| R2-AC-21 | **Given** `DELETE FROM acct WHERE acc_no NOT IN ('1001')` **When** Reset เอาออกจนหมด **Then** raise `ValueError` ที่มีข้อความบอกเหตุผล (NOT IN ว่างแปลว่า "ทุกแถว") และไม่คืน SQL ที่แก้แล้ว | unittest |
| R2-AC-22 | **Given** เปิดหน้าต่าง Reset Parameter (detected mode) กับ `DELETE FROM acct WHERE acc_no IN ('1001')` **When** เลือกเอาค่าออกจนหมด **Then** preview กับ SQL ที่ใส่ลง Editor หลังกด Apply ตรงกัน และไม่มี DELETE ที่ไม่มี WHERE / ถ้าถูกปฏิเสธ หน้าต่างแสดงเหตุผลและ Editor ไม่เปลี่ยน | Manual/GUI |

#### M3 — บรรทัด `/` ของ Oracle เป็นตัวคั่น statement

| AC | Given / When / Then | วิธีทดสอบ |
|---|---|---|
| R2-AC-23 | **Given** `'BEGIN NULL; END;\n/\nBEGIN NULL; END;\n/'` **When** เรียก `split_sql_statements` **Then** ได้ 2 statement คือ `['BEGIN NULL; END;', 'BEGIN NULL; END;']` | unittest |
| R2-AC-24 | **Given** `'SELECT 1 FROM dual\n/\nDELETE FROM t\n/'` **When** เรียก `assess_sql` **Then** `statement_count == 2`, `risk is SqlRisk.DATA_CHANGE` และ `is_select_query` คืน False (Export จะ skip ไม่รัน) | unittest |
| R2-AC-25 | **Given** job ที่ query เป็น SQL ใน R2-AC-24 **When** เรียก `_prepare_run_sql` (stub แบบ `PrepareRunSqlTests`) **Then** คืน `None` และ error มีข้อความ "more than one" | unittest |
| R2-AC-26 | **Given** กรณีขอบ 4 แบบ: (1) `'SELECT * FROM dual\n/'` (2) `'SELECT 4 / 2 FROM dual'` (หาร ไม่ใช่ตัวคั่น) (3) `'SELECT 1 FROM dual\n  /  \nSELECT 2 FROM dual'` (บรรทัด `/` มีช่องว่างรอบ) (4) `"SELECT 'a\n/\nb' FROM dual"` (`/` อยู่ใน string) **When** เรียก `split_sql_statements` / `assess_sql` **Then** ได้ 1, 1, 2 และ 1 statement ตามลำดับ (กรณี 1 ยังเป็น READ_ONLY) และข้อความ statement ที่คืนเป็นข้อความต้นฉบับ ไม่มีอักขระ marker หลุดออกมา | unittest |

#### H4 — โหลด table data ใหม่เมื่อไฟล์เปลี่ยน

ทดสอบด้วย stub ที่ `table_data_file` ชี้ไปที่ไฟล์ใน `tempfile.TemporaryDirectory()` เปลี่ยนเวลาไฟล์ด้วย `os.utime` เพื่อไม่ต้องรอ

| AC | Given / When / Then | วิธีทดสอบ |
|---|---|---|
| R2-AC-27 | **Given** ไฟล์มี `{"timestamp": "T1", "tables": {"t": {"column_data": {"c": ["111"]}}}}` และเรียก `_current_table_data_tables()` ครั้งแรกแล้ว **When** เขียนไฟล์ใหม่เป็นค่า `["222", "333"]` (timestamp T2, mtime ใหม่กว่า) แล้วเรียกอีกครั้ง **Then** ได้ค่าใหม่ `["222", "333"]`, `loaded_table_data` เป็นข้อมูลใหม่ และ `last_table_data_mtime` อัปเดตเป็น mtime ใหม่ (Auto-sync จะไม่โหลดซ้ำ) | unittest |
| R2-AC-28 | **Given** ไฟล์เดียวกับ R2-AC-27 **When** เรียก `_prepare_run_sql` กับ `SELECT * FROM a WHERE c IN ({TABLE_T_C})` 2 ครั้ง โดยเปลี่ยนไฟล์ระหว่างครั้ง **Then** ครั้งแรกได้ `IN ('111')` ครั้งที่สองได้ `IN ('222', '333')` (หรือรูปแบบที่ `render_table_variables` สร้าง) | unittest |
| R2-AC-29 | **Given** ไฟล์ไม่เปลี่ยน (mtime เท่าเดิม) **When** เรียก `_current_table_data_tables()` ซ้ำ **Then** ไม่เปิดไฟล์อ่านซ้ำ (patch `open` / นับการอ่าน) และได้ข้อมูลเดิม | unittest |
| R2-AC-30 | **Given** โหลดข้อมูลไปแล้ว แล้วไฟล์ถูกเขียนใหม่เป็น JSON เสีย (mtime ใหม่) **When** เตรียมรัน **Then** ไม่ใช้ข้อมูลเก่า: `_current_table_data_tables()` คืน `None` ทำให้ `_prepare_run_sql` คืน `None` และแจ้ง error (ให้ลองใหม่) ไม่รัน | unittest |
| R2-AC-31 | **Given** โหลดข้อมูลไปแล้ว แล้วไฟล์ถูกลบ **When** เตรียมรัน **Then** `_current_table_data_tables()` คืน `None`, `_prepare_run_sql` คืน `None` และไม่รันด้วยข้อมูลเก่า | unittest |
| R2-AC-32 | **Given** SQL มี table variable และเตรียมรันสำเร็จ **When** ดู Execution Logs (`results_text`) **Then** มีบรรทัดบอกเวลาของข้อมูลที่ใช้ ได้แก่ค่า `timestamp` ใน JSON (ถ้ามี) และเวลาแก้ไขไฟล์ (mtime) และมีบรรทัดนี้ทุกครั้งที่รันด้วย table variable ไม่ใช่เฉพาะตอนโหลดไฟล์ใหม่ (เรียก `_prepare_run_sql` 2 ครั้งโดยไฟล์ไม่เปลี่ยน ต้องมี 2 บรรทัด) | unittest (`_FakeText`) |
| R2-AC-33 | **Given** ใช้แอปจริง Auto-sync ปิด **When** Run job ที่มี `{TABLE_...}` → ให้ Mail Notify Tool export ค่าใหม่ → Run อีกครั้ง และ Export Excel **Then** ครั้งที่สองและ Export ใช้ค่าใหม่ และ log แสดงเวลาข้อมูลใหม่ | Manual/GUI |

#### Regression

| AC | Given / When / Then | วิธีทดสอบ |
|---|---|---|
| R2-AC-34 | **Given** แก้ครบ 4 บัค **When** รัน `python -m unittest discover -s tests -p "test_*.py"` **Then** test ของ Round 1, test เดิมทั้งหมด และ test ใหม่ผ่าน (fixture `PrepareRunSqlTests.make_stub` ปรับให้เขียนไฟล์จริงได้ตาม R2-Q-7 ดูข้อจำกัด) | unittest |

**สรุปจำนวน AC Round 2**: 34 ข้อ
- unittest ล้วน 31 ข้อ
- unittest + Manual/GUI 1 ข้อ: R2-AC-13
- Manual/GUI ล้วน 2 ข้อ: R2-AC-22, R2-AC-33
- AC ที่อิงการตัดสินใจ: R2-AC-12 (R2-Q-1, R2-Q-2), R2-AC-1/3/5/7/10 (R2-Q-3), R2-AC-15 ถึง 18 (R2-Q-4), R2-AC-21 (R2-Q-5), R2-AC-30 (R2-Q-6), R2-AC-31 (R2-Q-7), R2-AC-32 (R2-Q-8)

### R2-5. ข้อจำกัด / สมมติฐาน

- ใช้ `unittest` เท่านั้น ฟังก์ชันหลักทั้ง 4 ข้อเป็น static/classmethod หรือเรียกผ่าน stub ได้อยู่แล้ว ไม่ต้องเปิด Tk
- H3 ใช้ `_scan_sql` (ตัวเดียวกับ `assess_sql`) เพื่อข้าม string / comment / วงเล็บ ไม่ใช้ regex กับข้อความทั้งก้อน
- H3: caller ทุกตัวของ `_render_sql_template` (11291, 11864, 12041, `reset_single_parameter` 10947) จับ `ValueError` / `Exception` อยู่แล้ว การ raise เพิ่มจึงไม่ทำให้แอปค้าง (preview จะแสดง `-- <error>` ต่อท้าย template)
- H3: รูปแบบผลลัพธ์จะเปลี่ยนจากเดิมเล็กน้อย (มีวงเล็บครอบเงื่อนไขเดิมเสมอ) ผู้ใช้ที่เคยเห็น SQL แบบเดิมจะเห็นวงเล็บเพิ่ม
- M3 เป็นการเปลี่ยนพฤติกรรม: script Oracle ที่มีหลาย block คั่นด้วย `/` ซึ่งเดิมผ่านตัวกัน (และส่งไป driver เป็นก้อนเดียว) จะถูกบล็อกด้วยข้อความ "more than one SQL statement" ตาม `ALLOW_MULTI_STATEMENT_SQL = False` (230) — นี่คือพฤติกรรมที่ตั้งใจของตัวกันอยู่แล้ว
- M3: test เดิม `test_oracle_slash_terminator`, `test_plsql_block_is_one_unknown_statement` และ `StripSqlTerminatorTests` ต้องยังผ่าน (SQL ที่มี `/` ท้ายตัวเดียวยังเป็น 1 statement)
- H4: `loaded_table_data` มาจากไฟล์เท่านั้น (5272, 5938) ไม่มีการแก้ข้อมูลในแอปที่ยังไม่บันทึก การโหลดใหม่จึงไม่ทำให้งานของผู้ใช้หาย
- H4: test เดิม `PrepareRunSqlTests.make_stub` (tests บรรทัด 241-249) ใส่ `loaded_table_data` ไว้ในหน่วยความจำแต่ `table_data_file = "unused.json"` ไม่มีอยู่จริง เมื่อ R2-Q-7 ตัดสินว่าไฟล์หาย = ไม่รัน QA ต้องปรับ fixture ให้เขียนไฟล์จริงใน tempdir — เป็นการปรับ test fixture ไม่ใช่เปลี่ยนสิ่งที่ test ตรวจ

### R2-6. การตัดสินใจ (ผู้ใช้เลือกคำตอบที่แนะนำครบ 8 ข้อ)

| # | บัค | เรื่อง | การตัดสินใจ | AC ที่เกี่ยวข้อง |
|---|---|---|---|---|
| R2-Q-1 | H3 | หาตำแหน่งที่ปลอดภัยไม่ได้ | raise `ValueError` ไม่แก้ SQL และแจ้งผู้ใช้ | R2-AC-12, R2-AC-13 |
| R2-Q-2 | H3 | `UNION` / `INTERSECT` / `EXCEPT` / `MINUS` ที่ระดับนอกสุด | error (ไม่ใส่เงื่อนไขให้ branch ใด) | R2-AC-12 |
| R2-Q-3 | H3 | การครอบวงเล็บ | ครอบเงื่อนไขเดิมด้วยวงเล็บทุกครั้ง แม้มีแต่ AND | R2-AC-1, 3, 5, 7, 10 |
| R2-Q-4 | M9 | เอาค่าออกจาก `IN (...)` จนหมด | ตัวเลือก A: แทนเงื่อนไขนั้นด้วย `1=0` ทุกกรณี (ทุกประเภท statement รวม SELECT ทุกตำแหน่ง) | R2-AC-15 ถึง 18, R2-AC-20, R2-AC-22 |
| R2-Q-5 | M9 | เอาค่าออกจาก `NOT IN (...)` จนหมด | ไม่แก้ SQL raise `ValueError` และแจ้งเหตุผล | R2-AC-21, R2-AC-22 |
| R2-Q-6 | H4 | ไฟล์ table data เปลี่ยนแต่อ่านไม่ได้ | ไม่รัน และแจ้งผู้ใช้ (ไม่ใช้ข้อมูลเก่า) | R2-AC-30 |
| R2-Q-7 | H4 | ไฟล์ table data หายไปหลังโหลดแล้ว | ไม่รัน (ต้องปรับ test fixture ตามข้อจำกัด) | R2-AC-31, R2-AC-34 |
| R2-Q-8 | H4 | log เวลาข้อมูล | บันทึกค่า `timestamp` ใน JSON + mtime ของไฟล์ ทุกครั้งที่รันด้วย table variable | R2-AC-32, R2-AC-33 |

---

## Round 3 — Feature: ปุ่ม Import / Export Groups ที่แถบ Preset ของ Sidebar

> สถานะ: **รออนุมัติ** (จุดอนุมัติที่ 1) — สมมติฐาน R3-A1 ถึง R3-A4 ต้องให้ผู้ใช้ยืนยัน
> ใช้เลข `R3-AC-x`, `R3-A-x`, `R3-Q-x` ไม่ชนกับ Round 1 / 2
> ไฟล์ที่เกี่ยวข้อง: `database_connect_gui.py` (เลขบรรทัดตรวจกับโค้ดปัจจุบันบน branch `ui/remove-duplicate-buttons`)

### R3-1. เป้าหมาย

requirement ผู้ใช้: "ต้องเพิ่ม function ของ 2 ปุ่มที่วงสีแดงไว้ เอามาเพิ่มตรงที่ไฮไลท์สีเขียว"
- ปุ่มที่วงแดง = `⇧  Import Groups` และ `⇩  Export Groups` ในหัวหน้าต่าง Script Groups (`show_script_groups_dialog` 4491, ปุ่มที่ 5007-5008, logic `export_groups` 4835-4897 / `import_groups` 4899-4996 เป็น nested function ที่ผูกกับ `dialog`, `state`, `current_group()`, `refresh_groups()`)
- ตำแหน่งสีเขียว = พื้นที่ว่างในแถบ Preset ด้านล่าง sidebar ของหน้าต่างหลัก ถัดจาก `Preset  💾 Save  📂 Load` (`presets_inner` 2591-2601 ปุ่มสร้างด้วย `_ghost`)

ผู้ได้ประโยชน์: ผู้ใช้ที่ต้องการ backup / ย้าย Script Groups ระหว่างเครื่องหรือระหว่างคน โดยไม่ต้องเปิดหน้าต่าง Script Groups ก่อน

### R3-2. ขอบเขต

#### In scope
- เพิ่มปุ่ม `⇧  Import Groups` และ `⇩  Export Groups` ใน `presets_inner` ต่อจากปุ่ม Load (ลำดับ: Save, Load, Import Groups, Export Groups) ใช้ `_ghost(..., bg=UI["surface"])` แบบเดียวกับ Save / Load
- พฤติกรรมเหมือนปุ่มในหน้าต่าง Script Groups: รูปแบบไฟล์ JSON (`type="script_groups"`, `version=1`, `exported`, `profile`, `groups`), การตัด key ที่ขึ้นต้นด้วย `_` และ `run_index`, การตรวจไฟล์, การจัดการชื่อซ้ำ (Yes = แทนที่ / No = เก็บทั้งคู่โดยตั้งชื่อใหม่ `name (n)` / Cancel = ไม่ import), การตรวจว่าเลือก Profile แล้ว, บรรทัด log `📤 Exported ...` / `📥 Imported ...` ใน `results_text`
- แยก logic ที่ไม่ผูกกับ Tk ออกมาเพื่อใช้ร่วมกันทั้ง dialog และ sidebar (ดู R3-5)

#### Out of scope
- เปลี่ยนรูปแบบไฟล์ export, เพิ่ม version ใหม่, หรือ import/export ข้าม Profile แบบเลือกได้
- ปุ่ม Import/Export ใน dialog เดิม: ไม่ลบ ไม่ย้าย ไม่เปลี่ยนพฤติกรรม (ตาม R3-A1)
- การปิดปุ่มระหว่างมีงานรัน (Script Groups ไม่กระทบ engine / Profile ที่ใช้รัน — ไม่ได้ขอ)
- ปรับดีไซน์อื่นของ sidebar (เช่น ย้ายปุ่ม Preset, เปลี่ยนข้อความ "Preset")

### R3-3. User stories
- **R3-US-1**: ในฐานะผู้ใช้ ฉันต้องการกด Export Groups จาก sidebar ได้ทันที เพื่อ backup กลุ่มทั้งหมดของ Profile ปัจจุบันโดยไม่ต้องเปิดหน้าต่าง Script Groups
- **R3-US-2**: ในฐานะผู้ใช้ ฉันต้องการกด Import Groups จาก sidebar เพื่อนำไฟล์กลุ่มเข้ามาใน Profile ปัจจุบัน ด้วยกติกาชื่อซ้ำเหมือนในหน้าต่าง Script Groups

### R3-4. Acceptance criteria

"วิธีทดสอบ" ความหมายเดียวกับ Round 1 / 2 — unittest ต้องไม่เปิดหน้าต่าง Tk ใช้ stub (`DatabaseConnectorGUI.__new__`) + `unittest.mock.patch` สำหรับ `filedialog` / `messagebox` + `tempfile`

#### Logic ที่ใช้ร่วมกัน (pure helper — ไม่ใช้ Tk)

| AC | Given / When / Then | วิธีทดสอบ |
|---|---|---|
| R3-AC-1 | **Given** กลุ่ม 2 กลุ่มของ Profile `P1` โดย script มี key `_tmp` และ `run_index` **When** สร้าง payload สำหรับ export **Then** ได้ dict ที่มี `type == "script_groups"`, `version == 1`, `exported` (string `YYYY-MM-DD HH:MM:SS`), `profile == "P1"`, `groups` 2 รายการแต่ละรายการมีแค่ `name`, `created`, `scripts` และ script ไม่มี key `_tmp` / `run_index` แต่ key อื่นครบ | unittest |
| R3-AC-2 | **Given** ข้อมูลไฟล์เป็น (a) dict ที่มี `groups` (b) list ของกลุ่มตรง ๆ **When** parse/validate ข้อมูลที่จะ import **Then** ทั้งสองแบบได้ list กลุ่มเดียวกัน และกลุ่มที่ไม่ใช่ dict / ไม่มี `name` / `name` ว่าง / `scripts` ไม่ใช่ list ถูกกรองทิ้ง | unittest |
| R3-AC-3 | **Given** ข้อมูลไม่มี list `groups` หรือมี script ที่ไม่มี `query` **When** parse/validate **Then** raise `ValueError` ที่มีเหตุผล (กรณี script ไม่มี SQL ข้อความมีชื่อกลุ่ม) | unittest |
| R3-AC-4 | **Given** Profile `P1` มีกลุ่ม `G1` อยู่แล้ว และมีกลุ่มของ `P2` ชื่อ `G1` ด้วย **When** merge กลุ่มที่ import ชื่อ `g1` (ตัวพิมพ์ต่าง) และ `G2` เข้า `P1` แบบ replace = True **Then** `G1` เดิมของ `P1` ถูกแทนที่ (เหลือชื่อนี้ใน `P1` เพียงกลุ่มเดียว), `G2` ถูกเพิ่ม, กลุ่มของ `P2` ไม่ถูกแตะ, กลุ่มใหม่มี `profile == "P1"`, `imported` และ `created` (ใช้ของไฟล์ถ้ามี ไม่มีใช้เวลาปัจจุบัน) | unittest |
| R3-AC-5 | **Given** เหมือน R3-AC-4 **When** merge แบบ replace = False **Then** `G1` เดิมยังอยู่ และกลุ่มที่ import ได้ชื่อ `g1 (2)` (ถ้า `g1 (2)` มีแล้วใช้ `(3)` ต่อไป) | unittest |
| R3-AC-6 | **Given** ไฟล์มีชื่อซ้ำกันเอง 2 กลุ่ม (`G1`, `G1`) และ Profile มี `G1` อยู่แล้ว **When** merge แบบ replace = True **Then** กลุ่มเดิมถูกแทนที่ครั้งเดียว กลุ่มที่สองจากไฟล์ได้ชื่อ `G1 (2)` (พฤติกรรมเดียวกับโค้ดเดิม 4970-4979) และ helper คืนชื่อกลุ่มสุดท้ายที่เพิ่ม | unittest |
| R3-AC-7 | **Given** script ที่ import มีค่าที่ไม่ใช่ JSON type (เช่น `Timestamp`) **When** merge **Then** ค่าถูกแปลงเป็น string (`default=str`) และ script ในกลุ่มใหม่เป็น copy (แก้ object ต้นฉบับแล้วไม่กระทบ) | unittest |

#### ปุ่มใน Sidebar

| AC | Given / When / Then | วิธีทดสอบ |
|---|---|---|
| R3-AC-8 | **Given** Profile `P1` มี 2 กลุ่ม **When** เรียก action Export ของ sidebar และ patch `asksaveasfilename` ให้คืน path ใน tempdir **Then** ไม่ถาม "all / only one" (R3-A2), ไฟล์ที่เขียนมี 2 กลุ่มของ `P1` เท่านั้น, ชื่อไฟล์เริ่มต้นเป็น `script_groups_P1_<YYYYmmdd_HHMMSS>.json`, `results_text` มีบรรทัด `📤 Exported 2 group(s), <n> script(s) → <path>` และ messagebox ใช้ `parent` = หน้าต่างหลัก (R3-A4) | unittest |
| R3-AC-9 | **Given** Profile ปัจจุบันไม่มีกลุ่ม **When** กด Export จาก sidebar **Then** แสดง info "This profile has no groups to export" และไม่เปิด file dialog | unittest |
| R3-AC-10 | **Given** ผู้ใช้กด Cancel ใน file dialog (คืน `""`) **When** Export หรือ Import **Then** ไม่มีไฟล์ถูกเขียน, `script_groups` ไม่เปลี่ยน, ไม่มีบรรทัด log | unittest |
| R3-AC-11 | **Given** ยังไม่ได้เลือก Profile (`profile_combo.get() == ""`) **When** กด Import จาก sidebar **Then** แสดง warning "Please select a profile first" และไม่เปิด file dialog | unittest |
| R3-AC-12 | **Given** ไฟล์ import ถูกต้อง มีชื่อชนกับกลุ่มเดิม **When** กด Import จาก sidebar แล้วตอบ Yes / No / Cancel **Then** ผลตรงกับ R3-AC-4 / R3-AC-5 / ไม่เปลี่ยนอะไร ตามลำดับ; กรณี Yes / No เรียก `save_script_groups()` 1 ครั้ง และ `results_text` มีบรรทัด `📥 Imported <n> group(s) from <path>` | unittest |
| R3-AC-13 | **Given** ไฟล์ไม่ใช่ Script Groups ที่ถูกต้อง (JSON เสีย / ไม่มี groups / script ไม่มี SQL) **When** Import จาก sidebar **Then** แสดง error "Not a valid Script Groups file" และ `script_groups` ไม่เปลี่ยน | unittest |
| R3-AC-14 | **Given** ยังไม่เคยเปิดหน้าต่าง Script Groups ในเซสชันนี้ (ไม่มี attribute `script_groups`) **When** กด Import หรือ Export จาก sidebar **Then** โหลด `script_groups` จาก `load_script_groups()` ก่อนใช้ (ไม่ crash และไม่ทับกลุ่มเดิมในไฟล์) | unittest |
| R3-AC-15 | **Given** หน้าต่าง Script Groups เปิดอยู่ **When** Import จาก sidebar สำเร็จ **Then** รายการกลุ่มในหน้าต่างนั้น refresh และเลือกกลุ่มสุดท้ายที่ import (R3-A3) / ถ้าหน้าต่างไม่ได้เปิด ไม่มี error | unittest (logic: ตรวจว่า callback refresh ที่ลงทะเบียนไว้ถูกเรียกด้วยชื่อกลุ่มสุดท้าย) + Manual/GUI |
| R3-AC-16 | **Given** เปิดแอป **When** ดู sidebar ด้านล่าง **Then** เห็นแถวแรก `Preset  💾 Save  📂 Load` และแถวใหม่ใต้ลงมา `⇧ Import Groups  ⇩ Export Groups` (ผู้ใช้เลือกขึ้นแถวใหม่ตาม R3-Q-2) สไตล์ ghost เดียวกับ Save / Load ไม่ล้นหรือถูกตัดที่ความกว้าง sidebar ปกติ | Manual/GUI |

#### Regression

| AC | Given / When / Then | วิธีทดสอบ |
|---|---|---|
| R3-AC-17 | **Given** ปุ่ม Import / Export ในหน้าต่าง Script Groups **When** ใช้งาน **Then** พฤติกรรมเดิมทุกอย่าง (รวมคำถาม all / only selected ตอน Export เมื่อมีมากกว่า 1 กลุ่มและมีกลุ่มที่เลือก, messagebox parent = dialog) | Manual/GUI (+ unittest ของ helper ที่ใช้ร่วมกัน R3-AC-1 ถึง 7) |
| R3-AC-18 | **Given** เพิ่มฟีเจอร์ครบ **When** รัน `python -m unittest discover -s tests -p "test_*.py"` **Then** test เดิมทั้งหมดและ test ใหม่ผ่าน | unittest |

**สรุปจำนวน AC Round 3**: 18 ข้อ — unittest ล้วน 15, unittest + Manual/GUI 2 (R3-AC-15, R3-AC-17), Manual/GUI ล้วน 1 (R3-AC-16)

### R3-5. ข้อจำกัด / สมมติฐาน

**สมมติฐานที่ต้องให้ผู้ใช้ยืนยัน**

| # | สมมติฐาน | ทางเลือกอื่น |
|---|---|---|
| R3-A1 | **เพิ่ม** ปุ่มที่ sidebar โดยปุ่มเดิมในหน้าต่าง Script Groups ยังอยู่ (ไม่ใช่ย้าย) | ย้าย = ลบปุ่มออกจาก dialog |
| R3-A2 | จาก sidebar ไม่มี "กลุ่มที่เลือก" จึง Export **ทุกกลุ่ม** ของ Profile ปัจจุบัน (`profile_combo.get()`) โดยไม่ถาม all / only one | ถามให้เลือกกลุ่มก่อน export |
| R3-A3 | ถ้าหน้าต่าง Script Groups เปิดอยู่ตอน Import จาก sidebar ให้ refresh รายการกลุ่มในหน้าต่างนั้น | ไม่ refresh (ผู้ใช้ต้องปิด-เปิดใหม่) |
| R3-A4 | messagebox / file dialog ที่เรียกจาก sidebar ใช้ `parent` = หน้าต่างหลัก (`self.root`) | — |

**ข้อจำกัด / แนวทางสำหรับ architect**
- ห้ามคัดลอก logic ซ้ำ: แยก `export_groups` / `import_groups` ออกจาก nested function เป็น instance method ที่รับ `parent` (และ callback refresh / ตัวเลือกกลุ่มที่เลือก ถ้ามี) ให้ทั้ง dialog และ sidebar เรียกตัวเดียวกัน และแยก pure helper อย่างน้อย 3 ตัวที่ไม่ใช้ Tk: สร้าง payload export (R3-AC-1), parse/validate ไฟล์ import (R3-AC-2, 3), merge กลุ่มเข้า `script_groups` (R3-AC-4 ถึง 7)
- การ refresh dialog (R3-A3) ต้องไม่อ้าง closure ของ dialog ที่ปิดไปแล้ว — เช่นเก็บ callback refresh ไว้บน instance ตอนเปิด dialog และล้างเมื่อปิด หรือตรวจ `_script_groups_window.winfo_exists()`
- ถ้า `_script_groups_save_blocked` (จาก Round 1 C2) เป็น True การ Import จาก sidebar ต้องเจอการบล็อกแบบเดียวกับใน dialog (ผ่าน `save_script_groups()` ตัวเดิม) — ไม่สร้างทางลัดเขียนไฟล์เอง
- ข้อความปุ่มและข้อความ messagebox ใช้ของเดิม (ภาษาอังกฤษ) เพื่อความสม่ำเสมอ

### R3-6. คำถามที่ยังไม่มีคำตอบ

| # | คำถาม | คำตอบที่แนะนำ |
|---|---|---|
| R3-Q-1 | ยืนยัน R3-A1 ถึง R3-A4 หรือไม่ (โดยเฉพาะ A1: เพิ่ม vs ย้าย) | ยืนยันตามที่เขียน |
| R3-Q-2 | sidebar กว้างพอสำหรับ 4 ปุ่มในแถวเดียวหรือไม่ ถ้าไม่พอจะให้ย่อข้อความ (เช่น `⇧ Import` / `⇩ Export`) หรือขึ้นแถวใหม่ | ใช้ข้อความเต็มก่อน ถ้าล้นให้ย่อเป็น `⇧ Import Groups` → `⇧ Import` พร้อม tooltip (ให้ผู้ใช้ตัดสิน) |
| R3-Q-3 | Export จาก sidebar ตอนยังไม่เลือก Profile (`profile_combo` ว่าง) ควรทำอย่างไร — โค้ดเดิมใน dialog ไม่ได้เช็ก (จะ export กลุ่มที่ `profile` ว่าง ถ้ามี) | เหมือน dialog: ถ้าไม่มีกลุ่มแสดง "no groups to export" |

---

# Round 4 — Bugfix: ป้องกันรันผิด Profile และ Export เกินขีดจำกัด Excel

> ใช้เลข `R4-AC-x` และ `R4-Q-x` แยกจาก Round ก่อนหน้า
> ขอบเขตจำกัดเฉพาะ 2 finding ที่ผู้ใช้อนุมัติ: connection Profile ไม่ตรงกับ Profile ที่เลือก และ Excel export ตัดแถวเกินขีดจำกัดแล้วรายงานสำเร็จ

### R4-1. เป้าหมาย

แก้ความเสี่ยงที่ผู้ใช้เลือก Profile B แต่ engine / `_run_target` ยังชี้ไป Profile A ทำให้ Run Job, Run All หรือ Export ใช้ฐานข้อมูล A โดยผู้ใช้เข้าใจว่าเป็น B และแก้การ Export ที่ปัจจุบันตัด DataFrame เหลือ 1,048,575 แถวแล้วนับ Job ว่าสำเร็จ

ผู้ได้ประโยชน์: ผู้ใช้ที่สลับ Profile และรัน Saved Jobs หรือ Export ผลลัพธ์ ซึ่งต้องเห็นชัดว่า connection ที่จะใช้ตรงกับ Profile ที่เลือก และต้องไม่เข้าใจผิดว่าข้อมูล Excel ถูก export ครบเมื่อเกิน limit

### R4-2. ขอบเขต

#### In scope

- ก่อนเริ่มงานที่ใช้ connection ร่วมกับ `self.engine` ให้ตรวจ Profile ที่เลือกเทียบกับ Profile ใน `_run_target.info` หากมีค่าและไม่ตรงกัน ให้ปฏิเสธงานและบันทึกข้อความที่ระบุ Profile ที่เลือกกับ Profile ของ connection ปัจจุบันอย่างชัดเจน โดยไม่เปลี่ยน engine / `_run_target` เงียบ ๆ
- ใช้การตรวจ mismatch กับ Run Job (`run_job`), Run All / Run Group (`run_selected_job`), Export (`export_jobs_to_excel`), SQL Editor (`execute_query`) และ Tables (`list_tables`) เนื่องจากใช้ connection เดียวกัน
- Export DataFrame ที่มีแถวข้อมูลมากกว่า 1,048,575 แถวต้องทำให้ Job นั้น Failed พร้อม error ที่อธิบายจำนวนแถวสูงสุดที่ Excel รองรับ และสร้างชีต Failed ตามกลไกเดิม ห้ามตัด DataFrame แล้วเขียนผลเพียงบางส่วน
- เมื่อ Job หนึ่ง Export ไม่ได้เพราะเกิน limit ให้ประมวลผล Job ถัดไปตามปกติ และรายงาน Success / Failed ตามผลจริงของแต่ละ Job
- ใช้ `unittest` และ stub / mock โดยไม่ต่อฐานข้อมูลจริงและไม่เปิดหน้าต่าง Tk จริง

#### Out of scope

- การเปลี่ยน Profile หรือ engine ให้อัตโนมัติเมื่อพบ mismatch รวมถึงการเชื่อมต่อฐานข้อมูลใหม่โดยอัตโนมัติ
- การแก้บัคอื่นที่พบใน code review หรือการเปลี่ยนพฤติกรรมที่ไม่เกี่ยวกับสอง finding นี้
- การเปลี่ยนรูปแบบ workbook, การจัดรูปแบบเซลล์, การตั้งชื่อ sheet หรือกติกา Export อื่น นอกเหนือจากผลเมื่อเกิน row limit
- การเปลี่ยนขีดจำกัด Excel: รองรับได้สูงสุด 1,048,576 แถวต่อ worksheet รวม header 1 แถว จึงมีข้อมูลได้สูงสุด 1,048,575 แถวต่อ Job

### R4-3. User stories

- **R4-US-1**: ในฐานะผู้ใช้ที่เลือก Profile B ฉันต้องการให้แอปปฏิเสธการรันเมื่อ engine ยังผูกกับ Profile A และบอกให้ทราบอย่างชัดเจน เพื่อไม่ให้ SQL ไปรันผิดฐานข้อมูล
- **R4-US-2**: ในฐานะผู้ใช้ที่ Export ผลลัพธ์ ฉันต้องการให้ Job ที่มีข้อมูลเกินขีดจำกัด Excel ถูกระบุว่า Failed โดยไม่มีไฟล์ผลลัพธ์บางส่วน เพื่อไม่เข้าใจผิดว่าข้อมูลครบ
- **R4-US-3**: ในฐานะผู้ใช้ที่ Export หลาย Job ฉันต้องการให้ Job อื่นยัง Export ต่อได้เมื่อมี Job หนึ่งเกิน limit

### R4-4. Acceptance criteria

วิธีทดสอบทุกข้อเป็น `unittest` ใช้ stub ของ GUI / DataFrame, `unittest.mock`, `tempfile` ตามความเหมาะสม ไม่เปิด Tk จริงและไม่เชื่อมต่อฐานข้อมูลจริง

#### Profile mismatch — ปฏิเสธการใช้ connection ของ Profile อื่น

| AC | Given / When / Then | วิธีทดสอบ |
|---|---|---|
| R4-AC-1 | **Given** `profile_combo` เลือก Profile B แต่ `_run_target.info.profile` เป็น Profile A **When** เรียก `run_job`, `run_selected_job` (รวม Run Group) หรือ `export_jobs_to_excel` **Then** ปฏิเสธก่อนเริ่ม SQL / worker / file dialog, ไม่เรียก `read_sql_dataframe`, ไม่สร้าง thread, และ engine กับ `_run_target` ยังคงเป็น object เดิม | unittest |
| R4-AC-2 | **Given** Profile ที่เลือกไม่ตรงกับ `_run_target.info.profile` **When** เรียก `execute_query` หรือ `list_tables` ซึ่งใช้ connection เดียวกัน **Then** ปฏิเสธก่อนส่ง SQL หรือ metadata query ไปยัง worker และ engine ไม่เปลี่ยน | unittest |
| R4-AC-3 | **Given** งานถูกปฏิเสธเพราะ Profile ไม่ตรง **When** ตรวจ Execution Logs **Then** มีข้อความชัดเจนที่ระบุ Profile ที่เลือกและ Profile ที่ connection ใช้อยู่ พร้อมบอกว่าไม่ได้เริ่มงาน; ไม่เปลี่ยน Profile ที่เลือกและไม่สลับ / สร้าง engine ให้เอง | unittest |
| R4-AC-4 | **Given** Profile ที่เลือกตรงกับ `_run_target.info.profile` **When** เริ่ม Run Job, Run All, Export, SQL Editor หรือ Tables **Then** การตรวจ mismatch ไม่บล็อกงาน และงานใช้ engine ที่ผูกอยู่กับ `_run_target` ตามพฤติกรรมเดิม | unittest |
| R4-AC-5 | **Given** เลือก Profile B ขณะ engine ปัจจุบันยังเป็นของ Profile A **When** เชื่อมต่อ Profile B สำเร็จ แล้วเริ่มงานอีกครั้ง **Then** `_run_target` อ้างถึง engine ใหม่ของ Profile B, งานไม่ถูกปฏิเสธเพราะ mismatch และไม่ใช้ engine A | unittest (stub การเชื่อมต่อ; ไม่ใช้ฐานข้อมูลจริง) |

#### Excel row limit — ไม่เขียนผลบางส่วน

| AC | Given / When / Then | วิธีทดสอบ |
|---|---|---|
| R4-AC-6 | **Given** ผลของ Job มีแถวข้อมูลมากกว่า 1,048,575 แถว **When** Export Job นั้น **Then** Job ถูกนับเป็น Failed, error ระบุ limit 1,048,575 แถวข้อมูล, workbook มีชีต Failed ตามกลไกเดิม และไม่มีแถวข้อมูลบางส่วนจาก DataFrame ถูกเขียนเป็นผลสำเร็จของ Job นั้น | unittest (stub DataFrame / Excel writer) |
| R4-AC-7 | **Given** ผลของ Job มีแถวข้อมูลตั้งแต่ 0 ถึง 1,048,575 แถว **When** Export **Then** ยังคง Export ด้วยพฤติกรรมเดิมโดยไม่มีการตัดแถว; กรณี 1,048,575 แถวต้องเขียนครบทั้งหมด | unittest (stub DataFrame / Excel writer) |
| R4-AC-8 | **Given** Export มี Job ที่เกิน limit ตามด้วย Job ที่อยู่ใน limit **When** Export ทำงานจนจบ **Then** Job แรกถูกนับ Failed และมีชีต Failed, Job ถัดไปถูก Export ครบและนับ Success, และสรุปจำนวน Success / Failed ตรงกับผลจริง | unittest (stub jobs, DataFrame และ Excel writer) |

#### Regression

| AC | Given / When / Then | วิธีทดสอบ |
|---|---|---|
| R4-AC-9 | **Given** แก้ครบทั้งสอง finding **When** รัน `python -m unittest discover -s tests -p "test_*.py"` **Then** test เดิมทั้งหมดและ test ใหม่ผ่าน โดย test ใหม่ไม่ต้องใช้ฐานข้อมูลจริงหรือหน้าต่าง Tk จริง | unittest |

### R4-5. ข้อจำกัด / สมมติฐาน

- การเทียบ Profile ใช้ค่า string ของ Profile ที่เลือกและ `_run_target.info.profile`; ไม่เปลี่ยน engine หรือ Profile อัตโนมัติ กรณีตรงกันให้ใช้ engine ของ `_run_target` ตามเดิม
- ค่า row limit หมายถึงจำนวนแถวข้อมูล ไม่รวม header: 1,048,575 แถวข้อมูลบวก header 1 แถวเท่ากับ worksheet limit 1,048,576 แถว
- การตรวจ row limit ต้องเกิดก่อนเขียนข้อมูลของ Job ลง worksheet เพื่อให้ Job ที่เกิน limit ไม่เหลือผลลัพธ์บางส่วน; ใช้กลไกจับ error / สร้างชีต Failed ที่มีอยู่แล้ว
- Test สามารถใช้ DataFrame / writer stub ที่จำลองจำนวนแถวและบันทึกการเรียกเขียนได้ ไม่จำเป็นต้องสร้างข้อมูลจริงมากกว่า 1 ล้านแถว

### R4-6. คำถามที่ยังไม่มีคำตอบ

| # | คำถาม | คำตอบที่แนะนำ |
|---|---|---|
| R4-Q-1 | ถ้า engine มีอยู่แต่ `_run_target.info` หรือชื่อ Profile ที่เลือกว่าง / ไม่มี จะถือว่า mismatch และปฏิเสธงานหรือไม่ | ปฏิเสธเฉพาะเมื่อมีค่า Profile ทั้งสองฝั่งและไม่ตรงกัน; กรณีเปรียบเทียบไม่ได้คงพฤติกรรมเดิม ไม่เดา Profile จาก engine หรือ URL |

---

# Round 5 — Bugfix: Profile, Export, SQL parsing และ UI thread safety

> ใช้เลข `R5-AC-x` แยกจาก Round ก่อนหน้า
> ขอบเขตจำกัดเฉพาะ bug C-1, H-3, C-2, C-3, H-2, M-1, H-1, M-3, M-2, M-4, M-5 และ M-6 ที่ระบุในรอบนี้
> แต่ละ bug มีไฟล์ unittest แยกตาม `tests/test_bugfix_<id>.py` โดยเขียน ID เป็นตัวพิมพ์เล็กและตัดขีดกลางออก เช่น `C-1` เป็น `tests/test_bugfix_c1.py`

### R5-1. เป้าหมาย

แก้พฤติกรรมบันทึก/โหลด Profile และ Job ที่รายงานความสำเร็จผิด, ทำให้ข้อมูล Excel หรือ SQL ถูกตีความผิด, และแก้การเข้าถึง Tk / engine ชั่วคราวที่ไม่ปลอดภัยระหว่างทำงานเบื้องหลัง โดยคงการเปลี่ยนแปลงให้เล็กที่สุด

ผู้ได้ประโยชน์: ผู้ใช้ที่จัดการหลาย Profile / Job, export ผล query, ใช้ SQL parameter และเรียกดู Tables หรือปิดแอประหว่างงานกำลังทำงาน

### R5-2. ขอบเขต

#### In scope

- **C-1**: หลัง `save_profile_dialog.save` เลือก Profile ที่บันทึกแล้วด้วย `profile_combo.current(...)` ให้เรียก `self.update_jobs_list()`; `run_job` ต้อง log และ return เมื่อ Profile ของ Job ไม่ตรงกับ `profile_combo.get()`
- **H-3**: `save_profiles` และ `save_jobs` คืน `bool` ระบุผลบันทึก และ callers ที่ระบุใน R5-AC-2 ต้องไม่รายงานสำเร็จเมื่อบันทึกล้มเหลว พร้อม rollback การเปลี่ยนแปลงในหน่วยความจำ
- **C-2**: ก่อนเขียนข้อมูลลง Excel ตรวจ string cell ที่ยาวเกิน 32,767 ตัวอักษร ระบุ Job และ column ใน Execution Logs และทำเครื่องหมาย Job เป็น warning
- **C-3**: `clean_value` ต้องแปลงค่า `bytes` ด้วย `format_db_value(x)` เพื่อให้ได้ค่า hex ไม่ decode เป็นข้อความ
- **H-2**: การหา First IN list ใน `_render_sql_template` ใช้ `_scan_sql` เพื่อข้าม comment / string literal และแจ้ง error ชัดเจนเมื่อไม่พบ list
- **M-1**: ตรวจ placeholder จาก token ของ `_scan_sql`; ไม่ตรวจ placeholder ที่อยู่ใน string/comment, ไม่ถือ `::` cast เป็น placeholder และไม่จับเวลา `HH24:MI:SS` เป็น placeholder
- **H-1**: ก่อนเริ่ม Tables worker อ่าน `db_user`, `db_password`, `db_host`, `db_port` บน main thread แล้วส่งค่า snapshot ให้ worker; dispose `temp_engine` ใน `finally`; SQL Server schema discovery ใช้ bind parameter แทน f-string
- **M-3**: `_execute_query_background` อ่าน `debug_mode` หนึ่งครั้งบน main thread แล้วส่งค่าให้ worker; `test_connection` จัดการ UI/dialog ผ่าน `root.after` ไม่เรียก Tk จาก worker
- **M-2**: หลัง `ws.cell(...)` ที่เขียน SQL annotation, No Data, Failed และ Skipped ให้กำหนด `cell.data_type = 's'` เพื่อเก็บข้อความที่ขึ้นต้น `=` เป็น string ไม่ใช่ formula
- **M-4**: `on_closing` ถาม Yes/No ก่อน `root.destroy()` เมื่อ `self._is_busy()` เป็น True
- **M-5**: บันทึก preset ที่ชื่อไฟล์มีอยู่แล้วต้องถามยืนยัน โดยเทียบชื่อแบบไม่แยกตัวพิมพ์เล็ก/ใหญ่ตามพฤติกรรม Windows; เขียนด้วย `write_json_atomic`; Cancel หรือเขียนไม่สำเร็จต้องรักษาข้อมูลเดิม
- **M-6**: เมื่อ `do_import` เขียนทับ Profile ที่กำลัง active สำเร็จ ให้ reload Profile นั้นด้วย `load_profile_data(active)` เพื่ออัปเดต fields และ engine

#### Out of scope

- Refactor, rename, feature หรือ bugfix อื่นนอกเหนือจากรายการข้างต้น
- การเปลี่ยนรูปแบบหรือพฤติกรรมอื่นของ Profile, Job, preset, SQL template, workbook หรือ Tables ที่ไม่ได้กำหนดใน acceptance criteria
- Commit หรือแก้ไฟล์นอก `docs/spec.md` ในขั้นจัดทำ spec นี้

### R5-3. User stories

- **R5-US-1**: ในฐานะผู้ใช้หลาย Profile ฉันต้องการให้รายการ Job และ connection สอดคล้องกับ Profile ที่เลือก และให้ผลบันทึกล้มเหลวไม่ถูกแสดงเป็นความสำเร็จ เพื่อป้องกันข้อมูลในหน่วยความจำไม่ตรงกับไฟล์
- **R5-US-2**: ในฐานะผู้ใช้ Excel export และ SQL parameter ฉันต้องการให้ข้อมูลยาว/ชนิดพิเศษและ token ใน SQL ถูกจัดการตามความหมายจริง เพื่อให้ workbook และ SQL ที่ได้ไม่ผิดพลาด
- **R5-US-3**: ในฐานะผู้ใช้ที่เปิด Tables, ทดสอบ connection หรือปิดแอประหว่างทำงาน ฉันต้องการให้ worker ใช้ snapshot และให้ Tk ถูกเรียกจาก main thread เท่านั้น
- **R5-US-4**: ในฐานะผู้ใช้ preset ฉันต้องการยืนยันก่อนเขียนทับ และให้การยกเลิกหรือบันทึกล้มเหลวไม่ทำลายข้อมูลเดิม

### R5-4. Acceptance criteria

วิธีทดสอบทุกข้อเป็น `unittest` ใช้ `unittest.mock`, stub และไฟล์ชั่วคราวตามความเหมาะสม ไม่ต้องต่อฐานข้อมูลจริง เว้นแต่การทดสอบจำลองด้วย mock จะเพียงพอ ทั้งนี้แต่ละ bug ต้องมี test แยกในไฟล์ที่ระบุ

| AC | Given / When / Then | ไฟล์ test |
|---|---|---|
| R5-AC-1 (C-1) | **Given** `save_profile_dialog.save` บันทึก Profile สำเร็จ **When** combobox ถูกเปลี่ยนไปยัง Profile ที่บันทึกด้วย `profile_combo.current(...)` **Then** เรียก `self.update_jobs_list()` หลังเลือก Profile นั้น; และ **Given** Job มีค่า `job.get("profile")` ไม่ตรงกับ `profile_combo.get()` **When** เรียก `run_job(job)` **Then** เขียนเหตุผลลง Execution Logs, ไม่เริ่ม Job และ return | `tests/test_bugfix_c1.py` |
| R5-AC-2 (H-3) | **Given** การเขียน Profile หรือ Job สำเร็จ/ล้มเหลว **When** เรียก `save_profiles()` หรือ `save_jobs()` **Then** คืน `True` เมื่อบันทึกสำเร็จและ `False` เมื่อไม่สำเร็จ; หากผลเป็น `False` callers ต่อไปนี้ต้องไม่แสดง success message/log และต้อง rollback การเปลี่ยนแปลงในหน่วยความจำให้กลับเป็นค่าก่อนเริ่ม action: `save_profile_dialog.save`, `new_profile_dialog.create`, `delete_profile`, `do_import`, `save_job_dialog.save`, `edit_job.save_changes`, `load_preset_dialog`; เมื่อบันทึกสำเร็จให้คง success behavior เดิม | `tests/test_bugfix_h3.py` |
| R5-AC-3 (C-2) | **Given** ผลของ Job มี string cell ยาวเกิน 32,767 ตัวอักษร **When** `export_jobs_to_excel` เตรียมเขียน cell **Then** ตรวจพบก่อนเขียน cell นั้น, ไม่เขียน string ที่เกิน limit, บันทึก warning ใน Execution Logs ที่ระบุชื่อ Job และ column และนับ/ทำเครื่องหมาย Job นั้นเป็น warning ไม่ใช่ success ปกติ | `tests/test_bugfix_c2.py` |
| R5-AC-4 (C-3) | **Given** ค่า cell เป็น `bytes` **When** `clean_value` เตรียมค่าก่อนเขียน Excel **Then** เรียก `format_db_value(x)` และใช้ผลลัพธ์ hex ตาม formatter โดยไม่ลอง decode เป็น UTF-16LE / UTF-8 | `tests/test_bugfix_c3.py` |
| R5-AC-5 (H-2) | **Given** SQL มีคำ `IN (` อยู่ใน comment หรือ string ก่อน First IN list จริง **When** `_render_sql_template` แทนค่า parameter `__FIRST_IN_LIST__` **Then** แทน list จริงรายการแรกที่ `_scan_sql` ระบุ ไม่แก้ comment/string; และ **Given** ไม่มี IN list ที่เป็น SQL token **When** render **Then** raise `ValueError` พร้อมข้อความชัดเจนว่าไม่พบ `IN (...)` ใน SQL template | `tests/test_bugfix_h2.py` |
| R5-AC-6 (M-1) | **Given** SQL มี placeholder จริง, placeholder-like text ใน comment/string, cast `value::type` และเวลา `HH24:MI:SS` **When** ตรวจหา placeholder โดย tokenize ผ่าน `_scan_sql` **Then** ตรวจเฉพาะ placeholder จริง, ละเว้น comment/string และ `::` cast, และไม่รายงานส่วนเวลาเป็น placeholder | `tests/test_bugfix_m1.py` |
| R5-AC-7 (H-1) | **Given** ผู้ใช้กด Tables **When** เริ่ม worker **Then** `db_user`, `db_password`, `db_host`, `db_port` ถูกอ่านจาก Tk Variables บน main thread ก่อนเริ่ม worker และ worker ใช้เฉพาะ snapshot ที่ส่งเข้าไป; `temp_engine.dispose()` ถูกเรียกใน `finally` ทั้งเมื่อ discovery สำเร็จและเกิด exception; สำหรับ SQL Server การค้นหา schema bind ค่า schema เป็น parameter และไม่ประกอบ query ด้วย f-string | `tests/test_bugfix_h1.py` |
| R5-AC-8 (M-3) | **Given** เริ่ม `_execute_query_background` และค่า `debug_mode` เปลี่ยนภายหลัง worker เริ่มแล้ว **When** worker ทำงาน **Then** ใช้ค่า debug ที่อ่านครั้งเดียวบน main thread และส่งให้ worker; ใน `test_connection` การเปลี่ยน widget, แสดงผล และเปิด dialog ที่เกิดจากผล worker ต้องถูกจัดตารางผ่าน `root.after` และ worker ไม่เรียก Tk โดยตรง | `tests/test_bugfix_m3.py` |
| R5-AC-9 (M-2) | **Given** SQL annotation, No Data, Failed หรือ Skipped sheet ต้องเขียนข้อความที่ขึ้นต้นด้วย `=` **When** เขียนแต่ละ cell ด้วย `ws.cell(...)` **Then** กำหนด `cell.data_type = 's'` หลังสร้าง cell และค่าถูกเก็บเป็นข้อความ literal ไม่ถูกตีความเป็นสูตร | `tests/test_bugfix_m2.py` |
| R5-AC-10 (M-4) | **Given** `self._is_busy()` เป็น True **When** เรียก `on_closing` และผู้ใช้ตอบ No **Then** `root.destroy()` ไม่ถูกเรียก; เมื่อผู้ใช้ตอบ Yes จึงเรียก `root.destroy()`; เมื่อไม่ busy คงพฤติกรรมปิดหน้าต่างเดิม | `tests/test_bugfix_m4.py` |
| R5-AC-11 (M-5) | **Given** มี preset filename ที่ตรงกันโดยไม่สนตัวพิมพ์เล็ก/ใหญ่ **When** บันทึก preset **Then** ถามยืนยันก่อนเขียนทับ; เมื่อ Cancel หรือ write ล้มเหลว เนื้อหาเดิมยังคงอยู่; เมื่อยืนยันและเขียนสำเร็จ ใช้ `write_json_atomic` บันทึกไฟล์ | `tests/test_bugfix_m5.py` |
| R5-AC-12 (M-6) | **Given** `do_import` เขียนทับ Profile ที่ active อยู่และการบันทึกสำเร็จ **When** import เสร็จ **Then** เรียก `load_profile_data(active)` เพื่อโหลด fields และ engine จากข้อมูล Profile ที่ import เข้ามา; Profile อื่นที่ไม่ได้เขียนทับไม่ทำให้เกิด reload นี้ | `tests/test_bugfix_m6.py` |
| R5-AC-13 (Regression) | **Given** แก้ครบทั้ง 12 bugs **When** รัน `python -m unittest discover -s tests -p "test_*.py"` **Then** test เดิมทั้งหมดและ test ใหม่ผ่าน | Full suite |

### R5-5. ข้อจำกัด / สมมติฐาน

- การเปลี่ยนแปลงต้องเป็น minimal diffs: ห้าม refactor, rename หรือเพิ่ม feature/แก้บัคที่ไม่อยู่ในรายการ R5-2
- ใช้ Python 3, PEP 8 และ type hints
- Tk widgets และ Tk Variables เข้าถึงได้เฉพาะ main thread; อ่านค่าที่ worker ต้องใช้ก่อนเริ่ม worker แล้วส่งค่า snapshot เข้า worker
- เพิ่ม unittest ของ bug แต่ละรายการในไฟล์แยกตาม R5-AC-1 ถึง R5-AC-12
- คำสั่งตรวจรับเต็มชุดคือ `python -m unittest discover -s tests -p "test_*.py"`
- ห้าม commit

### R5-6. คำถามที่ยังไม่มีคำตอบ

ไม่มี — requirement และพฤติกรรมที่ต้องการระบุครบแล้ว

---

# Round 6 — Bugfix: Import Groups รายงานสำเร็จแม้บันทึก `script_groups.json` ไม่สำเร็จ

> ใช้เลข `R6-AC-x` และ `R6-Q-x` แยกจาก Round ก่อนหน้า
> ขอบเขตจำกัดเฉพาะบัค 1 ข้อที่ผู้ใช้อนุมัติ (ที่มา: `docs/review.md` Code Review Round 3, 🟡 Warning #1) ใช้แนวทางเดียวกับ Round 5 H-3 (R5-AC-2)
> ไม่แก้เนื้อหา Round ก่อนหน้า; R3-AC-12 ยังคงใช้กับกรณีบันทึกสำเร็จ
> ไฟล์ที่เกี่ยวข้อง: `database_connect_gui.py` — `save_script_groups` (~4392-4413), `import_script_groups` (~4489-4525, จุดบัค 4520-4524), `_refresh_script_groups_window` (~4554)

### R6-1. เป้าหมาย

ปัจจุบัน `import_script_groups` เรียก `merge_imported_script_groups(...)` แล้วเรียก `self.save_script_groups()` โดยไม่ตรวจผล จากนั้น refresh หน้าต่าง Script Groups และเขียน log `📥 Imported N group(s) from <path>` ส่วน `save_script_groups()` เมื่อถูกบล็อก (`_script_groups_save_blocked` เช่นไฟล์ถูก OneDrive ล็อกตอนเปิดแอป) หรือเขียนไฟล์ล้มเหลว จะแสดง error แล้ว return `None` ผลคือผู้ใช้เห็น error ตามด้วย log ว่า import สำเร็จ กลุ่มที่ import อยู่ในหน่วยความจำเท่านั้นและหายไปเมื่อเปิดแอปใหม่

เป้าหมาย: เมื่อบันทึกไม่สำเร็จ ต้องไม่รายงานสำเร็จ และหน่วยความจำต้องกลับเป็นสถานะก่อน import ให้ตรงกับไฟล์บนดิสก์

ผู้ได้ประโยชน์: ผู้ใช้ที่ Import Groups ทั้งจาก sidebar และจากหน้าต่าง Script Groups (ทั้งสองทางเรียก `import_script_groups` ตัวเดียวกัน)

### R6-2. ขอบเขต

#### In scope
- `save_script_groups()` คืน `True` เมื่อบันทึกสำเร็จ และ `False` เมื่อถูกบล็อก (`_script_groups_save_blocked`) หรือการเขียนล้มเหลว (รวม exception จาก `_backup_script_groups_once` และ `write_json_atomic` ที่อยู่ใน `try` เดิม) โดย error dialog เดิมทั้งสองกรณีคงข้อความ / title / จำนวนครั้งเดิม
- `import_script_groups`: ก่อน merge ทำ deep copy ของ `self.script_groups`; ถ้า `save_script_groups()` คืน `False` ให้ rollback `self.script_groups` ให้เท่ากับ snapshot ก่อน merge ทุกประการ, ไม่เขียนบรรทัด `📥 Imported`, ไม่รายงานสำเร็จ (คืน `None`) และเรียก refresh หน้าต่าง Script Groups ให้แสดงสถานะหลัง rollback
- เมื่อบันทึกสำเร็จ พฤติกรรมเดิมทุกอย่าง (R3-AC-12, R3-AC-15)

#### Out of scope
- callers อื่นของ `save_script_groups()` (closure ใน `show_script_groups_dialog` ~5038-5147) — คงพฤติกรรมเดิม ไม่ตรวจค่าคืนในรอบนี้
- 🟢 Suggestion อื่นใน Code Review Round 3 และ 🟡 Warning อื่น
- การเปลี่ยนข้อความ error dialog เดิม, การเพิ่ม log หรือ dialog ใหม่สำหรับกรณีล้มเหลว (error dialog ของ `save_script_groups()` เพียงพอแล้ว)
- การเปลี่ยน `merge_imported_script_groups`, `parse_script_groups_import`, รูปแบบไฟล์ หรือกลไก backup

### R6-3. User stories

- **R6-US-1**: ในฐานะผู้ใช้ที่ Import Groups ขณะ `script_groups.json` ถูกล็อกหรือเขียนไม่ได้ ฉันต้องการให้แอปไม่บอกว่า import สำเร็จและไม่แสดงกลุ่มที่ไม่ได้ถูกบันทึก เพื่อไม่เข้าใจผิดว่ากลุ่มจะยังอยู่หลังเปิดแอปใหม่
- **R6-US-2**: ในฐานะผู้ใช้ที่ Import Groups ในสภาวะปกติ ฉันต้องการให้พฤติกรรมเหมือนเดิมทุกอย่าง

### R6-4. Acceptance criteria

วิธีทดสอบทุกข้อเป็น `unittest` ใช้ stub (`DatabaseConnectorGUI.__new__`), `unittest.mock.patch` สำหรับ `filedialog` / `messagebox` / `write_json_atomic` และ `tempfile` ไม่เปิดหน้าต่าง Tk จริง ไฟล์ test ใหม่: `tests/test_r6_import_save_failure.py`

#### `save_script_groups()` คืนค่า bool

| AC | Given / When / Then | วิธีทดสอบ |
|---|---|---|
| R6-AC-1 | **Given** `_script_groups_save_blocked = True` **When** เรียก `save_script_groups()` **Then** คืน `False` (เป็น `bool` ไม่ใช่ `None`), `messagebox.showerror` ถูกเรียก 1 ครั้งด้วย title `"Script Groups"` และข้อความเดิม (`script_groups.json could not be read when the app started, so it is not overwritten. ...`), และไม่มีการเรียก `write_json_atomic` / ไม่มีไฟล์ถูกเขียน | unittest |
| R6-AC-2 | **Given** ไม่ถูกบล็อก และ `write_json_atomic` raise `OSError` (หรือ `_backup_script_groups_once` raise) **When** เรียก `save_script_groups()` **Then** คืน `False`, `messagebox.showerror` ถูกเรียก 1 ครั้งด้วยข้อความเดิม `Cannot save script_groups.json:\n<error>` และไฟล์เดิมบนดิสก์ไม่เปลี่ยน | unittest |
| R6-AC-3 | **Given** ไม่ถูกบล็อก และ path เขียนได้ (tempdir) **When** เรียก `save_script_groups()` **Then** คืน `True`, ไม่มี `showerror` และเนื้อหาไฟล์เหมือนพฤติกรรมเดิม (`{"version": 1, "groups": [...]}` ที่ตัด key `_*` / `run_index`) | unittest |

#### `import_script_groups` เมื่อบันทึกล้มเหลว

| AC | Given / When / Then | วิธีทดสอบ |
|---|---|---|
| R6-AC-4 | **Given** Profile `P1` มีกลุ่มเดิม (รวมกลุ่มของ Profile อื่น และ script ที่มี key ซ้อน เช่น dict / list) ไฟล์ import ถูกต้อง และ `_script_groups_save_blocked = True` **When** เรียก `import_script_groups(parent)` (ไม่มีชื่อชน) **Then** คืน `None`, `self.script_groups` เท่ากับ deep copy ที่เก็บไว้ก่อนเรียก (`assertEqual`) ทั้งจำนวน ลำดับ และค่าภายในทุกระดับ, และ `results_text` ไม่มีบรรทัดที่มี `📥 Imported` | unittest |
| R6-AC-5 | **Given** เหมือน R6-AC-4 แต่ไม่ถูกบล็อก และ `write_json_atomic` raise `OSError` **When** `import_script_groups(parent)` **Then** ผลเหมือน R6-AC-4 (คืน `None`, rollback เท่ากับก่อนเรียก, ไม่มี `📥 Imported`) และไฟล์ `script_groups.json` บนดิสก์ไม่เปลี่ยน | unittest |
| R6-AC-6 | **Given** ไฟล์ import มีชื่อชนกับกลุ่มเดิมของ `P1` และการบันทึกล้มเหลว (ทั้งกรณี blocked และ write failure) **When** ผู้ใช้ตอบ **Yes** (Replace) **Then** กลุ่มเดิมที่ถูกแทนที่กลับมาครบ ตำแหน่งเดิมในลิสต์ และค่าเท่าเดิม; `self.script_groups == snapshot` และไม่มีกลุ่มจากไฟล์หลงเหลือ | unittest |
| R6-AC-7 | **Given** เหมือน R6-AC-6 **When** ผู้ใช้ตอบ **No** (Keep both) **Then** ไม่มีกลุ่มที่ตั้งชื่อใหม่ `name (n)` หลงเหลือ; `self.script_groups == snapshot` | unittest |
| R6-AC-8 | **Given** การบันทึกล้มเหลว **When** `import_script_groups` ทำงานจบ **Then** ไม่มีการเรียก `results_text.insert` ที่มี `📥 Imported`, ไม่มี `messagebox.showinfo` / ข้อความแจ้งสำเร็จใด ๆ, ค่าคืนเป็น `None`, และ `save_script_groups` ถูกเรียก 1 ครั้ง; ผ่านทาง `sidebar_import_script_groups()` ก็ได้ผลเดียวกัน (คืน `None`) | unittest |
| R6-AC-9 | **Given** หน้าต่าง Script Groups เปิดอยู่ (`_script_groups_refresh` = mock callback, `_script_groups_window.winfo_exists()` เป็น True) และการบันทึกล้มเหลว **When** `import_script_groups` **Then** callback refresh ถูกเรียก 1 ครั้ง **หลัง** rollback (ตอนที่ callback ถูกเรียก `self.script_groups` เท่ากับ snapshot แล้ว) และไม่ได้ส่งชื่อกลุ่มที่ import (ส่ง `None` เพื่อคงการเลือกเดิม — ดู R6-Q-1); ถ้าหน้าต่างไม่ได้เปิด ไม่มี error | unittest |
| R6-AC-10 | **Given** การบันทึกล้มเหลว **When** rollback **Then** `self.script_groups` ยังเป็น list object เดิม (`is` ตัวเดียวกับก่อนเรียก — rollback แบบ in-place) เพื่อไม่ให้ส่วนอื่นที่อ้าง list นี้เห็นข้อมูลค้าง | unittest |

#### กรณีสำเร็จและ Regression

| AC | Given / When / Then | วิธีทดสอบ |
|---|---|---|
| R6-AC-11 | **Given** `save_script_groups()` คืน `True` **When** Import แบบไม่ชน, Yes และ No **Then** ผลเหมือนเดิมตาม R3-AC-12 / R3-AC-15: merge ตาม R3-AC-4 / R3-AC-5, `save_script_groups` ถูกเรียก 1 ครั้ง, ลำดับ save → refresh(ชื่อกลุ่มสุดท้าย) → log, `results_text` มีบรรทัด `📥 Imported <n> group(s) from <path>` และคืนชื่อกลุ่มสุดท้าย | unittest |
| R6-AC-12 | **Given** ผู้ใช้ตอบ Cancel, ไฟล์ไม่ถูกต้อง หรือยังไม่เลือก Profile **When** Import **Then** พฤติกรรมเดิม (R3-AC-10, 11, 13): ไม่เรียก `save_script_groups`, `script_groups` ไม่เปลี่ยน | unittest (test เดิมใน `tests/test_r3_script_groups_io.py`) |
| R6-AC-13 | **Given** แก้ครบ **When** รัน `python -m unittest discover -s tests -p "test_*.py"` **Then** test เดิมทั้งหมดและ test ใหม่ผ่าน | Full suite |

**สรุปจำนวน AC Round 6**: 13 ข้อ — unittest ทั้งหมด

### R6-5. ข้อจำกัด / สมมติฐาน

- Minimal diff: แก้เฉพาะ `save_script_groups` (เพิ่ม `return True` / `return False` และ type hint `-> bool`) และ `import_script_groups`; ไม่ refactor, ไม่ rename
- Snapshot ใช้ `copy.deepcopy(self.script_groups)` ก่อนเรียก `merge_imported_script_groups` (merge แก้ list in place และ `remove` กลุ่มเดิมเมื่อ Replace) และ rollback แบบ in-place เช่น `self.script_groups[:] = snapshot` (R6-AC-10)
- Callers อื่นของ `save_script_groups()` ไม่เปลี่ยนโค้ด — แค่ได้ค่าคืนเพิ่มที่ไม่ได้ใช้
- **ผลกระทบกับ test เดิม**: `tests/test_r3_script_groups_io.py:876` ตั้ง `save_script_groups.side_effect = lambda: order.append("save")` ซึ่งคืน `None` และจะถูกตีความเป็น "บันทึกล้มเหลว" หลังแก้ ทำให้ test success path ล้ม; test เดิมที่ mock `save_script_groups` แบบคืน `None` ต้องปรับให้คืน `True` (ปรับเฉพาะค่าคืนของ mock ไม่แก้ assertion) — `mock.Mock()` เปล่าคืน Mock ที่เป็น truthy จึงไม่กระทบ ทั้งนี้ implementation ควรเช็ก `if not self.save_script_groups():` เพื่อให้ mock เดิมที่คืน Mock ยังเป็นกรณีสำเร็จ
- Rollback ไม่กระทบไฟล์บนดิสก์ (ไฟล์ไม่ถูกเขียนอยู่แล้วเมื่อล้มเหลว) และไม่กระทบ `_script_groups_backup_done` / `_script_groups_save_blocked`
- ห้าม commit

### R6-6. คำถามที่ยังไม่มีคำตอบ

| # | คำถาม | คำตอบที่แนะนำ |
|---|---|---|
| R6-Q-1 | ตอน refresh หลัง rollback ควรเลือกกลุ่มใดในหน้าต่าง Script Groups | ส่ง `None` ให้ `refresh_groups` คงกลุ่มที่เลือกอยู่เดิม (ตามชื่อ) — เขียนไว้ใน R6-AC-9 แล้ว ถ้าผู้ใช้ต้องการแบบอื่นให้แจ้ง |

---

# Round 7 — Bugfix: ผลค้างจาก Round 5 / Round 6 review (R7-1 ถึง R7-5)

> ใช้เลข `R7-AC-x` และ `R7-Q-x` แยกจาก Round ก่อนหน้า ไม่แก้เนื้อหา Round ก่อนหน้า
> ที่มา (หลักฐานอยู่ใน `docs/review.md`): R7-1 = Round 5 🟡-1, R7-2 = Round 5 🟡-2, R7-3 = Round 5 🟡-3 (+ 🟢-6), R7-4 = Round 5 🟡-4, R7-5 = Round 6 🟢-3
> ผู้ใช้อนุมัติขอบเขตทั้ง 5 ข้อแล้ว: R7-3 ให้ **ขยาย** C-2 และ R7-4 ให้ **คืน** การตรวจ placeholder ที่อยู่ใน quote
> เลขบรรทัดอ้างอิงไฟล์ ณ วันที่เขียน spec (2026-11-16) อาจคลาดเคลื่อนเล็กน้อย

### R7-1. เป้าหมาย

ปิดช่องโหว่ 5 จุดที่ทำให้ contract ที่ Round 5 / Round 6 ตั้งไว้ไม่ครบ:

- **R7-1**: `save_profiles` (`database_connect_gui.py:10798-10802`) เรียก `print(error_msg)` ที่ขึ้นต้นด้วย "❌" ใน except; เมื่อ stdout เป็น encoding ที่ไม่มีอักขระนี้ (เช่น `cp874` ตอน redirect / pipe) `print` raise `UnicodeEncodeError` ทำให้ `save_profiles` raise แทนการคืน `False`, ไม่ขึ้น `showerror` และ callers ของ R5-AC-2 ไม่ได้ rollback
- **R7-2**: `run_job` (`:9639`) ใช้ `job.get("profile")` แต่ `update_jobs_list` (`:3920-3922`) และ `_current_profile_jobs` / `get_jobs_to_run` (`:4054`) ใช้ `job.get("profile", current_profile)` ทำให้ Job รุ่นเก่าที่ไม่มี key `"profile"` แสดงและรันผ่าน Run All ได้ แต่ปุ่ม ▶ ปฏิเสธด้วย "Job Profile คือ 'None'"
- **R7-3**: การตรวจ 32,767 ตัวอักษรของ C-2 ครอบคลุมเฉพาะ cell ผลลัพธ์ ข้อความที่เขียนลง sheet Skipped / Failed / No Data และ SQL annotation (`:10406-10414`, `:10439-10443`, `:10553-10555` → `append_sql_annotation` `:10340-10355`, `:10630-10632`) ไม่ถูกตรวจ ทำให้ Excel ต้องซ่อมไฟล์ / ตัดข้อความ และ Job ยังนับเป็น Success
- **R7-4**: หลัง M-1 `_detect_sql_placeholders` (`:458-494`) คืน `[]` สำหรับ `':ACC'` และ `'{ACC}'` ที่ `_render_sql_template` (`:11535-11547`) ยังรองรับ (`tests/test_database_connect_gui_core.py:542-544`) ทำให้ placeholder แบบมี quote ไม่ปรากฏในตัวเลือก Parameter ของ Load Excel
- **R7-5**: callers 8 จุดของ `save_script_groups()` ใน `show_script_groups_dialog` (`:5047-5156`) ไม่ตรวจค่าคืน เมื่อบันทึกล้มเหลว ข้อมูลในหน่วยความจำและหน้าต่างแสดงการเปลี่ยนแปลงที่ไม่ได้อยู่บนดิสก์ และหายไปเมื่อเปิดแอปใหม่

ผู้ได้ประโยชน์: ผู้ใช้ Windows ภาษาไทยที่รันแอป / test ผ่าน redirect หรือ pipe, ผู้ใช้ที่มี `saved_jobs.json` รุ่นเก่า, ผู้ใช้ที่ export Job ซึ่ง render IN list ยาวมาก, ผู้ใช้ที่เขียน placeholder ใน quote และผู้ใช้หน้าต่าง Script Groups ขณะไฟล์ถูกล็อก

### R7-2. ขอบเขต

#### In scope

- **R7-1**: ใน failure path ของ `save_profiles`, `save_jobs` และ `save_script_groups` (รวม `_profiles_save_refused` ที่ `save_profiles` เรียก) การเขียนข้อความลง console (`print`) ต้องไม่ทำให้ฟังก์ชัน raise: ถ้าการ print ล้มเหลวด้วย exception ใด ๆ ให้ข้ามไป แล้ว `showerror` และ `return False` ต้องเกิดขึ้นตามเดิม (ปัจจุบันมี `print` เฉพาะใน `save_profiles` ส่วนอีกสองฟังก์ชันใช้ AC เป็น regression lock)
- **R7-2**: `run_job` เปรียบเทียบด้วย `job.get("profile", selected_profile)` ให้ตรงกับ `update_jobs_list` / `_current_profile_jobs`
- **R7-3**: นำพฤติกรรม C-2 (เว้น cell ว่างแทนข้อความที่เกิน, log warning ระบุ Job และตำแหน่ง, ไม่นับเป็น Success ปกติ) ไปใช้กับ string ทุก cell ที่ `export_jobs_to_excel` เขียนลง sheet Skipped (`Status`, `Message`, `Query`), Failed (`Status`, `Error`, `Query`), บรรทัด SQL ของ sheet No Data และบรรทัด SQL ของ `append_sql_annotation`; และเปลี่ยนการนับความยาวเป็น **UTF-16 code units** ใน helper เดียวที่ใช้ทั้ง cell ผลลัพธ์ (C-2 เดิม) และ cell ใหม่ข้างต้น
- **R7-4**: `_detect_sql_placeholders` ตรวจ string literal แบบ single quote (`'...'`) ที่ **เนื้อหาทั้งหมด** เป็น placeholder หนึ่งตัวพอดี (`:name` หรือรูป braced ที่ `_SQL_BRACED_PLACEHOLDER_RE` รับ) ส่วน placeholder ที่อยู่ภายใน literal ที่ยาวกว่านั้น (เช่น `'HH24:MI:SS'`, `'text {x}'`, `'a :ACC'`) ยังไม่ถูกตรวจตาม M-1
- **R7-5**: ทั้ง 8 action ใน `show_script_groups_dialog` ที่เรียก `save_script_groups()` ใช้แนวทาง Round 6: deep-copy snapshot ก่อนแก้ข้อมูล, ถ้า `not self.save_script_groups()` ให้ rollback แบบ in-place (`self.script_groups[:] = snapshot`) แล้ว refresh หน้าต่างจากข้อมูลหลัง rollback และไม่แสดงผลสำเร็จ:

| # | Action (closure) | ปุ่ม / การกระทำ | จุดเรียก save | การแก้ข้อมูลที่ต้อง rollback |
|---|---|---|---|---|
| 1 | `new_group` | `＋ New Group` | `:5047` | `self.script_groups.append(new group)` |
| 2 | `rename_group` | `✎  Rename` / double-click กลุ่ม | `:5061` | `group["name"] = name` |
| 3 | `delete_group` | `🗑  Delete` (กลุ่ม) | `:5077` | `self.script_groups.remove(group)` |
| 4 | `add_sql` | `＋ Add SQL` | `:5090` | `group["scripts"].append(result)` |
| 5 | `add_from_jobs` | `🕘  From Saved Jobs` | `:5111` | `group["scripts"].append(...)` หลายรายการ |
| 6 | `edit_script` | `✎ Edit` / double-click script | `:5127` | `script.pop(...)` + `script.update(result)` |
| 7 | `delete_script` | `🗑 Remove` | `:5143` | `del group["scripts"][index]` |
| 8 | `move_script` | `↑` / `↓` | `:5156` | สลับตำแหน่ง script สองตัว |

#### Out of scope

- 🟢 Suggestion อื่นทั้งหมดใน Round 5 review (ข้อ 1-5, 7) และ Round 6 review (ข้อ 1-2)
- `print` อื่นในไฟล์ที่ไม่อยู่ใน failure path ของสามฟังก์ชันข้างต้น (เช่น `:95`, `:218`, `:6716-6774`, `:9099-9238`, `:10812`)
- การใช้ `job.get("profile")` แบบไม่มี default ที่อื่น (Save Preset `:5253`, Load Preset `:5458`, `:5479`)
- การตรวจความยาวของชื่อ column (header), sheet `Export` ตอน Stop และ cell ที่ไม่ได้ระบุใน R7-3
- การเปลี่ยน `_render_sql_template` (การแทนค่ายังเป็น `re.subn` บน SQL ดิบ — Round 5 🟢-5); การตรวจ placeholder ใน double-quoted identifier, backtick, `[...]` หรือ `$tag$` string (ดู R7-Q-2)
- การเพิ่ม log / dialog ใหม่สำหรับกรณีบันทึก Script Groups ล้มเหลว (error dialog ของ `save_script_groups()` เพียงพอ), การเปลี่ยนข้อความ error เดิม และ `import_script_groups` (แก้แล้วใน Round 6)
- Refactor / rename / commit

### R7-3. User stories

- **R7-US-1**: ในฐานะผู้ใช้ Windows ภาษาไทยที่รันแอปหรือ test โดย redirect output ฉันต้องการให้การบันทึก Profile ที่ล้มเหลวยังแสดง error และ rollback เสมอ เพื่อไม่ให้ข้อมูลในหน่วยความจำไม่ตรงกับไฟล์
- **R7-US-2**: ในฐานะผู้ใช้ที่มี Job รุ่นเก่าที่ไม่มี Profile กำกับ ฉันต้องการให้ปุ่ม ▶ ทำงานแบบเดียวกับ Run All เพื่อให้แอปทำงานสอดคล้องกัน
- **R7-US-3**: ในฐานะผู้ใช้ที่ export Job ที่มี SQL ยาวมาก ฉันต้องการให้ workbook เปิดใน Excel ได้โดยไม่ต้องซ่อม และรู้ว่า Job ไหนมีข้อความถูกเว้นว่าง
- **R7-US-4**: ในฐานะผู้ใช้ที่เขียน `':ACC'` หรือ `'{ACC}'` ใน SQL template ฉันต้องการเห็น placeholder นั้นในตัวเลือก Parameter ของ Load Excel เหมือนก่อน Round 5
- **R7-US-5**: ในฐานะผู้ใช้หน้าต่าง Script Groups ขณะ `script_groups.json` บันทึกไม่ได้ ฉันต้องการให้หน้าต่างไม่แสดงการเปลี่ยนแปลงที่ไม่ได้ถูกบันทึก

### R7-4. Acceptance criteria

วิธีทดสอบทุกข้อเป็น `unittest` ใช้ stub (`DatabaseConnectorGUI.__new__`), `unittest.mock.patch` (`messagebox`, `write_json_atomic`, `APP_DIR`, `sys.stdout`) และ `tempfile`; ไม่ต่อฐานข้อมูลจริง ไฟล์ test ใหม่ต่อ bug ตามที่ระบุ

#### R7-1 — console print ไม่ทำลาย contract `return False` (`tests/test_r7_console_print.py`)

stdout ที่ encode "❌" ไม่ได้ หมายถึง `io.TextIOWrapper(io.BytesIO(), encoding="cp874", errors="strict")` ที่ patch แทน `sys.stdout`

| AC | Given / When / Then |
|---|---|
| R7-AC-1 | **Given** stdout ที่ encode "❌" ไม่ได้ และ `write_json_atomic` raise `OSError` **When** เรียก `save_profiles()` **Then** ไม่มี exception หลุดออก, คืน `False` (`assertIs`), `messagebox.showerror` ถูกเรียก 1 ครั้งด้วย title `"Save Error"` และข้อความเดิม (`❌ Cannot save profile!\n\nError: <error>\n\nPath: <config_file>`) และไฟล์ profile บนดิสก์ไม่เปลี่ยน |
| R7-AC-2 | **Given** stdout ที่ `write` raise `OSError` (เช่น pipe ปิด) หรือ `sys.stdout` เป็น `None` และ `write_json_atomic` raise **When** เรียก `save_profiles()` **Then** ผลเหมือน R7-AC-1 (คืน `False`, `showerror` 1 ครั้ง) |
| R7-AC-3 | **Given** stdout ที่ encode "❌" ไม่ได้ **When** เรียก `save_jobs()` และ `save_script_groups()` ทั้งกรณี blocked และกรณี `write_json_atomic` raise และเรียก `save_profiles()` กรณี `_profiles_save_blocked = True` **Then** ทุกกรณีคืน `False` ไม่มี exception และ `showerror` 1 ครั้งด้วยข้อความเดิม |
| R7-AC-4 | **Given** stdout ที่ encode "❌" ไม่ได้ และ `write_json_atomic` raise **When** เรียก caller ของ R5-AC-2 อย่างน้อย `delete_profile` และ `do_import` **Then** `saved_profiles` ถูก rollback เท่ากับค่าก่อน action, ไม่มี success message / log และไม่มี exception หลุดออก |
| R7-AC-5 | **Given** stdout เป็น UTF-8 (เช่น `io.StringIO`) และ `write_json_atomic` raise **When** `save_profiles()` **Then** ยังพิมพ์ `error_msg` ลง stdout เหมือนเดิม (คงพฤติกรรมเดิมเมื่อ print ได้ — ดู R7-Q-1) และคืน `False`; เมื่อบันทึกสำเร็จคืน `True` ไม่พิมพ์อะไร |

#### R7-2 — `run_job` กับ Job ที่ไม่มี key `"profile"` (`tests/test_r7_run_job_legacy_profile.py`)

| AC | Given / When / Then |
|---|---|
| R7-AC-6 | **Given** Job ไม่มี key `"profile"` และ `profile_combo.get()` เป็น `"P1"` **When** เรียก `run_job(job)` **Then** ไม่มีบรรทัด `⛔ Run Job ไม่ได้เริ่มงาน` ใน `results_text` และทำงานต่อไปถึงขั้นถัดไป (`_capture_run_target` / `_block_if_profile_mismatch` ถูกเรียก) เหมือน Job ที่ `"profile": "P1"` |
| R7-AC-7 | **Given** Job มี `"profile": "P2"` และ Profile ที่เลือกเป็น `"P1"` **When** `run_job(job)` **Then** ยังปฏิเสธตาม R5-AC-1 (log `⛔ ... 'P2' ... 'P1'`, return ก่อน confirmation / thread) — test เดิม `tests/test_bugfix_c1.py` ยังผ่านโดยไม่แก้ |
| R7-AC-8 | **Given** `saved_jobs` มี Job ที่ไม่มี key `"profile"` และ Profile ที่เลือกคือ `"P1"` **When** ตรวจว่า Job นั้นอยู่ใน `_current_profile_jobs()` **Then** `run_job` ตัดสิน "ตรง Profile" ตรงกันกับรายการนั้นทุกกรณีใน matrix: ไม่มี key, `"P1"`, `"P2"` (ความสอดคล้องกับ list / Run All) |

#### R7-3 — ขยายการตรวจ 32,767 ของ C-2 (`tests/test_r7_excel_cell_limit.py`)

นิยาม: "เกิน limit" = `len(value.encode("utf-16-le")) // 2 > 32767`; "cell ว่าง" = ค่าใน workbook เป็น `None` หรือ `""`; test เปิดไฟล์ที่ export จริงด้วย `openpyxl.load_workbook` (เหมือนแนวทาง `tests/test_bugfix_c2.py`)

| AC | Given / When / Then |
|---|---|
| R7-AC-9 | **Given** Job ที่ไม่ใช่ SELECT (ไป sheet Skipped) และ `query` ยาวเกิน limit **When** `export_jobs_to_excel` **Then** cell `Query` ของ sheet นั้นว่าง, cell `Status` = `Skipped` และ `Message` คงเดิม, Execution Logs มีบรรทัด warning ที่มีชื่อ Job, ชื่อ column `Query` และ `32,767`; ตัวนับยังเป็น Skipped (ดู R7-Q-3) |
| R7-AC-10 | **Given** Job ที่ล้มเหลว (sheet Failed) และ `query` และ/หรือ `str(job_err)` ยาวเกิน limit **When** export **Then** cell `Query` / `Error` ที่เกินว่าง, cell ที่ไม่เกินคงค่าเดิม, log warning ระบุชื่อ Job และชื่อ column ที่เกินแต่ละ column; ตัวนับยังเป็น Failed |
| R7-AC-11 | **Given** Job ที่ query คืน DataFrame ว่าง (sheet No Data) และ SQL มีบรรทัดหนึ่งยาวเกิน limit **When** export **Then** cell ของบรรทัดนั้นว่าง, บรรทัด SQL อื่นอยู่แถวเดิม (เริ่มแถว 3 ตามเดิม) ค่าเดิม, log warning ระบุชื่อ Job, ว่าเป็นข้อความ SQL และเลขบรรทัด; Job นับเป็น Warning แทน Success (`warnings` +1, `ok` ไม่เพิ่ม) |
| R7-AC-12 | **Given** Job สำเร็จมีข้อมูล และ SQL annotation มีบรรทัดยาวเกิน limit **When** export **Then** cell annotation ของบรรทัดนั้นว่าง, บรรทัดอื่นอยู่ตำแหน่งเดิม, log warning ระบุ Job / SQL / เลขบรรทัด, log `Status: ⚠️ Warning` และนับเป็น Warning; ถ้า cell ผลลัพธ์ของ Job เดียวกันก็เกินด้วย Job ยังนับ Warning **1 ครั้ง** |
| R7-AC-13 | **Given** ข้อความยาว 32,767 UTF-16 units พอดี (ทั้ง ASCII และอักษรไทย BMP) **When** export ในตำแหน่งใดก็ได้ของ R7-AC-9 ถึง 12 และ cell ผลลัพธ์ **Then** เขียนครบไม่ตัด, ไม่มี warning, นับตามสถานะเดิม; ที่ 32,768 units → เว้นว่างและ warning |
| R7-AC-14 | **Given** cell ผลลัพธ์ (C-2 เดิม) มีข้อความ `"😀" * 16384` (16,384 code points = 32,768 UTF-16 units) **When** export **Then** cell นั้นว่างและมี warning ตาม C-2 (เดิมผ่านเพราะนับ code point); ข้อความ `"😀" * 16383 + "a"` (32,767 units) เขียนครบ |
| R7-AC-15 | **Given** ไม่มีข้อความเกิน limit **When** export Skipped / Failed / No Data / Success **Then** workbook, log และตัวนับเหมือนก่อนแก้ทุกประการ; `force_literal_strings` / `write_literal_cell` ยังกำหนด `data_type = "s"` ตาม R5-AC-9 (test `tests/test_bugfix_c2.py`, `tests/test_bugfix_m2.py` เดิมผ่านโดยไม่แก้) |

#### R7-4 — placeholder ที่อยู่ใน quote ทั้ง literal (`tests/test_r7_quoted_placeholder.py`)

| AC | Given / When / Then |
|---|---|
| R7-AC-16 | **Given** SQL `WHERE a IN (':ACC')` และ `WHERE a = '{acc}'` และ `WHERE a = '{{ ACC }}'` **When** `_detect_sql_placeholders` **Then** คืน `[":ACC"]`, `["{acc}"]` และ `["{{ ACC }}"]` ตามลำดับ (ค่าที่คืนไม่มีเครื่องหมาย quote และเป็นรูปเดียวกับ placeholder ที่ไม่มี quote เพื่อส่งเข้า `_render_sql_template` ได้) |
| R7-AC-17 | **Given** literal ที่มี placeholder อยู่ภายในข้อความที่ยาวกว่า: `'HH24:MI:SS'`, `'text {x}'`, `'a :ACC'`, `' :ACC'`, `':ACC '`, `':ACC:B'`, `'::x'`, `':1'` และ `''` **When** detect **Then** ไม่คืน placeholder ใดเลย (M-1 ยังคงอยู่); comment `/* ':ACC' */`, `-- ':ACC'` ไม่ถูกตรวจ |
| R7-AC-18 | **Given** SQL มีทั้ง `:ACC` และ `':ACC'` หรือ `{ACC}` และ `'{ACC}'` **When** detect **Then** แต่ละชื่อปรากฏครั้งเดียว และลำดับเป็นตามตำแหน่งที่พบครั้งแรกใน SQL |
| R7-AC-19 | **Given** template `WHERE a IN (':ACC')` **When** detect แล้วนำค่าที่ได้ส่งเข้า `_render_sql_template({"ACC": (":ACC", "'1'")})` **Then** ได้ `WHERE a IN ('1')` (สอดคล้องกับ `test_quoted_parameter_still_replaced`); และรูป `'{ACC}'` render ได้ผลแบบเดียวกัน |
| R7-AC-20 | **Given** test เดิม `tests/test_bugfix_m1.py` ซึ่งมี `':literal'` **When** รันหลังแก้ **Then** ปรับเฉพาะค่าที่คาดหวังเป็น `[":real_bind", "{braced}", "{{double_braced}}", ":literal"]` (ผลโดยตรงจากการตัดสินใจของผู้ใช้ใน R7-4) ส่วน `'HH24:MI:SS'`, `'text {not_a_bind}'`, comment และ `value::type` ยังไม่ถูกตรวจ |

#### R7-5 — rollback ใน 8 action ของหน้าต่าง Script Groups (`tests/test_r7_script_groups_dialog_rollback.py`)

วิธีทดสอบ: สร้าง `tk.Tk()` แบบ `withdraw()` (skip ถ้าไม่มี display ตามแนวทาง `tests/test_r3_script_groups_io.py:1715-1756`), `APP_DIR` = tempdir, เปิด `show_script_groups_dialog()` แล้วกดปุ่มตามชื่อในตาราง R7-2 ด้วย `invoke()`; patch `_ask_group_text`, `_edit_group_script_dialog`, `_pick_jobs_dialog`, `_current_profile_jobs`, `messagebox.askyesno` ให้คืนค่าที่ต้องการ; "บันทึกล้มเหลว" ทดสอบทั้งสองแบบ: `_script_groups_save_blocked = True` และ `write_json_atomic` raise `OSError`

| AC | Given / When / Then |
|---|---|
| R7-AC-21 | **Given** Profile `P1` มีหลายกลุ่ม (รวมกลุ่มของ Profile อื่น และ script ที่มีค่าซ้อน dict / list) และบันทึกล้มเหลว **When** ทำแต่ละ action ทั้ง 8 ในตาราง R7-2 (`move_script` ทั้ง `↑` และ `↓`) **Then** หลัง action: `self.script_groups == snapshot` ที่ deep-copy ไว้ก่อนกด (ทุกระดับ ลำดับ และจำนวน), `self.script_groups` เป็น list object เดิม (`is`), `save_script_groups` ถูกเรียก 1 ครั้ง และ `script_groups.json` บนดิสก์ไม่เปลี่ยน |
| R7-AC-22 | **Given** เหมือน R7-AC-21 **When** action จบ **Then** หน้าต่างแสดงสถานะหลัง rollback: รายการใน groups listbox และ scripts listbox ตรงกับข้อมูลใน snapshot (ไม่มีกลุ่มใหม่ / ชื่อใหม่ / script ใหม่ / ลำดับใหม่ และกลุ่มหรือ script ที่ถูกลบกลับมา) และการเลือกเป็นไปตาม R7-Q-4 |
| R7-AC-23 | **Given** เหมือน R7-AC-21 **When** action จบ **Then** มี `messagebox.showerror` 1 ครั้งจาก `save_script_groups()` เท่านั้น ไม่มี `showinfo` หรือข้อความสำเร็จอื่น และไม่มี exception |
| R7-AC-24 | **Given** action หนึ่งล้มเหลวและถูก rollback แล้ว (เช่น Rename แล้วตามด้วย Edit Script ที่ล้มเหลว) **When** ปลดสาเหตุ (`_script_groups_save_blocked = False` / เลิก raise) แล้วทำ action ถัดไปที่บันทึกสำเร็จ (เช่น `＋ Add SQL` บนกลุ่มที่เลือก) **Then** การแก้ไขเกิดกับ object ใน `self.script_groups` ปัจจุบัน (ไม่ใช่ object ค้างก่อน rollback): `script_groups.json` ที่อ่านกลับมามี script ใหม่ในกลุ่มชื่อเดิม และข้อมูลในหน่วยความจำเท่ากับไฟล์ (ตัด key `_*` / `run_index`) |
| R7-AC-25 | **Given** `save_script_groups()` คืน `True` **When** ทำแต่ละ action ทั้ง 8 **Then** พฤติกรรมเหมือนเดิม: ข้อมูลในหน่วยความจำและไฟล์เปลี่ยนตาม action, `save_script_groups` ถูกเรียก 1 ครั้ง, การ refresh / การเลือกหลัง action เหมือนเดิม (`new_group` / `rename_group` เลือกชื่อใหม่, `add_sql` / `add_from_jobs` เลือก script สุดท้าย, `edit_script` เลือก index เดิม, `move_script` เลือก index ปลายทาง) และไม่มี `showerror` |
| R7-AC-26 | **Given** action ถูกยกเลิกหรือไม่มีผล (dialog คืนค่าว่าง, ชื่อซ้ำ, `askyesno` ตอบ No, ไม่ได้เลือกกลุ่ม / script, `move_script` เกินขอบ) **When** ทำ action **Then** ไม่เรียก `save_script_groups`, ไม่มี rollback, `self.script_groups` ไม่เปลี่ยน — พฤติกรรมเดิม |
| R7-AC-27 | **Given** test เดิมของหน้าต่าง Script Groups (`tests/test_r3_script_groups_io.py`, `tests/test_script_groups_block.py`, `tests/test_r6_import_save_failure.py`) **When** รันหลังแก้ **Then** ผ่าน; ถ้า test ใด mock `save_script_groups` ให้คืน `None` ในทางสำเร็จของ 8 action ให้ปรับเฉพาะค่าคืนเป็น `True` ตามหลัก R6-5 ไม่แก้ assertion; implementation ใช้ `if not self.save_script_groups():` |

#### Regression

| AC | Given / When / Then |
|---|---|
| R7-AC-28 | **Given** แก้ครบ R7-1 ถึง R7-5 **When** รัน `python -m unittest discover -s tests -p "test_*.py"` สองแบบบนเครื่อง Windows ที่ code page เป็น `cp874`: (ก) ตั้ง `PYTHONIOENCODING=utf-8` และ (ข) **ไม่** ตั้ง `PYTHONIOENCODING` / `PYTHONUTF8` และ redirect stdout+stderr ไปยัง pipe หรือไฟล์ (เช่น `... 2>&1 \| cat` หรือ `> out.txt 2>&1`) **Then** ทั้งสองแบบได้ `OK` ไม่มี failure / error (แบบ (ข) ต้องผ่านด้วยผลของ R7-1 ซึ่งเดิม error ที่ `test_bugfix_h3.SaveProfilesResultTests.test_save_profiles_returns_false_when_write_raises`) และจำนวน test เท่ากันทั้งสองแบบ |

**สรุปจำนวน AC Round 7**: 28 ข้อ — unittest ทั้งหมด (R7-1: 5, R7-2: 3, R7-3: 7, R7-4: 5, R7-5: 7, Regression: 1)

### R7-5. ข้อจำกัด / สมมติฐาน

- Minimal diff ใน `database_connect_gui.py`: ไม่ refactor ไม่ rename; ใช้ Python 3, PEP 8, type hints
- **R7-1**: ครอบเฉพาะ `print` ใน failure path ด้วย `try / except Exception: pass` (หรือเทียบเท่า) ข้อความใน `showerror` ไม่เปลี่ยน; ไม่แก้ `print` อื่นในไฟล์
- **R7-2**: เปลี่ยนเฉพาะค่า default ของ `job.get("profile", ...)` ใน `run_job`; ข้อความ `⛔` เดิมคงไว้ (กรณี key มีค่าเป็น `None` ชัดเจนยังเทียบแบบเดียวกับ `update_jobs_list`)
- **R7-3 การตัดสินใจเรื่อง UTF-16**: **ใช้** การนับ UTF-16 code units (`len(s.encode("utf-16-le")) // 2`) เพราะต้นทุนต่ำ (เปลี่ยนการนับใน helper เดียว) และตรงกับวิธีที่ Excel นับ; ใช้ helper เดียวกันกับ cell ผลลัพธ์เดิมของ C-2 และ cell ใหม่ เพื่อให้ผลสอดคล้องกัน ผลข้างเคียง: cell ผลลัพธ์ที่มีอักขระนอก BMP ซึ่งเดิมผ่านอาจถูกเว้นว่างพร้อม warning (R7-AC-14) ซึ่งเป็นพฤติกรรมที่ถูกต้องตาม Excel
- **R7-3**: พฤติกรรมเมื่อเกิน = เหมือน C-2 คือเว้น cell ว่าง (ไม่ตัดข้อความ); การตรวจทำก่อนเขียน cell / ก่อน `to_excel` ของ Skipped / Failed; ข้อความ log ใหม่ต้องมีชื่อ Job, ตำแหน่ง (ชื่อ column หรือ "SQL" + เลขบรรทัด) และ `32,767` รูปแบบอื่นกำหนดได้ในขั้น design
- **R7-4**: นับเฉพาะ token ชนิด `"string"` ที่ขึ้นต้นและลงท้ายด้วย `'` (ไม่รวม `$tag$`); เนื้อหาระหว่าง quote ต้อง `fullmatch` กับ `:[A-Za-z_][A-Za-z0-9_]*` หรือ `_SQL_BRACED_PLACEHOLDER_RE` ทั้งหมด ไม่ trim ช่องว่าง (สอดคล้องกับ regex ของ `_render_sql_template` ที่ต้องมี quote ติดกับ placeholder)
- **R7-5**: snapshot ด้วย `copy.deepcopy(self.script_groups)` ก่อนการแก้ข้อมูลแต่ละครั้ง (หลังผ่านการตรวจ cancel / ชื่อซ้ำ / askyesno) rollback ด้วย `self.script_groups[:] = snapshot` แล้วเรียก `refresh_groups(...)` (ไม่ใช่แค่ `refresh_scripts`) เพราะ `state["groups"]` ถือ reference ของ dict กลุ่มเดิม ซึ่งหลัง rollback กลายเป็น object ค้าง (R7-AC-24)
- Test ของ R7-5 ต้องใช้ Tk จริง จึง skip ได้เมื่อไม่มี display (แนวทางเดียวกับ test เดิม)
- Test เดิมที่ต้องปรับ: `tests/test_bugfix_m1.py` (ค่าคาดหวังตาม R7-AC-20) และ mock ที่คืน `None` ตาม R7-AC-27 เท่านั้น
- ห้าม commit

### R7-6. คำถามที่ยังไม่มีคำตอบ

ทุกข้อมีคำตอบที่แนะนำซึ่ง AC ข้างต้นใช้เป็นค่าเริ่มต้นแล้ว ถ้าผู้ใช้ต้องการแบบอื่นให้แจ้งก่อนเริ่ม design

| # | คำถาม | คำตอบที่แนะนำ (default) |
|---|---|---|
| R7-Q-1 | R7-1: คง `print(error_msg)` ไว้แบบมี guard หรือลบทิ้ง / เปลี่ยนเป็นข้อความ ASCII | คงไว้แบบมี guard — เมื่อ console รองรับยังเห็นข้อความเดิม (R7-AC-5) และ diff เล็กที่สุด |
| R7-Q-2 | R7-4: ต้องตรวจ placeholder ใน double-quoted `":ACC"` ด้วยหรือไม่ (`_render_sql_template` รองรับ `"` แต่ใน SQL เป็น identifier และ `_scan_sql` จัดเป็น `ident`) | ไม่ตรวจ — ผู้ใช้ระบุ "string literal" ซึ่งคือ `'...'` เท่านั้น |
| R7-Q-3 | R7-3: Job ที่ไป sheet Skipped / Failed และมีข้อความเกิน limit ควรนับเป็น Warning เพิ่มหรือไม่ | ไม่ — คงนับเป็น Skipped / Failed (สถานะที่รุนแรงกว่า และไม่นับซ้ำสองหมวด) แต่เขียน log warning; Job ที่ไป No Data หรือ Success เท่านั้นที่เปลี่ยนเป็น Warning |
| R7-Q-4 | R7-5: หลัง rollback ควรเลือกกลุ่ม / script ใดในหน้าต่าง | เลือกกลุ่มที่เลือกอยู่ก่อนกด (ตามชื่อก่อนแก้) และ script index ก่อนกด (หรือ index ใกล้สุดที่มีอยู่); สำหรับ `new_group` คงกลุ่มที่เลือกอยู่เดิม |
| R7-Q-5 | R7-3: บรรทัด SQL ที่เกิน limit ควรเว้นว่าง (เหมือน C-2) หรือตัดข้อความให้เหลือ 32,767 | เว้นว่างตามที่ผู้ใช้สั่ง "ใช้พฤติกรรมเดียวกับ C-2" — บันทึกไว้เพื่อยืนยันเท่านั้น |
