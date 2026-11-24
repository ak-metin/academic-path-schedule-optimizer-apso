"""
Adım 4 Doğrulama Testleri (Pytest) — Excel (.xlsx) ve PDF (.pdf) Dışa Aktarım Servisleri:
- Modül 2 haftalık ders programı oluşturulduktan sonra `/api/v1/export/weekly.xlsx`
  uç noktasının geçerli bir OpenPyXL Excel çalışma kitabı döndürdüğünü doğrular.
- Modül 3 sınav, 1-boş-koltuk oturma planı ve Minimax gözetmen programı oluşturulduktan
  sonra `/api/v1/export/exams.pdf` uç noktasının geçerli bir ReportLab PDF belgesi
  (`%PDF-` imzalı) döndürdüğünü doğrular.
"""

import base64
import io
from openpyxl import load_workbook
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


def test_weekly_schedule_excel_export(client):
    """Haftalık ders programı üretildikten sonra Excel (.xlsx) dışa aktarımının doğruluğunu test eder."""
    gen_res = client.post(
        "/api/v1/schedule/weekly/generate",
        json={
            "academic_term": "2026-FALL",
            "semester_parity": "FALL",
            "max_time_seconds": 15,
        },
    )
    assert gen_res.status_code == 200

    xlsx_res = client.get("/api/v1/export/weekly.xlsx?academic_term=2026-FALL")
    assert xlsx_res.status_code == 200
    assert (
        xlsx_res.headers["content-type"]
        == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    wb = load_workbook(io.BytesIO(xlsx_res.content))
    assert "Weekly_Schedule_List" in wb.sheetnames
    ws = wb["Weekly_Schedule_List"]
    assert ws.max_row > 20


def test_exam_seating_and_proctor_pdf_export(client):
    """Sınav ve 1-boş-koltuk oturma planı üretildikten sonra PDF (.pdf) dışa aktarımını test eder."""
    gen_res = client.post(
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
    assert gen_res.status_code == 200

    pdf_res = client.get("/api/v1/export/exams.pdf?academic_term=2026-FALL&exam_type=FINAL")
    assert pdf_res.status_code == 200
    assert pdf_res.headers["content-type"] == "application/pdf"
    assert pdf_res.content.startswith(b"%PDF-")
    assert len(pdf_res.content) > 1500


def test_excel_import_with_pydantic_v2_validation_and_row_error_reporting(client):
    """
    Şablon Excel (.xlsx) dosyasının indirildiğini, içine 1 geçerli ders + 1 geçersiz ders
    (örneğin 15. yarıyıl gibi Pydantic v2 sınırını aşan satır) eklendiğinde geçerli satırın
    kaydedilip hatalı satırın satır numarasıyla Türkçe raporlandığını doğrular.
    """
    tpl_res = client.get("/api/v1/import/template.xlsx")
    assert tpl_res.status_code == 200

    wb = load_workbook(io.BytesIO(tpl_res.content))
    ws_c = wb["Courses"]
    # Satır 3'e kasıtlı olarak geçersiz yarıyıl (semester=15 -> ge=1, le=8 ihlali) ekleyelim
    ws_c.append(["SE999", "Invalid Semester Course", 15, 6, 3, 0, True, False, 30, "INST-01"])

    out_buf = io.BytesIO()
    wb.save(out_buf)
    b64_payload = base64.b64encode(out_buf.getvalue()).decode("ascii")

    imp_res = client.post(
        "/api/v1/import/excel",
        json={
            "filename": "atu_import_test.xlsx",
            "content_base64": b64_payload,
        },
    )
    assert imp_res.status_code == 200
    result = imp_res.json()

    assert result["courses_created"] == 1  # Şablondaki SE409 eklendi
    assert result["rooms_created"] == 1    # Şablondaki B-D302 eklendi
    assert result["total_errors"] == 1     # SE999 satırı Pydantic v2 tarafından yakalandı
    assert result["row_errors"][0]["sheet_name"] == "Courses"
    assert result["row_errors"][0]["row_number"] == 3
    assert result["row_errors"][0]["identifier"] == "SE999"

