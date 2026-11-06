*** Settings ***
Documentation     Script Groups
...               (TC_26 Add SQL พร้อม Load Excel ในหน้าต่างกลุ่ม ทดสอบมือ — ดู README)
Library           ../DBConnectorLibrary.py
Test Setup        เปิดโปรแกรมแล้วเชื่อมต่อ
Test Teardown     ปิดโปรแกรม


*** Variables ***
${G1}       กลุ่มที่ 1
${G2}       กลุ่มที่ 2


*** Test Cases ***
TC_21 สร้างกลุ่มใหม่ และชื่อซ้ำต้องสร้างไม่ได้
    [Tags]    High    Script Groups    จัดการกลุ่ม
    เปิดหน้าต่าง Script Groups
    สร้างกลุ่ม    ${G1}
    กลุ่มที่เห็นในหน้าต่างต้องเป็น    ${G1}
    สร้างกลุ่ม    ${G1}
    ต้องมีข้อความแจ้งเตือนที่มีคำว่า    already exists
    จำนวนกลุ่มชื่อนี้ต้องเป็น    ${G1}    1

TC_22 กลุ่มแยกตาม Profile
    [Tags]    Medium    Script Groups    จัดการกลุ่ม
    เปิดหน้าต่าง Script Groups
    สร้างกลุ่ม    ${G1}
    ปิดหน้าต่าง Script Groups
    เลือก Profile    test_other
    เปิดหน้าต่าง Script Groups
    กลุ่มที่เห็นในหน้าต่างต้องเป็น

TC_23 Add SQL เขียน Script ใหม่เข้ากลุ่ม
    [Tags]    High    Script Groups    จัดการ Script ในกลุ่ม
    ${before}=    อ่าน SQL ในช่อง Editor
    เปิดหน้าต่าง Script Groups
    สร้างกลุ่ม    ${G1}
    เพิ่ม SQL เข้ากลุ่ม    ${G1}    Script A    SELECT NAME FROM ACCOUNTS
    Script ในกลุ่มต้องเรียงเป็น    ${G1}    Script A
    SQL ของ Script ในกลุ่มต้องเป็น    ${G1}    Script A    SELECT NAME FROM ACCOUNTS
    SQL ในช่อง Editor ต้องเป็น    ${before}

TC_24 คัดลอก Job เดิมเข้ากลุ่ม Job ต้นฉบับต้องไม่หาย
    [Tags]    High    Script Groups    จัดการ Script ในกลุ่ม
    เปิดหน้าต่าง Script Groups
    สร้างกลุ่ม    ${G1}
    คัดลอก Job เข้ากลุ่ม    ${G1}    JOB_ACCOUNTS    JOB_STATUS    JOB_COUNT
    Script ในกลุ่มต้องเรียงเป็น    ${G1}    JOB_ACCOUNTS    JOB_STATUS    JOB_COUNT
    รายการ Saved Jobs ต้องเป็น    JOB_ACCOUNTS    JOB_STATUS    JOB_BAD    JOB_COUNT

TC_25 Script เดียวกันอยู่ 2 กลุ่ม แก้ในกลุ่มหนึ่ง อีกกลุ่มต้องไม่เปลี่ยน
    [Tags]    High    Script Groups    จัดการ Script ในกลุ่ม
    เปิดหน้าต่าง Script Groups
    สร้างกลุ่ม    ${G1}
    สร้างกลุ่ม    ${G2}
    คัดลอก Job เข้ากลุ่ม    ${G1}    JOB_ACCOUNTS
    คัดลอก Job เข้ากลุ่ม    ${G2}    JOB_ACCOUNTS
    แก้ SQL ของ Script    ${G2}    JOB_ACCOUNTS    SELECT 2 AS X
    SQL ของ Script ในกลุ่มต้องเป็น    ${G2}    JOB_ACCOUNTS    SELECT 2 AS X
    SQL ของ Script ในกลุ่มต้องเป็น    ${G1}    JOB_ACCOUNTS
    ...    SELECT ACCOUNT_NO, NAME, BALANCE FROM ACCOUNTS ORDER BY ACCOUNT_NO
    SQL ของ Job ต้องเป็น    JOB_ACCOUNTS
    ...    SELECT ACCOUNT_NO, NAME, BALANCE FROM ACCOUNTS ORDER BY ACCOUNT_NO

TC_27 สลับลำดับ Script แล้วรันตามลำดับใหม่
    [Tags]    Medium    Script Groups    Run Group
    เปิดหน้าต่าง Script Groups
    สร้างกลุ่ม    ${G1}
    คัดลอก Job เข้ากลุ่ม    ${G1}    JOB_ACCOUNTS    JOB_STATUS    JOB_COUNT
    เลื่อน Script ขึ้น    ${G1}    JOB_COUNT    2
    Script ในกลุ่มต้องเรียงเป็น    ${G1}    JOB_COUNT    JOB_ACCOUNTS    JOB_STATUS
    กด Run Group    ${G1}
    รอจนรันเสร็จ
    ลำดับ Job ที่รันใน Log ต้องเป็น    JOB_COUNT    JOB_ACCOUNTS    JOB_STATUS
    ถ่ายภาพหน้าจอ    หลัง Run Group ตามลำดับใหม่
    ปิดแล้วเปิดโปรแกรมใหม่
    Script ในกลุ่มต้องเรียงเป็น    ${G1}    JOB_COUNT    JOB_ACCOUNTS    JOB_STATUS

TC_28 Run Group รันทุก Script ในกลุ่ม
    [Tags]    High    Script Groups    Run Group
    เปิดหน้าต่าง Script Groups
    สร้างกลุ่ม    ${G1}
    คัดลอก Job เข้ากลุ่ม    ${G1}    JOB_ACCOUNTS    JOB_BAD    JOB_COUNT
    กด Run Group    ${G1}
    รอจนรันเสร็จ
    สรุปผลการรันต้องเป็น    3    2    1
    Results Grid ต้องมีผลของ    JOB_ACCOUNTS    JOB_COUNT
    หน้าต่าง Script Groups ต้องอยู่เหนือหน้าหลัก

TC_29 Export กลุ่มแล้ว Import กลับมาแบบเก็บทั้งคู่
    [Tags]    Medium    Script Groups    Import / Export กลุ่ม
    เปิดหน้าต่าง Script Groups
    สร้างกลุ่ม    ${G1}
    สร้างกลุ่ม    ${G2}
    คัดลอก Job เข้ากลุ่ม    ${G1}    JOB_ACCOUNTS
    คัดลอก Job เข้ากลุ่ม    ${G2}    JOB_STATUS    JOB_COUNT
    ${file}=    ตั้งไฟล์ที่จะบันทึกเป็น    groups_backup.json
    ตอบหน้าต่างยืนยันถัดไปว่า    Yes
    กด Export Groups
    ลบกลุ่ม    ${G2}
    กลุ่มที่เห็นในหน้าต่างต้องเป็น    ${G1}
    ตั้งไฟล์ที่จะเปิดเป็น    ${file}
    ตอบหน้าต่างยืนยันถัดไปว่า    No
    กด Import Groups
    กลุ่มที่เห็นในหน้าต่างต้องเป็น    ${G1}    ${G1} (2)    ${G2}
    Script ในกลุ่มต้องเรียงเป็น    ${G2}    JOB_STATUS    JOB_COUNT
    Script ในกลุ่มต้องเรียงเป็น    ${G1}    JOB_ACCOUNTS

TC_30 Import ไฟล์ที่ไม่ใช่ไฟล์กลุ่ม
    [Tags]    Low    Script Groups    Import / Export กลุ่ม
    เปิดหน้าต่าง Script Groups
    สร้างกลุ่ม    ${G1}
    ${bad}=    สร้างไฟล์ JSON ที่ไม่ใช่ไฟล์กลุ่ม
    ตั้งไฟล์ที่จะเปิดเป็น    ${bad}
    กด Import Groups
    ต้องมีข้อความแจ้งเตือนที่มีคำว่า    Not a valid Script Groups file
    กลุ่มที่เห็นในหน้าต่างต้องเป็น    ${G1}


*** Keywords ***
เปิดโปรแกรมแล้วเชื่อมต่อ
    เปิดโปรแกรมด้วยข้อมูลทดสอบ
    เชื่อมต่อฐานข้อมูลทดสอบ
