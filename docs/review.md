# Code Review — 2026-11-13

ขอบเขต: uncommitted changes บน branch `ui/remove-duplicate-buttons` (`git diff` ของ `database_connect_gui.py`, `README.md`, `tests/test_database_connect_gui_core.py` + ไฟล์ test ใหม่ทั้ง 8 ไฟล์ใน `tests/`)
อ้างอิง: `docs/spec.md` (Round 2), `docs/design.md`, `docs/tasks.md` (R2-T1 ถึง R2-T-fix)
ผล test: `python -m unittest discover -s tests -p "test_*.py"` → Ran 586 tests, OK (รันยืนยันแล้ว)
เลขบรรทัดอ้างอิงไฟล์ใน working tree ปัจจุบัน

## สรุป
**ต้องแก้** — 🔴 1, 🟠 2, 🟡 9

- H3 (Auto WHERE), M3 (`/` ของ Oracle), H4 (reload table data) ตรง AC ไม่พบปัญหาความถูกต้อง
- M9 detected mode: ยังมีทางที่ Reset ทำให้ DELETE/UPDATE กระทบแถว **มากขึ้น** และทางนี้ไม่อยู่ใน known limits ที่ยอมรับไว้ (🔴 ข้อ 1, 🟠 ข้อ 2)
- รหัสผ่าน: ไม่พบ ciphertext หรือ `_stored_db_password` หลุดไปไฟล์ export, ช่องรหัสผ่านใน UI หรือ connection (ตรวจ `decrypt_profile_password` 236, `profile_password_for_disk` 248, export 3198-3203, import 3495-3507, load 10403, save dialog 10678-10681) และไม่พบทางที่รหัสผ่านหาย
- Dead code: ไม่มี caller ของ `_IN_LIST_PATTERN` / `_remove_sql_condition` เหลืออยู่ ส่วน `_split_sql_values` ยังถูกใช้ที่ 11647 และ 11841 (ไม่ใช่ dead code) และ `Tuple` ที่ import เพิ่มก็ถูกใช้

## 🔴 Critical (ต้องแก้ก่อน merge)

- **[database_connect_gui.py:11392-11431 `_has_negated_in_before`] `NOT col IN (SELECT ... WHERE x IN (...))` ไม่ถูกมองว่าถูก negate — Reset จนค่าหมดแล้ว DELETE จะกระทบทั้งตาราง**
  - สถานการณ์ (ทดลองรันแล้ว): `DELETE FROM acct WHERE NOT status IN (SELECT status FROM lkp WHERE seg IN ('C'))` → Reset ค่า `'C'` ออกจนหมด → `DELETE FROM acct WHERE NOT status IN (SELECT status FROM lkp WHERE 1=0)` ซึ่ง subquery ว่าง ทำให้ `NOT status IN (ว่าง)` เป็นจริงทุกแถว ลบทั้งตาราง (`tests/test_r2_reset_parameter_qa.py:278` วัดได้ 1 แถว → 3 แถว)
  - ทำไมเป็น 🔴: SQL ที่มีความหมายเดียวกัน `status NOT IN (SELECT ...)` และ `NOT (status IN (SELECT ...))` ถูกปฏิเสธถูกต้อง แต่ลำดับคำ `NOT status IN (` ที่ระดับวงเล็บนอกหลุดไป ทั้งที่ R2-T-fix Bug 4 (`docs/tasks.md:229`) และ docstring บอกว่าครอบ "`NOT col IN (`" กับ "วงเล็บที่ครอบถูกนำหน้าด้วย NOT IN" กรณีนี้**ไม่อยู่ใน known limits ที่ผู้ใช้ยอมรับ** (`docs/tasks.md:238-241`) แต่ถูก pin ไว้ใน test ว่าเป็น "KNOWN LIMIT" (test pin พฤติกรรมที่ผิด)
  - แนวทางแก้: ในลูปเดินวงเล็บ (11424-11430) เมื่อ `prev` เป็นคำ `IN` ให้หาต้นคอลัมน์ของ predicate นอกด้วย `_in_list_column_start(tokens, index - 1)` แล้วเช็กว่า token ก่อนหน้าเป็น `NOT` หรือไม่ (ถ้าหาคอลัมน์ไม่ได้ ให้ถือว่า negate ไว้ก่อน) จากนั้นเปลี่ยน `test_known_limit_not_col_in_subquery_not_caught` ให้คาด `ValueError`

## 🟠 Major (ควรแก้)

- **[database_connect_gui.py:11392-11431 `_has_negated_in_before`] negation แบบ quantified comparison / set difference ใน subquery ไม่ถูกจับ และไม่อยู่ใน known limits**
  - ทดลองรันแล้ว ได้ `1=0` ทุกกรณี และทั้ง 4 แบบจะกลายเป็น "ทุกแถว":
    - `DELETE FROM a WHERE k <> ALL (SELECT k FROM b WHERE c IN (3))`: `<> ALL (ว่าง)` เป็น TRUE ทุกแถว
    - `DELETE FROM a WHERE NOT k = ANY (SELECT k FROM b WHERE c IN (3))`
    - `DELETE FROM a WHERE k IN (SELECT k FROM a MINUS SELECT k FROM b WHERE c IN (3))`: ฝั่งที่ถูกลบออกว่าง จึงได้ทุก k
    - แบบเดียวกันกับ `EXCEPT`
  - รูปแบบ `MINUS` ใน subquery พบได้จริงใน SQL ฝั่ง Oracle/OFSAA สำหรับงาน reconcile ส่วน `<> ALL` พบน้อยกว่า
  - แนวทางแก้ (เลือกแบบ conservative): เปลี่ยนจาก blacklist เป็น **whitelist** สำหรับ list ที่ depth > 0 ใน UPDATE/DELETE ให้ยอม `1=0` เฉพาะเมื่อวงเล็บที่ครอบทุกชั้นเป็นวงเล็บจัดกลุ่ม (นำหน้าด้วย `(`, `AND`, `OR`, `WHERE`, `ON`) หรือ `col IN (` / `EXISTS (` ที่ไม่มี NOT นำหน้า **และ** ใน subquery ชั้นนั้นไม่มี `MINUS` / `EXCEPT` ที่ depth เดียวกันอยู่ก่อน list นอกนั้นให้ raise `ValueError` (Reset ใช้ไม่ได้ ไม่อันตราย) วิธีนี้ปิดข้อ 🔴 ข้างบนด้วย
  - **ความเห็นเรื่อง known limits ที่ยอมรับไว้**:
    - LEFT JOIN anti-join (`LEFT JOIN b ON ... AND b.seg IN (...) WHERE b.k IS NULL`) เป็นรูปแบบที่ **realistic** ใน SQL ตรวจหา/ลบข้อมูลที่ไม่มีคู่ และจับได้ไม่ยาก: ถ้า lead ของ list คือ `ON` และ JOIN ที่ ON นั้นสังกัดเป็น `LEFT` / `RIGHT` / `FULL` ให้ปฏิเสธ
    - `(SELECT COUNT(*) ... AND x IN (...)) = 0` พบได้บ้างแต่น้อยกว่า whitelist ข้างบนจะจับได้อัตโนมัติ (scalar subquery ไม่ได้นำหน้าด้วย `IN` / `EXISTS`)
    - แนะนำให้ปิดทั้งสองแบบใน whitelist เดียวกัน ส่วน `1 - (n IN (1))`, `IS NOT TRUE`, `COALESCE(...) = 0` เป็นรูปแบบ exotic จริง คงเป็น known limit ได้

- **[database_connect_gui.py:11495-11497 และ README.md:67] ข้อความบอกผู้ใช้ว่า "เงื่อนไข IN ใน UPDATE/DELETE จะกลายเป็น 1=0 (ไม่กระทบแถวใด)" ไม่ตรงกับพฤติกรรมจริงของ parameter แบบ IN-column / First IN list**
  - ใน tracked mode `_reset_parameter_value` (11179-11192) ให้ `1=0` เฉพาะ `AUTO_WHERE_PARAMETER` ส่วน `IN_COLUMN_PARAMETER` และ `__FIRST_IN_LIST__` ที่ถูกล้างค่าจะกลับไปใช้ template (11143-11158)
  - template ของสองชนิดนี้คือ SQL ที่มีค่าพิมพ์ไว้เดิม (`_capture_sql_template` 11032) สถานการณ์:
    1. template `DELETE FROM acct WHERE acc_no IN ('1001','1002','1003')`
    2. เลือก "acc_no IN (...)" แล้วใส่ค่าจาก Excel `('2001')`
    3. Reset `'2001'` ออก
    4. ได้ SQL กลับเป็น `IN ('1001','1002','1003')` คือลบ 3 แถวที่ผู้ใช้ไม่ได้เลือกในรอบนี้ ทั้งที่หัว dialog บอกว่า "ไม่กระทบแถวใด"
  - preview แสดง SQL จริงก่อนกด Confirm และ spec อนุญาตให้ "parameter ชนิดอื่นกลับเป็น placeholder" (`docs/spec.md` R2-2 Out of scope) แต่ข้อความใหม่ทำให้ผู้ใช้เข้าใจผิดในทางที่อันตราย (`test_other_parameter_kinds_return_to_placeholder` ใน qa.py:647 pin พฤติกรรมนี้ไว้)
  - แนวทางแก้: (ก) ถามผู้ใช้ว่าจะขยาย `1=0` ไปครอบ IN-column / First IN list ใน UPDATE/DELETE ด้วยหรือไม่ หรือ (ข) แก้ข้อความทั้งสองที่ให้ตรงจริง เช่น "Auto WHERE ใน UPDATE/DELETE → 1=0; parameter อื่นกลับเป็นค่าใน template เดิม"

## 🟡 Minor (ทางเลือก)

- **[database_connect_gui.py:11865] ข้อความ footer ของ detected mode ล้าสมัย**: ยังเขียนว่า "ถ้าเอาออกครบทุกค่า เงื่อนไขนั้นจะถูกลบ" ซึ่งไม่ตรงกับพฤติกรรมใหม่ (กลายเป็น `1=0` หรือถูกปฏิเสธเมื่อเป็น NOT IN) แก้ข้อความให้ตรงกับหัว dialog

- **[database_connect_gui.py:11456-11459] ข้อความ error ระบุผิดคอลัมน์/ผิดชนิด**: กรณี negation มาจากวงเล็บนอก เช่น `x NOT IN (SELECT ... WHERE seg IN ('C'))` ข้อความเป็น "seg NOT IN (...) would have no values left" ทั้งที่ `seg` ใช้ `IN` ธรรมดา ทำให้ผู้ใช้งง แนะนำข้อความกลาง ๆ เช่น "`seg IN (...)` อยู่ใต้ NOT / NOT IN / NOT EXISTS — ถ้าเอาค่าออกจนหมดจะกระทบทุกแถว"

- **[docs/spec.md, docs/design.md, docs/tasks.md] งานรหัสผ่าน (DPAPI fallback, `PROFILE_STORED_PASSWORD_KEY`, `decrypt_profile_password`, `profile_password_for_disk`) ไม่มีใน spec/design/tasks**: ไม่มี AC และไม่มีบันทึกว่าผู้ใช้อนุมัติ (กฎ scope ใน CLAUDE.md) ตัวโค้ดตรวจแล้วปลอดภัย (ดูสรุป) แต่ควรเพิ่ม AC/บันทึกการอนุมัติลง `docs/spec.md` และ `docs/tasks.md` ให้ trace ได้ (หมายเหตุ: Export แบบ "include passwords" เขียน plaintext ซึ่งเป็นพฤติกรรมเดิมที่มี prompt เตือนอยู่แล้ว)

- **[database_connect_gui.py:10676-10681] ล้าง ciphertext ที่ถอดไม่ได้โดยตั้งใจไม่ได้**: เมื่อช่องรหัสผ่านว่าง ciphertext เดิมจะถูกเขียนกลับทุกครั้งที่ Save แม้ผู้ใช้เปลี่ยน host/user ไปแล้ว ไม่มีทางลบนอกจากใส่รหัสใหม่ ไม่อันตราย (ไม่มีวันถูกใช้หรือแสดง) แต่ค้างอยู่ในไฟล์ ถ้าต้องการอาจล้างเมื่อ `db_host`/`db_user` เปลี่ยน

- **[database_connect_gui.py:9995-10004, 10046] Export เมื่อไฟล์ table data หาย/อ่านไม่ได้ ไม่มีบรรทัดอธิบายใน log**: แต่ละ job ล้มด้วยข้อความ "Table variable has no data / is ambiguous" ซึ่งไม่บอกสาเหตุจริง (Run บอกว่า "file is missing or cannot be read — try again") ไม่ได้ใช้ข้อมูลเก่า จึงไม่อันตราย แนะนำให้เขียน log/แจ้งเตือนเหมือน Run และเพิ่ม test ที่รัน `worker` เพื่อยืนยันว่า job ล้ม (ปัจจุบัน `test_export_with_missing_file_writes_no_line` ตรวจแค่ว่าไม่มีบรรทัด timestamp)

- **[database_connect_gui.py:7567-7593] cache เทียบด้วย mtime อย่างเดียว**: ถ้าไฟล์ถูกเขียนใหม่ภายใน resolution ของ mtime เดียวกัน (FAT/SMB หรือ sync บางแบบที่ปัด mtime) จะใช้ข้อมูลเก่า บน NTFS โอกาสต่ำมาก ถ้าต้องการกันไว้ ให้เทียบ `(st_mtime_ns, st_size)` จาก `os.stat`

- **[database_connect_gui.py:11272-11431] maintainability ของ helper ใหม่**:
  - token เป็น tuple ใช้ index ตรง ๆ (`t[3]`, `t[4]`, `token[:2]`) และ type hint เป็น `tuple`/`list` เปล่า ควรประกาศ alias เช่น `SqlToken = Tuple[str, str, int, int, int]` หรือ `NamedTuple`
  - `_detect_sql_in_lists`, `_reset_parameter_value`, `_append_where_conditions` ยังไม่มี type hints
  - `_has_negated_in_before` scan `sql[:values_start]` ใหม่ทุก list (O(n·k)) ทั้งที่ `_detect_sql_in_lists` มี tokens อยู่แล้ว ส่ง tokens เข้าไปได้

- **[database_connect_gui.py:569 `_WHERE_TAIL_WORDS`] คอลัมน์ชื่อ `option` / `limit` / `offset` / `window` ที่ depth 0**: Auto WHERE จะแทรกผิดที่ เช่น `DELETE FROM t WHERE a=1 AND option='x'` → `WHERE (a=1 AND) AND C IN (...) option='x'` ได้ SQL ที่ syntax error (ไม่ทำให้แถวกว้างขึ้น จึงไม่อันตราย) แนะนำเช็กว่าคำถัดไปไม่ใช่ operator (`=`, `<`, `IN` ...) ก่อนถือว่าเป็น clause ท้าย หรือ raise `ValueError` ตั้งแต่ใน `_sql_where_layout` เมื่อ condition ลงท้ายด้วย AND/OR

- **[tests/test_r2_reset_parameter_qa.py, qa2.py, qa3.py] โครงสร้าง test**:
  - test 3 ไฟล์ตั้งชื่อตามรอบ QA ไม่ใช่ตามพฤติกรรม และซ้ำกันบางส่วน (`InvariantMixin`, `affected`, `norm` ถูกประกาศ/import ซ้ำ) แนะนำรวมเป็นไฟล์ตามหัวข้อ (detection / negation / tracked mode / known limits)
  - test ที่ pin พฤติกรรมอันตราย (`test_known_limit_*` ใน qa.py:278-306 และ qa3.py:296) ควรตั้งชื่อให้เห็นชัดว่า UNSAFE และอ้างข้อใน `docs/tasks.md`
  - ข้อ qa.py:278 ต้องเปลี่ยนตาม 🔴
  - ส่วน `tests/test_r2_table_data_refresh.py` และ `tests/test_profile_password.py` assert ผลจริงครบ (ค่าที่ได้, mtime, การไม่เปิดไฟล์, ไม่มี ciphertext ในไฟล์ export) ไม่พบ test ที่ไม่ assert อะไร

---

# Code Review — Round 3 (Import / Export Groups ที่ Sidebar) — 2026-11-13

ขอบเขต: ส่วนที่ Round 3 แตะใน `database_connect_gui.py` ได้แก่ pure helper (838-937), `_ensure_script_groups_loaded`, `export_script_groups`, `import_script_groups`, `_ask_import_mode`, `_refresh_script_groups_window`, `sidebar_export_script_groups`, `sidebar_import_script_groups` (4365-4509), closure ที่ delegate + การลงทะเบียน `_script_groups_refresh` / `<Destroy>` ใน `show_script_groups_dialog` (4765, 5106-5170), แถว `groups_io` ของ sidebar (2719-2726) และ `tests/test_r3_script_groups_io.py`
อ้างอิง: `docs/spec.md` Round 3 (R3-AC-1..18), `docs/design.md` R3-D1..D9, `docs/tasks.md` R3-T1..T5
ผล test: `python -m unittest tests.test_r3_script_groups_io` → Ran 144 tests, OK (รันยืนยันแล้ว); ทั้งชุด 781 OK ตามรายงาน QA

## สรุป
**ผ่าน** — 🔴 0, 🟡 2, 🟢 5

- เทียบ closure `export_groups` / `import_groups` เดิมใน `HEAD` ทีละบรรทัดแล้ว: ข้อความ messagebox, title, `parent`, ลำดับคำถาม, การกรองกลุ่ม, การตั้งชื่อ `name (n)`, `existing.pop` (กลุ่มเดิมถูกแทนที่ได้แค่ครั้งเดียว), `default=str` และลำดับ save → refresh → log **ตรงเดิมทุกจุด** ไม่พบ regression ของปุ่มใน dialog (R3-AC-17)
- sidebar ส่ง `selected=None` จึงไม่ถาม all / only one (R3-A2) และใช้ `parent=self.root` ทุก dialog (R3-A4) ตรง spec
- บันทึกผ่าน `save_script_groups()` ตัวเดิม จึงโดนบล็อก `_script_groups_save_blocked` เหมือนกัน (ข้อจำกัดใน spec R3-5)
- `<Destroy>` handler เช็กทั้ง `event.widget is dialog` และ identity ของ callback; `_refresh_script_groups_window` เช็ก `winfo_exists()` ซ้ำอีกชั้น จึงไม่เรียก closure ของ dialog ที่ปิดไปแล้ว
- ความปลอดภัย: ไฟล์ที่ import ไม่สามารถเปลี่ยน DB เป้าหมายตอนรันได้ เพราะ `group_jobs` (5085-5087) ทับ `profile` ด้วย Profile ปัจจุบันเสมอ ส่วน path มาจาก file dialog ที่ผู้ใช้เลือกเอง จึงไม่มีประเด็น path traversal
- Race: ตัวแก้ script (`_edit_group_script_dialog`) และ `_pick_jobs_dialog` ใช้ `grab_set()` จึงกดปุ่ม sidebar ไม่ได้ระหว่างที่ตัวแก้เปิดอยู่ กรณี Replace ลบ object กลุ่มที่กำลังแก้อยู่จึงเกิดไม่ได้
- `_ask_import_mode` ไม่อยู่ใน design แต่เป็นการแยกโค้ดเดิมออกมาตรง ๆ (ไม่เพิ่มพฤติกรรม) ช่วยลดความยาวของ `import_script_groups` จึงไม่ถือว่าเกิน scope

## 🔴 Critical (ต้องแก้ก่อน merge)
- ไม่มี

## 🟡 Warning (ควรแก้)

- **[database_connect_gui.py:4455-4459 `import_script_groups` + 4327-4348 `save_script_groups`] เขียน log "📥 Imported" แม้บันทึกไม่สำเร็จ**
  - `save_script_groups()` กลืน error (แสดง showerror แล้ว return `None`) ทั้งตอนบล็อก (4328-4334) และตอนเขียนไฟล์ล้ม (4346-4348) แต่ `import_script_groups` ยัง refresh และเขียน `📥 Imported N group(s) from ...` ต่อ
  - สถานการณ์: `script_groups.json` ถูก OneDrive ล็อกตอนเปิดแอป ทำให้ `_script_groups_save_blocked = True` → ผู้ใช้กด `⇧ Import Groups` ที่ sidebar → เห็น error "not overwritten" ตามด้วย log ว่า import สำเร็จ และกลุ่มขึ้นในหน้าต่าง Script Groups (อยู่ในหน่วยความจำเท่านั้น) → ปิดแอปแล้วกลุ่มที่ import หาย
  - ไฟล์เดิมไม่เสียหาย และเป็นพฤติกรรมเดิมของ dialog ที่ design ยอมรับไว้ (R3-R3) จึงไม่ใช่ 🔴 แต่ตอนนี้ทางนี้เข้าถึงได้ง่ายขึ้นจาก sidebar
  - แนวทางแก้ (ต้องขอผู้ใช้เพิ่มใน spec ก่อน): ให้ `save_script_groups()` คืน `bool` แล้วถ้าบันทึกไม่สำเร็จให้เขียน log อีกแบบ เช่น `⚠️ Imported ... (not saved)` หรือ rollback `self.script_groups` กลับเป็นค่าก่อน merge

- **[tests/test_r3_script_groups_io.py:1102-1110 `test_refresh_registered_and_destroy_guarded`] กลไก `<Destroy>` ที่เสี่ยงที่สุด (R3-R2) มีแค่ test ที่เทียบ string ของ source**
  - test ใช้ `assertIn` กับข้อความโค้ด จึงยังผ่านถ้าลอจิกผิดแต่ข้อความยังอยู่ (เช่น ย้าย `bind` ไปไว้ใน branch ที่ไม่ถูกเรียก) และจะล้มถ้า refactor แค่ whitespace หรือชื่อตัวแปรทั้งที่พฤติกรรมถูก ตอนนี้ M11-M13 (manual) เป็นสิ่งเดียวที่ยืนยันพฤติกรรมจริง
  - แนวทางแก้: ไฟล์นี้มีแบบอย่างการสร้าง Tk แบบ withdrawn + skipTest อยู่แล้ว (`TestSidebarRowBuild` 1643) ให้เพิ่ม test เปิด `show_script_groups_dialog` จริงแล้วตรวจ 3 กรณี (1) ทำลาย child widget แล้ว callback ยังอยู่ (2) `dialog.destroy()` แล้ว `_script_groups_refresh is None` (3) ปิดหน้าต่างเก่า เปิดใหม่ แล้ว callback ของหน้าต่างใหม่ไม่ถูกล้าง

## 🟢 Suggestion (ทางเลือก)

- **[database_connect_gui.py:4403-4408 `export_script_groups`] เขียนไฟล์ export แบบไม่ atomic**: ถ้าผู้ใช้เลือกเขียนทับไฟล์ backup เดิม แล้ว `json.dump` ล้มกลางทาง (ค่าที่ serialize ไม่ได้ / ดิสก์เต็ม / OneDrive ล็อก) จะเหลือไฟล์ที่ถูกตัดครึ่ง (`test_write_error_from_json_dump` 541 ยืนยันว่าทางนี้เกิดได้) design สั่งให้คงไว้เหมือนเดิม แต่ถ้าแก้ในรอบหน้าก็ใช้ `write_json_atomic` ที่มีอยู่แล้วได้ (ต้องรองรับ `ensure_ascii=False`)

- **[database_connect_gui.py:849-851 กับ 4337-4341] โค้ดตัด runtime key ซ้ำกัน**: `_export_script` กับ comprehension ใน `save_script_groups` เหมือนกันทุกตัวอักษร ถ้าวันหนึ่งเพิ่ม runtime key ใหม่ต้องแก้สองที่ ควรให้ `save_script_groups` เรียก `_export_script` (รอบนี้ design ห้ามแตะ `save_script_groups` จึงทำในรอบถัดไป)

- **[database_connect_gui.py:878-899 `parse_script_groups_import`] ชื่อกลุ่มที่มีช่องว่างหน้า/หลัง** (เป็นพฤติกรรมเดิม): ใช้ `strip()` แค่ตอนตรวจว่าว่างหรือไม่ แต่ไม่ได้ตัดช่องว่างออกจากชื่อจริง ไฟล์ที่มี `" G1 "` จึงไม่ชนกับ `"G1"` และได้กลุ่มที่ชื่อดูเหมือนซ้ำกันในรายการ ถ้าต้องการให้ normalize ด้วย `name.strip()` ก่อน merge (ต้องเพิ่มใน spec)

- **[database_connect_gui.py:902-904 `_profile_group_names` กับ 4312-4325 `load_script_groups`] ชื่อกลุ่มเดิมที่ไม่ใช่ string** (เป็นพฤติกรรมเดิม): `load_script_groups` กรองแค่ `g.get("name")` ที่เป็น truthy ถ้า `script_groups.json` ที่แก้ด้วยมือมี `"name": 123` อยู่ใน Profile เดียวกัน การ import จะเจอ `AttributeError` ที่ `.lower()` และขึ้น traceback ใน console (เกิดก่อนแก้ข้อมูลใด ๆ จึงไม่เสียหาย) กันได้ด้วย `str(g["name"])` หรือกรอง `isinstance(name, str)` ตอน load

- **[tests/test_r3_script_groups_io.py:1643-1712 `TestSidebarRowBuild`] สร้างหน้าต่างหลักจริงใน unittest**: spec R3-4 บอกว่า unittest ต้องไม่เปิดหน้าต่าง Tk ตัวนี้ใช้ `withdraw()`, patch `APP_DIR` / `messagebox` และ skip เมื่อไม่มี display ซึ่งรับได้ แต่ควรระบุข้อยกเว้นนี้ใน `docs/tasks.md` และตรวจว่า `DatabaseConnectorGUI.__init__` ไม่อ่าน/เขียนไฟล์นอก `APP_DIR` หรือตั้ง `after()` ที่ทำงานหลัง `root.destroy()` ส่วน test อื่นในไฟล์ assert ผลจริงครบ (เนื้อหาไฟล์ที่เขียน, `parent`, ข้อความ log, จำนวนครั้งที่เรียก save, ลำดับ save → refresh → log) ไม่พบ test ที่ไม่ได้ assert อะไรจริง

# Code Review — Round 4 (Profile mismatch / Excel row limit) — 2026-11-13

ขอบเขต: เฉพาะ Round 4 ใน `database_connect_gui.py`, `tests/test_r4_profile_mismatch.py`, `tests/test_r4_excel_row_limit.py`; อ้างอิง R4-AC-1 ถึง R4-AC-9 และ R4-D1 ถึง R4-D6
ผล test: focused R4 `python -m unittest tests.test_r4_profile_mismatch tests.test_r4_excel_row_limit` → Ran 8 tests, OK; `docs/tasks.md` บันทึก full suite 789 tests, OK (ไม่ได้รันซ้ำใน review นี้)

## สรุป
**ผ่านพร้อม Warning** — 🔴 0, 🟡 1, 🟢 0

- Guard ของ Profile ตรวจครบทั้งห้า entry points หลัง busy guard และก่อนเริ่ม SQL, confirmation, worker หรือ file dialog; log ระบุ Profile ที่เลือกและ connection โดยไม่แก้ engine/target เมื่อ mismatch
- Row-limit check ใช้ `>` กับขีดจำกัด 1,048,575 แถวข้อมูลก่อนเขียน DataFrame; กรณีเกินเข้าสู่ per-job failure handler และยังประมวลผล Job ถัดไป

## 🔴 Critical (ต้องแก้ก่อน merge)
- ไม่มี

## 🟡 Warning (ควรแก้)
- **[database_connect_gui.py:10373, 10375] การเขียน SQL ต่อท้ายยังทำให้ worksheet เกิน Excel row limit เมื่อ DataFrame อยู่ที่ขอบเขตสูงสุด**
  - สถานการณ์: Job มี 1,048,575 แถวพอดี; DataFrame พร้อม header ใช้แถว 1 ถึง 1,048,576 จากนั้นโค้ดคำนวณ `start_row = ws.max_row + 2` และเขียน SQL ลงแถว 1,048,578 เป็นต้นไป
  - ผลกระทบ: worksheet เกินเพดาน 1,048,576 แถว แม้ข้อมูล DataFrame จะไม่ถูกตัด; Excel อาจซ่อมไฟล์หรือไม่เก็บเนื้อหาส่วนที่อยู่นอกช่วงที่รองรับ ทำให้ผล export ที่ AC-7 ระบุว่าครบถ้วนไม่รับประกัน
  - หลักฐาน test gap: `tests/test_r4_excel_row_limit.py:64` กำหนด fake worksheet ให้ `max_row = 2`; `tests/test_r4_excel_row_limit.py:255` ตรวจจำนวนแถวที่ส่งเข้า `to_excel` แต่ stub ไม่ขยับ `max_row` ตาม DataFrame และไม่ตรวจตำแหน่ง SQL annotation จึงไม่ตรวจพบกรณีนี้
  - แนวทางแก้: เมื่อไม่มีแถวเหลือสำหรับ annotation ให้ไม่เขียน SQL ลง worksheet นั้น หรือจัดเก็บ SQL ในตำแหน่งที่ไม่ทำให้เกิน limit; เพิ่ม assertion สำหรับหมายเลขแถวหลังเขียนข้อมูลที่ boundary

## 🟢 Suggestion (ทางเลือก)
- ไม่มี

# Follow-up Review — Round 4 Warning — 2026-11-13

ขอบเขต: ตรวจเฉพาะการแก้ warning เรื่อง SQL annotation ใน `database_connect_gui.py` และ regression tests ใน `tests/test_r4_excel_row_limit.py`; อ้างอิง R4-AC-6 ถึง R4-AC-8 และรายงาน Round 4 ข้างต้น
ผล focused test: `python -m unittest tests.test_r4_excel_row_limit -v` → Ran 4 tests, OK
ผล full suite ล่าสุดตาม `docs/tasks.md`: `python -m unittest discover -s tests -p "test_*.py"` → Ran 790 tests, OK

## สรุป
**ผ่าน — 🔴 0, 🟡 0, 🟢 0**

- Warning เดิมปิดแล้ว: เมื่อ DataFrame มี 1,048,575 แถว ข้อมูลพร้อม header ใช้ worksheet ถึงแถว 1,048,576; `append_sql_annotation` ตรวจแถวสุดท้ายก่อนเขียนและข้าม annotation ทั้งก้อนเมื่อเกิน limit พร้อมบันทึก warning ลง Execution Logs ([database_connect_gui.py:10193](database_connect_gui.py#L10193), [database_connect_gui.py:10197](database_connect_gui.py#L10197)). ไม่มีการตัด DataFrame; boundary test ยืนยันจำนวนแถวครบและไม่มี cell write เกิน limit ([tests/test_r4_excel_row_limit.py:278](tests/test_r4_excel_row_limit.py#L278), [tests/test_r4_excel_row_limit.py:279](tests/test_r4_excel_row_limit.py#L279)).
- เมื่อมีพื้นที่ annotation ยังถูกเขียนตามปกติ (R4-AC-7; [tests/test_r4_excel_row_limit.py:290](tests/test_r4_excel_row_limit.py#L290)).
- Failure handling ไม่ regression: งานเกิน limit ยังคงถูกนับ Failed โดยไม่เขียน DataFrame บางส่วน และงานถัดไป export สำเร็จพร้อมยอดสรุปตรงตามผล (R4-AC-6/R4-AC-8; [database_connect_gui.py:10271](database_connect_gui.py#L10271), [database_connect_gui.py:10448](database_connect_gui.py#L10448), [tests/test_r4_excel_row_limit.py:244](tests/test_r4_excel_row_limit.py#L244), [tests/test_r4_excel_row_limit.py:298](tests/test_r4_excel_row_limit.py#L298)).
- ไม่พบข้อบกพร่องที่ยังค้างในขอบเขต follow-up นี้

## 🔴 Critical (ต้องแก้ก่อน merge)
- ไม่มี

## 🟡 Warning (ควรแก้)
- ไม่มี

## 🟢 Suggestion (ทางเลือก)
- ไม่มี
# Code Review - R2-T-fix2 / R3 Lifecycle / R4 Excel Tests - 2026-11-13

Scope: `_statement_scope_refusal` / `_in_list_reset_refusal` and `tests/test_r2_reset_t2t_plsql.py`; the lifecycle test in `tests/test_r3_script_groups_io.py`; and the Task 2 Excel row-limit test state in `tests/test_r4_excel_row_limit.py`. Reviewed against the R2 spec, R2-D4, task entries, and prior reviews.
Focused checks: R2-T-fix2 9 tests, R2 whitelist/invariant 44 tests, R3 lifecycle 1 test, and R4 Excel 4 tests passed.
Latest full-suite result provided by the user: `Ran 800 tests ... OK`. Tcl reported `invalid command name ... update_jobs_scroll_state` after UI tests; both UI tests pass separately.

## Summary
**Pass with warnings** - Critical 0, Warning 2, Suggestion 0

- No remaining widening path was found in the reviewed Reset safeguards: tested PL/SQL control-flow, unknown statement, negation, CASE, outer-join, and set-operation contexts refuse the reset; allowed SQLite write cases do not affect more rows.
- The R4 boundary test models DataFrame row growth, verifies the worksheet stops at row 1,048,576, skips an out-of-range SQL annotation, and still writes the annotation when space remains.
- The R3 lifecycle test uses real Tk to check child destruction, dialog destruction, and a subsequent dialog; no app or test source was changed in this review.

## Critical
- None

## Warning
- **[tests/test_r2_reset_t2t_plsql.py:307] Positive CTE use in a write statement is not asserted to reset successfully.**
  - Scenario: `test_independent_nonrecursive_cte_with_positive_references_never_widen` calls `assert_never_widens`; that helper treats `ValueError` as safe and continues (`tests/test_r2_reset_nested_whitelist.py:103-117`). The test does not assert rewritten SQL or that any case executed.
  - Impact: refusing every CTE still passes, although R2-T-fix2 requests support for nonrecursive CTEs used only in positive positions.
  - Recommendation: assert the expected rewritten SQL and affected-row count for at least one positive write-CTE case, retaining the invariant check.
- **[tests/test_r3_script_groups_io.py:1718, database_connect_gui.py:2779] Real-Tk teardown can leave an `after_idle` callback pending.**
  - Scenario: the lifecycle test constructs `DatabaseConnectorGUI` and destroys the root; app initialization schedules `update_jobs_scroll_state` through `jobs_canvas.after_idle`. The reported full-suite run emits the Tcl invalid-command diagnostic after UI tests despite passing assertions.
  - Impact: noisy suite output makes Tk teardown failures harder to distinguish; current evidence does not show a failed lifecycle assertion.
  - Recommendation: isolate lifecycle testing from full UI initialization or drain/cancel test-created pending callbacks before destroying the root. No app-code change was made in this review.

## Suggestion
- None

# Follow-up Review - R2-T-fix2 / R3 Lifecycle Warnings - 2026-11-13

Scope: the two warnings in the preceding follow-up review. Read-only verification only; tests were not run as requested.

## Summary
**Pass - Critical 0, Warning 0, Suggestion 0**

- The positive inline-view cases explicitly check that reset output contains `1=0` before invoking `assert_never_widens` (`tests/test_r2_reset_t2t_plsql.py:297-309`). The nonrecursive positive-reference CTE cases do the same (`tests/test_r2_reset_t2t_plsql.py:311-322`). The helper allows refusal, but those preceding output assertions require a successful reset; its row-invariant path then executes the rewritten SQL against SQLite and checks affected rows do not increase (`tests/test_r2_reset_nested_whitelist.py:91-118`). Warning closed.
- The real-Tk lifecycle test calls `root.update_idletasks()` after GUI construction and before opening/destroying dialogs (`tests/test_r3_script_groups_io.py:1725-1730`), draining the scheduled idle callback implicated in the teardown diagnostic. Warning closed.
- The latest full-suite record in `docs/tasks.md` is `Ran 800 tests in 8.458s`, `OK`, with no Tcl diagnostic (`docs/tasks.md:273`, `docs/tasks.md:332`). This record was inspected, not rerun.
- No source or test files were edited in this follow-up; only this review entry is appended. The existing worktree already reports `database_connect_gui.py` modified, and `docs/tasks.md` lists that source under R2-T3/R2-T-fix2, so this is not a claim that the accumulated Task 3 implementation is source-free.

## Critical
- None

## Warning
- None

## Suggestion
- None


# Code Review — Round 5 (Profile, Export, SQL parsing, UI thread safety) — 2026-11-16

> ขอบเขต: R5-T1 ถึง R5-T13 (C-1, H-3, C-2, C-3, H-2, M-1, H-1, M-3, M-2, M-4, M-5, M-6) ใน `database_connect_gui.py` และ `tests/test_bugfix_*.py` 12 ไฟล์
> หมายเหตุ: `git diff database_connect_gui.py` รวมงาน Round 2-4 ที่ยังไม่ commit ด้วย; review นี้ดูเฉพาะจุดของ Round 5
> หมายเหตุ: ระหว่าง review มีการแก้ `database_connect_gui.py` พร้อมกัน (`save_script_groups` เปลี่ยนเป็นคืน `bool` และเพิ่ม rollback ใน import Script Groups รวม +9 บรรทัด) และ `tests/test_script_groups_block.py`; งานนี้อยู่นอก Round 5 และไม่ได้ review; เลขบรรทัดในหัวข้อนี้อ้างอิงไฟล์หลังการแก้นั้น

## สรุป
ผ่าน (ไม่มี 🔴) แต่ควรแก้ 🟡 ก่อน merge — 🔴 0, 🟡 4, 🟢 7

ผลรัน test ในเครื่องที่ review (2026-11-16):
- `python -m unittest discover -s tests -p "test_*.py"` เมื่อ stdout เป็น pipe ที่ encoding เป็น `cp874` → **Ran 842, FAILED (errors=1)** ที่ `test_bugfix_h3.SaveProfilesResultTests.test_save_profiles_returns_false_when_write_raises` (ดู 🟡-1)
- ชุดเดียวกันเมื่อตั้ง `PYTHONIOENCODING=utf-8` → `test_bugfix_*.py` Ran 42, OK (ผล 842 OK ตามที่รายงานใน `docs/tasks.md` ทำซ้ำได้เฉพาะเมื่อ stdout เป็น UTF-8)

## Verdict ราย R5-AC

| AC | ผล | หมายเหตุ |
|---|---|---|
| R5-AC-1 (C-1) | ✅ ผ่าน | `database_connect_gui.py:11045-11047` เรียก `current(...)` แล้วจึง `update_jobs_list()`; `run_job` ปฏิเสธที่ `:9639-9648` ก่อน `_prepare_run_sql`/confirmation/thread (ดู 🟡-2 เรื่อง Job เก่าที่ไม่มี key `profile`) |
| R5-AC-2 (H-3) | ⚠️ ผ่านแบบมีเงื่อนไข | `save_profiles`/`save_jobs` คืน bool ทุกทาง (`:10784-10802`, `:9478-9492`); callers ทั้ง 7 ทำ snapshot/rollback ถูกต้อง; แต่ `save_profiles` อาจ raise แทน return False เมื่อ stdout ไม่ใช่ UTF-8 (🟡-1) |
| R5-AC-3 (C-2) | ⚠️ ผ่านตาม AC | cell ผลลัพธ์ที่เกินถูกเว้นว่าง, log ระบุ Job/column, นับเป็น Warning (`:10508-10527`, `:10610-10615`); แต่ cell อื่นในไฟล์เดียวกันยังไม่ตรวจ (🟡-3) |
| R5-AC-4 (C-3) | ✅ ผ่าน | `:10451-10452` ส่ง `bytes` เข้า `format_db_value`; โค้ด decode UTF-16LE/UTF-8 ถูกลบแล้ว |
| R5-AC-5 (H-2) | ✅ ผ่าน | `:11512-11533` หา `IN` + `(` จาก `_scan_sql`, จับวงเล็บซ้อนได้, ไม่พบ → `ValueError("SQL template does not contain an IN (...) list")` |
| R5-AC-6 (M-1) | ⚠️ ผ่านตาม spec | `_detect_sql_placeholders` (`:458-497`) ข้าม string/comment, `::` และ `HH24:MI:SS` (ทั้งในและนอก quote) ถูกต้อง; แต่ทำให้ placeholder แบบมี quote ที่เคยรองรับใช้ไม่ได้ (🟡-4) |
| R5-AC-7 (H-1) | ✅ ผ่าน | snapshot ที่ `:9037-9045` ส่งเข้า thread ทาง `args`; `temp_engine.dispose()` ใน `finally` (`:9149-9229`); SQL Server ใช้ `text(...)` + `{"schema": schema}` |
| R5-AC-8 (M-3) | ✅ ผ่าน | `execute_query` อ่าน `debug_mode` ที่ `:8316` แล้วส่งเข้า `_execute_query_background`; `test_connection` (`:11216-11258`) worker ไม่แตะ widget, `show()` ถูกจัดผ่าน `root.after` และตรวจ `winfo_exists` บน main thread |
| R5-AC-9 (M-2) | ✅ ผ่าน | `write_literal_cell` / `force_literal_strings` (`:10325-10338`) ใช้กับ annotation, No Data, Failed, Skipped |
| R5-AC-10 (M-4) | ✅ ผ่าน | `on_closing` (`:13979-13990`) ถาม Yes/No เมื่อ `_is_busy()` |
| R5-AC-11 (M-5) | ✅ ผ่าน | เทียบ `casefold()` กับ `os.listdir`, ถามก่อนเขียนทับ, ใช้ `write_json_atomic`, Cancel/ล้มเหลวไม่แตะไฟล์เดิม (`:5313-5354`) |
| R5-AC-12 (M-6) | ✅ ผ่าน | `do_import` เรียก `load_profile_data(active_profile)` หลัง save สำเร็จเท่านั้น (`:3698-3700`) |
| R5-AC-13 (Regression) | ⚠️ ผ่านแบบมีเงื่อนไข | 842 OK เฉพาะเมื่อ stdout เป็น UTF-8; บน pipe ที่ใช้ `cp874` มี 1 error (🟡-1) |

## 🔴 Critical (ต้องแก้ก่อน merge)
- ไม่มี

## 🟡 Warning (ควรแก้)
1. **[database_connect_gui.py:10798-10801] `save_profiles` อาจ raise แทนที่จะ return `False`**: บรรทัด except เรียก `print(error_msg)` โดย `error_msg` ขึ้นต้นด้วย "❌" ถ้า stdout ใช้ encoding ที่ไม่มีอักขระนี้ (เช่น `cp874` ของ Windows ภาษาไทยเมื่อ stdout ถูก redirect หรือ pipe, รวมถึงตอนรัน test ผ่าน pipe) `print` จะ raise `UnicodeEncodeError` ออกจาก except block
   - ผลกระทบ: เมื่อเขียนไฟล์ไม่สำเร็จ (เช่นไฟล์ถูกล็อก) จะไม่ขึ้น `showerror` และ exception หลุดออกจาก `save_profiles` ทำให้ caller ใน R5-AC-2 (`save_profile_dialog.save`, `new_profile_dialog.create`, `delete_profile`) ไม่ได้ rollback: `saved_profiles` ในหน่วยความจำไม่ตรงกับไฟล์ ซึ่งเป็นปัญหาที่ H-3 ตั้งใจแก้ ส่วน `do_import` จะเข้า except ทั่วไปที่ `:3726` ซึ่งไม่ได้ rollback เช่นกัน; test `tests/test_bugfix_h3.py:198-206` fail ในสภาพแวดล้อมนี้ ทำซ้ำได้ด้วย `python -m unittest tests.test_bugfix_h3 2>&1 | cat` บนเครื่องที่ใช้ `cp874`
   - แนวทางแก้: ครอบ `print` ด้วย `try/except Exception: pass` หรือ log ข้อความ ASCII ให้ `return False` เกิดขึ้นเสมอ (`print(error_msg)` มีมาตั้งแต่ก่อน Round 5 แต่ตอนนี้ contract ของ H-3 ขึ้นกับมัน)
2. **[database_connect_gui.py:9639-9648 เทียบกับ :3920-3922 และ :4054] Job เก่าที่ไม่มี key `"profile"` แสดงใน list ของทุก Profile แต่กด ▶ ไม่ได้**: `update_jobs_list` และ `get_jobs_to_run` ใช้ `job.get("profile", current_profile)` (ไม่มี key ให้ถือว่าเป็นของ Profile ปัจจุบัน) แต่ `run_job` ใช้ `job.get("profile")` ซึ่งได้ `None` จึงไม่เท่ากับ Profile ที่เลือก
   - ผลกระทบ: Job จาก `saved_jobs.json` รุ่นเก่ายังแสดงและรันผ่าน Run Selected/Run All ได้ แต่ปุ่ม ▶ บนการ์ดเดียวกันขึ้น "⛔ Run Job ไม่ได้เริ่มงาน: Job Profile คือ 'None' ..." ทำให้พฤติกรรมในแอปไม่สอดคล้องกัน
   - แนวทางแก้: เปรียบเทียบด้วย default เดียวกัน คือ `job.get("profile", selected_profile)` ซึ่งยังตรงกับเจตนาของ AC ที่ห้ามรัน Job ของ Profile อื่น
3. **[database_connect_gui.py:10412, :10439-10442, :10555 / :10340-10355, :10631] C-2 ตรวจเฉพาะ cell ของผลลัพธ์**: ข้อความ SQL ที่เขียนลง Skipped (`"Query": [query]`), Failed (`"Query"`/`"Error"`), No Data และ SQL annotation ไม่ได้ตรวจความยาว 32,767 ตัวอักษร
   - ผลกระทบ: Job ที่ render IN list จาก Excel หลายพันค่าลงในบรรทัดเดียว (เป็น flow หลักของแอปนี้) จะได้บรรทัด SQL ที่ยาวเกิน limit; openpyxl เขียนได้โดยไม่ error แต่ Excel จะเปิดไฟล์แบบต้องซ่อมแซมหรือตัดข้อความ และ Job ยังถูกนับเป็น Success
   - แนวทางแก้: ใช้ helper ตรวจความยาวเดียวกันใน `write_literal_cell` และก่อนสร้าง DataFrame ของ Skipped/Failed (ตัดข้อความหรือเว้นว่าง พร้อม log warning) เป็นส่วนขยายของ C-2 ที่ควรยืนยันกับผู้ใช้ก่อน เพราะ AC-3 ระบุเฉพาะ "ผลของ Job"
4. **[database_connect_gui.py:458-497, :11535-11544; tests/test_database_connect_gui_core.py:542-544] M-1 ทำให้ placeholder แบบมี quote ที่เคยรองรับใช้ไม่ได้**: `_render_sql_template` ตั้งใจรองรับ `':ACC'` และ `'{ACC}'` (regex `(?P<quote>['\"]?)`) และมี test `test_quoted_parameter_still_replaced` รองรับอยู่ แต่ตอนนี้ `_detect_sql_placeholders("WHERE a IN (':ACC')")` และ `_detect_sql_placeholders("WHERE a = '{acc}'")` คืน `[]` (ยืนยันแล้วด้วยการรันจริง)
   - ผลกระทบ: template ที่ผู้ใช้เขียน placeholder ในเครื่องหมายคำพูดจะไม่ปรากฏในตัวเลือก Parameter ของ Load Excel อีก จึงต้องใช้ IN list หรือ Auto WHERE แทน ซึ่งเป็น regression ที่เกิดจากการทำตาม spec
   - แนวทางแก้: ให้ผู้ใช้ตัดสิน; ถ้าต้องการคงพฤติกรรมเดิม ให้นับ string token ที่เนื้อหา**ทั้งหมด**เป็น placeholder พอดี (`':name'` หรือ `'{name}'`) เป็น placeholder ส่วน `'text {x}'` ยังข้ามตามเดิม

## 🟢 Suggestion (ทางเลือก)
1. [database_connect_gui.py:11045-11047] `update_profile_list()` (`:10848`) เรียก `update_jobs_list()` อยู่แล้ว จึงสร้าง Job cards ซ้ำสองรอบต่อการ Save Profile หนึ่งครั้ง ไม่ผิด แต่สิ้นเปลือง
2. [database_connect_gui.py:9038-9045] `getattr(self, "db_user", None).get() if getattr(self, "db_user", None) else ""` อ่านยาก และอาศัยค่า truthiness ของ widget; ใช้ `self.db_user.get()` ตรง ๆ เหมือน `self.db_name.get()` ในบรรทัดก่อนหน้าได้
3. [database_connect_gui.py:74-79] `write_json_atomic` ไม่ลบไฟล์ `<path>.tmp` เมื่อ `os.replace` ล้มเหลว (เช่น preset ถูกล็อกใน M-5) จึงเหลือไฟล์ค้าง ไฟล์เดิมยังปลอดภัย และ Load Preset ไม่หยิบไฟล์นี้เพราะกรอง `.json`
4. [database_connect_gui.py:13283] ตัวเลือก "First IN (...) list" ยังตัดสินด้วย regex บน SQL ดิบ เมื่อ `IN (` อยู่เฉพาะใน comment/string ผู้ใช้จะเห็นตัวเลือกนี้ แล้วจึงเจอ `ValueError` ของ H-2 ตอน render ควรใช้ token จาก `_scan_sql` ให้สอดคล้องกัน
5. [database_connect_gui.py:11535-11547] การแทนค่า `:name` / `{name}` ยังใช้ `re.subn` บน SQL ดิบ จึงแทนค่าใน comment หรือ string ที่มีชื่อเดียวกันด้วย (อยู่นอกขอบเขต M-1 ซึ่งระบุเฉพาะการตรวจหา)
6. [database_connect_gui.py:10514] `len(value) > 32767` นับเป็น code point ส่วน Excel นับเป็นหน่วย UTF-16 ข้อความที่มีอักขระนอก BMP (เช่น emoji) อาจเกิน limit แม้ผ่านการตรวจนี้
7. Test:
   - `tests/test_bugfix_c1.py:170` ใช้ `messagebox.assert_not_called()` บน mock ของทั้งโมดูล ซึ่งไม่จับการเรียก `messagebox.showerror(...)`; ควรตรวจ `messagebox.method_calls == []`
   - `tests/test_bugfix_m1.py:14-24` ทดสอบ `HH24:MI:SS` เฉพาะในรูป string literal; ควรเพิ่มรูปที่ไม่มี quote ด้วย (ตอนนี้ implementation ผ่านแล้ว)
   - `tests/test_bugfix_c3.py:18-35` ดึง `clean_value` ด้วย AST แล้ว exec ใหม่ ทำให้ test เปราะเมื่อ closure เปลี่ยน (เช่นถ้าเพิ่ม free variable ใหม่); test ใน `test_bugfix_c2.py` ที่รัน export จริงเชื่อถือได้มากกว่า

---

# Code Review — Round 6 — 2026-11-16

ขอบเขต: Import Groups ต้องไม่รายงานสำเร็จเมื่อบันทึก `script_groups.json` ไม่สำเร็จ (R6-AC-1 ถึง R6-AC-13)
ไฟล์ที่ตรวจ: `database_connect_gui.py:4392-4416` (`save_script_groups`), `:4492-4534` (`import_script_groups`), `tests/test_script_groups_block.py:154`, `tests/test_r3_script_groups_io.py:876`, `tests/test_r6_import_save_failure.py` (ใหม่, 36 tests)
ผลรันจริงของ reviewer: `PYTHONIOENCODING=utf-8 python -m unittest discover -s tests -p "test_*.py"` ได้ Ran 878 tests OK; `tests.test_r6_import_save_failure` ได้ 36 OK (error ของ `test_bugfix_h3` เมื่อไม่ใช้ UTF-8 คือ Round 5 🟡-1 จึงไม่นับซ้ำ)

## สรุป
**ผ่าน** — 🔴 0, 🟡 0, 🟢 3

ตรวจแล้วตรงกับ design R6-D4 ทุกข้อ:
- `save_script_groups` มี type hint `-> bool`, คืน `False` ที่ `:4400` (blocked) และ `:4415` (except ครอบทั้ง `_backup_script_groups_once` และ `write_json_atomic`), คืน `True` ที่ `:4416`; ข้อความ, title และจำนวนครั้งของ `showerror` เหมือนเดิม
- `import_script_groups` สร้าง snapshot ด้วย `copy.deepcopy` ที่ `:4524` หลัง `if replace is None` และก่อน `merge_imported_script_groups` (Cancel, ไฟล์ผิด และไม่มี Profile จึงไม่ทำ snapshot และไม่ save); ใช้ `if not self.save_script_groups():` (Mock เปล่าที่เป็น truthy ยังนับเป็นสำเร็จ); rollback แบบ in-place `self.script_groups[:] = snapshot` ที่ `:4528` แล้วเรียก refresh ด้วย `None` ที่ `:4529` **หลัง** rollback และ `return None` ก่อนถึงบรรทัด log `📥 Imported`; ทางสำเร็จยังเป็นลำดับ save → refresh(last_name) `:4531` → log → see → return เหมือนเดิม
- `import copy` มีอยู่แล้วที่ `:3`
- Callers อื่นของ `save_script_groups()` ใน `show_script_groups_dialog` (`:5047, 5061, 5077, 5090, 5111, 5127, 5143, 5156`) ไม่ได้แก้โค้ด และไม่มีตัวไหนใช้ค่าคืน เดิมได้ `None` ตอนนี้ได้ `bool` ที่ไม่ถูกใช้ จึงไม่มีพฤติกรรมเปลี่ยน; `import_groups` ในหน้าต่าง (`:5184`) และ `sidebar_import_script_groups` (`:4583`) เรียกตัวเดียวกัน ตัว sidebar ส่งค่าคืนต่อไปตรง ๆ จึงได้ `None` เมื่อล้มเหลว
- Rollback คืน dict ของกลุ่มเป็นสำเนา (deep copy) ไม่ใช่ object เดิม ตรวจแล้วไม่มีส่วนไหนถือ reference ข้ามการ import: `refresh_groups` (`:4964`) สร้าง `state["groups"]` ใหม่จาก `self.script_groups` และ `group_jobs` (`:5158-5160`) สร้างสำเนาของ script ก่อนรันทุกครั้ง

## R6-AC Verdict
| AC | ผล | หลักฐาน |
|---|---|---|
| R6-AC-1 | ✅ ผ่าน | โค้ด `:4394-4400`; test `test_blocked_returns_false` ตรวจ `assertIs(False)`, ข้อความเต็ม, `write_json_atomic`/`copy2` ไม่ถูกเรียก, ไฟล์ไม่เปลี่ยน; `test_script_groups_block.py:154` เปลี่ยนเป็น `assertIs(..., False)` |
| R6-AC-2 | ✅ ผ่าน | `:4410-4415`; test ครอบ `OSError` จาก `write_json_atomic`, `os.replace` จริงล้มเหลว, `shutil.copy2` ของ backup ล้มเหลว, `_backup_script_groups_once` raise และ exception ที่ไม่ใช่ OSError พร้อมตรวจข้อความและไฟล์บนดิสก์ |
| R6-AC-3 | ✅ ผ่าน | `:4416`; `test_success_returns_true_and_content` เทียบเนื้อหาไฟล์ที่ตัด `_*`/`run_index` และยืนยันว่าข้อมูลในหน่วยความจำไม่ถูกตัด |
| R6-AC-4 | ✅ ผ่าน | `test_blocked_noclash` + `assert_rolled_back` (ใช้ `save_script_groups` จริง, ข้อมูลมี Profile อื่นและค่าซ้อน dict/list) |
| R6-AC-5 | ✅ ผ่าน | `test_write_failure_noclash` ตรวจข้อความ error และ `assert_disk_unchanged` (ไม่มีไฟล์ `.tmp` ค้าง) |
| R6-AC-6 | ✅ ผ่าน | `test_yes_replaced_groups_restored_in_place` ทั้ง blocked และ write ตรวจลำดับ (name, profile) และว่าไม่เหลือ `IMPORTED*` |
| R6-AC-7 | ✅ ผ่าน | `test_no_keep_both_renamed_copies_removed` + รายชื่อ leftover ใน `test_matrix_modes_and_answers` |
| R6-AC-8 | ✅ ผ่าน | `assert_rolled_back` ตรวจ `insert`/`see`/`showinfo` ไม่ถูกเรียก, `showerror` 1 ครั้ง, save 1 ครั้ง; `test_sidebar_returns_none` ครบ 3×3 กรณี |
| R6-AC-9 | ✅ ผ่าน | `test_refresh_once_with_none_after_rollback` ถ่ายสถานะใน callback ตอนถูกเรียก (เท่ากับ snapshot และเป็น list เดิม) + `assert_called_once_with(None)`; `test_refresh_after_save_not_before`; `test_window_closed_no_error` ครอบกรณีหน้าต่างปิด, ไม่มี และ `winfo_exists` เป็น False |
| R6-AC-10 | ✅ ผ่าน | `:4528` slice assignment; `assertIs(self.stub.script_groups, self.sg_ref)` ใน `assert_rolled_back` ทุกกรณี |
| R6-AC-11 | ✅ ผ่าน | `TestImportSuccessUnchanged` ใช้ save จริงบน tempdir ตรวจลำดับ `["save", ("refresh", last), "log"]`, ข้อความ log ตรงตัว และผล merge ของกรณีไม่ชน, Yes และ No; `test_r3_script_groups_io.py:876` แก้เฉพาะค่าคืน (`or True`) ส่วน assertion คงเดิม |
| R6-AC-12 | ✅ ผ่าน | test เดิม R3 ยังผ่าน + `TestNoSaveOnEarlyExit` (Cancel ไม่เรียก `deepcopy`, ไฟล์ผิด, ไม่มี Profile, ตอบ No ตอนยืนยัน) |
| R6-AC-13 | ✅ ผ่าน | 878 tests OK (UTF-8) |

Test ไม่ได้ผ่านแบบไม่ได้ตรวจอะไร: ทางล้มเหลวใช้ `save_script_groups` จริง (spy แบบ `wraps`) ไม่ได้ mock ให้คืน `False` ตรง ๆ จึงทดสอบการเชื่อมกันจริงของสองเมธอด และ `test_falsy_none_save_is_failure` / `test_truthy_mock_save_still_success` ล็อกพฤติกรรม `if not ...` ไว้

## 🔴 Critical (ต้องแก้ก่อน merge)
- ไม่มี

## 🟡 Warning (ควรแก้)
- ไม่มี

## 🟢 Suggestion (ทางเลือก)
1. [tests/test_r6_import_save_failure.py:323, :349, :363, :385, :397, :434] เรียก `self.setUp()` ซ้ำภายในลูป `subTest` ทำให้ patch (`APP_DIR`, `messagebox`, `filedialog`) และ TemporaryDirectory ซ้อนกันหลายชั้นจนจบ test ตอนนี้ยังถูกต้องเพราะ cleanup ทำงานแบบ LIFO และ `self.mb`/`self.stub` ถูกแทนด้วยตัวใหม่ทุกรอบ แต่ถ้าในอนาคตมีคนเพิ่ม patch ที่ไม่ได้ลงทะเบียน `addCleanup` ไว้ จะรั่วข้ามรอบได้ ควรแยกเป็น helper `_fresh()` หรือแยกเป็นเมธอด test ต่อกรณี
2. [database_connect_gui.py:4524-4528] หลัง rollback กลุ่มทุกตัวเป็นสำเนาใหม่ (identity เปลี่ยน แต่ค่าเท่าเดิม) ตอนนี้ไม่มีผลเพราะไม่มีโค้ดไหนถือ reference ของ dict กลุ่มข้ามการ import ถ้าต้องการรักษา identity ด้วย ใช้ `snapshot = list(self.script_groups)` ก็พอ เพราะ `merge_imported_script_groups` (`:968-1003`) แค่ `remove`/`append` ไม่ได้แก้ dict ของกลุ่มเดิม แต่ spec R6-5 กำหนดให้ใช้ deepcopy ไว้แล้ว จึงเป็นทางเลือกเท่านั้น
3. [database_connect_gui.py:5047-5156] (รับทราบตาม design R6-R5 ซึ่งอยู่นอก scope) callers อื่นในหน้าต่าง Script Groups ยังไม่ตรวจค่าคืนของ `save_script_groups()` ปัญหาเดียวกัน (ข้อมูลในหน่วยความจำไม่ตรงกับไฟล์เมื่อบันทึกไม่สำเร็จ) จึงยังเกิดได้กับ Add, Rename, Delete Group และการแก้ script ตอนนี้ค่าคืน `bool` พร้อมใช้แล้ว ถ้าผู้ใช้ต้องการให้แก้ ให้เปิดเป็น Round ถัดไป

---

# Code Review — Round 7 — 2026-11-16

ขอบเขต: R7-1 ถึง R7-5 (R7-AC-1 ถึง R7-AC-28) เท่านั้น ไม่ตรวจซ้ำ Round ก่อนหน้า
ไฟล์ที่ตรวจ: `database_connect_gui.py` — `_excel_text_too_long` (`:123-134`), `_SQL_COLON_PLACEHOLDER_RE` + `_detect_sql_placeholders` (`:470-519`), `save_or_rollback` + 8 action (`:5053-5226`), `run_job` (`:9703-9720`), worker ของ `export_jobs_to_excel` (`:10394-10453`, `:10500-10518`, `:10529-10558`, `:10619-10634`, `:10661-10668`, `:10719-10746`), `save_profiles` (`:10897-10918`); test `tests/test_r7_console_print.py`, `tests/test_r7_run_job_legacy_profile.py`, `tests/test_r7_excel_cell_limit.py`, `tests/test_r7_quoted_placeholder.py`, `tests/test_r7_script_groups_dialog_rollback.py`, `tests/test_bugfix_m1.py:21-24`

สิ่งที่ reviewer รันจริง (stdout เป็น pipe, encoding `cp874`, **ไม่** ตั้ง `PYTHONIOENCODING`):
- Focused: 4 ไฟล์ `test_r7_*` ที่มีอยู่ + `test_bugfix_m1/h3/c1/c2/m2/h2`, `test_r4_excel_row_limit`, `test_r4_profile_mismatch`, `test_r6_import_save_failure`, `test_script_groups_block`, `test_r3_script_groups_io` → **Ran 304, OK**; `test_database_connect_gui_core` → Ran 75, OK (`test_bugfix_h3...test_save_profiles_returns_false_when_write_raises` ที่เคย error ใน Round 5 🟡-1 ผ่านแล้วใน mode นี้)
- ไม่ได้รันทั้งชุด (QA กำลังรันอยู่) — R7-AC-28 จึงรอผล R7-T8
- `tests/test_r7_script_groups_dialog_rollback.py` (QA เขียนเสร็จระหว่าง review) → **Ran 53, OK** (ราว 27 วินาที, Tk จริง) รอบแรกที่ reviewer รันขณะ QA ยังแก้ไฟล์อยู่มี 1 failure ที่ assertion การเลือกกลุ่มของ harness ใน `test_other_profile_group_is_never_touched` (ไม่ใช่โค้ดแอป) และผ่านหลัง QA แก้ test
- ก่อนไฟล์ test ข้างต้นจะเสร็จ reviewer ตรวจ R7-5 แยกต่างหากด้วย probe ชั่วคราวนอก repo (Tk จริงแบบ `withdraw()`, `APP_DIR` = tempdir, กดปุ่มด้วย `invoke()`) ครบ 8 action (`move_script` ทั้ง ↑ และ ↓) × ล้มเหลว 2 แบบ (`_script_groups_save_blocked` / `write_json_atomic` raise) + ทางสำเร็จ: ผลตรงกับ test ของ QA

## สรุป
**ผ่าน** — 🔴 0, 🟡 0, 🟢 6

ประเด็นที่หัวหน้าขอให้ตรวจเป็นพิเศษ:
- **จุด snapshot ของ 8 action**: ถูกทุกตัว — อยู่หลังทาง cancel / ชื่อซ้ำ / `askyesno` / ขอบเขต และก่อนการแก้ข้อมูลบรรทัดแรก: `new_group` `:5081` (ก่อน `append` `:5082`), `rename_group` `:5106` (ก่อน `:5107`), `delete_group` `:5126` (ก่อน `remove` `:5127`), `add_sql` `:5143` (หลัง `result["created"]` ซึ่งแก้เฉพาะ dict ใหม่ที่ยังไม่อยู่ใน `self.script_groups`, ก่อน `append` `:5144`), `add_from_jobs` `:5163` (ก่อน loop `:5164`), `edit_script` `:5185` (ก่อน `script.pop` `:5186`), `delete_script` `:5206` (ก่อน `del` `:5207`), `move_script` `:5222` (ภายใน `if 0 <= target < len(scripts)`, ก่อนสลับ `:5223`) และ `_edit_group_script_dialog` (`:4673-4790`) อ่าน `script` อย่างเดียว ไม่แก้ก่อนคืนค่า snapshot จึงเป็นสถานะก่อนแก้จริง
- **Rollback in-place**: `self.script_groups[:] = snapshot` ที่ `:5061` (list object เดิม) ใช้ `if self.save_script_groups():` แบบ truthy ตาม R7-AC-27
- **refresh_groups + คืนการเลือก**: `:5062` เรียก `refresh_groups(select_name=...)` เสมอ (สร้าง `state["groups"]` ใหม่จากข้อมูลหลัง rollback จึงไม่เหลือ dict ค้าง) แล้ว `refresh_scripts(select_index=...)` ที่ `:5063-5064`; `prev_name` ของทุก action จับก่อนแก้ (`rename_group` `:5104` จับก่อน `:5107` ตาม R7-R4)
- **Warning นับครั้งเดียว**: ค่าคืนของ `append_sql_annotation` ถูก OR เข้า `job_warning` ที่ `:10663-10664` และ `warnings += 1` ของ Job ที่มีข้อมูลมีจุดเดียวที่ `:10719-10720`; No Data นับที่ `:10553-10556` แล้ว `continue` จึงไม่ผ่าน `:10719` ซ้ำ; รันจริงกรณี cell ผลลัพธ์เกิน + บรรทัด SQL เกินใน Job เดียว → `Warning: 1`, `Status: ⚠️ Warning` 1 บรรทัด
- **ตัวนับ Skipped / Failed ไม่เปลี่ยน**: `skipped += 1` `:10500` และ `failed += 1` `:10727` อยู่ที่เดิม `blank_oversized_cells` (`:10419-10430`) แค่ log และแทนค่าเป็น `""` ไม่แตะตัวนับ; รันจริง Skipped ที่ `Query` เกิน → `Skipped: 1, Warning: 0`; Failed ที่ `Error`/`Query` เกิน → `Failed: 1, Warning: 0`
- **M-1 ยังอยู่**: กิ่ง string (`:483-492`) รับเฉพาะ literal `'...'` ที่ `fullmatch` placeholder หนึ่งตัวพอดี; รันจริง `'HH24:MI:SS'`, `'text {x}'`, `'a :ACC'`, `' :ACC'`, `':ACC '`, `':ACC:B'`, `'::x'`, `':1'`, `''`, `'it''s :ACC'`, comment, `":ACC"`, `$$:ACC$$`, literal ที่ไม่ปิด → `[]`; `value::type` และกิ่ง `punct` เดิม (`:493-517`) ไม่ถูกแก้
- **นอก Round 7**: diff ทั้งไฟล์ยังรวมทุก Round ที่ยังไม่ commit จึงแยก diff ราย Round ไม่ได้ reviewer ใช้เลขบรรทัดที่ design R7 บันทึกไว้เทียบกับปัจจุบันแทน: ส่วนเลื่อนสะสมตรงกับจำนวนบรรทัดที่ R7 เพิ่มทุกช่วง (+25 ก่อน `show_script_groups_dialog`, +69 ที่ `run_job`, +113 ที่ `save_profiles`, +116 หลังจากนั้น) ไม่พบการเพิ่ม/ลบบรรทัดนอกจุดแก้ 5 จุด (วิธีนี้ไม่จับการแก้ข้อความภายในบรรทัดเดิมนอกจุดที่อ่าน); `save_jobs` (`:9547-9561`), `save_script_groups` (`:4417-4441`), `_profiles_save_refused` (`:10874`), `_render_sql_template` (`:11610-11665`), `write_literal_cell` / `force_literal_strings` (`:10394-10407`), `job.get("profile")` ที่ Save Preset (`:5322`) อ่านแล้วเป็นไปตาม design และไม่มี `print` เพิ่มใน failure path ของสามฟังก์ชัน save

## Verdict ราย R7-AC

| AC | ผล | หลักฐาน |
|---|---|---|
| R7-AC-1 | ✅ ผ่าน | `:10911-10918` ครอบ `print` ด้วย `try/except Exception: pass` แล้ว `showerror("Save Error", error_msg)` + `return False` ตามเดิม; `test_r7_console_print.py:85-95` (cp874 strict: `assertIs False`, ข้อความเต็ม, ไฟล์บนดิสก์ไม่เปลี่ยน) และ `:56-62` ยืนยันว่า fixture ทำให้ `print` พังจริง |
| R7-AC-2 | ✅ ผ่าน | subTest `oserror` / `none` ที่ `:45-50`, `:85-100` |
| R7-AC-3 | ✅ ผ่าน | ไม่มี `print` ใน `save_jobs`, `save_script_groups`, `_profiles_save_refused`; test `:135-197` ครบ 5 กรณี และตรวจว่าไม่มี byte ใดถูกเขียนลง stdout |
| R7-AC-4 | ✅ ผ่าน | `:200-261` ใช้ `save_profiles` จริง: `delete_profile` และ `do_import` (merge / replace) rollback, `showerror` 1 ครั้งเป็น `"Save Error"` (ไม่ใช่ dialog จาก except ทั่วไปของ `do_import`), ไม่มี success |
| R7-AC-5 | ✅ ผ่าน | `:103-132` `io.StringIO` ยังได้ `error_msg`; ทางสำเร็จคืน `True` และ stdout ว่าง |
| R7-AC-6 | ✅ ผ่าน | `:9708-9710` `job.get("profile", selected_profile)`; `test_r7_run_job_legacy_profile.py:60-94` (ไม่มี `⛔`, `_capture_run_target` / `_block_if_profile_mismatch` ถูกเรียก, เทียบผลกับ Job ที่ `"profile": "P1"`, ไปถึง confirmation) |
| R7-AC-7 | ✅ ผ่าน | ข้อความ `⛔` `:9711-9717` เดิม; test `:98-113`; `tests/test_bugfix_c1.py` ผ่านโดยไม่แก้ |
| R7-AC-8 | ✅ ผ่าน | matrix `:134-154` เทียบกับ `_current_profile_jobs()` จริง รวมกรณี `"profile": None` (ปฏิเสธ และไม่อยู่ใน list — สอดคล้องกัน) |
| R7-AC-9 | ✅ ผ่าน | `:10504-10517`; รันจริง: `Query` ว่าง, `Status`/`Message` เดิม, log `Job '<name>', column 'Query' ... 32,767`, `Skipped: 1`; test `SkippedSheetLimitTests` (ASCII / ไทย / emoji) |
| R7-AC-10 | ✅ ผ่าน | `:10739-10746` อยู่หลัง log `Error :` เดิม (`:10734`); log แยกราย column; `Failed: 1`; test `FailedSheetLimitTests` 5 กรณี (ดู 🟢-1) |
| R7-AC-11 | ✅ ผ่าน | `:10541-10556` ใช้ `start_row + line_no` เดิม บรรทัดอื่นอยู่แถวเดิม (เริ่มแถว 3); รันจริง `Warning: 1, Success: 0`; หลายบรรทัดเกินใน Job เดียวยังนับ 1 (`NoDataSheetLimitTests`) |
| R7-AC-12 | ✅ ผ่าน | `:10432-10453`, `:10661-10664`, `:10719-10721`; รันจริงและ `test_oversized_result_cell_and_sql_line_count_one_warning` ยืนยัน Warning 1 ครั้ง; ทาง "worksheet เต็ม" และ "ไม่มีบรรทัด" คืน `False` |
| R7-AC-13 | ✅ ผ่าน | 32,767 units (ASCII / ไทย / `"😀" * 16383 + "a"`) เขียนครบไม่มี warning ทุกตำแหน่ง; 32,768 → ว่าง + warning (helper tests + export tests ทุก sheet) |
| R7-AC-14 | ✅ ผ่าน | `:10623` ใช้ `_excel_text_too_long`; `"😀" * 16384` → `True`, `"😀" * 16383 + "a"` → `False` (รันจริงและ `ResultCellLimitTests`) |
| R7-AC-15 | ✅ ผ่าน | ไม่มีค่าเกิน: `blank_oversized_cells` คืน dict ลำดับ key เดิม, DataFrame เท่าเดิม, `force_literal_strings` เรียกต่อ; test `test_short_*` ตรวจ `data_type == "s"` กับค่าที่ขึ้นต้น `=`; `test_bugfix_c2` / `test_bugfix_m2` ผ่านโดยไม่แก้; ข้อความ log C-2 เดิม (`:10629-10634`) ไม่เปลี่ยน |
| R7-AC-16 | ✅ ผ่าน | `:483-492` append `inner` (ไม่มี quote); รันจริงได้ `[":ACC"]`, `["{acc}"]`, `["{{ ACC }}"]` |
| R7-AC-17 | ✅ ผ่าน | ดูหัวข้อ "M-1 ยังอยู่"; `LongerLiteralNotDetectedTests` ครอบรายการใน AC ครบและเพิ่มกรณี `':'`, `'{}'`, `'{1}'`, escaped quote, ขึ้นบรรทัดใหม่ |
| R7-AC-18 | ✅ ผ่าน | `dict.fromkeys` `:519` + token เดินตามตำแหน่ง; `DuplicateAndOrderTests` ทั้ง bare→quoted และ quoted→bare |
| R7-AC-19 | ✅ ผ่าน | รันจริง detect → `_render_sql_template` ได้ `WHERE a IN ('1')` ทั้ง `':ACC'` และ `'{ACC}'`; `_render_sql_template` ไม่ถูกแก้ |
| R7-AC-20 | ✅ ผ่าน | `tests/test_bugfix_m1.py:21-24` ค่าคาดหวังเป็น `[":real_bind", "{braced}", "{{double_braced}}", ":literal"]` ตรงตาม AC; SQL ของ test ยังมี `'HH24:MI:SS'`, `'text {not_a_bind}'`, comment และ `value::type` |
| R7-AC-21 | ✅ ผ่าน | `FailedSaveRollsBackTests` (8 action × 2 แบบ, 18 tests) + probe: ทุก action × 2 แบบล้มเหลว → `script_groups == snapshot`, `is` list เดิม, `save_script_groups` 1 ครั้ง, ไฟล์บนดิสก์ไม่เปลี่ยน (ข้อมูลมีกลุ่มของ Profile อื่นและค่าซ้อน dict / list) |
| R7-AC-22 | ✅ ผ่าน | `assert_window_shows` ใน `press_expecting_rollback` + `FailedSaveSelectionEdgeTests` (script สุดท้าย, กลุ่มไม่มี script, Profile ไม่มีกลุ่ม); probe: groups / scripts listbox ตรง snapshot; การเลือกหลัง rollback = กลุ่มเดิม (index 1 ไม่ใช่ค่า default 0) และ script index เดิม (1) ทุก action รวม `rename_group`, `delete_group` (กลุ่มที่ลบกลับมาและถูกเลือก) และ `new_group` (คงกลุ่มเดิม) ตาม R7-Q-4 |
| R7-AC-23 | ✅ ผ่าน | `press_expecting_rollback` ตรวจ `showerror` 1 ครั้ง title `"Script Groups"`, ไม่มี `showinfo` / `showwarning`; probe: `showerror` 1 ครั้ง (จาก `save_script_groups`), `showinfo` 0, ไม่มี exception; `save_or_rollback` ไม่เพิ่ม dialog / log |
| R7-AC-24 | ✅ ผ่าน | `ActionAfterRollbackTests` (Rename ล้มเหลว → Edit ล้มเหลว → ปลดสาเหตุ → Add SQL; ตรวจไฟล์, identity ของ dict กลุ่ม และหน่วยความจำ == ไฟล์); probe: หลัง action ที่ล้มเหลวทุกตัว ปลดสาเหตุแล้ว `＋ Add SQL` สำเร็จ → script ใหม่อยู่ในกลุ่มชื่อเดิมทั้งในไฟล์และหน่วยความจำ (ไม่ได้แก้ dict ค้าง) |
| R7-AC-25 | ✅ ผ่าน | `SuccessfulSaveTests` 10 tests; บรรทัด refresh ทางสำเร็จเป็นไปตาม design (`:5092`, `:5110`, `:5130`, `:5147-5148`, `:5172-5173`, `:5191`, `:5210-5211`, `:5226`); probe: new/rename เลือกชื่อใหม่, add เลือก script สุดท้าย, edit เลือก index เดิม, move เลือก index ปลายทาง, save 1 ครั้ง, ไม่มี `showerror` |
| R7-AC-26 | ✅ ผ่าน | ทุก `return` ของทางยกเลิกอยู่ก่อนบรรทัด snapshot (ดูหัวข้อจุด snapshot); `CancelledActionTests` 13 tests ตั้ง `_script_groups_save_blocked = True` ไว้ล่วงหน้าและตรวจว่า `save_script_groups` ไม่ถูกเรียกเลย (ชื่อว่าง, ชื่อซ้ำ, ไม่มี Profile, `askyesno` = No, dialog คืนค่าว่าง, ไม่มี Job, move เกินขอบ) |
| R7-AC-27 | ✅ ผ่าน (ส่วนที่ตรวจได้) | `TruthySaveResultTests` (`mock.Mock()` เปล่าเป็นทางสำเร็จทุก action); `test_r3_script_groups_io`, `test_script_groups_block`, `test_r6_import_save_failure` ผ่านในรอบ focused ของ reviewer; implementation ใช้ truthiness (`:5059`) |
| R7-AC-28 | ⏳ รอ QA (R7-T8) | reviewer รัน focused 304 + 75 + 53 tests ใน mode (ข) ได้ OK; ผลทั้งชุดสอง mode และจำนวน test ที่เท่ากันต้องมาจาก R7-T8 |

## 🔴 Critical (ต้องแก้ก่อน merge)
- ไม่มี

## 🟡 Warning (ควรแก้)
- ไม่มี

## 🟢 Suggestion (ทางเลือก)
1. [database_connect_gui.py:10739-10742] sheet Failed อาจเหลือแค่คำว่า `Failed`: ถ้าข้อความ error ของ driver / SQLAlchemy แนบ SQL ทั้งก้อนมาด้วย (รูป `[SQL: ...]`) Job ที่ล้มเหลวและมี SQL ยาวเกิน limit (เช่น IN list หลายพันค่า) จะได้ `Error` เกิน limit พร้อมกับ `Query` และถูกเว้นว่างทั้งคู่ ผู้ที่เปิด workbook จะไม่เห็นสาเหตุ (ยังดูได้จาก Execution Logs ที่ `:10734` และมี log warning ราย column) reviewer ไม่ได้ทดสอบกับฐานข้อมูลจริง จึงยังไม่ยืนยันว่าข้อความ error จริงยาวเท่าใด พฤติกรรมนี้ตรงกับ R7-AC-10 ที่ผู้ใช้อนุมัติ จึงไม่ใช่ข้อบกพร่อง ถ้าต้องการให้ workbook บอกสาเหตุได้ ให้ถามผู้ใช้ว่าจะตัด `Error` ให้เหลือ 32,767 แทนการเว้นว่างเฉพาะ column นี้หรือไม่ (เป็นงาน Round ถัดไป)
2. [database_connect_gui.py:483-492 กับ :13395-13398] (รับทราบตาม design R7-R10) เมื่อ template มี literal รูป `':X'` / `'{X}'` ที่ผู้ใช้ตั้งใจให้เป็นข้อมูลจริง เช่น `WHERE flag = ':N' AND acc IN (...)` ตัวเลือก Parameter ของ Load Excel จะเป็น `:N` + Auto WHERE และตัวเลือก `acc IN (...)` หายไป เพราะ `:13395` ใช้ placeholder ก่อน IN list เสมอ เป็นผลที่ design บันทึกว่าผู้ใช้อนุมัติแล้ว บันทึกไว้เผื่อมีรายงานจากผู้ใช้ภายหลัง
3. [database_connect_gui.py:519 กับ :11651-11663] ชื่อเดียวกันที่ต่างตัวพิมพ์ (`':acc'` กับ `:ACC` — รันจริงได้ `[':acc', ':ACC']`) ถูกคืนเป็นสองตัวเลือก ทั้งที่ `_render_sql_template` แทนค่าแบบ `re.IGNORECASE` เป็นพฤติกรรมเดิมของรูปไม่มี quote ตั้งแต่ M-1 (ไม่ได้เกิดจาก R7) และ R7-AC-18 กำหนดเฉพาะชื่อที่ตรงกันทุกตัวอักษร
4. [database_connect_gui.py:474, :10420, :10432] คุณภาพเล็กน้อย: docstring ของ `_detect_sql_placeholders` ยังเขียนว่า "excluding comments and literals" ซึ่งไม่ตรงแล้ว (literal ที่เป็น placeholder ทั้งตัวถูกนับ); docstring ของ `blank_oversized_cells` ยาวเกิน 100 ตัวอักษร; `append_sql_annotation(ws, sql_text, job_name: str)` มี type hint ไม่ครบทุก parameter
5. [database_connect_gui.py:5062-5064] `refresh_groups` เรียก `refresh_scripts()` อยู่แล้ว (`:5000`) ตามด้วย `refresh_scripts(select_index=...)` อีกครั้ง scripts listbox จึงถูกวาดสองรอบต่อ rollback หนึ่งครั้ง ผลลัพธ์ถูกต้องและเกิดเฉพาะทางล้มเหลว ไม่จำเป็นต้องแก้
6. Test:
   - `tests/test_r7_run_job_legacy_profile.py:113` ใช้ `messagebox.assert_not_called()` บน mock ของทั้งโมดูล ซึ่งไม่จับการเรียก `messagebox.showerror(...)` (ประเด็นเดียวกับ Round 5 🟢-7); ควรตรวจ `messagebox.method_calls == []`
   - `tests/test_r7_console_print.py:97-100` ซ้ำกับ subTest `none` ที่ `:85-95`
   - `tests/test_r7_script_groups_dialog_rollback.py:99-150` สร้าง `DatabaseConnectorGUI` + Tk root ใหม่ทุก test (53 tests ใช้ราว 27 วินาที จากทั้งชุดที่เดิมใช้ไม่กี่วินาที) ถูกต้องและแยก state ได้ดี ถ้าเวลารันกลายเป็นปัญหาค่อยพิจารณาใช้ root ร่วมกันต่อ class

---

# Code Review — Round 8 (Bugfix B1: `load_jobs` write-back) — 2026-11-20

ขอบเขต: R8-T1 / R8-T2 (R8-AC-1 ถึง R8-AC-15) เท่านั้น ไม่ตรวจซ้ำ Round ก่อนหน้า
ไฟล์ที่ตรวจ: `database_connect_gui.py` — `load_jobs` (`:9482-9533`, hunk เดียวของ `git diff` ที่ `:9509-9533`); test ใหม่ `tests/test_r8_load_jobs_writeback.py` (437 บรรทัด, 18 tests); อ่านประกอบ `write_json_atomic` (`:71-79`), `save_jobs` (`:9559-9573`), `__init__` (`:2372-2374`)

สิ่งที่ reviewer รันจริง (stdout เป็น pipe, encoding `cp874`, **ไม่** ตั้ง `PYTHONIOENCODING`):
- Focused ตามที่หัวหน้ากำหนด: `python -m unittest tests.test_r8_load_jobs_writeback tests.test_r2_reset_parameter_qa tests.test_bugfix_h3 tests.test_r7_console_print` → **Ran 86, OK** (ตรงกับผล QA)
- ไม่รันทั้งชุด — ผู้ใช้สั่งเลื่อน (R8-T3)

## สรุป
**ผ่าน** — 🔴 0, 🟡 0, 🟢 4

ประเด็นที่หัวหน้าขอให้ตรวจเป็นพิเศษ:
- **`jobs` / `modified` ถูกกำหนดก่อนใช้ทุกเส้นทาง**: ไฟล์ไม่มีอยู่ → `return []` ที่ `:9485-9486` ก่อนถึง `try`; ทางอ่านสำเร็จ → `jobs` กำหนดที่ `:9492` และ `modified = False` ที่ `:9497` ก่อน loop ทั้งคู่อยู่ใน `try` เดียวกัน; exception ใด ๆ (`Exception`) ก่อน `:9497` ตกไป `except` ที่ `return []` (`:9512-9515`) จึงไม่มีทางมาถึง `if modified:` (`:9518`) โดยที่ตัวแปรยังไม่ถูกกำหนด; `BaseException` (เช่น `KeyboardInterrupt`) หลุดออกจากฟังก์ชันทั้งหมดเหมือนก่อนแก้
- **`except` เดิมไม่เปลี่ยน**: diff แสดง `except Exception as e:` / `print(f"Error loading jobs: {e}")` / `_handle_unreadable_file(...)` / `return []` เป็นบรรทัด context (ไม่มี `-`/`+`) และ loop เติม `"profile"` (`:9499-9510`) ไม่ถูกแตะ; การเปลี่ยนแปลงมีแค่ย้าย `if modified:` + `return jobs` ออกหลัง `except` และเพิ่ม `try` ใหม่ ตรง R8-D2 (ใช้ `os.remove` ตาม R8-R2, ไม่แตะ `write_json_atomic` / loader อื่น / `save_jobs` ตาม R8-R1)
- **ไม่มีทางที่ Job หาย**: หลังอ่านสำเร็จ ทุกเส้นทางจบที่ `return jobs` (`:9533`) — `try` ใหม่จับ `Exception` จาก `write_json_atomic`, ส่วน cleanup และ `print` มี guard ของตัวเองแยกกัน จึงไม่มี exception จากทางเขียนกลับไปถึง `_handle_unreadable_file` / `return []` ได้อีก; `_jobs_save_blocked` ไม่ถูกตั้งในทางนี้ (ใน `__init__` ไม่เคยตั้งค่า แต่ `save_jobs` ใช้ `getattr(..., False)` `:9561`) → `save_jobs()` ครั้งถัดไปเขียน `self.saved_jobs` ที่ migrate แล้วครบ; ไฟล์บนดิสก์ไม่ถูกแตะเพราะ `write_json_atomic` เขียนลง `.tmp` ก่อน `os.replace` เสมอ และ cleanup ลบเฉพาะ `<jobs_file>.tmp`
- **Test assert ผลจริงและไม่ pin พฤติกรรมผิด**: assert ค่าคืนเทียบ `expected_jobs()` ทั้ง list (ลำดับ + ค่าซ้อน + ไทย), bytes ไฟล์ก่อน/หลัง, `os.listdir`, `_jobs_save_blocked is False`, spy `_handle_unreadable_file` / `write_json_atomic`, dialog ทั้งสามแบบ และจำนวนบรรทัด log; ไม่มี test ที่ยืนยันพฤติกรรมเดิมที่ผิด (B1) — QA บันทึกว่ารันกับโค้ด HEAD ได้ 14 failures + 5 errors; AC-12 / AC-13 lock พฤติกรรมเดิมที่ spec กำหนดให้คงไว้ (`print("Error loading jobs")` ไม่มี guard — R8-R7 ยอมรับแล้ว)

## Verdict ราย R8-AC

| AC | ผล | หลักฐาน |
|---|---|---|
| R8-AC-1 | ✅ ผ่าน | `:9517-9533`; `test_ac1_ac3_ac4_ac5_both_failure_modes` (subTest `replace` / `atomic`) เทียบ list เต็มกับ `expected_jobs("P1")`, Job ที่มี `"P2"` คงเดิม; `test_ac1_first_profile_follows_dict_order` |
| R8-AC-2 | ✅ ผ่าน | `test_ac2_no_profiles_gives_default` สองแบบ → `"DEFAULT"` |
| R8-AC-3 | ✅ ผ่าน | ทางใหม่ไม่เรียก `messagebox` / `_handle_unreadable_file`; `_assert_ac1_to_5` ตรวจ `showwarning`/`showerror`/`showinfo` และ `handle.assert_not_called()` |
| R8-AC-4 | ✅ ผ่าน | ไม่มีชื่อ `_unreadable_` ใน listing, `assertIs(_jobs_save_blocked, False)` |
| R8-AC-5 | ✅ ผ่าน | `after == before` และ `b'"profile": "P1"'` ไม่อยู่ในไฟล์ |
| R8-AC-6 | ✅ ผ่าน | `:9523-9526` `os.remove(f"{self.jobs_file}.tmp")` best-effort; `test_ac6_tmp_removed_after_replace_failure` (listing = `["saved_jobs.json"]`), `test_ac6_remove_tmp_uses_jobs_file_tmp_path`, `test_ac6_remove_raises_still_returns_jobs_and_prints` (patch `os.remove` จบก่อนออกจาก tempdir ตาม R8-R6) |
| R8-AC-7 | ✅ ผ่าน | `:9527-9530` print 1 บรรทัดมี path + `e` ครอบ guard; `test_ac7_one_log_line_with_file_and_error` (1 บรรทัด, มี `str(error)` และ path, ไม่มี `Error loading jobs`), `test_ac7_cp874_console_cannot_encode_message` (precondition ยืนยันว่า print พังจริง), `test_ac7_stdout_write_raises_oserror`, `test_ac7_stdout_none` |
| R8-AC-8 | ✅ ผ่าน | `test_ac8_ac9_next_save_keeps_old_jobs`: `save_jobs() is True`, ไฟล์ = Job เดิม (มี `"profile"`) + `NEW`, `len == 4` |
| R8-AC-9 | ✅ ผ่าน | ต่อใน test เดียวกัน: `wraps` spy `assert_not_called()`, ค่าคืน == ไฟล์, bytes ไม่เปลี่ยน |
| R8-AC-10 | ✅ ผ่าน | `test_ac10_successful_write_back`: `spy.assert_called_once_with(jobs_file, result, indent=4)`, เนื้อไฟล์ == `json.dumps(expected, indent=4, ensure_ascii=False)`, ไม่มี `.tmp` / dialog / stdout |
| R8-AC-11 | ✅ ผ่าน | `test_ac11_no_migration_no_write` (ครบ profile และ `[]`): spy ไม่ถูกเรียก, bytes และ `st_mtime_ns` (ตั้งค่าเก่าไว้ก่อน) ไม่เปลี่ยน |
| R8-AC-12 | ✅ ผ่าน | `except` เดิมไม่เปลี่ยน; `test_ac12_unreadable_files_unchanged_behaviour` 4 แบบ: `[]`, `showwarning` 1 ครั้ง title/ข้อความตาม AC, สำเนา bytes เท่าเดิม, ไม่มี log ของทางใหม่ |
| R8-AC-13 | ✅ ผ่าน | `test_ac13_unreadable_and_no_copy_blocks_save`: `_jobs_save_blocked is True`, `save_jobs()` คืน `False`, ไฟล์ไม่เปลี่ยน; `test_bugfix_h3` / `test_r7_console_print` ผ่านโดยไม่แก้ (focused 86 OK) |
| R8-AC-14 | ✅ ผ่าน | `:9485-9486` ไม่เปลี่ยน; `test_ac14_missing_file`: `[]`, ไม่มี dialog, directory ว่าง |
| R8-AC-15 | ⏳ รอ — ผู้ใช้สั่งเลื่อน | R8-T3 ยังไม่รัน (ไม่นับเป็นข้อบกพร่อง); focused 86 tests OK ทั้ง utf-8 และ cp874 (QA) และ cp874 pipe (reviewer) |

## 🔴 Critical (ต้องแก้ก่อน merge)
- ไม่มี

## 🟡 Warning (ควรแก้)
- ไม่มี

## 🟢 Suggestion (ทางเลือก)
1. [database_connect_gui.py:9523-9526] (รับทราบตาม R8-R3) เมื่อ `write_json_atomic` ล้มตั้งแต่ `open(tmp, "w")` (เช่น `.tmp` ถูกล็อกโดย OneDrive) cleanup จะพยายามลบ `.tmp` ที่ไม่ได้สร้างใน call นี้ — ไม่มีผลต่อข้อมูลเพราะ `.tmp` เป็นไฟล์ชั่วคราวของไฟล์นี้เท่านั้น และถ้าถูกล็อกการลบก็ล้มแล้วถูกข้าม บันทึกไว้เท่านั้น
2. [tests/test_r8_load_jobs_writeback.py:251-254] ครึ่งแรกของ `test_ac7_stdout_none` เรียก `_run_failing_load(..., stdout=None)` ซึ่ง helper (`:116`) แปลง `None` เป็น `io.StringIO()` จึงซ้ำกับ `test_ac1_...` ไม่ได้ทดสอบ `sys.stdout = None` (ครึ่งหลัง `:255-260` ทดสอบจริงแล้ว) — ตัดครึ่งแรกออกหรือเปลี่ยนชื่อ parameter ได้
3. [tests/test_r8_load_jobs_writeback.py:89, :96, :111, :129] type hints ไม่ครบ (`_ClosedPipe.write`, `failure_patch` ไม่มี return type, `_run_failing_load` / `_assert_ac1_to_5` ไม่มี hint ของ parameter) — ไม่กระทบผล; ส่วน `load_jobs` ไม่มี hint เป็นของเดิม (นอกขอบเขต)
4. [database_connect_gui.py:9521-9522, :9526, :9530] comment ใหม่เป็นภาษาอังกฤษขณะที่ comment เดิมรอบ ๆ (`:9501`, `:9517`) เป็นภาษาไทย — ความสม่ำเสมอเล็กน้อยเท่านั้น

---

# Code Review — Round 9 (Bugfix B2: Load Preset ที่มี element เสีย) — 2026-11-20

ขอบเขต: R9-T1 / R9-T2 (R9-AC-1 ถึง R9-AC-16) เท่านั้น ไม่ตรวจซ้ำ Round ก่อนหน้า
ไฟล์ที่ตรวจ: `database_connect_gui.py` — `load_selected` ใน `load_preset_dialog` (`:5515-5609`, hunk `@@ -5521` และ `@@ -5543` ของ `git diff`; hunk `@@ -9509` ของ `load_jobs` เป็น Round 8 ที่ review แล้ว ไม่ตรวจ); test ใหม่ `tests/test_r9_load_preset_validation.py` (602 บรรทัด); อ่านประกอบ `save_jobs` (`:9593-9607`), `_restore_jobs_snapshot` (`:9609-9614`) และส่วนสร้างรายการ preset (`:5497-5513`, ไม่ถูกแก้)

สิ่งที่ reviewer รันจริง (stdout เป็น pipe, ไม่ตั้ง `PYTHONIOENCODING`):
- Focused ตามที่หัวหน้ากำหนด: `python -m unittest tests.test_r9_load_preset_validation tests.test_bugfix_h3 tests.test_bugfix_m5 tests.test_r8_load_jobs_writeback` → **Ran 57, OK** (ตรงกับผล QA)
- ไม่รันทั้งชุด — ผู้ใช้สั่งเลื่อน (R9-T3)

## สรุป
**ผ่าน** — 🔴 0, 🟡 0, 🟢 3

โค้ดตรงกับโค้ดตัวอย่างใน R9-D2 / R9-D3 ทุกบรรทัด, diff อยู่ใน `load_selected` เท่านั้น (R9-R8), ไม่แตะ `save_jobs` / `_restore_jobs_snapshot` / ส่วนสร้างรายการ / `load_jobs`

ประเด็นที่หัวหน้าขอให้ตรวจเป็นพิเศษ:
- **Validate อยู่ก่อน `askyesno` / `profile_combo.get` / การแตะ `saved_jobs`**: loop ตรวจ (`:5524-5541`) อยู่ต่อจาก `jobs = data.get("jobs", [])` ทันที ก่อน `current_profile = self.profile_combo.get()` (`:5543`), `current_profile_jobs` และ `askyesno` (`:5549`); ทาง reject ทำแค่ `showerror` + `return` ไม่กำหนดค่าใด ๆ ให้ `self.saved_jobs` หรือ dict ของ preset (R9-R1 ปิดแล้ว; test assert `profile_combo.get.assert_not_called()` และ `askyesno.assert_not_called()`)
- **ลำดับเงื่อนไขปลอดภัย**: `isinstance(job, dict)` มาก่อน `job.get(...)`; `job["name"].strip()` / `job["query"].strip()` ถูกเรียกเฉพาะเมื่อ `isinstance(..., str)` เป็นจริง (short-circuit `or`) จึงไม่มี exception จาก loop ตรวจเอง; `True` ตกข้อ dict, ค่า bool ไม่ผ่าน `isinstance(..., str)`; `[]` / ไม่มี `"jobs"` loop ไม่ทำงาน → ทางเดิม (R9-Q-4)
- **ไม่มีทางที่ Job หาย** (ทุก exit path หลังยืนยัน):
  - snapshot 3 ตัว (`saved_jobs_before`, `original_jobs`, `jobs_snapshot`) สร้างก่อนเข้า `try` → `except` อ้างถึงได้เสมอ
  - exception ใน filter / loop / `save_jobs()` (`:5566-5578`) → `except Exception` (`:5579`) → `_restore_jobs_snapshot` ก่อน `showerror` แล้ว `return`; exception ไม่หลุด
  - `save_jobs()` คืน `False` → `if not saved:` (`:5592`) restore + `return` แบบเดิม (R5-H-3)
  - `saved` ถูกกำหนดเสมอเมื่อมาถึง `:5592` เพราะทาง exception `return` ไปแล้ว
  - `save_jobs()` จริงจับ exception ของตัวเองและคืน `False` จึงไม่มีกรณี "ไฟล์เขียนแล้วแต่ไป rollback memory" ในทาง `except`
- **ไม่มี dialog ซ้ำ**: ทาง `False` ไม่มี `showerror` เพิ่ม (dialog มาจาก `save_jobs` 1 ครั้ง — R9-AC-13/14 assert `assert_not_called` / `assert_called_once`); ทาง exception มี `showerror("Load Preset Failed", ...)` 1 ครั้ง; ทาง reject 1 ครั้งแล้ว `return` ทันที (หยุดที่ element แรก)
- **ขอบเขต `try`**: เริ่มที่ filter จบที่ `saved = self.save_jobs()` (`:5578`); `update_jobs_list` (`:5597`), `results_text`, `showinfo`, `dialog.destroy()` (`:5609`) อยู่นอก `try` (R9-R3 ปิดแล้ว)
- **Test assert ผลจริงและไม่ pin พฤติกรรมผิด**: assert identity ของ list + identity ของ dict ทุกตัว + deep equality, bytes ของ `saved_jobs.json` และไฟล์ preset, dict ใน `preset_data` (จับผ่าน `json.load` wrapper) ไม่มี `"profile"`, `save_jobs` spy ด้วย `wraps`, จำนวนและ `parent` ของทุก dialog, ข้อความ `askyesno` เต็ม; `press()` จับ exception แล้ว `assertIsNone` จึงจับบัค B2 ได้จริง (QA บันทึกว่ากับโค้ดก่อน R9 ล้ม); ไม่มี test ใดยืนยันพฤติกรรม B2 เดิม; `Job #{n} ` มีช่องว่างท้ายกัน `#1` ชน `#12` และมี test ตำแหน่ง 12 จริง

## Verdict ราย R9-AC

| AC | ผล | หลักฐาน |
|---|---|---|
| R9-AC-1 | ✅ ผ่าน | `:5524-5541`; `BrokenPresetRejectedTests` — matrix 17 แบบ (`NON_DICT_ELEMENTS` 5 + missing 2 + name/query × 5) × ตำแหน่ง กลาง/แรก/สุดท้าย ด้วย `subTest` + probe `[ok, None]`; `assertIsNone(escaped)` + `assert_saved_jobs_unchanged` |
| R9-AC-2 | ✅ ผ่าน | `askyesno` / `profile_combo.get` / `save_spy` / `update_jobs_list` / `showinfo` / `showwarning` ไม่ถูกเรียก, `results_text.inserted == []`, `dialog.destroyed` False |
| R9-AC-3 | ✅ ผ่าน | `showerror("Invalid Preset", ..., parent=dialog)` 1 ครั้ง; test ตรวจ title, `'broken'`, `Job #<n> `, เหตุผล; `test_first_broken_element_is_reported_when_2_and_3_are_broken` → `#2`; `test_position_twelve_is_not_confused_with_one` |
| R9-AC-4 | ✅ ผ่าน | bytes `saved_jobs.json` + preset เท่าเดิม; object จาก `json.load` ที่ dialog ใช้ == preset และ dict ไม่มี `"profile"` |
| R9-AC-5 | ✅ ผ่าน | `AfterRejectTests._reject_then_save_new` (probe และ dict ที่ `query` = 7): ไฟล์ = `P-job0, U-job, P-job1, P-job2, new` และ == `before + [new]` |
| R9-AC-6 | ✅ ผ่าน | `test_good_preset_loads_after_broken_one_in_same_dialog`: reject แล้วโหลด preset ปกติใน dialog เดิมสำเร็จ, `showerror` รวม 1 ครั้ง, `askyesno` ข้อความเต็ม, `saved_jobs` / ไฟล์ = `[U-job, good1, good2]` พร้อม `"profile": "PROD"` |
| R9-AC-7 | ✅ ผ่าน | ส่วนสร้างรายการไม่ถูกแก้; `test_preset_list_unchanged_and_bad_files_skipped`: listbox 2 รายการรูปแบบเดิม, `skipped` 2 บรรทัด (JSON เสีย, `"jobs": 5`) โดย capture stdout |
| R9-AC-8 | ✅ ผ่าน | `:5565-5590`; `test_exception_in_save_jobs_is_rolled_back_and_reported`: `save_jobs` mock append + แก้ค่าซ้อน + rename แล้ว raise `RuntimeError("boom")` → identity + ค่ากลับครบ, `showerror` 1 ครั้งมี `boom` / `'good'` / `parent=dialog`, ไม่มี success, ไฟล์ไม่เปลี่ยน |
| R9-AC-9 | ✅ ผ่าน | `test_good_preset_loads_like_before` (`save_jobs` จริง, ชื่อมีช่องว่างหน้า/หลังผ่าน validate และไม่ถูก strip): `askyesno` ข้อความเต็ม, ลำดับ + `"profile": "PROD"` + key อื่นคงเดิม, ไฟล์ == memory, success ครบ, ไม่มี `showerror` |
| R9-AC-10 | ✅ ผ่าน | `test_answer_no_changes_nothing`: `save_spy` ไม่ถูกเรียก, ไม่มี dialog error/success, preset dict ไม่ถูกแก้ |
| R9-AC-11 | ✅ ผ่าน | `test_empty_or_missing_jobs_key_keeps_old_behaviour` (`[]` และไม่มี key): `with 0 jobs`, `saved_jobs` / ไฟล์ = `[U-job]`, `showinfo` 1 ครั้ง |
| R9-AC-12 | ✅ ผ่าน | `test_no_selection_warns_without_checking`: `showwarning` ตามเดิม, ไม่มี `showerror` แม้ preset เสียอยู่ในรายการ |
| R9-AC-13 | ✅ ผ่าน | `:5592-5596` ไม่มี `showerror`; `test_save_jobs_false_restores_without_extra_error` → `showerror.assert_not_called()` + identity/ค่าคืนครบ |
| R9-AC-14 | ✅ ผ่าน | `test_real_save_jobs_write_error` (`write_json_atomic` raise `OSError`) และ `test_real_save_jobs_blocked`: `showerror` 1 ครั้งข้อความเดิมของ `save_jobs`, ไฟล์ไม่เปลี่ยน, ไม่มี `showinfo` |
| R9-AC-15 | ✅ ผ่าน (ตาม focused) | test เดิมไม่ถูกแก้ (`git status` มีแค่ไฟล์ test ใหม่); `test_bugfix_h3` / `test_bugfix_m5` / `test_r8_load_jobs_writeback` ผ่านใน focused 57 OK — `test_r3_script_groups_io` ไม่อยู่ในคำสั่ง focused (ดู 🟢 ข้อ 3) |
| R9-AC-16 | ⏳ รอ — ผู้ใช้สั่งเลื่อน | R9-T3 ยังไม่รัน (ไม่นับเป็นข้อบกพร่อง); focused 57 OK ทั้ง utf-8 / cp874 (QA) และ cp874 pipe (reviewer) |

## 🔴 Critical (ต้องแก้ก่อน merge)
- ไม่มี

## 🟡 Warning (ควรแก้)
- ไม่มี

## 🟢 Suggestion (ทางเลือก)
1. [database_connect_gui.py:5545-5547] (บันทึกไว้เท่านั้น ไม่อยู่ใน scope) comprehension `current_profile_jobs` ที่เรียก `job.get("profile")` อยู่นอก `try` — ถ้า `self.saved_jobs` มี element ที่ไม่ใช่ dict exception จะหลุดออกจาก callback ก่อน `askyesno` แต่ยังไม่มีอะไรถูกแก้ จึงไม่มี Job หาย; การ validate `self.saved_jobs` เป็น Out of scope ตาม spec R9-2
2. [tests/test_r9_load_preset_validation.py:379-409] R9-AC-8 ทดสอบ exception จาก `save_jobs` เท่านั้น ไม่มีกรณี exception ระหว่าง filter / loop (`database_connect_gui.py:5566-5576`) — หลัง validate แล้วแทบไม่มีทางเกิดใน loop จริง และใช้ `except` เดียวกัน จึงไม่กระทบความมั่นใจ; ถ้าต้องการ lock ขอบเขต `try` ให้ครบ เพิ่ม test ที่ทำให้ขั้น filter raise ได้ (เช่น ให้ `profile_combo.get` ครั้งที่สองซึ่งอยู่หลัง `askyesno` คืนค่าที่ไม่ใช่ปัญหา แต่ใส่ `saved_jobs` เป็น list subclass ที่ `__iter__` raise หลังครั้งแรก)
3. [docs/spec.md R9-AC-15] AC ระบุ `tests/test_r3_script_groups_io.py` ด้วย แต่คำสั่ง focused ที่ผู้ใช้กำหนดไม่รวมไฟล์นี้ — R9-D6 วิเคราะห์ว่าไม่ผ่าน `load_selected` จึงความเสี่ยงต่ำ ให้ครอบคลุมเมื่อรัน R9-T3 (full suite) ภายหลัง

---

# Code Review — Round 10 (Bugfix B3: Export Excel เขียนผ่าน temp + `os.replace`) — 2026-11-20

ขอบเขต: R10-T1 / R10-T2 (R10-AC-1 ถึง R10-AC-21) เท่านั้น ไม่ตรวจซ้ำ Round ก่อนหน้า
ไฟล์ที่ตรวจ: `database_connect_gui.py` — import (`:3`, `:12`, `:17`), helper 4 ตัว (`:139-187`), worker ของ `export_jobs_to_excel` (`:10552-10558`, `:10856-10882`); อ่านประกอบ `log` / `on_done` (`:10432-10466`, ไม่ถูกแก้) — hunk `load_preset_dialog` (`@@ -5521`, `@@ -5543`) และ `load_jobs` (`@@ -9509`) เป็น Round 8-9 ที่ review แล้ว ไม่ตรวจ; `tests/test_r10_export_atomic_write.py` (ใหม่, 991 บรรทัด, 42 test) และ diff harness ของ `tests/test_r4_excel_row_limit.py`

สิ่งที่ reviewer รันจริง:
- Focused 14 ไฟล์ตามที่หัวหน้ากำหนด (`PYTHONIOENCODING=utf-8`) → **Ran 246, OK** (ตรงกับผล QA)
- `tests.test_r10_export_atomic_write tests.test_r4_excel_row_limit` แบบไม่ตั้ง `PYTHONIOENCODING` / `PYTHONUTF8` + redirect ไปไฟล์ (cp874) → **Ran 46, OK**
- `git status` หลังรัน: ไม่มีไฟล์ใหม่ใน repo
- ไม่รันทั้งชุด — ผู้ใช้สั่งเลื่อน (R10-T3)

## สรุป
**ผ่าน** — 🔴 0, 🟡 0, 🟢 4

ภาพรวม: โค้ดตรงกับ R10-D2 / R10-D3 ทุกตัวอักษร; diff ใน worker มีเฉพาะส่วนหัว (`:10552-10558`) และท้าย (`:10856-10882`) — body ของ loop ราย Job และ sheet `Export` ไม่ถูกแตะ (ไม่มีการเลื่อน indent, R10-R9); `on_done` และส่วนก่อนเริ่ม worker ไม่ถูกแก้

### ตรวจทุกทางออกของ worker

| ทางออก | ไฟล์เดิม | temp | handle ปิดก่อน replace/remove | ข้อความ | ผล |
|---|---|---|---|---|---|
| สำเร็จ / Stop (`break` = body จบปกติ) | ไม่ถูกเปิดเพื่อเขียนจน `os.replace` (`:10858`) | rename เป็น `file_path`, `temp_path = None` (`:10869`) | `temp_handle.close()` `:10856` ก่อน replace | `file_path` ปลายทางเท่านั้น | ✅ |
| fatal ใน body ก่อน/หลังมี sheet | ไม่เปลี่ยน | ลบใน `finally` `:10880` | ปิดใน `finally` `:10875-10879` ก่อน `_discard_export_temp` | contextmanager (`:169-174`) ไม่เรียก `writer.close()` เมื่อ body raise → ไม่มี `IndexError` บัง | ✅ |
| `writer.close()` / `Workbook.save` / flush ตอน `close()` ล้ม | ไม่เปลี่ยน | ลบ | `BufferedWriter.close()` ปิด raw แม้ flush ล้ม; `finally` ปิดซ้ำแบบกลืน `OSError` | สาเหตุจริง (`OSError: disk full`) | ✅ |
| ล็อก / read-only ตอนเริ่ม | ไม่ถูก create / truncate (`O_RDWR` ไม่มี `O_CREAT` / `O_TRUNC`) | ยังไม่สร้าง (ตรวจก่อน `mkstemp`) | — | `PermissionError: Cannot write to <file_path แบบตัวอักษรตรง>. ...` ไม่ใช่ repr | ✅ |
| `os.replace` ล้ม | ไม่เปลี่ยน (replace ที่ล้มไม่แตะปลายทาง) | เก็บไว้ (`keep_temp`) | ปิดแล้วที่ `:10856` | `<Type>: Could not replace <file_path> (<strerror>) ... kept at: <temp_path>` ใช้ `strerror` ไม่ใช่ `str(exc)` จึงไม่มี repr | ✅ |
| `BaseException` (`SystemExit` / `KeyboardInterrupt`) | ไม่เปลี่ยน | ลบใน `finally` | ปิดใน `finally` | ไม่ถูกกลืน หลุดออกเหมือนเดิม | ✅ |
| ลบ temp ไม่ได้ | ไม่เปลี่ยน | ค้าง + log 1 บรรทัด | — | `_discard_export_temp` คืนข้อความแทนการ raise → `fatal_error` ยังเป็นสาเหตุต้นเหตุ | ✅ |

- Thread safety: บรรทัด log ใหม่ (`:10882`) ใช้ `log()` เดิมซึ่งส่งผ่าน `self.root.after(0, ...)` เหมือน log อื่นของ worker และถูกคิวก่อน `on_done` จึงลำดับถูก ไม่มี state ร่วมใหม่ระหว่าง thread
- `_create_export_temp_file` (`:154-166`): `fdopen` ล้ม → ปิด fd + ลบ temp แล้ว raise ต่อ; `mkstemp` ใช้ `O_EXCL` (+ `O_BINARY` บน Windows) → ไม่ชนไฟล์ผู้ใช้ (R10-AC-3)
- pandas ไม่ปิด handle ที่ผู้เรียกส่งมา (`writer.close()` ปิดเฉพาะ handle ที่สร้างเอง) และ `ExcelWriter` ไม่มี `__del__` ที่จะ save ตอน GC — ทาง fatal จึงไม่มีการเขียนแฝงภายหลัง
- Scope: ไม่มีการแก้ `on_done`, ตัวนับ, ข้อความ log เดิม, B4-B16, retry หรือการล้าง temp ค้าง

### Verdict ราย AC

| AC | ผล | หลักฐาน |
|---|---|---|
| R10-AC-1 | ✅ ผ่าน | `test_ac1_old_file_intact_whenever_a_query_runs`: อ่าน bytes ปลายทางทุกครั้งที่ query รัน (3 ครั้ง) == ไฟล์เดิม |
| R10-AC-2 | ✅ ผ่าน (ตามการตีความที่หัวหน้ายืนยัน) | `_ensure_export_target_writable` `:139-151` เปิด `O_RDWR` ไม่ create / truncate; `test_ac2_...`: spy `open` / `os.open` (flag เขียน / สร้าง / ตัด) ว่าง, `ExcelWriter` ได้ file object ไม่ใช่ `file_path`, `os.replace` 1 ครั้ง `dst == file_path` โฟลเดอร์เดียวกัน ชื่อตรง `TEMP_RE`, bytes ปลายทาง ณ ตอน replace == เดิม |
| R10-AC-3 | ✅ ผ่าน | `test_ac3_...` 3 กรณี (สำเร็จ / fatal ก่อน / fatal หลัง) กับ `export.tmp.xlsx`, `export.xlsx.tmp`, `export.12345678.tmp.xlsx`, `~$export.xlsx`, `notes.txt` — bytes เท่าเดิมทุกไฟล์ |
| R10-AC-4 | ✅ ผ่าน | `test_ac4_...`: subprocess จริง, `IN_QUERY` แล้ว `kill()`; bytes ระหว่างรันและหลัง kill == เดิม, sheet `["Old"]`; มี timeout ฝั่ง parent |
| R10-AC-5 | ✅ ผ่าน | `test_ac5_...`: เทียบ `(coordinate, value, data_type)` ทุก cell กับ export ไป path ใหม่, ไม่มี `old-value` / `12345`, `=1+1` เป็น `"s"`, annotation ครบ, ตัวนับ 2/0/1/1 |
| R10-AC-6 | ✅ ผ่าน | `test_ac6_...`: ไฟล์ใหม่เพียง `export.xlsx`, 4 sheet |
| R10-AC-7 | ✅ ผ่าน | `test_ac7_...`: `📁 File:` / `📁 Saved to:` = `file_path`, `showinfo` 1 ครั้งมี `file_path`; temp path / ชื่อ / `.tmp.xlsx` ไม่ปรากฏใน log และ dialog |
| R10-AC-8 | ✅ ผ่าน | `test_ac8_...`: read error + row limit (R4) เป็น sheet `Failed` ครบ, replace 1 ครั้ง, ไม่มี temp ค้าง |
| R10-AC-9 | ✅ ผ่าน | `test_ac9_...` + `assert_fatal_keyerror`: ไฟล์เดิมคงอยู่, replace ไม่ถูกเรียก, `showerror` 1 ครั้งมี `KeyError` / `query`, log `Error: KeyError: ` และ `EXPORT EXCEL FAILED` 1 ครั้ง, ไม่มี `showinfo` |
| R10-AC-10 | ✅ ผ่าน | `test_ac10_...`: ไม่มี `IndexError` / `At least one sheet must be visible` ทั้ง dialog และ log; `read_sql_calls == []`; กรณีไม่มีไฟล์เดิมไม่สร้างอะไร (`test_ac9_ac10_fatal_without_an_old_file_creates_nothing`) |
| R10-AC-11 | ✅ ผ่าน | patch `Workbook.save` เขียน bytes บางส่วนลง handle แล้ว raise `OSError("disk full")`; ยืนยันว่า save ถูกเรียกจริง (`written == [True]`), ไฟล์เดิมคงอยู่, temp ถูกลบ |
| R10-AC-12 | ✅ ผ่าน | patch `os.remove` + `os.unlink` raise `PermissionError` ทั้งกรณี `KeyError` / `disk full`: log 1 บรรทัดมี temp path, `showerror` เป็นสาเหตุต้นเหตุ ไม่มี `PermissionError` / `Access is denied`, `on_done` 1 ครั้ง |
| R10-AC-13 | ✅ ผ่าน | `SystemExit` (หลังมี sheet / Job แรก) และ `KeyboardInterrupt`: `assertRaises` + ไฟล์เดิมคงอยู่ + ไม่มี temp ค้าง |
| R10-AC-14 | ✅ ผ่าน | `CreateFileW(FILE_SHARE_READ)` จริงบน win32 (ยืนยันว่า lock มีผลก่อน) + กรณี read-only: `read_sql_dataframe` ไม่ถูกเรียก, `showerror` มี `file_path` แบบตัวอักษรตรงและ `PermissionError`, ไม่มี temp |
| R10-AC-15 | ✅ ผ่าน | ล็อกจริงระหว่าง Job สุดท้าย (win32) + patch `os.replace` raise `PermissionError("locked")`: ไฟล์เดิมคงอยู่, temp ที่เก็บไว้มีครบ 2 sheet และค่าถูก, `showerror` มี `file_path` + temp path + สาเหตุ, ไม่มี temp อื่น |
| R10-AC-16 | ✅ ผ่าน | sheet `["Job 1"]`, `⏹ Stopped — 2 job(s) not exported`, replace 1 ครั้ง; ไม่ assert ข้อความสำเร็จ (B12) ถูกต้อง |
| R10-AC-17 | ✅ ผ่าน | sheet `Export` `Status = Stopped`, replace 1 ครั้ง, ไม่มี temp |
| R10-AC-18 | ✅ ผ่าน | matrix 7 กรณี: `Thread` / `_start_stoppable_run` ไม่ถูกเรียก, bytes ทุกไฟล์ในโฟลเดอร์เท่าเดิม, dialog ตามเดิม; patch `_block_if_profile_mismatch` ที่ class ถูกต้องเพราะโค้ดเรียกผ่าน `DatabaseConnectorGUI._block_if_profile_mismatch(self, ...)` |
| R10-AC-19 | ✅ ผ่าน | `_ExistingTargetMixin` × 6 class ของ R7 รันทุก test ของ R7 บนไฟล์เดิมที่มีอยู่ + assert ไม่มี temp ค้าง / ไม่มี sheet `Old` / ไฟล์ถูกแทนที่ |
| R10-AC-20 | ✅ ผ่าน | diff `tests/test_r4_excel_row_limit.py` มีเพียง `import tempfile`, `_FakeWriter.close()` และ path ใน `TemporaryDirectory` — ไม่แตะ assertion; test เดิมอื่นไม่ถูกแก้; focused 246 OK |
| R10-AC-21 | ⏳ รอ — ผู้ใช้สั่งเลื่อน | R10-T3 ยังไม่รัน (ไม่นับเป็นข้อบกพร่อง) |

## 🔴 Critical (ต้องแก้ก่อน merge)
- ไม่มี

## 🟡 Warning (ควรแก้)
- ไม่มี

## 🟢 Suggestion (ทางเลือก)
1. [database_connect_gui.py:154-158, :10873-10874] ถ้า `tempfile.mkstemp` ล้ม (โฟลเดอร์ที่ผู้ใช้แก้ไฟล์เดิมได้แต่สร้างไฟล์ใหม่ไม่ได้ หรือ path ปลายทางยาวเกือบ MAX_PATH 260 ตัวอักษร ซึ่งชื่อ temp ยาวกว่าเดิม 13 ตัวอักษร) `fatal_error` จะเป็น `str(exc)` เช่น `FileNotFoundError: [Errno 2] No such file or directory: 'C:\\...\\export.k3j2ab9x.tmp.xlsx'` — แสดง temp path ที่ผู้ใช้ไม่เคยเลือกในรูป repr และกรณี path ยาวเป็น regression เล็กน้อย (เดิมเขียนตรงได้) — R10-D3 ยอมรับแถวนี้ไว้แล้ว และเกิดได้ยากมาก; ถ้าจะปรับในอนาคต ห่อข้อความแบบ `_ensure_export_target_writable` (อ้าง `file_path` ตัวอักษรตรง + `strerror`)
2. [database_connect_gui.py:10856-10868] ไม่มี retry เมื่อ `os.replace` ล้มชั่วขณะเพราะ antivirus / OneDrive sync ถือ temp ที่เพิ่งปิด — ตาม R10-Q-3 ที่อนุมัติแล้ว และทาง fallback ไม่เสียข้อมูล (temp ถูกเก็บ + แจ้ง path); ถ้าผู้ใช้พบข้อความ "Could not replace" บ่อยในโฟลเดอร์ OneDrive ค่อยพิจารณา retry สั้น ๆ ใน Round ถัดไป
3. [tests/test_r10_export_atomic_write.py:201-208] การ "ปิด handle ก่อน `os.replace` / `os.remove`" ถูกตรวจทางอ้อมด้วยพฤติกรรมของ Windows เท่านั้น (ถ้ายังเปิดอยู่ replace / remove จริงจะล้ม) — บน OS อื่น regression นี้จะไม่ถูกจับ; ถ้าต้องการ lock แบบไม่ขึ้นกับ OS ให้ spy `app._create_export_temp_file` เก็บ handle แล้ว assert `handle.closed` ใน `_replace` / spy ของ `os.remove`; และยังไม่มี test สำหรับทาง `mkstemp` ล้ม (แถวใน R10-D3 ที่ไม่มี AC)
4. [database_connect_gui.py:156, :10862-10865] (cosmetic) บน Windows `file_path` จาก `asksaveasfilename` ใช้ `/` แต่ temp path มาจาก `os.path.abspath` จึงใช้ `\` — ข้อความกรณี replace ล้มจะมี separator ปนกัน ทั้งสอง path ยังเป็นตัวอักษรตรงและใช้งานได้

---

# Code Review — Round 11 (Bugfix B4: Header "target" และ Tables ใช้ snapshot ของ connection) — 2026-11-20

ขอบเขต: R11-T1 / R11-T2 (R11-AC-1 ถึง R11-AC-21) เท่านั้น ไม่ตรวจซ้ำ Round 8-10 (hunk `@@ -1`, `@@ -8`, `@@ -134`, `@@ -5521`, `@@ -5543`, `@@ -9509`, `@@ -10452`, `@@ -10751` ของ `git diff` เป็นของ Round 8-10 ที่ review แล้ว)
ไฟล์ที่ตรวจ: `database_connect_gui.py` — `_TARGET_MISMATCH_NOTE` / `_target_summary_text` (`:415-426`), `__init__` (`:2433`), closure `_refresh_target_summary` (`:2708-2711`), `connect_database` (`:7700`, `:7717`), `_replace_engine` (`:7737-7759`), `_connected_password_for` / `_details_differ_from` / `_update_target_summary` (`:7775-7831`), `list_tables` (`:9254-9285`), `_reset_profile_connection_state` (`:11223-11225`); อ่านประกอบ `_capture_run_target` (`:7761-7773`), worker ของ `list_tables` (`:9295-9534`, ไม่ถูกแก้), `get_connection_string` (`:7595-7642`), `on_list_tables_error` (`:9638-9650`); `tests/test_r11_connection_target_snapshot.py` (ใหม่, 912 บรรทัด, 45 test) และ diff `tests/test_run_engine_batch.py:424`

สิ่งที่ reviewer รันจริง:
- `python -m unittest tests.test_r11_connection_target_snapshot tests.test_run_engine_batch tests.test_bugfix_h1` ด้วย `PYTHONIOENCODING=utf-8` → **Ran 62, OK**
- คำสั่งเดียวกัน ไม่ตั้ง `PYTHONIOENCODING` / `PYTHONUTF8` (locale `cp874`) + redirect stdout+stderr ไปไฟล์ใน scratchpad → **Ran 62, OK**
- `git status` หลังรัน: ไม่มีไฟล์ใหม่ใน repo
- ไม่รันทั้งชุด — ผู้ใช้สั่งเลื่อน (R11-T3 / R11-Q-9)

## สรุป
**ผ่าน** — 🔴 0, 🟡 0, 🟢 5

ภาพรวม: โค้ดตรงกับ R11-D2 ถึง R11-D5 ทุกตัวอักษร; hunk ของ Round 11 อยู่เฉพาะจุดในขอบเขตของ design (`@@ -361`, `@@ -2366`, `@@ -2642`, `@@ -7627`, `@@ -7647`, `@@ -7676`, `@@ -9097`, `@@ -11009`); worker `fetch_tables_in_background`, `ConnectionInfo` / `RunTarget`, `_capture_run_target`, `_block_if_profile_mismatch`, `_confirm_data_change`, `execute_query`, `_refresh_conn_badge`, Save Job / Save Profile ไม่ถูกแตะ; ไม่ต้อง import ใหม่ (`Tuple` มีอยู่แล้วใน HEAD)

### ทุกเส้นทางที่ตั้ง / ล้าง password

ค้นทั้งไฟล์: `self.engine` ถูกเปลี่ยนค่าเพียง 3 จุด (`:2432` init, `:7750` `_replace_engine`, `:11223` reset) และ `_connected_password` ถูกเขียนเพียง 3 จุดคู่กัน — ไม่มีทางที่ engine เปลี่ยนแล้ว password ค้าง

| เส้นทาง | engine | `_connected_password` | ผล |
|---|---|---|---|
| `__init__` `:2432-2433` | `None` | `None` (มี type hint ที่จุดประกาศ) | ✅ |
| Connect สำเร็จ `:7717` | engine ใหม่ | `(engine, password)` ไม่ strip = ค่าที่ใช้สร้าง engine จริง (`:7658`) | ✅ AC-18/19ก/20 |
| Connect ล้ม `:7700` → `_replace_engine(None)` | `None` | `None` (`:7752-7754` เงื่อนไข `engine is not None`) — ล้างจริง ไม่ใช่แค่ถูกบัง | ✅ AC-19ข |
| Connect early return (busy / ช่องว่าง `:7665`) | ไม่แตะ | ไม่แตะ (connection เดิมใช้ต่อได้) | ✅ |
| `_replace_engine(x, info)` จากที่อื่น / test เดิม (ไม่ส่ง password) | `x` | `None` — password ของ engine เก่าไม่ติดไป | ✅ |
| `_reset_profile_connection_state` ตัดจริง `:11223-11225` | `None` | `None` | ✅ AC-19ค |
| reset ข้ามเพราะ reconnect แล้ว (`:11209`) / รอ busy (`:11219`) | ไม่แตะ | ไม่แตะ (ของ connection ใหม่ถูกต้อง) | ✅ |
| อ่านค่า `_connected_password_for` `:7775-7782` | — | คืนค่าเฉพาะ `stored[0] is engine`; `getattr(..., None)` รองรับ stub เดิม | ✅ AC-16/21 |

### ประเด็นที่หัวหน้าขอให้ตรวจเป็นพิเศษ

- **Password leakage**: password อยู่เฉพาะใน tuple ส่วนตัว (`:2433`) และ local `password` / `connection_credentials` (`:9263`, `:9272`) ที่ส่งเป็น thread args (`:9531`); ไม่อยู่ใน `ConnectionInfo` / `RunTarget` (field ไม่เปลี่ยน), ไม่มี `print` / `results_text.insert` / `_write_run_log` / ข้อความ exception ใหม่ที่อ้างถึง password; ข้อความ block `⛔` (`:9265-9269`) เป็นข้อความคงที่ไม่มี host / user / password; header (`:7797-7831`) ไม่อ่าน `db_password` เลย (ทั้งทาง info และไม่มี info); `threading.Thread.__repr__` ไม่แสดง args; test `test_ac18_*` ตรวจ `repr` / `str` / `asdict` / `target_label` / `log_target` / `run_log_header` / Execution Logs / `_write_run_log` / `messagebox` / `print` ที่ patch (และยืนยันว่า `print` ถูกจับจริง) — ไม่มี `S3cr3t`
- **Thread safety**: ค่าทั้งหมดที่ worker ใช้ (`engine`, `db_type`, `current_db_name`, `credentials`) ถูกจับบน main thread ก่อน `thread.start()` (`:9534`); `_connected_password` ถูกอ่าน / เขียนบน main thread เท่านั้น (Connect, reset, Tables, header poll); worker ไม่อ่าน `self._connected_password` / `self.engine` / ช่องกรอก — Connect ใหม่ระหว่าง worker ทำงานไม่เปลี่ยน tuple ที่ส่งไปแล้ว (`test_ac14_*` ยืนยัน)
- **Tk polling cost**: ต่อรอบ 500 ms ทางไม่มี info = `get()` 5 ช่อง + `cget` 3 ครั้ง (เดิม 5 + 2); ทางมี info = `_capture_run_target()` (getattr 2 ครั้ง) + `get()` 5 ช่องใน `_details_differ_from` + `cget` 3 ครั้ง; `config` ถูกเรียกเฉพาะเมื่อข้อความ / สีเปลี่ยน (`test_ac9_no_config_when_nothing_changed`, `test_ac9_warning_colour_set_once_then_restored_once`) — ไม่มี redraw ซ้ำทุก poll; `str(cget("fg"))` เทียบกับค่า `UI` ตัวพิมพ์ใหญ่ที่ label ถูกสร้างด้วย (`:2549-2551`) จึงตรงกัน
- **การหยุด poll**: `_update_target_summary` คืน `False` เมื่อ `tk.TclError` → closure ไม่ตั้ง `after` (เทียบเท่า `return` เดิม); exception ชนิดอื่นหลุดออกจาก callback เหมือนก่อนแก้ (ความเสี่ยงไม่เพิ่ม)
- **PEP 8 / type hints**: method ใหม่ทุกตัวมี type hint ครบ; ทุกบรรทัดใหม่ ≤ 95 ตัวอักษร (สอดคล้องความยาวบรรทัดที่ใช้ทั้งไฟล์); docstring ครบ
- **Harness `tests/test_run_engine_batch.py:424`**: diff มี 1 บรรทัด `stub._connected_password = (engine_a, "pw")` ก่อน `threads = self._start(stub)` ใน `test_info_db_type_wins_over_screen_at_start` เท่านั้น ไม่แตะ assertion — ตรง R11-Q-10 ที่ผู้ใช้อนุมัติ

### Verdict ราย AC

| AC | ผล | หลักฐาน |
|---|---|---|
| R11-AC-1 | ✅ ผ่าน | ทาง `info is None` (`:7814-7821`) ใช้สูตรเดิมทุกตัวอักษร (`db_type` ไม่ strip, port ไม่ `split`); `test_ac1_*` 2 test รวมกรณี port / database ว่าง, สี `muted` |
| R11-AC-2 | ✅ ผ่าน | `test_ac2_*`: `"PostgreSQL · app@uat-db:5432"` / `"Database / Service: UAT"` และกรณี `Database: (default)` |
| R11-AC-3 | ✅ ผ่าน | `test_ac3_*` ทั้งเรียก method ตรงและผ่าน closure จริงจาก `__init__` (AST): ไม่มี `prod-db` / `PROD`, มี `⚠` + `Connect`, `fg == UI["warn"]` |
| R11-AC-4 | ✅ ผ่าน | `subTest` 5 ช่อง; แก้ `db_password` / `profile_combo` ไม่เตือนและ `get()` ของสองช่องนี้ไม่ถูกเรียก |
| R11-AC-5 | ✅ ผ่าน | ช่องว่างหน้า/หลัง + `"5432:x"` ไม่เตือน; case-sensitive (`UAT-DB`) เตือน ตาม Q-4 |
| R11-AC-6 | ✅ ผ่าน | (ก) แก้ช่องกลับ → คำเตือนหาย สี `muted`; (ข) `connect_database` จริง → header เป็น `prod-db` / `PROD` ไม่เตือน |
| R11-AC-7 | ✅ ผ่าน | Connect ล้ม และ reset → header จากช่องกรอก ไม่เตือน |
| R11-AC-8 | ✅ ผ่าน | `RunTarget(engine, None)` และ `_run_target` ของ engine อื่น → ทางช่องกรอก |
| R11-AC-9 | ✅ ผ่าน | label ปิดแล้ว → คืน `False` ไม่ raise; closure ไม่เรียก `after` / เรียก `after(500, closure)` เมื่อปกติ; ไม่ `config` ซ้ำ |
| R11-AC-10 | ✅ ผ่าน | `execute_query` ไม่ถูกแก้; SELECT ได้ `engine_uat` ไม่มี dialog / `⛔`; DELETE แสดง `PostgreSQL · uat-db / UAT` |
| R11-AC-11 | ✅ ผ่าน | `get_connection_string` = `("MySQL","app","pw-uat","uat-db","3306","d1"/"d2")` และ assert ว่าไม่มีค่าใดจากช่องกรอก |
| R11-AC-12 | ✅ ผ่าน | ทั้งสองทิศ: snapshot ว่าง + ช่อง `PROD` → ทุก database, flag `False`; snapshot `UAT` + ช่องว่าง → `inspect(engine_uat)`, แถว `"Database": "UAT"`, flag `True` |
| R11-AC-13 | ✅ ผ่าน | `forbid_get` ทั้ง 6 ช่องก่อนเรียก ทั้งสองทาง + worker; `_reads` ว่าง |
| R11-AC-14 | ✅ ผ่าน | thread args จับก่อน start; Connect ใหม่หลัง start แล้ว worker ยังได้ค่า UAT; engine ใหม่ถูก `connect` เฉพาะ `SELECT 1` |
| R11-AC-15 | ✅ ผ่าน | Oracle ไม่มี password เก็บไว้ → ไม่ block, `create_engine` / `get_connection_string` ไม่ถูกเรียก, `inspect(engine)` |
| R11-AC-16 | ✅ ผ่าน | 3 กรณี (ไม่มี attribute / `None` / engine อื่น): ไม่มี thread, 1 บรรทัด `⛔ Tables ไม่ได้เริ่มงาน` มี `Connect`, `inspect_btn` / dialog / `root.update` / `showerror` ไม่ถูกแตะ, ช่องกรอกไม่ถูกอ่าน; ทาง database ปัจจุบันไม่ block |
| R11-AC-17 | ✅ ผ่าน | ไม่มี info → ลำดับอ่าน `db_type → db_name → user → password → host → port` เดิม และไม่ใช้ password ที่เก็บไว้; `test_bugfix_h1` + `test_run_engine_batch` ผ่าน (รันจริง) |
| R11-AC-18 | ✅ ผ่าน | ดูหัวข้อ leakage ข้างบน; ใช้ sqlite จริงด้วย; password ไม่ strip |
| R11-AC-19 | ✅ ผ่าน | (ก) Connect ซ้ำได้ B เท่านั้น; (ข) ล้มหลังมี connection และล้มครั้งแรก → `_connected_password is None`; (ค) reset → `None`, reset ที่ถูกข้ามเพราะ reconnect คง password ใหม่; accessor ต้อง engine ตัวเดียวกัน |
| R11-AC-20 | ✅ ผ่าน | แก้ช่อง `db_password` หลัง Connect → `get_connection_string` ยังได้ password A |
| R11-AC-21 | ✅ ผ่าน (reviewer รัน 3 ไฟล์ + ผล QA 14 ไฟล์ `Ran 276 OK`) | test เดิมไม่ถูกแก้ยกเว้น `tests/test_run_engine_batch.py:424` ตาม R11-Q-10 |
| R11-AC-22 | ⏳ รอ — ผู้ใช้สั่งเลื่อน | R11-T3 ยังไม่รัน (ไม่นับเป็นข้อบกพร่อง) |

## 🔴 Critical (ต้องแก้ก่อน merge)
- ไม่มี

## 🟡 Warning (ควรแก้)
- ไม่มี

## 🟢 Suggestion (ทางเลือก)
1. [database_connect_gui.py:9272] `connection_credentials` ใส่ password ที่เก็บไว้เข้า thread args เสมอ แม้ทาง "database ปัจจุบัน" และ Oracle ที่ worker ไม่ใช้ password เลย — ไม่ใช่การรั่ว (อยู่ใน memory เหมือน `engine.url`) แต่ถ้าต้องการลดจุดที่ password อยู่ ให้ส่ง `""` เมื่อ `current_db_name` มีค่าหรือ `db_type == "Oracle"` (hardening เล็กน้อย ไม่กระทบ AC)
2. [database_connect_gui.py:9352, :9478, :9638-9650] (พฤติกรรมเดิม ตาม R11-R3 ไม่ใช่ regression) worker `print` / `on_list_tables_error` แสดง `str(e)` ของ driver ตรง ๆ; สำหรับ SQL Server password อยู่ใน query `odbc_connect=...PWD=...` ซึ่ง SQLAlchemy ไม่ mask ใน `URL.__repr__` (mask เฉพาะ field password) — ถ้า driver / SQLAlchemy ใส่ URL ไว้ใน error password จะไปถึง console / Execution Logs ได้; Round นี้ไม่ได้ทำให้แย่ลง (เดิมก็ส่ง password จากช่องกรอก) แต่ถ้าจะปิดความเสี่ยงควรเปิด Round แยกเพื่อ redact `PWD=` / password ออกจากข้อความ error
3. [database_connect_gui.py:7660, :7786-7794] กรณีขอบ: ถ้าช่อง Port เป็น `"5432 :x"` ตอน Connect, `info.port` จะเป็น `"5432 "` (strip ก่อน split จึงเหลือช่องว่างท้าย) ขณะที่ `_details_differ_from` ได้ `"5432"` จากช่อง → header เตือนค้างทั้งที่ไม่ได้แก้อะไร; ไม่กระทบปลายทางที่รัน (เตือนเกิน ตามแนว Q-4) — ถ้าจะแก้ให้ `.strip()` ฝั่ง `info.port` ใน `_details_differ_from` (ไม่ต้องแตะ `connect_database`)
4. [database_connect_gui.py:7737-7742, :2708] type hint ยังไม่ครบ: parameter `engine` ของ `_replace_engine` ไม่มี annotation (ควรเป็น `engine: Any` ให้สอดคล้องกับ `_connected_password_for(self, engine: Any)`) และ closure `_refresh_target_summary()` ไม่มี `-> None` — ทั้งสองเป็นของเดิม แก้ได้ในบรรทัดที่ Round นี้แตะอยู่แล้ว
5. [tests/test_r11_connection_target_snapshot.py:194-202, tests/test_run_engine_batch.py:424] test ตั้ง `stub._connected_password = (engine, password)` ตรง ๆ จึงผูกกับรูปแบบภายใน (tuple) — ถ้าอนาคตเปลี่ยนวิธีเก็บ test ต้องแก้หลายจุด; ทางเลือกคือตั้งผ่าน `stub._replace_engine(engine, info, password=...)` ใน helper `set_snapshot` — ไม่กระทบความถูกต้องของผลปัจจุบัน

---

# Code Review — Round 12 (Follow-up: ข้อเสนอแนะ 🟢 จาก review Round 8–11) — 2026-11-23

ขอบเขต: R12-1 ถึง R12-8 และ R12-T เท่านั้น ไม่ตรวจซ้ำส่วนที่เป็น Round 8–11 ใน commit `1a573b2`
ไฟล์ที่ตรวจ: `database_connect_gui.py` — `write_json_atomic` (`:73-91`), `_SECRET_PATTERNS` / `redact_secrets` (`:94-119`), `_create_export_temp_file` (`:194-215`), `EXPORT_REPLACE_RETRY_DELAYS` / `_replace_export_with_retry` (`:228-244`) และจุดที่ worker ของ Export เรียกใช้ (`:11028-11041`), `load_selected` (`:5668-5672`), `_details_differ_from` (`:7856-7872`), `_replace_engine` (`:7809-7830`), closure `_refresh_target_summary` (`:2778`), `list_tables` (`:9336-9358`, print / traceback ใน worker `:9438-9441`, `:9546-9551`, `:9564-9567`), `on_list_tables_error` (`:9724-9740`), `load_jobs` (`:9776-9787`); tests: `tests/test_r8_load_jobs_writeback.py` (AC-6 / AC-7), `tests/test_r9_load_preset_validation.py:411-466`, `tests/test_r10_export_atomic_write.py` (harness `:175-178`, `assert_kept_temp` `:815-830`, retry `:859-906`, `TempHandleAndCreationTests` `:1045-1124`), `tests/test_r11_connection_target_snapshot.py:194-202`, `:364-372`, `:923-1006`, `tests/test_run_engine_batch.py:424`

สิ่งที่ reviewer รันจริง:
- `python -X utf8 -m unittest tests.test_r8_load_jobs_writeback tests.test_r9_load_preset_validation tests.test_r10_export_atomic_write tests.test_r11_connection_target_snapshot tests.test_run_engine_batch tests.test_bugfix_h3 tests.test_r6_import_save_failure tests.test_database_connect_gui_core` → **Ran 282, OK**
- probe ใน scratchpad (ไม่อยู่ใน repo): `write_json_atomic` ทุกทางออก และ `redact_secrets` กับ password 10 แบบ × 6 รูปแบบข้อความ (ODBC ดิบ, `odbc_connect=` encoded, `str(URL)` / `render_as_string` ของ SQLAlchemy 2.1.4, URL pg แบบ encoded / ไม่ encoded) + ข้อความ error ปกติ 7 แบบ
- `git status` หลังรัน: สะอาด
- ไม่รันทั้งชุดซ้ำ — ใช้ผลของหัวหน้า (`Ran 1147 ... OK` ทั้ง utf-8 และ cp874)

## สรุป
**ผ่าน** — 🔴 0, 🟡 1, 🟢 9

ประเด็นที่หัวหน้าขอให้ตรวจเป็นพิเศษ:

**1. `redact_secrets`**
- ผล probe: ข้อความที่แอปสร้างได้จริงทุกแบบ **ไม่มีรั่ว** — ODBC ดิบ `PWD={...}` (รวม `}`→`}}`, `;`, `=`, `{`, `PWD=` ซ้อนในรหัส), `odbc_connect=` แบบ `quote_plus` (pattern 2 ข้าม `%7D%7D` ได้ถูก และ `%` ในรหัสถูก encode เป็น `%25` จึงไม่ชน `%7D`), `str(URL)` / `render_as_string(hide_password=False)` ของ SQLAlchemy, URL pg/MySQL/Oracle ที่แอป `quote_plus` รหัสไว้ (`@`→`%40`, `:`→`%3A`) — แม้ไม่ส่ง known secret
- รั่วได้เฉพาะ URL ที่ใส่รหัส **ไม่ encode** และรหัสมีช่องว่าง / `'` / `"` / `@` (pattern 3 หยุดที่ตัวนั้น) — แอปไม่สร้าง URL แบบนี้ และถ้ารหัสยาว ≥ 4 ตัว known secret ปิดให้อยู่แล้ว (ดู 🟢 ข้อ 2)
- mask เกิน: ข้อความ error ทั่วไปของ PostgreSQL / MySQL / SQL Server / ลิงก์ `sqlalche.me` ไม่ถูกแตะ; กรณีขอบที่ mask แปลก ๆ บันทึกใน 🟢 ข้อ 2 — ไม่มีกรณีที่ทำให้ข้อความอ่านไม่รู้เรื่อง
- เส้นทางใน Tables: print / traceback ทั้ง 3 จุดใน worker และ `results_text` + `showerror` ใน `on_list_tables_error` ผ่าน `redact_secrets` แล้ว; ที่เหลือเป็น print ข้อความคงที่ / ชื่อ database / schema, `except: pass` (กลืน) และ `on_list_tables_success` (`str(e)` ของการแสดงผล ไม่เกี่ยว connection) — **ไม่พบเส้นทางดิบเหลือใน Tables**; นอก Tables ยังมี `connect_database` (🟢 ข้อ 3)

**2. `write_json_atomic`** (probe ยืนยันทุกแถว)

| ทางออก | `.tmp` | exception | ไฟล์เดิม |
|---|---|---|---|
| `open` ล้ม | ไม่แตะ (ไม่เข้า `try`) | เดิม | ไม่เปลี่ยน |
| `json.dump` ล้ม (`TypeError`) | ลบ (`with` ปิดก่อน) | เดิม | ไม่เปลี่ยน |
| `fsync` ล้ม | ลบ | เดิม | ไม่เปลี่ยน |
| `os.replace` ล้ม | ลบ | เดิม | ไม่เปลี่ยน |
| `KeyboardInterrupt` | ลบ | เดิม (bare `raise`) | ไม่เปลี่ยน |
| replace ล้ม + `os.remove` ล้ม | ค้าง | `PermissionError` เดิม ไม่ถูกบังด้วย error ของ remove | ไม่เปลี่ยน |

- ผู้เรียกอื่น (`save_jobs` `:9826`, script groups `:4560`, `:5529`, config `:11207`, `:11225`) ได้ exception เดิมทุกกรณี — ต่างจากเดิมเพียง `.tmp` ไม่ค้างหลังล้ม; ค้นทั้งไฟล์ไม่มีโค้ดที่อ่านหรืออาศัย `.tmp` ที่ค้าง จึงไม่กระทบ
- `load_jobs` (`:9776-9787`) ไม่เรียก `os.remove` แล้ว; comment เป็นภาษาไทย

**3. `_replace_export_with_retry`**
- retry เฉพาะ `PermissionError` (`except PermissionError`); `OSError` อื่นหลุดทันทีจาก attempt แรก → worker `except OSError` เก็บ temp + แจ้ง path (test `test_errors_other_than_permission_are_not_retried`: replace 1 ครั้ง, temp เก็บไว้)
- จำนวนครั้ง: 3 รอบใน loop + 1 ครั้งท้าย = 4 ครั้ง, รอรวม 0.2 + 0.5 + 1.0 = 1.7 วินาที (รอก่อนครั้งสุดท้ายด้วย ถูกต้อง); ครั้งสุดท้ายล้ม → exception จริงหลุดไป `except OSError` เดิม → `keep_temp = True`, ไฟล์เดิมไม่ถูกแตะ (replace ที่ล้มไม่แก้ปลายทาง), ข้อความมี `file_path` + temp path + `strerror` — R10-AC-15 ยังรักษาข้อมูลได้ครบ (`assert_kept_temp` ตรวจไฟล์เดิม, temp 1 ไฟล์ครบ 2 sheet, ทุก attempt ใช้ temp เดียวกัน, ข้อความ)
- `time.sleep` อยู่ใน worker thread (`threading.Thread(target=worker)` `:11048`) → UI ไม่ค้าง; `temp_handle.close()` เกิดก่อน retry ทั้งหมด
- Stop ระหว่าง retry: ไม่มีการเช็ก stop event ใน retry — รอสูงสุด 1.7 วินาทีแล้วจบตามปกติ (Stop เกิดหลัง body จบแล้ว งานที่เหลือมีแค่ rename ผลที่ได้ จึงไม่ควรยกเลิกอยู่แล้ว) ยอมรับได้

**4. Test**
- test ใหม่ส่วนใหญ่ assert ผลจริง (bytes ไฟล์, listing, call count, ค่า sleep, `handle.closed` ณ ตอน replace / remove, ข้อความ dialog ไม่มี `.tmp.xlsx`, `threads[0].args`, print ที่จับจริง) — ยกเว้น `RedactSecretsTests.test_patterns_and_known_secret` (🟡 ข้อ 1)
- test เดิมที่ถูกแก้ไม่ทำให้ความคุ้มครองหาย:
  - R8-AC-6: `test_ac6_remove_tmp_uses_jobs_file_tmp_path` ยังยืนยันว่าลบ `<jobs_file>.tmp` (ตอนนี้ผ่าน `write_json_atomic`); `test_ac6_remove_raises_...` แยก mode ถูก (replace → ลบ 1 ครั้ง + `.tmp` ค้าง; atomic → ไม่ลบ); `test_ac6_tmp_not_created_by_this_call_is_left_alone` ตรวจทั้ง `write_json_atomic` raise และ `open` ล้มจริง โดย bytes ของ `.tmp` คนอื่นคงเดิม
  - R10 `assert_kept_temp`: เพิ่ม check (ทุก attempt ใช้ temp เดียวกัน, จำนวน = 1 + retry) ไม่ได้ลด check เดิม
  - harness patch `EXPORT_REPLACE_RETRY_DELAYS` เป็น `0.0` × จำนวนเดิม — จำนวน retry เท่าของจริง ตัดแค่เวลารอ; ค่า sleep จริงตรวจแยกใน `test_retry_waits_the_configured_delays`
  - `tests/test_run_engine_batch.py:424` เปลี่ยนจากตั้ง tuple ตรงเป็น `_replace_engine(engine_a, ci, password="pw")` — engine เดียวกันจึงไม่ `dispose`, assertion ไม่เปลี่ยน

## Verdict ราย R12 item

| Item | ผล | หลักฐาน |
|---|---|---|
| R12-1 | ✅ ผ่าน | `:76-91` `open` อยู่นอก `try`; `load_jobs` `:9779-9787` ไม่มี `os.remove`; probe 6 ทางออกข้างบน; `test_ac6_*` 5 test |
| R12-2 | ✅ ผ่าน | `test_ac7_stdout_none` ใช้ `mock.patch("sys.stdout", None)` จริงทั้งสอง mode; type hints ครบใน helper (`_ClosedPipe`, `failure_patch`, `_run_failing_load`, `_assert_ac1_to_5`); comment `load_jobs` เป็นไทย (comment ใน test ไม่ตรง — 🟢 ข้อ 8) |
| R12-3 | ✅ ผ่าน | `:5668-5672` `isinstance(job, dict)`; `test_exception_while_filtering_jobs_is_rolled_back` (ยืนยันว่าถึงขั้น filter จริงด้วย counter, identity + ค่า rollback, `showerror` มี `filter broke`), `test_non_dict_in_current_jobs_does_not_escape_before_confirm` (นับ 3 ไม่นับ `None`) |
| R12-4 | ✅ ผ่าน | `:199-209`; `test_mkstemp_failure_names_the_chosen_file_not_a_temp_path` (ข้อความมี `file_path` + `strerror`, ไม่มี `.tmp.xlsx`, query ไม่รัน), `test_temp_path_uses_the_separators_of_the_chosen_path` (ทั้ง `/` และ `\`), `test_handle_is_closed_before_os_replace` / `..._temp_is_removed` ใช้ spy `handle.closed` ไม่ขึ้นกับ OS |
| R12-5 | ✅ ผ่าน | `:228-244`, `:11029-11041`; ดูข้อ 3 ข้างบน; test lock สั้น 2 ครั้งแล้วสำเร็จ (3 attempt, temp เดียวกัน, ไม่มี temp ค้าง), ค่า delay, `OSError` อื่นไม่ retry; spec ยังไม่อัปเดต (🟢 ข้อ 5) |
| R12-6 | ✅ ผ่าน | `:9350-9358` `needs_password`; `test_password_not_passed_to_thread_when_worker_does_not_use_it` 3 กรณี (database ปัจจุบัน / Oracle → `""`, MySQL list-all → รหัสจริง); ทาง R11-AC-16 block ยังใช้เงื่อนไขเดียวกัน |
| R12-7 | ✅ ผ่าน (test อ่อน — 🟡 ข้อ 1) | `:94-119`, `:9438-9441`, `:9546-9551`, `:9564-9567`, `:9736-9737`; probe ข้อ 1; `test_worker_error_output_is_redacted` (ยัง assert ว่า `login failed` / `RuntimeError` อยู่ จึงไม่ mask เกิน), `test_on_list_tables_error_is_redacted` (มี / ไม่มี password เก็บไว้ — กรณีหลังพึ่ง pattern ล้วน) |
| R12-8 | ✅ ผ่าน | `:7867` `info.port.strip()`; subTest `"5432 :x"` / `"5432"` / `" 5432 "` กับ `info.port = "5432 "` ไม่เตือน (`:364-372`); type hints `:7811`, `:2778`; `set_snapshot` (`:194-202`) ตั้งผ่าน `_replace_engine` |
| R12-T | ✅ ผ่าน (ผลหัวหน้า) | `Ran 1147 ... OK` สอง mode; reviewer รัน focused 282 OK |

## 🔴 Critical (ต้องแก้ก่อน merge)
- ไม่มี

## 🟡 Warning (ควรแก้)
1. [tests/test_r11_connection_target_snapshot.py:983-1000] `test_patterns_and_known_secret` ตรวจ "ไม่รั่ว" ด้วย `assertNotIn(pw)` / `assertNotIn(quote_plus(pw))` โดย `pw = "p@ss;w}rd"` — แต่ใน ODBC string รหัสถูกเขียนเป็น `{p@ss;w}}rd}` (`}` ถูกเบิ้ล) และในรูป encoded เป็น `p%40ss%3Bw%7D%7Drd` จึง**ไม่มี `pw` หรือ `quote_plus(pw)` อยู่ในข้อความตั้งแต่แรก** (reviewer ยืนยันด้วย probe: `pw in odbc` = `False`, `quote_plus(pw) in encoded` = `False`) — สองตัวอย่างแรกซึ่งเป็นกรณีหลักของ R12-7 (SQL Server) จึงผ่านแม้ pattern 1 / 2 จะ mask ได้แค่ครึ่งเดียว (เช่น regex จบที่ `}` ตัวแรกแล้วปล่อย `}rd}` / `%7Drd%7D` หลุด) — assert ที่เหลือคือ `"***" in plain` ซึ่งผ่านได้จากการ mask ส่วนใดส่วนหนึ่ง — ผลกระทบ: regression ของการจัดการ `}}` / `%7D%7D` ไม่ถูกจับ (โค้ดปัจจุบันถูกต้องตาม probe) — แนวทางแก้: assert ส่วนท้ายของรหัส เช่น `assertNotIn("rd", plain)` และ `assertNotIn("w}}rd", plain)` / `assertNotIn("%7D%7Drd", plain)` หรือ assert ข้อความผลลัพธ์ทั้งบรรทัด (`PWD=***` ตามด้วย `;Encrypt=...` / `%3BEncrypt...` หรือจบสตริง)

## 🟢 Suggestion (ทางเลือก)
1. [database_connect_gui.py:9736-9737] `on_list_tables_error` ใช้ password จาก `self._connected_password` ณ เวลาที่ error ถูกแสดง ไม่ใช่ `credentials[1]` ที่ worker ใช้ — ทาง "engine ไม่มี info" (R11-AC-17) ที่ worker ใช้รหัสจากช่องกรอก จะไม่มี known-secret masking (เหลือ pattern อย่างเดียว); ทางที่มี info ใช้ได้ถูกเพราะ dialog ของ Tables grab input จน Connect ใหม่ไม่ได้ — ถ้าจะให้ตรงที่สุด ส่ง `credentials[1]` ไปกับ `on_list_tables_error` (ผ่าน lambda ท้าย worker)
2. [database_connect_gui.py:94-101, :112-114] กรณีขอบของ pattern (ไม่เกิดกับข้อความที่แอปสร้าง): (ก) URL ที่รหัส**ไม่ถูก encode** และมีช่องว่าง / `'` / `"` / `@` → pattern 3 mask แค่ส่วนแรก เช่น `://u:p@ss@h` เหลือ `ss@h` (known secret ≥ 4 ตัวปิดให้); (ข) `password = 'x'` → `password = ***'x'` (แทรก `***` แต่ไม่ปิดค่าในเครื่องหมายคำพูด); (ค) `DB_PASSWORD=abc` ไม่ถูก mask เพราะไม่มี `\b` ระหว่าง `_` กับ `P`; (ง) `http://host:8080/a@b` → `http://host:***@b` (mask เกิน); (จ) known secret ที่เป็นคำทั่วไป เช่น `test` ทำให้ `testing table test_x` เป็น `***ing table ***_x` — ทั้งหมดเป็นทางที่ปลอดภัยกว่า หรือไม่เกิดในเส้นทาง Tables ปัจจุบัน บันทึกไว้ถ้าจะนำ `redact_secrets` ไปใช้ที่อื่น
3. [database_connect_gui.py:7776] (นอก scope R12) `connect_database` ยังแสดง `❌ Connection Error: {error}` ดิบใน Execution Logs — ความเสี่ยงชนิดเดียวกับที่ R12-7 ปิดใน Tables (SQL Server `odbc_connect=...PWD=...` ถ้า driver / SQLAlchemy ใส่ URL ไว้ใน error); ถ้าต้องการปิดให้ครบ ควรเปิด Round แยกเพื่อใช้ `redact_secrets(str(error), password)` ที่นี่ (และจุดแสดง error อื่นที่ผูกกับ connection)
4. [database_connect_gui.py:9438, :9441, :9547, :9551, :9564, :9567] บรรทัดที่ห่อ `redact_secrets` ยาว 113-138 ตัวอักษร (เกินแนว ≤ 95 ที่ใช้ทั้งไฟล์ / PEP 8) — แยก `message = redact_secrets(...)` ก่อน `print` จะอ่านง่ายขึ้น; `from urllib.parse import quote_plus` ใน `redact_secrets` (`:109`) ย้ายไป import ระดับ module ได้
5. [docs/spec.md:1174, :1223] R10-AC-15 ยังเขียนว่า replace ล้มแล้วเก็บ temp และ R10-Q-3 ยังเขียนว่า "ไม่ retry อัตโนมัติ" — ขัดกับ R12-5 ที่ผู้ใช้สั่ง (บันทึกไว้แค่ใน `docs/tasks.md:874`); ควรเพิ่มหมายเหตุใน spec / design ว่า R10-Q-3 ถูกแทนที่ (2026-11-23) เพื่อไม่ให้ Round ถัดไป "แก้กลับ"
6. [tests/test_r10_export_atomic_write.py:175-178, :880-888] ไม่มี test ที่ pin ค่าจริง `EXPORT_REPLACE_RETRY_DELAYS == (0.2, 0.5, 1.0)` (test ใช้ค่า patch ทั้งหมด) — ถ้ามีคนแก้เป็นค่ายาว ๆ จน worker รอนาน test ไม่จับ; เพิ่ม assert ค่าคงที่ หรือ `sum(...) <= 2.0` หนึ่งบรรทัด
7. [tests/test_database_connect_gui_core.py:488] ไม่มี unit test ตรงของ `write_json_atomic` สำหรับทาง `json.dump` ล้ม / `fsync` ล้ม / `BaseException` (ไฟล์เดิมคงอยู่, `.tmp` ถูกลบ, exception เดิม) — ปัจจุบันครอบคลุมผ่าน `os.replace` ล้มใน R8 / R6 เท่านั้น; reviewer ยืนยันพฤติกรรมด้วย probe แล้ว ถ้าต้องการ lock ไว้ให้เพิ่ม test เล็ก ๆ 3 กรณี
8. [tests/test_r8_load_jobs_writeback.py:305] comment `print raises AttributeError, swallowed` ไม่ตรงความจริง — CPython `print()` คืนค่าเงียบ ๆ เมื่อ `sys.stdout is None` (ไม่ raise); test ยังถูกต้อง (ยืนยันว่าโหลดสำเร็จเมื่อไม่มี console) แก้ comment ให้ตรงพอ
9. [database_connect_gui.py:5692-5694] หลัง R12-3 ตัวนับใน `askyesno` ข้าม element ที่ไม่ใช่ dict แต่ filter ใน `try` ยังเรียก `job.get` → ถ้า `saved_jobs` มี element เสียและผู้ใช้กด Yes จะได้ rollback + `Load Preset Failed: AttributeError` (ไม่มีข้อมูลหาย) — กรณีนี้เกิดไม่ได้จริงเพราะ `load_jobs` reject list ที่มี non-dict ตั้งแต่ตอนโหลด; ถ้าต้องการให้สม่ำเสมอ ใส่ `isinstance(job, dict)` ใน filter ด้วย (ต้องตัดสินว่าจะเก็บหรือทิ้ง element เสีย)
