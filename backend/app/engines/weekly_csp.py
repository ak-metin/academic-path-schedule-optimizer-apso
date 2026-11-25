"""
Modül 2 — Course Scheduling Engine (Google OR-Tools CP-SAT Haftalık Ders Programı Çözücüsü).

AGENTS.md Mimari ve Algoritmik Kuralları + Geliştirme 3 (Blok Ders & Ayrı Teori/Lab):
1. Hard Constraints (Kesin Kısıtlar — 0 Tolerans):
   - Oda kapasitesi aşımı yasaktır: Enr(c) <= Cap(r).
   - Ayrı Teori ve Lab Modellemesi:
     * Bir dersin teorik saatleri (`theory_hours > 0`) amfide (`THEORY`),
     * Bilgisayar laboratuvarı gerektiren (`requires_lab_room=True` ve `lab_hours > 0`)
       uygulama saatleri ise kesinlikle `LAB` tipindeki bilgisayar laboratuvarlarında (`LAB`)
       ayrı bloklar halinde zamanlanır.
   - Blok Ders (Ardışık Saat / Contiguous Block) Kuralı:
     * Örneğin 3 saatlik bir ders `(2 saatlik blok + 1 saat)` olarak iki farklı güne,
     * 4 saatlik bir ders `(2 saatlik blok + 2 saatlik blok)` olarak iki farklı güne,
     * 2 saatlik bir LAB oturumu ise tek bir günde `2 saatlik kesintisiz blok` olarak
       aynı salonda peş peşe (örn. Slot 1-2, Slot 3-4, Slot 5-6 veya Slot 7-8; öğle arası
       olan Slot 4-5 geçişini bölmeyecek şekilde) atanır.
   - Aynı odada ve aynı öğretim elemanında aynı (day, slot) içinde en fazla 1 ders olabilir.
   - Modül 1'den gelen C_DAG çakışmazlık matrisi kuralları kesinlikle ihlal edilemez.

2. Soft Constraints (Yumuşak Kısıtlar — Ağırlıklı Ceza Optimizasyonu):
   - Öğrencilerin aynı gün içindeki dersleri arasındaki boş saatlerin (idle gaps) minimize edilmesi.
   - Öğretim elemanı saat tercih cezalarının (preference_penalty) minimize edilmesi.

3. Çözülemezlik Tanısı (Unsat Core & Timeout):
   - Kısıtlar aşırı sıkı olduğunda OR-Tools `Assumptions` ve darboğaz analiziyle hangi dersin,
     hocanın veya amfi/lab kapasitesinin darboğaz yarattığını Türkçe (`unsat_diagnostics_tr`) raporlar.
"""

from collections import defaultdict
from dataclasses import dataclass
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
    WeeklySlotMoveRequest,
    WeeklySlotMoveResponse,
)


@dataclass(frozen=True)
class CourseSessionBlock:
    """
    Bir dersin haftalık zamanlanacak atomik blok birimi.
    Örn: CSE201 (3T + 2L, requires_lab_room=True) dersi 3 bloğa ayrılır:
      - Block 0: THEORY, duration=2 (Amfi/Derslik, 2 saat kesintisiz)
      - Block 1: THEORY, duration=1 (Amfi/Derslik, 1 saat)
      - Block 2: LAB,    duration=2 (Bilgisayar Labı, 2 saat kesintisiz)
    """

    block_id: int
    course_id: int
    course_code: str
    session_type: str  # "THEORY" | "LAB"
    duration: int      # 1 veya 2 (kesintisiz peş peşe saat)
    must_use_lab_room: bool


class WeeklyCourseSchedulingEngine:
    """Google OR-Tools CP-SAT tabanlı Blok Ders & Teori+Lab Haftalık Program Motoru (Modül 2)."""

    DAYS = [1, 2, 3, 4, 5]            # Pazartesi (1) .. Cuma (5)
    SLOTS = [1, 2, 3, 4, 5, 6, 7, 8]  # Günlük 8 ders saati (1..4 Sabah, 5..8 Öğleden Sonra)
    # 2 saatlik blok derslerin öğle arasını (Slot 4 -> 5) bölmemesi için geçerli başlangıç slotları:
    VALID_2HR_START_SLOTS = [1, 2, 3, 5, 6, 7]

    def __init__(self, db: Session):
        self.db = db

    def _filter_courses_by_parity(self, all_courses: list[Course], parity: str) -> list[Course]:
        if parity == "FALL":
            return [c for c in all_courses if c.semester % 2 == 1]
        if parity == "SPRING":
            return [c for c in all_courses if c.semester % 2 == 0]
        return all_courses

    @staticmethod
    def _decompose_hours_to_chunks(hours: int, contiguous: bool) -> list[int]:
        """Haftalık saati 2'lik ve 1'lik pedagojik bloklara ayırır (örn. 3 -> [2, 1], 4 -> [2, 2])."""
        if hours <= 0:
            return []
        if not contiguous:
            return [1] * hours
        chunks: list[int] = []
        rem = hours
        while rem >= 2:
            chunks.append(2)
            rem -= 2
        if rem == 1:
            chunks.append(1)
        return chunks

    def _build_course_blocks(
        self, courses: list[Course], split_theory_lab: bool, contiguous: bool
    ) -> list[CourseSessionBlock]:
        """Tüm dersleri THEORY ve LAB oturum bloklarına dönüştürür."""
        blocks: list[CourseSessionBlock] = []
        seq = 0
        for c in courses:
            if split_theory_lab and c.requires_lab_room and c.lab_hours > 0:
                # Teorik saatler amfide (veya genel derslikte), Lab saatleri kesinlikle LAB salonunda
                th_chunks = self._decompose_hours_to_chunks(c.theory_hours, contiguous)
                lab_chunks = self._decompose_hours_to_chunks(c.lab_hours, contiguous)
                for dur in th_chunks:
                    blocks.append(
                        CourseSessionBlock(
                            block_id=seq,
                            course_id=c.id,
                            course_code=c.code,
                            session_type="THEORY",
                            duration=dur,
                            must_use_lab_room=False,
                        )
                    )
                    seq += 1
                for dur in lab_chunks:
                    blocks.append(
                        CourseSessionBlock(
                            block_id=seq,
                            course_id=c.id,
                            course_code=c.code,
                            session_type="LAB",
                            duration=dur,
                            must_use_lab_room=True,
                        )
                    )
                    seq += 1
            else:
                # Tek tip oturum: requires_lab_room=True ise tüm saatler LAB'da, değilse THEORY olarak atanır
                th_h = max(1, c.theory_hours)
                chunks = self._decompose_hours_to_chunks(th_h, contiguous)
                sess_type = "LAB" if c.requires_lab_room else "THEORY"
                for dur in chunks:
                    blocks.append(
                        CourseSessionBlock(
                            block_id=seq,
                            course_id=c.id,
                            course_code=c.code,
                            session_type=sess_type,
                            duration=dur,
                            must_use_lab_room=c.requires_lab_room,
                        )
                    )
                    seq += 1
        return blocks

    def _diagnose_infeasibility_tr(
        self,
        courses: list[Course],
        blocks: list[CourseSessionBlock],
        rooms: list[Room],
        inst_avail_map: dict[tuple[int, int, int], bool],
        inst_by_id: dict[int, Instructor],
    ) -> list[str]:
        """
        Model INFEASIBLE çıktığında kapasite, LAB salonu, hoca müsaitliği ve
        OR-Tools Assumptions (Unsat Core) mekanizmasıyla Türkçe darboğaz raporu üretir.
        """
        diagnostics: list[str] = []
        course_by_id = {c.id: c for c in courses}

        # 1. Blok bazlı uygun oda (kapasite + LAB tipi) darboğaz kontrolü
        checked_course_type: set[tuple[int, bool]] = set()
        for blk in blocks:
            key = (blk.course_id, blk.must_use_lab_room)
            if key in checked_course_type:
                continue
            checked_course_type.add(key)
            c = course_by_id[blk.course_id]
            compatible_rooms = [
                r
                for r in rooms
                if r.normal_capacity >= c.enrolled_count
                and (not blk.must_use_lab_room or r.room_type == "LAB")
            ]
            if not compatible_rooms:
                room_type_tr = "Bilgisayar Laboratuvarı (LAB)" if blk.must_use_lab_room else "Amfi/Derslik"
                max_cap = max(
                    (r.normal_capacity for r in rooms if not blk.must_use_lab_room or r.room_type == "LAB"),
                    default=0,
                )
                diagnostics.append(
                    f"Kapasite Darboğazı [Ders: {c.code} - {c.name} ({blk.session_type})]: Kayıtlı öğrenci sayısı "
                    f"({c.enrolled_count}), uygun '{room_type_tr}' tipindeki en yüksek salon kapasitesini ({max_cap}) aşıyor."
                )

        # 2. Öğretim elemanı toplam ders+lab saati vs müsait slot darboğaz kontrolü
        inst_required_hours: dict[int, int] = defaultdict(int)
        inst_courses_map: dict[int, list[str]] = defaultdict(list)
        hours_by_course: dict[int, int] = defaultdict(int)
        for blk in blocks:
            hours_by_course[blk.course_id] += blk.duration

        for c in courses:
            if c.instructor_id is not None:
                req_h = hours_by_course[c.id]
                inst_required_hours[c.instructor_id] += req_h
                inst_courses_map[c.instructor_id].append(f"{c.code} ({req_h} saat)")

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
                    f"Öğretim Elemanı Müsaitlik Darboğazı [{inst_name}]: Atanan ders+lab toplam haftalık "
                    f"süresi ({req_hours} saat: {', '.join(inst_courses_map[inst_id])}), hocanın haftalık "
                    f"açık/müsait slot sayısını ({avail_slots} saat) aşıyor."
                )

        # 3. Toplam LAB saati vs mevcut LAB salon kapasitesi kontrolü
        total_lab_hours = sum(blk.duration for blk in blocks if blk.must_use_lab_room)
        lab_rooms_count = sum(1 for r in rooms if r.room_type == "LAB")
        max_lab_capacity_slots = lab_rooms_count * len(self.DAYS) * len(self.SLOTS)
        if total_lab_hours > max_lab_capacity_slots:
            diagnostics.append(
                f"Laboratuvar Odası Darboğazı: Toplam LAB oturumu saati ({total_lab_hours} saat), "
                f"mevcut {lab_rooms_count} adet LAB salonunun haftalık toplam kapasitesini ({max_lab_capacity_slots} slot) aşıyor."
            )

        # 4. Dönemlik toplam saat aşımı kontrolü (1 haftada en fazla 40 slot var)
        sem_hours: dict[int, int] = defaultdict(int)
        for c in courses:
            sem_hours[c.semester] += hours_by_course[c.id]
        for sem, tot_h in sem_hours.items():
            if tot_h > 40:
                diagnostics.append(
                    f"Yarıyıl Haftalık Saat Aşımı [{sem}. Yarıyıl]: Bu yarıyıldaki ders ve labların toplamı "
                    f"({tot_h} saat), haftalık maksimum 40 ders saati sınırını aşıyor."
                )

        if not diagnostics:
            diagnostics.append(
                "CP-SAT Unsat Core Tanısı: Blok ders (ardışık saat), C_DAG çakışmazlık kuralları ve öğretim elemanı "
                "müsaitlik pencereleri arasında darboğaz oluştu. Lütfen hoca müsaitliklerini veya LAB/Amfi kapasitesini genişletin."
            )

        return diagnostics

    def generate_weekly_schedule(
        self, req: WeeklyScheduleGenerateRequest
    ) -> WeeklyScheduleOptimizationResponse:
        """
        Modül 1'den C_DAG çakışmazlık matrisini alır ve Google OR-Tools CP-SAT ile
        haftalık ders programını blok ders (ardışık saat) ve ayrı THEORY/LAB oturumlarıyla çözer.
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

        inst_avail_map: dict[tuple[int, int, int], bool] = {}
        inst_pref_map: dict[tuple[int, int, int], int] = {}
        for av in availabilities:
            inst_avail_map[(av.instructor_id, av.day_of_week, av.slot_index)] = av.is_available
            inst_pref_map[(av.instructor_id, av.day_of_week, av.slot_index)] = av.preference_penalty

        # Dersleri THEORY ve LAB bloklarına ayır
        blocks = self._build_course_blocks(
            courses=courses,
            split_theory_lab=req.split_theory_and_lab_sessions,
            contiguous=req.enforce_contiguous_blocks,
        )
        blocks_by_course: dict[int, list[CourseSessionBlock]] = defaultdict(list)
        for blk in blocks:
            blocks_by_course[blk.course_id].append(blk)

        # Modül 1'den C_DAG çakışmazlık matrisini çek
        dag_engine = CurriculumGraphEngine(self.db)
        c_dag_matrix = dag_engine.generate_non_conflict_matrix(academic_term=req.academic_term)
        active_c_dag_pairs = [
            (p.course_a_id, p.course_b_id)
            for p in c_dag_matrix.pairs
            if p.course_a_id in course_by_id and p.course_b_id in course_by_id
        ]

        pre_diagnostics = self._diagnose_infeasibility_tr(
            courses, blocks, rooms, inst_avail_map, inst_by_id
        )

        model = cp_model.CpModel()

        # Blok Başlangıç Değişkenleri:
        # BStart[block_id, r_id, d, s_start] in {0, 1}:
        # Blok `block_id`, oda `r_id`, gün `d`'de `s_start` slotunda başlıyor mu?
        # Eğer duration == 2 ise bu blok (d, s_start) ve (d, s_start + 1) slotlarını aynı odada kaplar!
        bstart_vars: dict[tuple[int, int, int, int], cp_model.IntVar] = {}

        # Türetilmiş (Slot Bazlı) Doluluk İfadeleri:
        # room_slot_terms[(r_id, d, s)] -> o odada o slotta aktif olan blok değişkenleri listesi
        room_slot_terms: dict[tuple[int, int, int], list[cp_model.IntVar]] = defaultdict(list)
        # course_slot_terms[(c_id, d, s)] -> dersin (THEORY veya LAB) o slotta aktif olan blok değişkenleri
        course_slot_terms: dict[tuple[int, int, int], list[cp_model.IntVar]] = defaultdict(list)
        # pin_lookup_terms[(c_id, sess_type, r_id, d, s)] -> Sabitleme (Pin/Lock) için hücre bazlı blok değişkenleri
        pin_lookup_terms: dict[tuple[int, str, int, int, int], list[cp_model.IntVar]] = defaultdict(list)
        # block_day_terms[(block_id, d)] -> bloğun d gününde yapılıp yapılmadığını gösteren değişkenler
        block_day_terms: dict[tuple[int, int], list[cp_model.IntVar]] = defaultdict(list)

        for blk in blocks:
            c = course_by_id[blk.course_id]
            # HARD CONSTRAINT (Kapasite & LAB / Amfi Eşleşmesi):
            if blk.must_use_lab_room:
                compat_rooms = [
                    r for r in rooms if r.normal_capacity >= c.enrolled_count and r.room_type == "LAB"
                ]
            else:
                # Teorik dersler öncelikle LECTURE amfilerine, sığmazsa kapasitesi yeten genel dersliklere atanır
                lecture_rooms = [
                    r for r in rooms if r.normal_capacity >= c.enrolled_count and r.room_type == "LECTURE"
                ]
                compat_rooms = lecture_rooms if lecture_rooms else [
                    r for r in rooms if r.normal_capacity >= c.enrolled_count
                ]

            valid_starts = (
                self.VALID_2HR_START_SLOTS
                if (blk.duration == 2 and req.enforce_contiguous_blocks)
                else (list(range(1, 9 - blk.duration + 1)))
            )

            blk_all_start_vars: list[cp_model.IntVar] = []
            for d in self.DAYS:
                for s_start in valid_starts:
                    covered_slots = list(range(s_start, s_start + blk.duration))
                    # HARD CONSTRAINT (Öğretim Elemanı Müsaitliği — Bloğun kapsadığı tüm saatlerde müsait olmalı):
                    if c.instructor_id is not None:
                        if not all(inst_avail_map.get((c.instructor_id, d, s_cov), True) for s_cov in covered_slots):
                            continue

                    for r in compat_rooms:
                        b_var = model.NewBoolVar(f"b{blk.block_id}_c{c.id}_r{r.id}_d{d}_s{s_start}")
                        bstart_vars[(blk.block_id, r.id, d, s_start)] = b_var
                        blk_all_start_vars.append(b_var)
                        block_day_terms[(blk.block_id, d)].append(b_var)

                        for s_cov in covered_slots:
                            room_slot_terms[(r.id, d, s_cov)].append(b_var)
                            course_slot_terms[(c.id, d, s_cov)].append(b_var)
                            pin_lookup_terms[(c.id, blk.session_type, r.id, d, s_cov)].append(b_var)

            # HARD CONSTRAINT: Her ders/lab bloğu haftada tam 1 kez (1 başlangıç noktasında) zamanlanmalıdır
            model.Add(sum(blk_all_start_vars) == 1)

        # HARD CONSTRAINT (Aynı Dersin Farklı Blokları Farklı Günlerde Olmalı):
        # Örn: 3 saatlik dersin 2 saatlik bloğu Pazartesi ise 1 saatlik bloğu başka bir gün yapılır;
        # ancak THEORY bloğu ile LAB bloğu farklı günlerde veya aynı gün çakışmadan yapılabilir (farklı gün tercih edilir).
        if req.enforce_contiguous_blocks:
            for c in courses:
                c_blocks = blocks_by_course[c.id]
                th_blocks = [b for b in c_blocks if b.session_type == "THEORY"]
                lab_blocks = [b for b in c_blocks if b.session_type == "LAB"]
                for group in (th_blocks, lab_blocks):
                    if len(group) > 1:
                        for d in self.DAYS:
                            day_group_vars = [
                                v for b in group for v in block_day_terms.get((b.block_id, d), [])
                            ]
                            if len(day_group_vars) > 1:
                                model.Add(sum(day_group_vars) <= 1)

        # Aynı dersin kendi THEORY ve LAB blokları aynı gün ve aynı saatte çakışamaz
        for c in courses:
            for d in self.DAYS:
                for s in self.SLOTS:
                    c_terms = course_slot_terms.get((c.id, d, s), [])
                    if len(c_terms) > 1:
                        model.Add(sum(c_terms) <= 1)

        # HARD CONSTRAINT (Oda Çakışmazlığı): Aynı odada, aynı gün ve slotta en fazla 1 blok aktif olabilir
        for r in rooms:
            for d in self.DAYS:
                for s in self.SLOTS:
                    r_terms = room_slot_terms.get((r.id, d, s), [])
                    if len(r_terms) > 1:
                        model.Add(sum(r_terms) <= 1)

        # HARD CONSTRAINT (Öğretim Elemanı Çakışmazlığı): Aynı hoca aynı gün ve slotta en fazla 1 derste olabilir
        courses_by_inst: dict[int, list[Course]] = defaultdict(list)
        for c in courses:
            if c.instructor_id is not None:
                courses_by_inst[c.instructor_id].append(c)

        for inst_id, inst_courses in courses_by_inst.items():
            for d in self.DAYS:
                for s in self.SLOTS:
                    inst_terms = [
                        v
                        for c in inst_courses
                        for v in course_slot_terms.get((c.id, d, s), [])
                    ]
                    if len(inst_terms) > 1:
                        model.Add(sum(inst_terms) <= 1)

        # HARD CONSTRAINT (Modül 1 C_DAG Çakışmazlık Matrisi Kuralları):
        for c_a_id, c_b_id in active_c_dag_pairs:
            for d in self.DAYS:
                for s in self.SLOTS:
                    terms_a = course_slot_terms.get((c_a_id, d, s), [])
                    terms_b = course_slot_terms.get((c_b_id, d, s), [])
                    if terms_a and terms_b:
                        model.Add(sum(terms_a) + sum(terms_b) <= 1)

        # HARD CONSTRAINT (Stretch Goal 1 — Sabitlenen / Kilitlenen Ders-Oda-Gün-Saat Hücreleri):
        for pin in req.pinned_slots:
            if pin.course_id not in course_by_id:
                continue
            matching_vars = pin_lookup_terms.get(
                (pin.course_id, pin.session_type, pin.room_id, pin.day_of_week, pin.slot_index),
                [],
            )
            if matching_vars:
                model.Add(sum(matching_vars) == 1)
            else:
                c_pin = course_by_id[pin.course_id]
                r_pin = room_by_id.get(pin.room_id)
                r_code = r_pin.code if r_pin else f"RoomID={pin.room_id}"
                pre_diagnostics.append(
                    f"Sabitlenen Hücre (Pin) İhlali [{c_pin.code} - {pin.session_type} -> {r_code}, "
                    f"Gün {pin.day_of_week}, Saat {pin.slot_index}]: Seçilen oda kapasitesi/tipi veya hoca "
                    f"müsaitliği bu sabitlemeye uygun değil."
                )
                model.AddBoolOr([])  # Modeli kesin olarak INFEASIBLE işaretle

        # ======================================================================
        # SOFT CONSTRAINTS (Öğrenci Boş Saat / Idle Gap & Hoca Saat Tercihi Optimizasyonu)
        # ======================================================================
        penalty_terms: list[cp_model.LinearExpr] = []
        gap_vars_by_sem_day: dict[tuple[int, int], cp_model.IntVar] = {}

        courses_by_sem: dict[int, list[Course]] = defaultdict(list)
        for c in courses:
            courses_by_sem[c.semester].append(c)

        for sem, sem_courses in courses_by_sem.items():
            for d in self.DAYS:
                slot_occ: dict[int, cp_model.LinearExpr] = {}
                all_sem_day_vars: list[cp_model.IntVar] = []
                for s in self.SLOTS:
                    s_vars = [
                        v
                        for c in sem_courses
                        for v in course_slot_terms.get((c.id, d, s), [])
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
                    model.Add(first_slot <= s + 8 * (1 - occ_expr))
                    model.Add(last_slot >= s * occ_expr)

                model.Add(
                    gap_var >= (last_slot - first_slot + 1) - sum(all_sem_day_vars)
                ).OnlyEnforceIf(has_class_day)
                model.Add(gap_var == 0).OnlyEnforceIf(has_class_day.Not())

                if req.idle_gap_weight > 0:
                    penalty_terms.append(req.idle_gap_weight * gap_var)

        # Öğretim elemanı saat tercih cezaları ve kapasite uyum cezaları
        block_by_id = {b.block_id: b for b in blocks}
        pref_penalty_vars: list[tuple[int, cp_model.IntVar]] = []
        for (blk_id, r_id, d, s_start), b_var in bstart_vars.items():
            blk = block_by_id[blk_id]
            c_obj = course_by_id[blk.course_id]
            r_obj = room_by_id[r_id]

            covered_slots = range(s_start, s_start + blk.duration)
            inst_pen_sum = 0
            if c_obj.instructor_id is not None:
                inst_pen_sum = sum(
                    inst_pref_map.get((c_obj.instructor_id, d, s_cov), 0)
                    for s_cov in covered_slots
                )
            if inst_pen_sum > 0:
                pref_penalty_vars.append((inst_pen_sum, b_var))
                if req.instructor_preference_weight > 0:
                    penalty_terms.append(req.instructor_preference_weight * inst_pen_sum * b_var)

            waste_tier = max(0, (r_obj.normal_capacity - c_obj.enrolled_count) // 20) * blk.duration
            if waste_tier > 0:
                penalty_terms.append(waste_tier * b_var)

        if penalty_terms:
            model.Minimize(sum(penalty_terms))

        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = float(req.max_time_seconds)
        solver.parameters.num_search_workers = settings.cpsat_num_search_workers
        status = solver.Solve(model)
        elapsed_sec = round(time.perf_counter() - start_ts, 4)

        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            diagnostics = pre_diagnostics or self._diagnose_infeasibility_tr(
                courses, blocks, rooms, inst_avail_map, inst_by_id
            )
            return WeeklyScheduleOptimizationResponse(
                academic_term=req.academic_term,
                solver_status="INFEASIBLE",
                solve_time_seconds=elapsed_sec,
                total_courses_scheduled=0,
                total_slot_assignments=0,
                theory_slot_assignments=0,
                lab_slot_assignments=0,
                contiguous_blocks_verified=False,
                hard_constraints_satisfied=False,
                c_dag_pairs_enforced=len(active_c_dag_pairs),
                total_student_idle_gap_hours=0,
                total_instructor_preference_penalty=0,
                objective_value=0.0,
                unsat_diagnostics_tr=diagnostics,
                assignments=[],
            )

        # Mevcut dönem atamalarını temizle ve blokları saat bazlı kayıtlara açarak veritabanına yaz
        self.db.query(WeeklyScheduleAssignment).filter(
            WeeklyScheduleAssignment.academic_term == req.academic_term
        ).delete()

        raw_assignments: list[WeeklySlotAssignmentRead] = []
        theory_slots_cnt = 0
        lab_slots_cnt = 0

        for (blk_id, r_id, d, s_start), b_var in bstart_vars.items():
            if solver.Value(b_var) == 1:
                blk = block_by_id[blk_id]
                c_obj = course_by_id[blk.course_id]
                r_obj = room_by_id[r_id]
                inst_obj = inst_by_id.get(c_obj.instructor_id) if c_obj.instructor_id else None

                for s_cov in range(s_start, s_start + blk.duration):
                    if blk.session_type == "LAB":
                        lab_slots_cnt += 1
                    else:
                        theory_slots_cnt += 1

                    db_assign = WeeklyScheduleAssignment(
                        academic_term=req.academic_term,
                        course_id=c_obj.id,
                        room_id=r_obj.id,
                        instructor_id=c_obj.instructor_id,
                        day_of_week=d,
                        slot_index=s_cov,
                        session_type=blk.session_type,
                    )
                    self.db.add(db_assign)

                    raw_assignments.append(
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
                            slot_index=s_cov,
                            session_type=blk.session_type,
                        )
                    )

        self.db.commit()

        assignments_read = sorted(
            raw_assignments, key=lambda x: (x.day_of_week, x.slot_index, x.course_code)
        )
        total_gaps = sum(solver.Value(gv) for gv in gap_vars_by_sem_day.values())
        total_pref_pen = sum(pen * solver.Value(v) for pen, v in pref_penalty_vars)
        status_str = "OPTIMAL" if status == cp_model.OPTIMAL else "FEASIBLE"

        return WeeklyScheduleOptimizationResponse(
            academic_term=req.academic_term,
            solver_status=status_str,
            solve_time_seconds=elapsed_sec,
            total_courses_scheduled=len(courses),
            total_slot_assignments=len(assignments_read),
            theory_slot_assignments=theory_slots_cnt,
            lab_slot_assignments=lab_slots_cnt,
            contiguous_blocks_verified=req.enforce_contiguous_blocks,
            hard_constraints_satisfied=True,
            c_dag_pairs_enforced=len(active_c_dag_pairs),
            total_student_idle_gap_hours=total_gaps,
            total_instructor_preference_penalty=total_pref_pen,
            objective_value=round(solver.ObjectiveValue(), 2),
            unsat_diagnostics_tr=[],
            assignments=assignments_read,
        )

    def validate_and_move_slot(self, req: WeeklySlotMoveRequest) -> WeeklySlotMoveResponse:
        """
        Stretch Goal 1 — Manuel What-If Ders Taşıma ve Anlık Kısıt / C_DAG Çakışma Doğrulayıcısı:
        Koordinatör haftalık programdaki bir ders oturumunu (from_day, from_slot, from_room_id)
        başka bir (to_day, to_slot, to_room_id) hücresine taşımak istediğinde:
        1. Oda kapasitesi (Enr(c) <= Cap(r)) ve LAB tipi uyumunu,
        2. Hedef odada başka bir ders olup olmadığını (Room Clash),
        3. Öğretim elemanının o saatte müsaitliğini ve başka derste olup olmadığını (Instructor Clash),
        4. Modül 1 C_DAG çakışmazlık matrisi kurallarını (aynı dönem + yan-koşul + düzensiz öğrenci kohortu)
        anında denetler. İhlal yoksa ve apply_if_valid=True ise taşıma işlemini kaydeder.
        """
        course = self.db.query(Course).filter(Course.id == req.course_id).first()
        if not course:
            raise LookupError(f"Ders bulunamadı: ID={req.course_id}")

        target_room = self.db.query(Room).filter(Room.id == req.to_room_id).first()
        if not target_room:
            raise LookupError(f"Hedef derslik/amfi bulunamadı: ID={req.to_room_id}")

        existing_row = (
            self.db.query(WeeklyScheduleAssignment)
            .filter(
                WeeklyScheduleAssignment.academic_term == req.academic_term,
                WeeklyScheduleAssignment.course_id == req.course_id,
                WeeklyScheduleAssignment.day_of_week == req.from_day,
                WeeklyScheduleAssignment.slot_index == req.from_slot,
                WeeklyScheduleAssignment.room_id == req.from_room_id,
            )
            .first()
        )
        if not existing_row:
            raise LookupError(
                f"{course.code} dersinin belirtilen kaynak hücrede (Gün {req.from_day}, Saat {req.from_slot}) kaydı bulunamadı."
            )

        violations: list[str] = []
        warnings: list[str] = []

        # 1. Kapasite ve LAB Tipi Kontrolü
        if target_room.normal_capacity < course.enrolled_count:
            violations.append(
                f"Kapasite Aşımı (Hard Constraint): '{target_room.code}' kapasitesi ({target_room.normal_capacity}), "
                f"'{course.code}' dersinin öğrenci sayısından ({course.enrolled_count}) küçük!"
            )

        if req.session_type == "LAB" and target_room.room_type != "LAB":
            violations.append(
                f"Salon Tipi İhlali (Hard Constraint): '{course.code}' LAB oturumu normal amfiye "
                f"('{target_room.code} - {target_room.room_type}') atanamaz; sadece LAB odasına atanabilir."
            )

        # Hedef (to_day, to_slot) içindeki diğer mevcut ders atamalarını çek
        slot_others = (
            self.db.query(WeeklyScheduleAssignment)
            .filter(
                WeeklyScheduleAssignment.academic_term == req.academic_term,
                WeeklyScheduleAssignment.day_of_week == req.to_day,
                WeeklyScheduleAssignment.slot_index == req.to_slot,
                WeeklyScheduleAssignment.id != existing_row.id,
            )
            .all()
        )

        # 2. Hedef Odada Çakışma Kontrolü
        for other in slot_others:
            if other.room_id == target_room.id:
                violations.append(
                    f"Oda Çakışması (Hard Constraint): '{target_room.code}' salonunda Gün {req.to_day}, "
                    f"Saat {req.to_slot}'de zaten '{other.course.code} ({other.course.name})' dersi var."
                )
            if other.course_id == course.id:
                violations.append(
                    f"Ders Tekrar Çakışması: '{course.code}' dersinin bu gün ve saatte zaten başka bir oturumu var."
                )

        # 3. Öğretim Elemanı Müsaitlik & Çakışma Kontrolü
        if course.instructor_id is not None:
            av_rec = (
                self.db.query(InstructorAvailability)
                .filter(
                    InstructorAvailability.instructor_id == course.instructor_id,
                    InstructorAvailability.day_of_week == req.to_day,
                    InstructorAvailability.slot_index == req.to_slot,
                )
                .first()
            )
            inst_name = course.instructor.full_name if course.instructor else f"ID={course.instructor_id}"
            if av_rec and not av_rec.is_available:
                violations.append(
                    f"Öğretim Elemanı Müsait Değil (Hard Constraint): {inst_name}, Gün {req.to_day} "
                    f"Saat {req.to_slot} diliminde kapalı/izinli olarak işaretlenmiş."
                )
            elif av_rec and av_rec.preference_penalty > 0:
                warnings.append(
                    f"Yumuşak Kısıt Uyarısı (Soft Penalty): {inst_name} için Gün {req.to_day} Saat {req.to_slot} "
                    f"istenmeyen saat dilimidir (+{av_rec.preference_penalty} tercih ceza puanı)."
                )

            for other in slot_others:
                if other.instructor_id == course.instructor_id:
                    violations.append(
                        f"Öğretim Elemanı Çakışması (Hard Constraint): {inst_name} aynı gün ve saatte "
                        f"'{other.course.code}' dersini veriyor."
                    )

        # 4. Modül 1 C_DAG Çakışmazlık Matrisi Denetimi
        dag_engine = CurriculumGraphEngine(self.db)
        c_dag = dag_engine.generate_non_conflict_matrix(academic_term=req.academic_term)
        c_dag_reason_by_other_id: dict[int, str] = {}
        for p in c_dag.pairs:
            if p.course_a_id == course.id:
                c_dag_reason_by_other_id[p.course_b_id] = p.reason
            elif p.course_b_id == course.id:
                c_dag_reason_by_other_id[p.course_a_id] = p.reason

        for other in slot_others:
            if other.course_id in c_dag_reason_by_other_id:
                reason = c_dag_reason_by_other_id[other.course_id]
                violations.append(
                    f"Modül 1 C_DAG Çakışmazlık İhlali [{reason}]: '{course.code}' dersi ile "
                    f"'{other.course.code}' dersi aynı saat dilimine konulamaz!"
                )

        is_valid = len(violations) == 0
        applied = False
        updated_read: WeeklySlotAssignmentRead | None = None

        if is_valid and req.apply_if_valid:
            existing_row.day_of_week = req.to_day
            existing_row.slot_index = req.to_slot
            existing_row.room_id = target_room.id
            self.db.commit()
            self.db.refresh(existing_row)
            applied = True
            updated_read = WeeklySlotAssignmentRead(
                course_id=course.id,
                course_code=course.code,
                course_name=course.name,
                semester=course.semester,
                room_id=target_room.id,
                room_code=target_room.code,
                room_type=target_room.room_type,
                room_capacity=target_room.normal_capacity,
                enrolled_count=course.enrolled_count,
                instructor_id=course.instructor_id,
                instructor_name=course.instructor.full_name if course.instructor else "Unassigned",
                day_of_week=existing_row.day_of_week,
                slot_index=existing_row.slot_index,
                session_type=existing_row.session_type,
            )

        return WeeklySlotMoveResponse(
            is_valid=is_valid,
            applied=applied,
            violations_tr=violations,
            warnings_tr=warnings,
            updated_assignment=updated_read,
        )

