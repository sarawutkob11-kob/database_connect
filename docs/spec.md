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
