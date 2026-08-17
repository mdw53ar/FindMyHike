from app.models import Difficulty, HikeResult, SearchRequest, TransportMode
from app.services.ranking import passes_hard_filters, rank, score


def _request(**overrides) -> SearchRequest:
    defaults = dict(
        start_address="Bern, Switzerland",
        mode=TransportMode.car,
        max_travel_time_h=2.0,
        hike_length_h=5.0,
        circular=None,
        difficulties=[Difficulty.T2, Difficulty.T3],
        canton=None,
    )
    defaults.update(overrides)
    return SearchRequest(**defaults)


def _hike(**overrides) -> HikeResult:
    defaults = dict(
        name="Test Hike",
        canton="Bern",
        difficulty="T3",
        length_h=5.0,
        circular=True,
        travel_mode=TransportMode.car,
        trailhead_access="reachable by car",
        source_name="hikr.org",
        source_url="https://www.hikr.org/post1.html",
        travel_time_h=1.0,
    )
    defaults.update(overrides)
    return HikeResult(**defaults)


def test_passes_hard_filters_happy_path():
    assert passes_hard_filters(_hike(), _request())


def test_fails_on_difficulty_mismatch():
    assert not passes_hard_filters(_hike(difficulty="T5"), _request())


def test_fails_when_difficulty_unknown():
    # Unknown difficulty (or a non-T-grade scale, e.g. UIAA/ZS/WS) can't be
    # verified against the requested T-grades, so it's excluded rather than
    # silently passed through.
    assert not passes_hard_filters(_hike(difficulty=None), _request())


def test_fails_on_duration_outside_tolerance():
    # requested 5h, tolerance ±20% -> [4.0, 6.0]; 6.5h is outside.
    assert not passes_hard_filters(_hike(length_h=6.5), _request())


def test_passes_on_duration_within_tolerance():
    assert passes_hard_filters(_hike(length_h=5.9), _request())


def test_fails_when_duration_unknown():
    # Unknown duration can't be verified against the requested length, so
    # it's excluded rather than silently passed through (e.g. SAC.ch hikes
    # currently have no duration data — see app/sources/sac.py).
    assert not passes_hard_filters(_hike(length_h=None), _request())


def test_fails_on_circular_mismatch():
    assert not passes_hard_filters(_hike(circular=False), _request(circular=True))


def test_fails_when_travel_time_unknown():
    assert not passes_hard_filters(_hike(travel_time_h=None), _request())


def test_fails_when_travel_time_exceeds_budget():
    assert not passes_hard_filters(_hike(travel_time_h=3.0), _request(max_travel_time_h=2.0))


def test_fails_on_canton_mismatch():
    assert not passes_hard_filters(_hike(canton="Valais"), _request(canton="Bern"))


def test_score_prefers_closer_duration_and_travel_time():
    close = _hike(length_h=5.0, travel_time_h=0.5)
    far = _hike(length_h=5.0, travel_time_h=1.9)
    request = _request()
    assert score(close, request) < score(far, request)


def test_score_rewards_freshness():
    fresh = _hike(report_count=5)
    stale = _hike(report_count=0)
    request = _request()
    assert score(fresh, request) < score(stale, request)


def test_rank_excludes_non_matching_and_sorts_by_score():
    good = _hike(name="Good", travel_time_h=0.5)
    bad_difficulty = _hike(name="Bad", difficulty="T6")
    unreachable = _hike(name="Far", travel_time_h=None)
    request = _request()

    ranked = rank([good, bad_difficulty, unreachable], request)

    assert [h.name for h in ranked] == ["Good"]


def test_rank_caps_results_at_top_n():
    hikes = [_hike(name=f"Hike {i}", travel_time_h=0.1 * i) for i in range(30)]
    ranked = rank(hikes, _request(max_travel_time_h=5.0))
    assert len(ranked) == 20
