# APSO — Kısa Kullanıcı Kılavuzu (Short User Manual)

Bu kılavuz, **Academic Path & Schedule Optimizer (APSO)** platformunun üç temel kullanıcı rolü (**Akademik Danışman / Öğrenci**, **Bölüm Ders Programı Koordinatörü** ve **Sınav / Gözetmenlik Komisyonu**) tarafından nasıl kullanılacağını adım adım açıklar.

---

## 1. Sisteme Giriş ve Hazır ATÜ Veri Seti

1. Uygulamayı `docker compose up --build` komutuyla başlattıktan sonra tarayıcınızdan **`http://localhost:5173`** adresine gidin.
2. Üst bilgi çubuğunda sistemde yüklü olan **ATÜ Yazılım Mühendisliği** veri seti özeti (**40 Ders / 36 Önkoşul**, **10 Amfi & Lab**, **100 KVKK Uyumlu Öğrenci**, **8 Arş. Gör.**) otomatik olarak görüntülenir.
3. Üst menüdeki 3 sekme aracılığıyla üç çekirdek modül arasında geçiş yapabilirsiniz.

---

## 2. Sekme 1 — Modül 1: Müfredat DAG & Ders Kalma Simülasyonu

Bu ekran hem **öğrencilerin ve akademik danışmanların** ders kalma senaryolarını simüle etmesi hem de **bölüm koordinatörünün** müfredat önkoşullarını ve Excel verilerini yönetmesi için kullanılır:

- **Ders Kalma Simülasyonu (Critical Path Analysis):**
  1. **Bulunduğu Dönem** açılır menüsünden öğrencinin tamamladığı yarıyılı (örn. `2. Yarıyıl Sonu`) seçin.
  2. İsteğe bağlı olarak **40 AKTS Kurtarma Sınırı** kutucuğunu işaretleyin (işaretlenmezse normal 30 AKTS sınırı uygulanır).
  3. Alttaki **8 Dönemlik Müfredat DAG Haritası** üzerinde öğrencinin kaldığı ders(ler)e (örn. `CSE102`) tıklayın.
  4. Seçilen ders **kırmızı** yanar; doğrudan kilitlediği dersler (örn. `CSE201`) **turuncu**, dolaylı (`transitive closure`) kilitlediği tüm üst dönem dersleri ise **açık turuncu** olarak işaretlenir.
  5. Üstteki **Akademik Danışman Karar Destek Raporu** kutusunda mezuniyetin kaç yarıyıl uzayacağı (`+Yarıyıl Gecikme`) ve kritik önkoşul zinciri (`CP`) anında listelenir.

- **DAG Çevrim Kontrolü (Cycle Detection — HTTP 422 Testi):**
  1. Sağdaki **DAG Çevrim Kontrolü Testi** panelinde **Önkoşul Ders** (örn. `SE403`) ve **Hedef Ders** (örn. `CSE101`) alanlarını doldurup **Önkoşul Ekle & Çevrim Kontrolü Yap** butonuna basın.
  2. Eğer eklenen bağ müfredatta döngü ($A \to B \to A$) oluşturuyorsa sistem işlemi `HTTP 422` hatası ve tam çevrim zinciriyle reddeder.

- **Excel (.xlsx) Veri İçe Aktarma (Pydantic v2 Doğrulamalı):**
  1. Sağ panelin alt kısmındaki **Şablon (.xlsx) İndir** bağlantısına tıklayarak örnek `Courses` ve `Rooms` sayfalarını içeren Excel şablonunu indirin.
  2. Kendi ders/amfi verilerinizi doldurup dosya seçici ile yükleyin. Sistem her satırı **Pydantic v2** şemasından geçirir; hatalı satır varsa satır numarasıyla Türkçe olarak listeler.

---

## 3. Sekme 2 — Modül 2: Haftalık Ders Programı CP-SAT Çözücü

1. Üst menüden **Modül 2: Haftalık Ders Programı CP-SAT Çözücü** sekmesine geçin.
2. Dönem seçiciden **Güz Dönemi (1, 3, 5, 7. Yarıyıl)** veya **Bahar Dönemi (2, 4, 6, 8. Yarıyıl)** seçimini yapıp **Haftalık Programı CP-SAT ile Optimize Et** butonuna tıklayın.
3. **Google OR-Tools CP-SAT** çözücüsü saniyeler içinde:
   - Modül 1'den gelen $C_{\text{DAG}}$ çakışmazlık kurallarını (aynı dönem dersleri, yan-koşullar ve alttan ders alan düzensiz öğrenci ders çiftleri),
   - Amfi kapasitelerini ve Bilgisayar Laboratuvarı (`LAB`) gereksinimlerini,
   - Öğretim elemanı müsaitliklerini kesin kısıt (0 tolerans) olarak sağlar; aynı zamanda öğrenci günlük boş saatlerini (*idle gaps*) minimize eder.
4. Çözüm tamamlandığında yarıyıl butonları (`1. Yarıyıl`, `3. Yarıyıl`, vb.) arasında geçiş yaparak 5×8 haftalık ders programı tablosunu inceleyebilir ve **Excel (.xlsx) İndir** butonuyla resmi Excel çıktısını indirebilirsiniz.
5. Eğer kısıtlar aşırı sıkıysa (çözülemez durum), ekranda kırmızı **CP-SAT Çözülemezlik Tanısı (Unsat Core Raporu)** kutusu açılır ve darboğaz yaratan ders/hoca/amfi Türkçe olarak raporlanır.

---

## 4. Sekme 3 — Modül 3: Sınav, 1-Boş-Koltuk & Minimax Gözetmen CSP

1. Üst menüden **Modül 3: Sınav, 1-Boş-Koltuk & Minimax Gözetmen CSP** sekmesine geçin.
2. Dönem (`Güz` / `Bahar`) ve Sınav Türü (`Final` / `Vize`) seçip **Sınav, 1-Boş-Koltuk & Gözetmen Planı Oluştur** butonuna tıklayın.
3. Sistem:
   - Ortak öğrencisi olan hiçbir iki dersin sınavını aynı oturuma koymaz (**0 Öğrenci Çakışması**),
   - Her amfinin fiziksel kapasitesi yerine **1-Boş-Koltuk Efektif Sınav Kapasitesini** ($\text{Cap}_{\text{exam}}(r) = \text{Rows}(r) \times \lceil \text{Cols}(r)/2 \rceil$) hesaplar ve tek amfiye sığmayan kalabalık sınavları (örn. 90 kişilik `MATH101`) otomatik olarak birden fazla amfiye böler,
   - Araştırma görevlilerini kendi lisansüstü ders saatleriyle çakışmadan **Minimax adalet kriterine** ($\min (L_{\max} - L_{\min})$) göre dengeli dağıtır.
4. Sol tablodaki herhangi bir sınav satırına tıkladığınızda alt bölümde o sınava giren öğrencilerin (`22060xxxx` KVKK uyumlu numaralarıyla) hangi amfide, hangi **Satır ve Tekil Sütun (`Col 1, 3, 5...` — Yanı Boş)** koordinatında oturacağı kartlar halinde gösterilir.
5. **Resmi PDF Raporu İndir** butonuna tıklayarak kapıya asılmaya hazır resmi sınav, gözetmen ve oturma planı PDF belgesini indirebilirsiniz.
