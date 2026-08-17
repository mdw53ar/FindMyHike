from app.models import Difficulty, SearchRequest, SearchResponse, TransportMode
from app.services import cache


def _request(address: str) -> SearchRequest:
    return SearchRequest(
        start_address=address,
        mode=TransportMode.car,
        max_travel_time_h=2.0,
        hike_length_h=5.0,
        difficulties=[Difficulty.T3],
    )


def test_cache_miss_returns_none():
    assert cache.get(_request("Nowhere, Switzerland")) is None


def test_cache_hit_returns_stored_response():
    request = _request("Interlaken, Switzerland")
    response = SearchResponse(results=[], warnings=["test"])

    cache.set(request, response)
    hit = cache.get(request)

    assert hit is not None
    assert hit.warnings == ["test"]


def test_cache_key_distinguishes_different_requests():
    cache.set(_request("Zurich, Switzerland"), SearchResponse(results=[]))
    assert cache.get(_request("Geneva, Switzerland")) is None
