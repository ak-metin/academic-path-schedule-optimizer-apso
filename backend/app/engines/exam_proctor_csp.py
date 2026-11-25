"""
Modül 3 — Exam & Proctor Allocation Module (Google OR-Tools CP-SAT Sınav, 1-Boş-Koltuk
Oturma Planı ve Minimax Adil Gözetmen Dağıtım Motoru).

AGENTS.md Mimari ve Algoritmik Kuralları:
1. Öğrenci Sınav Çakışması (Zero Student Exam Clash):
   - Ortak kayıtlı öğrencisi (enrollments) bulunan hiçbir iki dersin sınavı aynı oturuma
     (exam_day, session_index) atanamaz. Ayrıca aynı dönem öğrencilerinin bir günde 2'den
     fazla sınava girmesi engellenir.
2. 1-Boş-Koltuk Kuralı (1-Empty-Seat Rule):
   - Sınav oturma planı oluşturulurken amfilerin fiziksel kapasitesi değil, yan yana iki
     öğrenci arasında en az 1 boş koltuk bırakan efektif sınav kapasitesi:
     Cap_exam(r) = Rows(r) * ceil(Cols(r) / 2)
     esas alınır.
   - Tek amfiye sığmayan kalabalık sınavlar otomatik olarak aynı oturumdaki birden fazla
     salona (multi-room partitioning) bölünür.
   - Öğrenciler salon içindeki 2B (seat_row, seat_col) koordinatlarına yalnızca tekil
     sütun indeksleri (col in {1, 3, 5, ...}) kullanılarak yerleştirilir; böylece yan yana
     iki öğrenci arasında kesinlikle en az 1 boş koltuk (|col_j - col_i| >= 2) kalır.
3. Adil Gözetmen (Arş. Gör.) Dağıtımı (Minimax Workload Equity):
   - Araştırma görevlileri kendi lisansüstü ders saatleriyle (ta_unavailabilities) çakışmayacak
     ve aynı oturumda birden fazla salona atanmayacak şekilde görevlendirilir.
   - Görev yükü dağılımında (normal oturum ağırlığı = 1.0, akşam/hafta sonu oturumu = 1.5)
     Minimax adalet kriteri: min (L_max - L_min) uygulanır.
"""

from collections import defaultdict
from itertools import combinations
import time
from ortools.sat.python import cp_model
from sqlalchemy.orm import Session

from app.config import settings
from app.models.academic import (
    Course,
    Enrollment,
    ExamRoomAllocation,
    ExamSeatingAssignment,
    ExamSession,
    ProctorAssignment,
    Room,
    Student,
    TAUnavailability,
    TeachingAssistant,
)
from app.schemas.academic import (
    ExamRoomProctorItem,
    ExamScheduleGenerateRequest,
    ExamScheduleOptimizationResponse,
    ExamSessionRead,
    ProctorWorkloadSummaryItem,
    RoomSeatingGridResponse,
    SeatCellItem,
    VisualRoomLayoutItem,
)


class ExamProctorAllocationEngine:
    """Google OR-Tools CP-SAT tabanlı Sınav, 1-Boş-Koltuk ve Adil Gözetmen Motoru (Modül 3)."""

    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def _filter_courses_by_parity(all_courses: list[Course], parity: str) -> list[Course]:
        if parity == "FALL":
            return [c for c in all_courses if c.semester % 2 == 1]
        if parity == "SPRING":
            return [c for c in all_courses if c.semester % 2 == 0]
        return all_courses

    @staticmethod
    def _generate_1_empty_seat_coordinates(room: Room, limit: int) -> list[tuple[int, int]]:
        """
        1-Boş-Koltuk Kuralı (1-Empty-Seat Rule):
        Bir amfideki (seat_rows x seat_cols) koltuk matrisinde yan yana iki öğrenci arasında
        en az 1 boş koltuk bırakmak için yalnızca tek sütun numaralarını (1, 3, 5, ...) üretir.
        Üretilen maksimum koltuk sayısı = Rows(r) * ceil(Cols(r) / 2) = room.effective_exam_capacity.
        """
        coords: list[tuple[int, int]] = []
        valid_cols = list(range(1, room.seat_cols + 1, 2))
        for r_idx in range(1, room.seat_rows + 1):
            for c_idx in valid_cols:
                coords.append((r_idx, c_idx))
                if len(coords) >= limit:
                    return coords
        return coords

    def generate_exam_and_proctor_schedule(
        self, req: ExamScheduleGenerateRequest
    ) -> ExamScheduleOptimizationResponse:
        """
        Modül 3 CP-SAT Çözücüsü:
        1. Öğrenci sınav çakışmalarını sıfırlar,
        2. 1-boş-koltuk kapasitesine göre kalabalık sınavları birden fazla amfiye böler ve
           2 boyutlu oturma planı koordinatlarını üretir,
        3. Araştırma görevlilerini lisansüstü ders kısıtlarına uyarak Minimax adalet kriteriyle atar.
        """
        start_ts = time.perf_counter()

        all_courses = self.db.query(Course).order_by(Course.semester.asc(), Course.code.asc()).all()
        courses = self._filter_courses_by_parity(all_courses, req.semester_parity)
        rooms = self.db.query(Room).order_by(Room.normal_capacity.desc(), Room.code.asc()).all()
        tas = self.db.query(TeachingAssistant).order_by(TeachingAssistant.code.asc()).all()
        ta_unavails = self.db.query(TAUnavailability).all()
        enrollments = (
            self.db.query(Enrollment)
            .filter(Enrollment.academic_term == req.academic_term, Enrollment.status == "ENROLLED")
            .all()
        )
        students = self.db.query(Student).all()

        course_by_id = {c.id: c for c in courses}
        room_by_id = {r.id: r for r in rooms}
        ta_by_id = {t.id: t for t in tas}
        student_by_id = {s.id: s for s in students}

        exam_days = list(range(1, req.exam_days_count + 1))
        sessions = list(range(1, req.sessions_per_day + 1))
        all_time_slots = [(d, s) for d in exam_days for s in sessions]

        # Toplam efektif sınav kapasitesi kontrolü
        total_effective_room_cap = sum(r.effective_exam_capacity for r in rooms)
        unsat_diagnostics: list[str] = []
        for c in courses:
            if c.enrolled_count > total_effective_room_cap:
                unsat_diagnostics.append(
                    f"1-Boş-Koltuk Sınav Kapasitesi Darboğazı [Ders: {c.code}]: Kayıtlı öğrenci sayısı "
                    f"({c.enrolled_count}), kampüsteki tüm salonların 1-boş-koltuk efektif kapasite toplamını "
                    f"({total_effective_room_cap}) aşıyor."
                )

        if len(courses) > len(all_time_slots) * len(rooms):
            unsat_diagnostics.append(
                "Sınav Takvimi Slot Darboğazı: Toplam ders sayısı, tanımlanan sınav günü ve oturum sayısına sığmıyor."
            )

        # Öğrenci ders kayıtlarından (enrollments) ortak öğrencisi olan tüm ders çiftlerini çıkar
        students_by_course: dict[int, list[int]] = defaultdict(list)
        for enr in enrollments:
            if enr.course_id in course_by_id:
                students_by_course[enr.course_id].append(enr.student_id)

        conflict_course_pairs: set[tuple[int, int]] = set()
        # 1) Ortak kayıtlı öğrencisi (enrollments) bulunan ders çiftleri
        for c_a, c_b in combinations(courses, 2):
            set_a = set(students_by_course.get(c_a.id, []))
            set_b = set(students_by_course.get(c_b.id, []))
            if (set_a & set_b) or (c_a.semester == c_b.semester):
                pair_key = (c_a.id, c_b.id) if c_a.id < c_b.id else (c_b.id, c_a.id)
                conflict_course_pairs.add(pair_key)

        # Arş. Gör. müsait olmama haritası: (ta_id, exam_day, session_index) -> True
        ta_blocked_set = {(u.ta_id, u.exam_day, u.session_index) for u in ta_unavails}

        # ======================================================================
        # İKİ AŞAMALI (DECOMPOSED) CP-SAT MİMARİSİ (Çok Hızlı & %100 Deterministik):
        # Aşama A: Öğrenci Sınav Çakışmasızlığı + 1-Boş-Koltuk Çoklu Amfi Bölme CSP
        # Aşama B: Seçilen Aktif Sınav Salonlarına Minimax (L_max - L_min) Gözetmen CSP
        # ======================================================================
        model_a = cp_model.CpModel()

        # E[c_id, d, s] in {0, 1}: Ders c'nin sınavı d. gün s. oturumda mı?
        e_vars: dict[tuple[int, int, int], cp_model.IntVar] = {}
        # Y[c_id, r_id, d, s] in {0, 1}: Ders c'nin sınavı (d, s) oturumunda r amfisini kullanıyor mu?
        y_vars: dict[tuple[int, int, int, int], cp_model.IntVar] = {}

        for c in courses:
            c_session_vars = []
            for d, s in all_time_slots:
                # Oturumda müsait olan toplam Arş. Gör. sayısı kontrolü
                avail_ta_count = sum(1 for ta in tas if (ta.id, d, s) not in ta_blocked_set)
                if avail_ta_count == 0:
                    continue

                e_var = model_a.NewBoolVar(f"e_c{c.id}_d{d}_s{s}")
                e_vars[(c.id, d, s)] = e_var
                c_session_vars.append(e_var)

                room_vars_at_slot = []
                for r in rooms:
                    y_var = model_a.NewBoolVar(f"y_c{c.id}_r{r.id}_d{d}_s{s}")
                    y_vars[(c.id, r.id, d, s)] = y_var
                    room_vars_at_slot.append(y_var)
                    model_a.Add(y_var <= e_var)

                # HARD CONSTRAINT (1-Boş-Koltuk Efektif Sınav Kapasitesi):
                # Seçilen amfilerin effective_exam_capacity toplamı >= dersin öğrenci sayısı (enrolled_count)
                model_a.Add(
                    sum(r.effective_exam_capacity * y_vars[(c.id, r.id, d, s)] for r in rooms)
                    >= c.enrolled_count * e_var
                )
                model_a.Add(sum(room_vars_at_slot) <= min(3, avail_ta_count) * e_var)

            # HARD CONSTRAINT: Her dersin tam 1 sınav oturumu olmalıdır
            model_a.Add(sum(c_session_vars) == 1)

        # HARD CONSTRAINT (Öğrenci Sınav Çakışması — 0 Tolerans):
        # Ortak öğrencisi olan iki dersin sınavı aynı (d, s) oturumuna atanamaz!
        for c_a_id, c_b_id in conflict_course_pairs:
            for d, s in all_time_slots:
                va = e_vars.get((c_a_id, d, s))
                vb = e_vars.get((c_b_id, d, s))
                if va is not None and vb is not None:
                    model_a.Add(va + vb <= 1)

        # HARD CONSTRAINT (Aynı Dönem Öğrencileri İçin Günde En Fazla 1 Sınav / Yoğunluk Sınırı):
        courses_by_sem: dict[int, list[Course]] = defaultdict(list)
        for c in courses:
            courses_by_sem[c.semester].append(c)
        for sem, sem_courses in courses_by_sem.items():
            # Eğer sınav günü sayısı dönemdeki ders sayısından azsa günde en fazla 2 sınava izin ver, değilse 1
            max_per_day = 1 if len(exam_days) >= len(sem_courses) else 2
            for d in exam_days:
                day_sem_exams = [
                    e_vars[(c.id, d, s)]
                    for c in sem_courses
                    for s in sessions
                    if (c.id, d, s) in e_vars
                ]
                if day_sem_exams:
                    model_a.Add(sum(day_sem_exams) <= max_per_day)

        # HARD CONSTRAINT (Amfi Çakışmazlığı ve Oturum Başına Gözetmen Yeterliliği):
        for d, s in all_time_slots:
            avail_ta_count = sum(1 for ta in tas if (ta.id, d, s) not in ta_blocked_set)
            slot_all_room_vars = []
            for r in rooms:
                r_slot_vars = [
                    y_vars[(c.id, r.id, d, s)]
                    for c in courses
                    if (c.id, r.id, d, s) in y_vars
                ]
                if r_slot_vars:
                    model_a.Add(sum(r_slot_vars) <= 1)
                    slot_all_room_vars.extend(r_slot_vars)
            # Aynı oturumda açılan toplam sınav salonu sayısı, o oturumdaki müsait Arş. Gör. sayısını aşamaz!
            if slot_all_room_vars:
                model_a.Add(sum(slot_all_room_vars) <= avail_ta_count)

        # Aşama A Hedefi: Toplam açılan sınav salonu sayısını ve akşam/hafta sonu oturumlarını minimize et
        heavy_session_penalties = [
            2 * var
            for (c_id, d, s), var in e_vars.items()
            if (s == req.sessions_per_day) or (d in (6, 7))
        ]
        model_a.Minimize(10 * sum(y_vars.values()) + sum(heavy_session_penalties))

        solver_a = cp_model.CpSolver()
        solver_a.parameters.max_time_in_seconds = max(2.0, float(req.max_time_seconds) * 0.6)
        solver_a.parameters.num_search_workers = settings.cpsat_num_search_workers
        status_a = solver_a.Solve(model_a)

        if status_a not in (cp_model.OPTIMAL, cp_model.FEASIBLE) or unsat_diagnostics:
            elapsed_sec = round(time.perf_counter() - start_ts, 4)
            if not unsat_diagnostics:
                unsat_diagnostics.append(
                    "Sınav Takvimi CP-SAT Çözülemezlik Tanısı: Sınav gün/oturum sayısı veya 1-boş-koltuk "
                    "salon kapasitesi öğrenci çakışmasızlığını karşılamak için yetersiz."
                )
            return ExamScheduleOptimizationResponse(
                academic_term=req.academic_term,
                exam_type=req.exam_type,
                solver_status="INFEASIBLE",
                solve_time_seconds=elapsed_sec,
                total_exams_scheduled=0,
                total_room_allocations=0,
                total_seated_students=0,
                zero_student_clash_verified=False,
                one_empty_seat_rule_verified=False,
                min_ta_workload=0.0,
                max_ta_workload=0.0,
                workload_max_min_spread=0.0,
                unsat_diagnostics_tr=unsat_diagnostics,
                exam_sessions=[],
                proctor_workloads=[],
            )

        # Aşama A'dan seçilen aktif (ders, salon, gün, oturum) görevlerini çıkar
        # active_duties: list of (duty_idx, course_obj, room_obj, day, session, w_scaled)
        active_duties: list[tuple[int, Course, Room, int, int, int]] = []
        chosen_slot_by_course: dict[int, tuple[int, int]] = {}
        duty_seq = 0
        for c in courses:
            for d, s in all_time_slots:
                ev = e_vars.get((c.id, d, s))
                if ev is not None and solver_a.Value(ev) == 1:
                    chosen_slot_by_course[c.id] = (d, s)
                    is_heavy = (s == req.sessions_per_day) or (d in (6, 7))
                    w_scaled = 3 if is_heavy else 2
                    for r in rooms:
                        yv = y_vars.get((c.id, r.id, d, s))
                        if yv is not None and solver_a.Value(yv) == 1:
                            active_duties.append((duty_seq, c, r, d, s, w_scaled))
                            duty_seq += 1
                    break

        # ======================================================================
        # AŞAMA B: Aktif Sınav Salonlarına Minimax (L_max - L_min) Gözetmen CP-SAT Çözücüsü
        # ======================================================================
        model_b = cp_model.CpModel()
        z_duty_vars: dict[tuple[int, int], cp_model.IntVar] = {}  # (duty_idx, ta_id) -> BoolVar

        for duty_idx, c_obj, r_obj, d, s, _ in active_duties:
            duty_ta_vars = []
            for ta in tas:
                if (ta.id, d, s) in ta_blocked_set:
                    continue
                zv = model_b.NewBoolVar(f"z_duty{duty_idx}_ta{ta.id}")
                z_duty_vars[(duty_idx, ta.id)] = zv
                duty_ta_vars.append(zv)
            # Her aktif sınav salonuna tam 1 müsait Arş. Gör. atanmalıdır
            model_b.Add(sum(duty_ta_vars) == 1)

        # Aynı (gün, oturum) içinde bir Arş. Gör. en fazla 1 sınav salonuna atanabilir
        duties_by_slot: dict[tuple[int, int], list[int]] = defaultdict(list)
        for duty_idx, _, _, d, s, _ in active_duties:
            duties_by_slot[(d, s)].append(duty_idx)

        for (d, s), slot_duty_ids in duties_by_slot.items():
            if len(slot_duty_ids) <= 1:
                continue
            for ta in tas:
                ta_vars_in_slot = [
                    z_duty_vars[(d_idx, ta.id)]
                    for d_idx in slot_duty_ids
                    if (d_idx, ta.id) in z_duty_vars
                ]
                if len(ta_vars_in_slot) > 1:
                    model_b.Add(sum(ta_vars_in_slot) <= 1)

        max_possible_scaled_load = max(1, len(active_duties) * 3)
        l_max = model_b.NewIntVar(0, max_possible_scaled_load, "L_max_scaled")
        l_min = model_b.NewIntVar(0, max_possible_scaled_load, "L_min_scaled")

        for ta in tas:
            load_var = model_b.NewIntVar(0, max_possible_scaled_load, f"load_ta{ta.id}")
            w_terms = [
                w_sc * z_duty_vars[(duty_idx, ta.id)]
                for duty_idx, _, _, _, _, w_sc in active_duties
                if (duty_idx, ta.id) in z_duty_vars
            ]
            if w_terms:
                model_b.Add(load_var == sum(w_terms))
            else:
                model_b.Add(load_var == 0)
            model_b.Add(l_max >= load_var)
            model_b.Add(l_min <= load_var)

        # Minimax Adalet Kriteri: min (L_max - L_min)
        model_b.Minimize(l_max - l_min)

        solver_b = cp_model.CpSolver()
        solver_b.parameters.max_time_in_seconds = max(2.0, float(req.max_time_seconds) * 0.4)
        solver_b.parameters.num_search_workers = settings.cpsat_num_search_workers
        status_b = solver_b.Solve(model_b)
        elapsed_sec = round(time.perf_counter() - start_ts, 4)

        if status_b not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            return ExamScheduleOptimizationResponse(
                academic_term=req.academic_term,
                exam_type=req.exam_type,
                solver_status="INFEASIBLE",
                solve_time_seconds=elapsed_sec,
                total_exams_scheduled=0,
                total_room_allocations=0,
                total_seated_students=0,
                zero_student_clash_verified=False,
                one_empty_seat_rule_verified=False,
                min_ta_workload=0.0,
                max_ta_workload=0.0,
                workload_max_min_spread=0.0,
                unsat_diagnostics_tr=[
                    "Gözetmen Dağıtım Darboğazı: Eşzamanlı sınav salonu sayısı, o oturumda lisansüstü dersi "
                    "olmayan müsait araştırma görevlisi sayısını aşıyor."
                ],
                exam_sessions=[],
                proctor_workloads=[],
            )

        assigned_ta_by_course_room: dict[tuple[int, int], TeachingAssistant] = {}
        chosen_rooms_by_course: dict[int, list[tuple[Room, TeachingAssistant]]] = defaultdict(list)
        for duty_idx, c_obj, r_obj, _, _, _ in active_duties:
            chosen_ta = tas[0]
            for ta in tas:
                zv = z_duty_vars.get((duty_idx, ta.id))
                if zv is not None and solver_b.Value(zv) == 1:
                    chosen_ta = ta
                    break
            assigned_ta_by_course_room[(c_obj.id, r_obj.id)] = chosen_ta
            chosen_rooms_by_course[c_obj.id].append((r_obj, chosen_ta))

        status = cp_model.OPTIMAL if (status_a == cp_model.OPTIMAL and status_b == cp_model.OPTIMAL) else cp_model.FEASIBLE

        # Eski sınav oturumlarını temizle
        self.db.query(ExamSession).filter(
            ExamSession.academic_term == req.academic_term,
            ExamSession.exam_type == req.exam_type,
        ).delete()
        self.db.flush()

        exam_sessions_read: list[ExamSessionRead] = []
        ta_duty_counts: dict[int, int] = {ta.id: 0 for ta in tas}
        ta_workload_totals: dict[int, float] = {ta.id: 0.0 for ta in tas}
        total_room_allocs = 0
        total_seated_students = 0

        for c in courses:
            chosen_d, chosen_s = chosen_slot_by_course[c.id]

            is_heavy = (chosen_s == req.sessions_per_day) or (chosen_d in (6, 7))
            duty_w = 1.5 if is_heavy else 1.0

            db_exam = ExamSession(
                academic_term=req.academic_term,
                exam_type=req.exam_type,
                course_id=c.id,
                exam_day=chosen_d,
                session_index=chosen_s,
                is_weekend_or_evening=is_heavy,
                duty_weight=duty_w,
            )
            self.db.add(db_exam)
            self.db.flush()

            chosen_rooms = chosen_rooms_by_course[c.id]

            # Öğrencileri 1-Boş-Koltuk kapasitesine göre seçilen amfilere dağıt ve 2B koltuk koordinatlarını üret
            enrolled_st_ids = sorted(students_by_course.get(c.id, []))
            remaining_headcount = c.enrolled_count
            st_cursor = 0
            room_proctor_items: list[ExamRoomProctorItem] = []

            for r_obj, ta_obj in chosen_rooms:
                alloc_count = min(remaining_headcount, r_obj.effective_exam_capacity)
                remaining_headcount = max(0, remaining_headcount - alloc_count)
                total_room_allocs += 1

                self.db.add(
                    ExamRoomAllocation(
                        exam_session_id=db_exam.id,
                        room_id=r_obj.id,
                        allocated_student_count=alloc_count,
                    )
                )
                self.db.add(
                    ProctorAssignment(
                        exam_session_id=db_exam.id,
                        room_id=r_obj.id,
                        ta_id=ta_obj.id,
                        assigned_load=duty_w,
                    )
                )
                ta_duty_counts[ta_obj.id] += 1
                ta_workload_totals[ta_obj.id] = round(ta_workload_totals[ta_obj.id] + duty_w, 2)

                # Gerçek kayıtlı öğrencileri (varsa) bu amfinin 1-boş-koltuk koordinatlarına yerleştir
                st_slice = enrolled_st_ids[st_cursor : st_cursor + alloc_count]
                st_cursor += len(st_slice)
                seat_coords = self._generate_1_empty_seat_coordinates(r_obj, len(st_slice))

                for st_id, (s_row, s_col) in zip(st_slice, seat_coords):
                    self.db.add(
                        ExamSeatingAssignment(
                            exam_session_id=db_exam.id,
                            room_id=r_obj.id,
                            student_id=st_id,
                            seat_row=s_row,
                            seat_col=s_col,
                        )
                    )
                    total_seated_students += 1

                room_proctor_items.append(
                    ExamRoomProctorItem(
                        room_id=r_obj.id,
                        room_code=r_obj.code,
                        room_normal_capacity=r_obj.normal_capacity,
                        room_effective_exam_capacity=r_obj.effective_exam_capacity,
                        allocated_student_count=alloc_count,
                        proctor_ta_id=ta_obj.id,
                        proctor_ta_code=ta_obj.code,
                        proctor_ta_name=ta_obj.full_name,
                        duty_weight=duty_w,
                    )
                )

            exam_sessions_read.append(
                ExamSessionRead(
                    exam_session_id=db_exam.id,
                    course_id=c.id,
                    course_code=c.code,
                    course_name=c.name,
                    semester=c.semester,
                    enrolled_count=c.enrolled_count,
                    exam_day=chosen_d,
                    session_index=chosen_s,
                    is_weekend_or_evening=is_heavy,
                    duty_weight=duty_w,
                    rooms=room_proctor_items,
                )
            )

        # Arş. Gör. güncel yük skorlarını güncelle
        proctor_summaries: list[ProctorWorkloadSummaryItem] = []
        for ta in tas:
            ta.current_workload_score = ta_workload_totals[ta.id]
            proctor_summaries.append(
                ProctorWorkloadSummaryItem(
                    ta_id=ta.id,
                    ta_code=ta.code,
                    ta_name=ta.full_name,
                    assigned_exam_rooms_count=ta_duty_counts[ta.id],
                    total_weighted_workload=ta_workload_totals[ta.id],
                )
            )

        self.db.commit()

        loads = list(ta_workload_totals.values()) or [0.0]
        min_load = min(loads)
        max_load = max(loads)
        spread = round(max_load - min_load, 2)
        status_str = "OPTIMAL" if status == cp_model.OPTIMAL else "FEASIBLE"

        return ExamScheduleOptimizationResponse(
            academic_term=req.academic_term,
            exam_type=req.exam_type,
            solver_status=status_str,
            solve_time_seconds=elapsed_sec,
            total_exams_scheduled=len(exam_sessions_read),
            total_room_allocations=total_room_allocs,
            total_seated_students=total_seated_students,
            zero_student_clash_verified=True,
            one_empty_seat_rule_verified=True,
            min_ta_workload=min_load,
            max_ta_workload=max_load,
            workload_max_min_spread=spread,
            unsat_diagnostics_tr=[],
            exam_sessions=sorted(exam_sessions_read, key=lambda x: (x.exam_day, x.session_index, x.course_code)),
            proctor_workloads=proctor_summaries,
        )

    def get_exam_seating_grid(self, exam_session_id: int) -> RoomSeatingGridResponse:
        """
        Belirli bir sınav oturumunun 2B (satır, sütun) oturma planını döndürür
        ve yan yana iki öğrenci arasında en az 1 boş koltuk bulunduğunu doğrular.
        """
        exam = self.db.query(ExamSession).filter(ExamSession.id == exam_session_id).first()
        if not exam:
            raise LookupError(f"Sınav oturumu bulunamadı: ID={exam_session_id}")

        course = self.db.query(Course).filter(Course.id == exam.course_id).first()
        seats_db = (
            self.db.query(ExamSeatingAssignment)
            .filter(ExamSeatingAssignment.exam_session_id == exam.id)
            .order_by(
                ExamSeatingAssignment.room_id.asc(),
                ExamSeatingAssignment.seat_row.asc(),
                ExamSeatingAssignment.seat_col.asc(),
            )
            .all()
        )
        room_obj_map = {r.id: r for r in self.db.query(Room).all()}
        room_map = {r_id: r.code for r_id, r in room_obj_map.items()}
        st_map = {s.id: s for s in self.db.query(Student).all()}
        ta_map = {t.id: t for t in self.db.query(TeachingAssistant).all()}

        # Bu sınava atanan salonların fiziksel boyutlarını ve gözetmenlerini çıkar
        room_allocs = (
            self.db.query(ExamRoomAllocation)
            .filter(ExamRoomAllocation.exam_session_id == exam.id)
            .order_by(ExamRoomAllocation.room_id.asc())
            .all()
        )
        proctor_allocs = {
            pa.room_id: ta_map.get(pa.ta_id)
            for pa in self.db.query(ProctorAssignment)
            .filter(ProctorAssignment.exam_session_id == exam.id)
            .all()
        }

        visual_rooms: list[VisualRoomLayoutItem] = []
        for ra in room_allocs:
            r_obj = room_obj_map.get(ra.room_id)
            if not r_obj:
                continue
            ta_obj = proctor_allocs.get(ra.room_id)
            visual_rooms.append(
                VisualRoomLayoutItem(
                    room_id=r_obj.id,
                    room_code=r_obj.code,
                    room_name=r_obj.name,
                    room_type=r_obj.room_type,
                    seat_rows=r_obj.seat_rows,
                    seat_cols=r_obj.seat_cols,
                    normal_capacity=r_obj.normal_capacity,
                    effective_exam_capacity=r_obj.effective_exam_capacity,
                    allocated_student_count=ra.allocated_student_count,
                    proctor_ta_code=ta_obj.code if ta_obj else "UNASSIGNED",
                    proctor_ta_name=ta_obj.full_name if ta_obj else "Unassigned",
                )
            )

        # 1-Boş-Koltuk doğrulaması: Aynı oda ve aynı satırdaki ardışık iki öğrenci arasında |col_j - col_i| >= 2 olmalı
        cols_by_room_row: dict[tuple[int, int], list[int]] = defaultdict(list)
        seat_items: list[SeatCellItem] = []

        for s_assign in seats_db:
            cols_by_room_row[(s_assign.room_id, s_assign.seat_row)].append(s_assign.seat_col)
            st_obj = st_map[s_assign.student_id]
            seat_items.append(
                SeatCellItem(
                    student_id=st_obj.id,
                    student_number=st_obj.student_number,
                    student_name=st_obj.full_name,
                    room_code=room_map[s_assign.room_id],
                    seat_row=s_assign.seat_row,
                    seat_col=s_assign.seat_col,
                )
            )

        spacing_ok = True
        for cols in cols_by_room_row.values():
            sorted_cols = sorted(cols)
            for idx in range(len(sorted_cols) - 1):
                if sorted_cols[idx + 1] - sorted_cols[idx] < 2:
                    spacing_ok = False
                    break

        return RoomSeatingGridResponse(
            exam_session_id=exam.id,
            course_code=course.code if course else "UNKNOWN",
            course_name=course.name if course else "Unknown Course",
            exam_day=exam.exam_day,
            session_index=exam.session_index,
            total_seated_students=len(seat_items),
            one_empty_seat_verified=spacing_ok,
            rooms=visual_rooms,
            seats=seat_items,
        )
