import hashlib
import json

from cachetools import TTLCache

from app.config import settings
from app.models import SearchRequest, SearchResponse

_cache: TTLCache = TTLCache(maxsize=256, ttl=settings.cache_ttl_seconds)


def _key_for(request: SearchRequest) -> str:
    normalized = json.dumps(
        request.model_dump(mode="json"), sort_keys=True, default=str
    )
    return hashlib.sha256(normalized.encode()).hexdigest()


def get(request: SearchRequest) -> SearchResponse | None:
    return _cache.get(_key_for(request))


def set(request: SearchRequest, response: SearchResponse) -> None:
    _cache[_key_for(request)] = response
