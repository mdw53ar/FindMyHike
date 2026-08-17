from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from app.models import SearchRequest


@dataclass
class RawHike:
    """Hike candidate as discovered from a source, before travel-time/weather
    enrichment and constraint filtering."""

    name: str
    source_name: str
    source_url: str
    canton: str | None = None
    difficulty: str | None = None
    length_h: float | None = None
    elevation_gain_m: float | None = None
    elevation_loss_m: float | None = None
    circular: bool | None = None
    climbing_required: bool = False
    climbing_grade: str | None = None
    trailhead_hint: str | None = None
    trailhead_latlng: tuple[float, float] | None = None
    gpx_url: str | None = None
    report_count: int | None = None
    raw_text: str = field(default="", repr=False)


class HikeSource(ABC):
    """A source of candidate hikes (SAC.ch, hikr.org, gipfelbuch.ch, ...).

    Implementations must never raise out of `discover()` — any failure
    (network, layout change, auth) should be logged and result in an empty
    list, so one broken source never fails the whole search (§5)."""

    name: str

    @abstractmethod
    async def discover(self, criteria: SearchRequest) -> list[RawHike]:
        ...
