"""
Geliştirme 1 Doğrulama Testleri (Pytest) — İnteraktif Kaynak & Hoca / Arş. Gör. Müsaitlik Yönetimi:
- Öğretim elemanı 5x8 haftalık müsaitlik ve tercih cezası matrisinin (`GET/PUT /api/v1/instructors/{id}/availabilities`)
  güncellenmesi ve Modül 2 CP-SAT çözücüsünün kapatılan saate ders atamadığının doğrulanması,
- Amfi/Lab kapasite ve 2B koltuk matrisinin (`PUT /api/v1/rooms/{id}/capacity`) güncellenmesi ve
  1-boş-koltuk efektif sınav kapasitesinin otomatik yeniden hesaplandığının doğrulanması,
- Araştırma görevlisi sınav kısıtı ekleme/silme (`POST/DELETE /api/v1/teaching-assistants/.../unavailabilities`)
  ve Ders kısıtı güncelleme (`PUT /api/v1/courses/{id}/constraints`) uç noktalarının doğrulanması.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models.academic import Course, Instructor, Room, TeachingAssistant
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


def test_instructor_availability_matrix_update_and_cpsat_enforcement(client, db_session):
    """
    Bir öğretim elemanının Pazartesi (day=1) tüm saatlerini (slot=1..8) 'is_available=False'
    olarak kapattığımızda Modül 2 CP-SAT çözücüsünün o hocaya Pazartesi günü hiçbir ders
    atamadığını doğrular.
    """
    inst = db_session.query(Instructor).filter(Instructor.code == "INST-01").first()
    get_res = client.get(f"/api/v1/instructors/{inst.id}/availabilities")
    assert get_res.status_code == 200
    assert len(get_res.json()) == 40  # 5 gün x 8 saat

    # Pazartesi (day=1) tüm 8 saati kapat
    monday_closed_slots = [
        {"day_of_week": 1, "slot_index": s, "is_available": False, "preference_penalty": 0}
        for s in range(1, 9)
    ]
    put_res = client.put(
        f"/api/v1/instructors/{inst.id}/availabilities",
        json={"slots": monday_closed_slots},
    )
    assert put_res.status_code == 200

    # Şimdi Modül 2 CP-SAT haftalık ders programını çalıştır
    sched_res = client.post(
        "/api/v1/schedule/weekly/generate",
        json={
            "academic_term": "2026-FALL",
            "semester_parity": "FALL",
            "max_time_seconds": 15,
        },
    )
    assert sched_res.status_code == 200
    sched = sched_res.json()
    assert sched["solver_status"] in ("OPTIMAL", "FEASIBLE")

    # INST-01 hocasına ait hiçbir dersin Pazartesi (day_of_week == 1) gününe atanmadığını doğrula!
    inst01_assignments = [
        a for a in sched["assignments"] if a["instructor_id"] == inst.id
    ]
    assert len(inst01_assignments) > 0
    assert all(a["day_of_week"] != 1 for a in inst01_assignments)


def test_room_course_and_ta_unavailability_crud_endpoints(client, db_session):
    """Amfi kapasite/grid, ders kısıtı ve Arş. Gör. sınav kısıtı CRUD uç noktalarını doğrular."""
    # 1. Amfi 2B grid güncelleme -> 1-boş-koltuk kapasite yeniden hesaplama
    room = db_session.query(Room).filter(Room.code == "B-D101").first()
    r_res = client.put(
        f"/api/v1/rooms/{room.id}/capacity",
        json={
            "room_type": "LECTURE",
            "normal_capacity": 100,
            "seat_rows": 10,
            "seat_cols": 11,  # Cap_exam = 10 * ceil(11/2) = 10 * 6 = 60
        },
    )
    assert r_res.status_code == 200
    assert r_res.json()["effective_exam_capacity"] == 60

    # 2. Ders kısıtı güncelleme
    course = db_session.query(Course).filter(Course.code == "SE101").first()
    c_res = client.put(
        f"/api/v1/courses/{course.id}/constraints",
        json={
            "enrolled_count": 68,
            "requires_lab_room": False,
            "theory_hours": 3,
            "lab_hours": 0,
            "instructor_id": course.instructor_id,
        },
    )
    assert c_res.status_code == 200
    assert c_res.json()["enrolled_count"] == 68

    # 3. Arş. Gör. yüksek lisans ders / sınav kısıtı ekleme ve silme
    ta = db_session.query(TeachingAssistant).filter(TeachingAssistant.code == "TA-01").first()
    ta_post = client.post(
        f"/api/v1/teaching-assistants/{ta.id}/unavailabilities",
        json={"exam_day": 4, "session_index": 3, "reason": "PhD Qualifier Defense"},
    )
    assert ta_post.status_code == 201
    created_id = ta_post.json()["id"]

    ta_list = client.get("/api/v1/teaching-assistants/unavailabilities")
    assert ta_list.status_code == 200
    assert any(u["id"] == created_id for u in ta_list.json())

    ta_del = client.delete(f"/api/v1/teaching-assistants/unavailabilities/{created_id}")
    assert ta_del.status_code == 204
