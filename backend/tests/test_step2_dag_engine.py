"""
Adım 2 Doğrulama Testleri (Pytest) — Modül 1: Curriculum Graph Engine (NetworkX & DAG):
- Müfredatın geçerli bir DAG olduğunun, Blocking Factor ve Critical Path (CP)
  hesaplamalarının doğrulanması,
- Yeni önkoşul eklenirken çevrim (cycle detection: A -> B -> A ve self-loop A -> A)
  tespitinin HTTP 422 ile reddedilmesi,
- Öğrenci ders kalma simülasyonunda (Critical Path Analysis) geçişli kapanış
  (transitive closure) ve 30/40 AKTS sınırlarının mezuniyet gecikmesine etkisinin doğrulanması,
- Modül 2 için üretilen C_DAG Çakışmazlık Matrisinin (aynı dönem + yan-koşul +
  alttan ders alan düzensiz öğrenci kohortu) doğrulanması.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
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


def test_curriculum_dag_analysis_and_critical_path(client):
    """Müfredatın DAG olduğunu, CSE101'in en yüksek darboğaz dersi olduğunu ve kritik yolu doğrular."""
    res = client.get("/api/v1/curriculum/graph")
    assert res.status_code == 200
    data = res.json()

    assert data["is_valid_dag"] is True
    assert data["total_nodes"] == 40
    assert data["total_edges"] == 36
    assert data["longest_critical_path_length"] >= 6

    # CSE101 -> CSE102 -> CSE201 -> ... zincirinin kontrolü
    cse101_node = next(n for n in data["nodes"] if n["code"] == "CSE101")
    assert "CSE102" in cse101_node["direct_dependents"]
    assert "CSE201" in cse101_node["transitive_dependents"]
    assert "SE304" in cse101_node["transitive_dependents"]
    assert cse101_node["blocking_factor"] == len(cse101_node["transitive_dependents"])
    assert cse101_node["blocking_factor"] >= 10
    assert cse101_node["critical_path_length"] == len(cse101_node["critical_path_chain"])


def test_cycle_detection_rejects_circular_dependency_with_http_422(client):
    """
    AGENTS.md Kuralı: Döngüsel bağımlılık (A -> B -> ... -> A) veya self-loop (A -> A)
    eklenmeye çalışıldığında sistem HTTP 422 döndürmelidir.
    """
    # 1. Doğrudan self-loop denemesi: CSE101 -> CSE101
    res_self = client.post(
        "/api/v1/prerequisites",
        json={"prerequisite_code": "CSE101", "target_code": "CSE101", "is_corequisite": False},
    )
    assert res_self.status_code == 422

    # 2. Çok adımlı çevrim (Cycle) denemesi:
    # Mevcut zincir: CSE101 -> CSE102 -> CSE201 -> CSE202 -> SE303 -> SE403
    # Eğer SE403 -> CSE101 eklenirse 6 düğümlü döngü oluşur -> HTTP 422 ile reddedilmeli
    res_cycle = client.post(
        "/api/v1/prerequisites",
        json={"prerequisite_code": "SE403", "target_code": "CSE101", "is_corequisite": False},
    )
    assert res_cycle.status_code == 422
    detail = res_cycle.json()["detail"]
    assert "cycle_path" in detail
    assert "CSE101" in detail["cycle_path"]
    assert "SE403" in detail["cycle_path"]

    # 3. Geçerli ve döngü oluşturmayan yeni bir önkoşul ekleme denemesi:
    # MATH201 (3. dönem Linear Algebra) -> CSE302 (6. dönem Machine Learning)
    res_valid = client.post(
        "/api/v1/prerequisites",
        json={"prerequisite_code": "MATH201", "target_code": "CSE302", "is_corequisite": False},
    )
    assert res_valid.status_code == 201
    edge_data = res_valid.json()
    assert edge_data["prerequisite_code"] == "MATH201"
    assert edge_data["target_code"] == "CSE302"


def test_student_failure_simulation_and_ects_caps(client):
    """
    Öğrenci 2. dönemde CSE102 (OOP) dersinden kaldığında:
    - CSE201 ve ona bağlı tüm alt/üst dönem derslerinin (transitive closure) kilitlendiğini,
    - Dönemlik AKTS üst sınırlarına (40 AKTS kurtarma vs 30 AKTS normal) göre mezuniyet
      planının dönem dönem üretildiğini doğrular.
    """
    res_sim = client.post(
        "/api/v1/curriculum/simulate-failure",
        json={
            "current_semester": 2,
            "failed_course_codes": ["CSE102"],
            "use_recovery_ects_cap": True,
        },
    )
    assert res_sim.status_code == 200
    sim = res_sim.json()

    assert sim["directly_locked_courses"] == ["CSE201"]
    assert "CSE202" in sim["transitively_locked_courses"]
    assert "CSE204" in sim["transitively_locked_courses"]
    assert "SE304" in sim["transitively_locked_courses"]
    assert sim["applied_ects_cap"] == 40

    # 3. dönemde (Güz) CSE201 kilitli olduğu için alınamamalı (blocked_courses_in_this_term içinde olmalı)
    term_3_plan = sim["semester_by_semester_plan"][0]
    assert term_3_plan["simulated_term_index"] == 3
    assert "CSE201" in term_3_plan["blocked_courses_in_this_term"]
    assert "CSE201" not in term_3_plan["planned_courses"]

    # Hiçbir simüle edilen dönemde toplam AKTS, uygulanan AKTS üst sınırını aşmamalı
    for term_plan in sim["semester_by_semester_plan"]:
        assert term_plan["total_ects"] <= term_plan["ects_cap_applied"]


def test_non_conflict_matrix_generation_for_module2(client):
    """
    Modül 1'in Modül 2 için ürettiği C_DAG çakışmazlık matrisinin:
    1) Aynı dönem derslerini (SAME_SEMESTER_MANDATORY),
    2) Yan-koşul derslerini (COREQUISITE),
    3) Alttan ders alan düzensiz (irregular) öğrenci ders çiftlerini (IRREGULAR_RETAKE_COHORT)
    içerdiğini doğrular.
    """
    res = client.get("/api/v1/curriculum/non-conflict-matrix?academic_term=2026-FALL")
    assert res.status_code == 200
    matrix = res.json()

    assert matrix["total_non_conflict_pairs"] > 0
    assert matrix["same_semester_pairs_count"] > 0
    assert matrix["irregular_retake_pairs_count"] > 0

    reasons = {p["reason"] for p in matrix["pairs"]}
    assert "SAME_SEMESTER_MANDATORY" in reasons
    assert "IRREGULAR_RETAKE_COHORT" in reasons

    # Seed verisindeki 3. dönem düzensiz öğrencileri alttan CSE101 ile 3. dönem SE201'i birlikte alıyor.
    # Bu çift C_DAG içinde IRREGULAR_RETAKE_COHORT olarak bulunmalı!
    irregular_pairs = [
        {p["course_a_code"], p["course_b_code"]}
        for p in matrix["pairs"]
        if p["reason"] == "IRREGULAR_RETAKE_COHORT"
    ]
    assert {"CSE101", "SE201"} in irregular_pairs
    assert {"CSE201", "SE301"} in irregular_pairs
