import React, { useEffect, useState } from "react";
import {
  API_BASE_URL,
  PinnedSlotItem,
  RoomRead,
  WeeklyScheduleOptimizationResponse,
  WeeklySlotAssignmentRead,
  WeeklySlotMoveResponse,
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
  const [contiguousBlocks, setContiguousBlocks] = useState<boolean>(true);
  const [splitTheoryLab, setSplitTheoryLab] = useState<boolean>(true);
  const [loading, setLoading] = useState<boolean>(false);
  const [result, setResult] =
    useState<WeeklyScheduleOptimizationResponse | null>(null);

  // Stretch Goal 1: Sabitleme (Pin/Lock) ve What-If Manuel Taşıma Durumları
  const [rooms, setRooms] = useState<RoomRead[]>([]);
  const [pinnedSlots, setPinnedSlots] = useState<PinnedSlotItem[]>([]);
  const [selectedSlotForMove, setSelectedSlotForMove] =
    useState<WeeklySlotAssignmentRead | null>(null);
  const [moveTargetDay, setMoveTargetDay] = useState<number>(1);
  const [moveTargetSlot, setMoveTargetSlot] = useState<number>(1);
  const [moveTargetRoomId, setMoveTargetRoomId] = useState<number>(1);
  const [moveFeedback, setMoveFeedback] =
    useState<WeeklySlotMoveResponse | null>(null);

  useEffect(() => {
    fetch(`${API_BASE_URL}/rooms`)
      .then((r) => (r.ok ? r.json() : []))
      .then((data: RoomRead[]) => {
        setRooms(data);
        if (data.length > 0) setMoveTargetRoomId(data[0].id);
      })
      .catch(() => null);
  }, []);

  const termStr = parity === "FALL" ? "2026-FALL" : "2026-SPRING";

  const handleOptimize = async (usePins: boolean = true) => {
    setLoading(true);
    setMoveFeedback(null);
    try {
      const res = await fetch(`${API_BASE_URL}/schedule/weekly/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          academic_term: termStr,
          semester_parity: parity,
          max_time_seconds: 20,
          idle_gap_weight: 10,
          instructor_preference_weight: 5,
          enforce_contiguous_blocks: contiguousBlocks,
          split_theory_and_lab_sessions: splitTheoryLab,
          pinned_slots: usePins ? pinnedSlots : [],
        }),
      });
      if (res.ok) {
        const data: WeeklyScheduleOptimizationResponse = await res.json();
        setResult(data);
        if (![1, 2, 3, 4, 5, 6, 7, 8].includes(selectedSemester)) {
          setSelectedSemester(parity === "FALL" ? 1 : 2);
        }
      }
    } finally {
      setLoading(false);
    }
  };

  const makePinKey = (
    courseId: number,
    sessType: string,
    roomId: number,
    day: number,
    slot: number
  ) => `${courseId}_${sessType}_${roomId}_${day}_${slot}`;

  const pinnedKeySet = new Set(
    pinnedSlots.map((p) =>
      makePinKey(p.course_id, p.session_type, p.room_id, p.day_of_week, p.slot_index)
    )
  );

  const togglePinSlot = (item: WeeklySlotAssignmentRead, e: React.MouseEvent) => {
    e.stopPropagation();
    const key = makePinKey(
      item.course_id,
      item.session_type,
      item.room_id,
      item.day_of_week,
      item.slot_index
    );
    if (pinnedKeySet.has(key)) {
      setPinnedSlots((prev) =>
        prev.filter(
          (p) =>
            makePinKey(
              p.course_id,
              p.session_type,
              p.room_id,
              p.day_of_week,
              p.slot_index
            ) !== key
        )
      );
    } else {
      setPinnedSlots((prev) => [
        ...prev,
        {
          course_id: item.course_id,
          room_id: item.room_id,
          day_of_week: item.day_of_week,
          slot_index: item.slot_index,
          session_type: item.session_type,
        },
      ]);
    }
  };

  const handleSelectSlotForMove = (item: WeeklySlotAssignmentRead) => {
    setSelectedSlotForMove(item);
    setMoveTargetDay(item.day_of_week);
    setMoveTargetSlot(item.slot_index);
    setMoveTargetRoomId(item.room_id);
    setMoveFeedback(null);
  };

  const handleExecuteWhatIfMove = async (applyIfValid: boolean) => {
    if (!selectedSlotForMove) return;
    const res = await fetch(`${API_BASE_URL}/schedule/weekly/move`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        academic_term: termStr,
        course_id: selectedSlotForMove.course_id,
        session_type: selectedSlotForMove.session_type,
        from_day: selectedSlotForMove.day_of_week,
        from_slot: selectedSlotForMove.slot_index,
        from_room_id: selectedSlotForMove.room_id,
        to_day: moveTargetDay,
        to_slot: moveTargetSlot,
        to_room_id: moveTargetRoomId,
        apply_if_valid: applyIfValid,
      }),
    });
    if (res.ok) {
      const moveRes: WeeklySlotMoveResponse = await res.json();
      setMoveFeedback(moveRes);
      if (moveRes.applied && moveRes.updated_assignment && result) {
        // Tablodaki atamayı anında güncelle
        const updatedList = result.assignments.map((a) => {
          if (
            a.course_id === selectedSlotForMove.course_id &&
            a.day_of_week === selectedSlotForMove.day_of_week &&
            a.slot_index === selectedSlotForMove.slot_index &&
            a.room_id === selectedSlotForMove.room_id
          ) {
            return moveRes.updated_assignment!;
          }
          return a;
        });
        setResult({ ...result, assignments: updatedList });
        setSelectedSlotForMove(moveRes.updated_assignment);
      }
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

  return (
    <div className="space-y-6">
      {/* Kontrol Çubuğu */}
      <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 className="text-base font-bold text-slate-900">
            Modül 2 — Google OR-Tools CP-SAT Haftalık Ders Programı & What-If
            Editörü
          </h2>
          <p className="text-xs text-slate-600 mt-0.5">
            Modül 1&apos;den gelen <code>C_DAG</code> kurallarını, blok dersleri
            ve Teori/Lab ayrımını çözer. Ders kartlarındaki <b>📌 Sabitle</b>{" "}
            ikonuyla hücre kilitleyebilir veya karta tıklayarak{" "}
            <b>What-If Taşıma & Çakışma Kontrolü</b> yapabilirsiniz.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2.5">
          <label className="flex items-center gap-1.5 text-xs font-semibold text-slate-700 cursor-pointer bg-slate-50 border border-slate-200 px-2.5 py-2 rounded-lg">
            <input
              type="checkbox"
              checked={contiguousBlocks}
              onChange={(e) => setContiguousBlocks(e.target.checked)}
            />
            Blok Ders (Ardışık 2 Saat)
          </label>

          <label className="flex items-center gap-1.5 text-xs font-semibold text-slate-700 cursor-pointer bg-slate-50 border border-slate-200 px-2.5 py-2 rounded-lg">
            <input
              type="checkbox"
              checked={splitTheoryLab}
              onChange={(e) => setSplitTheoryLab(e.target.checked)}
            />
            Ayrı Teori (Amfi) + Lab (LAB)
          </label>

          <select
            value={parity}
            onChange={(e) => {
              const nextP = e.target.value as "FALL" | "SPRING";
              setParity(nextP);
              setPinnedSlots([]);
              setSelectedSemester(nextP === "FALL" ? 1 : 2);
            }}
            className="border border-slate-300 rounded-lg px-3 py-2 text-xs font-semibold"
          >
            <option value="FALL">Güz Dönemi (1, 3, 5, 7. Yarıyıl)</option>
            <option value="SPRING">Bahar Dönemi (2, 4, 6, 8. Yarıyıl)</option>
          </select>

          <button
            onClick={() => handleOptimize(true)}
            disabled={loading}
            className="bg-blue-700 hover:bg-blue-800 disabled:opacity-50 text-white font-semibold text-xs px-4 py-2.5 rounded-lg shadow-sm transition"
          >
            {loading
              ? "CP-SAT Çözücü Çalışıyor..."
              : pinnedSlots.length > 0
              ? `Sabitlenenleri Koruyarak Optimize Et (${pinnedSlots.length} Pin)`
              : "Haftalık Programı CP-SAT ile Optimize Et"}
          </button>

          {pinnedSlots.length > 0 && (
            <button
              onClick={() => setPinnedSlots([])}
              className="bg-amber-100 hover:bg-amber-200 text-amber-900 font-semibold text-xs px-3 py-2.5 rounded-lg transition"
            >
              Pinleri Temizle ({pinnedSlots.length})
            </button>
          )}

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
                  Teori (Amfi) / Lab (LAB) Saati
                </div>
                <div className="text-lg font-bold text-slate-900 mt-1">
                  {result.theory_slot_assignments}T +{" "}
                  <span className="text-purple-700">
                    {result.lab_slot_assignments}L
                  </span>{" "}
                  ({result.total_slot_assignments} Saat)
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

          {/* Stretch Goal 1: Seçili Ders İçin Manuel What-If Taşıma & Anlık Çakışma Doğrulayıcı Paneli */}
          {selectedSlotForMove && (
            <div className="bg-amber-50/70 border border-amber-300 p-4 rounded-xl space-y-3 shadow-sm">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="text-xs font-bold text-slate-900">
                  What-If Manuel Ders Taşıma & Anlık Kısıt Doğrulayıcı:{" "}
                  <span className="text-blue-800">
                    {selectedSlotForMove.course_code} (
                    {selectedSlotForMove.session_type})
                  </span>{" "}
                  — Mevcut: Gün {selectedSlotForMove.day_of_week}, Saat{" "}
                  {selectedSlotForMove.slot_index}, Salon{" "}
                  {selectedSlotForMove.room_code}
                </div>
                <button
                  onClick={() => setSelectedSlotForMove(null)}
                  className="text-xs font-semibold text-slate-600 hover:underline"
                >
                  Paneli Kapat
                </button>
              </div>

              <div className="flex flex-wrap items-end gap-3">
                <div>
                  <label className="block text-[11px] font-semibold text-slate-700">
                    Hedef Gün
                  </label>
                  <select
                    value={moveTargetDay}
                    onChange={(e) => setMoveTargetDay(Number(e.target.value))}
                    className="mt-1 border border-slate-300 rounded px-2.5 py-1.5 text-xs bg-white"
                  >
                    {DAYS.map((d) => (
                      <option key={d.id} value={d.id}>
                        {d.label}
                      </option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="block text-[11px] font-semibold text-slate-700">
                    Hedef Saat Dilimi
                  </label>
                  <select
                    value={moveTargetSlot}
                    onChange={(e) => setMoveTargetSlot(Number(e.target.value))}
                    className="mt-1 border border-slate-300 rounded px-2.5 py-1.5 text-xs bg-white"
                  >
                    {SLOTS.map((s) => (
                      <option key={s.id} value={s.id}>
                        Slot {s.id} ({s.time})
                      </option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="block text-[11px] font-semibold text-slate-700">
                    Hedef Amfi / Lab
                  </label>
                  <select
                    value={moveTargetRoomId}
                    onChange={(e) =>
                      setMoveTargetRoomId(Number(e.target.value))
                    }
                    className="mt-1 border border-slate-300 rounded px-2.5 py-1.5 text-xs bg-white"
                  >
                    {rooms.map((r) => (
                      <option key={r.id} value={r.id}>
                        {r.code} ({r.room_type}, Kap: {r.normal_capacity})
                      </option>
                    ))}
                  </select>
                </div>

                <button
                  onClick={() => handleExecuteWhatIfMove(false)}
                  className="bg-slate-800 hover:bg-slate-900 text-white font-semibold text-xs px-3.5 py-2 rounded-lg transition"
                >
                  Sadece Çakışma Kontrolü Yap (Test Et)
                </button>

                <button
                  onClick={() => handleExecuteWhatIfMove(true)}
                  className="bg-amber-600 hover:bg-amber-700 text-white font-semibold text-xs px-3.5 py-2 rounded-lg transition"
                >
                  Geçerliyse Taşı & Kaydet
                </button>
              </div>

              {moveFeedback && (
                <div
                  className={`p-3 rounded-lg border text-xs space-y-1 ${
                    moveFeedback.is_valid
                      ? "bg-emerald-50 border-emerald-300 text-emerald-900"
                      : "bg-red-50 border-red-300 text-red-900"
                  }`}
                >
                  <div className="font-bold">
                    {moveFeedback.is_valid
                      ? moveFeedback.applied
                        ? "✓ Kısıt İhlali Yok: Ders yeni gün/saat/salona başarıyla taşındı!"
                        : "✓ What-If Testi Başarılı: Bu taşıma tüm Hard Constraint ve C_DAG kurallarına uygundur."
                      : "✕ Kısıt İhlali Tespit Edildi (Taşıma Engellendi):"}
                  </div>
                  {moveFeedback.violations_tr.map((v, i) => (
                    <div key={i}>• {v}</div>
                  ))}
                  {moveFeedback.warnings_tr.map((w, i) => (
                    <div key={i} className="text-amber-800 font-medium">
                      ⚠ {w}
                    </div>
                  ))}
                </div>
              )}
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
                  Derse tıklayarak <b>What-If Taşıma</b> yapabilir, 📌 butonuna
                  tıklayarak dersi o saate <b>sabitleyebilirsiniz</b>.
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
                              {items.map((item) => {
                                const pinKey = makePinKey(
                                  item.course_id,
                                  item.session_type,
                                  item.room_id,
                                  item.day_of_week,
                                  item.slot_index
                                );
                                const isPinned = pinnedKeySet.has(pinKey);
                                return (
                                  <div
                                    key={`${item.course_code}_${item.session_type}_${item.slot_index}`}
                                    onClick={() =>
                                      handleSelectSlotForMove(item)
                                    }
                                    className={`p-2 rounded-lg border text-left space-y-0.5 cursor-pointer transition hover:shadow ${
                                      isPinned
                                        ? "bg-amber-100 border-amber-500 ring-2 ring-amber-400 text-slate-900"
                                        : item.session_type === "LAB"
                                        ? "bg-purple-50 border-purple-300 text-purple-950"
                                        : "bg-blue-50 border-blue-200 text-blue-950"
                                    }`}
                                  >
                                    <div className="flex items-center justify-between font-bold gap-1">
                                      <span>
                                        {item.course_code}{" "}
                                        <span className="text-[9px] font-semibold opacity-75">
                                          [{item.session_type}]
                                        </span>
                                      </span>
                                      <div className="flex items-center gap-1">
                                        <span className="text-[10px] px-1.5 py-0.5 rounded bg-white/80 font-semibold">
                                          {item.room_code}
                                        </span>
                                        <button
                                          type="button"
                                          title={
                                            isPinned
                                              ? "Sabitlemeyi Kaldır"
                                              : "Bu Saate Sabitle (Pin)"
                                          }
                                          onClick={(e) =>
                                            togglePinSlot(item, e)
                                          }
                                          className={`px-1 py-0.5 rounded text-[10px] ${
                                            isPinned
                                              ? "bg-amber-500 text-white"
                                              : "bg-white/60 hover:bg-white"
                                          }`}
                                        >
                                          📌
                                        </button>
                                      </div>
                                    </div>
                                    <div className="text-[11px] leading-tight">
                                      {item.course_name}
                                    </div>
                                    <div className="text-[10px] opacity-80">
                                      {item.instructor_name} (
                                      {item.enrolled_count}/{item.room_capacity}
                                      )
                                    </div>
                                  </div>
                                );
                              })}
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
