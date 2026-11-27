# Code Review — database_connect_gui

> งานที่เสร็จแล้ว (Round 1–15) ถูกลบออกจากไฟล์นี้เมื่อ 2026-11-27 เพื่อลด token ตามคำสั่งผู้ใช้ — ดูย้อนหลังได้จาก git history (`git show ef6d896:docs/<file>`) เลขบรรทัดที่อ้างถึง docs เดิมอาจไม่ตรงแล้ว

## ข้อเสนอแนะที่ยังไม่ได้ทำ (จาก Code Review Round 15, 2026-11-24 — ผล Round 15: ผ่าน 🔴 0 🟡 0)

1. [database_connect_gui.py:990] `format_sql_value(numpy.float32(1001.0))` ยังได้ `1001.0` เพราะ `numpy.float32` ไม่ใช่ subclass ของ `float` (`float64` ผ่านแล้ว) — เกิดได้เฉพาะ df ที่ผู้ใช้/driver ให้ dtype float32 ซึ่ง `read_sql` ปกติไม่ให้ จึงไม่กระทบ AC; ถ้าจะครอบให้ใช้ `isinstance(value, (float, np.floating))`
2. [database_connect_gui.py:12052 / :13405] เมื่อ editor ≠ SQL ที่ render ไว้ การ sync เกิด**ก่อน**เปิด dialog — ถ้าผู้ใช้กด Cancel ค่า Excel ที่ track ไว้ก็ถูกล้างไปแล้ว (แถบ Excel ในหน้าหลักหายไป) แม้ไม่ได้ Reset อะไร. เป็นพฤติกรรมเดียวกับ Edit Job และตรงกับ R15-5 ("หลัง sync ค่าที่ track ถูกล้าง") จึงไม่ใช่บัค แค่บันทึกไว้เป็นพฤติกรรมที่ผู้ใช้อาจสังเกตเห็น
3. [database_connect_gui.py:11912-11919 / :11965-11968] เงื่อนไขกรอง "Job ของ Profile" เขียนซ้ำสองที่ (`delete_profile` และ `_delete_profile_jobs_and_groups`) — ถ้าภายหลังเปลี่ยนกฎ (เช่นตัดช่องว่างชื่อ) ต้องแก้สองจุด; อาจส่ง list ที่นับไว้แล้วเข้า helper หรือแยก predicate เล็ก ๆ. ไม่กระทบผล
4. [database_connect_gui.py:546-561] db_type ที่ไม่รู้จัก (เช่น SQLite) ตกไปใช้กฎ quote ของ PostgreSQL — ตรงกับ design (เดิมก็ตกไป branch PostgreSQL) และ schema จาก inspector ไม่เป็น `None` ในทางปกติ; ถ้าเพิ่ม DB ชนิดใหม่ในอนาคตควรเพิ่ม branch ให้ชัด
5. [database_connect_gui.py:10403] ข้อความ `⛔ Stopped — ... not run` ใช้ `self.root.after` ตามแบบบรรทัด Stop เดิม `:10285` (นอก scope BH-13 ตาม R15-5) — ถ้าเปิด Edit Job ระหว่าง Run all ข้อความนี้จะถูก schedule บน dialog; `after(0)` ทำงานทันทีจึงแทบไม่มีโอกาสหาย ไม่ต้องแก้ใน Round นี้

ข้อสังเกตนอกขอบเขต (ไม่นับเป็นปัญหาของ Round 15): R15-Q-9 datetime ใน `format_sql_value`, ตาราง `"0012"` ที่ Tk แปลงเป็น `12` (ทั้งค่าในแถวและข้อความหัวตารางที่ `copy_selected_rows` อ่านจาก `tree.heading(col, "text")`), และโค้ดที่ไม่มีผู้เรียก (`reset_single_parameter`) — คงไว้ตามที่ตกลง

# Code Review — Round 16 (Bugfix B1, B2, B3) — 2026-11-27

## สรุป
**ผ่าน** — 🔴 0, 🟡 0, 🟢 3

ขอบเขต: `git diff HEAD -- database_connect_gui.py` (+85 บรรทัด) และ test ใหม่ `tests/test_r16_stop_lines.py`, `tests/test_r16_import_saved_jobs.py`, `tests/test_r16_jobs_scrollbar.py` (รันซ้ำ 105 tests OK). diff ตรงกับ design R16 แบบ minimal ไม่พบงานเกิน spec
- ความปลอดภัย: บรรทัด Stop ที่นำกลับมาแสดง (`_replay_stop_lines` :8382-8390) เป็นข้อความคงที่ + ตัวเลข ไม่มีรหัสผ่าน และเขียนผ่าน `_results_text_raw_insert` จึงไม่ลง run log ซ้ำ; ข้อความ error ของ B2 (:1173-1180) มีเพียงชื่อ item จากไฟล์ที่ผู้ใช้เลือกเอง
- ความถูกต้อง: `_stop_lines` ถูกล้างตอนเริ่มทุกงานที่ล้าง Logs ตอนจบ (`_start_stoppable_run` :8378 สำหรับ Job / SQL Editor / Run all / Export และ `list_tables` :9522 ซึ่งไม่เรียก `_start_stoppable_run`) และทุกจุดเริ่มงานผ่าน `_block_if_busy` จึงไม่มีงานสองตัวที่ล้างรายการของกันและกัน; ปุ่ม Retry ใน dialog error เรียก `execute_query` (ซึ่งล้างรายการ) จึงไม่นำบรรทัด Stop เก่ากลับมา; การเรียกตอน**เริ่ม** Job (:10176, :10307) ยังใช้ `keep_stop_lines=False` (R16-AC-6)

## Verdict ราย R16-AC
| AC | ผล | หลักฐาน |
|---|---|---|
| R16-AC-1, 2, 8 | ผ่าน | `finish` → `_start_job_result_report(keep_stop_lines=True)` :10197; test AC1/AC2/AC8 ใน `test_r16_stop_lines.py` assert ข้อความ Logs ทั้งก้อน (บรรทัด Stop ก่อนผล, ครั้งเดียว, ตามลำดับ) |
| R16-AC-3 | ผ่าน | `_clear_results_keep_stop_lines` ที่ :7189, :8787, :8817, :8847 ครบ 4 ทาง รวม dialog ปิด/เปิด |
| R16-AC-4 | ผ่าน | :9825; ทาง error / list ว่างไม่ล้าง Logs → บรรทัดเดียวเดิม (test :464, :477) |
| R16-AC-5 | ผ่าน | ไม่มี Stop → `_replay_stop_lines` ไม่ insert อะไร; test assert ข้อความเท่ากับผลเดิมทุกตัวอักษร |
| R16-AC-6 | ผ่าน | ล้างรายการตอนเริ่มงาน; Stop ตอน idle return ก่อน append (:8493-8494) |
| R16-AC-7 | ผ่าน | `_install_run_log_hook` :8398-8410 เก็บ raw insert; test นับ `Stop requested` ใน run log = จำนวนครั้งที่กด |
| R16-AC-9 | ผ่าน | Run all / Export ไม่เรียก helper ใหม่ (ไม่ล้าง Logs ตอนจบ); test เดิมไม่ถูกแก้ |
| R16-AC-10..12 | ผ่าน | ตรวจ item แบบ Job ก่อนกรอง :1173-1180 ทั้ง bare list และ `{"groups": ...}` รวมไฟล์ผสม; label `item N` นับตามลำดับใน list ดิบ |
| R16-AC-13 | ผ่าน | item ที่มี `scripts` (แม้ไม่ใช่ list) หรือไม่มี `query` ไม่โดนกฎใหม่; test round-trip export / ไฟล์ภายในแอปผ่าน |
| R16-AC-14, 16 | ผ่าน | `pack(..., before=jobs_canvas)` :3039 และตรวจด้วย `winfo_manager()` → ไม่ pack ซ้ำ |
| R16-AC-15 | ผ่าน (มีเงื่อนไข) | ส่วนตรวจพิกเซลแทนด้วยตรวจสถานะ pack ตาม R16-R1 ที่ผู้ใช้อนุมัติ (`tests/test_r16_jobs_scrollbar.py:7-12`); ยังเหลือตรวจด้วยตาบนหน้าต่างจริงตาม R16-R2 (Manual) |
| R16-AC-17 | ผ่าน | ตามรายงาน QA: full suite 1528 OK ทั้งสอง encoding |

## 🔴 Critical (ต้องแก้ก่อน merge)
- ไม่มี

## 🟡 Warning (ควรแก้)
- ไม่มี

## 🟢 Suggestion (ทางเลือก)
- [database_connect_gui.py:8517] `self.__dict__.setdefault("_stop_lines", []).append(msg)` ใช้รูปแบบต่างจากจุดอื่น (`getattr` ที่ :8385 และ attribute ตรง ๆ ที่ :8378) — มีไว้เพื่อ stub ที่สร้างด้วย `__new__` ทำงานได้ถูกต้อง แต่อ่านยาก; ถ้าต้องการให้สม่ำเสมออาจทำ helper เล็ก ๆ หรือใส่ comment สั้น ๆ. ไม่กระทบผล
- [database_connect_gui.py:8392-8396] `_stop_lines` ยังค้างอยู่หลังงานจบจนกว่างานถัดไปจะเริ่ม — ตอนนี้ถูกต้องเพราะผู้เรียก helper ทุกตัวเป็น callback ตอนจบของงานที่ล้างรายการตอนเริ่มแล้ว แต่ถ้าในอนาคตมีจุดใหม่เรียก `_clear_results_keep_stop_lines` นอกงานที่เริ่มผ่าน `_start_stoppable_run` / `list_tables` จะนำบรรทัด Stop ของงานเก่ากลับมา; อาจเพิ่มข้อความใน docstring ว่า "เรียกได้เฉพาะตอนจบงาน"
- [tests/test_r16_import_saved_jobs.py:447-455] `TestSourceShape` ตรวจ source code / docstring (`inspect.getsource`, `"Saved Job" in __doc__`) แทนพฤติกรรม — พังได้เมื่อ refactor หรือแก้คำใน docstring แม้พฤติกรรมไม่เปลี่ยน; พฤติกรรมเดียวกันมี test แบบ dialog / sidebar ครอบอยู่แล้ว (:338-365) จึงลบหรือลดได้
