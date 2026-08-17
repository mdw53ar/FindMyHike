export type TransportMode = "car" | "public_transport";

export type Difficulty = "T2" | "T3" | "T4" | "T5" | "T6";

export interface SearchRequest {
  start_address: string;
  mode: TransportMode;
  max_travel_time_h: number;
  hike_length_h: number;
  circular: boolean | null;
  difficulties: Difficulty[];
  canton: string | null;
}

export interface WeatherDay {
  date: string;
  summary: string;
  temp_min_c: number | null;
  temp_max_c: number | null;
  precipitation_probability_pct: number | null;
}

export interface CablewayAccess {
  required: boolean;
  name: string | null;
  opening_hours: string | null;
  season: string | null;
  selbstbedienung: boolean | null;
  note: string | null;
}

export interface HikeResult {
  name: string;
  canton: string | null;
  difficulty: string | null;
  length_h: number | null;
  elevation_gain_m: number | null;
  elevation_loss_m: number | null;
  circular: boolean | null;
  climbing_required: boolean;
  climbing_grade: string | null;
  travel_time_h: number | null;
  travel_mode: TransportMode;
  trailhead_access: string;
  cableway: CablewayAccess | null;
  weather: WeatherDay[];
  source_name: string;
  source_url: string;
  report_count: number | null;
  gpx_url: string | null;
  score: number | null;
}

export interface SearchResponse {
  results: HikeResult[];
  cached: boolean;
  warnings: string[];
}
