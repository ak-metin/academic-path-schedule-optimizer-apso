import React, { useState } from "react";
import {
  API_BASE_URL,
  WeeklyScheduleOptimizationResponse,
  WeeklySlotAssignmentRead,
} from "../api";

const DAYS = [
  { id: 1, label: "Pazartesi" },
  { id: 2, label: "Salı" },
  { id: 3, label: "Çarşamba" },
  { id: 4, label: "Perşembe" },
  { id: 5, label: "Cuma" },
];

const SLOTS = [
  { id: 1, time: "08:30 - 09:20" },
  { id: 2, time: "09:30 - 10:20" },
  { id: 3, time: "10:30 - 11:20" },
  { id: 4, time: "11:30 - 12:20" },
  { id: 5, time: "13:30 - 14:20" },
  { id: 6, time: "14:30 - 15:20" },
  { id: 7, time: "15:30 - 16:20" },
  { id: 8, time: "16:30 - 17:20" },
];

export const WeeklySchedulePage: React.FC = () => {
  const [parity, setParity] = useState<"FALL" | "SPRING">("FALL");
  const [selectedSemester, setSelectedSemester] = useState<number>(1);
  const [loading, setLoading] = useState<boolean>(false);
  const [result, setResult] =
    useState<WeeklyScheduleOptimizationResponse | null>(null);

  const handleOptimize = async () => {
    setLoading(true);
    try {
      const term = parity === "FALL" ? "2026-FALL" : "2026-SPRING";
      const res = await fetch(`${API_BASE_URL}/schedule/weekly/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          academic_term: term,
          semester_parity: parity,
          max_time_seconds: 20,
          idle_gap_weight: 10,
          instructor_preference_weight: 5,
        }),
      });
      if (res.ok) {
        const data: WeeklyScheduleOptimizationResponse = await res.json();
        setResult(data);
        setSelectedSemester(parity === "FALL" ? 1 : 2);
      }
    } finally {
      setLoading(false);
    }
  };

  const semesterOptions = parity === "FALL" ? [1, 3, 5, 7] : [2, 4, 6, 8];
  const filteredAssignments =
    result?.assignments.filter((a) => a.semester === selectedSemester) || [];

  const cellMap: Record<string, WeeklySlotAssignmentRead[]> = {};
  filteredAssignments.forEach((a) => {
    const key = `${a.day_of_week}_${a.slot_index}`;
    if (!cellMap[key]) cellMap[key] = [];
    cellMap[key].push(a);
  });

  const termStr = parity === "FALL" ? "2026-FALL" : "2026-SPRING";

  return (
    <div className="space-y-6">
      {/* Kontrol Çubuğu */}
      <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 className="text-base font-bold text-slate-900">
            Modül 2 — Google OR-Tools CP-SAT Haftalık Ders Programı Çözücüsü
          </h2>
          <p className="text-xs text-slate-600 mt-0.5">
            Modül 1&apos;den gelen <code>C_DAG</code> çakışmazlık matrisini,
            amfi/lab kapasitelerini ve hoca müsaitliklerini kesin kısıt (0
            tolerans) olarak uygular; öğrenci boş saatlerini minimize eder.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <select
            value={parity}
            onChange={(e) => setParity(e.target.value as "FALL" | "SPRING")}
            className="border border-slate-300 rounded-lg px-3 py-2 text-xs font-semibold"
          >
            <option value="FALL">Güz Dönemi (1, 3, 5, 7. Yarıyıl)</option>
            <option value="SPRING">Bahar Dönemi (2, 4, 6, 8. Yarıyıl)</option>
          </select>

          <button
            onClick={handleOptimize}
            disabled={loading}
            className="bg-blue-700 hover:bg-blue-800 disabled:opacity-50 text-white font-semibold text-xs px-4 py-2.5 rounded-lg shadow-sm transition"
          >
            {loading
              ? "CP-SAT Çözücü Çalışıyor..."
              : "Haftalık Programı CP-SAT ile Optimize Et"}
          </button>

          {result && result.solver_status !== "INFEASIBLE" && (
            <a
              href={`${API_BASE_URL}/export/weekly.xlsx?academic_term=${termStr}`}
              className="bg-emerald-700 hover:bg-emerald-800 text-white font-semibold text-xs px-3.5 py-2.5 rounded-lg shadow-sm transition"
            >
              Excel (.xlsx) İndir
            </a>
          )}
        </div>
      </div>

      {/* Çözücü Metrikleri veya Unsat Core Tanı Raporu */}
      {result && (
        <>
          {result.solver_status === "INFEASIBLE" ? (
            <div className="bg-red-50 border border-red-200 p-4 rounded-xl space-y-2">
              <div className="text-sm font-bold text-red-900">
                CP-SAT Çözülemezlik Tanısı (Unsat Core Raporu):
              </div>
              {result.unsat_diagnostics_tr.map((msg, idx) => (
                <div key={idx} className="text-xs text-red-800">
                  • {msg}
                </div>
              ))}
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-5 gap-4">
              <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm">
                <div className="text-xs text-slate-500 font-semibold">
                  CP-SAT Durumu & Süre
                </div>
                <div className="text-lg font-bold text-emerald-700 mt-1">
                  {result.solver_status} ({result.solve_time_seconds} sn)
                </div>
              </div>
              <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm">
                <div className="text-xs text-slate-500 font-semibold">
                  Zamanlanan Ders / Saat
                </div>
                <div className="text-lg font-bold text-slate-900 mt-1">
                  {result.total_courses_scheduled} Ders /{" "}
                  {result.total_slot_assignments} Saat
                </div>
              </div>
              <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm">
                <div className="text-xs text-slate-500 font-semibold">
                  C_DAG Kısıt Çifti (Modül 1)
                </div>
                <div className="text-lg font-bold text-blue-800 mt-1">
                  {result.c_dag_pairs_enforced} Çift (%100 Uygun)
                </div>
              </div>
              <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm">
                <div className="text-xs text-slate-500 font-semibold">
                  Toplam Öğrenci Boş Saati (Gap)
                </div>
                <div className="text-lg font-bold text-slate-900 mt-1">
                  {result.total_student_idle_gap_hours} Saat / Hafta
                </div>
              </div>
              <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm">
                <div className="text-xs text-slate-500 font-semibold">
                  Hoca Tercih Ceza Skoru
                </div>
                <div className="text-lg font-bold text-slate-900 mt-1">
                  {result.total_instructor_preference_penalty} Puan
                </div>
              </div>
            </div>
          )}

          {/* Yarıyıl Seçici ve 5x8 Haftalık Ders Programı Tablosu */}
          {result.solver_status !== "INFEASIBLE" && (
            <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm space-y-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  {semesterOptions.map((sem) => (
                    <button
                      key={sem}
                      onClick={() => setSelectedSemester(sem)}
                      className={`px-3.5 py-1.5 rounded-lg text-xs font-bold transition ${
                        selectedSemester === sem
                          ? "bg-slate-900 text-white"
                          : "bg-slate-100 text-slate-700 hover:bg-slate-200"
                      }`}
                    >
                      {sem}. Yarıyıl Ders Programı
                    </button>
                  ))}
                </div>
                <span className="text-xs text-slate-500">
                  Aynı dönem ve alttan ders alan düzensiz öğrenci kohortlarında
                  0 çakışma doğrulanmıştır.
                </span>
              </div>

              <div className="overflow-x-auto">
                <table className="w-full border-collapse text-xs">
                  <thead>
                    <tr className="bg-slate-900 text-white">
                      <th className="p-2.5 border border-slate-700 w-28">
                        Saat Dilimi
                      </th>
                      {DAYS.map((d) => (
                        <th
                          key={d.id}
                          className="p-2.5 border border-slate-700 text-center"
                        >
                          {d.label}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {SLOTS.map((s) => (
                      <tr key={s.id} className="even:bg-slate-50">
                        <td className="p-2.5 border border-slate-200 font-semibold text-center text-slate-700">
                          {s.time}
                        </td>
                        {DAYS.map((d) => {
                          const items = cellMap[`${d.id}_${s.id}`] || [];
                          return (
                            <td
                              key={d.id}
                              className="p-2 border border-slate-200 align-top h-20"
                            >
                              {items.map((item) => (
                                <div
                                  key={`${item.course_code}_${item.slot_index}`}
                                  className={`p-2 rounded-lg border text-left space-y-0.5 ${
                                    item.session_type === "LAB"
                                      ? "bg-purple-50 border-purple-300 text-purple-950"
                                      : "bg-blue-50 border-blue-200 text-blue-950"
                                  }`}
                                >
                                  <div className="flex items-center justify-between font-bold">
                                    <span>{item.course_code}</span>
                                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-white/80 font-semibold">
                                      {item.room_code}
                                    </span>
                                  </div>
                                  <div className="text-[11px] leading-tight">
                                    {item.course_name}
                                  </div>
                                  <div className="text-[10px] opacity-80">
                                    {item.instructor_name} ({item.enrolled_count}
                                    /{item.room_capacity})
                                  </div>
                                </div>
                              ))}
                            </td>
                          );
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
};
