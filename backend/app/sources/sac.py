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

**Tour search is partially implemented**, verified live (2026-08-17). The
actual route database isn't on `www.sac-cas.ch` at all (that's mostly
marketing content) — it's a separate AngularJS single-page app,
"SuisseAlpine", at `www.suissealpine.sac-cas.ch`, talking to its own REST
API at `www.suissealpine.sac-cas.ch/api/1/...`. That API turned out to be
**public/unauthenticated for search** — `www.sac-cas.ch`'s login cookie
doesn't even carry over to that domain, and anonymous requests return the
identical data authenticated ones do (tested both ways). Confirmed working:

    GET /api/1/route/search?lang=de&type=mountain_hiking&limit=N&offset=N

- `type` is a Postgres enum (`discipline`); `mountain_hiking` is the one
  that carries the SAC T-grade scale this app filters by. Other valid
  values seen: `alpine_tour`, `alpine_climbing`, `ski_tour`,
  `snowshoe_tour`, `via_ferrata` (an invalid value 400s with a raw SQL
  error that conveniently reveals the enum name — that's how these were
  found).
- Response shape: `{"results": [...], "cursor": <next offset>}`. Each
  result has `id`, `title` (dict keyed by language, e.g. `{"de": "..."}`),
  `main_difficulty` (the real SAC T-grade, e.g. `"T4"`, or `None`),
  `destination_poi.regions_denormalization` (dict keyed by language, e.g.
  `{"de": "Berner Alpen", ...}` — a region name, not one of the 26
  cantons), `availability` (seen: `"limited"` — unclear if this reflects
  the "Tourenportal-Abonnement" gate mentioned on sac-cas.ch, or something
  else; worth revisiting), and `gis_geometry_ok` (bool — hints at whether
  GPX/track geometry exists, though the geometry itself isn't in this
  payload).
- **Not found in this pass**: duration, elevation gain/loss, circularity,
  or a GPX download link. Those aren't in the search/listing payload above
  — `/api/1/route/{id}` only allows `DELETE, OPTIONS` (not a read
  endpoint), and no other detail endpoint was located. A route's public
  page is assumed to be `https://www.suissealpine.sac-cas.ch/#!/route/{id}`
  (the app's Angular hashbang convention; a 200 was confirmed for that URL
  shape, but since the server can't see the `#!...` fragment, that only
  proves the SPA shell loads, not that the specific route renders).

A second, more thorough pass (2026-08-17) specifically hunting for the
technical-detail endpoint came up empty, and ruled out several plausible
leads rather than just giving up early:
- The Angular edit/view templates *do* reference the right field names
  (`route.ascent_time_min`/`ascent_time_max`, `descent_time_min`/
  `descent_time_max`, `ascent_altitude`, `descent_altitude`, a
  "+ Upload GPX/KML" widget) — so a fuller document with this data
  definitely exists server-side, it's just not reachable through anything
  found so far.
- Every plausible REST shape for fetching one route was tried and 404s or
  405s: `/route/{id}` (405, `Allow: DELETE, OPTIONS` — genuinely no GET
  handler registered, not a permissions issue), `/routes/{id}`, `/document/
  {id}`, `/documents/{id}`, `/route/{id}/geometry`, `/route/{id}/locales`,
  `/route/{id}/de`, `/geometry/{id}`, `/api/2/...`. Extra query params on
  the working `/route/search` endpoint (`extended`, `full`, `fields=all`,
  `format=full`, `detail=full`, `expand`) were all silently ignored —
  doesn't unlock more fields.
- `/route/search`'s response carries a `Vary: Session-Id,X-API-Key,Origin`
  header, which looked promising (an auth mechanism not yet tried), but
  neither `Session-Id` nor `X-API-Key` appears anywhere in either JS bundle
  (`loadApp.js`, `dependencies.js`), and the same Vary header shows up on
  `/poi/search` too — this is almost certainly generic API-gateway/cache
  config, not something this specific frontend actually sends. Ruled out,
  not just unexplored.
- No `client_id`, `oauth`, or `portal.sac-cas.ch` reference exists anywhere
  in the app's JS either, so (unlike `www.sac-cas.ch`) this app doesn't
  appear to run its own separate OAuth handshake — the "how does the
  logged-in web app get more data than this" question is still open.

Realistically, the remaining lead can't be resolved by replaying HTTP
requests with curl/httpx — it needs to see what the *actual, running*
Angular app requests when you open a specific route's detail page (e.g.
https://www.suissealpine.sac-cas.ch/#!/route/4523), since that call isn't
one of the URL shapes above. That means either real browser DevTools
(Network tab, filter by XHR, click a route on the real site) or driving a
headless browser (Playwright) against the real app and capturing its
traffic — both need actual JS execution, which a plain HTTP client can't
fake here. Once that request is known, fill in `length_h` /
`elevation_gain_m` / `elevation_loss_m` / `circular` / `gpx_url` on
`RawHike` in `_search` below (currently left `None`).
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
_ROUTE_SEARCH_URL = f"{_TOURENPORTAL_URL}/api/1/route/search"
_ROUTE_DETAIL_URL_TEMPLATE = f"{_TOURENPORTAL_URL}/#!/route/{{id}}"
_ROUTE_PAGE_SIZE = 25

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
        # The SuisseAlpine route-search API is public (verified: identical
        # results with or without the www.sac-cas.ch login cookie, which
        # doesn't even apply to this domain) — see module docstring.
        # "mountain_hiking" is the discipline that carries SAC's T-grade
        # scale, which is what this app filters by.
        try:
            resp = await client.get(
                _ROUTE_SEARCH_URL,
                params={
                    "lang": "de",
                    "type": "mountain_hiking",
                    "limit": _ROUTE_PAGE_SIZE,
                    "offset": 0,
                },
            )
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("SAC.ch route search failed: %s", exc)
            return []

        results: list[RawHike] = []
        for item in data.get("results", []):
            title = (item.get("title") or {}).get("de")
            item_id = item.get("id")
            if not title or item_id is None:
                continue

            # Region names here (e.g. "Berner Alpen") are alpine/geographic
            # regions, not one of the 26 political cantons this app filters
            # by, and no reliable mapping between the two was established —
            # left unset rather than guessed, per the same principle applied
            # to cable car hours (see services/cableways.py).
            results.append(
                RawHike(
                    name=title,
                    source_name="SAC.ch",
                    source_url=_ROUTE_DETAIL_URL_TEMPLATE.format(id=item_id),
                    canton=None,
                    difficulty=item.get("main_difficulty"),
                    raw_text=title,
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
