*** Settings ***
Documentation     ปุ่ม Stop, หน้าต่างผลลัพธ์ และ Log
...               ฐานข้อมูลทดสอบจำลองการยกเลิก Query แบบ Oracle (cancel)
...               บน Oracle จริงจะได้ ORA-01013 แทนข้อความ interrupted
Library           ../DBConnectorLibrary.py
Test Setup        เปิดโปรแกรมแล้วเชื่อมต่อ
Test Teardown     ปิดโปรแกรม


*** Test Cases ***
TC_35 กด Stop ตอน Query รันนาน ต้องหยุดทันที
    [Tags]    High    ปุ่ม Stop    หยุดการรัน
    ปุ่ม Stop ต้องกดไม่ได้
    ${sql}=    SQL ที่ใช้เวลานาน
    พิมพ์ SQL    ${sql}
    กด Execute
    รอ 2 วินาที
    ปุ่ม Stop ต้องกดได้
    กด Stop
    รอจนรันเสร็จ    timeout=15
    Error ล่าสุดต้องมีข้อความ    interrupted
    ปุ่ม Stop ต้องกดไม่ได้
    ปุ่ม Execute ต้องกดได้

TC_36 กด Stop ระหว่าง Run Group ตัวที่เหลือต้องไม่รัน
    [Tags]    High    ปุ่ม Stop    หยุดการรัน
    ${sql}=    SQL ที่ใช้เวลานาน
    เปิดหน้าต่าง Script Groups
    สร้างกลุ่ม    กลุ่มที่ 1
    เพิ่ม SQL เข้ากลุ่ม    กลุ่มที่ 1    LONG_QUERY    ${sql}
    คัดลอก Job เข้ากลุ่ม    กลุ่มที่ 1    JOB_ACCOUNTS    JOB_STATUS    JOB_COUNT
    กด Run Group    กลุ่มที่ 1
    รอ 2 วินาที
    กด Stop
    รอจนรันเสร็จ    timeout=15
    Log ต้องมีข้อความ    Stopped — 3 job(s) not run
    สรุปผลการรันต้องเป็น    1    0    1
    ปุ่ม Stop ต้องกดไม่ได้

TC_37 ปิด Open result windows แล้ว Run All ต้องไม่เปิด popup
    [Tags]    Low    หน้าต่างผลลัพธ์และ Log    หน้าต่างผลลัพธ์
    ตั้งค่า Open result windows เป็น    False
    กด Run All Jobs
    รอจนรันเสร็จ
    จำนวนหน้าต่างผลลัพธ์ที่เปิดอยู่ต้องเป็น    0
    Results Grid ต้องมีผลของ    JOB_ACCOUNTS    JOB_STATUS    JOB_COUNT
    ถ่ายภาพหน้าจอ    Run All แบบไม่เปิด popup ผลอยู่ใน Results Grid
    ปิดแล้วเปิดโปรแกรมใหม่
    ค่า Open result windows ต้องเป็น    False

TC_38 Log ถูกบันทึกลงไฟล์ และไม่มีรหัสผ่าน
    [Tags]    Medium    หน้าต่างผลลัพธ์และ Log    Log
    พิมพ์ SQL    SELECT COUNT(*) AS N FROM ACCOUNTS
    กด Execute
    รอจนรันเสร็จ
    กด Run All Jobs
    รอจนรันเสร็จ
    ไฟล์ log ของวันนี้ต้องมี    ===== RUN    profile=test_main    tester@localhost:5432/testdb
    ไฟล์ log ของวันนี้ต้องมี    SELECT ID, STATUS FROM TEST_TABLE ORDER BY ID    no such table: TABLE_NOT_EXIST
    ไฟล์ log ของวันนี้ต้องไม่มีรหัสผ่าน


*** Keywords ***
เปิดโปรแกรมแล้วเชื่อมต่อ
    เปิดโปรแกรมด้วยข้อมูลทดสอบ
    เชื่อมต่อฐานข้อมูลทดสอบ
