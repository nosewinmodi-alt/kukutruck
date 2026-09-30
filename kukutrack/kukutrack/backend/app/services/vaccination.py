"""Default vaccination programmes (day-of-age, vaccine).

These are common starting templates for Kenyan flocks and MUST be confirmed with a
registered veterinarian for your area, disease pressure and vaccine brand.
"""
from datetime import date, timedelta

_LAYER = [
    (7, "Newcastle + Infectious Bronchitis (Hitchner B1 / H120)"),
    (14, "Gumboro / IBD - 1st dose"),
    (21, "Newcastle - LaSota"),
    (28, "Gumboro / IBD - booster"),
    (42, "Fowl pox (wing-web)"),
    (56, "Newcastle - LaSota booster"),
    (112, "Pre-lay Newcastle + IB (+ EDS if advised)"),
]
TEMPLATES = {
    "layer": _LAYER,
    "kienyeji": _LAYER,
    "broiler": [
        (7, "Newcastle + Infectious Bronchitis (Hitchner B1 / H120)"),
        (14, "Gumboro / IBD"),
        (21, "Newcastle - LaSota"),
    ],
}


def schedule(kind: str, placed_on: date) -> list[tuple[date, str]]:
    return [(placed_on + timedelta(days=d), name) for d, name in TEMPLATES.get(kind, [])]
