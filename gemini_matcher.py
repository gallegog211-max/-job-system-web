import json
import os

from google import genai
from google.genai import types

MODEL_NAME = "gemini-3.1-flash-lite"


class GeminiUnavailableError(Exception):
    """Raised whenever Gemini can't be used, so the caller can fall back."""
    pass


def _get_client() -> genai.Client:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise GeminiUnavailableError(
            "No GEMINI_API_KEY set. Get a free key at "
            "https://aistudio.google.com/apikey and set it as an "
            "environment variable."
        )
    return genai.Client(api_key=api_key)


def gemini_rank_listings(applicant_skills: str, listings: list[dict], applicant_location: str = "") -> list[dict]:
    """
    Asks Gemini to score every listing against the applicant's skills.

    applicant_location is optional free text (e.g. "Janiuay, Iloilo").
    It is passed to Gemini only so the match_reason it writes can
    mention location relevance when useful (e.g. "close to your area").
    It does NOT change the skill-based match_score itself -- grouping
    listings into Philippines vs. international, and nudging local
    results by proximity, is handled afterwards in region_utils.py so
    that behavior stays identical whether Gemini or the TF-IDF fallback
    produced the underlying scores.

    Returns the same listing dicts, each with an added "match_score"
    (0-100) and "match_reason" (a short explanation), sorted best-first.

    Raises GeminiUnavailableError if Gemini can't be reached or the
    response can't be parsed, so the caller can fall back to matcher.py.
    """
    if not applicant_skills.strip() or not listings:
        return []

    client = _get_client()

    listings_block = "\n".join(
        f'- id {job["id"]}: "{job["title"]}" at {job["company"]} '
        f'(location: {job["location"]}; required skills: {job["skills"]})'
        for job in listings
    )

    location_line = (
        f"Applicant's location: {applicant_location}\n"
        if applicant_location.strip()
        else "Applicant's location: not specified\n"
    )

    prompt = f"""You are the matching engine for a job recommendation system.

Applicant's skills: {applicant_skills}
{location_line}
Job listings:
{listings_block}

For EVERY listing above, score how well it fits the applicant's skills on
a 0-100 scale (100 = perfect fit, 0 = no relevant overlap at all), and give
a one-sentence reason. Consider related/adjacent skills, not just exact
word matches (e.g. "React" experience is relevant to a "frontend developer"
role even if the listing doesn't say "React"). Base the score itself only
on skill fit, not on location. If the applicant's location is specified and
a listing is nearby or in the same area, you may briefly mention that in
the reason, but do not let it change the score.

Respond ONLY with a JSON array, no other text, in this exact format:
[{{"id": <listing id>, "match_score": <number 0-100>, "match_reason": "<one sentence>"}}]
"""

    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.2,
            ),
        )
        scored = json.loads(response.text)
    except Exception as e:
        raise GeminiUnavailableError(f"Gemini request failed: {e}") from e

    scores_by_id = {int(item["id"]): item for item in scored}

    ranked = []
    for job in listings:
        result = dict(job)
        gemini_result = scores_by_id.get(job["id"])
        if gemini_result:
            result["match_score"] = round(float(gemini_result["match_score"]), 1)
            result["match_reason"] = gemini_result.get("match_reason", "")
        else:
            result["match_score"] = 0.0
            result["match_reason"] = ""
        ranked.append(result)

    ranked.sort(key=lambda x: x["match_score"], reverse=True)
    return ranked


def gemini_extract_resume_profile(resume_text: str) -> dict:
    """
    Asks Gemini to read raw resume text and return both a clean list of
    skills AND the applicant's likely location (city/province), read
    from the resume's address or contact-info section. This detected
    location is what powers the "top match near you" grouping in
    region_utils.py -- e.g. a resume listing a Quezon City address will
    surface Quezon City-based listings first.

    Returns a dict: {"skills": [...], "location": "<city/province or ''>"}

    Raises GeminiUnavailableError if Gemini can't be reached or the
    response can't be parsed.
    """
    if not resume_text.strip():
        return {"skills": [], "location": ""}

    client = _get_client()

    prompt = f"""Read this resume text and extract two things:

1. "skills": a clean list of professional skills (technical tools,
   programming languages, software, and relevant soft skills). Only
   include skills actually mentioned or clearly implied by the
   experience described. Keep each skill short (1-3 words).

2. "location": the applicant's city or province, read from their
   address or contact-info section (e.g. "Quezon City", "Iloilo City",
   "Janiuay, Iloilo"). If no address is present anywhere in the resume,
   return an empty string for this field. Do not guess a location from
   unrelated content such as a previous employer's office address.

Resume text:
\"\"\"
{resume_text[:6000]}
\"\"\"

Respond ONLY with a JSON object, no other text, in this exact format:
{{"skills": ["python", "project management", "sql"], "location": "Quezon City"}}
"""

    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.1,
            ),
        )
        parsed = json.loads(response.text)
    except Exception as e:
        raise GeminiUnavailableError(f"Gemini request failed: {e}") from e

    skills = [str(s).strip().lower() for s in parsed.get("skills", []) if str(s).strip()]
    location = str(parsed.get("location", "") or "").strip()
    return {"skills": skills, "location": location}


def gemini_extract_skills(resume_text: str) -> list[str]:
    """
    Asks Gemini to read raw resume text and return a clean list of skills
    (technical and soft skills), rather than relying on exact keyword
    matches against a fixed vocabulary.

    Raises GeminiUnavailableError if Gemini can't be reached or the
    response can't be parsed.
    """
    if not resume_text.strip():
        return []

    client = _get_client()

    prompt = f"""Extract a clean list of professional skills (technical
tools, programming languages, software, and relevant soft skills) from
this resume text. Only include skills actually mentioned or clearly
implied by the experience described. Keep each skill short (1-3 words).

Resume text:
\"\"\"
{resume_text[:6000]}
\"\"\"

Respond ONLY with a JSON array of strings, no other text, e.g.:
["python", "project management", "sql"]
"""

    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.1,
            ),
        )
        skills = json.loads(response.text)
    except Exception as e:
        raise GeminiUnavailableError(f"Gemini request failed: {e}") from e

    return [str(s).strip().lower() for s in skills if str(s).strip()]