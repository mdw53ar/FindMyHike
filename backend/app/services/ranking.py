from app.models import HikeResult, SearchRequest

# Hike duration tolerance per §4.3 ("define a tolerance, e.g. ±20%").
DURATION_TOLERANCE = 0.20

# Ranking weights (documented, tunable v1 rule per §4.6):
#   duration closeness matters most, then travel-time closeness, then a
#   freshness bonus (more reports found ~= more likely still accurate/open).
_W_DURATION = 0.5
_W_TRAVEL = 0.3
_W_FRESHNESS = 0.2
_MAX_FRESHNESS_REPORTS = 5

TOP_N = 20


def passes_hard_filters(hike: HikeResult, criteria: SearchRequest) -> bool:
    # Unknown difficulty/duration are treated like unknown travel time /
    # ungeocodable trailhead elsewhere in the pipeline: excluded rather than
    # silently passed through, since the constraint genuinely can't be
    # verified. For difficulty specifically, "unknown" here usually means
    # the source's own scale isn't the SAC T-grade scale at all (e.g. a
    # UIAA/ZS/WS-graded alpine route) rather than a parsing gap — excluding
    # it is the correct call, not just a conservative one.
    if hike.difficulty is None or hike.difficulty not in {d.value for d in criteria.difficulties}:
        return False

    if hike.length_h is None:
        return False
    lower = criteria.hike_length_h * (1 - DURATION_TOLERANCE)
    upper = criteria.hike_length_h * (1 + DURATION_TOLERANCE)
    if not (lower <= hike.length_h <= upper):
        return False

    if criteria.circular is not None and hike.circular is not None:
        if hike.circular != criteria.circular:
            return False

    if criteria.canton and hike.canton and hike.canton.lower() != criteria.canton.lower():
        return False

    if hike.travel_time_h is None or hike.travel_time_h > criteria.max_travel_time_h:
        return False

    return True


def score(hike: HikeResult, criteria: SearchRequest) -> float:
    duration_penalty = 0.0
    if hike.length_h is not None and criteria.hike_length_h:
        duration_penalty = abs(hike.length_h - criteria.hike_length_h) / criteria.hike_length_h

    travel_penalty = 0.0
    if hike.travel_time_h is not None and criteria.max_travel_time_h:
        travel_penalty = hike.travel_time_h / criteria.max_travel_time_h

    freshness_bonus = 0.0
    if hike.report_count is not None:
        freshness_bonus = min(hike.report_count, _MAX_FRESHNESS_REPORTS) / _MAX_FRESHNESS_REPORTS
    elif hike.source_name in ("SAC.ch", "gipfelbuch.ch"):
        # Authenticated official sources are treated as maximally fresh —
        # they don't have a "report count" concept the way hikr.org does.
        freshness_bonus = 1.0

    return _W_DURATION * duration_penalty + _W_TRAVEL * travel_penalty - _W_FRESHNESS * freshness_bonus


def rank(hikes: list[HikeResult], criteria: SearchRequest) -> list[HikeResult]:
    survivors = [h for h in hikes if passes_hard_filters(h, criteria)]
    for hike in survivors:
        hike.score = score(hike, criteria)
    survivors.sort(key=lambda h: h.score)
    return survivors[:TOP_N]
