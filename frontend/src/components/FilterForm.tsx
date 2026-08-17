import { useState } from "react";

import { CANTONS } from "../constants/cantons";
import type { Difficulty, SearchRequest, TransportMode } from "../types";

const ALL_DIFFICULTIES: Difficulty[] = ["T2", "T3", "T4", "T5", "T6"];

interface Props {
  onSubmit: (request: SearchRequest) => void;
  loading: boolean;
}

export default function FilterForm({ onSubmit, loading }: Props) {
  const [startAddress, setStartAddress] = useState("");
  const [mode, setMode] = useState<TransportMode>("car");
  const [maxTravelTimeH, setMaxTravelTimeH] = useState(2);
  const [hikeLengthH, setHikeLengthH] = useState(5);
  const [circular, setCircular] = useState(false);
  const [difficulties, setDifficulties] = useState<Difficulty[]>(["T2", "T3"]);
  const [canton, setCanton] = useState("");

  function toggleDifficulty(d: Difficulty) {
    setDifficulties((prev) =>
      prev.includes(d) ? prev.filter((x) => x !== d) : [...prev, d]
    );
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    onSubmit({
      start_address: startAddress,
      mode,
      max_travel_time_h: maxTravelTimeH,
      hike_length_h: hikeLengthH,
      circular,
      difficulties,
      canton: canton || null,
    });
  }

  const canSubmit = startAddress.trim().length >= 3 && difficulties.length > 0;

  return (
    <form
      onSubmit={handleSubmit}
      className="grid grid-cols-1 gap-4 rounded-lg border border-slate-200 bg-white p-6 shadow-sm sm:grid-cols-2 lg:grid-cols-3"
    >
      <div className="sm:col-span-2 lg:col-span-1">
        <label className="mb-1 block text-sm font-medium text-slate-700">
          Start from
        </label>
        <input
          type="text"
          value={startAddress}
          onChange={(e) => setStartAddress(e.target.value)}
          placeholder="e.g. Bahnhofstrasse 1, Zürich"
          className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
          required
        />
      </div>

      <div>
        <label className="mb-1 block text-sm font-medium text-slate-700">Go by</label>
        <select
          value={mode}
          onChange={(e) => setMode(e.target.value as TransportMode)}
          className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
        >
          <option value="car">Car</option>
          <option value="public_transport">Public transport</option>
        </select>
      </div>

      <div>
        <label className="mb-1 block text-sm font-medium text-slate-700">
          Max travel time (h)
        </label>
        <input
          type="number"
          min={0.1}
          step={0.25}
          value={maxTravelTimeH}
          onChange={(e) => setMaxTravelTimeH(Number(e.target.value))}
          className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
        />
      </div>

      <div>
        <label className="mb-1 block text-sm font-medium text-slate-700">
          Hike length (h, round trip)
        </label>
        <input
          type="number"
          min={0.5}
          step={0.5}
          value={hikeLengthH}
          onChange={(e) => setHikeLengthH(Number(e.target.value))}
          className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
        />
      </div>

      <div className="flex items-end">
        <label className="flex items-center gap-2 text-sm font-medium text-slate-700">
          <input
            type="checkbox"
            checked={circular}
            onChange={(e) => setCircular(e.target.checked)}
            className="h-4 w-4 rounded border-slate-300 text-emerald-600 focus:ring-emerald-500"
          />
          Circular hike
        </label>
      </div>

      <div>
        <label className="mb-1 block text-sm font-medium text-slate-700">Canton</label>
        <select
          value={canton}
          onChange={(e) => setCanton(e.target.value)}
          className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
        >
          <option value="">Any</option>
          {CANTONS.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>
      </div>

      <div className="sm:col-span-2 lg:col-span-3">
        <span className="mb-1 block text-sm font-medium text-slate-700">
          Difficulty (SAC scale)
        </span>
        <div className="flex flex-wrap gap-4">
          {ALL_DIFFICULTIES.map((d) => (
            <label key={d} className="flex items-center gap-2 text-sm text-slate-700">
              <input
                type="checkbox"
                checked={difficulties.includes(d)}
                onChange={() => toggleDifficulty(d)}
                className="h-4 w-4 rounded border-slate-300 text-emerald-600 focus:ring-emerald-500"
              />
              {d}
            </label>
          ))}
        </div>
      </div>

      <div className="sm:col-span-2 lg:col-span-3">
        <button
          type="submit"
          disabled={!canSubmit || loading}
          className="rounded-md bg-emerald-600 px-5 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-emerald-700 disabled:cursor-not-allowed disabled:bg-slate-300"
        >
          {loading ? "Searching…" : "Find hikes"}
        </button>
      </div>
    </form>
  );
}
