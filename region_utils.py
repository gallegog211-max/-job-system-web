"""
region_utils.py
----------------
Splits an already skill-ranked list of listings into two groups:

    1. "Philippines" listings (local) -- shown first, and re-ordered so
       listings closer to the applicant's own stated address get a small
       upward nudge on top of their existing AI/TF-IDF match_score.
    2. "International" listings -- shown after, sorted by match_score only.

This keeps the AI matching (Gemini or TF-IDF) focused purely on skill
fit, and applies the location-based grouping as a separate, transparent
step on top of it.

Proximity is computed using a real Philippine city/province/region
hierarchy (ph_locations.py) rather than naive word overlap, so:

  - "Iloilo City" and "Quezon City" no longer share a false bonus just
    because both contain the generic word "City".
  - "Pasig" and "Quezon City" correctly get a partial bonus for being
    in the same region (Metro Manila) even though they share no words
    at all.
  - Free text that isn't a recognized Philippine place -- gibberish,
    "Remote", a foreign city, or a blank field -- always yields a bonus
    of 0.0 instead of accidentally matching on unrelated words.
"""

from ph_locations import PH_LOCATIONS, match_location

# Recognized Philippine keywords used to confirm a listing is local
# even if the word "Philippines" itself isn't written out. Derived from
# the shared location table so this list can't drift out of sync with
# the one used for proximity matching.
PH_KEYWORDS = ["philippines"] + list(PH_LOCATIONS.keys())

# Proximity bonus tiers. Small and capped so they only ever break ties
# between listings that are already a similarly good skill fit -- never
# large enough to override a real difference in match_score.
BONUS_SAME_CITY = 2.0
BONUS_SAME_PROVINCE = 1.2
BONUS_SAME_REGION = 0.6


def is_international(location: str) -> bool:
    """
    Returns True if a listing's location text marks it as an
    international (outside the Philippines) posting.
    """
    loc = (location or "").lower()

    if "international" in loc:
        return True
    if any(keyword in loc for keyword in PH_KEYWORDS):
        return False
    # Plain "Remote" with no country mentioned is treated as a
    # Philippines-based remote listing by default.
    if loc.strip() in ("", "remote"):
        return False
    return False


def location_proximity_bonus(listing_location: str, applicant_location: str) -> float:
    """
    Tiered heuristic bonus used only to break ties among local
    (Philippines) listings when the applicant provides their own
    address. Never large enough to override a real difference in
    match_score -- it only nudges listings that are already a similarly
    good skill fit.

    Tiers:
        same city/municipality  -> +2.0
        same province           -> +1.2
        same region              -> +0.6
        anything else            -> 0.0

    If either side isn't a recognized Philippine place -- e.g. the
    applicant typed gibberish, left it blank, or typed "Remote" (not an
    actual address) -- the bonus is always 0.0 rather than risking a
    coincidental word match.
    """
    if not applicant_location or not listing_location:
        return 0.0

    applicant_place = match_location(applicant_location)
    listing_place = match_location(listing_location)

    if not applicant_place or not listing_place:
        return 0.0

    if applicant_place["city"] == listing_place["city"]:
        return BONUS_SAME_CITY
    if applicant_place["province"] == listing_place["province"]:
        return BONUS_SAME_PROVINCE
    if applicant_place["region"] == listing_place["region"]:
        return BONUS_SAME_REGION

    return 0.0


def split_and_rank_by_region(ranked_listings: list[dict], applicant_location: str = "") -> tuple[list[dict], list[dict]]:
    """
    Takes a list of listings that already have a "match_score" (from
    either the Gemini engine or the TF-IDF fallback) and splits them
    into (philippines_matches, international_matches).

    Philippines matches are re-sorted using match_score plus a small
    tiered proximity bonus based on the applicant's stated address.
    International matches are sorted by match_score alone.
    """
    philippines_matches = []
    international_matches = []

    for listing in ranked_listings:
        if is_international(listing.get("location", "")):
            international_matches.append(dict(listing))
        else:
            philippines_matches.append(dict(listing))

    for listing in philippines_matches:
        bonus = location_proximity_bonus(listing.get("location", ""), applicant_location)
        listing["location_bonus"] = bonus
        listing["display_score"] = round(listing.get("match_score", 0) + bonus, 1)

    for listing in international_matches:
        listing["location_bonus"] = 0.0
        listing["display_score"] = listing.get("match_score", 0)

    philippines_matches.sort(key=lambda x: x["display_score"], reverse=True)
    international_matches.sort(key=lambda x: x["display_score"], reverse=True)

    return philippines_matches, international_matches