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

---

# Round 8 — Bugfix B1: `load_jobs` ทิ้ง Job ทั้งหมดเมื่อเขียน migration กลับไม่สำเร็จ

> ใช้เลข `R8-AC-x` และ `R8-Q-x` แยกจาก Round ก่อนหน้า ไม่แก้เนื้อหา Round ก่อนหน้า
> ที่มา: รายงาน bug-hunter ข้อ B1 (ยืนยันด้วย probe แล้ว) ผู้ใช้สั่งให้แก้ **เฉพาะ B1** — บัค B2 ถึง B16 อยู่นอกขอบเขตทั้งหมด
> ไฟล์ที่เกี่ยวข้อง: `database_connect_gui.py` — `write_json_atomic` (`:71-79`), `preserve_unreadable_file` (`:82-96`), `__init__` เรียก `self.saved_jobs = self.load_jobs()` (`:2374`), `load_jobs` (`:9482-9521`, จุดบัค `:9513-9514` และ `:9518-9521`), `_handle_unreadable_file` (`:9523-9545`), `save_jobs` (`:9547-9561`)
> เลขบรรทัดอ้างอิงไฟล์ ณ วันที่เขียน spec (2026-11-20) อาจคลาดเคลื่อนเล็กน้อย

### R8-1. เป้าหมาย

`load_jobs` อ่านและ parse `saved_jobs.json` แล้วเติม key `"profile"` ให้ Job รุ่นเก่า (ชื่อ Profile แรกใน `saved_profiles` หรือ `"DEFAULT"`) จากนั้นเขียนกลับด้วย `write_json_atomic(self.jobs_file, jobs, indent=4)` **ภายใน `try` เดียวกับการอ่าน** ถ้าการเขียนกลับล้ม (เช่น OneDrive ล็อกไฟล์ → `os.replace` raise `PermissionError`) exception ตกไป `except Exception` ที่ถือว่า "ไฟล์อ่านไม่ได้":

1. แสดง warning `Cannot read saved_jobs.json: ...` ทั้งที่ไฟล์อ่านได้ปกติ
2. สร้างสำเนา `saved_jobs_unreadable_<time>.json` และ `return []` → รายการ Job ในแอปว่าง
3. เพราะสำเนาสำเร็จ `_jobs_save_blocked` จึงเป็น `False` → Save Job ครั้งถัดไปเขียนทับไฟล์ด้วยรายการที่มีแค่ Job ใหม่ = **Job เดิมหายถาวร** (เหลือเพียงในสำเนา `_unreadable_`)
4. ถ้าล้มที่ `os.replace` จะมีไฟล์ `saved_jobs.json.tmp` ค้าง

หลักฐาน probe: patch `os.replace` ให้ raise `PermissionError` → `load_jobs()` คืน `[]`, `_jobs_save_blocked` = `False`, เรียก `save_jobs()` หลังเพิ่ม Job `NEW` แล้วไฟล์เหลือ `[{'name': 'NEW', ...}]`

เป้าหมาย: เมื่อ parse สำเร็จแล้ว ความล้มเหลวของการเขียน migration กลับต้อง **ไม่** ถูกตีความเป็น "ไฟล์อ่านไม่ได้" — แอปต้องได้ Job ครบ (มี `"profile"` ใน memory) และ save ครั้งถัดไปต้องไม่ทำ Job หาย

ผู้ได้ประโยชน์: ผู้ใช้ที่มี `saved_jobs.json` รุ่นเก่า (Job ไม่มี key `"profile"`) และเก็บโฟลเดอร์แอปบน OneDrive หรือที่อื่นที่ไฟล์อาจถูกล็อกชั่วคราวตอนเปิดแอป

### R8-2. ขอบเขต

#### In scope

- แยกการเขียน migration กลับ (`write_json_atomic` ใน `load_jobs`) ออกจาก `try` ของการอ่าน / parse / validate: ถ้าการเขียนกลับ raise `Exception` ใด ๆ ให้
  - คืน `jobs` ที่อ่านได้ (รวม `"profile"` ที่เติมแล้วใน memory)
  - ไม่เรียก `_handle_unreadable_file` (ไม่มี warning "Cannot read", ไม่มีสำเนา `_unreadable_`) และไม่ตั้ง `_jobs_save_blocked = True`
  - เขียน log ลง console ตาม R8-Q-1 โดย `print` ต้องไม่ทำให้ `load_jobs` raise (แนวทางเดียวกับ R7-1 — ครอบ `try / except Exception: pass`)
  - ลบไฟล์ `<jobs_file>.tmp` ที่อาจค้างจาก `write_json_atomic` แบบ best-effort ตาม R8-Q-2 (ถ้าลบไม่ได้ให้ข้าม ไม่ raise)
- กรณีไฟล์อ่านไม่ได้จริง (JSON เสีย, โครงสร้างไม่ใช่ list ของ dict, เปิดไฟล์ไม่ได้, decode ไม่ได้) คงพฤติกรรมเดิมทุกประการ
- กรณีไม่มี Job ต้อง migrate คงพฤติกรรมเดิม (ไม่เขียนไฟล์)

#### Out of scope

- บัค B2 ถึง B16 จากรายงาน bug-hunter ทั้งหมด
- การแก้ `write_json_atomic` (ฟังก์ชันกลางที่ `save_jobs` / `save_profiles` / `save_script_groups` ใช้ร่วม) รวมถึงการให้มันลบ `.tmp` เองเมื่อล้ม
- การแก้ `_handle_unreadable_file`, `preserve_unreadable_file`, `save_jobs` และข้อความ dialog เดิม
- `load_profiles`, `load_script_groups` หรือ loader อื่น แม้จะมีรูปแบบคล้ายกัน
- การเปลี่ยนกฎเลือก Profile ที่เติมให้ Job รุ่นเก่า (Profile แรก หรือ `"DEFAULT"`), การเปลี่ยน `indent=4` ของการเขียนกลับ
- การ retry การเขียนกลับ หรือการแสดง dialog ใหม่ (ดู R8-Q-1)
- Refactor / rename / commit

### R8-3. User stories

- **R8-US-1**: ในฐานะผู้ใช้ที่มี Job รุ่นเก่าและเปิดแอปขณะ OneDrive ล็อก `saved_jobs.json` ฉันต้องการเห็น Job ของฉันครบ เพื่อทำงานต่อได้ตามปกติ
- **R8-US-2**: ในฐานะผู้ใช้คนเดียวกัน ฉันต้องการให้การ Save Job ครั้งถัดไปไม่ลบ Job เดิมของฉัน เพื่อไม่สูญเสียข้อมูลถาวร
- **R8-US-3**: ในฐานะผู้ใช้ที่ไฟล์ `saved_jobs.json` เสียจริง ฉันต้องการให้แอปยังเก็บสำเนาและเตือนเหมือนเดิม

### R8-4. Acceptance criteria

วิธีทดสอบทุกข้อเป็น `unittest` ใช้ stub (`DatabaseConnectorGUI.__new__`, ตั้ง `jobs_file` ใน `tempfile.TemporaryDirectory()`, `saved_profiles`, `_jobs_save_blocked = False` ตามแนวทาง `tests/test_r2_reset_parameter_qa.py:579-590`), `unittest.mock.patch` สำหรับ `messagebox`, `os.replace` / `write_json_atomic` (ของ module `database_connect_gui`) และ `sys.stdout`; ไม่เปิดหน้าต่าง Tk จริง ไฟล์ test ใหม่: `tests/test_r8_load_jobs_writeback.py`

นิยาม:
- "ไฟล์รุ่นเก่า" = `saved_jobs.json` ที่เป็น list ของ Job อย่างน้อย 2 ตัว โดยมีอย่างน้อย 1 ตัวไม่มี key `"profile"` และอย่างน้อย 1 ตัวมี `"profile"` อยู่แล้ว (เช่น `"P2"`) รวม Job ที่มีค่าซ้อน (dict / list) และอักษรไทย
- "เขียนกลับล้ม" ทดสอบสองแบบ: (ก) patch `os.replace` ให้ raise `PermissionError` (เหมือน probe — `.tmp` ถูกสร้างแล้ว) และ (ข) patch `write_json_atomic` ให้ raise `OSError` (ล้มก่อนสร้าง `.tmp`)
- "ไฟล์บนดิสก์ไม่เปลี่ยน" = bytes ของ `saved_jobs.json` เท่ากับก่อนเรียก

#### เขียน migration กลับล้มเหลว

| AC | Given / When / Then |
|---|---|
| R8-AC-1 | **Given** ไฟล์รุ่นเก่า, `saved_profiles = {"P1": {...}, "P2": {...}}` และเขียนกลับล้ม (ทั้งแบบ ก และ ข) **When** เรียก `load_jobs()` **Then** ไม่มี exception หลุดออก, คืน list ที่จำนวน ลำดับ และค่าทุก key ตรงกับไฟล์ ยกเว้น Job ที่ไม่มี `"profile"` ได้ `"profile": "P1"` (Profile แรก) และ Job ที่มี `"profile": "P2"` อยู่แล้วคงเป็น `"P2"` |
| R8-AC-2 | **Given** เหมือน R8-AC-1 แต่ `saved_profiles = {}` **When** `load_jobs()` **Then** Job ที่ไม่มี key ได้ `"profile": "DEFAULT"` และ Job อื่นครบเหมือน R8-AC-1 |
| R8-AC-3 | **Given** เหมือน R8-AC-1 **When** `load_jobs()` **Then** ไม่มีการเรียก `messagebox.showwarning` (ไม่มีข้อความ `Cannot read saved_jobs.json`), ไม่มี `showerror` / `showinfo` ใด ๆ และ `_handle_unreadable_file` ไม่ถูกเรียก |
| R8-AC-4 | **Given** เหมือน R8-AC-1 **When** `load_jobs()` **Then** ใน directory ของ `jobs_file` ไม่มีไฟล์ที่ชื่อมี `_unreadable_` และ `_jobs_save_blocked` ยังเป็น `False` (ไม่ถูกตั้งเป็น `True`) |
| R8-AC-5 | **Given** เหมือน R8-AC-1 **When** `load_jobs()` **Then** `saved_jobs.json` บนดิสก์ไม่เปลี่ยน (bytes เท่ากับก่อนเรียก — Job รุ่นเก่ายังไม่มี `"profile"` ในไฟล์) |
| R8-AC-6 | **Given** เหมือน R8-AC-1 แบบ (ก) ซึ่ง `write_json_atomic` สร้าง `saved_jobs.json.tmp` ก่อน `os.replace` ล้ม **When** `load_jobs()` จบ **Then** ไม่มีไฟล์ `saved_jobs.json.tmp` เหลืออยู่ (R8-Q-2); และถ้าการลบ `.tmp` เองก็ล้ม (patch `os.remove` ให้ raise `OSError`) `load_jobs()` ยังคืน Job ครบตาม R8-AC-1 ไม่มี exception |
| R8-AC-7 | **Given** เหมือน R8-AC-1 และ stdout เป็น `io.StringIO` **When** `load_jobs()` **Then** มีบรรทัด log ลง stdout 1 ครั้งที่มีชื่อไฟล์ `saved_jobs.json` และข้อความ error ของ exception (R8-Q-1); และเมื่อ stdout เป็น `io.TextIOWrapper(io.BytesIO(), encoding="cp874", errors="strict")` หรือ `write` raise `OSError` ผลของ R8-AC-1 ถึง R8-AC-5 ยังเป็นจริง ไม่มี exception |

#### Save ครั้งถัดไปหลังเขียนกลับล้ม

| AC | Given / When / Then |
|---|---|
| R8-AC-8 | **Given** `load_jobs()` ตาม R8-AC-1 แล้ว (ตั้ง `stub.saved_jobs` = ผลที่คืน) และปลดการ patch ที่ทำให้เขียนล้ม **When** append Job ใหม่ `NEW` แล้วเรียก `save_jobs()` **Then** คืน `True`, ไม่มี `showerror`, และ `saved_jobs.json` ที่อ่านกลับมามี Job เดิมทุกตัว (ค่าเดิม + `"profile"` ที่เติมแล้ว) ตามด้วย `NEW` — ตรงข้ามกับผล probe ที่เหลือแค่ `[{'name': 'NEW', ...}]` |
| R8-AC-9 | **Given** เหมือน R8-AC-8 แล้ว **When** เรียก `load_jobs()` อีกครั้ง (ไม่มีการ patch) **Then** ไม่มีการเขียนไฟล์ (ไม่มี Job ต้อง migrate แล้ว — `write_json_atomic` ไม่ถูกเรียก) และคืน list เท่ากับที่บันทึกใน R8-AC-8 |

#### กรณีเดิมที่ต้องไม่เปลี่ยน (regression lock)

| AC | Given / When / Then |
|---|---|
| R8-AC-10 | **Given** ไฟล์รุ่นเก่าและการเขียนกลับสำเร็จ **When** `load_jobs()` **Then** พฤติกรรมเดิม: คืน Job ครบพร้อม `"profile"` ที่เติม, ไฟล์บนดิสก์ถูกเขียนใหม่ให้ทุก Job มี `"profile"` (`json.load` ได้ค่าเท่ากับที่คืน, เขียนด้วย `indent=4`), ไม่มี `.tmp` ค้าง, ไม่มี dialog, ไม่มีสำเนา `_unreadable_` |
| R8-AC-11 | **Given** ไฟล์ที่ทุก Job มี `"profile"` อยู่แล้ว (รวม list ว่าง `[]`) **When** `load_jobs()` **Then** คืน list เท่ากับไฟล์, `write_json_atomic` ไม่ถูกเรียก (assert ด้วย mock wrapper), ไฟล์บนดิสก์ไม่เปลี่ยน (bytes และ mtime) และไม่มี dialog |
| R8-AC-12 | **Given** ไฟล์อ่านไม่ได้จริงแต่ละแบบ: JSON เสีย (เช่น `[{"name": "a",`), JSON ที่ไม่ใช่ list (`{}`), list ที่มีสมาชิกไม่ใช่ dict (`[1]`), และ bytes ที่ decode UTF-8 ไม่ได้ **When** `load_jobs()` **Then** พฤติกรรมเดิม: คืน `[]`, `messagebox.showwarning` ถูกเรียก 1 ครั้งด้วย title `"Saved Jobs not loaded"` และข้อความขึ้นต้น `Cannot read saved_jobs.json:`, มีสำเนา `saved_jobs_unreadable_<time>.json` ที่ bytes เท่ากับไฟล์เดิม, `_jobs_save_blocked` = `False`, `write_json_atomic` ไม่ถูกเรียก และไฟล์เดิมไม่เปลี่ยน |
| R8-AC-13 | **Given** ไฟล์อ่านไม่ได้จริง (JSON เสีย) และ `preserve_unreadable_file` คืน `None` (สำเนาไม่ได้) **When** `load_jobs()` **Then** พฤติกรรมเดิม: คืน `[]`, `_jobs_save_blocked` = `True` และ `save_jobs()` ครั้งถัดไปคืน `False` ไม่เขียนไฟล์ (test เดิม `tests/test_bugfix_h3.py`, `tests/test_r7_console_print.py` ยังผ่านโดยไม่แก้) |
| R8-AC-14 | **Given** ไม่มีไฟล์ `saved_jobs.json` **When** `load_jobs()` **Then** คืน `[]`, ไม่มี dialog, ไม่สร้างไฟล์ใด ๆ — พฤติกรรมเดิม |

#### Regression

| AC | Given / When / Then |
|---|---|
| R8-AC-15 | **Given** แก้ B1 ครบ **When** รัน `python -m unittest discover -s tests -p "test_*.py"` สองแบบตาม R7-AC-28: (ก) ตั้ง `PYTHONIOENCODING=utf-8` และ (ข) ไม่ตั้ง `PYTHONIOENCODING` / `PYTHONUTF8` บนเครื่อง code page `cp874` และ redirect stdout+stderr ไปไฟล์หรือ pipe **Then** ทั้งสองแบบได้ `OK` ไม่มี failure / error, จำนวน test เท่ากันทั้งสองแบบ และไม่น้อยกว่าจำนวนก่อนแก้ (1007) บวก test ใหม่ของ Round 8; test เดิมไม่ต้องแก้ |

**สรุปจำนวน AC Round 8**: 15 ข้อ — unittest ทั้งหมด (เขียนกลับล้ม: 7, save ครั้งถัดไป: 2, regression lock: 5, full suite: 1)

### R8-5. ข้อจำกัด / สมมติฐาน

- Minimal diff: แก้เฉพาะ `load_jobs` ใน `database_connect_gui.py`; ไม่ refactor ไม่ rename; PEP 8 + type hints เท่าที่จำเป็น
- การแยก `try`: การอ่าน / `json.load` / validate / เติม `"profile"` อยู่ใน `try` เดิม (ล้ม → `_handle_unreadable_file` ตามเดิม); การเขียนกลับอยู่ใน `try` แยกที่จับ `Exception` และไม่ส่งต่อไป `except` เดิม
- เมื่อเขียนกลับล้ม การ migrate ยังค้างอยู่เฉพาะใน memory; จะลงไฟล์เมื่อ (1) `save_jobs()` ครั้งถัดไปสำเร็จ (เขียน `self.saved_jobs` ทั้งหมดที่มี `"profile"` แล้ว) หรือ (2) เปิดแอปครั้งถัดไปแล้วเขียนกลับสำเร็จ — ถือว่ายอมรับได้เพราะไม่มีข้อมูลหาย
- `load_jobs` ถูกเรียกใน `__init__` (`:2374`) ก่อนสร้าง widget จึงยังไม่มี `results_text` สำหรับ log; การแจ้งจึงใช้ console (`print`) ตาม R8-Q-1
- `.tmp` ที่ค้างไม่ทำให้ข้อมูลเสีย (การ save ครั้งถัดไปเปิด `.tmp` แบบ `"w"` เขียนทับ) การลบจึงเป็น best-effort เพื่อความสะอาดเท่านั้น และทำใน `load_jobs` ไม่ใช่ใน `write_json_atomic` (R8-Q-2)
- สมมติว่า `saved_profiles` ถูกโหลดก่อน `load_jobs` (ตามลำดับใน `__init__` `:2373-2374`) ซึ่งเป็นพฤติกรรมเดิม
- ห้าม commit

### R8-6. คำถามที่ยังไม่มีคำตอบ

ทุกข้อมีคำตอบที่แนะนำซึ่ง AC ข้างต้นใช้เป็นค่าเริ่มต้นแล้ว ถ้าผู้ใช้ต้องการแบบอื่นให้แจ้งก่อนเริ่ม design

| # | คำถาม | คำตอบที่แนะนำ (default) |
|---|---|---|
| R8-Q-1 | เมื่อเขียน migration กลับล้ม ควรแจ้งผู้ใช้อย่างไร: (ก) log ลง console อย่างเดียว, (ข) แสดง `messagebox.showwarning` เพิ่ม, (ค) เงียบ | (ก) `print` 1 บรรทัดที่มีชื่อไฟล์และ error ครอบด้วย guard ตาม R7-1 — Job ครบใน memory และจะถูกบันทึกเมื่อ save ครั้งถัดไป จึงไม่ต้องรบกวนผู้ใช้ด้วย dialog ตอนเปิดแอป; ไม่มี `results_text` ให้ log ในจังหวะนี้ (R8-AC-3, R8-AC-7) |
| R8-Q-2 | ควรลบ `saved_jobs.json.tmp` ที่ค้างหลังเขียนกลับล้มหรือไม่ และลบที่ไหน | ลบแบบ best-effort ใน `load_jobs` (เฉพาะไฟล์ `<jobs_file>.tmp`, ลบไม่ได้ให้ข้าม) โดยไม่แก้ `write_json_atomic` ซึ่งใช้ร่วมกับ save อื่น — การแก้ `write_json_atomic` อยู่นอกขอบเขต B1 (R8-AC-6) ถ้าผู้ใช้ไม่ต้องการ ให้ตัด R8-AC-6 ออก |
| R8-Q-3 | หลังเขียนกลับล้ม ควรตั้ง flag ให้พยายาม migrate / เขียนกลับอีกครั้งในระหว่าง session หรือไม่ | ไม่ — `save_jobs()` ครั้งถัดไปเขียนข้อมูลที่ migrate แล้วอยู่แล้ว (R8-AC-8) การ retry เพิ่มเป็น scope creep |

---

# Round 9 — Bugfix B2: Load Preset ที่มี element เสียทำให้ Job ของ Profile ปัจจุบันหาย

> ใช้เลข `R9-AC-x` และ `R9-Q-x` แยกจาก Round ก่อนหน้า ไม่แก้เนื้อหา Round ก่อนหน้า
> ที่มา: รายงาน bug-hunter ข้อ B2 (ยืนยันด้วย probe แล้ว) ผู้ใช้สั่งให้แก้ **เฉพาะ B2** — บัค B3 ถึง B16 อยู่นอกขอบเขตทั้งหมด; การแก้ของ Round 8 (B1, `load_jobs`) ยังไม่ commit และห้ามแตะ
> ไฟล์ที่เกี่ยวข้อง: `database_connect_gui.py` — `load_preset_dialog` (`:5456-5602`): สร้างรายการ preset (`:5497-5513`, ตรวจเพียง `"jobs"` เป็น list ที่ `:5505`), `load_selected` (`:5515-5575`, จุดบัค: กรอง `self.saved_jobs` `:5547-5549` → loop `job["profile"] = ...` `:5552-5556` → `save_jobs` + rollback `:5558-5562`); `save_jobs` (`:9559-9573`); `_restore_jobs_snapshot` (`:9575-9580`, มาจาก R5-H-3); test เดิม `tests/test_bugfix_h3.py` `LoadPresetTests` (`:498-`)
> เลขบรรทัดอ้างอิงไฟล์ ณ วันที่เขียน spec (2026-11-20 — หลังแก้ Round 8 ที่ยังไม่ commit) อาจคลาดเคลื่อนเล็กน้อย

### R9-1. เป้าหมาย

`load_selected` ใน `load_preset_dialog` แก้ `self.saved_jobs` **ก่อน** ตรวจว่า element ใน `"jobs"` ของ preset ใช้ได้:

1. `self.saved_jobs = [job ... if job.get("profile") != current_profile]` (`:5547`) — Job ของ Profile ปัจจุบันถูกตัดออก (เป็น list ใหม่)
2. loop `job["profile"] = current_profile` (`:5554`) — ถ้า element ไม่ใช่ dict (`null`, ตัวเลข, string, list) raise `TypeError` ทันที
3. exception หลุดออกจาก callback โดยไม่มี rollback — `_restore_jobs_snapshot` ถูกเรียกเฉพาะเมื่อ `save_jobs()` คืน `False` (`:5558-5562`)

ผล: Job ของ Profile ปัจจุบันหายจาก memory (บางส่วนของ preset ที่อยู่ก่อน element เสียถูก append ไปแล้ว) และ save ใด ๆ ต่อมา (Save Job / Edit / Delete) เขียนสถานะนี้ลงไฟล์ → **หายถาวร**

หลักฐาน probe: preset `"jobs": [{"name": "ok", ...}, null]`, Profile `PROD` มี `P-job0..2`, Profile อื่นมี `U-job` → กด Load + ยืนยัน → `TypeError: 'NoneType' object does not support item assignment`; in-memory เหลือ `['U-job', 'ok']`; หลัง Save Job `new` แล้ว `saved_jobs.json` = `['U-job', 'ok', 'new']`

ผลการตรวจโค้ดเพิ่มเติม (รูปแบบ element อื่นที่ทำให้พัง):

| รูปแบบ element / preset | ผลในโค้ดปัจจุบัน |
|---|---|
| ไม่ใช่ dict: `null`, `1`, `"x"`, `[]`, `true` | `TypeError` ที่ `:5554` → Job หายตามข้างต้น (บัคหลัก) |
| dict ที่ไม่มี `"query"` หรือ `"name"` | Load สำเร็จและบันทึกลงไฟล์ แต่พังภายหลัง: `edit_job` ใช้ `job["name"]` / `job["query"]` (`:4202`, `:4226`) → `KeyError`; `load_job_to_editor` (`:4158`, `:4162`); การแสดงผล Run All / export ใช้ `job["name"]` / `job["query"]` (`:9943`, `:9977`, `:10010`, `:10094`, `:10117`, `:10186`, `:10474`) |
| dict ที่ `"query"` / `"name"` ไม่ใช่ string (เช่น `null`, ตัวเลข, list) หรือเป็น string ว่าง / มีแต่ช่องว่าง | Load สำเร็จแต่ข้อมูลผิดจากที่แอปสร้างเองเสมอ (Save Job / Edit Job ปฏิเสธชื่อและ SQL ว่าง `:4332-4338`, `:9633`) และพังหรือทำงานผิดเมื่อนำไปใช้ (`tk.Text.insert` / `assess_sql` / การรัน) |
| `"jobs": []` หรือไม่มี key `"jobs"` | ไม่พัง: ยืนยันข้อความ "replace N jobs with 0 jobs" แล้วลบ Job ของ Profile ปัจจุบันทั้งหมดและบันทึก — เป็นผลที่ผู้ใช้ยืนยันเองอย่างชัดแจ้ง (ดู R9-Q-4) |
| top-level ไม่ใช่ dict / JSON เสีย / `"jobs"` ไม่ใช่ list | ไม่พัง: ถูกข้ามตอนสร้างรายการ (`:5512-5513` `print` "skipped") — พฤติกรรมเดิม |
| `save_jobs()` คืน `False` (เขียนไฟล์ล้ม / `_jobs_save_blocked`) | rollback ด้วย `_restore_jobs_snapshot` ถูกต้องอยู่แล้ว (R5-H-3, lock โดย `tests/test_bugfix_h3.py` `LoadPresetTests`) |

เป้าหมาย: preset ที่มี element เสีย **ต้องไม่เปลี่ยน `self.saved_jobs`** ทั้งใน memory และบนดิสก์, ผู้ใช้ต้องได้รับแจ้งว่า preset ใช้ไม่ได้, และ exception ที่ไม่คาดคิดใด ๆ ระหว่างการแทนที่ Job ต้องถูก rollback แบบเดียวกับกรณี save ล้ม โดย preset ปกติทำงานเหมือนเดิมทุกประการ

ผู้ได้ประโยชน์: ผู้ใช้ที่แก้ไฟล์ `preset_*.json` ด้วยมือ หรือมีไฟล์ preset เสีย (เช่นจาก OneDrive sync) และผู้ใช้ทุกคนที่มี Job ของ Profile ปัจจุบันซึ่งจะถูกแทนที่ตอน Load Preset

### R9-2. ขอบเขต

#### In scope

- **Validate ก่อนแตะข้อมูล**: ใน `load_selected` ตรวจทุก element ของ `"jobs"` ตามนิยาม "element ที่ใช้ได้" (R9-Q-3) **ก่อน** `messagebox.askyesno` และก่อนแก้ `self.saved_jobs` (R9-Q-1, R9-Q-2):
  - ถ้ามี element ที่ใช้ไม่ได้อย่างน้อย 1 ตัว → ปฏิเสธทั้ง preset: แสดง `messagebox.showerror` 1 ครั้ง (parent = dialog) ระบุชื่อ preset และลำดับ (1-based) ของ element แรกที่เสียพร้อมเหตุผลสั้น ๆ, ไม่ถามยืนยัน, ไม่แก้ `self.saved_jobs`, ไม่เรียก `save_jobs`, ไม่แก้ dict ของ preset, dialog ยังเปิดอยู่ให้เลือก preset อื่นได้
- **Rollback สำหรับ exception ที่ไม่คาดคิด**: ครอบบล็อกตั้งแต่การกรอง `self.saved_jobs` ถึงการเรียก `save_jobs()` ด้วย `try / except Exception` ที่เรียก `_restore_jobs_snapshot(saved_jobs_before, original_jobs, jobs_snapshot)` แล้วแจ้ง `messagebox.showerror` (R9-Q-5) และ return โดยไม่มีผลสำเร็จ (ไม่ `update_jobs_list`, ไม่เขียน `results_text`, ไม่ `showinfo`, ไม่ปิด dialog) — exception ไม่หลุดออกจาก callback
- คงทาง rollback เดิมเมื่อ `save_jobs()` คืน `False` ทุกประการ (R5-H-3)
- คงพฤติกรรมของ preset ปกติทุกประการ (ข้อความยืนยัน, ลำดับ Job, การตั้ง `"profile"`, ข้อความสำเร็จ)

#### Out of scope

- บัค B1 (แก้แล้วใน Round 8 — ห้ามแตะ `load_jobs`) และ B3 ถึง B16 ทั้งหมด
- การเปลี่ยนการสร้างรายการ preset (`:5497-5513`): ยังแสดง preset ที่มี element เสียตามเดิม (R9-Q-2), ยังข้ามไฟล์ JSON เสีย / `"jobs"` ไม่ใช่ list ด้วย `print` เดิม
- การ validate `saved_jobs.json` ใน `load_jobs`, การ validate Job ที่มีอยู่แล้วใน `self.saved_jobs`, หรือการแก้จุดที่ใช้ `job["name"]` / `job["query"]` ที่อื่น
- `save_preset_dialog` (รวมการเขียน `run_index` ลง Job ใน memory) และการ `job.get("profile")` แบบไม่มี default ใน Load / Save Preset (ยกไว้แล้วใน R7 Out of scope)
- การทำ deep-copy ของ dict ใน preset ก่อน append (preset dict ถูก append เข้า `self.saved_jobs` โดยตรงตามเดิม) และการที่ `"profile"` ใน dict ของ preset ถูกแก้ค้างไว้เมื่อ `save_jobs()` ล้ม (ไม่กระทบไฟล์ preset และ `saved_jobs`)
- การเปลี่ยนพฤติกรรม preset ที่ `"jobs"` ว่าง (R9-Q-4), การเพิ่ม key ที่ต้องมีนอกเหนือ `"name"` / `"query"`, การ validate ค่า key อื่น (`database`, `db_type`, `excel_parameters`, ...)
- exception ที่เกิด **หลัง** `save_jobs()` คืน `True` (เช่นใน `update_jobs_list`) — ไฟล์ถูกเขียนแล้ว การ rollback memory จะทำให้ memory ไม่ตรงกับดิสก์
- `save_jobs`, `_restore_jobs_snapshot`, `write_json_atomic` และข้อความ dialog เดิม
- Refactor / rename / commit

### R9-3. User stories

- **R9-US-1**: ในฐานะผู้ใช้ที่เผลอ Load preset ที่ไฟล์เสีย ฉันต้องการให้ Job ของ Profile ปัจจุบันยังอยู่ครบทั้งในแอปและในไฟล์ เพื่อไม่สูญเสียงานถาวร
- **R9-US-2**: ในฐานะผู้ใช้คนเดียวกัน ฉันต้องการเห็นข้อความบอกว่า preset ไหนใช้ไม่ได้และเสียที่ตำแหน่งใด เพื่อไปแก้ไฟล์ได้
- **R9-US-3**: ในฐานะผู้ใช้ preset ปกติ ฉันต้องการให้ Load Preset ทำงานเหมือนเดิม

### R9-4. Acceptance criteria

วิธีทดสอบทุกข้อเป็น `unittest` ตามแนวทาง `tests/test_bugfix_h3.py` `LoadPresetTests` (stub จาก `make_job_stub`, `fake_dialog_widgets`, กดปุ่ม Load ด้วย `command()`), `unittest.mock.patch.object(app, "messagebox")`, `tempfile.TemporaryDirectory()` เป็นโฟลเดอร์ของ `jobs_file` / preset; ไม่เปิด Tk จริง ไม่ต่อฐานข้อมูล ไฟล์ test ใหม่: `tests/test_r9_load_preset_validation.py`

นิยาม:
- "สถานะเริ่มต้น" = `profile_combo.get()` คืน `"PROD"`; `self.saved_jobs` มี `P-job0`, `P-job1`, `P-job2` (`"profile": "PROD"`) และ `U-job` (`"profile": "UAT"`) สลับลำดับกัน รวมค่าซ้อน (dict / list) และอักษรไทย; `saved_jobs.json` บนดิสก์มีเนื้อหาเดียวกัน (เขียนด้วย `save_jobs()` จริง)
- "element เสีย" = ชุด matrix: ไม่ใช่ dict (`None`, `1`, `"x"`, `[]`, `True`); dict ที่ไม่มี `"query"`; ไม่มี `"name"`; `"query"` / `"name"` เป็น `None`, ตัวเลข, list; `"query"` / `"name"` เป็น `""` หรือ `"   "` (ตาม R9-Q-3)
- "preset เสีย" = `{"created": "...", "jobs": [<Job ปกติ>, <element เสีย>, <Job ปกติ>]}` (element เสียไม่อยู่ตำแหน่งแรก เพื่อจับกรณี append ไปบางส่วนแบบ probe) และกรณี element เสียอยู่ตำแหน่งแรก / สุดท้าย
- "`saved_jobs` ไม่เปลี่ยน" = `stub.saved_jobs is` list object เดิม, แต่ละ element `is` dict object เดิมตามลำดับเดิม, และ `==` deep-copy ที่เก็บไว้ก่อนกด Load
- "ดิสก์ไม่เปลี่ยน" = bytes ของ `saved_jobs.json` และ `preset_*.json` เท่ากับก่อนกด Load

#### Preset เสีย — ปฏิเสธก่อนแตะข้อมูล

| AC | Given / When / Then |
|---|---|
| R9-AC-1 | **Given** สถานะเริ่มต้นและ preset เสีย (ทุกแบบใน matrix ด้วย `subTest`, รวมกรณี probe `[{ok}, null]`) **When** เลือก preset แล้วกด Load **Then** ไม่มี exception หลุดออก และ `saved_jobs` ไม่เปลี่ยน (ไม่มี `ok` ถูก append, `P-job0..2` ยังอยู่) |
| R9-AC-2 | **Given** เหมือน R9-AC-1 **When** กด Load **Then** `messagebox.askyesno` ไม่ถูกเรียก, `save_jobs` ไม่ถูกเรียก (spy), `update_jobs_list` ไม่ถูกเรียก, `results_text` ไม่ถูกเขียน, `showinfo` ไม่ถูกเรียก และ dialog ไม่ถูก destroy |
| R9-AC-3 | **Given** เหมือน R9-AC-1 **When** กด Load **Then** `messagebox.showerror` ถูกเรียก 1 ครั้งด้วย `parent=dialog` และข้อความมีชื่อ preset และลำดับ 1-based ของ element **แรก** ที่เสีย (เช่น preset ที่ element ที่ 2 และ 3 เสีย → ระบุ `2`) |
| R9-AC-4 | **Given** เหมือน R9-AC-1 **When** กด Load **Then** ดิสก์ไม่เปลี่ยน (`saved_jobs.json` และไฟล์ preset) และ dict ของ Job ปกติใน preset (ที่อยู่ใน `preset_data`) ไม่ถูกเพิ่ม / แก้ key `"profile"` |
| R9-AC-5 | **Given** กด Load preset เสียแล้วตาม R9-AC-1 (ใช้ `save_jobs` จริง) **When** append Job ใหม่ `new` (`"profile": "PROD"`) แล้วเรียก `save_jobs()` **Then** คืน `True` และ `saved_jobs.json` ที่อ่านกลับมา = Job เดิมทั้ง 4 ตัวตามลำดับเดิม ตามด้วย `new` — ตรงข้ามกับผล probe `['U-job', 'ok', 'new']` |
| R9-AC-6 | **Given** dialog เดียวกันหลังปฏิเสธ preset เสียตาม R9-AC-1 และมี preset ปกติอีกไฟล์ในรายการ **When** เลือก preset ปกติแล้วกด Load + ยืนยัน **Then** โหลดสำเร็จตาม R9-AC-9 (preset เสียไม่ทิ้งสถานะค้างที่กระทบการโหลดครั้งถัดไป) |
| R9-AC-7 | **Given** โฟลเดอร์มี preset เสียและ preset ปกติ **When** เปิด `load_preset_dialog()` **Then** รายการใน listbox เหมือนเดิม: ทั้งสองไฟล์ปรากฏ ด้วยข้อความรูปแบบเดิม `"<name> (<len(jobs)> jobs) - <created[:10]>"` (R9-Q-2); ไฟล์ JSON เสีย / `"jobs"` ไม่ใช่ list ยังถูกข้ามพร้อม `print` เดิม |

#### Rollback เมื่อเกิด exception ที่ไม่คาดคิด

| AC | Given / When / Then |
|---|---|
| R9-AC-8 | **Given** สถานะเริ่มต้น, preset ปกติ และ `save_jobs` ถูก patch ให้แก้ `self.saved_jobs` (append / แก้ค่าซ้อนของ Job เดิม) แล้ว raise `RuntimeError("boom")` **When** กด Load + ยืนยัน **Then** ไม่มี exception หลุดออก, `saved_jobs` ไม่เปลี่ยน (identity + ค่า ตามนิยาม), ไม่มี `update_jobs_list` / `results_text` / `showinfo`, dialog ไม่ถูก destroy, `messagebox.showerror` ถูกเรียก 1 ครั้งและข้อความมี `boom` (R9-Q-5), และ `saved_jobs.json` บนดิสก์ไม่เปลี่ยน |

#### Preset ปกติ (regression lock)

| AC | Given / When / Then |
|---|---|
| R9-AC-9 | **Given** สถานะเริ่มต้นและ preset ปกติ 2 Job (ตัวหนึ่งไม่มี key `"profile"`, อีกตัวมี `"profile": "UAT"`, มี key อื่นเช่น `database`, `run_index`, `excel_parameters`) **When** กด Load + ยืนยัน (`save_jobs` จริง) **Then** `askyesno` ถูกเรียก 1 ครั้งด้วยข้อความเดิม (`... replace current 3 jobs with 2 jobs from preset.`), `saved_jobs` = `[U-job, <preset job 1>, <preset job 2>]` (Job Profile อื่นคงอยู่ลำดับเดิม ตามด้วย Job ของ preset ตามลำดับในไฟล์) โดย Job ของ preset ทุกตัวมี `"profile": "PROD"` และ key อื่นคงค่าเดิม, `saved_jobs.json` บนดิสก์เท่ากับ `saved_jobs`, `update_jobs_list` 1 ครั้ง, `results_text` มี `Loaded preset: <name>` และ `Jobs loaded: 2`, `showinfo` 1 ครั้ง, dialog ถูก destroy, ไม่มี `showerror`, ไฟล์ preset ไม่เปลี่ยน |
| R9-AC-10 | **Given** preset ปกติ **When** กด Load แล้วตอบ No ใน `askyesno` **Then** `saved_jobs` ไม่เปลี่ยน, `save_jobs` ไม่ถูกเรียก, ไม่มี dialog error / success — พฤติกรรมเดิม |
| R9-AC-11 | **Given** preset ที่ `"jobs": []` และ preset ที่ไม่มี key `"jobs"` **When** กด Load + ยืนยัน **Then** พฤติกรรมเดิม (R9-Q-4): ข้อความยืนยันระบุ `with 0 jobs`, Job ของ `PROD` ถูกลบ, `saved_jobs` = `[U-job]` และบันทึกลงไฟล์, `showinfo` สำเร็จ, ไม่มี `showerror` |
| R9-AC-12 | **Given** ไม่ได้เลือก preset ใน listbox **When** กด Load **Then** `showwarning("Warning", "Please select a preset", parent=dialog)` เหมือนเดิม และไม่มีการตรวจ / แก้ข้อมูล |

#### Rollback เดิมเมื่อ save ล้ม (regression lock R5-H-3)

| AC | Given / When / Then |
|---|---|
| R9-AC-13 | **Given** สถานะเริ่มต้น, preset ปกติ และ `save_jobs` คืน `False` หลังแก้ `self.saved_jobs` in-place **When** กด Load + ยืนยัน **Then** พฤติกรรมเดิม: `saved_jobs` ไม่เปลี่ยน (identity + ค่า), ไม่มี `update_jobs_list` / `results_text` / `showinfo`, dialog ไม่ถูก destroy, ไฟล์ preset ไม่เปลี่ยน และ **ไม่มี** `showerror` เพิ่มจากโค้ดของ Round 9 (error dialog มาจาก `save_jobs` เท่านั้น) |
| R9-AC-14 | **Given** สถานะเริ่มต้น, preset ปกติ และ `save_jobs` จริงที่ล้มสองแบบ: (ก) patch `write_json_atomic` ให้ raise `OSError` (ข) `_jobs_save_blocked = True` **When** กด Load + ยืนยัน **Then** `saved_jobs` ไม่เปลี่ยน, `saved_jobs.json` บนดิสก์ไม่เปลี่ยน, `showerror` ถูกเรียก 1 ครั้งด้วยข้อความเดิมของ `save_jobs` (`Failed to save jobs:` / `could not be read when the app started`) และไม่มี `showinfo` |
| R9-AC-15 | **Given** test เดิม `tests/test_bugfix_h3.py` (`LoadPresetTests`), `tests/test_bugfix_m5.py`, `tests/test_r3_script_groups_io.py` และ `tests/test_r8_load_jobs_writeback.py` **When** รันหลังแก้ **Then** ผ่านโดยไม่แก้ test เดิม |

#### Regression ทั้งชุด (ผู้ใช้เลื่อนได้)

| AC | Given / When / Then |
|---|---|
| R9-AC-16 | **Given** แก้ B2 ครบ **When** รัน `python -m unittest discover -s tests -p "test_*.py"` สองแบบตาม R7-AC-28 / R8-AC-15: (ก) ตั้ง `PYTHONIOENCODING=utf-8` และ (ข) ไม่ตั้ง `PYTHONIOENCODING` / `PYTHONUTF8` บนเครื่อง code page `cp874` และ redirect stdout+stderr ไปไฟล์หรือ pipe **Then** ทั้งสองแบบได้ `OK`, จำนวน test เท่ากันทั้งสองแบบ และไม่มี test เดิมถูกแก้ — **AC นี้แยกไว้ให้ผู้ใช้เลื่อนได้** (Round 8 ผู้ใช้สั่งรันเฉพาะ focused: ถ้าเลื่อน ให้รัน focused `tests.test_r9_load_preset_validation tests.test_bugfix_h3 tests.test_bugfix_m5 tests.test_r8_load_jobs_writeback` แทน และบันทึกว่า R9-AC-16 รอ) |

**สรุปจำนวน AC Round 9**: 16 ข้อ — unittest ทั้งหมด (preset เสีย: 7, rollback exception: 1, preset ปกติ: 4, rollback เดิม R5: 3, full suite (เลื่อนได้): 1)

### R9-5. ข้อจำกัด / สมมติฐาน

- Minimal diff: แก้เฉพาะ `load_selected` ภายใน `load_preset_dialog` ใน `database_connect_gui.py`; ไม่ refactor ไม่ rename; ไม่แตะ `load_jobs` (Round 8 ยังไม่ commit); PEP 8 + type hints สำหรับ helper ใหม่ (ถ้ามี)
- การตรวจทำกับ `data` ที่ cache ไว้ใน `preset_data` ตอนเปิด dialog (ไม่อ่านไฟล์ใหม่) — สอดคล้องกับพฤติกรรมเดิม
- นิยาม "element ที่ใช้ได้" (ค่าเริ่มต้นตาม R9-Q-3): `isinstance(job, dict)` และ `"name"` กับ `"query"` เป็น `str` ที่ `.strip()` แล้วไม่ว่าง — ตรงกับสิ่งที่ Save Job / Edit Job รับประกันเสมอ (`:9633`, `:4332-4338`) ดังนั้น preset ที่แอปสร้างเองผ่านทุกตัว; key `"profile"` ใน preset จะถูกเขียนทับอยู่แล้วจึงไม่ตรวจ
- การ validate ทำก่อน `askyesno` เพื่อไม่ให้ผู้ใช้ยืนยันการแทนที่ที่จะไม่เกิดขึ้น; ข้อความ `showerror` มีชื่อ preset + ลำดับ element แรกที่เสีย + เหตุผล รูปแบบที่เหลือกำหนดในขั้น design (ใช้ title เช่น `"Invalid Preset"`)
- `try / except Exception` ครอบเฉพาะช่วงกรอง → loop → `save_jobs()`; ทาง `save_jobs()` คืน `False` ยังใช้ `_restore_jobs_snapshot` + `return` เดิม (ไม่มี dialog เพิ่ม — R9-AC-13); exception หลัง save สำเร็จไม่อยู่ใน `try` (Out of scope)
- snapshot (`saved_jobs_before`, `original_jobs`, `jobs_snapshot`) ต้องถูกสร้างก่อนเข้า `try` และก่อนแก้ข้อมูลใด ๆ (ตามโค้ดเดิม `:5542-5544`)
- ห้าม commit

### R9-6. คำถามที่ยังไม่มีคำตอบ

ทุกข้อมีคำตอบที่แนะนำซึ่ง AC ข้างต้นใช้เป็นค่าเริ่มต้นแล้ว ถ้าผู้ใช้ต้องการแบบอื่นให้แจ้งก่อนเริ่ม design

| # | คำถาม | คำตอบที่แนะนำ (default) |
|---|---|---|
| R9-Q-1 | preset ที่มี **บาง** element เสีย: (ก) ปฏิเสธทั้งไฟล์ หรือ (ข) ข้ามตัวเสียแล้วโหลดที่เหลือ | (ก) ปฏิเสธทั้งไฟล์ — การ Load **แทนที่** Job ทั้งหมดของ Profile ถ้าข้ามบางตัว ผู้ใช้จะเสีย Job เดิมแลกกับ preset ที่ไม่ครบโดยอาจไม่รู้ตัว; ผู้ใช้แก้ไฟล์แล้วโหลดใหม่ได้ (R9-AC-1 ถึง R9-AC-4) |
| R9-Q-2 | ควรซ่อน preset ที่มี element เสียจากรายการ (ตรวจตอนสร้างรายการเหมือน `"jobs"` ไม่ใช่ list) หรือแสดงแล้วปฏิเสธตอนกด Load | แสดงตามเดิมแล้วปฏิเสธตอนกด Load พร้อม `showerror` — การซ่อนแจ้งได้แค่ `print` ลง console ผู้ใช้จะไม่รู้ว่า preset หายไปเพราะอะไร (ไม่ตรงข้อกำหนด "แจ้งผู้ใช้") และไม่ต้องแก้ส่วนสร้างรายการ (R9-AC-7) |
| R9-Q-3 | "element ที่ใช้ได้" ต้องเข้มแค่ไหน: (ก) แค่เป็น dict, (ข) dict + มี `"query"`, (ค) dict + `"name"` และ `"query"` เป็น string ไม่ว่าง | (ค) — ตรงกับที่แอปบังคับตอน Save / Edit Job และกันพังภายหลังที่ `edit_job` / Run All / export ซึ่งใช้ `job["name"]` / `job["query"]` โดยตรง; preset ที่แอปสร้างเองผ่านเสมอ ถ้าผู้ใช้ต้องการผ่อนเป็น (ข) ให้ตัดกรณี `"name"` ออกจาก matrix ของ R9-AC-1 |
| R9-Q-4 | preset ที่ `"jobs": []` หรือไม่มี key `"jobs"` ควรถือว่าเสียหรือไม่ (ปัจจุบันลบ Job ของ Profile ทั้งหมดหลังผู้ใช้ยืนยัน "with 0 jobs") | ไม่ถือว่าเสีย คงพฤติกรรมเดิม (R9-AC-11) — ไม่ใช่ crash ไม่มีข้อมูลหายโดยไม่ตั้งใจเพราะข้อความยืนยันบอกจำนวน 0 ชัดเจน; การเปลี่ยนเป็น scope creep |
| R9-Q-5 | exception ที่ไม่คาดคิดในช่วงแทนที่ Job (หลังผ่าน validate): rollback แล้ว (ก) แสดง `showerror` ที่มีข้อความ exception, (ข) rollback แล้ว re-raise ให้ Tk พิมพ์ traceback, (ค) rollback เงียบ | (ก) — ผู้ใช้รู้ว่า Load ไม่สำเร็จและข้อมูลเดิมยังอยู่ ไม่มี traceback หลุด (R9-AC-8); ทาง `save_jobs()` คืน `False` คงเดิมไม่มี dialog ซ้ำ (R9-AC-13) |
| R9-Q-6 | R9-AC-16 (full suite สองแบบ encoding) จะรันใน Round นี้หรือเลื่อนแบบ Round 8 | ให้ผู้ใช้ตัดสิน — ถ้าเลื่อน ให้รัน focused ตามที่ระบุใน R9-AC-16 แทน |

---

# Round 10 — Bugfix B3: Export Excel ทำไฟล์ `.xlsx` เดิมหายเมื่อ export ไม่จบ

> ใช้เลข `R10-AC-x` และ `R10-Q-x` แยกจาก Round ก่อนหน้า ไม่แก้เนื้อหา Round ก่อนหน้า
> ที่มา: รายงาน bug-hunter ข้อ B3 (ยืนยันด้วย probe แล้ว) ผู้ใช้สั่งให้แก้ **เฉพาะ B3** — บัค B4 ถึง B16 อยู่นอกขอบเขตทั้งหมด (รวม B12 กด Stop แล้วขึ้น "Export Excel เรียบร้อย"); การแก้ของ Round 8 (`load_jobs`) และ Round 9 (`load_preset_dialog`) ยังไม่ commit และห้ามแตะ
> ไฟล์ที่เกี่ยวข้อง: `database_connect_gui.py` — `export_jobs_to_excel` (`:10318-10808`): เลือกไฟล์ `asksaveasfilename` (`:10353-10360`), log เริ่มต้น `📁 File:` (`:10376`), `on_done` (`:10392-10416`: ทาง fatal `:10395-10401`, ทางสำเร็จ `📁 Saved to:` `:10408` + `showinfo` `:10411-10416`), `worker` (`:10430-10806`): **`pd.ExcelWriter(file_path, engine="openpyxl")` `:10502`** (จุดบัค), `job["query"]` นอก `try` ราย Job `:10508`, Stop `:10504-10506`, `try` ราย Job `:10527` / `except Exception as job_err` `:10772-10792`, sheet `Export` เมื่อไม่มี sheet `:10794-10798`, `except Exception as e` → `fatal_error` `:10800-10801`; callers: Export Group `:5246`, Export ผลของ Job เดียว `export_to_excel_result` `:9113-9121`; `on_closing` + "Confirm Exit" (`:14141-14152`); test เดิมที่เกี่ยวข้อง `tests/test_r7_excel_cell_limit.py`, `tests/test_bugfix_c2.py`, `tests/test_bugfix_m2.py`, `tests/test_r4_excel_row_limit.py` (mock `pd.ExcelWriter` `:224-226`), `tests/test_r2_table_data_refresh.py` (`:342-350`)
> เลขบรรทัดอ้างอิงไฟล์ ณ วันที่เขียน spec (2026-11-20 — หลังแก้ Round 8-9 ที่ยังไม่ commit; รายงาน bug-hunter อ้าง `:10456` / `:10462` ซึ่งเลื่อนมาเป็น `:10502` / `:10508`) อาจคลาดเคลื่อนเล็กน้อย

### R10-1. เป้าหมาย

`pd.ExcelWriter(file_path)` เปิดไฟล์ปลายทางแบบ `"wb"` **ทันที** ตอนเข้า `with` (`:10502`) ก่อนรัน query ของ Job แรก ซึ่งอาจใช้เวลาหลายชั่วโมง ไฟล์ปลายทางจึงเป็น 0 byte ตลอดการ export และเนื้อหาจริงถูกเขียนตอน `__exit__` เท่านั้น ถ้าผู้ใช้เลือกเขียนทับรายงาน `.xlsx` เดิม:

1. ปิดแอประหว่าง export (ตอบ Yes ใน "Confirm Exit" → `root.destroy()` → thread `daemon=True` ถูกตัดทิ้ง), process ถูก kill หรือเครื่องดับ → **ไฟล์เดิมหาย เหลือ 0 byte**
2. exception ที่หลุดออกนอก `try` ราย Job (เช่น `job["query"]` `:10508` ของ Job ที่ไม่มี key `"query"`, ชื่อ Job ไม่ใช่ dict, exception ภายใน `except job_err` เอง หรือการ save workbook ล้ม) → ถ้ามี sheet แล้ว `__exit__` เขียน workbook **บางส่วน** ทับไฟล์เดิม; ถ้ายังไม่มี sheet `__exit__` raise `IndexError: At least one sheet must be visible` ซึ่ง **บังสาเหตุจริง** — `fatal_error` และ dialog แสดง `IndexError` แทน `KeyError: 'query'` และไฟล์เดิมเหลือ 0 byte

หลักฐาน probe: ไฟล์เดิม 11,980 bytes → ภายใน `with pd.ExcelWriter(...)` ขนาด 0 bytes; exception ก่อนมี sheet → `__exit__` raise `IndexError: At least one sheet must be visible`

ผลการตรวจโค้ด — ทุกทางออกของ worker ในโค้ดปัจจุบัน:

| ทางออก | ผลต่อไฟล์ปลายทางปัจจุบัน | ข้อความ / log ปัจจุบัน |
|---|---|---|
| สำเร็จครบทุก Job (รวม Job ที่ Failed / Skipped / No Data ราย Job ซึ่งถูกจับใน `try` ราย Job) | workbook ใหม่ทับไฟล์เดิม ✅ | `🏁 Export Excel Completed`, `📁 Saved to: <file_path>`, `showinfo` "Export Success" |
| กด Stop ระหว่างทาง | workbook ของ Job ที่เสร็จแล้วทับไฟล์เดิม; Stop ก่อน Job แรก → sheet `Export` (`Status = Stopped`) ทับไฟล์เดิม | `⏹ Stopped — N job(s) not exported` + ข้อความสำเร็จ (B12 — นอกขอบเขต) |
| exception นอก `try` ราย Job หลังมี sheet แล้ว | workbook บางส่วนทับไฟล์เดิม | `❌ EXPORT EXCEL FAILED` + `showerror` ด้วยสาเหตุจริง |
| exception นอก `try` ราย Job ก่อนมี sheet | ไฟล์เดิมเหลือ 0 byte | `IndexError: At least one sheet must be visible` (บังสาเหตุจริง) |
| การ save workbook ตอน `__exit__` ล้ม (ดิสก์เต็ม, OneDrive ล็อก ฯลฯ) | ไฟล์เดิมเหลือ 0 byte หรือเขียนไม่ครบ | `❌ EXPORT EXCEL FAILED` |
| ไฟล์ปลายทางถูก Excel เปิดค้างตอนเริ่ม | `PermissionError` ทันทีที่ `pd.ExcelWriter(...)` ก่อนรัน query ใด ๆ ไฟล์เดิมไม่เปลี่ยน | `❌ EXPORT EXCEL FAILED` (fail เร็ว — พฤติกรรมที่ดีและต้องคงไว้) |
| ปิดแอป / kill process ระหว่าง export | ไฟล์เดิมเหลือ 0 byte | — |
| ไม่มี Job / ยกเลิก dialog เลือกไฟล์ / ยกเลิก dialog reuse / busy / Profile ไม่ตรง / ไม่ได้ Connect / ไม่มี `openpyxl` | ไม่แตะไฟล์ (return ก่อนเริ่ม worker) | ข้อความเดิม |

เป้าหมาย: ไฟล์ปลายทางเดิม **ไม่ถูกเปิด / ตัด / แก้** จนกว่า workbook ใหม่จะถูกเขียนครบสมบูรณ์ แล้วจึงแทนที่ในขั้นเดียว (`os.replace`) ถ้า export ไม่สำเร็จ ไฟล์เดิมต้องคงอยู่ครบ ไม่มีไฟล์ชั่วคราวค้าง (ยกเว้นกรณีที่ระบุใน R10-Q-3 / R10-Q-6) และผู้ใช้ต้องเห็นสาเหตุจริงของความล้มเหลว โดยผลลัพธ์ของ export ที่สำเร็จเหมือนเดิมทุกประการ

ผู้ได้ประโยชน์: ผู้ใช้ที่ export รายงานทับไฟล์เดิม (Export Excel / Export Group / Export ผลของ Job เดียว ซึ่งใช้ `export_jobs_to_excel` ตัวเดียวกัน) โดยเฉพาะงานที่ใช้เวลานาน

### R10-2. ขอบเขต

#### In scope

- **เขียนลงไฟล์ชั่วคราวแล้วแทนที่**: worker ของ `export_jobs_to_excel` เขียน workbook ลงไฟล์ชั่วคราวในโฟลเดอร์เดียวกับไฟล์ปลายทาง (ชื่อตาม R10-Q-1) และเรียก `os.replace(<temp>, file_path)` เฉพาะเมื่อ workbook ถูก save ครบสมบูรณ์โดยไม่มี fatal error; ไฟล์ปลายทางไม่ถูกเปิดเพื่อเขียนก่อนจังหวะนั้น
- **ล้มแล้วลบ temp**: ทุกทางที่ไม่ไปถึง `os.replace` (fatal exception, save workbook ล้ม) ลบไฟล์ชั่วคราวแบบ best-effort; ลบไม่ได้ให้ข้าม (ไม่ raise) และบันทึกตาม R10-Q-9
- **ไม่บังสาเหตุจริง**: `fatal_error` / `showerror` / Execution Logs ต้องแสดง exception ต้นเหตุ (ชนิด + ข้อความ) ไม่ใช่ `IndexError: At least one sheet must be visible` หรือ error จากการ close / ลบ temp ที่เกิดตามมา
- **ไฟล์ปลายทางถูกล็อก**: ตรวจตั้งแต่ก่อนรัน query (คงพฤติกรรม fail เร็วแบบเดิม) และจัดการกรณี `os.replace` ล้มตาม R10-Q-3
- **Stop**: พฤติกรรมของไฟล์ตาม R10-Q-2 (ค่าเริ่มต้น = เหมือนเดิม คือ workbook บางส่วนแทนที่ไฟล์ปลายทาง แต่ผ่าน temp + `os.replace`)
- **path ที่แสดง**: log `📁 File:` / `📁 Saved to:` และ `showinfo` แสดง `file_path` ปลายทางเหมือนเดิม; path ของ temp แสดงเฉพาะกรณีที่ระบุใน R10-Q-3 / R10-Q-9
- ครอบทั้ง 3 ทางเข้า (Export Excel, Export Group `:5246`, `export_to_excel_result` `:9121`) โดยอัตโนมัติเพราะใช้ worker เดียวกัน

#### Out of scope

- บัค B4 ถึง B16 ทั้งหมด — รวม **B12** (Stop แล้ว `on_done` ขึ้น `Export Excel เรียบร้อย` / `Export Success`): Round นี้ไม่แก้ข้อความ / ตัวนับ / dialog ของ Stop; AC ของ Round นี้จึง **ไม่ assert** ข้อความสำเร็จ / ไม่สำเร็จในกรณี Stop
- Round 8 (`load_jobs`) และ Round 9 (`load_preset_dialog`) ที่ยังไม่ commit — ห้ามแตะ
- การย้าย `job["query"]` (`:10508`) เข้า `try` ราย Job ให้กลายเป็น Job Failed แทน fatal (R10-Q-7) — Round นี้แค่ทำให้ error จริงไม่ถูกบัง
- การเปลี่ยนเนื้อหา workbook (sheet, cell, รูปแบบ, การตรวจ 32,767 ของ R7, row limit ของ R4, `force_literal_strings` / `data_type = "s"`), ตัวนับ Success / Warning / Failed / Skipped และข้อความ log อื่นของ worker
- การ retry `os.replace`, การล้าง temp ที่ค้างจาก Round ก่อน / จากการ kill process ตอนเปิดแอปครั้งถัดไป (R10-Q-6), การเปลี่ยนข้อความ "Confirm Exit" หรือการรอ worker ก่อนปิดแอป
- การเก็บ attribute / ACL / creation time ของไฟล์เดิม (ไฟล์ใหม่แทนที่ทั้งไฟล์)
- จุดอื่นที่เขียนไฟล์ลงปลายทางโดยตรง (R10-Q-8): `export_selected` ในหน้าต่างเลือกค่า (`:14084` `to_excel(save_path)`), `export_to_csv` (`:9098-9106`), Export Profiles / Groups JSON (`:3419`, `:4500`) — ทั้งหมดเขียนข้อมูลที่อยู่ใน memory แล้วจบทันที ไม่มี query ยาวคั่น
- `write_json_atomic` และ helper กลางอื่น, refactor / rename / commit

### R10-3. User stories

- **R10-US-1**: ในฐานะผู้ใช้ที่ export ทับรายงาน `.xlsx` เดิม ฉันต้องการให้ไฟล์เดิมยังอยู่ครบถ้าฉันปิดแอป, process ตาย หรือ export ล้มกลางทาง เพื่อไม่เสียรายงานเดิม
- **R10-US-2**: ในฐานะผู้ใช้คนเดียวกัน ฉันต้องการเห็นสาเหตุจริงที่ export ล้ม เพื่อแก้ไขได้ถูกจุด
- **R10-US-3**: ในฐานะผู้ใช้ที่ export สำเร็จ ฉันต้องการได้ไฟล์ผลลัพธ์เหมือนเดิมทุกประการ ที่ path ที่ฉันเลือก โดยไม่มีไฟล์แปลกปลอมค้างในโฟลเดอร์
- **R10-US-4**: ในฐานะผู้ใช้ที่เปิดไฟล์ปลายทางใน Excel ค้างไว้ ฉันต้องการรู้ตั้งแต่ต้นว่าเขียนไม่ได้ และถ้าไฟล์ถูกล็อกตอนท้าย ฉันต้องการไม่เสียผล export ที่รันมาหลายชั่วโมง

### R10-4. Acceptance criteria

วิธีทดสอบทุกข้อเป็น `unittest` ตามแนวทาง `tests/test_r7_excel_cell_limit.py` `_ExportCase` (stub จาก `DatabaseConnectorGUI.__new__`, `root.after` เรียก callback ทันที, patch `filedialog.asksaveasfilename`, `threading.Thread` → `_ImmediateThread`, `messagebox`, `read_sql_dataframe` เป็น callback ของ test) ใช้ `pandas` / `openpyxl` จริงเขียนไฟล์จริงใน `tempfile.TemporaryDirectory()`; ไม่ต่อฐานข้อมูล ไม่เปิด Tk จริง ไฟล์ test ใหม่: `tests/test_r10_export_atomic_write.py`

นิยาม:
- "ไฟล์เดิม" = `.xlsx` ที่ถูกต้องซึ่งสร้างด้วย `openpyxl` ก่อน export ที่ `file_path` (มี sheet / ค่าที่จำได้) — เก็บ bytes และ `os.stat().st_size` ไว้ก่อนเริ่ม
- "ไฟล์เดิมไม่เปลี่ยน" = bytes ของ `file_path` เท่ากับก่อนเริ่ม (และ `openpyxl.load_workbook` เปิดได้ค่าเดิม)
- "ไม่มี temp ค้าง" = ชุดชื่อไฟล์ในโฟลเดอร์ปลายทางหลัง export เท่ากับชุดก่อน export (บวก `file_path` ถ้าเดิมไม่มีและ export สำเร็จ)
- "Job ชุดมาตรฐาน" = 4 Job ที่ครอบทุก sheet type: Success (มีข้อมูล), No Data, Skipped (ไม่ใช่ SELECT), Failed ราย Job (`read_sql_dataframe` raise `RuntimeError`)
- "fatal ก่อนมี sheet" = Job แรกไม่มี key `"query"`; "fatal หลังมี sheet" = Job แรกปกติ, Job ที่สองไม่มี key `"query"` (`KeyError` ที่ `:10508` นอก `try` ราย Job — ทางเดียวกับ probe)
- "temp path" = path ของไฟล์ชั่วคราวที่ worker สร้าง (test หาได้จาก spy บน `os.replace` หรือจากไฟล์ใหม่ในโฟลเดอร์)

#### ไฟล์เดิมไม่เปลี่ยนจนกว่า export สำเร็จ

| AC | Given / When / Then |
|---|---|
| R10-AC-1 | **Given** ไฟล์เดิมที่ `file_path` และ Job ชุดมาตรฐาน **When** `read_sql_dataframe` ถูกเรียกแต่ละครั้ง (callback ของ test อ่าน `file_path` ณ ขณะนั้น) **Then** ทุกครั้ง bytes ของ `file_path` เท่ากับไฟล์เดิม (ไม่ใช่ 0 byte) — ตรงข้ามกับผล probe |
| R10-AC-2 | **Given** เหมือน R10-AC-1 **When** export สำเร็จ **Then** workbook ถูกเขียนลงไฟล์อื่นก่อนแล้ว `os.replace` (spy ที่เรียกของจริง) ถูกเรียก **1 ครั้ง** ด้วย `dst == file_path` และ `os.path.dirname(src) == os.path.dirname(file_path)` (โฟลเดอร์เดียวกัน — R10-Q-1); ไม่มีการเปิด `file_path` ด้วย mode เขียนก่อน `os.replace` |
| R10-AC-3 | **Given** ในโฟลเดอร์ปลายทางมีไฟล์อื่นของผู้ใช้อยู่ก่อน รวมไฟล์ชื่อ `<stem>.tmp.xlsx` และ `<stem>.xlsx.tmp` **When** export สำเร็จ และ export ที่ fatal (ทั้งสองแบบ) **Then** ไฟล์อื่นทุกไฟล์มี bytes เท่าเดิมและไม่ถูกลบ (temp ต้องไม่ชนกับไฟล์ที่มีอยู่ — R10-Q-1) |
| R10-AC-4 | **Given** ไฟล์เดิมที่ `file_path` และ Job 2 ตัว **When** subprocess ที่รัน export บน stub เดียวกัน ถูก `Popen.kill()` ระหว่าง `read_sql_dataframe` ของ Job ที่สอง (child ส่งสัญญาณ "อยู่ใน query" ทาง stdout แล้วรอ) **Then** หลัง process ตาย `file_path` เป็นไฟล์เดิม (bytes เท่าเดิม) — จำลองการปิดแอป / kill process; ไฟล์ temp อาจค้างได้ตาม R10-Q-6 (test ไม่ assert เรื่อง temp ในข้อนี้) |

#### Export สำเร็จ — ผลเหมือนเดิม

| AC | Given / When / Then |
|---|---|
| R10-AC-5 | **Given** ไฟล์เดิมที่ `file_path` และ Job ชุดมาตรฐาน **When** export **Then** `file_path` เป็น workbook ใหม่ที่ชื่อ sheet, ลำดับ sheet, ค่าทุก cell, `data_type` ของ cell string และ annotation SQL **เท่ากับ** workbook ที่ export ชุดเดียวกันไปยัง path ใหม่ที่ไม่เคยมีไฟล์ (เทียบด้วย `openpyxl`), ไม่มี sheet / ค่าจากไฟล์เดิมหลงเหลือ, ไม่มี temp ค้าง, ตัวนับใน log `Success: 2`, `Warning: 0`, `Failed: 1`, `Skipped (not SELECT): 1` (No Data นับ Success ตามเดิม) |
| R10-AC-6 | **Given** `file_path` ยังไม่มีไฟล์ **When** export Job ชุดมาตรฐาน **Then** `file_path` ถูกสร้าง, เปิดด้วย `openpyxl` ได้ 4 sheet ตามเดิม และในโฟลเดอร์มีไฟล์ใหม่เพียง `file_path` (ไม่มี temp ค้าง) |
| R10-AC-7 | **Given** export สำเร็จตาม R10-AC-5 **When** ตรวจข้อความ **Then** Execution Logs มี `📁 File: <file_path>` และ `📁 Saved to: <file_path>`, `showinfo` ถูกเรียก 1 ครั้ง (title `"Export Success"`) และข้อความมี `file_path`; temp path **ไม่** ปรากฏใน Execution Logs หรือ dialog ใด; ไม่มี `showerror` |
| R10-AC-8 | **Given** Job ที่ Failed ราย Job (exception ใน `try` ราย Job เช่น `read_sql_dataframe` raise, เกิน row limit ของ R4) อยู่ปนกับ Job ปกติ **When** export **Then** ไม่ถือเป็น fatal: `file_path` ถูกแทนที่ด้วย workbook ที่มี sheet `Failed` ของ Job นั้นครบตามเดิม และไม่มี temp ค้าง — พฤติกรรมเดิม |

#### Export ล้ม (fatal) — ไฟล์เดิมคงอยู่ ไม่มี temp ค้าง error จริงไม่ถูกบัง

| AC | Given / When / Then |
|---|---|
| R10-AC-9 | **Given** ไฟล์เดิมและ "fatal หลังมี sheet" **When** export **Then** ไฟล์เดิมไม่เปลี่ยน (ไม่ถูกแทนที่ด้วย workbook บางส่วน — เปลี่ยนจากพฤติกรรมเดิมตาม R10-Q-4), ไม่มี temp ค้าง, `os.replace` ไม่ถูกเรียก, `showerror` ถูกเรียก 1 ครั้ง title `"Export Error"` ข้อความมี `KeyError` และ `query`, Execution Logs มี `❌ EXPORT EXCEL FAILED` และ `Error: KeyError: ...`, ไม่มี `showinfo` |
| R10-AC-10 | **Given** ไฟล์เดิมและ "fatal ก่อนมี sheet" **When** export **Then** เหมือน R10-AC-9 และข้อความใน `showerror` / Execution Logs **ไม่มี** `IndexError` และ `At least one sheet must be visible` (สาเหตุจริง `KeyError: 'query'` ไม่ถูกบัง) |
| R10-AC-11 | **Given** ไฟล์เดิม, Job ปกติ และการ save workbook ล้ม (patch `openpyxl.workbook.workbook.Workbook.save` หรือ close ของ writer ให้ raise `OSError("disk full")` หลังเขียน temp ไปบางส่วน) **When** export **Then** ไฟล์เดิมไม่เปลี่ยน, ไม่มี temp ค้าง, `os.replace` ไม่ถูกเรียก, `showerror` 1 ครั้งข้อความมี `disk full` |
| R10-AC-12 | **Given** เหมือน R10-AC-9 / R10-AC-11 และการลบ temp เองล้ม (patch `os.remove` / `os.unlink` ให้ raise `PermissionError`) **When** export **Then** ไม่มี exception หลุดออกจาก worker, `on_done` ถูกเรียก 1 ครั้ง, ข้อความใน `showerror` เป็นสาเหตุต้นเหตุ (`KeyError` / `disk full`) **ไม่ใช่** `PermissionError` ของการลบ, ไฟล์เดิมไม่เปลี่ยน และ Execution Logs มีบรรทัดระบุ temp path ที่ลบไม่ได้ (R10-Q-9) |
| R10-AC-13 | **Given** ไฟล์เดิมและ `read_sql_dataframe` raise `BaseException` ที่ไม่ใช่ `Exception` (เช่น `SystemExit`) ระหว่าง Job **When** worker ทำงาน (test จับ exception ที่หลุดออก) **Then** ไฟล์เดิมไม่เปลี่ยน และไม่มี temp ค้าง (การลบ temp อยู่ในทาง `finally` หรือเทียบเท่า) — exception นั้นยังหลุดออกเหมือนเดิม (ไม่ถูกกลืน) |

#### ไฟล์ปลายทางถูกล็อก

"ล็อกแบบ Excel" = handle ที่เปิดด้วย `CreateFileW` (`ctypes`) โดย `dwShareMode = FILE_SHARE_READ` (ไม่อนุญาตเขียน / ลบ) เหมือนที่ Excel ถือไฟล์ที่เปิดอยู่; test ส่วนนี้ skip เมื่อ `sys.platform != "win32"`

| AC | Given / When / Then |
|---|---|
| R10-AC-14 | **Given** ไฟล์เดิมที่ถูกล็อกแบบ Excel ตั้งแต่ก่อนเริ่ม **When** export **Then** fail ก่อนรัน query (R10-Q-3): `read_sql_dataframe` **ไม่ถูกเรียก**, `showerror` 1 ครั้ง title `"Export Error"` ข้อความมี `file_path` และสาเหตุ (`PermissionError` / ข้อความว่าไฟล์ถูกเปิดอยู่), ไฟล์เดิมไม่เปลี่ยน, ไม่มี temp ค้าง — คงพฤติกรรม fail เร็วของโค้ดเดิม |
| R10-AC-15 | **Given** ไฟล์เดิมไม่ถูกล็อกตอนเริ่ม แต่ถูกล็อกแบบ Excel ใน `read_sql_dataframe` ของ Job สุดท้าย (จำลองผู้ใช้เปิดไฟล์ระหว่าง export) และ test แบบไม่ขึ้นกับ OS ที่ patch `os.replace` ให้ raise `PermissionError` **When** export จบ **Then** (ตาม R10-Q-3) ไฟล์เดิมไม่เปลี่ยน, ไฟล์ temp ที่ save ครบ **ถูกเก็บไว้** และ `openpyxl` เปิดได้ครบทุก sheet ของ export, `showerror` 1 ครั้งข้อความมี `file_path`, temp path และสาเหตุ, Execution Logs มีข้อมูลเดียวกัน, ไม่มี `showinfo` และไม่มีไฟล์ temp อื่นค้าง — **หมายเหตุ (2026-11-23, R13-AC-11): ส่วน "replace ล้มครั้งเดียวแล้วเก็บ temp" ถูกแทนที่โดย R12-5 ที่ผู้ใช้สั่ง — `os.replace` ที่ล้มด้วย `PermissionError` ถูก retry ตาม `EXPORT_REPLACE_RETRY_DELAYS` (0.2 / 0.5 / 1.0 วินาที รวม 1 + 3 ครั้ง) ก่อน แล้วจึงเก็บ temp + แจ้ง path ตาม AC นี้; `OSError` อื่นไม่ retry (ดู `docs/tasks.md` R12-5) ห้าม Round ถัดไปแก้กลับเป็น replace ครั้งเดียว** |

#### Stop (พฤติกรรมไฟล์เท่านั้น — ข้อความเป็นเรื่องของ B12)

| AC | Given / When / Then |
|---|---|
| R10-AC-16 | **Given** ไฟล์เดิม, 3 Job และ `_stop_event` ถูก set ใน `read_sql_dataframe` ของ Job ที่ 1 **When** export จบ **Then** (ค่าเริ่มต้น R10-Q-2) `file_path` ถูกแทนที่ด้วย workbook ที่มีเฉพาะ sheet ของ Job ที่ 1 (เหมือนผลของโค้ดเดิม), Execution Logs มี `⏹ Stopped — 2 job(s) not exported`, ไม่มี temp ค้าง; **ไม่ assert** ข้อความสำเร็จ / `showinfo` (B12) |
| R10-AC-17 | **Given** ไฟล์เดิมและ `_stop_event` ถูก set ก่อน Job แรก **When** export จบ **Then** (ค่าเริ่มต้น R10-Q-2) `file_path` เป็น workbook ที่มี sheet `Export` (`Status = Stopped`) เหมือนผลของโค้ดเดิม, ไม่มี temp ค้าง; ไม่ assert ข้อความ (B12) |

#### ทางที่ไม่เริ่ม export (regression lock)

| AC | Given / When / Then |
|---|---|
| R10-AC-18 | **Given** ไฟล์เดิมที่ `file_path` **When** export แต่ละกรณี: ไม่มี Job (`jobs_override=[]`), `asksaveasfilename` คืน `""`, `_reuse_last_run_results` คืน `None`, `_block_if_busy` คืน `True` (ครั้งแรก และครั้งที่สองหลัง dialog), `_block_if_profile_mismatch` คืน `True`, `engine` เป็น `None` **Then** ไม่มีไฟล์ใดในโฟลเดอร์ถูกสร้าง / แก้ / ลบ (ไฟล์เดิมไม่เปลี่ยน, ไม่มี temp), worker ไม่ถูกเริ่ม และข้อความ / dialog เหมือนเดิม |

#### Regression lock ของ cell limit / warning (Round 7) และ test เดิม

| AC | Given / When / Then |
|---|---|
| R10-AC-19 | **Given** ไฟล์เดิมที่ `file_path` และ Job ที่มีข้อความเกิน 32,767 UTF-16 units ทุกตำแหน่งของ R7 (cell ผลลัพธ์, `Query` ของ Skipped, `Error` / `Query` ของ Failed, บรรทัด SQL ของ No Data, บรรทัด SQL annotation) และข้อความ 32,767 units พอดี **When** export **Then** `file_path` (หลังแทนที่) มี cell ที่เกินว่าง, cell ที่ 32,767 พอดีครบ, บรรทัด log warning ทุกบรรทัด (ชื่อ Job, ตำแหน่ง, `32,767`) และตัวนับ Success / Warning / Failed / Skipped ตรงกับ R7-AC-9 ถึง R7-AC-14 ทุกประการ; cell string ยัง `data_type == "s"` (R5-AC-9) และไม่มี temp ค้าง |
| R10-AC-20 | **Given** test เดิม `tests/test_r7_excel_cell_limit.py`, `tests/test_bugfix_c2.py`, `tests/test_bugfix_m2.py`, `tests/test_r2_table_data_refresh.py`, `tests/test_r4_excel_row_limit.py`, `tests/test_r4_profile_mismatch.py`, `tests/test_run_entry_block.py`, `tests/test_r8_load_jobs_writeback.py`, `tests/test_r9_load_preset_validation.py` **When** รันหลังแก้ **Then** ผ่านโดยไม่แก้ assertion; ข้อยกเว้นเดียวคือ harness ของ `tests/test_r4_excel_row_limit.py` ที่ mock `pd.ExcelWriter` ด้วย writer ปลอม (ไม่สร้างไฟล์จริง) และใช้ path สัมพัทธ์ `"export.xlsx"` — ปรับได้เฉพาะ harness ตาม R10-Q-5 (เช่น ให้ path อยู่ใน `TemporaryDirectory` / stub การแทนที่ไฟล์) และต้องไม่มีไฟล์ใดถูกสร้างใน working directory ของ repo ระหว่างรัน |

#### Regression ทั้งชุด (ผู้ใช้เลื่อนได้)

| AC | Given / When / Then |
|---|---|
| R10-AC-21 | **Given** แก้ B3 ครบ **When** รัน `python -m unittest discover -s tests -p "test_*.py"` สองแบบตาม R7-AC-28: (ก) ตั้ง `PYTHONIOENCODING=utf-8` และ (ข) ไม่ตั้ง `PYTHONIOENCODING` / `PYTHONUTF8` บนเครื่อง code page `cp874` และ redirect stdout+stderr ไปไฟล์หรือ pipe **Then** ทั้งสองแบบได้ `OK`, จำนวน test เท่ากันทั้งสองแบบ และไม่มี test เดิมถูกแก้นอกจากที่ R10-AC-20 อนุญาต — **AC นี้แยกไว้ให้ผู้ใช้เลื่อนได้**: ถ้าเลื่อน ให้รัน focused `tests.test_r10_export_atomic_write tests.test_r7_excel_cell_limit tests.test_bugfix_c2 tests.test_bugfix_m2 tests.test_r4_excel_row_limit tests.test_r2_table_data_refresh tests.test_r4_profile_mismatch tests.test_run_entry_block` แทน และบันทึกว่า R10-AC-21 รอ |

**สรุปจำนวน AC Round 10**: 21 ข้อ — unittest ทั้งหมด (ไฟล์เดิมไม่เปลี่ยนระหว่างรัน: 4, สำเร็จ: 4, fatal: 5, ไฟล์ล็อก: 2, Stop: 2, ทางไม่เริ่ม: 1, regression R7 + test เดิม: 2, full suite (เลื่อนได้): 1)

### R10-5. ข้อจำกัด / สมมติฐาน

- Minimal diff: แก้เฉพาะ worker ของ `export_jobs_to_excel` (และส่วนก่อนเริ่ม worker เท่าที่จำเป็นสำหรับการตรวจไฟล์ล็อก) ใน `database_connect_gui.py`; ไม่แตะ `on_done` ยกเว้นข้อความกรณี R10-Q-3 / R10-Q-9 ถ้า design เลือกให้ผ่าน `fatal_error`; ไม่แตะ `load_jobs` / `load_preset_dialog` (Round 8-9 ยังไม่ commit); PEP 8 + type hints สำหรับ helper ใหม่ (ถ้ามี)
- ไฟล์ temp ต้องอยู่ **โฟลเดอร์เดียวกับปลายทาง** เพื่อให้ `os.replace` เป็นการ rename บน volume เดียวกัน (atomic บน NTFS) — ไม่ใช้ `%TEMP%`
- `pd.ExcelWriter` ยังใช้ `engine="openpyxl"`; เนื้อหา workbook ต้องเหมือนเดิมทุก byte ที่มีความหมาย (R10-AC-5 เทียบด้วย `openpyxl` ไม่เทียบ bytes ดิบ เพราะ zip มี timestamp)
- การตรวจ "ไฟล์ปลายทางเขียนได้" ตอนเริ่มต้องไม่แก้ไฟล์เดิม (ไม่ truncate ไม่เปลี่ยนเนื้อหา) และเมื่อปลายทางยังไม่มีไฟล์ต้องไม่สร้างไฟล์ที่ `file_path`; วิธีตรวจกำหนดในขั้น design (เช่นเปิดแบบไม่ truncate บน Windows ซึ่งจะ fail เมื่อ Excel ถือ handle อยู่) — ต้องไม่ทำให้ `tests/test_r2_table_data_refresh.py` (mock `Thread`, ปลายทางยังไม่มี) เปลี่ยนผล
- ปิดแอป / kill process ไม่สามารถลบ temp ได้ (thread เป็น `daemon=True` และ `on_closing` ไม่รอ worker) จึงรับประกันเฉพาะว่าไฟล์เดิมไม่เปลี่ยน (R10-AC-4); temp ที่ค้างจากกรณีนี้ตาม R10-Q-6
- `os.replace` แทนที่ทั้งไฟล์: attribute / ACL / เวลาสร้างของไฟล์เดิมไม่ถูกเก็บ; ไฟล์ปลายทางแบบ read-only ทำให้ `os.replace` ล้มและเข้าทาง R10-Q-3
- R10-AC-4 ใช้ `subprocess` + `sys.executable`; child สร้าง stub เองแบบเดียวกับ test อื่น (ไม่เปิด Tk จริง) — ถ้า QA พบว่าทำไม่ได้บนเครื่องนี้ให้รายงานเป็น `[!]` ไม่ตัด AC เอง
- ห้าม commit

### R10-6. คำถามที่ยังไม่มีคำตอบ

ทุกข้อมีคำตอบที่แนะนำซึ่ง AC ข้างต้นใช้เป็นค่าเริ่มต้นแล้ว ถ้าผู้ใช้ต้องการแบบอื่นให้แจ้งก่อนเริ่ม design

| # | คำถาม | คำตอบที่แนะนำ (default) |
|---|---|---|
| R10-Q-1 | ชื่อ / ที่อยู่ไฟล์ temp: (ก) ชื่อตายตัว `<stem>.tmp.xlsx` ตามที่ bug-hunter เสนอ, (ข) ชื่อไม่ซ้ำแบบสร้าง exclusive ในโฟลเดอร์เดียวกัน เช่น `<stem>.<สุ่ม>.tmp.xlsx` (`tempfile.mkstemp(dir=<โฟลเดอร์ปลายทาง>, prefix=f"{stem}.", suffix=".tmp.xlsx")`) | (ข) — ชื่อตายตัวอาจเขียนทับ / ลบไฟล์ของผู้ใช้ที่บังเอิญชื่อตรงกัน หรือชนกันเมื่อ export สองครั้งไปปลายทางเดียวกัน (R10-AC-3); ลงท้าย `.xlsx` ให้เปิดดูได้ถ้าค้าง; ไม่ใช้ prefix `~$` (ชนกับไฟล์ lock ของ Excel) และไม่ใช้ `%TEMP%` (R10-AC-2) |
| R10-Q-2 | กด Stop แล้วจะ (ก) แทนที่ไฟล์ปลายทางด้วย workbook บางส่วนเหมือนเดิม (ผ่าน temp + replace), (ข) ถือเป็นยกเลิก — ลบ temp และคงไฟล์เดิม, (ค) ถามผู้ใช้ตอน Stop | (ก) — คงพฤติกรรมเดิมของ Stop ให้มากที่สุดเพราะ B12 (ข้อความ / ความหมายของ Stop) อยู่นอกขอบเขต; การเปลี่ยนความหมาย Stop ควรตัดสินพร้อม B12 (R10-AC-16, R10-AC-17) ถ้าผู้ใช้เลือก (ข) ให้แก้ R10-AC-16/17 เป็น "ไฟล์เดิมไม่เปลี่ยน + ไม่มี temp" |
| R10-Q-3 | ไฟล์ปลายทางถูกล็อก (Excel เปิดอยู่): ตอนเริ่ม และตอน `os.replace` ล้มหลังรันเสร็จ จะทำอย่างไร | ตอนเริ่ม: ตรวจก่อนรัน query แล้ว fail เร็วพร้อม `showerror` (คงพฤติกรรมเดิมที่ `ExcelWriter` fail ทันที — R10-AC-14); ตอน replace ล้ม: **เก็บ temp ที่สมบูรณ์ไว้** แล้วแจ้ง path ปลายทาง, path temp และสาเหตุ ให้ผู้ใช้ปิด Excel แล้วเปลี่ยนชื่อเอง ไม่ทิ้งผลที่รันมาหลายชั่วโมง (R10-AC-15); ไม่ retry อัตโนมัติ ไม่มี dialog ถามซ้ำ — **หมายเหตุ (2026-11-23, R13-AC-11): "ไม่ retry อัตโนมัติ" ถูกแทนที่โดย R12-5 ที่ผู้ใช้สั่ง — ตอน replace ล้มด้วย `PermissionError` ให้ retry อัตโนมัติตาม `EXPORT_REPLACE_RETRY_DELAYS` (0.2 / 0.5 / 1.0 วินาที) ก่อน ถ้ายังล้มจึงเก็บ temp ตามเดิม; ส่วน "ตอนเริ่ม fail เร็ว" และ "ไม่มี dialog ถามซ้ำ" ยังคงเดิม** |
| R10-Q-4 | fatal error หลังเขียนไปแล้วบาง sheet: (ก) คงไฟล์เดิม ลบ temp (เปลี่ยนจากเดิมที่เขียน workbook บางส่วนทับ), (ข) แทนที่ด้วย workbook บางส่วนเหมือนเดิม | (ก) — คือหัวใจของ B3 "ไฟล์เดิมไม่เปลี่ยนจนกว่า export สำเร็จ"; workbook บางส่วนจาก fatal ไม่มีสัญญาณบอกว่าไม่ครบ (R10-AC-9) |
| R10-Q-5 | `tests/test_r4_excel_row_limit.py` mock `pd.ExcelWriter` ด้วย writer ปลอมที่ไม่สร้างไฟล์ และใช้ path สัมพัทธ์ `"export.xlsx"` — หลังแก้ `os.replace` จะหา temp ไม่เจอ / อาจสร้างไฟล์ใน repo: อนุญาตให้ปรับ harness หรือบังคับให้ design เข้ากันได้โดยไม่แก้ test | อนุญาตให้ปรับ **เฉพาะ harness** (path ใน `TemporaryDirectory`, stub การแทนที่ไฟล์) ไม่แตะ assertion ตามหลัก R7-AC-27 และรายงานไฟล์ที่ปรับ (R10-AC-20); ถ้า design ทำให้ผ่านได้โดยไม่แก้ก็ไม่ต้องปรับ |
| R10-Q-6 | temp ที่ค้างจากการปิดแอป / kill process ระหว่าง export ควรถูกล้างอัตโนมัติ (เช่นตอนเปิดแอปครั้งถัดไป) หรือไม่ | ไม่ — นอกขอบเขต (ต้องสแกนโฟลเดอร์ที่ผู้ใช้เลือกซึ่งแอปไม่ได้จดไว้); ชื่อ temp ตาม R10-Q-1 บอกชัดว่าเป็นไฟล์ชั่วคราว ผู้ใช้ลบเองได้ ไฟล์เดิมปลอดภัยแล้ว (R10-AC-4) |
| R10-Q-7 | Job ที่ไม่มี key `"query"` (`:10508` นอก `try` ราย Job) ควรเปลี่ยนเป็น Job Failed ราย Job แทนการล้มทั้ง export หรือไม่ | ไม่ใน Round นี้ — คงเป็น fatal แต่แสดงสาเหตุจริง (R10-AC-9, R10-AC-10); การเปลี่ยนเป็น Failed ราย Job เปลี่ยนตัวนับ / เนื้อหา workbook เป็น scope ใหม่ (Job ที่แอปสร้างเองมี `"query"` เสมอ และ R9 กัน preset เสียแล้ว) |
| R10-Q-8 | จุดอื่นที่เขียนไฟล์ลงปลายทางโดยตรง — `export_selected` (`:14084` `to_excel(save_path)` ในหน้าต่างเลือกค่า), `export_to_csv` (`:9106`), Export Profiles / Groups JSON (`:3419`, `:4500`) — ควรรวมใน Round นี้หรือไม่ | ไม่รวม — ทุกจุดเขียนข้อมูลที่อยู่ใน memory แล้วจบในไม่กี่วินาที ไม่มี query ยาวคั่น ความเสี่ยงต่ำกว่า B3 มาก ถ้าผู้ใช้ต้องการให้เปิดเป็น Round แยก |
| R10-Q-9 | เมื่อลบ temp ไม่ได้ (หลัง fatal) ควรแจ้งอย่างไร | เขียน 1 บรรทัดใน Execution Logs ระบุ temp path ที่ลบไม่ได้ (ไม่มี dialog เพิ่ม) และ `showerror` ยังแสดงสาเหตุต้นเหตุเท่านั้น (R10-AC-12) |
| R10-Q-10 | R10-AC-21 (full suite สองแบบ encoding) จะรันใน Round นี้หรือเลื่อนแบบ Round 8-9 | ให้ผู้ใช้ตัดสิน — ถ้าเลื่อน ให้รัน focused ตามที่ระบุใน R10-AC-21 แทน |

---

# Round 11 — Bugfix B4: Header "target" และ Tables ใช้ค่าจากช่องกรอก ไม่ใช่ connection จริง

> ใช้เลข `R11-AC-x` และ `R11-Q-x` แยกจาก Round ก่อนหน้า ไม่แก้เนื้อหา Round ก่อนหน้า
> ที่มา: รายงาน bug-hunter ข้อ B4 (ยืนยันด้วยการอ่านโค้ดเท่านั้น **ยังไม่ได้ทดสอบกับฐานข้อมูลจริง**) ผู้ใช้สั่งให้แก้ **เฉพาะ B4** — B5 (Stop ไม่หยุด `list_tables`) และบัคอื่นทั้งหมดอยู่นอกขอบเขต; การแก้ของ Round 8-10 ที่ยังไม่ commit ห้ามแตะ
> ไฟล์ที่เกี่ยวข้อง: `database_connect_gui.py` — label header `target_main` / `target_sub` (`:2531-2538`), closure `_refresh_target_summary` (`:2694-2709`, poll ทุก 500 ms, เรียกครั้งแรก `:2721`), badge `_refresh_conn_badge` (`:2732-2751`), `ConnectionInfo` (`:374-404`, "Never holds the password"), `RunTarget` (`:408-412`), `connect_database` (`:7651-7733`: อ่านช่องกรอก `:7654-7659`, บังคับ password ไม่ว่าง `:7663`, ล้ม → `_replace_engine(None)` `:7698`, สร้าง `ConnectionInfo` `:7707-7714`), `_replace_engine` (`:7735-7748`), `_capture_run_target` (`:7750-7762`), `_block_if_profile_mismatch` (`:8094-8117` เทียบเฉพาะชื่อ Profile), `_confirm_destination` / `_confirm_data_change` (`:8340-8398`, SELECT ไม่มี dialog), `execute_query` (`:8429-8473`), **`list_tables`** (`:9174-9448`: `current_db_name = self.db_name.get()` `:9191`, `connection_credentials` จากช่องกรอก `:9192-9199`, ทาง "ทุก database" ใช้ `engine` เดิมหา DB `:9222-9270` แล้ว `get_connection_string(... credentials ...)` + `create_engine` ราย DB `:9294-9305`, ทาง "database ปัจจุบัน" `:9397-9428`, `on_list_tables_success(..., bool(current_db_name))` `:9433-9435`), `_reset_profile_connection_state` (`:11121-11147`); test เดิมที่เกี่ยวข้อง `tests/test_run_target.py` (`test_no_password_like_field`, `test_password_never_stored`), `tests/test_bugfix_h1.py`, `tests/test_run_engine_batch.py`, `tests/test_list_tables_stop.py`, `tests/test_bugfix_c1.py`, `tests/test_r4_profile_mismatch.py`, `tests/test_run_entry_block.py`, `tests/test_confirm_destination.py`, `tests/test_profile_connect_block.py`, `tests/test_profile_password.py`
> เลขบรรทัดอ้างอิงไฟล์ ณ วันที่เขียน spec (2026-11-20 — หลังแก้ Round 8-10 ที่ยังไม่ commit; รายงาน bug-hunter อ้าง `:2643-2658` / `:9106-9114` ซึ่งเลื่อนมาเป็น `:2694-2709` / `:9191-9199`) อาจคลาดเคลื่อนเล็กน้อย

### R11-1. เป้าหมาย

หลัง Connect แล้ว ผู้ใช้แก้ช่อง Host / Port / Database / User / Database Type ในแถบ Details ได้โดยไม่ต้องกด Connect ใหม่ แต่ connection จริง (`self.engine` + `ConnectionInfo` ใน `_run_target`) ยังชี้ไปที่ปลายทางเดิม สองจุดยังอ่านค่าจากช่องกรอกแทน connection จริง:

1. **Header "target"** (`_refresh_target_summary` `:2694-2709`) แสดง `db_type · user@host:port` และ `Database / Service: <db>` จาก **ช่องกรอก** ทุก 500 ms ขณะที่ badge แสดง `Connected` ตัวอย่าง: Connect ไป UAT → แก้ช่อง Database/Service เป็น PROD → header แสดง PROD + `Connected` แต่ `execute_query` รันบน engine ของ UAT; SELECT ไม่มี dialog ยืนยัน (DML มีและแสดงปลายทางถูกต้องจาก snapshot) และ `_block_if_profile_mismatch` เทียบเฉพาะชื่อ Profile จึงไม่จับกรณีนี้ → ผู้ใช้เชื่อว่าผลลัพธ์มาจาก PROD
2. **`list_tables`** อ่าน `db_name`, user, password, host, port จากช่องกรอก (`:9191-9199`): ตัดสินว่าจะ list "ทุก database" หรือ "database ปัจจุบัน" จากช่องกรอก, ใช้ engine เดิมหารายชื่อ DB แต่สร้าง engine ราย DB ด้วย host / user / port **ใหม่** จากช่องกรอก → ผลลัพธ์ผสมสอง server และ label คอลัมน์ `Database` ผิด

เป้าหมาย: ขณะ Connect อยู่ ทั้ง header และ `list_tables` ใช้ปลายทางจาก `ConnectionInfo` ของ connection จริง (snapshot ตอน Connect) และ header เตือนให้เห็นชัดเมื่อช่องกรอกไม่ตรงกับ connection; ไม่มีการเก็บ password ใน `ConnectionInfo` / `RunTarget` (คงหลักเดิม)

ผู้ได้ประโยชน์: ผู้ใช้ที่สลับ UAT / PROD โดยแก้ช่อง Details และผู้ใช้ปุ่ม Tables

### R11-2. ขอบเขต

#### In scope

- **Header ขณะ Connect**: เมื่อ `_capture_run_target()` คืน `RunTarget` ที่มี `info` ให้ `target_main` / `target_sub` แสดงค่าจาก `info` (รูปแบบข้อความเดิมทุกประการ) แทนช่องกรอก
- **Header ขณะไม่ได้ Connect** (ยังไม่ Connect, Connect ล้ม, หลัง `_reset_profile_connection_state`) หรือ `info is None`: แสดงจากช่องกรอกเหมือนเดิม
- **คำเตือนเมื่อช่องกรอกไม่ตรง**: ขณะ Connect และช่องกรอกต่างจาก `info` (เกณฑ์ตาม R11-Q-4) header แสดงคำเตือนตาม R11-Q-2 และกลับเป็นปกติเมื่อแก้ช่องกลับให้ตรง หรือกด Connect ใหม่สำเร็จ
- **แยก logic header ให้ทดสอบได้**: ส่วนที่อ่านค่า + `config` label ของ `_refresh_target_summary` ย้ายเป็น method ของ `DatabaseConnectorGUI` ที่รับ label ทั้งสองเป็น argument (ชื่อกำหนดใน design) closure เดิมเรียก method นี้แล้วตั้ง `after(500, ...)` เหมือนเดิม
- **`list_tables` ใช้ snapshot**: เมื่อ `target.info` มีค่า — การเลือกทาง "ทุก database" / "database ปัจจุบัน", label คอลัมน์ `Database`, ค่า flag ที่ส่งให้ `on_list_tables_success` และ user / host / port / db_type ของ engine ราย DB มาจาก `target.info`; password มาจากค่าที่เก็บไว้ตอน Connect ตาม R11-Q-5 — ไม่อ่านช่องกรอกใด ๆ
- **เก็บ password ของ connection ปัจจุบัน** (ตาม R11-Q-5) ใน memory แยกจาก `ConnectionInfo` / `RunTarget`, ผูกกับ engine ปัจจุบัน, ล้างเมื่อ engine ถูกแทน / ตัด; ไม่เขียนลง Execution Logs, run log, console หรือไฟล์ใด
- กรณีไม่มี password ที่เก็บไว้ / `info is None` ตาม R11-Q-6 / R11-Q-7

#### Out of scope

- **B5** (Stop ไม่หยุด `list_tables`) และบัคอื่นทั้งหมดจากรายงาน bug-hunter; Round 8-10 ที่ยังไม่ commit
- การ block / ยืนยัน / log เพิ่มตอน Run, Run Job, Run All, Export เมื่อช่องกรอกไม่ตรง — ค่าเริ่มต้นคือเตือนที่ header เท่านั้น (R11-Q-1); `_block_if_profile_mismatch` และ `_confirm_data_change` ไม่เปลี่ยน
- การ reconnect อัตโนมัติเมื่อแก้ช่องกรอก, ปุ่ม Disconnect, การเปลี่ยนข้อความ badge `Connected · <db_type>` หรือ `status_label`
- จุดอื่นที่อ่านช่องกรอกขณะ Connect: Save Job (`"database": self.db_name.get()` `:9726`), Save Profile (`:11252-11263`) — R11-Q-8
- การเพิ่ม field ใน `ConnectionInfo` / `RunTarget` (ห้ามมี field password — `test_no_password_like_field`)
- การเปลี่ยน logic ภายในทาง "ทุก database" นอกเหนือจากแหล่งค่า (query หารายชื่อ DB, skip schema, ทาง Oracle ใช้ engine เดิม), การเปลี่ยน `get_connection_string` / `connect_database` นอกจากการเก็บ password
- refactor / rename / commit

### R11-3. User stories

- **R11-US-1**: ในฐานะผู้ใช้ที่ Connect ไป UAT แล้วเผลอแก้ช่อง Database เป็น PROD ฉันต้องการให้ header ยังบอกว่า connection จริงคือ UAT และเตือนว่าช่องกรอกไม่ตรง เพื่อไม่เข้าใจผิดว่าผล SELECT มาจาก PROD
- **R11-US-2**: ในฐานะผู้ใช้คนเดียวกัน ฉันต้องการให้ header กลับเป็นปกติเมื่อกด Connect ใหม่ เพื่อรู้ว่าตอนนี้ใช้ค่าใหม่แล้ว
- **R11-US-3**: ในฐานะผู้ใช้ปุ่ม Tables ฉันต้องการให้รายชื่อ table มาจาก server ที่ Connect อยู่จริงทั้งหมด ไม่ผสมกับ server ที่พิมพ์ค้างในช่องกรอก
- **R11-US-4**: ในฐานะผู้ดูแลความปลอดภัย ฉันต้องการให้ password ไม่ปรากฏใน snapshot / log / console เพิ่มขึ้นจากเดิม

### R11-4. Acceptance criteria

วิธีทดสอบทุกข้อเป็น `unittest` ตามแนวทาง `tests/test_run_target.py` / `tests/test_bugfix_h1.py` / `tests/test_run_engine_batch.py` (stub จาก `DatabaseConnectorGUI.__new__`, `_FakeEntry` ที่ตั้งค่าได้และ `forbid_get` ได้, label ปลอมที่จำ `text` / `fg`, `threading.Thread` ที่จับ `target` / `args` แล้วรันเอง, patch `create_engine` / `inspect` / `messagebox` / `print`) ไม่ต่อฐานข้อมูลจริง ไม่เปิด Tk จริง ไฟล์ test ใหม่: `tests/test_r11_connection_target_snapshot.py`

นิยาม:
- "snapshot UAT" = `ConnectionInfo(profile="P1", db_type="PostgreSQL", user="app", host="uat-db", port="5432", database="UAT")` ใน `_run_target = RunTarget(engine_uat, info)` และ `self.engine is engine_uat`
- "ช่องกรอก PROD" = ช่องกรอกเหมือน snapshot UAT ทุกช่อง ยกเว้น `db_host = "prod-db"` และ `db_name = "PROD"`
- "method header" = method ที่แยกจาก `_refresh_target_summary` ตาม R11-2 เรียกด้วย label ปลอม `target_main`, `target_sub`
- "รูปแบบเดิม" = `main = f"{db_type} · {user}@{host}" + (f":{port}" if port else "")`, `sub = f"Database / Service: {db}" if db else "Database: (default)"` (ตาม `:2701-2702`)
- "คำเตือน" = ข้อความตาม R11-Q-2 (ค่าเริ่มต้น: มี `⚠` และคำว่า `Connect`)

#### Header

| AC | Given / When / Then |
|---|---|
| R11-AC-1 | **Given** ไม่ได้ Connect (`engine is None`, `_run_target is None`) และช่องกรอกค่าใดก็ได้ **When** เรียก method header **Then** `target_main` / `target_sub` เท่ากับรูปแบบเดิมจากช่องกรอก (strip) — พฤติกรรมเดิม ไม่มีคำเตือน และ `target_sub` ใช้สี `UI["muted"]` |
| R11-AC-2 | **Given** snapshot UAT และช่องกรอกตรงกับ snapshot ทุกช่อง **When** เรียก method header **Then** `target_main == "PostgreSQL · app@uat-db:5432"`, `target_sub == "Database / Service: UAT"` (ตรงกับรูปแบบเดิมทุกตัวอักษร) ไม่มีคำเตือน สี `UI["muted"]` |
| R11-AC-3 | **Given** snapshot UAT และช่องกรอก PROD **When** เรียก method header **Then** `target_main` / `target_sub` แสดงค่าจาก snapshot (`uat-db`, `UAT`) **ไม่มี** `prod-db` / `PROD` และ header มีคำเตือน (R11-Q-2) — สีของบรรทัดที่มีคำเตือนเปลี่ยนเป็นสีเตือนที่ design กำหนด (ไม่ใช่ `UI["muted"]`) |
| R11-AC-4 | **Given** snapshot UAT **When** แก้ช่องกรอกทีละช่องให้ต่างจาก snapshot (`db_type`, `db_user`, `db_host`, `db_port`, `db_name` — แยก subTest) แล้วเรียก method header **Then** ทุกกรณีมีคำเตือน; เมื่อแก้แค่ `db_password` หรือเปลี่ยน `profile_combo` **ไม่** มีคำเตือน (R11-Q-3; Profile ต่างเป็นหน้าที่ของ `_block_if_profile_mismatch`) |
| R11-AC-5 | **Given** snapshot UAT **When** ช่องกรอกต่างจาก snapshot เฉพาะช่องว่างหน้า/หลัง (`" uat-db "`) หรือ port แบบ `"5432:x"` (แบบที่ `connect_database` ตัดเป็น `5432`) **Then** ไม่มีคำเตือน (เกณฑ์ R11-Q-4) |
| R11-AC-6 | **Given** snapshot UAT + ช่องกรอก PROD (มีคำเตือน) **When** (ก) แก้ช่องกลับเป็นค่า UAT แล้วเรียก method header, (ข) เรียก `connect_database` สำเร็จด้วยช่องกรอก PROD (patch `create_engine` / `messagebox`) แล้วเรียก method header **Then** (ก) คำเตือนหาย สีกลับ `UI["muted"]`; (ข) header แสดง `prod-db` / `PROD` ไม่มีคำเตือน |
| R11-AC-7 | **Given** snapshot UAT + ช่องกรอก PROD **When** Connect ใหม่ล้ม (`create_engine` raise) หรือ `_reset_profile_connection_state` ตัด connection แล้วเรียก method header **Then** header แสดงจากช่องกรอก (`prod-db` / `PROD`) ไม่มีคำเตือน — ตาม R11-AC-1 เพราะไม่มี connection แล้ว |
| R11-AC-8 | **Given** `self.engine` มีค่าแต่ `_run_target` เป็น `RunTarget(engine, None)` (engine ที่ไม่ได้มาจาก `connect_database`) **When** เรียก method header **Then** แสดงจากช่องกรอกแบบเดิม ไม่มีคำเตือน (R11-Q-7) |
| R11-AC-9 | **Given** label ปลอมที่ `config` แล้ว raise `tk.TclError` (หน้าต่างถูกปิด) **When** เรียก closure / method header **Then** ไม่มี exception หลุด และไม่ตั้ง `after` รอบถัดไป — พฤติกรรมเดิม `:2707-2709`; และเมื่อข้อความ / สีไม่เปลี่ยน ไม่เรียก `config` ซ้ำ (คงการเช็ก `cget` เดิม) |

#### Run (regression lock — ค่าเริ่มต้น R11-Q-1 = เตือนที่ header เท่านั้น)

| AC | Given / When / Then |
|---|---|
| R11-AC-10 | **Given** snapshot UAT + ช่องกรอก PROD และ SQL `SELECT 1` **When** `execute_query` **Then** `_execute_query_background` ได้ `engine is engine_uat`, ไม่มี dialog ยืนยัน, ไม่มีบรรทัด `⛔` ใน Execution Logs (ไม่ block) — พฤติกรรมเดิม; และ SQL `DELETE FROM t` ยังแสดงปลายทาง `PostgreSQL · uat-db / UAT` ใน dialog ยืนยันเหมือนเดิม |

#### `list_tables` ใช้ snapshot

| AC | Given / When / Then |
|---|---|
| R11-AC-11 | **Given** snapshot แบบ "ทุก database" (`info.database == ""`, `db_type="MySQL"`, `host="uat-db"`, `user="app"`, `port="3306"`), engine เดิมคืนรายชื่อ DB `["d1", "d2"]`, password ที่เก็บตอน Connect = `"pw-uat"` และช่องกรอก `db_host="prod-db"`, `db_user="other"`, `db_port="9999"`, `db_password="pw-prod"`, `db_name=""` **When** `list_tables` แล้วรัน worker **Then** `get_connection_string` ถูกเรียก 2 ครั้งด้วย `("MySQL", "app", "pw-uat", "uat-db", "3306", "d1")` และ `(... "d2")` — ไม่มีค่าใดจากช่องกรอก |
| R11-AC-12 | **Given** snapshot "ทุก database" เหมือน R11-AC-11 แต่ช่องกรอก `db_name="PROD"` **When** `list_tables` **Then** ใช้ทาง "ทุก database" (engine เดิมถูก query หารายชื่อ DB, `create_engine` ราย DB ถูกเรียก) และ `on_list_tables_success` ได้ flag `False`; กลับกัน snapshot `info.database="UAT"` + ช่องกรอก `db_name=""` → ใช้ทาง "database ปัจจุบัน" (`inspect(engine_uat)`, `create_engine` ไม่ถูกเรียก), ทุกแถวมี `"Database": "UAT"` และ flag `True` |
| R11-AC-13 | **Given** snapshot (มี `info`) **When** `list_tables` และ worker ทำงาน **Then** `get()` ของ `db_name`, `db_user`, `db_password`, `db_host`, `db_port`, `db_type` **ไม่ถูกเรียกเลย** (ใช้ `forbid_get` ตั้งแต่ก่อนเรียก) |
| R11-AC-14 | **Given** snapshot ตาม R11-AC-11 **When** `list_tables` **Then** ค่าที่ worker ใช้ถูกจับบน main thread ก่อน `Thread.start()` (คงหลัก R5 / `test_bugfix_h1`): หลัง start แล้ว `connect_database` ไป server อื่น (snapshot + password ใหม่) worker ยังใช้ `app` / `pw-uat` / `uat-db` / `3306` ของตอนกด Tables |
| R11-AC-15 | **Given** snapshot ทาง Oracle (`db_type="Oracle"`, `info.database==""`) และช่องกรอกต่างจาก snapshot **When** `list_tables` **Then** ใช้ `inspect(engine_uat)` เท่านั้น `create_engine` ไม่ถูกเรียก (พฤติกรรมเดิม) และไม่ต้องใช้ password ที่เก็บไว้ (ทำงานได้แม้ไม่มี password เก็บไว้) |
| R11-AC-16 | **Given** snapshot "ทุก database" ที่ไม่ใช่ Oracle แต่ไม่มี password เก็บไว้สำหรับ engine ปัจจุบัน (เช่น stub ตั้ง `_run_target` โดยไม่ผ่าน `connect_database`) **When** `list_tables` **Then** ตามค่าเริ่มต้น R11-Q-6: Execution Logs มี 1 บรรทัดขึ้นต้น `⛔ Tables ไม่ได้เริ่มงาน` ที่บอกให้กด Connect ใหม่, thread ไม่ถูกเริ่ม, `create_engine` / `get_connection_string` ไม่ถูกเรียก, ช่องกรอกไม่ถูกอ่าน, ปุ่ม `inspect_btn` ไม่ถูกเปลี่ยนเป็น `⏳ Loading...` |
| R11-AC-17 | **Given** `_run_target = RunTarget(engine, None)` (ไม่มี `info`) **When** `list_tables` **Then** อ่านช่องกรอกแบบเดิมทุกประการ (R11-Q-7) — `tests/test_bugfix_h1.py` และ `tests/test_run_engine_batch.py` (`test_current_db_inspects_start_engine`, `test_no_info_reads_db_type_before_thread_starts`) ผ่านโดยไม่แก้ |

#### Password ของ connection ปัจจุบัน

| AC | Given / When / Then |
|---|---|
| R11-AC-18 | **Given** `connect_database` สำเร็จด้วย password `"S3cr3t-UAT"` (patch `create_engine` ด้วย sqlite จริงแบบ `test_password_never_stored`) **When** ตรวจ **Then** `list_tables` ทาง "ทุก database" ได้ password นั้น (R11-AC-11), password **ไม่** อยู่ใน `repr` / `str` / `dataclasses.asdict` ของ `ConnectionInfo` / `RunTarget`, `target_label()`, `log_target()`, `run_log_header()`, Execution Logs, ข้อความที่ส่งเข้า `_write_run_log` และ stdout ที่ patch `print` จับได้ระหว่าง `list_tables`; `tests/test_run_target.py` (`test_no_password_like_field`, `test_password_never_stored`) ผ่านโดยไม่แก้ |
| R11-AC-19 | **Given** Connect UAT สำเร็จ (password A) **When** (ก) Connect ไป PROD สำเร็จ (password B), (ข) Connect ใหม่ล้ม, (ค) `_reset_profile_connection_state` ตัด connection **Then** (ก) password ที่ใช้ได้คือ B เท่านั้น; (ข) และ (ค) ไม่มี password เก็บไว้ (ค่าเดิมถูกล้าง ไม่ใช่แค่ถูกบัง) — ตรวจผ่าน accessor ที่ design กำหนด |
| R11-AC-20 | **Given** Connect UAT สำเร็จด้วย password A แล้วผู้ใช้แก้ช่อง `db_password` เป็น B โดยไม่ Connect **When** `list_tables` ทาง "ทุก database" **Then** `get_connection_string` ได้ A (password ของ connection จริง) |

#### Regression

| AC | Given / When / Then |
|---|---|
| R11-AC-21 | **Given** test เดิม `tests/test_run_target.py`, `tests/test_bugfix_h1.py`, `tests/test_run_engine_batch.py`, `tests/test_list_tables_stop.py`, `tests/test_bugfix_c1.py`, `tests/test_r4_profile_mismatch.py`, `tests/test_run_entry_block.py`, `tests/test_confirm_destination.py`, `tests/test_profile_connect_block.py`, `tests/test_profile_password.py`, `tests/test_r8_load_jobs_writeback.py`, `tests/test_r9_load_preset_validation.py`, `tests/test_r10_export_atomic_write.py` **When** รันหลังแก้ **Then** ผ่านโดยไม่แก้ test ใด (ถ้า stub เดิมขาด attribute ใหม่ ต้องแก้ที่โค้ดด้วย `getattr(..., default)` ไม่ใช่แก้ test) — **ข้อยกเว้นเดียว (R11-Q-10)**: ใน `tests/test_run_engine_batch.py` test `ListTablesEngineTests::test_info_db_type_wins_over_screen_at_start` อนุญาตให้เพิ่ม setup 1 บรรทัด `stub._connected_password = (engine_a, "pw")` ก่อน `self._start(stub)` เท่านั้น ห้ามแก้ assertion ใด และห้ามแก้ test อื่น |
| R11-AC-22 | **Given** แก้ B4 ครบ **When** รัน `python -m unittest discover -s tests -p "test_*.py"` สองแบบตาม R7-AC-28 ((ก) `PYTHONIOENCODING=utf-8`, (ข) ไม่ตั้ง บน `cp874` + redirect) **Then** ทั้งสองแบบ `OK` จำนวน test เท่ากัน — **AC นี้แยกไว้ให้ผู้ใช้เลื่อนได้** (R11-Q-9): ถ้าเลื่อน ให้รัน focused `tests.test_r11_connection_target_snapshot` + ทุกไฟล์ใน R11-AC-21 แทน และบันทึกว่า R11-AC-22 รอ |

**สรุปจำนวน AC Round 11**: 22 ข้อ — unittest ทั้งหมด (header: 9, Run regression: 1, `list_tables`: 7, password: 3, regression test เดิม: 1, full suite (เลื่อนได้): 1)

### R11-5. ข้อจำกัด / สมมติฐาน

- บัคยืนยันด้วยการอ่านโค้ดเท่านั้น; การทดสอบทั้งหมดใช้ stub / mock ไม่ต่อ DB จริง — ผล "ไม่ผสมสอง server" ยืนยันระดับ argument ที่ส่งให้ `get_connection_string` / `create_engine` เท่านั้น
- Minimal diff: แก้ `_refresh_target_summary` (แยก method), `list_tables` (เฉพาะแหล่งค่า + ทาง R11-Q-6), `connect_database` / `_replace_engine` / `_reset_profile_connection_state` (เฉพาะเก็บ / ล้าง password); ไม่แตะ `ConnectionInfo` / `RunTarget` / `_block_if_profile_mismatch` / `_confirm_data_change`; PEP 8 + type hints สำหรับ method ใหม่
- `ConnectionInfo` เก็บ `user` / `host` / `database` แบบ strip แล้ว ขณะที่ engine เดิมสร้างจากค่าไม่ strip (`:7673-7675`) — `list_tables` ใช้ค่าจาก `info` (strip) ซึ่งถือว่าถูกต้องกว่า; password ใช้ค่าตามที่ใช้สร้าง engine (ไม่ strip)
- ใน flow จริงของแอป engine ถูกตั้งผ่าน `connect_database` → `_replace_engine(engine, info)` เท่านั้น จึงมี `info` และ password (ไม่ว่าง ตาม `:7663`) เสมอขณะ Connect; กรณี `info is None` / ไม่มี password เกิดใน stub / test เท่านั้น
- password ที่เก็บไว้อยู่ใน memory เท่านั้น (เทียบเท่าที่ engine URL ถืออยู่แล้ว) ไม่เพิ่มการเปิดเผยใหม่
- Header ยัง poll ทุก 500 ms; ไม่เพิ่ม event binding ใหม่
- ห้าม commit

### R11-6. คำถามที่ยังไม่มีคำตอบ

ทุกข้อมีคำตอบที่แนะนำซึ่ง AC ข้างต้นใช้เป็นค่าเริ่มต้นแล้ว ถ้าผู้ใช้ต้องการแบบอื่นให้แจ้งก่อนเริ่ม design

| # | คำถาม | คำตอบที่แนะนำ (default) |
|---|---|---|
| R11-Q-1 | เมื่อช่องกรอกไม่ตรงกับ connection จะ (ก) เตือนที่ header เท่านั้น, (ข) (ก) + เขียน 1 บรรทัดเตือนใน Execution Logs ตอนเริ่ม Run / Tables / Run Job / Export แล้วรันต่อ, (ค) block ทุกทางเข้าแบบ `_block_if_profile_mismatch` จนกว่าจะ Connect ใหม่หรือแก้ช่องกลับ, (ง) dialog ยืนยันแม้เป็น SELECT | (ก) — header แสดงปลายทางจริงแล้ว ผู้ใช้เห็นความจริงก่อนกด Run; minimal diff ไม่กระทบทางเข้า / test เดิม (R11-AC-10). (ค) ปลอดภัยสุดแต่เพิ่ม scope ทุกทางเข้า + ต้องแก้ test entry-block; ถ้าผู้ใช้เลือก (ข)/(ค)/(ง) ต้องเพิ่ม AC ใหม่และแก้ R11-AC-10 |
| R11-Q-2 | ข้อความ / ตำแหน่งคำเตือนบน header | ต่อท้าย `target_sub` เป็น `"<sub เดิม>  ·  ⚠ ช่อง Details ไม่ตรงกับ connection — กด Connect เพื่อใช้ค่าใหม่"` และเปลี่ยนสี `target_sub` เป็นสีเตือน (เช่น `#D97706` แบบ pill `warn`); ไม่ระบุว่าช่องไหนต่าง ไม่เพิ่ม widget ใหม่ — AC assert เฉพาะ `⚠`, `Connect` และสีไม่ใช่ `UI["muted"]` |
| R11-Q-3 | การแก้ช่อง Password อย่างเดียว (โดยไม่ Connect) ควรนับว่า "ไม่ตรง" หรือไม่ | ไม่นับ — password ไม่เปลี่ยนปลายทาง และการเทียบต้องอ่าน password ที่เก็บไว้ในทุก poll 500 ms โดยไม่จำเป็น (R11-AC-4) |
| R11-Q-4 | เกณฑ์ "ตรงกัน" | เทียบ 5 ช่อง `db_type`, `user`, `host`, `port`, `database` หลัง `strip()`; port ตัดด้วย `split(":")[0]` แบบเดียวกับ `connect_database`; เทียบแบบ case-sensitive (ตามที่ `ConnectionInfo` เก็บ) — host `UAT-DB` กับ `uat-db` จึงนับว่าต่าง (เตือนเกินดีกว่าเตือนขาด) |
| R11-Q-5 | `list_tables` ทาง "ทุก database" ต้องใช้ password — เอามาจากไหน: (ก) เก็บใน attribute ส่วนตัวของ GUI ตอน Connect สำเร็จ ผูกกับ engine (แยกจาก `ConnectionInfo` / `RunTarget`), (ข) ดึงจาก `engine.url` ของ SQLAlchemy (`url.set(database=...)`) ไม่ต้องเก็บเพิ่ม, (ค) ใช้ช่อง Password เฉพาะเมื่อช่องอื่นตรงกับ snapshot ไม่งั้น block | (ก) — ตรงกับที่ bug-hunter เสนอ ทำงานเหมือนกันทุก db_type; (ข) ใช้ไม่ได้ตรง ๆ กับ SQL Server ที่ใช้ `odbc_connect` (ต้อง parse / สร้าง connection string ใหม่) และผูกกับ SQLAlchemy internals; (ค) ยังพังเมื่อผู้ใช้แก้ password อย่างเดียว (R11-AC-20) |
| R11-Q-6 | มี `info` แต่ไม่มี password เก็บไว้ (เกิดได้เฉพาะ stub / อนาคต) ในทาง "ทุก database" ที่ไม่ใช่ Oracle จะ (ก) block พร้อม log ให้กด Connect ใหม่, (ข) fallback ไปอ่านช่อง Password, (ค) list เฉพาะรายชื่อ DB โดยไม่เข้าแต่ละ DB | (ก) — ไม่ผสมแหล่งค่า (หัวใจของ B4) และไม่เดา; ทาง "database ปัจจุบัน" และ Oracle ไม่ต้องใช้ password จึงทำงานต่อได้ (R11-AC-15, R11-AC-16) |
| R11-Q-7 | `RunTarget(engine, None)` (ไม่มี `info`) — header / `list_tables` ทำอย่างไร | คงพฤติกรรมเดิม (อ่านช่องกรอก) เพราะไม่มี snapshot ให้เทียบ และกรณีนี้ไม่เกิดใน flow จริง; รักษา test เดิม `test_bugfix_h1` / `test_run_engine_batch` (R11-AC-8, R11-AC-17) |
| R11-Q-8 | จุดอื่นที่อ่านช่องกรอกขณะ Connect — Save Job บันทึก `"database": self.db_name.get()` (`:9726`) และ `"db_type": self.db_type.get()` ซึ่งอาจไม่ตรงกับ connection ที่ใช้รัน — รวมใน Round นี้หรือไม่ | ไม่รวม — เป็น metadata ของ Job ไม่ได้เปลี่ยนปลายทางที่รัน และไม่อยู่ในรายงาน B4; ถ้าผู้ใช้ต้องการให้เปิด Round แยก |
| R11-Q-9 | R11-AC-22 (full suite สองแบบ encoding) จะรันใน Round นี้หรือเลื่อนแบบ Round 8-10 | ให้ผู้ใช้ตัดสิน — ถ้าเลื่อน ให้รัน focused ตามที่ระบุใน R11-AC-22 แทน |
| R11-Q-10 | Blocker R11-R1 (ดู Round 11 ใน `docs/design.md` / `docs/tasks.md`): `test_info_db_type_wins_over_screen_at_start` ใน `tests/test_run_engine_batch.py` ตั้ง `info` แต่ไม่มี password ที่เก็บไว้ จึงชนกับ R11-Q-6 (block) และขัดกับ R11-AC-21 (ห้ามแก้ test) | **ผู้ใช้ตัดสินแล้ว: ตัวเลือก (a)** — อนุญาตให้ปรับ harness เฉพาะ test นี้ โดยเพิ่ม setup 1 บรรทัด `stub._connected_password = (engine_a, "pw")` ก่อน `self._start(stub)`; ห้ามแก้ assertion ใด ตามแนวทางเดียวกับ R10-Q-5; R11-AC-21 ปรับให้ระบุข้อยกเว้นนี้แล้ว |

---

# Round 13 — Follow-up: ข้อเสนอแนะ 🟢 ทั้ง 9 ข้อจาก Code Review Round 12 (ก่อนเปิด PR เข้า main)

> ใช้เลข `R13-AC-x` และ `R13-Q-x` แยกจาก Round ก่อนหน้า ไม่ลบเนื้อหา Round ก่อนหน้า (ยกเว้นหมายเหตุที่เพิ่มใน R10-AC-15 / R10-Q-3 ตาม R13-AC-11)
> ที่มา: `docs/review.md` หัวข้อ `# Code Review — Round 12` ส่วน 🟢 Suggestion ข้อ 1-9 (🟡 ข้อ 1 แก้แล้วใน commit `d2c4dd5`) — ผู้ใช้สั่ง "แก้ก่อน" ทั้ง 9 ข้อ
> ไฟล์ที่เกี่ยวข้อง (เลขบรรทัด ณ 2026-11-23 อาจคลาดเล็กน้อย): `database_connect_gui.py` — `_SECRET_PATTERNS` / `redact_secrets` (`:94-121`), `load_preset_dialog` filter (`:5692-5694`), `connect_database` (`:7725-7807`, except `:7764-7779`), `_show_connection_error` (`:7911-7944`, `ui_dialog(..., message=str(error))` `:7939`), `results_text.insert` ถูกห่อให้เขียน run log ด้วย (`:3300-3308`), `list_tables` worker (`:9438`, `:9441`, `:9547`, `:9551`, `:9564`, `:9567`, ส่ง error `:9612`), `on_list_tables_error` (`:9724-9740`), `new_profile_dialog` → closure `test_connection` (`:11632-11674`, ข้อความ error `:11656-11658`); tests: `tests/test_r8_load_jobs_writeback.py:305`, `tests/test_r10_export_atomic_write.py:175-178`, `tests/test_r11_connection_target_snapshot.py:982-1012`, `tests/test_database_connect_gui_core.py`

### R13-1. เป้าหมาย

ปิดข้อเสนอแนะ 🟢 ที่ค้างจาก review Round 12 ก่อนเปิด PR เข้า main โดยหลักคือ **ไม่ให้ password หลุดผ่านข้อความ error ของการ Connect** (🟢3): ตอนนี้ `connect_database` แสดง `❌ Connection Error: {error}` ดิบใน Execution Logs (ซึ่งถูกเขียนลง `logs/run_YYYY-MM-DD.log` ด้วย) และ dialog Connection Error; ปุ่ม "ทดสอบการเชื่อมต่อ" ใน New Profile ก็แสดง error ดิบ — ถ้า driver / SQLAlchemy ใส่ connection string ไว้ใน error (SQL Server `odbc_connect=...PWD=...`) รหัสจะปรากฏบนจอและในไฟล์ log; ที่เหลือเป็นการปรับ pattern ของ `redact_secrets`, test ที่ขาด, ความสม่ำเสมอของโค้ด และเอกสาร

ผู้ได้ประโยชน์: ผู้ใช้ที่ Connect ล้ม (รหัสไม่ไปอยู่ในจอ / log ที่ส่งต่อคนอื่น), ผู้ดูแลความปลอดภัย, ผู้พัฒนา Round ถัดไป

### R13-2. ขอบเขต

#### In scope

- **🟢3 เส้นทาง error ของการ Connect** (ค้นแล้วมี 2 จุดที่สร้าง connection และแสดง error):
  1. `connect_database` except — (ก) `results_text.insert("❌ Connection Error: ...")` (→ Execution Logs + run log), (ข) `_show_connection_error`: Label ในกล่องแดง (`msg`) และ `ui_dialog(message=...)`
  2. `new_profile_dialog` → `test_connection` → `work()` except — ข้อความ `✕  เชื่อมต่อไม่สำเร็จ: ...` ใน `result_label`
  - ทุกจุดต้องผ่าน `redact_secrets(str(error), <password ที่ใช้สร้าง connection นั้น>)` **ก่อน** ตัดบรรทัด / ตัดความยาว; ข้อความส่วนอื่นคงเดิม
  - Tables (`list_tables` / `on_list_tables_error`) ทำแล้วใน R12-7 — Round นี้แก้เฉพาะ 🟢1 / 🟢4
- **🟢1** `on_list_tables_error` ใช้ password เดียวกับที่ worker ใช้ (`credentials[1]`) ส่งไปพร้อม error
- **🟢2** ปรับ `_SECRET_PATTERNS` ตาม R13-Q-1 (ค่าเริ่มต้น: แก้ (ข) (ค) (ง), ยอมรับ (ก) (จ) เป็น known limit)
- **🟢4** แยกบรรทัด `redact_secrets(...)` ที่ยาวใน `list_tables` worker; `quote_plus` import ระดับ module
- **🟢5** หมายเหตุใน R10-AC-15 / R10-Q-3 ว่าถูก R12-5 แทน — **PM ใส่แล้วใน Round นี้** (ข้อความเดิมคงอยู่)
- **🟢6** test pin ค่า `EXPORT_REPLACE_RETRY_DELAYS`
- **🟢7** unit test ตรงของ `write_json_atomic` 3 ทาง (`json.dump` ล้ม, `fsync` ล้ม, `BaseException`)
- **🟢8** แก้ comment `tests/test_r8_load_jobs_writeback.py:305` ให้ตรงความจริง (ข้อยกเว้นของกฎห้ามแก้ test เดิม — comment เท่านั้น)
- **🟢9** filter ใน `load_preset_dialog` (`:5692-5694`) ทน element ที่ไม่ใช่ dict ตาม R13-Q-3

#### Out of scope

- error ของการ **รัน** query / Run Job / Run All / Export (`on_query_error_enhanced`, `on_query_error`, Error & Debug tab, debug print `:6997-7001`, `show_batch_error`, `show_critical_error`) — R13-Q-2
- เปลี่ยนข้อความ / layout ของ dialog Connection Error, tips, ปุ่ม Retry / Edit
- เปลี่ยนเกณฑ์ความยาวขั้นต่ำ 4 ตัวของ known secret, เปลี่ยนวิธีสร้าง connection string / URL
- กรณีขอบ (ก) / (จ) ของ 🟢2 (ถ้า R13-Q-1 ยืนยัน known limit)
- แก้ `docs/design.md` (หน้าที่ architect — ถ้าต้องการหมายเหตุ R12-5 ที่นั่นด้วย)
- refactor อื่น, commit

### R13-3. User stories

- **R13-US-1**: ในฐานะผู้ใช้ที่ Connect SQL Server ไม่ผ่าน ฉันต้องการเห็นสาเหตุจากฐานข้อมูลโดยไม่มีรหัสผ่านของฉันบนจอ ใน Execution Logs หรือในไฟล์ `logs/run_*.log` เพื่อส่ง log ให้ทีมอื่นได้อย่างปลอดภัย
- **R13-US-2**: ในฐานะผู้ใช้ที่กด "ทดสอบการเชื่อมต่อ" ตอนสร้าง Profile ฉันต้องการข้อความ error ที่ไม่มีรหัสผ่านเช่นกัน
- **R13-US-3**: ในฐานะผู้พัฒนา Round ถัดไป ฉันต้องการ test ที่ล็อกพฤติกรรม (retry delay, `write_json_atomic`) และ spec ที่ไม่ขัดกับของจริง เพื่อไม่แก้กลับโดยไม่รู้ตัว

### R13-4. Acceptance criteria

วิธีทดสอบ: `unittest` แบบ stub (`DatabaseConnectorGUI.__new__`, `_FakeEntry`, patch `create_engine` / `messagebox` / `ui_dialog` / `tk.Label` / `print` / `threading.Thread`) ไม่ต่อ DB จริง ไม่เปิด Tk จริง; ไฟล์ test ใหม่ทั้งหมดอยู่ใน `tests/test_r13_*.py`

นิยาม:
- `PW = "S3cr;t}PW-13"` (มี `;` และ `}` → ODBC เขียนเป็น `{S3cr;t}}PW-13}`)
- "error ที่มีรหัส" (แยก subTest): (1) ODBC ดิบ `... DRIVER={D};SERVER=h,1;UID={u};PWD={S3cr;t}}PW-13};Encrypt=yes ... Login failed for user 'u'.`; (2) `mssql+pyodbc:///?odbc_connect=` + `quote_plus(<ODBC ข้อ 1>)` + ` Login failed for user 'u'.`; (3) ข้อความอิสระที่มี `PW` ตรงตัว `bad password S3cr;t}PW-13 for u`
- "ไม่รั่ว" = ข้อความไม่มี `PW`, `quote_plus(PW)`, `S3cr`, `PW-13`, `}}PW-13`, `%7D%7DPW-13`
- "ไม่ mask เกิน" = ข้อความยังมี `Login failed for user 'u'` (หรือ `bad password` / `for u` ใน (3))

#### Connect (🟢3)

| AC | Given / When / Then |
|---|---|
| R13-AC-1 | **Given** ช่อง Password = `PW` และ `engine.connect()` raise "error ที่มีรหัส" แต่ละแบบ **When** `connect_database` **Then** ทุกข้อความที่ `results_text.insert` ได้รับ (Execution Logs และ run log ที่ป้อนจาก insert เดียวกัน `:3300-3308`) "ไม่รั่ว" และ "ไม่ mask เกิน"; ยังมีบรรทัดขึ้นต้น `❌ Connection Error: ` ตามเดิม; `print` ที่ถูกจับ (ถ้ามี) ไม่รั่ว |
| R13-AC-2 | **Given** เหมือน R13-AC-1 **When** dialog Connection Error ถูกสร้าง (patch `ui_dialog` ให้เรียก `build_body` กับ frame ปลอม และจับ `text` ของ `tk.Label`) **Then** argument `message`, `subtitle` และ `text` ของ Label ทุกตัว "ไม่รั่ว"; Label กล่องแดงยัง "ไม่ mask เกิน"; การตัด 400 ตัวอักษรทำ **หลัง** redact (ข้อความยาว > 400 ที่มี `PWD={...}` ช่วงท้าย ไม่เหลือส่วนของรหัส) |
| R13-AC-3 | **Given** `create_engine` / `get_connection_string` raise (ไม่ใช่ `engine.connect()`) ด้วย "error ที่มีรหัส" แบบ (1) **When** `connect_database` **Then** ผลเหมือน R13-AC-1 / R13-AC-2 และพฤติกรรมเดิมคงอยู่: `_replace_engine(None)`, `status_label` = `❌ Connection Failed`, `execute_btn` / `inspect_btn` disabled |
| R13-AC-4 | **Given** ช่อง Password ยาว < 4 ตัว (`"pw1"`) และ error แบบ (1) ที่ใช้รหัสนี้ **When** `connect_database` **Then** ไม่รั่ว (ผ่าน pattern) และคำทั่วไปที่มี `pw1` นอก `PWD=` ไม่ถูกแตะ — ยืนยันเกณฑ์ 4 ตัวเดิม |
| R13-AC-5 | **Given** การกด "ทดสอบการเชื่อมต่อ" ใน New Profile ด้วย Password = `PW` และ `create_engine` / `connect` raise "error ที่มีรหัส" แต่ละแบบ **When** สร้างข้อความผลลัพธ์ (logic ใน `work()` แยกเป็น helper ที่ทดสอบได้โดยไม่เปิด dialog — ชื่อกำหนดใน design) **Then** ข้อความ `✕  เชื่อมต่อไม่สำเร็จ: ...` "ไม่รั่ว"; redact ทำก่อนเลือกบรรทัดแรกและก่อนตัด 300 ตัวอักษร; กรณีสำเร็จข้อความ `✓  ทดสอบเชื่อมต่อสำเร็จ · ...` เหมือนเดิม |
| R13-AC-6 | **Given** error ปกติที่ไม่มีรหัส (`could not translate host name "x" to address`, `Login timeout expired`, ลิงก์ `https://sqlalche.me/e/20/e3q8`) **When** ผ่าน R13-AC-1 / R13-AC-5 **Then** ข้อความเท่ากับเดิมทุกตัวอักษร |

#### Tables (🟢1, 🟢4)

| AC | Given / When / Then |
|---|---|
| R13-AC-7 | **Given** `_run_target = RunTarget(engine, None)` (ทาง R11-AC-17 อ่านรหัสจากช่องกรอก) ช่อง Password = `PW`, ไม่มี `_connected_password` และ worker raise error แบบ (3) (รหัสตรงตัว ไม่มี `PWD=`) **When** `list_tables` จนถึง `on_list_tables_error` **Then** `results_text` และ `showerror` "ไม่รั่ว" — เพราะใช้ password ที่ worker ใช้ (`credentials[1]`) ไม่ใช่ `_connected_password` |
| R13-AC-8 | **Given** snapshot มี `info` + `_connected_password = (engine, PW)` แล้วก่อน `on_list_tables_error` ถูกเรียก `_connected_password` ถูกเปลี่ยนเป็นรหัสอื่น **When** error แบบ (3) ถึง `on_list_tables_error` **Then** ยัง "ไม่รั่ว" (ใช้รหัสของ worker); test เดิม `test_on_list_tables_error_is_redacted` ผ่านโดยไม่แก้ (ถ้า signature เปลี่ยน ต้องรองรับการเรียกแบบเดิมด้วย default) |
| R13-AC-9 | **Given** source ของ `database_connect_gui.py` **When** test อ่านทุกบรรทัดที่มี `redact_secrets(` **Then** ทุกบรรทัดยาว ≤ 95 ตัวอักษร (แนวที่ใช้ทั้งไฟล์); และ `inspect.getsource(app.redact_secrets)` ไม่มี `import`, `app.quote_plus` มีอยู่ระดับ module |

#### `redact_secrets` patterns (🟢2 — ตามค่าเริ่มต้น R13-Q-1)

| AC | Given / When / Then |
|---|---|
| R13-AC-10 | **When** `redact_secrets(text)` (ไม่ส่ง known secret) **Then** ผลตรงทุกตัวอักษร (subTest): (ข) `password = 'x y'` → `password = '***'`, `PWD="a;b"` → `PWD="***"`, quote ไม่ปิด `password='abc` → `password='***` ; (ค) `DB_PASSWORD=abc next` → `DB_PASSWORD=*** next`, `MY_PWD=abc;` → `MY_PWD=***;`; (ง) `http://host:8080/a@b` และ `see http://h:80/x?y=a@b` **ไม่เปลี่ยน**; ขณะที่ `postgresql://u:p%40ss@h/db` → `postgresql://u:***@h/db` ตามเดิม; และ test เดิม `RedactSecretsTests` ทั้งคลาสผ่านโดยไม่แก้ |
| R13-AC-12 | **Given** known limit (ก) / (จ) ตาม R13-Q-1 **When** `redact_secrets("postgresql://u:p@ss@h/db")` และ `redact_secrets("testing table test_x", "test")` **Then** ได้ `"postgresql://u:***@ss@h/db"` และ `"***ing table ***_x"` ตามลำดับ (พฤติกรรมปัจจุบัน) — pin ไว้เป็น known limit ให้เห็นถ้ามีคนเปลี่ยน; และ `redact_secrets("postgresql://u:p@ss@h/db", "p@ss")` ไม่มี `p@ss` (known secret ปิดให้) — ถ้าผู้ใช้เลือกแก้ (ก) / (จ) ใน R13-Q-1 ให้ปรับ AC นี้เป็นผลใหม่ |

#### Export / persistence / เอกสาร (🟢5, 🟢6, 🟢7, 🟢8, 🟢9)

| AC | Given / When / Then |
|---|---|
| R13-AC-11 | **Given** `docs/spec.md` **When** อ่านแถว R10-AC-15 และ R10-Q-3 **Then** ข้อความเดิมยังอยู่ครบ และมีหมายเหตุ "ถูกแทนที่โดย R12-5 (2026-11-23)" — **ทำแล้วโดย PM ใน Round นี้**; ตรวจด้วย review (ไม่ต้องมี unittest) |
| R13-AC-13 | **Given** โมดูล `app` (ไม่ patch) **When** test อ่าน `app.EXPORT_REPLACE_RETRY_DELAYS` **Then** `== (0.2, 0.5, 1.0)` และ `sum(...) <= 2.0` |
| R13-AC-14 | **Given** ไฟล์ JSON เดิมที่มีเนื้อหา X ใน temp dir **When** `write_json_atomic` ล้มแต่ละแบบ (subTest): (ก) `json.dump` raise `TypeError` (ข้อมูล serialize ไม่ได้), (ข) patch `os.fsync` raise `OSError`, (ค) patch `os.fsync` (หรือ `json.dump`) raise `KeyboardInterrupt` **Then** exception ชนิดเดิมหลุดออกมา (instance เดียวกัน), bytes ของไฟล์เดิม = X, ไม่มี `<path>.tmp` ค้าง และ `os.replace` ไม่ถูกเรียก |
| R13-AC-15 | **Given** `tests/test_r8_load_jobs_writeback.py:305` **When** แก้ **เฉพาะ comment** ให้ตรงความจริง (เช่น `print() returns silently when sys.stdout is None`) **Then** ไม่มีการแก้บรรทัดอื่นในไฟล์นั้น (ตรวจด้วย `git diff` ใน review) และ test ผ่าน |
| R13-AC-16 | **Given** `saved_jobs = [job_P1_a, None, "junk", job_P2_b]` (profile ปัจจุบัน = P1) และ preset ที่ valid 1 job **When** Load Preset แล้วกด Yes (`save_jobs` สำเร็จ) **Then** ไม่มี exception / rollback / `showerror`; `askyesno` นับ 1 job; ผล `saved_jobs` = ตาม R13-Q-3 (ค่าเริ่มต้น: `[None, "junk", job_P2_b, <job จาก preset>]` — element เสียถูก**เก็บไว้**ตามลำดับเดิม, `job_P1_a` ถูกแทน) |

#### Regression

| AC | Given / When / Then |
|---|---|
| R13-AC-17 | **Given** แก้ครบ **When** รัน `python -m unittest discover -s tests -p "test_*.py"` สองแบบ ((ก) `PYTHONIOENCODING=utf-8`, (ข) ไม่ตั้ง บน `cp874` + redirect stdout/stderr ไปไฟล์) **Then** ทั้งสองแบบ `OK` จำนวน test เท่ากัน และ ≥ 1147 + จำนวน test ใหม่ของ `tests/test_r13_*.py`; test เดิมทุกไฟล์ไม่ถูกแก้ ยกเว้น comment ตาม R13-AC-15 |
| R13-AC-18 | **Given** test ใหม่ทั้งหมด **When** รัน **Then** ไม่มี password จริง / รหัสทดสอบปรากฏใน stdout / stderr ของการรัน test, ใน `logs/` หรือไฟล์ใดนอก temp dir ของ test; `ConnectionInfo` / `RunTarget` ยังไม่มี field password (`tests/test_run_target.py` ผ่าน) |

**สรุปจำนวน AC Round 13**: 18 ข้อ (Connect 6, Tables 3, patterns 2, export / persistence / เอกสาร 5 — R13-AC-11 ตรวจด้วย review, regression 2)

### R13-5. ข้อจำกัด / สมมติฐาน

- ยังไม่มีหลักฐานว่า driver ใส่ `PWD=` ใน error ของการ Connect จริง — เป็นการปิดความเสี่ยงล่วงหน้าแบบเดียวกับ R12-7; ทดสอบด้วยข้อความจำลองเท่านั้น
- Known secret ของ Connect / Test connection = ค่าที่อ่านจากช่อง Password ตอนกด (ค่าที่ใช้สร้าง connection นั้น); รหัส < 4 ตัวพึ่ง pattern อย่างเดียว (เกณฑ์เดิม)
- run log ได้ข้อความจาก `results_text.insert` ที่ถูกห่อ — redact ก่อน insert จึงครอบ run log ด้วย; dialog / `print` ต้อง redact แยก
- Minimal diff: แก้ `_SECRET_PATTERNS` / `redact_secrets`, except ของ `connect_database`, `_show_connection_error` (หรือผู้เรียกส่งข้อความที่ redact แล้ว), `test_connection` (แยก helper), `list_tables` (บรรทัด print + ส่ง password ให้ error handler), `on_list_tables_error`, filter `load_preset_dialog`; PEP 8 + type hints สำหรับ helper ใหม่
- ห้าม commit

### R13-6. คำถามที่ยังไม่มีคำตอบ

AC ใช้คำตอบที่แนะนำเป็นค่าเริ่มต้น ถ้าผู้ใช้ต้องการแบบอื่นให้แจ้งก่อนเริ่ม design

| # | คำถาม | คำตอบที่แนะนำ (default) |
|---|---|---|
| R13-Q-1 | กรณีขอบ 🟢2 แก้ข้อไหน: (ก) URL ไม่ encode ที่รหัสมีช่องว่าง / `'` / `"` / `@`, (ข) `password = 'x'` → `***'x'`, (ค) `DB_PASSWORD=` ไม่ถูก mask, (ง) URL ที่ไม่ใช่ userinfo ถูก mask เกิน (`http://host:8080/a@b`), (จ) known secret ที่เป็นคำทั่วไป (`test`) mask คำอื่นด้วย | **แก้ (ข) (ค) (ง)** — เปลี่ยน regex เล็กน้อย ไม่ลดการป้องกันข้อความที่แอปสร้าง (แอป `quote_plus` รหัสใน URL → ไม่มี `/` ดิบ จึงตัด `/` ออกจาก userinfo ได้). **known limit (ก) (จ)** — (ก) แอปไม่สร้าง URL แบบนี้และ known secret ≥ 4 ตัวปิดให้; (จ) mask เกินคือฝั่งปลอดภัย การจำกัดเป็น whole-word จะพลาด `PWD%3Dtest%3B` (`D` ติดหน้า) — R13-AC-12 pin พฤติกรรมไว้ |
| R13-Q-2 | ขยายการ redact ไปยัง error ของการ**รัน** (Run / Run Job / Run All / Export / Error & Debug tab / debug print) ด้วยหรือไม่ — connection ที่หลุดแล้ว reconnect (`pool_pre_ping`) อาจได้ error แบบเดียวกัน | **ไม่รวมใน Round นี้** — review 🟢3 ระบุเฉพาะ Connect, ผู้ใช้ต้องการด่วนก่อน PR; ถ้าต้องการให้เปิด Round แยก |
| R13-Q-3 | 🟢9 element ที่ไม่ใช่ dict ใน `saved_jobs` ตอน Load Preset (กด Yes): เก็บไว้ หรือทิ้ง | **เก็บไว้** — ไม่ใช่ Job ของ Profile ปัจจุบัน (สอดคล้องกับตัวนับที่ไม่นับมัน), ไม่ทำลายข้อมูลที่ไม่เข้าใจ; ในทางปฏิบัติไม่เกิดเพราะ `load_jobs` reject ตั้งแต่โหลด (R13-AC-16) |

คำตอบผู้ใช้ (2026-11-23): **R13-Q-1** แก้ (ข) (ค) (ง); ยอมรับ (ก) URL ไม่ encode ที่มี `@` และ (จ) known secret ที่เป็นคำทั่วไป เป็น known limit (R13-AC-12 คงตามเดิม) · **R13-Q-2** ไม่ redact error ตอนรัน (Run / Run Job / Run All / Export / Error & Debug / reconnect) ใน Round นี้ · **R13-Q-3** element ที่ไม่ใช่ dict ใน `saved_jobs` ตอน Load Preset → เก็บไว้ในลำดับเดิม (R13-AC-16 คงตามเดิม)

---

# Round 14 — ซ่อนรหัสผ่านใน error ตอนรัน (ต่อจาก R13-Q-2)

> ใช้เลข `R14-AC-x` / `R14-Q-x` แยกจาก Round ก่อนหน้า ไม่แก้เนื้อหา Round ก่อนหน้า
> ที่มา: ผู้ใช้สั่งทำข้อที่ R13-Q-2 ตัดออก (ด่วน)
> เลขบรรทัด `database_connect_gui.py` ณ 2026-11-23 (commit `00ef40b`) อาจคลาดเล็กน้อย

### R14-1. เป้าหมาย / ปัญหา

Round 13 redact เฉพาะ error ของ Connect / Test connection / Tables แต่ error ของ DB driver ตอน**รัน** (Run, Run Job, Run all, Export Excel) ยังออกไปดิบ ๆ ทั้ง `str(e)` และ `traceback.format_exc()` ไปยัง Execution Logs (→ `logs/run_*.log` ผ่าน `_insert_and_log` `:3316-3324`), messagebox, popup, dialog Error Details + clipboard, แท็บ Error & Debug, console (`print`) และ cell `Error` ในไฟล์ Excel. ถ้า driver / SQLAlchemy ใส่ connection string ไว้ใน error (เช่นตอน `pool_pre_ping` reconnect ใน `engine.raw_connection()` / `engine.connect()` ระหว่างรัน) รหัสผ่านจะหลุดไปทุกที่ที่กล่าวมา

ผู้ได้ประโยชน์: ผู้ใช้ที่ส่ง log / ไฟล์ Excel / screenshot ให้คนอื่น, ผู้ดูแลความปลอดภัย

### R14-2. เส้นทางที่พบ (ค้นด้วย `str(e)`, `str(error)`, `format_exc`, `print_exc`, `print(... {e})`)

| # | เส้นทาง | ฟังก์ชัน / บรรทัด | ปลายทาง |
|---|---|---|---|
| P1 | Run — worker except | `_execute_query_background.execute_in_background` `:6999-7027` (`message` `:7002`, `traceback` `:7003`, `self.last_error_details` `:7022`) | ต้นทางของ P2-P5 |
| P2 | Run — debug print | `:7013-7019` (`Error Message`, `Full Traceback`) เมื่อ Debug mode | console |
| P3 | Run — แสดงผล error | `on_query_error_enhanced` `:7112-7119` (`Error Message`, `Debug Traceback`) | Execution Logs + run log |
| P4 | Run — Show Details | `_show_error_details_dialog` Label `:7172`, traceback `:7219`, `copy_error` `:7226-7233` | dialog, clipboard |
| P5 | แท็บ Error & Debug | `_build_error_debug_tab._poll_last_error` `:9052-9060` (อ่าน `last_error_details`) | แท็บ |
| P6 | Run — dialog ถูกปิดก่อนจบ / ผู้เรียกเดิม | `on_query_error` `:8726`, `:8732` (เรียกจาก `:7041`) | Execution Logs + run log, `messagebox.showerror` |
| P7 | Run Job | `run_job.run_in_background` except `:10111-10113` → `finish` → `update_job_status(status="error")` `:10386` (`Error       : {error}`), popup `pd.DataFrame({"Error": [str(error)]})` `:10393` | Execution Logs + run log, popup ผลลัพธ์ (ซึ่ง export CSV/Excel ต่อได้) |
| P8 | Run all — ต่อ Job | `run_selected_job.run_all_jobs` except `:10279-10305` → `update_job_status(..., show_popup=False)` `:10301` | Execution Logs + run log |
| P9 | Run all — ทั้งชุดล้ม | except `:10321-10322` → `show_batch_error` `:11087` | Execution Logs + run log |
| P10 | Export — Job ล้ม | `export_jobs_to_excel.worker` except `:11020-11040`: `log("Error : ...")` `:11028`, `log(traceback.format_exc())` `:11029`, cell `Error` `:11035` (ผ่าน `blank_oversized_cells`) | Execution Logs + run log, ไฟล์ Excel |
| P11 | Export — fatal | `:11063-11064` → `on_done` `:10641`, `:10643` | Execution Logs + run log, `messagebox.showerror` |
| P12 | Stop — cancel ล้ม | `stop_running_queries` `:8394-8395` `print(f"Stop: cancel failed: {e}")` (error ของ driver) | console |

ตรวจแล้ว**ไม่ใช่เส้นทาง**: `show_batch_summary` (แสดงแค่ชื่อ Job ที่ล้ม), `job_results["_error"]` (ใช้ตรวจ `is None` เท่านั้น), `show_critical_error` `:11098` (ไม่มีผู้เรียก), `run_selected_job` `error_msg` `:10281` (ไม่ถูกใช้), `print("Error in error handler")` + `traceback.print_exc()` `:7124-7125` และ `Failed to append SQL` `:10962` (error ของ Tk / openpyxl ไม่ใช่ DB), debug print `Engine:` `:6965` (แสดงแค่ชื่อ dialect อยู่แล้ว)

### R14-3. ขอบเขต

#### In scope
- P1-P12: ข้อความ error และ traceback ผ่าน `redact_secrets(<text>, <password ของ engine ที่รัน>)` **ที่ต้นทาง** (ก่อนเก็บลง `last_error_details` / ส่งให้ main thread / `log` / เขียน cell / ตัดความยาว / ตรวจ 32,767) — ปลายทางทั้งหมดจึงได้ข้อความเดียวกันที่ redact แล้ว
- password = `_connected_password_for(target.engine)` อ่านครั้งเดียวบน main thread ตอนเริ่มรัน (snapshot เดียวกับ engine ของการรันนั้น) แล้วส่งให้ worker — **ไม่อ่านช่อง Password** และไม่อ่าน `_connected_password` ซ้ำใน worker
- P12 ใช้ `_connected_password_for(self.engine)` + pattern
- `on_query_error` (P6) redact ซ้ำด้วย pattern + `_connected_password_for(self.engine)` เพื่อคุมผู้เรียกที่ส่ง exception ดิบ (redact ซ้ำบนข้อความที่ redact แล้วไม่เปลี่ยนผล)

#### Out of scope
- redact ข้อความ SQL ของผู้ใช้เอง (cell `Query`, กล่อง Failed Query, ส่วน `QUERY` ในแท็บ Error & Debug, `print("Query: ...")`, `SQL:` / `SQL         :` ใน Execution Logs / run log) — ตาม R14-Q-1
- เปลี่ยน `_SECRET_PATTERNS` / เกณฑ์ 4 ตัว / known limit (ก) (จ) ของ R13-Q-1
- เปลี่ยนรูปแบบข้อความ, layout dialog, ตัวนับ, ลำดับการทำงาน; เส้นทางที่ระบุว่า "ไม่ใช่เส้นทาง" ใน R14-2
- error ของ Connect / Test connection / Tables (ทำแล้วใน R12 / R13), commit

### R14-4. User stories
- **R14-US-1**: ในฐานะผู้ใช้ที่รัน query / Job แล้วล้ม ฉันต้องการเห็นสาเหตุจากฐานข้อมูลโดยไม่มีรหัสผ่านบนจอ ใน log ใน console หรือในไฟล์ Excel เพื่อส่งต่อให้ทีมอื่นได้อย่างปลอดภัย
- **R14-US-2**: ในฐานะผู้ใช้ที่ไม่มี error เกี่ยวกับรหัส ฉันต้องการให้ข้อความ error และผลรันเหมือนเดิมทุกตัวอักษร

### R14-5. Acceptance criteria

วิธีทดสอบ: `unittest` แบบ stub เหมือน Round 13 (`DatabaseConnectorGUI.__new__`, patch `threading.Thread` ให้รัน target ทันที, `root.after` เรียกทันที, patch `messagebox` / `print` / `tk.Label` / `tk.Text` / `tk.Toplevel`, `read_sql_dataframe` / `_execute_modification` raise) ไม่ต่อ DB จริง ไม่เปิด Tk จริง; Export เขียนไฟล์จริงใน temp dir แล้วอ่านด้วย `openpyxl`; ไฟล์ test ใหม่อยู่ใน `tests/test_r14_*.py`

นิยาม:
- `PW = "S3cr;t}PW-14"`; engine ของการรัน `E` และ `_connected_password = (E, PW)`; ช่อง Password = `"field-pw-x"` (ต่างจาก `PW`)
- "error ที่มีรหัส" (subTest): (1) ODBC ดิบ `... PWD={S3cr;t}}PW-14};Encrypt=yes ... Login failed for user 'u'.`; (2) `odbc_connect=` + `quote_plus(<ODBC ข้อ 1>)` + ` Login failed for user 'u'.`; (3) `bad password S3cr;t}PW-14 for u` (รหัสตรงตัว ไม่มี `PWD=`)
- "ไม่รั่ว" = ไม่มี `PW`, `quote_plus(PW)`, `S3cr`, `PW-14`, `}}PW-14`, `%7D%7DPW-14`; "ไม่ mask เกิน" = ยังมี `Login failed for user 'u'` (หรือ `bad password` / `for u`)
- "traceback" = `traceback.format_exc()` ของ exception ที่มีรหัส (ข้อความ exception อยู่ท้าย traceback)

#### Run (P1-P6)

| AC | Given / When / Then |
|---|---|
| R14-AC-1 | **Given** `execute_query` บน `E`, query raise "error ที่มีรหัส" **When** worker จบ **Then** `last_error_details["message"]` และ `["traceback"]` "ไม่รั่ว"; `message` "ไม่ mask เกิน"; `["type"]` = ชื่อ class เดิม; `["query"]` = SQL เดิม |
| R14-AC-2 | **Given** R14-AC-1 และ Debug mode เปิด **When** worker จบ **Then** ทุก `print` ที่จับได้ "ไม่รั่ว" (บรรทัด `Error Message:` และ `Full Traceback:`) |
| R14-AC-3 | **Given** R14-AC-1 (Debug mode เปิดและปิด) **When** `on_query_error_enhanced` **Then** ทุกข้อความที่ `results_text.insert` ได้รับ (รวม `Debug Traceback`) และสิ่งที่ `_write_run_log` ได้รับ "ไม่รั่ว"; บรรทัด `Error Message: ` ยังอยู่ |
| R14-AC-4 | **Given** `error_details` จาก R14-AC-1 **When** `_show_error_details_dialog` และกด `copy_error` **Then** `text` ของ Label, ข้อความที่ใส่ใน traceback Text และ `clipboard_append` "ไม่รั่ว" |
| R14-AC-5 | **Given** `last_error_details` จาก R14-AC-1 **When** `_poll_last_error` ของแท็บ Error & Debug ทำงาน **Then** ข้อความที่ insert ลง `debug_text` "ไม่รั่ว" (ส่วน type: message และ TRACEBACK) |
| R14-AC-6 | **Given** loading dialog ถูกปิดก่อน error มาถึง (`winfo_exists` → False) และกรณีเรียก `on_query_error(<exception ดิบ>, dialog)` ตรง ๆ โดย `self.engine = E` **When** `on_query_error` **Then** `results_text.insert` และ `messagebox.showerror` "ไม่รั่ว" |

#### Run Job / Run all (P7-P9)

| AC | Given / When / Then |
|---|---|
| R14-AC-7 | **Given** `run_job` บน `E`, query raise "error ที่มีรหัส" **When** จบ **Then** บรรทัด `Error       : ...` ใน Execution Logs / run log และ cell `Error` ของ DataFrame ที่ส่งให้ `show_table_popup` "ไม่รั่ว" และ "ไม่ mask เกิน"; `Status      : Fail`, `_finish_job_result_report(1, 0, 1)` เหมือนเดิม |
| R14-AC-8 | **Given** Run all 3 Job (SELECT ผ่าน, SELECT ล้มด้วย "error ที่มีรหัส", SELECT ผ่าน) **When** จบ **Then** Execution Logs / run log "ไม่รั่ว"; ตัวนับ Total / Success / Fail = 3 / 2 / 1 เหมือนเดิม; และกรณี Job modify ล้มยังหยุด loop ตามเดิม |
| R14-AC-9 | **Given** Run all ที่ loop ภายนอก raise "error ที่มีรหัส" (เช่น `update_job_status` scheduling ล้ม) **When** `show_batch_error` **Then** Execution Logs / run log "ไม่รั่ว" และปุ่มกลับมา normal เหมือนเดิม |

#### Export Excel (P10-P11)

| AC | Given / When / Then |
|---|---|
| R14-AC-10 | **Given** Export 2 Job บน `E` (Job A ผ่าน, Job B raise "error ที่มีรหัส") **When** export จบ **Then** ใน Excel sheet ของ B: `Status` = `Failed`, cell `Error` "ไม่รั่ว" และ "ไม่ mask เกิน", cell `Query` = SQL เดิมทุกตัวอักษร; บรรทัด `Error : ` และ traceback ใน Execution Logs / run log "ไม่รั่ว"; summary `Success: 1`, `Failed: 1`, `Warning: 0` เหมือนเดิม |
| R14-AC-11 | **Given** Job ล้มด้วยข้อความ error ที่ (ก) ยาวดิบ > 32,767 แต่หลัง redact ≤ 32,767 (มี `PW` ซ้ำหลายครั้ง) และ (ข) ยาวดิบ ≤ 32,767 แต่หลัง redact > 32,767 (`PWD=` ว่างหลายครั้ง → `PWD=***`) **When** export **Then** (ก) cell `Error` = ข้อความที่ redact แล้ว ไม่มี Warning ของคอลัมน์ `Error`; (ข) cell `Error` ว่าง + log Warning `column 'Error' is over Excel's 32,767-character limit` ตามเดิม — ยืนยันว่า redact **ก่อน** ตรวจความยาว |
| R14-AC-12 | **Given** worker export raise "error ที่มีรหัส" นอก loop ของ Job (fatal, เช่น patch `_ensure_export_target_writable`) **When** `on_done` **Then** `Error: ...` ใน Execution Logs / run log และ `messagebox.showerror` "ไม่รั่ว"; ข้อความขึ้นต้น `<ชื่อ class>: ` ตามเดิม |

#### แหล่งของรหัส / อื่น ๆ

| AC | Given / When / Then |
|---|---|
| R14-AC-13 | **Given** Run / Run Job / Run all / Export เริ่มบน `E` แล้ว**ระหว่างรัน** `_connected_password` ถูกเปลี่ยนเป็น `(E2, "Other-PW-99")` และ `self.engine = E2` (reconnect) **When** error แบบ (3) ของ `E` มาถึง **Then** ทุกปลายทางของเส้นทางนั้น "ไม่รั่ว" (ใช้รหัส snapshot ตอนเริ่ม); ช่อง Password ไม่ถูกอ่านใน worker (`_FakeEntry.get` ไม่ถูกเรียกหลังเริ่มรัน) |
| R14-AC-14 | **Given** engine ที่ไม่ได้มาจาก Connect (`_connected_password_for(E) is None`) **When** error แบบ (1) / (2) **Then** "ไม่รั่ว" (ผ่าน pattern); แบบ (3) ไม่ถูกแก้ (known limit — ตาม R14-Q-3) |
| R14-AC-15 | **Given** `self.engine = E`, connection ปลอมที่ `cancel()` raise "error ที่มีรหัส" **When** `stop_running_queries` **Then** `print` ที่จับได้ "ไม่รั่ว" และยังขึ้นต้น `Stop: cancel failed: ` |

#### ข้อกำหนดเดิมที่ต้องคง

| AC | Given / When / Then |
|---|---|
| R14-AC-16 | **Given** error ที่ไม่มีรหัส (`ORA-00942: table or view does not exist`, `could not translate host name "x" to address`, ข้อความ SQLAlchemy ที่มี `[SQL: SELECT 1]` และลิงก์ `https://sqlalche.me/e/20/f405`) **When** ผ่าน P1-P12 **Then** ทุกปลายทาง (Execution Logs, run log, messagebox, popup, dialog, clipboard, Error & Debug, print, cell `Error` ใน Excel) เท่ากับพฤติกรรมเดิมทุกตัวอักษร และตัวนับ Success / Failed / Warning เท่าเดิม |
| R14-AC-17 | **Given** test ใหม่ทั้งหมด **When** รัน **Then** ไม่มี `PW` / ชิ้นส่วนรหัสใน stdout / stderr, ใน `logs/` หรือไฟล์ใดนอก temp dir; `last_error_details`, `job_results`, `RunTarget`, `ConnectionInfo` ไม่มี field password (`tests/test_run_target.py` ผ่าน); ทุกบรรทัดที่มี `redact_secrets(` ยังยาว ≤ 95 (test R13-AC-9 เดิมผ่าน) |
| R14-AC-18 | **Given** แก้ครบ **When** รัน `python -m unittest discover -s tests -p "test_*.py"` สองแบบ ((ก) `PYTHONIOENCODING=utf-8`, (ข) ไม่ตั้ง บน `cp874` + redirect stdout/stderr ไปไฟล์) **Then** ทั้งสองแบบ `OK` จำนวน test เท่ากัน และ ≥ 1182 + จำนวน test ใหม่ใน `tests/test_r14_*.py`; test เดิมไม่ถูกแก้ |

**สรุปจำนวน AC Round 14**: 18 ข้อ (Run 6, Run Job / Run all 3, Export 3, แหล่งรหัส / อื่น ๆ 3, ข้อกำหนดเดิม 3)

### R14-6. ข้อจำกัด / สมมติฐาน
- ยังไม่มีหลักฐานว่า driver ใส่รหัสใน error ตอนรันจริง — ปิดความเสี่ยงล่วงหน้า ทดสอบด้วยข้อความจำลองเท่านั้น
- error ของ SQLAlchemy มี `[SQL: ...]` อยู่ในข้อความ error — เมื่อ redact ทั้งข้อความ error ส่วน SQL **ภายในข้อความ error** ที่ตรง pattern (`password='x'`) จะถูก mask ด้วย (ฝั่งปลอดภัย) ขณะที่ช่อง SQL แยก (cell `Query` ฯลฯ) ไม่ถูกแตะตาม R14-Q-1
- run log ได้ข้อความจาก `results_text.insert` ที่ถูกห่อ → redact ก่อน insert ครอบ run log; `print` / messagebox / Excel / clipboard ได้ข้อความเดียวกันที่ redact ที่ต้นทาง
- รหัสอยู่ใน memory เท่านั้น ไม่ถูกเก็บใน `error_details` / `job_results` / log (ส่งผ่านเป็น argument / closure ของ worker)
- Minimal diff: แก้เฉพาะจุด P1-P12 + การส่งรหัสจาก main thread ให้ worker; PEP 8, บรรทัด `redact_secrets(` ≤ 95; ห้าม commit

### R14-7. คำถามที่ยังไม่มีคำตอบ

AC เขียนตามคำตอบที่แนะนำ ถ้าผู้ใช้ต้องการแบบอื่นให้แจ้งก่อนเริ่ม design

| # | คำถาม | คำตอบที่แนะนำ (default) |
|---|---|---|
| R14-Q-1 | redact ข้อความ SQL ของผู้ใช้เอง (cell `Query` ใน Excel, กล่อง Failed Query, ส่วน QUERY ในแท็บ Error & Debug, `print("Query: ...")`, `SQL:` ใน Execution Logs / run log) ที่อาจมี `password=` หรือไม่ | **ไม่ redact** — เป็นข้อความที่ผู้ใช้เขียนเอง ไม่ใช่รหัสของ connection; การ redact จะทำให้ SQL ใน Excel / log ไม่ตรงกับที่รันจริงและกระทบ SQL ปกติ (เช่น `WHERE password = 'x'` ในตาราง user) — R14-AC-1 / R14-AC-10 ตรวจว่า SQL คงเดิม |
| R14-Q-2 | traceback เต็ม (แท็บ Error & Debug, Show Details, Copy, `Debug Traceback` ใน Execution Logs, log ของ Export, debug print) redact แค่ไหน | **redact ทั้งข้อความ traceback ด้วย `redact_secrets` (pattern + รหัสที่รู้ค่า) แต่คง traceback ไว้ครบ** ไม่ตัด / ไม่ซ่อนทั้งก้อน — ยังใช้ debug ได้; ข้อเสียคือบรรทัด source ของ library ที่ตรง pattern (เช่น `url.password = x`) อาจถูก mask บางส่วน (ฝั่งปลอดภัย) |
| R14-Q-3 | engine ที่ไม่มีรหัสเก็บไว้ (`_connected_password_for` → `None`) ควร fallback ใช้ค่าในช่อง Password หรือไม่ | **ไม่ fallback — ใช้ pattern อย่างเดียว** ตามหลัก "รหัสของ engine ที่รันอยู่ ไม่ใช่ช่องกรอก" (ช่องกรอกอาจถูกแก้แล้วไม่ใช่รหัสของ engine); ในการใช้งานจริง engine มาจาก `connect_database` เสมอจึงมีรหัสเก็บไว้ — R14-AC-14 pin ไว้ |

คำตอบผู้ใช้ (2026-11-23): **R14-Q-1** ไม่ redact SQL ที่ผู้ใช้เขียนเอง (cell `Query`, Failed Query, QUERY ในแท็บ Error & Debug, `SQL:` ใน log) · **R14-Q-2** redact ทั้งข้อความด้วย `redact_secrets` แต่คง traceback ไว้ครบ · **R14-Q-3** engine ที่ไม่มีรหัสเก็บไว้ใช้ pattern อย่างเดียว ไม่อ่านช่อง Password (R14-AC-1..18 คงตามเดิม)
