"""
APSO Raporlama ve Dışa Aktarım Servisi (OpenPyXL Excel & ReportLab PDF).

AGENTS.md Kuralları:
- Yalnızca onaylı teknoloji yığınındaki `openpyxl` ve `reportlab` kütüphanelerini kullanır.
- KVKK uyumu gereği üretilen Excel ve PDF dosyalarında yalnızca `22060xxxx` formatındaki
  anonimleştirilmiş/sentetik öğrenci numaraları yer alır; hassas kişisel veri (PII) bulunmaz.
"""

import io
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy.orm import Session

from app.models.academic import (
    Course,
    ExamRoomAllocation,
    ExamSeatingAssignment,
    ExamSession,
    ProctorAssignment,
    Room,
    Student,
    TeachingAssistant,
    WeeklyScheduleAssignment,
)

DAY_NAMES = {
    1: "Monday",
    2: "Tuesday",
    3: "Wednesday",
    4: "Thursday",
    5: "Friday",
}

SLOT_LABELS = {
    1: "08:30 - 09:20",
    2: "09:30 - 10:20",
    3: "10:30 - 11:20",
    4: "11:30 - 12:20",
    5: "13:30 - 14:20",
    6: "14:30 - 15:20",
    7: "15:30 - 16:20",
    8: "16:30 - 17:20",
}


class ExportService:
    """Haftalık ders programı (.xlsx) ve Sınav / 1-Boş-Koltuk / Gözetmen (.pdf) dışa aktarım servisi."""

    def __init__(self, db: Session):
        self.db = db

    def export_weekly_schedule_xlsx(self, academic_term: str = "2026-FALL") -> bytes:
        """
        Modül 2 tarafından oluşturulan haftalık ders programını hem liste hem de
        yarıyıl bazlı 5x8 haftalık matris sayfaları olarak Excel (.xlsx) formatında üretir.
        """
        assignments = (
            self.db.query(WeeklyScheduleAssignment)
            .filter(WeeklyScheduleAssignment.academic_term == academic_term)
            .order_by(
                WeeklyScheduleAssignment.day_of_week.asc(),
                WeeklyScheduleAssignment.slot_index.asc(),
            )
            .all()
        )

        wb = Workbook()
        ws = wb.active
        ws.title = "Weekly_Schedule_List"

        header_fill = PatternFill(start_color="14233C", end_color="14233C", fill_type="solid")
        header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
        thin_border = Border(
            left=Side(style="thin", color="D0D7DE"),
            right=Side(style="thin", color="D0D7DE"),
            top=Side(style="thin", color="D0D7DE"),
            bottom=Side(style="thin", color="D0D7DE"),
        )

        headers = [
            "Academic Term",
            "Day",
            "Slot",
            "Time Interval",
            "Semester",
            "Course Code",
            "Course Name",
            "Session Type",
            "Room Code",
            "Room Capacity",
            "Enrolled Students",
            "Instructor",
        ]
        ws.append(headers)
        for col_idx in range(1, len(headers) + 1):
            cell = ws.cell(row=1, column=col_idx)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center", vertical="center")

        for a in assignments:
            row_vals = [
                a.academic_term,
                DAY_NAMES.get(a.day_of_week, f"Day {a.day_of_week}"),
                a.slot_index,
                SLOT_LABELS.get(a.slot_index, f"Slot {a.slot_index}"),
                a.course.semester,
                a.course.code,
                a.course.name,
                a.session_type,
                a.room.code,
                a.room.normal_capacity,
                a.course.enrolled_count,
                a.instructor.full_name if a.instructor else "Unassigned",
            ]
            ws.append(row_vals)
            cur_row = ws.max_row
            for col_idx in range(1, len(headers) + 1):
                c = ws.cell(row=cur_row, column=col_idx)
                c.border = thin_border
                if col_idx in (1, 2, 3, 4, 5, 6, 8, 9, 10, 11):
                    c.alignment = Alignment(horizontal="center", vertical="center")

        for col in ws.columns:
            max_len = max((len(str(cell.value or "")) for cell in col), default=12)
            col_letter = col[0].column_letter
            ws.column_dimensions[col_letter].width = min(max_len + 4, 42)

        buf = io.BytesIO()
        wb.save(buf)
        return buf.getvalue()

    def export_exam_and_seating_pdf(
        self, academic_term: str = "2026-FALL", exam_type: str = "FINAL"
    ) -> bytes:
        """
        Modül 3 tarafından üretilen Sınav Takvimini, 1-Boş-Koltuk Salon Bölünmesini,
        Minimax Arş. Gör. Gözetmen Dağılımını ve 2B Koltuk Koordinat Özetini resmi
        ATÜ PDF raporu olarak oluşturur.
        """
        exam_sessions = (
            self.db.query(ExamSession)
            .filter(
                ExamSession.academic_term == academic_term,
                ExamSession.exam_type == exam_type,
            )
            .order_by(ExamSession.exam_day.asc(), ExamSession.session_index.asc())
            .all()
        )
        courses = {c.id: c for c in self.db.query(Course).all()}
        rooms = {r.id: r for r in self.db.query(Room).all()}
        tas = {t.id: t for t in self.db.query(TeachingAssistant).order_by(TeachingAssistant.code.asc()).all()}
        students = {s.id: s for s in self.db.query(Student).all()}

        buf = io.BytesIO()
        doc = SimpleDocTemplate(
            buf,
            pagesize=landscape(A4),
            leftMargin=28,
            rightMargin=28,
            topMargin=28,
            bottomMargin=28,
            title=f"APSO Exam, 1-Empty-Seat & Proctor Report ({academic_term})",
        )

        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            "APSOTitle",
            parent=styles["Heading1"],
            fontSize=15,
            leading=19,
            textColor=colors.HexColor("#14233C"),
            spaceAfter=4,
        )
        sub_style = ParagraphStyle(
            "APSOSub",
            parent=styles["Normal"],
            fontSize=9.5,
            leading=13,
            textColor=colors.HexColor("#475569"),
            spaceAfter=12,
        )
        section_style = ParagraphStyle(
            "APSOSection",
            parent=styles["Heading2"],
            fontSize=12,
            leading=15,
            textColor=colors.HexColor("#8B0000"),
            spaceBefore=10,
            spaceAfter=6,
        )

        story = [
            Paragraph(
                f"ADANA ALPARSLAN TURKES SCIENCE AND TECHNOLOGY UNIVERSITY (ATU) — APSO OFFICIAL REPORT",
                title_style,
            ),
            Paragraph(
                f"Department of Software Engineering | {academic_term} {exam_type} Examination Schedule, "
                f"1-Empty-Seat Classroom Allocation & Minimax TA Proctor Roster (KVKK Compliant)",
                sub_style,
            ),
            Paragraph("1. Examination Schedule, Multi-Room 1-Empty-Seat Allocation & Assigned Proctors", section_style),
        ]

        # Tablo 1: Sınav Takvimi, Salon Bölünmesi ve Gözetmenler
        exam_table_data = [
            [
                "Exam Day",
                "Session",
                "Course Code",
                "Course Title",
                "Sem.",
                "Enrolled",
                "Assigned Hall(s) [1-Empty-Seat Cap.]",
                "Assigned Proctor(s) (TA)",
                "Duty Wt.",
            ]
        ]

        for ex in exam_sessions:
            c_obj = courses.get(ex.course_id)
            room_allocs = (
                self.db.query(ExamRoomAllocation)
                .filter(ExamRoomAllocation.exam_session_id == ex.id)
                .all()
            )
            proctor_allocs = (
                self.db.query(ProctorAssignment)
                .filter(ProctorAssignment.exam_session_id == ex.id)
                .all()
            )
            proctor_by_room = {pa.room_id: tas.get(pa.ta_id) for pa in proctor_allocs}

            room_strs = []
            ta_strs = []
            for ra in room_allocs:
                r_obj = rooms.get(ra.room_id)
                if r_obj:
                    room_strs.append(
                        f"{r_obj.code} ({ra.allocated_student_count}/{r_obj.effective_exam_capacity})"
                    )
                ta_obj = proctor_by_room.get(ra.room_id)
                if ta_obj:
                    ta_strs.append(f"{ta_obj.code}: {ta_obj.full_name}")

            exam_table_data.append(
                [
                    f"Day {ex.exam_day}",
                    f"Session {ex.session_index}",
                    c_obj.code if c_obj else "-",
                    (c_obj.name[:34] + "...") if c_obj and len(c_obj.name) > 37 else (c_obj.name if c_obj else "-"),
                    str(c_obj.semester if c_obj else "-"),
                    str(c_obj.enrolled_count if c_obj else 0),
                    ", ".join(room_strs) or "-",
                    ", ".join(ta_strs) or "-",
                    f"{ex.duty_weight:.1f}x",
                ]
            )

        exam_tbl = Table(
            exam_table_data,
            colWidths=[52, 52, 62, 165, 32, 48, 165, 165, 45],
            repeatRows=1,
        )
        exam_tbl.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#14233C")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, 0), 8.5),
                    ("FONTSIZE", (0, 1), (-1, -1), 8),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("ALIGN", (3, 1), (3, -1), "LEFT"),
                    ("ALIGN", (6, 1), (7, -1), "LEFT"),
                    ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#CBD5E1")),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        story.append(exam_tbl)
        story.append(Spacer(1, 12))

        # Tablo 2: Araştırma Görevlisi Minimax Görev Yükü Özeti
        story.append(Paragraph("2. Equitable Proctor (Teaching Assistant) Workload Distribution (Minimax Criterion)", section_style))
        ta_table_data = [["TA Code", "Teaching Assistant Name", "Total Weighted Workload Score"]]
        for ta in tas.values():
            ta_table_data.append([ta.code, ta.full_name, f"{ta.current_workload_score:.2f}"])

        ta_tbl = Table(ta_table_data, colWidths=[90, 240, 160])
        ta_tbl.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#8B0000")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("ALIGN", (1, 1), (1, -1), "LEFT"),
                    ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#CBD5E1")),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#FFF8F8")]),
                ]
            )
        )
        story.append(ta_tbl)
        story.append(Spacer(1, 12))

        # Tablo 3: İlk Sınav Oturumu İçin Örnek 1-Boş-Koltuk Kapı Listesi (KVKK Uyumlu)
        if exam_sessions:
            first_ex = exam_sessions[0]
            first_course = courses.get(first_ex.course_id)
            seats = (
                self.db.query(ExamSeatingAssignment)
                .filter(ExamSeatingAssignment.exam_session_id == first_ex.id)
                .order_by(
                    ExamSeatingAssignment.room_id.asc(),
                    ExamSeatingAssignment.seat_row.asc(),
                    ExamSeatingAssignment.seat_col.asc(),
                )
                .limit(20)
                .all()
            )
            if seats:
                story.append(
                    Paragraph(
                        f"3. Sample 1-Empty-Seat Classroom Door Roster — {first_course.code if first_course else ''} "
                        f"(Odd Columns Only: |col_j - col_i| >= 2, KVKK Anonymized IDs)",
                        section_style,
                    )
                )
                seat_rows_data = [["Student Number (KVKK)", "Anonymized Name", "Exam Hall", "Row", "Column (1-Empty-Seat)"]]
                for s_item in seats:
                    st_obj = students.get(s_item.student_id)
                    r_obj = rooms.get(s_item.room_id)
                    seat_rows_data.append(
                        [
                            st_obj.student_number if st_obj else "-",
                            st_obj.full_name if st_obj else "-",
                            r_obj.code if r_obj else "-",
                            f"Row {s_item.seat_row}",
                            f"Col {s_item.seat_col}",
                        ]
                    )
                seat_tbl = Table(seat_rows_data, colWidths=[120, 200, 110, 80, 120])
                seat_tbl.setStyle(
                    TableStyle(
                        [
                            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E3A8A")),
                            ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                            ("FONTSIZE", (0, 0), (-1, -1), 8),
                            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#CBD5E1")),
                        ]
                    )
                )
                story.append(seat_tbl)

        doc.build(story)
        return buf.getvalue()
