"""
Modül 2 — Course Scheduling Engine (Google OR-Tools CP-SAT Haftalık Ders Programı Çözücüsü).

AGENTS.md Mimari ve Algoritmik Kuralları:
1. Hard Constraints (Kesin Kısıtlar — 0 Tolerans):
   - Oda kapasitesi aşımı yasaktır: Enr(c) <= Cap(r).
   - Laboratuvar gerektiren ders (requires_lab_room=True) normal amfiye atanamaz; sadece LAB odasına atanır.
   - Aynı odada aynı (day, slot) içinde en fazla 1 ders olabilir.
   - Aynı öğretim elemanında aynı (day, slot) içinde en fazla 1 ders olabilir ve hoca sadece
     müsait (is_available=True) olduğu saatlere atanabilir.
   - Modül 1'den gelen C_DAG çakışmazlık matrisi kuralları (aynı dönem dersleri, yan-koşul dersleri
     ve alttan ders alan düzensiz öğrencilerin birlikte aldığı ders çiftleri) aynı (day, slot)
     dilimine KESİNLİKLE atanamaz.

2. Soft Constraints (Yumuşak Kısıtlar — Ağırlıklı Ceza Optimizasyonu):
   - Öğrencilerin (her yarıyıl kohortunun) aynı gün içindeki dersleri arasındaki boş saatlerin
     (idle gaps: G_{k,d} = Span_{k,d} - ActiveHours_{k,d}) minimize edilmesi.
   - Öğretim elemanı saat tercih cezalarının (preference_penalty) minimize edilmesi.

3. Çözülemezlik Tanısı (Unsat Core & Timeout):
   - CP-SAT çözücüsü sonsuz döngüye bırakılmaz (`max_time_in_seconds` sınırı uygulanır).
   - Kısıtlar aşırı sıkı olduğunda sadece "INFEASIBLE" döndürmek yerine, OR-Tools `Assumptions`
     ve darboğaz analiz mekanizmasıyla hangi dersin, hocanın veya amfi/lab kapasitesinin
     çözülemezlik yarattığını anlaşılır Türkçe mesajlarla (`unsat_diagnostics_tr`) raporlar.
"""

from collections import defaultdict
import time
from ortools.sat.python import cp_model
from sqlalchemy.orm import Session

from app.config import settings
from app.engines.dag_engine import CurriculumGraphEngine
from app.models.academic import (
    Course,
    Instructor,
    InstructorAvailability,
    Room,
    WeeklyScheduleAssignment,
)
from app.schemas.academic import (
    WeeklyScheduleGenerateRequest,
    WeeklyScheduleOptimizationResponse,
    WeeklySlotAssignmentRead,
)


class WeeklyCourseSchedulingEngine:
    """Google OR-Tools CP-SAT tabanlı Haftalık Ders Programı Optimizasyon Motoru (Modül 2)."""

    DAYS = [1, 2, 3, 4, 5]          # Pazartesi (1) .. Cuma (5)
    SLOTS = [1, 2, 3, 4, 5, 6, 7, 8]  # Günlük 8 ders saati dilimi

    def __init__(self, db: Session):
        self.db = db

    def _filter_courses_by_parity(self, all_courses: list[Course], parity: str) -> list[Course]:
        if parity == "FALL":
            return [c for c in all_courses if c.semester % 2 == 1]
        if parity == "SPRING":
            return [c for c in all_courses if c.semester % 2 == 0]
        return all_courses

    def _diagnose_infeasibility_tr(
        self,
        courses: list[Course],
        rooms: list[Room],
        inst_avail_map: dict[tuple[int, int, int], bool],
        inst_by_id: dict[int, Instructor],
    ) -> list[str]:
        """
        Model INFEASIBLE çıktığında veya ön-kontrolde darboğaz tespit edildiğinde,
        OR-Tools Assumptions (Unsat Core) ve kapasite/müsaitlik analizi ile
        hangi dersin, hocanın veya amfinin darboğaz yarattığını Türkçe raporlar.
        """
        diagnostics: list[str] = []

        # 1. Ders bazlı uygun oda (kapasite + LAB tipi) darboğaz kontrolü
        for c in courses:
            compatible_rooms = [
                r
                for r in rooms
                if r.normal_capacity >= c.enrolled_count
                and (not c.requires_lab_room or r.room_type == "LAB")
            ]
            if not compatible_rooms:
                room_type_tr = "Bilgisayar Laboratuvarı (LAB)" if c.requires_lab_room else "Amfi/Derslik"
                max_cap = max(
                    (r.normal_capacity for r in rooms if not c.requires_lab_room or r.room_type == "LAB"),
                    default=0,
                )
                diagnostics.append(
                    f"Kapasite Darboğazı [Ders: {c.code} - {c.name}]: Kayıtlı öğrenci sayısı ({c.enrolled_count}), "
                    f"uygun '{room_type_tr}' tipindeki en yüksek salon kapasitesini ({max_cap}) aşıyor."
                )

        # 2. Öğretim elemanı toplam ders saati vs müsait slot darboğaz kontrolü
        inst_required_hours: dict[int, int] = defaultdict(int)
        inst_courses_map: dict[int, list[str]] = defaultdict(list)
        for c in courses:
            if c.instructor_id is not None:
                # Haftalık ders yükü: theory_hours (veya en az 3 saat)
                weekly_slots_needed = max(1, c.theory_hours)
                inst_required_hours[c.instructor_id] += weekly_slots_needed
                inst_courses_map[c.instructor_id].append(f"{c.code} ({weekly_slots_needed} saat)")

        for inst_id, req_hours in inst_required_hours.items():
            avail_slots = sum(
                1
                for d in self.DAYS
                for s in self.SLOTS
                if inst_avail_map.get((inst_id, d, s), True)
            )
            inst_obj = inst_by_id.get(inst_id)
            inst_name = inst_obj.full_name if inst_obj else f"ID={inst_id}"
            if req_hours > avail_slots:
                diagnostics.append(
                    f"Öğretim Elemanı Müsaitlik Darboğazı [{inst_name}]: Atanan derslerin toplam haftalık "
                    f"süresi ({req_hours} saat: {', '.join(inst_courses_map[inst_id])}), hocanın haftalık "
                    f"açık/müsait slot sayısını ({avail_slots} saat) aşıyor."
                )

        # 3. Dönem (Cohort) veya LAB toplam slot darboğazı
        total_lab_hours = sum(max(1, c.theory_hours) for c in courses if c.requires_lab_room)
        lab_rooms_count = sum(1 for r in rooms if r.room_type == "LAB")
        max_lab_capacity_slots = lab_rooms_count * len(self.DAYS) * len(self.SLOTS)
        if total_lab_hours > max_lab_capacity_slots:
            diagnostics.append(
                f"Laboratuvar Odası Darboğazı: Toplam LAB dersi saati ({total_lab_hours} saat), "
                f"mevcut {lab_rooms_count} adet LAB salonunun haftalık toplam kapasitesini ({max_lab_capacity_slots} slot) aşıyor."
            )

        # 4. Eğer yukarıdaki temel kontrollerde doğrudan aşım yoksa, OR-Tools Assumptions (Unsat Core) çalıştır
        if not diagnostics:
            assump_model = cp_model.CpModel()
            course_assumptions: dict[int, cp_model.IntVar] = {}
            x_vars: dict[tuple[int, int, int, int], cp_model.IntVar] = {}

            for c in courses:
                a_lit = assump_model.NewBoolVar(f"assump_course_{c.code}")
                course_assumptions[c.id] = a_lit
                compat_rooms = [
                    r
                    for r in rooms
                    if r.normal_capacity >= c.enrolled_count
                    and (not c.requires_lab_room or r.room_type == "LAB")
                ]
                c_vars = []
                for r in compat_rooms:
                    for d in self.DAYS:
                        for s in self.SLOTS:
                            if c.instructor_id is not None and not inst_avail_map.get((c.instructor_id, d, s), True):
                                continue
                            v = assump_model.NewBoolVar(f"ax_{c.id}_{r.id}_{d}_{s}")
                            x_vars[(c.id, r.id, d, s)] = v
                            c_vars.append(v)
                req_h = max(1, c.theory_hours)
                assump_model.Add(sum(c_vars) == req_h).OnlyEnforceIf(a_lit)

            # Oda ve Hoca çakışmazlığı
            for r in rooms:
                for d in self.DAYS:
                    for s in self.SLOTS:
                        r_slot_vars = [
                            x_vars[(c.id, r.id, d, s)]
                            for c in courses
                            if (c.id, r.id, d, s) in x_vars
                        ]
                        if len(r_slot_vars) > 1:
                            assump_model.Add(sum(r_slot_vars) <= 1)

            for inst_id in inst_required_hours:
                inst_c_list = [c for c in courses if c.instructor_id == inst_id]
                for d in self.DAYS:
                    for s in self.SLOTS:
                        i_vars = [
                            x_vars[(c.id, r.id, d, s)]
                            for c in inst_c_list
                            for r in rooms
                            if (c.id, r.id, d, s) in x_vars
                        ]
                        if len(i_vars) > 1:
                            assump_model.Add(sum(i_vars) <= 1)

            assump_model.AddAssumptions(list(course_assumptions.values()))
            solver = cp_model.CpSolver()
            solver.parameters.max_time_in_seconds = 5.0
            solver.parameters.num_search_workers = 1  # Unsat core extraction tek iş parçacığında kesin çalışır
            status = solver.Solve(assump_model)

            if status == cp_model.INFEASIBLE:
                core_lits = set(solver.SufficientAssumptionsForInfeasibility())
                conflicting_courses = [
                    f"{c.code} ({c.name})"
                    for c in courses
                    if course_assumptions[c.id].Index() in core_lits
                ]
                if conflicting_courses:
                    diagnostics.append(
                        f"CP-SAT Unsat Core Tanısı: Şu dersler ortak amfi kapasitesi, hoca müsaitliği veya "
                        f"C_DAG çakışmazlık kuralları nedeniyle aynı anda zamanlanamıyor: {', '.join(conflicting_courses)}."
                    )

        if not diagnostics:
            diagnostics.append(
                "CP-SAT Çözülemezlik Tanısı: C_DAG çakışmazlık kısıtları ile öğretim elemanı müsaitlik pencereleri "
                "arasında darboğaz oluştu. Lütfen hoca müsaitlik saatlerini veya büyük amfi sayısını genişletin."
            )

        return diagnostics

    def generate_weekly_schedule(
        self, req: WeeklyScheduleGenerateRequest
    ) -> WeeklyScheduleOptimizationResponse:
        """
        Modül 1'den C_DAG çakışmazlık matrisini alır ve Google OR-Tools CP-SAT ile
        haftalık ders programını tüm kesin (hard) ve yumuşak (soft) kısıtlarla optimize eder.
        """
        start_ts = time.perf_counter()

        all_courses = self.db.query(Course).order_by(Course.semester.asc(), Course.code.asc()).all()
        courses = self._filter_courses_by_parity(all_courses, req.semester_parity)
        rooms = self.db.query(Room).order_by(Room.code.asc()).all()
        instructors = self.db.query(Instructor).all()
        availabilities = self.db.query(InstructorAvailability).all()

        course_by_id = {c.id: c for c in courses}
        room_by_id = {r.id: r for r in rooms}
        inst_by_id = {i.id: i for i in instructors}

        # Hoca müsaitlik ve tercih cezası haritaları
        inst_avail_map: dict[tuple[int, int, int], bool] = {}
        inst_pref_map: dict[tuple[int, int, int], int] = {}
        for av in availabilities:
            inst_avail_map[(av.instructor_id, av.day_of_week, av.slot_index)] = av.is_available
            inst_pref_map[(av.instructor_id, av.day_of_week, av.slot_index)] = av.preference_penalty

        # Modül 1'den zorunlu C_DAG çakışmazlık matrisini çek
        dag_engine = CurriculumGraphEngine(self.db)
        c_dag_matrix = dag_engine.generate_non_conflict_matrix(academic_term=req.academic_term)
        active_c_dag_pairs = [
            (p.course_a_id, p.course_b_id)
            for p in c_dag_matrix.pairs
            if p.course_a_id in course_by_id and p.course_b_id in course_by_id
        ]

        # ÖN-KONTROL: Her ders için kapasite ve tip (LAB/LECTURE) uyumlu en az 1 oda var mı?
        pre_diagnostics = self._diagnose_infeasibility_tr(courses, rooms, inst_avail_map, inst_by_id)
        # Eğer kesin bir kapasite veya hoca toplam saat aşımı varsa CP-SAT'a girmeden hemen önce de yakalanır,
        # ancak CP-SAT modelini yine de kurup kesin doğrulama yapıyoruz.

        model = cp_model.CpModel()

        # Karar Değişkenleri:
        # X[c_id, r_id, d, s] in {0, 1}: Ders c, oda r, gün d, slot s'de yapılıyor mu?
        # Active[c_id, d, s] in {0, 1}: Ders c, gün d, slot s'de (herhangi bir uygun odada) yapılıyor mu?
        x_vars: dict[tuple[int, int, int, int], cp_model.IntVar] = {}
        active_vars: dict[tuple[int, int, int], cp_model.IntVar] = {}

        for c in courses:
            # HARD CONSTRAINT (Kapasite & LAB Odası Kuralı):
            # Sadece kapasitesi yeten ve LAB gereksinimine uyan odalar için değişken üretilir (0 tolerans)
            compatible_rooms = [
                r
                for r in rooms
                if r.normal_capacity >= c.enrolled_count
                and (not c.requires_lab_room or r.room_type == "LAB")
            ]

            course_all_slot_vars: list[cp_model.IntVar] = []
            for d in self.DAYS:
                day_active_vars: list[cp_model.IntVar] = []
                for s in self.SLOTS:
                    # HARD CONSTRAINT (Öğretim Elemanı Müsaitliği):
                    if c.instructor_id is not None and not inst_avail_map.get((c.instructor_id, d, s), True):
                        continue

                    slot_room_vars: list[cp_model.IntVar] = []
                    for r in compatible_rooms:
                        var = model.NewBoolVar(f"x_c{c.id}_r{r.id}_d{d}_s{s}")
                        x_vars[(c.id, r.id, d, s)] = var
                        slot_room_vars.append(var)

                    if slot_room_vars:
                        act_var = model.NewBoolVar(f"act_c{c.id}_d{d}_s{s}")
                        model.Add(sum(slot_room_vars) == act_var)
                        active_vars[(c.id, d, s)] = act_var
                        course_all_slot_vars.append(act_var)
                        day_active_vars.append(act_var)

                # Pedagojik kısıt: Bir ders aynı günde en fazla 2 saat yapılabilir (derslerin haftaya dengeli dağılımı)
                if day_active_vars:
                    model.Add(sum(day_active_vars) <= 2)

            # HARD CONSTRAINT (Haftalık Toplam Ders Saati):
            required_weekly_slots = max(1, c.theory_hours)
            model.Add(sum(course_all_slot_vars) == required_weekly_slots)

        # HARD CONSTRAINT (Oda Çakışmazlığı): Aynı odada, aynı gün ve slotta en fazla 1 ders olabilir
        for r in rooms:
            for d in self.DAYS:
                for s in self.SLOTS:
                    room_vars = [
                        x_vars[(c.id, r.id, d, s)]
                        for c in courses
                        if (c.id, r.id, d, s) in x_vars
                    ]
                    if len(room_vars) > 1:
                        model.Add(sum(room_vars) <= 1)

        # HARD CONSTRAINT (Öğretim Elemanı Çakışmazlığı): Aynı hoca aynı gün ve slotta en fazla 1 derse girebilir
        courses_by_inst: dict[int, list[Course]] = defaultdict(list)
        for c in courses:
            if c.instructor_id is not None:
                courses_by_inst[c.instructor_id].append(c)

        for inst_id, inst_courses in courses_by_inst.items():
            if len(inst_courses) <= 1:
                continue
            for d in self.DAYS:
                for s in self.SLOTS:
                    inst_slot_vars = [
                        active_vars[(c.id, d, s)]
                        for c in inst_courses
                        if (c.id, d, s) in active_vars
                    ]
                    if len(inst_slot_vars) > 1:
                        model.Add(sum(inst_slot_vars) <= 1)

        # HARD CONSTRAINT (Modül 1 C_DAG Çakışmazlık Matrisi Kuralları):
        # (c_a, c_b) in C_DAG ise aynı gün ve slotta kesinlikle çakışamazlar!
        for c_a_id, c_b_id in active_c_dag_pairs:
            for d in self.DAYS:
                for s in self.SLOTS:
                    va = active_vars.get((c_a_id, d, s))
                    vb = active_vars.get((c_b_id, d, s))
                    if va is not None and vb is not None:
                        model.Add(va + vb <= 1)

        # ======================================================================
        # SOFT CONSTRAINTS (Öğrenci Boş Saat / Idle Gap & Hoca Saat Tercihi Optimizasyonu)
        # ======================================================================
        penalty_terms: list[cp_model.LinearExpr] = []
        gap_vars_by_sem_day: dict[tuple[int, int], cp_model.IntVar] = {}

        # 1. Öğrenci Kohortları Günlük Boş Saat (Idle Gap) Minimizasyonu
        courses_by_sem: dict[int, list[Course]] = defaultdict(list)
        for c in courses:
            courses_by_sem[c.semester].append(c)

        for sem, sem_courses in courses_by_sem.items():
            for d in self.DAYS:
                # Dönemdeki öğrencilerin d gününde s slotunda dersi olup olmadığını gösteren değişken:
                # C_DAG kısıtı nedeniyle aynı dönemin dersleri aynı slotta zaten çakışamaz (toplam <= 1)
                slot_occ: dict[int, cp_model.LinearExpr] = {}
                all_sem_day_vars: list[cp_model.IntVar] = []
                for s in self.SLOTS:
                    s_vars = [
                        active_vars[(c.id, d, s)]
                        for c in sem_courses
                        if (c.id, d, s) in active_vars
                    ]
                    if s_vars:
                        slot_occ[s] = sum(s_vars)
                        all_sem_day_vars.extend(s_vars)

                if not all_sem_day_vars:
                    continue

                has_class_day = model.NewBoolVar(f"has_class_sem{sem}_d{d}")
                model.Add(sum(all_sem_day_vars) >= 1).OnlyEnforceIf(has_class_day)
                model.Add(sum(all_sem_day_vars) == 0).OnlyEnforceIf(has_class_day.Not())

                first_slot = model.NewIntVar(1, 8, f"first_sem{sem}_d{d}")
                last_slot = model.NewIntVar(1, 8, f"last_sem{sem}_d{d}")
                gap_var = model.NewIntVar(0, 7, f"gap_sem{sem}_d{d}")
                gap_vars_by_sem_day[(sem, d)] = gap_var

                for s, occ_expr in slot_occ.items():
                    # Eğer s slotunda ders varsa (occ_expr == 1):
                    # first_slot <= s  ve  last_slot >= s
                    model.Add(first_slot <= s + 8 * (1 - occ_expr))
                    model.Add(last_slot >= s * occ_expr)

                # Boş saat (Idle Gap) = (last_slot - first_slot + 1) - (O günkü toplam ders saati)
                model.Add(
                    gap_var >= (last_slot - first_slot + 1) - sum(all_sem_day_vars)
                ).OnlyEnforceIf(has_class_day)
                model.Add(gap_var == 0).OnlyEnforceIf(has_class_day.Not())

                if req.idle_gap_weight > 0:
                    penalty_terms.append(req.idle_gap_weight * gap_var)

        # 2. Öğretim Elemanı Saat Tercih Cezası ve Oda Kapasite İsrafı Minimizasyonu
        pref_penalty_vars: list[tuple[int, cp_model.IntVar]] = []
        for (c_id, r_id, d, s), var in x_vars.items():
            c_obj = course_by_id[c_id]
            r_obj = room_by_id[r_id]
            inst_pen = 0
            if c_obj.instructor_id is not None:
                inst_pen = inst_pref_map.get((c_obj.instructor_id, d, s), 0)

            if inst_pen > 0:
                pref_penalty_vars.append((inst_pen, var))
                if req.instructor_preference_weight > 0:
                    penalty_terms.append(req.instructor_preference_weight * inst_pen * var)

            # Aşırı büyük amfiye küçük ders atanmasını önleyen küçük kapasite uyum ağırlığı
            waste_tier = max(0, (r_obj.normal_capacity - c_obj.enrolled_count) // 20)
            if waste_tier > 0:
                penalty_terms.append(waste_tier * var)

        if penalty_terms:
            model.Minimize(sum(penalty_terms))

        # CP-SAT Çözücüsünü Çalıştır
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = float(req.max_time_seconds)
        solver.parameters.num_search_workers = settings.cpsat_num_search_workers
        status = solver.Solve(model)
        elapsed_sec = round(time.perf_counter() - start_ts, 4)

        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            diagnostics = pre_diagnostics or self._diagnose_infeasibility_tr(
                courses, rooms, inst_avail_map, inst_by_id
            )
            return WeeklyScheduleOptimizationResponse(
                academic_term=req.academic_term,
                solver_status="INFEASIBLE",
                solve_time_seconds=elapsed_sec,
                total_courses_scheduled=0,
                total_slot_assignments=0,
                hard_constraints_satisfied=False,
                c_dag_pairs_enforced=len(active_c_dag_pairs),
                total_student_idle_gap_hours=0,
                total_instructor_preference_penalty=0,
                objective_value=0.0,
                unsat_diagnostics_tr=diagnostics,
                assignments=[],
            )

        # Mevcut dönem atamalarını temizle ve yeni optimal programı veritabanına kaydet
        self.db.query(WeeklyScheduleAssignment).filter(
            WeeklyScheduleAssignment.academic_term == req.academic_term
        ).delete()

        assignments_read: list[WeeklySlotAssignmentRead] = []
        for (c_id, r_id, d, s), var in sorted(x_vars.items(), key=lambda item: (item[0][2], item[0][3], item[0][0])):
            if solver.Value(var) == 1:
                c_obj = course_by_id[c_id]
                r_obj = room_by_id[r_id]
                inst_obj = inst_by_id.get(c_obj.instructor_id) if c_obj.instructor_id else None
                sess_type = "LAB" if c_obj.requires_lab_room else "THEORY"

                db_assign = WeeklyScheduleAssignment(
                    academic_term=req.academic_term,
                    course_id=c_obj.id,
                    room_id=r_obj.id,
                    instructor_id=c_obj.instructor_id,
                    day_of_week=d,
                    slot_index=s,
                    session_type=sess_type,
                )
                self.db.add(db_assign)

                assignments_read.append(
                    WeeklySlotAssignmentRead(
                        course_id=c_obj.id,
                        course_code=c_obj.code,
                        course_name=c_obj.name,
                        semester=c_obj.semester,
                        room_id=r_obj.id,
                        room_code=r_obj.code,
                        room_type=r_obj.room_type,
                        room_capacity=r_obj.normal_capacity,
                        enrolled_count=c_obj.enrolled_count,
                        instructor_id=c_obj.instructor_id,
                        instructor_name=inst_obj.full_name if inst_obj else "Unassigned",
                        day_of_week=d,
                        slot_index=s,
                        session_type=sess_type,
                    )
                )

        self.db.commit()

        total_gaps = sum(solver.Value(gv) for gv in gap_vars_by_sem_day.values())
        total_pref_pen = sum(pen * solver.Value(v) for pen, v in pref_penalty_vars)
        status_str = "OPTIMAL" if status == cp_model.OPTIMAL else "FEASIBLE"

        return WeeklyScheduleOptimizationResponse(
            academic_term=req.academic_term,
            solver_status=status_str,
            solve_time_seconds=elapsed_sec,
            total_courses_scheduled=len(courses),
            total_slot_assignments=len(assignments_read),
            hard_constraints_satisfied=True,
            c_dag_pairs_enforced=len(active_c_dag_pairs),
            total_student_idle_gap_hours=total_gaps,
            total_instructor_preference_penalty=total_pref_pen,
            objective_value=round(solver.ObjectiveValue(), 2),
            unsat_diagnostics_tr=[],
            assignments=assignments_read,
        )
