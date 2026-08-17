import logging
from dataclasses import dataclass

import httpx

from app.config import settings
from app.models import TransportMode

logger = logging.getLogger(__name__)

# The legacy Directions API was retired for new projects on 2025-03-01 and
# replaced by the Routes API — a POST/JSON endpoint, not the old GET one.
# See https://developers.google.com/maps/documentation/routes/migrate-routes
ROUTES_URL = "https://routes.googleapis.com/directions/v2:computeRoutes"

_GOOGLE_TRAVEL_MODE = {
    TransportMode.car: "DRIVE",
    TransportMode.public_transport: "TRANSIT",
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

    travel_mode = _GOOGLE_TRAVEL_MODE[mode]
    body = {
        "origin": {"location": {"latLng": {"latitude": origin[0], "longitude": origin[1]}}},
        "destination": {
            "location": {"latLng": {"latitude": destination[0], "longitude": destination[1]}}
        },
        "travelMode": travel_mode,
    }
    # routingPreference is only valid for DRIVE/TWO_WHEELER, not TRANSIT.
    if travel_mode == "DRIVE":
        body["routingPreference"] = "TRAFFIC_AWARE"

    async with httpx.AsyncClient(timeout=10) as client:
        try:
            resp = await client.post(
                ROUTES_URL,
                json=body,
                headers={
                    "Content-Type": "application/json",
                    "X-Goog-Api-Key": settings.google_maps_api_key,
                    "X-Goog-FieldMask": "routes.duration",
                },
            )
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("Routes API request failed: %s", exc)
            return None

    routes = data.get("routes")
    if not routes:
        logger.info("No route found for mode=%s", mode)
        return TravelResult(duration_h=float("inf"), reachable_directly=False)

    # Duration comes back as a string like "1234s".
    duration_h = int(routes[0]["duration"].rstrip("s")) / 3600
    return TravelResult(duration_h=duration_h, reachable_directly=True)
