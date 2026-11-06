# Robot Framework — Database Connector GUI

ชุดทดสอบอัตโนมัติจาก Test Case ในไฟล์ `TestCase_DatabaseConnector.xlsx`
ชื่อเทสใช้ ID เดียวกับในไฟล์ Excel (TC_3, TC_4, …)

## วิธีรัน

```bash
cd robot_tests
python -m robot --outputdir results testcases
```

ดูผลที่ `results/report.html` (สรุป) และ `results/log.html` (รายละเอียดทุก step)

รันเฉพาะบางเคส / บาง Scenario:

```bash
python -m robot --outputdir results -t "TC_10*" testcases
python -m robot --outputdir results -i High testcases
python -m robot --outputdir results -i "Script Groups" testcases
```

ต้องติดตั้ง: `pip install robotframework` (นอกนั้นใช้ library เดียวกับตัวโปรแกรม)

## ทำงานยังไง

- เทสเรียกโปรแกรมจริง (`database_connect_gui.py`) ผ่านปุ่ม / ฟังก์ชันของโปรแกรมเอง หน้าต่างโปรแกรมจะเปิดขึ้นมาระหว่างรัน **อย่าคลิกหรือพิมพ์ในหน้าต่างระหว่างเทสรัน**
- **ไม่แตะข้อมูลจริง:** ทุกเทสใช้โฟลเดอร์ชั่วคราวของตัวเอง (`db_profiles.json`, `saved_jobs.json`, `script_groups.json`, `app_settings.json`, `logs/`) แล้วลบทิ้งตอนจบ
- **ไม่ต่อ UAT / Production:** ปุ่ม Connect ผ่านโค้ดจริงของโปรแกรม แต่ฐานข้อมูลถูกเปลี่ยนเป็นไฟล์ SQLite ในโฟลเดอร์ชั่วคราว มีตารางทดสอบ `ACCOUNTS`, `TEST_TABLE`, `BIG_NUMBERS`
- ฐานข้อมูลทดสอบจำลองการยกเลิก Query แบบ Oracle (`cancel()`) ปุ่ม Stop จึงทดสอบได้ บน Oracle จริงจะได้ `ORA-01013` แทนข้อความ `interrupted`
- หน้าต่างถามยืนยัน / เลือกไฟล์ ถูกตอบโดยเทส (เช่น `ตอบหน้าต่างยืนยันถัดไปว่า    No`)
- Load Excel ทดสอบในขั้นแทนค่าใน SQL (เหมือนกด Confirm) โดยไม่เปิดหน้าต่างเลือกไฟล์

## เคสที่ยังต้องทดสอบมือ (6 เคส)

| ID | เรื่อง | เหตุผล |
|---|---|---|
| TC_1 | Connect เข้า Oracle UAT | ต้องใช้ฐานข้อมูลและ network จริง |
| TC_2 | Connect ด้วยรหัสผ่านผิด | ต้องการ Error จาก Oracle จริง (ORA-01017) |
| TC_6 | Export / Import Profile | หน้าต่าง Import มี Preview หลายขั้น ทดสอบมือเร็วกว่า |
| TC_7 | ผลลัพธ์ตรงกับ DBeaver | ต้องเทียบกับ DBeaver ด้วยตา |
| TC_15 | Load Excel ตอนไฟล์เปิดค้างใน Excel | ต้องเปิดไฟล์ใน Microsoft Excel จริง |
| TC_26 | Add SQL + Load Excel ในหน้าต่างกลุ่ม | หน้าต่างเลือกค่า Excel หลายขั้น |

## ไฟล์

```text
robot_tests/
├── DBConnectorLibrary.py          # keyword ภาษาไทย (Python)
├── testcases/
│   ├── 01_connection_profile.robot
│   ├── 02_execute_sql.robot
│   ├── 03_saved_jobs.robot
│   ├── 04_script_groups.robot
│   ├── 05_export_excel.robot
│   └── 06_stop_results_log.robot
└── results/                       # ผลการรัน (ไม่ commit)
```
