import type { HikeResult } from "../types";

interface Props {
  results: HikeResult[];
}

function formatHours(h: number | null): string {
  return h === null ? "—" : `${h.toFixed(1)} h`;
}

function CablewayCell({ hike }: { hike: HikeResult }) {
  if (hike.trailhead_access.startsWith("unknown")) {
    return <span className="text-slate-400">unknown</span>;
  }
  if (hike.trailhead_access !== "requires cable car" || !hike.cableway) {
    return <span className="text-slate-500">reachable directly</span>;
  }
  const c = hike.cableway;
  return (
    <div className="space-y-0.5">
      <div className="font-medium text-slate-800">{c.name ?? "Cable car required"}</div>
      {c.opening_hours && <div className="text-xs text-slate-500">{c.opening_hours}</div>}
      {c.selbstbedienung === true && (
        <div className="text-xs text-emerald-700">Selbstbedienung available off-hours</div>
      )}
      {c.selbstbedienung === null && (
        <div className="text-xs text-amber-700">Selbstbedienung: unverified</div>
      )}
      {c.note && <div className="text-xs text-slate-400">{c.note}</div>}
    </div>
  );
}

function WeatherCell({ hike }: { hike: HikeResult }) {
  if (hike.weather.length === 0) {
    return <span className="text-slate-400">unavailable</span>;
  }
  return (
    <div className="space-y-1">
      {hike.weather.map((day) => (
        <div key={day.date} className="text-xs">
          <span className="font-medium text-slate-700">{day.date}</span>{" "}
          <span className="text-slate-600">{day.summary}</span>{" "}
          {day.temp_min_c !== null && day.temp_max_c !== null && (
            <span className="text-slate-500">
              ({Math.round(day.temp_min_c)}–{Math.round(day.temp_max_c)}°C)
            </span>
          )}
        </div>
      ))}
    </div>
  );
}

export default function ResultsTable({ results }: Props) {
  return (
    <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white shadow-sm">
      <table className="min-w-full divide-y divide-slate-200 text-sm">
        <thead className="bg-slate-50">
          <tr>
            {[
              "Name", "Canton", "Difficulty", "Length / Elevation", "Circular",
              "Climbing", "Travel time", "Trailhead access", "Weather",
              "Source", "Reports", "GPX",
            ].map((h) => (
              <th
                key={h}
                className="px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-slate-500"
              >
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {results.map((hike) => (
            <tr key={`${hike.source_url}-${hike.name}`} className="align-top">
              <td className="px-3 py-3 font-medium text-slate-900">{hike.name}</td>
              <td className="px-3 py-3 text-slate-600">{hike.canton ?? "—"}</td>
              <td className="px-3 py-3 text-slate-600">{hike.difficulty ?? "—"}</td>
              <td className="px-3 py-3 text-slate-600">
                <div>{formatHours(hike.length_h)}</div>
                {(hike.elevation_gain_m || hike.elevation_loss_m) && (
                  <div className="text-xs text-slate-400">
                    +{hike.elevation_gain_m ?? "?"} / -{hike.elevation_loss_m ?? "?"} m
                  </div>
                )}
              </td>
              <td className="px-3 py-3 text-slate-600">
                {hike.circular === null ? "—" : hike.circular ? "Y" : "N"}
              </td>
              <td className="px-3 py-3 text-slate-600">
                {hike.climbing_required
                  ? `Y${hike.climbing_grade ? ` (${hike.climbing_grade})` : ""}`
                  : "N"}
              </td>
              <td className="px-3 py-3 text-slate-600">
                {formatHours(hike.travel_time_h)}
                <div className="text-xs text-slate-400">
                  {hike.travel_mode === "car" ? "car" : "public transport"}
                </div>
              </td>
              <td className="px-3 py-3">
                <CablewayCell hike={hike} />
              </td>
              <td className="px-3 py-3">
                <WeatherCell hike={hike} />
              </td>
              <td className="px-3 py-3">
                <a
                  href={hike.source_url}
                  target="_blank"
                  rel="noreferrer"
                  className="text-emerald-700 hover:underline"
                >
                  {hike.source_name}
                </a>
              </td>
              <td className="px-3 py-3 text-slate-600">{hike.report_count ?? "—"}</td>
              <td className="px-3 py-3">
                {hike.gpx_url ? (
                  <a
                    href={hike.gpx_url}
                    target="_blank"
                    rel="noreferrer"
                    className="text-emerald-700 hover:underline"
                  >
                    GPX
                  </a>
                ) : (
                  <span className="text-slate-400">—</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
