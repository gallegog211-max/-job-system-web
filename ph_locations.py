"""
ph_locations.py
----------------
Single source of truth for recognized Philippine cities/municipalities,
their province, and their region. Shared by:

  - region_utils.py    -> tiered proximity bonus (city > province > region)
                           and Philippines-vs-international classification
  - resume_parser.py   -> detecting an applicant's address from resume text

Keeping one table instead of separate keyword lists in each file avoids
the two going out of sync (e.g. one file recognizing "Quezon City" as
Philippine and the other not).
"""

PH_LOCATIONS = {
    # Metro Manila / NCR
    "quezon city": {"province": "metro manila", "region": "ncr"},
    "manila": {"province": "metro manila", "region": "ncr"},
    "makati": {"province": "metro manila", "region": "ncr"},
    "pasig": {"province": "metro manila", "region": "ncr"},
    "taguig": {"province": "metro manila", "region": "ncr"},
    "caloocan": {"province": "metro manila", "region": "ncr"},
    "mandaluyong": {"province": "metro manila", "region": "ncr"},
    "san juan": {"province": "metro manila", "region": "ncr"},
    "pasay": {"province": "metro manila", "region": "ncr"},
    "marikina": {"province": "metro manila", "region": "ncr"},
    "muntinlupa": {"province": "metro manila", "region": "ncr"},
    "valenzuela": {"province": "metro manila", "region": "ncr"},
    "malabon": {"province": "metro manila", "region": "ncr"},
    "las pinas": {"province": "metro manila", "region": "ncr"},
    "paranaque": {"province": "metro manila", "region": "ncr"},
    # Western Visayas
    "iloilo city": {"province": "iloilo", "region": "western visayas"},
    "janiuay": {"province": "iloilo", "region": "western visayas"},
    "bacolod": {"province": "negros occidental", "region": "western visayas"},
    "boracay": {"province": "aklan", "region": "western visayas"},
    # Central Visayas
    "cebu city": {"province": "cebu", "region": "central visayas"},
    "cebu": {"province": "cebu", "region": "central visayas"},
    # Davao Region / Mindanao
    "davao city": {"province": "davao del sur", "region": "davao region"},
    "davao": {"province": "davao del sur", "region": "davao region"},
    # Cordillera
    "baguio": {"province": "benguet", "region": "cordillera administrative region"},
    # CALABARZON
    "antipolo": {"province": "rizal", "region": "calabarzon"},
    "cavite": {"province": "cavite", "region": "calabarzon"},
    "laguna": {"province": "laguna", "region": "calabarzon"},
    # Central Luzon
    "bulacan": {"province": "bulacan", "region": "central luzon"},
    "pampanga": {"province": "pampanga", "region": "central luzon"},
}


def match_location(text: str):
    """
    Finds the most specific known Philippine place mentioned in free
    text and returns {"city": <key>, "province": ..., "region": ...},
    or None if nothing recognizable is found.

    Longer/more specific entries (e.g. "quezon city") are checked before
    shorter, broader ones (e.g. "cebu") so "Caloocan, Quezon City"
    resolves to Quezon City rather than stopping at a partial word.
    """
    if not text:
        return None

    text_lower = text.lower()

    for key in sorted(PH_LOCATIONS.keys(), key=len, reverse=True):
        if key in text_lower:
            info = PH_LOCATIONS[key]
            return {"city": key, "province": info["province"], "region": info["region"]}

    return None
