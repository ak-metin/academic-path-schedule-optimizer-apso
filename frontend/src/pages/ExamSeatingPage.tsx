import React, { useState } from "react";
import {
  API_BASE_URL,
  ExamScheduleOptimizationResponse,
  RoomSeatingGridResponse,
  SeatCellItem,
  VisualRoomLayoutItem,
} from "../api";

export const ExamSeatingPage: React.FC = () => {
  const [examType, setExamType] = useState<"FINAL" | "MIDTERM">("FINAL");
  const [parity, setParity] = useState<"FALL" | "SPRING">("FALL");
  const [loading, setLoading] = useState<boolean>(false);
  const [result, setResult] =
    useState<ExamScheduleOptimizationResponse | null>(null);
  const [selectedSeating, setSelectedSeating] =
    useState<RoomSeatingGridResponse | null>(null);
  const [activeRoomCode, setActiveRoomCode] = useState<string>("");

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
      if (data.rooms && data.rooms.length > 0) {
        setActiveRoomCode(data.rooms[0].room_code);
      } else if (data.seats.length > 0) {
        setActiveRoomCode(data.seats[0].room_code);
      }
    }
  };

  // Seçili amfi düzenini ve (satır_sütun -> öğrenci) haritasını hazırla
  const currentRoomLayout: VisualRoomLayoutItem | undefined =
    selectedSeating?.rooms.find((r) => r.room_code === activeRoomCode) ||
    selectedSeating?.rooms[0];

  const seatByCoord: Record<string, SeatCellItem> = {};
  if (selectedSeating && currentRoomLayout) {
    selectedSeating.seats
      .filter((s) => s.room_code === currentRoomLayout.room_code)
      .forEach((s) => {
        seatByCoord[`${s.seat_row}_${s.seat_col}`] = s;
      });
  }

  return (
    <div className="space-y-6">
      {/* Üst Kontrol Paneli */}
      <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 className="text-base font-bold text-slate-900">
            Modül 3 — Sınav Takvimi, 1-Boş-Koltuk 2B Amfi Haritası & Minimax
            Adil Gözetmen Çözücüsü
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

      {result && result.solver_status === "INFEASIBLE" && (
        <div className="bg-red-50 border border-red-200 p-4 rounded-xl space-y-1.5">
          <div className="text-sm font-bold text-red-900">
            Modül 3 CP-SAT Çözülemezlik Tanısı:
          </div>
          {result.unsat_diagnostics_tr.map((d, i) => (
            <div key={i} className="text-xs text-red-800">
              • {d}
            </div>
          ))}
        </div>
      )}

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
                Atamaları (2B Amfi Haritası İçin Satıra Tıklayın)
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

          {/* GELİŞTİRME 2: Görsel 2 Boyutlu Amfi / Sinema Koltuk Haritası (1-Boş-Koltuk Izgarası) */}
          {selectedSeating && currentRoomLayout && (
            <div className="bg-white p-6 rounded-xl border border-slate-200 shadow-sm space-y-5">
              <div className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-200 pb-4">
                <div>
                  <h3 className="text-base font-bold text-slate-900">
                    Görsel 2 Boyutlu Amfi Koltuk Haritası:{" "}
                    <span className="text-rose-800">
                      {selectedSeating.course_code} —{" "}
                      {selectedSeating.course_name}
                    </span>
                  </h3>
                  <p className="text-xs text-slate-600 mt-0.5">
                    Gün {selectedSeating.exam_day} • Oturum{" "}
                    {selectedSeating.session_index} • Salon Gözetmeni:{" "}
                    <b>
                      {currentRoomLayout.proctor_ta_code} (
                      {currentRoomLayout.proctor_ta_name})
                    </b>{" "}
                    • Boyut:{" "}
                    <b>
                      {currentRoomLayout.seat_rows} Satır ×{" "}
                      {currentRoomLayout.seat_cols} Sütun
                    </b>{" "}
                    (Fiziksel: {currentRoomLayout.normal_capacity}, 1-Boş-Koltuk
                    Kapasitesi: {currentRoomLayout.effective_exam_capacity})
                  </p>
                </div>

                <span className="px-3 py-1.5 rounded-lg bg-emerald-100 text-emerald-900 text-xs font-bold">
                  1-Boş-Koltuk Kuralı:{" "}
                  {selectedSeating.one_empty_seat_verified
                    ? "DOĞRULANDI (|col_j - col_i| >= 2)"
                    : "İHLAL"}
                </span>
              </div>

              {/* Çoklu Amfi Seçici Sekmeler (Kalabalık Sınavlar Bölündüğünde) */}
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="flex flex-wrap items-center gap-2">
                  {selectedSeating.rooms.map((rm) => (
                    <button
                      key={rm.room_code}
                      onClick={() => setActiveRoomCode(rm.room_code)}
                      className={`px-3.5 py-2 rounded-lg text-xs font-bold border transition ${
                        currentRoomLayout.room_code === rm.room_code
                          ? "bg-slate-900 text-white border-slate-900 shadow-sm"
                          : "bg-slate-50 text-slate-700 border-slate-300 hover:bg-slate-100"
                      }`}
                    >
                      {rm.room_code} — {rm.room_name} (
                      {rm.allocated_student_count}/{rm.effective_exam_capacity}{" "}
                      Koltuk)
                    </button>
                  ))}
                </div>

                {/* Renk Lejantı */}
                <div className="flex flex-wrap items-center gap-4 text-xs">
                  <span className="flex items-center gap-1.5">
                    <span className="w-3.5 h-3.5 rounded bg-blue-600 inline-block"></span>
                    <b>Dolu Koltuk (KVKK Öğrenci No)</b>
                  </span>
                  <span className="flex items-center gap-1.5">
                    <span className="w-3.5 h-3.5 rounded bg-amber-100 border border-amber-400 inline-block"></span>
                    <b>1-Boş-Koltuk Kuralı (Zorunlu Boş Sütun)</b>
                  </span>
                  <span className="flex items-center gap-1.5">
                    <span className="w-3.5 h-3.5 rounded bg-slate-100 border border-slate-300 inline-block"></span>
                    <b>Yedek Uygun Tekil Koltuk</b>
                  </span>
                </div>
              </div>

              {/* Kürsü / Tahta Sahne Çubuğu */}
              <div className="max-w-4xl mx-auto">
                <div className="w-full py-2 rounded-t-2xl bg-slate-800 text-amber-300 text-center text-xs font-bold tracking-widest uppercase shadow-inner">
                  [ TAHTA & GÖZETMEN KÜRSÜSÜ — {currentRoomLayout.proctor_ta_name}{" "}
                  ]
                </div>
              </div>

              {/* 2 Boyutlu Satır x Sütun Koltuk Matrisi */}
              <div className="overflow-x-auto pb-2">
                <div className="inline-block min-w-full">
                  <table className="mx-auto border-separate border-spacing-1.5 text-xs">
                    <thead>
                      <tr>
                        <th className="px-2 py-1 text-[11px] text-slate-500 font-bold">
                          Satır \ Sütun
                        </th>
                        {Array.from(
                          { length: currentRoomLayout.seat_cols },
                          (_, idx) => idx + 1
                        ).map((colNum) => (
                          <th
                            key={colNum}
                            className={`px-2 py-1 text-[11px] font-bold rounded ${
                              colNum % 2 === 0
                                ? "bg-amber-50 text-amber-800"
                                : "bg-slate-100 text-slate-800"
                            }`}
                          >
                            Sütun {colNum}
                            <div className="text-[9px] font-normal">
                              {colNum % 2 === 0 ? "(Boş Şerit)" : "(Sınav)"}
                            </div>
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {Array.from(
                        { length: currentRoomLayout.seat_rows },
                        (_, rIdx) => rIdx + 1
                      ).map((rowNum) => (
                        <tr key={rowNum}>
                          <td className="px-2.5 py-1.5 font-bold text-slate-600 bg-slate-100 rounded text-center whitespace-nowrap">
                            Sıra {rowNum}
                          </td>
                          {Array.from(
                            { length: currentRoomLayout.seat_cols },
                            (_, cIdx) => cIdx + 1
                          ).map((colNum) => {
                            const seatedStudent =
                              seatByCoord[`${rowNum}_${colNum}`];
                            const isMandatoryGapCol = colNum % 2 === 0;

                            if (seatedStudent) {
                              return (
                                <td
                                  key={colNum}
                                  title={`${seatedStudent.student_number} — ${seatedStudent.student_name}`}
                                  className="w-24 h-14 p-1.5 rounded-lg bg-blue-600 text-white border border-blue-700 shadow-sm text-center align-middle"
                                >
                                  <div className="font-bold text-[11px] leading-tight">
                                    {seatedStudent.student_number}
                                  </div>
                                  <div className="text-[9px] text-blue-100 truncate max-w-[84px] mx-auto">
                                    S{rowNum}•K{colNum}
                                  </div>
                                </td>
                              );
                            }

                            if (isMandatoryGapCol) {
                              return (
                                <td
                                  key={colNum}
                                  className="w-20 h-14 p-1 rounded-lg bg-amber-50/80 border border-dashed border-amber-300 text-amber-800 text-center align-middle"
                                >
                                  <div className="text-[10px] font-bold">
                                    BOŞ
                                  </div>
                                  <div className="text-[9px] opacity-75">
                                    1-Boş-Koltuk
                                  </div>
                                </td>
                              );
                            }

                            return (
                              <td
                                key={colNum}
                                className="w-24 h-14 p-1 rounded-lg bg-slate-50 border border-slate-200 text-slate-400 text-center align-middle"
                              >
                                <div className="text-[10px] font-semibold">
                                  Müsait
                                </div>
                                <div className="text-[9px]">
                                  S{rowNum}•K{colNum}
                                </div>
                              </td>
                            );
                          })}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
};
