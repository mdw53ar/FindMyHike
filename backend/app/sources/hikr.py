"""hikr.org scraper — the one source that requires no login (§6 confirms
hikr.org as the hike-report source), so this is a real implementation, not a
stub. It is deliberately built around a few durable, structural signals
rather than guessed CSS class names, since hikr.org's exact markup couldn't
be inspected live while building this (the site returned HTTP 403 to a
sandboxed research fetch — likely bot protection). It still needs a live
calibration pass by whoever runs this with real network access:
  - confirm/adjust `_SEARCH_URL` and its query params against the real
    /filter.php form,
  - confirm the `/postNNNNN.html` individual-report URL pattern still holds,
  - tighten the regexes below against real page text if extraction misses.
Every network/parse step is guarded so a layout change degrades to "skip
that item," never a crash (§5).
"""

import logging
import re

import httpx
from bs4 import BeautifulSoup

from app.models import SearchRequest
from app.sources.base import HikeSource, RawHike

logger = logging.getLogger(__name__)

BASE_URL = "https://www.hikr.org"
_SEARCH_URL = f"{BASE_URL}/filter.php"
_REPORT_LINK_RE = re.compile(r"^/post(\d+)\.html$")
_MAX_CANDIDATES = 25

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "de-CH,de;q=0.9,en;q=0.8,fr;q=0.7",
}

# T-grade e.g. "T4" or "SAC T4", optionally with +/-.
_TGRADE_RE = re.compile(r"\bT[2-6][+-]?\b")
# Duration like "5:30 h", "5.5 h", "5h30", "5 Std".
_DURATION_RE = re.compile(
    r"(\d{1,2})[:.](\d{2})\s*h|(\d{1,2}(?:[.,]\d)?)\s*(?:h\b|std|hours)", re.IGNORECASE
)
_ASCENT_RE = re.compile(r"(?:aufstieg|ascent|mont[ée]e)\D{0,10}(\d{2,5})\s*m", re.IGNORECASE)
_DESCENT_RE = re.compile(r"(?:abstieg|descent|descente)\D{0,10}(\d{2,5})\s*m", re.IGNORECASE)
_CIRCULAR_RE = re.compile(r"rundtour|rundweg|circular|tour circulaire|boucle", re.IGNORECASE)
_UIAA_RE = re.compile(r"\bUIAA\s*([IVX]{1,4}[+-]?)\b", re.IGNORECASE)
_CLIMB_KEYWORDS_RE = re.compile(
    r"kletterei|kletterstelle|klettern|scrambl|escalade", re.IGNORECASE
)


class HikrSource(HikeSource):
    name = "hikr.org"

    async def discover(self, criteria: SearchRequest) -> list[RawHike]:
        try:
            async with httpx.AsyncClient(
                timeout=15, headers=_HEADERS, follow_redirects=True
            ) as client:
                report_urls = await self._find_candidate_reports(client, criteria)
                results: list[RawHike] = []
                for url in report_urls[:_MAX_CANDIDATES]:
                    hike = await self._parse_report(client, url)
                    if hike:
                        results.append(hike)
                self._annotate_report_counts(results)
                return results
        except Exception:
            logger.exception("hikr.org discovery failed; returning no candidates")
            return []

    async def _find_candidate_reports(
        self, client: httpx.AsyncClient, criteria: SearchRequest
    ) -> list[str]:
        params = {"activity": "hiking"}
        if criteria.canton:
            params["region"] = criteria.canton
        if criteria.difficulties:
            params["difficulty"] = ",".join(d.value for d in criteria.difficulties)

        try:
            resp = await client.get(_SEARCH_URL, params=params)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("hikr.org search request failed (%s): %s", params, exc)
            return []

        soup = BeautifulSoup(resp.text, "lxml")
        urls: list[str] = []
        seen: set[str] = set()
        for a in soup.find_all("a", href=True):
            match = _REPORT_LINK_RE.match(a["href"])
            if match and a["href"] not in seen:
                seen.add(a["href"])
                urls.append(BASE_URL + a["href"])

        if not urls:
            logger.info(
                "No hikr.org report links found for %s — site may be blocking "
                "automated requests or the search markup has changed; "
                "needs a live calibration pass.",
                params,
            )
        return urls

    async def _parse_report(self, client: httpx.AsyncClient, url: str) -> RawHike | None:
        try:
            resp = await client.get(url)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            logger.info("Skipping hikr.org report %s (%s)", url, exc)
            return None

        try:
            return parse_report_html(resp.text, url)
        except Exception:
            logger.exception("Failed to parse hikr.org report %s", url)
            return None

    @staticmethod
    def _annotate_report_counts(hikes: list[RawHike]) -> None:
        """Freshness signal per §4.2: count how many reports were found for
        the same route name in this discovery pass, so near-duplicate/rarely
        reported routes can be flagged as potentially outdated."""
        counts: dict[str, int] = {}
        for hike in hikes:
            key = hike.name.strip().lower()
            counts[key] = counts.get(key, 0) + 1
        for hike in hikes:
            hike.report_count = counts[hike.name.strip().lower()]


def parse_report_html(html: str, url: str) -> RawHike | None:
    """Pure parsing function (no network), split out from `HikrSource` so it
    can be unit-tested against a static HTML fixture."""
    soup = BeautifulSoup(html, "lxml")
    title_tag = soup.find("h1")
    name = title_tag.get_text(strip=True) if title_tag else url
    text = soup.get_text(" ", strip=True)

    gpx_url = None
    for a in soup.find_all("a", href=True):
        if a["href"].lower().endswith(".gpx"):
            gpx_url = a["href"]
            if not gpx_url.startswith("http"):
                gpx_url = BASE_URL + gpx_url
            break

    tgrade_match = _TGRADE_RE.search(text)
    duration_h = _parse_duration(text)
    ascent_match = _ASCENT_RE.search(text)
    descent_match = _DESCENT_RE.search(text)
    uiaa_match = _UIAA_RE.search(text)
    climbing_required = bool(uiaa_match or _CLIMB_KEYWORDS_RE.search(text))

    return RawHike(
        name=name,
        source_name="hikr.org",
        source_url=url,
        difficulty=tgrade_match.group(0).upper() if tgrade_match else None,
        length_h=duration_h,
        elevation_gain_m=float(ascent_match.group(1)) if ascent_match else None,
        elevation_loss_m=float(descent_match.group(1)) if descent_match else None,
        circular=bool(_CIRCULAR_RE.search(text)) or None,
        climbing_required=climbing_required,
        climbing_grade=uiaa_match.group(1) if uiaa_match else None,
        gpx_url=gpx_url,
        raw_text=text,
    )


def _parse_duration(text: str) -> float | None:
    match = _DURATION_RE.search(text)
    if not match:
        return None
    if match.group(1) and match.group(2):
        return int(match.group(1)) + int(match.group(2)) / 60
    if match.group(3):
        return float(match.group(3).replace(",", "."))
    return None
