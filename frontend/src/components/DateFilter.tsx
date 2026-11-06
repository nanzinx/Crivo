"use client";
import { presets } from "@/lib/api";

export default function DateFilter({
  ini,
  fim,
  onChange,
}: {
  ini: string;
  fim: string;
  onChange: (i: string, f: string) => void;
}) {
  const pList = presets();
  const isAll = !ini && !fim;

  return (
    <div className="flex flex-wrap items-center gap-2">
      <div className="flex items-center gap-1.5 bg-slate-900 border border-slate-800 rounded-lg px-2 py-1">
        <label className="text-[11px] font-medium text-slate-400">De</label>
        <input
          type="date"
          value={ini}
          onChange={(e) => onChange(e.target.value, fim)}
          className="bg-transparent border-0 p-0 text-xs focus:ring-0"
        />
        <label className="text-[11px] font-medium text-slate-400 ml-1">Até</label>
        <input
          type="date"
          value={fim}
          onChange={(e) => onChange(ini, e.target.value)}
          className="bg-transparent border-0 p-0 text-xs focus:ring-0"
        />
      </div>

      <div className="flex flex-wrap items-center gap-1">
        {Object.entries(pList).map(([k, [a, b]]) => {
          const active = (k === "Todas" && isAll) || (ini === a && fim === b && !isAll);
          return (
            <button
              key={k}
              type="button"
              className={`px-2.5 py-1 text-xs rounded-lg transition font-medium border ${
                active
                  ? "bg-indigo-600 text-white border-indigo-500 shadow-sm"
                  : "bg-slate-900 text-slate-300 border-slate-800 hover:bg-slate-800"
              }`}
              onClick={() => onChange(a, b)}
            >
              {k}
            </button>
          );
        })}
      </div>
    </div>
  );
}
