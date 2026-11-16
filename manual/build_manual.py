"""Build Database_Connector_Manual.pptx from the screenshots in manual/screens.

Run capture_screens.py first. Every table row describes a numbered marker in
the matching screenshot; the text is based on database_connect_gui.py.

Usage: python manual/build_manual.py
"""

import os
import re

from PIL import Image
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Inches, Pt

HERE = os.path.dirname(os.path.abspath(__file__))
SCREENS = os.path.join(HERE, "screens")
OUTPUT = os.path.join(HERE, "Database_Connector_Manual.pptx")

FONT = "Leelawadee UI"  # Thai + Latin, ships with Windows
MONO = "Consolas"

NAVY = RGBColor(0x0F, 0x17, 0x2A)
SLATE = RGBColor(0x1E, 0x29, 0x3B)
TEXT = RGBColor(0x1E, 0x29, 0x3B)
MUTED = RGBColor(0x64, 0x74, 0x8B)
LINE = RGBColor(0xE2, 0xE8, 0xF0)
ROW_ALT = RGBColor(0xF8, 0xFA, 0xFC)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
ORANGE = RGBColor(0xF9, 0x73, 0x16)
BLUE = RGBColor(0x25, 0x63, 0xEB)
NOTE_BG = RGBColor(0xEF, 0xF6, 0xFF)

SLIDE_W, SLIDE_H = 13.333, 7.5
MARGIN = 0.5
CONTENT_TOP = 1.45
CONTENT_BOTTOM = 6.95
TOTAL_SLIDES = 13


# ---------------------------------------------------------------------------
# Text helpers
# ---------------------------------------------------------------------------
def style_run(run, size, bold=False, color=TEXT, font=FONT):
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = color
    run.font.name = font
    rpr = run._r.get_or_add_rPr()
    for tag in ("a:ea", "a:cs"):  # Thai text uses the complex-script font
        el = rpr.find(qn(tag))
        if el is None:
            el = rpr.makeelement(qn(tag), {})
            rpr.append(el)
        el.set("typeface", font)


def add_text(slide, x, y, w, h, text, size, bold=False, color=TEXT, align=PP_ALIGN.LEFT,
             anchor=MSO_ANCHOR.TOP, font=FONT, line_spacing=1.1):
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = box.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = anchor
    lines = text if isinstance(text, list) else [text]
    for i, line in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        p.line_spacing = line_spacing
        style_run(p.add_run(), size, bold, color, font)
        p.runs[0].text = line
    return box


ICON_PREFIX = re.compile(r"^[▶⏹📗↩💾▦✎🔌＋🗑⇩⇧🕘📊📋🐛📄☑✓◀\s]+")


def button_name(text):
    """Drop the leading icon of a button label; the screenshot shows it already."""
    name = ICON_PREFIX.sub("", text)
    return name or text


def fill_cell(cell, text, size, bold=False, color=TEXT, bg=WHITE, align=PP_ALIGN.LEFT, font=FONT):
    cell.fill.solid()
    cell.fill.fore_color.rgb = bg
    cell.margin_left = cell.margin_right = Inches(0.08)
    cell.margin_top = cell.margin_bottom = Inches(0.045)
    cell.vertical_anchor = MSO_ANCHOR.MIDDLE
    tf = cell.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.alignment = align
    run = p.add_run()
    run.text = text
    style_run(run, size, bold, color, font)


# ---------------------------------------------------------------------------
# Slide parts
# ---------------------------------------------------------------------------
def set_background(slide, color):
    bg = slide.background.fill
    bg.solid()
    bg.fore_color.rgb = color


def add_header(slide, number, title, subtitle):
    set_background(slide, WHITE)
    add_text(slide, MARGIN, 0.38, 10.5, 0.6, title, 28, bold=True, color=NAVY)
    add_text(slide, MARGIN, 0.95, 12.3, 0.4, subtitle, 13, color=MUTED)
    add_text(slide, MARGIN, 7.08, 6, 0.25, "Database Connector · คู่มือการใช้งาน", 9, color=MUTED)
    add_text(slide, SLIDE_W - MARGIN - 1.5, 7.08, 1.5, 0.25, f"{number} / {TOTAL_SLIDES}", 9,
             color=MUTED, align=PP_ALIGN.RIGHT)


def add_screenshot(slide, name, max_w, max_h, x=MARGIN, y=CONTENT_TOP):
    path = os.path.join(SCREENS, f"{name}.png")
    with Image.open(path) as im:
        px_w, px_h = im.size
    scale = min(max_w / px_w, max_h / px_h)
    w, h = px_w * scale, px_h * scale
    pic = slide.shapes.add_picture(path, Inches(x), Inches(y), Inches(w), Inches(h))
    pic.line.color.rgb = LINE
    pic.line.width = Pt(1)
    return x, y, w, h


def add_note(slide, x, y, w, lines):
    h = 0.22 + 0.3 * len(lines)
    box = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h))
    box.adjustments[0] = 0.08
    box.fill.solid()
    box.fill.fore_color.rgb = NOTE_BG
    box.line.fill.background()
    box.shadow.inherit = False
    tf = box.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = Inches(0.16)
    tf.margin_top = tf.margin_bottom = Inches(0.08)
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    for i, line in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = PP_ALIGN.LEFT
        run = p.add_run()
        run.text = line
        style_run(run, 12, color=TEXT)


def add_button_table(slide, x, y, w, rows, headers=("เลข", "ปุ่ม", "หน้าที่"), size=12,
                     col1=1.55):
    table = slide.shapes.add_table(len(rows) + 1, 3, Inches(x), Inches(y), Inches(w),
                                   Inches(0.3 * (len(rows) + 1))).table
    table.first_row = True
    table.horz_banding = False
    num_w = 0.5
    table.columns[0].width = Inches(num_w)
    table.columns[1].width = Inches(col1)
    table.columns[2].width = Inches(w - num_w - col1)
    for c, head in enumerate(headers):
        fill_cell(table.cell(0, c), head, size, bold=True, color=WHITE, bg=SLATE,
                  align=PP_ALIGN.CENTER if c == 0 else PP_ALIGN.LEFT)
    for r, (number, button, what) in enumerate(rows, start=1):
        bg = WHITE if r % 2 else ROW_ALT
        fill_cell(table.cell(r, 0), str(number), size, bold=True, color=WHITE, bg=ORANGE,
                  align=PP_ALIGN.CENTER)
        fill_cell(table.cell(r, 1), button_name(button), size, bold=True, bg=bg)
        fill_cell(table.cell(r, 2), what, size, bg=bg)
    for r in range(len(rows) + 1):
        table.rows[r].height = Inches(0.3)
    return table


def content_slide(prs, number, title, subtitle, image, rows, note=None, size=12,
                  img_w=7.45, col1=1.55, headers=("เลข", "ปุ่ม", "หน้าที่")):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    add_header(slide, number, title, subtitle)
    max_h = CONTENT_BOTTOM - CONTENT_TOP
    if note:
        max_h -= 0.3 * len(note) + 0.45
    x, y, w, h = add_screenshot(slide, image, img_w, max_h)
    if note:
        add_note(slide, x, y + h + 0.22, max(w, 5.2), note)
    table_x = x + w + 0.35
    table_w = min(SLIDE_W - MARGIN - table_x, 6.6)
    add_button_table(slide, table_x, CONTENT_TOP, table_w, rows, headers, size, col1)
    return slide


# ---------------------------------------------------------------------------
# Slides
# ---------------------------------------------------------------------------
def cover(prs):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    set_background(slide, NAVY)
    add_text(slide, 0.8, 1.7, 5.6, 0.4, "คู่มือการใช้งาน", 18, color=RGBColor(0xFD, 0xBA, 0x74))
    add_text(slide, 0.8, 2.15, 5.8, 1.0, "Database Connector", 42, bold=True, color=WHITE)
    add_text(slide, 0.8, 3.25, 5.4, 1.3,
             ["โปรแกรมเชื่อมต่อฐานข้อมูล รัน SQL",
              "เก็บ Query เป็น Job และ Export ผลเป็น Excel"],
             17, color=RGBColor(0xCB, 0xD5, 0xE1), line_spacing=1.25)
    add_text(slide, 0.8, 4.75, 5.6, 0.4, "Oracle · PostgreSQL · MySQL · Microsoft SQL Server", 13,
             color=RGBColor(0x94, 0xA3, 0xB8))
    add_text(slide, 0.8, 6.55, 5, 0.35, "พฤศจิกายน 2569", 12, color=RGBColor(0x94, 0xA3, 0xB8))
    path = os.path.join(SCREENS, "raw_main.png")
    with Image.open(path) as im:
        ratio = im.size[1] / im.size[0]
    w = 6.2
    pic = slide.shapes.add_picture(path, Inches(6.65), Inches(3.75 - w * ratio / 2), Inches(w))
    pic.line.color.rgb = RGBColor(0x33, 0x41, 0x55)
    pic.line.width = Pt(1)


def files_slide(prs, number):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    add_header(slide, number, "ไฟล์ที่โปรแกรมเก็บ",
               "ทุกไฟล์อยู่ในโฟลเดอร์เดียวกับ database_connect_gui.py")
    files = [
        "db_profiles.json",
        "saved_jobs.json",
        "script_groups.json",
        "script_groups_backup.json",
        "preset_<ชื่อ>.json",
        "app_settings.json",
        "logs/run_YYYY-MM-DD.log",
        "jobs_export_YYYYMMDD_HHMMSS.xlsx",
    ]
    x, y, w = MARGIN, CONTENT_TOP, 5.6
    row_h = 0.44
    h = 0.75 + row_h * len(files)
    card = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h))
    card.adjustments[0] = 0.04
    card.fill.solid()
    card.fill.fore_color.rgb = ROW_ALT
    card.line.color.rgb = LINE
    card.shadow.inherit = False
    add_text(slide, x + 0.3, y + 0.22, w - 0.5, 0.35, "📁  database_connect_gui/", 14, bold=True,
             color=NAVY)
    for i, name in enumerate(files, start=1):
        ry = y + 0.7 + (i - 1) * row_h
        dot = slide.shapes.add_shape(MSO_SHAPE.OVAL, Inches(x + 0.55), Inches(ry + 0.06), Inches(0.32), Inches(0.32))
        dot.fill.solid()
        dot.fill.fore_color.rgb = ORANGE
        dot.line.fill.background()
        dot.shadow.inherit = False
        tf = dot.text_frame
        tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
        p = tf.paragraphs[0]
        p.alignment = PP_ALIGN.CENTER
        run = p.add_run()
        run.text = str(i)
        style_run(run, 11, bold=True, color=WHITE)
        tf.vertical_anchor = MSO_ANCHOR.MIDDLE
        add_text(slide, x + 1.05, ry + 0.04, w - 1.2, 0.36, name, 13, font=MONO,
                 anchor=MSO_ANCHOR.MIDDLE)
    add_note(slide, x, y + h + 0.25, w,
             ["ไฟล์ Profile, Job และ log มีข้อมูลการเชื่อมต่อ", "อยู่ใน .gitignore แล้ว ไม่ควร commit ขึ้น git"])
    rows = [
        (1, "db_profiles.json", "Profile การเชื่อมต่อ รหัสผ่านเข้ารหัสด้วย Windows DPAPI ใช้ได้เฉพาะ Windows user เดิม"),
        (2, "saved_jobs.json", "Job ทั้งหมด แยกตาม Profile"),
        (3, "script_groups.json", "Script Groups แยกตาม Profile"),
        (4, "script_groups_backup.json", "เวอร์ชันก่อนหน้า สร้างใหม่ทุกครั้งที่บันทึกกลุ่ม"),
        (5, "preset_<ชื่อ>.json", "ชุด Job ที่บันทึกจาก Preset · Save"),
        (6, "app_settings.json", "ค่าตั้งของโปรแกรม เช่น Open result windows"),
        (7, "logs/run_….log", "log การรันวันละไฟล์ ไม่มีรหัสผ่าน ลบเองเมื่อเก่ากว่า 90 วัน"),
        (8, "jobs_export_….xlsx", "ไฟล์จากปุ่ม Export เลือกที่เก็บเองตอนบันทึก"),
    ]
    add_button_table(slide, x + w + 0.4, CONTENT_TOP, SLIDE_W - MARGIN - (x + w + 0.4), rows,
                     headers=("เลข", "ไฟล์", "เก็บอะไร"), size=12, col1=2.3)


def build():
    prs = Presentation()
    prs.slide_width = Inches(SLIDE_W)
    prs.slide_height = Inches(SLIDE_H)

    cover(prs)

    content_slide(
        prs, 2, "ภาพรวมหน้าจอ", "หน้าต่างหลักแบ่งเป็น 5 ส่วน", "overview",
        [
            (1, "แถบบน", "เลือก Profile ดู/แก้ข้อมูลเชื่อมต่อ กด Connect และจัดการ Profile"),
            (2, "แถบซ้าย", "รายการ Saved Jobs แท็บ Script Groups และปุ่ม Preset"),
            (3, "SQL Editor", "เขียนและรัน SQL ใส่ค่าจาก Excel บันทึกเป็น Job"),
            (4, "ผลลัพธ์", "แท็บ Results Grid, Execution Logs, Error & Debug"),
            (5, "แถบสถานะ", "Ready / Running… สถานะการเชื่อมต่อ จำนวน Excel parameter ไฟล์ log ของวันนี้ และตำแหน่ง cursor"),
        ],
        note=["ลากเส้นแบ่งเพื่อปรับขนาดแถบซ้าย และสัดส่วน Editor กับผลลัพธ์ได้",
              "เปิดได้ทีละหน้าต่าง ถ้าสั่งเปิดซ้ำ โปรแกรมจะดึงหน้าต่างเดิมขึ้นมา"],
        size=13, col1=1.4,
    )

    content_slide(
        prs, 3, "แถบบน (Top bar)", "เลือก Profile เชื่อมต่อฐานข้อมูล และจัดการ Profile", "topbar",
        [
            (1, "Profile", "เลือก Profile ที่บันทึกไว้ โหลดค่าเชื่อมต่อและแสดง Job ของ Profile นั้น"),
            (2, "ข้อมูลปลายทาง", "ชนิดฐานข้อมูล user@host:port และ Database / Service ที่จะต่อ"),
            (3, "✎ Details", "เปิด/ปิดช่องกรอกข้อมูลเชื่อมต่อ"),
            (4, "สถานะ", "Connected หรือ Not Connected"),
            (5, "🔌 Connect", "เชื่อมต่อฐานข้อมูลด้วยค่าในช่อง Details"),
            (6, "＋ New", "สร้าง Profile ใหม่ ทดสอบการเชื่อมต่อได้ก่อนกดสร้าง"),
            (7, "Save", "บันทึกค่าที่แก้ใน Details กลับเข้า Profile"),
            (8, "Import", "นำเข้า Profile จากไฟล์ JSON เลือก Merge หรือ Replace"),
            (9, "Export", "ส่งออก Profile เป็น JSON ถามก่อนว่าจะใส่รหัสผ่านในไฟล์หรือไม่"),
            (10, "ปุ่ม ⋯", "เมนู Delete profile และ Config file location"),
        ],
        note=["เปิดโปรแกรมแล้วจะโหลด Profile ที่ใช้ล่าสุดให้",
              "เปลี่ยน Profile แล้วการเชื่อมต่อเดิมจะถูกตัด ต้องกด Connect ใหม่"],
    )

    content_slide(
        prs, 4, "ช่องเชื่อมต่อ (Details)", "กดปุ่ม Details เพื่อเปิดช่องกรอกข้อมูลการเชื่อมต่อ", "details",
        [
            (1, "Database Type", "Oracle, PostgreSQL, MySQL, SQL Server เปลี่ยนแล้ว Port จะเปลี่ยนเป็นค่าเริ่มต้น (1521 / 5432 / 3306 / 1433)"),
            (2, "Host", "ชื่อเครื่องหรือ IP ของฐานข้อมูล"),
            (3, "Port", "พอร์ตของฐานข้อมูล"),
            (4, "Database / Service", "Oracle ใส่ Service Name ช่องนี้ไม่บังคับ (SQL Server ว่าง = master)"),
            (5, "User", "ชื่อผู้ใช้ฐานข้อมูล"),
            (6, "Password", "รหัสผ่าน แสดงเป็น *"),
            (7, "ไอคอนตา", "แสดง/ซ่อนรหัสผ่าน"),
            (8, "✎ Details ▴", "ปิดช่องกรอก"),
            (9, "Save", "บันทึกค่าในช่องเหล่านี้เข้า Profile"),
        ],
        note=["กด Connect ได้เมื่อกรอก Type, Host, Port, User และ Password ครบ",
              "รหัสผ่านในไฟล์ถูกเข้ารหัสด้วย Windows DPAPI"],
    )

    content_slide(
        prs, 5, "Saved Jobs", "เก็บ SQL ไว้เป็น Job ของแต่ละ Profile แล้วสั่งรันทีละตัวหรือทั้งชุด", "sidebar",
        [
            (1, "Saved Jobs", "รายการ Job ของ Profile ที่เลือก"),
            (2, "Script Groups", "เปิดหน้าต่าง Script Groups"),
            (3, "▶ Run all", "รันทุก Job ทีละตัว ถ้าติ๊กไว้จะเป็น Run selected (n) รันเฉพาะที่ติ๊ก Job ที่ error ไม่หยุดการรัน จบแล้วแสดงสรุป"),
            (4, "⇩ Export", "รัน Job ที่เลือกแล้วรวมผลเป็น Excel ไฟล์เดียว 1 Job = 1 Sheet"),
            (5, "Select all", "ติ๊ก/เอาติ๊กออกทุก Job และแสดงจำนวนที่เลือก"),
            (6, "🗑 Delete (n)", "ลบ Job ที่ติ๊ก ถามยืนยันก่อน"),
            (7, "ช่องติ๊ก", "เลือก Job"),
            (8, "ปุ่ม ▶ ในแถว", "รัน Job นี้ตัวเดียว"),
            (9, "ปุ่ม ✎ ในแถว", "แก้ไขชื่อและ SQL ของ Job"),
            (10, "ปุ่ม 🗑 ในแถว", "ลบ Job นี้ ถามยืนยันก่อน"),
            (11, "Preset · Save", "บันทึกชุด Job ของ Profile เป็นไฟล์ preset"),
            (12, "Preset · Load", "โหลดชุด Job จากไฟล์ preset"),
        ],
        size=12, img_w=4.0, col1=1.6,
    )

    content_slide(
        prs, 6, "SQL Editor", "เขียน SQL รัน และใส่ค่าจาก Excel", "editor",
        [
            (1, "▶ Run", "รัน SQL ใน Editor (หรือ Ctrl+Enter) ใช้ได้หลัง Connect"),
            (2, "📗 Load Excel", "เลือกค่าจากไฟล์ Excel มาใส่แทน parameter ใน SQL"),
            (3, "↩ Reset template", "เอาค่าที่ใส่จาก Excel ออก ให้ SQL กลับเป็น parameter เดิม"),
            (4, "💾 Save as Job", "บันทึก SQL นี้เป็น Job"),
            (5, "▦ Tables", "แสดงรายการ schema และ table ของฐานข้อมูล"),
            (6, "แถบ Excel parameter", "บอก parameter ที่ใส่ค่าอยู่ และจำนวนค่า"),
            (7, "✎ เปลี่ยนค่า", "เปิด Load Excel อีกครั้งเพื่อเลือกค่าใหม่"),
            (8, "Editor", "มีเลขบรรทัดและสี syntax ตัด ; หรือ / ท้ายคำสั่งให้ก่อนรัน"),
        ],
        note=["SELECT / WITH แสดงผลเป็นตาราง",
              "INSERT / UPDATE / DELETE / DDL แสดงจำนวนแถวที่เปลี่ยน และถามยืนยันก่อนรัน"],
    )

    content_slide(
        prs, 7, "Load Excel และ Reset template", "นำค่าจากคอลัมน์ใน Excel (เช่นเลขบัญชี) ไปใส่ในเงื่อนไข SQL", "load_excel",
        [
            (1, "Sheet", "เลือก worksheet"),
            (2, "ใส่แทน parameter", "ตำแหน่งใน SQL ที่จะใส่ค่า เช่น {ACCOUNT_LIST}, :name, รายการ IN (...) หรือ Auto WHERE"),
            (3, "เลือกคอลัมน์", "คอลัมน์ใน Excel"),
            (4, "เลือกค่า", "ติ๊กค่าที่ต้องการ มีช่องค้นหา"),
            (5, "☑ Select All", "ติ๊กทุกค่าในคอลัมน์"),
            (6, "ล้างที่เลือก", "เอาติ๊กออกทั้งหมด"),
            (7, "Selected values", "ค่าที่เลือกแล้ว (เลือก / ทั้งหมด)"),
            (8, "SQL ที่จะได้", "ตัวอย่าง SQL หลังใส่ค่า ตัวเลขใส่ตรง ๆ ข้อความใส่ '...'"),
            (9, "✓ Confirm", "ใส่ค่าลงใน SQL Editor"),
            (10, "ยกเลิก", "ปิดโดยไม่เปลี่ยน SQL"),
        ],
        note=["Reset template ใช้หน้าจอแบบเดียวกัน: เลือกคอลัมน์ ติ๊กค่าที่จะเอาออก",
              "ดู SQL หลัง Reset แล้วกด Confirm หรือกด Reset All Parameters"],
        img_w=6.9,
    )

    content_slide(
        prs, 8, "ผลลัพธ์ (Results)", "ผลของ Query แสดงในแท็บด้านล่างของหน้าจอ", "results",
        [
            (1, "📊 Results Grid", "ตารางผลลัพธ์ หน้าละ 1,000 แถว"),
            (2, "📋 Execution Logs", "log การเชื่อมต่อ การรัน และ Export บันทึกลงไฟล์ logs/ ด้วย"),
            (3, "🐛 Error & Debug", "รายละเอียด error ล่าสุด มีจุด ● เมื่อมี error ใหม่ที่ยังไม่ได้เปิดดู"),
            (4, "Open result windows", "ติ๊ก = เปิดผลแต่ละ Query เป็นหน้าต่างแยกด้วย (โปรแกรมจำค่าไว้)"),
            (5, "RESULT", "เลือกดูผลของแต่ละ Job แสดงเมื่อรันหลาย Job"),
            (6, "ข้อมูลผลลัพธ์", "ชื่อ Job จำนวนแถว × คอลัมน์ และแถวที่แสดงอยู่"),
            (7, "Prev / Next", "เปลี่ยนหน้า"),
            (8, "📄 Export CSV", "บันทึกผลเป็นไฟล์ CSV"),
            (9, "📗 Export Excel", "บันทึกผลเป็นไฟล์ Excel"),
            (10, "ตาราง", "NULL แสดงเป็น [NULL] วันที่แบบ yyyy-MM-dd HH:mm:ss.SSS กด Ctrl+C คัดลอกแถวที่เลือก"),
        ],
        img_w=7.0,
    )

    content_slide(
        prs, 9, "ระหว่างรัน", "เมื่อมีงานรันอยู่ จะมีแถบสีเหลืองเหนือผลลัพธ์", "running",
        [
            (1, "ข้อความสถานะ", "กำลังรัน Job ที่เท่าไรจากทั้งหมด ชื่อ Job และเวลาที่ใช้ (รัน SQL เดี่ยวหรือ Export จะบอกแยก)"),
            (2, "Progress bar", "ความคืบหน้าของ Job ทั้งชุด"),
            (3, "⏹ Stop (แถบเหลือง)", "หยุดงาน และข้าม Job ที่เหลือ"),
            (4, "Running…", "แถบสถานะล่างเปลี่ยนจาก Ready"),
        ],
        note=["Oracle: Stop ยกเลิก Query ที่กำลังรันได้ทันที",
              "PostgreSQL / MySQL / SQL Server: รอ Query ปัจจุบันจบ แล้วข้าม Job ที่เหลือ",
              "ระหว่างรันหลาย Job กด Run all ซ้ำไม่ได้"],
        size=13, col1=1.75,
    )

    content_slide(
        prs, 10, "Script Groups", "เก็บ Script เป็นกลุ่มแยกตาม Profile แล้วรันหรือ Export ทั้งกลุ่ม", "groups",
        [
            (1, "＋ New Group", "สร้างกลุ่มใหม่ใน Profile ที่เลือก"),
            (2, "รายการกลุ่ม", "กลุ่มของ Profile นี้ และจำนวน Script"),
            (3, "✎ Rename", "เปลี่ยนชื่อกลุ่ม"),
            (4, "🗑 Delete", "ลบกลุ่ม"),
            (5, "รายการ Script", "Script ในกลุ่ม รันตามลำดับนี้"),
            (6, "ปุ่ม ↑ ↓", "เลื่อนลำดับ Script"),
            (7, "✎ Edit", "แก้ไข Script"),
            (8, "🗑 Remove", "เอา Script ออกจากกลุ่ม"),
            (9, "＋ Add SQL", "เขียน SQL ใหม่เข้ากลุ่ม"),
            (10, "🕘 From Saved Jobs", "คัดลอก Job เข้ากลุ่ม Job เดิมยังอยู่"),
            (11, "SQL preview", "SQL ของ Script ที่เลือก"),
            (12, "▶ Run Group", "รันทุก Script ในกลุ่ม"),
            (13, "⇩ Export Group", "รันแล้วรวมผลเป็น Excel 1 Script = 1 Sheet"),
            (14, "⏹ Stop", "หยุดงานที่กำลังรัน"),
            (15, "⇧ Import Groups", "นำเข้ากลุ่มจากไฟล์ JSON"),
            (16, "⇩ Export Groups", "ส่งออกกลุ่มเป็นไฟล์ JSON"),
        ],
        note=["Script ในกลุ่มเป็นสำเนา แก้ในกลุ่มไม่กระทบ Saved Jobs"],
        size=10.5, img_w=6.9, col1=1.75,
    )

    content_slide(
        prs, 11, "การยืนยันก่อนแก้ข้อมูล", "ก่อนรันคำสั่งที่ไม่ใช่ SELECT โปรแกรมจะถามก่อนเสมอ", "confirm",
        [
            (1, "หัวข้อ", "จำนวนคำสั่งที่จะแก้ไขข้อมูลและ commit ทันที"),
            (2, "รายการคำสั่ง", "ชื่อ Job และ SQL ของคำสั่งที่แก้ข้อมูล"),
            (3, "Profile / Database", "ปลายทางที่จะรัน ให้ตรวจก่อนกด"),
            (4, "คำเตือน", "ย้อนกลับไม่ได้หลัง commit"),
            (5, "ยกเลิก", "ไม่รัน ปุ่มนี้ถูกเลือกไว้ก่อน กด Esc ก็คือยกเลิก"),
            (6, "▶ รันและ commit", "รันคำสั่ง"),
        ],
        note=["ถามเมื่อมีคำสั่ง UPDATE / INSERT / DELETE / DDL",
              "ใช้กับ Run, ปุ่มรันของแต่ละ Job, Run all / Run selected และ Run Group",
              "คำสั่ง SELECT / WITH ไม่ถาม"],
        img_w=5.6, size=13, col1=1.85,
    )

    content_slide(
        prs, 12, "ขั้นตอนการใช้งาน", "ลำดับการใช้งานตั้งแต่สร้าง Profile จนรันเป็นชุด", "steps",
        [
            (1, "＋ New", "สร้าง Profile เลือกชนิดฐานข้อมูล กรอกข้อมูล ทดสอบการเชื่อมต่อ แล้วสร้าง"),
            (2, "🔌 Connect", "เลือก Profile แล้วเชื่อมต่อ"),
            (3, "Load Excel / Run", "เขียน SQL ใส่ค่าจาก Excel ถ้าต้องการ แล้วรัน (Ctrl+Enter)"),
            (4, "💾 Save as Job", "ตรวจผลใน Results Grid แล้วบันทึกเป็น Job"),
            (5, "Run selected / Export", "ติ๊ก Job ที่ต้องการ แล้วรัน หรือ Export เป็น Excel"),
            (6, "Script Groups", "ถ้าต้องรันเป็นชุด สร้างกลุ่ม เพิ่ม Script แล้ว Run Group หรือ Export"),
        ],
        headers=("ขั้น", "ปุ่ม", "สิ่งที่ทำ"), size=13, col1=1.8,
    )

    files_slide(prs, 13)

    prs.save(OUTPUT)
    print("saved", OUTPUT)


if __name__ == "__main__":
    build()
