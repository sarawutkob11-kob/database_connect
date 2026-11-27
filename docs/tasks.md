# Tasks — database_connect_gui

> งานที่เสร็จแล้ว (Round 1–16) ถูกลบออกจากไฟล์นี้เพื่อลด token ตามคำสั่งผู้ใช้ — ดูย้อนหลังได้จาก git history (Round 1–15: `git show ef6d896:docs/<file>`, Round 16: `git show 1373c92:docs/<file>`)

## งานค้าง

### Round 17
- [x] R17-T1: `format_sql_value` รองรับ `np.floating` (จำนวนเต็ม → int, NaN → NULL)
  - QA: tests/test_r17_format_sql_value.py 12 test ผ่าน (fail 28 subTest กับ HEAD เดิม)
  - ไฟล์: `database_connect_gui.py` (developer), `tests/test_r17_format_sql_value.py` (qa ใหม่)
  - ทำอะไร: ตาม `docs/design.md` Round 17 — import numpy + แก้ 2 เงื่อนไข; qa เขียน test ครบทุกค่าใน AC
  - AC ที่ครอบคลุม: R17-AC-1..8, R17-AC-10
- [x] R17-T2: Regression full suite
  - QA: Ran 1540 tests OK ทั้ง PYTHONIOENCODING=utf-8 และไม่ตั้ง+redirect; git diff tests/ ว่าง
  - ไฟล์: — (ห้ามแก้ test เดิม ห้าม commit)
  - ทำอะไร: `python -m unittest discover -s tests -p "test_*.py"` ผ่านทั้งหมด (1528 + test ใหม่)
  - AC ที่ครอบคลุม: R17-AC-9

> Manual GUI checklist ผ่านครบแล้ว (AC-25 บน Oracle จริง ผู้ใช้ยืนยัน 2026-11-27)
