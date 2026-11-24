"""
ATÜ Yazılım Mühendisliği Bölümü 8 Dönemlik Müfredat, Amfi/Lab, Öğretim Elemanı,
Araştırma Görevlisi ve KVKK Uyumlu Anonim Öğrenci Veri Seti (Seed Generator).

KVKK Kuralı: Gerçek öğrencilere ait TC Kimlik No veya hassas kişisel veri (PII)
bulundurulmaz; tüm öğrenci numaraları 22060xxxx formatında sentetik olarak üretilir.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.academic import (
    Course,
    CoursePrerequisite,
    Enrollment,
    Instructor,
    InstructorAvailability,
    Room,
    Student,
    TAUnavailability,
    TeachingAssistant,
)


# 1. Öğretim Elemanları (12 Akademisyen)
ATU_INSTRUCTORS = [
    ("INST-01", "Asst. Prof. Dr. Havva Esin Ünal", "Asst. Prof. Dr.", 14),
    ("INST-02", "Prof. Dr. Ahmet Yılmaz", "Prof. Dr.", 12),
    ("INST-03", "Assoc. Prof. Dr. Mehmet Kaya", "Assoc. Prof. Dr.", 14),
    ("INST-04", "Assoc. Prof. Dr. Elif Demir", "Assoc. Prof. Dr.", 14),
    ("INST-05", "Asst. Prof. Dr. Burak Şahin", "Asst. Prof. Dr.", 16),
    ("INST-06", "Asst. Prof. Dr. Zeynep Çelik", "Asst. Prof. Dr.", 16),
    ("INST-07", "Asst. Prof. Dr. Emre Aydın", "Asst. Prof. Dr.", 16),
    ("INST-08", "Asst. Prof. Dr. Selin Arslan", "Asst. Prof. Dr.", 16),
    ("INST-09", "Asst. Prof. Dr. Caner Koç", "Asst. Prof. Dr.", 16),
    ("INST-10", "Lect. Dr. Deniz Özkan", "Lect. Dr.", 18),
    ("INST-11", "Lect. Gökhan Polat", "Lecturer", 18),
    ("INST-12", "Lect. Merve Kurt", "Lecturer", 18),
]


# 2. ATÜ Yazılım Mühendisliği 8 Dönemlik Müfredat Dersleri
# Format: (code, name, semester, ects, theory_hrs, lab_hrs, is_mandatory, requires_lab, enrolled, instructor_code)
ATU_COURSES = [
    # 1. Dönem (Güz - 1. Sınıf)
    ("SE101", "Introduction to Software Engineering", 1, 5, 3, 0, True, False, 75, "INST-01"),
    ("CSE101", "Algorithms and Programming I", 1, 7, 3, 2, True, False, 85, "INST-05"),
    ("MATH101", "Calculus I", 1, 6, 4, 0, True, False, 90, "INST-10"),
    ("PHYS101", "General Physics I", 1, 6, 3, 2, True, False, 80, "INST-11"),
    ("ENG101", "Academic English I", 1, 3, 3, 0, True, False, 85, "INST-12"),
    ("TURK101", "Turkish Language I", 1, 3, 2, 0, True, False, 85, "INST-12"),
    # 2. Dönem (Bahar - 1. Sınıf)
    ("CSE102", "Object-Oriented Programming (Programming II)", 2, 7, 3, 2, True, True, 82, "INST-05"),
    ("MATH102", "Calculus II", 2, 6, 4, 0, True, False, 80, "INST-10"),
    ("MATH104", "Discrete Mathematics", 2, 6, 3, 0, True, False, 76, "INST-03"),
    ("PHYS102", "General Physics II", 2, 6, 3, 2, True, False, 74, "INST-11"),
    ("ENG102", "Academic English II", 2, 3, 3, 0, True, False, 80, "INST-12"),
    # 3. Dönem (Güz - 2. Sınıf)
    ("CSE201", "Data Structures and Algorithms", 3, 7, 3, 2, True, True, 72, "INST-03"),
    ("SE201", "Software Requirements Engineering", 3, 6, 3, 0, True, False, 65, "INST-01"),
    ("MATH201", "Linear Algebra for Engineers", 3, 5, 3, 0, True, False, 68, "INST-10"),
    ("MATH203", "Probability and Statistics", 3, 6, 3, 0, True, False, 70, "INST-04"),
    ("CSE203", "Digital Logic Design", 3, 6, 3, 2, True, False, 64, "INST-07"),
    # 4. Dönem (Bahar - 2. Sınıf)
    ("SE202", "Software Design and Architecture", 4, 6, 3, 2, True, False, 62, "INST-01"),
    ("CSE202", "Database Management Systems", 4, 6, 3, 2, True, True, 66, "INST-06"),
    ("CSE204", "Operating Systems", 4, 6, 3, 2, True, False, 60, "INST-07"),
    ("CSE206", "Design and Analysis of Algorithms", 4, 6, 3, 0, True, False, 58, "INST-03"),
    ("MATH202", "Differential Equations", 4, 6, 4, 0, True, False, 60, "INST-10"),
    # 5. Dönem (Güz - 3. Sınıf)
    ("SE301", "Software Quality Assurance and Testing", 5, 6, 3, 2, True, True, 56, "INST-01"),
    ("CSE301", "Computer Networks", 5, 6, 3, 2, True, False, 54, "INST-08"),
    ("SE303", "Web Engineering and Cloud Systems", 5, 6, 3, 2, True, True, 58, "INST-06"),
    ("CSE303", "Artificial Intelligence", 5, 6, 3, 0, True, False, 55, "INST-04"),
    ("SE305", "Human-Computer Interaction", 5, 6, 3, 0, True, False, 50, "INST-09"),
    # 6. Dönem (Bahar - 3. Sınıf)
    ("SE302", "Software Project Management", 6, 6, 3, 0, True, False, 54, "INST-02"),
    ("SE304", "Distributed Systems and Microservices", 6, 6, 3, 2, True, True, 50, "INST-08"),
    ("CSE302", "Machine Learning", 6, 6, 3, 2, True, False, 52, "INST-04"),
    ("SE306", "Information Security and Cryptography", 6, 6, 3, 0, True, False, 48, "INST-09"),
    ("SE308", "Formal Methods in Software Engineering", 6, 6, 3, 0, False, False, 35, "INST-03"),
    # 7. Dönem (Güz - 4. Sınıf)
    ("SE401", "Graduation Project I (Proposal & Design)", 7, 8, 2, 4, True, False, 48, "INST-01"),
    ("SE403", "DevOps and Continuous Delivery", 7, 6, 3, 2, True, True, 44, "INST-06"),
    ("SE405", "Mobile Application Development", 7, 6, 3, 2, False, True, 40, "INST-05"),
    ("SE407", "Data Mining and Business Analytics", 7, 5, 3, 0, False, False, 38, "INST-04"),
    ("ENG401", "Engineering Ethics and Entrepreneurship", 7, 5, 3, 0, True, False, 48, "INST-02"),
    # 8. Dönem (Bahar - 4. Sınıf)
    ("SE402", "Graduation Project II (Implementation & Thesis)", 8, 12, 2, 6, True, False, 46, "INST-01"),
    ("SE404", "Secure Software Development", 8, 6, 3, 0, False, False, 36, "INST-09"),
    ("SE406", "Cloud-Native Optimization & Operations Research", 8, 6, 3, 0, False, False, 34, "INST-02"),
    ("SE408", "Deep Learning Applications", 8, 6, 3, 0, False, False, 38, "INST-04"),
]


# 3. Önkoşul ve Yan-Koşul Bağları (Directed Acyclic Graph - DAG Kenarları)
# Format: (prerequisite_code, target_code, is_corequisite)
ATU_PREREQUISITES = [
    # Programlama ve Veri Yapıları Zinciri (En Kritik Darboğaz Yolu)
    ("CSE101", "CSE102", False),
    ("CSE102", "CSE201", False),
    ("CSE201", "CSE202", False),
    ("CSE201", "CSE204", False),
    ("CSE201", "CSE206", False),
    ("CSE201", "CSE303", False),
    ("CSE202", "SE303", False),
    ("CSE204", "CSE301", False),
    ("CSE301", "SE304", False),
    ("CSE206", "SE406", False),
    # Yazılım Mühendisliği Çekirdek Zinciri
    ("SE101", "SE201", False),
    ("SE201", "SE202", False),
    ("SE202", "SE301", False),
    ("SE202", "SE302", False),
    ("SE301", "SE401", False),
    ("SE302", "SE401", False),
    ("SE401", "SE402", False),
    ("SE303", "SE403", False),
    ("SE303", "SE405", False),
    # Matematik, Yapay Zeka ve Güvenlik Zinciri
    ("MATH101", "MATH102", False),
    ("MATH101", "MATH201", False),
    ("MATH102", "MATH203", False),
    ("MATH102", "MATH202", False),
    ("MATH104", "CSE201", False),
    ("MATH104", "SE308", False),
    ("MATH203", "CSE303", False),
    ("CSE303", "CSE302", False),
    ("CSE302", "SE407", False),
    ("CSE302", "SE408", False),
    ("CSE301", "SE306", False),
    ("SE306", "SE404", False),
    # Fizik ve İngilizce Zinciri
    ("PHYS101", "PHYS102", False),
    ("PHYS102", "CSE203", False),
    ("ENG101", "ENG102", False),
    # Yan-Koşul (Co-requisite) Örnekleri (Aynı dönemde birlikte alınabilen bağımlı dersler)
    ("SE201", "CSE201", True),
    ("SE301", "SE303", True),
]


# 4. Fiziksel Derslikler, Amfiler ve Bilgisayar Laboratuvarları
# Format: (code, name, room_type, normal_capacity, seat_rows, seat_cols)
# Not: 1-boş-koltuk sınav kapasitesi Cap_exam = seat_rows * ceil(seat_cols / 2)
ATU_ROOMS = [
    ("B-AMFI-1", "Engineering Grand Amphitheater 1", "LECTURE", 120, 10, 12),  # Cap_exam = 10 * 6 = 60
    ("B-AMFI-2", "Engineering Grand Amphitheater 2", "LECTURE", 100, 10, 10),  # Cap_exam = 10 * 5 = 50
    ("B-D101", "Lecture Hall D-101", "LECTURE", 80, 8, 10),                    # Cap_exam = 8 * 5 = 40
    ("B-D102", "Lecture Hall D-102", "LECTURE", 80, 8, 10),                    # Cap_exam = 8 * 5 = 40
    ("B-D201", "Lecture Hall D-201", "LECTURE", 64, 8, 8),                     # Cap_exam = 8 * 4 = 32
    ("B-D202", "Lecture Hall D-202", "LECTURE", 64, 8, 8),                     # Cap_exam = 8 * 4 = 32
    ("B-D301", "Seminar Classroom D-301", "LECTURE", 48, 6, 8),                # Cap_exam = 6 * 4 = 24
    ("LAB-SE1", "Software Engineering Lab 1", "LAB", 90, 9, 10),               # Cap_exam = 9 * 5 = 45
    ("LAB-SE2", "Software Engineering Lab 2", "LAB", 72, 8, 9),                # Cap_exam = 8 * 5 = 40
    ("LAB-AI", "AI & Data Science Computer Lab", "LAB", 60, 6, 10),            # Cap_exam = 6 * 5 = 30
]


# 5. Araştırma Görevlileri (Gözetmenler / Invigilators)
ATU_TAS = [
    ("TA-01", "Res. Asst. Ali Vural"),
    ("TA-02", "Res. Asst. Ayşe Yıldırım"),
    ("TA-03", "Res. Asst. Berkay Doğan"),
    ("TA-04", "Res. Asst. Ceren Korkmaz"),
    ("TA-05", "Res. Asst. Furkan Şen"),
    ("TA-06", "Res. Asst. Gizem Aksoy"),
    ("TA-07", "Res. Asst. Hakan Tekin"),
    ("TA-08", "Res. Asst. İrem Bulut"),
]


def seed_atu_dataset(db: Session) -> dict[str, int]:
    """
    Veritabanı boşsa ATÜ Yazılım Mühendisliği başlangıç veri setini yükler.
    İdempotent çalışır: Veri zaten yüklüyse mevcut kayıt sayılarını döndürür.
    """
    existing_course_count = db.scalar(select(Course.id).limit(1))
    if existing_course_count is not None:
        return {
            "courses": db.query(Course).count(),
            "prerequisites": db.query(CoursePrerequisite).count(),
            "instructors": db.query(Instructor).count(),
            "rooms": db.query(Room).count(),
            "students": db.query(Student).count(),
            "enrollments": db.query(Enrollment).count(),
            "teaching_assistants": db.query(TeachingAssistant).count(),
        }

    # 1. Öğretim Elemanlarını ve Haftalık Müsaitliklerini Ekle
    instructor_map: dict[str, Instructor] = {}
    for idx, (code, full_name, title, max_hrs) in enumerate(ATU_INSTRUCTORS):
        inst = Instructor(
            code=code,
            full_name=full_name,
            title=title,
            department="Software Engineering",
            max_weekly_hours=max_hrs,
        )
        db.add(inst)
        db.flush()
        instructor_map[code] = inst

        # Her hoca için 5 gün x 8 saat dilimi müsaitlik ve tercih profili oluştur
        for day in range(1, 6):
            for slot in range(1, 9):
                # Gerçekçi kısıt: Her hocanın haftada belirli bir yarım günü araştırma/idari izinli olsun
                blocked_day = (idx % 5) + 1
                is_avail = not (day == blocked_day and slot in (7, 8))
                # Sabah ilk saat (slot=1) ve akşam son saat (slot=8) için yumuşak tercih cezası
                pref_penalty = 2 if slot in (1, 8) else 0
                db.add(
                    InstructorAvailability(
                        instructor_id=inst.id,
                        day_of_week=day,
                        slot_index=slot,
                        is_available=is_avail,
                        preference_penalty=pref_penalty,
                    )
                )

    # 2. Müfredat Derslerini Ekle
    course_map: dict[str, Course] = {}
    for (
        code,
        name,
        sem,
        ects,
        th_hrs,
        lab_hrs,
        is_mand,
        req_lab,
        enrolled,
        inst_code,
    ) in ATU_COURSES:
        course = Course(
            code=code,
            name=name,
            semester=sem,
            ects=ects,
            theory_hours=th_hrs,
            lab_hours=lab_hrs,
            is_mandatory=is_mand,
            requires_lab_room=req_lab,
            enrolled_count=enrolled,
            instructor_id=instructor_map[inst_code].id,
        )
        db.add(course)
        db.flush()
        course_map[code] = course

    # 3. Önkoşul ve Yan-Koşul Kenarlarını (DAG Edges) Ekle
    for prereq_code, target_code, is_coreq in ATU_PREREQUISITES:
        db.add(
            CoursePrerequisite(
                prerequisite_course_id=course_map[prereq_code].id,
                target_course_id=course_map[target_code].id,
                is_corequisite=is_coreq,
            )
        )

    # 4. Amfileri ve Bilgisayar Laboratuvarlarını Ekle
    for code, name, r_type, cap, rows, cols in ATU_ROOMS:
        db.add(
            Room(
                code=code,
                name=name,
                room_type=r_type,
                normal_capacity=cap,
                seat_rows=rows,
                seat_cols=cols,
            )
        )

    # 5. Araştırma Görevlilerini ve Lisansüstü Ders Kısıtlarını Ekle
    for idx, (ta_code, ta_name) in enumerate(ATU_TAS):
        ta = TeachingAssistant(
            code=ta_code,
            full_name=ta_name,
            current_workload_score=0.0,
        )
        db.add(ta)
        db.flush()
        # Her Arş. Gör. için sınav haftasında kendi yüksek lisans seminer/ders saatini kapat
        db.add(
            TAUnavailability(
                ta_id=ta.id,
                exam_day=(idx % 5) + 1,
                session_index=(idx % 4) + 1,
                reason="MSc/PhD Graduate Seminar Course",
            )
        )

    # 6. KVKK Uyumlu Anonim / Sentetik Öğrenciler ve Ders Kayıtları (Düzenli + Alttan Alan Düzensiz)
    # Güz dönemi (1., 3., 5., 7. yarıyıl) öğrencileri + alttan kritik ders tekrarlayan (irregular) öğrenciler
    student_seq = 1001
    active_fall_semesters = [1, 3, 5, 7]
    courses_by_sem: dict[int, list[Course]] = {}
    for c in course_map.values():
        courses_by_sem.setdefault(c.semester, []).append(c)

    for sem in active_fall_semesters:
        # Her aktif dönemde 20 düzenli (regular) öğrenci
        for i in range(20):
            st_num = f"22060{student_seq}"
            student_seq += 1
            st = Student(
                student_number=st_num,
                full_name=f"Synthetic Student {st_num[-4:]}",
                current_semester=sem,
                is_irregular=False,
            )
            db.add(st)
            db.flush()
            for c in courses_by_sem.get(sem, []):
                db.add(
                    Enrollment(
                        student_id=st.id,
                        course_id=c.id,
                        academic_term="2026-FALL",
                        status="ENROLLED",
                        is_retake=False,
                    )
                )

    # 3. ve 5. dönemde olup alttan kritik ders (CSE101, MATH101 veya CSE201, MATH203) tekrarlayan
    # 20 düzensiz (irregular) öğrenci oluştur (Modül 1 C_DAG ve Modül 3 sınav çakışması testleri için)
    irregular_scenarios = [
        # 3. dönem öğrencisi CSE101'den kalmış -> CSE201 alamaz ama SE201, MATH201, MATH203 + alttan CSE101 alır
        (3, ["CSE101", "SE201", "MATH201", "MATH203", "CSE203"], {"CSE101"}),
        # 5. dönem öğrencisi CSE201'den kalmış -> CSE303 alamaz ama SE301, SE303, SE305 + alttan CSE201 alır
        (5, ["CSE201", "SE301", "SE303", "SE305"], {"CSE201"}),
    ]
    for sem, course_codes, retake_codes in irregular_scenarios:
        for _ in range(10):
            st_num = f"22060{student_seq}"
            student_seq += 1
            st = Student(
                student_number=st_num,
                full_name=f"Synthetic Irregular Student {st_num[-4:]}",
                current_semester=sem,
                is_irregular=True,
            )
            db.add(st)
            db.flush()
            for c_code in course_codes:
                db.add(
                    Enrollment(
                        student_id=st.id,
                        course_id=course_map[c_code].id,
                        academic_term="2026-FALL",
                        status="ENROLLED",
                        is_retake=(c_code in retake_codes),
                    )
                )

    db.commit()

    return {
        "courses": db.query(Course).count(),
        "prerequisites": db.query(CoursePrerequisite).count(),
        "instructors": db.query(Instructor).count(),
        "rooms": db.query(Room).count(),
        "students": db.query(Student).count(),
        "enrollments": db.query(Enrollment).count(),
        "teaching_assistants": db.query(TeachingAssistant).count(),
    }
