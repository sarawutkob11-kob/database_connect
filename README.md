# Database Connector GUI

โปรแกรม GUI (Python + Tkinter) สำหรับเชื่อมต่อฐานข้อมูลและรัน SQL Query เก็บ Query ไว้เป็น **Job** ได้ สั่งรันหลาย Job ทีเดียวแล้ว Export ผลลัพธ์รวมเป็นไฟล์ Excel ไฟล์เดียว ผลลัพธ์ที่แสดงและที่ Export ออกมาจัดรูปแบบตรงกับที่เห็นใน DBeaver

## ฐานข้อมูลที่รองรับ

| Database             | Driver (SQLAlchemy)             | Port เริ่มต้น | หมายเหตุ                                                  |
| -------------------- | ------------------------------- | ------------ | --------------------------------------------------------- |
| Oracle               | `oracle+oracledb` (thin mode)   | 1521         | ไม่ต้องติดตั้ง Oracle Client, ช่อง Database = Service Name |
| PostgreSQL           | `postgresql+pg8000`             | 5432         |                                                           |
| MySQL                | `mysql+pymysql`                 | 3306         |                                                           |
| Microsoft SQL Server | `mssql+pyodbc` (`{SQL Server}`) | 1433         | ถ้าไม่ระบุ Database จะต่อเข้า `master`                      |

ช่อง Database เป็น optional (ยกเว้นต้องการระบุ Service Name / Database เฉพาะ)

## หน้าจอหลัก

- **แถบบน**: เลือก Profile, ปุ่ม **✎ Details** (เปิด/ปิดช่องกรอก Host, Port, Database, User, Password), สถานะการเชื่อมต่อ, ปุ่ม **🔌 Connect** และปุ่มจัดการ Profile ด้านขวา
- **แถบซ้าย**: รายการ **🕘 Saved Jobs** และแท็บ **▤ Script Groups** ด้านล่างสุดเป็นปุ่ม Preset
- **ตรงกลาง**: SQL Editor ด้านบน และผลลัพธ์ด้านล่าง ลากเส้นแบ่งเพื่อปรับขนาดได้ แถบด้านซ้ายก็ลากปรับความกว้างได้
- **แถบสถานะล่างสุด**: สถานะ Ready / Running…, การเชื่อมต่อ, จำนวน Excel parameter ที่ใส่อยู่, ไฟล์ log ของวันนี้ และตำแหน่ง cursor (Ln / Col)

## ความสามารถหลัก

### 1. Connection Profiles

- **＋ New** — เปิดหน้าต่างสร้าง Profile ใหม่: เลือกชนิดฐานข้อมูลจากการ์ด (Port เปลี่ยนให้ตามชนิด) กรอกข้อมูล แล้วกด **🔌 ทดสอบการเชื่อมต่อ** ก่อน **＋ สร้าง Profile** ได้
- **Save** — บันทึกค่าที่แก้ในช่อง Details กลับเข้า Profile
- **Import / Export** — นำเข้า/ส่งออก Profile เป็นไฟล์ JSON (Import มี Preview ให้เลือก **Merge** หรือ **Replace**)
- เมนู **⋯** มี **Delete profile** และ **Config file location** (แสดงตำแหน่งไฟล์ config พร้อมปุ่มเปิดโฟลเดอร์ / คัดลอก path)
- ใต้ชื่อ Profile แสดง Host และ Database / Service ที่จะต่อ
- โหลด Profile ที่ใช้ล่าสุดให้อัตโนมัติเมื่อเปิดโปรแกรม
- รหัสผ่านถูกเข้ารหัสด้วย Windows DPAPI (ผูกกับ Windows user account) ส่วน Profile เก่าที่เก็บรหัสผ่านเป็น plain text ยังอ่านได้ และจะถูกเข้ารหัสเมื่อบันทึกครั้งถัดไป
  - ถ้าคัดลอก `db_profiles.json` ไปใช้กับ user/เครื่องอื่น ต้องกรอกรหัสผ่านใหม่
- เปลี่ยน Profile แล้วจะ reset การเชื่อมต่อและแสดงเฉพาะ Job ของ Profile นั้น
- ถ้า connection ถูกตัดระหว่างเปิดโปรแกรมทิ้งไว้ (เช่น `ORA-03113`, `DPI-1080`) โปรแกรมจะตรวจก่อนใช้งานและต่อใหม่ให้เอง ส่วน connection ที่เก่ากว่า 30 นาทีจะถูกเปลี่ยนใหม่

### 2. SQL Editor

- **▶ Run** หรือ `Ctrl+Enter` — รัน Query ใน background thread (UI ไม่ค้าง) มีหน้าต่าง Loading พร้อมปุ่ม **Retry / Show Details** เมื่อเกิด error
- รองรับ `SELECT` / `WITH` (แสดงผลเป็นตาราง) และ `INSERT` / `UPDATE` / `DELETE` / DDL (แสดงจำนวน rows affected)
- ตัด `;` หรือ `/` ท้าย Query ให้อัตโนมัติ (เหมือน DBeaver)
- มีเลขบรรทัดและสี syntax (keyword, string, parameter, comment) สีใช้แสดงผลอย่างเดียว ไม่แก้ข้อความ SQL
- `Ctrl+Z` / `Ctrl+Y` / `Ctrl+C` / `Ctrl+X` / `Ctrl+V` / `Ctrl+A` ใช้ได้ทั้งตอนแป้นพิมพ์เป็นภาษาไทยและอังกฤษ และมีเมนูคลิกขวา Cut / Copy / Paste / Select All
- แถบเครื่องมือเหนือ Editor: **📗 Load Excel**, **↩ Reset template**, **💾 Save as Job**, **▦ Tables** (ดูรายการ Table ของฐานข้อมูล)
- **ยืนยันก่อนแก้ข้อมูล** — ก่อนรันคำสั่งที่ไม่ใช่ `SELECT` (UPDATE / INSERT / DELETE / DDL) จะแสดงรายการคำสั่ง พร้อม Profile, Host และ Database ให้ยืนยันก่อน (ค่าตั้งต้นคือ **No**) ใช้กับ Run, Run Job, Run all และ Run Group ส่วน `SELECT` จะไม่ถาม
- **⏹ Stop** — กดได้ระหว่างที่มี Query / Job กำลังรัน (มีข้างปุ่ม Run, ในแถบสีเหลืองที่ขึ้นเหนือผลลัพธ์ระหว่างรัน และในหน้าต่าง Script Groups)
  - Oracle: ยกเลิก Query ที่กำลังรันทันที (`ORA-01013: user requested cancel`)
  - Job ที่เหลือใน Run all / Run Group / Export จะถูกข้าม
  - PostgreSQL / MySQL / SQL Server: driver ยกเลิกกลางทางไม่ได้ Query ปัจจุบันจะรันจนจบ แล้วข้าม Job ที่เหลือ
- ระหว่างรันหลาย Job แถบสีเหลืองเหนือผลลัพธ์จะบอกว่ากำลังรัน Job ไหน (Job i / N) พร้อม progress bar

### 3. Excel Parameters (แทนค่าใน SQL จากไฟล์ Excel)

ใช้ค่าจากคอลัมน์ใน Excel (เช่นรายการเลขบัญชี) ไปแทนในเงื่อนไข SQL

1. เขียน SQL ที่มี parameter เช่น
   ```sql
   SELECT * FROM ACCOUNTS WHERE ACCOUNT_NO IN ({ACCOUNT_LIST})
   ```
   รองรับรูปแบบ `{NAME}`, `{{NAME}}`, `:name`, รายการ `IN (...)` ว่างตัวแรก หรือสร้าง `WHERE <column> IN (...)` ให้อัตโนมัติจากชื่อคอลัมน์ใน Excel
2. กด **📗 Load Excel** → เลือก Sheet และ parameter ที่จะใส่แทน
3. ① เลือกคอลัมน์ → ② เลือกค่า (มีช่องค้นหา, **☑ Select All** และ **ล้างที่เลือก**) → ③ ตรวจค่าที่เลือกและดู "SQL ที่จะได้" → **✓ Confirm · ใส่ค่าใน SQL**
4. ค่าตัวเลขใส่ตรง ๆ ค่าข้อความใส่ `'...'` และ escape `'` ให้อัตโนมัติ
5. หลังใส่ค่าแล้ว จะมีแถบสีฟ้าเหนือ Editor บอก parameter ที่ใส่อยู่ กด **✎ เปลี่ยนค่า** เพื่อเลือกค่าใหม่ได้
6. **↩ Reset template** — หน้าจอแบบเดียวกับ Load Excel: ① เลือกคอลัมน์/parameter ② ติ๊กค่าในคอลัมน์นั้นที่ต้องการเอาออก ③ ดูค่าที่จะ Reset และ SQL หลัง Reset แล้วกด **↩ Confirm · Reset ค่าที่เลือก** (เลือกได้หลายคอลัมน์; ถ้าเอาออกครบทุกค่า คอลัมน์นั้นจะกลับเป็น placeholder เดิม) หรือกด **Reset All Parameters**

อ่านไฟล์ Excel ได้แม้ไฟล์กำลังเปิดอยู่ใน Excel ค่า parameter ที่เลือกจะถูกเก็บไว้กับ Job ด้วย

### 4. Results

แท็บผลลัพธ์ด้านล่างมี 3 แท็บ

- **📊 Results Grid** — ตารางผลลัพธ์ แบ่งหน้าละ 1,000 แถว (ปุ่ม ◀ / Next ▶) และ **📗 Export Excel** / **📄 Export CSV** ได้ทันที
  - เมื่อรันหลาย Job จะมีปุ่มเลือกชุดผลลัพธ์ (มี ▾) ให้สลับดูผลของแต่ละ Job
  - เคลียร์ผลเก่าทุกครั้งที่เริ่มรันใหม่ และแสดงข้อความเมื่อ Job ล้มเหลวหรือไม่มี result set
- **📋 Execution Logs** — log การเชื่อมต่อ การรัน Job และการ Export
  - บันทึกลงไฟล์ `logs/run_YYYY-MM-DD.log` ด้วย (วันละไฟล์ มีเวลากำกับทุกบรรทัด) ทุกการรันมีบรรทัดหัวบอก Profile / User / Host / Database และบันทึก SQL ของแต่ละ Job แต่**ไม่บันทึกรหัสผ่าน**
  - ไฟล์ log ที่เก่ากว่า 90 วันจะถูกลบอัตโนมัติ, ปุ่ม **📂 Open Log Folder** เปิดโฟลเดอร์ log
- **🐛 Error & Debug** — รายละเอียด error ล่าสุด (Error type, message, SQL, traceback) พร้อมปุ่ม Copy ถ้ามี error ใหม่ที่ยังไม่ได้เปิดดู ชื่อแท็บจะมีจุด ● ต่อท้าย

ช่อง **Open result windows** มุมขวาบนของแท็บผลลัพธ์: ติ๊ก = เปิดผลของแต่ละ Query เป็น popup แยกด้วย (ค่าเริ่มต้น), ไม่ติ๊ก = ดูผลใน Results Grid อย่างเดียว (โปรแกรมจำค่าไว้ใน `app_settings.json`)

popup ผลลัพธ์เปิดบนจอเดียวกับหน้าต่างหลัก และวางเหลื่อมกันเมื่อมีหลาย popup มีปุ่ม First / Previous / Next / Last, Copy Selected, Export CSV / Excel และคลิกหัวคอลัมน์เพื่อ sort ได้

### 5. การแสดงผลให้ตรงกับ DBeaver

- ชื่อคอลัมน์ตามที่ฐานข้อมูลส่งกลับมา (Oracle = ตัวพิมพ์ใหญ่)
- Oracle `NUMBER` อ่านเป็น `Decimal` เลขยาวจึงไม่ถูกปัดเศษ
- CLOB / NCLOB / BLOB อ่านเป็นข้อความ / hex
- `NULL` แสดงเป็น `[NULL]`
- วันที่/เวลา: `yyyy-MM-dd HH:mm:ss.SSS`, `yyyy-MM-dd`, `HH:mm:ss`

### 6. Saved Jobs

- **＋** (มุมขวาบนของแถบซ้าย) หรือ **💾 Save as Job** — บันทึก Query ปัจจุบัน (รวมสถานะ Excel parameter) เป็น Job ของ Profile ที่เลือก
- แต่ละ Job แสดงลำดับ ชื่อ และ SQL บรรทัดแรก (เอาเมาส์ชี้เพื่อดูชื่อเต็มและ SQL) มีปุ่ม **▶** (Run), **✎** (Edit) และ **🗑** (Delete) หน้า Edit มีเครื่องมือ Excel parameter ในตัว
- ติ๊ก checkbox เพื่อเลือก Job หรือ **Select all** จะเห็นจำนวนที่เลือก และปุ่ม **🗑 Delete (n)** / **🗑 Delete all**
- **▶ Run all** — ถ้าติ๊ก Job ไว้ ปุ่มจะเปลี่ยนเป็น **▶ Run selected (n)** และรันเฉพาะที่ติ๊ก ถ้าไม่ติ๊กเลยจะรันทุก Job ของ Profile รันทีละตัว Job ที่ error จะไม่หยุดการรัน ตอนจบแสดงสรุปจำนวน Success / Failed
  - ระหว่างรันจะกดซ้ำไม่ได้ และ popup ผลลัพธ์ของรอบก่อนจะถูกปิดให้อัตโนมัติ
- **Preset: 💾 Save / 📂 Load** (ล่างสุดของแถบซ้าย) — บันทึก/โหลดชุด Job ทั้งชุด
- **▤ Script Groups** — เก็บ Script เป็นกลุ่ม (ดูหัวข้อ 8)

### 7. Export Excel (Jobs)

**⇩ Export** (ข้างปุ่ม Run all) รัน Job ที่เลือกแล้วรวมผลเป็นไฟล์เดียว `jobs_export_YYYYMMDD_HHMMSS.xlsx`

- 1 Job = 1 Worksheet (ชื่อ Sheet = ชื่อ Job)
- Header สี `#BC9BFF`, Freeze header, เส้นขอบทุก cell, ปรับความกว้างคอลัมน์อัตโนมัติ
- ต่อท้ายแต่ละ Sheet ด้วย SQL ที่ใช้รัน
- `NULL` → `[NULL]`, ตัวเลข/วันที่เป็นชนิดจริงใน Excel
- ตัวเลขเกิน 15 หลัก (เช่นเลขบัญชี) เก็บเป็นข้อความเพื่อไม่ให้ Excel ปัดหลัก
- เก็บช่องว่างหน้า/หลังข้อความไว้ตามจริง
- ถ้าเกินจำนวนแถวสูงสุดของ Excel จะตัดและแจ้งใน log
- ถ้าเพิ่งกด Run all / Run selected / Run Group มา ตอน Export จะถามว่าใช้ผลจากรอบนั้นเลยไหม (บอกเวลาที่รัน): **Yes** = ใช้ผลเดิม (เร็ว), **No** = รันใหม่ (ข้อมูลล่าสุด)
  - Job ที่ไม่มีผลเดิมจะถูกรันตามปกติ
  - โปรแกรมจะไม่เสนอผลเดิมหลัง Connect ใหม่ หรือเมื่อ SQL ถูกแก้

### 8. Script Groups

เก็บ Script เป็นกลุ่มแยกตาม Profile เช่น "กลุ่มที่ 1" มี 3 Script, "กลุ่มที่ 2" มี 5 Script กลุ่มเหล่านี้แยกจากรายการ Saved Jobs (Job ที่ไม่ได้ใส่กลุ่มยังอยู่ที่เดิม)

หน้าต่าง Script Groups แบ่งเป็นรายการกลุ่มทางซ้าย, Script ในกลุ่มทางขวา และ SQL preview ของ Script ที่เลือก

- กดแท็บ **▤ Script Groups** → **＋ New Group** → ตั้งชื่อกลุ่ม (**✎ Rename** / **🗑 Delete** ได้)
- เพิ่ม Script เข้ากลุ่ม
  - **＋ Add SQL** — เขียน SQL ใหม่ในหน้าต่างแยก (มี 📗 Load Excel / ↩ Reset SQL Template เหมือนหน้า Edit Job)
  - **🕘 From Saved Jobs** — คัดลอก Job เดิมเข้ากลุ่ม (เลือกได้หลายตัว) Job ต้นฉบับยังอยู่ที่เดิม
- **↑ ↓ / ✎ Edit / 🗑 Remove** — สลับลำดับ แก้ไข และลบ Script (รันตามลำดับที่เห็น)
- Script ในแต่ละกลุ่มเป็นสำเนาของกลุ่มนั้น ถ้ามี Script เดียวกันอยู่ในกลุ่มที่ 1 และ 2 ก็แก้แยกกันได้
- **▶ Run Group** — รันทุก Script ในกลุ่ม (ทำงานเหมือน Run all)
- **⇩ Export Group to Excel** — ได้ไฟล์ `<ชื่อกลุ่ม>_YYYYMMDD_HHMMSS.xlsx` (1 Script = 1 Sheet)
- **⇩ Export Groups / ⇧ Import Groups** — สำรองหรือย้ายกลุ่มไปเครื่องอื่นเป็นไฟล์ JSON
  - Export ได้ทุกกลุ่มของ Profile หรือเฉพาะกลุ่มที่เลือก
  - Import เข้า Profile ที่เลือกอยู่ ถ้าชื่อกลุ่มซ้ำเลือกได้ว่า **แทนที่** หรือ **เก็บทั้งคู่** (ตัวที่นำเข้าได้ชื่อใหม่)
- ทุกครั้งที่บันทึก จะเก็บเวอร์ชันก่อนหน้าไว้ที่ `script_groups_backup.json`

## การติดตั้ง

ต้องใช้ Python 3 บน Windows (DPAPI สำหรับเข้ารหัสรหัสผ่านใช้ได้เฉพาะ Windows)

```bash
pip install pandas sqlalchemy openpyxl oracledb pg8000 pymysql pyodbc xlrd
```

- `xlrd` ใช้อ่านไฟล์ `.xls` (ไม่จำเป็นถ้าใช้แต่ `.xlsx`)
- SQL Server ต้องมี ODBC driver `SQL Server` ในเครื่อง (มีมากับ Windows)

## การรันโปรแกรม

```bash
python database_connect_gui.py
```

โปรแกรมเปิดแบบเต็มจอ และบันทึก Profile ที่ใช้ล่าสุดเมื่อปิดหน้าต่าง

เปิดได้ทีละหน้าต่างเดียว ถ้าสั่งรันซ้ำตอนที่โปรแกรมเปิดอยู่แล้ว (เช่นกด Run แล้วกด Debug ใน VS Code) จะไม่เปิดหน้าต่างใหม่ แต่ดึงหน้าต่างเดิมขึ้นมาด้านหน้าแทน

## ขั้นตอนการใช้งาน

```text
1. ＋ New → เลือกชนิดฐานข้อมูล กรอกข้อมูล → 🔌 ทดสอบการเชื่อมต่อ → ＋ สร้าง Profile
2. เลือก Profile → 🔌 Connect
3. เขียน SQL → (ถ้าต้องการ) 📗 Load Excel เพื่อแทน parameter → ▶ Run / Ctrl+Enter
4. ตรวจผลใน Results Grid → 💾 Save as Job
5. ติ๊ก Job ที่ต้องการ → ▶ Run selected หรือ ⇩ Export
6. (ถ้าต้องการรันเป็นชุด) ▤ Script Groups → ＋ New Group → ＋ Add SQL / 🕘 From Saved Jobs → ▶ Run Group หรือ ⇩ Export Group to Excel
```

## การทดสอบ

มีชุดทดสอบ Robot Framework อยู่ใน `robot_tests/` วิธีรันและรายละเอียดอยู่ใน [robot_tests/README.md](robot_tests/README.md)

```bash
cd robot_tests
python -m robot --outputdir results testcases
```

## ไฟล์ในโปรเจกต์

```text
database_connect_gui/
├── database_connect_gui.py    # โปรแกรมหลัก
├── README.md
├── robot_tests/               # ชุดทดสอบ Robot Framework
├── db_profiles.json           # Connection profiles (รหัสผ่านเข้ารหัส DPAPI)
├── saved_jobs.json            # Jobs ทั้งหมด (แยกตาม profile)
├── preset_<name>.json         # Job presets
├── query_templates.json       # Query templates (สร้างเมื่อใช้งาน)
├── script_groups.json         # Script Groups (แยกตาม profile)
├── script_groups_backup.json  # Script Groups เวอร์ชันก่อนหน้า (สำรองอัตโนมัติ)
├── app_settings.json          # ค่าตั้งของโปรแกรม (เช่น Open result windows)
└── logs/run_YYYY-MM-DD.log    # Log การรัน (เก็บ 90 วัน)
```

ไฟล์ `db_profiles*.json`, `saved_jobs.json`, `script_groups*.json`, `app_settings.json`, โฟลเดอร์ `logs/` และ `*.xlsx` อยู่ใน `.gitignore` แล้ว ห้าม commit ไฟล์เหล่านี้เพราะมีข้อมูลการเชื่อมต่อและข้อมูลการใช้งาน ผลการทดสอบ Robot (`robot_tests/results/` และ `log.html`, `report.html`, `output.xml`, `screenshots/` ที่ root) ก็อยู่ใน `.gitignore` เช่นกัน

## License

Internal Use Only
