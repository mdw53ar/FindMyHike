import logging
from dataclasses import dataclass

import httpx

from app.config import settings
from app.models import TransportMode

logger = logging.getLogger(__name__)

DIRECTIONS_URL = "https://maps.googleapis.com/maps/api/directions/json"

_GOOGLE_MODE = {
    TransportMode.car: "driving",
    TransportMode.public_transport: "transit",
}


@dataclass
class TravelResult:
    duration_h: float
    reachable_directly: bool


async def travel_time(
    origin: tuple[float, float],
    destination: tuple[float, float],
    mode: TransportMode,
) -> TravelResult | None:
    """Returns None (rather than raising) on any failure so callers can
    gracefully exclude a hike instead of crashing the whole search, per the
    spec's "handle source failures gracefully" requirement."""
    if not settings.google_maps_api_key:
        logger.info("Skipping travel-time lookup: GOOGLE_MAPS_API_KEY not set")
        return None

    async with httpx.AsyncClient(timeout=10) as client:
        try:
            resp = await client.get(
                DIRECTIONS_URL,
                params={
                    "origin": f"{origin[0]},{origin[1]}",
                    "destination": f"{destination[0]},{destination[1]}",
                    "mode": _GOOGLE_MODE[mode],
                    "key": settings.google_maps_api_key,
                },
            )
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("Directions request failed: %s", exc)
            return None

    if data.get("status") != "OK" or not data.get("routes"):
        logger.info("No route found (%s) for mode=%s", data.get("status"), mode)
        return TravelResult(duration_h=float("inf"), reachable_directly=False)

    leg = data["routes"][0]["legs"][0]
    duration_h = leg["duration"]["value"] / 3600
    return TravelResult(duration_h=duration_h, reachable_directly=True)
