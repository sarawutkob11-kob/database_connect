*** Settings ***
Documentation     Saved Jobs
Library           ../DBConnectorLibrary.py
Test Setup        เปิดโปรแกรมแล้วเชื่อมต่อ
Test Teardown     ปิดโปรแกรม


*** Variables ***
${ACCOUNT_SQL}      SELECT ACCOUNT_NO, NAME FROM ACCOUNTS WHERE ACCOUNT_NO IN ({ACCOUNT_LIST})


*** Test Cases ***
TC_16 Save Job แล้วค่าจาก Excel ต้องติดไปกับ Job
    [Tags]    High    Saved Jobs    จัดการ Job
    พิมพ์ SQL    ${ACCOUNT_SQL}
    ใส่ค่าจาก Excel แทน    {ACCOUNT_LIST}    14764478022247801378
    บันทึก SQL เป็น Job ชื่อ    TEST_ACCOUNT_LIST
    Job ต้องเก็บค่า Excel parameter ไว้    TEST_ACCOUNT_LIST
    ถ่ายภาพหน้าจอ    หลัง Save Job (ก่อนปิดเปิดโปรแกรม)
    ปิดแล้วเปิดโปรแกรมใหม่
    รายการ Saved Jobs ต้องมี    TEST_ACCOUNT_LIST
    SQL ของ Job ต้องเป็น    TEST_ACCOUNT_LIST
    ...    SELECT ACCOUNT_NO, NAME FROM ACCOUNTS WHERE ACCOUNT_NO IN ('14764478022247801378')

TC_17 Edit Job แก้ชื่อและ SQL
    [Tags]    Medium    Saved Jobs    จัดการ Job
    แก้ Job    JOB_COUNT    JOB_COUNT_EDIT    SELECT COUNT(*) AS N FROM TEST_TABLE
    รายการ Saved Jobs ต้องมี    JOB_COUNT_EDIT
    กด Run Job    JOB_COUNT_EDIT
    รอจนรันเสร็จ
    ค่าในตาราง Results Grid แถว 1 คอลัมน์ N ต้องเป็น    2

TC_18 ติ๊กหลาย Job แล้ว Delete Selected
    [Tags]    Medium    Saved Jobs    จัดการ Job
    ติ๊ก Job    JOB_BAD    JOB_COUNT
    ตอบหน้าต่างยืนยันถัดไปว่า    Yes
    กด Delete Selected
    หน้าต่างยืนยันล่าสุดต้องมีข้อความ    JOB_BAD    JOB_COUNT
    รายการ Saved Jobs ต้องเป็น    JOB_ACCOUNTS    JOB_STATUS

TC_19 Run All Jobs มี Job หนึ่ง error ต้องรันตัวที่เหลือต่อจนครบ
    [Tags]    High    Saved Jobs    Run All / Run Selected
    กด Run All Jobs
    รอจนรันเสร็จ
    สรุปผลการรันต้องเป็น    4    3    1
    ลำดับ Job ที่รันใน Log ต้องเป็น    JOB_ACCOUNTS    JOB_STATUS    JOB_BAD    JOB_COUNT
    Results Grid ต้องมีผลของ    JOB_ACCOUNTS    JOB_STATUS    JOB_COUNT

TC_20 ติ๊กบาง Job แล้วรันเฉพาะตัวที่ติ๊ก
    [Tags]    Medium    Saved Jobs    Run All / Run Selected
    ติ๊ก Job    JOB_ACCOUNTS    JOB_COUNT
    กด Run All Jobs
    รอจนรันเสร็จ
    สรุปผลการรันต้องเป็น    2    2    0
    ลำดับ Job ที่รันใน Log ต้องเป็น    JOB_ACCOUNTS    JOB_COUNT


*** Keywords ***
เปิดโปรแกรมแล้วเชื่อมต่อ
    เปิดโปรแกรมด้วยข้อมูลทดสอบ
    เชื่อมต่อฐานข้อมูลทดสอบ
