"""
Academic Path & Schedule Optimizer (APSO) — FastAPI Ana Uygulama Giriş Noktası.

Adım 1 kapsamında:
- Veritabanı tablolarının (Single Source of Truth) oluşturulması,
- ATÜ Yazılım Mühendisliği 8 dönemlik müfredat, amfi/lab, öğretim elemanı ve
  KVKK uyumlu anonim öğrenci veri setinin otomatik yüklenmesi (seed),
- Temel veri doğrulama ve envanter sorgulama REST API uç noktaları sunulmaktadır.
"""

import base64
import logging
from contextlib import asynccontextmanager
from pydantic import BaseModel, Field
from fastapi import Depends, FastAPI, HTTPException, Query, Response, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from app.config import settings
from app.database import Base, SessionLocal, engine, get_db
from app.engines.dag_engine import CurriculumCycleError, CurriculumGraphEngine
from app.engines.exam_proctor_csp import ExamProctorAllocationEngine
from app.engines.weekly_csp import WeeklyCourseSchedulingEngine
from app.services.export_service import ExportService
from app.services.import_service import ExcelImportService
from app.models.academic import (
    Course,
    CoursePrerequisite,
    Enrollment,
    Instructor,
    InstructorAvailability,
    Room,
    Student,
    TAUnavailability,
    TeachingAssistant,
    WeeklyScheduleAssignment,
)
from app.schemas.academic import (
    CourseConstraintUpdateRequest,
    CourseRead,
    CurriculumGraphAnalysisResponse,
    ExamScheduleGenerateRequest,
    ExamScheduleOptimizationResponse,
    ExcelImportResultResponse,
    FailureSimulationRequest,
    FailureSimulationResponse,
    InstructorAvailabilitySlotSchema,
    InstructorAvailabilityUpdateRequest,
    InstructorRead,
    NonConflictMatrixResponse,
    PrerequisiteCreateRequest,
    PrerequisiteEdgeRead,
    RoomCapacityUpdateRequest,
    RoomRead,
    RoomSeatingGridResponse,
    SystemDatasetSummary,
    TAUnavailabilityCreateRequest,
    TAUnavailabilityRead,
    TeachingAssistantRead,
    WeeklyScheduleGenerateRequest,
    WeeklyScheduleOptimizationResponse,
    WeeklySlotAssignmentRead,
    WeeklySlotMoveRequest,
    WeeklySlotMoveResponse,
)
from app.seed.atu_software_eng_seed import seed_atu_dataset

logger = logging.getLogger("apso")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Uygulama başlangıcında şemayı hazırlar ve gerekirse ATÜ veri setini yükler."""
    Base.metadata.create_all(bind=engine)
    if settings.auto_seed_on_startup:
        with SessionLocal() as db:
            counts = seed_atu_dataset(db)
            logger.info("ATÜ Yazılım Mühendisliği veri seti hazır: %s", counts)
    yield


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=(
        "ATÜ Yazılım Mühendisliği Bölümü için Müfredat DAG Analizi (Modül 1), "
        "Haftalık Ders Programı CP-SAT Çözücüsü (Modül 2) ve Sınav / 1-Boş-Koltuk / "
        "Adil Gözetmen Dağıtım Sistemi (Modül 3)."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/v1/health", tags=["System"])
def health_check():
    """Sistemin ayakta olduğunu doğrulayan sağlık kontrolü uç noktası."""
    return {
        "status": "ok",
        "service": settings.app_name,
        "version": settings.app_version,
    }


@app.get("/api/v1/dataset/summary", response_model=SystemDatasetSummary, tags=["System"])
def get_dataset_summary(db: Session = Depends(get_db)):
    """Veritabanındaki yüklü ATÜ Yazılım Mühendisliği veri setinin özet istatistiklerini döndürür."""
    total_courses = db.query(Course).count()
    total_prereqs = db.query(CoursePrerequisite).count()
    total_instructors = db.query(Instructor).count()
    total_rooms = db.query(Room).count()
    total_lecture_halls = db.query(Room).filter(Room.room_type == "LECTURE").count()
    total_lab_rooms = db.query(Room).filter(Room.room_type == "LAB").count()
    total_students = db.query(Student).count()
    regular_students = db.query(Student).filter(Student.is_irregular.is_(False)).count()
    irregular_students = db.query(Student).filter(Student.is_irregular.is_(True)).count()
    total_enrollments = db.query(Enrollment).count()
    total_tas = db.query(TeachingAssistant).count()

    return SystemDatasetSummary(
        app_name=settings.app_name,
        version=settings.app_version,
        total_courses=total_courses,
        total_prerequisite_edges=total_prereqs,
        total_instructors=total_instructors,
        total_rooms=total_rooms,
        total_lecture_halls=total_lecture_halls,
        total_lab_rooms=total_lab_rooms,
        total_students=total_students,
        regular_students=regular_students,
        irregular_students=irregular_students,
        total_enrollments=total_enrollments,
        total_teaching_assistants=total_tas,
    )


@app.get("/api/v1/courses", response_model=list[CourseRead], tags=["Academic Catalog"])
def list_courses(
    semester: int | None = Query(default=None, ge=1, le=8, description="Döneme göre filtrele (1..8)"),
    db: Session = Depends(get_db),
):
    """Müfredattaki tüm dersleri (veya belirli bir dönemin derslerini) listeler."""
    query = db.query(Course)
    if semester is not None:
        query = query.filter(Course.semester == semester)
    return query.order_by(Course.semester.asc(), Course.code.asc()).all()


@app.get("/api/v1/prerequisites", response_model=list[PrerequisiteEdgeRead], tags=["Academic Catalog"])
def list_prerequisites(db: Session = Depends(get_db)):
    """Müfredattaki tüm önkoşul ve yan-koşul kenarlarını (DAG edges) listeler."""
    edges = db.query(CoursePrerequisite).all()
    course_code_by_id = {c.id: c.code for c in db.query(Course).all()}
    return [
        PrerequisiteEdgeRead(
            id=e.id,
            prerequisite_course_id=e.prerequisite_course_id,
            target_course_id=e.target_course_id,
            prerequisite_code=course_code_by_id[e.prerequisite_course_id],
            target_code=course_code_by_id[e.target_course_id],
            is_corequisite=e.is_corequisite,
        )
        for e in edges
    ]


@app.get("/api/v1/rooms", response_model=list[RoomRead], tags=["Academic Catalog"])
def list_rooms(db: Session = Depends(get_db)):
    """Tüm amfi ve laboratuvarları normal kapasiteleri ve 1-boş-koltuk sınav kapasiteleriyle listeler."""
    rooms = db.query(Room).order_by(Room.code.asc()).all()
    return [
        RoomRead(
            id=r.id,
            code=r.code,
            name=r.name,
            room_type=r.room_type,
            normal_capacity=r.normal_capacity,
            seat_rows=r.seat_rows,
            seat_cols=r.seat_cols,
            effective_exam_capacity=r.effective_exam_capacity,
        )
        for r in rooms
    ]


@app.get("/api/v1/instructors", response_model=list[InstructorRead], tags=["Academic Catalog"])
def list_instructors(db: Session = Depends(get_db)):
    """Bölüm öğretim elemanlarını listeler."""
    return db.query(Instructor).order_by(Instructor.code.asc()).all()


@app.get("/api/v1/teaching-assistants", response_model=list[TeachingAssistantRead], tags=["Academic Catalog"])
def list_teaching_assistants(db: Session = Depends(get_db)):
    """Sınav gözetmeni araştırma görevlilerini listeler."""
    return db.query(TeachingAssistant).order_by(TeachingAssistant.code.asc()).all()


# ==============================================================================
# MODÜL 1 — Curriculum Graph Engine (NetworkX & DAG) REST API Uç Noktaları
# ==============================================================================

@app.get(
    "/api/v1/curriculum/graph",
    response_model=CurriculumGraphAnalysisResponse,
    tags=["Module 1: Curriculum DAG Engine"],
)
def analyze_curriculum_dag(db: Session = Depends(get_db)):
    """
    Müfredatı Yönlü Çevrimsiz Graf (DAG) olarak analiz eder; her dersin Blocking Factor,
    Critical Path (en uzun önkoşul zinciri) ve topolojik sıralamasını döndürür.
    """
    dag_engine = CurriculumGraphEngine(db)
    try:
        return dag_engine.analyze_curriculum()
    except CurriculumCycleError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"message": exc.message, "cycle_path": exc.cycle_path},
        ) from exc


@app.post(
    "/api/v1/prerequisites",
    response_model=PrerequisiteEdgeRead,
    status_code=status.HTTP_201_CREATED,
    tags=["Module 1: Curriculum DAG Engine"],
)
def create_prerequisite_edge(
    payload: PrerequisiteCreateRequest,
    db: Session = Depends(get_db),
):
    """
    Yeni bir önkoşul veya yan-koşul kenarı ekler.
    AGENTS.md Kuralı: Döngüsel bağımlılık (A -> B -> A) veya kronolojik yarıyıl
    ihlali tespit edilirse işlemi HTTP 422 ile reddeder.
    """
    dag_engine = CurriculumGraphEngine(db)
    try:
        return dag_engine.add_prerequisite_with_cycle_check(
            prerequisite_code=payload.prerequisite_code,
            target_code=payload.target_code,
            is_corequisite=payload.is_corequisite,
        )
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"message": str(exc)},
        ) from exc
    except CurriculumCycleError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"message": exc.message, "cycle_path": exc.cycle_path},
        ) from exc


@app.post(
    "/api/v1/curriculum/simulate-failure",
    response_model=FailureSimulationResponse,
    tags=["Module 1: Curriculum DAG Engine"],
)
def simulate_course_failure(
    payload: FailureSimulationRequest,
    db: Session = Depends(get_db),
):
    """
    Öğrenci ve akademik danışman için ders kalma simülasyonu (Critical Path Analysis).
    Kalan dersin kilitlediği tüm alt/üst dönem derslerini (transitive closure) ve
    dönemlik AKTS üst sınırlarını (30 / 40 AKTS) hesaba katarak mezuniyet gecikmesini hesaplar.
    """
    dag_engine = CurriculumGraphEngine(db)
    try:
        return dag_engine.simulate_course_failure(payload)
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"message": str(exc)},
        ) from exc


@app.get(
    "/api/v1/curriculum/non-conflict-matrix",
    response_model=NonConflictMatrixResponse,
    tags=["Module 1: Curriculum DAG Engine"],
)
def get_non_conflict_matrix(
    academic_term: str = Query(default="2026-FALL", description="Akademik dönem (Örn: 2026-FALL)"),
    db: Session = Depends(get_db),
):
    """
    Modül 1'in ürettiği ve Modül 2'nin (Weekly Course Scheduling Engine) doğrudan
    zorunlu girdisi olan Çakışmazlık Matrisini (C_DAG) döndürür.
    """
    dag_engine = CurriculumGraphEngine(db)
    return dag_engine.generate_non_conflict_matrix(academic_term=academic_term)


# ==============================================================================
# MODÜL 2 — Weekly Course Scheduling Engine (Google OR-Tools CP-SAT) Uç Noktaları
# ==============================================================================

@app.post(
    "/api/v1/schedule/weekly/generate",
    response_model=WeeklyScheduleOptimizationResponse,
    tags=["Module 2: Weekly Course Scheduling CSP"],
)
def generate_weekly_schedule(
    payload: WeeklyScheduleGenerateRequest,
    db: Session = Depends(get_db),
):
    """
    Modül 1'den C_DAG çakışmazlık matrisini alır ve Google OR-Tools CP-SAT ile
    haftalık ders programını tüm kesin (hard) ve yumuşak (soft) kısıtlar altında çözer.
    Çözülemezlik (INFEASIBLE) durumunda Türkçe Unsat Core darboğaz raporu döndürür.
    """
    weekly_engine = WeeklyCourseSchedulingEngine(db)
    return weekly_engine.generate_weekly_schedule(payload)


@app.get(
    "/api/v1/schedule/weekly",
    response_model=list[WeeklySlotAssignmentRead],
    tags=["Module 2: Weekly Course Scheduling CSP"],
)
def list_weekly_schedule(
    academic_term: str = Query(default="2026-FALL", description="Akademik dönem"),
    semester: int | None = Query(default=None, ge=1, le=8, description="Döneme göre filtrele"),
    db: Session = Depends(get_db),
):
    """Kaydedilmiş haftalık ders programı atamalarını listeler."""
    rows = (
        db.query(WeeklyScheduleAssignment)
        .filter(WeeklyScheduleAssignment.academic_term == academic_term)
        .order_by(
            WeeklyScheduleAssignment.day_of_week.asc(),
            WeeklyScheduleAssignment.slot_index.asc(),
        )
        .all()
    )
    result: list[WeeklySlotAssignmentRead] = []
    for a in rows:
        if semester is not None and a.course.semester != semester:
            continue
        result.append(
            WeeklySlotAssignmentRead(
                course_id=a.course.id,
                course_code=a.course.code,
                course_name=a.course.name,
                semester=a.course.semester,
                room_id=a.room.id,
                room_code=a.room.code,
                room_type=a.room.room_type,
                room_capacity=a.room.normal_capacity,
                enrolled_count=a.course.enrolled_count,
                instructor_id=a.instructor_id,
                instructor_name=a.instructor.full_name if a.instructor else "Unassigned",
                day_of_week=a.day_of_week,
                slot_index=a.slot_index,
                session_type=a.session_type,
            )
        )
    return result


@app.post(
    "/api/v1/schedule/weekly/move",
    response_model=WeeklySlotMoveResponse,
    tags=["Module 2: Weekly Course Scheduling CSP"],
)
def move_and_validate_weekly_slot(
    payload: WeeklySlotMoveRequest,
    db: Session = Depends(get_db),
):
    """
    Stretch Goal 1 — Manuel What-If Ders Taşıma ve Anlık Çakışma Doğrulayıcısı:
    Bir ders oturumunu hedef gün, saat ve amfiye taşırken oda kapasitesi, LAB tipi,
    hoca müsaitliği ve Modül 1 C_DAG çakışmazlık kurallarını anında denetler.
    """
    weekly_engine = WeeklyCourseSchedulingEngine(db)
    try:
        return weekly_engine.validate_and_move_slot(payload)
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"message": str(exc)},
        ) from exc


# ==============================================================================
# MODÜL 3 — Exam, 1-Empty-Seat Grid & Equitable Proctor Allocation CSP Uç Noktaları
# ==============================================================================

@app.post(
    "/api/v1/schedule/exams/generate",
    response_model=ExamScheduleOptimizationResponse,
    tags=["Module 3: Exam, Seating & Proctor CSP"],
)
def generate_exam_and_proctor_schedule(
    payload: ExamScheduleGenerateRequest,
    db: Session = Depends(get_db),
):
    """
    Google OR-Tools CP-SAT ile öğrenci sınav çakışmalarını sıfırlayan,
    1-boş-koltuk (Cap_exam = Rows * ceil(Cols/2)) kuralına göre kalabalık sınavları
    birden fazla amfiye bölen ve Arş. Gör. gözetmen yükünü Minimax kriteriyle
    dağıtan sınav/oturma/gözetmen planını üretir.
    """
    exam_engine = ExamProctorAllocationEngine(db)
    return exam_engine.generate_exam_and_proctor_schedule(payload)


@app.get(
    "/api/v1/schedule/exams/{exam_session_id}/seating",
    response_model=RoomSeatingGridResponse,
    tags=["Module 3: Exam, Seating & Proctor CSP"],
)
def get_exam_seating_plan(
    exam_session_id: int,
    db: Session = Depends(get_db),
):
    """
    Belirli bir sınav oturumunun salonlarındaki 2B (satır, sütun) 1-boş-koltuk
    öğrenci oturma matrisini döndürür.
    """
    exam_engine = ExamProctorAllocationEngine(db)
    try:
        return exam_engine.get_exam_seating_grid(exam_session_id=exam_session_id)
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"message": str(exc)},
        ) from exc


# ==============================================================================
# EXCEL (.xlsx) VE PDF (.pdf) RAPOR DIŞA AKTARIM UÇ NOKTALARI
# ==============================================================================

@app.get(
    "/api/v1/export/weekly.xlsx",
    tags=["Export & Reports (Excel / PDF)"],
)
def download_weekly_schedule_excel(
    academic_term: str = Query(default="2026-FALL", description="Akademik dönem"),
    db: Session = Depends(get_db),
):
    """Haftalık ders programını resmi Excel (.xlsx) çalışma kitabı olarak indirir."""
    exporter = ExportService(db)
    xlsx_bytes = exporter.export_weekly_schedule_xlsx(academic_term=academic_term)
    filename = f"APSO_Weekly_Schedule_{academic_term}.xlsx"
    return Response(
        content=xlsx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get(
    "/api/v1/export/exams.pdf",
    tags=["Export & Reports (Excel / PDF)"],
)
def download_exam_and_seating_pdf(
    academic_term: str = Query(default="2026-FALL", description="Akademik dönem"),
    exam_type: str = Query(default="FINAL", pattern="^(MIDTERM|FINAL)$"),
    db: Session = Depends(get_db),
):
    """
    Sınav takvimini, 1-boş-koltuk salon bölünmesini, Minimax Arş. Gör. gözetmen
    listesini ve KVKK uyumlu kapı oturma planını resmi PDF (.pdf) olarak indirir.
    """
    exporter = ExportService(db)
    pdf_bytes = exporter.export_exam_and_seating_pdf(
        academic_term=academic_term, exam_type=exam_type
    )
    filename = f"APSO_Exam_Seating_Proctors_{academic_term}_{exam_type}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ==============================================================================
# EXCEL (.xlsx) VERİ İÇE AKTARMA (IMPORT & PYDANTIC V2 DOĞRULAMA) UÇ NOKTALARI
# ==============================================================================

class ExcelBase64UploadRequest(BaseModel):
    """Yüklenen Excel (.xlsx) dosyasının Base64 kodlu JSON taşıyıcısı."""

    filename: str = Field(default="department_data.xlsx", min_length=3, max_length=120)
    content_base64: str = Field(..., min_length=8, description="Base64 kodlanmış .xlsx dosya içeriği")


@app.get(
    "/api/v1/import/template.xlsx",
    tags=["Import & Validation (Excel)"],
)
def download_import_template_excel(db: Session = Depends(get_db)):
    """Bölüm ders ve amfi/laboratuvar yükleme şablonunu (.xlsx) indirir."""
    importer = ExcelImportService(db)
    tpl_bytes = importer.generate_import_template_xlsx()
    return Response(
        content=tpl_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="APSO_Import_Template.xlsx"'},
    )


@app.post(
    "/api/v1/import/excel",
    response_model=ExcelImportResultResponse,
    tags=["Import & Validation (Excel)"],
)
def import_excel_dataset(
    payload: ExcelBase64UploadRequest,
    db: Session = Depends(get_db),
):
    """
    Base64 olarak gönderilen Excel (.xlsx) dosyasındaki Courses ve Rooms sayfalarını
    okur, her satırı Pydantic v2 şema doğrulamasından geçirir ve hatalı satırları
    numarasıyla birlikte Türkçe raporlar.
    """
    try:
        raw_bytes = base64.b64decode(payload.content_base64)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"message": f"Base64 çözme hatası: {exc}"},
        ) from exc

    importer = ExcelImportService(db)
    try:
        return importer.import_excel_workbook(raw_bytes, filename=payload.filename)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"message": str(exc)},
        ) from exc


# ==============================================================================
# GELİŞTİRME 1 — İnteraktif Kaynak & Hoca / Arş. Gör. Müsaitlik Yönetimi Uç Noktaları
# ==============================================================================

@app.get(
    "/api/v1/instructors/{instructor_id}/availabilities",
    response_model=list[InstructorAvailabilitySlotSchema],
    tags=["Resource & Availability Editor"],
)
def get_instructor_availabilities(
    instructor_id: int,
    db: Session = Depends(get_db),
):
    """Belirli bir öğretim elemanının 5x8 haftalık müsaitlik ve tercih cezası matrisini döndürür."""
    inst = db.query(Instructor).filter(Instructor.id == instructor_id).first()
    if not inst:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"message": f"Öğretim elemanı bulunamadı: ID={instructor_id}"},
        )

    rows = (
        db.query(InstructorAvailability)
        .filter(InstructorAvailability.instructor_id == instructor_id)
        .order_by(InstructorAvailability.day_of_week.asc(), InstructorAvailability.slot_index.asc())
        .all()
    )
    return [
        InstructorAvailabilitySlotSchema(
            day_of_week=r.day_of_week,
            slot_index=r.slot_index,
            is_available=r.is_available,
            preference_penalty=r.preference_penalty,
        )
        for r in rows
    ]


@app.put(
    "/api/v1/instructors/{instructor_id}/availabilities",
    response_model=list[InstructorAvailabilitySlotSchema],
    tags=["Resource & Availability Editor"],
)
def update_instructor_availabilities(
    instructor_id: int,
    payload: InstructorAvailabilityUpdateRequest,
    db: Session = Depends(get_db),
):
    """
    Öğretim elemanının haftalık 5x8 müsaitlik ve tercih hücrelerini günceller.
    Modül 2 CP-SAT çözücüsü bir sonraki çalıştırmada doğrudan bu güncel matrisi kullanır.
    """
    inst = db.query(Instructor).filter(Instructor.id == instructor_id).first()
    if not inst:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"message": f"Öğretim elemanı bulunamadı: ID={instructor_id}"},
        )

    existing_map = {
        (r.day_of_week, r.slot_index): r
        for r in db.query(InstructorAvailability)
        .filter(InstructorAvailability.instructor_id == instructor_id)
        .all()
    }

    for slot_item in payload.slots:
        key = (slot_item.day_of_week, slot_item.slot_index)
        if key in existing_map:
            existing_map[key].is_available = slot_item.is_available
            existing_map[key].preference_penalty = slot_item.preference_penalty
        else:
            db.add(
                InstructorAvailability(
                    instructor_id=instructor_id,
                    day_of_week=slot_item.day_of_week,
                    slot_index=slot_item.slot_index,
                    is_available=slot_item.is_available,
                    preference_penalty=slot_item.preference_penalty,
                )
            )

    db.commit()
    return get_instructor_availabilities(instructor_id=instructor_id, db=db)


@app.put(
    "/api/v1/courses/{course_id}/constraints",
    response_model=CourseRead,
    tags=["Resource & Availability Editor"],
)
def update_course_constraints(
    course_id: int,
    payload: CourseConstraintUpdateRequest,
    db: Session = Depends(get_db),
):
    """Bir dersin öğrenci sayısını, LAB odası zorunluluğunu, haftalık saatini veya hocasını günceller."""
    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"message": f"Ders bulunamadı: ID={course_id}"},
        )

    course.enrolled_count = payload.enrolled_count
    course.requires_lab_room = payload.requires_lab_room
    course.theory_hours = payload.theory_hours
    course.lab_hours = payload.lab_hours
    if payload.instructor_id is not None:
        course.instructor_id = payload.instructor_id

    db.commit()
    db.refresh(course)
    return course


@app.put(
    "/api/v1/rooms/{room_id}/capacity",
    response_model=RoomRead,
    tags=["Resource & Availability Editor"],
)
def update_room_capacity_and_grid(
    room_id: int,
    payload: RoomCapacityUpdateRequest,
    db: Session = Depends(get_db),
):
    """
    Bir amfi veya laboratuvarın normal kapasitesini ve 2B (satır x sütun) koltuk
    boyutlarını günceller; 1-boş-koltuk sınav kapasitesi otomatik yeniden hesaplanır.
    """
    room = db.query(Room).filter(Room.id == room_id).first()
    if not room:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"message": f"Derslik/Amfi bulunamadı: ID={room_id}"},
        )

    room.room_type = payload.room_type
    room.normal_capacity = payload.normal_capacity
    room.seat_rows = payload.seat_rows
    room.seat_cols = payload.seat_cols
    db.commit()
    db.refresh(room)

    return RoomRead(
        id=room.id,
        code=room.code,
        name=room.name,
        room_type=room.room_type,
        normal_capacity=room.normal_capacity,
        seat_rows=room.seat_rows,
        seat_cols=room.seat_cols,
        effective_exam_capacity=room.effective_exam_capacity,
    )


@app.get(
    "/api/v1/teaching-assistants/unavailabilities",
    response_model=list[TAUnavailabilityRead],
    tags=["Resource & Availability Editor"],
)
def list_ta_unavailabilities(db: Session = Depends(get_db)):
    """Araştırma görevlilerinin sınav haftası lisansüstü ders / izin kısıtlarını listeler."""
    rows = db.query(TAUnavailability).order_by(TAUnavailability.ta_id.asc(), TAUnavailability.exam_day.asc()).all()
    ta_map = {t.id: t for t in db.query(TeachingAssistant).all()}
    return [
        TAUnavailabilityRead(
            id=r.id,
            ta_id=r.ta_id,
            ta_code=ta_map[r.ta_id].code if r.ta_id in ta_map else f"TA-{r.ta_id}",
            ta_name=ta_map[r.ta_id].full_name if r.ta_id in ta_map else "Unknown TA",
            exam_day=r.exam_day,
            session_index=r.session_index,
            reason=r.reason,
        )
        for r in rows
    ]


@app.post(
    "/api/v1/teaching-assistants/{ta_id}/unavailabilities",
    response_model=TAUnavailabilityRead,
    status_code=status.HTTP_201_CREATED,
    tags=["Resource & Availability Editor"],
)
def add_ta_unavailability(
    ta_id: int,
    payload: TAUnavailabilityCreateRequest,
    db: Session = Depends(get_db),
):
    """Araştırma görevlisine yeni bir sınav günü/oturumu kısıtı (lisansüstü ders saati) ekler."""
    ta = db.query(TeachingAssistant).filter(TeachingAssistant.id == ta_id).first()
    if not ta:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"message": f"Araştırma görevlisi bulunamadı: ID={ta_id}"},
        )

    existing = (
        db.query(TAUnavailability)
        .filter(
            TAUnavailability.ta_id == ta_id,
            TAUnavailability.exam_day == payload.exam_day,
            TAUnavailability.session_index == payload.session_index,
        )
        .first()
    )
    if existing:
        existing.reason = payload.reason
        db.commit()
        db.refresh(existing)
        rec = existing
    else:
        rec = TAUnavailability(
            ta_id=ta_id,
            exam_day=payload.exam_day,
            session_index=payload.session_index,
            reason=payload.reason,
        )
        db.add(rec)
        db.commit()
        db.refresh(rec)

    return TAUnavailabilityRead(
        id=rec.id,
        ta_id=ta.id,
        ta_code=ta.code,
        ta_name=ta.full_name,
        exam_day=rec.exam_day,
        session_index=rec.session_index,
        reason=rec.reason,
    )


@app.delete(
    "/api/v1/teaching-assistants/unavailabilities/{unavailability_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["Resource & Availability Editor"],
)
def delete_ta_unavailability(
    unavailability_id: int,
    db: Session = Depends(get_db),
):
    """Araştırma görevlisinin sınav oturumu kısıtını kaldırır."""
    rec = db.query(TAUnavailability).filter(TAUnavailability.id == unavailability_id).first()
    if not rec:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"message": f"Kısıt kaydı bulunamadı: ID={unavailability_id}"},
        )
    db.delete(rec)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)





