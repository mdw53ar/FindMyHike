import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"


class GeocodingError(Exception):
    """Raised when an address can't be resolved to coordinates."""


class LatLng(tuple):
    def __new__(cls, lat: float, lng: float):
        return super().__new__(cls, (lat, lng))

    @property
    def lat(self) -> float:
        return self[0]

    @property
    def lng(self) -> float:
        return self[1]


async def geocode_address(address: str) -> LatLng:
    if not settings.google_maps_api_key:
        raise GeocodingError(
            "Google Maps API key is not configured (GOOGLE_MAPS_API_KEY). "
            "Set it in backend/.env to enable geocoding."
        )

    async with httpx.AsyncClient(timeout=10) as client:
        try:
            resp = await client.get(
                GEOCODE_URL,
                params={"address": address, "key": settings.google_maps_api_key},
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("Geocoding request failed for %r: %s", address, exc)
            raise GeocodingError(f"Could not reach Google Geocoding API: {exc}") from exc

    data = resp.json()
    status = data.get("status")
    if status != "OK" or not data.get("results"):
        raise GeocodingError(
            f"Could not geocode address {address!r} (Google status: {status})"
        )

    location = data["results"][0]["geometry"]["location"]
    return LatLng(location["lat"], location["lng"])
