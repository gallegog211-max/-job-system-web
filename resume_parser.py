import io
import re

import docx
import PyPDF2


def extract_text_from_pdf(file_stream) -> str:
    reader = PyPDF2.PdfReader(file_stream)
    text = []
    for page in reader.pages:
        text.append(page.extract_text() or "")
    return "\n".join(text)


def extract_text_from_docx(file_stream) -> str:
    document = docx.Document(file_stream)
    return "\n".join(p.text for p in document.paragraphs)


def extract_resume_text(filename: str, file_bytes: bytes) -> str:
    """
    Dispatches to the right extractor based on file extension.
    Raises ValueError for unsupported file types.
    """
    stream = io.BytesIO(file_bytes)
    lower_name = filename.lower()

    if lower_name.endswith(".pdf"):
        return extract_text_from_pdf(stream)
    elif lower_name.endswith(".docx"):
        return extract_text_from_docx(stream)
    else:
        raise ValueError("Unsupported file type. Please upload a PDF or DOCX resume.")


def find_skills_in_text(resume_text: str, known_skills: set[str]) -> list[str]:
    """
    Scans the resume text for any known skill keyword (case-insensitive,
    whole-word match) and returns the ones found, in the order they first
    appear in the resume.
    """
    text_lower = resume_text.lower()
    found = []
    for skill in known_skills:
        pattern = r"\b" + re.escape(skill.lower()) + r"\b"
        if re.search(pattern, text_lower) and skill not in found:
            found.append(skill)
    return found


def build_skill_vocabulary(listings: list[dict]) -> set[str]:
    """
    Builds the set of known skill keywords from every listing's "skills"
    field, so the resume parser knows what terms are worth looking for.
    """
    vocabulary = set()
    for listing in listings:
        for token in listing["skills"].split():
            vocabulary.add(token)
    return vocabulary


# Common Philippine cities/areas that tend to appear in a resume's
# address or contact-info section. Shares the same table used by
# region_utils.py's proximity matching, so a location detected here
# will always be recognized there too.
from ph_locations import match_location


def find_location_in_text(resume_text: str) -> str:
    """
    Scans resume text for a recognizable Philippine city/area name and
    returns it (title-cased) if found, so the applicant's detected
    address can feed directly into the location-based match grouping.
    Returns "" if nothing recognizable is found.
    """
    match = match_location(resume_text)
    return match["city"].title() if match else ""
