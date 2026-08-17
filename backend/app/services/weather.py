import logging
from datetime import date, timedelta

import httpx

from app.models import WeatherDay

logger = logging.getLogger(__name__)

# Open-Meteo's MeteoSwiss-model passthrough: real MeteoSwiss ICON forecast
# data, JSON, no API key required. See §4.5 ("use public open data").
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

# No date field exists in the search form, so we show a short forecast
# (tomorrow + day after) for the trailhead, labeled by date, and let the user
# match it to whichever day they actually go.
_FORECAST_DAYS_AHEAD = 2

_WEATHER_CODE_SUMMARY = {
    0: "Clear sky", 1: "Mostly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Rime fog",
    51: "Light drizzle", 53: "Drizzle", 55: "Dense drizzle",
    61: "Light rain", 63: "Rain", 65: "Heavy rain",
    66: "Freezing rain", 67: "Heavy freezing rain",
    71: "Light snow", 73: "Snow", 75: "Heavy snow", 77: "Snow grains",
    80: "Light showers", 81: "Showers", 82: "Violent showers",
    85: "Light snow showers", 86: "Heavy snow showers",
    95: "Thunderstorm", 96: "Thunderstorm with hail", 99: "Severe thunderstorm with hail",
}


async def forecast(lat: float, lng: float) -> list[WeatherDay]:
    """Returns [] (not a crash) on any failure, per §5's graceful-degradation
    requirement — a missing forecast shouldn't drop an otherwise-good hike."""
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            resp = await client.get(
                FORECAST_URL,
                params={
                    "latitude": lat,
                    "longitude": lng,
                    "daily": "weathercode,temperature_2m_max,temperature_2m_min,"
                    "precipitation_probability_max",
                    "models": "meteoswiss_icon_seamless",
                    "timezone": "Europe/Zurich",
                    "forecast_days": _FORECAST_DAYS_AHEAD + 1,
                },
            )
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("Weather request failed for (%s, %s): %s", lat, lng, exc)
            return []

    daily = data.get("daily")
    if not daily or "time" not in daily:
        return []

    today = date.today()
    days: list[WeatherDay] = []
    for i, day_str in enumerate(daily["time"]):
        try:
            day = date.fromisoformat(day_str)
        except ValueError:
            continue
        if day <= today:
            continue
        code = daily.get("weathercode", [None] * len(daily["time"]))[i]
        days.append(
            WeatherDay(
                date=day_str,
                summary=_WEATHER_CODE_SUMMARY.get(code, "Unknown"),
                temp_max_c=_safe_get(daily, "temperature_2m_max", i),
                temp_min_c=_safe_get(daily, "temperature_2m_min", i),
                precipitation_probability_pct=_safe_get(
                    daily, "precipitation_probability_max", i
                ),
            )
        )
        if len(days) >= _FORECAST_DAYS_AHEAD:
            break

    return days


def _safe_get(daily: dict, key: str, index: int) -> float | None:
    values = daily.get(key)
    if not values or index >= len(values):
        return None
    return values[index]
