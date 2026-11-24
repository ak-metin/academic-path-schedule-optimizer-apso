"""
Adım 1 Doğrulama Testleri (Pytest):
- SQLAlchemy 2.0 veritabanı modellerinin ve kısıtlarının (Single Source of Truth) doğrulanması,
- ATÜ Yazılım Mühendisliği 8 dönemlik müfredat ve KVKK uyumlu veri setinin (seed) kontrolü,
- 1-Boş-Koltuk Kuralı (Cap_exam(r) = Rows(r) * ceil(Cols(r) / 2)) hesaplama doğruluğu,
- FastAPI katalog ve sağlık uç noktalarının (endpoints) entegrasyon testi.
"""

import math
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models.academic import Course, Room, Student
from app.seed.atu_software_eng_seed import seed_atu_dataset


@pytest.fixture()
def db_session():
    """Her test için izole bellek-içi (in-memory) ilişkisel veritabanı oturumu."""
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
    """FastAPI TestClient bağımlılık enjeksiyonu."""
    def _override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_seed_dataset_completeness_and_idempotency(db_session):
    """ATÜ Yazılım Mühendisliği veri setinin eksiksiz ve tekrarsız (idempotent) yüklendiğini doğrular."""
    counts_first = seed_atu_dataset(db_session)
    counts_second = seed_atu_dataset(db_session)
    assert counts_first == counts_second
    assert counts_first["courses"] == 40
    assert counts_first["prerequisites"] == 36
    assert counts_first["instructors"] == 12
    assert counts_first["rooms"] == 10
    assert counts_first["teaching_assistants"] == 8
    assert counts_first["students"] == 100  # 80 düzenli + 20 alttan ders alan düzensiz öğrenci

    # 8 dönemin tamamında ders bulunduğunu doğrula
    semesters = {c.semester for c in db_session.query(Course).all()}
    assert semesters == {1, 2, 3, 4, 5, 6, 7, 8}


def test_kvkk_student_anonymization_compliance(db_session):
    """KVKK Kuralı: Tüm öğrenci numaralarının 22060xxxx formatında sentetik olduğunu doğrular."""
    students = db_session.query(Student).all()
    assert len(students) == 100
    for st in students:
        assert st.student_number.startswith("22060")
        assert len(st.student_number) == 9
        assert "Synthetic" in st.full_name


def test_one_empty_seat_rule_effective_exam_capacity(db_session):
    """
    Modül 3 Kuralı: Amfilerin efektif sınav kapasitesinin
    Cap_exam(r) = Rows(r) * ceil(Cols(r) / 2) formülüyle birebir hesaplandığını doğrular.
    """
    rooms = db_session.query(Room).all()
    assert len(rooms) == 10
    for room in rooms:
        expected_cap = room.seat_rows * math.ceil(room.seat_cols / 2.0)
        assert room.effective_exam_capacity == expected_cap
        assert room.effective_exam_capacity < room.normal_capacity


def test_api_endpoints_health_and_catalog(client):
    """FastAPI sağlık, veri seti özeti, dersler, önkoşullar ve derslikler uç noktalarını doğrular."""
    res_health = client.get("/api/v1/health")
    assert res_health.status_code == 200
    assert res_health.json()["status"] == "ok"

    res_summary = client.get("/api/v1/dataset/summary")
    assert res_summary.status_code == 200
    summary = res_summary.json()
    assert summary["total_courses"] == 40
    assert summary["regular_students"] == 80
    assert summary["irregular_students"] == 20

    res_sem1 = client.get("/api/v1/courses?semester=1")
    assert res_sem1.status_code == 200
    sem1_courses = res_sem1.json()
    assert len(sem1_courses) == 6
    assert all(c["semester"] == 1 for c in sem1_courses)

    res_rooms = client.get("/api/v1/rooms")
    assert res_rooms.status_code == 200
    rooms_data = res_rooms.json()
    amfi1 = next(r for r in rooms_data if r["code"] == "B-AMFI-1")
    assert amfi1["normal_capacity"] == 120
    assert amfi1["effective_exam_capacity"] == 60
