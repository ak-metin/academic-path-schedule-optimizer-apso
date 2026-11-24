"""
Uygulama ve Veritabanı Yapılandırma Modülü.
Tüm bağlantı dizeleri ve çözücü parametreleri gizli bilgi güvenliği kuralı
gereği ortam değişkenlerinden (.env) okunur.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """APSO sistem genel ayarları ve CP-SAT çözücü sabitleri."""

    app_name: str = "Academic Path & Schedule Optimizer (APSO)"
    app_version: str = "1.0.0"
    app_env: str = "development"

    # Veritabanı bağlantı dizesi (Varsayılan yerel geliştirme/test için SQLite,
    # Docker veya prod ortamında DATABASE_URL üzerinden PostgreSQL 16 kullanılır)
    database_url: str = "sqlite:///./apso_local.db"

    # Uygulama başlangıcında veritabanı boşsa ATÜ Yazılım Müh. verisini otomatik yükle
    auto_seed_on_startup: bool = True

    # Google OR-Tools CP-SAT zaman aşımı ve paralel iş parçacığı sınırları
    cpsat_max_time_seconds: int = 25
    cpsat_num_search_workers: int = 8

    # AKTS (ECTS) dönemlik kredi üst sınırları
    normal_semester_ects_cap: int = 30
    recovery_semester_ects_cap: int = 40

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
