import type { SearchRequest, SearchResponse } from "../types";

export class ApiError extends Error {}

export async function searchHikes(request: SearchRequest): Promise<SearchResponse> {
  const res = await fetch("/api/hikes/search", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });

  if (!res.ok) {
    const body = await res.json().catch(() => null);
    const detail = body?.detail ?? `Request failed with status ${res.status}`;
    throw new ApiError(detail);
  }

  return res.json();
}
