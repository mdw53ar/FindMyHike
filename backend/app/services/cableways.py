import json
from pathlib import Path

from app.models import CablewayAccess

_DATA_PATH = Path(__file__).with_name("cableways.json")
_DATA: dict[str, dict] = json.loads(_DATA_PATH.read_text(encoding="utf-8"))

# Keywords (DE/FR/EN) that indicate a cable car / gondola / chairlift is
# involved in reaching the trailhead. This is a heuristic over free-text hike
# descriptions, not a geospatial analysis — false negatives are possible.
_CABLEWAY_KEYWORDS = [
    "seilbahn", "gondelbahn", "gondel", "sesselbahn", "luftseilbahn",
    "standseilbahn", "bergbahn", "zahnradbahn", "funicular", "funiculaire",
    "téléphérique", "telepherique", "télécabine", "telecabine", "cable car",
    "gondola", "chairlift", "cabriolet",
]


def detect_cableway_mention(text: str) -> bool:
    lowered = text.lower()
    return any(keyword in lowered for keyword in _CABLEWAY_KEYWORDS)


def lookup(name_hint: str | None) -> CablewayAccess:
    """Looks up a mentioned cableway by (fuzzy, substring) name match against
    the curated list. Returns an access record marked "required" either way;
    when the specific lift isn't in the curated list, hours/selbstbedienung
    are reported as unknown rather than guessed — the spec explicitly warns
    that self-service access must be verified per lift, not assumed."""
    if name_hint:
        lowered = name_hint.lower()
        for key, entry in _DATA.items():
            if key in lowered or entry["name"].lower() in lowered:
                return CablewayAccess(
                    required=True,
                    name=entry["name"],
                    opening_hours=entry["opening_hours"],
                    season=entry["season"],
                    selbstbedienung=entry["selbstbedienung"],
                    note=entry["note"],
                )

    return CablewayAccess(
        required=True,
        name=name_hint,
        opening_hours=None,
        season=None,
        selbstbedienung=None,
        note=(
            "Cable car/lift mentioned but not in the curated lookup table — "
            "opening hours and self-service (Selbstbedienung) availability "
            "must be verified directly with the operator."
        ),
    )
