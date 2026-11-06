*** Settings ***
Documentation     Export Excel
Library           ../DBConnectorLibrary.py
Test Setup        เปิดโปรแกรมแล้วเชื่อมต่อ
Test Teardown     ปิดโปรแกรม


*** Test Cases ***
TC_31 Export Excel ได้ 1 Job ต่อ 1 Sheet รูปแบบถูกต้อง
    [Tags]    High    Export Excel    Export Jobs
    ติ๊ก Job    JOB_ACCOUNTS    JOB_STATUS    JOB_COUNT
    ตั้งไฟล์ที่จะบันทึกเป็น    jobs.xlsx
    กด Export Excel
    รอจนรันเสร็จ
    ไฟล์ Excel ต้องมี Sheet    JOB_ACCOUNTS    JOB_STATUS    JOB_COUNT
    หัวตารางของ Sheet ต้องเป็นสีม่วงและ freeze แถวหัว    JOB_ACCOUNTS
    Sheet ต้องมี SQL ที่ใช้รันต่อท้าย    JOB_STATUS    SELECT ID, STATUS FROM TEST_TABLE ORDER BY ID

TC_32 เลขบัญชีเกิน 15 หลักและค่า NULL ใน Excel ต้องถูกต้อง
    [Tags]    High    Export Excel    Export Jobs
    พิมพ์ SQL    SELECT ACCOUNT_NO, AMOUNT, NOTE FROM BIG_NUMBERS
    บันทึก SQL เป็น Job ชื่อ    BIG_NUMBERS
    ติ๊ก Job    BIG_NUMBERS
    ตั้งไฟล์ที่จะบันทึกเป็น    big.xlsx
    กด Export Excel
    รอจนรันเสร็จ
    ค่าใน Sheet ต้องเป็น    BIG_NUMBERS    A2    1234567890123456789    text
    ค่าใน Sheet ต้องเป็น    BIG_NUMBERS    B2    10.5    number
    ค่าใน Sheet ต้องเป็น    BIG_NUMBERS    C2    [NULL]

TC_33 Export หลัง Run All เลือกใช้ผลเดิมได้ ไม่ต้องรันซ้ำ
    [Tags]    Medium    Export Excel    Export Jobs
    ติ๊ก Job    JOB_STATUS
    กด Run All Jobs
    รอจนรันเสร็จ
    ปิดหน้าต่างที่เปิดค้างทั้งหมด
    แก้ข้อมูลในฐานข้อมูลโดยตรง    UPDATE TEST_TABLE SET STATUS = 'Z'
    # Yes = ใช้ผลเดิม → ยังเป็นค่า A ตอนรัน
    ตั้งไฟล์ที่จะบันทึกเป็น    reuse.xlsx
    ตอบหน้าต่างยืนยันถัดไปว่า    Yes
    กด Export Excel
    รอจนรันเสร็จ
    หน้าต่างยืนยันล่าสุดต้องมีข้อความ    already have results from the run
    ค่าใน Sheet ต้องเป็น    JOB_STATUS    B2    A
    # No = รันใหม่ → ได้ค่าล่าสุด Z
    ตั้งไฟล์ที่จะบันทึกเป็น    rerun.xlsx
    ตอบหน้าต่างยืนยันถัดไปว่า    No
    กด Export Excel
    รอจนรันเสร็จ
    ค่าใน Sheet ต้องเป็น    JOB_STATUS    B2    Z

TC_34 Export Group to Excel ได้ไฟล์ชื่อตามกลุ่ม
    [Tags]    Medium    Export Excel    Export Group
    เปิดหน้าต่าง Script Groups
    สร้างกลุ่ม    กลุ่มที่ 1
    คัดลอก Job เข้ากลุ่ม    กลุ่มที่ 1    JOB_ACCOUNTS    JOB_STATUS    JOB_COUNT
    ตั้งไฟล์ที่จะบันทึกเป็น    group.xlsx
    กด Export Group to Excel    กลุ่มที่ 1
    รอจนรันเสร็จ
    ชื่อไฟล์ที่เสนอตอน Export ต้องขึ้นต้นด้วย    กลุ่มที่ 1_
    ไฟล์ Excel ต้องมี Sheet    JOB_ACCOUNTS    JOB_STATUS    JOB_COUNT


*** Keywords ***
เปิดโปรแกรมแล้วเชื่อมต่อ
    เปิดโปรแกรมด้วยข้อมูลทดสอบ
    เชื่อมต่อฐานข้อมูลทดสอบ
