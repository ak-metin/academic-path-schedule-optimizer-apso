import React, { useEffect, useState } from "react";
import {
  API_BASE_URL,
  CourseGraphNodeMetric,
  CurriculumGraphAnalysisResponse,
  ExcelImportResultResponse,
  FailureSimulationResponse,
} from "../api";

export const CurriculumDAGPage: React.FC = () => {
  const [graphData, setGraphData] =
    useState<CurriculumGraphAnalysisResponse | null>(null);
  const [selectedFailed, setSelectedFailed] = useState<string[]>(["CSE102"]);
  const [currentSemester, setCurrentSemester] = useState<number>(2);
  const [useRecoveryCap, setUseRecoveryCap] = useState<boolean>(true);
  const [simResult, setSimResult] = useState<FailureSimulationResponse | null>(
    null
  );
  const [prereqSource, setPrereqSource] = useState<string>("SE403");
  const [prereqTarget, setPrereqTarget] = useState<string>("CSE101");
  const [edgeStatusMsg, setEdgeStatusMsg] = useState<{
    type: "error" | "success";
    text: string;
  } | null>(null);
  const [importResult, setImportResult] =
    useState<ExcelImportResultResponse | null>(null);
  const [importError, setImportError] = useState<string | null>(null);

  const handleExcelUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setImportResult(null);
    setImportError(null);
    try {
      const buf = await file.arrayBuffer();
      const bytes = new Uint8Array(buf);
      let binary = "";
      for (let i = 0; i < bytes.byteLength; i++) {
        binary += String.fromCharCode(bytes[i]);
      }
      const b64 = window.btoa(binary);
      const res = await fetch(`${API_BASE_URL}/import/excel`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          filename: file.name,
          content_base64: b64,
        }),
      });
      const body = await res.json();
      if (!res.ok) {
        setImportError(body?.detail?.message || "Excel yükleme hatası.");
      } else {
        setImportResult(body);
        fetchGraph();
      }
    } catch (err) {
      setImportError(String(err));
    }
  };

  const fetchGraph = async () => {
    const res = await fetch(`${API_BASE_URL}/curriculum/graph`);
    if (res.ok) {
      const data: CurriculumGraphAnalysisResponse = await res.json();
      setGraphData(data);
    }
  };

  const runSimulation = async () => {
    if (selectedFailed.length === 0) return;
    const res = await fetch(`${API_BASE_URL}/curriculum/simulate-failure`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        current_semester: currentSemester,
        failed_course_codes: selectedFailed,
        use_recovery_ects_cap: useRecoveryCap,
      }),
    });
    if (res.ok) {
      const data: FailureSimulationResponse = await res.json();
      setSimResult(data);
    }
  };

  useEffect(() => {
    fetchGraph();
  }, []);

  useEffect(() => {
    if (graphData) {
      runSimulation();
    }
  }, [graphData, selectedFailed, currentSemester, useRecoveryCap]);

  const toggleFailedCourse = (code: string) => {
    setSelectedFailed((prev) =>
      prev.includes(code) ? prev.filter((c) => c !== code) : [...prev, code]
    );
  };

  const handleAddPrerequisite = async (e: React.FormEvent) => {
    e.preventDefault();
    setEdgeStatusMsg(null);
    const res = await fetch(`${API_BASE_URL}/prerequisites`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        prerequisite_code: prereqSource,
        target_code: prereqTarget,
        is_corequisite: false,
      }),
    });
    const body = await res.json();
    if (!res.ok) {
      const msg =
        body?.detail?.message || "HTTP 422: Döngüsel bağımlılık reddedildi.";
      const cycle = body?.detail?.cycle_path?.join(" -> ");
      setEdgeStatusMsg({
        type: "error",
        text: cycle ? `${msg} [Çevrim: ${cycle}]` : msg,
      });
    } else {
      setEdgeStatusMsg({
        type: "success",
        text: `Önkoşul başarıyla eklendi: ${body.prerequisite_code} -> ${body.target_code}`,
      });
      fetchGraph();
    }
  };

  const lockedSet = new Set(simResult?.transitively_locked_courses || []);
  const directLockedSet = new Set(simResult?.directly_locked_courses || []);
  const failedSet = new Set(selectedFailed);

  const semesters = [1, 2, 3, 4, 5, 6, 7, 8];
  const nodesBySemester: Record<number, CourseGraphNodeMetric[]> = {};
  semesters.forEach((s) => (nodesBySemester[s] = []));
  graphData?.nodes.forEach((n) => {
    if (nodesBySemester[n.semester]) {
      nodesBySemester[n.semester].push(n);
    }
  });

  return (
    <div className="space-y-6">
      {/* Üst Özet Kartları */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm">
          <div className="text-xs font-semibold uppercase text-slate-500">
            DAG Durumu & Topoloji
          </div>
          <div className="text-xl font-bold text-emerald-700 mt-1">
            {graphData?.is_valid_dag ? "Geçerli DAG (Çevrimsiz)" : "Hatalı"}
          </div>
          <div className="text-xs text-slate-600 mt-1">
            {graphData?.total_nodes || 0} Ders Düğümü |{" "}
            {graphData?.total_edges || 0} Önkoşul Kenarı
          </div>
        </div>

        <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm">
          <div className="text-xs font-semibold uppercase text-slate-500">
            Global Kritik Yol (CP)
          </div>
          <div className="text-xl font-bold text-slate-900 mt-1">
            {graphData?.longest_critical_path_length || 0} Dönem Zinciri
          </div>
          <div className="text-xs text-slate-600 mt-1 truncate">
            {graphData?.global_critical_path.join(" → ")}
          </div>
        </div>

        <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm">
          <div className="text-xs font-semibold uppercase text-slate-500">
            En Kritik Darboğaz Dersler
          </div>
          <div className="flex flex-wrap gap-1.5 mt-2">
            {graphData?.top_bottleneck_courses.map((code) => (
              <span
                key={code}
                className="px-2 py-0.5 text-xs font-bold rounded bg-amber-100 text-amber-900"
              >
                {code}
              </span>
            ))}
          </div>
        </div>

        <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm">
          <div className="text-xs font-semibold uppercase text-slate-500">
            Simüle Edilen Mezuniyet Gecikmesi
          </div>
          <div
            className={`text-xl font-bold mt-1 ${
              (simResult?.estimated_graduation_delay_semesters || 0) > 0
                ? "text-red-700"
                : "text-emerald-700"
            }`}
          >
            +{simResult?.estimated_graduation_delay_semesters || 0} Yarıyıl
            Gecikme
          </div>
          <div className="text-xs text-slate-600 mt-1">
            Kilitlenen Üst Ders:{" "}
            {simResult?.transitively_locked_courses.length || 0} adet (
            {simResult?.applied_ects_cap || 40} AKTS Sınırı)
          </div>
        </div>
      </div>

      {/* Simülasyon Kontrol Paneli ve DAG Çevrim Testi */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 bg-white p-5 rounded-xl border border-slate-200 shadow-sm space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div>
              <h2 className="text-base font-bold text-slate-900">
                Öğrenci Ders Kalma & Critical Path Simülasyonu (MVP-2)
              </h2>
              <p className="text-xs text-slate-600">
                Aşağıdaki 8 dönemlik müfredat haritasından kaldığınız ders(ler)e
                tıklayın; kilitlenen tüm alt/üst dersler (transitive closure)
                otomatik hesaplanır.
              </p>
            </div>
            <div className="flex items-center gap-3">
              <label className="text-xs font-semibold text-slate-700">
                Bulunduğu Dönem:
                <select
                  value={currentSemester}
                  onChange={(e) => setCurrentSemester(Number(e.target.value))}
                  className="ml-2 border border-slate-300 rounded px-2 py-1 text-xs"
                >
                  {[1, 2, 3, 4, 5, 6, 7].map((s) => (
                    <option key={s} value={s}>
                      {s}. Yarıyıl Sonu
                    </option>
                  ))}
                </select>
              </label>

              <label className="flex items-center gap-1.5 text-xs font-semibold text-slate-700 cursor-pointer">
                <input
                  type="checkbox"
                  checked={useRecoveryCap}
                  onChange={(e) => setUseRecoveryCap(e.target.checked)}
                />
                40 AKTS Kurtarma Sınırı
              </label>
            </div>
          </div>

          {simResult && (
            <div className="bg-slate-50 p-3.5 rounded-lg border border-slate-200 space-y-1.5">
              <div className="text-xs font-bold text-slate-800">
                Akademik Danışman Karar Destek Raporu:
              </div>
              {simResult.advisor_recommendations.map((rec, i) => (
                <div key={i} className="text-xs text-slate-700">
                  • {rec}
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Önkoşul Ekleme ve HTTP 422 Çevrim Kontrolü Kutusu */}
        <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm space-y-3">
          <h2 className="text-base font-bold text-slate-900">
            DAG Çevrim Kontrolü Testi (MVP-1)
          </h2>
          <p className="text-xs text-slate-600">
            Yeni önkoşul eklerken döngüsel bağımlılık (örn.{" "}
            <code>SE403 → CSE101</code>) varsa sistem <code>HTTP 422</code> ile
            reddeder.
          </p>
          <form onSubmit={handleAddPrerequisite} className="space-y-2.5">
            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className="block text-xs font-semibold text-slate-700">
                  Önkoşul Ders
                </label>
                <input
                  type="text"
                  value={prereqSource}
                  onChange={(e) => setPrereqSource(e.target.value)}
                  className="w-full mt-1 border border-slate-300 rounded px-2.5 py-1.5 text-xs"
                />
              </div>
              <div>
                <label className="block text-xs font-semibold text-slate-700">
                  Hedef Ders
                </label>
                <input
                  type="text"
                  value={prereqTarget}
                  onChange={(e) => setPrereqTarget(e.target.value)}
                  className="w-full mt-1 border border-slate-300 rounded px-2.5 py-1.5 text-xs"
                />
              </div>
            </div>
            <button
              type="submit"
              className="w-full bg-slate-900 hover:bg-slate-800 text-white font-semibold text-xs py-2 rounded-lg transition"
            >
              Önkoşul Ekle & Çevrim Kontrolü Yap
            </button>
          </form>
          {edgeStatusMsg && (
            <div
              className={`p-2.5 rounded text-xs font-medium ${
                edgeStatusMsg.type === "error"
                  ? "bg-red-50 text-red-800 border border-red-200"
                  : "bg-emerald-50 text-emerald-800 border border-emerald-200"
              }`}
            >
              {edgeStatusMsg.text}
            </div>
          )}

          {/* Excel (.xlsx) Veri İçe Aktarma (Pydantic v2 Doğrulamalı) */}
          <div className="pt-3 border-t border-slate-200 space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold text-slate-900">
                Excel (.xlsx) Veri İçe Aktar (Pydantic v2)
              </span>
              <a
                href={`${API_BASE_URL}/import/template.xlsx`}
                className="text-[11px] font-semibold text-blue-700 hover:underline"
              >
                Şablon (.xlsx) İndir
              </a>
            </div>
            <input
              type="file"
              accept=".xlsx"
              onChange={handleExcelUpload}
              className="block w-full text-xs text-slate-600 file:mr-2 file:py-1 file:px-2.5 file:rounded file:border-0 file:text-xs file:font-semibold file:bg-slate-100 file:text-slate-800 hover:file:bg-slate-200"
            />
            {importError && (
              <div className="p-2 rounded bg-red-50 text-red-800 text-xs">
                {importError}
              </div>
            )}
            {importResult && (
              <div className="p-2 rounded bg-emerald-50 text-emerald-900 text-xs space-y-1">
                <div className="font-bold">
                  Excel Yüklendi ({importResult.filename}): +
                  {importResult.courses_created} Yeni Ders, +
                  {importResult.rooms_created} Yeni Amfi (Hata:{" "}
                  {importResult.total_errors})
                </div>
                {importResult.row_errors.map((err, i) => (
                  <div key={i} className="text-[11px] text-red-700">
                    • [{err.sheet_name} Satır {err.row_number} -{" "}
                    {err.identifier}]: {err.error_message_tr}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* 8 Dönemlik İnteraktif Müfredat DAG Matrisi */}
      <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-2 mb-4">
          <h3 className="text-sm font-bold text-slate-900">
            ATÜ Yazılım Mühendisliği 8 Dönemlik Müfredat DAG Haritası (Derse
            Tıklayarak "Kaldı" Simülasyonu Yapın)
          </h3>
          <div className="flex items-center gap-3 text-xs">
            <span className="flex items-center gap-1">
              <span className="w-3 h-3 rounded bg-red-600 inline-block"></span>{" "}
              Kaldığı Ders
            </span>
            <span className="flex items-center gap-1">
              <span className="w-3 h-3 rounded bg-amber-500 inline-block"></span>{" "}
              Doğrudan Kilitlenen
            </span>
            <span className="flex items-center gap-1">
              <span className="w-3 h-3 rounded bg-orange-200 inline-block"></span>{" "}
              Dolaylı (Transitive) Kilitlenen
            </span>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-4 lg:grid-cols-8 gap-3">
          {semesters.map((sem) => (
            <div
              key={sem}
              className="bg-slate-50 rounded-lg p-2.5 border border-slate-200 space-y-2"
            >
              <div className="text-xs font-bold text-center py-1 rounded bg-slate-800 text-white">
                {sem}. Yarıyıl ({sem % 2 === 1 ? "Güz" : "Bahar"})
              </div>
              {nodesBySemester[sem]?.map((node) => {
                const isFailed = failedSet.has(node.code);
                const isDirectLock = directLockedSet.has(node.code);
                const isTransLock = lockedSet.has(node.code);

                let cardStyle =
                  "bg-white border-slate-200 hover:border-slate-400 text-slate-800";
                if (isFailed) {
                  cardStyle =
                    "bg-red-600 border-red-700 text-white shadow-md ring-2 ring-red-400";
                } else if (isDirectLock) {
                  cardStyle =
                    "bg-amber-500 border-amber-600 text-white font-semibold";
                } else if (isTransLock) {
                  cardStyle =
                    "bg-orange-100 border-orange-300 text-orange-950";
                }

                return (
                  <button
                    key={node.code}
                    onClick={() => toggleFailedCourse(node.code)}
                    className={`w-full text-left p-2 rounded-lg border transition text-xs space-y-1 ${cardStyle}`}
                  >
                    <div className="flex items-center justify-between font-bold">
                      <span>{node.code}</span>
                      <span className="text-[10px] opacity-85">
                        {node.ects} AKTS
                      </span>
                    </div>
                    <div className="text-[11px] leading-tight line-clamp-2">
                      {node.name}
                    </div>
                    <div className="flex items-center justify-between text-[10px] pt-1 opacity-90 border-t border-current/10">
                      <span>BF: {node.blocking_factor}</span>
                      <span>CP: {node.critical_path_length}</span>
                    </div>
                  </button>
                );
              })}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};
