# Code Review — database_connect_gui

> งานที่เสร็จแล้ว (Round 1–16) ถูกลบออกจากไฟล์นี้เพื่อลด token ตามคำสั่งผู้ใช้ — ดูย้อนหลังได้จาก git history (Round 1–15: `git show ef6d896:docs/<file>`, Round 16: `git show 1373c92:docs/<file>`)

## ข้อเสนอแนะที่ยังไม่ได้ทำ (จาก Code Review Round 15, 2026-11-24 — ผล Round 15: ผ่าน 🔴 0 🟡 0)

1. [database_connect_gui.py:990] `format_sql_value(numpy.float32(1001.0))` ยังได้ `1001.0` เพราะ `numpy.float32` ไม่ใช่ subclass ของ `float` (`float64` ผ่านแล้ว) — เกิดได้เฉพาะ df ที่ผู้ใช้/driver ให้ dtype float32 ซึ่ง `read_sql` ปกติไม่ให้ จึงไม่กระทบ AC; ถ้าจะครอบให้ใช้ `isinstance(value, (float, np.floating))`
2. [database_connect_gui.py:12052 / :13405] เมื่อ editor ≠ SQL ที่ render ไว้ การ sync เกิด**ก่อน**เปิด dialog — ถ้าผู้ใช้กด Cancel ค่า Excel ที่ track ไว้ก็ถูกล้างไปแล้ว (แถบ Excel ในหน้าหลักหายไป) แม้ไม่ได้ Reset อะไร. เป็นพฤติกรรมเดียวกับ Edit Job และตรงกับ R15-5 ("หลัง sync ค่าที่ track ถูกล้าง") จึงไม่ใช่บัค แค่บันทึกไว้เป็นพฤติกรรมที่ผู้ใช้อาจสังเกตเห็น
3. [database_connect_gui.py:11912-11919 / :11965-11968] เงื่อนไขกรอง "Job ของ Profile" เขียนซ้ำสองที่ (`delete_profile` และ `_delete_profile_jobs_and_groups`) — ถ้าภายหลังเปลี่ยนกฎ (เช่นตัดช่องว่างชื่อ) ต้องแก้สองจุด; อาจส่ง list ที่นับไว้แล้วเข้า helper หรือแยก predicate เล็ก ๆ. ไม่กระทบผล
4. [database_connect_gui.py:546-561] db_type ที่ไม่รู้จัก (เช่น SQLite) ตกไปใช้กฎ quote ของ PostgreSQL — ตรงกับ design (เดิมก็ตกไป branch PostgreSQL) และ schema จาก inspector ไม่เป็น `None` ในทางปกติ; ถ้าเพิ่ม DB ชนิดใหม่ในอนาคตควรเพิ่ม branch ให้ชัด
5. [database_connect_gui.py:10403] ข้อความ `⛔ Stopped — ... not run` ใช้ `self.root.after` ตามแบบบรรทัด Stop เดิม `:10285` (นอก scope BH-13 ตาม R15-5) — ถ้าเปิด Edit Job ระหว่าง Run all ข้อความนี้จะถูก schedule บน dialog; `after(0)` ทำงานทันทีจึงแทบไม่มีโอกาสหาย ไม่ต้องแก้ใน Round นี้

ข้อสังเกตนอกขอบเขต (ไม่นับเป็นปัญหาของ Round 15): R15-Q-9 datetime ใน `format_sql_value`, ตาราง `"0012"` ที่ Tk แปลงเป็น `12` (ทั้งค่าในแถวและข้อความหัวตารางที่ `copy_selected_rows` อ่านจาก `tree.heading(col, "text")`), และโค้ดที่ไม่มีผู้เรียก (`reset_single_parameter`) — คงไว้ตามที่ตกลง

## ข้อเสนอแนะที่ยังไม่ได้ทำ (จาก Code Review Round 16, 2026-11-27 — ผล Round 16: ผ่าน 🔴 0 🟡 0)

- [database_connect_gui.py:8517] `self.__dict__.setdefault("_stop_lines", []).append(msg)` ใช้รูปแบบต่างจากจุดอื่น (`getattr` ที่ :8385 และ attribute ตรง ๆ ที่ :8378) — มีไว้เพื่อ stub ที่สร้างด้วย `__new__` ทำงานได้ถูกต้อง แต่อ่านยาก; ถ้าต้องการให้สม่ำเสมออาจทำ helper เล็ก ๆ หรือใส่ comment สั้น ๆ. ไม่กระทบผล
- [database_connect_gui.py:8392-8396] `_stop_lines` ยังค้างอยู่หลังงานจบจนกว่างานถัดไปจะเริ่ม — ตอนนี้ถูกต้องเพราะผู้เรียก helper ทุกตัวเป็น callback ตอนจบของงานที่ล้างรายการตอนเริ่มแล้ว แต่ถ้าในอนาคตมีจุดใหม่เรียก `_clear_results_keep_stop_lines` นอกงานที่เริ่มผ่าน `_start_stoppable_run` / `list_tables` จะนำบรรทัด Stop ของงานเก่ากลับมา; อาจเพิ่มข้อความใน docstring ว่า "เรียกได้เฉพาะตอนจบงาน"
- [tests/test_r16_import_saved_jobs.py:447-455] `TestSourceShape` ตรวจ source code / docstring (`inspect.getsource`, `"Saved Job" in __doc__`) แทนพฤติกรรม — พังได้เมื่อ refactor หรือแก้คำใน docstring แม้พฤติกรรมไม่เปลี่ยน; พฤติกรรมเดียวกันมี test แบบ dialog / sidebar ครอบอยู่แล้ว (:338-365) จึงลบหรือลดได้
