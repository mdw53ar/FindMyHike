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
  https://console.cloud.google.com/google/maps-apis (enable the Geocoding
  API and Directions API).
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
   returns HTTP 403 to automated requests from this environment (bot
   protection), confirmed both via a research fetch and a live run of the
   actual aggregator — so the search query params and extraction regexes
   are unverified against a real response. Run it from a normal residential
   IP / real browser-like environment, check the logs for "No hikr.org
   report links found," and adjust `_SEARCH_URL`'s params or the regexes
   against real page content as needed.
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
3. **SAC.ch** (`backend/app/sources/sac.py`) — **login and search both
   working**, verified live end-to-end. SAC.ch's login is a full OAuth2/OIDC
   flow through a separate `portal.sac-cas.ch` identity service (fully
   reverse-engineered). The actual route database isn't on sac-cas.ch at
   all — it's a separate AngularJS app, "SuisseAlpine", at
   `www.suissealpine.sac-cas.ch`, with its own public REST API
   (`GET /api/1/route/search?lang=de&type=mountain_hiking`) that turned out
   not to need authentication at all (confirmed: identical results logged
   in or not — the sac-cas.ch session cookie doesn't even apply to that
   domain). A live search returned 25 real routes with real SAC T-grades
   during testing. What's *not* wired up yet: that search endpoint only
   returns name/T-grade/id, not duration, elevation, circularity, or a GPX
   link — those fields are left blank for SAC-sourced hikes. A second,
   thorough pass specifically hunting for that fuller detail endpoint ruled
   out every plausible REST shape (`/route/{id}`, `/routes/{id}`,
   `/document(s)/{id}`, geometry/locale sub-paths, extra query params on
   `/route/search`) and a promising-looking `Vary: Session-Id,X-API-Key`
   response header that turned out to be generic API-gateway boilerplate,
   not something the app itself sends (neither string appears anywhere in
   its JS). The app's edit-form templates *do* reference the right
   underlying fields (`ascent_time_min/max`, `descent_time_min/max`,
   `ascent_altitude`, `descent_altitude`), confirming the data exists
   server-side — it's just not reachable via any HTTP request replay found
   so far. Cracking it likely needs real browser DevTools (or a headless
   browser) to see what the *actual running* Angular app requests when you
   open a specific route's page — something a plain HTTP client can't
   fake, since it requires executing the app's JS. Full trail documented in
   `sac.py`'s module docstring for whoever picks this up next. Also still
   open: whether the separate paid "SAC-Tourenportal Abonnement" advertised
   on sac-cas.ch gates anything beyond what's already working — worth
   checking on your account.

   Practically, this means SAC.ch candidates don't show up in results yet:
   `services/ranking.py`'s hard filter requires a known duration to verify
   the "hike length ≈ requested" constraint (the same "exclude, don't
   guess" rule already applied to unknown travel time and ungeocodable
   trailheads), and SAC hikes have no duration data. The source stays
   wired in — no reason to rip it out, login costs nothing to keep — and
   it'll start contributing real results automatically the moment the
   detail endpoint above is found, with no other code changes needed.
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
