from enum import Enum

from pydantic import BaseModel, Field


class TransportMode(str, Enum):
    car = "car"
    public_transport = "public_transport"


class Difficulty(str, Enum):
    T2 = "T2"
    T3 = "T3"
    T4 = "T4"
    T5 = "T5"
    T6 = "T6"


CANTONS: list[str] = [
    "Aargau", "Appenzell Ausserrhoden", "Appenzell Innerrhoden", "Basel-Landschaft",
    "Basel-Stadt", "Bern", "Fribourg", "Geneva", "Glarus", "Graubünden", "Jura",
    "Lucerne", "Neuchâtel", "Nidwalden", "Obwalden", "Schaffhausen", "Schwyz",
    "Solothurn", "St. Gallen", "Thurgau", "Ticino", "Uri", "Valais", "Vaud",
    "Zug", "Zürich",
]


class SearchRequest(BaseModel):
    start_address: str = Field(min_length=3)
    mode: TransportMode
    max_travel_time_h: float = Field(gt=0, le=12)
    hike_length_h: float = Field(gt=0, le=24)
    circular: bool | None = None
    difficulties: list[Difficulty] = Field(min_length=1)
    canton: str | None = None


class WeatherDay(BaseModel):
    date: str
    summary: str
    temp_min_c: float | None = None
    temp_max_c: float | None = None
    precipitation_probability_pct: float | None = None


class CablewayAccess(BaseModel):
    required: bool
    name: str | None = None
    opening_hours: str | None = None
    season: str | None = None
    selbstbedienung: bool | None = None
    note: str | None = None


class HikeResult(BaseModel):
    name: str
    canton: str | None = None
    difficulty: str | None = None
    length_h: float | None = None
    elevation_gain_m: float | None = None
    elevation_loss_m: float | None = None
    circular: bool | None = None
    climbing_required: bool = False
    climbing_grade: str | None = None
    travel_time_h: float | None = None
    travel_mode: TransportMode
    trailhead_access: str
    cableway: CablewayAccess | None = None
    weather: list[WeatherDay] = Field(default_factory=list)
    source_name: str
    source_url: str
    report_count: int | None = None
    gpx_url: str | None = None
    score: float | None = None


class SearchResponse(BaseModel):
    results: list[HikeResult]
    cached: bool = False
    warnings: list[str] = Field(default_factory=list)
