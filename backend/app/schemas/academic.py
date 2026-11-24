"""
Pydantic v2 İstek ve Yanıt Doğrulama Şemaları (Schemas).
Tüm dış girdiler veritabanına veya CP-SAT çözücüsüne ulaşmadan önce bu şemalardan geçer.
"""

from pydantic import BaseModel, ConfigDict, Field


class InstructorRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    full_name: str
    title: str
    department: str
    max_weekly_hours: int


class CourseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    semester: int = Field(..., ge=1, le=8)
    ects: int = Field(..., gt=0, le=30)
    theory_hours: int = Field(..., ge=0, le=10)
    lab_hours: int = Field(..., ge=0, le=10)
    is_mandatory: bool
    requires_lab_room: bool
    enrolled_count: int = Field(..., ge=0)
    instructor_id: int | None = None


class PrerequisiteEdgeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    prerequisite_course_id: int
    target_course_id: int
    prerequisite_code: str
    target_code: str
    is_corequisite: bool


class PrerequisiteCreateRequest(BaseModel):
    """Yeni bir önkoşul/yan-koşul eklemek için doğrulama şeması (Modül 1 DAG çevrim kontrolüne girer)."""

    prerequisite_code: str = Field(..., min_length=3, max_length=24, description="Önkoşul ders kodu (Örn: SE101)")
    target_code: str = Field(..., min_length=3, max_length=24, description="Hedef ders kodu (Örn: SE102)")
    is_corequisite: bool = Field(default=False, description="Aynı dönemde birlikte alınabilen yan-koşul mu?")


class RoomRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    room_type: str
    normal_capacity: int
    seat_rows: int
    seat_cols: int
    effective_exam_capacity: int


class TeachingAssistantRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    full_name: str
    current_workload_score: float


class SystemDatasetSummary(BaseModel):
    """Sistemdeki yüklü ATÜ Yazılım Mühendisliği veri setinin özet metrikleri."""

    app_name: str
    version: str
    total_courses: int
    total_prerequisite_edges: int
    total_instructors: int
    total_rooms: int
    total_lecture_halls: int
    total_lab_rooms: int
    total_students: int
    regular_students: int
    irregular_students: int
    total_enrollments: int
    total_teaching_assistants: int


# ==============================================================================
# MODÜL 1 (Curriculum Graph Engine - DAG & Critical Path) Şemaları
# ==============================================================================

class CourseGraphNodeMetric(BaseModel):
    """
    Müfredat DAG üzerindeki bir ders düğümünün topolojik ve kritik yol metrikleri.
    - blocking_factor: Bu dersin doğrudan veya dolaylı kilitlediği toplam üst ders sayısı |Reach(u)|.
    - critical_path_length: Bu dersten başlayarak mezuniyete kadar uzanan en uzun önkoşul zinciri CP(u).
    """

    course_id: int
    code: str
    name: str
    semester: int
    ects: int
    is_mandatory: bool
    direct_prerequisites: list[str]
    direct_dependents: list[str]
    transitive_dependents: list[str]
    blocking_factor: int
    critical_path_length: int
    critical_path_chain: list[str]


class CurriculumGraphAnalysisResponse(BaseModel):
    """Modül 1 tam müfredat DAG analizi yanıt şeması."""

    is_valid_dag: bool
    total_nodes: int
    total_edges: int
    longest_critical_path_length: int
    global_critical_path: list[str]
    top_bottleneck_courses: list[str]
    topological_order: list[str]
    nodes: list[CourseGraphNodeMetric]


class FailureSimulationRequest(BaseModel):
    """
    Öğrenci veya akademik danışman için ders kalma (course failure) simülasyon isteği.
    - current_semester: Öğrencinin şu an tamamladığı / bulunduğu dönem (1..8).
    - failed_course_codes: Öğrencinin kaldığı derslerin kod listesi (Örn: ["CSE102"]).
    - passed_course_codes: Opsiyonel. Verilmezse current_semester'a kadar olan ve
      failed_course_codes içinde yer almayan dersler başarılmış kabul edilir.
    - use_recovery_ects_cap: True ise kurtarma dönemlerinde 40 AKTS üst sınırı, False ise 30 AKTS uygulanır.
    """

    current_semester: int = Field(default=2, ge=1, le=8)
    failed_course_codes: list[str] = Field(..., min_length=1, description="Kaldığı ders kodları (Örn: ['CSE102'])")
    passed_course_codes: list[str] | None = Field(default=None)
    use_recovery_ects_cap: bool = Field(default=True, description="Kurtarma dönemlerinde 40 AKTS üst sınırı uygulansın mı?")


class SimulatedSemesterPlan(BaseModel):
    """Mezuniyet simülasyonundaki her bir gelecek dönemin ders ve AKTS yükü."""

    simulated_term_index: int
    semester_type: str  # FALL (Güz) | SPRING (Bahar)
    planned_courses: list[str]
    retake_courses: list[str]
    blocked_courses_in_this_term: list[str]
    total_ects: int
    ects_cap_applied: int


class FailureSimulationResponse(BaseModel):
    """
    Modül 1 — Ders kalma simülasyonu ve Critical Path analizi çıktısı.
    Kalan derslerin kilitlediği tüm alt/üst dönem derslerini (transitive closure)
    ve dönemlik AKTS (30 / 40 AKTS) sınırlarını hesaba katarak mezuniyet gecikmesini raporlar.
    """

    current_semester: int
    failed_course_codes: list[str]
    directly_locked_courses: list[str]
    transitively_locked_courses: list[str]
    critical_prerequisite_chains: dict[str, list[str]]
    nominal_remaining_semesters: int
    simulated_remaining_semesters: int
    estimated_graduation_delay_semesters: int
    applied_ects_cap: int
    advisor_recommendations: list[str]
    semester_by_semester_plan: list[SimulatedSemesterPlan]


class NonConflictPairItem(BaseModel):
    """Modül 1'den Modül 2'ye aktarılan C_DAG çakışmazlık matrisi ders çifti."""

    course_a_code: str
    course_b_code: str
    course_a_id: int
    course_b_id: int
    reason: str  # SAME_SEMESTER_MANDATORY | COREQUISITE | IRREGULAR_RETAKE_COHORT
    shared_irregular_students: int = 0


class NonConflictMatrixResponse(BaseModel):
    """Modül 2'nin doğrudan zorunlu girdisi olan C_DAG çakışmazlık matrisi."""

    academic_term: str
    total_non_conflict_pairs: int
    same_semester_pairs_count: int
    corequisite_pairs_count: int
    irregular_retake_pairs_count: int
    pairs: list[NonConflictPairItem]


# ==============================================================================
# MODÜL 2 (Weekly Course Scheduling Engine — Google OR-Tools CP-SAT) Şemaları
# ==============================================================================

class WeeklyScheduleGenerateRequest(BaseModel):
    """Haftalık ders programı optimizasyon isteği."""

    academic_term: str = Field(default="2026-FALL", description="Akademik dönem (Örn: 2026-FALL veya 2026-SPRING)")
    semester_parity: str = Field(
        default="FALL",
        pattern="^(FALL|SPRING|ALL)$",
        description="FALL (1,3,5,7. yarıyıl dersleri), SPRING (2,4,6,8. yarıyıl) veya ALL",
    )
    max_time_seconds: int = Field(default=20, ge=2, le=120, description="CP-SAT çözücü zaman aşımı sınırı (sn)")
    idle_gap_weight: int = Field(default=10, ge=0, le=100, description="Öğrenci günlük boş saat (idle gap) ceza ağırlığı")
    instructor_preference_weight: int = Field(default=5, ge=0, le=100, description="Hoca saat tercihi ceza ağırlığı")


class WeeklySlotAssignmentRead(BaseModel):
    """Haftalık ders programındaki tek bir ders-amfi-gün-saat ataması."""

    course_id: int
    course_code: str
    course_name: str
    semester: int
    room_id: int
    room_code: str
    room_type: str
    room_capacity: int
    enrolled_count: int
    instructor_id: int | None
    instructor_name: str
    day_of_week: int
    slot_index: int
    session_type: str


class WeeklyScheduleOptimizationResponse(BaseModel):
    """Modül 2 haftalık ders programı CP-SAT optimizasyon sonucu ve çözülemezlik (Unsat Core) tanı raporu."""

    academic_term: str
    solver_status: str  # OPTIMAL | FEASIBLE | INFEASIBLE
    solve_time_seconds: float
    total_courses_scheduled: int
    total_slot_assignments: int
    hard_constraints_satisfied: bool
    c_dag_pairs_enforced: int
    total_student_idle_gap_hours: int
    total_instructor_preference_penalty: int
    objective_value: float
    unsat_diagnostics_tr: list[str]
    assignments: list[WeeklySlotAssignmentRead]


# ==============================================================================
# MODÜL 3 (Exam, 1-Empty-Seat Grid & Equitable Proctor Allocation CSP) Şemaları
# ==============================================================================

class ExamScheduleGenerateRequest(BaseModel):
    """Vize / Final sınav takvimi, 1-boş-koltuk oturma planı ve adil gözetmen dağıtımı isteği."""

    academic_term: str = Field(default="2026-FALL", description="Akademik dönem (Örn: 2026-FALL)")
    exam_type: str = Field(default="FINAL", pattern="^(MIDTERM|FINAL)$")
    semester_parity: str = Field(default="FALL", pattern="^(FALL|SPRING|ALL)$")
    exam_days_count: int = Field(default=10, ge=3, le=15, description="Toplam sınav günü sayısı (Örn: 10 gün)")
    sessions_per_day: int = Field(default=4, ge=2, le=6, description="Günlük sınav oturumu sayısı (Örn: 4 oturum)")
    max_time_seconds: int = Field(default=20, ge=2, le=120)


class ExamRoomProctorItem(BaseModel):
    """Sınavın yapıldığı bir amfi, o amfideki öğrenci sayısı ve atanan gözetmen (Arş. Gör.)."""

    room_id: int
    room_code: str
    room_normal_capacity: int
    room_effective_exam_capacity: int
    allocated_student_count: int
    proctor_ta_id: int
    proctor_ta_code: str
    proctor_ta_name: str
    duty_weight: float


class ExamSessionRead(BaseModel):
    """Tek bir dersin sınav oturumu ve bölündüğü amfi/gözetmen detayları."""

    exam_session_id: int
    course_id: int
    course_code: str
    course_name: str
    semester: int
    enrolled_count: int
    exam_day: int
    session_index: int
    is_weekend_or_evening: bool
    duty_weight: float
    rooms: list[ExamRoomProctorItem]


class ProctorWorkloadSummaryItem(BaseModel):
    """Araştırma görevlisi gözetmenlik yükü özeti (Minimax adalet analizi)."""

    ta_id: int
    ta_code: str
    ta_name: str
    assigned_exam_rooms_count: int
    total_weighted_workload: float


class ExamScheduleOptimizationResponse(BaseModel):
    """Modül 3 sınav takvimi, 1-boş-koltuk kapasite bölünmesi ve Minimax gözetmen dağıtımı sonucu."""

    academic_term: str
    exam_type: str
    solver_status: str  # OPTIMAL | FEASIBLE | INFEASIBLE
    solve_time_seconds: float
    total_exams_scheduled: int
    total_room_allocations: int
    total_seated_students: int
    zero_student_clash_verified: bool
    one_empty_seat_rule_verified: bool
    min_ta_workload: float
    max_ta_workload: float
    workload_max_min_spread: float
    unsat_diagnostics_tr: list[str]
    exam_sessions: list[ExamSessionRead]
    proctor_workloads: list[ProctorWorkloadSummaryItem]


class SeatCellItem(BaseModel):
    """Sınav oturma planındaki tek bir öğrencinin (satır, sütun) koltuk koordinatı."""

    student_id: int
    student_number: str
    student_name: str
    room_code: str
    seat_row: int
    seat_col: int


class RoomSeatingGridResponse(BaseModel):
    """Bir sınav oturumunun tüm salonlarındaki 1-boş-koltuk 2B oturma matrisi."""

    exam_session_id: int
    course_code: str
    course_name: str
    exam_day: int
    session_index: int
    total_seated_students: int
    one_empty_seat_verified: bool
    seats: list[SeatCellItem]


# ==============================================================================
# EXCEL / CSV VERİ İÇE AKTARMA (IMPORT & PYDANTIC V2 DOĞRULAMA) ŞEMALARI
# ==============================================================================

class CourseImportRowSchema(BaseModel):
    """Excel/CSV üzerinden yüklenen her bir ders satırının Pydantic v2 doğrulama şeması."""

    code: str = Field(..., min_length=3, max_length=24)
    name: str = Field(..., min_length=2, max_length=160)
    semester: int = Field(..., ge=1, le=8)
    ects: int = Field(..., gt=0, le=30)
    theory_hours: int = Field(default=3, ge=0, le=10)
    lab_hours: int = Field(default=0, ge=0, le=10)
    is_mandatory: bool = Field(default=True)
    requires_lab_room: bool = Field(default=False)
    enrolled_count: int = Field(default=40, ge=1, le=500)
    instructor_code: str | None = Field(default=None, max_length=32)


class RoomImportRowSchema(BaseModel):
    """Excel/CSV üzerinden yüklenen her bir amfi/laboratuvar satırının Pydantic v2 doğrulama şeması."""

    code: str = Field(..., min_length=2, max_length=32)
    name: str = Field(..., min_length=2, max_length=120)
    room_type: str = Field(default="LECTURE", pattern="^(LECTURE|LAB)$")
    normal_capacity: int = Field(..., gt=0, le=1000)
    seat_rows: int = Field(..., gt=0, le=100)
    seat_cols: int = Field(..., gt=0, le=100)


class ExcelImportRowError(BaseModel):
    """Excel/CSV yüklemesinde doğrulamadan geçemeyen satırın hata detayı."""

    sheet_name: str
    row_number: int
    identifier: str
    error_message_tr: str


class ExcelImportResultResponse(BaseModel):
    """Excel/CSV veri içe aktarma işleminin satır bazlı doğrulama ve kayıt özeti."""

    filename: str
    courses_created: int
    courses_updated: int
    rooms_created: int
    rooms_updated: int
    total_errors: int
    row_errors: list[ExcelImportRowError]



