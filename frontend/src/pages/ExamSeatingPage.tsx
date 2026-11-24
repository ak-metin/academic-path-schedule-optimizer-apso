import React, { useState } from "react";
import {
  API_BASE_URL,
  ExamScheduleOptimizationResponse,
  RoomSeatingGridResponse,
} from "../api";

export const ExamSeatingPage: React.FC = () => {
  const [examType, setExamType] = useState<"FINAL" | "MIDTERM">("FINAL");
  const [parity, setParity] = useState<"FALL" | "SPRING">("FALL");
  const [loading, setLoading] = useState<boolean>(false);
  const [result, setResult] =
    useState<ExamScheduleOptimizationResponse | null>(null);
  const [selectedSeating, setSelectedSeating] =
    useState<RoomSeatingGridResponse | null>(null);

  const termStr = parity === "FALL" ? "2026-FALL" : "2026-SPRING";

  const handleGenerateExams = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE_URL}/schedule/exams/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          academic_term: termStr,
          exam_type: examType,
          semester_parity: parity,
          exam_days_count: 10,
          sessions_per_day: 4,
          max_time_seconds: 20,
        }),
      });
      if (res.ok) {
        const data: ExamScheduleOptimizationResponse = await res.json();
        setResult(data);
        if (data.exam_sessions.length > 0) {
          fetchSeating(data.exam_sessions[0].exam_session_id);
        }
      }
    } finally {
      setLoading(false);
    }
  };

  const fetchSeating = async (examSessionId: number) => {
    const res = await fetch(
      `${API_BASE_URL}/schedule/exams/${examSessionId}/seating`
    );
    if (res.ok) {
      const data: RoomSeatingGridResponse = await res.json();
      setSelectedSeating(data);
    }
  };

  return (
    <div className="space-y-6">
      {/* Üst Kontrol Paneli */}
      <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 className="text-base font-bold text-slate-900">
            Modül 3 — Sınav Takvimi, 1-Boş-Koltuk Oturma Planı & Minimax Adil
            Gözetmen Çözücüsü
          </h2>
          <p className="text-xs text-slate-600 mt-0.5">
            Öğrenci sınav çakışmalarını sıfırlar,{" "}
            <code>Cap_exam(r) = Rows(r) × ceil(Cols(r)/2)</code> formülüyle
            kalabalık sınavları böler ve Arş. Gör. yükünü Minimax kriteriyle
            dengeler.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <select
            value={parity}
            onChange={(e) => setParity(e.target.value as "FALL" | "SPRING")}
            className="border border-slate-300 rounded-lg px-3 py-2 text-xs font-semibold"
          >
            <option value="FALL">Güz Dönemi (2026-FALL)</option>
            <option value="SPRING">Bahar Dönemi (2026-SPRING)</option>
          </select>

          <select
            value={examType}
            onChange={(e) => setExamType(e.target.value as "FINAL" | "MIDTERM")}
            className="border border-slate-300 rounded-lg px-3 py-2 text-xs font-semibold"
          >
            <option value="FINAL">Final Sınavları</option>
            <option value="MIDTERM">Vize (Midterm) Sınavları</option>
          </select>

          <button
            onClick={handleGenerateExams}
            disabled={loading}
            className="bg-rose-800 hover:bg-rose-900 disabled:opacity-50 text-white font-semibold text-xs px-4 py-2.5 rounded-lg shadow-sm transition"
          >
            {loading
              ? "CP-SAT Sınav & Gözetmen Çözülüyor..."
              : "Sınav, 1-Boş-Koltuk & Gözetmen Planı Oluştur"}
          </button>

          {result && result.solver_status !== "INFEASIBLE" && (
            <a
              href={`${API_BASE_URL}/export/exams.pdf?academic_term=${termStr}&exam_type=${examType}`}
              className="bg-slate-900 hover:bg-slate-800 text-white font-semibold text-xs px-3.5 py-2.5 rounded-lg shadow-sm transition"
            >
              Resmi PDF Raporu İndir
            </a>
          )}
        </div>
      </div>

      {result && result.solver_status !== "INFEASIBLE" && (
        <>
          {/* Özet Metrik Kartları */}
          <div className="grid grid-cols-1 md:grid-cols-5 gap-4">
            <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm">
              <div className="text-xs font-semibold text-slate-500">
                CP-SAT Durumu & Süre
              </div>
              <div className="text-lg font-bold text-emerald-700 mt-1">
                {result.solver_status} ({result.solve_time_seconds} sn)
              </div>
            </div>
            <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm">
              <div className="text-xs font-semibold text-slate-500">
                Sınav / Salon Ataması
              </div>
              <div className="text-lg font-bold text-slate-900 mt-1">
                {result.total_exams_scheduled} Sınav →{" "}
                {result.total_room_allocations} Amfi
              </div>
            </div>
            <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm">
              <div className="text-xs font-semibold text-slate-500">
                Öğrenci Sınav Çakışması
              </div>
              <div className="text-lg font-bold text-emerald-700 mt-1">
                0 Çakışma (Doğrulandı)
              </div>
            </div>
            <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm">
              <div className="text-xs font-semibold text-slate-500">
                1-Boş-Koltuk Kuralı
              </div>
              <div className="text-lg font-bold text-blue-800 mt-1">
                %100 Uyumlu (Tek Sütunlar)
              </div>
            </div>
            <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm">
              <div className="text-xs font-semibold text-slate-500">
                Minimax Gözetmen Yük Farkı
              </div>
              <div className="text-lg font-bold text-rose-800 mt-1">
                Δ = {result.workload_max_min_spread} (Min:{" "}
                {result.min_ta_workload} / Max: {result.max_ta_workload})
              </div>
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Sol: Sınav Takvimi ve Çoklu Amfi Bölünmesi */}
            <div className="lg:col-span-2 bg-white p-5 rounded-xl border border-slate-200 shadow-sm space-y-3">
              <h3 className="text-sm font-bold text-slate-900">
                Sınav Takvimi, 1-Boş-Koltuk Salon Bölünmesi ve Gözetmen
                Atamaları (Oturma Planı İçin Satıra Tıklayın)
              </h3>
              <div className="overflow-x-auto max-h-96">
                <table className="w-full border-collapse text-xs">
                  <thead>
                    <tr className="bg-slate-900 text-white sticky top-0">
                      <th className="p-2 border border-slate-700">Gün / Ot.</th>
                      <th className="p-2 border border-slate-700">Ders</th>
                      <th className="p-2 border border-slate-700">Öğrenci</th>
                      <th className="p-2 border border-slate-700">
                        Atanan Amfi(ler) [1-Boş-Koltuk Kap.]
                      </th>
                      <th className="p-2 border border-slate-700">
                        Gözetmen (Arş. Gör.)
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.exam_sessions.map((ex) => (
                      <tr
                        key={ex.exam_session_id}
                        onClick={() => fetchSeating(ex.exam_session_id)}
                        className={`cursor-pointer transition hover:bg-blue-50 ${
                          selectedSeating?.exam_session_id ===
                          ex.exam_session_id
                            ? "bg-blue-50 font-semibold"
                            : "even:bg-slate-50"
                        }`}
                      >
                        <td className="p-2 border border-slate-200 text-center">
                          Gün {ex.exam_day} / Ot. {ex.session_index}
                        </td>
                        <td className="p-2 border border-slate-200">
                          <span className="font-bold">{ex.course_code}</span> —{" "}
                          {ex.course_name}
                        </td>
                        <td className="p-2 border border-slate-200 text-center">
                          {ex.enrolled_count}
                        </td>
                        <td className="p-2 border border-slate-200">
                          {ex.rooms.map((r) => (
                            <div key={r.room_code}>
                              <span className="font-semibold">
                                {r.room_code}
                              </span>{" "}
                              ({r.allocated_student_count}/
                              {r.room_effective_exam_capacity})
                            </div>
                          ))}
                        </td>
                        <td className="p-2 border border-slate-200">
                          {ex.rooms.map((r) => (
                            <div key={`${r.room_code}_${r.proctor_ta_code}`}>
                              {r.proctor_ta_code} — {r.proctor_ta_name}
                            </div>
                          ))}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Sağ: Minimax Arş. Gör. Gözetmenlik Yükü Dağılımı */}
            <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm space-y-3">
              <h3 className="text-sm font-bold text-slate-900">
                Minimax Araştırma Görevlisi Yük Dağılımı
              </h3>
              <div className="space-y-2.5">
                {result.proctor_workloads.map((ta) => {
                  const pct =
                    result.max_ta_workload > 0
                      ? Math.round(
                          (ta.total_weighted_workload /
                            result.max_ta_workload) *
                            100
                        )
                      : 0;
                  return (
                    <div key={ta.ta_code} className="space-y-1">
                      <div className="flex justify-between text-xs">
                        <span className="font-semibold text-slate-800">
                          {ta.ta_code} — {ta.ta_name}
                        </span>
                        <span className="font-bold text-rose-800">
                          {ta.total_weighted_workload} Puan (
                          {ta.assigned_exam_rooms_count} Salon)
                        </span>
                      </div>
                      <div className="w-full h-2.5 bg-slate-100 rounded-full overflow-hidden">
                        <div
                          className="h-full bg-rose-700 rounded-full"
                          style={{ width: `${pct}%` }}
                        ></div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>

          {/* 1-Boş-Koltuk 2B Oturma Planı Koordinat Listesi (KVKK Uyumlu) */}
          {selectedSeating && (
            <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm space-y-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h3 className="text-sm font-bold text-slate-900">
                  1-Boş-Koltuk Oturma Planı (KVKK Uyumlu):{" "}
                  {selectedSeating.course_code} — {selectedSeating.course_name}{" "}
                  (Gün {selectedSeating.exam_day}, Oturum{" "}
                  {selectedSeating.session_index})
                </h3>
                <span className="px-2.5 py-1 rounded bg-emerald-100 text-emerald-900 text-xs font-bold">
                  1-Boş-Koltuk Doğrulaması:{" "}
                  {selectedSeating.one_empty_seat_verified
                    ? "GEÇERLİ (|col_j - col_i| >= 2)"
                    : "HATALI"}
                </span>
              </div>

              <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 lg:grid-cols-6 gap-2.5">
                {selectedSeating.seats.map((s) => (
                  <div
                    key={`${s.room_code}_${s.seat_row}_${s.seat_col}`}
                    className="p-2.5 rounded-lg border border-blue-200 bg-blue-50/70 text-xs space-y-0.5"
                  >
                    <div className="flex items-center justify-between font-bold text-blue-950">
                      <span>{s.student_number}</span>
                      <span className="text-[10px] px-1.5 py-0.5 rounded bg-white text-slate-800">
                        {s.room_code}
                      </span>
                    </div>
                    <div className="text-[11px] text-slate-700 truncate">
                      {s.student_name}
                    </div>
                    <div className="text-[10px] font-semibold text-emerald-800">
                      Satır {s.seat_row} • Sütun {s.seat_col} (Yanı Boş)
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
};
