# Code Review — 2026-11-12

> ขอบเขต: Bugfix C1 / C2 / H1 / H2 (T1-T15) ใน `database_connect_gui.py`, `README.md` (หัวข้อ SQL Editor บรรทัด 47 / 51 / 52) และ test ใหม่ใน `tests/` (13 ไฟล์ + `addCleanup(dispose)` ใน `test_database_connect_gui_core.py`)
> อ้างอิง: `docs/spec.md` (AC-1 ถึง AC-38), `docs/design.md`, `docs/tasks.md`
> ผลรัน test: `python -m unittest discover -s tests -p "test_*.py"`: `Ran 325 tests ... OK`
> หมายเหตุ: `git diff` รวมการแก้ที่ยังไม่ commit จากรอบก่อนไว้ด้วย รีวิวนี้ดูเฉพาะงานรอบนี้ ข้อที่มาจากการแก้รอบก่อนแยกไว้ในหัวข้อท้ายไฟล์

## สรุป
**ผ่าน** (ไม่มีปัญหาระดับ Critical): 🔴 0, 🟠 1, 🟡 4, 💡 6 (และนอกรอบนี้: 🟠 1, 💡 1)

สิ่งที่ตรวจแล้วและถูกต้อง:
- **Worker ไม่อ่าน `self.engine` แล้ว**: ทุกจุดที่เหลือซึ่งอ่าน `self.engine` (`grep self\.engine`) อยู่บน main thread ทั้งหมด ได้แก่เช็ค "connected" ใน entry point, `_capture_run_target`, `show_batch_summary` / `_reuse_last_run_results` และ `_reset_profile_connection_state` ส่วน worker 4 ตัวใช้ engine ที่จับไว้ คือ `execute_in_background` (6296, 6308), `run_in_background` (9206, 9209), `run_all_jobs` (9317, 9351), `worker` ของ Export (9840) และ `fetch_tables_in_background` (8567, 8623, 8739)
- **ทุก entry point มี guard เป็นบรรทัดแรก** ตาม design ข้อ 3 (11 จุด) รวม wrapper `_ui_run_selected_job` (2853) และ `run_group` (4615-4623) ที่ไม่มี popup แล้ว ทางเข้าอ้อมก็ถูกบล็อกด้วย: Retry ของ Connection Error (7210 ไปที่ `connect_database`), Retry ใน Loading (6384 ไปที่ `execute_query`) และ Ctrl+Enter
- **target ตัวเดียวกัน** ถูกส่งไปที่หน้ายืนยัน, `_start_stoppable_run` / Run log และ worker ในทุกงาน และจับครั้งเดียว (มี test ยืนยัน)
- **รหัสผ่านไม่หลุด**: `ConnectionInfo` ไม่มี field รหัสผ่าน / URL, debug print ใช้ `engine.dialect.name` (6287), รูปแบบหน้ายืนยันและ Run log ตรงกับโค้ดเดิมที่ HEAD ทุกตัวอักษร
- **Backward compatible**: `engine=None` คืนไปใช้ `self.engine`, `target=None` คืนไปใช้ `_capture_run_target()`, `ExecuteModificationTests` เดิมยังผ่าน
- **Test มี assert จริง**: test ที่ไม่มี `assert` ในตัวเมธอดทั้ง 6 ตัวเรียก helper ที่ assert ให้ (`_run_blocked`, `_check`) test ของ C1 ใช้ SQLite 2 ไฟล์และสลับ engine ระหว่างรันจริง ไม่ได้ mock ทิ้ง

## 🔴 Critical (ต้องแก้ก่อน merge)
- ไม่มี

## 🟠 Major (ควรแก้ก่อน merge)
- [database_connect_gui.py:4036, 4043-4050] `_backup_script_groups_once` นับไฟล์ที่ **อ่านไม่ได้ชั่วคราว** (`PermissionError` / `OSError` เช่น OneDrive ล็อกไฟล์) เป็น "ไฟล์เสีย ไม่ต้อง backup" เพราะ `_is_readable_json` กลืน exception ทุกชนิดแล้วคืน False ผลคือ `_script_groups_backup_done = True` ทันที
  - สถานการณ์: บันทึกครั้งแรกของเซสชันตอนที่ OneDrive ล็อก `script_groups.json` จะไม่มี backup และ flag ถูกตั้งเป็น "เสร็จ" แล้ว ถ้า `os.replace` ล้มเหลวด้วย ผู้ใช้จะเห็น error แต่บันทึกครั้งถัดไป (หลังปลดล็อก) จะเขียนทับเลยโดย **ไม่ backup เวอร์ชันก่อนเซสชัน** ซึ่งขัดกับเจตนาของ Q4 และหมายเหตุใน T4 ที่ว่า "backup ไม่สำเร็จต้องลองใหม่ครั้งหน้า" และ US-3 ก็ยกกรณี OneDrive ล็อกไฟล์ขึ้นมาเองโดยตรง
  - แนวทางแก้: แยกสองกรณี ถ้า `json.load` เจอ `ValueError` / `UnicodeDecodeError` ให้นับเป็นไฟล์เสียแล้วข้าม backup ส่วน `OSError` ให้ raise ต่อไป (การบันทึกครั้งนั้นถูกปฏิเสธ flag ยังเป็น False และครั้งถัดไปลองใหม่ เหมือนกรณี `copy2` ล้มเหลว) แล้วเพิ่ม test ที่ patch `open` ให้ raise `PermissionError`

## 🟡 Warning (ควรแก้)
- [database_connect_gui.py:9667 จนถึง 9697-9712, 3049 จนถึง 3052] **TOCTOU ระหว่าง guard กับจุดที่ตั้งสถานะ busy** `export_jobs_to_excel` เช็ค `_block_if_busy` ก่อนเปิด `filedialog.asksaveasfilename` และ dialog "ใช้ผลเดิม?" แต่ตั้ง "Exporting" (ซึ่งทำให้ busy) หลังจากนั้น บน Windows file dialog แบบ native ปิดเฉพาะหน้าต่าง owner (root) แต่หน้าต่าง Script Groups (`transient` ไม่ grab) อาจยังกดได้
  - สถานการณ์: กด Export ในหน้าหลัก แล้วระหว่างที่หน้าต่างเลือกไฟล์เปิดอยู่ไปกด ▶ Run Group ในหน้าต่าง Script Groups ผลคือ Run Group เริ่มรัน จากนั้นเลือกไฟล์ แล้ว Export ก็เริ่มซ้อน (ผิด Q1) และ `_start_stoppable_run` ของ Export จะ `clear()` Stop ที่ผู้ใช้กดให้ Run Group ไปแล้ว ส่วน engine ยังเป็นตัวเดียวกัน (Connect ถูกปิดอยู่) จึงไม่เกิดปัญหารันผิดฐานข้อมูล กรณีเดียวกันเกิดได้กับ `import_profiles_dialog` (guard อยู่ก่อน `askopenfilename`)
  - แนวทางแก้: เช็ค `self._block_if_busy(...)` ซ้ำอีกครั้งหลัง dialog ทุกตัว ก่อน `_start_stoppable_run` (Export: ก่อน 9712, Import: หลังเลือกไฟล์) ใช้โค้ด 2 บรรทัด ไม่ต้องเปลี่ยน design
- [README.md:137] ยังเขียนว่า "ทุกครั้งที่บันทึก จะเก็บเวอร์ชันก่อนหน้าไว้ที่ `script_groups_backup.json`" แต่ T4 เปลี่ยนเป็น backup **เฉพาะการบันทึกครั้งแรกของแต่ละเซสชัน และเฉพาะเมื่อไฟล์เดิมเป็น JSON ที่อ่านได้** ผู้ใช้ที่หวังกู้เวอร์ชันก่อนการบันทึกล่าสุดจะได้เวอร์ชันตอนเปิดแอปแทน แนวทางแก้: แก้บรรทัด 137 (และคำอธิบายที่ 192) ให้ตรงกับพฤติกรรมจริง พร้อมบอกว่าถ้าอ่านไฟล์ไม่ได้ตอนเปิดแอปจะมีสำเนา `script_groups_unreadable_<เวลา>.json`
- [.gitignore / database_connect_gui.py:81-96, 4000] รอบนี้ทำให้ Script Groups สร้างไฟล์ `script_groups_unreadable_<เวลา>.json` เพิ่มขึ้นในโฟลเดอร์แอป (เหมือน `saved_jobs_unreadable_*` / `db_profiles_unreadable_*` เดิม) แต่ `.gitignore` ไม่ครอบคลุม pattern นี้ ไฟล์เหล่านี้มี SQL / ชื่อ schema / ข้อมูลเชื่อมต่อของธนาคาร (สำเนา db_profiles มีรหัสผ่านแบบเข้ารหัสด้วย) จึงเสี่ยงหลุดเข้า git ตอน `git add .` แนวทางแก้ (ต้องขออนุมัติผู้ใช้เพราะต้องแก้ `.gitignore`): เพิ่ม `*_unreadable_*.json`
- [database_connect_gui.py:8543, 8638-8645] (ความเสี่ยง R4 ที่รู้อยู่แล้ว อยู่นอก spec) list_tables ยังอ่าน `db_name` จากหน้าจอเพื่อตัดสินว่าจะ "list ทุก database" หรือไม่ และ worker thread ยังอ่าน `db_user/db_password/db_host/db_port.get()` จาก Entry ของ Tk **ใน worker thread** ซึ่งไม่ thread-safe และอาจไม่ตรงกับ engine ที่ Connect ไว้ถ้าผู้ใช้แก้ช่องหลัง Connect (ช่องเหล่านี้ไม่ถูก lock) แนวทางแก้ (งานถัดไป): ใช้ `target.info.database` และอ่านค่า credential บน main thread ก่อนเริ่ม thread (ไม่เก็บรหัสผ่านใน `ConnectionInfo` แต่ส่งเป็น local ของ closure)

## 💡 Suggestion (ทางเลือก)
- [database_connect_gui.py:7587-7593] กด Stop ระหว่าง ▦ Tables ข้อความยังเขียนว่า "remaining jobs are skipped" ซึ่งชวนสับสนเพราะไม่มี Job ให้ข้าม และ worker ของ Tables ไม่เช็ค `_stop_event` (R5) ควรปรับข้อความให้กลางขึ้น หรือแยกข้อความตาม `inspect_btn` ที่แสดง Loading
- [database_connect_gui.py:7606-7627] ถ้า `_is_busy` / `_apply_run_lock` error ซ้ำ ๆ (เช่น AttributeError ที่ไม่หายเอง) จะ `print` ทุก 300 ms ทำให้ console ท่วม ควร print เฉพาะครั้งแรก (จำข้อความล่าสุดไว้)
- [database_connect_gui.py:7632, 7635, 7699, 7478] type hints / ความสม่ำเสมอ: `_confirm_destination` คืน `tuple` (design ระบุ `tuple[str, str]`, ใช้ `"tuple[str, str]"` หรือ `Tuple[str, str]` ได้โดยไม่ผูกกับ 3.9+), parameter `button` / `widget` / `_event` ยังไม่มี type, และ `_register_run_lock_button` ใช้ `self.__dict__.setdefault(...)` ต่างจากที่อื่นที่ใช้ `getattr(..., default)` ตาม design
- [tests/test_run_lock.py:439-459, tests/test_ctrl_enter.py:161-171, tests/test_profile_connect_block.py:377+] หลาย test ตรวจด้วยการค้นข้อความในซอร์ส (`assertIn('if kind == "run":\n                    ...', self.source)`) ซึ่งพังเมื่อ format / เยื้องโค้ดเปลี่ยน แม้พฤติกรรมไม่เปลี่ยน ถ้าทำได้ควรใช้ AST หรือทดสอบพฤติกรรมแทน (test_ctrl_enter ส่วนที่ใช้ regex ยังพอรับได้)
- [tests/test_list_tables_stop.py:240-246] `test_sql_editor_dialog_has_no_stop_button` ล็อกข้อจำกัดที่อยู่นอก scope (R8) ไว้เป็นพฤติกรรมที่ "ถูกต้อง" ถ้างานถัดไปเพิ่ม Stop ให้ Loading ของ SQL Editor test นี้จะพังโดยไม่มีบั๊กจริง ควรเปลี่ยนชื่อหรือใส่ docstring ให้ชัดว่าเป็นตัวบันทึกข้อจำกัดชั่วคราว
- [database_connect_gui.py:6282, 6292, 6298, 6304, 6310, 6335] (มีอยู่ก่อนรอบนี้) worker ของ SQL Editor อ่าน `self.debug_mode.get()` (Tk `BooleanVar`) จาก worker thread ควรอ่านค่าครั้งเดียวบน main thread ใน `_execute_query_background` แบบเดียวกับ engine

## หัวข้อแยก: การแก้ที่ยังไม่ commit จากรอบก่อน / ไฟล์ใน working tree
- 🟠 [preset_สส.json (untracked, root ของ repo)] ไฟล์นี้มีข้อมูลจริงของธนาคาร (ชื่อ schema จริง, ค่าเลขบัญชีใน WHERE, service name ของฐานข้อมูล และชื่อ Profile ที่เป็นชื่อเล่นบุคคล) และ **ไม่อยู่ใน `.gitignore`** ถ้า commit ด้วย `git add .` ข้อมูลจะหลุดเข้า git / GitHub แนวทางแก้ (ต้องให้ผู้ใช้ตัดสิน): ย้ายไฟล์ออกจาก repo หรือเพิ่ม `preset_*.json` ใน `.gitignore` ก่อนจุดอนุมัติที่ 2
- 💡 [database_connect_gui.py:6259-6264, README.md:47] `_on_loading_close` ไม่ reset ปุ่ม Run แล้ว ทำให้ busy ยังเป็น True จนกว่า query จะจบจริง ซึ่งสอดคล้องกับ C1 / H1 (lock และ Stop ยังทำงาน) และ README บรรทัด 47 อธิบายไว้แล้ว ไม่ถือเป็นปัญหา แต่ควรให้ผู้ใช้ยืนยันพฤติกรรมนี้ตามข้อสังเกตท้าย Manual checklist ใน `docs/tasks.md`
- 💡 [database_connect_gui.py:12277-12282] (นอก scope) `on_closing` ปิดหน้าต่างได้ทันทีแม้ `_is_busy()` จะเป็น True ทำให้ worker แบบ daemon ถูกตัดกลางคัน (DML ที่ยังไม่ commit จะถูก rollback ฝั่ง DB) ควรถามยืนยันก่อนปิดเมื่อมีงานรันอยู่
