"""
APSO Excel (.xlsx) Veri İçe Aktarma (Import) ve Pydantic v2 Şema Doğrulama Servisi.

AGENTS.md Kuralı:
- Tüm dış girdileri (yüklenen Excel/CSV dosyaları dahil) sunucu tarafında Pydantic v2
  şema doğrulamasından geçirmeden veritabanına veya CP-SAT çözücüsüne gönderme.
- Hatalı satırları sessizce yutma; satır numarası ve Türkçe hata açıklamasıyla raporla.
"""

import io
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.models.academic import Course, Instructor, Room
from app.schemas.academic import (
    CourseImportRowSchema,
    ExcelImportResultResponse,
    ExcelImportRowError,
    RoomImportRowSchema,
)


class ExcelImportService:
    """Bölüm ders ve amfi/laboratuvar verilerini Excel (.xlsx) şablonundan okuyup doğrulayan servis."""

    def __init__(self, db: Session):
        self.db = db

    def generate_import_template_xlsx(self) -> bytes:
        """
        Bölüm koordinatörünün ders ve amfi/lab envanterini toplu yükleyebilmesi için
        örnek satırlar içeren resmi APSO Excel (.xlsx) veri yükleme şablonunu üretir.
        """
        wb = Workbook()

        header_fill = PatternFill(start_color="14233C", end_color="14233C", fill_type="solid")
        header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")

        # Sayfa 1: Courses (Dersler)
        ws_courses = wb.active
        ws_courses.title = "Courses"
        course_headers = [
            "code",
            "name",
            "semester",
            "ects",
            "theory_hours",
            "lab_hours",
            "is_mandatory",
            "requires_lab_room",
            "enrolled_count",
            "instructor_code",
        ]
        ws_courses.append(course_headers)
        for col_idx in range(1, len(course_headers) + 1):
            c = ws_courses.cell(row=1, column=col_idx)
            c.fill = header_fill
            c.font = header_font
            c.alignment = Alignment(horizontal="center")

        # Örnek satır
        ws_courses.append(
            ["SE409", "Cloud Architecture & Optimization", 7, 5, 3, 0, True, False, 42, "INST-01"]
        )

        # Sayfa 2: Rooms (Derslikler ve Laboratuvarlar)
        ws_rooms = wb.create_sheet(title="Rooms")
        room_headers = [
            "code",
            "name",
            "room_type",
            "normal_capacity",
            "seat_rows",
            "seat_cols",
        ]
        ws_rooms.append(room_headers)
        for col_idx in range(1, len(room_headers) + 1):
            c = ws_rooms.cell(row=1, column=col_idx)
            c.fill = header_fill
            c.font = header_font
            c.alignment = Alignment(horizontal="center")

        ws_rooms.append(["B-D302", "Lecture Hall D-302", "LECTURE", 64, 8, 8])

        buf = io.BytesIO()
        wb.save(buf)
        return buf.getvalue()

    @staticmethod
    def _parse_bool(val, default: bool = False) -> bool:
        if isinstance(val, bool):
            return val
        if val is None:
            return default
        s = str(val).strip().lower()
        return s in ("true", "1", "yes", "evet", "y")

    def import_excel_workbook(self, file_bytes: bytes, filename: str = "upload.xlsx") -> ExcelImportResultResponse:
        """
        Yüklenen Excel (.xlsx) dosyasındaki `Courses` ve `Rooms` sayfalarını okur,
        her satırı Pydantic v2 şemasından geçirir ve geçerli kayıtları veritabanına yazar.
        """
        try:
            wb = load_workbook(io.BytesIO(file_bytes), data_only=True)
        except Exception as exc:
            raise ValueError(f"Geçersiz veya bozuk Excel (.xlsx) dosyası: {exc}") from exc

        courses_created = 0
        courses_updated = 0
        rooms_created = 0
        rooms_updated = 0
        row_errors: list[ExcelImportRowError] = []

        instructor_by_code = {i.code.upper(): i for i in self.db.query(Instructor).all()}
        course_by_code = {c.code.upper(): c for c in self.db.query(Course).all()}
        room_by_code = {r.code.upper(): r for r in self.db.query(Room).all()}

        # 1. "Courses" Sayfası İşleme
        if "Courses" in wb.sheetnames:
            ws_c = wb["Courses"]
            for row_idx, row_vals in enumerate(ws_c.iter_rows(min_row=2, values_only=True), start=2):
                if not row_vals or all(v is None or str(v).strip() == "" for v in row_vals):
                    continue
                raw_code = str(row_vals[0] or "").strip().upper()
                try:
                    validated = CourseImportRowSchema(
                        code=raw_code,
                        name=str(row_vals[1] or "").strip(),
                        semester=int(row_vals[2]) if row_vals[2] is not None else 0,
                        ects=int(row_vals[3]) if row_vals[3] is not None else 0,
                        theory_hours=int(row_vals[4]) if len(row_vals) > 4 and row_vals[4] is not None else 3,
                        lab_hours=int(row_vals[5]) if len(row_vals) > 5 and row_vals[5] is not None else 0,
                        is_mandatory=self._parse_bool(row_vals[6] if len(row_vals) > 6 else True, True),
                        requires_lab_room=self._parse_bool(row_vals[7] if len(row_vals) > 7 else False, False),
                        enrolled_count=int(row_vals[8]) if len(row_vals) > 8 and row_vals[8] is not None else 40,
                        instructor_code=(
                            str(row_vals[9]).strip().upper()
                            if len(row_vals) > 9 and row_vals[9] is not None and str(row_vals[9]).strip()
                            else None
                        ),
                    )
                except (ValidationError, ValueError, TypeError) as exc:
                    row_errors.append(
                        ExcelImportRowError(
                            sheet_name="Courses",
                            row_number=row_idx,
                            identifier=raw_code or f"Row-{row_idx}",
                            error_message_tr=f"Pydantic v2 Şema Doğrulama Hatası: {exc}",
                        )
                    )
                    continue

                inst_id = None
                if validated.instructor_code:
                    inst_obj = instructor_by_code.get(validated.instructor_code)
                    if inst_obj:
                        inst_id = inst_obj.id

                existing_c = course_by_code.get(validated.code)
                if existing_c:
                    existing_c.name = validated.name
                    existing_c.semester = validated.semester
                    existing_c.ects = validated.ects
                    existing_c.theory_hours = validated.theory_hours
                    existing_c.lab_hours = validated.lab_hours
                    existing_c.is_mandatory = validated.is_mandatory
                    existing_c.requires_lab_room = validated.requires_lab_room
                    existing_c.enrolled_count = validated.enrolled_count
                    if inst_id is not None:
                        existing_c.instructor_id = inst_id
                    courses_updated += 1
                else:
                    new_c = Course(
                        code=validated.code,
                        name=validated.name,
                        semester=validated.semester,
                        ects=validated.ects,
                        theory_hours=validated.theory_hours,
                        lab_hours=validated.lab_hours,
                        is_mandatory=validated.is_mandatory,
                        requires_lab_room=validated.requires_lab_room,
                        enrolled_count=validated.enrolled_count,
                        instructor_id=inst_id,
                    )
                    self.db.add(new_c)
                    self.db.flush()
                    course_by_code[new_c.code] = new_c
                    courses_created += 1

        # 2. "Rooms" Sayfası İşleme
        if "Rooms" in wb.sheetnames:
            ws_r = wb["Rooms"]
            for row_idx, row_vals in enumerate(ws_r.iter_rows(min_row=2, values_only=True), start=2):
                if not row_vals or all(v is None or str(v).strip() == "" for v in row_vals):
                    continue
                raw_code = str(row_vals[0] or "").strip().upper()
                try:
                    validated_r = RoomImportRowSchema(
                        code=raw_code,
                        name=str(row_vals[1] or "").strip(),
                        room_type=str(row_vals[2] or "LECTURE").strip().upper(),
                        normal_capacity=int(row_vals[3]) if row_vals[3] is not None else 0,
                        seat_rows=int(row_vals[4]) if len(row_vals) > 4 and row_vals[4] is not None else 0,
                        seat_cols=int(row_vals[5]) if len(row_vals) > 5 and row_vals[5] is not None else 0,
                    )
                except (ValidationError, ValueError, TypeError) as exc:
                    row_errors.append(
                        ExcelImportRowError(
                            sheet_name="Rooms",
                            row_number=row_idx,
                            identifier=raw_code or f"Row-{row_idx}",
                            error_message_tr=f"Pydantic v2 Şema Doğrulama Hatası: {exc}",
                        )
                    )
                    continue

                existing_r = room_by_code.get(validated_r.code)
                if existing_r:
                    existing_r.name = validated_r.name
                    existing_r.room_type = validated_r.room_type
                    existing_r.normal_capacity = validated_r.normal_capacity
                    existing_r.seat_rows = validated_r.seat_rows
                    existing_r.seat_cols = validated_r.seat_cols
                    rooms_updated += 1
                else:
                    new_r = Room(
                        code=validated_r.code,
                        name=validated_r.name,
                        room_type=validated_r.room_type,
                        normal_capacity=validated_r.normal_capacity,
                        seat_rows=validated_r.seat_rows,
                        seat_cols=validated_r.seat_cols,
                    )
                    self.db.add(new_r)
                    self.db.flush()
                    room_by_code[new_r.code] = new_r
                    rooms_created += 1

        self.db.commit()

        return ExcelImportResultResponse(
            filename=filename,
            courses_created=courses_created,
            courses_updated=courses_updated,
            rooms_created=rooms_created,
            rooms_updated=rooms_updated,
            total_errors=len(row_errors),
            row_errors=row_errors,
        )
