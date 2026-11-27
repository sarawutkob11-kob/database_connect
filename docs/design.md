# Design — database_connect_gui

> งานที่เสร็จแล้ว (Round 1–16) ถูกลบออกจากไฟล์นี้เพื่อลด token ตามคำสั่งผู้ใช้ — ดูย้อนหลังได้จาก git history (Round 1–15: `git show ef6d896:docs/<file>`, Round 16: `git show 1373c92:docs/<file>`)

## Round 17 — `format_sql_value` รองรับ numpy float ทุกชนิด

**วิธี:** เพิ่ม `import numpy as np` (ติดมากับ pandas อยู่แล้ว) แล้วใช้ `isinstance(value, (float, np.floating))` แทน `isinstance(value, float)` ทั้ง 2 จุด
- ไม่ใช้ `pd.api.types.is_float` เพราะ API นั้นไม่ได้ระบุชัดว่าครอบ float16 และอ่านยากกว่า; `np.floating` ตรงกับข้อเสนอของ review และครอบ float16/32/64 (+longdouble)
- `np.bool_`, `int`, `np.int64`, `Decimal` ไม่ใช่ `np.floating` → พฤติกรรมเดิม (AC-5, AC-8)

**จุดที่แก้ (`database_connect_gui.py` เท่านั้น):**
- import บนสุดของไฟล์: `import numpy as np`
- `format_sql_value` (~:984) เงื่อนไข NaN → `isinstance(value, (float, np.floating)) and value != value` (AC-4, AC-10)
- (~:990) เงื่อนไขจำนวนเต็ม → `isinstance(value, (float, np.floating)) and value.is_integer()` → `str(int(value))` (AC-1, 2, 6); inf ได้ `is_integer()` False → `str(value)` เดิม (AC-7); ไม่ใช่จำนวนเต็ม → `str(value)` เดิม (AC-3)
- signature ไม่เปลี่ยน: `format_sql_value(value: Any) -> str`

**ความเสี่ยง:** ต่ำ — `np.floating.is_integer()` มีตั้งแต่ numpy 1.22 (ถ้า numpy เก่ากว่าจะ AttributeError; ใช้ `float(value).is_integer()` แทนได้เพื่อเลี่ยง) ไม่มีผลกับ caller อื่น (`format_sql_value_list` ได้ผลตามไปเอง)
