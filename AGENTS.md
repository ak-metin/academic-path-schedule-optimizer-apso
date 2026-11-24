# Proje Kuralları — Academic Path & Schedule Optimizer (APSO)

Bu belge, **Academic Path & Schedule Optimizer (APSO)** projesi üzerinde çalışan yapay zeka ajanlarının (agent) ve geliştiricilerin uyması gereken bağlayıcı mimari, algoritmik ve yazılımsal kuralları tanımlar.

---

## 1. Genel Yaklaşım ve Çalışma Disiplini
- **Varsayımda Bulunma:** Emin olmadığın dosya yollarını, fonksiyon imzalarını, veritabanı tablo/kolon adlarını, Pydantic şemalarını veya paket API'lerini (`ortools.sat.python.cp_model`, `networkx`, `sqlalchemy`, `fastapi`) tahmin etme; önce ilgili dosyaları oku veya netleştir.
- **Kapsam Kontrolü:** Değişiklik yapmadan önce kapsamı netleştir; onaylanan teknoloji yığını (**Python 3.12, FastAPI, Google OR-Tools CP-SAT, NetworkX, PostgreSQL 16, SQLAlchemy 2.0, React 18, TypeScript, Tailwind CSS, Pandas/OpenPyXL, ReportLab**) dışına çıkacak gereksiz dosya veya bağımlılık eklemekten kaçın.
- **Dil ve Dokümantasyon Standardı:** Kullanıcıya yapılan açıklamaları ve kod içi kritik algoritma/kısıt yorumlarını (özellikle DAG kritik yol hesaplamaları ve CP-SAT matematiksel kısıt formüllerini) **Türkçe** yaz; değişken, fonksiyon, sınıf ve veritabanı tablo/kolon isimlendirmelerini ise standart **İngilizce** (`snake_case` / `PascalCase`) olarak tut.
- **Üç Komut Kuralı (Deliverable Standardı):** Projeye eklenecek her yeni servis veya bağımlılık, projenin `docker compose up --build` ile **en fazla 3 komutta** ayağa kalkma ve `pytest` ile test edilebilme kuralını bozmamalıdır.

---

## 2. Üç Çekirdek Modül (Engine) ve Algoritmik Kurallar
APSO birbirine sıkı bağlı 3 çekirdek motordan oluşur. Bir motorda değişiklik yaparken diğer motorlarla olan veri sözleşmesini (contract) bozma:

1. **Modül 1 — Curriculum Graph Engine (`NetworkX` & DAG):**
   - Müfredat her zaman **Yönlü Çevrimsiz Graf (Directed Acyclic Graph - DAG)** olmak zorundadır. Veritabanına yeni bir önkoşul (`prerequisite`) eklenirken veya güncellenirken mutlaka çevrim kontrolü (`cycle detection` / topolojik sıralama) yapılmalı; döngüsel bağımlılık (`A -> B -> A`) varsa işlem `HTTP 422` ile reddedilmelidir.
   - Öğrenci ders kalma simülasyonlarında (*Critical Path Analysis*), öğrencinin kaldığı dersin kilitlediği tüm alt/üst dönem dersleri (`transitive closure`) ve dönemlik **AKTS (ECTS) üst sınırları** (normal 30 AKTS, üstten/alttan kurtarma senaryosu 40 AKTS) hesaba katılmalıdır.
   - Modül 1'in ürettiği **Çakışmazlık Matrisi ($C_{DAG}$)** (aynı dönem zorunlu dersleri, yan-koşul dersleri ve alttan en sık birlikte alınan kritik ders çiftleri), Modül 2'nin doğrudan zorunlu girdisidir.

2. **Modül 2 — Course Scheduling Engine (`Google OR-Tools CP-SAT`):**
   - **Hard Constraints (Kesin Kısıtlar):** Oda kapasitesi aşımı, aynı odada veya aynı öğretim elemanında saat çakışması, laboratuvar dersinin normal amfiye atanması ve Modül 1'den gelen $C_{DAG}$ çakışmazlık kuralları **asla** ihlal edilemez (0 tolerans).
   - **Soft Constraints (Yumuşak Kısıtlar):** Öğrencilerin aynı gün içindeki dersleri arasındaki boş saatlerin (*idle gaps*) minimize edilmesi ve öğretim elemanı saat tercihleri ağırlıklı ceza fonksiyonu (*weighted penalty objective*) ile optimize edilmelidir.
   - **Çözülemezlik Tanısı (Unsat Core & Timeout):** CP-SAT çözücüsü sonsuz döngüye bırakılmamalı (`max_time_in_seconds` sınırı, örn. 20–30 sn tanımlanmalı); kısıtlar aşırı sıkı olduğunda sadece `"INFEASIBLE"` döndürmek yerine `Assumptions` / gevşetme (*slack*) mekanizmasıyla hangi dersin, hocanın veya amfi kapasitesinin darboğaz yarattığını anlaşılır Türkçe mesajla raporlamalıdır.

3. **Modül 3 — Exam & Proctor Allocation Module (`Exam & Seating & Proctor CSP`):**
   - **Öğrenci Sınav Çakışması:** Ortak kayıtlı öğrencisi (`enrollments`) bulunan hiçbir iki dersin sınavı aynı oturuma (`exam_session`) atanamaz.
   - **1-Boş-Koltuk Kuralı (1-Empty-Seat Rule):** Sınav oturma planı oluşturulurken amfilerin fiziksel kapasitesi değil, yan yana iki öğrenci arasında en az 1 boş koltuk bırakan efektif sınav kapasitesi ($\text{Cap}_{\text{exam}}(r) = \text{Rows}(r) \times \lceil \text{Cols}(r) / 2 \rceil$) esas alınmalıdır. Tek amfiye sığmayan kalabalık sınavlar otomatik olarak birden fazla salona bölünmelidir.
   - **Adil Gözetmen (Arş. Gör.) Dağıtımı:** Araştırma görevlileri kendi lisansüstü ders saatleriyle çakışmayacak şekilde atanmalı ve görev yükü dağılımında **Minimax adalet kriteri** ($\min (L_{\max} - L_{\min})$) uygulanmalıdır.

---

## 3. Veritabanı, Veri Bütünlüğü ve KVKK Uyumu
- **Tek Gerçek Kaynak (Single Source of Truth):** PostgreSQL veritabanı şeması (SQLAlchemy modelleri ve migration dosyaları) tek gerçek kaynaktır. Yeni bir sorgu, çözücü girdisi veya API endpoint'i yazarken mevcut model ve kolon tanımlarını birebir esas al.
- **Şema Değişiklikleri:** Tablo, kolon veya yabancı anahtar (`ForeignKey`) yapısında değişiklik gerekiyorsa bunu sessizce yapma; açıkça belirt ve migration/seed güncelleme adımıyla birlikte ele al.
- **Girdi Doğrulaması:** Tüm dış girdileri (form, query, JSON body ve yüklenen Excel/CSV dosyaları) sunucu tarafında **Pydantic v2** şema doğrulamasından geçirmeden veritabanına veya CP-SAT çözücüsüne gönderme.
- **KVKK ve Kişisel Veri Gizliliği:** Veritabanında, seed dosyalarında, Excel/PDF çıktılarında veya test verilerinde gerçek öğrencilere ait TC Kimlik No, gerçek telefon/adres gibi hassas kişisel veriler (PII) **bulundurulmamalı**; anonimleştirilmiş veya sentetik öğrenci numaraları (`22060xxxx` formatında) kullanılmalıdır.

---

## 4. Güvenlik, Hata Yönetimi ve Kod Kalitesi
- **Gizli Bilgiler:** Veritabanı bağlantı dizelerini (`DATABASE_URL`), gizli anahtarları veya yapılandırma sabitlerini koda gömme (*hardcode etme*); `.env` ve ortam değişkenleri üzerinden oku.
- **Hata Yönetimi:** Hataları `except Exception: pass` gibi bloklarla sessizce yutma; anlamlı HTTP durum kodları (`400`, `404`, `409`, `422`, `500`), yapılandırılmış hata yanıtları ve loglama kullan.
- **Doğrulama ve Test Zorunluluğu:** Bir özellik, veritabanı modeli veya optimizasyon kısıtı tamamlandığında ilgili test (`pytest`), tip kontrolü (`tsc` / `flake8` / `ruff`) veya doğrulama komutlarını çalıştırarak sonucu kullanıcıya raporla.
