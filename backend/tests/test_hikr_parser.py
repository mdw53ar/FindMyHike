from pathlib import Path

from app.sources.hikr import parse_report_html

FIXTURE = Path(__file__).parent / "fixtures" / "hikr_sample.html"


def _parsed():
    html = FIXTURE.read_text(encoding="utf-8")
    return parse_report_html(html, "https://www.hikr.org/post12345.html")


def test_parses_title():
    assert _parsed().name == "Bluemlisalphütte Rundtour"


def test_parses_difficulty():
    assert _parsed().difficulty == "T4"


def test_parses_duration_hours_minutes():
    assert _parsed().length_h == 6.5


def test_parses_elevation_gain_and_loss():
    hike = _parsed()
    assert hike.elevation_gain_m == 1200.0
    assert hike.elevation_loss_m == 1150.0


def test_parses_circularity():
    assert _parsed().circular is True


def test_parses_climbing_grade():
    hike = _parsed()
    assert hike.climbing_required is True
    assert hike.climbing_grade == "II"


def test_parses_gpx_link():
    assert _parsed().gpx_url == "https://www.hikr.org/tracks/12345.gpx"


def test_source_url_is_preserved():
    assert _parsed().source_url == "https://www.hikr.org/post12345.html"
    assert _parsed().source_name == "hikr.org"


def test_returns_none_on_empty_html_gracefully():
    result = parse_report_html("<html><body></body></html>", "https://www.hikr.org/postX.html")
    assert result is not None
    assert result.name == "https://www.hikr.org/postX.html"
    assert result.difficulty is None
