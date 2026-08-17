"""Fallback source for "other" hike-report sites (§4.2 step 4). §6 explicitly
notes no general web search API is assumed, and sourcing from arbitrary
"other" sites requires either a search API (e.g. a SERP API key) or a
predefined per-site scraper — neither exists yet. This is a documented no-op
rather than something faked; plug a real implementation in here once a
search API key or a specific target site is chosen.
"""

import logging

from app.models import SearchRequest
from app.sources.base import HikeSource, RawHike

logger = logging.getLogger(__name__)


class OtherFallbackSource(HikeSource):
    name = "other"

    async def discover(self, criteria: SearchRequest) -> list[RawHike]:
        logger.info(
            "Fallback 'other sources' sourcing not implemented: no general "
            "web search API is configured (see app/sources/other_fallback.py)."
        )
        return []
