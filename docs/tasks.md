# Tasks — database_connect_gui

> งานที่เสร็จแล้ว (Round 1–16) ถูกลบออกจากไฟล์นี้เพื่อลด token ตามคำสั่งผู้ใช้ — ดูย้อนหลังได้จาก git history (Round 1–15: `git show ef6d896:docs/<file>`, Round 16: `git show 1373c92:docs/<file>`)

## งานค้าง — Manual GUI checklist (ผู้ใช้ทดสอบเอง)

> เตรียม: เปิดแอปด้วย `python database_connect_gui.py`, มี Profile ที่ต่อได้ และ Saved Jobs อย่างน้อย 2 ตัว (ควรมี 1 ตัวที่รันนาน เช่น query ที่ใช้เวลา 20-30 วินาที)
> query รันนานตัวอย่าง: Oracle `SELECT COUNT(*) FROM all_objects a, all_objects b WHERE ROWNUM < 50000000` / PostgreSQL `SELECT pg_sleep(30)` / MySQL `SELECT SLEEP(30)` / SQL Server `WAITFOR DELAY '00:00:30'`
> M2, M3, M9 และ B1 (Stop บน DB อื่น) ผู้ใช้ทดสอบบนจอจริงผ่านแล้ว (2026-11-27, branch fix/gui-walkthrough-bugs) — เหลือ AC-25 ที่ต้องใช้ Oracle จริง

- [ ] **AC-25 Job เดี่ยวบน Oracle: แถบเหลือง + Stop** (**ต้องใช้ Oracle จริง**)
  1. Connect Oracle แล้วกด ▶ ของ Job ที่รันนาน (เช่นชื่อ `Daily Balance`)
     - คาดหวัง: ภายใน ~0.5 วินาที แถบเหลืองขึ้น ข้อความ `กำลังรัน Job · Daily Balance · 00:0x` มีปุ่ม ⏹ Stop กดได้ และ status bar มุมล่างแสดง `Running…`
  2. กด ⏹ Stop
     - คาดหวัง: Execution Logs มี `⏹ Stop requested — cancelled 1 running query(ies)...` Job จบด้วย error `ORA-01013: user requested cancel` แถบเหลืองหายไป และ status bar กลับเป็น `Ready`
