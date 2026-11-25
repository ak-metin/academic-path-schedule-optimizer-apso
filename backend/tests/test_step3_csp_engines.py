"""
Adım 3 Doğrulama Testleri (Pytest) — Modül 2 (Weekly Course Scheduling CSP) ve
Modül 3 (Exam, 1-Empty-Seat Grid & Equitable Proctor Allocation CSP):

1. Modül 2 (Weekly Course CSP):
   - Oda kapasitesi aşımı, aynı odada/hocada çakışma, LAB dersinin normal amfiye atanması
     ve Modül 1 C_DAG çakışmazlık kurallarının %100 sağlandığının (0 tolerans) doğrulanması,
   - Kısıtlar aşırı sıkılaştırıldığında (örneğin bir dersin öğrenci sayısı tüm amfi kapasitelerini
     aştığında) CP-SAT çözücüsünün INFEASIBLE durumu ve Türkçe Unsat Core tanı mesajı
     (`unsat_diagnostics_tr`) döndürdüğünün doğrulanması.

2. Modül 3 (Exam & Seating & Proctor CSP):
   - Ortak öğrencisi olan hiçbir iki dersin sınavının aynı oturuma atanmadığının doğrulanması,
   - 1-Boş-Koltuk Kuralı (Cap_exam(r) = Rows(r) * ceil(Cols(r)/2)) nedeniyle tek amfiye
     sığmayan kalabalık sınavların (örn. MATH101 = 90 öğrenci, en büyük amfi Cap_exam = 60)
     otomatik olarak birden fazla salona bölündüğünün doğrulanması,
   - 2B oturma matrisinde yan yana oturan öğrenciler arasında en az 1 boş koltuk
     (|col_j - col_i| >= 2) bulunduğunun doğrulanması,
   - Araştırma görevlilerinin kendi lisansüstü ders saatleriyle çakışmadan ve Minimax
     adalet kriterine (min (L_max - L_min)) göre dengeli atandığının doğrulanması.
"""

from collections import defaultdict
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models.academic import Course, TAUnavailability
from app.seed.atu_software_eng_seed import seed_atu_dataset


@pytest.fixture()
def db_session():
    test_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(test_engine, "connect")
    def _enable_fk(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=test_engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    session = TestingSessionLocal()
    try:
        seed_atu_dataset(session)
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=test_engine)


@pytest.fixture()
def client(db_session):
    def _override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_module2_weekly_schedule_hard_and_soft_constraints(client):
    """
    Modül 2 CP-SAT çözücüsünün Güz (FALL) dönemi derslerini 0 çakışma,
    %100 oda kapasitesi/LAB uyumu ve Modül 1 C_DAG kısıtlarıyla çözdüğünü doğrular.
    """
    res = client.post(
        "/api/v1/schedule/weekly/generate",
        json={
            "academic_term": "2026-FALL",
            "semester_parity": "FALL",
            "max_time_seconds": 15,
            "idle_gap_weight": 10,
            "instructor_preference_weight": 5,
        },
    )
    assert res.status_code == 200
    data = res.json()

    assert data["solver_status"] in ("OPTIMAL", "FEASIBLE")
    assert data["hard_constraints_satisfied"] is True
    assert data["total_courses_scheduled"] == 21  # Güz dönemi (1, 3, 5, 7. yarıyıl) 21 ders
    assert data["c_dag_pairs_enforced"] > 0

    assignments = data["assignments"]
    assert len(assignments) > 0

    room_slot_seen: set[tuple[int, int, int]] = set()
    inst_slot_seen: set[tuple[int, int, int]] = set()
    course_slots_map: dict[str, set[tuple[int, int]]] = defaultdict(set)

    for a in assignments:
        # 1. Kapasite aşımı kontrolü
        assert a["enrolled_count"] <= a["room_capacity"]
        # 2. LAB dersi sadece LAB odasına atanmalı
        if a["session_type"] == "LAB":
            assert a["room_type"] == "LAB"
        # 3. Oda çakışmazlığı
        r_key = (a["room_id"], a["day_of_week"], a["slot_index"])
        assert r_key not in room_slot_seen
        room_slot_seen.add(r_key)
        # 4. Hoca çakışmazlığı
        if a["instructor_id"] is not None:
            i_key = (a["instructor_id"], a["day_of_week"], a["slot_index"])
            assert i_key not in inst_slot_seen
            inst_slot_seen.add(i_key)

        course_slots_map[a["course_code"]].add((a["day_of_week"], a["slot_index"]))

    # 5. Modül 1 C_DAG Düzensiz (Irregular) Öğrenci Çakışmazlığı Kontrolü:
    # 3. dönem düzensiz öğrencilerin birlikte aldığı CSE101 ve SE201 aynı (gün, slot) içinde olamaz!
    assert course_slots_map["CSE101"].isdisjoint(course_slots_map["SE201"])
    # 5. dönem düzensiz öğrencilerin birlikte aldığı CSE201 ve SE301 aynı (gün, slot) içinde olamaz!
    assert course_slots_map["CSE201"].isdisjoint(course_slots_map["SE301"])

    # 6. Geliştirme 3 — Ayrı Teori (THEORY) + Lab (LAB) ve Blok Ders (Ardışık Saat) Doğrulaması:
    # CSE201 dersi (3T + 2L, requires_lab_room=True) 3 saat THEORY ve 2 saat LAB olarak zamanlanmalı!
    cse201_assigns = [a for a in assignments if a["course_code"] == "CSE201"]
    cse201_theory = [a for a in cse201_assigns if a["session_type"] == "THEORY"]
    cse201_lab = [a for a in cse201_assigns if a["session_type"] == "LAB"]
    assert len(cse201_theory) == 3
    assert len(cse201_lab) == 2
    assert all(a["room_type"] == "LAB" for a in cse201_lab)

    # 2 saatlik LAB oturumunun aynı günde, aynı LAB odasında ve peş peşe (|s2 - s1| == 1) olduğunu doğrula
    assert cse201_lab[0]["day_of_week"] == cse201_lab[1]["day_of_week"]
    assert cse201_lab[0]["room_id"] == cse201_lab[1]["room_id"]
    assert abs(cse201_lab[1]["slot_index"] - cse201_lab[0]["slot_index"]) == 1


def test_module2_unsat_core_diagnostics_when_overconstrained(client, db_session):
    """
    AGENTS.md Kuralı: Kısıtlar aşırı sıkı olduğunda CP-SAT sadece 'INFEASIBLE'
    döndürmekle kalmamalı; hangi dersin/amfinin darboğaz yarattığını Türkçe raporlamalıdır.
    """
    # CSE101 dersinin öğrenci sayısını en büyük amfi kapasitesinin (120) üzerine (250) çıkaralım
    cse101 = db_session.query(Course).filter(Course.code == "CSE101").first()
    cse101.enrolled_count = 250
    db_session.commit()

    res = client.post(
        "/api/v1/schedule/weekly/generate",
        json={
            "academic_term": "2026-FALL",
            "semester_parity": "FALL",
            "max_time_seconds": 10,
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["solver_status"] == "INFEASIBLE"
    assert data["hard_constraints_satisfied"] is False
    assert len(data["unsat_diagnostics_tr"]) >= 1
    assert any("CSE101" in msg for msg in data["unsat_diagnostics_tr"])


def test_module3_exam_seating_1_empty_seat_and_minimax_proctors(client, db_session):
    """
    Modül 3 CP-SAT çözücüsünün:
    1) Öğrenci sınav çakışmalarını sıfırladığını,
    2) 1-boş-koltuk efektif sınav kapasitesine göre kalabalık sınavları (örn. MATH101 = 90 öğrenci,
       en büyük amfi efektif sınav kapasitesi = 60) otomatik olarak birden fazla salona böldüğünü,
    3) 2B oturma planında yan yana öğrenciler arasında en az 1 boş koltuk bıraktığını,
    4) Araştırma görevlilerini kendi lisansüstü ders saatleriyle çakışmadan ve Minimax
       adalet kriterine (L_max - L_min <= 1.5) göre dağıttığını doğrular.
    """
    res = client.post(
        "/api/v1/schedule/exams/generate",
        json={
            "academic_term": "2026-FALL",
            "exam_type": "FINAL",
            "semester_parity": "FALL",
            "exam_days_count": 10,
            "sessions_per_day": 4,
            "max_time_seconds": 15,
        },
    )
    assert res.status_code == 200
    data = res.json()

    assert data["solver_status"] in ("OPTIMAL", "FEASIBLE")
    assert data["total_exams_scheduled"] == 21
    assert data["zero_student_clash_verified"] is True
    assert data["one_empty_seat_rule_verified"] is True

    # 1. Tek amfiye sığmayan kalabalık sınavların (örn. MATH101 = 90 kişi, CSE101 = 85 kişi)
    # 1-boş-koltuk kuralı nedeniyle otomatik olarak 2 salona bölündüğünü doğrula:
    math101_exam = next(e for e in data["exam_sessions"] if e["course_code"] == "MATH101")
    assert len(math101_exam["rooms"]) >= 2
    total_eff_cap = sum(r["room_effective_exam_capacity"] for r in math101_exam["rooms"])
    assert total_eff_cap >= math101_exam["enrolled_count"]

    # 2. Alttan ders alan düzensiz öğrencilerin sınavlarının (CSE101 ile SE201) çakışmadığını doğrula:
    cse101_exam = next(e for e in data["exam_sessions"] if e["course_code"] == "CSE101")
    se201_exam = next(e for e in data["exam_sessions"] if e["course_code"] == "SE201")
    assert (cse101_exam["exam_day"], cse101_exam["session_index"]) != (
        se201_exam["exam_day"],
        se201_exam["session_index"],
    )

    # 3. Minimax Gözetmen Adaleti ve Lisansüstü Ders Çakışmazlığı Kontrolü:
    assert data["workload_max_min_spread"] <= 1.5
    ta_unavails = {
        (u.ta_id, u.exam_day, u.session_index)
        for u in db_session.query(TAUnavailability).all()
    }
    for ex in data["exam_sessions"]:
        for r_alloc in ex["rooms"]:
            assert (r_alloc["proctor_ta_id"], ex["exam_day"], ex["session_index"]) not in ta_unavails

    # 4. 2B Oturma Planı (1-Boş-Koltuk Matrisi) Uç Noktası Doğrulaması:
    seating_res = client.get(f"/api/v1/schedule/exams/{cse101_exam['exam_session_id']}/seating")
    assert seating_res.status_code == 200
    seating_grid = seating_res.json()
    assert seating_grid["one_empty_seat_verified"] is True
    assert seating_grid["total_seated_students"] == 30  # 20 düzenli 1. sınıf + 10 alttan alan 3. sınıf öğrencisi
    assert len(seating_grid["rooms"]) >= 2  # Görsel 2B harita için salon matris boyutları gelmeli
    assert all(rm["seat_rows"] > 0 and rm["seat_cols"] > 0 for rm in seating_grid["rooms"])
    # Tüm koltuk sütun indekslerinin tek sayı (1, 3, 5, ...) olduğunu doğrula
    for seat in seating_grid["seats"]:
        assert seat["seat_col"] % 2 == 1
