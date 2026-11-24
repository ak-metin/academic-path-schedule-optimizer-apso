"""
APSO Tek Gerçek Kaynak (Single Source of Truth) Veritabanı Şeması (SQLAlchemy 2.0).

Bu modül üç çekirdek motorun (Curriculum DAG Engine, Weekly Course Scheduling CSP,
Exam & Seating & Proctor CSP) ihtiyaç duyduğu tüm ilişkisel tabloları ve
bütünlük kısıtlarını (ForeignKey, UniqueConstraint, CheckConstraint) tanımlar.
"""

import math
from datetime import datetime, timezone
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


# ==============================================================================
# 1. MODÜL 1 & 2 ORTAK TABLOLAR: Öğretim Elemanları, Müfredat ve Önkoşullar
# ==============================================================================

class Instructor(Base):
    """Bölüm öğretim elemanları (Prof., Doç., Dr. Öğr. Üyesi, Öğr. Gör.)."""

    __tablename__ = "instructors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    title: Mapped[str] = mapped_column(String(64), nullable=False)
    department: Mapped[str] = mapped_column(String(120), default="Software Engineering")
    max_weekly_hours: Mapped[int] = mapped_column(Integer, default=16, nullable=False)

    courses: Mapped[list["Course"]] = relationship("Course", back_populates="instructor")
    availabilities: Mapped[list["InstructorAvailability"]] = relationship(
        "InstructorAvailability", back_populates="instructor", cascade="all, delete-orphan"
    )


class InstructorAvailability(Base):
    """
    Öğretim elemanlarının haftalık gün (1=Pzt..5=Cum) ve saat dilimi (1..8)
    bazında müsaitlik (Hard Constraint) ve tercih cezası (Soft Constraint) tablosu.
    preference_penalty: 0 = Çok İstenen Saat, 1 = Normal, 3 = İstenmeyen Saat.
    """

    __tablename__ = "instructor_availabilities"
    __table_args__ = (
        UniqueConstraint("instructor_id", "day_of_week", "slot_index", name="uq_instructor_day_slot"),
        CheckConstraint("day_of_week >= 1 AND day_of_week <= 5", name="ck_inst_avail_day"),
        CheckConstraint("slot_index >= 1 AND slot_index <= 8", name="ck_inst_avail_slot"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    instructor_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("instructors.id", ondelete="CASCADE"), nullable=False, index=True
    )
    day_of_week: Mapped[int] = mapped_column(Integer, nullable=False)
    slot_index: Mapped[int] = mapped_column(Integer, nullable=False)
    is_available: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    preference_penalty: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    instructor: Mapped["Instructor"] = relationship("Instructor", back_populates="availabilities")


class Course(Base):
    """
    ATÜ Yazılım Mühendisliği 8 dönemlik müfredat dersleri.
    Modül 1'de DAG düğümlerini (node), Modül 2 ve 3'te ise zamanlanacak ders/sınav
    birimlerini temsil eder.
    """

    __tablename__ = "courses"
    __table_args__ = (
        CheckConstraint("semester >= 1 AND semester <= 8", name="ck_course_semester"),
        CheckConstraint("ects > 0 AND ects <= 30", name="ck_course_ects"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    code: Mapped[str] = mapped_column(String(24), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    semester: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    ects: Mapped[int] = mapped_column(Integer, nullable=False)
    theory_hours: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    lab_hours: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_mandatory: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    requires_lab_room: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    enrolled_count: Mapped[int] = mapped_column(Integer, default=40, nullable=False)

    instructor_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("instructors.id", ondelete="SET NULL"), nullable=True, index=True
    )

    instructor: Mapped["Instructor | None"] = relationship("Instructor", back_populates="courses")
    enrollments: Mapped[list["Enrollment"]] = relationship(
        "Enrollment", back_populates="course", cascade="all, delete-orphan"
    )


class CoursePrerequisite(Base):
    """
    Modül 1 (Curriculum Graph Engine): Dersler arası yönlü bağımlılık kenarları (Directed Edges).
    prerequisite_course_id -> target_course_id (Örn: CSE101 -> CSE102).
    is_corequisite=True ise yan-koşul (aynı dönemde birlikte alınabilen bağımlı ders) anlamına gelir.
    """

    __tablename__ = "course_prerequisites"
    __table_args__ = (
        UniqueConstraint(
            "prerequisite_course_id", "target_course_id", name="uq_prerequisite_edge"
        ),
        CheckConstraint(
            "prerequisite_course_id != target_course_id", name="ck_no_self_prerequisite"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    prerequisite_course_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    target_course_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    is_corequisite: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    prerequisite_course: Mapped["Course"] = relationship(
        "Course", foreign_keys=[prerequisite_course_id]
    )
    target_course: Mapped["Course"] = relationship(
        "Course", foreign_keys=[target_course_id]
    )


# ==============================================================================
# 2. FİZİKSEL MEKÂNLAR (AMFİLER / LABLAR) VE KVKK UYUMLU ÖĞRENCİ KAYITLARI
# ==============================================================================

class Room(Base):
    """
    Derslik, Amfi ve Bilgisayar Laboratuvarları.
    Modül 3'teki 1-Boş-Koltuk Kuralı (1-Empty-Seat Rule) için her salonun fiziksel
    satır (seat_rows) ve sütun (seat_cols) matris boyutları tutulur.
    """

    __tablename__ = "rooms"
    __table_args__ = (
        CheckConstraint("normal_capacity > 0", name="ck_room_capacity_pos"),
        CheckConstraint("seat_rows > 0 AND seat_cols > 0", name="ck_room_grid_pos"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    room_type: Mapped[str] = mapped_column(String(32), default="LECTURE", nullable=False)  # LECTURE | LAB
    normal_capacity: Mapped[int] = mapped_column(Integer, nullable=False)
    seat_rows: Mapped[int] = mapped_column(Integer, nullable=False)
    seat_cols: Mapped[int] = mapped_column(Integer, nullable=False)

    @property
    def effective_exam_capacity(self) -> int:
        """
        Modül 3 — 1-Boş-Koltuk Kuralı efektif sınav kapasitesi formülü:
        Cap_exam(r) = Rows(r) * ceil(Cols(r) / 2)
        """
        return self.seat_rows * math.ceil(self.seat_cols / 2.0)


class Student(Base):
    """
    KVKK Uyumlu Anonimleştirilmiş / Sentetik Öğrenci Tablosu.
    Gerçek TC Kimlik No veya hassas kişisel veri (PII) tutulmaz; yalnızca
    22060xxxx formatında sentetik öğrenci numarası ve akademik dönem durumu tutulur.
    """

    __tablename__ = "students"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    student_number: Mapped[str] = mapped_column(String(24), unique=True, nullable=False, index=True)
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    current_semester: Mapped[int] = mapped_column(Integer, default=1, nullable=False, index=True)
    is_irregular: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)

    enrollments: Mapped[list["Enrollment"]] = relationship(
        "Enrollment", back_populates="student", cascade="all, delete-orphan"
    )


class Enrollment(Base):
    """
    Öğrencilerin ders kayıtları ve başarı durumları.
    status: 'ENROLLED' (Aktif dönemde alıyor), 'PASSED' (Geçti), 'FAILED' (Kaldı / Tekrar alacak).
    is_retake: Öğrencinin bu dersi alttan tekrar alıp almadığını belirtir (Modül 1 C_DAG hesabı için).
    """

    __tablename__ = "enrollments"
    __table_args__ = (
        UniqueConstraint("student_id", "course_id", "academic_term", name="uq_student_course_term"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    student_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True
    )
    course_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    academic_term: Mapped[str] = mapped_column(String(32), default="2026-FALL", nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="ENROLLED", nullable=False, index=True)
    is_retake: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    student: Mapped["Student"] = relationship("Student", back_populates="enrollments")
    course: Mapped["Course"] = relationship("Course", back_populates="enrollments")


# ==============================================================================
# 3. MODÜL 2 ÇIKTI TABLOSU: Haftalık Ders Programı Atamaları
# ==============================================================================

class WeeklyScheduleAssignment(Base):
    """
    Modül 2 (Google OR-Tools CP-SAT) tarafından üretilen haftalık ders programı.
    Aynı odada veya aynı hocada aynı (day_of_week, slot_index) çakışması veritabanı
    seviyesinde de UniqueConstraint ile korunur.
    """

    __tablename__ = "weekly_schedule_assignments"
    __table_args__ = (
        UniqueConstraint("academic_term", "room_id", "day_of_week", "slot_index", name="uq_weekly_room_slot"),
        CheckConstraint("day_of_week >= 1 AND day_of_week <= 5", name="ck_weekly_day"),
        CheckConstraint("slot_index >= 1 AND slot_index <= 8", name="ck_weekly_slot"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    academic_term: Mapped[str] = mapped_column(String(32), default="2026-FALL", nullable=False, index=True)
    course_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    room_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False, index=True
    )
    instructor_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("instructors.id", ondelete="SET NULL"), nullable=True, index=True
    )
    day_of_week: Mapped[int] = mapped_column(Integer, nullable=False)
    slot_index: Mapped[int] = mapped_column(Integer, nullable=False)
    session_type: Mapped[str] = mapped_column(String(24), default="THEORY", nullable=False)  # THEORY | LAB
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    course: Mapped["Course"] = relationship("Course")
    room: Mapped["Room"] = relationship("Room")
    instructor: Mapped["Instructor | None"] = relationship("Instructor")


# ==============================================================================
# 4. MODÜL 3 TABLOLARI: Araştırma Görevlileri, Sınav Oturumları, Oturma Planı & Gözetmenlik
# ==============================================================================

class TeachingAssistant(Base):
    """
    Araştırma Görevlileri (Sınav Gözetmenleri / Invigilators).
    Kendi lisansüstü ders saatleriyle çakışmadan Minimax adalet kriterine göre atanırlar.
    """

    __tablename__ = "teaching_assistants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    current_workload_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    unavailabilities: Mapped[list["TAUnavailability"]] = relationship(
        "TAUnavailability", back_populates="ta", cascade="all, delete-orphan"
    )


class TAUnavailability(Base):
    """
    Araştırma görevlilerinin kendi yüksek lisans/doktora dersleri veya izinli oldukları
    sınav günü (exam_day: 1..10) ve sınav oturumu (session_index: 1..4) kısıtları.
    """

    __tablename__ = "ta_unavailabilities"
    __table_args__ = (
        UniqueConstraint("ta_id", "exam_day", "session_index", name="uq_ta_exam_slot"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    ta_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("teaching_assistants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    exam_day: Mapped[int] = mapped_column(Integer, nullable=False)
    session_index: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(String(160), default="Graduate Course", nullable=False)

    ta: Mapped["TeachingAssistant"] = relationship("TeachingAssistant", back_populates="unavailabilities")


class ExamSession(Base):
    """
    Modül 3 tarafından oluşturulan vize (MIDTERM) veya final (FINAL) sınav oturumu.
    Kalabalık dersler 1-boş-koltuk kuralı nedeniyle birden fazla salona (ExamRoomAllocation) bölünebilir.
    """

    __tablename__ = "exam_sessions"
    __table_args__ = (
        UniqueConstraint("academic_term", "exam_type", "course_id", name="uq_term_exam_course"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    academic_term: Mapped[str] = mapped_column(String(32), default="2026-FALL", nullable=False, index=True)
    exam_type: Mapped[str] = mapped_column(String(24), default="FINAL", nullable=False)  # MIDTERM | FINAL
    course_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    exam_day: Mapped[int] = mapped_column(Integer, nullable=False)  # 1..10 (2 haftalık sınav takvimi)
    session_index: Mapped[int] = mapped_column(Integer, nullable=False)  # 1..4 (Gün içi oturum)
    is_weekend_or_evening: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    duty_weight: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)  # Normal=1.0, HaftaSonu/Akşam=1.5

    course: Mapped["Course"] = relationship("Course")
    room_allocations: Mapped[list["ExamRoomAllocation"]] = relationship(
        "ExamRoomAllocation", back_populates="exam_session", cascade="all, delete-orphan"
    )
    seating_assignments: Mapped[list["ExamSeatingAssignment"]] = relationship(
        "ExamSeatingAssignment", back_populates="exam_session", cascade="all, delete-orphan"
    )
    proctor_assignments: Mapped[list["ProctorAssignment"]] = relationship(
        "ProctorAssignment", back_populates="exam_session", cascade="all, delete-orphan"
    )


class ExamRoomAllocation(Base):
    """Bir sınav oturumunun atandığı fiziksel amfi(ler) ve o amfideki öğrenci sayısı."""

    __tablename__ = "exam_room_allocations"
    __table_args__ = (
        UniqueConstraint("exam_session_id", "room_id", name="uq_exam_room"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    exam_session_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("exam_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    room_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False, index=True
    )
    allocated_student_count: Mapped[int] = mapped_column(Integer, nullable=False)

    exam_session: Mapped["ExamSession"] = relationship("ExamSession", back_populates="room_allocations")
    room: Mapped["Room"] = relationship("Room")


class ExamSeatingAssignment(Base):
    """
    Modül 3 — 1-Boş-Koltuk Kuralına göre her öğrencinin sınav salonundaki
    2 boyutlu (seat_row, seat_col) koltuk koordinatı.
    Yan yana iki öğrenci arasında en az 1 boş koltuk bulunur (|col_j - col_i| >= 2).
    """

    __tablename__ = "exam_seating_assignments"
    __table_args__ = (
        UniqueConstraint("exam_session_id", "student_id", name="uq_exam_student_seat"),
        UniqueConstraint("exam_session_id", "room_id", "seat_row", "seat_col", name="uq_exam_room_coord"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    exam_session_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("exam_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    room_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False, index=True
    )
    student_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True
    )
    seat_row: Mapped[int] = mapped_column(Integer, nullable=False)
    seat_col: Mapped[int] = mapped_column(Integer, nullable=False)

    exam_session: Mapped["ExamSession"] = relationship("ExamSession", back_populates="seating_assignments")
    room: Mapped["Room"] = relationship("Room")
    student: Mapped["Student"] = relationship("Student")


class ProctorAssignment(Base):
    """
    Modül 3 — Araştırma görevlilerinin sınav salonlarına adil (Minimax) gözetmenlik ataması.
    """

    __tablename__ = "proctor_assignments"
    __table_args__ = (
        UniqueConstraint("exam_session_id", "room_id", "ta_id", name="uq_exam_room_ta"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    exam_session_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("exam_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    room_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False, index=True
    )
    ta_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("teaching_assistants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    assigned_load: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)

    exam_session: Mapped["ExamSession"] = relationship("ExamSession", back_populates="proctor_assignments")
    room: Mapped["Room"] = relationship("Room")
    ta: Mapped["TeachingAssistant"] = relationship("TeachingAssistant")
