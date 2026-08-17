# Swiss Hike Finder — Project Spec

## 1. Overview
A webapp that recommends Swiss hikes matching user-set constraints (start point,
transport mode, travel time budget, hike duration, circularity, SAC difficulty
grade, optional canton). Returns a table of up to 20 hikes enriched with
source link, GPX (if available), transport/cable-car access info, climbing
requirements, weather forecast, and freshness/reliability signals.

## 2. Tech Stack (suggested — adjust freely)
- Frontend: React + Vite, simple dashboard layout, Tailwind for styling
- Backend: Node.js (Express) or Python (FastAPI) — needed to keep API keys
  server-side and to run scraping/search jobs
- No database required for v1 (stateless, query → results); consider SQLite
  cache later for repeated queries (see §7)

## 3. Frontend

### 3.1 Filter form (dashboard)
| Field | Type | Notes |
|---|---|---|
| Start from | Text input (address) | Geocode via Google Maps Geocoding API |
| Go by | Dropdown | `car`, `public transport` |
| Max travel time | Number input (hours) | One-way, from start address to trailhead |
| Hike length | Number input (hours) | Total round-trip time (up + down) |
| Circular hike | Toggle | Yes / No |
| Difficulty | Multi-select checkboxes | T2, T3, T4, T5, T6 (SAC hiking scale) |
| Canton | Dropdown | All 26 cantons + "Any" (optional, default Any) |

Single button: **"Find hikes"**. On click → call backend, show loading state,
then render results as a table/grid.

### 3.2 Results table
One row per hike, columns:
- Name
- Canton
- Difficulty (T-scale)
- Length (h), elevation gain/loss if available
- Circular (Y/N)
- Climbing required (Y/N + grade, e.g. UIAA/SAC climbing scale, if any)
- Travel time from start (car/PT) + mode
- Trailhead access: "reachable by [car/PT]" or "requires cable car"
  - If cable car: name, opening hours, note if usable outside official
    hours via *Selbstbedienung* (self-service)
- Weather forecast (for the hike date/area, from MeteoSwiss)
- Source (SAC / hikr / gipfelbuch / other name) + link (one link only)
- Article/report count found for that route (recency signal)
- GPX link (if found)

Sortable/filterable columns are a nice-to-have, not required for v1.

## 4. Backend logic

### 4.1 Input validation
- Geocode "start from" address (Google Maps API) → lat/lng
- Reject if address can't be geocoded

### 4.2 Hike sourcing (priority order — stop at first success per hike)
1. **SAC.ch** (Schweizer Alpen-Club) — log in with the user's account to
   access full route data (see §6 re: credential handling)
2. **hikr.org** — Swiss hiking community reports
3. **gipfelbuch.ch** — log in with the user's account, same as SAC.ch
4. **Other sources** (fallback only if none of the above yield a result) —
   must record and display the actual source name/domain

Rules:
- Exactly **one link per hike** — the first source (in priority order)
  where a usable route description is found
- Prefer **recent articles/trip reports**; when the source isn't SAC,
  record and display **how many reports/articles** were found for that
  route, to flag potentially outdated/no-longer-recommended routes
- Extract if available: GPX download link, elevation profile, whether
  climbing sections exist (grade in UIAA or SAC scale), circularity,
  official SAC T-grade

### 4.3 Filtering against user constraints
Apply after candidate hikes are gathered:
- Difficulty ∈ selected T-grades
- Total hike duration ≈ requested length (define tolerance, e.g. ±20%)
- Circular flag matches (if user specified)
- Canton matches (if specified)
- Trailhead reachable within max travel time via chosen transport mode

### 4.4 Travel time & access (Google Maps API)
- Compute travel time from start address to trailhead, for the selected
  mode (driving or transit)
- Determine whether the trailhead itself is reachable directly by that
  mode, or whether a cable car / gondola / chairlift is needed to reach
  the actual starting point
- If a cable car is needed:
  - Look up operator's official opening hours/season
  - Note if off-hours self-service (*Selbstbedienung*) access exists —
    this is common for some Swiss mountain railways/huts, but must be
    verified per lift, not assumed

### 4.5 Weather (MeteoSwiss)
- Fetch forecast for the hike's location/region for the relevant date
  (MeteoSwiss has an open API/geo services — confirm exact endpoint
  during implementation, see Open Questions)

### 4.6 Output
- Return up to 20 hikes ranked by best fit to constraints (define a
  simple scoring/ranking rule, e.g. closest match on duration + travel
  time, then freshness)

## 5. Non-functional requirements
- Handle source sites gracefully if scraping/search fails (timeouts,
  layout changes) — skip and log, don't crash the whole request
- Cache results per query (e.g. 24h) to avoid hammering source sites and
  external APIs on repeated identical searches
- Respect robots.txt / terms of use of SAC.ch, hikr.org, gipfelbuch.ch —
  flag if authenticated scraping is against ToS and a manual/API
  alternative is preferable

## 6. Open questions / assumptions to resolve before/at build time
- **Confirmed**: hike-report source is **hikr.org**.
- **Confirmed**: SAC.ch and gipfelbuch.ch logins are automated using the
  user's own credentials. Credentials must be stored as backend secrets
  (env vars / secrets manager), never in frontend code or logs. Session
  cookies should be reused/cached rather than re-logging in on every
  request. Note this is against some sites' ToS for automated access —
  acceptable here since it's the user's own account for personal use,
  but worth a quick review of each site's terms before relying on it
  long-term.
- **API keys needed**: Google Maps (Geocoding + Directions/Distance
  Matrix), and confirmation of which MeteoSwiss endpoint to use (public
  open data vs. commercial API) — need to be provisioned and stored as
  backend secrets, never exposed to the frontend.
- **No general web search API assumed** — sourcing hikes from "other
  sources" (fallback) likely requires either a search API or a
  predefined scraping approach per site.
- **Ranking tie-breaks** and **duration tolerance** (§4.3) are
  placeholders — adjust to taste.
