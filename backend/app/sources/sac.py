"""SAC.ch adapter. §6 confirms this uses the user's own account.

**Login is fully implemented and verified live** (2026-08-17, with a real
account) — SAC.ch's login is a multi-hop OAuth2/OIDC flow, not a plain form
POST:

1. A logged-out page on `www.sac-cas.ch` (TYPO3) contains a login link of
   the form `/de/login/?&login_url=...&validation_hash=...` — both query
   params are generated per page-load and tied to the session cookie, so
   this link must be scraped fresh from a real page, not hardcoded.
2. Following that link 302-redirects through
   `portal.sac-cas.ch/oauth/authorize` to a Rails/Devise sign-in page at
   `portal.sac-cas.ch/de/users/sign_in?oauth=true`, which has a real HTML
   form (`#new_person`) with a fresh `authenticity_token`, plus fields
   `person[login_identity]` (email) and `person[password]`.
3. POSTing that form (as `application/x-www-form-urlencoded`, same cookie
   jar) authenticates the session on `portal.sac-cas.ch`, which 303s back
   through `oauth/authorize` (now succeeding) to `www.sac-cas.ch`'s OIDC
   callback with a fresh authorization `code`, which itself redirects to an
   authenticated `www.sac-cas.ch` page. With an `httpx.AsyncClient(
   follow_redirects=True)`, this entire 303→302→303→302 chain is chased
   automatically within the single login POST call — no separate steps
   needed.
4. The final authenticated page contains an `oidc/logout` link with a live
   `id_token_hint` — that's the "am I logged in" signal used below.

**Tour search is fully implemented with real technical data**, found by
driving a real, logged-in browser session with Playwright against
`https://www.sac-cas.ch/de/huetten-und-touren/sac-tourenportal` — a
different, working entry point than the standalone
`www.suissealpine.sac-cas.ch` Angular SPA (`#!/...`), which turned out to
be gated behind "You do not have permission to access this site" for
this account (almost certainly the separate paid "Tourenportal
Abonnement" — a real dead end, not a bug, documented in git history for
this file). This embedded widget on sac-cas.ch itself isn't gated the same
way, and — crucially — it calls a *different, richer* API than the
`/route/search` endpoint an earlier pass had settled for:

    GET https://www.suissealpine.sac-cas.ch/api/1/poi/search
        ?lang=de&output_lang=de&order_by=-first_time_published
        &disciplines=mountain_hiking&hut_type=all&mode=per_discipline&limit=N

This is public/unauthenticated (verified: identical response with or
without login) and returns POIs — huts, summits, etc. — each carrying a
nested `routes` array: the actual approach routes to reach that
destination, WITH the technical data the old endpoint lacked:
`ascent_time_min`/`ascent_time_max` (minutes), `descent_time_min`/
`descent_time_max` (minutes), `ascent_altitude`/`descent_altitude`
(meters), `main_difficulty` (SAC T-grade), `discipline`, `title` (e.g.
"Von Miralago" — an approach description, not a standalone hike name; hike
names are built as `f"{poi_name}: {route_title}"`), and per-route `id`.
`availability` is still often `"limited"` per route even on these fully
populated entries — that field doesn't gate this data the way it seemed to
on the old endpoint; it likely governs something else (comment/photo
visibility, maybe).

The permalink for a destination POI (confirmed by clicking through the
real UI, not guessed) is:

    https://www.sac-cas.ch/de/huetten-und-touren/sac-tourenportal/{poi_id}

— it points at the destination (a hut/summit can have several approach
routes), not at one specific route within it, which is a real but minor
imprecision worth knowing about.

Not carried over from this endpoint: circularity, climbing-section
grades, and a GPX download link — the real UI does have a
"GPX-Datei herunterladen" (download GPX) button, but the request it fires
wasn't captured in this pass. `RawHike.circular`, `.climbing_required/
_grade`, and `.gpx_url` are left unset for SAC-sourced hikes; a follow-up
Playwright pass (click the GPX button, capture the request) would find it
the same way this endpoint was found.
"""

import html
import json
import logging
import re
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from app.config import CACHE_DIR, settings
from app.models import SearchRequest
from app.sources.base import HikeSource, RawHike

logger = logging.getLogger(__name__)

_SESSION_FILE = CACHE_DIR / "sac_session.json"

BASE_URL = "https://www.sac-cas.ch"
_HOME_URL = f"{BASE_URL}/de/"
_SIGNIN_URL_RE = re.compile(r'href="(https://www\.sac-cas\.ch/de/login/\?[^"]*)"')

_TOURENPORTAL_URL = "https://www.suissealpine.sac-cas.ch"
_POI_SEARCH_URL = f"{_TOURENPORTAL_URL}/api/1/poi/search"
_POI_DETAIL_URL_TEMPLATE = f"{BASE_URL}/de/huetten-und-touren/sac-tourenportal/{{poi_id}}"
_POI_PAGE_SIZE = 25
# The discipline that carries SAC's T-grade (hiking) scale, which is what
# this app filters by — other values seen: alpine_tour, ski_tour, etc.
_ROUTE_DISCIPLINE = "mountain_hiking"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
}


class SacSource(HikeSource):
    name = "SAC.ch"

    async def discover(self, criteria: SearchRequest) -> list[RawHike]:
        if not settings.sac_configured:
            logger.info("SAC.ch sourcing skipped: SAC_USERNAME/SAC_PASSWORD not set")
            return []

        try:
            async with httpx.AsyncClient(
                timeout=15, headers=_HEADERS, follow_redirects=True
            ) as client:
                if not await self._ensure_logged_in(client):
                    return []
                return await self._search(client, criteria)
        except Exception:
            logger.exception("SAC.ch discovery failed; returning no candidates")
            return []

    async def _ensure_logged_in(self, client: httpx.AsyncClient) -> bool:
        cookies = self._load_cached_cookies()
        if cookies:
            client.cookies.update(cookies)
            if await self._session_is_valid(client):
                return True

        if await self._login(client):
            self._save_cookies(dict(client.cookies))
            return True

        logger.warning("SAC.ch login failed; skipping this source")
        return False

    async def _session_is_valid(self, client: httpx.AsyncClient) -> bool:
        try:
            resp = await client.get(_HOME_URL)
            resp.raise_for_status()
        except httpx.HTTPError:
            return False
        return "oidc/logout" in resp.text

    async def _login(self, client: httpx.AsyncClient) -> bool:
        try:
            home_resp = await client.get(_HOME_URL)
            home_resp.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("SAC.ch: could not load homepage: %s", exc)
            return False

        match = _SIGNIN_URL_RE.search(home_resp.text)
        if not match:
            logger.warning(
                "SAC.ch: no login link found on homepage (layout changed?)"
            )
            return False
        login_link = html.unescape(match.group(1))

        try:
            signin_resp = await client.get(login_link, headers={"Referer": _HOME_URL})
            signin_resp.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("SAC.ch: sign-in redirect chain failed: %s", exc)
            return False

        soup = BeautifulSoup(signin_resp.text, "lxml")
        form = soup.find("form", id="new_person")
        token_input = form.find("input", {"name": "authenticity_token"}) if form else None
        if not form or not token_input:
            logger.warning(
                "SAC.ch: sign-in form not found at %s (layout changed, or "
                "already logged in via a different path?)",
                signin_resp.url,
            )
            return False

        signin_action = urljoin(str(signin_resp.url), form["action"])
        try:
            login_resp = await client.post(
                signin_action,
                data={
                    "authenticity_token": token_input["value"],
                    "person[login_identity]": settings.sac_username,
                    "person[password]": settings.sac_password,
                    "person[remember_me]": "0",
                },
                headers={"Referer": str(signin_resp.url)},
            )
            login_resp.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("SAC.ch login POST failed: %s", exc)
            return False

        if "sign_in" in str(login_resp.url):
            logger.warning("SAC.ch login rejected (still on sign-in page) — check credentials")
            return False

        # With follow_redirects=True, httpx already chases the full
        # 303 -> oauth/authorize -> 302 -> oidc callback -> 302 -> homepage
        # chain within this single POST, landing on an authenticated
        # www.sac-cas.ch page. No separate step is needed (verified live —
        # earlier drafts of this code tried re-hitting the original
        # authorize link afterwards, which actually broke things by reusing
        # an already-consumed link).
        return "oidc/logout" in login_resp.text

    async def _search(
        self, client: httpx.AsyncClient, criteria: SearchRequest
    ) -> list[RawHike]:
        # Public/unauthenticated (verified: identical response logged in or
        # not) — see module docstring. Each POI (hut/summit/etc.) carries a
        # nested `routes` array of approach routes, which is where the real
        # technical data (duration, elevation) actually lives — the
        # single-discipline query still returns POIs whose *other* routes
        # cover different disciplines, so `_ROUTE_DISCIPLINE` is filtered
        # again per-route below rather than trusted from the query alone.
        try:
            resp = await client.get(
                _POI_SEARCH_URL,
                params={
                    "lang": "de",
                    "output_lang": "de",
                    "order_by": "-first_time_published",
                    "disciplines": _ROUTE_DISCIPLINE,
                    "hut_type": "all",
                    "mode": "per_discipline",
                    "limit": _POI_PAGE_SIZE,
                },
            )
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("SAC.ch POI search failed: %s", exc)
            return []

        results: list[RawHike] = []
        for poi in data.get("results", []):
            poi_id = poi.get("id")
            poi_name = poi.get("display_name")
            if poi_id is None or not poi_name:
                continue

            source_url = _POI_DETAIL_URL_TEMPLATE.format(poi_id=poi_id)
            # Region names here (e.g. "Berner Alpen") are alpine/geographic
            # regions, not one of the 26 political cantons this app filters
            # by, and no reliable mapping between the two was established —
            # left unset rather than guessed, per the same principle applied
            # to cable car hours (see services/cableways.py).
            canton = None

            for route in poi.get("routes") or []:
                if route.get("discipline") != _ROUTE_DISCIPLINE:
                    continue
                route_title = route.get("title")
                name = f"{poi_name}: {route_title}" if route_title else poi_name

                results.append(
                    RawHike(
                        name=name,
                        source_name="SAC.ch",
                        source_url=source_url,
                        canton=canton,
                        difficulty=route.get("main_difficulty"),
                        length_h=_route_duration_h(route),
                        elevation_gain_m=route.get("ascent_altitude"),
                        elevation_loss_m=route.get("descent_altitude"),
                        raw_text=name,
                    )
                )
        return results

    def _load_cached_cookies(self) -> dict | None:
        if not _SESSION_FILE.exists():
            return None
        try:
            return json.loads(_SESSION_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def _save_cookies(self, cookies: dict) -> None:
        try:
            _SESSION_FILE.write_text(json.dumps(cookies), encoding="utf-8")
        except OSError:
            logger.warning("Could not persist SAC.ch session cookies to %s", _SESSION_FILE)


def _route_duration_h(route: dict) -> float | None:
    """Round-trip duration estimate: ascent + descent time, each in minutes
    (only the ascent leg is always populated — many routes have no descent
    time recorded, in which case this falls back to ascent-only, an
    underestimate for anything but a one-way approach)."""
    ascent = route.get("ascent_time_max") or route.get("ascent_time_min")
    descent = route.get("descent_time_max") or route.get("descent_time_min")
    minutes = (ascent or 0) + (descent or 0)
    return minutes / 60 if minutes else None
