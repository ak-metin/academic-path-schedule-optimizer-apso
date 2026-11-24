"""
Academic Path & Schedule Optimizer (APSO) — FastAPI Ana Uygulama Giriş Noktası.

Adım 1 kapsamında:
- Veritabanı tablolarının (Single Source of Truth) oluşturulması,
- ATÜ Yazılım Mühendisliği 8 dönemlik müfredat, amfi/lab, öğretim elemanı ve
  KVKK uyumlu anonim öğrenci veri setinin otomatik yüklenmesi (seed),
- Temel veri doğrulama ve envanter sorgulama REST API uç noktaları sunulmaktadır.
"""

import logging
from contextlib import asynccontextmanager
from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from app.config import settings
from app.database import Base, SessionLocal, engine, get_db
from app.engines.dag_engine import CurriculumCycleError, CurriculumGraphEngine
from app.engines.exam_proctor_csp import ExamProctorAllocationEngine
from app.engines.weekly_csp import WeeklyCourseSchedulingEngine
from app.models.academic import (
    Course,
    CoursePrerequisite,
    Enrollment,
    Instructor,
    Room,
    Student,
    TeachingAssistant,
    WeeklyScheduleAssignment,
)
from app.schemas.academic import (
    CourseRead,
    CurriculumGraphAnalysisResponse,
    ExamScheduleGenerateRequest,
    ExamScheduleOptimizationResponse,
    FailureSimulationRequest,
    FailureSimulationResponse,
    InstructorRead,
    NonConflictMatrixResponse,
    PrerequisiteCreateRequest,
    PrerequisiteEdgeRead,
    RoomRead,
    RoomSeatingGridResponse,
    SystemDatasetSummary,
    TeachingAssistantRead,
    WeeklyScheduleGenerateRequest,
    WeeklyScheduleOptimizationResponse,
    WeeklySlotAssignmentRead,
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


