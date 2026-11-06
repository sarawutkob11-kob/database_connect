*** Settings ***
Documentation     รัน SQL (Execute) และ Excel Parameter
...               (TC_7 เทียบกับ DBeaver และ TC_15 ไฟล์ Excel เปิดค้าง ทดสอบมือ — ดู README)
Library           ../DBConnectorLibrary.py
Test Setup        เปิดโปรแกรมแล้วเชื่อมต่อ
Test Teardown     ปิดโปรแกรม


*** Variables ***
${UPDATE_SQL}       UPDATE TEST_TABLE SET STATUS = 'X' WHERE ID = 1
${ACCOUNT_SQL}      SELECT ACCOUNT_NO, NAME FROM ACCOUNTS WHERE ACCOUNT_NO IN ({ACCOUNT_LIST})
${NAME_SQL}         SELECT ACCOUNT_NO FROM ACCOUNTS WHERE NAME IN ({NAME_LIST})


*** Test Cases ***
TC_8 SQL ผิด ต้องแจ้ง Error ให้เข้าใจ
    [Tags]    Medium    รัน SQL (Execute)    SELECT
    พิมพ์ SQL    SELECT * FROM TABLE_NOT_EXIST
    กด Execute
    รอจนรันเสร็จ
    Error ล่าสุดต้องมีข้อความ    no such table
    ปุ่ม Execute ต้องกดได้

TC_9 SQL ที่ลงท้ายด้วย ; หรือ / รันได้เหมือน DBeaver
    [Tags]    Low    รัน SQL (Execute)    SELECT
    พิมพ์ SQL    SELECT COUNT(*) AS N FROM ACCOUNTS;
    กด Execute
    รอจนรันเสร็จ
    ผลลัพธ์ใน Results Grid ต้องมี 1 แถว
    ปิดหน้าต่างที่เปิดค้างทั้งหมด
    พิมพ์ SQL    SELECT COUNT(*) AS N FROM ACCOUNTS\n/
    กด Execute
    รอจนรันเสร็จ
    ค่าในตาราง Results Grid แถว 1 คอลัมน์ N ต้องเป็น    3

TC_10 รัน UPDATE ต้องถามยืนยันก่อน กด No แล้วข้อมูลต้องไม่เปลี่ยน
    [Tags]    High    รัน SQL (Execute)    แก้ไขข้อมูล (UPDATE/INSERT/DELETE)
    พิมพ์ SQL    ${UPDATE_SQL}
    ตอบหน้าต่างยืนยันถัดไปว่า    No
    กด Execute
    รอจนรันเสร็จ
    หน้าต่างยืนยันล่าสุดต้องมีข้อความ    test_main    localhost    testdb    UPDATE TEST_TABLE
    ผลจาก SQL ต้องเป็น    SELECT STATUS FROM TEST_TABLE WHERE ID = 1    A

TC_11 รัน UPDATE แล้วกด Yes ข้อมูลต้องเปลี่ยนจริง
    [Tags]    High    รัน SQL (Execute)    แก้ไขข้อมูล (UPDATE/INSERT/DELETE)
    พิมพ์ SQL    ${UPDATE_SQL}
    ตอบหน้าต่างยืนยันถัดไปว่า    Yes
    กด Execute
    รอจนรันเสร็จ
    ผลจาก SQL ต้องเป็น    SELECT STATUS FROM TEST_TABLE WHERE ID = 1    X
    ผลจาก SQL ต้องเป็น    SELECT STATUS FROM TEST_TABLE WHERE ID = 2    A

TC_12 Load Excel แล้วเลือกเลขบัญชีไปแทนใน {ACCOUNT_LIST}
    [Tags]    High    Excel Parameter    แทนค่าจาก Excel
    พิมพ์ SQL    ${ACCOUNT_SQL}
    ใส่ค่าจาก Excel แทน    {ACCOUNT_LIST}    14764478022247801378    14764478022247801379    14764478022247801380
    SQL ในช่อง Editor ต้องเป็น
    ...    SELECT ACCOUNT_NO, NAME FROM ACCOUNTS WHERE ACCOUNT_NO IN ('14764478022247801378', '14764478022247801379', '14764478022247801380')
    กด Execute
    รอจนรันเสร็จ
    ผลลัพธ์ใน Results Grid ต้องมี 3 แถว

TC_13 ค่าที่มีเครื่องหมาย ' ต้องไม่ทำให้ SQL พัง
    [Tags]    Medium    Excel Parameter    แทนค่าจาก Excel
    พิมพ์ SQL    ${NAME_SQL}
    ใส่ค่าจาก Excel แทน    {NAME_LIST}    O'NEIL
    SQL ในช่อง Editor ต้องเป็น    SELECT ACCOUNT_NO FROM ACCOUNTS WHERE NAME IN ('O''NEIL')
    กด Execute
    รอจนรันเสร็จ
    ผลลัพธ์ใน Results Grid ต้องมี 1 แถว
    ค่าในตาราง Results Grid แถว 1 คอลัมน์ ACCOUNT_NO ต้องเป็น    14764478022247801378

TC_14 Reset SQL Template คืนค่า SQL กลับเป็น {ACCOUNT_LIST}
    [Tags]    Medium    Excel Parameter    แทนค่าจาก Excel
    พิมพ์ SQL    ${ACCOUNT_SQL}
    ใส่ค่าจาก Excel แทน    {ACCOUNT_LIST}    14764478022247801378
    คืนค่า SQL Template ทั้งหมด
    SQL ในช่อง Editor ต้องเป็น    ${ACCOUNT_SQL}
    ใส่ค่าจาก Excel แทน    {ACCOUNT_LIST}    14764478022247801379
    SQL ในช่อง Editor ต้องเป็น
    ...    SELECT ACCOUNT_NO, NAME FROM ACCOUNTS WHERE ACCOUNT_NO IN ('14764478022247801379')


*** Keywords ***
เปิดโปรแกรมแล้วเชื่อมต่อ
    เปิดโปรแกรมด้วยข้อมูลทดสอบ
    เชื่อมต่อฐานข้อมูลทดสอบ
