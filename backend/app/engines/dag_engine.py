"""
Modül 1 — Curriculum Graph Engine (NetworkX & DAG Analiz Motoru).

Bu modül AGENTS.md kurallarına uygun olarak şu 3 temel görevi yerine getirir:
1. Müfredatı Yönlü Çevrimsiz Graf (Directed Acyclic Graph - DAG) olarak modeller.
   Yeni bir önkoşul (prerequisite) eklenirken çevrim kontrolü (cycle detection)
   ve topolojik sıralama yapar; döngüsel bağımlılık (A -> B -> A) varsa işlemi
   anlaşılır Türkçe tanı mesajı ve HTTP 422 hatası ile reddeder.
2. Öğrenci ders kalma simülasyonlarında (Critical Path Analysis), öğrencinin
   kaldığı dersin kilitlediği tüm alt/üst dönem derslerini (transitive closure)
   ve dönemlik AKTS (ECTS) üst sınırlarını (normal 30 AKTS, kurtarma senaryosu
   40 AKTS) hesaba katarak mezuniyet gecikmesini dönem dönem simüle eder.
3. Modül 2'nin (Weekly Course Scheduling Engine) doğrudan zorunlu girdisi olan
   Çakışmazlık Matrisini (C_DAG) üretir:
   - Aynı dönem zorunlu ders çiftleri (SAME_SEMESTER_MANDATORY),
   - Yan-koşul ders çiftleri (COREQUISITE),
   - Alttan ders alan düzensiz (irregular) öğrencilerin en sık birlikte aldığı
     kritik ders çiftleri (IRREGULAR_RETAKE_COHORT).
"""

from collections import defaultdict
from itertools import combinations
import networkx as nx
from sqlalchemy.orm import Session

from app.config import settings
from app.models.academic import Course, CoursePrerequisite, Enrollment, Student
from app.schemas.academic import (
    CourseGraphNodeMetric,
    CurriculumGraphAnalysisResponse,
    FailureSimulationRequest,
    FailureSimulationResponse,
    NonConflictMatrixResponse,
    NonConflictPairItem,
    PrerequisiteEdgeRead,
    SimulatedSemesterPlan,
)


class CurriculumCycleError(ValueError):
    """Döngüsel önkoşul (cycle) veya geçersiz yarıyıl bağımlılığı tespit edildiğinde fırlatılır."""

    def __init__(self, message: str, cycle_path: list[str] | None = None):
        super().__init__(message)
        self.message = message
        self.cycle_path = cycle_path or []


class CurriculumGraphEngine:
    """NetworkX tabanlı Müfredat DAG, Kritik Yol (CPA) ve C_DAG Çakışmazlık Motoru."""

    def __init__(self, db: Session):
        self.db = db

    def build_dag(self) -> tuple[nx.DiGraph, dict[str, Course], dict[int, Course]]:
        """
        Veritabanındaki ders ve önkoşul kayıtlarından NetworkX DiGraph nesnesini inşa eder.
        Yalnızca kesin önkoşullar (is_corequisite=False) yönlü zaman/dönem bağımlılığı
        kenarı oluşturur; yan-koşullar (is_corequisite=True) ayrıca işaretlenir.
        """
        courses = self.db.query(Course).order_by(Course.semester.asc(), Course.code.asc()).all()
        prereqs = self.db.query(CoursePrerequisite).all()

        course_by_code: dict[str, Course] = {c.code: c for c in courses}
        course_by_id: dict[int, Course] = {c.id: c for c in courses}

        graph = nx.DiGraph()
        for c in courses:
            graph.add_node(
                c.code,
                course_id=c.id,
                name=c.name,
                semester=c.semester,
                ects=c.ects,
                is_mandatory=c.is_mandatory,
            )

        for edge in prereqs:
            u_course = course_by_id.get(edge.prerequisite_course_id)
            v_course = course_by_id.get(edge.target_course_id)
            if u_course and v_course:
                graph.add_edge(
                    u_course.code,
                    v_course.code,
                    edge_id=edge.id,
                    is_corequisite=edge.is_corequisite,
                )

        return graph, course_by_code, course_by_id

    @staticmethod
    def _compute_longest_chain_from_node(graph: nx.DiGraph, start_node: str) -> list[str]:
        """
        DAG üzerinde start_node düğümünden başlayarak aşağı yönlü en uzun önkoşul
        zincirini (Critical Path Chain: CP(u) = 1 + max_{(u,v) in E} CP(v)) hesaplar.
        """
        memo: dict[str, list[str]] = {}

        def dfs(u: str) -> list[str]:
            if u in memo:
                return memo[u]
            best_subchain: list[str] = []
            for v in sorted(graph.successors(u)):
                candidate = dfs(v)
                if len(candidate) > len(best_subchain):
                    best_subchain = candidate
            memo[u] = [u] + best_subchain
            return memo[u]

        return dfs(start_node)

    def analyze_curriculum(self) -> CurriculumGraphAnalysisResponse:
        """
        Müfredat grafının DAG geçerliliğini, topolojik sıralamasını, her dersin
        Blocking Factor (BF(u) = |Reach(u)|) ve Critical Path Length (CP(u)) değerlerini hesaplar.
        """
        graph, course_by_code, _ = self.build_dag()
        is_dag = nx.is_directed_acyclic_graph(graph)
        if not is_dag:
            cycle_edges = nx.find_cycle(graph, orientation="original")
            cycle_chain = [edge[0] for edge in cycle_edges] + [cycle_edges[0][0]]
            raise CurriculumCycleError(
                f"Müfredat grafında döngüsel önkoşul (cycle) tespit edildi: {' -> '.join(cycle_chain)}",
                cycle_path=cycle_chain,
            )

        topo_order = list(nx.lexicographical_topological_sort(graph))
        node_metrics: list[CourseGraphNodeMetric] = []
        global_longest_chain: list[str] = []

        for code, course in course_by_code.items():
            direct_prereqs = sorted(graph.predecessors(code))
            direct_deps = sorted(graph.successors(code))
            transitive_deps = sorted(nx.descendants(graph, code))
            cp_chain = self._compute_longest_chain_from_node(graph, code)

            if len(cp_chain) > len(global_longest_chain):
                global_longest_chain = cp_chain

            node_metrics.append(
                CourseGraphNodeMetric(
                    course_id=course.id,
                    code=course.code,
                    name=course.name,
                    semester=course.semester,
                    ects=course.ects,
                    is_mandatory=course.is_mandatory,
                    direct_prerequisites=direct_prereqs,
                    direct_dependents=direct_deps,
                    transitive_dependents=transitive_deps,
                    blocking_factor=len(transitive_deps),
                    critical_path_length=len(cp_chain),
                    critical_path_chain=cp_chain,
                )
            )

        # En yüksek darboğaz (Blocking Factor + Critical Path) yaratan ilk 5 dersi sırala
        sorted_bottlenecks = sorted(
            node_metrics,
            key=lambda m: (m.blocking_factor, m.critical_path_length, -m.semester),
            reverse=True,
        )
        top_bottlenecks = [m.code for m in sorted_bottlenecks[:5] if m.blocking_factor > 0]

        return CurriculumGraphAnalysisResponse(
            is_valid_dag=True,
            total_nodes=graph.number_of_nodes(),
            total_edges=graph.number_of_edges(),
            longest_critical_path_length=len(global_longest_chain),
            global_critical_path=global_longest_chain,
            top_bottleneck_courses=top_bottlenecks,
            topological_order=topo_order,
            nodes=node_metrics,
        )

    def add_prerequisite_with_cycle_check(
        self, prerequisite_code: str, target_code: str, is_corequisite: bool = False
    ) -> PrerequisiteEdgeRead:
        """
        Veritabanına yeni bir önkoşul/yan-koşul eklemeden önce:
        1. Ders kodlarının varlığını kontrol eder,
        2. Kendine önkoşul (self-loop: A -> A) ve mükerrer kayıt kontrolü yapar,
        3. Önkoşul dersin döneminin hedef ders döneminden büyük olmamasını kontrol eder,
        4. NetworkX üzerinde geçici kenar ekleyerek çevrim kontrolü (cycle detection) yapar;
           döngü oluşuyorsa (A -> B -> A) CurriculumCycleError fırlatarak işlemi reddeder.
        """
        prereq_code = prerequisite_code.strip().upper()
        tgt_code = target_code.strip().upper()

        graph, course_by_code, _ = self.build_dag()

        if prereq_code not in course_by_code:
            raise LookupError(f"Önkoşul ders kodu bulunamadı: '{prereq_code}'")
        if tgt_code not in course_by_code:
            raise LookupError(f"Hedef ders kodu bulunamadı: '{tgt_code}'")

        if prereq_code == tgt_code:
            raise CurriculumCycleError(
                f"Bir ders kendisine önkoşul olamaz (Self-loop reddedildi): {prereq_code} -> {tgt_code}",
                cycle_path=[prereq_code, tgt_code],
            )

        if graph.has_edge(prereq_code, tgt_code):
            raise CurriculumCycleError(
                f"Bu önkoşul bağı zaten mevcut: {prereq_code} -> {tgt_code}",
                cycle_path=[prereq_code, tgt_code],
            )

        u_course = course_by_code[prereq_code]
        v_course = course_by_code[tgt_code]

        # Graf üzerine aday kenarı ekle ve DAG çevrim kontrolü (cycle detection) yap
        graph.add_edge(prereq_code, tgt_code, is_corequisite=is_corequisite)
        if not nx.is_directed_acyclic_graph(graph):
            cycle_edges = nx.find_cycle(graph, source=prereq_code, orientation="original")
            cycle_chain = [edge[0] for edge in cycle_edges] + [cycle_edges[0][0]]
            raise CurriculumCycleError(
                f"Döngüsel bağımlılık (DAG Cycle) tespit edildiği için önkoşul reddedildi: "
                f"{' -> '.join(cycle_chain)}",
                cycle_path=cycle_chain,
            )

        # Dönem tutarlılık kontrolü: Kesin önkoşul daha üst bir dönemden alt döneme verilemez
        if not is_corequisite and u_course.semester >= v_course.semester:
            raise CurriculumCycleError(
                f"Kronolojik dönem hatası: Önkoşul ders ({u_course.code}, {u_course.semester}. dönem), "
                f"hedef dersten ({v_course.code}, {v_course.semester}. dönem) daha önceki bir dönemde olmalıdır."
            )
        if is_corequisite and u_course.semester > v_course.semester:
            raise CurriculumCycleError(
                f"Yan-koşul dönem hatası: Yan-koşul ders ({u_course.code}, {u_course.semester}. dönem), "
                f"hedef dersten ({v_course.code}, {v_course.semester}. dönem) daha üst bir dönemde olamaz."
            )

        new_edge = CoursePrerequisite(
            prerequisite_course_id=u_course.id,
            target_course_id=v_course.id,
            is_corequisite=is_corequisite,
        )
        self.db.add(new_edge)
        self.db.commit()
        self.db.refresh(new_edge)

        return PrerequisiteEdgeRead(
            id=new_edge.id,
            prerequisite_course_id=u_course.id,
            target_course_id=v_course.id,
            prerequisite_code=u_course.code,
            target_code=v_course.code,
            is_corequisite=new_edge.is_corequisite,
        )

    def simulate_course_failure(self, req: FailureSimulationRequest) -> FailureSimulationResponse:
        """
        Modül 1 — Öğrenci Ders Kalma Simülasyonu ve Critical Path Analizi (MVP-2):
        - Öğrencinin kaldığı derslerin doğrudan ve geçişli (transitive closure) olarak
          kilitlediği tüm üst dönem derslerini hesaplar.
        - Dönemlik AKTS üst sınırlarını (normal 30 AKTS, alttan/üstten kurtarma 40 AKTS)
          ve derslerin Güz (tek yarıyıl: 1,3,5,7) / Bahar (çift yarıyıl: 2,4,6,8)
          açılma kurallarını dikkate alarak mezuniyete kadar dönem dönem simülasyon yapar.
        """
        graph, course_by_code, _ = self.build_dag()

        failed_codes = [c.strip().upper() for c in req.failed_course_codes]
        for f_code in failed_codes:
            if f_code not in course_by_code:
                raise LookupError(f"Simülasyon yapılacak ders müfredatta bulunamadı: '{f_code}'")

        failed_set = set(failed_codes)

        # Doğrudan ve geçişli (transitive closure) kilitlenen tüm dersleri bul
        directly_locked: set[str] = set()
        transitively_locked: set[str] = set()
        critical_chains: dict[str, list[str]] = {}

        for f_code in failed_codes:
            directly_locked.update(graph.successors(f_code))
            transitively_locked.update(nx.descendants(graph, f_code))
            critical_chains[f_code] = self._compute_longest_chain_from_node(graph, f_code)

        # Başarılmış (passed) dersleri belirle:
        # Eğer açıkça verilmemişse, current_semester ve altındaki dönemlerde yer alan,
        # ancak failed_set veya transitively_locked içinde olmayan tüm dersler geçilmiş sayılır.
        if req.passed_course_codes is not None:
            passed_set = {c.strip().upper() for c in req.passed_course_codes if c.strip().upper() in course_by_code}
            passed_set -= failed_set
            passed_set -= transitively_locked
        else:
            passed_set = {
                code
                for code, c_obj in course_by_code.items()
                if c_obj.semester <= req.current_semester
                and code not in failed_set
                and code not in transitively_locked
            }

        all_course_codes = set(course_by_code.keys())
        remaining_courses = all_course_codes - passed_set

        # Dönemlik AKTS üst sınırı (AGENTS.md kuralı: normal 30 AKTS, kurtarma 40 AKTS)
        ects_cap = (
            settings.recovery_semester_ects_cap
            if req.use_recovery_ects_cap
            else settings.normal_semester_ects_cap
        )

        # Her dersin kritik yol uzunluğunu ve bloklama faktörünü önceliklendirme için hesapla
        cp_len_map = {code: len(self._compute_longest_chain_from_node(graph, code)) for code in all_course_codes}
        bf_map = {code: len(nx.descendants(graph, code)) for code in all_course_codes}

        # Dönem dönem (Güz/Bahar paritesine ve AKTS sınırına uyarak) mezuniyet simülasyonu
        simulated_plans: list[SimulatedSemesterPlan] = []
        sim_term_idx = req.current_semester + 1
        max_sim_horizon = 20  # Sonsuz döngü koruması

        while remaining_courses and sim_term_idx <= max_sim_horizon:
            is_fall_term = (sim_term_idx % 2 == 1)
            term_type_str = "FALL" if is_fall_term else "SPRING"

            # Bu dönemde (Güz=tek dönemler, Bahar=çift dönemler) açılan ve henüz geçilmemiş dersler
            offered_this_season = [
                code
                for code in remaining_courses
                if (course_by_code[code].semester % 2 == sim_term_idx % 2)
                and course_by_code[code].semester <= sim_term_idx
            ]

            eligible_courses: list[str] = []
            blocked_this_term: list[str] = []

            for code in offered_this_season:
                # Kesin önkoşulların tamamı geçmiş dönemlerde başarılmış mı?
                strict_prereqs = [
                    u for u in graph.predecessors(code)
                    if not graph.edges[u, code].get("is_corequisite", False)
                ]
                if all(p in passed_set for p in strict_prereqs):
                    eligible_courses.append(code)
                else:
                    blocked_this_term.append(code)

            # Kritik yolu en uzun, bloklama faktörü en yüksek ve dönemi en alt olan derslere öncelik ver
            eligible_courses.sort(
                key=lambda c: (
                    c in failed_set,           # Alttan kalan dersler en yüksek öncelikli
                    cp_len_map[c],             # Kritik yol uzunluğu CP(u)
                    bf_map[c],                 # Bloklama faktörü BF(u)
                    -course_by_code[c].semester,
                ),
                reverse=True,
            )

            planned_this_term: list[str] = []
            retakes_this_term: list[str] = []
            current_ects = 0

            for code in eligible_courses:
                # Yan-koşul (co-requisite) kontrolü: Yan-koşul ya geçilmiş olmalı ya da aynı dönemde alınmalı
                coreq_preds = [
                    u for u in graph.predecessors(code)
                    if graph.edges[u, code].get("is_corequisite", False)
                ]
                if not all(cp in passed_set or cp in planned_this_term or cp in eligible_courses for cp in coreq_preds):
                    blocked_this_term.append(code)
                    continue

                c_ects = course_by_code[code].ects
                if current_ects + c_ects <= ects_cap:
                    planned_this_term.append(code)
                    current_ects += c_ects
                    if code in failed_set or course_by_code[code].semester < sim_term_idx:
                        retakes_this_term.append(code)

            # Dönem sonunda alınan dersler başarıldı kabul edilerek bir sonraki döneme geçilir
            passed_set.update(planned_this_term)
            remaining_courses -= set(planned_this_term)

            simulated_plans.append(
                SimulatedSemesterPlan(
                    simulated_term_index=sim_term_idx,
                    semester_type=term_type_str,
                    planned_courses=planned_this_term,
                    retake_courses=retakes_this_term,
                    blocked_courses_in_this_term=sorted(blocked_this_term),
                    total_ects=current_ects,
                    ects_cap_applied=ects_cap,
                )
            )
            sim_term_idx += 1

        nominal_remaining = max(0, 8 - req.current_semester)
        simulated_remaining = len(simulated_plans)
        graduation_delay = max(0, simulated_remaining - nominal_remaining)

        # Akademik danışman ve öğrenci için Türkçe karar destek önerileri üret
        recommendations: list[str] = []
        for f_code in failed_codes:
            chain = critical_chains[f_code]
            locked_count = len(nx.descendants(graph, f_code))
            recommendations.append(
                f"'{f_code} ({course_by_code[f_code].name})' dersi toplam {locked_count} üst dönem dersini "
                f"kilitlemektedir (Kritik Yol Uzunluğu CP = {len(chain)}: {' -> '.join(chain)})."
            )
        if graduation_delay > 0:
            recommendations.append(
                f"Dikkat: Önkoşul zinciri ve dönemlik {ects_cap} AKTS sınırı nedeniyle tahmini mezuniyet "
                f"süresi {graduation_delay} yarıyıl uzamaktadır. Alttan kalan kritik derslerin açıldığı ilk "
                f"dönemde öncelikli olarak alınması zorunludur."
            )
        else:
            recommendations.append(
                f"Kurtarma senaryosu ({ects_cap} AKTS üst sınırı) ile alttan kalan dersler üst dönem "
                f"dersleriyle çakışmadan alındığında normal sürede (gecikmesiz) mezuniyet mümkündür."
            )

        return FailureSimulationResponse(
            current_semester=req.current_semester,
            failed_course_codes=failed_codes,
            directly_locked_courses=sorted(directly_locked),
            transitively_locked_courses=sorted(transitively_locked),
            critical_prerequisite_chains=critical_chains,
            nominal_remaining_semesters=nominal_remaining,
            simulated_remaining_semesters=simulated_remaining,
            estimated_graduation_delay_semesters=graduation_delay,
            applied_ects_cap=ects_cap,
            advisor_recommendations=recommendations,
            semester_by_semester_plan=simulated_plans,
        )

    def generate_non_conflict_matrix(self, academic_term: str = "2026-FALL") -> NonConflictMatrixResponse:
        """
        Modül 1 -> Modül 2 Sözleşmesi (MVP-3):
        Modül 2'deki Haftalık Ders Programı CP-SAT çözücüsünün kesin kısıt (Hard Constraint)
        olarak kullanacağı Çakışmazlık Matrisini (C_DAG) üretir.

        Üç kaynak birleştirilir:
        1. SAME_SEMESTER_MANDATORY: Aynı yarıyılın (1..8) dersleri kendi aralarında çakışamaz.
        2. COREQUISITE: Yan-koşul (is_corequisite=True) bağlı ders çiftleri çakışamaz.
        3. IRREGULAR_RETAKE_COHORT: Alttan ders alan düzensiz (irregular) öğrencilerin aynı
           dönemde birlikte kayıtlı olduğu (veya DAG üzerinde bir alt yıldan kalan darboğaz
           dersin bir üst yılda kilitlemediği) kritik ders çiftleri çakışamaz.
        """
        _, course_by_code, course_by_id = self.build_dag()
        courses = list(course_by_code.values())

        pair_reasons: dict[tuple[int, int], str] = {}
        pair_shared_irregular: dict[tuple[int, int], int] = defaultdict(int)

        def _norm_pair(id1: int, id2: int) -> tuple[int, int]:
            return (id1, id2) if id1 < id2 else (id2, id1)

        # 1. Aynı dönem ders çiftleri
        courses_by_sem: dict[int, list[Course]] = defaultdict(list)
        for c in courses:
            courses_by_sem[c.semester].append(c)

        same_sem_count = 0
        for sem_courses in courses_by_sem.values():
            for c_a, c_b in combinations(sem_courses, 2):
                key = _norm_pair(c_a.id, c_b.id)
                if key not in pair_reasons:
                    pair_reasons[key] = "SAME_SEMESTER_MANDATORY"
                    same_sem_count += 1

        # 2. Yan-koşul (Co-requisite) ders çiftleri
        coreq_edges = (
            self.db.query(CoursePrerequisite)
            .filter(CoursePrerequisite.is_corequisite.is_(True))
            .all()
        )
        coreq_count = 0
        for edge in coreq_edges:
            key = _norm_pair(edge.prerequisite_course_id, edge.target_course_id)
            if key not in pair_reasons:
                pair_reasons[key] = "COREQUISITE"
                coreq_count += 1

        # 3. Alttan ders alan düzensiz (irregular) öğrenci kohortlarının birlikte aldığı ders çiftleri
        irregular_students = (
            self.db.query(Student)
            .filter(Student.is_irregular.is_(True))
            .all()
        )
        for st in irregular_students:
            enrolled_c_ids = [
                enr.course_id
                for enr in st.enrollments
                if enr.academic_term == academic_term and enr.status == "ENROLLED"
            ]
            for id_a, id_b in combinations(sorted(set(enrolled_c_ids)), 2):
                key = _norm_pair(id_a, id_b)
                pair_shared_irregular[key] += 1

        irregular_retake_count = 0
        for key, shared_cnt in pair_shared_irregular.items():
            if shared_cnt > 0 and key not in pair_reasons:
                pair_reasons[key] = "IRREGULAR_RETAKE_COHORT"
                irregular_retake_count += 1

        items: list[NonConflictPairItem] = []
        for (id_a, id_b), reason in sorted(pair_reasons.items()):
            c_a = course_by_id[id_a]
            c_b = course_by_id[id_b]
            items.append(
                NonConflictPairItem(
                    course_a_code=c_a.code,
                    course_b_code=c_b.code,
                    course_a_id=c_a.id,
                    course_b_id=c_b.id,
                    reason=reason,
                    shared_irregular_students=pair_shared_irregular.get((id_a, id_b), 0),
                )
            )

        return NonConflictMatrixResponse(
            academic_term=academic_term,
            total_non_conflict_pairs=len(items),
            same_semester_pairs_count=same_sem_count,
            corequisite_pairs_count=coreq_count,
            irregular_retake_pairs_count=irregular_retake_count,
            pairs=items,
        )
