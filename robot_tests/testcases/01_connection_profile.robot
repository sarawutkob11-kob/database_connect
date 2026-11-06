*** Settings ***
Documentation     การเชื่อมต่อฐานข้อมูล และ Connection Profile
...               (TC_1, TC_2, TC_6 ทดสอบมือ — ดู README)
Library           ../DBConnectorLibrary.py
Test Setup        เปิดโปรแกรมด้วยข้อมูลทดสอบ
Test Teardown     ปิดโปรแกรม


*** Test Cases ***
TC_3 เปิดโปรแกรมทิ้งไว้นานแล้วรัน SQL ได้โดยไม่ต้อง Connect ใหม่
    [Tags]    High    การเชื่อมต่อฐานข้อมูล    ต่อใหม่อัตโนมัติ
    เชื่อมต่อฐานข้อมูลทดสอบ
    ตัวเชื่อมต่อต้องตรวจ connection ก่อนใช้และเปลี่ยนใหม่ทุก 30 นาที
    พิมพ์ SQL    SELECT ACCOUNT_NO FROM ACCOUNTS
    กด Execute
    รอจนรันเสร็จ
    ปิดหน้าต่างที่เปิดค้างทั้งหมด
    จำลอง connection ถูกตัดระหว่างเปิดโปรแกรมทิ้งไว้
    กด Execute
    รอจนรันเสร็จ
    ผลลัพธ์ใน Results Grid ต้องมี 3 แถว
    สถานะการเชื่อมต่อต้องเป็น    Connected

TC_4 สร้าง Profile ใหม่และบันทึก รหัสผ่านต้องไม่เก็บเป็นตัวอักษรปกติ
    [Tags]    High    Connection Profile    จัดการ Profile
    เชื่อมต่อฐานข้อมูลทดสอบ
    บันทึก Profile ปัจจุบันเป็นชื่อ    test_new
    รหัสผ่านของ Profile ในไฟล์ต้องถูกเข้ารหัส    test_new
    ถ่ายภาพหน้าจอ    หลังบันทึก Profile test_new    บน
    ปิดแล้วเปิดโปรแกรมใหม่
    เลือก Profile    test_new
    Profile ที่เลือกอยู่ต้องเป็น    test_new
    เชื่อมต่อฐานข้อมูลทดสอบ

TC_5 เปลี่ยน Profile แล้วรายการ Job และการเชื่อมต่อเปลี่ยนตาม
    [Tags]    Medium    Connection Profile    จัดการ Profile
    เชื่อมต่อฐานข้อมูลทดสอบ
    รายการ Saved Jobs ต้องเป็น    JOB_ACCOUNTS    JOB_STATUS    JOB_BAD    JOB_COUNT
    เลือก Profile    test_other
    รายการ Saved Jobs ต้องเป็น    OTHER_JOB
    สถานะการเชื่อมต่อต้องเป็น    Not Connected
