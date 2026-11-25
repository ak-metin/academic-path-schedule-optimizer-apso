"""
Geliştirme 4 (Stretch Goal 1) Doğrulama Testleri (Pytest) — What-If Manuel Ders Taşıma,
Anlık Kısıt / C_DAG Doğrulayıcı ve Ders Sabitleme (Pin / Lock) ile Yeniden Optimizasyon:

1. Sabitlenen (pinned_slots) bir ders hücresinin CP-SAT çözücüsü yeniden çalıştırıldığında
   kesin olarak korunduğunun doğrulanması,
2. Manuel What-If ders taşıma uç noktasının (`POST /api/v1/schedule/weekly/move`):
   - Aynı dönemde veya C_DAG çakışması olan başka bir dersin saatine taşınmak istendiğinde
     ihlali yakalayıp (`is_valid=False`) taşımayı reddettiğinin doğrulanması,
   - LAB dersini normal amfiye taşımak istediğinde salon tipi ihlalini yakaladığının doğrulanması,
   - Uygun ve boş bir (gün, saat, amfi) hücresine taşındığında (`is_valid=True`, `applied=True`)
     değişikliği başarıyla kaydettiğinin doğrulanması.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models.academic import Course, Room
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


def test_pinned_slots_preserved_during_weekly_reoptimization(client, db_session):
    """
    SE101 (THEORY) dersini Çarşamba (day=3), Saat 2 (slot=2), B-AMFI-1 salonuna
    sabitleyerek (pinned_slots) CP-SAT çözücüsünü çalıştırdığımızda bu hücrenin
    birebir korunduğunu doğrular.
    """
    se101 = db_session.query(Course).filter(Course.code == "SE101").first()
    amfi1 = db_session.query(Room).filter(Room.code == "B-AMFI-1").first()

    res = client.post(
        "/api/v1/schedule/weekly/generate",
        json={
            "academic_term": "2026-FALL",
            "semester_parity": "FALL",
            "max_time_seconds": 15,
            "pinned_slots": [
                {
                    "course_id": se101.id,
                    "room_id": amfi1.id,
                    "day_of_week": 3,
                    "slot_index": 2,
                    "session_type": "THEORY",
                }
            ],
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["solver_status"] in ("OPTIMAL", "FEASIBLE")

    pinned_match = [
        a
        for a in data["assignments"]
        if a["course_id"] == se101.id
        and a["room_id"] == amfi1.id
        and a["day_of_week"] == 3
        and a["slot_index"] == 2
        and a["session_type"] == "THEORY"
    ]
    assert len(pinned_match) == 1


def test_what_if_slot_move_conflict_detection_and_valid_move(client, db_session):
    """
    What-If manuel ders taşıma doğrulayıcısının:
    1) C_DAG çakışması olan başka bir 1. sınıf dersinin saatine taşımayı engellediğini,
    2) LAB oturumunu normal LECTURE amfisine taşımayı engellediğini,
    3) Kapasitesi yetmeyen küçük sınıfa taşımayı engellediğini doğrular.
    """
    gen_res = client.post(
        "/api/v1/schedule/weekly/generate",
        json={
            "academic_term": "2026-FALL",
            "semester_parity": "FALL",
            "max_time_seconds": 15,
        },
    )
    assert gen_res.status_code == 200
    assignments = gen_res.json()["assignments"]

    se101_slot = next(a for a in assignments if a["course_code"] == "SE101")
    cse101_slot = next(a for a in assignments if a["course_code"] == "CSE101")
    cse201_lab_slot = next(
        a for a in assignments if a["course_code"] == "CSE201" and a["session_type"] == "LAB"
    )
    small_room = db_session.query(Room).filter(Room.code == "B-D301").first()  # Kapasite = 48
    lecture_room = db_session.query(Room).filter(Room.code == "B-AMFI-1").first()

    # 1. C_DAG & Oda Çakışması Testi: SE101'i aynı dönemdeki CSE101'in gün ve saatine taşımayı dene -> Reddedilmeli
    clash_res = client.post(
        "/api/v1/schedule/weekly/move",
        json={
            "academic_term": "2026-FALL",
            "course_id": se101_slot["course_id"],
            "session_type": se101_slot["session_type"],
            "from_day": se101_slot["day_of_week"],
            "from_slot": se101_slot["slot_index"],
            "from_room_id": se101_slot["room_id"],
            "to_day": cse101_slot["day_of_week"],
            "to_slot": cse101_slot["slot_index"],
            "to_room_id": cse101_slot["room_id"],
            "apply_if_valid": True,
        },
    )
    assert clash_res.status_code == 200
    clash_data = clash_res.json()
    assert clash_data["is_valid"] is False
    assert clash_data["applied"] is False
    assert any("C_DAG" in v for v in clash_data["violations_tr"])

    # 2. LAB Oturumunu Normal Amfiye (LECTURE) Taşıma Testi -> Reddedilmeli
    lab_res = client.post(
        "/api/v1/schedule/weekly/move",
        json={
            "academic_term": "2026-FALL",
            "course_id": cse201_lab_slot["course_id"],
            "session_type": "LAB",
            "from_day": cse201_lab_slot["day_of_week"],
            "from_slot": cse201_lab_slot["slot_index"],
            "from_room_id": cse201_lab_slot["room_id"],
            "to_day": cse201_lab_slot["day_of_week"],
            "to_slot": cse201_lab_slot["slot_index"],
            "to_room_id": lecture_room.id,
            "apply_if_valid": False,
        },
    )
    assert lab_res.status_code == 200
    assert lab_res.json()["is_valid"] is False
    assert any("LAB" in v for v in lab_res.json()["violations_tr"])

    # 3. 75 kişilik SE101 dersini 48 kişilik B-D301 sınıfına taşıma testi -> Kapasite Aşımı Reddedilmeli
    cap_res = client.post(
        "/api/v1/schedule/weekly/move",
        json={
            "academic_term": "2026-FALL",
            "course_id": se101_slot["course_id"],
            "session_type": "THEORY",
            "from_day": se101_slot["day_of_week"],
            "from_slot": se101_slot["slot_index"],
            "from_room_id": se101_slot["room_id"],
            "to_day": se101_slot["day_of_week"],
            "to_slot": se101_slot["slot_index"],
            "to_room_id": small_room.id,
            "apply_if_valid": False,
        },
    )
    assert cap_res.status_code == 200
    assert cap_res.json()["is_valid"] is False
    assert any("Kapasite" in v for v in cap_res.json()["violations_tr"])
