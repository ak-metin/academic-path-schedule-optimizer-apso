import React, { useEffect, useState } from "react";
import {
  API_BASE_URL,
  CourseRead,
  InstructorAvailabilitySlotSchema,
  InstructorRead,
  RoomRead,
  TAUnavailabilityRead,
  TeachingAssistantRead,
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

export const ResourceManagementPage: React.FC = () => {
  const [instructors, setInstructors] = useState<InstructorRead[]>([]);
  const [selectedInstId, setSelectedInstId] = useState<number>(1);
  const [availSlots, setAvailSlots] = useState<
    InstructorAvailabilitySlotSchema[]
  >([]);
  const [savingAvail, setSavingAvail] = useState<boolean>(false);
  const [statusBanner, setStatusBanner] = useState<string | null>(null);

  const [courses, setCourses] = useState<CourseRead[]>([]);
  const [rooms, setRooms] = useState<RoomRead[]>([]);
  const [tas, setTas] = useState<TeachingAssistantRead[]>([]);
  const [taUnavails, setTaUnavails] = useState<TAUnavailabilityRead[]>([]);

  const [selectedTaId, setSelectedTaId] = useState<number>(1);
  const [newTaDay, setNewTaDay] = useState<number>(1);
  const [newTaSession, setNewTaSession] = useState<number>(1);
  const newTaReason = "MSc/PhD Graduate Seminar";

  const loadAllCatalogs = async () => {
    const [instRes, courseRes, roomRes, taRes, unavailRes] = await Promise.all([
      fetch(`${API_BASE_URL}/instructors`),
      fetch(`${API_BASE_URL}/courses`),
      fetch(`${API_BASE_URL}/rooms`),
      fetch(`${API_BASE_URL}/teaching-assistants`),
      fetch(`${API_BASE_URL}/teaching-assistants/unavailabilities`),
    ]);
    if (instRes.ok) {
      const data: InstructorRead[] = await instRes.json();
      setInstructors(data);
      if (data.length > 0 && !selectedInstId) setSelectedInstId(data[0].id);
    }
    if (courseRes.ok) setCourses(await courseRes.json());
    if (roomRes.ok) setRooms(await roomRes.json());
    if (taRes.ok) {
      const tData: TeachingAssistantRead[] = await taRes.json();
      setTas(tData);
      if (tData.length > 0 && !selectedTaId) setSelectedTaId(tData[0].id);
    }
    if (unavailRes.ok) setTaUnavails(await unavailRes.json());
  };

  const loadInstructorAvailability = async (instId: number) => {
    const res = await fetch(
      `${API_BASE_URL}/instructors/${instId}/availabilities`
    );
    if (res.ok) {
      setAvailSlots(await res.json());
    }
  };

  useEffect(() => {
    loadAllCatalogs();
  }, []);

  useEffect(() => {
    if (selectedInstId) {
      loadInstructorAvailability(selectedInstId);
    }
  }, [selectedInstId]);

  /**
   * Hücreye her tıklandığında 3 durum arasında geçiş yapar:
   * 1) Müsait & İstenen Saat (is_available=true, preference_penalty=0) [Yeşil]
   * 2) Müsait Ama İstenmeyen Saat (is_available=true, preference_penalty=3) [Sarı - Soft Penalty]
   * 3) Kapalı / İzinli Saat (is_available=false, preference_penalty=0) [Kırmızı - Hard Constraint]
   */
  const cycleSlotState = (day: number, slot: number) => {
    setAvailSlots((prev) =>
      prev.map((item) => {
        if (item.day_of_week !== day || item.slot_index !== slot) return item;
        if (item.is_available && item.preference_penalty === 0) {
          return { ...item, is_available: true, preference_penalty: 3 };
        }
        if (item.is_available && item.preference_penalty > 0) {
          return { ...item, is_available: false, preference_penalty: 0 };
        }
        return { ...item, is_available: true, preference_penalty: 0 };
      })
    );
  };

  const handleSaveAvailability = async () => {
    setSavingAvail(true);
    setStatusBanner(null);
    try {
      const res = await fetch(
        `${API_BASE_URL}/instructors/${selectedInstId}/availabilities`,
        {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ slots: availSlots }),
        }
      );
      if (res.ok) {
        setAvailSlots(await res.json());
        setStatusBanner(
          "Öğretim elemanı 5×8 müsaitlik ve tercih matrisi kaydedildi! Modül 2 CP-SAT çözücüsü yeni kısıtları kullanacak."
        );
      }
    } finally {
      setSavingAvail(false);
    }
  };

  const handleUpdateCourse = async (course: CourseRead) => {
    const res = await fetch(
      `${API_BASE_URL}/courses/${course.id}/constraints`,
      {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          enrolled_count: course.enrolled_count,
          requires_lab_room: course.requires_lab_room,
          theory_hours: course.theory_hours,
          lab_hours: course.lab_hours,
          instructor_id: course.instructor_id,
        }),
      }
    );
    if (res.ok) {
      setStatusBanner(
        `${course.code} ders kısıtları (Öğrenci sayısı: ${course.enrolled_count}, LAB: ${
          course.requires_lab_room ? "Evet" : "Hayır"
        }) güncellendi.`
      );
      loadAllCatalogs();
    }
  };

  const handleUpdateRoom = async (room: RoomRead) => {
    const res = await fetch(`${API_BASE_URL}/rooms/${room.id}/capacity`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        room_type: room.room_type,
        normal_capacity: room.normal_capacity,
        seat_rows: room.seat_rows,
        seat_cols: room.seat_cols,
      }),
    });
    if (res.ok) {
      const updated: RoomRead = await res.json();
      setStatusBanner(
        `${updated.code} salonu güncellendi (1-Boş-Koltuk Efektif Sınav Kapasitesi: ${updated.effective_exam_capacity}).`
      );
      loadAllCatalogs();
    }
  };

  const handleAddTaUnavail = async (e: React.FormEvent) => {
    e.preventDefault();
    const res = await fetch(
      `${API_BASE_URL}/teaching-assistants/${selectedTaId}/unavailabilities`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          exam_day: newTaDay,
          session_index: newTaSession,
          reason: newTaReason,
        }),
      }
    );
    if (res.ok) {
      setStatusBanner(
        "Araştırma görevlisi yüksek lisans ders / sınav kısıtı eklendi."
      );
      loadAllCatalogs();
    }
  };

  const handleDeleteTaUnavail = async (id: number) => {
    const res = await fetch(
      `${API_BASE_URL}/teaching-assistants/unavailabilities/${id}`,
      { method: "DELETE" }
    );
    if (res.ok) {
      setStatusBanner("Araştırma görevlisi kısıtı kaldırıldı.");
      loadAllCatalogs();
    }
  };

  const slotMap: Record<string, InstructorAvailabilitySlotSchema> = {};
  availSlots.forEach((s) => {
    slotMap[`${s.day_of_week}_${s.slot_index}`] = s;
  });

  return (
    <div className="space-y-6">
      {statusBanner && (
        <div className="p-3.5 rounded-xl bg-emerald-50 border border-emerald-200 text-emerald-900 text-xs font-semibold flex items-center justify-between">
          <span>✓ {statusBanner}</span>
          <button
            onClick={() => setStatusBanner(null)}
            className="text-emerald-700 hover:underline ml-4"
          >
            Kapat
          </button>
        </div>
      )}

      {/* 1. Öğretim Elemanı 5x8 İnteraktif Müsaitlik & Tercih Matrisi */}
      <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <h2 className="text-base font-bold text-slate-900">
              1. Öğretim Elemanı Haftalık 5×8 Müsaitlik & Tercih Matrisi Editörü
            </h2>
            <p className="text-xs text-slate-600">
              Hücrelere tıklayarak{" "}
              <b className="text-emerald-700">Müsait (Tercih Edilen)</b> →{" "}
              <b className="text-amber-700">İstenmeyen Saat (Soft Ceza = 3)</b>{" "}
              → <b className="text-red-700">Kapalı / İzinli (Hard Kısıt)</b>{" "}
              arasında geçiş yapın.
            </p>
          </div>

          <div className="flex items-center gap-3">
            <select
              value={selectedInstId}
              onChange={(e) => setSelectedInstId(Number(e.target.value))}
              className="border border-slate-300 rounded-lg px-3 py-2 text-xs font-semibold"
            >
              {instructors.map((inst) => (
                <option key={inst.id} value={inst.id}>
                  {inst.code} — {inst.full_name}
                </option>
              ))}
            </select>

            <button
              onClick={handleSaveAvailability}
              disabled={savingAvail}
              className="bg-slate-900 hover:bg-slate-800 text-white font-semibold text-xs px-4 py-2 rounded-lg transition"
            >
              {savingAvail ? "Kaydediliyor..." : "Müsaitlik Matrisini Kaydet"}
            </button>
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-xs">
            <thead>
              <tr className="bg-slate-900 text-white">
                <th className="p-2 border border-slate-700 w-32">
                  Saat Dilimi
                </th>
                {DAYS.map((d) => (
                  <th
                    key={d.id}
                    className="p-2 border border-slate-700 text-center"
                  >
                    {d.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {SLOTS.map((s) => (
                <tr key={s.id}>
                  <td className="p-2 border border-slate-200 font-semibold text-center bg-slate-50">
                    {s.time}
                  </td>
                  {DAYS.map((d) => {
                    const cell = slotMap[`${d.id}_${s.id}`];
                    let btnStyle =
                      "bg-emerald-50 border-emerald-300 text-emerald-900 hover:bg-emerald-100";
                    let label = "Müsait (Ceza: 0)";
                    if (cell && !cell.is_available) {
                      btnStyle =
                        "bg-red-100 border-red-300 text-red-900 font-bold hover:bg-red-200";
                      label = "KAPALI (Hard Kısıt)";
                    } else if (cell && cell.preference_penalty > 0) {
                      btnStyle =
                        "bg-amber-100 border-amber-300 text-amber-900 font-semibold hover:bg-amber-200";
                      label = `İstenmeyen (Ceza: +${cell.preference_penalty})`;
                    }

                    return (
                      <td key={d.id} className="p-1.5 border border-slate-200">
                        <button
                          type="button"
                          onClick={() => cycleSlotState(d.id, s.id)}
                          className={`w-full py-2 px-2 rounded border text-center transition text-[11px] ${btnStyle}`}
                        >
                          {label}
                        </button>
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* 2. Amfi & Laboratuvar Kapasite / 1-Boş-Koltuk Matris Editörü ve Arş. Gör. Kısıtları */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Amfi & Lab Editörü */}
        <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm space-y-3">
          <h3 className="text-sm font-bold text-slate-900">
            2. Amfi & Laboratuvar Fiziksel ve 1-Boş-Koltuk Sınav Kapasitesi
            Editörü
          </h3>
          <div className="overflow-x-auto max-h-80">
            <table className="w-full border-collapse text-xs">
              <thead>
                <tr className="bg-slate-900 text-white sticky top-0">
                  <th className="p-2 border border-slate-700">Kod</th>
                  <th className="p-2 border border-slate-700">Tip</th>
                  <th className="p-2 border border-slate-700">Normal Kap.</th>
                  <th className="p-2 border border-slate-700">Satır × Sütun</th>
                  <th className="p-2 border border-slate-700">
                    1-Boş-Koltuk Kap.
                  </th>
                  <th className="p-2 border border-slate-700">İşlem</th>
                </tr>
              </thead>
              <tbody>
                {rooms.map((r, idx) => (
                  <tr key={r.id} className="even:bg-slate-50">
                    <td className="p-2 border border-slate-200 font-bold">
                      {r.code}
                    </td>
                    <td className="p-2 border border-slate-200">
                      <select
                        value={r.room_type}
                        onChange={(e) => {
                          const next = [...rooms];
                          next[idx] = { ...r, room_type: e.target.value };
                          setRooms(next);
                        }}
                        className="border border-slate-300 rounded px-1.5 py-0.5 text-xs"
                      >
                        <option value="LECTURE">LECTURE</option>
                        <option value="LAB">LAB</option>
                      </select>
                    </td>
                    <td className="p-2 border border-slate-200 text-center">
                      <input
                        type="number"
                        value={r.normal_capacity}
                        onChange={(e) => {
                          const next = [...rooms];
                          next[idx] = {
                            ...r,
                            normal_capacity: Number(e.target.value),
                          };
                          setRooms(next);
                        }}
                        className="w-16 border border-slate-300 rounded px-1.5 py-0.5 text-center"
                      />
                    </td>
                    <td className="p-2 border border-slate-200 text-center">
                      <input
                        type="number"
                        value={r.seat_rows}
                        onChange={(e) => {
                          const next = [...rooms];
                          next[idx] = {
                            ...r,
                            seat_rows: Number(e.target.value),
                          };
                          setRooms(next);
                        }}
                        className="w-11 border border-slate-300 rounded px-1 py-0.5 text-center"
                      />{" "}
                      ×{" "}
                      <input
                        type="number"
                        value={r.seat_cols}
                        onChange={(e) => {
                          const next = [...rooms];
                          next[idx] = {
                            ...r,
                            seat_cols: Number(e.target.value),
                          };
                          setRooms(next);
                        }}
                        className="w-11 border border-slate-300 rounded px-1 py-0.5 text-center"
                      />
                    </td>
                    <td className="p-2 border border-slate-200 text-center font-bold text-blue-800">
                      {r.seat_rows * Math.ceil(r.seat_cols / 2)}
                    </td>
                    <td className="p-2 border border-slate-200 text-center">
                      <button
                        onClick={() => handleUpdateRoom(r)}
                        className="bg-blue-700 hover:bg-blue-800 text-white px-2.5 py-1 rounded text-[11px] font-semibold"
                      >
                        Kaydet
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Arş. Gör. Lisansüstü Ders / Sınav Kısıtı Editörü */}
        <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm space-y-3">
          <h3 className="text-sm font-bold text-slate-900">
            3. Araştırma Görevlisi (Gözetmen) Lisansüstü Ders Kısıtları
          </h3>
          <form
            onSubmit={handleAddTaUnavail}
            className="grid grid-cols-1 sm:grid-cols-4 gap-2 items-end bg-slate-50 p-3 rounded-lg border border-slate-200"
          >
            <div>
              <label className="block text-[11px] font-semibold text-slate-700">
                Arş. Gör.
              </label>
              <select
                value={selectedTaId}
                onChange={(e) => setSelectedTaId(Number(e.target.value))}
                className="w-full mt-1 border border-slate-300 rounded px-2 py-1 text-xs"
              >
                {tas.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.code} — {t.full_name}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-[11px] font-semibold text-slate-700">
                Sınav Günü (1..10)
              </label>
              <input
                type="number"
                min={1}
                max={10}
                value={newTaDay}
                onChange={(e) => setNewTaDay(Number(e.target.value))}
                className="w-full mt-1 border border-slate-300 rounded px-2 py-1 text-xs"
              />
            </div>
            <div>
              <label className="block text-[11px] font-semibold text-slate-700">
                Oturum (1..4)
              </label>
              <input
                type="number"
                min={1}
                max={4}
                value={newTaSession}
                onChange={(e) => setNewTaSession(Number(e.target.value))}
                className="w-full mt-1 border border-slate-300 rounded px-2 py-1 text-xs"
              />
            </div>
            <button
              type="submit"
              className="bg-rose-800 hover:bg-rose-900 text-white font-semibold text-xs py-1.5 px-3 rounded"
            >
              Kısıt Ekle
            </button>
          </form>

          <div className="overflow-x-auto max-h-56">
            <table className="w-full border-collapse text-xs">
              <thead>
                <tr className="bg-slate-900 text-white sticky top-0">
                  <th className="p-2 border border-slate-700">Arş. Gör.</th>
                  <th className="p-2 border border-slate-700">Gün / Oturum</th>
                  <th className="p-2 border border-slate-700">Neden</th>
                  <th className="p-2 border border-slate-700">Sil</th>
                </tr>
              </thead>
              <tbody>
                {taUnavails.map((u) => (
                  <tr key={u.id} className="even:bg-slate-50">
                    <td className="p-2 border border-slate-200 font-semibold">
                      {u.ta_code} — {u.ta_name}
                    </td>
                    <td className="p-2 border border-slate-200 text-center">
                      Gün {u.exam_day} / Ot. {u.session_index}
                    </td>
                    <td className="p-2 border border-slate-200">{u.reason}</td>
                    <td className="p-2 border border-slate-200 text-center">
                      <button
                        onClick={() => handleDeleteTaUnavail(u.id)}
                        className="text-red-700 hover:underline font-semibold"
                      >
                        Kaldır
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* 3. Ders Öğrenci Mevcudu & LAB Gereksinimi Editörü (Unsat Core / Darboğaz Testleri İçin) */}
      <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm space-y-3">
        <div>
          <h3 className="text-sm font-bold text-slate-900">
            4. Ders Öğrenci Mevcudu, LAB Odası Zorunluluğu ve Öğretim Elemanı
            Editörü
          </h3>
          <p className="text-xs text-slate-600">
            İpucu: Bir dersin öğrenci mevcudunu 250&apos;ye çıkarıp
            kaydederseniz Modül 2 CP-SAT çözücüsünün{" "}
            <b>Türkçe Unsat Core Darboğaz Tanısını</b> canlı test edebilirsiniz.
          </p>
        </div>

        <div className="overflow-x-auto max-h-72">
          <table className="w-full border-collapse text-xs">
            <thead>
              <tr className="bg-slate-900 text-white sticky top-0">
                <th className="p-2 border border-slate-700">Ders Kodu & Adı</th>
                <th className="p-2 border border-slate-700">Dönem</th>
                <th className="p-2 border border-slate-700">Öğrenci Sayısı</th>
                <th className="p-2 border border-slate-700">Teori / Lab Saat</th>
                <th className="p-2 border border-slate-700">LAB Zorunlu Mu?</th>
                <th className="p-2 border border-slate-700">İşlem</th>
              </tr>
            </thead>
            <tbody>
              {courses.map((c, idx) => (
                <tr key={c.id} className="even:bg-slate-50">
                  <td className="p-2 border border-slate-200">
                    <b>{c.code}</b> — {c.name}
                  </td>
                  <td className="p-2 border border-slate-200 text-center">
                    {c.semester}. Yarıyıl
                  </td>
                  <td className="p-2 border border-slate-200 text-center">
                    <input
                      type="number"
                      value={c.enrolled_count}
                      onChange={(e) => {
                        const next = [...courses];
                        next[idx] = {
                          ...c,
                          enrolled_count: Number(e.target.value),
                        };
                        setCourses(next);
                      }}
                      className="w-16 border border-slate-300 rounded px-1.5 py-0.5 text-center"
                    />
                  </td>
                  <td className="p-2 border border-slate-200 text-center">
                    {c.theory_hours}T + {c.lab_hours}L
                  </td>
                  <td className="p-2 border border-slate-200 text-center">
                    <input
                      type="checkbox"
                      checked={c.requires_lab_room}
                      onChange={(e) => {
                        const next = [...courses];
                        next[idx] = {
                          ...c,
                          requires_lab_room: e.target.checked,
                        };
                        setCourses(next);
                      }}
                    />
                  </td>
                  <td className="p-2 border border-slate-200 text-center">
                    <button
                      onClick={() => handleUpdateCourse(c)}
                      className="bg-slate-900 hover:bg-slate-800 text-white px-2.5 py-1 rounded text-[11px] font-semibold"
                    >
                      Güncelle
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
