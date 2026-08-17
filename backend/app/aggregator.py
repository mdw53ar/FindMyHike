import logging

from app.models import SearchRequest
from app.sources.base import HikeSource, RawHike
from app.sources.gipfelbuch import GipfelbuchSource
from app.sources.hikr import HikrSource
from app.sources.other_fallback import OtherFallbackSource
from app.sources.sac import SacSource

logger = logging.getLogger(__name__)

# Priority order per §4.2: stop at the first source that yields a usable
# result for a given hike (by name). SAC.ch / gipfelbuch.ch are currently
# stubs (see their modules) and will return [] until calibrated with a real
# account — that's surfaced truthfully rather than papered over.
_SOURCES: list[HikeSource] = [
    SacSource(),
    HikrSource(),
    GipfelbuchSource(),
    OtherFallbackSource(),
]


async def gather_candidates(criteria: SearchRequest) -> tuple[list[RawHike], list[str]]:
    """Runs each source in priority order and merges results, keeping only
    the first (highest-priority) source's version of a given hike name —
    "exactly one link per hike, the first source in priority order" (§4.2).
    Per-source failures are caught inside each source's `discover()`, so one
    broken source never aborts the whole search.
    """
    seen_names: set[str] = set()
    merged: list[RawHike] = []
    warnings: list[str] = []

    for source in _SOURCES:
        try:
            candidates = await source.discover(criteria)
        except Exception:
            logger.exception("Unexpected error from source %s", source.name)
            warnings.append(f"{source.name}: failed unexpectedly, skipped")
            continue

        for hike in candidates:
            key = hike.name.strip().lower()
            if key in seen_names:
                continue
            seen_names.add(key)
            merged.append(hike)

    if not merged:
        warnings.append(
            "No hike candidates found from any source. hikr.org may be "
            "blocking automated requests, or SAC.ch/gipfelbuch.ch are not "
            "yet calibrated (see app/sources/sac.py, gipfelbuch.py)."
        )

    return merged, warnings
