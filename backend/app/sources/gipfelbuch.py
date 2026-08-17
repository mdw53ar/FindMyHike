"""gipfelbuch.ch adapter. §6 confirms this uses the user's own account.

Verified live against the real site (2026-08-17) with a real account, so
unlike the original stub this is a working implementation, not a
placeholder:

- Login is a jQuery/ajax flow, not a plain form POST. Loading the page sets
  a `dvf_csrf_token` (tied to the PHPSESSID cookie) and a `PHPSESSID`
  cookie. Both the "show login form" and "submit login" actions hit the
  same endpoint: `POST /meta/login`.
    * To submit: multipart/form-data with `dvf_csrf_token`, `email_login`,
      `password_login`, `dvForm_mandatory[]=email_login`,
      `dvForm_mandatory[]=password_login`, `var2=1`, `dvForm_subm=1`.
    * Response body is the literal string `META OK` on success, or HTML
      (an error message to redisplay) on failure. There's no redirect to
      follow — auth state lives entirely in the session cookie afterwards.
- Session validity: an authenticated GET of `/` contains `id="mein"` in the
  nav (the user's name/profile link); a logged-out page doesn't.
- Route search/listing lives at `/routen/uebersicht`, with a filter form
  (`#routen-form`) POSTing to a paginated list endpoint following the
  pattern `/{controller}/{action}list` (i.e. `/routen/list` for the
  "load more" pagination seen on that page). Useful filter fields found on
  that form: `src_routen` (free text), `src_routen_region` (broad
  geographic region, NOT the 26 Swiss cantons — see `_REGION_BY_CANTON`),
  `src_dauer` (bucketed duration: 1='1-2h', 2='2-3h', 3='4-6h', 4='>6h'),
  `src_routen_type` (5='Wanderung'/hiking, 8='Hochtour', 9='Klettersteig').
- Each result is an `<article class="item list-item select-route" ...>`
  with the route id in `data-id`, a detail link `/routen/{id}-{slug}`, a
  title in `<h2>`, a region string in `.topinfo .right` (e.g.
  "CH - Zentralschweiz"), and the SAC T-grade embedded in the free-text
  description as "Schwierigkeit: T 4" (note the space between T and the
  number — different from hikr.org's "T4").

Not yet verified live (left for a follow-up pass, since the filter-form
submission format for the paginated list endpoint wasn't captured — only
the field names were, from the static page): the exact request body
`/routen/list` expects. `_search` is implemented against the best-available
evidence (mirroring the filter form's own field names) and is
defensively guarded, but should be checked against real traffic if it
comes back empty.
"""

import json
import logging
import re

import httpx
from bs4 import BeautifulSoup

from app.config import CACHE_DIR, settings
from app.models import SearchRequest
from app.sources.base import HikeSource, RawHike

logger = logging.getLogger(__name__)

BASE_URL = "https://www.gipfelbuch.ch"
_SESSION_FILE = CACHE_DIR / "gipfelbuch_session.json"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
}

# gipfelbuch.ch's `src_routen_region` options are broad geographic regions,
# not the 26 Swiss cantons the rest of this app filters by. Best-effort
# mapping from canton -> region id, per the option list captured live from
# the filter form on /routen/uebersicht.
_REGION_BY_CANTON: dict[str, str] = {
    "Vaud": "1", "Fribourg": "1", "Bern": "1",
    "Glarus": "2", "St. Gallen": "2",
    "Graubünden": "3",
    "Ticino": "4",
    "Valais": "5",
    "Uri": "6", "Schwyz": "6", "Obwalden": "6", "Nidwalden": "6",
    "Lucerne": "6", "Zug": "6",
    "Jura": "40",
}
# Duration filter buckets (`src_dauer`); hikes are matched to the bucket
# whose range contains the requested `hike_length_h`.
_DURATION_BUCKETS = [(1, 2, "1"), (2, 3, "2"), (4, 6, "3"), (6, 999, "4")]

_TGRADE_RE = re.compile(r"^T\s?([2-6])\s?([+-]?)$")
_HOURS_RE = re.compile(r"([\d.]+)\s*h")
_METERS_RE = re.compile(r"(\d+)\s*m")
_MAX_CANDIDATES = 25


class GipfelbuchSource(HikeSource):
    name = "gipfelbuch.ch"

    async def discover(self, criteria: SearchRequest) -> list[RawHike]:
        if not settings.gipfelbuch_configured:
            logger.info(
                "gipfelbuch.ch sourcing skipped: GIPFELBUCH_USERNAME/"
                "GIPFELBUCH_PASSWORD not set"
            )
            return []

        try:
            async with httpx.AsyncClient(
                timeout=15, headers=_HEADERS, follow_redirects=True
            ) as client:
                if not await self._ensure_logged_in(client):
                    return []
                return await self._search(client, criteria)
        except Exception:
            logger.exception("gipfelbuch.ch discovery failed; returning no candidates")
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

        logger.warning("gipfelbuch.ch login failed; skipping this source")
        return False

    async def _session_is_valid(self, client: httpx.AsyncClient) -> bool:
        try:
            resp = await client.get(BASE_URL + "/")
            resp.raise_for_status()
        except httpx.HTTPError:
            return False
        return 'id="mein"' in resp.text

    async def _login(self, client: httpx.AsyncClient) -> bool:
        try:
            form_resp = await client.post(f"{BASE_URL}/meta/login")
            form_resp.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("gipfelbuch.ch: could not load login form: %s", exc)
            return False

        soup = BeautifulSoup(form_resp.text, "lxml")
        token_input = soup.find("input", {"name": "dvf_csrf_token"})
        if not token_input or not token_input.get("value"):
            logger.warning("gipfelbuch.ch: login form had no CSRF token (layout changed?)")
            return False

        try:
            login_resp = await client.post(
                f"{BASE_URL}/meta/login",
                files={
                    "dvf_csrf_token": (None, token_input["value"]),
                    "email_login": (None, settings.gipfelbuch_username),
                    "dvForm_mandatory[]": (None, "email_login"),
                    "password_login": (None, settings.gipfelbuch_password),
                    "var2": (None, "1"),
                    "dvForm_subm": (None, "1"),
                },
            )
            login_resp.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("gipfelbuch.ch login request failed: %s", exc)
            return False

        return login_resp.text.strip() == "META OK"

    async def _search(
        self, client: httpx.AsyncClient, criteria: SearchRequest
    ) -> list[RawHike]:
        params: dict[str, str] = {"src_routen_type": "5"}  # 5 = Wanderung (hiking)
        if criteria.canton:
            region = _REGION_BY_CANTON.get(criteria.canton)
            if region:
                params["src_routen_region"] = region
        for lo, hi, bucket in _DURATION_BUCKETS:
            if lo <= criteria.hike_length_h <= hi:
                params["src_dauer"] = bucket
                break

        try:
            resp = await client.get(f"{BASE_URL}/routen/uebersicht", params=params)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("gipfelbuch.ch search request failed (%s): %s", params, exc)
            return []

        try:
            return self._parse_listing(resp.text)
        except Exception:
            logger.exception("Failed to parse gipfelbuch.ch listing")
            return []

    @staticmethod
    def _parse_listing(html: str) -> list[RawHike]:
        # "html.parser" (stdlib), not "lxml": the site's article markup is
        # malformed (unclosed tags), which lxml's recovery mode mis-nests —
        # every article after the first ends up containing all *subsequent*
        # articles' `.bottominfo` stats too, so `article.select(...)` finds
        # far more than 3 stat elements per article and always returns the
        # same values. html.parser's more lenient tree-building handles this
        # correctly (verified: exactly 3 stat elements per article).
        soup = BeautifulSoup(html, "html.parser")
        results: list[RawHike] = []
        for article in soup.find_all("article", class_="list-item")[:_MAX_CANDIDATES]:
            link = article.find("a", href=True)
            title = article.find("h2")
            if not link or not title:
                continue

            url = link["href"]
            if not url.startswith("http"):
                url = BASE_URL + url

            region_el = article.select_one(".topinfo .right")
            canton = region_el.get_text(strip=True) if region_el else None

            # Each listing card has a structured stats block (icon + <p>
            # value, labeled via a self-describing data-tooltip attribute
            # like "Schwierigkeit: T 4" / "Zeitbedarf: 7.0h" /
            # "Höhenmeter: 1470m") — far more reliable than pattern-matching
            # the huge free-text route description, which is what this used
            # to do. "Höhenmeter" is a single figure (not separate ascent/
            # descent), assumed here to be total ascent — mapped to
            # elevation_gain_m only, elevation_loss_m left unset.
            difficulty = duration_h = elevation_gain_m = None
            for stat in article.select(".bottominfo i[data-tooltip]"):
                label, _, value = stat["data-tooltip"].partition(":")
                label, value = label.strip(), value.strip()
                if label == "Schwierigkeit":
                    tgrade_match = _TGRADE_RE.match(value)
                    if tgrade_match:
                        difficulty = f"T{tgrade_match.group(1)}{tgrade_match.group(2)}"
                elif label == "Zeitbedarf":
                    hours_match = _HOURS_RE.match(value)
                    if hours_match:
                        duration_h = float(hours_match.group(1))
                elif label == "Höhenmeter":
                    meters_match = _METERS_RE.match(value)
                    if meters_match:
                        elevation_gain_m = float(meters_match.group(1))

            article_text = article.get_text(" ", strip=True)
            results.append(
                RawHike(
                    name=title.get_text(strip=True),
                    source_name="gipfelbuch.ch",
                    source_url=url,
                    canton=canton,
                    difficulty=difficulty,
                    length_h=duration_h,
                    elevation_gain_m=elevation_gain_m,
                    raw_text=article_text,
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
            logger.warning(
                "Could not persist gipfelbuch.ch session cookies to %s", _SESSION_FILE
            )
