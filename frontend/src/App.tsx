import { useState } from "react";

import { ApiError, searchHikes } from "./api/hikes";
import EmptyState from "./components/EmptyState";
import FilterForm from "./components/FilterForm";
import LoadingState from "./components/LoadingState";
import ResultsTable from "./components/ResultsTable";
import type { HikeResult, SearchRequest } from "./types";

export default function App() {
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState<HikeResult[] | null>(null);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);

  async function handleSearch(request: SearchRequest) {
    setLoading(true);
    setError(null);
    try {
      const response = await searchHikes(request);
      setResults(response.results);
      setWarnings(response.warnings);
    } catch (err) {
      setResults(null);
      setError(err instanceof ApiError ? err.message : "Something went wrong.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto max-w-6xl px-4 py-5">
          <h1 className="text-xl font-semibold text-slate-900">Swiss Hike Finder</h1>
          <p className="text-sm text-slate-500">
            Find hikes matching your start point, time budget and difficulty.
          </p>
        </div>
      </header>

      <main className="mx-auto max-w-6xl space-y-6 px-4 py-6">
        <FilterForm onSubmit={handleSearch} loading={loading} />

        {error && (
          <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
            {error}
          </div>
        )}

        {loading && <LoadingState />}

        {!loading && results !== null && results.length === 0 && (
          <EmptyState warnings={warnings} />
        )}

        {!loading && results !== null && results.length > 0 && (
          <div className="space-y-2">
            {warnings.length > 0 && (
              <ul className="space-y-1 text-xs text-amber-700">
                {warnings.map((w) => (
                  <li key={w}>{w}</li>
                ))}
              </ul>
            )}
            <ResultsTable results={results} />
          </div>
        )}
      </main>
    </div>
  );
}
