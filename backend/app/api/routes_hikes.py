import logging

from fastapi import APIRouter

from app.aggregator import gather_candidates
from app.models import CablewayAccess, HikeResult, SearchRequest, SearchResponse
from app.services import cache
from app.services.cableways import detect_cableway_mention, lookup as lookup_cableway
from app.services.geocoding import GeocodingError, geocode_address
from app.services.ranking import rank
from app.services.travel import travel_time
from app.services.weather import forecast
from app.sources.base import RawHike

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/hikes", tags=["hikes"])


@router.post("/search", response_model=SearchResponse)
async def search_hikes(request: SearchRequest) -> SearchResponse:
    cached = cache.get(request)
    if cached is not None:
        cached.cached = True
        return cached

    # Geocoding the start address is best-effort, not required: without a
    # working GOOGLE_MAPS_API_KEY (or a transient failure), origin stays
    # None and hikes are still returned — just without travel time,
    # weather, or trailhead-access info, all of which depend on knowing a
    # location. This mirrors the same "external integration is optional,
    # source data is not" principle already applied to the travel-time cap
    # in services/ranking.py.
    origin: tuple[float, float] | None = None
    warnings: list[str] = []
    try:
        origin = await geocode_address(request.start_address)
    except GeocodingError as exc:
        warnings.append(
            f"Could not determine your location ({exc}); showing hikes without "
            "travel time, weather, or trailhead-access info."
        )
        logger.info("Geocoding origin failed: %s", exc)

    raw_hikes, source_warnings = await gather_candidates(request)
    warnings.extend(source_warnings)

    results: list[HikeResult] = []
    for raw in raw_hikes:
        result = await _enrich(raw, origin, request)
        if result is not None:
            results.append(result)

    ranked = rank(results, request)
    response = SearchResponse(results=ranked, cached=False, warnings=warnings)
    cache.set(request, response)
    return response


async def _enrich(
    raw: RawHike, origin: tuple[float, float] | None, request: SearchRequest
) -> HikeResult | None:
    trailhead = raw.trailhead_latlng
    if trailhead is None and origin is not None:
        geocode_query = raw.trailhead_hint or f"{raw.name}, Switzerland"
        try:
            trailhead = await geocode_address(geocode_query)
        except GeocodingError:
            # Unlike a missing/broken Maps integration overall (handled by
            # `origin is None` below), a working integration that still
            # can't place *this specific* hike is a real data-quality
            # signal — worth excluding, not just degrading.
            logger.info(
                "Skipping %r: could not determine trailhead coordinates", raw.name
            )
            return None

    travel_time_h: float | None = None
    reachable_directly = True
    weather_days: list = []

    if origin is not None and trailhead is not None:
        travel = await travel_time(origin, trailhead, request.mode)
        travel_time_h = travel.duration_h if travel else None
        reachable_directly = travel.reachable_directly if travel else True
        weather_days = await forecast(trailhead[0], trailhead[1])

    cableway: CablewayAccess | None = None
    if not reachable_directly or detect_cableway_mention(raw.raw_text):
        cableway = lookup_cableway(raw.name if not reachable_directly else None)
        trailhead_access = "requires cable car"
    elif origin is None:
        trailhead_access = "unknown (location unavailable)"
    else:
        trailhead_access = f"reachable by {request.mode.value.replace('_', ' ')}"

    return HikeResult(
        name=raw.name,
        canton=raw.canton,
        difficulty=raw.difficulty,
        length_h=raw.length_h,
        elevation_gain_m=raw.elevation_gain_m,
        elevation_loss_m=raw.elevation_loss_m,
        circular=raw.circular,
        climbing_required=raw.climbing_required,
        climbing_grade=raw.climbing_grade,
        travel_time_h=travel_time_h,
        travel_mode=request.mode,
        trailhead_access=trailhead_access,
        cableway=cableway,
        weather=weather_days,
        source_name=raw.source_name,
        source_url=raw.source_url,
        report_count=raw.report_count,
        gpx_url=raw.gpx_url,
    )
