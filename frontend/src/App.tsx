import React, { useEffect, useState } from "react";
import { API_BASE_URL, SystemDatasetSummary } from "./api";
import { CurriculumDAGPage } from "./pages/CurriculumDAGPage";
import { WeeklySchedulePage } from "./pages/WeeklySchedulePage";
import { ExamSeatingPage } from "./pages/ExamSeatingPage";

type TabType = "DAG" | "WEEKLY" | "EXAM";

export const App: React.FC = () => {
  const [activeTab, setActiveTab] = useState<TabType>("DAG");
  const [summary, setSummary] = useState<SystemDatasetSummary | null>(null);

  useEffect(() => {
    fetch(`${API_BASE_URL}/dataset/summary`)
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => setSummary(data))
      .catch(() => null);
  }, []);

  return (
    <div className="min-h-screen flex flex-col">
      {/* Üst Başlık Çubuğu */}
      <header className="bg-slate-900 text-white border-b border-slate-800">
        <div className="max-w-7xl mx-auto px-4 py-4 flex flex-wrap items-center justify-between gap-4">
          <div>
            <div className="text-xs font-semibold uppercase tracking-wider text-amber-400">
              Adana Alparslan Türkeş Science and Technology University (ATÜ) •
              Software Engineering
            </div>
            <h1 className="text-lg md:text-xl font-bold tracking-tight">
              Academic Path & Schedule Optimizer (APSO)
            </h1>
          </div>

          {summary && (
            <div className="flex flex-wrap items-center gap-2 text-xs">
              <span className="px-2.5 py-1 rounded-full bg-slate-800 border border-slate-700">
                <b>{summary.total_courses}</b> Ders /{" "}
                <b>{summary.total_prerequisite_edges}</b> Önkoşul
              </span>
              <span className="px-2.5 py-1 rounded-full bg-slate-800 border border-slate-700">
                <b>{summary.total_rooms}</b> Amfi & Lab
              </span>
              <span className="px-2.5 py-1 rounded-full bg-slate-800 border border-slate-700">
                <b>{summary.total_students}</b> KVKK Öğrenci (
                {summary.irregular_students} Düzensiz)
              </span>
              <span className="px-2.5 py-1 rounded-full bg-slate-800 border border-slate-700">
                <b>{summary.total_teaching_assistants}</b> Arş. Gör.
              </span>
            </div>
          )}
        </div>

        {/* 3 Çekirdek Modül Sekme Menüsü */}
        <div className="max-w-7xl mx-auto px-4 flex flex-wrap gap-2 pb-3">
          <button
            onClick={() => setActiveTab("DAG")}
            className={`px-4 py-2 rounded-lg text-xs font-bold transition ${
              activeTab === "DAG"
                ? "bg-emerald-600 text-white shadow"
                : "bg-slate-800 text-slate-300 hover:bg-slate-700"
            }`}
          >
            Modül 1: Müfredat DAG & Ders Kalma Simülasyonu
          </button>

          <button
            onClick={() => setActiveTab("WEEKLY")}
            className={`px-4 py-2 rounded-lg text-xs font-bold transition ${
              activeTab === "WEEKLY"
                ? "bg-blue-600 text-white shadow"
                : "bg-slate-800 text-slate-300 hover:bg-slate-700"
            }`}
          >
            Modül 2: Haftalık Ders Programı CP-SAT Çözücü
          </button>

          <button
            onClick={() => setActiveTab("EXAM")}
            className={`px-4 py-2 rounded-lg text-xs font-bold transition ${
              activeTab === "EXAM"
                ? "bg-rose-700 text-white shadow"
                : "bg-slate-800 text-slate-300 hover:bg-slate-700"
            }`}
          >
            Modül 3: Sınav, 1-Boş-Koltuk & Minimax Gözetmen CSP
          </button>
        </div>
      </header>

      {/* Ana İçerik */}
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 py-6">
        {activeTab === "DAG" && <CurriculumDAGPage />}
        {activeTab === "WEEKLY" && <WeeklySchedulePage />}
        {activeTab === "EXAM" && <ExamSeatingPage />}
      </main>

      {/* Alt Bilgi */}
      <footer className="bg-white border-t border-slate-200 py-3 text-center text-xs text-slate-500">
        Academic Path & Schedule Optimizer (APSO) v1.0 • NetworkX DAG + Google
        OR-Tools CP-SAT • ATÜ Department of Software Engineering
      </footer>
    </div>
  );
};

export default App;
