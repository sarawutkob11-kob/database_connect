# Spec — database_connect_gui

> งานที่เสร็จแล้ว (Round 1–16) ถูกลบออกจากไฟล์นี้เพื่อลด token ตามคำสั่งผู้ใช้ — ดูย้อนหลังได้จาก git history (Round 1–15: `git show ef6d896:docs/<file>`, Round 16: `git show 1373c92:docs/<file>`)

## Round 17 — `format_sql_value` รองรับ numpy.float32 (review R15 ข้อเสนอแนะ 🟢 ข้อ 1)

> สถานะ: **ผู้ใช้อนุมัติแล้ว** (2026-11-27) — R17-Q-1 = แก้ด้วย (R17-AC-10)

ที่มา: ผู้ใช้สั่งทำข้อนี้ข้อเดียว (2026-11-27)

### เป้าหมาย
`format_sql_value` (`database_connect_gui.py` ~:990) แปลง float ที่เป็นจำนวนเต็มเป็น int แล้ว (R15 BH-12) แต่เช็กแค่ `isinstance(value, float)` ทำให้ `numpy.float32(1001.0)` / `numpy.float16` ยังได้ `1001.0` (เพราะไม่ใช่ subclass ของ `float` ส่วน float64 เป็น subclass จึงผ่านอยู่แล้ว) ผลที่ได้คือ SQL literal ที่ออกมาไม่ตรงกันระหว่าง float แต่ละชนิด ผู้ได้ประโยชน์คือผู้ใช้ที่ render SQL จากข้อมูลที่มี dtype float32/float16

### ขอบเขต
- In scope: ให้ float ทุกชนิดของ numpy (`numpy.floating`) ที่เป็นจำนวนเต็มออกมาเป็น int แบบเดียวกับ `float` (แนวทางที่ review เสนอคือ `isinstance(value, (float, np.floating))`)
- Out of scope: ข้อเสนอแนะอื่นใน `docs/review.md`, การจัดรูปแบบ datetime (R15-Q-9), การเปลี่ยนพฤติกรรมของ inf และของค่าที่ไม่ใช่จำนวนเต็ม

### User story
ในฐานะผู้ใช้ที่ render SQL จากข้อมูลตาราง ฉันต้องการให้ `numpy.float32(1001.0)` ออกมาเป็น `1001` เหมือน float64 เพื่อให้ได้ SQL literal ที่สม่ำเสมอ

### Acceptance criteria
- **R17-AC-1**: Given `numpy.float32(1001.0)` When เรียก `format_sql_value` Then ได้ `"1001"`
- **R17-AC-2**: Given `numpy.float16(5.0)` และ `numpy.float32(-3.0)` และ `numpy.float32(0.0)` When เรียก Then ได้ `"5"`, `"-3"`, `"0"` ตามลำดับ
- **R17-AC-3**: Given `numpy.float32(1.5)` (ไม่ใช่จำนวนเต็ม) When เรียก Then ได้ผลเท่ากับ `str(numpy.float32(1.5))` แบบเดิม (คือ `"1.5"`)
- **R17-AC-4**: Given `float('nan')`, `numpy.float64('nan')` และ `None` When เรียก Then ได้ `"NULL"` เหมือนเดิม
- **R17-AC-5**: Given `True`, `False`, `numpy.bool_(True)`, `numpy.bool_(False)` When เรียก Then ได้ `"1"`, `"0"`, `"1"`, `"0"` เหมือนเดิม (ห้ามเข้าเงื่อนไขของ float)
- **R17-AC-6**: Given `1001.0`, `numpy.float64(1001.0)`, `1.5`, `numpy.float64(2.25)` When เรียก Then ได้ `"1001"`, `"1001"`, `"1.5"`, `"2.25"` เหมือนเดิม
- **R17-AC-7**: Given `float('inf')`, `numpy.float32('inf')` When เรียก Then ไม่เกิด exception และได้ผลเท่ากับ `str(value)` (`"inf"`) ซึ่งเหมือนพฤติกรรมเดิมของ float64 (`inf.is_integer()` เป็น False)
- **R17-AC-8**: Given ค่าชนิดอื่น (`int`, `numpy.int64`, `str`, `decimal.Decimal`) When เรียก Then ได้ผลเดิมทุกตัว
- **R17-AC-9**: Given test ใหม่ใน `tests/test_r17_*.py` (ห้ามแก้ test เดิม) When รัน `python -m unittest discover -s tests -p "test_*.py"` Then ผ่านทั้งหมด (ปัจจุบัน 1528 + test ใหม่) และไม่มีการ commit
- **R17-AC-10**: Given `numpy.float32('nan')` / `numpy.float16('nan')` When เรียก `format_sql_value` Then ได้ `"NULL"` (เพิ่มตาม R17-Q-1)

### ข้อจำกัด / สมมติฐาน
- ไฟล์ยังไม่ได้ `import numpy` โดยตรง (มีแค่ `pandas as pd`) แต่ numpy ติดมากับ pandas อยู่แล้ว จะ import numpy เพิ่มหรือใช้ `pd.api.types.is_float` ก็ได้ ให้ architect เลือก
- float32 ที่ค่าใหญ่มาก (เช่น `numpy.float32(1e20)`) ถือเป็นจำนวนเต็ม แปลงด้วย `int()` ได้เลขตามความละเอียดของ float32 ซึ่งตรงกับพฤติกรรมเดิมของ float64 ที่ค่าใหญ่ (เช่น `1e20` → `"100000000000000000000"`) ไม่ถือเป็นปัญหา

### คำถาม (ตอบแล้ว)
- **R17-Q-1**: ตอนนี้ `numpy.float32('nan')` ได้ `"nan"` ไม่ใช่ `"NULL"` (เงื่อนไข NaN ที่ :984 ก็เช็กแค่ `float` เหมือนกัน) จะให้แก้ไปด้วยเลยไหม — **ค่าแนะนำ: แก้ด้วย** (NaN ทุกชนิดได้ `NULL` ซึ่งเป็นสาเหตุเดียวกันและแก้เพิ่มแค่บรรทัดเดียว) ถ้าผู้ใช้ตกลงจะเพิ่มเป็น R17-AC-10: Given `numpy.float32('nan')` / `numpy.float16('nan')` When เรียก Then ได้ `"NULL"`
