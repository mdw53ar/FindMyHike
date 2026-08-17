# Swiss Hike Finder (v1)

Recommends Swiss hikes matching your start point, transport mode, travel-time
budget, hike duration, circularity, SAC difficulty grade, and (optionally)
canton. See `task.md` for the full spec this implements.

## Stack
- `backend/` — Python + FastAPI
- `frontend/` — React + Vite + Tailwind

## Setup

### Backend
```
cd backend
python -m venv .venv
.venv/Scripts/activate        # Windows
pip install -r requirements.txt
cp .env.example .env          # then fill in real values (see below)
uvicorn app.main:app --reload --port 8000
```

### Frontend
```
cd frontend
npm install
npm run dev
```
Open http://localhost:5173 — the Vite dev server proxies `/api/*` to the
backend on port 8000.

## Required configuration (`backend/.env`)
- `GOOGLE_MAPS_API_KEY` — required for geocoding the start address and
  computing travel times. Without it, searches return a clear 400 error
  rather than crashing. Get one at
  https://console.cloud.google.com/google/maps-apis/api-list (that
  dedicated Maps Platform page is more reliable than searching the generic
  API Library) and enable:
  - **Geocoding API** — for the start address.
  - **Routes API** — for travel time. *Not* "Directions API": Google
    retired that one for new projects on 2025-03-01 in favor of Routes API,
    which is what `backend/app/services/travel.py` actually calls (POST
    `https://routes.googleapis.com/directions/v2:computeRoutes`, not the
    old GET-based endpoint — a real code change, not just a rename).
- `SAC_USERNAME` / `SAC_PASSWORD`, `GIPFELBUCH_USERNAME` /
  `GIPFELBUCH_PASSWORD` — your own account credentials for each site (§6).
  Login for both is implemented for real and verified live. See "Known
  limitations" below for what's still missing on each.

Weather (MeteoSwiss ICON model via Open-Meteo) needs no key.

## Known limitations / what's left to calibrate
This is a v1 build.

1. **hikr.org scraper** (`backend/app/sources/hikr.py`) — the confirmed,
   public, no-login source. It's a real implementation, built against
   durable URL patterns (`/filter.php`, `/postNNNNN.html`), but hikr.org
   blocks this environment: confirmed via `httpx` (403), and again with a
   **real Chromium browser via Playwright** — not a JS challenge that
   auto-resolves, but Cloudflare's explicit "Sorry, you have been blocked"
   WAF page, which typically fires on known datacenter/cloud IP ranges
   regardless of how browser-like the request looks. Deliberately didn't
   pursue further (residential proxies, TLS fingerprint spoofing, etc.) —
   that crosses from "scraper with realistic headers" into actively
   defeating a security control, which isn't the right call even for
   legitimate personal use. **The scraper code itself is untested against a
   real response but should be re-checked from a normal home/residential
   network** (this sandbox's IP is almost certainly the actual problem, not
   the code) — check the logs for "No hikr.org report links found" and
   adjust `_SEARCH_URL`'s params or the regexes against real page content
   if needed once it's reachable.
2. **gipfelbuch.ch** (`backend/app/sources/gipfelbuch.py`) — **fully
   working, the one source that reaches end users right now**, verified
   live end-to-end (2026-08-17): real login (the site's own `/meta/login`
   ajax flow), real search against `/routen/uebersicht`, and real parsing
   of each listing card's structured stats block (name, canton/region, and
   — via a `data-tooltip="Schwierigkeit: T 4"`-style attribute, not the
   free-text description — real T-grade, duration, and elevation gain). A
   live search returned 25 candidates, 6 of which survived the app's full
   filter/rank pipeline for a sample query. One bug found and fixed along
   the way: the site's article markup is malformed (unclosed tags), which
   `lxml`'s error-recovery mode mis-nested — every article ended up
   containing all *subsequent* articles' stats too, so every parsed hike
   silently got identical (wrong) numbers. Switched to Python's stdlib
   `html.parser`, which handles it correctly — verified exactly 3 stats
   per article afterward. One remaining caveat: the exact request format
   for gipfelbuch's *paginated* "load more" endpoint (`/routen/list`)
   wasn't captured — only the single-page listing was verified, which
   already returns enough results for v1.
3. **SAC.ch** (`backend/app/sources/sac.py`) — **fully working, real
   technical data included**, verified live end-to-end (2026-08-17). Login
   is a full OAuth2/OIDC flow through a separate `portal.sac-cas.ch`
   identity service (fully reverse-engineered). The route database is a
   white-labeled deployment of the open-source **Camptocamp/c2corg
   platform** ("SuisseAlpine"); an earlier pass had settled for its
   `/api/1/route/search` endpoint, which only returns name/id/T-grade — no
   duration or elevation. That turned out to be the wrong endpoint, found
   by driving a real, logged-in browser session with Playwright against
   `https://www.sac-cas.ch/de/huetten-und-touren/sac-tourenportal` (a
   different, working entry point than the standalone `#!/...` SPA, which
   *is* gated behind a paid "Tourenportal-Abonnement" this account doesn't
   have — a real dead end, documented in `sac.py`'s git history, not
   pursued further). That page calls a richer, also-anonymous endpoint:

   ```
   GET https://www.suissealpine.sac-cas.ch/api/1/poi/search
       ?lang=de&output_lang=de&disciplines=mountain_hiking&hut_type=all
       &mode=per_discipline&limit=N
   ```

   Each result is a POI (hut/summit/etc.) carrying a nested `routes` array
   — the real approach routes to reach it, each with genuine
   `ascent_time_min/max` + `descent_time_min/max` (minutes, → duration),
   `ascent_altitude`/`descent_altitude` (meters), and `main_difficulty`
   (T-grade). A live search returned 41 candidates, all with real duration
   data, and 11 of them survived the app's full filter/rank pipeline for a
   sample query. The permalink pattern
   (`https://www.sac-cas.ch/de/huetten-und-touren/sac-tourenportal/{poi_id}`)
   was confirmed by clicking through the real UI, not guessed — one honest
   imprecision: it points at the destination POI, not at the one specific
   approach route among possibly several, since no per-route permalink was
   found. Still not wired up: circularity, climbing-section grades, and a
   GPX download link — the real UI has a "GPX-Datei herunterladen" button,
   but the request it fires wasn't captured this pass; a follow-up
   Playwright session (click that button, capture the request) would find
   it the same way the `poi/search` endpoint was found.
4. **"Other sources" fallback** (§4.2 step 4) — intentionally a no-op per
   §6 ("no general web search API assumed"). Plug in a SERP API key or a
   specific fallback site here if needed.
5. **Cable car hours/Selbstbedienung** (`backend/app/services/cableways.py`)
   — a small curated table of ~10 well-known lifts, plus a keyword heuristic
   to detect when a hike's trailhead needs one. Lifts not in the table are
   explicitly reported as "verify with operator," never guessed, per the
   spec's warning that self-service access must be verified per lift.
6. **Weather date** — the filter form has no date field, so the app shows a
   2-day forecast (tomorrow + day after), labeled by date.

## Testing
```
cd backend
pytest              # ranking/filtering logic + hikr.org parser (fixture-based, no network)
```
Frontend has no test suite yet (v1); `npm run build` typechecks it.
